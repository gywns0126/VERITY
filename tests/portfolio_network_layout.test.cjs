const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {performance}=require('node:perf_hooks');
const source=fs.readFileSync(path.join(__dirname,'../review/member-map/prototype-network-layout.js'),'utf8');
const box={Map,Set,Math,Number,Float64Array,TypeError};vm.runInNewContext(source,box);
const layout=box.memberNetworkLayout;
const item=(id,kind='document',stockIds=[])=>({id,kind,stockIds,width:160,height:64});
const rows=map=>[...map].map(([id,p])=>[id,{...p}]);
const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
function freeze(value){if(value&&typeof value==='object'){Object.freeze(value);Object.values(value).forEach(freeze);}return value;}
function check(items,result){
 assert.equal(result.size,items.length);assert.ok(result instanceof Map);
 const placed=items.map(n=>{const p=result.get(n.id);assert.ok(p&&Number.isFinite(p.x)&&Number.isFinite(p.y),n.id);return{...n,...p};});
 for(let i=0;i<placed.length;i++)for(let j=0;j<i;j++){
  const a=placed[i],b=placed[j],dx=Math.abs(a.x-b.x),dy=Math.abs(a.y-b.y);
  assert.ok(dx+1e-8>=(a.width+b.width)/2+16||dy+1e-8>=(a.height+b.height)/2+16,`overlap ${a.id} / ${b.id}`);
 }
 if(items.length){
  const left=Math.min(...placed.map(p=>p.x-p.width/2)),right=Math.max(...placed.map(p=>p.x+p.width/2));
  const top=Math.min(...placed.map(p=>p.y-p.height/2)),bottom=Math.max(...placed.map(p=>p.y+p.height/2));
  assert.ok(Math.abs((left+right)/2-500)<1e-8);assert.ok(Math.abs((top+bottom)/2-340)<1e-8);
 }
}
function graph(count,stocks=2){
 const items=Array.from({length:stocks},(_,i)=>item('stock-'+i,'stock')),links=[];
 for(let i=0;i<count;i++){
  const root='stock-'+i%stocks,id='record-'+String(i).padStart(4,'0');items.push(item(id,i%3?'document':'event',[root]));links.push({from:root,to:id});
  if(i%7===0&&stocks>1)links.push({from:'stock-'+(i+1)%stocks,to:id});
  if(i>stocks&&i%4===0)links.push({from:id,to:'record-'+String(i-stocks).padStart(4,'0')});
 }
 return{items,links};
}
test('empty/singleton/isolated inputs retain every ID without input changes',()=>{
 assert.equal(layout([],[]).size,0);
 for(const items of [[item('only','stock')],Array.from({length:18},(_,i)=>item('isolated-'+i))]){
  const before=JSON.stringify(items);freeze(items);check(items,layout(items,[]));assert.equal(JSON.stringify(items),before);
 }
});
test('shuffled items/links, reversed duplicate edges and self/dangling edges give identical deterministic positions',()=>{
 const {items,links}=graph(114,3),before=JSON.stringify({items,links});freeze(items);freeze(links);
 const first=layout(items,links);check(items,first);
 const reordered=items.slice().sort((a,b)=>a.id.split('').reverse().join('').localeCompare(b.id.split('').reverse().join('')));
 const reversed=links.slice().reverse().map(e=>({from:e.to,to:e.from}));
 assert.deepEqual(rows(layout(reordered,[...reversed,...links,{from:'missing',to:items[0].id},{from:items[0].id,to:items[0].id}])),rows(first));
 assert.equal(JSON.stringify({items,links}),before);
});
test('actual stock adjacency keeps source clusters near their participants, not stockIds/category guesses',()=>{
 const items=[item('a','stock'),item('b','stock')],links=[];
 for(const root of ['a','b'])for(let i=0;i<12;i++){const id=root+'-source-'+i;items.push(item(id,'document',[root==='a'?'b':'a']));links.push({from:root,to:id});}
 const result=layout(items,links);check(items,result);
 for(const root of ['a','b']){
  const other=root==='a'?'b':'a',members=items.filter(n=>n.id.startsWith(root+'-'));
  const own=members.reduce((sum,n)=>sum+distance(result.get(n.id),result.get(root)),0)/members.length;
  const foreign=members.reduce((sum,n)=>sum+distance(result.get(n.id),result.get(other)),0)/members.length;
  assert.ok(own<foreign*.6,`${root}: actual peers ${own.toFixed(1)} vs unrelated root ${foreign.toFixed(1)}`);
 }
 const changedMetadata=items.map(n=>({...n,stockIds:['unconnected-metadata']}));
 assert.deepEqual(rows(layout(changedMetadata,links)),rows(result),'metadata cannot invent attraction edges');
});
test('shared event is near the participant midpoint and source-to-source edges influence 2D geometry',()=>{
 const items=[item('a','stock'),item('b','stock'),item('shared','event',['a','b']),item('one'),item('two')];
 const links=[{from:'a',to:'shared'},{from:'b',to:'shared'},{from:'a',to:'one'},{from:'b',to:'two'}];
 const result=layout(items,links);check(items,result);
 const a=result.get('a'),b=result.get('b'),middle={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
 assert.ok(distance(result.get('shared'),middle)<distance(a,b)*.3);
 assert.notDeepEqual(rows(layout(items,[...links,{from:'one',to:'two'}])),rows(result),'actual non-stock edges affect layout');
 assert.ok(new Set([...result.values()].map(p=>Math.round(p.x))).size>2,'not category columns');
});
for(const [count,stocks]of[[114,2],[500,2],[500,15],[500,1]])test(`${count} records plus ${stocks} stocks: all finite, full inclusion and 16px card clearance`,t=>{
 const {items,links}=graph(count,stocks),before=JSON.stringify({items,links});freeze(items);freeze(links);
 const start=performance.now(),result=layout(items,links),elapsed=performance.now()-start;
 check(items,result);assert.equal(JSON.stringify({items,links}),before);
 t.diagnostic(`${items.length} nodes / ${links.length} links: ${elapsed.toFixed(1)}ms (local Node, not browser SLA)`);
});
test('dense 500-node actual graph has bounded synchronous work, no omitted nodes or overlaps',t=>{
 const items=Array.from({length:500},(_,i)=>item('n'+String(i).padStart(3,'0'),i<4?'stock':'event')),links=[];
 for(let a=0;a<items.length;a++)for(let b=a+1;b<items.length;b++)links.push({from:items[a].id,to:items[b].id});
 const start=performance.now(),result=layout(items,links),elapsed=performance.now()-start;check(items,result);
 t.diagnostic(`500 nodes / ${links.length} unique links: ${elapsed.toFixed(1)}ms (32 fixed iterations)`);
});
test('mixed dimensions keep real bounds without clamping or mutating input, invalid IDs fail explicitly',()=>{
 const {items,links}=graph(35,2);items.forEach((n,i)=>{n.width=80+i%5*20;n.height=24+i%6*8;});
 check(items,layout(items,links));
 assert.throws(()=>layout([item('same'),item('same')],[]),TypeError);
});

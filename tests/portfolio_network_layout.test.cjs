const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {performance}=require('node:perf_hooks');
const source=fs.readFileSync(path.join(__dirname,'../review/member-map/prototype-network-layout.js'),'utf8');
const box={Map,Set,Math,Number,Float64Array,TypeError};vm.runInNewContext(source,box);
const layout=box.memberNetworkLayout;
const explore=box.memberNetworkExplore;
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

test('network exploration uses literal case-insensitive text across identity and evidence fields without mutation',()=>{
 const items=[
  {id:'stock:mix[ed]+',kind:'stock',name:'Café Labs',ticker:'MiXeD'},
  {id:'filing:1',kind:'event',recordKind:'document',layer:'filing',name:'Annual report',
   evidence:[{source:'Reuters',title:'Report (A+B)',explanation:'Literal .* punctuation'}]},
  {id:'candidate:1',kind:'event',recordKind:'relationship',layer:'candidates',name:'Unreviewed'},
 ];
 const links=[{id:'public-edge',from:items[0].id,to:items[1].id}];
 const before=JSON.stringify({items,links});freeze(items);freeze(links);
 assert.deepEqual([...explore(items,links).ids].sort(),items.map(n=>n.id).sort(),'omitted kinds means all recognized kinds');
 assert.deepEqual([...explore(items,links,{query:'MIXED'}).ids],[items[0].id]);
 assert.deepEqual([...explore(items,links,{query:'reUTers'}).ids],[items[1].id]);
 assert.deepEqual([...explore(items,links,{query:'a+b'}).ids],[items[1].id],'regex punctuation is a literal substring');
 assert.deepEqual([...explore(items,links,{query:'.*'}).ids],[items[1].id]);
 assert.deepEqual([...explore(items,links,{query:'mix[ed]+'}).ids],[items[0].id],'identity punctuation is also literal');
 assert.equal(JSON.stringify({items,links}),before);
});

test('kind filters distinguish omitted from empty and use the runtime relationship/source/candidate classification',()=>{
 const items=[
  {id:'s',kind:'stock'},
  {id:'r',kind:'event',recordKind:'relationship',layer:'relationships'},
  {id:'src',kind:'event',recordKind:'document',layer:'filing'},
  {id:'c',kind:'event',recordKind:'relationship',layer:'candidates'},
  {id:'override',kind:'event',recordKind:'document',layer:'filing',networkKind:'candidate'},
 ];
 assert.deepEqual([...explore(items,[]).ids].sort(),items.map(n=>n.id).sort());
 assert.equal(explore(items,[],{kinds:[]}).ids.size,0);
 assert.deepEqual([...explore(items,[],{kinds:['relationship','candidate']}).ids].sort(),['c','override','r']);
 assert.deepEqual([...explore(items,[],{kinds:['stock']}).ids],['s']);
});

test('local depth is a bounded BFS over allowed kinds and intersects with the literal search result',()=>{
 const items=[
  {id:'stock',kind:'stock',name:'Anchor'},
  {id:'rel',kind:'event',recordKind:'relationship',layer:'relationships',name:'Reviewed relation'},
  {id:'source',kind:'event',recordKind:'document',layer:'filing',name:'Public source'},
  {id:'candidate',kind:'event',recordKind:'relationship',layer:'candidates',name:'Candidate bridge'},
  {id:'far',kind:'event',recordKind:'document',layer:'filing',name:'Far source'},
 ];
 const links=[{id:'a',from:'stock',to:'rel'},{id:'b',from:'rel',to:'source'},
  {id:'c',from:'stock',to:'candidate'},{id:'d',from:'source',to:'far'}];
 assert.deepEqual([...explore(items,links,{anchor:'stock',depth:1}).ids].sort(),['candidate','rel','stock']);
 assert.deepEqual([...explore(items,links,{anchor:'stock',depth:2,query:'source'}).ids],['source']);
 assert.deepEqual([...explore(items,links,{anchor:'stock',depth:2,kinds:['stock','source']}).ids],['stock'],
  'a filtered relationship cannot be traversed as a hidden bridge');
 assert.deepEqual([...explore(items,links,{anchor:'missing',depth:1}).ids],[]);
 assert.deepEqual([...explore(items,links,{anchor:'stock',depth:99}).ids].sort(),items.map(n=>n.id).sort(),
  'depth is capped at three');
 const result=explore(items,links,{anchor:'stock',depth:2});
 assert.deepEqual(result.links.map(link=>link.id).sort(),['a','b','c']);
 assert.ok(result.links.every(link=>links.includes(link)),'returned links are original input links, not invented edges');
});

test('orphan removal uses the visible induced links after query and kind filtering',()=>{
 const items=[{id:'a',kind:'stock',name:'Keep A'},{id:'b',kind:'stock',name:'Keep B'},
  {id:'alone',kind:'event',recordKind:'document',layer:'filing',name:'Keep alone'}];
 const links=[{id:'edge',from:'a',to:'b'},{id:'dangling',from:'a',to:'missing'}];
 assert.deepEqual([...explore(items,links,{showOrphans:false}).ids].sort(),['a','b']);
 assert.deepEqual(explore(items,links,{query:'alone',showOrphans:false}).ids, new Set());
 assert.deepEqual(explore(items,links,{kinds:['stock'],showOrphans:false}).links.map(link=>link.id),['edge']);
});

test('layout options preserve defaults, while pinned finite positions stay exact and reserve 16px clearance',()=>{
 const items=[item('stock','stock'),item('record-a'),item('record-b')];
 const links=[{from:'stock',to:'record-a'},{from:'record-a',to:'record-b'}];
 const defaults=layout(items,links),explicitDefaults=layout(items,links,{});
 assert.deepEqual(rows(explicitDefaults),rows(defaults));
 assert.notDeepEqual(rows(layout(items,links,{linkDistance:420})),rows(defaults));
 assert.notDeepEqual(rows(layout(items,links,{repulsion:0})),rows(defaults));
 const pinned=new Map([['stock',{x:200,y:180}],['record-a',{x:200,y:180}]]);
 const result=layout(items,links,{pinned});
 assert.deepEqual([result.get('stock').x,result.get('stock').y],[200,180]);
 assert.deepEqual([result.get('record-a').x,result.get('record-a').y],[200,180],'user-pinned overlaps remain intentional and unchanged');
 const floating={...item('record-b'),...result.get('record-b')};
 for(const id of ['stock','record-a']){
  const fixed={...item(id,id==='stock'?'stock':'document'),...result.get(id)};
  const dx=Math.abs(floating.x-fixed.x),dy=Math.abs(floating.y-fixed.y);
  assert.ok(dx>=(floating.width+fixed.width)/2+16||dy>=(floating.height+fixed.height)/2+16,
   `unpinned node clears reserved pin ${id}`);
 }
});

test('a pin from the existing 500x340 world frame keeps free stock anchors in that same vicinity',()=>{
 const {items,links}=graph(28,3),baseline=layout(items,links),pinId='stock-1',pin=baseline.get(pinId);
 const result=layout(items,links,{pinned:new Map([[pinId,{...pin}]])});
 assert.deepEqual(result.get(pinId),pin,'the supplied world coordinate remains exact');
 for(const id of ['stock-0','stock-2'])assert.ok(distance(result.get(id),baseline.get(id))<200,
  `${id} remains near its prior world anchor instead of shifting toward the origin`);
});

test('invalid and unknown pins are ignored and inputs remain unchanged',()=>{
 const {items,links}=graph(16,2),before=JSON.stringify({items,links});
 const invalid=new Map([['stock-0',{x:NaN,y:4}],['record-0000',{x:4,y:Infinity}],['unknown',{x:20,y:30}]]);
 const expected=layout(items,links),actual=layout(items,links,{pinned:invalid});
 assert.deepEqual(rows(actual),rows(expected));
 assert.equal(JSON.stringify({items,links}),before);
});

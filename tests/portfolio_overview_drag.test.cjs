const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../review/member-map/prototype-overview-runtime.js'),'utf8');
function extract(name){const start=source.indexOf('function '+name+'('),begin=source.indexOf('{',start);let depth=0;for(let i=begin;i<source.length;i++){if(source[i]==='{')depth++;else if(source[i]==='}'&&--depth===0)return source.slice(start,i+1);}throw Error(name);}
test('an overview move adopts the displayed title offset only when explicitly called',()=>{
 const n={id:'event',x:.5,y:.5},el={dataset:{overviewTitle:'true'},style:{left:'140px',top:'160px'}};
 const context={nodeById:{event:n},nodesEl:{querySelector:()=>el},memberOverviewElements:new Map([[el,{}]]),state:{zoom:.2},WORLD_WIDTH:1000,WORLD_HEIGHT:680,point:()=>({x:100,y:120}),parseFloat,Number};
 vm.runInNewContext(extract('memberOverviewRebaseMovement'),context);
 assert.deepEqual(n,{id:'event',x:.5,y:.5});
 context.memberOverviewRebaseMovement('event');
 assert.equal(n.x,.7);assert.ok(Math.abs(n.y-(.5+40/136))<1e-12);
});
test('unrendered/full-size titles and invalid zoom cannot rewrite coordinates',()=>{
 for(const [overview,zoom]of[['false',.2],['true',0],['true',NaN]]){
  const n={id:'a',x:.6,y:.7},el={dataset:{overviewTitle:overview},style:{left:'140px',top:'160px'}};
  const context={nodeById:{a:n},nodesEl:{querySelector:()=>el},memberOverviewElements:new Map([[el,{}]]),state:{zoom},WORLD_WIDTH:1000,WORLD_HEIGHT:680,point:()=>({x:100,y:120}),parseFloat,Number};
  vm.runInNewContext(extract('memberOverviewRebaseMovement'),context);context.memberOverviewRebaseMovement('a');assert.equal(n.x,.6);assert.equal(n.y,.7);
 }
});
test('manual title anchors do not depend on compact label grid columns',()=>{
 const context={memberLayoutBases:new Map([['a',{x:.5,y:.5}]]),Math};vm.runInNewContext(extract('memberOverviewManual'),context);
 assert.equal(context.memberOverviewManual({id:'a',x:.5,y:.5}),false);
 assert.equal(context.memberOverviewManual({id:'a',x:.52,y:.5}),true);
 assert.equal(context.memberOverviewManual({id:'a',x:.52,y:.51}),true);
 assert.match(source,/automatic=items\.flatMap\(\(item,i\)=>item\.manual\?\[\]/);
});
test('compact relationship paths and hit areas follow displayed cards without replacing animation elements',()=>{
 const nodes={a:{id:'a',x:.5,y:.5},b:{id:'b',x:.6,y:.6}};
 const els={a:{dataset:{overviewTitle:'true'},style:{left:'140px',top:'160px'}},b:{dataset:{overviewTitle:'true'},style:{left:'380px',top:'220px'}}};
 const path={setAttribute(k,v){this[k]=v}},hit={setAttribute(k,v){this[k]=v}},flow={style:{},identity:1},rim={style:{},identity:2};
 const pair={group:{style:{}},path,hit,flow,rim};
 const context={nodeById:nodes,nodesEl:{querySelector:s=>els[s.match(/"([^"]+)"/)[1]]},edges:[{id:'e',from:'a',to:'b'}],edgeEls:new Map([['e',pair]]),point:()=>({x:1,y:2}),parseFloat,Number};
 vm.runInNewContext(extract('memberOverviewSyncEdgePaths'),context);context.memberOverviewSyncEdgePaths();
 assert.equal(path.d,'M 140 160 Q 276 190 380 220');assert.equal(hit.d,path.d);
 assert.equal(flow.style.offsetPath,'path("'+path.d+'")');assert.equal(rim.style.offsetPath,flow.style.offsetPath);
 assert.equal(pair.flow,flow);assert.equal(pair.rim,rim);assert.equal(nodes.a.x,.5);
 els.a.style.left='148px';context.memberOverviewSyncEdgePaths();assert.match(path.d,/^M 148 160 /);
 assert.equal(pair.flow,flow);
});

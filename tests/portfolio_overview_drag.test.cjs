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

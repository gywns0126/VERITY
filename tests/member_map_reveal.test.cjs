const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../vercel-api/public/member-map-canvas.html'),'utf8');
const a=source.indexOf('function keepRevealedMemberRecordsInView('),b=source.indexOf('\nfunction syncMemberScopedLayout(',a);
assert.ok(a>=0&&b>a);
function fixture(rects,narrow=false){
  const nodes=rects.map((rect,i)=>({id:'record-'+i,x:.2,y:.8,rect})),state={zoom:.45,panX:70,panY:-30,notes:{keep:'memo'},marks:{keep:{read:true}}};
  const box={state,innerWidth:narrow?390:1200,root:{dataset:{detail:narrow?'open':'closed'}},
    space:{getBoundingClientRect:()=>({left:0,right:460,top:0,bottom:580})},detail:{getBoundingClientRect:()=>({top:400})},
    memberVisible:new Set(nodes.map(n=>n.id)),nodesEl:{querySelector:s=>{const n=nodes.find(n=>s.includes('"'+n.id+'"'));return n?{hidden:false,getBoundingClientRect:()=>n.rect}:null;}},
    renders:0,saves:0,renderMap(){box.renders++;},saveZoomSoon(){box.saves++;}};
  vm.runInNewContext(source.slice(a,b),box);return {box,nodes,group:{records:nodes}};
}
test('deployed reveal pans an offscreen card without changing zoom, saved coordinates or marks',()=>{
  const {box,nodes,group}=fixture([{left:-96,right:22,top:1482,bottom:1540}]);
  const before=JSON.stringify(nodes),personal=JSON.stringify([box.state.notes,box.state.marks]);
  box.keepRevealedMemberRecordsInView(group,new Set());
  assert.equal(box.state.panX,178);assert.equal(box.state.panY,-1002);assert.equal(box.state.zoom,.45);
  assert.equal(JSON.stringify(nodes),before);assert.equal(JSON.stringify([box.state.notes,box.state.marks]),personal);
  assert.equal(box.renders,1);assert.equal(box.saves,1);
});
test('visible/newly collapsed cards preserve camera; more tracks only the new batch',()=>{
  const {box,nodes,group}=fixture([{left:50,right:170,top:60,bottom:120},{left:50,right:170,top:800,bottom:860}]);
  const before=JSON.stringify(box.state);box.keepRevealedMemberRecordsInView(group,new Set());assert.equal(JSON.stringify(box.state),before);
  box.keepRevealedMemberRecordsInView(group,new Set(nodes.map(n=>n.id)));assert.equal(JSON.stringify(box.state),before);
  box.keepRevealedMemberRecordsInView(group,new Set([nodes[0].id]));assert.equal(box.state.panY,-322);assert.equal(box.state.zoom,.45);
});
test('reveal keeps a card above the narrow detail sheet; oversized cards keep their title reachable',()=>{
  const {box,group}=fixture([{left:30,right:200,top:420,bottom:490}],true);
  box.keepRevealedMemberRecordsInView(group,new Set());assert.equal(box.state.panY,-132);
  const tall=fixture([{left:30,right:200,top:420,bottom:900}],true);
  tall.box.keepRevealedMemberRecordsInView(tall.group,new Set());assert.equal(tall.box.state.panY,-438);
});
test('emitted click handlers preserve drag suppression and follow reveal but not collapse',()=>{
  class E{constructor(){this.dataset={};this.style={};}append(){}setAttribute(){}}
  const record={id:'record'},box={document:{createElement:()=>new E()},memberCategoryIcon:()=>new E(),memberGroups:new Map(),memberGroupLayer:{append(){}},
    suppressClick:true,cancelGesture:null,closePreview(){},memberGroupManual:new Set(),memberReveal:'',memberVisible:new Set(),memberOpenGroups:new Map(),
    renders:0,reveals:0,renderMap(){box.renders++;box.memberVisible=box.memberOpenGroups.has('business')?new Set(['record']):new Set();},
    keepRevealedMemberRecordsInView(g,prior){box.reveals++;assert.equal(g.key,'business');assert.equal(typeof prior.has,'function');}};
  vm.runInNewContext(source.slice(source.indexOf('function makeMemberGroup('),source.indexOf('function memberCardSize(')),box);
  const group=box.makeMemberGroup('business');group.records=[record];
  group.button.onclick();assert.equal(box.renders,0);assert.equal(box.suppressClick,false);
  group.button.onclick();assert.equal(box.reveals,1);assert.equal(box.memberVisible.size,1);
  group.button.onclick();assert.equal(box.reveals,1);assert.equal(box.memberVisible.size,0);
  group.more.onclick();assert.equal(box.reveals,2);
});

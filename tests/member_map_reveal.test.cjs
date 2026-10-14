const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../vercel-api/public/member-map-canvas.html'),'utf8');
const a=source.indexOf('function keepRevealedMemberRecordsInView('),b=source.indexOf('\nfunction syncMemberScopedLayout(',a);
assert.ok(a>=0&&b>a);
function revealFixture({spread=false,width=460,height=580,detailTop=580,narrow=false}={}){
  const world={width:1000,height:680},state={zoom:.45,panX:-150,panY:136,notes:{keep:'memo'},marks:{keep:{read:true}}};
  const positions=spread?[
    ...Array.from({length:6},(_,i)=>({id:'record-new-'+i,x:.02+i*.015,y:.18+i*.08,width:260,height:112})),
    {id:'stock-a',kind:'stock',x:.5,y:.5,width:160,height:52},
    {id:'stock-b',kind:'stock',x:.98,y:.82,width:160,height:52},
  ]:[
    {id:'record-old',x:.04,y:.2,width:260,height:112},
    ...Array.from({length:6},(_,i)=>({id:'record-new-'+i,x:.055+i*.01,y:.23+i*.085,width:260,height:112})),
    {id:'stock-a',kind:'stock',x:.07,y:.26,width:160,height:52},
    {id:'stock-b',kind:'stock',x:.085,y:.29,width:160,height:52},
  ];
  const centerX=width/2,centerY=height/2;
  const rectFor=item=>{
    const x=centerX+(item.x-.5)*world.width*state.zoom+state.panX;
    const y=centerY+(item.y-.5)*world.height*state.zoom+state.panY;
    const w=item.width*state.zoom,h=item.height*state.zoom;
    return {left:x-w/2,right:x+w/2,top:y-h/2,bottom:y+h/2};
  };
  const elements=new Map(positions.map(item=>[item.id,{hidden:false,getBoundingClientRect:()=>rectFor(item)}]));
  const group={records:positions.filter(item=>item.id.startsWith('record-')),stockIds:positions.filter(item=>item.kind==='stock').map(item=>item.id),x:.05,y:.24,
    button:{offsetWidth:160,offsetHeight:50,hidden:false,getBoundingClientRect:()=>rectFor({x:.05,y:.24,width:160,height:50})},
    morePoint:{x:.05,y:1},more:{offsetWidth:96,offsetHeight:32,hidden:false,getBoundingClientRect:()=>rectFor({x:.05,y:1,width:96,height:32})}};
  const box={state,innerWidth:narrow?390:1200,WORLD_WIDTH:world.width,WORLD_HEIGHT:world.height,root:{dataset:{detail:narrow?'open':'closed'}},
    space:{clientWidth:width,getBoundingClientRect:()=>({left:0,right:width,top:0,bottom:height})},detail:{getBoundingClientRect:()=>({top:detailTop})},
    memberVisible:new Set(positions.filter(item=>item.id.startsWith('record-')).map(item=>item.id)),nodeById:Object.fromEntries(positions.filter(item=>item.kind==='stock').map(item=>[item.id,item])),
    nodesEl:{querySelector:s=>{const match=s.match(/data-node=["']([^"']+)["']/),el=match&&elements.get(match[1]);return el||null;}},
    renders:0,saves:0,renderMap(){box.renders++;},saveZoomSoon(){box.saves++;}};
  const a=source.indexOf('function keepRevealedMemberRecordsInView('),b=source.indexOf('\nfunction syncMemberScopedLayout(',a);
  vm.runInNewContext(source.slice(a,b),box);
  return {box,nodes:positions,group,rectFor,viewport:{left:0,right:width,top:0,bottom:narrow?Math.min(height,detailTop):height}};
}
function targetRects(fixture){
  const newRecords=fixture.group.records.filter(item=>item.id.startsWith('record-new-'));
  return [...newRecords,fixture.group.button,fixture.group.more,...fixture.group.stockIds.map(id=>fixture.nodes.find(item=>item.id===id))].map(item=>
    item===fixture.group.button||item===fixture.group.more?item.getBoundingClientRect():fixture.rectFor(item));
}
function assertTargetsInside(fixture){
  for(const rect of targetRects(fixture))assert.ok(rect.left>=fixture.viewport.left-1e-6&&rect.right<=fixture.viewport.right+1e-6&&
    rect.top>=fixture.viewport.top-1e-6&&rect.bottom<=fixture.viewport.bottom+1e-6,`target DOM box fits viewport: ${JSON.stringify(rect)}`);
}
test('reveal pans six new cards, group title, more button and connected stock boxes by the minimum delta',()=>{
  const fixture=revealFixture(),{box,nodes,group}=fixture;
  const before=JSON.stringify({nodes,group:{x:group.x,y:group.y,morePoint:group.morePoint}}),saved=JSON.stringify({notes:box.state.notes,marks:box.state.marks});
  const rects=targetRects(fixture),union={left:Math.min(...rects.map(r=>r.left)),right:Math.max(...rects.map(r=>r.right)),
    top:Math.min(...rects.map(r=>r.top)),bottom:Math.max(...rects.map(r=>r.bottom))};
  const clampPan=(current,low,high)=>Math.max(low,Math.min(high,current));
  const area={left:fixture.viewport.left+12,right:fixture.viewport.right-12,top:fixture.viewport.top+12,bottom:fixture.viewport.bottom-12};
  const expectedX=clampPan(0,area.left-union.left,area.right-union.right);
  const expectedY=clampPan(0,area.top-union.top,area.bottom-union.bottom);
  const moreBefore=group.more.getBoundingClientRect();
  assert.ok(moreBefore.bottom>fixture.viewport.bottom&&moreBefore.bottom-fixture.viewport.bottom<7,
    'fixture reproduces the more button clipped by roughly six pixels');
  box.keepRevealedMemberRecordsInView(group,new Set(['record-old']));
  assertTargetsInside(fixture);
  assert.ok(Math.abs(box.state.panX-(-150+expectedX))<1e-6,'x pan is the smallest displacement that fits the union');
  assert.ok(Math.abs(box.state.panY-(136+expectedY))<1e-6,'y pan is the smallest displacement that fits the union');
  assert.equal(box.state.zoom,.45);
  assert.equal(JSON.stringify({nodes,group:{x:group.x,y:group.y,morePoint:group.morePoint}}),before);assert.equal(JSON.stringify({notes:box.state.notes,marks:box.state.marks}),saved);
  assert.equal(box.renders,1);assert.equal(box.saves,1);
});
test('the entire newly revealed batch and its anchors zoom out only as much as needed, respecting the .08 floor',()=>{
  const fixture=revealFixture({spread:true}),{box,group}=fixture;
  const before=JSON.stringify({nodes:fixture.nodes,group:{x:group.x,y:group.y,morePoint:group.morePoint}}),saved=JSON.stringify({notes:box.state.notes,marks:box.state.marks});
  box.keepRevealedMemberRecordsInView(group,new Set());
  assert.ok(box.state.zoom<.45&&box.state.zoom>=.08,`minimal fit zoom stays above floor (got ${box.state.zoom})`);
  assertTargetsInside(fixture);
  const fitted=targetRects(fixture),width=Math.max(...fitted.map(r=>r.right))-Math.min(...fitted.map(r=>r.left));
  const height=Math.max(...fitted.map(r=>r.bottom))-Math.min(...fitted.map(r=>r.top));
  assert.ok(width>=fixture.viewport.right-fixture.viewport.left-24-1e-5||height>=fixture.viewport.bottom-fixture.viewport.top-24-1e-5,
    'the fitted target union is tight on at least one viewport axis');
  assert.equal(JSON.stringify({nodes:fixture.nodes,group:{x:group.x,y:group.y,morePoint:group.morePoint}}),before);assert.equal(JSON.stringify({notes:box.state.notes,marks:box.state.marks}),saved);
});
test('already-visible target union and collapse leave the camera untouched; more only includes newly revealed records',()=>{
  const fixture=revealFixture(),{box,nodes,group}=fixture;
  box.state.panX=100;box.state.panY=30;
  const before=JSON.stringify(box.state),visible=new Set([...nodes.map(node=>node.id),...group.stockIds]);
  box.keepRevealedMemberRecordsInView(group,visible);
  assert.equal(JSON.stringify(box.state),before);assert.equal(box.renders,0);
  box.keepRevealedMemberRecordsInView(group,visible);assert.equal(JSON.stringify(box.state),before,'previously visible members are not treated as a new reveal');
});
test('narrow canvas reveal avoids the open detail sheet and anchors an oversized card at its top',()=>{
  const fixture=revealFixture({narrow:true,detailTop:400});
  fixture.box.keepRevealedMemberRecordsInView(fixture.group,new Set());assertTargetsInside(fixture);
  assert.equal(fixture.box.state.zoom,.45);
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

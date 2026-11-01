const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const canvas=fs.readFileSync(path.join(__dirname,'../vercel-api/public/member-map-canvas.html'),'utf8');
const relationship=fs.readFileSync(path.join(__dirname,'../review/member-map/prototype-relationship-layout.js'),'utf8');
const clone=v=>JSON.parse(JSON.stringify(v));
function actualFunction(source,name){
  const start=source.indexOf('function '+name+'(');assert.ok(start>=0,name+' exists in delivered source');
  const begin=source.indexOf('){',start)+1;assert.ok(begin>start);let depth=0;
  for(let i=begin;i<source.length;i++){if(source[i]==='{')depth++;else if(source[i]==='}'&&!--depth)return source.slice(start,i+1);}
  assert.fail('unterminated '+name);
}
function fixture(){
  const captures=new Map(),listeners=new Map(),pending=[];
  let dispatch;
  function element(kind='background'){
    const local=new Map(),classes=new Set();
    const el={kind,dataset:kind==='node'?{node:'stock'}:{},hidden:false,style:{},clientWidth:1000,clientHeight:600,
      classList:{add:n=>classes.add(n),remove:n=>classes.delete(n),contains:n=>classes.has(n)},
      getBoundingClientRect:()=>({left:10,top:20,width:1000,height:600,right:1010,bottom:620}),
      closest(selector){if(kind==='node'&&(selector==='[data-node]'||selector.includes('button')))return el;return null;},
      focus(){},addEventListener(type,fn,capture=false){if(!local.has(type))local.set(type,[]);local.get(type).push({fn,capture:!!capture});},
      removeEventListener(type,fn){local.set(type,(local.get(type)||[]).filter(v=>v.fn!==fn));},
      setPointerCapture(id){captures.set(id,el);},hasPointerCapture:id=>captures.get(id)===el,
      releasePointerCapture(id){if(captures.get(id)!==el)return;captures.delete(id);dispatch('lostpointercapture',{pointerId:id,target:el});},
      handlers:local};
    listeners.set(el,local);return el;
  }
  const space=element(),nodeElement=element('node'),detail=element(),panel=element();
  panel.getBoundingClientRect=()=>({left:682,right:1002,top:8,bottom:680,width:320,height:672});
  const node={id:'stock',kind:'stock',x:.45,y:.3};
  const notes={attached:{id:'attached',target:'stock',text:'unsaved attached note',pinned:true},free:{id:'free',target:'',x:.25,y:.6,text:'unsaved free note'}};
  const state={zoom:2,panX:13,panY:-7,notes,marks:{stock:{important:true}},selected:'stock'};
  const history={past:[],future:[]},selections=[],rebases=[];
  const context={state,nodes:[node],nodeById:{stock:node},WORLD_WIDTH:1000,WORLD_HEIGHT:680,MIN_ZOOM:.08,MAX_ZOOM:4,
    space,detail,root:{dataset:{detail:'closed'},querySelector:s=>s==='.an-relation-panel'?panel:{disabled:false,textContent:''}},
    memberWritable:true,spaceHeld:false,nativeGesture:null,cancelGesture:null,nodeMoveActive:false,nodePointerActive:false,suppressClick:false,pendingMapResize:false,
    selectedItems:new Set(),moveHistory:history,HISTORY_LIMIT:50,
    focusOffsets:new Map(),memberDisplayOffsets:new Map(),memberRelationshipBases:new Map(),memberRelationshipLegacyOrigins:new Map(),
    initialPositions:new Map([['stock',{x:node.x,y:node.y}]]),memberLayoutBases:new Map([['stock',{x:node.x,y:node.y}]]),
    movableItems:()=>[{id:node.id,item:node,el:nodeElement}],closePreview(){},renderSelection(){},renderMap(){},observeTour(){},saveZoomSoon(){},clearFocus(){},
    select(id){selections.push(id);state.selected=id;},openNote(id){selections.push('note:'+id);},applyMapResize(){},syncHistoryButtons(){},
    setTimeout(fn){pending.push(fn);return pending.length;},clearTimeout(){},innerWidth:1240,Math,Number,Map,Set};
  vm.createContext(context);
  const helpers=['layoutSnapshot','recordMove','travelHistory','beginMove','zoomAt','viewPosition'].map(n=>actualFunction(canvas,n)).join('\n')+'\n'+actualFunction(relationship,'memberRelationshipRebaseMovement');
  const inputStart=canvas.indexOf('const memberTouchPoints=new Map();'),inputEnd=canvas.indexOf('let narrowFocusLayout=',inputStart);
  assert.ok(inputStart>0&&inputEnd>inputStart);
  const wheelStart=canvas.indexOf("space.addEventListener('wheel',function(e){"),wheelEnd=canvas.indexOf("space.addEventListener('pointerenter'",wheelStart);
  vm.runInContext(helpers+'\n'+canvas.slice(wheelStart,wheelEnd)+'\n'+canvas.slice(inputStart,inputEnd)+'\n'+actualFunction(relationship,'memberRelationFitViewport')+
    '\nglobalThis.touchState=()=>({mode:memberTouchDrag?.mode,count:memberTouchPoints.size,drag:memberTouchDrag});',context);
  const rebase=context.memberRelationshipRebaseMovement;
  context.memberRelationshipRebaseMovement=id=>{rebases.push(id);rebase(id);};
  // Bind the same actual beginMove path used by the delivered appendMemberNode.
  nodeElement.onpointerdown=e=>context.beginMove(e,node.id,nodeElement);
  nodeElement.onclick=()=>context.select(node.id);
  dispatch=(type,options={})=>{
    const event={type,pointerId:1,pointerType:'touch',button:0,clientX:300,clientY:220,detail:1,target:space,shiftKey:false,ctrlKey:false,metaKey:false,
      deltaX:0,deltaY:0,deltaMode:0,preventDefault(){this.defaultPrevented=true;},stopPropagation(){this.stopped=true;},...options};
    const target=captures.get(event.pointerId)||event.target;event.target=target;
    for(const {fn,capture}of [...(space.handlers.get(type)||[])])if(capture)fn(event);
    if(!event.stopped&&target!==space){for(const {fn,capture}of [...(target.handlers.get(type)||[])])if(!capture)fn(event);target['on'+type]?.(event);}
    if(!event.stopped)for(const {fn,capture}of [...(space.handlers.get(type)||[])])if(!capture)fn(event);
    return event;
  };
  return {c:context,state,node,space,panel,nodeElement,history,captures,selections,rebases,dispatch,notes:clone(notes),pending};
}
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,`${a} != ${b}`);

test('single touch pans the stage in CSS pixels without editing node, marks or unsaved notes',()=>{
  const f=fixture(),before=clone(f.node),marks=clone(f.state.marks);
  f.dispatch('pointerdown');assert.equal(f.c.touchState().mode,'pan');assert.equal(f.captures.get(1),f.space);
  f.dispatch('pointermove',{clientX:380,clientY:260});near(f.state.panX,93);near(f.state.panY,33);
  f.dispatch('pointerup',{clientX:380,clientY:260});assert.equal(f.c.cancelGesture,null);assert.equal(f.captures.size,0);
  assert.deepEqual(f.node,before);assert.deepEqual(f.state.notes,f.notes);assert.deepEqual(f.state.marks,marks);
  f.c.travelHistory(false);near(f.state.panX,13);near(f.state.panY,-7);
  f.c.travelHistory(true);near(f.state.panX,93);near(f.state.panY,33);
});
test('single touch node drag uses world scale, commits one history entry and supports undo/redo',()=>{
  const f=fixture(),before=clone(f.node),camera={zoom:2,panX:13,panY:-7};
  f.dispatch('pointerdown',{target:f.nodeElement});f.dispatch('pointermove',{clientX:380,clientY:260});
  near(f.node.x,before.x+80/2000);near(f.node.y,before.y+40/1360);assert.deepEqual(f.rebases,['stock']);
  f.dispatch('pointerup',{clientX:380,clientY:260});assert.equal(f.history.past.length,1);
  f.c.travelHistory(false);assert.deepEqual(f.node,before);f.c.travelHistory(true);near(f.node.x,before.x+.04);
  assert.deepEqual(f.state.notes,f.notes);for(const k of Object.keys(camera))assert.equal(f.state[k],camera[k]);
});
test('native mouse node drag and background pan retain stable captures and do not touch notes',()=>{
  const f=fixture();
  f.dispatch('pointerdown',{pointerType:'mouse',target:f.nodeElement});assert.equal(f.captures.get(1),f.nodeElement);
  f.dispatch('pointermove',{pointerType:'mouse',clientX:340,clientY:240});f.dispatch('pointerup',{pointerType:'mouse',clientX:340,clientY:240});
  near(f.node.x,.47);near(f.node.y,.3+20/1360);assert.equal(f.history.past.length,1);
  f.dispatch('pointerdown',{pointerType:'mouse'});assert.equal(f.captures.get(1),f.space);
  f.dispatch('pointermove',{pointerType:'mouse',clientX:350,clientY:250});f.dispatch('pointerup',{pointerType:'mouse',clientX:350,clientY:250});
  near(f.state.panX,63);near(f.state.panY,23);assert.equal(f.c.cancelGesture,null);assert.deepEqual(f.state.notes,f.notes);
});
test('two touches preserve the midpoint world anchor while translating and scaling',()=>{
  const f=fixture(),before=clone(f.node);
  f.dispatch('pointerdown',{pointerId:1,clientX:300,clientY:220});f.dispatch('pointerdown',{pointerId:2,clientX:500,clientY:220});
  const wx=(400-10-500-13)/2,wy=(220-20-300+7)/2;
  f.dispatch('pointermove',{pointerId:1,clientX:320,clientY:230});f.dispatch('pointermove',{pointerId:2,clientX:520,clientY:230});
  near(f.state.zoom,2);near(f.state.panX,33);near(f.state.panY,3);
  f.dispatch('pointermove',{pointerId:2,clientX:720,clientY:230});near(f.state.zoom,4);
  near((520-10-500-f.state.panX)/4,wx);near((230-20-300-f.state.panY)/4,wy);
  assert.deepEqual(f.node,before);assert.deepEqual(f.state.notes,f.notes);
});
test('3→2 reanchors a pinch; 2→1 reanchors pan without jump or lost final movement',()=>{
  const f=fixture();
  f.dispatch('pointerdown',{pointerId:1,clientX:300,clientY:220});f.dispatch('pointerdown',{pointerId:2,clientX:500,clientY:220});
  f.dispatch('pointermove',{pointerId:2,clientX:550,clientY:220});
  f.dispatch('pointerdown',{pointerId:3,clientX:650,clientY:260});f.dispatch('pointerup',{pointerId:1});
  assert.equal(f.c.touchState().count,2);assert.equal(f.c.touchState().mode,'pinch');
  const old={...f.state};f.dispatch('pointermove',{pointerId:2,clientX:550,clientY:220});near(f.state.zoom,old.zoom);near(f.state.panX,old.panX);near(f.state.panY,old.panY);
  f.dispatch('pointermove',{pointerId:3,clientX:700,clientY:280});assert.ok(f.state.zoom>old.zoom);
  f.dispatch('pointerup',{pointerId:2});assert.equal(f.c.touchState().mode,'pan');
  const pan={x:f.state.panX,y:f.state.panY,z:f.state.zoom};f.dispatch('pointermove',{pointerId:3,clientX:725,clientY:295});
  near(f.state.panX,pan.x+25);near(f.state.panY,pan.y+15);near(f.state.zoom,pan.z);
  f.dispatch('pointerup',{pointerId:3});assert.equal(f.c.touchState().count,0);assert.equal(f.captures.size,0);
  assert.deepEqual(f.state.notes,f.notes);assert.ok([f.state.zoom,f.state.panX,f.state.panY].every(Number.isFinite));
});
test('pointer cancellation restores the active node/camera transaction without notes or history changes',()=>{
  for(const target of ['node','background']){
    const f=fixture(),before=clone(f.node),camera=clone(f.state);
    f.dispatch('pointerdown',{target:target==='node'?f.nodeElement:f.space});f.dispatch('pointermove',{clientX:390,clientY:270});
    f.dispatch('pointercancel');assert.deepEqual(f.node,before);for(const k of ['zoom','panX','panY'])assert.equal(f.state[k],camera[k]);
    assert.equal(f.history.past.length,0);assert.equal(f.captures.size,0);assert.equal(f.c.cancelGesture,null);assert.deepEqual(f.state.notes,f.notes);
  }
});
test('pinch cancellation releases every capture and restores its starting camera',()=>{
  const f=fixture(),before=clone(f.state);
  f.dispatch('pointerdown',{pointerId:1});f.dispatch('pointerdown',{pointerId:2,clientX:500});f.dispatch('pointermove',{pointerId:2,clientX:650});
  f.dispatch('lostpointercapture',{pointerId:1});for(const k of ['zoom','panX','panY'])assert.equal(f.state[k],before[k]);
  assert.equal(f.c.touchState().count,0);assert.equal(f.captures.size,0);assert.equal(f.history.past.length,0);assert.deepEqual(f.state.notes,f.notes);
});
test('cancelling a rebased touch drag restores raw coordinates AND exact displayed world origin',()=>{
  for(const offsetExists of [true,false]){
    const f=fixture(),c=f.c;f.node.kind='event';f.node.x=.47;f.node.y=.32;
    if(offsetExists){c.focusOffsets.set('stock',{x:.2,y:.15});c.memberDisplayOffsets.set('stock',{x:.25,y:.18});}
    c.memberRelationshipLegacyOrigins.set('stock',{x:.55,y:.6});
    const raw=clone(f.node),world=clone(c.viewPosition(f.node)),focus=clone([...c.focusOffsets]),display=clone([...c.memberDisplayOffsets]);
    f.dispatch('pointerdown',{target:f.nodeElement});f.dispatch('pointermove',{clientX:390,clientY:270});
    assert.notDeepEqual(clone(c.viewPosition(f.node)),world,'real rebase plus movement changes the visible point');
    assert.equal(c.memberDisplayOffsets.has('stock'),true,'delivered rebase created/changed an offset');
    f.dispatch('pointercancel');assert.deepEqual(f.node,raw);assert.deepEqual(clone(c.viewPosition(f.node)),world);
    assert.deepEqual(clone([...c.focusOffsets]),focus);assert.deepEqual(clone([...c.memberDisplayOffsets]),display);
    assert.deepEqual(f.state.notes,f.notes);assert.equal(f.history.past.length,0);
  }
});
test('release-generated click is suppressed, next real pointer click and keyboard activation remain available',()=>{
  const f=fixture();
  f.dispatch('pointerdown',{pointerType:'mouse',target:f.nodeElement});f.dispatch('pointermove',{pointerType:'mouse',clientX:350});f.dispatch('pointerup',{pointerType:'mouse',clientX:350});
  const release=f.dispatch('click',{target:f.nodeElement,detail:1});assert.equal(release.defaultPrevented,true);assert.deepEqual(f.selections,[]);
  f.dispatch('pointerdown',{target:f.nodeElement,pointerType:'mouse'});f.dispatch('pointerup',{target:f.nodeElement,pointerType:'mouse'});
  f.dispatch('click',{target:f.nodeElement,detail:1});assert.deepEqual(f.selections,['stock']);
  f.c.suppressClick=true;f.dispatch('click',{target:f.nodeElement,detail:0});assert.deepEqual(f.selections,['stock','stock']);
});
test('wheel pans; ctrl-wheel and WebKit pinch preserve anchors and exclude concurrent pointer ownership',()=>{
  const f=fixture();f.dispatch('wheel',{deltaX:20,deltaY:30});near(f.state.panX,-7);near(f.state.panY,-37);near(f.state.zoom,2);
  const wx=(300-10-500-f.state.panX)/2,wy=(220-20-300-f.state.panY)/2;
  f.dispatch('wheel',{ctrlKey:true,deltaY:-20});assert.ok(f.state.zoom>2);
  near((300-10-500-f.state.panX)/f.state.zoom,wx);near((220-20-300-f.state.panY)/f.state.zoom,wy);
  f.dispatch('gesturestart',{scale:1});const initial=f.state.zoom;
  f.dispatch('gesturechange',{scale:1.2});f.dispatch('gesturechange',{scale:1.5});near(f.state.zoom,Math.min(4,initial*1.5));
  f.dispatch('gestureend');f.dispatch('pointerdown');f.dispatch('gesturestart',{scale:1});assert.equal(f.c.nativeGesture,null);
  const z=f.state.zoom;f.dispatch('wheel',{ctrlKey:true,deltaY:-30});assert.equal(f.state.zoom,z);
});
test('fit-only viewport excludes the desktop overlay and leaves camera/nodes/notes unchanged',()=>{
  const f=fixture(),before=clone({state:f.state,node:f.node});
  assert.deepEqual(clone(f.c.memberRelationFitViewport()),{width:660,height:600,offsetX:-170,offsetY:0});
  f.panel.hidden=true;assert.deepEqual(clone(f.c.memberRelationFitViewport()),{width:1000,height:600,offsetX:0,offsetY:0});
  f.panel.hidden=false;f.c.innerWidth=390;assert.deepEqual(clone(f.c.memberRelationFitViewport()),{width:1000,height:600,offsetX:0,offsetY:0});
  assert.deepEqual({state:f.state,node:f.node},before);
});

const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../vercel-api/public/member-map-canvas.html'),'utf8');
function extract(name){
  const start=source.indexOf('function '+name+'(');assert.ok(start>=0,name);
  const begin=source.indexOf('{',start);let depth=0;
  for(let i=begin;i<source.length;i++){if(source[i]==='{')depth++;else if(source[i]==='}'&&--depth===0)return source.slice(start,i+1);}
  assert.fail('Unclosed '+name);
}
// Exercise the delivered panel controller against existing editor elements.
// Panel navigation must never reconstruct a draft editor or touch the camera.
function panelFixture(width=1240){
  function element(){return {children:[],dataset:{},attributes:{},events:{},hidden:false,
    style:{setProperty(){}},getBoundingClientRect(){return {top:0}},
    append(...children){this.children.push(...children)},setAttribute(k,v){this.attributes[k]=v},
    addEventListener(k,v){this.events[k]=v},focus(){this.focused=true}};}
  const root=element(),body=element(),inbox=element(),detail=element(),primaryTools=element();
  const editor={value:'unsaved synthetic memo',selectionStart:7,selectionEnd:12};detail.append(editor);
  root.querySelector=()=>body;
  const state={zoom:.71,panX:37,panY:-19,selected:null,activeNote:null,noteList:false,notes:{n:{text:'retained'}},marks:{}};
  const c={root,inbox,detail,primaryTools,state,memberStockList:false,showGuide:false,cancelGesture:null,
    innerWidth:width,space:element(),workbar:element(),ResizeObserver:class{observe(){}},
    document:{createElement:element},closePreview(){},renderDetail(){},editable:target=>target===editor};
  vm.runInNewContext(extract('installMemberRelationPanel'),c);c.installMemberRelationPanel();
  const panel=body.children[0],bar=panel.children[0],[changes,evidence,close]=bar.children,toggle=primaryTools.children[0];
  return {c,state,panel,inbox,detail,editor,toggle,changes,evidence,close};
}
test('relation side panel toggles and tabs preserve camera, notes and the exact unsaved editor',()=>{
  const f=panelFixture(),before=JSON.stringify(f.state),editor=f.editor;
  for(let i=0;i<12;i++){
    f.toggle.onclick();assert.equal(f.panel.hidden,true);
    f.toggle.onclick();f.evidence.onclick();assert.equal(f.inbox.hidden,true);assert.equal(f.detail.hidden,false);
    f.changes.onclick();assert.equal(f.inbox.hidden,false);assert.equal(f.detail.hidden,true);
  }
  assert.equal(JSON.stringify(f.state),before);assert.equal(f.detail.children[0],editor);
  assert.equal(editor.value,'unsaved synthetic memo');assert.equal(editor.selectionStart,7);assert.equal(editor.selectionEnd,12);
  f.close.onclick();assert.equal(f.panel.hidden,true);assert.equal(f.toggle.focused,true);
});
test('narrow view starts with the reading panel folded and opens without moving the map',()=>{
  const f=panelFixture(390),before=JSON.stringify(f.state);assert.equal(f.panel.hidden,true);
  f.toggle.onclick();assert.equal(f.panel.hidden,false);assert.equal(JSON.stringify(f.state),before);
});
test('panel does not steal Escape from a note editor and repeated rendering retains the chosen tab',()=>{
  const f=panelFixture();let prevented=0;
  f.panel.events.keydown({key:'Escape',target:f.editor,preventDefault(){prevented++}});
  assert.equal(prevented,0);assert.equal(f.panel.hidden,false);
  f.state.activeNote='n';f.c.renderDetail();assert.equal(f.detail.hidden,false);
  f.changes.onclick();f.c.renderDetail();assert.equal(f.inbox.hidden,false);
  f.panel.events.keydown({key:'Escape',target:f.panel,preventDefault(){prevented++},stopPropagation(){}});
  assert.equal(prevented,1);assert.equal(f.panel.hidden,true);
});
function fixture(){
  const state={panX:73,panY:-29,zoom:.39,focusId:'stock',notes:{n:{x:.2,y:.7,text:'retained'}}};
  const calls={render:0,cancel:0,focus:0,preview:0,fit:0},frames=[];
  const c={state,space:{clientWidth:900,clientHeight:400,classList:{contains:()=>false}},nodeMoveActive:false,nativeGesture:null,pendingMapResize:false,narrowFocusLayout:false,
    memberPanelResizeOrigin:null,memberInitialViewportPending:false,memberInitialViewportFrame:0,memberInitialViewportSize:'',hasSavedCamera:false,requestAnimationFrame:fn=>(frames.push(fn),frames.length),cancelGesture:()=>calls.cancel++,closePreview:()=>calls.preview++,renderMap:()=>calls.render++,focusStock:()=>calls.focus++,fitNodes:()=>calls.fit++};
  vm.runInNewContext(extract('cancelMemberInitialViewport')+'\n'+extract('queueMemberInitialViewport')+'\n'+extract('fitMemberInitialViewport')+'\n'+extract('applyMapResize'),c);
  const origin=()=>[c.space.clientWidth/2+state.panX,c.space.clientHeight/2+state.panY];
  const begin=()=>{c.memberPanelResizeOrigin={width:c.space.clientWidth,height:c.space.clientHeight,panX:state.panX,panY:state.panY};};
  return {c,state,calls,origin,begin,frame:()=>frames.shift()?.()};
}
test('library expansion/collapse keeps the exact visible world origin, zoom and notes without cancelling its gesture or fitting',()=>{
  const f=fixture(),before=f.origin(),notes=JSON.stringify(f.state.notes),zoom=f.state.zoom;
  for(const height of [240,600,400,240,400]){
    f.begin();f.c.space.clientHeight=height;f.c.applyMapResize();
    assert.deepEqual(f.origin(),before);assert.equal(f.state.zoom,zoom);assert.equal(JSON.stringify(f.state.notes),notes);
    assert.equal(f.c.memberPanelResizeOrigin,null);
  }
  assert.equal(f.calls.cancel,0);assert.equal(f.calls.focus,0);assert.equal(f.calls.render,5);
});
test('one queued resize uses its first origin against the final panel size, not an intermediate one',()=>{
  const f=fixture(),before=f.origin();f.begin();f.c.space.clientHeight=350;f.c.space.clientHeight=200;f.c.applyMapResize();
  assert.deepEqual(f.origin(),before);assert.equal(f.calls.render,1);
});
test('node movement defers pending panel compensation until its existing gesture completes',()=>{
  const f=fixture(),before=f.origin();f.begin();f.c.nodeMoveActive=true;f.c.space.clientHeight=220;f.c.applyMapResize();
  assert.equal(f.c.pendingMapResize,true);assert.equal(f.calls.render,0);assert.ok(f.c.memberPanelResizeOrigin);
  f.c.nodeMoveActive=false;f.c.applyMapResize();assert.equal(f.c.pendingMapResize,false);assert.deepEqual(f.origin(),before);
});
test('ordinary window resize keeps the existing cancellation and explicit narrow-focus behavior',()=>{
  const f=fixture();f.c.space.clientWidth=390;f.c.applyMapResize();
  assert.equal(f.calls.cancel,1);assert.equal(f.calls.focus,1);assert.equal(f.calls.render,1);assert.equal(f.c.narrowFocusLayout,true);
  assert.deepEqual([f.state.panX,f.state.panY],[73,-29]);
});
test('initial fit waits for a measurable viewport and runs only once without changing notes',()=>{
  const f=fixture(),notes=JSON.stringify(f.state.notes);f.c.cancelGesture=null;f.c.memberInitialViewportPending=true;
  f.c.space.clientWidth=0;f.c.space.clientHeight=0;f.begin();
  assert.equal(f.c.fitMemberInitialViewport(),false);f.c.applyMapResize();
  assert.equal(f.calls.fit,0);assert.equal(f.c.memberInitialViewportPending,true);assert.equal(f.c.memberPanelResizeOrigin,null);
  f.c.space.clientWidth=980;f.c.space.clientHeight=389;f.c.applyMapResize();
  f.frame();assert.equal(f.calls.fit,0);f.frame();
  assert.equal(f.calls.fit,1);assert.equal(f.c.memberInitialViewportPending,false);
  f.c.applyMapResize();assert.equal(f.calls.fit,1);assert.equal(JSON.stringify(f.state.notes),notes);
});
test('restored camera cancels deferred fit; a zero-size origin cannot shift a later visible map',()=>{
  const f=fixture(),before=[f.state.panX,f.state.panY,f.state.zoom];f.c.cancelGesture=null;
  f.c.memberInitialViewportPending=true;f.c.hasSavedCamera=true;
  f.c.memberPanelResizeOrigin={width:0,height:0,panX:0,panY:0};f.c.applyMapResize();f.frame();
  assert.equal(f.calls.fit,0);assert.equal(f.c.memberInitialViewportPending,false);
  assert.deepEqual([f.state.panX,f.state.panY,f.state.zoom],before);
});
test('initial fit waits for the final library height across animation frames',()=>{
  const f=fixture();f.c.cancelGesture=null;f.c.memberInitialViewportPending=true;
  f.c.space.clientHeight=589;f.c.applyMapResize();f.frame();assert.equal(f.calls.fit,0);
  f.c.space.clientHeight=389;f.c.applyMapResize();f.frame();assert.equal(f.calls.fit,0);
  f.frame();assert.equal(f.calls.fit,1);assert.equal(f.c.memberPanelResizeOrigin,null);
});
test('queued panel compensation preserves newer camera input rather than restoring stale captured pan',()=>{
  const f=fixture();f.begin();f.state.panX+=22;f.state.panY-=13;
  const before=f.origin();f.c.space.clientHeight=220;f.c.applyMapResize();
  assert.deepEqual(f.origin(),before);assert.equal(f.calls.cancel,0);
});
test('delayed startup fit never overrides native pinch, background pan or completed deliberate input',()=>{
  for(const mode of ['pinch','pan','input']){
    const f=fixture(),before=[f.state.zoom,f.state.panX,f.state.panY];f.c.cancelGesture=null;f.c.memberInitialViewportPending=true;
    f.c.queueMemberInitialViewport();f.frame();
    if(mode==='pinch')f.c.nativeGesture={zoom:1};
    if(mode==='pan')f.c.space.classList.contains=name=>name==='panning';
    if(mode==='input')f.c.cancelMemberInitialViewport();
    f.frame();assert.equal(f.calls.fit,0,mode);assert.equal(f.c.memberInitialViewportPending,false);
    assert.deepEqual([f.state.zoom,f.state.panX,f.state.panY],before);
  }
  assert.match(source,/for\(const type of \['wheel','pointerdown','keydown','gesturestart'\]\)\s+space\.addEventListener\(type,cancelMemberInitialViewport,\{capture:true,passive:true\}\)/);
});

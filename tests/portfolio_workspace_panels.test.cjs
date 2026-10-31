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
function fixture(){
  const state={panX:73,panY:-29,zoom:.39,focusId:'stock',notes:{n:{x:.2,y:.7,text:'retained'}}};
  const calls={render:0,cancel:0,focus:0,preview:0,fit:0},frames=[];
  const c={state,space:{clientWidth:900,clientHeight:400,classList:{contains:()=>false}},nodeMoveActive:false,nativeGesture:null,pendingMapResize:false,narrowFocusLayout:false,
    memberPanelResizeOrigin:null,memberInitialViewportPending:false,memberInitialViewportFrame:0,memberInitialViewportSize:'',hasSavedCamera:false,requestAnimationFrame:fn=>(frames.push(fn),frames.length),cancelGesture:()=>calls.cancel++,closePreview:()=>calls.preview++,renderMap:()=>calls.render++,focusStock:()=>calls.focus++,fitNodes:()=>calls.fit++};
  vm.runInNewContext(extract('memberLibraryHeight')+'\n'+extract('cancelMemberInitialViewport')+'\n'+extract('queueMemberInitialViewport')+'\n'+extract('fitMemberInitialViewport')+'\n'+extract('applyMapResize'),c);
  const origin=()=>[c.space.clientWidth/2+state.panX,c.space.clientHeight/2+state.panY];
  const begin=()=>{c.memberPanelResizeOrigin={width:c.space.clientWidth,height:c.space.clientHeight,panX:state.panX,panY:state.panY};};
  return {c,state,calls,origin,begin,frame:()=>frames.shift()?.()};
}
test('height bounds retain a reachable header, cap short viewports and reject nonfinite input',()=>{
  const f=fixture();
  for(const [input,min,max,expected]of[[200,36,500,200],[-4,36,500,36],[999,36,500,500],[0,52,52,52],[NaN,36,500,36],[Infinity,36,500,36]])
    assert.equal(f.c.memberLibraryHeight(input,min,max),expected);
});
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

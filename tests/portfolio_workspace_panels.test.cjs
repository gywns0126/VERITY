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
  const calls={render:0,cancel:0,focus:0,preview:0};
  const c={state,space:{clientWidth:900,clientHeight:400},nodeMoveActive:false,pendingMapResize:false,narrowFocusLayout:false,
    memberPanelResizeOrigin:null,cancelGesture:()=>calls.cancel++,closePreview:()=>calls.preview++,renderMap:()=>calls.render++,focusStock:()=>calls.focus++};
  vm.runInNewContext(extract('memberLibraryHeight')+'\n'+extract('applyMapResize'),c);
  const origin=()=>[c.space.clientWidth/2+state.panX,c.space.clientHeight/2+state.panY];
  const begin=()=>{c.memberPanelResizeOrigin={width:c.space.clientWidth,height:c.space.clientHeight,panX:state.panX,panY:state.panY};};
  return {c,state,calls,origin,begin};
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

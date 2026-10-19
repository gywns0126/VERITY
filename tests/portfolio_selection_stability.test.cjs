const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(process.env.MEMBER_MAP_CANVAS||path.join(__dirname,'../vercel-api/public/member-map-canvas.html'),'utf8');
const clone=x=>JSON.parse(JSON.stringify(x));
function extract(marker){
 const start=source.indexOf(marker);assert.ok(start>=0,marker);const begin=source.indexOf('{',start);let depth=0;
 for(let i=begin;i<source.length;i++){if(source[i]==='{')depth++;else if(source[i]==='}'&&--depth===0)return source.slice(start,i+1);}
 assert.fail('Unclosed '+marker);
}
function fixture(stable=true){
 const state={scenario:'base',filter:'all',topic:'all',view:'all',selected:'',focusId:'',zoom:.43,panX:97,panY:-61,activeNote:'',noteList:false,
  notes:{memo:{id:'memo',target:'a',text:'synthetic retained note',x:.13,y:.27}},marks:{}};
 const nodeById={a:{id:'a',kind:'stock',x:.14,y:.31},b:{id:'b',kind:'stock',x:.79,y:.63},event:{id:'event',kind:'event',x:.45,y:.54}};
 const root={dataset:{relationshipCentered:stable?'true':'false'},querySelector:()=>({textContent:''})};
 const calls={focus:[],clear:0,render:0,detail:0,save:0,prepare:0},focusOffsets=new Map(),focusOrigins=new Map();
 const context={state,nodeById,root,edges:[{id:'edge',from:'event',to:'a'}],selectedItems:new Set(),showGuide:false,
  selectionReturn:null,changedReturn:null,focusCamera:null,focusOffsets,focusOrigins,memberReveal:'',
  closePreview(){},observeTour(){},relevant:()=>new Set(Object.keys(nodeById)),detail:{scrollTop:0},
  focusStock(id){calls.focus.push(id);state.focusId=id;focusOffsets.set('event',{x:.3,y:.2});},
  clearFocus(){calls.clear++;state.focusId='';focusOffsets.clear();focusOrigins.clear();context.focusCamera=null;},
  prepareMemberGroups(){calls.prepare++;},renderMap(){calls.render++;},renderDetail(){calls.detail++;},save(){calls.save++;}};
 vm.runInNewContext(['selectionContext','invalidateMemberSelectionReturn','select','returnToMap'].map(n=>extract('function '+n+'(')).join('\n'),context);
 context.memberSelect=context.select;context.memberStockList=false;
 vm.runInNewContext(extract('select=function(...args)')+';',context);
 context.ungroupedSelect=context.select;
 vm.runInNewContext(extract('select=function(id,')+';',context);
 const snapshot=()=>clone({camera:{zoom:state.zoom,panX:state.panX,panY:state.panY},nodes:nodeById,notes:state.notes,marks:state.marks,focusId:state.focusId,offsets:[...focusOffsets]});
 return{state,nodeById,context,calls,snapshot};
}
test('actual member selection wrapper and base handler select/reselect/deselect without changing viewport, coordinates or notes',()=>{
 const f=fixture(),before=f.snapshot();
 for(const [id,toggle,selected]of[['a',true,'a'],['b',true,'b'],['b',true,''],['event',true,'event'],['edge',true,'edge'],['',false,''],['missing',false,'']]){
  f.context.select(id,toggle);assert.equal(f.state.selected,selected);assert.deepEqual(f.snapshot(),before);
 }
 assert.deepEqual(f.calls.focus,[]);assert.equal(f.calls.clear,0);assert.equal(f.calls.prepare,7);assert.equal(f.calls.detail,7);
});
test('deselection cannot restore an old fit camera or clear an explicitly chosen surrounding view',()=>{
 const f=fixture();f.state.focusId='a';f.context.focusOffsets.set('event',{x:.2,y:.1});f.state.selected='a';
 f.context.selectionReturn={context:f.context.selectionContext(),camera:{zoom:1,panX:0,panY:0},usedFit:true};
 const before=f.snapshot();f.context.select('a',true);assert.equal(f.state.selected,'');assert.deepEqual(f.snapshot(),before);
 f.context.select('b',true);assert.deepEqual(f.snapshot(),before);assert.deepEqual(f.calls.focus,[]);assert.equal(f.calls.clear,0);
});
test('explicit return-to-map still restores a prior fit camera and clears focus through the real wrapper',()=>{
 const f=fixture();f.state.focusId='a';f.state.selected='a';
 f.context.selectionReturn={context:f.context.selectionContext(),camera:{zoom:.7,panX:-18,panY:23},usedFit:true};
 const retained=clone({nodes:f.nodeById,notes:f.state.notes});f.context.returnToMap();
 assert.equal(f.state.focusId,'');assert.equal(f.state.selected,'');assert.equal(f.state.zoom,.7);assert.equal(f.state.panX,-18);assert.equal(f.state.panY,23);
 assert.deepEqual(clone({nodes:f.nodeById,notes:f.state.notes}),retained);
});
test('legacy non-relationship template retains its existing click-to-focus behavior',()=>{
 const f=fixture(false);f.context.select('a');assert.deepEqual(f.calls.focus,['a']);assert.equal(f.state.focusId,'a');
 f.context.select('');assert.equal(f.state.focusId,'');assert.equal(f.calls.clear,1);
});

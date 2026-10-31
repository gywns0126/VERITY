const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const directory=path.join(__dirname,'../review/member-map');
const source=fs.readFileSync(path.join(directory,'prototype-network-runtime.js'),'utf8');
const engineSource=fs.readFileSync(path.join(directory,'prototype-network-engine.js'),'utf8');
const geometry=fs.readFileSync(path.join(directory,'prototype-network-layout.js'),'utf8');
const relationship=fs.readFileSync(path.join(directory,'prototype-relationship-layout.js'),'utf8');
const clone=value=>JSON.parse(JSON.stringify(value));
function functionSource(text,name){
 const start=text.indexOf('function '+name+'(');assert.ok(start>=0,'actual function '+name);
 const begin=text.indexOf('{',start);let depth=0;
 for(let i=begin;i<text.length;i++){if(text[i]==='{')depth++;else if(text[i]==='}'&&--depth===0)return text.slice(text.slice(Math.max(0,start-6),start)==='async '?start-6:start,i+1);}
 assert.fail('unterminated '+name);
}
function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
function readOnlyMap(entries){
 const map=new Map(entries);for(const key of ['set','delete','clear'])Object.defineProperty(map,key,{value:()=>assert.fail('native map mutation: '+key)});return map;
}
function element(tag='div'){
 const el={tagName:tag.toUpperCase(),dataset:{},attributes:{},children:[],hidden:false,inert:false,isConnected:true,focusCalls:[],
  style:{setProperty(key,value){this[key]=value;}},classList:{add(){},contains(){return false;}},
  append(...children){this.children.push(...children);},replaceChildren(...children){this.children=children;},
  setAttribute(key,value){this.attributes[key]=value;},querySelector(){return null;},contains(node){return this.children.includes(node);},
  focus(options){this.focusCalls.push(options);},cloneNode(){return element(tag);},
  getBoundingClientRect(){return this.rect||{width:900,height:600,left:0,top:0};}};
 return el;
}
function fixture(){
 const stock={id:'stock',kind:'stock',name:'Stock',x:.27,y:.33},
  record={id:'source',kind:'event',recordKind:'document',layer:'filing',name:'Original source',x:.62,y:.71,evidence:[{url:'https://example.org/filing',title:'Filing'}]},
  candidate={id:'candidate',kind:'event',recordKind:'relationship',layer:'candidates',name:'Unreviewed',x:.7,y:.8,evidence:[]};
 const scope=freeze({stocks:[stock],records:[record,candidate],stockIds:['stock']});
 const edges=freeze([{id:'source-edge',from:'stock',to:'source',scenario:'current'},
  {id:'candidate-edge',from:'stock',to:'candidate',scenario:'current'},
  {id:'other-scenario',from:'source',to:'candidate',scenario:'other'},
  {id:'outside',from:'stock',to:'not-in-current-scope',scenario:'current'}]);
 const native=freeze({camera:{zoom:.63,panX:82,panY:-41},notes:{attached:{id:'attached',target:'source',text:'keep',pinned:true},free:{id:'free',x:.3,y:.2,text:'free'}},
  selected:'source',marks:{source:{important:true}},history:{past:[{before:{source:{x:.5,y:.5}},after:{source:{x:.62,y:.71}}}],future:[]}});
 const root=element(),host=element('section'),space=element(),nodes=element(),svg=element('svg'),inspector=element(),live=element();
 const rootParts=new Map([['#an-live',live]]);root.querySelector=selector=>rootParts.get(selector)||null;
 const gridFine=element('path'),gridCoarse=element('path'),gridParts=new Map([['.an-network-grid-fine',gridFine],['.an-network-grid-coarse',gridCoarse]]);
 space.querySelector=selector=>gridParts.get(selector)||null;
 const button=element('button'),controls=element(),alreadyInert=element(),style=element('style'),script=element('script');
 alreadyInert.inert=true;root.dataset.other='kept';root.children=[controls,alreadyInert,style,script,host];
 root.contains=el=>root.children.includes(el);host.hidden=true;
 const hostParts=new Map(['output','h2','footer','[data-network-action=close]'].map(key=>[key,element()]));
 host.querySelector=selector=>hostParts.get(selector);
 const observer={observed:[],disconnects:0,observe(el){this.observed.push(el);},disconnect(){this.disconnects++;}};
 const visualContext=freeze({stockIds:['stock'],scope:'native-current'}),visualCalls=[];
 const reference=freeze({kind:'reference',topic:'neutral',color:'#6b7684',width:1,dash:'2 4',
  statusLabel:'참고 자료',summaryLabel:'영향 미평가',lineLabel:'자료 귀속'});
 const engineCalls=[],engineState={camera:null,stage:null,destroys:0,resizes:0,highlights:[]};
 const engine={setCamera(camera){engineState.camera={...camera};},getCamera:()=>({...engineState.camera}),setStage(stage,zoom){engineState.stage=stage;engineState.stageZoom=zoom;},
  resize(){engineState.resizes++;},highlight(id){engineState.highlights.push(id);},destroy(){engineState.destroys++;}};
 const graph=element();
 const captures=new Set();space.setPointerCapture=id=>captures.add(id);space.hasPointerCapture=id=>captures.has(id);space.releasePointerCapture=id=>captures.delete(id);
 space.contains=target=>target===space||target===graph||nodes.children.includes(target);
 const context={Map,Set,Math,Number,Float64Array,TypeError,URL,document:{createElement:element,createElementNS:(_,tag)=>element(tag)},
  root,memberNetworkHost:host,memberNetworkSpace:space,memberNetworkNodes:nodes,memberNetworkSvg:svg,memberNetworkInspector:inspector,
  memberNetworkButton:button,memberNetworkResize:observer,memberNetworkSession:null,memberNetworkOpening:false,memberNetworkCache:null,memberNetworkGraph:graph,memberReset:false,
  memberLoadNetworkEngine:async()=>{},memberCreateNetworkEngine(...args){engineCalls.push(args);return engine;},
  space:element(),nativeGesture:false,cancelGesture:null,closePreview(){},closeSearch(){},
  memberScope:()=>scope,edges,inScenario:e=>e.scenario==='current',eventHoldings:n=>n.kind==='stock'?[n.id]:['stock'],
  memberDisplayDecisions:readOnlyMap([['source',{evidence:'reported'}],['candidate',{evidence:'pending'}]]),
  memberVisualContext:()=>visualContext,
  memberEdgeVisual:(edge,record,context)=>{visualCalls.push({edge,record,context});return reference;},
  nodesEl:{querySelector:()=>null},memberCategoryIcon:()=>element('span'),memberGroupKey:n=>n.layer||'other',memberRecordDateText:n=>n.asOf||'date unknown',
  memberPort:{postMessage(){assert.fail('no native save/source message during exploration');}},
  state:native,nodeById:{stock,source:record,candidate},moveHistory:native.history,
  initialPositions:readOnlyMap([['source',{x:.5,y:.5}]]),focusOffsets:readOnlyMap([['source',{x:.01,y:.02}]]),
  memberLayoutBases:readOnlyMap([['source',{x:.5,y:.5}]])};
 const names=['memberNetworkStage','memberNetworkSnapshot','memberNetworkKind','memberNetworkKindText','memberNetworkOptions','memberNetworkSyncControls','memberNetworkFilter','memberNetworkMove','memberNetworkArrange','memberNetworkCardDrag','memberNetworkSelect',
  'memberNetworkHighlight','renderMemberNetworkGrid','drawMemberNetwork','zoomMemberNetwork','fitMemberNetwork','closeMemberNetwork','openMemberNetwork'];
 // Include the exact input functions and their local helpers, not copied input
 // logic. Keep the existing synthetic native-state and engine fixture intact.
 const inputNames=[...source.matchAll(/\bfunction (memberNetwork[A-Za-z0-9_]+)\(/g)].map(match=>match[1]);
 vm.runInNewContext(geometry+'\n'+functionSource(relationship,'memberRelationshipIsMapRecord')+'\n'+[...new Set([...names,...inputNames])].map(name=>functionSource(source,name)).join('\n'),context);
 const actualLayout=context.memberNetworkLayout;let layoutCalls=0;
 context.memberNetworkLayout=(items,links,options)=>{layoutCalls++;return actualLayout(items,links,options);};
 const nativeValues=()=>clone({scope,edges,native,initial:[...context.initialPositions],offsets:[...context.focusOffsets],bases:[...context.memberLayoutBases]});
 const before=nativeValues();
 return{context,scope,edges,stock,record,candidate,native,root,host,space,nodes,svg,inspector,live,button,controls,alreadyInert,observer,hostParts,
  visualContext,visualCalls,reference,engine,engineCalls,engineState,graph,gridFine,gridCoarse,layoutCalls:()=>layoutCalls,assertNative:()=>assert.deepEqual(nativeValues(),before)};
}
test('CSS contract allows long or unbroken network card and detail text to wrap',()=>{
 assert.match(source,/#an-map-design \.an-network-space\[data-stage=cards\] \.an-network-node>span:last-child\{flex:1;min-width:0\}/);
 assert.match(source,/#an-map-design \.an-network-space\[data-stage=cards\] \.an-network-label\{[^}]*overflow:hidden;overflow-wrap:anywhere/);
 assert.match(source,/#an-map-design \.an-network-inspector p\{[^}]*overflow-wrap:anywhere/);
 assert.match(source,/#an-map-design \.an-network-inspector button\{[^}]*overflow-wrap:anywhere/);
 assert.match(source,/@media\(max-width:700px\)[^\n]*\.an-network-inspector\{max-height:220px/);
});
test('stage thresholds are dots / names / cards at the exact boundaries',()=>{
 const {context:c}=fixture();
 for(const [zoom,expected]of[[.02,'dots'],[.279999,'dots'],[.28,'names'],[.799999,'names'],[.8,'cards'],[4,'cards']])assert.equal(c.memberNetworkStage(zoom),expected);
});
test('compact overview retains every node, selection persists through hover, and clearing restores exploration',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
 assert.ok(s.camera.zoom<=.65);assert.equal(s.elements.size,3);
 c.memberNetworkSelect('source');s.elements.get('candidate').onpointerenter();
 assert.equal(f.engineState.highlights.at(-1),'source');assert.equal(s.elements.get('candidate').dataset.emphasis,'true');
 s.elements.get('candidate').onpointerleave();assert.equal(s.elements.get('candidate').dataset.faded,'true');assert.equal(s.elements.get('candidate').dataset.emphasis,'false');
 assert.equal(s.elements.get('stock').dataset.emphasis,'true');
 c.memberNetworkSelect('');s.elements.get('candidate').onfocus();
 assert.equal(f.engineState.highlights.at(-1),'candidate');
 assert.match(source,/\[data-stage=cards\] \.an-network-node\{[^}]*height:32px/);
 assert.match(source,/\[data-stage=cards\] \.an-network-node\[aria-pressed=true\]\{height:76px/);
 assert.equal(f.layoutCalls(),1);c.closeMemberNetwork();f.assertNative();
});
test('inspector exposes literal full evidence and peer navigation without moving camera or editing native draft',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
 const explanation='<img src=x onerror=alert(1)>\n'+('긴 원문 근거 '.repeat(100));
 s.byId.get('source').evidence[0]={url:'https://example.org/filing',source:'공식 원문',asOf:'2026-10-01',explanation};
 c.memberNetworkSelect('source');
 assert.equal(f.inspector.children.find(el=>el.className==='an-network-excerpt').textContent,explanation);
 assert.ok(f.inspector.children.some(el=>el.textContent==='자료 기준 2026-10-01'));
 assert.ok(f.inspector.children.some(el=>el.textContent==='https://example.org/filing'));
 const peer=f.inspector.children.find(el=>el.tagName==='BUTTON'&&el.textContent.includes('Stock'));
 assert.ok(peer);const camera=clone(s.camera),positions=clone([...s.positions]);
 c.document.activeElement=peer;peer.onclick();
 assert.equal(s.selected,'stock');assert.deepEqual(clone(f.inspector.children[0].focusCalls),[{preventScroll:true}]);
 assert.deepEqual(clone(s.camera),camera);assert.deepEqual(clone([...s.positions]),positions);
 assert.equal(f.layoutCalls(),1);c.closeMemberNetwork();f.assertNative();
});
test('keyboard traversal includes only projected visible nodes and re-admits them after explicit camera movement',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
 s.positions=new Map([['stock',{x:500,y:340}],['source',{x:1000,y:340}],['candidate',{x:500,y:-50}]]);
 s.camera={zoom:1,panX:0,panY:0};c.drawMemberNetwork();
 assert.equal(s.elements.get('stock').tabIndex,0);assert.equal(s.elements.get('source').tabIndex,-1);assert.equal(s.elements.get('candidate').tabIndex,-1);
 s.camera.panX=-100;c.drawMemberNetwork();assert.equal(s.elements.get('source').tabIndex,0);
 s.camera.panY=100;c.drawMemberNetwork();assert.equal(s.elements.get('candidate').tabIndex,0);
 assert.equal(f.layoutCalls(),1,'keyboard eligibility never recalculates positions');f.assertNative();
});
test('snapshot copies current scope and evidence, filters links by both current IDs and inScenario, and never promotes candidates',()=>{
 const f=fixture(),c=f.context,s=c.memberNetworkSnapshot(f.scope,f.edges);
 assert.deepEqual(Array.from(s.items,n=>n.id),['stock','source','candidate']);
 assert.deepEqual(Array.from(s.links,e=>e.id),['source-edge','candidate-edge']);
 assert.notEqual(s.items[1],f.record);assert.notEqual(s.items[1].evidence,f.record.evidence);assert.notEqual(s.items[1].evidence[0],f.record.evidence[0]);
 assert.notEqual(s.links[0],f.edges[0]);
 s.items[1].evidence[0].title='copied edit';s.links[0].from='copy-only';
 assert.equal(f.record.evidence[0].title,'Filing');assert.equal(f.edges[0].from,'stock');
 assert.equal(c.memberNetworkKind(s.items[2]),'candidate');assert.equal(s.items[2].recordKind,'relationship');assert.equal(s.items[2].layer,'candidates');f.assertNative();
});
test('actual open builds every current node once with source/candidate semantics and independent session objects',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
 assert.equal(f.layoutCalls(),1);assert.equal(s.elements.size,3);assert.equal(s.positions.size,3);assert.equal(s.paths.length,2);
 assert.equal(s.elements.get('source').dataset.kind,'source');assert.equal(s.elements.get('candidate').dataset.kind,'candidate');
 assert.ok(s.paths.every(([,el])=>el.dataset.semantic==='reference'),'reuse native visual semantics rather than promoting source/candidate edges');
 assert.equal(s.visuals.size,2);assert.equal(f.visualCalls.length,2);
 assert.ok(f.visualCalls.every(call=>call.context===f.visualContext));
 assert.equal(f.controls.inert,true);assert.equal(f.alreadyInert.inert,true);assert.equal(f.host.hidden,false);
 await c.openMemberNetwork();assert.equal(f.layoutCalls(),1,'opening an already open session must not recalculate layout');
 assert.equal(f.engineCalls.length,1);assert.equal(f.engineCalls[0][0],f.graph);assert.equal(f.engineCalls[0][3],s.positions);assert.equal(f.engineCalls[0][4],s.visuals);f.assertNative();
});
test('missing embedded library fails via actual loader before native inert mutation and releases opening guard with a user message',async()=>{
 const f=fixture(),c=f.context,dataset={...f.root.dataset};
 for(const el of f.root.children){const original=el.inert;Object.defineProperty(el,'inert',{get:()=>original,set:()=>assert.fail('loader failure must not touch inert state')});}
 c.window={};vm.runInNewContext(functionSource(engineSource,'memberLoadNetworkEngine'),c);
 await assert.doesNotReject(()=>c.openMemberNetwork());
 assert.equal(f.live.textContent,'관계망 도구를 불러오지 못했어요. 원래 작업판은 그대로예요.');
 assert.equal(c.memberNetworkSession,null);assert.equal(c.memberNetworkOpening,false);assert.equal(f.button.disabled,false);
 assert.equal(f.host.hidden,true);assert.deepEqual(f.root.dataset,dataset);assert.equal(f.layoutCalls(),0);assert.equal(f.engineCalls.length,0);
 assert.equal(f.observer.observed.length,0);assert.equal(f.button.focusCalls.length,0);f.assertNative();
});
test('pending loader rejection after reset/root removal/missing live is harmless and never mutates native state',async()=>{
 for(const boundary of ['reset','removed','null-live','all']){
  const f=fixture(),c=f.context,children=f.root.children.slice(),dataset={...f.root.dataset};let reject;
  f.live.textContent='existing notice';
  for(const el of children){const original=el.inert;Object.defineProperty(el,'inert',{get:()=>original,set:()=>assert.fail('late loader failure must not touch inert state: '+boundary)});}
  c.memberLoadNetworkEngine=()=>new Promise((_,fail)=>{reject=fail;});
  const pending=c.openMemberNetwork();assert.equal(c.memberNetworkOpening,true);assert.equal(f.button.disabled,true);
  if(boundary==='reset'||boundary==='all')c.memberReset=true;
  if(boundary==='removed'||boundary==='all')f.root.isConnected=false;
  if(boundary==='null-live'||boundary==='all')f.root.querySelector=()=>null;
  reject(new Error('late loader rejection fixture'));await assert.doesNotReject(()=>pending,boundary);
  assert.equal(f.live.textContent,'existing notice');assert.equal(c.memberNetworkSession,null);assert.equal(c.memberNetworkOpening,false);assert.equal(f.button.disabled,false);
  assert.deepEqual(f.root.children,children);assert.deepEqual(f.root.dataset,dataset);assert.equal(f.host.hidden,true);
  assert.equal(f.layoutCalls(),0);assert.equal(f.engineCalls.length,0);assert.equal(f.visualCalls.length,0);
  assert.equal(f.nodes.children.length,0);assert.equal(f.graph.children.length,0);assert.equal(f.svg.children.length,0);
  assert.equal(f.observer.observed.length,0);assert.equal(f.button.focusCalls.length,0);f.assertNative();
 }
});
test('engine init failure restores original native inert/session state, clears temporary nodes and reports a user message',async()=>{
 const f=fixture(),c=f.context,children=f.root.children.slice(),inert=children.map(el=>el.inert),dataset={...f.root.dataset};
 c.memberCreateNetworkEngine=()=>{throw new Error('renderer unavailable fixture');};
 await assert.doesNotReject(()=>c.openMemberNetwork());
 assert.equal(f.live.textContent,'관계망을 표시하지 못했어요. 원래 작업판은 그대로예요.');
 assert.equal(c.memberNetworkSession,null);assert.equal(c.memberNetworkOpening,false);assert.equal(f.button.disabled,false);assert.equal(f.host.hidden,true);
 assert.deepEqual(f.root.children,children);assert.deepEqual(children.map(el=>el.inert),inert);assert.deepEqual(f.root.dataset,dataset);
 assert.equal(f.nodes.children.length,0);assert.equal(f.svg.children.length,0);assert.equal(f.button.attributes['aria-expanded'],'false');
 assert.equal(f.observer.observed.length,0);f.assertNative();
});
test('concurrent entry loads once and snapshots current scope only after loader resolves',async()=>{
 const f=fixture(),c=f.context;let resolve,loads=0;
 c.memberLoadNetworkEngine=()=>{loads++;return new Promise(done=>{resolve=done;});};
 const first=c.openMemberNetwork();assert.equal(c.memberNetworkOpening,true);assert.equal(f.controls.inert,false);assert.equal(f.button.disabled,true);
 await c.openMemberNetwork();assert.equal(loads,1);assert.equal(f.layoutCalls(),0);
 c.memberScope=()=>({stocks:[f.stock],records:[f.record]});resolve();await first;
 assert.equal(c.memberNetworkSession.elements.size,2);assert.equal(c.memberNetworkSession.elements.has('candidate'),false);
 assert.equal(f.engineCalls.length,1);assert.equal(f.layoutCalls(),1);assert.equal(f.button.disabled,false);c.closeMemberNetwork();f.assertNative();
});
test('vendor viewport/select/highlight callbacks update exploration only and late viewport cannot resurrect a session',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,hooks=f.engineCalls[0][5],before=clone([...s.positions]);
 hooks.viewport({zoom:.4,panX:21,panY:-11});assert.deepEqual({...s.camera},{zoom:.4,panX:21,panY:-11});assert.equal(f.engineState.stage,'names');
 hooks.select('source');assert.equal(s.selected,'source');hooks.highlight('stock');assert.equal(f.engineState.highlights.at(-1),'source');
 assert.deepEqual(clone([...s.positions]),before);assert.equal(f.layoutCalls(),1);c.closeMemberNetwork();
 hooks.viewport({zoom:2,panX:99,panY:99});assert.equal(c.memberNetworkSession,null);assert.equal(f.host.hidden,true);f.assertNative();
 await c.openMemberNetwork();const next=c.memberNetworkSession,selected=next.selected,highlights=f.engineState.highlights.length;
 hooks.select('source');hooks.highlight('source');hooks.viewport({zoom:2,panX:99,panY:99});
 assert.equal(c.memberNetworkSession,next);assert.equal(next.selected,selected);assert.equal(f.engineState.highlights.length,highlights);
 c.closeMemberNetwork();f.assertNative();
});
test('HTML click and vendor select-other/reselect preserve network camera, world/card centers and native drafts',async()=>{
 for(const zoom of [.4,1.2])for(const path of ['html-click','vendor-hook']){
  const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
  s.camera={zoom,panX:83,panY:-47};c.drawMemberNetwork();
  const camera=clone(s.camera),positions=clone([...s.positions]),items=clone([...s.byId]),elements=[...s.elements.values()],paths=s.paths.map(([,el])=>el);
  const centers=()=>[...s.elements].map(([id,el])=>[id,el.style.left,el.style.top,el.style.transform,el.hidden]);
  const before=centers(),engineCamera={...f.engineState.camera},stage=f.engineState.stage,visualCalls=f.visualCalls.length;
  assert.equal(stage,zoom<.8?'names':'cards');
  c.fitMemberNetwork=()=>assert.fail('selection must not fit/recenter the network');
  c.memberNetworkLayout=()=>assert.fail('selection must not rerun network layout');
  for(const position of s.positions.values())freeze(position);
  for(const method of ['set','delete','clear'])Object.defineProperty(s.positions,method,{value:()=>assert.fail('selection must not change world positions')});
  const select=f.engineCalls[0][5].select;
  for(const [id,expected]of [['stock','stock'],['source','source'],['stock','stock'],['stock','']]){
   if(path==='html-click')s.elements.get(id).onclick();else select(id);
   assert.equal(s.selected,expected);assert.equal(f.inspector.children[0].textContent,expected?s.byId.get(expected).name:'연결을 선택해 보세요');
   assert.deepEqual(clone(s.camera),camera);assert.deepEqual(clone([...s.positions]),positions);assert.deepEqual(centers(),before);
   assert.deepEqual([...s.elements.values()],elements);assert.deepEqual(s.paths.map(([,el])=>el),paths);assert.deepEqual(clone([...s.byId]),items);
   assert.deepEqual(f.engineState.camera,engineCamera);assert.equal(f.engineState.stage,stage);assert.equal(f.layoutCalls(),1);
   assert.equal(f.engineCalls.length,1);assert.equal(f.visualCalls.length,visualCalls);f.assertNative();
  }
  c.closeMemberNetwork();f.assertNative();
 }
});
test('shared wheel capture covers engine canvas and sibling HTML cards without a focus prerequisite',()=>{
 const listener=source.match(/memberNetworkSpace\.addEventListener\(['"]wheel['"],\s*memberNetworkWheel,\s*\{([^}]+)\}/);
 assert.ok(listener,'wheel must be owned by the common ancestor, not only the vendor canvas');
 assert.match(listener[1],/capture\s*:\s*true/);assert.match(listener[1],/passive\s*:\s*false/);
});
test('geometry failure reports a user message before changing native inert state or creating a session',async()=>{
 const f=fixture(),c=f.context,children=f.root.children.slice(),dataset={...f.root.dataset};
 const inertBefore=children.map(el=>el.inert);
 for(const el of children){const original=el.inert;Object.defineProperty(el,'inert',{get:()=>original,set:()=>assert.fail('geometry failure must not touch native inert state')});}
 c.memberNetworkLayout=()=>{throw new Error('geometry failure fixture');};
 await assert.doesNotReject(()=>c.openMemberNetwork());
 assert.equal(f.live.textContent,'관계망을 만들지 못했어요. 원래 작업판은 그대로예요.');
 assert.equal(c.memberNetworkSession,null);assert.equal(f.host.hidden,true);
 assert.deepEqual(f.root.children,children);assert.deepEqual(f.root.dataset,dataset);
 assert.deepEqual(children.map(el=>el.inert),inertBefore);
 assert.equal(f.button.attributes['aria-expanded'],undefined);assert.equal(f.button.focusCalls.length,0);
 assert.equal(f.nodes.children.length,0);assert.equal(f.svg.children.length,0);
 assert.equal(f.observer.observed.length,0);assert.equal(f.visualCalls.length,0);f.assertNative();
});
test('draw/zoom/pan/resize/fit preserve every world position, raw value and path/node identity without calling layout again',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,positions=clone([...s.positions]),elements=[...s.elements.values()],paths=s.paths.map(([,el])=>el);
 for(const p of s.positions.values())freeze(p);
 for(const key of ['set','delete','clear'])Object.defineProperty(s.positions,key,{value:()=>assert.fail('session world position mutation')});
 const center=id=>{const el=s.elements.get(id);return{x:parseFloat(el.style.left),y:parseFloat(el.style.top)};};
 for(const zoom of [.1,.28,.7,.8,1.6]){
  c.zoomMemberNetwork(zoom);c.drawMemberNetwork();
  assert.equal(f.space.dataset.stage,c.memberNetworkStage(zoom));
  assert.equal(f.engineState.stage,c.memberNetworkStage(zoom));assert.deepEqual(f.engineState.camera,{...s.camera});
  assert.equal(f.engineState.stageZoom,zoom,'runtime passes current camera zoom for constant rendered sizes');
  for(const [id,p]of s.positions){const el=s.elements.get(id),a=center(id),r=f.space.getBoundingClientRect();
   assert.ok(Math.abs(a.x-(r.width/2+(p.x-500)*zoom+s.camera.panX))<1e-9);
   assert.ok(Math.abs(a.y-(r.height/2+(p.y-340)*zoom+s.camera.panY))<1e-9);
   assert.equal(el.style.transform,'translate(-50%,-50%)'+(zoom>=.8?' scale('+zoom+')':''));
  }
 }
 const before=center('source');s.camera.panX+=35;s.camera.panY-=19;c.drawMemberNetwork();const after=center('source');
 assert.ok(Math.abs(after.x-before.x-35)<1e-9);assert.ok(Math.abs(after.y-before.y+19)<1e-9);
 f.space.rect={width:390,height:844,left:0,top:0};c.drawMemberNetwork();c.fitMemberNetwork();c.fitMemberNetwork();
 assert.deepEqual(clone([...s.positions]),positions);assert.deepEqual([...s.elements.values()],elements);assert.deepEqual(s.paths.map(([,el])=>el),paths);
 assert.equal(f.layoutCalls(),1);f.assertNative();
});
test('network background reuses the native themed grid behind the graph, without intercepting gestures',()=>{
 const rule=source.match(/#an-map-design \.an-network-space>\.an-network-grid\{([^}]+)\}/)[1];
 for(const declaration of ['pointer-events:none','stroke:light-dark(var(--an-grid),var(--an-divider))','stroke-width:1','shape-rendering:crispEdges'])assert.ok(rule.includes(declaration));
 const markup=source.match(/memberNetworkHost\.innerHTML='([^']+)';/)[1];
 assert.ok(markup.indexOf('class="an-network-grid"')<markup.indexOf('class="an-network-graph"'),'grid is behind the vendor canvas');
 assert.ok(markup.includes('<svg class="an-network-grid" aria-hidden="true">'));
});
test('native 24px grid tracks camera pan/zoom/resize with bounded low-zoom spacing and no layout/raw changes',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,before=clone([...s.positions]);
 const lines=()=>[f.gridFine,f.gridCoarse].flatMap(el=>[...el.attributes.d.matchAll(/M ([\d.]+) 0 V ([\d.]+)|M 0 ([\d.]+) H ([\d.]+)/g)].map(m=>m[1]?{axis:'x',value:+m[1],limit:+m[2]}:{axis:'y',value:+m[3],limit:+m[4]}));
 for(const zoom of [.02,.08,.2,.28,.649999,.65,1,2,4]){
  s.camera={zoom,panX:13,panY:-9};c.drawMemberNetwork();
  const r=f.space.getBoundingClientRect(),all=lines();assert.ok(all.length>0&&all.length<2*(r.width+r.height)/8+4);
  for(const line of all){const origin=(line.axis==='x'?r.width:r.height)/2+(line.axis==='x'?13:-9);
   const world=(line.value-.5-origin)/zoom,multiple=Math.round(world/24);
   assert.ok(Math.abs(world-multiple*24)*zoom<=.500001,'line stays on native world lattice within pixel snapping');}
  for(const el of [f.gridFine,f.gridCoarse])assert.ok(+el.style.opacity>=0&&+el.style.opacity<=1);
 }
 s.camera={zoom:1,panX:0,panY:0};c.drawMemberNetwork();const baseline=lines().filter(n=>n.axis==='x').map(n=>n.value);
 assert.ok(baseline.includes(450.5)&&baseline.includes(474.5),'native 24px spacing at reference zoom');
 s.camera.panX=7;c.drawMemberNetwork();const moved=lines().filter(n=>n.axis==='x').map(n=>n.value);
 for(const x of baseline.filter(x=>x+7<900))assert.ok(moved.includes(x+7),'grid translates with camera, not viewport-fixed');
 f.space.rect={width:390,height:844,left:0,top:0};c.drawMemberNetwork();assert.ok(lines().some(n=>n.axis==='x'&&n.value===202.5));
 c.fitMemberNetwork();assert.deepEqual(clone([...s.positions]),before);assert.equal(f.layoutCalls(),1);f.assertNative();
});
test('zoom preserves the cursor world point, clamps camera bounds, and fit remains finite without changing geometry',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,r=f.space.getBoundingClientRect(),at={x:131,y:227};
 const world=()=>({x:500+(at.x-r.width/2-s.camera.panX)/s.camera.zoom,y:340+(at.y-r.height/2-s.camera.panY)/s.camera.zoom});
 const before=world();c.zoomMemberNetwork(.6,at);const after=world();
 assert.ok(Math.abs(before.x-after.x)<1e-9&&Math.abs(before.y-after.y)<1e-9);
 c.zoomMemberNetwork(100);assert.equal(s.camera.zoom,4);c.zoomMemberNetwork(.00001);assert.equal(s.camera.zoom,.02);
 c.fitMemberNetwork();assert.ok(Object.values(s.camera).every(Number.isFinite));assert.equal(f.layoutCalls(),1);f.assertNative();
});
test('close destroys vendor engine, restores only connected native inert states and keeps native camera/notes/coordinates/history unchanged',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();
 f.graph.append(element('canvas'));assert.equal(f.graph.children.length,1);
 c.memberNetworkSelect('source');c.zoomMemberNetwork(.5);c.closeMemberNetwork();
 assert.equal(f.engineState.destroys,1);assert.equal(c.memberNetworkSession,null);assert.equal(f.host.hidden,true);assert.equal(f.root.dataset.networkOpen,undefined);
 assert.equal(f.controls.inert,false);assert.equal(f.alreadyInert.inert,true);assert.equal(f.root.dataset.other,'kept');
 assert.equal(f.nodes.children.length,0);assert.equal(f.svg.children.length,0);assert.equal(f.observer.disconnects,1);
 assert.equal(f.graph.children.length,0);
 assert.equal(f.button.attributes['aria-expanded'],'false');assert.equal(f.button.focusCalls.length,1);
 c.closeMemberNetwork();assert.equal(f.observer.disconnects,1,'second close is inert');assert.equal(f.engineState.destroys,1);f.assertNative();
});
test('close never refocuses/reinserts removed controls or mutates a node moved outside the native root',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();
 f.controls.isConnected=false;f.button.isConnected=false;f.root.children=f.root.children.filter(el=>el!==f.controls&&el!==f.alreadyInert);
 // A still-connected element moved elsewhere must not be mutated by restoration.
 f.alreadyInert.inert=false;const remaining=f.root.children.slice();
 c.closeMemberNetwork();assert.equal(f.controls.inert,true);assert.equal(f.alreadyInert.inert,false);
 assert.equal(f.button.focusCalls.length,0);assert.deepEqual(f.root.children,remaining);assert.ok(!f.root.children.includes(f.controls));f.assertNative();
});
test('empty scope and closed draw/zoom/fit calls are harmless and never fabricate nodes',async()=>{
 const f=fixture(),c=f.context;c.memberScope=()=>({stocks:[],records:[]});
 c.drawMemberNetwork();c.zoomMemberNetwork(.2);c.fitMemberNetwork();assert.equal(f.layoutCalls(),0);
 await c.openMemberNetwork();assert.equal(c.memberNetworkSession.elements.size,0);assert.equal(c.memberNetworkSession.positions.size,0);
 c.fitMemberNetwork();c.closeMemberNetwork();f.assertNative();
});
for(const [index,kind]of ['direct','indirect','history','review','reference'].entries())test(`native ${kind} visual is copied unchanged into path styling and inspector, not recomputed`,async()=>{
 const f=fixture(),c=f.context;
 const visual=freeze({kind,topic:'native-topic-'+kind,color:['#123456','#234567','#345678','#456789','#56789a'][index],
  width:1.25+index*.5,dash:kind==='direct'?'':'3 '+(index+2),statusLabel:'native-status-'+kind,
  summaryLabel:'native-summary-'+kind,lineLabel:'native-line-'+kind,extraNativeField:'preserve-'+kind});
 const before=clone(visual),calls=[];
 c.memberEdgeVisual=(edge,record,context)=>{calls.push({edge,record,context});return visual;};
 await c.openMemberNetwork();const s=c.memberNetworkSession;
 assert.equal(calls.length,2);
 for(const [edge,el]of s.paths){
  const saved=s.visuals.get(edge.id);assert.notEqual(saved,visual,'snapshot must not retain helper return object identity');
  assert.deepEqual(clone(saved),before);assert.equal(el.dataset.semantic,kind);assert.equal(el.dataset.topic,visual.topic);
  assert.equal(el.style.stroke,visual.color);assert.equal(el.style.strokeWidth,visual.width+'px');assert.equal(el.style.strokeDasharray,visual.dash);
  for(const label of [visual.statusLabel,visual.summaryLabel,visual.lineLabel])assert.ok(el.attributes['aria-label'].includes(label));
 }
 assert.equal(calls[0].record.id,'source');assert.equal(calls[1].record.id,'candidate');
 assert.ok(calls.every(call=>call.context===f.visualContext));
 const snapshots=[...s.visuals.values()];
 c.memberEdgeVisual=()=>assert.fail('inspector/camera must consume captured visual, not reinterpret it');
 c.memberVisualContext=()=>assert.fail('no fresh native context needed after entry');
 c.memberNetworkSelect('source');
 const lines=f.inspector.children.map(el=>el.textContent||'');
 assert.ok(lines.some(line=>[visual.statusLabel,visual.summaryLabel,visual.lineLabel].every(label=>line.includes(label))), 'inspector must reuse all three stored native labels');
 c.zoomMemberNetwork(.4);c.fitMemberNetwork();c.drawMemberNetwork();
 assert.deepEqual([...s.visuals.values()],snapshots);assert.deepEqual(clone(visual),before);
 assert.equal(s.byId.get('candidate').layer,'candidates');assert.equal(c.memberNetworkKind(s.byId.get('candidate')),'candidate');
 c.closeMemberNetwork();f.assertNative();
});
test('embedded network modules match their canonical source verbatim',()=>{
 const canvas=fs.readFileSync(process.env.MEMBER_MAP_CANVAS||path.join(__dirname,'../vercel-api/public/member-map-canvas.html'),'utf8');
 assert.ok(canvas.includes(geometry.trimEnd()),'geometry not yet emitted or mismatched');
 const engine=fs.readFileSync(path.join(directory,'prototype-network-engine.js'),'utf8');
 assert.ok(canvas.includes(engine.trimEnd()),'engine not yet emitted or mismatched');
 assert.ok(canvas.includes(source.trimEnd()),'runtime not yet emitted or mismatched');
});
test('search/type/local-depth filters change only the visible induced graph, not world positions or camera',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
 const before=clone([...s.positions]),camera=clone(s.camera),calls=[];s.engine.setVisible=ids=>calls.push([...ids]);
 s.options.query='Original';c.memberNetworkFilter();assert.deepEqual([...s.visible],['source']);assert.equal(s.visibleLinks.length,0);
 assert.equal(s.elements.get('stock').hidden,true);assert.equal(s.elements.get('stock').tabIndex,-1);
 s.options.query='';s.options.kinds=['stock','candidate'];c.memberNetworkFilter();assert.deepEqual([...s.visible].sort(),['candidate','stock']);assert.equal(s.visibleLinks.length,1);
 s.options.kinds=['stock','source','candidate'];s.options.anchor='source';s.options.depth=1;c.memberNetworkFilter();assert.deepEqual([...s.visible].sort(),['source','stock']);
 s.options.depth=2;c.memberNetworkFilter();assert.equal(s.visible.size,3);
 s.options.query='no-such-match';c.memberNetworkFilter();assert.equal(s.visible.size,0);c.fitMemberNetwork();assert.ok(f.hostParts.get('footer').textContent.includes('표시 0/3'));
 assert.equal(calls.length,5);assert.deepEqual(clone([...s.positions]),before);assert.deepEqual(clone(s.camera),camera);assert.equal(f.layoutCalls(),1);f.assertNative();
});
test('unlocked exploration move pins one node and survives view return without editing native draft',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,hooks=f.engineCalls[0][5],before=clone([...s.positions]);
 hooks.move('stock',{x:123,y:456});assert.deepEqual(clone([...s.positions]),before,'locked');
 s.draggable=true;hooks.move('stock',{x:123,y:456});assert.deepEqual({...s.positions.get('stock')},{x:123,y:456});assert.deepEqual({...s.pinned.get('stock')},{x:123,y:456});
 hooks.move('stock',{x:NaN,y:1});assert.deepEqual({...s.positions.get('stock')},{x:123,y:456});
 for(const [id,p]of before)if(id!=='stock')assert.deepEqual({...s.positions.get(id)},p);
 c.closeMemberNetwork();await c.openMemberNetwork();assert.deepEqual({...c.memberNetworkSession.positions.get('stock')},{x:123,y:456});assert.equal(c.memberNetworkSession.draggable,false);f.assertNative();
});
test('explicit layout adjustment honors pinned point, updates engine positions, and leaves camera alone',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,camera=clone(s.camera),updates=[];
 s.draggable=true;c.memberNetworkMove('stock',{x:700,y:100});s.engine.setPositions=ps=>updates.push([...ps]);
 s.options.linkDistance=300;s.options.repulsion=2;c.memberNetworkArrange();
 assert.equal(f.layoutCalls(),2);assert.equal(updates.length,1);assert.deepEqual({...s.positions.get('stock')},{x:700,y:100});assert.deepEqual(clone(s.camera),camera);f.assertNative();
});
test('card pointer drag prevents selection and writes exploration only',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,b=s.elements.get('source'),p={...s.positions.get('source')};
 const moved=[];s.engine.setPositions=ps=>moved.push([...ps]);s.draggable=true;s.camera.zoom=2;
 b.setPointerCapture=()=>{};b.hasPointerCapture=()=>true;b.releasePointerCapture=()=>{};
 const event=(x,y)=>({button:0,pointerId:1,clientX:x,clientY:y,stopPropagation(){}});
 b.onpointerdown(event(10,10));b.onpointermove(event(50,30));b.onpointerup(event(50,30));b.onclick();
 assert.equal(s.selected,'');assert.deepEqual({...s.positions.get('source')},{x:p.x+20,y:p.y+10});assert.equal(moved.length,1);assert.equal(s.pinned.has('source'),true);f.assertNative();
 b.onclick();assert.equal(s.selected,'source');
});
test('display threshold only changes stage, and editable controls bypass graph shortcuts',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,before=clone([...s.positions]);
 s.options.labelThreshold=.6;c.zoomMemberNetwork(.4);assert.equal(f.space.dataset.stage,'dots');c.zoomMemberNetwork(.7);assert.equal(f.space.dataset.stage,'names');
 assert.deepEqual(clone([...s.positions]),before);assert.match(source,/\['INPUT','SELECT','TEXTAREA','BUTTON','SUMMARY'\]\.includes\(e\.target\.tagName\)/);f.assertNative();
});

// Input tests call the delivered handlers directly. They need no browser focus,
// DOM event dispatcher, member account, network, or duplicated input algorithm.
function inputEvent(f,values={}){
 const counts={prevented:0,stopped:0};
 const target=values.target||f.graph;
 if(!target.closest)target.closest=selector=>selector.includes('.an-network-node')&&target.dataset?.networkNode?target:null;
 return{type:'wheel',deltaX:0,deltaY:0,deltaMode:0,ctrlKey:false,metaKey:false,shiftKey:false,
  pointerId:1,pointerType:'mouse',button:0,clientX:150,clientY:200,target,currentTarget:f.space,
  preventDefault(){counts.prevented++;},stopPropagation(){counts.stopped++;},...values,counts};
}
function worldAt(f,camera,x,y){const r=f.space.getBoundingClientRect();return{x:500+(x-r.left-r.width/2-camera.panX)/camera.zoom,y:340+(y-r.top-r.height/2-camera.panY)/camera.zoom};}
function nearPoint(actual,expected){for(const key of ['x','y'])assert.ok(Math.abs(actual[key]-expected[key])<1e-8,`${key}: ${actual[key]} != ${expected[key]}`);}

test('first plain wheel pans without click/focus, normalizes all delta modes and Shift, including HTML cards',async()=>{
 for(const zoom of [.4,1.2])for(const [deltaMode,unit]of [[0,1],[1,16],[2,600]])for(const [dx,dy,shift]of [[7,11,false],[0,11,true],[7,11,true]]){
  const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
  s.camera={zoom,panX:83,panY:-47};const before=clone([...s.positions]);
  const e=inputEvent(f,{deltaX:dx,deltaY:dy,deltaMode,shiftKey:shift,target:zoom<.8?f.graph:s.elements.get('source')});
  assert.equal(c.document.activeElement,undefined);c.memberNetworkWheel(e);
  assert.deepEqual({...s.camera},{zoom,panX:83-(shift&&!dx?dy:dx)*unit,panY:-47-(shift&&!dx?0:dy)*unit});
  assert.equal(e.counts.prevented,1);assert.equal(e.counts.stopped,1);
  assert.deepEqual(clone([...s.positions]),before);assert.equal(s.selected,'');assert.equal(f.layoutCalls(),1);f.assertNative();c.closeMemberNetwork();
 }
});

test('Ctrl/Meta wheel matches core exponential zoom and clamp while preserving the cursor world anchor',async()=>{
 for(const modifier of ['ctrlKey','metaKey'])for(const [deltaMode,raw,unit]of [[0,12,1],[0,-12,1],[1,20,16],[2,-1,600]]){
  const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
  f.space.rect={left:37,top:19,width:900,height:600};s.camera={zoom:.6,panX:83,panY:-47};
  const x=168,y=246,before=worldAt(f,s.camera,x,y),positions=clone([...s.positions]);
  const e=inputEvent(f,{[modifier]:true,deltaMode,deltaY:raw,clientX:x,clientY:y,target:s.elements.get('source')});
  c.memberNetworkWheel(e);
  const delta=Math.max(-120,Math.min(120,raw*unit)),expected=Math.max(.02,Math.min(4,.6*Math.exp(-delta*(modifier==='ctrlKey'?.012:.003))));
  assert.ok(Math.abs(s.camera.zoom-expected)<1e-10);nearPoint(worldAt(f,s.camera,x,y),before);
  assert.equal(e.counts.prevented,1);assert.equal(e.counts.stopped,1);assert.deepEqual(clone([...s.positions]),positions);
  assert.equal(s.selected,'');assert.equal(f.layoutCalls(),1);f.assertNative();c.closeMemberNetwork();
 }
});

test('wheel is consumed but cannot change camera during an owned pointer, node drag, or Safari gesture',async()=>{
 for(const active of ['pointer','drag','gesture']){
  const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,input=c.memberNetworkInput(s),before=clone(s.camera),positions=clone([...s.positions]);
  if(active==='pointer')input.points.set(7,{x:10,y:20});
  if(active==='drag')input.drag={mode:'pan',moved:true};
  if(active==='gesture')input.gesture={zoom:s.camera.zoom,scale:1,x:10,y:20};
  for(const ctrlKey of [false,true]){const e=inputEvent(f,{deltaY:20,ctrlKey});c.memberNetworkWheel(e);assert.equal(e.counts.prevented,1);assert.equal(e.counts.stopped,1);}
  assert.deepEqual(clone(s.camera),before);assert.deepEqual(clone([...s.positions]),positions);f.assertNative();c.closeMemberNetwork();
 }
});

test('Safari gesture zoom works on first gesture, uses initial scale and cursor anchor, and ends cleanly',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
 f.space.rect={left:37,top:19,width:900,height:600};s.camera={zoom:.6,panX:83,panY:-47};
 const x=168,y=246,anchor=worldAt(f,s.camera,x,y),positions=clone([...s.positions]);
 const start=inputEvent(f,{type:'gesturestart',scale:2,clientX:x,clientY:y});c.memberNetworkGestureStart(start);
 assert.equal(c.document.activeElement,undefined);
 for(const scale of [3,1]){const e=inputEvent(f,{type:'gesturechange',scale,clientX:x+50,clientY:y+50});c.memberNetworkGestureChange(e);
  assert.ok(Math.abs(s.camera.zoom-.6*scale/2)<1e-10);nearPoint(worldAt(f,s.camera,x,y),anchor);
  assert.equal(e.counts.prevented,1);assert.equal(e.counts.stopped,1);}
 const end=inputEvent(f,{type:'gestureend'});c.memberNetworkGestureEnd(end);assert.equal(s.input.gesture,null);
 const before=clone(s.camera);c.memberNetworkGestureChange(inputEvent(f,{type:'gesturechange',scale:9}));assert.deepEqual(clone(s.camera),before);
 c.memberNetworkWheel(inputEvent(f,{deltaY:5}));assert.equal(s.camera.panY,before.panY-5);
 assert.deepEqual(clone([...s.positions]),positions);assert.equal(s.selected,'');assert.equal(f.layoutCalls(),1);f.assertNative();c.closeMemberNetwork();
});

test('Safari gesture cannot double-apply an active pointer pinch, and closed input calls are inert',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,input=c.memberNetworkInput(s),before=clone(s.camera);
 input.points.set(1,{x:100,y:100});input.points.set(2,{x:200,y:100});
 c.memberNetworkGestureStart(inputEvent(f,{type:'gesturestart',scale:1}));c.memberNetworkGestureChange(inputEvent(f,{type:'gesturechange',scale:2}));
 assert.equal(input.gesture,null);assert.deepEqual(clone(s.camera),before);f.assertNative();c.closeMemberNetwork();
 for(const name of ['memberNetworkWheel','memberNetworkGestureStart','memberNetworkGestureChange','memberNetworkGestureEnd'])assert.doesNotThrow(()=>c[name](inputEvent(f,{scale:2})));
 f.assertNative();
});

test('Space, middle button and locked overlay card pan immediately without selecting or changing geometry',async()=>{
 for(const path of ['space','middle','locked-card']){
  const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,positions=clone([...s.positions]);
  s.camera={zoom:1.2,panX:83,panY:-47};if(path==='space')c.memberNetworkInput(s).space=true;
  const target=path==='locked-card'||path==='space'?s.elements.get('source'):f.graph;
  const down=inputEvent(f,{type:'pointerdown',target,clientX:100,clientY:150,button:path==='middle'?1:0});
  c.memberNetworkPointerDown(down);
  c.memberNetworkPointerMove(inputEvent(f,{type:'pointermove',target,clientX:130,clientY:138}));
  assert.deepEqual({...s.camera},{zoom:1.2,panX:113,panY:-59});
  c.memberNetworkPointerEnd(inputEvent(f,{type:'pointerup',target,clientX:130,clientY:138}));
  assert.equal(s.input.points.size,0);assert.equal(s.input.drag,null);assert.equal(f.space.hasPointerCapture(1),false);
  f.engineCalls[0][5].select('source');assert.equal(s.selected,'','a moved pan cannot leak a vendor tap');
  assert.deepEqual(clone([...s.positions]),positions);assert.equal(s.pinned.size,0);assert.equal(f.layoutCalls(),1);f.assertNative();c.closeMemberNetwork();
 }
});

test('normal mouse canvas background is not captured by the custom adapter',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,before=clone(s.camera);
 const down=inputEvent(f,{type:'pointerdown'});c.memberNetworkPointerDown(down);
 assert.equal(down.counts.prevented,0);assert.equal(down.counts.stopped,0);assert.equal(s.input.points.size,0);assert.equal(s.input.drag,null);
 assert.deepEqual(clone(s.camera),before);f.assertNative();c.closeMemberNetwork();
});

test('a new ordinary mouse pointerdown clears release ghost suppression before the next engine selection',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,input=c.memberNetworkInput(s),hooks=f.engineCalls[0][5];
 const camera=clone(s.camera),positions=clone([...s.positions]);input.suppressUntil=Date.now()+300;
 hooks.select('source');assert.equal(s.selected,'','release ghost remains suppressed before a new pointerdown');
 const down=inputEvent(f,{type:'pointerdown',pointerType:'mouse',target:f.graph});c.memberNetworkPointerDown(down);
 assert.equal(input.suppressUntil,0);assert.equal(input.points.size,0);assert.equal(input.drag,null);
 assert.equal(down.counts.prevented,0);assert.equal(down.counts.stopped,0);
 hooks.select('source');assert.equal(s.selected,'source','the next genuine click is not swallowed');
 assert.deepEqual(clone(s.camera),camera);assert.deepEqual(clone([...s.positions]),positions);f.assertNative();c.closeMemberNetwork();
});

test('one-finger touch starts pan on its first pointer without click/focus or native-node movement',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,positions=clone([...s.positions]);
 s.camera={zoom:.6,panX:83,panY:-47};
 const down=inputEvent(f,{type:'pointerdown',pointerType:'touch',clientX:20,clientY:20});c.memberNetworkPointerDown(down);
 assert.equal(c.document.activeElement,undefined);assert.equal(down.counts.prevented,1);assert.equal(down.counts.stopped,1);
 c.memberNetworkPointerMove(inputEvent(f,{type:'pointermove',pointerType:'touch',clientX:50,clientY:5}));
 assert.deepEqual({...s.camera},{zoom:.6,panX:113,panY:-62});
 c.memberNetworkPointerEnd(inputEvent(f,{type:'pointerup',pointerType:'touch',clientX:50,clientY:5}));
 assert.equal(s.input.points.size,0);assert.equal(s.selected,'');assert.deepEqual(clone([...s.positions]),positions);f.assertNative();c.closeMemberNetwork();
});

test('touch pinch scales and translates around its midpoint, then reanchors remaining finger without a jump',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,positions=clone([...s.positions]);
 f.space.rect={left:37,top:19,width:900,height:600};s.camera={zoom:.6,panX:83,panY:-47};
 const event=(type,pointerId,x,y)=>inputEvent(f,{type,pointerType:'touch',pointerId,clientX:x,clientY:y});
 c.memberNetworkPointerDown(event('pointerdown',7,100,100));c.memberNetworkPointerDown(event('pointerdown',3,200,100));
 const world=worldAt(f,s.camera,150,100);
 c.memberNetworkPointerMove(event('pointermove',7,90,120));c.memberNetworkPointerMove(event('pointermove',3,230,140));
 assert.ok(Math.abs(s.camera.zoom-.6*Math.hypot(140,20)/100)<1e-10);nearPoint(worldAt(f,s.camera,160,130),world);
 c.memberNetworkPointerEnd(event('pointerup',3,230,140));const remaining=clone(s.camera);
 c.memberNetworkPointerMove(event('pointermove',7,110,135));
 assert.deepEqual({...s.camera},{zoom:remaining.zoom,panX:remaining.panX+20,panY:remaining.panY+15});
 c.memberNetworkPointerEnd(event('pointerup',7,110,135));assert.equal(s.input.drag,null);assert.equal(s.input.points.size,0);
 f.engineCalls[0][5].select('source');assert.equal(s.selected,'');assert.equal(f.space.hasPointerCapture(3),false);assert.equal(f.space.hasPointerCapture(7),false);
 assert.deepEqual(clone([...s.positions]),positions);assert.equal(f.layoutCalls(),1);f.assertNative();c.closeMemberNetwork();
});

test('three-to-two touch release or cancellation restarts pinch, then one finger pans and zero ends without native changes',async()=>{
 for(const endType of ['pointerup','pointercancel','lostpointercapture'])for(const ended of [1,2,3]){
  const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
  f.space.rect={left:37,top:19,width:900,height:600};s.camera={zoom:.6,panX:83,panY:-47};
  s.pinned.set('source',{...s.positions.get('source')});c.memberNetworkSelect('stock');
  const positions=clone([...s.positions]),pins=clone([...s.pinned]),points=new Map([[1,{x:100,y:100}],[2,{x:200,y:100}],[3,{x:300,y:120}]]);
  const event=(type,id,p)=>inputEvent(f,{type,pointerType:'touch',pointerId:id,clientX:p.x,clientY:p.y});
  for(const [id,p]of points)c.memberNetworkPointerDown(event('pointerdown',id,p));
  points.set(2,{x:220,y:110});c.memberNetworkPointerMove(event('pointermove',2,points.get(2)));
  const camera=clone(s.camera);c.memberNetworkPointerEnd(event(endType,ended,points.get(ended)));points.delete(ended);
  const [[first,a],[second,b]]=[...points],mid={x:(a.x+b.x)/2,y:(a.y+b.y)/2},distance=Math.hypot(b.x-a.x,b.y-a.y);
  assert.equal(s.input.points.size,2);assert.equal(s.input.drag.mode,'pinch',endType+' ending '+ended);
  assert.equal(s.input.drag.distance,distance);assert.equal(s.input.drag.x,mid.x);assert.equal(s.input.drag.y,mid.y);
  assert.deepEqual(clone(s.input.drag.camera),camera);assert.deepEqual(clone(s.camera),camera,'release itself never jumps the camera');
  assert.equal(f.space.hasPointerCapture(ended),false);
  const anchor=worldAt(f,camera,mid.x,mid.y),moved={x:a.x-20,y:a.y+15};
  c.memberNetworkPointerMove(event('pointermove',first,moved));
  assert.ok(Object.values(s.camera).every(Number.isFinite),'remaining pinch must not produce NaN');
  assert.ok(Math.abs(s.camera.zoom-camera.zoom*Math.hypot(b.x-moved.x,b.y-moved.y)/distance)<1e-10);
  nearPoint(worldAt(f,s.camera,(moved.x+b.x)/2,(moved.y+b.y)/2),anchor);
  const pinched=clone(s.camera);c.memberNetworkPointerEnd(event('pointerup',second,b));
  assert.equal(s.input.points.size,1);assert.equal(s.input.drag.mode,'pan');assert.deepEqual(clone(s.camera),pinched);
  const panned={x:moved.x+17,y:moved.y-9};c.memberNetworkPointerMove(event('pointermove',first,panned));
  assert.deepEqual({...s.camera},{zoom:pinched.zoom,panX:pinched.panX+17,panY:pinched.panY-9});
  c.memberNetworkPointerEnd(event('pointerup',first,panned));
  assert.equal(s.input.points.size,0);assert.equal(s.input.drag,null);
  for(const id of [1,2,3])assert.equal(f.space.hasPointerCapture(id),false);
  f.engineCalls[0][5].select('source');assert.equal(s.selected,'stock','release cannot leak a selection');
  assert.deepEqual(clone([...s.positions]),positions);assert.deepEqual(clone([...s.pinned]),pins);assert.equal(f.layoutCalls(),1);
  f.assertNative();c.closeMemberNetwork();f.assertNative();
 }
});

test('touch hit-test selects the nearest visible point on first tap, with no second synthetic selection',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
 s.positions=new Map([['stock',{x:500,y:340}],['source',{x:900,y:340}],['candidate',{x:1300,y:340}]]);
 s.camera={zoom:1,panX:0,panY:0};const positions=clone([...s.positions]),camera=clone(s.camera);
 const event=type=>inputEvent(f,{type,pointerType:'touch',clientX:455,clientY:304});
 c.memberNetworkPointerDown(event('pointerdown'));c.memberNetworkPointerEnd(event('pointerup'));assert.equal(s.selected,'stock');
 f.engineCalls[0][5].select('stock');assert.equal(s.selected,'stock','compatibility tap must not toggle the first selection off');
 assert.equal(c.memberNetworkTouchHit(event('pointerdown'),s),'stock');s.visible.delete('stock');assert.equal(c.memberNetworkTouchHit(event('pointerdown'),s),'');
 assert.deepEqual(clone(s.camera),camera);assert.deepEqual(clone([...s.positions]),positions);f.assertNative();c.closeMemberNetwork();
});

test('unlocked touch moves one point only; pointercancel and capture loss restore its previous position and pin',async()=>{
 for(const endType of ['pointercancel','lostpointercapture'])for(const wasPinned of [false,true]){
  const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,id='source',card=s.elements.get(id);
  s.draggable=true;s.camera={zoom:2,panX:83,panY:-47};const original={...s.positions.get(id)},pin={x:original.x+2,y:original.y-3};
  if(wasPinned)s.pinned.set(id,pin);const before=clone([...s.positions]),camera=clone(s.camera),updates=[];s.engine.setPositions=ps=>updates.push(clone([...ps]));
  const event=(type,x,y)=>inputEvent(f,{type,pointerType:'touch',target:card,clientX:x,clientY:y});
  c.memberNetworkPointerDown(event('pointerdown',10,10));c.memberNetworkPointerMove(event('pointermove',50,30));
  assert.deepEqual({...s.positions.get(id)},{x:original.x+20,y:original.y+10});assert.equal(s.pinned.has(id),true);
  c.memberNetworkPointerEnd(event(endType,50,30));assert.deepEqual(clone([...s.positions]),before);assert.equal(s.pinned.has(id),wasPinned);
  if(wasPinned)assert.deepEqual({...s.pinned.get(id)},pin);
  assert.equal(updates.length,2);assert.deepEqual(clone(s.camera),camera);assert.equal(s.selected,'');f.assertNative();c.closeMemberNetwork();
 }
});

test('second touch restores an in-flight node drag before pinch takes ownership',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,id='source',card=s.elements.get(id),before=clone([...s.positions]);s.draggable=true;
 s.camera.zoom=1.2;c.drawMemberNetwork();
 const event=(type,pointerId,x,y)=>inputEvent(f,{type,pointerType:'touch',target:card,pointerId,clientX:x,clientY:y});
 c.memberNetworkPointerDown(event('pointerdown',1,10,10));c.memberNetworkPointerMove(event('pointermove',1,50,30));assert.equal(s.pinned.has(id),true);
 c.memberNetworkPointerDown(event('pointerdown',2,90,30));assert.deepEqual(clone([...s.positions]),before);assert.equal(s.pinned.has(id),false);
 assert.equal(s.input.drag.mode,'pinch');c.memberNetworkCancelInput();assert.equal(s.input.points.size,0);assert.equal(s.input.drag,null);assert.equal(s.input.space,false);
 f.assertNative();c.closeMemberNetwork();
});

test('close cancels an owned touch drag before caching and releases every pointer',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,id='source',card=s.elements.get(id),before=clone([...s.positions]);s.draggable=true;
 s.camera.zoom=1.2;c.drawMemberNetwork();
 c.memberNetworkPointerDown(inputEvent(f,{type:'pointerdown',pointerType:'touch',target:card,clientX:10,clientY:10}));
 c.memberNetworkPointerMove(inputEvent(f,{type:'pointermove',pointerType:'touch',target:card,clientX:50,clientY:30}));c.closeMemberNetwork();
 assert.equal(f.space.hasPointerCapture(1),false);await c.openMemberNetwork();assert.deepEqual(clone([...c.memberNetworkSession.positions]),before);assert.equal(c.memberNetworkSession.pinned.has(id),false);
 f.assertNative();c.closeMemberNetwork();
});

test('HTML card cancel/capture loss restores both its manual point and exact previous pin',async()=>{
 for(const endType of ['pointercancel','lostpointercapture'])for(const wasPinned of [false,true]){
  const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,id='source',b=s.elements.get(id),p={...s.positions.get(id)},pin={x:p.x+2,y:p.y-3};
  s.draggable=true;s.camera.zoom=1.2;c.drawMemberNetwork();if(wasPinned)s.pinned.set(id,pin);const before=clone([...s.positions]);
  b.setPointerCapture=()=>{};b.hasPointerCapture=()=>true;b.releasePointerCapture=()=>{};
  b.onpointerdown(inputEvent(f,{type:'pointerdown',target:b,clientX:10,clientY:10}));b.onpointermove(inputEvent(f,{type:'pointermove',target:b,clientX:50,clientY:30}));
  b['on'+endType](inputEvent(f,{type:endType,target:b,clientX:50,clientY:30}));
  assert.deepEqual(clone([...s.positions]),before);assert.equal(s.pinned.has(id),wasPinned);if(wasPinned)assert.deepEqual({...s.pinned.get(id)},pin);
  b.onclick();assert.equal(s.selected,'');f.assertNative();c.closeMemberNetwork();
 }
});

test('a real HTML card drag blocks wheel until its release',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,b=s.elements.get('source');s.draggable=true;
 s.camera.zoom=1.2;c.drawMemberNetwork();
 b.setPointerCapture=()=>{};b.hasPointerCapture=()=>true;b.releasePointerCapture=()=>{};
 b.onpointerdown(inputEvent(f,{type:'pointerdown',target:b,clientX:10,clientY:10}));b.onpointermove(inputEvent(f,{type:'pointermove',target:b,clientX:50,clientY:30}));
 const camera=clone(s.camera),positions=clone([...s.positions]);c.memberNetworkWheel(inputEvent(f,{target:b,deltaY:20,ctrlKey:true}));
 assert.deepEqual(clone(s.camera),camera);assert.deepEqual(clone([...s.positions]),positions);
 b.onpointerup(inputEvent(f,{type:'pointerup',target:b,clientX:50,clientY:30}));f.assertNative();c.closeMemberNetwork();
});

test('native canvas point drag also blocks wheel until its moveEnd callback',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,hooks=f.engineCalls[0][5];s.draggable=true;
 hooks.move('source',{x:500,y:350});const camera=clone(s.camera),positions=clone([...s.positions]);
 c.memberNetworkWheel(inputEvent(f,{deltaY:20,ctrlKey:true}));assert.deepEqual(clone(s.camera),camera);assert.deepEqual(clone([...s.positions]),positions);
 hooks.moveEnd('source');c.memberNetworkWheel(inputEvent(f,{deltaY:5}));assert.equal(s.camera.panY,camera.panY-5);
 f.assertNative();c.closeMemberNetwork();
});

test('close also cancels a live HTML card drag before its session positions are cached',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession,b=s.elements.get('source'),before=clone([...s.positions]);s.draggable=true;
 s.camera.zoom=1.2;c.drawMemberNetwork();
 b.setPointerCapture=()=>{};b.hasPointerCapture=()=>true;b.releasePointerCapture=()=>{};
 b.onpointerdown(inputEvent(f,{type:'pointerdown',target:b,clientX:10,clientY:10}));b.onpointermove(inputEvent(f,{type:'pointermove',target:b,clientX:50,clientY:30}));
 c.closeMemberNetwork();await c.openMemberNetwork();assert.deepEqual(clone([...c.memberNetworkSession.positions]),before);assert.equal(c.memberNetworkSession.pinned.size,0);
 f.assertNative();c.closeMemberNetwork();
});

test('Space keeps side-panel controls usable even when the pointer remains over the graph, but arms pan on a node',async()=>{
 const f=fixture(),c=f.context;await c.openMemberNetwork();const s=c.memberNetworkSession;
 const marker="memberNetworkHost.addEventListener('keydown',e=>{",start=source.indexOf(marker)+marker.length,end=source.indexOf('\n},true);',start);
 assert.ok(start>=marker.length&&end>start);vm.runInNewContext('function dispatchNetworkKeyDown(e){'+source.slice(start,end)+'\n}',c);
 s.hovered=true;
 for(const tag of ['button','input','select','textarea','summary']){
  const target=element(tag);target.closest=selector=>selector.split(',').some(part=>part===tag)?target:null;
  const e=inputEvent(f,{type:'keydown',code:'Space',key:' ',target});c.dispatchNetworkKeyDown(e);
  assert.equal(e.counts.prevented,0,tag+' keeps its normal Space activation/input');assert.equal(c.memberNetworkInput(s).space,false);
 }
 const card=s.elements.get('source'),e=inputEvent(f,{type:'keydown',code:'Space',key:' ',target:card});c.dispatchNetworkKeyDown(e);
 assert.equal(e.counts.prevented,1);assert.equal(s.input.space,true);c.memberNetworkCancelInput();f.assertNative();c.closeMemberNetwork();
});

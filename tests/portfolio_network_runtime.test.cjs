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
  setAttribute(key,value){this.attributes[key]=value;},querySelector(){return null;},
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
 const context={Map,Set,Math,Number,Float64Array,TypeError,URL,document:{createElement:element,createElementNS:(_,tag)=>element(tag)},
  root,memberNetworkHost:host,memberNetworkSpace:space,memberNetworkNodes:nodes,memberNetworkSvg:svg,memberNetworkInspector:inspector,
  memberNetworkButton:button,memberNetworkResize:observer,memberNetworkSession:null,memberNetworkOpening:false,memberNetworkGraph:graph,memberReset:false,
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
 const names=['memberNetworkStage','memberNetworkSnapshot','memberNetworkKind','memberNetworkKindText','memberNetworkSelect',
  'memberNetworkHighlight','renderMemberNetworkGrid','drawMemberNetwork','zoomMemberNetwork','fitMemberNetwork','closeMemberNetwork','openMemberNetwork'];
 vm.runInNewContext(geometry+'\n'+functionSource(relationship,'memberRelationshipIsMapRecord')+'\n'+names.map(name=>functionSource(source,name)).join('\n'),context);
 const actualLayout=context.memberNetworkLayout;let layoutCalls=0;
 context.memberNetworkLayout=(items,links)=>{layoutCalls++;return actualLayout(items,links);};
 const nativeValues=()=>clone({scope,edges,native,initial:[...context.initialPositions],offsets:[...context.focusOffsets],bases:[...context.memberLayoutBases]});
 const before=nativeValues();
 return{context,scope,edges,stock,record,candidate,native,root,host,space,nodes,svg,inspector,live,button,controls,alreadyInert,observer,hostParts,
  visualContext,visualCalls,reference,engine,engineCalls,engineState,graph,gridFine,gridCoarse,layoutCalls:()=>layoutCalls,assertNative:()=>assert.deepEqual(nativeValues(),before)};
}
test('stage thresholds are dots / names / cards at the exact boundaries',()=>{
 const {context:c}=fixture();
 for(const [zoom,expected]of[[.02,'dots'],[.279999,'dots'],[.28,'names'],[.799999,'names'],[.8,'cards'],[4,'cards']])assert.equal(c.memberNetworkStage(zoom),expected);
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
 hooks.select('source');assert.equal(s.selected,'source');hooks.highlight('stock');assert.equal(f.engineState.highlights.at(-1),'stock');
 assert.deepEqual(clone([...s.positions]),before);assert.equal(f.layoutCalls(),1);c.closeMemberNetwork();
 hooks.viewport({zoom:2,panX:99,panY:99});assert.equal(c.memberNetworkSession,null);assert.equal(f.host.hidden,true);f.assertNative();
 await c.openMemberNetwork();const next=c.memberNetworkSession,selected=next.selected,highlights=f.engineState.highlights.length;
 hooks.select('source');hooks.highlight('source');hooks.viewport({zoom:2,panX:99,panY:99});
 assert.equal(c.memberNetworkSession,next);assert.equal(next.selected,selected);assert.equal(f.engineState.highlights.length,highlights);
 c.closeMemberNetwork();f.assertNative();
});
test('runtime delegates gestures to vendor rather than adding custom pointer/wheel handlers',()=>{
 assert.doesNotMatch(source,/memberNetworkSpace\.addEventListener\(['"](?:wheel|pointerdown)['"]/);
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

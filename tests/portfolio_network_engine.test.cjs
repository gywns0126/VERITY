const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const enginePath=path.join(__dirname,'../review/member-map/prototype-network-engine.js');
const source=fs.readFileSync(enginePath,'utf8');
const copy=value=>JSON.parse(JSON.stringify(value));
function nearCamera(actual,expected){for(const key of ['zoom','panX','panY'])assert.ok(Math.abs(actual[key]-expected[key])<1e-9,`${key}: ${actual[key]} != ${expected[key]}`);}
function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
function functionSource(text,name){
 const start=text.indexOf('function '+name+'(');assert.ok(start>=0,'actual function '+name);
 const begin=text.indexOf('{',start);let depth=0;
 for(let i=begin;i<text.length;i++){if(text[i]==='{')depth++;else if(text[i]==='}'&&--depth===0)return text.slice(start,i+1);}
 assert.fail('unterminated '+name);
}
function lockedMap(entries){const map=new Map(entries.map(([id,value])=>[id,freeze(value)]));
 for(const method of ['set','delete','clear'])Object.defineProperty(map,method,{value:()=>assert.fail('input map mutation')});return map;}
function colorDOM(){const children=[];return{root:{append(el){children.push(el);}},
 document:{createElement(){const el={style:{},dataset:{},remove(){children.splice(children.indexOf(el),1);}};return el;}},
 getComputedStyle:el=>({color:el.style.color?.startsWith('#')?el.style.color:'#6b7684'}),children};}
function fixture(options={}){
 const ids=['stock # [" ] : 한글','source\\path','__proto__'];
 const items=freeze(ids.map((id,index)=>({id,kind:index?'event':'stock',name:'private title '+index,evidence:[{text:'private source body'}]})));
 const links=freeze(['direct','indirect','history','review','reference'].map((kind,index)=>({id:kind,from:ids[index%3],to:ids[(index+1)%3],status:kind})));
 const positions=lockedMap(ids.map((id,index)=>[id,{x:440+index*170,y:220+index*95}]));
 const visuals=lockedMap(links.map((e,index)=>[e.id,{kind:e.status,color:'#'+String(index+1).repeat(6),width:1+index*.5,dash:index?'2 '+(index+2):'',statusLabel:e.status}]));
 const before=copy({items,links,positions:[...positions],visuals:[...visuals]});
 const container={rect:{width:900,height:600},getBoundingClientRect(){return this.rect;}};
 const state={config:null,zoom:1,pan:{x:0,y:0},handlers:[],viewportCalls:0,resizeCalls:0,destroyCalls:0,lookups:[],nodeStyles:{},nodes:[],edges:[],batches:0};
 const renderElement=element=>({id:()=>element.data.id,data:key=>element.data[key],renderStyle:{},classes:new Set(),isLocked:false,
  style(key,value){if(typeof key==='object')Object.assign(this.renderStyle,key);else if(value!==undefined)this.renderStyle[key]=value;return value===undefined&&typeof key==='string'?this.renderStyle[key]:this;},
  locked(){return state.autolock||this.isLocked;},lock(){this.isLocked=true;},unlock(){this.isLocked=false;},
  position(value){if(value!==undefined&&!this.locked())element.position={...value};return element.position;}});
 const collection={removeClass(){return this;},addClass(){return this;},difference(){return this;},
  style(key,value){if(typeof key==='object')Object.assign(state.nodeStyles,key);else if(value!==undefined)state.nodeStyles[key]=value;return value===undefined&&typeof key==='string'?state.nodeStyles[key]:this;},
  hide(){state.nodeStyles.display='none';return this;},show(){state.nodeStyles.display='element';return this;}};
 const cy={zoom:()=>state.zoom,pan:()=>({...state.pan}),
  autolock(value){if(value!==undefined)state.autolock=value;return state.autolock;},
  autoungrabify(value){if(value!==undefined)state.autoungrabify=value;return state.autoungrabify;},
  on(...args){if(options.failOn)throw new Error('event initialization failed');state.handlers.push(args);return this;},
  viewport(value){state.viewportCalls++;state.zoom=value.zoom;state.pan={...value.pan};emit('viewport');return this;},
  resize(){state.resizeCalls++;return this;},destroy(){state.destroyCalls++;},batch(fn){state.batches++;fn();},elements:()=>collection,nodes:()=>state.nodes,edges:()=>state.edges,
  getElementById(id){state.lookups.push(id);return{closedNeighborhood:()=>collection};},
  $(selector){assert.fail('unsafe selector lookup '+selector);},layout(){assert.fail('no second/force layout');}};
 function emit(type,target){for(const args of state.handlers)if(args[0].split(' ').includes(type))args.at(-1)({target:target||cy});}
 const hooks={viewport:[],select:[],highlight:[],move:[],moveEnd:[]};
 const context={window:{cytoscape(config){state.config=config;if(options.factoryFailure)throw new Error('factory failed');
  state.autolock=config.autolock;state.autoungrabify=config.autoungrabify;
  state.nodes=config.elements.filter(el=>el.position).map(renderElement);state.edges=config.elements.filter(el=>!el.position).map(renderElement);
  state.nodes.removeClass=function(name){this.forEach(node=>node.classes.delete(name));return this;};
  state.nodes.addClass=function(name){this.forEach(node=>node.classes.add(name));return this;};return cy;}},
  ...colorDOM(),memberNetworkKind:n=>n.kind==='stock'?'stock':'source',
  fetch:()=>assert.fail('no upload'),XMLHttpRequest:()=>assert.fail('no upload'),
  JSON:{stringify:()=>assert.fail('no source payload serialization')},Map,Set,Math,Number};
 vm.runInNewContext(functionSource(source,'memberCreateNetworkEngine'),context);
 const create=()=>context.memberCreateNetworkEngine(container,items,links,positions,visuals,Object.fromEntries(Object.keys(hooks).map(key=>[key,(id,position)=>hooks[key].push(key==='move'?{id,position}:id)])));
 return{ids,items,links,positions,visuals,before,container,state,cy,hooks,emit,create,
  unchanged:()=>assert.deepEqual(copy({items,links,positions:[...positions],visuals:[...visuals]}),before)};
}
test('loader only checks the embedded library: present resolves, missing/nonfunction rejects, with zero DOM/network/timers',async()=>{
 const blocked=()=>assert.fail('inline-only loader must not create scripts, access DOM, start timers or use network');
 const context={window:{cytoscape:()=>assert.fail('loader must not initialize a core')},Promise,
  fetch:blocked,XMLHttpRequest:blocked,setTimeout:blocked,clearTimeout:blocked};
 Object.defineProperty(context,'document',{get:blocked});
 vm.runInNewContext(functionSource(source,'memberLoadNetworkEngine'),context);
 await assert.doesNotReject(()=>context.memberLoadNetworkEngine());
 for(const unavailable of [undefined,null,{}]){context.window.cytoscape=unavailable;
  await assert.rejects(()=>context.memberLoadNetworkEngine(),/Graph engine unavailable/);}
 context.window.cytoscape=()=>{};await assert.doesNotReject(()=>context.memberLoadNetworkEngine());
});
test('adapter uses exact frozen supplied positions and preset-only locked layout without sending private payload',()=>{
 const f=fixture(),api=f.create(),config=f.state.config;
 assert.deepEqual(copy(config.layout),{name:'preset',fit:false,animate:false});
 assert.equal(config.autolock,true);assert.equal(config.autoungrabify,true);
  assert.equal(config.userZoomingEnabled,false,'the shared input adapter owns user wheel/pinch zoom');
  assert.equal(config.userPanningEnabled,true,'ordinary mouse background pan remains available without a prior click');
  assert.equal(config.wheelSensitivity,undefined,'no vendor sensitivity override is needed when user zoom is disabled');
 const nodes=config.elements.filter(e=>e.position);assert.equal(nodes.length,f.items.length);
 nodes.forEach((node,index)=>{assert.deepEqual(copy(node.position),copy(f.positions.get(f.ids[index])));assert.notEqual(node.position,f.positions.get(f.ids[index]));
  assert.equal(node.data.name,undefined);assert.equal(node.data.evidence,undefined);});
 assert.equal(new Set(config.elements.map(e=>e.data.id)).size,config.elements.length);
 api.setCamera({zoom:.2,panX:3,panY:4});api.resize();f.unchanged();api.destroy();
});
test('actual directed edges retain five native status/color/width/dash semantics without fabricated edges',()=>{
 const f=fixture(),api=f.create(),elements=f.state.config.elements,nodes=elements.filter(e=>e.position),edges=elements.filter(e=>!e.position);
 assert.equal(edges.length,f.links.length);
 edges.forEach((edge,index)=>{const original=f.links[index],visual=f.visuals.get(original.id);
  assert.equal(edge.data.source,nodes[f.ids.indexOf(original.from)].data.id);assert.equal(edge.data.target,nodes[f.ids.indexOf(original.to)].data.id);
  assert.equal(edge.data.semantic,visual.kind);assert.equal(edge.data.color,visual.color);assert.equal(edge.data.width,visual.width);
  assert.equal(edge.data.lineStyle,index?'dashed':'solid');assert.deepEqual(copy(edge.data.dash),index?[2,index+2]:[1,1]);});
 const style=f.state.config.style.find(rule=>rule.selector==='edge').style;
 for(const [key,value]of Object.entries({'line-color':'data(color)',width:'data(width)','line-style':'data(lineStyle)','line-dash-pattern':'data(dash)'}))assert.equal(style[key],value);
 f.unchanged();api.destroy();
});
test('camera roundtrip matches native affine projection and identical setCamera never recursively emits',()=>{
 const f=fixture(),api=f.create();
 for(const zoom of [.02,.08,.28,.8,1,2,4]){
  const camera={zoom,panX:37,panY:-26};api.setCamera(camera);nearCamera(api.getCamera(),camera);
  const {width,height}=f.container.rect;
  for(const p of f.positions.values()){
   assert.ok(Math.abs(p.x*zoom+f.state.pan.x-(width/2+(p.x-500)*zoom+37))<1e-9);
   assert.ok(Math.abs(p.y*zoom+f.state.pan.y-(height/2+(p.y-340)*zoom-26))<1e-9);
  }
  const count=f.state.viewportCalls;api.setCamera(camera);assert.equal(f.state.viewportCalls,count);
 }
 f.state.zoom=.7;f.state.pan={x:45,y:-30};f.emit('viewport');
 nearCamera(f.hooks.viewport.at(-1),{zoom:.7,panX:-55,panY:-92});
 f.container.rect={width:390,height:844};api.resize();api.setCamera({zoom:.7,panX:0,panY:0});
 nearCamera(api.getCamera(),{zoom:.7,panX:0,panY:0});f.unchanged();api.destroy();
});
test('arbitrary source IDs roundtrip through events and highlight without selector interpolation',()=>{
 const f=fixture(),api=f.create(),nodes=f.state.config.elements.filter(e=>e.position);
 f.ids.forEach((id,index)=>{const target={id:()=>nodes[index].data.id};f.emit('tap',target);f.emit('mouseover',target);api.highlight(id);
  assert.equal(f.hooks.select.at(-1),id);assert.equal(f.hooks.highlight.at(-1),id);assert.equal(f.state.lookups.at(-1),nodes[index].data.id);});
 f.emit('mouseout');assert.equal(f.hooks.highlight.at(-1),'');api.highlight('');f.unchanged();api.destroy();
});
test('vendor tap select-other/reselect never moves camera, supplied positions or rendered centers in names/cards',()=>{
 for(const [stage,zoom]of [['names',.4],['cards',1.2]]){
  const f=fixture(),api=f.create();api.setCamera({zoom,panX:83,panY:-47});api.setStage(stage,zoom);
  const nodes=f.state.config.elements.filter(el=>el.position),camera=copy(api.getCamera()),positions=copy(nodes.map(el=>el.position));
  const centers=()=>nodes.map(el=>({x:el.position.x*f.state.zoom+f.state.pan.x,y:el.position.y*f.state.zoom+f.state.pan.y}));
  const before=centers(),viewportCalls=f.state.viewportCalls,notices=f.hooks.viewport.length;
  f.cy.fit=()=>assert.fail('tap must not fit/recenter');
  for(const node of nodes)freeze(node.position);
  const order=[0,1,0,0];
  for(const index of order){
   f.emit('tap',{id:()=>nodes[index].data.id});assert.equal(f.hooks.select.at(-1),f.ids[index]);
   assert.deepEqual(copy(api.getCamera()),camera);assert.deepEqual(copy(nodes.map(el=>el.position)),positions);assert.deepEqual(centers(),before);
   assert.equal(f.state.viewportCalls,viewportCalls);assert.equal(f.hooks.viewport.length,notices);f.unchanged();
  }
  assert.deepEqual(f.hooks.select,order.map(index=>f.ids[index]));api.destroy();
 }
});
test('destroy is once-only and stale callbacks/camera operations are inert',()=>{
 const f=fixture(),api=f.create();api.destroy();api.destroy();assert.equal(f.state.destroyCalls,1);
 const before=copy(f.hooks);f.emit('viewport');f.emit('tap',{id:()=> 'n0'});f.emit('mouseover',{id:()=> 'n0'});f.emit('mouseout');
 api.setCamera({zoom:2,panX:0,panY:0});api.resize();api.highlight(f.ids[0]);
 assert.deepEqual(copy(f.hooks),before);assert.equal(f.state.viewportCalls,0);assert.equal(f.state.resizeCalls,0);f.unchanged();
});
test('stage/zoom preserves rendered dot sizes, native line weights and all supplied positions',()=>{
 const f=fixture(),api=f.create(),before=copy(f.state.config.elements);
 f.state.nodes[1].classes.add('an-network-muted');
 for(const zoom of [.02,.08,.2,.279999,.28,.64,.8,1.2,4])for(const stage of ['dots','names','cards']){
  api.setStage(stage,zoom);
  for(const node of f.state.nodes){const expected=node.data('kind')==='stock'?10:6;
   assert.ok(Math.abs(node.renderStyle.width*zoom-expected)<1e-9);assert.ok(Math.abs(node.renderStyle.height*zoom-expected)<1e-9);
   assert.equal(node.classes.has('an-network-card'),stage==='cards');assert.equal(node.renderStyle.opacity,undefined,'no opacity bypass may override muted highlight');}
  assert.equal(f.state.nodes[1].classes.has('an-network-muted'),true);
  for(const edge of f.state.edges){assert.ok(Math.abs(edge.renderStyle.width*zoom-edge.data('width'))<1e-9);
   edge.renderStyle['line-dash-pattern'].forEach((value,index)=>assert.ok(Math.abs(value*zoom-edge.data('dash')[index])<1e-9));}
  assert.deepEqual(copy(f.state.config.elements),before);
  const batches=f.state.batches;api.setStage(stage,zoom);assert.equal(f.state.batches,batches,'identical stage+zoom must not repeat style work');
 }
 f.state.zoom=.5;api.setStage('dots');assert.equal(f.state.nodes[0].renderStyle.width,20,'omitted zoom uses vendor camera');
 const styles=copy([...f.state.nodes,...f.state.edges].map(el=>el.renderStyle));api.destroy();api.setStage('cards',2);
 assert.deepEqual(copy([...f.state.nodes,...f.state.edges].map(el=>el.renderStyle)),styles);f.unchanged();
});
test('partial engine initialization failure destroys allocated core and leaves input intact',()=>{
 const f=fixture({failOn:true});assert.throws(f.create,/event initialization failed/);assert.equal(f.state.destroyCalls,1);f.unchanged();
 const failed=fixture({factoryFailure:true});assert.throws(failed.create,/factory failed/);assert.equal(failed.state.destroyCalls,0);failed.unchanged();
});
test('visibility retains the exact induced subgraph without deleting nodes, changing geometry or camera',()=>{
 const f=fixture(),api=f.create();api.setCamera({zoom:.4,panX:75,panY:-21});
 const camera=copy(api.getCamera()),before=copy(f.state.config.elements),ids=new Set(f.ids.slice(0,2));
 api.setVisible(ids);ids.clear();
 f.state.nodes.forEach((node,index)=>assert.equal(node.renderStyle.display,index<2?'element':'none'));
 f.state.edges.forEach(edge=>assert.equal(edge.renderStyle.display,['n0','n1'].includes(edge.data('source'))&&['n0','n1'].includes(edge.data('target'))?'element':'none'));
 f.emit('tap',f.state.nodes[2]);assert.equal(f.hooks.select.length,0);
 api.highlight(f.ids[0]);api.setStage('cards',.4);
 assert.equal(f.state.nodes[2].renderStyle.display,'none','stage/highlight cannot unhide filtered nodes');
 api.setVisible(new Set());assert.ok([...f.state.nodes,...f.state.edges].every(el=>el.renderStyle.display==='none'));
 api.setVisible(new Set([...f.ids,'unknown']));assert.ok([...f.state.nodes,...f.state.edges].every(el=>el.renderStyle.display==='element'));
 assert.deepEqual(copy(f.state.config.elements),before);nearCamera(api.getCamera(),camera);f.unchanged();api.destroy();
});
test('programmatic positions work while locked, preserve locks and inputs, and never emit a drag move or move peers/camera',()=>{
 const f=fixture(),api=f.create(),camera=copy(api.getCamera()),peers=copy(f.state.nodes.map(node=>node.position()));
 f.state.nodes[0].lock();
 const changes=lockedMap([[f.ids[0],{x:-300,y:45}],[f.ids[1],{x:1200,y:-90}],[f.ids[2],{x:Infinity,y:20}],['unknown',{x:1,y:2}]]);
 api.setPositions(changes);
 assert.deepEqual(copy(f.state.nodes[0].position()),{x:-300,y:45});assert.deepEqual(copy(f.state.nodes[1].position()),{x:1200,y:-90});
 assert.deepEqual(copy(f.state.nodes[2].position()),peers[2]);assert.equal(f.state.autolock,true);assert.equal(f.state.nodes[0].isLocked,true);
 api.setInteraction({draggable:true});assert.equal(f.state.nodes[1].locked(),false,'temporary global unlock must not create permanent per-node locks');
 assert.equal(f.state.nodes[0].locked(),true,'explicit per-node lock is retained');
 assert.equal(f.hooks.move.length,0);assert.equal(f.hooks.viewport.length,0);nearCamera(api.getCamera(),camera);f.unchanged();api.destroy();
});
test('only actual native dragging reports copied model points and suppresses its tap, never peers or camera',()=>{
 const f=fixture(),api=f.create(),node=f.state.nodes[0],camera=copy(api.getCamera()),peers=copy(f.state.nodes.slice(1).map(n=>n.position()));
 api.setInteraction({draggable:true});assert.equal(f.state.autolock,false);assert.equal(f.state.autoungrabify,false);
 f.emit('grab',node);f.emit('drag',node);assert.equal(f.hooks.move.length,0,'grab without displacement is not a drag');
 node.position({x:111,y:-222});f.emit('drag',node);f.emit('drag',node);
 assert.deepEqual(copy(f.hooks.move),[{id:f.ids[0],position:{x:111,y:-222}}]);
 api.setInteraction({draggable:true});node.position({x:112,y:-223});f.emit('drag',node);
 assert.equal(f.hooks.move.length,2,'idempotent interaction refresh must not cancel the active gesture');
 f.emit('free',node);f.emit('tap',node);assert.equal(f.hooks.select.length,0);assert.deepEqual(f.hooks.moveEnd,[f.ids[0]]);
 f.hooks.move[1].position.x=999;assert.equal(node.position().x,112,'callback points cannot alias model points');
 f.emit('tapstart',node);f.emit('grab',node);f.emit('free',node);f.emit('tap',node);
 assert.deepEqual(f.hooks.select,[f.ids[0]],'the next genuine click selects normally');assert.deepEqual(f.hooks.moveEnd,[f.ids[0]],'unmoved click has no completion callback');
 assert.deepEqual(copy(f.state.nodes.slice(1).map(n=>n.position())),peers);nearCamera(api.getCamera(),camera);assert.equal(f.state.viewportCalls,0);
 api.setInteraction({draggable:false});assert.equal(f.state.autolock,true);assert.equal(f.state.autoungrabify,true);
 f.emit('grab',node);f.emit('drag',node);assert.equal(f.hooks.move.length,2);f.unchanged();api.destroy();
});
test('display scales refresh at identical stage/zoom, retain status semantics and opt into names-stage labels only',()=>{
 const f=fixture(),api=f.create(),before=copy(f.state.config.elements);api.setStage('names',.5);
 api.setDisplay({nodeScale:2,edgeScale:3,labels:true});api.setStage('names',.5);
 f.state.nodes.forEach((node,index)=>{assert.equal(node.renderStyle.width,(index?6:10)*4);assert.equal(node.renderStyle.label,f.items[index].name);});
 f.state.edges.forEach(edge=>{assert.equal(edge.renderStyle.width,edge.data('width')*6);assert.deepEqual(copy(edge.renderStyle['line-dash-pattern']),copy(edge.data('dash').map(n=>n*2)));});
 const batches=f.state.batches;api.setDisplay({nodeScale:2,edgeScale:3,labels:true});api.setDisplay({nodeScale:NaN,edgeScale:0,labels:'invalid'});
 assert.equal(f.state.batches,batches);api.setDisplay({nodeScale:1});assert.equal(f.state.edges[0].renderStyle.width,f.state.edges[0].data('width')*6);
 for(const stage of ['dots','cards']){api.setStage(stage,.5);assert.ok(f.state.nodes.every(node=>node.renderStyle.label===''));}
 api.setStage('names',.5);api.setDisplay({labels:false});assert.ok(f.state.nodes.every(node=>node.renderStyle.label===''));
 assert.deepEqual(copy(f.state.config.elements),before);f.unchanged();api.destroy();
});
test('destroy makes exploration setters and late drag callbacks inert',()=>{
 const f=fixture(),api=f.create(),node=f.state.nodes[0];api.setInteraction({draggable:true});f.emit('grab',node);api.destroy();
 const before=copy({config:f.state.config,hooks:f.hooks,batches:f.state.batches,autolock:f.state.autolock});
 api.setVisible(new Set());api.setPositions(new Map([[f.ids[0],{x:0,y:0}]]));api.setInteraction({draggable:false});api.setDisplay({nodeScale:2,labels:true});
 f.emit('drag',node);f.emit('free',node);f.emit('tapstart',node);f.emit('tap',node);api.destroy();
 assert.deepEqual(copy({config:f.state.config,hooks:f.hooks,batches:f.state.batches,autolock:f.state.autolock}),before);
 assert.equal(f.state.destroyCalls,1);f.unchanged();
});
test('optional degree sizing counts distinct visible verified neighbors, not repeated edges, and refreshes at fixed zoom',()=>{
 const f=fixture(),api=f.create();api.setStage('names',.5);
 assert.equal(f.state.nodes[0].renderStyle.width,20,'default sizing remains unchanged');
 api.setDisplay({degreeSizing:true});
 for(const node of f.state.nodes){const base=node.data('kind')==='stock'?10:6;assert.ok(Math.abs(node.renderStyle.width-base*(1+Math.sqrt(2)*.16)/.5)<1e-9);}
 api.setVisible(new Set(f.ids.slice(0,2)));
 assert.ok(Math.abs(f.state.nodes[0].renderStyle.width-20*1.16)<1e-9,'parallel/repeated directed links count as one neighbor');
 api.setVisible(new Set([f.ids[0]]));assert.equal(f.state.nodes[0].renderStyle.width,20,'isolated visible node has zero degree');
 api.setVisible(new Set(f.ids));api.setDisplay({degreeSizing:false});assert.equal(f.state.nodes[0].renderStyle.width,20);
 assert.equal(f.state.viewportCalls,0);f.unchanged();api.destroy();
});
const vendorPath=path.join(__dirname,'../vercel-api/public/member-map-vendor/cytoscape-3.34.4.min.js');
test('pinned real vendor headless preserves supplied preset positions and safe arbitrary IDs',{skip:!fs.existsSync(vendorPath)&&'vendor not yet supplied by MAIN'},()=>{
 const cytoscape=require(vendorPath),f=fixture();let core;
 // Normalize VM-created option objects into the vendor's realm, just as the browser shares one realm.
 const context={window:{cytoscape:options=>{core=cytoscape({...copy({...options,container:undefined}),headless:true,styleEnabled:true});
  const viewport=core.viewport.bind(core);core.viewport=value=>viewport(copy(value));
  core.elements().forEach(el=>{const style=el.style.bind(el);el.style=function(key,value){return style(typeof key==='object'?copy(key):key,value);};});return core;}},
  ...colorDOM(),memberNetworkKind:n=>n.kind==='stock'?'stock':'source'};
 vm.runInNewContext(functionSource(source,'memberCreateNetworkEngine'),context);
 const api=context.memberCreateNetworkEngine(f.container,f.items,f.links,f.positions,f.visuals,{viewport(){},select(){},highlight(){}});
 try{assert.equal(core.nodes().length,f.items.length);assert.equal(core.edges().length,f.links.length);
  assert.equal(core.userZoomingEnabled(),false);assert.equal(core.userPanningEnabled(),true);
  core.nodes().forEach((node,index)=>assert.deepEqual(copy(node.position()),copy(f.positions.get(f.ids[index]))));
  core.edges().forEach((edge,index)=>{assert.equal(edge.data('semantic'),f.links[index].status);
   assert.equal(edge.style('width'),f.visuals.get(f.links[index].id).width+'px');assert.equal(edge.style('line-style'),index?'dashed':'solid');});
  for(const zoom of [.02,.08,.28,.8,1.2,4]){
   api.setCamera({zoom,panX:0,panY:0});api.setStage('cards',zoom);assert.ok(core.nodes().every(node=>node.style('opacity')==='0'));
   api.setStage('dots',zoom);assert.ok(core.nodes().every(node=>node.style('opacity')==='1'));
   core.nodes().forEach((node,index)=>{assert.ok(Math.abs(node.width()*zoom-(index?6:10))<1e-9);
    assert.deepEqual(copy(node.position()),copy(f.positions.get(f.ids[index])));});
   core.edges().forEach(edge=>assert.ok(Math.abs(parseFloat(edge.style('width'))*zoom-edge.data('width'))<1e-9));
   core.edges().forEach(edge=>edge.style('line-dash-pattern').split(' ').map(Number).forEach((value,index)=>assert.ok(Math.abs(value*zoom-edge.data('dash')[index])<1e-9)));
  }
  const muted=core.nodes()[1];muted.addClass('an-network-muted');api.setStage('names',.5);
  assert.equal(muted.style('opacity'),'0.12');api.setStage('cards',.5);assert.equal(muted.style('opacity'),'0');
  api.setStage('dots',.5);assert.equal(muted.style('opacity'),'0.12','leaving cards preserves native muted state');
  api.highlight(f.ids[1]);api.setCamera({zoom:.8,panX:33,panY:-2});nearCamera(api.getCamera(),{zoom:.8,panX:33,panY:-2});
  core.nodes().forEach((node,index)=>assert.deepEqual(copy(node.position()),copy(f.positions.get(f.ids[index]))));f.unchanged();
 }finally{api.destroy();}assert.equal(core.destroyed(),true);
});
test('pinned vendor applies visibility, locked programmatic positioning, display and single-node drag without camera drift',()=>{
 const cytoscape=require(vendorPath),f=fixture(),moves=[],selected=[],ended=[];let core;
 const context={window:{cytoscape:options=>{core=cytoscape({...copy({...options,container:undefined}),headless:true,styleEnabled:true});
  const viewport=core.viewport.bind(core);core.viewport=value=>viewport(copy(value));
  core.elements().forEach(el=>{const style=el.style.bind(el);el.style=function(key,value){return style(typeof key==='object'?copy(key):key,value);};
   const position=el.position.bind(el);el.position=value=>position(value===undefined?undefined:copy(value));});return core;}},
  ...colorDOM(),memberNetworkKind:n=>n.kind==='stock'?'stock':'source'};
 vm.runInNewContext(functionSource(source,'memberCreateNetworkEngine'),context);
 const api=context.memberCreateNetworkEngine(f.container,f.items,f.links,f.positions,f.visuals,
  {viewport(){},highlight(){},select:id=>selected.push(id),move:(id,p)=>moves.push({id,p:copy(p)}),moveEnd:id=>ended.push(id)});
 try{
  api.setCamera({zoom:.5,panX:37,panY:-29});const camera=copy(api.getCamera()),peers=copy(core.nodes().slice(1).map(n=>n.position()));
  api.setPositions(new Map([[f.ids[0],{x:55,y:-70}]]));assert.deepEqual(copy(core.nodes()[0].position()),{x:55,y:-70});
  assert.equal(core.autolock(),true);assert.equal(moves.length,0);
  api.setVisible(new Set(f.ids.slice(0,2)));assert.deepEqual(core.nodes().map(n=>n.visible()),[true,true,false]);
  core.edges().forEach(edge=>assert.equal(edge.visible(),edge.source().id()!=='n2'&&edge.target().id()!=='n2'));
  api.setVisible(new Set(f.ids));assert.ok(core.elements().every(el=>el.visible()));
  api.setStage('names',.5);api.setDisplay({nodeScale:2,edgeScale:3,labels:true});api.setStage('names',.5);
  assert.equal(core.nodes()[0].width(),40);assert.equal(core.nodes()[0].style('label'),f.items[0].name);
  assert.equal(parseFloat(core.edges()[0].style('width')),6);
  api.setInteraction({draggable:true});assert.ok(core.nodes().every(n=>!n.locked()&&n.grabbable()&&!n.selected()));
  const node=core.nodes()[0];node.emit('grab');node.position({x:-25,y:90});node.emit('drag');node.emit('free');node.emit('tap');
  assert.deepEqual(moves,[{id:f.ids[0],p:{x:-25,y:90}}]);assert.deepEqual(selected,[]);assert.deepEqual(ended,[f.ids[0]]);
  node.emit('tapstart');node.emit('grab');node.emit('free');node.emit('tap');assert.deepEqual(selected,[f.ids[0]]);
  assert.deepEqual(copy(core.nodes().slice(1).map(n=>n.position())),peers);nearCamera(api.getCamera(),camera);
  api.setInteraction({draggable:false});assert.ok(core.nodes().every(n=>n.locked()&&!n.grabbable()));
  f.unchanged();
 }finally{api.destroy();}assert.equal(core.destroyed(),true);
});
test('inline vendor bytes match the pinned canonical file and SHA-256 manifest',()=>{
 const vendor=fs.readFileSync(vendorPath),manifest=JSON.parse(fs.readFileSync(path.join(path.dirname(vendorPath),'cytoscape.json'),'utf8'));
 assert.equal(require('node:crypto').createHash('sha256').update(vendor).digest('hex'),manifest.sha256);
 const canvas=fs.readFileSync(process.env.MEMBER_MAP_CANVAS||path.join(__dirname,'../vercel-api/public/member-map-canvas.html'),'utf8');
 assert.ok(canvas.includes(vendor.toString('utf8').trimEnd()),'complete canonical vendor must be inline, not an external script');
});

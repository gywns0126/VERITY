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
 const renderElement=element=>({data:key=>element.data[key],renderStyle:{},classes:new Set(),
  style(key,value){if(typeof key==='object')Object.assign(this.renderStyle,key);else if(value!==undefined)this.renderStyle[key]=value;return value===undefined&&typeof key==='string'?this.renderStyle[key]:this;},
  position(value){assert.equal(value,undefined,'stage must not rewrite model positions');return element.position;}});
 const collection={removeClass(){return this;},addClass(){return this;},difference(){return this;},
  style(key,value){if(typeof key==='object')Object.assign(state.nodeStyles,key);else if(value!==undefined)state.nodeStyles[key]=value;return value===undefined&&typeof key==='string'?state.nodeStyles[key]:this;},
  hide(){state.nodeStyles.display='none';return this;},show(){state.nodeStyles.display='element';return this;}};
 const cy={zoom:()=>state.zoom,pan:()=>({...state.pan}),
  on(...args){if(options.failOn)throw new Error('event initialization failed');state.handlers.push(args);return this;},
  viewport(value){state.viewportCalls++;state.zoom=value.zoom;state.pan={...value.pan};emit('viewport');return this;},
  resize(){state.resizeCalls++;return this;},destroy(){state.destroyCalls++;},batch(fn){state.batches++;fn();},elements:()=>collection,nodes:()=>state.nodes,edges:()=>state.edges,
  getElementById(id){state.lookups.push(id);return{closedNeighborhood:()=>collection};},
  $(selector){assert.fail('unsafe selector lookup '+selector);},layout(){assert.fail('no second/force layout');}};
 function emit(type,target){for(const args of state.handlers)if(args[0].split(' ').includes(type))args.at(-1)({target:target||cy});}
 const hooks={viewport:[],select:[],highlight:[]};
 const context={window:{cytoscape(config){state.config=config;if(options.factoryFailure)throw new Error('factory failed');
  state.nodes=config.elements.filter(el=>el.position).map(renderElement);state.edges=config.elements.filter(el=>!el.position).map(renderElement);
  state.nodes.removeClass=function(name){this.forEach(node=>node.classes.delete(name));return this;};
  state.nodes.addClass=function(name){this.forEach(node=>node.classes.add(name));return this;};return cy;}},
  ...colorDOM(),memberNetworkKind:n=>n.kind==='stock'?'stock':'source',
  fetch:()=>assert.fail('no upload'),XMLHttpRequest:()=>assert.fail('no upload'),
  JSON:{stringify:()=>assert.fail('no source payload serialization')},Map,Set,Math,Number};
 vm.runInNewContext(functionSource(source,'memberCreateNetworkEngine'),context);
 const create=()=>context.memberCreateNetworkEngine(container,items,links,positions,visuals,Object.fromEntries(Object.keys(hooks).map(key=>[key,value=>hooks[key].push(value)])));
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
 assert.equal(config.wheelSensitivity,undefined,'vendor default wheel sensitivity is retained');
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
test('inline vendor bytes match the pinned canonical file and SHA-256 manifest',()=>{
 const vendor=fs.readFileSync(vendorPath),manifest=JSON.parse(fs.readFileSync(path.join(path.dirname(vendorPath),'cytoscape.json'),'utf8'));
 assert.equal(require('node:crypto').createHash('sha256').update(vendor).digest('hex'),manifest.sha256);
 const canvas=fs.readFileSync(process.env.MEMBER_MAP_CANVAS||path.join(__dirname,'../vercel-api/public/member-map-canvas.html'),'utf8');
 assert.ok(canvas.includes(vendor.toString('utf8').trimEnd()),'complete canonical vendor must be inline, not an external script');
});

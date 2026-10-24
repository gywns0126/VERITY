// Synthetic state only. No account, network, browser, or persistence writes.
// This is a characterization of v2, not an assertion that historical origins
// can be recovered. Card measurements below are explicit test inputs.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '..');
const esbuild = createRequire(path.join(process.env.MEMBER_MAP_TEST_DEPENDENCY_ROOT || root, 'package.json'))('esbuild');
const source = fs.readFileSync(path.join(root, 'review/member-map/Map.snapshot.tsx'), 'utf8');
const box = {exports:{}};
vm.runInNewContext(esbuild.transformSync(source + '\nexport {mergePrototypeDraft,mergePrototypeOriginSave,prototypeMemberModel,validMapDocument,editMapLayout};',
    {loader:'tsx',format:'cjs',target:'es2022'}).code, {
    module:box,exports:box.exports,require:name => {
        if(name==='react')return {};
        if(name==='framer')return {addPropertyControls(){},ControlType:{Number:'number'}};
        throw Error(name);
    }, TextEncoder,URL,AbortController,Map,Set,console,
});
const {mergePrototypeDraft:merge,prototypeMemberModel:model,validMapDocument,editMapLayout} = box.exports;
const clone = value => JSON.parse(JSON.stringify(value));
const candidate=box.exports;
const ids = ['company:000660','company:TSM','overview','hbm',
    'automatic:relation:sec-role:ac04dfa1e009efa0','contract:KR:348210:20261006900146'];
function fixture(){
    const companies = [{id:ids[0],ticker:'000660',market:'KR',name:'Synthetic A'},
        {id:ids[1],ticker:'TSM',market:'US',name:'Synthetic B'}];
    const documents = ids.slice(2,4).map(id=>({id,kind:'source-document',title:id,url:'https://example.test/'+id,
        source:'synthetic',evidence:[],tickers:['000660'],read_revision:1}));
    return {phase:'ready',holdings:[],selectedTickers:['000660','TSM'],graph:{companies,documents,links:[],
        automaticRelations:[{id:ids[4],title:'Synthetic supplier',reported:true,reportedBasis:'business-period',
            participants:[{id:'US:TSM',role:'reported_supplier'}],reason:'fixture',source:'synthetic',read_revision:1}],
        contractEvents:[{id:ids[5],title:'Synthetic contract',participants:[],selectedIds:[],legacyIds:[],
            evidence:[],read_revision:1,correctionCount:0,terminationNoticeCount:0}],
    },privateState:{phase:'ready',revision:16,dirty:false,document:{layouts:[{map_key:'main_v2',positions:[
        {node_id:ids[0],x:8.928571428571402,y:8.095238095238145},
        {node_id:ids[1],x:26.785714285714306,y:8.095238095238145},
        {node_id:ids[5],x:-61.08082459305869,y:-98.46483658028947},
        {node_id:'offscreen:retained',x:123.456,y:-78.9}],
        notes:[{note_id:'note-1',anchor:null,x:13.14,y:71.1,text:'synthetic only',done:false},
            {note_id:'note-2',anchor:{kind:'node',id:'offscreen:retained'},x:10,y:-20,text:'synthetic hidden',done:true}],
        marks:{overview:{read_revision:1,important:true,disposition:'later'}}}]}}};
}
function draft(s){
    const m=model(s),saved=s.privateState.document.layouts.find(l=>l.map_key==='main_v2');
    return {positions:m.nodes.filter(n=>saved.positions.some(p=>p.node_id===n.id)).map(({id,x,y})=>({id,x,y})),
        notes:Object.values(m.notes),marks:{}};
}
function accepted(s,d){
    const next=merge(s,d);assert.ok(next);
    return {...s,privateState:{...s.privateState,document:clone(editMapLayout(s.privateState.document,next.map_key,()=>next))}};
}
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,`${a} != ${b}`);

test('v2 no-op roundtrip preserves raw deltas, unknown positions, notes and marks',()=>{
    const s=fixture(),before=clone(s);
    assert.equal(model(s).nodes.length,6);
    const loaded=accepted(s,draft(s));
    assert.equal(validMapDocument(loaded.privateState.document),true);
    assert.deepEqual(loaded.privateState.document,before.privateState.document);
    assert.deepEqual(s,before);
});
test('existing v2 remains writable at three layouts; latest old-client note and position win',()=>{
    const s=fixture();s.privateState.document.layouts.push(...['other','another'].map(map_key=>({map_key,positions:[],notes:[],marks:{}})));
    const before=clone(s),d=draft(s);assert.equal(model(s).writable,true);
    d.notes[0].text='synthetic latest old tab';d.positions[0].x+=.1;
    const loaded=accepted(s,d),m=model(loaded);
    assert.equal(loaded.privateState.document.layouts.length,3);
    assert.deepEqual(loaded.privateState.document.layouts.slice(1),before.privateState.document.layouts.slice(1));
    assert.equal(Object.values(m.notes)[0].text,d.notes[0].text);
    near(m.nodes.find(n=>n.id===ids[0]).x,d.positions[0].x);
    assert.deepEqual(s,before);
});
test('an alternate layout never masks a later v2 old-client save',()=>{
    const s=fixture();s.privateState.document.layouts.push({map_key:'main_v3',positions:[{node_id:ids[5],x:999,y:999}],
        notes:[{note_id:'obsolete',anchor:null,x:0,y:0,text:'obsolete alternative',done:false}],marks:{}});
    const before=clone(s),d=draft(s);d.positions.find(p=>p.id===ids[5]).x+=.125;
    d.notes[0].text='latest v2 edit';const loaded=accepted(s,d),m=model(loaded);
    near(m.nodes.find(n=>n.id===ids[5]).x,d.positions.find(p=>p.id===ids[5]).x);
    assert.equal(Object.values(m.notes)[0].text,'latest v2 edit');
    assert.deepEqual(loaded.privateState.document.layouts[1],before.privateState.document.layouts[1]);
    assert.deepEqual(s,before);
});

const canvas=fs.readFileSync(path.join(root,'vercel-api/public/member-map-canvas.html'),'utf8');
function section(start,end){
    const a=canvas.indexOf(start),b=canvas.indexOf(end,a);
    assert.ok(a>=0&&b>a);assert.equal(canvas.indexOf(start,a+1),-1);
    return canvas.slice(a,b);
}
const grouping=section('function syncMemberScopedLayout(context,scope){','shown=function(n){return !!n&&ungroupedShown(n)');
const relationship=fs.readFileSync(path.join(root,'review/member-map/prototype-relationship-layout.js'),'utf8').split('const memberRelationshipStyle=')[0];
function runLayout(m,zoom,compactHeight=100,width=1000){
    const nodes=clone(m.nodes),stocks=nodes.filter(n=>n.kind==='stock'),records=nodes.filter(n=>n.kind!=='stock');
    const scope={stocks,records,stockIds:new Set(stocks.map(n=>n.id))},offsets=new Map(),groups=new Map();
    const messages=[];
    const c={nodes,member:{...m,originGeneration:23},memberLocalView:false,memberSaveButton:{},memberPort:{postMessage:m=>messages.push(clone(m))},holdings:stocks,nodeById:Object.fromEntries(nodes.map(n=>[n.id,n])),
        state:{zoom,panX:0,panY:0,focusId:null,selected:null,filter:'all',topic:'all',view:'all',notes:clone(m.notes),marks:{}},
        edges:[],memberLayoutBases:new Map(Object.entries(clone(m.layoutBases))),initialPositions:new Map(),
        focusOffsets:offsets,memberDisplayOffsets:new Map(),memberGroups:groups,
        memberVisible:new Set(),memberEligible:[],memberBaseLayoutKey:'',memberGroupContext:'',memberReveal:'',
        memberDisplayDecisions:new Map(),memberGroupManual:new Set(),memberOpenGroups:new Map(),changeStatus:{},
        memberFocusGroupId:'',memberGroupNames:{},WORLD_WIDTH:1000,WORLD_HEIGHT:680,MEMBER_DEFAULT_BUDGET:12,
        root:{dataset:{},querySelectorAll:()=>[]},space:{clientWidth:width,clientHeight:680},noteEls:new Map(),
        memberScope:()=>scope,ungroupedShown:()=>true,inScenario:()=>true,
        memberCardSize:n=>({width:n.kind==='stock'?160:220,height:n.kind==='stock'?52:c.state.zoom<.65?compactHeight:140}),
        memberDisplayDecision:()=>({mode:'default',evidence:'reported'}),compareMemberDisplay:()=>0,
        memberGroupKey:n=>n.recordKind==='event'?'events':n.layer||'other',
        memberSummaryScale:z=>Math.max(.08,Math.min(4,z)),eventHoldings:()=>stocks.map(n=>n.id),
        viewPosition:n=>({x:n.x+(offsets.get(n.id)?.x||0),y:n.y+(offsets.get(n.id)?.y||0)}),
        // Notes are serialization fixtures here, not measured browser obstacles.
        noteVisible:()=>false,layoutSnapshot:()=>({}),recordMove(){},travelHistory(){},clearFocus(){},
        makeMemberGroup:key=>{
            const g={key,records:[],recordShifts:new Map(),dx:0,dy:0,baseX:.5,baseY:.5,
                button:{hidden:false,offsetWidth:240,offsetHeight:90,setAttribute(){}},
                more:{hidden:true,offsetWidth:120,offsetHeight:32},title:{},count:{},hint:{},
                get x(){return this.baseX+this.dx},get y(){return this.baseY+this.dy}};
            groups.set(key,g);return g;
        },
    };
    const draftRuntime=section('let memberWritable=','function emitMemberDraft(force=false){');
    vm.createContext(c);vm.runInContext(grouping+'\n'+draftRuntime+'\n'+relationship+'\nthis.prepare=prepareMemberGroups;',c);
    c.prepare();return {c,nodes,messages,centers:()=>Object.fromEntries(nodes.map(n=>[n.id,c.viewPosition(n)]))};
}
const delta=(a,b,id)=>({x:(b[id].x-a[id].x)*1000,y:(b[id].y-a[id].y)*680});
test('generated origins: same-session compacting preserves manual center; fresh compact initialization differs',()=>{
    const s=fixture(),before=clone(s),m=model(s),first=runLayout(m,.73),centers=first.centers();
    const loaded=model(accepted(s,draft(s))),same=runLayout(loaded,.73);
    assert.deepEqual(same.centers(),centers,'same dimensions reload exactly');
    first.c.state.zoom=.49;first.c.prepare();const compact=runLayout(loaded,.49);
    const sessionDelta=delta(centers,first.centers(),ids[5]),freshDelta=delta(centers,compact.centers(),ids[5]);
    near(sessionDelta.x,0);near(sessionDelta.y,0);near(freshDelta.x,0);near(freshDelta.y,-20);
    for(const id of ids.slice(0,2)){const d=delta(centers,compact.centers(),id);near(d.x,0);near(d.y,0);}
    assert.deepEqual(first.nodes,clone(m.nodes));assert.deepEqual(compact.nodes,clone(loaded.nodes));assert.deepEqual(s,before);
});
test('constant synthetic card dimensions remove this initialization difference, without rewriting saved deltas',()=>{
    const m=model(fixture()),detail=runLayout(m,.73),compact=runLayout(m,.49,140);
    assert.deepEqual(compact.centers(),detail.centers());assert.deepEqual(compact.nodes,clone(m.nodes));
});
test('constant dimensions preserve this six-node fixture across zoom, filter and narrow reload only',()=>{
    const s=fixture(),before=clone(s),m=model(s),first=runLayout(m,.73,140,1280),centers=first.centers();
    first.c.state.zoom=.49;first.c.state.filter='supply';first.c.prepare();
    const loaded=model(accepted(s,draft(s))),reload=runLayout(loaded,.49,140,390);
    for(const id of [ids[0],ids[1],ids[5]]){
        assert.deepEqual(first.centers()[id],centers[id]);assert.deepEqual(reload.centers()[id],centers[id]);
    }
    assert.deepEqual(first.nodes,clone(m.nodes));assert.deepEqual(reload.nodes,clone(loaded.nodes));
    assert.deepEqual(s,before);
});
test('constant dimensions do not preserve the legacy manual origin when a new category enters the graph',()=>{
    const s=fixture(),before=clone(s),m=model(s),first=runLayout(m,.73,140),centers=first.centers();
    const changed=clone(m),extra={...changed.nodes.find(n=>n.id===ids[2]),id:'synthetic:new-category',layer:'news',x:.5,y:.5};
    changed.nodes.push(extra);changed.layoutBases[extra.id]={x:.5,y:.5};
    const reload=runLayout(changed,.73,140),d=delta(centers,reload.centers(),ids[5]);
    near(d.x,-176);near(d.y,0);
    for(const id of ids.slice(0,2))assert.deepEqual(reload.centers()[id],centers[id]);
    assert.deepEqual(reload.nodes.find(n=>n.id===ids[5]),clone(m.nodes.find(n=>n.id===ids[5])));
    assert.deepEqual(s,before,'no stored field changes despite the displayed displacement');
});
function capturesFor(s){
    const m=model(s),run=runLayout(m,.73),centers=run.centers();
    return m.nodes.filter(n=>m.savedPositionIds.includes(n.id)).map(n=>({id:n.id,x:(centers[n.id].x-(n.x-.5))*1000,y:(centers[n.id].y-(n.y-.5))*680,raw:{x:n.x,y:n.y}}));
}
test('optional origins preserve raw values, notes, marks and all three layouts on explicit save',()=>{
    const s=fixture();s.privateState.document.layouts.push(...['other','another'].map(map_key=>({map_key,positions:[],notes:[],marks:{}})));
    const before=clone(s),next=candidate.mergePrototypeOriginSave(s,draft(s),capturesFor(s));assert.ok(next);
    assert.equal(next.origins.length,3);assert.equal(next.positions.length,4);
    for(const p of before.privateState.document.layouts[0].positions)assert.deepEqual(clone(next.positions.find(n=>n.node_id===p.node_id)),p);
    assert.deepEqual(clone(next.notes),before.privateState.document.layouts[0].notes);assert.deepEqual(clone(next.marks),before.privateState.document.layouts[0].marks);
    assert.equal(candidate.validMapDocument({layouts:[next,...s.privateState.document.layouts.slice(1)]}),true);
    assert.deepEqual(s,before);
});
test('origin contract rejects stale raw captures, unknown IDs, duplicates, nonfinite values and mismatched binding',()=>{
    const s=fixture(),before=clone(s),captures=capturesFor(s);
    for(const mutate of [c=>c[0].raw.x+=.001,c=>c[0].id='unknown',c=>c.push(c[0]),c=>c[0].x=Infinity]){
        const changed=clone(captures);mutate(changed);assert.equal(candidate.mergePrototypeOriginSave(s,draft(s),changed),null);
    }
    const next=clone(candidate.mergePrototypeOriginSave(s,draft(s),captures));next.origins[0].dx+=1;
    assert.equal(candidate.validMapDocument({layouts:[next]}),false);assert.deepEqual(s,before);
    for(const position of [null,undefined,3,'invalid',{}]){
        const malformed=clone(candidate.mergePrototypeOriginSave(s,draft(s),captures));malformed.positions[0]=position;
        assert.doesNotThrow(()=>assert.equal(candidate.validMapDocument({layouts:[malformed]}),false));
    }
});
test('origin save retains 200 real positions; an extra explicit movement fails without dropping data',()=>{
    const s=fixture(),l=s.privateState.document.layouts[0];while(l.positions.length<200)l.positions.push({node_id:'retained:'+l.positions.length,x:1,y:2});
    const before=clone(s);assert.ok(candidate.mergePrototypeOriginSave(s,draft(s),capturesFor(s)));
    const d=draft(s),n=model(s).nodes.find(n=>n.id===ids[4]);d.positions.push({id:n.id,x:n.x+.1,y:n.y});
    assert.equal(candidate.mergePrototypeOriginSave(s,d,capturesFor(s)),null);assert.deepEqual(s,before);
});
test('actual Save hook emits one atomic capture; reload survives changed graph and dimensions',()=>{
    const s=fixture(),m=model(s),first=runLayout(m,.73),before=clone(s);
    first.nodes.find(n=>n.id===ids[2]).x+=.12;first.nodes.find(n=>n.id===ids[0]).x+=.03;
    first.nodes.find(n=>n.id===ids[4]).y+=.2;first.c.prepare();
    const centers=first.centers();assert.equal(first.messages.length,0,'hydration/layout does not emit a save');
    first.c.memberSaveButton.onclick();assert.equal(first.messages.length,1);
    const message=first.messages[0];assert.equal(message.type,'save');assert.equal(message.originGeneration,23);
    for(const id of [ids[0],ids[2],ids[4],ids[5]])assert.ok(message.origins.some(o=>o.id===id));
    const saved=candidate.mergePrototypeOriginSave(s,message.draft,message.origins);assert.ok(saved);
    const next={...s,privateState:{...s.privateState,document:{layouts:[clone(saved)]}}},loaded=model(next);
    assert.equal(Object.keys(loaded.positionOrigins).length,saved.origins.length);
    loaded.nodes.push({...loaded.nodes.find(n=>n.id===ids[2]),id:'new-category',layer:'news',x:.5,y:.5});loaded.layoutBases['new-category']={x:.5,y:.5};
    const reload=runLayout(loaded,.49,100,390);
    for(const o of saved.origins){near(reload.centers()[o.node_id].x,centers[o.node_id].x);near(reload.centers()[o.node_id].y,centers[o.node_id].y);}
    assert.deepEqual(clone(saved.notes),before.privateState.document.layouts[0].notes);assert.deepEqual(s,before);
    vm.runInContext('memberApplyingGraph=true',first.c);first.c.memberSaveButton.onclick();assert.equal(first.messages.length,1,'graph generation gate prevents stale save');
    vm.runInContext('memberApplyingGraph=false;memberWritable=false',first.c);first.c.memberSaveButton.onclick();assert.equal(first.messages.length,1,'readonly prevents save');
});

test('201 generated materials do not consume positions; an explicitly saved zero delta still gets an origin',()=>{
    const s=fixture(),l=s.privateState.document.layouts[0];l.positions.push({node_id:ids[4],x:0,y:0});
    s.graph.documents.push(...Array.from({length:201},(_,i)=>({...s.graph.documents[0],id:'generated:'+i})));
    const before=clone(s),run=runLayout(model(s),.73);run.c.memberSaveButton.onclick();
    const message=run.messages[0],saved=candidate.mergePrototypeOriginSave(s,message.draft,message.origins);
    assert.ok(saved);assert.equal(saved.positions.length,5);assert.equal(saved.origins.length,4);
    assert.ok(saved.origins.some(o=>o.node_id===ids[4]&&o.dx===0&&o.dy===0));
    assert.equal(saved.positions.some(p=>p.node_id.startsWith('generated:')),false);
    assert.deepEqual(clone(saved.notes),l.notes);assert.deepEqual(s,before);
});

test('moved then filter-hidden card captures its observed origin; unseen legacy records are not guessed',()=>{
    const s=fixture(),before=clone(s),run=runLayout(model(s),.73);
    run.nodes.find(n=>n.id===ids[4]).y+=.2;run.c.prepare();
    const displayed=run.centers()[ids[4]],scope=run.c.memberScope();
    run.c.memberScope=()=>({...scope,records:scope.records.filter(n=>n.id!==ids[4])});
    run.c.state.filter='other';run.c.prepare();assert.equal(run.c.memberVisible.has(ids[4]),false);
    run.c.memberSaveButton.onclick();const message=run.messages[0];
    assert.ok(message.origins.some(o=>o.id===ids[4]));
    assert.equal(message.origins.some(o=>o.id==='offscreen:retained'),false);
    const saved=candidate.mergePrototypeOriginSave(s,message.draft,message.origins);assert.ok(saved);
    const next=clone(s);next.privateState.document.layouts=[clone(saved)];const reload=runLayout(model(next),.49,100,390);
    near(reload.centers()[ids[4]].x,displayed.x);near(reload.centers()[ids[4]].y,displayed.y);
    assert.deepEqual(clone(saved.positions.find(p=>p.node_id==='offscreen:retained')),before.privateState.document.layouts[0].positions[3]);
    assert.deepEqual(s,before);
});

test('ordinary note edit retains bound origins; changed raw delta invalidates only that origin without inventing replacements',()=>{
    const s=fixture(),saved=candidate.mergePrototypeOriginSave(s,draft(s),capturesFor(s));
    s.privateState.document.layouts=[clone(saved)];const before=clone(s),d=draft(s);d.notes[0].text='latest synthetic edit';
    const notesOnly=merge(s,d);assert.deepEqual(clone(notesOnly.origins),clone(saved.origins));
    d.positions[0].x+=.1;const moved=merge(s,d);
    assert.equal(moved.origins.some(o=>o.node_id===ids[0]),false);
    assert.equal(moved.origins.length,saved.origins.length-1);assert.equal(moved.notes[0].text,d.notes[0].text);
    const stale=clone(s);stale.privateState.document.layouts[0].positions[0].x+=1;
    assert.equal(Object.hasOwn(model(stale).positionOrigins,ids[0]),false);
    assert.deepEqual(s,before);
});

test('actual parent bridge applies an atomic origin save once, rejects stale generations and keeps failed drafts unsaved',async()=>{
    let current=fixture(),subscriber,nonce=0,edits=0,saves=0;const before=clone(current),listeners={},channels=[],messages=[];
    const window={location:{href:'https://fixture.test/review',origin:'https://fixture.test'},addEventListener:(t,f)=>listeners[t]=f,removeEventListener:t=>delete listeners[t]};
    class Channel{constructor(){this.port1={postMessage:m=>messages.push(clone(m)),close(){}};this.port2={};channels.push(this);}}
    const module={exports:{}};
    vm.runInNewContext(esbuild.transformSync(source+'\nexport {mountMemberPrototype};',{loader:'tsx',format:'cjs',target:'es2022'}).code,{
        module,exports:module.exports,require:name=>name==='react'?{}:{addPropertyControls(){},ControlType:{Number:'number'}},
        window,URL,AbortController,TextEncoder,MessageChannel:Channel,crypto:{randomUUID:()=>String(++nonce)},
    });
    const frame={style:{},contentWindow:{postMessage(){}},setAttribute(){},removeAttribute(){},addEventListener(){},removeEventListener(){}};
    const workspace={getState:()=>clone(current),subscribe:f=>{subscriber=f;f(clone(current));return()=>{}},
        editLayout:(key,fn)=>{edits++;current.privateState.document=clone(editMapLayout(current.privateState.document,key,fn));current.privateState.dirty=true;subscriber(clone(current));return true},
        save:async()=>{saves++;return true}};
    const bridge=module.exports.mountMemberPrototype(frame,"'__ALPHANEST_FRAME_NONCE__'",workspace,{account:()=> 'synthetic'});
    listeners.message({source:frame.contentWindow,origin:'null',data:{type:'alphanest-member-ready',nonce:JSON.parse(frame.srcdoc)}});
    const port=channels.at(-1).port1,generation=messages.findLast(m=>m.type==='init').model.originGeneration;
    await port.onmessage({data:{type:'hydrated',originGeneration:generation}});
    const run=runLayout(model(current),.73);run.c.memberSaveButton.onclick();const command=run.messages[0];command.originGeneration=generation;
    await port.onmessage({data:{...command,originGeneration:generation-1}});assert.equal(edits,0);assert.equal(saves,0);
    await port.onmessage({data:command});assert.equal(edits,1);assert.equal(saves,1);
    assert.equal(current.privateState.document.layouts[0].origins.length,3);
    assert.deepEqual(current.privateState.document.layouts[0].notes,before.privateState.document.layouts[0].notes);
    const saved=clone(current),bad=clone(command);bad.origins[0].raw.x+=1;
    await port.onmessage({data:bad});assert.equal(edits,1);assert.equal(saves,1);assert.deepEqual(current,saved);
    assert.match(messages.at(-1).message,/origin_capture/);bridge();
});

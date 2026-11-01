// Relationship-centered presentation. Neither canonical coordinates nor private
// notes/marks are rewritten: automatic sources use the existing evidence list.
function memberRelationshipIsMapRecord(n){
  return !!n&&n.layer!=='candidates'&&(n.recordKind==='event'||n.recordKind==='relationship'&&n.layer==='relationships');
}
function memberRelationshipOverviewNodes(){
  return nodes.filter(n=>n.kind==='event'&&shown(n)).map(n=>({id:n.id,n,el:nodesEl.querySelector('[data-node="'+n.id+'"]')}));
}
function memberRelationshipSlotsFor(records,stocks,obstacles=[],prior=new Map()){
  const gap=24,placed=new Map(),occupied=obstacles.map(b=>({...b})),segments=[];
  const rect=p=>({left:p.x-p.width/2,right:p.x+p.width/2,top:p.y-p.height/2,bottom:p.y+p.height/2});
  const hits=(a,b)=>a.left<b.right+gap&&a.right>b.left-gap&&a.top<b.bottom+gap&&a.bottom>b.top-gap;
  const stockRects=stocks.map(s=>({...rect(s),id:s.id}));occupied.push(...stockRects);
  const peers=r=>stocks.filter(s=>(r.stockIds||[]).includes(s.id));
  const reserve=(r,p)=>{placed.set(r.id,p);occupied.push(rect(p));for(const stock of peers(r))segments.push({a:p,b:stock});};
  const order=new Map([...prior.keys()].map((id,i)=>[id,i]));
  const existing=records.filter(r=>prior.has(r.id)).sort((a,b)=>order.get(a.id)-order.get(b.id)),fresh=records.filter(r=>!prior.has(r.id)),displaced=[];
  // Reserve safe established slots before allocating any additions. New records
  // cannot push earlier expanded cards, manual obstacles or stock anchors away.
  for(const r of existing){
    const p={...prior.get(r.id),width:r.width,height:r.height};
    if(occupied.some(o=>hits(rect(p),o)))displaced.push(r);else reserve(r,p);
  }
  const turn=(a,b,c)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
  const crosses=(a,b,c,d)=>turn(a,b,c)*turn(a,b,d)<-1e-6&&turn(c,d,a)*turn(c,d,b)<-1e-6;
  const through=(a,b,box)=>{
    const corners=[{x:box.left,y:box.top},{x:box.right,y:box.top},{x:box.right,y:box.bottom},{x:box.left,y:box.bottom}];
    return corners.some((c,i)=>crosses(a,b,c,corners[(i+1)%4]));
  };
  for(const r of [...displaced,...fresh]){
    const linked=peers(r),anchors=linked.length?linked:stocks;
    const home={x:anchors.length?anchors.reduce((sum,s)=>sum+s.x,0)/anchors.length:500,y:anchors.length?anchors.reduce((sum,s)=>sum+s.y,0)/anchors.length:340};
    const stepX=r.width+gap,stepY=r.height+gap,candidates=[];
    const add=(x,y)=>candidates.push({x,y,width:r.width,height:r.height});
    add(home.x,home.y);
    // Adjacent faces of actual participants are usually closer than a free
    // lattice cell. Four directions prevent the old downward-only tower.
    for(const stock of anchors){
      add(stock.x-stock.width/2-gap-r.width/2,stock.y);add(stock.x+stock.width/2+gap+r.width/2,stock.y);
      add(stock.x,stock.y-stock.height/2-gap-r.height/2);add(stock.x,stock.y+stock.height/2+gap+r.height/2);
    }
    let best=null,bestCost=Infinity;
    const cost=p=>{
      const box=rect(p),all=[...occupied,box];
      const width=Math.max(...all.map(o=>o.right))-Math.min(...all.map(o=>o.left)),height=Math.max(...all.map(o=>o.bottom))-Math.min(...all.map(o=>o.top));
      let value=Math.hypot(p.x-home.x,p.y-home.y)+width*.12+height*.24;
      if(linked.length)value+=linked.reduce((sum,stock)=>sum+Math.hypot(p.x-stock.x,p.y-stock.y),0)/linked.length;
      for(const stock of linked){
        value+=segments.filter(line=>line.b.id!==stock.id&&crosses(p,stock,line.a,line.b)).length*120;
        value+=stockRects.filter(o=>o.id!==stock.id&&through(p,stock,o)).length*240;
      }
      return value;
    };
    const consider=()=>{for(const p of candidates.splice(0)){if(occupied.some(o=>hits(rect(p),o)))continue;const score=cost(p);if(score<bestCost){best=p;bestCost=score;}}};
    consider();
    // Finite outward rings, then compare one more ring after finding a free
    // candidate. Geometry/order alone determines ties; there is no simulation.
    let foundRing=best?0:null;
    for(let ring=1;ring<=occupied.length+2;ring++){
      for(let x=-ring;x<=ring;x++){add(home.x+x*stepX,home.y-ring*stepY);add(home.x+x*stepX,home.y+ring*stepY);}
      for(let y=-ring+1;y<ring;y++){add(home.x-ring*stepX,home.y+y*stepY);add(home.x+ring*stepX,home.y+y*stepY);}
      consider();if(best&&foundRing===null)foundRing=ring;if(foundRing!==null&&ring>=foundRing+1)break;
    }
    // A finite obstacle family always has space beyond its rightmost bound.
    if(!best)best={x:Math.max(home.x,...occupied.map(o=>o.right))+gap+r.width/2,y:home.y,width:r.width,height:r.height};
    reserve(r,best);
  }
  return placed;
}
const memberRelationshipSlots=new Map();
let memberRelationshipContext='';
const relationshipSnapshot=layoutSnapshot,relationshipRecordMove=recordMove,relationshipTravelHistory=travelHistory;
layoutSnapshot=function(){
  const snapshot=relationshipSnapshot();
  snapshot.relationshipSlots=new Map(nodes.filter(n=>n.kind==='event'&&memberVisible.has(n.id)).map(n=>{const p=viewPosition(n),s=memberCardSize(n);return [n.id,{x:p.x*WORLD_WIDTH,y:p.y*WORLD_HEIGHT,...s}];}));
  return snapshot;
};
recordMove=function(before,label,options={}){
  const prior=moveHistory.past.at(-1);relationshipRecordMove(before,label,options);
  const entry=moveHistory.past.at(-1);if(!entry)return;
  if(entry!==prior)entry.relationshipBefore=before.relationshipSlots;
  if(entry!==prior||options.repeat)entry.relationshipAfter=layoutSnapshot().relationshipSlots;
};
travelHistory=function(redo){
  if(cancelGesture)return;
  const entry=(redo?moveHistory.future:moveHistory.past).at(-1),slots=redo?entry?.relationshipAfter:entry?.relationshipBefore;
  if(slots){memberRelationshipSlots.clear();for(const [id,p] of slots)memberRelationshipSlots.set(id,p);}
  relationshipTravelHistory(redo);
};
function memberRelationshipBasesFor(records,stocks){
  const ordered=records.slice().sort((a,b)=>a.id.localeCompare(b.id));
  const relationships=ordered.filter(r=>r.isRelationship),sources=ordered.filter(r=>!r.isRelationship);
  const bases=memberRelationshipSlotsFor(relationships,stocks);
  const bottom=Math.max(340,...stocks.map(s=>s.y+s.height/2),...[...bases.values()].map(p=>p.y+p.height/2));
  const center=stocks.length?stocks.reduce((sum,s)=>sum+s.x,0)/stocks.length:500;
  // Source material lives in the library, not in 100 reserved canvas rows.
  // Explicit pins start at this shared home; the visible-slot pass separates
  // them, and an explicit drag records that presentation delta before moving.
  sources.forEach(r=>bases.set(r.id,{x:center,y:bottom+70+r.height/2,width:r.width,height:r.height}));
  return bases;
}
let memberRelationshipBases=new Map();
// First fresh grouping origin, not a reconstruction of an unsaved prior session.
// Store the absolute origin so a later model-origin rebase keeps the same view.
const memberRelationshipLegacyOrigins=new Map();
function memberRelationshipCaptureLegacyOrigins(scope){
  for(const n of [...scope.stocks,...scope.records]){
    if(memberRelationshipLegacyOrigins.has(n.id))continue;
    const offset=focusOffsets.get(n.id);if(!offset)continue;
    const base=memberLayoutBases.get(n.id)||initialPositions.get(n.id)||n;
    memberRelationshipLegacyOrigins.set(n.id,{x:base.x+offset.x,y:base.y+offset.y});
  }
}
function memberRelationshipRebaseMovement(id){
  const n=nodeById[id],p=memberRelationshipBases.get(id),legacy=memberRelationshipLegacyOrigins.get(id);if(!n)return;
  if(n.kind!=='stock'&&(legacy||p)){
    const base=memberLayoutBases.get(id)||initialPositions.get(id)||n,offset=focusOffsets.get(id)||{x:0,y:0};
    const next=legacy?{x:legacy.x-base.x,y:legacy.y-base.y}:{x:p.x/WORLD_WIDTH-base.x,y:p.y/WORLD_HEIGHT-base.y};
    // Only an explicit move converts a collision-avoidance offset into saved
    // movement. Fresh grouping origins, not lost prior-session slots, own reload.
    n.x+=offset.x-next.x;n.y+=offset.y-next.y;
    memberDisplayOffsets.set(id,next);focusOffsets.set(id,next);
  }
  if(typeof memberOverviewRebaseMovement==='function')memberOverviewRebaseMovement(id);
}
moveWithKeys=function(e,id){
  const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
  if(!delta||cancelGesture||!memberWritable)return;
  e.preventDefault();e.stopPropagation();
  const before=layoutSnapshot(),step=e.shiftKey?20:8,entries=movableItems().filter(entry=>selectedItems.has(id)?selectedItems.has(entry.id):entry.id===id);
  for(const entry of entries){memberRelationshipRebaseMovement(entry.id);entry.item.x+=delta[0]*step/(WORLD_WIDTH*state.zoom);entry.item.y+=delta[1]*step/(WORLD_HEIGHT*state.zoom);}
  recordMove(before,'항목 이동을',{key:e.key+':'+entries.map(entry=>entry.id).sort().join(','),repeat:e.repeat});renderMap();
};
function memberRelationshipMovedIds(scope){
  const ids=new Set();
  for(const n of [...scope.stocks,...scope.records]){
    const base=memberLayoutBases.get(n.id)||initialPositions.get(n.id)||n;
    if(Math.abs(n.x-base.x)>1e-9||Math.abs(n.y-base.y)>1e-9)ids.add(n.id);
  }
  return ids;
}
function memberRelationshipPinnedIds(scope){
  const ids=memberRelationshipMovedIds(scope);
  for(const note of Object.values(state.notes)){
    if(nodeById[note.target])ids.add(note.target);
    const edge=edges.find(e=>e.id===note.target);if(edge){ids.add(edge.from);ids.add(edge.to);}
  }
  return ids;
}
function prepareMemberRelationshipPins(scope){
  for(const id of memberRelationshipPinnedIds(scope))if(scope.stockIds.has(id)||scope.records.some(n=>n.id===id))memberVisible.add(id);
}
function memberRelationshipAlias(n,records){
  if(n.recordKind!=='relationship')return null;
  const peers=eventHoldings(n).slice().sort().join('|'),urls=new Set((n.evidence||[]).map(e=>e.url).filter(Boolean));
  if(!urls.size)return null;
  return records.find(other=>other.recordKind==='event'&&other.asOf===n.asOf&&eventHoldings(other).slice().sort().join('|')===peers
    &&(other.evidence||[]).some(e=>urls.has(e.url)))||null;
}
function applyMemberRelationshipLayout(scope){
  memberRelationshipCaptureLegacyOrigins(scope);
  const context=[memberBaseLayoutKey,state.focusId,state.filter,state.topic,state.view].join('|');
  if(memberRelationshipContext!==context){memberRelationshipSlots.clear();memberRelationshipContext=context;}
  const pinned=memberRelationshipPinnedIds(scope),moved=memberRelationshipMovedIds(scope),selectedEdge=edges.find(e=>e.id===state.selected);
  // Restore manual stock anchors before using them as automatic-card obstacles.
  for(const n of [...scope.stocks,...scope.records].filter(n=>moved.has(n.id))){
    const legacy=memberRelationshipLegacyOrigins.get(n.id),base=memberLayoutBases.get(n.id)||initialPositions.get(n.id)||n;
    if(legacy){const offset={x:legacy.x-base.x,y:legacy.y-base.y};memberDisplayOffsets.set(n.id,offset);focusOffsets.set(n.id,offset);}
  }
  const selected=new Set([state.selected,...(selectedEdge?[selectedEdge.from,selectedEdge.to]:[])]);
  const candidates=scope.records.filter(n=>memberRelationshipIsMapRecord(n)&&memberDisplayDecisions.get(n.id)?.evidence==='reported'
    &&memberDisplayDecisions.get(n.id)?.mode!=='detail');
  const ranked=candidates.filter(n=>!memberRelationshipAlias(n,candidates)||pinned.has(n.id)||selected.has(n.id))
    .sort((a,b)=>compareMemberDisplay(memberDisplayDecisions.get(a.id),memberDisplayDecisions.get(b.id)));
  // A browsing budget is not an economic grade. Explicit selections, notes and
  // manually placed records remain accessible even outside the initial budget.
  const visible=new Set([...scope.stocks.map(n=>n.id),...ranked.slice(0,MEMBER_DEFAULT_BUDGET).map(n=>n.id)]);
  for(const n of scope.records)if(pinned.has(n.id)||selected.has(n.id)&&memberRelationshipIsMapRecord(n)||state.marks[n.id]?.important)visible.add(n.id);
  memberVisible=visible;
  for(const g of memberGroups.values()){g.button.hidden=true;g.more.hidden=true;}
  const world=n=>{const p=viewPosition(n),s=memberCardSize(n);return {id:n.id,x:p.x*WORLD_WIDTH,y:p.y*WORLD_HEIGHT,...s};};
  const rect=p=>({left:p.x-p.width/2,right:p.x+p.width/2,top:p.y-p.height/2,bottom:p.y+p.height/2});
  const stocks=scope.stocks.map(world),obstacles=[];
  // Filters decide visibility, never the basis interpreting saved movement.
  const baseStocks=holdings.map(n=>{const p=world(n),base=memberLayoutBases.get(n.id)||initialPositions.get(n.id)||n;return {...p,x:p.x-(n.x-base.x)*WORLD_WIDTH,y:p.y-(n.y-base.y)*WORLD_HEIGHT};});
  memberRelationshipBases=memberRelationshipBasesFor(nodes.filter(n=>n.kind==='event').map(n=>({...world(n),stockIds:eventHoldings(n),isRelationship:memberRelationshipIsMapRecord(n)})),baseStocks);
  for(const n of scope.records.filter(n=>visible.has(n.id)&&moved.has(n.id)))obstacles.push(rect(world(n)));
  for(const note of Object.values(state.notes)){
    if(!noteVisible(note))continue;
    const p=noteAnchor(note),z=Math.max(.08,state.zoom),el=noteEls.get(note.id);
    const x=WORLD_WIDTH/2+(p.x-space.clientWidth/2-state.panX)/z,y=WORLD_HEIGHT/2+(p.y-space.clientHeight/2-state.panY)/z;
    // Free notes share the map scale; attached notes remain small annotations
    // on their already-reserved owner, not independently placed source cards.
    if(!note.target)obstacles.push(rect({x,y,width:el?.offsetWidth||150,height:el?.offsetHeight||64}));
  }
  const automatic=scope.records.filter(n=>visible.has(n.id)&&!moved.has(n.id)).map(n=>({...world(n),stockIds:eventHoldings(n)}));
  const prior=new Map(automatic.map(n=>[n.id,memberRelationshipSlots.get(n.id)||memberRelationshipBases.get(n.id)]));
  const slots=memberRelationshipSlotsFor(automatic,stocks,obstacles,prior);
  for(const [id,p] of slots){
    const n=nodeById[id],offset={x:p.x/WORLD_WIDTH-n.x,y:p.y/WORLD_HEIGHT-n.y};
    memberRelationshipSlots.set(id,p);memberDisplayOffsets.set(id,offset);focusOffsets.set(id,offset);
  }
}
// Origins are accepted by the parent only when bound to the saved raw delta.
// Legacy records still use the first current-session grouping origin above.
const memberRelationshipObservedOrigins=new Map();
const relationshipObserveLayout=applyMemberRelationshipLayout;
applyMemberRelationshipLayout=function(scope){
  relationshipObserveLayout(scope);
  for(const n of [...scope.stocks,...scope.records].filter(n=>memberVisible.has(n.id))){
    const p=viewPosition(n),base=memberLayoutBases.get(n.id)||initialPositions.get(n.id)||n;
    memberRelationshipObservedOrigins.set(n.id,{x:p.x-(n.x-base.x),y:p.y-(n.y-base.y)});
  }
};
const memberRelationshipSavedOriginIds=new Set();
const memberRelationshipSavedPositionIds=new Set(typeof member==='undefined'?[]:member.savedPositionIds||[]);
function memberRelationshipRestoreOrigins(model,existingIds=new Set()){
  for(const [id,p] of Object.entries(model?.positionOrigins||{})){
    if(existingIds.has(id)||!Number.isFinite(p?.x)||!Number.isFinite(p?.y))continue;
    memberRelationshipLegacyOrigins.set(id,{x:p.x,y:p.y});memberRelationshipSavedOriginIds.add(id);
  }
}
if(typeof member!=='undefined')memberRelationshipRestoreOrigins(member);
const relationshipMovedIds=memberRelationshipMovedIds;
memberRelationshipMovedIds=function(scope){
  const ids=relationshipMovedIds(scope);
  for(const n of [...scope.stocks,...scope.records])if(memberRelationshipSavedOriginIds.has(n.id))ids.add(n.id);
  return ids;
};
function memberRelationshipCaptureSaveOrigins(){
  // Only existing positions and explicit movement consume the position budget.
  // An untouched generated card is not a saved pin, even when visible.
  return nodes.filter(n=>memberRelationshipSavedPositionIds.has(n.id)||memberPositionEdits.has(n.id)).flatMap(n=>{
    const base=memberLayoutBases.get(n.id)||initialPositions.get(n.id)||{x:.5,y:.5};
    const p=memberVisible.has(n.id)?viewPosition(n):null;
    const origin=p?{x:p.x-(n.x-base.x),y:p.y-(n.y-base.y)}:memberRelationshipObservedOrigins.get(n.id);
    // Hidden cards use only a prior actual presentation, never a fresh guess.
    return origin?[{id:n.id,x:origin.x*WORLD_WIDTH,y:origin.y*WORLD_HEIGHT,raw:{x:n.x,y:n.y}}]:[];
  });
}
if(typeof updateMemberGraph==='function'){
  const relationshipUpdate=updateMemberGraph;
  updateMemberGraph=function(model,ticker){
    // Existing nodes may contain unsaved movement. Never replace their origins.
    memberRelationshipRestoreOrigins(model,new Set(nodes.map(n=>n.id)));
    for(const id of model.savedPositionIds||[])memberRelationshipSavedPositionIds.add(id);
    return relationshipUpdate(model,ticker);
  };
}
if(typeof memberSaveButton!=='undefined')memberSaveButton.onclick=()=>{
  if(memberApplyingGraph||!memberWritable)return;
  memberPort.postMessage({type:'save',draft:memberDraft(),origins:memberRelationshipCaptureSaveOrigins(),...memberOriginStamp()});
};
// Graph stage geometry is independent of the reading panel. Toggling the
// panel never calls fit/layout/save or replaces an in-progress note editor.
const memberRelationshipStyle=document.createElement('style');memberRelationshipStyle.textContent=`
#an-map-design{--an-bg:light-dark(#f8f9fb,#1d242c);--an-panel:light-dark(#ffffff,#171c23);--an-text:light-dark(#191f28,#e3e7ec);--an-sub:light-dark(#6b7684,#9aa4b1);--an-accent:light-dark(#6c5ce7,#a99bff);--an-soft:light-dark(#e9edf2,#303945)}
#an-map-design .an-body{display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(180px,1fr);grid-template-areas:'map';position:relative}
#an-map-design .an-map{grid-area:map;min-width:0;min-height:0}
#an-map-design .an-relation-panel{position:absolute;z-index:6;top:var(--an-relation-panel-top,8px);right:8px;bottom:8px;width:320px;max-width:calc(100% - 16px);display:flex;flex-direction:column;min-height:0;overflow:hidden;border-radius:18px;background:var(--an-panel);box-shadow:0 4px 16px var(--an-shadow)}
#an-map-design .an-relation-panel-head{display:flex;align-items:center;gap:4px;flex:none;padding:8px}
#an-map-design .an-relation-panel-head button{min-height:44px;padding:8px 12px;border-radius:10px;font-size:12px;font-weight:700}
#an-map-design .an-relation-panel-head [data-relation-tab][aria-pressed=true]{background:var(--an-soft)}
#an-map-design .an-relation-panel-head .an-relation-close{margin-left:auto;min-width:44px}
#an-map-design .an-relation-panel .an-inbox{display:block!important;flex:1;min-height:0;min-width:0;padding:12px;overflow:auto;background:var(--an-panel);scrollbar-gutter:stable}
#an-map-design .an-relation-panel :is(.an-inbox,.an-detail)[hidden]{display:none!important}
#an-map-design .an-relation-panel .an-inbox>h3{margin:0 8px 12px;font-size:14px;font-weight:800}
#an-map-design .an-relation-panel .an-inbox>[data-member-list]{margin:0 0 10px;box-shadow:none;background:var(--an-bg)}
#an-map-design .an-relation-panel .an-inbox>[data-member-list]>summary{min-height:44px;padding:10px 12px}
#an-map-design .an-relation-panel .an-inbox>[data-member-list]>[data-select]{display:block;text-align:left;width:calc(100% - 16px);padding:10px 12px;font-size:12px;white-space:normal;overflow-wrap:anywhere}
#an-map-design .an-relation-panel [data-select] strong{display:block;white-space:normal;font-size:13px;line-height:1.55;font-weight:700}
#an-map-design .an-relation-panel [data-select] small{display:block;font-size:11px;font-weight:600;line-height:1.55;margin-top:4px}
#an-map-design .an-relation-panel .an-detail{position:static;display:block;flex:1;min-height:0;min-width:0;width:auto;height:auto;max-height:none;padding:20px;border-radius:0;box-shadow:none;overflow:auto;background:var(--an-panel)}
#an-map-design .an-relation-panel .an-aside-note{font-size:11px;font-weight:600;line-height:1.6}
#an-map-design .an-note-marker[data-free=true]{transform:translate(-50%,-50%) scale(var(--an-relationship-zoom,1))}
#an-map-design #an-member-groups,#an-map-design #an-member-sections{visibility:hidden;pointer-events:none}
#an-map-design #an-nodes .an-node[data-overview-title=true] .an-category-icon{width:18px;height:18px;flex-basis:18px}
#an-map-design #an-nodes .an-node.event[data-overview-title=true] :is(.an-record-category,.an-record-date,.an-record-criteria,.an-relation-summary){display:none!important}
#an-map-design #an-nodes .an-node.event[data-overview-title=true] strong{display:block!important;white-space:nowrap!important;line-height:18px!important;-webkit-line-clamp:unset}
#an-map-design :is(button,select,input,textarea,a,summary):focus-visible{filter:none;background-color:var(--an-soft)}
#an-map-design .an-relation-panel :is(button,summary){transition:background-color 160ms}
@media(hover:hover){#an-map-design .an-relation-panel :is(button,summary):hover,#an-map-design .an-tool:hover,#an-map-design .an-zoom button:hover{background:light-dark(#f1f3f5,#252c35);filter:none}}
@media(max-width:700px){#an-map-design .an-relation-panel{bottom:8px;width:300px;max-width:calc(100% - 56px)}}
@media(prefers-reduced-motion:reduce){#an-map-design .an-relation-panel :is(button,summary){transition:none}}
`;root.append(memberRelationshipStyle);
inbox.setAttribute('aria-label','변화와 근거 자료');inbox.querySelector('h3').textContent='변화와 근거 자료';
// Only explicit/initial fit consumes this visible reading area. Panel toggles
// neither invoke fit nor change the stage, camera, node positions or drafts.
function memberRelationFitViewport(){
  const map=space.getBoundingClientRect(),panel=root.querySelector('.an-relation-panel');
  const width=space.clientWidth,height=space.clientHeight;
  if(panel&&!panel.hidden&&innerWidth>700){
    const box=panel.getBoundingClientRect();
    if(box.top<map.bottom&&box.bottom>map.top&&box.left<map.right&&box.right>map.left){
      const available=Math.max(1,Math.min(width,box.left-map.left-12));
      return {width:available,height,offsetX:(available-width)/2,offsetY:0};
    }
  }
  return {width,height,offsetX:0,offsetY:0};
}
function installMemberRelationPanel(){
  const panel=document.createElement('aside'),bar=document.createElement('div');
  panel.id='an-relation-panel';panel.className='an-relation-panel';panel.setAttribute('aria-label','변화 목록과 선택 근거');
  bar.className='an-relation-panel-head';panel.append(bar,inbox,detail);root.querySelector('.an-body').append(panel);
  const toggle=document.createElement('button');toggle.type='button';toggle.id='an-relation-changes';toggle.className='an-tool';toggle.textContent='변화·자료';toggle.setAttribute('aria-controls',panel.id);primaryTools.append(toggle);
  const make=(text,tab)=>{const b=document.createElement('button');b.type='button';b.textContent=text;b.dataset.relationTab=tab;bar.append(b);return b;};
  const changes=make('변화·자료','changes'),evidence=make('선택 근거','detail'),close=document.createElement('button');close.type='button';close.className='an-relation-close';close.textContent='×';close.setAttribute('aria-label','변화·근거 패널 접기');bar.append(close);
  let open=innerWidth>700,tab='changes',selection=state.selected,note=state.activeNote,noteList=state.noteList,stockList=memberStockList,guide=showGuide;
  // The panel is a sibling of the stage so its controls never enter the map's
  // capture listeners. Follow wrapped toolbar height without resizing the map.
  function positionPanel(){
    const body=root.querySelector('.an-body').getBoundingClientRect(),map=space.getBoundingClientRect();
    root.style.setProperty('--an-relation-panel-top',Math.max(8,map.top-body.top+8)+'px');
  }
  const panelResize=new ResizeObserver(positionPanel);
  for(const el of [root.querySelector('.an-body'),space,primaryTools,workbar])panelResize.observe(el);
  positionPanel();
  function sync(){
    panel.hidden=!open;inbox.hidden=tab!=='changes';detail.hidden=tab!=='detail';
    toggle.setAttribute('aria-expanded',String(open));changes.setAttribute('aria-pressed',String(tab==='changes'));evidence.setAttribute('aria-pressed',String(tab==='detail'));
    root.dataset.relationPanel=open?tab:'closed';
  }
  function show(next){open=true;tab=next;closePreview();sync();}
  toggle.onclick=()=>{if(cancelGesture)return;if(open&&tab==='changes')open=false;else{open=true;tab='changes';}closePreview();sync();};
  changes.onclick=()=>show('changes');evidence.onclick=()=>show('detail');
  close.onclick=()=>{open=false;closePreview();sync();toggle.focus({preventScroll:true});};
  // Background events in the native source/details DOM must not move the map.
  panel.addEventListener('keydown',e=>{if(e.key==='Escape'&&!e.defaultPrevented&&!editable(e.target)){e.preventDefault();e.stopPropagation();open=false;sync();toggle.focus({preventScroll:true});}});
  const priorDetail=renderDetail;
  renderDetail=function(){
    const changed=selection!==state.selected||note!==state.activeNote||noteList!==state.noteList||stockList!==memberStockList||guide!==showGuide;
    priorDetail();
    if(changed&&(state.selected||state.activeNote||state.noteList||memberStockList||showGuide)){open=true;tab='detail';}
    selection=state.selected;note=state.activeNote;noteList=state.noteList;stockList=memberStockList;guide=showGuide;sync();
  };
  sync();
}
installMemberRelationPanel();
const memberRelationshipDrawGroups=drawMemberGroups;
drawMemberGroups=function(){
  memberRelationshipDrawGroups();memberGroupLines.replaceChildren();memberSectionLayer.replaceChildren();
  root.style.setProperty('--an-relationship-zoom',String(state.zoom));
  root.dataset.relationshipCentered='true';
  root.querySelector('#an-counts').textContent='종목 '+memberScope().stocks.length+' · 사건·고정 자료 '+memberEligible.filter(n=>memberVisible.has(n.id)).length+' · 전체 자료 '+memberEligible.length;
  root.querySelector('.an-foot > span:last-of-type').textContent='관계 중심 지도 · 변화·자료에서 원문 확인 · 배경 드래그 이동 · Shift+드래그 선택';
  for(const button of inbox.querySelectorAll('[data-select]')){
    const n=nodeById[button.dataset.select],small=button.querySelector('small');if(!n||!small)continue;
    const kind=memberRelationshipIsMapRecord(n)?'사건·관계':n.layer==='candidates'?'미검수 후보':'근거 자료';
    small.textContent=[kind,memberRecordDateText(n)].filter(Boolean).join(' · ');
  }
};

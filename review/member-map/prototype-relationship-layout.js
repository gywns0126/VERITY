// Relationship-centered presentation. Neither canonical coordinates nor private
// notes/marks are rewritten: automatic sources use the existing evidence list.
function memberRelationshipIsMapRecord(n){
  return !!n&&n.layer!=='candidates'&&(n.recordKind==='event'||n.recordKind==='relationship'&&n.layer==='relationships');
}
function memberRelationshipOverviewNodes(){
  return nodes.filter(n=>n.kind==='event'&&shown(n)).map(n=>({id:n.id,n,el:nodesEl.querySelector('[data-node="'+n.id+'"]')}));
}
function memberRelationshipSlotsFor(records,stocks,obstacles=[],prior=new Map()){
  const gap=24,placed=new Map(),occupied=obstacles.map(b=>({...b}));
  const rect=p=>({left:p.x-p.width/2,right:p.x+p.width/2,top:p.y-p.height/2,bottom:p.y+p.height/2});
  const hits=(a,b)=>a.left<b.right+gap&&a.right>b.left-gap&&a.top<b.bottom+gap&&a.bottom>b.top-gap;
  for(const s of stocks)occupied.push(rect(s));
  const existing=records.filter(r=>prior.has(r.id)),fresh=records.filter(r=>!prior.has(r.id));
  // Prior insertion order, not changed reading order, owns established slots.
  existing.sort((a,b)=>[...prior.keys()].indexOf(a.id)-[...prior.keys()].indexOf(b.id));
  const displaced=[];
  // Reserve every still-safe prior slot before relocating a newly obstructed
  // card. Otherwise one moved memo can cascade through unaffected records.
  for(const r of existing){
    const p={...prior.get(r.id),width:r.width,height:r.height},b=rect(p);
    if(occupied.some(o=>hits(b,o)))displaced.push(r);
    else{placed.set(r.id,p);occupied.push(b);}
  }
  for(const r of [...displaced,...fresh]){
    const peers=stocks.filter(s=>(r.stockIds||[]).includes(s.id)),linked=peers.length?peers:stocks;
    const x=linked.length?linked.reduce((a,s)=>a+s.x,0)/linked.length:500;
    const bottom=linked.length?Math.max(...linked.map(s=>s.y+s.height/2)):340;
    const old=prior.get(r.id),p={x:old?.x??x,y:old?.y??bottom+70+r.height/2,width:r.width,height:r.height};
    // Keep X aligned with this relationship's participants; avoid only downward.
    // Appending or folding sources never participates in this calculation.
    for(let i=0;i<=occupied.length;i++){
      const b=rect(p),collisions=occupied.filter(o=>hits(b,o));
      if(!collisions.length)break;
      p.y=Math.max(...collisions.map(o=>o.bottom))+gap+r.height/2;
    }
    placed.set(r.id,p);occupied.push(rect(p));
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
const memberRelationshipStyle=document.createElement('style');memberRelationshipStyle.textContent=`
#an-map-design .an-body{grid-template-columns:minmax(0,1fr) 300px;grid-template-rows:minmax(180px,1fr) 200px;grid-template-areas:'map detail' 'library detail'}
#an-map-design .an-map{grid-area:map;min-width:0;min-height:0}
#an-map-design .an-detail{grid-area:detail}
#an-map-design .an-inbox{grid-area:library;display:grid!important;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));align-content:start;align-items:start;gap:12px;padding:16px 20px;background:light-dark(#f8f9fb,#1d242c);scrollbar-gutter:stable}
#an-map-design .an-inbox>h3{grid-column:1/-1;margin:0;font-size:14px;font-weight:800;color:light-dark(#191f28,#e3e7ec)}
#an-map-design .an-inbox>[data-member-list]{margin:0;min-width:0;box-shadow:0 2px 8px light-dark(rgb(25 31 40 / 4%),rgb(0 0 0 / 12%))}
#an-map-design .an-inbox>[data-member-list]>summary{min-height:44px;padding:10px 12px}
#an-map-design .an-inbox>[data-member-list]>[data-select]{display:block;text-align:left;width:calc(100% - 16px);font-size:12px;white-space:normal;overflow-wrap:anywhere}
#an-map-design .an-inbox>[data-member-list]>[data-select] strong{display:block;white-space:normal;font-size:12px;line-height:1.5;font-weight:700}
#an-map-design .an-inbox>[data-member-list]>[data-select] small{display:block;font-size:11px;font-weight:600;line-height:1.5;margin-top:4px}
#an-map-design .an-inbox>[data-member-list]>[data-select] .an-record-date{display:none}
#an-map-design .an-inbox .an-aside-note{grid-column:1/-1;margin:0;font-size:11px;font-weight:600}
#an-map-design #an-member-groups,#an-map-design #an-member-sections{visibility:hidden;pointer-events:none}
#an-map-design .an-inbox .an-node{position:static;transform:none}
#an-map-design .an-note-marker[data-free=true]{transform:translate(-50%,-50%) scale(var(--an-relationship-zoom,1))}
#an-map-design #an-nodes .an-node[data-overview-title=true] .an-category-icon{width:18px;height:18px;flex-basis:18px}
#an-map-design #an-nodes .an-node.event[data-overview-title=true] :is(.an-record-category,.an-record-date,.an-record-criteria,.an-relation-summary){display:none!important}
#an-map-design #an-nodes .an-node.event[data-overview-title=true] strong{display:block!important;white-space:nowrap!important;line-height:18px!important;-webkit-line-clamp:unset}
@media(max-width:1100px){#an-map-design .an-body{grid-template-columns:minmax(0,1fr) 280px}}
@media(max-width:700px){#an-map-design .an-body{grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(160px,1fr) 164px;grid-template-areas:'map' 'library'}#an-map-design .an-inbox{grid-template-columns:minmax(0,1fr);padding:12px;gap:10px}#an-map-design .an-detail{grid-area:auto}}
`;root.append(memberRelationshipStyle);
inbox.setAttribute('aria-label','종목별 근거 자료');inbox.querySelector('h3').textContent='근거 자료 · 사건과 구분해 보기';
const memberRelationshipDrawGroups=drawMemberGroups;
drawMemberGroups=function(){
  memberRelationshipDrawGroups();memberGroupLines.replaceChildren();memberSectionLayer.replaceChildren();
  root.style.setProperty('--an-relationship-zoom',String(state.zoom));
  root.dataset.relationshipCentered='true';
  root.querySelector('#an-counts').textContent='종목 '+memberScope().stocks.length+' · 사건·고정 자료 '+memberEligible.filter(n=>memberVisible.has(n.id)).length+' · 전체 자료 '+memberEligible.length;
  root.querySelector('.an-foot > span:last-of-type').textContent='사건 중심 지도 · 아래 자료함에서 원문 펼치기 · Space+드래그로 이동';
  for(const button of inbox.querySelectorAll('[data-select]')){
    const n=nodeById[button.dataset.select],small=button.querySelector('small');if(!n||!small)continue;
    const kind=memberRelationshipIsMapRecord(n)?'사건·관계':n.layer==='candidates'?'미검수 후보':'근거 자료';
    small.textContent=[kind,memberRecordDateText(n)].filter(Boolean).join(' · ');
  }
};

// A temporary exploration surface. Its camera and positions never enter the
// member draft, native layout, selection, movement history or note editor.
function memberNetworkStage(zoom){return zoom<.28?'dots':zoom<.8?'names':'cards';}
function memberNetworkSnapshot(scope,allEdges){
  const items=[...scope.stocks,...scope.records].map(n=>({...n,evidence:(n.evidence||[]).map(e=>({...e}))})),ids=new Set(items.map(n=>n.id));
  return {items,links:allEdges.filter(e=>ids.has(e.from)&&ids.has(e.to)&&inScenario(e)).map(e=>({...e}))};
}
const memberNetworkStyle=document.createElement('style');memberNetworkStyle.textContent=`
#an-map-design[data-network-open=true]>:not(.an-network-view):not(style):not(script){visibility:hidden!important}
#an-map-design .an-network-view[hidden]{display:none!important}
#an-map-design .an-network-view{--an-sub:light-dark(#6b7684,#9aa4b1);position:fixed;inset:0;z-index:50;display:flex;flex-direction:column;background:light-dark(#f8f9fb,#1d242c);color:var(--an-text);font:600 12px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif}
#an-map-design .an-network-head{display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:12px 16px;background:var(--an-panel)}
#an-map-design .an-network-head h2{font-size:16px;font-weight:800;margin:0 auto 0 0}
#an-map-design .an-network-view button{font:inherit;font-weight:700;border:0;border-radius:10px;color:var(--an-text);background:var(--an-panel);cursor:pointer}
#an-map-design .an-network-head button{min-height:36px;padding:6px 10px;background:light-dark(#f8f9fb,#1d242c)}
#an-map-design .an-network-view button:focus-visible{outline:none;background:light-dark(#e9edf2,#303945)}
#an-map-design .an-network-main{min-height:0;flex:1;display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,320px)}
#an-map-design .an-network-side{display:flex;flex-direction:column;min-height:0;overflow:auto;background:var(--an-panel)}
#an-map-design .an-network-settings{padding:12px 16px;background:var(--an-panel)}
#an-map-design .an-network-settings summary{cursor:pointer;font-weight:800;padding:8px;border-radius:10px}
#an-map-design .an-network-settings summary:focus-visible{outline:none;background:light-dark(#e9edf2,#303945)}
#an-map-design .an-network-settings label{display:flex;align-items:center;gap:8px;margin:8px 0;min-height:32px;white-space:nowrap;color:var(--an-text)}
#an-map-design .an-network-settings input:not([type=checkbox]),#an-map-design .an-network-settings select{box-sizing:border-box;min-width:0;width:100%;font:inherit;color:var(--an-text);background:light-dark(#f8f9fb,#1d242c);border:0;border-radius:10px;padding:8px}
#an-map-design .an-network-settings input:focus-visible,#an-map-design .an-network-settings select:focus-visible{outline:none;background:light-dark(#e9edf2,#303945)}
#an-map-design .an-network-kinds{display:grid;grid-template-columns:1fr 1fr;gap:0 8px}
#an-map-design .an-network-settings input[type=checkbox]{accent-color:var(--an-accent)}
#an-map-design .an-network-settings p{margin:8px 0;color:var(--an-sub);font-size:11px}
#an-map-design .an-network-settings button{padding:8px 10px;min-height:36px;background:light-dark(#f8f9fb,#1d242c)}
#an-map-design .an-network-results{max-height:150px;overflow:auto}
#an-map-design .an-network-results button{display:block;text-align:left;width:100%;margin-top:4px;overflow-wrap:anywhere}
#an-map-design .an-network-node[hidden]{display:none!important}
#an-map-design .an-network-node[data-pinned=true] .an-network-label::before{content:'● ';color:var(--an-accent)}
#an-map-design .an-network-space{position:relative;min-width:0;min-height:0;overflow:clip;touch-action:none;cursor:grab}
#an-map-design .an-network-space:focus-visible{outline:none}
#an-map-design .an-network-space>svg{display:none}
#an-map-design .an-network-space>.an-network-grid{display:block;position:absolute;inset:0;width:100%;height:100%;pointer-events:none;fill:none;stroke:light-dark(var(--an-grid),var(--an-divider));stroke-width:1;shape-rendering:crispEdges}
#an-map-design .an-network-graph{position:absolute;inset:0}
#an-map-design .an-network-nodes{position:absolute;inset:0;pointer-events:none}
#an-map-design .an-network-space:not([data-stage=cards]) .an-network-node{pointer-events:none;background:transparent;box-shadow:none}
#an-map-design .an-network-space[data-stage=cards] .an-network-node{pointer-events:auto}
#an-map-design .an-network-node .an-network-dot{display:none}
#an-map-design .an-network-edge{fill:none;stroke:var(--an-line);stroke-width:1;stroke-dasharray:2 4;opacity:.55}
#an-map-design .an-network-node{position:absolute;box-sizing:border-box;width:18px;height:18px;min-height:0;padding:0;transform:translate(-50%,-50%);background:transparent;box-shadow:none;user-select:none;touch-action:none}
#an-map-design .an-network-dot{display:block;position:absolute;width:6px;height:6px;left:50%;top:50%;transform:translate(-50%,-50%);border-radius:50%;background:var(--an-line)}
#an-map-design .an-network-node[data-kind=stock] .an-network-dot{width:10px;height:10px;background:var(--an-text)}
#an-map-design .an-network-node[data-kind=relationship] .an-network-dot{background:var(--an-accent)}
#an-map-design .an-network-label,#an-map-design .an-network-face,#an-map-design .an-network-meta{display:none}
#an-map-design .an-network-space[data-stage=names] .an-network-label{display:block;position:absolute;left:calc(50% + 8px);top:50%;transform:translateY(-50%);width:var(--an-network-label-width);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px;font-weight:700;text-align:left;pointer-events:none}
#an-map-design .an-network-space[data-stage=cards] .an-network-node{display:flex;align-items:center;gap:8px;width:160px;height:32px;padding:5px 10px;background:var(--an-panel);border-radius:14px;text-align:left;box-shadow:0 2px 8px var(--an-shadow)}
#an-map-design .an-network-space[data-stage=cards] .an-network-node[aria-pressed=true]{height:76px;padding:10px 12px}
#an-map-design .an-network-space[data-stage=cards] .an-network-dot{display:none}
#an-map-design .an-network-space[data-stage=cards] .an-network-face{display:flex;flex:0 0 20px;align-items:center;width:20px;height:20px}
#an-map-design .an-network-face :is(svg,.an-logo){width:20px;height:20px;flex:0 0 20px}
#an-map-design .an-network-face .an-logo img{width:100%;height:100%;object-fit:contain;border-radius:6px}
#an-map-design .an-network-face .an-flag{width:10px;height:10px;right:-2px;bottom:-2px}
#an-map-design .an-network-space[data-stage=cards] .an-network-node>span:last-child{flex:1;min-width:0}
#an-map-design .an-network-space[data-stage=cards] .an-network-label{display:-webkit-box;overflow:hidden;overflow-wrap:anywhere;-webkit-line-clamp:1;-webkit-box-orient:vertical;font-size:12px;line-height:18px;font-weight:800}
#an-map-design .an-network-space[data-stage=cards] .an-network-node[aria-pressed=true] .an-network-label{-webkit-line-clamp:2}
#an-map-design .an-network-space[data-stage=cards] .an-network-node[aria-pressed=true] .an-network-meta{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px;font-weight:600;color:var(--an-sub)}
#an-map-design .an-network-space[data-stage=names] .an-network-node[data-kind=stock] .an-network-face{display:flex;position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:20px;height:20px}
#an-map-design .an-network-space[data-stage=names] .an-network-node[data-kind=stock] .an-network-label{left:calc(50% + 16px);width:max(90px,var(--an-network-label-width))}
#an-map-design .an-network-space[data-stage=names] .an-network-node:is([data-kind=source],[data-kind=candidate]):not([data-emphasis=true]) .an-network-label{display:none}
#an-map-design .an-network-node[data-faded=true],#an-map-design .an-network-edge[data-faded=true]{opacity:.12}
#an-map-design .an-network-node[aria-pressed=true]{background:light-dark(#e9edf2,#303945)}
#an-map-design .an-network-inspector{overflow:auto;min-height:0;padding:16px;background:var(--an-panel);scrollbar-gutter:stable}
#an-map-design .an-network-inspector h3{font-size:14px;font-weight:800;margin:0 0 8px;overflow-wrap:anywhere}
#an-map-design .an-network-inspector p{margin:0 0 12px;color:var(--an-sub);overflow-wrap:anywhere}
#an-map-design .an-network-inspector h4{font-size:13px;font-weight:800;margin:20px 0 8px}
#an-map-design .an-network-inspector .an-network-excerpt{white-space:pre-wrap;line-height:1.7}
#an-map-design .an-network-inspector button{display:block;width:100%;text-align:left;min-height:36px;padding:8px 10px;margin-top:8px;background:light-dark(#f8f9fb,#1d242c);overflow-wrap:anywhere}
#an-map-design .an-network-foot{padding:8px 16px;background:var(--an-panel);color:var(--an-sub);font-size:11px}
@media(prefers-reduced-motion:no-preference){#an-map-design .an-network-node{transition:opacity 160ms}}
@media(hover:hover){#an-map-design .an-network-view button:hover{background:light-dark(#f1f3f5,#252c35)}}
@media(max-width:700px){#an-map-design .an-network-main{grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(0,1fr) min(220px,35%)}#an-map-design .an-network-inspector{max-height:220px;padding:12px 16px}#an-map-design .an-network-head{padding:10px 12px;gap:6px}}
@media(pointer:coarse){#an-map-design .an-network-head button,#an-map-design .an-network-inspector button{min-height:44px}}
`;root.append(memberNetworkStyle);
const memberNetworkButton=document.createElement('button');memberNetworkButton.type='button';memberNetworkButton.className='an-tool';memberNetworkButton.textContent='전체 관계망';memberNetworkButton.setAttribute('aria-expanded','false');root.querySelector('.an-zoom').append(memberNetworkButton);
const memberNetworkHost=document.createElement('section');memberNetworkHost.className='an-network-view';memberNetworkHost.hidden=true;memberNetworkHost.setAttribute('aria-label','전체 관계망 탐색');
memberNetworkHost.innerHTML='<header class="an-network-head"><h2>전체 관계망</h2><button type="button" data-network-action="lock" aria-pressed="true">배치 잠김</button><button type="button" data-network-action="out" aria-label="관계망 축소">−</button><output aria-label="관계망 배율"></output><button type="button" data-network-action="in" aria-label="관계망 확대">+</button><button type="button" data-network-action="fit">한눈에</button><button type="button" data-network-action="close">원래 보기</button></header><div class="an-network-main"><div class="an-network-space" tabindex="0" role="group" aria-label="관계망 · 배경 드래그로 이동, 휠로 확대축소"><svg aria-hidden="true"></svg><svg class="an-network-grid" aria-hidden="true"><path class="an-network-grid-fine"/><path class="an-network-grid-coarse"/></svg><div class="an-network-graph" aria-hidden="true"></div><div class="an-network-nodes"></div></div><aside class="an-network-side"><details class="an-network-settings" open><summary>탐색 설정</summary><label>검색<input type="search" data-network-filter="query" aria-label="관계망 검색" placeholder="종목·사건·원문 검색"></label><div class="an-network-results" aria-label="검색 결과"></div><div class="an-network-kinds"><label><input type="checkbox" data-network-kind="stock" checked>종목</label><label><input type="checkbox" data-network-kind="relationship" checked>사건·관계</label><label><input type="checkbox" data-network-kind="source" checked>근거 자료</label><label><input type="checkbox" data-network-kind="candidate" checked>미검수 후보</label></div><label><input type="checkbox" data-network-filter="orphans" checked>연결 없는 항목도 표시</label><label>연결 범위<select data-network-filter="depth" aria-label="연결 깊이"><option value="0">전체 연결</option><option value="1">선택 항목 주변 1단계</option><option value="2">선택 항목 주변 2단계</option><option value="3">선택 항목 주변 3단계</option></select></label><button type="button" data-network-action="filters-reset">필터 초기화</button><details><summary>표시·배치 조절</summary><label><input type="checkbox" data-network-degree checked>연결 수에 따라 점 크기</label><label>점 크기<input type="range" min="0.5" max="2" step="0.1" value="1" data-network-display="nodeScale"></label><label>선 굵기<input type="range" min="0.5" max="2" step="0.1" value="1" data-network-display="edgeScale"></label><label>이름 표시 배율<input type="range" min="0.1" max="0.7" step="0.01" value="0.28" data-network-display="labelThreshold"></label><label>연결 거리<input type="range" min="80" max="300" step="10" value="150" data-network-layout="linkDistance"></label><label>밀어내기<input type="range" min="0.5" max="3" step="0.25" value="1" data-network-layout="repulsion"></label><button type="button" data-network-action="arrange">배치 정돈</button><button type="button" data-network-action="unpin">탐색 위치 고정 해제</button><p>배치 정돈은 버튼을 눌렀을 때만 실행돼요. 직접 옮긴 점은 고정됩니다. 점 크기는 연결 수, 선은 기존 관계 판정을 따르며 조절값은 화면에만 적용돼요. 원래 지도 기록은 바뀌지 않아요. 탐색 위치는 이 페이지에서만 유지되며 새로고침하면 초기화돼요.</p></details></details><div class="an-network-inspector" aria-label="관계망 선택 자료"></div></aside></div><footer class="an-network-foot" aria-live="polite"></footer>';
root.append(memberNetworkHost);
const memberNetworkSpace=memberNetworkHost.querySelector('.an-network-space'),memberNetworkGraph=memberNetworkHost.querySelector('.an-network-graph'),memberNetworkSvg=memberNetworkHost.querySelector('svg'),memberNetworkNodes=memberNetworkHost.querySelector('.an-network-nodes'),memberNetworkInspector=memberNetworkHost.querySelector('.an-network-inspector');
memberNetworkSpace.setAttribute('aria-label','관계망 · 휠·두 손가락 이동 · ⌘/Ctrl+휠·핀치 확대축소 · Space+드래그 이동');
let memberNetworkSession=null,memberNetworkOpening=false,memberNetworkCache=null;
function memberNetworkOptions(){return {query:'',kinds:['stock','relationship','source','candidate'],showOrphans:true,depth:0,anchor:'',nodeScale:1,edgeScale:1,degreeSizing:true,labelThreshold:.28,linkDistance:150,repulsion:1};}
function memberNetworkSyncControls(){
  const s=memberNetworkSession;if(!s)return;const q=selector=>memberNetworkHost.querySelector(selector);
  if(!q('[data-network-filter=query]'))return;
  q('[data-network-filter=query]').value=s.options.query;q('[data-network-filter=orphans]').checked=s.options.showOrphans;q('[data-network-filter=depth]').value=String(s.options.depth);
  q('[data-network-degree]').checked=s.options.degreeSizing;
  for(const el of memberNetworkHost.querySelectorAll('[data-network-kind]'))el.checked=s.options.kinds.includes(el.dataset.networkKind);
  for(const el of memberNetworkHost.querySelectorAll('[data-network-display],[data-network-layout]'))el.value=String(s.options[el.dataset.networkDisplay||el.dataset.networkLayout]);
  const lock=q('[data-network-action=lock]');lock.textContent=s.draggable?'점 이동 가능':'배치 잠김';lock.setAttribute('aria-pressed',String(!s.draggable));
}
function memberNetworkFilter(){
  const s=memberNetworkSession;if(!s)return;
  const result=memberNetworkExplore([...s.byId.values()].map(n=>({...n,networkKind:memberNetworkKind(n)})),s.links,s.options);
  s.visible=result.ids;s.visibleLinks=result.links;s.engine?.setVisible?.(s.visible);
  for(const [id,el] of s.elements)el.hidden=!s.visible.has(id);
  const out=memberNetworkHost.querySelector('.an-network-results');
  if(out){out.replaceChildren();if(s.options.query.trim())for(const id of [...s.visible].slice(0,30)){const n=s.byId.get(id),b=document.createElement('button');b.type='button';b.textContent=n.name+' · '+memberNetworkKindText(n);b.onclick=()=>memberNetworkSelect(id);out.append(b);}}
  memberNetworkHost.querySelector('footer').textContent='표시 '+s.visible.size+'/'+s.byId.size+'개 · 연결 '+s.visibleLinks.length+'/'+s.links.length+'개'+(s.options.depth?' · 중심: '+(s.byId.get(s.options.anchor)?.name||'항목을 먼저 선택하세요'):'')+' · '+s.pinned.size+'개 위치 고정 · 실선: 직접 / 점선: 간접·참고·미검수 · Esc 복귀';
  memberNetworkSelect(s.visible.has(s.selected)?s.selected:'',true);drawMemberNetwork();
}
function memberNetworkMove(id,p){
  const s=memberNetworkSession;if(!s||!s.draggable||!s.byId.has(id)||!Number.isFinite(p?.x)||!Number.isFinite(p?.y))return;
  s.positions.set(id,{x:p.x,y:p.y});s.pinned.set(id,{x:p.x,y:p.y});s.elements.get(id).dataset.pinned='true';drawMemberNetwork();
}
function memberNetworkArrange(){
  const s=memberNetworkSession;if(!s)return;
  const items=[...s.byId.values()].filter(n=>s.visible.has(n.id));
  const positions=memberNetworkLayout(items.map(n=>({id:n.id,kind:n.kind,width:160,height:76})),s.visibleLinks,{linkDistance:s.options.linkDistance,repulsion:9000*s.options.repulsion,pinned:s.pinned});
  for(const [id,p] of positions)s.positions.set(id,p);s.engine?.setPositions?.(positions);drawMemberNetwork();
}
function memberNetworkCardDrag(b,id){
  let drag=null,suppress=false;
  b.onpointerdown=e=>{const s=memberNetworkSession;if(!s?.draggable||e.button!==0||s.input?.space||e.pointerType==='touch')return;const p=s.positions.get(id);drag={pointer:e.pointerId,x:e.clientX,y:e.clientY,p:{...p},pin:s.pinned.get(id),moved:false,cancel:()=>finish(e,true)};memberNetworkInput(s).cancelCard=drag.cancel;b.setPointerCapture(e.pointerId);e.stopPropagation();};
  b.onpointermove=e=>{const s=memberNetworkSession;if(!s||!drag||drag.pointer!==e.pointerId)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.hypot(dx,dy)<4&&!drag.moved)return;drag.moved=true;const p={x:drag.p.x+dx/s.camera.zoom,y:drag.p.y+dy/s.camera.zoom};memberNetworkMove(id,p);s.engine?.setPositions?.(new Map([[id,p]]));e.stopPropagation();};
  const finish=(e,cancelled=false)=>{if(!drag||drag.pointer!==e.pointerId)return;const before=drag;drag=null;suppress=before.moved||cancelled;const s=memberNetworkSession;if(s?.input?.cancelCard===before.cancel)s.input.cancelCard=null;if(cancelled&&s){s.positions.set(id,before.p);if(before.pin)s.pinned.set(id,before.pin);else s.pinned.delete(id);b.dataset.pinned=String(s.pinned.has(id));s.engine?.setPositions?.(new Map([[id,before.p]]));}if(b.hasPointerCapture(e.pointerId))b.releasePointerCapture(e.pointerId);e.stopPropagation();memberNetworkFilter();};
  b.onpointerup=e=>finish(e);b.onpointercancel=e=>finish(e,true);b.onlostpointercapture=e=>finish(e,true);
  b.onclick=()=>{if(suppress){suppress=false;return;}memberNetworkSelect(id);};
}
function memberNetworkInput(s){return s.input||(s.input={points:new Map(),drag:null,gesture:null,space:false,suppressUntil:0});}
function memberNetworkWheel(e){
  const s=memberNetworkSession;if(!s)return;e.preventDefault();e.stopPropagation();const input=memberNetworkInput(s);if(input.gesture||input.points.size||input.drag||input.cancelCard||input.engineDragging)return;
  const r=memberNetworkSpace.getBoundingClientRect(),unit=e.deltaMode===1?16:e.deltaMode===2?r.height:1;
  if(!e.ctrlKey&&!e.metaKey){s.camera.panX-=(e.shiftKey&&!e.deltaX?e.deltaY:e.deltaX)*unit;s.camera.panY-=(e.shiftKey&&!e.deltaX?0:e.deltaY)*unit;drawMemberNetwork();return;}
  const delta=Math.max(-120,Math.min(120,e.deltaY*unit));zoomMemberNetwork(s.camera.zoom*Math.exp(-delta*(e.ctrlKey ? .012 : .003)),{x:e.clientX-r.left,y:e.clientY-r.top});
}
function memberNetworkGestureStart(e){const s=memberNetworkSession;if(!s)return;e.preventDefault();e.stopPropagation();const input=memberNetworkInput(s);if(input.points.size)return;input.gesture={zoom:s.camera.zoom,scale:e.scale||1,x:e.clientX,y:e.clientY};}
function memberNetworkGestureChange(e){const s=memberNetworkSession;if(!s)return;e.preventDefault();e.stopPropagation();const g=memberNetworkInput(s).gesture;if(!g)return;const r=memberNetworkSpace.getBoundingClientRect();zoomMemberNetwork(g.zoom*(e.scale||1)/g.scale,{x:g.x-r.left,y:g.y-r.top});}
function memberNetworkGestureEnd(e){if(!memberNetworkSession)return;e.preventDefault();e.stopPropagation();memberNetworkInput(memberNetworkSession).gesture=null;}
function memberNetworkTouchHit(e,s){
  const card=e.target.closest?.('.an-network-node');if(card)return card.dataset.networkNode;
  const r=memberNetworkSpace.getBoundingClientRect();let nearest='',distance=18;
  for(const [id,p] of s.positions){if(!s.visible.has(id))continue;const d=Math.hypot(e.clientX-r.left-r.width/2-(p.x-500)*s.camera.zoom-s.camera.panX,e.clientY-r.top-r.height/2-(p.y-340)*s.camera.zoom-s.camera.panY);if(d<distance){nearest=id;distance=d;}}
  return nearest;
}
function memberNetworkRestoreDrag(s,drag){
  if(drag?.mode!=='node'||!drag.p)return;s.positions.set(drag.id,{...drag.p});if(drag.pin)s.pinned.set(drag.id,{...drag.pin});else s.pinned.delete(drag.id);s.elements.get(drag.id).dataset.pinned=String(s.pinned.has(drag.id));s.engine?.setPositions?.(new Map([[drag.id,drag.p]]));drawMemberNetwork();
}
function memberNetworkPointerDown(e){
  const s=memberNetworkSession;if(!s||(e.button!==0&&e.button!==1))return;const input=memberNetworkInput(s),touch=e.pointerType==='touch',card=e.target.closest?.('.an-network-node');
  if(!input.points.size&&!input.drag&&!input.cancelCard&&!input.engineDragging)input.suppressUntil=0;
  if(!touch&&!input.space&&e.button!==1&&(!card||s.draggable))return;
  input.points.set(e.pointerId,{x:e.clientX,y:e.clientY});input.gesture=null;
  if(touch||input.space||e.button===1){e.preventDefault();e.stopPropagation();memberNetworkSpace.setPointerCapture(e.pointerId);}
  if(input.points.size>1){memberNetworkRestoreDrag(s,input.drag);const [a,b]=[...input.points.values()];input.drag={mode:'pinch',distance:Math.max(1,Math.hypot(b.x-a.x,b.y-a.y)),x:(a.x+b.x)/2,y:(a.y+b.y)/2,camera:{...s.camera},moved:true};input.suppressUntil=Date.now()+300;return;}
  const id=touch?memberNetworkTouchHit(e,s):card?.dataset.networkNode||'';
  input.drag={mode:touch&&s.draggable&&id&&!input.space?'node':'pan',id,p:id?{...s.positions.get(id)}:null,pin:s.pinned.get(id),x:e.clientX,y:e.clientY,camera:{...s.camera},pointer:e.pointerId,moved:false,touch};
}
function memberNetworkPointerMove(e){
  const s=memberNetworkSession,input=s?.input;if(!input?.points.has(e.pointerId)||!input.drag)return;input.points.set(e.pointerId,{x:e.clientX,y:e.clientY});const d=input.drag;
  if(input.points.size>1){const [a,b]=[...input.points.values()],r=memberNetworkSpace.getBoundingClientRect(),x=(a.x+b.x)/2-r.left-r.width/2,y=(a.y+b.y)/2-r.top-r.height/2,z=Math.max(.02,Math.min(4,d.camera.zoom*Math.hypot(b.x-a.x,b.y-a.y)/d.distance)),ratio=z/d.camera.zoom;
    s.camera={zoom:z,panX:x-(d.x-r.left-r.width/2-d.camera.panX)*ratio,panY:y-(d.y-r.top-r.height/2-d.camera.panY)*ratio};
  }else{const dx=e.clientX-d.x,dy=e.clientY-d.y;if(!d.moved&&Math.hypot(dx,dy)<4)return;d.moved=true;
    if(d.mode==='node'){const p={x:d.p.x+dx/s.camera.zoom,y:d.p.y+dy/s.camera.zoom};memberNetworkMove(d.id,p);s.engine?.setPositions?.(new Map([[d.id,p]]));}
    else{s.camera.panX=d.camera.panX+dx;s.camera.panY=d.camera.panY+dy;}}
  e.preventDefault();e.stopPropagation();memberNetworkSpace.setPointerCapture(e.pointerId);input.suppressUntil=Date.now()+300;drawMemberNetwork();
}
function memberNetworkPointerEnd(e){
  const s=memberNetworkSession,input=s?.input;if(!input?.points.has(e.pointerId))return;const d=input.drag,cancelled=e.type==='pointercancel'||e.type==='lostpointercapture';input.points.delete(e.pointerId);
  if(cancelled)memberNetworkRestoreDrag(s,d);
  if(input.points.size){const [pointer,p]=[...input.points][0];input.drag={mode:'pan',id:'',pointer,x:p.x,y:p.y,camera:{...s.camera},moved:true,touch:true};}
  else input.drag=null;
  if(memberNetworkSpace.hasPointerCapture(e.pointerId))memberNetworkSpace.releasePointerCapture(e.pointerId);
  if(d?.moved||cancelled){input.suppressUntil=Date.now()+300;e.preventDefault();e.stopPropagation();}
  else if(d?.touch){memberNetworkSelect(d.id||'');input.suppressUntil=Date.now()+300;e.preventDefault();e.stopPropagation();}
}
function memberNetworkCancelInput(){
  const s=memberNetworkSession,input=s?.input;if(!input)return;input.cancelCard?.();memberNetworkRestoreDrag(s,input.drag);memberNetworkRestoreDrag(s,input.engineDrag);input.engineDrag=null;input.engineDragging=false;input.drag=null;input.gesture=null;input.space=false;const ids=[...input.points.keys()];input.points.clear();for(const id of ids)if(memberNetworkSpace.hasPointerCapture(id))memberNetworkSpace.releasePointerCapture(id);
}
function memberNetworkKind(n){return n.kind==='stock'?'stock':memberRelationshipIsMapRecord(n)?'relationship':n.layer==='candidates'?'candidate':'source';}
function memberNetworkKindText(n){return {stock:'종목',relationship:'사건·관계',candidate:'미검수 후보',source:'근거 자료'}[memberNetworkKind(n)];}
function memberNetworkSelect(id,refresh=false){
  const s=memberNetworkSession;if(!s)return;s.selected=refresh?id:s.selected===id?'':id;
  if(!refresh&&s.options.depth&&s.selected){s.options.anchor=s.selected;memberNetworkFilter();}
  const fromInspector=memberNetworkInspector.contains(document.activeElement);
  memberNetworkInspector.replaceChildren();
  const n=s.byId.get(s.selected),title=document.createElement('h3'),caption=document.createElement('p');
  title.textContent=n?n.name:s.elements.size?'연결을 선택해 보세요':'표시할 자료가 없어요';
  caption.textContent=n?memberNetworkKindText(n)+' · '+memberRecordDateText(n):'작은 점은 근거 자료, 이름이 보이는 점은 종목·사건입니다. 점을 선택하면 연결과 원문을 여기서 읽을 수 있어요. 확대해도 배치는 그대로예요.';
  memberNetworkInspector.append(title,caption);
  if(n){
    const clear=document.createElement('button');clear.type='button';clear.textContent='선택 해제';clear.onclick=()=>memberNetworkSelect('');memberNetworkInspector.append(clear);
    const local=document.createElement('button');local.type='button';local.textContent='이 항목 주변 연결 탐색';local.onclick=()=>{s.options.anchor=n.id;s.options.depth=1;memberNetworkSyncControls();memberNetworkFilter();};memberNetworkInspector.append(local);
    const pin=document.createElement('button');pin.type='button';pin.textContent=s.pinned.has(n.id)?'이 점 위치 고정 해제':'이 점 위치 고정';pin.onclick=()=>{if(s.pinned.has(n.id))s.pinned.delete(n.id);else s.pinned.set(n.id,{...s.positions.get(n.id)});s.elements.get(n.id).dataset.pinned=String(s.pinned.has(n.id));s.selected='';memberNetworkSelect(n.id);memberNetworkFilter();};memberNetworkInspector.append(pin);
    const connected=s.visibleLinks.filter(e=>e.from===n.id||e.to===n.id),why=document.createElement('p');
    why.textContent=memberNetworkKind(n)==='source'?'점선은 원문이 해당 종목에 속한다는 뜻이며, 경제적 영향 판정은 아닙니다.':memberNetworkKind(n)==='candidate'?'검수 전 후보입니다. 확인된 관계로 표시하지 않습니다.':'연결 수는 경제적 중요도나 수익 확률이 아닙니다.';memberNetworkInspector.append(why);
    const count=document.createElement('p');count.textContent='표시 연결 '+connected.length+'개';memberNetworkInspector.append(count);
    for(const e of connected){const peer=s.byId.get(e.from===n.id?e.to:e.from),v=s.visuals.get(e.id),line=document.createElement(peer?'button':'p');line.textContent=[e.verb||'자료 연결',peer?.name||'종목 미확인',v?.statusLabel,v?.summaryLabel,v?.lineLabel].filter(Boolean).join(' · ');if(peer){line.type='button';line.onclick=()=>memberNetworkSelect(peer.id);}memberNetworkInspector.append(line);}
    for(const evidence of n.evidence||[]){
      const heading=document.createElement('h4');heading.textContent=evidence.title||evidence.source||'원문 근거';memberNetworkInspector.append(heading);
      if(evidence.asOf){const date=document.createElement('p');date.textContent='자료 기준 '+evidence.asOf;memberNetworkInspector.append(date);}
      if(evidence.explanation){const excerpt=document.createElement('p');excerpt.className='an-network-excerpt';excerpt.textContent=evidence.explanation;memberNetworkInspector.append(excerpt);}
      try{const url=new URL(evidence.url);if(url.protocol!=='https:'||url.username||url.password||/[\u0000-\u001f\u007f]/.test(decodeURIComponent(evidence.url)))continue;
        const address=document.createElement('p');address.textContent=url.href;memberNetworkInspector.append(address);
        const b=document.createElement('button');b.type='button';b.textContent=evidence.source||evidence.title||'원문 열기';b.onclick=()=>memberPort.postMessage({type:'source',url:url.href});memberNetworkInspector.append(b);
      }catch{}
    }
  }
  memberNetworkHighlight(s.selected);
  if(fromInspector){title.tabIndex=-1;title.focus({preventScroll:true});}
}
function memberNetworkHighlight(id){
  const s=memberNetworkSession;if(!s)return;const inspected=id;id=s.selected||id;const linked=new Set(id?[id]:[]);
  for(const e of s.links)if(e.from===id||e.to===id){linked.add(e.from);linked.add(e.to);}
  for(const [key,el] of s.elements){el.dataset.faded=String(!!id&&!linked.has(key)&&key!==inspected);el.dataset.emphasis=String(linked.has(key)||key===inspected);el.setAttribute('aria-pressed',String(key===s.selected));}
  for(const [e,el] of s.paths)el.dataset.faded=String(!!id&&e.from!==id&&e.to!==id);
  s.engine?.highlight(id);
}
function renderMemberNetworkGrid(){
  const s=memberNetworkSession;if(!s)return;
  const {width:w,height:h}=memberNetworkSpace.getBoundingClientRect();let step=24*s.camera.zoom;
  // Native workboard lattice/fade; at extreme zoom-out retain every fourth line until spacing is readable.
  while(step<8)step*=4;
  const originX=w/2+s.camera.panX,originY=h/2+s.camera.panY,fade=Math.max(0,Math.min(1,(step-8)/16)),fineOpacity=fade*.8,paths=['',''];
  for(let i=Math.ceil(-originX/step);i<=Math.floor((w-originX)/step);i++){
    const major=i%4===0;if(!major&&!fineOpacity)continue;
    const x=Math.round(originX+i*step)+.5;paths[major?1:0]+='M '+x+' 0 V '+h+' ';
  }
  for(let i=Math.ceil(-originY/step);i<=Math.floor((h-originY)/step);i++){
    const major=i%4===0;if(!major&&!fineOpacity)continue;
    const y=Math.round(originY+i*step)+.5;paths[major?1:0]+='M 0 '+y+' H '+w+' ';
  }
  const fine=memberNetworkSpace.querySelector('.an-network-grid-fine'),coarse=memberNetworkSpace.querySelector('.an-network-grid-coarse');
  fine.setAttribute('d',paths[0]);coarse.setAttribute('d',paths[1]);
  fine.style.opacity=String(fineOpacity);coarse.style.opacity=String(1-(1-fineOpacity)*(1-(.65-fade*.25)));
}
function drawMemberNetwork(){
  const s=memberNetworkSession;if(!s)return;
  const {width,height}=memberNetworkSpace.getBoundingClientRect(),z=s.camera.zoom,project=p=>({x:width/2+(p.x-500)*z+s.camera.panX,y:height/2+(p.y-340)*z+s.camera.panY});
  const stage=z<(s.options?.labelThreshold??.28)?'dots':z<.8?'names':'cards';memberNetworkSpace.dataset.stage=stage;memberNetworkSpace.style.setProperty('--an-network-label-width',Math.max(40,145*z)+'px');
  s.engine?.setCamera(s.camera);s.engine?.setStage(stage,z);
  renderMemberNetworkGrid();
  for(const [id,el] of s.elements){const p=project(s.positions.get(id));el.style.left=p.x+'px';el.style.top=p.y+'px';el.style.transform='translate(-50%,-50%)'+(stage==='cards'?' scale('+z+')':'');el.tabIndex=!el.hidden&&p.x>=0&&p.x<=width&&p.y>=0&&p.y<=height?0:-1;}
  memberNetworkHost.querySelector('output').textContent=Math.round(z*100)+'%';
}
function zoomMemberNetwork(next,at){
  const s=memberNetworkSession;if(!s)return;const r=memberNetworkSpace.getBoundingClientRect(),x=(at?.x??r.width/2)-r.width/2,y=(at?.y??r.height/2)-r.height/2,z=Math.max(.02,Math.min(4,next)),ratio=z/s.camera.zoom;
  s.camera.panX=x-(x-s.camera.panX)*ratio;s.camera.panY=y-(y-s.camera.panY)*ratio;s.camera.zoom=z;drawMemberNetwork();
}
function fitMemberNetwork(){
  const s=memberNetworkSession;if(!s)return;const ps=[...s.positions].filter(([id])=>s.visible.has(id)).map(([,p])=>p),r=memberNetworkSpace.getBoundingClientRect();if(!ps.length)return;
  const left=Math.min(...ps.map(p=>p.x))-90,right=Math.max(...ps.map(p=>p.x))+90,top=Math.min(...ps.map(p=>p.y))-50,bottom=Math.max(...ps.map(p=>p.y))+50;
  const z=Math.max(.02,Math.min(.65,(r.width-48)/(right-left),(r.height-48)/(bottom-top)));
  s.camera={zoom:z,panX:(500-(left+right)/2)*z,panY:(340-(top+bottom)/2)*z};drawMemberNetwork();
}
function closeMemberNetwork(){
  const s=memberNetworkSession;if(!s)return;memberNetworkCancelInput();memberNetworkCache={key:s.key,positions:new Map(s.positions),pinned:new Map(s.pinned),options:{...s.options,kinds:s.options.kinds.slice()},camera:{...s.camera}};s.engine?.destroy();memberNetworkSession=null;memberNetworkHost.hidden=true;delete root.dataset.networkOpen;
  for(const [el,inert] of s.inert)if(el.isConnected&&root.contains(el))el.inert=inert;
  memberNetworkNodes.replaceChildren();memberNetworkSvg.replaceChildren();memberNetworkGraph.replaceChildren();memberNetworkResize.disconnect();memberNetworkButton.setAttribute('aria-expanded','false');
  if(!memberReset&&memberNetworkButton.isConnected)memberNetworkButton.focus({preventScroll:true});
}
async function openMemberNetwork(){
  if(memberNetworkSession||memberNetworkOpening||memberReset||space.classList.contains('panning')||nativeGesture)return;
  memberNetworkOpening=true;memberNetworkButton.disabled=true;
  try{await memberLoadNetworkEngine();}
  catch{const live=root.querySelector('#an-live');if(!memberReset&&root.isConnected&&live)live.textContent='관계망 도구를 불러오지 못했어요. 원래 작업판은 그대로예요.';return;}
  finally{memberNetworkOpening=false;memberNetworkButton.disabled=false;}
  if(memberNetworkSession||memberReset||!root.isConnected||space.classList.contains('panning')||nativeGesture)return;
  if(cancelGesture)cancelGesture();closePreview();closeSearch(false);
  const {items,links}=memberNetworkSnapshot(memberScope(),edges),key=JSON.stringify([items.map(n=>[n.id,memberNetworkKind(n)]),links.map(e=>[e.id,e.from,e.to])]),cached=memberNetworkCache?.key===key?memberNetworkCache:null;let positions;
  try{positions=cached?new Map(cached.positions):memberNetworkLayout(items.map(n=>({id:n.id,kind:n.kind,stockIds:eventHoldings(n),width:160,height:76})),links);}
  catch{const live=root.querySelector('#an-live');if(!memberReset&&root.isConnected&&live)live.textContent='관계망을 만들지 못했어요. 원래 작업판은 그대로예요.';return;}
  const s={key,byId:new Map(items.map(n=>[n.id,n])),links,positions:cached?new Map(cached.positions):positions,pinned:cached?new Map(cached.pinned):new Map(),visible:new Set(items.map(n=>n.id)),visibleLinks:links,options:cached?{...cached.options,kinds:cached.options.kinds.slice()}:memberNetworkOptions(),draggable:false,elements:new Map(),paths:[],visuals:new Map(),selected:'',camera:cached?{...cached.camera}:{zoom:1,panX:0,panY:0},inert:[]};memberNetworkSession=s;
  for(const el of root.children)if(el!==memberNetworkHost&&el.tagName!=='STYLE'&&el.tagName!=='SCRIPT'){s.inert.push([el,el.inert]);el.inert=true;}
  root.dataset.networkOpen='true';memberNetworkHost.hidden=false;memberNetworkButton.setAttribute('aria-expanded','true');
  memberNetworkHost.querySelector('h2').textContent='전체 관계망 · 종목 '+items.filter(n=>n.kind==='stock').length+' · 자료 '+items.filter(n=>n.kind!=='stock').length;
  memberNetworkHost.querySelector('footer').textContent='실선: 직접 · 긴 점선: 간접 · 짧은 점선: 참고·미검수 · 혼합 점선: 이력·후속 확인 · 기존 색·굵기 기준 유지 · 탐색 전용 / Esc 복귀';
  for(const e of links){
    const source=items.find(n=>n.id===e.from&&n.kind==='event')||items.find(n=>n.id===e.to&&n.kind==='event'),path=document.createElementNS('http://www.w3.org/2000/svg','path');
    const visual={...memberEdgeVisual(e,source,memberVisualContext())};s.visuals.set(e.id,visual);
    path.classList.add('an-network-edge');path.dataset.semantic=visual.kind;path.dataset.topic=visual.topic;path.style.stroke=visual.color;path.style.strokeWidth=visual.width+'px';path.style.strokeDasharray=visual.dash;path.setAttribute('aria-label',[e.verb,visual.statusLabel,visual.summaryLabel,visual.lineLabel].filter(Boolean).join(' · '));memberNetworkSvg.append(path);s.paths.push([e,path]);
  }
  for(const n of items){
    const b=document.createElement('button');b.type='button';b.className='an-network-node';b.dataset.networkNode=n.id;b.dataset.kind=memberNetworkKind(n);b.setAttribute('aria-label',n.name+' · '+memberNetworkKindText(n));b.setAttribute('aria-pressed','false');b.title=n.name+' · '+memberNetworkKindText(n);
    const dot=document.createElement('i');dot.className='an-network-dot';dot.setAttribute('aria-hidden','true');const face=document.createElement('span');face.className='an-network-face';face.setAttribute('aria-hidden','true');
    const original=nodesEl.querySelector('[data-node="'+n.id+'"] .an-logo');face.append(original?original.cloneNode(true):memberCategoryIcon(memberGroupKey(n)));
    const copy=document.createElement('span'),name=document.createElement('strong'),meta=document.createElement('small');name.className='an-network-label';name.textContent=n.name;meta.className='an-network-meta';meta.textContent=memberNetworkKindText(n)+' · '+(n.asOf||'기준일 미확인');copy.append(name,meta);b.append(dot,face,copy);
    memberNetworkCardDrag(b,n.id);b.dataset.pinned=String(s.pinned.has(n.id));b.onpointerenter=()=>memberNetworkHighlight(n.id);b.onpointerleave=()=>memberNetworkHighlight(s.selected);b.onfocus=()=>memberNetworkHighlight(n.id);b.onblur=()=>memberNetworkHighlight(s.selected);memberNetworkNodes.append(b);s.elements.set(n.id,b);
  }
  try{s.engine=memberCreateNetworkEngine(memberNetworkGraph,items,links,s.positions,s.visuals,{
    viewport(camera){if(memberNetworkSession!==s)return;s.camera=camera;drawMemberNetwork();},
    select(id){if(memberNetworkSession===s&&Date.now()>=(s.input?.suppressUntil||0))memberNetworkSelect(id);},highlight(id){if(memberNetworkSession===s)memberNetworkHighlight(id||s.selected);},
    moveStart(id){if(memberNetworkSession!==s)return;const input=memberNetworkInput(s);input.engineDragging=true;input.engineDrag={mode:'node',id,p:{...s.positions.get(id)},pin:s.pinned.get(id)};},
    move(id,p){if(memberNetworkSession===s){memberNetworkInput(s).engineDragging=true;memberNetworkMove(id,p);}},
    moveEnd(){if(memberNetworkSession===s){const input=memberNetworkInput(s);input.engineDragging=false;input.engineDrag=null;memberNetworkFilter();}},
    moveRelease(){if(memberNetworkSession===s){const input=memberNetworkInput(s);input.engineDragging=false;input.engineDrag=null;}}
  });}catch{closeMemberNetwork();const live=root.querySelector('#an-live');if(!memberReset&&root.isConnected&&live)live.textContent='관계망을 표시하지 못했어요. 원래 작업판은 그대로예요.';return;}
  s.engine?.setDisplay?.(s.options);memberNetworkSyncControls();memberNetworkResize.observe(memberNetworkSpace);memberNetworkSelect('');memberNetworkFilter();if(!cached)fitMemberNetwork();memberNetworkHost.querySelector('[data-network-action=close]').focus({preventScroll:true});
}
memberNetworkButton.onclick=openMemberNetwork;
memberNetworkHost.querySelector('[data-network-action=close]').onclick=closeMemberNetwork;
memberNetworkHost.querySelector('[data-network-action=fit]').onclick=fitMemberNetwork;
memberNetworkHost.querySelector('[data-network-action=in]').onclick=()=>zoomMemberNetwork(memberNetworkSession.camera.zoom*2);
memberNetworkHost.querySelector('[data-network-action=out]').onclick=()=>zoomMemberNetwork(memberNetworkSession.camera.zoom/2);
memberNetworkHost.querySelector('[data-network-action=lock]').onclick=()=>{const s=memberNetworkSession;if(!s)return;s.draggable=!s.draggable;s.engine?.setInteraction?.({draggable:s.draggable});memberNetworkSyncControls();};
memberNetworkHost.querySelector('[data-network-action=arrange]').onclick=memberNetworkArrange;
memberNetworkHost.querySelector('[data-network-action=unpin]').onclick=()=>{const s=memberNetworkSession;if(!s)return;s.pinned.clear();for(const el of s.elements.values())el.dataset.pinned='false';memberNetworkFilter();};
memberNetworkHost.querySelector('[data-network-action=filters-reset]').onclick=()=>{const s=memberNetworkSession;if(!s)return;Object.assign(s.options,{query:'',kinds:['stock','relationship','source','candidate'],depth:0,anchor:'',showOrphans:true});memberNetworkSyncControls();memberNetworkFilter();};
memberNetworkHost.addEventListener('input',e=>{const s=memberNetworkSession,el=e.target;if(!s)return;
  if(el.dataset.networkFilter==='query')s.options.query=el.value;
  if(el.dataset.networkFilter==='orphans')s.options.showOrphans=el.checked;
  if(el.dataset.networkFilter==='depth'){s.options.depth=Number(el.value);s.options.anchor=s.selected||s.options.anchor;}
  if(el.dataset.networkKind)s.options.kinds=[...memberNetworkHost.querySelectorAll('[data-network-kind]:checked')].map(n=>n.dataset.networkKind);
  if(el.hasAttribute('data-network-degree')){s.options.degreeSizing=el.checked;s.engine?.setDisplay?.(s.options);return;}
  if(el.dataset.networkDisplay){s.options[el.dataset.networkDisplay]=Number(el.value);s.engine?.setDisplay?.(s.options);drawMemberNetwork();return;}
  if(el.dataset.networkLayout){s.options[el.dataset.networkLayout]=Number(el.value);return;}
  memberNetworkFilter();
});
// Capture wheel even over HTML cards; focus and vendor defaults must not choose its meaning.
memberNetworkSpace.addEventListener('wheel',memberNetworkWheel,{passive:false,capture:true});
memberNetworkSpace.addEventListener('gesturestart',memberNetworkGestureStart,{passive:false,capture:true});
memberNetworkSpace.addEventListener('gesturechange',memberNetworkGestureChange,{passive:false,capture:true});
memberNetworkSpace.addEventListener('gestureend',memberNetworkGestureEnd,{passive:false,capture:true});
memberNetworkSpace.addEventListener('pointerdown',memberNetworkPointerDown,true);
memberNetworkSpace.addEventListener('pointermove',memberNetworkPointerMove,true);
for(const type of ['pointerup','pointercancel','lostpointercapture'])memberNetworkSpace.addEventListener(type,memberNetworkPointerEnd,true);
for(const type of ['touchstart','touchmove','touchend','touchcancel'])memberNetworkSpace.addEventListener(type,e=>{if(memberNetworkSession){e.preventDefault();e.stopPropagation();}},{passive:false,capture:true});
memberNetworkSpace.addEventListener('click',e=>{if(e.detail!==0&&Date.now()<(memberNetworkSession?.input?.suppressUntil||0)){e.preventDefault();e.stopPropagation();}},true);
memberNetworkSpace.addEventListener('pointerenter',()=>{if(memberNetworkSession)memberNetworkSession.hovered=true;});
memberNetworkSpace.addEventListener('pointerleave',()=>{if(memberNetworkSession)memberNetworkSession.hovered=false;});
memberNetworkHost.addEventListener('keyup',e=>{if(memberNetworkSession&&e.code==='Space'){memberNetworkInput(memberNetworkSession).space=false;e.preventDefault();e.stopPropagation();}},true);
window.addEventListener('blur',memberNetworkCancelInput);
// Do not bubble exploratory actions into the native draft-edit event listeners.
for(const type of ['click','input','change','pointerup','keyup'])memberNetworkHost.addEventListener(type,e=>e.stopPropagation());
memberNetworkHost.addEventListener('keydown',e=>{
  if(!memberNetworkSession)return;e.stopPropagation();
  if(e.key==='Escape'){e.preventDefault();closeMemberNetwork();return;}
  if(e.key==='Tab'){
    const focusable=[...memberNetworkHost.querySelectorAll('button:not([disabled]):not([tabindex="-1"]),input,select,summary,[tabindex="0"]')].filter(el=>!el.hidden&&el.getClientRects().length),first=focusable[0],last=focusable.at(-1);
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}return;
  }
  if(e.code==='Space'&&!e.ctrlKey&&!e.metaKey&&(memberNetworkSpace.contains(e.target)||memberNetworkSession.hovered&&!e.target.closest('button,input,select,textarea,summary,[contenteditable]'))&&!e.target.closest('input,select,textarea,summary,[contenteditable]')){e.preventDefault();memberNetworkInput(memberNetworkSession).space=true;return;}
  if(['INPUT','SELECT','TEXTAREA','BUTTON','SUMMARY'].includes(e.target.tagName)||e.target.closest('button,summary'))return;
  if(e.code==='Space'){e.preventDefault();return;}
  if(['+','=','-','_'].includes(e.key)){e.preventDefault();zoomMemberNetwork(memberNetworkSession.camera.zoom*(['+','='].includes(e.key)?2:.5));return;}
  const delta={ArrowLeft:[40,0],ArrowRight:[-40,0],ArrowUp:[0,40],ArrowDown:[0,-40]}[e.key];
  if(delta){e.preventDefault();memberNetworkSession.camera.panX+=delta[0];memberNetworkSession.camera.panY+=delta[1];drawMemberNetwork();}
},true);
const memberNetworkResize=new ResizeObserver(()=>{if(memberNetworkSession){memberNetworkSession.engine?.resize();drawMemberNetwork();}});
const memberNetworkRemoval=new MutationObserver(()=>{if(!memberNetworkHost.isConnected){closeMemberNetwork();memberNetworkResize.disconnect();memberNetworkRemoval.disconnect();}});memberNetworkRemoval.observe(root,{childList:true});
window.addEventListener('pagehide',()=>{closeMemberNetwork();memberNetworkRemoval.disconnect();});
// Share only public company identities with the separate parent view. No draft,
// notes, positions, quantities, member records or authentication enter this bridge.
const memberStructureRequest=event=>{
  if(memberReset||event.source!==window.parent||!event.data||event.data.type!=='an-company-structure-request'||typeof event.data.request!=='string'||!/^[a-f0-9-]{36}$/.test(event.data.request))return;
  const stocks=memberScope().stocks.slice(0,30).map(n=>({id:n.id,name:n.name,ticker:n.ticker,market:n.market,logo:memberLogos.get(n.market+':'+n.ticker)||null}));
  window.parent.postMessage({type:'an-company-structure-snapshot',request:event.data.request,stocks,flags:memberFlags},'*');
};
window.addEventListener('message',memberStructureRequest);
window.addEventListener('pagehide',()=>window.removeEventListener('message',memberStructureRequest));

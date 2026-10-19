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
#an-map-design .an-network-main{min-height:0;flex:1;display:grid;grid-template-columns:minmax(0,1fr) 240px}
#an-map-design .an-network-space{position:relative;min-width:0;min-height:0;overflow:hidden;touch-action:none;cursor:grab}
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
#an-map-design .an-network-space[data-stage=cards] .an-network-node{display:flex;align-items:center;gap:8px;width:160px;height:76px;padding:10px 12px;background:var(--an-panel);border-radius:14px;text-align:left;box-shadow:0 2px 8px var(--an-shadow)}
#an-map-design .an-network-space[data-stage=cards] .an-network-dot{display:none}
#an-map-design .an-network-space[data-stage=cards] .an-network-face{display:flex;flex:0 0 20px;align-items:center;width:20px;height:20px}
#an-map-design .an-network-face :is(svg,.an-logo){width:20px;height:20px;flex:0 0 20px}
#an-map-design .an-network-face .an-logo img{width:100%;height:100%;object-fit:contain;border-radius:6px}
#an-map-design .an-network-face .an-flag{width:10px;height:10px;right:-2px;bottom:-2px}
#an-map-design .an-network-space[data-stage=cards] .an-network-label{display:-webkit-box;overflow:hidden;-webkit-line-clamp:2;-webkit-box-orient:vertical;font-size:12px;line-height:18px;font-weight:800}
#an-map-design .an-network-space[data-stage=cards] .an-network-meta{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px;font-weight:600;color:var(--an-sub)}
#an-map-design .an-network-node[data-faded=true],#an-map-design .an-network-edge[data-faded=true]{opacity:.12}
#an-map-design .an-network-node[aria-pressed=true]{background:light-dark(#e9edf2,#303945)}
#an-map-design .an-network-inspector{overflow:auto;min-height:0;padding:16px;background:var(--an-panel);scrollbar-gutter:stable}
#an-map-design .an-network-inspector h3{font-size:14px;font-weight:800;margin:0 0 8px;overflow-wrap:anywhere}
#an-map-design .an-network-inspector p{margin:0 0 12px;color:var(--an-sub)}
#an-map-design .an-network-inspector button{display:block;width:100%;text-align:left;min-height:36px;padding:8px 10px;margin-top:8px;background:light-dark(#f8f9fb,#1d242c)}
#an-map-design .an-network-foot{padding:8px 16px;background:var(--an-panel);color:var(--an-sub);font-size:11px}
@media(hover:hover){#an-map-design .an-network-view button:hover{background:light-dark(#f1f3f5,#252c35)}}
@media(max-width:700px){#an-map-design .an-network-main{grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(160px,1fr) auto}#an-map-design .an-network-inspector{max-height:150px;padding:12px 16px}#an-map-design .an-network-head{padding:10px 12px;gap:6px}}
@media(pointer:coarse){#an-map-design .an-network-head button,#an-map-design .an-network-inspector button{min-height:44px}}
`;root.append(memberNetworkStyle);
const memberNetworkButton=document.createElement('button');memberNetworkButton.type='button';memberNetworkButton.className='an-tool';memberNetworkButton.textContent='전체 관계망';memberNetworkButton.setAttribute('aria-expanded','false');root.querySelector('.an-zoom').append(memberNetworkButton);
const memberNetworkHost=document.createElement('section');memberNetworkHost.className='an-network-view';memberNetworkHost.hidden=true;memberNetworkHost.setAttribute('aria-label','전체 관계망 탐색');
memberNetworkHost.innerHTML='<header class="an-network-head"><h2>전체 관계망</h2><button type="button" data-network-action="out" aria-label="관계망 축소">−</button><output aria-label="관계망 배율"></output><button type="button" data-network-action="in" aria-label="관계망 확대">+</button><button type="button" data-network-action="fit">한눈에</button><button type="button" data-network-action="close">원래 보기</button></header><div class="an-network-main"><div class="an-network-space" tabindex="0" role="group" aria-label="고정 관계망 · 드래그로 이동, 휠로 확대축소"><svg aria-hidden="true"></svg><svg class="an-network-grid" aria-hidden="true"><path class="an-network-grid-fine"/><path class="an-network-grid-coarse"/></svg><div class="an-network-graph" aria-hidden="true"></div><div class="an-network-nodes"></div></div><aside class="an-network-inspector" aria-label="관계망 선택 자료"></aside></div><footer class="an-network-foot"></footer>';
root.append(memberNetworkHost);
const memberNetworkSpace=memberNetworkHost.querySelector('.an-network-space'),memberNetworkGraph=memberNetworkHost.querySelector('.an-network-graph'),memberNetworkSvg=memberNetworkHost.querySelector('svg'),memberNetworkNodes=memberNetworkHost.querySelector('.an-network-nodes'),memberNetworkInspector=memberNetworkHost.querySelector('.an-network-inspector');
let memberNetworkSession=null,memberNetworkOpening=false;
function memberNetworkKind(n){return n.kind==='stock'?'stock':memberRelationshipIsMapRecord(n)?'relationship':n.layer==='candidates'?'candidate':'source';}
function memberNetworkKindText(n){return {stock:'종목',relationship:'사건·관계',candidate:'미검수 후보',source:'근거 자료'}[memberNetworkKind(n)];}
function memberNetworkSelect(id){
  const s=memberNetworkSession;if(!s)return;s.selected=s.selected===id?'':id;
  memberNetworkInspector.replaceChildren();
  const n=s.byId.get(s.selected),title=document.createElement('h3'),caption=document.createElement('p');
  title.textContent=n?n.name:s.elements.size?'연결을 선택해 보세요':'표시할 자료가 없어요';
  caption.textContent=n?memberNetworkKindText(n)+' · '+memberRecordDateText(n):'현재 종목·필터 범위의 자료를 모두 표시합니다. 배치는 고정되며, 기존 작업판의 위치와 메모는 바뀌지 않아요.';
  memberNetworkInspector.append(title,caption);
  if(n){
    const connected=s.links.filter(e=>e.from===n.id||e.to===n.id),why=document.createElement('p');
    why.textContent=memberNetworkKind(n)==='source'?'점선은 원문이 해당 종목에 속한다는 뜻이며, 경제적 영향 판정은 아닙니다.':memberNetworkKind(n)==='candidate'?'검수 전 후보입니다. 확인된 관계로 표시하지 않습니다.':'연결 수는 경제적 중요도나 수익 확률이 아닙니다.';memberNetworkInspector.append(why);
    const count=document.createElement('p');count.textContent='표시 연결 '+connected.length+'개';memberNetworkInspector.append(count);
    for(const e of connected){const peer=s.byId.get(e.from===n.id?e.to:e.from),v=s.visuals.get(e.id),line=document.createElement('p');line.textContent=[e.verb||'자료 연결',peer?.name||'종목 미확인',v?.statusLabel,v?.summaryLabel,v?.lineLabel].filter(Boolean).join(' · ');memberNetworkInspector.append(line);}
    for(const evidence of n.evidence||[]){
      try{const url=new URL(evidence.url);if(url.protocol!=='https:'||url.username||url.password||/[\u0000-\u001f\u007f]/.test(decodeURIComponent(evidence.url)))continue;
        const b=document.createElement('button');b.type='button';b.textContent=evidence.source||evidence.title||'원문 열기';b.onclick=()=>memberPort.postMessage({type:'source',url:url.href});memberNetworkInspector.append(b);
      }catch{}
    }
  }
  memberNetworkHighlight(s.selected);
}
function memberNetworkHighlight(id){
  const s=memberNetworkSession;if(!s)return;const linked=new Set(id?[id]:[]);
  for(const e of s.links)if(e.from===id||e.to===id){linked.add(e.from);linked.add(e.to);}
  for(const [key,el] of s.elements){el.dataset.faded=String(!!id&&!linked.has(key));el.setAttribute('aria-pressed',String(key===s.selected));}
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
  const stage=memberNetworkStage(z);memberNetworkSpace.dataset.stage=stage;memberNetworkSpace.style.setProperty('--an-network-label-width',Math.max(40,145*z)+'px');
  s.engine?.setCamera(s.camera);s.engine?.setStage(stage,z);
  renderMemberNetworkGrid();
  for(const [id,el] of s.elements){const p=project(s.positions.get(id));el.style.left=p.x+'px';el.style.top=p.y+'px';el.style.transform='translate(-50%,-50%)'+(stage==='cards'?' scale('+z+')':'');}
  memberNetworkHost.querySelector('output').textContent=Math.round(z*100)+'%';
}
function zoomMemberNetwork(next,at){
  const s=memberNetworkSession;if(!s)return;const r=memberNetworkSpace.getBoundingClientRect(),x=(at?.x??r.width/2)-r.width/2,y=(at?.y??r.height/2)-r.height/2,z=Math.max(.02,Math.min(4,next)),ratio=z/s.camera.zoom;
  s.camera.panX=x-(x-s.camera.panX)*ratio;s.camera.panY=y-(y-s.camera.panY)*ratio;s.camera.zoom=z;drawMemberNetwork();
}
function fitMemberNetwork(){
  const s=memberNetworkSession;if(!s)return;const ps=[...s.positions.values()],r=memberNetworkSpace.getBoundingClientRect();if(!ps.length)return;
  const left=Math.min(...ps.map(p=>p.x))-90,right=Math.max(...ps.map(p=>p.x))+90,top=Math.min(...ps.map(p=>p.y))-50,bottom=Math.max(...ps.map(p=>p.y))+50;
  const z=Math.max(.02,Math.min(1,(r.width-48)/(right-left),(r.height-48)/(bottom-top)));
  s.camera={zoom:z,panX:(500-(left+right)/2)*z,panY:(340-(top+bottom)/2)*z};drawMemberNetwork();
}
function closeMemberNetwork(){
  const s=memberNetworkSession;if(!s)return;s.engine?.destroy();memberNetworkSession=null;memberNetworkHost.hidden=true;delete root.dataset.networkOpen;
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
  const {items,links}=memberNetworkSnapshot(memberScope(),edges);let positions;
  try{positions=memberNetworkLayout(items.map(n=>({id:n.id,kind:n.kind,stockIds:eventHoldings(n),width:160,height:76})),links);}
  catch{const live=root.querySelector('#an-live');if(!memberReset&&root.isConnected&&live)live.textContent='관계망을 만들지 못했어요. 원래 작업판은 그대로예요.';return;}
  const s={byId:new Map(items.map(n=>[n.id,n])),links,positions,elements:new Map(),paths:[],visuals:new Map(),selected:'',camera:{zoom:1,panX:0,panY:0},inert:[]};memberNetworkSession=s;
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
    b.onclick=()=>memberNetworkSelect(n.id);b.onpointerenter=()=>memberNetworkHighlight(n.id);b.onpointerleave=()=>memberNetworkHighlight(s.selected);b.onfocus=()=>memberNetworkHighlight(n.id);b.onblur=()=>memberNetworkHighlight(s.selected);memberNetworkNodes.append(b);s.elements.set(n.id,b);
  }
  try{s.engine=memberCreateNetworkEngine(memberNetworkGraph,items,links,positions,s.visuals,{
    viewport(camera){if(memberNetworkSession!==s)return;s.camera=camera;drawMemberNetwork();},
    select(id){if(memberNetworkSession===s)memberNetworkSelect(id);},highlight(id){if(memberNetworkSession===s)memberNetworkHighlight(id||s.selected);}
  });}catch{closeMemberNetwork();const live=root.querySelector('#an-live');if(!memberReset&&root.isConnected&&live)live.textContent='관계망을 표시하지 못했어요. 원래 작업판은 그대로예요.';return;}
  memberNetworkResize.observe(memberNetworkSpace);memberNetworkSelect('');fitMemberNetwork();memberNetworkHost.querySelector('[data-network-action=close]').focus({preventScroll:true});
}
memberNetworkButton.onclick=openMemberNetwork;
memberNetworkHost.querySelector('[data-network-action=close]').onclick=closeMemberNetwork;
memberNetworkHost.querySelector('[data-network-action=fit]').onclick=fitMemberNetwork;
memberNetworkHost.querySelector('[data-network-action=in]').onclick=()=>zoomMemberNetwork(memberNetworkSession.camera.zoom*2);
memberNetworkHost.querySelector('[data-network-action=out]').onclick=()=>zoomMemberNetwork(memberNetworkSession.camera.zoom/2);
// Do not bubble exploratory actions into the native draft-edit event listeners.
for(const type of ['click','input','change','pointerup','keyup'])memberNetworkHost.addEventListener(type,e=>e.stopPropagation());
memberNetworkHost.addEventListener('keydown',e=>{
  if(!memberNetworkSession)return;e.stopPropagation();
  if(e.key==='Escape'){e.preventDefault();closeMemberNetwork();return;}
  if(e.key==='Tab'){
    const focusable=[...memberNetworkHost.querySelectorAll('button:not([disabled]),[tabindex="0"]')],first=focusable[0],last=focusable.at(-1);
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}return;
  }
  if(e.code==='Space'){e.preventDefault();return;}
  if(['+','=','-','_'].includes(e.key)){e.preventDefault();zoomMemberNetwork(memberNetworkSession.camera.zoom*(['+','='].includes(e.key)?2:.5));return;}
  const delta={ArrowLeft:[40,0],ArrowRight:[-40,0],ArrowUp:[0,40],ArrowDown:[0,-40]}[e.key];
  if(delta){e.preventDefault();memberNetworkSession.camera.panX+=delta[0];memberNetworkSession.camera.panY+=delta[1];drawMemberNetwork();}
},true);
const memberNetworkResize=new ResizeObserver(()=>{if(memberNetworkSession){memberNetworkSession.engine?.resize();drawMemberNetwork();}});
const memberNetworkRemoval=new MutationObserver(()=>{if(!memberNetworkHost.isConnected){closeMemberNetwork();memberNetworkResize.disconnect();memberNetworkRemoval.disconnect();}});memberNetworkRemoval.observe(root,{childList:true});
window.addEventListener('pagehide',()=>{closeMemberNetwork();memberNetworkRemoval.disconnect();});

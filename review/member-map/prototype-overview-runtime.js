// Screen-space titles reuse the real stock/group buttons and their gestures.
// World positions, automatic slots and private draft coordinates stay unchanged.
const memberOverviewStyle=document.createElement('style');
memberOverviewStyle.textContent=`
#an-map-design :is(#an-nodes,#an-member-groups) .an-node[data-overview-title=true]{width:max-content!important;max-width:160px!important;min-height:36px!important;padding:8px 10px!important;gap:6px!important;border:0;box-sizing:border-box;z-index:3}
#an-map-design :is(#an-nodes,#an-member-groups) .an-node[data-overview-title=true]>span:last-child{display:block;min-width:0}
#an-map-design :is(#an-nodes,#an-member-groups) .an-node[data-overview-title=true] strong{font-size:12px!important;line-height:1.5;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#an-map-design :is(#an-nodes,#an-member-groups) .an-node[data-overview-title=true] :is(small,.an-note-badge){display:none!important}
#an-map-design #an-nodes .an-node[data-overview-title=true] .an-logo{width:20px;height:20px;flex:0 0 20px}
#an-map-design #an-member-groups .an-node[data-overview-title=true] .an-category-icon{width:18px;height:18px;flex-basis:18px}
#an-map-design .an-overview-leader{fill:none;stroke:var(--an-line);stroke-width:1;stroke-dasharray:1 4;opacity:.5;pointer-events:none}
@media(pointer:coarse){#an-map-design :is(#an-nodes,#an-member-groups) .an-node[data-overview-title=true]{min-height:44px!important}}
`;document.head.append(memberOverviewStyle);
const memberOverviewLeaders=document.createElementNS('http://www.w3.org/2000/svg','g');
memberOverviewLeaders.setAttribute('aria-hidden','true');memberGroupLines.before(memberOverviewLeaders);
const memberOverviewElements=new Map();
function resetMemberOverviewTitles(){
  for(const [el,style] of memberOverviewElements){
    delete el.dataset.overviewTitle;delete el.dataset.overviewWidth;delete el.dataset.overviewHeight;Object.assign(el.style,style);
  }
  memberOverviewElements.clear();memberOverviewLeaders.replaceChildren();
}
function memberOverviewTitleSlots(items,obstacles,width,height){
  const gap=6,margin=8,occupied=obstacles.map(r=>({...r})),result=[];
  const visible=items.filter(item=>item.x>=0&&item.y>=0&&item.x<=width&&item.y<=height);
  const maxWidth=Math.max(0,...visible.map(item=>item.w)),maxHeight=Math.max(0,...visible.map(item=>item.h));
  const columns=Math.max(1,Math.floor((width-margin*2+gap)/(maxWidth+gap)));
  const crowded=visible.length*(maxHeight+gap)>height-margin*2;
  const centers=Array.from({length:columns},(_,i)=>margin+(width-margin*2)/columns*(i+.5));
  const intersects=(a,b)=>a.left<b.right+gap&&a.right>b.left-gap&&a.top<b.bottom+gap&&a.bottom>b.top-gap;
  for(const item of items){
    const {x,y,w,h}=item;if(x<0||y<0||x>width||y>height){result.push(null);continue;}
    let slot=null;
    const preferred=crowded&&columns>1?centers.reduce((best,c)=>Math.abs(c-x)<Math.abs(best-x)?c:best,centers[0]):x;
    const cx=Math.max(margin+w/2,Math.min(width-margin-w/2,preferred));
    const cy=Math.max(margin+h/2,Math.min(height-margin-h/2,y));
    const rows=Math.ceil(height/(h+gap));
    for(let row=0;row<=rows&&!slot;row++)for(const sign of row?(item.group?[-1]:[-1,1]):[0]){
      const py=cy+row*(h+gap)*sign;
      const xs=crowded&&columns>1?[cx,...centers.filter(c=>c!==cx)]:[cx,cx-(w+gap),cx+w+gap];
      for(const px of xs){
        const r={left:px-w/2,right:px+w/2,top:py-h/2,bottom:py+h/2};
        if(r.left<margin||r.right>width-margin||r.top<margin||r.bottom>height-margin||occupied.some(o=>intersects(r,o)))continue;
        slot={x:px,y:py,...r};occupied.push(r);break;
      }
      if(slot)break;
    }
    result.push(slot);
  }
  return result;
}
function drawMemberOverviewTitles(){
  if(state.zoom>=.65)return;
  const entries=[...holdings.filter(shown).map(n=>({id:n.id,n,el:nodesEl.querySelector('[data-node="'+n.id+'"]')})),
    ...[...memberGroups.values()].filter(g=>g.records.length&&!g.button.hidden).map(g=>({id:g.id,n:g,el:g.button}))]
    .filter(({el})=>el&&!el.hidden);
  // Group titles occupy the band above their anchors. Sources expand below it;
  // opening or closing a source must not reshuffle the title band.
  const canvas=space.getBoundingClientRect(),obstacles=[...noteEls.values()]
    .filter(el=>!el.hidden).map(el=>{const r=el.getBoundingClientRect();return {left:r.left-canvas.left,right:r.right-canvas.left,top:r.top-canvas.top,bottom:r.bottom-canvas.top};});
  // Stable identity order keeps hover/selection redraws from changing title rows.
  entries.sort((a,b)=>Number(a.n.kind!=='stock')-Number(b.n.kind!=='stock')||a.id.localeCompare(b.id));
  const items=entries.map(({n,el})=>{
    el.dataset.summaryIcon='false';
    const p=point(n),w=el.offsetWidth,h=el.offsetHeight;
    el.dataset.overviewWidth=String(w);el.dataset.overviewHeight=String(h);
    memberOverviewElements.set(el,{left:el.style.left,top:el.style.top,transform:el.style.transform});el.dataset.overviewTitle='true';
    const group=n.kind!=='stock',height=el.offsetHeight;
    return {x:p.x,y:group?p.y-height/2-h*state.zoom/2-6:p.y,w:el.offsetWidth,h:height,group,anchor:p};
  });
  const slots=memberOverviewTitleSlots(items,obstacles,space.clientWidth,space.clientHeight);
  entries.forEach(({el},i)=>{
    const slot=slots[i],p=items[i];
    if(!slot){delete el.dataset.overviewTitle;return;}
    el.style.left=slot.x+'px';el.style.top=slot.y+'px';el.style.transform='translate(-50%,-50%)';
    if(Math.hypot(slot.x-p.anchor.x,slot.y-p.anchor.y)>3){
      const path=document.createElementNS(memberOverviewLeaders.namespaceURI,'path');path.setAttribute('class','an-overview-leader');
      path.setAttribute('d','M '+p.anchor.x+' '+p.anchor.y+' L '+slot.x+' '+slot.y);path.setAttribute('title','축소 제목 위치 안내 · 관계선 아님');memberOverviewLeaders.append(path);
    }
  });
}
const memberOverviewBaseDrawGroups=drawMemberGroups;
drawMemberGroups=function(){
  resetMemberOverviewTitles();memberOverviewBaseDrawGroups();drawMemberOverviewTitles();
  // Recheck the selected relation against the actual, readable title rectangles.
  syncMemberEdgeLabels();applyMemberEdgeVisuals();
};
const memberOverviewBaseRenderMap=renderMap;
renderMap=function(){resetMemberOverviewTitles();memberOverviewBaseRenderMap();};

// The pinned vendor is inline in the existing sandbox; no CSP widening or CDN.
function memberLoadNetworkEngine(){
  return typeof window.cytoscape==='function'?Promise.resolve():Promise.reject(new Error('Graph engine unavailable'));
}
function memberCreateNetworkEngine(container,items,links,positions,visuals,hooks){
  const nodeIds=new Map(items.map((item,index)=>[item.id,'n'+index])),originalIds=new Map([...nodeIds].map(([id,key])=>[key,id]));
  const probe=document.createElement('span'),colors=new Map();probe.style.display='none';root.append(probe);
  const resolveColor=(value,topic='holding')=>{const key=topic+'|'+value;if(colors.has(key))return colors.get(key);
    probe.dataset.topic=topic;probe.style.color=value;const result=getComputedStyle(probe).color;colors.set(key,result);return result;};
  const nodeLine=resolveColor('var(--an-line)'),nodeText=resolveColor('var(--an-text)'),nodeAccent=resolveColor('var(--an-accent)');
  const elements=items.map(item=>({data:{id:nodeIds.get(item.id),kind:memberNetworkKind(item)},position:{...positions.get(item.id)}}));
  for(const [index,edge]of links.entries()){
    const visual=visuals.get(edge.id),dash=String(visual?.dash||'').trim().split(/[ ,]+/).map(Number).filter(n=>Number.isFinite(n)&&n>0);
    elements.push({data:{id:'e'+index,source:nodeIds.get(edge.from),target:nodeIds.get(edge.to),
      color:resolveColor(visual.color,visual.topic),width:visual.width,lineStyle:dash.length?'dashed':'solid',dash:dash.length?dash:[1,1],semantic:visual.kind}});
  }
  probe.remove();
  let cy,destroyed=false,lastStage='',lastZoom=0,draggable=false,drag=null,suppressedTap='';
  let visible=new Set(nodeIds.keys());
  const display={nodeScale:1,edgeScale:1,labels:false,degreeSizing:false};
  const names=new Map(items.map(item=>[nodeIds.get(item.id),typeof item.name==='string'?item.name:'']));
  // Distinct neighbors from verified links only: connectivity, not importance.
  const neighbors=new Map([...nodeIds.values()].map(id=>[id,new Set()]));
  for(const edge of links){const a=nodeIds.get(edge.from),b=nodeIds.get(edge.to);
    if(a!==b&&neighbors.has(a)&&neighbors.has(b)){neighbors.get(a).add(b);neighbors.get(b).add(a);}}
  let degrees=new Map([...neighbors].map(([id,peers])=>[id,peers.size]));
  try{
    cy=window.cytoscape({container,elements,layout:{name:'preset',fit:false,animate:false},minZoom:.02,maxZoom:4,
      autolock:true,autoungrabify:true,autounselectify:true,boxSelectionEnabled:false,
      userZoomingEnabled:false,userPanningEnabled:true,
      style:[
        {selector:'node',style:{width:14,height:14,'background-color':nodeLine,'overlay-opacity':0,label:''}},
        {selector:'node[kind="stock"]',style:{width:24,height:24,'background-color':nodeText}},
        {selector:'node[kind="relationship"]',style:{'background-color':nodeAccent}},
        {selector:'edge',style:{width:'data(width)','line-color':'data(color)','line-style':'data(lineStyle)',
          'line-dash-pattern':'data(dash)','curve-style':'straight','opacity':.82,'overlay-opacity':0}},
        {selector:'.an-network-muted',style:{opacity:.12}},
        {selector:'node.an-network-card',style:{opacity:0}}
      ]});
    const getCamera=()=>{const z=cy.zoom(),p=cy.pan(),r=container.getBoundingClientRect();return{zoom:z,panX:p.x-r.width/2+500*z,panY:p.y-r.height/2+340*z};};
    const applyStage=(stage,zoom)=>{lastStage=stage;lastZoom=zoom;cy.batch(()=>{
      const nodes=cy.nodes();nodes.removeClass('an-network-card');if(stage==='cards')nodes.addClass('an-network-card');
      nodes.forEach(node=>{const connectivity=display.degreeSizing?Math.min(2.2,1+Math.sqrt(degrees.get(node.id())||0)*.16):1;
        const size=(node.data('kind')==='stock'?10:6)*display.nodeScale*connectivity/zoom;
        node.style({width:size,height:size,label:display.labels&&stage==='names'?names.get(node.id()):'',
          color:nodeText,'font-family':"Pretendard, -apple-system, BlinkMacSystemFont, sans-serif",'font-weight':700,'font-size':11/zoom});});
      cy.edges().forEach(edge=>edge.style({width:edge.data('width')*display.edgeScale/zoom,'line-dash-pattern':edge.data('dash').map(value=>value/zoom)}));
    });};
    cy.on('viewport',()=>{if(!destroyed)hooks.viewport(getCamera());});
    // Suppress only the release of a moved gesture, not the next real click.
    cy.on('tapstart','node',()=>{if(!destroyed)suppressedTap='';});
    cy.on('grab','node',event=>{if(destroyed||!draggable)return;
      const id=event.target.id(),p=event.target.position();suppressedTap='';
      drag=visible.has(originalIds.get(id))?{id,x:p.x,y:p.y}:null;
      if(drag)hooks.moveStart?.(originalIds.get(id));
    });
    cy.on('drag','node',event=>{if(destroyed||!draggable||!drag||drag.id!==event.target.id())return;
      const id=originalIds.get(drag.id),p=event.target.position();
      if(!visible.has(id)||!Number.isFinite(p.x)||!Number.isFinite(p.y)||p.x===drag.x&&p.y===drag.y)return;
      drag={id:drag.id,x:p.x,y:p.y};suppressedTap=drag.id;hooks.move?.(id,{x:p.x,y:p.y});
    });
    cy.on('free','node',event=>{if(destroyed||!drag||drag.id!==event.target.id())return;
      const id=drag.id,moved=suppressedTap===id;drag=null;if(moved)hooks.moveEnd?.(originalIds.get(id));hooks.moveRelease?.(originalIds.get(id));});
    cy.on('tap','node',event=>{const key=event.target.id(),id=originalIds.get(key);
      if(!destroyed&&visible.has(id)&&key!==suppressedTap)hooks.select(id);});
    cy.on('mouseover','node',event=>{if(!destroyed)hooks.highlight(originalIds.get(event.target.id()));});
    cy.on('mouseout','node',()=>{if(!destroyed)hooks.highlight('');});
    return{
      getCamera,
      setCamera(camera){if(destroyed)return;const r=container.getBoundingClientRect(),current=getCamera();
        if(['zoom','panX','panY'].every(key=>Math.abs(current[key]-camera[key])<1e-8))return;
        cy.viewport({zoom:camera.zoom,pan:{x:r.width/2-500*camera.zoom+camera.panX,y:r.height/2-340*camera.zoom+camera.panY}});},
      resize(){if(!destroyed)cy.resize();},
      setStage(stage,zoom=cy.zoom()){if(destroyed||stage===lastStage&&Math.abs(zoom-lastZoom)<1e-8)return;
        applyStage(stage,zoom);},
      setVisible(ids){if(destroyed||!ids||typeof ids.has!=='function')return;
        visible=new Set([...nodeIds.keys()].filter(id=>ids.has(id)));
        degrees=new Map([...neighbors].map(([id,peers])=>[id,[...peers].filter(peer=>visible.has(originalIds.get(peer))).length]));
        cy.batch(()=>{
          cy.nodes().forEach(node=>node.style('display',visible.has(originalIds.get(node.id()))?'element':'none'));
          cy.edges().forEach(edge=>edge.style('display',visible.has(originalIds.get(edge.data('source')))&&visible.has(originalIds.get(edge.data('target')))?'element':'none'));
        });if(display.degreeSizing)applyStage(lastStage||'dots',lastZoom||cy.zoom());},
      setPositions(map){if(destroyed||!map||typeof map.get!=='function')return;
        const locked=cy.autolock();cy.autolock(false);
        try{cy.batch(()=>cy.nodes().forEach(node=>{
          const p=map.get(originalIds.get(node.id()));if(!p||!Number.isFinite(p.x)||!Number.isFinite(p.y))return;
          const wasLocked=node.locked();if(wasLocked)node.unlock();
          try{node.position({x:p.x,y:p.y});}finally{if(wasLocked)node.lock();}
        }));}finally{cy.autolock(locked);}
      },
      setInteraction(options){if(destroyed||typeof options?.draggable!=='boolean')return;
        if(draggable===options.draggable)return;
        draggable=options.draggable;drag=null;cy.autolock(!draggable);cy.autoungrabify(!draggable);
      },
      setDisplay(options={}){if(destroyed||!options)return;let changed=false;
        for(const key of ['nodeScale','edgeScale'])if(Number.isFinite(options[key])&&options[key]>0&&options[key]!==display[key]){display[key]=options[key];changed=true;}
        for(const key of ['labels','degreeSizing'])if(typeof options[key]==='boolean'&&options[key]!==display[key]){display[key]=options[key];changed=true;}
        if(changed)applyStage(lastStage||'dots',lastZoom||cy.zoom());
      },
      highlight(id){if(destroyed)return;cy.batch(()=>{
        cy.elements().removeClass('an-network-muted');const key=nodeIds.get(id);if(!key)return;
        const selected=cy.getElementById(key),keep=selected.closedNeighborhood();cy.elements().difference(keep).addClass('an-network-muted');
      });},
      destroy(){if(destroyed)return;destroyed=true;cy.destroy();}
    };
  }catch(error){cy?.destroy();throw error;}
}

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
  let cy,destroyed=false,lastStage='',lastZoom=0;
  try{
    cy=window.cytoscape({container,elements,layout:{name:'preset',fit:false,animate:false},minZoom:.02,maxZoom:4,
      autolock:true,autoungrabify:true,autounselectify:true,boxSelectionEnabled:false,
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
    cy.on('viewport',()=>{if(!destroyed)hooks.viewport(getCamera());});
    cy.on('tap','node',event=>{if(!destroyed)hooks.select(originalIds.get(event.target.id()));});
    cy.on('mouseover','node',event=>{if(!destroyed)hooks.highlight(originalIds.get(event.target.id()));});
    cy.on('mouseout','node',()=>{if(!destroyed)hooks.highlight('');});
    return{
      getCamera,
      setCamera(camera){if(destroyed)return;const r=container.getBoundingClientRect(),current=getCamera();
        if(['zoom','panX','panY'].every(key=>Math.abs(current[key]-camera[key])<1e-8))return;
        cy.viewport({zoom:camera.zoom,pan:{x:r.width/2-500*camera.zoom+camera.panX,y:r.height/2-340*camera.zoom+camera.panY}});},
      resize(){if(!destroyed)cy.resize();},
      setStage(stage,zoom=cy.zoom()){if(destroyed||stage===lastStage&&Math.abs(zoom-lastZoom)<1e-8)return;
        lastStage=stage;lastZoom=zoom;cy.batch(()=>{
          const nodes=cy.nodes();nodes.removeClass('an-network-card');if(stage==='cards')nodes.addClass('an-network-card');
          nodes.forEach(node=>{const size=(node.data('kind')==='stock'?10:6)/zoom;node.style({width:size,height:size});});
          cy.edges().forEach(edge=>edge.style({width:edge.data('width')/zoom,'line-dash-pattern':edge.data('dash').map(value=>value/zoom)}));
        });},
      highlight(id){if(destroyed)return;cy.batch(()=>{
        cy.elements().removeClass('an-network-muted');const key=nodeIds.get(id);if(!key)return;
        const selected=cy.getElementById(key),keep=selected.closedNeighborhood();cy.elements().difference(keep).addClass('an-network-muted');
      });},
      destroy(){if(destroyed)return;destroyed=true;cy.destroy();}
    };
  }catch(error){cy?.destroy();throw error;}
}

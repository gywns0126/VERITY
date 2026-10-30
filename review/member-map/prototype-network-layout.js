// Static geometry only. links are the sole adjacency source; stockIds, labels
// and categories never manufacture edges or economic importance. No DOM/camera.
function memberNetworkKindFor(item){
  if(['stock','relationship','source','candidate'].includes(item?.networkKind))return item.networkKind;
  if(item?.kind==='stock')return 'stock';
  if(item?.layer!=='candidates'&&(item?.recordKind==='event'||item?.recordKind==='relationship'&&item?.layer==='relationships'))return 'relationship';
  return item?.layer==='candidates'?'candidate':'source';
}
function memberNetworkExplore(items,links,{query='',kinds,showOrphans=true,anchor='',depth=0}={}){
  const allowedKinds=kinds===undefined?new Set(['stock','relationship','source','candidate'])
    :new Set(Array.isArray(kinds)||kinds instanceof Set?[...kinds].filter(kind=>['stock','relationship','source','candidate'].includes(kind)):[]);
  const rows=Array.isArray(items)?items:[],edges=Array.isArray(links)?links:[];
  const byId=new Map(),visible=new Set();
  for(const item of rows)if(typeof item?.id==='string'&&item.id)byId.set(item.id,item);
  for(const [id,item] of byId)if(allowedKinds.has(memberNetworkKindFor(item)))visible.add(id);
  const term=typeof query==='string'?query.trim().toLowerCase():'';
  const matches=item=>{
    if(!term)return true;
    const values=[item.name,item.ticker,item.id,item.title,item.source,item.explanation];
    if(Array.isArray(item.evidence))for(const evidence of item.evidence)values.push(evidence?.source,evidence?.title,evidence?.explanation);
    return values.some(value=>typeof value==='string'&&value.toLowerCase().includes(term));
  };
  if(term)for(const id of [...visible])if(!matches(byId.get(id)))visible.delete(id);
  const localDepth=Number.isInteger(depth)&&depth>0&&typeof anchor==='string'&&anchor?Math.min(3,depth):0;
  if(localDepth){
    if(!byId.has(anchor)||!allowedKinds.has(memberNetworkKindFor(byId.get(anchor))))visible.clear();
    else{
      const adjacency=new Map([...byId.keys()].filter(id=>allowedKinds.has(memberNetworkKindFor(byId.get(id)))).map(id=>[id,new Set()]));
      for(const link of edges)if(adjacency.has(link?.from)&&adjacency.has(link?.to)){
        adjacency.get(link.from).add(link.to);adjacency.get(link.to).add(link.from);
      }
      const distance=new Map([[anchor,0]]),queue=[anchor];
      for(let head=0;head<queue.length;head++){
        const id=queue[head],nextDistance=distance.get(id)+1;if(nextDistance>localDepth)continue;
        for(const next of adjacency.get(id)||[])if(!distance.has(next)){distance.set(next,nextDistance);queue.push(next);}
      }
      for(const id of [...visible])if(!distance.has(id))visible.delete(id);
    }
  }
  let visibleLinks=edges.filter(link=>visible.has(link?.from)&&visible.has(link?.to));
  if(showOrphans===false){
    const incident=new Set();for(const link of visibleLinks){incident.add(link.from);incident.add(link.to);}
    for(const id of [...visible])if(!incident.has(id))visible.delete(id);
    visibleLinks=visibleLinks.filter(link=>visible.has(link.from)&&visible.has(link.to));
  }
  return {ids:visible,links:visibleLinks};
}
function memberNetworkLayout(items,links,options={}){
  options=options&&typeof options==='object'?options:{};
  const compare=(a,b)=>a<b?-1:a>b?1:0;
  const sqrt=Math.sqrt,hypot=Math.hypot,min=Math.min,max=Math.max;
  const ordered=items.slice().sort((a,b)=>compare(a.id,b.id)),index=new Map();
  const size=(value,fallback)=>Number.isFinite(value)&&value>0?value:fallback;
  const nonnegative=(value,fallback)=>Number.isFinite(value)&&value>=0?value:fallback;
  const linkDistance=nonnegative(options.linkDistance,150),repulsion=nonnegative(options.repulsion,9000);
  const pinInput=options.pinned&&typeof options.pinned.entries==='function'?options.pinned:null;
  const pinned=new Map(),pinnedWorld=new Map();
  const nodes=ordered.map((item,i)=>{
    if(typeof item.id!=='string'||!item.id||index.has(item.id))throw new TypeError('Network items require unique nonempty string IDs');
    index.set(item.id,i);
    return {id:item.id,stock:item.kind==='stock',w:size(item.width,160),h:size(item.height,64),x:0,y:0};
  });
  if(pinInput)for(const [id,point] of pinInput)if(index.has(id)&&Number.isFinite(point?.x)&&Number.isFinite(point?.y)){
    // Pins use the public layout frame; the force/placement work uses its
    // origin-centered frame, then translates free nodes back to that frame.
    pinned.set(id,{x:point.x-500,y:point.y-340});pinnedWorld.set(id,{x:point.x,y:point.y});
  }
  const n=nodes.length;if(!n)return new Map();
  const adjacency=nodes.map(()=>new Set());
  for(const link of links){
    const a=index.get(link.from),b=index.get(link.to);
    if(a===undefined||b===undefined||a===b)continue;
    adjacency[a].add(b);adjacency[b].add(a);
  }
  // Sort once: duplicate/reversed edges and reordered input give identical sums.
  const neighbors=adjacency.map(set=>[...set].sort((a,b)=>a-b)),pairs=[];
  neighbors.forEach((list,a)=>{for(const b of list)if(a<b)pairs.push([a,b]);});
  const roots=nodes.flatMap((node,i)=>node.stock?[i]:[]),owner=nodes.map(()=>-1),queue=roots.slice();
  roots.forEach(i=>{owner[i]=i;});
  for(let q=0;q<queue.length;q++){
    const a=queue[q];for(const b of neighbors[a])if(owner[b]===-1){owner[b]=owner[a];queue.push(b);}
  }
  const radius=roots.length>1?Math.max(260,Math.sqrt(n/roots.length)*110+160):0;
  roots.forEach((i,k)=>{
    const angle=-Math.PI/2+2*Math.PI*k/roots.length;
    nodes[i].x=Math.cos(angle)*radius;nodes[i].y=Math.sin(angle)*radius;
  });
  const rank=new Map(),golden=Math.PI*(3-Math.sqrt(5));
  nodes.forEach((node,i)=>{
    if(node.stock)return;
    const peers=neighbors[i].filter(j=>nodes[j].stock),root=owner[i];
    const k=rank.get(root)||0;rank.set(root,k+1);
    const anchor=peers.length>1?{
      x:peers.reduce((sum,j)=>sum+nodes[j].x,0)/peers.length,
      y:peers.reduce((sum,j)=>sum+nodes[j].y,0)/peers.length
    }:root>=0?nodes[root]:{x:0,y:0};
    const r=peers.length>1?24:110*Math.sqrt(k+1),angle=k*golden;
    node.x=anchor.x+Math.cos(angle)*r;node.y=anchor.y+Math.sin(angle)*r*.8;
    node.homeX=anchor.x;node.homeY=anchor.y;
  });
  for(const [id,point] of pinned){const node=nodes[index.get(id)];node.x=point.x;node.y=point.y;}
  // Fixed synchronous work, not a running force simulation: O(32*(N²+E)).
  // Stocks are stable geometric anchors; actual links attract their endpoints.
  for(let iteration=0;iteration<32;iteration++){
    const dx=new Float64Array(n),dy=new Float64Array(n);
    for(let a=0;a<n;a++)for(let b=a+1;b<n;b++){
      let x=nodes[b].x-nodes[a].x,y=nodes[b].y-nodes[a].y,d2=x*x+y*y;
      if(d2<1e-6){const angle=(a+1)*golden+(b+1);x=Math.cos(angle);y=Math.sin(angle);d2=1;}
      const distance=sqrt(d2),force=min(18,repulsion/d2),fx=x/distance*force,fy=y/distance*force;
      dx[a]-=fx;dy[a]-=fy;dx[b]+=fx;dy[b]+=fy;
    }
    for(const [a,b] of pairs){
      const x=nodes[b].x-nodes[a].x,y=nodes[b].y-nodes[a].y,distance=hypot(x,y)||1;
      const force=(distance-linkDistance)*.035/sqrt(max(1,min(neighbors[a].length,neighbors[b].length)));
      dx[a]+=x/distance*force;dy[a]+=y/distance*force;dx[b]-=x/distance*force;dy[b]-=y/distance*force;
    }
    const step=18*(1-iteration/40);
    nodes.forEach((node,i)=>{
      if(node.stock||pinned.has(node.id))return;
      dx[i]+=(node.homeX-node.x)*.012;dy[i]+=(node.homeY-node.y)*.012;
      const length=hypot(dx[i],dy[i])||1,scale=min(1,step/length);
      node.x+=dx[i]*scale;node.y+=dy[i]*scale;
    });
  }
  // Exact rectangle clearance after relaxation. A spatial hash bounds neighbor
  // checks; finite square-ring candidates stay local to each graph-derived home.
  const gap=16,cellW=Math.max(...nodes.map(p=>p.w))+gap+1,cellH=Math.max(...nodes.map(p=>p.h))+gap+1;
  const cells=new Map(),placed=new Map();
  const bounds=p=>({left:p.x-p.w/2,right:p.x+p.w/2,top:p.y-p.h/2,bottom:p.y+p.h/2});
  function visit(area,callback){
    for(let x=Math.floor(area.left/cellW);x<=Math.floor(area.right/cellW);x++)
      for(let y=Math.floor(area.top/cellH);y<=Math.floor(area.bottom/cellH);y++)if(callback(x+':'+y)===false)return false;
    return true;
  }
  function free(p){
    const b=bounds(p),expanded={left:b.left-gap,right:b.right+gap,top:b.top-gap,bottom:b.bottom+gap};
    return visit(expanded,key=>!(cells.get(key)||[]).some(a=>b.left<a.right+gap&&b.right>a.left-gap&&b.top<a.bottom+gap&&b.bottom>a.top-gap));
  }
  let right=-Infinity;
  for(const [id] of pinned){
    const node=nodes[index.get(id)],point=pinned.get(id),fixed={...node,x:point.x,y:point.y},box=bounds(fixed);
    placed.set(id,fixed);visit(box,key=>{if(!cells.has(key))cells.set(key,[]);cells.get(key).push(box);});right=Math.max(right,box.right);
  }
  const placementOrder=nodes.map((_,i)=>i).filter(i=>!pinned.has(nodes[i].id))
    .sort((a,b)=>Number(nodes[b].stock)-Number(nodes[a].stock)||neighbors[b].length-neighbors[a].length||a-b);
  const maxRing=Math.ceil(Math.sqrt(4*n+1));
  for(const i of placementOrder){
    const node=nodes[i];let point=null;
    for(let ring=0;ring<=maxRing&&!point;ring++){
      // Ordered perimeter only, O(N) candidate cells per node in the worst case.
      const tryAt=(x,y)=>{const p={...node,x:node.x+x*cellW,y:node.y+y*cellH};if(free(p)){point=p;return true;}return false;};
      if(!ring){tryAt(0,0);continue;}
      for(let x=-ring;x<=ring&&!point;x++){tryAt(x,-ring);if(!point)tryAt(x,ring);}
      for(let y=-ring+1;y<ring&&!point;y++){tryAt(-ring,y);if(!point)tryAt(ring,y);}
    }
    // Explicit finite fallback, never omit a node even for atypical dimensions.
    if(!point)point={...node,x:right+gap+node.w/2+1};
    const box=bounds(point);visit(box,key=>{if(!cells.has(key))cells.set(key,[]);cells.get(key).push(box);});
    placed.set(node.id,point);right=Math.max(right,box.right);
  }
  const boxes=[...placed.values()].map(bounds),cx=(Math.min(...boxes.map(b=>b.left))+Math.max(...boxes.map(b=>b.right)))/2;
  const cy=(Math.min(...boxes.map(b=>b.top))+Math.max(...boxes.map(b=>b.bottom)))/2;
  return new Map(nodes.map(node=>{
    const p=placed.get(node.id),pin=pinnedWorld.get(node.id);
    return [node.id,pin?{x:pin.x,y:pin.y}:pinned.size?{x:p.x+500,y:p.y+340}:{x:p.x-cx+500,y:p.y-cy+340}];
  }));
}

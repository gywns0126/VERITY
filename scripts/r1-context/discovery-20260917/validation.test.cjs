const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),esbuild=require('esbuild');
const candidate=fs.readFileSync(process.env.DISCOVERY_TEST_SOURCE || path.resolve(__dirname,'../../../framer-components/public-probe/PublicDiscovery.tsx'),'utf8');
const props={stockUrl:'kr',usStockUrl:'us',usSmallcapUrl:'small',insiderUrl:'insider',usInsiderUrl:'us-insider',flowUrl:'flow',forensicsUrl:'forensics'};
const kr={ticker:'005930',name:'검수 국내',market:'KOSPI',sector:'반도체',facts:{PER:10,ROE:12,PBR:1,'시가총액':'100조'}};
const us={ticker:'AAPL',name:'검수 미국',market:'NASDAQ',sector:'IT',facts:{PER:20,ROE:15,PBR:2,'시가총액':'200조'}};
const payload={kr:{stocks:[kr]},us:{stocks:[us]},small:{stocks:[]},insider:{stocks:[]},'us-insider':{stocks:[]},flow:{flows:{'005930':[{foreign_net:4}]}},forensics:{stocks:[]}};
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve}}
function runtime(source=candidate,{search='',fetcher,rootWidth=1100}={}){
 let cursor=0,dirty=true,tree,effects=[],slots=[],cleanups=[],renders=0;
 const calls=[];
 const changed=(a,b)=>!a||!b||a.length!==b.length||a.some((v,i)=>!Object.is(v,b[i]));
 const react={
  useState(init){const i=cursor++;if(!slots[i])slots[i]={v:typeof init==='function'?init():init};return[slots[i].v,v=>{const n=typeof v==='function'?v(slots[i].v):v;if(!Object.is(n,slots[i].v)){slots[i].v=n;dirty=true}}]},
  useMemo(fn,deps){const i=cursor++;if(!slots[i]||changed(slots[i].deps,deps))slots[i]={v:fn(),deps};return slots[i].v},
  useRef(){const i=cursor++;if(!slots[i])slots[i]={v:{current:{getBoundingClientRect:()=>({width:rootWidth})}}};return slots[i].v},
  useEffect(fn,deps){const i=cursor++;if(!slots[i]||changed(slots[i].deps,deps)){slots[i]={deps};effects.push(()=>{cleanups[i]?.();cleanups[i]=fn()})}},
 };
 const jsx=(type,props,key)=>({type,props:props||{},key});
 const moduleBox={exports:{}};
 const injected=';export {validDiscoveryDoc,discoveryRangeError,discoveryRows,loadDiscoverySources};';
 const js=esbuild.transformSync(source+'\nexport {SCREENS};'+injected,{loader:'tsx',format:'cjs',jsx:'automatic'}).code;
 const context={module:moduleBox,exports:moduleBox.exports,URLSearchParams,AbortController,setTimeout,clearTimeout,
  window:{location:{search,href:''}},
  ResizeObserver:class{constructor(cb){this.cb=cb}observe(el,options){this.cb([{borderBoxSize:[{inlineSize:rootWidth}],contentRect:{width:rootWidth-36}}]);calls.push({resize:options})}disconnect(){}},
  fetch:async(url,options)=>{calls.push({url,options});return fetcher?fetcher(url,options):{ok:true,json:async()=>payload[url]||{logos:{}}}},
  require:id=>id==='react'?react:id==='react/jsx-runtime'?{jsx,jsxs:jsx,Fragment:'fragment'}:id==='framer'?{ControlType:{},addPropertyControls(){},RenderTarget:{canvas:0,current:()=>1}}:{}
 };
 vm.runInNewContext(js,context);
 let currentProps=props;
 async function settle(){for(let tick=0;tick<35;tick++){
  if(dirty){dirty=false;cursor=0;tree=moduleBox.exports.default(currentProps);renders++;const pending=effects;effects=[];pending.forEach(fn=>fn())}
  await new Promise(r=>setImmediate(r));
 }assert.ok(!dirty,'render cycle must settle');return tree}
 function nodes(node,out=[]){if(Array.isArray(node)){node.forEach(n=>nodes(n,out));return out}if(node&&typeof node==='object'&&node.props){out.push(node);nodes(node.props.children,out)}return out}
 function text(node){if(Array.isArray(node))return node.map(text).join('');if(node===null||node===undefined||typeof node==='boolean')return'';if(typeof node!=='object')return String(node);return text(node.props?.children)}
 return {exports:moduleBox.exports,calls,settle,nodes:()=>nodes(tree),text:(node=tree)=>text(node),get renders(){return renders},find:f=>nodes(tree).find(f),setProps:p=>{currentProps={...currentProps,...p};dirty=true},dispose:()=>cleanups.forEach(fn=>fn?.())};
}
test('delayed source preserves requested screen',async()=>{
 const flow=deferred();const r=runtime(candidate,{search:'?screen=foreign_buy',fetcher:async u=>u==='flow'?flow.promise:{ok:true,json:async()=>payload[u]}});
 try{await r.settle();assert.match(r.text(),/외국인이 최근 순매수한 회사/);flow.resolve({ok:true,json:async()=>payload.flow});await r.settle();assert.match(r.text(),/외국인이 최근 순매수한 회사/);assert.match(r.text(),/확인된 자료에서 1종목/)}finally{r.dispose()}
});
test('empty valid report finishes loading instead of indefinite shimmer',async()=>{
 const r=runtime(candidate,{fetcher:async()=>({ok:true,json:async()=>({stocks:[]})})});
 try{await r.settle();assert.match(r.text(),/현재 수신된 종목 자료가 비어/);assert.ok(r.find(n=>n.props['aria-label']==='업종 필터'))}finally{r.dispose()}
});
test('all report failures differ from no matching companies; retry recovers without new URLs',async()=>{
 let fail=true;const r=runtime(candidate,{fetcher:async u=>({ok:!fail,json:async()=>payload[u]})});
 try{await r.settle();assert.match(r.text(),/자료를 확인하지 못해/);assert.match(r.text(),/3개 소스 중 0개 확인/);fail=false;r.find(n=>n.type==='button'&&r.text(n)==='자료 다시 불러오기').props.onClick();await r.settle();assert.match(r.text(),/확인된 자료에서 2종목/);assert.equal(r.calls.filter(c=>c.url&& !String(c.url).includes('/api/stock_slice?')).length,14)}finally{r.dispose()}
});
test('partial report failure retains received rows with denominator',async()=>{
 const r=runtime(candidate,{fetcher:async u=>({ok:u!=='kr',json:async()=>payload[u]})});
 try{await r.settle();assert.match(r.text(),/3개 소스 중 2개 확인/);assert.match(r.text(),/검수 미국/);assert.doesNotMatch(r.text(),/검수 국내/)}finally{r.dispose()}
});
test('US-only configuration loads without KR URL',async()=>{
 const r=runtime();try{r.setProps({stockUrl:'',usSmallcapUrl:''});await r.settle();assert.match(r.text(),/검수 미국/);assert.equal(r.calls.filter(c=>c.url==='kr').length,0)}finally{r.dispose()}
});
test('selected zero-count tab remains visible and selected',async()=>{
 const r=runtime(candidate,{search:'?screen=insider_buy'});try{await r.settle();assert.match(r.text(),/선택한 조건에 맞는 종목이 없어요/);assert.ok(r.find(n=>n.type==='button'&&n.props['aria-pressed']===true&&r.text(n).includes('내부자 순매수')))}finally{r.dispose()}
});
test('late response from obsolete URL cannot replace current rows',async()=>{
 const old=deferred();const r=runtime(candidate,{fetcher:async u=>u==='kr'?old.promise:{ok:true,json:async()=>payload[u]||{stocks:[]}}});
 try{await r.settle();r.setProps({stockUrl:'replacement'});await r.settle();old.resolve({ok:true,json:async()=>({stocks:[{...kr,name:'obsolete'}]})});await r.settle();assert.doesNotMatch(r.text(),/obsolete/);assert.match(r.text(),/검수 미국/);assert.equal(r.calls.find(c=>c.url==='kr').options.signal.aborted,true)}finally{r.dispose()}
});
test('numeric filter errors hide stale detail and list; reset recovers',async()=>{
 const r=runtime();try{await r.settle();r.find(n=>n.props['aria-label']==='지표 범위').props.onChange({target:{value:'PER'}});await r.settle();r.find(n=>n.props['aria-label']==='지표 최솟값').props.onChange({target:{value:'not-a-number'}});await r.settle();assert.match(r.text(),/유한한 숫자를 입력/);assert.doesNotMatch(r.text(),/검수 국내|검수 미국/);assert.equal(r.find(n=>n.props['aria-label']==='지표 최솟값').props['aria-invalid'],true);r.find(n=>n.type==='button'&&r.text(n).includes('초기화')).props.onClick();await r.settle();assert.match(r.text(),/검수 국내/)}finally{r.dispose()}
});
test('market-only filter offers reset',async()=>{
 const r=runtime();try{await r.settle();r.find(n=>n.type==='button'&&r.text(n)==='미장').props.onClick();await r.settle();assert.ok(r.find(n=>n.type==='button'&&r.text(n).includes('초기화')))}finally{r.dispose()}
});
test('border-box observer and keyboard activation are installed',async()=>{
 const r=runtime();try{await r.settle();assert.equal(r.calls.find(c=>c.resize).resize.box,'border-box');const rows=r.nodes().filter(n=>n.props.role==='button');assert.ok(rows.length>=2);for(const row of rows)assert.equal(typeof row.props.onKeyDown,'function')}finally{r.dispose()}
});
for(const [label,metric,min,max,error] of [
 ['inactive range','','NaN','',false],['blank','PER','','',false],['zero','PER','0','0',false],['negative valid','ROE','-20','-1',false],['reverse','PER','20','10',true],['NaN','PER','abc','',true],['Infinity','PER','','Infinity',true],['overflow','PER','1e999','',true],
])test('range '+label,()=>{const r=runtime();assert.equal(Boolean(r.exports.discoveryRangeError(metric,min,max)),error);r.dispose()});
test('payload validation and ticker dedup',()=>{const r=runtime();const x=r.exports;assert.equal(x.validDiscoveryDoc({stocks:[]},'stocks'),true);assert.equal(x.validDiscoveryDoc({error:'oops'},'stocks'),false);assert.equal(x.validDiscoveryDoc({flows:{A:[]}},'flows'),true);assert.equal(x.validDiscoveryDoc({flows:{A:{}}},'flows'),false);assert.deepEqual(Array.from(x.discoveryRows([{stocks:[kr,kr,null,{},us]}]),s=>s.ticker),['005930','AAPL']);r.dispose()});
test('eleven screen predicates and default sorts are present',()=>{const r=runtime();assert.deepEqual(Array.from(r.exports.SCREENS,s=>s.id),['all','insider_buy','insider_dom','foreign_buy','dilution_hist','value_quality_strict','value_quality','per_cheap','roe_top','low_debt','below_book']);for(const s of r.exports.SCREENS){assert.equal(typeof s.pred,'function');assert.equal(typeof s.sortBy,'function')}r.dispose()});
test('typography and theme are preserved; no weak weights',()=>{
 assert.doesNotMatch(candidate,/fontWeight:\s*(400|500|650)\b/);assert.match(candidate,/Pretendard/);assert.match(candidate,/AN_PALETTE/);assert.match(candidate,/padding: `8px \$\{pad\}px \$\{pad\}px`/);
});
test('null flow entry is a failed payload, not a render exception',()=>{const r=runtime();assert.equal(r.exports.validDiscoveryDoc({flows:{A:[null]}},'flows'),false);r.dispose()});
test('mobile full-bleed tabs include their padding inside the available width',()=>assert.match(candidate,/width: `calc\(100% \+ \$\{pad \* 2\}px\)`,\s*boxSizing: "border-box"/));
module.exports={runtime,candidate,kr,us,props,payload};

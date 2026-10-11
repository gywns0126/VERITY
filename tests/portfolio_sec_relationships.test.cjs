// Synthetic fixtures plus an optional saved official capture; not investment judgments.
// MEMBER_MAP_SNAPSHOT=review/member-map/Map.snapshot.tsx node --test tests/portfolio_sec_relationships.test.cjs
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const {createHash} = require('node:crypto');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');
const snapshot = process.env.MEMBER_MAP_SNAPSHOT
  ? fs.readFileSync(path.resolve(process.env.MEMBER_MAP_SNAPSHOT),'utf8') : null;
function load(name) {
  let code;
  if (snapshot !== null) {
    const modules = {
      'PortfolioAutomaticEvidence.ts':['PortfolioAnalysisPrices.ts','parseAutomaticEvidence'],
      'PortfolioPrototypeAutomatic.ts':['PortfolioStockSearch.ts','projectAutomaticPrototype'],
    };
    assert.ok(Object.hasOwn(modules,name),'Unexpected snapshot module');
    const [next,symbol] = modules[name], marker = '// framer-components/public-probe/';
    const startMarker = marker+name+'\n', endMarker = marker+next+'\n';
    assert.equal(snapshot.split(startMarker).length,2,'Snapshot start anchor must be unique');
    assert.equal(snapshot.split(endMarker).length,2,'Snapshot end anchor must be unique');
    const start = snapshot.indexOf(startMarker), end = snapshot.indexOf(endMarker);
    assert.ok(end > start,'Snapshot module boundaries must be ordered');
    code = snapshot.slice(start,end)+`\nmodule.exports={${symbol}};`;
  } else {
    code = require('esbuild').buildSync({entryPoints:[path.join(root,'framer-components/public-probe',name)],
      bundle:true,write:false,format:'cjs',platform:'node',target:'es2022'}).outputFiles[0].text;
  }
  const box = {exports:{}};
  vm.runInNewContext(code,{module:box,exports:box.exports,URL});
  return box.exports;
}
const {parseAutomaticEvidence} = load('PortfolioAutomaticEvidence.ts');
const {projectAutomaticPrototype} = load('PortfolioPrototypeAutomatic.ts');
const selected = new Set(['US:SYNTH','US:ALPHA']);
const hash = text => createHash('sha256').update(text).digest('hex');
function row(role='customer') {
  const cik='0000123456', accession='0000123456-26-000001';
  const quote=`Our major ${role}s include Alpha, Inc., Beta Corp. and Gamma Ltd..`;
  return {stable_id:'relation:sec-role:1234567890abcdef',revision:'a'.repeat(64),
    type:'reported-sec-counterparty',status:'accepted_reported',verification:'reported-sec-excerpt',
    snapshot_scope:'reported-filing-period-not-current',
    label:role==='customer'?'SEC 보고서상 매출처':'SEC 보고서상 공급처',
    participants:[{id:'US:SYNTH',role:'document_issuer',name:'Synthetic Issuer Inc.'},
      {id:'US:ALPHA',role:'reported_'+role,name:'Alpha Corporation'}],
    source:{id:`source:sec:${cik}:${accession}`,kind:'sec-filing-excerpt',cik,accession,
      as_of:'2026-03-20',period_end:'2025-12-31',form:'10-K',
      url:`https://www.sec.gov/Archives/edgar/data/123456/${accession.replaceAll('-','')}/synthetic_10-k.htm`,
      document_issuer:'US:SYNTH'},
    evidence:{role,raw_name:'Alpha',quote,paragraph_sha256:hash(quote),document_sha256:hash('synthetic document')}};
}
const payload = r => ({schema:'portfolio-auto-evidence-v1',verified_events:[],relationships:[r],materials:[]});
function withQuote(quote,rawName='Alpha',role='customer') {
  const r=row(role); Object.assign(r.evidence,{quote,raw_name:rawName,paragraph_sha256:hash(quote)}); return r;
}
function rejects(mutations) {
  for (const mutate of mutations) {
    const r=row(); mutate(r);
    assert.throws(()=>parseAutomaticEvidence(payload(r),selected),String(mutate));
  }
}

test('SEC customer and supplier keep source, period, quote and existing zero-strength map behavior',()=>{
  for(const role of ['customer','supplier']) {
    const r=row(role); r.participants.reverse();
    const parsed=parseAutomaticEvidence(payload(r),selected), relation=parsed.relations[0];
    assert.equal(relation.title,r.label);
    assert.equal(relation.reported,true); assert.equal(relation.reportedBasis,'business-period');
    assert.equal(relation.asOf,'2026-03-20'); assert.equal(relation.url,r.source.url);
    assert.equal(relation.source,'SEC · 10-K');
    assert.ok(relation.reason.endsWith(r.evidence.quote));
    assert.match(relation.reason,/보고기간 종료일 2025-12-31 · 공개 제출일 2026-03-20/);
    assert.match(relation.reason,/현재 유효 여부·거래 규모·주가 영향은 미확인/);
    const model=projectAutomaticPrototype({companies:[...selected].map(id=>({id,market:'US',ticker:id.slice(3),name:id})),automaticRelations:parsed.relations});
    assert.equal(model.nodes.length,1); assert.equal(model.edges.length,2);
    assert.equal(model.nodes[0].topic,'supply');
    assert.ok(model.edges.every(e=>e.strength===0&&e.impact==='미확인'));
    assert.deepEqual(Array.from(model.edges,e=>e.verb).sort(),role==='customer'
      ? ['공시상 매출처','매출처 공시 회사'] : ['공시상 공급처','구매처 공시 회사']);
    assert.ok(!JSON.stringify(model).includes('sha256'));
  }
});

test('SEC exact whole lists support principal/are, case and legal suffixes without substring matches',()=>{
  for(const [quote,name,role] of [
    ['Our customers are Alpha.','Alpha','customer'],
    ['Our principal suppliers include Alpha Corporation and Beta Ltd..','alpha','supplier'],
    ['OUR MAJOR CUSTOMERS ARE Alpha, Inc., Beta, Ltd., and Gamma Corp..','Alpha Incorporated','customer'],
    ['Our customers include Alpha and Beta.','Beta Corporation','customer'],
  ]) assert.equal(parseAutomaticEvidence(payload(withQuote(quote,name,role)),selected).relations.length,1);
  for(const name of ['Alph','Alpha unrelated','Unknown','Alpha Corp. subsidiary']) {
    assert.throws(()=>parseAutomaticEvidence(payload(withQuote('Our customers include Alpha.',name)),selected));
  }
});

test('SEC 20-F and .html are allowed; either selected party suffices',()=>{
  const r=row();r.source.form='20-F';r.source.url=r.source.url.replace('.htm','.html');
  for(const identifier of selected) assert.equal(parseAutomaticEvidence(payload(r),new Set([identifier])).relations.length,1);
  assert.throws(()=>parseAutomaticEvidence(payload(r),new Set(['US:OTHER'])));
  assert.equal(parseAutomaticEvidence(undefined,selected).relations.length,0);
  const p=payload(r);p.relationships=[];assert.equal(parseAutomaticEvidence(p,selected).relations.length,0);
});

test('SEC identity roles and closed relation contract fail closed',()=>rejects([
  r=>r.stable_id='relation:sec-role:1234',r=>r.revision='a'.repeat(63),r=>r.revision='A'.repeat(64),
  r=>r.type='reported-business-counterparty',r=>r.status='accepted_candidate',
  r=>r.verification='reported-business-excerpt',r=>r.snapshot_scope='current',r=>r.label='확실한 상승',
  r=>r.participants[0].id='KR:005930',r=>r.participants[1].id='KR:000660',
  r=>r.participants[1].id=r.participants[0].id,r=>r.participants[0].role='from',
  r=>r.participants[1].role='document_issuer',r=>r.participants[1].role='reported_supplier',
  r=>r.participants[0].name='',r=>r.participants[1].name='<b>Alpha</b>',
  r=>r.participants.push({id:'US:BETA',role:'reported_customer',name:'Beta'}),
  r=>r.participants[1].rating='high',r=>r.impact='positive',r=>r.source.secret='not-public',
  r=>r.evidence.rating=10,r=>delete r.evidence.document_sha256,
]));

test('SEC source path, accession, issuer and document kind cannot be swapped or extended',()=>rejects([
  r=>r.source.kind='dart-filing-excerpt',r=>r.source.cik='123456',r=>r.source.cik='0000000000',
  r=>r.source.accession='123456-26-000001',r=>r.source.id+='x',r=>r.source.document_issuer='US:ALPHA',
  r=>r.source.form='8-K',r=>r.source.form='10-K/A',r=>r.source.url=r.source.url.replace('www.sec.gov','evil.example'),
  r=>r.source.url=r.source.url.replace('/123456/','/654321/'),
  r=>r.source.url=r.source.url.replace('/000012345626000001/','/000012345626000002/'),
  r=>r.source.url+='?token=secret',r=>r.source.url+='#fragment',
  r=>r.source.url=r.source.url.replace('synthetic_10-k.htm','../synthetic.htm'),
  r=>r.source.url=r.source.url.replace('synthetic_10-k.htm','sub/synthetic.htm'),
  r=>r.source.url=r.source.url.replace('https://','http://'),
  r=>r.source.url=r.source.url.replace('.htm','.pdf'),
]));

test('SEC dates are valid distinct filing/period dates; hashes must remain present and well formed',()=>rejects([
  r=>r.source.as_of='2026-02-30',r=>r.source.as_of='2026-3-20',r=>r.source.as_of='9999-01-01',
  r=>r.source.period_end='2026-03-21',r=>r.source.period_end='2025-02-29',r=>r.source.period_end='0000-01-01',
  r=>r.evidence.paragraph_sha256='',r=>r.evidence.document_sha256='0'.repeat(65),
  r=>r.evidence.paragraph_sha256='g'.repeat(64),r=>r.evidence.document_sha256=null,
]));

test('SEC explicit grammar withholds subsidiary, indirect, planned, negative and unrelated assertions',()=>{
  const quotes=[
    'Our subsidiaries customers include Alpha.', 'Our customers may include Alpha.',
    'Our customers include Alpha subsidiary.', 'Our customers include Alpha indirectly.',
    'Our customers include not Alpha.', 'Our customers include Alpha, a potential customer.',
    'Our customers include Alpha except Beta.', 'Our customers include Alpha, and plan Beta.',
    'Our suppliers include Alpha.', 'Customers of Other include Alpha.',
    'Our customers include Alpha. We also discuss Beta.', ' Our customers include Alpha.',
    'Our customers include Alpha.\n', 'Our customers include\nAlpha.',
    'Our customers include <b>Alpha</b>.', 'Our customers include Alpha',
  ];
  for(const quote of quotes) assert.throws(()=>parseAutomaticEvidence(payload(withQuote(quote)),selected),quote);
  for(const risk of ['not','no','may','might','could','would','will','expect','plan','former','previous','potential','indirect','subsidiary','affiliate','competitor','except','excluding','terminated','ceased','historical','if','unless','subject to','according to']) {
    // Alpha still matches one list entry: the whole-quote risk veto must win.
    const quote=`Our customers include Alpha, ${risk} Beta.`;
    assert.throws(()=>parseAutomaticEvidence(payload(withQuote(quote)),selected),risk);
  }
});

test('SEC qualifying clauses and malformed other list entries cannot leave a known party accepted',()=>{
  for(const quote of [
    'Our customers include Alpha, subject to approval.',
    'Our customers include Alpha, unless the agreement ends.',
    'Our customers include Alpha, according to Other.',
    'Our customers include Alpha, SUBJECT TO Beta.',
    'Our customers include Alpha, Beta; approval required.',
    'Our customers include Alpha, Beta: arrangements.',
    'Our customers include Alpha,, Beta.',
    'Our customers include Alpha, .',
  ]) assert.throws(()=>parseAutomaticEvidence(payload(withQuote(quote)),selected),quote);
});

const foundrySentence='We utilize foundries, such as Taiwan Semiconductor Manufacturing Company Limited, or TSMC, and Samsung Electronics Co., Ltd., or Samsung, to produce our semiconductor wafers.';
const foundryParagraph=`Manufacturing is organized by region. ${foundrySentence} We purchase memory from Micron Technology, Inc..`;
function foundryRow(quote=foundryParagraph) {
  const r=withQuote(quote,'Taiwan Semiconductor Manufacturing Company Limited','supplier');
  r.participants[1]={id:'US:TSM',role:'reported_supplier',name:'Taiwan Semiconductor Manufacturing Company Limited'};
  return r;
}
test('complete foundry clause preserves whole paragraph and binds full names, never acronym or memory mentions',()=>{
  const r=foundryRow(), parsed=parseAutomaticEvidence(payload(r),new Set(['US:SYNTH']));
  assert.ok(parsed.relations[0].reason.endsWith(foundryParagraph));
  assert.equal(parsed.relations[0].participants[1].id,'US:TSM');
  for(const name of ['TSMC','Samsung','Micron Technology, Inc.','Taiwan Semiconductor']) {
    const bad=foundryRow();bad.evidence.raw_name=name;
    assert.throws(()=>parseAutomaticEvidence(payload(bad),new Set(['US:SYNTH'])),name);
  }
  const customer=foundryRow();customer.participants[1].role='reported_customer';customer.evidence.role='customer';customer.label='SEC 보고서상 매출처';
  assert.throws(()=>parseAutomaticEvidence(payload(customer),new Set(['US:SYNTH'])));
});
test('foundry clause rejects attribution, conditions, quotes and malformed boundaries across full paragraph',()=>{
  for(const quote of [
    `Other states. ${foundrySentence}`, `Other said. ${foundrySentence}`, `Other says. ${foundrySentence}`,
    `An example follows. ${foundrySentence}`, `An illustration follows. ${foundrySentence}`,
    `Quoted statement. ${foundrySentence}`, `“${foundrySentence}”`, `"${foundrySentence}"`,
    `${foundrySentence} This is subject to approval.`,`${foundrySentence} This holds unless cancelled.`,
    `${foundrySentence} According to Other.`, `${foundrySentence} Our subsidiary handles purchases.`,
    `Other: ${foundrySentence}`,foundrySentence.replace('We utilize','We may utilize'),
    foundrySentence.replace('to produce our semiconductor wafers','to produce their semiconductor wafers'),
    foundrySentence.replace(', or Samsung,',' , or Samsung;'),foundrySentence.replace('wafers.','wafers.not a sentence'),
  ]) assert.throws(()=>parseAutomaticEvidence(payload(foundryRow(quote)),new Set(['US:SYNTH'])),quote);
});

test('SEC quote/list sizes, evidence role and duplicate identities are bounded',()=>{
  for(const [quote,name] of [
    [`Our customers include ${['Alpha',...Array.from({length:12},(_,i)=>`Company ${i}`)].join(', ')}.`,'Alpha'],
    [`Our customers include Alpha, ${'x'.repeat(1200)}.`,'Alpha'],
    ['Our customers include Alpha.',' Alpha'],
  ]) assert.throws(()=>parseAutomaticEvidence(payload(withQuote(quote,name)),selected));
  rejects([r=>r.evidence.role='supplier',r=>r.evidence.raw_name='x'.repeat(161)]);
  const p=payload(row());p.relationships.push(row());assert.throws(()=>parseAutomaticEvidence(p,selected));
});

test('Python SEC index and attachment reach the browser parser without a model or file writes',()=>{
  const script=String.raw`
import json
from api.intelligence.portfolio_sec_relationships import index_sec_relationships, attach_sec_relationships
companies=[{'id':'US:SYNTH','name':'Synthetic Issuer Inc.'}, {'id':'US:ALPHA','name':'Alpha Corporation'}, {'id':'US:BETA','name':'Beta Ltd.'}]
capture={'schema':'sec-annual-excerpts-v1','issuer_id':'US:SYNTH','issuer_name':'Synthetic Issuer Inc.',
'cik':'0000123456','accession':'0000123456-26-000001','filed_date':'2026-03-20','period_end':'2025-12-31','form':'10-K',
'primary_document':'synthetic.htm','url':'https://www.sec.gov/Archives/edgar/data/123456/000012345626000001/synthetic.htm',
'document_sha256':'d'*64,'paragraphs':['Our customers include Alpha, Inc. and Beta Ltd..','Our principal suppliers are Alpha Corporation.']}
index=index_sec_relationships([capture],companies)
projection={'schema':'portfolio-auto-evidence-v1','verified_events':[],'relationships':[],'materials':[],'sources':[],'coverage':{}}
out=attach_sec_relationships(projection,index,[{'market':'US','ticker':'SYNTH'}])
print(json.dumps({'index':index,'projection':out}))
`;
  const result=JSON.parse(execFileSync('python3',['-c',script],{cwd:root,encoding:'utf8',
    env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}}));
  assert.equal(result.index.coverage.relationships,3);
  const parsed=parseAutomaticEvidence(result.projection,new Set(['US:SYNTH']));
  assert.equal(parsed.relations.length,3);
  assert.deepEqual(Array.from(parsed.relations,r=>r.title).sort(),['SEC 보고서상 공급처','SEC 보고서상 매출처','SEC 보고서상 매출처']);
  for(const r of parsed.relations) assert.ok(result.index.relations.some(original=>r.reason.endsWith(original.evidence.quote)));
});

const nvdaCapture=process.env.SEC_NVDA_CAPTURE || '/private/tmp/sec-us-nvda-20261011/member_map_auto_evidence.json';
if (process.env.SEC_NVDA_CAPTURE) assert.ok(fs.existsSync(nvdaCapture),'Explicit SEC capture must exist');
test('saved official NVDA paragraph reaches TSM only; unknown KR foundry does not erase this complete clause',
  {skip:!fs.existsSync(nvdaCapture)},()=>{
  const script=String.raw`
import json,sys
from api.intelligence.portfolio_sec_relationships import index_sec_relationships
captures=json.load(open(sys.argv[1]))['sec_filing_excerpts']
capture=next(r for r in captures if r['issuer_id']=='US:NVDA')
companies=[{'id':'US:NVDA','name':'NVIDIA CORP'},
{'id':'US:TSM','name':'Taiwan Semiconductor Manufacturing Company Limited'},
{'id':'US:MU','name':'Micron Technology, Inc.'}, {'id':'KR:005930','name':'Samsung Electronics Co., Ltd.'}]
print(json.dumps({'capture':capture,'index':index_sec_relationships([capture],companies)}))
`;
  const result=JSON.parse(execFileSync('python3',['-c',script,nvdaCapture],{cwd:root,encoding:'utf8',
    env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}}));
  assert.equal(result.index.relations.length,1);
  const r=result.index.relations[0];
  assert.equal(r.participants[1].id,'US:TSM');assert.equal(r.evidence.role,'supplier');
  assert.equal(r.evidence.quote,result.capture.paragraphs[16]);
  assert.equal(r.evidence.paragraph_sha256,hash(result.capture.paragraphs[16]));
  const parsed=parseAutomaticEvidence(payload(r),new Set(['US:NVDA']));
  assert.equal(parsed.relations.length,1);assert.ok(parsed.relations[0].reason.endsWith(result.capture.paragraphs[16]));
  assert.equal(parsed.relations[0].asOf,'2026-02-25');
  assert.match(parsed.relations[0].reason,/보고기간 종료일 2026-01-25/);
});

test('latest conditional guard rejects generic and trailing foundry qualifiers',()=>{
  for(const risk of ['provided that','conditional','conditionally','contingent','pending']) {
    const generic=withQuote('Our customers include Alpha, '+risk+' Beta.');
    assert.throws(()=>parseAutomaticEvidence(payload(generic),selected),risk);
    const foundry=foundryRow(foundrySentence+' '+risk+' approval.');
    assert.throws(()=>parseAutomaticEvidence(payload(foundry),new Set(['US:SYNTH'])),risk);
  }
});

const test = require('node:test');
const assert = require('node:assert/strict');
const {PUBLIC_URL, digest, validate, preserveBaseline, verify, publish} = require('../scripts/nps_history_publish.cjs');
const fixture = () => ({count: 1, holdings: [{ticker:'123456'}], full_n:100,
  full:[{ticker:'123456',name:'First',eval_amt_100m:100,as_of:'2025-12-31'},
    ...Array.from({length:99},(_,i)=>({ticker:null,name:`Unmapped${i}`,eval_amt_100m:0,as_of:'2025-12-31'}))], fund:{unchanged:true},
  detail_history:{schema_version:1,scope:'annual_domestic_evaluation_top100',
    selection:{as_of:'2025-12-31',limit:100,target_n:1,annual_top100_n:100,annual_top100_unmatched_n:99},
    stocks:[{ticker:'123456',name:'First',rank:1,eval_amt_100m:100,selection_as_of:'2025-12-31',
      events:[{rcept_no:'20260101000001',date_basis:'filing_date',trade_date:null}]}]}});
const fetcher = value => async url => { assert.equal(url, PUBLIC_URL); return {ok:true,json:async()=>value}; };
test('canonical hashes ignore object key formatting only', () => {
  assert.equal(digest({b:2,a:1}),digest({a:1,b:2}));assert.notEqual(digest([1,2]),digest([2,1]));
});
test('official six-character alphanumeric KRX codes remain supported', () => {
  const p=fixture();p.full[0].ticker=p.detail_history.stocks[0].ticker='0126Z0';assert.equal(validate(p).selected,1);
});
test('right counts cannot replace the source Top100 with unrelated stocks or reorder ranks', () => {
  const p=fixture();p.detail_history.stocks[0].ticker='654321';assert.throws(()=>validate(p),/official annual source Top100/);
  p.detail_history.stocks[0].ticker='123456';p.detail_history.stocks[0].rank=100;assert.throws(()=>validate(p));
});
test('selection, annual date, receipt and missing history fail closed', () => {
  assert.equal(validate(fixture()).filings,1);
  for (const mutate of [p=>p.full_n=2,p=>p.full[0].as_of='2024-12-31',
    p=>p.detail_history.selection.target_n=99,p=>p.detail_history.stocks[0].events[0].rcept_no='bad',
    p=>p.detail_history.stocks[0].events[0].trade_date='2026-01-01',p=>p.detail_history.stocks[0].events=[]]) {
    const p=fixture();mutate(p);assert.throws(()=>validate(p));
  }
});
test('annual rollbacks, unrelated changes and lost filings are refused', () => {
  const p=fixture(), previous=fixture();preserveBaseline(p,previous);
  previous.detail_history.selection.as_of='2026-12-31';assert.throws(()=>preserveBaseline(p,previous));
  previous.detail_history.selection.as_of='2025-12-31';previous.fund={changed:true};assert.throws(()=>preserveBaseline(p,previous));
  previous.fund=p.fund;previous.detail_history.stocks[0].events.push({rcept_no:'20260102000001'});
  assert.throws(()=>preserveBaseline(p,previous));
});
test('verification checks normal consumer URL and mismatches fail', async () => {
  const p=fixture();assert.equal((await verify(p,{fetcher:fetcher(p)})).with_history,1);
  await assert.rejects(verify(p,{fetcher:fetcher({...p,count:2}),attempts:1}));
});
test('identical data skips writes; missing token and wrong store cannot write', async () => {
  let writes=0;const p=fixture();const sdk={head:async()=>({url:PUBLIC_URL,pathname:'nps_holdings.json'}),put:async()=>{writes++;}};
  assert.equal((await publish(p,{sdk,token:'test-only',fetcher:fetcher(p)})).unchanged,true);
  await assert.rejects(publish(p,{sdk,token:null,fetcher:fetcher(p)}));
  await assert.rejects(publish(p,{sdk:{...sdk,head:async()=>({url:'https://wrong.example'})},token:'test-only',fetcher:fetcher(p)}));
  assert.equal(writes,0);
});
test('changed data writes only the fixed NPS pathname and verifies readback', async () => {
  const p=fixture(),old={...p,generated_at:'old'};let calls=0,written=false;
  const sdk={head:async()=>({url:PUBLIC_URL,pathname:'nps_holdings.json'}),put:async(name,body,options)=>{
    assert.equal(name,'nps_holdings.json');assert.equal(JSON.parse(body).count,1);
    assert.equal(options.allowOverwrite,true);assert.equal(options.addRandomSuffix,false);written=true;return {url:PUBLIC_URL};}};
  const result=await publish(p,{sdk,token:'test-only',fetcher:async()=>({ok:true,json:async()=>++calls===1?old:p})});
  assert.equal(written,true);assert.equal(result.unchanged,false);
});

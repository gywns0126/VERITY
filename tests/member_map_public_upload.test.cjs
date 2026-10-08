const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { buildPublicCatalog } = require('../scripts/member-map/build-public-source-filter.cjs');
const { upload, failureSummary } = require('../scripts/member-map/upload-public-source-filter.cjs');
const token = 'vercel_blob_rw_rte5guenhonw9fzn_synthetic';
function fixture() {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'map-upload-test-'));
  const source = path.join(directory, 'member_map_auto_evidence.json');
  const document = buildPublicCatalog({ generatedAt: '2026-10-05T00:00:00Z',
    universe: { stocks: [{ticker:'009150',market:'KR',name:'삼성전기'}] },
    chainSnippets: { updated_at: '2026-10-04T00:00:00Z', documents: [] }, groupStructure: { updated_at: '2026-10-04T00:00:00Z', count: 0, structures: {} },
    inputMetadata: Object.fromEntries(['universe','chainSnippets','groupStructure'].map(key=>[key,{bytes:10,sha256:'a'.repeat(64)}])) });
  fs.writeFileSync(source, JSON.stringify(document));
  return {source, document, body:fs.readFileSync(source)};
}
test('one fixed public file is uploaded and hash-read back', async () => {
  const f=fixture(); let calls=0, puts=0;
  const result=await upload(f.source,{token, fetch:async()=>++calls===1?new Response(null,{status:404}):new Response(f.body),
    put:async(name,body,options)=>{puts++;assert.equal(name,'member_map_auto_evidence.json');assert.deepEqual(body,f.body);assert.equal(options.access,'public');return {url:'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/'+name};}});
  assert.equal(puts,1); assert.equal(result.verified,true);
});
test('same bytes skip writing; same-age changed bytes refuse replacement',async()=>{
  const f=fixture();const put=async()=>assert.fail('must not upload');
  assert.equal((await upload(f.source,{token,put,fetch:async()=>new Response(f.body)})).uploaded,false);
  const changed={...f.document,generatedAt:'2026-10-05T00:00:00Z',extra:'changed'};
  await assert.rejects(upload(f.source,{token,put,fetch:async()=>Response.json(changed)}),
    e=>e.stage==='public-preflight');
});
test('wrong store credential, access denial and mismatched readback fail closed',async()=>{
  const f=fixture();const put=async()=>assert.fail('must not upload');
  await assert.rejects(upload(f.source,{token:'wrong',put}),{stage:'credential'});
  await assert.rejects(upload(f.source,{token,put,fetch:async()=>new Response(null,{status:403})}),{stage:'public-preflight'});
  let n=0;
  await assert.rejects(upload(f.source,{token,fetch:async()=>++n===1?new Response(null,{status:404}):Response.json({}),
    put:async()=>({url:'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/member_map_auto_evidence.json'})}),{stage:'readback-hash'});
});
test('failure output identifies the stage without provider messages or credentials',async()=>{
  const f=fixture();
  const secret='synthetic-secret-never-in-output';
  await assert.rejects(upload(f.source,{token,fetch:async()=>new Response(null,{status:404}),
    put:async()=>{throw Error(secret);}}),e=>{
      assert.deepEqual(failureSummary(e),{status:'failed',stage:'upload'});
      assert.equal(JSON.stringify(failureSummary(e)).includes(secret),false);
      assert.equal(e.cause,undefined);
      assert.equal(e.stack.includes(secret),false);
      return true;
    });
  assert.deepEqual(failureSummary({stage:secret,message:secret}),{status:'failed',stage:'unknown'});
});
test('stale cached readback is retried without a second upload',async()=>{
  const f=fixture();let reads=0,puts=0;const waits=[];const urls=[];
  const older={...f.document,generatedAt:'2026-10-04T00:00:00Z'};
  const result=await upload(f.source,{token,sleep:async ms=>waits.push(ms),
    fetch:async url=>{urls.push(url);reads++;return reads===1?new Response(null,{status:404}):reads===2?Response.json(older):new Response(f.body);},
    put:async()=>{puts++;return {url:'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/member_map_auto_evidence.json'};}});
  assert.equal(puts,1);assert.equal(result.readbackAttempts,2);assert.deepEqual(waits,[10000]);
  assert.notEqual(urls[1],urls[2]);
});
test('stale readback exhausts bounded reads and still fails closed',async()=>{
  const f=fixture();let reads=0,puts=0;const waits=[];
  await assert.rejects(upload(f.source,{token,sleep:async ms=>waits.push(ms),
    fetch:async()=>++reads===1?new Response(null,{status:404}):Response.json({...f.document,generatedAt:'2026-10-04T00:00:00Z'}),
    put:async()=>{puts++;return {url:'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/member_map_auto_evidence.json'};}}),{stage:'readback-hash'});
  assert.equal(puts,1);assert.equal(reads,5);assert.deepEqual(waits,[10000,20000,30000]);
});
test('temporary read errors retry but denied access and competing content do not',async()=>{
  const f=fixture();const put=async()=>({url:'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/member_map_auto_evidence.json'});
  for (const status of [404,429,503]) {
    let reads=0;const waits=[];
    const result=await upload(f.source,{token,put,sleep:async ms=>waits.push(ms),
      fetch:async()=>++reads===1?new Response(null,{status:404}):reads===2?new Response(null,{status}):new Response(f.body)});
    assert.equal(result.verified,true);assert.deepEqual(waits,[10000]);
  }
  for (const response of [new Response(null,{status:403}),Response.json({...f.document,extra:'same-age-different-bytes'}),Response.json({...f.document,generatedAt:'2026-10-06T00:00:00Z'})]) {
    let reads=0;
    await assert.rejects(upload(f.source,{token,put,sleep:async()=>assert.fail('must not wait'),
      fetch:async()=>++reads===1?new Response(null,{status:404}):response}));
    assert.equal(reads,2);
  }
});

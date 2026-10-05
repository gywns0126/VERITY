const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { buildPublicCatalog } = require('../scripts/member-map/build-public-source-filter.cjs');
const { upload } = require('../scripts/member-map/upload-public-source-filter.cjs');
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
  await assert.rejects(upload(f.source,{token,put,fetch:async()=>Response.json(changed)}),/same-age or newer/);
});
test('wrong store credential, access denial and mismatched readback fail closed',async()=>{
  const f=fixture();const put=async()=>assert.fail('must not upload');
  await assert.rejects(upload(f.source,{token:'wrong',put}),/credential/);
  await assert.rejects(upload(f.source,{token,put,fetch:async()=>new Response(null,{status:403})}),/403/);
  let n=0;
  await assert.rejects(upload(f.source,{token,fetch:async()=>++n===1?new Response(null,{status:404}):Response.json({}),
    put:async()=>({url:'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/member_map_auto_evidence.json'})}),/hash mismatch/);
});

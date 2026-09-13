const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const {validate} = require('../scripts/publish_search_index.cjs');
const {verifyReadback} = require('../scripts/publish_search_index.cjs');
const next = JSON.parse(fs.readFileSync('data/universe_search.json','utf8'));
const catalog = JSON.parse(fs.readFileSync('data/us_depositary_search.json','utf8'));
const clone = x => JSON.parse(JSON.stringify(x));

test('accepts intact current artifact', () => assert.equal(validate(next,next,catalog).catalog,catalog.stocks.length));
test('rejects losing one existing ticker', () => {
    const bad=clone(next); bad.stocks.pop(); bad._meta.count--;
    assert.throws(()=>validate(next,bad,catalog));
});
test('rejects overwriting existing metadata', () => {
    const bad=clone(next); bad.stocks[0].name='incorrect';
    assert.throws(()=>validate(next,bad,catalog));
});
test('rejects old generation date', () => {
    const bad=clone(next); bad._meta.generated_at='2000-01-01';
    assert.throws(()=>validate(next,bad,catalog));
});
test('rejects truncated catalog and duplicate tickers', () => {
    const bad=clone(catalog); bad.stocks=[];
    assert.throws(()=>validate(next,next,bad));
    const index=clone(next); index.stocks[1]=index.stocks[0];
    assert.throws(()=>validate(next,index,catalog));
});
test('manual workflow has one named upload and no broad side effects', () => {
    const code=fs.readFileSync('scripts/publish_search_index.cjs','utf8');
    const wf=fs.readFileSync('.github/workflows/search_index_publish.yml','utf8');
    assert.equal((code.match(/await put\(/g)||[]).length,1);
    assert(code.includes('ifMatch: etag'));
    assert(!/await del\(|await list\(/.test(code));
    assert(!/schedule:|repository_dispatch:|personal_token:|SUPABASE_SERVICE_ROLE_KEY:|KIS_APP_KEY:/.test(wf));
    assert(wf.includes('contents: read'));
});

test('CDN propagation retries reads and accepts exact bytes', async () => {
    let reads=0, pauses=0;
    await verifyReadback(Buffer.from('new'), async()=>({ok:true,arrayBuffer:async()=>Buffer.from(++reads<3?'old':'new')}),
        async()=>{pauses++;});
    assert.equal(reads,3); assert.equal(pauses,2);
});
test('CDN mismatch remains failure after bounded reads', async () => {
    let reads=0;
    await assert.rejects(verifyReadback(Buffer.from('new'),async()=>{reads++;return {ok:true,arrayBuffer:async()=>Buffer.from('old')};},
        async()=>{},3),/propagation window/);
    assert.equal(reads,3);
});

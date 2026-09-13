// One public classification object only. No holdings, credentials, private uploads or deletes.
const fs = require('node:fs'), cp = require('node:child_process'), assert = require('node:assert/strict');
const NAME = 'portfolio_exposure_map.json';
const URL = 'https://rte5guenhonw9fzn.public.blob.vercel-storage.com/' + NAME;
function validate(next, current = null) {
    assert.deepEqual(Object.keys(next).sort(), ['_meta', 'stocks']);
    const rows = Object.values(next.stocks);
    assert(rows.length >= 7000 && rows.length === next._meta.count, 'classification coverage');
    assert.equal(rows.filter(r => r.sector).length, next._meta.sector_mapped);
    assert(next._meta.sector_mapped >= 6000, 'sector coverage');
    for (const r of rows) {
        assert.deepEqual(Object.keys(r).sort(), ['market', 'name', 'sector']);
        assert(Object.values(r).every(v => typeof v === 'string'), 'public strings only');
    }
    for (const key of ['kr_generated_at', 'us_generated_at']) {
        assert(Number.isFinite(Date.parse(next._meta[key])), 'missing source timestamp');
        if (current) assert(Date.parse(next._meta[key]) >= Date.parse(current._meta[key]), 'older source');
    }
    if (current) assert(rows.length >= Object.keys(current.stocks).length, 'would reduce coverage');
    return { count: rows.length, sector_mapped: next._meta.sector_mapped,
        kr_generated_at: next._meta.kr_generated_at, us_generated_at: next._meta.us_generated_at };
}
async function main() {
    assert(process.env.BLOB_READ_WRITE_TOKEN, 'existing Blob credential required');
    const {put, head} = require('@vercel/blob');
    const body = fs.readFileSync('data/' + NAME), next = JSON.parse(body);
    const response = await fetch(URL + '?verify=' + Date.now(), {signal: AbortSignal.timeout(30000)});
    assert(response.ok || response.status === 404, 'public read failed');
    const previous = response.ok ? Buffer.from(await response.arrayBuffer()) : null;
    const coverage = validate(next, previous ? JSON.parse(previous) : null);
    let etag;
    if (previous) {
        etag = (await head(URL)).etag;
        assert(etag && response.headers.get('etag')?.replace(/^W\//, '') === etag.replace(/^W\//, ''), 'storage/CDN mismatch');
    }
    cp.execFileSync('git', ['fetch','origin','main','--quiet']);
    assert(body.equals(cp.execFileSync('git', ['show','origin/main:data/' + NAME], {maxBuffer:2000000})), 'main changed');
    const unchanged = previous && body.equals(previous);
    if (!unchanged) {
        const result = await put(NAME, body, {access:'public',addRandomSuffix:false,
            allowOverwrite:!!previous, ...(etag ? {ifMatch:etag} : {}),
            contentType:'application/json',cacheControlMaxAge:7200});
        assert.equal(result.url, URL, 'unexpected store');
    }
    for (let i=0;i<12;i++) {
        if (i) await new Promise(r=>setTimeout(r,10000));
        const check = await fetch(URL + '?verify=' + Date.now(), {signal:AbortSignal.timeout(30000)});
        if (check.ok && body.equals(Buffer.from(await check.arrayBuffer()))) {
            console.log(JSON.stringify({file:NAME,published:'1/1',unchanged:!!unchanged,...coverage}));return;
        }
    }
    throw Error('public bytes do not match; no repeated write');
}
module.exports = {validate};
if (require.main === module) main().catch(e=>{
    // No SDK request metadata or credentials in logs.
    console.error('exposure-only publish failed: ' + e.constructor.name);
    process.exitCode=1;
});

const test = require('node:test'), assert = require('node:assert/strict');
const { loadCompanyCoreGraph } = require('../scripts/member-map/company-core-workspace.cjs');
const positions = [{ market: 'KR', ticker: '001111' }];
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const flush = () => new Promise(setImmediate);
function fixture() {
    const core = deferred(), full = deferred(), seen = [], previews = [];
    const parent = new AbortController();
    const graph = ids => ({ companies: [], documents: ids.map(id => ({ id })), coverage: { sources: [] } });
    const response = (ids = ['doc-1'], values = ['d:' + 'a'.repeat(64)]) => ({
        _meta: { snapshot_scope: 'core-facts-disclosures', snapshot_release: 'c'.repeat(64),
            core_claims: { status: 'ready', companies: { 'KR:001111': values } } }, ids });
    const running = loadCompanyCoreGraph({ positions, preview: value => previews.push(value),
        client: async (_positions, o) => {
            const payload = await (await o.fetcher('https://project-yw131.vercel.app/api/member_map_analysis', { method: 'POST', signal: o.signal })).json();
            return graph(payload.ids);
        }, options: { signal: parent.signal, fetcher: async (url, init) => {
            seen.push({ url, signal: init.signal });
            const payload = await (url.includes('company_snapshot') ? core.promise : full.promise);
            return { ok: true, status: 200, json: async () => payload };
        } }, legacy: async () => graph([]), merge: async (_legacy, actual) => { await Promise.resolve(); return actual; } });
    return { core, full, seen, previews, parent, running, response };
}
test('core is available before full; same evidence promotes without losing a card', async () => {
    const f = fixture(); f.core.resolve(f.response()); await flush();
    assert.equal(f.previews.length, 1); assert.equal(f.previews[0].documents[0].id, 'doc-1');
    f.full.resolve(f.response(['doc-1', 'doc-2'], ['d:' + 'a'.repeat(64), 'f:' + 'b'.repeat(64)]));
    assert.equal((await f.running).documents.length, 2);
});
test('source mismatch refuses full replacement', async () => {
    const f = fixture(); f.core.resolve(f.response()); await flush();
    f.full.resolve(f.response(['doc-1'], ['d:' + 'b'.repeat(64)]));
    await assert.rejects(f.running, /generation-mismatch/); assert.equal(f.previews.length, 1);
});
test('pre-cap claims cannot authorize removal from the delivered full payload', async () => {
    const f = fixture(); f.core.resolve(f.response()); await flush(); f.full.resolve(f.response([]));
    await assert.rejects(f.running, /generation-mismatch/);
});
test('completed full lane does not wait for an optimization whose transport ignores abort', async () => {
    const f = fixture(); f.full.resolve(f.response()); const actual = await f.running;
    assert.equal(actual.documents.length, 1); assert.equal(f.seen.find(x => x.url.includes('company_snapshot')).signal.aborted, true);
    f.core.resolve(f.response()); await flush(); assert.equal(f.previews.length, 0);
});
test('failed core stays absent and uses the existing full result', async () => {
    const f = fixture(); f.core.reject(Error('unavailable')); await flush(); f.full.resolve(f.response());
    assert.equal((await f.running).documents.length, 1); assert.equal(f.previews.length, 0);
});
test('parent abort prevents a late core preview even if the transport ignores it', async () => {
    const f = fixture(); f.parent.abort(); f.core.resolve(f.response()); await flush();
    assert.equal(f.previews.length, 0); f.full.reject(Error('aborted')); await assert.rejects(f.running, /aborted/);
});

const test = require('node:test'), assert = require('node:assert/strict');
const { captureAnalysis, claimsOf, coreIncluded, compatibleCoreGraph, ANALYSIS, CORE } = require('../scripts/member-map/company-core-client.cjs');
const positions = [{ market: 'KR', ticker: '001111' }];
const claims = { status: 'ready', companies: { 'KR:001111': ['d:' + 'a'.repeat(64), 'f:' + 'b'.repeat(64)] } };
const payload = () => ({ _meta: { core_claims: structuredClone(claims), snapshot_scope: 'core-facts-disclosures', snapshot_release: 'c'.repeat(64) } });
const graph = () => ({ companies: [], documents: [{ id: 'doc-1' }], coverage: { sources: [
    { sectionId: 'business', state: 'empty' }, { sectionId: 'events', state: 'available' }] } });

test('source core reuses strict adapter, existing auth transport and request-local options', async () => {
    let call;
    const signal = new AbortController().signal;
    const options = { ownerId: 'synthetic-account', signal, getSession: () => ({ token: 'synthetic-token' }),
        fetcher: async (url, init) => { call = { url, init }; return { ok: true, status: 200, json: async () => payload() }; } };
    const client = async (p, o) => {
        assert.deepEqual(p, positions); assert.equal(o.ownerId, options.ownerId); assert.equal(o.signal, signal);
        const result = await o.fetcher(ANALYSIS, { method: 'POST', headers: { Authorization: 'Bearer synthetic-token' }, body: JSON.stringify({ positions }) });
        claimsOf(await result.json(), positions, true); return graph();
    };
    const actual = await captureAnalysis(client, positions, options, true);
    assert.equal(call.url, CORE); assert.equal(call.init.headers.Authorization, 'Bearer synthetic-token');
    assert.equal(actual.graph.coverage.unknown, 1); assert.equal(actual.graph.coverage.empty, 0);
    assert.match(actual.graph.analysisNotice, /연결 중/); assert.equal(actual.release, 'c'.repeat(64));
    assert.equal(JSON.stringify(call).includes('synthetic-account'), false);
});

test('full analysis requests inclusion claims only on its opt-in query', async () => {
    let url;
    const actual = await captureAnalysis(async (_p, options) => {
        await (await options.fetcher(ANALYSIS, { method: 'POST' })).json(); return graph();
    }, positions, { fetcher: async value => { url = value; return { ok: true, status: 200, json: async () => payload() }; } });
    assert.equal(url, ANALYSIS + '?core_claims=1'); assert.equal(actual.release, null);
});

test('new overlay facts may extend a core while changed/missing facts cannot replace it', () => {
    const full = structuredClone(claims); full.companies['KR:001111'].push('d:' + 'e'.repeat(64));
    assert.equal(coreIncluded(claims, full), true);
    for (const bad of [{ status: 'unbounded' }, { status: 'ready', companies: {} }, { status: 'ready', companies: { 'KR:001111': ['d:' + 'a'.repeat(64)] } }])
        assert.equal(coreIncluded(claims, bad), false);
});

test('full document cap cannot remove an already displayed core document', () => {
    const core = { graph: graph(), claims }, full = { claims };
    assert.equal(compatibleCoreGraph(core, full, graph()), true);
    assert.equal(compatibleCoreGraph(core, full, { documents: [] }), false);
});

test('wrong company, duplicate/invalid claims, missing scope and excessive claims fail closed', () => {
    for (const alter of [p => { p._meta.core_claims.companies = {}; }, p => { p._meta.snapshot_scope = 'full'; },
        p => { p._meta.core_claims.companies['KR:001111'].push('bad'); },
        p => { p._meta.core_claims.companies['KR:001111'].push('d:' + 'a'.repeat(64)); },
        p => { delete p._meta.snapshot_release; }]) {
        const p = payload(); alter(p); assert.throws(() => claimsOf(p, positions, true));
    }
});

test('transport cannot redirect an unrelated or non-POST request with the supplied credential', async () => {
    for (const [url, method] of [['https://evil.test', 'POST'], [ANALYSIS, 'PUT']]) {
        let calls = 0;
        await assert.rejects(captureAnalysis(async (_p, o) => o.fetcher(url, { method }), positions,
            { fetcher: () => { calls++; } }, true), /core-transport-rejected/);
        assert.equal(calls, 0);
    }
});

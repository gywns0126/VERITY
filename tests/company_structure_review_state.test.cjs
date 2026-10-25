'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { buildArtifacts } = require('../scripts/member-map/build-live-company-structure.cjs');
const { validatePayload } = require('../scripts/member-map/publish-company-structure.cjs');

function fixture(status = 'needs-review', retained = false) {
  const review = { schema: 'sec-company-subsidiaries-v1', cik: '0000001234',
    accession: '0000001234-26-000002', status: 'needs-review', filedDate: '2026-08-15', periodEnd: '2026-06-30',
    url: 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000002/ex21.htm',
    documentSha256: 'b'.repeat(64), reviewReason: 'ambiguous-row-binding',
    rows: [{ name: 'Unverified Corp.', jurisdiction: 'Delaware', ownershipPct: null, directOwnership: 'unspecified' }] };
  const source = { attemptStatus: status, attemptedAt: '2026-10-25T01:00:00Z', tickerAliases: ['TEST'],
    reviewExhibit: review, sourceGap: 'source-gap:ex21-needs-review' };
  if (retained) Object.assign(source, { lastSuccessAt: '2026-03-01T00:00:00Z', exhibit: {
    ...review, accession: '0000001234-26-000001', status: 'parsed', filedDate: '2026-02-15', periodEnd: '2025-12-31',
    url: 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/ex21.htm', documentSha256: 'a'.repeat(64),
    rows: [{ name: 'Verified Ltd.', jurisdiction: 'Delaware', ownershipPct: null, directOwnership: 'unspecified' }] } });
  return { generatedAt: '2026-10-25T02:00:00Z', strictSources: true,
    universe: { stocks: [{ ticker: 'TEST', name: 'Test Inc.', market: 'US' }] }, cikMap: { TEST: '1234' },
    usSources: { schema: 'alphanest-company-structure-us-sources-v1', issuers: { '0000001234': source } } };
}
function project(args) {
  const built = buildArtifacts(args), entry = built.manifest.issuers['US:TEST'];
  const raw = built.payloads.get(entry.sha256), payload = JSON.parse(raw);
  validatePayload(payload);
  return { built, raw, payload, entry };
}

test('review hold preserves bound pending metadata but never emits unverified rows or a successful check', () => {
  for (const retained of [false, true]) {
    const args = fixture('needs-review', retained), before = JSON.stringify(args);
    const { payload: p, built, entry } = project(args);
    assert.equal(JSON.stringify(args), before);
    assert.equal(entry.status, 'needs-review'); assert.equal(p.coverage.attemptStatus, 'needs-review');
    assert.equal(p.coverage.sourceChecked, false); assert.equal(built.manifest.coverage.US.checkedCiks, 0);
    assert.equal(p.coverage.pendingReview.filedDate, '2026-08-15');
    assert.equal(p.coverage.pendingReview.periodEnd, '2026-06-30');
    assert.equal(p.coverage.pendingReview.reason, 'ambiguous-row-binding');
    assert.equal(p.coverage.pendingReview.documentSha256, 'b'.repeat(64));
    assert.equal(p.relations.length, retained ? 1 : 0);
    assert.ok(!JSON.stringify(p).includes('Unverified Corp.'));
    assert.ok(!JSON.stringify(p.coverage).includes('https://'));
    assert.equal(p.coverage.filedDate, retained ? '2026-02-15' : null);
    assert.equal(p.coverage.lastSuccessAt, retained ? '2026-03-01T00:00:00Z' : null);
    if (retained) { assert.equal(p.relations[0].asOf, '2025-12-31'); assert.equal(p.relations[0].observedAt, '2026-03-01T00:00:00Z'); }
  }
});

test('source gaps, review holds and budget deferrals remain distinct from HTTP and invalid-source failures', () => {
  for (const status of ['needs-review', 'source-gap', 'budget-deferred', 'attempting', 'HTTP503', 'error']) {
    const { payload, entry } = project(fixture(status));
    assert.equal(payload.coverage.attemptStatus, status);
    assert.equal(entry.status, ['HTTP503', 'error'].includes(status) ? 'refresh-error' : status);
    assert.equal(payload.relations.length, 0); assert.equal(payload.coverage.sourceChecked, false);
    assert.equal(!!payload.coverage.pendingReview, status === 'needs-review');
  }
});

test('unbound or future review metadata is omitted; original hold remains and no relationship is promoted', () => {
  for (const mutate of [r => r.cik = '0000009999', r => r.accession = '0000001234-26-000003',
    r => r.url += '?token=secret', r => r.filedDate = '2027-01-01', r => r.periodEnd = '2026-02-30']) {
    const args = fixture(); mutate(args.usSources.issuers['0000001234'].reviewExhibit);
    const { payload } = project(args);
    assert.equal(payload.coverage.status, 'needs-review'); assert.equal(payload.coverage.pendingReview, undefined);
    assert.equal(payload.relations.length, 0);
  }
  const { payload } = project(fixture());
  payload.coverage.pendingReview.reason = '<raw source>'; assert.throws(() => validatePayload(payload));
});

test('exact generated artifacts cross Python API manifest validation, hash check and dispatch without reclassifying holds', () => {
  for (const state of ['needs-review', 'source-gap', 'budget-deferred', 'attempting', 'HTTP503']) {
    const { built, raw, payload } = project(fixture(state, true));
    const script = `import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('structure','vercel-api/api/company_structure.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
v=json.load(sys.stdin)
manifest=v['manifest'].encode();payload=v['payload'].encode()
m._read_public_bytes=lambda url,limit: manifest if url==m.INDEX_URL else payload
status,body=m._dispatch('/api/company_structure?market=US&ticker=TEST')
print(json.dumps({'status':status,'body':body}))`;
    const result = spawnSync('python3', ['-c', script], { cwd: path.resolve(__dirname, '..'), encoding: 'utf8',
      input: JSON.stringify({ manifest: built.manifestBytes.toString(), payload: raw.toString() }) });
    assert.equal(result.status, 0, result.stderr);
    const answer = JSON.parse(result.stdout); assert.equal(answer.status, 200);
    assert.equal(answer.body.coverage.sourceStatus, payload.coverage.status);
    assert.deepEqual(answer.body.relations, payload.relations);
    for (const [key, value] of Object.entries(payload.coverage)) assert.deepEqual(answer.body.coverage[key], value);
  }
});

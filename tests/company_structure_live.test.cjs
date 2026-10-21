'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { createHash } = require('node:crypto');
const { buildArtifacts, writeArtifacts, main, MAX_BYTES } = require('../scripts/member-map/build-live-company-structure.cjs');
const { makeCatalog } = require('../review/member-map/company-structure-data.cjs');

const at = '2026-10-21T10:00:00Z', oldAt = '2026-10-03T10:00:00Z';
const emptySource = () => ({ schema: 'alphanest-company-structure-sources-v1', issuers: {} });
function rawRow(name = 'Holder Corp.', investment = false) {
  const fields = { corp_code: '00000001', rcept_no: '20260814000001', stlm_dt: '2026-06-30',
    ...(investment ? { inv_prm: name, trmend_blce_qota_rt: '25', trmend_blce_qy: '100' } : { nm: name, trmend_posesn_stock_qota_rt: '25' }) };
  return { ...(investment ? { inv_corp_name: name, ownership_pct: 25, end_balance_qty: 100 } : { nm: name, stock_rate: '25' }),
    provenance: { corp_code: fields.corp_code, rcept_no: fields.rcept_no, stlm_dt: fields.stlm_dt, endpoint: investment ? 'otrCprInvstmntSttus' : 'hyslrSttus', bsns_year: '2026', reprt_code: '11012' },
    sourceRow: { index: 0, fields } };
}
function source(holderRows = [rawRow()], investmentRows = [rawRow('Target Ltd.', true)]) {
  return { schema: 'alphanest-company-structure-sources-v1', issuers: { 'KR:0001A0': { ticker: '0001A0', market: 'KR', name: 'Issuer', corp_code: '00000001', collectedAt: oldAt,
    endpoints: { hyslrSttus: { status: '000', attemptStatus: '000', attemptedAt: oldAt, lastSuccessAt: oldAt, rows: holderRows },
      otrCprInvstmntSttus: { status: '000', attemptStatus: '000', attemptedAt: oldAt, lastSuccessAt: oldAt, rows: investmentRows } } } } };
}
const base = () => ({ listed: { '0001A0': { name: 'Issuer', market: 'KQ' } }, sources: source(), generatedAt: at });
const payload = (r, id = 'KR:0001A0') => JSON.parse(r.payloads.get(r.manifest.issuers[id].sha256));

test('market manifest removes the 39 cap, accepts alphanumeric KR, and separately counts excluded assets/CIKs', () => {
  const listed = Object.fromEntries(Array.from({ length: 42 }, (_, i) => [String(100000 + i), { name: `Issuer ${i}` }]));
  listed['0001A0'] = { name: 'Alpha' };
  const r = buildArtifacts({ listed, sources: emptySource(), generatedAt: at,
    universe: { stocks: [{ ticker: 'ABC', name: 'ABC Corp.', market: 'US' }, { ticker: 'DEF', name: 'DEF Corp.', market: 'US' },
      { ticker: 'ETF1', name: 'Fund', market: 'US', type: 'us_etf' }, { ticker: '123456', market: 'ETN' }, { ticker: '^GSPC', market: 'US', type: 'index' }] }, cikMap: { ABC: '123' } });
  assert.equal(r.manifest.coverage.KR.total, 43);
  assert.equal(r.manifest.coverage.US.total, 2);
  assert.equal(r.manifest.coverage.US.withCik, 1);
  assert.equal(r.manifest.coverage.US.withoutCik, 1);
  assert.equal(r.manifest.coverage.US.checked, 0);
  assert.equal(r.manifest.coverage.US.pending, 2);
  assert.deepEqual(r.manifest.coverage.excluded, { ETF: 1, ETN: 1, index: 1, other: 0, invalidTicker: 0 });
  assert.equal(r.manifest.issuers['KR:0001A0'].status, 'not-attempted');
  assert.equal(r.payloads.size, 0);
});

test('matching original company/name/percentage/receipt/settlement date creates only dated shareholder/investment evidence', () => {
  const args = base(), before = JSON.stringify(args), r = buildArtifacts(args), p = payload(r);
  assert.equal(JSON.stringify(args), before);
  assert.equal(p.relations.length, 2);
  assert.equal(p.coverage.sourceChecked, true);
  for (const relation of p.relations) {
    assert.equal(relation.asOf, '2026-06-30'); assert.equal(relation.observedAt, oldAt); assert.equal(relation.ownershipPct, 25);
    assert.equal(relation.status, 'source-dated');
    assert.equal(relation.evidence[0].url, 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814000001');
  }
  assert.equal(p.relations.some(r => r.type === 'subsidiary'), false);
  assert.equal(/sourceRow|trmend_|corp_code|stock_cnt/.test(JSON.stringify(p)), false);
  assert.ok(p.companies.some(c => c.id === 'KR:0001A0'));
});

test('mismatched names, percentages, corporate identity, receipts and invalid settlement dates never become proof', () => {
  for (const change of [r => r.sourceRow.fields.nm = 'Different Corp.', r => r.stock_rate = '60', r => r.sourceRow.fields.corp_code = '99999999',
    r => r.provenance.rcept_no = '20260814000002', r => r.provenance.stlm_dt = '2026-02-30']) {
    const row = rawRow(); change(row);
    const p = payload(buildArtifacts({ ...base(), sources: source([row], []) }));
    assert.equal(p.relations.length, 1);
    assert.equal(p.relations[0].asOf, null); assert.equal(p.relations[0].ownershipPct, null);
    assert.deepEqual(p.relations[0].evidence, []);
  }
});

test('personal/aggregate/fund/zero-original/ended rows are excluded and verified TSMC investment is allowed', () => {
  const zero = rawRow('Zero Ltd.', true); zero.ownership_pct = 0; zero.sourceRow.fields.trmend_blce_qota_rt = '0';
  const ended = rawRow('Ended Ltd.', true); ended.end_balance_qty = 0; ended.sourceRow.fields.trmend_blce_qy = '0';
  const p = payload(buildArtifacts({ ...base(), sources: source([rawRow('김성운'), rawRow('합계'), rawRow('Venture Fund Ltd.')],
    [zero, ended, rawRow('TSMC', true)]), universe: { stocks: [{ ticker: 'TSM', market: 'US', name: 'TSMC' }] } }));
  assert.deepEqual(p.companies.map(c => c.id).sort(), ['KR:0001A0', 'US:TSM']);
  assert.equal(p.relations.length, 1); assert.equal(p.relations[0].type, 'investment'); assert.equal(p.relations[0].status, 'source-dated');
});

test('a failed refresh retains old proof but never promotes its timestamp or checked state', () => {
  const s = source();
  for (const e of Object.values(s.issuers['KR:0001A0'].endpoints)) { e.attemptStatus = 'timeout'; e.attemptedAt = at; }
  const p = payload(buildArtifacts({ ...base(), sources: s }));
  assert.equal(p.coverage.status, 'refresh-error'); assert.equal(p.coverage.sourceChecked, false); assert.equal(p.coverage.attemptStatus, 'error');
  for (const r of p.relations) assert.equal(r.observedAt, oldAt);
  assert.equal(p.coverage.endpoints.hyslrSttus.attemptedAt, at);
  assert.equal(p.coverage.endpoints.hyslrSttus.lastSuccessAt, oldAt);
  const empty = source([], []); for (const e of Object.values(empty.issuers['KR:0001A0'].endpoints)) { e.status = '013'; e.attemptStatus = '013'; }
  const checked = payload(buildArtifacts({ ...base(), sources: empty }));
  assert.equal(checked.coverage.sourceChecked, true); assert.equal(checked.relations.length, 0);
});

test('seed wrapper rows retain provenance and fall back under a newer failed attempt; legacy remains undated', () => {
  const issuer = source().issuers['KR:0001A0'];
  const seed = { schema: 'alphaconsole-dart-structured-provenance-source-v1', issuers: [{ ...issuer, collectedAt: undefined, collected_at: oldAt }] };
  for (const e of Object.values(seed.issuers[0].endpoints)) { delete e.attemptedAt; delete e.attemptStatus; delete e.lastSuccessAt; }
  // The saved seed captures contain only relevant raw fields, not quantity.
  delete seed.issuers[0].endpoints.otrCprInvstmntSttus.rows[0].sourceRow.fields.trmend_blce_qy;
  seed.issuers[0].endpoints.otrCprInvstmntSttus.rows[0].end_balance_qty = 0;
  const sources = source([], []); for (const e of Object.values(sources.issuers['KR:0001A0'].endpoints)) { e.attemptStatus = '020'; e.attemptedAt = at; delete e.lastSuccessAt; }
  const p = payload(buildArtifacts({ ...base(), sources, seed }));
  assert.equal(p.relations.length, 2); assert.equal(p.coverage.status, 'refresh-error');
  for (const r of p.relations) { assert.equal(r.observedAt, oldAt); assert.equal(r.status, 'source-dated'); }
  const legacy = payload(buildArtifacts({ ...base(), sources: emptySource(), ownership: { _meta: { generated_at: oldAt }, holders: { '0001A0': { year: '2025', top: [{ name: 'Holder Corp.', pct: 30 }] } } } }));
  assert.equal(legacy.coverage.status, 'legacy-only'); assert.equal(legacy.coverage.sourceChecked, false);
  assert.equal(legacy.relations[0].asOf, null); assert.deepEqual(legacy.relations[0].evidence, []); assert.equal(legacy.relations[0].ownershipPct, null);
});

test('legacy model defaults stay identical and curations preserve observation time unless a newer dated source wins', () => {
  const input = { count: 1, updated_at: oldAt, structures: { '000660': { ticker: '000660', name: 'SK하이닉스', collected_at: oldAt, major_shareholders: [], subsidiaries: [] } } };
  const legacy = makeCatalog(input), original = JSON.stringify(legacy);
  const options = { listed: { '000660': { name: 'SK하이닉스' } }, sources: emptySource(), legacy, generatedAt: at };
  const first = payload(buildArtifacts(options), 'KR:000660');
  assert.equal(JSON.stringify(legacy), original); assert.equal(first.relations.length, 2);
  assert.equal(first.relations.find(r => r.type === 'subsidiary').observedAt, legacy.relations.find(r => r.type === 'subsidiary').observedAt);
  const row = rawRow('SK스퀘어'); row.sourceRow.fields.stlm_dt = '2026-09-30'; row.provenance.stlm_dt = '2026-09-30';
  row.sourceRow.fields.rcept_no = row.provenance.rcept_no = '20261001000001';
  const s = source([row], []); s.issuers['KR:000660'] = { ...s.issuers['KR:0001A0'], ticker: '000660' }; delete s.issuers['KR:0001A0'];
  const newer = payload(buildArtifacts({ ...options, listed: { ...options.listed, '402340': { name: 'SK스퀘어' } }, sources: s }), 'KR:000660');
  assert.equal(newer.relations.find(r => r.from === 'KR:402340').asOf, '2026-09-30');
  assert.equal(makeCatalog(input, { includeCurations: false }).relations.length, 0);
});

test('exact-byte hashes, fixed manifest filename, input immutability and new-output protection hold', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'company-live-test-'));
  try {
    const sourceDir = path.join(temp, 'input'); fs.mkdirSync(sourceDir);
    const inputs = { 'kr_listed.json': base().listed, 'universe_search.json': {}, 'sec_ticker_cik_map.json': {}, 'sources.json': source() };
    for (const [name, value] of Object.entries(inputs)) fs.writeFileSync(path.join(sourceDir, name), JSON.stringify(value));
    const snapshots = Object.fromEntries(Object.keys(inputs).map(n => [n, fs.readFileSync(path.join(sourceDir, n), 'utf8')]));
    const outputDir = path.join(temp, 'output'); const args = ['--source-dir', sourceDir, '--sources', path.join(sourceDir, 'sources.json'), '--output-dir', outputDir, '--generated-at', at];
    const built = main(args);
    const manifest = JSON.parse(fs.readFileSync(path.join(outputDir, 'member_map_company_structure_index.json')));
    for (const entry of Object.values(manifest.issuers).filter(e => e.sha256)) {
      const bytes = fs.readFileSync(path.join(outputDir, 'company-structure', entry.sha256 + '.json'));
      assert.equal(bytes.length, entry.bytes); assert.equal(createHash('sha256').update(bytes).digest('hex'), entry.sha256); assert.ok(bytes.length <= MAX_BYTES);
    }
    assert.equal(manifest.issuers['KR:0001A0'].sha256, built.manifest.issuers['KR:0001A0'].sha256);
    assert.throws(() => main(args), /new output directory/u);
    for (const n of Object.keys(inputs)) assert.equal(fs.readFileSync(path.join(sourceDir, n), 'utf8'), snapshots[n]);
    assert.equal(JSON.stringify(manifest).includes('https://'), false);
  } finally { fs.rmSync(temp, { recursive: true, force: true }); }
});

test('issuer/node/relation/serialized byte bounds and invalid schemas fail closed', () => {
  assert.throws(() => buildArtifacts({ ...base(), sources: { issuers: {} } }), /source schema/u);
  assert.throws(() => buildArtifacts({ ...base(), generatedAt: '2026-02-30T00:00:00Z' }), /generatedAt/u);
  assert.throws(() => buildArtifacts({ listed: Object.fromEntries(Array.from({ length: 25001 }, (_, n) => [String(n).padStart(6, '0'), { name: 'Issuer' }])) }), /Issuer limit/u);
  const largeUs = Array.from({ length: 16000 }, (_, n) => ({ ticker: 'A' + String(n).padStart(5, '0'), market: 'US', name: 'A'.repeat(100) }));
  assert.throws(() => buildArtifacts({ sources: emptySource(), universe: { stocks: largeUs } }), /Manifest byte limit/u);
  const rows = Array.from({ length: 3001 }, (_, n) => rawRow(`Company ${n} Corp.`));
  assert.throws(() => buildArtifacts({ ...base(), sources: source(rows, []) }), /limit/u);
});

test('available local 39-issuer capture replays the whole current market offline into a temporary output', t => {
  const root = '/Users/macbookpro/Desktop/배리티 터미널', wt = path.resolve(__dirname, '..');
  const seedFile = path.join(root, 'output/member-map-integration-20260927/relationship-acceptance-20261003/dart-structured-provenance-source.json');
  if (!fs.existsSync(seedFile)) { t.skip('Local saved capture is not installed in this checkout'); return; }
  const read = (file, fallback = {}) => { const p = path.join(wt, 'data', file); return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p)) : fallback; };
  const r = buildArtifacts({ listed: read('kr_listed.json'), universe: read('universe_search.json'), cikMap: read('sec_ticker_cik_map.json'), groups: read('group_structure.json'), ownership: read('kr_ownership.json'),
    seed: JSON.parse(fs.readFileSync(seedFile)), sources: emptySource(), generatedAt: at,
    legacy: JSON.parse(fs.readFileSync(path.join(wt, 'vercel-api/public/member-map-review/company-structure.json'))) });
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'company-live-replay-')), outputDir = path.join(temp, 'public');
  writeArtifacts(r, outputDir);
  const all = [...r.payloads.values()].map(b => JSON.parse(b));
  const evidenceCompanies = all.filter(p => p.relations.some(r => r.evidence.length)).length;
  t.diagnostic(JSON.stringify({ outputDir, coverage: r.manifest.coverage, payloads: r.payloads.size, evidenceCompanies,
    verifiedRelations: all.reduce((n, p) => n + p.relations.filter(r => r.status === 'source-dated').length, 0),
    storedRelations: all.reduce((n, p) => n + p.relations.filter(r => r.status === 'undated-snapshot').length, 0), manifestBytes: r.manifestBytes.length,
    payloadBytes: [...r.payloads.values()].reduce((n, b) => n + b.length, 0), maxPayloadBytes: Math.max(0, ...[...r.payloads.values()].map(b => b.length)) }));
  assert.ok(r.manifest.coverage.KR.total > 39); assert.ok(r.manifest.coverage.US.total > 0);
  assert.equal(r.manifest.coverage.US.checked, 0); assert.ok(r.manifestBytes.length <= MAX_BYTES);
  const c = r.manifest.coverage;
  assert.equal(c.rawRowsExamined, c.rawVerifiedRows + c.storedRows + c.unsupportedRows);
});

function usFixture() {
  return { universe: { stocks: [{ ticker: 'ACME', name: 'Acme Corp.', market: 'US' }, { ticker: 'ACME.A', name: 'Acme Corp.', market: 'US' }, { ticker: 'GAP', name: 'Gap Inc.', market: 'US' }] },
    cikMap: { ACME: '1234', 'ACME.A': '0000001234' }, generatedAt: at,
    usSources: { schema: 'alphanest-company-structure-us-sources-v1', issuers: { '0000001234': {
      attemptStatus: 'success', attemptedAt: at, lastSuccessAt: oldAt, tickerAliases: ['ACME', 'ACME.A'],
      exhibit: { schema: 'sec-company-subsidiaries-v1', cik: '0000001234', accession: '0000001234-26-000001', status: 'parsed', filedDate: '2026-02-15', periodEnd: '2025-12-31',
        url: 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/ex21.htm', documentSha256: 'a'.repeat(64),
        rows: [{ name: 'Subsidiary Ltd.', jurisdiction: 'Delaware', ownershipPct: null, directOwnership: 'unspecified', sourceRow: { text: 'Subsidiary Ltd. Delaware' } }] } } } } };
}
test('US CIK deduped denominator does not merge security-root graphs or infer direct control/country', () => {
  const args = usFixture(), before = JSON.stringify(args), r = buildArtifacts(args);
  assert.equal(JSON.stringify(args), before);
  assert.equal(r.manifest.coverage.US.total, 3); assert.equal(r.manifest.coverage.US.uniqueCiks, 1);
  assert.equal(r.manifest.coverage.US.checkedCiks, 1); assert.equal(r.manifest.coverage.US.checked, 2);
  assert.notEqual(r.manifest.issuers['US:ACME'].sha256, r.manifest.issuers['US:ACME.A'].sha256);
  for (const ticker of ['ACME', 'ACME.A']) {
    const p = payload(r, 'US:' + ticker), edge = p.relations[0];
    assert.equal(edge.from, 'US:' + ticker); assert.equal(edge.type, 'subsidiary'); assert.equal(edge.label, '공시상 자회사·직간접 미구분');
    assert.equal(edge.ownershipPct, null); assert.equal(edge.asOf, '2025-12-31'); assert.equal(edge.evidence[0].asOf, '2026-02-15');
    assert.ok(p.companies.every(c => c.country === undefined)); assert.equal(JSON.stringify(p).includes('sourceRow'), false);
  }
  assert.equal(r.manifest.issuers['US:GAP'].sha256, undefined);
});
test('US failed retained sources stay old; wrong CIK/unsafe URL never produce proof or unchecked placeholders', () => {
  const args = usFixture(); args.usSources.issuers['0000001234'].attemptStatus = 'HTTP429';
  const p = payload(buildArtifacts(args), 'US:ACME');
  assert.equal(p.coverage.sourceChecked, false); assert.equal(p.coverage.status, 'refresh-error'); assert.equal(p.relations[0].observedAt, oldAt);
  assert.equal(p.coverage.attemptStatus, 'HTTP429'); assert.equal(p.coverage.attemptedAt, at); assert.equal(p.coverage.lastSuccessAt, oldAt);
  for (const mutate of [e => e.cik = '0000009999', e => e.url += '?token=private', e => e.url = 'https://evil.example/ex21.htm']) {
    const a = usFixture(); mutate(a.usSources.issuers['0000001234'].exhibit);
    assert.equal(payload(buildArtifacts(a), 'US:ACME').relations.length, 0);
  }
  const a = usFixture(); a.usSources.issuers['0000001234'].attemptedAt = null;
  assert.equal(buildArtifacts(a).payloads.size, 0);
});
test('DART original qy is authoritative, missing original quantity never turns parser-default zero into ended proof', () => {
  const s = source([], [rawRow('Active Corp.', true)]), row = s.issuers['KR:0001A0'].endpoints.otrCprInvstmntSttus.rows[0];
  row.end_balance_qty = 0; delete row.sourceRow.fields.trmend_blce_qy;
  assert.equal(payload(buildArtifacts({ ...base(), sources: s })).relations[0].status, 'source-dated');
  row.sourceRow.fields.trmend_blce_qy = '100';
  assert.equal(payload(buildArtifacts({ ...base(), sources: s })).relations[0].status, 'undated-snapshot');
  row.sourceRow.fields.trmend_blce_qy = '0';
  assert.equal(payload(buildArtifacts({ ...base(), sources: s })).relations.length, 0);
});

test('live per-issuer sorting keeps official Solidigm within six branches before listed then unlisted raw investments', () => {
  const legacy = makeCatalog({ updated_at: oldAt, count: 1, structures: { '000660': { ticker: '000660', name: 'SK하이닉스', collected_at: oldAt, major_shareholders: [], subsidiaries: [] } } });
  const r = buildArtifacts({ listed: { '000660': { name: 'SK하이닉스' }, '111111': { name: 'Listed Corp.' } }, legacy, generatedAt: at,
    groups: { structures: { '000660': { collected_at: oldAt, subsidiaries: [
      ...Array.from({ length: 9 }, (_, n) => ({ name: `Raw ${n} Ltd.` })), { name: 'Listed Corp.' }], major_shareholders: [] } } } });
  const p = payload(r, 'KR:000660'), outgoing = p.relations.filter(r => r.from === 'KR:000660');
  assert.equal(outgoing[0].to, 'FOREIGN:solidigm-inc'); assert.equal(outgoing[1].to, 'KR:111111');
  assert.ok(outgoing.slice(0, 6).some(r => r.to === 'FOREIGN:solidigm-inc')); assert.equal(outgoing.length, 11);
});

test('unattempted endpoint placeholders remain metadata-only; unchanged stored data has stable payload hashes across builds', () => {
  const sources = source([], []);
  for (const e of Object.values(sources.issuers['KR:0001A0'].endpoints)) {
    Object.assign(e, { status: 'error', attemptStatus: 'not-attempted', attemptedAt: null, lastSuccessAt: null });
  }
  sources.issuers['KR:0001A0'].collectedAt = null;
  const a = { listed: base().listed, sources, generatedAt: at };
  const r = buildArtifacts(a); assert.equal(r.payloads.size, 0); assert.equal(r.manifest.issuers['KR:0001A0'].status, 'not-attempted');
  a.ownership = { holders: { '0001A0': { top: [{ name: 'Holder Corp.', pct: 30 }] } } };
  const first = buildArtifacts(a), second = buildArtifacts({ ...a, generatedAt: '2026-10-22T12:00:00Z' });
  assert.equal(first.manifest.issuers['KR:0001A0'].sha256, second.manifest.issuers['KR:0001A0'].sha256);
});

test('publication build rejects a newly successful row with broken binding; valid dotted settlement dates normalize without changing inputs', () => {
  const a = base(); a.sources.issuers['KR:0001A0'].endpoints.hyslrSttus.rows[0].sourceRow.fields.nm = 'Wrong Corp.';
  assert.throws(() => buildArtifacts({ ...a, strictSources: true }), /binding/u);
  const b = base(), row = b.sources.issuers['KR:0001A0'].endpoints.hyslrSttus.rows[0];
  row.provenance.stlm_dt = row.sourceRow.fields.stlm_dt = '2026.06.30';
  assert.equal(payload(buildArtifacts({ ...b, strictSources: true })).relations.find(r => r.type === 'major-shareholder').asOf, '2026-06-30');
  const c = usFixture(); c.usSources.issuers['0000001234'].exhibit.cik = '0000009999';
  assert.throws(() => buildArtifacts({ ...c, strictSources: true }), /binding/u);
});

test('cross-period 013 retains older successful corporate rows without claiming latest-period coverage; real replacement 013 stays empty', () => {
  const a = base();
  for (const e of Object.values(a.sources.issuers['KR:0001A0'].endpoints)) { e.attemptStatus = '013'; e.attemptedAt = at; }
  const p = payload(buildArtifacts(a));
  assert.equal(p.relations.length, 2); assert.equal(p.coverage.sourceChecked, false); assert.equal(p.coverage.status, 'partial');
  assert.ok(p.relations.every(r => r.observedAt === oldAt && r.asOf === '2026-06-30'));
  const state = p.coverage.endpoints.hyslrSttus;
  assert.deepEqual(state, { status: '000', attemptStatus: '013', attemptedAt: at, lastSuccessAt: oldAt });
  for (const e of Object.values(a.sources.issuers['KR:0001A0'].endpoints)) { e.status = '013'; e.lastSuccessAt = at; }
  const replaced = payload(buildArtifacts(a));
  assert.equal(replaced.relations.length, 0); assert.equal(replaced.coverage.sourceChecked, true);
});

test('US same-name entities in different original jurisdictions remain distinct without country inference', () => {
  const a = usFixture(), rows = a.usSources.issuers['0000001234'].exhibit.rows;
  rows.push({ ...rows[0], jurisdiction: 'California' });
  const p = payload(buildArtifacts(a), 'US:ACME');
  assert.equal(p.relations.length, 2); assert.notEqual(p.relations[0].to, p.relations[1].to);
  const peers = p.companies.filter(c => c.id.startsWith('FOREIGN:'));
  assert.equal(peers.length, 2); assert.equal(peers[0].name, peers[1].name);
  assert.ok(p.companies.every(c => c.country === undefined));
});

test('DART rejects future settlement evidence, invalid receipt calendar dates and settlement after receipt', () => {
  for (const [settlement, receipt] of [['2026-11-30', '20261215000001'], ['2026-06-30', '20260230000001'], ['2026-08-15', '20260814000001']]) {
    const row = rawRow(); row.provenance.stlm_dt = row.sourceRow.fields.stlm_dt = settlement;
    row.provenance.rcept_no = row.sourceRow.fields.rcept_no = receipt;
    const args = { ...base(), sources: source([row], []) }, before = JSON.stringify(args);
    const relation = payload(buildArtifacts(args)).relations[0];
    assert.equal(relation.status, 'undated-snapshot'); assert.equal(relation.asOf, null); assert.deepEqual(relation.evidence, []);
    assert.throws(() => buildArtifacts({ ...args, strictSources: true }), /binding|date ordering/u);
    assert.equal(JSON.stringify(args), before);
  }
  const row = rawRow(); row.provenance.stlm_dt = row.sourceRow.fields.stlm_dt = '2026-08-14';
  const args = { ...base(), sources: source([row], []) };
  Object.assign(args.sources.issuers['KR:0001A0'].endpoints.hyslrSttus, { attemptedAt: '2026-08-14T23:00:00Z', lastSuccessAt: '2026-08-14T23:00:00Z' });
  assert.equal(payload(buildArtifacts({ ...args, strictSources: true })).relations[0].asOf, '2026-08-14');
});

test('SEC confirms only calendar-valid period end <= filing date <= original successful observation date', () => {
  for (const [periodEnd, filedDate, lastSuccessAt] of [
    ['2026-03-01', '2026-02-15', oldAt], ['2025-12-31', '2026-10-04', oldAt], ['2025-12-31', '2026-02-30', oldAt],
  ]) {
    const a = usFixture(), issuer = a.usSources.issuers['0000001234'];
    Object.assign(issuer.exhibit, { periodEnd, filedDate }); issuer.lastSuccessAt = lastSuccessAt;
    const before = JSON.stringify(a), p = payload(buildArtifacts(a), 'US:ACME');
    assert.equal(p.coverage.sourceChecked, false); assert.equal(p.coverage.status, 'refresh-error'); assert.equal(p.relations.length, 0);
    assert.throws(() => buildArtifacts({ ...a, strictSources: true }), /SEC source binding/u);
    assert.equal(JSON.stringify(a), before);
    issuer.attemptStatus = 'HTTP403';
    const retained = payload(buildArtifacts(a), 'US:ACME');
    assert.equal(retained.relations.length, 0); assert.equal(retained.coverage.lastSuccessAt, lastSuccessAt);
    assert.equal(retained.coverage.attemptStatus, 'HTTP403');
  }
  const a = usFixture(), issuer = a.usSources.issuers['0000001234'];
  issuer.exhibit.periodEnd = issuer.exhibit.filedDate = '2026-10-03';
  assert.equal(payload(buildArtifacts({ ...a, strictSources: true }), 'US:ACME').relations[0].asOf, '2026-10-03');
});

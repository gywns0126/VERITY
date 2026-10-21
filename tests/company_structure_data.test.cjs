'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { makeCatalog, selectedRootNeighbors, safeUrl, primaryEvidenceUrl } = require('../review/member-map/company-structure-data.cjs');

const at = '2026-10-21T00:00:00.000Z';
const sample = { updated_at: at, count: 2, structures: {
  '000660': { ticker: '000660', name: 'SK하이닉스', collected_at: at,
    parent: { name: 'SK스퀘어(주)', symbol: '402340', relate: '최대주주', ownership_pct: 20.07 },
    major_shareholders: [], subsidiaries: [{ name: 'SK hynix NAND Product Solutions Corp.', ownership_pct: 97.5 },
      { name: 'Solidigm Inc.', ownership_pct: 99 }, { name: 'TSMC', symbol: 'TSM', market: 'US', ownership_pct: 10 }, { name: '펀드', ownership_pct: 1 }] },
  '003550': { ticker: '003550', name: 'LG', collected_at: at,
    parent: { name: '구광모', relate: '최대주주 본인', ownership_pct: 16.27 },
    major_shareholders: [], subsidiaries: [{ name: 'LG Corp.', ownership_pct: 50 }, { name: 'LG', symbol: '003550', ownership_pct: 1 }] },
} };

test('curations replace stale pairs and preserve distinct Solidigm legal entities', () => {
  const data = makeCatalog(sample, { officialObservedAt: at });
  assert.equal(data.schema, 'alphanest-company-structure-v1');
  assert.equal(data.coverage.sourceIssuers, 2);
  const square = data.relations.filter(r => r.from === 'KR:402340' && r.to === 'KR:000660');
  assert.equal(square.length, 1);
  assert.equal(square[0].ownershipPct, 20.5);
  assert.equal(square[0].asOf, '2026-05-06');
  assert.equal(square[0].status, 'source-dated');
  assert.equal(square[0].label, '주요주주');
  assert.equal(square[0].evidence[0].url, 'https://www.skhynix.com/ir/UI-FR-IR04/');
  const solidigm = data.relations.filter(r => r.from === 'KR:000660' && r.to === 'FOREIGN:solidigm-inc');
  assert.equal(solidigm.length, 1);
  assert.equal(solidigm[0].type, 'subsidiary');
  assert.equal(solidigm[0].asOf, null);
  assert.equal(solidigm[0].status, 'official-undated');
  assert.equal(solidigm[0].ownershipPct, null);
  assert.equal(solidigm[0].evidence[0].url, 'https://www.solidigm.com/support/faqs.html');
  const legacy = data.companies.find(c => c.name === 'SK hynix NAND Product Solutions Corp.');
  assert.ok(legacy && legacy.id !== 'FOREIGN:solidigm-inc');
  assert.equal(data.relations.find(r => r.to === legacy.id).type, 'investment');
  const investment = data.relations.find(r => r.to === 'FOREIGN:solidigm-inc' && r.type === 'investment');
  assert.equal(investment, undefined);
  const other = data.relations.find(r => r.from === 'KR:003550' && r.type === 'investment');
  assert.equal(other.asOf, null);
  assert.equal(other.status, 'undated-snapshot');
  assert.equal(other.observedAt, at);
  assert.equal(other.ownershipPct, null);
  assert.equal(data.relations.some(r => r.from === r.to), false);
  assert.equal(data.companies.some(c => c.name === '구광모' || c.name === 'TSMC'), false);
  assert.equal(data.relations.some(r => r.type === 'subsidiary' && r.to !== 'FOREIGN:solidigm-inc'), false);
  assert.deepEqual(selectedRootNeighbors(data, '000660').relations.map(r => r.type).sort(), ['investment', 'major-shareholder', 'subsidiary']);
});

function fixture(parent, investments, extra = {}) {
  return { updated_at: at, count: 1, structures: { '123456': { ticker: '123456', name: '123456.KQ', collected_at: at,
    parent, major_shareholders: parent ? [parent] : [], subsidiaries: investments, ...extra } } };
}

test('parent is a shareholder regardless of collector relate; group never creates ownership', () => {
  const input = fixture({ name: 'Owner Corp.', relate: '본인', ownership_pct: 90 }, [{ name: 'Target Ltd.', ownership_pct: 100 }], { group_name: 'Imaginary Group' });
  const data = makeCatalog(input);
  const holder = data.relations.find(r => r.to === 'KR:123456');
  assert.equal(holder.type, 'major-shareholder');
  assert.equal(holder.ownershipPct, null);
  assert.equal(holder.observedAt, at);
  assert.equal(data.relations.find(r => r.from === 'KR:123456').type, 'investment');
  assert.equal(data.companies.some(c => c.name === 'Imaginary Group'), false);
  assert.deepEqual(input, fixture({ name: 'Owner Corp.', relate: '본인', ownership_pct: 90 }, [{ name: 'Target Ltd.', ownership_pct: 100 }], { group_name: 'Imaginary Group' }));
});

test('explicit US listings, local name aliases and unknown foreign jurisdiction are separate', () => {
  const data = makeCatalog(fixture(null, [
    { name: 'Foreign Corp.', symbol: 'ABCD', market: 'NASDAQ' },
    { name: 'Unknown GmbH' }, { name: '(주)한회사' },
    { name: 'Sk Square' }, { name: 'sk hynix Inc.' },
  ]), { names: { '123456': '한회사' } });
  assert.equal(data.companies.find(c => c.id === 'US:ABCD').country, undefined);
  assert.equal(data.companies.find(c => c.name === 'Unknown GmbH').country, undefined);
  assert.equal(data.companies.find(c => c.id === 'KR:123456').name, '한회사');
  assert.equal(data.companies.some(c => c.name === '(주)한회사'), false);
  assert.equal(data.relations.some(r => r.from === r.to), false);
  assert.equal(data.companies.filter(c => c.id === 'KR:402340').length, 1);
  assert.equal(data.companies.filter(c => c.id === 'KR:000660').length, 1);
});

test('dated values need real calendar dates; evidence is copied only from valid links', () => {
  const input = fixture(null, [
    { name: 'Dated Ltd.', asOf: '2026-09-01', ownership_pct: 12.5, links: { official: 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260901000001', unsafe: 'javascript:alert(1)' } },
    { name: 'Invalid Ltd.', asOf: '2026-02-30', ownership_pct: 80 },
    { name: 'No Link Ltd.', ownership_pct: 99 },
  ]);
  const data = makeCatalog(input);
  const relation = name => data.relations.find(r => r.to === data.companies.find(c => c.name === name).id);
  assert.equal(relation('Dated Ltd.').ownershipPct, 12.5);
  assert.deepEqual(relation('Dated Ltd.').evidence.map(e => e.url), ['https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260901000001']);
  assert.equal(relation('Invalid Ltd.').asOf, null);
  assert.equal(relation('Invalid Ltd.').ownershipPct, null);
  assert.deepEqual(relation('No Link Ltd.').evidence, []);
  const datedRow = makeCatalog(fixture(null, [{ name: 'Row Dated Ltd.', ownership_pct: 14 }], { asOf: '2026-08-01' }));
  assert.equal(datedRow.relations.find(r => r.from === 'KR:123456').asOf, '2026-08-01');
});

test('personal shareholders and vehicles are omitted, names stay compact, identities do not truncate', () => {
  const prefix = 'Company '.repeat(30);
  const data = makeCatalog(fixture({ name: '김성운' }, [
    { name: '김성운' }, { name: 'Venture Fund Ltd.' }, { name: `${prefix}A Ltd.` }, { name: `${prefix}B Ltd.` },
    { name: '<X>\u0000\u202e Corp.' },
  ]));
  assert.equal(data.companies.some(c => c.name === '김성운' || /Fund/u.test(c.name)), false);
  const long = data.companies.filter(c => c.name.startsWith('Company'));
  assert.equal(long.length, 2);
  assert.notEqual(long[0].id, long[1].id);
  for (const c of data.companies) { assert.ok(c.name.length <= 100); assert.doesNotMatch(c.name, /[<>\u0000\u202e]/u); }
});

test('malformed sources fail closed and node/relation budgets are enforced', () => {
  assert.throws(() => makeCatalog({ ...sample, count: 39 }), /count/u);
  assert.throws(() => makeCatalog(fixture(null, [], { collected_at: '2026-09-01' })), /observedAt/u);
  assert.throws(() => makeCatalog(fixture(null, Array.from({ length: 3001 }, (_, i) => ({ name: `Company ${i} Ltd.` })))), /Company limit/u);
  // Keep nodes under budget while adding more than 3000 distinct issuer-target pairs.
  const structures = Object.fromEntries(Array.from({ length: 60 }, (_, i) => {
    const code = String(100000 + i);
    return [code, { ticker: code, name: `Issuer ${i}`, collected_at: at, parent: null, major_shareholders: [], subsidiaries: Array.from({ length: 51 }, (_, n) => ({ name: `Target ${n} Ltd.` })) }];
  }));
  assert.throws(() => makeCatalog({ updated_at: at, count: 60, structures }), /Relation limit/u);
});

test('URL allowlist rejects unsafe and credential-bearing links', () => {
  assert.equal(safeUrl('javascript:alert(1)'), null);
  assert.equal(safeUrl('http://example.com'), null);
  assert.equal(safeUrl('https://user:secret@example.com'), null);
  assert.equal(safeUrl('https:example.com'), null);
  assert.equal(safeUrl('https://example.com/\npath'), null);
  assert.equal(safeUrl('https://example.com/path'), 'https://example.com/path');
});

test('official Solidigm branch precedes raw outgoing investments within the six-branch budget', () => {
  const input = structuredClone(sample);
  input.structures['000660'].subsidiaries.unshift(...Array.from({ length: 12 }, (_, n) => ({ name: `Branch ${n} Ltd.` })));
  const data = makeCatalog(input);
  const branches = data.relations.filter(r => r.from === 'KR:000660');
  assert.ok(branches.length > 6);
  assert.equal(branches[0].to, 'FOREIGN:solidigm-inc');
  assert.equal(data.companies.find(c => c.id === branches[0].to).country, 'US');
  assert.equal(branches.slice(0, 6).filter(r => r.type === 'subsidiary').length, 1);
});

test('quote/wiki/profile/share links never become ownership evidence', () => {
  const links = {
    namuwiki: 'https://namu.wiki/w/Test', official: 'https://finance.naver.com/item/main.naver?code=000660',
    profile: 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=&command=searchCompanyInfoDetail&corpCode=123',
    share: 'https://www.solidigm.com/share/test', fakeOfficial: 'https://www.solidigm.com.evil.test/report',
  };
  for (const url of Object.values(links)) assert.equal(primaryEvidenceUrl(url), null);
  const data = makeCatalog(fixture(null, [{ name: 'Snapshot Corp.', ownership_pct: 90, links }]));
  const r = data.relations.find(r => r.from === 'KR:123456');
  assert.deepEqual(r.evidence, []);
  assert.equal(r.asOf, null);
  assert.equal(r.status, 'undated-snapshot');
  assert.equal(data.coverage.relationsWithoutOriginalUrls, 1);
});

test('curated then listed then unlisted relation order preserves listed identities', () => {
  const data = makeCatalog(fixture(null, [
    { name: 'Ambiguous Corp.' }, { name: 'Listed Corp.', symbol: '654321' },
  ]));
  const children = data.relations.filter(r => r.from === 'KR:123456');
  assert.equal(children[0].to, 'KR:654321');
  assert.match(children[1].to, /^FOREIGN:/u);
  assert.equal(data.relations.slice(0, 2).every(r => r.from === 'KR:000660' || r.from === 'KR:402340'), true);
  assert.match(data.coverage.identityNote, /opaque ID namespace, not a country assertion/u);
});

test('published catalogue is bounded, internally linked, and source honest', () => {
  const data = JSON.parse(fs.readFileSync(path.join(__dirname, '../vercel-api/public/member-map-review/company-structure.json'), 'utf8'));
  assert.equal(data.schema, 'alphanest-company-structure-v1');
  assert.equal(data.coverage.sourceIssuers, 39);
  assert.equal(data.coverage.sourceMajorShareholderRows, 149);
  assert.equal(data.coverage.sourceInvestmentRows, 1125);
  assert.ok(data.companies.length <= 3000 && data.relations.length <= 3000);
  const ids = new Set(data.companies.map(c => c.id));
  assert.equal(ids.size, data.companies.length);
  assert.equal(new Set(data.relations.map(r => `${r.from}|${r.to}`)).size, data.relations.length);
  for (const c of data.companies) {
    if (c.market === 'KR' || c.market === 'US') assert.equal(c.id, `${c.market}:${c.ticker}`);
    else assert.match(c.id, /^FOREIGN:/u);
  }
  for (const r of data.relations) {
    assert.ok(ids.has(r.from) && ids.has(r.to));
    assert.notEqual(r.from, r.to);
    assert.ok(['major-shareholder', 'investment', 'subsidiary'].includes(r.type));
    assert.equal(r.asOf === null, r.status === 'undated-snapshot' || r.status === 'official-undated');
    if (r.asOf === null) assert.equal(r.ownershipPct, null);
    for (const proof of r.evidence) assert.equal(primaryEvidenceUrl(proof.url), proof.url);
  }
  assert.equal(data.relations.filter(r => r.type === 'subsidiary').length, 1);
  assert.equal(data.coverage.relationsWithoutOriginalUrls, data.relations.filter(r => !r.evidence.length).length);
  assert.equal(data.relations.filter(r => r.from === 'KR:000660')[0].to, 'FOREIGN:solidigm-inc');
  assert.equal(data.companies.some(c => ['구광모', '김성운', '정의선'].includes(c.name)), false);
  assert.equal(data.relations.some(r => r.from === 'KR:000660' && r.to === 'KR:402340'), false);
});

test('builder requires explicit paths and preserves the source; offline output reproduces exactly', () => {
  const script = path.join(__dirname, '../scripts/member-map/build-company-structure-data.cjs');
  assert.notEqual(spawnSync(process.execPath, [script], { encoding: 'utf8' }).status, 0);
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'company-structure-test-'));
  try {
    const source = path.join(temp, 'source.json');
    const output = path.join(temp, 'output.json');
    const structures = Object.fromEntries(Array.from({ length: 39 }, (_, i) => {
      const code = String(100000 + i);
      return [code, { ticker: code, name: `Issuer ${i}`, collected_at: at, major_shareholders: [], subsidiaries: [] }];
    }));
    const bytes = JSON.stringify({ updated_at: at, count: 39, structures });
    fs.writeFileSync(source, bytes);
    assert.notEqual(spawnSync(process.execPath, [script, '--input', source], { encoding: 'utf8' }).status, 0);
    assert.notEqual(spawnSync(process.execPath, [script, '--input', source, '--output', source], { encoding: 'utf8' }).status, 0);
    const args = [script, '--input', source, '--output', output];
    assert.equal(spawnSync(process.execPath, args, { encoding: 'utf8' }).status, 0);
    const first = fs.readFileSync(output, 'utf8');
    assert.equal(spawnSync(process.execPath, args, { encoding: 'utf8' }).status, 0);
    assert.equal(fs.readFileSync(output, 'utf8'), first);
    assert.equal(fs.readFileSync(source, 'utf8'), bytes);
  } finally { fs.rmSync(temp, { recursive: true, force: true }); }
});

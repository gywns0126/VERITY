'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { buildArtifacts, usSubsidiaryLabel } = require('../scripts/member-map/build-live-company-structure.cjs');
const { sanitizeUsSources, validatePayload } = require('../scripts/member-map/publish-company-structure.cjs');

const at = '2026-10-25T09:00:00Z', observed = '2026-10-23T19:57:39Z';
// The previously omitted legal forms from the reviewed EQT/SPG exhibits. This
// fixture tests classification only; original bytes and dates are audited in the
// release receipt before any real source is promoted.
const names = [
  'EQM Midstream Partners, LP', 'Equitrans, L.P.',
  'Simon Property Group, L.P.', 'The Retail Property Trust',
  'Simon Property Group (Illinois), L.P.', 'Simon Property Group (Texas), L.P.',
  'Simon Property Group Administrative Services Partnership, L.P.',
  'Kravco Simon Investments, L.P.', 'Premium Outlet Partners, L.P.',
  'Simon Global Development B.V.', 'Simon MAC S.a.r.l.', 'Simon International S.a.r.l.',
];
const row = name => ({ name, jurisdiction: 'Delaware', ownershipPct: null, directOwnership: 'unspecified' });
function fixture(values = names) {
  const source = { cik: '0000001234', tickerAliases: ['ACME'], attemptStatus: 'success', attemptedAt: at,
    lastSuccessAt: observed, exhibit: { schema: 'sec-company-subsidiaries-v1', cik: '0000001234',
      accession: '0000001234-26-000001', status: 'parsed', filedDate: '2026-02-18', periodEnd: '2025-12-31',
      url: 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/ex21.htm',
      documentSha256: 'a'.repeat(64), rows: values.map(row) } };
  return { schema: 'alphanest-company-structure-us-sources-v1', generatedAt: at, issuers: { '0000001234': source } };
}
function project(doc, strictSources = true) {
  const result = buildArtifacts({ generatedAt: at, strictSources,
    universe: { stocks: [{ ticker: 'ACME', name: 'Acme Corp.', market: 'US' }] },
    cikMap: { ACME: '1234' }, usSources: doc });
  return JSON.parse(result.payloads.get(result.manifest.issuers['US:ACME'].sha256));
}

test('reviewed US legal forms have the same admission rule across all three public boundaries', () => {
  const raw = fixture(), before = JSON.stringify(raw), safe = sanitizeUsSources(raw);
  assert.equal(JSON.stringify(raw), before);
  assert.deepEqual(safe.issuers['0000001234'].exhibit.rows.map(r => r.name), names);
  assert.deepEqual(sanitizeUsSources(safe), safe);
  const p = project(safe);
  assert.deepEqual(p.companies.filter(c => c.id !== 'US:ACME').map(c => c.name), names);
  assert.equal(p.relations.length, 12);
  assert.equal(p.coverage.unsupportedRows, 0);
  assert.ok(p.companies.every(c => c.country === undefined));
  assert.ok(p.relations.every(r => r.ownershipPct === null && r.asOf === '2025-12-31' &&
    r.observedAt === observed && r.evidence[0].asOf === '2026-02-18' && r.label === '공시상 자회사·직간접 미구분'));
  assert.doesNotThrow(() => validatePayload(p));
});

test('legal-form punctuation is equivalent, not an arbitrary word inside a name', () => {
  for (const [a, b] of [['Example L.P.', 'Example LP'], ['Example B.V.', 'Example BV'],
    ['Example S.a.r.l.', 'Example SARL'], ['Example S.R.L.', 'Example SRL'], ['Example W.L.L.', 'Example WLL']]) {
    assert.equal(usSubsidiaryLabel(a), true, a); assert.equal(usSubsidiaryLabel(b), true, b);
  }
  assert.equal(usSubsidiaryLabel('Acme United (APAC) Pte.Ltd.'), true);
  for (const name of ['AAR Airlift S.A.S.', 'AAR Airlift Group Peru S.A.C.', 'Example S.A. de C.V.', '㈜테스트'])
    assert.equal(usSubsidiaryLabel(name), true, name);
  for (const name of ['Cimpress España, S.L.', 'Cimpress Technology Czech Republic s.r.o.',
    'Exaprint SAS', 'FL Print SAS', 'FM Impressos Personalizados Ltda', 'La Mougère SAS',
    'National Pen Czech s.r.o.', 'Pixartprinting S.p.A.']) assert.equal(usSubsidiaryLabel(name), true, name);
  for (const name of ['HELP Partners', 'BVL Agency', 'Alpha Sarlight', 'No legal form']) assert.equal(usSubsidiaryLabel(name), false, name);
});

test('personal holders and investment funds remain excluded; a generic trust is not a business-form proof', () => {
  const excluded = ['John Smith', 'Smith Trust', 'Family Property Trust', 'Alice Personal Realty Trust',
    'Alice Irrevocable Property Trust', 'Estate Business Trust', 'Example Fund LP',
    'Individual LLC', '개인 Property Trust', '투자조합 B.V.', '펀드 S.a.r.l.'];
  excluded.forEach(name => assert.equal(usSubsidiaryLabel(name), false, name));
  const safe = sanitizeUsSources(fixture([...names, ...excluded]));
  assert.deepEqual(safe.issuers['0000001234'].exhibit.rows.map(r => r.name), names);
  assert.equal(project(safe).relations.length, names.length);
});

test('broader legal forms never bypass SEC original binding, review holds or ownership qualifiers', () => {
  const held = fixture(); held.issuers['0000001234'].exhibit.status = 'needs-review';
  held.issuers['0000001234'].attemptStatus = 'needs-review';
  assert.equal(project(sanitizeUsSources(held)).relations.length, 0);
  for (const field of ['url', 'cik']) {
    const wrong = fixture(); wrong.issuers['0000001234'].exhibit[field] = field === 'url'
      ? 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000002/ex21.htm' : '0000009999';
    assert.throws(() => sanitizeUsSources(wrong));
    assert.throws(() => project(wrong));
  }
  for (const [key, value] of [['ownershipPct', 50], ['directOwnership', 'direct']]) {
    const wrong = fixture(); wrong.issuers['0000001234'].exhibit.rows[0][key] = value;
    assert.throws(() => sanitizeUsSources(wrong));
    assert.equal(project(wrong).relations.length, names.length - 1);
  }
});

test('US business-trust acceptance does not weaken the KR public shareholder boundary', () => {
  const p = project(sanitizeUsSources(fixture(['The Retail Property Trust'])));
  delete p.coverage.cik;
  assert.throws(() => validatePayload(p));
});

test('already visible entities retain IDs, dates, labels and edge order when another legal form becomes visible', () => {
  const old = project(sanitizeUsSources(fixture(['Visible Company, Inc.', 'SmartBank'])));
  const updated = project(sanitizeUsSources(fixture(['Visible Company, Inc.', 'SmartBank', ...names])));
  assert.deepEqual(updated.relations.slice(0, old.relations.length), old.relations);
  assert.deepEqual(updated.companies.slice(0, old.companies.length), old.companies);
});

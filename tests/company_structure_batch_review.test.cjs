const test = require('node:test');
const assert = require('node:assert/strict');
const {sanitizeUsSources} = require('../scripts/member-map/publish-company-structure.cjs');

test('public review keeps machine reason and original dates, not raw cache or text', () => {
  const cik = '0000001234';
  const source = {
    tickerAliases: ['ABC'], attemptStatus: 'needs-review', attemptedAt: '2026-10-22T19:40:00Z',
    rawCachePath: '/private/not-public',
    reviewExhibit: {
      schema: 'sec-company-subsidiaries-v1', cik, accession: '0000001234-26-000001',
      filedDate: '2026-04-22', periodEnd: '2026-02-28', statedAsOf: '2026-03-01',
      url: 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/ex21.htm',
      documentSha256: 'a'.repeat(64), status: 'needs-review',
      reviewReason: 'exhibit-as-of-differs-from-period-end',
      parserRevision: 'test-parser', rows: [{sourceRow: {text: 'DO_NOT_PUBLISH'}}],
    },
  };
  const doc = {schema: 'alphanest-company-structure-us-sources-v1',
    generatedAt: '2026-10-22T19:40:00Z', issuers: {[cik]: source}};
  const safe = sanitizeUsSources(doc);
  assert.equal(safe.issuers[cik].reviewExhibit.reviewReason, source.reviewExhibit.reviewReason);
  assert.equal(safe.issuers[cik].reviewExhibit.statedAsOf, '2026-03-01');
  assert.equal(safe.issuers[cik].reviewExhibit.periodEnd, '2026-02-28');
  assert.equal(safe.issuers[cik].attemptedAt, source.attemptedAt);
  assert.doesNotMatch(JSON.stringify(safe), /private|DO_NOT_PUBLISH|rawCachePath/);
  source.reviewExhibit.reviewReason = '<html>raw content</html>';
  assert.equal(sanitizeUsSources(doc).issuers[cik].reviewExhibit.reviewReason, undefined);
});

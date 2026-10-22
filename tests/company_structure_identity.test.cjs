'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { buildArtifacts, mappedCik } = require('../scripts/member-map/build-live-company-structure.cjs');

test('share-class dot/hyphen aliases reuse existing SEC identifiers without merging classes or accepting conflicts', () => {
  assert.equal(mappedCik('AKO.A', { 'AKO-A': '0000925261' }), '0000925261');
  assert.equal(mappedCik('AKO-B', { 'AKO.B': { cik_str: 925261 } }), '0000925261');
  assert.equal(mappedCik('AKO.A', { 'AKO.A': 925261, 'AKO-A': '0000925261' }), '0000925261');
  for (const mapping of [{ AKO: 925261 }, { 'AKO-B': 925261 },
    { 'AKO.A': 925261, 'AKO-A': 9999 }, { 'AKO.A': 0, 'AKO-A': 925261 }]) {
    assert.equal(mappedCik('AKO.A', mapping), null);
  }
  assert.equal(mappedCik('ABC.A.B', { 'ABC-A-B': 1234 }), null);
  assert.equal(mappedCik('ABC.PRA', { 'ABC-PRA': 1234 }), null);
});

test('share classes retain separate node IDs and original ticker strings, while only the CIK collection is deduplicated', () => {
  const input = { universe: { stocks: ['AKO.A', 'AKO.B'].map(ticker => ({ ticker, market: 'US', name: ticker })) },
    cikMap: { 'AKO-A': 925261, 'AKO-B': 925261 }, generatedAt: '2026-10-22T00:00:00Z' };
  const before = JSON.stringify(input), { manifest, payloads } = buildArtifacts(input);
  assert.deepEqual(Object.keys(manifest.issuers), ['US:AKO.A', 'US:AKO.B']);
  assert.equal(manifest.coverage.US.uniqueCiks, 1);
  assert.equal(manifest.coverage.US.withCik, 2);
  assert.equal(manifest.coverage.US.checked, 0); // Identity alone never proves a relationship.
  assert.equal(payloads.size, 0);
  assert.equal(JSON.stringify(input), before);
});

test('existing universe recovers four exact punctuation gaps without adding a source success or rewriting the map', () => {
  const universe = require('../data/universe_search.json'), cikMap = require('../data/sec_ticker_cik_map.json');
  for (const [ticker, expected] of [['AKO.A', '0000925261'], ['AKO.B', '0000925261'],
    ['CIG.C', '0001157557'], ['PBR.A', '0001119639']]) {
    assert.ok(universe.stocks.some(s => s.market === 'US' && s.ticker === ticker));
    assert.equal(mappedCik(ticker, cikMap), expected);
  }
});

test('reviewed ticker changes require independent current identity and never rename nodes or prove relationships', () => {
  const reviewedAliases = require('../data/member_map_company_structure_aliases.json');
  const generatedAt = '2026-10-23T00:00:00Z';
  const tickers = ['SATS', 'ECHO', 'FDP', 'DMC'];
  const cikMap = { ECHO: 1415404, DMC: 1047340 };
  const input = { reviewedAliases, generatedAt, cikMap,
    universe: { stocks: tickers.map(ticker => ({ ticker, market: 'US', name: ticker })) } };
  const before = JSON.stringify(input), { manifest, payloads } = buildArtifacts(input);
  assert.deepEqual(Object.keys(manifest.issuers), ['US:DMC', 'US:ECHO', 'US:FDP', 'US:SATS']);
  assert.equal(manifest.coverage.US.withCik, 4);
  assert.equal(manifest.coverage.US.uniqueCiks, 2);
  assert.equal(manifest.coverage.US.checked, 0);
  assert.equal(payloads.size, 0);
  assert.equal(JSON.stringify(input), before);
  const resolve = (map, aliases = reviewedAliases, current = new Set(tickers), asOf = generatedAt) => mappedCik('SATS', map, aliases, current, asOf);
  const excluded = buildArtifacts({ ...input, universe: { stocks: [{ ticker: 'SATS', market: 'US' }, { ticker: 'ECHO', market: 'US', type: 'ETF' }] } });
  assert.equal(excluded.manifest.coverage.US.withoutCik, 1);
  assert.throws(() => buildArtifacts({ ...input, reviewedAliases: { schema: 'wrong' } }), /alias schema/);
  assert.equal(resolve({ ...cikMap, SATS: 999 }), '0000000999');
  assert.equal(resolve({ ...cikMap, SATS: 0 }), null);
  assert.equal(resolve({ ECHO: 999 }), null);
  assert.equal(resolve({}), null);
  assert.equal(resolve(cikMap, reviewedAliases, new Set(['SATS'])), null);
  assert.equal(resolve(cikMap, reviewedAliases, new Set(tickers), '2026-06-01T00:00:00Z'), null);
  for (const patch of [{ kind: 'merger' }, { currentTicker: 'SATS' }, { sources: [] },
    { effectiveDate: '2026-02-30' }, { reviewedAt: '2027-01-01T00:00:00Z' }]) {
    const changed = structuredClone(reviewedAliases);
    Object.assign(changed.aliases.SATS, patch);
    assert.equal(resolve(cikMap, changed), null);
  }
});

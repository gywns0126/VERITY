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

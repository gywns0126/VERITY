const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const {
  CAPTURE_FIELDS,
  buildPublicCatalog,
  mergePriorCaptures,
} = require('../scripts/member-map/build-public-source-filter.cjs');

const metadata = {
  universe: { bytes: 11, sha256: 'a'.repeat(64) },
  chainSnippets: { bytes: 12, sha256: 'b'.repeat(64) },
  groupStructure: { bytes: 13, sha256: 'c'.repeat(64) },
};
const universe = {
  _meta: { count: 3, generated_at: '2026-10-05T00:00:00Z' },
  stocks: [
    { ticker: '900001', market: 'KR', name: '합성 발행사 알파' },
    { ticker: '900002', market: 'KR', name: '합성 주주 베타' },
    { ticker: '900003', market: 'KR', name: '합성 주주 감마' },
  ],
};
const provenance = {
  rcept_no: '20241015000001', stlm_dt: '2024-12-31', bsns_year: '2024',
  reprt_code: '11011', corp_code: '00000001', endpoint: 'hyslrSttus',
};
const sourceRow = {
  index: 0,
  fields: {
    rcept_no: provenance.rcept_no, corp_code: provenance.corp_code,
    corp_name: '합성 발행사 알파', stlm_dt: provenance.stlm_dt,
    nm: '합성 주주 베타', relate: '합성 주요주주 관계', stock_knd: '보통주',
    trmend_posesn_stock_qota_rt: '12.5',
  },
};

function catalog({ structured, pct = 12.5, role = '합성 주요주주 관계', target = '900002', family = 'major_shareholders', missingIssuer = false, emptyRelations = false, identities = universe, generatedAt }) {
  const rowProvenance = {
    ...provenance,
    ...(family === 'subsidiaries' ? { endpoint: 'otrCprInvstmntSttus' } : {}),
  };
  const rowSource = family === 'subsidiaries'
    ? {
      index: 0,
      fields: {
        rcept_no: provenance.rcept_no, corp_code: provenance.corp_code,
        corp_name: '합성 발행사 알파', stlm_dt: provenance.stlm_dt,
        inv_prm: '합성 주주 베타', trmend_blce_qota_rt: '12.5',
      },
    }
    : sourceRow;
  const row = {
    symbol: target,
    relate: role,
    ownership_pct: pct,
    ...(structured ? { provenance: rowProvenance, sourceRow: rowSource } : {}),
  };
  return buildPublicCatalog({
    generatedAt,
    universe: identities,
    chainSnippets: { updated_at: '2026-10-05T00:00:00Z', documents: [] },
    groupStructure: {
      updated_at: '2026-10-05T00:00:00Z', count: missingIssuer ? 0 : 1,
      structures: missingIssuer ? {} : {
        '900001': {
          ticker: '900001', collected_at: '2024-10-15T02:30:00Z',
          major_shareholders: !emptyRelations && family === 'major_shareholders' ? [row] : [],
          subsidiaries: !emptyRelations && family === 'subsidiaries' ? [row] : [],
        },
      },
    },
    inputMetadata: metadata,
  });
}

function withEmptyCaptures(prior) {
  for (const field of CAPTURE_FIELDS) prior[field] = [];
  return prior;
}

test('public rebuild restores only exact retained structured provenance and keeps catalog invariants', () => {
  const prior = withEmptyCaptures(catalog({
    structured: true, generatedAt: '2025-01-01T00:00:00Z',
  }));
  const current = catalog({
    structured: false, generatedAt: '2026-10-05T01:00:00Z',
  });
  const originalCurrentRelationCount = Object.keys(current.relations).length;
  const originalCurrentDenominators = structuredClone(current.denominators);
  const originalCurrentGeneratedAt = current.generatedAt;

  const restored = mergePriorCaptures(current, prior);
  const restoredRelations = Object.values(restored.relations);
  assert.equal(restored.generatedAt, originalCurrentGeneratedAt);
  assert.deepEqual(restored.denominators, originalCurrentDenominators);
  assert.equal(restoredRelations.length, originalCurrentRelationCount);
  assert.equal(restoredRelations.length, 1, 'provenance restoration must not add a relation fact');
  const relation = restoredRelations[0];
  assert.equal(relation.verification, 'candidate-source-row-receipt');
  assert.equal(relation.role, '합성 주요주주 관계');
  assert.equal(relation.reportedOwnershipPct, 12.5);
  assert.equal(relation.sourceDate, null);
  assert.equal(relation.artifactObservedAt, '2024-10-15T02:30:00Z');
  assert.deepEqual(relation.sourceRow, sourceRow);
  const source = restored.sources[relation.sourceId];
  assert.equal(source.receiptNo, provenance.rcept_no);
  assert.equal(source.sourceDate, null);
  assert.equal(source.settlementDate, '2024-12-31');
  assert.equal(source.artifactObservedAt, '2024-10-15T02:30:00Z');
  for (const ticker of [relation.from, relation.to]) {
    assert.ok(restored.tickerIndex[ticker].sourceCandidates.includes(relation.sourceId));
    assert.ok(restored.tickerIndex[ticker].relationCandidates.includes(relation.id));
  }
  assert.equal(Object.keys(restored.tickerIndex).length, restored.denominators.issuersIndexed);
  for (const field of CAPTURE_FIELDS) assert.deepEqual(restored[field], []);

  for (const mismatch of [
    { pct: 12.6 },
    { role: '다른 합성 역할' },
    { target: '900003' },
    { family: 'subsidiaries' },
  ]) {
    const mismatchedPrior = withEmptyCaptures(catalog({
      structured: true, generatedAt: '2025-01-01T00:00:00Z', ...mismatch,
    }));
    assert.throws(
      () => mergePriorCaptures(current, mismatchedPrior),
      /structured source family downgrade/,
      `must not restore semantic mismatch: ${JSON.stringify(mismatch)}`,
    );
  }

  const conflictingBase = structuredClone(current);
  const priorRelation = Object.values(prior.relations)[0];
  for (const [field, value] of [['rcept_no', '20241015000002'], ['corp_code', '00000002'], ['stlm_dt', '2023-12-31']]) {
    const mismatchedEvidence = structuredClone(prior);
    mismatchedEvidence.relations[priorRelation.id].sourceRow.fields[field] = value;
    assert.throws(() => mergePriorCaptures(current, mismatchedEvidence), /structured provenance binding/);
  }
  const wrongIssuer = structuredClone(prior);
  wrongIssuer.sources[priorRelation.sourceId].documentIssuer = 'KR:900003';
  assert.throws(() => mergePriorCaptures(current, wrongIssuer), /structured provenance binding/);
  conflictingBase.sources[priorRelation.sourceId] = { id: priorRelation.sourceId, kind: 'conflicting' };
  assert.throws(() => mergePriorCaptures(conflictingBase, prior), /structured provenance collision/);

  const ambiguousPrior = structuredClone(prior);
  const relationCopy = structuredClone(priorRelation);
  relationCopy.id = `${relationCopy.id}:duplicate`;
  relationCopy.sourceId = `${relationCopy.sourceId}:duplicate`;
  const sourceCopy = structuredClone(prior.sources[priorRelation.sourceId]);
  sourceCopy.id = relationCopy.sourceId;
  ambiguousPrior.sources[relationCopy.sourceId] = sourceCopy;
  ambiguousPrior.relations[relationCopy.id] = relationCopy;
  for (const ticker of [relationCopy.from, relationCopy.to]) {
    ambiguousPrior.tickerIndex[ticker].sourceCandidates.push(relationCopy.sourceId);
    ambiguousPrior.tickerIndex[ticker].relationCandidates.push(relationCopy.id);
  }
  assert.throws(() => mergePriorCaptures(current, ambiguousPrior), /ambiguous structured provenance/);
});

test('a missing issuer snapshot retains literal receipt-bound rows as historical, not freshly collected relations', () => {
  for (const family of ['major_shareholders', 'subsidiaries']) {
    const prior = withEmptyCaptures(catalog({ structured: true, family, generatedAt: '2025-01-01T00:00:00Z' }));
    const current = catalog({ structured: false, missingIssuer: true, generatedAt: '2026-11-01T00:00:00Z' });
    const beforeCurrent = structuredClone(current), beforePrior = structuredClone(prior);
    const retained = mergePriorCaptures(current, prior);
    assert.deepEqual(current, beforeCurrent); assert.deepEqual(prior, beforePrior);
    assert.deepEqual(retained.relations, prior.relations);
    assert.deepEqual(retained.sources, Object.fromEntries(Object.entries(prior.sources)
      .filter(([, source]) => source.kind === 'dart-structured-relation')));
    assert.equal(retained.generatedAt, current.generatedAt);
    assert.deepEqual(retained.inputs, current.inputs);
    assert.deepEqual(retained.artifactTimestamps, current.artifactTimestamps);
    assert.deepEqual(retained.sourceDateCoverage, current.sourceDateCoverage);
    assert.equal(retained.scope.runtimeFreshness, 'not-automatically-reverified');
    assert.equal(retained.denominators.relationsInput, 1);
    assert.equal(retained.denominators.relationsAccepted, 1);
    assert.equal(retained.denominators.relationsRejected, 0);
    for (const relation of Object.values(prior.relations)) {
      assert.equal(retained.sources[relation.sourceId].receiptNo, provenance.rcept_no);
      assert.equal(retained.sources[relation.sourceId].sourceDate, null);
      assert.equal(retained.sources[relation.sourceId].settlementDate, provenance.stlm_dt);
      assert.equal(retained.relations[relation.id].artifactObservedAt, '2024-10-15T02:30:00Z');
      for (const ticker of [relation.from, relation.to]) {
        assert.ok(retained.tickerIndex[ticker].sourceCandidates.includes(relation.sourceId));
        assert.ok(retained.tickerIndex[ticker].relationCandidates.includes(relation.id));
      }
    }
    for (const field of CAPTURE_FIELDS) assert.deepEqual(retained[field], prior[field]);
    assert.deepEqual(mergePriorCaptures(current, retained), retained, 'rebuilding must not duplicate historical rows');
    const projected = spawnSync('python3', ['-B', '-c', [
      'import json,sys',
      'from api.intelligence.portfolio_evidence import project_portfolio_evidence',
      'result=project_portfolio_evidence(json.load(sys.stdin),[{"ticker":"900001","market":"KR"}])',
      'print(json.dumps(result["relationships"]))',
    ].join('\n')], { cwd: path.resolve(__dirname, '..'), input: JSON.stringify(retained), encoding: 'utf8', timeout: 15000 });
    assert.equal(projected.status, 0, projected.stderr);
    const relationships = JSON.parse(projected.stdout);
    assert.equal(relationships.length, 1);
    assert.equal(relationships[0].status, 'accepted_reported');
    assert.equal(relationships[0].snapshot_scope, 'reported-at-settlement-not-current');
    assert.equal(relationships[0].source.as_of, null);
    assert.equal(relationships[0].source.artifact_observed_at, '2024-10-15T02:30:00Z');
    assert.equal(relationships[0].source.settlement_date, provenance.stlm_dt);
    assert.deepEqual(relationships[0].evidence.source_row, Object.values(prior.relations)[0].sourceRow);
  }
});

test('an explicitly empty or wholly rejected current issuer keeps its source marker and cannot restore prior relations', () => {
  const prior = withEmptyCaptures(catalog({ structured: true, generatedAt: '2025-01-01T00:00:00Z' }));
  for (const options of [{ emptyRelations: true }, { target: '999999' }]) {
    const current = catalog({ structured: false, generatedAt: '2026-11-01T00:00:00Z', ...options });
    assert.equal(Object.keys(current.relations).length, 0);
    assert.ok(Object.values(current.sources).some(source => source.documentIssuer === 'KR:900001'
      && source.kind === 'local-structured-relation-candidate'), 'known raw issuer emits a source even without accepted relations');
    assert.equal(current.denominators.relationsAccepted, 0);
    assert.equal(current.denominators.relationsRejected, options.emptyRelations ? 0 : 1);
    const before = structuredClone(current);
    assert.throws(() => mergePriorCaptures(current, prior), /structured source family downgrade/);
    assert.deepEqual(current, before);
  }
});

test('a raw issuer may emit no source when unresolved, but the missing current identity still blocks historical retention', () => {
  const prior = withEmptyCaptures(catalog({ structured: true, generatedAt: '2025-01-01T00:00:00Z' }));
  const identities = { ...universe, _meta: { ...universe._meta, count: 2 },
    stocks: universe.stocks.filter(row => row.ticker !== '900001') };
  // The fixture still contains the raw 900001 issuer with explicit empty arrays.
  const current = catalog({ structured: false, emptyRelations: true, identities, generatedAt: '2026-11-01T00:00:00Z' });
  assert.equal(Object.keys(current.sources).length, 0);
  assert.equal(Object.keys(current.relations).length, 0);
  assert.equal(current.tickerIndex['KR:900001'], undefined);
  assert.throws(() => mergePriorCaptures(current, prior), /structured provenance binding/);
});

test('historical retention fails closed on identity, source/index binding and identifier collisions', () => {
  const prior = withEmptyCaptures(catalog({ structured: true, generatedAt: '2025-01-01T00:00:00Z' }));
  const current = catalog({ structured: false, missingIssuer: true, generatedAt: '2026-11-01T00:00:00Z' });
  const relation = Object.values(prior.relations)[0];
  const renamed = structuredClone(current); renamed.tickerIndex[relation.from].issuer.name = '다른 합성 주주';
  assert.throws(() => mergePriorCaptures(renamed, prior), /structured provenance binding/);
  const missing = structuredClone(prior); missing.tickerIndex[relation.from].relationCandidates = [];
  assert.throws(() => mergePriorCaptures(current, missing), /structured provenance binding/);
  for (const [field, value] of [['rcept_no', '20241015000002'], ['corp_code', '00000002'], ['stlm_dt', '2023-12-31']]) {
    const changed = structuredClone(prior); changed.relations[relation.id].sourceRow.fields[field] = value;
    assert.throws(() => mergePriorCaptures(current, changed), /structured provenance binding/);
  }
  const collision = structuredClone(current); collision.sources[relation.sourceId] = { id: relation.sourceId, kind: 'conflicting' };
  assert.throws(() => mergePriorCaptures(collision, prior), /structured provenance collision/);
});

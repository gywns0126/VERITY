const test = require('node:test');
const assert = require('node:assert/strict');
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

function catalog({ structured, pct = 12.5, role = '합성 주요주주 관계', target = '900002', family = 'major_shareholders', generatedAt }) {
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
    universe,
    chainSnippets: { updated_at: '2026-10-05T00:00:00Z', documents: [] },
    groupStructure: {
      updated_at: '2026-10-05T00:00:00Z', count: 1,
      structures: {
        '900001': {
          ticker: '900001', collected_at: '2024-10-15T02:30:00Z',
          major_shareholders: family === 'major_shareholders' ? [row] : [],
          subsidiaries: family === 'subsidiaries' ? [row] : [],
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

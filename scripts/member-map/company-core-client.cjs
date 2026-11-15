// Candidate transport/compatibility helper; the operating UI does not import it.
// Inject existing analysisToGraph/fetchPortfolioAnalysisGraph adapters at build time.
const ANALYSIS = 'https://project-yw131.vercel.app/api/member_map_analysis';
const CORE = 'https://project-yw131.vercel.app/api/member_map_company_snapshot';
const HASH = /^[a-f0-9]{64}$/;
const CLAIM = /^[fdp]:[a-f0-9]{64}$/;
function claimsOf(payload, positions, requireSnapshot = false) {
    const meta = payload?._meta, claims = meta?.core_claims;
    const expected = positions.map(p => p.market + ':' + p.ticker).sort();
    if (!claims || claims.status !== 'ready' || !claims.companies ||
        JSON.stringify(Object.keys(claims.companies).sort()) !== JSON.stringify(expected)) throw Error('core-claims-unavailable');
    let count = 0;
    for (const id of expected) {
        const rows = claims.companies[id];
        if (!Array.isArray(rows) || rows.some(value => typeof value !== 'string' || !CLAIM.test(value)) ||
            new Set(rows).size !== rows.length || (count += rows.length) > 4096) throw Error('core-claims-rejected');
    }
    if (requireSnapshot && (meta.snapshot_scope !== 'core-facts-disclosures' ||
        typeof meta.snapshot_release !== 'string' || !HASH.test(meta.snapshot_release))) throw Error('core-scope-rejected');
    return JSON.parse(JSON.stringify(claims));
}
function coreIncluded(initial, final) {
    if (!initial || !final || initial.status !== 'ready' || final.status !== 'ready') return false;
    return Object.entries(initial.companies).every(([id, claims]) => {
        const available = new Set(final.companies[id] || []);
        return claims.every(value => available.has(value));
    });
}
async function captureAnalysis(client, positions, options, snapshot = false) {
    let payload;
    const fetcher = options.fetcher || fetch;
    const graph = await client(positions, { ...options, fetcher: async (url, init) => {
        if (url !== ANALYSIS || init?.method !== 'POST') throw Error('core-transport-rejected');
        const response = await fetcher(snapshot ? CORE : ANALYSIS + '?core_claims=1', init);
        return { ok: response.ok, status: response.status, headers: response.headers,
            json: async () => { payload = await response.json(); return payload; } };
    } });
    const claims = claimsOf(payload, positions, snapshot);
    if (snapshot) {
        graph.graphCoreClaims = claims;
        graph.analysisNotice = ['공시·재무 근거 먼저 · 관계·뉴스·판단 연결 중', graph.analysisNotice].filter(Boolean).join(' · ');
        graph.coverage.sources = graph.coverage.sources.map(row => row.sectionId === 'business'
            ? { ...row, state: 'unknown', messages: ['전체 관계·사업 분석을 연결 중이에요.'] } : row);
        for (const key of ['available', 'empty', 'partial', 'unavailable', 'unknown'])
            graph.coverage[key] = graph.coverage.sources.filter(row => row.state === key).length;
    }
    return { graph, claims, release: snapshot ? payload._meta.snapshot_release : null };
}
function compatibleCoreGraph(core, full, merged) {
    if (!coreIncluded(core.claims, full.claims)) return false;
    const ids = new Set(merged.documents.map(row => row.id));
    return core.graph.documents.every(row => ids.has(row.id));
}
module.exports = { ANALYSIS, CORE, claimsOf, coreIncluded, captureAnalysis, compatibleCoreGraph };

// Opt-in startup patch only. Not imported by the operating Framer build.
const { captureAnalysis, compatibleCoreGraph } = require('./company-core-client.cjs');

async function loadCompanyFullGraph({ client, positions, options, legacy, merge }) {
    const [full, source] = await Promise.all([captureAnalysis(client, positions, options), legacy()]);
    return { ...full, graph: await merge(source, full.graph) };
}

async function loadCompanyCoreGraph({ client, positions, options, legacy, merge, preview }) {
    const controller = new AbortController();
    const cancel = () => controller.abort();
    options.signal?.addEventListener('abort', cancel, { once: true });
    if (options.signal?.aborted) cancel();
    const timer = setTimeout(cancel, 3500);
    let core;
    const early = captureAnalysis(client, positions, { ...options, signal: controller.signal }, true)
        .then(value => { if (!controller.signal.aborted) { core = value; preview(value.graph, positions); } })
        .catch(() => { /* Snapshot miss uses the existing full lane; no empty promotion. */ });
    try {
        const full = await loadCompanyFullGraph({ client, positions, options, legacy, merge });
        // A response that already arrived is checked before full replacement.
        // Do not delay a completed full response for an unavailable optimization.
        cancel();
        const graph = full.graph;
        if (core && !compatibleCoreGraph(core, full, graph)) throw Error('company-core-generation-mismatch');
        return graph;
    } finally {
        cancel(); clearTimeout(timer);
        options.signal?.removeEventListener('abort', cancel);
        // `early` owns its rejection even when an injected transport ignores abort.
        void early;
    }
}

function applyCompanyCoreWorkspace(source) {
    const replace = (old, value) => {
        if (source.split(old).length !== 2) throw Error('company-core-workspace-boundary');
        source = source.replace(old, value);
    };
    replace('    if (!account) return Promise.reject(new Error("authentication-required"));\n    return Promise.all([',
`    if (!account) return Promise.reject(new Error("authentication-required"));
    if (onLegacy) return loadCompanyCoreGraph({ client: fetchPortfolioAnalysisGraph, positions,
      options: { getSession, ownerId: account.userId, fetcher, signal }, preview: onLegacy,
      legacy: () => (options.analysisSourceLoader || fetchPortfolioMapGraph)(codes, API, signal),
      merge: mergePortfolioAnalysisGraphs });
    return Promise.all([`);
    replace('      memberMapLoadDiagnostic(timedOut ? "graph-timeout" : "graph-other", error);',
`      if (state.partialGraph && state.graph) {
        state = { ...state, phase: "ready", error: "company-core-full-unavailable",
          dataRefresh: { ...state.dataRefresh, phase: "error", error: "company-core-full-unavailable" } };
        emit(); return false;
      }
      memberMapLoadDiagnostic(timedOut ? "graph-timeout" : "graph-other", error);`);
    // Reuse the existing user-invoked recheck; preserve the mounted core frame
    // and all private state while only its full public enrichment is retried.
    replace('    refreshData,\n    applyDataUpdate()', '    refreshData,\n    retryCompanyCore,\n    applyDataUpdate()');
    replace('  const refreshData = () => {',
`  const retryCompanyCore = async () => {
    if (!account || !valid(generation) || disposed || pending || state.phase !== "ready" || !state.graph || !state.partialGraph) return false;
    const core = state.graph, version = generation, codes = [...state.selectedTickers];
    const controller = new AbortController(); pending = controller;
    const timer = setTimeout(() => controller.abort(), 60000);
    timers.add(timer);
    state = { ...state, dataRefresh: { ...state.dataRefresh, phase: "checking" } }; emit();
    try {
      const stocks = new Map(workspaceStocks(state).map(row => [row.ticker, row]));
      const positions = codes.map(ticker => ({ ticker, market: stocks.get(ticker).market }));
      const full = await loadCompanyFullGraph({ client: fetchPortfolioAnalysisGraph, positions,
        options: { getSession, ownerId: account.userId, fetcher, signal: controller.signal },
        legacy: () => (options.analysisSourceLoader || fetchPortfolioMapGraph)(codes, API, controller.signal),
        merge: mergePortfolioAnalysisGraphs });
      if (!valid(version) || controller.signal.aborted || state.graph !== core || !state.partialGraph) return false;
      if (!compatibleCoreGraph({ graph: core, claims: core.graphCoreClaims }, full, full.graph)) throw Error("company-core-generation-mismatch");
      state = { ...state, graph: full.graph, partialGraph: false, error: null, dataRefresh: { phase: "idle", checkedAt: null, error: null } }; emit(); return true;
    } catch {
      if (valid(version) && state.graph === core && state.partialGraph) { state = { ...state, dataRefresh: { ...state.dataRefresh, phase: "error" } }; emit(); }
      return false;
    } finally {
      clearTimeout(timer); timers.delete(timer); if (pending === controller) pending = null;
    }
  };
  const refreshData = () => {`);
    return source;
}

function applyCompanyCorePresentation(source) {
    const button = '    void controller.current?.refreshData();';
    const phase = 'phase: state.partialGraph ? "initial" : state.dataRefresh?.phase,';
    if (source.split(button).length !== 2 || source.split(phase).length !== 2) throw Error('company-core-presentation-boundary');
    return source.replace(button, '    void (state?.partialGraph ? controller.current?.retryCompanyCore() : controller.current?.refreshData());')
        .replace(phase, 'phase: state.partialGraph ? state.error ? "error" : "initial" : state.dataRefresh?.phase,');
}

module.exports = { loadCompanyFullGraph, loadCompanyCoreGraph, applyCompanyCoreWorkspace, applyCompanyCorePresentation };

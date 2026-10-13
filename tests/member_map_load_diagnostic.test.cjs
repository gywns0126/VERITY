const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const repoRoot = path.resolve(__dirname, '..');
const esbuild = createRequire(path.join(process.env.MEMBER_MAP_TEST_DEPENDENCY_ROOT || repoRoot, 'package.json'))('esbuild');
const source = fs.readFileSync(path.join(process.env.MEMBER_MAP_TEST_SOURCE_ROOT || repoRoot, 'review/member-map/Map.snapshot.tsx'), 'utf8');
const code = esbuild.transformSync(source + '\nexport { memberMapLoadDiagnostic, fetchPortfolioAnalysisGraph, createPortfolioMapWorkspace, fetchMapWatchlist };', { loader: 'tsx', format: 'cjs', target: 'es2022' }).code;
const CANARY = 'private-canary user@example.invalid Bearer synthetic-secret';
const A = { userId: '11111111-1111-4111-8111-111111111111', token: CANARY };
const B = { userId: '22222222-2222-4222-8222-222222222222', token: CANARY + '-B' };
const generic = '분석 자료를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.';
const plain = value => JSON.parse(JSON.stringify(value));
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
function runtime(query = '?mapDiagnostics=1', extra = {}) {
  const logs = [], box = { exports: {} };
  const sandbox = {
    module: box, exports: box.exports, AbortController, URL, URLSearchParams,
    window: { location: { search: query } }, console: { warn: (...args) => {
      assert.equal(args.length, 2);
      assert.equal(typeof args[1], 'string');
      const fields = JSON.parse(args[1]);
      assert.deepEqual(Object.keys(fields).sort(), ['errorCode', 'errorName', 'missingBinding', 'stage', 'status']);
      for (const value of [CANARY, A.userId, B.userId, 'user@example.invalid', 'synthetic-secret', 'positions', 'Authorization', 'stack']) assert.ok(!args[1].includes(value));
      logs.push([args[0], fields]);
    } },
    setTimeout, clearTimeout,
    require: name => {
      if (name === 'react') return {};
      if (name === 'framer') return { addPropertyControls() {}, ControlType: { Number: 'number' }, useIsStaticRenderer: () => false };
      throw Error('unexpected_snapshot_import');
    }, ...extra
  };
  vm.runInNewContext(code, sandbox);
  return { api: box.exports, logs, sandbox };
}
function analysis(h, fetcher, options = {}) {
  return h.api.fetchPortfolioAnalysisGraph([{ ticker: 'EXM', market: 'US' }], {
    getSession: () => A, ownerId: A.userId, fetcher, ...options
  });
}
function safeLog(h, expected) {
  assert.equal(h.logs.length, 1);
  assert.deepEqual(h.logs[0], ['member-map-load-diagnostic', { stage: expected.stage,
    errorName: expected.errorName || 'Error', errorCode: expected.errorCode || 'unknown',
    missingBinding: expected.missingBinding || 'unknown', status: expected.status ?? null }]);
  const text = JSON.stringify(h.logs);
  for (const privateValue of [CANARY, A.userId, B.userId, 'user@example.invalid', 'synthetic-secret', 'positions', 'Authorization', 'stack']) assert.ok(!text.includes(privateValue));
}
function workspaceFixture(query = '?mapDiagnostics=1', extra = {}, watch) {
  let now = 0, serial = 0, session = A, mode = 'ready', failure = new Error(CANARY);
  const timers = new Map(), loads = [];
  const h = runtime(query, {
    setTimeout(fn, ms) { const id = ++serial; timers.set(id, { fn, due: now + ms }); return id; },
    clearTimeout(id) { timers.delete(id); }, ...extra
  });
  const graph = codes => ({ companies: codes.map(ticker => ({ id: 'company:' + ticker, ticker, name: ticker, market: 'US' })), documents: [], links: [], coverage: { sources: [] } });
  const workspace = h.api.createPortfolioMapWorkspace({ getSession: () => session, includeWatchlist: !!watch,
    fetcher: async (url, init) => url.endsWith('/watchgroups') ? watch(url, init) : ({ ok: true, status: 200, json: async () => url.endsWith('/holdings')
      ? [{ ticker: 'EXM', market: 'US', name: '합성' }] : { revision: 0, document: { layouts: [] } } }),
    graphLoader: codes => {
      if (mode === 'ready') return Promise.resolve(graph(codes));
      if (mode === 'error') return Promise.reject(failure);
      return new Promise((resolve, reject) => loads.push({ resolve: () => resolve(graph(codes)), reject }));
    }
  });
  return { ...h, workspace, loads, timers, mode: value => { mode = value; }, failure: value => { failure = value; }, session: value => { session = value; },
    async advance(ms) { now += ms; for (const [id, entry] of [...timers]) if (entry.due <= now) { timers.delete(id); entry.fn(); } await flush(); }
  };
}

for (const query of ['', '?mapDiagnostics=0', '?mapDiagnostics=true', '?mapDiagnostics=11', '?mapDiagnostics=1&mapDiagnostics=1']) {
  test('비활성 쿼리에서는 실제 분석 함수와 화면 함수 모두 진단 없음: ' + query, async () => {
    const h = workspaceFixture(query); await h.workspace.open();
    await assert.rejects(analysis(h, async () => { throw new TypeError(CANARY); }), { message: generic });
    h.mode('error'); assert.equal(await h.workspace.showTickers(['EXM']), false);
    assert.equal(h.logs.length, 0); h.workspace.dispose();
  });
}
test('실제 분석 함수 요청 단계: 원문·토큰·이메일 제외', async () => {
  const h = runtime();
  await assert.rejects(analysis(h, async () => { throw new TypeError(CANARY); }), { message: generic });
  safeLog(h, { stage: 'request', errorName: 'TypeError' });
});
test('실제 분석 함수 HTTP 실패는 상태 숫자와 정확한 고정 코드만 출력', async () => {
  const h = runtime();
  await assert.rejects(analysis(h, async () => ({ ok: false, status: 503, body: CANARY, url: CANARY })), { message: generic });
  safeLog(h, { stage: 'request', errorCode: 'unavailable', status: 503 });
});
test('실제 분석 함수 JSON 단계 실패와 원문 비노출', async () => {
  const h = runtime();
  await assert.rejects(analysis(h, async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError(CANARY); } })), { message: generic });
  safeLog(h, { stage: 'json', errorName: 'SyntaxError', status: 200 });
});
test('실제 분석 어댑터 형식 거부 단계', async () => {
  const h = runtime();
  await assert.rejects(analysis(h, async () => ({ ok: true, status: 200, json: async () => ({ private: CANARY }) })), { message: generic });
  safeLog(h, { stage: 'adapter', errorCode: 'analysis-format', status: 200 });
});
test('분석 계정 변경 검사는 진단보다 먼저 실행', async () => {
  const h = runtime(); let current = A;
  await assert.rejects(analysis(h, async () => { current = B; throw new Error(CANARY); }, { getSession: () => current }), { message: '로그인 계정이 변경되었어요.' });
  assert.equal(h.logs.length, 0);
});
test('분석 취소 검사는 진단보다 먼저 실행', async () => {
  const h = runtime(), controller = new AbortController();
  await assert.rejects(analysis(h, async () => { controller.abort(); throw new Error(CANARY); }, { signal: controller.signal }));
  assert.equal(h.logs.length, 0);
});
test('진단 함수 실패는 기존 분석 오류를 바꾸지 않음', async () => {
  const h = runtime('?mapDiagnostics=1', { console: { warn() { throw new Error(CANARY); } } });
  await assert.rejects(analysis(h, async () => { throw new Error(CANARY); }), { message: generic });
});
test('알 수 없는 오류명·메시지·상태 및 코드 접두사 차단', () => {
  for (const message of [CANARY, 'portfolio-document-identity-conflict ' + CANARY, 'unavailable:' + CANARY]) {
    const h = runtime(); h.api.memberMapLoadDiagnostic('adapter', { name: CANARY, message, stack: CANARY, token: CANARY }, { status: CANARY });
    safeLog(h, { stage: 'adapter', errorName: 'unknown' });
  }
});
test('허용 오류명 7개만 그대로 출력', () => {
  for (const name of ['Error', 'TypeError', 'ReferenceError', 'SyntaxError', 'RangeError', 'AbortError', 'TimeoutError']) {
    const h = runtime(); h.api.memberMapLoadDiagnostic('request', { name, message: CANARY });
    safeLog(h, { stage: 'request', errorName: name });
  }
});
test('공개 바인딩 16개만 정확한 ReferenceError 문구에서 식별', () => {
  const bindings = ['crypto', 'TextEncoder', 'buildPortfolioMapGraph', 'portfolioDocumentIdentity', 'parseAutomaticEvidence', 'parseAnalysisPrices', 'parseMarketContext', 'parseDocumentLineage', 'parseContractFacts', 'parseContractEvents', 'parseContractTermination', 'attachPublicAIReview', 'quotedContractDay', 'quotedContractFinancialLines', 'memberMapBoundBusinessJudgments', 'mergePortfolioAnalysisGraphs'];
  for (const binding of bindings) for (const message of [binding + ' is not defined', "Can't find variable: " + binding]) {
    const h = runtime(); h.api.memberMapLoadDiagnostic('adapter', new ReferenceError(message));
    safeLog(h, { stage: 'adapter', errorName: 'ReferenceError', missingBinding: binding });
  }
  for (const message of [CANARY + ' is not defined', 'crypto is not defined ' + CANARY, "Can't find variable: crypto " + CANARY]) {
    const h = runtime(); h.api.memberMapLoadDiagnostic('adapter', new ReferenceError(message));
    safeLog(h, { stage: 'adapter', errorName: 'ReferenceError' });
  }
});
test('getter·console·브라우저 전역 장애는 외부로 전파되지 않음', () => {
  const h = runtime();
  assert.doesNotThrow(() => h.api.memberMapLoadDiagnostic('request', { get message() { throw new Error(CANARY); } }));
  assert.doesNotThrow(() => h.api.memberMapLoadDiagnostic('request', new Error(), { get status() { throw new Error(CANARY); } }));
  const absent = runtime('', { window: undefined });
  assert.doesNotThrow(() => absent.api.memberMapLoadDiagnostic('request', new Error(CANARY)));
  assert.equal(h.logs.length + absent.logs.length, 0);
});
test('실제 화면 함수에서 동일 그래프 시간초과 진단과 기존 오류 유지', async () => {
  const h = workspaceFixture(); await h.workspace.open(); h.mode('pending');
  const pending = h.workspace.showTickers(['EXM']); await flush(); await h.advance(60000);
  assert.equal(await pending, false); assert.equal(h.workspace.getState().error, 'graph-load-timeout');
  safeLog(h, { stage: 'graph-timeout', errorCode: 'graph-load-timeout' });
  h.loads[0].resolve(); await flush(); assert.equal(h.logs.length, 1); h.workspace.dispose();
});
test('실제 화면 함수 기타 오류는 고정 코드만 출력', async () => {
  const h = workspaceFixture(); await h.workspace.open(); h.mode('error'); h.failure(new Error('portfolio-document-identity-conflict'));
  assert.equal(await h.workspace.showTickers(['EXM']), false);
  safeLog(h, { stage: 'graph-other', errorCode: 'portfolio-document-identity-conflict' }); h.workspace.dispose();
});
test('실제 화면 함수의 비공개 원문은 진단에 포함되지 않음', async () => {
  const h = workspaceFixture(); await h.workspace.open(); h.mode('error');
  assert.equal(await h.workspace.showTickers(['EXM']), false);
  safeLog(h, { stage: 'graph-other' }); h.workspace.dispose();
});
test('화면 계정 변경·취소는 진단 없이 무시', async () => {
  const h = workspaceFixture(); await h.workspace.open(); h.mode('pending');
  const pending = h.workspace.showTickers(['EXM']); await flush(); h.session(B); h.workspace.getState();
  assert.equal(await pending, false); h.loads[0].reject(new Error(CANARY)); await flush();
  assert.equal(h.logs.length, 0); h.workspace.dispose();
});
test('화면의 진단 출력 실패도 원래 상태 전이를 유지', async () => {
  const h = workspaceFixture('?mapDiagnostics=1', { console: { warn() { throw new Error(CANARY); } } });
  await h.workspace.open(); h.mode('error');
  assert.equal(await h.workspace.showTickers(['EXM']), false);
  assert.equal(h.workspace.getState().phase, 'error'); h.workspace.dispose();
});

test('관심목록 5초 경계: current 재검사 예외도 고정 코드 관측, 늦은 결과 무시', async () => {
  let finish, signal;
  const h = workspaceFixture('?mapDiagnostics=1', {}, (_url, init) => {
    signal = init.signal;
    return new Promise(resolve => { finish = resolve; });
  });
  const pending = h.workspace.open(); await flush(); await h.advance(4999);
  assert.equal(signal.aborted, false); assert.equal(h.logs.length, 0);
  await h.advance(1); assert.equal(await pending, true);
  assert.equal(signal.aborted, true);
  assert.equal(h.workspace.getState().watchlistError, 'watchlist-aborted');
  assert.equal(h.workspace.getState().holdings.length, 1);
  safeLog(h, { stage: 'watch-load', errorName: 'AbortError', errorCode: 'watchlist-aborted' });
  const before = plain(h.workspace.getState());
  finish({ ok: true, status: 200, json: async () => [] }); await flush();
  assert.deepEqual(plain(h.workspace.getState()), before); assert.equal(h.logs.length, 1);
  h.workspace.dispose();
});
test('관심목록 HTTP 오류는 고정 코드와 상태만 관측', async () => {
  for (const status of [401, 503]) {
    let requests = 0;
    const h = workspaceFixture('?mapDiagnostics=1', {}, async () => {
      requests++; return { ok: false, status, body: CANARY, url: CANARY };
    });
    assert.equal(await h.workspace.open(), true);
    const errorCode = status === 401 ? 'authentication-required' : 'watchlist-unavailable';
    assert.equal(h.workspace.getState().watchlistError, errorCode); assert.equal(requests, 1);
    safeLog(h, { stage: 'watch-load', errorCode, status }); h.workspace.dispose();
  }
});
test('관심목록 JSON 및 형식 오류도 본문 없이 관측', async () => {
  for (const syntax of [false, true]) {
    const h = workspaceFixture('?mapDiagnostics=1', {}, async () => ({ ok: true, status: 200,
      json: async () => { if (syntax) throw new SyntaxError(CANARY); return { private: CANARY }; }
    }));
    assert.equal(await h.workspace.open(), true);
    safeLog(h, { stage: 'watch-load', status: 200, errorName: syntax ? 'SyntaxError' : 'Error',
      errorCode: syntax ? 'unknown' : 'invalid-watchlist-response' }); h.workspace.dispose();
  }
});
test('관심목록 코드 접두사 및 미허용 오류명은 개인정보 없이 unknown', async () => {
  for (const message of [CANARY, 'watchlist-unavailable ' + CANARY, 'watchlist-aborted:' + CANARY]) {
    const h = workspaceFixture('?mapDiagnostics=1', {}, async () => { throw { name: CANARY, message, stack: CANARY }; });
    assert.equal(await h.workspace.open(), true);
    safeLog(h, { stage: 'watch-load', errorName: 'unknown' }); h.workspace.dispose();
  }
});
test('관심목록 비활성 진단에서는 오류와 5초 취소 모두 로그 없음', async () => {
  for (const query of ['', '?mapDiagnostics=0', '?mapDiagnostics=1&mapDiagnostics=1']) {
    const h = workspaceFixture(query, {}, () => new Promise(() => {}));
    const pending = h.workspace.open(); await flush(); await h.advance(5000);
    assert.equal(await pending, true); assert.equal(h.logs.length, 0);
    assert.equal(h.workspace.getState().watchlistError, 'watchlist-aborted'); h.workspace.dispose();
  }
});
test('관심목록 계정 전환 및 상위 취소는 진단 없음', async () => {
  for (const dispose of [false, true]) {
    const h = workspaceFixture('?mapDiagnostics=1', {}, () => new Promise(() => {}));
    const pending = h.workspace.open(); await flush();
    if (dispose) h.workspace.dispose(); else { h.session(B); h.workspace.getState(); }
    await flush(); assert.equal(await pending, false); assert.equal(h.logs.length, 0); h.workspace.dispose();
  }
});
test('관심목록 401은 동일 계정의 바뀐 토큰에만 한 번 재시도', async () => {
  let requests = 0;
  const h = workspaceFixture('?mapDiagnostics=1', {}, async () => {
    requests++;
    if (requests === 1) { h.session({ ...A, token: CANARY + '-new' }); return { ok: false, status: 401 }; }
    return { ok: true, status: 200, json: async () => [] };
  });
  assert.equal(await h.workspace.open(), true); assert.equal(requests, 2);
  assert.equal(h.workspace.getState().watchlistError, null); assert.equal(h.logs.length, 0); h.workspace.dispose();
});
test('관심목록 비지원 항목은 기존대로 제외하며 오류 진단 없음', async () => {
  const h = workspaceFixture('?mapDiagnostics=1', {}, async () => ({ ok: true, status: 200,
    json: async () => [{ id: 'synthetic-group', user_id: A.userId,
      items: [{ group_id: 'synthetic-group', ticker: 'CMD_GOLD', market: 'OTHER', name: CANARY }] }]
  }));
  assert.equal(await h.workspace.open(), true); assert.equal(h.workspace.getState().watchlistUnsupportedCount, 1);
  assert.equal(h.workspace.getState().watchlistError, null); assert.equal(h.logs.length, 0); h.workspace.dispose();
});
test('관심목록 진단 출력 실패는 기존 선택적 경고와 보유자료 유지', async () => {
  const h = workspaceFixture('?mapDiagnostics=1', { console: { warn() { throw new Error(CANARY); } } },
    async () => ({ ok: false, status: 503 }));
  assert.equal(await h.workspace.open(), true); assert.equal(h.workspace.getState().watchlistError, 'watchlist-unavailable');
  assert.equal(h.workspace.getState().holdings.length, 1); h.workspace.dispose();
});
test('관심목록 catch는 원래 예외 및 current 예외를 그대로 전파', async () => {
  const h = runtime(), original = new Error(CANARY);
  const base = { api: '/synthetic', getSession: () => A, ownerId: A.userId, signal: new AbortController().signal,
    fetcher: async () => { throw original; }, onDiagnostic() { throw new Error('합성 진단 실패'); } };
  await assert.rejects(h.api.fetchMapWatchlist(base), error => error === original);
  let current = A;
  await assert.rejects(h.api.fetchMapWatchlist({ ...base, getSession: () => current,
    fetcher: async () => { current = B; throw original; } }), { message: 'session-changed' });
  const controller = new AbortController();
  await assert.rejects(h.api.fetchMapWatchlist({ ...base, signal: controller.signal,
    fetcher: async () => { controller.abort(); throw original; } }), { name: 'AbortError', message: 'watchlist-aborted' });
});

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(process.env.HOME_SOURCE_FILE || path.join(root, 'framer-components/public-probe/PublicMorningBriefing.tsx'), 'utf8');
const React = require('../operator-web/node_modules/react');
const { renderToStaticMarkup } = require('../operator-web/node_modules/react-dom/server');
const code = esbuild.transformSync(source + '\nexport { PublicHomeSearch, PublicHomeOverview, homeBriefingSections, homeReadingExample };', { loader: 'tsx', format: 'cjs', jsx: 'automatic' }).code;
const framer = { addPropertyControls() {}, ControlType: {}, RenderTarget: { canvas: 'canvas', current: () => 'preview' } };
const sessionModule = { __esModule: true, default: props => React.createElement('section', { 'data-session-timeline': props.personalizationState, 'data-session-holdings': props.holdingsTickers?.join('|') }) };
function load(overrides = {}) {
    const box = { exports: {} };
    vm.runInNewContext(code, { module: box, exports: box.exports, URL, console,
        require: id => id === 'framer' ? framer : id.includes('PublicSessionBriefing') ? sessionModule : id.startsWith('https:') ? { __esModule: true, default: () => React.createElement('input', { 'aria-label': '종목 이름이나 코드 검색' }) } : require(path.join(root, 'operator-web/node_modules', id)), ...overrides });
    return box.exports;
}
const home = load();
const html = (component, props = {}) => renderToStaticMarkup(React.createElement(component, props));
const today = new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10);
const stamp = new Date().toISOString();
const filing = { ticker: '000001', name: '검수용기업', title: '단일판매ㆍ공급계약체결', date: today, url: 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=' + today.replaceAll('-', '') + '000123' };
const brief = { generated_at: stamp, sections: [{ title: '최근 주요 공시', note: 'DART 접수 기준', items: [filing] }] };

test('SSR order is session timeline → search → neutral personal state → changes → collapsed unique briefing', () => {
    const output = html(home.default);
    const positions = ['data-session-timeline="loading"', 'id="home-search"', '내 자산 연결 상태 확인 중', 'id="home-changes"', 'data-home-briefing'].map(s => output.indexOf(s));
    assert(positions.every((n, i) => n >= 0 && (!i || n > positions[i - 1])));
    assert.doesNotMatch(output, /로그인 →|>NOW<|거장 종목과 알파네스트 소식|내 보유종목 소식|<details[^>]* open/);
    assert.equal((source.match(/<PublicHomeSearch\b/g) || []).length, 1);
    assert.equal((source.match(/<PublicHomeOverview\b/g) || []).length, 1);
    assert.equal((source.match(/<PublicSessionBriefing\b/g) || []).length, 1);
    assert.doesNotMatch(source, /HomeMasterStocks|EditorialNews|pulseIndex|pulsePaused|pulseItems|setReduceMotion/);
});
test('educational anchor survives missing data; a fresh example keeps its actual source and date', () => {
    for (const props of [{}, { brief }, { brief: { ...brief, generated_at: '2000-01-01T00:00:00Z' } }]) {
        const output = html(home.PublicHomeSearch, props);
        assert.equal((output.match(/id="home-filing-example"/g) || []).length, 1);
        assert(output.includes('id="home-search"'));
        assert.doesNotMatch(output, /내 보유·관심종목/);
    }
    const output = html(home.PublicHomeSearch, { brief });
    assert(output.includes(filing.url)); assert(output.includes(filing.title));
    assert.match(output, /실제 공시로 읽어보기/);
    assert.doesNotMatch(html(home.PublicHomeSearch, {}), /검수용기업/);
});
test('missing-data disclosure guide keeps a padded rounded click target', () => {
    const output = html(home.PublicHomeSearch, {});
    assert.match(output, /an-home-example-summary-label/);
    assert.match(output, /class="an-home-example-arrow"/);
    const summary = source.match(/\.an-home-example>summary\{([^}]+)\}/)?.[1] || '';
    assert.match(summary, /min-height:48px/);
    assert.match(summary, /padding:12px 16px!important/);
    assert.match(summary, /border-radius:14px/);
    assert.match(source, /\.an-home-example>summary::-webkit-details-marker\{display:none\}/);
    assert.match(source, /\.an-home-example>summary::marker\{content:""\}/);
});
test('only unique US disclosures, insider changes and estimated schedule survive in additional briefing', () => {
    const titles = ['직전 거래일 시장', '최근 주요 공시', '외인·기관 동반 순매수', '밤사이 미국 공시', '최근 7일 내부자 변동', '이번 주 실적 공시 예상', '알 수 없는 새 섹션'];
    const result = home.homeBriefingSections({ sections: titles.map(title => ({ title, note: '원문 기준일', items: [filing] })) });
    assert.deepEqual(Array.from(result, s => s.title), titles.slice(3, 6));
    assert(result.every(s => s.note === '원문 기준일' && s.items[0].date === today));
    for (const sections of [undefined, null, {}, [null], [{ title: titles[3], items: null }]]) assert.equal(home.homeBriefingSections({ sections }).length, 0);
});
test('larger charts still use received changes/explicit estimates and preserve unknowns', () => {
    const output = html(home.PublicHomeOverview, { brief: { generated_at: stamp, sections: [
        { as_of: '20260928', recap: { kospi: 0, kosdaq: -1.25, kospi_close: 3000, kosdaq_close: null } },
        { title: '외인·기관 동반 순매수', note: '추정금액 = 순매수주수×종가', items: [{ ticker: '000001', text: '외인·기관 동반 순매수 · 추정 1,000억원' }, { ticker: '000002', text: '금액 미제공' }] },
    ] } });
    for (const value of ['0.00%', '-1.25%', '1,000억원', '2026-09-28', '지수값 미제공', '순매수주수×종가']) assert(output.includes(value), value);
    assert.match(source, /\.an-home-zero\{height:12px/);
    assert.match(source, /\.an-home-bar\{height:10px/);
    assert.doesNotMatch(html(home.PublicHomeOverview, { failed: true }), /0.00%|1,000억원/);
});

// Same isolated-effect route as public_report_cards_resize: no browser/network required.
test('border-box observer is stable at padding/breakpoint boundaries, legacy fallback and cleanup', () => {
    const effect = source.match(/useEffect\(\(\) => \{\s*const el = rootRef\.current[\s\S]*?\}, \[\]\)/)?.[0];
    assert(effect);
    for (const outer of [320, 390, 419, 420, 421, 559.5, 590, 810, 1000]) for (const legacy of [false, true]) {
        let width = 0, changes = 0, ro, cleanup;
        const calls = [], el = { offsetWidth: outer };
        vm.runInNewContext(esbuild.transformSync(effect, { loader: 'ts' }).code, { rootRef: { current: el }, useEffect(fn) { cleanup = fn(); },
            setW(fn) { const next = fn(width); if (next !== width) changes++; width = next; },
            ResizeObserver: class { constructor(fn) { this.emit = fn; ro = this; } observe(node, options) { assert.equal(node, el); calls.push(options?.box || 'default'); if (legacy && options) throw Error('legacy'); } disconnect() { this.closed = true; } },
        });
        for (let i = 0; i < 20; i++) ro.emit([{ borderBoxSize: legacy ? undefined : [{ inlineSize: outer }], contentRect: { width: outer - (width < 420 ? 28 : 40) } }]);
        assert.equal(width, outer); assert.equal(changes, 1);
        for (const invalid of [0, -1, NaN, Infinity]) ro.emit([{ borderBoxSize: [{ inlineSize: invalid }] }]);
        assert.equal(width, outer);
        assert.deepEqual(calls, legacy ? ['border-box', 'default'] : ['border-box']);
        cleanup(); assert.equal(ro.closed, true);
    }
    for (const missing of [false, true]) {
        let width = 0;
        vm.runInNewContext(esbuild.transformSync(effect, { loader: 'ts' }).code, { rootRef: { current: missing ? null : { offsetWidth: 590 } }, ResizeObserver: undefined, useEffect(fn) { fn(); }, setW(fn) { width = fn(width); } });
        assert.equal(width, missing ? 0 : 590);
    }
    assert.doesNotMatch(effect, /contentRect|getBoundingClientRect/);
});

// Parent lifecycle harness; child hooks delegate to React for SSR, preserving the real render branches.
function lifecycle(token = '') {
    let cursor = 0, renderingParent = false, currentToken = token;
    const slots = [], queue = [], pending = [], listeners = new Map(), timers = new Map();
    const changed = (a, b) => !a || a.length !== b.length || a.some((v, i) => !Object.is(v, b[i]));
    const hooks = { ...React,
        useState(initial) { if (!renderingParent) return React.useState(initial); const i = cursor++; if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial; return [slots[i], next => { slots[i] = typeof next === 'function' ? next(slots[i]) : next; }]; },
        useRef(initial) { if (!renderingParent) return React.useRef(initial); const i = cursor++; return slots[i] ||= { current: initial }; },
        useMemo(fn, deps) { if (!renderingParent) return React.useMemo(fn, deps); const i = cursor++; if (!slots[i] || changed(slots[i].deps, deps)) slots[i] = { value: fn(), deps }; return slots[i].value; },
        useCallback(fn, deps) { return this.useMemo(fn, deps); },
        useEffect(fn, deps) { if (!renderingParent) return React.useEffect(fn, deps); const i = cursor++; if (!slots[i] || changed(slots[i].deps, deps)) { const previous = slots[i]; slots[i] = { deps }; queue.push(() => { previous?.cleanup?.(); slots[i].cleanup = fn(); }); } },
    };
    hooks.useCallback = (fn, deps) => hooks.useMemo(() => fn, deps);
    const events = { addEventListener(name, fn) { const set = listeners.get(name) || new Set(); set.add(fn); listeners.set(name, set); }, removeEventListener(name, fn) { listeners.get(name)?.delete(fn); } };
    const storage = { getItem: key => key === 'verity_supabase_session' && currentToken ? JSON.stringify({ access_token: currentToken, expires_at: Date.now() / 1000 + 1000 }) : null, setItem() {} };
    const m = load({ localStorage: storage, sessionStorage: { getItem: () => null, setItem() {} }, window: { ...events, location: {} }, document: { ...events, visibilityState: 'visible' },
        setInterval(fn, ms) { const id = timers.size + 1; timers.set(id, ms); return id; }, clearInterval(id) { timers.delete(id); },
        fetch(url, options) { return new Promise((resolve, reject) => pending.push({ url, options, resolve: data => resolve({ ok: true, json: () => Promise.resolve(data) }), reject })); },
        require: id => id === 'react' ? hooks : id === 'framer' ? framer : id.includes('PublicSessionBriefing') ? sessionModule : id.startsWith('https:') ? { __esModule: true, default: () => React.createElement('input') } : require(path.join(root, 'operator-web/node_modules', id)),
    });
    function render() { cursor = 0; renderingParent = true; let tree; try { tree = m.default({}); } finally { renderingParent = false; } return renderToStaticMarkup(tree); }
    return { pending, timers, render,
        flush() { for (const fn of queue.splice(0)) fn(); },
        auth(value) { currentToken = value; for (const fn of listeners.get('verity_auth_change') || []) fn(); },
        close() { for (const slot of slots) slot?.cleanup?.(); },
    };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const request = (run, suffix) => run.pending.find(p => p.url.endsWith(suffix));
const holding = { ticker: '000001', name: '내보유검수기업', shares: 2, avg_cost: 1000, market: 'kr' };
test('session timeline keeps auth/loading/error distinct and receives only current-account tickers in memory', async () => {
    const guest = lifecycle();
    assert.match(guest.render(), /data-session-timeline="loading"/);
    guest.flush(); assert.match(guest.render(), /data-session-timeline="market"/);
    assert.doesNotMatch(guest.render(), /data-session-holdings/); guest.close();
    for (const mode of ['empty', 'error', 'holdings', 'invalid']) {
        const run = lifecycle('a'); run.render(); run.flush();
        assert.match(run.render(), /data-session-timeline="loading"/);
        assert.doesNotMatch(run.render(), /data-session-holdings/);
        const req = request(run, '/api/holdings');
        if (mode === 'error') req.reject(Error('offline'));
        else req.resolve(mode === 'empty' ? [] : mode === 'invalid' ? [{ ...holding, ticker: '' }] : [holding, { ...holding, ticker: ' aapl ' }, holding]);
        await settle();
        const output = run.render();
        assert(output.includes(`data-session-timeline="${mode === 'empty' ? 'market' : mode === 'holdings' ? 'holdings' : 'error'}"`));
        if (mode === 'holdings') assert.match(output, /data-session-holdings="000001\|AAPL"/);
        else assert.doesNotMatch(output, /data-session-holdings/);
        assert.doesNotMatch(JSON.stringify(run.pending.map(({ url, options }) => ({ url, options }))), /000001|AAPL|shares|avg_cost/);
        run.auth('b'); assert.match(run.render(), /data-session-timeline="loading"/); assert.doesNotMatch(run.render(), /data-session-holdings/);
        run.auth(''); assert.match(run.render(), /data-session-timeline="market"/); assert.doesNotMatch(run.render(), /data-session-holdings/);
        run.close();
    }
});
test('logged-out and logged-in first paints are neutral; auth failure is not zero holdings or guest CTA', async () => {
    for (const token of ['', 'account-a']) {
        const run = lifecycle(token);
        assert.doesNotMatch(run.render(), /로그인 →|보유종목을 추가하면|내보유검수기업/);
        run.flush();
        if (!token) assert.match(run.render(), /로그인 →/);
        else {
            assert.match(run.render(), /내 자산 불러오는 중/);
            request(run, '/api/holdings').reject(Error('offline')); await settle();
            const output = run.render(); assert.match(output, /보유종목을 불러오지 못했습니다/);
            assert.doesNotMatch(output, /로그인 →|보유종목을 추가하면/);
        }
        run.close(); assert.equal(run.timers.size, 0);
    }
});
test('account changes/logout discard pending previous-account holdings', async () => {
    const run = lifecycle('a'); run.render(); run.flush();
    const first = request(run, '/api/holdings');
    run.auth('b'); const second = run.pending.filter(p => p.url.endsWith('/api/holdings'))[1];
    first.resolve([holding]); await settle(); assert.doesNotMatch(run.render(), /내보유검수기업/);
    second.resolve([{ ...holding, name: '새계정기업' }]); await settle(); assert.doesNotMatch(run.render(), /로그인 →/);
    run.auth(''); assert.match(run.render(), /로그인 →/);
    assert.doesNotMatch(run.render(), /내 보유종목 소식|새계정기업/); run.close();
});
test('zero holdings, zero received updates and failed news are distinct; personalization intersects holdings only', async () => {
    for (const mode of ['empty', 'zero', 'failed', 'news']) {
        const run = lifecycle('a'); run.render(); run.flush();
        request(run, '/api/holdings').resolve(mode === 'empty' ? [] : [holding]);
        const index = request(run, '/nest_briefing_index.json');
        if (mode === 'failed') index.reject(Error('offline'));
        else index.resolve({ _meta: { generated_at: stamp }, tickers: mode === 'news' ? { '000001': { ev: [{ d: today, t: '내보유공시' }] }, '000002': { ev: [{ d: today, t: '타종목공시' }] } } : {} });
        await settle(); const output = run.render();
        if (mode === 'empty') assert.match(output, /보유종목을 추가하면/);
        if (mode === 'zero') assert.match(output, /수신 자료에서 보유종목의 새 공시가 확인되지 않았어요/);
        if (mode === 'failed') { assert.match(output, /소식을 불러오지 못했습니다/); assert.doesNotMatch(output, /새 공시가 확인되지/); }
        if (mode === 'news') { assert.match(output, /내보유공시/); assert.doesNotMatch(output, /타종목공시/); assert(output.indexOf('내보유공시') < output.indexOf('id="home-changes"')); assert(output.includes(today.slice(5))); }
        run.close();
    }
});
test('seven existing requests, refresh cadence and cache-failure urgency guards stay intact', () => {
    assert.equal((source.match(/\bfetch\(/g) || []).length, 7);
    assert.match(source, /briefFresh && importantFresh/);
    assert.match(source, /setBriefFresh\(false\)/); assert.match(source, /setImportantFresh\(false\)/);
    assert.match(source, /sessionStorage.getItem/);
    const run = lifecycle(); run.render(); run.flush();
    assert.deepEqual([...run.timers.values()].sort((a, b) => a - b), [60000, 300000]); run.close();
});
test('live baseline fact/urgency/search helpers are unchanged', { skip: !process.env.HOME_BASELINE_FILE }, () => {
    const ts = require('../operator-web/node_modules/typescript');
    const before = fs.readFileSync(process.env.HOME_BASELINE_FILE, 'utf8');
    const functions = text => new Map(ts.createSourceFile('home.tsx', text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX).statements.filter(ts.isFunctionDeclaration).map(node => [node.name.text, node.getText()]));
    const old = functions(before), next = functions(source);
    const canonical = text => esbuild.transformSync(text, { loader: 'tsx', format: 'esm', minifyWhitespace: true }).code;
    for (const name of ['disclosureReceipt', 'urgentDisclosure', 'homeUrgentReason', 'homeCompanyLogoSrc', 'HomeCompanyLogo', 'finiteValue', 'receiptUrl', 'flowAmount', 'homeFilingFacts', 'homeSnapshot', 'updatedAt', 'homeReadingExample', 'getToken', '_usPath']) assert.equal(canonical(next.get(name)), canonical(old.get(name)), name);
});

test('collapsed briefing preserves feed-only important title/date/source and validated priority without duplicate overview rows', async () => {
    const run=lifecycle();run.render();run.flush();
    const additional={...filing,title:'부도발생',url:filing.url.replace(/000123$/,'000124')};
    request(run,'/daily_briefing.json').resolve({...brief,sections:[...brief.sections,{title:'최근 7일 내부자 변동',note:'DART 보고 사실',items:[{name:'내부자검수',text:'보고 주식수 변동'}]}]});
    request(run,'/urgent_alerts.json').resolve({_meta:{generated_at:stamp},alerts:[filing,additional].map(r=>({...r,type:'disclosure',headline:r.title,source_url:r.url}))});
    await settle();const output=run.render();
    const block=output.slice(output.indexOf('data-home-briefing'));
    assert.match(block,/중요 공시·미국 공시·예상 일정 더 보기/);
    assert.match(block,/추가 중요 공시/);assert.match(block,/부도발생/);assert.match(block,/data-home-urgency/);
    assert(block.includes(today));assert(block.includes(additional.url));assert(!block.includes(filing.url));
    assert.match(block,/target="_blank" rel="noopener noreferrer"/);
    assert.match(block,/내부자검수/);assert.doesNotMatch(block,/이번 자료에 제공된 추가 항목이 없습니다/);
    assert.doesNotMatch(output,/<details[^>]* open/);run.close();
});

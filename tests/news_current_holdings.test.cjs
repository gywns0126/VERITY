const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { transformSync } = require('esbuild');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(process.env.NEWS_COMPONENT_PATH || path.join(root, 'framer-components/public-probe/PublicNewsTab.tsx'), 'utf8');
const helper = source.slice(source.indexOf('function currentHoldingStocks'), source.indexOf('// 오늘 핫한 종목'));
const effect = source.slice(source.indexOf('/* 내 종목 source contract'), source.indexOf('/* 데이터 로드'));
const personalCode = transformSync(helper + '\n' + effect, { loader: 'tsx' }).code;
const normalize = value => JSON.parse(JSON.stringify(value));
const settled = () => new Promise(resolve => setImmediate(resolve));
const hynix = { ticker: '000660', name: 'SK하이닉스', market: 'KR', shares: 10 };
const millie = { ticker: '418470', name: '밀리의서재', market: 'KR', shares: 0 };

// Execute the actual component effect, with isolated test sessions and deferred HTTP responses.
// These strings are fixtures, never real session credentials or account data.
function harness({ member = true, local = [millie] } = {}) {
    const state = { watch: [], memberMode: false, loading: false, error: '' };
    const storage = new Map([['verity_watchlist', JSON.stringify(local)]]);
    if (member) storage.set('verity_supabase_session', JSON.stringify({ access_token: 'fixture-A' }));
    const listeners = new Map(), requests = [];
    const newsAudienceToken = { current: '' };
    let dispose;
    const box = {
        AbortController, onCanvas: false, props: { apiBase: 'https://fixture.invalid/' },
        newsAudienceToken,
        localStorage: { getItem: key => storage.get(key) || null },
        setWatch: value => { state.watch = normalize(value); },
        setNaverNews: () => {}, setNewsAudienceVersion: () => {},
        setMemberMode: value => { state.memberMode = value; },
        setPersonalLoading: value => { state.loading = value; },
        setPersonalError: value => { state.error = value; },
        useEffect: callback => { dispose = callback(); },
        window: {
            addEventListener: (name, callback) => listeners.set(name, callback),
            removeEventListener: (name, callback) => { if (listeners.get(name) === callback) listeners.delete(name); },
        },
        fetch: (url, options) => new Promise((resolve, reject) => {
            requests.push({ url, options, reject, respond: (payload, ok = true) => resolve({ ok, json: async () => payload }) });
        }),
    };
    vm.runInNewContext(personalCode, box);
    return { state, requests, listeners, storage, dispose: () => dispose(),
        emit: name => listeners.get(name)?.(), holdings: payload => normalize(box.currentHoldingStocks(payload)) };
}

test('only positive holdings: watchlist-only and sold Millie never enter member news', async () => {
    const h = harness();
    assert.equal(h.requests.length, 1);
    assert.equal(h.requests[0].url, 'https://fixture.invalid/api/holdings');
    assert.equal(h.requests[0].options.cache, 'no-store');
    assert.equal(h.requests[0].options.headers.Authorization, 'Bearer fixture-A');
    assert.equal(h.state.loading, true);
    h.requests[0].respond([hynix, millie]); await settled();
    assert.deepEqual(h.state.watch, [{ ticker: '000660', name: 'SK하이닉스', market: 'KR', watched: false, held: true }]);
    assert.equal(h.state.loading, false); assert.equal(h.state.error, ''); h.dispose();
});

test('quantity validation excludes missing, zero, negative, non-finite and boolean values', () => {
    const h = harness({ member: false });
    for (const shares of [undefined, null, '', ' ', '0', 0, -1, '-1', NaN, Infinity, 'Infinity', false, true, {}, []]) {
        assert.deepEqual(h.holdings([{ ...millie, shares }]), [], String(shares));
    }
    assert.deepEqual(h.holdings([null, 'bad row', 42, { shares: 1 }]), []);
    for (const shares of [1, '2', 0.25, '0.125']) assert.equal(h.holdings([{ ...hynix, shares }]).length, 1);
    h.dispose();
});

test('wrapper payload and normalized duplicates; zero row cannot replace a positive holding', () => {
    const h = harness({ member: false });
    const result = h.holdings({ holdings: [{ ticker: ' aapl ', shares: '0.5' }, { ticker: 'AAPL', shares: 2 }, { ticker: 'AAPL', shares: 0 }] });
    assert.deepEqual(result.map(row => row.ticker), ['AAPL']);
    for (const payload of [null, {}, { holdings: null }, { error: 'failure' }, 'bad']) assert.throws(() => h.holdings(payload), /Invalid holdings/);
    assert.deepEqual(h.holdings({ holdings: [] }), []); h.dispose();
});

test('empty holdings stays empty even with populated local watchlist', async () => {
    const h = harness(); h.requests[0].respond([]); await settled();
    assert.deepEqual(h.state, { watch: [], memberMode: true, loading: false, error: '' }); h.dispose();
});

for (const failure of ['http', 'network', 'malformed']) test(`${failure} failure clears personal membership instead of falling back`, async () => {
    const h = harness(); h.requests[0].respond([hynix]); await settled();
    h.emit('verity_holdings_change'); assert.deepEqual(h.state.watch.map(row => row.ticker), ['000660']); assert(h.state.loading);
    if (failure === 'network') h.requests[1].reject(new Error('offline'));
    else h.requests[1].respond(failure === 'malformed' ? {} : null, failure !== 'http');
    await settled(); assert.deepEqual(h.state.watch, []); assert(h.state.memberMode); assert(h.state.error); assert(!h.state.loading); h.dispose();
});

test('late old success cannot restore sold holdings after a newer response', async () => {
    const h = harness(); h.emit('verity_holdings_change');
    assert(h.requests[0].options.signal.aborted);
    h.requests[1].respond([hynix]); await settled();
    // Simulate a transport that ignores AbortSignal.
    h.requests[0].respond([{ ...millie, shares: 20 }]); await settled();
    assert.deepEqual(h.state.watch.map(row => row.ticker), ['000660']); h.dispose();
});

test('late old failure cannot clear newer holdings or set an error', async () => {
    const h = harness(); h.emit('focus'); h.requests[1].respond([hynix]); await settled();
    h.requests[0].reject(new Error('old request')); await settled();
    assert.equal(h.state.watch.length, 1); assert.equal(h.state.error, ''); h.dispose();
});

test('old response cannot end the latest loading state', async () => {
    const h = harness(); h.emit('pageshow'); h.requests[0].respond([millie]); await settled();
    assert(h.state.loading); assert.deepEqual(h.state.watch, []);
    h.requests[1].respond([hynix]); await settled(); assert(!h.state.loading); h.dispose();
});

test('logout invalidates member request and uses only explicitly labeled device watchlist', async () => {
    const h = harness(); h.storage.delete('verity_supabase_session'); h.emit('verity_auth_change');
    assert.equal(h.state.memberMode, false); assert.equal(h.state.watch[0].held, false);
    h.requests[0].respond([hynix]); await settled();
    assert.deepEqual(h.state.watch.map(row => row.ticker), ['418470']); assert(!h.state.loading); h.dispose();
});

test('account change invalidates former member response', async () => {
    const h = harness();
    h.storage.set('verity_supabase_session', JSON.stringify({ access_token: 'fixture-B' })); h.emit('storage');
    h.requests[1].respond([]); await settled(); h.requests[0].respond([hynix]); await settled();
    assert.deepEqual(h.state.watch, []); assert(h.state.memberMode); h.dispose();
});

test('unmount aborts the request, removes listeners and rejects late updates', async () => {
    const h = harness(); h.dispose(); const before = normalize(h.state);
    assert.equal(h.listeners.size, 0); assert(h.requests[0].options.signal.aborted);
    h.requests[0].respond([hynix]); await settled(); assert.deepEqual(h.state, before);
});

test('all canonical refresh events re-read current membership and clean up', () => {
    const events = ['verity-watchlist-changed', 'verity_watch_change', 'verity_holdings_change', 'verity_auth_change', 'storage', 'focus', 'pageshow'];
    const h = harness(); assert.deepEqual([...h.listeners.keys()], events);
    for (const event of events) h.emit(event);
    assert.equal(h.requests.length, events.length + 1);
    assert(h.requests.every(request => request.url.endsWith('/api/holdings'))); h.dispose();
});

const React = require('react');
const compiled = transformSync(source + '\nexport { StockNews };', { loader: 'tsx', format: 'cjs', jsx: 'automatic' }).code;
const declarations = source.slice(source.indexOf('export default function PublicNewsTab'), source.indexOf('/* 내 종목 source contract'));
const stateNames = [...declarations.matchAll(/const \[(\w+),[^\]]+\] = useState/g)].map(match => match[1]);
function draw(values) {
    let index = 0;
    const box = { exports: {}, module: { exports: {} }, URL, Intl, console, require: id =>
        id === 'framer' ? { addPropertyControls() {}, ControlType: {}, RenderTarget: { current: () => 'preview', canvas: 'canvas' } } :
        id === 'react' ? { ...React, useState: initial => { const name = stateNames[index++]; return [name in values ? values[name] : initial, () => {}]; }, useEffect() {}, useMemo: fn => fn(), useRef: () => ({ current: null }) } :
        require(id) };
    vm.runInNewContext(compiled, box);
    return { tree: box.module.exports.default({}), StockNews: box.module.exports.StockNews };
}
function elements(node, type, found = []) {
    if (Array.isArray(node)) node.forEach(item => elements(item, type, found));
    else if (node && typeof node === 'object') { if (node.type === type) found.push(node); elements(node.props?.children, type, found); }
    return found;
}
function textOf(node) {
    if (Array.isArray(node)) return node.map(textOf).join('');
    if (node && typeof node === 'object') return textOf(node.props?.children);
    return typeof node === 'string' || typeof node === 'number' ? String(node) : '';
}

test('actual component renders only holdings despite unrelated recommendation and cached news entries', () => {
    const h = harness({ member: false });
    const watch = h.holdings([hynix, millie]); h.dispose();
    const { tree, StockNews } = draw({ loading: false, memberMode: true, watch,
        recMap: { '418470': { ...millie, items: [{ title: 'Old Millie news' }] } },
        recGroups: [{ ...millie, items: [{ title: 'Old recommendation' }] }],
        naverNews: { '418470': [{ title: 'Cached old news' }] } });
    assert.match(textOf(tree), /보유종목1/); assert.match(textOf(tree), /보유 수량 0 초과 기준/);
    const personal = elements(tree, StockNews); assert.equal(personal.length, 1);
    assert.deepEqual(normalize(personal[0].props.groups).map(group => group.ticker), ['000660']);
    assert.deepEqual(normalize(personal[0].props.groups[0].items), []); // no news is not a reason to change membership
});

test('actual empty, loading and error UI never renders fallback personal cards', () => {
    for (const [state, message] of [
        [{}, '현재 보유종목이 없어요.'],
        [{ personalLoading: true }, '현재 보유종목을 확인하고 있어요.'],
        [{ personalError: '보유 조회 실패' }, '보유 조회 실패'],
    ]) {
        const { tree, StockNews } = draw({ loading: false, memberMode: true, ...state });
        assert.match(textOf(tree), new RegExp(message)); assert.equal(elements(tree, StockNews).length, 0);
    }
});

test('explicit search stays separate from personal holdings; guest source is labeled', () => {
    const searchGroup = { ...millie, items: [] };
    const { tree, StockNews } = draw({ loading: false, memberMode: true, watch: [hynix], searchGroup });
    const cards = elements(tree, StockNews);
    assert.equal(cards.length, 2); assert.equal(cards[0].props.groups[0].ticker, '418470');
    assert.equal(cards[1].props.groups[0].ticker, '000660'); assert.match(textOf(tree), /검색 결과/);
    assert.match(textOf(draw({ loading: false }).tree), /이 기기의 관심/);
});

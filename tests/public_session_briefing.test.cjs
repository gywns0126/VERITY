const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '..');
const React = require('../operator-web/node_modules/react');
const { renderToStaticMarkup } = require('../operator-web/node_modules/react-dom/server');
const source = fs.readFileSync(process.env.SESSION_SOURCE_FILE || path.join(root, 'framer-components/public-probe/PublicSessionBriefing.tsx'), 'utf8');
const code = esbuild.transformSync(source + '\nexport { Fact, CSS };', { loader: 'tsx', format: 'cjs', jsx: 'automatic' }).code;
const framer = { addPropertyControls() {}, ControlType: {}, RenderTarget: { canvas: 'canvas', current: () => 'preview' } };
function load(extra = {}) {
    const box = { exports: {} };
    vm.runInNewContext(code, { module: box, exports: box.exports, console, URL, Date, AbortController,
        require: id => id === 'framer' ? framer : require(path.join(root, 'operator-web/node_modules', id)), ...extra });
    return box.exports;
}
const mod = load();
const stripStyle = text => text.replace(/<style>[\s\S]*?<\/style>/g, '');
const html = (component, props) => stripStyle(renderToStaticMarkup(React.createElement(component, props)));
const calendar = { valid_from: '2026-01-01', valid_until: '2026-12-31', holidays: ['2026-10-09'], unknown_dates: ['2026-10-06'], open_minute: 540, close_minute: 930 };
const date = '2026-10-05';
const at = time => Date.parse(`${date}T${time}+09:00`);
const fact = (id, text, as_of = date, extra = {}) => ({ id, category: '공시', title: text, text, as_of, url: 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261005000123', ...extra });
const snapshot = (phase, time, items) => ({ snapshot_id: phase + '-1', generated_at: `${date}T${time}+09:00`, phase, items });
const day = () => ({ schema_version: 1, date, trading_day: { status: 'open' }, snapshots: [
    snapshot('pre', '08:30:00', [fact('shared', '매출 100억원', date), fact('held', '보유 기업 공시', date, { ticker: '000660', name: 'SK하이닉스' }), fact('other', '다른 기업 공시', date, { ticker: '005930', name: '삼성전자' })]),
    snapshot('open', '10:00:00', [fact('shared', '매출 120억원', date), fact('extra', '장중 원문 사실')]),
    snapshot('post', '16:00:00', [fact('shared', '매출 130억원', '2026-10-06'), fact('post', '마감 후 원문 사실')]),
], cards: { pre: 'pre-1', open: 'open-1', post: 'post-1' } });
const index = (days = [date], cal = calendar) => ({ schema_version: 1, generated_at: `${date}T08:30:00+09:00`, calendar: cal, days: days.map(d => ({ date: d, trading_day: { status: mod.tradingStatus(d, cal) } })) });
const settle = () => new Promise(resolve => setImmediate(resolve));

// Deterministic effects/network harness: actual component rendering with controlled monotonic time.
function lifecycle(props = {}, deviceTime = Date.parse('2040-01-01T00:00:00Z')) {
    let cursor = 0, parent = false, monotonic = 1000, tree, timerId = 0;
    const slots = [], effects = [], requests = [], timers = new Map(), listeners = new Map();
    const changed = (a, b) => !a || !b || a.length !== b.length || a.some((v, i) => !Object.is(v, b[i]));
    const hooks = { ...React,
        useState(initial) { if (!parent) return React.useState(initial); const i = cursor++; if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial; return [slots[i], value => { slots[i] = typeof value === 'function' ? value(slots[i]) : value; }]; },
        useRef(initial) { if (!parent) return React.useRef(initial); const i = cursor++; return slots[i] ||= { current: initial }; },
        useMemo(fn, deps) { if (!parent) return React.useMemo(fn, deps); const i = cursor++; if (!slots[i] || changed(slots[i].deps, deps)) slots[i] = { deps, value: fn() }; return slots[i].value; },
        useEffect(fn, deps) { if (!parent) return React.useEffect(fn, deps); const i = cursor++; if (!slots[i] || changed(slots[i].deps, deps)) { const old = slots[i]; slots[i] = { deps }; effects.push(() => { old?.cleanup?.(); slots[i].cleanup = fn(); }); } },
    };
    const events = { addEventListener(name, fn) { const set = listeners.get(name) || new Set(); set.add(fn); listeners.set(name, set); }, removeEventListener(name, fn) { listeners.get(name)?.delete(fn); } };
    class WrongDeviceDate extends Date { constructor(...args) { super(...(args.length ? args : [deviceTime])); } static now() { return deviceTime; } }
    const putTimer = (fn, ms, repeat) => { const id = ++timerId; timers.set(id, { fn, ms, repeat }); return id; };
    const m = load({ Date: WrongDeviceDate, performance: { now: () => monotonic }, window: { ...events, location: { origin: 'https://www.alphanest.kr' } }, document: { ...events, hidden: false },
        setTimeout: (fn, ms) => putTimer(fn, ms, false), clearTimeout: id => timers.delete(id), setInterval: (fn, ms) => putTimer(fn, ms, true), clearInterval: id => timers.delete(id),
        fetch(url, options = {}) { return new Promise((resolve, reject) => {
            const r = { url, options, done: false, resolve(value, headers = {}) { r.done = true; resolve({ ok: true, json: async () => value, headers: { get: name => headers[name] ?? null } }); }, reject(error = Error('offline')) { r.done = true; reject(error); } };
            options.signal?.addEventListener('abort', () => r.reject(Error('AbortError')), { once: true }); requests.push(r);
        }); },
        require: id => id === 'react' ? hooks : id === 'framer' ? framer : require(path.join(root, 'operator-web/node_modules', id)),
    });
    const render = () => { cursor = 0; parent = true; try { tree = m.default(props); } finally { parent = false; } return stripStyle(renderToStaticMarkup(tree)); };
    const nodes = node => { if (!node || typeof node !== 'object') return []; if (Array.isArray(node)) return node.flatMap(n => nodes(n)); return [node, ...nodes(node.props?.children)]; };
    return { requests, timers, render, props,
        flush() { for (const fn of effects.splice(0)) fn(); },
        request(suffix) { return requests.findLast(r => !r.done && !r.options.signal?.aborted && r.url.endsWith(suffix)); },
        selectDate(value) { nodes(tree).find(n => n.type === 'select').props.onChange({ target: { value } }); },
        selectMarket(value) { const group = nodes(tree).find(n => n.props?.className === 'asb-market-switch'); nodes(group).find(n => n.type === 'button' && n.key === value).props.onClick(); },
        expand(phase) { const card = nodes(tree).find(n => n.props?.['data-phase'] === phase); nodes(card).find(n => n.type === 'button').props.onClick(); },
        collapseDetail() { nodes(tree).find(n => n.type === 'button' && n.props['aria-label'] === '상세 기록 접기').props.onClick(); },
        trackChildren() { const track = nodes(tree).find(n => n.props?.className === 'asb-track'); const flat = node => !node || typeof node !== 'object' ? [] : Array.isArray(node) ? node.flatMap(flat) : node.type === React.Fragment ? flat(node.props.children) : [node]; return flat(track?.props.children); },
        event(name) { for (const fn of listeners.get(name) || []) fn(); },
        tick(ms) { monotonic += ms; for (const [id, t] of [...timers]) if (t.repeat && t.ms === ms) t.fn(); },
        expire(ms) { for (const [id, t] of [...timers]) if (!t.repeat && t.ms === ms) { timers.delete(id); t.fn(); } },
        close() { for (const slot of slots) slot?.cleanup?.(); },
    };
}
async function boot(run, record = day(), idx = index(), time = '16:10:00') {
    run.render(); run.flush();
    run.request('/').resolve(null, { Date: new Date(at(time)).toUTCString() }); await settle(); run.render(); run.flush();
    run.request('/index.json').resolve(idx); await settle(); run.render(); run.flush();
    const req = run.request(`/${date}.json`); if (req) req.resolve(record);
    await settle(); run.render(); run.flush(); return run.render();
}

test('trading dates have exactly three cards, closed dates one and unknown dates none', () => {
    assert.deepEqual(Array.from(mod.phaseCards('open')), ['pre', 'open', 'post']);
    assert.deepEqual(Array.from(mod.phaseCards('closed')), ['closed']);
    assert.equal(mod.phaseCards('unknown').length, 0);
    for (const d of ['2026-10-04', '2026-10-09']) assert.equal(mod.tradingStatus(d, calendar), 'closed');
    for (const d of ['2027-01-01', '2026-10-06']) assert.equal(mod.tradingStatus(d, calendar), 'unknown');
    assert.equal(mod.tradingStatus(date, calendar), 'open');
});
test('impossible dates and malformed calendars never invent a trading day', () => {
    for (const d of ['2026-02-30', '2026-13-01', '2026-00-00']) assert.equal(mod.tradingStatus(d, calendar), 'unknown', d);
    assert.equal(mod.tradingStatus(date, { ...calendar, valid_until: '' }), 'unknown');
});
test('09:00 and 15:30 boundaries use internet epoch, and KST midnight changes date', () => {
    for (const [t, p] of [['08:59:59', 'pre'], ['09:00:00', 'open'], ['15:29:59', 'open'], ['15:30:00', 'post']]) assert.equal(mod.activePhase(at(t), 'open', calendar), p);
    assert.equal(mod.activePhase(null, 'open', calendar), null);
    assert.equal(mod.activePhase(at('10:00:00'), 'unknown', calendar), null);
    assert.equal(mod.activePhase(at('10:00:00'), 'closed', calendar), 'closed');
    assert.equal(mod.kstDate(Date.parse('2026-10-05T15:00:00Z')), '2026-10-06');
});
test('invalid clock samples do not become a current phase', () => {
    for (const bad of [NaN, Infinity, -Infinity]) assert.equal(mod.activePhase(bad, 'open', calendar), null);
    assert.equal(mod.activePhase(at('10:00:00'), 'open', { ...calendar, open_minute: 1000, close_minute: 540 }), null);
    assert.equal(mod.serverEpoch('invalid', '0', 0), null);
    assert.equal(mod.serverEpoch(new Date(at('10:00:00')).toUTCString(), '-1', 0), null);
    assert.equal(mod.serverEpoch(new Date(at('10:00:00')).toUTCString(), '0', 10000), null);
    assert.equal(mod.serverEpoch(new Date(at('10:00:00')).toUTCString(), '30', 400), at('10:00:00') + 30200);
});
test('same-asof corrections retain original text with del; newer observations do not strike old facts', () => {
    const before = fact('x', '매출 100억원'), same = fact('x', '매출 120억원'), newer = fact('x', '매출 130억원', '2026-10-06');
    assert.equal(mod.itemChange(before, same), 'revision'); assert.equal(mod.itemChange(before, newer), 'observation');
    assert.equal(mod.itemChange(before, { ...same, id: 'other' }), null);
    const corrected = html(mod.Fact, { item: before, later: same });
    const beforeParagraph = corrected.match(/<p[^>]*>(.*?)<\/p>/s)[1];
    assert.equal(beforeParagraph.replace(/ <ins[^>]*>.*?<\/ins>/s, '').replace(/<[^>]+>/g, ''), before.text);
    assert.equal(beforeParagraph.replace(/<del[^>]*>.*?<\/del> /s, '').replace(/<[^>]+>/g, ''), same.text);
    assert.match(corrected, /<del/); assert.match(corrected, /<ins/);
    assert.match(corrected, /<del[^>]*>100<\/del>/); assert.match(corrected, /<ins[^>]*>120<\/ins>/);
    const observed = html(mod.Fact, { item: before, later: newer });
    assert.doesNotMatch(observed, /<del|<ins/); assert.match(observed, /매출 100억원/); assert.match(observed, /매출 130억원/);
    assert.match(observed, /이후 시점의 새 관측/);
    for (const [a, b] of [['', '새 공시'], ['삭제', ''], ['같음', '같음'], ['앞 1 뒤', '앞 2 뒤']]) { const d = mod.changedFragments(a, b); assert.equal(d.prefix + d.before + d.suffix, a); assert.equal(d.prefix + d.after + d.suffix, b); }
});
test('SSR remains neutral without invented dates, sample facts or phase cards', () => {
    const output = html(mod.default, { personalizationState: 'loading' });
    assert.doesNotMatch(output, /data-card-count|data-phase=|2040|매출 100/);
    assert.match(output, /시각 확인 중/); assert.match(output, /보유종목 확인 중/);
});
test('server time overrides a wildly wrong device clock and preserves real snapshot facts', async () => {
    const run = lifecycle(); try {
        const output = await boot(run);
        assert.match(output, /data-card-count="3"/); assert.doesNotMatch(output, /2040/);
        assert.match(output, /data-phase="post" data-active="true"/);
        for (const text of ['매출 100억원', '매출 120억원', '매출 130억원', '마감 후 원문 사실']) assert(output.includes(text), text);
        run.expand('pre'); const detail = run.render(); assert.match(detail, /다른 기업 공시/); assert.match(detail, /원문 확인/);
    } finally { run.close(); assert.equal(run.timers.size, 0); }
});
test('closed archive renders one card; unknown schedule never fabricates three cards', async () => {
    for (const status of ['closed', 'unknown']) { const record = day(); record.trading_day.status = status; record.snapshots = []; record.cards = {};
        const run = lifecycle(); try { const output = await boot(run, record); if (status === 'closed') { assert.match(output, /data-card-count="1"/); assert.match(output, /data-phase="closed"/); } else assert.doesNotMatch(output, /data-card-count|data-phase=/); } finally { run.close(); }
    }
});
test('personalization filters only display and never sends holdings, auth, shares or cost to public requests', async () => {
    for (const state of ['loading', 'error', 'market', 'holdings']) {
        const run = lifecycle({ holdingsTickers: ['000660'], personalizationState: state }); try {
            await boot(run); run.expand('pre'); const output = run.render();
            assert.match(output, /보유 기업 공시/); if (state === 'holdings') assert.doesNotMatch(output, /다른 기업 공시/); else assert.match(output, /다른 기업 공시/);
            const requests = run.requests.map(r => ({ url: r.url, options: r.options }));
            assert.doesNotMatch(JSON.stringify(requests), /000660|Authorization|holdings|shares|avg_cost/);
            assert(requests.every(r => r.options.credentials === 'omit'));
        } finally { run.close(); }
    }
});
test('network failure retains last real facts with an error marker', async () => {
    const run = lifecycle(); try {
        await boot(run); run.event('focus'); run.render(); run.flush();
        for (const r of run.requests.filter(r => !r.done && r.options.method !== 'HEAD')) r.reject();
        await settle(); const output = run.render(); assert.match(output, /불러오지 못/); assert.match(output, /매출 100억원/);
    } finally { run.close(); }
});
test('request deadline exits loading and offers retry instead of silently ignoring abort', async () => {
    const run = lifecycle(); try { run.render(); run.flush(); run.expire(10000); await settle(); const output = run.render(); assert.match(output, /불러오지 못|다시 불러오기/); } finally { run.close(); }
});
test('day deadline keeps received facts, leaves loading and exposes retry', async () => {
    const run = lifecycle(); try {
        await boot(run); run.event('focus'); run.render(); run.flush();
        run.request('/index.json').resolve(index()); await settle(); run.render(); run.flush();
        assert(run.request(`/${date}.json`)); run.expire(10000); await settle();
        const output = run.render(); assert.match(output, /불러오지 못|다시 불러오기/); assert.match(output, /매출 100억원/); assert.doesNotMatch(output, /기록을 불러오는 중/);
    } finally { run.close(); }
});
test('successful index refresh cannot erase the unresolved day request error', async () => {
    const run = lifecycle(); try {
        await boot(run); run.event('focus'); run.render(); run.flush();
        run.request(`/${date}.json`).reject(); await settle(); assert.match(run.render(), /불러오지 못/);
        run.request('/index.json').resolve(index()); await settle(); run.render(); run.flush();
        assert.match(run.render(), /불러오지 못/);
    } finally { run.close(); }
});
test('malformed day records fail closed without render crashes or fabricated facts', async () => {
    for (const corrupt of [r => { delete r.trading_day; }, r => { r.snapshots[0].items = [null]; }, r => { delete r.snapshots[1].generated_at; }, r => { r.cards = []; }]) {
        const run = lifecycle(), record = day(); corrupt(record);
        try { const output = await boot(run, record); assert.match(output, /불러오지 못|확인할 수 없|형식/); assert.doesNotMatch(output, /매출 100억원/); } finally { run.close(); }
    }
});
test('changing archive date discards pending older request and clears prior-date facts', async () => {
    const run = lifecycle(); try {
        await boot(run, day(), index([date, '2026-10-02']));
        run.selectDate('2026-10-02'); assert.doesNotMatch(run.render(), /매출 100억원/, 'before effects run, the old date must already be hidden'); run.flush();
        const older = run.request('/2026-10-02.json'); assert(older);
        assert.doesNotMatch(run.render(), /매출 100억원/);
        run.selectDate(date); run.render(); run.flush(); assert.equal(older.options.signal.aborted, true);
        run.request(`/${date}.json`).resolve(day()); await settle(); assert.match(run.render(), /매출 100억원/);
    } finally { run.close(); }
});
test('monotonic clock crosses phase boundary and expires if internet time cannot refresh', async () => {
    const run = lifecycle(); try { await boot(run, day(), index(), '08:59:50'); run.tick(15000); assert.match(run.render(), /data-phase="open" data-active="true"/); run.tick(15 * 60000); run.tick(15000); assert.match(run.render(), /시각 확인 중/); } finally { run.close(); }
});
test('KST date rollover does not present the prior day facts under a new date', async () => {
    const run = lifecycle(); try {
        await boot(run, day(), index(), '23:59:50'); run.tick(15000); run.render(); run.flush();
        const output = run.render(); assert.match(output, /2026\.10\.06/); assert.doesNotMatch(output, /매출 100억원|data-card-count=/);
    } finally { run.close(); }
});
test('future snapshots stay hidden until internet time reaches their generation time', async () => {
    const run = lifecycle(); try {
        const output = await boot(run, day(), index(), '10:00:00');
        assert.match(output, /data-card-count="3"/); assert.match(output, /data-phase="open" data-active="true"/);
        assert.doesNotMatch(output, /매출 130억원|마감 후 원문 사실/); assert.match(output, /아직 시작 전/);
    } finally { run.close(); }
});
test('index normalization rejects bad shapes and sorts a copy without rewriting received metadata', () => {
    const original = index(['2026-10-02', date]), before = JSON.stringify(original);
    const normalized = mod.normalizeIndex(original);
    assert.deepEqual(Array.from(normalized.days, d => d.date), [date, '2026-10-02']);
    assert.equal(JSON.stringify(original), before); assert.equal(normalized.generated_at, original.generated_at);
    for (const mutate of [r => r.schema_version = 2, r => r.generated_at = '2026-10-05T10:00:00', r => r.days[0].date = '2026-02-30', r => delete r.days[0].trading_day,
        r => r.calendar.holidays = ['2026-02-30'], r => r.calendar.open_minute = r.calendar.close_minute]) {
        const r = JSON.parse(JSON.stringify(original)); mutate(r); assert.throws(() => mod.normalizeIndex(r));
    }
});
test('day normalization validates dates, snapshot identities, card references and item types without mutating facts', () => {
    const original = day(), before = JSON.stringify(original);
    const normalized = mod.normalizeDay(original, date); assert.equal(JSON.stringify(normalized), before); assert.equal(JSON.stringify(original), before);
    assert.throws(() => mod.normalizeDay(original, '2026-10-02'));
    for (const mutate of [r => r.snapshots.push(r.snapshots[0]), r => r.snapshots[1].generated_at = '2026-10-05T10:00:00', r => r.snapshots[1].generated_at = '2026-10-04T10:00:00+09:00',
        r => r.cards.pre = 'missing', r => r.cards.pre = 'post-1', r => r.snapshots[0].items.push(r.snapshots[0].items[0]), r => r.snapshots[0].items[0].text = {}, r => r.snapshots[0].items[0].ticker = '../unsafe']) {
        const r = day(); mutate(r); assert.throws(() => mod.normalizeDay(r, date));
    }
});
test('closed day summary contains actual facts from every phase, latest revisions and original archived copies', async () => {
    const record = day(); record.day_summary = { status: 'closed', generated_at: '2026-10-06T00:05:00+09:00', cutoff_at: '2026-10-06T00:00:00+09:00', snapshot_ids: record.snapshots.map(s => s.snapshot_id), observed_changes: [] };
    const original = JSON.stringify(record), items = mod.dayItems(record, 'post');
    assert.deepEqual(Array.from(items, i => i.id), ['shared', 'held', 'other', 'extra', 'post']);
    assert.equal(items.find(i => i.id === 'shared').text, '매출 130억원'); assert.equal(record.snapshots[0].items[0].text, '매출 100억원'); assert.equal(JSON.stringify(record), original);
    const run = lifecycle(); try {
        await boot(run, record); run.expand('post'); const output = run.render();
        for (const text of ['보유 기업 공시', '다른 기업 공시', '장중 원문 사실', '마감 후 원문 사실', '매출 130억원']) assert(output.includes(text), text);
        assert.match(output, /원문 확인/); assert.match(output, /자료 기준/);
    } finally { run.close(); }
});
test('equivalent timestamp zones use chronological order while preserving original stamps', () => {
    const record = day(); record.snapshots = record.snapshots.slice(0, 2); delete record.cards.post;
    record.snapshots[1].generated_at = '2026-10-05T01:00:00Z';
    record.day_summary = { status: 'closed' };
    const normalized = mod.normalizeDay(record, date);
    assert.equal(mod.dayItems(normalized, 'post').find(i => i.id === 'shared').text, '매출 120억원');
    assert.equal(normalized.snapshots[1].generated_at, '2026-10-05T01:00:00Z');
});
test('manual phase selection stays stable across clock refresh without losing its original facts', async () => {
    const run = lifecycle(); try {
        await boot(run, day(), index([date, '2026-10-02']), '08:59:50'); run.expand('pre'); run.render();
        run.tick(15000); const output = run.render();
        assert.match(output, /data-phase="pre" data-active="true"/); assert.match(output, /장전 기록/); assert.match(output, /보유 기업 공시/);
        run.selectDate('2026-10-02'); const firstPaint = run.render(); assert.doesNotMatch(firstPaint, /보유 기업 공시|매출 100억원/);
        run.flush(); assert.doesNotMatch(run.render(), /class="asb-detail"/);
    } finally { run.close(); }
});

const temporalStates = output => Object.fromEntries([...output.matchAll(/<article\b[^>]*>/g)].map(([tag]) => [tag.match(/data-phase="([^"]+)"/)?.[1], tag.match(/data-time-state="([^"]+)"/)?.[1]]).filter(([phase]) => phase));
test('11:00 temporal state stays pre=past/open=current/post=future when a past card is selected', async () => {
    const run = lifecycle(); try {
        const expected = { pre: 'past', open: 'current', post: 'future' };
        assert.deepEqual(temporalStates(await boot(run, day(), index(), '11:00:00')), expected);
        run.expand('pre'); const output = run.render();
        assert.deepEqual(temporalStates(output), expected);
        assert.match(output, /data-phase="pre" data-active="true"/);
        const currentArticles = [...output.matchAll(/<article\b[^>]*>[\s\S]*?<\/article>/g)].filter(([block]) => block.includes('aria-current="step"'));
        assert.equal(currentArticles.length, 1); assert.match(currentArticles[0][0], /data-phase="open"/);
        assert.match(output, /장전 기록/);
    } finally { run.close(); }
});
test('historical trading date marks all three cards past independently of selected phase', async () => {
    const run = lifecycle(); try {
        await boot(run, day(), index([date, '2026-10-02']), '11:00:00');
        run.selectDate('2026-10-02'); run.render(); run.flush();
        const older = JSON.parse(JSON.stringify(day()).replaceAll(date, '2026-10-02'));
        run.request('/2026-10-02.json').resolve(older); await settle(); run.render(); run.flush();
        assert.deepEqual(temporalStates(run.render()), { pre: 'past', open: 'past', post: 'past' });
        run.expand('open'); const output = run.render(); assert.deepEqual(temporalStates(output), { pre: 'past', open: 'past', post: 'past' });
        assert.doesNotMatch(output, /aria-current="step"/);
    } finally { run.close(); }
});
test('expired internet time keeps phase relations unknown rather than asserting a current card', async () => {
    const run = lifecycle(); try {
        await boot(run, day(), index(), '11:00:00'); run.tick(15 * 60000); run.tick(15000);
        const output = run.render(); assert.match(output, /시각 확인 중/);
        assert.deepEqual(temporalStates(output), { pre: 'unknown', open: 'unknown', post: 'unknown' });
        assert.doesNotMatch(output, /data-time-state="current"|aria-current="step"/);
    } finally { run.close(); }
});
test('session time labels honor 09:00/15:30 boundaries, future ceiling and elapsed floor', () => {
    for (const [time, expected] of [
        ['07:30:00', '개장 1시간 30분 전'], ['08:58:01', '개장 2분 전'], ['08:59:59', '개장 1분 미만 전'],
        ['09:00:00', '장 마감 6시간 30분 전'], ['11:00:00', '장 마감 4시간 30분 전'], ['15:29:59', '장 마감 1분 미만 전'],
        ['15:30:00', '장 마감 1분 미만 경과'], ['15:30:59', '장 마감 1분 미만 경과'], ['15:31:59', '장 마감 1분 경과'], ['16:30:00', '장 마감 1시간 경과'],
    ]) assert.equal(mod.sessionTimeLabel(at(time), 'open', calendar), expected, time);
    for (const epoch of [null, NaN, Infinity]) assert.equal(mod.sessionTimeLabel(epoch, 'open', calendar), '시각 확인 중');
});
test('closed session counts down only through verified holiday/calendar coverage', () => {
    const sunday = Date.parse('2026-10-04T07:00:00+09:00');
    const known = { ...calendar, holidays: [], unknown_dates: [] };
    assert.equal(mod.sessionTimeLabel(sunday, 'closed', known), '다음 개장 1일 2시간 전');
    assert.equal(mod.sessionTimeLabel(sunday, 'closed', { ...known, holidays: ['2026-10-05'] }), '다음 개장 2일 2시간 전');
    for (const incomplete of [{ ...known, valid_until: '2026-10-04' }, { ...known, holidays: ['2026-10-05'], unknown_dates: ['2026-10-06'] }])
        assert.equal(mod.sessionTimeLabel(sunday, 'closed', incomplete), '다음 개장 일정 확인 중');
    assert.equal(mod.sessionTimeLabel(sunday, 'closed', undefined), '장 일정 확인 중');
    assert.equal(mod.sessionTimeLabel(at('11:00:00'), 'unknown', calendar), '장 일정 확인 중');
    assert.equal(mod.sessionTimeLabel(at('11:00:00'), 'open', undefined), '장 일정 확인 중');
    assert.equal(mod.sessionTimeLabel(at('11:00:00'), 'closed', known), '장 일정 확인 중');
});
test('only current card has countdown; historical dates and expired clock remove countdown', async () => {
    const run = lifecycle(); try {
        const output = await boot(run, day(), index([date, '2026-10-02']), '11:00:00');
        const articles = [...output.matchAll(/<article\b[^>]*>[\s\S]*?<\/article>/g)];
        const countdownCards = articles.filter(([block]) => block.includes('asb-countdown'));
        assert.equal(countdownCards.length, 1); assert.match(countdownCards[0][0], /data-phase="open"/); assert.match(countdownCards[0][0], /장 마감 4시간 30분 전/); assert.match(output, /11:00 KST/);
        run.expand('pre'); assert.equal((run.render().match(/class="asb-countdown"/g) || []).length, 1);
        run.selectDate('2026-10-02'); run.render(); run.flush();
        run.request('/2026-10-02.json').resolve(JSON.parse(JSON.stringify(day()).replaceAll(date, '2026-10-02'))); await settle();
        assert.doesNotMatch(run.render(), /asb-countdown/);
        run.selectDate(date); run.render(); run.flush(); run.request(`/${date}.json`).resolve(day()); await settle(); run.render();
        run.tick(15 * 60000); run.tick(15000); const expired = run.render(); assert.doesNotMatch(expired, /asb-countdown|asb-clock/); assert.match(expired, /시각 확인 중/);
    } finally { run.close(); }
});
test('one detail is adjacent to its reading card; switching and closing preserve current emphasis', async () => {
    const run = lifecycle(); try {
        await boot(run, day(), index(), '11:00:00');
        for (const phase of ['pre', 'open']) {
            run.expand(phase); const output = run.render(), children = run.trackChildren();
            const selected = children.findIndex(n => n.type === 'article' && n.props['data-phase'] === phase);
            assert.equal(children[selected]?.props['data-expanded'], true); assert.match(children[selected + 1]?.props.className || '', /\basb-detail\b/);
            assert.equal(children.filter(n => /\basb-detail\b/.test(n.props?.className || '')).length, 1);
            assert.equal(children.filter(n => n.type === 'article' && n.props['data-expanded'] === true).length, 1);
            assert.match(output, /class="asb-track"[^>]*data-expanded="true"/);
            assert.deepEqual(temporalStates(output), { pre: 'past', open: 'current', post: 'future' });
        }
        run.collapseDetail(); const closed = run.render(); assert.doesNotMatch(closed, /class="asb-detail"/);
        assert(run.trackChildren().every(n => n.props['data-expanded'] !== true));
        assert.deepEqual(temporalStates(closed), { pre: 'past', open: 'current', post: 'future' });
    } finally { run.close(); }
});

const krIndex = () => fact('kr', '코스피 +1.95% · 코스닥 +4.48%', '2026-10-01', { category: 'market_recap', name: '지수', title: '지수', country: 'KR' });
const usIndex = () => fact('us', 'S&P500 +0.73% · 나스닥 +1.19%', '', { category: 'market_recap', name: '미국 지수', title: '미국 지수', country: 'US', index_meta: {
    sp500: { source: 'fred', as_of: '2026-10-04T21:32:23+09:00' },
    nasdaq: { source: 'fred', as_of: '2026-10-04T21:32:24+09:00' },
    sox: { source: 'yfinance', as_of: '2026-10-04T21:32:25+09:00', data_date: '2026-10-02' },
} });
test('compact summaries keep the KR/US pair and a held company without changing legacy fallback', () => {
    const held = fact('held-a', '보유 정보 A', date, { ticker: '000660' }), second = fact('held-b', '보유 정보 B', date, { ticker: '000660' });
    const other = fact('other-company', '다른 기업', date, { ticker: '005930' }), broad = fact('breadth', '시장 흐름', date, { category: 'market_recap', name: '흐름' });
    const rows = [broad, held, other, second, krIndex(), usIndex()];
    const original = JSON.stringify(rows);
    assert.deepEqual(Array.from(mod.compactItems(rows, [], false), i => i.id), ['kr', 'us']);
    assert.deepEqual(Array.from(mod.compactItems(rows, ['000660'], true), i => i.id), ['held-a', 'kr', 'us']);
    assert.deepEqual(Array.from(mod.compactItems(rows, ['MSFT'], true), i => i.id), ['kr', 'us']);
    assert.deepEqual(Array.from(mod.compactItems(rows.slice(0, -1), [], false), i => i.id), ['breadth', 'held-a']);
    assert.deepEqual(Array.from(mod.compactItems(rows.slice(0, -1), ['000660'], true), i => i.id), ['held-a', 'breadth']);
    assert.equal(JSON.stringify(rows), original);
});
test('country flags recognize the actual index contract and never replace company logos', () => {
    assert.equal(mod.marketIndexCountry(krIndex()), 'KR'); assert.equal(mod.marketIndexCountry(usIndex()), 'US');
    assert.equal(mod.marketIndexCountry({ ...krIndex(), country: undefined }), 'KR');
    for (const item of [fact('news', '미국 뉴스', date, { country: 'US' }), { ...usIndex(), name: '흐름' }, { ...krIndex(), title: '다른 시장 정보' }, { ...krIndex(), country: 'unknown' }, { ...usIndex(), ticker: 'MSFT' }]) assert.equal(mod.marketIndexCountry(item), null);
    assert.match(html(mod.Fact, { item: krIndex() }), /circle-flags\/flags\/kr\.svg/);
    assert.match(html(mod.Fact, { item: usIndex() }), /circle-flags\/flags\/us\.svg/);
    const company = html(mod.Fact, { item: { ...usIndex(), ticker: 'MSFT', name: 'Microsoft' } });
    assert.match(company, /securities\/icn-sec-fill-MSFT\.png/); assert.doesNotMatch(company, /circle-flags/);
    for (const [name, cls] of [['올린 쪽', 'rising'], ['내린 쪽', 'falling']]) {
        const row = html(mod.Fact, { item: fact(name, '섹터 등락 자료', date, { category: 'market_recap', name }) });
        assert.match(row, new RegExp('asb-direction-' + cls)); assert.doesNotMatch(row, /circle-flags|asb-logo/);
    }
});
test('US collection time is distinct from actual data date on compact and detailed facts', () => {
    const detailed = html(mod.Fact, { item: usIndex() });
    assert.match(detailed, /S&amp;P500 · 자료 기준일 미제공 · 수집/);
    assert.match(detailed, /SOX · 자료 기준 2026-10-02 · 수집/);
    assert.doesNotMatch(detailed, /종가 기준 2026-10-04|자료 기준 2026-10-04/);
    const compact = html(mod.Fact, { item: usIndex(), compact: true });
    assert.match(compact, /미국 지수 자료 · 기준일 일부 미제공/); assert.match(compact, /SOX 2026-10-02/); assert.match(compact, /수집/);
    const missing = html(mod.Fact, { item: { ...usIndex(), index_meta: undefined } });
    assert.match(missing, /자료 기준일 미제공/);
});
test('KR view separates US records while desktop depth and full detail preserve facts and holdings privacy', async () => {
    for (const personal of [false, true]) {
        const record = day(); record.snapshots[0].items.push(krIndex(), fact('held-extra', '보유 기업 추가 공시', date, { ticker: '000660' }));
        record.snapshots[1].items.push(krIndex(), usIndex(), fact('held-open', '장중 보유 공시', date, { ticker: '000660' }), fact('held-open-extra', '장중 보유 추가 공시', date, { ticker: '000660' }));
        const run = lifecycle({ holdingsTickers: ['000660'], personalizationState: personal ? 'holdings' : 'market' });
        try {
            const output = await boot(run, record, index(), '11:00:00');
            const pre = output.match(/<article\b[^>]*data-phase="pre"[\s\S]*?<\/article>/)[0], open = output.match(/<article\b[^>]*data-phase="open"[\s\S]*?<\/article>/)[0];
            assert.doesNotMatch(pre, /미국 지수|S&amp;P500/);
            assert.match(open, /data-fact-count="4"/); assert.match(open, /국내 지수/); assert.doesNotMatch(open, /미국 지수/);
            if (personal) assert.match(open, /장중 보유 공시/);
            run.expand('open'); const detail = run.render().match(/<div class="asb-detail"[\s\S]*?<p class="asb-note">/)[0];
            for (const text of ['장중 원문 사실', '장중 보유 공시', '장중 보유 추가 공시', '국내 지수']) assert(detail.includes(text), text);
            assert.doesNotMatch(detail, /미국 지수/);
            assert.doesNotMatch(JSON.stringify(run.requests.map(r => ({ url: r.url, options: r.options }))), /000660|Authorization|holdings|shares|avg_cost/);
        } finally { run.close(); }
    }
});

const usCalendar = { valid_from: '2026-01-01', valid_until: '2026-12-31', timezone: 'America/New_York', holidays: ['2026-11-26', '2026-12-25'], open_minute: 570, close_minute: 960, early_closes: { '2026-11-27': 780, '2026-12-24': 780 } };
test('US sessions use New York trading dates, DST and verified early closes', () => {
    for (const [stamp, phase] of [
        ['2026-10-06T13:29:59Z', 'pre'], ['2026-10-06T13:30:00Z', 'open'], ['2026-10-06T20:00:00Z', 'post'],
        ['2026-11-02T14:29:59Z', 'pre'], ['2026-11-02T14:30:00Z', 'open'], ['2026-11-02T21:00:00Z', 'post'],
        ['2026-11-27T17:59:59Z', 'open'], ['2026-11-27T18:00:00Z', 'post'],
    ]) assert.equal(mod.activePhase(Date.parse(stamp), 'open', usCalendar), phase, stamp);
    const crossMidnight = Date.parse('2026-10-06T15:05:00Z');
    assert.equal(mod.marketDate(crossMidnight, 'America/New_York'), '2026-10-06');
    assert.equal(mod.kstDate(crossMidnight), '2026-10-07');
    assert.equal(mod.tradingStatus('2026-11-26', usCalendar), 'closed');
    assert.equal(mod.tradingStatus('2027-01-04', usCalendar), 'unknown');
    assert.equal(mod.sessionTimeLabel(Date.parse('2026-11-27T17:00:00Z'), 'open', usCalendar), '장 마감 1시간 전');
    assert.equal(mod.sessionTimeLabel(Date.parse('2026-10-31T05:00:00Z'), 'closed', usCalendar), '다음 개장 2일 9시간 30분 전');
});
test('US normalization preserves source dates and rejects unverified calendar payloads', () => {
    const record = { ...day(), timezone: 'America/New_York', date: '2026-10-06', snapshots: [{ snapshot_id: 'open-1', phase: 'open', generated_at: '2026-10-06T11:05:00-04:00', items: [usIndex()] }], cards: { open: 'open-1' } };
    assert.equal(mod.normalizeDay(record, record.date, usCalendar), record);
    assert.throws(() => mod.normalizeDay(record, record.date, calendar));
    assert.equal(record.snapshots[0].items[0].index_meta.sox.data_date, '2026-10-02');
    for (const bad of [{ ...usCalendar, timezone: 'bad-zone' }, { ...usCalendar, early_closes: { '2026-11-27': 500 } }]) assert.throws(() => mod.normalizeIndex(index([], bad)));
});
test('each market keeps its own facts and desktop adds depth without changing the mobile summary', () => {
    const rows = [fact('held', '보유 기업', date, { ticker: '000660' }), fact('other', '다른 기업', date, { ticker: '005930' }), krIndex(), fact('breadth', '시장 흐름', date, { category: 'market_recap' }), usIndex(), fact('us-filing', '미국 공시', date, { category: 'us_filings', ticker: 'MSFT' })];
    rows.push(fact('held-extra', '보유 기업 추가 공시', date, { ticker: '000660' }));
    const before = JSON.stringify(rows), kr = mod.marketItems(rows, 'KR'), us = mod.marketItems(rows, 'US');
    assert.deepEqual(Array.from(us, item => item.id), ['us', 'us-filing']);
    const packed = mod.cardItems(kr, ['000660'], true);
    assert.deepEqual(Array.from(packed.summary, item => item.id), ['held', 'kr']);
    assert.equal(packed.desktop.length, 4); assert.equal(JSON.stringify(rows), before);
    assert.match(mod.CSS, /@container\(max-width:680px\)\{\.asb-card-body \.asb-desktop-extra\{display:none\}/);
});
test('switching markets clears old facts, uses separate archive paths and rejects a KR index in US', async () => {
    const run = lifecycle({ holdingsTickers: ['000660'], personalizationState: 'holdings' });
    try {
        assert.match(await boot(run, day(), index(), '11:00:00'), /매출 120억원/);
        run.selectMarket('US'); assert.doesNotMatch(run.render(), /매출 120억원/); run.flush();
        const first = run.request('/us/index.json'); assert(first); first.resolve(index()); await settle(); run.render(); run.flush();
        assert.match(run.render(), /기록을 불러오지 못했어요/); assert.equal(run.request('/us/2026-10-04.json'), undefined);
        run.event('focus'); run.render(); run.flush();
        run.request('/us/index.json').resolve(index(['2026-10-04'], usCalendar)); await settle(); run.render(); run.flush();
        const us = { schema_version: 1, timezone: 'America/New_York', date: '2026-10-04', trading_day: { status: 'closed' }, snapshots: [{ snapshot_id: 'closed', phase: 'closed', generated_at: '2026-10-04T21:00:00-04:00', items: [usIndex()] }], cards: { closed: 'closed' } };
        run.request('/us/2026-10-04.json').resolve(us); await settle(); const output = run.render();
        assert.match(output, /미국 지수|S&amp;P500/); assert.match(output, /미국 거래일 · ET/); assert.doesNotMatch(output, /매출 120억원/);
        run.selectMarket('KR'); assert.doesNotMatch(run.render(), /S&amp;P500/); run.flush();
        assert(run.request('/index.json')); assert.doesNotMatch(JSON.stringify(run.requests.map(r => ({ url: r.url, options: r.options }))), /000660|Authorization|holdings|shares|avg_cost/);
    } finally { run.close(); }
});

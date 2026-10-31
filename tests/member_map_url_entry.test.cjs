// Exact delivered receiver + synthetic workspace/frame. No real account/storage/network.
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '..')
const source = fs.readFileSync(path.join(root, 'review/member-map/Map.snapshot.tsx'), 'utf8')
const start = source.indexOf('// framer-components/public-probe/PortfolioMapData.tsx')
const end = source.indexOf('// framer-components/public-probe/PortfolioHoldingsPanel.tsx', start)
assert.ok(start > 0 && end > start)
const receiver = source.slice(start, end) + '\nglobalThis.api={parsePortfolioMapEntry,portfolioMapEntryPath,createPortfolioMapWorkspace,mountMemberPrototype}'
const clone = value => JSON.parse(JSON.stringify(value))
const tick = () => new Promise(resolve => setImmediate(resolve))
const A = { userId: '11111111-1111-4111-8111-111111111111', token: 'synthetic-a' }
const B = { userId: '22222222-2222-4222-8222-222222222222', token: 'synthetic-b' }
const saved = { layouts: [{ map_key: 'main_v2', positions: [
    { node_id: 'company:NVDA', x: 420, y: -51 }, { node_id: 'hidden', x: -70, y: 900 },
], notes: [{ note_id: 'note-1', anchor: null, x: 51, y: -42, text: 'synthetic memo', done: false }],
marks: { hidden: { read_revision: 9, important: true, disposition: 'later' } } }] }
const graph = codes => ({ companies: codes.map(ticker => ({ id: 'company:' + ticker, ticker, name: ticker, market: /^\d/.test(ticker) ? 'KR' : 'US' })), documents: [], links: [], commonItems: [] })
function moduleContext(extra = {}) {
    const context = { AbortController, URL, URLSearchParams, Response, TextDecoder, DOMException, setTimeout, clearTimeout, ...extra }
    vm.runInNewContext(receiver, context)
    return context
}
const api = moduleContext().api

test('URL identity accepts explicit KR/US only and canonicalizes only the validated pair', () => {
    for (const [query, expected] of [
        ['?ticker=005930&market=KR', { ticker: '005930', market: 'KR' }],
        ['?market=US&ticker=brk.b&unused=ignored', { ticker: 'BRK.B', market: 'US' }],
        ['?ticker=BRK-B&market=US', { ticker: 'BRK-B', market: 'US' }],
    ]) {
        assert.deepEqual(clone(api.parsePortfolioMapEntry(query)), expected)
        assert.equal(api.portfolioMapEntryPath(query), '/member-map-review?' + new URLSearchParams(expected))
    }
    for (const query of ['', '?ticker=NVDA', '?market=US', '?ticker=NVDA&market=us',
        '?ticker=005930&market=US', '?ticker=NVDA&market=KR', '?ticker=NVDA&market=NASDAQ',
        '?ticker=NVDA&ticker=NVDA&market=US', '?ticker=NVDA&market=US&market=US',
        '?ticker=%20NVDA&market=US', '?ticker=NVDA%0a&market=US', '?ticker=NVDA%00&market=US',
        '?ticker=../NVDA&market=US', '?ticker=NVDA%26x=1&market=US', '?ticker=A..B&market=US',
        '?ticker=ABCDEFGHIJK&market=US', '?' + 'x'.repeat(2049)]) {
        assert.equal(api.parsePortfolioMapEntry(query), null, query)
        assert.equal(api.portfolioMapEntryPath(query), '/member-map-review')
    }
})

test('login shell uses the validated return path for both OAuth and email login', () => {
    const entry = fs.readFileSync(path.join(root, 'review/member-map/entry.tsx'), 'utf8')
    const config = entry.slice(entry.indexOf('const RETURN_PATH'), entry.indexOf('function Review'))
    const auth = fs.readFileSync(path.join(root, 'review/member-map/Auth.snapshot.tsx'), 'utf8')
    const { createRequire } = require('node:module')
    const dependencyRoot = process.env.MEMBER_MAP_TEST_DEPENDENCY_ROOT || root
    const esbuild = createRequire(path.join(dependencyRoot, 'package.json'))('esbuild')
    const resolver = auth.slice(auth.indexOf('function resolveNext('), auth.indexOf('// 이메일 회원가입'))
    const compiled = esbuild.transformSync(resolver, { loader: 'ts' }).code
    for (const query of ['?ticker=005930&market=KR', '?ticker=brk.b&market=US&private=not-forwarded', '?ticker=NVDA&market=KR']) {
        const context = { URL, URLSearchParams, portfolioMapEntryPath: api.portfolioMapEntryPath,
            window: { location: { search: query, origin: 'https://project-yw131.vercel.app' } } }
        vm.runInNewContext(config + compiled + '\nglobalThis.result={url:RETURN_URL,path:RETURN_PATH,next:resolveNext(RETURN_PATH)}', context)
        const expected = api.portfolioMapEntryPath(query)
        assert.deepEqual(clone(context.result), { url: 'https://project-yw131.vercel.app' + expected, path: expected, next: expected })
        assert.doesNotMatch(context.result.url, /private|not-forwarded/)
    }
    assert.match(entry, /redirectUrl=\{RETURN_URL\} afterLoginPath=\{RETURN_PATH\}/)
    assert.match(source, /entryStock: parsePortfolioMapEntry\(window\.location\.search\)/)
})

async function harness(t, options = {}) {
    let session = A, loader = async codes => graph(codes), subscriber
    const calls = [], messages = [], listeners = {}, channels = []
    const context = moduleContext({
        window: { location: { href: 'https://fixture.test/member-map-review', origin: 'https://fixture.test' },
            addEventListener: (type, fn) => { listeners[type] = fn }, removeEventListener: type => { delete listeners[type] } },
        crypto: { randomUUID: () => 'synthetic-nonce' },
        MessageChannel: class { constructor() {
            this.port1 = { postMessage: data => messages.push(clone(data)), close() {} };this.port2 = {};channels.push(this)
        } },
    })
    const workspace = context.api.createPortfolioMapWorkspace({ getSession: () => session,
        graphLoader: codes => loader(codes), fetcher: async (url, init = {}) => {
            calls.push({ url, method: init.method || 'GET' });assert.equal(init.method || 'GET', 'GET')
            const body = url.endsWith('/holdings') ? options.holdings || [{ ticker: 'NVDA', name: 'NVIDIA', market: 'us' }]
                : { revision: 8, document: clone(saved) }
            return { ok: true, json: async () => body }
        } })
    await workspace.open()
    workspace.editLayout('main_v2', layout => ({ ...layout, notes: layout.notes.map(note => ({ ...note, text: 'unsaved synthetic memo' })) }))
    const before = clone(workspace.getState())
    const frame = { style: {}, contentWindow: { postMessage() {} }, setAttribute() {}, removeAttribute() {}, addEventListener() {}, removeEventListener() {} }
    // State masking only tests the independent private-restore gate; real workspace
    // remains the owner of the data and all exploration/state mutation behavior.
    let privateLoading = options.privateLoading === true
    const viewState = value => privateLoading ? { ...value, privateState: { ...value.privateState, phase: 'loading' } } : value
    const hostWorkspace = { ...workspace, getState: () => viewState(workspace.getState()),
        subscribe: fn => { subscriber = fn;return workspace.subscribe(value => fn(viewState(value))) } }
    const bridge = context.api.mountMemberPrototype(frame, "'__ALPHANEST_FRAME_NONCE__'", hostWorkspace,
        { account: () => session?.userId || null, entryStock: { ticker: 'INTC', market: 'US' }, ...options })
    const connect = () => {
        listeners.message({ source: frame.contentWindow, origin: 'null', data: { type: 'alphanest-member-ready', nonce: JSON.parse(frame.srcdoc) } })
        return channels.at(-1).port1
    }
    const hydrate = port => port.onmessage({ data: { type: 'hydrated', originGeneration: messages.findLast(m => m.type === 'init').model.originGeneration } })
    const ack = (port, generation = messages.findLast(m => m.type === 'graph-update').model.originGeneration) => port.onmessage({ data: { type: 'graph-applied', originGeneration: generation } })
    t.after(() => { bridge();workspace.dispose() })
    return { workspace, messages, calls, before, connect, hydrate, ack, retire: bridge,
        loader: fn => { loader = fn }, owner: value => { session = value },
        restore: () => { privateLoading = false;subscriber(workspace.getState()) },
        focus: () => messages.filter(m => m.type === 'focus-stock'),
        unchanged: () => {
            const after = clone(workspace.getState())
            assert.deepEqual(after.privateState, before.privateState)
            assert.deepEqual(after.holdings, before.holdings)
            assert.deepEqual(after.watchlist, before.watchlist)
            assert.ok(calls.every(call => call.method === 'GET'))
        } }
}

test('new URL stock waits for hydration and fresh graph ACK; draft/manual positions survive exactly', async t => {
    let searches = 0
    const h = await harness(t, { searchLoader: async (query, { signal }) => {
        searches++;assert.equal(query, 'INTC');assert.equal(signal.aborted, false)
        return { stocks: [{ ticker: 'INTC', name: 'Intel', market: 'US' }] }
    } })
    const port = h.connect()
    await tick();assert.equal(searches, 0)
    await h.hydrate(port);await tick()
    assert.equal(searches, 1);assert.equal(h.focus().length, 0)
    assert.deepEqual(clone(h.workspace.getState().selectedTickers), ['NVDA', 'INTC'])
    assert.deepEqual(clone(h.workspace.getState().exploratory), [{ ticker: 'INTC', name: 'Intel', market: 'US' }])
    assert.equal(h.messages.filter(m => m.type === 'init').length, 1, 'no frame replacement on exploration')
    h.unchanged()
    await h.ack(port, 0);assert.equal(h.focus().length, 0)
    await h.ack(port);assert.deepEqual(h.focus(), [{ type: 'focus-stock', id: 'company:INTC' }])
    await h.ack(port);await h.hydrate(port);await tick()
    assert.equal(searches, 1);assert.equal(h.focus().length, 1);h.unchanged()
})

test('existing URL stock focuses once without search or graph reload', async t => {
    const h = await harness(t, { entryStock: { ticker: 'NVDA', market: 'US' }, searchLoader: () => assert.fail('known stock search') })
    h.loader(() => assert.fail('known stock graph reload'))
    const port = h.connect();await h.hydrate(port);await tick()
    assert.deepEqual(h.focus(), [{ type: 'focus-stock', id: 'company:NVDA' }])
    assert.deepEqual(clone(h.workspace.getState()), h.before);h.unchanged()
})

test('URL entry waits for restored private state even after an early frame hydration', async t => {
    let searches = 0
    const h = await harness(t, { privateLoading: true, searchLoader: async () => { searches++;return { stocks: [] } } })
    const port = h.connect();await h.hydrate(port);await tick()
    assert.equal(searches, 0)
    h.restore()
    const restoredPort = h.connect();await h.hydrate(restoredPort);await tick()
    assert.equal(searches, 1);assert.equal(h.focus().length, 0);h.unchanged()
})

for (const outcome of ['not-found', 'market-mismatch', 'failure', 'graph-failure']) test(`URL ${outcome} leaves the complete original workspace unchanged`, async t => {
    let searches = 0
    const h = await harness(t, { searchLoader: async () => {
        searches++
        if (outcome === 'failure') throw Error('synthetic search unavailable')
        return { stocks: outcome === 'not-found' ? [] : [{ ticker: 'INTC', name: 'Intel', market: outcome === 'market-mismatch' ? 'KR' : 'US' }] }
    } })
    if (outcome === 'graph-failure') h.loader(async () => { throw Error('synthetic graph unavailable') })
    const port = h.connect();await h.hydrate(port);await tick();await h.hydrate(port);await tick()
    assert.equal(searches, 1);assert.equal(h.focus().length, 0)
    assert.deepEqual(clone(h.workspace.getState()), h.before);h.unchanged()
})

test('late URL search cannot explore or focus after owner change or teardown', async t => {
    for (const reason of ['owner', 'teardown']) {
        let resolve, signal
        const h = await harness(t, { searchLoader: (_q, options) => { signal = options.signal;return new Promise(done => { resolve = done }) } })
        const port = h.connect();await h.hydrate(port)
        if (reason === 'owner') { h.owner(B);await h.workspace.open() }
        else { h.retire() }
        resolve({ stocks: [{ ticker: 'INTC', name: 'Intel', market: 'US' }] });await tick()
        assert.equal(h.focus().length, 0)
        assert.deepEqual(clone(h.workspace.getState().exploratory), [])
        assert.equal(signal.aborted, true)
    }
})

test('thirty-stock limit does not evict saved working stocks to satisfy a URL', async t => {
    const holdings = Array.from({ length: 30 }, (_, index) => ({ ticker: 'S' + index, name: 'Stock ' + index, market: 'us' }))
    const h = await harness(t, { holdings, searchLoader: async () => ({ stocks: [{ ticker: 'INTC', name: 'Intel', market: 'US' }] }) })
    const port = h.connect();await h.hydrate(port);await tick()
    assert.equal(h.focus().length, 0);assert.deepEqual(clone(h.workspace.getState()), h.before);h.unchanged()
})

test('KR URL exploration works with an empty portfolio without registering holdings', async t => {
    const h = await harness(t, { holdings: [], entryStock: { ticker: '005930', market: 'KR' },
        searchLoader: async () => ({ stocks: [{ ticker: '005930', name: '삼성전자', market: 'KR' }] }) })
    const port = h.connect();await h.hydrate(port);await tick();await h.ack(port)
    assert.deepEqual(h.focus(), [{ type: 'focus-stock', id: 'company:005930' }])
    assert.deepEqual(clone(h.workspace.getState().holdings), []);h.unchanged()
})

test('invalid or absent entry never invokes exploration or changes the loaded workspace', async t => {
    for (const entryStock of [null, { ticker: '005930', market: 'US' }, { ticker: 'NVDA', market: 'KR' }]) {
        const h = await harness(t, { entryStock, searchLoader: () => assert.fail('invalid URL search') })
        h.loader(() => assert.fail('invalid URL graph load'))
        const port = h.connect();await h.hydrate(port);await tick()
        assert.equal(h.focus().length, 0);assert.deepEqual(clone(h.workspace.getState()), h.before);h.unchanged()
    }
})

test('late exploratory graph cannot publish after the active owner changes', async t => {
    let resolve
    const h = await harness(t, { searchLoader: async () => ({ stocks: [{ ticker: 'INTC', name: 'Intel', market: 'US' }] }) })
    h.loader(codes => new Promise(done => { resolve = () => done(graph(codes)) }))
    const port = h.connect();await h.hydrate(port);await tick()
    h.owner(B);h.workspace.getState();resolve();await tick()
    assert.equal(h.focus().length, 0)
    assert.deepEqual(clone(h.workspace.getState().exploratory), [])
    assert.equal(h.workspace.getState().graph, null)
})

test('a note edited during URL lookup remains the current unsaved draft after exploration', async t => {
    let resolve
    const h = await harness(t, { searchLoader: () => new Promise(done => { resolve = done }) })
    const port = h.connect();await h.hydrate(port)
    h.workspace.editLayout('main_v2', layout => ({ ...layout, notes: layout.notes.map(note => ({ ...note, text: 'newer unsaved text' })) }))
    const before = clone(h.workspace.getState().privateState)
    resolve({ stocks: [{ ticker: 'INTC', name: 'Intel', market: 'US' }] });await tick();await h.ack(port)
    assert.deepEqual(clone(h.workspace.getState().privateState), before)
    assert.equal(h.focus().length, 1);assert.ok(h.calls.every(call => call.method === 'GET'))
})

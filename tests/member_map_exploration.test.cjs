const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const source = fs.readFileSync(path.resolve(__dirname, '../review/member-map/Map.snapshot.tsx'), 'utf8')
const start = source.indexOf('// framer-components/public-probe/MemberMapState.tsx')
const end = source.indexOf('// framer-components/public-probe/PortfolioHoldingsPanel.tsx', start)
assert.ok(start >= 0 && end > start)
const context = { AbortController, URL, URLSearchParams, Response, TextDecoder, DOMException, setTimeout, clearTimeout }
vm.runInNewContext(source.slice(start, end) + '\nglobalThis.api={createPortfolioMapWorkspace,normalizeSearchResults,fetchPortfolioStockSearch,prototypeMemberModel}', context)
const { createPortfolioMapWorkspace, normalizeSearchResults, fetchPortfolioStockSearch, prototypeMemberModel } = context.api
const clone = value => JSON.parse(JSON.stringify(value))
const A = { userId: '11111111-1111-4111-8111-111111111111', token: 'synthetic-a' }
const B = { userId: '22222222-2222-4222-8222-222222222222', token: 'synthetic-b' }
const graph = tickers => ({ companies: tickers.map(ticker => ({ id: 'company:' + ticker, ticker, name: ticker, market: 'US' })), documents: [], links: [], commonItems: [] })
function harness(t) {
    let session = A, loader = async codes => graph(codes)
    const calls = []
    const workspace = createPortfolioMapWorkspace({ getSession: () => session,
        graphLoader: (codes, api, signal) => loader(codes, signal),
        fetcher: async (url, init = {}) => {
            calls.push({ url, init });assert.equal(init.method || 'GET', 'GET')
            const data = url.endsWith('/holdings') ? [{ id: 'holding-a', ticker: 'NVDA', name: 'NVIDIA', market: 'us', shares: 2, avg_cost: 10 }]
                : { revision: 1, document: { layouts: [{ map_key: 'main', positions: [], notes: [], marks: {} }] } }
            return { ok: true, json: async () => clone(data) }
        } })
    t.after(() => workspace.dispose())
    return { workspace, calls, owner: value => { session = value }, loader: value => { loader = value } }
}

test('delivered search normalizes actual exchange labels and explicit ETF metadata', () => {
    assert.deepEqual(clone(normalizeSearchResults([
        { ticker: '005930', name: '삼성전자', market: 'KOSPI' },
        { ticker: 'nvda', name: 'NVIDIA', name_kr: '엔비디아', market: 'NASDAQ', etf: false },
        { ticker: 'NVDO', name: 'NVDA ETF', market: 'BATS', etf: true },
    ])), { stocks: [{ ticker: '005930', name: '삼성전자', market: 'KR' }, { ticker: 'NVDA', name: '엔비디아', market: 'US' },
        { ticker: 'NVDO', name: 'NVDA ETF', market: 'US', etf: true }], unsupportedCount: 0 })
    assert.throws(() => normalizeSearchResults(Array(13).fill({})))
})

test('delivered search uses same-origin GET without session or cookies', async () => {
    const calls = []
    const result = await fetchPortfolioStockSearch(' 인텔 ', { fetcher: async (url, init) => {
        calls.push({ url, init });return new Response(JSON.stringify([{ ticker: 'INTC', name: 'Intel', market: 'NASDAQ' }]))
    } })
    assert.equal(result.stocks[0].ticker, 'INTC');assert.equal(calls.length, 1)
    const { url, init } = calls[0]
    assert.ok(url.startsWith('/api/search?'));assert.equal(new URL(url, 'https://fixture.invalid').searchParams.get('q'), '인텔')
    assert.equal(init.method, 'GET');assert.equal(init.credentials, 'omit');assert.equal(init.redirect, 'error');assert.equal(init.headers, undefined)
    await assert.rejects(fetchPortfolioStockSearch('NVDA', { api: 'https://foreign.invalid/search' }))
})

test('delivered exploration joins a verified common event without changing holdings or writing membership', async t => {
    const h = harness(t);await h.workspace.open()
    const before = h.workspace.getState(), calls = h.calls.length
    assert.equal(await h.workspace.exploreStock({ ticker: 'INTC', name: 'Intel', market: 'US' }), true)
    const after = h.workspace.getState(), model = prototypeMemberModel(after)
    assert.deepEqual(clone(after.holdings), clone(before.holdings));assert.equal(h.calls.length, calls)
    const stock = model.nodes.find(n => n.ticker === 'INTC')
    assert.equal(stock.explore, true);assert.equal(stock.held, false);assert.equal(stock.watched, false)
    const event = model.nodes.find(n => n.recordKind === 'event')
    assert.ok(event);assert.equal(event.name, 'NVIDIA·Intel 제품 공동개발 발표');assert.equal(event.evidence.length, 2)
    assert.equal(model.edges.filter(e => e.from === event.id).length, 2)
    assert.deepEqual(clone(after.privateState), clone(before.privateState))
})

test('delivered exploration failure and late owner response leave no foreign graph', async t => {
    const h = harness(t);await h.workspace.open();const before = clone(h.workspace.getState())
    h.loader(async () => { throw Error('unavailable') })
    assert.equal(await h.workspace.exploreStock({ ticker: 'INTC', name: 'Intel', market: 'US' }), false)
    assert.deepEqual(clone(h.workspace.getState()), before)
    let resolve
    h.loader(codes => new Promise(done => { resolve = () => done(graph(codes)) }))
    const pending = h.workspace.exploreStock({ ticker: 'INTC', name: 'Intel', market: 'US' })
    h.owner(B);resolve();assert.equal(await pending, false)
    assert.equal(h.workspace.getState().graph, null);assert.deepEqual(clone(h.workspace.getState().exploratory), [])
})

test('delivered canvas counts visible exploration in shared connections, not hidden stocks', () => {
    const html = fs.readFileSync(path.resolve(__dirname, '../vercel-api/public/member-map-canvas.html'), 'utf8')
    const counter = html.match(/^eventHoldings=n=>.*;$/m)?.[0]
    assert.ok(counter, 'actual runtime overrides fixture-only counting')
    const scope = { eventHoldings: null, nodeById: { held: { kind: 'stock' }, explore: { kind: 'stock', explore: true }, hidden: { kind: 'stock', hidden: true } },
        edges: ['held', 'explore', 'hidden'].map(to => ({ from: 'event', to })), inScenario: value => !value.hidden }
    vm.runInNewContext(counter, scope)
    assert.deepEqual(clone(scope.eventHoldings({ id: 'event' })), ['held', 'explore'])
    assert.ok(html.includes('appendMemberNode(data)'))
    assert.ok(html.includes("pair.group.remove();edgeEls.delete(id)"))
    assert.ok(html.includes("이번 화면에서만 탐색해요. 보유·관심목록에 등록하지 않았어요."))
})

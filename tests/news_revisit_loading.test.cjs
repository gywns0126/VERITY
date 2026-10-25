const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { transformSync } = require('esbuild')

const source = fs.readFileSync(path.resolve(__dirname, '../framer-components/public-probe/PublicNewsTab.tsx'), 'utf8')
assert.doesNotThrow(() => transformSync(source, { loader: 'tsx' }), 'patched component transpiles')
const helper = source.slice(source.indexOf('const stockNewsInFlight'), source.indexOf('function asArray'))
const effectStart = source.indexOf('    useEffect(() => {\n        if (onCanvas || !krKey) return')
const effect = source.slice(effectStart, source.indexOf('    const tabs:', effectStart))
assert.ok(helper.includes('function loadStockNews') && effect.includes('loadStockNews'), 'news loader source anchors')
const runtimeCode = transformSync(`${helper}\nfunction registerNewsEffect() { ${effect} }\nglobalThis.registerNewsEffect = registerNewsEffect`, { loader: 'tsx' }).code
const settle = () => new Promise(resolve => setImmediate(resolve))

function harness(initial = {}) {
    const requests = []
    const state = { news: initial }
    let registered
    const box = vm.createContext({
        Map, Promise, encodeURIComponent, onCanvas: false,
        props: { apiBase: 'https://fixture.invalid/' },
        krKey: '005930,000660', newsAudienceVersion: 0,
        newsAudienceToken: { current: 'member-A' },
        useEffect: fn => { registered = fn },
        setNaverNews: update => { state.news = typeof update === 'function' ? update(state.news) : update },
        fetch: (url, options) => new Promise((resolve, reject) => requests.push({ url: String(url), options, resolve, reject })),
    })
    vm.runInContext(runtimeCode, box)
    const start = () => { box.registerNewsEffect(); return registered() }
    return { box, requests, state, start }
}
const reply = items => ({ ok: true, json: async () => ({ items }) })
const item = title => ({ title, url: 'https://example.com/' + title, source: 'fixture', rel_time: '방금' })

test('overlapping mounts share in-flight requests and each successful ticker appears immediately', async () => {
    const h = harness()
    const closeA = h.start(), closeB = h.start()
    assert.equal(h.requests.length, 2)
    assert(h.requests.every(request => request.options.cache === 'no-store'))
    h.requests[0].resolve(reply([item('first')]))
    await settle()
    assert.equal(h.state.news['005930'][0].title, 'first')
    assert.equal(h.state.news['000660'], undefined, 'slow ticker does not hold the first result')
    h.requests[1].resolve(reply([item('second')]))
    await settle()
    assert.equal(h.state.news['000660'][0].title, 'second')
    closeA(); closeB()
    const closeRevisit = h.start()
    assert.equal(h.requests.length, 4, 'settled responses are not retained as a new TTL cache')
    closeRevisit()
    h.requests[2].resolve(reply([])); h.requests[3].resolve(reply([]))
    await settle()
})

test('empty, malformed and failed responses preserve the previous successful source', async () => {
    const h = harness({ '005930': [item('kept')] })
    const close = h.start()
    h.requests[0].resolve(reply([]))
    h.requests[1].reject(new Error('offline'))
    await settle()
    assert.equal(h.state.news['005930'][0].title, 'kept')
    assert.equal(h.state.news['000660'], undefined)
    close()
    const again = h.start()
    assert.equal(h.requests.length, 4, 'failure removes the shared in-flight entry for a fresh retry')
    h.requests[2].resolve({ ok: true, json: async () => ({ error: 'bad' }) })
    h.requests[3].resolve({ ok: false, json: async () => ({ items: [item('wrong')] }) })
    await settle()
    assert.equal(h.state.news['005930'][0].title, 'kept')
    assert.equal(h.state.news['000660'], undefined)
    again()
})

test('unmount and explicit audience change reject late writes, including a shared request', async () => {
    const h = harness()
    const old = h.start()
    h.box.newsAudienceToken.current = 'member-B'
    h.state.news = {}
    const current = h.start()
    assert.equal(h.requests.length, 2, 'new audience may share public ticker transport in flight')
    h.requests[0].resolve(reply([item('new-account')]))
    await settle()
    assert.equal(h.state.news['005930'][0].title, 'new-account')
    old(); current()
    h.requests[1].resolve(reply([item('late')]))
    await settle()
    assert.equal(h.state.news['000660'], undefined)
})

test('same identity retains watch during revalidation; token switch clears it before the next response', async () => {
    const start = source.indexOf('    /* 내 종목 source contract')
    const end = source.indexOf('    /* 데이터 로드', start)
    assert(start >= 0 && end > start)
    const code = transformSync(`function registerPersonalEffect() { ${source.slice(start, end)} }\nglobalThis.registerPersonalEffect = registerPersonalEffect`, { loader: 'tsx' }).code
    const listeners = new Map()
    const requests = []
    const writes = []
    const state = { watch: [], news: { '005930': [item('old')] }, token: 'member-A' }
    let effect
    const box = vm.createContext({
        onCanvas: false, props: { apiBase: 'https://fixture.invalid/' },
        newsAudienceToken: { current: '' },
        AbortController,
        useEffect: fn => { effect = fn },
        setWatch: value => { state.watch = value; writes.push(['watch', value]) },
        setNaverNews: value => { state.news = value; writes.push(['news', value]) },
        setNewsAudienceVersion: () => {},
        setPersonalError: () => {}, setPersonalLoading: () => {}, setMemberMode: () => {},
        localStorage: {
            getItem: key => key === 'verity_supabase_session' ? JSON.stringify({ access_token: state.token }) : null,
            setItem: () => { throw new Error('auth/storage write') },
        },
        currentHoldingStocks: holdings => holdings,
        fetch: (url, options) => new Promise(resolve => requests.push({ url: String(url), options, resolve })),
        window: { addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name) },
    })
    vm.runInContext(code, box)
    box.registerPersonalEffect()
    const close = effect()
    assert.equal(requests.length, 1)
    requests[0].resolve({ ok: true, json: async () => [{ ticker: '005930', held: true }] })
    await settle()
    assert.equal(state.watch[0].ticker, '005930')
    const before = writes.length
    listeners.get('focus')()
    assert.equal(requests.length, 2)
    assert.equal(writes.slice(before).filter(([kind]) => kind === 'watch').length, 0, 'same account does not blank the list while holdings reload')
    assert.equal(state.watch[0].ticker, '005930')
    state.token = 'member-B'
    listeners.get('verity_auth_change')()
    assert.equal(requests.length, 3)
    assert.equal(state.watch.length, 0, 'account switch clears the previous holdings immediately')
    assert.equal(Object.keys(state.news).length, 0, 'account switch clears prior ticker news immediately')
    requests[1].resolve({ ok: true, json: async () => [{ ticker: 'OLD' }] })
    await settle()
    assert.equal(state.watch.length, 0, 'older generation cannot repopulate after switch')
    requests[2].resolve({ ok: true, json: async () => [{ ticker: 'NEW' }] })
    await settle()
    assert.equal(state.watch[0].ticker, 'NEW')
    close()
})

const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const test = require("node:test")
const vm = require("node:vm")

// Execute the delivered JS segments, not source imports or a second transpilation.
const source = fs.readFileSync(path.resolve(__dirname, "../review/member-map/Map.snapshot.tsx"), "utf8")
const start = source.indexOf("// framer-components/public-probe/MemberMapState.tsx")
const end = source.indexOf("// framer-components/public-probe/PortfolioPrototypeHost.ts", start)
assert.ok(start >= 0 && end > start, "generated member/workspace/reviewed segments exist")
const context = { AbortController, URL, JSON, Error, setTimeout, clearTimeout }
vm.runInNewContext(source.slice(start, end) + `
globalThis.runtime = { normalizeMapWatchlist, createPortfolioMapWorkspace, workspaceStocks,
    normalizeMapHoldings, projectReviewedPrototype, mapReadState };
`, context)
const runtime = context.runtime
const clone = value => JSON.parse(JSON.stringify(value))
const A = { userId: "11111111-1111-4111-8111-111111111111", token: "synthetic-owner-a" }
const B = { userId: "22222222-2222-4222-8222-222222222222", token: "synthetic-owner-b" }
const held = { id: "holding-1", ticker: "000660", market: "KR", name: "SK하이닉스", shares: 2, avg_cost: 100, memo: "preserve" }
const groups = () => [{ id: "group-1", user_id: A.userId, items: [
    { group_id: "group-1", ticker: "000660", market: "kr", name: "watch name" },
    { group_id: "group-1", ticker: " tsm ", market: "us", name: "TSMC" },
    { group_id: "group-1", ticker: "TSM", market: "US", name: "duplicate" },
] }]
const reply = (body, status = 200) => ({ ok: status === 200, status, json: async () => clone(body) })
const deferred = () => {
    let resolve
    const promise = new Promise(done => { resolve = done })
    return { promise, resolve }
}

function harness(t, options = {}) {
    let session = A
    const calls = [], graphs = []
    const workspace = runtime.createPortfolioMapWorkspace({
        includeWatchlist: options.includeWatchlist,
        getSession: () => session,
        fetcher: async (url, init = {}) => {
            calls.push({ url, init })
            assert.equal(init.method || "GET", "GET", "delivery regressions must not write")
            if (url.endsWith("/api/watchgroups")) return options.watch ? options.watch() : reply(groups())
            if (url.endsWith("/api/holdings")) return reply([held])
            assert.ok(url.endsWith("/api/member_map_state"), "only explicit synthetic routes allowed")
            return reply({ revision: 1, document: { layouts: [{ map_key: "main", positions: [], notes: [], marks: {} }] } })
        },
        graphLoader: async tickers => {
            graphs.push(clone(tickers))
            return { companies: tickers.map(ticker => ({ id: `company:${ticker}`, ticker,
                name: ticker, market: ticker === "000660" ? "KR" : "US" })), documents: [], links: [], commonItems: [] }
        },
    })
    t.after(() => workspace.dispose())
    return { workspace, calls, graphs, setSession: value => { session = value } }
}

test("snapshot watchgroups accepts only bare arrays and enforces owner/group identity", () => {
    const normalize = payload => clone(runtime.normalizeMapWatchlist(payload, A.userId))
    assert.deepEqual(normalize([]), { stocks: [], unsupportedCount: 0 })
    assert.deepEqual(normalize(groups()).stocks.map(stock => stock.ticker), ["000660", "TSM"])
    assert.throws(() => normalize({ groups: [] }), /invalid-watchlist-response/)
    const foreign = groups(); foreign[0].user_id = B.userId
    assert.throws(() => normalize(foreign), /watchlist-owner-mismatch/)
    const misplaced = groups(); misplaced[0].items[0].group_id = "other-group"
    assert.throws(() => normalize(misplaced), /watchlist-group-mismatch/)
    assert.throws(() => normalize([...groups(), ...groups()]), /duplicate-watchlist-group/)
})

test("snapshot workspace defaults to holdings only without watchgroups requests", async t => {
    const h = harness(t)
    assert.equal(await h.workspace.open(), true)
    assert.equal(h.calls.some(call => call.url.endsWith("/api/watchgroups")), false)
    assert.deepEqual(h.graphs, [["000660"]])
    assert.deepEqual(clone(h.workspace.getState().watchlist), [])
})

test("snapshot opt-in unions and deduplicates watched stocks without changing holdings", async t => {
    const h = harness(t, { includeWatchlist: true })
    assert.equal(await h.workspace.open(), true)
    const state = h.workspace.getState()
    assert.deepEqual(h.graphs, [["000660", "TSM"]])
    assert.deepEqual(clone(state.holdings), clone(runtime.normalizeMapHoldings([held]).holdings))
    assert.deepEqual(clone(runtime.workspaceStocks(state)), [
        { ticker: "000660", name: held.name, market: "KR", held: true, watched: true, exploring: false },
        { ticker: "TSM", name: "TSMC", market: "US", held: false, watched: true, exploring: false },
    ])
    assert.ok(state.watchlist.every(stock => !["shares", "avg_cost", "id"].some(key => key in stock)))
    const request = h.calls.find(call => call.url.endsWith("/api/watchgroups")).init
    assert.equal(request.headers.Authorization, "Bearer " + A.token)
    assert.equal(request.cache, "no-store")
    assert.equal(request.credentials, "omit")
    assert.equal(request.redirect, "error")
})

test("snapshot watch failure keeps holdings usable and explicit reload recovers union", async t => {
    let failed = true
    const h = harness(t, { includeWatchlist: true, watch: () => reply(failed ? {} : groups(), failed ? 503 : 200) })
    assert.equal(await h.workspace.open(), true)
    const before = h.workspace.getState()
    assert.equal(before.phase, "ready")
    assert.equal(before.watchlistError, "watchlist-unavailable")
    assert.deepEqual(clone(before.watchlist), [])
    assert.deepEqual(h.graphs, [["000660"]])
    failed = false
    assert.equal(await h.workspace.open(), true)
    const after = h.workspace.getState()
    assert.equal(after.watchlistError, null)
    assert.deepEqual(clone(after.holdings), clone(before.holdings))
    assert.deepEqual(h.graphs, [["000660"], ["000660", "TSM"]])
    assert.equal(h.calls.filter(call => call.url.endsWith("/api/watchgroups")).length, 2)
})

test("snapshot discards delayed watch JSON after owner switch without loading old graph", async t => {
    const body = deferred(), reading = deferred()
    const h = harness(t, { includeWatchlist: true, watch: () => ({ ok: true, status: 200,
        json: () => { reading.resolve(); return body.promise } }) })
    const opening = h.workspace.open()
    await reading.promise
    h.setSession(B)
    body.resolve(groups())
    assert.equal(await opening, false)
    const state = h.workspace.getState()
    assert.equal(state.phase, "signed-out")
    assert.deepEqual(clone(state.holdings), [])
    assert.deepEqual(clone(state.watchlist), [])
    assert.equal(state.graph, null)
    assert.deepEqual(h.graphs, [])
    assert.ok(h.calls.every(call => call.init.headers.Authorization === "Bearer " + A.token))
})

test("snapshot watched reviewed event preserves held-only fingerprint and legacy edge anchors", async t => {
    const h = harness(t, { includeWatchlist: true })
    assert.equal(await h.workspace.open(), true)
    const state = h.workspace.getState()
    const watched = runtime.projectReviewedPrototype(state)
    const event = watched.nodes.find(node => node.kind === "reviewed-event")
    assert.ok(event)
    assert.equal(event.id, "reviewed:events:event:skh-tsmc-hbm4-mou-20240419")
    const heldOnly = runtime.projectReviewedPrototype({ ...state, watchlist: [], holdings: [
        ...state.holdings, { ticker: "TSM", market: "US", name: "TSMC", shares: 1, avg_cost: 1, duplicate: false },
    ] })
    const original = heldOnly.nodes.find(node => node.id === event.id)
    assert.ok(original)
    assert.ok(Number.isSafeInteger(event.read_revision) && event.read_revision > 0)
    assert.equal(event.read_revision, original.read_revision)
    assert.deepEqual(clone(watched.recordsMap[event.id]), clone(heldOnly.recordsMap[event.id]))
    assert.deepEqual(clone(event.evidence), clone(original.evidence))
    assert.equal(runtime.mapReadState({ read_revision: original.read_revision }, event.read_revision), "read")
    const edges = watched.edges.filter(edge => edge.recordId === event.id)
    assert.deepEqual(clone(edges.map(edge => edge.id)).sort(), [
        "reviewed-link:event:skh-tsmc-hbm4-mou-20240419:KR:000660",
        "reviewed-link:event:skh-tsmc-hbm4-mou-20240419:US:TSM",
    ])
    assert.deepEqual(clone(edges.map(edge => edge.to)).sort(), ["company:000660", "company:TSM"])
    assert.ok(edges.every(edge => edge.influence === "unknown" && !("strength" in edge)))
})

const { test } = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const vm = require("node:vm")
const { createHash } = require("node:crypto")

const root = path.resolve(__dirname, "..")
const review = (...parts) => path.join(root, ...parts)
const USER = "11111111-1111-4111-8111-111111111111"

function memberMapStore() {
    const source = fs.readFileSync(review("review/member-map/Map.snapshot.tsx"), "utf8")
    const start = source.indexOf('var ENDPOINT = "https://project-yw131.vercel.app/api/member_map_state";')
    const end = source.indexOf("// framer-components/public-probe/PortfolioMapWorkspace.tsx", start)
    assert.ok(start >= 0 && end > start, "review snapshot contains the member-store segment")
    const context = { AbortController, JSON, Number, Set, clearTimeout, setTimeout }
    vm.runInNewContext(`${source.slice(start, end)}\nglobalThis.makeStore = createMemberMapStore`, context)
    return context.makeStore
}

function reviewedRuntime() {
    const source = fs.readFileSync(review("review/member-map/Map.snapshot.tsx"), "utf8")
    const stateStart = source.indexOf("// framer-components/public-probe/MemberMapState.tsx")
    const stateEnd = source.indexOf("// framer-components/public-probe/PortfolioMapWorkspace.tsx", stateStart)
    const reviewedStart = source.indexOf("// framer-components/public-probe/PortfolioReviewedState.tsx")
    const reviewedEnd = source.indexOf("// framer-components/public-probe/PublicPortfolioMap.tsx", reviewedStart)
    assert.ok(stateStart >= 0 && stateEnd > stateStart, "review snapshot contains member state")
    assert.ok(reviewedStart >= 0 && reviewedEnd > reviewedStart, "review snapshot contains reviewed state")
    const context = { AbortController, JSON, Number, Set, clearTimeout, setTimeout }
    vm.runInNewContext(`${source.slice(stateStart, stateEnd)}\n${source.slice(reviewedStart, reviewedEnd)}\n` +
        "globalThis.reviewedRuntime = { createMemberMapStore, mapReadState, reviewedRecord, withReviewedMark }", context)
    return context.reviewedRuntime
}

function workspaceRuntime() {
    const source = fs.readFileSync(review("review/member-map/Map.snapshot.tsx"), "utf8")
    const start = source.indexOf("// framer-components/public-probe/MemberMapState.tsx")
    const end = source.indexOf("// framer-components/public-probe/PortfolioMapCanvas.tsx", start)
    assert.ok(start >= 0 && end > start, "review snapshot contains the workspace runtime")
    const context = { AbortController, JSON, Number, Set, Map, clearTimeout, setTimeout }
    vm.runInNewContext(`${source.slice(start, end)}\nglobalThis.makeWorkspace = createPortfolioMapWorkspace`, context)
    return context.makeWorkspace
}

const document = () => ({ layouts: [{ map_key: "main", positions: [], notes: [], marks: {} }] })
const response = (revision, value) => ({ ok: true, json: async () => ({ revision, document: value }) })

test("HBM evidence matches the mixed-market pair without changing existing saved fingerprints", () => {
    const source = fs.readFileSync(review("review/member-map/Map.snapshot.tsx"), "utf8")
    const start = source.indexOf("// framer-components/public-probe/PortfolioReviewedFacts.tsx")
    const end = source.indexOf("// framer-components/public-probe/PortfolioReviewedView.tsx", start)
    assert.ok(start >= 0 && end > start)
    const context = { URL }
    vm.runInNewContext(source.slice(start, end) + "\nglobalThis.facts = h => buildReviewedPortfolioFacts(h, portfolioReviewedRegistry)", context)
    const pair = [{ ticker: "000660", market: "KR" }, { ticker: "TSM", market: "US" }]
    const result = context.facts(pair)
    assert.equal(result.coverage.sources.reviewed, 7)
    assert.equal(result.relationships.length, 1)
    assert.equal(result.events.length, 1)
    assert.equal(result.events[0].id, "event:skh-tsmc-hbm4-mou-20240419")
    assert.equal(result.events[0].date, "2024-04-19")
    assert.match(result.events[0].mergeBasis, /독립된 두 기관의 확인은 아니다/)
    assert.equal(result.events[0].sourceIds.includes("tsmc-skh-memory-partner"), false)
    for (const h of [[pair[0]], [pair[1]], [{ ...pair[0], market: "US" }, pair[1]]]) {
        const missing = context.facts(h)
        assert.equal(missing.relationships.length, 0)
        assert.equal(missing.events.length, 0)
    }
    const previous = context.facts(["NVDA", "INTC", "TSM"].map(ticker => ({ ticker, market: "US" })))
    const { reviewedRecord } = reviewedRuntime()
    assert.deepEqual(previous.relationships.map(f => reviewedRecord("relationships", f).read_revision).join(","),
        "4057281121906998,6744488560557087")
    assert.equal(reviewedRecord("events", previous.events[0]).read_revision, 1342022201796333)
})

test("member map load and save use a freshly rotated token without discarding a same-member draft", async () => {
    let session = { userId: USER, token: "rotated-before-load" }
    const calls = []
    const Store = memberMapStore()
    const store = Store({ getSession: () => session, fetcher: async (_url, init) => {
        calls.push(init)
        if (init.method === "GET") return response(4, document())
        return response(5, JSON.parse(init.body).document)
    } })

    assert.equal(await store.load(), true)
    assert.equal(calls[0].headers.Authorization, "Bearer rotated-before-load")
    assert.equal(store.update(value => ({ layouts: [{ ...value.layouts[0], notes: [{
        note_id: "note-1", anchor: null, x: 1, y: 2, text: "keep this draft", done: false,
    }] }] })), true)

    session = { userId: USER, token: "rotated-before-save" }
    assert.equal(store.getState().dirty, true, "same-member token rotation preserves the draft")
    assert.equal(await store.save(), true)
    assert.equal(calls[1].headers.Authorization, "Bearer rotated-before-save")
    assert.equal(JSON.parse(calls[1].body).document.layouts[0].notes[0].text, "keep this draft")
    assert.deepEqual(store.getState().document.layouts[0].notes[0].text, "keep this draft")
    assert.equal(store.getState().dirty, false)
})

test("workspace recovers one holdings 401 with a freshly rotated same-owner token", async () => {
    let token = "stale-token"
    const holdingCalls = []
    const Workspace = workspaceRuntime()
    const workspace = Workspace({
        getSession: () => ({ userId: USER, token }),
        fetcher: async (url, init) => {
            if (!url.endsWith("/api/holdings")) return response(1, document())
            holdingCalls.push(init.headers.Authorization)
            if (holdingCalls.length === 1) {
                token = "rotated-token"
                return { ok: false, status: 401, json: async () => ({}) }
            }
            return { ok: true, status: 200, json: async () => ([{ ticker: "NVDA", name: "NVIDIA", market: "US", shares: 1, avg_cost: 1 }]) }
        },
        graphLoader: async tickers => ({ companies: tickers.map(ticker => ({ ticker })), documents: [], links: [] }),
    })

    assert.equal(await workspace.open(), true)
    assert.deepEqual(holdingCalls, ["Bearer stale-token", "Bearer rotated-token"])
    assert.equal(workspace.getState().phase, "ready")
    workspace.dispose()
})

test("workspace does not retry a holdings 401 when the same token is still current", async () => {
    const holdingCalls = []
    const Workspace = workspaceRuntime()
    const workspace = Workspace({
        getSession: () => ({ userId: USER, token: "unchanged-token" }),
        fetcher: async (url, init) => {
            if (!url.endsWith("/api/holdings")) return response(1, document())
            holdingCalls.push(init.headers.Authorization)
            return { ok: false, status: 401, json: async () => ({}) }
        },
        graphLoader: async () => ({ companies: [], documents: [], links: [] }),
    })

    assert.equal(await workspace.open(), false)
    assert.deepEqual(holdingCalls, ["Bearer unchanged-token"])
    assert.equal(workspace.getState().error, "authentication-required")
    workspace.dispose()
})

test("workspace ignores a holdings response after the active owner changes", async () => {
    const OWNER_B = "22222222-2222-4222-8222-222222222222"
    let session = { userId: USER, token: "owner-a-token" }
    let releaseHoldings
    const Workspace = workspaceRuntime()
    const workspace = Workspace({
        getSession: () => session,
        fetcher: async (url) => {
            if (!url.endsWith("/api/holdings")) return response(1, document())
            return new Promise(resolve => { releaseHoldings = resolve })
        },
        graphLoader: async () => { throw new Error("owner-changed response must not load a graph") },
    })

    const opening = workspace.open()
    session = { userId: OWNER_B, token: "owner-b-token" }
    releaseHoldings({ ok: true, status: 200, json: async () => ([{ ticker: "NVDA", name: "NVIDIA", market: "US", shares: 1, avg_cost: 1 }]) })

    assert.equal(await opening, false)
    assert.deepEqual(workspace.getState().holdings, [])
    assert.equal(workspace.getState().graph, null)
    assert.equal(workspace.getState().phase, "signed-out")
    workspace.dispose()
})

test("design shell retains real-item rail, neutral controls and guarded state", () => {
    const source = fs.readFileSync(review("review/member-map/Map.snapshot.tsx"), "utf8")
    assert.match(source, /지도 항목 목록/)
    assert.match(source, /grid-template-columns:220px minmax\(0,1fr\) 300px/)
    assert.match(source, /font:400 13px\/1\.55/)
    assert.match(source, /previous\?\.kind === "document" && previous\.id === item\.id \? null/)
    assert.match(source, /ppm-reviewed-date/)
    const entry = fs.readFileSync(review("review/member-map/entry.tsx"), "utf8")
    assert.ok(entry.indexOf('className="review-boundary"') > entry.indexOf('className="review-auth"'))
})

test("review shell stays same-origin, provider-free, and without an iframe", () => {
    const entry = fs.readFileSync(review("review/member-map/entry.tsx"), "utf8")
    const shim = fs.readFileSync(review("review/member-map/framer-shim.ts"), "utf8")
    const build = fs.readFileSync(review("review/member-map/build.cjs"), "utf8")
    const config = JSON.parse(fs.readFileSync(review("vercel-api/vercel.json"), "utf8"))

    assert.match(entry, /redirectUrl=\{RETURN_URL\}/)
    assert.match(entry, /getVeritySession/)
    assert.doesNotMatch(entry + shim, /<iframe\b|postMessage|sessionStorage/)
    assert.doesNotMatch(build, /SUPABASE_SERVICE_ROLE_KEY|SERVICE_ROLE/)
    assert.match(build, /SUPABASE_URL/)
    assert.match(build, /SUPABASE_ANON_KEY/)
    const headers = config.headers.find(row => row.source === "/member-map-review(.*)")?.headers || []
    assert.equal(headers.some(row => row.key === "Access-Control-Allow-Origin"), false)
    assert.match(headers.find(row => row.key === "Content-Security-Policy")?.value || "", /connect-src 'self' https:\/\/lykqebdcurreppowulsl\.supabase\.co/)
})

test("review HTML and referenced assets are inside Vercel's existing public output", () => {
    const publicRoot = review("vercel-api/public")
    const html = fs.readFileSync(path.join(publicRoot, "member-map-review.html"), "utf8")
    const config = JSON.parse(fs.readFileSync(review("vercel-api/vercel.json"), "utf8"))
    const assets = [...html.matchAll(/(?:src|href)="(\/member-map-review\/[^"?#]+)"/g)].map(match => match[1])
    assert.equal(config.cleanUrls, true, "extensionless review URL resolves to its HTML")
    assert.deepEqual(assets.sort(), ["/member-map-review/app.js", "/member-map-review/style.css"])
    for (const asset of assets) assert.ok(fs.statSync(path.join(publicRoot, asset)).isFile(), asset)
    assert.equal(fs.existsSync(review("vercel-api/member-map-review.html")), false)
    assert.equal(fs.existsSync(review("vercel-api/member-map-review")), false)
    const build = fs.readFileSync(review("review/member-map/build.cjs"), "utf8")
    assert.match(build, /outfile: path\.join\(repo, 'vercel-api\/public\/member-map-review\/app\.js'\)/)
})

test("reviewed facts use the member map store without copying primary-source text into saved state", async () => {
    const { createMemberMapStore, mapReadState, reviewedRecord, withReviewedMark } = reviewedRuntime()
    const fact = {
        id: "relation:test",
        from: { ticker: "NVDA", market: "US" },
        to: { ticker: "INTC", market: "US" },
        label: "검토된 공동 개발",
        asOf: "2026-09-29",
        status: "historical-announcement",
        sourceIds: ["source-b", "source-a"],
        sources: [
            { id: "source-a", url: "https://example.com/a", publisher: "A", publishedAt: "2025-01-01", statement: "official statement A" },
            { id: "source-b", url: "https://example.com/b", publisher: "B", publishedAt: "2025-01-02", statement: "official statement B" },
        ],
        limitations: "당시 발표 범위만 확인",
        review: "manual-primary-source-comparison",
        impact: "unknown",
    }
    const legacyMark = { read_revision: 7, important: false, disposition: "inbox" }
    const initial = { layouts: [{ map_key: "main", positions: [], notes: [], marks: { "document:legacy": legacyMark } }] }
    const calls = []
    const store = createMemberMapStore({ getSession: () => ({ userId: USER, token: "reviewed-state-token" }), fetcher: async (_url, init) => {
        calls.push(init)
        if (init.method === "GET") return response(12, initial)
        return response(13, JSON.parse(init.body).document)
    } })

    assert.equal(await store.load(), true)
    const record = reviewedRecord("relationships", fact)
    assert.equal(record.id, "reviewed:relationships:relation:test")
    assert.ok(Number.isSafeInteger(record.read_revision) && record.read_revision > 0)
    assert.equal(store.update(value => ({ layouts: [withReviewedMark(value.layouts[0], "relationships", fact, {
        read: true, important: true, disposition: "later",
    })] })), true)
    assert.equal(await store.save(), true)

    const body = JSON.parse(calls[1].body)
    const savedMarks = body.document.layouts[0].marks
    assert.deepEqual(JSON.parse(JSON.stringify(savedMarks["document:legacy"])), legacyMark)
    assert.equal(savedMarks[record.id].read_revision, record.read_revision)
    assert.equal(savedMarks[record.id].important, true)
    assert.equal(savedMarks[record.id].disposition, "later")
    assert.equal(mapReadState(savedMarks[record.id], record.read_revision), "read")
    assert.equal(mapReadState(savedMarks[record.id], reviewedRecord("relationships", { ...fact, label: "변경된 의미" }).read_revision), "changed")
    assert.doesNotMatch(calls[1].body, /official statement|https:\/\/example\.com|publishedAt|publisher/)
    assert.equal(store.getState().revision, 13)
    assert.equal(store.getState().dirty, false)
})

test("review snapshot uses the actual workspace and reviewed-state graph while auth stays pinned", () => {
    const digest = value => createHash("sha256").update(value).digest("hex")
    const source = fs.readFileSync(review("review/member-map/Map.snapshot.tsx"), "utf8")
    const modules = ["PortfolioMapData", "MemberMapState", "PortfolioMapWorkspace", "PortfolioReviewedFacts",
        "PortfolioReviewedRegistry", "PortfolioReviewedView", "PortfolioReviewedState", "PublicPortfolioMap"]
    for (const name of modules) assert.match(source, new RegExp(`// framer-components/public-probe/${name}\\.tsx`), name)
    assert.match(source, /\/\/ output\/member-map-integration-20260927\/PortfolioMapReview\.entry\.tsx/)
    assert.match(source, /selectedFact && viewMode !== "documents" \? reviewedRecord\(viewMode, selectedFact\)/)
    assert.match(source, /else if \(selectedFact && viewMode !== "documents"\) edit\(\(value\) => withReviewedMark\(value, viewMode, selectedFact, change\)\)/)
    assert.match(source, /workspace = createPortfolioMapWorkspace\(\)/)
    assert.match(source, /createElement\(PublicPortfolioMap, null\)/)
    assert.doesNotMatch(source, /TestWorkspace/)
    assert.equal(digest(fs.readFileSync(review("review/member-map/Auth.snapshot.tsx"))),
        "3a2d96eeadb1e349a9f42af115d16497d6a154fb6cb0e0b490c90f697eacd2d4")
})

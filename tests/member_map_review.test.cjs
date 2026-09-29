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

const document = () => ({ layouts: [{ map_key: "main", positions: [], notes: [], marks: {} }] })
const response = (revision, value) => ({ ok: true, json: async () => ({ revision, document: value }) })

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

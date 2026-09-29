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

test("compact visual delivery preserves the accepted auth and 11 non-visual module sections", () => {
    const digest = value => createHash("sha256").update(value).digest("hex")
    const source = fs.readFileSync(review("review/member-map/Map.snapshot.tsx"), "utf8")
    const modules = ["StockInfoMapData", "PortfolioMapSources", "PortfolioCloseQuote", "PortfolioMapData",
        "MemberMapState", "PortfolioMapWorkspace", "PortfolioMapGuide", "PortfolioCompanyDetails",
        "PortfolioCloseDetails", "PortfolioSourceDetails", "PortfolioMapTheme"]
    const preserved = modules.map(name => {
        const start = source.indexOf(`// framer-components/public-probe/${name}.tsx\n`)
        const end = source.indexOf("\n// ", start)
        assert.ok(start >= 0 && end > start, name)
        return source.slice(start, end)
    }).join("\n")
    // Pin the already accepted delivery, not whichever candidate happens to be on disk.
    assert.equal(digest(preserved), "cfa9f93291c0e07b3f34257a8d3591f82baaf732f5bea9bb7bca514f591e0463")
    assert.equal(digest(fs.readFileSync(review("review/member-map/Auth.snapshot.tsx"))),
        "3a2d96eeadb1e349a9f42af115d16497d6a154fb6cb0e0b490c90f697eacd2d4")
    assert.match(source, /import \{ createPortal \} from "react-dom"/)
    assert.match(source, /shouldAutoFitCanvas/)
    assert.match(source, /sourceKind: d\.evidence\[0\]\?\.kind \|\| "other"/)
    assert.match(source, /\.pmc-toolbar\{width:max-content/)
    assert.match(source, /topInset = 112/)
})

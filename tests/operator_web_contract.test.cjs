// Existing node:test + VM pattern; uses the app's installed TypeScript/React only.
const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const vm = require("node:vm")
const { createRequire } = require("node:module")
const appRequire = createRequire(path.resolve(__dirname, "../operator-web/package.json"))
const ts = appRequire("typescript")
const { renderToStaticMarkup } = appRequire("react-dom/server")
const theme = { useDark: () => false, palette: () => ({}), cardStyle: () => ({}), FONT: "sans-serif" }
const flush = () => new Promise(setImmediate)
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }

function load(file, imports = {}, globals = {}) {
    const source = fs.readFileSync(path.resolve(__dirname, "../operator-web", file), "utf8")
    const js = ts.transpileModule(source, { compilerOptions: {
        module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
    } }).outputText
    const exports = {}
    vm.runInNewContext(js, { exports, URLSearchParams, AbortController,
        require: name => Object.hasOwn(imports, name) ? imports[name] : appRequire(name), ...globals })
    return exports
}

function hooks(initial = []) {
    const state = [...initial], effects = []
    let cursor = 0, writes = 0
    return { state, effects, reset() { cursor = 0; effects.length = 0 }, get writes() { return writes },
        render(Component, props) {
            // React discards a render when the component adjusts state for changed props.
            for (let i = 0; i < 5; i++) {
                this.reset()
                const before = writes, element = Component(props)
                if (writes === before) return element
            }
            throw Error("render did not settle")
        },
        react: { useState(value) { const i = cursor++; if (!(i in state)) state[i] = value
            return [state[i], next => { writes++; state[i] = typeof next === "function" ? next(state[i]) : next }] },
            useEffect(fn) { effects.push(fn) } },
    }
}

function api(fetch, headers = { Authorization: "Bearer fixture" }) {
    return load("lib/api.ts", { "./auth": { authHeaders: () => headers } }, { fetch })
}

test("expired auth waits for refresh, shares StrictMode flight, then rereads session", async () => {
    const pending = deferred()
    let session = { access_token: "old", expires_at: 1 }, calls = 0
    const auth = load("lib/auth.ts", { "./supabase": { refreshIfNeeded: () => { calls++; return pending.promise } } },
        { localStorage: { getItem: () => JSON.stringify(session) } })
    assert.equal(auth.isAuthed(), false)
    const a = auth.refreshAuth(), b = auth.refreshAuth()
    assert.equal(a, b)
    assert.equal(calls, 1)
    session = { access_token: "renewed", expires_at: Date.now() / 1000 + 3600 }
    pending.resolve(true)
    assert.equal(await a, true)
    assert.equal(auth.getJwt(), "renewed")
})

test("failed refresh preserves a valid session, rejects an expired session", async () => {
    let expires_at = Date.now() / 1000 + 10
    const auth = load("lib/auth.ts", { "./supabase": { refreshIfNeeded: async () => { throw Error("offline") } } },
        { localStorage: { getItem: () => JSON.stringify({ access_token: "fixture", expires_at }) } })
    assert.equal(await auth.refreshAuth(), true)
    expires_at = 1
    assert.equal(await auth.refreshAuth(), false)
})

for (const teardown of [true, false]) for (const allowed of [true, false]) test(`Home awaits auth (${allowed}), teardown=${teardown}`, async () => {
    const pending = deferred(), h = hooks(), redirects = [], timers = [], listeners = []
    const imports = { react: h.react, "@/lib/theme": theme,
        "@/lib/auth": { refreshAuth: () => pending.promise },
        "@/lib/supabase": { captureOAuthHash() {} }, "@/lib/api": {},
        "@/lib/useDataRefreshEpoch": { useDataRefreshEpoch: () => 0 } }
    const source = fs.readFileSync(path.resolve(__dirname, "../operator-web/app/page.tsx"), "utf8")
    for (const [, name] of source.matchAll(/from "(\.\/components\/[^\"]+)"/g)) imports[name] = { default: () => null }
    const Home = load("app/page.tsx", imports, { window: {
        location: { replace: value => redirects.push(value) },
        addEventListener: name => listeners.push(name), removeEventListener() {},
    }, setInterval: fn => { timers.push(fn); return 1 }, clearInterval() {} }).default
    Home()
    const cleanup = h.effects[0]()
    assert.equal(h.writes, 0)
    if (teardown) cleanup()
    pending.resolve(allowed)
    await flush()
    assert.equal(h.writes, !teardown && allowed ? 1 : 0)
    assert.deepEqual(redirects, !teardown && !allowed ? ["/login"] : [])
    assert.equal(timers.length, !teardown && allowed ? 1 : 0)
    assert.deepEqual(listeners, !teardown && allowed ? ["keydown"] : [])
    if (!teardown) cleanup()
})

test("fetchAsk preserves typed diagnostics, errors, cancellation and auth boundary", async () => {
    const fixture = { ticker: "JEPQ", status: "partial", sections: [{}], coverage: { checked: 2 },
        fetch_diagnostics: [{ source: "example.invalid/a", status: "unavailable", reason: "dns_error" }] }
    const controller = new AbortController()
    const client = api(async (url, options) => {
        assert.match(url, /ticker=JEPQ/)
        assert.equal(options.signal, controller.signal)
        assert.equal(options.headers.Authorization, "Bearer fixture")
        return { ok: true, status: 200, json: async () => fixture }
    })
    assert.equal((await client.fetchAsk("JEPQ", "", controller.signal)).data, fixture)
    assert.equal(client.askResultState(fixture), "degraded")
    assert.equal(client.askResultState({ ticker: "JEPQ", status: "ready", sections: [{}] }), "ready")
    assert.equal(client.askResultState({ ticker: "JEPQ", status: "empty", sections: [] }), "empty")
    assert.equal(client.askResultState({ ticker: null, status: "unresolved" }), "unresolved")
    assert.equal(client.askResultState({ ticker: "JEPQ", sections: [{}] }), "degraded")
    const noAuth = api(() => { throw Error("must not call fetch") }, {})
    assert.equal((await noAuth.fetchAsk("JEPQ")).error, "auth")
    const failed = api(async () => ({ ok: false, status: 500, json: async () => ({ error: "ask_failed" }) }))
    assert.equal((await failed.fetchAsk("JEPQ")).error, "ask_failed")
    const nonJson = api(async () => ({ ok: false, status: 502, json: async () => { throw Error("html") } }))
    assert.equal((await nonJson.fetchAsk("JEPQ")).status, 502)
})

for (const [realm, failure] of [
    ["host", new TypeError("Failed to fetch")],
    ["other VM", vm.runInNewContext('new TypeError("Failed to fetch")')],
]) test(`fetchAsk retries one ${realm} transport failure with the same request`, async () => {
    const fixture = { ticker: "fixture", status: "ready", sections: [] }
    const controller = new AbortController(), calls = []
    if (realm === "other VM") assert.equal(failure instanceof TypeError, false)
    const client = api(async (url, options) => {
        calls.push({ url, options })
        if (calls.length === 1) throw failure
        return { ok: true, status: 200, json: async () => fixture }
    })
    const result = await client.fetchAsk("fixture", "source & date?", controller.signal)
    assert.equal(result.ok, true)
    assert.equal(result.data, fixture)
    assert.equal(calls.length, 2)
    assert.equal(calls[1].url, calls[0].url)
    assert.equal(new URL(calls[1].url).searchParams.get("q"), "source & date?")
    assert.equal(calls[1].options, calls[0].options)
    assert.equal(calls[1].options.headers, calls[0].options.headers)
    assert.equal(calls[1].options.headers.Authorization, "Bearer fixture")
    assert.equal(calls[1].options.signal, controller.signal)
    assert.equal(calls[1].options.cache, "no-store")
})

test("fetchAsk surfaces the second transport failure without a third attempt", async () => {
    let calls = 0
    const client = api(async () => { calls++; throw new TypeError(`transport failure ${calls}`) })
    const result = await client.fetchAsk("fixture")
    assert.equal(calls, 2)
    assert.equal(result.ok, false)
    assert.equal(result.status, 0)
    assert.equal(result.error, "TypeError: transport failure 2")
})

for (const [label, failure] of [
    ["AbortError", Object.assign(new Error("cancelled"), { name: "AbortError" })],
    ["ordinary error", new Error("offline")],
]) test(`fetchAsk never retries ${label} rejection`, async () => {
    let calls = 0
    const client = api(async () => { calls++; throw failure })
    const result = await client.fetchAsk("fixture", "", new AbortController().signal)
    assert.equal(calls, 1)
    assert.equal(result.ok, false)
    assert.equal(result.error, String(failure))
})

for (const timing of ["before fetch", "during fetch"]) test(`fetchAsk never retries an aborted signal ${timing}`, async () => {
    const controller = new AbortController()
    const failure = new TypeError("custom cancellation")
    if (timing === "before fetch") controller.abort(failure)
    let calls = 0
    const client = api(async (_url, options) => {
        calls++
        assert.equal(options.signal, controller.signal)
        controller.abort(failure)
        throw failure
    })
    const result = await client.fetchAsk("fixture", "", controller.signal)
    assert.equal(calls, 1)
    assert.equal(result.ok, false)
    assert.equal(result.error, String(failure))
})

test("fetchAsk does not retry a synchronous fetch TypeError", async () => {
    let calls = 0
    const client = api(() => { calls++; throw new TypeError("invalid request") })
    const result = await client.fetchAsk("fixture")
    assert.equal(calls, 1)
    assert.equal(result.ok, false)
    assert.equal(result.error, "TypeError: invalid request")
})

for (const status of [401, 403, 400, 429, 500, 502, 503]) test(`fetchAsk never retries HTTP ${status}`, async () => {
    let calls = 0
    const client = api(async () => {
        calls++
        return { ok: false, status, json: async () => ({ error: "fixture-http-error" }) }
    })
    const result = await client.fetchAsk("fixture")
    assert.equal(calls, 1)
    assert.equal(result.ok, false)
    assert.equal(result.status, status)
    assert.equal(result.error, status === 401 || status === 403 ? "auth" : "fixture-http-error")
})

for (const [label, json] of [
    ["invalid JSON", async () => { throw new SyntaxError("invalid JSON") }],
    ["body TypeError", async () => { throw new TypeError("body read failed") }],
    ["null payload", async () => null],
    ["missing sections", async () => ({ ticker: "fixture" })],
    ["malformed sections", async () => ({ sections: {} })],
]) test(`fetchAsk never retries ${label}`, async () => {
    let calls = 0
    const client = api(async () => { calls++; return { ok: true, status: 200, json } })
    const result = await client.fetchAsk("fixture")
    assert.equal(calls, 1)
    assert.equal(result.ok, false)
    assert.equal(result.status, 200)
    assert.equal(result.error, "invalid_response")
})

for (const [stock, expected] of [
    [{ ticker: "JEPQ", name: "JEPQ", market: "ETF", type: "us_etf" }, "US"],
    [{ ticker: "AAPL", name: "Apple", market: "US" }, "US"],
    [{ ticker: "005930", name: "삼성전자", market: "KR" }, "KR"],
    [{ ticker: "069500", name: "KODEX 200", market: "ETF", type: "kr_etf" }, "KR"],
]) test(`search market label: ${stock.ticker} renders ${expected}`, () => {
    const h = hooks([[stock], stock.ticker, -1, []])
    const Search = load("app/components/StockSearch.tsx", {
        react: h.react, "@/lib/theme": { ...theme, NUM: {} },
        "@/lib/api": { fetchPublic: () => { throw Error("no network") } },
    }).default
    const html = renderToStaticMarkup(h.render(Search, {}))
    assert.match(html, /role="option"/)
    const labels = [...html.matchAll(/<span[^>]*>(US|KR)<\/span>/g)].map(match => match[1])
    assert.deepEqual(labels, [expected])
})

for (const [status, text] of [["unresolved", "종목을 확인하지 못했습니다"], ["empty", "조회된 자료 없음"],
    ["partial", "일부 소스 확인 불가"], ["ready", "사실 조회됨"]]) {
    test(`panel renders ${status}, source distinctions and unknown as-of`, () => {
        const data = { ticker: status === "unresolved" ? null : "JEPQ", status, sections: [{}], facts_text: "fixture fact",
            coverage: { total: 3, applicable: 3, checked: 3, hit: 1, no_record: 1, unavailable: 1, skipped: 0,
                sources: [{ source: "a", label: "A", status: "no_record" }, { source: "b", label: "B", status: "unavailable", reason: "dns_error" }] },
            fetch_diagnostics: [{ source: "example.invalid/a", status: "unavailable", reason: "http_429" }] }
        const h = hooks([{ generation: 0, result: { ok: true, data } }, true])
        const Panel = load("app/components/StockFactsPanel.tsx", {
            react: h.react, "@/lib/theme": theme, "@/lib/api": api(() => { throw Error("no network") }),
        }).default
        const html = renderToStaticMarkup(Panel({ ticker: "JEPQ" }))
        for (const phrase of [text, "자료 기준일 미상", "자료 없음", "조회 불가", "dns_error", "http_429", "fixture fact"])
            assert.ok(html.includes(phrase), phrase)
    })
}

test("idle has no request; ticker switch hides stale facts and aborts old response", async () => {
    const pending = deferred(), calls = [], h = hooks()
    const client = api(() => { throw Error("no network") })
    client.fetchAsk = (ticker, question, signal) => { calls.push({ ticker, signal }); return pending.promise }
    const Panel = load("app/components/StockFactsPanel.tsx", { react: h.react, "@/lib/theme": theme, "@/lib/api": client }).default
    assert.match(renderToStaticMarkup(Panel({ ticker: "" })), /종목을 선택하세요/)
    assert.equal(h.effects[0](), undefined)
    assert.equal(calls.length, 0)
    h.render(Panel, { ticker: "JEPQ" })
    const cleanup = h.effects[0]()
    const before = h.writes
    cleanup()
    assert.equal(calls[0].signal.aborted, true)
    pending.resolve({ ok: true, data: { ticker: "JEPQ", status: "ready", sections: [], facts_text: "old fact" } })
    await flush()
    assert.equal(h.writes, before)
    h.state[0] = { generation: h.state[2].generation, result: { ok: true, data: { ticker: "JEPQ", facts_text: "old fact" } } }
    const html = renderToStaticMarkup(h.render(Panel, { ticker: "AAPL" }))
    assert.match(html, /사실 조인 중/)
    assert.doesNotMatch(html, /old fact/)
})

test("A to B to A never revives the first A result while the new request is pending", async () => {
    const h = hooks([{ generation: 0, result: { ok: true, data: { ticker: "A", status: "ready", facts_text: "old A" } } }, true])
    const requests = [], client = api(() => { throw Error("no network") })
    client.fetchAsk = () => { const d = deferred(); requests.push(d); return d.promise }
    const Panel = load("app/components/StockFactsPanel.tsx", { react: h.react, "@/lib/theme": theme, "@/lib/api": client }).default
    assert.match(renderToStaticMarkup(h.render(Panel, { ticker: "A" })), /old A/)
    h.render(Panel, { ticker: "B" })
    const closeB = h.effects[0]()
    const backToA = renderToStaticMarkup(h.render(Panel, { ticker: "A" }))
    assert.doesNotMatch(backToA, /old A/)
    assert.match(backToA, /사실 조인 중/)
    closeB()
    const closeA = h.effects[0]()
    requests[0].resolve({ ok: true, data: { ticker: "B", status: "ready", facts_text: "late B" } })
    await flush()
    assert.doesNotMatch(renderToStaticMarkup(h.render(Panel, { ticker: "A" })), /old A|late B/)
    requests[1].resolve({ ok: true, data: { ticker: "A", status: "ready", facts_text: "new A" } })
    await flush()
    assert.match(renderToStaticMarkup(h.render(Panel, { ticker: "A" })), /new A/)
    closeA()
})

for (const [section, expected] of [
    [{ source: "kr_close_latest.json", label: "종가 (T+1 · 실시간 아님)", as_of: "2026-09-25" }, "종가 2026-09-25 기준"],
    [{ source: "legacy", label: "종가 (T+1 · 실시간 아님)", as_of: "2026-09-25" }, "종가 2026-09-25 기준"],
    [{ source: "yahoo:chart", label: "미국 시세·일봉", as_of: "2026-09-25T16:00:00-04:00" }, "미국 시세 2026-09-25T16:00:00-04:00 기준"],
    [{ source: "railway:us_quotes", label: "미국 시세", observed_at: "2026-09-27T15:00:00+09:00" }, "시세 자료 기준일 미상"],
]) test(`quote source/date contract: ${section.source}`, () => {
    const h = hooks([{ generation: 0, result: { ok: true, data: { ticker: "fixture", status: "ready", sections: [section] } } }, true])
    const Panel = load("app/components/StockFactsPanel.tsx", { react: h.react, "@/lib/theme": theme, "@/lib/api": api(() => {}) }).default
    const html = renderToStaticMarkup(Panel({ ticker: "fixture" }))
    assert.ok(html.includes(expected))
    if (section.observed_at) assert.ok(!html.includes(`${section.observed_at} 기준`))
})

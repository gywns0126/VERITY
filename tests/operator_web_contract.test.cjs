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
    vm.runInNewContext(js, { exports, URLSearchParams, AbortController, DOMException, setTimeout, clearTimeout,
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
            useRef(value) { const i = cursor++; if (!(i in state)) state[i] = { current: value }; return state[i] },
            useCallback(fn) { return fn },
            useEffect(fn) { effects.push(fn) } },
    }
}

function api(fetch, headers = { Authorization: "Bearer fixture" }, globals = {}, auth = {}) {
    return load("lib/api.ts", { "./auth": { authHeaders: () => headers, refreshAuth: async () => true, ...auth } }, { fetch, ...globals })
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
        assert.equal(options.signal.aborted, false)
        assert.equal(options.cache, "no-store")
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
    assert.equal(calls[1].options.method, "GET")
    assert.equal(calls[1].options.headers, calls[0].options.headers)
    assert.equal(calls[1].options.headers.Authorization, "Bearer fixture")
    assert.equal(calls[1].options.signal, calls[0].options.signal)
    assert.equal(controller.signal.aborted, false)
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
        assert.equal(options.signal.aborted, false)
        controller.abort(failure)
        throw failure
    })
    const result = await client.fetchAsk("fixture", "", controller.signal)
    assert.equal(calls, timing === "before fetch" ? 0 : 1)
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

for (const status of [401, 403, 400, 429, 500, 502, 503]) test(`fetchAsk HTTP ${status} obeys the transient retry budget`, async () => {
    let calls = 0
    const client = api(async () => {
        calls++
        return { ok: false, status, json: async () => ({ error: "fixture-http-error" }) }
    })
    const result = await client.fetchAsk("fixture")
    assert.equal(calls, [502, 503].includes(status) ? 2 : 1)
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

// Deterministic deadlines in each VM; no real network or sleeps.
function clock() {
    let now = 1800000000000, nextId = 0
    const timers = new Map()
    return {
        globals: {
            Date: class extends Date { static now() { return now } },
            setTimeout(fn, delay) { const id = ++nextId; timers.set(id, { at: now + delay, fn }); return id },
            clearTimeout(id) { timers.delete(id) },
        },
        get now() { return now }, get pending() { return timers.size },
        async advance(ms) {
            const end = now + ms
            await flush()
            while (true) {
                const due = [...timers].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0]
                if (!due) break
                const [id, timer] = due
                now = timer.at; timers.delete(id); timer.fn()
                await flush()
            }
            now = end
            await flush()
        },
    }
}

const SESSION_KEY = "verity_supabase_session", LOCK_KEY = "verity_session_refresh_lock"
const response = (status = 200, data = { ticker: "fixture", sections: [] }) => ({ ok: status >= 200 && status < 300, status, json: async () => data })
function storage() {
    const values = new Map()
    return { getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, String(v)), removeItem: k => values.delete(k) }
}
function session(clock, changes = {}) {
    return { access_token: "old", refresh_token: "old-refresh", expires_at: clock.now / 1000 - 1, ...changes }
}
function authStack(globals) {
    const supabase = load("lib/supabase.ts", {}, globals)
    const auth = load("lib/auth.ts", { "./supabase": supabase }, globals)
    const client = load("lib/api.ts", { "./auth": auth }, globals)
    return { supabase, auth, client }
}
const reads = {
    admin: (client, signal) => client.fetchOperator("portfolio_terminal", signal),
    facts: (client, signal) => client.fetchAsk("fixture", "", signal),
}

for (const expiry of ["expired", "near expiry"]) test(`admin and facts await the same ${expiry} refresh, including direct refresh callers`, async () => {
    const time = clock(), localStorage = storage(), token = deferred(), calls = []
    localStorage.setItem(SESSION_KEY, JSON.stringify(session(time, { expires_at: time.now / 1000 + (expiry === "expired" ? -1 : 10) })))
    const stack = authStack({ ...time.globals, localStorage, fetch: async (url, options) => {
        calls.push({ url, options })
        if (options.method === "POST") return token.promise
        assert.equal(options.headers.Authorization, "Bearer new")
        assert.equal(options.cache, "no-store")
        return response()
    } })
    const direct = stack.supabase.refreshIfNeeded()
    const gate = stack.auth.refreshAuth()
    const admin = reads.admin(stack.client), facts = reads.facts(stack.client)
    await time.advance(0)
    assert.equal(calls.length, 1)
    assert.equal(calls[0].options.method, "POST")
    token.resolve(response(200, session(time, { access_token: "new", refresh_token: "rotated", expires_at: time.now / 1000 + 3600 })))
    assert.equal(await direct, true)
    assert.equal(await gate, true)
    assert.equal((await admin).ok, true)
    assert.equal((await facts).ok, true)
    assert.equal(calls.length, 3)
    assert.equal(localStorage.getItem(LOCK_KEY), null)
    assert.equal(time.pending, 0)
})

for (const [name, read] of Object.entries(reads)) {
    for (const status of [502, 503, 504]) test(`${name}: one retry recovers HTTP ${status}`, async () => {
        const time = clock(), calls = []
        const client = api(async (url, options) => {
            calls.push({ url, options })
            return calls.length === 1 ? response(status, { error: "auth_service_unavailable" }) : response()
        }, undefined, time.globals)
        assert.equal((await read(client)).ok, true)
        assert.equal(calls.length, 2)
        assert.equal(calls[0].url, calls[1].url)
        assert.ok(calls.every(c => c.options.method === "GET" && c.options.cache === "no-store"))
        assert.equal(time.pending, 0)
    })
    for (const failures of [["transport", 503], [503, "transport"], [504, 502]]) test(`${name}: shared retry budget for ${failures.join(" then ")}`, async () => {
        let calls = 0
        const client = api(async () => {
            const failure = failures[calls++]
            if (failure === "transport") throw new TypeError("offline")
            return response(failure, { error: "auth_service_unavailable" })
        })
        const result = await read(client)
        assert.equal(result.ok, false)
        assert.equal(calls, 2)
    })
    for (const phase of ["auth", "fetch", "body"]) test(`${name}: deadline includes ${phase}; late completion cannot start another request`, async () => {
        const time = clock(), pending = deferred(), calls = []
        const timeout = name === "facts" ? 300000 : 30000
        const client = api(async (_url, options) => {
            calls.push(options)
            return phase === "fetch" ? pending.promise : { ...response(503), json: () => pending.promise }
        }, undefined, time.globals, { refreshAuth: () => phase === "auth" ? pending.promise : Promise.resolve(true) })
        const request = read(client)
        await time.advance(timeout - 1)
        assert.equal(calls.length, phase === "auth" ? 0 : 1)
        await time.advance(1)
        const result = await request
        assert.equal(result.status, 0)
        assert.match(result.error, /TimeoutError/)
        assert.ok(calls.every(c => c.signal.aborted))
        pending.resolve(phase === "fetch" ? response(503) : { error: "auth_service_unavailable" })
        await flush()
        assert.equal(calls.length, phase === "auth" ? 0 : 1)
        assert.equal(time.pending, 0)
    })
    for (const phase of ["auth", "fetch", "body"]) test(`${name}: explicit abort during ${phase} cleans up without retry`, async () => {
        const time = clock(), pending = deferred(), controller = new AbortController(), calls = []
        let added = 0, removed = 0
        const signal = {
            get aborted() { return controller.signal.aborted }, get reason() { return controller.signal.reason },
            addEventListener(...args) { added++; controller.signal.addEventListener(...args) },
            removeEventListener(...args) { removed++; controller.signal.removeEventListener(...args) },
        }
        const client = api(async (_url, options) => {
            calls.push(options)
            return phase === "fetch" ? pending.promise : { ...response(503), json: () => pending.promise }
        }, undefined, time.globals, { refreshAuth: () => phase === "auth" ? pending.promise : Promise.resolve(true) })
        const request = read(client, signal)
        await flush()
        controller.abort(new TypeError("user cancelled"))
        const result = await request
        assert.equal(result.error, "TypeError: user cancelled")
        assert.ok(calls.every(c => c.signal.aborted))
        pending.resolve(phase === "fetch" ? response(503) : { error: "auth_service_unavailable" })
        await flush()
        assert.equal(calls.length, phase === "auth" ? 0 : 1)
        assert.equal(added, 1)
        assert.equal(removed, 1)
        assert.equal(time.pending, 0)
    })
    for (const status of [200, 502]) test(`${name}: malformed JSON at HTTP ${status} is not retried`, async () => {
        let calls = 0
        const result = await read(api(async () => {
            calls++
            return { ...response(status), json: async () => { throw new SyntaxError("broken JSON") } }
        }))
        assert.equal(result.ok, false)
        assert.equal(result.status, status)
        assert.equal(calls, 1)
    })
}

for (const status of [401, 403, 400, 429, 500]) test(`admin: HTTP ${status} never retries or changes auth boundary`, async () => {
    let calls = 0
    const result = await reads.admin(api(async () => { calls++; return response(status, { error: "fixture" }) }))
    assert.equal(result.status, status)
    assert.equal(result.error, status === 401 || status === 403 ? "auth" : "fixture")
    assert.equal(calls, 1)
})

for (const [name, read] of Object.entries(reads)) test(`${name}: retry does not reset the read deadline including auth wait`, async () => {
    const time = clock(), auth = deferred(), first = deferred(), calls = []
    const timeout = name === "facts" ? 300000 : 30000
    const client = api(async (_url, options) => { calls.push(options); return calls.length === 1 ? first.promise : new Promise(() => {}) },
        undefined, time.globals, { refreshAuth: () => auth.promise })
    const pending = read(client)
    await time.advance(5000)
    assert.equal(calls.length, 0)
    auth.resolve(true)
    await time.advance(timeout - 15000)
    first.resolve(response(503))
    await flush()
    assert.equal(calls.length, 2)
    await time.advance(10000)
    assert.match((await pending).error, /TimeoutError/)
    assert.equal(calls.length, 2)
    assert.ok(calls.every(c => c.signal.aborted))
    assert.equal(time.pending, 0)
})

test("facts: a response after 30s succeeds before the 300s deadline", async () => {
    const time = clock(), responseReady = deferred(), calls = []
    const client = api(async (_url, options) => { calls.push(options); return responseReady.promise }, undefined, time.globals)
    let settled = false
    const pending = reads.facts(client).then(result => { settled = true; return result })
    await time.advance(30001)
    assert.equal(settled, false)
    assert.equal(calls.length, 1)
    assert.equal(calls[0].signal.aborted, false)
    await time.advance(209999) // 240s total, matching the facts core's work budget.
    assert.equal(settled, false)
    assert.equal(calls[0].signal.aborted, false)
    const payload = { ticker: "fixture", sections: [] }
    responseReady.resolve(response(200, payload))
    const result = await pending
    assert.equal(result.ok, true)
    assert.equal(result.data, payload)
    assert.equal(calls.length, 1)
    assert.equal(time.pending, 0)
})

test("aborting one read keeps the shared session refresh alive for another", async () => {
    const time = clock(), localStorage = storage(), token = deferred(), controller = new AbortController(), calls = []
    localStorage.setItem(SESSION_KEY, JSON.stringify(session(time)))
    const stack = authStack({ ...time.globals, localStorage, fetch: async (url, options) => {
        calls.push(options)
        return options.method === "POST" ? token.promise : response()
    } })
    const cancelled = reads.facts(stack.client, controller.signal), active = reads.admin(stack.client)
    await time.advance(0)
    controller.abort()
    assert.match((await cancelled).error, /AbortError/)
    assert.equal(calls[0].signal.aborted, false)
    token.resolve(response(200, session(time, { access_token: "renewed", expires_at: time.now / 1000 + 3600 })))
    assert.equal((await active).ok, true)
    assert.equal(calls.length, 2)
    assert.equal(time.pending, 0)
})

for (const status of [401, 403, 503, 500, 200]) test(`portfolio: HTTP ${status} cannot multiply retries through full fallback`, async () => {
    const urls = []
    const client = api(async url => { urls.push(url); return status === 200
        ? { ...response(), json: async () => { throw new SyntaxError("invalid") } }
        : response(status, { error: "fixture" }) })
    assert.equal((await client.fetchPortfolioSlim()).ok, false)
    assert.equal(urls.length, status === 503 ? 2 : 1)
    assert.ok(urls.every(url => url.includes("type=portfolio_terminal")))
})
test("portfolio: legacy unknown endpoint still falls back to authenticated full route", async () => {
    const urls = []
    const client = api(async url => { urls.push(url); return urls.length === 1 ? response(400, { error: "unknown_endpoint" }) : response() })
    assert.equal((await client.fetchPortfolioSlim()).ok, true)
    assert.match(urls[1], /type=portfolio_full/)
})

for (const rotatedStillDue of [false, true]) test(`cross-tab wait rereads rotated token; still due=${rotatedStillDue}`, async () => {
    const time = clock(), localStorage = storage(), used = []
    localStorage.setItem(SESSION_KEY, JSON.stringify(session(time)))
    localStorage.setItem(LOCK_KEY, String(time.now)) // Also supports the previous numeric lease format.
    const { supabase } = authStack({ ...time.globals, localStorage, fetch: async (_url, options) => {
        used.push(JSON.parse(options.body).refresh_token)
        return response(200, session(time, { access_token: "final", refresh_token: "final-refresh", expires_at: time.now / 1000 + 3600 }))
    } })
    const pending = supabase.refreshIfNeeded()
    await time.advance(500)
    assert.equal(used.length, 0)
    localStorage.setItem(SESSION_KEY, JSON.stringify(session(time, { access_token: "rotated", refresh_token: "rotated-refresh", expires_at: time.now / 1000 + (rotatedStillDue ? 10 : 3600) })))
    localStorage.removeItem(LOCK_KEY)
    await time.advance(100)
    assert.equal(await pending, rotatedStillDue)
    assert.deepEqual(used, rotatedStillDue ? ["rotated-refresh"] : [])
    assert.equal(time.pending, 0)
})

test("cross-tab wait times out without deleting the other tab's lock or refreshing its old token", async () => {
    const time = clock(), localStorage = storage(), lock = String(time.now)
    localStorage.setItem(SESSION_KEY, JSON.stringify(session(time)))
    localStorage.setItem(LOCK_KEY, lock)
    let calls = 0
    const { supabase } = authStack({ ...time.globals, localStorage, fetch: async () => { calls++; return response() } })
    const pending = supabase.refreshIfNeeded()
    await time.advance(15000)
    assert.equal(await pending, false)
    assert.equal(calls, 0)
    assert.equal(localStorage.getItem(LOCK_KEY), lock)
    assert.equal(time.pending, 0)
})

for (const phase of ["fetch", "body"]) test(`refresh ${phase} deadline clears own lock and ignores late token response`, async () => {
    const time = clock(), localStorage = storage(), pending = deferred(), calls = []
    const original = session(time)
    localStorage.setItem(SESSION_KEY, JSON.stringify(original))
    const { supabase } = authStack({ ...time.globals, localStorage, fetch: async (_url, options) => {
        calls.push(options)
        return phase === "fetch" ? pending.promise : { ...response(), json: () => pending.promise }
    } })
    const refresh = supabase.refreshIfNeeded()
    assert.equal(refresh, supabase.refreshIfNeeded())
    await time.advance(0)
    assert.equal(calls.length, 1)
    await time.advance(15000)
    assert.equal(await refresh, false)
    assert.equal(calls[0].signal.aborted, true)
    assert.equal(localStorage.getItem(LOCK_KEY), null)
    const late = session(time, { access_token: "late", expires_at: time.now / 1000 + 3600 })
    pending.resolve(phase === "fetch" ? response(200, late) : late)
    await flush()
    assert.equal(localStorage.getItem(SESSION_KEY), JSON.stringify(original))
    assert.equal(time.pending, 0)
})

for (const change of ["logout", "new session", "new lock"]) test(`refresh completion preserves ${change}`, async () => {
    const time = clock(), localStorage = storage(), pending = deferred()
    localStorage.setItem(SESSION_KEY, JSON.stringify(session(time)))
    const { supabase } = authStack({ ...time.globals, localStorage, fetch: () => pending.promise })
    const refresh = supabase.refreshIfNeeded()
    await time.advance(0)
    const newer = session(time, { access_token: "other-login", refresh_token: "other-refresh" })
    if (change === "logout") localStorage.removeItem(SESSION_KEY)
    if (change === "new session") localStorage.setItem(SESSION_KEY, JSON.stringify(newer))
    if (change === "new lock") localStorage.setItem(LOCK_KEY, "replacement-lock")
    pending.resolve(response(200, session(time, { access_token: "refreshed", expires_at: time.now / 1000 + 3600 })))
    await refresh
    if (change === "logout") assert.equal(localStorage.getItem(SESSION_KEY), null)
    if (change === "new session") assert.equal(localStorage.getItem(SESSION_KEY), JSON.stringify(newer))
    assert.equal(localStorage.getItem(LOCK_KEY), change === "new lock" ? "replacement-lock" : null)
    assert.equal(time.pending, 0)
})

test("simultaneous tabs share storage lease and only one consumes the refresh token", async () => {
    const time = clock(), localStorage = storage(), pending = deferred(), calls = []
    localStorage.setItem(SESSION_KEY, JSON.stringify(session(time)))
    const globals = { ...time.globals, localStorage, fetch: (_url, options) => { calls.push(options); return pending.promise } }
    const a = authStack(globals), b = authStack(globals)
    const first = a.auth.refreshAuth(), second = b.auth.refreshAuth()
    await time.advance(0)
    assert.equal(calls.length, 1)
    pending.resolve(response(200, session(time, { access_token: "fresh", refresh_token: "fresh-refresh", expires_at: time.now / 1000 + 3600 })))
    await time.advance(100)
    assert.equal(await first, true)
    assert.equal(await second, true)
    assert.equal(calls.length, 1)
    assert.equal(localStorage.getItem(LOCK_KEY), null)
    assert.equal(time.pending, 0)
})

test("Web Lock queue is bounded and a delayed callback cannot refresh after timeout", async () => {
    const time = clock(), localStorage = storage(), queued = deferred()
    localStorage.setItem(SESSION_KEY, JSON.stringify(session(time)))
    let callback, lockSignal, calls = 0
    const { supabase } = authStack({ ...time.globals, localStorage,
        navigator: { locks: { request: (name, options, fn) => { assert.equal(name, LOCK_KEY); callback = fn; lockSignal = options.signal; return queued.promise } } },
        fetch: async () => { calls++; return response() },
    })
    const refresh = supabase.refreshIfNeeded()
    await time.advance(15000)
    assert.equal(await refresh, false)
    assert.equal(lockSignal.aborted, true)
    await assert.rejects(callback(), { name: "TimeoutError" })
    queued.resolve(false)
    assert.equal(calls, 0)
    assert.equal(localStorage.getItem(LOCK_KEY), null)
    assert.equal(time.pending, 0)
})

const emptyBalance = () => ({ rt_cd: "0", output1: [], output2: [{ dnca_tot_amt: "0", tot_evlu_amt: "0", evlu_pfls_smtl_amt: "0" }] })
function balancePanel(client) {
    const h = hooks()
    const Panel = load("app/components/BalanceCard.tsx", {
        react: h.react, "@/lib/theme": { ...theme, NUM: {}, CARD_TITLE: {}, RAIL_PAD: 12 },
        "@/lib/api": client, "./StockLogo": { default: () => null }, "@/lib/types": { selectTicker() {} },
    }).default
    const html = () => renderToStaticMarkup(h.render(Panel, {}))
    html()
    return { h, html, start: () => h.effects[0]() }
}

for (const [label, payload] of [
    ["empty object", {}], ["null", null], ["array", []], ["missing success code", { output1: [], output2: emptyBalance().output2 }],
    ["upstream refusal", { rt_cd: "1", msg1: "balance unavailable" }],
    ["missing summary", { rt_cd: "0", output1: [] }],
    ["empty summary array", { rt_cd: "0", output1: [], output2: [] }],
    ["empty summary object", { rt_cd: "0", output1: [], output2: [{}] }],
    ["malformed amount", { ...emptyBalance(), output2: [{ ...emptyBalance().output2[0], tot_evlu_amt: "unavailable" }] }],
    ["blank amount", { ...emptyBalance(), output2: [{ ...emptyBalance().output2[0], dnca_tot_amt: "" }] }],
    ["null amount", { ...emptyBalance(), output2: [{ ...emptyBalance().output2[0], dnca_tot_amt: null }] }],
    ["missing holdings", { rt_cd: "0", output2: emptyBalance().output2 }],
    ["invalid holding", { ...emptyBalance(), output1: [null] }],
    ["invalid quantity", { ...emptyBalance(), output1: [{ hldg_qty: "unknown" }] }],
]) test(`balance: ${label} renders unavailable, never zero or no holdings`, async () => {
    let calls = 0
    const panel = balancePanel(api(async () => { calls++; return response(200, payload) }))
    const cleanup = panel.start()
    await flush()
    const html = panel.html()
    assert.match(html, /조회 불가/)
    assert.doesNotMatch(html, /실계좌 보유 종목 없음|총평가|예수금/)
    assert.equal(calls, 1)
    cleanup()
})

for (const failure of ["transport", "json", 401, 403, 502, 503, 504]) test(`balance: ${failure} is surfaced without automatic retry`, async () => {
    let calls = 0
    const panel = balancePanel(api(async () => {
        calls++
        if (failure === "transport") throw new TypeError("offline")
        if (failure === "json") return { ...response(), json: async () => { throw new SyntaxError("invalid JSON") } }
        return response(failure, { error: "balance_unavailable" })
    }))
    const cleanup = panel.start()
    await flush()
    assert.match(panel.html(), /조회 불가/)
    assert.doesNotMatch(panel.html(), /실계좌 보유 종목 없음/)
    assert.equal(calls, 1)
    cleanup()
})

for (const hasHoldings of [false, true]) test(`balance: validated ${hasHoldings ? "holdings" : "zero summary"} renders normally`, async () => {
    const payload = emptyBalance()
    if (hasHoldings) {
        payload.output1 = [{ pdno: "005930", prdt_name: "fixture stock", hldg_qty: "2", pchs_avg_pric: "100", prpr: "101", evlu_pfls_rt: "1", evlu_amt: "202" }]
        payload.output2[0] = { dnca_tot_amt: "1,000", tot_evlu_amt: "1,202", evlu_pfls_smtl_amt: "2" }
    }
    const panel = balancePanel(api(async () => response(200, payload)))
    const cleanup = panel.start()
    await flush()
    const html = panel.html()
    assert.doesNotMatch(html, /조회 불가/)
    assert.match(html, hasHoldings ? /fixture stock/ : /실계좌 보유 종목 없음/)
    assert.match(html, hasHoldings ? /1,202원/ : /0원/)
    cleanup()
})

test("balance: session refresh is awaited before its single GET, with no-store", async () => {
    const time = clock(), localStorage = storage(), token = deferred(), calls = []
    localStorage.setItem(SESSION_KEY, JSON.stringify(session(time)))
    const { client } = authStack({ ...time.globals, localStorage, fetch: async (url, options) => {
        calls.push({ url, options })
        if (options.method === "POST") return token.promise
        assert.match(url, /\/api\/order\?market=kr$/)
        assert.equal(options.method, "GET")
        assert.equal(options.headers.Authorization, "Bearer new")
        assert.equal(options.cache, "no-store")
        return response(200, emptyBalance())
    } })
    const panel = balancePanel(client), cleanup = panel.start()
    await time.advance(0)
    assert.equal(calls.length, 1)
    token.resolve(response(200, session(time, { access_token: "new", refresh_token: "rotated", expires_at: time.now / 1000 + 3600 })))
    await flush()
    assert.equal(calls.length, 2)
    assert.match(panel.html(), /실계좌 보유 종목 없음/)
    assert.equal(time.pending, 0)
    cleanup()
})

test("balance: deadline shows unavailable and teardown ignores late data", async () => {
    const time = clock(), pending = deferred(), calls = []
    const panel = balancePanel(api(async (_url, options) => { calls.push(options); return pending.promise }, undefined, time.globals))
    const cleanup = panel.start()
    await time.advance(30000)
    assert.match(panel.html(), /조회 불가.*TimeoutError/)
    assert.equal(calls.length, 1)
    assert.equal(calls[0].signal.aborted, true)
    assert.equal(time.pending, 0)
    cleanup()
    const writes = panel.h.writes
    pending.resolve(response(200, emptyBalance()))
    await flush()
    assert.equal(panel.h.writes, writes)
})

test("balance: teardown aborts an active GET and blocks stale state writes", async () => {
    const time = clock(), pending = deferred(), calls = []
    const panel = balancePanel(api(async (_url, options) => { calls.push(options); return pending.promise }, undefined, time.globals))
    const cleanup = panel.start()
    await flush()
    cleanup()
    const writes = panel.h.writes
    pending.resolve(response(200, emptyBalance()))
    await flush()
    assert.equal(panel.h.writes, writes)
    assert.equal(calls.length, 1)
    assert.equal(calls[0].signal.aborted, true)
    assert.equal(time.pending, 0)
})

test("Web Locks serialize tabs and the queued tab reads the rotated session", async () => {
    const time = clock(), localStorage = storage(), pending = deferred()
    localStorage.setItem(SESSION_KEY, JSON.stringify(session(time)))
    let tail = Promise.resolve(), claims = 0, tokenCalls = 0
    const globals = { ...time.globals, localStorage,
        navigator: { locks: { request(name, options, callback) {
            assert.equal(name, LOCK_KEY)
            claims++
            const next = tail.then(() => { options.signal.throwIfAborted(); return callback() })
            tail = next.catch(() => {})
            return next
        } } },
        fetch: () => { tokenCalls++; return pending.promise },
    }
    const a = authStack(globals), b = authStack(globals)
    const first = a.auth.refreshAuth(), second = b.auth.refreshAuth()
    await time.advance(0)
    assert.equal(claims, 2)
    assert.equal(tokenCalls, 1)
    pending.resolve(response(200, session(time, { access_token: "rotated", refresh_token: "rotated-refresh", expires_at: time.now / 1000 + 3600 })))
    await time.advance(0)
    assert.equal(await first, true)
    assert.equal(await second, true)
    assert.equal(b.auth.getJwt(), "rotated")
    assert.equal(tokenCalls, 1)
    assert.equal(localStorage.getItem(LOCK_KEY), null)
    assert.equal(time.pending, 0)
})

test("failed refresh is not retried and releases its own lease and shared flight", async () => {
    const time = clock(), localStorage = storage()
    localStorage.setItem(SESSION_KEY, JSON.stringify(session(time)))
    let calls = 0
    const { auth, supabase } = authStack({ ...time.globals, localStorage, fetch: async () => { calls++; throw new TypeError("offline") } })
    const pending = auth.refreshAuth()
    await time.advance(0)
    assert.equal(await pending, false)
    assert.equal(calls, 1)
    assert.equal(localStorage.getItem(LOCK_KEY), null)
    supabase.saveSession(session(time, { access_token: "new login", expires_at: time.now / 1000 + 3600 }))
    assert.equal(await auth.refreshAuth(), true)
    assert.equal(calls, 1)
    assert.equal(time.pending, 0)
})

test("balance: HTTP 403 broker configuration diagnosis survives to the UI without retry", async () => {
    const message = "BROKER_SLUGS missing; KIS_ACCOUNT_NO must match the account"
    let calls = 0
    const panel = balancePanel(api(async () => { calls++; return response(403, { error: message }) }))
    const cleanup = panel.start()
    await flush()
    const html = panel.html()
    assert.ok(html.includes(`조회 불가 — ${message}`))
    assert.doesNotMatch(html, /조회 불가 — auth|실계좌 보유 종목 없음/)
    assert.equal(calls, 1)
    cleanup()
})

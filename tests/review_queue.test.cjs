const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const vm = require("node:vm")
const { createRequire } = require("node:module")
const appRequire = createRequire(path.resolve(__dirname, "../operator-web/package.json"))
const ts = appRequire("typescript")
const { renderToStaticMarkup } = appRequire("react-dom/server")
const flush = () => new Promise(setImmediate)
const fixture = items => ({ schema: "analysis-review-queue-v1", total: items.length, generated_at: "2026-01-01T00:00:00Z", items })
const item = (ticker, state, extra = {}) => ({ ticker, name: ticker, state, prepared_at: "2026-01-01T00:00:00Z", reviewed_at: null, valid_until: null, verdict: null, confidence: null, ...extra })

function setup(fetch, allowed = true) {
    let cursor = 0, authorization = allowed ? "Bearer fixture" : undefined
    const state = [], effects = [], timers = new Map(), selected = [], listeners = {}
    const react = { useState(initial) { const i = cursor++; if (!(i in state)) state[i] = typeof initial === "function" ? initial() : initial
        return [state[i], next => { state[i] = typeof next === "function" ? next(state[i]) : next }] }, useEffect(fn) { effects.push(fn) } }
    const source = fs.readFileSync(path.resolve(__dirname, "../operator-web/app/components/ReviewQueue.tsx"), "utf8")
    const exports = {}
    vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText, {
        exports, AbortController, fetch, Date,
        setTimeout(fn) { timers.set(fn, fn); return fn }, clearTimeout(id) { timers.delete(id) },
        document: { getElementById: () => ({ scrollIntoView() {} }) },
        window: { addEventListener(name, fn) { listeners[name] = fn }, removeEventListener(name) { delete listeners[name] } },
        require(name) {
            if (name === "react") return react
            if (name === "@/lib/api") return { API_BASE: "https://fixture.invalid" }
            if (name === "@/lib/auth") return { refreshAuth: async () => true, authHeaders: () => ({ Authorization: authorization }) }
            if (name === "@/lib/types") return { selectTicker: (...args) => selected.push(args) }
            if (name === "@/lib/theme") return { useDark: () => false, palette: () => ({}), cardStyle: () => ({}) }
            return appRequire(name)
        },
    })
    const render = () => { cursor = 0; effects.length = 0; return exports.default() }
    render()
    const cleanup = effects[0]()
    return { state, timers, selected, render, cleanup, listeners, html: () => renderToStaticMarkup(render()), changeAuth: () => { authorization = undefined } }
}
const ok = data => ({ ok: true, json: async () => data })
function buttons(element, result = []) {
    if (!element || typeof element !== "object") return result
    if (element.type === "button") result.push(element)
    for (const child of [element.props?.children].flat(Infinity)) buttons(child, result)
    return result
}

test("queue uses authenticated private GET and selects the workspace ticker", async () => {
    const panel = setup(async (url, options) => {
        assert.match(url, /analysis_review\?view=queue$/)
        assert.equal(options.headers.Authorization, "Bearer fixture")
        assert.equal(options.cache, "no-store")
        assert.equal(options.redirect, "error")
        return ok(fixture([item("MSFT", "awaiting_review")]))
    })
    await flush()
    assert.match(panel.html(), /판단 대기/)
    buttons(panel.render()).find(b => b.props.className === "af-review-row").props.onClick()
    assert.deepEqual(panel.selected, [["MSFT", "MSFT"]])
    panel.cleanup()
})
test("past deadline overrides stored reviewed label; valid records stay separate", async () => {
    const panel = setup(async () => ok(fixture([
        item("OLD", "reviewed", { valid_until: "2020-01-01T00:00:00Z", verdict: "관심" }),
        item("NEW", "reviewed", { valid_until: "2099-01-01T00:00:00Z", verdict: "보류" }),
    ])))
    await flush()
    assert.match(panel.html(), /재검토 목록 · 1/)
    assert.match(panel.html(), /기한 경과 · 재검토 필요/)
    assert.match(panel.html(), /기한 내 검토 기록 · 1/)
    panel.cleanup()
})
for (const [name, response] of [
    ["empty", () => ok(fixture([]))],
    ["unavailable", () => ({ ok: false, status: 503 })],
    ["invalid", () => ok({ ...fixture([]), total: 1 })],
]) test(`queue distinguishes ${name}`, async () => {
    const panel = setup(async () => response())
    await flush()
    const html = panel.html()
    assert.match(html, name === "empty" ? /아직 게시된 분석 기록이 없습니다/ : /role="alert"/)
    if (name !== "empty") assert.doesNotMatch(html, /아직 게시된 분석 기록이 없습니다/)
    panel.cleanup()
})
test("missing auth never fetches", async () => {
    const panel = setup(() => { throw Error("must not fetch") }, false)
    await flush(); assert.match(panel.html(), /관리자 로그인이 필요/); panel.cleanup()
})
test("cross-tab session replacement clears already rendered private records", async () => {
    const panel = setup(async () => ok(fixture([item("PRIVATE", "awaiting_review")])))
    await flush(); assert.match(panel.html(), /PRIVATE/)
    panel.listeners.storage({ key: "verity_supabase_session" })
    assert.doesNotMatch(panel.html(), /PRIVATE/)
    panel.cleanup()
})
for (const boundary of ["timeout", "unmount", "session"]) test(`queue rejects a late response after ${boundary}`, async () => {
    let resolve
    const panel = setup(() => new Promise(r => { resolve = r }))
    await flush()
    if (boundary === "timeout") [...panel.timers.values()][0]()
    if (boundary === "unmount") panel.cleanup()
    if (boundary === "session") panel.changeAuth()
    resolve(ok(fixture([item("LATE", "awaiting_review")])))
    await flush()
    assert.doesNotMatch(panel.html(), /LATE/)
    if (boundary !== "unmount") assert.match(panel.html(), /role="alert"/)
    panel.cleanup()
})

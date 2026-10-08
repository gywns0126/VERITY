// Synthetic CRUD only: no credentials, external requests, database or production writes.
const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const vm = require("node:vm")
const { createRequire } = require("node:module")
const appRequire = createRequire(path.resolve(__dirname, "../operator-web/package.json"))
const ts = appRequire("typescript")
const { renderToStaticMarkup } = appRequire("react-dom/server")
const source = fs.readFileSync(path.resolve(__dirname, "../operator-web/app/components/SavedCompanies.tsx"), "utf8")
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText
const flush = () => new Promise(setImmediate)
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
const owner = "synthetic-owner-a"
const jwt = uid => `header.${Buffer.from(JSON.stringify({ sub: uid })).toString("base64url")}.signature`
const item = { id: "item-1", group_id: "group-1", ticker: "MSFT", name: "Microsoft", market: "us" }
const groups = () => [{ id: "group-1", user_id: owner, name: "장기 검토", items: [item] }]
const response = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
function nodes(node) {
    if (!node || typeof node !== "object") return []
    if (Array.isArray(node)) return node.flatMap(nodes)
    return [node, ...nodes(node.props?.children)]
}
function harness(options = {}) {
    const state = [], effects = [], requests = [], timers = new Map(), listeners = new Map(), selected = [], scrolls = []
    let cursor = 0, timerId = 0, writes = 0, token = jwt(owner)
    const react = {
        useState(initial) { const i = cursor++; if (!(i in state)) state[i] = initial
            return [state[i], value => { writes++; state[i] = typeof value === "function" ? value(state[i]) : value }] },
        useRef(value) { const i = cursor++; if (!(i in state)) state[i] = { current: value }; return state[i] },
        useEffect(fn) { effects.push(fn) },
    }
    const exports = {}
    vm.runInNewContext(js, { exports, AbortController, DOMException, atob: v => Buffer.from(v, "base64").toString("binary"),
        setTimeout: fn => { const id = ++timerId; timers.set(id, fn); return id }, clearTimeout: id => timers.delete(id),
        window: { addEventListener: (key, fn) => listeners.set(key, fn), removeEventListener: key => listeners.delete(key) },
        document: { getElementById: id => { assert.equal(id, "console-analysis"); return { scrollIntoView: value => scrolls.push(value) } } },
        fetch: async (url, init) => {
            assert.equal(url, "https://fixture.invalid/api/watchgroups")
            assert.equal(init.cache, "no-store"); assert.equal(init.credentials, "omit"); assert.equal(init.redirect, "error")
            assert.equal(init.headers.Authorization, `Bearer ${token}`)
            requests.push({ method: init.method, body: init.body ? JSON.parse(init.body) : undefined, signal: init.signal })
            return options.fetch ? options.fetch(requests.at(-1), requests.length) : response(groups())
        },
        require: name => name === "react" ? react : name === "@/lib/api" ? { API_BASE: "https://fixture.invalid" } : name === "@/lib/auth" ? {
            authHeaders: () => token ? { Authorization: `Bearer ${token}` } : {}, refreshAuth: options.refresh || (async () => true),
        } : name === "@/lib/theme" ? { useDark: () => false, palette: () => ({}), cardStyle: () => ({}), CARD_TITLE: {}, RAIL_PAD: "", FONT: "sans-serif" } : name === "@/lib/types" ? { selectTicker: (...value) => selected.push(value) } : appRequire(name),
    })
    const render = () => { cursor = 0; effects.length = 0; return exports.default() }
    const h = { requests, selected, scrolls, render, get writes() { return writes }, get timers() { return timers.size },
        node: predicate => { const found = nodes(render()).find(predicate); assert.ok(found, "UI node exists"); return found },
        html: () => renderToStaticMarkup(render()),
        input: (label, value) => h.node(n => n.props?.["aria-label"] === label).props.onChange({ target: { value } }),
        submit: text => h.node(n => n.type === "form" && nodes(n).some(child => child.type === "button" && child.props.children === text)).props.onSubmit({ preventDefault() {} }),
        click: text => h.node(n => n.type === "button" && n.props.children === text).props.onClick(),
        timeout: () => { const pending = [...timers.values()]; pending.forEach(fn => fn()) },
        session: (uid, notify = false) => { token = uid ? jwt(uid) : ""; if (notify) listeners.get("storage")?.({ key: "verity_supabase_session" }) },
    }
    render(); h.cleanup = effects[0]()
    return h
}

test("mount is GET only, accepts owned bare arrays and selects existing ticker", async () => {
    const h = harness(); await flush()
    assert.equal(h.requests.length, 1); assert.equal(h.requests[0].method, "GET")
    assert.match(h.html(), /AlphaNest 계정과 공유/)
    h.node(n => n.props?.["aria-label"] === "Microsoft 분석 보기").props.onClick()
    assert.deepEqual(h.selected, [["MSFT", "Microsoft"]]); assert.equal(h.scrolls.length, 1)
    assert.equal(h.timers, 0); h.cleanup()
})

for (const [label, body] of [
    ["object envelope", { groups: [] }],
    ["foreign group", [{ ...groups()[0], user_id: "other-owner" }]],
    ["misplaced item", [{ ...groups()[0], items: [{ ...item, group_id: "other-group" }] }]],
]) test(`malformed/foreign GET fails closed: ${label}`, async () => {
    const h = harness({ fetch: async () => response(body) }); await flush()
    assert.match(h.html(), /읽지 못했습니다/); assert.doesNotMatch(h.html(), /Microsoft 분석 보기/)
    assert.equal(h.node(n => n.props?.children === "그룹 만들기").props.disabled, true); h.cleanup()
})

test("named group creation needs explicit submit, one write, and confirming GET", async () => {
    const post = deferred(); let created = false
    const newGroup = { id: "group-2", user_id: owner, name: "반도체", items: [] }
    const h = harness({ fetch: async req => req.method === "POST" ? post.promise : response(created ? [...groups(), newGroup] : groups()) })
    await flush(); h.input("새 관심 그룹 이름", " 반도체 ")
    assert.equal(h.requests.length, 1)
    h.submit("그룹 만들기"); h.submit("그룹 만들기"); await flush()
    assert.equal(h.requests.filter(r => r.method === "POST").length, 1)
    assert.deepEqual(h.requests[1].body, { action: "create_group", name: "반도체" })
    created = true; post.resolve(response(newGroup, 201)); await flush()
    assert.equal(h.requests.at(-1).method, "GET")
    assert.equal(h.node(n => n.props?.["aria-label"] === "관심 그룹").props.value, "group-2")
    assert.match(h.html(), /저장하고 최신 목록에서 확인/); h.cleanup()
})

test("add preserves KR leading zeros and optional name; no user_id is sent", async () => {
    const added = { id: "item-2", group_id: "group-1", ticker: "005930", name: "삼성전자", market: "kr" }
    let changed = false
    const h = harness({ fetch: async req => {
        if (req.method === "POST") { changed = true; return response(added, 201) }
        return response([{ ...groups()[0], items: changed ? [item, added] : [item] }])
    } })
    await flush(); h.input("저장할 티커 또는 종목코드", " 005930 "); h.input("저장할 기업명", "삼성전자"); h.input("저장할 종목 시장", "kr")
    h.submit("기업 추가"); await flush()
    assert.deepEqual(h.requests[1].body, { action: "add_item", group_id: "group-1", ticker: "005930", name: "삼성전자", market: "kr" })
    assert.match(h.html(), /삼성전자/)
    h.input("저장할 티커 또는 종목코드", "msft"); h.input("저장할 종목 시장", "us"); h.submit("기업 추가"); await flush()
    assert.equal(h.requests.filter(r => r.method === "POST").length, 1); assert.match(h.html(), /이미 저장된 종목/); h.cleanup()
})

test("remove requires confirmation, cancellation writes nothing, DELETE is read back", async () => {
    let removed = false
    const h = harness({ fetch: async req => {
        if (req.method === "DELETE") { removed = true; return response({ ok: true }) }
        return response([{ ...groups()[0], items: removed ? [] : [item] }])
    } })
    await flush(); h.click("제외"); h.click("취소"); assert.equal(h.requests.length, 1)
    h.click("제외"); h.click("제외 확인"); await flush()
    assert.deepEqual(h.requests[1].body, { action: "remove_item", item_id: "item-1" })
    assert.equal(h.requests[1].method, "DELETE"); assert.equal(h.requests.at(-1).method, "GET")
    assert.match(h.html(), /저장된 기업이 없습니다/); h.cleanup()
})

for (const [market, value, message] of [["kr", "5930", /숫자 6자리/], ["us", "not a ticker", /미국 티커/]]) test(`unsupported ${market} input does not send a write`, async () => {
    const h = harness(); await flush()
    h.input("저장할 티커 또는 종목코드", value); h.input("저장할 종목 시장", market); h.submit("기업 추가"); await flush()
    assert.equal(h.requests.length, 1); assert.match(h.html(), message); h.cleanup()
})

test("add readback in a different group is not confirmed", async () => {
    const added = { id: "item-2", group_id: "group-1", ticker: "TSM", name: "", market: "us" }
    let changed = false
    const h = harness({ fetch: async req => {
        if (req.method === "POST") { changed = true; return response(added, 201) }
        return response(changed ? [...groups(), { id: "group-2", user_id: owner, name: "다른 그룹", items: [{ ...added, group_id: "group-2" }] }] : groups())
    } })
    await flush(); h.input("저장할 티커 또는 종목코드", "TSM"); h.submit("기업 추가"); await flush()
    assert.match(h.html(), /변경 응답은 받았지만 최신 목록 확인에 실패/); h.cleanup()
})

test("write acknowledgement + readback failure is not a write failure; manual GET unlocks", async () => {
    let changed = false, fail = true
    const h = harness({ fetch: async req => {
        if (req.method === "DELETE") { changed = true; return response({ ok: true }) }
        if (changed && fail) return response({}, 503)
        return response([{ ...groups()[0], items: changed ? [] : [item] }])
    } })
    await flush(); h.click("제외"); h.click("제외 확인"); await flush()
    assert.match(h.html(), /변경 응답은 받았지만 최신 목록 확인에 실패/)
    assert.equal(h.node(n => n.props?.children === "그룹 만들기").props.disabled, true)
    const before = h.requests.length; h.submit("그룹 만들기"); await flush(); assert.equal(h.requests.length, before)
    fail = false; h.click("목록 새로고침"); await flush()
    assert.match(h.html(), /최신 목록을 다시 읽었습니다/); assert.equal(h.requests.at(-1).method, "GET"); h.cleanup()
})

for (const failure of ["timeout", "transport", "invalid acknowledgement"]) test(`unknown mutation is never retried: ${failure}`, async () => {
    const post = deferred()
    const h = harness({ fetch: async req => {
        if (req.method === "GET") return response(groups())
        if (failure === "timeout") return post.promise
        if (failure === "transport") throw new TypeError("synthetic transport failure")
        return response([], 201)
    } })
    await flush(); h.input("새 관심 그룹 이름", "미확인"); h.submit("그룹 만들기"); await flush()
    if (failure === "timeout") { h.timeout(); await flush() }
    assert.match(h.html(), /변경이 반영되었을 수/)
    h.submit("그룹 만들기"); await flush()
    assert.equal(h.requests.filter(r => r.method === "POST").length, 1)
    assert.equal(h.node(n => n.props?.children === "그룹 만들기").props.disabled, true)
    h.cleanup(); post.resolve(response({ id: "late" }, 201)); await flush()
})

test("auth timeout/unmount never sends a late request or writes component state", async () => {
    const auth = deferred(), h = harness({ refresh: () => auth.promise })
    h.timeout(); await flush()
    assert.match(h.html(), /읽지 못했습니다/); assert.equal(h.requests.length, 0)
    h.cleanup(); const before = h.writes; auth.resolve(true); await flush()
    assert.equal(h.requests.length, 0); assert.equal(h.writes, before); assert.equal(h.timers, 0)
})

for (const storage of [false, true]) test(`owner switch discards old response; storage notification=${storage}`, async () => {
    const body = deferred()
    const h = harness({ fetch: async () => ({ ok: true, status: 200, json: () => body.promise }) })
    await flush(); h.session("synthetic-owner-b", storage); body.resolve(groups()); await flush()
    assert.doesNotMatch(h.html(), /Microsoft 분석 보기/)
    assert.match(h.html(), /로그인 상태/); h.cleanup()
})

test("unmount during mutation discards late acknowledgement and skips readback", async () => {
    const post = deferred()
    const h = harness({ fetch: async req => req.method === "GET" ? response(groups()) : post.promise })
    await flush(); h.input("새 관심 그룹 이름", "늦은 응답"); h.submit("그룹 만들기"); await flush()
    h.cleanup(); const before = h.writes
    post.resolve(response({ id: "group-2", user_id: owner, name: "늦은 응답" }, 201)); await flush()
    assert.equal(h.writes, before); assert.equal(h.requests.length, 2); assert.equal(h.timers, 0)
})

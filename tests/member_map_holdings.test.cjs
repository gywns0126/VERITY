const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const test = require("node:test")
const vm = require("node:vm")

const snapshotPath = path.resolve(__dirname, "../review/member-map/Map.snapshot.tsx")
const source = fs.readFileSync(snapshotPath, "utf8")
const between = (start, end) => {
    const from = source.indexOf(start), to = source.indexOf(end, from)
    assert.notEqual(from, -1, `missing snapshot marker: ${start}`)
    assert.notEqual(to, -1, `missing snapshot marker: ${end}`)
    return source.slice(from, to)
}
const draft = between("// framer-components/public-probe/PortfolioHoldingsDraft.ts", "// framer-components/public-probe/PortfolioHoldingsList.tsx")
const editor = between("// framer-components/public-probe/PortfolioHoldingsEditor.ts", "// framer-components/public-probe/PublicPortfolioPrototype.tsx")
const box = { exports: {} }
vm.runInNewContext(`
const __publicField = (target, key, value) => (target[key] = value, value);
${draft}
${editor}
exports.createPortfolioHoldingsEditor = createPortfolioHoldingsEditor;
exports.previewHoldingChange = previewHoldingChange;
`, { module: box, exports: box.exports, AbortController, setTimeout, clearTimeout, JSON, Map, Set, Number, Object, Array, String, Promise, Error })
const { createPortfolioHoldingsEditor } = box.exports
const clone = value => JSON.parse(JSON.stringify(value))
const reply = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => clone(body) })
const A = { userId: "11111111-1111-4111-8111-111111111111", token: "snapshot-A" }
const B = { userId: "22222222-2222-4222-8222-222222222222", token: "snapshot-B" }
const raw = { id: "holding-1", ticker: "AAPL", name: "Apple", market: "us", shares: 2, avg_cost: 100, memo: "before" }
const records = [{ ...raw, market: "US", duplicate: false }]

function harness({ fresh = [raw], write } = {}) {
    let session = A
    const calls = []
    const editor = createPortfolioHoldingsEditor({ getSession: () => session, fetcher: async (url, init = {}) => {
        calls.push({ url, init })
        if (!init.method) return reply(200, fresh)
        return write ? write(url, init) : reply(200, { ...raw, memo: "after" })
    } })
    return { editor, calls, session: value => { session = value } }
}

test("generated snapshot prepare is pure and confirm uses fresh GET then a partial PATCH", async () => {
    const h = harness()
    const preview = h.editor.prepare(records, { kind: "edit", id: "holding-1", memo: "after" })
    assert.equal(h.calls.length, 0)
    await h.editor.confirm(preview)
    assert.equal(h.calls.length, 2)
    assert.equal(h.calls[0].init.method, undefined)
    assert.equal(h.calls[1].init.method, "PATCH")
    assert.deepEqual(clone(JSON.parse(h.calls[1].init.body)), { id: "holding-1", memo: "after" })
})

test("generated snapshot refuses stale fresh rows without a write", async () => {
    const h = harness({ fresh: [{ ...raw, shares: 3 }] })
    const preview = h.editor.prepare(records, { kind: "edit", id: "holding-1", memo: "after" })
    await assert.rejects(() => h.editor.confirm(preview), /preflight-stale/)
    assert.equal(h.calls.length, 1)
})

test("generated snapshot rejects a delayed write response after account switch", async () => {
    let resolveWrite, session = A, calls = [], saved = 0
    const editor = createPortfolioHoldingsEditor({ getSession: () => session, onSaved: () => { saved += 1 }, fetcher: (url, init = {}) => {
        calls.push({ url, init })
        if (!init.method) return Promise.resolve(reply(200, [raw]))
        return new Promise(resolve => { resolveWrite = resolve })
    } })
    const pending = editor.confirm(editor.prepare(records, { kind: "edit", id: "holding-1", memo: "after" }))
    await new Promise(resolve => setTimeout(resolve, 0))
    session = B; resolveWrite(reply(200, { ...raw, memo: "after" }))
    await assert.rejects(() => pending, /session-changed/)
    assert.equal(calls.length, 2)
    assert.equal(saved, 0)
})

test("generated snapshot accepts formatted numeric API rows for fresh comparison", async () => {
    const h = harness({ fresh: [{ ...raw, shares: "2.0", avg_cost: "₩100원" }] })
    const preview = h.editor.prepare(records, { kind: "edit", id: "holding-1", memo: "after" })
    await h.editor.confirm(preview)
    assert.equal(h.calls.length, 2)
})

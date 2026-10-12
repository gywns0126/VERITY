// Extracted focused synthetic regressions from portfolio_prototype_host.test.cjs.
// Executes this checkout's exact flattened snapshot and canvas; no root TS, real storage or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const adjacentRoot = path.resolve(__dirname, '..');
const root = fs.existsSync(path.join(adjacentRoot, 'review/member-map/Map.snapshot.tsx')) ? adjacentRoot : process.cwd();
const dependencyRoot = path.resolve(process.env.MEMBER_MAP_TEST_DEPENDENCY_ROOT || root);
const esbuild = createRequire(path.join(dependencyRoot, 'package.json'))('esbuild');
const snapshot = fs.readFileSync(path.join(root, 'review/member-map/Map.snapshot.tsx'), 'utf8');
const compiled = esbuild.transformSync(snapshot + '\nexport { mergePrototypeDraft, prototypeMemberModel, mountMemberPrototype, validMapDocument };', {loader:'tsx',format:'cjs',target:'es2022'}).code;
const built = {outputFiles:[{text:compiled}]};
const snapshotRequire = name => {
    if (name === 'react') return {};
    if (name === 'framer') return {addPropertyControls(){},ControlType:{Number:'number'},useIsStaticRenderer:()=>false};
    throw Error('Unexpected snapshot import: ' + name);
};
const box = {exports:{}};
vm.runInNewContext(compiled, {module:box,exports:box.exports,require:snapshotRequire,Map,Set,Object,Array,Number,String,JSON,URL,TextEncoder,AbortController,MessageChannel,console});
const {mergePrototypeDraft,prototypeMemberModel,validMapDocument} = box.exports;
const canvas = fs.readFileSync(path.join(root, 'vercel-api/public/member-map-canvas.html'), 'utf8');
const runtimeStart = 'let memberWritable=', runtimeEnd = "memberPort.postMessage({type:'hydrated',...memberOriginStamp()});";
assert.equal(canvas.split(runtimeStart).length, 2);
assert.equal(canvas.split(runtimeEnd).length, 2);
const runtimeSource = canvas.slice(canvas.indexOf(runtimeStart), canvas.indexOf(runtimeEnd) + runtimeEnd.length);
assert.ok(runtimeSource.includes('const prototypeRenderMap='));

const clone = value => JSON.parse(JSON.stringify(value))

const graph = {
    companies: [{ id: 'company-tick', ticker: 'TICK', name: '회사', market: 'KR' }],
    documents: [{ id: 'document-1', kind: 'source-document', title: '문서', url: 'https://example.test/document', source: '공시', asOf: '2026-10-01', reason: '자료 사유', confirmation: 'confirmed', isCorrection: false, evidence: [], tickers: ['TICK'], read_revision: 50, contentHash: 'hash' }],
    links: [{ id: 'edge-1', companyId: 'company-tick', documentId: 'document-1', ticker: 'TICK', source: '공시', asOf: '2026-10-01', reason: '자료 사유', confirmation: 'confirmed', isCorrection: false, evidence: [] }],
    commonItems: [], coverage: { includedTickers: ['TICK'], availableTickers: ['TICK'], excluded: [] },
}

const prior = {
    map_key: 'main',
    positions: [
        { node_id: 'company-tick', x: 420, y: 204 },
        { node_id: 'hidden-position', x: 1201, y: -51 },
    ],
    notes: [{ note_id: 'note-1', anchor: { kind: 'edge', id: 'edge-1' }, x: -25, y: 701, text: '기존 메모', done: false }],
    marks: {
        'document-1': { read_revision: 40, important: true, disposition: 'later' },
        'hidden-document': { read_revision: 9, important: false, disposition: 'inbox' },
    },
}

const state = (overrides = {}) => ({ phase: 'ready', holdings: [], unsupportedCount: 0, selectedTickers: ['TICK'], graph, privateState: { phase: 'ready', document: { layouts: [clone(prior)] }, revision: 3, dirty: false, error: null }, error: null, ...overrides })

const draft = (overrides = {}) => ({ positions: [{ id: 'company-tick', x: .5 + 420 / 1000, y: .5 + 204 / 680 }], notes: [{ id: 'note-1', target: 'edge-1', x: .5 - 25 / 1000, y: .5 + 701 / 680, text: '기존 메모', done: false }], marks: {}, ...overrides })

const rejectionCases = [
    ['state_unready', () => [state({ phase: 'signed-out' }), draft()], [1, 1, 0]],
    ['draft_shape', () => [state(), null], [null, null, null]],
    ['positions_shape', () => [state(), draft({ positions: {} })], [null, 1, 0]],
    ['notes_shape', () => [state(), draft({ notes: null })], [1, null, 0]],
    ['marks_shape', () => [state(), draft({ marks: [] })], [1, 1, null]],
    ['positions_limit', () => [state(), draft({ positions: Array.from({ length: 201 }, () => ({ id: 'company-tick', x: .5, y: .5 })) })], [201, 1, 0]],
    ['notes_limit', () => [state(), draft({ notes: Array.from({ length: 101 }, () => draft().notes[0]) })], [1, 101, 0]],
    ['marks_limit', () => [state(), draft({ marks: Object.fromEntries(Array.from({ length: 201 }, (_, i) => ['synthetic-' + i, {}])) })], [1, 1, 201]],
    ['position_coordinates', () => [state(), draft({ positions: [{ id: 'company-tick', x: NaN, y: .5 }] })], [1, 1, 0]],
    ['position_identity', () => [state(), draft({ positions: [{ id: 'SYNTHETIC-UNKNOWN-ID', x: .5, y: .5 }] })], [1, 1, 0]],
    ['position_identity', () => [state(), draft({ positions: [draft().positions[0], draft().positions[0]] })], [2, 1, 0]],
    ['notes_shape', () => [state(), draft({ notes: [{ ...draft().notes[0], x: Infinity }] })], [1, 1, 0]],
    ['notes_identity', () => [state(), draft({ notes: [{ ...draft().notes[0], id: 'SYNTHETIC-NEW-ID' }] })], [1, 1, 0]],
    ['notes_anchor', () => [state(), draft({ notes: [{ ...draft().notes[0], target: 'SYNTHETIC-UNKNOWN-ANCHOR' }] })], [1, 1, 0]],
    ['mark_identity', () => [state(), draft({ marks: { 'SYNTHETIC-UNKNOWN-MARK': {} } })], [1, 1, 1]],
    ['mark_shape', () => [state(), draft({ marks: { 'document-1': { read: 'SYNTHETIC-NONBOOLEAN' } } })], [1, 1, 1]],
    ['final_schema', () => [state(), draft({ notes: [{ ...draft().notes[0], text: 'x'.repeat(2001) }] })], [2, 1, 2]],
    ['final_schema', () => [state(), draft({ positions: [{ id: 'company-tick', x: 1001, y: .5 }] })], [2, 1, 2]],
    ['final_schema', () => [state(), draft({ notes: [draft().notes[0], draft().notes[0]] })], [2, 2, 2]],
]

for (const [index, [code, fixture, counts]] of rejectionCases.entries()) {
    test(`draft rejection ${index + 1}: ${code} reports only fixed code/counts and preserves null API`, () => {
        const [current, value] = fixture(), before = clone(current), input = structuredClone(value), rejected = []
        assert.equal(mergePrototypeDraft(current, value), null)
        assert.equal(mergePrototypeDraft(current, value, result => rejected.push(clone(result))), null)
        assert.deepEqual(rejected, [{ code, positions: counts[0], notes: counts[1], marks: counts[2] }])
        assert.equal(mergePrototypeDraft(current, value, () => { throw Error('SYNTHETIC-CALLBACK-ERROR') }), null)
        assert.deepEqual(current, before)
        assert.deepEqual(value, input)
        assert.doesNotMatch(JSON.stringify(rejected), /SYNTHETIC|company-tick|document-1|edge-1|note-1|기존 메모/)
    })
}

for (const field of ['positions', 'marks']) test(`final_schema counts retained offscreen ${field} instead of only incoming draft`, () => {
    const current = state(), layout = current.privateState.document.layouts[0]
    if (field === 'positions') layout.positions = Array.from({ length: 200 }, (_, i) => ({ node_id: 'hidden-' + i, x: i, y: -(i + 1) }))
    else layout.marks = Object.fromEntries(Array.from({ length: 200 }, (_, i) => ['hidden-' + i, { read_revision: 9, important: false, disposition: 'inbox' }]))
    assert.equal(validMapDocument(current.privateState.document), true)
    const value = draft({ marks: field === 'marks' ? { 'document-1': { read: true } } : {} })
    const before = clone(current), rejected = []
    assert.equal(mergePrototypeDraft(current, value, result => rejected.push(clone(result))), null)
    assert.deepEqual(rejected, [{ code: 'final_schema', positions: field === 'positions' ? 201 : 2,
        notes: 1, marks: field === 'marks' ? 201 : 2 }])
    assert.deepEqual(current, before)
})

test('successful diagnostic merge keeps exact prior notes, hidden records and stale read revision without callbacks', () => {
    const current = state(), value = draft(), before = clone(current), rejected = []
    const next = mergePrototypeDraft(current, value, reason => rejected.push(reason))
    assert.deepEqual(rejected, [])
    assert.deepEqual(clone(next), before.privateState.document.layouts[0])
    assert.equal(validMapDocument({ layouts: [clone(next)] }), true)
    assert.deepEqual(current, before)
})

function focusHarness(options = {}) {
    let owner = 'owner-a', current = state(), subscriber, nonce = 0
    const listeners = {}, frameListeners = {}, channels = [], messages = [], frameMessages = []
    const window = { location: {href:'https://fixture.test/review',origin:'https://fixture.test'}, addEventListener: (type, fn) => { listeners[type] = fn }, removeEventListener: type => { delete listeners[type] } }
    class Channel {
        constructor() {
            this.port1 = { onmessage: null, closed: false, postMessage: data => messages.push(clone(data)), close() { this.closed = true } }
            this.port2 = {}
            channels.push(this)
        }
    }
    const module = { exports: {} }
    vm.runInNewContext(built.outputFiles[0].text, { module, exports: module.exports, require: snapshotRequire, window, URL, AbortController, MessageChannel: Channel, crypto: { randomUUID: () => String(++nonce) } })
    const frame = { style: {}, contentWindow: { postMessage(data) { frameMessages.push(data) } }, setAttribute() {}, removeAttribute() {},
        addEventListener: (type, fn) => { frameListeners[type] = fn }, removeEventListener: type => { delete frameListeners[type] } }
    // Match the real workspace: every read and subscriber notification is a fresh clone.
    const workspace = { getState: () => clone(current), subscribe: fn => { subscriber = fn;fn(clone(current));return () => { subscriber = null } },
        editLayout: () => assert.fail('focus must not edit'), save: () => assert.fail('focus must not save') }
    const bridge = module.exports.mountMemberPrototype(frame, "'__ALPHANEST_FRAME_NONCE__'", workspace, { account: () => owner, ...options })
    const connect = () => {
        listeners.message({ source: frame.contentWindow, origin: 'null', data: { type: 'alphanest-member-ready', nonce: JSON.parse(frame.srcdoc) } })
        return channels.at(-1)?.port1
    }
    return { bridge, messages, frameMessages, channels, connect, frame, workspace,
        setOwner: value => { owner = value },
        emit: next => { current = { ...current, ...next };subscriber?.(clone(current)) },
        hydrate: port => port.onmessage({ data: { type: 'hydrated', originGeneration: messages.findLast(m => m.type === 'init').model.originGeneration } }),
        focusMessages: () => messages.filter(m => m.type === 'focus-stock') }
}

for (const code of ['notes_anchor', 'local_view', 'workspace_rejected']) test(`status ${code} exposes only code/counts, blocks saving, and clears on successful edit`, async () => {
    const hiddenWrites = []
    const h = focusHarness(code === 'local_view' ? { localView: { getHiddenStockIds: () => [], setHiddenStockIds: ids => hiddenWrites.push(ids) } } : {})
    const port = h.connect();await h.hydrate(port)
    const originGeneration = h.messages.findLast(m => m.type === 'init').model.originGeneration
    const before = h.workspace.getState().privateState.document
    let saves = 0, edits = 0
    h.workspace.save = async () => { saves++;return true }
    h.workspace.editLayout = () => { edits++;return false }
    try {
        const bad = draft({ notes: [{ ...draft().notes[0], text: 'SYNTHETIC-PRIVATE-TEXT',
            ...(code === 'notes_anchor' ? { target: 'SYNTHETIC-PRIVATE-ID' } : {}) }],
            ...(code === 'local_view' ? { hiddenStockIds: ['SYNTHETIC-PRIVATE-ID'] } : {}) })
        await port.onmessage({ data: { type: 'edit', originGeneration, draft: bad } })
        await port.onmessage({ data: { type: 'save', originGeneration } })
        const status = h.messages.at(-1)
        assert.equal(status.type, 'status')
        const counts = code === 'workspace_rejected' ? 'positions=2, notes=1, marks=2' : 'positions=1, notes=1, marks=0'
        assert.ok(status.message.endsWith(`(${code}; ${counts})`))
        assert.doesNotMatch(JSON.stringify(status), /SYNTHETIC|company-tick|document-1|edge-1|note-1|기존 메모/)
        assert.equal(saves, 0);assert.equal(edits, code === 'workspace_rejected' ? 1 : 0)
        assert.deepEqual(hiddenWrites, [])
        assert.deepEqual(h.workspace.getState().privateState.document, before)
        h.workspace.editLayout = (_key, change) => {
            const current = h.workspace.getState()
            h.emit({ privateState: { ...current.privateState, document: { layouts: [change(current.privateState.document.layouts[0])] }, dirty: true } })
            return true
        }
        await port.onmessage({ data: { type: 'edit', originGeneration, draft: draft({ hiddenStockIds: [] }) } })
        assert.doesNotMatch(h.messages.at(-1).message, /notes_anchor|local_view|workspace_rejected|positions=/)
        await port.onmessage({ data: { type: 'save', originGeneration } })
        assert.equal(saves, 1)
        assert.deepEqual(h.workspace.getState().privateState.document, before)
    } finally { h.bridge() }
})

test('closing a rejected frame clears diagnostic counts before a fresh frame hydrates', async () => {
    const h = focusHarness(), port = h.connect();await h.hydrate(port)
    const originGeneration = h.messages.findLast(m => m.type === 'init').model.originGeneration
    await port.onmessage({ data: { type: 'edit', originGeneration, draft: null } })
    assert.match(h.messages.at(-1).message, /\(draft_shape; positions=\?, notes=\?, marks=\?\)$/)
    h.emit({ privateState: { ...state().privateState, phase: 'loading' } })
    h.emit({ privateState: state().privateState })
    const replacement = h.connect();await h.hydrate(replacement)
    assert.equal(port.closed, true)
    assert.doesNotMatch(h.messages.at(-1).message, /draft_shape|positions=/)
    h.bridge()
})

function originRuntime(model, localView = true) {
    const outgoing = [], context = {
        member: clone(model), memberLocalView: localView, memberSaveButton: {},
        nodes: clone(model.nodes), state: { scenario: 'basic', notes: clone(model.notes), marks: clone(model.marks) },
        boardDraft: { basic: { hidden: [] } }, nodeById: {},
        memberPort: { postMessage: message => outgoing.push(clone(message)) },
    }
    context.updateMemberGraph = next => {
        // updateMemberGraph emits after cancel/rebase; the protocol must suppress
        // that intermediate emission until the generation has advanced.
        context.nodes = clone(next.nodes)
        const ids = new Set(next.nodes.map(n => n.id))
        for (const id of Object.keys(context.state.marks)) if (!ids.has(id)) delete context.state.marks[id]
        Object.assign(context.state.marks, clone(next.marks))
        context.emitMemberDraft(true)
    }
    vm.runInNewContext(runtimeSource.slice(runtimeSource.indexOf('let memberWritable='), runtimeSource.indexOf('const prototypeRenderMap=')), context)
    vm.runInNewContext('lastDraft=JSON.stringify(memberDraft())', context)
    vm.runInNewContext(runtimeSource.slice(runtimeSource.lastIndexOf("memberPort.postMessage({type:'hydrated',")), context)
    return { context, outgoing }
}

for (const count of [110, 199]) test(`actual canvas serializer with synthetic ${count} documents and two stocks reaches the unchanged merge boundary`, () => {
    const current = state(), expanded = clone(graph)
    expanded.companies.push({ id: 'company-other', ticker: 'OTHER', market: 'US', name: '합성 회사' })
    expanded.documents = Array.from({ length: count }, (_, i) => ({ ...clone(graph.documents[0]), id: 'document-' + (i + 1) }))
    current.graph = expanded
    const before = clone(current), model = prototypeMemberModel(current), frame = originRuntime(model, false)
    frame.outgoing.length = 0
    frame.context.memberSaveButton.onclick()
    const [edit, save] = frame.outgoing
    assert.equal(edit.type, 'edit');assert.equal(save.type, 'save')
    // JSON round-trip is the existing harness transport, not real browser storage.
    const value = clone(edit.draft), rejected = []
    assert.equal(value.positions.length, count + 2)
    assert.equal(value.notes.length, 1);assert.equal(Object.keys(value.marks).length, count)
    const next = mergePrototypeDraft(current, value, reason => rejected.push(clone(reason)))
    if (count === 199) {
        assert.equal(next, null)
        assert.deepEqual(rejected, [{ code: 'positions_limit', positions: 201, notes: 1, marks: 199 }])
    } else {
        assert.ok(next);assert.deepEqual(rejected, [])
        assert.equal(validMapDocument({ layouts: [clone(next)] }), true)
        assert.equal(next.positions.length, 113) // Includes the retained offscreen position.
        assert.deepEqual(next.positions.find(p => p.node_id === 'hidden-position'), prior.positions[1])
        assert.deepEqual(clone(next.notes), prior.notes)
        assert.deepEqual(clone(next.marks['document-1']), prior.marks['document-1'])
        assert.deepEqual(clone(next.marks['hidden-document']), prior.marks['hidden-document'])
        assert.deepEqual(clone(prototypeMemberModel({ ...current, privateState: { ...current.privateState, document: { layouts: [next] } } }).notes), clone(model.notes))
    }
    assert.deepEqual(current, before)
})

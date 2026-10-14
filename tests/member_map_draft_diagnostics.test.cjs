// Extracted focused synthetic regressions from portfolio_prototype_host.test.cjs.
// Executes this checkout's exact flattened snapshot and canvas; no root TS, real storage or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const adjacentRoot = path.resolve(__dirname, '..');
const root = process.env.MEMBER_MAP_TEST_SOURCE_ROOT || (fs.existsSync(path.join(adjacentRoot, 'review/member-map/Map.snapshot.tsx')) ? adjacentRoot : process.cwd());
const dependencyRoot = path.resolve(process.env.MEMBER_MAP_TEST_DEPENDENCY_ROOT || root);
const esbuild = createRequire(path.join(dependencyRoot, 'package.json'))('esbuild');
const snapshot = fs.readFileSync(path.join(root, 'review/member-map/Map.snapshot.tsx'), 'utf8');
const compiled = esbuild.transformSync(snapshot + '\nexport { mergePrototypeDraft, prototypeMemberModel, mountMemberPrototype, validMapDocument, editMapLayout, projectWorkspaceToPrototype };', {loader:'tsx',format:'cjs',target:'es2022'}).code;
const built = {outputFiles:[{text:compiled}]};
const snapshotRequire = name => {
    if (name === 'react') return {};
    if (name === 'framer') return {addPropertyControls(){},ControlType:{Number:'number'},useIsStaticRenderer:()=>false};
    throw Error('Unexpected snapshot import: ' + name);
};
const box = {exports:{}};
vm.runInNewContext(compiled, {module:box,exports:box.exports,require:snapshotRequire,Map,Set,Object,Array,Number,String,JSON,URL,TextEncoder,AbortController,MessageChannel,console});
const {mergePrototypeDraft,prototypeMemberModel,validMapDocument,editMapLayout,projectWorkspaceToPrototype} = box.exports;
const canvas = fs.readFileSync(path.join(root, 'vercel-api/public/member-map-canvas.html'), 'utf8');
const runtimeStart = 'let memberWritable=', runtimeEnd = "memberPort.postMessage({type:'hydrated',...memberOriginStamp()});";
assert.equal(canvas.split(runtimeStart).length, 2);
assert.equal(canvas.split(runtimeEnd).length, 2);
const graphUpdateStart = 'function updateMemberGraph(model,ticker){';
assert.equal(canvas.split(graphUpdateStart).length, 2);
const runtimeSource = canvas.slice(canvas.indexOf(graphUpdateStart), canvas.indexOf(runtimeEnd) + runtimeEnd.length);
assert.ok(runtimeSource.includes('const prototypeRenderMap='));
const groupingStart = 'const groupingUpdate=updateMemberGraph;';
assert.equal(canvas.split(groupingStart).length, 2);
const groupingRuntimeSource = canvas.slice(canvas.indexOf(groupingStart), canvas.indexOf('\n};', canvas.indexOf(groupingStart)) + 4);

const clone = value => JSON.parse(JSON.stringify(value))

const graph = {
    companies: [{ id: 'company-tick', ticker: 'TICK', name: '회사', market: 'KR' }],
    documents: [{ id: 'document-1', kind: 'source-document', title: '문서', url: 'https://example.test/document', source: '공시', asOf: '2026-10-01', reason: '자료 사유', confirmation: 'confirmed', isCorrection: false, evidence: [], tickers: ['TICK'], read_revision: 50, contentHash: 'hash' }],
    links: [{ id: 'edge-1', companyId: 'company-tick', documentId: 'document-1', ticker: 'TICK', source: '공시', asOf: '2026-10-01', reason: '자료 사유', confirmation: 'confirmed', isCorrection: false, evidence: [] }],
    commonItems: [], coverage: { includedTickers: ['TICK'], availableTickers: ['TICK'], excluded: [] },
}

const prior = {
    map_key: 'main_v2',
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

function legacyState() {
    const current = state(), main = { ...clone(prior), map_key: 'main' }
    main.positions.push({ node_id: 'document-1', x: -310, y: 120 })
    current.privateState.document.layouts = [main]
    return current
}

test('emitted legacy stock delta survives v2 migration, one-to-four documents and reconnect without rewriting main', () => {
    const current = legacyState(), before = clone(current), model = prototypeMemberModel(current)
    const oldStock = projectWorkspaceToPrototype(current).nodes.find(n => n.id === 'company-tick')
    const unsaved = clone(current);unsaved.privateState.document.layouts = []
    const oldBase = projectWorkspaceToPrototype(unsaved).nodes.find(n => n.id === oldStock.id)
    const delta = { x: oldStock.x - oldBase.x, y: oldStock.y - oldBase.y }
    const stock = model.nodes.find(n => n.id === 'company-tick'), source = model.nodes.find(n => n.id === 'document-1')
    const assertStockDelta = (view, label) => {
        const found = view.nodes.find(n => n.id === stock.id), base = view.layoutBases[stock.id]
        assert.deepEqual(clone(base), { x: .5, y: .5 }, label)
        assert.ok(Math.abs(found.x - base.x - delta.x) < 1e-12, `${label}: x delta is preserved`)
        assert.ok(Math.abs(found.y - base.y - delta.y) < 1e-12, `${label}: y delta is preserved`)
    }
    assertStockDelta(model, 'first migration')
    assert.deepEqual([source.x, source.y], [.5, .5])
    assert.deepEqual(clone(model.layoutBases[source.id]), { x: .5, y: .5 })
    assert.equal(model.notes['note-1'].text, prior.notes[0].text)
    assert.equal(model.marks['document-1'].important, true)
    assert.deepEqual(current, before)
    const next = mergePrototypeDraft(current, { positions: [{ id: stock.id, x: stock.x, y: stock.y }], notes: Object.values(model.notes), marks: {} })
    assert.ok(next);assert.equal(next.map_key, 'main_v2')
    assert.equal(next.positions.length, 1)
    assert.equal(next.positions[0].node_id, stock.id)
    assert.ok(Math.abs(next.positions[0].x - delta.x * 1000) < 1e-10)
    assert.ok(Math.abs(next.positions[0].y - delta.y * 680) < 1e-10)
    assert.deepEqual(clone(next.notes), prior.notes);assert.deepEqual(clone(next.marks), prior.marks)
    assert.deepEqual(current, before, 'merge does not mutate or delete the legacy layout')
    const restored = clone(current);restored.privateState.document.layouts.push(clone(next))
    assert.equal(validMapDocument(restored.privateState.document), true)
    assert.deepEqual(restored.privateState.document.layouts[0], before.privateState.document.layouts[0])
    assertStockDelta(prototypeMemberModel(restored), 'saved v2 with one document')
    restored.graph.documents.push(...Array.from({ length: 3 }, (_, i) => ({ ...clone(graph.documents[0]), id: 'document-added-' + i })))
    assert.equal(restored.graph.documents.length, 4)
    const expandedUnsaved = clone(restored);expandedUnsaved.privateState.document.layouts = []
    const changedOldBase = projectWorkspaceToPrototype(expandedUnsaved).nodes.find(n => n.id === stock.id)
    assert.notDeepEqual({ x: changedOldBase.x, y: changedOldBase.y }, { x: oldBase.x, y: oldBase.y },
        'the fixture crosses a real legacy fallback grid change')
    assertStockDelta(prototypeMemberModel(restored), 'four documents')
    const reconnected = clone(restored), reloaded = prototypeMemberModel(reconnected)
    assertStockDelta(reloaded, 'reconnect after four documents')
    const reloadedStock = reloaded.nodes.find(n => n.id === stock.id)
    const again = mergePrototypeDraft(reconnected, { positions: [{ id: stock.id, x: reloadedStock.x, y: reloadedStock.y }],
        notes: Object.values(reloaded.notes), marks: {} })
    assert.ok(again)
    assert.deepEqual(clone(again), clone(next), 'saving after reconnect does not convert v2 pixels again')
    assert.deepEqual(reconnected.privateState.document.layouts[0], before.privateState.document.layouts[0])
    assert.deepEqual(reconnected.privateState.document.layouts[1], clone(next))
})

test('emitted already-saved v2 stock pixels bypass legacy conversion as document count changes', () => {
    const current = legacyState(), legacy = clone(current.privateState.document.layouts[0])
    current.privateState.document.layouts.push(clone(prior))
    for (const count of [1, 4]) {
        current.graph = { ...clone(graph), documents: Array.from({ length: count }, (_, i) => ({ ...clone(graph.documents[0]), id: 'document-' + (i + 1) })) }
        const reconnected = clone(current), model = prototypeMemberModel(reconnected)
        const stock = model.nodes.find(n => n.id === 'company-tick')
        assert.deepEqual(clone(model.layoutBases[stock.id]), { x: .5, y: .5 })
        assert.equal(stock.x, .5 + prior.positions[0].x / 1000)
        assert.equal(stock.y, .5 + prior.positions[0].y / 680)
        const next = mergePrototypeDraft(reconnected, { positions: [{ id: stock.id, x: stock.x, y: stock.y }],
            notes: Object.values(model.notes), marks: {} })
        assert.ok(next)
        assert.deepEqual(clone(next), prior, 'existing v2 coordinates and annotations remain byte-for-byte equivalent')
        assert.deepEqual(reconnected.privateState.document.layouts[0], legacy)
        assert.deepEqual(reconnected.privateState.document.layouts[1], prior)
    }
})

test('emitted main_v2 source movement survives reload and count changes with legacy main recoverable', () => {
    const current = legacyState(), legacy = clone(current.privateState.document.layouts[0])
    const model = prototypeMemberModel(current)
    const moved = mergePrototypeDraft(current, { positions: [{ id: 'document-1', x: .65, y: .4 }], notes: Object.values(model.notes), marks: {} })
    assert.ok(moved)
    const pixels = moved.positions.find(p => p.node_id === 'document-1')
    assert.ok(Math.abs(pixels.x - 150) < 1e-12 && Math.abs(pixels.y + 68) < 1e-12)
    current.privateState.document.layouts.push(clone(moved))
    const restored = prototypeMemberModel(current).nodes.find(n => n.id === 'document-1')
    assert.deepEqual([restored.x, restored.y], [.65, .4])
    current.graph = { ...clone(graph), documents: [{ ...clone(graph.documents[0]), id: 'document-added' }, ...clone(graph.documents)] }
    const refreshed = prototypeMemberModel(current), source = refreshed.nodes.find(n => n.id === 'document-1')
    assert.deepEqual([source.x, source.y], [.65, .4])
    const added = refreshed.nodes.find(n => n.id === 'document-added')
    assert.deepEqual([added.x, added.y], [.5, .5])
    assert.deepEqual(clone(refreshed.layoutBases['document-1']), { x: .5, y: .5 })
    assert.deepEqual(current.privateState.document.layouts[0], legacy)
    assert.equal(current.privateState.document.layouts[1].marks['hidden-document'].read_revision, 9)
})

test('emitted document, reviewed, candidate and market source bases are independent of graph size', () => {
    const current = state(), expanded = clone(graph)
    expanded.companies = [
        { id: 'company-skh', ticker: '000660', name: 'SK하이닉스', market: 'KR' },
        { id: 'company-tsm', ticker: 'TSM', name: 'Taiwan Semiconductor Manufacturing Company Ltd.', market: 'US' },
    ]
    expanded.documents = [{ ...clone(graph.documents[0]), id: 'document-extra', tickers: ['000660'] }]
    expanded.links = [];expanded.coverage = { includedTickers: ['000660', 'TSM'], availableTickers: ['000660', 'TSM'], excluded: [] }
    expanded.automaticRelations = [{ id: 'automatic:candidate:one', title: '관계 후보', participants: [{ id: 'KR:000660', name: 'SK하이닉스', role: 'from' }],
        reported: false, reason: '검수 자료', source: '공시', asOf: '2026-10-01', url: 'https://example.test/candidate', read_revision: 1 }]
    expanded.marketContext = [{ id: 'market:commodity:gold', kind: 'commodity', title: '금', summary: '시장 참고', source: '시장',
        url: 'https://example.test/gold', as_of: '2026-10-01', observed_at: null, value: null, change_pct: null, unit: null,
        company_ids: ['KR:000660'], basis: 'market-context', reason: '참고', read_revision: 1 }]
    Object.assign(current, { graph: expanded, selectedTickers: ['000660', 'TSM'], holdings: [
        { ticker: '000660', market: 'KR', shares: 1, avg_cost: 1, duplicate: false },
        { ticker: 'TSM', market: 'US', shares: 1, avg_cost: 1, duplicate: false },
    ] })
    current.privateState.document.layouts = [{ map_key: 'main_v2', positions: [], notes: [], marks: {} }]
    const first = prototypeMemberModel(current), sources = first.nodes.filter(n => n.kind !== 'stock')
    const kinds = new Set(sources.map(n => n.recordKind))
    for (const kind of ['document', 'event', 'relationship', 'market-context']) assert.ok(kinds.has(kind), kind)
    assert.ok(first.nodes.some(n => n.layer === 'candidates'), 'candidate projector is exercised')
    const next = clone(current);next.graph.documents.unshift({ ...clone(expanded.documents[0]), id: 'document-added' })
    const refreshed = prototypeMemberModel(next)
    for (const source of sources) {
        assert.deepEqual(clone(first.layoutBases[source.id]), { x: .5, y: .5 }, source.id)
        assert.deepEqual([source.x, source.y], [.5, .5], source.id)
        const found = refreshed.nodes.find(n => n.id === source.id)
        assert.ok(found, source.id)
        assert.deepEqual([found.x, found.y], [.5, .5], source.id)
        assert.deepEqual(clone(refreshed.layoutBases[source.id]), { x: .5, y: .5 }, source.id)
    }
})

test('emitted native bridge creates v2 once through the real layout editor while retaining main', async () => {
    const h = focusHarness(), current = legacyState(), legacy = clone(current.privateState.document.layouts[0])
    h.emit(current)
    try {
        const port = h.connect();await h.hydrate(port)
        const initial = h.messages.findLast(m => m.type === 'init').model
        let edits = 0, saves = 0
        h.workspace.editLayout = (key, change) => {
            assert.equal(key, 'main_v2');edits++
            const state = h.workspace.getState(), before = clone(state.privateState.document)
            const document = editMapLayout(state.privateState.document, key, change)
            assert.deepEqual(state.privateState.document, before, 'the real layout editor copies its input')
            assert.deepEqual(clone(document.layouts[0]), legacy)
            assert.equal(document.layouts.length, 2)
            h.emit({ privateState: { ...state.privateState, document: clone(document), dirty: true } })
            return true
        }
        h.workspace.save = async () => { saves++;return true }
        for (const x of [.75, .8]) {
            await port.onmessage({ data: { type: 'edit', originGeneration: initial.originGeneration,
                draft: { positions: [{ id: 'document-1', x, y: .25 }], notes: Object.values(initial.notes), marks: {} } } })
            await port.onmessage({ data: { type: 'save', originGeneration: initial.originGeneration } })
        }
        assert.equal(edits, 2);assert.equal(saves, 2)
        const state = h.workspace.getState(), layouts = state.privateState.document.layouts
        assert.deepEqual(layouts.map(layout => layout.map_key), ['main', 'main_v2'])
        assert.deepEqual(layouts[0], legacy)
        assert.deepEqual(layouts[1].notes, legacy.notes);assert.deepEqual(layouts[1].marks, legacy.marks)
        const restored = prototypeMemberModel(state).nodes.find(n => n.id === 'document-1')
        assert.deepEqual([restored.x, restored.y], [.8, .25])
    } finally { h.bridge() }
})

test('emitted native bridge refuses first v2 edit and save when three slots are occupied', async () => {
    const current = legacyState()
    current.privateState.document.layouts.push({ ...clone(prior), map_key: 'other_1' }, { ...clone(prior), map_key: 'other_2' })
    const before = clone(current), rejected = []
    assert.equal(validMapDocument(current.privateState.document), true)
    assert.equal(prototypeMemberModel(current).writable, false)
    assert.equal(mergePrototypeDraft(current, draft(), reason => rejected.push(clone(reason))), null)
    assert.deepEqual(rejected, [{ code: 'layout_limit', positions: 1, notes: 1, marks: 0 }])
    assert.deepEqual(current, before)
    const h = focusHarness();h.emit(current)
    try {
        const port = h.connect();await h.hydrate(port)
        const originGeneration = h.messages.findLast(m => m.type === 'init').model.originGeneration
        let edits = 0, saves = 0
        h.workspace.editLayout = () => { edits++;return true }
        h.workspace.save = async () => { saves++;return true }
        await port.onmessage({ data: { type: 'save', originGeneration } })
        await port.onmessage({ data: { type: 'edit', originGeneration, draft: draft() } })
        await port.onmessage({ data: { type: 'save', originGeneration } })
        assert.equal(edits, 0);assert.equal(saves, 0)
        assert.equal(h.messages.at(-1).writable, false)
        assert.match(h.messages.at(-1).message, /저장 슬롯/)
        assert.deepEqual(h.workspace.getState().privateState.document, before.privateState.document)
    } finally { h.bridge() }
    // Three slots are legal when v2 already exists: replacement needs no fourth slot.
    const existing = state();existing.privateState.document.layouts.push(...clone(current.privateState.document.layouts.slice(1)))
    assert.equal(prototypeMemberModel(existing).writable, true)
    assert.ok(mergePrototypeDraft(existing, draft()))
})

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
        context.nextDraftModel = next
        vm.runInNewContext('memberDraftOrigins=nextDraftModel.layoutBases||{}', context)
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
    assert.equal(value.positions.length, 1)
    assert.equal(value.notes.length, 1);assert.equal(Object.keys(value.marks).length, 1)
    const next = mergePrototypeDraft(current, value, reason => rejected.push(clone(reason)))
        assert.ok(next);assert.deepEqual(rejected, [])
        assert.equal(validMapDocument({ layouts: [clone(next)] }), true)
        assert.equal(next.positions.length, 2) // Defaults are omitted; both prior positions remain.
        assert.deepEqual(next.positions.find(p => p.node_id === 'hidden-position'), prior.positions[1])
        assert.deepEqual(clone(next.notes), prior.notes)
        assert.deepEqual(clone(next.marks['document-1']), prior.marks['document-1'])
        assert.deepEqual(clone(next.marks['hidden-document']), prior.marks['hidden-document'])
        assert.deepEqual(clone(prototypeMemberModel({ ...current, privateState: { ...current.privateState, document: { layouts: [next] } } }).notes), clone(model.notes))
    assert.deepEqual(current, before)
})

function sparseFixture() {
    const current = state(), expanded = clone(graph)
    expanded.companies.push({ id: 'company-other', ticker: 'OTHER', market: 'US', name: '합성 회사' })
    expanded.documents = Array.from({ length: 110 }, (_, i) => ({ ...clone(graph.documents[0]), id: 'document-' + (i + 1) }))
    current.graph = expanded
    current.privateState.document.layouts[0] = {
        map_key: 'main_v2',
        positions: Array.from({ length: 100 }, (_, i) => ({ node_id: 'offscreen-' + i, x: i, y: -(i + 1) })),
        notes: clone(prior.notes),
        marks: Object.fromEntries(Array.from({ length: 100 }, (_, i) => ['offscreen-' + i,
            { read_revision: i === 0 ? null : 9, important: i % 2 === 0, disposition: 'inbox' }])),
    }
    return current
}

function sparseCanvasDraft(current) {
    // Full-input Host defense remains independent of the actual sparse serializer.
    const model = prototypeMemberModel(current)
    return clone({ positions: model.nodes.map(({ id, x, y }) => ({ id, x, y })),
        notes: Object.values(model.notes), marks: model.marks })
}

test('sparse no-op round-trip preserves 100 hidden records while 112 current default positions and 110 marks are omitted', () => {
    const current = sparseFixture(), before = clone(current), value = sparseCanvasDraft(current), rejected = []
    assert.equal(value.positions.length, 112);assert.equal(Object.keys(value.marks).length, 110)
    assert.equal(validMapDocument(current.privateState.document), true)
    const next = mergePrototypeDraft(current, value, reason => rejected.push(reason))
    assert.ok(next);assert.deepEqual(rejected, [])
    assert.deepEqual(clone(next), before.privateState.document.layouts[0])
    const restored = { ...current, privateState: { ...current.privateState, document: { layouts: [clone(next)] } } }
    assert.equal(validMapDocument(restored.privateState.document), true)
    assert.deepEqual(clone(mergePrototypeDraft(restored, sparseCanvasDraft(restored))), clone(next))
    assert.deepEqual(current, before)
})

test('sparse explicit save bridge preserves hidden records and notes without persisting untouched defaults', async () => {
    const current = sparseFixture(), before = clone(current.privateState.document), h = focusHarness()
    h.emit(current)
    const port = h.connect(), model = h.messages.findLast(m => m.type === 'init').model, frame = originRuntime(model, false)
    let saves = 0
    h.workspace.editLayout = (_key, change) => {
        const next = change(h.workspace.getState().privateState.document.layouts[0])
        assert.deepEqual(clone(next), before.layouts[0])
        assert.equal(validMapDocument({ layouts: [clone(next)] }), true)
        return true
    }
    h.workspace.save = async () => { saves++;assert.deepEqual(h.workspace.getState().privateState.document, before);return true }
    try {
        await port.onmessage({ data: frame.outgoing.shift() })
        frame.context.memberSaveButton.onclick()
        for (const data of frame.outgoing.splice(0)) await port.onmessage({ data })
        assert.equal(saves, 1)
        assert.doesNotMatch(h.messages.at(-1).message, /final_schema/)
    } finally { h.bridge() }
})

test('sparse manual new position persists even one representable step from its default and preserves grouped movement', () => {
    const current = sparseFixture(), value = sparseCanvasDraft(current)
    for (const id of ['company-tick', 'document-1']) value.positions.find(p => p.id === id).x += .125
    value.positions.find(p => p.id === 'document-2').y += Number.EPSILON
    const next = mergePrototypeDraft(current, value)
    assert.ok(next);assert.equal(next.positions.length, 103)
    assert.deepEqual(clone(next.positions.slice(0, 100)), current.privateState.document.layouts[0].positions)
    for (const id of ['company-tick', 'document-1', 'document-2']) {
        const p = value.positions.find(p => p.id === id)
        assert.deepEqual(clone(next.positions.find(p => p.node_id === id)), { node_id: id, x: (p.x - .5) * 1000, y: (p.y - .5) * 680 })
    }
})

for (const [mark, expected] of [
    [{ read: true }, { read_revision: 50, important: false, disposition: 'inbox' }],
    [{ important: true }, { read_revision: null, important: true, disposition: 'inbox' }],
    [{ later: true }, { read_revision: null, important: false, disposition: 'later' }],
    [{ irrelevant: true }, { read_revision: null, important: false, disposition: 'irrelevant' }],
    [{ read: false, readTouched: true }, { read_revision: null, important: false, disposition: 'inbox' }],
]) test(`sparse new explicit mark ${Object.keys(mark).join('/')} is retained`, () => {
    const current = sparseFixture(), value = sparseCanvasDraft(current)
    value.marks['document-1'] = mark
    const next = mergePrototypeDraft(current, value)
    assert.ok(next);assert.equal(Object.keys(next.marks).length, 101)
    assert.deepEqual(clone(next.marks['document-1']), expected)
    for (const [id, saved] of Object.entries(current.privateState.document.layouts[0].marks)) assert.deepEqual(clone(next.marks[id]), saved)
})

test('sparse existing position reset to base and explicit false marks remain stored, including unread clear', () => {
    const current = sparseFixture(), base = prototypeMemberModel(current).layoutBases['company-tick']
    current.privateState.document.layouts[0].positions.push({ node_id: 'company-tick', x: 123, y: 456 })
    current.privateState.document.layouts[0].marks['document-1'] = { read_revision: 40, important: true, disposition: 'later' }
    const value = sparseCanvasDraft(current)
    Object.assign(value.positions.find(p => p.id === 'company-tick'), base)
    value.marks['document-1'] = { read: false, important: false, later: false, irrelevant: false }
    const reset = mergePrototypeDraft(current, value)
    assert.ok(reset);assert.equal(reset.positions.length, 101)
    assert.deepEqual(clone(reset.positions.find(p => p.node_id === 'company-tick')), { node_id: 'company-tick', x: (base.x - .5) * 1000, y: (base.y - .5) * 680 })
    assert.deepEqual(clone(reset.marks['document-1']), { read_revision: 40, important: false, disposition: 'inbox' })
    value.marks['document-1'].readTouched = true
    const cleared = mergePrototypeDraft(current, value)
    assert.deepEqual(clone(cleared.marks['document-1']), { read_revision: null, important: false, disposition: 'inbox' })
    const restored = { ...current, privateState: { ...current.privateState, document: { layouts: [clone(cleared)] } } }
    assert.deepEqual(clone(mergePrototypeDraft(restored, sparseCanvasDraft(restored))), clone(cleared))
})

test('sparse refreshed graph bases omit only new defaults and preserve existing manual pixels and marks', () => {
    const current = sparseFixture(), value = sparseCanvasDraft(current)
    value.positions.find(p => p.id === 'document-1').x += .125
    value.marks['document-1'].important = true
    const saved = mergePrototypeDraft(current, value)
    assert.ok(saved)
    current.privateState.document = { layouts: [clone(saved)] }
    const previousBase = prototypeMemberModel(current).layoutBases['document-2']
    current.graph.documents.unshift({ ...clone(graph.documents[0]), id: 'document-added' })
    const refreshed = prototypeMemberModel(current)
    assert.deepEqual(clone(previousBase), { x: .5, y: .5 })
    assert.deepEqual(clone(refreshed.layoutBases['document-2']), clone(previousBase))
    const next = mergePrototypeDraft(current, sparseCanvasDraft(current))
    assert.ok(next);assert.deepEqual(clone(next), clone(saved))
    assert.equal(Object.hasOwn(next.marks, 'document-added'), false)
    assert.equal(next.positions.some(p => p.node_id === 'document-added'), false)
})

for (const mutation of ['allowed-invalid-position-id', 'allowed-invalid-mark-id', 'unknown-position', 'unknown-mark', 'duplicate', 'nan', 'infinity', 'oversized-coordinate', 'malformed-mark']) {
    test(`sparse default omission cannot bypass validation: ${mutation}`, () => {
        const current = sparseFixture()
        if (mutation === 'allowed-invalid-position-id') current.graph.companies[1].id = 'company/invalid'
        if (mutation === 'allowed-invalid-mark-id') current.graph.documents[1].id = 'document/invalid'
        const value = sparseCanvasDraft(current)
        if (mutation === 'allowed-invalid-mark-id') value.positions = [] // Isolate default mark validation.
        if (mutation === 'unknown-position') value.positions[0].id = 'unknown'
        if (mutation === 'unknown-mark') value.marks.unknown = { read: false, important: false }
        if (mutation === 'duplicate') value.positions.push(clone(value.positions[0]))
        if (mutation === 'nan') value.positions[0].x = NaN
        if (mutation === 'infinity') value.positions[0].y = Infinity
        if (mutation === 'oversized-coordinate') value.positions[0].x = 1001
        if (mutation === 'malformed-mark') value.marks['document-1'].read = 'false'
        const before = clone(current), rejected = []
        assert.equal(mergePrototypeDraft(current, value, reason => rejected.push(reason)), null)
        assert.equal(rejected.length, 1)
        assert.deepEqual(current, before)
    })
}

for (const field of ['positions', 'marks']) test(`sparse still rejects retained genuine ${field} customizations above 200`, () => {
    const current = sparseFixture(), layout = current.privateState.document.layouts[0]
    if (field === 'positions') layout.positions = Array.from({ length: 200 }, (_, i) => ({ node_id: 'manual-' + i, x: i + 1, y: i + 2 }))
    else layout.marks = Object.fromEntries(Array.from({ length: 200 }, (_, i) => ['manual-' + i, { read_revision: 9, important: true, disposition: 'later' }]))
    const value = sparseCanvasDraft(current), before = clone(current), rejected = []
    if (field === 'positions') value.positions[0].x += .125
    else value.marks['document-1'].important = true
    assert.equal(validMapDocument(current.privateState.document), true)
    assert.equal(mergePrototypeDraft(current, value, reason => rejected.push(clone(reason))), null)
    assert.deepEqual(rejected, [{ code: 'final_schema', positions: field === 'positions' ? 201 : 100,
        notes: 1, marks: field === 'marks' ? 201 : 100 }])
    assert.deepEqual(current, before)
})


// Real serializer + real graph update + real grouping rebase. Only DOM painting
// and browser services are stubs; no browser storage or member records are read.
function sparseRuntime(model, localView = false) {
    const frame = originRuntime(model, localView), c = frame.context
    const element = () => ({ dataset: {}, children: [], textContent: '', remove() {}, append() {},
        querySelector() { return element() }, querySelectorAll() { return [] }, insertBefore() {} })
    Object.assign(c, {
        cancelGesture: null, closePreview() {}, selectedItems: new Set(), edges: clone(model.edges || []),
        edgeEls: new Map(), root: element(), nodesEl: { children: model.nodes.map(n => ({ ...element(), dataset: { node: n.id } })) },
        nodeById: Object.fromEntries(c.nodes.map(n => [n.id, n])), initialPositions: new Map(c.nodes.map(n => [n.id, { x: n.x, y: n.y }])),
        memberLayoutBases: new Map(Object.entries(clone(model.layoutBases))), memberDisplayOffsets: new Map(),
        memberGroups: {}, moveHistory: { past: [], future: [] }, holdings: [], clusterIds: [], changeStatus: {},
        inbox: element(), document: { createElement: element }, pendingExplore: null,
        decorateMemberStock() {}, decorateMemberRecord() {}, renderMap() {}, renderDetail() {}, renderMemberSearch() {},
        invalidateMemberSelectionReturn() {},
    })
    vm.runInNewContext(runtimeSource.slice(runtimeSource.indexOf('function updateMemberGraph(model,ticker){'), runtimeSource.indexOf('relationSource=edge=>')), c)
    vm.runInNewContext(groupingRuntimeSource.slice(groupingRuntimeSource.indexOf('const groupingUpdate=updateMemberGraph;')), c)
    return frame
}

function untouchedRuntimeModel(count = 1) {
    const current = state(), model = prototypeMemberModel(current)
    model.nodes = Array.from({ length: count }, (_, i) => ({ ...clone(model.nodes[0]), id: 'node-' + i, x: .9, y: .2 }))
    model.layoutBases = Object.fromEntries(model.nodes.map(n => [n.id, { x: n.x, y: n.y }]))
    model.edges = [];model.marks = Object.fromEntries(model.nodes.map(n => [n.id, { read: false, important: false, later: false, irrelevant: false }]))
    return model
}

test('sparse runtime 201 untouched nodes emit zero positions and marks while all old notes survive', () => {
    const model = untouchedRuntimeModel(201), frame = sparseRuntime(model)
    const value = clone(frame.context.memberDraft())
    assert.deepEqual(value.positions, []);assert.deepEqual(value.marks, {})
    assert.deepEqual(value.notes, clone(Object.values(model.notes)))
    frame.context.memberSaveButton.onclick()
    assert.deepEqual(frame.outgoing.at(-2).draft, value)
    assert.equal(frame.outgoing.at(-1).type, 'save')
})

test('sparse runtime first manual save then reset still serializes clearing position', () => {
    const frame = sparseRuntime(untouchedRuntimeModel()), c = frame.context
    c.nodes[0].x += .125;c.memberSaveButton.onclick()
    assert.equal(frame.outgoing.at(-2).draft.positions.length, 1)
    c.nodes[0].x = .9;c.memberSaveButton.onclick()
    assert.deepEqual(frame.outgoing.at(-2).draft.positions, [{ id: 'node-0', x: .9, y: .2 }])
})

test('sparse runtime initial saved override is remembered before its reset to base', () => {
    const model = untouchedRuntimeModel();model.nodes[0].x = .7
    const frame = sparseRuntime(model)
    frame.context.nodes[0].x = .9
    assert.deepEqual(clone(frame.context.memberDraft().positions), [{ id: 'node-0', x: .9, y: .2 }])
})

test('sparse runtime active and readTouched marks keep explicit inactive clears', () => {
    const frame = sparseRuntime(untouchedRuntimeModel()), c = frame.context
    for (const key of ['read', 'important', 'later', 'irrelevant', 'readTouched']) {
        c.state.marks['node-0'] = { [key]: true };c.memberSaveButton.onclick()
        assert.equal(frame.outgoing.at(-2).draft.marks['node-0'][key], true)
        c.state.marks['node-0'] = { [key]: false };c.memberSaveButton.onclick()
        assert.deepEqual(frame.outgoing.at(-2).draft.marks, { 'node-0': { [key]: false } })
    }
    const model = untouchedRuntimeModel();model.marks['node-0'].important = true
    const restored = sparseRuntime(model);restored.context.state.marks['node-0'].important = false
    assert.equal(restored.context.memberDraft().marks['node-0'].important, false)
})

test('sparse runtime graph origin shift creates no false manual positions and preserves manual axes and history', () => {
    const model = untouchedRuntimeModel(2), frame = sparseRuntime(model), c = frame.context
    c.nodes[1].y += .125
    c.moveHistory.past.push({ before: { 'node-1': { x: .9, y: .2 } }, after: { 'node-1': { x: .9, y: .325 } } })
    const next = clone(model)
    for (const n of next.nodes) { n.x = .3;n.y = .3;next.layoutBases[n.id] = { x: .3, y: .3 } }
    c.updateMemberGraph(next)
    assert.equal(c.nodes[0].x, .3);assert.equal(c.nodes[0].y, .3)
    assert.equal(c.nodes[1].x, .3);assert.equal(c.nodes[1].y, .325 + (.3 - .2))
    const value = clone(c.memberDraft())
    assert.deepEqual(value.positions.map(p => p.id), ['node-1'])
    assert.deepEqual(clone(c.initialPositions.get('node-0')), { x: .3, y: .3 })
    assert.deepEqual(clone(c.moveHistory.past[0].before['node-1']), { x: .3, y: .3 })
    assert.deepEqual(clone(c.moveHistory.past[0].after['node-1']), { x: .3, y: .325 + (.3 - .2) })
    // Undo must return to exact refreshed defaults, not introduce floating noise.
    Object.assign(c.nodes[1], c.moveHistory.past[0].before['node-1'])
    assert.deepEqual(clone(c.memberDraft().positions), [{ id: 'node-1', x: .3, y: .3 }])
})

test('sparse runtime preserves local-only hidden stocks and never emits them for member mode', () => {
    const model = untouchedRuntimeModel(), local = sparseRuntime(model, true), memberFrame = sparseRuntime(model, false)
    local.context.boardDraft.basic.hidden = ['node-0', 'missing']
    memberFrame.context.boardDraft.basic.hidden = ['node-0']
    assert.deepEqual(clone(local.context.memberDraft().hiddenStockIds), ['node-0'])
    assert.equal(Object.hasOwn(memberFrame.context.memberDraft(), 'hiddenStockIds'), false)
})

for (const bad of ['nan', 'infinity', 'string-coordinate', 'bad-mark', 'null-mark', 'array-mark']) test(`sparse runtime invalid payload is not dropped: ${bad}`, () => {
    const current = state(), model = prototypeMemberModel(current), frame = sparseRuntime(model), c = frame.context
    if (bad === 'nan') c.nodes[0].x = NaN
    if (bad === 'infinity') c.nodes[0].y = Infinity
    if (bad === 'string-coordinate') c.nodes[0].x = String(model.layoutBases[c.nodes[0].id].x)
    if (bad === 'bad-mark') c.state.marks['document-1'] = { read: 'false' }
    if (bad === 'null-mark') c.state.marks['document-1'] = null
    if (bad === 'array-mark') c.state.marks['document-1'] = []
    const value = c.memberDraft(), rejected = []
    if (bad.includes('mark')) assert.ok(Object.hasOwn(value.marks, 'document-1'))
    else assert.equal(value.positions.some(p => p.id === c.nodes[0].id), true)
    assert.equal(mergePrototypeDraft(current, value, reason => rejected.push(reason)), null)
    assert.equal(rejected.length, 1)
})

test('sparse runtime genuine 201 manual positions are retained and rejected without increasing limits', () => {
    const frame = sparseRuntime(untouchedRuntimeModel(201))
    frame.context.nodes.forEach(n => { n.x += .125 })
    const value = frame.context.memberDraft(), rejected = []
    assert.equal(value.positions.length, 201)
    assert.equal(mergePrototypeDraft(state(), value, reason => rejected.push(reason)), null)
    assert.equal(rejected[0].code, 'positions_limit')
})

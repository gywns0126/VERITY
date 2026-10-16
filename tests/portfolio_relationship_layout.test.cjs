const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const runtimePath = path.resolve(__dirname, '../review/member-map/prototype-relationship-layout.js')
const canvasPath = process.env.MEMBER_MAP_CANVAS || path.resolve(__dirname, '../vercel-api/public/member-map-canvas.html')
const clone = value => JSON.parse(JSON.stringify(value))

function functionSource(source, name) {
    const start = source.indexOf(`function ${name}(`)
    assert.ok(start >= 0, `missing pure helper ${name}`)
    const body = source.indexOf('{', start)
    let depth = 0
    for (let index = body; index < source.length; index++) {
        if (source[index] === '{') depth++
        else if (source[index] === '}' && --depth === 0) return source.slice(start, index + 1)
    }
    assert.fail(`unterminated pure helper ${name}`)
}

function assignmentSource(source, name) {
    const start = source.indexOf(`${name}=function(`)
    assert.ok(start >= 0, `missing assignment ${name}`)
    const body = source.indexOf('{', start)
    let depth = 0
    for (let index = body; index < source.length; index++) {
        if (source[index] === '{') depth++
        else if (source[index] === '}' && --depth === 0) return source.slice(start, index + 1) + ';'
    }
    assert.fail(`unterminated assignment ${name}`)
}

function helpers(names = ['memberRelationshipSlotsFor', 'memberRelationshipIsMapRecord'], context = {}) {
    const source = fs.readFileSync(runtimePath, 'utf8')
    const box = { Map, Set, Math, ...context }
    vm.runInNewContext(names.map(name => functionSource(source, name)).join('\n') +
        `\nthis.api={${names.join(',')}}`, box)
    return box.api
}

function rect(value) {
    return { left: value.x - value.width / 2, right: value.x + value.width / 2,
        top: value.y - value.height / 2, bottom: value.y + value.height / 2 }
}

function separated(a, b, gap = 24) {
    return a.right + gap <= b.left || b.right + gap <= a.left || a.bottom + gap <= b.top || b.bottom + gap <= a.top
}

function makeStocks(count) {
    return Array.from({ length: count }, (_, index) => ({
        id: `stock-${index}`, x: index * 320, y: 100 + index % 3 * 190, width: 160, height: 52,
    }))
}

function makeRecords(count, stocks) {
    return Array.from({ length: count }, (_, index) => ({
        id: `record-${index}`, width: 180, height: 96, stockIds: [stocks[index % stocks.length].id],
    }))
}

test('only reviewed event and relationship kinds enter the relationship map', () => {
    const { memberRelationshipIsMapRecord } = helpers()
    const cases = [
        [{ recordKind: 'event', layer: 'events' }, true],
        [{ recordKind: 'event', layer: 'filing' }, true],
        [{ recordKind: 'event', layer: 'candidates' }, false],
        [{ recordKind: 'relationship', layer: 'relationships' }, true],
        [{ recordKind: 'relationship', layer: 'candidates' }, false],
        [{ recordKind: 'document', layer: 'relationships' }, false],
        [{ recordKind: 'document', layer: 'filing' }, false],
        [{ recordKind: 'document', layer: 'candidates' }, false],
    ]
    for (const [record, expected] of cases) assert.equal(memberRelationshipIsMapRecord(record), expected, JSON.stringify(record))
})

test('shared event centers between both stock anchors and starts below the lower stock', () => {
    const { memberRelationshipSlotsFor } = helpers()
    const stocks = [
        { id: 'left', x: 100, y: 100, width: 160, height: 52 },
        { id: 'right', x: 700, y: 200, width: 160, height: 80 },
    ]
    const records = [
        { id: 'shared', width: 180, height: 100, stockIds: ['left', 'right'] },
        { id: 'left-only', width: 180, height: 100, stockIds: ['left'] },
    ]
    const slots = memberRelationshipSlotsFor(records, stocks)
    assert.ok(slots instanceof Map)
    assert.equal(slots.size, records.length)
    const shared = slots.get('shared')
    assert.equal(shared.x, 400)
    assert.equal(shared.y, 200 + 80 / 2 + 70 + 100 / 2)
    assert.equal(shared.width, 180)
    assert.equal(shared.height, 100)
    assert.equal(slots.get('left-only').x, 100)
    assert.ok(slots.get('left-only').y >= 100 + 52 / 2 + 70 + 100 / 2)
})

for (const stockCount of [2, 15, 30]) {
    test(`120 expanded records avoid one another, stocks, notes and manual obstacles with ${stockCount} stocks`, () => {
        const { memberRelationshipSlotsFor } = helpers()
        const stocks = makeStocks(stockCount)
        const records = makeRecords(120, stocks)
        const obstacles = [
            { left: -110, right: 110, top: 250, bottom: 430 }, // Free note.
            { left: 230, right: 450, top: 250, bottom: 430 }, // Manually displaced card.
        ]
        const before = clone({ stocks, records, obstacles })
        const slots = memberRelationshipSlotsFor(records, stocks, obstacles)
        assert.ok(slots instanceof Map)
        assert.equal(slots.size, records.length)
        const placed = [...slots.entries()].map(([id, slot]) => {
            assert.ok(records.some(record => record.id === id), `known record ${id}`)
            assert.ok(slot && Object.values(slot).every(Number.isFinite), `finite world-pixel slot ${id}`)
            return { id, bounds: rect(slot) }
        })
        for (const [index, item] of placed.entries()) {
            for (const other of placed.slice(0, index)) assert.ok(separated(item.bounds, other.bounds), `${item.id} / ${other.id}`)
            for (const obstacle of obstacles) assert.ok(separated(item.bounds, obstacle), `${item.id} / obstacle`)
            for (const stock of stocks) assert.ok(separated(item.bounds, rect(stock)), `${item.id} / ${stock.id}`)
        }
        assert.deepEqual({ stocks, records, obstacles }, before)
    })
}

test('safe prior slots survive extra records, input reordering and folding without input mutation', () => {
    const { memberRelationshipSlotsFor } = helpers()
    const stocks = makeStocks(2)
    const records = makeRecords(12, stocks)
    const initial = memberRelationshipSlotsFor(records, stocks)
    const prior = new Map([...initial].map(([id, slot]) => [id, clone(slot)]))
    const before = clone({ records, stocks, prior: [...prior] })
    const added = makeRecords(6, stocks).map((record, index) => ({ ...record, id: `new-${index}` }))
    const expanded = memberRelationshipSlotsFor([...records].reverse().concat(added), stocks, [], prior)
    for (const [id, slot] of initial) assert.deepEqual(clone(expanded.get(id)), clone(slot), `stable ${id} after append/reorder`)
    assert.equal(expanded.size, records.length + added.length)
    const folded = memberRelationshipSlotsFor(records.slice(0, 4).reverse(), stocks, [], expanded)
    for (const record of records.slice(0, 4)) assert.deepEqual(clone(folded.get(record.id)), clone(initial.get(record.id)), `stable ${record.id} after fold`)
    assert.equal(folded.size, 4)
    assert.deepEqual({ records, stocks, prior: [...prior] }, before)
})

test('a prior slot blocked by a new note is relocated while unaffected slots remain stable', () => {
    const { memberRelationshipSlotsFor } = helpers()
    const stocks = makeStocks(2)
    const records = makeRecords(4, stocks)
    const initial = memberRelationshipSlotsFor(records, stocks)
    const blocked = rect(initial.get(records[0].id))
    const next = memberRelationshipSlotsFor(records, stocks, [blocked], initial)
    assert.notDeepEqual(clone(next.get(records[0].id)), clone(initial.get(records[0].id)))
    assert.ok(separated(rect(next.get(records[0].id)), blocked))
    for (const record of records.slice(1)) {
        assert.ok(separated(rect(initial.get(record.id)), blocked), `prior ${record.id} is safe from the new note`)
        assert.deepEqual(clone(next.get(record.id)), clone(initial.get(record.id)), `safe prior ${record.id} stays fixed`)
    }
})

test('relationship bases are deterministic for the same graph regardless of input order', () => {
    const { memberRelationshipBasesFor } = helpers(['memberRelationshipSlotsFor', 'memberRelationshipBasesFor'])
    const stocks = [
        { id: 'stock-a', x: 120, y: 100, width: 160, height: 52 },
        { id: 'stock-b', x: 720, y: 160, width: 160, height: 52 },
    ]
    const records = [
        { id: 'event-shared', isRelationship: true, stockIds: ['stock-a', 'stock-b'], width: 180, height: 96 },
        { id: 'event-a', isRelationship: true, stockIds: ['stock-a'], width: 180, height: 96 },
        { id: 'source-b', isRelationship: false, stockIds: ['stock-b'], width: 220, height: 110 },
        { id: 'source-a', isRelationship: false, stockIds: ['stock-a'], width: 200, height: 100 },
    ]
    const before = clone({ stocks, records })
    const first = memberRelationshipBasesFor(records, stocks)
    const reordered = memberRelationshipBasesFor([...records].reverse(), [...stocks].reverse())
    const rows = slots => [...slots].sort(([a], [b]) => a.localeCompare(b)).map(([id, slot]) => [id, clone(slot)])
    assert.equal(first.size, records.length)
    assert.deepEqual(rows(reordered), rows(first))
    assert.deepEqual(rows(memberRelationshipBasesFor(records, stocks)), rows(first))
    assert.equal(first.get('event-shared').x, 420)
    assert.ok(first.get('source-a').y > first.get('event-shared').y)
    assert.deepEqual({ stocks, records }, before)
})

test('rebase preserves raw coordinates until movement and retains the effective manual delta', () => {
    const node = { id: 'event-a', kind: 'event', x: .31, y: .42 }
    const stock = { id: 'stock-a', kind: 'stock', x: .2, y: .2 }
    const base = { x: node.x, y: node.y }
    const slot = { x: 640, y: 408, width: 180, height: 96 }
    const automatic = { x: slot.x / 1000 - base.x, y: slot.y / 680 - base.y }
    const focusOffsets = new Map([[node.id, { ...automatic }], [stock.id, { x: .7, y: .8 }]])
    const memberDisplayOffsets = new Map()
    const context = {
        nodeById: { [node.id]: node, [stock.id]: stock },
        memberRelationshipBases: new Map([[node.id, slot], [stock.id, { x: 999, y: 999 }]]),
        memberLayoutBases: new Map([[node.id, base], [stock.id, { x: stock.x, y: stock.y }]]),
        initialPositions: new Map(), focusOffsets, memberDisplayOffsets,
        WORLD_WIDTH: 1000, WORLD_HEIGHT: 680,
    }
    const { memberRelationshipRebaseMovement } = helpers(['memberRelationshipRebaseMovement'], context)
    const rawBefore = clone(node)
    memberRelationshipRebaseMovement(node.id)
    assert.deepEqual(node, rawBefore, 'entering a move does not save an automatic offset as manual movement')
    assert.deepEqual(clone(focusOffsets.get(node.id)), automatic)
    focusOffsets.set(node.id, { x: automatic.x + .04, y: automatic.y - .02 })
    const viewBefore = { x: node.x + focusOffsets.get(node.id).x, y: node.y + focusOffsets.get(node.id).y }
    memberRelationshipRebaseMovement(node.id)
    assert.ok(Math.abs(node.x - (rawBefore.x + .04)) < 1e-12)
    assert.ok(Math.abs(node.y - (rawBefore.y - .02)) < 1e-12)
    assert.ok(Math.abs(node.x + focusOffsets.get(node.id).x - viewBefore.x) < 1e-12)
    assert.ok(Math.abs(node.y + focusOffsets.get(node.id).y - viewBefore.y) < 1e-12)
    assert.deepEqual(clone(memberDisplayOffsets.get(node.id)), automatic)
    const after = clone(node)
    memberRelationshipRebaseMovement(node.id)
    memberRelationshipRebaseMovement(stock.id)
    memberRelationshipRebaseMovement('missing')
    assert.deepEqual(node, after, 'repeated rebase does not apply the delta twice')
    assert.deepEqual(stock, { id: 'stock-a', kind: 'stock', x: .2, y: .2 }, 'stocks are never rebased by this helper')
})

test('a note-pinned source stays visible without becoming raw manual movement', () => {
    const source = { id: 'source', kind: 'event', recordKind: 'document', layer: 'filing', x: .31, y: .42 }
    const filteredEvent = { id: 'filtered-event', kind: 'event', recordKind: 'event', layer: 'events', x: .63, y: .48 }
    const stockA = { id: 'stock-a', kind: 'stock', x: .2, y: .2 }
    const stockB = { id: 'stock-b', kind: 'stock', x: .8, y: .2 }
    const allNodes = [source, filteredEvent, stockA, stockB]
    const originals = clone(allNodes)
    const scope = { records: [source], stocks: [stockA], stockIds: new Set([stockA.id]) }
    const note = { id: 'note', target: source.id }
    const captured = { records: null, stocks: null }
    const context = {
        nodes: allNodes, holdings: [stockA, stockB], nodeById: Object.fromEntries(allNodes.map(n => [n.id, n])),
        state: { notes: { [note.id]: note }, selected: null, marks: {}, focusId: '', filter: '', topic: '', view: '', zoom: 1, panX: 0, panY: 0 },
        edges: [], memberLayoutBases: new Map(allNodes.map(n => [n.id, { x: n.x, y: n.y }])), initialPositions: new Map(),
        memberDisplayDecisions: new Map(), memberGroups: new Map(), memberVisible: new Set(), memberDisplayOffsets: new Map(), focusOffsets: new Map(),
        memberRelationshipSlots: new Map(), memberRelationshipContext: '', memberBaseLayoutKey: 'main_v2',
        memberRelationshipBases: new Map(), MEMBER_DEFAULT_BUDGET: 12,
        WORLD_WIDTH: 1000, WORLD_HEIGHT: 680,
        viewPosition: n => ({ x: n.x, y: n.y }), memberCardSize: () => ({ width: 180, height: 96 }),
        eventHoldings: () => [stockA.id], noteVisible: () => true, noteAnchor: () => ({ x: 0, y: 0 }),
        noteEls: new Map(), space: { clientWidth: 1000, clientHeight: 680 },
        memberRelationshipBasesFor: (records, stocks) => {
            captured.records = clone(records)
            captured.stocks = clone(stocks)
            return new Map(records.map(r => [r.id, { x: 500, y: 500, width: r.width, height: r.height }]))
        },
        memberRelationshipSlotsFor: records => new Map(records.map(r => [r.id, { x: 500, y: 500, width: r.width, height: r.height }])),
    }
    const names = ['memberRelationshipIsMapRecord', 'memberRelationshipMovedIds', 'memberRelationshipPinnedIds', 'applyMemberRelationshipLayout']
    const { memberRelationshipMovedIds, memberRelationshipPinnedIds, applyMemberRelationshipLayout } = helpers(names, context)
    assert.equal(memberRelationshipMovedIds(scope).has(source.id), false)
    assert.equal(memberRelationshipPinnedIds(scope).has(source.id), true)
    applyMemberRelationshipLayout(scope)
    assert.deepEqual(allNodes, originals, 'a note anchor cannot convert automatic placement into saved raw movement')
    assert.deepEqual(captured.records.map(r => r.id).sort(), [filteredEvent.id, source.id].sort(), 'basis includes filtered-out events')
    assert.deepEqual(captured.stocks.map(s => s.id).sort(), [stockA.id, stockB.id].sort(), 'basis includes all holdings')
    assert.ok(context.memberDisplayOffsets.has(source.id), 'note-pinned source still receives a display-only slot')
})

test('keyboard movement snapshots original coordinates before rebase for Undo', () => {
    const source = fs.readFileSync(runtimePath, 'utf8')
    const node = { id: 'event-a', kind: 'event', x: .31, y: .42 }
    const original = clone(node)
    let undoBefore = null
    const context = {
        nodeById: { [node.id]: node }, memberRelationshipBases: new Map([[node.id, { x: 640, y: 408 }]]),
        memberLayoutBases: new Map([[node.id, { x: node.x, y: node.y }]]), initialPositions: new Map(),
        focusOffsets: new Map([[node.id, { x: .37, y: .18 }]]), memberDisplayOffsets: new Map(),
        WORLD_WIDTH: 1000, WORLD_HEIGHT: 680, state: { zoom: 1 }, cancelGesture: false, memberWritable: true,
        layoutSnapshot: () => clone(node), movableItems: () => [{ id: node.id, item: node }], selectedItems: new Set(),
        recordMove: before => { undoBefore = before }, renderMap: () => {},
    }
    vm.runInNewContext(functionSource(source, 'memberRelationshipRebaseMovement') + '\n' + assignmentSource(source, 'moveWithKeys'), context)
    let prevented = 0
    context.moveWithKeys({ key: 'ArrowRight', shiftKey: false, repeat: false, preventDefault: () => prevented++, stopPropagation: () => {} }, node.id)
    assert.equal(prevented, 1)
    assert.deepEqual(undoBefore, original, 'Undo must capture the original raw position, not the rebased one')
    assert.notDeepEqual(node, original, 'explicit movement changes raw coordinates')
})

function pointerMoveFixture() {
    const canvas = fs.readFileSync(canvasPath, 'utf8')
    const nodes = [
        { id: 'event-a', kind: 'event', x: .31, y: .42 },
        { id: 'event-b', kind: 'event', x: .51, y: .52 },
    ]
    const original = clone(nodes)
    const slots = new Map([
        [nodes[0].id, { x: 640, y: 408 }],
        [nodes[1].id, { x: 760, y: 476 }],
    ])
    const bases = new Map(nodes.map(n => [n.id, { x: n.x, y: n.y }]))
    const offsets = new Map(nodes.map(n => {
        const slot = slots.get(n.id)
        return [n.id, { x: slot.x / 1000 - n.x + .04, y: slot.y / 680 - n.y - .02 }]
    }))
    const listeners = new Map()
    const element = {
        captured: false,
        setPointerCapture() { this.captured = true },
        hasPointerCapture() { return this.captured },
        releasePointerCapture() { this.captured = false },
        addEventListener(type, handler) { listeners.set(type, handler) },
        removeEventListener(type) { listeners.delete(type) },
    }
    const rebased = []
    const moves = []
    let snapshotCount = 0
    const context = {
        nodeById: Object.fromEntries(nodes.map(n => [n.id, n])),
        memberRelationshipBases: slots, memberLayoutBases: bases, initialPositions: new Map(),
        focusOffsets: offsets, memberDisplayOffsets: new Map(), WORLD_WIDTH: 1000, WORLD_HEIGHT: 680,
        state: { zoom: 1 }, cancelGesture: null, nodePointerActive: false, nodeMoveActive: false,
        selectedItems: new Set(nodes.map(n => n.id)), renderSelection: () => {},
        layoutSnapshot: () => { snapshotCount++; return clone(nodes) },
        movableItems: () => nodes.map(n => ({ id: n.id, item: n })),
        closePreview: () => {}, recordMove: before => moves.push(before), renderMap: () => {},
        pendingMapResize: false, applyMapResize: () => {}, suppressClick: false, setTimeout: () => {},
    }
    const { memberRelationshipRebaseMovement } = helpers(['memberRelationshipRebaseMovement'], context)
    context.memberRelationshipRebaseMovement = id => { rebased.push(id); memberRelationshipRebaseMovement(id) }
    vm.runInNewContext(functionSource(canvas, 'beginMove'), context)
    const pointer = (clientX, type = 'pointermove') => listeners.get(type)({ pointerId: 7, clientX, clientY: 100 })
    const down = () => context.beginMove({ button: 0, shiftKey: false, pointerId: 7, clientX: 100, clientY: 100, stopPropagation() {} }, nodes[0].id, element)
    return { nodes, original, listeners, element, context, rebased, moves, pointer, down, snapshots: () => snapshotCount }
}

test('canvas beginMove click and cancelled drag preserve canonical coordinates', () => {
    const click = pointerMoveFixture()
    click.down()
    click.pointer(103)
    assert.deepEqual(click.nodes, click.original, 'movement within the 4px threshold is inert')
    click.pointer(103, 'pointerup')
    assert.deepEqual(click.nodes, click.original, 'click cannot turn presentation offsets into raw movement')
    assert.deepEqual(click.rebased, [])
    assert.equal(click.moves.length, 0)

    const cancelled = pointerMoveFixture()
    cancelled.down()
    cancelled.pointer(105)
    assert.notDeepEqual(cancelled.nodes, cancelled.original, 'drag beyond threshold does move while active')
    cancelled.pointer(105, 'pointercancel')
    assert.deepEqual(cancelled.nodes, cancelled.original, 'cancel restores both selected raw coordinates')
    assert.equal(cancelled.moves.length, 0)
    assert.equal(cancelled.element.captured, false)
})

test('canvas beginMove rebases selected items once after threshold and records pre-rebase Undo snapshot', () => {
    const drag = pointerMoveFixture()
    drag.down()
    assert.equal(drag.snapshots(), 1)
    assert.deepEqual(drag.rebased, [])
    drag.pointer(104)
    assert.deepEqual(drag.nodes, drag.original, 'exactly 4px does not start a drag')
    drag.pointer(105)
    assert.deepEqual(drag.rebased, drag.original.map(n => n.id), 'both selected nodes rebase on first committed move')
    drag.pointer(108)
    assert.deepEqual(drag.rebased, drag.original.map(n => n.id), 'subsequent move does not rebase again')
    for (const [index, node] of drag.nodes.entries()) {
        assert.ok(Math.abs(node.x - (drag.original[index].x + .04 + .008)) < 1e-12)
        assert.ok(Math.abs(node.y - (drag.original[index].y - .02)) < 1e-12)
    }
    drag.pointer(108, 'pointerup')
    assert.equal(drag.moves.length, 1)
    assert.deepEqual(drag.moves[0], drag.original, 'Undo starts before rebase changes raw coordinates')
    assert.equal(drag.snapshots(), 1)
    assert.equal(drag.listeners.size, 0)
})

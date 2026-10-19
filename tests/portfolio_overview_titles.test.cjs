const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const runtime = fs.readFileSync(path.resolve(__dirname, '../review/member-map/prototype-overview-runtime.js'), 'utf8')
const clone = value => JSON.parse(JSON.stringify(value))

test('the deployed canvas contains the tested overview runtime exactly', () => {
    const file = process.env.MEMBER_MAP_CANVAS || path.resolve(__dirname, '../vercel-api/public/member-map-canvas.html')
    assert.ok(fs.readFileSync(file, 'utf8').includes(runtime.trimEnd()))
})

function element(width = 104, height = 36) {
    return {
        dataset: {}, style: {}, hidden: false, children: [], attributes: {},
        offsetWidth: width, offsetHeight: height, namespaceURI: 'http://www.w3.org/2000/svg',
        append(child) { this.children.push(child) },
        replaceChildren(...children) { this.children = children },
        setAttribute(name, value) { this.attributes[name] = value },
        getBoundingClientRect() { return this.rect || { left: 0, right: 0, top: 0, bottom: 0 } },
    }
}

function harness(width = 1280, height = 720, zoom = .2) {
    const leader = element(), head = element(), groupLines = element()
    const document = {
        head,
        createElement: () => element(),
        createElementNS: () => element(),
    }
    groupLines.before = node => { leader.group = node }
    const baseCalls = { groups: 0, render: 0, edges: 0, visuals: 0, notes: 0 }
    const stockButtons = new Map(), eventButtons = []
    const nodesEl = {
        querySelector(selector) { return stockButtons.get(selector.match(/data-node="([^"]+)"/)?.[1]) },
        querySelectorAll() { return eventButtons },
    }
    const box = {
        document, memberGroupLines: groupLines, state: { zoom, panX: 0, panY: 0 },
        space: { clientWidth: width, clientHeight: height,
            getBoundingClientRect: () => ({ left: 100, top: 50, right: 100 + width, bottom: 50 + height }) },
        holdings: [], edges: [], edgeEls: new Map(), shown: () => true, nodesEl, memberGroups: new Map(), noteEls: new Map(),
        point(n) { return { x: width / 2 + (n.x - .5) * 1000 * box.state.zoom + box.state.panX,
            y: height / 2 + (n.y - .5) * 680 * box.state.zoom + box.state.panY } },
        drawMemberGroups() {
            baseCalls.groups++
            for (const n of [...box.holdings, ...(box.testRecords || [])]) {
                const button = stockButtons.get(n.id), p = box.point(n)
                Object.assign(button.style, { left: p.x + 'px', top: p.y + 'px', transform: 'translate(-50%,-50%) scale(' + box.state.zoom + ')' })
            }
            for (const group of box.memberGroups.values()) {
                const p = box.point(group)
                Object.assign(group.button.style, { left: p.x + 'px', top: p.y + 'px', transform: 'translate(-50%,-50%) scale(' + box.state.zoom + ')' })
            }
            box.renderNotes()
        },
        renderNotes() { baseCalls.notes++ },
        renderMap() { baseCalls.render++;box.drawMemberGroups() },
        syncMemberEdgeLabels() { baseCalls.edges++ },
        applyMemberEdgeVisuals() { baseCalls.visuals++ },
    }
    vm.runInNewContext(runtime, box)
    return { box, stockButtons, eventButtons, leader: leader.group, baseCalls }
}

function bounds(slot) { return slot && { left: slot.left, right: slot.right, top: slot.top, bottom: slot.bottom } }
function apart(a, b, gap = 6) {
    return a.right + gap <= b.left || b.right + gap <= a.left || a.bottom + gap <= b.top || b.bottom + gap <= a.top
}

for (const [width, height] of [[1280, 720], [390, 900]]) for (const count of [6, 15, 30]) {
    test(`screen slots fit ${count} titles at ${width}px without note overlap or changing inputs`, () => {
        const { box } = harness(width, height)
        const items = Array.from({ length: count }, (_, i) => ({ x: width / 2 + (i % 3 - 1) * 9,
            y: height / 2 + (Math.floor(i / 3) % 3 - 1) * 7, w: width < 560 ? 104 : 128, h: 36 }))
        const obstacles = [{ left: width / 2 - 58, right: width / 2 + 58, top: height / 2 - 25, bottom: height / 2 + 25 }]
        const before = clone({ items, obstacles })
        const slots = Array.from(box.memberOverviewTitleSlots(items, obstacles, width, height), bounds)
        assert.equal(slots.length, count)
        assert.ok(slots.every(Boolean), 'each visible title has a screen slot')
        for (const [i, slot] of slots.entries()) {
            assert.ok(slot.left >= 8 && slot.right <= width - 8, `horizontal fit ${i}`)
            assert.ok(slot.top >= 8 && slot.bottom <= height - 8, `vertical fit ${i}`)
            assert.ok(apart(slot, obstacles[0]), `note obstacle ${i}`)
            for (const prior of slots.slice(0, i)) assert.ok(apart(slot, prior), `title gap ${i}`)
        }
        assert.deepEqual(Array.from(box.memberOverviewTitleSlots(items, obstacles, width, height), bounds), slots)
        assert.deepEqual({ items, obstacles }, before)
    })
}

test('390px viewport fits thirty maximum-width compact titles in two or more columns', () => {
    const { box } = harness(390, 900)
    const items = Array.from({ length: 30 }, () => ({ x: 195, y: 450, w: 160, h: 36 }))
    const slots = Array.from(box.memberOverviewTitleSlots(items, [], 390, 900), bounds)
    assert.ok(slots.every(Boolean), `${slots.filter(Boolean).length}/30 maximum-width titles received slots`)
    for (const [i, slot] of slots.entries()) {
        assert.ok(slot.left >= 8 && slot.right <= 382 && slot.top >= 8 && slot.bottom <= 892)
        for (const prior of slots.slice(0, i)) assert.ok(apart(slot, prior))
    }
})

test('offscreen titles do not change a visible screen slot', () => {
    const { box } = harness(390, 900)
    const visible = { x: 195, y: 450, w: 160, h: 36 }
    const alone = box.memberOverviewTitleSlots([visible], [], 390, 900)[0]
    const offscreen = Array.from({ length: 30 }, () => ({ x: -20, y: 450, w: 160, h: 36 }))
    const withOffscreen = box.memberOverviewTitleSlots([visible, ...offscreen], [], 390, 900)
    assert.deepEqual(bounds(withOffscreen[0]), bounds(alone))
    assert.ok(withOffscreen.slice(1).every(slot => slot === null))
})

test('different zoom and pan change only screen anchors; offscreen anchors produce no title', () => {
    const { box } = harness(1280, 720)
    const canonical = Object.freeze({ x: .7, y: .35 }), before = clone(canonical)
    for (const zoom of [.12, .3, .64]) {
        box.state.zoom = zoom;box.state.panX = 17;box.state.panY = -11
        const anchor = box.point(canonical), item = { ...anchor, w: 104, h: 36 }
        const slot = box.memberOverviewTitleSlots([item], [], 1280, 720)[0]
        assert.ok(slot)
        assert.ok(Math.abs(slot.x - anchor.x) < 1e-10)
        assert.ok(Math.abs(slot.y - anchor.y) < 1e-10)
        assert.equal(slot.right - slot.left, item.w)
        assert.equal(slot.bottom - slot.top, item.h)
    }
    assert.equal(box.memberOverviewTitleSlots([{ x: -1, y: 300, w: 104, h: 36 }], [], 1280, 720)[0], null)
    assert.deepEqual(canonical, before)
})

test('group title collision search stays above its screen anchor', () => {
    const { box } = harness(390, 720)
    const items = Array.from({ length: 6 }, () => ({ x: 195, y: 350, w: 104, h: 36, group: true }))
    const before = clone(items)
    const slots = box.memberOverviewTitleSlots(items, [], 390, 720)
    assert.ok(slots.every(Boolean))
    assert.ok(slots.every(slot => slot.y <= 350))
    for (const [i, slot] of slots.entries()) for (const prior of slots.slice(0, i)) assert.ok(apart(slot, prior))
    assert.deepEqual(items, before)
})

test('summary icons are reset before measuring original fit dimensions and overview mode clears at .65', () => {
    const { box, stockButtons, leader, baseCalls } = harness(1280, 720, .2)
    const n = { id: 'stock', kind: 'stock', x: .5, y: .5 }
    const button = element(160, 60)
    Object.defineProperties(button, {
        offsetWidth: { get() { return this.dataset.summaryIcon === 'true' ? 44 : this.dataset.overviewTitle === 'true' ? 104 : 160 } },
        offsetHeight: { get() { return this.dataset.summaryIcon === 'true' ? 44 : this.dataset.overviewTitle === 'true' ? 36 : 60 } },
    })
    stockButtons.set(n.id, button);box.holdings.push(n)
    button.dataset.summaryIcon = 'true'
    assert.equal(button.offsetWidth, 44);assert.equal(button.offsetHeight, 44)
    // The base draw preserves summaryIcon, so the real wrapper must clear it before measuring.
    box.renderMap()
    assert.equal(baseCalls.groups, 1)
    assert.equal(button.dataset.summaryIcon, 'false')
    assert.equal(button.dataset.overviewWidth, '160')
    assert.equal(button.dataset.overviewHeight, '60')
    assert.equal(button.dataset.overviewTitle, 'true')
    assert.equal(button.offsetWidth, 104);assert.equal(button.offsetHeight, 36)
    box.state.zoom = .65
    box.renderMap()
    for (const key of ['overviewTitle', 'overviewWidth', 'overviewHeight']) {
        assert.equal(Object.hasOwn(button.dataset, key), false)
    }
    assert.equal(button.offsetWidth, 160);assert.equal(button.offsetHeight, 60)
    assert.equal(button.style.transform, 'translate(-50%,-50%) scale(0.65)')
    assert.equal(leader.children.length, 0)
})

test('real stock/group buttons stay interactive, above source cards, and keep canonical and fit data unchanged', () => {
    const { box, stockButtons, eventButtons, leader, baseCalls } = harness(390, 720, .2)
    const clicks = []
    for (let i = 0; i < 6; i++) {
        const n = { id: 'stock-' + i, kind: 'stock', x: .48 + i * .004, y: .5 }
        const button = element(120, 72);button.onclick = () => clicks.push(n.id);button.onkeydown = () => clicks.push('key-' + n.id)
        stockButtons.set(n.id, button);box.holdings.push(n)
    }
    const groupButton = element(130, 72)
    groupButton.onclick = () => clicks.push('group');groupButton.onkeydown = () => clicks.push('key-group')
    const group = { id: 'group:news', kind: 'group', x: .52, y: .53, records: [{}], button: groupButton }
    box.memberGroups.set('news', group)
    const note = element();note.rect = { left: 235, right: 305, top: 360, bottom: 410 }
    box.noteEls.set('note', note)
    const event = element();event.rect = { left: 290, right: 335, top: 280, bottom: 320 }
    eventButtons.push(event)
    const nodesBefore = clone(box.holdings), groupBefore = clone({ id: group.id, x: group.x, y: group.y })
    box.root = { dataset: { readableFit: 'true', readableFitZoom: '.2', fitWorldWidth: 'kept' } }
    const datasetBefore = clone(box.root.dataset)
    box.renderMap()
    const buttons = [...stockButtons.values(), groupButton]
    assert.ok(buttons.every(button => button.dataset.overviewTitle === 'true'))
    assert.ok(buttons.every(button => button.style.transform === 'translate(-50%,-50%)'))
    const first = buttons.map(button => ({ left: button.style.left, top: button.style.top }))
    assert.ok(Number.parseFloat(groupButton.style.top) < box.point(group).y, 'group title stays above its world anchor')
    assert.ok([...stockButtons.values()].every(button => button.dataset.overviewWidth === '120' && button.dataset.overviewHeight === '72'))
    assert.equal(groupButton.dataset.overviewWidth, '130')
    assert.equal(groupButton.dataset.overviewHeight, '72')
    const noteLocal = { left: 135, right: 205, top: 310, bottom: 360 }
    for (const button of buttons) {
        const x = Number.parseFloat(button.style.left), y = Number.parseFloat(button.style.top)
        const rect = { left: x - button.offsetWidth / 2, right: x + button.offsetWidth / 2,
            top: y - button.offsetHeight / 2, bottom: y + button.offsetHeight / 2 }
        assert.ok(apart(rect, noteLocal))
        button.onclick();button.onkeydown()
    }
    assert.equal(clicks.length, 14)
    assert.deepEqual(box.holdings, nodesBefore);assert.deepEqual({ id: group.id, x: group.x, y: group.y }, groupBefore)
    assert.deepEqual(box.root.dataset, datasetBefore)
    event.rect = { left: 100, right: 350, top: 200, bottom: 600 }
    box.renderMap()
    assert.deepEqual(buttons.map(button => ({ left: button.style.left, top: button.style.top })), first,
        'expanded source cards cannot move stock or group titles')
    event.hidden = true
    box.renderMap()
    assert.deepEqual(buttons.map(button => ({ left: button.style.left, top: button.style.top })), first,
        'folded source cards cannot move stock or group titles')
    box.renderMap()
    assert.deepEqual(buttons.map(button => ({ left: button.style.left, top: button.style.top })), first)
    assert.equal(baseCalls.render, 4);assert.equal(baseCalls.groups, 4)
    assert.equal(baseCalls.edges, 4);assert.equal(baseCalls.visuals, 4)
    assert.ok(leader.children.every(path => path.attributes.class === 'an-overview-leader'))
    box.state.zoom = .65
    box.renderMap()
    assert.ok(buttons.every(button => !Object.hasOwn(button.dataset, 'overviewTitle')))
    assert.ok(buttons.every(button => !Object.hasOwn(button.dataset, 'overviewWidth') && !Object.hasOwn(button.dataset, 'overviewHeight')))
    assert.ok(buttons.every(button => button.style.transform.includes('scale(0.65)')))
    assert.equal(leader.children.length, 0)
    assert.deepEqual(box.root.dataset, datasetBefore)
})

function relationshipHarness() {
    const fixture = harness(390, 720, .2)
    const { box, stockButtons } = fixture
    const records = [], excluded = new Set()
    box.testRecords = records
    box.state.notes = { attached: { id: 'attached', target: 'event-a', text: 'preserved note' },
        free: { id: 'free', x: .8, y: .9, text: 'preserved free note' } }
    box.nodeById = {};box.WORLD_WIDTH = 1000;box.WORLD_HEIGHT = 680
    box.shown = n => !excluded.has(n.id)
    box.memberRelationshipOverviewNodes = () => records.filter(box.shown)
        .map(n => ({ id: n.id, n, el: stockButtons.get(n.id) }))
    const add = (id, kind, x, y) => {
        const n = { id, kind, x, y }, button = element(104, 36)
        stockButtons.set(id, button);box.nodeById[id] = n
        ;(kind === 'stock' ? box.holdings : records).push(n)
        return n
    }
    add('stock-a', 'stock', .48, .5);add('stock-b', 'stock', .52, .5)
    add('event-a', 'event', .5, .51);add('event-b', 'event', .51, .52)
    const note = element();note.rect = { left: 100, right: 490, top: 50, bottom: 770 }
    box.noteEls.set('free', note)
    // In this mode neither a full-canvas note nor dense titles authorize slots.
    box.memberOverviewTitleSlots = () => assert.fail('relationship mode must never call the screen-space allocator')
    const render = () => {
        for (const n of records) {
            const button = stockButtons.get(n.id), p = box.point(n)
            button.hidden = !box.shown(n)
            Object.assign(button.style, { left: p.x + 'px', top: p.y + 'px', transform: 'translate(-50%,-50%) scale(' + box.state.zoom + ')' })
        }
        box.renderMap()
    }
    const centers = () => Object.fromEntries([...box.holdings, ...records].filter(box.shown).map(n => {
        const el = stockButtons.get(n.id)
        return [n.id, { x: parseFloat(el.style.left), y: parseFloat(el.style.top) }]
    }))
    const assertAnchors = () => {
        for (const [id, center] of Object.entries(centers())) assert.deepEqual(center, box.point(box.nodeById[id]), `point-only ${id}`)
        assert.equal(fixture.leader.children.length, 0, 'no collision-offset leaders in relationship mode')
    }
    return { ...fixture, records, excluded, add, render, centers, assertAnchors }
}

test('relationship titles translate by the exact pan delta, including repeated redraw and pointerup', () => {
    const f = relationshipHarness(), { box } = f
    const saved = JSON.stringify({ nodes: box.nodeById, notes: box.state.notes })
    f.render();const before = f.centers()
    box.state.panX += 137;box.state.panY -= 83
    f.render();f.assertAnchors()
    for (const [id, center] of Object.entries(f.centers())) {
        assert.ok(Math.abs(center.x - before[id].x - 137) < 1e-10)
        assert.ok(Math.abs(center.y - before[id].y + 83) < 1e-10)
    }
    const panned = f.centers()
    f.render();f.render() // Released pointer / follow-up redraw cannot retile.
    assert.deepEqual(f.centers(), panned)
    assert.equal(JSON.stringify({ nodes: box.nodeById, notes: box.state.notes }), saved)
})

test('relationship compact/full centers follow zoom affine projection without a .65 transition jump', () => {
    const f = relationshipHarness(), { box, stockButtons } = f
    box.state.panX = 19;box.state.panY = -23
    for (const zoom of [.08, .2, .64, .649999, .65, .650001, 1.2, .2]) {
        box.state.zoom = zoom;f.render();f.assertAnchors()
        for (const [id, center] of Object.entries(f.centers())) {
            const n = box.nodeById[id]
            assert.ok(Math.abs((center.x - 195 - 19) / zoom - (n.x - .5) * 1000) < 1e-9)
            assert.ok(Math.abs((center.y - 360 + 23) / zoom - (n.y - .5) * 680) < 1e-9)
            assert.equal(stockButtons.get(id).dataset.overviewTitle, 'true')
            assert.equal(stockButtons.get(id).style.transform, `translate(-50%,-50%) scale(${zoom})`)
        }
    }
})

test('relationship viewport entry/exit, new records, filter/fold and note changes never retile surviving anchors', () => {
    const f = relationshipHarness(), { box, records, stockButtons, excluded } = f
    f.render();const initial = f.centers(), raw = JSON.stringify(box.nodeById)
    box.state.panX = -1000;f.render();f.assertAnchors()
    assert.ok(Object.values(f.centers()).every(p => p.x < 0), 'offscreen titles remain world-projected, not viewport-clamped')
    box.state.panX = 0;f.render();assert.deepEqual(f.centers(), initial)
    f.add('event-0-new', 'event', .5, .51);f.render()
    for (const [id, p] of Object.entries(initial)) assert.deepEqual(f.centers()[id], p)
    excluded.add(records[0].id);box.state.filter = 'filtered';f.render();f.assertAnchors()
    for (const [id, p] of Object.entries(initial)) if (!excluded.has(id)) assert.deepEqual(f.centers()[id], p)
    excluded.clear();box.state.filter = 'all'
    const [folded] = records.splice(1, 1);f.render();f.assertAnchors()
    for (const [id, p] of Object.entries(initial)) if (id !== folded.id) assert.deepEqual(f.centers()[id], p)
    records.splice(1, 0, folded);f.render()
    box.noteEls.get('free').hidden = true;f.render();f.assertAnchors()
    for (const [id, p] of Object.entries(initial)) assert.deepEqual(f.centers()[id], p)
    for (const n of Object.values(JSON.parse(raw))) assert.deepEqual(box.nodeById[n.id], n)
    assert.ok([...stockButtons.values()].filter(el => !el.hidden).every(el => el.dataset.overviewTitle === 'true'))
})

test('relationship explicit drag adopts no extra title offset and has no release-time slot jump', () => {
    const f = relationshipHarness(), { box } = f
    f.render()
    const n = box.nodeById['event-a'], before = clone(n), start = f.centers()[n.id]
    box.memberOverviewRebaseMovement(n.id)
    assert.deepEqual(n, before, 'point-centered title adds zero canonical delta at drag threshold')
    n.x += 18 / (1000 * box.state.zoom);n.y -= 9 / (680 * box.state.zoom)
    f.render();f.assertAnchors()
    const dragged = f.centers()[n.id]
    assert.ok(Math.abs(dragged.x - start.x - 18) < 1e-10)
    assert.ok(Math.abs(dragged.y - start.y + 9) < 1e-10)
    f.render();assert.deepEqual(f.centers()[n.id], dragged, 'release redraw stays at the dragged point')
})

test('relationship compact canonical fit dimensions, notes and saved pins stay constant across all zooms', () => {
    const f = relationshipHarness(), { box, stockButtons } = f
    for (const el of stockButtons.values()) Object.defineProperties(el, {
        offsetWidth: { get() { return this.dataset.summaryIcon === 'true' ? 44 : this.dataset.overviewTitle === 'true' ? 104 : 160 } },
        offsetHeight: { get() { return this.dataset.summaryIcon === 'true' ? 44 : this.dataset.overviewTitle === 'true' ? 36 : 60 } },
    })
    box.state.marks = { 'event-a': { important: true } }
    const saved = JSON.stringify({ nodes: box.nodeById, notes: box.state.notes, marks: box.state.marks })
    for (const zoom of [.08, .2, .64, .649999, .65, .650001, 1.2, .2]) {
        box.state.zoom = zoom;f.render();f.assertAnchors()
        for (const [id, el] of stockButtons) {
            assert.equal(el.dataset.overviewTitle, 'true')
            assert.equal(el.dataset.overviewWidth, String(el.offsetWidth), `canonical fit width ${id}`)
            assert.equal(el.dataset.overviewHeight, String(el.offsetHeight), `canonical fit height ${id}`)
            assert.equal(el.dataset.overviewWidth, '104')
            assert.equal(el.dataset.overviewHeight, '36')
            assert.equal(el.style.transform, `translate(-50%,-50%) scale(${zoom})`)
            const center = f.centers()[id], n = box.nodeById[id]
            // Attached-note anchors use the same point; camera changes must
            // not add a label offset or a threshold-dependent display origin.
            assert.deepEqual(center, box.point(n))
        }
        assert.equal(JSON.stringify({ nodes: box.nodeById, notes: box.state.notes, marks: box.state.marks }), saved)
    }
})

test('relationship drag and pan remain continuous above and below the former compact threshold', () => {
    for (const zoom of [.08, .2, .64, .649999, .65, .650001, 1.2]) {
        const f = relationshipHarness(), { box } = f
        box.state.zoom = zoom;f.render()
        const n = box.nodeById['event-a'], raw = clone(n), before = f.centers()[n.id]
        box.memberOverviewRebaseMovement(n.id)
        assert.deepEqual(n, raw, 'centered presentation adds no drag-start coordinate change')
        n.x += 18 / (1000 * zoom);n.y -= 9 / (680 * zoom)
        f.render();const dragged = f.centers()[n.id]
        assert.ok(Math.abs(dragged.x - before.x - 18) < 1e-10)
        assert.ok(Math.abs(dragged.y - before.y + 9) < 1e-10)
        f.render();assert.deepEqual(f.centers()[n.id], dragged)
        box.state.panX += 37;box.state.panY -= 21;f.render();f.assertAnchors()
        assert.ok(Math.abs(f.centers()[n.id].x - dragged.x - 37) < 1e-10)
        assert.ok(Math.abs(f.centers()[n.id].y - dragged.y + 21) < 1e-10)
    }
})

test('relationship attached note is refreshed from actual noteAnchor after final compact dimensions and transform', () => {
    const f = relationshipHarness(), { box, stockButtons } = f
    const canvas = fs.readFileSync(process.env.MEMBER_MAP_CANVAS || path.resolve(__dirname, '../vercel-api/public/member-map-canvas.html'), 'utf8')
    const start = canvas.indexOf('function noteAnchor('), end = canvas.indexOf('function noteTargetName(', start)
    assert.ok(start >= 0 && end > start)
    box.nodeScale = () => box.state.zoom
    vm.runInNewContext(canvas.slice(start, end), box)
    const el = stockButtons.get('event-a'), note = box.state.notes.attached
    Object.defineProperties(el, {
        offsetWidth: { get() { return this.dataset.overviewTitle === 'true' ? 104 : 160 } },
        offsetHeight: { get() { return this.dataset.overviewTitle === 'true' ? 36 : 60 } },
    })
    const calls = []
    box.renderNotes = () => calls.push({ anchor: clone(box.noteAnchor(note)), compact: el.dataset.overviewTitle,
        transform: el.style.transform })
    const saved = JSON.stringify({ nodes: box.nodeById, notes: box.state.notes })
    for (const zoom of [.2, .649999, .65, .650001, 1.2]) {
        calls.length = 0;box.state.zoom = zoom;f.render()
        assert.equal(calls.length, 2, 'early native note placement plus one non-recursive post-title refresh')
        const early = calls[0], final = calls.at(-1), p = box.point(box.nodeById[note.target])
        assert.notDeepEqual(early.anchor, final.anchor, 'fixture reproduces dimensions changing after native note placement')
        assert.deepEqual(final.anchor, { x: p.x + 104 * zoom / 2 - 2, y: p.y - 36 * zoom / 2 })
        assert.equal(final.compact, 'true')
        assert.equal(final.transform, `translate(-50%,-50%) scale(${zoom})`)
        assert.equal(JSON.stringify({ nodes: box.nodeById, notes: box.state.notes }), saved)
    }
})

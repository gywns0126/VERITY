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
    const baseCalls = { groups: 0, render: 0, edges: 0, visuals: 0 }
    const stockButtons = new Map(), eventButtons = []
    const nodesEl = {
        querySelector(selector) { return stockButtons.get(selector.match(/data-node="([^"]+)"/)?.[1]) },
        querySelectorAll() { return eventButtons },
    }
    const box = {
        document, memberGroupLines: groupLines, state: { zoom, panX: 0, panY: 0 },
        space: { clientWidth: width, clientHeight: height,
            getBoundingClientRect: () => ({ left: 100, top: 50, right: 100 + width, bottom: 50 + height }) },
        holdings: [], shown: () => true, nodesEl, memberGroups: new Map(), noteEls: new Map(),
        point(n) { return { x: width / 2 + (n.x - .5) * 1000 * box.state.zoom + box.state.panX,
            y: height / 2 + (n.y - .5) * 680 * box.state.zoom + box.state.panY } },
        drawMemberGroups() {
            baseCalls.groups++
            for (const n of box.holdings) {
                const button = stockButtons.get(n.id), p = box.point(n)
                Object.assign(button.style, { left: p.x + 'px', top: p.y + 'px', transform: 'translate(-50%,-50%) scale(' + box.state.zoom + ')' })
            }
            for (const group of box.memberGroups.values()) {
                const p = box.point(group)
                Object.assign(group.button.style, { left: p.x + 'px', top: p.y + 'px', transform: 'translate(-50%,-50%) scale(' + box.state.zoom + ')' })
            }
        },
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

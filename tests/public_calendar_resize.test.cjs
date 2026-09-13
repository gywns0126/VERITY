const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const vm = require("node:vm")
const esbuild = require("esbuild")

const target =
    process.env.PUBLIC_CALENDAR_TEST_FILE ||
    path.resolve(
        __dirname,
        "../framer-components/public-probe/PublicCalendar.tsx"
    )
const source = fs.readFileSync(target, "utf8")
const pattern =
    /useEffect\(\(\) => \{\s*const el = rootRef\.current[\s\S]*?\}, \[\]\)/
const effect = source.match(pattern)?.[0]
assert.ok(effect, "root ResizeObserver effect must exist")

function mount({ outer = 590, initial = 0, legacy = false } = {}) {
    let width = initial
    let changes = 0
    let observer
    let cleanup
    const calls = []
    const el = { offsetWidth: outer }

    class Observer {
        constructor(callback) {
            this.callback = callback
            observer = this
        }
        observe(node, options) {
            assert.equal(node, el)
            calls.push(options ? options.box : "default")
            if (legacy && options) throw Error("options unsupported")
        }
        disconnect() {
            this.disconnected = true
        }
    }

    vm.runInNewContext(effect, {
        rootRef: { current: el },
        ResizeObserver: Observer,
        useEffect(callback) {
            cleanup = callback()
        },
        setW(update) {
            const next = typeof update === "function" ? update(width) : update
            if (!Object.is(next, width)) changes++
            width = next
        },
    })

    return {
        el,
        calls,
        get width() {
            return width
        },
        get changes() {
            return changes
        },
        emit(entry) {
            observer.callback([entry])
        },
        close() {
            cleanup()
            assert.equal(observer.disconnected, true)
        },
    }
}

test("old content-box measurement reproduces the tablet feedback loop", () => {
    let width = 0
    const seen = []
    for (let i = 0; i < 6; i++) {
        const padding = width > 0 && width < 560 ? 14 : 20
        width = 590 - 2 * padding
        seen.push(width)
    }
    assert.deepEqual(seen, [550, 562, 550, 562, 550, 562])
})

test("border-box measurement settles once at mobile, tablet and desktop widths", () => {
    for (const outer of [390, 520, 559, 560, 590, 768, 810, 1024, 1200]) {
        const run = mount({ outer })
        for (let i = 0; i < 60; i++) {
            const padding = run.width > 0 && run.width < 560 ? 14 : 20
            run.emit({
                borderBoxSize: [{ inlineSize: outer }],
                contentRect: { width: outer - 2 * padding },
            })
        }
        assert.equal(run.width, outer)
        assert.equal(run.changes, 1)
        assert.deepEqual(run.calls, ["border-box"])
        run.close()
    }
})

test("invalid widths are ignored and legacy observers use offsetWidth", () => {
    const run = mount({ outer: 590, initial: 560 })
    for (const width of [0, -1, NaN, Infinity]) {
        run.emit({ borderBoxSize: [{ inlineSize: width }] })
        assert.equal(run.width, 560)
    }
    run.close()

    const legacy = mount({ outer: 590, legacy: true })
    assert.deepEqual(legacy.calls, ["border-box", "default"])
    legacy.emit({ contentRect: { width: 550 } })
    assert.equal(legacy.width, 590)
    legacy.close()
})

test("production effect avoids content-box width and full TSX compiles", () => {
    assert.doesNotMatch(effect, /contentRect|getBoundingClientRect/)
    assert.match(effect, /borderBoxSize/)
    assert.match(effect, /offsetWidth/)
    assert.doesNotThrow(() =>
        esbuild.transformSync(source, { loader: "tsx", format: "esm" })
    )
})

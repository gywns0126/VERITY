const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const vm = require("node:vm")
const esbuild = require("esbuild")

const target =
    process.env.DISCLOSURE_FEED_TEST_FILE ||
    path.resolve(
        __dirname,
        "../framer-components/public-probe/PublicDisclosureFeed.tsx"
    )
const source = fs.readFileSync(target, "utf8")
const effects = [
    ...source.matchAll(
        /useEffect\(\(\) => \{\s*const el = rootRef\.current[\s\S]*?\}, \[\]\)/g
    ),
]
assert.equal(effects.length, 1, "exactly one root ResizeObserver effect")
const effect = effects[0][0]

function mount({ outer = 520, initial = 0, legacy = false } = {}) {
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

test("old content-box width alternates across the 520px padding breakpoint", () => {
    let width = 0
    const seen = []
    for (let i = 0; i < 6; i++) {
        const pad = width > 0 && width < 520 ? 12 : 18
        width = 548 - 2 * pad
        seen.push(width)
    }
    assert.deepEqual(seen, [512, 524, 512, 524, 512, 524])
})

test("border-box measurement settles once across tablet boundary widths", () => {
    for (const outer of [480, 511, 512, 519, 520, 524, 548, 768, 810, 1024]) {
        const run = mount({ outer })
        for (let i = 0; i < 40; i++) {
            const pad = run.width > 0 && run.width < 520 ? 12 : 18
            run.emit({
                borderBoxSize: [{ inlineSize: outer }],
                contentRect: { width: outer - 2 * pad },
            })
        }
        assert.equal(run.width, outer)
        assert.equal(run.changes, 1)
        assert.deepEqual(run.calls, ["border-box"])
        run.close()
    }
})

test("invalid measurements preserve the last width and legacy APIs use offsetWidth", () => {
    const run = mount({ outer: 768, initial: 520 })
    for (const width of [0, -1, NaN, Infinity]) {
        run.emit({ borderBoxSize: [{ inlineSize: width }] })
        assert.equal(run.width, 520)
    }
    run.close()

    const legacy = mount({ outer: 768, legacy: true })
    assert.deepEqual(legacy.calls, ["border-box", "default"])
    legacy.emit({ contentRect: { width: 732 } })
    assert.equal(legacy.width, 768)
    legacy.close()
})

test("production effect avoids content-box measurement and full TSX compiles", () => {
    assert.doesNotMatch(effect, /contentRect|getBoundingClientRect/)
    assert.match(effect, /borderBoxSize/)
    assert.match(effect, /offsetWidth/)
    assert.doesNotThrow(() =>
        esbuild.transformSync(source, { loader: "tsx", format: "esm" })
    )
})

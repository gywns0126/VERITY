const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const esbuild = require("esbuild")

const target =
    process.env.PUBLIC_PORTFOLIO_LAB_TEST_FILE ||
    path.resolve(
        __dirname,
        "../framer-components/public-probe/PublicPortfolioLab.tsx"
    )
const source = fs.readFileSync(target, "utf8")

test("all three advanced selects use the shared aligned control", () => {
    assert.equal((source.match(/<SelectControl\b/g) || []).length, 3)
    for (const label of ["투자 주기", "비중 조정", "공개 범위"]) {
        assert.match(source, new RegExp(`<SelectControl label="${label}"`))
    }
    assert.equal((source.match(/<select\b/g) || []).length, 1)
})

test("native inset is removed and text starts on the common 15px line", () => {
    assert.match(source, /appearance: "none"/)
    assert.match(source, /WebkitAppearance: "none"/)
    assert.match(source, /paddingLeft: 15/)
    assert.match(source, /paddingRight: 42/)
    assert.match(source, /textAlign: "left"/)
    assert.match(source, /textAlignLast: "left"/)
})

test("custom caret is aligned and cannot intercept selection", () => {
    assert.match(source, /<CaretDown aria-hidden="true"/)
    assert.match(source, /right: 15/)
    assert.match(source, /pointerEvents: "none"/)
})

test("public typography tokens and TSX remain valid", () => {
    assert.doesNotMatch(source, /fontWeight:\s*(?:400|500|650)\b/)
    assert.match(source, /Pretendard, -apple-system, BlinkMacSystemFont/)
    assert.doesNotThrow(() =>
        esbuild.transformSync(source, { loader: "tsx", format: "esm" })
    )
})

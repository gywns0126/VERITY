const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")
const vm = require("node:vm")
const { createRequire } = require("node:module")
const appRequire = createRequire(path.resolve(__dirname, "../operator-web/package.json"))
const ts = appRequire("typescript")
const { renderToStaticMarkup } = appRequire("react-dom/server")
const source = fs.readFileSync(path.resolve(__dirname, "../operator-web/app/components/AnalysisEvidencePanel.tsx"), "utf8")
const exportsObject = {}
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
} }).outputText, { exports: exportsObject,
    require: name => name === "@/lib/theme" ? { NUM: {} } : appRequire(name),
    fetch: () => { throw Error("evidence display must reuse the existing payload") },
})
const render = (rec, summary) => renderToStaticMarkup(exportsObject.default({ rec, summary, c: {} }))

test("legacy or absent recommendations never imply verified source coverage", () => {
    assert.equal(render(undefined), "")
    assert.match(render({ ticker: "TEST" }), /이전 분석에는 진단 기록 없음/)
    assert.doesNotMatch(render({ ticker: "TEST" }), /8\/8/)
})

test("selected source periods, unknowns and mismatches remain distinct", () => {
    const html = render({ ticker: "TEST", verity_brain: { fact_score: { coverage_scope: { source_alignment: {
        aligned_fields: 1, field_count: 8, fields: {
            "stock.revenue": { status: "aligned", source: "SEC", contexts: [{ start: "2025-03-01", end: "2026-02-28", unit: "USD", document_id: "receipt-test" }] },
            "stock.net_income": { status: "mismatch", reasons: ["mixed_accounting_periods"] },
            "graham_value.roe": { status: "unknown", reasons: ["selected_input_has_no_source_evidence"] },
        },
    } } } } })
    for (const value of ["1/8", "2025-03-01", "2026-02-28", "receipt-test", "혼합 회계기간", "확인 불가", "선택한 입력의 원천 근거 없음"])
        assert.ok(html.includes(value), value)
    assert.match(html, /<details/)
    assert.match(html, /<summary/)
})

test("analysis capture time is not substituted for quote time or historical entry evidence", () => {
    const html = render({ ticker: "TEST", currency: "USD",
        evidence_snapshot: { captured_at: "2026-10-15T12:00:00+09:00", input_hash: "0123456789abcdef0123",
            price: { value: 12, as_of: null, source: null, adjustment: null }, run: { run_id: "123", scan_id: "gh:100:1" } },
        rec_price_evidence: { value: 10, status: "unknown", quote_as_of: null, source: null },
        analysis_change: { status: "changed", previous_completed_at: "2026-10-14T12:00:00+09:00", changes: {
            recommendation: { before: "WATCH", after: "BUY" },
            scores: { before: { brain_score: 50 }, after: { brain_score: 61 } },
            inputs: { changed_fields: ["roe"] },
        } },
    })
    for (const text of ["기록 시각 2026-10-15", "가격 기준시각 미확인", "최초 추천 가격 10", "종합 점수 50 → 61", "WATCH → BUY", "기여도로 해석하지 않습니다"])
        assert.ok(html.includes(text), text)
})

test("rejected quote and unavailable comparison axes are visible with the cohort denominator", () => {
    const html = render({ ticker: "TEST", evidence_snapshot: {
        price: { value: 12, status: "unknown", as_of: "2026-10-16T12:00:00+09:00", source: "fixture", adjustment: false, reasons: ["quote_timestamp_after_capture"] },
    }, rec_price_evidence: { value: 10, status: "unknown", quote_reasons: ["legacy_origin_unavailable"] },
    analysis_change: { status: "unchanged", reasons: ["previous_analysis_price_observation_unavailable", "previous_or_current_input_snapshot_unavailable"] },
    }, { current_count: 40, compared_count: 30, unresolved_count: 10, price_compared_count: 0, input_compared_count: 0, input_snapshot_count: 40, baseline_source: "legacy_local" })
    for (const text of ["가격 근거: 확인 불가", "미래여서 검증 거부", "최초 추천 가격 근거 확인 불가", "가격 변화 비교 불가", "입력·공시 변화 비교 불가", "전체 40종목 · 비교 30 · 비교 불가 10", "가격 비교 0/40", "입력 비교 0/40", "비공개 기준본 확인 불가"])
        assert.ok(html.includes(text), text)
})

test("equal coverage does not hide changed measurement axes, missing fields or source mismatch", () => {
    const html = render({ ticker: "TEST", analysis_change: { status: "changed", changes: { measurement: {
        before: { data_coverage: 0.8, component_states: { graham_value: "measured" }, fundamental_missing_fields: [], source_alignment_status: "aligned" },
        after: { data_coverage: 0.8, component_states: { graham_value: "missing" }, fundamental_missing_fields: ["roe"], source_alignment_status: "mismatch" },
    } } } })
    for (const text of ["가치·재무 실측 → 결측", "결측 항목 없음 → ROE", "원천 정합 정보 일치 → 불일치"])
        assert.ok(html.includes(text), text)
    assert.doesNotMatch(html, /0.8 → 0.8/)
})

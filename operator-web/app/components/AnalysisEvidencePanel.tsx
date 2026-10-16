import type { Rec, AnalysisChanges, AnalysisMeasurement } from "@/lib/types"
import { NUM, type Palette } from "@/lib/theme"

const fieldNames: Record<string, string> = {
    "graham_value.debt_ratio": "부채비율", "graham_value.roe": "ROE", "graham_value.current_ratio": "유동비율",
    "stock.revenue": "매출", "stock.operating_profit": "영업이익", "stock.net_income": "순이익",
    "stock.operating_cashflow": "영업현금흐름", "stock.operating_margin": "영업이익률",
}
const statusNames: Record<string, string> = { aligned: "정보 일치", mismatch: "불일치", unknown: "확인 불가", missing: "입력 없음", partial: "일부 일치" }
const inputNames: Record<string, string> = { roe: "ROE", per: "PER", pbr: "PBR", debt_ratio: "부채비율", current_ratio: "유동비율", revenue: "매출", operating_profit: "영업이익", net_income: "순이익", operating_cashflow: "영업현금흐름", operating_margin: "영업이익률", price: "가격", macro: "거시 환경" }
const reasonNames: Record<string, string> = {
    selected_input_has_no_source_evidence: "선택한 입력의 원천 근거 없음",
    no_finite_selected_input: "사용할 수 있는 수치 없음",
    ticker_mismatch: "종목 불일치", source_ticker_mismatch: "원천 종목 불일치",
    issuer_id_missing: "발행사 식별자 없음", issuer_id_mismatch: "발행사 불일치", source_issuer_mismatch: "원천 발행사 불일치",
    selected_value_mismatch: "입력 값 불일치", source_unit_missing: "원천 단위 없음",
    source_currency_mismatch: "통화 불일치", output_unit_mismatch: "출력 단위 불일치",
    mixed_source_units: "혼합 단위", mixed_accounting_periods: "혼합 회계기간", mixed_disclosures: "서로 다른 공시",
    filing_or_period_date_missing: "공시일 또는 보고기간 없음", duration_start_or_end_missing: "보고기간 시작·종료일 없음",
    annual_quarter_or_cumulative_definition_mismatch: "연간·분기·누적 기준 불일치",
    definition_or_output_unit_missing: "정의 또는 출력 단위 없음", source_operands_missing: "산식 원천 입력 없음",
    source_operand_missing: "일부 산식 원천 입력 없음", document_or_concept_missing: "접수번호 또는 계정 없음",
    filed_before_period_end: "보고기간보다 이른 공시일", financial_statement_scope_missing: "연결·별도 구분 없음",
    mixed_financial_statement_scopes: "연결·별도 혼합", unmeasured_source_operand: "측정되지 않은 산식 입력",
    unsupported_or_unidentified_primary_source: "원천 식별 미확인",
    malformed_source_evidence: "출처 정보 형식 오류",
    quote_timestamp_after_capture: "가격 기준시각이 기록 시각보다 미래여서 검증 거부",
    quote_timestamp_missing_or_invalid: "가격 기준시각 없음 또는 형식 오류",
    price_missing_or_invalid: "가격 없음 또는 유효하지 않은 값",
    price_source_unknown: "가격 출처 미확인", price_adjustment_unknown: "가격 조정 여부 미확인",
    previous_analysis_price_observation_unavailable: "이전 가격 기록이 없어 가격 변화 비교 불가",
    previous_or_current_input_snapshot_unavailable: "입력 원본이 없어 입력·공시 변화 비교 불가",
    legacy_origin_unavailable: "최초 추천 시점 근거 없음",
    diagnostic_capture_failed: "이번 실행의 근거 기록 실패",
    new_identity: "직전 분석에 같은 종목·통화 없음", missing_identity: "종목·통화 식별 불가",
    ambiguous_identity: "중복된 종목·통화로 비교 불가", previous_analysis_not_completed: "이전 분석 완료 여부 미확인",
}

const stateName = (state?: string) => ({ ...statusNames, measured: "실측", substituted: "대체", missing: "결측", not_applicable: "적용 제외" })[state ?? "unknown"] ?? state
const namedFields = (fields?: string[] | null) => fields == null ? "미확인" : fields.length ? fields.map(key => inputNames[key] ?? key).join(", ") : "없음"
function MeasurementChanges({ before = {}, after = {} }: { before?: AnalysisMeasurement; after?: AnalysisMeasurement }) {
    const axes = [...new Set([...Object.keys(before.component_states ?? {}), ...Object.keys(after.component_states ?? {})])]
    const axisNames: Record<string, string> = { graham_value: "가치·재무", lynch_growth: "성장", quality: "퀄리티", quant: "정량", consensus: "컨센서스" }
    return <div>
        {before.data_coverage !== after.data_coverage ? <div>입력 커버리지 {before.data_coverage ?? "미확인"} → {after.data_coverage ?? "미확인"}</div> : null}
        {axes.filter(key => before.component_states?.[key] !== after.component_states?.[key]).map(key => <div key={key}>{axisNames[key] ?? key} {stateName(before.component_states?.[key])} → {stateName(after.component_states?.[key])}</div>)}
        {JSON.stringify(before.fundamental_missing_fields) !== JSON.stringify(after.fundamental_missing_fields) ? <div>결측 항목 {namedFields(before.fundamental_missing_fields)} → {namedFields(after.fundamental_missing_fields)}</div> : null}
        {before.source_alignment_status !== after.source_alignment_status ? <div>원천 정합 {stateName(before.source_alignment_status)} → {stateName(after.source_alignment_status)}</div> : null}
        {Object.keys(after.source_alignment_counts ?? {}).filter(key => before.source_alignment_counts?.[key] !== after.source_alignment_counts?.[key]).map(key => <div key={key}>원천 {stateName(key)} 항목 {before.source_alignment_counts?.[key] ?? "미확인"} → {after.source_alignment_counts?.[key]}</div>)}
    </div>
}

/** Uses the selected analysis already fetched by the page; adds no requests. */
export default function AnalysisEvidencePanel({ rec, summary, c }: { rec?: Rec; summary?: AnalysisChanges; c: Palette }) {
    const alignment = rec?.verity_brain?.fact_score?.coverage_scope?.source_alignment
    if (!rec) return null
    const snapshot = rec.evidence_snapshot
    const entry = rec.rec_price_evidence
    const change = rec.analysis_change
    const changes = change?.changes
    const value = (v: string | number | null | undefined) => v == null ? "미확인" : typeof v === "number" ? v.toLocaleString() : v
    const adjustment = (v: string | boolean | null | undefined) => v === true ? "조정 가격" : v === false ? "비조정 가격" : !v || v === "unknown" ? "미확인" : v
    const source = (v: string | null | undefined) => !v || v === "unknown" ? "미확인" : v
    return (
        <details className="af-console-disclosure">
            <summary>자동 분석 입력 근거 · {alignment?.field_count ? `${alignment.aligned_fields ?? 0}/${alignment.field_count} 정보 일치` : alignment ? "진단 확인 불가" : "이전 분석에는 진단 기록 없음"}</summary>
            <div style={{ padding: "8px 12px", fontSize: 12, color: c.sub, lineHeight: 1.6 }}>
                {summary ? <div style={{ marginBottom: 12 }}>
                    전체 {summary.current_count ?? "미확인"}종목 · 비교 {summary.compared_count ?? "미확인"} · 비교 불가 {summary.unresolved_count ?? "미확인"}
                    <div>가격 비교 {summary.price_compared_count ?? "미확인"}/{summary.current_count ?? "미확인"} · 입력 비교 {summary.input_compared_count ?? "미확인"}/{summary.current_count ?? "미확인"} · 입력 원본 기록 {summary.input_snapshot_count ?? "미확인"}/{summary.current_count ?? "미확인"}</div>
                    <div>비교 기준: {summary.baseline_source === "private_storage" ? "이전 비공개 완료 분석" : "기존 로컬 기록 · 비공개 기준본 확인 불가"}</div>
                </div> : null}
                {change ? <div style={{ marginBottom: 12 }}>
                    <b style={{ color: c.ink }}>직전 완료 분석과 비교</b>
                    <div>{change.previous_completed_at ?? "비교할 완료 기록 없음"}</div>
                    {change.status === "unchanged" ? <div>비교한 항목의 변화 없음</div> : null}
                    {change.status === "unavailable" ? <div>동일 종목·통화의 비교 근거 부족</div> : null}
                    {change.reasons?.map(reason => <div key={reason} style={{ color: c.amber }}>{reasonNames[reason] ?? reason}</div>)}
                    {changes?.grade ? <div>등급 {value(changes.grade.before)} → {value(changes.grade.after)}</div> : null}
                    {changes?.recommendation ? <div>추천 {value(changes.recommendation.before)} → {value(changes.recommendation.after)}</div> : null}
                    {changes?.price ? <div>입력 가격 {value(changes.price.before)} → {value(changes.price.after)}</div> : null}
                    {changes?.scores ? Object.entries({ brain_score: "종합 점수", fact_score: "팩트 점수", sentiment_score: "심리 점수" }).map(([key, label]) => {
                        const before = changes.scores?.before?.[key], after = changes.scores?.after?.[key]
                        return before !== after ? <div key={key}>{label} {value(before)} → {value(after)}</div> : null
                    }) : null}
                    {changes?.measurement ? <MeasurementChanges {...changes.measurement} /> : null}
                    {changes?.inputs?.changed_fields?.length ? <div>변경된 입력: {changes.inputs.changed_fields.map(key => inputNames[key] ?? key).join(", ")}</div> : null}
                    {changes?.inputs?.context_changed ? <div>거시·시장 입력 변경</div> : null}
                    {changes?.disclosures?.changed_fields?.length ? <div>변경된 공시 근거: {changes.disclosures.changed_fields.join(", ")}</div> : null}
                    {change.status === "changed" ? <div style={{ color: c.faint }}>함께 바뀐 항목을 표시하며, 점수 변화의 기여도로 해석하지 않습니다.</div> : null}
                </div> : null}
                {snapshot ? <div style={{ marginBottom: 12, overflowWrap: "anywhere" }}>
                    <b style={{ color: c.ink }}>분석 시점 기록</b>
                    <div>가격 근거: {snapshot.price?.status === "captured" ? "기록됨" : "확인 불가"}</div>
                    {snapshot.price?.reasons?.map(reason => <div key={reason} style={{ color: c.amber }}>{reasonNames[reason] ?? reason}</div>)}
                    <div>기록 시각 {snapshot.captured_at ?? "미확인"}</div>
                    <div>사용 가격 {snapshot.price?.value == null ? "미확인" : `${snapshot.price.value.toLocaleString()} ${rec.currency ?? ""}`} · 가격 기준시각 {snapshot.price?.as_of ?? "미확인"}</div>
                    <div>출처 {source(snapshot.price?.source)} · 가격 조정 {adjustment(snapshot.price?.adjustment)}</div>
                    <div>실행 {snapshot.run?.run_id ?? "미확인"} · 스캔 {snapshot.run?.scan_id ?? "미확인"}</div>
                    <div title={snapshot.input_hash}>입력 식별값 {snapshot.input_hash?.slice(0, 16) ?? "미확인"}</div>
                    {entry ? <div>최초 추천 가격 {entry.value == null ? "미확인" : entry.value.toLocaleString()} · 기준시각 {entry.quote_as_of ?? "미확인"} · 출처 {source(entry.source)}</div> : null}
                    {entry && entry.status !== "captured" ? <div style={{ color: c.amber }}>최초 추천 가격 근거 확인 불가{entry.quote_reasons?.length ? ` · ${entry.quote_reasons.map(reason => reasonNames[reason] ?? reason).join(" · ")}` : ""}</div> : null}
                </div> : null}
                <p style={{ margin: "0 0 8px" }}>선택된 회계 입력의 종목·보고기간·통화·단위를 대조합니다. 수치 자체의 정확성이나 분석 전체의 품질을 뜻하지 않습니다.</p>
                {Object.entries(alignment?.fields ?? {}).map(([key, field]) => (
                    <div key={key} style={{ padding: "7px 0", borderTop: `1px solid ${c.track}`, overflowWrap: "anywhere" }}>
                        <b style={{ color: c.ink }}>{fieldNames[key] ?? key}</b>{" · "}
                        <span style={{ color: field.status === "mismatch" ? c.amber : c.sub }}>{statusNames[field.status ?? "unknown"] ?? field.status}</span>
                        {field.source ? ` · ${field.source}` : ""}
                        {field.reasons?.length ? <div>{field.reasons.map(reason => reasonNames[reason] ?? reason).join(" · ")}</div> : null}
                        {field.contexts?.map((context, index) => <div key={index} style={{ color: c.faint, fontSize: 11, ...NUM }}>
                            {context.start ? `${context.start} ~ ` : ""}{context.end ?? "기간 미확인"}{" · "}{context.unit ?? "단위 미확인"}{" · "}{context.document_id ?? "접수번호 미확인"}
                        </div>)}
                    </div>
                ))}
            </div>
        </details>
    )
}

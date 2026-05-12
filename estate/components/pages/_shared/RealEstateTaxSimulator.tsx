import { addPropertyControls, ControlType } from "framer"
import React, { useState, useCallback } from "react"

/* ◆ ESTATE DESIGN TOKENS v1.1 (다크 + 골드 — 패밀리룩) ◆ */
const C = {
    bgPage: "#0A0908",
    bgCard: "#0F0D0A",
    bgElevated: "#16130E",
    bgInput: "#1F1B14",
    border: "transparent",
    borderStrong: "#3A3024",
    textPrimary: "#F2EFE9",
    textSecondary: "#A8A299",
    textTertiary: "#6B665E",
    textDisabled: "#4A453E",
    accent: "#B8864D",
    accentBright: "#D4A26B",
    accentSoft: "rgba(184,134,77,0.15)",
    success: "#22C55E",
    warn: "#F59E0B",
    danger: "#EF4444",
    info: "#5BA9FF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
/* ◆ TOKENS END ◆ */

const ESTATE_API_BASE = "https://project-yw131.vercel.app"
const TAX_SIMULATOR_URL = `${ESTATE_API_BASE}/api/estate/tax-simulator`

/* ──────────────────────────────────────────────────────────────
 * RealEstateTaxSimulator — ESTATE Tier 2 / F
 *
 * 한국 부동산 1세대 1주택 세제 시뮬레이션:
 *   취득세 (1회) + 연간 보유세 (재산세 + 종부세) + 양도세 (매도 시).
 * 외부 API 없음 — 룰 표 endpoint 내장.
 * docs/REAL_ESTATE_TAX_SIMULATOR_PLAN_v0.1.md 참조.
 * ────────────────────────────────────────────────────────────── */

interface Breakdown {
    rate?: number
    deduction?: number
    applied_bracket?: string | number
    taxable_base?: number
    deduction_applied?: number
    fair_market_ratio?: number
    status?: string
    taxable_gain?: number
    long_term_deduction_rate?: number
    after_deduction?: number
    exempt_threshold?: number
}

interface SimulationResult {
    acquisition_tax: number
    annual_property_tax: number
    annual_comprehensive_tax: number
    annual_holding_tax: number
    total_holding_tax: number
    capital_gains_tax: number
    total_burden: number
    effective_rate: number
    breakdown: {
        acquisition: Breakdown
        property: Breakdown
        comprehensive: Breakdown
        capital_gains: Breakdown
    }
    input: {
        purchase_price: number
        appraised_value: number
        holding_years: number
        residence_years: number
        sale_price: number
    }
    track: string
}

interface Props {
    apiUrlOverride?: string
}

const fmt = (n: number) => n.toLocaleString("ko-KR")

const PRESETS = [
    { label: "예시 1: 6억 매수 → 5년 후 8억 매도", purchase_price: 600_000_000, holding_years: 5, residence_years: 5, sale_price: 800_000_000 },
    { label: "예시 2: 10억 매수 → 3년 후 14억 매도", purchase_price: 1_000_000_000, holding_years: 3, residence_years: 3, sale_price: 1_400_000_000 },
    { label: "예시 3: 8억 매수 → 1년 미만 단기 매도", purchase_price: 800_000_000, holding_years: 0, residence_years: 0, sale_price: 1_000_000_000 },
]

export default function RealEstateTaxSimulator(props: Props) {
    const url = (props.apiUrlOverride && props.apiUrlOverride.trim()) || TAX_SIMULATOR_URL

    const [purchasePrice, setPurchasePrice] = useState<string>("500000000")
    const [appraisedValue, setAppraisedValue] = useState<string>("")
    const [holdingYears, setHoldingYears] = useState<string>("5")
    const [residenceYears, setResidenceYears] = useState<string>("5")
    const [salePrice, setSalePrice] = useState<string>("700000000")
    const [result, setResult] = useState<SimulationResult | null>(null)
    const [loading, setLoading] = useState<boolean>(false)
    const [error, setError] = useState<string | null>(null)
    const [showBreakdown, setShowBreakdown] = useState<boolean>(false)

    const applyPreset = useCallback((p: typeof PRESETS[0]) => {
        setPurchasePrice(String(p.purchase_price))
        setHoldingYears(String(p.holding_years))
        setResidenceYears(String(p.residence_years))
        setSalePrice(String(p.sale_price))
        setAppraisedValue("")
    }, [])

    const run = useCallback(() => {
        setLoading(true)
        setError(null)
        const body: Record<string, number> = {
            purchase_price: parseInt(purchasePrice, 10) || 0,
            holding_years: parseInt(holdingYears, 10) || 0,
            residence_years: parseInt(residenceYears, 10) || 0,
            sale_price: parseInt(salePrice, 10) || 0,
        }
        if (appraisedValue) body.appraised_value = parseInt(appraisedValue, 10) || 0

        fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        })
            .then(async (r) => {
                const data = await r.json()
                if (!r.ok) throw new Error(data?.message || `HTTP ${r.status}`)
                return data as SimulationResult
            })
            .then((d) => {
                setResult(d)
                setLoading(false)
            })
            .catch((e) => {
                setError(String(e?.message || e))
                setResult(null)
                setLoading(false)
            })
    }, [url, purchasePrice, appraisedValue, holdingYears, residenceYears, salePrice])

    return (
        <div
            style={{
                width: "100%",
                background: C.bgCard,
                borderRadius: R.lg,
                padding: 16,
                fontFamily: FONT,
                color: C.textPrimary,
                boxSizing: "border-box",
                border: `1px solid ${C.borderStrong}`,
            }}
        >
            {/* HEADER */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
                <span style={{ fontSize: 11, letterSpacing: 1.2, color: C.accent, fontFamily: FONT_MONO }}>
                    TAX SIMULATOR · 1주택 v0
                </span>
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, color: C.textPrimary, marginBottom: 12 }}>
                부동산 세제 시뮬레이터
                <span style={{ fontSize: 12, fontWeight: 400, color: C.textSecondary, marginLeft: 8 }}>
                    취득 · 보유 · 양도
                </span>
            </div>

            {/* PRESETS */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 12 }}>
                {PRESETS.map((p, i) => (
                    <button
                        key={i}
                        onClick={() => applyPreset(p)}
                        style={{
                            background: "transparent",
                            color: C.textSecondary,
                            border: `1px solid ${C.borderStrong}`,
                            borderRadius: R.pill,
                            padding: "3px 9px",
                            fontSize: 10,
                            cursor: "pointer",
                            transition: "all 150ms ease",
                        }}
                    >
                        {p.label}
                    </button>
                ))}
            </div>

            {/* INPUTS */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
                <Field label="매수가 (원)" value={purchasePrice} onChange={setPurchasePrice} />
                <Field
                    label="공시가격 (원, 선택)"
                    value={appraisedValue}
                    onChange={setAppraisedValue}
                    placeholder="비우면 매수가 × 70%"
                />
                <Field label="보유기간 (년)" value={holdingYears} onChange={setHoldingYears} />
                <Field label="거주기간 (년)" value={residenceYears} onChange={setResidenceYears} />
                <Field
                    label="매도가 (원, 선택)"
                    value={salePrice}
                    onChange={setSalePrice}
                    placeholder="비우면 양도세 0"
                />
                <button
                    onClick={run}
                    disabled={loading}
                    style={{
                        background: C.accent,
                        color: C.bgPage,
                        border: "none",
                        borderRadius: R.md,
                        padding: "0 16px",
                        fontSize: 12,
                        fontWeight: 600,
                        fontFamily: FONT,
                        cursor: loading ? "wait" : "pointer",
                        alignSelf: "stretch",
                        marginTop: 16,
                        opacity: loading ? 0.6 : 1,
                    }}
                >
                    {loading ? "계산중…" : "시뮬레이션"}
                </button>
            </div>

            {/* ERROR */}
            {error && (
                <div
                    style={{
                        padding: 12,
                        background: C.bgInput,
                        border: `1px solid ${C.danger}`,
                        borderRadius: R.md,
                        color: C.danger,
                        fontSize: 11,
                        marginBottom: 8,
                    }}
                >
                    {error}
                </div>
            )}

            {/* RESULT */}
            {result && (
                <>
                    <div
                        style={{
                            background: C.bgElevated,
                            border: `1px solid ${C.borderStrong}`,
                            borderRadius: R.md,
                            padding: 12,
                            marginTop: 8,
                            marginBottom: 8,
                        }}
                    >
                        <ResultRow
                            label="취득세 (1회)"
                            value={result.acquisition_tax}
                            secondary={result.breakdown.acquisition.applied_bracket as string}
                        />
                        <ResultRow
                            label={`재산세 (연간 × ${result.input.holding_years}년)`}
                            value={result.annual_property_tax}
                            total={result.annual_property_tax * result.input.holding_years}
                        />
                        <ResultRow
                            label={`종부세 (연간 × ${result.input.holding_years}년)`}
                            value={result.annual_comprehensive_tax}
                            total={result.annual_comprehensive_tax * result.input.holding_years}
                            note={result.annual_comprehensive_tax === 0 ? "12억 공제 적용" : undefined}
                        />
                        <ResultRow
                            label="양도세"
                            value={result.capital_gains_tax}
                            note={
                                result.breakdown.capital_gains.status === "exempt_1house_under_12억"
                                    ? "1주택 12억 이하 비과세"
                                    : result.breakdown.capital_gains.status
                            }
                        />
                        <div
                            style={{
                                borderTop: `1px solid ${C.borderStrong}`,
                                marginTop: 8,
                                paddingTop: 8,
                                display: "flex",
                                justifyContent: "space-between",
                                fontSize: 14,
                                fontWeight: 600,
                            }}
                        >
                            <span style={{ color: C.accentBright }}>총 부담</span>
                            <span style={{ color: C.accentBright, fontFamily: FONT_MONO }}>
                                {fmt(result.total_burden)}원
                            </span>
                        </div>
                        <div
                            style={{
                                display: "flex",
                                justifyContent: "space-between",
                                fontSize: 11,
                                color: C.textTertiary,
                                marginTop: 4,
                            }}
                        >
                            <span>실효세율</span>
                            <span style={{ fontFamily: FONT_MONO }}>
                                {(result.effective_rate * 100).toFixed(2)}%
                            </span>
                        </div>
                    </div>

                    <button
                        onClick={() => setShowBreakdown((v) => !v)}
                        style={{
                            background: "transparent",
                            color: C.textTertiary,
                            border: `1px solid ${C.borderStrong}`,
                            borderRadius: R.sm,
                            padding: "4px 10px",
                            fontSize: 10,
                            fontFamily: FONT_MONO,
                            cursor: "pointer",
                            marginBottom: 8,
                        }}
                    >
                        {showBreakdown ? "▼ 산식 숨기기" : "▶ 산식 보기"}
                    </button>

                    {showBreakdown && (
                        <pre
                            style={{
                                fontSize: 10,
                                fontFamily: FONT_MONO,
                                color: C.textTertiary,
                                background: C.bgElevated,
                                padding: 10,
                                borderRadius: R.sm,
                                overflowX: "auto",
                                margin: 0,
                                marginBottom: 8,
                            }}
                        >
                            {JSON.stringify(result.breakdown, null, 2)}
                        </pre>
                    )}
                </>
            )}

            {/* DISCLAIMER */}
            <div
                style={{
                    fontSize: 9,
                    color: C.textTertiary,
                    fontFamily: FONT,
                    lineHeight: 1.4,
                    marginTop: 8,
                    paddingTop: 8,
                    borderTop: `1px dashed ${C.borderStrong}`,
                }}
            >
                v0 = 1세대 1주택 트랙. 다주택·법인·임대사업자 미지원. 실 신고 전 국세청 또는 세무사 확인 의무.
                2026 기준 룰. 변경 시 운영 코드 갱신.
            </div>
        </div>
    )
}

function Field({
    label, value, onChange, placeholder,
}: {
    label: string
    value: string
    onChange: (v: string) => void
    placeholder?: string
}) {
    return (
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11 }}>
            <span style={{ color: C.textTertiary }}>{label}</span>
            <input
                type="number"
                inputMode="numeric"
                value={value}
                placeholder={placeholder}
                onChange={(e) => onChange(e.target.value)}
                style={{
                    background: C.bgInput,
                    border: `1px solid ${C.borderStrong}`,
                    borderRadius: R.sm,
                    padding: "6px 8px",
                    color: C.textPrimary,
                    fontSize: 12,
                    fontFamily: FONT_MONO,
                    outline: "none",
                }}
            />
        </label>
    )
}

function ResultRow({
    label, value, total, secondary, note,
}: {
    label: string
    value: number
    total?: number
    secondary?: string
    note?: string
}) {
    return (
        <div
            style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                padding: "4px 0",
                fontSize: 12,
            }}
        >
            <div style={{ display: "flex", flexDirection: "column" }}>
                <span style={{ color: C.textPrimary }}>{label}</span>
                {secondary && (
                    <span style={{ fontSize: 9, color: C.textTertiary, fontFamily: FONT_MONO }}>
                        {secondary}
                    </span>
                )}
                {note && (
                    <span style={{ fontSize: 9, color: C.accent, fontFamily: FONT_MONO }}>
                        · {note}
                    </span>
                )}
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
                <span style={{ color: C.textPrimary, fontFamily: FONT_MONO }}>{fmt(value)}원</span>
                {total !== undefined && total !== value && (
                    <span style={{ fontSize: 9, color: C.textTertiary, fontFamily: FONT_MONO }}>
                        총 {fmt(total)}원
                    </span>
                )}
            </div>
        </div>
    )
}

addPropertyControls(RealEstateTaxSimulator, {
    apiUrlOverride: {
        type: ControlType.String,
        title: "API URL (override)",
        defaultValue: "",
        placeholder: TAX_SIMULATOR_URL,
    },
})

// CorpDisposalsPanel — CATALYST (종목 부동산 매각 공시 추적)
// ESTATE 폐기(2026-05-21) 후 VERITY 터미널 re-home + reframe:
//   부동산 매각 공시 = 주식 catalyst (본사·공장 매각 → 현금유입/특별배당/구조조정).
//   ticker 입력 → DART 주요사항보고서 + 키워드 필터 (부동산 ∩ 처분).
// Backend: /api/estate/corp-disposals (보존). RULE 6 정합 — 공시 list + 메타 only, LLM narrative X.
// ⚠ corp snapshot(portfolio/recommendations 종목)만 수집 대상.

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"

/* ◆ VERITY 터미널 토큰 ◆ */
const C = {
    bgCard: "#0E0F11", bgElevated: "#16161D", bgInput: "#1C1C25",
    borderStrong: "#2E2E37", borderSoft: "#202026",
    textPrimary: "#F2F3F5", textSecondary: "#9AA0AA", textTertiary: "#5E5E68",
    accent: "#B5FF17", accentSoft: "rgba(181,255,23,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const R = { sm: 6, md: 10, lg: 14, pill: 999 }

const API_BASE = "https://project-yw131.vercel.app"

interface Disposal {
    rcept_dt: string
    report_nm: string
    rcept_no: string
    flr_nm?: string
}

interface DisposalsPayload {
    ticker: string
    corp_code: string
    company_name: string
    period_months: number
    disposals: Disposal[]
    total_count: number
}

interface ApiError {
    error: string
    message: string
}

interface Props {
    defaultTicker?: string
    apiUrlOverride?: string
}

const MONTH_OPTIONS = [6, 12, 24]
const TICKER_RE = /^\d{6}$/

export default function CorpDisposalsPanel(props: Props) {
    const base = (props.apiUrlOverride && props.apiUrlOverride.trim()) || API_BASE
    const [tickerInput, setTickerInput] = useState<string>(props.defaultTicker?.trim() || "")
    const [activeTicker, setActiveTicker] = useState<string>(props.defaultTicker?.trim() || "")
    const [months, setMonths] = useState<number>(12)
    const [data, setData] = useState<DisposalsPayload | null>(null)
    const [err, setErr] = useState<ApiError | null>(null)
    const [loading, setLoading] = useState<boolean>(false)

    const tickerValid = useMemo(() => TICKER_RE.test(tickerInput), [tickerInput])

    useEffect(() => {
        if (!activeTicker || !TICKER_RE.test(activeTicker)) {
            setData(null); setErr(null); return
        }
        let cancelled = false
        setLoading(true); setErr(null)
        const url = `${base}/api/estate/corp-disposals?ticker=${activeTicker}&months=${months}`
        fetch(url)
            .then(async (r) => {
                const j = await r.json()
                if (!r.ok) throw j
                return j
            })
            .then((d: DisposalsPayload) => {
                if (cancelled) return
                setData(d); setLoading(false)
            })
            .catch((e: any) => {
                if (cancelled) return
                setErr({ error: e?.error || "fetch_failed", message: e?.message || String(e) })
                setData(null); setLoading(false)
            })
        return () => { cancelled = true }
    }, [base, activeTicker, months])

    const onSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        if (tickerValid) setActiveTicker(tickerInput)
    }

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
                border: `1px solid ${C.borderSoft}`,
            }}
        >
            {/* HEADER */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
                <span style={{ fontSize: 11, letterSpacing: 1.2, color: C.accent, fontFamily: FONT_MONO }}>
                    CATALYST
                </span>
                <span style={{ fontSize: 11, color: C.textTertiary }}>종목 부동산 매각 공시</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: C.textPrimary }}>
                    부동산 매각 catalyst
                </div>
                <span style={{ fontSize: 12, color: C.textSecondary }}>DART 주요사항보고서</span>
            </div>

            {/* CONTROLS */}
            <form onSubmit={onSubmit} style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                <input
                    type="text"
                    value={tickerInput}
                    onChange={(e) => setTickerInput(e.target.value.replace(/[^\d]/g, "").slice(0, 6))}
                    placeholder="ticker 6자리 (예: 035420)"
                    style={{
                        flex: 1,
                        background: C.bgInput,
                        border: `1px solid ${tickerValid || !tickerInput ? C.borderStrong : C.danger}`,
                        borderRadius: R.sm,
                        color: C.textPrimary,
                        padding: "6px 10px",
                        fontSize: 13,
                        fontFamily: FONT_MONO,
                        outline: "none",
                    }}
                />
                <select
                    value={months}
                    onChange={(e) => setMonths(Number(e.target.value))}
                    style={{
                        background: C.bgInput,
                        border: `1px solid ${C.borderStrong}`,
                        borderRadius: R.sm,
                        color: C.textPrimary,
                        padding: "6px 10px",
                        fontSize: 12,
                        fontFamily: FONT_MONO,
                        outline: "none",
                    }}
                >
                    {MONTH_OPTIONS.map((m) => (
                        <option key={m} value={m}>최근 {m}개월</option>
                    ))}
                </select>
                <button
                    type="submit"
                    disabled={!tickerValid}
                    style={{
                        background: tickerValid ? C.accent : C.borderSoft,
                        color: tickerValid ? "#08070E" : C.textTertiary,
                        border: "none",
                        borderRadius: R.sm,
                        padding: "6px 14px",
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: tickerValid ? "pointer" : "not-allowed",
                    }}
                >
                    조회
                </button>
            </form>

            {/* CONTENT */}
            {!activeTicker ? (
                <Placeholder text="ticker 6자리 입력 후 조회" />
            ) : loading ? (
                <SkeletonRows />
            ) : err ? (
                <ErrorBlock err={err} />
            ) : data ? (
                <DisposalsList data={data} />
            ) : null}
        </div>
    )
}

function DisposalsList({ data }: { data: DisposalsPayload }) {
    return (
        <>
            {/* COMPANY META */}
            <div
                style={{
                    background: C.bgElevated,
                    border: `1px solid ${C.borderStrong}`,
                    borderRadius: R.md,
                    padding: 10,
                    marginBottom: 10,
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    fontSize: 12,
                }}
            >
                <div style={{ fontWeight: 600 }}>{data.company_name}</div>
                <span style={{ color: C.textTertiary, fontFamily: FONT_MONO, fontSize: 11 }}>{data.ticker}</span>
                <span
                    style={{
                        marginLeft: "auto",
                        fontFamily: FONT_MONO,
                        fontSize: 11,
                        color: data.total_count === 0 ? C.textTertiary : C.accent,
                    }}
                >
                    {data.total_count === 0 ? "공시 없음" : `${data.total_count}건 / 최근 ${data.period_months}개월`}
                </span>
            </div>

            {/* LIST */}
            {data.total_count === 0 ? (
                <Placeholder text={`최근 ${data.period_months}개월 부동산·유형자산 양도/처분 공시 없음`} />
            ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {data.disposals.map((d) => (
                        <DisposalRow key={d.rcept_no} d={d} />
                    ))}
                </div>
            )}
        </>
    )
}

function DisposalRow({ d }: { d: Disposal }) {
    const date = d.rcept_dt && d.rcept_dt.length === 8
        ? `${d.rcept_dt.slice(0, 4)}-${d.rcept_dt.slice(4, 6)}-${d.rcept_dt.slice(6, 8)}`
        : d.rcept_dt
    return (
        <a
            href={`https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${d.rcept_no}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "8px 10px",
                background: C.bgElevated,
                border: `1px solid ${C.borderSoft}`,
                borderRadius: R.sm,
                textDecoration: "none",
                color: C.textPrimary,
                transition: "border-color 200ms ease",
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = C.accent }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = C.borderSoft }}
        >
            <span style={{ fontSize: 11, fontFamily: FONT_MONO, color: C.textTertiary, minWidth: 80 }}>{date}</span>
            <span style={{ flex: 1, fontSize: 12, color: C.textPrimary }}>{d.report_nm}</span>
            <span style={{ fontSize: 10, fontFamily: FONT_MONO, color: C.accent }}>DART ↗</span>
        </a>
    )
}

function ErrorBlock({ err }: { err: ApiError }) {
    const isNoData = err.error === "no_corp_data"
    return (
        <div
            style={{
                padding: 16,
                textAlign: "center",
                color: isNoData ? C.textTertiary : C.danger,
                fontSize: 12,
                background: C.bgElevated,
                borderRadius: R.md,
                border: `1px dashed ${isNoData ? C.borderStrong : C.danger}`,
            }}
        >
            <div style={{ fontFamily: FONT_MONO, fontSize: 10, marginBottom: 4 }}>{err.error}</div>
            <div>{err.message}</div>
            {isNoData && (
                <div style={{ fontSize: 10, color: C.textTertiary, marginTop: 4 }}>
                    corp snapshot 미수집 — portfolio/recommendations 내 종목만 수집 대상
                </div>
            )}
        </div>
    )
}

function SkeletonRows() {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {[0, 1, 2].map((i) => (
                <div key={i} style={{ height: 34, background: C.bgElevated, borderRadius: R.sm, opacity: 0.4 }} />
            ))}
        </div>
    )
}

function Placeholder({ text }: { text: string }) {
    return (
        <div
            style={{
                padding: 18,
                textAlign: "center",
                color: C.textTertiary,
                fontSize: 12,
                background: C.bgElevated,
                borderRadius: R.md,
                border: `1px dashed ${C.borderStrong}`,
            }}
        >
            {text}
        </div>
    )
}

addPropertyControls(CorpDisposalsPanel, {
    defaultTicker: {
        type: ControlType.String,
        title: "기본 ticker (선택)",
        placeholder: "035420",
    },
    apiUrlOverride: {
        type: ControlType.String,
        title: "API URL (선택)",
        placeholder: API_BASE,
    },
})

// CorpAssetExplorerDashboard — ASSET PLAYS (부동산 숨은가치 종목 스크리너)
// ESTATE 폐기(2026-05-21) 후 VERITY 터미널로 re-home + reframe.
//   옛: 부동산 탐색기(25구 지도 + 지역별 Top 회사). → 제거.
//   신: 자산주 스크린 — 추적 종목 중 부동산 자산비중(P/A)·재평가·숨은가치 신호.
// Backend: /api/estate/corp-asset-discount (보존). RULE 6 정합 — metric only.
// ⚠ universe = corp snapshot(portfolio/recommendations 종목)만. 전 시장 X. N=0 가설.
// (구문: optional chaining/IIFE 회피 — Framer esbuild panic 가드, [[feedback_framer_esbuild_modern_syntax_panic]])

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

/* ◆ VERITY 터미널 토큰 (project color styles: /VERITY /Base /배경 /Border) ◆ */
const C = {
    bgPage: "#08070E", bgCard: "#0E0F11", bgElevated: "#16161D", bgInput: "#1C1C25",
    border: "#202026", borderStrong: "#2E2E37", borderHover: "#B5FF17",
    textPrimary: "#F2F3F5", textSecondary: "#9AA0AA", textTertiary: "#5E5E68",
    accent: "#B5FF17", accentSoft: "rgba(181,255,23,0.12)",
    gradeHOT: "#EF4444", gradeWARM: "#F59E0B", gradeNEUT: "#9AA0AA",
    statusPos: "#22C55E", statusNeg: "#EF4444",
}
const T = { cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 26,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }


/* ◆ TYPES ◆ */
interface CorpDiscountEntry {
    corp_code: string
    ticker: string
    company_name: string
    period: string
    total_property_krw: number
    property_to_asset_pct: number
    investment_property_krw: number | null
    revaluation_flag: boolean
    revaluation_amount_krw: number | null
    book_value_total_krw: number | null
    fair_value_total_krw: number | null
    hidden_value_krw: number | null
}

interface CorpDiscountResponse {
    filters: { min_ratio: number; revaluation_only: boolean; period: string; limit: number }
    watchlist: CorpDiscountEntry[]
    total_matches: number
}


/* ◆ HELPERS ◆ */
function fmtKRW(v: number | null | undefined): string {
    if (v === null || v === undefined) return "—"
    if (v >= 1e12) return `${(v / 1e12).toFixed(1)}조`
    if (v >= 1e8) return `${(v / 1e8).toFixed(0)}억`
    if (v >= 1e4) return `${(v / 1e4).toFixed(0)}만`
    return v.toLocaleString()
}

function fmtPct(v: number | null | undefined, digits: number): string {
    if (v === null || v === undefined || isNaN(v)) return "—"
    return `${v.toFixed(digits)}%`
}


/* ◆ ROW ◆ */
function AssetPlayRow(props: { rank: number; entry: CorpDiscountEntry }) {
    const rank = props.rank
    const entry = props.entry
    const ratioColor = entry.property_to_asset_pct >= 30 ? C.gradeHOT
        : entry.property_to_asset_pct >= 20 ? C.gradeWARM
        : C.gradeNEUT

    return (
        <div style={{
            display: "grid", gridTemplateColumns: "32px 1fr auto auto", alignItems: "center",
            gap: S.md, padding: S.md, backgroundColor: C.bgElevated,
            border: `1px solid ${C.border}`, borderRadius: R.sm,
            transition: `border-color ${X.fast}`, cursor: "default",
        }}
             onMouseEnter={(e) => { e.currentTarget.style.borderColor = C.borderStrong }}
             onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.border }}>
            <span style={{ fontSize: T.title, fontWeight: T.w_semi, color: C.accent, ...MONO }}>
                #{rank}
            </span>
            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                <span style={{
                    fontSize: T.body, fontWeight: T.w_semi, color: C.textPrimary,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>{entry.company_name}</span>
                <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO }}>
                    {entry.ticker} · {entry.period}
                    {entry.revaluation_flag && (
                        <span style={{ marginLeft: S.sm, color: C.statusPos, fontWeight: T.w_med }}>· 재평가↑</span>
                    )}
                </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                <span style={{ fontSize: T.sub, fontWeight: T.w_semi, color: C.textPrimary, ...MONO }}>
                    {fmtKRW(entry.total_property_krw)}
                </span>
                <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO }}>부동산자산</span>
            </div>
            <div style={{
                display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2,
                minWidth: 76, padding: `${S.xs}px ${S.sm}px`,
                backgroundColor: `${ratioColor}1A`, borderRadius: R.sm,
            }}>
                <span style={{ fontSize: T.sub, fontWeight: T.w_bold, color: ratioColor, ...MONO }}>
                    {fmtPct(entry.property_to_asset_pct, 1)}
                </span>
                <span style={{ fontSize: T.cap, color: ratioColor, opacity: 0.85, ...MONO }}>자산비중</span>
            </div>
        </div>
    )
}

function EmptyHint(props: { label: string }) {
    return (
        <div style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: S.xxl, color: C.textTertiary, fontSize: T.body, textAlign: "center",
        }}>{props.label}</div>
    )
}


/* ◆ MAIN ◆ */
function CorpAssetExplorerDashboard(props: { apiUrl?: string }) {
    const apiUrl = props.apiUrl || "https://project-yw131.vercel.app"
    const [minRatio, setMinRatio] = useState<number>(20)
    const [watchlist, setWatchlist] = useState<CorpDiscountEntry[]>([])
    const [loading, setLoading] = useState(false)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        fetch(`${apiUrl}/api/estate/corp-asset-discount?min_ratio=${minRatio}&limit=50`)
            .then(function (r) {
                if (!r.ok) throw new Error(String(r.status))
                return r.json()
            })
            .then(function (j: CorpDiscountResponse) {
                if (cancelled) return
                setWatchlist(j && j.watchlist ? j.watchlist : [])
                setLoading(false)
            })
            .catch(function () {
                if (cancelled) return
                setWatchlist([])
                setLoading(false)
            })
        return function () {
            cancelled = true
        }
    }, [minRatio, apiUrl])

    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: S.lg,
            padding: S.xl, backgroundColor: C.bgPage, minHeight: 480,
            fontFamily: FONT, color: C.textPrimary,
        }}>
            {/* Header */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: S.md, flexWrap: "wrap" }}>
                    <span style={{ fontSize: T.cap, letterSpacing: 1.4, color: C.accent, ...MONO }}>
                        ASSET&nbsp;PLAYS
                    </span>
                    <span style={{ fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary }}>
                        부동산 숨은가치 종목
                    </span>
                </div>
                <span style={{ fontSize: T.cap, color: C.textTertiary }}>
                    부동산 자산비중(P/A)·재평가 기반 자산주 스크린 · 가설(N=0) · 추적 종목 한정 (전 시장 X) · 매수권유 아님
                </span>
            </div>

            {/* Filter */}
            <div style={{
                display: "flex", alignItems: "center", gap: S.md, flexWrap: "wrap",
                padding: S.md, backgroundColor: C.bgCard, border: `1px solid ${C.border}`, borderRadius: R.md,
            }}>
                <span style={{ fontSize: T.cap, color: C.textSecondary, ...MONO }}>
                    자산비중 ≥ {minRatio}%
                </span>
                <input
                    type="range" min={5} max={50} step={5}
                    value={minRatio}
                    onChange={(e) => setMinRatio(parseInt(e.target.value, 10))}
                    style={{ flex: 1, minWidth: 160, accentColor: C.accent }}
                />
                <span style={{ fontSize: T.cap, color: C.textPrimary, ...MONO }}>
                    {watchlist.length}개사
                </span>
                {loading && <span style={{ fontSize: T.cap, color: C.accent, ...MONO }}>로딩…</span>}
            </div>

            {/* List */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                {!loading && watchlist.length === 0 && (
                    <EmptyHint label={`자산비중 ${minRatio}% 이상인 추적 종목이 없습니다.`} />
                )}
                {watchlist.map((entry, i) => (
                    <AssetPlayRow key={entry.corp_code} rank={i + 1} entry={entry} />
                ))}
            </div>
        </div>
    )
}

addPropertyControls(CorpAssetExplorerDashboard, {
    apiUrl: {
        type: ControlType.String,
        defaultValue: "https://project-yw131.vercel.app",
        description: "VERITY backend API base URL",
    },
})

export default CorpAssetExplorerDashboard

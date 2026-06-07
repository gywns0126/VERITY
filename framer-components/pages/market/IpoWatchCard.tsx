import { addPropertyControls, ControlType } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * IpoWatchCard — 상장 전(pre-IPO) 공모 pipeline watch
 *
 * "비상장 기대주 미리 선별" (PM 2026-06-07). 기존 EventCalendar/StockHeatmap 과 직교 —
 * 상장 전 공모 단계 종목만 다룸. source = DART 증권신고서(C001, corp_cls=E).
 *
 * ⚠️ watch list = 가설(N=0), 추천 아님 (RULE 7 + feedback_scope):
 *   상장 전은 가격 데이터가 없어 Brain 검증 trail 미적용. 상장 후 funnel 편입 시점부터
 *   검증 시작. → 상단 disclaimer 배너 상시 노출 의무.
 *
 * 데이터: ipo_watch.json (ipo_scout collector 산출, 주간 cron)
 *   watch[]: corp_name / stage(최초·정정·확정) / offering(공모가·청약일·모집총액) /
 *            doc_financials(매출 추이, 단위 미상) / dart_url
 *
 * 모던 심플: 외곽 1개 + 행 spacing / 청약 D-day mono / 매출 mini 막대(단위 무관 상대) /
 *            stage 색 discipline (확정=accent / 정정=warn / 최초=tertiary)
 */

/* ◆ DESIGN TOKENS ◆ */
const C = {
    bgPage: "#0a0a0a", bgCard: "#141414", bgElevated: "#1a1a1a",
    border: "rgba(255,255,255,0.06)", borderStrong: "rgba(255,255,255,0.10)",
    textPrimary: "#ffffff", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#7fffa0", accentSoft: "rgba(127,255,160,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800, lh_normal: 1.5,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }

/* ─────────── fetch + last-good 캐시 fallback (2026-06-06 표준 스니펫) ─────────── */
const FETCH_TIMEOUT_MS = 15_000
const CACHE_KEY = "verity_cache_ipowatch"

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}
function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    const timer = setTimeout(() => ac.abort(), FETCH_TIMEOUT_MS)
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal: ac.signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
        .finally(() => clearTimeout(timer))
}
function loadCache(key: string): { data: any; ts: number } | null {
    try {
        const raw = localStorage.getItem(key)
        if (!raw) return null
        const obj = JSON.parse(raw)
        return obj && obj.ts ? obj : null
    } catch (e) { return null }
}
function saveCache(key: string, data: any) {
    try { localStorage.setItem(key, JSON.stringify({ data: data, ts: Date.now() })) } catch (e) {}
}
function cacheAge(ts: number): string {
    const m = Math.round((Date.now() - ts) / 60000)
    if (m < 1) return "방금 전"
    if (m < 60) return `${m}분 전`
    const h = Math.round(m / 60)
    return h < 24 ? `${h}시간 전` : `${Math.round(h / 24)}일 전`
}

/* ─────────── helpers ─────────── */
function dotToDate(s?: string): string {
    // "2026.06.23" → "2026-06-23"
    if (!s) return ""
    return s.replace(/\./g, "-").replace(/-+$/, "")
}
function calcDDay(dateStr: string): number {
    if (!dateStr) return 9999
    const target = new Date(dateStr + "T00:00:00")
    if (isNaN(target.getTime())) return 9999
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    return Math.round((target.getTime() - today.getTime()) / 86400000)
}
function won(n?: number): string {
    if (n == null) return "—"
    return n.toLocaleString("ko-KR")
}
function eokFromWon(n?: number): string {
    // 원 → 억원 (모집총액 가독)
    if (n == null) return "—"
    const eok = n / 1e8
    if (eok >= 100) return `${Math.round(eok).toLocaleString("ko-KR")}억`
    return `${eok.toFixed(eok >= 10 ? 0 : 1)}억`
}

interface StageStyle { fg: string; label: string }
function stageStyle(stage?: string): StageStyle {
    if (stage === "확정") return { fg: C.accent, label: "확정" }       // 공모가·청약일 확정 (수요예측 후)
    if (stage === "정정") return { fg: C.warn, label: "정정" }
    return { fg: C.textTertiary, label: stage || "신고" }              // 최초
}

interface OfferingT {
    shares?: number
    price_planned?: number
    price_confirmed?: number
    total_planned?: number
    total_confirmed?: number
    subscribe_start?: string
    subscribe_end?: string
    payment_date?: string
}
interface DocFinT {
    available?: boolean
    unit?: string
    periods?: string[]
    revenue?: (number | null)[]
    operating_income?: (number | null)[]
    net_income?: (number | null)[]
}
interface WatchItem {
    corp_name: string
    corp_code?: string
    rcept_dt?: string
    report_nm?: string
    dart_url?: string
    stage?: string
    offering?: OfferingT
    doc_financials?: DocFinT
}

/* 청약 상태 + 정렬 키 */
function subscribeStatus(o?: OfferingT): { text: string; color: string; sortKey: number } {
    const start = dotToDate(o?.subscribe_start)
    const end = dotToDate(o?.subscribe_end)
    if (!start) return { text: "일정 미정", color: C.textTertiary, sortKey: 8000 }
    const dStart = calcDDay(start)
    const dEnd = end ? calcDDay(end) : dStart
    if (dStart > 0) return { text: `청약 D-${dStart}`, color: dStart <= 3 ? C.warn : C.textSecondary, sortKey: dStart }
    if (dEnd >= 0) return { text: "청약 진행중", color: C.accent, sortKey: -1 }
    return { text: "청약 마감", color: C.textTertiary, sortKey: 10000 - dEnd }
}

/* ═══════════════════════════ 메인 ═══════════════════════════ */
interface Props { dataUrl: string }

export default function IpoWatchCard(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [cacheTs, setCacheTs] = useState<number | null>(null)
    const [showAll, setShowAll] = useState(false)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal)
            .then((d) => { if (!ac.signal.aborted) { saveCache(CACHE_KEY, d); setData(d); setCacheTs(null) } })
            .catch(() => { const c = loadCache(CACHE_KEY); if (c) { setData(c.data); setCacheTs(c.ts) } })
        return () => ac.abort()
    }, [dataUrl])

    const items = useMemo<WatchItem[]>(() => {
        const w: WatchItem[] = (data && Array.isArray(data.watch)) ? data.watch : []
        return [...w].sort((a, b) => subscribeStatus(a.offering).sortKey - subscribeStatus(b.offering).sortKey)
    }, [data])

    const DEFAULT_VISIBLE = 5
    const visible = showAll ? items : items.slice(0, DEFAULT_VISIBLE)

    if (!data) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>IPO 파이프라인 로딩 중…</span>
                </div>
            </div>
        )
    }

    return (
        <div style={shell}>
            {cacheTs != null && (
                <div style={{ fontSize: 11, color: C.warn, fontFamily: FONT, marginBottom: 6 }}>
                    ⚠ 오프라인 · {cacheAge(cacheTs)} 데이터
                </div>
            )}

            {/* Header */}
            <div style={headerRow}>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={titleStyle}>IPO Watch</span>
                    <span style={metaStyle}>상장 전 공모 pipeline · {items.length}건 · DART 증권신고서</span>
                </div>
            </div>

            {/* RULE 7 disclaimer 배너 (상시) */}
            <div style={disclaimerBox}>
                관찰 watch list · <b style={{ color: C.textSecondary }}>가설 (N=0)</b> · 추천 아님 — 상장 후 검증 시작
            </div>

            <div style={hr} />

            {items.length === 0 ? (
                <div style={emptyBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>현재 공모 pipeline 종목 없음</span>
                </div>
            ) : (
                <div style={{ display: "flex", flexDirection: "column" }}>
                    {visible.map((it, i) => <IpoRow key={`${it.corp_code || it.corp_name}-${i}`} item={it} />)}
                    {items.length > DEFAULT_VISIBLE && (
                        <button onClick={() => setShowAll((v) => !v)} style={moreBtn}>
                            {showAll ? "▾ 접기" : `▸ 더보기 (+${items.length - DEFAULT_VISIBLE})`}
                        </button>
                    )}
                </div>
            )}
        </div>
    )
}

/* ─────────── 행 ─────────── */
function IpoRow({ item }: { item: WatchItem }) {
    const o = item.offering || {}
    const st = stageStyle(item.stage)
    const sub = subscribeStatus(o)
    const price = o.price_confirmed ?? o.price_planned
    const priceConfirmed = o.price_confirmed != null
    const total = o.total_confirmed ?? o.total_planned

    return (
        <div style={rowStyle}>
            {/* 청약 D-day */}
            <div style={dDayBlock}>
                <span style={{ ...MONO, color: sub.color, fontSize: T.body, fontWeight: T.w_bold }}>{sub.text}</span>
                {o.subscribe_start && (
                    <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                        {dotToDate(o.subscribe_start).slice(5)}
                    </span>
                )}
            </div>

            {/* 본문 */}
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: S.sm, flexWrap: "wrap" }}>
                    <span style={{ ...stageBadge, color: st.fg, borderColor: st.fg + "40" }}>{st.label}</span>
                    {item.dart_url ? (
                        <a href={item.dart_url} target="_blank" rel="noopener noreferrer" style={nameLink}>
                            {item.corp_name}
                        </a>
                    ) : (
                        <span style={nameStyle}>{item.corp_name}</span>
                    )}
                </div>

                {/* 공모 조건 */}
                <div style={{ display: "flex", gap: S.lg, flexWrap: "wrap" }}>
                    <Metric label="공모가" value={price != null ? `${won(price)}원` : "미상"}
                        tag={price != null ? (priceConfirmed ? "확정" : "예정") : undefined}
                        tagColor={priceConfirmed ? C.accent : C.textTertiary} />
                    <Metric label="모집총액" value={total != null ? eokFromWon(total) : "—"} />
                    {o.shares != null && <Metric label="공모주식" value={`${won(o.shares)}주`} />}
                </div>

                {/* 매출 mini 막대 (단위 미상 → 상대 높이만, picture-book) */}
                <RevenueSpark fin={item.doc_financials} />
            </div>
        </div>
    )
}

function Metric({ label, value, tag, tagColor }: { label: string; value: string; tag?: string; tagColor?: string }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <span style={{ color: C.textTertiary, fontSize: 10, letterSpacing: 0.5, textTransform: "uppercase" }}>{label}</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <span style={{ ...MONO, color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>{value}</span>
                {tag && <span style={{ color: tagColor, fontSize: 9, fontWeight: T.w_bold, letterSpacing: 0.5 }}>{tag}</span>}
            </span>
        </div>
    )
}

/* 매출 추이 — 단위 미상이라 절대값 대신 상대 막대 + YoY 증감률(단위 무관) */
function RevenueSpark({ fin }: { fin?: DocFinT }) {
    if (!fin || !fin.available) return null
    const rev = (fin.revenue || []).filter((v): v is number => typeof v === "number" && v > 0)
    if (rev.length < 2) return null
    const max = Math.max(...rev)
    const yoy = rev[0] > 0 ? ((rev[rev.length - 1] - rev[0]) / rev[0]) * 100 : null
    return (
        <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
            <span style={{ color: C.textTertiary, fontSize: 10, letterSpacing: 0.5, textTransform: "uppercase" }}>매출 추이</span>
            <span style={{ display: "inline-flex", alignItems: "flex-end", gap: 2, height: 16 }}>
                {rev.map((v, i) => (
                    <span key={i} style={{
                        width: 5, height: Math.max(2, Math.round((v / max) * 16)),
                        background: i === rev.length - 1 ? C.accent : C.borderStrong, borderRadius: 1,
                    }} />
                ))}
            </span>
            {yoy != null && (
                <span style={{ ...MONO, fontSize: T.cap, fontWeight: T.w_semi, color: yoy >= 0 ? C.success : C.danger }}>
                    {yoy >= 0 ? "+" : ""}{yoy.toFixed(0)}%
                </span>
            )}
            <span style={{ color: C.textDisabled, fontSize: 9 }}>
                {fin.unit && fin.unit !== "미상" ? `단위 ${fin.unit}` : "단위 DART"}
            </span>
        </div>
    )
}

/* ─────────── 스타일 ─────────── */
const shell: CSSProperties = {
    width: "100%", boxSizing: "border-box",
    fontFamily: FONT, color: C.textPrimary, background: C.bgPage,
    borderRadius: 8, padding: S.xxl, display: "flex", flexDirection: "column",
}
const headerRow: CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: S.md, flexWrap: "wrap" }
const titleStyle: CSSProperties = { fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary, letterSpacing: -0.5, lineHeight: 1.2 }
const metaStyle: CSSProperties = { fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med }
const disclaimerBox: CSSProperties = {
    marginTop: S.md, padding: `${S.sm}px ${S.md}px`, borderRadius: R.sm,
    background: C.bgElevated, border: `1px solid ${C.border}`,
    color: C.textTertiary, fontSize: T.cap, fontFamily: FONT, lineHeight: T.lh_normal,
}
const hr: CSSProperties = { height: 1, background: C.border, margin: `${S.md}px 0 0` }
const rowStyle: CSSProperties = { display: "flex", gap: S.md, alignItems: "flex-start", padding: `${S.lg}px 0`, borderBottom: `1px solid ${C.border}` }
const dDayBlock: CSSProperties = { display: "flex", flexDirection: "column", alignItems: "center", minWidth: 76, flexShrink: 0 }
const stageBadge: CSSProperties = {
    background: "transparent", fontSize: 10, fontWeight: T.w_bold, letterSpacing: 1,
    padding: "2px 7px", borderRadius: R.sm, border: "1px solid", fontFamily: FONT,
}
const nameStyle: CSSProperties = { color: C.textPrimary, fontSize: T.sub, fontWeight: T.w_bold }
const nameLink: CSSProperties = { ...nameStyle, textDecoration: "none", borderBottom: `1px dashed ${C.borderStrong}` }
const moreBtn: CSSProperties = {
    border: "none", background: "transparent", color: C.textSecondary,
    padding: `${S.sm}px ${S.md}px`, borderRadius: R.md, fontSize: T.cap, fontWeight: T.w_semi,
    fontFamily: FONT, cursor: "pointer", marginTop: S.md, alignSelf: "center", transition: X.base,
}
const loadingBox: CSSProperties = { minHeight: 200, display: "flex", alignItems: "center", justifyContent: "center" }
const emptyBox: CSSProperties = { padding: `${S.xxl}px 0`, textAlign: "center" }

/* ─────────── Framer Property Controls ─────────── */
IpoWatchCard.defaultProps = {
    dataUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/ipo_watch.json",
}
addPropertyControls(IpoWatchCard, {
    dataUrl: {
        type: ControlType.String,
        title: "IPO Watch URL",
        defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/ipo_watch.json",
    },
})

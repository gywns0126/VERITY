// AlertDashboard — 알림 피드 페이지
// VERITY ESTATE 페이지급 컴포넌트.
// 신규 작성 (Tag 인라인 + 필터 + 카드 리스트 + 마킹 워크플로우).

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useMemo } from "react"

/* ◆ DESIGN TOKENS START ◆ */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B8864D", accentHover: "#D4A063", accentSoft: "rgba(184,134,77,0.12)",
    catGEI: "#EF4444", catCatalyst: "#F59E0B", catRegulation: "#9B59B6", catAnomaly: "#5BA9FF",
    sevHigh: "#EF4444", sevMid: "#F59E0B", sevLow: "#A8ABB2",
    statusPos: "#22C55E", statusNeut: "#A8ABB2", statusNeg: "#EF4444",
    info: "#5BA9FF",
}
const T = { cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 6, md: 10, lg: 14 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ◆ TYPES ◆ */
type CategoryId = "gei" | "catalyst" | "regulation" | "anomaly"
type Severity = "high" | "mid" | "low"
type AlertStatus = "new" | "read" | "hidden"

interface Alert {
    id: string
    category: CategoryId
    severity: Severity
    title: string
    body: string
    gu?: string
    timestamp: string  // ISO
    status: AlertStatus
}

interface FilterState {
    categories: Set<CategoryId>
    severities: Set<Severity>
    showHidden: boolean
    showRead: boolean
}


/* ◆ MAPS ◆ */
const CAT_LABEL: Record<CategoryId, string> = {
    gei: "GEI", catalyst: "Catalyst", regulation: "Regulation", anomaly: "Anomaly",
}
const CAT_ICON: Record<CategoryId, string> = {
    gei: "🔴", catalyst: "🟡", regulation: "🟣", anomaly: "🔵",
}
const CAT_COLOR: Record<CategoryId, string> = {
    gei: C.catGEI, catalyst: C.catCatalyst, regulation: C.catRegulation, anomaly: C.catAnomaly,
}
const SEV_LABEL: Record<Severity, string> = { high: "높음", mid: "중간", low: "낮음" }
const SEV_COLOR: Record<Severity, string> = { high: C.sevHigh, mid: C.sevMid, low: C.sevLow }


/* ◆ MOCK DATA ◆ */
const MOCK_ALERTS: Alert[] = [
    { id: "a1", category: "gei", severity: "high", title: "강남구 GEI Stage 4 진입",
      body: "매물 회전율 급증 + 임차료 상승률 12% — 과열 구간 가능성", gu: "강남구",
      timestamp: "2026-04-25T08:30:00Z", status: "new" },
    { id: "a2", category: "regulation", severity: "high", title: "재건축 안전진단 강화 시행 임박",
      body: "국토부 발표 — 4월 30일부터 D등급 이상 정밀안전진단 의무화",
      timestamp: "2026-04-25T07:10:00Z", status: "new" },
    { id: "a3", category: "catalyst", severity: "mid", title: "용산구 신분당선 연장 확정",
      body: "예타 통과 — 2030 개통 예정. V·S 점수 +5 예상", gu: "용산구",
      timestamp: "2026-04-24T18:45:00Z", status: "new" },
    { id: "a4", category: "anomaly", severity: "mid", title: "마포구 거래량 이상 패턴",
      body: "주간 거래량 평균 대비 +180%. 단발 이벤트 또는 정책 변동 가능성", gu: "마포구",
      timestamp: "2026-04-24T15:20:00Z", status: "read" },
    { id: "a5", category: "gei", severity: "mid", title: "송파구 GEI Stage 3 유지",
      body: "3주 연속 Stage 3. 진정 신호는 아직 없음", gu: "송파구",
      timestamp: "2026-04-23T11:05:00Z", status: "read" },
    { id: "a6", category: "catalyst", severity: "low", title: "성동구 도시계획안 공람 시작",
      body: "5월 12일까지. 주민 의견 수렴 단계", gu: "성동구",
      timestamp: "2026-04-22T09:00:00Z", status: "read" },
]


/* ◆ DATA FETCH ◆ */
// /api/estate/alerts (vercel-api). 인증 토큰은 window.__VERITY_TOKEN__ 또는 localStorage 에서.
async function fetchAlerts(apiUrl: string, signal?: AbortSignal): Promise<Alert[]> {
    if (!apiUrl) return MOCK_ALERTS
    try {
        const token = (typeof window !== "undefined" &&
            ((window as any).__VERITY_TOKEN__ || localStorage.getItem("verity_access_token"))) || ""
        if (!token) return MOCK_ALERTS
        const res = await fetch(`${apiUrl.replace(/\/$/, "")}/api/estate/alerts`, {
            signal, headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) throw new Error()
        const j = await res.json()
        // 백엔드 응답: { alerts: [...] }
        const arr: any[] = Array.isArray(j?.alerts) ? j.alerts : []
        if (!arr.length) return MOCK_ALERTS
        // 백엔드 필드 → 프론트 Alert 매핑 (occurred_at → timestamp 등)
        return arr.map((a) => ({
            id: a.id,
            category: a.category,
            severity: a.severity,
            title: a.title,
            body: a.body ?? "",
            gu: a.gu ?? undefined,
            timestamp: a.occurred_at ?? a.timestamp,
            status: a.status ?? "new",
        }))
    } catch {
        return MOCK_ALERTS
    }
}


/* ◆ UTIL ◆ */
function formatRelTime(iso: string): string {
    try {
        const t = new Date(iso).getTime()
        const now = Date.now()
        const min = Math.floor((now - t) / 60000)
        if (min < 1) return "방금"
        if (min < 60) return `${min}분 전`
        if (min < 60 * 24) return `${Math.floor(min / 60)}시간 전`
        return `${Math.floor(min / 60 / 24)}일 전`
    } catch { return iso }
}


/* ◆ INTERNAL: Tag (category/severity 인라인) ◆ */
function CategoryTag({ category }: { category: CategoryId }) {
    const c = CAT_COLOR[category]
    return (
        <span style={{
            display: "inline-flex", alignItems: "center", gap: S.xs,
            padding: "2px 8px", borderRadius: R.sm,
            background: c + "1A", color: c,
            fontSize: T.cap, fontWeight: T.w_med, fontFamily: FONT,
            lineHeight: 1, whiteSpace: "nowrap",
        }}>
            <span>{CAT_ICON[category]}</span>{CAT_LABEL[category]}
        </span>
    )
}
function SeverityTag({ severity }: { severity: Severity }) {
    const c = SEV_COLOR[severity]
    return (
        <span style={{
            display: "inline-flex", alignItems: "center",
            padding: "2px 8px", borderRadius: R.sm,
            background: c + "1A", color: c,
            fontSize: T.cap, fontWeight: T.w_med, fontFamily: FONT,
            lineHeight: 1,
        }}>{SEV_LABEL[severity]}</span>
    )
}


/* ◆ INTERNAL: FilterBar ◆ */
function FilterBar({ filters, onChange, totalCount, visibleCount, onMarkAllRead }: {
    filters: FilterState
    onChange: (next: FilterState) => void
    totalCount: number
    visibleCount: number
    onMarkAllRead: () => void
}) {
    const cats: CategoryId[] = ["gei", "catalyst", "regulation", "anomaly"]
    const sevs: Severity[] = ["high", "mid", "low"]

    const toggleCat = (c: CategoryId) => {
        const next = new Set(filters.categories)
        if (next.has(c)) next.delete(c); else next.add(c)
        onChange({ ...filters, categories: next })
    }
    const toggleSev = (s: Severity) => {
        const next = new Set(filters.severities)
        if (next.has(s)) next.delete(s); else next.add(s)
        onChange({ ...filters, severities: next })
    }

    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: S.sm,
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
        }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: S.md }}>
                    <span style={{ fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary }}>알림</span>
                    <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO }}>{visibleCount}/{totalCount}</span>
                </div>
                <button
                    onClick={onMarkAllRead}
                    style={{
                        padding: `${S.xs}px ${S.sm}px`, background: "transparent", color: C.textSecondary,
                        border: `1px solid ${C.border}`, borderRadius: R.sm,
                        fontSize: T.cap, fontFamily: FONT, cursor: "pointer",
                    }}
                >모두 읽음</button>
            </div>

            <div style={{ display: "flex", gap: S.xs, flexWrap: "wrap", alignItems: "center" }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary, marginRight: S.sm }}>카테고리</span>
                {cats.map((c) => (
                    <FilterChip key={c} active={filters.categories.has(c)} onClick={() => toggleCat(c)} color={CAT_COLOR[c]}>
                        {CAT_ICON[c]} {CAT_LABEL[c]}
                    </FilterChip>
                ))}
            </div>

            <div style={{ display: "flex", gap: S.xs, flexWrap: "wrap", alignItems: "center" }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary, marginRight: S.sm }}>심각도</span>
                {sevs.map((s) => (
                    <FilterChip key={s} active={filters.severities.has(s)} onClick={() => toggleSev(s)} color={SEV_COLOR[s]}>
                        {SEV_LABEL[s]}
                    </FilterChip>
                ))}
                <span style={{ flex: 1 }} />
                <FilterChip active={filters.showRead} onClick={() => onChange({ ...filters, showRead: !filters.showRead })}>
                    읽은 알림
                </FilterChip>
                <FilterChip active={filters.showHidden} onClick={() => onChange({ ...filters, showHidden: !filters.showHidden })}>
                    숨김 알림
                </FilterChip>
            </div>
        </div>
    )
}

function FilterChip({ active, onClick, color, children }: {
    active: boolean
    onClick: () => void
    color?: string
    children: React.ReactNode
}) {
    const c = color ?? C.accent
    return (
        <button
            onClick={onClick}
            style={{
                padding: `${S.xs}px ${S.sm}px`,
                background: active ? c + "1A" : "transparent",
                color: active ? c : C.textSecondary,
                border: `1px solid ${active ? c : C.border}`,
                borderRadius: R.sm,
                fontSize: T.cap, fontWeight: active ? T.w_semi : T.w_reg,
                fontFamily: FONT, cursor: "pointer",
                transition: X.fast, whiteSpace: "nowrap",
            }}
        >{children}</button>
    )
}


/* ◆ INTERNAL: AlertCard ◆ */
function AlertCard({ alert, onRead, onHide, onUnhide }: {
    alert: Alert
    onRead: (id: string) => void
    onHide: (id: string) => void
    onUnhide: (id: string) => void
}) {
    const isNew = alert.status === "new"
    const isHidden = alert.status === "hidden"
    const catColor = CAT_COLOR[alert.category]

    return (
        <article style={{
            display: "flex", flexDirection: "column", gap: S.sm,
            padding: S.md, backgroundColor: C.bgCard,
            border: `1px solid ${isNew ? catColor : C.border}`,
            borderLeft: `3px solid ${catColor}`,
            borderRadius: R.md,
            opacity: isHidden ? 0.5 : 1,
            transition: X.base,
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: S.sm, flexWrap: "wrap" }}>
                <CategoryTag category={alert.category} />
                <SeverityTag severity={alert.severity} />
                {alert.gu && (
                    <span style={{ fontSize: T.cap, color: C.textTertiary }}>· {alert.gu}</span>
                )}
                <span style={{ flex: 1 }} />
                {isNew && (
                    <span style={{
                        padding: "2px 6px", borderRadius: R.sm,
                        background: C.accent, color: C.bgPage,
                        fontSize: 10, fontWeight: T.w_bold, letterSpacing: 0.5,
                    }}>NEW</span>
                )}
                <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO }}>{formatRelTime(alert.timestamp)}</span>
            </div>

            <h3 style={{
                margin: 0, fontSize: T.sub,
                fontWeight: isNew ? T.w_bold : T.w_semi,
                color: C.textPrimary, lineHeight: 1.4,
            }}>{alert.title}</h3>

            <p style={{
                margin: 0, fontSize: T.body, color: C.textSecondary,
                lineHeight: 1.5,
            }}>{alert.body}</p>

            <div style={{ display: "flex", gap: S.sm, marginTop: S.xs }}>
                {isNew && (
                    <ActionBtn onClick={() => onRead(alert.id)}>읽음 표시</ActionBtn>
                )}
                {isHidden ? (
                    <ActionBtn onClick={() => onUnhide(alert.id)}>숨김 해제</ActionBtn>
                ) : (
                    <ActionBtn onClick={() => onHide(alert.id)} subtle>숨기기</ActionBtn>
                )}
            </div>
        </article>
    )
}

function ActionBtn({ children, onClick, subtle }: { children: React.ReactNode; onClick: () => void; subtle?: boolean }) {
    return (
        <button
            onClick={onClick}
            style={{
                padding: `${S.xs}px ${S.sm}px`,
                background: subtle ? "transparent" : C.bgElevated,
                color: subtle ? C.textTertiary : C.textPrimary,
                border: `1px solid ${C.border}`, borderRadius: R.sm,
                fontSize: T.cap, fontWeight: T.w_med, fontFamily: FONT,
                cursor: "pointer", transition: X.fast,
            }}
        >{children}</button>
    )
}


/* ◆ MAIN ◆ */
interface Props {
    apiUrl: string
}

const DEFAULT_FILTERS = (): FilterState => ({
    categories: new Set<CategoryId>(["gei", "catalyst", "regulation", "anomaly"]),
    severities: new Set<Severity>(["high", "mid", "low"]),
    showHidden: false,
    showRead: true,
})

function AlertDashboard({ apiUrl = "" }: Props) {
    const [alerts, setAlerts] = useState<Alert[]>(MOCK_ALERTS)
    const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS())
    const [loading, setLoading] = useState(false)

    useEffect(() => {
        const ac = new AbortController()
        setLoading(true)
        fetchAlerts(apiUrl, ac.signal)
            .then((a) => { setAlerts(a); setLoading(false) })
            .catch(() => setLoading(false))
        return () => ac.abort()
    }, [apiUrl])

    const filtered = useMemo(() => {
        return alerts.filter((a) => {
            if (!filters.categories.has(a.category)) return false
            if (!filters.severities.has(a.severity)) return false
            if (a.status === "hidden" && !filters.showHidden) return false
            if (a.status === "read" && !filters.showRead) return false
            return true
        })
    }, [alerts, filters])

    const handleRead = (id: string) => {
        setAlerts((as) => as.map((a) => (a.id === id ? { ...a, status: "read" } : a)))
    }
    const handleHide = (id: string) => {
        setAlerts((as) => as.map((a) => (a.id === id ? { ...a, status: "hidden" } : a)))
    }
    const handleUnhide = (id: string) => {
        setAlerts((as) => as.map((a) => (a.id === id ? { ...a, status: "read" } : a)))
    }
    const handleMarkAllRead = () => {
        setAlerts((as) => as.map((a) => (a.status === "new" ? { ...a, status: "read" } : a)))
    }

    return (
        <div style={{
            width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: S.md, padding: S.md,
            backgroundColor: C.bgPage, fontFamily: FONT, color: C.textPrimary,
            boxSizing: "border-box", minWidth: 640, minHeight: 480, overflowY: "auto",
        }}>
            <FilterBar
                filters={filters} onChange={setFilters}
                totalCount={alerts.length} visibleCount={filtered.length}
                onMarkAllRead={handleMarkAllRead}
            />

            {loading && <span style={{ fontSize: T.cap, color: C.info, ...MONO }}>· 로딩 중</span>}

            {filtered.length === 0 ? (
                <div style={{
                    padding: S.xxl, textAlign: "center", color: C.textTertiary, fontSize: T.body,
                    border: `1px dashed ${C.border}`, borderRadius: R.md,
                }}>
                    조건에 맞는 알림이 없습니다.
                </div>
            ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                    {filtered.map((a) => (
                        <AlertCard key={a.id} alert={a}
                            onRead={handleRead} onHide={handleHide} onUnhide={handleUnhide}
                        />
                    ))}
                </div>
            )}
        </div>
    )
}

addPropertyControls(AlertDashboard, {
    apiUrl: { type: ControlType.String, defaultValue: "", description: "Alerts API base URL. 비우면 mock 데이터." },
})

export default AlertDashboard

import { addPropertyControls, ControlType } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * AlertHub — VERITY 통합 알림 (Step 3, Alert 2→1)
 *
 * 출처:
 *   - AlertBriefing.tsx (507줄) — banner + 펼침에 다가오는 이벤트 (D-7)
 *   - AlertDashboard.tsx (368줄) — 알림 list + filter chip
 *
 * 통합 후 책임:
 *   - 평소 (default): banner (톤 + 헤드라인 + 카운트 + 지금 해야 할 것)
 *   - 펼침 (expand): 알림 list + filter chip (전체/긴급/주의/참고)
 *
 * 제거 (중복):
 *   - "다가오는 이벤트 (D-7)" — EventCalendar 가 담당. hint 한 줄 표시
 *
 * 모던 심플 6원칙:
 *   1. No card-in-card — 외곽 1개 + 섹션 spacing
 *   2. Flat hierarchy — banner cap + headline + filter chip + list
 *   3. Mono numerics — 카운트 / 시각
 *   4. Expand on tap — banner 클릭 시 알림 list 펼침
 *   5. Color discipline — level = success/warn/danger/info 토큰만
 *   6. Hover tooltip — alert level 라벨 (긴급/주의/참고) 의미 명확화
 *
 * Emoji 0개, 자체 색 0개. 모두 토큰.
 *
 * feedback_no_hardcode_position 적용 — inline 렌더링.
 *
 * Market filter prop (KR/US): 시장별 알림 분리 (기존 분류 로직 유지).
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF", watch: "#FFD600",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    success: "0 0 6px rgba(34,197,94,0.30)",
    warn: "0 0 6px rgba(245,158,11,0.30)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
    info: "0 0 6px rgba(91,169,255,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ─────────── Portfolio fetch ─────────── */
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000
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
    const timer = setTimeout(() => ac.abort(), PORTFOLIO_FETCH_TIMEOUT_MS)
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal: ac.signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
        .finally(() => clearTimeout(timer))
}


/* ─────────── KR/US 분류 (기존 로직 그대로) ─────────── */
const US_ALERT_KW = ["미국", "연준", "Fed", "NASDAQ", "NYSE", "S&P", "다우", "국채", "VIX", "달러"]
const KR_ALERT_KW = ["한국", "국내", "코스피", "코스닥", "KRX", "원달러", "원화", "한국은행", "기준금리"]

function _isUSTicker(ticker: string): boolean {
    return /^[A-Z]{1,5}$/.test(String(ticker || "").trim())
}
function _isUSStock(s: any): boolean {
    return s?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(s?.market || "") || _isUSTicker(s?.ticker || "")
}
function _toText(v: any): string {
    if (v == null) return ""
    if (Array.isArray(v)) return v.map(_toText).join(" ")
    return String(v)
}
function _containsAny(text: string, kws: string[]): boolean {
    const t = String(text || "").toLowerCase()
    return kws.some((kw) => t.includes(kw.toLowerCase()))
}
function _containsToken(text: string, tokens: Set<string>): boolean {
    const t = String(text || "").toLowerCase()
    for (const token of tokens) if (token && t.includes(token)) return true
    return false
}
function _isUSAlert(a: any, usTokens: Set<string>, krTokens: Set<string>): boolean {
    const cat = String(a?.category || "").toLowerCase()
    const ticker = String(a?.ticker || "").trim()
    const txt = `${_toText(a?.message)} ${_toText(a?.action)} ${_toText(a?.ticker)}`
    if (ticker) return _isUSTicker(ticker)
    if (_containsToken(txt, usTokens)) return true
    if (_containsToken(txt, krTokens)) return false
    if (_containsAny(txt, US_ALERT_KW)) return true
    if (_containsAny(txt, KR_ALERT_KW)) return false
    if (["holding", "earnings", "opportunity", "price_target", "value_chain"].includes(cat)) return false
    return false
}


/* ─────────── Level meta ─────────── */
type AlertLevel = "CRITICAL" | "WARNING" | "INFO"
type FilterType = "all" | AlertLevel

const LEVEL_META: Record<AlertLevel, { color: string; glow: string; label: string }> = {
    CRITICAL: { color: C.danger, glow: G.danger, label: "긴급" },
    WARNING: { color: C.warn, glow: G.warn, label: "주의" },
    INFO: { color: C.info, glow: G.info, label: "참고" },
}

const CAT_LABELS: Record<string, string> = {
    macro: "매크로",
    macro_event: "매크로 이벤트",
    holding: "보유",
    earnings: "실적",
    opportunity: "기회",
    news: "뉴스",
    event: "이벤트",
    strategy: "전략",
    ai_consensus: "AI합의",
    price_target: "목표가",
    value_chain: "밸류체인",
}


/* ─────────── 톤 산출 (헤드라인 banner) ─────────── */
type Tone = "urgent" | "cautious" | "neutral"

function computeTone(counts: { critical: number; warning: number; info: number }): { key: Tone; color: string; glow: string; label: string } {
    if (counts.critical > 0) return { key: "urgent", color: C.danger, glow: G.danger, label: "긴급" }
    if (counts.warning > 0) return { key: "cautious", color: C.warn, glow: G.warn, label: "주의" }
    return { key: "neutral", color: C.textTertiary, glow: "none", label: "정상" }
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

interface Props {
    dataUrl: string
    market: "kr" | "us"
    maxAlerts: number
    /** 펼침 default 상태 (펼친 채 시작) */
    defaultExpanded: boolean
}

export default function AlertHub(props: Props) {
    const { dataUrl, maxAlerts, defaultExpanded } = props
    const isUS = props.market === "us"
    const [data, setData] = useState<any>(null)
    const [expanded, setExpanded] = useState(!!defaultExpanded)
    const [filter, setFilter] = useState<FilterType>("all")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then((d) => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    /* alerts 분류 + 시장 필터 */
    const { alerts, counts, aiConsensusCount, headline, actions, updatedAt } = useMemo(() => {
        if (!data) return { alerts: [], counts: { critical: 0, warning: 0, info: 0 }, aiConsensusCount: 0, headline: "", actions: [] as string[], updatedAt: "" }

        const briefing = data.briefing || {}
        const fromBriefing = briefing.alerts
        const fromRoot = data.alerts
        const rawAll: any[] = Array.isArray(fromBriefing) ? fromBriefing : Array.isArray(fromRoot) ? fromRoot : []

        const recs: any[] = data.recommendations || []
        const usTokens = new Set<string>()
        const krTokens = new Set<string>()
        for (const r of recs) {
            const ticker = String(r?.ticker || "").trim().toLowerCase()
            const name = String(r?.name || "").trim().toLowerCase()
            const target = _isUSStock(r) ? usTokens : krTokens
            if (ticker.length >= 1) target.add(ticker)
            if (name.length >= 2) target.add(name)
        }
        const filtered = rawAll.filter((a: any) => (isUS ? _isUSAlert(a, usTokens, krTokens) : !_isUSAlert(a, usTokens, krTokens)))
        const cap = Math.min(30, Math.max(1, Number(maxAlerts) || 15))
        const capped = filtered.slice(0, cap)

        const c = {
            critical: capped.filter((a: any) => a?.level === "CRITICAL").length,
            warning: capped.filter((a: any) => a?.level === "WARNING").length,
            info: capped.filter((a: any) => a?.level === "INFO").length,
        }
        const aiConsensus = capped.filter((a: any) => (a?.category || "").toLowerCase() === "ai_consensus").length
        const head = capped[0]?.message || briefing.headline || "분석 대기 중"
        const acts: string[] = capped
            .map((a: any) => String(a?.action || "").trim())
            .filter(Boolean)
            .slice(0, 3)
        return {
            alerts: capped,
            counts: c,
            aiConsensusCount: aiConsensus,
            headline: head,
            actions: acts,
            updatedAt: data.updated_at || "",
        }
    }, [data, isUS, maxAlerts])

    const tone = computeTone(counts)
    const totalAlerts = alerts.length
    const filteredAlerts = filter === "all" ? alerts : alerts.filter((a: any) => a.level === filter)

    const updatedLabel = updatedAt
        ? new Date(updatedAt).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
        : ""

    /* 로딩 */
    if (!data) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>알림 로딩 중…</span>
                </div>
            </div>
        )
    }

    return (
        <div style={shell}>
            {/* ── Banner (항상 보임, 클릭 시 펼침 토글) ── */}
            <div
                style={{
                    ...banner,
                    borderLeft: `3px solid ${tone.color}`,
                    cursor: "pointer",
                }}
                onClick={() => setExpanded((v) => !v)}
            >
                {/* tone label + 화살표 */}
                <div style={bannerTop}>
                    <div style={bannerLabelRow}>
                        <span
                            style={{
                                width: 8, height: 8, borderRadius: "50%",
                                background: tone.color, boxShadow: tone.glow,
                            }}
                        />
                        <span
                            style={{
                                color: tone.color, fontSize: T.cap, fontWeight: T.w_bold,
                                letterSpacing: "0.1em", textTransform: "uppercase",
                            }}
                        >
                            VERITY · {tone.label}
                        </span>
                    </div>
                    <span style={{ color: C.textTertiary, fontSize: T.cap }}>{expanded ? "▾ 접기" : "▸ 펼침"}</span>
                </div>

                {/* 헤드라인 메시지 */}
                <div style={headlineMsg}>{headline}</div>

                {/* 카운트 배지 + 갱신 시각 */}
                <div style={badgeRow}>
                    {counts.critical > 0 && (
                        <CountBadge label="긴급" count={counts.critical} color={C.danger} />
                    )}
                    {counts.warning > 0 && (
                        <CountBadge label="주의" count={counts.warning} color={C.warn} />
                    )}
                    {counts.info > 0 && (
                        <CountBadge label="참고" count={counts.info} color={C.info} />
                    )}
                    {aiConsensusCount > 0 && (
                        <CountBadge label="AI합의" count={aiConsensusCount} color={C.accent} />
                    )}
                    {updatedLabel && (
                        <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap, marginLeft: "auto" }}>
                            {updatedLabel}
                        </span>
                    )}
                </div>

                {/* 지금 해야 할 것 */}
                {actions.length > 0 && (
                    <div style={actionBox}>
                        <span style={actionTitle}>지금 해야 할 것</span>
                        <div style={{ display: "flex", flexDirection: "column", gap: S.xs, marginTop: S.xs }}>
                            {actions.map((a, i) => (
                                <div key={i} style={actionItem}>→ {a}</div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* ── Expand panel ── */}
            {expanded && (
                <>
                    <div style={hr} />

                    {/* Filter chip row */}
                    <div style={filterRow}>
                        <FilterChip label="전체" active={filter === "all"} count={totalAlerts} onClick={() => setFilter("all")} color={C.textPrimary} />
                        <FilterChip label="긴급" active={filter === "CRITICAL"} count={counts.critical} onClick={() => setFilter("CRITICAL")} color={C.danger} />
                        <FilterChip label="주의" active={filter === "WARNING"} count={counts.warning} onClick={() => setFilter("WARNING")} color={C.warn} />
                        <FilterChip label="참고" active={filter === "INFO"} count={counts.info} onClick={() => setFilter("INFO")} color={C.info} />
                    </div>

                    {/* Alert list */}
                    <div style={listWrap}>
                        {filteredAlerts.length === 0 && (
                            <div style={emptyBox}>
                                <span style={{ color: C.textTertiary, fontSize: T.body }}>
                                    {totalAlerts === 0 ? "알림 없음" : "해당 레벨 알림 없음"}
                                </span>
                            </div>
                        )}
                        {filteredAlerts.map((a: any, i: number) => (
                            <AlertCard key={i} alert={a} />
                        ))}
                    </div>

                    {/* EventCalendar 참조 hint */}
                    <div style={hr} />
                    <div style={hintRow}>
                        <span style={{ color: C.textTertiary, fontSize: T.cap, letterSpacing: 0.5, textTransform: "uppercase" }}>
                            다가오는 이벤트
                        </span>
                        <span style={{ color: C.textSecondary, fontSize: T.cap }}>
                            EventCalendar 컴포넌트 참조
                        </span>
                    </div>
                </>
            )}
        </div>
    )
}


/* ─────────── 서브 컴포넌트 ─────────── */

function CountBadge({ label, count, color }: { label: string; count: number; color: string }) {
    return (
        <span
            style={{
                display: "inline-flex", alignItems: "center", gap: 4,
                padding: `${S.xs / 2}px ${S.sm}px`,
                background: `${color}1A`,
                border: `1px solid ${color}33`,
                borderRadius: R.sm,
                fontSize: T.cap, fontWeight: T.w_semi,
                color, fontFamily: FONT,
            }}
        >
            <span>{label}</span>
            <span style={{ ...MONO, fontWeight: T.w_bold }}>{count}</span>
        </span>
    )
}

function FilterChip({ label, active, count, onClick, color }: {
    label: string; active: boolean; count: number; onClick: () => void; color: string
}) {
    return (
        <button
            onClick={onClick}
            style={{
                background: active ? `${color}1A` : "transparent",
                border: `1px solid ${active ? color : C.border}`,
                color: active ? color : C.textTertiary,
                padding: `${S.xs}px ${S.md}px`,
                borderRadius: R.pill,
                fontSize: T.cap,
                fontWeight: T.w_semi,
                fontFamily: FONT,
                letterSpacing: 0.5,
                cursor: "pointer",
                transition: X.base,
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
            }}
        >
            <span>{label}</span>
            {count > 0 && (
                <span style={{ ...MONO, fontSize: T.cap, color: active ? color : C.textTertiary }}>
                    {count}
                </span>
            )}
        </button>
    )
}

function AlertCard({ alert }: { alert: any }) {
    const meta = LEVEL_META[alert.level as AlertLevel] || LEVEL_META.INFO
    const cat = String(alert.category || "").toLowerCase()
    const catLabel = CAT_LABELS[cat] || alert.category

    return (
        <div
            style={{
                padding: `${S.md}px ${S.lg}px`,
                borderLeft: `2px solid ${meta.color}`,
                display: "flex",
                flexDirection: "column",
                gap: S.xs,
                borderBottom: `1px solid ${C.border}`,
            }}
        >
            {/* level + category row */}
            <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                <span
                    style={{
                        width: 6, height: 6, borderRadius: "50%",
                        background: meta.color,
                    }}
                />
                <span style={{ color: meta.color, fontSize: T.cap, fontWeight: T.w_bold, letterSpacing: 0.5 }}>
                    {meta.label}
                </span>
                {catLabel && (
                    <>
                        <span style={{ color: C.textDisabled, fontSize: T.cap }}>·</span>
                        <span
                            style={{
                                fontSize: T.cap, fontWeight: T.w_semi,
                                color: C.textTertiary,
                                letterSpacing: 0.5,
                            }}
                        >
                            {catLabel}
                        </span>
                    </>
                )}
                {alert.ticker && (
                    <>
                        <span style={{ color: C.textDisabled, fontSize: T.cap }}>·</span>
                        <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap }}>{alert.ticker}</span>
                    </>
                )}
            </div>

            {/* message */}
            <div style={{ color: C.textPrimary, fontSize: T.body, lineHeight: T.lh_normal }}>
                {alert.message}
            </div>

            {/* action */}
            {alert.action && (
                <div
                    style={{
                        color: C.accent, fontSize: T.cap, fontWeight: T.w_semi,
                        background: C.accentSoft,
                        borderLeft: `2px solid ${C.accent}80`,
                        padding: `${S.xs}px ${S.sm}px`,
                        borderRadius: R.sm,
                        marginTop: 2,
                    }}
                >
                    → {alert.action}
                </div>
            )}
        </div>
    )
}


/* ─────────── 스타일 ─────────── */

const shell: CSSProperties = {
    width: "100%", boxSizing: "border-box",
    fontFamily: FONT, color: C.textPrimary,
    background: C.bgPage,
    border: `1px solid ${C.border}`,
    borderRadius: 16,
    padding: S.xxl,
    display: "flex", flexDirection: "column",
    gap: S.lg,
}

const banner: CSSProperties = {
    display: "flex", flexDirection: "column", gap: S.md,
    paddingLeft: S.lg,
    transition: X.base,
}

const bannerTop: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
}

const bannerLabelRow: CSSProperties = {
    display: "flex", alignItems: "center", gap: S.sm,
}

const headlineMsg: CSSProperties = {
    color: C.textPrimary, fontSize: T.title, fontWeight: T.w_semi,
    lineHeight: T.lh_normal, letterSpacing: "-0.01em",
}

const badgeRow: CSSProperties = {
    display: "flex", gap: S.sm, flexWrap: "wrap", alignItems: "center",
}

const actionBox: CSSProperties = {
    background: C.bgElevated,
    borderLeft: `2px solid ${C.accent}80`,
    padding: `${S.md}px ${S.lg}px`,
    borderRadius: R.sm,
    display: "flex", flexDirection: "column",
}

const actionTitle: CSSProperties = {
    color: C.accent, fontSize: T.cap, fontWeight: T.w_bold,
    letterSpacing: "0.08em", textTransform: "uppercase",
}

const actionItem: CSSProperties = {
    color: C.textPrimary, fontSize: T.body, lineHeight: T.lh_normal,
}

const hr: CSSProperties = {
    height: 1, background: C.border, margin: 0,
}

const filterRow: CSSProperties = {
    display: "flex", gap: S.sm, flexWrap: "wrap",
}

const listWrap: CSSProperties = {
    display: "flex", flexDirection: "column",
}

const emptyBox: CSSProperties = {
    padding: `${S.xxl}px 0`, textAlign: "center",
}

const hintRow: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: `${S.sm}px 0`,
}

const loadingBox: CSSProperties = {
    minHeight: 120,
    display: "flex", alignItems: "center", justifyContent: "center",
}


/* ─────────── Framer Property Controls ─────────── */

AlertHub.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    market: "kr",
    maxAlerts: 15,
    defaultExpanded: false,
}

addPropertyControls(AlertHub, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
    maxAlerts: {
        type: ControlType.Number,
        title: "최대 알림 수",
        defaultValue: 15,
        min: 5, max: 30, step: 1,
    },
    defaultExpanded: {
        type: ControlType.Boolean,
        title: "펼친 상태로 시작",
        defaultValue: false,
    },
})

import { addPropertyControls, ControlType } from "framer"
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * StockSearch — 종목 검색 (Step 6.4 모던 심플)
 *
 * 출처: StockSearch.tsx (470줄) 통째 재작성.
 *
 * 설계:
 *   - KR/US toggle (시장별 검색 + analyze)
 *   - 검색 입력 + suggestions list (debounce 200ms)
 *   - 종목 선택 시 analyze API → 결과 카드 (multi_score + 6 metrics + signals + 비상장)
 *   - watchlist 하트 토글 (localStorage 영속, cross-component sync)
 *   - API base normalize (Vercel preview 경고)
 *
 * 모던 심플 6원칙:
 *   1. No card-in-card — 외곽 1개 + 결과 카드만
 *   2. Flat hierarchy — input + 결과 + suggestions
 *   3. Mono numerics — 점수, PER, RSI, %
 *   4. Color discipline — 등급 색 토큰 (strongBuy/buy/watch/caution/avoid)
 *   5. Emoji 0 (✕ → "×" 텍스트, ✕ 닫기)
 *   6. 자체 색 (#B5FF19 / #FFD600 / #FF4D4D / #555 / #888 / #fff /
 *      #2A0000 / #1A2A00 / #0D1A00 / #1A1A1A) 모두 토큰
 *
 * feedback_no_hardcode_position 적용: inline 렌더링.
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    success: "0 0 6px rgba(34,197,94,0.30)",
    warn: "0 0 6px rgba(245,158,11,0.30)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_normal: 1.5,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ─────────── API 헬퍼 ─────────── */
const DEFAULT_API = "https://project-yw131.vercel.app"

function normalizeApiBase(raw: string): string {
    let s = (raw || "").trim().replace(/\/+$/, "")
    if (!s) return ""
    if (!/^https?:\/\//i.test(s)) s = `https://${s.replace(/^\/+/, "")}`
    return s.replace(/\/+$/, "")
}

const FETCH_OPTS: RequestInit = { mode: "cors", credentials: "omit" }

function humanizeFetchError(err: unknown, fallback: string): string {
    const msg = err instanceof Error ? err.message : typeof err === "string" ? err : ""
    const m = (msg || "").toLowerCase()
    if (msg === "Failed to fetch" || m.includes("failed to fetch") || m.includes("networkerror") || m.includes("load failed")) {
        return "Failed to fetch — Vercel Deployment Protection(로그인 벽)이 켜져 있으면 Framer에서 막힙니다. Dashboard → Settings → Deployment Protection 에서 Production 공개로 변경하세요."
    }
    if (m.includes("unexpected end of json") || m.includes("json.parse") || m.includes("unexpected token")) {
        return "서버 응답 비정상 (빈 응답 또는 JSON 오류). API 상태를 확인하세요."
    }
    return msg || fallback
}

function safeJsonParse(text: string): any {
    if (!text || text.trim().length === 0) return null
    try { return JSON.parse(text) } catch { return null }
}

function looksLikeVercelPreviewUrl(url: string): boolean {
    try {
        const host = new URL(url).hostname.toLowerCase()
        if (!host.endsWith(".vercel.app")) return false
        return host.includes("-git-")
    } catch { return false }
}


/* ─────────── Watchlist (localStorage) ─────────── */
const LS_KEY = "verity_watchlist"
const WATCH_EVENT = "verity-watchlist-change"

interface WatchlistItem {
    ticker: string
    name: string
    market: string
    addedAt: number
}

function readWatchlist(): WatchlistItem[] {
    if (typeof window === "undefined") return []
    try {
        const raw = localStorage.getItem(LS_KEY)
        if (!raw || raw.length < 2) return []
        const parsed = JSON.parse(raw)
        return Array.isArray(parsed) ? parsed : []
    } catch { return [] }
}

function writeWatchlist(items: WatchlistItem[]) {
    if (typeof window === "undefined") return
    localStorage.setItem(LS_KEY, JSON.stringify(items))
    window.dispatchEvent(new CustomEvent(WATCH_EVENT, { detail: items }))
}

function addToWatchlist(ticker: string, name: string, market: string): boolean {
    const list = readWatchlist()
    if (list.some((it) => it.ticker === ticker)) return false
    list.push({ ticker, name, market, addedAt: Date.now() })
    writeWatchlist(list)
    return true
}

function removeFromWatchlist(ticker: string) {
    writeWatchlist(readWatchlist().filter((it) => it.ticker !== ticker))
}

function HeartIcon({ filled, size = 14, color }: { filled?: boolean; size?: number; color: string }) {
    return (
        <svg
            width={size} height={size} viewBox="0 0 24 24"
            fill={filled ? color : "none"}
            stroke={color} strokeWidth={2}
            strokeLinecap="round" strokeLinejoin="round"
        >
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
        </svg>
    )
}


/* ─────────── 색 매핑 ─────────── */
function scoreColor(score: number): string {
    if (score >= 65) return C.accent
    if (score >= 45) return C.watch
    return C.danger
}
function recColor(rec: string): string {
    if (rec === "STRONG_BUY") return C.strongBuy
    if (rec === "BUY") return C.buy
    if (rec === "WATCH") return C.watch
    if (rec === "CAUTION") return C.caution
    if (rec === "AVOID") return C.avoid
    return C.textTertiary
}
function rsiColor(rsi: number): string {
    if (rsi <= 30) return C.success
    if (rsi >= 70) return C.danger
    return C.textPrimary
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

interface Props {
    apiBase: string
    market: "kr" | "us"
}

export default function StockSearch(props: Props) {
    const api = normalizeApiBase(props.apiBase) || normalizeApiBase(DEFAULT_API)
    const market: "kr" | "us" = props.market || "kr"
    const isUS = market === "us"

    const [query, setQuery] = useState("")
    const [suggestions, setSuggestions] = useState<any[]>([])
    const [result, setResult] = useState<any>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
    const marketRef = useRef(market)
    marketRef.current = market

    const handleSearch = (q: string) => {
        setQuery(q)
        if (!q.trim()) {
            setSuggestions([])
            setResult(null)
            setError(null)
            return
        }
        setResult(null)
        setError(null)

        if (looksLikeVercelPreviewUrl(api)) {
            setError("API Base 가 Preview 주소입니다. Production URL 을 넣으세요.")
            setSuggestions([])
            return
        }

        if (searchTimer.current) clearTimeout(searchTimer.current)
        searchTimer.current = setTimeout(() => {
            const mkt = marketRef.current === "us" ? "us" : "kr"
            fetch(`${api}/api/search?q=${encodeURIComponent(q.trim())}&limit=8&market=${mkt}`, FETCH_OPTS)
                .then(async (r) => {
                    if (!r.ok) throw new Error(`HTTP ${r.status}`)
                    const txt = await r.text()
                    const parsed = safeJsonParse(txt)
                    if (parsed === null) throw new Error("서버가 빈 응답을 반환했습니다")
                    return parsed
                })
                .then((items) => {
                    if (Array.isArray(items)) {
                        setSuggestions(items)
                        setError(null)
                    } else {
                        setSuggestions([])
                        setError("검색 응답 형식 오류")
                    }
                })
                .catch((e) => {
                    setSuggestions([])
                    setError(humanizeFetchError(e, "검색 API 연결 실패"))
                })
        }, 200)
    }

    const analyze = (ticker: string, name: string) => {
        setLoading(true)
        setSuggestions([])
        setError(null)
        setQuery(name)
        if (looksLikeVercelPreviewUrl(api)) {
            setResult({ error: "Preview URL 은 Framer 에서 막힐 수 있습니다." })
            setLoading(false)
            return
        }
        const mkt = marketRef.current === "us" ? "us" : "kr"
        fetch(`${api}/api/stock?q=${encodeURIComponent(ticker)}&market=${mkt}`, FETCH_OPTS)
            .then(async (r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                const txt = await r.text()
                const parsed = safeJsonParse(txt)
                if (parsed === null) throw new Error("서버가 빈 응답을 반환했습니다")
                return parsed
            })
            .then((res) => {
                setResult(res.error ? { error: res.error } : res)
                setLoading(false)
            })
            .catch((e) => {
                setResult({ error: humanizeFetchError(e, "서버 연결 실패 (URL·CORS 확인)") })
                setLoading(false)
            })
    }

    /* watchlist sync */
    const [watchlist, setWatchlist] = useState<WatchlistItem[]>(() => readWatchlist())
    useEffect(() => {
        const onSync = () => setWatchlist(readWatchlist())
        const onStorage = (e: StorageEvent) => { if (e.key === LS_KEY) onSync() }
        window.addEventListener(WATCH_EVENT, onSync)
        window.addEventListener("storage", onStorage)
        return () => {
            window.removeEventListener(WATCH_EVENT, onSync)
            window.removeEventListener("storage", onStorage)
        }
    }, [])

    /* market 변경 시 reset */
    useEffect(() => {
        setQuery("")
        setSuggestions([])
        setResult(null)
        setError(null)
    }, [market])

    /* heart toast */
    const [heartToast, setHeartToast] = useState<string | null>(null)
    const heartToastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
    const showHeartToast = useCallback((msg: string) => {
        setHeartToast(msg)
        if (heartToastTimer.current) clearTimeout(heartToastTimer.current)
        heartToastTimer.current = setTimeout(() => setHeartToast(null), 2000)
    }, [])

    const watchedTickers = useMemo(() => new Set(watchlist.map((it) => it.ticker)), [watchlist])

    const handleHeartClick = useCallback(
        (e: React.MouseEvent, ticker: string, name: string, mkt?: string) => {
            e.stopPropagation()
            if (watchedTickers.has(ticker)) {
                removeFromWatchlist(ticker)
                setWatchlist(readWatchlist())
                showHeartToast(`${name} 관심 해제`)
            } else {
                addToWatchlist(ticker, name, mkt || (isUS ? "us" : "kr"))
                setWatchlist(readWatchlist())
                showHeartToast(`${name} 관심 등록 완료`)
            }
        },
        [watchedTickers, isUS, showHeartToast]
    )

    const s = result && !result.error ? result : null
    const ms = s ? (s.multi_factor?.multi_score ?? s.safety_score ?? 0) : 0
    const msC = scoreColor(ms)
    const sRec = s?.recommendation || "WATCH"
    const sRecC = recColor(sRec)

    const isToastErr =
        !!heartToast && (heartToast.includes("실패") || heartToast.includes("오류") || heartToast.includes("못했"))

    return (
        <div style={{ ...shell, position: "relative" }}>
            {/* heart toast */}
            {heartToast && (
                <div
                    style={{
                        position: "absolute",
                        top: -36, left: "50%", transform: "translateX(-50%)",
                        background: isToastErr ? `${C.danger}1A` : C.accentSoft,
                        border: `1px solid ${isToastErr ? C.danger : C.accent}`,
                        color: isToastErr ? C.danger : C.accent,
                        padding: `${S.xs}px ${S.lg}px`,
                        borderRadius: R.md,
                        fontSize: T.cap,
                        fontWeight: T.w_semi,
                        fontFamily: FONT,
                        zIndex: 20,
                        maxWidth: 320,
                        wordBreak: "break-all",
                        boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
                    }}
                >
                    {heartToast}
                </div>
            )}

            {/* Search input */}
            <div style={inputRow}>
                <svg width={16} height={16} viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
                    <circle cx={11} cy={11} r={7} stroke={C.textTertiary} strokeWidth={2} />
                    <path d="M16 16L20 20" stroke={C.textTertiary} strokeWidth={2} strokeLinecap="round" />
                </svg>
                <input
                    type="text"
                    placeholder={isUS ? "종목명 또는 티커 (예: 테슬라, AAPL)" : "종목명 또는 코드"}
                    value={query}
                    onChange={(e) => handleSearch(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Escape") { setQuery(""); setResult(null); setSuggestions([]) }
                    }}
                    style={inputStyle}
                />
                {query && (
                    <button
                        onClick={() => { setQuery(""); setResult(null); setSuggestions([]) }}
                        style={{
                            background: "none", border: "none",
                            color: C.textTertiary, cursor: "pointer",
                            fontSize: T.sub, padding: 0,
                            fontFamily: FONT, lineHeight: 1,
                        }}
                        aria-label="검색어 지우기"
                    >
                        ×
                    </button>
                )}
            </div>

            {/* Loading */}
            {loading && (
                <div style={{ textAlign: "center", padding: `${S.xxl}px 0` }}>
                    <div
                        style={{
                            width: 28, height: 28,
                            border: `3px solid ${C.bgElevated}`,
                            borderTopColor: C.accent,
                            borderRadius: "50%",
                            margin: "0 auto",
                            animation: "ssp-spin 0.8s linear infinite",
                        }}
                    />
                    <span style={{ color: C.textSecondary, fontSize: T.cap, marginTop: S.sm, display: "block" }}>
                        실시간 분석 중…
                    </span>
                    <style>{`@keyframes ssp-spin { to { transform: rotate(360deg) } }`}</style>
                </div>
            )}

            {/* Result card */}
            {!loading && s && (
                <div style={resultCard}>
                    {/* name + ticker + recommendation */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: S.sm }}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                            <span style={{ color: C.textPrimary, fontSize: T.sub, fontWeight: T.w_bold }}>
                                {s.name}
                            </span>
                            <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap, marginLeft: S.sm }}>
                                {s.ticker} · {s.market}
                            </span>
                        </div>
                        <span
                            style={{
                                background: sRecC,
                                color: sRec === "WATCH" ? C.bgPage : sRec === "BUY" || sRec === "STRONG_BUY" ? C.bgPage : C.textPrimary,
                                fontSize: T.cap, fontWeight: T.w_bold,
                                letterSpacing: "0.05em",
                                padding: `${S.xs / 2}px ${S.sm}px`,
                                borderRadius: R.sm,
                                cursor: sRec === "AVOID" ? "help" : "default",
                                flexShrink: 0,
                            }}
                            title={sRec === "AVOID" ? "AVOID = 펀더멘털 결함 (감사거절·분식·상폐 위험 등). 단순 저점수는 CAUTION." : undefined}
                        >
                            {sRec}
                        </span>
                    </div>

                    {/* score + 6 metrics */}
                    <div style={{ display: "flex", gap: S.md }}>
                        <div
                            style={{
                                width: 64, height: 64, borderRadius: "50%",
                                border: `3px solid ${msC}`,
                                display: "flex", flexDirection: "column",
                                alignItems: "center", justifyContent: "center",
                                flexShrink: 0,
                            }}
                        >
                            <span style={{ ...MONO, color: msC, fontSize: T.title, fontWeight: T.w_black, lineHeight: 1 }}>
                                {ms}
                            </span>
                            <span style={{ color: C.textTertiary, fontSize: 9, fontWeight: T.w_med, letterSpacing: "0.05em" }}>
                                종합점수
                            </span>
                        </div>
                        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: S.xs }}>
                            <Metric
                                label={isUS ? "Price" : "현재가"}
                                value={isUS
                                    ? `$${(s.price ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                                    : `${(s.price ?? 0).toLocaleString()}원`}
                            />
                            <Metric label="PER" value={s.per != null ? s.per.toFixed(1) : "—"} />
                            <Metric label={isUS ? "Div" : "배당"} value={s.div_yield != null ? `${s.div_yield.toFixed(1)}%` : "—"} />
                            <Metric
                                label="RSI"
                                value={s.technical?.rsi != null ? String(s.technical.rsi) : "—"}
                                color={rsiColor(s.technical?.rsi ?? 50)}
                            />
                            <Metric label={isUS ? "Flow" : "수급"} value={s.flow?.flow_score != null ? String(s.flow.flow_score) : "—"} />
                            <Metric
                                label={isUS ? "From High" : "고점대비"}
                                value={s.drop_from_high_pct != null ? `${s.drop_from_high_pct.toFixed(0)}%` : "—"}
                            />
                        </div>
                    </div>

                    {/* Signals */}
                    {Array.isArray(s.technical?.signals) && s.technical.signals.length > 0 && (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: S.xs }}>
                            {s.technical.signals.map((sig: string, i: number) => (
                                <span key={i} style={signalTag}>{sig}</span>
                            ))}
                        </div>
                    )}

                    {/* Watchlist heart */}
                    <div>
                        <button
                            onClick={(e) => handleHeartClick(e, s.ticker, s.name, s.market)}
                            style={{
                                background: C.bgElevated,
                                border: `1px solid ${C.border}`,
                                borderRadius: R.md,
                                padding: `${S.xs}px ${S.md}px`,
                                cursor: "pointer", fontFamily: FONT,
                                display: "flex", alignItems: "center", gap: S.xs,
                            }}
                        >
                            <HeartIcon
                                filled={watchedTickers.has(s.ticker)}
                                size={14}
                                color={watchedTickers.has(s.ticker) ? C.accent : C.textTertiary}
                            />
                            <span
                                style={{
                                    color: watchedTickers.has(s.ticker) ? C.accent : C.textSecondary,
                                    fontSize: T.cap,
                                    fontWeight: T.w_semi,
                                }}
                            >
                                {watchedTickers.has(s.ticker) ? "관심 해제" : "관심 등록"}
                            </span>
                        </button>
                    </div>

                    {/* 비상장 노출 */}
                    {s.unlisted_exposure?.total_count > 0 && (
                        <div
                            style={{
                                background: C.bgPage,
                                border: `1px solid ${C.accent}33`,
                                borderRadius: R.md,
                                padding: `${S.md}px ${S.lg}px`,
                                display: "flex", flexDirection: "column", gap: S.xs,
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <span
                                    style={{
                                        color: C.accent, fontSize: T.cap,
                                        fontWeight: T.w_bold, letterSpacing: "0.05em",
                                    }}
                                >
                                    비상장 투자 ({s.unlisted_exposure.total_count}건)
                                </span>
                                {s.unlisted_exposure.total_stake_value_억 > 0 && (
                                    <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap }}>
                                        지분가치 {s.unlisted_exposure.total_stake_value_억.toLocaleString()}억
                                    </span>
                                )}
                            </div>
                            {s.unlisted_exposure.items.slice(0, 5).map((u: any, ui: number) => (
                                <div
                                    key={ui}
                                    style={{
                                        display: "flex", justifyContent: "space-between", alignItems: "center",
                                        padding: `${S.xs}px 0`,
                                        borderBottom: ui < Math.min(4, s.unlisted_exposure.items.length - 1) ? `1px solid ${C.border}` : "none",
                                    }}
                                >
                                    <div style={{ display: "flex", gap: S.xs, alignItems: "center" }}>
                                        <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap, minWidth: 14 }}>
                                            {ui + 1}
                                        </span>
                                        <span style={{ color: C.textPrimary, fontSize: T.cap, fontWeight: T.w_semi }}>
                                            {u.name}
                                        </span>
                                    </div>
                                    <div style={{ display: "flex", gap: S.sm, alignItems: "center" }}>
                                        <span style={{ ...MONO, color: C.accent, fontSize: T.cap, fontWeight: T.w_bold }}>
                                            {u.ownership_pct}%
                                        </span>
                                        {u.stake_value_억 > 0 && (
                                            <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap }}>
                                                {u.stake_value_억.toLocaleString()}억
                                            </span>
                                        )}
                                    </div>
                                </div>
                            ))}
                            {s.unlisted_exposure.total_count > 5 && (
                                <div style={{ textAlign: "center" }}>
                                    <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                                        외 {s.unlisted_exposure.total_count - 5}건 더
                                    </span>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Result error */}
            {!loading && result?.error && (
                <div style={{ textAlign: "center", padding: `${S.lg}px 0` }}>
                    <span style={{ color: C.danger, fontSize: T.body }}>{result.error}</span>
                </div>
            )}

            {/* Suggestions list */}
            {!loading && !result && suggestions.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span
                        style={{
                            color: C.textTertiary, fontSize: T.cap,
                            fontWeight: T.w_med, letterSpacing: "0.05em",
                            textTransform: "uppercase",
                            marginBottom: S.xs,
                        }}
                    >
                        {isUS ? "Select a stock for real-time analysis" : "종목 선택 시 실시간 분석"}
                    </span>
                    {suggestions.map((sg: any) => (
                        <div
                            key={sg.ticker}
                            style={{
                                display: "flex", justifyContent: "space-between", alignItems: "center",
                                padding: `${S.sm}px ${S.md}px`,
                                borderRadius: R.sm,
                                position: "relative",
                                transition: X.fast,
                            }}
                            onMouseEnter={(e) => (e.currentTarget.style.background = C.bgElevated)}
                            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                        >
                            <div style={{ flex: 1, cursor: "pointer", minWidth: 0 }} onClick={() => analyze(sg.ticker, sg.name)}>
                                <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>
                                    {sg.name}
                                </span>
                                {sg.name_kr && (
                                    <span style={{ color: C.textSecondary, fontSize: T.cap, marginLeft: S.xs }}>
                                        {sg.name_kr}
                                    </span>
                                )}
                                <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap, marginLeft: S.sm }}>
                                    {sg.ticker}
                                </span>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: S.xs }}>
                                <span style={{ color: C.textTertiary, fontSize: T.cap }}>{sg.market}</span>
                                <button
                                    onClick={(e) => handleHeartClick(e, sg.ticker, sg.name, sg.market)}
                                    style={{
                                        background: "none", border: "none",
                                        cursor: "pointer", padding: "2px 4px",
                                        lineHeight: 1, display: "flex", alignItems: "center",
                                    }}
                                    title="관심종목에 추가"
                                >
                                    <HeartIcon
                                        filled={watchedTickers.has(sg.ticker)}
                                        size={14}
                                        color={watchedTickers.has(sg.ticker) ? C.accent : C.textTertiary}
                                    />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Search error */}
            {!loading && error && (
                <div style={{ padding: `${S.md}px 0` }}>
                    <span style={{ color: C.warn, fontSize: T.cap, lineHeight: T.lh_normal }}>{error}</span>
                </div>
            )}

            {/* Empty result */}
            {!loading && !result && !error && suggestions.length === 0 && query.length >= 2 && (
                <div style={{ textAlign: "center", padding: `${S.lg}px 0` }}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>
                        "{query}" 검색 결과 없음
                    </span>
                </div>
            )}
        </div>
    )
}


/* ─────────── 서브 컴포넌트 ─────────── */

function Metric({ label, value, color = C.textPrimary }: { label: string; value: string; color?: string }) {
    return (
        <div
            style={{
                background: C.bgPage,
                borderRadius: R.sm,
                padding: `${S.xs}px ${S.sm}px`,
                display: "flex", flexDirection: "column", gap: 2,
                minWidth: 0,
            }}
        >
            <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med, letterSpacing: "0.03em" }}>
                {label}
            </span>
            <span style={{ ...MONO, color, fontSize: T.cap, fontWeight: T.w_semi }}>
                {value}
            </span>
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
    padding: S.lg,
    display: "flex", flexDirection: "column",
    gap: S.md,
}

const inputRow: CSSProperties = {
    display: "flex", alignItems: "center", gap: S.sm,
    background: C.bgElevated,
    border: `1px solid ${C.border}`,
    borderRadius: R.md,
    padding: `${S.sm}px ${S.lg}px`,
}

const inputStyle: CSSProperties = {
    flex: 1,
    background: "transparent",
    border: "none",
    outline: "none",
    color: C.textPrimary,
    fontSize: T.body,
    fontFamily: FONT,
}

const resultCard: CSSProperties = {
    background: C.bgCard,
    border: `1px solid ${C.border}`,
    borderRadius: R.md,
    padding: `${S.lg}px ${S.lg}px`,
    display: "flex", flexDirection: "column", gap: S.md,
}

const signalTag: CSSProperties = {
    background: C.accentSoft,
    border: `1px solid ${C.accent}33`,
    color: C.accent,
    fontSize: T.cap,
    fontWeight: T.w_semi,
    padding: `2px ${S.sm}px`,
    borderRadius: R.sm,
    fontFamily: FONT,
    letterSpacing: "0.02em",
}


/* ─────────── Framer Property Controls ─────────── */

StockSearch.defaultProps = {
    apiBase: DEFAULT_API,
    market: "kr",
}

addPropertyControls(StockSearch, {
    apiBase: {
        type: ControlType.String,
        title: "API Base (Production URL)",
        defaultValue: DEFAULT_API,
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})

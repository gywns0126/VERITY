import { addPropertyControls, ControlType } from "framer"
import React, { useState, useRef, useEffect, useCallback, useMemo } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
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
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    accentStrong: "0 0 12px rgba(181,255,25,0.50)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


const DEFAULT_API = "https://vercel-api-alpha-umber.vercel.app"

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
    if (
        msg === "Failed to fetch" ||
        m.includes("failed to fetch") ||
        m.includes("networkerror") ||
        m.includes("load failed")
    ) {
        return "Failed to fetch — Vercel Deployment Protection(로그인 벽)이 켜져 있으면 Framer에서 막힙니다. Dashboard → 프로젝트 → Settings → Deployment Protection에서 Production 공개(또는 API만 허용)로 바꾸세요."
    }
    if (m.includes("unexpected end of json") || m.includes("json.parse") || m.includes("unexpected token")) {
        return "서버 응답이 비정상입니다 (빈 응답 또는 JSON 오류). API 상태를 확인하세요."
    }
    return msg || fallback
}

function safeJsonParse(text: string): any {
    if (!text || text.trim().length === 0) return null
    try { return JSON.parse(text) } catch (_e) { return null }
}

/** Vercel Git 브랜치 프리뷰(*-git-브랜치-*.vercel.app)만 경고. CLI/팀 Production URL은 해시가 있어도 여기 해당 안 함 */
function looksLikeVercelPreviewUrl(url: string): boolean {
    try {
        const host = new URL(url).hostname.toLowerCase()
        if (!host.endsWith(".vercel.app")) return false
        return host.includes("-git-")
    } catch (_e) {
        return false
    }
}

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
    } catch (_e) {
        return []
    }
}

function writeWatchlist(items: WatchlistItem[]) {
    if (typeof window === "undefined") return
    localStorage.setItem(LS_KEY, JSON.stringify(items))
    window.dispatchEvent(new CustomEvent(WATCH_EVENT, { detail: items }))
}

function addToWatchlist(ticker: string, name: string, market: string): boolean {
    const list = readWatchlist()
    if (list.some(it => it.ticker === ticker)) return false
    list.push({ ticker, name, market, addedAt: Date.now() })
    writeWatchlist(list)
    return true
}

function removeFromWatchlist(ticker: string) {
    writeWatchlist(readWatchlist().filter(it => it.ticker !== ticker))
}

function HeartIcon({ filled, size = 16, color = "#B5FF19" }: { filled?: boolean; size?: number; color?: string }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill={filled ? color : "none"} stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
        </svg>
    )
}

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
            setError("API Base가 Preview 주소입니다. Production URL을 넣으세요.")
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
            setResult({ error: "Preview URL은 Framer에서 막힐 수 있습니다." })
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

    useEffect(() => {
        setQuery("")
        setSuggestions([])
        setResult(null)
        setError(null)
    }, [market])

    const [heartToast, setHeartToast] = useState<string | null>(null)
    const heartToastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

    const showHeartToast = useCallback((msg: string) => {
        setHeartToast(msg)
        if (heartToastTimer.current) clearTimeout(heartToastTimer.current)
        heartToastTimer.current = setTimeout(() => setHeartToast(null), 2000)
    }, [])

    const watchedTickers = useMemo(() => new Set(watchlist.map(it => it.ticker)), [watchlist])

    const handleHeartClick = useCallback((e: React.MouseEvent, ticker: string, name: string, mkt?: string) => {
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
    }, [watchedTickers, isUS, showHeartToast])

    const s = result && !result.error ? result : null
    const ms = s ? (s.multi_factor?.multi_score ?? s.safety_score ?? 0) : 0
    const msColor = ms >= 65 ? "#B5FF19" : ms >= 45 ? "#FFD600" : "#FF4D4D"
    const sRec = s?.recommendation || "WATCH"
    const sRecColor = sRec === "BUY" ? "#B5FF19" : sRec === "AVOID" ? "#FF4D4D" : "#888"

    return (
        <div style={{ ...wrap, position: "relative" as const }}>
            {heartToast && (() => {
                const isErr = heartToast.includes("실패") || heartToast.includes("오류") || heartToast.includes("못했")
                return (
                    <div style={{
                        position: "absolute" as const, top: -36, left: "50%", transform: "translateX(-50%)",
                        background: isErr ? "#2A0000" : "#1A2A00", border: `1px solid ${isErr ? "#FF4D4D" : "#B5FF19"}`,
                        color: isErr ? "#FF4D4D" : "#B5FF19", padding: "6px 14px",
                        borderRadius: 8, fontSize: 11, fontWeight: 700, fontFamily: font, zIndex: 20,
                        maxWidth: 320, wordBreak: "break-all" as const, boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
                    }}>{heartToast}</div>
                )
            })()}
            <div style={inputRow}>
                <svg width={16} height={16} viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
                    <circle cx={11} cy={11} r={7} stroke="#555" strokeWidth={2} />
                    <path d="M16 16L20 20" stroke="#555" strokeWidth={2} strokeLinecap="round" />
                </svg>
                <input
                    type="text"
                    placeholder={isUS ? "종목명 또는 티커 검색 (예: 테슬라, AAPL)..." : "종목명 또는 코드 검색..."}
                    value={query}
                    onChange={(e) => handleSearch(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Escape") { setQuery(""); setResult(null); setSuggestions([]) } }}
                    style={inputStyle}
                />
                {query && (
                    <button onClick={() => { setQuery(""); setResult(null); setSuggestions([]) }}
                        style={{ background: "none", border: "none", color: C.textTertiary, cursor: "pointer", fontSize: 16, padding: 0 }}>
                        ✕
                    </button>
                )}
            </div>

            {loading && (
                <div style={{ textAlign: "center", padding: "24px 0" }}>
                    <div style={{ width: 28, height: 28, border: "3px solid #222", borderTopColor: "#B5FF19", borderRadius: "50%", margin: "0 auto 10px", animation: "spin 0.8s linear infinite" }} />
                    <span style={{ color: C.textSecondary, fontSize: 12 }}>실시간 분석 중...</span>
                    <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
                </div>
            )}

            {!loading && s && (
                <div style={resultCard}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                        <div>
                            <span style={{ color: C.textPrimary, fontSize: 16, fontWeight: 800 }}>{s.name}</span>
                            <span style={{ color: C.textTertiary, fontSize: 12, marginLeft: 8 }}>{s.ticker} · {s.market}</span>
                        </div>
                        <span
                            style={{ background: sRecColor, color: "#000", fontSize: 11, fontWeight: 800, padding: "3px 10px", borderRadius: 6, cursor: sRec === "AVOID" ? "help" : "default" }}
                            title={sRec === "AVOID" ? "AVOID = 펀더멘털 결함 (감사거절·분식·상폐 위험 등). 단순 저점수는 CAUTION." : undefined}
                        >{sRec}</span>
                    </div>
                    <div style={{ display: "flex", gap: 12 }}>
                        <div style={{ width: 64, height: 64, borderRadius: 32, border: `3px solid ${msColor}`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                            <span style={{ color: msColor, fontSize: 20, fontWeight: 900 }}>{ms}</span>
                            <span style={{ color: C.textTertiary, fontSize: 8 }}>종합점수</span>
                        </div>
                        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                            <Metric label={isUS ? "Price" : "현재가"} value={isUS ? `$${s.price?.toLocaleString("en-US", {minimumFractionDigits:2, maximumFractionDigits:2})}` : `${s.price?.toLocaleString()}원`} />
                            <Metric label="PER" value={s.per?.toFixed(1) || "—"} />
                            <Metric label={isUS ? "Div" : "배당"} value={`${s.div_yield?.toFixed(1)}%`} />
                            <Metric label="RSI" value={String(s.technical?.rsi || "—")} color={(s.technical?.rsi || 50) <= 30 ? "#B5FF19" : (s.technical?.rsi || 50) >= 70 ? "#FF4D4D" : "#fff"} />
                            <Metric label={isUS ? "Flow" : "수급"} value={String(s.flow?.flow_score || "—")} />
                            <Metric label={isUS ? "From High" : "고점대비"} value={`${s.drop_from_high_pct?.toFixed(0)}%`} />
                        </div>
                    </div>
                    {s.technical?.signals?.length > 0 && (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}>
                            {s.technical.signals.map((sig: string, i: number) => (
                                <span key={i} style={signalTag}>{sig}</span>
                            ))}
                        </div>
                    )}

                    {/* 관심 등록 하트 */}
                    <div style={{ marginTop: 8 }}>
                        <button
                            onClick={(e) => handleHeartClick(e, s.ticker, s.name, s.market)}
                            style={{ background: C.bgElevated, border: `1px solid ${C.border}`, borderRadius: 8, padding: "6px 12px", cursor: "pointer", fontFamily: font, display: "flex", alignItems: "center", gap: 6 }}
                        >
                            <HeartIcon filled={watchedTickers.has(s.ticker)} size={14} color={watchedTickers.has(s.ticker) ? "#B5FF19" : "#555"} />
                            <span style={{ color: watchedTickers.has(s.ticker) ? "#B5FF19" : "#888", fontSize: 11, fontWeight: 700 }}>
                                {watchedTickers.has(s.ticker) ? "관심 해제" : "관심 등록"}
                            </span>
                        </button>
                    </div>

                    {s.unlisted_exposure?.total_count > 0 && (
                        <div style={{ marginTop: 10, padding: "10px 12px", background: C.bgPage, border: "1px solid #1A2A00", borderRadius: 10 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                                <span style={{ color: "#B5FF19", fontSize: 11, fontWeight: 700 }}>비상장 투자 ({s.unlisted_exposure.total_count}건)</span>
                                {s.unlisted_exposure.total_stake_value_억 > 0 && (
                                    <span style={{ color: C.textSecondary, fontSize: 10 }}>지분가치 {s.unlisted_exposure.total_stake_value_억.toLocaleString()}억</span>
                                )}
                            </div>
                            {s.unlisted_exposure.items.slice(0, 5).map((u: any, ui: number) => (
                                <div key={ui} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0", borderBottom: ui < Math.min(4, s.unlisted_exposure.items.length - 1) ? "1px solid #1A1A1A" : "none" }}>
                                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                                        <span style={{ color: C.textTertiary, fontSize: 9, minWidth: 14 }}>{ui + 1}</span>
                                        <span style={{ color: C.textPrimary, fontSize: 11, fontWeight: 600 }}>{u.name}</span>
                                    </div>
                                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                        <span style={{ color: "#B5FF19", fontSize: 10, fontWeight: 700 }}>{u.ownership_pct}%</span>
                                        {u.stake_value_억 > 0 && <span style={{ color: C.textSecondary, fontSize: 9 }}>{u.stake_value_억.toLocaleString()}억</span>}
                                    </div>
                                </div>
                            ))}
                            {s.unlisted_exposure.total_count > 5 && (
                                <div style={{ textAlign: "center", marginTop: 4 }}>
                                    <span style={{ color: C.textTertiary, fontSize: 9 }}>외 {s.unlisted_exposure.total_count - 5}건 더</span>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {!loading && result?.error && (
                <div style={{ textAlign: "center", padding: "16px 0" }}>
                    <span style={{ color: "#FF4D4D", fontSize: 13 }}>{result.error}</span>
                </div>
            )}

            {!loading && !result && suggestions.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 8 }}>
                    <span style={{ color: C.textTertiary, fontSize: 10, marginBottom: 4 }}>{isUS ? "Select a stock for real-time analysis" : "종목을 선택하면 실시간 분석합니다"}</span>
                    {suggestions.map((sg: any) => (
                        <div key={sg.ticker}
                            style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 10px", borderRadius: 8, position: "relative" as const }}
                            onMouseEnter={(e) => (e.currentTarget.style.background = "#1A1A1A")}
                            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                            <div style={{ flex: 1, cursor: "pointer" }} onClick={() => analyze(sg.ticker, sg.name)}>
                                <span style={{ color: C.textPrimary, fontSize: 13, fontWeight: 600 }}>{sg.name}</span>
                                {sg.name_kr && <span style={{ color: C.textSecondary, fontSize: 10, marginLeft: 4 }}>{sg.name_kr}</span>}
                                <span style={{ color: C.textTertiary, fontSize: 10, marginLeft: 6 }}>{sg.ticker}</span>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{ color: C.textTertiary, fontSize: 10 }}>{sg.market}</span>
                                <button
                                    onClick={(e) => handleHeartClick(e, sg.ticker, sg.name, sg.market)}
                                    style={{ background: "none", border: "none", cursor: "pointer", padding: "2px 4px", lineHeight: 1, display: "flex", alignItems: "center" }}
                                    title="관심종목에 추가"
                                >
                                    <HeartIcon filled={watchedTickers.has(sg.ticker)} size={14} color={watchedTickers.has(sg.ticker) ? "#B5FF19" : "#555"} />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {!loading && error && (
                <div style={{ textAlign: "left", padding: "12px 0" }}>
                    <span style={{ color: "#FF9F40", fontSize: 11, lineHeight: 1.5 }}>{error}</span>
                </div>
            )}

            {!loading && !result && !error && suggestions.length === 0 && query.length >= 2 && (
                <div style={{ textAlign: "center", padding: "16px 0" }}>
                    <span style={{ color: C.textTertiary, fontSize: 13 }}>"{query}" 검색 결과 없음</span>
                </div>
            )}
        </div>
    )
}

function Metric({ label, value, color = "#fff" }: { label: string; value: string; color?: string }) {
    return (
        <div style={{ background: C.bgPage, borderRadius: 6, padding: "6px 8px", display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ color: C.textTertiary, fontSize: 9, fontWeight: 500 }}>{label}</span>
            <span style={{ color, fontSize: 12, fontWeight: 700 }}>{value}</span>
        </div>
    )
}

StockSearch.defaultProps = { apiBase: DEFAULT_API, market: "kr" }

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

const font = "'Pretendard', -apple-system, sans-serif"
const wrap: React.CSSProperties = { width: "100%", background: C.bgPage, borderRadius: 16, fontFamily: font, padding: 16, border: `1px solid ${C.border}` }
const inputRow: React.CSSProperties = { display: "flex", alignItems: "center", gap: 8, background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: 10, padding: "8px 14px" }
const inputStyle: React.CSSProperties = { flex: 1, background: "transparent", border: "none", outline: "none", color: C.textPrimary, fontSize: 13, fontFamily: font }
const resultCard: React.CSSProperties = { background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: 12, padding: 16, marginTop: 12 }
const signalTag: React.CSSProperties = { background: "#0D1A00", border: "1px solid #1A2A00", color: "#B5FF19", fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 4 }

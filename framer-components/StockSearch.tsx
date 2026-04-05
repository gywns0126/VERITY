import { addPropertyControls, ControlType } from "framer"
import { useState, useRef } from "react"

const DEFAULT_API = "https://vercel-an2dzupi8-kim-hyojuns-projects.vercel.app"

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
    return msg || fallback
}

/** Vercel Git 브랜치 프리뷰(*-git-브랜치-*.vercel.app)만 경고. CLI/팀 Production URL은 해시가 있어도 여기 해당 안 함 */
function looksLikeVercelPreviewUrl(url: string): boolean {
    try {
        const host = new URL(url).hostname.toLowerCase()
        if (!host.endsWith(".vercel.app")) return false
        return host.includes("-git-")
    } catch {
        return false
    }
}

interface Props {
    apiBase: string
}

export default function StockSearch(props: Props) {
    const api = normalizeApiBase(props.apiBase) || normalizeApiBase(DEFAULT_API)
    const [query, setQuery] = useState("")
    const [suggestions, setSuggestions] = useState<any[]>([])
    const [result, setResult] = useState<any>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

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
            fetch(`${api}/api/search?q=${encodeURIComponent(q.trim())}&limit=8`, FETCH_OPTS)
                .then(async (r) => {
                    if (!r.ok) throw new Error(`HTTP ${r.status}`)
                    const ct = r.headers.get("content-type") || ""
                    if (!ct.includes("application/json")) throw new Error("API가 JSON이 아님")
                    return r.json()
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
        fetch(`${api}/api/stock?q=${encodeURIComponent(ticker)}`, FETCH_OPTS)
            .then(async (r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                const ct = r.headers.get("content-type") || ""
                if (!ct.includes("application/json")) throw new Error("JSON 아님")
                return r.json()
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

    const s = result && !result.error ? result : null
    const ms = s ? (s.multi_factor?.multi_score || s.safety_score || 0) : 0
    const msColor = ms >= 65 ? "#B5FF19" : ms >= 45 ? "#FFD600" : "#FF4D4D"
    const sRec = s?.recommendation || "WATCH"
    const sRecColor = sRec === "BUY" ? "#B5FF19" : sRec === "AVOID" ? "#FF4D4D" : "#888"

    return (
        <div style={wrap}>
            <div style={inputRow}>
                <svg width={16} height={16} viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
                    <circle cx={11} cy={11} r={7} stroke="#555" strokeWidth={2} />
                    <path d="M16 16L20 20" stroke="#555" strokeWidth={2} strokeLinecap="round" />
                </svg>
                <input
                    type="text"
                    placeholder="종목명 또는 코드 검색..."
                    value={query}
                    onChange={(e) => handleSearch(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Escape") { setQuery(""); setResult(null); setSuggestions([]) } }}
                    style={inputStyle}
                />
                {query && (
                    <button onClick={() => { setQuery(""); setResult(null); setSuggestions([]) }}
                        style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: 16, padding: 0 }}>
                        ✕
                    </button>
                )}
            </div>

            {loading && (
                <div style={{ textAlign: "center", padding: "24px 0" }}>
                    <div style={{ width: 28, height: 28, border: "3px solid #222", borderTopColor: "#B5FF19", borderRadius: "50%", margin: "0 auto 10px", animation: "spin 0.8s linear infinite" }} />
                    <span style={{ color: "#888", fontSize: 12 }}>실시간 분석 중...</span>
                    <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
                </div>
            )}

            {!loading && s && (
                <div style={resultCard}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                        <div>
                            <span style={{ color: "#fff", fontSize: 16, fontWeight: 800 }}>{s.name}</span>
                            <span style={{ color: "#555", fontSize: 12, marginLeft: 8 }}>{s.ticker} · {s.market}</span>
                        </div>
                        <span style={{ background: sRecColor, color: "#000", fontSize: 11, fontWeight: 800, padding: "3px 10px", borderRadius: 6 }}>{sRec}</span>
                    </div>
                    <div style={{ display: "flex", gap: 12 }}>
                        <div style={{ width: 64, height: 64, borderRadius: 32, border: `3px solid ${msColor}`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                            <span style={{ color: msColor, fontSize: 20, fontWeight: 900 }}>{ms}</span>
                            <span style={{ color: "#666", fontSize: 8 }}>종합점수</span>
                        </div>
                        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                            <Metric label="현재가" value={`${s.price?.toLocaleString()}원`} />
                            <Metric label="PER" value={s.per?.toFixed(1) || "—"} />
                            <Metric label="배당" value={`${s.div_yield?.toFixed(1)}%`} />
                            <Metric label="RSI" value={String(s.technical?.rsi || "—")} color={(s.technical?.rsi || 50) <= 30 ? "#B5FF19" : (s.technical?.rsi || 50) >= 70 ? "#FF4D4D" : "#fff"} />
                            <Metric label="수급" value={String(s.flow?.flow_score || "—")} />
                            <Metric label="고점대비" value={`${s.drop_from_high_pct?.toFixed(0)}%`} />
                        </div>
                    </div>
                    {s.technical?.signals?.length > 0 && (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}>
                            {s.technical.signals.map((sig: string, i: number) => (
                                <span key={i} style={signalTag}>{sig}</span>
                            ))}
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
                    <span style={{ color: "#444", fontSize: 10, marginBottom: 4 }}>종목을 선택하면 실시간 분석합니다</span>
                    {suggestions.map((sg: any) => (
                        <div key={sg.ticker} onClick={() => analyze(sg.ticker, sg.name)}
                            style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 10px", borderRadius: 8, cursor: "pointer" }}
                            onMouseEnter={(e) => (e.currentTarget.style.background = "#1A1A1A")}
                            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                            <div>
                                <span style={{ color: "#fff", fontSize: 13, fontWeight: 600 }}>{sg.name}</span>
                                <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{sg.ticker}</span>
                            </div>
                            <span style={{ color: "#444", fontSize: 10 }}>{sg.market}</span>
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
                    <span style={{ color: "#555", fontSize: 13 }}>"{query}" 검색 결과 없음</span>
                </div>
            )}
        </div>
    )
}

function Metric({ label, value, color = "#fff" }: { label: string; value: string; color?: string }) {
    return (
        <div style={{ background: "#0A0A0A", borderRadius: 6, padding: "6px 8px", display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ color: "#555", fontSize: 9, fontWeight: 500 }}>{label}</span>
            <span style={{ color, fontSize: 12, fontWeight: 700 }}>{value}</span>
        </div>
    )
}

StockSearch.defaultProps = { apiBase: DEFAULT_API }

addPropertyControls(StockSearch, {
    apiBase: {
        type: ControlType.String,
        title: "API Base (Production URL)",
        defaultValue: DEFAULT_API,
    },
})

const font = "'Pretendard', -apple-system, sans-serif"
const wrap: React.CSSProperties = { width: "100%", background: "#0A0A0A", borderRadius: 16, fontFamily: font, padding: 16, border: "1px solid #222" }
const inputRow: React.CSSProperties = { display: "flex", alignItems: "center", gap: 8, background: "#111", border: "1px solid #222", borderRadius: 10, padding: "8px 14px" }
const inputStyle: React.CSSProperties = { flex: 1, background: "transparent", border: "none", outline: "none", color: "#fff", fontSize: 13, fontFamily: font }
const resultCard: React.CSSProperties = { background: "#111", border: "1px solid #222", borderRadius: 12, padding: 16, marginTop: 12 }
const signalTag: React.CSSProperties = { background: "#0D1A00", border: "1px solid #1A2A00", color: "#B5FF19", fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 4 }

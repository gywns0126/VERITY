import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * 내 보유종목 — VERITY 공개 터미널 (골든구스) 탭.
 *
 * 인증 — localStorage["verity_supabase_session"].access_token → /api/holdings (user_holdings CRUD).
 *   미로그인/캔버스 = SAMPLE 데모 + 로그인 CTA. (StockDashboard getAccessToken 패턴 재사용)
 * RULE 7 — 평가손익 = 현재가 × 수량 − 입력평단 (단순 계산·사실). 매수·매도·추천·점수 0.
 * 현재가 = /api/stock?q=ticker (best-effort). 실패 시 평단 기준 표시.
 * 행 클릭 → 종목 리포트 (KR=stockPath, US=usStockPath, ?q=ticker) per-종목 detail.
 * 반응형 — ResizeObserver + 100%/maxHeight/overflow.
 * 🎨 종목 로고·국기 = PublicDiscovery/StockReport 와 동일 토스 시그니처(2026-06-21 크로스-surface 통일). 카드 radius 16 표준.
 * 테마: Framer 네이티브 추종 — body[data-framer-theme] 읽어 dark 전환(캔버스는 dark prop 정적 프리뷰).
 *   onAccent = 브랜드 보라(vg) 위 글자색. 라이트=흰색/다크=짙은색(가독성).
 * 🚨 브랜드 = 보라(vg #6c5ce7/#a99bff, 2026-06-26 [[project_golden_goose_brand_purple]]). 면책("추천/권유 아님·점수 held") 제거 → 사이트 하단 단일 면책. 데이터-기준 설명은 유지.
 * 2026-06-27: 로그인 사용자 첫 로딩 = 샘플 목업 번쩍 제거 → shimmer 스켈레톤(소형주 vsrShimmer 통일). 비로그인=샘플 데모 유지.
 * 2026-06-27: 비로그인 = 로그인 CTA 카드 강화(큰 버튼 "로그인하고 시작하기") + 샘플을 "예시"로 명확 라벨 — 샘플을 실제 내 데이터로 오해하는 것 방지.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968",
    faint: "#8b95a1", line: "#e5e8eb", up: "#f04452", down: "#3182f6",
    vg: "#6c5ce7", vgS: "#f0edff", vt: "#6c5ce7", vtS: "#f0edff", danger: "#f04452", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1",
    faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff",
    vg: "#a99bff", vgS: "#241f3a", vt: "#a99bff", vtS: "#241f3a", danger: "#f04452", onAccent: "#0f1318",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const FX = 1380
const LOGO_BASE = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
const KR_MK = ["KOSPI", "KOSDAQ", "KONEX"]

interface Props {
    apiBase: string
    loginUrl: string
    stockPath: string
    usStockPath: string
    dark: boolean
}
const DEFAULT_API = "https://project-yw131.vercel.app"

const SAMPLE = [
    { ticker: "005930", name: "삼성전자", shares: 100, avg_cost: 68000, price: 71200, market: "kr" },
    { ticker: "NVDA", name: "NVIDIA", shares: 20, avg_cost: 120, price: 172.4, market: "us" },
    { ticker: "000660", name: "SK하이닉스", shares: 15, avg_cost: 215000, price: 241000, market: "kr" },
    { ticker: "247540", name: "에코프로비엠", shares: 8, avg_cost: 155000, price: 142300, market: "kr" },
]

function getToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const r = localStorage.getItem("verity_supabase_session")
        if (!r) return ""
        const s = JSON.parse(r)
        return (s && typeof s.access_token === "string") ? s.access_token : ""
    } catch {
        return ""
    }
}
function money(v: number): string {
    if (!isFinite(v)) return "—"
    return Math.round(v).toLocaleString("en-US") + "원"
}
function flagCode(market: any): string {
    const m = String(market || "").toUpperCase()
    if (KR_MK.indexOf(m) >= 0 || m.indexOf("KOS") >= 0 || m.indexOf("KONEX") >= 0) return "kr"
    if (m.indexOf("NAS") >= 0 || m.indexOf("NYSE") >= 0 || m.indexOf("AMEX") >= 0 || m.indexOf("US") >= 0) return "us"
    return "kr"
}

function Logo(props: { ticker: string; name: string; market: string; C: any; size?: number }) {
    const { ticker, name, market, C } = props
    const size = props.size || 32
    const [err, setErr] = useState(false)
    const ch = (String(name || "?").trim().charAt(0)) || "?"
    const code = flagCode(market)
    const fsize = Math.round(size * 0.46)
    return (
        <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
            {!err && ticker ? (
                <img src={LOGO_BASE + ticker + ".png"} alt="" width={size} height={size}
                    onError={() => setErr(true)}
                    style={{ width: size, height: size, borderRadius: 10, objectFit: "cover", display: "block", background: C.bg }} />
            ) : (
                <div style={{ width: size, height: size, borderRadius: 10, background: C.vtS, color: C.vt, display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * 0.42), fontWeight: 800 }}>{ch}</div>
            )}
            {code && (
                <img src={FLAG_BASE + code + ".svg"} alt="" width={fsize} height={fsize}
                    style={{ position: "absolute", right: -3, bottom: -3, width: fsize, height: fsize, borderRadius: "50%", border: `1.5px solid ${C.card}`, background: C.card, display: "block", boxShadow: "0 1px 2px rgba(0,0,0,0.18)" }} />
            )}
        </div>
    )
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicHoldingsTab(props: Props) {
    const { apiBase, loginUrl, stockPath, usStockPath, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [rows, setRows] = useState<any[]>(SAMPLE)
    const [prices, setPrices] = useState<Record<string, number>>({})
    const [isDemo, setIsDemo] = useState(true)
    // 로그인(토큰) 사용자는 첫 로딩 = 스켈레톤(샘플 목업 번쩍 방지). 비로그인/캔버스 = 즉시 샘플.
    const [loading, setLoading] = useState<boolean>(() => (onCanvas ? false : !!getToken()))
    const [showAdd, setShowAdd] = useState(false)
    const [form, setForm] = useState({ ticker: "", name: "", shares: "", avg_cost: "", market: "kr" })
    const [busy, setBusy] = useState(false)
    const [themeDark, setThemeDark] = useState<boolean>(!!dark)

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 dark prop 정적) */
    useEffect(() => {
        if (onCanvas) return
        const read = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    const loadHoldings = useCallback(() => {
        if (onCanvas) return
        const token = getToken()
        if (!token) { setIsDemo(true); setRows(SAMPLE); setLoading(false); return }
        setLoading(true)
        fetch(base + "/api/holdings", { headers: { Authorization: "Bearer " + token } })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (Array.isArray(d)) { setIsDemo(false); setRows(d) }
            })
            .catch(() => {})
            .finally(() => setLoading(false))
    }, [base, onCanvas])

    useEffect(() => { loadHoldings() }, [loadHoldings])

    useEffect(() => {
        if (onCanvas || isDemo) return
        let alive = true
        rows.forEach((h) => {
            const tk = String(h.ticker || "")
            if (!tk || prices[tk] != null) return
            fetch(base + "/api/stock?q=" + encodeURIComponent(tk) + "&market=" + (h.market || "kr"))
                .then((r) => (r.ok ? r.json() : null))
                .then((d) => {
                    const p = d && (d.price ?? d.current_price ?? (d.stock && d.stock.price))
                    if (alive && p) setPrices((prev) => ({ ...prev, [tk]: Number(p) }))
                })
                .catch(() => {})
        })
        return () => { alive = false }
    }, [rows, isDemo, base, onCanvas, prices])

    const goStock = useCallback((h: any) => {
        if (typeof window === "undefined") return
        const tk = String(h.ticker || "").trim()
        if (!tk) return
        const isUs = h.market === "us" || h.currency === "USD"
        const path = (isUs ? (usStockPath || "/us/stock") : (stockPath || "/stock")).replace(/\/+$/, "")
        window.location.href = path + "?q=" + encodeURIComponent(tk)
    }, [stockPath, usStockPath])

    const addHolding = useCallback(() => {
        const token = getToken()
        if (!token) { if (loginUrl && typeof window !== "undefined") window.location.href = loginUrl; return }
        const tk = form.ticker.trim()
        if (!tk) return
        setBusy(true)
        fetch(base + "/api/holdings", {
            method: "POST",
            headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({
                ticker: tk, name: form.name.trim(), market: form.market,
                shares: Number(form.shares) || 0, avg_cost: Number(form.avg_cost) || 0,
            }),
        })
            .then((r) => r.json().catch(() => ({})))
            .then(() => {
                setShowAdd(false)
                setForm({ ticker: "", name: "", shares: "", avg_cost: "", market: "kr" })
                loadHoldings()
            })
            .catch(() => {})
            .finally(() => setBusy(false))
    }, [form, base, loginUrl, loadHoldings])

    const delHolding = useCallback((id: string) => {
        const token = getToken()
        if (!token || !id) return
        fetch(base + "/api/holdings", {
            method: "DELETE",
            headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({ id }),
        }).then(() => loadHoldings()).catch(() => {})
    }, [base, loadHoldings])

    const narrow = w > 0 && w < 560
    const pad = narrow ? 12 : 18

    const evald = rows.map((h) => {
        const fx = h.market === "us" || h.currency === "USD" ? FX : 1
        const cur = prices[String(h.ticker)] != null ? prices[String(h.ticker)] : Number(h.price) || Number(h.avg_cost) || 0
        const val = (Number(h.shares) || 0) * cur * fx
        const cost = (Number(h.shares) || 0) * (Number(h.avg_cost) || 0) * fx
        const pl = val - cost
        const plPct = cost > 0 ? (pl / cost) * 100 : 0
        return { ...h, _val: val, _pl: pl, _plPct: plPct }
    })
    const totalVal = evald.reduce((a, b) => a + b._val, 0)
    const totalCost = evald.reduce((a, b) => a + (Number(b.shares) || 0) * (Number(b.avg_cost) || 0) * (b.market === "us" || b.currency === "USD" ? FX : 1), 0)
    const totalPl = totalVal - totalCost
    const totalPlPct = totalCost > 0 ? (totalPl / totalCost) * 100 : 0
    const withWeight = evald.map((h) => ({ ...h, _weight: totalVal > 0 ? (h._val / totalVal) * 100 : 0 })).sort((a, b) => b._val - a._val)
    const plColor = (v: number) => (v > 0 ? C.up : v < 0 ? C.down : C.faint)

    const inputStyle: CSSProperties = {
        border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 10px", fontSize: 13,
        fontFamily: FONT, background: C.bg, color: C.ink, outline: "none", minWidth: 0,
    }

    const wrap: CSSProperties = {
        width: "100%", height: "100%", maxHeight: "100%", overflowY: "auto", overflowX: "hidden",
        background: C.bg, fontFamily: FONT, padding: pad, boxSizing: "border-box", color: C.ink,
    }

    // ── 스켈레톤 shimmer (소형주 카드 vsrShimmer 와 동일 패턴) ──
    const shimmer: CSSProperties = {
        backgroundColor: isDark ? "#222a33" : "#e9edf1",
        backgroundImage: `linear-gradient(90deg, ${isDark ? "#222a33" : "#e9edf1"} 25%, ${isDark ? "#2d3742" : "#f3f5f7"} 37%, ${isDark ? "#222a33" : "#e9edf1"} 63%)`,
        backgroundSize: "800px 100%",
        animation: "vhtShimmer 1.4s ease-in-out infinite",
    }
    const sk = (sw: number | string, sh: number, r: number): CSSProperties => ({ width: sw, height: sh, borderRadius: r, ...shimmer })

    return (
        <div ref={rootRef} style={wrap}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: narrow ? 18 : 20, fontWeight: 800, letterSpacing: "-0.5px" }}>내 보유종목</div>
                    <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 3 }}>
                        평단 입력 기준
                    </div>
                </div>
                {!loading && !isDemo && (
                    <button onClick={() => setShowAdd((v) => !v)}
                        style={{ border: "none", cursor: "pointer", padding: "7px 14px", borderRadius: 999, fontSize: 13, fontWeight: 700, fontFamily: FONT, flexShrink: 0, background: C.vg, color: C.onAccent }}>
                        {showAdd ? "닫기" : "+ 종목 추가"}
                    </button>
                )}
            </div>

            {loading ? (
                <>
                    <style>{"@keyframes vhtShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}"}</style>
                    {/* 요약 스켈레톤 */}
                    <div style={{ background: C.card, borderRadius: 16, padding: "18px 18px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 12 }}>
                        <div style={sk(80, 12, 6)} />
                        <div style={{ ...sk(170, 27, 7), margin: "9px 0" }} />
                        <div style={sk(120, 14, 6)} />
                    </div>
                    {/* 행 스켈레톤 */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
                        {[0, 1, 2, 3, 4].map((k) => (
                            <div key={k} style={{ display: "flex", alignItems: "center", gap: 12, background: C.card, borderRadius: 16, padding: "13px 15px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                                <div style={{ ...sk(36, 36, 10), flexShrink: 0 }} />
                                <div style={{ minWidth: 0, flex: 1 }}>
                                    <div style={sk("58%", 14, 6)} />
                                    <div style={{ ...sk("40%", 11, 5), marginTop: 7 }} />
                                </div>
                                <div style={{ textAlign: "right", flexShrink: 0 }}>
                                    <div style={sk(52, 14, 6)} />
                                    <div style={{ ...sk(72, 11, 5), marginTop: 7 }} />
                                </div>
                            </div>
                        ))}
                    </div>
                </>
            ) : (
                <>
                    {isDemo && (
                        <div style={{ background: C.vgS, color: C.ink, borderRadius: 16, padding: narrow ? "16px 15px" : "20px 18px", marginTop: 12 }}>
                            <div style={{ fontSize: narrow ? 15 : 16, fontWeight: 800, letterSpacing: "-0.3px" }}>로그인하고 내 보유종목 관리하기</div>
                            <div style={{ fontSize: 13, color: C.sub, fontWeight: 600, lineHeight: 1.6, marginTop: 7 }}>종목·수량·평단만 입력하면 평가손익을 한눈에. 기기·세션이 바뀌어도 그대로 유지돼요.</div>
                            {loginUrl && (
                                <a href={loginUrl} style={{ display: "inline-block", marginTop: 14, background: C.vg, color: C.onAccent, borderRadius: 10, padding: "11px 20px", fontSize: 14, fontWeight: 800, textDecoration: "none" }}>로그인하고 시작하기</a>
                            )}
                            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 12 }}>아래는 예시 화면이에요 — 로그인하면 내 종목으로 바뀌어요.</div>
                        </div>
                    )}

                    {/* 추가 폼 */}
                    {!isDemo && showAdd && (
                        <div style={{ background: C.card, borderRadius: 16, padding: "14px 15px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                            <div style={{ display: "grid", gridTemplateColumns: narrow ? "1fr 1fr" : "1fr 1fr 1fr 1fr", gap: 8 }}>
                                <input style={inputStyle} placeholder="종목코드 (005930)" value={form.ticker} onChange={(e) => setForm({ ...form, ticker: e.target.value })} />
                                <input style={inputStyle} placeholder="종목명" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                                <input style={inputStyle} placeholder="수량" inputMode="decimal" value={form.shares} onChange={(e) => setForm({ ...form, shares: e.target.value })} />
                                <input style={inputStyle} placeholder="평단" inputMode="decimal" value={form.avg_cost} onChange={(e) => setForm({ ...form, avg_cost: e.target.value })} />
                            </div>
                            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                                <select style={inputStyle} value={form.market} onChange={(e) => setForm({ ...form, market: e.target.value })}>
                                    <option value="kr">국내(KR)</option>
                                    <option value="us">미국(US)</option>
                                </select>
                                <button onClick={addHolding} disabled={busy}
                                    style={{ border: "none", cursor: "pointer", padding: "8px 18px", borderRadius: 8, fontSize: 13, fontWeight: 800, fontFamily: FONT, background: C.vg, color: C.onAccent, opacity: busy ? 0.6 : 1 }}>
                                    {busy ? "저장 중…" : "저장"}
                                </button>
                            </div>
                        </div>
                    )}

                    {/* 요약 */}
                    <div style={{ background: C.card, borderRadius: 16, padding: "18px 18px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 12 }}>
                        <div style={{ fontSize: 12, color: C.faint, fontWeight: 700 }}>총 평가금액{isDemo ? " · 예시" : ""}</div>
                        <div style={{ fontSize: 27, fontWeight: 800, letterSpacing: "-1px", margin: "3px 0" }}>{money(totalVal)}</div>
                        <div style={{ fontSize: 14, fontWeight: 800, color: plColor(totalPl) }}>
                            {(totalPl > 0 ? "+" : "") + money(totalPl)} · {(totalPlPct > 0 ? "+" : "") + totalPlPct.toFixed(1)}%
                        </div>
                        <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 6 }}>
                            보유 {rows.length}종목 · 평단 입력 기준(사실)
                        </div>
                    </div>

                    {/* 리스트 — 행 클릭 시 종목 리포트로 이동 */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
                        {withWeight.map((h) => (
                            <div key={h.id || h.ticker} onClick={() => goStock(h)} role="link" tabIndex={0}
                                style={{ display: "flex", alignItems: "center", gap: 12, background: C.card, borderRadius: 16, padding: "13px 15px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", cursor: "pointer" }}>
                                <Logo ticker={h.ticker} name={h.name} market={h.market} C={C} size={36} />
                                <div style={{ minWidth: 0, flex: narrow ? "1" : "0 0 auto", width: narrow ? "auto" : 150 }}>
                                    <div style={{ fontSize: 14.5, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{h.name || h.ticker}</div>
                                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>
                                        {h.ticker} · {Number(h.shares) || 0}주 · 비중 {h._weight.toFixed(0)}%
                                    </div>
                                </div>
                                {!narrow && (
                                    <div style={{ flex: 1, minWidth: 50 }}>
                                        <div style={{ height: 6, borderRadius: 3, background: C.line, overflow: "hidden" }}>
                                            <div style={{ width: Math.min(100, h._weight) + "%", height: "100%", background: C.vg }} />
                                        </div>
                                    </div>
                                )}
                                <div style={{ textAlign: "right", marginLeft: "auto", flexShrink: 0 }}>
                                    <div style={{ fontSize: 14.5, fontWeight: 800, color: plColor(h._pl) }}>{(h._plPct > 0 ? "+" : "") + h._plPct.toFixed(1)}%</div>
                                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>{money(h._val)}</div>
                                </div>
                                <span style={{ flexShrink: 0, fontSize: 16, color: C.faint, fontWeight: 700, lineHeight: 1 }}>›</span>
                                {!isDemo && h.id && (
                                    <button onClick={(e) => { e.stopPropagation(); delHolding(h.id) }} title="삭제"
                                        style={{ border: "none", background: "transparent", cursor: "pointer", color: C.faint, fontSize: 16, fontWeight: 700, padding: "0 2px", flexShrink: 0 }}>×</button>
                                )}
                            </div>
                        ))}
                    </div>

                    <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 14, lineHeight: 1.5 }}>
                        종목 누르면 상세 리포트 · 평가손익 = 현재가 × 보유수량 − 입력 평단 (단순 계산·사실)
                    </div>
                </>
            )}
        </div>
    )
}

addPropertyControls(PublicHoldingsTab, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    loginUrl: { type: ControlType.String, title: "Login URL", defaultValue: "/login" },
    stockPath: { type: ControlType.String, title: "Stock Path (KR)", defaultValue: "/stock" },
    usStockPath: { type: ControlType.String, title: "Stock Path (US)", defaultValue: "/us/stock" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

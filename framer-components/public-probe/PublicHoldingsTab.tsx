import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * 내 보유종목 — VERITY 공개 터미널 (골든구스) 탭. [보유종목 | 예상 세금] 2-탭.
 *
 * 인증 — localStorage["verity_supabase_session"].access_token → /api/holdings (user_holdings CRUD).
 *   미로그인/캔버스 = SAMPLE 미리보기 + 로그인 CTA. (StockDashboard getAccessToken 패턴 재사용)
 * RULE 7 — 평가손익 = 현재가 × 수량 − 입력평단 (단순 계산·사실). 매수·매도·추천·점수 0.
 * 현재가 = /api/stock?q=ticker (best-effort). 행 클릭 → 종목 리포트.
 * 반응형 — ResizeObserver. 테마 = body[data-framer-theme] 자가감지. 브랜드 보라(vg).
 * 🚩 국기 = circle-flags SVG(Logo/FlagIcon) — 이모지 금지(싸구려). 데모 = 단순 CTA(3D목업 X).
 *
 * 예상 세금 탭: 보유(같은 데이터) → 매도 가정 비용 추정.
 *   세금(법정·증권사 무관) = KR 양도세 0%(비과세 ~2029)+증권거래세 0.20% / US 양도세 22%·27.5%·250만 공제(누진) / 대주주 10억 경고.
 *   수수료(증권사별) = broker_guide.json domestic_fee/overseas_fee × 매도금액.
 *   세제 SoT = api/trading/account_profile.py (변경 시 TAX 상수 동기화). RULE 7 사실+세무사 면책, RULE 6 LLM 0.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968",
    faint: "#8b95a1", line: "#e5e8eb", up: "#f04452", down: "#3182f6",
    vg: "#6c5ce7", vgS: "#f0edff", vt: "#6c5ce7", vtS: "#f0edff", danger: "#f04452", warn: "#ff9500", warnS: "#fff6e9", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1",
    faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff",
    vg: "#a99bff", vgS: "#241f3a", vt: "#a99bff", vtS: "#241f3a", danger: "#f04452", warn: "#ffb340", warnS: "#3a2c14", onAccent: "#0f1318",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const FX = 1380
const LOGO_BASE = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
const KR_MK = ["KOSPI", "KOSDAQ", "KONEX"]
const BROKER_URL = "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/broker_guide.json"

// ── 세제 상수 (SoT = api/trading/account_profile.py, 2026 시행값) — inline 미러, 변경 시 동기화 ──
const TAX = {
    KR_TXN: 0.0020,              // 증권거래세 KOSPI/KOSDAQ (농특세 포함, 2026)
    KR_MAJOR_AMT: 1_000_000_000, // 대주주 종목당 보유 기준 = 10억 (양도세 과세)
    US_CGT: 0.22,                // 해외주식 양도세 (과표 3억 이하)
    US_CGT_HIGH: 0.275,          // 과표 3억 초과분
    US_DEDUCT: 2_500_000,        // 해외 양도소득 기본공제 (연, 합산)
    US_BRACKET: 300_000_000,     // 과표 3억 분기점
}

interface Props {
    apiBase: string
    loginUrl: string
    stockPath: string
    usStockPath: string
    dark: boolean
}
const DEFAULT_API = "https://project-yw131.vercel.app"

const SAMPLE = [
    { ticker: "005930", name: "삼성전자", shares: 100, avg_cost: 68000, price: 81200, market: "kr" },
    { ticker: "NVDA", name: "NVIDIA", shares: 20, avg_cost: 120, price: 172.4, market: "us" },
    { ticker: "000660", name: "SK하이닉스", shares: 15, avg_cost: 215000, price: 241000, market: "kr" },
    { ticker: "AAPL", name: "Apple", shares: 30, avg_cost: 150, price: 214.3, market: "us" },
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
const won = money
function wonCompact(v: number): string {
    const a = Math.abs(Math.round(v))
    const sign = v < 0 ? "-" : ""
    if (a >= 1e8) return sign + (a / 1e8).toFixed(a >= 1e9 ? 0 : 1) + "억원"
    if (a >= 1e4) return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만원"
    return sign + a.toLocaleString("en-US") + "원"
}
function parseFee(s: any): number {
    const n = parseFloat(String(s || "").replace(/[%\s]/g, ""))
    return isFinite(n) ? n / 100 : 0
}
function flagCode(market: any): string {
    const m = String(market || "").toUpperCase()
    if (KR_MK.indexOf(m) >= 0 || m.indexOf("KOS") >= 0 || m.indexOf("KONEX") >= 0) return "kr"
    if (m.indexOf("NAS") >= 0 || m.indexOf("NYSE") >= 0 || m.indexOf("AMEX") >= 0 || m.indexOf("US") >= 0) return "us"
    return "kr"
}

// 국기 = circle-flags SVG (이모지 X). Logo 의 국기 배지와 동일 소스.
function FlagIcon(props: { code: string; size?: number }) {
    const size = props.size || 15
    return (
        <img src={FLAG_BASE + props.code + ".svg"} alt="" width={size} height={size}
            style={{ width: size, height: size, borderRadius: "50%", display: "inline-block", verticalAlign: "-2px", flexShrink: 0 }} />
    )
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
    const [loading, setLoading] = useState<boolean>(() => (onCanvas ? false : !!getToken()))
    const [showAdd, setShowAdd] = useState(false)
    const [form, setForm] = useState({ ticker: "", name: "", shares: "", avg_cost: "", market: "kr" })
    const [busy, setBusy] = useState(false)
    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    const [view, setView] = useState<"holdings" | "tax">("holdings")
    const [brokers, setBrokers] = useState<any[]>([])
    const [brokerIdx, setBrokerIdx] = useState(0)

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

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

    // 증권사 수수료 (broker_guide) — 예상 세금 탭의 매도 수수료 산정용. 실패해도 무해(수수료 0).
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(BROKER_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const bs = (d && (d.brokers || d.items)) || []
                if (alive && Array.isArray(bs) && bs.length) setBrokers(bs)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas])

    const loadHoldings = useCallback(() => {
        if (onCanvas) return
        const token = getToken()
        if (!token) { setIsDemo(true); setRows(SAMPLE); setLoading(false); return }
        setLoading(true)
        fetch(base + "/api/holdings", { headers: { Authorization: "Bearer " + token } })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (Array.isArray(d)) { setIsDemo(false); setRows(d) } })
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
        const us = h.market === "us" || h.currency === "USD"
        const path = (us ? (usStockPath || "/us/stock") : (stockPath || "/stock")).replace(/\/+$/, "")
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
        const us = h.market === "us" || h.currency === "USD"
        const fx = us ? FX : 1
        const cur = prices[String(h.ticker)] != null ? prices[String(h.ticker)] : Number(h.price) || Number(h.avg_cost) || 0
        const val = (Number(h.shares) || 0) * cur * fx
        const cost = (Number(h.shares) || 0) * (Number(h.avg_cost) || 0) * fx
        const pl = val - cost
        const plPct = cost > 0 ? (pl / cost) * 100 : 0
        return { ...h, _us: us, _val: val, _pl: pl, _plPct: plPct }
    })
    const totalVal = evald.reduce((a, b) => a + b._val, 0)
    const totalCost = evald.reduce((a, b) => a + (Number(b.shares) || 0) * (Number(b.avg_cost) || 0) * (b._us ? FX : 1), 0)
    const totalPl = totalVal - totalCost
    const totalPlPct = totalCost > 0 ? (totalPl / totalCost) * 100 : 0
    const withWeight = evald.map((h) => ({ ...h, _weight: totalVal > 0 ? (h._val / totalVal) * 100 : 0 })).sort((a, b) => b._val - a._val)
    const plColor = (v: number) => (v > 0 ? C.up : v < 0 ? C.down : C.faint)

    // ── 예상 세금 + 수수료 (매도 가정) ──
    const krRows = evald.filter((h) => !h._us)
    const usRows = evald.filter((h) => h._us)
    const krProceeds = krRows.reduce((a, b) => a + b._val, 0)
    const usProceeds = usRows.reduce((a, b) => a + b._val, 0)
    const krTxnTax = krProceeds * TAX.KR_TXN
    const usGainSum = usRows.reduce((a, b) => a + b._pl, 0)
    const usTaxable = Math.max(0, usGainSum - TAX.US_DEDUCT)
    const usCgt = usTaxable <= TAX.US_BRACKET
        ? usTaxable * TAX.US_CGT
        : TAX.US_BRACKET * TAX.US_CGT + (usTaxable - TAX.US_BRACKET) * TAX.US_CGT_HIGH
    const broker = brokers[brokerIdx] || null
    const krCommission = krProceeds * parseFee(broker && broker.domestic_fee)
    const usCommission = usProceeds * parseFee(broker && broker.overseas_fee)
    const totalTax = krTxnTax + usCgt
    const totalCommission = krCommission + usCommission
    const krMajorRows = krRows.filter((h) => h._val >= TAX.KR_MAJOR_AMT)

    const inputStyle: CSSProperties = {
        border: `1px solid ${C.line}`, borderRadius: 8, padding: "8px 10px", fontSize: 13,
        fontFamily: FONT, background: C.bg, color: C.ink, outline: "none", minWidth: 0,
    }
    const wrap: CSSProperties = {
        width: "100%", height: "100%", maxHeight: "100%", overflowY: "auto", overflowX: "hidden",
        background: C.bg, fontFamily: FONT, padding: pad, boxSizing: "border-box", color: C.ink,
    }
    const cardS: CSSProperties = { background: C.card, borderRadius: 16, padding: "16px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 12 }

    const shimmer: CSSProperties = {
        backgroundColor: isDark ? "#222a33" : "#e9edf1",
        backgroundImage: `linear-gradient(90deg, ${isDark ? "#222a33" : "#e9edf1"} 25%, ${isDark ? "#2d3742" : "#f3f5f7"} 37%, ${isDark ? "#222a33" : "#e9edf1"} 63%)`,
        backgroundSize: "800px 100%", animation: "vhtShimmer 1.4s ease-in-out infinite",
    }
    const sk = (sw: number | string, sh: number, r: number): CSSProperties => ({ width: sw, height: sh, borderRadius: r, ...shimmer })
    const kv = (k: any, v: string, color?: string) => (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "6px 0", gap: 10 }}>
            <span style={{ fontSize: 12.5, color: C.sub, fontWeight: 600 }}>{k}</span>
            <span style={{ fontSize: 13.5, fontWeight: 800, color: color || C.ink, fontVariantNumeric: "tabular-nums" }}>{v}</span>
        </div>
    )

    const Tabs = (
        <div style={{ display: "flex", gap: 4, background: C.bg, borderRadius: 11, padding: 3, marginTop: 12 }}>
            {([["holdings", "보유종목"], ["tax", "예상 세금"]] as const).map(([k, label]) => (
                <div key={k} onClick={() => setView(k)} style={{
                    flex: 1, textAlign: "center", cursor: "pointer", fontSize: 13, fontWeight: 800, padding: "8px 0", borderRadius: 8,
                    background: view === k ? C.card : "transparent", color: view === k ? C.ink : C.faint,
                    boxShadow: view === k ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
                }}>{label}</div>
            ))}
        </div>
    )

    return (
        <div ref={rootRef} style={wrap}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: narrow ? 18 : 20, fontWeight: 800, letterSpacing: "-0.5px" }}>내 보유종목</div>
                    <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 3 }}>평단 입력 기준</div>
                </div>
                {!loading && !isDemo && view === "holdings" && (
                    <button onClick={() => setShowAdd((v) => !v)}
                        style={{ border: "none", cursor: "pointer", padding: "7px 14px", borderRadius: 999, fontSize: 13, fontWeight: 700, fontFamily: FONT, flexShrink: 0, background: C.vg, color: C.onAccent }}>
                        {showAdd ? "닫기" : "+ 종목 추가"}
                    </button>
                )}
            </div>

            {loading ? (
                <>
                    <style>{"@keyframes vhtShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}"}</style>
                    <div style={cardS}>
                        <div style={sk(80, 12, 6)} />
                        <div style={{ ...sk(170, 27, 7), margin: "9px 0" }} />
                        <div style={sk(120, 14, 6)} />
                    </div>
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
                            <div style={{ fontSize: 13, color: C.sub, fontWeight: 600, lineHeight: 1.6, marginTop: 7 }}>종목·수량·평단만 입력하면 평가손익·예상 세금을 한눈에. 기기·세션이 바뀌어도 그대로 유지돼요.</div>
                            {loginUrl && (
                                <a href={loginUrl} style={{ display: "inline-block", marginTop: 14, background: C.vg, color: C.onAccent, borderRadius: 10, padding: "11px 20px", fontSize: 14, fontWeight: 800, textDecoration: "none" }}>로그인하고 시작하기</a>
                            )}
                        </div>
                    )}

                    {Tabs}

                    {view === "holdings" ? (
                        <>
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

                            <div style={{ ...cardS, padding: "18px 18px" }}>
                                <div style={{ fontSize: 12, color: C.faint, fontWeight: 700 }}>총 평가금액</div>
                                <div style={{ fontSize: 27, fontWeight: 800, letterSpacing: "-1px", margin: "3px 0" }}>{money(totalVal)}</div>
                                <div style={{ fontSize: 14, fontWeight: 800, color: plColor(totalPl) }}>
                                    {(totalPl > 0 ? "+" : "") + money(totalPl)} · {(totalPlPct > 0 ? "+" : "") + totalPlPct.toFixed(1)}%
                                </div>
                                <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 6 }}>보유 {rows.length}종목 · 평단 입력 기준(사실)</div>
                            </div>

                            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
                                {withWeight.map((h) => (
                                    <div key={h.id || h.ticker} onClick={() => goStock(h)} role="link" tabIndex={0}
                                        style={{ display: "flex", alignItems: "center", gap: 12, background: C.card, borderRadius: 16, padding: "13px 15px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", cursor: "pointer" }}>
                                        <Logo ticker={h.ticker} name={h.name} market={h.market} C={C} size={36} />
                                        <div style={{ minWidth: 0, flex: narrow ? "1" : "0 0 auto", width: narrow ? "auto" : 150 }}>
                                            <div style={{ fontSize: 14.5, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{h.name || h.ticker}</div>
                                            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>{h.ticker} · {Number(h.shares) || 0}주 · 비중 {h._weight.toFixed(0)}%</div>
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
                    ) : (
                        <>
                            <div style={{ ...cardS, padding: "18px 18px" }}>
                                <div style={{ fontSize: 12, color: C.faint, fontWeight: 700 }}>매도 가정 시 예상 비용 (세금 + 수수료)</div>
                                <div style={{ fontSize: 27, fontWeight: 800, letterSpacing: "-1px", margin: "3px 0" }}>{won(totalTax + totalCommission)}</div>
                                <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 600 }}>세금 {wonCompact(totalTax)} + 수수료 {wonCompact(totalCommission)} · 평가손익 {totalPl >= 0 ? "+" : ""}{wonCompact(totalPl)} 기준</div>
                            </div>

                            {brokers.length > 0 && (
                                <div style={{ ...cardS, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                                    <span style={{ fontSize: 12.5, color: C.sub, fontWeight: 700 }}>증권사 (매도 수수료)</span>
                                    <select value={brokerIdx} onChange={(e) => setBrokerIdx(Number(e.target.value))} style={{ ...inputStyle, fontWeight: 700, maxWidth: "60%" }}>
                                        {brokers.map((b, i) => (<option key={i} value={i}>{b.name}</option>))}
                                    </select>
                                </div>
                            )}

                            <div style={cardS}>
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                                    <span style={{ fontSize: 15, fontWeight: 800, display: "flex", alignItems: "center", gap: 7 }}><FlagIcon code="kr" /> 국내 주식</span>
                                    <span style={{ fontSize: 11.5, fontWeight: 800, color: C.vg, background: C.vgS, padding: "3px 9px", borderRadius: 8 }}>양도세 0% · 비과세</span>
                                </div>
                                {kv("양도소득세", "0원 (비과세, ~2029)", C.vg)}
                                {kv("증권거래세 0.20%", won(krTxnTax))}
                                {broker ? kv("매도 수수료 (" + (broker.domestic_fee || "—") + ")", won(krCommission)) : null}
                                {kv("매도금액 합계", wonCompact(krProceeds))}
                                {krMajorRows.length > 0 && (
                                    <div style={{ background: C.warnS, color: C.warn, borderRadius: 10, padding: "9px 11px", fontSize: 11.5, fontWeight: 700, lineHeight: 1.5, marginTop: 8 }}>
                                        대주주 검토 — {krMajorRows.map((h) => h.name || h.ticker).join(", ")} (종목당 10억+ 보유 시 양도세 과세 대상). 시행령 공포일·정확 판정은 세무사 확인.
                                    </div>
                                )}
                            </div>

                            <div style={cardS}>
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                                    <span style={{ fontSize: 15, fontWeight: 800, display: "flex", alignItems: "center", gap: 7 }}><FlagIcon code="us" /> 해외 주식</span>
                                    <span style={{ fontSize: 11.5, fontWeight: 800, color: C.warn, background: C.warnS, padding: "3px 9px", borderRadius: 8 }}>양도세 22%</span>
                                </div>
                                {kv("양도소득 합계", (usGainSum >= 0 ? "+" : "") + wonCompact(usGainSum), usGainSum >= 0 ? C.up : C.down)}
                                {kv("기본공제 (연)", "−" + wonCompact(TAX.US_DEDUCT))}
                                {kv("과세표준", wonCompact(usTaxable))}
                                {kv("예상 양도세", won(usCgt), usCgt > 0 ? C.ink : C.vg)}
                                {broker ? kv("매도 수수료 (" + (broker.overseas_fee || "—") + ")", won(usCommission)) : null}
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>22%(과표 3억↓)·27.5%(초과) · 손실 연내통산(이월 없음) · 환율 {FX}원/$ 가정</div>
                            </div>

                            <div style={cardS}>
                                <div style={{ fontSize: 12.5, fontWeight: 800, marginBottom: 4 }}>종목별 평가손익</div>
                                {[...evald].sort((a, b) => Math.abs(b._pl) - Math.abs(a._pl)).map((h, i) => (
                                    <div key={h.id || h.ticker} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 0", borderTop: i === 0 ? "none" : "1px solid " + C.line, gap: 10 }}>
                                        <div style={{ minWidth: 0 }}>
                                            <div style={{ fontSize: 13.5, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "flex", alignItems: "center", gap: 6 }}>
                                                <FlagIcon code={h._us ? "us" : "kr"} />{h.name || h.ticker}
                                            </div>
                                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 2 }}>{h._us ? "양도세 22% 대상" : (h._val >= TAX.KR_MAJOR_AMT ? "대주주 과세 검토" : "비과세 · 거래세만")}</div>
                                        </div>
                                        <div style={{ fontSize: 13.5, fontWeight: 800, color: plColor(h._pl), fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>{h._pl >= 0 ? "+" : ""}{wonCompact(h._pl)}</div>
                                    </div>
                                ))}
                            </div>

                            <div style={{ ...cardS, background: C.vgS }}>
                                <div style={{ fontSize: 12.5, fontWeight: 800, marginBottom: 7 }}>알아두기</div>
                                {[
                                    "국내 상장주식 양도세 = 비과세 (금투세 폐지 2024-12-10, 2029년까지 유지 기조)",
                                    "대주주(종목당 보유 10억+) 는 국내도 양도세 과세 — 시행령 공포일 확인 필요",
                                    "해외주식 양도세 = 22% (과표 3억↓), 연 250만 기본공제(국가 합산), 손익 연내통산",
                                    "수수료는 증권사별로 다름 — 세금(양도세·거래세)은 법정으로 증권사 무관",
                                    "가상자산 양도세 = 2027-01-01~ 22% (연 250만 공제) — 본 추적기는 주식만 계산",
                                ].map((t, i) => (
                                    <div key={i} style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, lineHeight: 1.55, paddingLeft: 12, position: "relative", marginBottom: 4 }}>
                                        <span style={{ position: "absolute", left: 0, color: C.vg }}>·</span>{t}
                                    </div>
                                ))}
                            </div>

                            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 13, lineHeight: 1.5 }}>
                                세율·공제는 2026 시행값(사실). 추정·관측 보조용 — 실제 납세 판단은 세무사 확인. 절세 자문 아님.
                            </div>
                        </>
                    )}
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

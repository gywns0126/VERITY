import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * 예상 세금 추적기 — VERITY 공개 터미널 (골든구스) 탭. KR 홈그라운드 차별 기능.
 *
 * 보유종목(/api/holdings, PublicHoldingsTab 와 동일 인증·소스) → 매도 가정 시 예상 세금 추정.
 * 🚨 RULE 7 — 세율·공제는 사실(account_profile.py SoT 미러). 자체 점수·절세 자문·추천 0. "세무사 확인" 면책 내장.
 * 🚨 RULE 6 — LLM narrative 0. 순수 계산·규칙 표시(교육 가치).
 *
 * 세제 SoT = api/trading/account_profile.py (2026-06-19 Perplexity+KPMG cross-source 확정).
 *   ⚠️ 상수 변경 시 account_profile.py 와 동기화 의무(공유모듈 Framer 불가 → inline 미러).
 * 계산: KR 상장주식 양도세 0%(비과세, 금투세 폐지 ~2029) + 증권거래세 0.20%(매도금액) /
 *   US 해외주식 양도세 22%(과표 3억↓)·27.5%(초과), 연 250만 기본공제(합산) /
 *   대주주(종목당 보유 10억↑) = KR 양도세 과세 경고 / crypto 2027~ 22% horizon(주식탭 비계산, 안내).
 *
 * 생성 2026-06-27. 다크모드 자가감지 · cache-fallback · 배경 투명 · 브랜드 보라(vg).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968",
    faint: "#8b95a1", line: "#e5e8eb", up: "#f04452", down: "#3182f6",
    vg: "#6c5ce7", vgS: "#f0edff", danger: "#f04452", warn: "#ff9500", warnS: "#fff6e9", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1",
    faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff",
    vg: "#a99bff", vgS: "#241f3a", danger: "#f04452", warn: "#ffb340", warnS: "#3a2c14", onAccent: "#0f1318",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const FX = 1380

// ── 세제 상수 (SoT = api/trading/account_profile.py, 2026 시행값) — inline 미러, 변경 시 동기화 ──
const TAX = {
    KR_CGT: 0.0,                  // 국내 상장주식 양도세 = 비과세 (일반 개인, 금투세 폐지 2024-12-10)
    KR_TXN: 0.0020,              // 증권거래세 KOSPI/KOSDAQ (농특세 포함, 2026)
    KR_MAJOR_AMT: 1_000_000_000, // 대주주 종목당 보유 기준 = 10억 (양도세 과세)
    US_CGT: 0.22,                // 해외주식 양도세 (과표 3억 이하; 소득세20%+지방세2%)
    US_CGT_HIGH: 0.275,          // 과표 3억 초과분 (소득세25%+지방세2.5%)
    US_DEDUCT: 2_500_000,        // 해외 양도소득 기본공제 (연, 합산)
    US_BRACKET: 300_000_000,     // 과표 3억 분기점
    CRYPTO_CGT: 0.22,            // 가상자산 양도세 (2027-01-01~)
}

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
function isUs(h: any): boolean {
    return h.market === "us" || h.currency === "USD"
}
function won(v: number): string {
    if (!isFinite(v)) return "—"
    const a = Math.round(v)
    return a.toLocaleString("en-US") + "원"
}
function wonCompact(v: number): string {
    const a = Math.abs(Math.round(v))
    const sign = v < 0 ? "-" : ""
    if (a >= 1e8) return sign + (a / 1e8).toFixed(a >= 1e9 ? 0 : 1) + "억원"
    if (a >= 1e4) return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만원"
    return sign + a.toLocaleString("en-US") + "원"
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicTaxTracker(props: {
    apiBase: string; loginUrl: string; dark: boolean
}) {
    const { apiBase, loginUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [rows, setRows] = useState<any[]>(SAMPLE)
    const [prices, setPrices] = useState<Record<string, number>>({})
    const [isDemo, setIsDemo] = useState(true)
    const [loading, setLoading] = useState<boolean>(() => (onCanvas ? false : !!getToken()))
    const [themeDark, setThemeDark] = useState<boolean>(!!dark)

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT
    const base = (apiBase || "https://project-yw131.vercel.app").replace(/\/+$/, "")

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

    const load = useCallback(() => {
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

    useEffect(() => { load() }, [load])

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

    const narrow = w > 0 && w < 560
    const pad = narrow ? 12 : 18

    // ── 세금 계산 (매도 가정 시) ──
    const ev = rows.map((h) => {
        const us = isUs(h)
        const fx = us ? FX : 1
        const cur = prices[String(h.ticker)] != null ? prices[String(h.ticker)] : Number(h.price) || Number(h.avg_cost) || 0
        const shares = Number(h.shares) || 0
        const gainKRW = (cur - (Number(h.avg_cost) || 0)) * shares * fx   // 평가손익(원)
        const proceedsKRW = cur * shares * fx                            // 매도금액(원)
        const krMajor = !us && proceedsKRW >= TAX.KR_MAJOR_AMT           // 대주주(종목당 10억+) → KR 양도세 과세
        return { ...h, us, gainKRW, proceedsKRW, krMajor }
    })

    // KR: 양도세 0(비과세) — 단 대주주 종목은 과세 경고. 증권거래세 0.20%(매도금액).
    const krProceeds = ev.filter((h) => !h.us).reduce((a, b) => a + b.proceedsKRW, 0)
    const krTxnTax = krProceeds * TAX.KR_TXN
    const krMajorRows = ev.filter((h) => h.krMajor)

    // US: 양도소득 합산 → 250만 공제 → 누진(22% / 3억 초과 27.5%). 손실은 연내 통산(음수 합산).
    const usGainSum = ev.filter((h) => h.us).reduce((a, b) => a + b.gainKRW, 0)
    const usTaxable = Math.max(0, usGainSum - TAX.US_DEDUCT)
    const usCgt = usTaxable <= TAX.US_BRACKET
        ? usTaxable * TAX.US_CGT
        : TAX.US_BRACKET * TAX.US_CGT + (usTaxable - TAX.US_BRACKET) * TAX.US_CGT_HIGH

    const totalTax = usCgt + krTxnTax
    const totalGain = ev.reduce((a, b) => a + b.gainKRW, 0)

    const wrap: CSSProperties = {
        width: "100%", height: "100%", maxHeight: "100%", overflowY: "auto", overflowX: "hidden",
        background: "transparent", fontFamily: FONT, padding: pad, boxSizing: "border-box", color: C.ink,
    }
    const card: CSSProperties = {
        background: C.card, borderRadius: 16, padding: "16px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 12,
    }

    // 스켈레톤
    const shimmer: CSSProperties = {
        backgroundColor: isDark ? "#222a33" : "#e9edf1",
        backgroundImage: `linear-gradient(90deg, ${isDark ? "#222a33" : "#e9edf1"} 25%, ${isDark ? "#2d3742" : "#f3f5f7"} 37%, ${isDark ? "#222a33" : "#e9edf1"} 63%)`,
        backgroundSize: "800px 100%", animation: "vttShimmer 1.4s ease-in-out infinite",
    }
    const sk = (sw: number | string, sh: number, r: number): CSSProperties => ({ width: sw, height: sh, borderRadius: r, ...shimmer })

    const kv = (k: string, v: string, color?: string) => (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "6px 0", gap: 10 }}>
            <span style={{ fontSize: 12.5, color: C.sub, fontWeight: 600 }}>{k}</span>
            <span style={{ fontSize: 13.5, fontWeight: 800, color: color || C.ink, fontVariantNumeric: "tabular-nums" }}>{v}</span>
        </div>
    )

    return (
        <div ref={rootRef} style={wrap}>
            <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: narrow ? 18 : 20, fontWeight: 800, letterSpacing: "-0.5px" }}>예상 세금</div>
                <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 3 }}>
                    지금 전량 매도 가정 시 추정 · 사실·규칙 기반(자문 아님)
                </div>
            </div>

            {loading ? (
                <>
                    <style>{"@keyframes vttShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}"}</style>
                    <div style={card}>
                        <div style={sk(90, 12, 6)} />
                        <div style={{ ...sk(180, 28, 7), margin: "9px 0" }} />
                        <div style={sk(140, 13, 6)} />
                    </div>
                    {[0, 1, 2].map((k) => (
                        <div key={k} style={card}>
                            <div style={sk("50%", 14, 6)} />
                            <div style={{ ...sk("80%", 12, 5), marginTop: 9 }} />
                        </div>
                    ))}
                </>
            ) : (
                <>
                    {isDemo && (
                        <div style={{ background: C.vgS, color: C.ink, borderRadius: 12, padding: "11px 13px", fontSize: 12.5, fontWeight: 700, lineHeight: 1.5, marginTop: 12, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                            <span style={{ flex: 1, minWidth: 0 }}>샘플 기준 추정이에요. 로그인하면 내 보유종목으로 계산해요.</span>
                            {loginUrl && (
                                <a href={loginUrl} style={{ flexShrink: 0, background: C.vg, color: C.onAccent, borderRadius: 999, padding: "6px 14px", fontSize: 12.5, fontWeight: 800, textDecoration: "none" }}>로그인</a>
                            )}
                        </div>
                    )}

                    {/* 총 예상 세금 요약 */}
                    <div style={card}>
                        <div style={{ fontSize: 12, color: C.faint, fontWeight: 700 }}>예상 세금 합계 (매도 가정)</div>
                        <div style={{ fontSize: 27, fontWeight: 800, letterSpacing: "-1px", margin: "3px 0", color: totalTax > 0 ? C.ink : C.vg }}>
                            {won(totalTax)}
                        </div>
                        <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 600 }}>
                            평가손익 {totalGain >= 0 ? "+" : ""}{wonCompact(totalGain)} 기준 · 미국 양도세 {wonCompact(usCgt)} + 국내 거래세 {wonCompact(krTxnTax)}
                        </div>
                    </div>

                    {/* 국내(KR) */}
                    <div style={card}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                            <span style={{ fontSize: 15, fontWeight: 800 }}>🇰🇷 국내 주식</span>
                            <span style={{ fontSize: 11.5, fontWeight: 800, color: C.vg, background: C.vgS, padding: "3px 9px", borderRadius: 8 }}>양도세 0% · 비과세</span>
                        </div>
                        {kv("양도소득세", "0원 (비과세, 금투세 폐지 ~2029)", C.vg)}
                        {kv("증권거래세 0.20%", won(krTxnTax))}
                        {kv("매도금액 합계", wonCompact(krProceeds))}
                        {krMajorRows.length > 0 && (
                            <div style={{ background: C.warnS, color: C.warn, borderRadius: 10, padding: "9px 11px", fontSize: 11.5, fontWeight: 700, lineHeight: 1.5, marginTop: 8 }}>
                                ⚠ 대주주 가능성 — {krMajorRows.map((h) => h.name || h.ticker).join(", ")} (종목당 10억+ 보유 시 양도세 과세 대상). 시행령 공포일·정확 판정은 세무사 확인.
                            </div>
                        )}
                    </div>

                    {/* 미국(US) */}
                    <div style={card}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                            <span style={{ fontSize: 15, fontWeight: 800 }}>🇺🇸 해외 주식</span>
                            <span style={{ fontSize: 11.5, fontWeight: 800, color: C.warn, background: C.warnS, padding: "3px 9px", borderRadius: 8 }}>양도세 22%</span>
                        </div>
                        {kv("양도소득 합계", (usGainSum >= 0 ? "+" : "") + wonCompact(usGainSum), usGainSum >= 0 ? C.up : C.down)}
                        {kv("기본공제 (연)", "−" + wonCompact(TAX.US_DEDUCT))}
                        {kv("과세표준", wonCompact(usTaxable))}
                        {kv("예상 양도세", won(usCgt), usCgt > 0 ? C.ink : C.vg)}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>
                            22%(과표 3억↓)·27.5%(초과) · 손실은 연내 손익통산(이월공제 없음) · 환율 {FX}원/$ 가정
                        </div>
                    </div>

                    {/* 종목별 */}
                    <div style={{ ...card, paddingTop: 12 }}>
                        <div style={{ fontSize: 12.5, fontWeight: 800, marginBottom: 4 }}>종목별 평가손익</div>
                        {ev.sort((a, b) => Math.abs(b.gainKRW) - Math.abs(a.gainKRW)).map((h, i) => (
                            <div key={h.id || h.ticker} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 0", borderTop: i === 0 ? "none" : "1px solid " + C.line, gap: 10 }}>
                                <div style={{ minWidth: 0 }}>
                                    <div style={{ fontSize: 13.5, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                        {h.us ? "🇺🇸 " : "🇰🇷 "}{h.name || h.ticker}
                                    </div>
                                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 2 }}>
                                        {h.us ? "양도세 22% 대상" : (h.krMajor ? "대주주 과세 검토" : "비과세 · 거래세만")}
                                    </div>
                                </div>
                                <div style={{ textAlign: "right", flexShrink: 0 }}>
                                    <div style={{ fontSize: 13.5, fontWeight: 800, color: h.gainKRW > 0 ? C.up : h.gainKRW < 0 ? C.down : C.faint, fontVariantNumeric: "tabular-nums" }}>
                                        {h.gainKRW >= 0 ? "+" : ""}{wonCompact(h.gainKRW)}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* horizon / 교육 */}
                    <div style={{ ...card, background: C.vgS }}>
                        <div style={{ fontSize: 12.5, fontWeight: 800, marginBottom: 7 }}>알아두기</div>
                        {[
                            "국내 상장주식 양도세 = 비과세 (금투세 폐지 2024-12-10, 2029년까지 유지 기조)",
                            "대주주(종목당 보유 10억+) 는 국내도 양도세 과세 — 시행령 공포일 확인 필요",
                            "해외주식 양도세 = 22% (과표 3억↓), 연 250만 기본공제(국가 합산), 손익 연내통산",
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
        </div>
    )
}

addPropertyControls(PublicTaxTracker, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: "https://project-yw131.vercel.app" },
    loginUrl: { type: ControlType.String, title: "Login URL", defaultValue: "/login" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

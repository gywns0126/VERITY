import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 옵션 시장 렌즈 — VERITY 공개 터미널 (AlphaNest, TIDE 보조). ETF 자금흐름(PublicETFFlow)처럼 독립 "렌즈".
 * 디자인 = 토스식 미니멀: 무채색 위주 + 얇은 구분선, 색배경·외곽선·이모지 없음.
 *
 * 🚨 차별 각도: BTC/ETH 옵션 시장의 내재변동성(DVOL)·실현변동성·풋콜 OI 비율·맥스페인(만기인력 행사가).
 *   DVOL = Deribit 내재변동성 지수(시장 공포/기대). 실현변동성 = 과거 실제 변동성(비교 baseline).
 *   풋콜 OI 비율 = 미결제약정 기준 풋/콜 — >1 이면 풋 우위(역발상 신호 보조 단서). 맥스페인 = 만기 시 옵션 손실 최대 행사가(인력).
 * 🚨 RULE 7: DVOL·풋콜·맥스페인 = Deribit 1차 사실(풋콜·맥스페인은 자체 산출). 점수·추천 0.
 * 데이터 = crypto_options.json (단일 writer, blob 발행). 테마 = body[data-framer-theme] 자가 추종.
 */

interface Props {
    dataUrl: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/crypto_options.json"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#f0f1f3", up: "#f04452", down: "#3182f6",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#222730", up: "#f04452", down: "#5b9bff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const CACHE_KEY = "verity_crypto_options_cache"

const DEMO = {
    ok: true,
    btc: {
        dvol: 41.6, hist_vol_pct: 38.2, put_call_ratio_oi: 0.62,
        max_pain_strike: 63500, max_pain_expiry: "2026-06-27", total_oi: 412800,
        underlying_price: 64820,
    },
    eth: {
        dvol: 55.9, hist_vol_pct: 51.4, put_call_ratio_oi: 0.71,
        max_pain_strike: 3450, max_pain_expiry: "2026-06-27", total_oi: 1284500,
        underlying_price: 3512,
    },
}

function fmtUSD(v: any): string {
    const n = Number(v)
    if (!isFinite(n)) return "—"
    return "$" + Math.round(n).toLocaleString("en-US")
}
function fmtPct(v: any, digits = 1): string {
    const n = Number(v)
    if (!isFinite(n)) return "—"
    return n.toFixed(digits) + "%"
}
function fmtRatio(v: any): string {
    const n = Number(v)
    if (!isFinite(n)) return "—"
    return n.toFixed(2)
}
function fmtExpiry(iso: any): string {
    if (!iso) return ""
    try {
        const d = new Date(String(iso))
        if (isNaN(d.getTime())) return String(iso)
        const mm = String(d.getMonth() + 1).padStart(2, "0")
        const dd = String(d.getDate()).padStart(2, "0")
        return `${mm}/${dd}`
    } catch {
        return String(iso)
    }
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function CryptoOptionsPublic(props: Props) {
    const { dataUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    useEffect(() => {
        if (onCanvas) return
        const read = () => {
            const t = typeof document !== "undefined" && document.body ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [data, setData] = useState<any>(onCanvas ? DEMO : null)

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    useEffect(() => {
        if (onCanvas || !dataUrl) return
        let alive = true
        // cache-fallback: 직전 성공 응답을 먼저 그려두기
        try {
            const cached = typeof localStorage !== "undefined" ? localStorage.getItem(CACHE_KEY) : null
            if (cached) {
                const d = JSON.parse(cached)
                if (alive && d && (d.btc || d.eth)) setData(d)
            }
        } catch {}
        fetch(dataUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d || !(d.btc || d.eth)) return
                setData(d)
                try { if (typeof localStorage !== "undefined") localStorage.setItem(CACHE_KEY, JSON.stringify(d)) } catch {}
            })
            .catch(() => {})
        return () => { alive = false }
    }, [dataUrl, onCanvas])

    const narrow = w > 0 && w < 560
    const loading = !data

    const coins = useMemo(() => {
        if (!data) return [] as any[]
        const out: any[] = []
        if (data.btc) out.push({ sym: "BTC", name: "비트코인", o: data.btc })
        if (data.eth) out.push({ sym: "ETH", name: "이더리움", o: data.eth })
        return out
    }, [data])

    const skBase = isDark ? "#1e242c" : "#edeff2"
    const skHi = isDark ? "#2a313b" : "#f5f6f8"
    const sk = (bw: any, bh: number, br = 7): CSSProperties => ({
        width: bw, height: bh, borderRadius: br, background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%", animation: "copShimmer 1.4s ease-in-out infinite", flexShrink: 0,
    })

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT,
        padding: narrow ? 16 : 22, boxSizing: "border-box", color: C.ink,
    }
    const card: CSSProperties = {
        background: C.card, borderRadius: 18, padding: narrow ? 16 : 20, boxSizing: "border-box",
    }

    if (loading) {
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes copShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ ...sk(110, 12, 6), marginBottom: 12 }} />
                <div style={{ ...sk("64%", 24, 8), marginBottom: 22 }} />
                <div style={{ ...sk("100%", 150, 18), marginBottom: 12 }} />
                <div style={sk("100%", 150, 18)} />
            </div>
        )
    }

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>옵션 시장</div>
            <div style={{ fontSize: narrow ? 20 : 23, fontWeight: 700, color: C.ink, letterSpacing: "-0.5px", marginTop: 6 }}>Deribit IV·풋콜·맥스페인</div>
            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 7 }}>
                내재변동성(DVOL)·실현변동성·풋콜 OI 비율·맥스페인 · Deribit
            </div>

            {coins.map((c, idx) => {
                const o = c.o || {}
                const dvol = Number(o.dvol)
                const hv = Number(o.hist_vol_pct)
                const pcr = Number(o.put_call_ratio_oi)
                const ivPremium = isFinite(dvol) && isFinite(hv) ? dvol - hv : null
                // 풋콜>1 = 풋 우위(역발상 의미) 절제된 색만. DVOL/실현변동성은 방향 의미 약하니 무채색.
                const pcrCol = isFinite(pcr) ? (pcr > 1 ? C.up : C.ink) : C.faint
                return (
                    <div key={c.sym} style={{ ...card, marginTop: idx === 0 ? 18 : 12 }}>
                        {/* 코인 헤더 */}
                        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 16 }}>
                            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                                <div style={{ fontSize: 15, fontWeight: 700, color: C.ink }}>{c.sym}</div>
                                <div style={{ fontSize: 12, fontWeight: 500, color: C.faint }}>{c.name}</div>
                            </div>
                            {isFinite(Number(o.underlying_price)) && (
                                <div style={{ fontSize: 13, fontWeight: 600, color: C.sub, fontVariantNumeric: "tabular-nums" }}>{fmtUSD(o.underlying_price)}</div>
                            )}
                        </div>

                        {/* DVOL */}
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "11px 0" }}>
                            <div style={{ fontSize: 13, fontWeight: 500, color: C.sub }}>내재변동성 (DVOL)</div>
                            <div style={{ fontSize: 15, fontWeight: 700, color: C.ink, fontVariantNumeric: "tabular-nums" }}>{fmtPct(dvol)}</div>
                        </div>

                        {/* 실현변동성 */}
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "11px 0", borderTop: `1px solid ${C.line}` }}>
                            <div style={{ fontSize: 13, fontWeight: 500, color: C.sub }}>실현변동성{ivPremium != null ? <span style={{ color: C.faint, fontWeight: 500 }}>{` · IV−RV ${ivPremium > 0 ? "+" : ""}${ivPremium.toFixed(1)}p`}</span> : ""}</div>
                            <div style={{ fontSize: 15, fontWeight: 600, color: C.ink, fontVariantNumeric: "tabular-nums" }}>{fmtPct(hv)}</div>
                        </div>

                        {/* 풋콜 OI 비율 */}
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "11px 0", borderTop: `1px solid ${C.line}` }}>
                            <div style={{ fontSize: 13, fontWeight: 500, color: C.sub }}>풋콜 OI 비율</div>
                            <div style={{ textAlign: "right" }}>
                                <span style={{ fontSize: 15, fontWeight: 700, color: pcrCol, fontVariantNumeric: "tabular-nums" }}>{fmtRatio(pcr)}</span>
                                {isFinite(pcr) && (
                                    <span style={{ fontSize: 11.5, fontWeight: 500, color: C.faint, marginLeft: 6 }}>{pcr > 1 ? "풋 우위" : "콜 우위"}</span>
                                )}
                            </div>
                        </div>

                        {/* 맥스페인 */}
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "11px 0", borderTop: `1px solid ${C.line}` }}>
                            <div style={{ fontSize: 13, fontWeight: 500, color: C.sub }}>맥스페인 (만기인력)</div>
                            <div style={{ textAlign: "right" }}>
                                <span style={{ fontSize: 15, fontWeight: 600, color: C.ink, fontVariantNumeric: "tabular-nums" }}>{fmtUSD(o.max_pain_strike)}</span>
                                {o.max_pain_expiry && (
                                    <span style={{ fontSize: 11.5, fontWeight: 500, color: C.faint, marginLeft: 6 }}>만기 {fmtExpiry(o.max_pain_expiry)}</span>
                                )}
                            </div>
                        </div>
                    </div>
                )
            })}

            {/* 면책 */}
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 500, marginTop: 18, lineHeight: 1.6 }}>
                DVOL·풋콜·맥스페인은 Deribit 사실이에요(풋콜·맥스페인은 자체 산출).
            </div>
        </div>
    )
}

addPropertyControls(CryptoOptionsPublic, {
    dataUrl: { type: ControlType.String, title: "Options URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

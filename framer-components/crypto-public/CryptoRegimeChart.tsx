import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 레짐 추이 라인 — 공개형 TIDE 유리박스 시각화 (우리 엣지의 그림).
 * 종합 판독(net_score)을 시간축으로 + BTC 가격 오버레이 + 판독 색 마커. 누적될수록 강해지는 시계열.
 * AlphaNest 결: 흰 카드/얇은 라인/외곽선 없음. 방향색 = 한국 관례(위험선호=빨강/위험회피=파랑).
 *
 * 데이터 = crypto_regime.json (trail[] + track_record). RULE 7: 가설 v0, N<30 통계 무의미.
 * 다크 = body[data-framer-theme] 자가추종. 매매 미연결(관측-only).
 */

interface Props { dataUrl: string; dark: boolean }
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/crypto_regime.json"
const CACHE_KEY = "verity_crypto_regimechart_cache"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#f0f1f3", grid: "#e9ecef", up: "#f04452", down: "#3182f6", btc: "#c0c6cf",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#222730", grid: "#222932", up: "#f04452", down: "#5b9bff", btc: "#3a424d",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const NUM: CSSProperties = { fontVariantNumeric: "tabular-nums" }

function callColor(c: string, C: typeof LIGHT): string { return c === "risk_on" ? C.up : c === "risk_off" ? C.down : C.faint }
function callKo(c: string): string { return c === "risk_on" ? "위험선호" : c === "risk_off" ? "위험회피" : "중립" }

const DEMO = {
    collected_at: "demo",
    composite: { call: "neutral", net_score: -1 },
    trail: [
        { date: "2026-06-13", call: "risk_off", net_score: -3, btc_price: 64200 },
        { date: "2026-06-15", call: "risk_off", net_score: -2, btc_price: 63100 },
        { date: "2026-06-17", call: "neutral", net_score: -1, btc_price: 63600 },
        { date: "2026-06-19", call: "neutral", net_score: 0, btc_price: 64800 },
        { date: "2026-06-21", call: "risk_on", net_score: 2, btc_price: 66200 },
        { date: "2026-06-23", call: "neutral", net_score: -1, btc_price: 63200 },
        { date: "2026-06-24", call: "neutral", net_score: -1, btc_price: 62700 },
    ],
    track_record: { buckets: [{ horizon_days: 7, n: 0, hit_rate: null, label: "통계 무의미 (N<30)" }] },
}

export default function CryptoRegimeChart(props: Props) {
    const { dataUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    const [data, setData] = useState<any>(onCanvas ? DEMO : null)
    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)

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
        if (typeof localStorage !== "undefined") {
            try { const c = localStorage.getItem(CACHE_KEY); if (c) { const o = JSON.parse(c); if (o && o.trail) setData(o) } } catch {}
        }
        fetch(dataUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d) return
                setData(d)
                if (typeof localStorage !== "undefined") { try { localStorage.setItem(CACHE_KEY, JSON.stringify(d)) } catch {} }
            })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas, dataUrl])

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT
    const narrow = w > 0 && w < 560

    const trail = useMemo(() => {
        const t = data && Array.isArray(data.trail) ? data.trail : []
        return t.filter((e: any) => e && e.net_score != null)
    }, [data])
    const bkt7 = useMemo(() => {
        const b = data && data.track_record && Array.isArray(data.track_record.buckets) ? data.track_record.buckets : []
        return b.find((x: any) => x.horizon_days === 7) || b[0] || null
    }, [data])

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, padding: narrow ? 16 : 22, boxSizing: "border-box", color: C.ink }
    const card: CSSProperties = { background: C.card, borderRadius: 18, padding: narrow ? 16 : 20, boxSizing: "border-box" }

    if (!data) {
        const skBase = isDark ? "#1e242c" : "#edeff2"
        const skHi = isDark ? "#2a313b" : "#f5f6f8"
        const sk = (bw: any, bh: number, br = 7): CSSProperties => ({ width: bw, height: bh, borderRadius: br, background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "vrcShimmer 1.4s ease-in-out infinite" })
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes vrcShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ ...sk(110, 12, 6), marginBottom: 12 }} />
                <div style={{ ...sk("55%", 24, 8), marginBottom: 22 }} />
                <div style={sk("100%", 220, 18)} />
            </div>
        )
    }

    // 차트 좌표 — net_score(±NMAX) + BTC 정규화 오버레이
    const VW = 600, VH = 200, padL = 8, padR = 8, padT = 14, padB = 18
    const n = trail.length
    const nets = trail.map((e: any) => Number(e.net_score))
    const NMAX = Math.max(3, ...nets.map((v: number) => Math.abs(v)))
    const xAt = (i: number) => padL + (n <= 1 ? 0.5 : i / (n - 1)) * (VW - padL - padR)
    const yNet = (v: number) => padT + (1 - (v + NMAX) / (2 * NMAX)) * (VH - padT - padB)
    const btcVals = trail.map((e: any) => Number(e.btc_price)).filter((v: number) => isFinite(v) && v > 0)
    const bMin = btcVals.length ? Math.min(...btcVals) : 0
    const bMax = btcVals.length ? Math.max(...btcVals) : 1
    const yBtc = (v: number) => { const span = bMax - bMin || 1; return padT + (1 - (v - bMin) / span) * (VH - padT - padB) }

    const netPath = trail.map((e: any, i: number) => (i === 0 ? "M" : "L") + xAt(i).toFixed(1) + " " + yNet(Number(e.net_score)).toFixed(1)).join(" ")
    const btcPath = trail.map((e: any, i: number) => { const v = Number(e.btc_price); return (i === 0 ? "M" : "L") + xAt(i).toFixed(1) + " " + (isFinite(v) && v > 0 ? yBtc(v) : yNet(0)).toFixed(1) }).join(" ")

    const last = trail.length ? trail[trail.length - 1] : null
    const enough = n >= 2

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>레짐 추이 · 유리박스</div>
            <div style={{ fontSize: narrow ? 20 : 23, fontWeight: 700, color: C.ink, letterSpacing: "-0.5px", marginTop: 6 }}>판독 history</div>
            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 7, ...NUM }}>
                종합 net 점수 추이 · BTC 오버레이 · {n}개 기록{last ? ` · 최근 ${callKo(last.call)}` : ""}
            </div>

            {/* 차트 카드 */}
            <div style={{ ...card, marginTop: 18 }}>
                {enough ? (
                    <svg viewBox={`0 0 ${VW} ${VH}`} width="100%" height={narrow ? 180 : 210} preserveAspectRatio="none" style={{ display: "block", overflow: "visible" }}>
                        {/* +2 / 0 / -2 기준선 */}
                        <line x1={padL} y1={yNet(2)} x2={VW - padR} y2={yNet(2)} stroke={C.up} strokeWidth="1" strokeDasharray="2 4" opacity="0.5" />
                        <line x1={padL} y1={yNet(0)} x2={VW - padR} y2={yNet(0)} stroke={C.grid} strokeWidth="1" />
                        <line x1={padL} y1={yNet(-2)} x2={VW - padR} y2={yNet(-2)} stroke={C.down} strokeWidth="1" strokeDasharray="2 4" opacity="0.5" />
                        {/* BTC 오버레이 (faint) */}
                        {btcVals.length >= 2 && <path d={btcPath} fill="none" stroke={C.btc} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />}
                        {/* net 라인 */}
                        <path d={netPath} fill="none" stroke={C.sub} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
                        {/* 판독 색 마커 */}
                        {trail.map((e: any, i: number) => (
                            <circle key={i} cx={xAt(i)} cy={yNet(Number(e.net_score))} r="3.2" fill={callColor(e.call, C)} stroke={C.card} strokeWidth="1.2" />
                        ))}
                    </svg>
                ) : (
                    <div style={{ padding: "28px 0", textAlign: "center" }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: C.ink }}>추이 누적 중 (기록 {n}개)</div>
                        <div style={{ fontSize: 12, color: C.sub, fontWeight: 500, marginTop: 6, lineHeight: 1.55 }}>판독을 매일 1점씩 기록해요. 점이 쌓이면 레짐 추이와 BTC 대조 그래프가 채워져요.</div>
                    </div>
                )}

                {/* 범례 */}
                {enough && (
                    <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 12, fontSize: 10.5, color: C.faint, fontWeight: 600 }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 9, height: 9, borderRadius: "50%", background: C.up }} /> 위험선호</span>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 9, height: 9, borderRadius: "50%", background: C.down }} /> 위험회피</span>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 12, height: 2, background: C.btc }} /> BTC</span>
                        <span style={{ marginLeft: "auto", ...NUM }}>net ±{NMAX} · ±2=레짐 임계</span>
                    </div>
                )}
            </div>

            {/* 채점 요약 + 면책 */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
                <div style={{ fontSize: 12.5, fontWeight: 600, color: C.sub }}>
                    7일 적중률 <span style={{ ...NUM, color: C.ink, fontWeight: 700 }}>{bkt7 && bkt7.hit_rate != null ? (Number(bkt7.hit_rate) * 100).toFixed(0) + "%" : "—"}</span>
                    <span style={{ color: C.faint, marginLeft: 6 }}>N={bkt7 ? bkt7.n : 0}</span>
                </div>
                <span style={{ fontSize: 11, color: C.faint, fontWeight: 500 }}>{bkt7 ? bkt7.label || "" : ""}</span>
            </div>
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 500, marginTop: 10, lineHeight: 1.6 }}>
                판독은 자체 기준 v0(가설)이에요. 적중은 판독 후 BTC 실현수익과 대조해 매기며, 표본이 쌓인 뒤(N≥30) 의미가 생겨요.
            </div>
        </div>
    )
}

addPropertyControls(CryptoRegimeChart, {
    dataUrl: { type: ControlType.String, title: "Regime URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 코인 레짐 종합 — 공개형 TIDE 리드 카드 (10피드 → 하나의 판독 + 유리박스 채점).
 * AlphaNest 정본 디자인 결(PublicETFFlow): 무채색 + 얇은 구분선, 색배경·외곽선·이모지 없음.
 *
 * 우리 엣지 = 데이터 양 아닌 종합. ① 한 판독 + ② 왜(6 드라이버보드) + ③ forward 자가채점 trail.
 * 운영자 TIDE(TSM/포지션)와 분리된 공개 희석 face — 관측-only, 매매 미연결.
 *
 * 데이터 = crypto_regime.json. composite{call,net_score,active_dims} · dimensions[6] · track_record
 * RULE 7: 종합 = 자체 기준 v0 가설(사전등록 2026-06-24, 임계 변경 1회+PM). hit rate N 병기, N<30 통계 무의미.
 * RULE 6: LLM 0(결정론 tally). 방향색 = 한국 관례(위험선호=빨강 / 위험회피=파랑). 다크 = body[data-framer-theme].
 */

interface Props { dataUrl: string; dark: boolean }
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/crypto_regime.json"
const CACHE_KEY = "verity_crypto_regime_cache"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#f0f1f3", up: "#f04452", down: "#3182f6",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#222730", up: "#f04452", down: "#5b9bff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const NUM: CSSProperties = { fontVariantNumeric: "tabular-nums" }

function num(v: any): number | null { const n = Number(v); return isFinite(n) ? n : null }
// 적중률 Wilson 95% 신뢰구간 (RULE 7 — hit_rate 단독 게재 금지). 작은 N=넓은 구간 그대로 노출.
function wilsonCI95(hitRate: any, n: any): string | null {
    const p0 = Number(hitRate), nn = Number(n)
    if (!isFinite(p0) || !isFinite(nn) || nn < 1) return null
    const z = 1.96, p = Math.max(0, Math.min(1, p0)), denom = 1 + (z * z) / nn
    const center = (p + (z * z) / (2 * nn)) / denom
    const half = (z * Math.sqrt((p * (1 - p)) / nn + (z * z) / (4 * nn * nn))) / denom
    return (Math.max(0, center - half) * 100).toFixed(0) + "–" + (Math.min(1, center + half) * 100).toFixed(0) + "%p"
}
function fmtSignedPct(v: any, digits = 2): string {
    const n = Number(v); if (!isFinite(n)) return "—"
    return (n > 0 ? "+" : "") + (n * 100).toFixed(digits) + "%"
}
function fmtUsd(v: any): string {
    const n = Number(v)
    if (!isFinite(n) || n === 0) return "—"
    const a = Math.abs(n), s = n < 0 ? "−" : "+"
    if (a >= 1e9) return s + "$" + (a / 1e9).toFixed(1) + "B"
    if (a >= 1e6) return s + "$" + (a / 1e6).toFixed(0) + "M"
    if (a >= 1e3) return s + "$" + (a / 1e3).toFixed(0) + "K"
    return s + "$" + a.toFixed(0)
}
function callKo(c: string): string { return c === "risk_on" ? "위험선호" : c === "risk_off" ? "위험회피" : "중립" }
function callColor(c: string, C: typeof LIGHT): string { return c === "risk_on" ? C.up : c === "risk_off" ? C.down : C.faint }
function readColor(read: string, active: boolean, C: typeof LIGHT): string {
    if (!active) return C.faint
    if (read === "on") return C.up
    if (read === "off") return C.down
    return C.faint
}
function readKo(read: string, active: boolean): string {
    if (!active) return read
    return read === "on" ? "위험선호" : read === "off" ? "위험회피" : "중립"
}
function driverSummary(name: string, d: Record<string, any>): string {
    if (!d) return ""
    if (name === "심리") { const f = num(d.fng); return f != null ? `공포·탐욕 ${f.toFixed(0)}` : "" }
    if (name === "포지셔닝") {
        const p: string[] = []
        if (d.funding_signal) p.push(`펀딩 ${d.funding_signal === "long_overheat" ? "과열" : d.funding_signal === "short_overheat" ? "숏과열" : "중립"}`)
        if (d.put_call_oi != null) p.push(`풋콜 ${Number(d.put_call_oi).toFixed(2)}`)
        if (d.long_short_ratio != null) p.push(`롱숏 ${Number(d.long_short_ratio).toFixed(2)}`)
        return p.join(" · ")
    }
    if (name === "자금흐름") return d.combined_net_inflow_usd != null ? `ETF ${fmtUsd(d.combined_net_inflow_usd)}` : ""
    if (name === "추세") { const c = num(d.btc_change_pct_7d); return c != null ? `BTC 7일 ${c > 0 ? "+" : ""}${c.toFixed(1)}%` : "" }
    if (name === "유동성") { const s = num(d.ssr); return s != null ? `SSR ${s.toFixed(2)} · 이력 누적` : "이력 누적" }
    if (name === "펀더멘털·온체인") { const tp = d.top_protocol_fees_24h; return tp && tp.name ? `${tp.name} 수수료 ${fmtUsd(tp.fees_24h)} · 브릿지` : "TIDE 브릿지 대기" }
    return ""
}

const DEMO = {
    collected_at: "demo",
    composite: { call: "neutral", net_score: -1, active_dims: 4 },
    dimensions: [
        { name: "심리", read: "on", active: true, drivers: { fng: 17 } },
        { name: "포지셔닝", read: "neutral", active: true, drivers: { funding_signal: "neutral", put_call_oi: 0.62, long_short_ratio: 1.58 } },
        { name: "자금흐름", read: "off", active: true, drivers: { combined_net_inflow_usd: -134210884 } },
        { name: "추세", read: "off", active: true, drivers: { btc_change_pct_7d: -4.8 } },
        { name: "유동성", read: "누적 중", active: false, drivers: { ssr: 4.83 } },
        { name: "펀더멘털·온체인", read: "브릿지 대기", active: false, drivers: { top_protocol_fees_24h: { name: "Tether", fees_24h: 16137742 } } },
    ],
    track_record: { buckets: [{ horizon_days: 7, n: 0, hit_rate: null, label: "통계 무의미 (N<30)" }] },
    _disclaimer: "가설 v0 · 자체 기준 · 관측-only · 매매 미연결",
}

export default function CryptoRegimeSynthesis(props: Props) {
    const { dataUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    const [data, setData] = useState<any>(onCanvas ? DEMO : null)
    const [cacheTs, setCacheTs] = useState<number | null>(null)
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
            try { const c = localStorage.getItem(CACHE_KEY); if (c) { const o = JSON.parse(c); if (o && o.data) { setData(o.data); setCacheTs(o.ts || null) } } } catch {}
        }
        fetch(dataUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d) return
                setData(d); setCacheTs(null)
                if (typeof localStorage !== "undefined") { try { localStorage.setItem(CACHE_KEY, JSON.stringify({ data: d, ts: Date.now() })) } catch {} }
            })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas, dataUrl])

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT
    const narrow = w > 0 && w < 560

    const comp = data && data.composite ? data.composite : null
    const dims: any[] = useMemo(() => (data && Array.isArray(data.dimensions) ? data.dimensions : []), [data])
    const bkt7 = useMemo(() => {
        const b = data && data.track_record && Array.isArray(data.track_record.buckets) ? data.track_record.buckets : []
        return b.find((x: any) => x.horizon_days === 7) || b[0] || null
    }, [data])

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, padding: narrow ? 16 : 22, boxSizing: "border-box", color: C.ink }
    const card: CSSProperties = { background: C.card, borderRadius: 18, padding: narrow ? 16 : 20, boxSizing: "border-box" }

    if (!data || !comp) {
        const skBase = isDark ? "#1e242c" : "#edeff2"
        const skHi = isDark ? "#2a313b" : "#f5f6f8"
        const sk = (bw: any, bh: number, br = 7): CSSProperties => ({ width: bw, height: bh, borderRadius: br, background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "vrsShimmer 1.4s ease-in-out infinite" })
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes vrsShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ ...sk(110, 12, 6), marginBottom: 12 }} />
                <div style={{ ...sk("50%", 26, 8), marginBottom: 22 }} />
                <div style={{ ...sk("100%", 260, 18), marginBottom: 12 }} />
                <div style={sk("100%", 72, 18)} />
            </div>
        )
    }

    const call = comp.call || "neutral"
    const cCol = callColor(call, C)
    const net = num(comp.net_score)

    return (
        <div ref={rootRef} style={wrap}>
            {cacheTs != null && <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginBottom: 8 }}>오프라인 캐시</div>}

            {/* 헤더 — 한 판독 */}
            <div style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>코인 레짐 종합</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginTop: 6, flexWrap: "wrap" }}>
                <span style={{ fontSize: narrow ? 26 : 30, fontWeight: 700, color: cCol, letterSpacing: "-0.6px" }}>{callKo(call)}</span>
                <span style={{ fontSize: 13.5, fontWeight: 600, color: C.sub, ...NUM }}>net {net != null ? (net > 0 ? "+" : "") + net : "—"} · {comp.active_dims}/6 차원</span>
            </div>
            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 7 }}>
                10개 신호를 하나로 종합한 오늘의 판독 · 관측-only{data.collected_at ? ` · ${String(data.collected_at).slice(0, 10)}` : ""}
            </div>

            {/* 드라이버보드 — 왜 */}
            <div style={{ ...card, marginTop: 18, paddingTop: 6, paddingBottom: 6 }}>
                {dims.map((dim: any, i: number) => {
                    const active = !!dim.active
                    const col = readColor(dim.read, active, C)
                    return (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "13px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}`, opacity: active ? 1 : 0.6 }}>
                            <div style={{ width: narrow ? 78 : 92, flexShrink: 0, fontSize: 13.5, fontWeight: 600, color: C.ink }}>{dim.name}</div>
                            <div style={{ flex: 1, minWidth: 0, fontSize: 12, fontWeight: 500, color: C.faint, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", ...NUM }}>{driverSummary(dim.name, dim.drivers)}</div>
                            <div style={{ flexShrink: 0, fontSize: 13, fontWeight: 600, color: col, ...NUM }}>{readKo(dim.read, active)}</div>
                        </div>
                    )
                })}
            </div>

            {/* 유리박스 — forward 채점 */}
            <div style={{ ...card, marginTop: 12, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 700, color: C.ink }}>유리박스 · 7일 forward 채점</div>
                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 4, lineHeight: 1.5 }}>판독을 매일 기록하고 BTC 실현수익과 대조해요. 표본이 쌓일수록 신뢰가 생겨요.</div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: narrow ? 14 : 20, flexShrink: 0 }}>
                    <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 17, fontWeight: 700, color: C.ink, ...NUM }}>{bkt7 && bkt7.hit_rate != null ? (Number(bkt7.hit_rate) * 100).toFixed(0) + "%" : "—"}</div>
                        <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 500, marginTop: 2 }}>적중률</div>
                        {bkt7 && wilsonCI95(bkt7.hit_rate, bkt7.n) ? <div style={{ fontSize: 9.5, color: C.faint, fontWeight: 600, marginTop: 1, ...NUM }}>95% CI {wilsonCI95(bkt7.hit_rate, bkt7.n)}</div> : null}
                    </div>
                    <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 17, fontWeight: 700, color: bkt7 && Number(bkt7.mean_realized_return) < 0 ? C.down : C.ink, ...NUM }}>{bkt7 ? fmtSignedPct(bkt7.mean_realized_return) : "—"}</div>
                        <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 500, marginTop: 2 }}>기대값</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 17, fontWeight: 700, color: C.ink, ...NUM }}>{bkt7 ? bkt7.n : 0}</div>
                        <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 500, marginTop: 2 }}>표본 N</div>
                    </div>
                </div>
            </div>

            {/* 면책 */}
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 500, marginTop: 18, lineHeight: 1.6 }}>
                종합은 6개 차원을 가중치 없이 투명하게 합산해요(곡선맞추기 없음). 드라이버 수치는 사실, 판독은 자체 기준 v0(가설)이에요. {bkt7 ? bkt7.label || "" : ""} · 자체 채점은 표본이 쌓인 뒤(N≥30) 의미가 생겨요.
            </div>
        </div>
    )
}

addPropertyControls(CryptoRegimeSynthesis, {
    dataUrl: { type: ControlType.String, title: "Regime URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

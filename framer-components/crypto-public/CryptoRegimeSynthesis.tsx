import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 코인 레짐 종합 — 공개형 TIDE 리드 카드 (10피드 → 하나의 판독 + 유리박스 채점).
 *
 * 우리 엣지 = 데이터 양 아닌 종합. CoinGecko·LLM 못 가지는 자기 자산:
 *   ① 한 판독(risk-on/off/neutral) + ② 왜(6 차원 드라이버보드) + ③ forward 자가채점 trail.
 * 운영자 TIDE(TSM 전략/포지션)와 분리된 공개 희석 face — 관측-only, 매매 미연결.
 *
 * 데이터 = crypto_regime.json (crypto_collect 종합단계 → 공유 Vercel Blob).
 *   composite{call,net_score,active_dims} · dimensions[6]{name,read,active,drivers} · track_record
 *
 * 🚨 RULE 7: 종합 score·분류 = 자체 기준 v0 가설(사전등록 2026-06-24). 임계 변경 1회+PM 승인.
 *            hit rate 단독 금지(N·평균수익 병기, N<30 통계 무의미). 드라이버 raw=사실/색=가설.
 * 🚨 RULE 6: LLM·서술 합성 0. 결정론 tally(가중치 없음).
 * 다크모드 = body[data-framer-theme] 자가감지. onCanvas = 데모.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", on: "#15c47e", off: "#f04452", neutral: "#8b95a1", warn: "#ff9500",
    track: "#eef1f4", muted: "#aab2bd", dim: "#f7f9fa",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", on: "#3ddc97", off: "#ff6b76", neutral: "#828d9b", warn: "#ffb454",
    track: "#222a33", muted: "#5a6473", dim: "#12171d",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const MONO: CSSProperties = { fontFamily: "'SF Mono','JetBrains Mono','Menlo',monospace", fontVariantNumeric: "tabular-nums" }
const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const CACHE_KEY = "verity_crypto_regime_cache"

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function alpha(hex: string, a: number): string {
    const h = hex.replace("#", "")
    const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16)
    return `rgba(${r},${g},${b},${a.toFixed(3)})`
}
function num(v: any): number | null {
    const n = Number(v)
    return isFinite(n) ? n : null
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

// call → 한글 + 색
function callKo(call: string): string {
    if (call === "risk_on") return "위험선호"
    if (call === "risk_off") return "위험회피"
    return "중립"
}
function callColor(call: string, C: typeof LIGHT): string {
    if (call === "risk_on") return C.on
    if (call === "risk_off") return C.off
    return C.neutral
}
// dimension read → 색 + 한글
function readColor(read: string, active: boolean, C: typeof LIGHT): string {
    if (!active) return C.muted
    if (read === "on") return C.on
    if (read === "off") return C.off
    return C.neutral
}
function readKo(read: string, active: boolean): string {
    if (!active) return read  // "누적 중" / "브릿지 대기"
    if (read === "on") return "위험선호"
    if (read === "off") return "위험회피"
    return "중립"
}

// 차원별 드라이버 한 줄 요약 (raw 사실)
function driverSummary(name: string, d: Record<string, any>): string {
    if (!d) return ""
    if (name === "심리") {
        const f = num(d.fng)
        return f != null ? `FNG ${f.toFixed(0)}` : ""
    }
    if (name === "포지셔닝") {
        const parts: string[] = []
        if (d.funding_signal) parts.push(`펀딩 ${d.funding_signal === "long_overheat" ? "과열" : d.funding_signal === "short_overheat" ? "숏과열" : "중립"}`)
        if (d.put_call_oi != null) parts.push(`풋콜 ${Number(d.put_call_oi).toFixed(2)}`)
        if (d.long_short_ratio != null) parts.push(`롱숏 ${Number(d.long_short_ratio).toFixed(2)}`)
        return parts.join(" · ")
    }
    if (name === "자금흐름") {
        return d.combined_net_inflow_usd != null ? `ETF ${fmtUsd(d.combined_net_inflow_usd)}` : ""
    }
    if (name === "추세") {
        const c = num(d.btc_change_pct_7d)
        return c != null ? `BTC 7d ${c > 0 ? "+" : ""}${c.toFixed(1)}%` : ""
    }
    if (name === "유동성") {
        const s = num(d.ssr)
        return s != null ? `SSR ${s.toFixed(2)} (이력 누적)` : "이력 누적"
    }
    if (name === "펀더멘털·온체인") {
        const tp = d.top_protocol_fees_24h
        return tp && tp.name ? `${tp.name} 수수료 ${fmtUsd(tp.fees_24h)} (브릿지)` : "TIDE 브릿지 대기"
    }
    return ""
}

const DEMO = {
    collected_at: "demo",
    composite: { call: "neutral", net_score: -1, active_dims: 4, rule: "net≥+2 risk_on / ≤−2 risk_off / else neutral" },
    dimensions: [
        { name: "심리", read: "on", active: true, drivers: { fng: 17, search_trend_pct: -8.7 } },
        { name: "포지셔닝", read: "neutral", active: true, drivers: { funding_signal: "neutral", put_call_oi: 0.615, long_short_ratio: 1.58 } },
        { name: "자금흐름", read: "off", active: true, drivers: { combined_net_inflow_usd: -134210884 } },
        { name: "추세", read: "off", active: true, drivers: { btc_change_pct_7d: -4.8 } },
        { name: "유동성", read: "누적 중", active: false, drivers: { ssr: 4.83 } },
        { name: "펀더멘털·온체인", read: "브릿지 대기", active: false, drivers: { top_protocol_fees_24h: { name: "Tether", fees_24h: 16137742 } } },
    ],
    track_record: { buckets: [{ horizon_days: 7, n: 0, hit_rate: null, mean_realized_return: null, label: "통계 무의미 (N<30)" }, { horizon_days: 30, n: 0, hit_rate: null, mean_realized_return: null, label: "통계 무의미 (N<30)" }] },
    _disclaimer: "가설 v0 · 자체 기준 · 관측-only · 매매 미연결",
}

export default function CryptoRegimeSynthesis(props: { dataUrl?: string; dark?: boolean }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const [data, setData] = useState<any>(onCanvas ? DEMO : null)
    const [cacheTs, setCacheTs] = useState<number | null>(null)
    const rootRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        if (typeof localStorage !== "undefined") {
            try {
                const c = localStorage.getItem(CACHE_KEY)
                if (c) { const o = JSON.parse(c); if (o && o.data) { setData(o.data); setCacheTs(o.ts || null) } }
            } catch {}
        }
        const url = props.dataUrl || BLOB + "/crypto_regime.json"
        fetch(url, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d) return
                setData(d); setCacheTs(null)
                if (typeof localStorage !== "undefined") {
                    try { localStorage.setItem(CACHE_KEY, JSON.stringify({ data: d, ts: Date.now() })) } catch {}
                }
            })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    const comp = data && data.composite ? data.composite : null
    const dims: any[] = useMemo(() => (data && Array.isArray(data.dimensions) ? data.dimensions : []), [data])
    const bkt7 = useMemo(() => {
        const b = data && data.track_record && Array.isArray(data.track_record.buckets) ? data.track_record.buckets : []
        return b.find((x: any) => x.horizon_days === 7) || b[0] || null
    }, [data])

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", fontFamily: FONT, color: C.ink, background: C.bg, borderRadius: 16, padding: 20, display: "flex", flexDirection: "column", gap: 16 }

    if (!data || !comp) {
        const skBase = isDark ? "#222a33" : "#e9edf1"
        const skHi = isDark ? "#2d3742" : "#f3f5f7"
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                {Array.from({ length: 7 }).map((_, i) => (
                    <div key={i} style={{ height: i === 0 ? 64 : 44, borderRadius: 12, background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite" }} />
                ))}
            </div>
        )
    }

    const call = comp.call || "neutral"
    const cCol = callColor(call, C)
    const net = num(comp.net_score)

    return (
        <div ref={rootRef} style={wrap}>
            {cacheTs != null && (
                <div style={{ ...MONO, fontSize: 11, color: C.warn, fontWeight: 700 }}>오프라인 캐시 데이터</div>
            )}

            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 19, fontWeight: 800, letterSpacing: "-0.4px" }}>코인 레짐 종합</span>
                <span style={{ marginLeft: "auto", ...MONO, fontSize: 10.5, color: C.faint, fontWeight: 700 }}>{String(data.collected_at || "").slice(0, 10)} · 관측-only</span>
            </div>

            {/* ① 한 판독 (hero) */}
            <div style={{ display: "flex", alignItems: "center", gap: 16, background: alpha(cCol, isDark ? 0.12 : 0.08), border: `1px solid ${alpha(cCol, 0.3)}`, borderRadius: 14, padding: "16px 18px" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontSize: 26, fontWeight: 800, color: cCol, letterSpacing: "-0.6px", lineHeight: 1 }}>{callKo(call)}</span>
                    <span style={{ fontSize: 11.5, color: C.sub, fontWeight: 700 }}>오늘의 한 판독</span>
                </div>
                <div style={{ marginLeft: "auto", textAlign: "right" }}>
                    <div style={{ ...MONO, fontSize: 22, fontWeight: 800, color: cCol, lineHeight: 1 }}>{net != null ? (net > 0 ? "+" : "") + net : "—"}</div>
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 700, marginTop: 3 }}>net · {comp.active_dims}/6 차원</div>
                </div>
            </div>

            {/* ② 드라이버보드 — 왜 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 700, letterSpacing: "0.3px", textTransform: "uppercase" }}>드라이버 — 왜 이 판독인가</span>
                {dims.map((dim: any, i: number) => {
                    const active = !!dim.active
                    const col = readColor(dim.read, active, C)
                    return (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, background: active ? C.card : C.dim, border: `1px solid ${C.line}`, borderRadius: 10, padding: "9px 12px", opacity: active ? 1 : 0.72 }}>
                            <span style={{ width: 7, height: 7, borderRadius: "50%", background: col, flexShrink: 0 }} />
                            <span style={{ fontSize: 13, fontWeight: 800, color: C.ink, minWidth: 96 }}>{dim.name}</span>
                            <span style={{ flex: "1 1 auto", minWidth: 0, ...MONO, fontSize: 11, color: C.faint, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{driverSummary(dim.name, dim.drivers)}</span>
                            <span style={{ fontSize: 11, fontWeight: 800, color: col, padding: "3px 9px", borderRadius: 999, background: alpha(col, active ? 0.14 : 0.1), flexShrink: 0 }}>{readKo(dim.read, active)}</span>
                        </div>
                    )
                })}
            </div>

            {/* ③ 유리박스 — forward 채점 trail */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: "11px 14px", flexWrap: "wrap" }}>
                <div style={{ display: "flex", flexDirection: "column" }}>
                    <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 700, letterSpacing: "0.3px", textTransform: "uppercase" }}>유리박스 — 7일 forward 채점</span>
                    <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>판독을 매일 기록 · BTC 실현수익 대조</span>
                </div>
                <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14 }}>
                    <div style={{ textAlign: "right" }}>
                        <div style={{ ...MONO, fontSize: 16, fontWeight: 800, color: C.ink }}>{bkt7 && bkt7.hit_rate != null ? (Number(bkt7.hit_rate) * 100).toFixed(0) + "%" : "—"}</div>
                        <div style={{ fontSize: 9.5, color: C.faint, fontWeight: 700 }}>적중률</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                        <div style={{ ...MONO, fontSize: 16, fontWeight: 800, color: C.ink }}>{bkt7 ? bkt7.n : 0}</div>
                        <div style={{ fontSize: 9.5, color: C.faint, fontWeight: 700 }}>표본 N</div>
                    </div>
                    <span style={{ fontSize: 10, color: C.warn, fontWeight: 700, padding: "3px 8px", borderRadius: 999, background: alpha(C.warn, 0.14) }}>{bkt7 ? bkt7.label : "누적 시작"}</span>
                </div>
            </div>

            {/* 푸터 — RULE 7 */}
            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.5, borderTop: `1px solid ${C.line}`, paddingTop: 10 }}>
                {data._disclaimer || "가설 v0 · 자체 기준 · 관측-only · 매매 미연결"}
                <br />종합 = 6 차원 투명 tally(가중치 없음, 곡선맞추기 X). 드라이버 raw = 사실, 판독·색 = 가설. 점수·추천 아님.
            </div>
        </div>
    )
}

addPropertyControls(CryptoRegimeSynthesis, {
    dataUrl: { type: ControlType.String, title: "데이터 URL", defaultValue: BLOB + "/crypto_regime.json" },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})

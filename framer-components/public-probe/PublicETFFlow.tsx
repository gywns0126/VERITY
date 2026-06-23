import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * ETF 자금흐름 렌즈 — VERITY 공개 터미널 (골든구스). 국민연금(PublicNPSHoldings)처럼 독립 "렌즈".
 *
 * 🚨 차별 각도: 토스/네이버 ETF 화면(보수율·수익률)과 달리 "패시브 자금이 어느 테마로 들어오나/나가나".
 *   진짜 흐름 = Δ상장좌수(설정/환매) = 가격효과 제거. est_flow = Δ좌수 × NAV (그날 설정/환매 자금규모).
 *
 * 🚨 RULE 7 (held-2027 / feedback_scope):
 *  - 상장좌수·NAV·순자산·흐름 = KRX OpenAPI etf_bydd_trd 1차 사실(api/collectors/etf_flow.py 누적). 그대로 노출.
 *  - 점수·추천·등급 0 (RULE 6 통과 — 결정론적 산식 표시일 뿐).
 *  - 흐름 = 일별 누적형. 첫 신호 = 거래일 ≥2 (그 전엔 "집계 중" graceful — N 누적 투명 표기).
 *
 * 데이터 = data/etf_flow.json (단일 writer, publish-data 발행). 새 파이프라인 0.
 * 테마 = body[data-framer-theme] 자가 추종(다른 public-probe 컴포넌트와 동일 규약).
 */

interface Props {
    dataUrl: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/etf_flow.json"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", in: "#0ca678", inS: "#e7faf0", out: "#f04452", outS: "#ffeef0", accentS: "#eaf3ff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", in: "#34e08a", inS: "#0f241c", out: "#f04452", outS: "#2a1518", accentS: "#15233a",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

// category enum → 한글 (etf_flow.py / etfdata.py _KR_TOP_ETFS 와 1:1)
const CAT: Record<string, string> = {
    equity_domestic: "국내주식", equity_foreign: "해외주식", thematic: "테마",
    bond_kr: "한국채권", bond_us: "미국채권", commodity_gold: "금", commodity: "원자재",
    leverage: "레버리지", inverse: "인버스", sector_financial: "금융", sector_tech: "IT",
    sector: "섹터", dividend: "배당",
}

function fmtKRW(won: any, signed = false): string {
    const n = Number(won)
    if (!isFinite(n) || n === 0) return signed ? "0" : "—"
    const a = Math.abs(n)
    const sign = signed ? (n > 0 ? "+" : "−") : ""
    if (a >= 1e12) return sign + (a / 1e12).toFixed(2) + "조"
    if (a >= 1e8) return sign + Math.round(a / 1e8).toLocaleString("en-US") + "억"
    return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만"
}
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch {
        return ""
    }
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicETFFlow(props: Props) {
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
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    useEffect(() => {
        if (!dataUrl) return
        let alive = true
        fetch(dataUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive && d && Array.isArray(d.etfs)) setData(d) })
            .catch(() => {})
        return () => { alive = false }
    }, [dataUrl])

    const narrow = w > 0 && w < 560
    const loading = !data

    // 카테고리 집계 (흐름 있는 것만)
    const cats = useMemo(() => {
        if (!data) return [] as any[]
        const m: Record<string, number> = {}
        for (const e of data.etfs || []) {
            const f = Number(e.est_flow)
            if (isFinite(f) && f !== 0) m[e.category] = (m[e.category] || 0) + f
        }
        return Object.entries(m).map(([k, v]) => ({ cat: k, flow: v })).sort((a, b) => Math.abs(b.flow) - Math.abs(a.flow))
    }, [data])

    const skBase = isDark ? "#222a33" : "#e9edf1"
    const skHi = isDark ? "#2d3742" : "#f3f5f7"
    const skBlock = (bw: any, bh: number, br = 6): CSSProperties => ({
        width: bw, height: bh, borderRadius: br, background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%", animation: "vefShimmer 1.4s ease-in-out infinite", flexShrink: 0,
    })

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT,
        padding: narrow ? 14 : 18, boxSizing: "border-box", color: C.ink,
    }
    const cardStyle: CSSProperties = {
        background: C.card, borderRadius: 16, padding: narrow ? 14 : 16,
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)", boxSizing: "border-box",
    }

    if (loading) {
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes vefShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ ...skBlock(140, 13, 6), marginBottom: 10 }} />
                <div style={{ ...skBlock("60%", 22, 8), marginBottom: 16 }} />
                <div style={{ ...skBlock("100%", 70, 14), marginBottom: 12 }} />
                {Array.from({ length: 6 }).map((_, i) => <div key={i} style={{ ...skBlock("100%", 46, 12), marginBottom: 8 }} />)}
            </div>
        )
    }

    const etfs: any[] = data.etfs || []
    const hasFlow = Number(data.with_flow_count) > 0
    const maxCat = cats.length ? Math.max(...cats.map((c) => Math.abs(c.flow))) : 0

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ fontSize: 11.5, fontWeight: 800, color: C.faint, letterSpacing: "0.3px" }}>ETF 자금흐름</div>
            <div style={{ fontSize: narrow ? 17 : 19, fontWeight: 800, color: C.ink, letterSpacing: "-0.4px", marginTop: 4 }}>
                패시브 자금이 어디로
            </div>
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 5 }}>
                설정·환매(Δ상장좌수) · 가격효과 제거 · KRX{data.updated_at ? ` · ${fmtAge(data.updated_at)} 갱신` : ""}
            </div>

            {/* 집계 중 배너 (거래일 1일차) */}
            {!hasFlow && (
                <div style={{ ...cardStyle, marginTop: 12, background: C.accentS, display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontSize: 18 }}>⏳</span>
                    <div>
                        <div style={{ fontSize: 13, fontWeight: 800, color: C.ink }}>자금흐름 집계 중</div>
                        <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, marginTop: 2, lineHeight: 1.45 }}>
                            흐름 = 일별 상장좌수 변화. 거래일 2일차부터 순유입/유출 표시. 현재 = 기준 스냅샷({etfs.length}개 ETF) 적재.
                        </div>
                    </div>
                </div>
            )}

            {/* 카테고리 흐름 (흐름 있을 때) */}
            {hasFlow && cats.length > 0 && (
                <div style={{ ...cardStyle, marginTop: 12 }}>
                    <div style={{ fontSize: 11.5, fontWeight: 800, color: C.faint, marginBottom: 10 }}>테마별 순흐름</div>
                    {cats.slice(0, 8).map((c) => {
                        const pos = c.flow > 0
                        const col = pos ? C.in : C.out
                        const pct = maxCat ? Math.max(6, (Math.abs(c.flow) / maxCat) * 100) : 0
                        return (
                            <div key={c.cat} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0" }}>
                                <div style={{ width: narrow ? 62 : 76, flexShrink: 0, fontSize: 12, fontWeight: 700, color: C.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{CAT[c.cat] || c.cat}</div>
                                <div style={{ flex: 1, minWidth: 0, display: "flex", justifyContent: pos ? "flex-start" : "flex-end" }}>
                                    <div style={{ width: `${pct}%`, height: 10, borderRadius: 5, background: col, opacity: 0.85 }} />
                                </div>
                                <div style={{ width: narrow ? 72 : 88, flexShrink: 0, textAlign: "right", fontSize: 12, fontWeight: 800, color: col, fontVariantNumeric: "tabular-nums" }}>{fmtKRW(c.flow, true)}원</div>
                            </div>
                        )
                    })}
                </div>
            )}

            {/* ETF 리스트 */}
            <div style={{ ...cardStyle, marginTop: 12, padding: "4px 8px" }}>
                {etfs.map((e, idx) => {
                    const f = Number(e.est_flow)
                    const has = isFinite(f) && f !== 0
                    const pos = f > 0
                    const col = !has ? C.faint : pos ? C.in : C.out
                    return (
                        <div key={e.ticker} style={{ display: "flex", alignItems: "center", gap: 11, padding: "11px 6px", borderTop: idx === 0 ? "none" : `1px solid ${C.line}` }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 13.5, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{e.name}</div>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 3 }}>
                                    <span style={{ fontSize: 10.5, fontWeight: 700, color: C.sub, background: C.bg, borderRadius: 6, padding: "2px 7px" }}>{CAT[e.category] || e.category}</span>
                                    <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600 }}>순자산 {fmtKRW(e.netasset)}원</span>
                                </div>
                            </div>
                            <div style={{ flexShrink: 0, textAlign: "right" }}>
                                {has ? (
                                    <>
                                        <div style={{ fontSize: 13.5, fontWeight: 800, color: col, fontVariantNumeric: "tabular-nums" }}>{fmtKRW(f, true)}원</div>
                                        <div style={{ fontSize: 10.5, fontWeight: 700, color: col, marginTop: 1 }}>{pos ? "유입" : "유출"}{e.flow_pct != null ? ` ${Number(e.flow_pct) > 0 ? "+" : ""}${Number(e.flow_pct).toFixed(2)}%` : ""}</div>
                                    </>
                                ) : (
                                    <span style={{ fontSize: 11, fontWeight: 700, color: C.faint, background: C.bg, borderRadius: 6, padding: "3px 8px" }}>집계 중</span>
                                )}
                            </div>
                        </div>
                    )
                })}
            </div>

            {/* 면책 */}
            <div style={{ textAlign: "center", fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 18, lineHeight: 1.55 }}>
                상장좌수·NAV·순자산 = KRX OpenAPI 1차 사실 · 흐름 = Δ상장좌수(설정/환매) × NAV, 가격효과 제거 · 일별 누적(거래일≥2 신호) · 등급·추천 아님 · 자체 점수는 검증 후(2027) 공개
            </div>
        </div>
    )
}

addPropertyControls(PublicETFFlow, {
    dataUrl: { type: ControlType.String, title: "ETF Flow URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

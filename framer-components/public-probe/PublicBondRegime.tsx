import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * 채권·금리 레짐 — VERITY 공개 터미널 (AlphaNest). 국민연금(PublicNPSHoldings)처럼 독립 "렌즈".
 * 디자인 = 토스식 미니멀: 무채색 위주 + 방향값만 up(빨강)/down(파랑), 얇은 구분선, 색배경·외곽선·뱃지 없음.
 *
 * 🚨 RULE 7 (held-2027 / feedback_scope / feedback_source_attribution_discipline):
 *  - 생 수치(yields / 2Y-10Y·3M-10Y 스프레드 / IG·HY OAS) = ECOS(KR)·FRED(US) 1차 사실.
 *  - 레짐 분류(금리환경 / 곡선 / 신용사이클) = 자체 기준 v0 = 가설 (bondanalyzer.py). 섹션·푸터에 명시.
 *  - recession_signal(3M-10Y < -10bp) = Fed 표준. 점수·추천 0 (RULE 6 통과 — 결정론 산출 표시).
 * 데이터 = data/bonds.json (단일 writer, publish-data 발행). 테마 = body[data-framer-theme] 자가 추종.
 */

interface Props {
    dataUrl: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/bonds.json"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#f0f1f3", up: "#f04452", down: "#3182f6",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#222730", up: "#f04452", down: "#5b9bff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const RATE_ENV: Record<string, string> = {
    rate_high_restrictive: "고금리 긴축", rate_elevated: "금리 높음",
    rate_normal: "중립 금리", rate_low_accommodative: "저금리 완화",
}
const CURVE_SHAPE: Record<string, { ko: string; desc: string; warn: boolean }> = {
    steep: { ko: "가파른 우상향", desc: "경기회복 기대와 인플레이션 우려가 같이 반영된 모습이에요.", warn: false },
    normal: { ko: "정상 우상향", desc: "장기금리가 단기보다 높은 건강한 형태예요.", warn: false },
    flat: { ko: "평탄(플래트닝)", desc: "장단기 금리 차가 줄어 경기 불확실성이 커진 국면이에요.", warn: true },
    inverted: { ko: "역전", desc: "단기금리가 장기보다 높아요. 경기침체 선행신호로 봐요.", warn: true },
    unknown: { ko: "—", desc: "", warn: false },
}
const CREDIT_CYCLE: Record<string, string> = {
    tightening: "스프레드 타이트", neutral: "중립", easing: "스프레드 확대", stress: "신용 스트레스",
}

function fmtPct(v: any, d = 2): string {
    const n = Number(v)
    return isFinite(n) ? n.toFixed(d) + "%" : "—"
}
function fmtBp(v: any): string {
    const n = Number(v)
    if (!isFinite(n)) return "—"
    return (n > 0 ? "+" : "") + (n * 100).toFixed(0) + "bp"
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
export default function PublicBondRegime(props: Props) {
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
    const [mkt, setMkt] = useState<"us" | "kr">("us")

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
            .then((d) => { if (alive && d && d.yield_curves) setData(d) })
            .catch(() => {})
        return () => { alive = false }
    }, [dataUrl])

    const narrow = w > 0 && w < 560
    const loading = !data

    const skBase = isDark ? "#1e242c" : "#edeff2"
    const skHi = isDark ? "#2a313b" : "#f5f6f8"
    const sk = (bw: any, bh: number, br = 7): CSSProperties => ({
        width: bw, height: bh, borderRadius: br, background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%", animation: "vbrShimmer 1.4s ease-in-out infinite", flexShrink: 0,
    })

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT,
        padding: narrow ? 16 : 22, boxSizing: "border-box", color: C.ink,
    }
    const card: CSSProperties = {
        background: C.card, borderRadius: 18, padding: narrow ? 16 : 20, boxSizing: "border-box",
    }
    const secLabel = (t: string, hint?: string) => (
        <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 4 }}>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: C.ink }}>{t}</span>
            {hint && <span style={{ fontSize: 10.5, fontWeight: 500, color: C.faint }}>{hint}</span>}
        </div>
    )

    if (loading) {
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes vbrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ ...sk(120, 12, 6), marginBottom: 12 }} />
                <div style={{ ...sk("70%", 24, 8), marginBottom: 22 }} />
                <div style={{ ...sk("100%", 150, 18), marginBottom: 12 }} />
                <div style={sk("100%", 180, 18)} />
            </div>
        )
    }

    const yc = data.yield_curves || {}
    const reg = data.bond_regime || {}
    const credit = data.credit_spreads || {}
    const alerts: any[] = Array.isArray(data.inversion_alerts) ? data.inversion_alerts : []
    const usYC = yc.us || {}
    const cur = mkt === "us" ? usYC : (yc.kr || {})
    const curve: any[] = Array.isArray(cur.curve) ? cur.curve : []

    const reKo = RATE_ENV[reg.rate_environment] || reg.rate_environment || "—"
    const cs = CURVE_SHAPE[reg.curve_shape || cur.curve_shape] || CURVE_SHAPE.unknown
    const ccKo = CREDIT_CYCLE[reg.credit_cycle] || reg.credit_cycle || "—"
    const recession = !!reg.recession_signal

    const headline = recession ? "침체 선행신호가 켜졌어요" : `${cs.ko} 곡선이에요`

    const krSpread = (a: string, b: string): number | null => {
        const fa = curve.find((x) => x.tenor === a)
        const fb = curve.find((x) => x.tenor === b)
        if (!fa || !fb) return null
        return Number(fb.yield) - Number(fa.yield)
    }
    const sp210 = mkt === "us" ? usYC.spread_2y_10y : krSpread("2Y", "10Y")
    const sp3m10 = mkt === "us" ? usYC.spread_3m_10y : krSpread("3M", "10Y")

    // 토스식 행 — 라벨(좌, 회색) · 값(우, ink) · 얇은 구분선
    const row = (label: string, value: any, opts?: { color?: string; note?: string; first?: boolean }) => (
        <div key={label} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 0", borderTop: opts?.first ? "none" : `1px solid ${C.line}` }}>
            <span style={{ fontSize: 13.5, fontWeight: 500, color: C.sub }}>{label}</span>
            <span style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                {opts?.note && <span style={{ fontSize: 11.5, fontWeight: 500, color: C.faint }}>{opts.note}</span>}
                <span style={{ fontSize: 14.5, fontWeight: 600, color: opts?.color || C.ink, fontVariantNumeric: "tabular-nums" }}>{value}</span>
            </span>
        </div>
    )
    const spreadColor = (v: any): string | undefined => {
        const n = Number(v)
        if (!isFinite(n)) return undefined
        return n < 0 ? C.up : undefined
    }
    const spreadNote = (v: any): string => {
        const n = Number(v)
        if (!isFinite(n)) return ""
        return n < 0 ? "역전" : n * 100 < 25 ? "평탄" : ""
    }

    const renderCurve = () => {
        const W = 100, H = 44, pX = 1, pY = 9
        const ys = curve.map((p) => Number(p.yield)).filter((v) => isFinite(v))
        if (curve.length < 2 || !ys.length) return <div style={{ fontSize: 12.5, color: C.faint, padding: "8px 0" }}>곡선 데이터 없음</div>
        const minY = Math.min(...ys), maxY = Math.max(...ys), span = maxY - minY || 1, n = curve.length
        const pts = curve.map((p, i) => ({
            x: pX + (i / (n - 1)) * (W - 2 * pX),
            y: pY + (1 - (Number(p.yield) - minY) / span) * (H - 2 * pY),
        }))
        // 부드러운 곡선(Catmull-Rom → 베지어). 점 마커는 늘린 좌표에서 타원으로 찌그러져 제거.
        let line = `M ${pts[0].x.toFixed(2)} ${pts[0].y.toFixed(2)}`
        for (let i = 0; i < n - 1; i++) {
            const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2
            const c1x = p1.x + (p2.x - p0.x) / 6, c1y = p1.y + (p2.y - p0.y) / 6
            const c2x = p2.x - (p3.x - p1.x) / 6, c2y = p2.y - (p3.y - p1.y) / 6
            line += ` C ${c1x.toFixed(2)} ${c1y.toFixed(2)} ${c2x.toFixed(2)} ${c2y.toFixed(2)} ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`
        }
        const lineCol = recession || cs.warn ? C.up : C.down
        return (
            <div>
                <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: 96, display: "block" }}>
                    <path d={`${line} L ${pts[n - 1].x.toFixed(2)} ${H} L ${pts[0].x.toFixed(2)} ${H} Z`} fill={lineCol} opacity={isDark ? 0.1 : 0.06} />
                    <path d={line} fill="none" stroke={lineCol} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                </svg>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
                    {curve.map((p, i) => (
                        <div key={i} style={{ flex: 1, textAlign: "center", minWidth: 0 }}>
                            <div style={{ fontSize: narrow ? 8.5 : 9.5, color: C.faint, fontWeight: 500, whiteSpace: "nowrap" }}>{p.tenor}</div>
                            <div style={{ fontSize: narrow ? 9.5 : 10.5, color: C.sub, fontWeight: 600, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", marginTop: 1 }}>{Number(p.yield).toFixed(2)}</div>
                        </div>
                    ))}
                </div>
            </div>
        )
    }

    const igRisk = String(credit.us_ig_risk || "")
    const hyRisk = String(credit.us_hy_risk || "")

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>채권·금리</div>
            <div style={{ fontSize: narrow ? 20 : 23, fontWeight: 700, color: C.ink, letterSpacing: "-0.5px", marginTop: 6, lineHeight: 1.25 }}>{headline}</div>
            <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 500, marginTop: 7, lineHeight: 1.5 }}>
                {recession ? `${cs.ko} 곡선 · ${reKo}` : `${reKo} · 신용 ${ccKo}`}
            </div>
            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 4 }}>
                채권시장이 주식에 보내는 신호{data.updated_at ? ` · ${fmtAge(data.updated_at)}` : ""}
            </div>

            {/* 수익률 곡선 */}
            <div style={{ ...card, marginTop: 18 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 700, color: C.ink }}>수익률 곡선</span>
                    <div style={{ display: "flex", gap: 2, background: C.bg, borderRadius: 9, padding: 2 }}>
                        {([["us", "미국"], ["kr", "한국"]] as const).map(([k, lb]) => (
                            <button key={k} onClick={() => setMkt(k)}
                                style={{ border: "none", cursor: "pointer", fontFamily: FONT, padding: "5px 13px", borderRadius: 7, fontSize: 11.5, fontWeight: 600, background: mkt === k ? C.card : "transparent", color: mkt === k ? C.ink : C.faint }}>{lb}</button>
                        ))}
                    </div>
                </div>
                {renderCurve()}
                {cs.desc && (
                    <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 500, marginTop: 12, lineHeight: 1.5 }}>{cs.desc}</div>
                )}
            </div>

            {/* 레짐 요약 */}
            <div style={{ ...card, marginTop: 12 }}>
                {secLabel("한눈에", "분류는 자체 기준 v0")}
                {row("금리 환경", reKo, { first: true })}
                {row("곡선 형태", cs.ko)}
                {row("신용 사이클", ccKo)}
                {row("침체 신호", recession ? "켜짐" : "없음", { color: recession ? C.up : undefined })}
            </div>

            {/* 스프레드 */}
            <div style={{ ...card, marginTop: 12 }}>
                {secLabel(`스프레드 · ${mkt === "us" ? "미국" : "한국"}`)}
                {row("2Y–10Y", fmtBp(sp210), { first: true, color: spreadColor(sp210), note: spreadNote(sp210) })}
                {row("3M–10Y", fmtBp(sp3m10), { color: spreadColor(sp3m10), note: spreadNote(sp3m10) })}
                <div style={{ fontSize: 11, color: C.faint, fontWeight: 500, marginTop: 10, lineHeight: 1.5 }}>3M–10Y가 −10bp 아래면 침체 선행신호로 봐요(Fed 표준).</div>
            </div>

            {/* 신용 스프레드 */}
            {(credit.us_ig_oas != null || credit.us_hy_oas != null) && (
                <div style={{ ...card, marginTop: 12 }}>
                    {secLabel("신용 스프레드 · 미국")}
                    {credit.us_ig_oas != null && row("투자등급 IG", fmtPct(credit.us_ig_oas), { first: true, note: igRisk })}
                    {credit.us_hy_oas != null && row("하이일드 HY", fmtPct(credit.us_hy_oas), { note: hyRisk })}
                </div>
            )}

            {/* 역전 경보 */}
            {alerts.length > 0 && (
                <div style={{ ...card, marginTop: 12 }}>
                    {secLabel("곡선 역전 경보")}
                    {alerts.map((a, i) => (
                        <div key={i} style={{ fontSize: 13, fontWeight: 600, color: C.up, padding: "5px 0", lineHeight: 1.5 }}>
                            {a.message || `${a.market} ${a.type}`}
                        </div>
                    ))}
                </div>
            )}

            {/* 면책 */}
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 500, marginTop: 18, lineHeight: 1.6 }}>
                수익률·스프레드·OAS는 ECOS(한국)·FRED(미국) 사실. 레짐 분류(금리환경·곡선·신용사이클)는 자체 기준 v0이고, 침체신호는 Fed 표준이에요. 자체 점수는 검증 후(2027) 공개해요.
            </div>
        </div>
    )
}

addPropertyControls(PublicBondRegime, {
    dataUrl: { type: ControlType.String, title: "Bonds URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

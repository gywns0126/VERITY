import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 채권·금리 레짐 신호판 — VERITY 공개 터미널 (골든구스). 국민연금(PublicNPSHoldings)처럼 독립 "렌즈" 컴포넌트.
 *
 * 🚨 차별 각도(스크리너 아님): 토스/네이버 채권 화면(단순 금리표)과 달리 "채권이 주식에 보내는 신호"로 해석.
 *   한·미 수익률 곡선 + 장단기/신용 스프레드 + 거시 레짐 → 우리 regime/market_horizon 시스템 맥락.
 *
 * 🚨 RULE 7 (held-2027 / feedback_scope / feedback_source_attribution_discipline):
 *  - 생 수치(yields / 2Y-10Y·3M-10Y 스프레드 / IG·HY OAS) = ECOS(KR)·FRED(US) 1차 사실. 그대로 노출.
 *  - 레짐 분류(rate_environment / curve_shape / credit_cycle) = 자체 휴리스틱 v0 = 가설. "자체 분류 v0" 명시 의무.
 *    · curve_shape 임계(2Y-10Y >100/25/-10bp) / credit_cycle 임계(HY OAS 3.0/4.5/6.5%) = bondanalyzer.py 자체 설정.
 *  - recession_signal(3M-10Y < -10bp) = Fed 리서치 표준 = 학술 근거 있음(그래도 신호이지 점수 아님).
 *  - 자체 점수 0 (RULE 6 통과 — LLM narrative 아님, bondanalyzer 결정론적 산출 표시일 뿐).
 *
 * 데이터 = data/bonds.json (단일 writer, publish-data 발행). 새 파이프라인 0.
 * 테마 = body[data-framer-theme] 자가 추종(다른 public-probe 컴포넌트와 동일 규약).
 */

interface Props {
    dataUrl: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/bonds.json"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", good: "#0ca678", goodS: "#e7faf0", warn: "#f08c00", warnS: "#fff4e0",
    bad: "#f04452", badS: "#ffeef0", accent: "#3182f6", accentS: "#eaf3ff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", good: "#34e08a", goodS: "#0f241c", warn: "#ffba4d", warnS: "#2a2113",
    bad: "#f04452", badS: "#2a1518", accent: "#5b9bff", accentS: "#15233a",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

// ── 레짐 enum → 한글·색 (bondanalyzer.py 산출과 1:1, 드리프트 금지) ──
const RATE_ENV: Record<string, { ko: string; tone: string }> = {
    rate_high_restrictive: { ko: "고금리 긴축", tone: "bad" },
    rate_elevated: { ko: "금리 높음", tone: "warn" },
    rate_normal: { ko: "중립 금리", tone: "neutral" },
    rate_low_accommodative: { ko: "저금리 완화", tone: "good" },
}
const CURVE_SHAPE: Record<string, { ko: string; tone: string; desc: string }> = {
    steep: { ko: "가파른 우상향", tone: "warn", desc: "경기회복 기대 + 인플레이션 우려 반영" },
    normal: { ko: "정상 우상향", tone: "good", desc: "건전한 경기 확장 국면" },
    flat: { ko: "플래트닝(평탄)", tone: "warn", desc: "경기 불확실성 확대 국면" },
    inverted: { ko: "역전", tone: "bad", desc: "단기금리 > 장기금리 · 경기침체 선행신호" },
    unknown: { ko: "—", tone: "neutral", desc: "" },
}
// credit_cycle 은 HY OAS 가 넓어질수록 tightening→neutral→easing→stress (위험선호 ↓). 라벨 혼동 방지 위해 위험선호로 풀어 표기.
const CREDIT_CYCLE: Record<string, { ko: string; tone: string }> = {
    tightening: { ko: "스프레드 타이트 · 위험선호", tone: "good" },
    neutral: { ko: "중립", tone: "neutral" },
    easing: { ko: "스프레드 확대 · 경계", tone: "warn" },
    stress: { ko: "신용 스트레스 · 방어", tone: "bad" },
}
const RISK_TONE: Record<string, string> = { LOW: "good", MODERATE: "warn", ELEVATED: "warn", HIGH: "bad", STRESS: "bad" }

function fmtPct(v: any, digits = 2): string {
    const n = Number(v)
    return isFinite(n) ? n.toFixed(digits) + "%" : "—"
}
function fmtBp(v: any): string {
    const n = Number(v)
    if (!isFinite(n)) return "—"
    return (n > 0 ? "+" : "") + (n * 100).toFixed(0) + "bp"
}
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const then = new Date(String(iso)).getTime()
        const mins = Math.max(0, Math.round((Date.now() - then) / 60000))
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

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 */
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

    const toneColor = (tone: string): string =>
        tone === "good" ? C.good : tone === "warn" ? C.warn : tone === "bad" ? C.bad : C.faint
    const toneBg = (tone: string): string =>
        tone === "good" ? C.goodS : tone === "warn" ? C.warnS : tone === "bad" ? C.badS : C.bg

    // ── 스켈레톤 ──
    const skBase = isDark ? "#222a33" : "#e9edf1"
    const skHi = isDark ? "#2d3742" : "#f3f5f7"
    const skBlock = (bw: any, bh: number, br = 6): CSSProperties => ({
        width: bw, height: bh, borderRadius: br, background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%", animation: "vbrShimmer 1.4s ease-in-out infinite", flexShrink: 0,
    })

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT,
        padding: narrow ? 14 : 18, boxSizing: "border-box", color: C.ink,
    }
    const cardStyle: CSSProperties = {
        background: C.card, borderRadius: 16, padding: narrow ? 14 : 18,
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)", boxSizing: "border-box",
    }
    const subLabel = (t: string): JSX.Element => (
        <div style={{ fontSize: 11.5, fontWeight: 800, color: C.faint, marginBottom: 8, letterSpacing: "-0.2px" }}>{t}</div>
    )

    if (loading) {
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes vbrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ ...skBlock(150, 13, 6), marginBottom: 10 }} />
                <div style={{ ...skBlock("66%", 22, 8), marginBottom: 16 }} />
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
                    {Array.from({ length: 4 }).map((_, i) => <div key={i} style={skBlock(narrow ? "46%" : 150, 56, 12)} />)}
                </div>
                <div style={{ ...skBlock("100%", 150, 16), marginBottom: 12 }} />
                <div style={skBlock("100%", 110, 16)} />
            </div>
        )
    }

    const yc = data.yield_curves || {}
    const reg = data.bond_regime || {}
    const credit = data.credit_spreads || {}
    const alerts: any[] = Array.isArray(data.inversion_alerts) ? data.inversion_alerts : []
    const usYC = yc.us || {}
    const krYC = yc.kr || {}
    const cur = mkt === "us" ? usYC : krYC
    const curve: any[] = Array.isArray(cur.curve) ? cur.curve : []

    const reName = RATE_ENV[reg.rate_environment] || { ko: reg.rate_environment || "—", tone: "neutral" }
    const csName = CURVE_SHAPE[reg.curve_shape || cur.curve_shape] || CURVE_SHAPE.unknown
    const ccName = CREDIT_CYCLE[reg.credit_cycle] || { ko: reg.credit_cycle || "—", tone: "neutral" }
    const recession = !!reg.recession_signal

    // 한 줄 요약 (사실 기반 — 침체신호 우선, 아니면 곡선형태)
    const headline = recession
        ? "경기침체 선행신호 발동 — 방어적 자산배분 고려"
        : `${csName.ko} 곡선 · ${reName.ko}`
    const headTone = recession ? "bad" : csName.tone

    // 스프레드 행 (US 는 발행값, KR 은 곡선서 산출)
    const krFromCurve = (a: string, b: string): number | null => {
        const fa = curve.find((x) => x.tenor === a)
        const fb = curve.find((x) => x.tenor === b)
        if (!fa || !fb) return null
        return Number(fb.yield) - Number(fa.yield)
    }
    const spread210 = mkt === "us" ? usYC.spread_2y_10y : krFromCurve("2Y", "10Y")
    const spread3m10 = mkt === "us" ? usYC.spread_3m_10y : krFromCurve("3M", "10Y")

    // ── 미니 수익률 곡선 SVG ──
    const renderCurve = (): JSX.Element => {
        const W = 100, H = 46, padX = 3, padY = 6
        const ys = curve.map((p) => Number(p.yield)).filter((v) => isFinite(v))
        if (curve.length < 2 || !ys.length) return <div style={{ fontSize: 12, color: C.faint }}>곡선 데이터 없음</div>
        const minY = Math.min(...ys), maxY = Math.max(...ys)
        const span = maxY - minY || 1
        const n = curve.length
        const pts = curve.map((p, i) => {
            const x = padX + (i / (n - 1)) * (W - 2 * padX)
            const y = padY + (1 - (Number(p.yield) - minY) / span) * (H - 2 * padY)
            return { x, y, p }
        })
        const path = pts.map((pt, i) => (i === 0 ? "M" : "L") + pt.x.toFixed(1) + " " + pt.y.toFixed(1)).join(" ")
        const lineCol = toneColor(csName.tone)
        return (
            <div>
                <div style={{ position: "relative", width: "100%" }}>
                    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: 92, display: "block" }}>
                        <path d={`${path} L ${pts[n - 1].x.toFixed(1)} ${H} L ${pts[0].x.toFixed(1)} ${H} Z`} fill={lineCol} opacity={isDark ? 0.12 : 0.08} />
                        <path d={path} fill="none" stroke={lineCol} strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                        {pts.map((pt, i) => <circle key={i} cx={pt.x} cy={pt.y} r={1.1} fill={lineCol} vectorEffect="non-scaling-stroke" />)}
                    </svg>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                    {curve.map((p, i) => (
                        <div key={i} style={{ flex: 1, textAlign: "center", minWidth: 0 }}>
                            <div style={{ fontSize: narrow ? 8.5 : 9.5, color: C.faint, fontWeight: 700, whiteSpace: "nowrap" }}>{p.tenor}</div>
                            <div style={{ fontSize: narrow ? 9 : 10, color: C.ink, fontWeight: 700, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{Number(p.yield).toFixed(2)}</div>
                        </div>
                    ))}
                </div>
            </div>
        )
    }

    const chip = (label: string, value: string, tone: string, hyp?: boolean): JSX.Element => (
        <div style={{ flex: narrow ? "1 1 46%" : "1 1 0", minWidth: 0, background: toneBg(tone), borderRadius: 12, padding: "10px 12px", border: `1px solid ${C.line}` }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, color: C.faint, marginBottom: 3 }}>{label}{hyp ? " · 자체 v0" : ""}</div>
            <div style={{ fontSize: 13.5, fontWeight: 800, color: toneColor(tone), letterSpacing: "-0.3px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{value}</div>
        </div>
    )

    const spreadRow = (label: string, v: any, invertAlert = true): JSX.Element => {
        const n = Number(v)
        const has = isFinite(n)
        const inverted = has && n < 0
        const tone = !has ? "neutral" : inverted ? "bad" : n * 100 < 25 ? "warn" : "good"
        return (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 0", borderTop: `1px solid ${C.line}` }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, color: C.sub }}>{label}</span>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 13.5, fontWeight: 800, color: toneColor(tone), fontVariantNumeric: "tabular-nums" }}>{fmtBp(v)}</span>
                    {has && invertAlert && (
                        <span style={{ fontSize: 10.5, fontWeight: 700, color: toneColor(tone), background: toneBg(tone), borderRadius: 6, padding: "2px 7px" }}>
                            {inverted ? "역전" : tone === "warn" ? "평탄" : "정상"}
                        </span>
                    )}
                </span>
            </div>
        )
    }

    const igTone = RISK_TONE[String(credit.us_ig_risk || "").toUpperCase()] || "neutral"
    const hyTone = RISK_TONE[String(credit.us_hy_risk || "").toUpperCase()] || "neutral"

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ fontSize: 11.5, fontWeight: 800, color: C.faint, letterSpacing: "0.3px" }}>채권·금리 레짐</div>
            <div style={{ display: "flex", alignItems: "center", gap: 9, marginTop: 5, flexWrap: "wrap" }}>
                <span style={{ width: 9, height: 9, borderRadius: "50%", background: toneColor(headTone), flexShrink: 0 }} />
                <span style={{ fontSize: narrow ? 17 : 19, fontWeight: 800, color: C.ink, letterSpacing: "-0.4px" }}>{headline}</span>
            </div>
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 5 }}>
                채권시장이 주식에 보내는 신호 · ECOS·FRED{data.updated_at ? ` · ${fmtAge(data.updated_at)} 갱신` : ""}
            </div>

            {/* 레짐 칩 4개 */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
                {chip("금리 환경", reName.ko, reName.tone, true)}
                {chip("곡선 형태", csName.ko, csName.tone, true)}
                {chip("신용 사이클", ccName.ko, ccName.tone, true)}
                {chip("침체 신호", recession ? "발동" : "정상", recession ? "bad" : "good")}
            </div>

            {/* 수익률 곡선 */}
            <div style={{ ...cardStyle, marginTop: 12 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                    {subLabel(`수익률 곡선 · ${mkt === "us" ? "미국" : "한국"}`)}
                    <div style={{ display: "flex", gap: 3, background: C.bg, borderRadius: 9, padding: 3 }}>
                        {([["us", "미국"], ["kr", "한국"]] as const).map(([k, lb]) => (
                            <button key={k} onClick={() => setMkt(k)}
                                style={{ border: "none", cursor: "pointer", fontFamily: FONT, padding: "5px 12px", borderRadius: 7, fontSize: 11.5, fontWeight: 700, background: mkt === k ? C.card : "transparent", color: mkt === k ? C.ink : C.sub, boxShadow: mkt === k ? "0 1px 2px rgba(0,0,0,0.06)" : "none" }}>{lb}</button>
                        ))}
                    </div>
                </div>
                {renderCurve()}
                {csName.desc && (
                    <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, marginTop: 10, lineHeight: 1.5, background: C.bg, borderRadius: 9, padding: "8px 10px" }}>
                        <span style={{ color: toneColor(csName.tone), fontWeight: 800 }}>{csName.ko}</span> · {csName.desc}
                    </div>
                )}
            </div>

            {/* 핵심 스프레드 */}
            <div style={{ ...cardStyle, marginTop: 12 }}>
                {subLabel(`핵심 스프레드 · ${mkt === "us" ? "미국" : "한국"}`)}
                <div style={{ borderTop: `1px solid transparent` }} />
                {spreadRow("2Y–10Y (기간 스프레드)", spread210)}
                {spreadRow("3M–10Y (침체 선행)", spread3m10)}
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.45 }}>
                    3M–10Y &lt; −10bp = 침체 선행신호(Fed 표준). 곡선·스프레드 수치는 ECOS·FRED 사실.
                </div>
            </div>

            {/* 신용 스프레드 (미국 IG/HY OAS) */}
            {(credit.us_ig_oas != null || credit.us_hy_oas != null) && (
                <div style={{ ...cardStyle, marginTop: 12 }}>
                    {subLabel("신용 스프레드 · 미국 OAS")}
                    <div style={{ display: "flex", gap: 10 }}>
                        {credit.us_ig_oas != null && (
                            <div style={{ flex: 1, background: C.bg, borderRadius: 12, padding: "11px 12px" }}>
                                <div style={{ fontSize: 10.5, fontWeight: 700, color: C.faint }}>투자등급 (IG)</div>
                                <div style={{ fontSize: 17, fontWeight: 800, color: C.ink, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{fmtPct(credit.us_ig_oas)}</div>
                                {credit.us_ig_risk && <span style={{ fontSize: 10.5, fontWeight: 700, color: toneColor(igTone), background: toneBg(igTone), borderRadius: 6, padding: "2px 7px", display: "inline-block", marginTop: 5 }}>{credit.us_ig_risk}</span>}
                            </div>
                        )}
                        {credit.us_hy_oas != null && (
                            <div style={{ flex: 1, background: C.bg, borderRadius: 12, padding: "11px 12px" }}>
                                <div style={{ fontSize: 10.5, fontWeight: 700, color: C.faint }}>하이일드 (HY)</div>
                                <div style={{ fontSize: 17, fontWeight: 800, color: C.ink, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{fmtPct(credit.us_hy_oas)}</div>
                                {credit.us_hy_risk && <span style={{ fontSize: 10.5, fontWeight: 700, color: toneColor(hyTone), background: toneBg(hyTone), borderRadius: 6, padding: "2px 7px", display: "inline-block", marginTop: 5 }}>{credit.us_hy_risk}</span>}
                            </div>
                        )}
                    </div>
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.45 }}>
                        OAS = FRED 사실. 신용 사이클 구간(HY 3.0/4.5/6.5%) = 자체 휴리스틱 v0 (가설).
                    </div>
                </div>
            )}

            {/* 역전 경보 */}
            {alerts.length > 0 && (
                <div style={{ ...cardStyle, marginTop: 12, border: `1px solid ${C.bad}`, background: C.badS }}>
                    {subLabel("⚠ 곡선 역전 경보")}
                    {alerts.map((a, i) => (
                        <div key={i} style={{ fontSize: 12.5, fontWeight: 700, color: C.bad, padding: "4px 0", lineHeight: 1.5 }}>
                            {a.message || `${a.market} ${a.type}`}{a.severity ? ` (${a.severity})` : ""}
                        </div>
                    ))}
                </div>
            )}

            {/* 면책 */}
            <div style={{ textAlign: "center", fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 18, lineHeight: 1.55 }}>
                수익률·스프레드·OAS = ECOS(한국)·FRED(미국) 1차 사실 · 레짐 분류(금리환경·곡선·신용사이클) = 자체 휴리스틱 v0(가설) · 침체신호 = Fed 표준 · 등급·추천 아님 · 자체 점수는 검증 후(2027) 공개
            </div>
        </div>
    )
}

addPropertyControls(PublicBondRegime, {
    dataUrl: { type: ControlType.String, title: "Bonds URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

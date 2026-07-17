import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 코인 레짐 트레일 — 코인 AlphaNest 유리박스 lead (TIDE 자기 운영 trail 의 공개 표면).
 *
 * "개미가 손으로 매일 못 모으는 자동화 자산" = 5 온체인/심리 센서 일일 수집 + 레짐 forward 자가채점 + Phase0 백테스트.
 * CoinGecko·LLM 이 못 가지는 view = 우리가 실제 돌린 크립토 레짐 관측의 검증 trail(과정 노출).
 *
 * 데이터 = tide/dashboard.json (TIDE repo → 공유 Vercel Blob, 일 1회 09:07 KST cycle).
 *   regime.latest.sensors = { fear_and_greed, active_addresses, coingecko_macro(SSR+BTC.D), nvt_proxy }
 *   regime.history[14] = 14일 score/label trail · regime.track_record = forward hit(N·평균수익률 병기)
 *   phase0 = A5 TSM 백테스트(정적)
 *
 * 🚨 RULE 7: 레짐 score·분류·등급 = 자체 기준 v0 가설. 센서 raw 값은 사실, 색 해석은 가설.
 *            hit rate 단독 금지(N·평균수익률 병기, TIDE 측 라벨 내장 활용). N<30 "통계 무의미".
 *            Phase0 = 백테스트(라이브 아님) 명시. paper trades=0(약세장 정상) "검증 진행 중".
 * 🚨 RULE 6: LLM·서술 합성 0. 결정론 표시만.
 * 🚨 관측-only: TIDE 매매 미연결(observation_only). 점수→포지션 경로 없음.
 * 다크모드 = body[data-framer-theme] 자가감지(AlphaNest 패턴). onCanvas = 데모.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", up: "#15c47e", down: "#f04452", warn: "#ff9500", accent: "#0ca678",
    track: "#eef1f4", cool: "#3182f6", hypo: "#fff4e3",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", up: "#3ddc97", down: "#ff6b76", warn: "#ffb454", accent: "#3ddc97",
    track: "#222a33", cool: "#5b9dff", hypo: "#2a2113",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const MONO: CSSProperties = { fontFamily: "'SF Mono','JetBrains Mono','Menlo',monospace", fontVariantNumeric: "tabular-nums" }
const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const CACHE_KEY = "verity_tide_regime_cache"

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
    } catch (e) {}
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
function fmtSigned(n: number | null, digits = 1): string {
    if (n == null) return "—"
    return (n > 0 ? "+" : "") + n.toFixed(digits) + "%"
}
// 적중률 Wilson 95% 신뢰구간 (RULE 7 — hit_rate 단독 게재 금지, CI 병기 의무).
// 작은 N 에서 구간이 넓게 나오는 것 = 정직성 핵심(동전던지기와 구별 안 됨을 그대로 노출).
function wilsonCI95(hitRate: number | null, n: number | null): string | null {
    if (hitRate == null || n == null || n < 1) return null
    const z = 1.96
    const p = Math.max(0, Math.min(1, Number(hitRate)))
    const denom = 1 + (z * z) / n
    const center = (p + (z * z) / (2 * n)) / denom
    const half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom
    const lo = Math.max(0, center - half) * 100
    const hi = Math.min(1, center + half) * 100
    return lo.toFixed(0) + "–" + hi.toFixed(0) + "%p"
}
function fmtBig(n: number | null): string {
    if (n == null || n <= 0) return "—"
    if (n >= 1e6) return (n / 1e6).toFixed(2) + "M"
    if (n >= 1e3) return (n / 1e3).toFixed(0) + "K"
    return String(Math.round(n))
}
function cacheAge(ts: number): string {
    const m = Math.round((Date.now() - ts) / 60000)
    if (m < 60) return m + "분 전"
    const h = Math.round(m / 60)
    return h < 24 ? h + "시간 전" : Math.round(h / 24) + "일 전"
}

// risk_on/off 한글 + 색 (관측 사실 표기 — 호재/악재 판정 아님)
function regimeCallKo(call: string): string {
    if (call === "risk_on") return "위험선호"
    if (call === "risk_off") return "위험회피"
    return "중립"
}
function regimeCallColor(call: string, C: typeof LIGHT): string {
    if (call === "risk_on") return C.up
    if (call === "risk_off") return C.cool
    return C.faint
}
// FNG: 낮음=공포(저점 신호), 높음=탐욕(과열). 단방향 강도 아닌 양극 — 사실 강도만.
function fngColor(v: number | null, C: typeof LIGHT): string {
    if (v == null) return C.faint
    if (v >= 75) return C.down       // 극단탐욕 = 과열
    if (v <= 25) return C.cool       // 극단공포 = 저점 가능
    return C.sub
}
function fngKo(label: string): string {
    if (label === "Extreme Greed") return "극단탐욕"
    if (label === "Greed") return "탐욕"
    if (label === "Neutral") return "중립"
    if (label === "Fear") return "공포"
    if (label === "Extreme Fear") return "극단공포"
    return label || "—"
}

const DEMO = {
    generated_at: "demo",
    regime: {
        status: "active", observation_only: true, affects_trading: false,
        latest: {
            obs_date: "2026-06-24", score: 27, label: "비관", regime_call: "risk_off", ok_count: 4,
            sensors: {
                fear_and_greed: { ok: true, value: 23, label: "Extreme Fear", signal: "extreme_fear" },
                active_addresses: { ok: true, trend_pct: -2.35, recent_avg: 455377, signal: "stable" },
                coingecko_macro: { ok: true, ssr: 4.7, btc_dominance_pct: 56.17, total_mcap_b: 2218.5, stablecoin_mcap_b: 265.2 },
                nvt_proxy: { ok: true, nvt_signal: 219.0, marketcap_b: 1282.9 },
            },
        },
        history: [
            { obs_date: "2026-06-11", score: 52, regime_call: "neutral" },
            { obs_date: "2026-06-12", score: 49, regime_call: "neutral" },
            { obs_date: "2026-06-13", score: 44, regime_call: "risk_off" },
            { obs_date: "2026-06-14", score: 41, regime_call: "risk_off" },
            { obs_date: "2026-06-15", score: 38, regime_call: "risk_off" },
            { obs_date: "2026-06-16", score: 35, regime_call: "risk_off" },
            { obs_date: "2026-06-17", score: 33, regime_call: "risk_off" },
            { obs_date: "2026-06-18", score: 36, regime_call: "risk_off" },
            { obs_date: "2026-06-19", score: 31, regime_call: "risk_off" },
            { obs_date: "2026-06-20", score: 29, regime_call: "risk_off" },
            { obs_date: "2026-06-21", score: 30, regime_call: "risk_off" },
            { obs_date: "2026-06-22", score: 28, regime_call: "risk_off" },
            { obs_date: "2026-06-23", score: 27, regime_call: "risk_off" },
            { obs_date: "2026-06-24", score: 27, regime_call: "risk_off" },
        ],
        track_record: {
            buckets: [{ key: "risk_off_7d", regime_call: "risk_off", horizon_days: 7, n: 8, hit_eligible: 8, hit_rate: 0.5, mean_realized_return: 0.0134, label: "통계 무의미 (N 부족)" }],
            _disclaimer: "가설 · 관측-only · 매매 미연결 · hit rate는 N·평균수익률 병기",
        },
        _disclaimer: "가설 · 관측-only · 매매 미연결 · N<30 통계 무의미",
    },
    phase0: { a5_sharpe: 1.8, mdd_pct: -31.1 },
    paper: { trades_count: 0, cycles_count: 150 },
}

export default function CryptoRegimeTrail(props: { dataUrl?: string; dark?: boolean }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))
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
        // cache-fallback: 직전 성공 응답 먼저 표시(빈 화면 회피) → fetch 성공 시 갱신, 실패 시 stale 유지
        if (typeof localStorage !== "undefined") {
            try {
                const c = localStorage.getItem(CACHE_KEY)
                if (c) { const o = JSON.parse(c); if (o && o.data) { setData(o.data); setCacheTs(o.ts || null) } }
            } catch {}
        }
        const url = props.dataUrl || BLOB + "/tide/dashboard.json"
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

    const regime = data && data.regime ? data.regime : null
    const latest = regime && regime.latest ? regime.latest : null
    const sensors = latest && latest.sensors ? latest.sensors : {}

    const spark = useMemo(() => {
        const h = regime && Array.isArray(regime.history) ? regime.history : []
        // history 는 최신순(DESC) → 좌→우 시간순으로 reverse
        return [...h].reverse().map((r: any) => ({ score: num(r.score), call: r.regime_call }))
    }, [regime])

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", fontFamily: FONT, color: C.ink, background: C.bg, borderRadius: 14, padding: 18, display: "flex", flexDirection: "column", gap: 14 }

    // 로딩 / no-data
    if (!data || !regime || regime.status === "no_data") {
        if (!data) {
            const skBase = isDark ? "#222a33" : "#e9edf1"
            const skHi = isDark ? "#2d3742" : "#f3f5f7"
            return (
                <div ref={rootRef} style={wrap}>
                    <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                    {Array.from({ length: 6 }).map((_, i) => (
                        <div key={i} style={{ height: 48, borderRadius: 10, background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite" }} />
                    ))}
                </div>
            )
        }
        return (
            <div ref={rootRef} style={wrap}>
                <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>코인 레짐 트레일</div>
                <div style={{ fontSize: 12.5, color: C.sub, lineHeight: 1.6 }}>레짐 관측 데이터 없음 — TIDE cycle 이 아직 안 돌았거나 dashboard.json 미발행.</div>
            </div>
        )
    }

    const score = num(latest.score)
    const call = latest.regime_call || "neutral"
    const callCol = regimeCallColor(call, C)

    // 센서 추출
    const fng = sensors.fear_and_greed || {}
    const aa = sensors.active_addresses || {}
    const cg = sensors.coingecko_macro || {}
    const nvt = sensors.nvt_proxy || {}
    const fngV = num(fng.value)
    const aaTrend = num(aa.trend_pct)
    const ssr = num(cg.ssr)
    const btcd = num(cg.btc_dominance_pct)
    const nvtV = num(nvt.nvt_signal)

    // track record (첫 bucket — 라벨/disclaimer TIDE 내장 활용)
    const tr = regime.track_record || {}
    const bkt = Array.isArray(tr.buckets) && tr.buckets.length > 0 ? tr.buckets[0] : null

    // phase0 / paper
    const phase0 = data.phase0 || {}
    const sharpe = num(phase0.a5_sharpe)
    const mdd = num(phase0.mdd_pct != null ? phase0.mdd_pct : phase0.mdd)
    const paper = data.paper || {}
    const trades = num(paper.trades_count)

    const SECTION: CSSProperties = { display: "flex", flexDirection: "column", gap: 8 }
    const SECLABEL: CSSProperties = { fontSize: 10.5, color: C.faint, fontWeight: 700, letterSpacing: "0.3px", textTransform: "uppercase" }

    return (
        <div ref={rootRef} style={wrap}>
            {cacheTs != null && (
                <div style={{ ...MONO, fontSize: 11, color: C.warn, fontWeight: 700 }}>오프라인 · {cacheAge(cacheTs)} 데이터</div>
            )}

            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>코인 레짐 트레일</span>
                <span style={{ ...MONO, fontSize: 11, color: callCol, fontWeight: 800, padding: "3px 8px", borderRadius: 999, background: alpha(callCol, 0.14) }}>{regimeCallKo(call)}</span>
                <span style={{ marginLeft: "auto", ...MONO, fontSize: 10.5, color: C.faint, fontWeight: 700 }}>{latest.obs_date} · {latest.ok_count}/4 센서</span>
            </div>
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: -8 }}>관측 전용 · 매매 미연결 · 자체 기준 v0 (가설)</div>

            {/* ① 종합 레짐 점수 + 14일 스파크라인 */}
            <div style={{ display: "flex", alignItems: "center", gap: 14, background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: "12px 14px" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 1, flexShrink: 0 }}>
                    <span style={{ ...MONO, fontSize: 30, fontWeight: 800, color: callCol, lineHeight: 1, letterSpacing: "-1px" }}>{score != null ? score.toFixed(0) : "—"}</span>
                    <span style={{ fontSize: 11.5, color: C.sub, fontWeight: 700 }}>{latest.label || "—"} · 0~100</span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <Sparkline points={spark} C={C} />
                    <div style={{ ...MONO, display: "flex", justifyContent: "space-between", fontSize: 9.5, color: C.faint, fontWeight: 600, marginTop: 3 }}>
                        <span>14일 전</span><span>오늘</span>
                    </div>
                </div>
            </div>

            {/* ② 센서 5분해 — 정보 가치 핵심 (개미가 매일 손으로 못 모음) */}
            <div style={SECTION}>
                <span style={SECLABEL}>센서 분해 — 심리 · 온체인</span>
                <SensorRow C={C} name="Fear & Greed" desc="시장 심리 (alternative.me)"
                    value={fngV != null ? fngV.toFixed(0) : "—"} tag={fngKo(fng.label)} col={fngColor(fngV, C)}
                    bar={fngV != null ? { pct: fngV, col: fngColor(fngV, C) } : null} />
                <SensorRow C={C} name="활성 주소" desc="온체인 사용 추세 (blockchain.info)"
                    value={fmtSigned(aaTrend)} tag={aa.recent_avg ? "평균 " + fmtBig(num(aa.recent_avg)) : ""} col={aaTrend == null ? C.faint : aaTrend >= 0 ? C.up : C.down}
                    bar={aaTrend != null ? { pct: 50 + Math.max(-50, Math.min(50, aaTrend * 5)), col: aaTrend >= 0 ? C.up : C.down } : null} />
                <SensorRow C={C} name="SSR" desc="BTC시총÷스테이블 (매수여력)"
                    value={ssr != null ? ssr.toFixed(1) : "—"} tag={cg.stablecoin_mcap_b ? "스테이블 $" + Math.round(cg.stablecoin_mcap_b) + "B" : ""} col={C.sub}
                    bar={null} />
                <SensorRow C={C} name="BTC 도미넌스" desc="총시총 중 BTC 비중"
                    value={btcd != null ? btcd.toFixed(1) + "%" : "—"} tag={cg.total_mcap_b ? "총 $" + Math.round(cg.total_mcap_b) + "B" : ""} col={C.sub}
                    bar={btcd != null ? { pct: btcd, col: C.accent } : null} />
                <SensorRow C={C} name="NVT Signal" desc="시총÷온체인 전송액 (밸류, 후행)"
                    value={nvtV != null ? nvtV.toFixed(0) : "—"} tag={nvt.marketcap_b ? "시총 $" + Math.round(nvt.marketcap_b) + "B" : ""} col={nvtV != null && nvtV >= 150 ? C.warn : C.sub}
                    bar={null} />
            </div>

            {/* ③ 레짐콜 검증 trail (forward) — RULE 7 라벨 TIDE 내장 활용 */}
            <div style={SECTION}>
                <span style={SECLABEL}>레짐콜 검증 trail (forward)</span>
                {bkt ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 12, background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: "11px 14px", flexWrap: "wrap" }}>
                        <Stat C={C} label="적중률" value={bkt.hit_rate != null ? (Number(bkt.hit_rate) * 100).toFixed(0) + "%" : "—"} hint={wilsonCI95(bkt.hit_rate, bkt.hit_eligible != null ? bkt.hit_eligible : bkt.n) ? "95% CI " + wilsonCI95(bkt.hit_rate, bkt.hit_eligible != null ? bkt.hit_eligible : bkt.n) : null} />
                        <Stat C={C} label="기대값(평균수익)" value={fmtSigned(bkt.mean_realized_return != null ? Number(bkt.mean_realized_return) * 100 : null, 2)} col={bkt.mean_realized_return >= 0 ? C.up : C.down} />
                        <Stat C={C} label="표본 N" value={String(bkt.n != null ? bkt.n : "—")} />
                        <Stat C={C} label="기간" value={(bkt.horizon_days || "—") + "일 · " + regimeCallKo(bkt.regime_call)} />
                        <span style={{ marginLeft: "auto", fontSize: 10.5, color: C.warn, fontWeight: 700, padding: "3px 8px", borderRadius: 999, background: alpha(C.warn, 0.14) }}>{bkt.label || "검증 진행 중"}</span>
                    </div>
                ) : (
                    <div style={{ fontSize: 12, color: C.sub, background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: "11px 14px" }}>채점 가능한 레짐콜 누적 전 — 검증 진행 중 (N=0)</div>
                )}
            </div>

            {/* ④ Phase 0 백테스트 + paper 상태 — 가설/라이브 구분 명시 */}
            <div style={SECTION}>
                <span style={SECLABEL}>전략 trail (TSM)</span>
                <div style={{ display: "flex", alignItems: "center", gap: 12, background: alpha(C.hypo, isDark ? 0.5 : 1), border: `1px solid ${C.line}`, borderRadius: 12, padding: "11px 14px", flexWrap: "wrap" }}>
                    <Stat C={C} label="Sharpe" value={sharpe != null ? sharpe.toFixed(2) : "—"} />
                    <Stat C={C} label="MDD" value={mdd != null ? Math.abs(mdd).toFixed(1) + "%" : "—"} col={C.down} />
                    <Stat C={C} label="라이브 거래" value={trades != null ? String(trades) + "건" : "—"} />
                    <span style={{ marginLeft: "auto", fontSize: 10.5, color: C.faint, fontWeight: 700 }}>
                        {trades === 0 ? "백테스트 (라이브 아님) · 라이브 N=0 약세장 정상" : "백테스트 (라이브 아님)"}
                    </span>
                </div>
            </div>

            {/* 푸터 — RULE 7 disclaimer (TIDE 내장 문구 우선) */}
            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.5, borderTop: `1px solid ${C.line}`, paddingTop: 10 }}>
                {regime._disclaimer || "가설 · 관측-only · 매매 미연결 · N<30 통계 무의미"}
                <br />레짐 score·분류 = 자체 기준 v0 (가설). 센서 raw 값 = 사실, 색 해석 = 가설. 점수·추천 아님.
            </div>
        </div>
    )
}

/* ── 14일 스파크라인 (score 0~100) ── */
function Sparkline({ points, C }: { points: { score: number | null; call: string }[]; C: typeof LIGHT }) {
    const W = 240, H = 40, pad = 3
    const vals = points.map((p) => p.score).filter((v): v is number => v != null)
    if (vals.length < 2) return <div style={{ height: H, fontSize: 10.5, color: C.faint }}>추세 데이터 부족</div>
    const lo = Math.min(...vals, 25), hi = Math.max(...vals, 75)
    const span = hi - lo || 1
    const n = points.length
    const xy = points.map((p, i) => {
        const x = pad + (i / (n - 1)) * (W - pad * 2)
        const v = p.score == null ? lo : p.score
        const y = pad + (1 - (v - lo) / span) * (H - pad * 2)
        return [x, y]
    })
    const path = xy.map(([x, y], i) => (i === 0 ? "M" : "L") + x.toFixed(1) + " " + y.toFixed(1)).join(" ")
    const last = points[points.length - 1]
    const lastCol = last.call === "risk_on" ? C.up : last.call === "risk_off" ? C.cool : C.faint
    return (
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" style={{ display: "block" }}>
            {/* 중립선 50 */}
            <line x1={pad} y1={pad + (1 - (50 - lo) / span) * (H - pad * 2)} x2={W - pad} y2={pad + (1 - (50 - lo) / span) * (H - pad * 2)} stroke={C.line} strokeWidth="1" strokeDasharray="2 3" />
            <path d={path} fill="none" stroke={lastCol} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx={xy[xy.length - 1][0]} cy={xy[xy.length - 1][1]} r="2.5" fill={lastCol} />
        </svg>
    )
}

/* ── 센서 행 ── */
function SensorRow({ C, name, desc, value, tag, col, bar }: {
    C: typeof LIGHT; name: string; desc: string; value: string; tag?: string; col: string
    bar: { pct: number; col: string } | null
}) {
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 10, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: "9px 12px" }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: col, flexShrink: 0 }} />
            <div style={{ flex: "1 1 auto", minWidth: 0 }}>
                <div style={{ ...MONO, fontSize: 12.5, fontWeight: 800, color: C.ink }}>{name}</div>
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{desc}</div>
            </div>
            {bar && (
                <div style={{ width: 64, height: 4, borderRadius: 2, background: C.track, flexShrink: 0, overflow: "hidden" }}>
                    <div style={{ width: Math.max(0, Math.min(100, bar.pct)) + "%", height: "100%", background: bar.col }} />
                </div>
            )}
            <div style={{ textAlign: "right", flexShrink: 0, minWidth: 56 }}>
                <div style={{ ...MONO, fontSize: 14, fontWeight: 800, color: col }}>{value}</div>
                {tag ? <div style={{ ...MONO, fontSize: 9.5, color: C.faint, fontWeight: 600 }}>{tag}</div> : null}
            </div>
        </div>
    )
}

/* ── 통계 셀 ── */
function Stat({ C, label, value, col, hint }: { C: typeof LIGHT; label: string; value: string; col?: string; hint?: string | null }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <span style={{ fontSize: 10, color: C.faint, fontWeight: 700, letterSpacing: "0.2px" }}>{label}</span>
            <span style={{ ...MONO, fontSize: 15, fontWeight: 800, color: col || C.ink }}>{value}</span>
            {hint ? <span style={{ ...MONO, fontSize: 9.5, color: C.faint, fontWeight: 700 }}>{hint}</span> : null}
        </div>
    )
}

addPropertyControls(CryptoRegimeTrail, {
    dataUrl: { type: ControlType.String, title: "데이터 URL", defaultValue: BLOB + "/tide/dashboard.json" },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})

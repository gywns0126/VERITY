import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * Cross-Asset 레짐 — 단일 북 (TIDE 엣지 #2: VERITY 주식 + TIDE 크립토 + 매크로를 한 화면).
 *
 * 펀드는 자산군 silo, 리테일 툴은 단일자산 — 1인이 한 책으로 cross-asset 코히어런스를 보는 게 차별점.
 * 매크로 risk-on/off + 주식 사이클 + 크립토 레짐 + 자산 간 상관(분산 유효성)을 통합 읽기.
 *
 * 🚨 RULE 7: 레짐 "읽기"(가설) — 검증 전 자체 산식, 운영자용. 신호·포지션·매매 추천 아님.
 *    통합 점수 = 기존 market_mood + 크립토 composite 단순 평균(신규 산식 아님, 표시용 결합).
 * 데이터 = portfolio.json(macro.market_mood / market_horizon / macro.cross_asset_corr) + crypto_macro.json(fresh composite).
 * 다크모드 = body[data-framer-theme] 자가감지.
 */

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", on: "#15c47e", off: "#f04452", warn: "#ff9500", accent: "#0ca678" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", on: "#3ddc97", off: "#ff6b76", warn: "#ffb454", accent: "#3ddc97" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const MONO: CSSProperties = { fontFamily: "'SF Mono','JetBrains Mono','Menlo',monospace", fontVariantNumeric: "tabular-nums" }
const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function num(v: any): number | null { const n = Number(v); return isFinite(n) ? n : null }
function riskColor(score: number | null, C: any): string {
    if (score == null) return C.faint
    if (score >= 65) return C.on
    if (score <= 35) return C.off
    return C.warn
}
function riskLabel(score: number | null): string {
    if (score == null) return "—"
    if (score >= 65) return "위험 선호"
    if (score <= 35) return "위험 회피"
    return "중립"
}

const DEMO_PF = {
    macro: { market_mood_us: { score: 55, label: "낙관" }, cross_asset_corr: { regime_signal: "normal", window_days: 30, pairs: { stock_btc: -0.27, gold_usd: -0.55 } } },
    market_horizon: { cycle_stage: "euphoria", cycle_stage_label_ko: "과열 (Euphoria)", recession_prob_12m: 0.158 },
}
const DEMO_CR = { composite: { score: 41, label: "중립", risk_level: "normal" } }

export default function CrossAssetRegime(props: { portfolioUrl?: string; cryptoUrl?: string; dark?: boolean }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const [pf, setPf] = useState<any>(onCanvas ? DEMO_PF : null)
    const [cr, setCr] = useState<any>(onCanvas ? DEMO_CR : null)

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
        fetch(props.portfolioUrl || BLOB + "/portfolio.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((d) => { if (alive && d) setPf(d) }).catch(() => {})
        fetch(props.cryptoUrl || BLOB + "/crypto_macro.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((d) => { if (alive && d) setCr(d) }).catch(() => {})
        return () => { alive = false }
    }, [onCanvas, props.portfolioUrl, props.cryptoUrl])

    const macro = pf?.macro || {}
    const mh = pf?.market_horizon || {}
    const macroScore = num(macro?.market_mood_us?.score) ?? num(macro?.market_mood?.score)
    const cryptoComp = (cr && cr.composite) || (pf?.crypto_macro && pf.crypto_macro.composite) || {}
    const cryptoScore = num(cryptoComp?.score)
    const cac = macro?.cross_asset_corr || {}
    const sync = String(cac?.regime_signal || "")

    const unified = useMemo(() => {
        const arr = [macroScore, cryptoScore].filter((x): x is number => x != null)
        return arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : null
    }, [macroScore, cryptoScore])

    const stockLate = /euphoria|distribution|과열/i.test(String(mh?.cycle_stage || "") + (mh?.cycle_stage_label_ko || ""))
    const fragile = /all_correlated/i.test(sync)
    const diversified = /decoupled/i.test(sync)
    const stockBtc = num(cac?.pairs?.stock_btc)

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", fontFamily: FONT, color: C.ink, background: C.bg, borderRadius: 16, padding: 18, display: "flex", flexDirection: "column", gap: 12 }

    if (!pf) {
        const b = isDark ? "#222a33" : "#e9edf1", h = isDark ? "#2d3742" : "#f3f5f7"
        const sk = (w: any, ht: number, mt = 0): CSSProperties => ({ width: w, height: ht, borderRadius: 8, marginTop: mt, background: b, backgroundImage: `linear-gradient(90deg, ${b} 25%, ${h} 37%, ${b} 63%)`, backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite" })
        return (
            <div style={wrap}>
                <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={sk(160, 18)} /><div style={sk("100%", 70, 6)} />
                <div style={{ display: "flex", gap: 8 }}>{[0, 1, 2].map((i) => <div key={i} style={{ flex: 1 }}><div style={sk("100%", 64)} /></div>)}</div>
                <div style={sk("100%", 40, 4)} />
            </div>
        )
    }

    const axis = (label: string, scoreOrText: any, sub: string, col: string) => (
        <div style={{ flex: 1, minWidth: 0, background: C.card, borderRadius: 12, padding: "11px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>{label}</div>
            <div style={{ ...MONO, fontSize: 18, fontWeight: 800, color: col, marginTop: 2, letterSpacing: "-0.3px" }}>{scoreOrText}</div>
            <div style={{ fontSize: 10.5, fontWeight: 600, color: C.sub, marginTop: 2, lineHeight: 1.4 }}>{sub}</div>
        </div>
    )

    return (
        <div style={wrap}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>Cross-Asset 레짐 · 단일 북</span>
                <span style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>주식 + 크립토 + 매크로 한 화면 · 레짐 읽기(가설)</span>
            </div>

            {/* 통합 risk-on/off */}
            <div style={{ background: C.card, borderRadius: 14, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>통합 위험 선호</div>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                        <span style={{ ...MONO, fontSize: 30, fontWeight: 800, color: riskColor(unified, C), letterSpacing: "-1px" }}>{unified ?? "—"}</span>
                        <span style={{ fontSize: 14, fontWeight: 800, color: riskColor(unified, C) }}>{riskLabel(unified)}</span>
                    </div>
                </div>
                <div style={{ flex: 1, minWidth: 180 }}>
                    <div style={{ height: 8, borderRadius: 999, background: C.line, overflow: "hidden", position: "relative" }}>
                        {unified != null && <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: unified + "%", background: riskColor(unified, C) }} />}
                    </div>
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 5, lineHeight: 1.45 }}>
                        매크로({macroScore ?? "—"}) + 크립토({cryptoScore ?? "—"}) 평균
                        {stockLate ? " · ⚠ 주식 사이클 후기" : ""}{fragile ? " · ⚠ 자산 동기화(분산 무력)" : ""}
                    </div>
                </div>
            </div>

            {/* 3축 */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {axis("매크로", macroScore ?? "—", macro?.market_mood_us?.label || macro?.market_mood?.label || "risk-on/off", riskColor(macroScore, C))}
                {axis("주식 사이클", mh?.cycle_stage_label_ko || mh?.cycle_stage || "—", mh?.recession_prob_12m != null ? `침체확률 ${Math.round(Number(mh.recession_prob_12m) * 100)}%` : "", stockLate ? C.warn : C.ink)}
                {axis("크립토", cryptoScore ?? "—", cryptoComp?.label ? cryptoComp.label + (cryptoComp.risk_level ? " · " + cryptoComp.risk_level : "") : "레짐", riskColor(cryptoScore, C))}
            </div>

            {/* 자산 동기화(분산 유효성) */}
            <div style={{ background: C.card, borderRadius: 12, padding: "11px 13px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 12.5, fontWeight: 800 }}>자산 간 동기화</span>
                    <span style={{ fontSize: 11.5, fontWeight: 800, color: fragile ? C.off : diversified ? C.on : C.warn, background: C.bg, borderRadius: 7, padding: "3px 9px" }}>
                        {fragile ? "위기 동기화 — 분산 무력" : diversified ? "디커플 — 분산 유효" : "정상"}
                    </span>
                    {cac?.window_days ? <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600 }}>{cac.window_days}일</span> : null}
                    {stockBtc != null && <span style={{ ...MONO, marginLeft: "auto", fontSize: 11.5, fontWeight: 700, color: C.sub }}>주식↔BTC {stockBtc > 0 ? "+" : ""}{stockBtc.toFixed(2)}</span>}
                </div>
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.45 }}>
                    6자산(주식·채권·금·USD·원유·BTC) 30일 상관 · all_correlated=위기 시 동반 하락(분산 효과 소멸)
                </div>
            </div>

            <div style={{ textAlign: "center", fontSize: 10, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>
                운영자 단일 북 · 레짐 읽기(가설, 검증 전) · 점수 = 기존 지표 표시용 결합
            </div>
        </div>
    )
}

addPropertyControls(CrossAssetRegime, {
    portfolioUrl: { type: ControlType.String, title: "Portfolio URL", defaultValue: BLOB + "/portfolio.json" },
    cryptoUrl: { type: ControlType.String, title: "Crypto Macro URL", defaultValue: BLOB + "/crypto_macro.json" },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})

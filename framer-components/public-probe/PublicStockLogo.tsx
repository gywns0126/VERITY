import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState } from "react"

/**
 * 종목 로고 아톰 — 커뮤니티 등 임의 표면에서 종목 옆에 붙이는 재사용 배지 (2026-07-11).
 *
 * 토스 종목 CDN 로고(404/차단 시 이니셜 폴백) + circle-flags 원형 국기. 클릭 = /stock?q=<티커>.
 * 비율 고정: 프레임을 어떤 크기로 늘려도 배지 = min(가로,세로) 정사각 중앙 (ResizeObserver 실측).
 *
 * 🚨 2026-07-24 테마 = 자체 내장 CSS 변수(--an-slg-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
 *   <style>{AN_PALETTE} 로 정적 HTML 정합. SVG stroke 는 style 로 넘김(var). 되돌리지 말 것. 데이터 fetch 0.
 */

const LOGO_BASE = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"

const LIGHT = { card: "#ffffff", bg: "#f2f4f6", vt: "#6c5ce7", vtS: "#f0edff" }
const DARK = { card: "#171c23", bg: "#0f1318", vt: "#a99bff", vtS: "#241f3a" }

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-slg-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "slg"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

const isKR = (t: string) => /^\d{6}$/.test(t)
const isRates = (t: string) => t.toUpperCase().startsWith("RATES_")

interface Props {
    ticker: string
    name: string
    showFlag: boolean
    clickable: boolean
    stockPath: string
    dark: boolean
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 * @framerIntrinsicWidth 22
 * @framerIntrinsicHeight 22
 */
export default function PublicStockLogo(props: Props) {
    const { ticker, name, showFlag, clickable, stockPath } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    /* 프레임 실측 → 배지 = min(w,h) 정사각 (비율 고정) */
    const rootRef = useRef<HTMLDivElement>(null)
    const [box, setBox] = useState<{ w: number; h: number }>({ w: 22, h: 22 })
    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries) setBox({ w: e.contentRect.width, h: e.contentRect.height })
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])
    const size = Math.max(12, Math.round(Math.min(box.w || 22, box.h || 22)))

    const [err, setErr] = useState(false)

    const tk = String(ticker || "").trim().toUpperCase()
    const ch = (String(name || tk || "?").trim().charAt(0)) || "?"
    const fsize = Math.round(size * 0.46)
    const flagCode = isKR(tk) ? "kr" : "us"

    const go = () => {
        if (!clickable || onCanvas || typeof window === "undefined" || !tk) return
        try { window.location.href = `${(stockPath || "/stock").replace(/\/+$/, "")}?q=${encodeURIComponent(tk)}` } catch (e) { /* ignore */ }
    }

    const flag = showFlag && tk ? (
        <img src={FLAG_BASE + (isRates(tk) ? (tk === "RATES_KR" ? "kr" : "us") : flagCode) + ".svg"} alt="" width={fsize} height={fsize}
            style={{ position: "absolute", right: -3, bottom: -3, width: fsize, height: fsize, borderRadius: "50%", border: `1.5px solid ${C.card}`, background: C.card, display: "block", boxShadow: "0 1px 2px rgba(0,0,0,0.18)" }} />
    ) : null

    return (
        <div ref={rootRef} onClick={go}
            style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", cursor: clickable && !onCanvas ? "pointer" : "default" }}
            title={clickable && tk ? `${name || tk} 리포트` : undefined}>
            <style>{AN_PALETTE}</style>
            <span style={{ position: "relative", width: size, height: size, flexShrink: 0, display: "inline-block" }}>
                {isRates(tk) ? (
                    <span style={{ width: size, height: size, borderRadius: Math.round(size * 0.32), background: C.vtS, display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <svg width={Math.round(size * 0.62)} height={Math.round(size * 0.62)} viewBox="0 0 16 16" fill="none" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ stroke: C.vt }}>
                            <path d="M2 11 C5 11 6 4 9 4 C12 4 12 7 14 7" />
                        </svg>
                    </span>
                ) : !err && tk ? (
                    <img src={LOGO_BASE + tk.replace(/-/g, ".") + ".png"} alt="" width={size} height={size}
                        onError={() => setErr(true)}
                        style={{ width: size, height: size, borderRadius: Math.round(size * 0.32), objectFit: "cover", display: "block", background: C.bg }} />
                ) : (
                    <span style={{ width: size, height: size, borderRadius: Math.round(size * 0.32), background: C.vtS, color: C.vt, display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * 0.42), fontWeight: 800 }}>{ch}</span>
                )}
                {flag}
            </span>
        </div>
    )
}

addPropertyControls(PublicStockLogo, {
    ticker: { type: ControlType.String, title: "Ticker", defaultValue: "005930", placeholder: "005930 / AAPL" },
    name: { type: ControlType.String, title: "Name", defaultValue: "삼성전자", placeholder: "이니셜 폴백용" },
    showFlag: { type: ControlType.Boolean, title: "국기", defaultValue: true, enabledTitle: "On", disabledTitle: "Off" },
    clickable: { type: ControlType.Boolean, title: "클릭→리포트", defaultValue: true, enabledTitle: "On", disabledTitle: "Off" },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
    dark: { type: ControlType.Boolean, title: "Dark(미사용)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

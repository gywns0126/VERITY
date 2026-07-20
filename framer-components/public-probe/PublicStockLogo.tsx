import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState } from "react"

/**
 * 종목 로고 아톰 — 커뮤니티 등 임의 표면에서 종목 옆에 붙이는 재사용 배지 (2026-07-11).
 *
 * 검색창(PublicStockSearch)·리포트 내장 검색과 동일 문법:
 *   토스 종목 CDN 로고(404/차단 시 이니셜 폴백) + circle-flags 원형 국기(티커 형식으로 KR/US 판별).
 *   RATES_KR/US(채권·금리 가상 티커) = 곡선 마크. 클릭 = /stock?q=<티커> (끌 수 있음).
 * 비율 고정 (PM "검색창처럼"): 프레임을 어떤 크기로 늘려도 배지 = min(가로,세로) 정사각 중앙
 *   — ResizeObserver 실측이라 캔버스 리사이즈에 왜곡 0. Size 수동 prop 불필요(프레임이 크기).
 * 테마 = body[data-framer-theme] 자가 추종 (이니셜 폴백 색). 데이터 fetch 0 — 순수 표시 아톰.
 */

const LOGO_BASE = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"

const LIGHT = { card: "#ffffff", bg: "#f2f4f6", vt: "#6c5ce7", vtS: "#f0edff" }
const DARK = { card: "#171c23", bg: "#0f1318", vt: "#a99bff", vtS: "#241f3a" }

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
// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.
let __anHyd = false
function anReadDark(): boolean {
    if (typeof document === "undefined") return false
    if (!__anHyd) {
        __anHyd = true
        return false
    }
    const h = document.documentElement ? document.documentElement.dataset.anTheme : null
    if (h === "dark") return true
    if (h === "light") return false
    return !!(document.body && document.body.dataset.framerTheme === "dark")
}


// 마운트/토글 재판독 SoT — verity_theme(localStorage) 우선 → html[data-an-theme] → body[data-framer-theme].
// 791d29f7e 8개 fix 에서 누락됐던 body-only 재판독 버그 정정(다크에서 라이트 고정 방지, 2026-07-21 일괄).
function readBodyDark(): boolean {
    if (typeof document === "undefined") return false
    try {
        const pref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (pref === "dark") return true
        if (pref === "light") return false
        const h = document.documentElement ? document.documentElement.dataset.anTheme : null
        if (h === "dark") return true
        if (h === "light") return false
        if (document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

export default function PublicStockLogo(props: Props) {
    const { ticker, name, showFlag, clickable, stockPath, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : anReadDark()))
    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

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

    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT
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
            <span style={{ position: "relative", width: size, height: size, flexShrink: 0, display: "inline-block" }}>
                {isRates(tk) ? (
                    <span style={{ width: size, height: size, borderRadius: Math.round(size * 0.32), background: C.vtS, display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <svg width={Math.round(size * 0.62)} height={Math.round(size * 0.62)} viewBox="0 0 16 16" fill="none" stroke={C.vt} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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
    dark: { type: ControlType.Boolean, title: "Dark(캔버스)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

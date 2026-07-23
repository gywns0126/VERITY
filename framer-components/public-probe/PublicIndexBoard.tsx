import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * 실시간 지수 보드 — AlphaNest 공개. TradingView Single Quote 위젯을 알파네스트 카드 크롬에 녹임.
 *
 * 🚨 시세 컴플라이언스 (2026-07-15):
 *   · 안쪽 이름·가격·등락 = TradingView Single Quote 위젯(TV가 라이선스 부담·렌더 = 우리 재배포 아님). 무료·어트리뷰션 유지.
 *   · 바깥 카드·섹션·그리드·다크모드 = 알파네스트 디자인. TV 데이터 자체 렌더는 ToS/cross-origin 불가 → 위젯 임베드가 유일 합법.
 *   · ⚠️ KR 지수(KRX:KOSPI/KOSDAQ)는 KRX 임베드 정책상 안 뜰 수 있음 → 실측 후 안 뜨면 SECTIONS 에서 제거.
 *   · 컴팩트 = Single Quote(차트 없음, 이름+가격+등락) — 미니차트 위젯 대비 숫자 잘림/세로 짤림 해소. 라벨 중복 제거(TV가 한글명 표시).
 * 🚨 RULE 7 — 사실(지수 레벨·등락)만. 다크모드 자가감지(body[data-framer-theme]). 캔버스 = 안내.
 */

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb" }
const DARK = { bg: "#0f1318", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684", line: "#2b2f37" }

// 섹션별 지수 (TradingView 심볼). FOREXCOM=거의 실시간 CFD, TVC/KRX/XETR=거래소.
const SECTIONS: { title: string; items: { sym: string; name: string }[] }[] = [
    { title: "국내", items: [
        { sym: "KRX:KOSPI", name: "코스피" },
        { sym: "KRX:KOSDAQ", name: "코스닥" },
    ] },
    { title: "미국", items: [
        { sym: "FOREXCOM:SPXUSD", name: "S&P 500" },
        { sym: "FOREXCOM:NSXUSD", name: "나스닥 100" },
        { sym: "FOREXCOM:DJI", name: "다우" },
    ] },
    { title: "아시아·유럽", items: [
        { sym: "TVC:NI225", name: "닛케이" },
        { sym: "TVC:HSI", name: "항셍" },
        { sym: "XETR:DAX", name: "DAX" },
    ] },
]

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {}
    return false
}

// 지수 카드 = 알파네스트 카드 크롬 + 안쪽 TV Single Quote 위젯
function IndexCard(props: { sym: string; isDark: boolean; C: any }) {
    const { sym, isDark, C } = props
    const ref = useRef<HTMLDivElement | null>(null)

    useEffect(() => {
        const host = ref.current
        if (!host) return
        host.innerHTML = ""
        const container = document.createElement("div")
        container.className = "tradingview-widget-container"
        const w = document.createElement("div")
        w.className = "tradingview-widget-container__widget"
        container.appendChild(w)
        const s = document.createElement("script")
        s.type = "text/javascript"
        s.async = true
        s.src = "https://s3.tradingview.com/external-embedding/embed-widget-single-quote.js"
        s.innerHTML = JSON.stringify({
            symbol: sym,
            width: "100%",
            isTransparent: true,
            colorTheme: isDark ? "dark" : "light",
            locale: "kr",
        })
        container.appendChild(s)
        host.appendChild(container)
        return () => { host.innerHTML = "" }
    }, [sym, isDark])

    return (
        <div style={{ background: C.card, borderRadius: 14, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", overflow: "hidden", padding: 2, boxSizing: "border-box" }}>
            <div ref={ref} style={{ width: "100%" }} />
        </div>
    )
}

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


export default function PublicIndexBoard(props: { width?: number; dark?: boolean; minCard?: number }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : anReadDark()))
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const minCard = props.minCard || 200

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const wrap: CSSProperties = { width: "100%", maxWidth: props.width || 720, margin: "0 auto", fontFamily: FONT, color: C.ink, padding: "0 14px", boxSizing: "border-box" }

    if (onCanvas) {
        return (
            <div style={{ ...wrap, minHeight: 120, display: "flex", alignItems: "center", justifyContent: "center", background: C.card, borderRadius: 12, color: C.faint, fontSize: 12.5, fontWeight: 600 }}>
                실시간 지수 보드 (TradingView + 알파네스트 카드) · Preview/Publish 에서 동작
            </div>
        )
    }

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <div style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px" }}>글로벌 지수</div>
                <span style={{ marginLeft: "auto", fontSize: 10.5, fontWeight: 600, color: C.faint }}>장중 · TradingView</span>
            </div>
            {SECTIONS.map((sec) => (
                <div key={sec.title} style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 11.5, fontWeight: 700, color: C.faint, letterSpacing: "0.02em", marginBottom: 6 }}>{sec.title}</div>
                    <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fill, minmax(${minCard}px, 1fr))`, gap: 8 }}>
                        {sec.items.map((it) => <IndexCard key={it.sym} sym={it.sym} isDark={isDark} C={C} />)}
                    </div>
                </div>
            ))}
        </div>
    )
}

addPropertyControls(PublicIndexBoard, {
    width: { type: ControlType.Number, title: "Max Width", defaultValue: 720 },
    minCard: { type: ControlType.Number, title: "카드 최소폭", defaultValue: 200, min: 140, max: 320, step: 10, unit: "px" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

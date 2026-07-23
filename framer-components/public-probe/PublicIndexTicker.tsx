import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState } from "react"

/**
 * 실시간 지수 티커 — AlphaNest 공개 상단. TradingView Ticker Tape 위젯 임베드.
 *
 * 🚨 시세 컴플라이언스 (2026-07-15):
 *   · TradingView 가 라이선스를 부담하는 '표시(display) 위젯' = 우리는 재배포자 아님(임베드만). 무료.
 *   · FX/CFD형 지수 심볼(FOREXCOM:*)은 거의 실시간, 거래소 지수 심볼(KRX:*, TVC:*)은 지연이나 장중 갱신.
 *     → "어제 종가"가 아니라 장중에 움직이는 숫자 = 신뢰(사짜 예언자 인상 제거). 기본기(table stakes).
 *   · 어트리뷰션(TradingView 로고/링크) 제거 금지 = 무료 사용 조건. 위젯이 자동 포함.
 *   · ⚠️ KR 지수(KRX:KOSPI/KOSDAQ)는 KRX 임베드 정책상 표시 안 될 수 있음 → 붙여넣기 후 실측.
 *     안 뜨면 KR 심볼만 제거(미국·글로벌은 정상). 상세 = 권리감사 메모리.
 * 🚨 RULE 7 — 사실(지수 레벨·등락)만. 다크모드 자가감지(body[data-framer-theme]). 캔버스 = 안내 플레이스홀더.
 */

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

// 기본 지수 세트 — FOREXCOM=거의 실시간 CFD, TVC/KRX=거래소 지연. title=한글 라벨.
const DEFAULT_SYMBOLS = [
    { proName: "FOREXCOM:SPXUSD", title: "S&P 500" },
    { proName: "FOREXCOM:NSXUSD", title: "나스닥 100" },
    { proName: "FOREXCOM:DJI", title: "다우" },
    { proName: "KRX:KOSPI", title: "코스피" },
    { proName: "KRX:KOSDAQ", title: "코스닥" },
    { proName: "TVC:NI225", title: "닛케이" },
    { proName: "TVC:HSI", title: "항셍" },
    { proName: "XETR:DAX", title: "DAX" },
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


export default function PublicIndexTicker(props: { width?: number; dark?: boolean; symbolsJson?: string }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : anReadDark()))
    const hostRef = useRef<HTMLDivElement | null>(null)
    const isDark = onCanvas ? !!props.dark : themeDark

    // 테마 추종
    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    // TradingView Ticker Tape 위젯 주입 (테마 바뀌면 재주입)
    useEffect(() => {
        if (onCanvas) return
        const host = hostRef.current
        if (!host) return
        host.innerHTML = ""

        const container = document.createElement("div")
        container.className = "tradingview-widget-container"
        const widget = document.createElement("div")
        widget.className = "tradingview-widget-container__widget"
        container.appendChild(widget)

        let symbols = DEFAULT_SYMBOLS
        try { if (props.symbolsJson && props.symbolsJson.trim()) { const p = JSON.parse(props.symbolsJson); if (Array.isArray(p) && p.length) symbols = p } } catch (e) {}

        const script = document.createElement("script")
        script.type = "text/javascript"
        script.async = true
        script.src = "https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js"
        script.innerHTML = JSON.stringify({
            symbols,
            showSymbolLogo: true,
            isTransparent: true,
            displayMode: "adaptive",
            colorTheme: isDark ? "dark" : "light",
            locale: "kr",
        })
        container.appendChild(script)
        host.appendChild(container)

        return () => { host.innerHTML = "" }
    }, [onCanvas, isDark, props.symbolsJson])

    const wrap: any = { width: "100%", maxWidth: props.width || 1000, margin: "0 auto", fontFamily: FONT, boxSizing: "border-box" }

    if (onCanvas) {
        return (
            <div style={{ ...wrap, minHeight: 46, display: "flex", alignItems: "center", justifyContent: "center", gap: 10, background: isDark ? "#1e2128" : "#f2f4f6", borderRadius: 10, color: isDark ? "#6b7684" : "#8b95a1", fontSize: 12.5, fontWeight: 600, padding: "0 14px" }}>
                실시간 지수 티커 (TradingView) · Preview/Publish 에서 동작
            </div>
        )
    }

    return <div ref={hostRef} style={wrap} />
}

addPropertyControls(PublicIndexTicker, {
    width: { type: ControlType.Number, title: "Max Width", defaultValue: 1000 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    symbolsJson: { type: ControlType.String, title: "Symbols JSON", defaultValue: "", displayTextArea: true, placeholder: '[{"proName":"FOREXCOM:SPXUSD","title":"S&P 500"}]' },
})

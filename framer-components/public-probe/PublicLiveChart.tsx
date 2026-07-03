import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * 시세 차트 — VERITY 공개 터미널. TradingView Advanced Chart 위젯(20분 지연) 임베드 + 네이버 실시간 link-out.
 *
 * 🚨 시세 재배포 컴플라이언스(2026-07-02): 이전 자체 SVG 차트(/api/chart KIS OHLCV + /api/stock 실시간 폴링)
 *   = KRX/KIS 시세 시계열을 익명 공개에 재배포 → 개인 비사업자는 제3자 재배포 불가(코스콤/KRX 계약 필요). 중단.
 *   TradingView 임베드 위젯 = 데이터 라이선스 책임을 TV가 부담 → 임베드 사이트는 별도 계약 불요(20분 지연 무료).
 *   · §non-display: 위젯 데이터는 display 전용. 브레인/스코어링에 사용 금지(우리 브레인은 KRX own-use 직접 사용, 위젯 격리).
 *   · attribution(TradingView 링크) 유지 의무 · 위젯 코드 변형 금지.
 *   · 🚨 유료 구독 티어 전환 시 = TV 상업 라이선스 별도 계약 필요(platforms@tradingview.com). 현 무료 공개는 OK.
 *   상세 = docs/MIGRATION_KRX_QUOTE_REDISTRIBUTION_2026_07.md.
 *
 * 종목 = prop → URL ?q=. verity-ticker-change(StockReport/검색 in-page 전환)·popstate 수신해 리로드 없이 추종.
 * 심볼 = 6자리 KR 코드 → KRX:{code}(코스피·코스닥 공통 프리픽스). 6자리 아니면 빈 상태(엉뚱한 종목 방지).
 * 테마 = body[data-framer-theme] 추종(위젯 theme 파라미터). 캔버스(에디터)는 위젯 미로드 → 플레이스홀더.
 */

interface Props {
    ticker: string
    interval: string
    height: number
    dark: boolean
}
const LIGHT = { bg: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", vg: "#6c5ce7" }
const DARK = { bg: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", vg: "#a99bff" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const TV_SCRIPT = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"

function isMobileWidth(): boolean {
    if (typeof window === "undefined") return false
    return window.innerWidth > 0 && window.innerWidth < 560
}
// 증권사(네이버)가 서빙 = 재배포 아님. 실시간·무료·합법 딥링크.
function naverUrl(tk: string): string {
    if (!/^\d{6}$/.test(tk)) return "https://finance.naver.com/"
    return isMobileWidth()
        ? "https://m.stock.naver.com/domestic/stock/" + tk + "/total"
        : "https://finance.naver.com/item/main.naver?code=" + tk
}

export default function PublicLiveChart(props: Props) {
    const { ticker, interval, height, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const Hprop = height || 340

    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 dark prop 정적) */
    useEffect(() => {
        if (onCanvas) return
        const read = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    // 🚨 종목 미지정 시 삼성전자(005930) 등 기본 종목으로 떨어뜨리지 않음 — 유효 6자리 없으면 빈 상태.
    // 종목 = prop → URL ?q=. verity-ticker-change(StockReport/검색 in-page 전환)·popstate 수신해 리로드 없이 추종.
    const resolveTk = (): string => {
        let t = String(ticker || "").trim()
        if (!t && typeof window !== "undefined") t = (new URLSearchParams(window.location.search).get("q") || "").trim()
        return /^\d{6}$/.test(t) ? t : ""
    }
    const [tk, setTk] = useState<string>(resolveTk)
    useEffect(() => {
        if (onCanvas) return
        const reread = () => setTk(resolveTk())
        reread()
        window.addEventListener("verity-ticker-change", reread)
        window.addEventListener("popstate", reread)
        return () => { window.removeEventListener("verity-ticker-change", reread); window.removeEventListener("popstate", reread) }
    }, [ticker, onCanvas])

    const tvSymbol = tk ? "KRX:" + tk : ""

    /* TradingView Advanced Chart 위젯 임베드 — 심볼/테마 변경 시 재주입. 캔버스는 스킵. */
    const containerRef = useRef<HTMLDivElement>(null)
    useEffect(() => {
        if (onCanvas || !tvSymbol) return
        const container = containerRef.current
        if (!container || typeof document === "undefined") return
        container.innerHTML = ""
        const widgetDiv = document.createElement("div")
        widgetDiv.className = "tradingview-widget-container__widget"
        widgetDiv.style.height = "100%"
        widgetDiv.style.width = "100%"
        container.appendChild(widgetDiv)
        const script = document.createElement("script")
        script.src = TV_SCRIPT
        script.type = "text/javascript"
        script.async = true
        // 위젯 코드 변형 금지 — 공식 config 그대로. autosize=프레임 채움.
        script.innerHTML = JSON.stringify({
            autosize: true,
            symbol: tvSymbol,
            interval: interval || "D",
            timezone: "Asia/Seoul",
            theme: isDark ? "dark" : "light",
            style: "1",
            locale: "kr",
            hide_side_toolbar: true,
            allow_symbol_change: false,
            save_image: false,
            support_host: "https://www.tradingview.com",
        })
        container.appendChild(script)
        return () => { if (container) container.innerHTML = "" }
    }, [tvSymbol, isDark, interval, onCanvas])

    const wrap: CSSProperties = {
        width: "100%", height: "100%", minHeight: Math.max(180, Hprop), position: "relative",
        background: C.bg, borderRadius: 16, overflow: "hidden", boxSizing: "border-box",
        fontFamily: FONT, display: "flex", flexDirection: "column",
    }
    const footer: CSSProperties = {
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
        padding: "6px 12px", flexShrink: 0, borderTop: `1px solid ${C.line}`, flexWrap: "wrap",
    }
    // attribution — TradingView 링크 유지 의무(≥13px, 은폐 금지).
    const attribution = (
        <span style={{ fontSize: 11.5, fontWeight: 600, color: C.faint }}>
            차트 제공 · <a href="https://www.tradingview.com/" target="_blank" rel="noopener nofollow" style={{ color: C.faint, textDecoration: "underline" }}>TradingView</a> · 20분 지연
        </span>
    )
    const naverLink = tk ? (
        <a href={naverUrl(tk)} target="_blank" rel="noopener noreferrer"
            style={{ fontSize: 11.5, fontWeight: 800, color: C.vg, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 3 }}>
            실시간 호가·차트 · 네이버 ↗
        </a>
    ) : null

    // 캔버스(에디터) — 위젯 미로드 → 플레이스홀더
    if (onCanvas) {
        return (
            <div style={wrap}>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8 }}>
                    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" style={{ opacity: 0.55 }}>
                        <path d="M3 3v18h18" stroke={C.faint} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M7 13l3-4 3 3 4-6" stroke={C.vg} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    <span style={{ fontSize: 12.5, fontWeight: 700, color: C.sub }}>TradingView 차트 (게시 시 표시)</span>
                    <span style={{ fontSize: 11, fontWeight: 500, color: C.faint }}>{tvSymbol || "종목 미지정"}</span>
                </div>
                <div style={footer}>{attribution}{naverLink}</div>
            </div>
        )
    }

    // 종목 미지정 — 정직한 빈 상태
    if (!tk) {
        return (
            <div style={wrap}>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 7, padding: "0 18px", textAlign: "center" }}>
                    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" style={{ opacity: 0.45 }}>
                        <path d="M3 3v18h18" stroke={C.faint} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M7 14l3-3 3 3 4-5" stroke={C.faint} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="2.5 2.5" />
                    </svg>
                    <span style={{ fontSize: 13, fontWeight: 700, color: C.sub }}>표시할 종목이 없습니다</span>
                    <span style={{ fontSize: 11, fontWeight: 500, color: C.faint }}>종목을 선택하면 차트가 표시돼요</span>
                </div>
            </div>
        )
    }

    return (
        <div style={wrap}>
            <div ref={containerRef} className="tradingview-widget-container" style={{ flex: 1, width: "100%", minHeight: 0 }} />
            <div style={footer}>{attribution}{naverLink}</div>
        </div>
    )
}

addPropertyControls(PublicLiveChart, {
    ticker: { type: ControlType.String, title: "Ticker", defaultValue: "" },
    interval: { type: ControlType.Enum, title: "Interval", defaultValue: "D", options: ["1", "5", "15", "60", "D", "W", "M"], optionTitles: ["1분", "5분", "15분", "60분", "일", "주", "월"] },
    height: { type: ControlType.Number, title: "Height(min)", defaultValue: 340, min: 160, max: 720, step: 10 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

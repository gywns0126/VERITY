import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { createElement, lazy, Suspense, useEffect, useRef, useState } from "react"
const STOCK_CHART_MODULE = ["https://framer.com/m/", "PublicLiveChart-hYuiQM.js"].join("")
const PublicLiveChart: any = lazy(() => import(STOCK_CHART_MODULE).then((module: any) => ({ default: module.default })))

interface Props {
    ticker?: string
    previewTicker?: string
    chartBase?: string
    height?: number
    usChartHeight?: number
    showVolume?: boolean
    dark?: boolean
    [key: string]: any
}

const COMMODITIES: Record<
    string,
    { name: string; symbol: string; exchange: string; page: string }
> = {
    CMD_GOLD: { name: "금", symbol: "COMEX:GC1!", exchange: "COMEX", page: "COMEX-GC1%21" },
    CMD_SILVER: { name: "은", symbol: "COMEX:SI1!", exchange: "COMEX", page: "COMEX-SI1%21" },
    CMD_COPPER: { name: "구리", symbol: "COMEX:HG1!", exchange: "COMEX", page: "COMEX-HG1%21" },
    CMD_WTI: { name: "WTI 원유", symbol: "NYMEX:CL1!", exchange: "NYMEX", page: "NYMEX-CL1%21" },
    CMD_BRENT: { name: "브렌트유", symbol: "ICEEUR:BRN1!", exchange: "ICE Europe", page: "ICEEUR-BRN1%21" },
    CMD_NATGAS: { name: "천연가스", symbol: "NYMEX:NG1!", exchange: "NYMEX", page: "NYMEX-NG1%21" },
    CMD_CORN: { name: "옥수수", symbol: "CBOT:ZC1!", exchange: "CBOT", page: "CBOT-ZC1%21" },
    CMD_WHEAT: { name: "밀", symbol: "CBOT:ZW1!", exchange: "CBOT", page: "CBOT-ZW1%21" },
    CMD_SOYBEAN: { name: "대두", symbol: "CBOT:ZS1!", exchange: "CBOT", page: "CBOT-ZS1%21" },
    CMD_COFFEE: { name: "커피", symbol: "ICEUS:KC1!", exchange: "ICE US", page: "ICEUS-KC1%21" },
    CMD_SUGAR: { name: "설탕", symbol: "ICEUS:SB1!", exchange: "ICE US", page: "ICEUS-SB1%21" },
    CMD_COTTON: { name: "면화", symbol: "ICEUS:CT1!", exchange: "ICE US", page: "ICEUS-CT1%21" },
}
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

function readTicker(fallback = ""): string {
    if (typeof window === "undefined") return fallback.trim().toUpperCase()
    const query = (
        new URLSearchParams(window.location.search).get("q") || ""
    )
        .trim()
        .toUpperCase()
    if (query) return query
    try {
        return (
            window.localStorage.getItem("verity_last_ticker") || fallback
        )
            .trim()
            .toUpperCase()
    } catch {
        return fallback.trim().toUpperCase()
    }
}

function widgetHtml(symbol: string, dark: boolean): string {
    const bg = dark ? "#171c23" : "#ffffff"
    const config = {
        autosize: true,
        symbol,
        interval: "D",
        timezone: "Asia/Seoul",
        theme: dark ? "dark" : "light",
        style: "1",
        locale: "kr",
        hide_side_toolbar: true,
        allow_symbol_change: false,
        save_image: false,
        withdateranges: true,
        support_host: "https://www.tradingview.com",
    }
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' +
        "*{margin:0;padding:0;border-radius:0!important}" +
        "html,body,.tradingview-widget-container{width:100%;height:100%;overflow:hidden;border:none;background:" +
        bg +
        "}</style></head><body>" +
        '<div class="tradingview-widget-container"><div class="tradingview-widget-container__widget" style="width:100%;height:100%"></div>' +
        '<script src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>' +
        JSON.stringify(config) +
        "</scr" +
        "ipt></div></body></html>"
    )
}

function QuoteStrip({
    symbol,
    dark,
}: {
    symbol: string
    dark: boolean
}) {
    const ref = useRef<HTMLDivElement>(null)
    useEffect(() => {
        const host = ref.current
        if (!host) return
        host.innerHTML = ""
        const container = document.createElement("div")
        container.className = "tradingview-widget-container"
        const widget = document.createElement("div")
        widget.className = "tradingview-widget-container__widget"
        container.appendChild(widget)
        const script = document.createElement("script")
        script.async = true
        script.src =
            "https://s3.tradingview.com/external-embedding/embed-widget-single-quote.js"
        script.innerHTML = JSON.stringify({
            symbol,
            width: "100%",
            isTransparent: true,
            colorTheme: dark ? "dark" : "light",
            locale: "kr",
        })
        container.appendChild(script)
        host.appendChild(container)
        return () => {
            host.innerHTML = ""
        }
    }, [symbol, dark])
    return (
        <div
            ref={ref}
            style={{
                minHeight: 112,
                borderRadius: 14,
                overflow: "hidden",
                background: dark ? "#1e242c" : "#ffffff",
                boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
            }}
        />
    )
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicLiveChartRouter(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const fallback = String(
        props.ticker || (onCanvas ? props.previewTicker || "" : "")
    )
    const [ticker, setTicker] = useState(() => readTicker(fallback))
    const [dark, setDark] = useState(Boolean(props.dark))

    useEffect(() => {
        if (onCanvas) return
        const sync = () => setTicker(readTicker(String(props.ticker || "")))
        sync()
        window.addEventListener("popstate", sync)
        window.addEventListener("verity-ticker-change", sync)
        return () => {
            window.removeEventListener("popstate", sync)
            window.removeEventListener("verity-ticker-change", sync)
        }
    }, [props.ticker, onCanvas])

    useEffect(() => {
        if (typeof document === "undefined") return
        const sync = () =>
            setDark(
                document.body.getAttribute("data-framer-theme") === "dark" ||
                    Boolean(props.dark)
            )
        sync()
        const observer = new MutationObserver(sync)
        observer.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-framer-theme"],
        })
        return () => observer.disconnect()
    }, [props.dark])

    const commodity = COMMODITIES[ticker]
    if (!commodity) return <Suspense fallback={null}>{createElement(PublicLiveChart, props)}</Suspense>

    const height = Math.max(
        300,
        Number(props.usChartHeight || props.height || 480)
    )
    const ink = dark ? "#e3e7ec" : "#191f28"
    const faint = dark ? "#828d9b" : "#8b95a1"
    const bg = dark ? "#171c23" : "#ffffff"
    const violet = dark ? "#a99bff" : "#6c5ce7"

    return (
        <div
            style={{
                width: "100%",
                height: "100%",
                minHeight: 0,
                display: "flex",
                flexDirection: "column",
                gap: 10,
                padding: "0 10px 4px",
                boxSizing: "border-box",
                overflowY: "auto",
                fontFamily: FONT,
            }}
        >
            <div style={{ padding: "0 4px" }}>
                <div
                    style={{
                        color: ink,
                        fontSize: 16,
                        fontWeight: 800,
                        letterSpacing: "-0.3px",
                    }}
                >
                    {commodity.name}
                </div>
                <div
                    style={{
                        color: faint,
                        fontSize: 11.5,
                        fontWeight: 700,
                        marginTop: 3,
                    }}
                >
                    {ticker} · {commodity.exchange} · 선물 연속물
                </div>
            </div>
            <QuoteStrip symbol={commodity.symbol} dark={dark} />
            <div
                style={{
                    width: "100%",
                    minHeight: height,
                    flex: "0 0 " + height + "px",
                    borderRadius: 12,
                    overflow: "hidden",
                    background: bg,
                    lineHeight: 0,
                }}
            >
                <iframe
                    key={commodity.symbol + (dark ? "-dark" : "-light")}
                    title={commodity.name + " 선물 연속물 차트"}
                    srcDoc={widgetHtml(commodity.symbol, dark)}
                    loading="lazy"
                    sandbox="allow-scripts allow-same-origin allow-popups"
                    style={{
                        width: "calc(100% + 6px)",
                        height: "calc(100% + 6px)",
                        margin: -3,
                        border: 0,
                        display: "block",
                        background: bg,
                    }}
                />
            </div>
            <div
                style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    flexWrap: "wrap",
                    padding: "0 4px",
                }}
            >
                <span
                    style={{
                        color: faint,
                        fontSize: 10.5,
                        fontWeight: 600,
                    }}
                >
                    거래소·상품별 지연 가능 · 현물·ETF·ETN과 가격 차이 가능
                </span>
                <a
                    href={
                        "https://www.tradingview.com/symbols/" +
                        commodity.page +
                        "/"
                    }
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                        marginLeft: "auto",
                        color: violet,
                        fontSize: 13,
                        fontWeight: 700,
                        textDecoration: "none",
                    }}
                >
                    차트 by TradingView
                </a>
            </div>
        </div>
    )
}

addPropertyControls(PublicLiveChartRouter, {
    ticker: { type: ControlType.String, title: "Ticker", defaultValue: "" },
    previewTicker: {
        type: ControlType.String,
        title: "Preview",
        defaultValue: "CMD_GOLD",
    },
    chartBase: {
        type: ControlType.String,
        title: "Chart Base",
        defaultValue:
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com",
    },
    height: {
        type: ControlType.Number,
        title: "Height",
        defaultValue: 480,
        min: 220,
        max: 900,
        step: 10,
    },
    usChartHeight: {
        type: ControlType.Number,
        title: "Commodity",
        defaultValue: 400,
        min: 260,
        max: 900,
        step: 10,
    },
    showVolume: {
        type: ControlType.Boolean,
        title: "Volume",
        defaultValue: true,
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark",
        defaultValue: false,
    },
})

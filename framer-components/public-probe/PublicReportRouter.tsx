import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { createElement, lazy, Suspense, useEffect, useMemo, useRef, useState, type CSSProperties } from "react"
const STOCK_REPORT_MODULE = ["https://framer.com/m/", "PublicStockReport-g31utJ.js"].join("")
const PublicStockReport: any = lazy(() => import(STOCK_REPORT_MODULE).then((module: any) => ({ default: module.default })))

interface Props {
    ticker?: string
    previewTicker?: string
    searchUrl?: string
    [key: string]: any
}

const UNIVERSE_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
const COMMODITY_NAMES: Record<string, string> = {
    CMD_GOLD: "금",
    CMD_SILVER: "은",
    CMD_COPPER: "구리",
    CMD_WTI: "WTI 원유",
    CMD_BRENT: "브렌트유",
    CMD_NATGAS: "천연가스",
    CMD_CORN: "옥수수",
    CMD_WHEAT: "밀",
    CMD_SOYBEAN: "대두",
    CMD_COFFEE: "커피",
    CMD_SUGAR: "설탕",
    CMD_COTTON: "면화",
}
const STOCK_DEFAULTS = {
    stockUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json",
    usStockUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json",
    usSmallcapUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_us_smallcap.json",
    flowUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_flow_5d.json",
    forensicsUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/disclosure_forensics.json",
    insiderUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/insider_trades.json",
    warnUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/market_warnings.json",
    lendingUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/securities_lending.json",
    supplyUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/supply_demand.json",
    apiBase: "https://project-yw131.vercel.app",
}
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const PALETTE =
    "body{--an-rr-card:#fff;--an-rr-ink:#191f28;--an-rr-sub:#4e5968;--an-rr-faint:#8b95a1;--an-rr-chip:#f2f4f6;--an-rr-violet:#6c5ce7}" +
    'body[data-framer-theme="dark"]{--an-rr-card:#171c23;--an-rr-ink:#e3e7ec;--an-rr-sub:#9aa4b1;--an-rr-faint:#828d9b;--an-rr-chip:#222933;--an-rr-violet:#a99bff}'

function readTicker(fallback = ""): string {
    if (typeof window === "undefined") return fallback.trim().toUpperCase()
    const fromUrl = (
        new URLSearchParams(window.location.search).get("q") || ""
    )
        .trim()
        .toUpperCase()
    if (fromUrl) return fromUrl
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

function labelOf(item: any): string {
    return String(item.name_ko || item.name || item.ticker || "")
}

function commitTicker(ticker: string) {
    if (typeof window === "undefined") return
    const next = String(ticker || "").trim().toUpperCase()
    if (!next) return
    try {
        window.localStorage.setItem("verity_last_ticker", next)
    } catch {}
    const url = new URL(window.location.href)
    url.searchParams.set("q", next)
    window.history.replaceState({}, "", url.toString())
    window.dispatchEvent(
        new CustomEvent("verity-ticker-change", {
            detail: { ticker: next },
        })
    )
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 */
export default function PublicReportRouter(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const initial = String(
        props.ticker || (onCanvas ? props.previewTicker || "" : readTicker())
    )
        .trim()
        .toUpperCase()
    const [ticker, setTicker] = useState(initial)
    const [query, setQuery] = useState(COMMODITY_NAMES[initial] || initial)
    const [universe, setUniverse] = useState<any[]>([])
    const [open, setOpen] = useState(false)
    const rootRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (onCanvas) return
        const sync = () => {
            const next = readTicker(String(props.ticker || ""))
            setTicker(next)
            setQuery(COMMODITY_NAMES[next] || next)
        }
        sync()
        window.addEventListener("popstate", sync)
        window.addEventListener("verity-ticker-change", sync)
        return () => {
            window.removeEventListener("popstate", sync)
            window.removeEventListener("verity-ticker-change", sync)
        }
    }, [props.ticker, onCanvas])

    useEffect(() => {
        if (!/^CMD_/.test(ticker)) return
        let alive = true
        fetch(props.searchUrl || UNIVERSE_URL)
            .then((response) => (response.ok ? response.json() : null))
            .then((data) => {
                if (!alive || !data) return
                setUniverse(Array.isArray(data) ? data : data.stocks || [])
            })
            .catch(() => {
                if (alive) setUniverse([])
            })
        return () => {
            alive = false
        }
    }, [ticker, props.searchUrl])

    const matches = useMemo(() => {
        const needle = query.trim().toLowerCase()
        if (!needle) return []
        return universe
            .filter((item: any) => {
                const haystack = [
                    item.ticker,
                    item.name,
                    item.name_ko,
                    item.market,
                    item.type,
                ]
                    .filter(Boolean)
                    .join(" ")
                    .toLowerCase()
                return haystack.includes(needle)
            })
            .slice(0, 8)
    }, [query, universe])

    if (!/^CMD_/.test(ticker)) return <Suspense fallback={null}>{createElement(PublicStockReport, { ...STOCK_DEFAULTS, ...props })}</Suspense>

    const choose = (next: string) => {
        setOpen(false)
        commitTicker(next)
    }
    const shell: CSSProperties = {
        width: "100%",
        padding: "0 clamp(14px, 2vw, 20px)",
        boxSizing: "border-box",
        fontFamily: FONT,
    }

    return (
        <div ref={rootRef} style={shell}>
            <style>{PALETTE}</style>
            <div style={{ position: "relative" }}>
                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        minHeight: 52,
                        padding: "0 16px",
                        borderRadius: 16,
                        background: "var(--an-rr-card)",
                        boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                    }}
                >
                    <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="var(--an-rr-faint)"
                        strokeWidth="2"
                        strokeLinecap="round"
                    >
                        <circle cx="11" cy="11" r="7" />
                        <path d="m20 20-3.5-3.5" />
                    </svg>
                    <input
                        value={query}
                        onChange={(event) => {
                            setQuery(event.target.value)
                            setOpen(true)
                        }}
                        onFocus={() => setOpen(true)}
                        onBlur={() =>
                            window.setTimeout(() => setOpen(false), 140)
                        }
                        onKeyDown={(event) => {
                            if (event.key === "Enter" && matches[0])
                                choose(String(matches[0].ticker))
                        }}
                        placeholder="종목·ETF·원자재·채권 검색"
                        aria-label="리포트 검색"
                        style={{
                            width: "100%",
                            minWidth: 0,
                            border: 0,
                            outline: 0,
                            background: "transparent",
                            color: "var(--an-rr-ink)",
                            fontFamily: FONT,
                            fontSize: 15,
                            fontWeight: 700,
                        }}
                    />
                    <span
                        style={{
                            flex: "0 0 auto",
                            color: "var(--an-rr-violet)",
                            fontSize: 11,
                            fontWeight: 800,
                        }}
                    >
                        원자재
                    </span>
                </div>
                {open && matches.length > 0 && (
                    <div
                        style={{
                            position: "absolute",
                            zIndex: 20,
                            top: 58,
                            left: 0,
                            right: 0,
                            padding: 8,
                            borderRadius: 16,
                            background: "var(--an-rr-card)",
                            boxShadow: "0 8px 30px rgba(0,0,0,0.12)",
                        }}
                    >
                        {matches.map((item: any) => (
                            <button
                                key={String(item.ticker)}
                                type="button"
                                onMouseDown={(event) =>
                                    event.preventDefault()
                                }
                                onClick={() => choose(String(item.ticker))}
                                style={{
                                    width: "100%",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "space-between",
                                    gap: 12,
                                    border: 0,
                                    borderRadius: 12,
                                    padding: "10px 12px",
                                    background: "transparent",
                                    color: "var(--an-rr-ink)",
                                    cursor: "pointer",
                                    fontFamily: FONT,
                                    textAlign: "left",
                                }}
                            >
                                <span style={{ fontSize: 13, fontWeight: 800 }}>
                                    {labelOf(item)}
                                </span>
                                <span
                                    style={{
                                        color: "var(--an-rr-faint)",
                                        fontSize: 11,
                                        fontWeight: 700,
                                    }}
                                >
                                    {String(item.ticker)}
                                </span>
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}

addPropertyControls(PublicReportRouter, {
    ticker: { type: ControlType.String, title: "Ticker", defaultValue: "" },
    previewTicker: {
        type: ControlType.String,
        title: "Preview",
        defaultValue: "CMD_GOLD",
    },
    searchUrl: {
        type: ControlType.String,
        title: "Universe",
        defaultValue: UNIVERSE_URL,
    },
})

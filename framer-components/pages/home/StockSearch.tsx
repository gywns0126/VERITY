// StockSearch — 종목 검색 (오퍼레이터). 모든 흐름의 입구.
// 사용자 리스트 "검색". universe_search.json(공개 사실 목록 9593종) 클라 필터.
// 선택 시 기존 패턴 발신: URL ?q= + localStorage verity_last_ticker + verity_recent_tickers +
//   CustomEvent "verity-ticker" → 리포트/분석 컴포넌트가 반응. (기존 컨벤션 정합, RULE 11)
import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', system-ui, sans-serif"
const MONO = "'SF Mono', ui-monospace, SFMono-Regular, Menlo, monospace"
const RECENT_KEY = "verity_recent_tickers"
const LAST_KEY = "verity_last_ticker"
const PURPLE = "#6c5ce7"

function readBodyDark() {
    if (typeof document === "undefined") return false
    try {
        var attr = document.documentElement.getAttribute("data-theme")
        if (attr === "dark") return true
        if (attr === "light") return false
        var t = localStorage.getItem("verity_theme")
        if (t === "dark") return true
        if (t === "light") return false
        if (window.matchMedia)
            return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {
        return false
    }
    return false
}

function loadRecent() {
    try {
        var raw = localStorage.getItem(RECENT_KEY)
        if (!raw) return []
        var arr = JSON.parse(raw)
        return Array.isArray(arr) ? arr.slice(0, 8) : []
    } catch (e) {
        return []
    }
}

const SAMPLE = [
    { ticker: "000660", name: "SK하이닉스", market: "KR", name_ko: "에스케이하이닉스", kw: "에스케이하이닉스" },
    { ticker: "005930", name: "삼성전자", market: "KR", name_ko: "삼성전자", kw: "삼성전자" },
    { ticker: "AAPL", name: "Apple", market: "US", name_ko: "애플", kw: "애플" },
    { ticker: "035420", name: "NAVER", market: "KR", name_ko: "네이버", kw: "네이버" },
]

/**
 * @framerSupportedLayoutWidth any-prefer-fixed
 * @framerSupportedLayoutHeight auto
 */
export default function StockSearch(props) {
    var placeholder = props && props.placeholder ? props.placeholder : "종목명·티커 검색"

    var isCanvas = RenderTarget.current() === RenderTarget.canvas
    var uni = useState([])
    var universe = uni[0]
    var setUniverse = uni[1]
    var q = useState("")
    var query = q[0]
    var setQuery = q[1]
    var rc = useState([])
    var recent = rc[0]
    var setRecent = rc[1]
    var dk = useState(false)
    var dark = dk[0]
    var setDark = dk[1]

    useEffect(function () {
        setDark(readBodyDark())
        setRecent(loadRecent())
    }, [])

    useEffect(
        function () {
            if (isCanvas) {
                setUniverse(SAMPLE)
                return
            }
            var cancelled = false
            fetch(BLOB + "/universe_search.json")
                .then(function (r) {
                    if (!r.ok) throw new Error("http")
                    return r.json()
                })
                .then(function (d) {
                    if (cancelled) return
                    var list = d && d.stocks ? d.stocks : []
                    setUniverse(list)
                })
                .catch(function () {
                    if (!cancelled) setUniverse([])
                })
            return function () {
                cancelled = true
            }
        },
        [isCanvas]
    )

    function select(item) {
        try {
            localStorage.setItem(LAST_KEY, item.ticker)
            var next = [item]
            for (var i = 0; i < recent.length; i++) {
                if (recent[i] && recent[i].ticker !== item.ticker) next.push(recent[i])
            }
            next = next.slice(0, 8)
            localStorage.setItem(RECENT_KEY, JSON.stringify(next))
            setRecent(next)
        } catch (e) {}
        try {
            var url = new URL(window.location.href)
            url.searchParams.set("q", item.ticker)
            window.history.replaceState({}, "", url.toString())
        } catch (e) {}
        try {
            window.dispatchEvent(
                new CustomEvent("verity-ticker", { detail: { ticker: item.ticker, item: item } })
            )
        } catch (e) {}
        setQuery("")
    }

    var results = []
    var norm = query.trim().toLowerCase()
    if (norm.length >= 1) {
        var count = 0
        for (var i = 0; i < universe.length; i++) {
            var it = universe[i]
            if (!it) continue
            var hay =
                String(it.ticker || "").toLowerCase() +
                " " +
                String(it.name || "").toLowerCase() +
                " " +
                String(it.name_ko || "").toLowerCase() +
                " " +
                String(it.kw || "").toLowerCase()
            if (hay.indexOf(norm) >= 0) {
                results.push(it)
                count++
                if (count >= 12) break
            }
        }
    }

    var card = dark ? "#17171c" : "#ffffff"
    var fg = dark ? "#f2f2f5" : "#1a1a1e"
    var sub = dark ? "#9a9aa5" : "#8a8a94"
    var border = dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)"
    var inputBg = dark ? "#0f0f14" : "#f2f2f5"
    var hover = dark ? "rgba(108,92,231,0.14)" : "rgba(108,92,231,0.08)"

    function Row(item, key) {
        var isUS = item.market === "US"
        return (
            <div
                key={key}
                onClick={function () {
                    select(item)
                }}
                style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "9px 11px",
                    borderRadius: 10,
                    cursor: "pointer",
                    gap: 8,
                }}
                onMouseEnter={function (e) {
                    e.currentTarget.style.background = hover
                }}
                onMouseLeave={function (e) {
                    e.currentTarget.style.background = "transparent"
                }}
            >
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 0 }}>
                    <span
                        style={{
                            fontSize: 14,
                            fontWeight: 600,
                            color: fg,
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                        }}
                    >
                        {item.name || item.ticker}
                    </span>
                    <span style={{ fontFamily: MONO, fontSize: 11, color: sub }}>{item.ticker}</span>
                </div>
                <span
                    style={{
                        fontSize: 10,
                        fontWeight: 700,
                        color: isUS ? "#3182f6" : PURPLE,
                        background: isUS ? "rgba(49,130,246,0.12)" : "rgba(108,92,231,0.12)",
                        borderRadius: 6,
                        padding: "2px 6px",
                    }}
                >
                    {isUS ? "US" : "KR"}
                </span>
            </div>
        )
    }

    return (
        <div style={{ fontFamily: FONT, width: "100%", boxSizing: "border-box" }}>
            <input
                value={query}
                onChange={function (e) {
                    setQuery(e.target.value)
                }}
                placeholder={placeholder}
                style={{
                    width: "100%",
                    boxSizing: "border-box",
                    background: inputBg,
                    color: fg,
                    border: "none",
                    borderRadius: 12,
                    padding: "13px 15px",
                    fontSize: 15,
                    fontFamily: FONT,
                    outline: "none",
                }}
            />

            {results.length > 0 ? (
                <div
                    style={{
                        marginTop: 8,
                        background: card,
                        border: "1px solid " + border,
                        borderRadius: 14,
                        padding: 6,
                        display: "flex",
                        flexDirection: "column",
                        gap: 2,
                    }}
                >
                    {results.map(function (it, i) {
                        return Row(it, (it.ticker || "") + i)
                    })}
                </div>
            ) : null}

            {results.length === 0 && recent.length > 0 ? (
                <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 11, color: sub, marginBottom: 7, paddingLeft: 2 }}>
                        최근 검색
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {recent.map(function (it, i) {
                            if (!it) return null
                            return (
                                <span
                                    key={(it.ticker || "") + i}
                                    onClick={function () {
                                        select(it)
                                    }}
                                    style={{
                                        fontSize: 12,
                                        color: fg,
                                        background: inputBg,
                                        borderRadius: 999,
                                        padding: "6px 11px",
                                        cursor: "pointer",
                                    }}
                                >
                                    {it.name || it.ticker}
                                </span>
                            )
                        })}
                    </div>
                </div>
            ) : null}
        </div>
    )
}

addPropertyControls(StockSearch, {
    placeholder: {
        type: ControlType.String,
        title: "안내문구",
        defaultValue: "종목명·티커 검색",
    },
})

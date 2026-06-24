import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useMemo, useState, type CSSProperties } from "react"
import {
    useStockUniverse,
    matchStocks,
    pushRecent,
    STOCK_UNIVERSE_URL,
    LAST_TICKER_KEY,
} from "./verityUniverse"

/**
 * 종목 선택기 (미니) — 현재 페이지의 URL `?q=` 를 바꿔 같은 페이지의 결정 컴포넌트(DecisionPanel/ThesisNote/Report)를 갱신.
 * stockPath 커스텀 prop 불요(MCP 한계 우회) — window.location.pathname 그대로 + ?q=ticker 로 같은 페이지 머묾.
 * 🔗 universe·매칭·최근목록 = verityUniverse 공유 모듈 (4 검색창 단일 출처 — nav/report/decision/watchlist 연동).
 * RULE 7 — 종목 검색 도구일 뿐, 점수·추천 0.
 */

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", vt: "#6c5ce7", vtS: "#f0edff" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", vt: "#a99bff", vtS: "#241f3a" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

interface Props { stockUrl: string; dark: boolean }

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicTickerPicker(props: Props) {
    const { stockUrl, dark } = props
    const C = dark ? DARK : LIGHT
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const universe = useStockUniverse({ onCanvas, krUrl: stockUrl })
    const [q, setQ] = useState("")

    const cur = useMemo(() => {
        if (typeof window === "undefined") return ""
        try {
            const qp = (new URLSearchParams(window.location.search).get("q") || "").trim()
            if (qp) return qp
            return (window.localStorage.getItem(LAST_TICKER_KEY) || "").trim()
        } catch { return "" }
    }, [])

    const curName = useMemo(() => {
        const f = universe.find((x) => String(x.ticker) === cur); return f ? f.name : ""
    }, [universe, cur])

    const matches = useMemo(() => matchStocks(universe, q, 10), [q, universe])

    const pick = (tk: string, nm?: string) => {
        if (onCanvas || typeof window === "undefined" || !tk) return
        pushRecent(tk, nm)
        window.location.href = window.location.pathname + "?q=" + encodeURIComponent(tk)
    }

    const wrap: CSSProperties = { width: "100%", background: C.bg, fontFamily: FONT, padding: 14, boxSizing: "border-box", color: C.ink }
    const input: CSSProperties = { width: "100%", border: `1px solid ${C.line}`, borderRadius: 11, padding: "11px 14px", fontSize: 14, fontFamily: FONT, fontWeight: 600, background: C.card, color: C.ink, outline: "none", boxSizing: "border-box" }

    return (
        <div style={wrap}>
            <div style={{ background: C.card, borderRadius: 14, padding: "13px 15px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, marginBottom: 8 }}>
                    <span style={{ fontSize: 13.5, fontWeight: 800, color: C.ink }}>종목 선택</span>
                    {(curName || cur) && <span style={{ fontSize: 11.5, fontWeight: 700, color: C.vt }}>현재: {curName || cur}</span>}
                </div>
                <input style={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="종목 검색 (이름·코드) — DL이앤씨 / 005930" />
                {matches.length > 0 && (
                    <div style={{ marginTop: 6, border: `1px solid ${C.line}`, borderRadius: 11, padding: 4, maxHeight: 260, overflowY: "auto" }}>
                        {matches.map((m) => (
                            <div key={m.ticker} onClick={() => pick(m.ticker, m.name)} role="button" tabIndex={0}
                                style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "9px 10px", borderRadius: 8, cursor: "pointer" }}>
                                <span style={{ fontSize: 13.5, fontWeight: 700, color: C.ink }}>{m.name}</span>
                                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{m.ticker} · {m.market}</span>
                            </div>
                        ))}
                    </div>
                )}
                {onCanvas && <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 7 }}>프리뷰에서 검색→선택 시 같은 페이지가 ?q=종목코드 로 갱신돼요.</div>}
            </div>
        </div>
    )
}

addPropertyControls(PublicTickerPicker, {
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: STOCK_UNIVERSE_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

interface Holding {
    name: string
    ticker: string
    buyPrice: number
    quantity: number
    currentPrice: number
}

interface Props {
    dataUrl: string
}

export default function PortfolioPanel(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [tab, setTab] = useState<"vams" | "manual">("vams")

    const [manualHoldings, setManualHoldings] = useState<Holding[]>([])
    const [name, setName] = useState("")
    const [ticker, setTicker] = useState("")
    const [buyPrice, setBuyPrice] = useState("")
    const [quantity, setQuantity] = useState("")
    const [currentPrice, setCurrentPrice] = useState("")

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.text())
            .then((txt) =>
                JSON.parse(
                    txt
                        .replace(/\bNaN\b/g, "null")
                        .replace(/\bInfinity\b/g, "null")
                        .replace(/-null/g, "null"),
                ),
            )
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    const vams = data?.vams || {}
    const total = vams.total_asset || 0
    const cash = vams.cash || 0
    const ret = vams.total_return_pct || 0
    const holdings = vams.holdings || []
    const realizedPnl = vams.total_realized_pnl || 0
    const initialCash =
        vams.initial_cash ||
        cash +
            holdings.reduce(
                (sum: number, h: any) =>
                    sum + (h.buy_price || 0) * (h.quantity || 0),
                0,
            ) ||
        total ||
        0
    const hasVams = total > 0 || holdings.length > 0
    const totalPnl = hasVams ? total - initialCash : 0
    const unrealizedPnl = hasVams ? total - initialCash - realizedPnl : 0

    const retColor = ret >= 0 ? "#22C55E" : "#EF4444"
    const pnlColor = (v: number) =>
        v > 0 ? "#22C55E" : v < 0 ? "#EF4444" : "#888"
    const formatPnl = (v: number) =>
        `${v >= 0 ? "+" : ""}${Math.round(v).toLocaleString()}원`

    /* ── 수동 입력 ── */
    const addManual = () => {
        if (!name || !buyPrice || !quantity) return
        setManualHoldings([
            ...manualHoldings,
            {
                name,
                ticker,
                buyPrice: Number(buyPrice),
                quantity: Number(quantity),
                currentPrice: Number(currentPrice) || Number(buyPrice),
            },
        ])
        setName("")
        setTicker("")
        setBuyPrice("")
        setQuantity("")
        setCurrentPrice("")
    }
    const removeManual = (idx: number) =>
        setManualHoldings(manualHoldings.filter((_, i) => i !== idx))

    const manualInvested = manualHoldings.reduce(
        (s, h) => s + h.buyPrice * h.quantity,
        0,
    )
    const manualCurrent = manualHoldings.reduce(
        (s, h) => s + h.currentPrice * h.quantity,
        0,
    )
    const manualReturn =
        manualInvested > 0
            ? ((manualCurrent - manualInvested) / manualInvested) * 100
            : 0

    if (!data) {
        return (
            <div
                style={{
                    ...card,
                    alignItems: "center",
                    justifyContent: "center",
                    minHeight: 200,
                }}
            >
                <span style={{ color: "#555", fontSize: 14, fontFamily: font }}>
                    포트폴리오 데이터 로딩 중...
                </span>
            </div>
        )
    }

    return (
        <div style={card}>
            {/* 탭 */}
            <div style={tabRow}>
                {(["vams", "manual"] as const).map((t) => (
                    <button
                        key={t}
                        onClick={() => setTab(t)}
                        style={{
                            ...tabBtn,
                            color: tab === t ? "#B5FF19" : "#666",
                            borderBottom:
                                tab === t
                                    ? "2px solid #B5FF19"
                                    : "2px solid transparent",
                        }}
                    >
                        {t === "vams" ? "가상 투자 현황" : "실계좌 수동 입력"}
                    </button>
                ))}
            </div>

            {/* ── VAMS 탭 ── */}
            {tab === "vams" && (
                <>
                    <div style={heroSection}>
                        <span style={totalLabel}>총 자산</span>
                        <span style={totalValue}>
                            {total.toLocaleString()}
                            <span style={totalUnit}>원</span>
                        </span>
                        <span style={{ ...returnBadge, color: retColor }}>
                            {ret >= 0 ? "+" : ""}
                            {ret.toFixed(2)}%
                        </span>
                    </div>

                    <div style={pnlRow}>
                        <div style={pnlBox}>
                            <span style={metricLabel}>총 손익</span>
                            <span
                                style={{
                                    ...pnlAmount,
                                    color: pnlColor(totalPnl),
                                }}
                            >
                                {formatPnl(totalPnl)}
                            </span>
                        </div>
                        <div style={pnlBox}>
                            <span style={metricLabel}>실현 손익</span>
                            <span
                                style={{
                                    ...pnlAmount,
                                    color: pnlColor(realizedPnl),
                                }}
                            >
                                {formatPnl(realizedPnl)}
                            </span>
                        </div>
                        <div style={pnlBox}>
                            <span style={metricLabel}>평가 손익</span>
                            <span
                                style={{
                                    ...pnlAmount,
                                    color: pnlColor(unrealizedPnl),
                                }}
                            >
                                {formatPnl(unrealizedPnl)}
                            </span>
                        </div>
                    </div>

                    <div style={metricsRow}>
                        <div style={metricBox}>
                            <span style={metricLabel}>현금</span>
                            <span style={metricVal}>
                                {cash.toLocaleString()}원
                            </span>
                        </div>
                        <div style={metricBox}>
                            <span style={metricLabel}>보유 종목</span>
                            <span style={metricVal}>{holdings.length}개</span>
                        </div>
                    </div>

                    {holdings.length > 0 ? (
                        <div style={holdingsList}>
                            {holdings.map((h: any, i: number) => {
                                const pct = h.return_pct || 0
                                const pctColor =
                                    pct >= 0 ? "#22C55E" : "#EF4444"
                                const pnl =
                                    ((h.current_price || 0) -
                                        (h.buy_price || 0)) *
                                    (h.quantity || 0)
                                return (
                                    <div key={i} style={holdingRow}>
                                        <div style={holdingLeft}>
                                            <span style={holdingName}>
                                                {h.name}
                                            </span>
                                            <span style={holdingDetail}>
                                                {h.quantity}주 · 평단{" "}
                                                {h.buy_price?.toLocaleString()}
                                                원
                                            </span>
                                        </div>
                                        <div style={holdingRight}>
                                            <span
                                                style={{
                                                    ...holdingReturn,
                                                    color: pctColor,
                                                }}
                                            >
                                                {pct >= 0 ? "+" : ""}
                                                {pct.toFixed(2)}%
                                            </span>
                                            <span
                                                style={{
                                                    ...holdingPnl,
                                                    color: pctColor,
                                                }}
                                            >
                                                {formatPnl(pnl)}
                                            </span>
                                            <span style={holdingPrice}>
                                                현재{" "}
                                                {h.current_price?.toLocaleString()}
                                                원
                                            </span>
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    ) : (
                        <div style={emptyHolder}>
                            <span style={emptyText}>
                                아직 매수한 종목이 없습니다
                            </span>
                        </div>
                    )}
                </>
            )}

            {/* ── 수동 입력 탭 ── */}
            {tab === "manual" && (
                <>
                    <div style={form}>
                        <input
                            style={input}
                            placeholder="종목명"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                        />
                        <input
                            style={{ ...input, width: 90 }}
                            placeholder="종목코드"
                            value={ticker}
                            onChange={(e) => setTicker(e.target.value)}
                        />
                        <input
                            style={{ ...input, width: 100 }}
                            placeholder="매수가"
                            type="number"
                            value={buyPrice}
                            onChange={(e) => setBuyPrice(e.target.value)}
                        />
                        <input
                            style={{ ...input, width: 60 }}
                            placeholder="수량"
                            type="number"
                            value={quantity}
                            onChange={(e) => setQuantity(e.target.value)}
                        />
                        <input
                            style={{ ...input, width: 100 }}
                            placeholder="현재가"
                            type="number"
                            value={currentPrice}
                            onChange={(e) => setCurrentPrice(e.target.value)}
                        />
                        <button style={addBtn} onClick={addManual}>
                            추가
                        </button>
                    </div>

                    {manualHoldings.length > 0 && (
                        <div style={manualSummary}>
                            <span style={summaryText}>
                                투자금: {manualInvested.toLocaleString()}원
                            </span>
                            <span style={summaryText}>
                                평가금: {manualCurrent.toLocaleString()}원
                            </span>
                            <span
                                style={{
                                    ...summaryReturn,
                                    color:
                                        manualReturn >= 0
                                            ? "#B5FF19"
                                            : "#FF4D4D",
                                }}
                            >
                                {manualReturn >= 0 ? "+" : ""}
                                {manualReturn.toFixed(2)}%
                            </span>
                        </div>
                    )}

                    {manualHoldings.map((h, i) => {
                        const pct =
                            h.buyPrice > 0
                                ? ((h.currentPrice - h.buyPrice) /
                                      h.buyPrice) *
                                  100
                                : 0
                        return (
                            <div key={i} style={manualRow}>
                                <div style={rowLeft}>
                                    <span style={rowName}>{h.name}</span>
                                    <span style={rowDetail}>
                                        {h.quantity}주 ·{" "}
                                        {h.buyPrice.toLocaleString()}원
                                    </span>
                                </div>
                                <span
                                    style={{
                                        ...rowReturn,
                                        color:
                                            pct >= 0 ? "#B5FF19" : "#FF4D4D",
                                    }}
                                >
                                    {pct >= 0 ? "+" : ""}
                                    {pct.toFixed(1)}%
                                </span>
                                <button
                                    style={removeBtn}
                                    onClick={() => removeManual(i)}
                                >
                                    ✕
                                </button>
                            </div>
                        )
                    })}

                    {manualHoldings.length === 0 && (
                        <div style={emptyHolder}>
                            <span style={emptyText}>
                                위 폼에서 보유 종목을 추가하세요
                            </span>
                        </div>
                    )}
                </>
            )}
        </div>
    )
}

PortfolioPanel.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
}

addPropertyControls(PortfolioPanel, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue:
            "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
})

const font = "'Pretendard', -apple-system, sans-serif"

const card: React.CSSProperties = {
    width: "100%",
    background: "#111",
    borderRadius: 20,
    padding: "32px 28px",
    fontFamily: font,
    display: "flex",
    flexDirection: "column",
    gap: 20,
    border: "1px solid #222",
}

const tabRow: React.CSSProperties = {
    display: "flex",
    gap: 0,
    borderBottom: "1px solid #222",
}

const tabBtn: React.CSSProperties = {
    background: "none",
    border: "none",
    padding: "8px 16px",
    fontSize: 13,
    fontWeight: 600,
    fontFamily: font,
    cursor: "pointer",
    letterSpacing: -0.3,
}

const heroSection: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 4,
}

const totalLabel: React.CSSProperties = {
    color: "#666",
    fontSize: 12,
    fontWeight: 500,
}

const totalValue: React.CSSProperties = {
    color: "#fff",
    fontSize: 36,
    fontWeight: 800,
    letterSpacing: -1.5,
}

const totalUnit: React.CSSProperties = {
    fontSize: 18,
    fontWeight: 500,
    color: "#888",
    marginLeft: 4,
}

const returnBadge: React.CSSProperties = { fontSize: 18, fontWeight: 700 }

const metricsRow: React.CSSProperties = {
    display: "flex",
    gap: 16,
    padding: "12px 0 0",
}

const metricBox: React.CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 4,
}

const metricLabel: React.CSSProperties = {
    color: "#666",
    fontSize: 11,
    fontWeight: 500,
}

const metricVal: React.CSSProperties = {
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
}

const pnlRow: React.CSSProperties = {
    display: "flex",
    gap: 12,
    padding: "14px 0",
    borderTop: "1px solid #222",
    borderBottom: "1px solid #222",
}

const pnlBox: React.CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 4,
}

const pnlAmount: React.CSSProperties = { fontSize: 15, fontWeight: 800 }

const holdingsList: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 12,
}

const holdingRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 16px",
    background: "#0A0A0A",
    borderRadius: 12,
}

const holdingLeft: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const holdingName: React.CSSProperties = {
    color: "#fff",
    fontSize: 15,
    fontWeight: 700,
}

const holdingDetail: React.CSSProperties = {
    color: "#555",
    fontSize: 12,
    fontWeight: 400,
}

const holdingRight: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-end",
    gap: 2,
}

const holdingReturn: React.CSSProperties = { fontSize: 15, fontWeight: 800 }
const holdingPnl: React.CSSProperties = { fontSize: 13, fontWeight: 600 }
const holdingPrice: React.CSSProperties = {
    color: "#555",
    fontSize: 11,
    fontWeight: 400,
}

const emptyHolder: React.CSSProperties = {
    padding: "24px 0",
    textAlign: "center",
}

const emptyText: React.CSSProperties = { color: "#555", fontSize: 13 }

/* ── 수동 입력 전용 스타일 ── */
const form: React.CSSProperties = {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    alignItems: "center",
}

const input: React.CSSProperties = {
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid #333",
    background: "#0A0A0A",
    color: "#fff",
    fontSize: 13,
    fontFamily: font,
    outline: "none",
    width: 110,
}

const addBtn: React.CSSProperties = {
    padding: "10px 20px",
    background: "#B5FF19",
    color: "#000",
    border: "none",
    borderRadius: 10,
    fontSize: 13,
    fontWeight: 700,
    cursor: "pointer",
    fontFamily: font,
}

const manualSummary: React.CSSProperties = {
    display: "flex",
    gap: 16,
    alignItems: "center",
    padding: "12px 16px",
    background: "#0A0A0A",
    border: "1px solid #222",
    borderRadius: 12,
}

const summaryText: React.CSSProperties = {
    color: "#888",
    fontSize: 13,
    fontWeight: 500,
}

const summaryReturn: React.CSSProperties = {
    fontSize: 18,
    fontWeight: 800,
    marginLeft: "auto",
}

const manualRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 16px",
    background: "#0A0A0A",
    borderRadius: 12,
}

const rowLeft: React.CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const rowName: React.CSSProperties = {
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
}

const rowDetail: React.CSSProperties = { color: "#555", fontSize: 12 }

const rowReturn: React.CSSProperties = { fontSize: 16, fontWeight: 800 }

const removeBtn: React.CSSProperties = {
    background: "none",
    border: "none",
    color: "#555",
    fontSize: 14,
    cursor: "pointer",
    padding: 4,
}

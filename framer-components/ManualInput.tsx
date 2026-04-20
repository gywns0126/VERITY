import { addPropertyControls, ControlType } from "framer"
import { useState } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    accentStrong: "0 0 12px rgba(181,255,25,0.50)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


interface Holding {
    name: string
    ticker: string
    buyPrice: number
    quantity: number
    currentPrice: number
}

interface Props {
    title: string
}

export default function ManualInput(props: Props) {
    const { title } = props
    const [holdings, setHoldings] = useState<Holding[]>([])
    const [name, setName] = useState("")
    const [ticker, setTicker] = useState("")
    const [buyPrice, setBuyPrice] = useState("")
    const [quantity, setQuantity] = useState("")
    const [currentPrice, setCurrentPrice] = useState("")

    const addHolding = () => {
        if (!name || !buyPrice || !quantity) return
        setHoldings([
            ...holdings,
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

    const removeHolding = (idx: number) => {
        setHoldings(holdings.filter((_, i) => i !== idx))
    }

    const totalInvested = holdings.reduce(
        (s, h) => s + h.buyPrice * h.quantity,
        0
    )
    const totalCurrent = holdings.reduce(
        (s, h) => s + h.currentPrice * h.quantity,
        0
    )
    const totalReturn =
        totalInvested > 0
            ? ((totalCurrent - totalInvested) / totalInvested) * 100
            : 0

    return (
        <div style={card}>
            <span style={cardTitle}>{title}</span>

            {/* 입력 폼 */}
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
                <button style={addBtn} onClick={addHolding}>
                    추가
                </button>
            </div>

            {/* 합계 */}
            {holdings.length > 0 && (
                <div style={summary}>
                    <span style={summaryText}>
                        투자금: {totalInvested.toLocaleString()}원
                    </span>
                    <span style={summaryText}>
                        평가금: {totalCurrent.toLocaleString()}원
                    </span>
                    <span
                        style={{
                            ...summaryReturn,
                            color:
                                totalReturn >= 0 ? "#B5FF19" : "#FF4D4D",
                        }}
                    >
                        {totalReturn >= 0 ? "+" : ""}
                        {totalReturn.toFixed(2)}%
                    </span>
                </div>
            )}

            {/* 보유 목록 */}
            {holdings.map((h, i) => {
                const pct =
                    h.buyPrice > 0
                        ? ((h.currentPrice - h.buyPrice) / h.buyPrice) * 100
                        : 0
                return (
                    <div key={i} style={row}>
                        <div style={rowLeft}>
                            <span style={rowName}>{h.name}</span>
                            <span style={rowDetail}>
                                {h.quantity}주 · {h.buyPrice.toLocaleString()}원
                            </span>
                        </div>
                        <span
                            style={{
                                ...rowReturn,
                                color: pct >= 0 ? "#B5FF19" : "#FF4D4D",
                            }}
                        >
                            {pct >= 0 ? "+" : ""}
                            {pct.toFixed(1)}%
                        </span>
                        <button
                            style={removeBtn}
                            onClick={() => removeHolding(i)}
                        >
                            ✕
                        </button>
                    </div>
                )
            })}
        </div>
    )
}

ManualInput.defaultProps = {
    title: "실계좌 수동 입력",
}

addPropertyControls(ManualInput, {
    title: {
        type: ControlType.String,
        title: "제목",
        defaultValue: "실계좌 수동 입력",
    },
})

const font = FONT

const card: React.CSSProperties = {
    width: "100%",
    background: "#F8F7F2",
    borderRadius: 20,
    padding: "32px 28px",
    fontFamily: font,
    display: "flex",
    flexDirection: "column",
    gap: 16,
    border: "1px solid #E8E7E2",
}

const cardTitle: React.CSSProperties = {
    color: "#000",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: -0.3,
}

const form: React.CSSProperties = {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    alignItems: "center",
}

const input: React.CSSProperties = {
    padding: "10px 12px",
    borderRadius: 10,
    border: "1px solid #DDD",
    background: "#fff",
    fontSize: 13,
    fontFamily: font,
    outline: "none",
    width: 110,
}

const addBtn: React.CSSProperties = {
    padding: "10px 20px",
    background: "#000",
    color: "#B5FF19",
    border: "none",
    borderRadius: 10,
    fontSize: 13,
    fontWeight: 700,
    cursor: "pointer",
    fontFamily: font,
}

const summary: React.CSSProperties = {
    display: "flex",
    gap: 16,
    alignItems: "center",
    padding: "12px 16px",
    background: "#000",
    borderRadius: 12,
}

const summaryText: React.CSSProperties = {
    color: C.textSecondary,
    fontSize: 13,
    fontWeight: 500,
}

const summaryReturn: React.CSSProperties = {
    fontSize: 18,
    fontWeight: 800,
    marginLeft: "auto",
}

const row: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 16px",
    background: "#fff",
    borderRadius: 12,
}

const rowLeft: React.CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const rowName: React.CSSProperties = {
    color: "#000",
    fontSize: 14,
    fontWeight: 700,
}

const rowDetail: React.CSSProperties = {
    color: C.textSecondary,
    fontSize: 12,
}

const rowReturn: React.CSSProperties = {
    fontSize: 16,
    fontWeight: 800,
}

const removeBtn: React.CSSProperties = {
    background: "none",
    border: "none",
    color: C.textPrimary,
    fontSize: 14,
    cursor: "pointer",
    padding: 4,
}

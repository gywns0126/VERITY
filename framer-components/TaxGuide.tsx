import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

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


function _bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    return `${u}${u.includes("?") ? "&" : "?"}_=${Date.now()}`
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(_bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

interface Props {
    dataUrl: string
}

type Tab = "kr" | "us" | "tips" | "calc"

type CalcMode = "kr_stt" | "kr_div" | "us_gain"

interface TaxRow {
    label: string
    rate: string
    note: string
}

const KR_TAX: TaxRow[] = [
    { label: "증권거래세 (KOSPI)", rate: "0.03%", note: "매도 시 자동 원천징수" },
    { label: "증권거래세 (KOSDAQ)", rate: "0.15%", note: "매도 시 자동 원천징수" },
    { label: "양도소득세 (대주주)", rate: "22~27.5%", note: "종목당 10억+ 보유 시 과세" },
    { label: "양도소득세 (소액주주)", rate: "비과세", note: "상장주식 장내거래 한정" },
    { label: "배당소득세", rate: "15.4%", note: "소득세 14% + 지방세 1.4%" },
    { label: "금융소득종합과세", rate: "6~45%", note: "이자+배당 연 2천만원 초과 시" },
]

const US_TAX: TaxRow[] = [
    { label: "양도소득세 (해외주식)", rate: "22%", note: "연 250만원 기본공제 후 과세 (지방세 포함)" },
    { label: "단기 양도 (1년 미만)", rate: "6~45%", note: "국내 종합소득세율 적용" },
    { label: "장기 양도 (1년 이상)", rate: "22%", note: "분류과세 (기본공제 250만원)" },
    { label: "배당소득세 (미국 원천)", rate: "15%", note: "미국에서 원천징수, 한국 세액공제 가능" },
    { label: "배당소득세 (한국 추가)", rate: "0.4%", note: "한국 15.4% - 미국 15% = 차액 과세" },
    { label: "환차익", rate: "비과세", note: "주식 매매차익에 포함되어 별도 과세 없음" },
]

interface TipItem {
    title: string
    desc: string
    tag: string
}

const TAX_TIPS: TipItem[] = [
    {
        title: "손익통산 활용",
        desc: "같은 해에 실현된 이익과 손실을 상계할 수 있습니다. 수익 종목 매도 전 손실 종목을 먼저 정리하면 절세 효과.",
        tag: "전략",
    },
    {
        title: "연말 Tax-Loss Harvesting",
        desc: "12월 말 기준 미실현 손실 종목을 매도 후 재매수하여 당해 과세 소득을 줄이는 전략. 미국 Wash Sale Rule(30일) 주의.",
        tag: "연말",
    },
    {
        title: "ISA 계좌 활용",
        desc: "중개형 ISA 계좌에서 국내 주식 거래 시 비과세 한도(일반 200만원, 서민형 400만원) 적용. 3년 이상 유지 필수.",
        tag: "계좌",
    },
    {
        title: "IRP/연금저축 해외 ETF",
        desc: "연금계좌에서 해외 ETF 매수 시 매매차익·배당 과세 이연. 연간 세액공제(최대 900만원 납입분)도 함께 활용.",
        tag: "연금",
    },
    {
        title: "배당 기준일 전후 매매",
        desc: "배당소득세를 피하려면 배당 기준일 전 매도 후 배당락일에 재매수. 단, 주가 변동 리스크 감안 필요.",
        tag: "배당",
    },
    {
        title: "해외주식 250만원 공제",
        desc: "해외주식 양도세는 연간 250만원 기본공제. 부부 각각 적용되므로 분산 보유하면 공제 2배(500만원).",
        tag: "해외",
    },
    {
        title: "대주주 회피 (국내)",
        desc: "종목당 10억 이상 보유 시 대주주 양도세 과세. 연말 기준일 전 비중 조절로 대주주 요건 회피 가능.",
        tag: "국장",
    },
]

const KR_STT_RATE = { kospi: 0.0003, kosdaq: 0.0015 } as const
const KR_DIVIDEND_RATE = 0.154
const US_OVERSEAS_DEDUCTION = 2_500_000
const US_LONG_TERM_RATE = 0.22

const US_SHORT_BRACKETS = [
    { label: "6% 구간", rate: 0.06 },
    { label: "15% 구간", rate: 0.15 },
    { label: "24% 구간", rate: 0.24 },
    { label: "35% 구간", rate: 0.35 },
    { label: "38% 구간", rate: 0.38 },
    { label: "40% 구간", rate: 0.4 },
    { label: "42% 구간", rate: 0.42 },
    { label: "45% 구간", rate: 0.45 },
] as const

function parseAmount(raw: string): number {
    const n = Number(String(raw).replace(/,/g, "").replace(/\s/g, ""))
    return Number.isFinite(n) && n >= 0 ? n : 0
}

function parseSignedAmount(raw: string): number {
    const n = Number(String(raw).replace(/,/g, "").replace(/\s/g, ""))
    return Number.isFinite(n) ? n : 0
}

function formatKRW(n: number): string {
    if (!Number.isFinite(n)) return "0"
    return Math.round(n).toLocaleString("ko-KR")
}

function tradingValueWarning(value: number): { level: string; color: string; msg: string } | null {
    if (value <= 0) return null
    const billion = value / 1e8
    if (billion < 10) {
        return { level: "HIGH", color: "#EF4444", msg: `거래대금 ${billion.toFixed(0)}억 — 유동성 극히 낮음. 대량 매매 시 슬리피지 주의` }
    }
    if (billion < 50) {
        return { level: "MID", color: "#EAB308", msg: `거래대금 ${billion.toFixed(0)}억 — 중소형주 수준. 분할 매매 권장` }
    }
    if (billion < 200) {
        return { level: "LOW", color: "#22C55E", msg: `거래대금 ${billion.toFixed(0)}억 — 유동성 양호` }
    }
    return { level: "NONE", color: "#B5FF19", msg: `거래대금 ${(billion / 10000).toFixed(1)}조 — 대형주, 즉시 체결 가능` }
}

export default function TaxGuide(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [tab, setTab] = useState<Tab>("kr")
    const [expandedTip, setExpandedTip] = useState<number | null>(null)
    const [calcMode, setCalcMode] = useState<CalcMode>("kr_stt")
    const [krSellRaw, setKrSellRaw] = useState("")
    const [krMarket, setKrMarket] = useState<"kospi" | "kosdaq">("kospi")
    const [krDivRaw, setKrDivRaw] = useState("")
    const [usGainRaw, setUsGainRaw] = useState("")
    const [usLongTerm, setUsLongTerm] = useState(true)
    const [usShortBracketIdx, setUsShortBracketIdx] = useState(2)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const recs: any[] = data?.recommendations || []
    const topLiquidity = [...recs]
        .filter((r) => r.trading_value > 0)
        .sort((a, b) => a.trading_value - b.trading_value)
        .slice(0, 5)

    const taxRows = tab === "kr" ? KR_TAX : US_TAX

    const krSell = parseAmount(krSellRaw)
    const krSttRate = KR_STT_RATE[krMarket]
    const krSttTax = krSell * krSttRate
    const krDivAmount = parseAmount(krDivRaw)
    const krDivTax = krDivAmount * KR_DIVIDEND_RATE
    const usGain = parseSignedAmount(usGainRaw)
    let usEstTax = 0
    let usTaxableBase = 0
    if (usGain > 0) {
        if (usLongTerm) {
            usTaxableBase = Math.max(0, usGain - US_OVERSEAS_DEDUCTION)
            usEstTax = usTaxableBase * US_LONG_TERM_RATE
        } else {
            usTaxableBase = usGain
            const r = US_SHORT_BRACKETS[usShortBracketIdx]?.rate ?? 0.24
            usEstTax = usTaxableBase * r
        }
    }

    return (
        <div style={card}>
            <div style={header}>
                <span style={titleText}>세금 & 유동성 가이드</span>
            </div>

            {/* Tabs */}
            <div style={tabBar}>
                {([
                    { key: "kr" as Tab, label: "🇰🇷 한국" },
                    { key: "us" as Tab, label: "🇺🇸 미국" },
                    { key: "tips" as Tab, label: "💡 절세 팁" },
                    { key: "calc" as Tab, label: "🧮 계산기" },
                ]).map((t) => (
                    <button
                        key={t.key}
                        onClick={() => setTab(t.key)}
                        style={{
                            ...tabBtn,
                            color: tab === t.key ? "#B5FF19" : "#666",
                            borderBottom: tab === t.key ? "2px solid #B5FF19" : "2px solid transparent",
                        }}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            {/* Tax table */}
            {(tab === "kr" || tab === "us") && (
                <div style={{ padding: "12px 16px" }}>
                    <div style={tableHeader}>
                        <span style={{ ...tableHeaderCell, flex: 2 }}>항목</span>
                        <span style={{ ...tableHeaderCell, flex: 1, textAlign: "right" }}>세율</span>
                    </div>
                    {taxRows.map((row, i) => (
                        <div key={i} style={tableRow}>
                            <div style={{ flex: 2 }}>
                                <div style={rowLabel}>{row.label}</div>
                                <div style={rowNote}>{row.note}</div>
                            </div>
                            <div style={{ flex: 1, textAlign: "right" }}>
                                <span style={{
                                    ...rateBadge,
                                    color: row.rate === "비과세" ? "#22C55E" : "#fff",
                                    background: row.rate === "비과세" ? "rgba(34,197,94,0.12)" : "rgba(255,255,255,0.06)",
                                }}>
                                    {row.rate}
                                </span>
                            </div>
                        </div>
                    ))}

                    {tab === "kr" && (
                        <div style={disclaimerBox}>
                            금융투자소득세(금투세)는 2025년 시행 예정이었으나 2년 유예되었습니다. 2027년 이후 시행 여부를 확인하세요.
                        </div>
                    )}
                    {tab === "us" && (
                        <div style={disclaimerBox}>
                            해외주식 양도소득은 다음 해 5월 종합소득세 신고 시 직접 신고·납부해야 합니다. 증권사 대행 신고 서비스를 활용하세요.
                        </div>
                    )}
                </div>
            )}

            {/* Tax calculator */}
            {tab === "calc" && (
                <div style={{ padding: "12px 16px" }}>
                    <div style={calcModeRow}>
                        {([
                            { key: "kr_stt" as CalcMode, label: "국내 거래세" },
                            { key: "kr_div" as CalcMode, label: "국내 배당" },
                            { key: "us_gain" as CalcMode, label: "해외 양도" },
                        ]).map((m) => (
                            <button
                                key={m.key}
                                type="button"
                                onClick={() => setCalcMode(m.key)}
                                style={{
                                    ...calcModeBtn,
                                    color: calcMode === m.key ? "#B5FF19" : "#888",
                                    borderColor: calcMode === m.key ? "rgba(181,255,25,0.35)" : "#2a2a2a",
                                    background: calcMode === m.key ? "rgba(181,255,25,0.08)" : "#151515",
                                }}
                            >
                                {m.label}
                            </button>
                        ))}
                    </div>

                    {calcMode === "kr_stt" && (
                        <>
                            <label style={calcLabel}>매도 금액 (원)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                placeholder="예: 10000000"
                                value={krSellRaw}
                                onChange={(e) => setKrSellRaw(e.target.value)}
                                style={calcInput}
                            />
                            <div style={calcToggleRow}>
                                <span style={calcHint}>시장</span>
                                <div style={{ display: "flex", gap: 8 }}>
                                    {(["kospi", "kosdaq"] as const).map((mk) => (
                                        <button
                                            key={mk}
                                            type="button"
                                            onClick={() => setKrMarket(mk)}
                                            style={{
                                                ...calcPill,
                                                color: krMarket === mk ? "#111" : "#aaa",
                                                background: krMarket === mk ? "#B5FF19" : "#1a1a1a",
                                                borderColor: krMarket === mk ? "#B5FF19" : "#333",
                                            }}
                                        >
                                            {mk === "kospi" ? "KOSPI (0.03%)" : "KOSDAQ (0.15%)"}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div style={calcResultBox}>
                                <div style={calcResultRow}>
                                    <span style={calcResultLabel}>예상 증권거래세</span>
                                    <span style={calcResultValue}>{formatKRW(krSttTax)}원</span>
                                </div>
                                <div style={calcResultNote}>
                                    매도 체결금액 × {krMarket === "kospi" ? "0.03" : "0.15"}% (자동 원천징수 기준)
                                </div>
                            </div>
                        </>
                    )}

                    {calcMode === "kr_div" && (
                        <>
                            <label style={calcLabel}>배당 금액 (원, 세전)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                placeholder="예: 500000"
                                value={krDivRaw}
                                onChange={(e) => setKrDivRaw(e.target.value)}
                                style={calcInput}
                            />
                            <div style={calcResultBox}>
                                <div style={calcResultRow}>
                                    <span style={calcResultLabel}>예상 배당소득세 (15.4%)</span>
                                    <span style={calcResultValue}>{formatKRW(krDivTax)}원</span>
                                </div>
                                <div style={calcResultRow}>
                                    <span style={calcResultLabel}>세후 수령액 (추정)</span>
                                    <span style={{ ...calcResultValue, color: "#86EFAC" }}>
                                        {formatKRW(Math.max(0, krDivAmount - krDivTax))}원
                                    </span>
                                </div>
                                <div style={calcResultNote}>소득세 14% + 지방세 1.4% 단순 적용. 금융소득종합과세는 별도.</div>
                            </div>
                        </>
                    )}

                    {calcMode === "us_gain" && (
                        <>
                            <label style={calcLabel}>실현 손익 (원, 당해 연도)</label>
                            <input
                                type="text"
                                inputMode="decimal"
                                placeholder="매도 − 매수 − 수수료 등"
                                value={usGainRaw}
                                onChange={(e) => setUsGainRaw(e.target.value)}
                                style={calcInput}
                            />
                            <div style={calcToggleRow}>
                                <span style={calcHint}>보유 기간</span>
                                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                    <button
                                        type="button"
                                        onClick={() => setUsLongTerm(true)}
                                        style={{
                                            ...calcPill,
                                            color: usLongTerm ? "#111" : "#aaa",
                                            background: usLongTerm ? "#B5FF19" : "#1a1a1a",
                                            borderColor: usLongTerm ? "#B5FF19" : "#333",
                                        }}
                                    >
                                        1년 이상 (22% 분류)
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setUsLongTerm(false)}
                                        style={{
                                            ...calcPill,
                                            color: !usLongTerm ? "#111" : "#aaa",
                                            background: !usLongTerm ? "#B5FF19" : "#1a1a1a",
                                            borderColor: !usLongTerm ? "#B5FF19" : "#333",
                                        }}
                                    >
                                        1년 미만 (종합소득)
                                    </button>
                                </div>
                            </div>
                            {!usLongTerm && (
                                <div style={{ marginTop: 10 }}>
                                    <label style={calcLabel}>추정 종합소득세율 (단기)</label>
                                    <select
                                        value={usShortBracketIdx}
                                        onChange={(e) => setUsShortBracketIdx(Number(e.target.value))}
                                        style={calcSelect}
                                    >
                                        {US_SHORT_BRACKETS.map((b, i) => (
                                            <option key={b.label} value={i}>
                                                {b.label}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                            )}
                            <div style={calcResultBox}>
                                {usGain < 0 ? (
                                    <div style={{ ...calcResultNote, color: "#86EFAC", fontSize: 12 }}>
                                        실현 손실 — 해외주식 양도소득세 과세 대상 아님(이익과 통산은 종합소득세 신고 시).
                                    </div>
                                ) : usLongTerm ? (
                                    <>
                                        <div style={calcResultRow}>
                                            <span style={calcResultLabel}>과세표준 (250만 공제 후)</span>
                                            <span style={calcResultValue}>{formatKRW(usTaxableBase)}원</span>
                                        </div>
                                        <div style={calcResultRow}>
                                            <span style={calcResultLabel}>예상 세액 (22%)</span>
                                            <span style={calcResultValue}>{formatKRW(usEstTax)}원</span>
                                        </div>
                                    </>
                                ) : (
                                    <div style={calcResultRow}>
                                        <span style={calcResultLabel}>예상 세액 (선택 세율)</span>
                                        <span style={calcResultValue}>{formatKRW(usEstTax)}원</span>
                                    </div>
                                )}
                                {usGain >= 0 && (
                                    <div style={calcResultNote}>
                                        장기는 연 250만원 기본공제 후 22% 단순 모델입니다. 단기는 본인 추정 세율을 선택하세요. 실제는 다른 소득·공제에 따라 달라질 수 있습니다.
                                    </div>
                                )}
                            </div>
                        </>
                    )}

                    <div style={{ ...disclaimerBox, marginTop: 14 }}>
                        계산 결과는 참고용 추정치이며, 세법 개정·개인 상황에 따라 다릅니다.
                    </div>
                </div>
            )}

            {/* Tips */}
            {tab === "tips" && (
                <div style={{ padding: "12px 16px" }}>
                    {TAX_TIPS.map((tip, i) => {
                        const isOpen = expandedTip === i
                        return (
                            <div
                                key={i}
                                onClick={() => setExpandedTip(isOpen ? null : i)}
                                style={{
                                    ...tipCard,
                                    background: isOpen ? "#1A1A1A" : "transparent",
                                    cursor: "pointer",
                                }}
                            >
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                        <span style={tipTag}>{tip.tag}</span>
                                        <span style={tipTitle}>{tip.title}</span>
                                    </div>
                                    <span style={{ color: C.textTertiary, fontSize: 12, transition: "transform 0.2s", transform: isOpen ? "rotate(90deg)" : "rotate(0deg)" }}>
                                        ›
                                    </span>
                                </div>
                                {isOpen && (
                                    <div style={tipDesc}>{tip.desc}</div>
                                )}
                            </div>
                        )
                    })}
                </div>
            )}

            {/* Liquidity warnings */}
            {topLiquidity.length > 0 && (tab === "kr" || tab === "us") && (
                <div style={liquiditySection}>
                    <div style={liquiditySectionTitle}>유동성 경고 (거래대금 하위)</div>
                    {topLiquidity.map((r, i) => {
                        const warn = tradingValueWarning(r.trading_value)
                        if (!warn) return null
                        return (
                            <div key={i} style={liquidityRow}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    <span style={{ ...liquidityDot, background: warn.color }} />
                                    <span style={liquidityName}>{r.name}</span>
                                </div>
                                <span style={{ ...liquidityMsg, color: warn.color }}>{warn.msg}</span>
                            </div>
                        )
                    })}
                </div>
            )}

            <div style={footer}>
                본 세금 정보는 참고용이며, 정확한 세금 상담은 세무사에게 문의하세요.
            </div>
        </div>
    )
}

TaxGuide.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
}

addPropertyControls(TaxGuide, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    },
})

const font = FONT

const card: React.CSSProperties = {
    width: "100%",
    background: C.bgElevated,
    borderRadius: 16,
    border: `1px solid ${C.border}`,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: font,
}

const header: React.CSSProperties = {
    padding: "14px 16px",
    borderBottom: `1px solid ${C.border}`,
}

const titleText: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: 15,
    fontWeight: 700,
    fontFamily: font,
}

const tabBar: React.CSSProperties = {
    display: "flex",
    gap: 0,
    borderBottom: `1px solid ${C.border}`,
}

const tabBtn: React.CSSProperties = {
    flex: 1,
    padding: "10px 0",
    background: "none",
    border: "none",
    fontSize: 13,
    fontWeight: 600,
    fontFamily: font,
    cursor: "pointer",
}

const tableHeader: React.CSSProperties = {
    display: "flex",
    padding: "6px 0",
    borderBottom: `1px solid ${C.border}`,
    marginBottom: 4,
}

const tableHeaderCell: React.CSSProperties = {
    color: C.textTertiary,
    fontSize: 12,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: 1,
    fontFamily: font,
}

const tableRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    padding: "10px 0",
    borderBottom: `1px solid ${C.border}`,
}

const rowLabel: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: 13,
    fontWeight: 600,
    fontFamily: font,
}

const rowNote: React.CSSProperties = {
    color: C.textTertiary,
    fontSize: 12,
    marginTop: 2,
    fontFamily: font,
}

const rateBadge: React.CSSProperties = {
    display: "inline-block",
    fontSize: 12,
    fontWeight: 700,
    padding: "3px 10px",
    borderRadius: 6,
    fontFamily: font,
}

const disclaimerBox: React.CSSProperties = {
    marginTop: 12,
    padding: "10px 12px",
    background: "rgba(234,179,8,0.06)",
    borderRadius: 8,
    border: "1px solid rgba(234,179,8,0.15)",
    color: "#EAB308",
    fontSize: 12,
    lineHeight: "1.5",
    fontFamily: font,
}

const tipCard: React.CSSProperties = {
    padding: "10px 12px",
    borderBottom: `1px solid ${C.border}`,
    borderRadius: 8,
    transition: "background 0.15s",
}

const tipTag: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 700,
    color: "#B5FF19",
    background: "rgba(181,255,25,0.1)",
    padding: "2px 6px",
    borderRadius: 6,
    fontFamily: font,
}

const tipTitle: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: 13,
    fontWeight: 600,
    fontFamily: font,
}

const tipDesc: React.CSSProperties = {
    color: C.textSecondary,
    fontSize: 12,
    lineHeight: "1.6",
    marginTop: 8,
    fontFamily: font,
}

const liquiditySection: React.CSSProperties = {
    padding: "12px 16px",
    borderTop: `1px solid ${C.border}`,
}

const liquiditySectionTitle: React.CSSProperties = {
    color: C.textSecondary,
    fontSize: 12,
    fontWeight: 600,
    letterSpacing: 1,
    textTransform: "uppercase",
    marginBottom: 8,
    fontFamily: font,
}

const liquidityRow: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    padding: "6px 0",
    borderBottom: `1px solid ${C.border}`,
}

const liquidityDot: React.CSSProperties = {
    width: 6,
    height: 6,
    borderRadius: 3,
}

const liquidityName: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: 12,
    fontWeight: 600,
    fontFamily: font,
}

const liquidityMsg: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 500,
    paddingLeft: 14,
    fontFamily: font,
}

const footer: React.CSSProperties = {
    padding: "10px 16px",
    borderTop: `1px solid ${C.border}`,
    color: C.textTertiary,
    fontSize: 12,
    textAlign: "center",
    fontFamily: font,
}

const calcModeRow: React.CSSProperties = {
    display: "flex",
    gap: 8,
    marginBottom: 14,
    flexWrap: "wrap",
}

const calcModeBtn: React.CSSProperties = {
    flex: "1 1 auto",
    minWidth: 88,
    padding: "8px 10px",
    borderRadius: 8,
    border: "1px solid #2a2a2a",
    fontSize: 12,
    fontWeight: 600,
    fontFamily: font,
    cursor: "pointer",
}

const calcLabel: React.CSSProperties = {
    display: "block",
    color: C.textSecondary,
    fontSize: 12,
    fontWeight: 600,
    marginBottom: 6,
    fontFamily: font,
}

const calcInput: React.CSSProperties = {
    width: "100%",
    boxSizing: "border-box",
    padding: "10px 12px",
    borderRadius: 8,
    border: `1px solid ${C.border}`,
    background: "#0d0d0d",
    color: "#eee",
    fontSize: 14,
    fontFamily: font,
    marginBottom: 12,
    outline: "none",
}

const calcToggleRow: React.CSSProperties = {
    marginBottom: 12,
}

const calcHint: React.CSSProperties = {
    display: "block",
    color: C.textTertiary,
    fontSize: 12,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 8,
    fontFamily: font,
}

const calcPill: React.CSSProperties = {
    padding: "8px 12px",
    borderRadius: 8,
    border: `1px solid ${C.border}`,
    fontSize: 12,
    fontWeight: 600,
    fontFamily: font,
    cursor: "pointer",
}

const calcSelect: React.CSSProperties = {
    width: "100%",
    boxSizing: "border-box",
    padding: "10px 12px",
    borderRadius: 8,
    border: `1px solid ${C.border}`,
    background: "#0d0d0d",
    color: "#eee",
    fontSize: 13,
    fontFamily: font,
    marginBottom: 12,
    cursor: "pointer",
}

const calcResultBox: React.CSSProperties = {
    marginTop: 4,
    padding: "12px 14px",
    background: "rgba(181,255,25,0.06)",
    borderRadius: 10,
    border: "1px solid rgba(181,255,25,0.12)",
}

const calcResultRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    gap: 12,
    marginBottom: 8,
}

const calcResultLabel: React.CSSProperties = {
    color: C.textSecondary,
    fontSize: 12,
    fontFamily: font,
}

const calcResultValue: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: 16,
    fontWeight: 700,
    fontFamily: font,
}

const calcResultNote: React.CSSProperties = {
    color: C.textTertiary,
    fontSize: 12,
    lineHeight: 1.5,
    marginTop: 4,
    fontFamily: font,
}

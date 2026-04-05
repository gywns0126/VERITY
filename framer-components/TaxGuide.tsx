import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

interface Props {
    dataUrl: string
}

type Tab = "kr" | "us" | "tips"

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

    const recs: any[] = data?.recommendations || []
    const topLiquidity = [...recs]
        .filter((r) => r.trading_value > 0)
        .sort((a, b) => a.trading_value - b.trading_value)
        .slice(0, 5)

    const taxRows = tab === "kr" ? KR_TAX : US_TAX

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
                                    <span style={{ color: "#444", fontSize: 12, transition: "transform 0.2s", transform: isOpen ? "rotate(90deg)" : "rotate(0deg)" }}>
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
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
}

addPropertyControls(TaxGuide, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
})

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const card: React.CSSProperties = {
    width: "100%",
    background: "#111",
    borderRadius: 16,
    border: "1px solid #222",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: font,
}

const header: React.CSSProperties = {
    padding: "14px 16px",
    borderBottom: "1px solid #222",
}

const titleText: React.CSSProperties = {
    color: "#fff",
    fontSize: 15,
    fontWeight: 700,
    fontFamily: font,
}

const tabBar: React.CSSProperties = {
    display: "flex",
    gap: 0,
    borderBottom: "1px solid #222",
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
    borderBottom: "1px solid #222",
    marginBottom: 4,
}

const tableHeaderCell: React.CSSProperties = {
    color: "#555",
    fontSize: 10,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: 1,
    fontFamily: font,
}

const tableRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    padding: "10px 0",
    borderBottom: "1px solid #1a1a1a",
}

const rowLabel: React.CSSProperties = {
    color: "#ddd",
    fontSize: 13,
    fontWeight: 600,
    fontFamily: font,
}

const rowNote: React.CSSProperties = {
    color: "#666",
    fontSize: 10,
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
    fontSize: 11,
    lineHeight: "1.5",
    fontFamily: font,
}

const tipCard: React.CSSProperties = {
    padding: "10px 12px",
    borderBottom: "1px solid #1a1a1a",
    borderRadius: 8,
    transition: "background 0.15s",
}

const tipTag: React.CSSProperties = {
    fontSize: 9,
    fontWeight: 700,
    color: "#B5FF19",
    background: "rgba(181,255,25,0.1)",
    padding: "2px 6px",
    borderRadius: 4,
    fontFamily: font,
}

const tipTitle: React.CSSProperties = {
    color: "#ddd",
    fontSize: 13,
    fontWeight: 600,
    fontFamily: font,
}

const tipDesc: React.CSSProperties = {
    color: "#999",
    fontSize: 12,
    lineHeight: "1.6",
    marginTop: 8,
    fontFamily: font,
}

const liquiditySection: React.CSSProperties = {
    padding: "12px 16px",
    borderTop: "1px solid #222",
}

const liquiditySectionTitle: React.CSSProperties = {
    color: "#888",
    fontSize: 11,
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
    borderBottom: "1px solid #1a1a1a",
}

const liquidityDot: React.CSSProperties = {
    width: 6,
    height: 6,
    borderRadius: 3,
}

const liquidityName: React.CSSProperties = {
    color: "#ccc",
    fontSize: 12,
    fontWeight: 600,
    fontFamily: font,
}

const liquidityMsg: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 500,
    paddingLeft: 14,
    fontFamily: font,
}

const footer: React.CSSProperties = {
    padding: "10px 16px",
    borderTop: "1px solid #222",
    color: "#444",
    fontSize: 9,
    textAlign: "center",
    fontFamily: font,
}

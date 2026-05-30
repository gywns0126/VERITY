// ARENA Trade Turn — mockup v0 (2026-05-30)
// 디자인 preview only. 시뮬 logic / Kelly 계산 / VERITY 연결 모두 mock.
// 6/6 ARENA repo init 시 migrate.
// TIDE design system token share + ARENA 단순 모던 layer ([[project_tide_design_system_2026_05_27]]).

import { useState } from "react"

const colors = {
    bgPrimary: "#0a0a0a",
    bgElevated: "#141414",
    bgSubtle: "rgba(255,255,255,0.02)",
    textPrimary: "#ffffff",
    textSecondary: "#A8ABB2",
    textTertiary: "#6B6E76",
    textDisabled: "#4A4C52",
    gradeA: "#7fffa0",
    gradeB: "#FFD600",
    gradeC: "#FFA05A",
    gradeD: "#FF5A5A",
    riskSoft: "#FF7F7F",
    divider: "rgba(255,255,255,0.06)",
    border: "rgba(255,255,255,0.06)",
}

const fontBody = "'Pretendard', 'Inter', -apple-system, sans-serif"
const fontMono = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const fontHero = "'Lora', serif"

const labelStyle = {
    fontSize: 11,
    color: colors.textTertiary,
    textTransform: "uppercase" as const,
    letterSpacing: "0.04em",
    fontFamily: fontBody,
}

function gradeColor(g: string): string {
    if (g === "A") return colors.gradeA
    if (g === "B") return colors.gradeB
    if (g === "C") return colors.gradeC
    return colors.gradeD
}

const ASSET_BY_CATEGORY: Record<string, string> = {
    "KR ETF": "KODEX 200",
    "미장 ETF": "SPY",
    "코인": "BTC",
    "레버리지 ETF": "SOXL",
}

const CATEGORIES = ["KR ETF", "미장 ETF", "코인", "레버리지 ETF"]

export default function ArenaTradeTurn() {
    const [assetCategory, setAssetCategory] = useState("KR ETF")
    const [position, setPosition] = useState(25)
    const [leverage, setLeverage] = useState(7)

    // Mock data
    const capital = 100000000
    const turn = 1
    const totalTurns = 252
    const assetName = ASSET_BY_CATEGORY[assetCategory] || "KODEX 200"

    const brainGrade = "A"
    const brainScore = 78
    const brainLabel = "STRONG BUY"

    const positionSize = Math.round(capital * position / 100)
    const notional = positionSize * leverage
    const kellyHalf = 18
    const kellyFull = 36

    const formatKRW = (n: number) => "₩" + n.toLocaleString()

    const leverageAccent =
        leverage <= 3 ? colors.gradeA : leverage <= 6 ? colors.gradeC : colors.riskSoft

    return (
        <div
            style={{
                background: colors.bgPrimary,
                color: colors.textPrimary,
                fontFamily: fontBody,
                padding: 24,
                borderRadius: 8,
                border: "1px solid " + colors.border,
                maxWidth: 480,
                display: "flex",
                flexDirection: "column",
            }}
        >
            {/* Header — Turn / Capital */}
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    paddingBottom: 16,
                    borderBottom: "1px solid " + colors.divider,
                }}
            >
                <div>
                    <div style={labelStyle}>ARENA · TURN</div>
                    <div
                        style={{
                            fontSize: 14,
                            fontWeight: 600,
                            marginTop: 4,
                            fontFamily: fontMono,
                            fontVariantNumeric: "tabular-nums",
                        }}
                    >
                        {turn} / {totalTurns}
                    </div>
                </div>
                <div style={{ textAlign: "right" }}>
                    <div style={labelStyle}>CAPITAL</div>
                    <div
                        style={{
                            fontSize: 20,
                            fontFamily: fontHero,
                            fontWeight: 600,
                            marginTop: 4,
                            fontVariantNumeric: "tabular-nums",
                        }}
                    >
                        {formatKRW(capital)}
                    </div>
                </div>
            </div>

            {/* Asset selection */}
            <div
                style={{
                    paddingTop: 20,
                    paddingBottom: 16,
                    borderBottom: "1px solid " + colors.divider,
                }}
            >
                <div style={labelStyle}>ASSET</div>
                <div
                    style={{
                        display: "flex",
                        gap: 8,
                        marginTop: 8,
                        flexWrap: "wrap",
                    }}
                >
                    {CATEGORIES.map((cat) => {
                        const active = assetCategory === cat
                        return (
                            <button
                                key={cat}
                                onClick={() => setAssetCategory(cat)}
                                style={{
                                    background: active ? colors.textPrimary : colors.bgElevated,
                                    color: active ? colors.bgPrimary : colors.textPrimary,
                                    border: "none",
                                    padding: "6px 12px",
                                    borderRadius: 4,
                                    fontSize: 12,
                                    fontFamily: fontBody,
                                    fontWeight: 600,
                                    cursor: "pointer",
                                }}
                            >
                                {cat}
                            </button>
                        )
                    })}
                </div>
                <div
                    style={{
                        fontSize: 18,
                        fontWeight: 600,
                        marginTop: 12,
                        fontFamily: fontMono,
                    }}
                >
                    {assetName}
                </div>
            </div>

            {/* VERITY OPINION */}
            <div
                style={{
                    paddingTop: 20,
                    paddingBottom: 16,
                    borderBottom: "1px solid " + colors.divider,
                }}
            >
                <div style={labelStyle}>VERITY OPINION</div>
                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        marginTop: 8,
                        fontSize: 13,
                    }}
                >
                    <div
                        style={{
                            width: 8,
                            height: 8,
                            borderRadius: 4,
                            background: gradeColor(brainGrade),
                        }}
                    />
                    <span style={{ color: gradeColor(brainGrade), fontWeight: 600 }}>
                        {brainGrade}
                    </span>
                    <span style={{ color: colors.textSecondary }}>·</span>
                    <span style={{ color: colors.textPrimary, fontWeight: 600 }}>
                        {brainLabel}
                    </span>
                    <span style={{ color: colors.textSecondary }}>·</span>
                    <span
                        style={{
                            color: colors.textSecondary,
                            fontFamily: fontMono,
                            fontVariantNumeric: "tabular-nums",
                        }}
                    >
                        score {brainScore}
                    </span>
                </div>
            </div>

            {/* Position % slider */}
            <div
                style={{
                    paddingTop: 20,
                    paddingBottom: 16,
                    borderBottom: "1px solid " + colors.divider,
                }}
            >
                <div
                    style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                    }}
                >
                    <div style={labelStyle}>POSITION %</div>
                    <div
                        style={{
                            fontSize: 16,
                            fontWeight: 600,
                            fontFamily: fontMono,
                            fontVariantNumeric: "tabular-nums",
                        }}
                    >
                        {position}%
                    </div>
                </div>
                <input
                    type="range"
                    min={0}
                    max={100}
                    value={position}
                    onChange={(e) => setPosition(parseInt(e.target.value))}
                    style={{
                        width: "100%",
                        marginTop: 12,
                        accentColor: colors.gradeA,
                    }}
                />
            </div>

            {/* Leverage slider */}
            <div
                style={{
                    paddingTop: 20,
                    paddingBottom: 16,
                    borderBottom: "1px solid " + colors.divider,
                }}
            >
                <div
                    style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                    }}
                >
                    <div style={labelStyle}>LEVERAGE</div>
                    <div
                        style={{
                            fontSize: 16,
                            fontWeight: 600,
                            fontFamily: fontMono,
                            fontVariantNumeric: "tabular-nums",
                            color: leverageAccent,
                        }}
                    >
                        {leverage}x
                    </div>
                </div>
                <input
                    type="range"
                    min={1}
                    max={10}
                    value={leverage}
                    onChange={(e) => setLeverage(parseInt(e.target.value))}
                    style={{
                        width: "100%",
                        marginTop: 12,
                        accentColor: leverageAccent,
                    }}
                />
            </div>

            {/* Expected rows */}
            <div
                style={{
                    paddingTop: 20,
                    paddingBottom: 16,
                    borderBottom: "1px solid " + colors.divider,
                }}
            >
                <div style={labelStyle}>EXPECTED</div>
                <div
                    style={{
                        marginTop: 12,
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                    }}
                >
                    <Row label="Position size" value={formatKRW(positionSize)} />
                    <Row label={"Notional (" + leverage + "x)"} value={formatKRW(notional)} />
                    <Row
                        label="Kelly half / full"
                        value={kellyHalf + "% / " + kellyFull + "%"}
                        hint={
                            position < kellyHalf
                                ? "under"
                                : position > kellyFull
                                ? "over"
                                : "in range"
                        }
                        hintColor={
                            position < kellyHalf
                                ? colors.textTertiary
                                : position > kellyFull
                                ? colors.riskSoft
                                : colors.gradeA
                        }
                    />
                </div>
            </div>

            {/* Execute button */}
            <div style={{ marginTop: 20 }}>
                <button
                    style={{
                        width: "100%",
                        background: colors.gradeA,
                        color: colors.bgPrimary,
                        border: "none",
                        padding: "14px 24px",
                        borderRadius: 4,
                        fontSize: 14,
                        fontFamily: fontBody,
                        fontWeight: 700,
                        letterSpacing: "0.04em",
                        textTransform: "uppercase" as const,
                        cursor: "pointer",
                    }}
                >
                    Execute Turn
                </button>
            </div>

            {/* Footer disclaimer */}
            <div
                style={{
                    marginTop: 16,
                    paddingTop: 12,
                    fontSize: 11,
                    color: colors.textTertiary,
                    lineHeight: 1.5,
                    textAlign: "center",
                }}
            >
                ARENA mockup v0 · 시뮬 logic 미구현 · 디자인 preview only
            </div>
        </div>
    )
}

interface RowProps {
    label: string
    value: string
    hint?: string
    hintColor?: string
}

function Row(props: RowProps) {
    return (
        <div
            style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 13,
            }}
        >
            <span style={{ color: colors.textSecondary }}>{props.label}</span>
            <span
                style={{
                    color: colors.textPrimary,
                    fontWeight: 600,
                    fontFamily: fontMono,
                    fontVariantNumeric: "tabular-nums",
                }}
            >
                {props.value}
                {props.hint ? (
                    <span
                        style={{
                            color: props.hintColor || colors.textTertiary,
                            marginLeft: 6,
                            fontWeight: 400,
                        }}
                    >
                        ({props.hint})
                    </span>
                ) : null}
            </span>
        </div>
    )
}

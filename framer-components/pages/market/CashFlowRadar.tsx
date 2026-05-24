import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * CashFlowRadar — 자산 클래스 간 cross-asset 자금흐름 (옛 CapitalFlowRadar 재해석).
 *
 * 옛 CapitalFlowRadar 는 *섹터 자본 흐름* 이었고 MacroHub Flow 탭으로 흡수.
 * 본 컴포넌트는 *자산 클래스* (주식 / 채권 / 원자재 / 코인) 간 상대 강도 + 회전 시각화.
 *
 * 데이터 (portfolio.json):
 *   - macro.capital_flow: { equities/bonds/commodities score + flow_direction }
 *   - crypto_macro.composite.score (코인 0~100 종합)
 *   - macro.cross_asset_corr.pairs (5 자산 페어와이즈 30d corr)
 *   - macro.gold/silver/copper/wti_oil + sp500/nasdaq + us_10y/us_2y + usd_krw
 *
 * 디자인:
 *   - SVG 레이더 차트 4축 (Equities / Bonds / Commodities / Crypto, 0~100 score)
 *   - flow_direction narrative (어디서 어디로)
 *   - 자산별 chip (dominant + change_pct + score)
 *   - cross_asset_corr 미니 매트릭스 (5x5 색상 grid)
 *
 * 모던 심플 6원칙 + feedback_no_hardcode_position 적용.
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_normal: 1.5,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ─────────── Portfolio fetch ─────────── */
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000
function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}
function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    const timer = setTimeout(() => ac.abort(), PORTFOLIO_FETCH_TIMEOUT_MS)
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal: ac.signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
        .finally(() => clearTimeout(timer))
}


/* ─────────── 헬퍼 ─────────── */
function fmtPct(n: number | null | undefined, digits = 2): string {
    if (n == null || !Number.isFinite(n)) return "—"
    const sign = n > 0 ? "+" : ""
    return `${sign}${n.toFixed(digits)}%`
}

function pctColor(n: number | null | undefined): string {
    if (n == null || !Number.isFinite(n)) return C.textTertiary
    if (n > 0) return C.success
    if (n < 0) return C.danger
    return C.textTertiary
}

function scoreColor(score: number | null | undefined): string {
    if (score == null || !Number.isFinite(score)) return C.textTertiary
    if (score >= 65) return C.success
    if (score >= 50) return C.warn
    if (score >= 35) return C.textSecondary
    return C.danger
}

function corrColor(corr: number): string {
    /* corr 절대값 → 강한 동조(빨강) / 분리(파랑) / 중립(회색).
     * 양/음 부호 표시: 양수=동조, 음수=역동조. */
    const abs = Math.abs(corr)
    if (abs < 0.2) return "rgba(107,110,118,0.5)"  // tertiary 톤
    if (corr > 0) {
        if (abs >= 0.6) return "rgba(239,68,68,0.5)"  // danger 강
        return "rgba(245,158,11,0.4)"                  // warn 중
    } else {
        if (abs >= 0.6) return "rgba(91,169,255,0.5)" // info 강
        return "rgba(91,169,255,0.25)"                 // info 약
    }
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

interface Props {
    dataUrl: string
}

const ASSET_CLASSES = ["equities", "bonds", "commodities", "crypto"] as const
type AssetKey = typeof ASSET_CLASSES[number]

const ASSET_LABELS: Record<AssetKey, string> = {
    equities: "주식",
    bonds: "채권",
    commodities: "원자재",
    crypto: "코인",
}

const ASSET_DOMINANT_LABELS: Record<string, string> = {
    sp500: "S&P 500", nasdaq: "나스닥", dji: "다우", kospi: "코스피", kosdaq: "코스닥",
    us_10y: "미 10Y", us_2y: "미 2Y", kr_10y: "한 10Y",
    gold: "금", silver: "은", copper: "구리", wti_oil: "WTI 원유",
    btc: "BTC", eth: "ETH",
}

export default function CashFlowRadar({ dataUrl }: Props) {
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then((d) => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    if (!data) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>자금흐름 로딩 중…</span>
                </div>
            </div>
        )
    }

    const macro = data.macro || {}
    const cf = macro.capital_flow || {}
    const cryptoMacro = data.crypto_macro || {}

    /* 4 자산 클래스 score 추출 */
    const scores: Record<AssetKey, { score: number | null; change_pct: number | null; dominant: string | null }> = {
        equities: {
            score: cf.equities?.score ?? null,
            change_pct: cf.equities?.change_pct ?? null,
            dominant: cf.equities?.dominant ?? null,
        },
        bonds: {
            score: cf.bonds?.score ?? null,
            change_pct: cf.bonds?.change_pct ?? null,
            dominant: cf.bonds?.dominant ?? null,
        },
        commodities: {
            score: cf.commodities?.score ?? null,
            change_pct: cf.commodities?.change_pct ?? null,
            dominant: cf.commodities?.dominant ?? null,
        },
        crypto: {
            /* crypto_macro.composite 에서 추출. capital_flow 에 crypto 없음. */
            score: cryptoMacro.composite?.score ?? null,
            change_pct: cryptoMacro.fear_and_greed?.change ?? null,
            dominant: cryptoMacro.composite?.label ? "BTC" : null,  // 일단 BTC 가정 (Binance 차단 시 fallback)
        },
    }

    const flowDirection = cf.flow_direction as string | undefined
    const interpretation = cf.interpretation as string | undefined
    const corr = macro.cross_asset_corr || {}

    /* 우세 자산 (가장 높은 score) */
    const ranked = ASSET_CLASSES
        .map((k) => ({ key: k, score: scores[k].score ?? -1 }))
        .sort((a, b) => b.score - a.score)
    const dominant = ranked[0]
    const weakest = ranked[ranked.length - 1]

    return (
        <div style={shell}>
            {/* Header */}
            <div style={headerRow}>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={titleStyle}>자금흐름 레이더</span>
                    <span style={metaStyle}>
                        주식 · 채권 · 원자재 · 코인 cross-asset · cross-verdict 백테스트 대기 (Q2 사전 등록)
                    </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                    <span style={{ color: C.textTertiary, fontSize: T.cap }}>우세 자산</span>
                    <span style={{ ...MONO, color: C.accent, fontSize: T.body, fontWeight: T.w_bold }}>
                        {ASSET_LABELS[dominant.key as AssetKey]} {dominant.score >= 0 ? dominant.score : "—"}
                    </span>
                </div>
            </div>

            <div style={hr} />

            {/* Radar SVG (4축) */}
            <RadarChart scores={scores} />

            <div style={hr} />

            {/* 자산 클래스 chip 4개 */}
            <div style={chipGrid}>
                {ASSET_CLASSES.map((k) => {
                    const s = scores[k]
                    const domLabel = s.dominant ? (ASSET_DOMINANT_LABELS[s.dominant] || s.dominant) : "—"
                    return (
                        <div key={k} style={chipBox}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                                <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold }}>
                                    {ASSET_LABELS[k]}
                                </span>
                                <span style={{ ...MONO, color: scoreColor(s.score), fontSize: T.title, fontWeight: T.w_black }}>
                                    {s.score ?? "—"}
                                </span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                                <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                                    {domLabel}
                                </span>
                                <span style={{ ...MONO, color: pctColor(s.change_pct), fontSize: T.cap, fontWeight: T.w_semi }}>
                                    {fmtPct(s.change_pct)}
                                </span>
                            </div>
                        </div>
                    )
                })}
            </div>

            {/* Flow direction narrative */}
            {(flowDirection || interpretation) && (
                <>
                    <div style={hr} />
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        <span style={sectionCap}>회전 신호</span>
                        {flowDirection && (
                            <div style={{ display: "flex", alignItems: "center", gap: S.sm, flexWrap: "wrap" }}>
                                <span style={{ ...MONO, color: C.accent, fontSize: T.cap, fontWeight: T.w_bold, letterSpacing: 0.5, textTransform: "uppercase" }}>
                                    {flowDirection.replace(/_/g, " → ")}
                                </span>
                            </div>
                        )}
                        {interpretation && (
                            <span style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                                {interpretation}
                            </span>
                        )}
                    </div>
                </>
            )}

            {/* Cross-asset corr matrix */}
            {corr.available && corr.assets && corr.matrix && (
                <>
                    <div style={hr} />
                    <CorrMatrix assets={corr.assets} matrix={corr.matrix} windowDays={corr.window_days} />
                </>
            )}
        </div>
    )
}


/* ─────────── 레이더 차트 (4축 SVG) ─────────── */
function RadarChart({ scores }: { scores: Record<AssetKey, { score: number | null }> }) {
    const SIZE = 320
    const CENTER = SIZE / 2
    const MAX_R = 130
    /* 2026-05-16: 좌(코인) / 우(채권) 라벨 좌우 절반(약 22px) 가 viewBox 0/320 경계 밖에서
       잘리던 결함 정정. label 위치 = CENTER ± (MAX_R+22) = ±8/+312 → 라벨 폭 ~30px 이라
       음수/over-flow. viewBox 좌우 PAD_X 확장으로 라벨 공간 확보. SIZE 자체 그대로. */
    const PAD_X = 40
    const PAD_Y = 16

    /* 4축 — 12시 / 3시 / 6시 / 9시 (Equities / Bonds / Commodities / Crypto) */
    const angles: Record<AssetKey, number> = {
        equities: -90,
        bonds: 0,
        commodities: 90,
        crypto: 180,
    }

    const polar = (scoreVal: number | null, ang: number): [number, number] => {
        const r = ((scoreVal ?? 0) / 100) * MAX_R
        const rad = (ang * Math.PI) / 180
        return [CENTER + r * Math.cos(rad), CENTER + r * Math.sin(rad)]
    }

    const points = ASSET_CLASSES.map((k) => polar(scores[k].score, angles[k]))
    const polygonStr = points.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ")

    /* 등급 ring (25 / 50 / 75 / 100) */
    const rings = [25, 50, 75, 100]

    return (
        <div style={{ display: "flex", justifyContent: "center", padding: `${S.md}px 0` }}>
            <svg
                width={SIZE + PAD_X * 2}
                height={SIZE + PAD_Y * 2}
                viewBox={`${-PAD_X} ${-PAD_Y} ${SIZE + PAD_X * 2} ${SIZE + PAD_Y * 2}`}
                aria-label="자산 레이더"
            >
                {/* Rings */}
                {rings.map((r) => (
                    <circle
                        key={r}
                        cx={CENTER} cy={CENTER}
                        r={(r / 100) * MAX_R}
                        fill="none"
                        stroke={C.border}
                        strokeWidth={1}
                        strokeDasharray={r === 100 ? "none" : "2,3"}
                    />
                ))}
                {/* 4축 라인 */}
                {ASSET_CLASSES.map((k) => {
                    const [x, y] = polar(100, angles[k])
                    return (
                        <line
                            key={k}
                            x1={CENTER} y1={CENTER} x2={x} y2={y}
                            stroke={C.border}
                            strokeWidth={1}
                        />
                    )
                })}
                {/* 데이터 polygon */}
                <polygon
                    points={polygonStr}
                    fill="rgba(181,255,25,0.18)"
                    stroke={C.accent}
                    strokeWidth={2}
                    strokeLinejoin="round"
                />
                {/* 데이터 dot */}
                {ASSET_CLASSES.map((k, i) => (
                    <circle
                        key={k}
                        cx={points[i][0]}
                        cy={points[i][1]}
                        r={4}
                        fill={C.accent}
                    />
                ))}
                {/* Axis labels */}
                {ASSET_CLASSES.map((k) => {
                    const [x, y] = polar(100, angles[k])
                    /* label 위치는 약간 바깥쪽 */
                    const ang = angles[k]
                    const rad = (ang * Math.PI) / 180
                    const lx = CENTER + (MAX_R + 22) * Math.cos(rad)
                    const ly = CENTER + (MAX_R + 22) * Math.sin(rad)
                    return (
                        <text
                            key={k}
                            x={lx} y={ly}
                            fill={C.textSecondary}
                            fontSize={13}
                            fontWeight={600}
                            fontFamily={FONT}
                            textAnchor="middle"
                            dominantBaseline="middle"
                        >
                            {ASSET_LABELS[k]}
                        </text>
                    )
                })}
                {/* Score labels at each dot */}
                {ASSET_CLASSES.map((k, i) => {
                    const sc = scores[k].score
                    if (sc == null) return null
                    return (
                        <text
                            key={`s-${k}`}
                            x={points[i][0]}
                            y={points[i][1] - 12}
                            fill={C.accent}
                            fontSize={11}
                            fontWeight={700}
                            fontFamily={FONT_MONO}
                            textAnchor="middle"
                        >
                            {sc}
                        </text>
                    )
                })}
            </svg>
        </div>
    )
}


/* ─────────── Cross-asset corr 매트릭스 ─────────── */
function CorrMatrix({ assets, matrix, windowDays }: {
    assets: string[]
    matrix: Record<string, Record<string, number>>
    windowDays?: number
}) {
    const ASSET_KR: Record<string, string> = {
        stock: "주식", bond_yield: "10Y", gold: "금", usd: "달러", oil: "원유",
    }
    const cellSize = 48

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={sectionCap}>자산 상관계수</span>
                <span style={{ color: C.textTertiary, fontSize: 10, ...MONO }}>
                    {windowDays ? `${windowDays}일 rolling` : ""}
                </span>
            </div>
            <div style={{ overflowX: "auto" }}>
                <div style={{ display: "inline-block" }}>
                    {/* Header row */}
                    <div style={{ display: "flex", marginLeft: cellSize }}>
                        {assets.map((a) => (
                            <div key={a} style={{
                                width: cellSize, height: 24,
                                display: "flex", alignItems: "center", justifyContent: "center",
                                color: C.textTertiary, fontSize: 11, fontFamily: FONT,
                            }}>
                                {ASSET_KR[a] || a}
                            </div>
                        ))}
                    </div>
                    {/* Body rows */}
                    {assets.map((rowKey) => (
                        <div key={rowKey} style={{ display: "flex" }}>
                            <div style={{
                                width: cellSize, height: cellSize,
                                display: "flex", alignItems: "center", justifyContent: "center",
                                color: C.textTertiary, fontSize: 11, fontFamily: FONT,
                            }}>
                                {ASSET_KR[rowKey] || rowKey}
                            </div>
                            {assets.map((colKey) => {
                                const v = matrix[rowKey]?.[colKey] ?? 0
                                const isDiag = rowKey === colKey
                                const bg = isDiag ? C.bgElevated : corrColor(v)
                                return (
                                    <div key={colKey} style={{
                                        width: cellSize, height: cellSize,
                                        display: "flex", alignItems: "center", justifyContent: "center",
                                        background: bg,
                                        borderRadius: 4,
                                        margin: 1,
                                        color: isDiag ? C.textTertiary : C.textPrimary,
                                        fontSize: 11,
                                        fontWeight: T.w_semi,
                                        ...MONO,
                                    }}>
                                        {isDiag ? "·" : v.toFixed(2)}
                                    </div>
                                )
                            })}
                        </div>
                    ))}
                </div>
            </div>
            <span style={{ color: C.textTertiary, fontSize: 10, lineHeight: 1.5 }}>
                양수 = 동조 / 음수 = 역동조 / |corr| ≥ 0.6 = 강한 신호
            </span>
        </div>
    )
}


/* ─────────── Property Controls ─────────── */
const DEFAULT_PORTFOLIO_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json"

CashFlowRadar.defaultProps = {
    dataUrl: DEFAULT_PORTFOLIO_URL,
}

addPropertyControls(CashFlowRadar, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: DEFAULT_PORTFOLIO_URL,
    },
})


/* ─────────── 스타일 ─────────── */
const shell: CSSProperties = {
    width: "100%",
    fontFamily: FONT,
    color: C.textPrimary,
    background: C.bgPage,
    padding: S.xl,
    display: "flex",
    flexDirection: "column",
    gap: S.lg,
    boxSizing: "border-box",
}

const loadingBox: CSSProperties = {
    padding: `${S.xl}px 0`,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
}

const headerRow: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: S.md,
}

const titleStyle: CSSProperties = {
    fontSize: T.h2,
    fontWeight: T.w_bold,
    color: C.textPrimary,
}

const metaStyle: CSSProperties = {
    fontSize: T.cap,
    color: C.textTertiary,
    fontWeight: T.w_med,
}

const sectionCap: CSSProperties = {
    fontSize: T.cap,
    color: C.textTertiary,
    fontWeight: T.w_med,
    letterSpacing: 0.5,
    textTransform: "uppercase",
}

const hr: CSSProperties = {
    height: 1,
    background: C.border,
    margin: 0,
}

const chipGrid: CSSProperties = {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
    gap: S.md,
}

const chipBox: CSSProperties = {
    padding: `${S.md}px ${S.lg}px`,
    background: C.bgCard,
    borderRadius: R.md,
    display: "flex",
    flexDirection: "column",
}

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"
const BG = "#000"
const CARD = "#111"
const BORDER = "#222"
const MUTED = "#8B95A1"
const UP = "#22C55E"
const DOWN = "#EF4444"
const WARN = "#F59E0B"
const BLUE = "#3B82F6"
const PURPLE = "#8B5CF6"

interface FactorScores {
    momentum: number | null
    value: number | null
    quality: number | null
    liquidity: number | null
}

interface ETFDetail {
    ticker: string
    name: string
    category: string
    verity_etf_score: number | null
    signal: string | null
    factor_scores: FactorScores
    close: number | null
    change_pct: number | null
    aum: number | null
    expense_ratio: number | null
    dividend_yield: number | null
    returns: Record<string, number | null>
}

interface Props { dataUrl: string }

const F_COLOR: Record<string, string> = { momentum: BLUE, value: PURPLE, quality: UP, liquidity: WARN }
const F_LABEL: Record<string, string> = { momentum: "모멘텀", value: "밸류", quality: "퀄리티", liquidity: "유동성" }
const FACTORS = ["momentum", "value", "quality", "liquidity"] as const

function FactorRadar({ scores }: { scores: FactorScores }) {
    const S = 96, CX = S / 2, CY = S / 2, R = 36
    const N = FACTORS.length
    const angle = (i: number) => (Math.PI * 2 * i) / N - Math.PI / 2
    const pt = (i: number, r: number) => ({ x: CX + r * Math.cos(angle(i)), y: CY + r * Math.sin(angle(i)) })

    const scorePts = FACTORS.map((f, i) => pt(i, ((scores[f] ?? 0) / 100) * R))
    const poly = scorePts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")
    const grid = (lv: number) => FACTORS.map((_, i) => pt(i, R * lv)).map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")

    return (
        <svg width={S} height={S} viewBox={`0 0 ${S} ${S}`}>
            {[0.33, 0.67, 1].map((l, i) => <polygon key={i} points={grid(l)} fill="none" stroke={BORDER} strokeWidth={1} />)}
            {FACTORS.map((_, i) => { const o = pt(i, R); return <line key={i} x1={CX} y1={CY} x2={o.x} y2={o.y} stroke={BORDER} strokeWidth={1} /> })}
            <polygon points={poly} fill={BLUE + "33"} stroke={BLUE} strokeWidth={1.5} />
            {FACTORS.map((f, i) => {
                const o = pt(i, R + 9)
                return <text key={f} x={o.x} y={o.y + 3} textAnchor="middle" fill={MUTED} fontSize={7} fontFamily={font}>{F_LABEL[f]}</text>
            })}
        </svg>
    )
}

function FactorBars({ scores }: { scores: FactorScores }) {
    return (
        <div style={{ display: "flex", flexDirection: "column" as const, gap: 4 }}>
            {FACTORS.map((f) => {
                const val = scores[f] ?? 0
                return (
                    <div key={f}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 1 }}>
                            <span style={{ fontSize: 9, color: MUTED, fontFamily: font }}>{F_LABEL[f]}</span>
                            <span style={{ fontSize: 9, color: F_COLOR[f], fontVariantNumeric: "tabular-nums", fontFamily: font }}>{val.toFixed(0)}</span>
                        </div>
                        <div style={{ height: 3, background: BORDER, borderRadius: 2 }}>
                            <div style={{ height: "100%", width: `${val}%`, background: F_COLOR[f], borderRadius: 2, transition: "width 0.5s ease" }} />
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

function DetailCard({ etf, onClose }: { etf: ETFDetail; onClose: () => void }) {
    const fs = etf.factor_scores ?? { momentum: 0, value: 0, quality: 0, liquidity: 0 }
    const score = etf.verity_etf_score
    const scoreColor = score != null && score >= 60 ? UP : score != null && score >= 45 ? WARN : DOWN

    return (
        <div style={{ position: "absolute" as const, top: 0, left: 0, right: 0, bottom: 0, background: BG, borderRadius: 12, padding: 14, zIndex: 10, overflow: "auto" as const }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                <div>
                    <div style={{ fontSize: 15, fontWeight: 800, color: "#FFF", fontFamily: font }}>{etf.ticker}</div>
                    <div style={{ fontSize: 11, color: MUTED, marginTop: 1, fontFamily: font }}>{etf.name}</div>
                </div>
                <button onClick={onClose} style={{ background: CARD, border: `1px solid ${BORDER}`, color: MUTED, borderRadius: 5, padding: "3px 9px", cursor: "pointer", fontSize: 11, fontFamily: font }}>닫기</button>
            </div>

            <div style={{ display: "flex", gap: 14, alignItems: "center", marginBottom: 14 }}>
                <FactorRadar scores={fs} />
                <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 28, fontWeight: 900, fontVariantNumeric: "tabular-nums", color: scoreColor, fontFamily: font }}>{score?.toFixed(0) ?? "—"}</div>
                    <div style={{ fontSize: 10, color: MUTED, marginBottom: 6, fontFamily: font }}>VERITY ETF SCORE</div>
                    <FactorBars scores={fs} />
                </div>
            </div>

            <div style={{ background: CARD, borderRadius: 8, padding: "8px 10px", marginBottom: 8, border: `1px solid ${BORDER}` }}>
                {[
                    { label: "현재가", val: etf.close != null ? etf.close.toLocaleString() : "—" },
                    { label: "등락률", val: etf.change_pct != null ? `${etf.change_pct > 0 ? "+" : ""}${etf.change_pct.toFixed(2)}%` : "—" },
                    { label: "순자산(AUM)", val: etf.aum != null ? etf.aum.toLocaleString() : "—" },
                    { label: "총보수(TER)", val: etf.expense_ratio != null ? `${(etf.expense_ratio * 100).toFixed(2)}%` : "—" },
                    { label: "배당수익률", val: etf.dividend_yield != null ? `${(etf.dividend_yield * 100).toFixed(2)}%` : "—" },
                ].map(({ label, val }) => (
                    <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: `1px solid ${BORDER}` }}>
                        <span style={{ fontSize: 11, color: MUTED, fontFamily: font }}>{label}</span>
                        <span style={{ fontSize: 11, color: "#E5E5E5", fontVariantNumeric: "tabular-nums", fontFamily: font }}>{val}</span>
                    </div>
                ))}
            </div>

            <div style={{ background: CARD, borderRadius: 8, padding: "8px 10px", border: `1px solid ${BORDER}` }}>
                <div style={{ fontSize: 9, color: MUTED, marginBottom: 6, textTransform: "uppercase" as const, letterSpacing: 0.8, fontWeight: 700, fontFamily: font }}>기간별 수익률</div>
                <div style={{ display: "flex", gap: 4 }}>
                    {["1M", "3M", "6M", "1Y"].map((p) => {
                        const val = etf.returns?.[p]
                        const color = val == null ? MUTED : val >= 0 ? UP : DOWN
                        return (
                            <div key={p} style={{ flex: 1, background: BG, borderRadius: 5, padding: "5px 3px", textAlign: "center" as const }}>
                                <div style={{ fontSize: 8, color: MUTED, marginBottom: 2, fontFamily: font }}>{p}</div>
                                <div style={{ fontSize: 11, fontWeight: 700, color, fontVariantNumeric: "tabular-nums", fontFamily: font }}>
                                    {val != null ? `${val > 0 ? "+" : ""}${val.toFixed(1)}%` : "—"}
                                </div>
                            </div>
                        )
                    })}
                </div>
            </div>
        </div>
    )
}

export default function ETFScreenerPanel(props: Props) {
    const { dataUrl } = props
    const [etfs, setEtfs] = useState<ETFDetail[]>([])
    const [loading, setLoading] = useState(true)
    const [selected, setSelected] = useState<ETFDetail | null>(null)
    const [minScore, setMinScore] = useState(0)
    const [bondOnly, setBondOnly] = useState(false)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then((data) => {
            if (ac.signal.aborted) return
            const screened = data.etfs?.overall_top20 ?? [...(data.etfs?.kr_top ?? []), ...(data.etfs?.us_top ?? []), ...(data.etfs?.us_bond ?? [])]
            setEtfs(screened)
            setLoading(false)
        }).catch(() => { if (!ac.signal.aborted) setLoading(false) })
        return () => ac.abort()
    }, [dataUrl])

    const filtered = etfs.filter((e) => {
        if ((e.verity_etf_score ?? 0) < minScore) return false
        if (bondOnly && !(e.category || "").includes("bond")) return false
        return true
    })

    return (
        <div style={{ ...wrap, position: "relative" as const }}>
            {selected && <DetailCard etf={selected} onClose={() => setSelected(null)} />}

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: "#FFF", fontFamily: font }}>ETF 스크리너</span>
                <span style={{ fontSize: 10, color: MUTED, fontFamily: font }}>{filtered.length}개</span>
            </div>

            <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center" }}>
                <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 9, color: MUTED, marginBottom: 2, fontFamily: font }}>최소 스코어: {minScore}+</div>
                    <input type="range" min={0} max={80} step={5} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} style={{ width: "100%", accentColor: BLUE }} />
                </div>
                <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: MUTED, cursor: "pointer", whiteSpace: "nowrap" as const, fontFamily: font }}>
                    <input type="checkbox" checked={bondOnly} onChange={(e) => setBondOnly(e.target.checked)} style={{ accentColor: BLUE }} />
                    채권형
                </label>
            </div>

            {loading ? (
                <div style={{ textAlign: "center" as const, color: MUTED, padding: 20, fontSize: 12, fontFamily: font }}>로딩 중...</div>
            ) : (
                <div style={{ display: "flex", flexDirection: "column" as const, gap: 5, flex: 1, minHeight: 0, overflowY: "auto" as const }}>
                    {filtered.map((etf) => {
                        const score = etf.verity_etf_score ?? 0
                        const scoreColor = score >= 60 ? UP : score >= 45 ? WARN : DOWN
                        return (
                            <div key={etf.ticker} onClick={() => setSelected(etf)} style={{
                                background: CARD, borderRadius: 8, padding: "9px 10px", cursor: "pointer",
                                display: "flex", alignItems: "center", gap: 9,
                                border: `1px solid ${BORDER}`, transition: "border-color 0.15s ease",
                            }}>
                                <div style={{
                                    width: 36, height: 36, borderRadius: "50%", flexShrink: 0,
                                    background: `conic-gradient(${scoreColor} ${score * 3.6}deg, ${BORDER} 0deg)`,
                                    display: "flex", alignItems: "center", justifyContent: "center",
                                }}>
                                    <div style={{
                                        width: 26, height: 26, borderRadius: "50%", background: CARD,
                                        display: "flex", alignItems: "center", justifyContent: "center",
                                        fontSize: 9, fontWeight: 800, color: "#E5E5E5", fontFamily: font,
                                    }}>{score.toFixed(0)}</div>
                                </div>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                        <span style={{ fontSize: 11, fontWeight: 700, color: "#93C5FD", fontFamily: font }}>{etf.ticker}</span>
                                        <span style={{
                                            fontSize: 10, fontWeight: 600, fontVariantNumeric: "tabular-nums", fontFamily: font,
                                            color: (etf.change_pct ?? 0) >= 0 ? UP : DOWN,
                                        }}>
                                            {etf.change_pct != null ? `${etf.change_pct > 0 ? "+" : ""}${etf.change_pct.toFixed(2)}%` : "—"}
                                        </span>
                                    </div>
                                    <div style={{ fontSize: 10, color: MUTED, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const, fontFamily: font }}>{etf.name}</div>
                                    <div style={{ display: "flex", gap: 2, marginTop: 4 }}>
                                        {FACTORS.map((f) => (
                                            <div key={f} style={{ flex: 1, height: 3, background: BORDER, borderRadius: 1 }}>
                                                <div style={{ height: "100%", width: `${etf.factor_scores?.[f] ?? 0}%`, background: F_COLOR[f], borderRadius: 1 }} />
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}
        </div>
    )
}

ETFScreenerPanel.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
}

addPropertyControls(ETFScreenerPanel, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json" },
})

const wrap: React.CSSProperties = { width: "100%", height: "100%", boxSizing: "border-box" as const, background: BG, borderRadius: 12, padding: 14, fontFamily: font, color: "#E5E5E5", display: "flex", flexDirection: "column" as const, overflow: "hidden" }

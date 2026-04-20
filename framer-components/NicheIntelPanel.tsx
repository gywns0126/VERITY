import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"
import type { CSSProperties } from "react"

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


/** Framer에 이 파일만 넣을 때를 위해 fetch 인라인 (fetchPortfolioJson.ts와 동일) */
function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

// WARN-24: 15초 timeout + AbortController — 네트워크 hang 방지
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000

function _withTimeout<T>(p: Promise<T>, ms: number, ac: AbortController): Promise<T> {
    const timer = setTimeout(() => ac.abort(), ms)
    return p.finally(() => clearTimeout(timer))
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    return _withTimeout(
        fetch(bustPortfolioUrl(url), {
            cache: "no-store",
            mode: "cors",
            credentials: "omit",
            signal: ac.signal,
        })
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.text()
            })
            .then((txt) =>
                JSON.parse(
                    txt
                        .replace(/\bNaN\b/g, "null")
                        .replace(/\bInfinity\b/g, "null")
                        .replace(/-null/g, "null"),
                ),
            ),
        PORTFOLIO_FETCH_TIMEOUT_MS,
        ac,
    )
}

function normalizeStockIndex(v: unknown): number {
    const n = typeof v === "number" ? v : Number(v)
    if (!Number.isFinite(n) || n < 0) return 0
    return Math.floor(n)
}

function _isUS(r: any): boolean {
    return r?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r?.market || "")
}

interface Props {
    dataUrl: string
    stockIndex: number
    market: "kr" | "us"
}

export default function NicheIntelPanel(props: Props) {
    const { dataUrl, stockIndex } = props
    const [data, setData] = useState<any>(null)
    const [activeIndex, setActiveIndex] = useState(() =>
        normalizeStockIndex(stockIndex),
    )

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    useEffect(() => {
        setActiveIndex(normalizeStockIndex(stockIndex))
    }, [stockIndex])

    useEffect(() => {
        if (!data) return
        const m = Math.max(0, (data.recommendations || []).length - 1)
        setActiveIndex((i) => Math.min(Math.max(0, i), m))
    }, [data])

    if (!data) {
        return (
            <div style={{ ...panelWrap, minHeight: 200, justifyContent: "center", alignItems: "center" }}>
                <span style={{ color: C.textTertiary, fontSize: 13 }}>데이터 로딩 중...</span>
            </div>
        )
    }

    const isUS = props.market === "us"
    const allRecs: any[] = data?.recommendations || []
    const recs: any[] = allRecs.filter((r: any) => isUS ? _isUS(r) : !_isUS(r))
    const maxIdx = Math.max(0, recs.length - 1)
    const idx = Math.min(Math.max(0, activeIndex), maxIdx)
    const stock = recs[idx]

    const macro = data?.macro || {}
    if (!stock) {
        return (
            <div style={{ ...panelWrap, minHeight: 120, justifyContent: "center", alignItems: "center" }}>
                <span style={{ color: C.textTertiary, fontSize: 13 }}>종목을 선택하세요</span>
            </div>
        )
    }

    const n = stock?.niche_data || {}
    const mc = macro?.niche_credit || {}
    const secFilings: any[] = stock?.sec_filings || []
    const insiderSent = stock?.insider_sentiment || {}
    const instOwn = stock?.institutional_ownership || {}
    const finFacts = stock?.sec_financials || stock?.financial_facts || {}
    const hasUSData = secFilings.length > 0 || insiderSent.mspr != null || instOwn.total_holders > 0 || finFacts.fcf != null
    const hasAny =
        (n.trends && Object.keys(n.trends).length > 0) ||
        (n.legal && (n.legal.hits?.length > 0 || n.legal.risk_flag)) ||
        (n.credit && (n.credit.ig_spread_pp != null || n.credit.debt_ratio_pct != null || n.credit.note)) ||
        (mc.corporate_spread_vs_gov_pp != null || mc.alert) ||
        (isUS && hasUSData)

    return (
        <div style={panelWrap}>
            <div style={headBlock}>
                <div style={headRow}>
                    <span style={title}>
                        {String(
                            stock?.name ??
                                stock?.ticker ??
                                `종목 #${idx + 1}`,
                        )}{" "}
                        — {isUS ? "Deep Intel" : "틈새 정보"}
                    </span>
                    {n.updated_at && <span style={sub}>갱신 {n.updated_at}</span>}
                </div>
                {recs.length > 1 && (
                    <div style={switcherRow}>
                        <button
                            type="button"
                            style={navBtn}
                            onClick={() => setActiveIndex((i) => Math.max(0, i - 1))}
                            disabled={idx <= 0}
                            aria-label="이전 종목"
                        >
                            ‹
                        </button>
                        <select
                            style={stockSelect}
                            value={String(idx)}
                            onChange={(e) =>
                                setActiveIndex(Number(e.target.value))
                            }
                            aria-label="추천 목록에서 종목 선택"
                        >
                            {recs.map((r: any, i: number) => (
                                <option key={i} value={String(i)}>
                                    {String(
                                        r?.name ||
                                            r?.ticker ||
                                            `#${i + 1}`,
                                    )}
                                </option>
                            ))}
                        </select>
                        <span style={indexHint}>
                            {idx + 1} / {recs.length}
                        </span>
                        <button
                            type="button"
                            style={navBtn}
                            onClick={() =>
                                setActiveIndex((i) => Math.min(maxIdx, i + 1))
                            }
                            disabled={idx >= maxIdx}
                            aria-label="다음 종목"
                        >
                            ›
                        </button>
                    </div>
                )}
            </div>

            {!hasAny && (
                <div style={emptyBox}>
                    <span style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.5 }}>
                        이 종목에 대한 틈새 데이터(트렌드·법 리스크·신용)는 백엔드 수집기 연동 후 표시됩니다.
                    </span>
                </div>
            )}

            {/* Trends */}
            <div style={card}>
                <div style={cardHead}>
                    <span style={chip}>Trends</span>
                    <span style={cardTitle}>검색·관심도</span>
                </div>
                {n.trends?.keyword || n.trends?.interest_index != null ? (
                    <div style={cardBody}>
                        <Row label="키워드" value={n.trends.keyword || "—"} />
                        <Row label="관심 지수" value={String(n.trends.interest_index ?? "—")} />
                        {n.trends.week_change_pct != null && (
                            <Row
                                label="주간 변화"
                                value={`${n.trends.week_change_pct >= 0 ? "+" : ""}${n.trends.week_change_pct}%`}
                                color={n.trends.week_change_pct >= 0 ? C.up : C.down}
                            />
                        )}
                        {n.trends.note && <p style={note}>{n.trends.note}</p>}
                    </div>
                ) : (
                    <span style={muted}>주 1회 수집 예정 (소비·게임·뷰티 등)</span>
                )}
            </div>

            {/* Risk */}
            <div style={card}>
                <div style={cardHead}>
                    <span style={chip}>Risk</span>
                    <span style={cardTitle}>소송·리스크 키워드</span>
                </div>
                {n.legal?.risk_flag && (
                    <div style={{ background: "#1A0A0A", border: "1px solid #3A1515", borderRadius: 8, padding: "8px 10px", marginBottom: 8 }}>
                        <span style={{ color: "#FF4D4D", fontSize: 12, fontWeight: 700 }}>리스크 플래그 ON</span>
                    </div>
                )}
                {n.legal?.hits?.length > 0 ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {n.legal.hits.slice(0, 6).map((h: any, i: number) => (
                            <div key={i} style={newsRow}>
                                <span
                                    style={{
                                        color: C.textSecondary,
                                        fontSize: 12,
                                        lineHeight: 1.45,
                                    }}
                                >
                                    {typeof h === "string"
                                        ? h
                                        : h != null
                                          ? String(h)
                                          : "—"}
                                </span>
                            </div>
                        ))}
                    </div>
                ) : (
                    <span style={muted}>뉴스 RSS에서 소송·판결·가압류 등 매칭 시 표시</span>
                )}
            </div>

            {/* Credit */}
            <div style={card}>
                <div style={cardHead}>
                    <span style={chip}>Credit</span>
                    <span style={cardTitle}>신용·유동성</span>
                </div>
                <div style={cardBody}>
                    {n.credit?.ig_spread_pp != null && (
                        <Row label="IG 스프레드" value={`${n.credit.ig_spread_pp}%p`} />
                    )}
                    {n.credit?.debt_ratio_pct != null && (
                        <Row
                            label="부채비율"
                            value={`${n.credit.debt_ratio_pct.toFixed(0)}%`}
                            color={n.credit.debt_ratio_pct > 100 ? "#FF4D4D" : "#22C55E"}
                        />
                    )}
                    {n.credit?.alert && (
                        <div style={{ color: "#FF9F40", fontSize: 12, marginTop: 6 }}>종목 단위 신용 알림</div>
                    )}
                    {n.credit?.note && <p style={note}>{n.credit.note}</p>}
                    {(mc.corporate_spread_vs_gov_pp != null || mc.alert) && (
                        <div style={{ borderTop: `1px solid ${C.border}`, marginTop: 10, paddingTop: 10 }}>
                            <span style={{ color: C.textTertiary, fontSize: 12, display: "block", marginBottom: 6 }}>시장 (macro.niche_credit)</span>
                            {mc.corporate_spread_vs_gov_pp != null && (
                                <Row
                                    label="회사채-국고 스프레드"
                                    value={`${mc.corporate_spread_vs_gov_pp}%p${mc.alert ? " · 경고" : ""}`}
                                    color={mc.alert || mc.corporate_spread_vs_gov_pp >= 2 ? "#FF4D4D" : "#22C55E"}
                                />
                            )}
                            {mc.updated_at && <span style={{ color: C.textTertiary, fontSize: 12 }}>{mc.updated_at}</span>}
                        </div>
                    )}
                    {n.credit?.ig_spread_pp == null && n.credit?.debt_ratio_pct == null && mc.corporate_spread_vs_gov_pp == null && !mc.alert && (
                        <span style={muted}>중소형주는 개별 데이터가 없을 수 있음. 시장 전체 지표 위주.</span>
                    )}
                </div>
            </div>

            {isUS && (
                <>
                    {/* SEC Filings */}
                    <div style={card}>
                        <div style={cardHead}>
                            <span style={chip}>SEC</span>
                            <span style={cardTitle}>Recent Filings</span>
                        </div>
                        {secFilings.length > 0 ? (
                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                {secFilings.slice(0, 5).map((f: any, i: number) => (
                                    <div key={i} style={bidRow}>
                                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                            <span style={{ color: "#A78BFA", fontSize: 12, fontWeight: 700 }}>{f.form_type || "Filing"}</span>
                                            <span style={{ color: C.textTertiary, fontSize: 12 }}>{f.filed_date || ""}</span>
                                        </div>
                                        {f.description && <span style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.4 }}>{f.description}</span>}
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <span style={muted}>SEC 공시 데이터 없음</span>
                        )}
                    </div>

                    {/* Insider Sentiment */}
                    <div style={card}>
                        <div style={cardHead}>
                            <span style={chip}>Insider</span>
                            <span style={cardTitle}>Insider Activity</span>
                        </div>
                        {insiderSent.mspr != null ? (
                            <div style={cardBody}>
                                <Row label="MSPR" value={typeof insiderSent.mspr === "number" && Number.isFinite(insiderSent.mspr) ? `${insiderSent.mspr > 0 ? "+" : ""}${insiderSent.mspr.toFixed(4)}` : "—"}
                                    color={insiderSent.mspr > 0 ? "#22C55E" : insiderSent.mspr < 0 ? "#EF4444" : "#888"} />
                                <Row label="Buy Count" value={String(insiderSent.positive_count || 0)} color="#22C55E" />
                                <Row label="Sell Count" value={String(insiderSent.negative_count || 0)} color="#EF4444" />
                                {insiderSent.net_shares != null && (
                                    <Row label="Net Shares" value={typeof insiderSent.net_shares === "number" ? insiderSent.net_shares.toLocaleString() : "—"}
                                        color={insiderSent.net_shares > 0 ? C.up : C.down} />
                                )}
                            </div>
                        ) : (
                            <span style={muted}>내부자 거래 데이터 없음</span>
                        )}
                    </div>

                    {/* Institutional + Financials */}
                    <div style={card}>
                        <div style={cardHead}>
                            <span style={chip}>Inst</span>
                            <span style={cardTitle}>Institutional & Financials</span>
                        </div>
                        <div style={cardBody}>
                            {instOwn.total_holders > 0 && (
                                <>
                                    <Row label="Inst. Holders" value={String(instOwn.total_holders)} />
                                    {instOwn.change_pct != null && (
                                        <Row label="Holdings Chg" value={`${instOwn.change_pct > 0 ? "+" : ""}${instOwn.change_pct}%`}
                                            color={instOwn.change_pct > 0 ? C.up : C.down} />
                                    )}
                                </>
                            )}
                            {finFacts.fcf != null && <Row label="FCF" value={`$${(finFacts.fcf / 1e9).toFixed(1)}B`} />}
                            {finFacts.revenue != null && <Row label="Revenue" value={`$${(finFacts.revenue / 1e9).toFixed(1)}B`} />}
                            {finFacts.net_income != null && <Row label="Net Income" value={`$${(finFacts.net_income / 1e9).toFixed(1)}B`}
                                color={finFacts.net_income >= 0 ? C.up : C.down} />}
                            {finFacts.operating_income != null && <Row label="Op. Income" value={`$${(finFacts.operating_income / 1e9).toFixed(1)}B`}
                                color={finFacts.operating_income >= 0 ? C.up : C.down} />}
                            {finFacts.debt_ratio != null && <Row label="Debt Ratio" value={`${finFacts.debt_ratio.toFixed(0)}%`}
                                color={finFacts.debt_ratio > 100 ? "#EF4444" : "#22C55E"} />}
                            {!instOwn.total_holders && finFacts.fcf == null && (
                                <span style={muted}>기관/재무 데이터 대기 중</span>
                            )}
                        </div>
                    </div>
                </>
            )}
        </div>
    )
}

function Row({ label, value, color = "#fff" }: { label: string; value: string; color?: string }) {
    return (
        <div style={rowStyle}>
            <span style={lbl}>{label}</span>
            <span style={{ ...val, color }}>{value}</span>
        </div>
    )
}

NicheIntelPanel.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    stockIndex: 0,
    market: "kr",
}

addPropertyControls(NicheIntelPanel, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
    stockIndex: {
        type: ControlType.Number,
        title: "종목 인덱스",
        defaultValue: 0,
        min: 0,
        max: 30,
        step: 1,
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})

const font = FONT

const panelWrap: CSSProperties = {
    width: "100%",
    background: C.bgElevated,
    border: `1px solid ${C.border}`,
    borderRadius: 16,
    padding: 16,
    fontFamily: font,
    display: "flex",
    flexDirection: "column",
    gap: 12,
    boxSizing: "border-box",
}
const headBlock: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    marginBottom: 4,
}
const headRow: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    gap: 8,
}
const switcherRow: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
}
const navBtn: CSSProperties = {
    width: 32,
    height: 32,
    padding: 0,
    borderRadius: 8,
    border: `1px solid ${C.border}`,
    background: C.bgPage,
    color: "#B5FF19",
    fontSize: 18,
    fontWeight: 700,
    lineHeight: 1,
    cursor: "pointer",
    fontFamily: font,
    flexShrink: 0,
}
const stockSelect: CSSProperties = {
    flex: 1,
    minWidth: 120,
    maxWidth: "100%",
    padding: "8px 10px",
    borderRadius: 8,
    border: `1px solid ${C.border}`,
    background: C.bgPage,
    color: C.textPrimary,
    fontSize: 12,
    fontWeight: 600,
    fontFamily: font,
    cursor: "pointer",
    outline: "none",
}
const indexHint: CSSProperties = {
    color: C.textTertiary,
    fontSize: 12,
    fontWeight: 600,
    whiteSpace: "nowrap",
    flexShrink: 0,
}
const title: CSSProperties = { color: C.textPrimary, fontSize: 15, fontWeight: 800 }
const sub: CSSProperties = { color: C.textTertiary, fontSize: 12 }
const emptyBox: CSSProperties = { background: C.bgPage, borderRadius: 10, padding: 12, border: "1px dashed #333" }
const card: CSSProperties = { background: C.bgPage, border: `1px solid ${C.border}`, borderRadius: 12, padding: 12 }
const cardHead: CSSProperties = { display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }
const chip: CSSProperties = { background: "#0D1A00", color: "#B5FF19", fontSize: 12, fontWeight: 800, padding: "2px 6px", borderRadius: 6, letterSpacing: 0.5 }
const cardTitle: CSSProperties = { color: C.textPrimary, fontSize: 12, fontWeight: 700 }
const cardBody: CSSProperties = { display: "flex", flexDirection: "column", gap: 8 }
const rowStyle: CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }
const lbl: CSSProperties = { color: C.textTertiary, fontSize: 12 }
const val: CSSProperties = { color: C.textPrimary, fontSize: 12, fontWeight: 700 }
const note: CSSProperties = { color: "#777", fontSize: 12, lineHeight: 1.45, margin: "6px 0 0" }
const muted: CSSProperties = { color: C.textTertiary, fontSize: 12, lineHeight: 1.5 }
const bidRow: CSSProperties = { background: C.bgElevated, borderRadius: 8, padding: "8px 10px", border: `1px solid ${C.border}` }
const newsRow: CSSProperties = { background: C.bgElevated, borderRadius: 8, padding: "8px 10px" }

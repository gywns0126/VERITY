import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"
import type { CSSProperties } from "react"

/** Framer에 이 파일만 넣을 때를 위해 fetch 인라인 (fetchPortfolioJson.ts와 동일) */
function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchPortfolioJson(url: string): Promise<any> {
    return fetch(bustPortfolioUrl(url), {
        cache: "no-store",
        mode: "cors",
        credentials: "omit",
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
        )
}

function normalizeStockIndex(v: unknown): number {
    const n = typeof v === "number" ? v : Number(v)
    if (!Number.isFinite(n) || n < 0) return 0
    return Math.floor(n)
}

interface Props {
    dataUrl: string
    stockIndex: number
}

export default function NicheIntelPanel(props: Props) {
    const { dataUrl, stockIndex } = props
    const [data, setData] = useState<any>(null)
    const [activeIndex, setActiveIndex] = useState(() =>
        normalizeStockIndex(stockIndex),
    )

    useEffect(() => {
        if (!dataUrl) return
        fetchPortfolioJson(dataUrl).then(setData).catch(console.error)
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
                <span style={{ color: "#555", fontSize: 13 }}>데이터 로딩 중...</span>
            </div>
        )
    }

    const recs: any[] = data?.recommendations || []
    const maxIdx = Math.max(0, recs.length - 1)
    const idx = Math.min(Math.max(0, activeIndex), maxIdx)
    const stock = recs[idx]

    const macro = data?.macro || {}
    if (!stock) {
        return (
            <div style={{ ...panelWrap, minHeight: 120, justifyContent: "center", alignItems: "center" }}>
                <span style={{ color: "#555", fontSize: 13 }}>종목을 선택하세요</span>
            </div>
        )
    }

    const n = stock?.niche_data || {}
    const mc = macro?.niche_credit || {}
    const hasAny =
        (n.trends && Object.keys(n.trends).length > 0) ||
        (n.g2b && (n.g2b.items?.length > 0 || n.g2b.summary)) ||
        (n.legal && (n.legal.hits?.length > 0 || n.legal.risk_flag)) ||
        (n.credit && (n.credit.ig_spread_pp != null || n.credit.note)) ||
        (mc.corporate_spread_vs_gov_pp != null || mc.alert)

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
                        — 틈새 정보
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
                    <span style={{ color: "#888", fontSize: 12, lineHeight: 1.5 }}>
                        이 종목에 대한 틈새 데이터(트렌드·G2B·법 리스크·신용)는 백엔드 수집기 연동 후 표시됩니다.
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
                                color={n.trends.week_change_pct >= 0 ? "#22C55E" : "#EF4444"}
                            />
                        )}
                        {n.trends.note && <p style={note}>{n.trends.note}</p>}
                    </div>
                ) : (
                    <span style={muted}>주 1회 수집 예정 (소비·게임·뷰티 등)</span>
                )}
            </div>

            {/* G2B */}
            <div style={card}>
                <div style={cardHead}>
                    <span style={chip}>G2B</span>
                    <span style={cardTitle}>공공 수주</span>
                </div>
                {n.g2b?.items?.length > 0 ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {n.g2b.items.slice(0, 5).map((it: any, i: number) => (
                            <div key={i} style={bidRow}>
                                <span style={{ color: "#ccc", fontSize: 11, lineHeight: 1.4 }}>{it.title || "—"}</span>
                                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                                    <span style={{ color: "#555", fontSize: 10 }}>{it.bid_date || ""}</span>
                                    <span style={{ color: "#B5FF19", fontSize: 11, fontWeight: 700 }}>
                                        {it.amount_won != null ? `${(it.amount_won / 1e8).toFixed(1)}억` : ""}
                                        {it.winner ? " · 낙찰" : ""}
                                    </span>
                                </div>
                            </div>
                        ))}
                        {n.g2b.summary && <p style={note}>{n.g2b.summary}</p>}
                    </div>
                ) : n.g2b?.summary ? (
                    <p style={note}>{n.g2b.summary}</p>
                ) : (
                    <span style={muted}>장 마감 후·B2G 섹터 위주 수집</span>
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
                                        color: "#aaa",
                                        fontSize: 11,
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
                    {n.credit?.alert && (
                        <div style={{ color: "#FF9F40", fontSize: 11, marginTop: 6 }}>종목 단위 신용 알림</div>
                    )}
                    {n.credit?.note && <p style={note}>{n.credit.note}</p>}
                    {(mc.corporate_spread_vs_gov_pp != null || mc.alert) && (
                        <div style={{ borderTop: "1px solid #222", marginTop: 10, paddingTop: 10 }}>
                            <span style={{ color: "#666", fontSize: 10, display: "block", marginBottom: 6 }}>시장 (macro.niche_credit)</span>
                            {mc.corporate_spread_vs_gov_pp != null && (
                                <Row
                                    label="회사채-국고 스프레드"
                                    value={`${mc.corporate_spread_vs_gov_pp}%p${mc.alert ? " · 경고" : ""}`}
                                    color={mc.alert || mc.corporate_spread_vs_gov_pp >= 2 ? "#FF4D4D" : "#22C55E"}
                                />
                            )}
                            {mc.updated_at && <span style={{ color: "#444", fontSize: 10 }}>{mc.updated_at}</span>}
                        </div>
                    )}
                    {!n.credit?.ig_spread_pp && mc.corporate_spread_vs_gov_pp == null && !mc.alert && (
                        <span style={muted}>중소형주는 개별 데이터가 없을 수 있음. 시장 전체 지표 위주.</span>
                    )}
                </div>
            </div>
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
})

const font = "'Pretendard', -apple-system, sans-serif"

const panelWrap: CSSProperties = {
    width: "100%",
    background: "#111",
    border: "1px solid #222",
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
    border: "1px solid #333",
    background: "#0A0A0A",
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
    border: "1px solid #333",
    background: "#0A0A0A",
    color: "#fff",
    fontSize: 12,
    fontWeight: 600,
    fontFamily: font,
    cursor: "pointer",
    outline: "none",
}
const indexHint: CSSProperties = {
    color: "#555",
    fontSize: 11,
    fontWeight: 600,
    whiteSpace: "nowrap",
    flexShrink: 0,
}
const title: CSSProperties = { color: "#fff", fontSize: 15, fontWeight: 800 }
const sub: CSSProperties = { color: "#555", fontSize: 10 }
const emptyBox: CSSProperties = { background: "#0A0A0A", borderRadius: 10, padding: 12, border: "1px dashed #333" }
const card: CSSProperties = { background: "#0A0A0A", border: "1px solid #222", borderRadius: 12, padding: 12 }
const cardHead: CSSProperties = { display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }
const chip: CSSProperties = { background: "#0D1A00", color: "#B5FF19", fontSize: 9, fontWeight: 800, padding: "2px 6px", borderRadius: 4, letterSpacing: 0.5 }
const cardTitle: CSSProperties = { color: "#ccc", fontSize: 12, fontWeight: 700 }
const cardBody: CSSProperties = { display: "flex", flexDirection: "column", gap: 8 }
const rowStyle: CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }
const lbl: CSSProperties = { color: "#666", fontSize: 11 }
const val: CSSProperties = { color: "#fff", fontSize: 12, fontWeight: 700 }
const note: CSSProperties = { color: "#777", fontSize: 11, lineHeight: 1.45, margin: "6px 0 0" }
const muted: CSSProperties = { color: "#555", fontSize: 11, lineHeight: 1.5 }
const bidRow: CSSProperties = { background: "#111", borderRadius: 8, padding: "8px 10px", border: "1px solid #1A1A1A" }
const newsRow: CSSProperties = { background: "#111", borderRadius: 8, padding: "8px 10px" }

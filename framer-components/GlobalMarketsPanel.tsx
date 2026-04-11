import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"
import type { CSSProperties } from "react"

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchPortfolioJson(url: string): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit" })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"
const UP = "#22C55E"
const DOWN = "#EF4444"
const BG = "#000"
const CARD = "#111"
const BORDER = "#222"
const MUTED = "#8B95A1"
const ACCENT = "#B5FF19"

type MarketId = "NAS" | "NYS" | "HKS" | "TSE" | "SHS" | "SZS"

const MARKET_META: Record<MarketId, { name: string; flag: string; impact: string }> = {
    NAS: { name: "나스닥", flag: "🇺🇸", impact: "글로벌 기술주 선행" },
    NYS: { name: "뉴욕", flag: "🇺🇸", impact: "대형주·산업재 벤치마크" },
    HKS: { name: "홍콩", flag: "🇭🇰", impact: "중국 대리 지표" },
    TSE: { name: "도쿄", flag: "🇯🇵", impact: "아시아 선행·환율 연동" },
    SHS: { name: "상해", flag: "🇨🇳", impact: "중국 A주·원자재" },
    SZS: { name: "심천", flag: "🇨🇳", impact: "중국 기술·성장주" },
}

type SubTab = "volume" | "updown" | "surge" | "cap"

const SUB_TABS: { id: SubTab; label: string }[] = [
    { id: "updown", label: "등락률" },
    { id: "volume", label: "거래량" },
    { id: "surge", label: "급증" },
    { id: "cap", label: "시총" },
]

function fmtPct(v: any): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return "—"
    return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`
}

function fmtVol(v: any): string {
    const n = Number(v)
    if (!Number.isFinite(n) || n === 0) return "—"
    if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`
    return n.toLocaleString()
}

function fmtPrice(v: any): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return "—"
    return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export default function GlobalMarketsPanel({
    portfolioUrl = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    defaultMarkets = "NAS,NYS,HKS,TSE",
    refreshInterval = 300000,
}: {
    portfolioUrl?: string
    defaultMarkets?: string
    refreshInterval?: number
}) {
    const [portfolio, setPortfolio] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [fetchError, setFetchError] = useState(false)
    const [retryKey, setRetryKey] = useState(0)
    const [activeMarket, setActiveMarket] = useState<MarketId>("NAS")
    const [subTab, setSubTab] = useState<SubTab>("updown")

    const markets = useMemo<MarketId[]>(() => {
        return (defaultMarkets || "NAS,NYS,HKS,TSE").split(",").map(s => s.trim()) as MarketId[]
    }, [defaultMarkets])

    useEffect(() => {
        if (!portfolioUrl) return
        let cancelled = false
        setLoading(true)
        setFetchError(false)
        const load = () => {
            fetchPortfolioJson(portfolioUrl)
                .then((d) => { if (!cancelled) { setPortfolio(d); setLoading(false); setFetchError(false) } })
                .catch(() => { if (!cancelled) { setLoading(false); setFetchError(true) } })
        }
        load()
        const iv = refreshInterval > 0 ? setInterval(load, refreshInterval) : undefined
        return () => { cancelled = true; if (iv) clearInterval(iv) }
    }, [portfolioUrl, refreshInterval, retryKey])

    const kisOverseas = portfolio?.kis_overseas_market || {}
    const kisDomestic = portfolio?.kis_market || {}
    const newsItems = kisOverseas.news || []
    const breakingItems = kisOverseas.breaking || []

    const mktData = kisOverseas[activeMarket] || {}

    const listForTab = useMemo(() => {
        switch (subTab) {
            case "updown": return mktData.updown_rank || []
            case "volume": return mktData.volume_rank || []
            case "surge": return mktData.volume_surge || []
            case "cap": return mktData.market_cap || []
            default: return []
        }
    }, [subTab, mktData])

    const getField = (item: any, tab: SubTab): { name: string; ticker: string; price: string; pct: string; vol: string } => {
        const name = item.hts_kor_isnm || item.name || item.symb || "—"
        const ticker = item.symb || item.mksc_shrn_iscd || ""
        const price = fmtPrice(item.last || item.stck_prpr || item.ovrs_nmix_prpr || 0)
        const pct = fmtPct(item.rate || item.prdy_ctrt || item.fluc_rt || 0)
        const vol = fmtVol(item.tvol || item.acml_vol || item.tamt || 0)
        return { name, ticker, price, pct, vol }
    }

    const usFallback = useMemo(() => {
        const recs: any[] = (portfolio?.recommendations || []).filter((r: any) =>
            r?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r?.market || "")
        )
        return [...recs]
            .sort((a, b) => (b?.technical?.price_change_pct || b?.change_pct || 0) - (a?.technical?.price_change_pct || a?.change_pct || 0))
            .slice(0, 15)
    }, [portfolio])

    const hasKisData = Object.keys(kisOverseas).length > 0

    if (loading) {
        return (
            <div style={wrapStyle}>
                <div style={{ ...flexCenter, padding: 30 }}>
                    <span style={{ color: ACCENT, fontSize: 13, fontWeight: 600, fontFamily: font }}>글로벌 마켓 데이터 로딩 중…</span>
                </div>
            </div>
        )
    }

    if (fetchError && !portfolio) {
        return (
            <div style={wrapStyle}>
                <div style={{ ...flexCenter, padding: 30 }}>
                    <span style={{ color: MUTED, fontSize: 13, fontFamily: font }}>데이터를 불러올 수 없습니다</span>
                    <span style={{ color: "#555", fontSize: 10, fontFamily: font, marginTop: 4 }}>네트워크 또는 CORS 설정을 확인하세요</span>
                    <button
                        type="button"
                        onClick={() => setRetryKey(k => k + 1)}
                        style={{
                            marginTop: 12, padding: "8px 18px", borderRadius: 8,
                            background: ACCENT, color: "#000", border: "none",
                            fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: font,
                        }}
                    >
                        다시 시도
                    </button>
                </div>
            </div>
        )
    }

    if (!hasKisData) {
        return (
            <div style={wrapStyle}>
                {usFallback.length === 0 ? (
                    <div style={{ ...flexCenter, padding: 30 }}>
                        <span style={{ color: MUTED, fontSize: 13, fontFamily: font }}>글로벌 마켓 데이터 준비 중</span>
                        <span style={{ color: "#555", fontSize: 10, fontFamily: font, marginTop: 4 }}>
                            KIS 파이프라인 실행 후 데이터가 표시됩니다
                        </span>
                        <button
                            type="button"
                            onClick={() => setRetryKey(k => k + 1)}
                            style={{
                                marginTop: 12, padding: "6px 14px", borderRadius: 8,
                                background: "transparent", color: ACCENT, border: `1px solid ${ACCENT}`,
                                fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: font,
                            }}
                        >
                            새로고침
                        </button>
                    </div>
                ) : (
                    <>
                        <div style={{ padding: "14px 16px", borderBottom: `1px solid ${BORDER}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <div>
                                <div style={{ color: "#fff", fontSize: 14, fontWeight: 800, fontFamily: font }}>US 마켓</div>
                                <div style={{ color: MUTED, fontSize: 10, marginTop: 2, fontFamily: font }}>추천 종목 기반 · {usFallback.length}종목</div>
                            </div>
                            <button
                                type="button"
                                onClick={() => setRetryKey(k => k + 1)}
                                style={{
                                    padding: "4px 10px", borderRadius: 6,
                                    background: "transparent", color: MUTED, border: `1px solid ${BORDER}`,
                                    fontSize: 10, cursor: "pointer", fontFamily: font,
                                }}
                            >
                                ↻
                            </button>
                        </div>
                        <div style={{ flex: 1, overflowY: "auto", padding: "8px 16px" }}>
                            {usFallback.map((r: any, i: number) => {
                                const pctVal = Number(r?.technical?.price_change_pct || r?.change_pct || 0)
                                return (
                                    <div key={`${r.ticker}-${i}`} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 0", borderBottom: i < usFallback.length - 1 ? `1px solid ${BORDER}` : "none" }}>
                                        <div style={{ width: 24, color: MUTED, fontSize: 11, fontWeight: 700, textAlign: "right", flexShrink: 0 }}>{i + 1}</div>
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ color: "#fff", fontSize: 12, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: font }}>{r.name || r.ticker}</div>
                                            <div style={{ color: MUTED, fontSize: 10, marginTop: 2, fontFamily: font }}>{r.ticker} · {r.market || "US"}</div>
                                        </div>
                                        <div style={{ textAlign: "right" }}>
                                            <div style={{ color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: font }}>{fmtPrice(r.price || r.current_price || 0)}</div>
                                            <div style={{ color: pctVal >= 0 ? UP : DOWN, fontSize: 11, fontWeight: 700, fontFamily: font }}>{fmtPct(pctVal)}</div>
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    </>
                )}
            </div>
        )
    }

    return (
        <div style={wrapStyle}>
            {/* 헤더 */}
            <div style={{ padding: "14px 16px", borderBottom: `1px solid ${BORDER}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                    <div style={{ color: "#fff", fontSize: 16, fontWeight: 800 }}>글로벌 마켓</div>
                    <div style={{ color: MUTED, fontSize: 10, marginTop: 2 }}>
                        KIS Open API · {kisOverseas.timestamp ? new Date(kisOverseas.timestamp).toLocaleTimeString("ko-KR") : "—"}
                    </div>
                </div>
                <div style={{ color: ACCENT, fontSize: 11, fontWeight: 700 }}>
                    {markets.length}개 시장
                </div>
            </div>

            {/* 국내 시장 요약 */}
            {(kisDomestic.kospi || kisDomestic.kosdaq) && (
                <div style={{ padding: "10px 16px", borderBottom: `1px solid ${BORDER}`, display: "flex", gap: 12 }}>
                    {kisDomestic.kospi && (() => {
                        const k = kisDomestic.kospi
                        const pct = Number(k.bstp_nmix_prdy_ctrt || 0)
                        return (
                            <div style={{ flex: 1, background: CARD, borderRadius: 10, padding: "10px 12px", border: `1px solid ${BORDER}` }}>
                                <div style={{ color: MUTED, fontSize: 10, marginBottom: 4 }}>코스피</div>
                                <div style={{ color: "#fff", fontSize: 15, fontWeight: 800 }}>{Number(k.bstp_nmix_prpr || 0).toLocaleString()}</div>
                                <div style={{ color: pct >= 0 ? UP : DOWN, fontSize: 11, fontWeight: 700 }}>{fmtPct(pct)}</div>
                            </div>
                        )
                    })()}
                    {kisDomestic.kosdaq && (() => {
                        const k = kisDomestic.kosdaq
                        const pct = Number(k.bstp_nmix_prdy_ctrt || 0)
                        return (
                            <div style={{ flex: 1, background: CARD, borderRadius: 10, padding: "10px 12px", border: `1px solid ${BORDER}` }}>
                                <div style={{ color: MUTED, fontSize: 10, marginBottom: 4 }}>코스닥</div>
                                <div style={{ color: "#fff", fontSize: 15, fontWeight: 800 }}>{Number(k.bstp_nmix_prpr || 0).toLocaleString()}</div>
                                <div style={{ color: pct >= 0 ? UP : DOWN, fontSize: 11, fontWeight: 700 }}>{fmtPct(pct)}</div>
                            </div>
                        )
                    })()}
                </div>
            )}

            {/* 시장 탭 */}
            <div style={{ display: "flex", overflowX: "auto", borderBottom: `1px solid ${BORDER}`, padding: "0 12px" }}>
                {markets.map((mId) => {
                    const meta = MARKET_META[mId]
                    if (!meta) return null
                    const active = mId === activeMarket
                    return (
                        <button
                            key={mId}
                            type="button"
                            onClick={() => setActiveMarket(mId)}
                            style={{
                                padding: "10px 14px",
                                background: "none",
                                border: "none",
                                borderBottom: active ? `2px solid ${ACCENT}` : "2px solid transparent",
                                cursor: "pointer",
                                fontFamily: font,
                                whiteSpace: "nowrap",
                            }}
                        >
                            <div style={{ fontSize: 12, fontWeight: active ? 800 : 600, color: active ? "#fff" : MUTED }}>
                                {meta.flag} {meta.name}
                            </div>
                        </button>
                    )
                })}
            </div>

            {/* 시장 설명 */}
            <div style={{ padding: "8px 16px", borderBottom: `1px solid ${BORDER}` }}>
                <div style={{ color: MUTED, fontSize: 10, lineHeight: 1.4 }}>
                    {MARKET_META[activeMarket]?.impact || ""}
                </div>
            </div>

            {/* 서브 탭 */}
            <div style={{ display: "flex", gap: 6, padding: "8px 16px", borderBottom: `1px solid ${BORDER}` }}>
                {SUB_TABS.map((st) => (
                    <button
                        key={st.id}
                        type="button"
                        onClick={() => setSubTab(st.id)}
                        style={{
                            padding: "6px 12px",
                            borderRadius: 8,
                            border: `1px solid ${st.id === subTab ? ACCENT : BORDER}`,
                            background: st.id === subTab ? "rgba(181,255,25,0.1)" : "transparent",
                            color: st.id === subTab ? ACCENT : MUTED,
                            fontSize: 11,
                            fontWeight: 700,
                            cursor: "pointer",
                            fontFamily: font,
                        }}
                    >
                        {st.label}
                    </button>
                ))}
            </div>

            {/* 리스트 */}
            <div style={{ flex: 1, overflowY: "auto", padding: "8px 16px" }}>
                {listForTab.length === 0 ? (
                    <div style={{ color: MUTED, fontSize: 12, textAlign: "center", padding: 20 }}>
                        데이터 없음
                    </div>
                ) : (
                    listForTab.slice(0, 20).map((item: any, i: number) => {
                        const { name, ticker, price, pct, vol } = getField(item, subTab)
                        const pctVal = Number(item.rate || item.prdy_ctrt || item.fluc_rt || 0)
                        return (
                            <div
                                key={`${ticker}-${i}`}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 10,
                                    padding: "10px 0",
                                    borderBottom: i < listForTab.length - 1 ? `1px solid ${BORDER}` : "none",
                                }}
                            >
                                <div style={{ width: 24, color: MUTED, fontSize: 11, fontWeight: 700, textAlign: "right", flexShrink: 0 }}>
                                    {i + 1}
                                </div>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ color: "#fff", fontSize: 12, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                        {name}
                                    </div>
                                    <div style={{ color: MUTED, fontSize: 10, marginTop: 2 }}>
                                        {ticker} · Vol {vol}
                                    </div>
                                </div>
                                <div style={{ textAlign: "right", flexShrink: 0 }}>
                                    <div style={{ color: "#fff", fontSize: 12, fontWeight: 700 }}>{price}</div>
                                    <div style={{ color: pctVal >= 0 ? UP : DOWN, fontSize: 11, fontWeight: 700 }}>{pct}</div>
                                </div>
                            </div>
                        )
                    })
                )}
            </div>

            {/* 뉴스 */}
            {(newsItems.length > 0 || breakingItems.length > 0) && (
                <div style={{ borderTop: `1px solid ${BORDER}`, padding: "12px 16px", maxHeight: 200, overflowY: "auto" }}>
                    <div style={{ color: ACCENT, fontSize: 10, fontWeight: 800, marginBottom: 8 }}>해외 뉴스</div>
                    {breakingItems.slice(0, 3).map((n: any, i: number) => (
                        <div key={`brk-${i}`} style={{ marginBottom: 6, fontSize: 11, lineHeight: 1.4 }}>
                            <span style={{ color: "#EF4444", fontWeight: 700, marginRight: 4 }}>속보</span>
                            <span style={{ color: "#fff" }}>{n.hts_pbnt_titl_cntt || n.title || "—"}</span>
                            <span style={{ color: MUTED, marginLeft: 4 }}>{n.data_dt || ""}</span>
                        </div>
                    ))}
                    {newsItems.slice(0, 5).map((n: any, i: number) => (
                        <div key={`nws-${i}`} style={{ marginBottom: 6, fontSize: 11, lineHeight: 1.4 }}>
                            <span style={{ color: "#fff" }}>{n.hts_pbnt_titl_cntt || n.title || "—"}</span>
                            <span style={{ color: MUTED, marginLeft: 4 }}>{n.data_dt || ""}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

GlobalMarketsPanel.defaultProps = {
    portfolioUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    defaultMarkets: "NAS,NYS,HKS,TSE",
    refreshInterval: 300000,
}

addPropertyControls(GlobalMarketsPanel, {
    portfolioUrl: { type: ControlType.String, title: "portfolio.json URL", defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json" },
    defaultMarkets: { type: ControlType.String, title: "시장 목록 (콤마 구분)", defaultValue: "NAS,NYS,HKS,TSE" },
    refreshInterval: { type: ControlType.Number, title: "갱신 주기(ms)", defaultValue: 300000, min: 0, step: 10000 },
})

const wrapStyle: CSSProperties = {
    width: "100%",
    height: "100%",
    minHeight: 400,
    background: BG,
    borderRadius: 20,
    border: `1px solid ${BORDER}`,
    overflow: "hidden",
    fontFamily: font,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
}

const flexCenter: CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
}

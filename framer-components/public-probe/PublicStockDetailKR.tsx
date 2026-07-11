import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * AlphaNest 공개 — KR 종목 심화 (기관·국민연금 대량보유 + 사업장 + 공시 forensics). DART 사실만.
 * PublicForensics + PublicHoldingsDetail 통합(2026-07-01) — 배치 1번. 둘은 폐기.
 * 🚨 RULE 7 — 위험점수·심각도·해석 0. 사실만. 데이터 = stock_report_public.json(지분·사업장) + kr_forensics_public.json(forensics).
 * 다크모드 = body[data-framer-theme] 자가감지. 외곽선 없음(소프트 카드).
 * Framer codeFileId = WNrsqjb (insertUrl framer.com/m/PublicStockDetailKR-RbhPiw.js).
 */

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#f0f1f3", vt: "#6c5ce7", vtS: "#f0edff" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#222730", vt: "#a99bff", vtS: "#241f3a" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const REPORT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
const FORENSICS_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/kr_forensics_public.json"

const FSECTIONS: { key: string; label: string }[] = [
    { key: "related_party_transactions", label: "특수관계자 거래" },
    { key: "contingent_liabilities", label: "우발부채·보증" },
    { key: "pending_litigation", label: "진행 중 소송" },
    { key: "material_sanctions", label: "제재" },
]

const SAMPLE_REC: any = {
    institutional: { total_pct: 5.18, n: 1, holders: [{ reporter: "국민연금공단", pct: 5.18, qty_change: 108230, date: "2026-04-01" }], note: "DART 5%+ 대량보유 보고(기관·국민연금) — 사실, 신호 아님" },
    facilities: { headquarters: { location: "경상남도 창원시 성산구", ownership: "소유" }, facilities: [{ name: "창원공장", location: "경상남도 창원시", use: "공장", segment: "디펜스솔루션" }], note: "DART 사업보고서 시설 현황 — 사실" },
}
const SAMPLE_FOR: any = { related_party_transactions: ["상대방: 계열사 등 / 유형: 제품매출 / 규모: 1,505억원 (영업수익의 약 75%)"], contingent_liabilities: ["금융기관 지급보증 USD 137백만 등"], cb_bw: { n_instruments: 2, dilution_pct: 12.5, instruments: [{ type: "CB", issue_amount: 50000000000, strike: 50000, resolved_date: "20250601" }, { type: "BW", issue_amount: 10000000000, strike: 40000, resolved_date: "20240301" }], note: "DART 주요사항보고 발행 기준(전환·상환 미반영) · 희석률=발행가능÷발행주식" }, year: "2025", source_note: "DART 사업보고서 원문 사실 · 자체 위험판단 아님" }

function readDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

function readBodyDark(): boolean {
    // 첫 페인트 flash 방지 — body 속성 미설정(마운트 직후) 시 토글 저장 선호(localStorage) → OS 순 폴백.
    // PublicThemeToggle 이 verity_theme 로 저장 + body[data-framer-theme] 설정 = 동일 소스라 첫 페인트부터 정합.
    try {
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

export default function PublicStockDetailKR(props: { ticker?: string; reportUrl?: string; forensicsUrl?: string; dark?: boolean }) {
    // ETF/ETN 선택 시 자기 숨김 — StockReport 가 body[data-verity-asset-kind] 신호 발행 (2026-07-10)
    const [assetKind, setAssetKind] = useState<string>("stock")
    useEffect(() => {
        if (typeof document === "undefined" || !document.body) return
        const read = () => setAssetKind(document.body.dataset.verityAssetKind || "stock")
        read()
        if (typeof MutationObserver === "undefined") return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-verity-asset-kind"] })
        return () => obs.disconnect()
    }, [])
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const [rec, setRec] = useState<any>(onCanvas ? SAMPLE_REC : null)
    const [forensics, setForensics] = useState<any>(onCanvas ? SAMPLE_FOR : null)
    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas || !props.ticker) return
        let alive = true
        const tk = String(props.ticker)
        fetch(props.reportUrl || REPORT_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive) setRec(d && d.stocks ? d.stocks[tk] || null : null) })
            .catch(() => { if (alive) setRec(null) })
        fetch(props.forensicsUrl || FORENSICS_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive) setForensics(d && d.stocks ? d.stocks[tk] || null : null) })
            .catch(() => { if (alive) setForensics(null) })
        return () => { alive = false }
    }, [props.ticker, props.reportUrl, props.forensicsUrl, onCanvas])

    const inst = rec && rec.institutional
    const fac = rec && rec.facilities
    const hasInst = inst && Array.isArray(inst.holders) && inst.holders.length > 0
    const hasFac = fac && (Array.isArray(fac.facilities) || fac.headquarters)
    const hasFor = forensics && (FSECTIONS.some((s) => Array.isArray(forensics[s.key]) && forensics[s.key].length) || (forensics.cb_bw && forensics.cb_bw.n_instruments > 0))
    const narrow = w > 0 && w < 420
    if (!hasInst && !hasFac && !hasFor) return <div ref={rootRef} style={{ width: "100%", height: 0, overflow: "hidden" }} />

    const HEAD = "Pretendard, -apple-system, sans-serif"
    const wrap: CSSProperties = { width: "100%", minHeight: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: narrow ? 14 : 18, display: "flex", flexDirection: "column", gap: 14 }
    const title = (t: string, sub: string) => (
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 2 }}>
            <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.3px" }}>{t}</span>
            <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{sub}</span>
        </div>
    )
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }

    if (assetKind === "etf") return null  // ETF/ETN = 기업 전용 섹션 숨김

    return (
        <div ref={rootRef} style={wrap}>
            {hasInst && (
                <div>
                    {title("기관·국민연금 대량보유", "DART 5%+ 보고 · 사실")}
                    <div style={card}>
                        {inst.total_pct != null && (
                            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
                                <span style={{ fontFamily: HEAD, fontSize: 22, fontWeight: 800, color: C.vt, letterSpacing: "-0.6px" }}>{inst.total_pct}%</span>
                                <span style={{ fontSize: 12.5, fontWeight: 700 }}>기관 합산 보유</span>
                                {inst.n != null && <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{inst.n}곳</span>}
                            </div>
                        )}
                        {inst.holders.map((h: any, i: number) => (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{h.reporter}</span>
                                {h.qty_change != null && <span style={{ flexShrink: 0, fontSize: 11, fontWeight: 600, color: C.faint }}>변동 {Number(h.qty_change) >= 0 ? "+" : ""}{Number(h.qty_change).toLocaleString("ko-KR")}</span>}
                                <span style={{ flexShrink: 0, fontSize: 12.5, fontWeight: 800, color: C.vt, minWidth: 46, textAlign: "right" }}>{h.pct}%</span>
                            </div>
                        ))}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginTop: 9 }}>{inst.note}</div>
                    </div>
                </div>
            )}
            {hasFac && (
                <div>
                    {title("사업장·설비", "DART 사업보고서 · 사실")}
                    <div style={card}>
                        {fac.headquarters && fac.headquarters.location && (
                            <div style={{ fontSize: 12.5, fontWeight: 600, color: C.sub, marginBottom: 8 }}>본사 · {fac.headquarters.location}{fac.headquarters.ownership ? ` (${fac.headquarters.ownership})` : ""}</div>
                        )}
                        {Array.isArray(fac.facilities) && fac.facilities.map((f: any, i: number) => (
                            <div key={i} style={{ padding: "8px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                                    <span style={{ fontSize: 13, fontWeight: 700, color: C.ink }}>{f.name}</span>
                                    {f.use && <span style={{ fontSize: 11, fontWeight: 700, color: C.vt, background: C.vtS, borderRadius: 6, padding: "2px 7px" }}>{f.use}</span>}
                                </div>
                                {(f.location || f.segment) && <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>{[f.location, f.segment].filter(Boolean).join(" · ")}</div>}
                            </div>
                        ))}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginTop: 9 }}>{fac.note}</div>
                    </div>
                </div>
            )}
            {hasFor && (
                <div>
                    {title("공시 forensics", "DART 사업보고서 · 사실" + (forensics.year ? " · " + forensics.year : ""))}
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                        {FSECTIONS.map((s) => {
                            const items = Array.isArray(forensics[s.key]) ? forensics[s.key] : []
                            if (!items.length) return null
                            return (
                                <div key={s.key} style={card}>
                                    <div style={{ fontSize: 12.5, fontWeight: 800, color: C.vt, marginBottom: 8 }}>{s.label}<span style={{ color: C.faint, marginLeft: 6, fontWeight: 600 }}>{items.length}</span></div>
                                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                        {items.map((it: string, i: number) => (
                                            <div key={i} style={{ fontSize: 12, color: C.sub, fontWeight: 500, lineHeight: 1.55, paddingLeft: 11, position: "relative" }}>
                                                <span style={{ position: "absolute", left: 0, color: C.vt }}>·</span>{String(it)}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )
                        })}
                        {forensics.cb_bw && forensics.cb_bw.n_instruments > 0 && (() => {
                            const cb = forensics.cb_bw
                            const eok = (v: any) => {
                                const n = Number(v)
                                if (!isFinite(n) || n <= 0) return "—"
                                return n >= 1e12 ? (n / 1e12).toFixed(1) + "조" : n >= 1e8 ? Math.round(n / 1e8).toLocaleString() + "억" : Math.round(n).toLocaleString() + "원"
                            }
                            const won = (v: any) => { const n = Number(v); return isFinite(n) && n > 0 ? Math.round(n).toLocaleString() + "원" : "—" }
                            return (
                                <div style={card}>
                                    <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
                                        <span style={{ fontSize: 12.5, fontWeight: 800, color: C.vt }}>CB·BW 희석 오버행</span>
                                        {cb.dilution_pct != null ? <span style={{ fontSize: 13, fontWeight: 800, color: C.vt }}>전환·행사 시 +{cb.dilution_pct}%</span> : null}
                                        <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{cb.n_instruments}건</span>
                                    </div>
                                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                        {(cb.instruments || []).map((ins: any, i: number) => (
                                            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11.5 }}>
                                                <span style={{ flexShrink: 0, fontSize: 10, fontWeight: 800, color: C.vt, background: C.vtS, borderRadius: 5, padding: "2px 6px" }}>{ins.type}</span>
                                                <span style={{ flex: 1, minWidth: 0, color: C.sub, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{eok(ins.issue_amount)} · 전환가 {won(ins.strike)}</span>
                                                <span style={{ flexShrink: 0, color: C.faint, fontWeight: 600 }}>{ins.resolved_date && String(ins.resolved_date).length >= 6 ? String(ins.resolved_date).slice(2, 4) + "." + String(ins.resolved_date).slice(4, 6) : ""}</span>
                                            </div>
                                        ))}
                                    </div>
                                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginTop: 7 }}>{cb.note}</div>
                                </div>
                            )
                        })()}
                    </div>
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginTop: 8 }}>{forensics.source_note || "DART 사업보고서 원문 사실 · 자체 위험판단 아님"}</div>
                </div>
            )}
        </div>
    )
}

addPropertyControls(PublicStockDetailKR, {
    ticker: { type: ControlType.String, title: "종목코드", defaultValue: "" },
    reportUrl: { type: ControlType.String, title: "Report URL", defaultValue: REPORT_URL },
    forensicsUrl: { type: ControlType.String, title: "Forensics URL", defaultValue: FORENSICS_URL },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})

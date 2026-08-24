import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState } from "react"

/**
 * PublicSmartMoneySearch — 거장 보유 역조회 검색 (2026-08-24).
 *
 * 거장 페이지 보조 축: 종목을 검색하면 "누가 · 얼마나 · 언제부터" 보유 중인지 보여준다.
 * 데이터 = us_smart_money_13f.json (종목 축, SEC 13F-HR · 집중형 16개 운용사 · S&P1500).
 * 인물 축(PublicInvestorPortfolios)과 같은 원천의 반대 방향 조회다.
 *
 * 🚨 팔레트 = AlphaNest 공통 토큰만 (PublicInvestorPortfolios 와 동일 값 — 자체 팔레트 금지,
 *   2026-07-30 PM 지적). 상승/증액=빨강 · 감액=파랑 (한국 관례).
 * 🚨 입력창 = 보더/아웃라인 금지 ([[feedback_no_border_outline_public_inputs]]) — 배경 채움만.
 * 🚨 '수익률' 라벨 금지 — 13F 는 분기말 보유를 최대 45일 뒤 제출 + 롱 미국주식만.
 *   신선도(보유 기준일·제출일)는 각주가 아니라 1급 정보로 노출한다.
 * 🚨 로고 = 토스 CDN 레인 유지 ([[project_logo_toss_lane_2026_07_12]] — 갈아타기 금지).
 * 🚨 모바일 = CSS 미디어쿼리로만 판정 (Framer 프레임 폭 ≠ 뷰포트 — JS 측정 금지).
 */

const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const FX_FALLBACK = 1450

// AlphaNest 공통 토큰 (PublicInvestorPortfolios/PublicCalendar/NPSHoldings 동일 값)
const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", track: "#eef0f3", hi: "#f6f7f9",
    vt: "#6c5ce7", vtS: "#f0edff",
    up: "#f04452", down: "#3182f6", upS: "#fdecee", downS: "#eaf1fe",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", track: "#222a33", hi: "#1e242c",
    vt: "#a99bff", vtS: "#241f3a",
    up: "#ff6b76", down: "#5a9cff", upS: "#2a1c20", downS: "#1b2740",
}
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const NUM = { fontVariantNumeric: "tabular-nums" as const }

const KO_CHANGE: Record<string, string> = {
    NEW: "신규",
    INCREASED: "증액",
    DECREASED: "감액",
    HELD: "유지",
}

const AN_SMS_CSS = `
.an-sms-tbl{min-width:640px}
.an-sms-head{align-items:center}
@media (max-width:700px){
.an-sms-tbl{min-width:520px}
.an-sms-head{flex-direction:column;align-items:flex-start}
}
`

function readBodyDark(): boolean {
    try {
        const _lsPref =
            typeof localStorage !== "undefined"
                ? localStorage.getItem("verity_theme")
                : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
    } catch (e) {}
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

const dot = (s?: string | null) => (s || "").replace(/-/g, ".")
// "2024-09-30" → "2024.09" (분기말 일자는 소음 — 분기 식별엔 연.월이면 충분)
const ym = (s?: string | null) => (s ? dot(s).slice(0, 7) : "—")

function fmtMoney(v: number | null | undefined, krw: boolean, fx: number): string {
    if (v == null || !Number.isFinite(v)) return "—"
    if (!krw) {
        if (v >= 1e9) return "$" + (v / 1e9).toFixed(1) + "B"
        if (v >= 1e6) return "$" + (v / 1e6).toFixed(0) + "M"
        return "$" + Math.round(v).toLocaleString()
    }
    const w = v * fx
    if (w >= 1e12) return (w / 1e12).toFixed(1) + "조원"
    if (w >= 1e8) return Math.round(w / 1e8).toLocaleString() + "억원"
    return Math.round(w / 1e4).toLocaleString() + "만원"
}

// 로고 = 토스 CDN (미국 티커도 서빙 — 2026-08-01 실호출 AAPL/NVDA/MSFT 200). 404 = 이니셜 폴백.
const TOSS_LOGO = (t: string) =>
    `https://static.toss.im/png-icons/securities/icn-sec-fill-${encodeURIComponent(t)}.png`

function TickerLogo({ ticker, C, size }: { ticker?: string | null; C: typeof LIGHT; size: number }) {
    const [bad, setBad] = useState(false)
    const box = {
        width: size,
        height: size,
        borderRadius: "50%",
        flex: `0 0 ${size}px`,
    } as const
    if (ticker && !bad) {
        return (
            <img
                src={TOSS_LOGO(ticker)}
                alt=""
                loading="lazy"
                onError={() => setBad(true)}
                style={{ ...box, objectFit: "cover", display: "block", background: C.hi }}
            />
        )
    }
    return (
        <span
            aria-hidden="true"
            style={{
                ...box,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                background: C.vtS,
                color: C.vt,
                fontSize: size * 0.34,
                fontWeight: 700,
            }}
        >
            {(ticker || "?").slice(0, 2)}
        </span>
    )
}

// 캔버스 샘플 (fetch 없는 캔버스 렌더에서 빈 화면 방지)
const CANVAS_SAMPLE = {
    _meta: {
        generated_at: "2026-08-24T09:00:00+09:00",
        managers: ["Berkshire Hathaway", "Fisher Asset Management", "AQR Capital"],
        count: 1021,
        held_since_window_quarters: 9,
        funds: {
            "Berkshire Hathaway": { report_date: "2026-06-30", filed_at: "2026-08-14" },
            "Fisher Asset Management": { report_date: "2026-06-30", filed_at: "2026-08-12" },
            "AQR Capital": { report_date: "2026-06-30", filed_at: "2026-08-13" },
        },
    },
    stocks: [
        {
            ticker: "GOOGL",
            name: "ALPHABET INC",
            total_value_usd: 48817177284,
            holder_count: 3,
            holders: [
                { fund: "Berkshire Hathaway", shares: 78791167, value_usd: 28157599351, weight_in_fund_pct: 9.8, change_type: "INCREASED", value_change_usd: 12557527438, held_since: "2025-03-31", quarters_held: 6, held_since_floor: false },
                { fund: "Fisher Asset Management", shares: 39989840, value_usd: 14291169577, weight_in_fund_pct: 5.4, change_type: "HELD", value_change_usd: 0, held_since: "2024-06-30", quarters_held: 9, held_since_floor: true },
                { fund: "AQR Capital", shares: 18000000, value_usd: 6368408356, weight_in_fund_pct: 1.9, change_type: "NEW", value_change_usd: 6368408356, held_since: "2026-06-30", quarters_held: 1, held_since_floor: false },
            ],
        },
    ],
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 * @framerIntrinsicWidth 900
 */
export default function PublicSmartMoneySearch(props: {
    dataUrl?: string
    macroUrl?: string
    dark?: boolean
    stockPath?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    // 🚨 훅은 전부 조건부 return 위 ([[feedback_framer_hooks_top_level]])
    const [themeDark, setThemeDark] = useState<boolean>(() =>
        onCanvas ? !!props.dark : readBodyDark()
    )
    const [data, setData] = useState<any>(onCanvas ? CANVAS_SAMPLE : null)
    const [q, setQ] = useState("")
    const [selTicker, setSelTicker] = useState<string | null>(onCanvas ? "GOOGL" : null)
    const [krw, setKrw] = useState(false)
    const [fx, setFx] = useState<{ rate: number; asOf: string | null }>({
        rate: FX_FALLBACK,
        asOf: null,
    })
    const inputRef = useRef<HTMLInputElement | null>(null)

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (
            typeof MutationObserver === "undefined" ||
            typeof document === "undefined" ||
            !document.body
        )
            return
        const obs = new MutationObserver(read)
        obs.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-framer-theme"],
        })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.dataUrl || BLOB + "/us_smart_money_13f.json")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive && d && Array.isArray(d.stocks)) setData(d)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas, props.dataUrl])

    // 실시간 환율 — macro_snapshot.macro.usd_krw (형제 컴포넌트 동일 소스)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.macroUrl || BLOB + "/macro_snapshot.json")
            .then((r) => (r.ok ? r.json() : null))
            .then((m) => {
                const u = m && m.macro && m.macro.usd_krw
                const v = u && Number(u.value)
                if (alive && v && Number.isFinite(v) && v > 0)
                    setFx({ rate: v, asOf: u.as_of || m.collected_at || null })
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas, props.macroUrl])

    const C = themeDark ? DARK : LIGHT
    const stocks: any[] = useMemo(
        () => (data && Array.isArray(data.stocks) ? data.stocks : []),
        [data]
    )
    const meta = (data && data._meta) || {}
    const fundsMeta: Record<string, any> = meta.funds || {}

    // 검색 — 티커 전방일치 우선, 회사명 부분일치 후순위. 최대 8건.
    const qn = q.trim().toUpperCase()
    const suggests: any[] = useMemo(() => {
        if (!qn) return []
        const byTicker: any[] = []
        const byName: any[] = []
        for (const s of stocks) {
            const tk = String(s.ticker || "").toUpperCase()
            const nm = String(s.name || "").toUpperCase()
            if (tk.startsWith(qn)) byTicker.push(s)
            else if (nm.includes(qn)) byName.push(s)
            if (byTicker.length >= 8) break
        }
        return byTicker.concat(byName).slice(0, 8)
    }, [stocks, qn])

    const cur: any = useMemo(
        () => stocks.find((s) => s.ticker === selTicker) || null,
        [stocks, selTicker]
    )
    // 미커버 안내 — 입력이 있고 제안 0 + 선택 0 일 때
    const noHit = !!qn && suggests.length === 0 && !cur

    const stockPath = (props.stockPath || "/stock").replace(/\/+$/, "")
    const goStock = (tk?: string | null) => {
        if (!tk || onCanvas) return
        try {
            window.location.href = stockPath + "?q=" + encodeURIComponent(tk)
        } catch (e) {}
    }

    const chipBg = (t: string) =>
        t === "NEW" ? C.vtS : t === "INCREASED" ? C.upS : t === "DECREASED" ? C.downS : C.hi
    const chipFg = (t: string) =>
        t === "NEW" ? C.vt : t === "INCREASED" ? C.up : t === "DECREASED" ? C.down : C.sub

    // "언제부터" 표기 — floor(추적창 상한 도달)면 "이전부터" (실제 시작은 더 과거일 수 있음)
    const heldSinceLabel = (h: any): string => {
        if (!h || !h.held_since) return "—"
        return h.held_since_floor
            ? ym(h.held_since) + " 이전부터"
            : ym(h.held_since) + "부터"
    }

    const holders: any[] = (cur && cur.holders) || []
    const latestReport = holders
        .map((h) => (fundsMeta[h.fund] || {}).report_date)
        .filter(Boolean)
        .sort()
        .pop()

    return (
        <div
            style={{
                fontFamily: FONT,
                background: C.bg,
                color: C.ink,
                borderRadius: 20,
                padding: "18px 18px 20px",
                width: "100%",
                boxSizing: "border-box",
            }}
        >
            <style>{AN_SMS_CSS}</style>

            {/* 헤더 */}
            <div
                className="an-sms-head"
                style={{ display: "flex", gap: 10, justifyContent: "space-between" }}
            >
                <div>
                    <div style={{ fontSize: 17, fontWeight: 750 }}>거장 보유 검색</div>
                    <div style={{ marginTop: 3, fontSize: 12.5, color: C.faint }}>
                        종목을 검색하면 어떤 거장 펀드가 얼마나 · 언제부터 보유 중인지
                        보여드려요 · 집중형 {(meta.managers || []).length}개 운용사 ·{" "}
                        {(meta.count || 0).toLocaleString()}종목 커버
                    </div>
                </div>
                <button
                    onClick={() => setKrw((v) => !v)}
                    style={{
                        border: "none",
                        outline: "none",
                        cursor: "pointer",
                        background: C.hi,
                        color: C.sub,
                        borderRadius: 999,
                        padding: "7px 13px",
                        fontSize: 12.5,
                        fontWeight: 650,
                        fontFamily: FONT,
                        alignSelf: "flex-start",
                        whiteSpace: "nowrap",
                    }}
                >
                    {krw ? "₩ 원화" : "$ 달러"}
                </button>
            </div>

            {/* 검색창 — 보더/아웃라인 금지, 배경 채움만 */}
            <div style={{ position: "relative", marginTop: 14 }}>
                <input
                    ref={inputRef}
                    value={q}
                    onChange={(e) => {
                        setQ(e.target.value)
                        setSelTicker(null)
                    }}
                    onKeyDown={(e) => {
                        if (e.key === "Enter" && suggests.length > 0)
                            setSelTicker(suggests[0].ticker)
                    }}
                    placeholder="티커 또는 회사명 검색 (예: NVDA, APPLE)"
                    aria-label="거장 보유 종목 검색"
                    style={{
                        width: "100%",
                        boxSizing: "border-box",
                        border: "none",
                        outline: "none",
                        background: C.card,
                        color: C.ink,
                        borderRadius: 14,
                        padding: "13px 16px",
                        fontSize: 14.5,
                        fontWeight: 600,
                        fontFamily: FONT,
                    }}
                />
                {suggests.length > 0 && !cur && (
                    <div
                        style={{
                            position: "absolute",
                            top: "calc(100% + 6px)",
                            left: 0,
                            right: 0,
                            zIndex: 1,
                            background: C.card,
                            borderRadius: 14,
                            boxShadow: themeDark
                                ? "0 8px 24px rgba(0,0,0,0.45)"
                                : "0 8px 24px rgba(25,31,40,0.10)",
                            overflow: "hidden",
                        }}
                    >
                        {suggests.map((s) => (
                            <div
                                key={s.ticker}
                                onClick={() => {
                                    setSelTicker(s.ticker)
                                    setQ(s.ticker)
                                }}
                                onKeyDown={(e: any) => {
                                    if (e.key === "Enter") {
                                        setSelTicker(s.ticker)
                                        setQ(s.ticker)
                                    }
                                }}
                                role="option"
                                tabIndex={0}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 10,
                                    padding: "10px 14px",
                                    cursor: "pointer",
                                    borderTop: `1px solid ${C.line}`,
                                }}
                            >
                                <TickerLogo ticker={s.ticker} C={C} size={26} />
                                <span style={{ fontSize: 13.5, fontWeight: 700 }}>
                                    {s.ticker}
                                </span>
                                <span
                                    style={{
                                        fontSize: 12.5,
                                        color: C.faint,
                                        overflow: "hidden",
                                        textOverflow: "ellipsis",
                                        whiteSpace: "nowrap",
                                        flex: 1,
                                    }}
                                >
                                    {s.name && s.name !== s.ticker ? s.name : ""}
                                </span>
                                <span style={{ fontSize: 12, color: C.sub, ...NUM }}>
                                    {s.holder_count}개 펀드 보유
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* 미커버 안내 — 커버리지 분모를 함께 말한다 */}
            {noHit && (
                <div style={{ marginTop: 14, fontSize: 13, color: C.sub }}>
                    "{q.trim()}" 은(는) 추적 대상에 없어요. 검색 범위는 집중형{" "}
                    {(meta.managers || []).length}개 운용사가 보유한 S&P1500{" "}
                    {(meta.count || 0).toLocaleString()}종목이에요 — 이 펀드들이 담지 않은
                    종목은 나오지 않아요.
                </div>
            )}

            {/* 결과 */}
            {cur && (
                <div
                    style={{
                        marginTop: 14,
                        background: C.card,
                        borderRadius: 16,
                        padding: "16px 16px 14px",
                    }}
                >
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 11,
                            flexWrap: "wrap",
                        }}
                    >
                        <TickerLogo ticker={cur.ticker} C={C} size={38} />
                        <div style={{ minWidth: 0, flex: 1 }}>
                            <div style={{ fontSize: 16.5, fontWeight: 750 }}>
                                {cur.ticker}
                                {cur.name && cur.name !== cur.ticker && (
                                    <span
                                        style={{
                                            marginLeft: 8,
                                            fontSize: 13,
                                            fontWeight: 550,
                                            color: C.faint,
                                        }}
                                    >
                                        {cur.name}
                                    </span>
                                )}
                            </div>
                            <div style={{ marginTop: 2, fontSize: 12.5, color: C.sub, ...NUM }}>
                                거장 {cur.holder_count}개 펀드 보유 · 합산{" "}
                                {fmtMoney(cur.total_value_usd, krw, fx.rate)}
                                {latestReport ? ` · 보유 기준일 ${dot(latestReport)}` : ""}
                            </div>
                        </div>
                        <button
                            onClick={() => goStock(cur.ticker)}
                            style={{
                                border: "none",
                                outline: "none",
                                cursor: "pointer",
                                background: C.vtS,
                                color: C.vt,
                                borderRadius: 999,
                                padding: "8px 14px",
                                fontSize: 13,
                                fontWeight: 700,
                                fontFamily: FONT,
                                whiteSpace: "nowrap",
                            }}
                        >
                            종목 리포트 →
                        </button>
                    </div>

                    <div style={{ overflowX: "auto", marginTop: 12 }}>
                        <table
                            className="an-sms-tbl"
                            style={{ width: "100%", borderCollapse: "collapse" }}
                        >
                            <thead>
                                <tr>
                                    {["운용사", "평가액", "펀드 내 비중", "주식수", "보유 시작", "기준일", "분기 변화"].map(
                                        (h, i) => (
                                            <th
                                                key={h}
                                                style={{
                                                    fontSize: 11.5,
                                                    fontWeight: 650,
                                                    letterSpacing: "0.07em",
                                                    color: C.faint,
                                                    textAlign: i === 0 ? "left" : "right",
                                                    padding: "8px 9px",
                                                    whiteSpace: "nowrap",
                                                }}
                                            >
                                                {h}
                                            </th>
                                        )
                                    )}
                                </tr>
                            </thead>
                            <tbody>
                                {holders.map((h: any) => {
                                    const fm = fundsMeta[h.fund] || {}
                                    return (
                                        <tr key={h.fund}>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    fontSize: 13.5,
                                                    fontWeight: 650,
                                                    borderTop: `1px solid ${C.line}`,
                                                    whiteSpace: "nowrap",
                                                }}
                                            >
                                                {h.fund}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    ...NUM,
                                                    fontSize: 13.5,
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                    whiteSpace: "nowrap",
                                                }}
                                            >
                                                {fmtMoney(h.value_usd, krw, fx.rate)}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    ...NUM,
                                                    fontSize: 13.5,
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                }}
                                            >
                                                {h.weight_in_fund_pct == null
                                                    ? "—"
                                                    : h.weight_in_fund_pct.toFixed(2) + "%"}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    ...NUM,
                                                    fontSize: 13.5,
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                    whiteSpace: "nowrap",
                                                }}
                                            >
                                                {Math.round(h.shares || 0).toLocaleString()}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    ...NUM,
                                                    fontSize: 13,
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                    whiteSpace: "nowrap",
                                                    color: C.sub,
                                                }}
                                            >
                                                {heldSinceLabel(h)}
                                                {h.quarters_held > 0 && (
                                                    <span style={{ color: C.faint }}>
                                                        {" "}
                                                        ({h.quarters_held}분기
                                                        {h.held_since_floor ? "+" : ""})
                                                    </span>
                                                )}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    ...NUM,
                                                    fontSize: 12.5,
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                    whiteSpace: "nowrap",
                                                    color: C.faint,
                                                }}
                                            >
                                                {ym(fm.report_date)}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                }}
                                            >
                                                <span
                                                    style={{
                                                        display: "inline-block",
                                                        padding: "2.5px 9px",
                                                        borderRadius: 999,
                                                        fontSize: 11.5,
                                                        fontWeight: 650,
                                                        background: chipBg(h.change_type),
                                                        color: chipFg(h.change_type),
                                                    }}
                                                >
                                                    {KO_CHANGE[h.change_type] || h.change_type}
                                                </span>
                                            </td>
                                        </tr>
                                    )
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* 신선도·한계 — 1급 정보 (숨기면 최신 보유로 오독) */}
            <div style={{ marginTop: 12, fontSize: 12, color: C.faint, lineHeight: 1.6 }}>
                13F 분기 공시 기준 — 분기말 보유를 최대 45일 뒤 제출하므로 현재 보유와 다를
                수 있어요. 롱 미국주식만 포함(숏·채권·현금·비미국 제외). "보유 시작"은 최근{" "}
                {meta.held_since_window_quarters || 9}개 분기 공시로 역추적한 연속 보유
                시작이며, "이전부터" 표기는 추적 범위 이전부터 보유 중이라는 뜻이에요.
                {krw &&
                    ` 환율 ${Math.round(fx.rate).toLocaleString()}원/$${fx.asOf ? ` (${dot(fx.asOf).slice(0, 16)} 기준)` : ""} 적용.`}
            </div>
        </div>
    )
}

addPropertyControls(PublicSmartMoneySearch, {
    dark: {
        type: ControlType.Boolean,
        title: "Dark (canvas)",
        defaultValue: false,
    },
    dataUrl: {
        type: ControlType.String,
        title: "데이터 URL",
        defaultValue: BLOB + "/us_smart_money_13f.json",
    },
    macroUrl: {
        type: ControlType.String,
        title: "환율 URL",
        defaultValue: BLOB + "/macro_snapshot.json",
    },
    stockPath: {
        type: ControlType.String,
        title: "종목 페이지 경로",
        defaultValue: "/stock",
    },
})

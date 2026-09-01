import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * AlphaNest 공개 — 종목 배당 이력 (한국예탁결제원 배당기준일 원장).
 *
 * 왜 별 컴포넌트인가 — `PublicStockReport.tsx` 는 10,186줄이라 손대면 라이브 편집분을
 * 덮을 위험이 크다(RULE 11). /stock 은 이미 여러 카드의 조합(StockNews·StockDetailKR 등)이라
 * 새 카드를 얹는 것이 기존 구성 방식이다.
 *
 * 데이터 = stock_report_public.json 의 종목 `dividends` 섹션 (빌더가 KSD 원장에서 부착).
 *   🚨 `stocks` 는 **배열**이다. `d.stocks[ticker]` 로 읽으면 항상 undefined 다 —
 *   PublicStockDetailKR 이 정확히 그 실수로 기관·사업장 파트가 조용히 비어 있었다(2026-08-23 발견).
 *   반드시 find 로 찾을 것.
 *
 * 🚨 RULE 7 — 점수·등급·추천 0. 공시 사실만.
 * 🚨 라이선스 = 공공저작물 제2유형(출처표시 + 상업적 이용금지). 화면에 "한국예탁결제원"
 *   표기가 **의무**다. 출처 줄을 지우지 말 것. 유료화 시 정보이용계약이 선행돼야 한다.
 * 🚨 배당기준일은 배당락일이 아니다. 기준일 당일에 사면 받지 못한다 — 안내 문구 필수.
 *
 * 테마 = 자체 내장 CSS 변수(--an-div-*) 구동. JS 다크 감지 안 씀(라이브 표준 2026-07-24). 되돌리지 말 것.
 */

const LIGHT = {
    bg: "#f2f4f6",
    card: "#ffffff",
    ink: "#191f28",
    sub: "#4e5968",
    faint: "#8b95a1",
    line: "#f0f1f3",
    vt: "#6c5ce7",
    vtS: "#f0edff",
}
const DARK = {
    bg: "#0f1318",
    card: "#171c23",
    ink: "#e3e7ec",
    sub: "#9aa4b1",
    faint: "#828d9b",
    line: "#222730",
    vt: "#a99bff",
    vtS: "#241f3a",
}
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const HEAD = "Pretendard, -apple-system, sans-serif"

const _ANP = "div"
const AN_PALETTE =
    "body{" +
    Object.keys(LIGHT)
        .map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k])
        .join(";") +
    "}" +
    'body[data-framer-theme="dark"]{' +
    Object.keys(DARK)
        .map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k])
        .join(";") +
    "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

const REPORT_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
const CLOSE_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/kr_close_latest.json"

interface DivRow {
    record_date: string
    pay_date?: string | null
    dps: number
}
interface DivSec {
    recent: DivRow[]
    ttm_dps?: number | null
    latest_record_date?: string | null
    latest_pay_date?: string | null
    paid_years_10y?: number
    upcoming_record_date?: string | null
    stock_kind?: string | null
    source?: string
    note?: string
}

const SAMPLE: DivSec = {
    recent: [
        { record_date: "2026-06-30", pay_date: "2026-08-28", dps: 374 },
        { record_date: "2026-03-31", pay_date: "2026-05-29", dps: 372 },
        { record_date: "2025-12-31", pay_date: "2026-04-17", dps: 566 },
        { record_date: "2025-09-30", pay_date: "2025-11-19", dps: 370 },
    ],
    ttm_dps: 1682,
    latest_record_date: "2026-06-30",
    latest_pay_date: "2026-08-28",
    paid_years_10y: 10,
    stock_kind: "보통주",
    source: "한국예탁결제원(KSD) · 금융위 공공데이터",
    note: "배당기준일 기준 · 한국예탁결제원 · 기준일 당일 매수로는 받지 못하며 그 전에 보유해야 함 (배당락일 아님)",
}

function readTickerFromUrl(): string {
    if (typeof window === "undefined") return ""
    try {
        const q = (
            new URLSearchParams(window.location.search).get("q") || ""
        ).trim()
        if (q) return q.toUpperCase()
        return (window.localStorage.getItem("verity_last_ticker") || "")
            .trim()
            .toUpperCase()
    } catch {
        return ""
    }
}

const md = (iso?: string | null) => {
    const s = String(iso || "")
    return s.length >= 10
        ? s.slice(2, 4) + "." + s.slice(5, 7) + "." + s.slice(8, 10)
        : "—"
}
const won = (v: any) => {
    const n = Number(v)
    if (!isFinite(n) || n <= 0) return "—"
    // 소수 배당(우선주 등)도 있어 정수화하지 않는다
    return (Math.round(n * 100) / 100).toLocaleString("ko-KR") + "원"
}

interface Props {
    ticker: string
    reportUrl: string
    closeUrl: string
    dark: boolean
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicDividendHistory(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [tk, setTk] = useState<string>(() =>
        String(props.ticker || "")
            .trim()
            .toUpperCase()
    )
    const [sec, setSec] = useState<DivSec | null>(onCanvas ? SAMPLE : null)
    const [close, setClose] = useState<{ px: number; asOf: string } | null>(
        onCanvas ? { px: 71000, asOf: "20260820" } : null
    )

    // ETF/ETN 선택 시 자기 숨김 — StockReport 가 body[data-verity-asset-kind] 발행
    const [assetKind, setAssetKind] = useState<string>("stock")
    useEffect(() => {
        if (typeof document === "undefined" || !document.body) return
        const read = () =>
            setAssetKind(document.body.dataset.verityAssetKind || "stock")
        read()
        if (typeof MutationObserver === "undefined") return
        const obs = new MutationObserver(read)
        obs.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-verity-asset-kind"],
        })
        return () => obs.disconnect()
    }, [])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries) setW(e.contentRect.width)
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    /* 종목 = prop 우선, 없으면 URL ?q → localStorage.
     *
     * 🚨 in-page 전환은 `verity-ticker-change` 로 온다. StockReport.goTicker() 가
     *   localStorage + history.replaceState + 이 커스텀 이벤트 셋을 함께 쏘는데,
     *   **replaceState 는 popstate 를 발생시키지 않는다** — popstate 만 달면 페이지 안에서
     *   종목을 바꿔도 안 울리고 폴링(최대 1s 지연)에만 의존하게 된다.
     *   LiveChart·StockBrief·DecisionPanel·ThesisNote·AISynthesis 가 전부 이 이벤트를 듣는다.
     *   폴링은 그 이벤트를 놓친 경우의 안전망으로만 남긴다.
     */
    useEffect(() => {
        if (onCanvas) return
        const propTk = String(props.ticker || "")
            .trim()
            .toUpperCase()
        if (propTk) {
            setTk(propTk)
            return
        }
        const sync = () => {
            const u = readTickerFromUrl()
            if (u) setTk((cur) => (cur === u ? cur : u))
        }
        sync()
        window.addEventListener("verity-ticker-change", sync)
        window.addEventListener("popstate", sync)
        const iv = setInterval(sync, 1000)
        return () => {
            window.removeEventListener("verity-ticker-change", sync)
            window.removeEventListener("popstate", sync)
            clearInterval(iv)
        }
    }, [props.ticker, onCanvas])

    useEffect(() => {
        if (onCanvas) return
        const code = String(tk).trim()
        if (!/^\d{6}$/.test(code)) {
            setSec(null)
            setClose(null)
            return
        } // KR 종목코드만
        let alive = true
        // 🚨 종목이 바뀌면 **먼저 비운다.** blob 이 11MB 라 첫 fetch 가 느린데, 그동안
        //   이전 종목의 배당이 새 종목 화면에 남아 보인다. 빈 화면보다 나쁜 오류다.
        setSec(null)
        setClose(null)
        fetch(props.reportUrl || REPORT_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                // 🚨 stocks 는 배열이다. d.stocks[code] 로 읽으면 영원히 undefined.
                const arr = d && Array.isArray(d.stocks) ? d.stocks : []
                const hit = arr.find((s: any) => String(s && s.ticker) === code)
                setSec(hit && hit.dividends ? (hit.dividends as DivSec) : null)
            })
            .catch(() => {
                if (alive) setSec(null)
            })
        fetch(props.closeUrl || CLOSE_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                const px = Number(d && d.prices ? d.prices[code] : 0)
                const asOf = String((d && d._meta && d._meta.as_of) || "")
                // 🚨 실패를 0 으로 흡수하지 않는다 — 없으면 null 이고 수익률을 아예 안 그린다.
                setClose(isFinite(px) && px > 0 ? { px, asOf } : null)
            })
            .catch(() => {
                if (alive) setClose(null)
            })
        return () => {
            alive = false
        }
    }, [tk, props.reportUrl, props.closeUrl, onCanvas])

    if (assetKind === "etf" || /^CMD_/.test(String(tk).toUpperCase())) return null
    const rows = sec && Array.isArray(sec.recent) ? sec.recent : []
    if (!sec || !rows.length)
        return (
            <div
                ref={rootRef}
                style={{ width: "100%", height: 0, overflow: "hidden" }}
            />
        )

    const narrow = w > 0 && w < 560
    const ttm = Number(sec.ttm_dps || 0)
    // 시가배당률 = TTM 주당배당금 ÷ 종가. 🚨 종가 기준일을 함께 표기한다(현재가 아님).
    const yieldPct = close && ttm > 0 ? (ttm / close.px) * 100 : null
    const closeMd =
        close && close.asOf.length === 8
            ? close.asOf.slice(4, 6) + "/" + close.asOf.slice(6, 8)
            : ""

    const wrap: CSSProperties = {
        width: "100%",
        minHeight: "100%",
        background: "transparent",
        fontFamily: FONT,
        padding: "0 clamp(14px, 2vw, 20px)",
        boxSizing: "border-box",
        color: C.ink,
    }
    const chip: CSSProperties = {
        fontSize: 10.5,
        fontWeight: 800,
        color: C.vt,
        background: C.vtS,
        padding: "2px 7px",
        borderRadius: 6,
        whiteSpace: "nowrap",
    }

    return (
        <div ref={rootRef} style={wrap}>
            <style>{AN_PALETTE}</style>
            <div
                style={{
                    background: C.card,
                    borderRadius: 16,
                    padding: narrow ? 14 : 18,
                    boxSizing: "border-box",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                }}
            >
                <div
                    style={{
                        display: "flex",
                        alignItems: "baseline",
                        gap: 7,
                        marginBottom: 12,
                        flexWrap: "wrap",
                    }}
                >
                    <span
                        style={{
                            fontSize: narrow ? 15 : 16,
                            fontWeight: 800,
                            letterSpacing: "-0.3px",
                        }}
                    >
                        배당
                    </span>
                    <span
                        style={{
                            fontSize: 11.5,
                            color: C.faint,
                            fontWeight: 600,
                        }}
                    >
                        배당기준일 · 사실
                    </span>
                    {sec.stock_kind && sec.stock_kind !== "보통주" ? (
                        <span style={chip}>{sec.stock_kind}</span>
                    ) : null}
                </div>

                {/* 헤드라인 — 최근 1년 주당배당금 (+ 종가 기준 시가배당률) */}
                <div
                    style={{
                        display: "flex",
                        alignItems: "baseline",
                        gap: 8,
                        flexWrap: "wrap",
                        marginBottom: 4,
                    }}
                >
                    {ttm > 0 ? (
                        <>
                            <span
                                style={{
                                    fontFamily: HEAD,
                                    fontSize: narrow ? 20 : 23,
                                    fontWeight: 800,
                                    color: C.vt,
                                    letterSpacing: "-0.6px",
                                }}
                            >
                                {won(ttm)}
                            </span>
                            <span style={{ fontSize: 12.5, fontWeight: 700 }}>
                                최근 1년 주당배당금
                            </span>
                        </>
                    ) : (
                        <span
                            style={{
                                fontSize: 12.5,
                                fontWeight: 700,
                                color: C.sub,
                            }}
                        >
                            최근 1년 배당 없음
                        </span>
                    )}
                    {yieldPct != null ? (
                        <span
                            style={{
                                fontSize: 11.5,
                                color: C.faint,
                                fontWeight: 600,
                            }}
                        >
                            시가배당률 {yieldPct.toFixed(2)}% · {closeMd} 종가
                            기준
                        </span>
                    ) : null}
                </div>

                <div
                    style={{
                        fontSize: 11.5,
                        color: C.faint,
                        fontWeight: 600,
                        marginBottom: 12,
                        lineHeight: 1.55,
                    }}
                >
                    {sec.paid_years_10y
                        ? `최근 10년 중 ${sec.paid_years_10y}년 지급`
                        : "최근 10년 지급 이력 없음"}
                    {sec.upcoming_record_date
                        ? ` · 다음 기준일 ${md(sec.upcoming_record_date)}`
                        : ""}
                </div>

                {/* 이력 */}
                <div style={{ display: "flex", flexDirection: "column" }}>
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            padding: "0 0 6px",
                            fontSize: 10.5,
                            color: C.faint,
                            fontWeight: 700,
                        }}
                    >
                        <span style={{ flex: 1, minWidth: 0 }}>배당기준일</span>
                        <span
                            style={{
                                flexShrink: 0,
                                minWidth: narrow ? 62 : 74,
                                textAlign: "right",
                            }}
                        >
                            주당
                        </span>
                        <span
                            style={{
                                flexShrink: 0,
                                minWidth: narrow ? 54 : 64,
                                textAlign: "right",
                            }}
                        >
                            지급일
                        </span>
                    </div>
                    {rows.map((r, i) => (
                        <div
                            key={i}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 8,
                                padding: "9px 0",
                                borderTop: "1px solid " + C.line,
                            }}
                        >
                            <span
                                style={{
                                    flex: 1,
                                    minWidth: 0,
                                    fontSize: 12.5,
                                    fontWeight: 700,
                                    color: C.ink,
                                }}
                            >
                                {md(r.record_date)}
                            </span>
                            <span
                                style={{
                                    flexShrink: 0,
                                    minWidth: narrow ? 62 : 74,
                                    textAlign: "right",
                                    fontSize: 12.5,
                                    fontWeight: 800,
                                    color: C.vt,
                                }}
                            >
                                {won(r.dps)}
                            </span>
                            <span
                                style={{
                                    flexShrink: 0,
                                    minWidth: narrow ? 54 : 64,
                                    textAlign: "right",
                                    fontSize: 11.5,
                                    fontWeight: 600,
                                    color: C.faint,
                                }}
                            >
                                {r.pay_date ? md(r.pay_date) : "미정"}
                            </span>
                        </div>
                    ))}
                </div>

                {/* 🚨 출처표시 = 라이선스 의무 · 기준일 오도 차단. 지우지 말 것. */}
                <div
                    style={{
                        fontSize: 10.5,
                        color: C.faint,
                        fontWeight: 500,
                        marginTop: 13,
                        lineHeight: 1.55,
                    }}
                >
                    {sec.note ||
                        "배당기준일 기준 · 기준일 당일 매수로는 받지 못하며 그 전에 보유해야 함 (배당락일 아님)"}
                    <br />
                    {sec.source || "한국예탁결제원(KSD) · 금융위 공공데이터"}
                </div>
            </div>
        </div>
    )
}

addPropertyControls(PublicDividendHistory, {
    ticker: {
        type: ControlType.String,
        title: "Ticker(빈값=URL ?q)",
        defaultValue: "",
    },
    reportUrl: {
        type: ControlType.String,
        title: "Report URL",
        defaultValue: REPORT_URL,
    },
    closeUrl: {
        type: ControlType.String,
        title: "Close URL",
        defaultValue: CLOSE_URL,
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark(캔버스 미리보기)",
        defaultValue: false,
    },
})


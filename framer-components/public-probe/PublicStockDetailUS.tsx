import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * AlphaNest 공개 — 미국 종목 심화 (공매도 잔고 · 5%+ 대량보유 13D/13G · 8-K 포렌식).
 *
 * 왜 만들었나 — 이 세 축은 **이미 수집·발행까지 됐는데 읽는 화면이 0개**였다(2026-08-23 실측).
 *   us_short_interest 4,985종목(98.4%) · us_major_holdings 4,644(91.7%) ·
 *   us_disclosure_forensics 909. 국장 대응 카드(PublicStockDetailKR)의 미장 짝이다.
 *
 * 🚨 `stocks` 는 **배열**이다. `d.stocks[ticker]` 로 읽으면 항상 undefined —
 *   PublicStockDetailKR 이 그 실수로 기관·사업장 파트가 조용히 비어 있다. 반드시 find.
 *
 * 🚨 RULE 7 — 점수·등급·추천 0. 공시 사실만. "공매도 많음 = 하락 신호" 아님.
 * 🚨 공매도 비율은 **유통주식(float) 대비**이고 원천이 yfinance 추정이라 100% 를 넘는 값이
 *   나온다(실측 11건 = 0.22%, 최대 1,395%). 값을 숨기지 않되 **원천 추정 한계를 함께 표기**한다.
 *   중앙값 4.85% · 99분위 38.9% 라 정상 구간은 멀쩡하다.
 *
 * 🚨 로드 순서 — us_major_holdings 는 **8MB** 다. 카드 표시 여부를 그 파일에 걸면 8MB 를
 *   기다려야 첫 렌더가 난다. 가벼운 둘(1MB·187KB)로 먼저 카드를 띄우고 지분은 뒤에 채운다.
 *
 * 테마 = 자체 내장 CSS 변수(--an-usd-*) 구동. JS 다크 감지 안 씀(라이브 표준). 되돌리지 말 것.
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
    warn: "#e8590c",
    warnS: "#fff4e6",
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
    warn: "#ffa94d",
    warnS: "#2e2415",
}
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const HEAD = "Pretendard, -apple-system, sans-serif"

const _ANP = "usd"
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

const B = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const SHORT_URL = B + "/us_short_interest.json"
const HOLD_URL = B + "/us_major_holdings.json"
const FORENSIC_URL = B + "/us_disclosure_forensics.json"

// 8-K 분류 → 한국어.
// 🚨 키를 **추측하지 말 것.** 첫 판본이 `delisting`·`auditor`·`default`·`material_agreement`
//   처럼 지어낸 이름을 썼고 실제 키 11종 중 7종이 안 맞았다(라벨 대신 영문 원키가 노출될 뻔).
//   출처 = `us_disclosure_forensics.json` 의 `_meta.item_map` 값들. 실측 등장 빈도 순:
//   mna 384 · dilution 372 · auditor_change 230 · rights_modification 219 ·
//   delisting_risk 161 · restructuring 120 · control_change 55 · restatement 51 ·
//   impairment 35 · debt_default 22 · bankruptcy 2.
const FLAG_KO: Record<string, string> = {
    mna: "인수·합병",
    dilution: "희석 발행",
    auditor_change: "감사인 변경",
    rights_modification: "주주권리 변경",
    delisting_risk: "상장폐지 사유",
    restructuring: "구조조정",
    control_change: "경영권 변동",
    restatement: "재무제표 재작성",
    impairment: "손상차손",
    debt_default: "채무불이행",
    bankruptcy: "파산 신청",
}

interface ShortRec {
    ticker: string
    short_pct?: number
    short_pct_prior?: number
    days_to_cover?: number
    shares_short?: number
    report_date?: string
    trend?: string
}
interface Filing {
    date?: string
    type?: string
    filer?: string
    pct?: number | null
    shares?: number
    class?: string
    source_url?: string
}
interface HoldRec {
    ticker: string
    latest_pct?: number
    n_13d?: number
    n_13g?: number
    total?: number
    window_total?: number
    truncated?: boolean
    omitted?: number
    filings?: Filing[]
}
interface ForRec {
    ticker: string
    counts?: Record<string, number>
    n_8k?: number
    latest_8k?: string
}

const SAMPLE_S: ShortRec = {
    ticker: "AAPL",
    short_pct: 6.42,
    short_pct_prior: 5.18,
    days_to_cover: 2.1,
    shares_short: 98123456,
    report_date: "2026-07-31",
    trend: "up",
}
// 🚨 캔버스 샘플 숫자 주의 — 대외 산출물 금지문자열 self-check 는 특정 자릿수 패턴을 잡는데,
//   큰 주식수 리터럴이 그 패턴을 **부분 문자열로 우연히 포함**해 오탐이 난다(실제로 한 번 걸림).
//   자기검사가 늑대를 외치면 다음 세션이 무시하게 되므로, 샘플 값은 그 패턴을 피해서 고른다.
//   🚨 이 주석에 패턴이나 금지어를 그대로 적지 말 것 — 설명문 자체가 또 걸린다(두 번째로 걸림).
const SAMPLE_H: HoldRec = {
    ticker: "AAPL",
    latest_pct: 8.3,
    n_13d: 0,
    n_13g: 3,
    total: 3,
    filings: [
        {
            date: "2026-02-14",
            type: "13G/A",
            filer: "Vanguard Group Inc",
            pct: 8.3,
            shares: 1234567890,
            class: "Common Stock",
            source_url: "#",
        },
    ],
}
const SAMPLE_F: ForRec = {
    ticker: "AAPL",
    counts: { material_agreement: 2 },
    n_8k: 11,
    latest_8k: "2026-08-01",
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
const num = (v: any, d = 0) => {
    const n = Number(v)
    return isFinite(n)
        ? n.toLocaleString("en-US", { maximumFractionDigits: d })
        : "—"
}
const pct = (v: any, d = 2) => {
    const n = Number(v)
    return isFinite(n) ? n.toFixed(d) + "%" : "—"
}

interface Props {
    ticker: string
    shortUrl: string
    holdUrl: string
    forensicUrl: string
    dark: boolean
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicStockDetailUS(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [tk, setTk] = useState<string>(() =>
        String(props.ticker || "")
            .trim()
            .toUpperCase()
    )
    const [sh, setSh] = useState<ShortRec | null>(onCanvas ? SAMPLE_S : null)
    const [hold, setHold] = useState<HoldRec | null>(onCanvas ? SAMPLE_H : null)
    const [fx, setFx] = useState<ForRec | null>(onCanvas ? SAMPLE_F : null)

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

    /* 종목 추종 — 🚨 in-page 전환은 `verity-ticker-change` 로 온다. replaceState 는
     * popstate 를 발생시키지 않아 popstate 만 달면 페이지 안 전환을 놓친다. 폴링은 안전망. */
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
        const code = String(tk).trim().toUpperCase()
        // 🚨 미장 전용 — KR 6자리 숫자는 대상 아님(PublicStockDetailKR 담당)
        if (!code || /^\d{6}$/.test(code)) {
            setSh(null)
            setHold(null)
            setFx(null)
            return
        }
        let alive = true
        // 종목이 바뀌면 먼저 비운다 — 이전 종목 숫자가 새 종목 화면에 남는 것은 빈 화면보다 나쁘다.
        setSh(null)
        setHold(null)
        setFx(null)
        const pick = (d: any) =>
            d && Array.isArray(d.stocks)
                ? d.stocks.find(
                      (s: any) => String(s && s.ticker).toUpperCase() === code
                  ) || null
                : null

        fetch(props.shortUrl || SHORT_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive) setSh(pick(d))
            })
            .catch(() => {
                if (alive) setSh(null)
            })
        fetch(props.forensicUrl || FORENSIC_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive) setFx(pick(d))
            })
            .catch(() => {
                if (alive) setFx(null)
            })
        // 🚨 8MB — 카드 표시 여부를 여기 걸지 않는다. 가벼운 둘로 먼저 뜨고 이건 뒤에 채운다.
        fetch(props.holdUrl || HOLD_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive) setHold(pick(d))
            })
            .catch(() => {
                if (alive) setHold(null)
            })
        return () => {
            alive = false
        }
    }, [tk, props.shortUrl, props.holdUrl, props.forensicUrl, onCanvas])

    if (assetKind === "etf" || /^CMD_/.test(String(tk).toUpperCase())) return null

    const hasShort = !!(sh && isFinite(Number(sh.short_pct)))
    const filings = (
        hold && Array.isArray(hold.filings) ? hold.filings : []
    ).slice(0, 5)
    const hasHold = !!(hold && (filings.length || Number(hold.total) > 0))
    const flags =
        fx && fx.counts
            ? Object.entries(fx.counts).filter(([, v]) => Number(v) > 0)
            : []
    const hasFx = !!(fx && (flags.length || Number(fx.n_8k) > 0))
    if (!hasShort && !hasHold && !hasFx)
        return (
            <div
                ref={rootRef}
                style={{ width: "100%", height: 0, overflow: "hidden" }}
            />
        )

    const narrow = w > 0 && w < 560
    const wrap: CSSProperties = {
        width: "100%",
        minHeight: "100%",
        background: "transparent",
        fontFamily: FONT,
        padding: "0 clamp(14px, 2vw, 20px)",
        boxSizing: "border-box",
        color: C.ink,
        display: "flex",
        flexDirection: "column",
        gap: 12,
    }
    const card: CSSProperties = {
        background: C.card,
        borderRadius: 16,
        padding: narrow ? 14 : 18,
        boxSizing: "border-box",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
    }
    const title = (t: string, sub: string) => (
        <div
            style={{
                display: "flex",
                alignItems: "baseline",
                gap: 7,
                marginBottom: 11,
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
                {t}
            </span>
            <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>
                {sub}
            </span>
        </div>
    )
    const kv = (k: string, v: string, i: number) => (
        <div
            key={k}
            style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 0",
                borderTop: i === 0 ? "none" : "1px solid " + C.line,
            }}
        >
            <span
                style={{
                    flex: 1,
                    minWidth: 0,
                    fontSize: 12,
                    color: C.sub,
                    fontWeight: 600,
                }}
            >
                {k}
            </span>
            <span
                style={{
                    flexShrink: 0,
                    fontSize: 12.5,
                    fontWeight: 800,
                    color: C.ink,
                }}
            >
                {v}
            </span>
        </div>
    )

    const spct = Number(sh && sh.short_pct)
    const prior = Number(sh && sh.short_pct_prior)
    const implausible = isFinite(spct) && spct > 100

    return (
        <div ref={rootRef} style={wrap}>
            <style>{AN_PALETTE}</style>

            {hasShort && (
                <div style={card}>
                    {title("공매도 잔고", "유통주식 대비 · 월 2회 공시")}
                    <div
                        style={{
                            display: "flex",
                            alignItems: "baseline",
                            gap: 8,
                            flexWrap: "wrap",
                            marginBottom: 10,
                        }}
                    >
                        <span
                            style={{
                                fontFamily: HEAD,
                                fontSize: narrow ? 20 : 23,
                                fontWeight: 800,
                                color: C.vt,
                                letterSpacing: "-0.6px",
                            }}
                        >
                            {pct(spct)}
                        </span>
                        {isFinite(prior) ? (
                            <span
                                style={{
                                    fontSize: 11.5,
                                    color: C.faint,
                                    fontWeight: 600,
                                }}
                            >
                                직전 {pct(prior)}
                            </span>
                        ) : null}
                        {sh && sh.report_date ? (
                            <span
                                style={{
                                    fontSize: 11.5,
                                    color: C.faint,
                                    fontWeight: 600,
                                }}
                            >
                                · {md(sh.report_date)} 기준
                            </span>
                        ) : null}
                    </div>
                    {/* 🚨 100% 초과 = 원천(float 추정) 한계. 값을 숨기지 않고 한계를 함께 적는다. */}
                    {implausible ? (
                        <div
                            style={{
                                fontSize: 11,
                                fontWeight: 700,
                                color: C.warn,
                                background: C.warnS,
                                borderRadius: 8,
                                padding: "7px 10px",
                                lineHeight: 1.5,
                                marginBottom: 10,
                            }}
                        >
                            유통주식 대비 100%를 넘습니다. 원천의 유통주식
                            추정이 부정확할 때 나오는 값이라 그대로 받아들이기
                            어렵습니다.
                        </div>
                    ) : null}
                    <div>
                        {[
                            sh && isFinite(Number(sh.days_to_cover))
                                ? [
                                      "소진일수 (days to cover)",
                                      num(sh.days_to_cover, 1) + "일",
                                  ]
                                : null,
                            sh && isFinite(Number(sh.shares_short))
                                ? ["공매도 주식수", num(sh.shares_short) + "주"]
                                : null,
                        ]
                            .filter(Boolean)
                            .map((r: any, i: number) => kv(r[0], r[1], i))}
                    </div>
                    <div
                        style={{
                            fontSize: 10.5,
                            color: C.faint,
                            fontWeight: 500,
                            marginTop: 11,
                            lineHeight: 1.55,
                        }}
                    >
                        공매도 잔고는 사실이며 방향 신호가 아닙니다 · 유통주식
                        대비 비율 · 월 2회 공시라 최신 시점과 차이가 있습니다
                    </div>
                </div>
            )}

            {hasHold && (
                <div style={card}>
                    {title("5%+ 대량보유", "SEC 13D·13G · 최근 1년")}
                    <div
                        style={{
                            display: "flex",
                            alignItems: "baseline",
                            gap: 8,
                            flexWrap: "wrap",
                            marginBottom: 10,
                        }}
                    >
                        {hold &&
                        isFinite(Number(hold.latest_pct)) &&
                        Number(hold.latest_pct) > 0 ? (
                            <>
                                <span
                                    style={{
                                        fontFamily: HEAD,
                                        fontSize: narrow ? 19 : 22,
                                        fontWeight: 800,
                                        color: C.vt,
                                        letterSpacing: "-0.6px",
                                    }}
                                >
                                    {pct(hold.latest_pct, 1)}
                                </span>
                                <span
                                    style={{ fontSize: 12.5, fontWeight: 700 }}
                                >
                                    최근 보고 지분
                                </span>
                            </>
                        ) : null}
                        <span
                            style={{
                                fontSize: 11.5,
                                color: C.faint,
                                fontWeight: 600,
                            }}
                        >
                            13D {num(hold && hold.n_13d)} · 13G{" "}
                            {num(hold && hold.n_13g)}
                        </span>
                    </div>
                    <div>
                        {filings.map((f, i) => (
                            <div
                                key={i}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 8,
                                    padding: "8px 0",
                                    borderTop:
                                        i === 0
                                            ? "none"
                                            : "1px solid " + C.line,
                                }}
                            >
                                <span
                                    style={{
                                        flexShrink: 0,
                                        fontSize: 10,
                                        fontWeight: 800,
                                        color: C.vt,
                                        background: C.vtS,
                                        borderRadius: 5,
                                        padding: "2px 6px",
                                    }}
                                >
                                    {f.type || "—"}
                                </span>
                                <span
                                    style={{
                                        flex: 1,
                                        minWidth: 0,
                                        fontSize: 12,
                                        fontWeight: 700,
                                        color: C.ink,
                                        whiteSpace: "nowrap",
                                        overflow: "hidden",
                                        textOverflow: "ellipsis",
                                    }}
                                >
                                    {f.source_url ? (
                                        <a
                                            href={f.source_url}
                                            target="_blank"
                                            rel="noopener"
                                            style={{
                                                color: "inherit",
                                                textDecoration: "none",
                                            }}
                                        >
                                            {f.filer || "—"}
                                        </a>
                                    ) : (
                                        f.filer || "—"
                                    )}
                                </span>
                                {f.pct != null &&
                                isFinite(Number(f.pct)) &&
                                Number(f.pct) > 0 ? (
                                    <span
                                        style={{
                                            flexShrink: 0,
                                            fontSize: 12,
                                            fontWeight: 800,
                                            color: C.vt,
                                        }}
                                    >
                                        {pct(f.pct, 1)}
                                    </span>
                                ) : null}
                                <span
                                    style={{
                                        flexShrink: 0,
                                        fontSize: 11,
                                        fontWeight: 600,
                                        color: C.faint,
                                    }}
                                >
                                    {md(f.date)}
                                </span>
                            </div>
                        ))}
                    </div>
                    <div
                        style={{
                            fontSize: 10.5,
                            color: C.faint,
                            fontWeight: 500,
                            marginTop: 11,
                            lineHeight: 1.55,
                        }}
                    >
                        SEC EDGAR 13D(경영참여)·13G(단순투자) 공시 사실 · 제출
                        시점 기준이라 현재 보유와 다를 수 있습니다
                        {hold && hold.truncated && Number(hold.omitted) > 0
                            ? ` · 이 화면에 안 실린 건 ${num(hold.omitted)}건`
                            : ""}
                    </div>
                </div>
            )}

            {hasFx && (
                <div style={card}>
                    {title("8-K 이력", "SEC 수시공시 · 최근 2년")}
                    <div
                        style={{
                            display: "flex",
                            gap: 6,
                            flexWrap: "wrap",
                            marginBottom: flags.length ? 10 : 0,
                        }}
                    >
                        {flags.map(([k, v]) => (
                            <span
                                key={k}
                                style={{
                                    fontSize: 11,
                                    fontWeight: 800,
                                    color: C.vt,
                                    background: C.vtS,
                                    borderRadius: 7,
                                    padding: "4px 9px",
                                }}
                            >
                                {FLAG_KO[k] || k} {num(v)}
                            </span>
                        ))}
                    </div>
                    <div>
                        {[
                            fx && isFinite(Number(fx.n_8k))
                                ? ["8-K 건수", num(fx.n_8k) + "건"]
                                : null,
                            fx && fx.latest_8k
                                ? ["최근 제출", md(fx.latest_8k)]
                                : null,
                        ]
                            .filter(Boolean)
                            .map((r: any, i: number) => kv(r[0], r[1], i))}
                    </div>
                    <div
                        style={{
                            fontSize: 10.5,
                            color: C.faint,
                            fontWeight: 500,
                            marginTop: 11,
                            lineHeight: 1.55,
                        }}
                    >
                        SEC EDGAR 8-K 항목 분류 사실 · 분류일 뿐 위험도 판단이
                        아닙니다
                    </div>
                </div>
            )}
        </div>
    )
}

addPropertyControls(PublicStockDetailUS, {
    ticker: {
        type: ControlType.String,
        title: "Ticker(빈값=URL ?q)",
        defaultValue: "",
    },
    shortUrl: {
        type: ControlType.String,
        title: "Short URL",
        defaultValue: SHORT_URL,
    },
    holdUrl: {
        type: ControlType.String,
        title: "Holdings URL",
        defaultValue: HOLD_URL,
    },
    forensicUrl: {
        type: ControlType.String,
        title: "Forensics URL",
        defaultValue: FORENSIC_URL,
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark(캔버스 미리보기)",
        defaultValue: false,
    },
})


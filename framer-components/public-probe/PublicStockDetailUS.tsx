import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * AlphaNest 공개 — 미국 종목 심화 (Form 4 · Form 144 · 13D/G · 13F · 공매도 · 8-K).
 *
 * 종목별 통합 API(`/api/verity/us-forensics`) 한 번으로 6개 공개 사실 소스를 읽는다.
 * 원천별 전 종목 JSON을 브라우저에서 각각 받던 구조로 되돌리지 말 것.
 *
 * 🚨 RULE 7 — 점수·등급·추천 0. 공시 사실만. "공매도 많음 = 하락 신호" 아님.
 * 🚨 공매도 비율은 **유통주식(float) 대비**이고 원천이 yfinance 추정이라 100% 를 넘는 값이
 *   나온다(실측 11건 = 0.22%, 최대 1,395%). 값을 숨기지 않되 **원천 추정 한계를 함께 표기**한다.
 *   중앙값 4.85% · 99분위 38.9% 라 정상 구간은 멀쩡하다.
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
const DEFAULT_API_BASE = "https://project-yw131.vercel.app"

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
const CHANGE_KO: Record<string, string> = {
    NEW: "신규",
    INCREASED: "증가",
    DECREASED: "감소",
    HELD: "유지",
    EXITED: "정리",
}
const SOURCE_KO: Record<string, string> = {
    insider: "Form 4",
    holdings: "13D/G",
    smart_money: "13F",
    short_interest: "공매도",
    disclosure_forensics: "8-K",
    form144: "Form 144",
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
    collection_status?: string
    event_state?: string
    recent_window_days?: number
    recent_8k_n?: number
    recent_8k_truncated?: boolean
    recent_filings?: Recent8K[]
    classification_window_days?: number
    deep_window_days?: number
}
interface Recent8K {
    date?: string
    title?: string
    source_url?: string
    item_codes?: string[]
}
interface InsiderTrade {
    date?: string
    person?: string
    position?: string
    change?: number
    code?: string
    source_url?: string
    plan_10b51?: boolean
    sell_to_cover?: boolean
}
interface InsiderRec {
    ticker: string
    net_change?: number
    buy_n?: number
    sell_n?: number
    total?: number
    trades?: InsiderTrade[]
    collected_at?: string
}
interface Form144Notice {
    person?: string
    relationship?: string
    units?: number
    value_usd?: number
    approx_sale_date?: string
    filing_date?: string
    source_url?: string
}
interface Form144Rec {
    ticker: string
    notice_count?: number
    notices_in_window?: number
    truncated?: boolean
    total_value_usd?: number
    latest_filing_date?: string
    notices?: Form144Notice[]
}
interface SmartHolder {
    fund?: string
    shares?: number
    value_usd?: number
    weight_in_fund_pct?: number
    change_type?: string
    held_since?: string
    quarters_held?: number
    source_url?: string
}
interface SmartRec {
    ticker: string
    total_value_usd?: number
    holder_count?: number
    holders?: SmartHolder[]
}
interface SourceMeta {
    status?: string
    data_state?: string
    generated_at?: string
    source?: string
    universe_n?: number
    processed_n?: number
}
interface TimelineItem {
    date: string
    kind: string
    title: string
    note?: string
    source_url?: string
    tone?: "up" | "down" | "neutral"
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
    collection_status: "covered",
    event_state: "recent_8k",
    recent_window_days: 90,
    recent_8k_n: 1,
    recent_filings: [
        {
            date: "2026-08-01",
            title: "Current report",
            source_url: "#",
            item_codes: ["1.01"],
        },
    ],
}
const SAMPLE_I: InsiderRec = {
    ticker: "AAPL",
    net_change: -1439,
    buy_n: 0,
    sell_n: 1,
    total: 1,
    trades: [
        {
            date: "2026-08-25",
            person: "Jennifer Newstead",
            position: "Officer",
            change: -1439,
            code: "S",
            source_url: "#",
            plan_10b51: true,
        },
    ],
}
const SAMPLE_144: Form144Rec = {
    ticker: "AAPL",
    notice_count: 1,
    notices_in_window: 1,
    total_value_usd: 2660900,
    latest_filing_date: "2026-08-11",
    notices: [
        {
            person: "Jennifer Newstead",
            relationship: "Officer",
            units: 8632,
            value_usd: 2660900,
            filing_date: "2026-08-11",
            source_url: "#",
        },
    ],
}
const SAMPLE_M: SmartRec = {
    ticker: "AAPL",
    total_value_usd: 65950296923,
    holder_count: 2,
    holders: [
        {
            fund: "Berkshire Hathaway",
            shares: 227917808,
            value_usd: 65950296923,
            weight_in_fund_pct: 22.04,
            change_type: "HELD",
            held_since: "2024-06-30",
            quarters_held: 9,
        },
    ],
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
    if (v === null || v === undefined || v === "") return "—"
    const n = Number(v)
    return isFinite(n)
        ? n.toLocaleString("en-US", { maximumFractionDigits: d })
        : "—"
}
const pct = (v: any, d = 2) => {
    if (v === null || v === undefined || v === "") return "—"
    const n = Number(v)
    return isFinite(n) ? n.toFixed(d) + "%" : "—"
}
const usd = (v: any) => {
    if (v === null || v === undefined || v === "") return "—"
    const n = Number(v)
    if (!isFinite(n)) return "—"
    if (Math.abs(n) >= 1e12) return "$" + (n / 1e12).toFixed(1) + "T"
    if (Math.abs(n) >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B"
    if (Math.abs(n) >= 1e6) return "$" + (n / 1e6).toFixed(1) + "M"
    return "$" + num(n)
}

interface Props {
    ticker: string
    apiBase: string
    // 이전 Framer 인스턴스 속성 호환용. 데이터 로드는 통합 API만 사용한다.
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
    const [insider, setInsider] = useState<InsiderRec | null>(
        onCanvas ? SAMPLE_I : null
    )
    const [form144, setForm144] = useState<Form144Rec | null>(
        onCanvas ? SAMPLE_144 : null
    )
    const [smart, setSmart] = useState<SmartRec | null>(
        onCanvas ? SAMPLE_M : null
    )
    const [sourceMeta, setSourceMeta] = useState<Record<string, SourceMeta>>(
        onCanvas
            ? {
                  insider: { status: "ok" },
                  holdings: { status: "ok" },
                  smart_money: { status: "ok" },
                  short_interest: { status: "ok" },
                  disclosure_forensics: { status: "ok" },
                  form144: { status: "ok" },
              }
            : {}
    )
    const [loadState, setLoadState] = useState<"idle" | "loading" | "ready" | "error">(
        onCanvas ? "ready" : "idle"
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
    }, [tk, assetKind])

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
        if (
            !code ||
            /^\d{6}$/.test(code) ||
            /^CMD_/.test(code) ||
            assetKind === "etf"
        ) {
            setSh(null)
            setHold(null)
            setFx(null)
            setInsider(null)
            setForm144(null)
            setSmart(null)
            setSourceMeta({})
            setLoadState("idle")
            return
        }
        let alive = true
        // 종목이 바뀌면 먼저 비운다 — 이전 종목 숫자가 새 종목 화면에 남는 것은 빈 화면보다 나쁘다.
        setSh(null)
        setHold(null)
        setFx(null)
        setInsider(null)
        setForm144(null)
        setSmart(null)
        setSourceMeta({})
        setLoadState("loading")
        const apiBase = (props.apiBase || DEFAULT_API_BASE).replace(/\/+$/, "")
        fetch(
            apiBase +
                "/api/verity/us-forensics?ticker=" +
                encodeURIComponent(code),
            { cache: "no-store" }
        )
            .then((r) => {
                if (!r.ok) throw new Error(String(r.status))
                return r.json()
            })
            .then((d) => {
                if (!alive) return
                const sections = d && d.status === "ok" ? d.sections || {} : {}
                setInsider(sections.insider || null)
                setHold(sections.holdings || null)
                setSmart(sections.smart_money || null)
                setSh(sections.short_interest || null)
                setFx(sections.disclosure_forensics || null)
                setForm144(sections.form144 || null)
                setSourceMeta((d && d.sources) || {})
                setLoadState("ready")
            })
            .catch(() => {
                if (alive) setLoadState("error")
            })
        return () => {
            alive = false
        }
    }, [tk, props.apiBase, onCanvas, assetKind])

    if (
        assetKind === "etf" ||
        !String(tk).trim() ||
        /^\d{6}$/.test(String(tk)) ||
        /^CMD_/.test(String(tk).toUpperCase())
    )
        return null

    const hasShort = !!(sh && isFinite(Number(sh.short_pct)))
    const filings = (
        hold && Array.isArray(hold.filings) ? hold.filings : []
    ).slice(0, 5)
    const hasHold = !!(hold && (filings.length || Number(hold.total) > 0))
    const flags =
        fx && fx.counts
            ? Object.entries(fx.counts).filter(([, v]) => Number(v) > 0)
            : []
    const recent8k = (
        fx && Array.isArray(fx.recent_filings) ? fx.recent_filings : []
    ).slice(0, 5)
    const hasFx = !!fx
    const trades = (
        insider && Array.isArray(insider.trades) ? insider.trades : []
    ).slice(0, 5)
    const notices = (
        form144 && Array.isArray(form144.notices) ? form144.notices : []
    ).slice(0, 5)
    const holders = (
        smart && Array.isArray(smart.holders) ? smart.holders : []
    ).slice(0, 5)
    const hasInsider = !!(
        insider &&
        (trades.length || Number(insider.total) > 0)
    )
    const has144 = !!(
        form144 &&
        (notices.length || Number(form144.notice_count) > 0)
    )
    const hasSmart = !!(
        smart &&
        (holders.length || Number(smart.holder_count) > 0)
    )
    const sourceKeys = [
        "insider",
        "holdings",
        "smart_money",
        "short_interest",
        "disclosure_forensics",
        "form144",
    ]
    const sourceHit = sourceKeys.filter(
        (key) => sourceMeta[key] && sourceMeta[key].status === "ok"
    ).length
    const unavailable = sourceKeys.filter(
        (key) => !sourceMeta[key] || sourceMeta[key].status !== "ok"
    )

    const timeline: TimelineItem[] = []
    trades.slice(0, 4).forEach((trade) => {
        if (!trade.date) return
        const change = Number(trade.change)
        const sold = isFinite(change) && change < 0
        const bought = isFinite(change) && change > 0
        timeline.push({
            date: trade.date,
            kind: "Form 4",
            title:
                (trade.person || "내부자") +
                " · " +
                (sold ? "매도 " : bought ? "매수 " : "거래 ") +
                num(Math.abs(change)) +
                "주",
            note: [
                trade.position,
                trade.plan_10b51 ? "10b5-1 계획" : "",
                trade.sell_to_cover ? "세금 원천징수 목적" : "",
            ]
                .filter(Boolean)
                .join(" · "),
            source_url: trade.source_url,
            tone: sold ? "down" : bought ? "up" : "neutral",
        })
    })
    notices.slice(0, 4).forEach((notice) => {
        const date = notice.filing_date || notice.approx_sale_date
        if (!date) return
        timeline.push({
            date,
            kind: "Form 144",
            title:
                (notice.person || "내부자") +
                " · 매도 예정 " +
                num(notice.units) +
                "주",
            note: "예정 신고 · 실제 체결 아님",
            source_url: notice.source_url,
            tone: "neutral",
        })
    })
    filings.slice(0, 3).forEach((filing) => {
        if (!filing.date) return
        timeline.push({
            date: filing.date,
            kind: filing.type || "13D/G",
            title:
                (filing.filer || "대량보유자") +
                (filing.pct != null && Number(filing.pct) > 0
                    ? " · " + pct(filing.pct, 1)
                    : ""),
            note: "5% 이상 보유 공시",
            source_url: filing.source_url,
            tone: "neutral",
        })
    })
    if (hasShort && sh && sh.report_date)
        timeline.push({
            date: sh.report_date,
            kind: "Short",
            title: "공매도 잔고 " + pct(sh.short_pct),
            note: "유통주식 대비 · 월 2회 공시",
            tone: "neutral",
        })
    recent8k.slice(0, 3).forEach((filing) => {
        if (!filing.date) return
        timeline.push({
            date: filing.date,
            kind: "8-K",
            title: filing.title || "SEC 수시공시",
            note: (filing.item_codes || []).length
                ? "SEC 항목 " + (filing.item_codes || []).join(", ")
                : "SEC 8-K",
            source_url: filing.source_url,
            tone: "neutral",
        })
    })
    if (recent8k.length === 0 && hasFx && fx && fx.latest_8k)
        timeline.push({
            date: fx.latest_8k,
            kind: "8-K",
            title: "최근 심화 분류 이력 · " + num(fx.n_8k) + "건",
            note: flags
                .slice(0, 3)
                .map(([key]) => FLAG_KO[key] || key)
                .join(" · "),
            tone: "neutral",
        })
    timeline.sort((a, b) => String(b.date).localeCompare(String(a.date)))

    const narrow = w > 0 && w < 560
    const wrap: CSSProperties = {
        width: "100%",
        minHeight: "100%",
        background: "transparent",
        fontFamily: FONT,
        padding: narrow ? "0 12px" : "0 18px",
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
    const grid: CSSProperties = {
        display: "grid",
        gridTemplateColumns: w >= 760 ? "repeat(2, minmax(0,1fr))" : "1fr",
        gap: 12,
        alignItems: "start",
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
    const hasAny =
        hasInsider || has144 || hasSmart || hasShort || hasHold || hasFx

    if (loadState === "loading")
        return (
            <div ref={rootRef} style={wrap}>
                <style>{AN_PALETTE}</style>
                <div style={{ ...card, color: C.faint, fontSize: 12 }}>
                    미국 공시·수급 상세 확인 중…
                </div>
            </div>
        )
    if (loadState === "error")
        return (
            <div ref={rootRef} style={wrap}>
                <style>{AN_PALETTE}</style>
                <div role="status" style={{ ...card, color: C.sub, fontSize: 12 }}>
                    미국 공시·수급 상세를 불러오지 못했습니다. 위 기본 리포트는
                    그대로 이용할 수 있습니다.
                </div>
            </div>
        )

    return (
        <div ref={rootRef} style={wrap}>
            <style>{AN_PALETTE}</style>

            <header
                style={{
                    ...card,
                    display: "flex",
                    alignItems: "flex-start",
                    justifyContent: "space-between",
                    gap: 12,
                }}
            >
                <div style={{ minWidth: 0 }}>
                    <div
                        style={{
                            color: C.vt,
                            fontSize: 11,
                            fontWeight: 800,
                        }}
                    >
                        미국 공시·수급 상세
                    </div>
                    <div
                        style={{
                            marginTop: 4,
                            color: C.ink,
                            fontSize: narrow ? 17 : 19,
                            fontWeight: 800,
                            letterSpacing: "-0.45px",
                        }}
                    >
                        {tk}에서 실제로 달라진 것
                    </div>
                    <div
                        style={{
                            marginTop: 5,
                            color: C.faint,
                            fontSize: 10.5,
                            lineHeight: 1.55,
                        }}
                    >
                        SEC 공시와 시장 자료를 기준일 순서로 봅니다 · 추천·점수
                        없음
                    </div>
                </div>
                <div
                    style={{
                        flexShrink: 0,
                        borderRadius: 999,
                        padding: "6px 9px",
                        background: C.vtS,
                        color: C.vt,
                        fontSize: 10.5,
                        fontWeight: 800,
                        whiteSpace: "nowrap",
                    }}
                >
                    연결 {sourceHit}/{sourceKeys.length}
                </div>
            </header>

            {unavailable.length > 0 ? (
                <div
                    role="status"
                    style={{
                        padding: "9px 12px",
                        borderRadius: 10,
                        background: C.warnS,
                        color: C.warn,
                        fontSize: 10.5,
                        fontWeight: 700,
                    }}
                >
                    현재 미조회 {unavailable.length}개 · {unavailable
                        .map((key) => SOURCE_KO[key] || key)
                        .join(", ")}
                </div>
            ) : null}

            {timeline.length > 0 ? (
                <section style={card} aria-labelledby="us-fact-timeline-title">
                    {title("최근 변화 연대기", "서로 다른 공시 주기의 실제 기준일")}
                    <div id="us-fact-timeline-title">
                        {timeline.slice(0, 12).map((item, index) => {
                            const tone =
                                item.tone === "up"
                                    ? C.up
                                    : item.tone === "down"
                                      ? C.down
                                      : C.vt
                            return (
                                <div
                                    key={item.kind + item.date + index}
                                    style={{
                                        display: "grid",
                                        gridTemplateColumns: narrow
                                            ? "58px minmax(0,1fr)"
                                            : "70px 64px minmax(0,1fr)",
                                        gap: 8,
                                        alignItems: "start",
                                        padding: "9px 0",
                                        borderTop:
                                            index === 0
                                                ? "none"
                                                : "1px solid " + C.line,
                                    }}
                                >
                                    <span
                                        style={{
                                            color: C.faint,
                                            fontSize: 10.5,
                                            fontWeight: 600,
                                        }}
                                    >
                                        {md(item.date)}
                                    </span>
                                    {!narrow ? (
                                        <span
                                            style={{
                                                color: tone,
                                                fontSize: 10,
                                                fontWeight: 800,
                                            }}
                                        >
                                            {item.kind}
                                        </span>
                                    ) : null}
                                    <div style={{ minWidth: 0 }}>
                                        {item.source_url ? (
                                            <a
                                                href={item.source_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                style={{
                                                    color: C.ink,
                                                    fontSize: 11.5,
                                                    fontWeight: 750,
                                                    lineHeight: 1.45,
                                                    textDecoration: "none",
                                                }}
                                            >
                                                {narrow ? item.kind + " · " : ""}
                                                {item.title}
                                            </a>
                                        ) : (
                                            <span
                                                style={{
                                                    color: C.ink,
                                                    fontSize: 11.5,
                                                    fontWeight: 750,
                                                    lineHeight: 1.45,
                                                }}
                                            >
                                                {narrow ? item.kind + " · " : ""}
                                                {item.title}
                                            </span>
                                        )}
                                        {item.note ? (
                                            <div
                                                style={{
                                                    marginTop: 2,
                                                    color: C.faint,
                                                    fontSize: 9.5,
                                                    lineHeight: 1.45,
                                                }}
                                            >
                                                {item.note}
                                            </div>
                                        ) : null}
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                </section>
            ) : null}

            {!hasAny && loadState === "ready" ? (
                <div style={{ ...card, color: C.sub, fontSize: 12 }}>
                    연결된 {sourceKeys.length}개 소스에서 이 종목의 표시 가능한 기록을 찾지
                    못했습니다. 기록 부재와 소스 장애는 구분해 표시합니다.
                </div>
            ) : null}

            {hasAny ? <div style={grid}>
            {hasInsider && (
                <section style={card} aria-labelledby="us-form4-title">
                    {title("내부자 실제 거래", "SEC Form 4 · 체결 후 신고")}
                    <div
                        id="us-form4-title"
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
                                fontSize: narrow ? 19 : 22,
                                fontWeight: 800,
                                color:
                                    Number(insider && insider.net_change) > 0
                                        ? C.up
                                        : Number(insider && insider.net_change) < 0
                                          ? C.down
                                          : C.ink,
                            }}
                        >
                            {Number(insider && insider.net_change) > 0 ? "+" : ""}
                            {num(insider && insider.net_change)}주
                        </span>
                        <span
                            style={{
                                color: C.faint,
                                fontSize: 11,
                                fontWeight: 650,
                            }}
                        >
                            매수 {num(insider && insider.buy_n)} · 매도 {num(insider && insider.sell_n)}
                        </span>
                    </div>
                    <div>
                        {trades.map((trade, index) => {
                            const change = Number(trade.change)
                            return (
                                <div
                                    key={(trade.date || "") + (trade.person || "") + index}
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 8,
                                        padding: "8px 0",
                                        borderTop:
                                            index === 0
                                                ? "none"
                                                : "1px solid " + C.line,
                                    }}
                                >
                                    <span
                                        style={{
                                            flex: 1,
                                            minWidth: 0,
                                            overflow: "hidden",
                                            textOverflow: "ellipsis",
                                            whiteSpace: "nowrap",
                                            color: C.ink,
                                            fontSize: 11.5,
                                            fontWeight: 700,
                                        }}
                                    >
                                        {trade.source_url ? (
                                            <a href={trade.source_url} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "none" }}>
                                                {trade.person || "—"}
                                            </a>
                                        ) : trade.person || "—"}
                                    </span>
                                    <span style={{ color: change > 0 ? C.up : change < 0 ? C.down : C.sub, fontSize: 11.5, fontWeight: 800 }}>
                                        {change > 0 ? "+" : ""}{num(change)}주
                                    </span>
                                    <span style={{ color: C.faint, fontSize: 10.5 }}>{md(trade.date)}</span>
                                </div>
                            )
                        })}
                    </div>
                    <div style={{ color: C.faint, fontSize: 10.5, lineHeight: 1.55, marginTop: 10 }}>
                        매수·매도 사실이며 회사 전망 신호가 아닙니다 · 10b5-1 계획과
                        세금 원천징수 목적 여부는 각 행의 원문에서 확인합니다
                    </div>
                </section>
            )}

            {has144 && (
                <section style={card} aria-labelledby="us-form144-title">
                    {title("내부자 매도 예정", "SEC Form 144 · 체결 확인 아님")}
                    <div id="us-form144-title" style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap", marginBottom: 10 }}>
                        <span style={{ fontFamily: HEAD, fontSize: narrow ? 19 : 22, fontWeight: 800, color: C.vt }}>
                            {num(form144 && form144.notice_count)}건
                        </span>
                        <span style={{ color: C.faint, fontSize: 11, fontWeight: 650 }}>
                            신고 합계 {usd(form144 && form144.total_value_usd)}
                        </span>
                    </div>
                    <div>
                        {notices.map((notice, index) => (
                            <div key={(notice.filing_date || "") + (notice.person || "") + index} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto", gap: 8, alignItems: "center", padding: "8px 0", borderTop: index === 0 ? "none" : "1px solid " + C.line }}>
                                <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: C.ink, fontSize: 11.5, fontWeight: 700 }}>
                                    {notice.source_url ? <a href={notice.source_url} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "none" }}>{notice.person || "—"}</a> : notice.person || "—"}
                                </span>
                                <span style={{ color: C.sub, fontSize: 11, fontWeight: 700 }}>{num(notice.units)}주</span>
                                <span style={{ color: C.faint, fontSize: 10.5 }}>{md(notice.filing_date || notice.approx_sale_date)}</span>
                            </div>
                        ))}
                    </div>
                    <div style={{ color: C.faint, fontSize: 10.5, lineHeight: 1.55, marginTop: 10 }}>
                        매도 의향 신고라 실제로 전부 체결됐다는 뜻이 아닙니다
                        {form144 && form144.truncated ? " · 화면은 최근 일부 신고만 표시합니다" : ""}
                    </div>
                </section>
            )}

            {hasSmart && (
                <section style={card} aria-labelledby="us-13f-title">
                    {title("기관 분기 보유", "SEC 13F · 집중형 매니저")}
                    <div id="us-13f-title" style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap", marginBottom: 10 }}>
                        <span style={{ fontFamily: HEAD, fontSize: narrow ? 19 : 22, fontWeight: 800, color: C.vt }}>
                            {num(smart && smart.holder_count)}곳
                        </span>
                        <span style={{ color: C.faint, fontSize: 11, fontWeight: 650 }}>
                            보고가치 합계 {usd(smart && smart.total_value_usd)}
                        </span>
                    </div>
                    <div>
                        {holders.map((holder, index) => {
                            const change = String(holder.change_type || "").toUpperCase()
                            const tone = change === "NEW" || change === "INCREASED" ? C.up : change === "DECREASED" || change === "EXITED" ? C.down : C.faint
                            return (
                                <div key={(holder.fund || "") + index} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto", gap: 8, alignItems: "center", padding: "8px 0", borderTop: index === 0 ? "none" : "1px solid " + C.line }}>
                                    <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: C.ink, fontSize: 11.5, fontWeight: 700 }}>{holder.fund || "—"}</span>
                                    <span style={{ color: tone, fontSize: 10.5, fontWeight: 800 }}>{CHANGE_KO[change] || change || "—"}</span>
                                    <span style={{ color: C.sub, fontSize: 10.5, fontWeight: 700 }}>{usd(holder.value_usd)}</span>
                                </div>
                            )
                        })}
                    </div>
                    <div style={{ color: C.faint, fontSize: 10.5, lineHeight: 1.55, marginTop: 10 }}>
                        분기말 보유를 최대 45일 뒤 신고한 자료입니다 · 가치 변화에는
                        주가 변화가 섞여 있어 순매수 금액으로 읽지 않습니다
                    </div>
                </section>
            )}

            {hasShort && (
                <section style={card}>
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
                </section>
            )}

            {hasHold && (
                <section style={card}>
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
                </section>
            )}

            {hasFx && (
                <section style={card}>
                    {title(
                        "8-K 이력",
                        fx && fx.deep_window_days
                            ? `SEC 수시공시 · 최근 ${num(fx.recent_window_days || 90)}일 + ${num(fx.deep_window_days)}일 심화`
                            : `SEC 수시공시 · 최근 ${num((fx && fx.recent_window_days) || 90)}일`
                    )}
                    {fx && fx.event_state === "no_recent_8k" ? (
                        <div
                            style={{
                                borderRadius: 12,
                                padding: "12px 13px",
                                background: C.bg,
                                color: C.sub,
                                fontSize: 12,
                                fontWeight: 700,
                                lineHeight: 1.55,
                                marginBottom: flags.length ? 10 : 0,
                            }}
                        >
                            최근 {num(fx.recent_window_days || 90)}일 8-K 없음
                            <div style={{ marginTop: 3, color: C.faint, fontSize: 10.5, fontWeight: 500 }}>
                                SEC 원천 조회는 완료됐고 해당 기간에 제출된 8-K가 없습니다.
                            </div>
                        </div>
                    ) : fx && fx.event_state === "unknown" ? (
                        <div
                            style={{
                                borderRadius: 12,
                                padding: "12px 13px",
                                background: C.warnS,
                                color: C.warn,
                                fontSize: 12,
                                fontWeight: 700,
                                lineHeight: 1.55,
                                marginBottom: flags.length ? 10 : 0,
                            }}
                        >
                            8-K 원천 확인 필요
                            <div style={{ marginTop: 3, color: C.faint, fontSize: 10.5, fontWeight: 500 }}>
                                공시가 없다는 뜻이 아니라 이번 수집에서 확인되지 않은 상태입니다.
                            </div>
                        </div>
                    ) : null}
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
                            fx && fx.event_state === "recent_8k"
                                ? [
                                      `최근 ${num(fx.recent_window_days || 90)}일`,
                                      num(fx.recent_8k_n) + (fx.recent_8k_truncated ? "건 이상" : "건"),
                                  ]
                                : null,
                            fx && fx.deep_window_days && isFinite(Number(fx.n_8k))
                                ? ["심화 분류 범위", num(fx.n_8k) + "건"]
                                : null,
                            fx && fx.latest_8k
                                ? ["최근 제출", md(fx.latest_8k)]
                                : null,
                        ]
                            .filter(Boolean)
                            .map((r: any, i: number) => kv(r[0], r[1], i))}
                    </div>
                    {recent8k.length > 0 ? (
                        <div style={{ marginTop: 8 }}>
                            {recent8k.map((filing, index) => (
                                <div
                                    key={(filing.date || "") + (filing.source_url || "") + index}
                                    style={{
                                        display: "grid",
                                        gridTemplateColumns: "minmax(0,1fr) auto",
                                        gap: 8,
                                        alignItems: "center",
                                        padding: "8px 0",
                                        borderTop: index === 0 ? "none" : "1px solid " + C.line,
                                    }}
                                >
                                    <div style={{ minWidth: 0 }}>
                                        {filing.source_url ? (
                                            <a href={filing.source_url} target="_blank" rel="noopener noreferrer" style={{ color: C.ink, textDecoration: "none", fontSize: 11.5, fontWeight: 700 }}>
                                                {filing.title || "SEC 8-K"}
                                            </a>
                                        ) : (
                                            <span style={{ color: C.ink, fontSize: 11.5, fontWeight: 700 }}>
                                                {filing.title || "SEC 8-K"}
                                            </span>
                                        )}
                                        {(filing.item_codes || []).length > 0 ? (
                                            <div style={{ marginTop: 2, color: C.faint, fontSize: 10 }}>
                                                SEC 항목 {(filing.item_codes || []).join(", ")}
                                            </div>
                                        ) : null}
                                    </div>
                                    <span style={{ color: C.faint, fontSize: 10.5, fontWeight: 600 }}>
                                        {md(filing.date)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    ) : null}
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
                </section>
            )}
            </div> : null}
        </div>
    )
}

addPropertyControls(PublicStockDetailUS, {
    ticker: {
        type: ControlType.String,
        title: "Ticker(빈값=URL ?q)",
        defaultValue: "",
    },
    apiBase: {
        type: ControlType.String,
        title: "API Base",
        defaultValue: DEFAULT_API_BASE,
    },
    shortUrl: {
        type: ControlType.String,
        title: "Short URL(이전 호환)",
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

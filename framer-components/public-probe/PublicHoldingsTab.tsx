import { addPropertyControls, ControlType, RenderTarget } from "framer"
import {
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
    type CSSProperties,
} from "react"

/**
 * 내 보유종목 — VERITY 공개 터미널 (AlphaNest) 탭. [보유종목 | 분산 | 예상 세금] 3-탭.
 * 🚨 분산 탭(2026-07-04) = 사실 계산기(추천 아님): 지역 비중·집중도(사실 산술) + 목표 갭(100% 사용자 설정) + 보유 자산군 ETF 자금(etf_flow 사실). 조합 추천·점수 0 (RULE 6/7·유사투자자문 회피).
 *
 * 인증 — localStorage["verity_supabase_session"].access_token → /api/holdings (user_holdings CRUD).
 *   미로그인/캔버스 = SAMPLE 미리보기 + 로그인 CTA. (StockDashboard getAccessToken 패턴 재사용)
 * RULE 7 — 평가손익 = 종가 × 수량 − 입력평단 (단순 계산·사실). 매수·매도·추천·점수 0.
 * 🚨 시세 재배포 컴플라이언스(2026-07-03 Phase 1.5): /api/stock 실시간가 폴링 제거 — KIS/yfinance 시세 회원(제3자) 재배포 불가.
 *   평가 기준가 = kr_close_latest.json (금융위 공공데이터 직전 거래일 종가, 전 종목 동일 기준일, ~2,900종목).
 *   🚨 되돌리지 말 것 (2026-07-31) — 옛 소스 stock_flow_5d.json 은 회전 수집이라 종목마다 종가 날짜가
 *   달라(어제~5주 전) 하락 종목이 플러스로 표시됐다(실측 71% 불일치). 커버리지 밖(미국·ETF·거래정지)은
 *   0% 로 위장하지 않고 "시세 없음" + 손익 합계 제외.
 *   실시간 시세 = 행 클릭 → 종목 리포트(네이버 link-out + TV 위젯)에서.
 * 반응형 — ResizeObserver. 테마 = body[data-framer-theme] 자가감지. 브랜드 보라(vg).
 * 🚩 국기 = circle-flags SVG(Logo/FlagIcon) — 이모지 금지(싸구려). 데모 = 단순 CTA(3D목업 X).
 *
 * 예상 세금 탭: 보유(같은 데이터) → 매도 가정 비용 추정.
 *   세금(법정·증권사 무관) = KR 양도세 0%(비과세 ~2029)+증권거래세 0.20% / US 양도세 22%·27.5%·250만 공제(누진) / 대주주 10억 경고.
 *   수수료(증권사별) = broker_guide.json domestic_fee/overseas_fee × 매도금액.
 *   세제 SoT = api/trading/account_profile.py (변경 시 TAX 상수 동기화). RULE 7 사실+세무사 면책, RULE 6 LLM 0.
 */

const LIGHT = {
    bg: "#f2f4f6",
    card: "#ffffff",
    ink: "#191f28",
    sub: "#4e5968",
    faint: "#8b95a1",
    line: "#e5e8eb",
    up: "#f04452",
    down: "#3182f6",
    vg: "#6c5ce7",
    vgS: "#f0edff",
    vt: "#6c5ce7",
    vtS: "#f0edff",
    danger: "#f04452",
    warn: "#ff9500",
    warnS: "#fff6e9",
    onAccent: "#ffffff",
    shim: "#e9edf1",
    shimHi: "#f3f5f7",
    buyS: "#eaf2ff",
    sellS: "#ffeaec",
    rowHd: "#f7f8fa",
}
const DARK = {
    bg: "#0f1318",
    card: "#171c23",
    ink: "#e3e7ec",
    sub: "#9aa4b1",
    faint: "#828d9b",
    line: "#252b34",
    up: "#f04452",
    down: "#5b9bff",
    vg: "#a99bff",
    vgS: "#241f3a",
    vt: "#a99bff",
    vtS: "#241f3a",
    danger: "#f04452",
    warn: "#ffb340",
    warnS: "#3a2c14",
    onAccent: "#0f1318",
    shim: "#222a33",
    shimHi: "#2d3742",
    buyS: "#152238",
    sellS: "#3a1a1e",
    rowHd: "#1c222b",
}
// 🎨 2026-08-03 테마 = 자체 내장 CSS 변수(--an-hld-*) 구동. **JS 다크 감지 제거.**
//   PublicExploreHub(--an-exh-*) 와 동일 규약. 되돌리지 말 것 — 이유:
//   JS 판정(readBodyDark)은 Framer 정적 export 의 첫 페인트와 경쟁해 라이트로 떨어지고,
//   그러면 컴포넌트가 흰 판을 깔거나 글자가 배경색에 묻힌다(2026-08-01 리포트 / 08-03 둥지).
//   CSS 변수는 body[data-framer-theme] 에 직접 걸려 Framer 가 테마를 바꾸는 순간 같이 바뀐다.
const _ANP = "hld"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const CVAR: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) CVAR[_k] = "var(--an-" + _ANP + "-" + _k + ")"

const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const FX_FALLBACK = 1380 // 스냅샷 실패 시에만 — 평상시엔 실환율(useAnFx)

/* ── 환율·통화 (2026-07-30) ────────────────────────────────────────────────
   🚨 옛 코드는 FX 를 1380 으로 **하드코딩**해 두고 화면에도 "환율 1380원/$ 가정" 이라 적었다.
   실제 환율이 1,450원대라 미국 보유분 평가액이 약 5% 낮게 잡히고 있었다(PM 지적 계기).
   이제 macro_snapshot.json 의 usd_krw(yfinance, 30분 크론)를 읽는다. 실시간 틱이 아니므로
   화면에 기준 시각을 함께 적는다 — 없는 정밀도를 있는 척하지 않는다. 스냅샷 실패 시에만 1380 폴백.
   Framer 코드 컴포넌트는 서로 import 할 수 없어 이 블록은 각 파일에 같은 모양으로 둔다. */
const AN_FX_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/macro_snapshot.json"
const AN_CCY_KEY = "an_ccy"
const AN_CCY_EVENT = "an-ccy-change"
function anReadCcy(): string {
    try {
        return window.localStorage.getItem(AN_CCY_KEY) === "KRW" ? "KRW" : "USD"
    } catch (e) {
        return "USD"
    }
}
function useAnCcy(onCanvas: boolean): [string, (v: string) => void] {
    const [ccy, setCcy] = useState<string>(() => (onCanvas ? "USD" : anReadCcy()))
    useEffect(() => {
        if (onCanvas) return
        const read = () => setCcy(anReadCcy())
        read()
        window.addEventListener(AN_CCY_EVENT, read)
        window.addEventListener("storage", read)
        return () => {
            window.removeEventListener(AN_CCY_EVENT, read)
            window.removeEventListener("storage", read)
        }
    }, [onCanvas])
    return [
        ccy,
        (v: string) => {
            setCcy(v)
            try {
                window.localStorage.setItem(AN_CCY_KEY, v)
                window.dispatchEvent(new CustomEvent(AN_CCY_EVENT))
            } catch (e) {
                /* no-op */
            }
        },
    ]
}
function useAnFx(onCanvas: boolean): { rate: number; asOf: string; ok: boolean } {
    const [fx, setFx] = useState<any>(null)
    useEffect(() => {
        if (onCanvas || fx) return
        let alive = true
        try {
            const c = sessionStorage.getItem("an_fx")
            if (c) {
                const j = JSON.parse(c)
                if (j && j.rate > 0) {
                    setFx(j)
                    return
                }
            }
        } catch (e) {
            /* no-op */
        }
        fetch(AN_FX_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const u = d && d.macro && d.macro.usd_krw
                const rate = Number(u && u.value)
                if (!alive || !(rate > 0)) return
                const j = { rate, asOf: String((u && u.as_of) || "") }
                setFx(j)
                try {
                    sessionStorage.setItem("an_fx", JSON.stringify(j))
                } catch (e) {
                    /* no-op */
                }
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas, fx])
    return fx && fx.rate > 0
        ? { rate: fx.rate, asOf: fx.asOf, ok: true }
        : { rate: FX_FALLBACK, asOf: "", ok: false }
}


// ── Brandfetch 로고 (토스 핫링킹 제거 2026-07-10) — logo_map(빌드타임 확정) + US 티커 규칙 + 이니셜 폴백 ──
const BF_CID = "1idalDez9T7KlggM8qX" // 공개 임베드 client id (Logo Link 전용)
const BF_MAP_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
let __bfMap: Record<string, string> | null = null
let __bfColors: Record<string, string> = {}
let __bfShapes: Record<string, number> = {}
let __bfStyle: any = { padS: 8, padW: 15, wideRatio: 2.2 } // 발행 데이터(style)로 조절 — 코드 수정 불요
let __bfP: Promise<Record<string, string>> | null = null
function fetchBfMap(): Promise<Record<string, string>> {
    if (__bfMap) return Promise.resolve(__bfMap)
    if (!__bfP)
        __bfP = fetch(BF_MAP_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                __bfMap = (d && d.logos) || {}
                __bfColors = (d && d.colors) || {}
                __bfShapes = (d && d.shapes) || {}
                __bfStyle = (d && d.style) || __bfStyle
                return __bfMap as Record<string, string>
            })
            .catch(() => ({}) as Record<string, string>)
    return __bfP
}
function useBfLogoMap(): Record<string, string> | null {
    const [m, setM] = useState<Record<string, string> | null>(__bfMap)
    useEffect(() => {
        let al = true
        fetchBfMap().then((mm) => {
            if (al) setM(mm)
        })
        return () => {
            al = false
        }
    }, [])
    return m
}
function bfLogoPad(ticker: any): string {
    // 모양 적응 패딩 — 심볼(정사각)은 크게, 워드마크(가로 김)는 여백 확보 (토스식 가시성)
    const tk = String(ticker || "")
        .toUpperCase()
        .replace(/-/g, ".")
    const r = __bfShapes[tk] || __bfShapes[tk.replace(/\./g, "-")] || 1
    if (r === 0) return "0%" // 큐레이션 풀블리드 아이콘(자체 배경 포함) = 타일 꽉 채움
    return (
        (r > (__bfStyle.wideRatio || 2.2)
            ? __bfStyle.padW || 15
            : __bfStyle.padS || 8) + "%"
    )
}
function bfInitialBg(ticker: any): string {
    // 이니셜 타일 — 티커 해시 투톤 그라데이션 (미보유 4.6K 도 디자인 자산화, 종목별 고정색)
    let h = 0
    const s = String(ticker || "?")
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360
    return (
        "linear-gradient(135deg, hsl(" +
        h +
        ",62%,55%), hsl(" +
        ((h + 42) % 360) +
        ",68%,42%))"
    )
}
function bfLogoBg(ticker: any): string {
    // 아이덴티티 색 틴트 타일 (토스식 참조 — 색은 로고 대표색/공식 브랜드색, 자산 복사 아님)
    const tk = String(ticker || "")
        .toUpperCase()
        .replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    // 토스식 넉아웃 (기본): 브랜드색 솔리드 배경 + 로고 흰 실루엣(bfLogoFilter). 조건 미충족 = 솔리드 파스텔.
    // style.mode 노브: "knockout"(기본) | "pastel". mixPct = 파스텔 혼합비(기본 30).
    const p2 =
        (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    if (
        c &&
        p2 &&
        p2.indexOf("http") !== 0 &&
        (__bfStyle.mode || "pastel") === "knockout"
    )
        return c // 솔리드 브랜드색
    if (!c) return "#ffffff"
    const mix = Number(__bfStyle.mixPct || 30)
    try {
        if (
            typeof CSS !== "undefined" &&
            CSS.supports &&
            CSS.supports("color", "color-mix(in srgb, red 50%, white)")
        )
            return `color-mix(in srgb, ${c} ${mix}%, #ffffff)`
    } catch (e2) {}
    return c + (__bfStyle.tintA || "4D")
}
function bfLogoFilter(ticker: any): string {
    // 넉아웃 조건과 동일할 때만 흰 실루엣 (Brandfetch 투명 로고 한정 — 파비콘류는 불투명이라 제외)
    const tk = String(ticker || "")
        .toUpperCase()
        .replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    const p2 =
        (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    return c &&
        p2 &&
        p2.indexOf("http") !== 0 &&
        (__bfStyle.mode || "pastel") === "knockout"
        ? "brightness(0) invert(1)"
        : "none"
}
function bfLogoSrc(
    ticker: any,
    lm: Record<string, string> | null,
    size: number
): string {
    const tk = String(ticker || "")
        .toUpperCase()
        .replace(/-/g, ".")
    const p = (lm && (lm[tk] || lm[tk.replace(/\./g, "-")])) || "" // 맵 전용 — 미검증 경로 = B 플레이스홀더 위험(2026-07-10)
    if (!p) return ""
    if (p.indexOf("http") === 0) return p // 폴백 소스(nvstly·공식 파비콘) = 절대 URL 그대로
    return (
        "https://cdn.brandfetch.io/" +
        p +
        "?c=" +
        BF_CID +
        "&w=" +
        size * 2 +
        "&h=" +
        size * 2
    )
}
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
const KR_MK = ["KOSPI", "KOSDAQ", "KONEX"]
const BROKER_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/broker_guide.json"

// ── 세제 상수 (SoT = api/trading/account_profile.py, 2026 시행값) — inline 미러, 변경 시 동기화 ──
const TAX = {
    KR_TXN: 0.002, // 증권거래세 KOSPI/KOSDAQ (농특세 포함, 2026)
    KR_MAJOR_AMT: 1_000_000_000, // 대주주 종목당 보유 기준 = 10억 (양도세 과세)
    US_CGT: 0.22, // 해외주식 양도세 (과표 3억 이하)
    US_CGT_HIGH: 0.275, // 과표 3억 초과분
    US_DEDUCT: 2_500_000, // 해외 양도소득 기본공제 (연, 합산)
    US_BRACKET: 300_000_000, // 과표 3억 분기점
}

interface Props {
    apiBase: string
    loginUrl: string
    stockPath: string
    usStockPath: string
    dark: boolean
}
const DEFAULT_API = "https://project-yw131.vercel.app"

const SAMPLE = [
    {
        ticker: "005930",
        name: "삼성전자",
        shares: 100,
        avg_cost: 68000,
        price: 81200,
        market: "kr",
    },
    {
        ticker: "NVDA",
        name: "NVIDIA",
        shares: 20,
        avg_cost: 120,
        price: 172.4,
        market: "us",
    },
    {
        ticker: "000660",
        name: "SK하이닉스",
        shares: 15,
        avg_cost: 215000,
        price: 241000,
        market: "kr",
    },
    {
        ticker: "AAPL",
        name: "Apple",
        shares: 30,
        avg_cost: 150,
        price: 214.3,
        market: "us",
    },
]

// 거래 기록(실현손익) 데모 — 미로그인/캔버스 미리보기. 실제 데이터는 /api/trades 가 서버 이동평균 요약 반환.
const SAMPLE_TRADES = [
    {
        ticker: "005930",
        name: "삼성전자",
        market: "kr",
        side: "buy",
        shares: 100,
        price: 68000,
        traded_at: "2026-03-04",
    },
    {
        ticker: "005930",
        name: "삼성전자",
        market: "kr",
        side: "sell",
        shares: 40,
        price: 81200,
        traded_at: "2026-06-18",
    },
    {
        ticker: "NVDA",
        name: "NVIDIA",
        market: "us",
        side: "buy",
        shares: 20,
        price: 120,
        traded_at: "2026-02-11",
    },
]
const SAMPLE_TRADE_SUMMARY = {
    by_ticker: [
        {
            ticker: "005930",
            name: "삼성전자",
            market: "kr",
            realized_pnl: 528000,
            open_shares: 60,
            open_avg_cost: 68000,
        },
        {
            ticker: "NVDA",
            name: "NVIDIA",
            market: "us",
            realized_pnl: 0,
            open_shares: 20,
            open_avg_cost: 120,
        },
    ],
    total_realized_pnl: 528000,
}

function getToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const r = localStorage.getItem("verity_supabase_session")
        if (!r) return ""
        const s = JSON.parse(r)
        return s && typeof s.access_token === "string" ? s.access_token : ""
    } catch {
        return ""
    }
}
function money(v: number): string {
    if (!isFinite(v)) return "—"
    return Math.round(v).toLocaleString("en-US") + "원"
}
const won = money
function wonCompact(v: number): string {
    const a = Math.abs(Math.round(v))
    const sign = v < 0 ? "-" : ""
    if (a >= 1e8) return sign + (a / 1e8).toFixed(a >= 1e9 ? 0 : 1) + "억원"
    if (a >= 1e4)
        return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만원"
    return sign + a.toLocaleString("en-US") + "원"
}
function parseFee(s: any): number {
    const n = parseFloat(String(s || "").replace(/[%\s]/g, ""))
    return isFinite(n) ? n / 100 : 0
}
// 통화 표기 — US=$, KR=원 (거래 원장·종목별 실현손익은 네이티브 통화. 합계만 FX 환산=holdings 관행).
function px(v: number, us: boolean, ccy?: string, fx?: number): string {
    if (!isFinite(v)) return "—"
    // 미국 종목을 원화로 볼 때만 환산. 국내는 원래 원화라 손대지 않는다.
    if (us && ccy === "KRW" && fx && fx > 0)
        return Math.round(v * fx).toLocaleString("en-US") + "원"
    return us
        ? "$" + v.toLocaleString("en-US", { maximumFractionDigits: 2 })
        : Math.round(v).toLocaleString("en-US") + "원"
}
// 오늘 날짜(로컬 기준 YYYY-MM-DD) — 거래일 기본값. 자정 근처 UTC 밀림 방지 위해 tz offset 보정.
function todayISO(): string {
    try {
        const d = new Date()
        return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
            .toISOString()
            .slice(0, 10)
    } catch {
        return ""
    }
}

// 평가 기준일 "YYYYMMDD" → "7/30". 없는 정밀도를 있는 척하지 않으려면 기준일을 화면에 적어야 한다.
function fmtAsOf(s: string): string {
    const t = String(s || "")
    if (t.length !== 8) return t
    return Number(t.slice(4, 6)) + "/" + Number(t.slice(6, 8))
}

// ETF 누적 순흐름(Δ상장좌수 × NAV, 가격효과 제거) — /etf 페이지 cumFlow 와 동일 로직. 자산군 자금 방향(사실) 참조용.
const ETF_WINDOW = 20
function etfCumFlow(series: any[]): number | null {
    if (!Array.isArray(series) || series.length < 2) return null
    const win = series.slice(-ETF_WINDOW)
    const a = win[0],
        b = win[win.length - 1]
    const as = Number(a.list_shrs),
        bs = Number(b.list_shrs),
        nav = Number(b.nav)
    if (!isFinite(as) || !isFinite(bs) || !isFinite(nav)) return null
    return (bs - as) * nav
}
// 조/억 부호 포맷 (자금흐름용)
function fmtFlow(v: number): string {
    if (!isFinite(v) || v === 0) return "0"
    const a = Math.abs(v),
        s = v > 0 ? "+" : "−"
    if (a >= 1e12) return s + (a / 1e12).toFixed(2) + "조"
    if (a >= 1e8) return s + Math.round(a / 1e8).toLocaleString("en-US") + "억"
    return s + Math.round(a / 1e4).toLocaleString("en-US") + "만"
}
function flagCode(market: any): string {
    const m = String(market || "").toUpperCase()
    if (
        KR_MK.indexOf(m) >= 0 ||
        m.indexOf("KOS") >= 0 ||
        m.indexOf("KONEX") >= 0
    )
        return "kr"
    if (
        m.indexOf("NAS") >= 0 ||
        m.indexOf("NYSE") >= 0 ||
        m.indexOf("AMEX") >= 0 ||
        m.indexOf("US") >= 0
    )
        return "us"
    return "kr"
}

// 국기 = circle-flags SVG (이모지 X). Logo 의 국기 배지와 동일 소스.
function FlagIcon(props: { code: string; size?: number }) {
    const size = props.size || 15
    return (
        <img
            src={FLAG_BASE + props.code + ".svg"}
            alt=""
            loading="lazy"
            decoding="async"
            width={size}
            height={size}
            style={{
                width: size,
                height: size,
                borderRadius: "50%",
                display: "inline-block",
                verticalAlign: "-2px",
                flexShrink: 0,
            }}
        />
    )
}

function Logo(props: {
    ticker: string
    name: string
    market: string
    C: any
    size?: number
}) {
    const { ticker, name, market, C } = props
    const size = props.size || 32
    const [err, setErr] = useState(false)
    const lm = useBfLogoMap()
    const bfSrc = bfLogoSrc(ticker, lm, size)
    const ch =
        String(name || "?")
            .trim()
            .charAt(0) || "?"
    const code = flagCode(market)
    const fsize = Math.round(size * 0.46)
    return (
        <div
            style={{
                position: "relative",
                width: size,
                height: size,
                flexShrink: 0,
            }}
        >
            {!err && bfSrc ? (
                <img
                    src={bfSrc}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    width={size}
                    height={size}
                    onError={() => setErr(true)}
                    style={{
                        width: size,
                        height: size,
                        borderRadius: Math.round(size * 0.32),
                        filter: bfLogoFilter(ticker),
                        objectFit: "contain",
                        padding: bfLogoPad(ticker),
                        boxSizing: "border-box",
                        display: "block",
                        background: bfLogoBg(ticker),
                    }}
                />
            ) : (
                <div
                    style={{
                        width: size,
                        height: size,
                        borderRadius: Math.round(size * 0.32),
                        background: bfInitialBg(ticker),
                        color: "#ffffff",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: Math.round(size * 0.42),
                        fontWeight: 800,
                    }}
                >
                    {ch}
                </div>
            )}
            {code && (
                <img
                    src={FLAG_BASE + code + ".svg"}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    width={fsize}
                    height={fsize}
                    style={{
                        position: "absolute",
                        right: -3,
                        bottom: -3,
                        width: fsize,
                        height: fsize,
                        borderRadius: "50%",
                        border: `1.5px solid ${C.card}`,
                        background: C.card,
                        display: "block",
                        boxShadow: "0 1px 2px rgba(0,0,0,0.18)",
                    }}
                />
            )}
        </div>
    )
}

function readBodyDark(): boolean {
    // 🎨 html[data-an-theme](헤드 스크립트 pre-paint, 레이스 제거) → body[data-framer-theme] → verity_theme 순.
    // 🚨 body-first 금지 — Framer 정적 export 가 새로고침에 body 를 light 로 두면 verity 이전에 단락 → 부분 라이트(2026-07-23). 되돌리지 말 것.
    try {
        if (typeof document !== "undefined") {
            const h = document.documentElement ? document.documentElement.dataset.anTheme : null
            if (h === "dark") return true
            if (h === "light") return false
            if (document.body) {
                const a = document.body.dataset.framerTheme
                if (a === "dark") return true
                if (a === "light") return false
            }
        }
        const s = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (s === "dark") return true
    } catch (e) {}
    return false
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */

/* 🚨 2026-07-29 미장 링크 사고 — usStockPath 기본값이 "/us/stock" 이었는데 **그 페이지는 존재한 적이 없다**
   (실측: https://www.alphanest.kr/us/stock?q=AAPL → 404). 둥지 보유종목·브리핑·커뮤니티에서 미국 종목을
   누르면 전부 빈 404 로 떨어졌다. 리포트 페이지가 미장도 처리하므로 같은 경로로 보낸다.
   캔버스 인스턴스에 옛 값이 남아 있어도 여기서 흡수한다 — 되돌리지 말 것. */
function _usPath(us: any, kr: any): string {
    const v = String(us || "").replace(/\/+$/, "")
    if (!v || v === "/us/stock") return String(kr || "").replace(/\/+$/, "") || "/stock"
    return v
}

export default function PublicHoldingsTab(props: Props) {
    const { apiBase, loginUrl, stockPath, usStockPath, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    // 실환율 — 하드코딩 1380 대체. 스냅샷 실패 시에만 폴백값이 쓰이고 라벨로 구분된다.
    const fxInfo = useAnFx(onCanvas)
    const FX = fxInfo.rate
    const [ccy, setCcy] = useAnCcy(onCanvas)

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    // 🚨 2026-07-27 목업 깜빡임 제거 — 초기 state 에 SAMPLE 을 넣으면 Framer 정적 HTML(SSG)에 그대로
    //   구워져 실사용자에게 "삼성전자 60주·NVIDIA 20주" 가 잠깐 보였다가 실제 값으로 바뀐다(PM 지적).
    //   캔버스 프리뷰는 마운트 후 useEffect 로만 주입 → 첫 페인트는 어떤 렌더타깃에서도 목업 0.
    const [rows, setRows] = useState<any[]>([])
    const [closes, setCloses] = useState<Record<string, number>>({}) // KR 종가(kr_close_latest) — 실시간 아님
    const [closeAsOf, setCloseAsOf] = useState<string>("") // YYYYMMDD — 화면에 기준일 명시
    const [isDemo, setIsDemo] = useState(true)
    const [loading, setLoading] = useState<boolean>(() =>
        onCanvas ? false : !!getToken()
    )
    const [showAdd, setShowAdd] = useState(false)
    const [busy, setBusy] = useState(false)
    const [themeDark, setThemeDark] = useState<boolean>(() =>
        RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()
    )
    const [view, setView] = useState<"holdings" | "mix" | "tax" | "trades">(
        "holdings"
    )
    const [brokers, setBrokers] = useState<any[]>([])
    const [brokerIdx, setBrokerIdx] = useState(0)
    const [catFlow, setCatFlow] = useState<Record<string, number>>({}) // etf_flow 자산군 누적 흐름(사실, 분산 탭)
    const [targetKr, setTargetKr] = useState<number | null>(null) // 목표 국내 비중 %(사용자 설정, null=현재값)
    const [universe, setUniverse] = useState<any[]>([]) // 검색 유니버스(universe_search, KR+US)
    const [q, setQ] = useState("") // 종목 검색어
    const [pop, setPop] = useState<any>(null) // 추가/수정 팝업 {id?, ticker, name, market, shares, avg_cost}
    // 거래 기록(실현손익) — 본인 매매 이력. RULE 7 사실 기록, 순위·배지·공개 없음. /api/trades.
    const [tradeData, setTradeData] = useState<{ trades: any[]; summary: any }>(() => ({
        trades: [],
        summary: { by_ticker: [], total_realized_pnl: 0 },
    }))
    const [tradesLoading, setTradesLoading] = useState(false)
    // 캔버스 전용 목업 주입 — 마운트 후라 정적 HTML 에는 절대 포함되지 않음.
    //   라이브 미로그인 목업은 loadHoldings 의 토큰 부재 분기가 담당(로그아웃 전환도 그쪽이 처리).
    useEffect(() => {
        if (!onCanvas) return
        setRows(SAMPLE)
        setTradeData({ trades: SAMPLE_TRADES, summary: SAMPLE_TRADE_SUMMARY })
    }, [onCanvas])
    const [showTAdd, setShowTAdd] = useState(false) // 거래 추가 검색 패널
    const [tq, setTq] = useState("") // 거래 추가 종목 검색어
    const [tPop, setTPop] = useState<any>(null) // 거래 팝업 {id?, ticker, name, market, side, shares, price, traded_at}
    const [tBusy, setTBusy] = useState(false)

    // 🚨 라이브/프리뷰 = CSS 변수(Framer body[data-framer-theme] 직결).
    //   캔버스만 dark prop 정적 선택 — 캔버스는 Framer 가 body 속성을 안 줘 변수 해석이 안 된다.
    const isDark = onCanvas ? !!dark : themeDark
    const C: any = onCanvas ? (dark ? DARK : LIGHT) : CVAR
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

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
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries) setW(e.contentRect.width)
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    // 증권사 수수료 (broker_guide) — 예상 세금 탭의 매도 수수료 산정용. 실패해도 무해(수수료 0).
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(BROKER_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const bs = (d && (d.brokers || d.items)) || []
                if (alive && Array.isArray(bs) && bs.length) setBrokers(bs)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas])

    // ETF 자산군 자금흐름 (분산 탭 — 보유 자산군에 패시브 자금 유입/유출 사실. /etf 와 동일 cumFlow).
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/etf_flow.json",
            { cache: "no-store" }
        )
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d || !Array.isArray(d.etfs)) return
                const hist = d.history || {}
                const m: Record<string, number> = {}
                for (const e of d.etfs) {
                    const cf = etfCumFlow(hist[e.ticker])
                    if (cf != null) m[e.category] = (m[e.category] || 0) + cf
                }
                setCatFlow(m)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas])

    const loadHoldings = useCallback(() => {
        if (onCanvas) return
        const token = getToken()
        if (!token) {
            /* 🚨 로그인 전 미리보기 = SAMPLE 목업(브라우저 창 + "예시" 배지, pointerEvents none).
               되돌리지 말 것 — 여기서 setRows([]) 로 비우면 로그인 전 화면이 CTA 만 남는다
               (2026-07-27 깜빡임 수정의 부작용, PM 지적 2026-08-01).
               깜빡임 안전: 이 경로는 useEffect(마운트 후) 에서만 호출되어 정적 HTML 에 목업이
               구워지지 않고, 토큰이 있으면 아래 분기로 빠져 SAMPLE 이 주입될 경로 자체가 없다. */
            setIsDemo(true)
            setRows(SAMPLE)
            setTradeData({
                trades: SAMPLE_TRADES,
                summary: SAMPLE_TRADE_SUMMARY,
            })
            setLoading(false)
            return
        }
        // 🚨 토큰 있으면 즉시 로그인 화면 전환 (API 응답 기다리지 않음 — 로그인했는데 CTA 뜨는 사고 방지, 2026-07-13)
        setIsDemo(false)
        setLoading(true)
        fetch(base + "/api/holdings", {
            headers: { Authorization: "Bearer " + token },
        })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (Array.isArray(d)) setRows(d)
                else if (d && Array.isArray(d.holdings)) setRows(d.holdings)
            })
            .catch(() => {})
            .finally(() => setLoading(false))
    }, [base, onCanvas])

    // 마운트 + 로그인/로그아웃(verity_auth_change·다른 탭 storage) 시 재평가 → 로그인 상태 자동 전환.
    useEffect(() => {
        loadHoldings()
        if (onCanvas || typeof window === "undefined") return
        const onAuth = () => loadHoldings()
        window.addEventListener("verity_auth_change", onAuth)
        window.addEventListener("storage", onAuth)
        return () => {
            window.removeEventListener("verity_auth_change", onAuth)
            window.removeEventListener("storage", onAuth)
        }
    }, [loadHoldings])

    // 검색 유니버스(KR+US ~8.9천, universe_search) — 보유/거래 추가 패널 열 때 1회 lazy 로드.
    useEffect(() => {
        if (onCanvas || (!showAdd && !showTAdd) || universe.length) return
        let alive = true
        fetch(
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json",
            { cache: "no-store" }
        )
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const a = d && (Array.isArray(d) ? d : d.stocks)
                if (alive && Array.isArray(a)) setUniverse(a)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas, showAdd, showTAdd, universe.length])

    /* 평가 기준가 — kr_close_latest.json (금융위 공공데이터 직전 거래일 종가, 전 종목 동일 기준일).
       🚨 되돌리지 말 것 (2026-07-31 수익률 부호 역전 사고) — 옛 소스 = stock_flow_5d.json 의
       마지막 close. 그 파일은 시총순 회전 수집(하루 500종목)이라 **종목마다 종가 날짜가 제각각**
       (어제~5주 전). 실측: 1,801종목 중 71% 가 직전 거래일 종가와 불일치, 23% 는 10%+ 괴리
       → 하락 종목이 플러스로 표시됐다. flow_5d 로 되돌리면 같은 사고가 재발한다.
       커버리지 밖(미국·ETF·거래정지) = 값을 지어내지 않고 "시세 없음" 표기 + 손익 합계 제외. */
    useEffect(() => {
        if (onCanvas || isDemo) return
        let alive = true
        fetch(
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/kr_close_latest.json",
            { cache: "no-store" }
        )
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const pm = d && d.prices
                if (!alive || !pm || typeof pm !== "object") return
                const m: Record<string, number> = {}
                for (const tk of Object.keys(pm)) {
                    const c = Number(pm[tk])
                    if (c > 0 && isFinite(c)) m[tk] = c
                }
                setCloses(m)
                setCloseAsOf(String((d._meta && d._meta.as_of) || ""))
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [isDemo, onCanvas])

    const goStock = useCallback(
        (h: any) => {
            if (typeof window === "undefined") return
            const tk = String(h.ticker || "").trim()
            if (!tk) return
            const us = h.market === "us" || h.currency === "USD"
            const path = (
                us ? _usPath(usStockPath, stockPath) : stockPath || "/stock"
            ).replace(/\/+$/, "")
            window.location.href = path + "?q=" + encodeURIComponent(tk)
        },
        [stockPath, usStockPath]
    )

    // 검색 결과 — universe_search 필터 + 이미 보유 표시. 상위 8개.
    const matches = useMemo(() => {
        const s = q.trim().toLowerCase()
        if (!s || !universe.length) return []
        const rk = (x: any) => {
            const t = String(x.ticker || "").toLowerCase(),
                n = String(x.name || "").toLowerCase(),
                k = String(x.name_ko || "").toLowerCase()
            return t === s
                ? 0
                : n === s || k === s
                  ? 1
                  : t.indexOf(s) === 0
                    ? 2
                    : n.indexOf(s) === 0 || (k && k.indexOf(s) === 0)
                      ? 3
                      : 4
        }
        const held = new Set(rows.map((r: any) => String(r.ticker)))
        return universe
            .filter(
                (x: any) =>
                    String(x.ticker).toLowerCase().includes(s) ||
                    String(x.name || "")
                        .toLowerCase()
                        .includes(s) ||
                    String(x.name_ko || "").includes(q.trim())
            )
            .sort((a: any, b: any) => rk(a) - rk(b))
            .slice(0, 8)
            .map((x: any) => ({ ...x, _held: held.has(String(x.ticker)) }))
    }, [q, universe, rows])

    // ★ 클릭 = 추가 팝업(수량·평단 수동 입력) / 리스트 수정 = 기존값 프리필 팝업
    const openAdd = (x: any) => {
        setPop({
            ticker: String(x.ticker),
            name: x.name || "",
            market: String(x.market || "kr").toLowerCase(),
            shares: "",
            avg_cost: "",
        })
        setQ("")
    }
    const openEdit = (h: any) => {
        setPop({
            id: h.id,
            ticker: h.ticker,
            name: h.name || "",
            market: h.market || "kr",
            shares: String(h.shares ?? ""),
            avg_cost: String(h.avg_cost ?? ""),
        })
    }
    const savePop = useCallback(() => {
        const token = getToken()
        if (!token || !pop) return
        setBusy(true)
        const isEdit = !!pop.id
        const body = isEdit
            ? {
                  id: pop.id,
                  shares: Number(pop.shares) || 0,
                  avg_cost: Number(pop.avg_cost) || 0,
              }
            : {
                  ticker: String(pop.ticker).trim(),
                  name: String(pop.name).trim(),
                  market: pop.market,
                  shares: Number(pop.shares) || 0,
                  avg_cost: Number(pop.avg_cost) || 0,
              }
        fetch(base + "/api/holdings", {
            method: isEdit ? "PATCH" : "POST",
            headers: {
                Authorization: "Bearer " + token,
                "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
        })
            .then((r) => r.json().catch(() => ({})))
            .then(() => {
                setPop(null)
                loadHoldings()
            })
            .catch(() => {})
            .finally(() => setBusy(false))
    }, [pop, base, loadHoldings])

    const delHolding = useCallback(
        (id: string) => {
            const token = getToken()
            if (!token || !id) return
            fetch(base + "/api/holdings", {
                method: "DELETE",
                headers: {
                    Authorization: "Bearer " + token,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ id }),
            })
                .then(() => loadHoldings())
                .catch(() => {})
        },
        [base, loadHoldings]
    )

    // ── 거래 기록 로드 — 미로그인/캔버스 = 샘플. 서버가 이동평균 실현손익 요약(summary) 동봉. ──
    const loadTrades = useCallback(() => {
        if (onCanvas) return
        const token = getToken()
        if (!token) {
            // 미로그인 = 거래 기록도 SAMPLE 미리보기 유지 (loadHoldings 토큰 부재 분기와 동일 규율)
            setTradesLoading(false)
            setTradeData({
                trades: SAMPLE_TRADES,
                summary: SAMPLE_TRADE_SUMMARY,
            })
            return
        }
        setTradesLoading(true)
        fetch(base + "/api/trades", {
            headers: { Authorization: "Bearer " + token },
        })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (d && Array.isArray(d.trades))
                    setTradeData({
                        trades: d.trades,
                        summary: d.summary || {
                            by_ticker: [],
                            total_realized_pnl: 0,
                        },
                    })
            })
            .catch(() => {})
            .finally(() => setTradesLoading(false))
    }, [base, onCanvas])

    // 거래 탭 최초 진입 시 lazy 로드(안 여는 사용자 API 호출 절약).
    useEffect(() => {
        if (view === "trades") loadTrades()
    }, [view, loadTrades])

    // 거래 추가 검색 — universe_search 필터(보유 여부 표시 불필요). 상위 8개.
    const tMatches = useMemo(() => {
        const s = tq.trim().toLowerCase()
        if (!s || !universe.length) return []
        const rk = (x: any) => {
            const t = String(x.ticker || "").toLowerCase(),
                n = String(x.name || "").toLowerCase(),
                k = String(x.name_ko || "").toLowerCase()
            return t === s
                ? 0
                : n === s || k === s
                  ? 1
                  : t.indexOf(s) === 0
                    ? 2
                    : n.indexOf(s) === 0 || (k && k.indexOf(s) === 0)
                      ? 3
                      : 4
        }
        return universe
            .filter(
                (x: any) =>
                    String(x.ticker).toLowerCase().includes(s) ||
                    String(x.name || "")
                        .toLowerCase()
                        .includes(s) ||
                    String(x.name_ko || "").includes(tq.trim())
            )
            .sort((a: any, b: any) => rk(a) - rk(b))
            .slice(0, 8)
    }, [tq, universe])

    const openTAdd = (x: any) => {
        setTPop({
            ticker: String(x.ticker),
            name: x.name || "",
            market: String(x.market || "kr").toLowerCase(),
            side: "buy",
            shares: "",
            price: "",
            traded_at: todayISO(),
        })
        setTq("")
        setShowTAdd(false)
    }
    const openTEdit = (t: any) => {
        setTPop({
            id: t.id,
            ticker: t.ticker,
            name: t.name || "",
            market: t.market || "kr",
            side: t.side || "buy",
            shares: String(t.shares ?? ""),
            price: String(t.price ?? ""),
            traded_at: t.traded_at || todayISO(),
        })
    }
    const saveTPop = useCallback(() => {
        const token = getToken()
        if (!token || !tPop) return
        const sh = Number(tPop.shares) || 0
        const pr = Number(tPop.price)
        if (sh <= 0 || !isFinite(pr) || pr < 0) return
        setTBusy(true)
        const isEdit = !!tPop.id
        const body = isEdit
            ? {
                  id: tPop.id,
                  side: tPop.side,
                  shares: sh,
                  price: pr,
                  traded_at: tPop.traded_at,
              }
            : {
                  ticker: String(tPop.ticker).trim(),
                  name: String(tPop.name).trim(),
                  market: tPop.market,
                  side: tPop.side,
                  shares: sh,
                  price: pr,
                  traded_at: tPop.traded_at,
              }
        fetch(base + "/api/trades", {
            method: isEdit ? "PATCH" : "POST",
            headers: {
                Authorization: "Bearer " + token,
                "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
        })
            .then((r) => r.json().catch(() => ({})))
            .then(() => {
                setTPop(null)
                loadTrades()
            })
            .catch(() => {})
            .finally(() => setTBusy(false))
    }, [tPop, base, loadTrades])
    const delTrade = useCallback(
        (id: string) => {
            const token = getToken()
            if (!token || !id) return
            fetch(base + "/api/trades", {
                method: "DELETE",
                headers: {
                    Authorization: "Bearer " + token,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ id }),
            })
                .then(() => loadTrades())
                .catch(() => {})
        },
        [base, loadTrades]
    )

    const narrow = w > 0 && w < 560
    const pad = narrow ? 12 : 18

    /* 평가 — 기준가 없는 종목(미국·ETF·거래정지)은 0% 로 위장하지 않는다(_priced=false).
       옛 코드는 종가가 없으면 평단을 현재가로 써서 "정확히 0.0%" 를 표시했다 — 사용자가 손익 0
       으로 오독한다. 지금은 손익 "—" + 합계 제외, 평가금액만 매입가 기준으로 잡아 비중을 유지. */
    const evald = rows.map((h) => {
        const us = h.market === "us" || h.currency === "USD"
        const fx = us ? FX : 1
        const shares = Number(h.shares) || 0
        const px = Number(closes[String(h.ticker)]) || 0
        const seeded = Number(h.price) || 0 // SAMPLE 미리보기 전용 시세
        const cur = px > 0 ? px : seeded > 0 ? seeded : Number(h.avg_cost) || 0
        const priced = px > 0 || seeded > 0
        const val = shares * cur * fx
        const cost = shares * (Number(h.avg_cost) || 0) * fx
        const pl = priced ? val - cost : 0
        const plPct = priced && cost > 0 ? (pl / cost) * 100 : 0
        return {
            ...h,
            _us: us,
            _priced: priced,
            _val: val,
            _cost: cost,
            _pl: pl,
            _plPct: plPct,
        }
    })
    const totalVal = evald.reduce((a, b) => a + b._val, 0) // 비중용 — 미평가는 매입가 기준
    const pricedRows = evald.filter((h) => h._priced)
    const unpricedN = evald.length - pricedRows.length
    const totalCost = pricedRows.reduce((a, b) => a + b._cost, 0)
    const totalPl = pricedRows.reduce((a, b) => a + b._pl, 0)
    const totalPlPct = totalCost > 0 ? (totalPl / totalCost) * 100 : 0
    const withWeight = evald
        .map((h) => ({
            ...h,
            _weight: totalVal > 0 ? (h._val / totalVal) * 100 : 0,
        }))
        .sort((a, b) => b._val - a._val)
    const plColor = (v: number) => (v > 0 ? C.up : v < 0 ? C.down : C.faint)

    // ── 예상 세금 + 수수료 (매도 가정) ──
    const krRows = evald.filter((h) => !h._us)
    const usRows = evald.filter((h) => h._us)
    const krProceeds = krRows.reduce((a, b) => a + b._val, 0)
    const usProceeds = usRows.reduce((a, b) => a + b._val, 0)
    const krTxnTax = krProceeds * TAX.KR_TXN
    const usGainSum = usRows.reduce((a, b) => a + b._pl, 0)
    const usTaxable = Math.max(0, usGainSum - TAX.US_DEDUCT)
    const usCgt =
        usTaxable <= TAX.US_BRACKET
            ? usTaxable * TAX.US_CGT
            : TAX.US_BRACKET * TAX.US_CGT +
              (usTaxable - TAX.US_BRACKET) * TAX.US_CGT_HIGH
    const broker = brokers[brokerIdx] || null
    const krCommission = krProceeds * parseFee(broker && broker.domestic_fee)
    const usCommission = usProceeds * parseFee(broker && broker.overseas_fee)
    const totalTax = krTxnTax + usCgt
    const totalCommission = krCommission + usCommission
    const krMajorRows = krRows.filter((h) => h._val >= TAX.KR_MAJOR_AMT)

    // ── 분산(조합) 사실 계산 — 비중·집중도·목표갭 ──
    const krVal = krRows.reduce((a, b) => a + b._val, 0)
    const usVal = usRows.reduce((a, b) => a + b._val, 0)
    const krPct = totalVal > 0 ? (krVal / totalVal) * 100 : 0
    const usPct = totalVal > 0 ? (usVal / totalVal) * 100 : 0
    const byVal = [...evald].sort((a, b) => b._val - a._val)
    const topName = byVal[0] ? byVal[0].name || byVal[0].ticker : ""
    const topPct =
        totalVal > 0 && byVal[0] ? (byVal[0]._val / totalVal) * 100 : 0
    const top3Pct =
        totalVal > 0
            ? (byVal.slice(0, 3).reduce((a, b) => a + b._val, 0) / totalVal) *
              100
            : 0
    const concentrated = topPct >= 40 || top3Pct >= 70
    const tgtKr = targetKr == null ? Math.round(krPct) : targetKr
    const gapKr = Math.round(krPct - tgtKr)

    // ── 거래 기록(실현손익) 파생 — 종목별 실현손익은 네이티브 통화, 합계만 FX 환산(holdings 관행). ──
    const tByTicker: any[] =
        tradeData.summary && Array.isArray(tradeData.summary.by_ticker)
            ? tradeData.summary.by_ticker
            : []
    const realizedKrw = tByTicker.reduce(
        (a, b) =>
            a +
            (Number(b.realized_pnl) || 0) *
                (String(b.market) === "us" ? FX : 1),
        0
    )
    const tLedger = [...(tradeData.trades || [])].reverse() // 최신 거래 먼저
    const tHasUs = (tradeData.trades || []).some(
        (t: any) => String(t.market) === "us"
    )

    const inputStyle: CSSProperties = {
        border: `1px solid ${C.line}`,
        borderRadius: 8,
        padding: "8px 10px",
        fontSize: 13,
        fontFamily: FONT,
        background: C.bg,
        color: C.ink,
        outline: "none",
        minWidth: 0,
    }
    // 커스텀 chevron — OS 기본 화살표 제거(appearance none), 브랜드 드롭다운 룩. 색=테마 faint.
    // data URI 전체 encodeURIComponent + viewBox + backgroundSize/no-repeat 로 타일링 차단 — 부분인코딩/viewBox누락 시 Safari·Framer 퍼블리시에서 chevron 이 버튼 전체로 반복(지그재그)됨.
    const chevronUrl = `url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6' width='10' height='6'><path d='M1 1l4 4 4-4' stroke='${C.faint}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>`)}")`
    const selStyle: CSSProperties = {
        ...inputStyle,
        cursor: "pointer",
        paddingRight: 30,
        border: "none",
        appearance: "none",
        WebkitAppearance: "none",
        MozAppearance: "none",
        backgroundImage: chevronUrl,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 11px center",
        backgroundSize: "10px 6px",
    }
    const wrap: CSSProperties = {
        width: "100%",
        height: "100%",
        maxHeight: "100%",
        overflowY: "auto",
        overflowX: "hidden",
        background: C.bg,
        fontFamily: FONT,
        padding: `0 ${pad}px`,
        boxSizing: "border-box",
        color: C.ink,
    }
    const cardS: CSSProperties = {
        background: C.card,
        borderRadius: 16,
        padding: "16px 17px",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        marginTop: 12,
    }

    const shimmer: CSSProperties = {
        backgroundColor: C.shim,
        backgroundImage: `linear-gradient(90deg, ${C.shim} 25%, ${C.shimHi} 37%, ${C.shim} 63%)`,
        backgroundSize: "800px 100%",
        animation: "vhtShimmer 1.4s ease-in-out infinite",
    }
    const sk = (sw: number | string, sh: number, r: number): CSSProperties => ({
        width: sw,
        height: sh,
        borderRadius: r,
        ...shimmer,
    })
    const kv = (k: any, v: string, color?: string) => (
        <div
            style={{
                display: "flex",
                alignItems: "baseline",
                justifyContent: "space-between",
                padding: "6px 0",
                gap: 10,
            }}
        >
            <span style={{ fontSize: 12.5, color: C.sub, fontWeight: 600 }}>
                {k}
            </span>
            <span
                style={{
                    fontSize: 13.5,
                    fontWeight: 800,
                    color: color || C.ink,
                    fontVariantNumeric: "tabular-nums",
                }}
            >
                {v}
            </span>
        </div>
    )

    /* 통화 토글 — 미국 보유분을 원화로 환산해 본다. 국내는 원래 원화라 바뀌지 않는다.
       선택은 localStorage(an_ccy)에 남아 리포트 등 다른 화면과 함께 움직인다.
       🚨 2026-07-30: 이 정의가 빠진 채 렌더 참조만 들어가 "CcyToggle is not defined" 로
       둥지 페이지가 통째로 죽었다(PM 캔버스 에러). 정의와 참조를 항상 같이 옮길 것. */
    const CcyToggle = (
        <div
            style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginTop: 10,
                flexWrap: "wrap",
            }}
        >
            <div
                style={{
                    display: "inline-flex",
                    gap: 2,
                    background: C.bg,
                    borderRadius: 9,
                    padding: 2,
                }}
            >
                {["USD", "KRW"].map((k) => (
                    <div
                        key={k}
                        onClick={() => setCcy(k)}
                        style={{
                            cursor: "pointer",
                            fontSize: 11.5,
                            fontWeight: 800,
                            padding: "4px 12px",
                            borderRadius: 7,
                            background: ccy === k ? C.card : "transparent",
                            color: ccy === k ? C.ink : C.faint,
                        }}
                    >
                        {k === "USD" ? "$ 달러" : "₩ 원화"}
                    </div>
                ))}
            </div>
            <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>
                미국 종목 표기 · 환율 {Math.round(FX).toLocaleString()}원/$
                {fxInfo.ok
                    ? fxInfo.asOf
                        ? " (" +
                          String(fxInfo.asOf).slice(5, 16).replace("T", " ") +
                          " 기준)"
                        : ""
                    : " (기본값 — 환율 불러오는 중)"}
            </span>
        </div>
    )

    const Tabs = (
        <div
            style={{
                display: "flex",
                gap: 4,
                background: C.bg,
                borderRadius: 11,
                padding: 3,
                marginTop: 12,
            }}
        >
            {(
                [
                    ["holdings", "보유종목"],
                    ["mix", "분산"],
                    ["trades", "거래 기록"],
                    ["tax", "예상 세금"],
                ] as const
            ).map(([k, label]) => (
                <div
                    key={k}
                    onClick={() => setView(k)}
                    style={{
                        flex: 1,
                        textAlign: "center",
                        cursor: "pointer",
                        fontSize: 13,
                        fontWeight: 800,
                        padding: "8px 0",
                        borderRadius: 8,
                        background: view === k ? C.card : "transparent",
                        color: view === k ? C.ink : C.faint,
                        boxShadow:
                            view === k ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
                    }}
                >
                    {label}
                </div>
            ))}
        </div>
    )

    return (
        <div ref={rootRef} style={wrap}>
            <style>{AN_PALETTE}</style>
            {/* 추가/수정 팝업 — ★(추가) 또는 행 '수정' 클릭 시. 수량·평단 수동 입력 → POST(신규)/PATCH(수정). */}
            {pop && (
                <div
                    onClick={() => setPop(null)}
                    style={{
                        position: "fixed",
                        inset: 0,
                        zIndex: 100,
                        background: "rgba(0,0,0,0.42)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: 16,
                    }}
                >
                    <div
                        onClick={(e) => e.stopPropagation()}
                        style={{
                            width: "100%",
                            maxWidth: 320,
                            background: C.card,
                            borderRadius: 18,
                            padding: "18px 18px 16px",
                            boxShadow: "0 14px 44px rgba(0,0,0,0.28)",
                            fontFamily: FONT,
                            boxSizing: "border-box",
                        }}
                    >
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 10,
                                marginBottom: 14,
                            }}
                        >
                            <Logo
                                ticker={pop.ticker}
                                name={pop.name}
                                market={pop.market}
                                C={C}
                                size={34}
                            />
                            <div style={{ minWidth: 0 }}>
                                <div
                                    style={{
                                        fontSize: 15,
                                        fontWeight: 800,
                                        color: C.ink,
                                        whiteSpace: "nowrap",
                                        overflow: "hidden",
                                        textOverflow: "ellipsis",
                                    }}
                                >
                                    {pop.name || pop.ticker}
                                </div>
                                <div
                                    style={{
                                        fontSize: 11.5,
                                        color: C.faint,
                                        fontWeight: 600,
                                    }}
                                >
                                    {pop.ticker} ·{" "}
                                    {String(pop.market).toUpperCase()} ·{" "}
                                    {pop.id ? "수정" : "추가"}
                                </div>
                            </div>
                        </div>
                        <div
                            style={{
                                display: "flex",
                                flexDirection: "column",
                                gap: 9,
                            }}
                        >
                            <div>
                                <div
                                    style={{
                                        fontSize: 11.5,
                                        fontWeight: 700,
                                        color: C.sub,
                                        marginBottom: 4,
                                    }}
                                >
                                    수량
                                </div>
                                <input
                                    autoFocus
                                    style={{
                                        ...inputStyle,
                                        width: "100%",
                                        boxSizing: "border-box",
                                    }}
                                    inputMode="decimal"
                                    placeholder="예: 10"
                                    value={pop.shares}
                                    onChange={(e) =>
                                        setPop({
                                            ...pop,
                                            shares: e.target.value,
                                        })
                                    }
                                />
                            </div>
                            <div>
                                <div
                                    style={{
                                        fontSize: 11.5,
                                        fontWeight: 700,
                                        color: C.sub,
                                        marginBottom: 4,
                                    }}
                                >
                                    평단 (평균 매입가)
                                </div>
                                <input
                                    style={{
                                        ...inputStyle,
                                        width: "100%",
                                        boxSizing: "border-box",
                                    }}
                                    inputMode="decimal"
                                    placeholder={
                                        pop.market === "us"
                                            ? "예: 150 ($)"
                                            : "예: 68000 (원)"
                                    }
                                    value={pop.avg_cost}
                                    onChange={(e) =>
                                        setPop({
                                            ...pop,
                                            avg_cost: e.target.value,
                                        })
                                    }
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") savePop()
                                    }}
                                />
                            </div>
                        </div>
                        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                            <button
                                onClick={() => setPop(null)}
                                style={{
                                    flex: 1,
                                    border: `1px solid ${C.line}`,
                                    background: "transparent",
                                    cursor: "pointer",
                                    color: C.sub,
                                    borderRadius: 10,
                                    padding: "10px 0",
                                    fontSize: 13,
                                    fontWeight: 700,
                                    fontFamily: FONT,
                                }}
                            >
                                취소
                            </button>
                            <button
                                onClick={savePop}
                                disabled={busy}
                                style={{
                                    flex: 2,
                                    border: "none",
                                    cursor: "pointer",
                                    background: C.vg,
                                    color: C.onAccent,
                                    borderRadius: 10,
                                    padding: "10px 0",
                                    fontSize: 13.5,
                                    fontWeight: 800,
                                    fontFamily: FONT,
                                    opacity: busy ? 0.6 : 1,
                                }}
                            >
                                {busy ? "저장 중…" : pop.id ? "저장" : "추가"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
            {/* 거래 기록 팝업 — 매수/매도 · 수량 · 체결가 · 거래일 → POST/PATCH /api/trades. 실현손익 서버 이동평균 재계산. */}
            {tPop && (
                <div
                    onClick={() => setTPop(null)}
                    style={{
                        position: "fixed",
                        inset: 0,
                        zIndex: 100,
                        background: "rgba(0,0,0,0.42)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: 16,
                    }}
                >
                    <div
                        onClick={(e) => e.stopPropagation()}
                        style={{
                            width: "100%",
                            maxWidth: 320,
                            background: C.card,
                            borderRadius: 18,
                            padding: "18px 18px 16px",
                            boxShadow: "0 14px 44px rgba(0,0,0,0.28)",
                            fontFamily: FONT,
                            boxSizing: "border-box",
                        }}
                    >
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 10,
                                marginBottom: 14,
                            }}
                        >
                            <Logo
                                ticker={tPop.ticker}
                                name={tPop.name}
                                market={tPop.market}
                                C={C}
                                size={34}
                            />
                            <div style={{ minWidth: 0 }}>
                                <div
                                    style={{
                                        fontSize: 15,
                                        fontWeight: 800,
                                        color: C.ink,
                                        whiteSpace: "nowrap",
                                        overflow: "hidden",
                                        textOverflow: "ellipsis",
                                    }}
                                >
                                    {tPop.name || tPop.ticker}
                                </div>
                                <div
                                    style={{
                                        fontSize: 11.5,
                                        color: C.faint,
                                        fontWeight: 600,
                                    }}
                                >
                                    {tPop.ticker} ·{" "}
                                    {String(tPop.market).toUpperCase()} ·{" "}
                                    {tPop.id ? "거래 수정" : "거래 기록"}
                                </div>
                            </div>
                        </div>
                        <div
                            style={{
                                display: "flex",
                                gap: 6,
                                marginBottom: 11,
                            }}
                        >
                            {(["buy", "sell"] as const).map((sd) => (
                                <div
                                    key={sd}
                                    onClick={() =>
                                        setTPop({ ...tPop, side: sd })
                                    }
                                    style={{
                                        flex: 1,
                                        textAlign: "center",
                                        cursor: "pointer",
                                        fontSize: 13,
                                        fontWeight: 800,
                                        padding: "9px 0",
                                        borderRadius: 10,
                                        border: `1px solid ${tPop.side === sd ? (sd === "buy" ? C.down : C.up) : C.line}`,
                                        color:
                                            tPop.side === sd
                                                ? sd === "buy"
                                                    ? C.down
                                                    : C.up
                                                : C.faint,
                                        background:
                                            tPop.side === sd
                                                ? sd === "buy"
                                                    ? C.buyS
                                                    : C.sellS
                                                : "transparent",
                                    }}
                                >
                                    {sd === "buy" ? "매수" : "매도"}
                                </div>
                            ))}
                        </div>
                        <div
                            style={{
                                display: "flex",
                                flexDirection: "column",
                                gap: 9,
                            }}
                        >
                            <div>
                                <div
                                    style={{
                                        fontSize: 11.5,
                                        fontWeight: 700,
                                        color: C.sub,
                                        marginBottom: 4,
                                    }}
                                >
                                    수량
                                </div>
                                <input
                                    autoFocus
                                    style={{
                                        ...inputStyle,
                                        width: "100%",
                                        boxSizing: "border-box",
                                    }}
                                    inputMode="decimal"
                                    placeholder="예: 10"
                                    value={tPop.shares}
                                    onChange={(e) =>
                                        setTPop({
                                            ...tPop,
                                            shares: e.target.value,
                                        })
                                    }
                                />
                            </div>
                            <div>
                                <div
                                    style={{
                                        fontSize: 11.5,
                                        fontWeight: 700,
                                        color: C.sub,
                                        marginBottom: 4,
                                    }}
                                >
                                    체결가 ({tPop.market === "us" ? "$" : "원"})
                                </div>
                                <input
                                    style={{
                                        ...inputStyle,
                                        width: "100%",
                                        boxSizing: "border-box",
                                    }}
                                    inputMode="decimal"
                                    placeholder={
                                        tPop.market === "us"
                                            ? "예: 150"
                                            : "예: 68000"
                                    }
                                    value={tPop.price}
                                    onChange={(e) =>
                                        setTPop({
                                            ...tPop,
                                            price: e.target.value,
                                        })
                                    }
                                />
                            </div>
                            <div>
                                <div
                                    style={{
                                        fontSize: 11.5,
                                        fontWeight: 700,
                                        color: C.sub,
                                        marginBottom: 4,
                                    }}
                                >
                                    거래일
                                </div>
                                <input
                                    type="date"
                                    style={{
                                        ...inputStyle,
                                        width: "100%",
                                        boxSizing: "border-box",
                                    }}
                                    value={tPop.traded_at}
                                    onChange={(e) =>
                                        setTPop({
                                            ...tPop,
                                            traded_at: e.target.value,
                                        })
                                    }
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") saveTPop()
                                    }}
                                />
                            </div>
                        </div>
                        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                            <button
                                onClick={() => setTPop(null)}
                                style={{
                                    flex: 1,
                                    border: `1px solid ${C.line}`,
                                    background: "transparent",
                                    cursor: "pointer",
                                    color: C.sub,
                                    borderRadius: 10,
                                    padding: "10px 0",
                                    fontSize: 13,
                                    fontWeight: 700,
                                    fontFamily: FONT,
                                }}
                            >
                                취소
                            </button>
                            <button
                                onClick={saveTPop}
                                disabled={tBusy}
                                style={{
                                    flex: 2,
                                    border: "none",
                                    cursor: "pointer",
                                    background:
                                        tPop.side === "sell" ? C.up : C.vg,
                                    color: C.onAccent,
                                    borderRadius: 10,
                                    padding: "10px 0",
                                    fontSize: 13.5,
                                    fontWeight: 800,
                                    fontFamily: FONT,
                                    opacity: tBusy ? 0.6 : 1,
                                }}
                            >
                                {tBusy
                                    ? "저장 중…"
                                    : tPop.id
                                      ? "저장"
                                      : tPop.side === "sell"
                                        ? "매도 기록"
                                        : "매수 기록"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
            <div
                style={{
                    display: "flex",
                    alignItems: "flex-start",
                    justifyContent: "space-between",
                    gap: 10,
                    flexWrap: "wrap",
                }}
            >
                <div style={{ minWidth: 0 }}>
                    <div
                        style={{
                            fontSize: narrow ? 18 : 20,
                            fontWeight: 800,
                            letterSpacing: "-0.5px",
                        }}
                    >
                        나만의 둥지
                    </div>
                    <div
                        style={{
                            fontSize: 12,
                            color: C.faint,
                            fontWeight: 600,
                            marginTop: 3,
                        }}
                    >
                        평단 입력 기준
                    </div>
                </div>
                {!loading && !isDemo && view === "holdings" && (
                    <button
                        onClick={() => setShowAdd((v) => !v)}
                        style={{
                            border: "none",
                            cursor: "pointer",
                            padding: "7px 14px",
                            borderRadius: 999,
                            fontSize: 13,
                            fontWeight: 700,
                            fontFamily: FONT,
                            flexShrink: 0,
                            background: C.vg,
                            color: C.onAccent,
                        }}
                    >
                        {showAdd ? "닫기" : "+ 종목 추가"}
                    </button>
                )}
                {!loading && !isDemo && view === "trades" && (
                    <button
                        onClick={() => setShowTAdd((v) => !v)}
                        style={{
                            border: "none",
                            cursor: "pointer",
                            padding: "7px 14px",
                            borderRadius: 999,
                            fontSize: 13,
                            fontWeight: 700,
                            fontFamily: FONT,
                            flexShrink: 0,
                            background: C.vg,
                            color: C.onAccent,
                        }}
                    >
                        {showTAdd ? "닫기" : "+ 거래 추가"}
                    </button>
                )}
            </div>

            {loading ? (
                <>
                    <style>
                        {
                            "@keyframes vhtShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}"
                        }
                    </style>
                    <div style={cardS}>
                        <div style={sk(80, 12, 6)} />
                        <div style={{ ...sk(170, 27, 7), margin: "9px 0" }} />
                        <div style={sk(120, 14, 6)} />
                    </div>
                    <div
                        style={{
                            display: "flex",
                            flexDirection: "column",
                            gap: 8,
                            marginTop: 12,
                        }}
                    >
                        {[0, 1, 2, 3, 4].map((k) => (
                            <div
                                key={k}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 12,
                                    background: C.card,
                                    borderRadius: 16,
                                    padding: "13px 15px",
                                    boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                                }}
                            >
                                <div
                                    style={{ ...sk(36, 36, 10), flexShrink: 0 }}
                                />
                                <div style={{ minWidth: 0, flex: 1 }}>
                                    <div style={sk("58%", 14, 6)} />
                                    <div
                                        style={{
                                            ...sk("40%", 11, 5),
                                            marginTop: 7,
                                        }}
                                    />
                                </div>
                                <div
                                    style={{
                                        textAlign: "right",
                                        flexShrink: 0,
                                    }}
                                >
                                    <div style={sk(52, 14, 6)} />
                                    <div
                                        style={{
                                            ...sk(72, 11, 5),
                                            marginTop: 7,
                                        }}
                                    />
                                </div>
                            </div>
                        ))}
                    </div>
                </>
            ) : (
                <>
                    {isDemo && (
                        <div
                            style={{
                                background: C.vgS,
                                color: C.ink,
                                borderRadius: 16,
                                padding: narrow ? "16px 15px" : "20px 18px",
                                marginTop: 12,
                            }}
                        >
                            <div
                                style={{
                                    fontSize: narrow ? 15 : 16,
                                    fontWeight: 800,
                                    letterSpacing: "-0.3px",
                                }}
                            >
                                로그인하고 나만의 둥지 관리하기
                            </div>
                            <div
                                style={{
                                    fontSize: 13,
                                    color: C.sub,
                                    fontWeight: 600,
                                    lineHeight: 1.6,
                                    marginTop: 7,
                                }}
                            >
                                종목·수량·평단만 입력하면 평가손익·예상 세금을
                                한눈에. 기기·세션이 바뀌어도 그대로 유지돼요.
                            </div>
                            {loginUrl && (
                                <a
                                    href={loginUrl}
                                    style={{
                                        display: "inline-block",
                                        marginTop: 14,
                                        background: C.vg,
                                        color: C.onAccent,
                                        borderRadius: 10,
                                        padding: "11px 20px",
                                        fontSize: 14,
                                        fontWeight: 800,
                                        textDecoration: "none",
                                    }}
                                >
                                    로그인하고 시작하기
                                </a>
                            )}
                        </div>
                    )}

                    {(onCanvas || !isDemo) && CcyToggle}
                    {(onCanvas || !isDemo) && Tabs}

                    {(() => {
                        const content =
                            view === "holdings" ? (
                                <>
                                    {!isDemo && showAdd && (
                                        <div
                                            style={{
                                                background: C.card,
                                                borderRadius: 16,
                                                padding: "14px 15px",
                                                boxShadow:
                                                    "0 1px 3px rgba(0,0,0,0.04)",
                                                marginTop: 12,
                                            }}
                                        >
                                            <input
                                                style={{
                                                    ...inputStyle,
                                                    width: "100%",
                                                    boxSizing: "border-box",
                                                }}
                                                placeholder="종목 검색 (이름·코드)"
                                                value={q}
                                                onChange={(e) =>
                                                    setQ(e.target.value)
                                                }
                                            />
                                            {q.trim() && matches.length > 0 && (
                                                <div
                                                    style={{
                                                        marginTop: 8,
                                                        display: "flex",
                                                        flexDirection: "column",
                                                        gap: 2,
                                                    }}
                                                >
                                                    {matches.map((m: any) => (
                                                        <div
                                                            key={m.ticker}
                                                            style={{
                                                                display: "flex",
                                                                alignItems:
                                                                    "center",
                                                                gap: 10,
                                                                padding:
                                                                    "8px 6px",
                                                                borderRadius: 10,
                                                            }}
                                                        >
                                                            <Logo
                                                                ticker={
                                                                    m.ticker
                                                                }
                                                                name={m.name}
                                                                market={String(
                                                                    m.market
                                                                ).toLowerCase()}
                                                                C={C}
                                                                size={26}
                                                            />
                                                            <div
                                                                style={{
                                                                    minWidth: 0,
                                                                    flex: 1,
                                                                }}
                                                            >
                                                                <div
                                                                    style={{
                                                                        fontSize: 13.5,
                                                                        fontWeight: 700,
                                                                        color: C.ink,
                                                                        whiteSpace:
                                                                            "nowrap",
                                                                        overflow:
                                                                            "hidden",
                                                                        textOverflow:
                                                                            "ellipsis",
                                                                    }}
                                                                >
                                                                    {m.name ||
                                                                        m.ticker}
                                                                </div>
                                                                <div
                                                                    style={{
                                                                        fontSize: 11,
                                                                        color: C.faint,
                                                                        fontWeight: 600,
                                                                    }}
                                                                >
                                                                    {m.ticker} ·{" "}
                                                                    {String(
                                                                        m.market
                                                                    ).toUpperCase()}
                                                                </div>
                                                            </div>
                                                            {m._held ? (
                                                                <span
                                                                    style={{
                                                                        fontSize: 11,
                                                                        fontWeight: 700,
                                                                        color: C.faint,
                                                                        flexShrink: 0,
                                                                        paddingRight: 4,
                                                                    }}
                                                                >
                                                                    보유중
                                                                </span>
                                                            ) : (
                                                                <button
                                                                    onClick={() =>
                                                                        openAdd(
                                                                            m
                                                                        )
                                                                    }
                                                                    title="보유종목 추가"
                                                                    style={{
                                                                        border: "none",
                                                                        background:
                                                                            C.vgS,
                                                                        cursor: "pointer",
                                                                        color: C.vg,
                                                                        borderRadius: 999,
                                                                        width: 30,
                                                                        height: 30,
                                                                        fontSize: 15,
                                                                        fontWeight: 800,
                                                                        flexShrink: 0,
                                                                        display:
                                                                            "inline-flex",
                                                                        alignItems:
                                                                            "center",
                                                                        justifyContent:
                                                                            "center",
                                                                    }}
                                                                >
                                                                    ★
                                                                </button>
                                                            )}
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                            {q.trim() &&
                                                matches.length === 0 && (
                                                    <div
                                                        style={{
                                                            fontSize: 12,
                                                            color: C.faint,
                                                            fontWeight: 600,
                                                            padding: "8px 4px",
                                                        }}
                                                    >
                                                        {universe.length
                                                            ? "검색 결과 없음"
                                                            : "불러오는 중…"}
                                                    </div>
                                                )}
                                            {!q.trim() && (
                                                <div
                                                    style={{
                                                        fontSize: 11.5,
                                                        color: C.faint,
                                                        fontWeight: 600,
                                                        padding: "8px 4px 2px",
                                                        lineHeight: 1.5,
                                                    }}
                                                >
                                                    종목을 검색해 ★ 를 누르면
                                                    수량·평단 입력 후 바로
                                                    추가돼요.
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    <div
                                        style={{
                                            ...cardS,
                                            padding: "18px 18px",
                                        }}
                                    >
                                        <div
                                            style={{
                                                fontSize: 12,
                                                color: C.faint,
                                                fontWeight: 700,
                                            }}
                                        >
                                            총 평가금액
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 27,
                                                fontWeight: 800,
                                                letterSpacing: "-1px",
                                                margin: "3px 0",
                                            }}
                                        >
                                            {money(totalVal)}
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 14,
                                                fontWeight: 800,
                                                color: plColor(totalPl),
                                            }}
                                        >
                                            {(totalPl > 0 ? "+" : "") +
                                                money(totalPl)}{" "}
                                            ·{" "}
                                            {(totalPlPct > 0 ? "+" : "") +
                                                totalPlPct.toFixed(1)}
                                            %
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 12,
                                                color: C.faint,
                                                fontWeight: 600,
                                                marginTop: 6,
                                            }}
                                        >
                                            보유 {rows.length}종목 · 평단 입력
                                            기준(사실)
                                            {closeAsOf
                                                ? ` · ${fmtAsOf(closeAsOf)} 종가 기준`
                                                : ""}
                                            {unpricedN
                                                ? ` · 시세 없는 ${unpricedN}종목 손익 제외`
                                                : ""}
                                            {usRows.length
                                                ? ` · 미국주식 환율 ${Math.round(FX).toLocaleString()}원/$${fxInfo.ok ? "" : " (기본값)"}`
                                                : ""}
                                        </div>
                                    </div>

                                    <div
                                        style={{
                                            display: "flex",
                                            flexDirection: "column",
                                            gap: 8,
                                            marginTop: 12,
                                        }}
                                    >
                                        {withWeight.map((h) => (
                                            <div
                                                key={h.id || h.ticker}
                                                onClick={() => goStock(h)}
                                                role="link"
                                                tabIndex={0}
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: 12,
                                                    background: C.card,
                                                    borderRadius: 16,
                                                    padding: "13px 15px",
                                                    boxShadow:
                                                        "0 1px 3px rgba(0,0,0,0.04)",
                                                    cursor: "pointer",
                                                }}
                                            >
                                                <Logo
                                                    ticker={h.ticker}
                                                    name={h.name}
                                                    market={h.market}
                                                    C={C}
                                                    size={36}
                                                />
                                                <div
                                                    style={{
                                                        minWidth: 0,
                                                        flex: narrow
                                                            ? "1"
                                                            : "0 0 auto",
                                                        width: narrow
                                                            ? "auto"
                                                            : 150,
                                                    }}
                                                >
                                                    <div
                                                        style={{
                                                            fontSize: 14.5,
                                                            fontWeight: 700,
                                                            whiteSpace:
                                                                "nowrap",
                                                            overflow: "hidden",
                                                            textOverflow:
                                                                "ellipsis",
                                                        }}
                                                    >
                                                        {h.name || h.ticker}
                                                    </div>
                                                    <div
                                                        style={{
                                                            fontSize: 11.5,
                                                            color: C.faint,
                                                            fontWeight: 600,
                                                            marginTop: 2,
                                                        }}
                                                    >
                                                        {h.ticker} ·{" "}
                                                        {Number(h.shares) || 0}
                                                        주 · 비중{" "}
                                                        {h._weight.toFixed(0)}%
                                                    </div>
                                                </div>
                                                {!narrow && (
                                                    <div
                                                        style={{
                                                            flex: 1,
                                                            minWidth: 50,
                                                        }}
                                                    >
                                                        <div
                                                            style={{
                                                                height: 6,
                                                                borderRadius: 3,
                                                                background:
                                                                    C.line,
                                                                overflow:
                                                                    "hidden",
                                                            }}
                                                        >
                                                            <div
                                                                style={{
                                                                    width:
                                                                        Math.min(
                                                                            100,
                                                                            h._weight
                                                                        ) + "%",
                                                                    height: "100%",
                                                                    background:
                                                                        C.vg,
                                                                }}
                                                            />
                                                        </div>
                                                    </div>
                                                )}
                                                <div
                                                    style={{
                                                        textAlign: "right",
                                                        marginLeft: "auto",
                                                        flexShrink: 0,
                                                    }}
                                                >
                                                    <div
                                                        style={{
                                                            fontSize: 14.5,
                                                            fontWeight: 800,
                                                            color: h._priced
                                                                ? plColor(h._pl)
                                                                : C.faint,
                                                        }}
                                                    >
                                                        {h._priced
                                                            ? (h._plPct > 0
                                                                  ? "+"
                                                                  : "") +
                                                              h._plPct.toFixed(
                                                                  1
                                                              ) +
                                                              "%"
                                                            : "—"}
                                                    </div>
                                                    <div
                                                        style={{
                                                            fontSize: 11.5,
                                                            color: C.faint,
                                                            fontWeight: 600,
                                                            marginTop: 2,
                                                        }}
                                                    >
                                                        {h._priced
                                                            ? money(h._val)
                                                            : "시세 없음"}
                                                    </div>
                                                </div>
                                                <span
                                                    style={{
                                                        flexShrink: 0,
                                                        fontSize: 16,
                                                        color: C.faint,
                                                        fontWeight: 700,
                                                        lineHeight: 1,
                                                    }}
                                                >
                                                    ›
                                                </span>
                                                {!isDemo && h.id && (
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            openEdit(h)
                                                        }}
                                                        title="수량·평단 수정"
                                                        style={{
                                                            border: "none",
                                                            background:
                                                                "transparent",
                                                            cursor: "pointer",
                                                            color: C.faint,
                                                            fontSize: 12,
                                                            fontWeight: 700,
                                                            padding: "0 2px",
                                                            flexShrink: 0,
                                                        }}
                                                    >
                                                        수정
                                                    </button>
                                                )}
                                                {!isDemo && h.id && (
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            delHolding(h.id)
                                                        }}
                                                        title="삭제"
                                                        style={{
                                                            border: "none",
                                                            background:
                                                                "transparent",
                                                            cursor: "pointer",
                                                            color: C.faint,
                                                            fontSize: 16,
                                                            fontWeight: 700,
                                                            padding: "0 2px",
                                                            flexShrink: 0,
                                                        }}
                                                    >
                                                        ×
                                                    </button>
                                                )}
                                            </div>
                                        ))}
                                    </div>

                                    <div
                                        style={{
                                            textAlign: "center",
                                            fontSize: 11,
                                            color: C.faint,
                                            fontWeight: 600,
                                            marginTop: 14,
                                            lineHeight: 1.5,
                                        }}
                                    >
                                        종목 누르면 상세 리포트 · 평가손익 ={" "}
                                        {closeAsOf
                                            ? `${fmtAsOf(closeAsOf)} 종가`
                                            : "직전 거래일 종가"}{" "}
                                        × 보유수량 − 입력 평단 (단순 계산·사실) ·
                                        종가 = 금융위 공공데이터(T+1) · 실시간
                                        시세는 리포트에서
                                    </div>
                                </>
                            ) : view === "mix" ? (
                                <>
                                    {/* 자산 구성 (사실) — 지역 비중 + 집중도 */}
                                    <div
                                        style={{
                                            ...cardS,
                                            padding: "18px 18px",
                                        }}
                                    >
                                        <div
                                            style={{
                                                fontSize: 12,
                                                color: C.faint,
                                                fontWeight: 700,
                                                marginBottom: 12,
                                            }}
                                        >
                                            자산 구성 · 사실(평가금액 기준)
                                        </div>
                                        <div
                                            style={{
                                                display: "flex",
                                                height: 12,
                                                borderRadius: 6,
                                                overflow: "hidden",
                                                background: C.bg,
                                                marginBottom: 9,
                                            }}
                                        >
                                            {krPct > 0 ? (
                                                <div
                                                    style={{
                                                        width: krPct + "%",
                                                        background: C.vg,
                                                    }}
                                                />
                                            ) : null}
                                            {usPct > 0 ? (
                                                <div
                                                    style={{
                                                        width: usPct + "%",
                                                        background: C.warn,
                                                    }}
                                                />
                                            ) : null}
                                        </div>
                                        <div
                                            style={{
                                                display: "flex",
                                                gap: 16,
                                                flexWrap: "wrap",
                                                fontSize: 12.5,
                                                fontWeight: 800,
                                            }}
                                        >
                                            <span style={{ color: C.vg }}>
                                                국내 {krPct.toFixed(0)}%{" "}
                                                <span
                                                    style={{
                                                        color: C.faint,
                                                        fontWeight: 600,
                                                    }}
                                                >
                                                    {wonCompact(krVal)}
                                                </span>
                                            </span>
                                            <span style={{ color: C.warn }}>
                                                해외 {usPct.toFixed(0)}%{" "}
                                                <span
                                                    style={{
                                                        color: C.faint,
                                                        fontWeight: 600,
                                                    }}
                                                >
                                                    {wonCompact(usVal)}
                                                </span>
                                            </span>
                                        </div>
                                        <div
                                            style={{
                                                borderTop: `1px solid ${C.line}`,
                                                marginTop: 12,
                                                paddingTop: 8,
                                            }}
                                        >
                                            {kv(
                                                "보유 종목 수",
                                                rows.length + "종목"
                                            )}
                                            {topName
                                                ? kv(
                                                      "최대 비중",
                                                      topName +
                                                          " " +
                                                          topPct.toFixed(0) +
                                                          "%"
                                                  )
                                                : null}
                                            {kv(
                                                "상위 3 비중",
                                                top3Pct.toFixed(0) + "%"
                                            )}
                                            {concentrated && (
                                                <div
                                                    style={{
                                                        background: C.warnS,
                                                        color: C.warn,
                                                        borderRadius: 10,
                                                        padding: "9px 11px",
                                                        fontSize: 11.5,
                                                        fontWeight: 700,
                                                        lineHeight: 1.5,
                                                        marginTop: 8,
                                                    }}
                                                >
                                                    집중 — 최대 비중{" "}
                                                    {topPct.toFixed(0)}%
                                                    {top3Pct >= 70
                                                        ? ` · 상위3 ${top3Pct.toFixed(0)}%`
                                                        : ""}
                                                    . 분산 여부는 본인 판단(사실
                                                    표시일 뿐).
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {/* 목표 갭 (사용자 설정) */}
                                    <div style={cardS}>
                                        <div
                                            style={{
                                                display: "flex",
                                                alignItems: "baseline",
                                                justifyContent: "space-between",
                                                flexWrap: "wrap",
                                                gap: 8,
                                                marginBottom: 6,
                                            }}
                                        >
                                            <span
                                                style={{
                                                    fontSize: 12,
                                                    color: C.faint,
                                                    fontWeight: 700,
                                                }}
                                            >
                                                내 목표 비중 · 직접 설정
                                            </span>
                                            <span
                                                style={{
                                                    fontSize: 11.5,
                                                    color: C.sub,
                                                    fontWeight: 700,
                                                }}
                                            >
                                                국내 {tgtKr}% · 해외{" "}
                                                {100 - tgtKr}%
                                            </span>
                                        </div>
                                        <input
                                            type="range"
                                            min={0}
                                            max={100}
                                            step={5}
                                            value={tgtKr}
                                            onChange={(e) =>
                                                setTargetKr(
                                                    Number(e.target.value)
                                                )
                                            }
                                            style={{
                                                width: "100%",
                                                accentColor: C.vg,
                                                cursor: "pointer",
                                            }}
                                        />
                                        <div
                                            style={{
                                                borderTop: `1px solid ${C.line}`,
                                                marginTop: 8,
                                                paddingTop: 8,
                                            }}
                                        >
                                            {kv(
                                                "국내 현재 → 목표",
                                                krPct.toFixed(0) +
                                                    "% → " +
                                                    tgtKr +
                                                    "%",
                                                Math.abs(gapKr) < 5
                                                    ? C.faint
                                                    : C.ink
                                            )}
                                            <div
                                                style={{
                                                    textAlign: "right",
                                                    fontSize: 11.5,
                                                    fontWeight: 800,
                                                    color:
                                                        Math.abs(gapKr) < 5
                                                            ? C.faint
                                                            : C.warn,
                                                }}
                                            >
                                                {gapKr === 0
                                                    ? "목표 일치"
                                                    : `갭 국내 ${gapKr > 0 ? "+" : ""}${gapKr}%p`}
                                            </div>
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 11,
                                                color: C.faint,
                                                fontWeight: 600,
                                                marginTop: 6,
                                                lineHeight: 1.5,
                                            }}
                                        >
                                            목표는 직접 설정한 값 · 추천·권유
                                            아님. 슬라이더로 조정하세요.
                                        </div>
                                    </div>

                                    {/* 보유 자산군 ETF 자금 (etf_flow, 참고 사실) */}
                                    {(krVal > 0 || usVal > 0) &&
                                    (catFlow.equity_domestic != null ||
                                        catFlow.equity_foreign != null) ? (
                                        <div style={cardS}>
                                            <div
                                                style={{
                                                    fontSize: 12,
                                                    color: C.faint,
                                                    fontWeight: 700,
                                                    marginBottom: 8,
                                                }}
                                            >
                                                보유 자산군 ETF 자금 · 최근
                                                20거래일 (KRX 사실)
                                            </div>
                                            {krVal > 0 &&
                                            catFlow.equity_domestic != null ? (
                                                <div
                                                    style={{
                                                        display: "flex",
                                                        alignItems: "center",
                                                        justifyContent:
                                                            "space-between",
                                                        padding: "8px 0",
                                                        gap: 10,
                                                    }}
                                                >
                                                    <span
                                                        style={{
                                                            fontSize: 13,
                                                            fontWeight: 700,
                                                        }}
                                                    >
                                                        국내주식 ETF
                                                    </span>
                                                    <span
                                                        style={{
                                                            fontSize: 13.5,
                                                            fontWeight: 800,
                                                            color:
                                                                catFlow.equity_domestic >
                                                                0
                                                                    ? C.up
                                                                    : C.down,
                                                            fontVariantNumeric:
                                                                "tabular-nums",
                                                        }}
                                                    >
                                                        {catFlow.equity_domestic >
                                                        0
                                                            ? "유입 "
                                                            : "유출 "}
                                                        {fmtFlow(
                                                            catFlow.equity_domestic
                                                        )}
                                                    </span>
                                                </div>
                                            ) : null}
                                            {usVal > 0 &&
                                            catFlow.equity_foreign != null ? (
                                                <div
                                                    style={{
                                                        display: "flex",
                                                        alignItems: "center",
                                                        justifyContent:
                                                            "space-between",
                                                        padding: "8px 0",
                                                        gap: 10,
                                                        borderTop:
                                                            krVal > 0 &&
                                                            catFlow.equity_domestic !=
                                                                null
                                                                ? `1px solid ${C.line}`
                                                                : "none",
                                                    }}
                                                >
                                                    <span
                                                        style={{
                                                            fontSize: 13,
                                                            fontWeight: 700,
                                                        }}
                                                    >
                                                        해외주식 ETF
                                                    </span>
                                                    <span
                                                        style={{
                                                            fontSize: 13.5,
                                                            fontWeight: 800,
                                                            color:
                                                                catFlow.equity_foreign >
                                                                0
                                                                    ? C.up
                                                                    : C.down,
                                                            fontVariantNumeric:
                                                                "tabular-nums",
                                                        }}
                                                    >
                                                        {catFlow.equity_foreign >
                                                        0
                                                            ? "유입 "
                                                            : "유출 "}
                                                        {fmtFlow(
                                                            catFlow.equity_foreign
                                                        )}
                                                    </span>
                                                </div>
                                            ) : null}
                                            <div
                                                style={{
                                                    fontSize: 11,
                                                    color: C.faint,
                                                    fontWeight: 600,
                                                    marginTop: 8,
                                                    lineHeight: 1.5,
                                                }}
                                            >
                                                내 종목이 아닌 같은 자산군 ETF의
                                                설정·환매 흐름 · 참고 사실 ·
                                                추천 아님
                                            </div>
                                        </div>
                                    ) : null}

                                    <div
                                        style={{
                                            textAlign: "center",
                                            fontSize: 11,
                                            color: C.faint,
                                            fontWeight: 600,
                                            marginTop: 13,
                                            lineHeight: 1.5,
                                        }}
                                    >
                                        비중·집중도 = 평가금액 기준 사실 산술 ·
                                        목표는 직접 설정 · 자산군 자금은 KRX ETF
                                        사실 · 투자자문·추천 아님
                                    </div>
                                </>
                            ) : view === "tax" ? (
                                <>
                                    <div
                                        style={{
                                            ...cardS,
                                            padding: "18px 18px",
                                        }}
                                    >
                                        <div
                                            style={{
                                                fontSize: 12,
                                                color: C.faint,
                                                fontWeight: 700,
                                            }}
                                        >
                                            매도 가정 시 예상 비용 (세금 +
                                            수수료)
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 27,
                                                fontWeight: 800,
                                                letterSpacing: "-1px",
                                                margin: "3px 0",
                                            }}
                                        >
                                            {won(totalTax + totalCommission)}
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 12.5,
                                                color: C.sub,
                                                fontWeight: 600,
                                            }}
                                        >
                                            세금 {wonCompact(totalTax)} + 수수료{" "}
                                            {wonCompact(totalCommission)} ·
                                            평가손익 {totalPl >= 0 ? "+" : ""}
                                            {wonCompact(totalPl)} 기준
                                        </div>
                                    </div>

                                    {brokers.length > 0 && (
                                        <div
                                            style={{
                                                ...cardS,
                                                display: "flex",
                                                alignItems: "center",
                                                justifyContent: "space-between",
                                                gap: 10,
                                                flexWrap: "wrap",
                                            }}
                                        >
                                            <span
                                                style={{
                                                    fontSize: 12.5,
                                                    color: C.sub,
                                                    fontWeight: 700,
                                                }}
                                            >
                                                증권사 (매도 수수료)
                                            </span>
                                            <select
                                                value={brokerIdx}
                                                onChange={(e) =>
                                                    setBrokerIdx(
                                                        Number(e.target.value)
                                                    )
                                                }
                                                style={{
                                                    ...selStyle,
                                                    fontWeight: 700,
                                                    maxWidth: "60%",
                                                }}
                                            >
                                                {brokers.map((b, i) => (
                                                    <option key={i} value={i}>
                                                        {b.name}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                    )}

                                    <div style={cardS}>
                                        <div
                                            style={{
                                                display: "flex",
                                                alignItems: "center",
                                                justifyContent: "space-between",
                                                marginBottom: 6,
                                            }}
                                        >
                                            <span
                                                style={{
                                                    fontSize: 15,
                                                    fontWeight: 800,
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: 7,
                                                }}
                                            >
                                                <FlagIcon code="kr" /> 국내 주식
                                            </span>
                                            <span
                                                style={{
                                                    fontSize: 11.5,
                                                    fontWeight: 800,
                                                    color: C.vg,
                                                    background: C.vgS,
                                                    padding: "3px 9px",
                                                    borderRadius: 8,
                                                }}
                                            >
                                                양도세 0% · 비과세
                                            </span>
                                        </div>
                                        {kv(
                                            "양도소득세",
                                            "0원 (비과세, ~2029)",
                                            C.vg
                                        )}
                                        {kv("증권거래세 0.20%", won(krTxnTax))}
                                        {broker
                                            ? kv(
                                                  "매도 수수료 (" +
                                                      (broker.domestic_fee ||
                                                          "—") +
                                                      ")",
                                                  won(krCommission)
                                              )
                                            : null}
                                        {kv(
                                            "매도금액 합계",
                                            wonCompact(krProceeds)
                                        )}
                                        {krMajorRows.length > 0 && (
                                            <div
                                                style={{
                                                    background: C.warnS,
                                                    color: C.warn,
                                                    borderRadius: 10,
                                                    padding: "9px 11px",
                                                    fontSize: 11.5,
                                                    fontWeight: 700,
                                                    lineHeight: 1.5,
                                                    marginTop: 8,
                                                }}
                                            >
                                                대주주 검토 —{" "}
                                                {krMajorRows
                                                    .map(
                                                        (h) =>
                                                            h.name || h.ticker
                                                    )
                                                    .join(", ")}{" "}
                                                (종목당 10억+ 보유 시 양도세
                                                과세 대상). 시행령 공포일·정확
                                                판정은 세무사 확인.
                                            </div>
                                        )}
                                    </div>

                                    <div style={cardS}>
                                        <div
                                            style={{
                                                display: "flex",
                                                alignItems: "center",
                                                justifyContent: "space-between",
                                                marginBottom: 6,
                                            }}
                                        >
                                            <span
                                                style={{
                                                    fontSize: 15,
                                                    fontWeight: 800,
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: 7,
                                                }}
                                            >
                                                <FlagIcon code="us" /> 해외 주식
                                            </span>
                                            <span
                                                style={{
                                                    fontSize: 11.5,
                                                    fontWeight: 800,
                                                    color: C.warn,
                                                    background: C.warnS,
                                                    padding: "3px 9px",
                                                    borderRadius: 8,
                                                }}
                                            >
                                                양도세 22%
                                            </span>
                                        </div>
                                        {kv(
                                            "양도소득 합계",
                                            (usGainSum >= 0 ? "+" : "") +
                                                wonCompact(usGainSum),
                                            usGainSum >= 0 ? C.up : C.down
                                        )}
                                        {kv(
                                            "기본공제 (연)",
                                            "−" + wonCompact(TAX.US_DEDUCT)
                                        )}
                                        {kv("과세표준", wonCompact(usTaxable))}
                                        {kv(
                                            "예상 양도세",
                                            won(usCgt),
                                            usCgt > 0 ? C.ink : C.vg
                                        )}
                                        {broker
                                            ? kv(
                                                  "매도 수수료 (" +
                                                      (broker.overseas_fee ||
                                                          "—") +
                                                      ")",
                                                  won(usCommission)
                                              )
                                            : null}
                                        <div
                                            style={{
                                                fontSize: 11,
                                                color: C.faint,
                                                fontWeight: 600,
                                                marginTop: 6,
                                                lineHeight: 1.5,
                                            }}
                                        >
                                            22%(과표 3억↓)·27.5%(초과) · 손실
                                            연내통산(이월 없음) · 환율{" "}
                                            {Math.round(FX).toLocaleString()}원/$
                                            {fxInfo.ok ? "" : " (기본값)"}
                                            가정
                                        </div>
                                    </div>

                                    <div style={cardS}>
                                        <div
                                            style={{
                                                fontSize: 12.5,
                                                fontWeight: 800,
                                                marginBottom: 4,
                                            }}
                                        >
                                            종목별 평가손익
                                        </div>
                                        {[...evald]
                                            .sort(
                                                (a, b) =>
                                                    Math.abs(b._pl) -
                                                    Math.abs(a._pl)
                                            )
                                            .map((h, i) => (
                                                <div
                                                    key={h.id || h.ticker}
                                                    style={{
                                                        display: "flex",
                                                        alignItems: "center",
                                                        justifyContent:
                                                            "space-between",
                                                        padding: "9px 0",
                                                        borderTop:
                                                            i === 0
                                                                ? "none"
                                                                : "1px solid " +
                                                                  C.line,
                                                        gap: 10,
                                                    }}
                                                >
                                                    <div
                                                        style={{ minWidth: 0 }}
                                                    >
                                                        <div
                                                            style={{
                                                                fontSize: 13.5,
                                                                fontWeight: 700,
                                                                whiteSpace:
                                                                    "nowrap",
                                                                overflow:
                                                                    "hidden",
                                                                textOverflow:
                                                                    "ellipsis",
                                                                display: "flex",
                                                                alignItems:
                                                                    "center",
                                                                gap: 6,
                                                            }}
                                                        >
                                                            <FlagIcon
                                                                code={
                                                                    h._us
                                                                        ? "us"
                                                                        : "kr"
                                                                }
                                                            />
                                                            {h.name || h.ticker}
                                                        </div>
                                                        <div
                                                            style={{
                                                                fontSize: 11,
                                                                color: C.faint,
                                                                fontWeight: 600,
                                                                marginTop: 2,
                                                            }}
                                                        >
                                                            {!h._priced
                                                                ? "시세 없음 · 손익 계산 제외"
                                                                : h._us
                                                                  ? "양도세 22% 대상"
                                                                  : h._val >=
                                                                      TAX.KR_MAJOR_AMT
                                                                    ? "대주주 과세 검토"
                                                                    : "비과세 · 거래세만"}
                                                        </div>
                                                    </div>
                                                    <div
                                                        style={{
                                                            fontSize: 13.5,
                                                            fontWeight: 800,
                                                            color: h._priced
                                                                ? plColor(h._pl)
                                                                : C.faint,
                                                            fontVariantNumeric:
                                                                "tabular-nums",
                                                            flexShrink: 0,
                                                        }}
                                                    >
                                                        {h._priced
                                                            ? (h._pl >= 0
                                                                  ? "+"
                                                                  : "") +
                                                              wonCompact(h._pl)
                                                            : "—"}
                                                    </div>
                                                </div>
                                            ))}
                                    </div>

                                    <div
                                        style={{ ...cardS, background: C.vgS }}
                                    >
                                        <div
                                            style={{
                                                fontSize: 12.5,
                                                fontWeight: 800,
                                                marginBottom: 7,
                                            }}
                                        >
                                            알아두기
                                        </div>
                                        {[
                                            "국내 상장주식 양도세 = 비과세 (금투세 폐지 2024-12-10, 2029년까지 유지 기조)",
                                            "대주주(종목당 보유 10억+) 는 국내도 양도세 과세 — 시행령 공포일 확인 필요",
                                            "해외주식 양도세 = 22% (과표 3억↓), 연 250만 기본공제(국가 합산), 손익 연내통산",
                                            "수수료는 증권사별로 다름 — 세금(양도세·거래세)은 법정으로 증권사 무관",
                                            "가상자산 양도세 = 2027-01-01~ 22% (연 250만 공제) — 본 추적기는 주식만 계산",
                                        ].map((t, i) => (
                                            <div
                                                key={i}
                                                style={{
                                                    fontSize: 11.5,
                                                    color: C.sub,
                                                    fontWeight: 600,
                                                    lineHeight: 1.55,
                                                    paddingLeft: 12,
                                                    position: "relative",
                                                    marginBottom: 4,
                                                }}
                                            >
                                                <span
                                                    style={{
                                                        position: "absolute",
                                                        left: 0,
                                                        color: C.vg,
                                                    }}
                                                >
                                                    ·
                                                </span>
                                                {t}
                                            </div>
                                        ))}
                                    </div>

                                    <div
                                        style={{
                                            textAlign: "center",
                                            fontSize: 11,
                                            color: C.faint,
                                            fontWeight: 600,
                                            marginTop: 13,
                                            lineHeight: 1.5,
                                        }}
                                    >
                                        세율·공제는 2026 시행값(사실). 추정·관측
                                        보조용 — 실제 납세 판단은 세무사 확인.
                                        절세 자문 아님.
                                    </div>
                                </>
                            ) : (
                                <>
                                    {/* 거래 검색/추가 패널 (매수·매도 기록) */}
                                    {!isDemo && showTAdd && (
                                        <div
                                            style={{
                                                background: C.card,
                                                borderRadius: 16,
                                                padding: "14px 15px",
                                                boxShadow:
                                                    "0 1px 3px rgba(0,0,0,0.04)",
                                                marginTop: 12,
                                            }}
                                        >
                                            <input
                                                style={{
                                                    ...inputStyle,
                                                    width: "100%",
                                                    boxSizing: "border-box",
                                                }}
                                                placeholder="종목 검색 (이름·코드)"
                                                value={tq}
                                                onChange={(e) =>
                                                    setTq(e.target.value)
                                                }
                                            />
                                            {tq.trim() &&
                                                tMatches.length > 0 && (
                                                    <div
                                                        style={{
                                                            marginTop: 8,
                                                            display: "flex",
                                                            flexDirection:
                                                                "column",
                                                            gap: 2,
                                                        }}
                                                    >
                                                        {tMatches.map(
                                                            (m: any) => (
                                                                <div
                                                                    key={
                                                                        m.ticker
                                                                    }
                                                                    onClick={() =>
                                                                        openTAdd(
                                                                            m
                                                                        )
                                                                    }
                                                                    style={{
                                                                        display:
                                                                            "flex",
                                                                        alignItems:
                                                                            "center",
                                                                        gap: 10,
                                                                        padding:
                                                                            "8px 6px",
                                                                        borderRadius: 10,
                                                                        cursor: "pointer",
                                                                    }}
                                                                >
                                                                    <Logo
                                                                        ticker={
                                                                            m.ticker
                                                                        }
                                                                        name={
                                                                            m.name
                                                                        }
                                                                        market={String(
                                                                            m.market
                                                                        ).toLowerCase()}
                                                                        C={C}
                                                                        size={
                                                                            26
                                                                        }
                                                                    />
                                                                    <div
                                                                        style={{
                                                                            minWidth: 0,
                                                                            flex: 1,
                                                                        }}
                                                                    >
                                                                        <div
                                                                            style={{
                                                                                fontSize: 13.5,
                                                                                fontWeight: 700,
                                                                                color: C.ink,
                                                                                whiteSpace:
                                                                                    "nowrap",
                                                                                overflow:
                                                                                    "hidden",
                                                                                textOverflow:
                                                                                    "ellipsis",
                                                                            }}
                                                                        >
                                                                            {m.name ||
                                                                                m.ticker}
                                                                        </div>
                                                                        <div
                                                                            style={{
                                                                                fontSize: 11,
                                                                                color: C.faint,
                                                                                fontWeight: 600,
                                                                            }}
                                                                        >
                                                                            {
                                                                                m.ticker
                                                                            }{" "}
                                                                            ·{" "}
                                                                            {String(
                                                                                m.market
                                                                            ).toUpperCase()}
                                                                        </div>
                                                                    </div>
                                                                    <span
                                                                        style={{
                                                                            border: "none",
                                                                            background:
                                                                                C.vgS,
                                                                            color: C.vg,
                                                                            borderRadius: 999,
                                                                            width: 30,
                                                                            height: 30,
                                                                            fontSize: 15,
                                                                            fontWeight: 800,
                                                                            flexShrink: 0,
                                                                            display:
                                                                                "inline-flex",
                                                                            alignItems:
                                                                                "center",
                                                                            justifyContent:
                                                                                "center",
                                                                        }}
                                                                    >
                                                                        +
                                                                    </span>
                                                                </div>
                                                            )
                                                        )}
                                                    </div>
                                                )}
                                            {tq.trim() &&
                                                tMatches.length === 0 && (
                                                    <div
                                                        style={{
                                                            fontSize: 12,
                                                            color: C.faint,
                                                            fontWeight: 600,
                                                            padding: "8px 4px",
                                                        }}
                                                    >
                                                        {universe.length
                                                            ? "검색 결과 없음"
                                                            : "불러오는 중…"}
                                                    </div>
                                                )}
                                            {!tq.trim() && (
                                                <div
                                                    style={{
                                                        fontSize: 11.5,
                                                        color: C.faint,
                                                        fontWeight: 600,
                                                        padding: "8px 4px 2px",
                                                        lineHeight: 1.5,
                                                    }}
                                                >
                                                    종목을 검색해 선택하면
                                                    매수·매도·체결가·거래일을
                                                    입력해 기록해요.
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* 🚨 거래 로딩 스켈레톤 — 없으면 "거래 0건 / 기록 없어요" 가 먼저 뜬 뒤
                                        실제 내역으로 바뀌어 빈 상태가 번쩍인다(2026-07-27 PM 지적 동일 계열). */}
                                    {tradesLoading ? (
                                        <>
                                            <div style={{ ...cardS, padding: "18px 18px" }}>
                                                <div style={sk(140, 12, 6)} />
                                                <div style={{ ...sk(190, 26, 8), marginTop: 10 }} />
                                                <div style={{ ...sk(240, 11, 6), marginTop: 10 }} />
                                            </div>
                                            <div style={{ ...cardS, padding: "16px 18px", marginTop: 10 }}>
                                                <div style={sk(72, 13, 6)} />
                                                {[0, 1, 2].map((i) => (
                                                    <div
                                                        key={i}
                                                        style={{
                                                            display: "flex",
                                                            alignItems: "center",
                                                            gap: 10,
                                                            marginTop: 14,
                                                        }}
                                                    >
                                                        <div style={sk(30, 30, 10)} />
                                                        <div style={{ flex: 1 }}>
                                                            <div style={sk("42%", 12, 6)} />
                                                            <div style={{ ...sk("28%", 10, 6), marginTop: 6 }} />
                                                        </div>
                                                        <div style={sk(84, 13, 6)} />
                                                    </div>
                                                ))}
                                            </div>
                                        </>
                                    ) : (
                                    <>
                                    {/* 실현손익 합계 (매도 확정분) */}
                                    <div
                                        style={{
                                            ...cardS,
                                            padding: "18px 18px",
                                        }}
                                    >
                                        <div
                                            style={{
                                                fontSize: 12,
                                                color: C.faint,
                                                fontWeight: 700,
                                            }}
                                        >
                                            실현손익 합계 · 매도 확정분(사실)
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 27,
                                                fontWeight: 800,
                                                letterSpacing: "-1px",
                                                margin: "3px 0",
                                                color: plColor(realizedKrw),
                                            }}
                                        >
                                            {(realizedKrw > 0 ? "+" : "") +
                                                money(realizedKrw)}
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 12,
                                                color: C.faint,
                                                fontWeight: 600,
                                                marginTop: 4,
                                            }}
                                        >
                                            이동평균 매입가 차감(사실) · 거래{" "}
                                            {(tradeData.trades || []).length}건
                                            {tHasUs
                                                ? ` · 미국주식 환율 ${Math.round(FX).toLocaleString()}원/$${fxInfo.ok ? "" : " (기본값)"}`
                                                : ""}
                                        </div>
                                    </div>

                                    {/* 종목별 실현손익 + 잔여 보유 */}
                                    {tByTicker.length > 0 && (
                                        <div
                                            style={{
                                                display: "flex",
                                                flexDirection: "column",
                                                gap: 8,
                                                marginTop: 12,
                                            }}
                                        >
                                            {tByTicker.map((s: any) => {
                                                const us =
                                                    String(s.market) === "us"
                                                return (
                                                    <div
                                                        key={s.ticker}
                                                        onClick={() =>
                                                            goStock(s)
                                                        }
                                                        role="link"
                                                        tabIndex={0}
                                                        style={{
                                                            display: "flex",
                                                            alignItems:
                                                                "center",
                                                            gap: 12,
                                                            background: C.card,
                                                            borderRadius: 16,
                                                            padding:
                                                                "13px 15px",
                                                            boxShadow:
                                                                "0 1px 3px rgba(0,0,0,0.04)",
                                                            cursor: "pointer",
                                                        }}
                                                    >
                                                        <Logo
                                                            ticker={s.ticker}
                                                            name={s.name}
                                                            market={s.market}
                                                            C={C}
                                                            size={36}
                                                        />
                                                        <div
                                                            style={{
                                                                minWidth: 0,
                                                                flex: 1,
                                                            }}
                                                        >
                                                            <div
                                                                style={{
                                                                    fontSize: 14.5,
                                                                    fontWeight: 700,
                                                                    whiteSpace:
                                                                        "nowrap",
                                                                    overflow:
                                                                        "hidden",
                                                                    textOverflow:
                                                                        "ellipsis",
                                                                }}
                                                            >
                                                                {s.name ||
                                                                    s.ticker}
                                                            </div>
                                                            <div
                                                                style={{
                                                                    fontSize: 11.5,
                                                                    color: C.faint,
                                                                    fontWeight: 600,
                                                                    marginTop: 2,
                                                                }}
                                                            >
                                                                {Number(
                                                                    s.open_shares
                                                                ) > 0
                                                                    ? `보유 ${s.open_shares}주 · 평단 ${px(Number(s.open_avg_cost) || 0, us, ccy, FX)}`
                                                                    : "전량 매도"}
                                                            </div>
                                                        </div>
                                                        <div
                                                            style={{
                                                                textAlign:
                                                                    "right",
                                                                flexShrink: 0,
                                                            }}
                                                        >
                                                            <div
                                                                style={{
                                                                    fontSize: 14.5,
                                                                    fontWeight: 800,
                                                                    color: plColor(
                                                                        Number(
                                                                            s.realized_pnl
                                                                        ) || 0
                                                                    ),
                                                                }}
                                                            >
                                                                {((Number(
                                                                    s.realized_pnl
                                                                ) || 0) > 0
                                                                    ? "+"
                                                                    : "") +
                                                                    px(
                                                                        Number(
                                                                            s.realized_pnl
                                                                        ) || 0,
                                                                        us,
                        ccy,
                        FX
                                                                    )}
                                                            </div>
                                                            <div
                                                                style={{
                                                                    fontSize: 11.5,
                                                                    color: C.faint,
                                                                    fontWeight: 600,
                                                                    marginTop: 2,
                                                                }}
                                                            >
                                                                실현손익
                                                            </div>
                                                        </div>
                                                    </div>
                                                )
                                            })}
                                        </div>
                                    )}

                                    {/* 거래 이력 (원장) */}
                                    <div
                                        style={{
                                            ...cardS,
                                            padding: "16px 17px",
                                        }}
                                    >
                                        <div
                                            style={{
                                                fontSize: 12.5,
                                                fontWeight: 800,
                                                marginBottom: 6,
                                            }}
                                        >
                                            거래 이력
                                        </div>
                                        {tLedger.length === 0 ? (
                                            <div
                                                style={{
                                                    fontSize: 12,
                                                    color: C.faint,
                                                    fontWeight: 600,
                                                    padding: "10px 2px",
                                                }}
                                            >
                                                아직 기록한 거래가 없어요.{" "}
                                                {isDemo
                                                    ? "로그인하면"
                                                    : "+ 거래 추가로"}{" "}
                                                매수·매도를 남겨보세요.
                                            </div>
                                        ) : (
                                            tLedger.map((t: any, i: number) => {
                                                const us =
                                                    String(t.market) === "us"
                                                const isBuy = t.side === "buy"
                                                return (
                                                    <div
                                                        key={t.id || i}
                                                        style={{
                                                            display: "flex",
                                                            alignItems:
                                                                "center",
                                                            gap: 11,
                                                            padding: "10px 0",
                                                            borderTop:
                                                                i === 0
                                                                    ? "none"
                                                                    : "1px solid " +
                                                                      C.line,
                                                        }}
                                                    >
                                                        <Logo
                                                            ticker={t.ticker}
                                                            name={t.name}
                                                            market={t.market}
                                                            C={C}
                                                            size={30}
                                                        />
                                                        <div
                                                            style={{
                                                                minWidth: 0,
                                                                flex: 1,
                                                            }}
                                                        >
                                                            <div
                                                                style={{
                                                                    fontSize: 13.5,
                                                                    fontWeight: 700,
                                                                    whiteSpace:
                                                                        "nowrap",
                                                                    overflow:
                                                                        "hidden",
                                                                    textOverflow:
                                                                        "ellipsis",
                                                                    display:
                                                                        "flex",
                                                                    alignItems:
                                                                        "center",
                                                                    gap: 6,
                                                                }}
                                                            >
                                                                <span
                                                                    style={{
                                                                        fontSize: 10.5,
                                                                        fontWeight: 800,
                                                                        color: isBuy
                                                                            ? C.down
                                                                            : C.up,
                                                                        background:
                                                                            isBuy
                                                                                ? C.buyS
                                                                                : C.sellS,
                                                                        borderRadius: 6,
                                                                        padding:
                                                                            "2px 6px",
                                                                        flexShrink: 0,
                                                                    }}
                                                                >
                                                                    {isBuy
                                                                        ? "매수"
                                                                        : "매도"}
                                                                </span>
                                                                <span
                                                                    style={{
                                                                        whiteSpace:
                                                                            "nowrap",
                                                                        overflow:
                                                                            "hidden",
                                                                        textOverflow:
                                                                            "ellipsis",
                                                                    }}
                                                                >
                                                                    {t.name ||
                                                                        t.ticker}
                                                                </span>
                                                            </div>
                                                            <div
                                                                style={{
                                                                    fontSize: 11,
                                                                    color: C.faint,
                                                                    fontWeight: 600,
                                                                    marginTop: 2,
                                                                }}
                                                            >
                                                                {t.traded_at ||
                                                                    "—"}{" "}
                                                                ·{" "}
                                                                {Number(
                                                                    t.shares
                                                                ) || 0}
                                                                주 @{" "}
                                                                {px(
                                                                    Number(
                                                                        t.price
                                                                    ) || 0,
                                                                    us,
                        ccy,
                        FX
                                                                )}
                                                            </div>
                                                        </div>
                                                        <div
                                                            style={{
                                                                fontSize: 13,
                                                                fontWeight: 800,
                                                                color: C.ink,
                                                                fontVariantNumeric:
                                                                    "tabular-nums",
                                                                flexShrink: 0,
                                                                textAlign:
                                                                    "right",
                                                            }}
                                                        >
                                                            {px(
                                                                (Number(
                                                                    t.shares
                                                                ) || 0) *
                                                                    (Number(
                                                                        t.price
                                                                    ) || 0),
                                                                us,
                                                                ccy,
                                                                FX
                                                            )}
                                                        </div>
                                                        {!isDemo && t.id && (
                                                            <button
                                                                onClick={() =>
                                                                    openTEdit(t)
                                                                }
                                                                title="거래 수정"
                                                                style={{
                                                                    border: "none",
                                                                    background:
                                                                        "transparent",
                                                                    cursor: "pointer",
                                                                    color: C.faint,
                                                                    fontSize: 12,
                                                                    fontWeight: 700,
                                                                    padding:
                                                                        "0 2px",
                                                                    flexShrink: 0,
                                                                }}
                                                            >
                                                                수정
                                                            </button>
                                                        )}
                                                        {!isDemo && t.id && (
                                                            <button
                                                                onClick={() =>
                                                                    delTrade(
                                                                        t.id
                                                                    )
                                                                }
                                                                title="삭제"
                                                                style={{
                                                                    border: "none",
                                                                    background:
                                                                        "transparent",
                                                                    cursor: "pointer",
                                                                    color: C.faint,
                                                                    fontSize: 16,
                                                                    fontWeight: 700,
                                                                    padding:
                                                                        "0 2px",
                                                                    flexShrink: 0,
                                                                }}
                                                            >
                                                                ×
                                                            </button>
                                                        )}
                                                    </div>
                                                )
                                            })
                                        )}
                                    </div>

                                    <div
                                        style={{
                                            textAlign: "center",
                                            fontSize: 11,
                                            color: C.faint,
                                            fontWeight: 600,
                                            marginTop: 13,
                                            lineHeight: 1.5,
                                        }}
                                    >
                                        실현손익 = 매도가 − 이동평균 매입가
                                        (단순 계산·사실) · 본인 기록용 ·
                                        순위·배지·공개 없음 · 투자자문 아님
                                    </div>
                                    </>
                                    )}
                                </>
                            )
                        /* 미로그인(=isDemo) = 브라우저 창 목업 안 SAMPLE 미리보기 + "예시" 배지.
                           pointerEvents none 이라 조작 불가 — 로그인 CTA 로만 진입.
                           🚨 캔버스 전용(onCanvas)으로 좁히지 말 것 — 2026-07-27 그렇게 좁혔다가
                           로그인 전 미리보기가 통째로 사라졌다(PM 지적 2026-08-01). */
                        return isDemo ? (
                            rows.length ? (
                                <div
                                    style={{
                                        marginTop: 14,
                                        borderRadius: 16,
                                        border: `1px solid ${C.line}`,
                                        boxShadow:
                                            "0 6px 16px rgba(0,0,0,0.08)",
                                        overflow: "hidden",
                                        background: C.card,
                                    }}
                                >
                                    <div
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            gap: 7,
                                            padding: "10px 13px",
                                            borderBottom: `1px solid ${C.line}`,
                                            background: C.rowHd,
                                        }}
                                    >
                                        <span
                                            style={{
                                                width: 11,
                                                height: 11,
                                                borderRadius: "50%",
                                                background: "#ff5f57",
                                                flexShrink: 0,
                                            }}
                                        />
                                        <span
                                            style={{
                                                width: 11,
                                                height: 11,
                                                borderRadius: "50%",
                                                background: "#febc2e",
                                                flexShrink: 0,
                                            }}
                                        />
                                        <span
                                            style={{
                                                width: 11,
                                                height: 11,
                                                borderRadius: "50%",
                                                background: "#28c840",
                                                flexShrink: 0,
                                            }}
                                        />
                                        <div
                                            style={{
                                                flex: 1,
                                                minWidth: 0,
                                                margin: "0 6px",
                                                background: C.bg,
                                                borderRadius: 7,
                                                padding: "5px 12px",
                                                fontSize: 11.5,
                                                color: C.faint,
                                                fontWeight: 600,
                                                textAlign: "center",
                                                whiteSpace: "nowrap",
                                                overflow: "hidden",
                                                textOverflow: "ellipsis",
                                            }}
                                        >
                                            alphanest.kr/nest
                                        </div>
                                        <span
                                            style={{
                                                flexShrink: 0,
                                                fontSize: 10.5,
                                                fontWeight: 800,
                                                color: C.vg,
                                                background: C.vgS,
                                                borderRadius: 6,
                                                padding: "3px 8px",
                                            }}
                                        >
                                            예시
                                        </span>
                                    </div>
                                    <div
                                        style={{
                                            padding: narrow
                                                ? "0 12px 14px"
                                                : "0 16px 16px",
                                            pointerEvents: "none",
                                        }}
                                    >
                                        {content}
                                    </div>
                                </div>
                            ) : null
                        ) : (
                            content
                        )
                    })()}
                </>
            )}
        </div>
    )
}

addPropertyControls(PublicHoldingsTab, {
    apiBase: {
        type: ControlType.String,
        title: "API Base",
        defaultValue: DEFAULT_API,
    },
    loginUrl: {
        type: ControlType.String,
        title: "Login URL",
        defaultValue: "/login",
    },
    stockPath: {
        type: ControlType.String,
        title: "Stock Path (KR)",
        defaultValue: "/stock",
    },
    usStockPath: {
        type: ControlType.String,
        title: "Stock Path (US)",
        defaultValue: "/stock",
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark",
        defaultValue: false,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
})

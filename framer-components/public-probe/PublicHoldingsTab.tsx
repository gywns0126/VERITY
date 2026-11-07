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
 * 되돌리지 말 것 (2026-09-14): HTTP 성공 확인, 계정별 응답 격리, 입력 오류 표시, 시세 결손 세금 보류.
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
 *   세금(법정·증권사 무관) = KR 양도세 0%(대주주 제외)+증권거래세 0.20% / 일반 국외주식 양도세 22%·250만 공제 / 대주주 50억 경고(직전 사업연도말 종가 기준).
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
// SVG images cannot inherit page CSS variables; encode each resolved theme color.
const selectChevronUrl = (color: string) => `url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6' width='10' height='6'><path d='M1 1l4 4 4-4' stroke='${color}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>`)}")`
const AN_PALETTE =
    "body{" +
    Object.keys(LIGHT)
        .map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k])
        .join(";") +
    ";--an-hld-select-chevron:" + selectChevronUrl(LIGHT.faint) +
    "}" +
    'body[data-framer-theme="dark"]{' +
    Object.keys(DARK)
        .map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k])
        .join(";") +
    ";--an-hld-select-chevron:" + selectChevronUrl(DARK.faint) +
    "}"

const NEST_NAV_CSS = `
.an-hld-simple{--nest-stack:#f8f9fb;--nest-hover:#f1f3f5;--nest-focus:#e9edf2;--nest-card:#ffffff;--nest-sub:#6b7684;--nest-accent:#6c5ce7}
.an-hld-simple[data-nest-dark="true"],html:not([data-an-theme="light"]) body[data-framer-theme="dark"] .an-hld-simple:not([data-nest-canvas="true"]),html[data-an-theme="dark"] .an-hld-simple:not([data-nest-canvas="true"]){--nest-stack:#1d242c;--nest-hover:#252c35;--nest-focus:#303945;--nest-card:#171c23;--nest-sub:#9aa4b1;--nest-accent:#a99bff}
html[data-an-theme="light"] .an-hld-simple:not([data-nest-canvas="true"]){--nest-stack:#f8f9fb;--nest-hover:#f1f3f5;--nest-focus:#e9edf2;--nest-card:#ffffff;--nest-sub:#6b7684;--nest-accent:#6c5ce7}
.an-hld-simple .an-hld-nav-button{display:inline-flex;align-items:center;justify-content:center;gap:8px;box-sizing:border-box;min-width:0;min-height:44px;padding:10px 12px;border:0;border-radius:10px;background:transparent;color:var(--nest-sub);font:700 13px/1.4 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;cursor:pointer;text-decoration:none;transition:background-color 160ms ease,color 160ms ease}
.an-hld-simple .an-hld-nav-button[aria-pressed="true"]{background:var(--nest-card);color:var(--nest-accent)}
@media(hover:hover){.an-hld-simple .an-hld-nav-button:not(:focus-visible):hover{background:var(--nest-hover)}}
.an-hld-simple .an-hld-nav-button:focus-visible{background:var(--nest-focus);outline:none;box-shadow:none}
@media(prefers-reduced-motion:reduce){.an-hld-simple .an-hld-nav-button{transition:none}}
`

const CVAR: Record<string, string> = {}
for (const _k of Object.keys(LIGHT))
    CVAR[_k] = "var(--an-" + _ANP + "-" + _k + ")"

const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const FX_FALLBACK = 1380 // 캔버스/비로그인 예시에만 사용. 실제 평가·세금에는 사용하지 않는다.

/* ── 환율·통화 (2026-07-30) ────────────────────────────────────────────────
   🚨 옛 코드는 FX 를 1380 으로 **하드코딩**해 두고 화면에도 "환율 1380원/$ 가정" 이라 적었다.
   실제 환율이 1,450원대라 미국 보유분 평가액이 약 5% 낮게 잡히고 있었다(PM 지적 계기).
   이제 macro_snapshot.json 의 usd_krw(yfinance, 30분 크론)를 읽는다. 실시간 틱이 아니므로
   화면에 기준 시각을 함께 적는다 — 없는 정밀도를 있는 척하지 않는다. 스냅샷 실패 시에만 1380 폴백.
   Framer 코드 컴포넌트는 서로 import 할 수 없어 이 블록은 각 파일에 같은 모양으로 둔다. */
const AN_FX_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/macro_snapshot.json"
const CLOSE_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/kr_close_latest.json"
const EXPOSURE_MAP_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio_exposure_map.json"
const CLOSE_REFRESH_THROTTLE_MS = 2 * 60 * 1000
const CLOSE_VISIBLE_POLL_MS = 5 * 60 * 1000
const CLOSE_REQUEST_TIMEOUT_MS = 15 * 1000

type CloseSnapshot = {
    prices: Record<string, number>
    asOf: string
    generatedAt: string
    source: string
    count: number
}

function kstDateKey(now: number): string {
    return new Date(now + 9 * 60 * 60 * 1000).toISOString().slice(0, 10).replace(/-/g, "")
}

function closeDateUtc(asOf: string): number {
    if (!/^\d{8}$/.test(asOf)) return NaN
    const y = Number(asOf.slice(0, 4))
    const m = Number(asOf.slice(4, 6))
    const d = Number(asOf.slice(6, 8))
    const value = Date.UTC(y, m - 1, d)
    const roundTrip = new Date(value).toISOString().slice(0, 10).replace(/-/g, "")
    return roundTrip === asOf ? value : NaN
}

function normalizeCloseSnapshot(raw: any, now: number = Date.now()): CloseSnapshot {
    const meta = raw && raw._meta
    const source = String((meta && meta.source) || "")
    const asOf = String((meta && meta.as_of) || "")
    const generatedAt = String((meta && meta.generated_at) || "")
    const asOfTime = closeDateUtc(asOf)
    const generatedTime = Date.parse(generatedAt)
    if (!raw || typeof raw !== "object" || !meta || typeof meta !== "object")
        throw new Error("종가 응답 메타데이터를 확인할 수 없어요.")
    if (!source.includes("금융위원회"))
        throw new Error("종가 출처를 확인할 수 없어요.")
    if (!isFinite(asOfTime) || asOf > kstDateKey(now))
        throw new Error("종가 기준일을 확인할 수 없어요.")
    if (!isFinite(generatedTime) || generatedTime > now + 60 * 60 * 1000)
        throw new Error("종가 생성 시각을 확인할 수 없어요.")
    const input = raw.prices
    if (!input || typeof input !== "object" || Array.isArray(input))
        throw new Error("종가 목록 형식을 확인할 수 없어요.")
    const prices: Record<string, number> = {}
    for (const ticker of Object.keys(input)) {
        const value = Number(input[ticker])
        if (!ticker || !(value > 0) || !isFinite(value))
            throw new Error("종가 목록에 잘못된 값이 있어요.")
        prices[ticker] = value
    }
    const count = Object.keys(prices).length
    if (count < 500 || Number(meta.count) !== count)
        throw new Error("종가 목록 수량을 확인할 수 없어요.")
    return { prices, asOf, generatedAt, source, count }
}

function closeBusinessLag(asOf: string, now: number = Date.now()): number {
    const start = closeDateUtc(asOf)
    if (!isFinite(start)) return Infinity
    const todayKey = kstDateKey(now)
    const end = closeDateUtc(todayKey)
    let days = 0
    for (let cursor = start + 86400000; cursor <= end; cursor += 86400000) {
        const day = new Date(cursor).getUTCDay()
        if (day >= 1 && day <= 5) days += 1
    }
    return days
}

function describeCloseFreshness(snapshot: CloseSnapshot, now: number = Date.now()) {
    const businessLag = closeBusinessLag(snapshot.asOf, now)
    const generatedAgeHours = Math.max(0, (now - Date.parse(snapshot.generatedAt)) / 3600000)
    const delayed = businessLag > 1 || generatedAgeHours > 96
    return {
        businessLag,
        generatedAgeHours,
        delayed,
        label: delayed ? "업데이트 지연 가능" : "공개 종가 확인",
    }
}
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
    const [ccy, setCcy] = useState<string>(() =>
        onCanvas ? "USD" : anReadCcy()
    )
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
            if (onCanvas) return
            try {
                window.localStorage.setItem(AN_CCY_KEY, v)
                window.dispatchEvent(new CustomEvent(AN_CCY_EVENT))
            } catch (e) {
                /* no-op */
            }
        },
    ]
}
function useAnFx(onCanvas: boolean): {
    rate: number
    asOf: string
    ok: boolean
} {
    const [fx, setFx] = useState<any>(null)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        try {
            const c = sessionStorage.getItem("an_fx")
            if (c) {
                const j = JSON.parse(c)
                if (
                    j &&
                    j.rate > 0 &&
                    Date.now() - Number(j.cachedAt) < 30 * 60 * 1000
                ) {
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
                const j = {
                    rate,
                    asOf: String((u && u.as_of) || ""),
                    cachedAt: Date.now(),
                }
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
    }, [onCanvas])
    return fx &&
        fx.rate > 0 &&
        Date.now() - Date.parse(fx.asOf) < 96 * 3600 * 1000
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
function useBfLogoMap(offline = false): Record<string, string> | null {
    const [m, setM] = useState<Record<string, string> | null>(__bfMap)
    useEffect(() => {
        if (offline) return
        let al = true
        fetchBfMap().then((mm) => {
            if (al) setM(mm)
        })
        return () => {
            al = false
        }
    }, [offline])
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
    // 🚨 2026-08-22 정정 10억→50억. 종전 값은 '2025-12 환원 통과' 라는 틀린 전제였다 —
    //   실제는 채택 안 됨, 현행 50억 유지(기재부·정책브리핑·국회예산정책처·KDI 4출처).
    //   SoT = api/trading/account_profile.py · 동기 가드 = tests/test_tax_constants_sync.py
    KR_MAJOR_AMT: 5_000_000_000, // 대주주 종목당 보유 평가액 기준 = 50억 (양도세 과세)
    US_CGT: 0.22, // 일반 국외주식 양도세 (소득세 20% + 지방세 2%)
    US_CGT_HIGH: 0.22, // 호환용: 국내 대주주 누진 구간을 국외주식에 적용하지 않음
    US_DEDUCT: 2_500_000, // 해외 양도소득 기본공제 (연, 합산)
    US_BRACKET: 300_000_000, // 과표 3억 분기점
}

interface Props {
    apiBase: string
    loginUrl: string
    stockPath: string
    usStockPath: string
    dark: boolean
    showReadingGuide?: boolean
    previewOnly?: boolean
    demoPath?: string
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
const SAMPLE_SECTORS: Record<string, string> = {
    "005930": "반도체",
    "000660": "반도체",
    NVDA: "반도체",
    AAPL: "IT 하드웨어",
}

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


// Example-only fixtures. Prices, dates, FX and fees are illustrative fixed values.
const NEST_DEMO_AS_OF = "20260618"
const NEST_DEMO_CATALOG = [...SAMPLE, { ticker: "MSFT", name: "Microsoft", market: "us", price: 100 }]
const NEST_DEMO_FX = { rate: FX_FALLBACK, asOf: "2026-06-18T15:30:00+09:00", ok: true }
const NEST_DEMO_BROKERS = [{ name: "예시 증권사 · 학습용 수수료", domestic_fee: "0.015%", overseas_fee: "0.25%" }]
const nestDemoRows = () => SAMPLE.map((row, index) => ({ ...row, id: "demo-h-" + index }))
const nestDemoTrades = () => SAMPLE_TRADES.map((row, index) => ({ ...row, id: "demo-t-" + index }))

// Same moving-average rule as /api/trades; no request or account data is used.
function nestDemoTradeData(input: any[]) {
    const trades = input.map((trade) => ({ ...trade }))
    const groups = new Map<string, any[]>()
    for (const trade of trades) groups.set(trade.ticker, [...(groups.get(trade.ticker) || []), trade])
    let unmatched = 0
    const by_ticker = Array.from(groups, ([ticker, records]) => {
        let quantity = 0, cost = 0, realized = 0, name = "", market = "kr"
        records.sort((a, b) => String(a.traded_at || "").localeCompare(String(b.traded_at || "")) || String(a.created_at || "").localeCompare(String(b.created_at || "")))
        for (const trade of records) {
            const shares = Number(trade.shares), price = Number(trade.price)
            name = trade.name || name
            market = trade.market || market
            if (!(shares > 0) || !(price > 0)) continue
            if (trade.side === "buy") {
                quantity += shares
                cost += shares * price
            } else {
                unmatched += Math.max(0, shares - quantity)
                if (!(quantity > 0)) continue
                const average = cost / quantity
                const sold = Math.min(shares, quantity)
                realized += (price - average) * sold
                quantity -= sold
                cost = average * quantity
            }
        }
        return { ticker, name, market, realized_pnl: Number(realized.toFixed(2)), open_shares: Number(quantity.toFixed(6)), open_avg_cost: quantity > 0 ? Number((cost / quantity).toFixed(4)) : 0 }
    }).sort((a, b) => b.realized_pnl - a.realized_pnl)
    const total = (market: string) => Number(by_ticker.filter((row) => row.market === market).reduce((sum, row) => sum + row.realized_pnl, 0).toFixed(2))
    return { trades, summary: { by_ticker, total_realized_pnl: new Set(by_ticker.map((row) => row.market)).size > 1 ? null : total(by_ticker[0]?.market || "kr"), realized_by_currency: { KRW: total("kr"), USD: total("us") }, unmatched_sell_shares: Number(unmatched.toFixed(6)) } }
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
// Presentation identity only; authentication is always verified by the API.
function accountKey(): string {
    try {
        const s = JSON.parse(
            localStorage.getItem("verity_supabase_session") || "null"
        )
        return s?.user?.id || s?.access_token || ""
    } catch {
        return ""
    }
}
function supportedAsset(x: any): boolean {
    const market = String(x.market || "").toLowerCase()
    return (
        !String(x.ticker || "")
            .toUpperCase()
            .startsWith("CMD_") &&
        x.type !== "commodity" &&
        ["kr", "us"].includes(market)
    )
}
async function nestRequest(url: string, init: RequestInit = {}): Promise<any> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 28000)
    try {
        const r = await fetch(url, {
            ...init,
            signal: controller.signal,
            cache: init.headers ? "no-store" : "default",
        })
        const data = await r.json().catch(() => null)
        if (!r.ok)
            throw new Error(
                r.status === 401
                    ? "로그인 시간이 만료됐어요. 잠시 후 다시 시도하거나 다시 로그인해 주세요."
                    : (data?.error || "요청 실패") + " (HTTP " + r.status + ")"
            )
        if (!data) throw new Error("서버 응답을 확인할 수 없어요.")
        return data
    } catch (error: any) {
        if (error?.name === "AbortError" || error instanceof TypeError)
            throw new Error(
                "응답을 확인하지 못했어요. 저장·삭제 여부는 목록을 다시 확인해 주세요. 입력 내용은 유지됩니다."
            )
        throw error
    } finally {
        clearTimeout(timer)
    }
}
function money(v: number): string {
    if (!isFinite(v)) return "—"
    return Math.round(v).toLocaleString("en-US") + "원"
}
const won = money
function wonCompact(v: number): string {
    if (!isFinite(v)) return "—"
    const a = Math.abs(Math.round(v))
    const sign = v < 0 ? "-" : ""
    if (a >= 1e8) return sign + (a / 1e8).toFixed(a >= 1e9 ? 0 : 1) + "억원"
    if (a >= 1e4)
        return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만원"
    return sign + a.toLocaleString("en-US") + "원"
}
function parseFee(s: any): number {
    const match = String(s || "")
        .trim()
        .match(/^(\d+(?:\.\d+)?)\s*%$/)
    return match ? Number(match[1]) / 100 : NaN
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

function fmtCloseGeneratedAt(s: string): string {
    const t = Date.parse(String(s || ""))
    if (!isFinite(t)) return "생성 시각 미확인"
    try {
        return new Intl.DateTimeFormat("ko-KR", {
            month: "numeric",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
            timeZone: "Asia/Seoul",
        }).format(new Date(t))
    } catch {
        return String(s)
    }
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
function groupExposure(rows: any[], key: (row: any) => string): any[] {
    const sums = new Map<string, number>()
    for (const row of rows)
        sums.set(key(row), (sums.get(key(row)) || 0) + row.value)
    const total = rows.reduce((sum, row) => sum + row.value, 0)
    return Array.from(sums, ([name, value]) => ({
        name,
        value,
        weight: total > 0 ? (value / total) * 100 : 0,
    })).sort((a, b) => b.value - a.value)
}
function ExposureRows(props: { rows: any[]; C: any; limit?: number }) {
    const { rows, C } = props
    const limit = props.limit || 8
    if (!rows.length)
        return (
            <div style={{ color: C.faint, fontSize: 11.5, fontWeight: 600 }}>
                계산 가능한 보유종목 없음
            </div>
        )
    return (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", minWidth: 0, gap: 9 }}>
            {rows.slice(0, limit).map((row: any) => (
                <div key={row.name} style={{ minWidth: 0 }}>
                    <div
                        style={{
                            display: "flex",
                            justifyContent: "space-between",
                            gap: 10,
                            fontSize: 11.5,
                        }}
                    >
                        <span
                            title={row.name}
                            style={{
                                minWidth: 0,
                                flex: 1,
                                color: C.sub,
                                fontWeight: 700,
                                whiteSpace: "nowrap",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                            }}
                        >
                            {row.name}
                        </span>
                        <span
                            style={{
                                flexShrink: 0,
                                color: C.ink,
                                fontWeight: 800,
                            }}
                        >
                            {row.weight.toFixed(1)}% · {wonCompact(row.value)}
                        </span>
                    </div>
                    <div
                        aria-hidden
                        style={{
                            marginTop: 5,
                            height: 6,
                            borderRadius: 999,
                            background: C.line,
                            overflow: "hidden",
                        }}
                    >
                        <div
                            style={{
                                width: `${Math.max(1, Math.min(100, row.weight))}%`,
                                height: "100%",
                                borderRadius: 999,
                                background: C.vg,
                            }}
                        />
                    </div>
                </div>
            ))}
        </div>
    )
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

/* 관심/보유 별 — 🚨 PublicStockReport 헤더 별과 **같은 자산**이다(2026-08-22 PM 지시
   "리포트에서 쓰는것처럼 노랑색 모서리가 둥근 별"). 종전엔 문자 ★ 를 보라색으로 썼는데
   같은 사이트에서 같은 뜻의 마크가 두 형태로 보였다.
   · 소프트골드 #f6b93b + strokeLinejoin="round" 로 꼭짓점을 둥글린다(토스풍, 2026-06-22 확정)
   · 문자 ★ 로 되돌리지 말 것 — 폰트마다 모양·굵기가 달라 렌더가 흔들린다.
   · path 는 리포트와 동일. 한쪽만 바꾸면 두 화면이 갈린다. */
const AN_STAR_GOLD = "#f6b93b"
function StarMark(props: { size?: number; color?: string }) {
    const sz = props.size || 16
    const c = props.color || AN_STAR_GOLD
    return (
        <svg
            width={sz}
            height={sz}
            viewBox="0 0 24 24"
            style={{ fill: c, stroke: c, flexShrink: 0 }}
            strokeWidth={2.6}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
        >
            <path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.685 21.5a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.45 10.286a.53.53 0 0 1 .294-.903l5.165-.756a2.122 2.122 0 0 0 1.597-1.16z" />
        </svg>
    )
}

function Logo(props: {
    ticker: string
    name: string
    market: string
    C: any
    size?: number
    offline?: boolean
}) {
    const { ticker, name, market, C } = props
    const size = props.size || 32
    const [err, setErr] = useState(false)
    const lm = useBfLogoMap(!!props.offline)
    const bfSrc = props.offline ? "" : bfLogoSrc(ticker, lm, size)
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
            const h = document.documentElement
                ? document.documentElement.dataset.anTheme
                : null
            if (h === "dark") return true
            if (h === "light") return false
            if (document.body) {
                const a = document.body.dataset.framerTheme
                if (a === "dark") return true
                if (a === "light") return false
            }
        }
        const s =
            typeof localStorage !== "undefined"
                ? localStorage.getItem("verity_theme")
                : null
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
    if (!v || v === "/us/stock")
        return String(kr || "").replace(/\/+$/, "") || "/stock"
    return v
}

/* 둥지 배지 — 보유 종목의 ① 최근 공시(3일창) ② 국민연금 대량보유(5%+).
   🚨 RULE 7 — 공시 제목은 DART/SEC **원문 그대로**, 지분율은 공시 수치. 점수·등급·추천 0.
   🚨 국민연금은 5% 이상 대량보유 공시가 원천이라 **없음 ≠ 미보유**. 색인에 없으면 아무것도
      표시하지 않는다(= "5% 미만"). 부재를 보유하지 않는다고 단정하는 문구는 거짓이 된다.
   🚨 색인 로드 전(null)에는 아무것도 그리지 않는다 — 없음을 단정하지 않기 위해서다. */
function NestBadges(props: {
    h: any
    nestIdx: Record<string, any> | null
    npsMap: Record<string, number> | null
    C: any
}) {
    const { h, nestIdx, npsMap, C } = props
    const tk = String(h && h.ticker ? h.ticker : "")
    if (!tk) return null
    const ent = nestIdx ? nestIdx[tk] : null
    const evs: any[] = ent && Array.isArray(ent.ev) ? ent.ev : []
    const pct = Number(npsMap && npsMap[tk]) || 0
    if (!evs.length && !(pct > 0)) return null
    // 🚨 2026-08-22 PM — "세로로 배치하지 말고 스택 높이 변화 없이 표시".
    //   종전 flexWrap:"wrap" + marginTop 이라 칩이 줄바꿈되며 **행 높이가 늘었다**
    //   (국민연금 1 + 공시 2 + "+1" = 4줄). 보유 목록은 한 행 높이가 고정이어야
    //   스캔이 된다. 그래서 **새 줄을 만들지 않고** 한 줄 안에서 넘치면 자른다.
    //   · nowrap + overflow hidden = 줄바꿈 금지, 넘치면 잘림
    //   · minWidth 0 = flex 자식이 줄어들 수 있게(안 주면 부모를 밀어낸다)
    //   · 공시는 1건만 + 나머지는 개수로. 제목 전문은 title 툴팁에 남긴다
    //   🚨 flexWrap:"wrap" 이나 marginTop 을 되돌리지 말 것 — 행 높이가 다시 흔들린다.
    const chip: CSSProperties = {
        fontSize: 10.5,
        fontWeight: 700,
        padding: "1px 6px",
        borderRadius: 999,
        whiteSpace: "nowrap",
        lineHeight: 1.45,
        flexShrink: 0,
    }
    const rest = evs.length - 1
    return (
        <span
            style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                minWidth: 0,
                overflow: "hidden",
                marginLeft: 6,
                verticalAlign: "middle",
            }}
        >
            {pct > 0 && (
                <span
                    style={{ ...chip, background: C.line, color: C.sub }}
                    title="국민연금 5% 이상 대량보유 공시 기준"
                >
                    연금 {pct.toFixed(1)}%
                </span>
            )}
            {evs.length > 0 && (
                <span
                    style={{
                        ...chip,
                        background: C.line,
                        color: C.sub,
                        flexShrink: 1,
                        minWidth: 0,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                    }}
                    title={evs
                        .map((e) => (e.d || "") + " " + (e.t || ""))
                        .join("\n")}
                >
                    {String(evs[0].t || "").slice(0, 14)}
                    {rest > 0 ? " +" + rest : ""}
                </span>
            )}
        </span>
    )
}

export default function PublicHoldingsTab(props: Props) {
    return <HoldingsWorkspace key={props.previewOnly ? "example" : "account"} {...props} />
}

function HoldingsWorkspace(props: Props) {
    const { apiBase, loginUrl, stockPath, usStockPath, dark, showReadingGuide = true, previewOnly = false, demoPath = "/nest-demo" } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const demoMode = !!previewOnly
    const isolated = onCanvas || demoMode
    // 실환율 — 하드코딩 1380 대체. 스냅샷 실패 시에만 폴백값이 쓰이고 라벨로 구분된다.
    const liveFxInfo = useAnFx(isolated)
    const fxInfo = demoMode ? NEST_DEMO_FX : liveFxInfo
    const [ccy, setCcy] = useAnCcy(isolated)

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    // 🚨 2026-07-27 목업 깜빡임 제거 — 초기 state 에 SAMPLE 을 넣으면 Framer 정적 HTML(SSG)에 그대로
    //   구워져 실사용자에게 "삼성전자 60주·NVIDIA 20주" 가 잠깐 보였다가 실제 값으로 바뀐다(PM 지적).
    //   캔버스 프리뷰는 마운트 후 useEffect 로만 주입 → 첫 페인트는 어떤 렌더타깃에서도 목업 0.
    const [rows, setRows] = useState<any[]>([])
    const [closes, setCloses] = useState<Record<string, number>>({}) // KR 종가(kr_close_latest) — 실시간 아님
    const [closeMeta, setCloseMeta] = useState<CloseSnapshot | null>(null)
    const [closeStatus, setCloseStatus] = useState<
        "idle" | "loading" | "ready" | "same" | "error"
    >("idle")
    const [closeError, setCloseError] = useState("")
    const [closeCheckedAt, setCloseCheckedAt] = useState(0)
    // 🚨 대주주 판정 **전용** 기준가 — 직전 사업연도 종료일 종가(소득세법 시행령 §157⑥).
    //   손익·평가액은 현재가를 쓴다. 이 둘을 섞으면 안 된다.
    const [basisPx, setBasisPx] = useState<Record<string, number>>({})
    const [basisAsOf, setBasisAsOf] = useState<string>("")
    const [closeAsOf, setCloseAsOf] = useState<string>(() => demoMode ? NEST_DEMO_AS_OF : "") // YYYYMMDD — 화면에 기준일 명시
    const [isDemo, setIsDemo] = useState(!demoMode)
    const FX = fxInfo.ok || isDemo || isolated ? fxInfo.rate : 0
    const [loading, setLoading] = useState<boolean>(() =>
        isolated ? false : !!getToken()
    )
    const [showAdd, setShowAdd] = useState(false)
    const [nestGuideOpen, setNestGuideOpen] = useState(false)
    const [busy, setBusy] = useState(false)
    const [themeDark, setThemeDark] = useState<boolean>(() =>
        isolated ? !!dark : readBodyDark()
    )
    const [view, setView] = useState<"holdings" | "mix" | "tax" | "trades">(
        "holdings"
    )
    const [toolsOpen, setToolsOpen] = useState(false)
    const [brokers, setBrokers] = useState<any[]>(() => demoMode ? NEST_DEMO_BROKERS.map((broker) => ({ ...broker })) : [])
    const [brokerIdx, setBrokerIdx] = useState(0)
    const [catFlow, setCatFlow] = useState<Record<string, number>>({}) // etf_flow 자산군 누적 흐름(사실, 분산 탭)
    const [targetKr, setTargetKr] = useState<number | null>(null) // 목표 국내 비중 %(사용자 설정, null=현재값)
    // 원가 기준 시장·업종·종목 노출. 보유·환율은 이 컴포넌트의 기존 상태를 재사용한다.
    const [sectorMap, setSectorMap] = useState<Record<string, string>>(() =>
        demoMode ? { ...SAMPLE_SECTORS, MSFT: "소프트웨어" } : isolated ? SAMPLE_SECTORS : {}
    )
    const [exposureMeta, setExposureMeta] = useState<any>(() =>
        isolated ? { count: 4, sector_mapped: 4 } : null
    )
    const [universe, setUniverse] = useState<any[]>(() => demoMode ? NEST_DEMO_CATALOG.map((row) => ({ ...row, type: "stock" })) : []) // 검색 유니버스(universe_search, KR+US)
    // 🚨 2026-08-21 — 둥지 브리핑. 보유 종목의 최근 공시 + 국민연금 대량보유.
    //   회원별 서버 발행이 아니라 **전역 색인 1개**를 받아 브라우저가 본인 티커만 고른다
    //   (회원 수와 무관하게 blob 캐시 1개). 인증·보유목록은 이미 위 /api/holdings 배선 재사용.
    //   RULE 6 = LLM 0(결정론적 조회) · RULE 7 = 공시 사실·지분율만, 점수·추천 0.
    const [nestIdx, setNestIdx] = useState<Record<string, any> | null>(null) // 티커→최근 공시
    const [npsMap, setNpsMap] = useState<Record<string, number> | null>(null) // 티커→국민연금 지분%
    const [q, setQ] = useState("") // 종목 검색어
    const [popErr, setPopErr] = useState<string>("") // 팝업 입력 오류 — 조용한 0 저장 방지
    const [pop, setPop] = useState<any>(null) // 추가/수정 팝업 {id?, ticker, name, market, shares, avg_cost}
    // 거래 기록(실현손익) — 본인 매매 이력. RULE 7 사실 기록, 순위·배지·공개 없음. /api/trades.
    const [tradeData, setTradeData] = useState<{ trades: any[]; summary: any }>(
        () => ({
            trades: [],
            summary: { by_ticker: [], total_realized_pnl: 0 },
        })
    )
    const [tradesLoading, setTradesLoading] = useState(false)
    // 캔버스 전용 목업 주입 — 마운트 후라 정적 HTML 에는 절대 포함되지 않음.
    //   라이브 미로그인 목업은 loadHoldings 의 토큰 부재 분기가 담당(로그아웃 전환도 그쪽이 처리).
    useEffect(() => {
        if (!isolated) return
        setRows(demoMode ? nestDemoRows() : SAMPLE)
        setTradeData(demoMode ? nestDemoTradeData(nestDemoTrades()) : { trades: SAMPLE_TRADES, summary: SAMPLE_TRADE_SUMMARY })
    }, [isolated])
    const [showTAdd, setShowTAdd] = useState(false) // 거래 추가 검색 패널
    const [tq, setTq] = useState("") // 거래 추가 종목 검색어
    const [tPop, setTPop] = useState<any>(null) // 거래 팝업 {id?, ticker, name, market, side, shares, price, traded_at}
    const [tBusy, setTBusy] = useState(false)
    const [tPopErr, setTPopErr] = useState("")
    const [loadErr, setLoadErr] = useState("")
    const [tradeErr, setTradeErr] = useState("")
    const [actionErr, setActionErr] = useState("")
    const [searchErr, setSearchErr] = useState("")
    const [searchRetry, setSearchRetry] = useState(0)
    const holdingSeq = useRef(0)
    const tradeSeq = useRef(0)
    const closeSeq = useRef(0)
    const closeLastAttempt = useRef(0)
    const closeMetaRef = useRef<CloseSnapshot | null>(null)
    const closeRequestRef = useRef<{
        controller: AbortController
        promise: Promise<void>
    } | null>(null)
    const mutationRef = useRef<string | null>(null)
    const currentAccount = useRef("")
    const [authRevision, setAuthRevision] = useState(0)

    const demoSequence = useRef(100)
    const resetDemo = () => {
        if (!demoMode) return
        demoSequence.current = 100
        setRows(nestDemoRows())
        setTradeData(nestDemoTradeData(nestDemoTrades()))
        setPop(null); setTPop(null); setShowAdd(false); setShowTAdd(false)
        setQ(""); setTq(""); setTargetKr(null); setBrokerIdx(0)
        setPopErr(""); setTPopErr(""); setActionErr(""); setTradeErr("")
        setView("holdings"); setToolsOpen(false); setCcy("USD")
    }

    // 🚨 라이브/프리뷰 = CSS 변수(Framer body[data-framer-theme] 직결).
    //   캔버스만 dark prop 정적 선택 — 캔버스는 Framer 가 body 속성을 안 줘 변수 해석이 안 된다.
    const isDark = onCanvas ? !!dark : themeDark
    const C: any = onCanvas ? (dark ? DARK : LIGHT) : CVAR
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

    useEffect(() => {
        if (isolated) return
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
    }, [isolated])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries)
                setW(
                    e.borderBoxSize?.[0]?.inlineSize ||
                        el.getBoundingClientRect().width
                )
        })
        try {
            ro.observe(el, { box: "border-box" })
        } catch {
            ro.observe(el)
        }
        return () => ro.disconnect()
    }, [])

    // 증권사 수수료가 결손이면 0으로 대신하지 않고 예상 비용 계산을 보류한다.
    useEffect(() => {
        if (isolated) return
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
    }, [isolated])

    // ETF 자산군 자금흐름 (분산 탭 — 보유 자산군에 패시브 자금 유입/유출 사실. /etf 와 동일 cumFlow).
    useEffect(() => {
        if (isolated) return
        let alive = true
        fetch(
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/etf_flow.json"
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
    }, [isolated])

    const loadHoldings = useCallback(() => {
        if (isolated) return
        const seq = ++holdingSeq.current
        const token = getToken()
        setLoadErr("")
        if (!token) {
            setIsDemo(true)
            setRows(SAMPLE)
            setLoading(false)
            return
        }
        setIsDemo(false)
        setLoading(true)
        const current = () => seq === holdingSeq.current && token === getToken()
        nestRequest(base + "/api/holdings", {
            headers: { Authorization: "Bearer " + token },
        })
            .then((d) => {
                const items = Array.isArray(d) ? d : d?.holdings
                if (!Array.isArray(items))
                    throw new Error("보유 목록 응답 형식을 확인할 수 없어요.")
                if (current()) setRows(items)
            })
            .catch((e) => {
                if (current()) setLoadErr(e.message)
            })
            .finally(() => {
                if (current()) setLoading(false)
            })
    }, [base, isolated])

    // Account changes invalidate pending reads and clear private UI immediately.
    // Same-account token refresh keeps the draft, but reloads BOTH datasets.
    useEffect(() => {
        if (isolated || typeof window === "undefined") return
        const onAuth = (event?: Event) => {
            if (
                event?.type === "storage" &&
                (event as StorageEvent).key &&
                (event as StorageEvent).key !== "verity_supabase_session"
            )
                return
            holdingSeq.current += 1
            tradeSeq.current += 1
            const key = accountKey()
            if (key !== currentAccount.current) {
                currentAccount.current = key
                setRows([])
                setTradeData({
                    trades: [],
                    summary: { by_ticker: [], total_realized_pnl: 0 },
                })
                setPop(null)
                setTPop(null)
                setShowAdd(false)
                setShowTAdd(false)
                setQ("")
                setTq("")
                setTargetKr(null)
                setPopErr("")
                setTPopErr("")
                setActionErr("")
                setTradeErr("")
                mutationRef.current = null
                setBusy(false)
                setTBusy(false)
            }
            setAuthRevision((n) => n + 1)
            loadHoldings()
        }
        onAuth()
        window.addEventListener("verity_auth_change", onAuth)
        window.addEventListener("storage", onAuth)
        return () => {
            holdingSeq.current += 1
            tradeSeq.current += 1
            window.removeEventListener("verity_auth_change", onAuth)
            window.removeEventListener("storage", onAuth)
        }
    }, [loadHoldings, isolated])

    // 검색 유니버스(KR+US ~8.9천, universe_search) — 보유/거래 추가 패널 열 때 1회 lazy 로드.
    useEffect(() => {
        if (
            isolated ||
            (!showAdd && !showTAdd && view !== "tax") ||
            universe.length
        )
            return
        let alive = true
        setSearchErr("")
        nestRequest(
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
        )
            .then((d) => {
                const a = Array.isArray(d) ? d : d?.stocks
                if (!Array.isArray(a) || !a.length)
                    throw new Error("검색 목록을 확인할 수 없어요.")
                if (alive) setUniverse(a)
            })
            .catch((e) => {
                if (alive) setSearchErr(e.message)
            })
        return () => {
            alive = false
        }
    }, [isolated, showAdd, showTAdd, view, universe.length, searchRetry])

    // 둥지 브리핑 재료 — 티커 색인(공시) + 국민연금 대량보유. 각 1회.
    // 🚨 기존 피드를 직접 받지 않는 이유 = 크기. us_disclosure_feed 4.1MB + KR 862KB 를
    //    브라우저가 받을 수 없어 서버에서 최근 3일·종목당 3건으로 압축한 색인을 쓴다(178KB).
    // 🚨 국민연금은 **5% 이상 대량보유 공시**가 원천이다. 색인에 없다 = "미보유"가 아니라
    //    "5% 미만"이다. 아래 렌더에서 그렇게 표기한다 — 오독 방지.
    useEffect(() => {
        if (isolated || isDemo) return
        let alive = true
        fetch(
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/nest_briefing_index.json"
        )
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive && d && d.tickers) setNestIdx(d.tickers)
            })
            .catch(() => {})
        fetch(
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/nps_holdings.json"
        )
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const arr = d && (d.holdings || d.full)
                if (!alive || !Array.isArray(arr)) return
                const m: Record<string, number> = {}
                for (const x of arr) {
                    const tk = x && x.ticker ? String(x.ticker) : ""
                    const p = Number(x && x.pct)
                    if (tk && p > 0 && isFinite(p))
                        m[tk] = Math.max(m[tk] || 0, p)
                }
                setNpsMap(m)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [isolated, isDemo])

    // 분산 탭 최초 진입 때 업종 분류 맵만 1회 로드한다. 별도 보유 API·환율 호출 금지.
    useEffect(() => {
        if (isolated || isDemo || view !== "mix" || exposureMeta) return
        let alive = true
        nestRequest(EXPOSURE_MAP_URL)
            .then((d) => {
                if (!alive) return
                const m: Record<string, string> = {}
                const stocks = d && d.stocks
                if (
                    !stocks ||
                    typeof stocks !== "object" ||
                    !Object.keys(stocks).length
                )
                    throw new Error("업종 분류 응답 오류")
                if (stocks && typeof stocks === "object") {
                    for (const key of Object.keys(stocks)) {
                        const item = stocks[key] || {}
                        const ticker = String(
                            key || item.ticker || ""
                        ).toUpperCase()
                        const sector = String(item.sector || "").trim()
                        if (ticker && sector) m[ticker] = sector
                    }
                }
                setSectorMap(m)
                setExposureMeta(
                    (d && d._meta) || { count: 0, sector_mapped: 0 }
                )
            })
            .catch(() => {
                if (alive)
                    setExposureMeta({ count: 0, sector_mapped: 0, error: true })
            })
        return () => {
            alive = false
        }
    }, [exposureMeta, isDemo, isolated, view])

    const refreshCloses = useCallback(
        (reason: "login" | "focus" | "visible" | "poll" | "manual", force = false): Promise<void> => {
            if (isolated || isDemo) return Promise.resolve()
            if (closeRequestRef.current) return closeRequestRef.current.promise
            const now = Date.now()
            if (!force && now - closeLastAttempt.current < CLOSE_REFRESH_THROTTLE_MS)
                return Promise.resolve()
            closeLastAttempt.current = now
            const seq = ++closeSeq.current
            const controller = new AbortController()
            let timedOut = false
            const timer = setTimeout(() => {
                timedOut = true
                controller.abort()
            }, CLOSE_REQUEST_TIMEOUT_MS)
            setCloseStatus("loading")
            setCloseError("")
            const promise = fetch(CLOSE_URL, {
                signal: controller.signal,
                cache: "no-store",
                headers: { Accept: "application/json" },
            })
                .then(async (response) => {
                    if (!response.ok)
                        throw new Error("종가 요청 실패 (HTTP " + response.status + ")")
                    const contentType = response.headers?.get?.("content-type") || ""
                    if (contentType && !contentType.toLowerCase().includes("json"))
                        throw new Error("종가 응답 형식을 확인할 수 없어요.")
                    return response.json()
                })
                .then((raw) => normalizeCloseSnapshot(raw, Date.now()))
                .then((snapshot) => {
                    if (seq !== closeSeq.current || controller.signal.aborted) return
                    const previous = closeMetaRef.current
                    if (
                        previous &&
                        (snapshot.asOf < previous.asOf ||
                            (snapshot.asOf === previous.asOf &&
                                Date.parse(snapshot.generatedAt) <
                                    Date.parse(previous.generatedAt)))
                    )
                        throw new Error(
                            "이전보다 오래된 종가 자료가 도착해 기존 값을 유지합니다."
                        )
                    const unchanged =
                        !!previous &&
                        previous.asOf === snapshot.asOf &&
                        previous.generatedAt === snapshot.generatedAt &&
                        previous.count === snapshot.count
                    setCloses(snapshot.prices)
                    closeMetaRef.current = snapshot
                    setCloseMeta(snapshot)
                    setCloseAsOf(snapshot.asOf)
                    setCloseCheckedAt(Date.now())
                    setCloseStatus(unchanged ? "same" : "ready")
                })
                .catch((error: any) => {
                    if (seq !== closeSeq.current) return
                    setCloseStatus("error")
                    setCloseCheckedAt(Date.now())
                    setCloseError(
                        timedOut
                            ? "종가 요청 시간이 초과됐어요."
                            : (error && error.message) ||
                            "종가 자료를 다시 확인하지 못했어요."
                    )
                })
                .finally(() => {
                    clearTimeout(timer)
                    if (closeRequestRef.current?.controller === controller)
                        closeRequestRef.current = null
                })
            closeRequestRef.current = { controller, promise }
            return promise
        },
        [isDemo, isolated]
    )

    useEffect(() => {
        if (isolated || isDemo) return
        void refreshCloses("login")
        const onFocus = () => void refreshCloses("focus")
        const onVisible = () => {
            if (document.visibilityState === "visible")
                void refreshCloses("visible")
        }
        const poll = window.setInterval(() => {
            if (document.visibilityState === "visible")
                void refreshCloses("poll")
        }, CLOSE_VISIBLE_POLL_MS)
        window.addEventListener("focus", onFocus)
        document.addEventListener("visibilitychange", onVisible)
        return () => {
            window.clearInterval(poll)
            window.removeEventListener("focus", onFocus)
            document.removeEventListener("visibilitychange", onVisible)
        }
    }, [authRevision, isDemo, isolated, refreshCloses])

    useEffect(() => {
        if (!isolated && !isDemo) return
        closeSeq.current += 1
        closeRequestRef.current?.controller.abort()
        closeRequestRef.current = null
    }, [isDemo, isolated])

    useEffect(
        () => () => {
            closeSeq.current += 1
            closeRequestRef.current?.controller.abort()
            closeRequestRef.current = null
        },
        []
    )

    /* 평가 기준가 — kr_close_latest.json (금융위 공공데이터 직전 거래일 종가, 전 종목 동일 기준일).
       🚨 되돌리지 말 것 (2026-07-31 수익률 부호 역전 사고) — 옛 소스 = stock_flow_5d.json 의
       마지막 close. 그 파일은 시총순 회전 수집(하루 500종목)이라 **종목마다 종가 날짜가 제각각**
       (어제~5주 전). 실측: 1,801종목 중 71% 가 직전 거래일 종가와 불일치, 23% 는 10%+ 괴리
       → 하락 종목이 플러스로 표시됐다. flow_5d 로 되돌리면 같은 사고가 재발한다.
       커버리지 밖(미국·ETF·거래정지) = 값을 지어내지 않고 "시세 없음" 표기 + 손익 합계 제외. */
    useEffect(() => {
        if (isolated || isDemo) return
        let alive = true
        // 대주주 판정 기준가 — 실패해도 손익 표시는 멀쩡하다(판정만 보류)
        fetch(
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/kr_prior_fy_close.json"
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
                setBasisPx(m)
                setBasisAsOf(String((d._meta && d._meta.requested_date) || ""))
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [isDemo, isolated])

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
                    String(x.name_ko || "")
                        .toLowerCase()
                        .includes(s)
            )
            .sort((a: any, b: any) => rk(a) - rk(b))
            .slice(0, 8)
            .map((x: any) => ({ ...x, _held: held.has(String(x.ticker)) }))
    }, [q, universe, rows])

    // ★ 클릭 = 추가 팝업(수량·평단 수동 입력) / 리스트 수정 = 기존값 프리필 팝업
    const openAdd = (x: any) => {
        setPopErr("")
        setActionErr("")
        if (!supportedAsset(x)) {
            setActionErr(
                "직접 원자재는 계약 단위가 달라 둥지 기록을 아직 지원하지 않아요. 주식·ETF·ADR을 선택해 주세요."
            )
            return
        }
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
        setPopErr("")
        setActionErr("")
        setPop({
            id: h.id,
            ticker: h.ticker,
            name: h.name || "",
            market: h.market || "kr",
            shares: String(h.shares ?? ""),
            avg_cost: String(h.avg_cost ?? ""),
        })
    }
    // 🚨 2026-08-22 — 쉼표 입력이 조용히 0 으로 저장되던 것. PM 실사고:
    //   "하이닉스 10주를 2,000,000원에 샀다고 올렸는데 자동으로 1,690,000원으로 되더라".
    //   Number("2,000,000") = NaN → `|| 0` 이 0 으로 만들고, 서버 float() 도 ValueError →
    //   default 0. avg_cost=0 이면 평가 화면이 현재가로 대체 표시해(1344행) **바뀐 것처럼
    //   보인다**. 실제로는 입력이 버려진 것이다. DB 실측 = 삼성전자·하이닉스 둘 다 0.0.
    //   🚨 에러가 안 뜨는 게 핵심 — 서버가 0 을 정상값으로 받는다(avg_cost >= 0 통과).
    //   되돌리지 말 것: 정규화 + **파싱 실패 시 저장 차단**(조용한 0 금지).
    const parseNum = (v: any): number | null => {
        const t = String(v == null ? "" : v)
            .replace(/[,\s₩$원]/g, "")
            .trim()
        if (!t) return null
        const n = Number(t)
        return isFinite(n) && n >= 0 ? n : null
    }
    const savePop = useCallback(() => {
        const token = demoMode ? "" : getToken()
        if ((!demoMode && !token) || !pop || mutationRef.current) return
        const sh = parseNum(pop.shares)
        const av = parseNum(pop.avg_cost)
        if (sh === null || av === null || sh <= 0 || av <= 0) {
            setPopErr(
                "수량과 평단을 0보다 큰 숫자로 입력해 주세요. 쉼표는 사용할 수 있어요."
            )
            return
        }
        setPopErr("")
        if (demoMode) {
            const item = { ...pop, id: pop.id || "demo-h-" + ++demoSequence.current, shares: sh, avg_cost: av, price: NEST_DEMO_CATALOG.find((row) => row.ticker === pop.ticker)?.price || 0 }
            setRows((current) => pop.id ? current.map((row) => row.id === pop.id ? item : row) : [...current, item])
            setPop(null)
            return
        }
        mutationRef.current = token
        setBusy(true)
        const isEdit = !!pop.id
        const body = isEdit
            ? {
                  id: pop.id,
                  shares: sh,
                  avg_cost: av,
              }
            : {
                  ticker: String(pop.ticker).trim(),
                  name: String(pop.name).trim(),
                  market: pop.market,
                  shares: sh,
                  avg_cost: av,
              }
        nestRequest(base + "/api/holdings", {
            method: isEdit ? "PATCH" : "POST",
            headers: {
                Authorization: "Bearer " + token,
                "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
        })
            .then(() => {
                if (token !== getToken()) return
                setPop(null)
                loadHoldings()
            })
            .catch((e) => {
                if (token === getToken()) setPopErr(e.message)
            })
            .finally(() => {
                if (mutationRef.current === token) {
                    mutationRef.current = null
                    setBusy(false)
                }
            })
    }, [pop, base, loadHoldings, demoMode])

    const delHolding = useCallback(
        (id: string) => {
            const token = demoMode ? "" : getToken()
            if ((!demoMode && !token) || !id || mutationRef.current) return
            if (
                !window.confirm(
                    "이 보유종목을 삭제할까요? 거래 기록은 유지됩니다."
                )
            )
                return
            if (demoMode) {
                setRows((current) => current.filter((row) => row.id !== id))
                return
            }
            mutationRef.current = token
            setActionErr("")
            nestRequest(base + "/api/holdings", {
                method: "DELETE",
                headers: {
                    Authorization: "Bearer " + token,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ id }),
            })
                .then(() => {
                    if (token === getToken()) loadHoldings()
                })
                .catch((e) => {
                    if (token === getToken()) setActionErr(e.message)
                })
                .finally(() => {
                    if (mutationRef.current === token)
                        mutationRef.current = null
                })
        },
        [base, loadHoldings, demoMode]
    )

    const loadTrades = useCallback(() => {
        if (isolated) return
        const seq = ++tradeSeq.current
        const token = getToken()
        setTradeErr("")
        if (!token) {
            setTradesLoading(false)
            setTradeData({
                trades: SAMPLE_TRADES,
                summary: SAMPLE_TRADE_SUMMARY,
            })
            return
        }
        setTradesLoading(true)
        const current = () => seq === tradeSeq.current && token === getToken()
        nestRequest(base + "/api/trades", {
            headers: { Authorization: "Bearer " + token },
        })
            .then((d) => {
                if (
                    !Array.isArray(d?.trades) ||
                    !Array.isArray(d?.summary?.by_ticker)
                )
                    throw new Error("거래 목록 응답 형식을 확인할 수 없어요.")
                if (current())
                    setTradeData({ trades: d.trades, summary: d.summary })
            })
            .catch((e) => {
                if (current()) setTradeErr(e.message)
            })
            .finally(() => {
                if (current()) setTradesLoading(false)
            })
    }, [base, isolated])

    useEffect(() => {
        if (isolated) return
        if (view === "trades" || !getToken()) loadTrades()
    }, [view, loadTrades, authRevision, isolated])

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
                    String(x.name_ko || "")
                        .toLowerCase()
                        .includes(s)
            )
            .sort((a: any, b: any) => rk(a) - rk(b))
            .slice(0, 8)
    }, [tq, universe])

    const openTAdd = (x: any) => {
        setTPopErr("")
        setActionErr("")
        if (!supportedAsset(x)) {
            setActionErr(
                "직접 원자재 거래는 아직 지원하지 않아요. 주식·ETF·ADR을 선택해 주세요."
            )
            return
        }
        setTPop({
            request_id:
                typeof crypto !== "undefined" && crypto.randomUUID
                    ? crypto.randomUUID()
                    : undefined,
            ticker: String(x.ticker),
            name: x.name || "",
            market: String(x.market || "kr").toLowerCase(),
            side: "buy",
            shares: "",
            price: "",
            traded_at: demoMode ? "2026-06-18" : todayISO(),
        })
        setTq("")
        setShowTAdd(false)
    }
    const openTEdit = (t: any) => {
        setTPopErr("")
        setActionErr("")
        setTPop({
            id: t.id,
            ticker: t.ticker,
            name: t.name || "",
            market: t.market || "kr",
            side: t.side || "buy",
            shares: String(t.shares ?? ""),
            price: String(t.price ?? ""),
            traded_at: t.traded_at || (demoMode ? "2026-06-18" : todayISO()),
        })
    }
    const saveTPop = useCallback(() => {
        const token = demoMode ? "" : getToken()
        if ((!demoMode && !token) || !tPop || mutationRef.current) return
        const sh = parseNum(tPop.shares)
        const pr = parseNum(tPop.price)
        if (sh === null || pr === null || sh <= 0 || pr <= 0) {
            setTPopErr(
                "수량과 체결가를 0보다 큰 숫자로 입력해 주세요. 쉼표는 사용할 수 있어요."
            )
            return
        }
        if (
            !/^\d{4}-\d{2}-\d{2}$/.test(tPop.traded_at || "") ||
            !Number.isFinite(Date.parse(tPop.traded_at)) ||
            new Date(tPop.traded_at).toISOString().slice(0, 10) !==
                tPop.traded_at
        ) {
            setTPopErr("거래 날짜를 확인해 주세요.")
            return
        }
        setTPopErr("")
        if (demoMode) {
            const item = { ...tPop, id: tPop.id || "demo-t-" + ++demoSequence.current, shares: sh, price: pr }
            setTradeData((current) => nestDemoTradeData(tPop.id ? current.trades.map((trade) => trade.id === tPop.id ? item : trade) : [...current.trades, item]))
            setTPop(null)
            return
        }
        mutationRef.current = token
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
                  request_id: tPop.request_id,
                  ticker: String(tPop.ticker).trim(),
                  name: String(tPop.name).trim(),
                  market: tPop.market,
                  side: tPop.side,
                  shares: sh,
                  price: pr,
                  traded_at: tPop.traded_at,
              }
        nestRequest(base + "/api/trades", {
            method: isEdit ? "PATCH" : "POST",
            headers: {
                Authorization: "Bearer " + token,
                "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
        })
            .then(() => {
                if (token !== getToken()) return
                setTPop(null)
                loadTrades()
            })
            .catch((e) => {
                if (token === getToken()) setTPopErr(e.message)
            })
            .finally(() => {
                if (mutationRef.current === token) {
                    mutationRef.current = null
                    setTBusy(false)
                }
            })
    }, [tPop, base, loadTrades, demoMode])
    const delTrade = useCallback(
        (id: string) => {
            const token = demoMode ? "" : getToken()
            if ((!demoMode && !token) || !id || mutationRef.current) return
            if (
                !window.confirm(
                    "이 거래 기록을 삭제할까요? 실현손익이 다시 계산되며 보유목록은 바뀌지 않습니다."
                )
            )
                return
            if (demoMode) {
                setTradeData((current) => nestDemoTradeData(current.trades.filter((trade) => trade.id !== id)))
                return
            }
            mutationRef.current = token
            setActionErr("")
            nestRequest(base + "/api/trades", {
                method: "DELETE",
                headers: {
                    Authorization: "Bearer " + token,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ id }),
            })
                .then(() => {
                    if (token === getToken()) loadTrades()
                })
                .catch((e) => {
                    if (token === getToken()) setActionErr(e.message)
                })
                .finally(() => {
                    if (mutationRef.current === token)
                        mutationRef.current = null
                })
        },
        [base, loadTrades, demoMode]
    )

    const narrow = w > 0 && w < 560

    /* 평가 — 기준가 없는 종목(미국·ETF·거래정지)은 0% 로 위장하지 않는다(_priced=false).
       옛 코드는 종가가 없으면 평단을 현재가로 써서 "정확히 0.0%" 를 표시했다 — 사용자가 손익 0
       으로 오독한다. 지금은 손익 "—" + 합계 제외, 평가금액만 매입가 기준으로 잡아 비중을 유지. */
    const evald = rows.map((h) => {
        const us = h.market === "us" || h.currency === "USD"
        const supported = supportedAsset(h)
        const fx = !supported
            ? 0
            : us
              ? fxInfo.ok || isDemo || isolated
                  ? FX
                  : 0
              : 1
        const shares = Number(h.shares) || 0
        const px = Number(closes[String(h.ticker)]) || 0
        const seeded = Number(h.price) || 0 // SAMPLE 미리보기 전용 시세
        const cur = px > 0 ? px : seeded > 0 ? seeded : Number(h.avg_cost) || 0
        const priced =
            supported &&
            shares > 0 &&
            Number(h.avg_cost) > 0 &&
            fx > 0 &&
            (px > 0 || ((isDemo || isolated) && seeded > 0))
        const val = shares * cur * fx
        const cost = shares * (Number(h.avg_cost) || 0) * fx
        const pl = priced ? val - cost : 0
        const plPct = priced && cost > 0 ? (pl / cost) * 100 : 0
        return {
            ...h,
            _us: us,
            _supported: supported,
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
    const totalPlPct = totalCost > 0 ? (totalPl / totalCost) * 100 : NaN
    const withWeight = evald
        .map((h) => ({
            ...h,
            _weight: totalVal > 0 ? (h._val / totalVal) * 100 : 0,
        }))
        .sort((a, b) => b._val - a._val)
    const plColor = (v: number) => (v > 0 ? C.up : v < 0 ? C.down : C.faint)

    // ── 예상 세금 + 수수료 (🚨 **전량 매도** 가정) ──
    //   2026-08-22 검증: 손계산 대조 통과(US 1,000만 → (1,000만−250만)×22% = 165만 ·
    //   4억 이익 → 공제 후 과세표준 × 22% · 손실 시 과세표준 0).
    //   🚨 다만 usGainSum 은 **보유 전 종목 손익의 단순 합**이다. 실제 양도세는 그 해에
    //   **실현한 것만** 통산하므로, 일부만 팔면 미실현 손실이 차감되지 않아 실제 세금이
    //   더 크다. 계산을 바꾸지 않고 **전제를 화면에 명시**한다(헤더 "전량 매도" + 하단 설명).
    //   숫자를 조용히 낙관 쪽으로 보여주는 게 이 화면에서 가장 위험하다.
    const krRows = evald.filter((h) => !h._us)
    const usRows = evald.filter((h) => h._us)
    const krProceeds = krRows.reduce((a, b) => a + b._val, 0)
    const usProceeds = usRows.reduce((a, b) => a + b._val, 0)
    const krTxnTax = krProceeds * TAX.KR_TXN
    const usGainSum = usRows.reduce((a, b) => a + b._pl, 0)
    const usTaxable = Math.max(0, usGainSum - TAX.US_DEDUCT)
    const usCgt = usTaxable * TAX.US_CGT
    const broker = brokers[brokerIdx] || null
    const krCommission = krRows.length
        ? krProceeds * parseFee(broker && broker.domestic_fee)
        : 0
    const usCommission = usRows.length
        ? usProceeds * parseFee(broker && broker.overseas_fee)
        : 0
    const totalTax = krTxnTax + usCgt
    const totalCommission = krCommission + usCommission
    // 🚨 대주주 판정은 **현재가가 아니라 직전 사업연도 종료일 종가**로 한다
    //   (소득세법 시행령 §157⑥). 종전에는 _val(현재가 기준)로 재고 있었다 —
    //   실측 2026-08-22 삼성전자 기준가 119,900 vs 현재 271,000(+126%)로 2배 넘게 부풀어
    //   실제 기준의 절반 이하 보유액에서도 대주주로 표시됐다.
    //   🚨 기준가를 못 받았으면 **판정하지 않는다**(현재가로 대체 금지 — 그게 원래 결함이다).
    // Current quantity times prior-FY close is a screening approximation only.
    // Midyear acquisition concerns the ownership-ratio test; average cost is not a tax basis test.
    // Source: NTS nttSn=1353905 (2026); historical quantity/related parties are not collected here.
    const majorPath = (h: any): "" | "basis" => {
        const shares = Number(h.shares) || 0
        const b = Number(basisPx[String(h.ticker)]) || 0
        return shares > 0 && b > 0 && shares * b >= TAX.KR_MAJOR_AMT
            ? "basis"
            : ""
    }
    const krMajorRows = krRows.filter((h) => majorPath(h) !== "")
    const krMajorUnknown = krRows.filter(
        (h) => !(Number(basisPx[String(h.ticker)]) > 0)
    ).length
    const universeByTicker = new Map(
        universe.map((x) => [String(x.ticker).toUpperCase(), x])
    )
    const taxExcluded = evald.filter((h) => {
        if (isDemo || isolated) return !h._supported
        const meta = universeByTicker.get(String(h.ticker).toUpperCase())
        // Fund/ETN tax needs product classification and tax-base NAV, not the stock formula.
        return (
            !h._supported ||
            !meta ||
            ["etf", "etn", "fund", "commodity"].includes(
                String(meta.type || "").toLowerCase()
            )
        )
    })
    const taxBlocked =
        !!loadErr ||
        loading ||
        !evald.length ||
        unpricedN > 0 ||
        taxExcluded.length > 0 ||
        krMajorRows.length > 0 ||
        (!isDemo && !isolated && usRows.length > 0 && !fxInfo.ok) ||
        !broker ||
        (krRows.length > 0 && !isFinite(parseFee(broker?.domestic_fee))) ||
        (usRows.length > 0 && !isFinite(parseFee(broker?.overseas_fee)))
    const closeFreshness = closeMeta
        ? describeCloseFreshness(closeMeta, closeCheckedAt || Date.now())
        : null

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

    // 입력 원가 기준 노출 — 현재가·목표 비중을 섞지 않는다.
    const exposureModel = useMemo(() => {
        const valued: any[] = []
        const excluded: string[] = []
        let sectorMapped = 0
        for (const holding of rows) {
            const ticker = String(
                holding && holding.ticker ? holding.ticker : ""
            )
                .trim()
                .toUpperCase()
            const shares = Number(holding && holding.shares)
            const avgCost = Number(holding && holding.avg_cost)
            const market = String(
                (holding && holding.market) || ""
            ).toLowerCase()
            const us =
                market === "us" ||
                String((holding && holding.currency) || "").toUpperCase() ===
                    "USD" ||
                /^[A-Z.-]+$/.test(ticker)
            const factor = us ? (isolated || fxInfo.ok ? FX : 0) : 1
            const sector = sectorMap[ticker] || ""
            if (sector) sectorMapped += 1
            if (
                !supportedAsset(holding) ||
                !(shares > 0) ||
                !(avgCost > 0) ||
                !(factor > 0)
            ) {
                excluded.push(
                    String((holding && holding.name) || ticker || "이름 없음")
                )
                continue
            }
            valued.push({
                ...holding,
                ticker,
                marketLabel: us ? "미국" : "한국",
                sector: sector || "업종 미분류",
                value: shares * avgCost * factor,
            })
        }
        return {
            valued,
            excluded,
            total: valued.reduce((sum, row) => sum + row.value, 0),
            markets: groupExposure(valued, (row) => row.marketLabel),
            sectors: groupExposure(valued, (row) => row.sector),
            tickers: groupExposure(
                valued,
                (row) => `${row.name || row.ticker} · ${row.ticker}`
            ),
            sectorMapped,
        }
    }, [FX, fxInfo.ok, isolated, rows, sectorMap])

    // ── 거래 기록(실현손익) 파생 — 종목별 실현손익은 네이티브 통화, 합계만 FX 환산(holdings 관행). ──
    const tradeInputsValid = (tradeData.trades || []).every(
        (t) => Number(t.shares) > 0 && Number(t.price) > 0 && supportedAsset(t)
    )
    const tByTicker: any[] =
        tradeInputsValid &&
        tradeData.summary &&
        Array.isArray(tradeData.summary.by_ticker)
            ? tradeData.summary.by_ticker
            : []
    const realizedKrw =
        !tradeInputsValid ||
        (!isolated &&
            !isDemo &&
            !fxInfo.ok &&
            tByTicker.some((t) => t.market === "us"))
            ? NaN
            : tByTicker.reduce(
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
    // Theme-specific SVG URLs preserve the rounded chevron without JS theme detection.
    // Keep full URI encoding and no-repeat sizing to avoid Safari tiling.
    const selStyle: CSSProperties = {
        ...inputStyle,
        cursor: "pointer",
        paddingRight: 30,
        border: "none",
        appearance: "none",
        WebkitAppearance: "none",
        MozAppearance: "none",
        backgroundImage: "var(--an-hld-select-chevron)",
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 11px center",
        backgroundSize: "10px 6px",
    }
    const wrap: CSSProperties = {
        width: "100%",
        maxWidth: 1000,
        margin: "0 auto",
        height: "100%",
        maxHeight: "100%",
        overflowY: "auto",
        overflowX: "hidden",
        background: "transparent",
        fontFamily: FONT,
        padding: "8px clamp(14px, 2vw, 20px) 20px",
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
                            // 🚨 좌우 폭 고정 — 되돌리지 말 것 (2026-08-09 PM, 거장 토글과 동일 규율).
                            //   "$ 달러" / "₩ 원화" 는 글자수가 같아도 기호 폭이 달라 알약이 흔들린다.
                            width: 56,
                            padding: "4px 0",
                            textAlign: "center",
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
                미국 종목 표기 · {demoMode ? "예시 환율" : "환율"} {Math.round(FX).toLocaleString()}원/$
                {fxInfo.ok
                    ? fxInfo.asOf
                        ? " (" +
                          String(fxInfo.asOf).slice(5, 16).replace("T", " ") +
                          " 기준)"
                        : ""
                    : " (환율 미확인 — 실제 원화 계산 제외)"}
            </span>
        </div>
    )

    const Tabs = (
        <div style={{ marginTop: 12 }}>
            <div
                role="group"
                aria-label="둥지 보기"
                style={{ display: "flex", gap: 4, padding: 4, borderRadius: 14, background: "var(--nest-stack)" }}
            >
                <button
                    type="button"
                    className="an-hld-nav-button"
                    aria-pressed={view === "holdings"}
                    onClick={() => setView("holdings")}
                    style={{ flex: 1 }}
                >
                    보유종목
                </button>
                <a
                    className="an-hld-nav-button"
                    href="/mindmap"
                    aria-label="마인드맵 베타 (새 탭에서 열림)"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ flex: 1 }}
                >
                    마인드맵 베타
                </a>
                <button
                    type="button"
                    className="an-hld-nav-button"
                    aria-expanded={toolsOpen}
                    aria-controls="nest-secondary-tools"
                    onClick={() => setToolsOpen((value) => !value)}
                    style={{ flex: 1 }}
                >
                    <span>
                        보조 도구{view !== "holdings" ? " · " + ({ mix: "분산", trades: "거래 기록", tax: "예상 세금" } as const)[view] : ""}
                    </span>
                    <span aria-hidden="true" style={{ fontSize: 11, fontWeight: 700 }}>
                        {toolsOpen ? "접기" : "펼치기"}
                    </span>
                </button>
            </div>
            <div id="nest-secondary-tools" role="group" aria-label="보조 도구 선택" hidden={!toolsOpen}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 4, marginTop: 6, padding: 4, borderRadius: 14, background: "var(--nest-stack)" }}>
                    {([
                        ["mix", "분산"],
                        ["trades", "거래 기록"],
                        ["tax", "예상 세금"],
                    ] as const).map(([key, label]) => (
                        <button
                            key={key}
                            type="button"
                            className="an-hld-nav-button"
                            aria-pressed={view === key}
                            onClick={() => setView(key)}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    )

    return (
        <div className="an-hld-simple" data-nest-dark={isDark} data-nest-canvas={onCanvas} ref={rootRef} style={wrap}>
            <style>{AN_PALETTE + NEST_NAV_CSS}</style>
            {demoMode ? (
                <section aria-label="둥지 예시 체험" style={{ ...cardS, background: "var(--nest-stack)", marginTop: 0, marginBottom: 16 }}>
                    <div style={{ fontSize: 12, fontWeight: 800, color: C.vg }}>예시로 체험 중</div>
                    <p style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.6, color: C.sub, margin: "6px 0 0" }}>
                        수량·평단을 바꾸고 거래를 추가해 보세요. 이 화면의 종목·가격·기준일·환율·수수료는 설명용 고정 예시이며 실제 보유자료·최신 시세가 아닙니다. 변경은 이 화면에서만 유지되고 새로고침하면 초기화돼요.
                    </p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                        <a className="an-hld-nav-button" href="/nest">내 둥지로 돌아가기</a>
                        <button type="button" className="an-hld-nav-button" onClick={resetDemo}>예시 초기화</button>
                    </div>
                </section>
            ) : (
                <a className="an-hld-nav-button" href={demoPath || "/nest-demo"} style={{ marginBottom: 8 }}>예시로 체험하기</a>
            )}
            {(loadErr || tradeErr || actionErr || searchErr) && (
                <div
                    role="alert"
                    style={{
                        ...cardS,
                        color: C.danger,
                        fontWeight: 600,
                        lineHeight: 1.6,
                    }}
                >
                    {loadErr || tradeErr || actionErr || searchErr}
                    {(loadErr || tradeErr) && (
                        <div>
                            조회 실패는 보유·거래가 0건이라는 뜻이 아니에요.
                            아래 값은 최신으로 확인되지 않았습니다.
                        </div>
                    )}
                    <button
                        style={{
                            ...inputStyle,
                            border: "none",
                            fontWeight: 700,
                            marginTop: 8,
                        }}
                        onClick={() => {
                            setActionErr("")
                            loadHoldings()
                            loadTrades()
                            setSearchRetry((n) => n + 1)
                        }}
                    >
                        다시 확인
                    </button>
                    {(loadErr || tradeErr) && (
                        <a
                            href={loginUrl || "/login?next=/nest"}
                            style={{ marginLeft: 12, color: C.vg }}
                        >
                            다시 로그인
                        </a>
                    )}
                </div>
            )}
            {!isDemo && !isolated && (
                <div
                    role="status"
                    aria-live="polite"
                    aria-busy={closeStatus === "loading"}
                    style={{
                        ...cardS,
                        marginBottom: 24,
                        color:
                            closeError || closeFreshness?.delayed
                                ? C.warn
                                : C.sub,
                        fontWeight: 600,
                        lineHeight: 1.55,
                    }}
                >
                    <div style={{ color: C.ink, fontWeight: 700 }}>
                        가격 출처 · 금융위원회 주식시세정보 · 일별 종가
                    </div>
                    <div>
                        {closeMeta
                            ? `기준일 ${fmtAsOf(closeMeta.asOf)} · 생성 ${fmtCloseGeneratedAt(closeMeta.generatedAt)} · ${closeFreshness?.label} · 실시간 아님`
                            : closeStatus === "loading"
                              ? "기준일과 생성 시각을 확인하고 있어요."
                              : "확인된 종가 자료가 없어 손익 계산을 보류합니다."}
                    </div>
                    {closeCheckedAt > 0 && (
                        <div>
                            브라우저 확인 {fmtCloseGeneratedAt(new Date(closeCheckedAt).toISOString())}
                            {closeStatus === "same"
                                ? " · 같은 기준일의 자료를 다시 확인했어요."
                                : ""}
                        </div>
                    )}
                    {closeError && (
                        <div role="alert">
                            {closeError}{" "}
                            {closeMeta
                                ? `기존 ${fmtAsOf(closeMeta.asOf)} 종가를 유지합니다.`
                                : "없는 값을 0으로 계산하지 않습니다."}
                        </div>
                    )}
                    <button
                        type="button"
                        disabled={closeStatus === "loading"}
                        onClick={() => void refreshCloses("manual", true)}
                        style={{
                            ...inputStyle,
                            border: "none",
                            fontWeight: 700,
                            marginTop: 8,
                            opacity: closeStatus === "loading" ? 0.65 : 1,
                            cursor:
                                closeStatus === "loading" ? "wait" : "pointer",
                        }}
                    >
                        {closeStatus === "loading"
                            ? "종가 확인 중"
                            : "종가 새로고침"}
                    </button>
                </div>
            )}
            {view === "trades" && (
                <div
                    style={{
                        ...cardS,
                        marginBottom: 24,
                        fontWeight: 600,
                        color: C.sub,
                        lineHeight: 1.6,
                    }}
                >
                    거래 기록과 보유목록은 별도로 저장돼요. 매수·매도를 기록해도
                    보유 수량은 자동으로 바뀌지 않아요.
                    {!tradeInputsValid && (
                        <div role="alert" style={{ color: C.warn }}>
                            이전 기록에 체결가·수량이 0이거나 지원하지 않는
                            자산이 있어 손익 합산을 보류했어요. 아래 기록을
                            수정해 주세요.
                        </div>
                    )}
                    {tradeData.summary?.unmatched_sell_shares > 0 && (
                        <div role="status" style={{ color: C.warn }}>
                            매수 기록보다 많은 매도가 있어 손익 일부를 계산하지
                            못했어요. 이전 매수 기록을 확인해 주세요.
                        </div>
                    )}
                </div>
            )}
            {view === "mix" && exposureMeta?.error && (
                <div role="alert" style={{ ...cardS, color: C.sub }}>
                    업종 분류를 불러오지 못했어요. 보유목록은 유지됩니다.{" "}
                    <button
                        style={{
                            ...inputStyle,
                            border: "none",
                            fontWeight: 700,
                        }}
                        onClick={() => setExposureMeta(null)}
                    >
                        다시 불러오기
                    </button>
                </div>
            )}
            {evald.some((h) => !h._supported) && (
                <div role="status" style={{ ...cardS, color: C.warn }}>
                    직접 원자재 등 지원하지 않는 자산은 평가·분산·세금 합계에서
                    제외했어요. 기존 기록은 보존되며 삭제할 수 있습니다.
                </div>
            )}
            {!fxInfo.ok && !isDemo && !isolated && usRows.length > 0 && (
                <div role="status" style={{ ...cardS, color: C.warn }}>
                    환율을 확인하지 못해 해외 자산의 원화 평가와 세금 계산을
                    보류했어요.
                </div>
            )}
            {/* 추가/수정 팝업 — ★(추가) 또는 행 '수정' 클릭 시. 수량·평단 수동 입력 → POST(신규)/PATCH(수정). */}
            {pop && (
                <div
                    onClick={() => {
                        if (!mutationRef.current) setPop(null)
                    }}
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
                            maxHeight: "85dvh",
                            overflowY: "auto",
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
                            <Logo offline={demoMode}
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
                        {popErr && (
                            <div
                                role="alert"
                                style={{
                                    color: C.danger,
                                    fontWeight: 600,
                                    fontSize: 13,
                                    marginTop: 10,
                                }}
                            >
                                {popErr}
                            </div>
                        )}
                        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                            <button
                                onClick={() => {
                                    if (!mutationRef.current) setPop(null)
                                }}
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
                    onClick={() => {
                        if (!mutationRef.current) setTPop(null)
                    }}
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
                            maxHeight: "85dvh",
                            overflowY: "auto",
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
                            <Logo offline={demoMode}
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
                        {tPopErr && (
                            <div
                                role="alert"
                                style={{
                                    color: C.danger,
                                    fontWeight: 600,
                                    fontSize: 13,
                                    marginTop: 10,
                                }}
                            >
                                {tPopErr}
                            </div>
                        )}
                        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                            <button
                                onClick={() => {
                                    if (!mutationRef.current) setTPop(null)
                                }}
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
                            fontSize: 18,
                            fontWeight: 800,
                            letterSpacing: "-0.4px",
                            lineHeight: 1.3,
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

            {showReadingGuide ? (
            <section
                style={{
                    background: C.card,
                    borderRadius: 16,
                    padding: narrow ? "14px 15px" : "16px 17px",
                    marginTop: 12,
                    boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                }}
            >
                <button
                    type="button"
                    onClick={() => setNestGuideOpen((value) => !value)}
                    aria-expanded={nestGuideOpen}
                    aria-controls="nest-reading-guide"
                    style={{
                        width: "100%",
                        border: "none",
                        padding: 0,
                        background: "transparent",
                        color: C.ink,
                        fontFamily: FONT,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 12,
                        textAlign: "left",
                    }}
                >
                    <span style={{ minWidth: 0 }}>
                        <span
                            style={{
                                display: "block",
                                color: C.vg,
                                fontSize: 10.5,
                                fontWeight: 800,
                            }}
                        >
                            보유 맥락 읽기
                        </span>
                        <span
                            style={{
                                display: "block",
                                marginTop: 3,
                                fontSize: 15,
                                fontWeight: 800,
                            }}
                        >
                            자본 규모보다 먼저 확인할 순서
                        </span>
                    </span>
                    <span
                        style={{
                            flexShrink: 0,
                            color: C.vg,
                            background: C.vgS,
                            borderRadius: 999,
                            padding: "6px 9px",
                            fontSize: 10.5,
                            fontWeight: 800,
                        }}
                    >
                        {nestGuideOpen ? "접기" : "처음이라면 · 펼치기"}
                    </span>
                </button>
                {nestGuideOpen ? (
                    <div id="nest-reading-guide">
                        <p
                            style={{
                                margin: "12px 0 0",
                                color: C.sub,
                                fontSize: 11.5,
                                lineHeight: 1.65,
                            }}
                        >
                            자본 규모는 무엇을 살지보다 확인 순서를 바꿉니다.
                            경험이 적을수록 평가손익보다 입력값·기준일·분모를
                            먼저 확인하세요.
                        </p>
                        <ol
                            style={{
                                margin: "12px 0 0",
                                paddingLeft: 20,
                                display: "grid",
                                gap: 9,
                                color: C.sub,
                                fontSize: 11.5,
                                lineHeight: 1.55,
                            }}
                        >
                            <li>
                                <b style={{ color: C.ink }}>입력값</b> —
                                수량·평균단가·통화가 실제 계좌와 맞는지
                                확인합니다.
                            </li>
                            <li>
                                <b style={{ color: C.ink }}>집중도</b> — 자본이
                                클수록 단일 종목·업종·지역 집중과 현금화
                                가능성을 먼저 확인합니다.
                            </li>
                            <li>
                                <b style={{ color: C.ink }}>평가손익</b> — 최근
                                공식 종가 기준일과 환율 기준일을 확인한 뒤
                                읽습니다. 실시간 가격이 아닙니다.
                            </li>
                            <li>
                                <b style={{ color: C.ink }}>공시·세금 사실</b> —
                                보유 종목 공시와 세금 기준일을 예상 수익과 섞지
                                않습니다.
                            </li>
                        </ol>
                        <div
                            style={{
                                marginTop: 12,
                                padding: "9px 10px",
                                borderRadius: 10,
                                background: C.bg,
                                color: C.faint,
                                fontSize: 10.5,
                                lineHeight: 1.55,
                            }}
                        >
                            함께 볼 것: 원가 분모 + 가격·환율 기준일 + 집중도.
                            자본 규모나 경험 수준만으로 위험성향과 적합 자산을
                            판정하지 않습니다.
                        </div>
                        <nav
                            aria-label="다음으로 볼 페이지"
                            style={{
                                marginTop: 12,
                                display: "flex",
                                alignItems: "center",
                                gap: 7,
                                flexWrap: "wrap",
                            }}
                        >
                            <span
                                style={{
                                    color: C.faint,
                                    fontSize: 10.5,
                                    fontWeight: 800,
                                }}
                            >
                                다음으로 볼 곳
                            </span>
                            {(
                                [
                                    ["종목 확인", "/stock"],
                                    ["보유 종목 공시", "/disclosure"],
                                    ["시장 환경", "/market"],
                                ] as const
                            ).map(([label, path]) => (
                                <a
                                    key={path}
                                    href={path}
                                    style={{
                                        color: C.vg,
                                        background: C.vgS,
                                        borderRadius: 999,
                                        padding: "5px 9px",
                                        fontSize: 10.5,
                                        fontWeight: 800,
                                        textDecoration: "none",
                                    }}
                                >
                                    {label}
                                </a>
                            ))}
                        </nav>
                    </div>
                ) : null}
            </section>
            ) : null}

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

                    {(isolated || !isDemo) && CcyToggle}
                    {(isolated || !isDemo) && Tabs}

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
                                                placeholder={demoMode ? "예시만 검색 · 예: Microsoft / MSFT" : "종목 검색 (이름·코드)"}
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
                                                            <Logo offline={demoMode}
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
                                                                            "transparent",
                                                                        cursor: "pointer",
                                                                        color: AN_STAR_GOLD,
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
                                                                    <StarMark
                                                                        size={
                                                                            17
                                                                        }
                                                                    />
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
                                                    종목을 검색해{" "}
                                                    <StarMark size={13} /> 를
                                                    누르면 수량·평단 입력 후
                                                    바로 추가돼요.
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
                                            {unpricedN > 0
                                                ? "참고금액 · 시세 없는 종목은 원가"
                                                : "총 평가금액"}
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 27,
                                                fontWeight: 800,
                                                letterSpacing: "-1px",
                                                margin: "3px 0",
                                            }}
                                        >
                                            {loading || loadErr
                                                ? "확인 중"
                                                : money(totalVal)}
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 14,
                                                fontWeight: 800,
                                                color: plColor(totalPl),
                                            }}
                                        >
                                            {pricedRows.length &&
                                            !loading &&
                                            !loadErr
                                                ? (totalPl > 0 ? "+" : "") +
                                                  money(totalPl) +
                                                  " · " +
                                                  (totalPlPct > 0 ? "+" : "") +
                                                  totalPlPct.toFixed(1) +
                                                  "%"
                                                : "손익 계산 보류"}
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 12,
                                                color: C.faint,
                                                fontWeight: 600,
                                                marginTop: 6,
                                            }}
                                        >
                                            보유 {rows.length}종목 · {demoMode ? "예시 입력값 기준" : "평단 입력 기준(사실)"}
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
                                                onKeyDown={(e) => {
                                                    if (
                                                        e.target ===
                                                            e.currentTarget &&
                                                        e.key === "Enter"
                                                    )
                                                        goStock(h)
                                                }}
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
                                                <Logo offline={demoMode}
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
                                                            // 🚨 2026-08-22 PM "스택 높이 변화 없이" — 이 줄은 **한 줄로 고정**한다.
                                                            //   배지(NestBadges)가 여기 인라인으로 들어오므로 nowrap 이 없으면
                                                            //   긴 공시 제목에서 줄바꿈돼 행 높이가 늘어난다(종전 4줄 사고).
                                                            //   overflow hidden 과 함께여야 잘림이 성립한다. 되돌리지 말 것.
                                                            whiteSpace:
                                                                "nowrap",
                                                            overflow: "hidden",
                                                            textOverflow:
                                                                "ellipsis",
                                                            display: "flex",
                                                            alignItems:
                                                                "center",
                                                            minWidth: 0,
                                                        }}
                                                    >
                                                        {h.ticker} ·{" "}
                                                        {Number(h.shares) || 0}
                                                        주 · 비중{" "}
                                                        {h._weight.toFixed(0)}%
                                                        <NestBadges
                                                            h={h}
                                                            nestIdx={nestIdx}
                                                            npsMap={npsMap}
                                                            C={C}
                                                        />
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
                                                            : Number(
                                                                    h.avg_cost
                                                                ) > 0
                                                              ? "시세·통화 확인 필요"
                                                              : "입력 평단 확인 필요"}
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
                                        {demoMode ? "평가손익 = 설명용 고정 예시 가격 × 보유수량 − 입력 평단 · 실제 시세 아님" : (<>

                                        종목 누르면 상세 리포트 · 평가손익 ={" "}
                                        {closeAsOf
                                            ? `${fmtAsOf(closeAsOf)} 종가`
                                            : "직전 거래일 종가"}{" "}
                                        × 보유수량 − 입력 평단 (단순 계산·사실)
                                        · 종가 = 금융위 공공데이터(T+1) · 실시간
                                        시세는 리포트에서
                                                                            </>)}
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

                                    {/* 입력 원가 기준 시장·업종·종목 노출 — 별도 컴포넌트 기능을 분산 탭에 흡수. */}
                                    <div style={cardS}>
                                        <div
                                            style={{
                                                display: "flex",
                                                alignItems: "flex-start",
                                                justifyContent: "space-between",
                                                gap: 12,
                                                flexWrap: "wrap",
                                                marginBottom: 12,
                                            }}
                                        >
                                            <div>
                                                <div
                                                    style={{
                                                        fontSize: 12,
                                                        color: C.vg,
                                                        fontWeight: 800,
                                                    }}
                                                >
                                                    내 원가 기준 사실 지도
                                                </div>
                                                <div
                                                    style={{
                                                        fontSize: 16,
                                                        fontWeight: 800,
                                                        marginTop: 3,
                                                    }}
                                                >
                                                    포트폴리오 노출
                                                </div>
                                                <div
                                                    style={{
                                                        fontSize: 11,
                                                        color: C.faint,
                                                        fontWeight: 600,
                                                        marginTop: 4,
                                                    }}
                                                >
                                                    현재가·수익률·목표 배분 없이
                                                    입력한 수량×평단만 사용
                                                </div>
                                            </div>
                                            <div
                                                style={{
                                                    textAlign: "right",
                                                    flexShrink: 0,
                                                }}
                                            >
                                                <div
                                                    style={{
                                                        fontSize: 16,
                                                        fontWeight: 800,
                                                    }}
                                                >
                                                    {wonCompact(
                                                        exposureModel.total
                                                    )}
                                                </div>
                                                <div
                                                    style={{
                                                        fontSize: 10.5,
                                                        color: C.faint,
                                                        fontWeight: 600,
                                                    }}
                                                >
                                                    환산 원가 합계
                                                </div>
                                            </div>
                                        </div>
                                        <div
                                            style={{
                                                display: "grid",
                                                gridTemplateColumns: narrow
                                                    ? "1fr"
                                                    : "repeat(3,minmax(0,1fr))",
                                                gap: 10,
                                            }}
                                        >
                                            {[
                                                [
                                                    "시장 노출",
                                                    exposureModel.markets,
                                                ],
                                                [
                                                    "업종 노출",
                                                    exposureModel.sectors,
                                                ],
                                                [
                                                    "종목 노출",
                                                    exposureModel.tickers,
                                                ],
                                            ].map(([label, data]: any) => (
                                                <div
                                                    key={label}
                                                    style={{
                                                        minWidth: 0,
                                                        padding: 12,
                                                        borderRadius: 12,
                                                        background: C.bg,
                                                    }}
                                                >
                                                    <div
                                                        style={{
                                                            fontSize: 13,
                                                            fontWeight: 800,
                                                            marginBottom: 10,
                                                        }}
                                                    >
                                                        {label}
                                                    </div>
                                                    <ExposureRows
                                                        rows={data}
                                                        C={C}
                                                    />
                                                </div>
                                            ))}
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 10.5,
                                                color: C.faint,
                                                fontWeight: 600,
                                                lineHeight: 1.5,
                                                marginTop: 11,
                                            }}
                                        >
                                            원가 계산{" "}
                                            {exposureModel.valued.length}/
                                            {rows.length}종목 · 업종 연결{" "}
                                            {exposureModel.sectorMapped}/
                                            {rows.length}종목
                                        </div>
                                        {exposureModel.excluded.length > 0 && (
                                            <div
                                                role="status"
                                                style={{
                                                    fontSize: 10.5,
                                                    color: C.faint,
                                                    fontWeight: 600,
                                                    lineHeight: 1.5,
                                                    marginTop: 4,
                                                }}
                                            >
                                                원가 계산 제외:{" "}
                                                {exposureModel.excluded.join(
                                                    ", "
                                                )}{" "}
                                                · 수량·평단 또는 미국 종목 환율
                                                결손
                                            </div>
                                        )}
                                        <div
                                            style={{
                                                fontSize: 10.5,
                                                color: C.faint,
                                                fontWeight: 600,
                                                lineHeight: 1.5,
                                                marginTop: 4,
                                            }}
                                        >
                                            USD/KRW{" "}
                                            {fxInfo.ok
                                                ? Number(FX).toLocaleString(
                                                      "ko-KR",
                                                      {
                                                          maximumFractionDigits: 2,
                                                      }
                                                  )
                                                : "결손"}
                                            {" · 기준 "}
                                            {fxInfo.asOf
                                                ? String(fxInfo.asOf)
                                                      .replace("T", " ")
                                                      .slice(0, 19)
                                                : "—"}
                                            {exposureMeta && exposureMeta.error
                                                ? " · 업종 분류 결손"
                                                : ""}
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
                                        {demoMode ? "예시 가격 기준 비중·집중도 계산 · 목표는 직접 설정 · 실제 자료 아님" : (<>

                                        비중·집중도 = 평가금액 기준 사실 산술 ·
                                        목표는 직접 설정 · 자산군 자금은 KRX ETF
                                        사실 · 투자자문·추천 아님
                                                                            </>)}
</div>
                                </>
                            ) : view === "tax" ? (
                                taxBlocked ? (
                                    <div
                                        role="status"
                                        style={{
                                            ...cardS,
                                            fontWeight: 600,
                                            lineHeight: 1.7,
                                        }}
                                    >
                                        <div
                                            style={{
                                                fontSize: 20,
                                                fontWeight: 800,
                                                color: C.ink,
                                            }}
                                        >
                                            예상 비용 계산 보류
                                        </div>
                                        필요한 자료가 없는 값을 0원으로 표시하지
                                        않아요.
                                        <ul>
                                            {!evald.length && (
                                                <li>
                                                    먼저 보유종목을 입력해
                                                    주세요.
                                                </li>
                                            )}
                                            {unpricedN > 0 && (
                                                <li>
                                                    평가 시세·환율 미확인{" "}
                                                    {unpricedN}/{evald.length}
                                                    종목:{" "}
                                                    {evald
                                                        .filter(
                                                            (h) => !h._priced
                                                        )
                                                        .map(
                                                            (h) =>
                                                                h.name ||
                                                                h.ticker
                                                        )
                                                        .join(", ")}
                                                </li>
                                            )}
                                            {taxExcluded.length > 0 && (
                                                <li>
                                                    자산 유형 미확인 또는 별도
                                                    세제 확인 필요:{" "}
                                                    {taxExcluded
                                                        .map(
                                                            (h) =>
                                                                h.name ||
                                                                h.ticker
                                                        )
                                                        .join(", ")}
                                                    . ETF·ETN·직접 원자재에는
                                                    일반 주식 산식을 적용하지
                                                    않아요.
                                                </li>
                                            )}
                                            {krMajorRows.length > 0 && (
                                                <li>
                                                    대주주 요건 검토가 필요해요.
                                                    현재 수량과 직전 연말
                                                    가격만으로는 확정할 수
                                                    없어요.
                                                </li>
                                            )}
                                            {(!broker ||
                                                (krRows.length > 0 &&
                                                    !isFinite(
                                                        parseFee(
                                                            broker?.domestic_fee
                                                        )
                                                    )) ||
                                                (usRows.length > 0 &&
                                                    !isFinite(
                                                        parseFee(
                                                            broker?.overseas_fee
                                                        )
                                                    ))) && (
                                                <li>
                                                    적용할 증권사 수수료를
                                                    확인하지 못했어요.
                                                </li>
                                            )}
                                        </ul>
                                        {brokers.length > 0 && (
                                            <label
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent:
                                                        "space-between",
                                                    gap: 10,
                                                    flexWrap: "wrap",
                                                    marginBottom: 12,
                                                    fontWeight: 700,
                                                }}
                                            >
                                                증권사 (매도 수수료)
                                                <select
                                                    aria-label="증권사 (매도 수수료)"
                                                    value={brokerIdx}
                                                    onChange={(e) =>
                                                        setBrokerIdx(
                                                            Number(
                                                                e.target.value
                                                            )
                                                        )
                                                    }
                                                    style={{
                                                        ...selStyle,
                                                        fontWeight: 700,
                                                        maxWidth: "100%",
                                                    }}
                                                >
                                                    {brokers.map((b, i) => (
                                                        <option
                                                            key={i}
                                                            value={i}
                                                        >
                                                            {b.name}
                                                        </option>
                                                    ))}
                                                </select>
                                            </label>
                                        )}
                                        일반계좌·국내 소액주주의 장내 매도를
                                        가정한 학습용 계산이며,
                                        ISA·연금·대주주·장외거래는 별도 확인이
                                        필요해요.
                                    </div>
                                ) : (
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
                                                일반계좌·소액주주{" "}
                                                <b>전량 매도</b> 가정 시 예상
                                                비용 (세금 + 수수료)
                                            </div>
                                            <div
                                                style={{
                                                    fontSize: 27,
                                                    fontWeight: 800,
                                                    letterSpacing: "-1px",
                                                    margin: "3px 0",
                                                }}
                                            >
                                                {won(
                                                    totalTax + totalCommission
                                                )}
                                            </div>
                                            <div
                                                style={{
                                                    fontSize: 12.5,
                                                    color: C.sub,
                                                    fontWeight: 600,
                                                }}
                                            >
                                                세금 {wonCompact(totalTax)} +
                                                수수료{" "}
                                                {wonCompact(totalCommission)} ·
                                                평가손익{" "}
                                                {totalPl >= 0 ? "+" : ""}
                                                {wonCompact(totalPl)} 기준
                                            </div>
                                        </div>

                                        {brokers.length > 0 && (
                                            <div
                                                style={{
                                                    ...cardS,
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent:
                                                        "space-between",
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
                                                            Number(
                                                                e.target.value
                                                            )
                                                        )
                                                    }
                                                    style={{
                                                        ...selStyle,
                                                        fontWeight: 700,
                                                        maxWidth: "60%",
                                                    }}
                                                >
                                                    {brokers.map((b, i) => (
                                                        <option
                                                            key={i}
                                                            value={i}
                                                        >
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
                                                    justifyContent:
                                                        "space-between",
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
                                                    <FlagIcon code="kr" /> 국내
                                                    주식
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
                                                    장내 소액주주 가정
                                                </span>
                                            </div>
                                            {kv(
                                                "양도소득세",
                                                "0원 (소액주주 장내 매도 가정)",
                                                C.vg
                                            )}
                                            {kv(
                                                "증권거래세 0.20%",
                                                won(krTxnTax)
                                            )}
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
                                                                h.name ||
                                                                h.ticker
                                                        )
                                                        .join(", ")}{" "}
                                                    (종목당 50억+ 보유 시 양도세
                                                    과세 대상). 판정 기준 ={" "}
                                                    {basisAsOf
                                                        ? `${basisAsOf.slice(0, 4)}-${basisAsOf.slice(4, 6)}-${basisAsOf.slice(6, 8)} 종가`
                                                        : "직전 사업연도 종료일 종가"}{" "}
                                                    — 현재가 아님. 지분율(코스피
                                                    1%·코스닥 2%) 요건은 별도.
                                                    기준일 보유수는 알 수 없어
                                                    현재 보유수로 근사했습니다 —
                                                    정확 판정은 세무사 확인.
                                                </div>
                                            )}
                                            {krMajorUnknown > 0 && (
                                                <div
                                                    style={{
                                                        color: C.sub,
                                                        fontSize: 11,
                                                        lineHeight: 1.5,
                                                        marginTop: 6,
                                                    }}
                                                >
                                                    판정 보류 {krMajorUnknown}
                                                    종목 — 직전 연말 종가
                                                    미확인. 현재가로 대체하지
                                                    않습니다.
                                                </div>
                                            )}
                                        </div>

                                        <div style={cardS}>
                                            <div
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent:
                                                        "space-between",
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
                                                    <FlagIcon code="us" /> 해외
                                                    주식
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
                                            {kv(
                                                "과세표준",
                                                wonCompact(usTaxable)
                                            )}
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
                                                22%(일반 외국법인 주식) · 손실
                                                연내통산(이월 없음) · 환율{" "}
                                                {Math.round(
                                                    FX
                                                ).toLocaleString()}
                                                원/$
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
                                                            alignItems:
                                                                "center",
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
                                                            style={{
                                                                minWidth: 0,
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
                                                                <FlagIcon
                                                                    code={
                                                                        h._us
                                                                            ? "us"
                                                                            : "kr"
                                                                    }
                                                                />
                                                                {h.name ||
                                                                    h.ticker}
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
                                                                      : majorPath(
                                                                              h
                                                                          ) !==
                                                                          ""
                                                                        ? "대주주 과세 검토"
                                                                        : "소액주주 장내 매도 가정"}
                                                            </div>
                                                        </div>
                                                        <div
                                                            style={{
                                                                fontSize: 13.5,
                                                                fontWeight: 800,
                                                                color: h._priced
                                                                    ? plColor(
                                                                          h._pl
                                                                      )
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
                                                                  wonCompact(
                                                                      h._pl
                                                                  )
                                                                : "—"}
                                                        </div>
                                                    </div>
                                                ))}
                                        </div>

                                        <div
                                            style={{
                                                ...cardS,
                                                background: C.vgS,
                                            }}
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
                                                "국내 상장주식은 소액주주의 장내 매도를 가정합니다. 대주주·장외거래·절세계좌는 별도 확인이 필요해요.",
                                                "대주주(종목당 보유 50억+, 직전 사업연도 종료일 종가 기준) 는 국내도 양도세 과세 — 지분율 요건 별도",
                                                "국외주식 양도세 = 22%, 연 250만 기본공제(국가 합산), 실현손익 연내통산",
                                                "수수료는 증권사별로 다름 — 세금(양도세·거래세)은 법정으로 증권사 무관",
                                                "해외 세금은 매입·매도 당시 환율과 연간 실현손익이 필요합니다. 현재 환율을 함께 적용한 여기의 시나리오는 실제 신고세액이 아닙니다.",
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
                                                            position:
                                                                "absolute",
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
                                        {demoMode ? "일반계좌 전량 매도 학습용 예시 · 설명용 고정 가격·환율·수수료를 적용하므로 실제 세액이 아닙니다." : (<>

                                            세율·공제는 2026 시행값(사실). 🚨
                                            해외 양도세는{" "}
                                            <b>
                                                보유 전량을 같은 해에 판다고
                                                가정
                                            </b>
                                            해 이익·손실을 통산한 값이에요 —
                                            일부만 팔면 손실 종목이 차감되지
                                            않아 실제 세금은 더 클 수 있어요.
                                            추정·관측 보조용 — 실제 납세 판단은
                                            세무사 확인. 절세 자문 아님.
                                                                                </>)}
</div>
                                    </>
                                )
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
                                                placeholder={demoMode ? "예시만 검색 · 예: Microsoft / MSFT" : "종목 검색 (이름·코드)"}
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
                                                                    <Logo offline={demoMode}
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
                                            <div
                                                style={{
                                                    ...cardS,
                                                    padding: "18px 18px",
                                                }}
                                            >
                                                <div style={sk(140, 12, 6)} />
                                                <div
                                                    style={{
                                                        ...sk(190, 26, 8),
                                                        marginTop: 10,
                                                    }}
                                                />
                                                <div
                                                    style={{
                                                        ...sk(240, 11, 6),
                                                        marginTop: 10,
                                                    }}
                                                />
                                            </div>
                                            <div
                                                style={{
                                                    ...cardS,
                                                    padding: "16px 18px",
                                                    marginTop: 10,
                                                }}
                                            >
                                                <div style={sk(72, 13, 6)} />
                                                {[0, 1, 2].map((i) => (
                                                    <div
                                                        key={i}
                                                        style={{
                                                            display: "flex",
                                                            alignItems:
                                                                "center",
                                                            gap: 10,
                                                            marginTop: 14,
                                                        }}
                                                    >
                                                        <div
                                                            style={sk(
                                                                30,
                                                                30,
                                                                10
                                                            )}
                                                        />
                                                        <div
                                                            style={{ flex: 1 }}
                                                        >
                                                            <div
                                                                style={sk(
                                                                    "42%",
                                                                    12,
                                                                    6
                                                                )}
                                                            />
                                                            <div
                                                                style={{
                                                                    ...sk(
                                                                        "28%",
                                                                        10,
                                                                        6
                                                                    ),
                                                                    marginTop: 6,
                                                                }}
                                                            />
                                                        </div>
                                                        <div
                                                            style={sk(
                                                                84,
                                                                13,
                                                                6
                                                            )}
                                                        />
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
                                                    실현손익 합계 · 매도
                                                    확정분(사실)
                                                </div>
                                                <div
                                                    style={{
                                                        fontSize: 27,
                                                        fontWeight: 800,
                                                        letterSpacing: "-1px",
                                                        margin: "3px 0",
                                                        color: plColor(
                                                            realizedKrw
                                                        ),
                                                    }}
                                                >
                                                    {(realizedKrw > 0
                                                        ? "+"
                                                        : "") +
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
                                                    이동평균 매입가 차감(사실) ·
                                                    거래{" "}
                                                    {
                                                        (tradeData.trades || [])
                                                            .length
                                                    }
                                                    건
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
                                                            String(s.market) ===
                                                            "us"
                                                        return (
                                                            <div
                                                                key={s.ticker}
                                                                onClick={() =>
                                                                    goStock(s)
                                                                }
                                                                role="link"
                                                                tabIndex={0}
                                                                onKeyDown={(
                                                                    e
                                                                ) => {
                                                                    if (
                                                                        e.target ===
                                                                            e.currentTarget &&
                                                                        e.key ===
                                                                            "Enter"
                                                                    )
                                                                        goStock(
                                                                            s
                                                                        )
                                                                }}
                                                                style={{
                                                                    display:
                                                                        "flex",
                                                                    alignItems:
                                                                        "center",
                                                                    gap: 12,
                                                                    background:
                                                                        C.card,
                                                                    borderRadius: 16,
                                                                    padding:
                                                                        "13px 15px",
                                                                    boxShadow:
                                                                        "0 1px 3px rgba(0,0,0,0.04)",
                                                                    cursor: "pointer",
                                                                }}
                                                            >
                                                                <Logo offline={demoMode}
                                                                    ticker={
                                                                        s.ticker
                                                                    }
                                                                    name={
                                                                        s.name
                                                                    }
                                                                    market={
                                                                        s.market
                                                                    }
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
                                                                                ) ||
                                                                                    0
                                                                            ),
                                                                        }}
                                                                    >
                                                                        {((Number(
                                                                            s.realized_pnl
                                                                        ) ||
                                                                            0) >
                                                                        0
                                                                            ? "+"
                                                                            : "") +
                                                                            px(
                                                                                Number(
                                                                                    s.realized_pnl
                                                                                ) ||
                                                                                    0,
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
                                                        아직 기록한 거래가
                                                        없어요.{" "}
                                                        {isDemo
                                                            ? "로그인하면"
                                                            : "+ 거래 추가로"}{" "}
                                                        매수·매도를 남겨보세요.
                                                    </div>
                                                ) : (
                                                    tLedger.map(
                                                        (t: any, i: number) => {
                                                            const us =
                                                                String(
                                                                    t.market
                                                                ) === "us"
                                                            const isBuy =
                                                                t.side === "buy"
                                                            return (
                                                                <div
                                                                    key={
                                                                        t.id ||
                                                                        i
                                                                    }
                                                                    style={{
                                                                        display:
                                                                            "flex",
                                                                        alignItems:
                                                                            "center",
                                                                        gap: 11,
                                                                        padding:
                                                                            "10px 0",
                                                                        borderTop:
                                                                            i ===
                                                                            0
                                                                                ? "none"
                                                                                : "1px solid " +
                                                                                  C.line,
                                                                    }}
                                                                >
                                                                    <Logo offline={demoMode}
                                                                        ticker={
                                                                            t.ticker
                                                                        }
                                                                        name={
                                                                            t.name
                                                                        }
                                                                        market={
                                                                            t.market
                                                                        }
                                                                        C={C}
                                                                        size={
                                                                            30
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
                                                                            ) ||
                                                                                0}
                                                                            주 @{" "}
                                                                            {px(
                                                                                Number(
                                                                                    t.price
                                                                                ) ||
                                                                                    0,
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
                                                                            ) ||
                                                                                0) *
                                                                                (Number(
                                                                                    t.price
                                                                                ) ||
                                                                                    0),
                                                                            us,
                                                                            ccy,
                                                                            FX
                                                                        )}
                                                                    </div>
                                                                    {!isDemo &&
                                                                        t.id && (
                                                                            <button
                                                                                onClick={() =>
                                                                                    openTEdit(
                                                                                        t
                                                                                    )
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
                                                                    {!isDemo &&
                                                                        t.id && (
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
                                                        }
                                                    )
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
                                        {demoMode ? "예시 거래의 이동평균 매입가 기준 계산 · 실제 보유·거래와 분리 · 이 화면에서만 유지" : (<>

                                                실현손익 = 매도가 − 이동평균
                                                매입가 (단순 계산·사실) · 본인
                                                기록용 · 순위·배지·공개 없음 ·
                                                투자자문 아님
                                                                                    </>)}
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
    previewOnly: {
        type: ControlType.Boolean,
        title: "Example Only",
        defaultValue: false,
    },
    demoPath: {
        type: ControlType.String,
        title: "Example Path",
        defaultValue: "/nest-demo",
    },
    showReadingGuide: {
        type: ControlType.Boolean,
        title: "Reading Guide",
        defaultValue: true,
        enabledTitle: "Show",
        disabledTitle: "Hide",
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark",
        defaultValue: false,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
})

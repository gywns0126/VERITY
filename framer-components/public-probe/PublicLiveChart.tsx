import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 일봉 차트 v2 — VERITY 공개 터미널. 자체 SVG 캔들 (외부 라이브러리 0 · 외부 위젯 0).
 *
 * 🚨 시세 재배포 컴플라이언스 (2026-07-04 v2):
 *   · KRX/KIS raw 재배포 불가 → 자체 차트 중단(7/2) → TradingView 위젯 시도 → KRX 임베드 표시 제한 확인(7/4 실증).
 *   · v2 source = 금융위원회_주식시세정보 공공데이터 (data.go.kr/data/15094808) — "이용허락범위 제한 없음" + 무료.
 *   · T+1 전일 종가까지 — 당일/실시간 없음. 라벨 정직 표기 의무. 실시간 = 네이버 link-out.
 *   상세 = docs/MIGRATION_KRX_QUOTE_REDISTRIBUTION_2026_07.md.
 *
 * 데이터 = Blob /kr_chart_daily/chunk_XX.json (청크 = parseInt(code,36)%40 — collector 와 동일 산식).
 *   종목당 최근 250거래일 [basDt,시,고,저,종,거래량] 오름차순. 평일 14:23 KST cron 갱신.
 * KR 색 = 상승 빨강 / 하락 파랑. 캔버스 = 데모 봉. 로딩 = shimmer 스켈레톤.
 *
 * 🚨 2026-07-28 ETF 지원 — kr_chart_daily 는 주식만 담아 ETF/ETN 이 청크에 없다.
 *   청크 미스 시 /etf_hist/{code}.json (KRX etf_bydd_trd 백필) 폴백 → OHLC 가 없으므로
 *   종가 라인 + NAV 점선 + 순자산 막대. 미장 티커는 재배포 권리 부재로 차트 미제공 안내.
 *
 * 🚨 2026-07-24 테마 = 자체 내장 CSS 변수(--an-plc-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
 *   <style>{AN_PALETTE} 정적 HTML 정합. 🚨 SVG stroke/fill = style 로 넘김(var 는 프레젠테이션 attribute 미해석). 되돌리지 말 것.
 */

interface Props {
    ticker: string
    chartBase: string
    height: number
    dark: boolean
    showVolume: boolean
    /* 해외(TradingView) 임베드 높이 — 고정 px. 위젯이 툴바·지표·하단 기간바를 자체로 들고 있어
       남는 공간을 나눠 쓰면 캔들 영역이 눌려 답답해 보인다(PM 2026-07-30). 캔버스에서 조절. */
    usChartHeight: number
}
const DEFAULT_BASE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
// 미장 보강 소스 — 한글명·네이버 딥링크 코드(universe_search.nv) + US ETF 사실(us_etf)
const UNIVERSE_URL = DEFAULT_BASE + "/universe_search.json"
const US_ETF_URL = DEFAULT_BASE + "/us_etf.json"
// 미국 개별종목 사실 = 슬라이스 API 1콜(~3.4KB). 전 종목 파일은 4.5MB 라 차트 옆에 두기엔 무겁다.
const US_SLICE_BASE = "https://project-yw131.vercel.app/api/stock_slice?ticker="
const N_CHUNKS = 40
const LIGHT = {
    bg: "#ffffff",
    card: "#ffffff",
    ink: "#191f28",
    sub: "#4e5968",
    faint: "#8b95a1",
    line: "#e5e8eb",
    grid: "#eef1f4",
    up: "#f04452",
    down: "#3182f6",
    vg: "#6c5ce7",
    ma5: "#f2a33c",
    ma20: "#0ca678",
    ma60: "#8b6cf0",
    hi52: "#f04452",
    lo52: "#3182f6",
    tipBd: "#e5e8eb",
    tabActive: "#f2f4f6",
    skBase: "#e9edf1",
    skHi: "#f3f5f7",
}
const DARK = {
    bg: "#171c23",
    card: "#1e242c",
    ink: "#e3e7ec",
    sub: "#9aa4b1",
    faint: "#828d9b",
    line: "#252b34",
    grid: "#1e242c",
    up: "#f04452",
    down: "#5b9bff",
    vg: "#a99bff",
    ma5: "#ffb454",
    ma20: "#34e08a",
    ma60: "#a99bff",
    hi52: "#ff6b76",
    lo52: "#5b9bff",
    tipBd: "#2d343d",
    tabActive: "#252b34",
    skBase: "#222a33",
    skHi: "#2d3742",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const WK = ["일", "월", "화", "수", "목", "금", "토"]
const RANGES = [
    { key: "1M", days: 22 },
    { key: "3M", days: 66 },
    { key: "6M", days: 132 },
    { key: "1Y", days: 250 },
    { key: "전체", days: 0 }, // MAX — 히스토리 lazy fetch + 주봉 자동 전환
]

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-plc-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "plc"
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

function isMobileWidth(): boolean {
    if (typeof window === "undefined") return false
    return window.innerWidth > 0 && window.innerWidth < 560
}
function isKrSecurityCode(tk: string): boolean {
    return /^\d[0-9A-Z]{5}$/i.test(String(tk || "").trim())
}
// 증권사(네이버)가 서빙 = 재배포 아님. 실시간·무료·합법 딥링크.
function naverUrl(tk: string): string {
    if (!isKrSecurityCode(tk)) return "https://finance.naver.com/"
    return isMobileWidth()
        ? "https://m.stock.naver.com/domestic/stock/" + tk + "/total"
        : "https://finance.naver.com/item/main.naver?code=" + tk
}
/* 🚨 미국 차트 = TradingView Advanced Chart 임베드 (2026-07-30, PM "차트를 아예 못 보여준다고?").
   2026-07-04 에 TV 를 접은 이유는 **KRX 심볼이 임베드에서 거부**됐기 때문이지 위젯 자체가 아니었다
   (docs 실증: "KR 종목은 위젯 종류 무관 표시 불가"). 미국 심볼은 애초에 제한 대상이 아니다.
   TV 문서 기준 **데이터 라이선스 책임은 TradingView 가 부담** → 임베드 측은 별도 계약 불요(지연 데이터).
   의무 = attribution(TradingView 링크) 병기 + 위젯 코드 변형 금지.
   🚨 iframe 높이는 반드시 px 로 준다 — Fit 이면 0 으로 계산돼 위젯이 통째로 사라진다(과거 사고). */
function tvWidgetHtml(symbol: string, dark: boolean, bg: string): string {
    const cfg = {
        autosize: true,
        symbol,
        interval: "D",
        timezone: "Asia/Seoul",
        theme: dark ? "dark" : "light",
        style: "1",
        locale: "kr",
        hide_side_toolbar: true,
        allow_symbol_change: false,
        save_image: false,
        withdateranges: true,
        support_host: "https://www.tradingview.com",
    }
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">' +
        "<style>*{margin:0;padding:0;border-radius:0!important}html,body,.tradingview-widget-container{width:100%;height:100%;overflow:hidden;border:none;background:" +
        bg +
        '}</style></head><body><div class="tradingview-widget-container">' +
        '<div class="tradingview-widget-container__widget" style="width:100%;height:100%"></div>' +
        '<script src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>' +
        JSON.stringify(cfg) +
        "</scr" +
        "ipt></div></body></html>"
    )
}

/* 🚨 미장 현재가 스트립 — TradingView Single Quote 를 알파네스트 카드 크롬에 녹인다 (PM 2026-08-17).
   되돌리지 말 것.

   왜 필요했나: renderForeign 은 이름·티커 다음이 곧바로 차트라 **가격·등락 숫자가 아예 없었다.**
     국내 분기는 헤더에 "전일 종가 · 날짜" 를 띄우는데 미장만 빈칸이었다.
   왜 우리 데이터가 아닌 TV 인가: KIS·거래소 실시간을 공개 표면에 얹으면 **재배포**다.
     2026-07-03 에 PublicStockReport 의 실시간 현재가 폴링을 제거한 이유가 정확히 그것이다.
     TV 위젯은 데이터 라이선스를 TV 가 부담하는 '표시(display)' 임베드라 우리는 재배포자가 아니다.
   왜 iframe 이 아니라 직접 주입인가: Single Quote 는 높이가 심볼마다 다른데 iframe 은 자동 높이를
     못 잡는다(같은 파일의 차트가 px 고정인 이유 = [[feedback_framer_iframe_fixed_height]]).
     PublicIndexBoard.IndexCard 가 쓰는 검증된 경로를 그대로 쓴다.
   🚨 라벨을 "실시간" 으로 단정하지 말 것 — TV 무료 위젯은 심볼에 따라 단일거래소(Cboe BZX)
     실시간이거나 지연이다. 위젯이 자체 표기하는 상태를 그대로 둔다. 어트리뷰션은 위젯이
     자동 포함하며 제거 = 무료 사용 조건 위반.
   크롬은 CSS 변수(C.card)로 테마를 따라가고, 위젯 자체 색은 tvDark 를 값으로 넘긴다
     (TV JSON 설정은 CSS var 를 해석하지 못한다). */
function UsQuoteStrip(props: { sym: string; isDark: boolean }) {
    const { sym, isDark } = props
    const ref = useRef<HTMLDivElement | null>(null)

    useEffect(() => {
        const host = ref.current
        if (!host) return
        host.innerHTML = ""
        const container = document.createElement("div")
        container.className = "tradingview-widget-container"
        const w = document.createElement("div")
        w.className = "tradingview-widget-container__widget"
        container.appendChild(w)
        const s = document.createElement("script")
        s.type = "text/javascript"
        s.async = true
        s.src =
            "https://s3.tradingview.com/external-embedding/embed-widget-single-quote.js"
        s.innerHTML = JSON.stringify({
            symbol: sym,
            width: "100%",
            isTransparent: true,
            colorTheme: isDark ? "dark" : "light",
            locale: "kr",
        })
        container.appendChild(s)
        host.appendChild(container)
        return () => {
            host.innerHTML = ""
        }
    }, [sym, isDark])

    return (
        <div
            style={{
                background: C.card,
                borderRadius: 14,
                boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                overflow: "hidden",
                padding: 2,
                boxSizing: "border-box",
            }}
        >
            <div ref={ref} style={{ width: "100%" }} />
        </div>
    )
}

/* 해외 딥링크 (2026-07-29) — 미장 시세 시계열은 재배포 권리가 없어 자체 차트를 못 그린다.
   증권사가 서빙하는 화면으로 정확히 보내는 것이 최선이자 합법.
   코드는 universe_search 의 nv(빌드 타임 해석). 실측상 접미어가 종목마다 다르다 —
   TSLA.O(나스닥) / VOO(무접미) / BRKb(클래스주). nv 가 아직 없으면 검색으로 보낸다(빈손 금지). */
function naverWorldUrl(tk: string, nv: string): string {
    if (nv) return "https://m.stock.naver.com/worldstock/stock/" + nv + "/total"
    return "https://m.stock.naver.com/search?query=" + encodeURIComponent(tk)
}
function mmdd(bas: number): string {
    const s = String(bas)
    return s.length === 8 ? s.slice(4, 6) + "." + s.slice(6, 8) : s
}
function dateDot(bas: number): string {
    const s = String(bas)
    if (s.length !== 8) return s
    const wd =
        WK[
            new Date(
                +s.slice(0, 4),
                +s.slice(4, 6) - 1,
                +s.slice(6, 8)
            ).getDay()
        ]
    return `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}(${wd})`
}
function won(v: any): string {
    const x = Number(v)
    return isFinite(x) && x > 0
        ? Math.round(x).toLocaleString("en-US") + "원"
        : "—"
}
function fmtVol(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x <= 0) return "—"
    if (x >= 1e8) return (x / 1e8).toFixed(2) + "억"
    if (x >= 1e4) return Math.round(x / 1e4).toLocaleString("en-US") + "만"
    return Math.round(x).toLocaleString("en-US")
}
// 순자산총액 — 조/억 단위 (ETF 잔액은 자릿수가 커 원 단위 노출이 안 읽힘)
function fmtAmt(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x <= 0) return "—"
    if (x >= 1e12) return (x / 1e12).toFixed(2) + "조원"
    if (x >= 1e8) return Math.round(x / 1e8).toLocaleString("en-US") + "억원"
    return Math.round(x).toLocaleString("en-US") + "원"
}
// collector(_chunk_idx)와 동일 — base36 (코드 'K' 포함 우선주 변형 대응). 양측 검증 완료.
function chunkOf(code: string): string {
    const n = parseInt(code, 36) % N_CHUNKS
    return String(n).padStart(2, "0")
}
function sma(closes: number[], period: number): (number | null)[] {
    const out: (number | null)[] = []
    let sum = 0
    for (let i = 0; i < closes.length; i++) {
        sum += closes[i]
        if (i >= period) sum -= closes[i - period]
        out.push(i >= period - 1 ? sum / period : null)
    }
    return out
}
// 일봉 → 주봉 (주 키 = 월요일). [주 마지막날, 첫 시가, max 고, min 저, 마지막 종가, 합 거래량]
function toWeekly(cs: number[][]): number[][] {
    const out: number[][] = []
    let cur: number[] | null = null
    let curKey = ""
    for (const c of cs) {
        const str = String(c[0])
        if (str.length !== 8) continue
        const dt = new Date(
            +str.slice(0, 4),
            +str.slice(4, 6) - 1,
            +str.slice(6, 8)
        )
        const day = (dt.getDay() + 6) % 7
        const mon = new Date(
            dt.getFullYear(),
            dt.getMonth(),
            dt.getDate() - day
        )
        const key = String(
            mon.getFullYear() * 10000 +
                (mon.getMonth() + 1) * 100 +
                mon.getDate()
        )
        if (key !== curKey) {
            if (cur) out.push(cur)
            cur = c.slice() // ETF 전용 6·7번(NAV·좌수)까지 보존
            curKey = key
        } else if (cur) {
            cur[0] = c[0]
            cur[2] = Math.max(cur[2], c[2])
            cur[3] = Math.min(cur[3], c[3])
            cur[4] = c[4]
            if (c.length > 6) {
                // ETF = 5번이 순자산총액(잔액). 합산하면 안 됨 — 주 마지막값.
                cur[5] = c[5]
                cur[6] = c[6]
                cur[7] = c[7]
            } else cur[5] += c[5]
        }
    }
    if (cur) out.push(cur)
    return out
}
// 히스토리(월간 stale 가능) + 최근 청크(fresh) 병합 — 같은 날은 최근 청크 우선
function mergeHist(hist: number[][] | null, recent: number[][]): number[][] {
    if (!hist || !hist.length) return recent
    const m: Record<number, number[]> = {}
    for (const c of hist) m[c[0]] = c
    for (const c of recent) m[c[0]] = c
    return Object.keys(m)
        .map((k) => m[+k])
        .sort((a, b) => a[0] - b[0])
}

function demoCandles(): number[][] {
    const demo: number[][] = []
    let p = 70000
    for (let i = 0; i < 60; i++) {
        const o = p,
            c = Math.round(p * (1 + (((i * 7) % 11) - 5) / 100))
        demo.push([
            20260400 + (i % 28) + 1,
            o,
            Math.round(Math.max(o, c) * 1.01),
            Math.round(Math.min(o, c) * 0.99),
            c,
            1000000 + i * 9000,
        ])
        p = c
    }
    return demo
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicLiveChart(props: Props) {
    const { ticker, chartBase, height, dark, showVolume, usChartHeight } = props
    const base = (chartBase || DEFAULT_BASE).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const Hprop = height || 480

    const wrapRef = useRef<HTMLDivElement>(null)
    const svgRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    // 🚨 높이 상태 없음 — 자기 높이를 읽으면 Fit 순환이 닫힌다(위 ResizeObserver 주석).
    const [full, setFull] = useState<number[][]>(() =>
        RenderTarget.current() === RenderTarget.canvas ? demoCandles() : []
    )
    const [name, setName] = useState("")
    const [range, setRange] = useState("3M")
    const [hoverIdx, setHoverIdx] = useState<number | null>(null)
    const [noData, setNoData] = useState(false)
    const [isEtf, setIsEtf] = useState(false)
    // 해외 종목 보강 — PM 2026-07-29 "최대한의 정보 노출은 하자". 차트를 못 그린다고 빈 칸을 두지 않는다.
    const [usInfo, setUsInfo] = useState<any>(null)
    /* 🚨 TradingView iframe 전용 테마 플래그. 이 컴포넌트 본문은 CSS 변수(--an-plc-*)로 칠하지만
       iframe 안에서는 부모의 CSS 변수를 못 읽는다 → 테마와 배경색을 **값으로** 넘겨야 한다.
       그래서 여기서만 body[data-framer-theme] 를 직접 읽는다(본문 렌더에는 쓰지 않음). */
    const [tvDark, setTvDark] = useState(false)
    useEffect(() => {
        if (onCanvas) return
        const read = () =>
            setTvDark(
                !!(
                    typeof document !== "undefined" &&
                    document.body &&
                    document.body.dataset.framerTheme === "dark"
                )
            )
        read()
        if (typeof MutationObserver === "undefined" || !document.body) return
        const o = new MutationObserver(read)
        o.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-framer-theme"],
        })
        return () => o.disconnect()
    }, [onCanvas])

    // 종목 = prop → URL ?q= → localStorage(StockReport 기록). 이벤트·popstate 수신해 리로드 없이 추종.
    // 유효 코드 아니면 빈 상태 (기본 종목 fallback 금지 — 엉뚱 그래프 방지). 영숫자 KRX 단축코드 허용.
    const resolveTk = (): string => {
        let t = String(ticker || "")
            .trim()
            .toUpperCase()
        if (!t && typeof window !== "undefined") {
            t = (new URLSearchParams(window.location.search).get("q") || "")
                .trim()
                .toUpperCase()
            if (!t) {
                try {
                    t = (
                        window.localStorage.getItem("verity_last_ticker") || ""
                    )
                        .trim()
                        .toUpperCase()
                } catch (e) {
                    t = ""
                }
            }
        }
        return t
    }
    // 2026-07-28: 옛 코드는 여기서 6자리 코드가 아니면 ""를 돌려줬다 → 미장 티커(VOO)가
    // "표시할 종목이 없습니다"(= 종목 자체가 없다)로 보여 오독을 낳았다. 이제 원문을 보존하고
    // 국내 코드 여부만 파생 — 해외는 "차트 미제공"으로 정직하게 구분해 안내한다.
    const [rawTk, setTk] = useState<string>(resolveTk)
    const tk = isKrSecurityCode(rawTk) ? rawTk : ""
    const isForeign = !!rawTk && !tk
    useEffect(() => {
        if (onCanvas) return
        const reread = () => setTk(resolveTk())
        reread()
        window.addEventListener("verity-ticker-change", reread)
        window.addEventListener("popstate", reread)
        return () => {
            window.removeEventListener("verity-ticker-change", reread)
            window.removeEventListener("popstate", reread)
        }
    }, [ticker, onCanvas])

    /* 해외 종목 = 유니버스(한글명·네이버 코드) + us_etf(ETF 사실) 를 받아 빈 화면을 채운다.
       국내 종목이면 아무것도 받지 않는다(불필요 트래픽 0). */
    useEffect(() => {
        setUsInfo(null)
        if (onCanvas || !isForeign) return
        let alive = true
        const acc: any = { ticker: rawTk }
        fetch(UNIVERSE_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d) return
                const arr = Array.isArray(d) ? d : d.stocks || []
                const hit = arr.find(
                    (x: any) => String(x.ticker || "").toUpperCase() === rawTk
                )
                if (hit) {
                    acc.name = hit.name_ko || hit.name || rawTk
                    acc.nv = hit.nv || ""
                    acc.market = hit.market || ""
                }
                setUsInfo({ ...acc })
                if (String(acc.market) !== "ETF") {
                    // 미국 개별종목 — 시총·거래대금·PER·EPS 등 발행 사실을 채운다.
                    return fetch(US_SLICE_BASE + encodeURIComponent(rawTk))
                        .then((r) => (r.ok ? r.json() : null))
                        .then((d2) => {
                            const rep2 = d2 && d2.report
                            if (!alive || !rep2) return
                            setUsInfo({ ...acc, stock: rep2 })
                        })
                        .catch(() => {})
                }
                return fetch(US_ETF_URL)
                    .then((r) => (r.ok ? r.json() : null))
                    .then((e) => {
                        if (!alive || !e) return
                        const f = (e.etfs || []).find(
                            (x: any) =>
                                String(x.ticker || "").toUpperCase() === rawTk
                        )
                        if (f) setUsInfo({ ...acc, etf: f })
                    })
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [isForeign, rawTk, onCanvas])

    /* 🚨 **폭만 관찰한다. 높이는 절대 읽지 않는다.** (2026-08-17, 되돌리지 말 것)
       종전엔 같은 ResizeObserver 로 자기 높이(contentRect.height)까지 읽어 `chartH = h - 118`
       로 썼다. 두 가지가 동시에 깨졌다.
         ① Fit 무한 성장 — Fit 이면 프레임 높이가 콘텐츠로 정해지는데 그 높이를 다시 읽어
            차트를 키우니 h↑ → chartH↑ → 콘텐츠↑ → h↑ 로 순환이 닫힌다. PM 이 본 "끝없이
            아래로 늘어짐" 이 이것이고, 560px 고정은 증상만 막은 우회였다.
         ② 세로 늘어짐 — 높이가 고정이면 **폭이 줄어도 높이가 안 준다.** 모바일 폭에서
            플롯이 1.1:1(거의 정사각형)이 돼 캔들이 세로로 늘어난다(데스크톱은 2.3:1 정상).
       높이 권위를 폭으로 옮기면 둘 다 사라진다 — 순환의 고리가 끊기고, 폭이 줄면 높이도 준다. */
    useEffect(() => {
        const el = wrapRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries) setW(e.contentRect.width)
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    /* 데이터 — Blob 청크 fetch (sessionStorage 캐시, cache-fallback). 종목 미포함 = 정직한 빈 상태. */
    useEffect(() => {
        if (onCanvas) {
            setFull(demoCandles())
            setName("미리보기")
            return
        }
        setFull([])
        setNoData(false)
        setName("")
        setIsEtf(false)
        setHoverIdx(null)
        if (!tk) return
        let alive = true
        const url = base + "/kr_chart_daily/chunk_" + chunkOf(tk) + ".json"
        const cacheKey = "krchart_" + chunkOf(tk)
        const apply = (doc: any): boolean => {
            const ent = doc && doc.stocks && doc.stocks[tk]
            if (ent && Array.isArray(ent.c) && ent.c.length > 1) {
                if (alive) {
                    setFull(ent.c)
                    setName(ent.n || tk)
                }
                return true
            }
            return false
        }
        /* ETF 폴백 — 금융위 주식시세정보(kr_chart_daily)는 **주식만** 담는다. ETF/ETN 은 청크에
           아예 없어 옛 코드가 곧장 "시세 정보 없음"으로 떨어졌다(PM 지적 2026-07-28).
           ETF 는 KRX etf_bydd_trd 백필(etf_hist/{code}.json)이 종가·NAV·좌수·순자산을 갖고 있다.
           OHLC 가 없으므로 캔들 대신 종가 라인 + NAV 라인으로 그린다.
           행 = [날짜, 종가x4, 순자산(막대), NAV, 상장좌수] — 뒤 2칸이 ETF 전용. */
        const tryEtf = () => {
            fetch(base + "/etf_hist/" + tk + ".json")
                .then((r) => (r.ok ? r.json() : null))
                .then((d) => {
                    if (!alive) return
                    const ds = d && Array.isArray(d.d) ? d.d : null
                    if (!ds) {
                        setNoData(true)
                        return
                    }
                    const rows: number[][] = []
                    for (let i = 0; i < ds.length; i++) {
                        const px = Number(d.c ? d.c[i] : NaN)
                        if (!isFinite(px) || px <= 0) continue // 휴장/결측일 = 건너뜀
                        const nav = Number(d.v ? d.v[i] : NaN)
                        const ast = Number(d.a ? d.a[i] : NaN)
                        const shr = Number(d.s ? d.s[i] : NaN)
                        rows.push([
                            Number(ds[i]),
                            px,
                            px,
                            px,
                            px,
                            isFinite(ast) ? ast : 0,
                            isFinite(nav) ? nav : 0,
                            isFinite(shr) ? shr : 0,
                        ])
                    }
                    if (rows.length > 1) {
                        rows.sort((a, b) => a[0] - b[0])
                        setFull(rows)
                        setName(d.n || tk)
                        setIsEtf(true)
                    } else setNoData(true)
                })
                .catch(() => {
                    if (alive) setNoData(true)
                })
        }
        fetch(url)
            .then((r) => (r.ok ? r.json() : null))
            .then((doc) => {
                if (!alive) return
                if (doc) {
                    try {
                        sessionStorage.setItem(cacheKey, JSON.stringify(doc))
                    } catch (e) {}
                    if (!apply(doc)) tryEtf() // 청크 수신 OK · 종목 없음 = ETF 일 수 있음
                } else {
                    try {
                        const c = sessionStorage.getItem(cacheKey)
                        if (!(c && apply(JSON.parse(c)))) tryEtf()
                    } catch (e) {
                        tryEtf()
                    }
                }
            })
            .catch(() => {
                try {
                    const c = sessionStorage.getItem(cacheKey)
                    if (!(c && apply(JSON.parse(c)))) {
                        /* 네트워크 오류 = 스켈레톤 유지 */
                    }
                } catch (e) {}
            })
        return () => {
            alive = false
        }
    }, [tk, base, onCanvas])

    /* 전체(MAX) 탭 — 히스토리 lazy fetch (탭 선택 시에만 1회). [] = 미보유(최근 청크만으로 표시). */
    const [histFull, setHistFull] = useState<number[][] | null>(null)
    useEffect(() => {
        setHistFull(null)
    }, [tk])
    useEffect(() => {
        // ETF 는 etf_hist 자체가 전체 히스토리 — 별도 kr_chart_history 없음(404 방지)
        if (onCanvas || range !== "전체" || !tk || histFull || isEtf) return
        let alive = true
        fetch(base + "/kr_chart_history/" + tk + ".json")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive)
                    setHistFull(
                        d && Array.isArray(d.c) && d.c.length > 1 ? d.c : []
                    )
            })
            .catch(() => {
                if (alive) setHistFull([])
            })
        return () => {
            alive = false
        }
    }, [range, tk, base, onCanvas, histFull])

    /* 파생 — 52주(전체 250d) 고저 + MA 는 full 기준 계산 후 range 슬라이스 (경계 왜곡 방지) */
    const view = useMemo(() => {
        if (!full || full.length < 2) return null
        const hi52 = Math.max(...full.map((c) => c[2]))
        const lo52 = Math.min(...full.map((c) => c[3]))
        if (range === "전체") {
            const merged = mergeHist(histFull, full)
            const isWeekly = merged.length > 320
            const candles = isWeekly ? toWeekly(merged) : merged
            const none: (number | null)[] = []
            // MAX = 주봉·수년 스팬 — MA(일봉 산식)·52주선 비표시 (오독 방지)
            return {
                candles,
                ma5: none,
                ma20: none,
                ma60: none,
                hi52,
                lo52,
                prevClose: null,
                isMax: true,
                isWeekly,
            }
        }
        const closesAll = full.map((c) => c[4])
        const ma5All = sma(closesAll, 5),
            ma20All = sma(closesAll, 20),
            ma60All = sma(closesAll, 60)
        const days = (RANGES.find((r) => r.key === range) || RANGES[1]).days
        const start = Math.max(0, full.length - days)
        return {
            candles: full.slice(start),
            ma5: ma5All.slice(start),
            ma20: ma20All.slice(start),
            ma60: ma60All.slice(start),
            hi52,
            lo52,
            prevClose: start > 0 ? full[start - 1][4] : null,
            isMax: false,
            isWeekly: false,
        }
    }, [full, range, histFull])

    /* 좌표 — 프레임 실측 높이 안을 꽉 채움 (헤더/탭/축/푸터 크롬 ≈ 118px 제외) */
    const cv = useMemo(() => {
        if (!view) return null
        const candles = view.candles
        const his = candles.map((c) => c[2]),
            los = candles.map((c) => c[3])
        // 52주 고저선은 시야 밖일 수 있음 — 가격축은 현 range + (근접 시) 52주선 포함
        let pmin = Math.min(...los),
            pmax = Math.max(...his)
        if (!view.isMax) {
            const prng0 = pmax - pmin || 1
            if (view.hi52 <= pmax + prng0 * 0.25)
                pmax = Math.max(pmax, view.hi52)
            if (view.lo52 >= pmin - prng0 * 0.25)
                pmin = Math.min(pmin, view.lo52)
        }
        const prng = pmax - pmin || 1
        const W = Math.max(240, (w || 800) - 4)
        /* 🚨 차트 높이 = **폭에서 나온다.** 프레임 잔여 높이를 먹지 않는다 (2026-08-17).
           1.75 = 가격 플롯+거래량 영역의 가로:세로 목표비. 1.75 를 키우면 납작해지고
           줄이면 세로로 늘어난다. 118 = 헤더+x축+범례+링크+패딩 추정치.
           · W 300(모바일) → 171 → 하한 190 적용   · W 800(데스크톱) → 457
           Hprop 은 **상한**으로만 쓴다 — 캔버스에서 더 낮게 조일 수 있되, 폭이 좁을 때
           억지로 늘리지는 못한다. 늘리는 방향이 세로 늘어짐의 원인이었다.

           🚨 상수를 따로 선언하지 않고 리터럴로 둔다 (2026-08-18).
             종전엔 CHART_ASPECT/CHROME_H 를 모듈 최상위 상수로 뺐는데, 복붙이 블록 단위라
             **상수 블록만 누락되면 `W / undefined` = NaN** 이 되고 chartH→Hp→전 좌표가
             NaN 으로 번진다. 그러면 SVG 는 캔들·MA·거래량을 통째로 안 그리는데 축 라벨·
             툴팁·범례는 HTML 이라 멀쩡히 남아 "차트만 사라진" 것처럼 보인다. 실제로 그렇게
             깨졌다. 블록 간 의존을 없애 이 실패 자체를 불가능하게 만든다. 되돌리지 말 것.

           🚨 유한성 가드 — 어떤 이유로든 NaN 이 되면 조용히 빈 차트가 되는 대신 기본값을 쓴다.
             빈 화면은 원인을 못 알려주지만 그려진 차트는 최소한 보인다. */
        const _ch = Math.min(
            Math.max(190, Math.round(W / 1.75)),
            Math.max(220, Hprop - 118)
        )
        const chartH = Number.isFinite(_ch) ? _ch : 320
        const Hv = showVolume !== false ? Math.round(chartH * 0.16) : 0
        const gap = Hv ? 8 : 0
        const padT = 10,
            padB = 4
        const Hp = chartH - Hv - gap
        const n = candles.length
        const xAt = (i: number) => (n === 1 ? W / 2 : (i / (n - 1)) * W)
        const yP = (v: number) =>
            padT + (Hp - padT - padB) - ((v - pmin) / prng) * (Hp - padT - padB)
        const vols = candles.map((c) => c[5])
        const vmax = Math.max(1, ...vols)
        // ETF 순자산 막대는 0 기준이면 변화가 안 보인다(잔액이라 늘 큰 값) — 최소값 기준으로 깔아줌
        const vmin = isEtf
            ? Math.min(...vols.filter((v) => v > 0), vmax) * 0.98
            : 0
        const vspan = Math.max(1, vmax - vmin)
        const cw = Math.max(1.2, (W / n) * 0.62)
        const items = candles.map((c, i) => {
            // ETF 는 시가가 없어 o=c — 전일 종가 대비로 색을 정한다
            const upDay = isEtf
                ? i > 0
                    ? c[4] >= candles[i - 1][4]
                    : true
                : c[4] >= c[1]
            const bh = Hv ? (Math.max(0, c[5] - vmin) / vspan) * (Hv - 2) : 0
            return {
                x: xAt(i),
                oy: yP(c[1]),
                cy: yP(c[4]),
                hy: yP(c[2]),
                ly: yP(c[3]),
                upDay,
                volTop: Hp + gap + (Hv - bh),
                volH: Math.max(0.5, bh),
            }
        })
        const tickIdx = [
            0,
            Math.round((n - 1) / 3),
            Math.round((2 * (n - 1)) / 3),
            n - 1,
        ]
        const maPath = (arr: (number | null)[]): string => {
            let dstr = "",
                pen = false
            for (let i = 0; i < arr.length; i++) {
                const v = arr[i]
                if (v == null) {
                    pen = false
                    continue
                }
                dstr +=
                    (pen ? "L" : "M") +
                    xAt(i).toFixed(1) +
                    "," +
                    yP(v).toFixed(1)
                pen = true
            }
            return dstr
        }
        // ETF 라인 — 종가 실선 + 아래 면적, NAV 는 점선(괴리를 눈으로 확인)
        const closeLine = isEtf ? maPath(candles.map((c) => c[4])) : ""
        const navLine =
            isEtf && candles.some((c) => c.length > 6 && c[6] > 0)
                ? maPath(candles.map((c) => (c[6] > 0 ? c[6] : null)))
                : ""
        const closeArea = closeLine
            ? closeLine +
              "L" +
              xAt(n - 1).toFixed(1) +
              "," +
              (Hp - padB).toFixed(1) +
              "L" +
              xAt(0).toFixed(1) +
              "," +
              (Hp - padB).toFixed(1) +
              "Z"
            : ""
        return {
            W,
            H: chartH,
            Hp,
            Hv,
            gap,
            pmin,
            pmax,
            xAt,
            yP,
            items,
            cw,
            n,
            tickIdx,
            closeLine,
            navLine,
            closeArea,
            p5: maPath(view.ma5),
            p20: maPath(view.ma20),
            p60: maPath(view.ma60),
        }
    }, [view, w, Hprop, showVolume, isEtf])

    const setHoverFromX = (clientX: number) => {
        if (!cv || !svgRef.current) return
        const rect = svgRef.current.getBoundingClientRect()
        if (rect.width <= 0) return
        let rel = (clientX - rect.left) / rect.width
        rel = Math.max(0, Math.min(1, rel))
        setHoverIdx(Math.round(rel * (cv.n - 1)))
    }

    const candles = view ? view.candles : []
    const last = candles.length ? candles[candles.length - 1] : null
    const prevOfLast =
        candles.length > 1
            ? candles[candles.length - 2][4]
            : (view && view.prevClose) || null
    const lastChg =
        last && prevOfLast ? ((last[4] - prevOfLast) / prevOfLast) * 100 : null

    const hov =
        hoverIdx != null && cv && hoverIdx >= 0 && hoverIdx < cv.n
            ? candles[hoverIdx]
            : null
    const hovX = hov && cv ? cv.xAt(hoverIdx as number) : 0
    const hovChg = (() => {
        if (!hov || hoverIdx == null) return null
        const pc =
            (hoverIdx as number) > 0
                ? candles[(hoverIdx as number) - 1][4]
                : view && view.prevClose
        if (!pc || pc <= 0) return null
        return ((hov[4] - pc) / pc) * 100
    })()
    const cardLeftPct = cv ? (hovX / cv.W) * 100 : 0
    const cardFlip = cv
        ? hoverIdx != null && (hoverIdx as number) > cv.n * 0.5
        : false

    const wrap: CSSProperties = {
        /* 🚨 height:100% 로 되돌렸다 (2026-08-18 이분탐색).
           `height:"auto"` 로 바꿨더니 캔들·MA·거래량이 통째로 안 그려졌다(축 라벨·툴팁은 HTML
           이라 남아 원인이 안 보인다). 정적 분석으로는 못 짚었고 — 높이 계산·색 토큰·팔레트
           주입 전부 정상이었다 — 변경 4건 중 이 레이아웃 한 건만 되돌려 원인을 가른다.
           🚨 되돌리지 말 것: 종횡비 수정(폭에서 높이 산출)은 그대로 유지된다. 프레임은
           고정 높이로 둔다(Fit 은 이 값이 100% 라 다시 순환 위험 — 별도로 다뤄야 한다). */
        width: "100%",
        height: "100%",
        minHeight: Math.max(260, Hprop),
        position: "relative",
        background: C.bg,
        borderRadius: 16,
        overflow: "hidden",
        boxSizing: "border-box",
        fontFamily: FONT,
        padding: "10px 4px 4px",
        display: "flex",
        flexDirection: "column",
    }
    const tipRow = (label: string, value: any, color?: string) => (
        <div
            style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 10,
                padding: "2px 0",
            }}
        >
            <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 500 }}>
                {label}
            </span>
            <span
                style={{
                    fontSize: 11.5,
                    color: color || C.ink,
                    fontWeight: 600,
                    fontVariantNumeric: "tabular-nums",
                }}
            >
                {value}
            </span>
        </div>
    )
    const maChip = (label: string, color: string) => (
        <span
            style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 3,
                fontSize: 10,
                fontWeight: 600,
                color: C.faint,
            }}
        >
            <span
                style={{
                    width: 10,
                    height: 2,
                    background: color,
                    display: "inline-block",
                    borderRadius: 1,
                }}
            />
            {label}
        </span>
    )
    const rangeTab = (r: { key: string }) => (
        <button
            key={r.key}
            onClick={() => {
                setRange(r.key)
                setHoverIdx(null)
            }}
            style={{
                border: "none",
                cursor: "pointer",
                fontFamily: FONT,
                padding: "4px 10px",
                borderRadius: 8,
                fontSize: 11.5,
                fontWeight: 700,
                background: range === r.key ? C.tabActive : "transparent",
                color: range === r.key ? C.ink : C.faint,
            }}
        >
            {r.key}
        </button>
    )

    const renderEmpty = () => (
        <div
            style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 7,
                padding: "0 18px",
                textAlign: "center",
            }}
        >
            {/* Phosphor chart-line (regular) — 자작 점선 아이콘의 끊김 인상 교체 (PM 2026-07-07) */}
            <svg
                width="30"
                height="30"
                viewBox="0 0 256 256"
                style={{ opacity: 0.5 }}
            >
                <path
                    d="M232,208a8,8,0,0,1-8,8H32a8,8,0,0,1-8-8V48a8,8,0,0,1,16,0v94.37L90.73,98a8,8,0,0,1,10.07-.38l58.81,44.11L218.73,90a8,8,0,1,1,10.54,12l-64,56a8,8,0,0,1-10.07.38L96.39,114.29,40,163.63V200H224A8,8,0,0,1,232,208Z"
                    style={{ fill: C.faint }}
                />
            </svg>
            <span style={{ fontSize: 13, fontWeight: 700, color: C.sub }}>
                {tk ? "표시할 시세 정보가 없습니다" : "표시할 종목이 없습니다"}
            </span>
            <span
                style={{
                    fontSize: 11,
                    fontWeight: 500,
                    color: C.faint,
                    lineHeight: 1.5,
                }}
            >
                {tk
                    ? "이 종목은 차트로 표시할 일봉 데이터가 없어요"
                    : "종목을 선택하면 차트가 표시돼요"}
            </span>
        </div>
    )
    /* 해외 종목 — 차트를 못 그리는 자리에 "없다"만 적어두지 않는다(PM 2026-07-29).
       가진 사실(한글명 · 분류 · ETF면 수익률/보수/분배율/베타/AUM)을 펴고,
       실시간 시세는 증권사(네이버) 화면으로 바로 보낸다. */
    const renderForeign = () => {
        const e = (usInfo && usInfo.etf) || null
        const nm = (usInfo && usInfo.name) || rawTk
        const url = naverWorldUrl(rawTk, (usInfo && usInfo.nv) || "")
        const kv = (k: string, v: string, col?: string) => (
            <div key={k} style={{ minWidth: 78 }}>
                <div
                    style={{ fontSize: 10.5, color: C.faint, fontWeight: 700 }}
                >
                    {k}
                </div>
                <div
                    style={{
                        fontSize: 14,
                        fontWeight: 800,
                        color: col || C.ink,
                        marginTop: 2,
                        letterSpacing: "-0.3px",
                    }}
                >
                    {v}
                </div>
            </div>
        )
        const sg = (v: any) => {
            const x = Number(v)
            return (x > 0 ? "+" : "") + x.toFixed(2) + "%"
        }
        const cl = (v: any) =>
            Number(v) > 0 ? C.up : Number(v) < 0 ? C.down : C.faint
        const st = (usInfo && usInfo.stock) || null
        const rows: any[] = []
        if (st) {
            const h = st.header || {}
            const f = st.facts || {}
            if (h.market_cap) rows.push(kv("시가총액", String(h.market_cap)))
            if (h.trading_value)
                rows.push(kv("거래대금", String(h.trading_value)))
            if (f["PER"]) rows.push(kv("PER", String(f["PER"])))
            if (f["PBR"]) rows.push(kv("PBR", String(f["PBR"])))
            if (f["EPS"]) rows.push(kv("EPS", String(f["EPS"])))
            if (f["ROE"]) rows.push(kv("ROE", String(f["ROE"])))
        }
        if (e && e.returns) {
            if (e.returns.ytd != null)
                rows.push(kv("올해", sg(e.returns.ytd), cl(e.returns.ytd)))
            if (e.returns.y3 != null)
                rows.push(kv("3년 연평균", sg(e.returns.y3), cl(e.returns.y3)))
            if (e.returns.y5 != null)
                rows.push(kv("5년 연평균", sg(e.returns.y5), cl(e.returns.y5)))
        }
        if (e) {
            if (e.expense != null) rows.push(kv("총보수", e.expense + "%"))
            if (e.yield_pct != null) rows.push(kv("분배율", e.yield_pct + "%"))
            if (e.beta3y != null) rows.push(kv("베타 3년", String(e.beta3y)))
            if (e.aum_usd)
                rows.push(
                    kv(
                        "순자산",
                        "$" + (Number(e.aum_usd) / 1e9).toFixed(1) + "B"
                    )
                )
        }
        // 위젯 높이 — 프레임 실측에서 헤더/사실/푸터 몫을 뺀 값. px 고정(Fit 금지).
        /* 🚨 고정 높이 (PM 2026-07-30 "이것저것 기능이 많다보니 답답해보이네").
           옛 계산식은 프레임 높이에서 사실줄·링크줄 몫을 뺀 **나머지**를 줬는데, 위젯이 툴바·지표선택·
           하단 기간바를 자체로 들고 있어 나머지만으로는 캔들 영역이 눌렸다. 이제 px 로 고정한다. */
        const tvH = Math.max(240, Number(usChartHeight) || 460)
        return (
            <div
                style={{
                    flex: 1,
                    minHeight: 0,
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                    padding: "0 10px 4px",
                    // 차트를 고정 높이로 주면 프레임이 짧을 때 아래 내용이 잘린다 → 자체 스크롤.
                    overflowY: "auto",
                }}
            >
                <div style={{ padding: "0 4px" }}>
                    <div
                        style={{
                            fontSize: 16,
                            fontWeight: 800,
                            color: C.ink,
                            letterSpacing: "-0.3px",
                        }}
                    >
                        {nm}
                    </div>
                    <div
                        style={{
                            fontSize: 11.5,
                            fontWeight: 700,
                            color: C.faint,
                            marginTop: 3,
                        }}
                    >
                        {rawTk}
                        {e && e.category
                            ? " · " + e.category
                            : st && st.gics_ko
                              ? " · " + st.gics_ko
                              : " · 미국 상장"}
                        {e && e.family ? " · " + e.family : ""}
                    </div>
                </div>
                {/* 현재가·등락 — 이 자리가 미장만 비어 있었다(국내는 헤더에 전일 종가 표기).
                    상세·라이선스 근거 = UsQuoteStrip 정의부 주석. */}
                <UsQuoteStrip sym={rawTk} isDark={tvDark} />
                {/* TradingView 임베드 — 데이터·라이선스는 TV 가 서빙. 우리는 저장·재배포하지 않는다. */}
                {/* 🚨 모서리 처리 — 2차 수정(PM 재지적 2026-07-30).
                    1차엔 래퍼에 radius+overflow:hidden 만 줬는데 여전히 잘려 보였다. 원인은
                    **위젯이 자기 문서 안에서 1px 테두리를 그린다**는 것 — TradingView 는 중첩 iframe 을
                    쓰기 때문에 우리가 srcDoc CSS 로 border:0 를 걸어도 그 안까지 닿지 않는다.
                    → iframe 을 사방 3px 크게 잡고 -3px 로 당겨(overscan) 위젯 테두리를 잘라낸다.
                    래퍼의 overflow:hidden 이 넘친 부분을 먹으므로 모서리가 깔끔해진다. 되돌리지 말 것. */}
                <div
                    style={{
                        width: "100%",
                        height: tvH,
                        borderRadius: 12,
                        overflow: "hidden",
                        background: tvDark ? DARK.bg : LIGHT.bg,
                        lineHeight: 0,
                    }}
                >
                    <iframe
                        key={rawTk + (tvDark ? "-d" : "-l")}
                        title={rawTk + " 차트"}
                        srcDoc={tvWidgetHtml(
                            rawTk,
                            tvDark,
                            tvDark ? DARK.bg : LIGHT.bg
                        )}
                        style={{
                            width: "calc(100% + 6px)",
                            height: "calc(100% + 6px)",
                            margin: -3,
                            border: "none",
                            display: "block",
                            background: tvDark ? DARK.bg : LIGHT.bg,
                        }}
                        loading="lazy"
                        sandbox="allow-scripts allow-same-origin allow-popups"
                    />
                </div>
                {rows.length > 0 && (
                    <div
                        style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: "8px 18px",
                            padding: "0 4px",
                        }}
                    >
                        {rows}
                    </div>
                )}
                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        flexWrap: "wrap",
                        padding: "0 4px",
                    }}
                >
                    <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                            fontSize: 12,
                            fontWeight: 800,
                            color: C.vg,
                            textDecoration: "none",
                        }}
                    >
                        실시간 호가 · 네이버 ↗
                    </a>
                    {/* attribution 의무 — TV 링크 병기(13px 이상) */}
                    <a
                        href={
                            "https://www.tradingview.com/symbols/" +
                            encodeURIComponent(rawTk) +
                            "/"
                        }
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                            fontSize: 13,
                            fontWeight: 600,
                            color: C.faint,
                            textDecoration: "none",
                        }}
                    >
                        차트 by TradingView
                    </a>
                </div>
            </div>
        )
    }
    const renderSkeleton = () => {
        const skBase = C.skBase
        const skHi = C.skHi
        const sh: CSSProperties = {
            background: skBase,
            backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
            backgroundSize: "800px 100%",
            animation: "plcShimmer 1.4s ease-in-out infinite",
        }
        const n = 40
        return (
            <div
                style={{
                    flex: 1,
                    padding: "8px 10px 0",
                    display: "flex",
                    flexDirection: "column",
                }}
            >
                <style>{`@keyframes plcShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div
                    style={{
                        flex: 1,
                        display: "flex",
                        alignItems: "flex-end",
                        gap: 3,
                    }}
                >
                    {Array.from({ length: n }).map((_, i) => {
                        const bh = 26 + ((i * 41 + 17) % 64)
                        return (
                            <div
                                key={i}
                                style={{
                                    flex: 1,
                                    height: bh + "%",
                                    borderRadius: 3,
                                    ...sh,
                                }}
                            />
                        )
                    })}
                </div>
                <div
                    style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginTop: 10,
                        marginBottom: 6,
                    }}
                >
                    {Array.from({ length: 4 }).map((_, i) => (
                        <div
                            key={i}
                            style={{
                                width: 38,
                                height: 9,
                                borderRadius: 4,
                                ...sh,
                            }}
                        />
                    ))}
                </div>
            </div>
        )
    }

    return (
        <div ref={wrapRef} style={wrap}>
            <style>{AN_PALETTE}</style>
            {/* 헤더 — 전일 종가·등락 + 52주 + 기간탭 (정직: T+1 전일까지).
                🚨 해외 종목에서는 통째로 숨긴다. TradingView 위젯이 자체 기간 선택(withdateranges)을
                갖고 있어 우리 탭은 눌러도 아무 일이 없다 — 죽은 버튼을 두면 고장으로 읽힌다(PM 지적). */}
            <div
                style={{
                    display: isForeign ? "none" : "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "0 10px 6px",
                    flexWrap: "wrap",
                }}
            >
                {last && (
                    <>
                        <span
                            style={{
                                fontSize: 17,
                                fontWeight: 800,
                                color: C.ink,
                                letterSpacing: -0.3,
                            }}
                        >
                            {won(last[4])}
                        </span>
                        {lastChg != null && (
                            <span
                                style={{
                                    fontSize: 12.5,
                                    fontWeight: 700,
                                    color:
                                        lastChg > 0
                                            ? C.up
                                            : lastChg < 0
                                              ? C.down
                                              : C.faint,
                                }}
                            >
                                {(lastChg > 0
                                    ? "▲ +"
                                    : lastChg < 0
                                      ? "▼ "
                                      : "") +
                                    lastChg.toFixed(2) +
                                    "%"}
                            </span>
                        )}
                        <span
                            style={{
                                fontSize: 10.5,
                                fontWeight: 700,
                                color: C.faint,
                                background: C.grid,
                                padding: "1px 6px",
                                borderRadius: 5,
                            }}
                        >
                            전일 종가 · {dateDot(last[0])}
                        </span>
                        {view && view.isWeekly && (
                            <span
                                style={{
                                    fontSize: 10,
                                    fontWeight: 700,
                                    color: C.vg,
                                }}
                            >
                                주봉
                            </span>
                        )}
                        {view && (
                            <span
                                style={{
                                    fontSize: 10.5,
                                    fontWeight: 600,
                                    color: C.faint,
                                }}
                            >
                                52주{" "}
                                <span style={{ color: C.hi52 }}>
                                    {Number(view.hi52).toLocaleString()}
                                </span>{" "}
                                /{" "}
                                <span style={{ color: C.lo52 }}>
                                    {Number(view.lo52).toLocaleString()}
                                </span>
                            </span>
                        )}
                    </>
                )}
                <span
                    style={{
                        marginLeft: "auto",
                        display: "inline-flex",
                        gap: 2,
                    }}
                >
                    {RANGES.map(rangeTab)}
                </span>
            </div>

            {cv && view ? (
                <>
                    <div
                        ref={svgRef}
                        style={{
                            position: "relative",
                            width: "100%",
                            touchAction: "pan-y",
                        }}
                        onMouseMove={(e) => setHoverFromX(e.clientX)}
                        onMouseLeave={() => setHoverIdx(null)}
                        onTouchStart={(e) => {
                            if (e.touches[0])
                                setHoverFromX(e.touches[0].clientX)
                        }}
                        onTouchMove={(e) => {
                            if (e.touches[0])
                                setHoverFromX(e.touches[0].clientX)
                        }}
                    >
                        <svg
                            viewBox={`0 0 ${cv.W} ${cv.H}`}
                            width="100%"
                            height={cv.H}
                            preserveAspectRatio="none"
                            style={{ display: "block" }}
                        >
                            <line
                                x1={0}
                                y1={cv.yP(cv.pmax)}
                                x2={cv.W}
                                y2={cv.yP(cv.pmax)}
                                strokeWidth={1}
                                style={{ stroke: C.grid }}
                            />
                            <line
                                x1={0}
                                y1={cv.yP((cv.pmax + cv.pmin) / 2)}
                                x2={cv.W}
                                y2={cv.yP((cv.pmax + cv.pmin) / 2)}
                                strokeWidth={1}
                                style={{ stroke: C.grid }}
                            />
                            <line
                                x1={0}
                                y1={cv.yP(cv.pmin)}
                                x2={cv.W}
                                y2={cv.yP(cv.pmin)}
                                strokeWidth={1}
                                style={{ stroke: C.grid }}
                            />
                            {/* 52주 고저 점선 (가격축 범위 안 + MAX 아님) */}
                            {!view.isMax &&
                                view.hi52 <= cv.pmax &&
                                view.hi52 >= cv.pmin && (
                                    <line
                                        x1={0}
                                        y1={cv.yP(view.hi52)}
                                        x2={cv.W}
                                        y2={cv.yP(view.hi52)}
                                        strokeWidth={1}
                                        strokeOpacity={0.5}
                                        strokeDasharray="4 4"
                                        vectorEffect="non-scaling-stroke"
                                        style={{ stroke: C.hi52 }}
                                    />
                                )}
                            {!view.isMax &&
                                view.lo52 <= cv.pmax &&
                                view.lo52 >= cv.pmin && (
                                    <line
                                        x1={0}
                                        y1={cv.yP(view.lo52)}
                                        x2={cv.W}
                                        y2={cv.yP(view.lo52)}
                                        strokeWidth={1}
                                        strokeOpacity={0.5}
                                        strokeDasharray="4 4"
                                        vectorEffect="non-scaling-stroke"
                                        style={{ stroke: C.lo52 }}
                                    />
                                )}
                            {/* ETF = 종가 라인(+면적) · NAV 점선 / 주식 = 캔들. 막대 = 순자산 or 거래량 */}
                            {isEtf
                                ? cv.items.map((cd: any, i: number) =>
                                      cv.Hv > 0 ? (
                                          <rect
                                              key={i}
                                              x={cd.x - cv.cw / 2}
                                              y={cd.volTop}
                                              width={cv.cw}
                                              height={cd.volH}
                                              fillOpacity={0.3}
                                              style={{
                                                  fill: cd.upDay
                                                      ? C.up
                                                      : C.down,
                                              }}
                                          />
                                      ) : null
                                  )
                                : cv.items.map((cd: any, i: number) => {
                                      const col = cd.upDay ? C.up : C.down
                                      const bodyTop = Math.min(cd.oy, cd.cy)
                                      const bodyH = Math.max(
                                          0.8,
                                          Math.abs(cd.oy - cd.cy)
                                      )
                                      return (
                                          <g key={i}>
                                              {cv.Hv > 0 && (
                                                  <rect
                                                      x={cd.x - cv.cw / 2}
                                                      y={cd.volTop}
                                                      width={cv.cw}
                                                      height={cd.volH}
                                                      fillOpacity={0.35}
                                                      style={{ fill: col }}
                                                  />
                                              )}
                                              <line
                                                  x1={cd.x}
                                                  y1={cd.hy}
                                                  x2={cd.x}
                                                  y2={cd.ly}
                                                  strokeWidth={1}
                                                  vectorEffect="non-scaling-stroke"
                                                  style={{ stroke: col }}
                                              />
                                              <rect
                                                  x={cd.x - cv.cw / 2}
                                                  y={bodyTop}
                                                  width={Math.max(1, cv.cw)}
                                                  height={bodyH}
                                                  style={{ fill: col }}
                                              />
                                          </g>
                                      )
                                  })}
                            {isEtf && cv.closeArea && (
                                <path
                                    d={cv.closeArea}
                                    stroke="none"
                                    fillOpacity={0.1}
                                    style={{ fill: C.vg }}
                                />
                            )}
                            {isEtf && cv.closeLine && (
                                <path
                                    d={cv.closeLine}
                                    fill="none"
                                    strokeWidth={1.8}
                                    vectorEffect="non-scaling-stroke"
                                    style={{ stroke: C.vg }}
                                />
                            )}
                            {isEtf && cv.navLine && (
                                <path
                                    d={cv.navLine}
                                    fill="none"
                                    strokeWidth={1.2}
                                    strokeDasharray="3 3"
                                    vectorEffect="non-scaling-stroke"
                                    style={{ stroke: C.ma20 }}
                                />
                            )}
                            {/* 이동평균선 5/20/60 */}
                            {cv.p60 && (
                                <path
                                    d={cv.p60}
                                    fill="none"
                                    strokeWidth={1.2}
                                    strokeOpacity={0.9}
                                    vectorEffect="non-scaling-stroke"
                                    style={{ stroke: C.ma60 }}
                                />
                            )}
                            {cv.p20 && (
                                <path
                                    d={cv.p20}
                                    fill="none"
                                    strokeWidth={1.2}
                                    strokeOpacity={0.9}
                                    vectorEffect="non-scaling-stroke"
                                    style={{ stroke: C.ma20 }}
                                />
                            )}
                            {cv.p5 && (
                                <path
                                    d={cv.p5}
                                    fill="none"
                                    strokeWidth={1.2}
                                    strokeOpacity={0.9}
                                    vectorEffect="non-scaling-stroke"
                                    style={{ stroke: C.ma5 }}
                                />
                            )}
                            {hov && (
                                <>
                                    <line
                                        x1={hovX}
                                        y1={0}
                                        x2={hovX}
                                        y2={cv.H}
                                        strokeWidth={1}
                                        strokeOpacity={0.45}
                                        vectorEffect="non-scaling-stroke"
                                        style={{ stroke: C.faint }}
                                    />
                                    <circle
                                        cx={hovX}
                                        cy={cv.yP(hov[4])}
                                        r={4}
                                        strokeWidth={1.5}
                                        style={{
                                            fill:
                                                hov[4] >= hov[1]
                                                    ? C.up
                                                    : C.down,
                                            stroke: C.bg,
                                        }}
                                    />
                                </>
                            )}
                        </svg>
                        <span
                            style={{
                                position: "absolute",
                                top: 2,
                                right: 4,
                                fontSize: 10,
                                fontWeight: 600,
                                color: C.faint,
                                background: C.bg,
                                padding: "0 3px",
                                borderRadius: 4,
                            }}
                        >
                            {Number(cv.pmax).toLocaleString()}
                        </span>
                        <span
                            style={{
                                position: "absolute",
                                top: cv.Hp - 14 + "px",
                                right: 4,
                                fontSize: 10,
                                fontWeight: 600,
                                color: C.faint,
                                background: C.bg,
                                padding: "0 3px",
                                borderRadius: 4,
                            }}
                        >
                            {Number(cv.pmin).toLocaleString()}
                        </span>

                        {/* 크로스헤어 플로팅 카드 (토스풍 컴팩트) */}
                        {hov && (
                            <div
                                style={{
                                    position: "absolute",
                                    top: 2,
                                    left: cardLeftPct + "%",
                                    transform: cardFlip
                                        ? "translateX(calc(-100% - 8px))"
                                        : "translateX(8px)",
                                    background: C.card,
                                    border: `1px solid ${C.tipBd}`,
                                    borderRadius: 10,
                                    boxShadow: "0 8px 24px rgba(0,0,0,0.14)",
                                    padding: "7px 9px",
                                    minWidth: 122,
                                    zIndex: 30,
                                    pointerEvents: "none",
                                }}
                            >
                                <div
                                    style={{
                                        fontSize: 12,
                                        fontWeight: 600,
                                        color: C.ink,
                                        marginBottom: 4,
                                        letterSpacing: "-0.2px",
                                    }}
                                >
                                    {dateDot(hov[0])}
                                </div>
                                {isEtf ? (
                                    <>
                                        {tipRow("종가", won(hov[4]))}
                                        {hov.length > 6 &&
                                            hov[6] > 0 &&
                                            tipRow("NAV", won(hov[6]), C.ma20)}
                                        {hov.length > 6 &&
                                            hov[6] > 0 &&
                                            (() => {
                                                const dv =
                                                    ((hov[4] - hov[6]) /
                                                        hov[6]) *
                                                    100
                                                return tipRow(
                                                    "괴리율",
                                                    (dv > 0 ? "+" : "") +
                                                        dv.toFixed(2) +
                                                        "%",
                                                    Math.abs(dv) >= 0.5
                                                        ? C.up
                                                        : C.faint
                                                )
                                            })()}
                                        {tipRow("순자산", fmtAmt(hov[5]))}
                                    </>
                                ) : (
                                    <>
                                        {tipRow("시가", won(hov[1]))}
                                        {tipRow("종가", won(hov[4]))}
                                        {tipRow("최고", won(hov[2]), C.up)}
                                        {tipRow("최저", won(hov[3]), C.down)}
                                        {tipRow("거래량", fmtVol(hov[5]))}
                                    </>
                                )}
                                {hovChg != null &&
                                    tipRow(
                                        "등락률",
                                        (hovChg > 0 ? "+" : "") +
                                            hovChg.toFixed(2) +
                                            "%",
                                        hovChg > 0
                                            ? C.up
                                            : hovChg < 0
                                              ? C.down
                                              : C.faint
                                    )}
                            </div>
                        )}
                    </div>
                    {/* 날짜축 */}
                    <div
                        style={{
                            position: "relative",
                            height: 14,
                            margin: "2px 2px 0",
                        }}
                    >
                        {cv.tickIdx.map((ti: number, i: number) => {
                            const lp = (cv.xAt(ti) / cv.W) * 100
                            const tf =
                                i === 0
                                    ? "translateX(0)"
                                    : i === cv.tickIdx.length - 1
                                      ? "translateX(-100%)"
                                      : "translateX(-50%)"
                            return (
                                <span
                                    key={i}
                                    style={{
                                        position: "absolute",
                                        left: lp + "%",
                                        transform: tf,
                                        fontSize: 10,
                                        fontWeight: 500,
                                        color: C.faint,
                                        whiteSpace: "nowrap",
                                    }}
                                >
                                    {candles[ti] ? mmdd(candles[ti][0]) : ""}
                                </span>
                            )
                        })}
                    </div>
                    {/* 푸터 — MA 범례 + 정직 라벨 + 네이버 실시간 */}
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 10,
                            padding: "5px 10px 4px",
                            flexWrap: "wrap",
                        }}
                    >
                        {isEtf ? (
                            <>
                                {maChip("종가", C.vg)}
                                {maChip("NAV", C.ma20)}
                                {showVolume !== false && maChip("순자산", C.up)}
                            </>
                        ) : (
                            !view.isMax && (
                                <>
                                    {maChip("MA5", C.ma5)}
                                    {maChip("MA20", C.ma20)}
                                    {maChip("MA60", C.ma60)}
                                </>
                            )
                        )}
                        <span
                            style={{
                                fontSize: 10,
                                color: C.faint,
                                fontWeight: 500,
                            }}
                        >
                            {isEtf
                                ? (view.isWeekly ? "주봉" : "일봉") +
                                  " · 전일까지 · KRX OpenAPI (T+1)"
                                : (view.isMax
                                      ? view.isWeekly
                                          ? "주봉 · 전체 기간 (2020~)"
                                          : "일봉 · 전체 기간"
                                      : "일봉") +
                                  " · 전일까지 · 금융위 공공데이터 (T+1)"}
                        </span>
                        {tk && (
                            <a
                                href={naverUrl(tk)}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                    marginLeft: "auto",
                                    fontSize: 11,
                                    fontWeight: 800,
                                    color: C.vg,
                                    textDecoration: "none",
                                }}
                            >
                                실시간 호가·차트 · 네이버 ↗
                            </a>
                        )}
                    </div>
                </>
            ) : isForeign ? (
                renderForeign()
            ) : noData || (!tk && !onCanvas) ? (
                renderEmpty()
            ) : (
                renderSkeleton()
            )}
        </div>
    )
}

addPropertyControls(PublicLiveChart, {
    ticker: { type: ControlType.String, title: "Ticker", defaultValue: "" },
    chartBase: {
        type: ControlType.String,
        title: "Chart Base",
        defaultValue: DEFAULT_BASE,
    },
    height: {
        type: ControlType.Number,
        title: "Height(fallback)",
        defaultValue: 480,
        min: 220,
        max: 800,
        step: 10,
    },
    usChartHeight: {
        type: ControlType.Number,
        title: "해외 차트 높이",
        defaultValue: 460,
        min: 240,
        max: 900,
        step: 10,
    },
    showVolume: {
        type: ControlType.Boolean,
        title: "Volume",
        defaultValue: true,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark(미사용)",
        defaultValue: false,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
})


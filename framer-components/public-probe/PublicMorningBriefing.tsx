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
 * 시장 브리핑 — 홈 최상단 단일 채널 (PM 2026-07-05 · 2026-07-11 통합 지시).
 *
 * 🚨 2026-07-28 상시 갱신 전환 (PM: "모닝 브리핑에서 모닝을 빼고 수시로 체크하는거지.
 *   사용자가 들어올때마다 전체적인 시장 상황을 짐작 및 이해할 수 있게").
 *   · publish_at 07:30 embargo 폐기 — 받는 즉시 노출.
 *   · 제호 "모닝 브리핑" → "시장 브리핑", 부제 = 장 상태 + "N분 전 갱신".
 *   · 탭 복귀(visibilitychange/focus) + 5분 폴링 재조회.
 *   · KR 지수·섹터는 금융위 공공데이터 T+1 이라 오늘 종가가 아니다 → 섹션 부제에
 *     "MM.DD 종가 기준" 을 찍어 오늘 것으로 오독하지 않게 한다.
 *   구성 = 제호(카드 밖) + [① 내 자산 카드] + [② 시장 브리핑 카드] — 형제 카드 2장.
 *   🚨 2026-07-11 PM: 사파리 창/신문 제호 목업 제거 — 토스식 플랫 카드, 정보 가독성 우선.
 *      기존 PublicDailyBriefing(s1NvKbN) 데이터 로직(1면 배너·섹션·mover·접힘·cache-fallback) 이식,
 *      연출(스트림 애니·창 크롬·마스트헤드)만 제거. s1NvKbN 인스턴스는 홈에서 제거(코드파일 보존).
 *   🚨 2026-07-11 PM 가독성 1차 — 통합 카드 1장(블록 7개) = 섹션 경계 소실. 처방 3종:
 *      (a) 카드 2장 분할 — 개인(자산) / 시장 = 성격이 다름. 중첩 tint 박스는 카드로 승격.
 *      (b) 보라(C.vg) = 액션 전용 — 종목명 보라 800 이 섹션 제목(검정 800)보다 튀어 위계가 역전됨.
 *          종목명 = C.ink 700 + 흐린 밑줄(클릭 어포던스). 보라는 버튼/CTA 에만.
 *      (c) 섹션 경계 = hairline + 여백. 섹션 사이:안 = 32:7 (기존 15:7 = 근접성 대비 부족).
 *   🚨 2026-07-11 PM 가독성 2차 — 보라 회수 후 "전부 검정, 폰트 크기만 다름" = 위계 축이 1개뿐.
 *      처방 = 명도 위계. 검정 = 희소 자원으로 회수.
 *      · 라벨(섹션 제목 · 코스피/코스닥 지수명) = 회색 캡션 (C.sub / C.faint + letterSpacing) 으로 후퇴.
 *      · 검정(C.ink) = 콘텐츠에만 — 1면 헤드라인 · 종목명 · 자산 총액.
 *      · 숫자(등락%) = 이미 등락색(빨강/파랑) 보유 → 라벨이 물러날수록 대비가 살아남.
 *
 * ① 내 자산 — 사용자 개인 보유종목 (VERITY 시스템 성과 아님). PublicHoldingsTab 계산 재사용.
 *   인증 — localStorage["verity_supabase_session"].access_token → /api/holdings.
 *   총 자산 = Σ(종가 × 수량), 종가 = kr_close_latest.json(금융위 공공데이터, 전 종목 동일 거래일)
 *     → h.price → avg_cost graceful. 🚨 stock_flow_5d 로 되돌리지 말 것 (2026-08-01 오표시).
 *   전일 증감 = Σ(종가 − 전일 종가) × 수량 — 🚨 전일 "종가" 대비만(실시간 아님).
 *     시세 재배포 컴플라이언스(2026-07-03 Phase 1.5): 실시간 폴링 0, EOD 종가 재사용만.
 *     KR 한정 → 증감 집계 = 국내 커버 종목만(US·미커버 = 총액엔 포함, 증감 제외).
 *   미로그인(라이브) = 컴팩트 CTA 한 줄. 캔버스 = SAMPLE 미리보기.
 *
 * ② 시장 브리핑 — daily_briefing.json (빌더 미착수 → 라이브 404 시 "준비 중" 한 줄, SAMPLE 은 캔버스 전용).
 *   1면 recap(지수 레벨+등락%, 금융위 공공데이터) + 섹션(아이템·mover 등락색·"+N건" 접힘).
 *   sessionStorage cache-fallback. 종목 클릭 → stockPath?q=.
 *   상단 중요 소식 = urgent_alerts.json 중 최신 3건. 자동 순환 없이 한 번에 노출하고,
 *   DART 원문 URL이 확인된 항목만 연결한다. 산출물이 72시간 넘게 갱신되지 않으면 섹션을 숨긴다.
 *
 * RULE 6 = LLM 0 (결정론 조립). RULE 7 = 사실만 (점수·추천·매매의견 0), 면책 푸터.
 * KR 등락색 관례 = 상승 빨강 / 하락 파랑. 테마 = body[data-framer-theme] 자가감지. 반응형 = ResizeObserver.
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
    warn: "#ff9500",
    onAccent: "#ffffff",
}
const DARK = {
    bg: "#10141a",
    card: "#171c23",
    ink: "#e3e7ec",
    sub: "#9aa4b1",
    faint: "#828d9b",
    line: "#252b34",
    up: "#f04452",
    down: "#5b9bff",
    vg: "#a99bff",
    vgS: "#241f3a",
    warn: "#ffb340",
    onAccent: "#0f1318",
}
// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-mbr-*)로 발행. 되돌리지 말 것.
//   JS 다크 감지(readBodyDark/MutationObserver)는 첫 페인트를 라이트로 그린 뒤 뒤늦게
//   다크로 바꿔 "부분 라이트" 로 보이는 사고가 반복됐다. body[data-framer-theme] 를 CSS 가
//   직접 받으면 페인트 시점부터 정합이라 그 창 자체가 없어진다.
//   (이미 마이그레이션된 36개 공개 컴포넌트와 동일 문법 — 프레이머 네이티브 테마 정합)
const _ANP = "mbr"
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
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
// 미국주식 KRW 환산 — 실시간 usd_krw(price_pulse) 조회. 폴백=근사값(PublicHoldingsTab 동기).
const FX_FALLBACK = 1500
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
const KR_MK = ["KOSPI", "KOSDAQ", "KONEX"]
const DEFAULT_API = "https://project-yw131.vercel.app"
const CLOSE_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/kr_close_latest.json"
const PULSE_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/price_pulse.json"
const BRIEF_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/daily_briefing.json"
const IMPORTANT_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/urgent_alerts.json"
const PER_SECTION = 3 // 섹션당 기본 노출, 초과 = "+N건" 접힘
const IMPORTANT_LIMIT = 3
const IMPORTANT_MAX_AGE_MS = 72 * 60 * 60 * 1000
const SITE_UPDATE_VERSION = "2026-09-01-home-pulse-v1"
const SITE_UPDATE_READ_KEY = "alphanest_site_update_read"
const SITE_UPDATES = [
    { title: "보유·관심종목 로딩 개선", text: "데이터 확인 전 빈 상태가 먼저 보이던 문제를 개선했습니다.", href: "/nest" },
    { title: "페이지별 읽기 가이드", text: "시장·공시·보유 화면에서 먼저 확인할 순서를 안내합니다.", href: "/market" },
    { title: "종목 변화 센터", text: "가격·사업·고용·자본조달 변화를 기준일과 함께 확인할 수 있습니다.", href: "/stock" },
] as const

interface Props {
    apiBase: string
    loginUrl: string
    holdingsUrl: string
    stockPath: string
    usStockPath: string
    briefUrl: string
    importantUrl: string
    dark: boolean
}

// ── 캔버스/데모 샘플 (실제 숫자 아님) ──
const SAMPLE_HOLD = [
    {
        ticker: "005930",
        name: "삼성전자",
        shares: 100,
        avg_cost: 68000,
        price: 81200,
        market: "kr",
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
        ticker: "NVDA",
        name: "NVIDIA",
        shares: 20,
        avg_cost: 120,
        price: 172.4,
        market: "us",
    },
]
const SAMPLE_PREV: Record<string, number> = {
    "005930": 80720,
    "000660": 242000,
}
const SAMPLE_BRIEF = {
    date: "2026-07-11",
    weekday: "금",
    warnings_n: 0,
    sections: [
        {
            title: "지난 거래일 시장",
            note: "금융위 공공데이터 · 공시 병기 = 사실, 인과 해석 아님",
            recap: {
                date: "07/10",
                kospi: 0.62,
                kosdaq: 1.15,
                kospi_close: 7291.91,
                kosdaq_close: 794.0,
                headline:
                    "코스피는 올랐지만 종목 2,633개 중 1,587개는 내렸어요",
            },
            items: [
                {
                    name: "내린 쪽",
                    text: "경기소비재 -4.5% · 생활소비재 -4.3%",
                },
                { name: "올린 쪽", text: "정보기술 +1.9%" },
                { ticker: "000660", name: "SK하이닉스", text: "거래대금 1위" },
                {
                    ticker: "049960",
                    name: "오픈베이스",
                    text: "+13.2% · 같은 날 공시: 단일판매ㆍ공급계약체결",
                    mover: true,
                },
            ],
        },
        {
            title: "밤사이 미국 공시",
            note: "SEC EDGAR 일일 인덱스 감지분",
            items: [
                {
                    ticker: "CNXC",
                    name: "Concentrix",
                    text: "10-K/Q 재무 공시 제출 → 재무 반영 완료",
                },
            ],
        },
        {
            title: "최근 7일 내부자 변동",
            note: "DART 보고 사실 · 증감 주식수",
            items: [
                {
                    ticker: "402340",
                    name: "SK스퀘어",
                    text: "12,111,300주 매수 (07-01)",
                },
            ],
        },
    ],
    disclaimer:
        "전부 공시·수집 사실과 자체계산 예상 창 · 점수·추천·매매의견 아님",
}
const SAMPLE_IMPORTANT = {
    _meta: { generated_at: "", source: "DART 공시 원문" },
    alerts: [
        {
            ticker: "005930",
            name: "삼성전자",
            type: "disclosure",
            headline: "주요사항보고서 예시",
            label: "주요사항보고",
            date: "2026-09-05",
            source_url: "https://dart.fss.or.kr/",
        },
    ],
}

function getToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const r = localStorage.getItem("verity_supabase_session")
        if (!r) return ""
        const s = JSON.parse(r)
        if (!s || typeof s.access_token !== "string") return ""
        // 🚨 만료 토큰 = 미로그인 취급 (2026-07-14). 공개 페이지엔 refresh 주체가 없어(=/login 만) 만료 방치 →
        //   죽은 토큰으로 401·빈 결과 대신 정직한 로그인 CTA. HoldingsTab getToken 과 동기.
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return ""
        return s.access_token
    } catch {
        return ""
    }
}
function money(v: number): string {
    if (!isFinite(v)) return "—"
    return Math.round(v).toLocaleString("en-US") + "원"
}
function wonCompact(v: number): string {
    const a = Math.abs(Math.round(v))
    const sign = v < 0 ? "-" : ""
    if (a >= 1e8) return sign + (a / 1e8).toFixed(a >= 1e9 ? 0 : 1) + "억원"
    if (a >= 1e4)
        return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만원"
    return sign + a.toLocaleString("en-US") + "원"
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
function isUsMkt(h: any): boolean {
    return (
        h.market === "us" || h.currency === "USD" || flagCode(h.market) === "us"
    )
}
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

function dartSourceUrl(value: any): string {
    try {
        const url = new URL(String(value || ""))
        return url.protocol === "https:" && url.hostname === "dart.fss.or.kr"
            ? url.href
            : ""
    } catch {
        return ""
    }
}

function shortDate(value: any): string {
    const text = String(value || "")
    return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text.slice(5).replace("-", ".") : text
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.

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

export default function PublicMorningBriefing(props: Props) {
    const {
        apiBase,
        loginUrl,
        holdingsUrl,
        stockPath,
        usStockPath,
        briefUrl,
        importantUrl,
        dark,
    } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)

    // ① 내 자산 상태
    const [rows, setRows] = useState<any[]>(SAMPLE_HOLD)
    // 🚨 2026-08-22 — "내 보유 종목 소식". 회원별 서버 발행이 아니라 **전역 색인 1개**를
    //   받아 브라우저가 위 rows(보유) 와 교차한다. 인증·보유목록은 위 /api/holdings 재사용.
    //   🚨 겹침 0이면 **섹션 자체를 렌더하지 않는다** — 빈 섹션이 매일 뜨는 걸 막는 것이
    //   이 설계의 핵심이다(전용 섹션 신설을 처음에 반대했던 이유이고, 그 절충안이다).
    //   RULE 6 = LLM 0(결정론적 교차) · RULE 7 = 공시 제목 원문 + 지분율, 점수·추천 0.
    const [nestIdx, setNestIdx] = useState<Record<string, any> | null>(null)
    const [npsMap, setNpsMap] = useState<Record<string, number> | null>(null)
    const [closes, setCloses] = useState<
        Record<string, { last: number; prev: number | null }>
    >({})
    const [closeDate, setCloseDate] = useState<string>("") // 종가 기준일(kr_close_latest _meta.as_of, 전 종목 공통) — "전일" 대신 실제 날짜 표기
    const [isDemo, setIsDemo] = useState(true)
    const [loading, setLoading] = useState<boolean>(() =>
        onCanvas ? false : !!getToken()
    )
    const [fxRate, setFxRate] = useState<number>(FX_FALLBACK) // 실시간 usd_krw(price_pulse). 폴백=FX_FALLBACK.

    // ② 시장 브리핑 상태
    const [brief, setBrief] = useState<any>(onCanvas ? SAMPLE_BRIEF : null)
    const [importantFeed, setImportantFeed] = useState<any>(
        onCanvas ? SAMPLE_IMPORTANT : null
    )
    const [briefFailed, setBriefFailed] = useState(false)
    const [openSec, setOpenSec] = useState<Record<string, boolean>>({})
    const [, setNowTick] = useState(0) // 경과 시간 표시 갱신용 60초 틱
    const [reloadTick, setReloadTick] = useState(0) // 탭 복귀·5분 폴링 재조회 트리거
    const [pulseIndex, setPulseIndex] = useState(0)
    const [pulsePaused, setPulsePaused] = useState(false)
    const [reduceMotion, setReduceMotion] = useState(false)
    const [updatesOpen, setUpdatesOpen] = useState(false)
    const [updatesUnread, setUpdatesUnread] = useState(false)

    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

    // 반응형 폭
    useEffect(() => {
        if (typeof ResizeObserver === "undefined" || !rootRef.current) return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries) setW(e.contentRect.width)
        })
        ro.observe(rootRef.current)
        return () => ro.disconnect()
    }, [])

    // 테마 자가감지
    // 보유 ∩ 색인 = 내 종목 소식. 🚨 겹침 0이면 아래에서 섹션을 통째로 안 그린다.
    const myNews = useMemo(() => {
        if (!nestIdx || !Array.isArray(rows) || !rows.length) return []
        const out: any[] = []
        for (const h of rows) {
            const tk = String((h && h.ticker) || "")
            if (!tk) continue
            const ent = nestIdx[tk]
            const pct: number = Number(npsMap?.[tk] ?? 0)
            const evs = ent && Array.isArray(ent.ev) ? ent.ev : []
            if (!evs.length && !(pct > 0)) continue
            out.push({
                ticker: tk,
                name: (h && h.name) || (ent && ent.n) || tk,
                nps: pct > 0 ? pct : null,
                ev: evs.slice(0, 2),
            })
        }
        // 공시가 있는 종목을 위로 (국민연금만 있는 건 아래)
        out.sort((a, b) => b.ev.length - a.ev.length)
        return out
    }, [nestIdx, npsMap, rows])

    // 내 종목 소식 재료 — 티커 색인(최근 3일 공시) + 국민연금 대량보유. 각 1회.
    // 🚨 원본 피드(us_disclosure_feed 4.1MB + KR 862KB)를 직접 받지 않는다 — 서버에서
    //   최근 3일·종목당 3건으로 압축한 색인(178KB)을 쓴다.
    // 🚨 국민연금 원천 = 5% 이상 대량보유 공시. 색인에 없다 = "5% 미만" 이지 미보유가 아니다.
    useEffect(() => {
        if (onCanvas) return
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
    }, [onCanvas])

    // 보유종목 로드 (/api/holdings)
    const loadHoldings = useCallback(() => {
        if (onCanvas) return
        const token = getToken()
        if (!token) {
            setIsDemo(true)
            setRows(SAMPLE_HOLD)
            setLoading(false)
            return
        }
        // 🚨 토큰 있으면 즉시 로그인 상태 확정 (isDemo=false) — API 실패해도 "로그인하면…" CTA 뜨는 사고 방지(2026-07-14). SAMPLE 즉시 비움.
        setIsDemo(false)
        setRows([])
        setLoading(true)
        fetch(base + "/api/holdings", {
            headers: { Authorization: "Bearer " + token },
        })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                setRows(
                    Array.isArray(d)
                        ? d
                        : d && Array.isArray(d.holdings)
                          ? d.holdings
                          : []
                )
            })
            .catch(() => setRows([]))
            .finally(() => setLoading(false))
    }, [base, onCanvas])
    // 마운트 + 로그인/로그아웃(verity_auth_change · 다른 탭 storage) 재평가 → 로그인 상태 자동 전환 (HoldingsTab 동기, 2026-07-14).
    // 🚨 홈 마운트가 세션 기록보다 앞서거나 홈에서 로그인 시, 리스너 없으면 데모/CTA 상태에 남음 (본 버그 root cause — HoldingsTab 은 리스너 보유로 정상, MorningBriefing 만 누락).
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

    // 실시간 환율(usd_krw) — price_pulse.indices.usdkrw. 실패 시 폴백 유지(무해).
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(PULSE_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const v =
                    d &&
                    d.indices &&
                    d.indices.usdkrw &&
                    Number(d.indices.usdkrw.value)
                if (alive && v && isFinite(v) && v > 0) setFxRate(v)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas])

    /* 종가(마지막·직전) — kr_close_latest.json (금융위 공공데이터, 전 종목 동일 거래일).
       🚨 되돌리지 말 것 (2026-08-01 총자산·증감 오표시) — 옛 소스 stock_flow_5d.json 은
       시총순 회전 수집(하루 500종목)이라 종목마다 종가 날짜가 다르다(어제~5주 전).
       실측: 1,801종목 중 71% 가 직전 거래일 종가와 불일치, 23% 는 10%+ 괴리.
       총자산이 옛 가격으로 부풀고, 화면의 "N/N 종가 기준" 도 **첫 종목 날짜**를 전체에
       붙인 거짓 표기였다. 지금은 전 종목 공통 as_of 라 표기가 사실과 일치한다.
       증감(전일 대비)도 두 종가가 연속 거래일임이 보장돼야 성립한다(prev 맵). */
    useEffect(() => {
        if (onCanvas || isDemo) return
        let alive = true
        fetch(CLOSE_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const pm = d && d.prices
                if (!alive || !pm || typeof pm !== "object") return
                const pv = (d && d.prev) || {}
                const m: Record<string, { last: number; prev: number | null }> =
                    {}
                for (const tk of Object.keys(pm)) {
                    const last = Number(pm[tk])
                    if (!isFinite(last) || !last) continue
                    const prevRaw = Number(pv[tk])
                    m[tk] = {
                        last,
                        prev: isFinite(prevRaw) && prevRaw ? prevRaw : null,
                    }
                }
                setCloses(m)
                const ao = String((d._meta && d._meta.as_of) || "")
                // "YYYYMMDD" → "YYYY-MM-DD" (표기부가 slice(5) 로 월/일을 뽑는다)
                if (ao.length === 8)
                    setCloseDate(
                        ao.slice(0, 4) +
                            "-" +
                            ao.slice(4, 6) +
                            "-" +
                            ao.slice(6)
                    )
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [isDemo, onCanvas])

    // 시장 브리핑 로드 — sessionStorage cache-fallback (기존 PublicDailyBriefing 이식)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const fallback = () => {
            try {
                const c = sessionStorage.getItem("daily_briefing")
                if (alive && c) {
                    setBrief(JSON.parse(c))
                    return
                }
            } catch (e) {
                /* ignore */
            }
            if (alive) setBriefFailed(true)
        }
        fetch(briefUrl || BRIEF_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                if (d && Array.isArray(d.sections)) {
                    setBrief(d)
                    try {
                        sessionStorage.setItem(
                            "daily_briefing",
                            JSON.stringify(d)
                        )
                    } catch (e) {
                        /* ignore */
                    }
                } else fallback()
            })
            .catch(fallback)
        const onBack = () => {
            if (document.visibilityState === "visible")
                setReloadTick((t) => t + 1)
        }
        document.addEventListener("visibilitychange", onBack)
        window.addEventListener("focus", onBack)
        const poll = setInterval(() => setReloadTick((t) => t + 1), 300000)
        return () => {
            alive = false
            document.removeEventListener("visibilitychange", onBack)
            window.removeEventListener("focus", onBack)
            clearInterval(poll)
        }
    }, [onCanvas, briefUrl, reloadTick])

    // 중요 소식 — 기존 공개 산출물 재사용. 자동 순환·문구 재해석 없이 DART 원문 사실만 노출한다.
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(importantUrl || IMPORTANT_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive && d && Array.isArray(d.alerts)) setImportantFeed(d)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas, importantUrl, reloadTick])

    // 🚨 2026-07-28 상시 갱신 — 옛 embargo(publish_at 07:30 전 숨김) 타이머 폐기.
    //   PM: "모닝 브리핑에서 모닝을 빼고 수시로 체크하는거지." 받는 즉시 노출한다.
    //   경과 시간 표시가 1분 단위로 늙어 보이게 60초 틱만 유지.
    useEffect(() => {
        if (onCanvas) return
        const id = setInterval(() => setNowTick((t) => t + 1), 60000)
        return () => clearInterval(id)
    }, [onCanvas])

    // 제품 업데이트는 버전당 한 번만 자동으로 펼친다. 닫은 뒤에는 상단 버튼으로 다시 볼 수 있다.
    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        let seen = ""
        try { seen = localStorage.getItem(SITE_UPDATE_READ_KEY) || "" } catch {}
        const unread = seen !== SITE_UPDATE_VERSION
        setUpdatesUnread(unread)
        setUpdatesOpen(unread)
        const media = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)")
        const syncMotion = () => setReduceMotion(!!media?.matches)
        syncMotion()
        media?.addEventListener?.("change", syncMotion)
        return () => media?.removeEventListener?.("change", syncMotion)
    }, [onCanvas])

    // ── 내 자산 계산 ──
    const asset = useMemo(() => {
        const usePrev = isDemo ? SAMPLE_PREV : null
        const evald = rows.map((h) => {
            const tk = String(h.ticker)
            const us = isUsMkt(h)
            const fx = us ? fxRate : 1
            const shares = Number(h.shares) || 0
            const q = closes[tk]
            const last = q ? q.last : Number(h.price) || Number(h.avg_cost) || 0
            const prev = q
                ? q.prev
                : usePrev && usePrev[tk] != null
                  ? usePrev[tk]
                  : null
            const val = last * shares * fx
            const dayDelta =
                prev != null && isFinite(prev)
                    ? (last - prev) * shares * fx
                    : null
            const prevVal =
                prev != null && isFinite(prev) ? prev * shares * fx : null
            return {
                tk,
                name: h.name || tk,
                market: h.market,
                us,
                _val: val,
                _day: dayDelta,
                _prevVal: prevVal,
                _dayPct:
                    prev != null && prev ? ((last - prev) / prev) * 100 : null,
            }
        })
        const totalVal = evald.reduce((a, b) => a + (b._val || 0), 0)
        const covered = evald.filter((e) => e._day != null)
        const dayChange = covered.reduce((a, b) => a + (b._day || 0), 0)
        const coveredPrevVal = covered.reduce(
            (a, b) => a + (b._prevVal || 0),
            0
        )
        const dayPct =
            coveredPrevVal > 0 ? (dayChange / coveredPrevVal) * 100 : null
        const hasUncovered = evald.length > covered.length
        const movers = covered
            .slice()
            .sort((a, b) => Math.abs(b._day || 0) - Math.abs(a._day || 0))
            .slice(0, 3)
        return {
            totalVal,
            dayChange,
            dayPct,
            movers,
            hasUncovered,
            count: evald.length,
        }
    }, [rows, closes, isDemo, fxRate])

    const noLogin = !onCanvas && isDemo
    const upC = (v: number) => (v >= 0 ? C.up : C.down)
    const arrow = (v: number) => (v > 0 ? "▲" : v < 0 ? "▼" : "·")
    const narrow = w > 0 && w < 420

    const goHoldings = () => {
        if (typeof window === "undefined") return
        window.location.href = (holdingsUrl || "/holdings").replace(/\/+$/, "")
    }
    const goLogin = () => {
        if (typeof window === "undefined" || !loginUrl) return
        window.location.href = loginUrl
    }
    const goStockTk = (tk: string, us?: boolean) => {
        if (typeof window === "undefined" || !tk) return
        const path = (
            us ? _usPath(usStockPath, stockPath) : stockPath || "/stock"
        ).replace(/\/+$/, "")
        window.location.href = path + "?q=" + encodeURIComponent(tk)
    }

    // ── 브리핑 렌더 준비 (기존 로직 이식) ──
    const pctColor = (v: number) => (v > 0 ? C.up : v < 0 ? C.down : C.sub)
    const fmtPct = (v: number) =>
        (v > 0 ? "+" : "") + Number(v).toFixed(2) + "%"
    const fmtLevel = (v: any) =>
        typeof v === "number" && isFinite(v)
            ? v.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
              })
            : ""
    // mover 행 — "+13.2% · 같은 날 공시: …" 앞 % 만 등락색 분리
    const moverText = (t: string) => {
        const cut = t.indexOf(" · ")
        if (cut < 0)
            return <span style={{ color: C.sub, fontWeight: 600 }}>{t}</span>
        const pct = t.slice(0, cut)
        const rest = t.slice(cut)
        const col =
            pct.indexOf("+") === 0
                ? C.up
                : pct.indexOf("-") === 0 || pct.indexOf("−") === 0
                  ? C.down
                  : C.sub
        return (
            <span style={{ minWidth: 0 }}>
                <span
                    style={{
                        color: col,
                        fontWeight: 800,
                        fontVariantNumeric: "tabular-nums",
                    }}
                >
                    {pct}
                </span>
                <span style={{ color: C.sub, fontWeight: 600 }}>{rest}</span>
            </span>
        )
    }
    const secs: any[] = (brief && brief.sections) || []
    const banner =
        secs.length && secs[0].recap && typeof secs[0].recap.kospi === "number"
            ? secs[0].recap
            : null
    // 발행 시각 = JSON publish_at(고정 조간 07:30) 우선, 없으면 generated_at(실 빌드시각) 폴백. "07:30" 하드코딩 폐기 — gh cron 지연 부정확 방지(2026-07-14).
    const pubHM = (iso: any) => {
        const m = String(iso || "").match(/T(\d{2}:\d{2})/)
        return m ? m[1] : ""
    }
    const pubTime = brief
        ? pubHM(brief.publish_at) || pubHM(brief.generated_at)
        : ""
    // embargo — publish_at(고정 발행시각) 전에는 ② 시장 브리핑을 노출하지 않고 "발행 예정" 표시. 클라 시계로 그 시각에 교체.
    // 🚨 embargo 폐기 (2026-07-28) — 아침 한 번이 아니라 상시. 항상 false.
    const embargoed = false
    // 신선도 = "몇 분 전 갱신". 고정 발행 시각 표기는 상시 갱신과 맞지 않는다.
    const agoText = (iso: any) => {
        const t = Date.parse(String(iso || ""))
        if (!isFinite(t)) return ""
        const mins = Math.floor((Date.now() - t) / 60000)
        if (mins < 1) return "방금 갱신"
        if (mins < 60) return mins + "분 전 갱신"
        const hrs = Math.floor(mins / 60)
        if (hrs < 24) return hrs + "시간 전 갱신"
        return Math.floor(hrs / 24) + "일 전 갱신"
    }
    const SESSL: Record<string, string> = {
        장전: "장 시작 전",
        장중: "장중",
        장마감: "장 마감",
        휴장: "휴장",
    }
    const dateLine = brief
        ? [
              brief.session ? SESSL[String(brief.session)] || "" : "",
              agoText(brief.generated_at),
          ]
              .filter(Boolean)
              .join(" · ")
        : "수시 갱신"

    // 생산자가 정한 순서를 그대로 사용한다. 원문 링크가 없거나 피드가 72시간 넘게 멈추면 미노출.
    const importantNews: any[] = (() => {
        if (!importantFeed || !Array.isArray(importantFeed.alerts)) return []
        const generated = Date.parse(String(importantFeed?._meta?.generated_at || ""))
        if (
            !onCanvas &&
            (!isFinite(generated) || Date.now() - generated > IMPORTANT_MAX_AGE_MS)
        )
            return []
        return importantFeed.alerts
            .filter(
                (item: any) =>
                    item &&
                    String(item.headline || "").trim() &&
                    dartSourceUrl(item.source_url)
            )
            .slice(0, IMPORTANT_LIMIT)
    })()

    // 기존 브리핑 응답만 재사용한다. 별도 API·Blob 요청을 추가하지 않는다.
    const pulseItems = useMemo(() => {
        const items: Array<{ text: string; href?: string }> = []
        if (brief) {
            const factCount = ((brief.sections || []) as any[]).reduce(
                (sum, section) => sum + (Array.isArray(section?.items) ? section.items.length : 0),
                0
            )
            if (factCount > 0) items.push({ text: `시장 브리핑 반영 사실 ${factCount}건 · ${dateLine}` })
            if (banner?.date) items.push({ text: `시장 지수·업종 ${banner.date} 종가 기준`, href: "/market" })
        }
        if (!isDemo && myNews.length > 0) items.push({ text: `내 보유 종목 새 소식 ${myNews.length}종목 · 최근 3일`, href: "/nest" })
        items.push({ text: `새 기능 ${SITE_UPDATES.length}건 · 업데이트 내용 보기` })
        return items
    }, [brief, banner?.date, dateLine, isDemo, myNews.length])

    useEffect(() => {
        if (pulseIndex >= pulseItems.length) setPulseIndex(0)
    }, [pulseIndex, pulseItems.length])

    useEffect(() => {
        if (onCanvas || reduceMotion || pulsePaused || pulseItems.length < 2) return
        const id = setInterval(() => setPulseIndex((index) => (index + 1) % pulseItems.length), 7000)
        return () => clearInterval(id)
    }, [onCanvas, pulseItems.length, pulsePaused, reduceMotion])

    const markUpdatesRead = () => {
        try { localStorage.setItem(SITE_UPDATE_READ_KEY, SITE_UPDATE_VERSION) } catch {}
        setUpdatesUnread(false)
    }

    const toggleUpdates = () => {
        const next = !updatesOpen
        setUpdatesOpen(next)
        if (next || updatesUnread) markUpdatesRead()
    }

    // 카드 밖 제호 + 형제 카드 2장 (개인 / 시장). 중첩 카드 회피.
    const shell: CSSProperties = {
        fontFamily: FONT,
        width: "100%",
        boxSizing: "border-box",
        color: C.ink,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: "8px clamp(14px, 2vw, 20px) 20px",
    }
    const card: CSSProperties = {
        background: C.card,
        borderRadius: 16,
        padding: narrow ? "14px 14px" : "18px 18px",
        boxSizing: "border-box",
    }
    const cta: CSSProperties = {
        ...card,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 10,
        padding: narrow ? "15px 16px" : "16px 18px",
        cursor: "pointer",
    }
    // 명도 위계 — 라벨(섹션 제목·지수명)은 회색 캡션으로 물러나고, 검정은 콘텐츠(헤드라인·종목명)에만.
    // 크기만 다른 검정 일색 = 위계 축이 1개뿐 → 안 읽힘 (PM 2026-07-11 2차 지적).
    const secTitle: CSSProperties = {
        fontSize: 11.5,
        fontWeight: 800,
        color: C.sub,
        letterSpacing: "0.6px",
    }
    const secNote: CSSProperties = {
        fontSize: 11,
        fontWeight: 600,
        color: C.faint,
    }
    const idxLabel: CSSProperties = {
        fontSize: 11.5,
        fontWeight: 700,
        color: C.faint,
        letterSpacing: "0.4px",
    }

    return (
        <div ref={rootRef} style={shell}>
            <style>{AN_PALETTE}</style>
            {/* 제호 — 카드 밖 (카드 2장을 하나의 채널로 묶는 역할) */}
            <div
                style={{
                    display: "flex",
                    alignItems: "baseline",
                    justifyContent: "space-between",
                    gap: 8,
                    padding: "0 4px",
                }}
            >
                <span
                    style={{
                        fontSize: 18,
                        fontWeight: 800,
                        letterSpacing: "-0.4px",
                    }}
                >
                    시장 브리핑
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: 7, flexShrink: 0 }}>
                    <span style={{ fontSize: 11.5, fontWeight: 600, color: C.faint, whiteSpace: "nowrap" }}>{dateLine}</span>
                    <button
                        type="button"
                        onClick={toggleUpdates}
                        aria-expanded={updatesOpen}
                        aria-controls="site-update-panel"
                        style={{ border: "none", borderRadius: 999, padding: "5px 8px", background: updatesUnread ? C.vg : C.vgS, color: updatesUnread ? C.onAccent : C.vg, fontFamily: FONT, fontSize: 10.5, fontWeight: 800, cursor: "pointer", whiteSpace: "nowrap" }}
                    >
                        업데이트 {updatesUnread ? "NEW" : SITE_UPDATES.length}
                    </button>
                </div>
            </div>

            {/* 데이터 활동 스트립 — 브리핑에 이미 내려온 사실만 순환. 연속 전광판·추가 요청 없음. */}
            <div
                role="status"
                aria-live="polite"
                onMouseEnter={() => setPulsePaused(true)}
                onMouseLeave={() => setPulsePaused(false)}
                style={{ minHeight: 36, display: "flex", alignItems: "center", gap: 9, background: C.card, borderRadius: 12, padding: "8px 11px", boxSizing: "border-box", overflow: "hidden" }}
            >
                <span style={{ flexShrink: 0, color: C.vg, background: C.vgS, borderRadius: 999, padding: "3px 7px", fontSize: 9.5, fontWeight: 850, letterSpacing: "0.3px" }}>NOW</span>
                <button
                    type="button"
                    onClick={() => {
                        const item = pulseItems[pulseIndex]
                        if (item?.href && typeof window !== "undefined") window.location.href = item.href
                        else if (!updatesOpen) toggleUpdates()
                    }}
                    style={{ minWidth: 0, flex: 1, border: "none", padding: 0, background: "transparent", color: C.sub, fontFamily: FONT, fontSize: 11.5, fontWeight: 700, textAlign: "left", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", cursor: "pointer" }}
                >
                    {pulseItems[pulseIndex]?.text || "AlphaNest 데이터 확인 중"}
                </button>
                {pulseItems.length > 1 && (
                    <span aria-hidden="true" style={{ flexShrink: 0, color: C.faint, fontSize: 9.5, fontVariantNumeric: "tabular-nums" }}>{pulseIndex + 1}/{pulseItems.length}</span>
                )}
            </div>

            {updatesOpen && (
                <section id="site-update-panel" aria-label="AlphaNest 업데이트" style={{ ...card, padding: narrow ? "14px" : "16px 18px" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                        <div>
                            <div style={{ color: C.vg, fontSize: 10.5, fontWeight: 850 }}>ALPHANEST UPDATE</div>
                            <div style={{ marginTop: 3, color: C.ink, fontSize: 15, fontWeight: 800 }}>이번에 달라진 점</div>
                        </div>
                        <button type="button" onClick={() => { setUpdatesOpen(false); markUpdatesRead() }} style={{ border: "none", background: C.bg, color: C.sub, borderRadius: 999, padding: "6px 9px", fontFamily: FONT, fontSize: 10.5, fontWeight: 800, cursor: "pointer" }}>닫기</button>
                    </div>
                    <div style={{ marginTop: 11, display: "grid", gap: 7 }}>
                        {SITE_UPDATES.map((update) => (
                            <a key={update.title} href={update.href} style={{ display: "block", padding: "10px 11px", borderRadius: 11, background: C.bg, color: C.ink, textDecoration: "none" }}>
                                <div style={{ fontSize: 12.5, fontWeight: 800 }}>{update.title}</div>
                                <div style={{ marginTop: 3, color: C.faint, fontSize: 10.5, fontWeight: 600, lineHeight: 1.5 }}>{update.text}</div>
                            </a>
                        ))}
                    </div>
                    <div style={{ marginTop: 9, color: C.faint, fontSize: 10, fontWeight: 600 }}>2026.09.01 · 새 버전일 때 한 번만 자동으로 열립니다.</div>
                </section>
            )}

            {/* ── ① 내 자산 카드 ── */}
            {noLogin ? (
                <div
                    onClick={goLogin}
                    role="button"
                    style={{ ...cta, background: C.vgS }}
                >
                    <div
                        style={{
                            fontSize: 13,
                            fontWeight: 700,
                            color: C.ink,
                            lineHeight: 1.5,
                        }}
                    >
                        <span style={{ color: C.vg }}>내 자산</span> —
                        로그인하면 보유종목 증감을 여기서 바로 볼 수 있어요
                    </div>
                    <span
                        style={{
                            flexShrink: 0,
                            fontSize: 12.5,
                            fontWeight: 800,
                            color: C.vg,
                        }}
                    >
                        로그인 →
                    </span>
                </div>
            ) : loading ? (
                <div
                    style={{
                        ...card,
                        textAlign: "center",
                        color: C.faint,
                        fontSize: 12.5,
                        fontWeight: 600,
                    }}
                >
                    내 자산 불러오는 중…
                </div>
            ) : asset.count === 0 ? (
                <div onClick={goHoldings} role="button" style={cta}>
                    <div
                        style={{ fontSize: 13, fontWeight: 700, color: C.sub }}
                    >
                        보유종목을 추가하면 자산 요약이 여기 떠요
                    </div>
                    <span
                        style={{
                            flexShrink: 0,
                            fontSize: 12.5,
                            fontWeight: 800,
                            color: C.vg,
                        }}
                    >
                        추가 →
                    </span>
                </div>
            ) : (
                <div style={{ ...card, paddingBottom: 0 }}>
                    <div
                        style={{
                            display: "flex",
                            alignItems: "baseline",
                            justifyContent: "space-between",
                            gap: 8,
                        }}
                    >
                        <span
                            style={{
                                fontSize: 11.5,
                                color: C.faint,
                                fontWeight: 700,
                            }}
                        >
                            내 자산
                        </span>
                        <span
                            style={{
                                fontSize: 10.5,
                                color: C.faint,
                                fontWeight: 600,
                            }}
                        >
                            {"평단 입력 기준 · " +
                                (closeDate
                                    ? closeDate.slice(5).replace("-", "/") +
                                      " 종가 기준"
                                    : "전일 종가 대비")}
                        </span>
                    </div>
                    <div
                        style={{
                            fontSize: narrow ? 23 : 26,
                            fontWeight: 800,
                            letterSpacing: "-1px",
                            margin: "3px 0 2px",
                            fontVariantNumeric: "tabular-nums",
                        }}
                    >
                        {money(asset.totalVal)}
                    </div>
                    {asset.dayPct != null ? (
                        <div
                            style={{
                                fontSize: 13.5,
                                fontWeight: 800,
                                color: upC(asset.dayChange),
                                fontVariantNumeric: "tabular-nums",
                            }}
                        >
                            {arrow(asset.dayChange)}{" "}
                            {(asset.dayChange >= 0 ? "+" : "") +
                                wonCompact(asset.dayChange)}{" "}
                            (
                            {(asset.dayPct >= 0 ? "+" : "") +
                                asset.dayPct.toFixed(2)}
                            %)
                            {asset.hasUncovered && (
                                <span
                                    style={{
                                        fontSize: 10.5,
                                        fontWeight: 600,
                                        color: C.faint,
                                        marginLeft: 6,
                                    }}
                                >
                                    국내 종목 기준
                                </span>
                            )}
                        </div>
                    ) : (
                        <div
                            style={{
                                fontSize: 12.5,
                                fontWeight: 700,
                                color: C.faint,
                            }}
                        >
                            종가 데이터 대기
                        </div>
                    )}
                    {/* 움직인 종목 — 컴팩트 행 */}
                    {asset.movers.length > 0 && (
                        <div style={{ marginTop: 10 }}>
                            {asset.movers.map((m: any) => (
                                <div
                                    key={m.tk}
                                    onClick={() => goStockTk(m.tk, m.us)}
                                    role="button"
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        justifyContent: "space-between",
                                        gap: 8,
                                        padding: "8px 0",
                                        borderTop: `1px solid ${C.line}`,
                                        cursor: "pointer",
                                    }}
                                >
                                    <div
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            gap: 7,
                                            minWidth: 0,
                                        }}
                                    >
                                        <FlagIcon
                                            code={flagCode(m.market)}
                                            size={14}
                                        />
                                        <span
                                            style={{
                                                fontSize: 13,
                                                fontWeight: 700,
                                                color: C.ink,
                                                whiteSpace: "nowrap",
                                                overflow: "hidden",
                                                textOverflow: "ellipsis",
                                            }}
                                        >
                                            {m.name}
                                        </span>
                                    </div>
                                    <div
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            gap: 9,
                                            flexShrink: 0,
                                            fontVariantNumeric: "tabular-nums",
                                        }}
                                    >
                                        {m._dayPct != null && (
                                            <span
                                                style={{
                                                    fontSize: 12.5,
                                                    fontWeight: 800,
                                                    color: upC(m._day),
                                                }}
                                            >
                                                {(m._dayPct >= 0 ? "+" : "") +
                                                    m._dayPct.toFixed(1)}
                                                %
                                            </span>
                                        )}
                                        <span
                                            style={{
                                                fontSize: 12,
                                                fontWeight: 700,
                                                color: upC(m._day),
                                                minWidth: 64,
                                                textAlign: "right",
                                            }}
                                        >
                                            {(m._day >= 0 ? "+" : "") +
                                                wonCompact(m._day)}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                    <button
                        onClick={goHoldings}
                        style={{
                            display: "block",
                            width: "100%",
                            background: "transparent",
                            border: "none",
                            borderTop: `1px solid ${C.line}`,
                            padding: "10px 0",
                            fontFamily: FONT,
                            fontSize: 12.5,
                            fontWeight: 800,
                            color: C.vg,
                            cursor: "pointer",
                            textAlign: "center",
                        }}
                    >
                        보유종목 전체 보기 →
                    </button>
                </div>
            )}

            {/* ── ② 시장 브리핑 카드 ── */}
            <div style={card}>
                {!brief ? (
                    <div
                        style={{
                            fontSize: 12.5,
                            color: C.faint,
                            fontWeight: 600,
                        }}
                    >
                        {briefFailed
                            ? "시장 브리핑 준비 중 — 곧 다시 채워져요"
                            : "시장 브리핑 수신 중…"}
                    </div>
                ) : embargoed ? (
                    <div
                        style={{
                            fontSize: 12.5,
                            color: C.faint,
                            fontWeight: 600,
                            lineHeight: 1.6,
                        }}
                    >
                        오늘 시장 브리핑은{" "}
                        <span style={{ color: C.ink, fontWeight: 800 }}>
                            {pubTime || "07:30"}
                        </span>{" "}
                        에 발행돼요
                    </div>
                ) : (
                    <div>
                        {/* 중요 소식 — 정지형 목록. 움직임·자동 넘김 없이 최대 3건을 동시에 보여준다. */}
                        {importantNews.length > 0 && (
                            <section
                                aria-label="중요 소식"
                                style={{
                                    marginBottom: 18,
                                    paddingBottom: 16,
                                    borderBottom: `1px solid ${C.line}`,
                                }}
                            >
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "baseline",
                                        justifyContent: "space-between",
                                        gap: 8,
                                        flexWrap: "wrap",
                                    }}
                                >
                                    <span
                                        style={{
                                            fontSize: 11.5,
                                            fontWeight: 850,
                                            color: C.warn,
                                            letterSpacing: "0.5px",
                                        }}
                                    >
                                        중요 소식
                                    </span>
                                    <span style={secNote}>
                                        DART 원문 · {agoText(importantFeed?._meta?.generated_at)}
                                    </span>
                                </div>
                                <div
                                    style={{
                                        marginTop: 9,
                                        display: "flex",
                                        flexDirection: "column",
                                    }}
                                >
                                    {importantNews.map((item: any, index: number) => {
                                        const href = dartSourceUrl(item.source_url)
                                        const sourceLabel =
                                            item.type === "disclosure"
                                                ? item.label || "공시"
                                                : "임원·주요주주"
                                        return (
                                            <a
                                                key={`${item.ticker || item.name}-${item.date}-${index}`}
                                                href={href}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                style={{
                                                    display: "block",
                                                    padding: index === 0 ? "0 0 10px" : "10px 0",
                                                    borderTop:
                                                        index === 0
                                                            ? "none"
                                                            : `1px solid ${C.line}`,
                                                    color: "inherit",
                                                    textDecoration: "none",
                                                }}
                                            >
                                                <div
                                                    style={{
                                                        display: "flex",
                                                        alignItems: "baseline",
                                                        gap: 7,
                                                        minWidth: 0,
                                                        lineHeight: 1.45,
                                                    }}
                                                >
                                                    <span
                                                        style={{
                                                            flexShrink: 0,
                                                            fontSize: 12.5,
                                                            fontWeight: 800,
                                                            color: C.ink,
                                                        }}
                                                    >
                                                        {item.name || item.ticker}
                                                    </span>
                                                    <span
                                                        style={{
                                                            minWidth: 0,
                                                            fontSize: 12.5,
                                                            fontWeight: 650,
                                                            color: C.sub,
                                                        }}
                                                    >
                                                        {item.headline}
                                                    </span>
                                                </div>
                                                <div
                                                    style={{
                                                        marginTop: 3,
                                                        fontSize: 10.5,
                                                        fontWeight: 650,
                                                        color: C.faint,
                                                    }}
                                                >
                                                    {sourceLabel} · {shortDate(item.date)} · 원문 보기 ↗
                                                </div>
                                            </a>
                                        )
                                    })}
                                </div>
                            </section>
                        )}

                        {/* 1면 배너 — 지수 레벨 + 큰 등락% + 흐름 한 줄. 구분선은 아래 섹션이 각자 소유 */}
                        {banner && (
                            <div>
                                <div
                                    style={{
                                        display: "flex",
                                        gap: narrow ? 20 : 28,
                                        alignItems: "flex-end",
                                        flexWrap: "wrap",
                                    }}
                                >
                                    {[
                                        [
                                            "코스피",
                                            banner.kospi,
                                            banner.kospi_close,
                                        ],
                                        [
                                            "코스닥",
                                            banner.kosdaq,
                                            banner.kosdaq_close,
                                        ],
                                    ].map(([lb, pct, lv]: any) => (
                                        <div key={lb}>
                                            <div
                                                style={{
                                                    display: "flex",
                                                    alignItems: "baseline",
                                                    gap: 6,
                                                }}
                                            >
                                                <span style={idxLabel}>
                                                    {lb}
                                                </span>
                                                {fmtLevel(lv) && (
                                                    <span
                                                        style={{
                                                            fontSize: 11.5,
                                                            fontWeight: 600,
                                                            color: C.faint,
                                                            fontVariantNumeric:
                                                                "tabular-nums",
                                                        }}
                                                    >
                                                        {fmtLevel(lv)}
                                                    </span>
                                                )}
                                            </div>
                                            <div
                                                style={{
                                                    marginTop: 2,
                                                    fontSize: narrow ? 22 : 25,
                                                    fontWeight: 800,
                                                    letterSpacing: "-0.7px",
                                                    color: pctColor(pct),
                                                    fontVariantNumeric:
                                                        "tabular-nums",
                                                    lineHeight: 1.1,
                                                }}
                                            >
                                                {fmtPct(pct)}
                                            </div>
                                        </div>
                                    ))}
                                    <div
                                        style={{
                                            marginLeft: "auto",
                                            alignSelf: "flex-start",
                                            fontSize: 10.5,
                                            fontWeight: 600,
                                            color: C.faint,
                                            whiteSpace: "nowrap",
                                        }}
                                    >
                                        {banner.date} 종가
                                        {Number(brief.warnings_n) > 0
                                            ? " · 시장경보 " + brief.warnings_n
                                            : ""}
                                    </div>
                                </div>
                                {banner.headline && (
                                    <div
                                        style={{
                                            marginTop: 9,
                                            fontSize: narrow ? 14 : 15,
                                            fontWeight: 800,
                                            letterSpacing: "-0.2px",
                                            color: C.ink,
                                            lineHeight: 1.45,
                                        }}
                                    >
                                        {banner.headline}
                                    </div>
                                )}
                            </div>
                        )}

                        {/* 내 종목 소식 — 🚨 겹침 0이면 렌더 안 함(빈 섹션 방지).
                            데모/캔버스에서도 안 그린다(가짜 개인화 방지). */}
                        {!isDemo && myNews.length > 0 && (
                            <div style={{ marginBottom: 32 }}>
                                <div
                                    style={{
                                        fontSize: 11.5,
                                        fontWeight: 800,
                                        color: C.sub,
                                        letterSpacing: "0.3px",
                                        marginBottom: 10,
                                    }}
                                >
                                    내 보유 종목 소식
                                    <span
                                        style={{
                                            color: C.faint,
                                            fontWeight: 700,
                                            marginLeft: 6,
                                        }}
                                    >
                                        {myNews.length}종목 · 최근 3일 공시
                                    </span>
                                </div>
                                <div
                                    style={{
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: 7,
                                    }}
                                >
                                    {myNews.map((m: any) => (
                                        <div key={m.ticker}>
                                            <div
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: 6,
                                                    flexWrap: "wrap",
                                                }}
                                            >
                                                <span
                                                    style={{
                                                        fontSize: 13.5,
                                                        fontWeight: 700,
                                                        color: C.ink,
                                                    }}
                                                >
                                                    {m.name}
                                                </span>
                                                {m.nps != null && (
                                                    <span
                                                        style={{
                                                            fontSize: 10.5,
                                                            fontWeight: 700,
                                                            color: C.sub,
                                                            background: C.line,
                                                            borderRadius: 999,
                                                            padding: "2px 7px",
                                                        }}
                                                        title="국민연금 5% 이상 대량보유 공시 기준"
                                                    >
                                                        국민연금{" "}
                                                        {m.nps.toFixed(2)}%
                                                    </span>
                                                )}
                                            </div>
                                            {m.ev.map((e: any, i: number) => (
                                                <div
                                                    key={i}
                                                    style={{
                                                        fontSize: 11.5,
                                                        color: C.sub,
                                                        fontWeight: 600,
                                                        marginTop: 2,
                                                        lineHeight: 1.45,
                                                    }}
                                                >
                                                    {String(e.d || "").slice(5)}{" "}
                                                    · {String(e.t || "")}
                                                </div>
                                            ))}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* 섹션들 */}
                        {secs.map((s: any, si: number) => {
                            const isBannerSec = si === 0 && !!banner
                            const allItems: any[] = (s.items || []).filter(
                                (it: any) =>
                                    !isBannerSec ||
                                    (it.name !== "지수" && it.name !== "흐름")
                            )
                            const open = !!openSec[s.title]
                            const items = open
                                ? allItems
                                : allItems.slice(0, PER_SECTION)
                            const extra = allItems.length - PER_SECTION
                            const firstMover = items.findIndex(
                                (it: any) => it.mover
                            )
                            if (!allItems.length && !isBannerSec) return null
                            // 섹션 경계 = hairline + 여백 16/16 (사이 32 : 안 7 ≈ 4.5배). 첫 섹션이 카드 최상단이면 선 없음.
                            const divided = !(si === 0 && !banner)
                            return (
                                <div
                                    key={si}
                                    style={{
                                        marginTop: divided ? 16 : 0,
                                        paddingTop: divided ? 16 : 0,
                                        borderTop: divided
                                            ? `1px solid ${C.line}`
                                            : "none",
                                    }}
                                >
                                    <div
                                        style={{
                                            display: "flex",
                                            alignItems: "baseline",
                                            gap: 8,
                                            flexWrap: "wrap",
                                        }}
                                    >
                                        <span style={secTitle}>{s.title}</span>
                                        <span style={secNote}>
                                            {isBannerSec
                                                ? (s.as_of
                                                      ? String(s.as_of).slice(
                                                            4,
                                                            6
                                                        ) +
                                                        "." +
                                                        String(s.as_of).slice(
                                                            6,
                                                            8
                                                        ) +
                                                        " 종가 기준 · "
                                                      : "") +
                                                  "섹터 · 거래대금 · 같은 날 공시"
                                                : s.note}
                                        </span>
                                    </div>
                                    <div
                                        style={{
                                            marginTop: 8,
                                            display: "flex",
                                            flexDirection: "column",
                                            gap: 7,
                                        }}
                                    >
                                        {items.map((it: any, i: number) => (
                                            <div key={i}>
                                                {isBannerSec &&
                                                    it.mover &&
                                                    i === firstMover && (
                                                        <div
                                                            style={{
                                                                fontSize: 10.5,
                                                                fontWeight: 700,
                                                                color: C.faint,
                                                                letterSpacing:
                                                                    "0.3px",
                                                                margin: "6px 0 7px",
                                                                paddingTop: 9,
                                                                borderTop: `1px dashed ${C.line}`,
                                                            }}
                                                        >
                                                            같은 날 공시와 함께
                                                            움직인 종목
                                                        </div>
                                                    )}
                                                <div
                                                    style={{
                                                        display: "flex",
                                                        gap: 8,
                                                        alignItems: "baseline",
                                                        fontSize: narrow
                                                            ? 12.5
                                                            : 13,
                                                        lineHeight: 1.5,
                                                    }}
                                                >
                                                    {/* 종목명 = ink 700 + 흐린 밑줄. 보라는 액션 전용 (섹션 제목과의 위계 역전 방지) */}
                                                    <span
                                                        onClick={() =>
                                                            goStockTk(
                                                                String(
                                                                    it.ticker ||
                                                                        ""
                                                                )
                                                            )
                                                        }
                                                        style={{
                                                            flexShrink: 0,
                                                            fontWeight: 700,
                                                            color: it.ticker
                                                                ? C.ink
                                                                : C.faint,
                                                            cursor: it.ticker
                                                                ? "pointer"
                                                                : "default",
                                                            textDecoration:
                                                                it.ticker
                                                                    ? "underline"
                                                                    : "none",
                                                            textDecorationColor:
                                                                C.line,
                                                            textUnderlineOffset: 3,
                                                        }}
                                                    >
                                                        {it.name || it.ticker}
                                                    </span>
                                                    {it.mover && it.text ? (
                                                        moverText(
                                                            String(it.text)
                                                        )
                                                    ) : (
                                                        <span
                                                            style={{
                                                                color: C.sub,
                                                                fontWeight: 600,
                                                                minWidth: 0,
                                                            }}
                                                        >
                                                            {it.text ||
                                                                (it.date
                                                                    ? "예상일 " +
                                                                      String(
                                                                          it.date
                                                                      ).slice(5)
                                                                    : "")}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                    {extra > 0 && (
                                        <button
                                            onClick={() =>
                                                setOpenSec((o) => ({
                                                    ...o,
                                                    [s.title]: !open,
                                                }))
                                            }
                                            style={{
                                                border: "none",
                                                background: "transparent",
                                                cursor: "pointer",
                                                fontFamily: FONT,
                                                fontSize: 11.5,
                                                fontWeight: 700,
                                                color: C.vg,
                                                padding: "7px 0 0",
                                            }}
                                        >
                                            {open
                                                ? "접기"
                                                : "+" + extra + "건 더보기"}
                                        </button>
                                    )}
                                </div>
                            )
                        })}

                        {/* 면책 푸터 */}
                        <div
                            style={{
                                fontSize: 10,
                                color: C.faint,
                                fontWeight: 600,
                                marginTop: 16,
                                paddingTop: 11,
                                borderTop: `1px solid ${C.line}`,
                                lineHeight: 1.5,
                                letterSpacing: "0.2px",
                            }}
                        >
                            {brief.disclaimer ||
                                "전부 공시·수집 사실 · 점수·추천 아님"}
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}

addPropertyControls(PublicMorningBriefing, {
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
    holdingsUrl: {
        type: ControlType.String,
        title: "Holdings URL",
        defaultValue: "/holdings",
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
    briefUrl: {
        type: ControlType.String,
        title: "Briefing JSON",
        defaultValue: BRIEF_URL,
    },
    importantUrl: {
        type: ControlType.String,
        title: "Important JSON",
        defaultValue: IMPORTANT_URL,
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark",
        defaultValue: false,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
})

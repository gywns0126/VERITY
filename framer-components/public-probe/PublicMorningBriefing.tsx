import { addPropertyControls, ControlType, RenderTarget } from "framer"
import PublicStockSearch from "https://framer.com/m/PublicStockSearch-iqt9J1.js"
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
 *   2026-09-29 구성: 검색·첫 안내 → 내 보유 요약·소식 → 시장·공시·수급 → 고유 브리핑 접힘.
 *   NOW와 내장 거장·편집 소식은 제거. 별도 홈 컴포넌트를 다시 중복 삽입하지 않는다.
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
 * ② 시장 브리핑 — daily_briefing.json. SAMPLE 은 캔버스 전용.
 *   recap·주요 공시·수급은 overview에서 한 번, 미국 공시·내부자·예상 일정만 추가 접힘.
 *   sessionStorage cache-fallback. 종목 클릭 → stockPath?q=.
 *   urgent_alerts.json은 제목 보강·확인 우선 표시와 overview에 없는 추가 중요 공시 최대 3건에 재사용.
 *   출처·생성시각·신선도·정정 검사에 실패하면 확인 우선 표시를 숨긴다.
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
// Preserve: search first, no login gate, no synthetic live data or additional feed fetch.
// Data contract: api/builders/daily_briefing_builder.py -> daily_briefing.json.
const UNIVERSE =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
// Preserve source titles/dates separately from DART categories; never manufacture an event or amount.
type HomeItem = {
    ticker?: string
    name?: string
    text?: string
    title?: string
    label?: string
    date?: string
    is_correction?: boolean
    url?: string
}
type HomeSection = {
    title?: string
    note?: string
    as_of?: string
    recap?: Record<string, unknown>
    items?: HomeItem[]
}
type HomeBrief = {
    generated_at?: string
    recap_as_of?: string
    sections?: HomeSection[]
}
type HomeOverviewProps = {
    brief?: HomeBrief | null
    importantFeed?: any
    failed?: boolean
    stockPath?: string
    urgencyNow?: number
}

type HomeSearchProps = Pick<HomeOverviewProps, "brief" | "importantFeed" | "stockPath"> & { dark?: boolean }

// Keep priority rules aligned with PublicDisclosureFeed; never infer an action deadline.
type HomeUrgencyDisclosure = {
    ticker: string
    title: string
    date: string
    source_url: string
    is_correction?: boolean
    stamp: string
}
function disclosureReceipt(source: string): string {
    try {
        const url = new URL(source)
        const receipts = url.searchParams.getAll("rcpNo")
        if (
            url.protocol !== "https:" ||
            url.hostname !== "dart.fss.or.kr" ||
            url.port ||
            url.username ||
            url.password ||
            url.hash ||
            url.pathname !== "/dsaf001/main.do"
        )
            return ""
        if (
            Array.from(url.searchParams.keys()).some(
                (key) => key !== "rcpNo"
            ) ||
            receipts.length !== 1
        )
            return ""
        return /^\d{14}$/.test(receipts[0]) ? receipts[0] : ""
    } catch {
        return ""
    }
}
/**
 * 확인 우선순위 v1: KST 오늘 접수 + 24h 이내 생성 피드 + 정확한 공시 유형만.
 * 현재 거래정지/상장폐지 상태를 판정하지 않는다. 정정·철회·해제 및 같은 유형의
 * 후속 공시가 수신되면 보수적으로 숨긴다. 접수일을 청약 마감일로 사용하지 말 것.
 */
function urgentDisclosure(
    d: HomeUrgencyDisclosure,
    siblings: HomeUrgencyDisclosure[],
    stamp: string,
    now: number
): string {
    if (
        !Number.isFinite(now) ||
        now <= 0 ||
        !/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(stamp)
    )
        return ""
    const generatedAt = Date.parse(stamp)
    if (
        !Number.isFinite(generatedAt) ||
        generatedAt > now ||
        now - generatedAt > 24 * 60 * 60 * 1000
    )
        return ""
    const today = new Date(now + 9 * 60 * 60 * 1000).toISOString().slice(0, 10)
    const receipt = disclosureReceipt(d.source_url)
    if (
        d.date !== today ||
        !receipt ||
        receipt.slice(0, 8) !== today.replace(/-/g, "")
    )
        return ""
    const title = (d.title || "").replace(/\s/g, "")
    if (
        d.is_correction ||
        /정정|철회|취하|취소|해제|해소|종결|기각|부인|미해당|미발생|예고|우려|조회공시/.test(
            title
        )
    )
        return ""
    // Exact report names only; mentions in a lawsuit, explanation or periodic report do not qualify.
    const rules: [RegExp, RegExp, string][] = [
        [
            /^(?:주권)?매매거래정지(?:\([^()]*\))?$/,
            /거래정지|거래재개/,
            "거래정지 공시 · 사유와 적용 시각 확인",
        ],
        [
            /^(?:주요사항보고서\()?부도발생\)?$/,
            /부도/,
            "부도 발생 공시 · 지급 상황 확인",
        ],
        [
            /^(?:주요사항보고서\()?회생절차개시신청\)?$/,
            /회생/,
            "회생 신청 공시 · 신청 내용과 진행 단계 확인",
        ],
        [
            /^(?:주요사항보고서\()?파산신청\)?$/,
            /파산/,
            "파산 신청 공시 · 신청 주체와 내용 확인",
        ],
        [
            /^상장폐지결정(?:\([^()]*\))?$/,
            /상장폐지/,
            "상장폐지 결정 공시 · 사유와 후속 일정 확인",
        ],
    ]
    const rule = rules.find(([pattern]) => pattern.test(title))
    if (!rule) return ""
    // The feed is capped, so absence of a follow-up is not proof of current exchange status.
    if (
        siblings.some((other) => {
            if (
                other === d ||
                !rule[1].test((other.title || "").replace(/\s/g, ""))
            )
                return false
            if (other.date < d.date) return false
            if (
                other.is_correction ||
                /정정|철회|취하|취소|해제|해소|종결|기각|부인/.test(
                    other.title || ""
                )
            )
                return true
            const otherReceipt = disclosureReceipt(other.source_url)
            return (
                other.date > d.date || !otherReceipt || otherReceipt > receipt
            )
        })
    )
        return ""
    return rule[2]
}

function homeUrgentReason(
    item: HomeItem,
    brief: HomeBrief | null | undefined,
    feed: any,
    now: number
): string {
    const receipt = disclosureReceipt(String(item.url || ""))
    if (!receipt || !/^\d{6}$/.test(String(item.ticker || ""))) return ""
    const rows: HomeUrgencyDisclosure[] = []
    for (const section of Array.isArray(brief?.sections)
        ? brief.sections
        : []) {
        if (section?.title !== "최근 주요 공시") continue
        for (const row of Array.isArray(section.items) ? section.items : []) {
            if (!row?.ticker || row.ticker !== item.ticker) continue
            rows.push({
                ticker: row.ticker,
                title: String(row.title || row.text || ""),
                date: String(row.date || ""),
                source_url: String(row.url || ""),
                is_correction: row.is_correction,
                stamp: String(brief?.generated_at || ""),
            })
        }
    }
    for (const row of Array.isArray(feed?.alerts) ? feed.alerts : []) {
        if (row?.type !== "disclosure" || row.ticker !== item.ticker) continue
        rows.push({
            ticker: row.ticker,
            title: String(row.headline || ""),
            date: String(row.date || ""),
            source_url: String(row.source_url || ""),
            is_correction: row.is_correction,
            stamp: String(feed?._meta?.generated_at || ""),
        })
    }
    // Match the displayed fact to its own source timestamp. A newer second feed cannot refresh it.
    const title = String(item.title || item.text || "").replace(/\s/g, "")
    const matches = rows.filter(
        (row) => disclosureReceipt(row.source_url) === receipt
    )
    if (
        matches.some(
            (row) => row.is_correction || (row.date && row.date !== item.date)
        )
    )
        return ""
    for (const row of matches) {
        if (row.title.replace(/\s/g, "") !== title || row.date !== item.date)
            continue
        const reason = urgentDisclosure(row, rows, row.stamp, now)
        if (reason) return reason
    }
    return ""
}
function HomeUrgencySticker({ reason }: { reason: string }) {
    if (!reason) return null
    return (
        <div
            data-home-urgency
            style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 6,
                margin: "6px 0",
                lineHeight: 1.5,
            }}
        >
            <span
                style={{
                    color: "#fff",
                    background: "#c92a3a",
                    borderRadius: 7,
                    padding: "3px 7px",
                    fontSize: 11,
                    fontWeight: 700,
                    flexShrink: 0,
                }}
            >
                즉시 확인
            </span>
            <span style={{ fontSize: 11, fontWeight: 600 }}>{reason}</span>
            <span
                style={{ flexBasis: "100%", fontSize: 10.5, fontWeight: 600 }}
            >
                확인 우선 표시 · 매매 신호 아님 · 최신 정정·진행 상태는 원문
                확인
            </span>
        </div>
    )
}

function homeCompanyLogoSrc(ticker?: string): string {
    const code = String(ticker || "").trim()
    // Match the existing site's company-logo provider; these DART rows are domestic issuers.
    return /^\d{6}$/.test(code)
        ? `https://static.toss.im/png-icons/securities/icn-sec-fill-${code}.png`
        : ""
}
function HomeCompanyLogo({ ticker, name, showFlag = true }: { ticker?: string; name?: string; showFlag?: boolean }) {
    const src = homeCompanyLogoSrc(ticker)
    const [failedSrc, setFailedSrc] = useState("")
    const [flagFailed, setFlagFailed] = useState(false)
    const isKoreanListing = /^\d{6}$/.test(String(ticker || "").trim())
    return (
        <span className="an-home-company-mark">
            <span className="an-home-company-logo" aria-hidden="true">
                <span>
                    {String(name || ticker || "?")
                        .trim()
                        .slice(0, 1) || "?"}
                </span>
                {src && failedSrc !== src ? (
                    <img
                        src={src}
                        alt=""
                        width={36}
                        height={36}
                        loading="lazy"
                        decoding="async"
                        onError={() => setFailedSrc(src)}
                    />
                ) : null}
            </span>
            {showFlag && isKoreanListing ? (
                <span className="an-home-company-flag" role="img" aria-label="한국 상장 종목">
                    {flagFailed ? "KR" : (
                        <img
                            src={FLAG_BASE + "kr.svg"}
                            alt=""
                            width={16}
                            height={16}
                            loading="lazy"
                            decoding="async"
                            onError={() => setFlagFailed(true)}
                        />
                    )}
                </span>
            ) : null}
        </span>
    )
}

function finiteValue(value: unknown): number | null {
    return typeof value === "number" && Number.isFinite(value) ? value : null
}
function receiptUrl(value: unknown): string | null {
    try {
        const url = new URL(String(value || ""))
        return url.protocol === "https:" &&
            url.hostname === "dart.fss.or.kr" &&
            url.pathname === "/dsaf001/main.do" &&
            /^\d{14}$/.test(url.searchParams.get("rcpNo") || "")
            ? url.href
            : null
    } catch {
        return null
    }
}
function flowAmount(text?: string): number | null {
    // Accept only the existing producer's explicit estimate; never infer an amount from other prose.
    const match =
        /^외인·기관 동반 순매수 · 추정 ((?:\d{1,3}(?:,\d{3})+|\d+))억원$/.exec(
            text || ""
        )
    return match ? Number(match[1].replace(/,/g, "")) : null
}
function homeFilingFacts(item: HomeItem) {
    const text = String(item.title || item.text || "").trim()
    const generic =
        /^(?:주요사항보고|발행공시|지분공시|거래소공시|공시|공시 제목 미제공)$/.test(
            text
        )
    const title = text && !generic ? text : "공시 제목 미제공 · 원문 확인"
    const rawDate = String(item.date || "")
    const stamp = /^\d{4}-\d{2}-\d{2}$/.test(rawDate)
        ? Date.parse(rawDate + "T00:00:00Z")
        : NaN
    const date =
        Number.isFinite(stamp) &&
        new Date(stamp).toISOString().slice(0, 10) === rawDate
            ? rawDate
            : "접수일 미제공"
    // Questions to check in the source, not claims that a contract or financing succeeded.
    const check = /공급계약|단일판매/.test(title)
        ? "원문에서 계약금액·매출 대비 비중·기간 확인"
        : /전환사채|신주인수권|증자/.test(title)
          ? "원문에서 조달금액·발행조건·주식 수 변화 확인"
          : /자기주식/.test(title)
            ? "원문에서 취득·처분 규모와 실제 이행 여부 확인"
            : /배당/.test(title)
              ? "원문에서 주당 배당금·기준일·지급일 확인"
              : /합병|분할|양수|양도/.test(title)
                ? "원문에서 거래조건·일정·승인 여부 확인"
                : "원문에서 발표 내용·핵심 수치·정정 여부 확인"
    return {
        title,
        date,
        check,
        correction:
            item.is_correction === true || /\[[^\]]*정정[^\]]*\]/.test(title),
    }
}
function homeSnapshot(
    brief?: HomeBrief | null,
    importantFeed?: any,
    now = Date.now()
) {
    const sections = Array.isArray(brief?.sections)
        ? brief.sections.filter(Boolean)
        : []
    const market = sections.find((s) => s.recap && typeof s.recap === "object")
    const company = sections.find((s) => s.title === "최근 주요 공시")
    const flow = sections.find((s) => s.title === "외인·기관 동반 순매수")
    const items = (section?: HomeSection) =>
        Array.isArray(section?.items)
            ? section.items.filter((i) => i && i.ticker)
            : []
    const generated = Date.parse(
        String(importantFeed?._meta?.generated_at || "")
    )
    const alerts =
        Number.isFinite(generated) &&
        generated <= now + 300_000 &&
        now - generated <= IMPORTANT_MAX_AGE_MS &&
        Array.isArray(importantFeed?.alerts)
            ? importantFeed.alerts
            : []
    const filings = items(company)
        .filter((i) => receiptUrl(i.url))
        .map((item) => {
            // Reuse the already received feed only when BOTH issuer and exact receipt match.
            const match = alerts.find(
                (a: any) =>
                    a?.type === "disclosure" &&
                    a.ticker === item.ticker &&
                    receiptUrl(a.source_url) === receiptUrl(item.url)
            )
            return match
                ? {
                      ...item,
                      title: item.title || match.headline,
                      date: item.date || match.date,
                  }
                : item
        })
    const flows = items(flow)
    const rawDate = String(market?.as_of || brief?.recap_as_of || "")
    const marketDate = /^\d{8}$/.test(rawDate)
        ? `${rawDate.slice(0, 4)}-${rawDate.slice(4, 6)}-${rawDate.slice(6)}`
        : "기준일 미제공"
    return { market, company, flow, filings, flows, marketDate }
}
function updatedAt(value?: string) {
    if (!value || !/[Zz]|[+-]\d{2}:\d{2}$/.test(value))
        return "업데이트 시각 미제공"
    const date = new Date(value)
    if (!Number.isFinite(date.getTime())) return "업데이트 시각 미제공"
    return (
        "업데이트 " +
        new Intl.DateTimeFormat("ko-KR", {
            timeZone: "Asia/Seoul",
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hourCycle: "h23",
        }).format(date) +
        " KST"
    )
}
// Preserve: onboarding uses the received filing, never a hardcoded recommendation or sample price.
function homeReadingExample(brief?: HomeBrief | null, now = Date.now()) {
    const generated = brief?.generated_at || ""
    const builtAt = /(?:Z|[+-]\d{2}:\d{2})$/i.test(generated)
        ? Date.parse(generated)
        : NaN
    if (
        !Number.isFinite(now) ||
        !Number.isFinite(builtAt) ||
        now - builtAt > IMPORTANT_MAX_AGE_MS ||
        builtAt > now + 300_000
    )
        return null
    const data = homeSnapshot(brief)
    const item = data.filings.find((item) => {
        if (!/^\d{6}$/.test(item.ticker || "")) return false
        const receipt = new URL(receiptUrl(item.url)!).searchParams.get(
            "rcpNo"
        )!
        const day = `${receipt.slice(0, 4)}-${receipt.slice(4, 6)}-${receipt.slice(6, 8)}`
        const utcDay = Date.parse(`${day}T00:00:00Z`)
        if (
            !Number.isFinite(utcDay) ||
            new Date(utcDay).toISOString().slice(0, 10) !== day
        )
            return false
        const startKst = utcDay - 9 * 60 * 60 * 1000
        // DART gives a receipt day here, not an intraday timestamp. Bound age from that KST day's end.
        return (
            startKst <= now &&
            now - (startKst + 24 * 60 * 60 * 1000 - 1) <= IMPORTANT_MAX_AGE_MS
        )
    })
    return item
        ? {
              item,
              source: receiptUrl(item.url)!,
              note: data.company?.note || "공시 기준일 미제공",
          }
        : null
}
// Preserve (2026-09-19): stable home search fill, no focus underline; empty, idle prompts slide upward.
const HOME_OVERVIEW_CSS = `
.an-home-overview{--ho-ink:var(--an-mbr-ink,#191f28);--ho-sub:var(--an-mbr-sub,#4e5968);--ho-muted:var(--an-mbr-faint,#6b7684);--ho-card:var(--an-mbr-card,#fff);--ho-line:var(--an-mbr-line,#f2f3f5);--ho-accent:var(--an-mbr-vg,#6c5ce7);color:var(--ho-ink);width:100%;min-width:0;font-family:Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;container-type:inline-size}
.an-home-overview{box-sizing:border-box;max-width:100%;overflow-wrap:anywhere;scroll-margin-top:84px}#home-filing-example{scroll-margin-top:84px}.an-home-overview *{box-sizing:border-box}.an-home-overview a{color:inherit;text-decoration:none}.an-home-overview a:focus-visible{outline:2px solid var(--ho-accent);outline-offset:4px;border-radius:5px}
.an-home-intro-main{min-width:0;margin-bottom:28px}.an-home-intro-main .an-home-hero{padding-bottom:0}
.an-home-hero{padding:16px 4px 22px}.an-home-hero h1{font-size:clamp(24px,3.4cqi,30px);line-height:1.35;letter-spacing:-1px;margin:0 0 8px;font-weight:750;word-break:keep-all}.an-home-hero p{margin:0;color:var(--ho-sub);font-size:14px;line-height:1.65;word-break:keep-all}
.an-home-search{position:relative;display:block;height:56px;margin-top:20px;border:0;border-radius:14px;background:var(--ho-card);box-shadow:0 3px 15px rgba(20,25,40,.035)}.an-home-search:focus-within{outline:none;box-shadow:0 3px 15px rgba(20,25,40,.035)}.an-home-search input{font-size:16px!important;font-weight:600!important;padding:0!important;background:transparent!important;color:var(--ho-ink)!important;box-shadow:none!important;border:0!important}.an-home-search>div,.an-home-search div:has(>input){border-radius:14px!important;background:transparent!important;box-shadow:none!important}.an-home-search input::placeholder{color:var(--ho-muted);opacity:1}
.an-home-search:focus-within div:has(>input)>span{border-color:var(--ho-accent)!important}.an-home-search:focus-within div:has(>input)>span>span{background:var(--ho-accent)!important}
.an-home-search-prompt{display:none;position:absolute;left:35px;right:14px;top:50%;transform:translateY(-50%);height:24px;overflow:hidden;pointer-events:none;color:var(--ho-muted);font-size:16px;font-weight:600;line-height:24px}
.an-home-search-track{display:block;animation:anHomeSearchFlip 12s cubic-bezier(.22,.68,0,1) infinite;animation-play-state:paused}.an-home-search-track>span{display:block;height:24px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
@keyframes anHomeSearchFlip{0%,30%{transform:translateY(0)}33.333%,63.333%{transform:translateY(-24px)}66.667%,96.667%{transform:translateY(-48px)}100%{transform:translateY(-72px)}}
@supports selector(:has(input)){.an-home-search:has(input:placeholder-shown):not(:focus-within) .an-home-search-prompt{display:block}.an-home-search:not(:focus-within) input::placeholder{color:transparent}.an-home-search[data-search-motion="running"]:has(input:placeholder-shown):not(:focus-within) .an-home-search-track{animation-play-state:running}.an-home-search:hover .an-home-search-track{animation-play-state:paused!important}}
@media(prefers-reduced-motion:reduce){.an-home-search-track{animation:none!important;transform:none!important}}
.an-home-helper{font-size:12px!important;margin-top:9px!important}.an-home-sr{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
.an-home-start{display:flex;flex-direction:column;align-items:stretch;gap:12px;margin-top:18px;font-size:13px;font-weight:600}.an-home-start>a{align-self:flex-end;max-width:100%;color:var(--ho-sub);font-weight:700;text-decoration:underline;text-underline-offset:3px;line-height:1.6}.an-home-example{width:100%;min-width:0;border:0!important;outline:0!important;border-radius:14px;background:var(--ho-card);box-shadow:0 2px 12px rgba(20,25,40,.025)}.an-home-example:focus-within{border:0!important;outline:0!important}.an-home-example>summary{cursor:pointer;display:flex;align-items:center;justify-content:flex-start;gap:7px;color:var(--ho-accent);font-weight:700;width:100%;max-width:100%;min-height:48px;padding:12px 16px!important;line-height:1.6;list-style:none;border:0!important;outline:0!important;box-shadow:none!important;border-radius:14px}.an-home-example>summary::-webkit-details-marker{display:none}.an-home-example>summary::marker{content:""}.an-home-example>summary:focus,.an-home-example>summary:focus-visible{border:0!important;outline:0!important;box-shadow:none!important}.an-home-example>summary::after{content:none!important;display:none!important}.an-home-example-summary-label{flex:1;min-width:0}.an-home-example-arrow{display:block;flex:0 0 14px;width:14px;height:14px;transition:transform .16s ease;transform:rotate(0deg)}.an-home-example[open] .an-home-example-arrow{transform:rotate(90deg)}.an-home-example[open]>summary{border-radius:14px 14px 0 0}.an-home-example-body{padding:0 16px 18px;border-radius:0 0 14px 14px;line-height:1.7}.an-home-example-body strong{font-weight:800}.an-home-example-body p{font-size:13px;margin:8px 0}.an-home-example-body ol{display:grid;gap:7px;margin:14px 0;padding-left:22px;color:var(--ho-sub)}.an-home-example-links{display:flex;gap:12px 18px;flex-wrap:wrap;padding-top:2px}.an-home-example-links a{font-weight:700;color:var(--ho-accent);text-decoration:underline;text-underline-offset:3px}.an-home-example-body small{display:block;color:var(--ho-muted);font-size:11px;margin-top:12px;overflow-wrap:anywhere}
.an-home-heading{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap;padding:0 4px;margin:0 0 12px}.an-home-heading h2{font-size:18px;letter-spacing:-.5px;margin:0}.an-home-heading span{font-size:11px;color:var(--ho-muted)}
.an-home-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.an-home-card{min-width:0;display:flex;flex-direction:column;padding:18px;border:0;border-radius:18px;background:var(--ho-card);box-shadow:0 3px 16px rgba(20,25,40,.025)}
body[data-framer-theme="dark"] .an-home-card,html[data-an-theme="dark"] .an-home-card{box-shadow:none}
.an-home-kicker{font-size:11px;color:var(--ho-muted);font-weight:650;letter-spacing:.3px}.an-home-card h3{font-size:16px;line-height:1.5;letter-spacing:-.4px;margin:5px 0 14px;word-break:keep-all}.an-home-card p{font-size:12px;line-height:1.65;margin:10px 0;color:var(--ho-sub);word-break:keep-all}
.an-home-card h3 a:hover,.an-home-ticker:hover,.an-home-source:hover{text-decoration:underline;text-underline-offset:3px}.an-home-row{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px;font-size:13px}.an-home-row strong,.an-home-amount{font-variant-numeric:tabular-nums;white-space:nowrap}.an-home-price{display:block;font-size:11px;color:var(--ho-muted);margin-top:3px;font-variant-numeric:tabular-nums}
.an-home-index{margin-bottom:20px}.an-home-zero{height:12px;border-radius:4px;background:var(--ho-line);position:relative;margin-top:8px;overflow:hidden}.an-home-zero:after{content:'';position:absolute;left:50%;top:0;height:100%;width:1px;background:var(--ho-muted);opacity:.4}.an-home-zero i{position:absolute;height:100%;border-radius:4px}
.an-home-list{list-style:none;padding:0;margin:0;display:grid;gap:12px}.an-home-list li+li{padding-top:12px;border-top:1px solid var(--ho-line)}.an-home-ticker{font-weight:650;min-width:0;overflow-wrap:anywhere}.an-home-source{font-size:11px;color:var(--ho-muted)!important;white-space:nowrap}.an-home-filing{font-size:12px;line-height:1.55;color:var(--ho-sub);margin-top:4px;word-break:keep-all}.an-home-code{font-size:10px;color:var(--ho-muted);margin-left:4px}
.an-home-company-row{align-items:center}.an-home-company-link{display:flex;align-items:center;gap:10px;flex:1;min-width:0}.an-home-company-logo{position:relative;display:grid;place-items:center;flex:0 0 36px;width:36px;height:36px;border-radius:11px;overflow:hidden;background:var(--ho-line);color:var(--ho-sub);font-size:15px;font-weight:700}.an-home-company-logo img{position:absolute;inset:0;width:36px;height:36px;object-fit:contain;border-radius:11px;background:var(--ho-card)}.an-home-company-mark{position:relative;display:inline-flex;flex:0 0 36px;width:36px;height:36px}.an-home-company-flag{position:absolute;right:-3px;bottom:-3px;z-index:1;display:flex;align-items:center;justify-content:center;width:19px;height:19px;border:1.5px solid var(--ho-card);border-radius:50%;background:var(--ho-card);color:var(--ho-sub);font-size:7px;font-weight:800;line-height:1;box-shadow:0 1px 2px rgba(0,0,0,.15);overflow:hidden}.an-home-company-flag img{display:block;width:100%;height:100%;border-radius:50%;object-fit:cover}.an-home-company-copy{display:grid;gap:4px;min-width:0}.an-home-company-name{line-height:1.45}.an-home-company-filing{display:block;margin:0;font-weight:500}
.an-home-amount{font-size:12px;font-weight:650}.an-home-bar{height:10px;background:var(--ho-line);border-radius:4px;margin-top:8px;overflow:hidden}.an-home-bar i{display:block;height:100%;background:var(--ho-accent);border-radius:4px}.an-home-foot{margin-top:auto;padding-top:14px;font-size:10px;line-height:1.6;color:var(--ho-muted);overflow-wrap:anywhere}.an-home-foot a{text-decoration:underline;text-underline-offset:2px}.an-home-empty{padding:8px 0 16px;font-size:12px;color:var(--ho-muted);line-height:1.6}
.an-home-overview{font-weight:600}.an-home-hero h1,.an-home-heading h2,.an-home-card h3{font-weight:800}.an-home-kicker,.an-home-ticker,.an-home-amount{font-weight:700}.an-home-company-filing{font-weight:600}.an-home-event-date{display:block;margin-top:7px;color:var(--ho-muted);font-size:10px;font-weight:600}.an-home-card .an-home-event-check{margin:4px 0 0;font-size:11px;font-weight:600;line-height:1.6}
@container (max-width:720px){.an-home-grid{grid-template-columns:1fr}.an-home-card{padding:16px}.an-home-hero{padding-top:10px}.an-home-heading span{font-size:10px}.an-home-search{margin-top:16px}.an-home-list{gap:10px}}
`

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 */
function PublicHomeSearch({ brief = null, importantFeed, stockPath = "/stock", dark = false }: HomeSearchProps) {
    const searchRef = useRef<HTMLLabelElement>(null)
    useEffect(() => {
        const el = searchRef.current
        const target = RenderTarget.current()
        if (
            !el ||
            typeof document === "undefined" ||
            target === RenderTarget.canvas ||
            target === RenderTarget.export ||
            target === RenderTarget.thumbnail
        )
            return
        let visible = false
        const syncMotion = () => {
            el.dataset.searchMotion =
                visible && document.visibilityState === "visible"
                    ? "running"
                    : "paused"
        }
        const observer =
            typeof IntersectionObserver !== "undefined"
                ? new IntersectionObserver(([entry]) => {
                      visible = !!entry?.isIntersecting
                      syncMotion()
                  })
                : null
        if (observer) observer.observe(el)
        else {
            visible = true
            syncMotion()
        }
        document.addEventListener("visibilitychange", syncMotion)
        return () => {
            observer?.disconnect()
            document.removeEventListener("visibilitychange", syncMotion)
            el.dataset.searchMotion = "paused"
        }
    }, [])
    const data = homeSnapshot(brief, importantFeed)
    const example = homeReadingExample(brief)
    const stockHref = (ticker?: string) =>
        `${(stockPath || "/stock").replace(/\/+$/, "")}?q=${encodeURIComponent(ticker || "")}`
    return (
        <section id="home-search" className="an-home-overview" aria-label="종목 검색과 첫 안내">
            <style>{HOME_OVERVIEW_CSS}</style>
            <div className="an-home-intro-main">
                <div className="an-home-hero">
                    <h1>기업의 변화를 근거와 함께 살펴보세요</h1>
                    <p>실적·공시·수급의 변화를 출처와 함께 확인하세요.</p>
                    <label
                        className="an-home-search"
                        ref={searchRef}
                        style={{ background: "var(--an-mbr-card, #fff)" }}
                    >
                        <span className="an-home-sr">
                            종목 이름이나 코드 검색
                        </span>
                        <PublicStockSearch
                            placeholder="궁금한 종목 이름이나 코드를 입력하세요"
                            stockPath={stockPath}
                            stockUrl={UNIVERSE}
                            usStockUrl=""
                            dark={dark}
                            reportStyle={false}
                            fieldBackground="transparent"
                        />
                        <span
                            className="an-home-search-prompt"
                            aria-hidden="true"
                        >
                            <span className="an-home-search-track">
                                <span>오늘은 어떤 종목을 검색해볼까?</span>
                                <span>어떤 종목이 달라졌을까?</span>
                                <span>궁금한 기업의 소식을 찾아보세요</span>
                                <span>오늘은 어떤 종목을 검색해볼까?</span>
                            </span>
                        </span>
                    </label>
                    <p className="an-home-helper">
                        로그인 없이 검색할 수 있어요. 이름·종목코드·미국 티커로
                        찾아보세요.
                    </p>
                    <div className="an-home-start">
                        {example ? (
                            <details id="home-filing-example" className="an-home-example">
                                <summary>
                                    <span className="an-home-example-summary-label">처음이라면 · 실제 공시로 읽어보기</span>
                                    <svg
                                        className="an-home-example-arrow"
                                        viewBox="0 0 16 16"
                                        fill="none"
                                        aria-hidden="true"
                                    >
                                        <path
                                            d="M5.75 3.5 10.25 8l-4.5 4.5"
                                            stroke="currentColor"
                                            strokeWidth="1.8"
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                        />
                                    </svg>
                                </summary>
                                <div className="an-home-example-body">
                                    <strong>
                                        {example.item.name ||
                                            example.item.ticker}
                                    </strong>
                                    <span className="an-home-code">
                                        {example.item.ticker}
                                    </span>
                                    <p>
                                        {
                                            homeFilingFacts(
                                                data.filings.find(
                                                    (item) =>
                                                        item.url ===
                                                        example.item.url
                                                ) || example.item
                                            ).title
                                        }
                                    </p>
                                    <ol>
                                        <li>
                                            기업 리포트에서 사업과 실적의
                                            기준일을 확인해요.
                                        </li>
                                        <li>
                                            DART 원문에서 무엇을 알렸는지,
                                            정정된 내용이 있는지 확인해요.
                                        </li>
                                        <li>
                                            내 생각과 공시에 적힌 사실을
                                            구분하고, 다음에 확인할 질문을
                                            남겨요.
                                        </li>
                                    </ol>
                                    <nav
                                        className="an-home-example-links"
                                        aria-label="공시 예시 읽기"
                                    >
                                        <a
                                            href={stockHref(
                                                example.item.ticker
                                            )}
                                        >
                                            기업 리포트 보기 →
                                        </a>
                                        <a
                                            href={example.source}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                        >
                                            DART 원문 ↗
                                        </a>
                                    </nav>
                                    <small>
                                        {example.note}
                                        <br />
                                        수신 국내 공시 중 읽기 예시 1건이에요.
                                        추천 종목이나 수익 전망이 아닙니다.
                                    </small>
                                </div>
                            </details>
                        ) : (
                            <details id="home-filing-example" className="an-home-example">
                                <summary>
                                    <span className="an-home-example-summary-label">처음이라면 · 공시 읽는 순서</span>
                                    <svg
                                        className="an-home-example-arrow"
                                        viewBox="0 0 16 16"
                                        fill="none"
                                        aria-hidden="true"
                                    >
                                        <path
                                            d="M5.75 3.5 10.25 8l-4.5 4.5"
                                            stroke="currentColor"
                                            strokeWidth="1.8"
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                        />
                                    </svg>
                                </summary>
                                <div className="an-home-example-body">
                                    <p>지금은 읽기 예시로 사용할 최신 공시를 확인하지 못했어요. 종목을 검색한 뒤 기업 리포트의 기준일, 공시 원문과 정정 여부를 차례로 확인하세요.</p>
                                    <a href="#home-search">종목 검색으로 이동 →</a>
                                </div>
                            </details>
                        )}
                        <a href="/nest">내 보유종목 이어보기 →</a>
                    </div>
                </div>
            </div>
        </section>
    )
}

function PublicHomeOverview({ brief = null, importantFeed, failed = false, stockPath = "/stock", urgencyNow = 0 }: HomeOverviewProps) {
    const data = homeSnapshot(brief, importantFeed)
    const stockHref = (ticker?: string) =>
        `${(stockPath || "/stock").replace(/\/+$/, "")}?q=${encodeURIComponent(ticker || "")}`
    const indexRows = [
        {
            name: "코스피",
            change: finiteValue(data.market?.recap?.kospi),
            level: finiteValue(data.market?.recap?.kospi_close),
        },
        {
            name: "코스닥",
            change: finiteValue(data.market?.recap?.kosdaq),
            level: finiteValue(data.market?.recap?.kosdaq_close),
        },
    ]
    const scale = Math.max(1, ...indexRows.map((i) => Math.abs(i.change ?? 0)))
    const flowRows = data.flows.slice(0, 3)
    const maxAmount = Math.max(
        1,
        ...flowRows.map((i) => flowAmount(i.text) ?? 0)
    )
    const empty = !brief
        ? failed
            ? "자료를 불러오지 못했어요. 종목 검색은 계속 이용할 수 있어요."
            : "자료를 확인하고 있어요."
        : "이번 자료에 제공된 항목이 없어요."
    return (
        <section id="home-changes" className="an-home-overview" aria-label="최근 시장·공시·수급 변화">
            <div className="an-home-heading">
                <h2>최근 시장·공시·수급 변화</h2>
                <span>{updatedAt(brief?.generated_at)}</span>
            </div>
            <div className="an-home-grid">
                <article className="an-home-card">
                    <span className="an-home-kicker">시장 · 국내 지수</span>
                    <h3>
                        <a href="/market">시장은 어느 쪽으로 움직였을까? →</a>
                    </h3>
                    {data.market ? (
                        <>
                            {indexRows.map((row) => (
                                <div className="an-home-index" key={row.name}>
                                    <div className="an-home-row">
                                        <span>
                                            {row.name}
                                            <span className="an-home-price">
                                                {row.level === null
                                                    ? "지수값 미제공"
                                                    : row.level.toLocaleString(
                                                          "ko-KR",
                                                          {
                                                              maximumFractionDigits: 2,
                                                          }
                                                      ) + " pt"}
                                            </span>
                                        </span>
                                        <strong
                                            style={{
                                                color:
                                                    row.change === null ||
                                                    row.change === 0
                                                        ? "var(--ho-sub)"
                                                        : row.change > 0
                                                          ? "#f04452"
                                                          : "#3182f6",
                                            }}
                                        >
                                            {row.change === null
                                                ? "등락 미제공"
                                                : `${row.change > 0 ? "+" : ""}${row.change.toFixed(2)}%`}
                                        </strong>
                                    </div>
                                    <div
                                        className="an-home-zero"
                                        aria-hidden="true"
                                    >
                                        <i
                                            style={{
                                                left:
                                                    row.change !== null &&
                                                    row.change < 0
                                                        ? `${50 - (Math.abs(row.change) / scale) * 50}%`
                                                        : "50%",
                                                width: `${(Math.abs(row.change ?? 0) / scale) * 50}%`,
                                                background:
                                                    (row.change ?? 0) > 0
                                                        ? "#f04452"
                                                        : "#3182f6",
                                            }}
                                        />
                                    </div>
                                </div>
                            ))}
                            {typeof data.market.recap?.headline === "string" ? (
                                <p>{data.market.recap.headline}</p>
                            ) : null}
                        </>
                    ) : (
                        <div className="an-home-empty">{empty}</div>
                    )}
                    <footer className="an-home-foot">
                        {data.marketDate} 종가 · 실시간 시세 아님
                        <br />
                        금융위원회 공공데이터 · 막대 중앙은 0%
                        <br />
                        <a href="/market">시장 자료와 출처 확인 →</a>
                    </footer>
                </article>
                <article className="an-home-card">
                    <span className="an-home-kicker">
                        기업 · 최근 주요 공시
                    </span>
                    <h3>
                        <a href="/disclosure">기업이 방금 알려줬어요! →</a>
                    </h3>
                    {data.filings.length ? (
                        <ul className="an-home-list">
                            {data.filings.slice(0, 3).map((item, i) => {
                                const fact = homeFilingFacts(item)
                                return (
                                    <li key={`${item.ticker}-${i}`}>
                                        <div className="an-home-row an-home-company-row">
                                            <a
                                                className="an-home-ticker an-home-company-link"
                                                href={stockHref(item.ticker)}
                                            >
                                                <HomeCompanyLogo
                                                    key={item.ticker}
                                                    ticker={item.ticker}
                                                    name={item.name}
                                                />
                                                <span className="an-home-company-copy">
                                                    <span className="an-home-company-name">
                                                        {item.name ||
                                                            item.ticker}
                                                    </span>
                                                    <span className="an-home-filing an-home-company-filing">
                                                        {fact.title}
                                                    </span>
                                                </span>
                                            </a>
                                            <a
                                                className="an-home-source"
                                                href={receiptUrl(item.url)!}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                aria-label={`${item.name || item.ticker} ${fact.title} DART 원문`}
                                            >
                                                원문 ↗
                                            </a>
                                        </div>
                                        <HomeUrgencySticker
                                            reason={homeUrgentReason(
                                                item,
                                                brief,
                                                importantFeed,
                                                urgencyNow
                                            )}
                                        />
                                        <small className="an-home-event-date">
                                            {fact.date}
                                            {fact.date !== "접수일 미제공"
                                                ? " 접수"
                                                : ""}
                                            {fact.correction
                                                ? " · 정정 공시"
                                                : ""}
                                        </small>
                                        <p className="an-home-event-check">
                                            {fact.check}
                                        </p>
                                    </li>
                                )
                            })}
                        </ul>
                    ) : (
                        <div className="an-home-empty">{empty}</div>
                    )}
                    <footer className="an-home-foot">
                        {data.company?.note || "공시 기준일 미제공"}
                        <br />
                        {data.filings.length
                            ? `원문 연결 ${data.filings.length}건 중 ${Math.min(3, data.filings.length)}건 표시`
                            : "원문이 확인되는 공시만 표시해요."}
                    </footer>
                </article>
                <article className="an-home-card">
                    <span className="an-home-kicker">수급 · 외국인·기관</span>
                    <h3>
                        <a href="/market">외국인·기관이 가장 많이 산 종목은? →</a>
                    </h3>
                    {flowRows.length ? (
                        <ul className="an-home-list">
                            {flowRows.map((item, i) => {
                                const amount = flowAmount(item.text)
                                return (
                                    <li key={`${item.ticker}-${i}`}>
                                        <div className="an-home-row an-home-company-row">
                                            <a
                                                className="an-home-ticker an-home-company-link"
                                                href={stockHref(item.ticker)}
                                            >
                                                <HomeCompanyLogo
                                                    key={item.ticker}
                                                    ticker={item.ticker}
                                                    name={item.name}
                                                    showFlag={false}
                                                />
                                                <span className="an-home-company-copy">
                                                    <span className="an-home-company-name">
                                                        {item.name || item.ticker}
                                                    </span>
                                                </span>
                                            </a>
                                            {amount !== null ? (
                                                <span className="an-home-amount">
                                                    {amount.toLocaleString(
                                                        "ko-KR"
                                                    )}
                                                    억원
                                                </span>
                                            ) : null}
                                        </div>
                                        {amount !== null ? (
                                            <div
                                                className="an-home-bar"
                                                aria-hidden="true"
                                            >
                                                <i
                                                    style={{
                                                        width: `${(amount / maxAmount) * 100}%`,
                                                    }}
                                                />
                                            </div>
                                        ) : (
                                            <div className="an-home-filing">
                                                {item.text || "금액 미제공"}
                                            </div>
                                        )}
                                    </li>
                                )
                            })}
                        </ul>
                    ) : (
                        <div className="an-home-empty">{empty}</div>
                    )}
                    <footer className="an-home-foot">
                        {data.flow?.note || "수급 기준일 미제공"}
                        <br />
                        {data.flow
                            ? `추정 합산 순매수금액 · 수신 ${data.flows.length}종목 중 ${flowRows.length}종목`
                            : "자료 미제공은 순매수 0을 의미하지 않아요."}
                        <br />
                        <a href="/market">수급 자료와 출처 확인 →</a>
                    </footer>
                </article>
            </div>
        </section>
    )
}

// Preserve important feed receipts omitted by the overview's actual three-row preview.
function homeAdditionalImportant(brief: HomeBrief | null | undefined, feed: any, now = Date.now()): any[] {
    const stamp = String(feed?._meta?.generated_at || "")
    const generated = /T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(stamp) ? Date.parse(stamp) : NaN
    if (!Number.isFinite(now) || now <= 0 || !Number.isFinite(generated) || generated > now || now - generated > IMPORTANT_MAX_AGE_MS || !Array.isArray(feed?.alerts)) return []
    const seen = new Set(homeSnapshot(brief, feed, now).filings.slice(0, 3).map(item => disclosureReceipt(String(item.url || ""))).filter(Boolean))
    const items: any[] = []
    for (const alert of feed.alerts) {
        const receipt = disclosureReceipt(String(alert?.source_url || ""))
        if (!receipt || seen.has(receipt) || typeof alert?.headline !== "string" || !alert.headline.trim()) continue
        seen.add(receipt)
        items.push({ ...alert, title: alert.headline, url: alert.source_url })
        if (items.length === 3) break
    }
    return items
}

function homeBriefingSections(brief?: HomeBrief | null): HomeSection[] {
    const uniqueTitles = new Set(["밤사이 미국 공시", "최근 7일 내부자 변동", "이번 주 실적 공시 예상"])
    return (Array.isArray(brief?.sections) ? brief.sections : [])
        .filter(section => section && uniqueTitles.has(section.title || ""))
        .map(section => ({ ...section, items: Array.isArray(section.items) ? section.items.filter(Boolean) : [] }))
        .filter(section => section.items.length > 0)
}

const PER_SECTION = 3 // 섹션당 기본 노출, 초과 = "+N건" 접힘
const IMPORTANT_MAX_AGE_MS = 72 * 60 * 60 * 1000

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
    const [rows, setRows] = useState<any[]>(onCanvas ? SAMPLE_HOLD : [])
    // 🚨 2026-08-22 — "내 보유 종목 소식". 회원별 서버 발행이 아니라 **전역 색인 1개**를
    //   받아 브라우저가 위 rows(보유) 와 교차한다. 인증·보유목록은 위 /api/holdings 재사용.
    //   보유 기반만 표시한다. 관심종목 연동으로 설명하지 않는다. 빈 결과·수신 실패를 구분한다.
    //   RULE 6 = LLM 0(결정론적 교차) · RULE 7 = 공시 제목 원문 + 지분율, 점수·추천 0.
    const [nestIdx, setNestIdx] = useState<Record<string, any> | null>(null)
    const [npsMap, setNpsMap] = useState<Record<string, number> | null>(null)
    const [closes, setCloses] = useState<
        Record<string, { last: number; prev: number | null }>
    >({})
    const [closeDate, setCloseDate] = useState<string>("") // 종가 기준일(kr_close_latest _meta.as_of, 전 종목 공통) — "전일" 대신 실제 날짜 표기
    const [isDemo, setIsDemo] = useState(true)
    // SSR/첫 렌더는 중립 상태: 인증 확인 전에 비회원 CTA나 예시 자산을 노출하지 않는다.
    const [authReady, setAuthReady] = useState(onCanvas)
    const [loading, setLoading] = useState(!onCanvas)
    const [holdingsFailed, setHoldingsFailed] = useState(false)
    const holdingsRequest = useRef(0)
    const [newsSettled, setNewsSettled] = useState(false)
    const [newsFailed, setNewsFailed] = useState(false)
    const [newsStamp, setNewsStamp] = useState("")
    const [npsStamp, setNpsStamp] = useState("")
    const [fxRate, setFxRate] = useState<number>(FX_FALLBACK) // 실시간 usd_krw(price_pulse). 폴백=FX_FALLBACK.

    // ② 시장 브리핑 상태
    const [brief, setBrief] = useState<any>(onCanvas ? SAMPLE_BRIEF : null)
    const [importantFeed, setImportantFeed] = useState<any>(
        onCanvas ? SAMPLE_IMPORTANT : null
    )
    const [briefFailed, setBriefFailed] = useState(false)
    const [openSec, setOpenSec] = useState<Record<string, boolean>>({})
    const [nowTick, setNowTick] = useState(0) // 경과 시간 표시 갱신용 60초 틱
    const [briefFresh, setBriefFresh] = useState(false)
    const [importantFresh, setImportantFresh] = useState(false)
    const urgencyNow =
        !onCanvas && nowTick > 0 && briefFresh && importantFresh
            ? Date.now()
            : 0
    const [reloadTick, setReloadTick] = useState(0) // 탭 복귀·5분 폴링 재조회 트리거

    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

    // Measure the same border box before/after responsive padding; ignore hidden/invalid sizes.
    useEffect(() => {
        const el = rootRef.current
        if (!el) return
        const measure = (width: number) => {
            if (Number.isFinite(width) && width > 0) setW(prev => prev === width ? prev : width)
        }
        measure(el.offsetWidth)
        if (typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver(entries => {
            for (const entry of entries) measure(entry.borderBoxSize?.[0]?.inlineSize ?? el.offsetWidth)
        })
        try { ro.observe(el, { box: "border-box" }) } catch { ro.observe(el) }
        return () => ro.disconnect()
    }, [])

    // 테마 자가감지
    // 보유 ∩ 수신 색인 = 내 종목 소식. 데이터가 없음을 업데이트 0건으로 단정하지 않는다.
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
    // 국민연금 원천 = 수신 대량보유 공시. 색인 미등재를 미보유나 특정 지분율로 단정하지 않는다.
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/nest_briefing_index.json"
        )
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                if (d && d.tickers && typeof d.tickers === "object" && !Array.isArray(d.tickers)) {
                    setNestIdx(d.tickers)
                    setNewsStamp(String(d._meta?.generated_at || ""))
                } else setNewsFailed(true)
            })
            .catch(() => { if (alive) setNewsFailed(true) })
            .finally(() => { if (alive) setNewsSettled(true) })
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
                setNpsStamp(String(d.generated_at || ""))
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas])

    // Preserve auth changes and fail closed on stale responses from a previous account.
    const loadHoldings = useCallback(() => {
        if (onCanvas) return
        const request = ++holdingsRequest.current
        const token = getToken()
        setAuthReady(true)
        setHoldingsFailed(false)
        setRows([])
        if (!token) {
            setIsDemo(true)
            setLoading(false)
            return
        }
        setIsDemo(false)
        setLoading(true)
        const current = () => request === holdingsRequest.current && token === getToken()
        fetch(base + "/api/holdings", {
            headers: { Authorization: "Bearer " + token },
        })
            .then(r => { if (!r.ok) throw new Error("holdings unavailable"); return r.json() })
            .then(d => {
                if (!current()) return
                const items = Array.isArray(d) ? d : d?.holdings
                if (!Array.isArray(items)) throw new Error("invalid holdings")
                setRows(items)
            })
            .catch(() => { if (current()) { setRows([]); setHoldingsFailed(true) } })
            .finally(() => { if (current()) setLoading(false) })
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
            holdingsRequest.current++
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
            if (alive) setBriefFresh(false)
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
                    setBriefFresh(true)
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
                if (!alive) return
                setImportantFresh(Boolean(d && Array.isArray(d.alerts)))
                if (d && Array.isArray(d.alerts)) setImportantFeed(d)
            })
            .catch(() => {
                if (alive) setImportantFresh(false)
            })
        return () => {
            alive = false
        }
    }, [onCanvas, importantUrl, reloadTick])

    // 🚨 2026-07-28 상시 갱신 — 옛 embargo(publish_at 07:30 전 숨김) 타이머 폐기.
    //   PM: "모닝 브리핑에서 모닝을 빼고 수시로 체크하는거지." 받는 즉시 노출한다.
    //   경과 시간 표시가 1분 단위로 늙어 보이게 60초 틱만 유지.
    useEffect(() => {
        if (onCanvas) return
        setNowTick((t) => t + 1)
        const id = setInterval(() => setNowTick((t) => t + 1), 60000)
        return () => clearInterval(id)
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

    const noLogin = authReady && !onCanvas && isDemo
    const upC = (v: number) => (v >= 0 ? C.up : C.down)
    const arrow = (v: number) => (v > 0 ? "▲" : v < 0 ? "▼" : "·")
    const narrow = w > 0 && w < 420

    const goHoldings = () => {
        if (typeof window === "undefined") return
        window.location.href = (holdingsUrl || "/holdings").replace(/\/+$/, "")
    }
    const goStockTk = (tk: string, us?: boolean) => {
        if (typeof window === "undefined" || !tk) return
        const path = (
            us ? _usPath(usStockPath, stockPath) : stockPath || "/stock"
        ).replace(/\/+$/, "")
        window.location.href = path + "?q=" + encodeURIComponent(tk)
    }

    // These are the unique briefing sections; market/DART/flow already live in the overview.
    const secs = homeBriefingSections(brief)
    const additionalImportant = homeAdditionalImportant(brief, importantFeed)

    // 카드 밖 제호 + 형제 카드 2장 (개인 / 시장). 중첩 카드 회피.
    const shell: CSSProperties = {
        fontFamily: FONT,
        width: "100%",
        minWidth: 0,
        maxWidth: "100%",
        overflowWrap: "anywhere",
        boxSizing: "border-box",
        color: C.ink,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: "8px clamp(14px, 2vw, 20px) 20px",
    }
    const card: CSSProperties = {
        minWidth: 0,
        maxWidth: "100%",
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
    return (
        <div ref={rootRef} style={shell}>
            <style>{AN_PALETTE}</style>
            {/* Preserve order and stable search identity: search → holdings → public changes. */}
            <PublicHomeSearch brief={brief} importantFeed={importantFeed} stockPath={stockPath || "/stock"} dark={dark} />

            {/* ── ① 내 자산 카드 ── */}
            {!authReady ? (
                <div role="status" style={{ ...card, color: C.faint, fontSize: 12, fontWeight: 600 }}>내 자산 연결 상태 확인 중…</div>
            ) : noLogin ? (
                <a
                    href={loginUrl || "/login"}
                    style={{
                        ...cta,
                        padding: "10px 4px",
                        background: "transparent",
                        textDecoration: "none",
                    }}
                >
                    <div
                        style={{
                            fontSize: 13,
                            fontWeight: 700,
                            color: C.ink,
                            lineHeight: 1.5,
                        }}
                    >
                        로그인하면 내 보유종목과 자산 변화를 이어볼 수 있어요.
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
                </a>
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
            ) : holdingsFailed ? (
                <div role="status" style={{ ...card, color: C.faint, fontSize: 12, fontWeight: 600 }}>보유종목을 불러오지 못했습니다. <a href={holdingsUrl || "/holdings"} style={{ color: C.vg }}>내 자산에서 확인 →</a></div>
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

                            {authReady && !loading && !holdingsFailed && !isDemo && myNews.length > 0 && (
                                <section aria-label="내 보유종목 소식" style={{ ...card, marginBottom: 8 }}>
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
                                            {myNews.length}종목 · 수신 공시·국민연금 공시 기준
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
                                                                background:
                                                                    C.line,
                                                                borderRadius: 999,
                                                                padding:
                                                                    "2px 7px",
                                                            }}
                                                            title="국민연금 5% 이상 대량보유 공시 기준"
                                                        >
                                                            국민연금{" "}
                                                            {m.nps.toFixed(2)}%
                                                        </span>
                                                    )}
                                                </div>
                                                {m.ev.map(
                                                    (e: any, i: number) => (
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
                                                            {String(
                                                                e.d || ""
                                                            ).slice(5)}{" "}
                                                            ·{" "}
                                                            {String(e.t || "")}
                                                        </div>
                                                    )
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                    <div style={{ ...secNote, marginTop: 10 }}>
                                        DART·SEC 공시 색인 · {updatedAt(newsStamp)}
                                        <br />국민연금 대량보유 공시 자료 · {updatedAt(npsStamp)} · 생성시각과 개별 공시 기준일은 다를 수 있어요.
                                    </div>
                                </section>
                            )}


            {authReady && !loading && !holdingsFailed && !isDemo && asset.count > 0 && myNews.length === 0 ? (
                <p role="status" style={{ ...secNote, margin: "4px 4px 12px", lineHeight: 1.6 }}>
                    {!newsSettled ? "보유종목 소식을 확인하고 있어요." : newsFailed ? "보유종목 소식을 불러오지 못했습니다." : "수신 자료에서 보유종목의 새 공시가 확인되지 않았어요. 모든 소식이 없다는 뜻은 아닙니다."}
                    {newsSettled && !newsFailed ? <span> · {updatedAt(newsStamp)}</span> : null}
                </p>
            ) : null}
            <PublicHomeOverview brief={brief} importantFeed={importantFeed} failed={briefFailed} stockPath={stockPath || "/stock"} urgencyNow={urgencyNow} />

            <details style={card} data-home-briefing>
                <summary style={{ cursor: "pointer", color: C.ink, fontSize: 13, fontWeight: 700 }}>
                    중요 공시·미국 공시·예상 일정 더 보기
                </summary>
                <div style={{ paddingTop: 14 }}>
                    <p style={secNote}>{updatedAt(brief?.generated_at)} · 항목별 기준일 확인</p>
                    {additionalImportant.length > 0 ? (
                        <section aria-label="추가 중요 공시" style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${C.line}` }}>
                            <h3 style={{ ...secTitle, margin: "0 0 5px" }}>추가 중요 공시</h3>
                            <div style={secNote}>DART 원문 · {updatedAt(importantFeed?._meta?.generated_at)}</div>
                            {additionalImportant.map(item => (
                                <div key={item.url} style={{ marginTop: 10, fontSize: 12, lineHeight: 1.6 }}>
                                    <a href={item.url} target="_blank" rel="noopener noreferrer" style={{ color: C.ink, textDecoration: "none" }}>
                                        <span style={{ fontWeight: 700 }}>{item.name || item.ticker} · {item.title}</span>
                                        <span style={{ ...secNote, display: "block" }}>{item.date || "접수일 미제공"} · 원문 보기 ↗</span>
                                    </a>
                                    <HomeUrgencySticker reason={item.type === "disclosure" ? homeUrgentReason(item, brief, importantFeed, urgencyNow) : ""} />
                                </div>
                            ))}
                        </section>
                    ) : null}
                    {!brief ? <p style={secNote}>{briefFailed ? "시장 브리핑을 불러오지 못했습니다." : "시장 브리핑 수신 중…"}</p>
                        : secs.length === 0 ? (additionalImportant.length === 0 ? <p style={secNote}>이번 자료에 제공된 추가 항목이 없습니다.</p> : null)
                        : secs.map((section: HomeSection) => {
                            const allItems = section.items || []
                            const open = !!openSec[section.title!]
                            const items = open ? allItems : allItems.slice(0, PER_SECTION)
                            return <section key={section.title} style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${C.line}` }}>
                                <h3 style={{ ...secTitle, margin: "0 0 5px" }}>{section.title}</h3>
                                <div style={secNote}>{section.note || "출처·기준일 미제공"}</div>
                                {items.map((item, index) => <div key={index} style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8, fontSize: 12, lineHeight: 1.6 }}>
                                    {item.ticker ? <a href={`${(/^[A-Za-z]/.test(item.ticker) ? _usPath(usStockPath, stockPath) : stockPath || "/stock").replace(/\/+$/, "")}?q=${encodeURIComponent(item.ticker)}`} style={{ color: C.ink, fontWeight: 700, textUnderlineOffset: 3 }}>{item.name || item.ticker}</a> : <span style={{ color: C.ink, fontWeight: 700 }}>{item.name}</span>}
                                    <span style={{ minWidth: 0, color: C.sub, fontWeight: 600 }}>{item.text || ""}{item.date ? ` · ${section.title === "이번 주 실적 공시 예상" ? "예상일 " : ""}${item.date}` : ""}</span>
                                </div>)}
                                {allItems.length > PER_SECTION ? <button type="button" onClick={() => setOpenSec(prev => ({ ...prev, [section.title!]: !open }))} style={{ border: 0, background: "transparent", color: C.vg, fontFamily: FONT, fontSize: 12, fontWeight: 700, cursor: "pointer", padding: "8px 0" }}>{open ? "접기" : `+${allItems.length - PER_SECTION}건 더보기`}</button> : null}
                            </section>
                        })}
                    <p style={{ ...secNote, marginTop: 14 }}>{brief?.disclaimer || "공시·수집 사실 · 점수·추천 아님"}</p>
                </div>
            </details>
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

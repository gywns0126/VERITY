import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 종목 리포트 — VERITY 공개 터미널 (AlphaNest). 전 종목 검색→선택→리포트.
 * 데이터 = stock_report_public + flow_5d + disclosure_forensics + insider_trades + market_warnings (Blob).
 * 🚨 시세 재배포 컴플라이언스(2026-07-03): 내장 차트(/api/chart KIS OHLCV)+실시간 현재가(/api/stock 폴링)+trending_kr
 *   = KRX/KIS 시세 재배포 → 제거. 차트 = 같은 페이지 형제 PublicLiveChart(TradingView 위젯, verity-ticker-change 추종) 위임.
 *   실시간 시세 = 네이버 link-out(증권사 서빙 = 재배포 아님). "지금 거래 활발" = 네이버 거래대금 상위 link-out.
 * 시장경보 = 경보 시 헤더(종목명·가격·메타) 통째 틴트 박스(외곽선 없음)로 감싸 한눈에. 경보 없으면 헤더 평범.
 * 폰트 = Pretendard 단일. 탭→상세 = 기본지표(계산식+실제 투입숫자 facts_calc·출처)/수급(정확 주수)/동종업계(비교)/재무(전체 재무제표 그룹) + 공시·내부자·forensics(원문) — 전업러용 raw 접근. 있는 데이터만(RULE10).
 * 다크모드 = Framer 네이티브 토글(body[data-framer-theme]) 추종 — themeDark + MutationObserver. canvas 에선 dark prop. 사이트 다크모드 버튼과 실시간 연동.
 * 관심종목 = 로그인 시 헤더 별(둥근 SVG, 2026-06-22 토스풍 라운드+소프트골드, 미담김=회색 솔리드·외곽선 없음 2026-07-19) → /api/watchgroups(JWT) 담기/해제. 미로그인=담기 안내. 세션=verity_supabase_session(AlphaNestAuth).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968",
    faint: "#8b95a1", line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", upS: "#fff0f1", down: "#3182f6", downS: "#eef4ff",
    amber: "#ff9500", amberS: "#fff6e9", green: "#15c47e", greenS: "#eafaf3",
    vg: "#6c5ce7", vgS: "#f0edff", vt: "#6c5ce7", vtS: "#f0edff", tipBg: "#191f28", tipFg: "#ffffff", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1",
    // down = #4a90f0 (2026-07-12) — 옛 #5b9bff 는 다크 표면 대비 OKLCH L=0.693 으로 다크 밴드(0.48~0.67)
    //   이탈 FAIL (dataviz validator). 교체값은 등락쌍 전 항목 PASS (protan ΔE 79.8).
    faint: "#828d9b", line: "#252b34", grid: "#1e242c", up: "#f04452", upS: "#2a1a1d", down: "#4a90f0", downS: "#152031",
    amber: "#ff9500", amberS: "#2a2113", green: "#34e08a", greenS: "#0f241c",
    vg: "#a99bff", vgS: "#241f3a", vt: "#a99bff", vtS: "#241f3a", tipBg: "#222a33", tipFg: "#e3e7ec", onAccent: "#0f1318",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const HEAD = FONT

// ── Brandfetch 로고 (토스 핫링킹 제거 2026-07-10) — logo_map(빌드타임 확정) + US 티커 규칙 + 이니셜 폴백 ──
const BF_CID = "1idalDez9T7KlggM8qX"  // 공개 임베드 client id (Logo Link 전용)
const BF_MAP_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
let __bfMap: Record<string, string> | null = null
let __bfColors: Record<string, string> = {}
let __bfShapes: Record<string, number> = {}
let __bfStyle: any = { padS: 8, padW: 15, wideRatio: 2.2 }  // 발행 데이터(style)로 조절 — 코드 수정 불요
let __bfP: Promise<Record<string, string>> | null = null
function fetchBfMap(): Promise<Record<string, string>> {
    if (__bfMap) return Promise.resolve(__bfMap)
    if (!__bfP) __bfP = fetch(BF_MAP_URL).then((r) => (r.ok ? r.json() : null)).then((d) => { __bfMap = (d && d.logos) || {}; __bfColors = (d && d.colors) || {}; __bfShapes = (d && d.shapes) || {}; __bfStyle = (d && d.style) || __bfStyle; return __bfMap as Record<string, string> }).catch(() => ({} as Record<string, string>))
    return __bfP
}
function useBfLogoMap(): Record<string, string> | null {
    const [m, setM] = useState<Record<string, string> | null>(__bfMap)
    useEffect(() => { let al = true; fetchBfMap().then((mm) => { if (al) setM(mm) }); return () => { al = false } }, [])
    return m
}
function bfLogoPad(ticker: any): string {
    // 모양 적응 패딩 — 심볼(정사각)은 크게, 워드마크(가로 김)는 여백 확보 (토스식 가시성)
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const r = __bfShapes[tk] || __bfShapes[tk.replace(/\./g, "-")] || 1
    if (r === 0) return "0%"  // 큐레이션 풀블리드 아이콘(자체 배경 포함) = 타일 꽉 채움
    return (r > (__bfStyle.wideRatio || 2.2) ? (__bfStyle.padW || 15) : (__bfStyle.padS || 8)) + "%"
}
function bfInitialBg(ticker: any): string {
    // 이니셜 타일 — 티커 해시 투톤 그라데이션 (미보유 4.6K 도 디자인 자산화, 종목별 고정색)
    let h = 0; const s = String(ticker || "?")
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360
    return "linear-gradient(135deg, hsl(" + h + ",62%,55%), hsl(" + ((h + 42) % 360) + ",68%,42%))"
}
function bfLogoBg(ticker: any): string {
    // 아이덴티티 색 틴트 타일 (토스식 참조 — 색은 로고 대표색/공식 브랜드색, 자산 복사 아님)
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    // 토스식 넉아웃 (기본): 브랜드색 솔리드 배경 + 로고 흰 실루엣(bfLogoFilter). 조건 미충족 = 솔리드 파스텔.
    // style.mode 노브: "knockout"(기본) | "pastel". mixPct = 파스텔 혼합비(기본 30).
    const p2 = (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    if (c && p2 && p2.indexOf("http") !== 0 && (__bfStyle.mode || "pastel") === "knockout") return c  // 솔리드 브랜드색
    if (!c) return "#ffffff"
    const mix = Number(__bfStyle.mixPct || 30)
    try { if (typeof CSS !== "undefined" && CSS.supports && CSS.supports("color", "color-mix(in srgb, red 50%, white)")) return `color-mix(in srgb, ${c} ${mix}%, #ffffff)` } catch (e2) {}
    return c + (__bfStyle.tintA || "4D")
}
function bfLogoFilter(ticker: any): string {
    // 넉아웃 조건과 동일할 때만 흰 실루엣 (Brandfetch 투명 로고 한정 — 파비콘류는 불투명이라 제외)
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    const p2 = (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    return (c && p2 && p2.indexOf("http") !== 0 && (__bfStyle.mode || "pastel") === "knockout") ? "brightness(0) invert(1)" : "none"
}
function bfLogoSrc(ticker: any, lm: Record<string, string> | null, size: number): string {
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    if (!tk) return ""
    // 로고 = 토스 종목 CDN (PM 결정: 완전 공개[런칭] 전까지 토스 사용, 2026-07-12). 404/차단 시 onError → 이니셜 폴백. lm 미사용.
    return "https://static.toss.im/png-icons/securities/icn-sec-fill-" + tk + ".png"
}
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
const KR_MK = ["KOSPI", "KOSDAQ", "KONEX"]
const WK = ["일", "월", "화", "수", "목", "금", "토"]

const INFO: Record<string, string> = {
    "PER": "주가 ÷ 주당순이익. 낮으면 이익 대비 싸게, 높으면 비싸게 거래된다는 뜻. 업종 평균과 비교해 봐요.",
    "PBR": "주가 ÷ 주당순자산. 1 미만이면 장부가보다 싸게 거래된다는 의미예요.",
    "ROE": "자기자본 대비 순이익률. 높을수록 자본을 효율적으로 굴린다는 뜻이에요.",
    "부채비율": "빚 ÷ 자기자본. 높을수록 빚 부담이 크다는 뜻. 업종 중앙값과 함께 봐야 해요.",
    "영업이익률": "매출 대비 영업이익 비율. 높을수록 본업 수익성이 좋다는 뜻이에요.",
    "Altman-Z": "부도 위험 점수. 3 이상이면 안전 구간, 1.8 미만이면 위험 신호로 봐요.",
    "시가총액": "주가 × 총 주식수. 회사 전체의 시장 가치예요.",
    "D/E": "부채 ÷ 자기자본. 낮을수록 빚 부담이 적어요.",
    "매출성장": "전년 대비 매출 증감률. +면 성장, −면 역성장이에요.",
    "매출총이익률": "매출에서 원가를 뺀 비율. 제품 자체의 수익성이에요.",
    "순이익률": "매출 대비 최종 순이익 비율이에요.",
    "EPS": "주당순이익. 순이익을 총 주식수로 나눈 값으로, 한 주가 1년에 번 이익이에요.",
    "배당수익률": "주가 대비 1년 배당금 비율. 높을수록 배당으로 받는 현금이 크다는 뜻이에요.",
    "수급": "외국인·기관이 이 종목을 며칠간 순매수(+, 빨강) 했는지 순매도(−, 파랑) 했는지예요. 큰손 자금 방향을 보여주지만, 그 자체가 매수·매도 신호는 아니에요.",
    "이동평균": "최근 N일 종가의 평균선. 20일=한 달 추세, 60일=분기 추세. 단기선이 장기선 위면 상승 흐름으로 봐요(신호 아님).",
    "공시이력": "이 종목이 유상증자·전환사채·감자 같은 주주가치 희석·리스크 공시를 언제 몇 번 냈는지의 사실 빈도예요. 반복이 잦을수록 참고하되, 그 자체가 좋다·나쁘다 판단은 아니에요.",
    "교차검증": "같은 지분율을 DART 공시와 공정거래위원회 공식 자료 두 곳에서 비교한 거예요. 일치하면 신뢰도가 높고, 차이가 나면 기준·시점 차이일 수 있어요.",
    "동종업계": "같은 섹터 종목들의 중앙값과 이 종목을 비교한 거예요. PER/PBR은 KRX 공식 시총÷DART 재무로 직접 계산했어요. 업종 대비 높은지/낮은지 사실 비교일 뿐, 판단은 아니에요.",
    "교차피어": "이 종목을 반대 시장(국장↔미장)의 같은 GICS 섹터 종목 중앙값과 비교한 거예요. 어느 MTS도 잘 안 주는 교차시장 비교라 참고하되, 높다·낮다가 좋다·나쁘다 판단은 아니에요.",
    "내부자": "임원·주요주주가 자기 회사 주식을 사고(+, 빨강)·팔았는지(−, 파랑)예요. 내부 사정을 아는 사람의 매매라 참고하되, 그 자체가 매수·매도 신호는 아니에요.",
    "시장경보": "KRX가 공식 지정한 투자주의·투자경고·투자위험·단기과열·관리종목 상태예요. 거래소가 위험을 경고한 사실이라 꼭 확인하되, 자체 판단은 아니에요.",
    "컨센 목표가": "증권사들이 제시한 목표주가의 평균이에요. AlphaNest 자체 의견이 아니라 애널리스트 집계 사실이고, 자체 점수는 검증 후(2027) 공개해요.",
    "재무제표": "DART 전자공시 최근 결산 실값이에요. 손익(번 돈)·재무상태(가진 것/빚)·현금흐름(실제 현금 이동)·비율을 사실 그대로 보여줘요. 단년 기준이라 추이는 아직 없어요.",
    "대차잔고": "시장에 빌려준 주식 잔고예요(공매도의 재료). 많을수록 공매도 압력이 커질 수 있다는 참고 사실이지, 그 자체가 하락 신호는 아니에요. 진짜 공매도 잔고는 아니에요(KRX 무료 비공개).",
    "공매도": "전체 거래 중 공매도가 차지한 비중이에요(최근 5일 평균). 높을수록 하락에 베팅한 거래가 많았다는 뜻으로 참고하되, 그 자체가 매도 신호는 아니에요.",
    "신용잔고": "빚내서(신용융자) 산 주식의 잔고예요. 많을수록 빚으로 산 물량이 많아, 주가가 내리면 반대매매 부담이 커질 수 있다는 참고 사실이에요.",
    "마진율": "매출에서 해당 이익이 차지하는 비율이에요(영업이익률=영업이익÷매출, 순이익률=순이익÷매출). 높을수록 같은 매출로 더 많이 남긴다는 뜻이에요.",
}
const METRIC_FORMULA: Record<string, string> = {
    "PER": "KRX 공식 시가총액 ÷ DART 순이익(최근 결산)",
    "PBR": "KRX 공식 시가총액 ÷ 자기자본(DART)",
    "ROE": "순이익 ÷ 자기자본 × 100 (DART)",
    "부채비율": "부채 ÷ 자기자본 × 100 (DART)",
    "영업이익률": "영업이익 ÷ 매출 × 100 (DART)",
    "Altman-Z": "운전자본·이익잉여금·EBIT·자기자본/부채 가중합 (부도위험 모델)",
    "EPS": "순이익 ÷ 총 발행주식수 (DART)",
    "배당수익률": "주당 배당금 ÷ 주가 × 100",
}
const GLOSSARY: Record<string, string> = {
    "유상증자": "새 주식을 발행해 돈을 조달. 주식 수가 늘어 기존 주주 지분이 옅어져요.",
    "공급계약": "납품 계약. 매출 대비 규모가 크면 실적 기대 요인이에요.",
    "자기주식": "회사가 자기 주식을 사거나 보유. 매입하면 시중 주식이 줄어 보통 우호적이에요.",
    "전환사채": "주식으로 바꿀 수 있는 채권(CB). 전환되면 주식 수가 늘어요.",
    "대량보유": "5% 이상 주주의 보유·변동 신고. 큰손 흐름이 드러나요.",
    "최대주주": "지분을 가장 많이 가진 주주. 매수·매도가 중요한 신호예요.",
}
const GKEYS = Object.keys(GLOSSARY).sort((a, b) => b.length - a.length)
const DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
const DILUTION_CATS = new Set(["유상증자", "전환사채(CB)", "신주인수권부사채(BW)", "교환사채(EB)", "자기주식처분"])
const RISK_CATS = new Set(["감자", "횡령·배임", "회생·상장폐지", "불성실공시"])
const FAVORABLE_CATS = new Set(["자기주식취득"])

interface Props {
    stockUrl: string
    usStockUrl: string
    usSmallcapUrl?: string
    flowUrl: string
    forensicsUrl: string
    insiderUrl: string
    warnUrl: string
    lendingUrl?: string
    supplyUrl?: string
    apiBase: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
// 검색 universe — 통합 KR+US ~8.4천(검색창 4종 단일 소스). 리포트 DATA(아래 DEFAULT_URL 등)와 분리:
// 검색은 전 universe, 리포트는 보유 종목만 → 미보유 종목 선택 시 graceful "준비중"(엉뚱 종목 폴백 차단).
const UNIVERSE_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
const DEFAULT_FLOW = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_flow_5d.json"
const DEFAULT_FORENSICS = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/disclosure_forensics.json"
const DEFAULT_INSIDER = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/insider_trades.json"
const DEFAULT_WARN = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/market_warnings.json"
const DEFAULT_LENDING = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/securities_lending.json"
const DEFAULT_SUPPLY = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/supply_demand.json"
const DEFAULT_EMPLOYMENT = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/nps_employment.json"
const ETF_FLOW_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/etf_flow.json"
const US_ETF_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_etf.json"
const KR_INDEX_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/kr_index_daily.json"
const CROSS_KR_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/cross_gics_kr.json"  // KR↔US 교차피어: KR 섹터 중앙값
const CROSS_US_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/cross_gics_us.json"  // KR↔US 교차피어: US 섹터 중앙값
// 시세 컴플라이언스 — 실시간 시세·거래대금 상위 = 네이버 link-out(증권사 서빙 = 재배포 아님, 실시간·무료·합법)
const NAVER_QUANT = "https://finance.naver.com/sise/sise_quant.naver"
// 2026-07-11 정정 — 옛 /sise/trade = 404(네이버 경로 변경). 모바일/PC UA 양쪽 200 실측.
const M_NAVER_QUANT = "https://m.stock.naver.com/domestic/home/trading/KOSPI"
function naverStockUrl(tk: string): string {
    if (!/^\d{6}$/.test(String(tk || ""))) return ""
    const mobile = typeof window !== "undefined" && window.innerWidth < 720
    return mobile
        ? "https://m.stock.naver.com/domestic/stock/" + tk + "/total"
        : "https://finance.naver.com/item/main.naver?code=" + tk
}
const RECENTS_KEY = "verity_recent_tickers" // nav 검색(PublicStockSearch)과 공유
function readRecents(): any[] {
    if (typeof window === "undefined") return []
    try { const a = JSON.parse(window.localStorage.getItem(RECENTS_KEY) || "[]"); return Array.isArray(a) ? a.filter((x) => x && x.t) : [] } catch { return [] }
}
const DEFAULT_API = "https://project-yw131.vercel.app"
const WATCH_SESSION_KEY = "verity_supabase_session"
const WATCH_EVENT = "verity_watch_change"
const AUTH_EVENT = "verity_auth_change"

const SAMPLE = [
    {
        ticker: "005930", name: "삼성전자", market: "KOSPI", business: "메모리·파운드리 반도체",
        facts: { PER: "14.2", PBR: "1.1", ROE: "9.1%", "부채비율": "38%", "Altman-Z": "3.4", "시가총액": "425조", "EPS": "5,280원", "배당수익률": "1.80%" },
        facts_note: { "Altman-Z": "안전구간", "PER": "자체계산", "PBR": "자체계산" },
        facts_calc: { "PER": "시가총액 425조 ÷ 순이익 45.2조", "PBR": "시가총액 425조 ÷ 자기자본 386조" },
        header: { range_52w: "49,900~88,000", trading_value: "4,210억", market_cap: "425조" },
        overview: { tagline: "메모리·파운드리 반도체", shares: "5.97억주", sector: "반도체" },
        warnings: { labels: [{ label: "단기과열", severity: "warn" }, { label: "투자주의", severity: "caution" }] },
        peer: {
            sector: "IT·기술", industry: "Semiconductors", n: 142,
            rows: [{ key: "PER", value: "14.2", median: "18.3", vs: "below", pct: 32 }, { key: "PBR", value: "1.1", median: "1.6", vs: "below", pct: 28 }, { key: "ROE", value: "9.1%", median: "7.5%", vs: "above", pct: 68 }, { key: "부채비율", value: "38%", median: "52%", vs: "below", pct: 30 }, { key: "영업이익률", value: "14.3%", median: "8.1%", vs: "above", pct: 81 }],
            note: "같은 섹터 종목 중앙값과 비교 · PER/PBR=KRX 시총÷DART 재무 자체계산 — 자체 등급 아님",
        },
        financials: {
            values: { "매출": "300조", "영업이익": "43조", "순이익": "45조" }, period: "2025",
            groups: [
                { title: "손익계산서", rows: [{ k: "매출", v: "333.6조" }, { k: "매출원가", v: "202.2조" }, { k: "매출총이익", v: "131.4조" }, { k: "영업이익", v: "43.6조" }, { k: "순이익", v: "45.2조" }, { k: "매출총이익률", v: "39.4%" }, { k: "영업이익률", v: "13.1%" }] },
                { title: "재무상태표", rows: [{ k: "총자산", v: "566.9조" }, { k: "유동자산", v: "247.7조" }, { k: "유동부채", v: "106.4조" }, { k: "이익잉여금", v: "402.1조" }, { k: "운전자본", v: "141.3조" }] },
                { title: "현금흐름표", rows: [{ k: "영업활동", v: "85.3조" }, { k: "투자활동", v: "−68.5조" }, { k: "재무활동", v: "−13.5조" }, { k: "잉여현금흐름(FCF)", v: "16.8조" }] },
                { title: "주요 비율", rows: [{ k: "부채비율", v: "29.9%" }, { k: "유동비율", v: "232.8%" }, { k: "ROE", v: "10.4%" }, { k: "ROA", v: "8%" }, { k: "자산회전율", v: "0.59회" }] },
            ],
        },
        real_estate: { total: "8.4조", items: [{ name: "토지", value: "3.2조" }, { name: "건물", value: "5.2조" }], note: "재무상태표 장부가(시가 아님) · DART" },
        disclosures: [{ title: "주요사항보고서(자기주식취득결정)", label: "주요사항", date: "2026-06-15", is_correction: false, filer: "삼성전자", source_url: DART + "20260615000777" }],
        insider: {
            net_change: 95960, buy_n: 3, sell_n: 1, total: 4,
            trades: [
                { date: "2026-06-10", person: "이재용", position: "회장", registered: "등기임원", change: 85960, shares_after: 1000000, source_url: DART + "20260610000111" },
                { date: "2026-05-20", person: "한종희", position: "부회장", registered: "등기임원", change: -20000, shares_after: 50000, source_url: DART + "20260520000222" },
            ],
        },
        ownership: {
            family_pct: 21.2, group: "삼성",
            shareholders: [{ name: "기타", type: "기타", pct: 60.3 }, { name: "소속회사", type: "소속회사", pct: 19.1 }, { name: "동일인", type: "동일인", pct: 1.2 }, { name: "친족", type: "친족", pct: 0.4 }],
            cross_check: { entity: "삼성생명", dart_pct: 8.51, ftc_pct: 8.51, status: "match" },
            sub_count: 59, note: "동일인+친족 = 총수일가 지배지분 · 공정위 분류(의결권 지분율)", source: "공정거래위원회 기업집단포털 (2026)",
        },
        consensus: { target_price: "82,000원", opinion: "매수" },
        calendar: [{ event: "실적발표", kind: "실적", date: "2026-08-05" }],
    },
    {
        ticker: "247540", name: "에코프로비엠", market: "KOSDAQ", business: "2차전지 양극재",
        facts: { PBR: "4.8", ROE: "8.1%", "부채비율": "184%" }, facts_note: {},
        financials: { values: { "매출": "5조", "영업이익": "2천억" }, period: "2025" },
        disclosures: [], ownership: null, consensus: { target_price: "165,000원", opinion: "중립" }, calendar: [],
    },
]
const SAMPLE_FLOW: Record<string, any[]> = {
    "005930": [
        { date: "2026-06-12", foreign_net: 120000, inst_net: -40000, close: 81000 },
        { date: "2026-06-15", foreign_net: 230000, inst_net: 55000, close: 81500 },
        { date: "2026-06-16", foreign_net: -90000, inst_net: 135000, close: 82000 },
        { date: "2026-06-17", foreign_net: 340000, inst_net: -20000, close: 82500 },
        { date: "2026-06-18", foreign_net: 180000, inst_net: 70000, close: 83000 },
    ],
}
const SAMPLE_FORENSICS: Record<string, any> = {
    "005930": {
        counts: { "자기주식취득": 2, "정정공시": 1 }, total: 3, dilution_count: 0,
        forensics_flags: { correction_count: 1, correction_pct: 33, dilution_12m: 0, dilution_span: "", dilution_annual_avg_prior: 0, dilution_history_from: "" },
        events: [
            { date: "2026-06-15", category: "자기주식취득", risk: "favorable", title: "주요사항보고서(자기주식취득결정)", is_correction: false, source_url: DART + "20260615000777" },
            { date: "2026-05-30", category: "정정공시", risk: "correction", title: "[기재정정]분기보고서", is_correction: true, source_url: DART + "20260530000111" },
        ],
    },
}
const SAMPLE_INSIDER: Record<string, any> = { "005930": SAMPLE[0].insider }
const SAMPLE_WARN: Record<string, any> = { "005930": SAMPLE[0].warnings }

function fmtMan(v: any): string {
    const x = Number(v)
    if (!isFinite(x)) return "—"
    const m = x / 10000
    const a = Math.abs(m)
    const body = a >= 10 ? m.toFixed(0) : m.toFixed(1)
    return (m > 0 ? "+" : "") + body + "만"
}
function fmtShares(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x === 0) return "0"
    const a = Math.abs(x)
    const sign = x > 0 ? "+" : "−"
    if (a >= 1e4) return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만주"
    return sign + Math.round(a).toLocaleString("en-US") + "주"
}
function fmtSharesExact(v: any): string {
    const x = Number(v)
    if (!isFinite(x)) return "—"
    const sign = x > 0 ? "+" : x < 0 ? "−" : ""
    return sign + Math.abs(Math.round(x)).toLocaleString("en-US") + "주"
}
function mmdd(s: any): string {
    const x = String(s || "")
    if (/^\d{8}$/.test(x)) return x.slice(4, 6) + "." + x.slice(6, 8)
    if (x.length >= 10) return x.slice(5).replace(/-/g, ".")
    return x
}
function dateDot(s: any): string {
    const x = String(s || "").replace(/-/g, "")
    if (!/^\d{8}$/.test(x)) return String(s || "")
    const wd = WK[new Date(+x.slice(0, 4), +x.slice(4, 6) - 1, +x.slice(6, 8)).getDay()]
    return `${x.slice(0, 4)}.${x.slice(4, 6)}.${x.slice(6, 8)}(${wd})`
}
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch (e) {
        return ""
    }
}
/* 등락 화살표 — 뉴스 페이지(PublicNewsTab)와 동일한 라운드 스트로크 화살표. ▲▼ 글리프 대체 (PM 2026-07-04) */
function TrendArrow({ dir, color, size = 10 }: { dir: "up" | "down" | "flat"; color: string; size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 12 12" fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0 }}>
            {dir === "up" && (<><line x1="6" y1="10" x2="6" y2="2.6" /><polyline points="2.8,5.6 6,2.4 9.2,5.6" /></>)}
            {dir === "down" && (<><line x1="6" y1="2" x2="6" y2="9.4" /><polyline points="2.8,6.4 6,9.6 9.2,6.4" /></>)}
            {dir === "flat" && (<><line x1="2" y1="6" x2="9.4" y2="6" /><polyline points="6.4,2.8 9.6,6 6.4,9.2" /></>)}
        </svg>
    )
}
function wonStr(v: any): string {
    const x = Number(v)
    if (!isFinite(x)) return "—"
    return x.toLocaleString("en-US") + "원"
}
function eokWon(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x <= 0) return "—"
    if (x >= 1e12) return (x / 1e12).toFixed(1) + "조원"
    if (x >= 1e8) return Math.round(x / 1e8).toLocaleString("en-US") + "억원"
    return Math.round(x).toLocaleString("en-US") + "원"
}
function fmtVol(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x <= 0) return "—"
    if (x >= 1e8) return (x / 1e8).toFixed(2) + "억주"
    if (x >= 1e4) return Math.round(x / 1e4).toLocaleString("en-US") + "만주"
    return Math.round(x).toLocaleString("en-US") + "주"
}
function loadWatchToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const raw = localStorage.getItem(WATCH_SESSION_KEY)
        if (!raw) return ""
        const s = JSON.parse(raw)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return ""
        return typeof s.access_token === "string" ? s.access_token : ""
    } catch { return "" }
}
function flagCode(market: any): string {
    const m = String(market || "").toUpperCase()
    if (KR_MK.indexOf(m) >= 0 || m.indexOf("KOS") >= 0 || m.indexOf("KONEX") >= 0) return "kr"
    if (m.indexOf("NAS") >= 0 || m.indexOf("NYSE") >= 0 || m.indexOf("AMEX") >= 0 || m.indexOf("US") >= 0) return "us"
    return "kr"
}
// 로고 — 토스 종목 CDN, 404/차단 시 이니셜 아바타 폴백 + circle-flags 원형 국기 코너 배지.
function Logo(props: { ticker: string; name: string; market: string; C: any; size?: number }) {
    const { ticker, name, market, C } = props
    const size = props.size || 38
    const [err, setErr] = useState(false)
    const lm = useBfLogoMap()
    const bfSrc = bfLogoSrc(ticker, lm, size)
    const ch = (String(name || "?").trim().charAt(0)) || "?"
    const code = flagCode(market)
    const fsize = Math.round(size * 0.46)
    return (
        <span style={{ position: "relative", width: size, height: size, flexShrink: 0, display: "inline-block" }}>
            {!err && bfSrc ? (
                <img src={bfSrc} alt="" loading="lazy" decoding="async" width={size} height={size}
                    onError={() => setErr(true)}
                    style={{ width: size, height: size, borderRadius: Math.round(size * 0.32), objectFit: "cover", display: "block", background: "transparent" }} />
            ) : (
                <span style={{ width: size, height: size, borderRadius: Math.round(size * 0.32), background: bfInitialBg(ticker), color: "#ffffff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * 0.42), fontWeight: 800 }}>{ch}</span>
            )}
            {code && (
                <img src={FLAG_BASE + code + ".svg"} alt="" loading="lazy" decoding="async" width={fsize} height={fsize}
                    style={{ position: "absolute", right: -3, bottom: -3, width: fsize, height: fsize, borderRadius: "50%", border: `1.5px solid ${C.card}`, background: C.card, display: "block", boxShadow: "0 1px 2px rgba(0,0,0,0.18)" }} />
            )}
        </span>
    )
}

/* 재무 시계열(매출·영업이익·순익) 추이 + 과거 비교 — DART 공시 실값(추이 그래프, 자체 산식 없음) */
function fmtKRWcompact(v: any): string {
    if (v == null || isNaN(Number(v))) return "—"
    const n = Number(v)
    const neg = n < 0
    const a = Math.abs(n)
    let s: string
    if (a >= 1e12) s = (a / 1e12).toFixed(a >= 1e13 ? 0 : 1) + "조"
    else if (a >= 1e8) s = Math.round(a / 1e8).toLocaleString() + "억"
    else if (a >= 1e4) s = Math.round(a / 1e4).toLocaleString() + "만"
    else s = Math.round(a).toLocaleString()
    return (neg ? "−" : "") + s
}
function fmtUSDcompact(v: any): string {
    if (v == null || isNaN(Number(v))) return "—"
    const n = Number(v)
    const neg = n < 0
    const a = Math.abs(n)
    let s: string
    if (a >= 1e12) s = "$" + (a / 1e12).toFixed(2) + "T"
    else if (a >= 1e9) s = "$" + (a / 1e9).toFixed(1) + "B"
    else if (a >= 1e6) s = "$" + (a / 1e6).toFixed(0) + "M"
    else s = "$" + Math.round(a).toLocaleString("en-US")
    return (neg ? "−" : "") + s
}

// Catmull-Rom → cubic bezier 부드러운 곡선 path (유선형 추이용)
/* 🧺 ETF/ETN 구성 블록 — etf_flow.json(KRX 공시 사실). 기업 리포트 대신 렌더 (2026-07-10 PM).
   흐름 = Δ상장좌수×NAV(설정/환매, 가격효과 제거). RULE 7 — 관측 사실만, 미추적 = 안내(가짜 데이터 0). */
/* 📈 지수 뷰 — kr_index_daily.json(금융위 공공데이터). 레벨·추이 차트·기간수익률. 사실만(RULE 7). */
function IndexReportBlock({ C, narrow, name, doc }: any) {
    const HEAD = "Pretendard, -apple-system, sans-serif"
    const card: any = { background: C.card, borderRadius: 16, padding: "16px 18px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const idx = doc && doc.indices ? doc.indices[name] : null
    const ser: any[] = (idx && Array.isArray(idx.c)) ? idx.c : []
    const dd = (n: any) => { const s = String(n); return s.length === 8 ? s.slice(2, 4) + "." + s.slice(4, 6) + "." + s.slice(6, 8) : s }
    const head = (
        <div style={{ display: "flex", alignItems: "baseline", gap: 9, flexWrap: "wrap", marginBottom: 4 }}>
            <span style={{ fontFamily: HEAD, fontSize: narrow ? 20 : 23, fontWeight: 800, letterSpacing: "-0.5px" }}>{name}</span>
            <span style={{ fontSize: 11, fontWeight: 800, color: C.vt, background: C.vtS, borderRadius: 7, padding: "3px 9px" }}>지수{idx && idx.csf ? " · " + idx.csf : ""}</span>
        </div>
    )
    if (!idx || ser.length === 0) {
        return <div style={{ marginTop: 14 }}>{head}<div style={card}><div style={{ fontSize: 13, color: C.sub, fontWeight: 600 }}>지수 데이터를 불러오지 못했어요</div></div></div>
    }
    const last = ser[ser.length - 1]
    const level = Number(last[1]), chg = Number(last[2])
    const periodPct = Number(ser[0][1]) ? (level - Number(ser[0][1])) / Number(ser[0][1]) * 100 : null
    const closes = ser.map((s) => Number(s[1]))
    const mn = Math.min(...closes), mx = Math.max(...closes), rng = (mx - mn) || 1
    const CW = 320, CH = 90, PX = 4, PY = 8
    const pts = ser.map((s, i) => ({ x: PX + (i / Math.max(1, ser.length - 1)) * (CW - PX * 2), y: PY + (1 - (Number(s[1]) - mn) / rng) * (CH - PY * 2) }))
    const linePath = pts.map((p, i) => (i === 0 ? "M" : "L") + p.x.toFixed(1) + " " + p.y.toFixed(1)).join(" ")
    const upC = chg >= 0 ? C.up : C.down
    return (
        <div style={{ marginTop: 14 }}>
            {head}
            <div style={card}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ fontFamily: HEAD, fontSize: 30, fontWeight: 800, color: C.ink, letterSpacing: "-1px" }}>{level.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                    <span style={{ fontSize: 15, fontWeight: 800, color: upC }}>{chg >= 0 ? "+" : ""}{chg}%</span>
                </div>
                {pts.length >= 2 && (
                    <svg width="100%" viewBox={`0 0 ${CW} ${CH}`} style={{ display: "block", marginTop: 10 }}>
                        <path d={linePath} fill="none" stroke={upC} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
                        <circle cx={pts[pts.length - 1].x} cy={pts[pts.length - 1].y} r={3.4} fill={upC} />
                    </svg>
                )}
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>
                    <span>{dd(ser[0][0])}</span><span>{dd(last[0])}</span>
                </div>
                <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 700, marginTop: 8 }}>
                    최근 {ser.length}거래일 · 기간 <span style={{ color: periodPct != null && periodPct >= 0 ? C.up : C.down }}>{periodPct != null ? (periodPct >= 0 ? "+" : "") + periodPct.toFixed(1) + "%" : "—"}</span>
                </div>
                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>금융위 공공데이터 · T+1 EOD(전일 종가) · KRX 지수 사실 · 점수·추천 아님</div>
            </div>
        </div>
    )
}

function EtfReportBlock({ C, isDark, narrow, ticker, name, market, doc, onPick }: any) {
    const CATL: Record<string, string> = {
        equity_domestic: "국내주식", equity_foreign: "해외주식", thematic: "테마", bond_kr: "한국채권",
        bond_us: "미국채권", commodity_gold: "금", commodity: "원자재", leverage: "레버리지",
        inverse: "인버스", sector_financial: "금융", sector_tech: "IT", sector: "섹터", dividend: "배당",
        reit: "리츠",
    }
    const fmtF = (won: any, signed = false) => {
        const n = Number(won)
        if (!isFinite(n) || n === 0) return signed ? "0원" : "—"
        const a = Math.abs(n), sign = signed ? (n > 0 ? "+" : "−") : ""
        if (a >= 1e12) return sign + (a / 1e12).toFixed(2) + "조원"
        if (a >= 1e8) return sign + Math.round(a / 1e8).toLocaleString() + "억원"
        return sign + Math.round(a / 1e4).toLocaleString() + "만원"
    }
    const ds = (d: string) => { const s = String(d || ""); return s.length === 8 ? `${s.slice(4, 6)}.${s.slice(6)}` : s }
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "14px 16px", marginTop: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const e = (doc && Array.isArray(doc.etfs)) ? doc.etfs.find((x: any) => String(x.ticker) === String(ticker)) : null
    const isUs = !/^[0-9]{6}$/.test(String(ticker))  // 알파벳 티커=US ETF(us_etf.json) / 6자리=KR(etf_flow)
    const hist = (doc && doc.history && doc.history[ticker]) || []
    const series: any[] = []
    let cum = 0
    for (let i2 = 1; i2 < hist.length; i2++) {
        const prev = hist[i2 - 1], cur = hist[i2]
        const dSh = Number(cur.list_shrs) - Number(prev.list_shrs)
        const flow = isFinite(dSh) && isFinite(Number(cur.nav)) ? dSh * Number(cur.nav) : 0
        cum += flow
        const prem = (isFinite(Number(cur.close)) && Number(cur.nav)) ? ((Number(cur.close) - Number(cur.nav)) / Number(cur.nav)) * 100 : null
        series.push({ date: String(cur.date), flow, cum, prem })
    }
    const flowColor = cum > 0 ? C.up : cum < 0 ? C.down : C.faint
    const prem = e && isFinite(Number(e.close)) && Number(e.nav) ? ((Number(e.close) - Number(e.nav)) / Number(e.nav)) * 100 : null
    const CW = 640, CH = 110, PX = 6, PY = 12
    const vals = series.map((x) => x.cum)
    const mn = Math.min(0, ...vals), mx = Math.max(0, ...vals), rng = (mx - mn) || 1
    const pts = series.map((s2, i2) => ({ x: PX + (i2 / Math.max(1, series.length - 1)) * (CW - PX * 2), y: PY + (1 - (s2.cum - mn) / rng) * (CH - PY * 2) }))
    const zeroY = PY + (1 - (0 - mn) / rng) * (CH - PY * 2)
    const kv = (k: string, v: string, color?: string) => (
        <div style={{ flex: 1, minWidth: 92 }}>
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 700 }}>{k}</div>
            <div style={{ fontFamily: HEAD, fontSize: 15, fontWeight: 800, color: color || C.ink, marginTop: 2, letterSpacing: "-0.3px" }}>{v}</div>
        </div>
    )
    return (
        <div style={{ marginTop: 14 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 9, flexWrap: "wrap" }}>
                <span style={{ fontFamily: HEAD, fontSize: narrow ? 20 : 23, fontWeight: 800, letterSpacing: "-0.5px" }}>{name}</span>
                <span style={{ fontSize: 12.5, color: C.faint, fontWeight: 700 }}>{ticker}</span>
                <span style={{ fontSize: 11, fontWeight: 800, color: C.vt, background: C.vtS, borderRadius: 7, padding: "3px 9px" }}>{market}{e && e.category ? " · " + (CATL[e.category] || e.category) : ""}</span>
            </div>
            {!e ? (
                <div style={card}>
                    <div style={{ fontSize: 14, fontWeight: 800 }}>이 {market}는 아직 자금흐름 관측 대상이 아니에요</div>
                    <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 600, marginTop: 6, lineHeight: 1.6 }}>
                        흐름 렌즈는 순자산 상위 ETF부터 순차 확대 중이에요. 시세·구성종목은 증권사 앱이 정확해요.
                    </div>
                </div>
            ) : isUs ? (
                <>
                    <div style={card}>
                        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                            {e.category ? kv("카테고리", String(e.category)) : null}
                            {e.aum_usd ? kv("순자산(AUM)", "$" + (Number(e.aum_usd) / 1e9).toFixed(1) + "B") : null}
                            {e.expense != null ? kv("총보수 (연)", e.expense + "%") : null}
                            {e.family ? kv("운용사", String(e.family)) : null}
                        </div>
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>미국 상장 ETF · yfinance 사실(카테고리·순자산·보수·구성) · 시세는 증권사 앱 · 점수·추천 아님</div>
                    </div>
                    {Array.isArray(e.top_holdings) && e.top_holdings.length > 0 && (
                        <div style={card}>
                            <div style={{ fontSize: 13.5, fontWeight: 800, marginBottom: 4 }}>구성종목 상위 {e.top_holdings.length}</div>
                            {e.top_holdings.map((h: any, i2: number) => (
                                <div key={i2} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0", borderTop: i2 === 0 ? "none" : "1px solid " + C.line }}>
                                    <span style={{ flexShrink: 0, width: 54, fontSize: 12, fontWeight: 800, color: C.vt }}>{h.t}</span>
                                    <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: C.sub, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{h.n}</span>
                                    <span style={{ flexShrink: 0, fontSize: 12, fontWeight: 800 }}>{h.w != null ? h.w + "%" : ""}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </>
            ) : (
                <>
                    <div style={card}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                            <span style={{ fontFamily: HEAD, fontSize: 22, fontWeight: 800, color: flowColor, letterSpacing: "-0.6px" }}>{fmtF(cum || Number(e.est_flow) || 0, true)}</span>
                            <span style={{ fontSize: 12.5, fontWeight: 700 }}>누적 순설정 (최근 {series.length || Number(e.days_n) || 0}거래일)</span>
                        </div>
                        {pts.length >= 2 && (
                            <svg width="100%" viewBox={`0 0 ${CW} ${CH}`} style={{ display: "block", marginTop: 10 }}>
                                <line x1={PX} x2={CW - PX} y1={zeroY} y2={zeroY} stroke={C.grid} strokeWidth={1} />
                                <path d={smoothLine(pts)} fill="none" stroke={flowColor} strokeWidth={2.2} strokeLinecap="round" />
                                <circle cx={pts[pts.length - 1].x} cy={pts[pts.length - 1].y} r={3.4} fill={flowColor} />
                            </svg>
                        )}
                        {series.length >= 2 && (
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>
                                <span>{ds(series[0].date)}</span><span>{ds(series[series.length - 1].date)}</span>
                            </div>
                        )}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>
                            순설정 = Δ상장좌수 × NAV (설정−환매, 가격효과 제거) · KRX 공시 사실 · 점수·추천 아님
                        </div>
                    </div>
                    <div style={card}>
                        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                            {kv("종가", Number(e.close).toLocaleString() + "원")}
                            {kv("NAV", Math.round(Number(e.nav)).toLocaleString() + "원")}
                            {kv("괴리율", prem == null ? "—" : (prem >= 0 ? "+" : "") + prem.toFixed(2) + "%", prem == null ? undefined : prem >= 0 ? C.up : C.down)}
                        </div>
                        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
                            {kv("순자산", fmtF(e.netasset))}
                            {kv("상장좌수", Number(e.list_shrs).toLocaleString() + "좌")}
                            {kv("오늘 순설정", fmtF(e.est_flow, true), Number(e.est_flow) > 0 ? C.up : Number(e.est_flow) < 0 ? C.down : undefined)}
                        </div>
                        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
                            {e.ter ? kv("총보수 (연)", String(e.ter)) : null}
                            {e.manager ? kv("운용사", String(e.manager)) : null}
                            {e.base_index ? kv("기초지수", String(e.base_index)) : null}
                        </div>
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
                            괴리율 = (종가 − NAV) ÷ NAV — 프리미엄(+)/디스카운트(−){doc && doc.bas_dd ? ` · 기준일 ${ds(String(doc.bas_dd))}` : ""}
                        </div>
                    </div>
                    {Array.isArray(e.top_holdings) && e.top_holdings.length > 0 && (
                        <div style={card}>
                            <div style={{ fontSize: 13.5, fontWeight: 800, marginBottom: 4 }}>구성종목 상위 {e.top_holdings.length}</div>
                            {e.top_holdings.map((h: any, i2: number) => {
                                const maxW = Math.max(...e.top_holdings.map((x: any) => Number(x.w) || 0), 1)
                                return (
                                    <div key={h.t} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0", borderTop: i2 === 0 ? "none" : `1px solid ${C.line}` }}>
                                        <span style={{ flexShrink: 0, minWidth: 130, maxWidth: 170, fontSize: 13, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", cursor: "pointer" }}
                                            onClick={() => { if (onPick) onPick(String(h.t), String(h.n)) }}>{h.n}</span>
                                        <div style={{ flex: 1, height: 7, borderRadius: 4, background: C.grid, overflow: "hidden" }}>
                                            <div style={{ width: `${Math.max(3, (Number(h.w) / maxW) * 100)}%`, height: "100%", borderRadius: 4, background: C.vt }} />
                                        </div>
                                        <span style={{ flexShrink: 0, minWidth: 52, textAlign: "right", fontFamily: HEAD, fontSize: 12.5, fontWeight: 800, color: C.sub }}>{Number(h.w).toFixed(2)}%</span>
                                    </div>
                                )
                            })}
                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>
                                1CU 기준 상위 구성 (네이버 금융 집계) · 종목명 클릭 = 해당 종목 리포트
                            </div>
                        </div>
                    )}
                    {series.length > 0 && (
                        <div style={card}>
                            <div style={{ fontSize: 13.5, fontWeight: 800, marginBottom: 4 }}>일별 순설정</div>
                            {series.slice(-10).reverse().map((s2: any, i2: number) => (
                                <div key={s2.date} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderTop: i2 === 0 ? "none" : `1px solid ${C.line}` }}>
                                    <span style={{ minWidth: 48, fontSize: 12.5, color: C.sub, fontWeight: 700 }}>{ds(s2.date)}</span>
                                    <span style={{ flex: 1, fontSize: 13, fontWeight: 800, color: s2.flow > 0 ? C.up : s2.flow < 0 ? C.down : C.faint }}>{fmtF(s2.flow, true)}</span>
                                    {s2.prem != null && <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>괴리 {(s2.prem >= 0 ? "+" : "") + s2.prem.toFixed(2)}%</span>}
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, margin: "14px 0 4px", lineHeight: 1.5 }}>
                KRX OpenAPI 공시 사실 · 자금흐름 = 설정/환매 관측 · AlphaNest 의견·추천 아님
            </div>
        </div>
    )
}

function smoothLine(p: { x: number; y: number }[]): string {
    // 직선 꺾은선(선형) — 곡선 보간은 실측값 사이를 지어내는 인상 (PM 2026-07-04 '그래프 선형으로')
    // ETF 자금흐름(EtfReportBlock) 등 관측 시계열은 선형 유지. 연간 손익만 curveLine(유선형) 사용.
    if (!p.length) return ""
    if (p.length === 1) return `M ${p[0].x} ${p[0].y}`
    let d = `M ${p[0].x} ${p[0].y}`
    for (let i = 1; i < p.length; i++) {
        d += ` L ${p[i].x} ${p[i].y}`
    }
    return d
}

// Catmull-Rom → cubic bezier 유선형 곡선 (PM 2026-07-11 '연간 손익 유선형으로'). 연간 손익 추이 전용.
// 실측값(연도별 정점)은 그대로 통과 — 곡선은 정점 사이 보간만 부드럽게. 점 2개 이하는 직선 폴백.
// TENS = 곡률(control point 오프셋). 표준 Catmull-Rom = 1/6(0.167). 낮출수록 정점 쪽으로 당겨져
//   급한 곡률(직선에 가까움) → 정점 사이 보정(interpolation) 인상 축소 (PM 2026-07-11 '곡률 급하게').
const CURVE_TENS = 0.09
function curveLine(p: { x: number; y: number }[]): string {
    if (!p.length) return ""
    if (p.length === 1) return `M ${p[0].x} ${p[0].y}`
    if (p.length === 2) return `M ${p[0].x} ${p[0].y} L ${p[1].x} ${p[1].y}`
    let d = `M ${p[0].x.toFixed(2)} ${p[0].y.toFixed(2)}`
    for (let i = 0; i < p.length - 1; i++) {
        const p0 = p[i - 1] || p[i]
        const p1 = p[i]
        const p2 = p[i + 1]
        const p3 = p[i + 2] || p2
        const c1x = p1.x + (p2.x - p0.x) * CURVE_TENS, c1y = p1.y + (p2.y - p0.y) * CURVE_TENS
        const c2x = p2.x - (p3.x - p1.x) * CURVE_TENS, c2y = p2.y - (p3.y - p1.y) * CURVE_TENS
        d += ` C ${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`
    }
    return d
}

function FinTrend({ series, C, usd }: { series: any[]; C: any; usd?: boolean }) {
    const [metric, setMetric] = useState<"revenue" | "op" | "net">("revenue")
    const METRICS: { k: "revenue" | "op" | "net"; l: string }[] = [
        { k: "revenue", l: "매출" }, { k: "op", l: "영업이익" }, { k: "net", l: "순이익" },
    ]
    const pts = (series || []).filter((p) => p && p.year != null)
    if (pts.length < 2) return null
    const last = pts[pts.length - 1]
    const lastYear = Number(last.year)
    const valOf = (p: any) => (p && p[metric] != null && !isNaN(Number(p[metric]))) ? Number(p[metric]) : null
    const vals = pts.map(valOf).filter((v): v is number => v != null)
    const maxAbs = Math.max(1, ...vals.map((v) => Math.abs(v)))
    const hasNeg = vals.some((v) => v < 0)
    const lastVal = valOf(last)
    const cmp = (n: number) => {
        const prev = pts.find((p) => Number(p.year) === lastYear - n)
        const pv = prev ? valOf(prev) : null
        if (pv == null || lastVal == null || pv === 0) return null
        return ((lastVal - pv) / Math.abs(pv)) * 100
    }
    const COMPARES = [{ n: 1, l: "1년 전" }, { n: 3, l: "3년 전" }, { n: 5, l: "5년 전" }]
    // 유선형 추이 좌표 (viewBox 0~100 × 0~H, preserveAspectRatio none + non-scaling-stroke)
    const H = 110, PADV = 8
    const baseY = hasNeg ? H / 2 : H - PADV
    const ampl = hasNeg ? (H / 2 - PADV) : (H - 2 * PADV)
    const xy = pts.map((p, i) => {
        const v = valOf(p)
        const x = pts.length <= 1 ? 50 : (i / (pts.length - 1)) * 100
        const y = v == null ? baseY : baseY - (v / maxAbs) * ampl
        return { x: +x.toFixed(2), y: +y.toFixed(2), v }
    })
    const defined = xy.filter((q) => q.v != null)
    const linePath = curveLine(defined)
    const areaPath = defined.length >= 2 ? linePath + ` L ${defined[defined.length - 1].x} ${baseY} L ${defined[0].x} ${baseY} Z` : ""
    // 마진율 % 오버레이 (영업이익률/순이익률) — 매출 선택 시 생략. 자체 y-범위(추이 모양용).
    const revOf = (p: any) => (p && p.revenue != null && !isNaN(Number(p.revenue))) ? Number(p.revenue) : null
    const showMargin = metric !== "revenue"
    const marginVals = pts.map((p) => { const v = valOf(p); const r = revOf(p); return (v != null && r && r !== 0) ? (v / r) * 100 : null })
    const mDef = marginVals.filter((m): m is number => m != null)
    const mMin = mDef.length ? Math.min(...mDef) : 0
    const mRange = (mDef.length ? Math.max(...mDef) - mMin : 1) || 1
    const mXY = pts.map((p, i) => {
        const m = marginVals[i]
        if (m == null) return null
        const x = pts.length <= 1 ? 50 : (i / (pts.length - 1)) * 100
        const y = (H - PADV) - ((m - mMin) / mRange) * (H - 2 * PADV)
        return { x: +x.toFixed(2), y: +y.toFixed(2) }
    }).filter((q): q is { x: number; y: number } => q != null)
    const marginPath = showMargin && mXY.length >= 2 ? curveLine(mXY) : ""
    const lastMargin = [...marginVals].reverse().find((m) => m != null)
    const marginLabel = metric === "op" ? "영업이익률" : "순이익률"
    return (
        <div style={{ background: C.card, borderRadius: 16, padding: "12px 16px 14px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            {/* metric 선택 */}
            <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
                {METRICS.map((m) => (
                    <button key={m.k} onClick={() => setMetric(m.k)} style={{ flex: 1, border: "none", cursor: "pointer", padding: "7px 0", borderRadius: 9, fontSize: 12, fontWeight: 800, fontFamily: FONT, background: metric === m.k ? C.vt : C.bg, color: metric === m.k ? C.onAccent : C.sub }}>{m.l}</button>
                ))}
            </div>
            {/* 최신값 */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4 }}>
                <span style={{ fontFamily: HEAD, fontSize: 22, fontWeight: 800, color: C.ink, letterSpacing: "-0.6px" }}>{usd ? fmtUSDcompact(lastVal) : fmtKRWcompact(lastVal)}</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: C.faint }}>{lastYear} {METRICS.find((m) => m.k === metric)!.l}</span>
                {showMargin && lastMargin != null && (
                    <span style={{ fontSize: 11.5, fontWeight: 800, color: C.amber, marginLeft: "auto" }}>{marginLabel} {lastMargin.toFixed(1)}%</span>
                )}
            </div>
            {/* 과거 비교 칩 */}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
                {COMPARES.map((c) => {
                    const ch = cmp(c.n)
                    if (ch == null) return null
                    const col = ch > 0 ? C.up : ch < 0 ? C.down : C.faint
                    return (
                        <span key={c.n} style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 11.5, fontWeight: 700, color: col, background: C.bg, borderRadius: 8, padding: "5px 9px" }}>
                            {c.l} 대비 {ch !== 0 && <TrendArrow dir={ch > 0 ? "up" : "down"} color={col} />}{Math.abs(ch).toFixed(0)}%
                        </span>
                    )
                })}
            </div>
            {/* 유선형 추이 — 부드러운 곡선(Catmull-Rom) + 영역 + 마진율 오버레이(amber 점선) */}
            <svg viewBox={`0 0 100 ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: H, display: "block", overflow: "visible" }}>
                {hasNeg && <line x1={0} y1={baseY} x2={100} y2={baseY} stroke={C.line} strokeWidth={1} vectorEffect="non-scaling-stroke" />}
                {areaPath && <path d={areaPath} fill={C.vt} fillOpacity={0.1} stroke="none" />}
                {linePath && <path d={linePath} fill="none" stroke={C.vt} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />}
                {marginPath && <path d={marginPath} fill="none" stroke={C.amber} strokeWidth={1.6} strokeDasharray="3 2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />}
            </svg>
            {showMargin && marginPath && (
                <div style={{ display: "flex", gap: 12, marginTop: 6, fontSize: 10.5, fontWeight: 700 }}>
                    <span style={{ color: C.vt }}>— {METRICS.find((m) => m.k === metric)!.l}</span>
                    <span style={{ color: C.amber }}>┄ {marginLabel}(매출 대비)</span>
                </div>
            )}
            {/* 연도 라벨 */}
            <div style={{ display: "flex", gap: 3, marginTop: 5 }}>
                {pts.map((p, i) => (
                    <div key={p.year} style={{ flex: 1, minWidth: 0, textAlign: "center", fontSize: 8.5, fontWeight: 700, color: Number(p.year) === lastYear ? C.vt : C.faint }}>
                        {(i === 0 || i === pts.length - 1 || pts.length <= 7 || i % 2 === 0) ? "'" + String(p.year).slice(2) : ""}
                    </div>
                ))}
            </div>
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>{usd ? "SEC 10-K" : "DART 전자공시"} 연간 실값(추이선) · 증감은 위 과거 비교 칩(↑증가 ↓감소)</div>
        </div>
    )
}

/* 분기 재무 추이 — 인라인(2026-06-27, 컴포넌트 import 캐시 회피). 선형 차트 + 영역 + 최고/최저점.
   데이터 = dart_quarterly_public.json (backfill 누적분). 실데이터 4분기 미만 시 자동 숨김(RULE 7). 캔버스=SAMPLE.
   필드 = dart_quarterly_snapshots.jsonl 스키마 정합. 색: 라인/영역=vt보라 / 개선=green / 악화=amber. */
const QT_DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/dart_quarterly_public.json"
const QT_US_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_quarterly_public.json"  // 미장 분기추이(us_quarterly_public_builder)
const QT_METRICS: { key: string; label: string; unit: string; better: "up" | "down"; note?: string }[] = [
    { key: "debt_ratio", label: "부채비율", unit: "%", better: "down" },
    { key: "roa", label: "ROA", unit: "%", better: "up" },
    { key: "current_ratio", label: "유동비율", unit: "%", better: "up" },
    { key: "gross_margin", label: "매출총이익률", unit: "%", better: "up", note: "분기 누적" },
]
const QT_SAMPLE = (() => {
    const qs: any[] = []
    const ends = ["03-31", "06-30", "09-30", "12-31"]
    let i = 0
    for (let y = 2021; y <= 2025; y++) for (const e of ends) {
        const t = i / 19
        qs.push({
            q: `${y}-${e}`,
            debt_ratio: +(168 - 76 * t + Math.sin(i) * 4).toFixed(1),
            roa: +(1.2 + 5.6 * t + Math.cos(i * 1.3) * 0.35).toFixed(2),
            current_ratio: +(98 + 67 * t + Math.sin(i * 0.8) * 5).toFixed(1),
            gross_margin: +(31 + 11 * t + Math.cos(i) * 0.9).toFixed(1),
        })
        i++
    }
    return qs
})()
function qtLabel(qEnd: string): string {
    const s = String(qEnd || "")
    if (s.length < 10) return s
    const y = s.slice(2, 4); const mm = s.slice(5, 7)
    const q = mm === "03" ? "1Q" : mm === "06" ? "2Q" : mm === "09" ? "3Q" : mm === "12" ? "4Q" : mm
    return `${y}.${q}`
}

function QuarterlyTrend({ ticker, C, isDark, showExtremes = true, quarterlyUrl = QT_DEFAULT_URL, maxQuarters = 40, embedded = false, onCount }: { ticker: string; C: any; isDark: boolean; showExtremes?: boolean; quarterlyUrl?: string; maxQuarters?: number; embedded?: boolean; onCount?: (n: number) => void }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const ref = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [quarters, setQuarters] = useState<any[]>(onCanvas ? QT_SAMPLE : [])
    useEffect(() => {
        const el = ref.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((es) => { for (const e of es) setW(e.contentRect.width) })
        ro.observe(el); return () => ro.disconnect()
    }, [])
    useEffect(() => {
        if (onCanvas || !quarterlyUrl || !ticker) return
        let alive = true
        fetch(quarterlyUrl).then((r) => (r.ok ? r.json() : null)).then((d) => {
            const rec = d && d.stocks && d.stocks[ticker]
            const arr = rec && Array.isArray(rec.quarters) ? rec.quarters : null
            if (alive && arr && arr.length) setQuarters(arr)
        }).catch(() => {})
        return () => { alive = false }
    }, [quarterlyUrl, ticker, onCanvas])
    const cap = Math.max(4, Math.min(40, maxQuarters || 20))
    const series = useMemo(() => [...quarters].sort((a, b) => String(a.q).localeCompare(String(b.q))).slice(-cap), [quarters, cap])
    // 병합 '재무 추이' 탭 가용성 보고 — 부모가 '분기 건전성' 탭 노출 여부 판단 (2026-07-10)
    useEffect(() => { if (onCount) onCount(series.length) }, [series.length])
    const narrow = w > 0 && w < 420
    if (!onCanvas && series.length < 4) return null
    const CW = Math.max(80, (w || 360) - (narrow ? 28 : 36))
    const CH = 84, PX = 4, PY = 20   // PY 크게 = 최고/최저 라벨이 라인·상하단과 안 겹침
    return (
        <div ref={ref} style={{ background: C.card, borderRadius: 16, padding: narrow ? "15px 14px" : "17px 18px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                {/* embedded = 병합 '재무 추이' 섹션 안 탭 콘텐츠 — 섹션 제목과 중복되는 자체 제목 생략 */}
                {!embedded && <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.4px", color: C.ink }}>분기 재무 추이</span>}
                <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{embedded ? `최근 ${series.length}분기 · 실값` : `최근 ${series.length}분기 · DART 분기보고서 · 사실`}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 0, marginTop: 10 }}>
                {QT_METRICS.map((m, mi) => {
                    const raw = series.map((q) => { const v = q[m.key]; return typeof v === "number" && isFinite(v) ? v : null })
                    const present = raw.filter((v): v is number => v != null)
                    if (present.length < 2) return null
                    const lo = Math.min(...present), hi = Math.max(...present), span = hi - lo || 1
                    const first = present[0], last = present[present.length - 1], delta = last - first
                    const improved = m.better === "down" ? delta < 0 : delta > 0
                    const flat = Math.abs(delta) < span * 0.04
                    const dirColor = flat ? C.faint : improved ? C.green : C.amber
                    const dirBg = flat ? C.line : improved ? C.greenS : C.amberS
                    const lineColor = flat ? C.faint : delta > 0 ? C.up : C.down  // 라인=값 상승(빨강)/하락(파랑), KR 등락식
                    const dirText = flat ? "보합" : improved ? "개선" : "악화"
                    const arrowDir: "up" | "down" | "flat" = flat ? "flat" : improved ? "up" : "down"
                    const dec = m.key === "roa" ? 2 : 1
                    const n = raw.length
                    const xAt = (i: number) => PX + (n <= 1 ? 0 : (i / (n - 1)) * (CW - PX * 2))
                    const yAt = (v: number) => PY + (1 - (v - lo) / span) * (CH - PY * 2)
                    const pts = raw.map((v, i) => (v == null ? null : { x: xAt(i), y: yAt(v), v, i })).filter((p): p is { x: number; y: number; v: number; i: number } => p != null)
                    // 유선형(Catmull-Rom→베지어) — 2026-07-08 PM 승인: 7/4 '그래프 선형' 결정 override.
                    //   장력 1/6(표준, BondRegime 동일) = 실측점 밖 overshoot 최소화(분기 사이 값 지어냄 인상 억제).
                    const linePath = pts.length < 2
                        ? (pts.length ? `M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}` : "")
                        : (() => {
                            let d = `M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`
                            for (let i = 0; i < pts.length - 1; i++) {
                                const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2
                                const c1x = p1.x + (p2.x - p0.x) / 6, c2x = p2.x - (p3.x - p1.x) / 6
                                // control point y 를 세그먼트 두 끝점 범위로 clamp → 큐빅 베지어가 그 y-band 안에
                                //   갇혀 실측 min/max 밖으로 overshoot 0 (2026-07-09: '최저 1.82보다 밑으로 내려감'
                                //   괴리 해소. 곡선 유지하되 분기 사이 값 지어냄 인상 차단).
                                const loY = Math.min(p1.y, p2.y), hiY = Math.max(p1.y, p2.y)
                                const c1y = Math.max(loY, Math.min(hiY, p1.y + (p2.y - p0.y) / 6))
                                const c2y = Math.max(loY, Math.min(hiY, p2.y - (p3.y - p1.y) / 6))
                                d += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`
                            }
                            return d
                        })()
                    const areaPath = `${linePath} L${pts[pts.length - 1].x.toFixed(1)},${CH - 1} L${pts[0].x.toFixed(1)},${CH - 1} Z`
                    const hiPt = pts.reduce((a, b) => (b.v > a.v ? b : a))
                    const loPt = pts.reduce((a, b) => (b.v < a.v ? b : a))
                    const lastPt = pts[pts.length - 1]
                    const gid = `qtr-${m.key}-${mi}`
                    const clampX = (x: number) => Math.max(16, Math.min(CW - 16, x))
                    return (
                        <div key={m.key} style={{ padding: "20px 0", borderTop: mi === 0 ? "none" : `1px solid ${C.line}` }}>
                            <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 12, flexWrap: "wrap" }}>
                                <span style={{ fontSize: 13, fontWeight: 700, color: C.ink }}>{m.label}</span>
                                {m.note && <span style={{ fontSize: 10, color: C.faint, fontWeight: 600 }}>· {m.note}</span>}
                                <span style={{ marginLeft: "auto", fontSize: 15, fontWeight: 800, letterSpacing: "-0.3px", color: C.ink, fontVariantNumeric: "tabular-nums" }}>{last.toFixed(dec)}{m.unit}</span>
                                <span style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 10.5, fontWeight: 800, color: dirColor, background: dirBg, borderRadius: 6, padding: "2px 7px" }}><TrendArrow dir={arrowDir} color={dirColor} size={9} /> {dirText}</span>
                            </div>
                            {/* 측정폭(CW) 고정 렌더 — width:100% 스트레치는 svg 내부 텍스트·원을 가로로 왜곡 (PM 2026-07-04) */}
                            <svg width={CW} height={CH} style={{ display: "block", overflow: "visible" }} viewBox={`0 0 ${CW} ${CH}`}>
                                <defs>
                                    <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor={lineColor} stopOpacity={isDark ? 0.26 : 0.16} />
                                        <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <path d={areaPath} fill={`url(#${gid})`} />
                                <path d={linePath} fill="none" stroke={lineColor} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                                {showExtremes && (
                                    <>
                                        <circle cx={hiPt.x} cy={hiPt.y} r={2.6} fill={C.card} stroke={lineColor} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
                                        <circle cx={loPt.x} cy={loPt.y} r={2.6} fill={C.card} stroke={lineColor} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
                                        <text x={clampX(hiPt.x)} y={Math.max(9, hiPt.y - 8)} textAnchor="middle" fontSize={9} fontWeight={700} fill={C.faint} fontFamily={FONT}>최고 {hiPt.v.toFixed(dec)}</text>
                                        <text x={clampX(loPt.x)} y={Math.min(CH - 3, loPt.y + 14)} textAnchor="middle" fontSize={9} fontWeight={700} fill={C.faint} fontFamily={FONT}>최저 {loPt.v.toFixed(dec)}</text>
                                    </>
                                )}
                                <circle cx={lastPt.x} cy={lastPt.y} r={3.4} fill={lineColor} stroke={C.card} strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
                            </svg>
                            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 9 }}>
                                <span style={{ fontSize: 10, color: C.faint, fontWeight: 600 }}>{qtLabel(series[0].q)}</span>
                                <span style={{ fontSize: 10, color: dirColor, fontWeight: 700 }}>{(delta > 0 ? "+" : "") + delta.toFixed(dec)}{m.unit} ({series.length}분기)</span>
                                <span style={{ fontSize: 10, color: C.faint, fontWeight: 600 }}>{qtLabel(series[series.length - 1].q)}</span>
                            </div>
                        </div>
                    )
                })}
            </div>
            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>
                출처 DART 분기·반기·사업보고서 · 비율 자체계산(사실){showExtremes ? " · ○ 최고·최저점" : ""}
                {onCanvas && <span style={{ color: C.amber }}> · ⚠ SAMPLE 미리보기(실데이터는 backfill 누적 후)</span>}
            </div>
        </div>
    )
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
/* 로딩 스켈레톤 — 토스식: 회색 placeholder가 리포트 레이아웃을 미리 그림 + shimmer.
 * 삼성전자 샘플 flash 대신 노출. 즉시 로드 깜빡임은 호출부 160ms 지연 게이트로 차단. */
function StockReportSkeleton({ C, isDark, narrow }: { C: any; isDark: boolean; narrow: boolean }) {
    const base = isDark ? "#222a33" : "#e9edf1"
    const hi = isDark ? "#2d3742" : "#f3f5f7"
    const sk = (w: number | string, h: number, r = 8, mt = 0): CSSProperties => ({
        width: w, height: h, borderRadius: r, marginTop: mt, background: base,
        backgroundImage: `linear-gradient(90deg, ${base} 25%, ${hi} 37%, ${base} 63%)`,
        backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite",
    })
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "14px 16px", marginTop: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    return (
        <>
            <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            <div style={sk("100%", 44, 12)} />
            <div style={{ ...card, display: "flex", alignItems: "center", gap: 12 }}>
                <div style={sk(44, 44, 12)} />
                <div style={{ flex: 1 }}><div style={sk(140, 18, 6)} /><div style={sk(90, 13, 5, 8)} /></div>
                <div><div style={sk(100, 22, 6)} /><div style={sk(64, 13, 5, 8)} /></div>
            </div>
            <div style={{ ...card, display: "flex", gap: 8 }}>
                {[0, 1, 2, 3].map((i) => <div key={i} style={{ flex: 1 }}><div style={sk("100%", 48, 10)} /></div>)}
            </div>
            <div style={card}><div style={sk("100%", narrow ? 200 : 240, 12)} /></div>
            {[0, 1].map((i) => (
                <div key={i} style={card}>
                    <div style={sk(120, 15, 6)} />
                    <div style={sk("100%", 12, 5, 12)} />
                    <div style={sk("85%", 12, 5, 8)} />
                    <div style={sk("60%", 12, 5, 8)} />
                </div>
            ))}
        </>
    )
}

/* ────────────────────────────────────────────────────────────────────────────
   데이터 시각화 (2026-07-12) — dataviz 가이드 정합. 형태는 데이터의 '일'이 결정.

   🚨 색 규칙 (validator 실측, 눈대중 아님):
     · 등락 빨강(#f04452) / 파랑(#3182f6·다크 #4a90f0) = 다이버징 쌍. 전 항목 PASS (protan ΔE 80).
     · 🚨 보라(C.vt) 는 차트 계열색 금지 — 파랑과 deutan ΔE 6.6 (안전 하한 8 미달, 적록색약 구분 불가).
       보라 = UI 액센트(버튼·칩) 전용. 아래 두 차트는 등락색 + 중립 회색만 사용.
     · 곡선 보간 금지(PM 2026-07-04) — 아래는 둘 다 막대(보간 자체가 없음).
   RULE 7 = 사실만. 자체 점수·추천 0. 데이터 없으면 렌더 자체를 안 함(가짜 추세 0).
   ──────────────────────────────────────────────────────────────────────────── */

/* 한글 축약 금액 문자열 → 숫자 (예 "9043억" → 9.043e11, "−2318억" → −2.318e11, "3.1조" → 3.1e12).
   음수 = U+2212(−) 또는 ASCII(-) 양쪽. 파싱 실패 = null (차트 미렌더 → 가짜 값 0). */
function parseKRWCompact(v: any): number | null {
    if (typeof v === "number") return isFinite(v) ? v : null
    const raw = String(v == null ? "" : v).trim().replace(/,/g, "").replace(/\s/g, "")
    if (!raw) return null
    const neg = raw.charAt(0) === "−" || raw.charAt(0) === "-" || raw.charAt(0) === "△"
    const body = neg ? raw.slice(1) : raw
    const m = body.match(/^([0-9]*\.?[0-9]+)(조|억|만)?원?$/)
    if (!m) return null
    const n = parseFloat(m[1])
    if (!isFinite(n)) return null
    const unit = m[2]
    const mul = unit === "조" ? 1e12 : unit === "억" ? 1e8 : unit === "만" ? 1e4 : 1
    return (neg ? -1 : 1) * n * mul
}

/* 수급 — 외국인·기관 5일 순매매 다이버징 막대.
   데이터의 일 = 부호 있는 크기 비교(사자/팔자) → 0 기준선 다이버징 막대. 색 = 등락 관례(+빨강/−파랑).
   계열 2개(외국인·기관) = 범례 필수 + 직접 라벨. 호버 = 막대별 정확 주수 툴팁. */
function FlowDivergingChart({ rows, C, narrow }: { rows: any[]; C: any; narrow: boolean }) {
    const [hov, setHov] = useState<string>("")
    // 🚨 측정폭 고정 렌더 — preserveAspectRatio="none" + width:100% 스트레치는 rect 의 rx(라운드)를
    //    가로로 늘려 타원으로 왜곡 (PM 2026-07-04 QuarterlyTrend 학습). 실측 폭으로 그린다.
    const boxRef = useRef<HTMLDivElement>(null)
    const [bw, setBw] = useState(0)
    useEffect(() => {
        const el = boxRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((es) => { for (const e of es) setBw(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])
    const data = (rows || []).filter((r) => r && (r.foreign_net != null || r.inst_net != null))
    const maxAbs = Math.max(1, ...data.map((r) => Math.max(Math.abs(Number(r.foreign_net) || 0), Math.abs(Number(r.inst_net) || 0))))
    const H = 132, MID = H / 2, AMP = MID - 16   // 상하 여백 = 직접 라벨 자리
    const CW = Math.max(60, bw || 300)
    const COLS = Math.max(1, data.length)
    const colW = CW / COLS
    const barW = Math.max(4, Math.min(14, colW * 0.3))   // 얇은 마크
    const gap = Math.max(2, colW * 0.06)                 // 계열 사이 표면 간격
    const SERIES = [
        { key: "foreign_net", label: "외국인", off: -(barW / 2 + gap / 2) },
        { key: "inst_net", label: "기관", off: (barW / 2 + gap / 2) },
    ]
    if (data.length < 2) return null
    return (
        <div ref={boxRef} style={{ position: "relative", padding: "4px 2px 0" }}>
            {/* 범례 — 계열 2개 = 필수 (색 단독 식별 금지). 텍스트는 ink 토큰, 마크가 정체성 운반 */}
            <div style={{ display: "flex", gap: 12, marginBottom: 6 }}>
                {SERIES.map((s2) => (
                    <span key={s2.key} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: C.sub }}>
                        <span style={{ width: 9, height: 9, borderRadius: 3, background: s2.key === "foreign_net" ? C.ink : C.faint }} />
                        {s2.label}
                    </span>
                ))}
                <span style={{ marginLeft: "auto", fontSize: 10.5, fontWeight: 600, color: C.faint }}>위=순매수 · 아래=순매도</span>
            </div>
            <svg width={CW} height={H} viewBox={`0 0 ${CW} ${H}`} style={{ display: "block", overflow: "visible" }}>
                <line x1={0} y1={MID} x2={CW} y2={MID} stroke={C.line} strokeWidth={1} vectorEffect="non-scaling-stroke" />
                {data.map((r, i) => {
                    const cx = colW * (i + 0.5)
                    return SERIES.map((s2) => {
                        const v = Number(r[s2.key]) || 0
                        const h = (Math.abs(v) / maxAbs) * AMP
                        const pos = v >= 0
                        const col = pos ? C.up : C.down
                        const x = cx + s2.off - barW / 2
                        const y = pos ? MID - h : MID
                        const id = i + ":" + s2.key
                        // 4px 라운드 데이터 엔드 = 기준선에서 먼 쪽만. 최소 높이 1.5 (0 도 존재 표시)
                        const hh = Math.max(1.5, h)
                        return (
                            <rect key={id} x={x} y={pos ? MID - hh : MID} width={barW} height={hh}
                                rx={2} fill={col} opacity={hov && hov !== id ? 0.35 : 1}
                                onMouseEnter={() => setHov(id)} onMouseLeave={() => setHov("")}
                                style={{ cursor: "pointer", transition: "opacity 0.12s" }} />
                        )
                    })
                })}
            </svg>
            {/* 날짜 축 — 직접 라벨(모든 점에 숫자 X) */}
            <div style={{ display: "flex", marginTop: 4 }}>
                {data.map((r, i) => (
                    <div key={i} style={{ flex: 1, textAlign: "center", fontSize: 10, fontWeight: 700, color: C.faint }}>{mmdd(r.date)}</div>
                ))}
            </div>
            {/* 호버 툴팁 — 정확 주수(사실). 막대보다 큰 히트 타깃은 rect 자체 */}
            {hov && (() => {
                const [ii, key] = hov.split(":")
                const r = data[Number(ii)]
                if (!r) return null
                const v = Number(r[key]) || 0
                const lbl = key === "foreign_net" ? "외국인" : "기관"
                return (
                    <div style={{ marginTop: 6, background: C.tipBg, color: C.tipFg, borderRadius: 10, padding: "8px 11px", fontSize: 12, fontWeight: 600, lineHeight: 1.5 }}>
                        <b>{dateDot(r.date)}</b> · {lbl} <span style={{ fontWeight: 800, color: v >= 0 ? "#ff8f97" : "#9fc6ff" }}>{fmtSharesExact(v)}</span>
                        {r.close != null ? <span style={{ color: C.faint }}> · 종가 {wonStr(r.close)}</span> : null}
                    </div>
                )
            })()}
        </div>
    )
}

/* 현금흐름 워터폴 — 영업 → 투자 → 재무 → 순증감.
   데이터의 일 = 부호 있는 구성요소가 누적되어 합계를 이룸 → 워터폴(막대의 정석 용례).
   토스·네이버·증권사 앱 어디에도 없는 뷰. 자체 산식 0 — DART 실값을 더하기만 함(RULE 7).
   파싱 실패 항목이 하나라도 있으면 렌더 안 함(가짜 숫자 0). */
function CashflowWaterfall({ group, C, narrow }: { group: any; C: any; narrow: boolean }) {
    const [hov, setHov] = useState<number>(-1)
    // 측정폭 고정 렌더 (PM 2026-07-04) — 스트레치 시 rx 라운드가 타원으로 왜곡됨
    const boxRef = useRef<HTMLDivElement>(null)
    const [bw, setBw] = useState(0)
    useEffect(() => {
        const el = boxRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((es) => { for (const e of es) setBw(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])
    const rows: any[] = (group && Array.isArray(group.rows)) ? group.rows : []
    const pick = (k: string) => { const r = rows.find((x: any) => String(x.k || "").indexOf(k) === 0); return r ? parseKRWCompact(r.v) : null }
    const op = pick("영업활동"), inv = pick("투자활동"), fin = pick("재무활동")
    if (op == null || inv == null || fin == null) return null
    const steps = [
        { label: "영업활동", v: op, note: "본업이 벌어들인 현금" },
        { label: "투자활동", v: inv, note: "설비·지분 등에 쓴 현금" },
        { label: "재무활동", v: fin, note: "차입·배당 등 자금 조달/상환" },
    ]
    const net = op + inv + fin
    // 누적 경로 — 각 막대는 이전 누적에서 시작해 v 만큼 이동. 마지막 = 합계(0 기준 전체 막대).
    let run = 0
    const bars = steps.map((s2) => { const from = run; run += s2.v; return { ...s2, from, to: run } })
    const all = [0, ...bars.map((b) => b.from), ...bars.map((b) => b.to), net]
    const lo = Math.min(...all), hi = Math.max(...all)
    const span = (hi - lo) || 1
    const H = 150, PY = 22
    const yAt = (v: number) => PY + (1 - (v - lo) / span) * (H - PY * 2)
    const CW = Math.max(60, bw || 300)
    const COLS = bars.length + 1
    const colW = CW / COLS
    const barW = Math.max(8, Math.min(34, colW * 0.44))
    const zeroY = yAt(0)
    const cells = [
        ...bars.map((b, i) => ({ ...b, i, isTotal: false, top: Math.min(yAt(b.from), yAt(b.to)), bot: Math.max(yAt(b.from), yAt(b.to)) })),
        { label: "순증감", v: net, note: "영업 + 투자 + 재무", from: 0, to: net, i: bars.length, isTotal: true, top: Math.min(zeroY, yAt(net)), bot: Math.max(zeroY, yAt(net)) },
    ]
    return (
        <div ref={boxRef} style={{ position: "relative" }}>
            <svg width={CW} height={H} viewBox={`0 0 ${CW} ${H}`} style={{ display: "block", overflow: "visible" }}>
                <line x1={0} y1={zeroY} x2={CW} y2={zeroY} stroke={C.line} strokeWidth={1} vectorEffect="non-scaling-stroke" />
                {cells.map((c) => {
                    const cx = colW * (c.i + 0.5)
                    const x = cx - barW / 2
                    const h = Math.max(1.5, c.bot - c.top)
                    // 합계 = 중립 회색(구성요소가 아니라 결과 — 색으로 계열 오인 방지). 구성 = 등락색.
                    const col = c.isTotal ? C.faint : (c.v >= 0 ? C.up : C.down)
                    return (
                        <g key={c.i}>
                            {/* 연결선 — 누적 흐름 (recessive) */}
                            {c.i > 0 && !c.isTotal && (
                                <line x1={colW * (c.i - 0.5) + barW / 2} x2={x} y1={yAt(c.from)} y2={yAt(c.from)}
                                    stroke={C.line} strokeWidth={1} strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />
                            )}
                            <rect x={x} y={c.top} width={barW} height={h} rx={2} fill={col}
                                opacity={hov >= 0 && hov !== c.i ? 0.35 : 1}
                                onMouseEnter={() => setHov(c.i)} onMouseLeave={() => setHov(-1)}
                                style={{ cursor: "pointer", transition: "opacity 0.12s" }} />
                        </g>
                    )
                })}
            </svg>
            {/* 라벨 + 값 — 직접 라벨(4개뿐이라 전부 표기 가능). 텍스트는 ink 토큰, 값만 등락색 */}
            <div style={{ display: "flex", marginTop: 6 }}>
                {cells.map((c) => (
                    <div key={c.i} style={{ flex: 1, textAlign: "center", minWidth: 0 }}>
                        <div style={{ fontSize: 10.5, fontWeight: 700, color: c.isTotal ? C.ink : C.faint, whiteSpace: "nowrap" }}>{c.label}</div>
                        <div style={{ fontSize: narrow ? 11 : 12, fontWeight: 800, color: c.isTotal ? C.ink : (c.v >= 0 ? C.up : C.down), fontVariantNumeric: "tabular-nums" }}>
                            {(c.v >= 0 ? "+" : "−") + fmtKRWcompact(Math.abs(c.v))}
                        </div>
                    </div>
                ))}
            </div>
            {hov >= 0 && cells[hov] && (
                <div style={{ marginTop: 8, background: C.tipBg, color: C.tipFg, borderRadius: 10, padding: "8px 11px", fontSize: 12, fontWeight: 600, lineHeight: 1.5 }}>
                    <b>{cells[hov].label}</b> · {cells[hov].note}
                </div>
            )}
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>
                DART 현금흐름표 실값을 순서대로 누적 · 순증감 = 영업+투자+재무 (더하기만, 자체 산식 0) · 점수·추천 아님
            </div>
        </div>
    )
}

/* 동종업계 백분위 스트립 (2026-07-12) — 이 종목이 같은 섹터 분포 안에서 어디쯤인가.
   데이터의 일 = 단일 값의 '분포 내 위치' → 0~100 트랙 위의 점 (막대 아님. 크기가 아니라 위치가 정보).
   기존엔 탭해야 나오는 6px 마커라 사실상 안 보였음 → 항상 노출.
   🚨 색: 이 차트엔 등락 파랑이 없으므로 보라(C.vt) 마크 사용 가능 (보라↔파랑 deutan ΔE 6.6 충돌 회피 규칙 정합).
   RULE 7 = 위치는 사실. 높다·낮다가 좋다·나쁘다 아님 — 좋음/나쁨 색(빨강·초록) 절대 사용 안 함. */
function PeerStrip({ pct, C }: { pct: number; C: any }) {
    const p = Math.max(0, Math.min(100, Number(pct)))
    const TRACK = 7, DOT = 9   // 마커 ≥8px (dataviz 마크 스펙)
    return (
        <div style={{ position: "relative", height: DOT + 2, marginTop: 7, marginBottom: 2 }}>
            {/* 트랙 — recessive */}
            <div style={{ position: "absolute", left: 0, right: 0, top: (DOT + 2 - TRACK) / 2, height: TRACK, borderRadius: TRACK / 2, background: C.bg }} />
            {/* 업종 중앙값 = 정의상 50번째 백분위 — 기준 눈금 */}
            <div style={{ position: "absolute", left: "50%", top: 0, width: 1.5, height: DOT + 2, marginLeft: -0.75, borderRadius: 1, background: C.line }} />
            {/* 이 종목 — 표면 링 2px (겹침 대비, 마크 스펙) */}
            <div style={{
                position: "absolute", left: `${p}%`, top: 1, width: DOT, height: DOT, marginLeft: -DOT / 2,
                borderRadius: "50%", background: C.vt, boxShadow: `0 0 0 2px ${C.card}`,
            }} />
        </div>
    )
}

function readBodyDark(): boolean {
    // 기본 = 라이트(사이트 첫 시작 라이트 결정, 2026-07-19). 명시적 'dark' 신호가 있을 때만 다크.
    //   판독 순서 = html[data-an-theme](Custom Code 헤드/보디 스크립트가 페인트 전 세팅, 레이스 제거)
    //   → body[data-framer-theme](토글) → localStorage. OS 설정은 안 봄(로드마다 뒤집힘 방지).
    //   ⚠ useState init 은 false(SSG 라이트와 동일) → 이 함수는 effect 에서만 실제 테마 교정에 사용.
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

export default function PublicStockReport(props: Props) {
    const { stockUrl, usStockUrl, usSmallcapUrl, flowUrl, forensicsUrl, insiderUrl, warnUrl, lendingUrl, supplyUrl, apiBase, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!dark : false))
    const C = (RenderTarget.current() === RenderTarget.canvas ? !!dark : themeDark) ? DARK : LIGHT
    useEffect(() => {
        if (RenderTarget.current() === RenderTarget.canvas) return
        const readTheme = () => setThemeDark(readBodyDark())
        readTheme()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(readTheme)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [])
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [list, setList] = useState<any[]>(onCanvas ? SAMPLE : [])   // 리포트 DATA(캔버스=SAMPLE 미리보기, 라이브=빈 값 → 슬라이스 로드 전 스켈레톤, SAMPLE flash 차단)
    const [reportAsOf, setReportAsOf] = useState<string>("")   // stock_report_public _meta.generated_at — 신선도 사실 노출
    const [tocSecs, setTocSecs] = useState<string[]>([])       // 미니 목차 — 렌더된 섹션 헤더(data-sec) DOM 스캔 결과
    // 캔버스만 SAMPLE(에디터 미리보기). 라이브는 빈 값 → 슬라이스 로드 전까지 스켈레톤 노출.
    // 콜드 랜딩 시 selTicker=005930(SAMPLE[0]) + list=SAMPLE 라 sliceReady 즉시 true → SAMPLE 삼성전자 리포트가
    // 찰나 렌더(초록 자기주식취득·내부자 순매수 배지 포함)되던 flash 차단. 라이브는 SAMPLE 절대 미노출.
    const [searchList, setSearchList] = useState<any[]>(onCanvas ? SAMPLE : []) // 검색 universe(전 종목 KR+US, ticker/name)
    const [flowMap, setFlowMap] = useState<Record<string, any[]>>(onCanvas ? SAMPLE_FLOW : {})
    const [forensicsMap, setForensicsMap] = useState<Record<string, any>>(onCanvas ? SAMPLE_FORENSICS : {})
    const [insiderMap, setInsiderMap] = useState<Record<string, any>>(onCanvas ? SAMPLE_INSIDER : {})
    const [warnMap, setWarnMap] = useState<Record<string, any>>(onCanvas ? SAMPLE_WARN : {})
    const [lendingMap, setLendingMap] = useState<Record<string, any>>({})
    const [lendAsOf, setLendAsOf] = useState<string>("")
    const [supplyMap, setSupplyMap] = useState<Record<string, any>>({})
    const [empMap, setEmpMap] = useState<Record<string, any>>({})
    const [crossMed, setCrossMed] = useState<{ KR: Record<string, any>; US: Record<string, any> }>({ KR: {}, US: {} })
    const [selTicker, setSelTicker] = useState<string>(() => {
        if (typeof window !== "undefined") {
            try {
                const qp = (new URLSearchParams(window.location.search).get("q") || "").trim()
                if (qp) { try { window.localStorage.setItem("verity_last_ticker", qp.toUpperCase()) } catch (e) {} ; return qp.toUpperCase() }
                const ls = (window.localStorage.getItem("verity_last_ticker") || "").trim()
                if (ls) return ls.toUpperCase()
            } catch (e) {}
        }
        return SAMPLE[0].ticker
    })
    const [listLoaded, setListLoaded] = useState<boolean>(false)
    const [skelVisible, setSkelVisible] = useState<boolean>(false)
    const [usForen, setUsForen] = useState<any>(null)   // 美 forensics (per-ticker 엔드포인트 집계)
    const [query, setQuery] = useState("")
    const [focused, setFocused] = useState(false)
    const [recents, setRecents] = useState<any[]>([])
    const [openTip, setOpenTip] = useState<string>("")
    const [tipBox, setTipBox] = useState<{ left: number; width: number }>({ left: 0, width: 240 })
    const [hoverCapable, setHoverCapable] = useState(true)
    const [openDisc, setOpenDisc] = useState<number>(-1)
    const [openMetric, setOpenMetric] = useState<string>("")
    const [openFlow, setOpenFlow] = useState<number>(-1)
    const [openPeer, setOpenPeer] = useState<number>(-1)
    const [openFin, setOpenFin] = useState<boolean>(false)
    // 병합 '재무 추이' 탭 (2026-07-10 PM — 연간 손익 vs 분기 건전성, 두 추이 섹션 이름 혼동 해소)
    const [trendTab, setTrendTab] = useState<"annual" | "q">("annual")
    const [qtN, setQtN] = useState<number>(0)   // 분기 추이 로드된 분기 수 (≥4 = 탭 노출)
    const [forenAll, setForenAll] = useState(false)
    const [insiderAll, setInsiderAll] = useState(false)
    const [watchToken, setWatchToken] = useState("")
    const [watchGroupId, setWatchGroupId] = useState<string>("")
    const [starItemId, setStarItemId] = useState<any>(null)
    const [starBusy, setStarBusy] = useState(false)
    const [starHint, setStarHint] = useState(false)

    useEffect(() => {
        if (typeof window === "undefined" || !window.matchMedia) return
        try { setHoverCapable(window.matchMedia("(hover: hover) and (pointer: fine)").matches) } catch { /* keep default */ }
    }, [])

    /* 콜드 랜딩 디폴트 = 그날 거래대금 1위 (2026-07-09) — ?q·최근본 이력 둘 다 없을 때만.
       명시 쿼리/최근 종목이 있으면 유지(연속성). hot_stock.json = 금융위 공공데이터(거래대금, 청정·EOD 사실). */
    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        try {
            const qp = (new URLSearchParams(window.location.search).get("q") || "").trim()
            const ls = (window.localStorage.getItem("verity_last_ticker") || "").trim()
            if (qp || ls) return
        } catch (e) { return }
        let alive = true
        fetch("https://rte5guenhonw9fzn.public.blob.vercel-storage.com/hot_stock.json")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
            const t = d && d.hot && d.hot.ticker
            if (!alive || !t) return
            const tk = String(t).toUpperCase()
            setSelTicker(tk)
            // 콜드 디폴트도 형제·타 페이지 전파 — verity_last_ticker + ?q + 이벤트 (차트·요약·PDF·결정 연동, 2026-07-18)
            try { window.localStorage.setItem("verity_last_ticker", tk) } catch (e) {}
            try { const pr = new URLSearchParams(window.location.search); pr.set("q", tk); window.history.replaceState(null, "", window.location.pathname + "?" + pr.toString() + window.location.hash) } catch (e) {}
            try { window.dispatchEvent(new CustomEvent("verity-ticker-change")) } catch (e) {}
        })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    useEffect(() => {
        if (typeof document === "undefined") return
        const close = () => setOpenTip("")
        document.addEventListener("click", close)
        return () => document.removeEventListener("click", close)
    }, [])

    // 종목 타입 — ETF/ETN 은 기업 리포트 대신 ETF 구성(자금흐름·NAV·괴리율) 렌더 (2026-07-10 PM).
    const kind = useMemo(() => {
        const u = searchList.find((x: any) => String(x.ticker) === String(selTicker))
        const mk = String((u && u.market) || "").toUpperCase()
        if (mk === "ETF" || mk === "ETN") return "etf"
        if (mk === "지수") return "index"   // KR 지수(코스피/코스닥/200 등) — 지수 뷰 렌더
        return "stock"
    }, [searchList, selTicker])
    const [etfDoc, setEtfDoc] = useState<any>(null)
    const [noReportTk, setNoReportTk] = useState<string>("")   // 슬라이스 확정 미보유 티커
    const lastGoodRef = useRef<any>(null)                       // 전환 중 이전 화면 유지 (깜빡임 제거)
    // 형제 컴포넌트(기업 전용: 뉴스 외 상세·이벤트·증권사리포트·브리핑)가 타입을 알 수 있게 body 신호 발행
    useEffect(() => {
        if (onCanvas || typeof document === "undefined" || !document.body) return
        document.body.dataset.verityAssetKind = kind
    }, [kind, onCanvas])
    const isUsEtf = kind === "etf" && !/^[0-9]{6}$/.test(String(selTicker))
    useEffect(() => {
        if (onCanvas || (kind !== "etf" && kind !== "index")) return
        let alive = true
        const url = kind === "index" ? KR_INDEX_URL : (isUsEtf ? US_ETF_URL : ETF_FLOW_URL)  // 지수 / US·KR ETF
        fetch(url)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive && d) setEtfDoc(d) })
            .catch(() => {})
        return () => { alive = false }
    }, [kind, isUsEtf, onCanvas])

    // 종목 상세 = 슬라이스 API 1콜(~11KB) — 전 종목 맵 로드(≈16MB) 대체 (로딩 극단 경량화 2026-07-08).
    //   report + flow/forensics/insider/warn/lending/supply/employment 를 한 번에 슬라이스 반환.
    //   검색 목록(searchList)은 universe_search.json 로 별도(경량) — 아래 effect. 상세는 선택 종목만.
    useEffect(() => {
        if (onCanvas) return
        if (kind === "etf" || kind === "index") { setListLoaded(true); return }
        const t = String(selTicker || "").trim().toUpperCase()
        if (!t) return
        let alive = true
        fetch(base + "/api/stock_slice?ticker=" + encodeURIComponent(t))
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                if (!d || d.status !== "ok") { setListLoaded(true); return }
                const rep = d.report
                if (rep && rep.ticker) { setList([rep]); setNoReportTk("") }
                else { setList([]); setNoReportTk(t) }   // 확정 미보유만 stub (전환 중 깜빡임 방지)
                if (d.report_as_of) setReportAsOf(String(d.report_as_of))
                // 항상 반영 (null 포함) — 슬라이스 성공 = 그 종목의 확정 답. null 을 skip 하면
                // SAMPLE placeholder 가 안 지워져 데모 라벨이 실 화면에 잔존 (2026-07-10 삼성전자
                // 가짜 '단기과열' 경보 사고 — 데모 키가 005930 이라 정확히 삼성전자에서 발현).
                const merge = (setter: any, sec: any) => setter((prev: any) => ({ ...prev, [t]: sec != null ? sec : null }))
                setFlowMap((p: any) => ({ ...p, [t]: d.flow != null ? d.flow : null }))
                merge(setForensicsMap, d.forensics)
                merge(setInsiderMap, d.insider)
                merge(setWarnMap, d.warn)
                merge(setLendingMap, d.lending); if (d.lend_as_of) setLendAsOf(String(d.lend_as_of))
                merge(setSupplyMap, d.supply)
                merge(setEmpMap, d.employment)
                setListLoaded(true)
            })
            .catch(() => { if (alive) setListLoaded(true) })
        return () => { alive = false }
    }, [selTicker, base, onCanvas, kind])

    // ?q= 가 종목명(비 티커)일 때 → 티커로 해석. 검색 universe 로드 후 1회 (딥링크 보존).
    useEffect(() => {
        if (onCanvas || !searchList.length) return
        const t = String(selTicker || "").trim()
        if (!t || searchList.some((x: any) => String(x.ticker).toUpperCase() === t.toUpperCase())) return
        const low = t.toLowerCase()
        const hit = searchList.find((x: any) => String(x.name || "").toLowerCase() === low || String(x.name_ko || "") === t)
            || searchList.find((x: any) => String(x.name || "").toLowerCase().includes(low) || String(x.name_ko || "").includes(t))
        if (hit) setSelTicker(String(hit.ticker).toUpperCase())
    }, [searchList, selTicker, onCanvas])

    /* 검색 universe 로드 — 통합 universe_search.json(전 종목 KR+US). 리포트 DATA(list)와 별개. */
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(UNIVERSE_URL).then((r) => (r.ok ? r.json() : null))
            .then((d) => { const a = d && (Array.isArray(d) ? d : d.stocks); if (alive && Array.isArray(a) && a.length) setSearchList(a) })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas])

    /* KR↔US 교차피어 (Tier B B-5) — 반대 시장 GICS 섹터 중앙값 테이블(전역·소형). 1회 로드. */
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        Promise.all([
            fetch(CROSS_KR_URL).then((r) => (r.ok ? r.json() : null)).catch(() => null),
            fetch(CROSS_US_URL).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        ]).then(([kr, us]: any[]) => {
            if (!alive) return
            setCrossMed({ KR: (kr && kr.medians) || {}, US: (us && us.medians) || {} })
        })
        return () => { alive = false }
    }, [onCanvas])

    // (flow·대차·수급·고용·포렌식·내부자·경보 전 종목 맵 fetch 는 슬라이스 API 로 통합 — 위 effect 참조.
    //  종목별 ~11KB 슬라이스로 대체해 페이지당 ≈16MB 다운로드 제거. 2026-07-08.)

    // 美 forensics — 종목이 US(비 6자리 ticker)일 때 per-ticker 엔드포인트 집계
    // (Form4 내부자 · 13D/G 대량보유 · 13F 스마트머니 · 컨센서스). KR 은 skip.
    useEffect(() => {
        if (onCanvas) return
        const t = String(selTicker || "").toUpperCase()
        if (!t || /^[0-9]{6}$/.test(t)) { setUsForen(null); return }
        let alive = true
        fetch(base + "/api/verity/us-forensics?ticker=" + encodeURIComponent(t), { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive) setUsForen(d && d.status === "ok" ? (d.sections || null) : null) })
            .catch(() => {})
        return () => { alive = false }
    }, [selTicker, base, onCanvas])

    const s = useMemo(() => {
        const hit = list.find((x) => x.ticker === selTicker)
        if (hit) { lastGoodRef.current = hit; return hit }
        // 확정 미보유(슬라이스 응답 완료) = stub 안내. 응답 대기 중엔 이전 종목 화면 유지(깜빡임 제거 2026-07-10).
        if (String(noReportTk) === String(selTicker)) {
            const u = searchList.find((x) => String(x.ticker) === String(selTicker))
            if (u) return { ticker: u.ticker, name: u.name, market: u.market, _noReport: true }
        }
        if (lastGoodRef.current && String(lastGoodRef.current.ticker) === String(selTicker)) return lastGoodRef.current
        const u2 = searchList.find((x) => String(x.ticker) === String(selTicker))
        if (u2) return { ticker: u2.ticker, name: u2.name, market: u2.market, _noReport: true }
        return list[0] || {}
    }, [list, searchList, selTicker, noReportTk])
    // 로딩 중(실데이터 미도착 or 선택 종목 미발견)엔 삼성전자 샘플 폴백 대신 스켈레톤. 160ms 지연 게이트=즉시 로드 깜빡임 차단(토스식).
    // 스켈레톤 = 현재 선택 종목의 슬라이스가 아직 도착 안 함(전환 중 포함). 2026-07-11 수리:
    //   옛 로직(!lastGoodRef.current)은 종목 전환 시 이전 종목(네이버 등)을 계속 노출 → 잘못된 종목 깜빡임.
    //   list=현재 종목 슬라이스만 보유(누적 X)이므로 selTicker 미포함 = 로딩 중 = 스켈레톤. 160ms 게이트로 빠른 로드는 무깜빡.
    const sliceReady = list.some((x: any) => String(x.ticker) === String(selTicker)) || String(noReportTk) === String(selTicker)
    const showSkeleton = !onCanvas && !sliceReady
    useEffect(() => {
        if (!showSkeleton) { setSkelVisible(false); return }
        const t = setTimeout(() => setSkelVisible(true), 160)
        return () => clearTimeout(t)
    }, [showSkeleton])

    useEffect(() => { setOpenDisc(-1); setOpenMetric(""); setOpenFlow(-1); setOpenPeer(-1); setOpenFin(false); setForenAll(false); setInsiderAll(false); setOpenTip("") }, [selTicker])

    // 관심종목(별표) — 세션 토큰 추적 + 현재 종목 별표 상태 조회
    useEffect(() => {
        if (onCanvas) return
        const sync = () => setWatchToken(loadWatchToken())
        sync()
        window.addEventListener(AUTH_EVENT, sync)
        window.addEventListener("storage", sync)
        return () => { window.removeEventListener(AUTH_EVENT, sync); window.removeEventListener("storage", sync) }
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas || !watchToken || !s.ticker) { setStarItemId(null); return }
        let alive = true
        fetch(base + "/api/watchgroups", { headers: { Authorization: `Bearer ${watchToken}` }, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((groups) => {
                if (!alive || !Array.isArray(groups)) return
                if (groups.length && groups[0] && groups[0].id) setWatchGroupId(String(groups[0].id))
                let found: any = null
                for (const g of groups) {
                    for (const it of (g.items || [])) {
                        if (String(it.ticker || "").trim() === String(s.ticker)) { found = it; break }
                    }
                    if (found) break
                }
                setStarItemId(found ? found.id : null)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [watchToken, s.ticker, base, onCanvas])

    const narrow = w > 0 && w < 560
    const pad = narrow ? 12 : 18

    /* 종목 선택 = in-page 전환 + 최근 본 종목 누적(nav 검색과 공유 키). */
    const goTicker = (tk: any, nm?: any) => {
        const t = String(tk)
        setSelTicker(t)
        try {
            window.localStorage.setItem("verity_last_ticker", t)
            const name = nm || (list.find((x: any) => String(x.ticker) === t) || {}).name || t
            const cur = readRecents().filter((x: any) => String(x.t) !== t)
            cur.unshift({ t, n: name })
            window.localStorage.setItem(RECENTS_KEY, JSON.stringify(cur.slice(0, 8)))
            window.history.replaceState(null, "", window.location.pathname + "?q=" + encodeURIComponent(t) + window.location.hash)
            window.dispatchEvent(new Event("verity-ticker-change"))  // 같은 페이지 LiveChart/ThesisNote/DecisionPanel 종목 추종
        } catch (e) {}
        setQuery(""); setFocused(false)
    }

    const matches = useMemo(() => {
        const q = query.trim().toLowerCase()
        if (!q) return []
        const rk = (x: any) => {
            const t = String(x.ticker || "").toLowerCase(), n = String(x.name || "").toLowerCase(), k = String(x.name_ko || "").toLowerCase()
            return t === q ? 0 : (n === q || k === q) ? 1 : t.indexOf(q) === 0 ? 2 : (n.indexOf(q) === 0 || (k && k.indexOf(q) === 0)) ? 3 : 4
        }
        return searchList.filter((x) => String(x.name || "").toLowerCase().includes(q) || String(x.ticker || "").toLowerCase().includes(q) || String(x.name_ko || "").includes(q) || String(x.kw || "").toLowerCase().includes(q)).sort((a: any, b: any) => rk(a) - rk(b)).slice(0, 15)
    }, [query, searchList])

    const facts = s.facts || {}
    const fnote = s.facts_note || {}
    const factsCalc = s.facts_calc || {}
    const header = s.header || null
    const overview = s.overview || null
    const realEstate = s.real_estate || null
    const peer = s.peer || null
    const financials = s.financials
    const finGroups = (financials && Array.isArray(financials.groups)) ? financials.groups : []
    const disclosures = s.disclosures || []
    const consensus = s.consensus || {}
    const verityLens = s.verity_lens || null
    const ownership = s.ownership || {}
    const calendar = s.calendar || []
    const flowRows = useMemo(() => (flowMap && flowMap[s.ticker]) || [], [flowMap, s.ticker])
    const flowMax = useMemo(() => {
        let mx = 1
        for (const r of flowRows) mx = Math.max(mx, Math.abs(Number(r.foreign_net) || 0), Math.abs(Number(r.inst_net) || 0))
        return mx
    }, [flowRows])
    const lendingRow = useMemo(() => (lendingMap && lendingMap[s.ticker]) || null, [lendingMap, s.ticker])
    const supplyRow = useMemo(() => (supplyMap && supplyMap[s.ticker]) || null, [supplyMap, s.ticker])
    const empRow = useMemo(() => (empMap && empMap[s.ticker]) || null, [empMap, s.ticker])
    const foren = useMemo(() => (forensicsMap && forensicsMap[s.ticker]) || null, [forensicsMap, s.ticker])
    const insider = useMemo(() => (insiderMap && insiderMap[s.ticker]) || null, [insiderMap, s.ticker])
    const warn = useMemo(() => (warnMap && warnMap[s.ticker]) || null, [warnMap, s.ticker])
    const warnLabels = (warn && Array.isArray(warn.labels)) ? warn.labels : []
    const warnTop = warnLabels.some((l: any) => l.severity === "danger") ? "danger" : warnLabels.some((l: any) => l.severity === "warn") ? "warn" : warnLabels.length ? "caution" : null

    const synth = useMemo(() => {
        const f: string[] = []
        if (s.business) f.push(String(s.business))
        if (facts.PER) f.push("PER " + facts.PER)
        if (facts.ROE) f.push("ROE " + facts.ROE)
        if (facts["부채비율"]) f.push("부채비율 " + facts["부채비율"])
        if (facts["Altman-Z"]) f.push("Altman-Z " + facts["Altman-Z"] + (fnote["Altman-Z"] ? "(" + fnote["Altman-Z"] + ")" : ""))
        if (financials && financials.values && financials.values["매출"]) f.push("매출 " + financials.values["매출"])
        if (disclosures.length) f.push("최근 공시 " + disclosures.length + "건")
        if (insider && insider.total) f.push("내부자 거래 " + insider.total + "건")
        if (ownership && ownership.family_pct != null) f.push("총수일가 " + ownership.family_pct + "%")
        return f
    }, [s, facts, fnote, financials, disclosures, insider, ownership, consensus])

    const toggleStar = async () => {
        if (starBusy) return
        if (!watchToken) { setStarHint(true); setTimeout(() => setStarHint(false), 2600); return }
        setStarBusy(true)
        try {
            if (starItemId) {
                setStarItemId(null)
                await fetch(base + "/api/watchgroups", {
                    method: "DELETE",
                    headers: { Authorization: `Bearer ${watchToken}`, "Content-Type": "application/json" },
                    body: JSON.stringify({ action: "remove_item", item_id: starItemId }),
                })
            } else {
                let gid = watchGroupId
                if (!gid) {
                    const cr = await fetch(base + "/api/watchgroups", {
                        method: "POST",
                        headers: { Authorization: `Bearer ${watchToken}`, "Content-Type": "application/json" },
                        body: JSON.stringify({ name: "관심종목" }),
                    }).then((r) => (r.ok ? r.json() : null)).catch(() => null)
                    gid = cr && cr.id ? String(cr.id) : ""
                    if (gid) setWatchGroupId(gid)
                }
                if (!gid) { setStarBusy(false); return }
                const added = await fetch(base + "/api/watchgroups", {
                    method: "POST",
                    headers: { Authorization: `Bearer ${watchToken}`, "Content-Type": "application/json" },
                    body: JSON.stringify({ action: "add_item", group_id: gid, ticker: s.ticker, name: s.name, market: s.market }),
                }).then((r) => (r.ok ? r.json() : null)).catch(() => null)
                setStarItemId(added && added.id ? added.id : "pending")
            }
            if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(WATCH_EVENT))
        } catch { /* no-op */ }
        setStarBusy(false)
    }

    const openTipAt = (e: any, id: string) => {
        try {
            const root = rootRef.current?.getBoundingClientRect()
            const icon = e?.currentTarget?.getBoundingClientRect?.()
            if (root && icon && root.width > 0) {
                const M = 8
                const width = Math.min(240, Math.max(170, root.width - M * 2))
                const iconLeftC = icon.left - root.left
                const clampedLeftC = Math.max(M, Math.min(iconLeftC, root.width - width - M))
                setTipBox({ left: Math.round(clampedLeftC - iconLeftC), width })
            }
        } catch { /* ignore */ }
        setOpenTip(id)
    }
    const tipStyle = (): CSSProperties => ({
        position: "absolute", top: "calc(100% + 5px)", left: tipBox.left, zIndex: 50, display: "block",
        width: tipBox.width, background: C.tipBg, color: C.tipFg, borderRadius: 12,
        padding: "11px 13px", fontSize: 12.5, fontWeight: 500, lineHeight: 1.55,
        boxShadow: "0 6px 20px rgba(0,0,0,0.18)", whiteSpace: "normal", textAlign: "left",
    })

    const Info = ({ k }: { k: string }) => {
        if (!INFO[k]) return null
        const id = "i:" + k
        const isOpen = openTip === id
        const hov = hoverCapable ? { onMouseEnter: (e: any) => openTipAt(e, id), onMouseLeave: () => setOpenTip("") } : {}
        return (
            <span style={{ position: "relative", display: "inline-block" }}>
                <span role="button" tabIndex={0}
                    onClick={(e) => { e.stopPropagation(); if (isOpen) setOpenTip(""); else openTipAt(e, id) }}
                    {...hov}
                    style={{
                        display: "inline-flex", alignItems: "center", justifyContent: "center",
                        width: "1.42em", height: "1.42em", marginLeft: "0.4em", borderRadius: "50%",
                        background: "#6c5ce7", color: "#fff", fontSize: "0.62em", fontWeight: 700,
                        lineHeight: 1, verticalAlign: "middle", position: "relative", top: "-0.1em", cursor: "help",
                    }}>i</span>
                {isOpen && (
                    <span onClick={(e) => e.stopPropagation()} style={tipStyle()}>
                        <span style={{ fontWeight: 700, display: "block", marginBottom: 3, color: C.vg }}>{k}</span>
                        {INFO[k]}
                    </span>
                )}
            </span>
        )
    }

    const renderTitle = (text: string, idKey: string) => {
        const parts: any[] = []
        let rest = text, guard = 0
        while (rest.length && guard < 40) {
            guard++
            let hitIdx = -1, hitKey = ""
            for (const k of GKEYS) {
                const i2 = rest.indexOf(k)
                if (i2 >= 0 && (hitIdx === -1 || i2 < hitIdx)) { hitIdx = i2; hitKey = k }
            }
            if (hitIdx === -1) { parts.push(rest); break }
            if (hitIdx > 0) parts.push(rest.slice(0, hitIdx))
            const tipId = idKey + ":" + parts.length
            const isOpen = openTip === tipId
            const hov = hoverCapable ? { onMouseEnter: (e: any) => openTipAt(e, tipId), onMouseLeave: () => setOpenTip("") } : {}
            parts.push(
                <span key={tipId} style={{ position: "relative", display: "inline" }}>
                    <span role="button" tabIndex={0}
                        onClick={(e) => { e.stopPropagation(); if (isOpen) setOpenTip(""); else openTipAt(e, tipId) }}
                        {...hov}
                        style={{ borderBottom: `1px dashed ${C.vt}`, cursor: "help" }}>{hitKey}</span>
                    {isOpen && (
                        <span onClick={(e) => e.stopPropagation()} style={tipStyle()}>
                            <span style={{ fontWeight: 700, display: "block", marginBottom: 3, color: C.vg }}>{hitKey}</span>
                            {GLOSSARY[hitKey]}
                        </span>
                    )}
                </span>
            )
            rest = rest.slice(hitIdx + hitKey.length)
        }
        return <>{parts}</>
    }

    // 미니 목차 — 실제 렌더된 섹션(data-sec)만 스캔 (섹션별 빈 데이터 가드 자동 반영). 렌더마다 재스캔, 변화 시에만 set.
    useEffect(() => {
        const el = rootRef.current
        if (!el) return
        const secs = Array.from(el.querySelectorAll("[data-sec]")).map((n) => n.getAttribute("data-sec") || "").filter(Boolean)
        const key = secs.join("|")
        setTocSecs((prev) => (prev.join("|") === key ? prev : secs))
    })

    const sectionTitle = (t: string, sub?: string, infoKey?: string) => (
        <div data-sec={t} style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "18px 2px 8px", scrollMarginTop: 70 }}>
            <span style={{ fontFamily: HEAD, fontSize: 14, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px", display: "inline-flex", alignItems: "center" }}>{t}{infoKey ? <Info k={infoKey} /> : null}</span>
            {sub && <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{sub}</span>}
        </div>
    )
    const metaItem = (label: string, value: string, withInfo?: boolean, color?: string) => (
        <span style={{ fontSize: 11.5, fontWeight: 600, display: "inline-flex", alignItems: "center" }}>
            <span style={{ color: C.faint }}>{label} </span>
            <span style={{ color: color || C.ink, fontWeight: 700, marginLeft: 3 }}>{value}</span>
            {withInfo ? <Info k={label} /> : null}
        </span>
    )
    const kvRow = (k: string, v: any, i: number) => (
        <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "9px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}`, fontSize: 13 }}>
            <span style={{ color: C.sub, fontWeight: 600 }}>{k}</span>
            <span style={{ fontWeight: 700 }}>{v}</span>
        </div>
    )
    const sevC = (sev: string) => sev === "danger" ? { fg: C.up, bg: C.upS } : sev === "warn" ? { fg: C.amber, bg: C.amberS } : { fg: C.sub, bg: C.bg }
    const tipKV = (label: string, value: any, color?: string) => (
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, padding: "3px 0" }}>
            <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{label}</span>
            <span style={{ fontSize: 12, color: color || C.ink, fontWeight: 800 }}>{value}</span>
        </div>
    )

    // 검색 필드 — 공시 페이지(PublicDisclosureFeed)와 동일 토스식 borderless 채움 (테두리 X, 돋보기 아이콘 + 클리어 ×)
    const inputStyle: CSSProperties = {
        width: "100%", boxSizing: "border-box", border: "none",
        background: C.card, color: C.ink, borderRadius: 12,
        padding: "12px 34px 12px 38px", fontSize: 13.5, fontFamily: FONT, outline: "none",
        WebkitAppearance: "none",
    }
    const wrap: CSSProperties = {
        width: "100%", height: "100%", maxHeight: "100%", overflowY: "auto", overflowX: "hidden",
        background: C.bg, fontFamily: FONT, padding: pad, boxSizing: "border-box", color: C.ink,
    }

    const flowBar = (v: any, label: string) => {
        const x = Number(v) || 0
        const pos = x >= 0
        const wpct = Math.min(100, (Math.abs(x) / flowMax) * 100)
        return (
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 700, marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: 12.5, fontWeight: 800, color: pos ? C.up : C.down }}>{fmtMan(x)}</div>
                <div style={{ height: 4, borderRadius: 2, background: C.line, marginTop: 3, overflow: "hidden" }}>
                    <div style={{ width: wpct + "%", height: "100%", background: pos ? C.up : C.down }} />
                </div>
            </div>
        )
    }

    const catColor = (cat: string) => DILUTION_CATS.has(cat) ? C.amber : RISK_CATS.has(cat) ? C.up : FAVORABLE_CATS.has(cat) ? C.green : cat === "정정공시" ? C.faint : C.sub
    const shTypeColor = (t: string) => (t === "동일인" || t === "친족") ? C.vt : t === "소속회사" ? C.down : (t === "자기주식" || t === "기타") ? C.faint : C.sub
    const finValColor = (v: any) => (typeof v === "string" && v.trim().charAt(0) === "−") ? C.down : C.ink

    // 토스풍 경보 — 심각도별 부드러운 틴트 배경만(외곽선 없음). 경보 시 헤더 통째 감쌈.
    const warnTint = warnTop === "danger" ? C.upS : warnTop === "warn" ? C.amberS : C.card
    const warnAccent = warnTop === "danger" ? C.up : warnTop === "warn" ? C.amber : C.sub
    const headerBox: CSSProperties = warnTop
        ? { marginTop: 14, background: warnTint, borderRadius: 18, padding: narrow ? "13px 14px" : "15px 17px" }
        : { marginTop: 14, paddingLeft: narrow ? 14 : 17 }

    // 🔎 채권·금리 검색 진입(RATES_*) = 종목 리포트가 아니라 PublicBondRegime(searchMode)이 표시.
    //   이 컴포넌트는 렌더 양보(null) — 같은 /stock 페이지에서 채권이면 BondRegime, 종목이면 이 리포트.
    //   (2026-07-08 통합 검색·리포트. 미지 티커 "준비중" stub 이 채권에 뜨는 것 방지.)
    const searchBox = (
        <div style={{ position: "relative" }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={C.faint} strokeWidth="2.4" strokeLinecap="round"
                style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}>
                <circle cx="11" cy="11" r="7" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input style={inputStyle} placeholder={`종목 검색 (이름·코드) · 전 종목 ${searchList.length}개`}
                value={query} onChange={(e) => setQuery(e.target.value)}
                onFocus={() => { setRecents(readRecents()); setFocused(true) }} onBlur={() => setTimeout(() => setFocused(false), 150)} />
            {query && (
                <span role="button" tabIndex={0} onMouseDown={(e) => { e.preventDefault(); setQuery("") }}
                    style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", color: C.faint, fontSize: 15, fontWeight: 700, cursor: "pointer", lineHeight: 1 }}>×</span>
            )}
            {focused && (query.trim() ? matches.length > 0 : true) && (
                <div style={{
                    position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 60,
                    background: C.card, borderRadius: 12, boxShadow: "0 10px 30px rgba(0,0,0,0.14)",
                    padding: 6, maxHeight: 340, overflowY: "auto",
                }}>
                    {query.trim() ? (
                        matches.map((m) => (
                            /* 한글명 = 주 이름(있으면), 메타 = 티커·시장만 — 긴 한글 메타가 주 이름을
                               뭉개던 레이아웃 fix (2026-07-11 'The…/S' 스크린샷). 주 이름 flex+ellipsis. */
                            <div key={m.ticker} onMouseDown={() => goTicker(m.ticker, m.name_ko || m.name)}
                                style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 9, cursor: "pointer" }}>
                                <Logo ticker={m.ticker} name={m.name_ko || m.name} market={m.market} C={C} size={28} />
                                <span style={{ fontFamily: HEAD, fontSize: 13.5, fontWeight: 700, color: C.ink, flex: "1 1 auto", minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m.name_ko || m.name}</span>
                                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginLeft: "auto", flexShrink: 0 }}>{m.ticker} · {m.market}</span>
                            </div>
                        ))
                    ) : (
                        <>
                            {recents.length > 0 && (
                                <>
                                    <div style={{ fontSize: 11, fontWeight: 800, color: C.faint, padding: "8px 10px 4px" }}>최근 본 종목</div>
                                    {recents.slice(0, 6).map((r: any) => (
                                        <div key={"r:" + r.t} onMouseDown={() => goTicker(r.t, r.n)}
                                            style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 9, cursor: "pointer" }}>
                                            <Logo ticker={r.t} name={r.n} market={/^\d{6}$/.test(String(r.t)) ? "KOSPI" : "US"} C={C} size={28} />
                                            <span style={{ fontFamily: HEAD, fontSize: 13.5, fontWeight: 700, color: C.ink, flex: "1 1 auto", minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.n}</span>
                                            <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginLeft: "auto", flexShrink: 0 }}>{r.t}</span>
                                        </div>
                                    ))}
                                </>
                            )}
                            {/* 거래대금 상위 = 네이버 link-out — trending_kr(KRX raw) 재배포 중단(컴플라이언스 2026-07-03) */}
                            <div style={{ display: "flex", alignItems: "baseline", gap: 6, padding: "8px 10px 4px" }}>
                                <span style={{ fontSize: 11, fontWeight: 800, color: C.faint }}>지금 거래 활발</span>
                                <span style={{ fontSize: 10, fontWeight: 500, color: C.faint, opacity: 0.8 }}>거래대금 상위 · 네이버</span>
                            </div>
                            <div onMouseDown={() => { if (typeof window !== "undefined") window.open(window.innerWidth < 720 ? M_NAVER_QUANT : NAVER_QUANT, "_blank", "noopener") }}
                                style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 9, cursor: "pointer" }}>
                                <span style={{ width: 22, height: 22, borderRadius: 7, background: C.vtS, color: C.vt, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 800, flexShrink: 0 }}>↗</span>
                                <span style={{ fontSize: 13, fontWeight: 700, color: C.ink }}>실시간 거래대금 상위</span>
                                <span style={{ marginLeft: "auto", fontSize: 11.5, fontWeight: 700, color: C.faint }}>네이버 금융 ↗</span>
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    )

    if (String(selTicker || "").toUpperCase().startsWith("RATES_")) return null

    // 🧺 ETF/ETN — 기업 리포트 대신 ETF 구성 (자금흐름·NAV·괴리율, etf_flow.json) — 2026-07-10 PM
    if (kind === "etf") {
        const uEnt = searchList.find((x: any) => String(x.ticker) === String(selTicker)) || {}
        return (
            <div ref={rootRef} style={wrap}>
                {searchBox}
                <EtfReportBlock C={C} isDark={C === DARK} narrow={narrow} ticker={String(selTicker)}
                    name={String(uEnt.name || selTicker)} market={String(uEnt.market || "ETF")} doc={etfDoc} onPick={goTicker} />
            </div>
        )
    }

    if (kind === "index") {
        const uEntI = searchList.find((x: any) => String(x.ticker) === String(selTicker)) || {}
        return (
            <div ref={rootRef} style={wrap}>
                {searchBox}
                <IndexReportBlock C={C} narrow={narrow} name={String(uEntI.name || selTicker)} doc={etfDoc} />
            </div>
        )
    }

    if (showSkeleton) {
        return (
            <div ref={rootRef} style={wrap}>
                {skelVisible && <StockReportSkeleton C={C} isDark={C === DARK} narrow={narrow} />}
            </div>
        )
    }

    return (
        <div ref={rootRef} style={wrap}>
            {searchBox}

            {/* 리포트 미보유 종목(검색 universe엔 있으나 정밀 리포트 없음) — graceful 안내. 시세·차트=옆 LiveChart·네이버. */}
            {s._noReport && !onCanvas && (
                <div style={{ background: C.vtS, borderRadius: 12, padding: "11px 14px", marginBottom: 12, fontSize: 12.5, fontWeight: 600, color: C.sub, lineHeight: 1.5 }}>
                    아직 정밀 리포트가 준비되지 않은 종목이에요. 시세·차트는 실시간 차트 위젯과 네이버에서 볼 수 있어요 — 리포트는 순차 확대 중이에요.
                </div>
            )}

            {/* 헤더 (경보 시 종목명까지 감싸는 토스풍 틴트 박스 — 외곽선 없음) */}
            <div style={headerBox}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <Logo ticker={s.ticker} name={s.name} market={s.market} C={C} size={narrow ? 28 : 32} />
                    <span style={{ fontFamily: HEAD, fontSize: 23, fontWeight: 800, letterSpacing: "-0.6px" }}>{s.name}</span>
                    {s.name_ko && <span style={{ fontSize: 13.5, color: C.sub, fontWeight: 700 }}>{s.name_ko}</span>}
                    <span style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>{s.ticker} · {s.market}{reportAsOf ? " · 리포트 " + fmtAge(reportAsOf) + " 갱신" : ""}</span>
                    <button onClick={toggleStar} title={starItemId ? "관심종목 해제" : "관심종목 담기"} disabled={starBusy}
                        aria-label={starItemId ? "관심종목 해제" : "관심종목 담기"}
                        style={{ flexShrink: 0, border: "none", background: "transparent", cursor: starBusy ? "default" : "pointer", lineHeight: 0, padding: "2px 4px", display: "inline-flex", alignItems: "center" }}>
                        <svg width={18} height={18} viewBox="0 0 24 24" fill={starItemId ? "#f6b93b" : C.faint} stroke={starItemId ? "#f6b93b" : C.faint} strokeWidth={2.8} strokeLinejoin="round" strokeLinecap="round" aria-hidden="true">
                            <path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.685 21.5a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.45 10.286a.53.53 0 0 1 .294-.903l5.165-.756a2.122 2.122 0 0 0 1.597-1.16z" />
                        </svg>
                    </button>
                    {starHint && <span style={{ fontSize: 11, color: C.vg, fontWeight: 700 }}>로그인하면 저장돼요</span>}
                    {warnTop && (
                        <span style={{ flexShrink: 0, width: 22, height: 22, borderRadius: 7, background: warnAccent, color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 800, lineHeight: 1 }}>!</span>
                    )}
                    {warnTop && warnLabels.map((l: any, i: number) => (
                        <span key={i} style={{ fontSize: 11, fontWeight: 800, color: sevC(l.severity).fg, background: C.card, borderRadius: 999, padding: "3px 10px" }}>{l.label}</span>
                    ))}
                    {warnTop && <Info k="시장경보" />}
                </div>
                {s.business && <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 600, marginTop: 2 }}>{s.business}</div>}
                {/* 실시간 현재가 폴링(/api/stock KIS·yfinance) 제거 — 네이버 link-out(증권사 서빙 = 재배포 아님). KR 6자리만. */}
                {!onCanvas && naverStockUrl(String(s.ticker || "")) && (
                    <div style={{ marginTop: 7 }}>
                        <a href={naverStockUrl(String(s.ticker || ""))} target="_blank" rel="noopener noreferrer"
                            style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 800, color: C.vt, background: C.vtS, borderRadius: 9, padding: "6px 11px", textDecoration: "none" }}>
                            실시간 시세·호가 · 네이버 ↗
                        </a>
                    </div>
                )}
                {header && (
                    <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 9 }}>
                        {header && header.range_52w && metaItem("52주", header.range_52w)}
                        {header && header.trading_value && metaItem("거래대금", header.trading_value)}
                        {header && header.market_cap && metaItem("시총", header.market_cap)}
                    </div>
                )}
                {warnTop && (
                    <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, marginTop: 11, paddingTop: 10, borderTop: `1px solid ${C.line}`, lineHeight: 1.5 }}>
                        KRX 공식 지정 시장경보 — 자체 판단 아님. 투자 전 거래소 경고 꼭 확인
                    </div>
                )}
            </div>

            {/* 사실 합성 */}
            {synth.length > 1 && (
                <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 12, border: `1px solid ${C.vtS}` }}>
                    <div style={{ fontFamily: HEAD, fontSize: 12, fontWeight: 800, color: C.vg, marginBottom: 8 }}>사실 합성 · 한눈 요약</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {synth.map((f, i) => (
                            <div key={i} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                                <span style={{ flexShrink: 0, color: C.vg, fontSize: 12, fontWeight: 800, lineHeight: 1.45 }}>·</span>
                                <span style={{ fontSize: 13.5, fontWeight: 700, color: C.ink, lineHeight: 1.45, letterSpacing: "-0.2px" }}>{f}</span>
                            </div>
                        ))}
                    </div>
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 10 }}>화면의 사실을 규칙으로 추린 요약 — AI 작문·자체 등급 아님</div>
                </div>
            )}

            {/* 초보 Q&A 요약 (2026-07-16) — 우리 사실을 질문으로 재배치. 결정론·점수 0·중립색·"판단은 직접"(RULE 7). PlainRatio 스캐폴딩 정공법(LLM narrative 아님). */}
            {(() => {
                const rowOf = (k: string) => (peer && peer.rows) ? peer.rows.find((r: any) => r.key === k) : null
                const arr = (vs: string) => vs === "above" ? " ↑" : vs === "below" ? " ↓" : ""
                const cards: any[] = []
                const per = rowOf("PER")
                if (per) cards.push({ q: "지금 싸 보이나?", a: "PER " + per.value, sub: "섹터 중앙값 " + per.median + arr(per.vs) })
                const roe = rowOf("ROE")
                if (roe) cards.push({ q: "돈 잘 버나?", a: "ROE " + roe.value, sub: "섹터 " + roe.median + arr(roe.vs) })
                if (insider && insider.trades && insider.trades.length) {
                    const cutoff = Date.now() - 90 * 86400000
                    const parseD = (x: any) => { const t = new Date(String(x || "")).getTime(); return isFinite(t) ? t : 0 }
                    const recent = insider.trades.filter((t: any) => parseD(t.date) >= cutoff)
                    const buyers = new Set(recent.filter((t: any) => Number(t.change) > 0).map((t: any) => t.person))
                    const sellers = new Set(recent.filter((t: any) => Number(t.change) < 0).map((t: any) => t.person))
                    if (buyers.size || sellers.size) cards.push({ q: "큰손이 사나?", a: "내부자 " + (buyers.size >= sellers.size ? buyers.size + "명 매수" : sellers.size + "명 매도"), sub: "최근 90일 서로 다른 임원" })
                }
                const debt = rowOf("부채비율")
                if (debt || disclosures.length) cards.push({ q: "망가질 유의사항?", a: debt ? "부채비율 " + debt.value : "최근 공시 " + disclosures.length + "건", sub: disclosures.length ? "최근 공시 " + disclosures.length + "건" : (debt ? "섹터 " + debt.median + arr(debt.vs) : "") })
                if (cards.length < 2) return null
                return (
                    <div style={{ margin: "6px 0 2px" }}>
                        <div style={{ fontSize: 11.5, fontWeight: 700, color: C.faint, marginBottom: 6, paddingLeft: 2 }}>먼저 볼 것 · 사실만 · 판단은 직접</div>
                        <div style={{ display: "grid", gridTemplateColumns: narrow ? "1fr 1fr" : "repeat(4, 1fr)", gap: 8 }}>
                            {cards.map((c: any, i: number) => (
                                <div key={i} style={{ background: C.card, borderRadius: 14, padding: "11px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                                    <div style={{ fontSize: 11.5, fontWeight: 700, color: C.sub, marginBottom: 5 }}>{c.q}</div>
                                    <div style={{ fontSize: 14.5, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px" }}>{c.a}</div>
                                    {c.sub && <div style={{ fontSize: 10.5, fontWeight: 600, color: C.faint, marginTop: 3 }}>{c.sub}</div>}
                                </div>
                            ))}
                        </div>
                    </div>
                )
            })()}

            {/* 미니 목차 — 렌더된 섹션 자동 구성, 탭=해당 섹션 스크롤. sticky/fixed 없이 in-flow (하드코드 position 금지 정합) */}
            {tocSecs.length >= 4 && (
                <div data-noprint style={{ display: "flex", gap: 6, overflowX: "auto", padding: "10px 2px 2px", WebkitOverflowScrolling: "touch" }}>
                    {tocSecs.map((t) => (
                        <button key={t}
                            onClick={() => {
                                try {
                                    const n = rootRef.current && rootRef.current.querySelector(`[data-sec="${t.replace(/"/g, '\\"')}"]`)
                                    if (n) n.scrollIntoView({ behavior: "smooth", block: "start" })
                                } catch (e) {}
                            }}
                            style={{ flexShrink: 0, border: "none", cursor: "pointer", fontFamily: FONT, fontSize: 11.5, fontWeight: 700, color: C.sub, background: C.card, borderRadius: 999, padding: "6px 11px", boxShadow: "0 1px 2px rgba(0,0,0,0.04)" }}>
                            {t.split(" — ")[0].split(" · ")[0]}
                        </button>
                    ))}
                </div>
            )}

            {/* 내장 차트 제거(2026-07-03 컴플라이언스) — 차트 = 같은 페이지 PublicLiveChart(TradingView 위젯)가 담당(verity-ticker-change 추종) */}

            {/* 수급 — 탭하면 정확 수치 */}
            {flowRows.length > 0 && (
                <>
                    {sectionTitle("수급 — 외국인·기관 5일", "순매매량(주) · 네이버 · 탭=정확 수치", "수급")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "8px 14px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        {/* 다이버징 막대 — 외국인·기관 엇갈림을 한눈에. 아래 행 리스트는 정확 수치용으로 유지 */}
                        <FlowDivergingChart rows={flowRows} C={C} narrow={narrow} />
                        <div style={{ height: 1, background: C.line, margin: "12px 0 2px" }} />
                        {flowRows.map((r: any, i: number) => {
                            const opened = openFlow === i
                            return (
                                <div key={i} style={{ borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                    <div onClick={() => setOpenFlow(opened ? -1 : i)} style={{ display: "flex", gap: 12, padding: "10px 0", alignItems: "center", cursor: "pointer" }}>
                                        <span style={{ flexShrink: 0, width: 44, fontSize: 11.5, fontWeight: 700, color: C.faint }}>{mmdd(r.date)}</span>
                                        {flowBar(r.foreign_net, "외국인")}
                                        {flowBar(r.inst_net, "기관")}
                                        <span style={{ flexShrink: 0, fontSize: 13, color: C.faint, fontWeight: 700, transform: opened ? "rotate(90deg)" : "none", transition: "transform 0.12s" }}>›</span>
                                    </div>
                                    {opened && (
                                        <div style={{ padding: "2px 0 12px", display: "flex", flexDirection: "column", gap: 6 }}>
                                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
                                                <span style={{ color: C.sub, fontWeight: 600 }}>외국인 순매매</span>
                                                <span style={{ fontWeight: 800, color: (Number(r.foreign_net) || 0) >= 0 ? C.up : C.down }}>{fmtSharesExact(r.foreign_net)}</span>
                                            </div>
                                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
                                                <span style={{ color: C.sub, fontWeight: 600 }}>기관 순매매</span>
                                                <span style={{ fontWeight: 800, color: (Number(r.inst_net) || 0) >= 0 ? C.up : C.down }}>{fmtSharesExact(r.inst_net)}</span>
                                            </div>
                                            {r.close != null && (
                                                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
                                                    <span style={{ color: C.sub, fontWeight: 600 }}>종가</span>
                                                    <span style={{ fontWeight: 800, color: C.ink }}>{wonStr(r.close)}</span>
                                                </div>
                                            )}
                                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{dateDot(r.date)} · 네이버 순매매량 사실 · 자체 수급점수 아님</div>
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>+순매수(빨강)·−순매도(파랑) · 외부 시장 사실 · 자체 수급점수 아님</div>
                    </div>
                </>
            )}

            {/* 대차잔고 — 공매도 압력 proxy (top200 보유 종목만, 미보유 graceful 미표시) */}
            {lendingRow && (
                <>
                    {sectionTitle("대차잔고", "공매도 압력 proxy · 금융위 data.go.kr", "대차잔고")}
                    <div style={{ background: C.card, borderRadius: 16, padding: 14, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                            <div>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700 }}>대차잔고 금액</div>
                                <div style={{ fontSize: 16, fontWeight: 800, color: C.ink }}>{eokWon(lendingRow.lending_amt)}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700 }}>대차잔고 수량</div>
                                <div style={{ fontSize: 16, fontWeight: 800, color: C.ink }}>{fmtVol(lendingRow.lending_qty)}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700 }}>당일 신규체결</div>
                                <div style={{ fontSize: 14.5, fontWeight: 800, color: C.ink }}>{fmtVol(lendingRow.new_qty)}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700 }}>당일 상환</div>
                                <div style={{ fontSize: 14.5, fontWeight: 800, color: C.ink }}>{fmtVol(lendingRow.redemption_qty)}</div>
                            </div>
                        </div>
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>
                            대차잔고 = 시장에 빌려준 주식(공매도 재료·압력 proxy). 진짜 공매도 잔고 아님 · 외부 사실{lendAsOf ? " · " + dateDot(lendAsOf) : ""}
                        </div>
                    </div>
                </>
            )}

            {/* 공매도·신용 — 스냅샷 universe (graceful 미표시). KRX 무료차단 데이터=KIS */}
            {supplyRow && (supplyRow.short_ratio_5d != null || (supplyRow.credit_qty || 0) > 0) && (
                <>
                    {sectionTitle("공매도·신용", "KRX·KIS 외부 사실 · 스냅샷 종목")}
                    <div style={{ background: C.card, borderRadius: 16, padding: 14, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                            {supplyRow.short_ratio_5d != null && (
                                <div>
                                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700, display: "inline-flex", alignItems: "center" }}>공매도 비중 (5일평균)<Info k="공매도" /></div>
                                    <div style={{ fontSize: 16, fontWeight: 800, color: C.ink }}>{Number(supplyRow.short_ratio_5d).toFixed(2)}%</div>
                                </div>
                            )}
                            {supplyRow.short_qty != null && (
                                <div>
                                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700 }}>최근 공매도량</div>
                                    <div style={{ fontSize: 16, fontWeight: 800, color: C.ink }}>{fmtVol(supplyRow.short_qty)}</div>
                                </div>
                            )}
                            {(supplyRow.credit_qty || 0) > 0 && (
                                <div>
                                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700, display: "inline-flex", alignItems: "center" }}>신용잔고<Info k="신용잔고" /></div>
                                    <div style={{ fontSize: 16, fontWeight: 800, color: C.ink }}>{fmtVol(supplyRow.credit_qty)}</div>
                                </div>
                            )}
                            {(supplyRow.credit_rate || 0) > 0 && (
                                <div>
                                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700 }}>신용잔고율</div>
                                    <div style={{ fontSize: 16, fontWeight: 800, color: C.ink }}>{Number(supplyRow.credit_rate).toFixed(2)}%</div>
                                </div>
                            )}
                        </div>
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>
                            공매도 비중·신용잔고 = 외부 사실(KRX·KIS)
                        </div>
                    </div>
                </>
            )}

            {/* 기본 지표 — 탭하면 계산식·실제 투입 숫자·출처 */}
            {Object.keys(facts).length > 0 && (
                <>
                    {sectionTitle("기본 지표", "DART·KRX · 탭=계산식·출처")}
                    <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(${narrow ? 100 : 120}px, 1fr))`, gap: 10 }}>
                        {Object.keys(facts).map((k) => {
                            const opened = openMetric === k
                            return (
                                <div key={k} onClick={() => setOpenMetric(opened ? "" : k)} style={{ background: C.card, borderRadius: 14, padding: "12px 13px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", cursor: "pointer", gridColumn: opened ? "1 / -1" : "auto", transition: "grid-column 0.1s" }}>
                                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                        <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700, display: "inline-flex", alignItems: "center" }}>{k}<Info k={k} /></div>
                                        <span style={{ fontSize: 12, color: C.faint, fontWeight: 700, transform: opened ? "rotate(90deg)" : "none", transition: "transform 0.12s" }}>›</span>
                                    </div>
                                    <div style={{ fontFamily: HEAD, fontSize: 18, fontWeight: 800, letterSpacing: "-0.5px", margin: "3px 0" }}>{facts[k]}</div>
                                    {(() => {
                                        // 기준점 = 업종 중앙값 대비(peer). 외부 사실 비교일 뿐 좋다·나쁘다 판단 아님(RULE 7).
                                        const pr = peer && peer.rows ? peer.rows.find((r: any) => r.key === k) : null
                                        if (!pr || (pr.vs !== "above" && pr.vs !== "below")) return null
                                        return <div style={{ fontSize: 10.5, fontWeight: 700, color: C.vt, marginBottom: 2 }}>업종 {pr.vs === "above" ? "↑ 높음" : "↓ 낮음"}<span style={{ color: C.faint, fontWeight: 600 }}> · 중앙값 {pr.median}</span></div>
                                    })()}
                                    {fnote[k] && <div style={{ fontSize: 11, color: C.sub, fontWeight: 600 }}>{fnote[k]}</div>}
                                    {opened && (
                                        <div style={{ marginTop: 9, paddingTop: 9, borderTop: `1px solid ${C.line}`, display: "flex", flexDirection: "column", gap: 6 }}>
                                            {INFO[k] && <div style={{ fontSize: 12, color: C.sub, fontWeight: 600, lineHeight: 1.5 }}>{INFO[k]}</div>}
                                            {METRIC_FORMULA[k] && (
                                                <div style={{ fontSize: 11.5, fontWeight: 700, color: C.vt, lineHeight: 1.45 }}>
                                                    계산 · {METRIC_FORMULA[k]}{fnote[k] === "자체계산" ? " (AlphaNest 직접 계산)" : ""}
                                                </div>
                                            )}
                                            {factsCalc[k] && (
                                                <div style={{ fontSize: 11.5, fontWeight: 700, color: C.ink, lineHeight: 1.45, background: C.bg, borderRadius: 8, padding: "7px 9px" }}>
                                                    = {factsCalc[k]}
                                                </div>
                                            )}
                                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>출처 · DART·KRX 공식 사실</div>
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                    </div>
                </>
            )}

            {/* 기업 개요 */}
            {overview && (overview.sector || overview.shares || overview.tagline) && (
                <>
                    {sectionTitle("기업 개요", "DART·IR · 사실")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        {[["사업", overview.tagline], ["업종", overview.sector], ["발행주식수", overview.shares]].filter((x) => x[1]).map(([k, v]: any, i) => kvRow(k, v, i))}
                    </div>
                </>
            )}

            {/* 동종업계 비교 — 탭하면 상세 */}
            {peer && peer.rows && peer.rows.length > 0 && (
                <>
                    {sectionTitle("동종업계 비교 · " + peer.sector, "업종 중앙값(N=" + peer.n + ") · 탭=상세", "동종업계")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "8px 16px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        {peer.rows.map((r: any, i: number) => {
                            const opened = openPeer === i
                            const dir = r.vs === "above" ? "업종 중앙값보다 높음" : r.vs === "below" ? "업종 중앙값보다 낮음" : "업종 중앙값과 비슷"
                            return (
                                <div key={i} style={{ borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                    <div onClick={() => setOpenPeer(opened ? -1 : i)} style={{ padding: "11px 0 9px", cursor: "pointer" }}>
                                        <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                                            <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: C.sub, fontWeight: 600 }}>{r.key}</span>
                                            <span style={{ flexShrink: 0, fontSize: 14, fontWeight: 800, color: C.ink }}>{r.value}</span>
                                            <span style={{ flexShrink: 0, fontSize: 11.5, color: C.faint, fontWeight: 600 }}>업종 {r.median}</span>
                                            <span style={{ flexShrink: 0, width: 12, textAlign: "center", fontSize: 12, color: C.faint, fontWeight: 700, transform: opened ? "rotate(90deg)" : "none", transition: "transform 0.12s" }}>›</span>
                                        </div>
                                        {/* 백분위 스트립 — 분포 내 위치(항상 노출). 옛 ↑/↓ 화살표는 위치가 대신하므로 제거 */}
                                        {r.pct != null && <PeerStrip pct={r.pct} C={C} />}
                                    </div>
                                    {opened && (
                                        <div style={{ padding: "2px 0 12px", display: "flex", flexDirection: "column", gap: 5 }}>
                                            <div style={{ fontSize: 12.5, fontWeight: 700, color: C.ink, lineHeight: 1.5 }}>
                                                {r.key} {r.value} · {peer.sector} 중앙값 {r.median} (N={peer.n}) → <span style={{ color: C.vt }}>{dir}</span>
                                            </div>
                                            {/* 스트립은 접힌 행에 항상 노출 — 여기선 숫자로만 보강(중복 차트 금지) */}
                                            {r.pct != null && (
                                                <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 700 }}>동종 분포 백분위 {r.pct} <span style={{ color: C.faint, fontWeight: 600 }}>(이 값보다 낮은 동종 {r.pct}%)</span></div>
                                            )}
                                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>같은 섹터 종목 중앙값·분포와의 사실 비교 — 높다·낮다가 좋다·나쁘다는 아님(판단 X)</div>
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                        {/* 범례 — 단일 계열이라 범례 박스 대신 마크 설명 한 줄 (카드당 1회) */}
                        {peer.rows.some((r: any) => r.pct != null) && (
                            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginTop: 10, paddingTop: 9, borderTop: `1px solid ${C.line}` }}>
                                <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: C.sub }}>
                                    <span style={{ width: 9, height: 9, borderRadius: "50%", background: C.vt }} />이 종목
                                </span>
                                <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: C.sub }}>
                                    <span style={{ width: 1.5, height: 10, background: C.line }} />업종 중앙값
                                </span>
                                <span style={{ marginLeft: "auto", fontSize: 10.5, fontWeight: 600, color: C.faint }}>← 낮음 · 높음 →</span>
                            </div>
                        )}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>{peer.note}</div>
                    </div>
                </>
            )}

            {/* KR↔US 교차피어 (Tier B B-5) — 반대 시장 동일 GICS 섹터 중앙값 비교. 어느 MTS도 안 주는 교차시장 사실(RULE 7) */}
            {(() => {
                const gics = s.gics
                if (!gics) return null
                const isKR = s.market !== "US"
                const other = isKR ? crossMed.US : crossMed.KR
                const om = other && other[gics]
                if (!om || !om.median) return null
                const otherLabel = isKR ? "미국" : "한국"
                const secKo = s.gics_ko || om.sector_ko || gics
                const KEYS = ["PER", "PBR", "ROE", "영업이익률"]
                const rows = KEYS.map((k: string) => {
                    const med = om.median[k]
                    if (med == null) return null
                    const pr = peer && peer.rows ? peer.rows.find((r: any) => r.key === k) : null
                    if (!pr || pr.value == null) return null
                    const own = parseFloat(String(pr.value).replace(/[%,\s]/g, ""))
                    if (!isFinite(own)) return null
                    const suf = k === "ROE" || k === "영업이익률" ? "%" : ""
                    return { key: k, own: pr.value, med: med + suf, vs: own > med ? "above" : own < med ? "below" : "equal", n: (om.ns && om.ns[k]) || 0 }
                }).filter(Boolean) as any[]
                if (!rows.length) return null
                return (
                    <>
                        {sectionTitle("KR↔US 교차피어 · " + secKo, otherLabel + " 동종 섹터 중앙값 비교", "교차피어")}
                        <div style={{ background: C.card, borderRadius: 16, padding: "8px 16px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                            {rows.map((r: any, i: number) => (
                                <div key={i} style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                    <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: C.sub, fontWeight: 600 }}>{r.key}</span>
                                    <span style={{ flexShrink: 0, fontSize: 14, fontWeight: 800, color: C.ink, minWidth: 56, textAlign: "right" }}>{r.own}</span>
                                    <span style={{ flexShrink: 0, fontSize: 11.5, color: C.faint, fontWeight: 600, minWidth: 96, textAlign: "right" }}>{otherLabel} {r.med}{r.n ? " (N=" + r.n + ")" : ""}</span>
                                    <span style={{ flexShrink: 0, width: 16, textAlign: "center", fontSize: 13, fontWeight: 800, color: C.vt }}>{r.vs === "above" ? "↑" : r.vs === "below" ? "↓" : "="}</span>
                                </div>
                            ))}
                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>
                                {otherLabel} 상장사 중 같은 GICS 섹터(<b style={{ color: C.sub }}>{secKo}</b>) 종목의 중앙값과 비교 · 어느 MTS도 안 주는 교차시장 사실 — 높다·낮다가 좋다·나쁘다는 아님(RULE 7). 섹터=yfinance GICS(미상장분 SIC 근사).
                            </div>
                        </div>
                    </>
                )
            })()}

            {/* 재무 추이 — 연간 손익(fin_series) / 분기 건전성(dart_quarterly) 탭 병합.
                2026-07-10 PM: "재무 추이"·"분기 재무 추이" 두 섹션이 같은 걸로 보임(이름 혼동) → 한 섹션 탭 2개.
                데이터는 직교 — 연간 = 매출·영업이익·순익 절대 규모 + 1·3·5년 비교 / 분기 = 부채·ROA·유동·마진 건전성 비율.
                QuarterlyTrend 는 항상 mount(숨김) — fetch 1회 유지 + onCount 로 탭 노출 판단. 둘 다 없으면 섹션 자동 숨김(RULE 7). */}
            {(() => {
                const onCv = RenderTarget.current() === RenderTarget.canvas
                const isKRt = /^\d{6}$/.test(String(s.ticker || ""))
                const hasAnnual = Array.isArray(s.fin_series) && s.fin_series.length >= 2
                const hasQ = onCv || qtN >= 4
                const both = hasAnnual && hasQ
                const tab = trendTab === "q" ? (hasQ ? "q" : "annual") : (hasAnnual ? "annual" : "q")
                const show = hasAnnual || hasQ
                return (
                    <>
                        {show && sectionTitle("재무 추이", tab === "annual"
                            ? (isKRt ? "DART" : "SEC 10-K") + " · 연간 손익 실값 · 과거(1·3·5년) 비교"
                            : (isKRt ? "DART 분기보고서" : "SEC 10-Q") + " · 건전성 비율(부채·ROA·유동·마진)")}
                        {both && (
                            <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
                                {[{ k: "annual", l: "연간 손익" }, { k: "q", l: "분기 건전성" }].map((t) => (
                                    <button key={t.k} onClick={() => setTrendTab(t.k as "annual" | "q")}
                                        style={{ flex: 1, border: "none", cursor: "pointer", padding: "8px 0", borderRadius: 10, fontSize: 12.5, fontWeight: 800, fontFamily: FONT, background: tab === t.k ? C.vt : C.card, color: tab === t.k ? C.onAccent : C.sub, boxShadow: tab === t.k ? "none" : "0 1px 3px rgba(0,0,0,0.04)" }}>{t.l}</button>
                                ))}
                            </div>
                        )}
                        {show && tab === "annual" && hasAnnual && <FinTrend series={s.fin_series} C={C} usd={!isKRt} />}
                        {/* 항상 mount — display 토글만 (탭 전환마다 재fetch 방지, ResizeObserver 가 표시 시 폭 재측정) */}
                        <div style={{ display: show && tab === "q" ? "block" : "none" }}>
                            <QuarterlyTrend ticker={s.ticker} C={C} isDark={C === DARK} quarterlyUrl={isKRt ? QT_DEFAULT_URL : QT_US_URL} embedded onCount={setQtN} />
                        </div>
                    </>
                )
            })()}

            {/* 재무 요약 — 탭하면 재무제표 전체(손익/재무상태/현금흐름/비율) */}
            {financials && financials.values && Object.keys(financials.values).length > 0 && (
                <>
                    {sectionTitle("재무 요약", "DART · " + (financials.period || "최근 결산") + (finGroups.length ? " · 탭=재무제표 전체" : ""), finGroups.length ? "재무제표" : undefined)}
                    <div style={{ background: C.card, borderRadius: 16, padding: "6px 16px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        {Object.keys(financials.values).map((k, i) => kvRow(k, financials.values[k], i))}
                        {finGroups.length > 0 && (
                            <>
                                <button onClick={() => setOpenFin((v) => !v)} style={{ width: "100%", marginTop: 10, border: "none", cursor: "pointer", padding: "9px 0", borderRadius: 10, fontSize: 12, fontWeight: 800, fontFamily: FONT, background: openFin ? C.vg : C.bg, color: openFin ? C.onAccent : C.sub }}>
                                    {openFin ? "재무제표 접기" : "재무제표 전체 보기 (손익·재무상태·현금흐름·비율)"}
                                </button>
                                {openFin && (
                                    <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 14 }}>
                                        {finGroups.map((g: any, gi: number) => (
                                            <div key={gi}>
                                                <div style={{ fontFamily: HEAD, fontSize: 12, fontWeight: 800, color: C.vt, marginBottom: 4 }}>{g.title}</div>
                                                {(g.rows || []).map((row: any, ri: number) => (
                                                    <div key={ri} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderTop: ri === 0 ? "none" : `1px solid ${C.line}`, fontSize: 12.5 }}>
                                                        <span style={{ color: C.sub, fontWeight: 600 }}>{row.k}</span>
                                                        <span style={{ fontWeight: 800, color: finValColor(row.v) }}>{row.v}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        ))}
                                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>DART 전자공시 최근 결산 실값 · 음수=−(현금 유출) · 단년 기준(추이는 분기 누적 후) · 자체 판단 아님</div>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </>
            )}

            {/* (구 '재무 추이' 연간 블록 = 위 병합 섹션 '연간 손익' 탭으로 이동, 2026-07-10) */}

            {/* 현금흐름 워터폴 (2026-07-12) — 영업→투자→재무→순증감. DART 현금흐름표 실값 누적.
                파싱 실패 시 컴포넌트가 null 반환 → 섹션 자동 숨김(가짜 숫자 0). KR 한정(미장은 현금흐름 그룹 부재). */}
            {(() => {
                const cf = finGroups.find((g: any) => String(g && g.title || "").indexOf("현금흐름") >= 0)
                if (!cf) return null
                // 🚨 파싱 가능 여부를 섹션 밖에서 먼저 판정 — JSX 엘리먼트는 항상 truthy 라
                //    컴포넌트의 null 반환만으로는 섹션 제목·빈 카드가 남음.
                const cfRows: any[] = Array.isArray(cf.rows) ? cf.rows : []
                const pk = (k: string) => { const r = cfRows.find((x: any) => String(x.k || "").indexOf(k) === 0); return r ? parseKRWCompact(r.v) : null }
                if (pk("영업활동") == null || pk("투자활동") == null || pk("재무활동") == null) return null
                return (
                    <>
                        {sectionTitle("현금흐름", "DART · " + (financials.period || "최근 결산") + " · 실제 현금 이동")}
                        <div style={{ background: C.card, borderRadius: 16, padding: narrow ? "16px 14px 14px" : "18px 18px 14px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                            <CashflowWaterfall group={cf} C={C} narrow={narrow} />
                        </div>
                    </>
                )
            })()}

            {/* 공시·리스크 레이더 */}
            {disclosures.length > 0 && (
                <>
                    {sectionTitle("공시·리스크 레이더", "사실 · 탭=상세")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        {disclosures.map((d: any, i: number) => {
                            const corr = d.is_correction
                            const chipC = corr ? { fg: C.amber, bg: C.amberS } : { fg: C.down, bg: C.downS }
                            const opened = openDisc === i
                            return (
                                <div key={i} style={{ borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                    <div onClick={() => setOpenDisc(opened ? -1 : i)} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "11px 0", cursor: "pointer" }}>
                                        <span style={{ flexShrink: 0, fontSize: 11, fontWeight: 800, color: chipC.fg, background: chipC.bg, padding: "3px 8px", borderRadius: 7, whiteSpace: "nowrap" }}>{corr ? "정정" : d.label}</span>
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.45, wordBreak: "break-word" }}>{renderTitle(d.title, "d" + i)}</div>
                                            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3 }}>{d.date}{d.filer ? " · " + d.filer : ""}</div>
                                        </div>
                                        <span style={{ flexShrink: 0, fontSize: 13, color: C.faint, fontWeight: 700, transform: opened ? "rotate(90deg)" : "none", transition: "transform 0.12s" }}>›</span>
                                    </div>
                                    {opened && (
                                        <div style={{ padding: "2px 0 13px", display: "flex", flexDirection: "column", gap: 8 }}>
                                            <div style={{ fontSize: 13, fontWeight: 600, color: C.ink, lineHeight: 1.5, wordBreak: "break-word" }}>{d.title}</div>
                                            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 11.5, color: C.sub, fontWeight: 600 }}>
                                                <span>구분 · {corr ? "정정공시" : d.label}</span>
                                                <span>접수 · {d.date}</span>
                                                {d.filer && <span>제출 · {d.filer}</span>}
                                            </div>
                                            {d.source_url && (<a href={d.source_url} target="_blank" rel="noopener" style={{ alignSelf: "flex-start", fontSize: 12, fontWeight: 800, color: C.onAccent, background: C.vg, borderRadius: 9, padding: "8px 14px", textDecoration: "none" }}>DART 원문 전체 보기 ↗</a>)}
                                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>요약·판단 없이 원문 사실만 — 결론은 본인 판단</div>
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                    </div>
                </>
            )}

            {/* 공시 이력·빈도 */}
            {foren && foren.events && foren.events.length > 0 && (
                <>
                    {sectionTitle("공시 이력·빈도", "DART 원문 기준 · 사실", "공시이력")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
                            {Object.keys(foren.counts || {}).sort((a, b) => (foren.counts[b] - foren.counts[a])).map((cat) => (
                                <span key={cat} style={{ fontSize: 11.5, fontWeight: 800, color: catColor(cat), background: C.bg, borderRadius: 8, padding: "4px 9px" }}>{cat} {foren.counts[cat]}회</span>
                            ))}
                        </div>
                        {foren.dilution_count > 0 && (<div style={{ fontSize: 12, color: C.amber, fontWeight: 700, marginTop: 9, lineHeight: 1.5 }}>희석성 공시(유상증자·CB·BW 등) 합 {foren.dilution_count}회 — 사실 빈도일 뿐, 위험 판단 아님</div>)}
                        {foren.forensics_flags && (foren.forensics_flags.dilution_12m > 0 || foren.forensics_flags.correction_count > 0) && (
                            <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginTop: 9 }}>
                                {foren.forensics_flags.dilution_12m > 0 && (
                                    <span style={{ fontSize: 11.5, fontWeight: 700, color: C.amber, background: C.bg, borderRadius: 8, padding: "4px 9px" }}>최근 12개월 희석 {foren.forensics_flags.dilution_12m}회{foren.forensics_flags.dilution_annual_avg_prior > 0 ? ` (직전 연평균 ${foren.forensics_flags.dilution_annual_avg_prior}회)` : ""}{foren.forensics_flags.dilution_span ? ` · ${foren.forensics_flags.dilution_span}` : ""}</span>
                                )}
                                {foren.forensics_flags.correction_count > 0 && (
                                    <span style={{ fontSize: 11.5, fontWeight: 700, color: C.sub, background: C.bg, borderRadius: 8, padding: "4px 9px" }}>정정공시 {foren.forensics_flags.correction_count}회 ({foren.forensics_flags.correction_pct}%)</span>
                                )}
                            </div>
                        )}
                        <div style={{ marginTop: 10 }}>
                            {(forenAll ? foren.events : foren.events.slice(0, 6)).map((e: any, i: number) => (
                                <div key={i} style={{ display: "flex", gap: 9, alignItems: "flex-start", padding: "9px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                    <span style={{ flexShrink: 0, width: 42, fontSize: 11, fontWeight: 700, color: C.faint }}>{mmdd(e.date)}</span>
                                    <span style={{ flexShrink: 0, fontSize: 10.5, fontWeight: 800, color: catColor(e.category), background: C.bg, borderRadius: 6, padding: "2px 7px", whiteSpace: "nowrap" }}>{e.category}</span>
                                    <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, color: C.ink, lineHeight: 1.4, wordBreak: "break-word" }}>{e.title}</span>
                                    {e.source_url && (<a href={e.source_url} target="_blank" rel="noopener" style={{ flexShrink: 0, fontSize: 10, fontWeight: 800, color: C.vg, background: C.vgS, borderRadius: 6, padding: "2px 7px", textDecoration: "none", whiteSpace: "nowrap" }}>원문</a>)}
                                </div>
                            ))}
                        </div>
                        {foren.events.length > 6 && (<button onClick={() => setForenAll((v) => !v)} style={{ width: "100%", marginTop: 8, border: "none", cursor: "pointer", padding: "9px 0", borderRadius: 10, fontSize: 12, fontWeight: 800, fontFamily: FONT, background: C.bg, color: C.sub }}>{forenAll ? "접기" : `이력 ${foren.events.length}건 전체 보기`}</button>)}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>DART 원문 제목 기준 이벤트 빈도(사실) · 현재 수집창 한정(과거 백필 시 심화)</div>
                    </div>
                </>
            )}

            {/* 내부자 거래 */}
            {insider && insider.trades && insider.trades.length > 0 && (
                <>
                    {sectionTitle("내부자 거래 · 임원·주요주주", "DART · 美 Form4 KR판", "내부자")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "baseline" }}>
                            <span style={{ fontSize: 12.5, fontWeight: 800, color: C.up }}>매수 {insider.buy_n}건</span>
                            <span style={{ fontSize: 12.5, fontWeight: 800, color: C.down }}>매도 {insider.sell_n}건</span>
                            <span style={{ fontSize: 12.5, fontWeight: 800, color: (insider.net_change || 0) >= 0 ? C.up : C.down }}>순증감 {fmtShares(insider.net_change)}</span>
                        </div>
                        {/* 내부자 군집(사실) — 최근 90일 서로 다른 매수/매도 임원 수. 여러 임원 동시 매수 = 관측 강신호(교과서 일반론), 자체 점수 아님(RULE 7). */}
                        {(() => {
                            const tr: any[] = insider.trades || []
                            const cutoff = Date.now() - 90 * 86400000
                            const parseD = (s: any) => { const t = new Date(String(s || "")).getTime(); return isFinite(t) ? t : 0 }
                            const recent = tr.filter((t) => parseD(t.date) >= cutoff)
                            const buyers = new Set(recent.filter((t) => Number(t.change) > 0).map((t) => t.person))
                            const sellers = new Set(recent.filter((t) => Number(t.change) < 0).map((t) => t.person))
                            if (!buyers.size && !sellers.size) return null
                            return (
                                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 9, paddingTop: 9, borderTop: `1px solid ${C.line}` }}>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>최근 90일 군집</span>
                                    {buyers.size > 0 && <span style={{ fontSize: 11.5, fontWeight: 800, color: C.up }}>서로 다른 임원 {buyers.size}명 매수</span>}
                                    {sellers.size > 0 && <span style={{ fontSize: 11.5, fontWeight: 800, color: C.down }}>{sellers.size}명 매도</span>}
                                    {buyers.size >= 3 && <span style={{ fontSize: 10.5, fontWeight: 800, color: "#ffffff", background: C.up, borderRadius: 6, padding: "2px 7px", whiteSpace: "nowrap" }}>매수 집중</span>}
                                </div>
                            )
                        })()}
                        <div style={{ marginTop: 10 }}>
                            {(insiderAll ? insider.trades : insider.trades.slice(0, 6)).map((t: any, i: number) => (
                                <div key={i} style={{ display: "flex", gap: 9, alignItems: "center", padding: "9px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                    <span style={{ flexShrink: 0, width: 42, fontSize: 11, fontWeight: 700, color: C.faint }}>{mmdd(t.date)}</span>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <span style={{ fontSize: 12.5, fontWeight: 700, color: C.ink }}>{t.person}</span>
                                        {t.position && <span style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginLeft: 6 }}>{t.position}</span>}
                                    </div>
                                    <span style={{ flexShrink: 0, fontSize: 12.5, fontWeight: 800, color: (Number(t.change) || 0) >= 0 ? C.up : C.down }}>{fmtShares(t.change)}</span>
                                    {t.source_url && (<a href={t.source_url} target="_blank" rel="noopener" style={{ flexShrink: 0, fontSize: 10, fontWeight: 800, color: C.vg, background: C.vgS, borderRadius: 6, padding: "2px 7px", textDecoration: "none", whiteSpace: "nowrap" }}>원문</a>)}
                                </div>
                            ))}
                        </div>
                        {insider.trades.length > 6 && (<button onClick={() => setInsiderAll((v) => !v)} style={{ width: "100%", marginTop: 8, border: "none", cursor: "pointer", padding: "9px 0", borderRadius: 10, fontSize: 12, fontWeight: 800, fontFamily: FONT, background: C.bg, color: C.sub }}>{insiderAll ? "접기" : `거래 ${insider.trades.length}건 전체 보기`}</button>)}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>DART 공시 사실(보고자·증감 +매수/−매도)만 · 자체 매매신호 아님 · 토스·네이버엔 없는 내부자 view</div>
                    </div>
                </>
            )}

            {/* 美 forensics — Form4 내부자 · 13D/G 대량보유 · 13F 스마트머니 · 컨센서스 (US 종목, RULE 7 사실만) */}
            {usForen && (
                <>
                    {usForen.insider && usForen.insider.trades && usForen.insider.trades.length > 0 && (
                        <>
                            {sectionTitle("美 내부자 거래 · SEC Form 4", "임원·이사·10%주주")}
                            <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                                <div style={{ display: "flex", gap: 14, marginBottom: 10, flexWrap: "wrap" }}>
                                    <span style={{ fontSize: 12.5, fontWeight: 800, color: C.up }}>매수 {usForen.insider.buy_n || 0}건</span>
                                    <span style={{ fontSize: 12.5, fontWeight: 800, color: C.down }}>매도 {usForen.insider.sell_n || 0}건</span>
                                    <span style={{ fontSize: 12.5, fontWeight: 800, color: (usForen.insider.net_change || 0) >= 0 ? C.up : C.down }}>순증감 {fmtShares(usForen.insider.net_change)}</span>
                                </div>
                                {/* 내부자 군집(사실) — 최근 90일 서로 다른 매수/매도 임원 수. Form4 취득/처분 기준. 점수 아님(RULE 7). */}
                                {(() => {
                                    const tr: any[] = usForen.insider.trades || []
                                    const cutoff = Date.now() - 90 * 86400000
                                    const parseD = (s: any) => { const t = new Date(String(s || "")).getTime(); return isFinite(t) ? t : 0 }
                                    const recent = tr.filter((t) => parseD(t.date) >= cutoff)
                                    const buyers = new Set(recent.filter((t) => Number(t.change) > 0).map((t) => t.person))
                                    const sellers = new Set(recent.filter((t) => Number(t.change) < 0).map((t) => t.person))
                                    if (!buyers.size && !sellers.size) return null
                                    return (
                                        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
                                            <span style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>최근 90일 군집</span>
                                            {buyers.size > 0 && <span style={{ fontSize: 11.5, fontWeight: 800, color: C.up }}>서로 다른 임원 {buyers.size}명 매수</span>}
                                            {sellers.size > 0 && <span style={{ fontSize: 11.5, fontWeight: 800, color: C.down }}>{sellers.size}명 매도</span>}
                                            {buyers.size >= 3 && <span style={{ fontSize: 10.5, fontWeight: 800, color: "#ffffff", background: C.up, borderRadius: 6, padding: "2px 7px", whiteSpace: "nowrap" }}>매수 집중</span>}
                                        </div>
                                    )
                                })()}
                                {usForen.insider.trades.slice(0, 6).map((t: any, i: number) => (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "8px 0", borderTop: i === 0 ? "none" : "1px solid " + C.line, fontSize: 12.5 }}>
                                        <span style={{ color: C.sub, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.person || "—"}{t.position ? " · " + t.position : ""}</span>
                                        <span style={{ fontWeight: 800, color: (t.change || 0) >= 0 ? C.up : C.down, flexShrink: 0 }}>{fmtShares(t.change)} <span style={{ color: C.faint, fontWeight: 600 }}>({t.code || "?"})</span></span>
                                    </div>
                                ))}
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>SEC Form 4 공시 사실(취득+/처분−)만 · 자체 매매신호 아님 · 증권사·토스엔 없는 view</div>
                            </div>
                        </>
                    )}

                    {usForen.holdings && usForen.holdings.filings && usForen.holdings.filings.length > 0 && (
                        <>
                            {sectionTitle("美 대량보유 · SEC 13D/13G", "5%+ 신고")}
                            <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                                <div style={{ display: "flex", gap: 14, marginBottom: 10, flexWrap: "wrap" }}>
                                    {usForen.holdings.latest_pct != null && <span style={{ fontSize: 12.5, fontWeight: 800, color: C.vt }}>최근 {usForen.holdings.latest_pct}%</span>}
                                    <span style={{ fontSize: 12.5, fontWeight: 800, color: C.amber }}>13D {usForen.holdings.n_13d || 0}</span>
                                    <span style={{ fontSize: 12.5, fontWeight: 800, color: C.sub }}>13G {usForen.holdings.n_13g || 0}</span>
                                </div>
                                {usForen.holdings.filings.slice(0, 5).map((f: any, i: number) => (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "8px 0", borderTop: i === 0 ? "none" : "1px solid " + C.line, fontSize: 12.5 }}>
                                        <span style={{ color: C.sub, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.filer || "—"} <span style={{ color: C.faint }}>· {f.date}</span></span>
                                        <span style={{ fontWeight: 800, flexShrink: 0, color: String(f.type || "").indexOf("13D") === 0 ? C.amber : C.sub }}>{f.type}{f.pct != null ? " · " + f.pct + "%" : ""}</span>
                                    </div>
                                ))}
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>SEC 13D(행동주의)/13G(수동) 5%+ 공시 사실</div>
                            </div>
                        </>
                    )}

                    {usForen.smart_money && usForen.smart_money.holders && usForen.smart_money.holders.length > 0 && (
                        <>
                            {sectionTitle("美 스마트머니 · 13F", "집중형 액티브 펀드")}
                            <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                                <div style={{ fontSize: 12.5, fontWeight: 800, marginBottom: 10 }}>보유 펀드 {usForen.smart_money.holder_count || usForen.smart_money.holders.length}곳 <span style={{ color: C.faint, fontWeight: 600 }}>· 합산 ${((usForen.smart_money.total_value_usd || 0) / 1e9).toFixed(1)}B</span></div>
                                {usForen.smart_money.holders.slice(0, 6).map((h: any, i: number) => (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "8px 0", borderTop: i === 0 ? "none" : "1px solid " + C.line, fontSize: 12.5 }}>
                                        <span style={{ color: C.sub, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.fund}</span>
                                        <span style={{ flexShrink: 0, fontWeight: 800 }}><span style={{ color: (h.change_type === "NEW" || h.change_type === "INCREASED") ? C.green : h.change_type === "DECREASED" ? C.down : C.faint }}>{h.change_type}</span> <span style={{ color: C.faint, fontWeight: 600 }}>${((h.value_usd || 0) / 1e9).toFixed(1)}B</span></span>
                                    </div>
                                ))}
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>유명 집중형 펀드 13F 보유(분기말+45일 지연) · 인덱스펀드 제외</div>
                            </div>
                        </>
                    )}

                    {usForen.disclosure_forensics && usForen.disclosure_forensics.counts && Object.keys(usForen.disclosure_forensics.counts).length > 0 && (() => {
                        const FLBL: any = {
                            dilution: "희석성 증자(3.02)", delisting_risk: "상장폐지 위험(3.01)", bankruptcy: "파산(1.03)",
                            debt_default: "채무불이행(2.04)", impairment: "자산손상(2.06)", restatement: "재무제표 정정(4.02)",
                            auditor_change: "감사인 교체(4.01)", mna: "인수·합병(2.01)", rights_modification: "주주권리 변경(3.03)",
                            control_change: "지배권 변경(5.01)", restructuring: "구조조정(2.05)",
                        }
                        const df = usForen.disclosure_forensics
                        const adverse = (k: string) => /delisting_risk|bankruptcy|debt_default|restatement|impairment/.test(k)
                        return (
                            <>
                                {sectionTitle("美 공시 이상신호 · SEC 8-K", "중요사건 보고 유형별 건수")}
                                <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                                    <div style={{ fontSize: 12.5, fontWeight: 800, marginBottom: 10 }}>
                                        최근 2년 8-K {df.n_8k || 0}건{df.latest_8k ? <span style={{ color: C.faint, fontWeight: 600 }}> · 최근 {df.latest_8k}</span> : null}
                                    </div>
                                    <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                                        {Object.entries(df.counts).sort((a: any, b: any) => b[1] - a[1]).map(([k, n]: any) => (
                                            <span key={k} style={{ fontSize: 12, fontWeight: 700, color: adverse(k) ? C.up : C.sub, background: adverse(k) ? C.upS : C.bg, borderRadius: 8, padding: "5px 10px" }}>
                                                {FLBL[k] || k} <span style={{ fontWeight: 800 }}>{n}</span>
                                            </span>
                                        ))}
                                    </div>
                                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>SEC EDGAR 8-K item 사실 카운트 · 점수·추천 아님 · 증권사·토스엔 없는 view</div>
                                </div>
                            </>
                        )
                    })()}

                    {usForen.short_interest && usForen.short_interest.short_pct != null && (
                        <>
                            {sectionTitle("美 공매도 잔고 · Short Interest", "yfinance · 월 2회 공시")}
                            <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                                <div style={{ display: "flex", gap: 12, marginBottom: 8, flexWrap: "wrap", alignItems: "baseline" }}>
                                    <span style={{ fontSize: 20, fontWeight: 800, color: C.ink }}>{usForen.short_interest.short_pct}%</span>
                                    <span style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>float 대비 공매도 비중</span>
                                    {usForen.short_interest.short_pct_prior != null ? <span style={{ fontSize: 12, fontWeight: 700, color: C.sub }}>전기 {usForen.short_interest.short_pct_prior}% {(usForen.short_interest.short_pct - usForen.short_interest.short_pct_prior) >= 0 ? "▲" : "▼"}</span> : null}
                                </div>
                                <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 12.5, color: C.sub, fontWeight: 600 }}>
                                    {usForen.short_interest.days_to_cover != null ? <span>숏커버 {usForen.short_interest.days_to_cover}일</span> : null}
                                    {usForen.short_interest.shares_short != null ? <span>공매도 {fmtShares(usForen.short_interest.shares_short)}주</span> : null}
                                    {usForen.short_interest.report_date ? <span style={{ color: C.faint }}>{usForen.short_interest.report_date} 기준</span> : null}
                                </div>
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>NYSE/NASDAQ 공매도 잔고 사실 · 많음=하락 신호 아님(참고) · 증권사·토스엔 없는 view</div>
                            </div>
                        </>
                    )}

                </>
            )}

            {/* 컨센서스 = 출처 링크아웃 (2026-07-10) — 목표가·투자의견 숫자는 제공사(Benzinga/S&P) 소유라
                온사이트 재배포 대신 출처 연결(KRX→네이버 패턴). 실매매(내부자·13F)는 위 SEC 섹션이 담당.
                유료 티어 시 Polygon×Benzinga 정식 라이선스($99/월)로 숫자 부활 큐. */}
            {!onCanvas && s.ticker && (
                <>
                    {sectionTitle("애널리스트 컨센서스", "출처 바로가기")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "6px 8px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        {(/^[0-9]{6}$/.test(String(s.ticker))
                            ? [{ label: "네이버 증권 · 종목분석", url: `https://finance.naver.com/item/coinfo.naver?code=${s.ticker}` }]
                            : [
                                { label: "StockAnalysis · 목표가·의견", url: `https://stockanalysis.com/stocks/${String(s.ticker).toLowerCase()}/forecast/` },
                                { label: "Yahoo Finance", url: `https://finance.yahoo.com/quote/${s.ticker}` },
                            ]
                        ).map((l) => (
                            <a key={l.url} href={l.url} target="_blank" rel="noopener noreferrer"
                                style={{ display: "flex", alignItems: "center", gap: 9, textDecoration: "none", padding: "10px 9px", borderRadius: 10 }}>
                                <span style={{ fontSize: 13, fontWeight: 700, color: C.ink, flex: 1, minWidth: 0 }}>{l.label}</span>
                                <svg width={10} height={10} viewBox="0 0 12 12" fill="none" stroke={C.faint} strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                    <line x1="2.5" y1="9.5" x2="9" y2="3" /><polyline points="4.2,2.8 9.2,2.8 9.2,7.8" />
                                </svg>
                            </a>
                        ))}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, padding: "4px 9px 8px", lineHeight: 1.5 }}>
                            목표가·의견은 출처에서 · 실제 매매는 위 내부자·기관 섹션
                        </div>
                    </div>
                </>
            )}

            {/* 지분구조 · 지배구조 */}
            {ownership && ownership.family_pct != null && (
                <>
                    {sectionTitle("지분구조 · 지배구조", ownership.group ? ownership.group + " 그룹" : "공정위 공식")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                            <span style={{ fontFamily: HEAD, fontSize: 22, fontWeight: 800, color: C.vt, letterSpacing: "-0.6px" }}>{ownership.family_pct}%</span>
                            <span style={{ fontSize: 12.5, fontWeight: 700 }}>총수일가 지배지분</span>
                            {ownership.group && <span style={{ fontSize: 11, fontWeight: 800, color: C.vt, background: C.vtS, borderRadius: 7, padding: "3px 9px" }}>{ownership.group}</span>}
                        </div>
                        <div style={{ display: "flex", width: "100%", height: 8, borderRadius: 4, overflow: "hidden", margin: "10px 0 4px" }}>
                            <span style={{ width: Number(ownership.family_pct) + "%", background: C.vt }} />
                            <span style={{ width: (100 - Number(ownership.family_pct)) + "%", background: C.line }} />
                        </div>
                        {Array.isArray(ownership.shareholders) && ownership.shareholders.length > 0 && (
                            <div style={{ marginTop: 10 }}>
                                {ownership.shareholders.map((sh: any, i: number) => {
                                    const nm = sh.name && sh.name !== sh.type ? String(sh.name) : ""
                                    const generic = !nm || /기타|소액주주|자기주식|우리사주|^친족$|^동일인$|^임원$|기관투자|외국인|개인투자자|국민연금공단/.test(nm)
                                    const corp = sh.type === "소속회사" || /(주식회사|\(주\)|㈜|회사|Ltd|LTD|Inc|INC|Limited|Corp|Company|생명|화재|증권|물산|홀딩스|투자|캐피탈|은행|보험|자산운용|전자|중공업|텔레콤|공단|재단)/.test(nm)
                                    // 인물 = 빌더가 네이버 뉴스 건수 실검증한 link_ok 만 "회사명 이름" 검색 링크 (결과 보장, PM 2026-07-04).
                                    // 법인·재단 = 상시 링크. 검증 안 된 인물 = 일반 텍스트 = 죽은 링크 0.
                                    const shUrl = generic ? null
                                        : corp ? "https://search.naver.com/search.naver?query=" + encodeURIComponent(nm)
                                        : sh.link_ok ? "https://search.naver.com/search.naver?query=" + encodeURIComponent(((s.name || "") + " " + nm).trim())
                                        : null
                                    return (
                                    <div key={i} style={{ padding: "7px 0", borderTop: i === 0 ? `1px solid ${C.line}` : "none" }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                            <span style={{ flexShrink: 0, fontSize: 10.5, fontWeight: 800, color: shTypeColor(sh.type), background: C.bg, borderRadius: 6, padding: "2px 7px", minWidth: 52, textAlign: "center" }}>{sh.type}</span>
                                            {shUrl ? (
                                                <a href={shUrl} target="_blank" rel="noopener noreferrer" title={`${nm} 검색`} style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 700, color: C.vg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textDecoration: "none" }}>{nm} ↗</a>
                                            ) : (
                                                <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, color: C.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{nm}</span>
                                            )}
                                            <span style={{ flexShrink: 0, fontSize: 12.5, fontWeight: 800, color: C.ink }}>{sh.pct}%</span>
                                        </div>
                                        <div style={{ height: 3, borderRadius: 2, background: C.line, marginTop: 4, overflow: "hidden" }}>
                                            <div style={{ width: Math.min(100, Number(sh.pct) || 0) + "%", height: "100%", background: shTypeColor(sh.type) }} />
                                        </div>
                                    </div>
                                    )
                                })}
                            </div>
                        )}
                        {ownership.cross_check && ownership.cross_check.status && (
                            <div style={{ marginTop: 12, background: C.vtS, borderRadius: 12, padding: "11px 13px" }}>
                                <div style={{ fontSize: 11.5, fontWeight: 800, color: C.vt, display: "inline-flex", alignItems: "center" }}>DART ↔ 공정위 교차검증<Info k="교차검증" /></div>
                                <div style={{ fontSize: 12.5, fontWeight: 600, color: C.ink, marginTop: 5, lineHeight: 1.5 }}>
                                    {ownership.cross_check.entity && <b>{ownership.cross_check.entity}</b>}
                                    {ownership.cross_check.dart_pct != null && <> · DART {ownership.cross_check.dart_pct}%</>}
                                    {ownership.cross_check.ftc_pct != null && <> · 공정위 {ownership.cross_check.ftc_pct}%</>}
                                    {" → "}
                                    <span style={{ fontWeight: 800, color: ownership.cross_check.status === "match" ? C.green : C.amber }}>{ownership.cross_check.status === "match" ? "일치" : ownership.cross_check.status === "approx" ? "근사" : "차이"}</span>
                                </div>
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 5 }}>두 공식 출처(DART 공시·공정위 지정) 비교 — 일반 앱엔 없는 이중확인</div>
                            </div>
                        )}
                        {(ownership.parent || ownership.sub_count != null) && (
                            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11.5, color: C.sub, fontWeight: 600, marginTop: 11 }}>
                                {ownership.parent && <span>모회사 · {ownership.parent}</span>}
                                {ownership.sub_count != null && <span>계열사 · {ownership.sub_count}개</span>}
                            </div>
                        )}
                        {Array.isArray(ownership.subsidiaries) && ownership.subsidiaries.length > 0 && (
                            <div style={{ marginTop: 14 }}>
                                <div style={{ fontSize: 12, fontWeight: 800, color: C.ink, marginBottom: 8 }}>주요 자회사 출자 <span style={{ color: C.faint, fontWeight: 600 }}>· 지분율 상위</span></div>
                                {ownership.subsidiaries.map((sub: any, i: number) => (
                                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                        <span style={{ flexShrink: 0, fontSize: 10, fontWeight: 800, color: sub.is_listed ? C.vt : C.faint, background: sub.is_listed ? C.vtS : C.bg, borderRadius: 6, padding: "2px 7px" }}>{sub.is_listed ? "상장" : "비상장"}</span>
                                        <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub.name}</span>
                                        {sub.ownership_pct != null ? <span style={{ flexShrink: 0, fontSize: 12.5, fontWeight: 800, color: C.ink }}>{sub.ownership_pct}%</span> : null}
                                    </div>
                                ))}
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>DART 타법인출자현황·공정위 = 출자 지분율 사실 · 점수·추천 아님</div>
                            </div>
                        )}
                        <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginTop: 9 }}>{ownership.note}</div>
                        {ownership.source && <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 3 }}>{ownership.source} · 1차 출처(나무위키 아님)</div>}
                    </div>
                </>
            )}

            {/* 고용 동향 — 국민연금 가입 사업장 (공단 공시 사실, 월 단위. 사업보고서보다 빠른 고용 흐름) */}
            {empRow && empRow.jnngp_cnt > 0 && (() => {
                const ymTxt = empRow.ym && String(empRow.ym).length === 6 ? String(empRow.ym).slice(2, 4) + "." + Number(String(empRow.ym).slice(4)) + "월" : ""
                const net = Number(empRow.net) || 0
                const netColor = net > 0 ? C.green : net < 0 ? C.down : C.faint
                const stat = (label: string, val: any, color: string) => (
                    <div style={{ flex: 1, minWidth: 80, background: C.bg, borderRadius: 12, padding: "10px 12px" }}>
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 700 }}>{label}</div>
                        <div style={{ fontFamily: HEAD, fontSize: 17, fontWeight: 800, color, letterSpacing: "-0.4px", marginTop: 2 }}>{val}</div>
                    </div>
                )
                return (
                    <>
                        {sectionTitle("고용 동향", "국민연금 가입 기준" + (ymTxt ? " · " + ymTxt : ""))}
                        <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                                <span style={{ fontFamily: HEAD, fontSize: 22, fontWeight: 800, color: C.ink, letterSpacing: "-0.6px" }}>{Number(empRow.jnngp_cnt).toLocaleString()}명</span>
                                <span style={{ fontSize: 12.5, fontWeight: 700 }}>국민연금 가입 임직원</span>
                            </div>
                            <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                                {stat("월 입사", (Number(empRow.hire) || 0).toLocaleString() + "명", C.ink)}
                                {stat("월 퇴사", (Number(empRow.leave) || 0).toLocaleString() + "명", C.ink)}
                                {stat("순증감", (net > 0 ? "+" : "") + net.toLocaleString() + "명", netColor)}
                            </div>
                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>
                                국민연금공단 가입 사업장 공시 · 사업장명 정확일치 매칭 (고용 프록시 — 가입 제외 인원은 미포함) · 사업보고서(분기)보다 빠른 월 단위 관측
                            </div>
                        </div>
                    </>
                )
            })()}

            {/* 부동산 자산 */}
            {realEstate && realEstate.total && (
                <>
                    {sectionTitle("부동산 자산", "DART · 장부가")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                            <span style={{ fontFamily: HEAD, fontSize: 22, fontWeight: 800, color: C.vg, letterSpacing: "-0.6px" }}>{realEstate.total}</span>
                            <span style={{ fontSize: 12.5, fontWeight: 700 }}>투자부동산·토지·건물</span>
                        </div>
                        {Array.isArray(realEstate.items) && realEstate.items.length > 0 && (<div style={{ marginTop: 8 }}>{realEstate.items.map((it: any, i: number) => kvRow(it.name || "항목", it.value, i))}</div>)}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>{realEstate.note || "재무상태표 장부가(시가 아님) · DART"}</div>
                    </div>
                </>
            )}

            {/* VERITY 관측 lens — 컨센서스 위에 얹는 차별 view (토스·키움·LLM 미보유). 룰 기반 사실 분류만, 점수·추천 아님(RULE 7) */}
            {verityLens && verityLens.lynch && (() => {
                const ln = verityLens.lynch
                const lc = ln.color === "success" ? C.green : ln.color === "warn" || ln.color === "caution" ? C.amber
                    : ln.color === "danger" ? C.down : ln.color === "muted" ? C.faint : C.vt
                const lcS = ln.color === "success" ? C.greenS : ln.color === "warn" || ln.color === "caution" ? C.amberS
                    : ln.color === "danger" ? C.downS : C.vtS
                return (
                    <>
                        {sectionTitle("투자 스타일 진단", "피터 린치 6분류 · 공개 재무에 룰 적용")}
                        <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
                                <span style={{ fontSize: 12.5, fontWeight: 800, color: "#ffffff", background: lc, borderRadius: 8, padding: "5px 11px", letterSpacing: "-0.2px" }}>{ln.label || ln.class}</span>
                                {ln.summary && <span style={{ fontSize: 13, fontWeight: 700, color: C.ink }}>{ln.summary}</span>}
                            </div>
                            {Array.isArray(ln.reasons) && ln.reasons.length > 0 && (
                                <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 5 }}>
                                    {ln.reasons.map((r: string, i: number) => (
                                        <div key={i} style={{ fontSize: 12, color: C.sub, fontWeight: 600, lineHeight: 1.5, paddingLeft: 12, position: "relative" }}>
                                            <span style={{ position: "absolute", left: 0, color: lc }}>·</span>{r}
                                        </div>
                                    ))}
                                </div>
                            )}
                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 11, lineHeight: 1.5 }}>{verityLens.note || "피터 린치 6분류를 공개 재무 사실에 적용"}</div>
                        </div>
                    </>
                )
            })()}

            {/* KR 컨센서스 숫자 카드 제거 (2026-07-10) — 권리감사 쟁점4(네이버 ToS + 증권사 리서치 이중 IP).
                컨센 접근 = 위 '애널리스트 컨센서스 · 출처 바로가기' 링크아웃 섹션이 담당. */}

            {/* 일정 */}
            {calendar.length > 0 && (
                <>
                    {sectionTitle("이 종목 일정")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        {calendar.map((c: any, i: number) => (
                            <div key={i} style={{ display: "flex", gap: 12, padding: "11px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}`, alignItems: "baseline" }}>
                                <span style={{ minWidth: 64, flexShrink: 0, fontSize: 12.5, fontWeight: 800, color: C.vg }}>{c.date || ""}</span>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: 13.5, fontWeight: 700 }}>{c.event}</div>
                                    {c.kind && <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 1 }}>{c.kind}</div>}
                                </div>
                            </div>
                        ))}
                    </div>
                </>
            )}

            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 16, lineHeight: 1.5 }}>
                전 종목 사실 · 등급·추천 아님 · 출처 DART·공정위·FnGuide·KRX·네이버 · 차트·시세 = TradingView 위젯·네이버 · 점수 held(2027)
            </div>
        </div>
    )
}

addPropertyControls(PublicStockReport, {
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: DEFAULT_URL },
    usStockUrl: { type: ControlType.String, title: "US Stock URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json" },
    usSmallcapUrl: { type: ControlType.String, title: "US Smallcap URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_us_smallcap.json" },
    flowUrl: { type: ControlType.String, title: "Flow URL", defaultValue: DEFAULT_FLOW },
    forensicsUrl: { type: ControlType.String, title: "Forensics URL", defaultValue: DEFAULT_FORENSICS },
    insiderUrl: { type: ControlType.String, title: "Insider URL", defaultValue: DEFAULT_INSIDER },
    warnUrl: { type: ControlType.String, title: "Warnings URL", defaultValue: DEFAULT_WARN },
    lendingUrl: { type: ControlType.String, title: "Lending URL", defaultValue: DEFAULT_LENDING },
    supplyUrl: { type: ControlType.String, title: "Supply/Demand URL", defaultValue: DEFAULT_SUPPLY },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
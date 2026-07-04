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
 * 관심종목 = 로그인 시 헤더 별(둥근 SVG, 2026-06-22 토스풍 라운드+소프트골드, 미담김도 회색 채움+외곽선) → /api/watchgroups(JWT) 담기/해제. 미로그인=담기 안내. 세션=verity_supabase_session(AlphaNestAuth).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968",
    faint: "#8b95a1", line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", upS: "#fff0f1", down: "#3182f6", downS: "#eef4ff",
    amber: "#ff9500", amberS: "#fff6e9", green: "#15c47e", greenS: "#eafaf3",
    vg: "#6c5ce7", vgS: "#f0edff", vt: "#6c5ce7", vtS: "#f0edff", tipBg: "#191f28", tipFg: "#ffffff", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1",
    faint: "#828d9b", line: "#252b34", grid: "#1e242c", up: "#f04452", upS: "#2a1a1d", down: "#5b9bff", downS: "#152031",
    amber: "#ff9500", amberS: "#2a2113", green: "#34e08a", greenS: "#0f241c",
    vg: "#a99bff", vgS: "#241f3a", vt: "#a99bff", vtS: "#241f3a", tipBg: "#222a33", tipFg: "#e3e7ec", onAccent: "#0f1318",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const HEAD = FONT
const LOGO_BASE = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
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
// 시세 컴플라이언스 — 실시간 시세·거래대금 상위 = 네이버 link-out(증권사 서빙 = 재배포 아님, 실시간·무료·합법)
const NAVER_QUANT = "https://finance.naver.com/sise/sise_quant.naver"
const M_NAVER_QUANT = "https://m.stock.naver.com/sise/trade"
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
        forensics_flags: { correction_count: 1, correction_pct: 33, dilution_12m: 0, dilution_span: "" },
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
    const ch = (String(name || "?").trim().charAt(0)) || "?"
    const code = flagCode(market)
    const fsize = Math.round(size * 0.46)
    return (
        <span style={{ position: "relative", width: size, height: size, flexShrink: 0, display: "inline-block" }}>
            {!err && ticker ? (
                <img src={LOGO_BASE + String(ticker).replace(/-/g, ".") + ".png"} alt="" width={size} height={size}
                    onError={() => setErr(true)}
                    style={{ width: size, height: size, borderRadius: 11, objectFit: "cover", display: "block", background: C.bg }} />
            ) : (
                <span style={{ width: size, height: size, borderRadius: 11, background: C.vtS, color: C.vt, display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * 0.42), fontWeight: 800 }}>{ch}</span>
            )}
            {code && (
                <img src={FLAG_BASE + code + ".svg"} alt="" width={fsize} height={fsize}
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
function smoothLine(p: { x: number; y: number }[]): string {
    // 직선 꺾은선(선형) — 곡선 보간은 실측값 사이를 지어내는 인상 (PM 2026-07-04 '그래프 선형으로')
    if (!p.length) return ""
    if (p.length === 1) return `M ${p[0].x} ${p[0].y}`
    let d = `M ${p[0].x} ${p[0].y}`
    for (let i = 1; i < p.length; i++) {
        d += ` L ${p[i].x} ${p[i].y}`
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
    const linePath = smoothLine(defined)
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
    const marginPath = showMargin && mXY.length >= 2 ? smoothLine(mXY) : ""
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
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>{usd ? "SEC 10-K" : "DART 전자공시"} 연간 실값(추이선) · 증감은 위 과거 비교 칩(↑증가 ↓감소) · 점수·추천 아님</div>
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

function QuarterlyTrend({ ticker, C, isDark, showExtremes = true, quarterlyUrl = QT_DEFAULT_URL, maxQuarters = 40 }: { ticker: string; C: any; isDark: boolean; showExtremes?: boolean; quarterlyUrl?: string; maxQuarters?: number }) {
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
        fetch(quarterlyUrl, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((d) => {
            const rec = d && d.stocks && d.stocks[ticker]
            const arr = rec && Array.isArray(rec.quarters) ? rec.quarters : null
            if (alive && arr && arr.length) setQuarters(arr)
        }).catch(() => {})
        return () => { alive = false }
    }, [quarterlyUrl, ticker, onCanvas])
    const cap = Math.max(4, Math.min(40, maxQuarters || 20))
    const series = useMemo(() => [...quarters].sort((a, b) => String(a.q).localeCompare(String(b.q))).slice(-cap), [quarters, cap])
    const narrow = w > 0 && w < 420
    if (!onCanvas && series.length < 4) return null
    const CW = Math.max(80, (w || 360) - (narrow ? 28 : 36))
    const CH = 84, PX = 4, PY = 20   // PY 크게 = 최고/최저 라벨이 라인·상하단과 안 겹침
    return (
        <div ref={ref} style={{ background: C.card, borderRadius: 16, padding: narrow ? "15px 14px" : "17px 18px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.4px", color: C.ink }}>분기 재무 추이</span>
                <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>최근 {series.length}분기 · DART 분기보고서 · 사실</span>
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
                    const linePath = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")
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

export default function PublicStockReport(props: Props) {
    const { stockUrl, usStockUrl, usSmallcapUrl, flowUrl, forensicsUrl, insiderUrl, warnUrl, lendingUrl, supplyUrl, apiBase, dark } = props
    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    const C = (RenderTarget.current() === RenderTarget.canvas ? !!dark : themeDark) ? DARK : LIGHT
    useEffect(() => {
        if (RenderTarget.current() === RenderTarget.canvas) return
        const readTheme = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        readTheme()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(readTheme)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [])
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [list, setList] = useState<any[]>(SAMPLE)            // 리포트 DATA 보유 종목(facts/peer/flow)
    const [reportAsOf, setReportAsOf] = useState<string>("")   // stock_report_public _meta.generated_at — 신선도 사실 노출
    const [tocSecs, setTocSecs] = useState<string[]>([])       // 미니 목차 — 렌더된 섹션 헤더(data-sec) DOM 스캔 결과
    const [searchList, setSearchList] = useState<any[]>(SAMPLE) // 검색 universe(전 종목 KR+US, ticker/name)
    const [flowMap, setFlowMap] = useState<Record<string, any[]>>(SAMPLE_FLOW)
    const [forensicsMap, setForensicsMap] = useState<Record<string, any>>(SAMPLE_FORENSICS)
    const [insiderMap, setInsiderMap] = useState<Record<string, any>>(SAMPLE_INSIDER)
    const [warnMap, setWarnMap] = useState<Record<string, any>>(SAMPLE_WARN)
    const [lendingMap, setLendingMap] = useState<Record<string, any>>({})
    const [lendAsOf, setLendAsOf] = useState<string>("")
    const [supplyMap, setSupplyMap] = useState<Record<string, any>>({})
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
    const [forenAll, setForenAll] = useState(false)
    const [insiderAll, setInsiderAll] = useState(false)
    const [watchToken, setWatchToken] = useState("")
    const [watchGroupId, setWatchGroupId] = useState<string>("")
    const [starItemId, setStarItemId] = useState<any>(null)
    const [starBusy, setStarBusy] = useState(false)
    const [starHint, setStarHint] = useState(false)

    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    useEffect(() => {
        if (typeof window === "undefined" || !window.matchMedia) return
        try { setHoverCapable(window.matchMedia("(hover: hover) and (pointer: fine)").matches) } catch { /* keep default */ }
    }, [])

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

    useEffect(() => {
        if (onCanvas || !stockUrl) return
        let alive = true
        const urls = [stockUrl, usStockUrl, usSmallcapUrl].filter(Boolean)
        Promise.all(urls.map((u) => fetch(u, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null)))
            .then((docs) => {
                const arr: any[] = []
                for (const d of docs) { const a = d && (Array.isArray(d) ? d : d.stocks); if (Array.isArray(a)) arr.push(...(a as any[])) }
                if (!alive || !arr.length) return
                const ts = docs[0] && (docs[0] as any)._meta && (docs[0] as any)._meta.generated_at
                if (ts) setReportAsOf(String(ts))
                // ticker dedup — smallcap 트랙(us_stock_report_us_smallcap) ∩ sp600 중복. 먼저 등장(sp1500) 우선.
                const seen = new Set<string>()
                const deduped = arr.filter((s: any) => { const tk = String(s.ticker || ""); if (!tk || seen.has(tk)) return false; seen.add(tk); return true })
                setList(deduped); setListLoaded(true)
                let initT = deduped[0].ticker
                if (typeof window !== "undefined") {
                    let qp = (new URLSearchParams(window.location.search).get("q") || "").trim().toLowerCase()
                    if (!qp) { try { qp = (window.localStorage.getItem("verity_last_ticker") || "").trim().toLowerCase() } catch (e) {} }
                    if (qp) {
                        const hit = deduped.find((x: any) => String(x.ticker).toLowerCase() === qp || String(x.name || "").toLowerCase() === qp || String(x.name_ko || "") === qp)
                            || deduped.find((x: any) => String(x.ticker).toLowerCase().includes(qp) || String(x.name || "").toLowerCase().includes(qp) || String(x.name_ko || "").includes(qp))
                        if (hit) initT = hit.ticker
                    }
                }
                try { window.localStorage.setItem("verity_last_ticker", String(initT)) } catch (e) {}
                setSelTicker(initT)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [stockUrl, usStockUrl, usSmallcapUrl, onCanvas])

    /* 검색 universe 로드 — 통합 universe_search.json(전 종목 KR+US). 리포트 DATA(list)와 별개. */
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(UNIVERSE_URL, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null))
            .then((d) => { const a = d && (Array.isArray(d) ? d : d.stocks); if (alive && Array.isArray(a) && a.length) setSearchList(a) })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas || !flowUrl) return
        let alive = true
        fetch(flowUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { const fm = d && (d.flows || d); if (alive && fm && typeof fm === "object") setFlowMap(fm) })
            .catch(() => {})
        return () => { alive = false }
    }, [flowUrl, onCanvas])

    // 대차잔고(공매도 압력 proxy) — top200, stocks 배열 → ticker 맵. 미보유 종목은 graceful 미표시.
    useEffect(() => {
        const url = lendingUrl || DEFAULT_LENDING
        if (onCanvas || !url) return
        let alive = true
        fetch(url, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d || !Array.isArray(d.stocks)) return
                const m: Record<string, any> = {}
                for (const row of d.stocks) { if (row && row.ticker) m[String(row.ticker)] = row }
                setLendingMap(m)
                setLendAsOf((d._meta && d._meta.as_of) || "")
            })
            .catch(() => {})
        return () => { alive = false }
    }, [lendingUrl, onCanvas])

    // 수급 종합(공매도·신용잔고) — supply_demand.json (stocks 맵). 스냅샷 universe만, 미보유 graceful.
    useEffect(() => {
        const url = supplyUrl || DEFAULT_SUPPLY
        if (onCanvas || !url) return
        let alive = true
        fetch(url, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { const m = d && (d.stocks || d); if (alive && m && typeof m === "object") setSupplyMap(m) })
            .catch(() => {})
        return () => { alive = false }
    }, [supplyUrl, onCanvas])

    useEffect(() => {
        if (onCanvas || !forensicsUrl) return
        let alive = true
        fetch(forensicsUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const arr = d && (Array.isArray(d) ? d : d.stocks)
                if (!alive || !Array.isArray(arr)) return
                const m: Record<string, any> = {}
                for (const x of arr) { if (x && x.ticker) m[String(x.ticker)] = x }
                setForensicsMap(m)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [forensicsUrl, onCanvas])

    useEffect(() => {
        if (onCanvas || !insiderUrl) return
        let alive = true
        fetch(insiderUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const arr = d && (Array.isArray(d) ? d : d.stocks)
                if (!alive || !Array.isArray(arr)) return
                const m: Record<string, any> = {}
                for (const x of arr) { if (x && x.ticker) m[String(x.ticker)] = x }
                setInsiderMap(m)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [insiderUrl, onCanvas])

    useEffect(() => {
        if (onCanvas || !warnUrl) return
        let alive = true
        fetch(warnUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { const wm = d && (d.warnings || d); if (alive && wm && typeof wm === "object") setWarnMap(wm) })
            .catch(() => {})
        return () => { alive = false }
    }, [warnUrl, onCanvas])

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
        if (hit) return hit
        // 리포트 미보유 종목 = universe stub(올바른 ticker/name) — list[0] 엉뚱 종목 폴백 차단. _noReport=graceful 안내.
        const u = searchList.find((x) => String(x.ticker) === String(selTicker))
        if (u) return { ticker: u.ticker, name: u.name, market: u.market, _noReport: true }
        return list[0] || {}
    }, [list, searchList, selTicker])
    // 로딩 중(실데이터 미도착 or 선택 종목 미발견)엔 삼성전자 샘플 폴백 대신 스켈레톤. 160ms 지연 게이트=즉시 로드 깜빡임 차단(토스식).
    const found = useMemo(() => list.some((x) => String(x.ticker) === String(selTicker)), [list, selTicker])
    const showSkeleton = !onCanvas && (!listLoaded || !found)
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
        return searchList.filter((x) => String(x.name || "").toLowerCase().includes(q) || String(x.ticker || "").toLowerCase().includes(q) || String(x.name_ko || "").includes(q)).slice(0, 15)
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
        if (consensus && consensus.opinion) f.push("컨센 " + consensus.opinion)
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

    if (showSkeleton) {
        return (
            <div ref={rootRef} style={wrap}>
                {skelVisible && <StockReportSkeleton C={C} isDark={C === DARK} narrow={narrow} />}
            </div>
        )
    }

    return (
        <div ref={rootRef} style={wrap}>
            {/* 검색 — 공시 페이지와 동일 토스식 borderless 채움 (돋보기 아이콘 + 클리어 ×) */}
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
                                <div key={m.ticker} onMouseDown={() => goTicker(m.ticker, m.name)}
                                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 9, cursor: "pointer" }}>
                                    <Logo ticker={m.ticker} name={m.name} market={m.market} C={C} size={22} />
                                    <span style={{ fontFamily: HEAD, fontSize: 13.5, fontWeight: 700, color: C.ink }}>{m.name}</span>
                                    {m.name_ko && <span style={{ fontSize: 12, color: C.sub, fontWeight: 600 }}>{m.name_ko}</span>}
                                    <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginLeft: "auto" }}>{m.ticker} · {m.market}</span>
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
                                                <Logo ticker={r.t} name={r.n} market={/^\d{6}$/.test(String(r.t)) ? "KOSPI" : "US"} C={C} size={22} />
                                                <span style={{ fontFamily: HEAD, fontSize: 13.5, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.n}</span>
                                                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginLeft: "auto" }}>{r.t}</span>
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
                        <svg width={18} height={18} viewBox="0 0 24 24" fill={starItemId ? "#f6b93b" : C.line} stroke={starItemId ? "#f6b93b" : C.faint} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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
                {(header || consensus.target_price) && (
                    <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 9 }}>
                        {header && header.range_52w && metaItem("52주", header.range_52w)}
                        {header && header.trading_value && metaItem("거래대금", header.trading_value)}
                        {header && header.market_cap && metaItem("시총", header.market_cap)}
                        {consensus.target_price && metaItem("컨센 목표가", consensus.target_price, true, C.vt)}
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
                            대차잔고 = 시장에 빌려준 주식(공매도 재료·압력 proxy). 진짜 공매도 잔고 아님 · 외부 사실, 자체 신호 아님{lendAsOf ? " · " + dateDot(lendAsOf) : ""}
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
                            공매도 비중·신용잔고 = 외부 사실(KRX·KIS) · 자체 신호 아님
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
                                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>출처 · DART·KRX 공식 사실 · 자체 등급·점수 아님</div>
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
                    <div style={{ background: C.card, borderRadius: 16, padding: "6px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
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
                                    <div onClick={() => setOpenPeer(opened ? -1 : i)} style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 0", cursor: "pointer" }}>
                                        <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: C.sub, fontWeight: 600 }}>{r.key}</span>
                                        <span style={{ flexShrink: 0, fontSize: 14, fontWeight: 800, color: C.ink, minWidth: 56, textAlign: "right" }}>{r.value}</span>
                                        <span style={{ flexShrink: 0, fontSize: 11.5, color: C.faint, fontWeight: 600, minWidth: 70, textAlign: "right" }}>업종 {r.median}</span>
                                        <span style={{ flexShrink: 0, width: 16, textAlign: "center", fontSize: 13, fontWeight: 800, color: C.vt }}>{r.vs === "above" ? "↑" : r.vs === "below" ? "↓" : "="}</span>
                                    </div>
                                    {opened && (
                                        <div style={{ padding: "2px 0 12px", display: "flex", flexDirection: "column", gap: 5 }}>
                                            <div style={{ fontSize: 12.5, fontWeight: 700, color: C.ink, lineHeight: 1.5 }}>
                                                {r.key} {r.value} · {peer.sector} 중앙값 {r.median} (N={peer.n}) → <span style={{ color: C.vt }}>{dir}</span>
                                            </div>
                                            {r.pct != null && (
                                                <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 1 }}>
                                                    <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 700 }}>동종 분포 백분위 {r.pct} <span style={{ color: C.faint, fontWeight: 600 }}>(이 값보다 낮은 동종 {r.pct}%)</span></div>
                                                    <div style={{ position: "relative", height: 6, background: C.bg, borderRadius: 3 }}>
                                                        <div style={{ position: "absolute", left: `calc(${Math.max(0, Math.min(100, r.pct))}% - 3px)`, top: -2, width: 6, height: 10, borderRadius: 2, background: C.vt }} />
                                                    </div>
                                                </div>
                                            )}
                                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>같은 섹터 종목 중앙값·분포와의 사실 비교 — 높다·낮다가 좋다·나쁘다는 아님(판단 X)</div>
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>{peer.note}</div>
                    </div>
                </>
            )}

            {/* 분기 재무 추이 — 한눈 파악 먼저(재무 요약 위). 선형 차트 + 최고/최저점.
                실데이터(dart_quarterly_public.json) 없으면 자동 숨김(RULE 7). 캔버스=SAMPLE. */}
            <div style={{ marginTop: 12 }}>
                <QuarterlyTrend ticker={s.ticker} C={C} isDark={C === DARK} quarterlyUrl={/^\d{6}$/.test(String(s.ticker)) ? QT_DEFAULT_URL : QT_US_URL} />
            </div>

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

            {/* 재무 추이 — 연도별 매출·영업이익·순익 + 과거 비교 (DART 공시 실값) */}
            {Array.isArray(s.fin_series) && s.fin_series.length >= 2 && (
                <>
                    {sectionTitle("재무 추이", (/^\d{6}$/.test(String(s.ticker || "")) ? "DART" : "SEC 10-K") + " · 연간 실값 · 과거(1·3·5년) 비교")}
                    <FinTrend series={s.fin_series} C={C} usd={!/^\d{6}$/.test(String(s.ticker || ""))} />
                </>
            )}

            {/* 공시·리스크 레이더 */}
            {disclosures.length > 0 && (
                <>
                    {sectionTitle("공시·리스크 레이더", "사실 · 탭=상세")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "6px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
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
                    <div style={{ background: C.card, borderRadius: 16, padding: "12px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
                            {Object.keys(foren.counts || {}).sort((a, b) => (foren.counts[b] - foren.counts[a])).map((cat) => (
                                <span key={cat} style={{ fontSize: 11.5, fontWeight: 800, color: catColor(cat), background: C.bg, border: `1px solid ${C.line}`, borderRadius: 8, padding: "4px 9px" }}>{cat} {foren.counts[cat]}회</span>
                            ))}
                        </div>
                        {foren.dilution_count > 0 && (<div style={{ fontSize: 12, color: C.amber, fontWeight: 700, marginTop: 9, lineHeight: 1.5 }}>희석성 공시(유상증자·CB·BW 등) 합 {foren.dilution_count}회 — 사실 빈도일 뿐, 위험 판단 아님</div>)}
                        {foren.forensics_flags && (foren.forensics_flags.dilution_12m > 0 || foren.forensics_flags.correction_count > 0) && (
                            <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginTop: 9 }}>
                                {foren.forensics_flags.dilution_12m > 0 && (
                                    <span style={{ fontSize: 11.5, fontWeight: 700, color: C.amber, background: C.bg, border: `1px solid ${C.line}`, borderRadius: 8, padding: "4px 9px" }}>최근 12개월 희석 {foren.forensics_flags.dilution_12m}회{foren.forensics_flags.dilution_span ? ` · ${foren.forensics_flags.dilution_span}` : ""}</span>
                                )}
                                {foren.forensics_flags.correction_count > 0 && (
                                    <span style={{ fontSize: 11.5, fontWeight: 700, color: C.sub, background: C.bg, border: `1px solid ${C.line}`, borderRadius: 8, padding: "4px 9px" }}>정정공시 {foren.forensics_flags.correction_count}회 ({foren.forensics_flags.correction_pct}%)</span>
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
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>DART 원문 제목 기준 이벤트 빈도(사실) — 자체 위험점수·등급 아님. 현재 수집창 한정(과거 백필 시 심화).</div>
                    </div>
                </>
            )}

            {/* 내부자 거래 */}
            {insider && insider.trades && insider.trades.length > 0 && (
                <>
                    {sectionTitle("내부자 거래 · 임원·주요주주", "DART · 美 Form4 KR판", "내부자")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "12px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "baseline" }}>
                            <span style={{ fontSize: 12.5, fontWeight: 800, color: C.up }}>매수 {insider.buy_n}건</span>
                            <span style={{ fontSize: 12.5, fontWeight: 800, color: C.down }}>매도 {insider.sell_n}건</span>
                            <span style={{ fontSize: 12.5, fontWeight: 800, color: (insider.net_change || 0) >= 0 ? C.up : C.down }}>순증감 {fmtShares(insider.net_change)}</span>
                        </div>
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
                                {usForen.insider.trades.slice(0, 6).map((t, i) => (
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
                                {usForen.holdings.filings.slice(0, 5).map((f, i) => (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "8px 0", borderTop: i === 0 ? "none" : "1px solid " + C.line, fontSize: 12.5 }}>
                                        <span style={{ color: C.sub, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.filer || "—"} <span style={{ color: C.faint }}>· {f.date}</span></span>
                                        <span style={{ fontWeight: 800, flexShrink: 0, color: String(f.type || "").indexOf("13D") === 0 ? C.amber : C.sub }}>{f.type}{f.pct != null ? " · " + f.pct + "%" : ""}</span>
                                    </div>
                                ))}
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>SEC 13D(행동주의)/13G(수동) 5%+ 공시 사실만 · 자체 신호 아님</div>
                            </div>
                        </>
                    )}

                    {usForen.smart_money && usForen.smart_money.holders && usForen.smart_money.holders.length > 0 && (
                        <>
                            {sectionTitle("美 스마트머니 · 13F", "집중형 액티브 펀드")}
                            <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                                <div style={{ fontSize: 12.5, fontWeight: 800, marginBottom: 10 }}>보유 펀드 {usForen.smart_money.holder_count || usForen.smart_money.holders.length}곳 <span style={{ color: C.faint, fontWeight: 600 }}>· 합산 ${((usForen.smart_money.total_value_usd || 0) / 1e9).toFixed(1)}B</span></div>
                                {usForen.smart_money.holders.slice(0, 6).map((h, i) => (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "8px 0", borderTop: i === 0 ? "none" : "1px solid " + C.line, fontSize: 12.5 }}>
                                        <span style={{ color: C.sub, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.fund}</span>
                                        <span style={{ flexShrink: 0, fontWeight: 800 }}><span style={{ color: (h.change_type === "NEW" || h.change_type === "INCREASED") ? C.green : h.change_type === "DECREASED" ? C.down : C.faint }}>{h.change_type}</span> <span style={{ color: C.faint, fontWeight: 600 }}>${((h.value_usd || 0) / 1e9).toFixed(1)}B</span></span>
                                    </div>
                                ))}
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>유명 집중형 펀드 13F 보유(분기말+45일 지연) · 인덱스펀드 제외 · 자체 점수 아님</div>
                            </div>
                        </>
                    )}

                    {usForen.consensus && (usForen.consensus.num_analysts || usForen.consensus.target_mean != null) && (
                        <>
                            {sectionTitle("美 애널리스트 컨센서스", "yfinance 집계")}
                            <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                                {tipKV("투자의견", String(usForen.consensus.rec_key || "—").replace(/_/g, " "), C.vt)}
                                {usForen.consensus.num_analysts != null && tipKV("애널리스트", usForen.consensus.num_analysts + "명")}
                                {usForen.consensus.target_mean != null && tipKV("평균 목표가", "$" + Number(usForen.consensus.target_mean).toLocaleString("en-US"))}
                                {usForen.consensus.upside_pct != null && tipKV("업사이드", (usForen.consensus.upside_pct >= 0 ? "+" : "") + usForen.consensus.upside_pct + "%", usForen.consensus.upside_pct >= 0 ? C.up : C.down)}
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>외부 애널리스트 집계 사실(yfinance) · 우리 자체 점수 아님</div>
                            </div>
                        </>
                    )}
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
                        <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginTop: 9 }}>{ownership.note}</div>
                        {ownership.source && <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 3 }}>{ownership.source} · 1차 출처(나무위키 아님)</div>}
                    </div>
                </>
            )}

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
                        {sectionTitle("AlphaNest 관측 — 분류 lens", "공개 재무에 룰 적용 · 점수·추천 아님")}
                        <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
                                <span style={{ fontSize: 12.5, fontWeight: 800, color: lc, background: lcS, borderRadius: 8, padding: "5px 11px", letterSpacing: "-0.2px" }}>{ln.label || ln.class}</span>
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
                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 11, lineHeight: 1.5 }}>{verityLens.note || "Peter Lynch 분류 룰을 공개 재무 사실에 적용한 관측 — 자체 점수·매매의견 아님."}</div>
                        </div>
                    </>
                )
            })()}

            {/* 컨센서스 */}
            {(consensus.target_price || consensus.opinion) && (
                <>
                    {sectionTitle("애널리스트 컨센서스", "집계 · AlphaNest 의견 아님")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "6px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        {[["목표주가 평균", consensus.target_price], ["투자의견", consensus.opinion], ["추정 EPS", consensus.eps]].map(([k, v]: any, i) => v ? kvRow(k, v, i) : null)}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, padding: "4px 0 10px", lineHeight: 1.5 }}>증권사 집계 사실 — 자체 등급·점수는 검증 후(2027) 공개</div>
                    </div>
                </>
            )}

            {/* 일정 */}
            {calendar.length > 0 && (
                <>
                    {sectionTitle("이 종목 일정")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "6px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
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

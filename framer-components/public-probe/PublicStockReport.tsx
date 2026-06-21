import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 종목 리포트 — VERITY 공개 터미널 (골든구스). 전 종목 검색→선택→리포트.
 * 데이터 = stock_report_public + flow_5d + disclosure_forensics + insider_trades + market_warnings (Blob). 가격/차트=/api 라이브.
 * 차트 = OHLCV 선(부드러운 곡선+그라데이션, 기본)/캔들 + 거래량 + MA + 기간 + 공시마커 + 라이브 틱(장중 6s) + 토스풍 호버 카드.
 * 시장경보 = 경보 시 헤더(종목명·가격·메타) 통째 틴트 박스(외곽선 없음)로 감싸 한눈에. 경보 없으면 헤더 평범.
 * 폰트 = Pretendard 단일. 탭→상세 = 기본지표(계산식+실제 투입숫자 facts_calc·출처)/수급(정확 주수)/동종업계(비교)/재무(전체 재무제표 그룹) + 공시·내부자·forensics(원문) — 전업러용 raw 접근. 있는 데이터만(RULE10).
 * 다크모드 = Framer 네이티브 토글(body[data-framer-theme]) 추종 — themeDark + MutationObserver. canvas 에선 dark prop. 사이트 다크모드 버튼과 실시간 연동.
 * 관심종목 = 로그인 시 헤더 ☆ → /api/watchgroups(JWT) 담기/해제. 미로그인=담기 안내. 세션=verity_supabase_session(GoldenGooseAuth).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968",
    faint: "#8b95a1", line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", upS: "#fff0f1", down: "#3182f6", downS: "#eef4ff",
    amber: "#ff9500", amberS: "#fff6e9", green: "#15c47e", greenS: "#eafaf3",
    vg: "#0ca678", vgS: "#e7faf0", vt: "#6c5ce7", vtS: "#f0edff", tipBg: "#191f28", tipFg: "#ffffff", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1",
    faint: "#828d9b", line: "#252b34", grid: "#1e242c", up: "#f04452", upS: "#2a1a1d", down: "#5b9bff", downS: "#152031",
    amber: "#ff9500", amberS: "#2a2113", green: "#34e08a", greenS: "#0f241c",
    vg: "#7fffa0", vgS: "#11281d", vt: "#a99bff", vtS: "#241f3a", tipBg: "#222a33", tipFg: "#e3e7ec", onAccent: "#0f1318",
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
    "컨센 목표가": "증권사들이 제시한 목표주가의 평균이에요. VERITY 자체 의견이 아니라 애널리스트 집계 사실이고, 자체 점수는 검증 후(2027) 공개해요.",
    "재무제표": "DART 전자공시 최근 결산 실값이에요. 손익(번 돈)·재무상태(가진 것/빚)·현금흐름(실제 현금 이동)·비율을 사실 그대로 보여줘요. 단년 기준이라 추이는 아직 없어요.",
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
const PERIODS = [{ l: "1M", n: 20 }, { l: "3M", n: 60 }, { l: "전체", n: 0 }]
const DILUTION_CATS = new Set(["유상증자", "전환사채(CB)", "신주인수권부사채(BW)", "교환사채(EB)", "자기주식처분"])
const RISK_CATS = new Set(["감자", "횡령·배임", "회생·상장폐지", "불성실공시"])
const FAVORABLE_CATS = new Set(["자기주식취득"])

interface Props {
    stockUrl: string
    flowUrl: string
    forensicsUrl: string
    insiderUrl: string
    warnUrl: string
    apiBase: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
const DEFAULT_FLOW = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_flow_5d.json"
const DEFAULT_FORENSICS = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/disclosure_forensics.json"
const DEFAULT_INSIDER = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/insider_trades.json"
const DEFAULT_WARN = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/market_warnings.json"
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
            rows: [{ key: "PER", value: "14.2", median: "18.3", vs: "below" }, { key: "PBR", value: "1.1", median: "1.6", vs: "below" }, { key: "ROE", value: "9.1%", median: "7.5%", vs: "above" }, { key: "부채비율", value: "38%", median: "52%", vs: "below" }, { key: "영업이익률", value: "14.3%", median: "8.1%", vs: "above" }],
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
        events: [
            { date: "2026-06-15", category: "자기주식취득", risk: "favorable", title: "주요사항보고서(자기주식취득결정)", is_correction: false, source_url: DART + "20260615000777" },
            { date: "2026-05-30", category: "정정공시", risk: "correction", title: "[기재정정]분기보고서", is_correction: true, source_url: DART + "20260530000111" },
        ],
    },
}
const SAMPLE_INSIDER: Record<string, any> = { "005930": SAMPLE[0].insider }
const SAMPLE_WARN: Record<string, any> = { "005930": SAMPLE[0].warnings }

function pctColor(p: number, C: any) {
    if (!isFinite(p)) return C.faint
    return p > 0 ? C.up : p < 0 ? C.down : C.faint
}
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
function wonStr(v: any): string {
    const x = Number(v)
    if (!isFinite(x)) return "—"
    return x.toLocaleString("en-US") + "원"
}
function fmtVol(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x <= 0) return "—"
    if (x >= 1e8) return (x / 1e8).toFixed(2) + "억주"
    if (x >= 1e4) return Math.round(x / 1e4).toLocaleString("en-US") + "만주"
    return Math.round(x).toLocaleString("en-US") + "주"
}
function isKROpen(): boolean {
    const d = new Date()
    const k = new Date(d.getTime() + (d.getTimezoneOffset() + 540) * 60000)
    const day = k.getDay()
    if (day === 0 || day === 6) return false
    const m = k.getHours() * 60 + k.getMinutes()
    return m >= 540 && m <= 930
}
// 토스풍 부드러운 곡선 — Catmull-Rom → cubic bezier path. pts=[{x,y}].
function smoothPath(pts: { x: number; y: number }[]): string {
    if (!pts || pts.length < 2) return ""
    if (pts.length === 2) return `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)} L ${pts[1].x.toFixed(1)} ${pts[1].y.toFixed(1)}`
    const t = 0.16
    let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`
    for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[i - 1] || pts[i]
        const p1 = pts[i]
        const p2 = pts[i + 1]
        const p3 = pts[i + 2] || p2
        const c1x = p1.x + (p2.x - p0.x) * t
        const c1y = p1.y + (p2.y - p0.y) * t
        const c2x = p2.x - (p3.x - p1.x) * t
        const c2y = p2.y - (p3.y - p1.y) * t
        d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`
    }
    return d
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
                <img src={LOGO_BASE + ticker + ".png"} alt="" width={size} height={size}
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

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicStockReport(props: Props) {
    const { stockUrl, flowUrl, forensicsUrl, insiderUrl, warnUrl, apiBase, dark } = props
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
    const svgRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [list, setList] = useState<any[]>(SAMPLE)
    const [flowMap, setFlowMap] = useState<Record<string, any[]>>(SAMPLE_FLOW)
    const [forensicsMap, setForensicsMap] = useState<Record<string, any>>(SAMPLE_FORENSICS)
    const [insiderMap, setInsiderMap] = useState<Record<string, any>>(SAMPLE_INSIDER)
    const [warnMap, setWarnMap] = useState<Record<string, any>>(SAMPLE_WARN)
    const [selTicker, setSelTicker] = useState<string>(SAMPLE[0].ticker)
    const [query, setQuery] = useState("")
    const [focused, setFocused] = useState(false)
    const [live, setLive] = useState<{ price?: number; chg?: number }>({})
    const [chart, setChart] = useState<any[]>([])
    const [openTip, setOpenTip] = useState<string>("")
    const [tipBox, setTipBox] = useState<{ left: number; width: number }>({ left: 0, width: 240 })
    const [hoverCapable, setHoverCapable] = useState(true)
    const [hoverIdx, setHoverIdx] = useState<number | null>(null)
    const [openDisc, setOpenDisc] = useState<number>(-1)
    const [openMetric, setOpenMetric] = useState<string>("")
    const [openFlow, setOpenFlow] = useState<number>(-1)
    const [openPeer, setOpenPeer] = useState<number>(-1)
    const [openFin, setOpenFin] = useState<boolean>(false)
    const [chartMode, setChartMode] = useState<string>("line")
    const [chartPeriod, setChartPeriod] = useState<number>(0)
    const [showMA, setShowMA] = useState<boolean>(true)
    const [forenAll, setForenAll] = useState(false)
    const [insiderAll, setInsiderAll] = useState(false)
    const [pulse, setPulse] = useState(0)
    const [watchToken, setWatchToken] = useState("")
    const [watchGroupId, setWatchGroupId] = useState<string>("")
    const [starItemId, setStarItemId] = useState<any>(null)
    const [starBusy, setStarBusy] = useState(false)
    const [starHint, setStarHint] = useState(false)

    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const marketOpen = !onCanvas && isKROpen()

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
        fetch(stockUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const arr = d && (Array.isArray(d) ? d : d.stocks)
                if (!alive || !Array.isArray(arr) || !arr.length) return
                setList(arr)
                let initT = arr[0].ticker
                if (typeof window !== "undefined") {
                    const qp = (new URLSearchParams(window.location.search).get("q") || "").trim().toLowerCase()
                    if (qp) {
                        const hit = arr.find((x: any) => String(x.ticker) === qp || String(x.name || "").toLowerCase() === qp)
                            || arr.find((x: any) => String(x.ticker).includes(qp) || String(x.name || "").toLowerCase().includes(qp))
                        if (hit) initT = hit.ticker
                    }
                }
                setSelTicker(initT)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [stockUrl, onCanvas])

    useEffect(() => {
        if (onCanvas || !flowUrl) return
        let alive = true
        fetch(flowUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { const fm = d && (d.flows || d); if (alive && fm && typeof fm === "object") setFlowMap(fm) })
            .catch(() => {})
        return () => { alive = false }
    }, [flowUrl, onCanvas])

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

    const s = useMemo(() => list.find((x) => x.ticker === selTicker) || list[0] || {}, [list, selTicker])

    useEffect(() => { setHoverIdx(null); setOpenDisc(-1); setOpenMetric(""); setOpenFlow(-1); setOpenPeer(-1); setOpenFin(false); setForenAll(false); setInsiderAll(false); setOpenTip("") }, [selTicker])

    // 가격 폴링 — live 헤더 + 마지막 차트 봉 갱신(장중 6s). 장외엔 1회(종가).
    useEffect(() => {
        if (onCanvas || !s.ticker) { setLive({}); return }
        let alive = true
        setLive({})
        const tick = () => {
            fetch(base + "/api/stock?q=" + encodeURIComponent(s.ticker) + "&market=kr")
                .then((r) => (r.ok ? r.json() : null))
                .then((d) => {
                    if (!alive || !d) return
                    const p = d.price ?? d.current_price ?? (d.stock && d.stock.price)
                    const ch = d.price_change_pct ?? d.change_pct
                    const px = Number(p)
                    if (p != null) setLive({ price: px, chg: ch != null ? Number(ch) : undefined })
                    if (isFinite(px) && px > 0) {
                        setPulse((n) => n + 1)
                        setChart((prev) => {
                            if (!prev.length) return prev
                            const next = prev.slice()
                            const last = { ...next[next.length - 1] }
                            last.close = px
                            last.high = Math.max(Number(last.high) || px, px)
                            last.low = Math.min(Number(last.low) || px, px)
                            next[next.length - 1] = last
                            return next
                        })
                    }
                })
                .catch(() => {})
        }
        tick()
        let timer: any = null
        if (isKROpen()) timer = setInterval(tick, 6000)
        return () => { alive = false; if (timer) clearInterval(timer) }
    }, [s.ticker, base, onCanvas])

    useEffect(() => {
        if (onCanvas || !s.ticker || !/^\d{6}$/.test(String(s.ticker))) { setChart([]); return }
        let alive = true
        setChart([])
        fetch(base + "/api/chart?ticker=" + s.ticker + "&type=daily")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const arr = d && Array.isArray(d.daily) ? d.daily : (Array.isArray(d) ? d : null)
                if (alive && Array.isArray(arr) && arr.length > 1) setChart(arr)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [s.ticker, base, onCanvas])

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

    const matches = useMemo(() => {
        const q = query.trim().toLowerCase()
        if (!q) return []
        return list.filter((x) => String(x.name || "").toLowerCase().includes(q) || String(x.ticker || "").includes(q)).slice(0, 15)
    }, [query, list])

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
    const ownership = s.ownership || {}
    const calendar = s.calendar || []
    const flowRows = useMemo(() => (flowMap && flowMap[s.ticker]) || [], [flowMap, s.ticker])
    const flowMax = useMemo(() => {
        let mx = 1
        for (const r of flowRows) mx = Math.max(mx, Math.abs(Number(r.foreign_net) || 0), Math.abs(Number(r.inst_net) || 0))
        return mx
    }, [flowRows])
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

    const cv = useMemo(() => {
        if (!chart || chart.length < 2) return null
        const all = chart
        const rows = chartPeriod > 0 && chartPeriod < all.length ? all.slice(all.length - chartPeriod) : all
        const n = rows.length
        if (n < 2) return null
        const closes = rows.map((c: any) => Number(c.close))
        const opens = rows.map((c: any) => Number(c.open != null ? c.open : c.close))
        const highs = rows.map((c: any) => Number(c.high != null ? c.high : c.close))
        const lows = rows.map((c: any) => Number(c.low != null ? c.low : c.close))
        const vols = rows.map((c: any) => Number(c.volume != null ? c.volume : 0))
        const pmin = Math.min(...lows.filter((x) => isFinite(x)))
        const pmax = Math.max(...highs.filter((x) => isFinite(x)))
        if (!isFinite(pmin) || !isFinite(pmax)) return null
        const prng = (pmax - pmin) || 1
        const W = Math.max(240, (w || 360) - 2 * pad - 28)
        const Hp = narrow ? 130 : 150
        const Hv = 34
        const gap = 10
        const H = Hp + gap + Hv
        const padT = 8, padB = 4
        const xAt = (i: number) => (n === 1 ? W / 2 : (i / (n - 1)) * W)
        const yP = (v: number) => padT + (Hp - padT - padB) - ((v - pmin) / prng) * (Hp - padT - padB)
        const vmax = Math.max(1, ...vols.filter((x) => isFinite(x)))
        const yVtop = Hp + gap
        const pts = rows.map((c: any, i: number) => ({ x: xAt(i), y: yP(closes[i]) }))
        const linePath = smoothPath(pts)
        const areaPath = linePath ? `${linePath} L ${W.toFixed(1)} ${(Hp - padB).toFixed(1)} L 0 ${(Hp - padB).toFixed(1)} Z` : ""
        const up = closes[n - 1] >= closes[0]
        const maAt = (p2: number) => {
            const out: (number | null)[] = []
            for (let i = 0; i < n; i++) {
                if (i < p2 - 1) { out.push(null); continue }
                let sm = 0
                for (let j = i - p2 + 1; j <= i; j++) sm += closes[j]
                out.push(sm / p2)
            }
            return out
        }
        const maPath = (arr: (number | null)[] | null) => { if (!arr) return ""; const pts: { x: number; y: number }[] = []; for (let i = 0; i < arr.length; i++) { const vv = arr[i]; if (vv != null) pts.push({ x: xAt(i), y: yP(vv) }) } return smoothPath(pts) }
        const ma20Pts = n >= 20 ? maPath(maAt(20)) : ""
        const ma60Pts = n >= 60 ? maPath(maAt(60)) : ""
        const cw = Math.max(1.2, (W / n) * 0.62)
        const candles = rows.map((c: any, i: number) => {
            const upDay = closes[i] >= opens[i]
            return { x: xAt(i), oy: yP(opens[i]), cy: yP(closes[i]), hy: yP(highs[i]), ly: yP(lows[i]), upDay }
        })
        const volBars = rows.map((c: any, i: number) => {
            const upDay = closes[i] >= opens[i]
            const bh = (vols[i] / vmax) * Hv
            return { x: xAt(i), top: yVtop + (Hv - bh), h: Math.max(0.5, bh), upDay }
        })
        const dates = rows.map((c: any) => String(c.date))
        const markers = (disclosures || []).map((d: any, di: number) => {
            const dd = String(d.date || "").replace(/-/g, "")
            if (!dd) return null
            const idx = dates.findIndex((x: string) => x >= dd)
            if (idx < 0) return null
            return { x: xAt(idx), y: yP(closes[idx]), corr: !!d.is_correction, di }
        }).filter(Boolean) as any[]
        const tickIdx = [0, Math.round((n - 1) / 3), Math.round((2 * (n - 1)) / 3), n - 1]
        return { rows, n, W, H, Hp, Hv, gap, yVtop, pmin, pmax, xAt, yP, linePath, areaPath, up, ma20Pts, ma60Pts, candles, volBars, cw, dates, markers, tickIdx }
    }, [chart, disclosures, w, pad, narrow, chartPeriod])

    const setHoverFromClientX = (clientX: number) => {
        if (!cv || !svgRef.current) return
        const rect = svgRef.current.getBoundingClientRect()
        if (rect.width <= 0) return
        let rel = (clientX - rect.left) / rect.width
        rel = Math.max(0, Math.min(1, rel))
        setHoverIdx(Math.round(rel * (cv.n - 1)))
    }

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

    const sectionTitle = (t: string, sub?: string, infoKey?: string) => (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "18px 2px 8px" }}>
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
    const segBtn = (active: boolean): CSSProperties => ({
        border: "none", cursor: "pointer", padding: "5px 10px", borderRadius: 8, fontSize: 11.5, fontWeight: 800,
        fontFamily: FONT, background: active ? C.card : "transparent", color: active ? C.vg : C.sub, boxShadow: active ? "0 1px 2px rgba(0,0,0,0.18)" : "none",
    })
    const sevC = (sev: string) => sev === "danger" ? { fg: C.up, bg: C.upS } : sev === "warn" ? { fg: C.amber, bg: C.amberS } : { fg: C.sub, bg: C.bg }
    const tipKV = (label: string, value: any, color?: string) => (
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, padding: "3px 0" }}>
            <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{label}</span>
            <span style={{ fontSize: 12, color: color || C.ink, fontWeight: 800 }}>{value}</span>
        </div>
    )

    const inputStyle: CSSProperties = {
        width: "100%", border: `1px solid ${C.line}`, borderRadius: 12, padding: "11px 14px",
        fontSize: 14, fontFamily: FONT, background: C.card, color: C.ink, outline: "none", boxSizing: "border-box",
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

    const catColor = (cat: string) => DILUTION_CATS.has(cat) ? C.amber : RISK_CATS.has(cat) ? C.up : FAVORABLE_CATS.has(cat) ? C.vg : cat === "정정공시" ? C.faint : C.sub
    const shTypeColor = (t: string) => (t === "동일인" || t === "친족") ? C.vt : t === "소속회사" ? C.down : (t === "자기주식" || t === "기타") ? C.faint : C.sub
    const finValColor = (v: any) => (typeof v === "string" && v.trim().charAt(0) === "−") ? C.down : C.ink

    const hoverRow = hoverIdx != null && cv && hoverIdx >= 0 && hoverIdx < cv.n ? cv.rows[hoverIdx] : null
    const hoverX = hoverRow && cv ? cv.xAt(hoverIdx as number) : 0
    const hovPrevClose = (hoverRow && cv && (hoverIdx as number) > 0) ? Number(cv.rows[(hoverIdx as number) - 1].close) : (hoverRow ? Number(hoverRow.open) : NaN)
    const hovChg = (hoverRow && isFinite(hovPrevClose) && hovPrevClose > 0) ? ((Number(hoverRow.close) - hovPrevClose) / hovPrevClose) * 100 : null
    const cardFlip = (cv && hoverIdx != null) ? (hoverIdx as number) > cv.n * 0.5 : false

    // 토스풍 경보 — 심각도별 부드러운 틴트 배경만(외곽선 없음). 경보 시 헤더 통째 감쌈.
    const warnTint = warnTop === "danger" ? C.upS : warnTop === "warn" ? C.amberS : C.card
    const warnAccent = warnTop === "danger" ? C.up : warnTop === "warn" ? C.amber : C.sub
    const headerBox: CSSProperties = warnTop
        ? { marginTop: 14, background: warnTint, borderRadius: 18, padding: narrow ? "13px 14px" : "15px 17px" }
        : { marginTop: 14, paddingLeft: narrow ? 14 : 17 }

    return (
        <div ref={rootRef} style={wrap}>
            {/* 검색 */}
            <div style={{ position: "relative" }}>
                <input style={inputStyle} placeholder={`종목 검색 (이름·코드) · 전 종목 ${list.length}개`}
                    value={query} onChange={(e) => setQuery(e.target.value)}
                    onFocus={() => setFocused(true)} onBlur={() => setTimeout(() => setFocused(false), 150)} />
                {focused && matches.length > 0 && (
                    <div style={{
                        position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 60,
                        background: C.card, borderRadius: 12, boxShadow: "0 10px 30px rgba(0,0,0,0.14)",
                        padding: 6, maxHeight: 320, overflowY: "auto",
                    }}>
                        {matches.map((m) => (
                            <div key={m.ticker}
                                onMouseDown={() => { setSelTicker(m.ticker); setQuery(""); setFocused(false) }}
                                style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "9px 10px", borderRadius: 9, cursor: "pointer" }}>
                                <span style={{ fontFamily: HEAD, fontSize: 13.5, fontWeight: 700, color: C.ink }}>{m.name}</span>
                                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{m.ticker} · {m.market}</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* 헤더 (경보 시 종목명까지 감싸는 토스풍 틴트 박스 — 외곽선 없음) */}
            <div style={headerBox}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <Logo ticker={s.ticker} name={s.name} market={s.market} C={C} size={narrow ? 28 : 32} />
                    <span style={{ fontFamily: HEAD, fontSize: 23, fontWeight: 800, letterSpacing: "-0.6px" }}>{s.name}</span>
                    <span style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>{s.ticker} · {s.market}</span>
                    <button onClick={toggleStar} title={starItemId ? "관심종목 해제" : "관심종목 담기"} disabled={starBusy}
                        style={{ flexShrink: 0, border: "none", background: "transparent", cursor: starBusy ? "default" : "pointer", fontSize: 20, lineHeight: 1, padding: "2px 4px", color: starItemId ? "#ffb800" : C.faint }}>
                        {starItemId ? "★" : "☆"}
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
                {live.price != null && (
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 6 }}>
                        <span style={{ fontFamily: HEAD, fontSize: 25, fontWeight: 800, letterSpacing: "-0.8px" }}>{Number(live.price).toLocaleString()}원</span>
                        {live.chg != null && isFinite(live.chg) && (
                            <span style={{ fontSize: 13, fontWeight: 800, color: pctColor(Number(live.chg), C) }}>
                                {(live.chg > 0 ? "+" : "") + live.chg.toFixed(2)}%
                            </span>
                        )}
                        <span style={{ fontSize: 11, fontWeight: 800, color: marketOpen ? C.green : C.faint, display: "inline-flex", alignItems: "center", gap: 4 }}>
                            <span style={{ width: 6, height: 6, borderRadius: "50%", background: marketOpen ? C.green : C.faint, display: "inline-block", opacity: marketOpen ? (pulse % 2 ? 1 : 0.4) : 1, transition: "opacity 0.4s" }} />
                            {marketOpen ? "장중" : "장 마감"}
                        </span>
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

            {/* 연결된 차트 (선=부드러운 곡선+그라데이션 기본 / 캔들 + 라이브 틱 + 토스풍 호버 카드) */}
            {cv && (
                <div style={{ background: C.card, borderRadius: 16, padding: "12px 14px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                        <div style={{ display: "flex", gap: 4, background: C.bg, borderRadius: 10, padding: 3 }}>
                            {PERIODS.map((p) => (<button key={p.l} onClick={() => setChartPeriod(p.n)} style={segBtn(chartPeriod === p.n)}>{p.l}</button>))}
                        </div>
                        <div style={{ display: "flex", gap: 4, background: C.bg, borderRadius: 10, padding: 3 }}>
                            <button onClick={() => setChartMode("line")} style={segBtn(chartMode === "line")}>선</button>
                            <button onClick={() => setChartMode("candle")} style={segBtn(chartMode === "candle")}>캔들</button>
                        </div>
                        <button onClick={() => setShowMA((v) => !v)} style={segBtn(showMA)}>이평선</button>
                        <span style={{ marginLeft: "auto", fontSize: 10.5, fontWeight: 800, color: marketOpen ? C.green : C.faint, display: "inline-flex", alignItems: "center", gap: 4 }}>
                            <span style={{ width: 6, height: 6, borderRadius: "50%", background: marketOpen ? C.green : C.faint, display: "inline-block", opacity: marketOpen ? (pulse % 2 ? 1 : 0.4) : 1, transition: "opacity 0.4s" }} />
                            {marketOpen ? "장중 시세" : "장 마감·종가"}
                        </span>
                    </div>
                    <div style={{ minHeight: 16, marginBottom: 2 }}>
                        <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>차트 위 커서·터치 → 그날 시·고·저·종가·거래량·등락률</span>
                    </div>
                    <div ref={svgRef} style={{ position: "relative", width: "100%", touchAction: "pan-y" }}
                        onMouseMove={(e) => setHoverFromClientX(e.clientX)}
                        onMouseLeave={() => setHoverIdx(null)}
                        onTouchStart={(e) => { if (e.touches[0]) setHoverFromClientX(e.touches[0].clientX) }}
                        onTouchMove={(e) => { if (e.touches[0]) setHoverFromClientX(e.touches[0].clientX) }}>
                        <svg viewBox={`0 0 ${cv.W} ${cv.H}`} width="100%" height={cv.H} preserveAspectRatio="none" style={{ display: "block" }}>
                            <defs>
                                <linearGradient id="psr-area" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={cv.up ? C.up : C.down} stopOpacity={0.26} />
                                    <stop offset="100%" stopColor={cv.up ? C.up : C.down} stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <line x1={0} y1={cv.yP(cv.pmax)} x2={cv.W} y2={cv.yP(cv.pmax)} stroke={C.grid} strokeWidth={1} />
                            <line x1={0} y1={cv.yP(cv.pmin)} x2={cv.W} y2={cv.yP(cv.pmin)} stroke={C.grid} strokeWidth={1} />
                            {cv.volBars.map((b: any, i: number) => (<rect key={"v" + i} x={b.x - cv.cw / 2} y={b.top} width={cv.cw} height={b.h} fill={b.upDay ? C.up : C.down} fillOpacity={0.5} />))}
                            {chartMode === "candle" ? (
                                cv.candles.map((cd: any, i: number) => {
                                    const bodyTop = Math.min(cd.oy, cd.cy)
                                    const bodyH = Math.max(0.8, Math.abs(cd.oy - cd.cy))
                                    const col = cd.upDay ? C.up : C.down
                                    return (
                                        <g key={"c" + i}>
                                            <line x1={cd.x} y1={cd.hy} x2={cd.x} y2={cd.ly} stroke={col} strokeWidth={1} vectorEffect="non-scaling-stroke" />
                                            <rect x={cd.x - cv.cw / 2} y={bodyTop} width={Math.max(1, cv.cw)} height={bodyH} fill={col} />
                                        </g>
                                    )
                                })
                            ) : (
                                <>
                                    <path d={cv.areaPath} fill="url(#psr-area)" stroke="none" />
                                    <path d={cv.linePath} fill="none" stroke={cv.up ? C.up : C.down} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                                </>
                            )}
                            {showMA && cv.ma20Pts && <path d={cv.ma20Pts} fill="none" stroke={C.amber} strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />}
                            {showMA && cv.ma60Pts && <path d={cv.ma60Pts} fill="none" stroke={C.vt} strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />}
                            {cv.markers.map((m: any, i: number) => (<circle key={"m" + i} cx={m.x} cy={m.y} r={4.5} fill={m.corr ? C.amber : C.vt} stroke={C.card} strokeWidth={1.5} style={{ cursor: "pointer" }} onClick={() => setOpenDisc(m.di)} />))}
                            {hoverRow && (
                                <>
                                    <line x1={hoverX} y1={0} x2={hoverX} y2={cv.H} stroke={C.faint} strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
                                    <circle cx={hoverX} cy={cv.yP(Number(hoverRow.close))} r={4} fill={cv.up ? C.up : C.down} stroke={C.card} strokeWidth={1.5} />
                                </>
                            )}
                        </svg>
                        <span style={{ position: "absolute", top: 2, right: 2, fontSize: 10, fontWeight: 700, color: C.faint, background: C.card, padding: "0 3px", borderRadius: 4 }}>{Number(cv.pmax).toLocaleString()}</span>
                        <span style={{ position: "absolute", top: (cv.Hp - 14) + "px", right: 2, fontSize: 10, fontWeight: 700, color: C.faint, background: C.card, padding: "0 3px", borderRadius: 4 }}>{Number(cv.pmin).toLocaleString()}</span>
                        <span style={{ position: "absolute", bottom: 1, left: 2, fontSize: 9.5, fontWeight: 700, color: C.faint }}>거래량</span>

                        {hoverRow && (
                            <div style={{
                                position: "absolute", top: 4, left: (hoverX / cv.W) * 100 + "%",
                                transform: cardFlip ? "translateX(calc(-100% - 12px))" : "translateX(12px)",
                                background: C.card, border: `1px solid ${C.line}`, borderRadius: 12,
                                boxShadow: "0 8px 24px rgba(0,0,0,0.14)", padding: "10px 13px", minWidth: 166,
                                zIndex: 30, pointerEvents: "none",
                            }}>
                                <div style={{ fontFamily: HEAD, fontSize: 13, fontWeight: 800, color: C.ink, marginBottom: 6, letterSpacing: "-0.2px" }}>{dateDot(hoverRow.date)}</div>
                                {tipKV("시작", wonStr(hoverRow.open != null ? hoverRow.open : hoverRow.close))}
                                {tipKV("마지막", wonStr(hoverRow.close))}
                                {tipKV("최고", wonStr(hoverRow.high != null ? hoverRow.high : hoverRow.close), C.up)}
                                {tipKV("최저", wonStr(hoverRow.low != null ? hoverRow.low : hoverRow.close), C.down)}
                                {tipKV("거래량", fmtVol(hoverRow.volume))}
                                {hovChg != null && tipKV("등락률", (hovChg > 0 ? "+" : "") + hovChg.toFixed(2) + "%", hovChg > 0 ? C.up : hovChg < 0 ? C.down : C.faint)}
                            </div>
                        )}
                    </div>
                    <div style={{ position: "relative", height: 14, marginTop: 2 }}>
                        {cv.tickIdx.map((ti: number, i: number) => {
                            const lp = (cv.xAt(ti) / cv.W) * 100
                            const tf = i === 0 ? "translateX(0)" : i === cv.tickIdx.length - 1 ? "translateX(-100%)" : "translateX(-50%)"
                            return (<span key={i} style={{ position: "absolute", left: lp + "%", transform: tf, fontSize: 10, fontWeight: 600, color: C.faint, whiteSpace: "nowrap" }}>{mmdd(cv.dates[ti])}</span>)
                        })}
                    </div>
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 10, display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
                        {chartMode === "candle" && <span style={{ color: C.up }}>■ 양봉</span>}
                        {chartMode === "candle" && <span style={{ color: C.down }}>■ 음봉</span>}
                        <span style={{ color: C.vt }}>● 공시</span>
                        <span style={{ color: C.amber }}>● 정정</span>
                        {showMA && cv.ma20Pts && <span style={{ color: C.amber }}>— MA20</span>}
                        {showMA && cv.ma60Pts && <span style={{ color: C.vt }}>— MA60</span>}
                        <span>마커 누르면 해당 공시 · {cv.n}일 · {marketOpen ? "장중 갱신" : "종가"}</span>
                    </div>
                </div>
            )}

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
                                    {fnote[k] && <div style={{ fontSize: 11, color: C.sub, fontWeight: 600 }}>{fnote[k]}</div>}
                                    {opened && (
                                        <div style={{ marginTop: 9, paddingTop: 9, borderTop: `1px solid ${C.line}`, display: "flex", flexDirection: "column", gap: 6 }}>
                                            {INFO[k] && <div style={{ fontSize: 12, color: C.sub, fontWeight: 600, lineHeight: 1.5 }}>{INFO[k]}</div>}
                                            {METRIC_FORMULA[k] && (
                                                <div style={{ fontSize: 11.5, fontWeight: 700, color: C.vt, lineHeight: 1.45 }}>
                                                    계산 · {METRIC_FORMULA[k]}{fnote[k] === "자체계산" ? " (VERITY 직접 계산)" : ""}
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
                                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>같은 섹터 종목 중앙값과의 사실 비교 — 높다·낮다가 좋다·나쁘다는 아님(판단 X)</div>
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>{peer.note}</div>
                    </div>
                </>
            )}

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
                                {ownership.shareholders.map((sh: any, i: number) => (
                                    <div key={i} style={{ padding: "7px 0", borderTop: i === 0 ? `1px solid ${C.line}` : "none" }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                            <span style={{ flexShrink: 0, fontSize: 10.5, fontWeight: 800, color: shTypeColor(sh.type), background: C.bg, borderRadius: 6, padding: "2px 7px", minWidth: 52, textAlign: "center" }}>{sh.type}</span>
                                            <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, color: C.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sh.name && sh.name !== sh.type ? sh.name : ""}</span>
                                            <span style={{ flexShrink: 0, fontSize: 12.5, fontWeight: 800, color: C.ink }}>{sh.pct}%</span>
                                        </div>
                                        <div style={{ height: 3, borderRadius: 2, background: C.line, marginTop: 4, overflow: "hidden" }}>
                                            <div style={{ width: Math.min(100, Number(sh.pct) || 0) + "%", height: "100%", background: shTypeColor(sh.type) }} />
                                        </div>
                                    </div>
                                ))}
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
                                    <span style={{ fontWeight: 800, color: ownership.cross_check.status === "match" ? C.vg : C.amber }}>{ownership.cross_check.status === "match" ? "일치" : ownership.cross_check.status === "approx" ? "근사" : "차이"}</span>
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

            {/* 컨센서스 */}
            {(consensus.target_price || consensus.opinion) && (
                <>
                    {sectionTitle("애널리스트 컨센서스", "집계 · VERITY 의견 아님")}
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
                전 종목 사실 · 등급·추천 아님 · 출처 DART·공정위·FnGuide·KRX·네이버 · 가격·차트 실시간 · 점수 held(2027)
            </div>
        </div>
    )
}

addPropertyControls(PublicStockReport, {
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: DEFAULT_URL },
    flowUrl: { type: ControlType.String, title: "Flow URL", defaultValue: DEFAULT_FLOW },
    forensicsUrl: { type: ControlType.String, title: "Forensics URL", defaultValue: DEFAULT_FORENSICS },
    insiderUrl: { type: ControlType.String, title: "Insider URL", defaultValue: DEFAULT_INSIDER },
    warnUrl: { type: ControlType.String, title: "Warnings URL", defaultValue: DEFAULT_WARN },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

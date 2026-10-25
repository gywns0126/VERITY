import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useMemo, useRef, useState } from "react"

/**
 * AlphaNest 뉴스 탭 (공개) — 팩트형.
 * 되돌리지 말 것: 승인된 시장 언급 종목·테마 요약은 탭 아래, 기사·정렬 위에 두고 상세 통계는 모달로 확인한다.
 * 되돌리지 말 것: 명시적 URL q 검색은 개인 보유 목록과 분리하며, 이전 검색 응답은 무효화한다.
 * 되돌리지 말 것: 시장 번역은 제목·URL이 모두 같은 미국 기사의 기존 번역만 재사용한다. 번역이 없으면 원문을 유지한다.
 *
 * 회원 개인 뉴스는 현재 보유 수량 > 0인 종목만 표시한다. recommendations.json은 기사 lookup일 뿐이다.
 * 비회원은 이 기기 관심종목, portfolio.json의 headlines / us_headlines는 별도 "시장 / 미국" 뉴스다.
 *
 * RULE 6 (LLM narrative STOP): 제목 + 출처 + 시각 + 원문 링크만. 해설/요약 0.
 * RULE 7: 제목의 긍정/부정 표현은 키워드 자동분류(검증 전)이며 투자 효과·가격 방향이 아니다.
 * 되돌리지 말 것: 빈 개인 목록은 공개 시장 탭으로 안내하되 보유 조회 실패·명시 검색·직접 선택은 덮지 않는다.
 *   점수·등급·방향성 영향 추론은 미노출. 섹터 = 종목 멤버십 사실(영향·수혜 아님).
 *   출처 신뢰도(credibility≥0.8 자체 분류)도 "가설/N=" 표기(2026-07-04 사이트 감사 P1).
 *
 * 다크모드: body[data-framer-theme] 추종 (다른 public 컴포넌트와 동일 패턴).
 *  - 캔버스 에디터: dark prop 정적 프리뷰 (RenderTarget.canvas 가드)
 */

const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
// 종목 검색 = 표준 검색창(PublicStockSearch)과 동기 — 동일 유니버스·로고·국기.
const UNIVERSE_URL = BLOB + "/universe_search.json"
// 화제 종목 자동집계 제외 — 이름 자체가 흔한 일반어라 헤드라인 오탐(예: '지원 대상', '태양광 발전').
// 양쪽 단어경계 검사와 별개인 의미 충돌. 등록 2글자명 중 명백 일반어는 연결 근거로 삼지 않는다.
const HOT_NAME_BLOCKLIST = new Set([
    "대상",
    "태양",
    "남성",
    "신원",
    "동양",
    "동서",
    "진도",
    "선진",
    "전방",
    "서한",
    "삼일",
])

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
    if (!tk) return ""
    // 로고 = 토스 종목 CDN (PM 결정: 완전 공개[런칭] 전까지 토스 사용, 2026-07-12). 404/차단 시 onError → 이니셜 폴백.
    return (
        "https://static.toss.im/png-icons/securities/icn-sec-fill-" +
        tk +
        ".png"
    )
}
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"

// 명시적 공개 종목 코드만 전달한다. 계정·보유 수량·메모는 URL에 넣지 않는다.
function newsTicker(value: string): string {
    const code = String(value || "").trim().toUpperCase()
    return /^[A-Z0-9][A-Z0-9._-]{0,31}$/.test(code) ? code : ""
}
function newsReportHref(path: string | undefined, code: string): string {
    const base = path && /^\/(?!\/)[A-Za-z0-9/_-]*$/.test(path) ? path : "/stock"
    return base + "?q=" + encodeURIComponent(newsTicker(code))
}

interface Props {
    dark: boolean
    recUrl: string
    portfolioUrl: string
    maxPerStock: number
    maxMarket: number
    height: number
    marketCardHeight: number
    stockCardHeight: number
    reportPath: string
    apiBase: string
}

// 🚨 2026-07-24 테마 = 자체 내장 CSS 변수(--an-nws-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
//   <style>{AN_PALETTE} 정적 HTML 정합. 화살표 SVG stroke=style(var). Donut/LegendRow=CSS. 되돌리지 말 것.
const LIGHT = {
    bg: "#ffffff",
    card: "#ffffff",
    sub: "#f8f9fb",
    text: "#191f28",
    subtext: "#6b7684",
    faint: "#6b7684",
    border: "#e5e8eb",
    accent: "#6c5ce7",
    chipBg: "#f8f9fb",
    hover: "#f1f3f5",
    focus: "#e9edf2",
    up: "#f04452",
    down: "#3182f6",
    upBg: "#fdecee",
    downBg: "#eaf1fe",
    skBase: "#e9edf1",
    skHi: "#f3f5f7",
}
const DARK = {
    bg: "#171c23",
    card: "#171c23",
    sub: "#1d242c",
    text: "#e3e7ec",
    subtext: "#9aa4b1",
    faint: "#9aa4b1",
    border: "#2b3138",
    accent: "#a99bff",
    chipBg: "#1d242c",
    hover: "#252c35",
    focus: "#303945",
    up: "#f04452",
    down: "#5b9bff",
    upBg: "#2a1a1d",
    downBg: "#17263c",
    skBase: "#222a33",
    skHi: "#2d3742",
}

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-nws-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "nws"
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

// GICS/yfinance 섹터 EN→KR (멤버십 사실 라벨). 미스 시 원문.
const SECTOR_KR: Record<string, string> = {
    "Basic Materials": "기초소재",
    "Communication Services": "커뮤니케이션",
    "Consumer Cyclical": "경기소비재",
    "Consumer Defensive": "필수소비재",
    Energy: "에너지",
    "Financial Services": "금융",
    Financial: "금융",
    Healthcare: "헬스케어",
    Industrials: "산업재",
    "Real Estate": "부동산",
    Technology: "기술",
    Utilities: "유틸리티",
}
function sectorLabel(s: string): string {
    if (!s) return ""
    return SECTOR_KR[s] || s
}

type Tab = "stock" | "market" | "us"

// Derived default only: no new subscription, membership substitution or automatic history entry.
function defaultNewsTab(personalBusy: boolean, personalProblem: string, personalCount: number,
    explicitSearch: boolean, loading: boolean, marketProblem: string, marketCount: number, usCount: number): Tab {
    if (personalBusy || personalProblem || personalCount > 0 || explicitSearch) return "stock"
    // Do not conceal a failed market request by switching to another source.
    return !loading && !marketProblem && !marketCount && usCount > 0 ? "us" : "market"
}
function publicNewsFeeds(payload: any) {
    const rows = (value: any): boolean => Array.isArray(value) &&
        value.every((item: any) => item && typeof item === "object" && typeof item.title === "string")
    const usable = payload && typeof payload === "object" && !Array.isArray(payload) && !payload.error
    const marketOk = !!usable && rows(payload.headlines) &&
        (payload.bloomberg_google_headlines == null || rows(payload.bloomberg_google_headlines))
    const usOk = !!usable && rows(payload.us_headlines)
    // The market copy omits translations supplied on the same article in the US feed.
    // Exact title AND URL only; conflicting translations must not be guessed.
    const articleKey = (item: any): string => {
        const url = item.link || item.url
        return typeof url === "string" && url.trim()
            ? JSON.stringify([item.title, url.trim()])
            : ""
    }
    const translations = new Map<string, Set<string>>()
    for (const item of usOk ? payload.us_headlines : []) {
        const key = articleKey(item)
        const ko = typeof item.title_ko === "string" ? item.title_ko.trim() : ""
        if (!key || !ko || ko === item.title || !/[가-힣]/.test(ko)) continue
        const values = translations.get(key) || new Set<string>()
        values.add(ko)
        translations.set(key, values)
    }
    const market = marketOk
        ? payload.headlines.concat(payload.bloomberg_google_headlines || []).map((item: any) => {
            if (item.title_ko || /[가-힣]/.test(item.title)) return item
            const values = translations.get(articleKey(item))
            return values?.size === 1 ? { ...item, title_ko: [...values][0] } : item
        })
        : []
    return {
        marketOk, usOk,
        headlines: marketOk ? payload.headlines : [],
        market,
        us: usOk ? payload.us_headlines : [],
    }
}

interface NewsItem {
    title: string
    titleKo?: string
    url: string
    source: string
    time: string
    sentiment: string
    category?: string // Naver 종목뉴스 enrichment (내 종목 탭)
    outlets?: number // 같은 사안 보도 매체 수
    credible?: boolean // 신뢰 출처(✓)
    ts?: number // 정렬용 발행시각(ms) — 0=시각없음(뒤로)
    score?: number // composite_score (핫 정렬 · 매체동시보도+긴급 자체 산출)
}
interface StockGroup {
    ticker: string
    name: string
    market: string
    sector: string
    industry: string
    items: NewsItem[]
}
interface PersonalStock {
    ticker: string
    name: string
    market: string
    watched?: boolean
    held?: boolean
}
// 되돌리지 말 것: 회원 뉴스의 종목 집합은 현재 보유 수량 > 0인 행만 사용한다.
// 관심종목·매도 완료(0주)·공개 추천 목록은 회원 보유 목록의 대체값이 아니다.
function currentHoldingStocks(payload: unknown): PersonalStock[] {
    const rows = Array.isArray(payload)
        ? payload
        : payload && typeof payload === "object" && "holdings" in payload
          ? payload.holdings
          : null
    if (!Array.isArray(rows)) throw new Error("Invalid holdings response")
    const stocks = new Map<string, PersonalStock>()
    for (const row of rows) {
        if (!row || typeof row !== "object") continue
        if (typeof row.shares !== "number" && typeof row.shares !== "string") continue
        const shares = Number(row.shares)
        if (!Number.isFinite(shares) || shares <= 0) continue
        const ticker = String(row.ticker || "").trim().toUpperCase()
        if (!ticker) continue
        stocks.set(ticker, {
            ticker,
            name: String(row.name || ticker),
            market: String(row.market || ""),
            watched: false,
            held: true,
        })
    }
    return Array.from(stocks.values())
}

// 오늘 핫한 종목 — 수집된 시장 제목에서 종목별 언급 기사 수 집계. 보유 목록·추천·등급 아님.
interface HotStock {
    ticker: string
    name: string
    market: string
    count: number
    score: number
}

// 되돌리지 말 것: 회사명 일부·매체 접미사는 연결 근거가 아니며, 기사마다 각 종목을 한 번만 센다.
function countHeadlineStocks(items: NewsItem[], universe: any[]): HotStock[] {
    const issuers = new Map<string, any>()
    const owners = new Map<string, Set<string>>()
    const addAlias = (value: unknown, ticker: string) => {
        if (typeof value !== "string") return
        const alias = value.trim().toLowerCase()
        if (alias.length < 2 || HOT_NAME_BLOCKLIST.has(alias) || /^[a-z.\-]{1,4}$/.test(alias) || /^\d+$/.test(alias)) return
        if (!owners.has(alias)) owners.set(alias, new Set())
        owners.get(alias)!.add(ticker)
    }
    for (const row of universe) {
        if (!row || typeof row !== "object") continue
        const ticker = String(row.ticker || "").trim()
        if (!/^\d{6}$/.test(ticker)) continue
        issuers.set(ticker, row)
        addAlias(row.name_ko, ticker)
        addAlias(row.name, ticker)
    }
    // 해당 상장사가 유니버스에 있을 때만 공식명과 통칭을 연결한다. 그룹명으로 잘라내지 않는다.
    if (issuers.has("000660")) {
        addAlias("SK하이닉스", "000660")
        addAlias("하이닉스", "000660")
    }
    if (issuers.has("035420")) addAlias("네이버", "035420")
    const aliases = [...owners]
        .filter(([, codes]) => codes.size === 1)
        .map(([alias, codes]) => ({ alias, ticker: [...codes][0] }))
    // Reuse boundary expressions: compiling a Unicode regex for every issuer is costly.
    const startsWord = /^[\p{L}\p{N}_]/u
    const endsWord = /[\p{L}\p{N}_]$/u
    const particle = /^(?:으로부터|으로는|에서는|에게는|에게|에서|에는|에도|에선|에겐|와는|과는|와의|과의|까지|부터|보다|처럼|마저|조차|이라며|이라는|이란|라고|이며|으로|로는|은|는|이|가|을|를|와|과|의|도|만|에|로)(?![\p{L}\p{N}_])/u
    const publisherSuffix = /\s+[-–—|]\s*(?:네이버\s*프리미엄\s*콘텐츠|naver\s*premium\s*contents?)\s*$/i
    const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    const tally = new Map<string, HotStock>()
    for (const item of items) {
        let title = typeof item?.title === "string" ? item.title : ""
        const source = typeof item?.source === "string" ? item.source.trim() : ""
        if (source) title = title.replace(new RegExp(`\\s+[-–—|]\\s*${escape(source)}\\s*$`, "i"), "")
        title = title.replace(publisherSuffix, "").toLowerCase()
        if (!/[가-힣]/.test(title)) continue // 기존 범위 유지: 한국어 시장 제목·국내 상장 종목
        const found = new Set<string>()
        for (const { alias, ticker } of aliases) {
            if (found.has(ticker)) continue
            for (let pos = title.indexOf(alias); pos >= 0; pos = title.indexOf(alias, pos + 1)) {
                const after = title.slice(pos + alias.length)
                if (!endsWord.test(title.slice(Math.max(0, pos - 2), pos)) && (!startsWord.test(after) || particle.test(after))) {
                    found.add(ticker)
                    break
                }
            }
        }
        for (const ticker of found) {
            if (!tally.has(ticker)) {
                const row = issuers.get(ticker)
                tally.set(ticker, { ticker, name: row.name_ko || row.name || ticker, market: "KR", count: 0, score: 0 })
            }
            tally.get(ticker)!.count++
        }
    }
    return [...tally.values()].sort((a, b) => b.count - a.count).slice(0, 8)
}

/* 오늘의 뉴스 한눈 — 전부 기존 사실 집계(RULE7, LLM 해석 0). 출처신뢰도·신선도·무드·테마빈도. */
interface Insights {
    total: number
    credHi: number
    credLo: number // 출처 신뢰도(credibility>=0.8=신뢰 출처, 자체 점수화)
    fresh: number
    dup: number // 신선도(near_duplicate MinHash)
    pos: number
    neg: number
    neu: number // 무드(sentiment 키워드)
    themes: { name: string; n: number }[] // 오늘의 테마(키워드 빈도, 단어 카운트만)
}
// 뉴스 테마 사전 — 제목 키워드 매칭으로 "오늘 시장 화두" 집계(LLM 아님, 순수 빈도). 사실 집계 RULE7.
const THEME_KEYWORDS: [string, string[]][] = [
    [
        "반도체",
        [
            "반도체",
            "HBM",
            "메모리",
            "D램",
            "낸드",
            "파운드리",
            "엔비디아",
            "TSMC",
        ],
    ],
    [
        "금리·환율",
        [
            "금리",
            "연준",
            "FOMC",
            "기준금리",
            "인하",
            "인상",
            "환율",
            "달러",
            "원·달러",
        ],
    ],
    ["AI", ["AI", "인공지능", "데이터센터", "챗GPT"]],
    ["2차전지", ["2차전지", "배터리", "전기차", "리튬", "양극재"]],
    ["정책·관세", ["관세", "트럼프", "규제", "대통령", "국회"]],
    ["실적", ["실적", "영업이익", "어닝", "순이익", "매출"]],
    ["지수·변동", ["코스피", "코스닥", "지수", "폭락", "급등", "급락"]],
    ["수급", ["외국인", "기관", "국민연금", "순매수", "순매도", "연기금"]],
    ["가상자산", ["비트코인", "코인", "가상자산", "이더리움"]],
    ["부동산", ["부동산", "집값", "분양", "전세"]],
]

function hostname(url: string): string {
    if (!url) return ""
    try {
        const m = url.replace(/^https?:\/\//, "").split("/")[0]
        return m.replace(/^www\./, "")
    } catch (e) {
        return ""
    }
}

/* "제목 - Yahoo Finance" 형태에서 끝 출처를 분리 */
function splitSource(title: string): { title: string; source: string } {
    if (!title) return { title: "", source: "" }
    const idx = title.lastIndexOf(" - ")
    if (idx > 8 && idx > title.length - 40) {
        return {
            title: title.slice(0, idx).trim(),
            source: title.slice(idx + 3).trim(),
        }
    }
    return { title: title.trim(), source: "" }
}

function dateOnly(t: string): string {
    if (!t) return ""
    const m = String(t).match(/\d{4}-\d{2}-\d{2}/)
    return m ? m[0] : ""
}

// 발행 시각 → 상대시각(방금/N분·시간·일 전), 7일 초과는 날짜. RFC-2822("Fri, 03 Jul 2026 04:43:16 GMT")·ISO 모두 파싱.
function fmtWhen(t: string): string {
    if (!t) return ""
    const ms = new Date(String(t)).getTime()
    if (!isFinite(ms)) return dateOnly(t) // 파싱 실패 = 날짜 부분만 폴백
    const mins = Math.round((Date.now() - ms) / 60000)
    if (mins < 0) return dateOnly(t)
    if (mins < 1) return "방금"
    if (mins < 60) return mins + "분 전"
    const hrs = Math.round(mins / 60)
    if (hrs < 24) return hrs + "시간 전"
    return Math.round(hrs / 24) + "일 전" // 오래돼도 날짜 대신 항상 '일 전'(PM 2026-07-05)
}

// 정렬용 발행시각 ms (파싱 실패=0 → 뒤로)
function toMs(t: string): number {
    const ms = new Date(String(t || "")).getTime()
    return isFinite(ms) ? ms : 0
}
const NEWS_LOAD_CAP = 60 // 로드 상한(더보기용 여유). display 는 FlatNews 가 페이지네이션
// 표시 창(PM 2026-07-12) — 시장 플래시=최근 7일, 저밀도(2~8건/일)·주말 공백이라 바닥 20건으로 빈 피드 방지.
//   저장(소스)이 아니라 화면 노출만 제어 — stale 헤드라인(수개월 전) 차단.
//   종목별 뉴스는 발생이 훨씬 드물어 30일 창 — /api/stock_news 서버에서 강제(여기 아님).
const FLASH_WINDOW_DAYS = 7
const FLASH_FLOOR = 20
// 최근 N일만 남기되, 창이 floor 미만이면 최신순으로 floor 개까지 채움(빈 피드 방지). ts=0(파싱실패)은 최신 취급 안 함.
function windowNews<T extends { ts?: number }>(
    arr: T[],
    days: number,
    floor: number
): T[] {
    const cutoff = Date.now() - days * 86400000
    const byTs = arr.slice().sort((a, b) => (b.ts || 0) - (a.ts || 0))
    const recent = byTs.filter((it) => (it.ts || 0) >= cutoff)
    return recent.length >= floor ? recent : byTs.slice(0, floor)
}
const NEWS_SORTS: { k: string; label: string }[] = [
    { k: "recent", label: "최신" },
    { k: "hot", label: "핫" },
    { k: "outlet", label: "언론사" },
]
// Share only simultaneous public ticker requests. Settled results are never retained here.
const stockNewsInFlight = new Map<string, Promise<any[] | null>>()
function loadStockNews(url: string): Promise<any[] | null> {
    const pending = stockNewsInFlight.get(url)
    if (pending) return pending
    const request: Promise<any[] | null> = fetch(url, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => (d && Array.isArray(d.items) ? d.items : null))
        .catch(() => null)
        .finally(() => {
            if (stockNewsInFlight.get(url) === request) stockNewsInFlight.delete(url)
        })
    stockNewsInFlight.set(url, request)
    return request
}

function asArray(x: any): any[] {
    return Array.isArray(x) ? x : []
}

/* 종목 로고 — 표준 검색창(PublicStockSearch)과 동일: 토스 CDN(404 시 이니셜) + circle-flags 원형 국기. */
function Logo(props: { ticker: any; name: any; C: any; size?: number }) {
    const { ticker, name, C } = props
    const size = props.size || 22
    const [err, setErr] = useState(false)
    const lm = useBfLogoMap()
    const bfSrc = bfLogoSrc(ticker, lm, size)
    const ch =
        String(name || "?")
            .trim()
            .charAt(0) || "?"
    const code = /^\d{6}$/.test(String(ticker || "")) ? "kr" : "us"
    const fsize = Math.round(size * 0.46)
    return (
        <span
            style={{
                position: "relative",
                width: size,
                height: size,
                flexShrink: 0,
                display: "inline-block",
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
                        objectFit: "cover",
                        display: "block",
                        background: "transparent",
                    }}
                />
            ) : (
                <span
                    style={{
                        width: size,
                        height: size,
                        borderRadius: Math.round(size * 0.32),
                        background: C.sub,
                        color: C.accent,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: Math.round(size * 0.42),
                        fontWeight: 800,
                    }}
                >
                    {ch}
                </span>
            )}
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
                }}
            />
        </span>
    )
}

/**
 * 🚨 2026-07-25 높이 정합 — 레이아웃 어노테이션 필수. 되돌리지 말 것.
 *   어노테이션이 없으면 Framer 는 코드 컴포넌트를 고정 높이로 취급 → 인스턴스 Fit(hug) 이 정상 동작하지 않고
 *   /news Desktop 프레임(overflow=clip)에서 본문이 잘림(실사고: height=720 고정).
 *   height=auto = Fit 만 지원 → PM 이 실수로 px 고정해도 다시 잘릴 수 없음.
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 */
export default function PublicNewsTab(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [chosenTab, setTab] = useState<Tab | null>(null)
    const [showKo, setShowKo] = useState<boolean>(false)
    const [mktSort, setMktSort] = useState<string>("recent") // 시장·미국 정렬: recent/hot/outlet
    const [recGroups, setRecGroups] = useState<StockGroup[]>([]) // 공개 뉴스 집계용; 개인 목록의 폴백으로 사용하지 않는다.
    const [recMap, setRecMap] = useState<Record<string, StockGroup>>({}) // 전 rec: ticker → 메타+뉴스(뉴스 소스 lookup)
    const [naverNews, setNaverNews] = useState<Record<string, NewsItem[]>>({}) // KR 종목 라이브 뉴스(네이버 enrich)
    const [watch, setWatch] = useState<PersonalStock[]>([]) // 로그인=현재 보유만, 비로그인=이 기기 관심종목
    const [memberMode, setMemberMode] = useState<boolean>(false)
    const newsAudienceToken = useRef("")
    const [newsAudienceVersion, setNewsAudienceVersion] = useState(0)
    const [personalLoading, setPersonalLoading] = useState<boolean>(false)
    const [personalError, setPersonalError] = useState<string>("")
    const [market, setMarket] = useState<NewsItem[]>([])
    const [us, setUs] = useState<NewsItem[]>([])
    const [insights, setInsights] = useState<Insights | null>(null)
    const [insightsOpen, setInsightsOpen] = useState(false)
    const insightsDialog = useRef<HTMLDialogElement>(null)
    const insightsTrigger = useRef<HTMLButtonElement>(null)
    const insightsClose = useRef<HTMLButtonElement>(null)
    const [loading, setLoading] = useState<boolean>(true)
    // 반응형 — 컨테이너 폭 감지(좁은 화면 패딩 축소). 다른 public 컴포넌트 동일 패턴.
    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const narrow = w > 0 && w < 480
    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries) setW(e.contentRect.width)
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])
    const [failed, setFailed] = useState<boolean>(false)
    const [marketError, setMarketError] = useState<string>("")
    const [usError, setUsError] = useState<string>("")
    const [q, setQ] = useState<string>("") // 종목 뉴스 검색어(이름/코드)
    const [uni, setUni] = useState<any[]>([]) // 종목 유니버스(표준 universe_search.json — 검색창 전역 동기)
    const [focused, setFocused] = useState<boolean>(false)
    const [searchGroup, setSearchGroup] = useState<StockGroup | null>(null) // 검색된 종목 뉴스(온디맨드)
    const [searching, setSearching] = useState<boolean>(false)
    const [searchMsg, setSearchMsg] = useState<string>("")
    const [selectedTicker, setSelectedTicker] = useState<string>("")
    const searchRequest = useRef<{ generation: number; controller: AbortController | null }>({
        generation: 0, controller: null,
    })
    const searchLocation = useRef<string | null>(null)
    const searchActions = useRef<{
        pick: (code: string, name: string, sync?: boolean) => Promise<void>
        clear: (sync?: boolean) => void
    } | null>(null)

    const tab = chosenTab ?? defaultNewsTab(
        personalLoading, personalError, watch.length,
        !!(selectedTicker || q.trim() || searchGroup || searchMsg),
        loading, marketError, market.length, us.length
    )
    const activeFeedError = tab === "us" ? usError : marketError

    // Native modal owns inertness and focus trapping; restore scroll and trigger on close/unmount.
    useEffect(() => {
        if (!insightsOpen) return
        const dialog = insightsDialog.current
        if (!dialog) return
        const body = dialog.ownerDocument.body
        const overflow = body.style.getPropertyValue("overflow")
        const priority = body.style.getPropertyPriority("overflow")
        const trigger = insightsTrigger.current
        if (!dialog.open) dialog.showModal()
        body.style.setProperty("overflow", "hidden")
        insightsClose.current?.focus({ preventScroll: true })
        return () => {
            if (dialog.open) dialog.close()
            body.style.setProperty("overflow", overflow, priority)
            if (trigger?.isConnected) trigger.focus({ preventScroll: true })
        }
    }, [insightsOpen])

    /* 내 종목 source contract — 로그인: 서버의 현재 보유(shares > 0)만 사용.
       비로그인: 이 기기의 임시 관심종목만 사용. 회원 조회 실패·빈 보유 목록도 관심종목으로 대체하지 않는다. */
    useEffect(() => {
        if (onCanvas) return
        const api = (
            props.apiBase || "https://project-yw131.vercel.app"
        ).replace(/\/+$/, "")
        let alive = true
        let generation = 0
        let controller: AbortController | null = null
        const load = () => {
            if (!alive) return
            const requestId = ++generation
            controller?.abort()
            controller = null
            setPersonalError("")
            setPersonalLoading(false)
            let token = ""
            try {
                const s = JSON.parse(
                    (typeof localStorage !== "undefined" &&
                        localStorage.getItem("verity_supabase_session")) ||
                        "null"
                )
                token = (s && s.access_token) || ""
            } catch (e) {}
            if (newsAudienceToken.current !== token) {
                newsAudienceToken.current = token
                setWatch([])
                setNaverNews({})
                setNewsAudienceVersion((version) => version + 1)
            }
            if (token) {
                setMemberMode(true)
                setPersonalLoading(true)
                controller = new AbortController()
                const H = { Authorization: `Bearer ${token}` }
                fetch(`${api}/api/holdings`, {
                    headers: H,
                    cache: "no-store",
                    signal: controller.signal,
                })
                    .then((r) => {
                        if (!r.ok) throw new Error("Holdings request failed")
                        return r.json()
                    })
                    .then((holdings) => {
                        if (!alive || requestId !== generation) return
                        setWatch(currentHoldingStocks(holdings))
                    })
                    .catch(() => {
                        if (!alive || requestId !== generation) return
                        setWatch([])
                        setPersonalError("보유종목을 불러오지 못했어요. 로그인 상태를 확인한 뒤 새로고침해 주세요.")
                    })
                    .finally(() => {
                        if (alive && requestId === generation) setPersonalLoading(false)
                    })
                return
            }
            if (alive) setMemberMode(false)
            const m = new Map<string, PersonalStock>()
            try {
                const r = typeof localStorage !== "undefined" ? localStorage.getItem("verity_watchlist") : null
                const a = r ? JSON.parse(r) : []
                if (Array.isArray(a)) for (const it of a) {
                    const tk = String((it && it.ticker) || "").trim()
                    if (!tk) continue
                    m.set(tk.toUpperCase(), { ticker: tk, name: (it && it.name) || tk, market: (it && it.market) || "", watched: true, held: false })
                }
            } catch (e) {}
            if (alive) setWatch(Array.from(m.values()))
        }
        load()
        window.addEventListener("verity-watchlist-changed", load) // PublicWatchlist(localStorage) 별표
        window.addEventListener("verity_watch_change", load) // AlphaNestWatchlist(로그인) 별표
        window.addEventListener("verity_holdings_change", load) // 둥지 보유 변경
        window.addEventListener("verity_auth_change", load) // 로그인/로그아웃
        window.addEventListener("storage", load)
        window.addEventListener("focus", load) // 다른 화면에서 보유를 수정한 뒤 복귀
        window.addEventListener("pageshow", load) // 뒤로 가기/BFCache 복원
        return () => {
            alive = false
            generation++
            controller?.abort()
            window.removeEventListener("verity-watchlist-changed", load)
            window.removeEventListener("verity_watch_change", load)
            window.removeEventListener("verity_holdings_change", load)
            window.removeEventListener("verity_auth_change", load)
            window.removeEventListener("storage", load)
            window.removeEventListener("focus", load)
            window.removeEventListener("pageshow", load)
        }
    }, [onCanvas, props.apiBase])

    /* 데이터 로드 — 🚨 2026-07-25 캔버스에서도 실데이터 로드(과거 onCanvas early-return 제거).
       이유: 캔버스가 빈 컴포넌트로 렌더되면 Fit(hug) 이 헤더 높이만 재서 실제 사이트 높이와 어긋남.
       캔버스 = 사이트와 같은 내용 → 같은 높이. 되돌리지 말 것. */
    useEffect(() => {
        let alive = true
        const recUrl = props.recUrl || BLOB + "/recommendations.json"
        const pfUrl = props.portfolioUrl || BLOB + "/portfolio.json"
        const maxPer = props.maxPerStock || 3
        setLoading(true)
        setMarket([])
        setUs([])
        setInsights(null)
        setFailed(false)
        setMarketError("")
        setUsError("")

        Promise.all([
            fetch(recUrl)
                .then((r) => (r.ok ? r.json() : null))
                .catch(() => null),
            fetch(pfUrl)
                .then((r) => (r.ok ? r.json() : null))
                .catch(() => null),
        ]).then((res) => {
            if (!alive) return
            const recRaw = res[0]
            const pf = res[1]
            const feeds = publicNewsFeeds(pf)

            // recommendations → 뉴스 소스 lookup. 개인 목록의 종목 집합은 변경하지 않는다.
            const recs = Array.isArray(recRaw)
                ? recRaw
                : (recRaw && recRaw.recommendations) || []
            const recGroupsArr: StockGroup[] = []
            const rmap: Record<string, StockGroup> = {}
            for (let i = 0; i < recs.length; i++) {
                const rec = recs[i] || {}
                const tk = String(rec.ticker || rec.code || "").trim()
                if (!tk) continue
                const sent = rec.sentiment || {}
                const links = asArray(sent.top_headline_links)
                const items: NewsItem[] = []
                for (
                    let j = 0;
                    j < links.length && items.length < maxPer;
                    j++
                ) {
                    const h = links[j] || {}
                    const url = h.url || h.link || ""
                    const sp = splitSource(h.title || "")
                    if (!sp.title) continue
                    items.push({
                        title: sp.title,
                        titleKo: h.title_ko
                            ? splitSource(String(h.title_ko)).title
                            : "",
                        url: url,
                        source: sp.source || hostname(url),
                        time: "",
                        sentiment: String(h.label || ""),
                    })
                }
                const grp: StockGroup = {
                    ticker: tk,
                    name: rec.name || rec.company_name || tk,
                    market: rec.market || "",
                    sector: rec.sector || "",
                    industry: rec.industry || "",
                    items: items,
                }
                rmap[tk] = grp
                rmap[tk.toUpperCase()] = grp
                if (items.length) recGroupsArr.push(grp)
            }

            // 시장 뉴스 (KR 헤드라인 + 글로벌/블룸버그 RSS 합본 — 볼륨↑, 제목 dedup)
            const mkRaw = feeds.market
            const mk: NewsItem[] = []
            const seenMk = new Set<string>()
            for (
                let i = 0;
                i < mkRaw.length && mk.length < NEWS_LOAD_CAP;
                i++
            ) {
                const h = mkRaw[i] || {}
                const sp = splitSource(h.title || "") // 블룸버그 RSS = "제목 - Bloomberg.com" 포맷이라 출처 분리
                const t = sp.title || String(h.title || "").trim()
                if (!t) continue
                const key = t.slice(0, 32)
                if (seenMk.has(key)) continue
                seenMk.add(key)
                const rawT = h.time || h.published_at || ""
                mk.push({
                    title: t,
                    titleKo: h.title_ko
                        ? splitSource(String(h.title_ko)).title
                        : "",
                    url: h.link || h.url || "",
                    source:
                        h.source ||
                        sp.source ||
                        hostname(h.link || h.url || ""),
                    time: fmtWhen(rawT),
                    sentiment: String(h.sentiment || ""),
                    ts: toMs(rawT),
                    score: Number(h.composite_score) || 0,
                })
            }

            // 미국 뉴스
            const usRaw = feeds.us
            const usArr: NewsItem[] = []
            for (
                let i = 0;
                i < usRaw.length && usArr.length < NEWS_LOAD_CAP;
                i++
            ) {
                const h = usRaw[i] || {}
                const sp = splitSource(h.title || "")
                if (!sp.title) continue
                const rawT = h.time || h.published_at || ""
                usArr.push({
                    title: sp.title,
                    titleKo: h.title_ko
                        ? splitSource(String(h.title_ko)).title
                        : "",
                    url: h.link || h.url || "",
                    source: sp.source || hostname(h.link || ""),
                    time: fmtWhen(rawT),
                    sentiment: String(h.sentiment || ""),
                    ts: toMs(rawT),
                    score: Number(h.composite_score) || 0,
                })
            }

            // 오늘의 뉴스 한눈 — KR headlines(category/near_duplicate/sentiment) + 추천 종목 뉴스량 집계
            const rawHl = feeds.headlines
            if (rawHl.length) {
                let credHi = 0,
                    credLo = 0,
                    fresh = 0,
                    dup = 0,
                    pos = 0,
                    neg = 0,
                    neu = 0
                for (const h of rawHl) {
                    if ((Number(h.credibility) || 0) >= 0.8) credHi++
                    else credLo++ // 신뢰 출처(자체 점수)
                    if (h.near_duplicate) dup++
                    else fresh++
                    const s = String(h.sentiment || "neutral")
                    if (s === "positive") pos++
                    else if (s === "negative") neg++
                    else neu++
                }
                // 오늘의 테마 = 시장 헤드라인(KR+글로벌) 제목 키워드 빈도(LLM 아님)
                const themeCnt: Record<string, number> = {}
                for (const it of windowNews(
                    mk,
                    FLASH_WINDOW_DAYS,
                    FLASH_FLOOR
                )) {
                    const t = it.title || ""
                    for (const [name, kws] of THEME_KEYWORDS) {
                        for (const k of kws) {
                            if (t.indexOf(k) >= 0) {
                                themeCnt[name] = (themeCnt[name] || 0) + 1
                                break
                            }
                        }
                    }
                }
                const themes = Object.keys(themeCnt)
                    .map((name) => ({ name, n: themeCnt[name] }))
                    .sort((a, b) => b.n - a.n)
                    .slice(0, 6)
                // 뉴스 많은 종목 = 라이브 per-stock 실제 건수(아래 enrichment effect서 채움). headline_count 는 포화라 미사용.
                setInsights({
                    total: rawHl.length,
                    credHi,
                    credLo,
                    fresh,
                    dup,
                    pos,
                    neg,
                    neu,
                    themes,
                })
            }

            // 오늘 화제 종목 = 실제 헤드라인 언급 tally(아래 useMemo). recommendations.headline_count 편향 폐기(2026-07-07).

            setRecGroups(recGroupsArr)
            setRecMap(rmap)
            setMarket(windowNews(mk, FLASH_WINDOW_DAYS, FLASH_FLOOR))
            setUs(windowNews(usArr, FLASH_WINDOW_DAYS, FLASH_FLOOR))
            setLoading(false)
            setMarketError(feeds.marketOk ? "" : "시장 뉴스를 불러오지 못했어요. 새로고침해 주세요.")
            setUsError(feeds.usOk ? "" : "미국 뉴스를 불러오지 못했어요. 새로고침해 주세요.")
            setFailed(!feeds.marketOk && !feeds.usOk)
        })

        return () => {
            alive = false
        }
    }, [props.recUrl, props.portfolioUrl, props.maxPerStock, props.maxMarket])

    /* 표시할 내 종목 = 회원은 현재 보유, 비회원은 기기 관심. 추천종목은 개인 목록에 섞지 않는다. */
    const stocks = useMemo<StockGroup[]>(() => {
        const withLive = (g: StockGroup): StockGroup => {
            const live =
                naverNews[g.ticker] || naverNews[String(g.ticker).toUpperCase()]
            return live && live.length ? { ...g, items: live } : g
        }
        return watch.map((w) => {
            const rm =
                recMap[w.ticker] || recMap[String(w.ticker).toUpperCase()]
            const g: StockGroup = {
                ticker: w.ticker,
                name: w.name || (rm ? rm.name : w.ticker),
                market: w.market || (rm ? rm.market : ""),
                sector: rm ? rm.sector : "",
                industry: rm ? rm.industry : "",
                items: rm ? rm.items : [],
            }
            return withLive(g)
        })
    }, [watch, recMap, naverNews])

    /* KR 관심·보유종목 라이브 뉴스 enrich — 목록 변경 시 재수집. 최대 15. */
    const krKey = useMemo(() => {
        const src = watch.map((w) => w.ticker)
        const out: string[] = []
        for (const tk of src) {
            const t = String(tk || "")
            if (/^\d{6}$/.test(t) && out.indexOf(t) < 0) out.push(t)
        }
        return out.slice(0, 15).join(",")
    }, [watch])

    useEffect(() => {
        if (onCanvas || !krKey) return
        const api = (
            props.apiBase || "https://project-yw131.vercel.app"
        ).replace(/\/+$/, "")
        const krs = krKey.split(",").filter(Boolean)
        let alive = true
        const audience = newsAudienceToken.current
        for (const tk of krs) {
            loadStockNews(`${api}/api/stock_news?code=${encodeURIComponent(tk)}`).then((items) => {
                if (!alive || newsAudienceToken.current !== audience || !items?.length) return
                setNaverNews((prev) => ({
                    ...prev,
                    [tk]: items.slice(0, 4).map((n: any) => ({
                        title: n.title,
                        url: n.url,
                        source: n.source,
                        time: n.rel_time || "",
                        sentiment: "",
                        category: n.category,
                        outlets: n.outlets,
                        credible: n.credible,
                    })),
                }))
            })
        }
        return () => {
            alive = false
        }
    }, [krKey, props.apiBase, onCanvas, newsAudienceVersion])

    const tabs: { key: Tab; label: string; count: number }[] = useMemo(
        () => [
            { key: "stock", label: memberMode ? "보유종목" : "이 기기의 관심", count: stocks.length },
            { key: "market", label: "시장", count: market.length },
            { key: "us", label: "미국", count: us.length },
        ],
        [memberMode, stocks.length, market.length, us.length]
    )

    /* 유니버스 로드(마운트) — 표준 검색창 autocomplete + '오늘 화제 종목' 언급 tally 공용(universe_search.json).
       캔버스도 로드(2026-07-25) — '오늘 화제 종목' 줄이 캔버스에서 빠지면 Fit 높이가 사이트보다 짧아짐. */
    useEffect(() => {
        if (uni.length) return
        fetch(UNIVERSE_URL, { cache: "force-cache" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const a = d && (Array.isArray(d) ? d : d.stocks)
                if (Array.isArray(a)) setUni(a)
            })
            .catch(() => {})
    }, [uni.length])

    /* 시장 전체의 종목별 언급 기사 수. 개인 보유 목록과 별도로 집계한다. */
    const hotStocks = useMemo<HotStock[]>(
        () => countHeadlineStocks(market, uni),
        [market, uni]
    )
    // 라이브 연관검색어 — 코드·이름 부분일치 상위 8 (표준과 동일 매칭).
    const matches = useMemo(() => {
        const s = q.trim().toLowerCase()
        if (!s || !uni.length) return []
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
        return uni
            .filter(
                (x) =>
                    String(x.ticker).toLowerCase().includes(s) ||
                    String(x.name || "")
                        .toLowerCase()
                        .includes(s) ||
                    String((x as any).name_ko || "").includes(s)
            )
            .sort((a: any, b: any) => rk(a) - rk(b))
            .slice(0, 8)
    }, [q, uni])
    /* Explicit search lifecycle — does not mutate holdings or device interests. */
    const cancelSearch = () => {
        const current = searchRequest.current
        current.generation += 1
        current.controller?.abort()
        current.controller = null
        return current.generation
    }
    const syncSearchUrl = (code: string) => {
        if (onCanvas || typeof window === "undefined") return
        const current = new URL(window.location.href)
        const values = current.searchParams.getAll("q")
        searchLocation.current = JSON.stringify(code ? [code] : [])
        if (values.length === (code ? 1 : 0) && (values[0] || "") === code) return
        // Retain Framer's history state; carry only the selected public code.
        window.history.pushState(window.history.state, "", current.pathname + (code ? "?q=" + encodeURIComponent(code) : ""))
    }
    const clearSearch = (sync = true) => {
        cancelSearch()
        setQ("")
        setFocused(false)
        React.startTransition(() => {
            setSelectedTicker("")
            setSearchGroup(null)
            setSearchMsg("")
            setSearching(false)
        })
        if (sync) syncSearchUrl("")
    }
    const pickNews = async (tk: string, nm: string, sync = true) => {
        const code = newsTicker(tk)
        const generation = cancelSearch()
        const isCurrent = () => searchRequest.current.generation === generation
        setFocused(false)
        setQ(nm || code)
        React.startTransition(() => {
            setTab("stock")
            setSelectedTicker(code)
            setSearchGroup(null)
            setSearchMsg("")
            setSearching(false)
        })
        if (sync) syncSearchUrl(code)
        if (!code || !/^\d{6}$/.test(code)) {
            React.startTransition(() => setSearchMsg(code
                ? "이 화면에서는 이 종목·자산의 개별 뉴스 검색을 아직 지원하지 않아요. 국내 6자리 종목 코드만 지원하며, 선택한 자산은 리포트에서 확인해 주세요."
                : "종목 코드를 확인해 주세요."))
            return
        }
        const controller = new AbortController()
        searchRequest.current.controller = controller
        React.startTransition(() => setSearching(true))
        try {
            const api = (props.apiBase || "https://project-yw131.vercel.app").replace(/\/+$/, "")
            const res = await fetch(
                `${api}/api/stock_news?code=${encodeURIComponent(code)}${nm ? "&name=" + encodeURIComponent(nm) : ""}`,
                { cache: "no-store", signal: controller.signal }
            )
            if (!res.ok) throw new Error("News request failed")
            const d = await res.json()
            if (!d || d.error || !Array.isArray(d.items) || (d.code != null && String(d.code) !== code)) throw new Error("Invalid news response")
            if (!isCurrent()) return
            const items: NewsItem[] = d.items.slice(0, 6).map((n: any) => ({
                title: n.title, url: n.url, source: n.source, time: n.rel_time || "",
                sentiment: "", category: n.category, outlets: n.outlets, credible: n.credible,
            }))
            const rm = recMap[code]
            React.startTransition(() => {
                setSearchGroup({
                    ticker: code, name: nm || (rm ? rm.name : code),
                    market: rm ? rm.market : "KR", sector: rm ? rm.sector : "",
                    industry: rm ? rm.industry : "", items,
                })
                if (!items.length) setSearchMsg("최근 뉴스가 없어요")
            })
        } catch {
            if (!isCurrent()) return
            React.startTransition(() => setSearchMsg("뉴스를 불러오지 못했어요. 종목을 다시 검색해 주세요."))
        } finally {
            if (isCurrent()) {
                searchRequest.current.controller = null
                React.startTransition(() => setSearching(false))
            }
        }
    }
    const editSearch = (value: string) => {
        // 되돌리지 말 것: 입력은 미확정 초안이다. 빈 방문 이력은 명시적 지우기에서만 추가한다.
        clearSearch(false)
        setQ(value)
        setFocused(true)
    }
    const goSearch = () => {
        const s = q.trim()
        if (!s) { clearSearch(); return }
        const exact = matches.find((m) => String(m.ticker).toUpperCase() === s.toUpperCase())
        if (exact) {
            void pickNews(String(exact.ticker), String(exact.name || ""))
        } else if (/^\d{6}$/.test(s) || /^CMD_[A-Z0-9_]+$/i.test(s)) {
            void pickNews(s, "")
        } else if (matches.length) {
            void pickNews(String(matches[0].ticker), String(matches[0].name || ""))
        } else if (newsTicker(s)) {
            void pickNews(s, "")
        } else {
            clearSearch()
            setQ(s)
            React.startTransition(() => setSearchMsg("‘" + s + "’ 종목을 못 찾았어요 (국내 종목명·6자리 코드)"))
        }
    }

    /* URL search subscription: latest handlers without resubscribing on data/input changes. */
    useEffect(() => {
        searchActions.current = { pick: pickNews, clear: clearSearch }
    })
    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        searchLocation.current = null
        const applyLocation = () => {
            const values = new URL(window.location.href).searchParams.getAll("q")
            const signature = JSON.stringify(values)
            if (searchLocation.current === signature) return
            searchLocation.current = signature
            const actions = searchActions.current
            if (!actions) return
            if (!values.length) { actions.clear(false); return }
            const code = values.length === 1 ? newsTicker(values[0]) : ""
            void actions.pick(code, "", false)
        }
        applyLocation()
        const events = ["popstate", "pageshow", "verity-ticker-change"]
        events.forEach((event) => window.addEventListener(event, applyLocation))
        return () => {
            events.forEach((event) => window.removeEventListener(event, applyLocation))
            cancelSearch()
        }
    }, [onCanvas, props.apiBase])
    /* End explicit search lifecycle. */

    // 🚨 2026-07-19 재테마 — root 흰 카드 감싸기 제거(BrokerGuide 동일). 표준 회색페이지: root 투명·자연 흐름 + 개별 흰 카드.
    //   프레임 높이 = 컴포넌트 자연 흐름(@framerSupportedLayoutHeight auto). props.height 미사용(컨트롤 하위호환 존치).
    const wrap: React.CSSProperties = {
        width: "100%",
        maxWidth: 1000,
        marginLeft: "auto",
        marginRight: "auto",
        background: "transparent",
        padding: "8px clamp(14px, 2vw, 20px) 20px",
        display: "flex",
        flexDirection: "column",
        fontFamily:
            "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif",
        boxSizing: "border-box",
        color: C.text,
    }

    return (
        <div ref={rootRef} className="an-news" style={wrap}>
            <style>{AN_PALETTE}</style>
            <style>{`
.an-news :is(.news-insights-trigger,.news-insights-close){min-height:44px;padding:8px 12px;border:0;border-radius:10px;background:var(--an-nws-card);color:var(--an-nws-text);font:inherit;font-size:13px;font-weight:700;line-height:1.6;cursor:pointer;box-sizing:border-box;text-decoration:none}
.an-news .news-header{display:flex;flex-direction:column;gap:13px;padding:0 0 12px}
.an-news .news-heading{display:flex;align-items:baseline;gap:8px;min-width:0}
.an-news .news-market-tabs{display:flex;flex-wrap:wrap;align-items:center;gap:6px;min-width:0}
.an-news .news-market-tab{min-height:36px;line-height:1.25;box-sizing:border-box}
.an-news .news-insights-trigger{white-space:nowrap;min-height:36px;line-height:1.25}
.an-news .news-header-compact{gap:12px}
.an-news .news-header-compact .news-market-tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
.an-news .news-header-compact .news-market-tab{min-width:0;min-height:36px;padding:7px 8px!important;display:flex;align-items:center;justify-content:center;white-space:nowrap;font-size:12px!important}
.an-news .news-tools{display:flex;align-items:center;flex-wrap:nowrap;gap:6px;padding:0 6px 12px;overflow-x:auto}
.an-news .news-sort-control{display:flex;align-items:center;gap:6px;min-width:0;flex:0 0 auto;white-space:nowrap}
.an-news .news-sort-control button{min-height:32px;line-height:1.25;padding:4px 8px!important;box-sizing:border-box;white-space:nowrap}
.an-news .news-secondary-tools{display:flex;align-items:stretch;justify-content:flex-start;gap:6px;margin-left:0;flex:0 0 auto}
.an-news .news-translation-toggle{margin-left:0!important;align-self:stretch!important;flex-shrink:0}
.an-news .news-translation-toggle button{min-height:32px;line-height:1.25;padding:4px 8px!important;box-sizing:border-box;white-space:nowrap}
.an-news .news-tools .news-insights-trigger{min-height:32px;line-height:1.25;padding:4px 8px;font-size:12px;margin-left:0}
.an-news .news-tools-compact .news-sort-control{gap:4px}
.an-news .news-tools-compact :is(.news-sort-control button,.news-translation-toggle button,.news-insights-trigger){font-size:12px!important;padding:4px 6px!important}
.an-news .news-tools-tight{gap:4px}
.an-news .news-tools-tight .news-secondary-tools{gap:4px}
.an-news .news-tools-tight :is(.news-sort-control button,.news-translation-toggle button,.news-insights-trigger){font-size:11px!important;padding:4px 4px!important}
@media(max-width:600px),(pointer:coarse){.an-news .news-market-tab,.an-news .news-header-compact .news-market-tab{min-height:44px}}
.an-news .news-sort-note{display:block;padding:0 6px 10px}
.an-news :is(.news-market-tab[aria-pressed="false"],.news-translation-toggle button[aria-pressed="false"]):focus-visible{outline:none;box-shadow:none;background:var(--an-nws-focus)!important}
@media(hover:hover){.an-news :is(.news-market-tab[aria-pressed="false"],.news-translation-toggle button[aria-pressed="false"]):not(:focus-visible):hover{background:var(--an-nws-hover)!important}}
.an-news .news-mentioned-stock{min-height:44px}
.an-news :is(.news-insights-trigger,.news-insights-close,.news-mentioned-stock):focus-visible{outline:none;box-shadow:none;background:var(--an-nws-focus)!important}
.an-news .news-theme-summary{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:16px;padding:12px 16px;border-radius:16px;background:var(--an-nws-sub);color:var(--an-nws-text);font-size:13px;font-weight:600;line-height:1.6}
.an-news .news-theme-label{flex-basis:100%;color:var(--an-nws-subtext);font-size:12px;font-weight:700}
.an-news .news-theme-item{display:inline-flex;align-items:center;gap:8px;padding:6px 10px;border-radius:10px;background:var(--an-nws-card);font-weight:700}
.an-news .news-theme-count{color:var(--an-nws-subtext);font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.an-news .news-insights-dialog{display:none;position:fixed;inset:0;margin:auto;width:min(800px,calc(100% - 40px));max-width:800px;max-height:calc(100vh - 40px);max-height:calc(100dvh - 40px);padding:0;border:0;border-radius:24px;background:var(--an-nws-card);color:var(--an-nws-text);font:inherit;box-sizing:border-box;overflow:hidden}
.an-news .news-insights-dialog[open]{display:flex;flex-direction:column}
.an-news .news-insights-dialog::backdrop{background:rgba(0,0,0,.45)}
.an-news .news-insights-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-shrink:0;padding:20px 24px 16px}
.an-news .news-insights-head h2{margin:0;min-width:0;font-size:20px;font-weight:800;line-height:1.3}
.an-news .news-insights-close{flex-shrink:0;background:var(--an-nws-sub)}
.an-news .news-insights-content{min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:0 24px 24px;overflow-wrap:anywhere}
.an-news .news-insights-limits{padding:12px 16px;border-radius:16px;background:var(--an-nws-sub);color:var(--an-nws-subtext);font-size:13px;font-weight:600;line-height:1.65}
.an-news .news-insights-limits p{margin:0}
.an-news .news-insights-limits p+p{margin-top:10px}
.an-news .news-insights-limits strong{color:var(--an-nws-text);font-weight:700}
.an-news .news-article-link{border-radius:10px;box-sizing:border-box;transition:background-color 160ms ease}
.an-news .news-flat-card>.news-article-link{height:100%;border-radius:inherit}
.an-news .news-flat-card>.news-article-link>.news-article-body{height:100%;display:flex;flex-direction:column;justify-content:center;box-sizing:border-box;border-radius:inherit}
.an-news .news-article-link:focus-visible{outline:none;box-shadow:none;background:var(--an-nws-focus)!important}
@media(hover:hover){.an-news .news-article-link:not(:focus-visible):hover{background:var(--an-nws-hover)!important}}
@media(prefers-reduced-motion:reduce){.an-news .news-article-link{transition:none}}
@media(max-width:560px){.an-news .news-insights-dialog{inset:auto 0 0;margin:0;width:100%;max-width:100%;max-height:86vh;max-height:86dvh;border-radius:24px 24px 0 0}.an-news .news-insights-head{padding:20px 20px 16px}.an-news .news-insights-content{padding:0 20px calc(20px + env(safe-area-inset-bottom,0px))}}
@media(hover:hover){.an-news :is(.news-insights-trigger,.news-insights-close,.news-mentioned-stock){transition:background-color 160ms ease}.an-news :is(.news-insights-trigger,.news-insights-close,.news-mentioned-stock):not(:focus-visible):hover{background:var(--an-nws-hover)!important}}
@media(prefers-reduced-motion:reduce){.an-news :is(.news-insights-trigger,.news-insights-close,.news-mentioned-stock){transition:none}}
`}</style>
            <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            {/* 헤더 */}
            <div className={narrow ? "news-header news-header-compact" : "news-header"}>
                <div className="news-heading">
                    <h1
                        style={{
                            margin: 0,
                            fontSize: 20,
                            fontWeight: 800,
                            color: C.text,
                            letterSpacing: "-0.4px",
                            lineHeight: 1.3,
                        }}
                    >
                        뉴스
                    </h1>
                    <span
                        style={{
                            fontSize: 12,
                            fontWeight: 600,
                            color: C.faint,
                            lineHeight: 1.5,
                        }}
                    >
                        팩트 헤드라인
                    </span>
                </div>
                    <div className="news-market-tabs">
                    {tabs.map((t) => {
                        const active = tab === t.key
                        return (
                            <button
                                key={t.key}
                                type="button"
                                className="news-market-tab"
                                onClick={() => setTab(t.key)}
                                aria-pressed={active}
                                aria-label={t.label + " " + t.count}
                                style={{
                                    border: "none",
                                    cursor: "pointer",
                                    background: active
                                        ? "#6c5ce7"
                                        : "transparent",
                                    color: active ? "#ffffff" : C.subtext,
                                    fontWeight: active ? 700 : 600,
                                    fontSize: 13,
                                    padding: "7px 15px",
                                    borderRadius: 9,
                                    transition: "all 140ms ease",
                                }}
                            >
                                {narrow && t.key === "stock" ? (memberMode ? "보유종목" : "기기 관심") : t.label}
                                <span
                                    style={{
                                        marginLeft: 6,
                                        color: active
                                            ? "rgba(255,255,255,0.85)"
                                            : C.faint,
                                        fontWeight: 700,
                                    }}
                                >
                                    {t.count}
                                </span>
                            </button>
                        )
                    })}
                    </div>

            </div>

            {/* 오늘 화제 종목 — KR 헤드라인에 언급된 종목(언급 수). 객관·추천 아님. 로고+국기. 가로 스크롤. */}
            {!loading && !failed && hotStocks.length ? (
                <div style={{ marginBottom: 20 }}>
                    <div
                        style={{
                            fontSize: 12.5,
                            fontWeight: 800,
                            color: C.text,
                            padding: "2px 2px 8px",
                            letterSpacing: "-0.01em",
                        }}
                    >
                        시장 전체 화제 종목{" "}
                        <span style={{ color: C.faint, fontWeight: 600 }}>
                            · 수집 뉴스의 종목별 언급 기사 수 · 보유종목과 별개 · 추천 아님
                        </span>
                    </div>
                    <div
                        style={{
                            display: "flex",
                            gap: 8,
                            overflowX: "auto",
                            paddingBottom: 4,
                        }}
                    >
                        {hotStocks.map((s, i) => (
                            <a
                                className="news-mentioned-stock"
                                key={s.ticker}
                                href={
                                    (props.reportPath || "/stock") +
                                    "?q=" +
                                    encodeURIComponent(s.ticker)
                                }
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                    flexShrink: 0,
                                    minWidth: 150,
                                    textDecoration: "none",
                                    background: C.card,
                                    borderRadius: 12,
                                    padding: "10px 12px",
                                    boxSizing: "border-box",
                                    boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 9,
                                }}
                            >
                                <Logo
                                    ticker={s.ticker}
                                    name={s.name}
                                    C={C}
                                    size={26}
                                />
                                <div style={{ minWidth: 0 }}>
                                    <div
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            gap: 5,
                                        }}
                                    >
                                        <span
                                            style={{
                                                fontSize: 11,
                                                fontWeight: 800,
                                                color: C.accent,
                                            }}
                                        >
                                            {i + 1}
                                        </span>
                                        <span
                                            style={{
                                                fontSize: 13,
                                                fontWeight: 800,
                                                color: C.text,
                                                whiteSpace: "nowrap",
                                                overflow: "hidden",
                                                textOverflow: "ellipsis",
                                                maxWidth: 88,
                                            }}
                                        >
                                            {s.name}
                                        </span>
                                    </div>
                                    <div
                                        style={{
                                            fontSize: 11,
                                            fontWeight: 700,
                                            color: C.faint,
                                            marginTop: 2,
                                        }}
                                    >
                                        언급{" "}
                                        <span style={{ color: C.accent }}>
                                            {s.count}회
                                        </span>
                                    </div>
                                </div>
                            </a>
                        ))}
                    </div>
                </div>
            ) : null}
            {!loading && !failed && insights && insights.themes.length ? (
                <div className="news-theme-summary" aria-label="시장 뉴스 키워드 집계">
                    <span className="news-theme-label">시장 뉴스 테마 · 제목 키워드 언급 기사 수 · 매수 신호 아님</span>
                    {insights.themes.slice(0, 3).map((theme) => (
                        <span key={theme.name} className="news-theme-item">
                            <span>{theme.name}</span>
                            <span className="news-theme-count">{theme.n}건</span>
                        </span>
                    ))}
                </div>
            ) : null}
            {/* 본문 */}
            <div
                style={{
                    padding: "4px 0 0",
                }}
            >
                {chosenTab === null && tab !== "stock" && !loading ? (
                    <div role="status" style={{ padding: "0 6px 12px", fontSize: 12, fontWeight: 600, color: C.faint, lineHeight: 1.5 }}>
                        {memberMode
                            ? "현재 보유종목이 없어요. 둥지에 보유종목을 기록하면 여기에 표시돼요."
                            : "등록한 관심종목이 없어요. 시장·미국 뉴스는 개인 목록과 별도로 볼 수 있어요."}
                    </div>
                ) : null}
                <div
                    className={narrow ? (w < 340 ? "news-tools news-tools-compact news-tools-tight" : "news-tools news-tools-compact") : "news-tools"}
                    role="group"
                    aria-label="뉴스 보기 옵션"
                >
                {/* 정렬 세그먼트 — 시장·미국 탭만(직교). 최신/핫/언론사그룹. 조회수 없음(데이터 부재). */}
                {!loading && !activeFeedError && !failed && (tab === "market" || tab === "us") ? (
                    <div className="news-sort-control">
                        <span
                            style={{
                                fontSize: 11,
                                fontWeight: 700,
                                color: C.faint,
                            }}
                        >
                            정렬
                        </span>
                        <div
                            style={{
                                display: "inline-flex",
                                background: C.card,
                                borderRadius: 9,
                                padding: 3,
                                gap: 2,
                            }}
                        >
                            {NEWS_SORTS.map((o) => {
                                const on = mktSort === o.k
                                return (
                                    <button
                                        key={o.k}
                                        type="button"
                                        onClick={() => setMktSort(o.k)}
                                        style={{
                                            border: "none",
                                            cursor: "pointer",
                                            background: on
                                                ? C.sub
                                                : "transparent",
                                            color: on ? C.text : C.subtext,
                                            fontWeight: on ? 700 : 600,
                                            fontSize: 12,
                                            padding: "4px 8px",
                                            borderRadius: 7,
                                            boxShadow: "none",
                                        }}
                                    >
                                        {o.label}
                                    </button>
                                )
                            })}
                        </div>

                    </div>
                ) : null}
                    <div className="news-secondary-tools">
                    {(market.some((it) => it.title && !/[가-힣]/.test(it.title)) ||
                        us.some((it) => it.title && !/[가-힣]/.test(it.title)) ||
                        stocks.some((g) =>
                            g.items.some(
                                (it) => it.title && !/[가-힣]/.test(it.title)
                            )
                        )) && (
                        <div
                            className="news-translation-toggle"
                            style={{
                                marginLeft: "auto",
                                alignSelf: "flex-start",
                                display: "inline-flex",
                                background: C.card,
                                borderRadius: 10,
                                padding: 3,
                                gap: 2,
                            }}
                        >
                            {[
                                { k: false, l: "원문" },
                                { k: true, l: "한글" },
                            ].map((o) => {
                                const active = showKo === o.k
                                return (
                                    <button
                                        key={String(o.k)}
                                        type="button"
                                        onClick={() => setShowKo(o.k)}
                                        aria-pressed={active}
                                        style={{
                                            border: "none",
                                            cursor: "pointer",
                                            background: active
                                                ? C.sub
                                                : "transparent",
                                            color: active ? C.text : C.subtext,
                                            fontWeight: active ? 700 : 600,
                                            fontSize: 12.5,
                                            padding: "4px 8px",
                                            borderRadius: 8,
                                            boxShadow: "none",
                                            transition: "all 140ms ease",
                                        }}
                                    >
                                        {o.l}
                                    </button>
                                )
                            })}
                        </div>
                    )}
                    <button
                        ref={insightsTrigger}
                        type="button"
                        className="news-insights-trigger"
                        aria-haspopup="dialog"
                        onClick={() => setInsightsOpen(true)}
                    >
                        통계·수집 기준
                    </button>
                    </div>

                </div>
                        {!loading && !activeFeedError && !failed && (tab === "market" || tab === "us") && mktSort === "hot" ? (
                            <span className="news-sort-note"
                                style={{
                                    fontSize: 10.5,
                                    color: C.faint,
                                    fontWeight: 600,
                                }}
                            >
                                핫 = 매체 동시보도 + 긴급(자체 산출) · 조회수
                                아님
                            </span>
                        ) : null}
                {loading && tab !== "stock" ? (
                    <NewsSkeleton C={C} />
                ) : (activeFeedError || failed) && tab !== "stock" ? (
                    <div
                        style={{
                            padding: 40,
                            textAlign: "center",
                            color: C.faint,
                            fontSize: 14,
                        }}
                    >
                        {activeFeedError || "뉴스를 불러오지 못했어요."}
                    </div>
                ) : tab === "stock" ? (
                    <>
                        {/* 종목 뉴스 검색 — 표준 검색창(알약+돋보기+로고 autocomplete)과 동기. 픽 → 인라인 뉴스. */}
                        <div
                            style={{
                                position: "relative",
                                padding: "0 6px 10px",
                            }}
                        >
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 7,
                                    background: C.card,
                                    borderRadius: 999,
                                    padding: "9px 14px",
                                    boxSizing: "border-box",
                                }}
                            >
                                <span
                                    style={{
                                        width: 14,
                                        height: 14,
                                        borderRadius: "50%",
                                        border: `2px solid ${C.faint}`,
                                        flexShrink: 0,
                                        position: "relative",
                                        display: "inline-block",
                                    }}
                                >
                                    <span
                                        style={{
                                            position: "absolute",
                                            width: 2,
                                            height: 6,
                                            background: C.faint,
                                            right: -3,
                                            bottom: -3,
                                            transform: "rotate(-45deg)",
                                        }}
                                    />
                                </span>
                                <input
                                    value={q}
                                    onChange={(e) => editSearch(e.target.value)}
                                    aria-label="종목 뉴스 검색"
                                    onFocus={() => setFocused(true)}
                                    onBlur={() =>
                                        setTimeout(() => setFocused(false), 160)
                                    }
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                            setFocused(false)
                                            goSearch()
                                        }
                                    }}
                                    placeholder="종목 뉴스 검색 (이름·코드)"
                                    style={{
                                        border: "none",
                                        outline: "none",
                                        background: "transparent",
                                        color: C.text,
                                        fontFamily: "inherit",
                                        fontSize: 14,
                                        fontWeight: 600,
                                        width: "100%",
                                        minWidth: 0,
                                    }}
                                />
                                {q || searching || selectedTicker ? (
                                    <button
                                        type="button"
                                        onClick={() => clearSearch()}
                                        aria-label="종목 뉴스 검색 지우기"
                                        style={{ border: "none", background: "transparent", color: C.faint, font: "inherit", fontSize: 12, fontWeight: 700, cursor: "pointer", flexShrink: 0 }}
                                    >지우기</button>
                                ) : null}
                                {searching ? (
                                    <span
                                        style={{
                                            fontSize: 11,
                                            color: C.faint,
                                            fontWeight: 700,
                                            flexShrink: 0,
                                        }}
                                    >
                                        검색 중
                                    </span>
                                ) : null}
                            </div>
                            {focused && !!q.trim() && matches.length > 0 ? (
                                <div
                                    style={{
                                        position: "absolute",
                                        top: "100%",
                                        left: 6,
                                        right: 6,
                                        marginTop: -2,
                                        zIndex: 50,
                                        background: C.card,
                                        borderRadius: 12,
                                        boxShadow:
                                            "0 10px 30px rgba(0,0,0,0.16)",
                                        padding: 6,
                                        maxHeight: 320,
                                        overflowY: "auto",
                                    }}
                                >
                                    {matches.map((m) => (
                                        <div
                                            key={m.ticker}
                                            onMouseDown={() =>
                                                pickNews(
                                                    String(m.ticker),
                                                    String(m.name || "")
                                                )
                                            }
                                            style={{
                                                display: "flex",
                                                alignItems: "center",
                                                gap: 8,
                                                padding: "8px 10px",
                                                borderRadius: 9,
                                                cursor: "pointer",
                                            }}
                                        >
                                            <Logo
                                                ticker={m.ticker}
                                                name={m.name}
                                                C={C}
                                                size={28}
                                            />
                                            <span
                                                style={{
                                                    fontSize: 13.5,
                                                    fontWeight: 700,
                                                    color: C.text,
                                                    whiteSpace: "nowrap",
                                                    overflow: "hidden",
                                                    textOverflow: "ellipsis",
                                                }}
                                            >
                                                {m.name}
                                            </span>
                                            <span
                                                style={{
                                                    marginLeft: "auto",
                                                    flexShrink: 0,
                                                    fontSize: 11.5,
                                                    color: C.faint,
                                                    fontWeight: 600,
                                                }}
                                            >
                                                {m.ticker}
                                                {m.market
                                                    ? " · " + m.market
                                                    : ""}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            ) : null}
                        </div>
                        {selectedTicker ? (
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "0 6px 10px", fontSize: 12, fontWeight: 600, color: C.faint }}>
                                <span>선택 종목 · {selectedTicker} · 개인 목록과 별도 검색</span>
                                <a href={newsReportHref(props.reportPath, selectedTicker)} style={{ color: C.accent, fontWeight: 700 }}>이 종목·자산 리포트 보기</a>
                            </div>
                        ) : null}
                        {searchMsg ? (
                            <div
                                role="status"
                                style={{
                                    fontSize: 12,
                                    color: C.faint,
                                    fontWeight: 600,
                                    padding: "0 6px 10px",
                                }}
                            >
                                {searchMsg}
                            </div>
                        ) : null}
                        {searchGroup ? (
                            <div style={{ marginBottom: 18 }}>
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 8,
                                        padding: "0 6px 8px",
                                    }}
                                >
                                    <span
                                        style={{
                                            fontSize: 12,
                                            fontWeight: 800,
                                            color: C.text,
                                        }}
                                    >
                                        검색 결과 · {searchGroup.name}
                                    </span>
                                    <button
                                        type="button"
                                        onClick={() => clearSearch()}
                                        style={{
                                            border: "none",
                                            background: "transparent",
                                            cursor: "pointer",
                                            color: C.faint,
                                            fontSize: 12,
                                            fontWeight: 700,
                                            fontFamily: "inherit",
                                            padding: 0,
                                        }}
                                    >
                                        지우기 ×
                                    </button>
                                </div>
                                <StockNews
                                    groups={[searchGroup]}
                                    C={C}
                                    cardH={344}
                                    showKo={showKo}
                                    reportPath={props.reportPath}
                                />
                            </div>
                        ) : null}
                        <div
                            style={{
                                fontSize: 11,
                                color: C.faint,
                                fontWeight: 600,
                                padding: "0 6px 10px",
                            }}
                        >
                            {personalLoading
                                ? "현재 보유종목을 확인하고 있어요."
                                : personalError
                                  ? personalError
                                  : watch.length
                                    ? memberMode
                                        ? `보유종목 ${watch.length}개 연동 · 보유 수량 0 초과 기준`
                                        : `이 기기의 관심종목 ${watch.length}개 연동`
                                    : memberMode
                                      ? "현재 보유종목이 없어요. 둥지에 보유종목을 기록하면 여기에 표시돼요."
                                      : "관심종목을 별표하면 이 기기에 저장되어 여기에 표시돼요."}
                        </div>
                        {!personalLoading && !personalError && watch.length > 0 ? (
                            <StockNews
                                groups={stocks}
                                C={C}
                                cardH={props.stockCardHeight || 232}
                                showKo={showKo}
                                reportPath={props.reportPath}
                            />
                        ) : null}
                    </>
                ) : tab === "market" ? (
                    <FlatNews
                        key={"market-" + mktSort}
                        items={market}
                        C={C}
                        empty="시장 뉴스가 없어요."
                        cardH={props.marketCardHeight || 92}
                        showKo={showKo}
                        sortMode={mktSort}
                    />
                ) : (
                    <FlatNews
                        key={"us-" + mktSort}
                        items={us}
                        C={C}
                        empty="미국 뉴스가 없어요."
                        cardH={props.marketCardHeight || 92}
                        showKo={showKo}
                        sortMode={mktSort}
                    />
                )}
                <dialog
                    ref={insightsDialog}
                    className="news-insights-dialog"
                    aria-labelledby="news-insights-title"
                    onCancel={(event) => {
                        event.preventDefault()
                        setInsightsOpen(false)
                    }}
                    onClose={(event) => {
                        if (!event.currentTarget.open) setInsightsOpen(false)
                    }}
                >
                    <div className="news-insights-head">
                        <h2 id="news-insights-title">통계·수집 기준</h2>
                        <button
                            ref={insightsClose}
                            type="button"
                            className="news-insights-close"
                            aria-label="통계·수집 기준 닫기"
                            onClick={() => setInsightsOpen(false)}
                        >닫기</button>
                    </div>
                    <div className="news-insights-content">
                        {insightsOpen && !loading && !failed && insights ? (
                            <NewsInsights
                                ins={insights}
                                C={C}
                                reportPath={props.reportPath}
                            />
                        ) : (
                            <p style={{ fontSize: 13, fontWeight: 600, color: C.subtext }}>표시할 통계가 아직 없어요.</p>
                        )}
                        <div className="news-insights-limits">
                            <p><strong>수집 범위</strong> · 시장 헤드라인 수집 묶음 기준이며, 선택한 종목·미국 탭의 통계가 아니에요. 출처·신선도·제목 표현은 수집한 국내 헤드라인, 테마는 화면에 표시할 시장 제목 기준으로 집계해 서로 건수가 다를 수 있어요. 전체 보도를 포함하지 않으며, 종목 언급은 한국어 시장 제목의 국내 종목만 세고 보유종목과 별개예요.</p>
                            <p><strong>시간 기준</strong> · 통계는 현재 수집 묶음 기준으로, 오늘 기사만 뜻하지 않아요. 시장·미국은 최근 {FLASH_WINDOW_DAYS}일을 우선하되 {FLASH_FLOOR}건 미만이면 오래된 기사도 포함해요. 종목 뉴스도 최근 30일을 우선하되 부족하면 이전 기사가 포함될 수 있어요. 발행 시각이 없거나 수집이 늦을 수 있으니 기사별 출처·시각·원문을 확인해 주세요.</p>
                            <p><strong>분류 한계</strong> · 출처 신뢰도와 제목 표현은 자동 분류(검증 전)예요. ‘신선도’는 비슷한 제목의 반복 여부로, 최신성이나 사실 확인을 뜻하지 않아요. 한 기사에 여러 테마가 잡힐 수 있고, 키워드·종목 언급 수는 매수 신호나 가격 방향이 아니에요.</p>
                        </div>
                    </div>
                </dialog>
            </div>
        </div>
    )
}

/* 로딩 스켈레톤 — 뉴스 카드 그리드 형태(제목 2줄 + 메타 1줄). shimmer. */
function NewsSkeleton(props: { C: any }) {
    const { C } = props
    const base = C.skBase
    const hi = C.skHi
    const bar = (
        w: string | number,
        h: number,
        mt: number
    ): React.CSSProperties => ({
        width: w,
        height: h,
        marginTop: mt,
        borderRadius: 5,
        background: base,
        backgroundImage:
            "linear-gradient(90deg, " +
            base +
            " 25%, " +
            hi +
            " 37%, " +
            base +
            " 63%)",
        backgroundSize: "800px 100%",
        animation: "vsrShimmer 1.4s ease-in-out infinite",
    })
    const cards = [0, 1, 2, 3, 4, 5, 6, 7]
    return (
        <div
            style={{
                display: "grid",
                gridTemplateColumns:
                    "repeat(auto-fill, minmax(min(340px, 100%), 1fr))",
                gap: 8,
                alignItems: "start",
            }}
        >
            {cards.map((i) => (
                <div
                    key={i}
                    style={{
                        background: C.card,
                        borderRadius: 12,
                        padding: "14px 16px",
                        boxSizing: "border-box",
                        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                    }}
                >
                    <div style={bar("92%", 13, 0)} />
                    <div style={bar("68%", 13, 7)} />
                    <div style={bar(90, 10, 14)} />
                </div>
            ))}
        </div>
    )
}

/* 도넛 차트 — conic-gradient 링 + 중앙 구멍(외부 lib 0). SVG stroke-dash 이음새 아티팩트 제거.
   애니: 마운트 시 링을 시계방향 draw-in(마스크 스윕) + 중앙 숫자 카운트업. RAF 구동.
   세션 1회만 재생(sessionStorage) + prefers-reduced-motion 정적. 중앙 = HTML 플렉스 오버레이. */
const DONUT_ANIM_KEY = "news_donut_anim_v1"
function Donut(props: {
    segs: { label: string; n: number; color: string }[]
    C: any
    size?: number
    thickness?: number
    centerValue?: number // 중앙 숫자(카운트업 대상)
    centerSuffix?: string // "%" | ""
    centerSub?: string
    index?: number // stagger 지연용
}) {
    const size = props.size || 72
    const th = props.thickness || 11
    const hole = size - th * 2
    const active = props.segs.filter((s) => s.n > 0)
    const total = active.reduce((a, b) => a + b.n, 0) || 1
    // conic-gradient 세그먼트 stops — 누적 비율, 하드 경계(이음새 없는 연속 링).
    let acc = 0
    const stops: string[] = []
    for (const s of active) {
        const start = (acc / total) * 100
        acc += s.n
        const end = (acc / total) * 100
        stops.push(`${s.color} ${start}% ${end}%`)
    }
    const ring = stops.length
        ? `conic-gradient(${stops.join(", ")})`
        : props.C.sub

    // 진행도 p (0→1). 기본 1(정적) — 애니 조건 충족 시 0부터 RAF 구동.
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [p, setP] = useState<number>(1)
    useEffect(() => {
        if (typeof window === "undefined") return
        const reduce = !!(
            window.matchMedia &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches
        )
        let played = false
        try {
            played = sessionStorage.getItem(DONUT_ANIM_KEY) === "1"
        } catch (e) {}
        if (onCanvas || reduce || played) {
            setP(1)
            return
        }
        const delay = (props.index || 0) * 90 // 카드별 시차(stagger)
        const dur = 700
        let raf = 0
        let start = 0
        setP(0)
        const tick = (t: number) => {
            if (!start) start = t
            const elapsed = t - start - delay
            if (elapsed < 0) {
                raf = requestAnimationFrame(tick)
                return
            }
            const prog = Math.min(1, elapsed / dur)
            setP(1 - Math.pow(1 - prog, 3)) // ease-out cubic
            if (prog < 1) {
                raf = requestAnimationFrame(tick)
            } else {
                try {
                    sessionStorage.setItem(DONUT_ANIM_KEY, "1")
                } catch (e) {}
            }
        }
        raf = requestAnimationFrame(tick)
        return () => cancelAnimationFrame(raf)
    }, [onCanvas, props.index])

    // 링 시계방향 공개 마스크(top=0deg 기준, conic 기본 시작점과 정합). p=0 숨김 → p=1 전체.
    const ang = Math.round(p * 3600) / 10 // deg, 소수 1자리
    const mask = `conic-gradient(#000 ${ang}deg, transparent ${ang}deg)`
    const centerText =
        props.centerValue != null
            ? Math.round(props.centerValue * p) + (props.centerSuffix || "")
            : undefined

    return (
        <div
            style={{
                position: "relative",
                width: size,
                height: size,
                flexShrink: 0,
            }}
            title={active.map((s) => s.label + " " + s.n).join(" · ")}
        >
            <div
                style={{
                    width: size,
                    height: size,
                    borderRadius: "50%",
                    background: ring,
                    WebkitMaskImage: mask,
                    maskImage: mask,
                }}
            />
            <div
                style={{
                    position: "absolute",
                    top: th,
                    left: th,
                    width: hole,
                    height: hole,
                    borderRadius: "50%",
                    background: props.C.card,
                }}
            />
            {centerText || props.centerSub ? (
                <div
                    style={{
                        position: "absolute",
                        inset: 0,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        lineHeight: 1.05,
                        pointerEvents: "none",
                    }}
                >
                    {centerText ? (
                        <span
                            style={{
                                fontSize: Math.round(size * 0.22),
                                fontWeight: 800,
                                color: props.C.text,
                                letterSpacing: "-0.03em",
                            }}
                        >
                            {centerText}
                        </span>
                    ) : null}
                    {props.centerSub ? (
                        <span
                            style={{
                                fontSize: Math.round(size * 0.13),
                                fontWeight: 700,
                                color: props.C.faint,
                                marginTop: 2,
                            }}
                        >
                            {props.centerSub}
                        </span>
                    ) : null}
                </div>
            ) : null}
        </div>
    )
}

/* 도넛 범례 한 줄 — 색점 + 라벨 + 건수. */
function LegendRow(props: { color: string; label: string; n: number; C: any }) {
    return (
        <div
            style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                width: "100%",
            }}
        >
            <span
                style={{
                    width: 8,
                    height: 8,
                    borderRadius: 3,
                    background: props.color,
                    flexShrink: 0,
                }}
            />
            <span
                style={{
                    color: props.C.subtext,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                }}
            >
                {props.label}
            </span>
            <span
                style={{
                    marginLeft: "auto",
                    paddingLeft: 6,
                    color: props.C.text,
                    fontWeight: 800,
                    flexShrink: 0,
                }}
            >
                {props.n}
            </span>
        </div>
    )
}

const _pctN = (n: number, t: number) => (t > 0 ? Math.round((n / t) * 100) : 0)
const THEME_COLORS = [
    "#6c5ce7",
    "#0ca678",
    "#f59f00",
    "#e64980",
    "#4dabf7",
    "#7048e8",
]

/* 오늘의 뉴스 한눈 — 출처 신뢰도 / 신선도(MinHash) / 키워드 무드 / 뉴스 많은 종목. 전부 사실 집계(RULE7). */
function NewsInsights(props: { ins: Insights; C: any; reportPath?: string }) {
    const { ins, C } = props
    const tile: React.CSSProperties = {
        flex: "1 1 190px",
        minWidth: 168,
        minHeight: 130,
        background: C.card,
        borderRadius: 12,
        padding: "12px 14px",
        boxSizing: "border-box",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
    }
    const lbl: React.CSSProperties = {
        fontSize: 11,
        fontWeight: 700,
        color: C.faint,
        marginBottom: 8,
    }
    const row: React.CSSProperties = {
        display: "flex",
        alignItems: "center",
        gap: 12,
        marginTop: 4,
    }
    const leg: React.CSSProperties = {
        display: "flex",
        flexDirection: "column",
        gap: 5,
        fontSize: 11.5,
        fontWeight: 700,
        minWidth: 74,
    }
    return (
        <div style={{ marginBottom: 28 }}>
            <div
                style={{
                    fontSize: 12.5,
                    fontWeight: 800,
                    color: C.text,
                    padding: "2px 2px 8px",
                    letterSpacing: "-0.01em",
                }}
            >
                오늘의 뉴스 한눈{" "}
                <span style={{ color: C.faint, fontWeight: 600 }}>
                    · 사실 집계
                </span>
            </div>
            <div
                style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 8,
                    alignItems: "flex-start",
                }}
            >
                {/* 출처 신뢰도 (자체 점수화 — 1차/신뢰 출처 비중) */}
                <div style={tile}>
                    <div style={lbl}>
                        출처 신뢰도 · 총 {ins.total}건{" "}
                        <span style={{ color: C.faint, fontWeight: 600 }}>
                            · 자체 분류(가설, N={ins.total})
                        </span>
                    </div>
                    <div style={row}>
                        <Donut
                            C={C}
                            index={0}
                            centerValue={_pctN(ins.credHi, ins.total)}
                            centerSuffix="%"
                            centerSub="신뢰"
                            segs={[
                                {
                                    label: "신뢰",
                                    n: ins.credHi,
                                    color: "#0ca678",
                                },
                                {
                                    label: "일반",
                                    n: ins.credLo,
                                    color: C.border,
                                },
                            ]}
                        />
                        <div style={leg}>
                            <LegendRow
                                color="#0ca678"
                                label="신뢰 출처"
                                n={ins.credHi}
                                C={C}
                            />
                            <LegendRow
                                color={C.border}
                                label="일반"
                                n={ins.credLo}
                                C={C}
                            />
                        </div>
                    </div>
                </div>
                {/* 신선도 */}
                <div style={tile}>
                    <div style={lbl}>신선도 · 신규 vs 재탕</div>
                    <div style={row}>
                        <Donut
                            C={C}
                            index={1}
                            centerValue={_pctN(ins.fresh, ins.fresh + ins.dup)}
                            centerSuffix="%"
                            centerSub="신규"
                            segs={[
                                {
                                    label: "신규",
                                    n: ins.fresh,
                                    color: C.accent,
                                },
                                { label: "재탕", n: ins.dup, color: C.border },
                            ]}
                        />
                        <div style={leg}>
                            <LegendRow
                                color={C.accent}
                                label="신규"
                                n={ins.fresh}
                                C={C}
                            />
                            <LegendRow
                                color={C.border}
                                label="재탕"
                                n={ins.dup}
                                C={C}
                            />
                        </div>
                    </div>
                </div>
                {/* 제목의 긍정/부정 표현 집계 — 종목의 투자 효과가 아님 */}
                <div style={tile}>
                    <div style={lbl}>
                        제목 표현 분류{" "}
                        <span style={{ color: C.faint, fontWeight: 600 }}>
                            · 검증 전
                        </span>
                    </div>
                    <div style={row}>
                        <Donut
                            C={C}
                            index={2}
                            centerValue={_pctN(
                                ins.pos,
                                ins.pos + ins.neu + ins.neg
                            )}
                            centerSuffix="%"
                            centerSub="긍정"
                            segs={[
                                { label: "제목 긍정 표현", n: ins.pos, color: C.up },
                                { label: "중립", n: ins.neu, color: C.border },
                                { label: "제목 부정 표현", n: ins.neg, color: C.down },
                            ]}
                        />
                        <div style={leg}>
                            <LegendRow
                                color={C.up}
                                label="긍정 표현"
                                n={ins.pos}
                                C={C}
                            />
                            <LegendRow
                                color={C.border}
                                label="중립"
                                n={ins.neu}
                                C={C}
                            />
                            <LegendRow
                                color={C.down}
                                label="부정 표현"
                                n={ins.neg}
                                C={C}
                            />
                        </div>
                    </div>
                </div>
                {/* '뉴스 많은 종목' 타일 → 상단 '오늘 핫한 종목' 스트립으로 이전(중복 제거, 2026-07-05) */}
                {/* 오늘의 뉴스 테마 (제목 키워드 빈도 — LLM 아님, 단어 카운트) → 도넛 */}
                {ins.themes.length ? (
                    <div style={{ ...tile, flexBasis: 300, minWidth: 236 }}>
                        <div style={lbl}>
                            오늘의 뉴스 테마{" "}
                            <span style={{ color: C.faint, fontWeight: 600 }}>
                                · 키워드 빈도(도넛 = 언급 수)
                            </span>
                        </div>
                        <div style={row}>
                            <Donut
                                C={C}
                                size={78}
                                index={3}
                                centerValue={ins.themes
                                    .slice(0, 6)
                                    .reduce((a, b) => a + b.n, 0)}
                                centerSuffix=""
                                centerSub="언급"
                                segs={ins.themes.slice(0, 6).map((th, i) => ({
                                    label: th.name,
                                    n: th.n,
                                    color: THEME_COLORS[
                                        i % THEME_COLORS.length
                                    ],
                                }))}
                            />
                            <div style={{ ...leg, flex: 1 }}>
                                {ins.themes.slice(0, 5).map((th, i) => (
                                    <LegendRow
                                        key={th.name}
                                        color={
                                            THEME_COLORS[
                                                i % THEME_COLORS.length
                                            ]
                                        }
                                        label={th.name}
                                        n={th.n}
                                        C={C}
                                    />
                                ))}
                            </div>
                        </div>
                    </div>
                ) : null}
            </div>
        </div>
    )
}

function MarketBadge(props: { market: string; C: any }) {
    const m = (props.market || "").toUpperCase()
    if (!m) return null
    const isKR = m.indexOf("KOS") >= 0 || m === "KR" || m.indexOf("KRX") >= 0
    return (
        <span
            style={{
                fontSize: 10.5,
                fontWeight: 700,
                color: props.C.faint,
                background: props.C.chipBg,
                borderRadius: 5,
                padding: "2px 6px",
            }}
        >
            {isKR ? "KR" : m}
        </span>
    )
}

/* 제목 표현 분류 — 카드 끝에는 기존 위·아래 화살표만 쓴다. */
function SentChip(props: { s: string; C: any }) {
    const s = props.s
    if (s !== "positive" && s !== "negative") return null
    const pos = s === "positive"
    const C = props.C
    const col = pos ? C.up : C.down
    const bg = pos ? C.upBg : C.downBg
    return (
        <span
            style={{
                flexShrink: 0,
                marginTop: 1,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 20,
                height: 20,
                borderRadius: 6,
                background: bg,
            }}
            title={(pos ? "제목 긍정 표현" : "제목 부정 표현") + " · 키워드 자동분류(검증 전), 투자 효과·가격 방향 아님"}
            aria-label={pos ? "제목 긍정 표현" : "제목 부정 표현"}
        >
            <svg
                width={11}
                height={11}
                viewBox="0 0 12 12"
                fill="none"
                style={{ stroke: col }}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
            >
                {pos ? (
                    <>
                        <line x1="6" y1="10" x2="6" y2="2.6" />
                        <polyline points="2.8,5.6 6,2.4 9.2,5.6" />
                    </>
                ) : (
                    <>
                        <line x1="6" y1="2" x2="6" y2="9.4" />
                        <polyline points="2.8,6.4 6,9.6 9.2,6.4" />
                    </>
                )}
            </svg>
        </span>
    )
}

/* 섹터 배지 — 종목의 섹터(멤버십 사실, 영향·수혜 아님). */
function SectorBadge(props: { sector: string; industry: string; C: any }) {
    const label = sectorLabel(props.sector)
    if (!label) return null
    return (
        <span
            style={{
                fontSize: 10.5,
                fontWeight: 700,
                color: props.C.accent,
                background: props.C.chipBg,
                borderRadius: 5,
                padding: "2px 7px",
            }}
            title={props.industry || props.sector}
        >
            {label}
        </span>
    )
}

function NewsRow(props: {
    item: NewsItem
    C: any
    clamp?: number
    showKo?: boolean
}) {
    const { item, C } = props
    const clamp = props.clamp || 2
    const ko = !!(props.showKo && item.titleKo && item.titleKo !== item.title)
    const shownTitle = ko ? (item.titleKo as string) : item.title
    const body = (
        <div
            className="news-article-body"
            style={{
                padding: "11px 8px",
                borderRadius: 10,
                cursor: item.url ? "pointer" : "default",
            }}
        >
            <div style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
                <span
                    style={{
                        flex: 1,
                        minWidth: 0,
                        fontSize: 14,
                        fontWeight: 600,
                        color: C.text,
                        lineHeight: 1.45,
                        letterSpacing: "-0.01em",
                        display: "-webkit-box",
                        WebkitLineClamp: clamp,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                        overflowWrap: "anywhere",
                    }}
                >
                    {shownTitle}
                </span>
                <SentChip s={item.sentiment} C={C} />
            </div>
            <div
                style={{
                    marginTop: 5,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    flexWrap: "wrap",
                }}
            >
                {item.category ? (
                    <span
                        style={{
                            fontSize: 10,
                            fontWeight: 800,
                            color: C.accent,
                            background: C.sub,
                            borderRadius: 5,
                            padding: "1px 6px",
                            whiteSpace: "nowrap",
                        }}
                    >
                        {item.category}
                    </span>
                ) : null}
                {ko ? (
                    <span
                        style={{
                            fontSize: 10,
                            fontWeight: 700,
                            color: C.accent,
                            background: C.bg,
                            borderRadius: 5,
                            padding: "1px 6px",
                        }}
                    >
                        AI 번역
                    </span>
                ) : null}
                {item.source ? (
                    <span
                        style={{
                            fontSize: 11.5,
                            fontWeight: 600,
                            color: C.subtext,
                        }}
                    >
                        {item.source}
                        {item.credible ? " ✓" : ""}
                    </span>
                ) : null}
                {item.time ? (
                    <>
                        <span
                            style={{
                                width: 2,
                                height: 2,
                                borderRadius: 2,
                                background: C.faint,
                            }}
                        />
                        <span style={{ fontSize: 11.5, color: C.faint }}>
                            {item.time}
                        </span>
                    </>
                ) : null}
                {item.outlets && item.outlets > 1 ? (
                    <span
                        style={{
                            fontSize: 10.5,
                            fontWeight: 700,
                            color: C.faint,
                        }}
                    >
                        · {item.outlets}개 매체
                    </span>
                ) : null}
            </div>
        </div>
    )
    if (!item.url) return body
    return (
        <a
            className="news-article-link"
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ textDecoration: "none", display: "block" }}
        >
            {body}
        </a>
    )
}

function FlatNews(props: {
    items: NewsItem[]
    C: any
    empty: string
    cardH: number
    showKo?: boolean
    sortMode: string
}) {
    const { items, C, cardH, sortMode } = props
    const [shown, setShown] = useState(15) // 초기 노출, 더보기 +15 (key=탭+정렬 로 모드 바뀌면 리셋)
    if (!items.length) {
        return (
            <div
                style={{
                    padding: 40,
                    textAlign: "center",
                    color: C.faint,
                    fontSize: 14,
                }}
            >
                {props.empty}
            </div>
        )
    }
    const foot = (
        <div
            style={{
                padding: "12px 8px 2px",
                fontSize: 10.5,
                color: C.faint,
                fontWeight: 600,
                lineHeight: 1.5,
            }}
        >
            제목 긍정·부정 표현 = 키워드 자동분류(검증 전) · 투자 효과나 가격 방향을 뜻하지 않아요.
        </div>
    )
    const moreBtn = (total: number, unit: string) =>
        total > shown ? (
            <button
                type="button"
                onClick={() => setShown((s) => s + 15)}
                style={{
                    width: "100%",
                    marginTop: 10,
                    border: "none",
                    cursor: "pointer",
                    background: C.card,
                    color: C.accent,
                    borderRadius: 10,
                    padding: "11px 0",
                    fontSize: 12.5,
                    fontWeight: 800,
                }}
            >
                더보기 ({total - shown}개 {unit})
            </button>
        ) : null

    // 언론사 그룹 모드 — 정렬 아니라 언론사로 묶어 보기(많이 보도한 순)
    if (sortMode === "outlet") {
        const bySrc: Record<string, NewsItem[]> = {}
        for (const it of items) {
            const s = it.source || "기타"
            ;(bySrc[s] = bySrc[s] || []).push(it)
        }
        const groups = Object.keys(bySrc)
            .map((s) => ({
                source: s,
                items: bySrc[s]
                    .slice()
                    .sort((a, b) => (b.ts || 0) - (a.ts || 0)),
            }))
            .sort(
                (a, b) =>
                    b.items.length - a.items.length ||
                    a.source.localeCompare(b.source)
            )
        return (
            <div>
                <div
                    style={{
                        display: "grid",
                        gridTemplateColumns:
                            "repeat(auto-fill, minmax(min(330px, 100%), 1fr))",
                        gap: 10,
                        alignItems: "start",
                    }}
                >
                    {groups.slice(0, shown).map((g, i) => (
                        <div
                            key={i}
                            style={{
                                background: C.card,
                                borderRadius: 14,
                                padding: "12px 12px 6px 12px",
                                boxSizing: "border-box",
                                boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                            }}
                        >
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 6,
                                    padding: "0 8px 4px 8px",
                                }}
                            >
                                <span
                                    style={{
                                        fontSize: 13.5,
                                        fontWeight: 800,
                                        color: C.text,
                                        letterSpacing: "-0.01em",
                                    }}
                                >
                                    {g.source}
                                </span>
                                <span
                                    style={{
                                        fontSize: 11.5,
                                        fontWeight: 700,
                                        color: C.accent,
                                    }}
                                >
                                    {g.items.length}
                                </span>
                            </div>
                            {g.items.slice(0, 4).map((it, j) => (
                                <NewsRow
                                    key={j}
                                    item={it}
                                    C={C}
                                    clamp={1}
                                    showKo={props.showKo}
                                />
                            ))}
                        </div>
                    ))}
                </div>
                {moreBtn(groups.length, "언론사")}
                {foot}
            </div>
        )
    }

    // 최신(발행시각) / 핫(composite_score) 정렬
    const sorted = items
        .slice()
        .sort((a, b) =>
            sortMode === "hot"
                ? (b.score || 0) - (a.score || 0)
                : (b.ts || 0) - (a.ts || 0)
        )
    return (
        <div>
            <div
                style={{
                    display: "grid",
                    gridTemplateColumns:
                        "repeat(auto-fill, minmax(min(340px, 100%), 1fr))",
                    gap: 8,
                    alignItems: "start",
                }}
            >
                {sorted.slice(0, shown).map((it, i) => (
                    <div
                        key={i}
                        className="news-flat-card"
                        style={{
                            height: cardH,
                            overflow: "hidden",
                            background: C.card,
                            borderRadius: 12,
                            boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                            display: "flex",
                            flexDirection: "column",
                            justifyContent: "center",
                        }}
                    >
                        <NewsRow
                            item={it}
                            C={C}
                            clamp={2}
                            showKo={props.showKo}
                        />
                    </div>
                ))}
            </div>
            {moreBtn(sorted.length, "뉴스")}
            {foot}
        </div>
    )
}

function StockNews(props: {
    groups: StockGroup[]
    C: any
    cardH: number
    showKo?: boolean
    reportPath?: string
}) {
    const { groups, C, cardH } = props
    if (!groups.length) {
        return (
            <div
                style={{
                    padding: 40,
                    textAlign: "center",
                    color: C.faint,
                    fontSize: 14,
                }}
            >
                표시할 종목 뉴스가 없어요.
            </div>
        )
    }
    return (
        <div
            style={{
                display: "grid",
                gridTemplateColumns:
                    "repeat(auto-fill, minmax(min(330px, 100%), 1fr))",
                gap: 10,
                alignItems: "start",
            }}
        >
            {groups.map((g, i) => (
                <div
                    key={i}
                    style={{
                        height: cardH,
                        overflow: "hidden",
                        background: C.card,
                        borderRadius: 14,
                        padding: "12px 12px 6px 12px",
                        boxSizing: "border-box",
                        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                    }}
                >
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            flexWrap: "wrap",
                            gap: 7,
                            padding: "0 8px 4px 8px",
                        }}
                    >
                        {g.ticker ? (
                            <a
                                href={
                                    (props.reportPath || "/stock") +
                                    "?q=" +
                                    encodeURIComponent(g.ticker)
                                }
                                target="_blank"
                                rel="noopener noreferrer"
                                title={(g.name || g.ticker) + " 분석"}
                                style={{
                                    fontSize: 14.5,
                                    fontWeight: 800,
                                    color: C.accent,
                                    letterSpacing: "-0.01em",
                                    textDecoration: "none",
                                }}
                            >
                                {g.name || g.ticker} ↗
                            </a>
                        ) : (
                            <span
                                style={{
                                    fontSize: 14.5,
                                    fontWeight: 800,
                                    color: C.text,
                                    letterSpacing: "-0.01em",
                                }}
                            >
                                {g.name || g.ticker}
                            </span>
                        )}
                        {g.ticker && g.ticker !== g.name ? (
                            <span
                                style={{
                                    fontSize: 12,
                                    fontWeight: 600,
                                    color: C.faint,
                                }}
                            >
                                {g.ticker}
                            </span>
                        ) : null}
                        <MarketBadge market={g.market} C={C} />
                        <SectorBadge
                            sector={g.sector}
                            industry={g.industry}
                            C={C}
                        />
                    </div>
                    {g.items.length ? (
                        g.items.map((it, j) => (
                            <NewsRow
                                key={j}
                                item={it}
                                C={C}
                                clamp={1}
                                showKo={props.showKo}
                            />
                        ))
                    ) : (
                        <div
                            style={{
                                fontSize: 11.5,
                                color: C.faint,
                                fontWeight: 600,
                                padding: "10px 8px",
                            }}
                        >
                            최근 관련 뉴스가 없어요
                        </div>
                    )}
                </div>
            ))}
        </div>
    )
}

addPropertyControls(PublicNewsTab, {
    dark: {
        type: ControlType.Boolean,
        title: "다크(캔버스)",
        defaultValue: false,
    },
    recUrl: {
        type: ControlType.String,
        title: "추천 JSON",
        defaultValue: BLOB + "/recommendations.json",
    },
    portfolioUrl: {
        type: ControlType.String,
        title: "포트폴리오 JSON",
        defaultValue: BLOB + "/portfolio.json",
    },
    maxPerStock: {
        type: ControlType.Number,
        title: "종목당 기사",
        defaultValue: 3,
        min: 1,
        max: 8,
        step: 1,
    },
    maxMarket: {
        type: ControlType.Number,
        title: "시장 기사 수",
        defaultValue: 30,
        min: 5,
        max: 60,
        step: 5,
    },
    height: {
        type: ControlType.Number,
        title: "높이",
        defaultValue: 720,
        min: 320,
        max: 1600,
        step: 20,
        unit: "px",
    },
    marketCardHeight: {
        type: ControlType.Number,
        title: "시장 카드 높이",
        defaultValue: 92,
        min: 72,
        max: 200,
        step: 4,
        unit: "px",
    },
    stockCardHeight: {
        type: ControlType.Number,
        title: "종목 카드 높이",
        defaultValue: 232,
        min: 120,
        max: 400,
        step: 4,
        unit: "px",
    },
    reportPath: {
        type: ControlType.String,
        title: "리포트 경로",
        defaultValue: "/stock",
    },
    apiBase: {
        type: ControlType.String,
        title: "API Base",
        defaultValue: "https://project-yw131.vercel.app",
    },
})

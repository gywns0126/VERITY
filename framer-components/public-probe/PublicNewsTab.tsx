import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useMemo, useState } from "react"

/**
 * AlphaNest 뉴스 탭 (공개) — 팩트형.
 *
 * 우리 종목 연동형: recommendations.json 의 종목별 sentiment.top_headline_links 를
 * "내 종목 뉴스" 로, portfolio.json 의 headlines / us_headlines 를 "시장 / 미국" 으로 노출.
 *
 * RULE 6 (LLM narrative STOP): 제목 + 출처 + 시각 + 원문 링크만. 해설/요약 0.
 * RULE 7: 호재/악재 칩 = 시장·미국 탭만(portfolio.headlines.sentiment = 키워드 자동분류, "검증 전" 라벨 명시).
 *   점수·등급·방향성 영향 추론은 미노출. 섹터 = 종목 멤버십 사실(영향·수혜 아님).
 *   출처 신뢰도(credibility≥0.8 자체 분류)도 "가설/N=" 표기(2026-07-04 사이트 감사 P1).
 *
 * 다크모드: body[data-framer-theme] 추종 (다른 public 컴포넌트와 동일 패턴).
 *  - 캔버스 에디터: dark prop 정적 프리뷰 (RenderTarget.canvas 가드)
 */

const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"

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

const LIGHT = {
    bg: "#ffffff",
    card: "#f9fafb",
    sub: "#f2f4f6",
    text: "#191f28",
    subtext: "#6b7280",
    faint: "#8b95a1",
    border: "#e5e8eb",
    accent: "#6c5ce7",
    chipBg: "#f2f4f6",
    up: "#f04452",
    down: "#3182f6",
    upBg: "#fdecee",
    downBg: "#eaf1fe",
}
const DARK = {
    bg: "#171c23",
    card: "#1e242c",
    sub: "#222933",
    text: "#f2f4f6",
    subtext: "#9aa4b1",
    faint: "#6b7682",
    border: "#2b3138",
    accent: "#a99bff",
    chipBg: "#222933",
    up: "#f04452",
    down: "#5b9bff",
    upBg: "#2a1a1d",
    downBg: "#17263c",
}

// GICS/yfinance 섹터 EN→KR (멤버십 사실 라벨). 미스 시 원문.
const SECTOR_KR: Record<string, string> = {
    "Basic Materials": "기초소재",
    "Communication Services": "커뮤니케이션",
    "Consumer Cyclical": "경기소비재",
    "Consumer Defensive": "필수소비재",
    "Energy": "에너지",
    "Financial Services": "금융",
    "Financial": "금융",
    "Healthcare": "헬스케어",
    "Industrials": "산업재",
    "Real Estate": "부동산",
    "Technology": "기술",
    "Utilities": "유틸리티",
}
function sectorLabel(s: string): string {
    if (!s) return ""
    return SECTOR_KR[s] || s
}

type Tab = "stock" | "market" | "us"

interface NewsItem {
    title: string
    titleKo?: string
    url: string
    source: string
    time: string
    sentiment: string
    category?: string   // Naver 종목뉴스 enrichment (내 종목 탭)
    outlets?: number    // 같은 사안 보도 매체 수
    credible?: boolean  // 신뢰 출처(✓)
    ts?: number         // 정렬용 발행시각(ms) — 0=시각없음(뒤로)
    score?: number      // composite_score (핫 정렬 · 매체동시보도+긴급 자체 산출)
}
interface StockGroup {
    ticker: string
    name: string
    market: string
    sector: string
    industry: string
    items: NewsItem[]
}
// 오늘 핫한 종목 — recommendations[].sentiment.headline_count(종목별 뉴스량) 순. 사실(뉴스 건수), 추천·등급 아님.
interface HotStock { ticker: string; name: string; market: string; count: number; score: number }

/* 오늘의 뉴스 한눈 — 전부 기존 사실 집계(RULE7, LLM 해석 0). 출처신뢰도·신선도·무드·테마빈도. */
interface Insights {
    total: number
    credHi: number; credLo: number         // 출처 신뢰도(credibility>=0.8=신뢰 출처, 자체 점수화)
    fresh: number; dup: number             // 신선도(near_duplicate MinHash)
    pos: number; neg: number; neu: number  // 무드(sentiment 키워드)
    themes: { name: string; n: number }[]  // 오늘의 테마(키워드 빈도, 단어 카운트만)
}
// 뉴스 테마 사전 — 제목 키워드 매칭으로 "오늘 시장 화두" 집계(LLM 아님, 순수 빈도). 사실 집계 RULE7.
const THEME_KEYWORDS: [string, string[]][] = [
    ["반도체", ["반도체", "HBM", "메모리", "D램", "낸드", "파운드리", "엔비디아", "TSMC"]],
    ["금리·환율", ["금리", "연준", "FOMC", "기준금리", "인하", "인상", "환율", "달러", "원·달러"]],
    ["AI", ["AI", "인공지능", "데이터센터", "챗GPT"]],
    ["2차전지", ["2차전지", "배터리", "전기차", "리튬", "양극재"]],
    ["정책·관세", ["관세", "트럼프", "규제", "대통령", "국회"]],
    ["실적", ["실적", "영업이익", "어닝", "순이익", "매출"]],
    ["지수·변동", ["코스피", "코스닥", "지수", "폭락", "급등", "급락"]],
    ["수급", ["외국인", "기관", "국민연금", "순매수", "순매도", "연기금"]],
    ["가상자산", ["비트코인", "코인", "가상자산", "이더리움"]],
    ["부동산", ["부동산", "집값", "분양", "전세"]],
]

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

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
        return { title: title.slice(0, idx).trim(), source: title.slice(idx + 3).trim() }
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
    if (!isFinite(ms)) return dateOnly(t)   // 파싱 실패 = 날짜 부분만 폴백
    const mins = Math.round((Date.now() - ms) / 60000)
    if (mins < 0) return dateOnly(t)
    if (mins < 1) return "방금"
    if (mins < 60) return mins + "분 전"
    const hrs = Math.round(mins / 60)
    if (hrs < 24) return hrs + "시간 전"
    return Math.round(hrs / 24) + "일 전"   // 오래돼도 날짜 대신 항상 '일 전'(PM 2026-07-05)
}

// 정렬용 발행시각 ms (파싱 실패=0 → 뒤로)
function toMs(t: string): number {
    const ms = new Date(String(t || "")).getTime()
    return isFinite(ms) ? ms : 0
}
const NEWS_LOAD_CAP = 60   // 로드 상한(더보기용 여유). display 는 FlatNews 가 페이지네이션
const NEWS_SORTS: { k: string; label: string }[] = [
    { k: "recent", label: "최신" },
    { k: "hot", label: "핫" },
    { k: "outlet", label: "언론사" },
]

function asArray(x: any): any[] {
    return Array.isArray(x) ? x : []
}

export default function PublicNewsTab(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const isDark = (onCanvas ? !!props.dark : themeDark)
    const C = isDark ? DARK : LIGHT

    const [tab, setTab] = useState<Tab>("stock")
    const [showKo, setShowKo] = useState<boolean>(false)
    const [mktSort, setMktSort] = useState<string>("recent")   // 시장·미국 정렬: recent/hot/outlet
    const [recGroups, setRecGroups] = useState<StockGroup[]>([])        // recommendations(뉴스 있는 것) — 관심종목 없을 때 폴백
    const [recMap, setRecMap] = useState<Record<string, StockGroup>>({}) // 전 rec: ticker → 메타+뉴스(뉴스 소스 lookup)
    const [naverNews, setNaverNews] = useState<Record<string, NewsItem[]>>({})  // KR 종목 라이브 뉴스(네이버 enrich)
    const [watch, setWatch] = useState<{ ticker: string; name: string; market: string }[]>([])  // 둥지/관심종목(로그인 watchgroups + localStorage)
    const [market, setMarket] = useState<NewsItem[]>([])
    const [us, setUs] = useState<NewsItem[]>([])
    const [hotStocks, setHotStocks] = useState<HotStock[]>([])
    const [insights, setInsights] = useState<Insights | null>(null)
    const [loading, setLoading] = useState<boolean>(true)
    const [failed, setFailed] = useState<boolean>(false)

    /* 테마 추종 */
    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    /* 둥지/관심종목 읽기 — localStorage(verity_watchlist, 무로그인 별표) + 로그인(/api/watchgroups) 병합.
       별표 토글/로그인 변경 이벤트 추종해 자동 갱신. 비어 있으면 아래 stocks 가 추천으로 폴백. */
    useEffect(() => {
        if (onCanvas) return
        const api = (props.apiBase || "https://project-yw131.vercel.app").replace(/\/+$/, "")
        let alive = true
        const load = () => {
            const m = new Map<string, { ticker: string; name: string; market: string }>()
            try {
                const r = typeof localStorage !== "undefined" ? localStorage.getItem("verity_watchlist") : null
                const a = r ? JSON.parse(r) : []
                if (Array.isArray(a)) for (const w of a) {
                    const tk = String((w && w.ticker) || "").trim()
                    if (tk && !m.has(tk.toUpperCase())) m.set(tk.toUpperCase(), { ticker: tk, name: (w && w.name) || tk, market: (w && w.market) || "" })
                }
            } catch (e) {}
            let token = ""
            try { const s = JSON.parse((typeof localStorage !== "undefined" && localStorage.getItem("verity_supabase_session")) || "null"); token = (s && s.access_token) || "" } catch (e) {}
            const finish = () => { if (alive) setWatch(Array.from(m.values())) }
            if (token) {
                fetch(`${api}/api/watchgroups`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" })
                    .then((r) => (r.ok ? r.json() : null))
                    .then((groups) => {
                        if (Array.isArray(groups)) for (const g of groups) for (const it of (g.items || [])) {
                            const tk = String((it && it.ticker) || "").trim()
                            if (tk && !m.has(tk.toUpperCase())) m.set(tk.toUpperCase(), { ticker: tk, name: (it && it.name) || tk, market: (it && it.market) || "" })
                        }
                    })
                    .catch(() => {})
                    .finally(finish)
            } else finish()
        }
        load()
        window.addEventListener("verity-watchlist-changed", load)   // PublicWatchlist(localStorage) 별표
        window.addEventListener("verity_watch_change", load)         // AlphaNestWatchlist(로그인) 별표
        window.addEventListener("verity-auth-change", load)          // 로그인/로그아웃
        window.addEventListener("storage", load)
        return () => {
            alive = false
            window.removeEventListener("verity-watchlist-changed", load)
            window.removeEventListener("verity_watch_change", load)
            window.removeEventListener("verity-auth-change", load)
            window.removeEventListener("storage", load)
        }
    }, [onCanvas, props.apiBase])

    /* 데이터 로드 */
    useEffect(() => {
        if (onCanvas) {
            setLoading(false)
            return
        }
        let alive = true
        const recUrl = props.recUrl || BLOB + "/recommendations.json"
        const pfUrl = props.portfolioUrl || BLOB + "/portfolio.json"
        const maxPer = props.maxPerStock || 3

        Promise.all([
            fetch(recUrl).then((r) => (r.ok ? r.json() : null)).catch(() => null),
            fetch(pfUrl).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        ]).then((res) => {
            if (!alive) return
            const recRaw = res[0]
            const pf = res[1]

            // recommendations → recMap(전체, 뉴스 소스 lookup) + recGroups(뉴스 있는 것, 관심종목 없을 때 폴백)
            const recs = Array.isArray(recRaw) ? recRaw : (recRaw && recRaw.recommendations) || []
            const recGroupsArr: StockGroup[] = []
            const rmap: Record<string, StockGroup> = {}
            for (let i = 0; i < recs.length; i++) {
                const rec = recs[i] || {}
                const tk = String(rec.ticker || rec.code || "").trim()
                if (!tk) continue
                const sent = rec.sentiment || {}
                const links = asArray(sent.top_headline_links)
                const items: NewsItem[] = []
                for (let j = 0; j < links.length && items.length < maxPer; j++) {
                    const h = links[j] || {}
                    const url = h.url || h.link || ""
                    const sp = splitSource(h.title || "")
                    if (!sp.title) continue
                    items.push({
                        title: sp.title,
                        titleKo: h.title_ko ? splitSource(String(h.title_ko)).title : "",
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
            const mkRaw = pf ? asArray(pf.headlines).concat(asArray(pf.bloomberg_google_headlines)) : []
            const mk: NewsItem[] = []
            const seenMk = new Set<string>()
            for (let i = 0; i < mkRaw.length && mk.length < NEWS_LOAD_CAP; i++) {
                const h = mkRaw[i] || {}
                const sp = splitSource(h.title || "")   // 블룸버그 RSS = "제목 - Bloomberg.com" 포맷이라 출처 분리
                const t = sp.title || String(h.title || "").trim()
                if (!t) continue
                const key = t.slice(0, 32)
                if (seenMk.has(key)) continue
                seenMk.add(key)
                const rawT = h.time || h.published_at || ""
                mk.push({
                    title: t,
                    titleKo: h.title_ko ? splitSource(String(h.title_ko)).title : "",
                    url: h.link || h.url || "",
                    source: h.source || sp.source || hostname(h.link || h.url || ""),
                    time: fmtWhen(rawT),
                    sentiment: String(h.sentiment || ""),
                    ts: toMs(rawT),
                    score: Number(h.composite_score) || 0,
                })
            }

            // 미국 뉴스
            const usRaw = pf ? asArray(pf.us_headlines) : []
            const usArr: NewsItem[] = []
            for (let i = 0; i < usRaw.length && usArr.length < NEWS_LOAD_CAP; i++) {
                const h = usRaw[i] || {}
                const sp = splitSource(h.title || "")
                if (!sp.title) continue
                const rawT = h.time || h.published_at || ""
                usArr.push({
                    title: sp.title,
                    titleKo: h.title_ko ? splitSource(String(h.title_ko)).title : "",
                    url: h.link || h.url || "",
                    source: sp.source || hostname(h.link || ""),
                    time: fmtWhen(rawT),
                    sentiment: String(h.sentiment || ""),
                    ts: toMs(rawT),
                    score: Number(h.composite_score) || 0,
                })
            }

            // 오늘의 뉴스 한눈 — KR headlines(category/near_duplicate/sentiment) + 추천 종목 뉴스량 집계
            const rawHl = pf ? asArray(pf.headlines) : []
            if (rawHl.length) {
                let credHi = 0, credLo = 0, fresh = 0, dup = 0, pos = 0, neg = 0, neu = 0
                for (const h of rawHl) {
                    if ((Number(h.credibility) || 0) >= 0.8) credHi++; else credLo++   // 신뢰 출처(자체 점수)
                    if (h.near_duplicate) dup++; else fresh++
                    const s = String(h.sentiment || "neutral")
                    if (s === "positive") pos++; else if (s === "negative") neg++; else neu++
                }
                // 오늘의 테마 = 시장 헤드라인(KR+글로벌) 제목 키워드 빈도(LLM 아님)
                const themeCnt: Record<string, number> = {}
                for (const it of mk) {
                    const t = it.title || ""
                    for (const [name, kws] of THEME_KEYWORDS) {
                        for (const k of kws) { if (t.indexOf(k) >= 0) { themeCnt[name] = (themeCnt[name] || 0) + 1; break } }
                    }
                }
                const themes = Object.keys(themeCnt).map((name) => ({ name, n: themeCnt[name] })).sort((a, b) => b.n - a.n).slice(0, 6)
                // 뉴스 많은 종목 = 라이브 per-stock 실제 건수(아래 enrichment effect서 채움). headline_count 는 포화라 미사용.
                setInsights({ total: rawHl.length, credHi, credLo, fresh, dup, pos, neg, neu, themes })
            }

            // 오늘 핫한 종목 — 종목별 뉴스량(headline_count) 순 (KR+US, 뉴스 있는 것만 top 8). 사실.
            const hot: HotStock[] = (recs as any[])
                .map((r) => {
                    const s = r.sentiment || {}
                    return { ticker: r.ticker || r.code || "", name: r.name || r.company_name || r.ticker || "", market: r.market || "", count: Number(s.headline_count) || 0, score: Number(s.score) || 0 }
                })
                .filter((x) => x.count > 0 && x.ticker)
                .sort((a, b) => b.count - a.count)
                .slice(0, 8)
            setHotStocks(hot)

            setRecGroups(recGroupsArr)
            setRecMap(rmap)
            setMarket(mk)
            setUs(usArr)
            setLoading(false)
            setFailed(!recRaw && !pf)
        })

        return () => {
            alive = false
        }
    }, [onCanvas, props.recUrl, props.portfolioUrl, props.maxPerStock, props.maxMarket])

    /* 표시할 내 종목 = 관심종목(watch) 있으면 그 종목, 없으면 추천(recGroups). 뉴스 = KR 라이브(naverNews) 우선, 없으면 recMap. */
    const stocks = useMemo<StockGroup[]>(() => {
        const withLive = (g: StockGroup): StockGroup => {
            const live = naverNews[g.ticker] || naverNews[String(g.ticker).toUpperCase()]
            return live && live.length ? { ...g, items: live } : g
        }
        if (watch.length) {
            return watch.map((w) => {
                const rm = recMap[w.ticker] || recMap[String(w.ticker).toUpperCase()]
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
        }
        return recGroups.map(withLive)
    }, [watch, recMap, recGroups, naverNews])

    /* KR 종목(관심 or 추천) 라이브 뉴스 enrich — 목록 바뀔 때(관심종목 변경 포함) 재수집. 최대 15. */
    const krKey = useMemo(() => {
        const src = watch.length ? watch.map((w) => w.ticker) : recGroups.map((g) => g.ticker)
        const out: string[] = []
        for (const tk of src) { const t = String(tk || ""); if (/^\d{6}$/.test(t) && out.indexOf(t) < 0) out.push(t) }
        return out.slice(0, 15).join(",")
    }, [watch, recGroups])

    useEffect(() => {
        if (onCanvas || !krKey) return
        const api = (props.apiBase || "https://project-yw131.vercel.app").replace(/\/+$/, "")
        const krs = krKey.split(",").filter(Boolean)
        let alive = true
        Promise.all(krs.map((tk) =>
            fetch(`${api}/api/stock_news?code=${encodeURIComponent(tk)}`, { cache: "no-store" })
                .then((r) => (r.ok ? r.json() : null))
                .then((d) => ({ tk, items: (d && Array.isArray(d.items)) ? d.items : null }))
                .catch(() => ({ tk, items: null }))
        )).then((results) => {
            if (!alive) return
            setNaverNews((prev) => {
                const next = { ...prev }
                for (const r of results) if (r.items && r.items.length) {
                    next[r.tk] = r.items.slice(0, 4).map((n: any) => ({
                        title: n.title, url: n.url, source: n.source, time: n.rel_time || "",
                        sentiment: "", category: n.category, outlets: n.outlets, credible: n.credible,
                    }))
                }
                return next
            })
        })
        return () => { alive = false }
    }, [krKey, props.apiBase, onCanvas])

    const tabs: { key: Tab; label: string; count: number }[] = useMemo(
        () => [
            { key: "stock", label: "내 종목", count: stocks.length },
            { key: "market", label: "시장", count: market.length },
            { key: "us", label: "미국", count: us.length },
        ],
        [stocks.length, market.length, us.length]
    )

    const wrap: React.CSSProperties = {
        width: "100%",
        maxWidth: 1180,
        marginLeft: "auto",
        marginRight: "auto",
        height: props.height || 720,
        background: C.bg,
        borderRadius: 20,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        fontFamily:
            "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif",
        boxSizing: "border-box",
    }

    return (
        <div style={wrap}>
            <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            {/* 헤더 */}
            <div style={{ padding: "20px 22px 12px 22px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 19, fontWeight: 800, color: C.text, letterSpacing: "-0.02em" }}>
                        뉴스
                    </span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>팩트 헤드라인</span>
                    {(us.some((it) => it.title && !/[가-힣]/.test(it.title)) || stocks.some((g) => g.items.some((it) => it.title && !/[가-힣]/.test(it.title)))) && (
                        <div style={{ marginLeft: "auto", display: "inline-flex", background: C.sub, borderRadius: 10, padding: 3, gap: 2 }}>
                            {[{ k: false, l: "원문" }, { k: true, l: "한글" }].map((o) => {
                                const active = showKo === o.k
                                return (
                                    <button
                                        key={String(o.k)}
                                        type="button"
                                        onClick={() => setShowKo(o.k)}
                                        style={{
                                            border: "none", cursor: "pointer",
                                            background: active ? C.bg : "transparent",
                                            color: active ? C.text : C.subtext,
                                            fontWeight: active ? 700 : 600,
                                            fontSize: 12.5, padding: "6px 13px", borderRadius: 8,
                                            boxShadow: active ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
                                            transition: "all 140ms ease",
                                        }}
                                    >
                                        {o.l}
                                    </button>
                                )
                            })}
                        </div>
                    )}
                </div>
                {/* 세그먼트 */}
                <div
                    style={{
                        marginTop: 14,
                        display: "inline-flex",
                        background: C.sub,
                        borderRadius: 10,
                        padding: 3,
                        gap: 2,
                    }}
                >
                    {tabs.map((t) => {
                        const active = tab === t.key
                        return (
                            <button
                                key={t.key}
                                type="button"
                                onClick={() => setTab(t.key)}
                                style={{
                                    border: "none",
                                    cursor: "pointer",
                                    background: active ? C.bg : "transparent",
                                    color: active ? C.text : C.subtext,
                                    fontWeight: active ? 700 : 600,
                                    fontSize: 13,
                                    padding: "7px 14px",
                                    borderRadius: 8,
                                    boxShadow: active ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
                                    transition: "all 140ms ease",
                                }}
                            >
                                {t.label}
                                <span style={{ marginLeft: 6, color: active ? C.accent : C.faint, fontWeight: 700 }}>
                                    {t.count}
                                </span>
                            </button>
                        )
                    })}
                </div>
            </div>

            {/* 본문 */}
            <div style={{ flex: 1, overflowY: "auto", padding: "4px 14px 18px 14px" }}>
                {/* 오늘 핫한 종목 — 종목별 뉴스량 순(headline_count). 사실, 추천·등급 아님. 가로 스크롤. */}
                {!loading && !failed && hotStocks.length ? (
                    <div style={{ marginBottom: 20 }}>
                        <div style={{ fontSize: 12.5, fontWeight: 800, color: C.text, padding: "2px 2px 8px", letterSpacing: "-0.01em" }}>
                            오늘 핫한 종목 <span style={{ color: C.faint, fontWeight: 600 }}>· 뉴스량 많은 순 · 추천·등급 아님</span>
                        </div>
                        <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
                            {hotStocks.map((s, i) => {
                                const mk = String(s.market || "").toUpperCase()
                                const mkLabel = mk ? (mk.indexOf("KOS") >= 0 || mk === "KR" || mk.indexOf("KRX") >= 0 ? "KR" : mk) : ""
                                return (
                                    <a key={s.ticker} href={(props.reportPath || "/stock") + "?q=" + encodeURIComponent(s.ticker)} target="_blank" rel="noopener noreferrer"
                                        style={{ flexShrink: 0, minWidth: 132, textDecoration: "none", background: C.card, borderRadius: 12, padding: "10px 13px", boxSizing: "border-box" }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                            <span style={{ fontSize: 11, fontWeight: 800, color: C.accent }}>{i + 1}</span>
                                            <span style={{ fontSize: 13, fontWeight: 800, color: C.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 92 }}>{s.name}</span>
                                        </div>
                                        <div style={{ fontSize: 11, fontWeight: 700, color: C.faint, marginTop: 4 }}>
                                            뉴스 <span style={{ color: C.accent }}>{s.count}건</span>{mkLabel ? " · " + mkLabel : ""}
                                        </div>
                                    </a>
                                )
                            })}
                        </div>
                    </div>
                ) : null}
                {!loading && !failed && insights ? <NewsInsights ins={insights} C={C} reportPath={props.reportPath} /> : null}
                {/* 정렬 세그먼트 — 시장·미국 탭만(직교). 최신/핫/언론사그룹. 조회수 없음(데이터 부재). */}
                {!loading && !failed && (tab === "market" || tab === "us") ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 6px 10px", flexWrap: "wrap" }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>정렬</span>
                        <div style={{ display: "inline-flex", background: C.sub, borderRadius: 9, padding: 3, gap: 2 }}>
                            {NEWS_SORTS.map((o) => {
                                const on = mktSort === o.k
                                return (
                                    <button key={o.k} type="button" onClick={() => setMktSort(o.k)}
                                        style={{ border: "none", cursor: "pointer", background: on ? C.bg : "transparent", color: on ? C.text : C.subtext, fontWeight: on ? 700 : 600, fontSize: 12, padding: "5px 12px", borderRadius: 7, boxShadow: on ? "0 1px 3px rgba(0,0,0,0.08)" : "none" }}>{o.label}</button>
                                )
                            })}
                        </div>
                        {mktSort === "hot" ? (
                            <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600 }}>핫 = 매체 동시보도 + 긴급(자체 산출) · 조회수 아님</span>
                        ) : null}
                    </div>
                ) : null}
                {loading ? (
                    <NewsSkeleton C={C} isDark={isDark} />
                ) : failed ? (
                    <div style={{ padding: 40, textAlign: "center", color: C.faint, fontSize: 14 }}>
                        뉴스를 불러오지 못했어요.
                    </div>
                ) : tab === "stock" ? (
                    <>
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, padding: "0 6px 10px" }}>
                            {watch.length ? `내 관심종목 ${watch.length}개 연동 · 별표 추가하면 자동 반영` : "관심종목을 별표하면 여기 연동돼요 · 지금은 추천 종목 뉴스"}
                        </div>
                        <StockNews groups={stocks} C={C} cardH={props.stockCardHeight || 232} showKo={showKo} reportPath={props.reportPath} />
                    </>
                ) : tab === "market" ? (
                    <FlatNews key={"market-" + mktSort} items={market} C={C} empty="시장 뉴스가 없어요." cardH={props.marketCardHeight || 92} showKo={showKo} sortMode={mktSort} />
                ) : (
                    <FlatNews key={"us-" + mktSort} items={us} C={C} empty="미국 뉴스가 없어요." cardH={props.marketCardHeight || 92} showKo={showKo} sortMode={mktSort} />
                )}
            </div>
        </div>
    )
}

/* 로딩 스켈레톤 — 뉴스 카드 그리드 형태(제목 2줄 + 메타 1줄). shimmer. */
function NewsSkeleton(props: { C: typeof LIGHT; isDark: boolean }) {
    const { C, isDark } = props
    const base = isDark ? "#222a33" : "#e9edf1"
    const hi = isDark ? "#2d3742" : "#f3f5f7"
    const bar = (w: string | number, h: number, mt: number): React.CSSProperties => ({
        width: w,
        height: h,
        marginTop: mt,
        borderRadius: 5,
        background: base,
        backgroundImage: "linear-gradient(90deg, " + base + " 25%, " + hi + " 37%, " + base + " 63%)",
        backgroundSize: "800px 100%",
        animation: "vsrShimmer 1.4s ease-in-out infinite",
    })
    const cards = [0, 1, 2, 3, 4, 5, 6, 7]
    return (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 8, alignItems: "start" }}>
            {cards.map((i) => (
                <div
                    key={i}
                    style={{
                        background: C.card,
                        borderRadius: 12,
                        padding: "14px 16px",
                        boxSizing: "border-box",
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

/* 비율 막대 — 세그먼트 너비 = 건수 비율 (순수 CSS, 외부 lib 0). */
function InsightBar(props: { segs: { label: string; n: number; color: string }[]; C: typeof LIGHT }) {
    const total = props.segs.reduce((a, b) => a + b.n, 0) || 1
    return (
        <div style={{ display: "flex", width: "100%", height: 8, borderRadius: 5, overflow: "hidden", background: props.C.sub }}>
            {props.segs.filter((s) => s.n > 0).map((s, i) => (
                <div key={i} title={s.label + " " + s.n} style={{ width: (s.n / total) * 100 + "%", background: s.color }} />
            ))}
        </div>
    )
}

/* 오늘의 뉴스 한눈 — 출처 신뢰도 / 신선도(MinHash) / 키워드 무드 / 뉴스 많은 종목. 전부 사실 집계(RULE7). */
function NewsInsights(props: { ins: Insights; C: typeof LIGHT; reportPath?: string }) {
    const { ins, C } = props
    const tile: React.CSSProperties = { flex: "1 1 190px", minWidth: 168, background: C.card, borderRadius: 12, padding: "12px 14px", boxSizing: "border-box" }
    const lbl: React.CSSProperties = { fontSize: 11, fontWeight: 700, color: C.faint, marginBottom: 8 }
    const chip: React.CSSProperties = { display: "flex", gap: 9, marginTop: 9, fontSize: 11.5, fontWeight: 700, flexWrap: "wrap" }
    return (
        <div style={{ marginBottom: 28 }}>
            <div style={{ fontSize: 12.5, fontWeight: 800, color: C.text, padding: "2px 2px 8px", letterSpacing: "-0.01em" }}>
                오늘의 뉴스 한눈 <span style={{ color: C.faint, fontWeight: 600 }}>· 사실 집계</span>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {/* 출처 신뢰도 (자체 점수화 — 1차/신뢰 출처 비중) */}
                <div style={tile}>
                    <div style={lbl}>출처 신뢰도 · 총 {ins.total}건 <span style={{ color: C.faint, fontWeight: 500 }}>· 자체 분류(가설, N={ins.total})</span></div>
                    <InsightBar segs={[{ label: "신뢰", n: ins.credHi, color: "#0ca678" }, { label: "일반", n: ins.credLo, color: C.border }]} C={C} />
                    <div style={chip}>
                        <span style={{ color: "#0ca678" }}>신뢰 출처 {ins.credHi}</span>
                        <span style={{ color: C.faint }}>일반 {ins.credLo}</span>
                    </div>
                </div>
                {/* 신선도 */}
                <div style={tile}>
                    <div style={lbl}>신선도 · 신규 vs 재탕</div>
                    <InsightBar segs={[{ label: "신규", n: ins.fresh, color: C.accent }, { label: "재탕", n: ins.dup, color: C.border }]} C={C} />
                    <div style={chip}>
                        <span style={{ color: C.accent }}>신규 {ins.fresh}</span>
                        <span style={{ color: C.faint }}>재탕 {ins.dup}</span>
                    </div>
                </div>
                {/* 키워드 무드 */}
                <div style={tile}>
                    <div style={lbl}>키워드 무드 <span style={{ color: C.faint, fontWeight: 500 }}>· 검증 전</span></div>
                    <InsightBar segs={[{ label: "호재", n: ins.pos, color: C.up }, { label: "중립", n: ins.neu, color: C.border }, { label: "악재", n: ins.neg, color: C.down }]} C={C} />
                    <div style={chip}>
                        <span style={{ color: C.up }}>호재 {ins.pos}</span>
                        <span style={{ color: C.faint }}>중립 {ins.neu}</span>
                        <span style={{ color: C.down }}>악재 {ins.neg}</span>
                    </div>
                </div>
                {/* '뉴스 많은 종목' 타일 → 상단 '오늘 핫한 종목' 스트립으로 이전(중복 제거, 2026-07-05) */}
                {/* 오늘의 뉴스 테마 (제목 키워드 빈도 — LLM 아님, 단어 카운트) */}
                {ins.themes.length ? (
                    <div style={{ ...tile, flexBasis: 280, minWidth: 236 }}>
                        <div style={lbl}>오늘의 뉴스 테마 <span style={{ color: C.faint, fontWeight: 500 }}>· 키워드 빈도</span></div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {ins.themes.map((th) => (
                                <span key={th.name} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5, fontWeight: 700, color: C.subtext, background: C.sub, borderRadius: 8, padding: "4px 9px" }}>
                                    {th.name} <span style={{ color: C.accent }}>{th.n}</span>
                                </span>
                            ))}
                        </div>
                    </div>
                ) : null}
            </div>
        </div>
    )
}

function MarketBadge(props: { market: string; C: typeof LIGHT }) {
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

/* 호재/악재 = 위/아래 화살표(텍스트 X). pos/neg 일 때만. 제목 끝(우측). KR 색: 호재 빨강↑ / 악재 파랑↓. */
function SentChip(props: { s: string; C: typeof LIGHT }) {
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
            title={pos ? "호재(키워드 분류)" : "악재(키워드 분류)"}
            aria-label={pos ? "호재" : "악재"}
        >
            <svg width={11} height={11} viewBox="0 0 12 12" fill="none" stroke={col} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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
function SectorBadge(props: { sector: string; industry: string; C: typeof LIGHT }) {
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

function NewsRow(props: { item: NewsItem; C: typeof LIGHT; clamp?: number; showKo?: boolean }) {
    const { item, C } = props
    const clamp = props.clamp || 2
    const ko = !!(props.showKo && item.titleKo && item.titleKo !== item.title)
    const shownTitle = ko ? (item.titleKo as string) : item.title
    const body = (
        <div
            style={{
                padding: "11px 8px",
                borderRadius: 10,
                cursor: item.url ? "pointer" : "default",
                transition: "background 120ms ease",
            }}
            onMouseEnter={(e) => {
                ;(e.currentTarget as HTMLDivElement).style.background = C.sub
            }}
            onMouseLeave={(e) => {
                ;(e.currentTarget as HTMLDivElement).style.background = "transparent"
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
            <div style={{ marginTop: 5, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                {item.category ? (
                    <span style={{ fontSize: 10, fontWeight: 800, color: C.accent, background: C.sub, borderRadius: 5, padding: "1px 6px", whiteSpace: "nowrap" }}>{item.category}</span>
                ) : null}
                {ko ? (
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.accent, background: C.bg, borderRadius: 5, padding: "1px 6px" }}>AI 번역</span>
                ) : null}
                {item.source ? (
                    <span style={{ fontSize: 11.5, fontWeight: 600, color: C.subtext }}>{item.source}{item.credible ? " ✓" : ""}</span>
                ) : null}
                {item.time ? (
                    <>
                        <span style={{ width: 2, height: 2, borderRadius: 2, background: C.faint }} />
                        <span style={{ fontSize: 11.5, color: C.faint }}>{item.time}</span>
                    </>
                ) : null}
                {item.outlets && item.outlets > 1 ? (
                    <span style={{ fontSize: 10.5, fontWeight: 700, color: C.faint }}>· {item.outlets}개 매체</span>
                ) : null}
            </div>
        </div>
    )
    if (!item.url) return body
    return (
        <a href={item.url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none", display: "block" }}>
            {body}
        </a>
    )
}

function FlatNews(props: { items: NewsItem[]; C: typeof LIGHT; empty: string; cardH: number; showKo?: boolean; sortMode: string }) {
    const { items, C, cardH, sortMode } = props
    const [shown, setShown] = useState(15)   // 초기 노출, 더보기 +15 (key=탭+정렬 로 모드 바뀌면 리셋)
    if (!items.length) {
        return <div style={{ padding: 40, textAlign: "center", color: C.faint, fontSize: 14 }}>{props.empty}</div>
    }
    const foot = (
        <div style={{ padding: "12px 8px 2px", fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>
            ↑ 호재 / ↓ 악재 = 키워드 자동분류(검증 전 · 중립 다수)
        </div>
    )
    const moreBtn = (total: number, unit: string) =>
        total > shown ? (
            <button type="button" onClick={() => setShown((s) => s + 15)}
                style={{ width: "100%", marginTop: 10, border: "none", cursor: "pointer", background: C.card, color: C.accent, borderRadius: 10, padding: "11px 0", fontSize: 12.5, fontWeight: 800 }}>
                더보기 ({total - shown}개 {unit})
            </button>
        ) : null

    // 언론사 그룹 모드 — 정렬 아니라 언론사로 묶어 보기(많이 보도한 순)
    if (sortMode === "outlet") {
        const bySrc: Record<string, NewsItem[]> = {}
        for (const it of items) { const s = it.source || "기타"; (bySrc[s] = bySrc[s] || []).push(it) }
        const groups = Object.keys(bySrc)
            .map((s) => ({ source: s, items: bySrc[s].slice().sort((a, b) => (b.ts || 0) - (a.ts || 0)) }))
            .sort((a, b) => b.items.length - a.items.length || a.source.localeCompare(b.source))
        return (
            <div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(330px, 1fr))", gap: 10, alignItems: "start" }}>
                    {groups.slice(0, shown).map((g, i) => (
                        <div key={i} style={{ background: C.card, borderRadius: 14, padding: "12px 12px 6px 12px", boxSizing: "border-box" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 8px 4px 8px" }}>
                                <span style={{ fontSize: 13.5, fontWeight: 800, color: C.text, letterSpacing: "-0.01em" }}>{g.source}</span>
                                <span style={{ fontSize: 11.5, fontWeight: 700, color: C.accent }}>{g.items.length}</span>
                            </div>
                            {g.items.slice(0, 4).map((it, j) => <NewsRow key={j} item={it} C={C} clamp={1} showKo={props.showKo} />)}
                        </div>
                    ))}
                </div>
                {moreBtn(groups.length, "언론사")}
                {foot}
            </div>
        )
    }

    // 최신(발행시각) / 핫(composite_score) 정렬
    const sorted = items.slice().sort((a, b) => (sortMode === "hot" ? (b.score || 0) - (a.score || 0) : (b.ts || 0) - (a.ts || 0)))
    return (
        <div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 8, alignItems: "start" }}>
                {sorted.slice(0, shown).map((it, i) => (
                    <div key={i} style={{ height: cardH, overflow: "hidden", background: C.card, borderRadius: 12, display: "flex", flexDirection: "column", justifyContent: "center" }}>
                        <NewsRow item={it} C={C} clamp={2} showKo={props.showKo} />
                    </div>
                ))}
            </div>
            {moreBtn(sorted.length, "뉴스")}
            {foot}
        </div>
    )
}

function StockNews(props: { groups: StockGroup[]; C: typeof LIGHT; cardH: number; showKo?: boolean; reportPath?: string }) {
    const { groups, C, cardH } = props
    if (!groups.length) {
        return (
            <div style={{ padding: 40, textAlign: "center", color: C.faint, fontSize: 14 }}>
                보유·추천 종목에 걸린 뉴스가 아직 없어요.
            </div>
        )
    }
    return (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(330px, 1fr))", gap: 10, alignItems: "start" }}>
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
                    }}
                >
                    <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 7, padding: "0 8px 4px 8px" }}>
                        {g.ticker ? (
                            <a href={(props.reportPath || "/stock") + "?q=" + encodeURIComponent(g.ticker)} target="_blank" rel="noopener noreferrer" title={(g.name || g.ticker) + " 분석"} style={{ fontSize: 14.5, fontWeight: 800, color: C.accent, letterSpacing: "-0.01em", textDecoration: "none" }}>
                                {g.name || g.ticker} ↗
                            </a>
                        ) : (
                            <span style={{ fontSize: 14.5, fontWeight: 800, color: C.text, letterSpacing: "-0.01em" }}>
                                {g.name || g.ticker}
                            </span>
                        )}
                        {g.ticker && g.ticker !== g.name ? (
                            <span style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>{g.ticker}</span>
                        ) : null}
                        <MarketBadge market={g.market} C={C} />
                        <SectorBadge sector={g.sector} industry={g.industry} C={C} />
                    </div>
                    {g.items.length ? (
                        g.items.map((it, j) => <NewsRow key={j} item={it} C={C} clamp={1} showKo={props.showKo} />)
                    ) : (
                        <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, padding: "10px 8px" }}>최근 관련 뉴스가 없어요</div>
                    )}
                </div>
            ))}
        </div>
    )
}

addPropertyControls(PublicNewsTab, {
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
    recUrl: { type: ControlType.String, title: "추천 JSON", defaultValue: BLOB + "/recommendations.json" },
    portfolioUrl: { type: ControlType.String, title: "포트폴리오 JSON", defaultValue: BLOB + "/portfolio.json" },
    maxPerStock: { type: ControlType.Number, title: "종목당 기사", defaultValue: 3, min: 1, max: 8, step: 1 },
    maxMarket: { type: ControlType.Number, title: "시장 기사 수", defaultValue: 30, min: 5, max: 60, step: 5 },
    height: { type: ControlType.Number, title: "높이", defaultValue: 720, min: 320, max: 1600, step: 20, unit: "px" },
    marketCardHeight: { type: ControlType.Number, title: "시장 카드 높이", defaultValue: 92, min: 72, max: 200, step: 4, unit: "px" },
    stockCardHeight: { type: ControlType.Number, title: "종목 카드 높이", defaultValue: 232, min: 120, max: 400, step: 4, unit: "px" },
    reportPath: { type: ControlType.String, title: "리포트 경로", defaultValue: "/stock" },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: "https://project-yw131.vercel.app" },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 공시 속보 — VERITY 공개 터미널 (AlphaNest) 1차 슬라이스.
 *
 * 데이터 = data/public_disclosure_feed.json (public_disclosure_feed_builder.py 산출).
 * RULE 7: 점수·등급·추천 0. 공시 사실(DART 원문 제목·분류·정정여부·접수일) + 원문 deep-link 만.
 * RULE 6: 용어/분류 평문 = 사전 작성 사전(GLOSSARY/LABEL_PLAIN). 런타임 LLM 0.
 * 도움말 = 항상 표시(용어 점선밑줄·분류칩). PC(hover) 커서 / 모바일(touch) 탭. 토글 없음. 툴팁 clamp.
 * 관심종목 핀: 로그인 시 Supabase watchgroups(단일 소스 — 리포트 별표와 동기) 종목을 상단 고정 · 미로그인 시 localStorage["verity_watchlist"] 폴백. (2026-06-23 단일화)
 * 검색: 종목명·코드 필터(2026-06-22) — maxStocks 늘려도 스크롤 없이 특정 종목 공시 찾기.
 * 테마: Framer 네이티브 추종 — body[data-framer-theme] 읽어 dark 전환(캔버스는 dark prop 정적 프리뷰).
 *   onAccent = 브랜드 보라(vg) 위 글자색. 라이트=흰색/다크=짙은색(2026-06-21 가독성).
 * 🚨 면책 문구 제거(2026-06-26, PM) — "추천·등급 아님 / 검증 후 2027 / 매수·매도 의견 아님" 류는 사이트 하단 단일 면책으로 통합. 출처·색 의미는 유지.
 * 🚨 SAMPLE = canvas 프리뷰 전용(2026-07-04, 사이트 감사 P1) — 라이브 초기 state 는 빈 배열, fetch 실패 시 가짜 공시 오노출 차단.
 * 로딩 스켈레톤(2026-07-04) — 토스식 shimmer 가 리포트 레이아웃 미리 그림 + 160ms 지연 게이트(즉시 로드 깜빡임 차단).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968",
    faint: "#8b95a1", line: "#e5e8eb", red: "#f04452", redS: "#fff0f1",
    amber: "#ff9500", amberS: "#fff6e9", blue: "#3182f6", blueS: "#eef4ff",
    green: "#15c47e", greenS: "#eafaf3", vg: "#6c5ce7", vgS: "#f0edff",
    vt: "#6c5ce7", vtS: "#f0edff", tipBg: "#191f28", tipFg: "#ffffff", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1",
    faint: "#828d9b", line: "#252b34", red: "#f04452", redS: "#2a1a1d",
    amber: "#ff9500", amberS: "#2a2113", blue: "#5b9bff", blueS: "#152031",
    green: "#34e08a", greenS: "#0f241c", vg: "#a99bff", vgS: "#241f3a",
    vt: "#a99bff", vtS: "#241f3a", tipBg: "#222a33", tipFg: "#e3e7ec", onAccent: "#0f1318",
}

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const LS_KEY = "verity_watchlist"
const SESSION_KEY = "verity_supabase_session"   // AlphaNestAuth 세션(access_token)
const AUTH_EVENT = "verity_auth_change"          // 로그인/로그아웃 시 dispatch
const WATCH_EVENT = "verity_watch_change"        // 리포트 별표 담기/해제 시 dispatch
const DEFAULT_API = "https://project-yw131.vercel.app"

const GLOSSARY: Record<string, string> = {
    "유상증자": "회사가 새 주식을 발행해 투자자에게 돈을 받고 파는 것. 자금은 들어오지만 주식 수가 늘어 기존 주주 지분이 옅어져요.",
    "무상증자": "기존 주주에게 공짜로 새 주식을 나눠주는 것. 회사 가치는 그대로라 주당 가격이 그만큼 조정돼요.",
    "전환사채": "회사가 빌린 돈을 정해진 가격에 주식으로 바꿀 수 있는 채권(CB). 전환되면 주식 수가 늘어요.",
    "신주인수권": "정해진 가격에 새 주식을 살 수 있는 권리(BW). 행사되면 주식 수가 늘어요.",
    "공급계약": "제품·서비스를 납품하기로 맺은 계약. 규모가 매출 대비 크면 향후 실적 기대 요인이에요.",
    "단일판매": "한 건의 큰 판매·공급 계약. 매출 대비 규모가 크면 중요한 사실이에요.",
    "자기주식": "회사가 자기 회사 주식을 사거나 보유하는 것. 매입하면 시중 주식 수가 줄어 보통 주주에 우호적이에요.",
    "자사주": "회사가 보유·매입하는 자기 회사 주식. 매입하면 시중 주식 수가 줄어 보통 주주에 우호적이에요.",
    "최대주주": "회사 지분을 가장 많이 가진 주주. 이들의 매수·매도는 회사 내부 사정을 비추는 신호예요.",
    "대량보유": "주식을 5% 이상 보유한 주주의 보유·변동 신고. 큰손의 매수·매도 흐름이 드러나요.",
    "감자": "자본금을 줄이는 것. 무상감자는 보통 주주에게 불리한 신호예요.",
    "합병": "두 회사를 하나로 합치는 것. 지분·주가에 큰 영향을 줄 수 있어요.",
    "분할": "회사를 둘 이상으로 나누는 것. 사업 구조·주주 가치에 영향을 줘요.",
}
const GKEYS = Object.keys(GLOSSARY).sort((a, b) => b.length - a.length)

const LABEL_PLAIN: Record<string, string> = {
    "지분공시": "주주의 지분 보유·변동 신고",
    "발행공시": "주식·사채 발행 관련 공시",
    "주요사항": "회사의 주요 결정 공시",
    "정정공시": "이전에 낸 공시를 고쳐 다시 낸 것",
}

// 공시 제목 → 유형 성격(사실 기반, 매수·매도 의견 아님). 색은 공시 종류의 일반적 효과만 나타냄.
// dilution = 주식 수가 늘어 지분이 옅어질 수 있는 공시 · favor = 유통주식 감소·주주환원 등 우호적 효과 · alert = 자본·법적 주의 사건
// 우선순위: alert > dilution > favor (한 제목에 여러 키워드 시 주의 우선).
type Tone = "dilution" | "favor" | "alert"
const TONE_KW: { key: Tone; kw: string[] }[] = [
    { key: "alert", kw: ["감자", "소송", "횡령", "배임", "상장폐지", "관리종목", "영업정지", "회생절차", "부도", "파산", "감사의견", "거래정지", "불성실공시", "투자주의", "투자경고", "투자위험"] },
    { key: "dilution", kw: ["유상증자", "전환사채", "신주인수권부사채", "교환사채", "신주인수권", "주식매수선택권"] },
    { key: "favor", kw: ["자기주식취득", "자기주식 취득", "자기주식소각", "자기주식 소각", "자사주", "무상증자", "단일판매", "공급계약", "현금배당", "현금ㆍ현물배당", "주식배당"] },
]
function classifyTone(title: string): Tone | "" {
    const t = title || ""
    for (const g of TONE_KW) { if (g.kw.some((k) => t.includes(k))) return g.key }
    return ""
}
const TONE_LABEL: Record<Tone, string> = { dilution: "희석", favor: "우호", alert: "주의" }

const DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="

interface Disclosure {
    title: string
    label: string
    date: string
    is_correction: boolean
    filer: string
    source_url: string
}
interface FeedItem {
    ticker: string
    name: string
    latest: string
    disclosures: Disclosure[]
}

const SAMPLE: FeedItem[] = [
    {
        ticker: "247540", name: "에코프로비엠", latest: "2026-06-16",
        disclosures: [
            { title: "주요사항보고서(유상증자결정)", label: "주요사항", date: "2026-06-16", is_correction: false, filer: "에코프로비엠", source_url: DART + "20260616000412" },
            { title: "단일판매ㆍ공급계약체결", label: "주요사항", date: "2026-06-09", is_correction: false, filer: "에코프로비엠", source_url: DART + "20260609000231" },
            { title: "[기재정정]분기보고서", label: "정정공시", date: "2026-06-02", is_correction: true, filer: "에코프로비엠", source_url: DART + "20260602000118" },
        ],
    },
    {
        ticker: "005930", name: "삼성전자", latest: "2026-06-15",
        disclosures: [
            { title: "주요사항보고서(자기주식취득결정)", label: "주요사항", date: "2026-06-15", is_correction: false, filer: "삼성전자", source_url: DART + "20260615000777" },
        ],
    },
    {
        ticker: "041510", name: "에스엠", latest: "2026-06-12",
        disclosures: [
            { title: "주식등의대량보유상황보고서(약식)", label: "지분공시", date: "2026-06-12", is_correction: false, filer: "티로우프라이스", source_url: DART + "20260612000309" },
        ],
    },
]

interface Props {
    feedUrl: string
    stockPath: string
    apiBase: string
    dark: boolean
    maxStocks: number
}

const DEFAULT_FEED_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/public_disclosure_feed.json"

function readWatchTickers(): string[] {
    if (typeof window === "undefined") return []
    try {
        const r = localStorage.getItem(LS_KEY)
        if (!r) return []
        const a = JSON.parse(r)
        return Array.isArray(a) ? a.map((x: any) => String(x.ticker)) : []
    } catch {
        return []
    }
}

// 로그인 세션 토큰(AlphaNestAuth 기록, 만료 체크) — 있으면 Supabase watchgroups 단일 소스 사용.
function loadToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return ""
        const s = JSON.parse(raw)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return ""
        return typeof s.access_token === "string" ? s.access_token : ""
    } catch { return "" }
}

/* 로딩 스켈레톤 — 토스식 shimmer. 실제 레이아웃(종목 카드 = 종목명 헤더 + 칩·제목 공시 행) 미리 그림.
 * 호출부 160ms 지연 게이트 = 즉시 로드 깜빡임 차단(StockReportSkeleton 관례). */
function DisclosureFeedSkeleton({ C, isDark }: { C: any; isDark: boolean }) {
    const base = isDark ? "#222a33" : "#e9edf1"
    const hi = isDark ? "#2d3742" : "#f3f5f7"
    const sk = (w: number | string, h: number, r = 6, mt = 0): CSSProperties => ({
        width: w, height: h, borderRadius: r, marginTop: mt, background: base,
        backgroundImage: `linear-gradient(90deg, ${base} 25%, ${hi} 37%, ${base} 63%)`,
        backgroundSize: "800px 100%", animation: "vdfShimmer 1.4s ease-in-out infinite", flexShrink: 0,
    })
    return (
        <>
            <style>{`@keyframes vdfShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            {[0, 1, 2, 3].map((card) => (
                <div key={card} style={{ background: C.card, borderRadius: 16, padding: "13px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                    {/* 종목명 헤더 줄 */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                        <div style={sk(card % 2 ? 96 : 128, 16, 6)} />
                        <div style={sk(44, 11, 5)} />
                        <div style={{ ...sk(58, 11, 5), marginLeft: "auto" }} />
                    </div>
                    {/* 공시 행 (칩 + 제목 + 메타) */}
                    {[0, 1, 2].slice(0, card === 3 ? 2 : 3).map((row) => (
                        <div key={row} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "10px 0", borderTop: `1px solid ${C.line}` }}>
                            <div style={sk(46, 20, 7)} />
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={sk(row % 2 ? "72%" : "88%", 13, 5)} />
                                <div style={sk(84, 10, 5, 7)} />
                            </div>
                        </div>
                    ))}
                </div>
            ))}
        </>
    )
}

function readBodyDark(): boolean {
    // 첫 페인트 flash 방지 — body 속성 미설정(마운트 직후) 시 토글 저장 선호(localStorage) → OS 순 폴백.
    // PublicThemeToggle 이 verity_theme 로 저장 + body[data-framer-theme] 설정 = 동일 소스라 첫 페인트부터 정합.
    try {
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicDisclosureFeed(props: Props) {
    const { feedUrl, stockPath, apiBase, dark, maxStocks } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    // SAMPLE 은 canvas 프리뷰 전용 — 라이브는 빈 배열로 시작해 fetch 로만 채운다(실패 시 SAMPLE 오노출 차단).
    const [items, setItems] = useState<FeedItem[]>(onCanvas ? SAMPLE : [])
    const [loaded, setLoaded] = useState<boolean>(onCanvas)
    const [skelVisible, setSkelVisible] = useState<boolean>(false)   // 160ms 게이트 — 즉시 로드 깜빡임 차단
    const [openTip, setOpenTip] = useState<string>("")
    const [tipBox, setTipBox] = useState<{ left: number; width: number }>({ left: 0, width: 248 })
    const [hoverCapable, setHoverCapable] = useState(true)
    const [openKey, setOpenKey] = useState<string>("")
    const [watchKey, setWatchKey] = useState<string>("")
    const [token, setToken] = useState<string>("")
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))
    const [query, setQuery] = useState<string>("")
    useEffect(() => {
        if (loaded) { setSkelVisible(false); return }
        const t = setTimeout(() => setSkelVisible(true), 160)
        return () => clearTimeout(t)
    }, [loaded])

    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 dark prop 정적 프리뷰) */
    useEffect(() => {
        if (onCanvas) return
        const read = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

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
        if (onCanvas || !feedUrl) return
        let alive = true
        fetch(feedUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                const arr = Array.isArray(d) ? d : (d && d.items)
                if (Array.isArray(arr) && arr.length) setItems(arr)
                setLoaded(true)
            })
            .catch(() => { if (alive) setLoaded(true) })
        return () => { alive = false }
    }, [feedUrl, onCanvas])

    // 세션 토큰 추적 (로그인/로그아웃 반영) — AlphaNestWatchlist·PublicStockReport 와 동일 패턴
    useEffect(() => {
        if (onCanvas) return
        const sync = () => setToken(loadToken())
        sync()
        window.addEventListener(AUTH_EVENT, sync)
        window.addEventListener("storage", sync)
        return () => { window.removeEventListener(AUTH_EVENT, sync); window.removeEventListener("storage", sync) }
    }, [onCanvas])

    // 관심종목 = 로그인 시 Supabase watchgroups(단일 소스, 리포트 별표와 동기) · 미로그인 시 localStorage 폴백.
    // 별표 담기/해제(WATCH_EVENT)·포커스 복귀·legacy localStorage 이벤트에 재조회. token 변경(로그인/로그아웃) 시 재실행.
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const apiB = (apiBase || DEFAULT_API).replace(/\/+$/, "")
        const refresh = () => {
            if (token) {
                fetch(`${apiB}/api/watchgroups`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" })
                    .then((r) => (r.ok ? r.json() : null))
                    .then((groups) => {
                        if (!alive) return
                        if (!Array.isArray(groups)) { setWatchKey(""); return }
                        const ts: string[] = []
                        const seen = new Set<string>()
                        for (const g of groups) {
                            for (const it of (g.items || [])) {
                                const tk = String(it.ticker || "").trim()
                                if (tk && !seen.has(tk)) { seen.add(tk); ts.push(tk) }
                            }
                        }
                        setWatchKey(ts.join(","))
                    })
                    .catch(() => { if (alive) setWatchKey("") })
            } else {
                setWatchKey(readWatchTickers().join(","))  // 미로그인 폴백(localStorage)
            }
        }
        refresh()
        if (typeof window === "undefined") return () => { alive = false }
        window.addEventListener(WATCH_EVENT, refresh)
        window.addEventListener("focus", refresh)
        window.addEventListener("verity-watchlist-changed", refresh as EventListener)
        return () => {
            alive = false
            window.removeEventListener(WATCH_EVENT, refresh)
            window.removeEventListener("focus", refresh)
            window.removeEventListener("verity-watchlist-changed", refresh as EventListener)
        }
    }, [onCanvas, token, apiBase])

    const narrow = w > 0 && w < 520
    const pad = narrow ? 12 : 18
    const cardPadV = narrow ? 12 : 14
    const cardPadH = narrow ? 13 : 16

    // 검색 필터 — 종목명·코드 (대소문자 무시)
    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase()
        if (!q) return items
        return items.filter((it) =>
            String(it.name || "").toLowerCase().includes(q) ||
            String(it.ticker || "").toLowerCase().includes(q)
        )
    }, [items, query])

    // 관심종목 핀: watchlist 순서대로 상단, 나머지 원래 순서 (검색 중엔 필터 결과 기준)
    const shown = useMemo(() => {
        const watch = watchKey ? watchKey.split(",").filter(Boolean) : []
        const wset = new Set(watch)
        const max = Math.max(1, maxStocks || 20)
        if (!wset.size || query.trim()) return filtered.slice(0, max)
        const widx: Record<string, number> = {}
        watch.forEach((t, i) => { widx[t] = i })
        const pinned: FeedItem[] = []
        const rest: FeedItem[] = []
        filtered.forEach((it) => { (wset.has(String(it.ticker)) ? pinned : rest).push(it) })
        pinned.sort((a, b) => (widx[String(a.ticker)] ?? 0) - (widx[String(b.ticker)] ?? 0))
        return pinned.concat(rest).slice(0, max)
    }, [filtered, watchKey, maxStocks, query])

    const watchSet = useMemo(() => new Set(watchKey ? watchKey.split(",").filter(Boolean) : []), [watchKey])

    const goStock = (ticker: string) => {
        if (typeof window === "undefined") return
        const p = (stockPath || "/stock").replace(/\/+$/, "")
        window.location.href = p + "?q=" + encodeURIComponent(String(ticker || "").trim())
    }

    // 툴팁 열기 — 가로 위치·폭을 컨테이너 안으로 clamp
    const openTipAt = (e: any, id: string) => {
        try {
            const root = rootRef.current?.getBoundingClientRect()
            const icon = e?.currentTarget?.getBoundingClientRect?.()
            if (root && icon && root.width > 0) {
                const M = 8
                const width = Math.min(248, Math.max(180, root.width - M * 2))
                const iconLeftC = icon.left - root.left
                const clampedLeftC = Math.max(M, Math.min(iconLeftC, root.width - width - M))
                setTipBox({ left: Math.round(clampedLeftC - iconLeftC), width })
            }
        } catch { /* ignore */ }
        setOpenTip(id)
    }

    const tipStyle = (): CSSProperties => ({
        position: "absolute", top: "calc(100% + 6px)", left: tipBox.left, zIndex: 50, display: "block",
        width: tipBox.width, background: C.tipBg, color: C.tipFg, borderRadius: 12,
        padding: "11px 13px", fontSize: 12.5, fontWeight: 500, lineHeight: 1.55, letterSpacing: "-0.1px",
        boxShadow: "0 6px 20px rgba(0,0,0,0.18)", whiteSpace: "normal", textAlign: "left",
    })

    const hoverProps = (id: string) => (hoverCapable
        ? { onMouseEnter: (e: any) => openTipAt(e, id), onMouseLeave: () => setOpenTip("") }
        : {})

    // 공시 제목 안 용어 — 항상 점선밑줄 + hover(PC)/탭(모바일) 시 뜻 팝업
    const renderTitle = (text: string, idKey: string) => {
        const parts: any[] = []
        let rest = text
        let guard = 0
        while (rest.length && guard < 50) {
            guard++
            let hitIdx = -1
            let hitKey = ""
            for (const k of GKEYS) {
                const i = rest.indexOf(k)
                if (i >= 0 && (hitIdx === -1 || i < hitIdx)) { hitIdx = i; hitKey = k }
            }
            if (hitIdx === -1) { parts.push(rest); break }
            if (hitIdx > 0) parts.push(rest.slice(0, hitIdx))
            const tipId = idKey + ":" + hitKey + ":" + parts.length
            const isOpen = openTip === tipId
            parts.push(
                <span key={tipId} style={{ position: "relative", display: "inline" }}>
                    <span role="button" tabIndex={0}
                        onClick={(e) => { e.stopPropagation(); if (isOpen) setOpenTip(""); else openTipAt(e, tipId) }}
                        {...hoverProps(tipId)}
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

    const wrap: CSSProperties = {
        width: "100%", height: "100%", maxHeight: "100%", overflowY: "auto", overflowX: "hidden",
        background: C.bg, fontFamily: FONT, padding: pad, boxSizing: "border-box", color: C.ink,
    }

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ marginBottom: 4 }}>
                <div style={{ fontSize: narrow ? 18 : 20, fontWeight: 800, letterSpacing: "-0.5px" }}>공시 속보</div>
                <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 3 }}>
                    공시-first (DART 원천) · 관심종목 공시는 위로
                </div>
            </div>

            {/* 검색 — 종목명·코드 */}
            <div style={{ marginTop: 12, position: "relative" }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={C.faint} strokeWidth="2.4" strokeLinecap="round"
                    style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}>
                    <circle cx="11" cy="11" r="7" />
                    <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="종목명·코드 검색"
                    style={{
                        width: "100%", boxSizing: "border-box", border: "none",
                        background: C.card, color: C.ink, borderRadius: 12,
                        padding: "12px 34px 12px 38px", fontSize: 13.5, fontFamily: FONT, outline: "none",
                        WebkitAppearance: "none",
                    }}
                />
                {query && (
                    <span role="button" tabIndex={0} onClick={() => setQuery("")}
                        style={{ position: "absolute", right: 11, top: "50%", transform: "translateY(-50%)", color: C.faint, fontSize: 15, fontWeight: 700, cursor: "pointer", lineHeight: 1 }}>×</span>
                )}
            </div>

            {/* 종목 카드 리스트 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
                {!loaded && skelVisible && <DisclosureFeedSkeleton C={C} isDark={themeDark} />}
                {loaded && shown.length === 0 ? (
                    <div style={{ textAlign: "center", color: C.faint, fontSize: 13, fontWeight: 600, padding: "30px 0", lineHeight: 1.5 }}>
                        {query.trim() ? `"${query.trim()}" 검색 결과가 없어요` : "표시할 공시가 없어요"}
                    </div>
                ) : null}
                {shown.map((it) => {
                    const pinned = watchSet.has(String(it.ticker))
                    return (
                        <div key={it.ticker} style={{ background: C.card, borderRadius: 16, padding: `${cardPadV}px ${cardPadH}px`, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", border: pinned ? `1px solid ${C.vtS}` : "1px solid transparent" }}>
                            {/* 종목명 — 탭하면 전체 리포트 */}
                            <div onClick={() => goStock(it.ticker)}
                                style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 6, flexWrap: "wrap", cursor: "pointer" }}>
                                {pinned && <span style={{ flexShrink: 0, fontSize: 10, fontWeight: 800, color: C.vt, background: C.vtS, padding: "2px 7px", borderRadius: 6 }}>관심</span>}
                                <span style={{ fontSize: 15.5, fontWeight: 700, letterSpacing: "-0.3px" }}>{it.name}</span>
                                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{it.ticker}</span>
                                <span style={{ fontSize: 11, color: C.vg, fontWeight: 800 }}>리포트 ›</span>
                                <span style={{ marginLeft: "auto", fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{it.latest}</span>
                            </div>

                            {it.disclosures.map((d, i) => {
                                const corr = d.is_correction
                                const chipC = corr ? { fg: C.amber, bg: C.amberS } : { fg: C.blue, bg: C.blueS }
                                const tone = classifyTone(d.title)
                                const toneSty = tone === "dilution" ? { fg: C.amber, bg: C.amberS } : tone === "favor" ? { fg: C.green, bg: C.greenS } : tone === "alert" ? { fg: C.red, bg: C.redS } : null
                                const key = it.ticker + ":" + i
                                const opened = openKey === key
                                const chipId = key + ":chip"
                                const chipOpen = openTip === chipId
                                const chipMeaning = corr ? LABEL_PLAIN["정정공시"] : (LABEL_PLAIN[d.label] || d.label)
                                return (
                                    <div key={i} style={{ borderTop: i === 0 ? `1px solid ${C.line}` : "none" }}>
                                        <div onClick={() => setOpenKey(opened ? "" : key)}
                                            style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "9px 0", cursor: "pointer" }}>
                                            {/* 분류 칩 — hover/탭 시 뜻 팝업 */}
                                            <div style={{ display: "flex", flexDirection: "column", gap: 5, flexShrink: 0, alignSelf: "flex-start", alignItems: "flex-start" }}>
                                                <span style={{ position: "relative", display: "inline-block" }}>
                                                    <span role="button" tabIndex={0}
                                                        onClick={(e) => { e.stopPropagation(); if (chipOpen) setOpenTip(""); else openTipAt(e, chipId) }}
                                                        {...hoverProps(chipId)}
                                                        style={{ display: "inline-block", fontSize: 11, fontWeight: 800, color: chipC.fg, background: chipC.bg, padding: "3px 8px", borderRadius: 7, whiteSpace: "nowrap", cursor: "help" }}>
                                                        {corr ? "정정" : d.label}
                                                    </span>
                                                    {chipOpen && (
                                                        <span onClick={(e) => e.stopPropagation()} style={tipStyle()}>
                                                            <span style={{ fontWeight: 700, display: "block", marginBottom: 3, color: C.vg }}>{corr ? "정정공시" : d.label}</span>
                                                            {chipMeaning}
                                                        </span>
                                                    )}
                                                </span>
                                                {tone && toneSty && (
                                                    <span style={{ display: "inline-block", fontSize: 10.5, fontWeight: 800, color: toneSty.fg, background: toneSty.bg, padding: "2px 7px", borderRadius: 6, whiteSpace: "nowrap" }}>
                                                        {TONE_LABEL[tone]}
                                                    </span>
                                                )}
                                            </div>
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ fontSize: 13.5, fontWeight: 600, color: C.ink, lineHeight: 1.45, wordBreak: "break-word" }}>
                                                    {renderTitle(d.title, key)}
                                                </div>
                                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3 }}>
                                                    {d.date}{d.filer ? " · " + d.filer : ""}
                                                </div>
                                            </div>
                                            <span style={{ flexShrink: 0, alignSelf: "center", fontSize: 13, color: C.faint, fontWeight: 700, transform: opened ? "rotate(90deg)" : "none", transition: "transform 0.12s" }}>›</span>
                                        </div>
                                        {opened && (
                                            <div style={{ padding: "2px 0 11px 0", display: "flex", flexDirection: "column", gap: 8 }}>
                                                <div style={{ fontSize: 13, fontWeight: 600, color: C.ink, lineHeight: 1.5, wordBreak: "break-word" }}>{d.title}</div>
                                                <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 11.5, color: C.sub, fontWeight: 600 }}>
                                                    <span>구분 · {corr ? "정정공시" : (LABEL_PLAIN[d.label] || d.label)}</span>
                                                    <span>접수 · {d.date}</span>
                                                    {d.filer && <span>제출 · {d.filer}</span>}
                                                </div>
                                                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                                    {d.source_url && (
                                                        <a href={d.source_url} target="_blank" rel="noopener"
                                                            style={{ fontSize: 12, fontWeight: 800, color: C.onAccent, background: C.vg, borderRadius: 9, padding: "8px 14px", textDecoration: "none" }}>
                                                            DART 원문 전체 보기 ↗
                                                        </a>
                                                    )}
                                                    <button onClick={(e) => { e.stopPropagation(); goStock(it.ticker) }}
                                                        style={{ border: `1px solid ${C.line}`, background: C.card, color: C.ink, cursor: "pointer", fontSize: 12, fontWeight: 800, borderRadius: 9, padding: "8px 14px", fontFamily: FONT }}>
                                                        {it.name} 리포트 ›
                                                    </button>
                                                </div>
                                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>원문 사실만 표시</div>
                                            </div>
                                        )}
                                    </div>
                                )
                            })}
                        </div>
                    )
                })}
            </div>

            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
                공시 사실·일정만 · 색 표시(희석·우호·주의)는 공시 유형의 일반적 성격 · 원문은 DART 전자공시
            </div>
        </div>
    )
}

addPropertyControls(PublicDisclosureFeed, {
    feedUrl: { type: ControlType.String, title: "Feed URL", defaultValue: DEFAULT_FEED_URL },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    maxStocks: { type: ControlType.Number, title: "Max stocks", defaultValue: 20, min: 1, max: 100, step: 1, displayStepper: true },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"
import { ArrowRight, ChatCircle, DotsThree, Heart, User } from "@phosphor-icons/react"

/**
 * 커뮤니티 페이지 — 전 종목 공개 관점 글로벌 피드 (2026-07-10, PM 결정 = 비공개 초안).
 *
 * 🚨 배치 참조: 토스(중앙 단일 컬럼 + 세그먼트 정렬 + 종목 칩 필터 + 카드 리스트) × 인스타/쓰레드(아바타 헤더 + 본문 + 하트·⋯ 액션 행).
 * 🚨 공개 게이트: 이 컴포넌트를 올린 Framer 페이지 = 네비 미연결 초안 유지. 규모 확인 후 PM 이 공개 결정.
 * 데이터 = /api/thesis_feed (ticker 생략 = 전 종목 최신). 종목명 = universe_search.json 매핑.
 * 🚨 RULE 7 — 피드 = 이용자 개인 의견 라벨 필수 (AlphaNest 분석·판단 아님). RULE 6 — LLM 0.
 *
 * 🚨 2026-07-24 테마 = 자체 내장 CSS 변수(--an-vcp-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
 *   <style>{AN_PALETTE} 정적 HTML 정합. Phosphor 아이콘 = 부모 color(var) currentColor 상속. 필터칩 = onAccent 토큰(플립). 되돌리지 말 것.
 */

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", up: "#f04452", upS: "#fdecee", down: "#3182f6", downS: "#e8f1fe",
    vg: "#6c5ce7", vgS: "#f0edff", chipBg: "#e8ebef", onAccent: "#ffffff", skBase: "#e9edf1", skHi: "#f3f5f7",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", up: "#f04452", upS: "#31181c", down: "#5b9bff", downS: "#16233a",
    vg: "#a99bff", vgS: "#241f3a", chipBg: "#1e242c", onAccent: "#0f1318", skBase: "#222a33", skHi: "#2d3742",
}

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-vcp-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "vcp"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

const STANCE_LABEL: Record<string, string> = { bull: "강세", watch: "관망", bear: "약세" }
// 신고 사유 — 운영자(/admin 모더레이션)가 판단 근거로 쓰는 값. 자유입력 대신 고정 4종(오남용·개인정보 유입 차단).
const REPORT_REASONS = ["스팸·광고", "욕설·비방", "허위·오해 소지", "기타"]
const UNIVERSE_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
const DEFAULT_API = "https://project-yw131.vercel.app"

const DEMO_FEED = [
    { id: "d1", ticker: "005930", nickname: "길동무", avatar: "", stance: "bull", note: "수주 잔고 증가 + 부채비율 하향 추세. 다음 분기 마진 확인 후 재검토.", created_at: "2026-07-09T09:00:00Z", likes: 12, liked: false, mine: false },
    { id: "d2", ticker: "NVDA", nickname: "가치사냥", avatar: "", stance: "watch", note: "밸류는 부담스러운데 수요가 계속 확인됨. 조정 오면 다시 본다.", created_at: "2026-07-08T13:00:00Z", likes: 7, liked: true, mine: false },
    { id: "d3", ticker: "000660", nickname: "느린걸음", avatar: "", stance: "bull", note: "HBM 증설 스케줄 그대로면 하반기 실적 방향은 위라고 본다.\n리스크 = 환율.", created_at: "2026-07-07T02:00:00Z", likes: 4, liked: false, mine: false },
    { id: "d4", ticker: "035720", nickname: "관망러", avatar: "", stance: "bear", note: "신사업 비용이 아직 무겁다. 흑자 전환 확인 전까진 보수적으로.", created_at: "2026-07-05T10:00:00Z", likes: 1, liked: false, mine: false },
]

const DEMO_NOTICES = [
    { id: "n1", kind: "event", title: "첫 관점 남기기 이벤트", body: "이번 주 안에 관점을 남기면 커뮤니티 첫 기록으로 남아요.", link: "", pinned: true, created_at: "2026-07-26T00:00:00Z" },
]
const DEMO_STATS = { total: { bull: 12, watch: 7, bear: 4, total: 23 }, by_ticker: [], window: 1000 }
const DEMO_EXPERIMENTS = [
    { id: "pe1", kind: "portfolio_experiment", nickname: "연습중", avatar: "", title: "매달 30만 원 분산투자", assets: [{ ticker: "005930", name: "삼성전자", market: "KR", weight: 50 }, { ticker: "SPY", name: "S&P 500 ETF", market: "US", weight: 50 }], asset_count: 2, start_date: "2020-01-02", contribution: 300000, frequency: "monthly", rebalance: "yearly", dividend_reinvest: true, privacy: "full", created_at: "2026-08-29T00:00:00Z", result_status: "engine_not_connected" },
]
const DEMO_QNA = [
    { id: "qa1", title: "관점은 공개해야 저장되나요?", body: "혼자 기록만 하고 싶을 때도 저장할 수 있나요?", answer: "네. 관점은 기본 비공개로 저장되며, 공개를 직접 선택한 경우에만 커뮤니티에 보여요.", answered_at: "2026-09-04T00:00:00Z" },
]
const DEMO_MY_SUPPORT = [
    { id: "ms1", kind: "question", title: "배당 기준일 표시", body: "기준일 설명도 함께 볼 수 있나요?", publish_consent: true, status: "answered", answer: "공시 기준일과 지급일을 구분해 표시하는 방향으로 반영할게요.", created_at: "2026-09-03T00:00:00Z" },
]
const DEMO_MY_THESES = [
    { id: "mt1", ticker: "005930", market: "kr", stance: "bull", note: "메모리 가격 회복 여부를 다음 실적에서 확인.", entry_price: 71200, is_public: true, created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z" },
    { id: "mt2", ticker: "NVDA", market: "us", stance: "watch", note: "성장성은 좋지만 밸류 부담을 더 확인.", entry_price: 0, is_public: false, created_at: "2026-08-28T00:00:00Z", updated_at: "2026-08-28T00:00:00Z" },
]

interface Props {
    apiBase: string
    stockPath: string
    usStockPath: string
    limit: number
    dark: boolean
}

function getToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const r = localStorage.getItem("verity_supabase_session")
        if (!r) return ""
        const s = JSON.parse(r)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return ""
        return typeof s.access_token === "string" ? s.access_token : ""
    } catch {
        return ""
    }
}

function fmtAgo(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 1) return "방금"
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        const days = Math.round(hrs / 24)
        if (days < 7) return days + "일 전"
        return String(iso).slice(0, 10)
    } catch {
        return ""
    }
}

// ── 종목 로고(Brandfetch logo_map) + 원형 국기(circle-flags) — 뉴스탭과 동일 소스 ──
const BF_CID = "1idalDez9T7KlggM8qX"
const BF_MAP_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
let __bfMap: Record<string, string> | null = null
let __bfP: Promise<Record<string, string>> | null = null
function fetchBfMap(): Promise<Record<string, string>> {
    if (__bfMap) return Promise.resolve(__bfMap)
    if (!__bfP)
        __bfP = fetch(BF_MAP_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                __bfMap = (d && d.logos) || {}
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
function bfLogoSrc(ticker: any, lm: Record<string, string> | null, size: number): string {
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    if (!tk) return ""
    // 로고 = 토스 종목 CDN (PM 결정: 완전 공개[런칭] 전까지 토스 사용, 2026-07-12). 404/차단 시 onError → 이니셜 폴백.
    return "https://static.toss.im/png-icons/securities/icn-sec-fill-" + tk + ".png"
}
function StockLogo(props: { ticker: any; name: any; C: any; size?: number }) {
    const { ticker, name, C } = props
    const size = props.size || 22
    const [err, setErr] = useState(false)
    const lm = useBfLogoMap()
    const src = bfLogoSrc(ticker, lm, size)
    const ch = String(name || "?").trim().charAt(0) || "?"
    const code = /^\d{6}$/.test(String(ticker || "")) ? "kr" : "us"
    const f = Math.round(size * 0.46)
    return (
        <span style={{ position: "relative", width: size, height: size, flexShrink: 0, display: "inline-block" }}>
            {!err && src ? (
                <img
                    src={src}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    width={size}
                    height={size}
                    onError={() => setErr(true)}
                    style={{ width: size, height: size, borderRadius: Math.round(size * 0.3), objectFit: "cover", background: "transparent", display: "block" }}
                />
            ) : (
                <span style={{ width: size, height: size, borderRadius: Math.round(size * 0.3), background: C.chipBg, color: C.faint, display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * 0.42), fontWeight: 800 }}>
                    {ch}
                </span>
            )}
            <img
                src={FLAG_BASE + code + ".svg"}
                alt=""
                loading="lazy"
                decoding="async"
                width={f}
                height={f}
                style={{ position: "absolute", right: -3, bottom: -3, width: f, height: f, borderRadius: "50%", border: `1.5px solid ${C.card}`, background: C.card, display: "block" }}
            />
        </span>
    )
}

/* 관점 온도 — 강세/관망/약세 "글 수" 막대. 사실 집계이며 추천·전망·목표가가 아님(RULE 7).
   표본이 작으면 비율이 튀므로 건수와 표본 창을 항상 병기. n<5 는 "표본 부족" 문구로 대체. */
function StanceBar(props: { c: any; label: string; window?: number; compact?: boolean }) {
    const { c, label } = props
    const bull = Number(c?.bull || 0)
    const watch = Number(c?.watch || 0)
    const bear = Number(c?.bear || 0)
    const n = bull + watch + bear
    const seg = [
        { k: "강세", v: bull, col: C.up },
        { k: "관망", v: watch, col: C.faint },
        { k: "약세", v: bear, col: C.down },
    ]
    return (
        <div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                <span style={{ fontSize: 13.5, fontWeight: 800, color: C.ink, letterSpacing: "-0.2px" }}>{label}</span>
                <span style={{ fontSize: 11, color: C.faint, fontWeight: 700 }}>{n}개</span>
            </div>
            {n < 5 ? (
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>
                    표본 부족 (5개 미만) · 관점이 쌓이면 비율을 보여드려요
                </div>
            ) : (
                <>
                    <div style={{ display: "flex", height: 8, borderRadius: 999, overflow: "hidden", marginTop: 8, background: C.chipBg }}>
                        {seg.map((s) => (
                            <div key={s.k} style={{ width: (s.v / n) * 100 + "%", background: s.col }} title={s.k + " " + s.v + "개"} />
                        ))}
                    </div>
                    <div style={{ display: "flex", gap: 10, marginTop: 7, flexWrap: "wrap" }}>
                        {seg.map((s) => (
                            <span key={s.k} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, fontWeight: 700, color: C.sub }}>
                                <span style={{ width: 7, height: 7, borderRadius: 3, background: s.col }} />
                                {s.k} {Math.round((s.v / n) * 100)}%
                                <span style={{ color: C.faint, fontWeight: 600 }}>({s.v})</span>
                            </span>
                        ))}
                    </div>
                </>
            )}
            {!props.compact && (
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 7, lineHeight: 1.5 }}>
                    이용자가 남긴 관점 글 수 집계{props.window ? ` · 최근 ${props.window}개 기준` : ""} · 추천·전망 아님
                </div>
            )}
        </div>
    )
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
    if (!v || v === "/us/stock") return String(kr || "").replace(/\/+$/, "") || "/stock"
    return v
}

export default function PublicCommunityPage(props: Props) {
    const { apiBase, stockPath, usStockPath, limit, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")
    const cap = Math.max(5, Math.min(50, limit || 30))

    const [token, setToken] = useState("")
    const [feed, setFeed] = useState<any[]>([])
    // 칩·트렌딩 원본 = 필터 없는 최신 페이지. 종목 필터가 서버로 넘어가도 칩 목록이 1종목으로 붕괴하지 않게 분리(2026-07-25).
    const [overview, setOverview] = useState<any[]>([])
    const [loading, setLoading] = useState(true)
    const [more, setMore] = useState(false) // 더보기 진행 중
    const [hasMore, setHasMore] = useState(false)
    const [hotWin, setHotWin] = useState(0) // 인기 집계 창(서버 응답 window) — 라벨 정합용
    const [sort, setSort] = useState<"new" | "hot">("new")
    const [filterTk, setFilterTk] = useState("")
    const [names, setNames] = useState<Record<string, string>>({})
    const [msg, setMsg] = useState("")
    const [menuId, setMenuId] = useState("")
    const [reportId, setReportId] = useState("") // 신고 사유 선택 대상
    const [reported, setReported] = useState<Record<string, boolean>>({})
    const [expanded, setExpanded] = useState<Record<string, boolean>>({})
    const [q, setQ] = useState("") // 종목 검색어(이름/코드)
    const [focused, setFocused] = useState(false)
    const [notices, setNotices] = useState<any[]>([]) // 공지·이벤트(027) — 관리자 발행분
    const [seenNotice, setSeenNotice] = useState("") // 배너 닫기(localStorage 기억)
    const [stats, setStats] = useState<any>(null) // 관점 온도 — 강세/관망/약세 글 수
    const [mainTab, setMainTab] = useState<"community" | "support" | "mine">("community")
    const [contentTab, setContentTab] = useState<"thesis" | "experiment">("thesis")
    const [experiments, setExperiments] = useState<any[]>([])
    const [experimentsLoading, setExperimentsLoading] = useState(true)
    const [publicQna, setPublicQna] = useState<any[]>([])
    const [mySupport, setMySupport] = useState<any[]>([])
    const [supportLoading, setSupportLoading] = useState(false)
    const [supportKind, setSupportKind] = useState<"question" | "feedback">("question")
    const [supportTitle, setSupportTitle] = useState("")
    const [supportBody, setSupportBody] = useState("")
    const [supportConsent, setSupportConsent] = useState(false)
    const [supportSending, setSupportSending] = useState(false)
    const [myTheses, setMyTheses] = useState<any[]>([])
    const [mineLoading, setMineLoading] = useState(false)
    const [mineVisibility, setMineVisibility] = useState<"all" | "public" | "private">("all")
    const [editingMine, setEditingMine] = useState("")
    const [mineDraft, setMineDraft] = useState<any>({ stance: "watch", note: "" })
    const [mineBusy, setMineBusy] = useState("")
    const note = (m: string) => {
        setMsg(m)
        if (typeof window !== "undefined") window.setTimeout(() => setMsg((cur) => (cur === m ? "" : cur)), 3500)
    }

    /* 공지·이벤트 배너 (2026-07-26) — /api/notices 공개 읽기. 관리자가 /admin 에서 발행한 문구 그대로(RULE 6: LLM 0).
       027 미적용 DB 나 발행분 0건이면 빈 목록 → 배너 자체가 안 뜸(무회귀). */
    useEffect(() => {
        if (onCanvas) {
            setNotices(DEMO_NOTICES)
            return
        }
        try {
            setSeenNotice(localStorage.getItem("an_notice_seen") || "")
        } catch (e) {}
        let alive = true
        fetch(base + "/api/notices")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive && d && Array.isArray(d.items)) setNotices(d.items)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [base, onCanvas])

    /* 관점 온도 — 공개 관점의 강세/관망/약세 글 수(사실 집계). 종목 필터 시 그 종목 기준.
       🚨 RULE 7: 추천·전망 아님. 표본(window)·건수 병기 의무. */
    useEffect(() => {
        if (onCanvas) {
            setStats(DEMO_STATS)
            return
        }
        let alive = true
        fetch(base + "/api/thesis_feed?stats=1" + (filterTk ? "&ticker=" + encodeURIComponent(filterTk) : ""))
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive && d && d.total) setStats(d)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [base, filterTk, onCanvas])

    useEffect(() => {
        if (onCanvas) {
            setExperiments(DEMO_EXPERIMENTS)
            setExperimentsLoading(false)
            return
        }
        let alive = true
        setExperimentsLoading(true)
        fetch(base + "/api/portfolio_experiments?limit=" + cap, { cache: "no-store" })
            .then((r) => r.ok ? r.json() : null)
            .then((d) => { if (alive) setExperiments(d && Array.isArray(d.items) ? d.items : []) })
            .catch(() => { if (alive) setExperiments([]) })
            .finally(() => { if (alive) setExperimentsLoading(false) })
        return () => { alive = false }
    }, [base, cap, onCanvas])

    // 세션 토큰 추적(로그인/로그아웃 반영 — AlphaNestAuth 가 dispatch)
    useEffect(() => {
        if (onCanvas) return
        const sync = () => setToken(getToken())
        sync()
        window.addEventListener("verity_auth_change", sync)
        window.addEventListener("storage", sync)
        return () => {
            window.removeEventListener("verity_auth_change", sync)
            window.removeEventListener("storage", sync)
        }
    }, [onCanvas])

    /* 공지·Q&A — 공개 답변과 본인 접수 내역을 서로 독립 요청해 한쪽 실패가 다른 쪽을 막지 않게 한다. */
    useEffect(() => {
        if (mainTab !== "support") return
        if (onCanvas) {
            setPublicQna(DEMO_QNA)
            setMySupport(DEMO_MY_SUPPORT)
            setSupportLoading(false)
            return
        }
        let alive = true
        setSupportLoading(true)
        const headers = token ? { Authorization: "Bearer " + token } : undefined
        Promise.all([
            fetch(base + "/api/support", { cache: "no-store" }).then((r) => r.ok ? r.json() : null).catch(() => null),
            token ? fetch(base + "/api/support?mine=1", { headers, cache: "no-store" }).then((r) => r.ok ? r.json() : null).catch(() => null) : Promise.resolve(null),
        ]).then(([pub, mine]) => {
            if (!alive) return
            setPublicQna(pub && Array.isArray(pub.items) ? pub.items : [])
            setMySupport(mine && Array.isArray(mine.items) ? mine.items : [])
        }).finally(() => { if (alive) setSupportLoading(false) })
        return () => { alive = false }
    }, [mainTab, base, token, onCanvas])

    /* 내 관점 — 로그인 사용자는 서버 전량, 비로그인은 이 기기의 기존 저널을 읽는다. */
    useEffect(() => {
        if (mainTab !== "mine") return
        if (onCanvas) {
            setMyTheses(DEMO_MY_THESES)
            setMineLoading(false)
            return
        }
        let alive = true
        setMineLoading(true)
        const localRows = () => {
            try {
                const saved = JSON.parse(localStorage.getItem("verity_thesis_v1") || "{}") || {}
                return Object.keys(saved).map((ticker) => ({
                    ticker, market: /^\d{6}$/.test(ticker) ? "kr" : "us",
                    stance: saved[ticker]?.stance || "watch", note: saved[ticker]?.note || "",
                    entry_price: saved[ticker]?.entryPrice ?? null, is_public: false,
                    created_at: saved[ticker]?.date || "", updated_at: saved[ticker]?.date || "", local_only: true,
                }))
            } catch { return [] }
        }
        if (!token) {
            setMyTheses(localRows())
            setMineLoading(false)
            return
        }
        fetch(base + "/api/thesis", { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => r.ok ? r.json() : null)
            .then((rows) => { if (alive) setMyTheses(Array.isArray(rows) ? rows : []) })
            .catch(() => { if (alive) setMyTheses(localRows()) })
            .finally(() => { if (alive) setMineLoading(false) })
        return () => { alive = false }
    }, [mainTab, base, token, onCanvas])

    /* 피드 로드 — 정렬·종목필터·페이지네이션 전부 서버(2026-07-25).
       이전: limit 30 단발 + 클라 정렬/필터 → 30개 넘는 글은 접근 경로 없음 + '인기'가 로드분 안에서만 정렬(가짜).
       지금: offset 페이지네이션(has_more) + sort=hot(서버 집계, 최근 window 개) + ticker 서버 필터. */
    const fetchPage = (off: number) => {
        const h: Record<string, string> = {}
        const t = getToken()
        if (t) h.Authorization = "Bearer " + t
        const u =
            base +
            "/api/thesis_feed?limit=" + cap +
            "&offset=" + off +
            (sort === "hot" ? "&sort=hot" : "") +
            (filterTk ? "&ticker=" + encodeURIComponent(filterTk) : "")
        return fetch(u, { headers: h, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => (d && Array.isArray(d.items) ? d : null))
            .catch(() => null)
    }

    useEffect(() => {
        if (onCanvas) {
            setFeed(DEMO_FEED)
            setOverview(DEMO_FEED)
            setHasMore(false)
            setLoading(false)
            return
        }
        let alive = true
        setLoading(true)
        fetchPage(0)
            .then((d) => {
                if (!alive) return
                setFeed(d ? d.items : [])
                setHasMore(!!(d && d.has_more))
                setHotWin(d && d.window ? Number(d.window) : 0)
                if (d && !filterTk) setOverview(d.items) // 칩·트렌딩 원본 갱신은 무필터일 때만
            })
            .finally(() => {
                if (alive) setLoading(false)
            })
        return () => {
            alive = false
        }
    }, [base, cap, sort, filterTk, token, onCanvas])

    const loadMore = () => {
        if (more || !hasMore || onCanvas) return
        setMore(true)
        fetchPage(feed.length)
            .then((d) => {
                if (!d) return
                setFeed((f) => {
                    const seen = new Set(f.map((x) => x.id))
                    return f.concat(d.items.filter((x: any) => !seen.has(x.id))) // 페이지 경계 신규글 중복 방지
                })
                setHasMore(!!d.has_more)
            })
            .finally(() => setMore(false))
    }

    // 종목명 매핑 (universe_search) — 실패해도 무해(티커 그대로 노출)
    useEffect(() => {
        if (onCanvas) {
            setNames({ "005930": "삼성전자", "000660": "SK하이닉스", NVDA: "NVIDIA", "035720": "카카오" })
            return
        }
        let alive = true
        fetch(UNIVERSE_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const a = d && (Array.isArray(d) ? d : d.stocks)
                if (!alive || !Array.isArray(a)) return
                const m: Record<string, string> = {}
                for (const x of a) {
                    const tk = String(x.ticker || "")
                    if (tk) m[tk] = x.name_ko || x.name || tk
                }
                setNames(m)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas])

    const tkName = (tk: string) => names[tk] || tk
    const goStock = (tk: string) => {
        if (onCanvas || typeof window === "undefined" || !tk) return
        const kr = /^\d{6}$/.test(tk)
        const p = (kr ? stockPath || "/stock" : _usPath(usStockPath, stockPath)).replace(/\/+$/, "")
        window.location.href = p + "?q=" + encodeURIComponent(tk)
    }

    // 종목 칩 = 최근 피드 등장 종목(글 수 내림차순). 원본 = overview(무필터) — 필터 중에도 목록 유지.
    const tickers = useMemo(() => {
        const cnt: Record<string, number> = {}
        for (const it of overview) {
            const tk = String(it.ticker || "")
            if (tk) cnt[tk] = (cnt[tk] || 0) + 1
        }
        return Object.keys(cnt).sort((a, b) => cnt[b] - cnt[a]).slice(0, 12)
    }, [overview])

    // 종목 검색 autocomplete — names(universe) 맵 재사용. 코드/이름 부분일치 상위 8, prefix 우선.
    const matches = useMemo(() => {
        const key = q.trim().toLowerCase()
        if (!key) return [] as [string, string][]
        const out: [string, string][] = []
        for (const tk in names) {
            const nm = String(names[tk] || "")
            if (tk.toLowerCase().indexOf(key) >= 0 || nm.toLowerCase().indexOf(key) >= 0) out.push([tk, nm])
            if (out.length > 60) break
        }
        const rk = (e: [string, string]) =>
            e[0].toLowerCase() === key ? 0 : e[0].toLowerCase().indexOf(key) === 0 ? 1 : e[1].toLowerCase().indexOf(key) === 0 ? 2 : 3
        return out.sort((a, b) => rk(a) - rk(b)).slice(0, 8)
    }, [q, names])

    // 정렬·필터 = 서버 처리(위 fetchPage). 캔버스 데모만 클라 필터.
    const shown = useMemo(
        () => (onCanvas && filterTk ? feed.filter((it) => it.ticker === filterTk) : feed),
        [feed, filterTk, onCanvas]
    )

    // 🚨 2026-07-24 사이드바 — 넓은 화면(≥940)만 우측에 트렌딩 종목. 피드는 가운데 단일 컬럼 유지(다열 금지=시간순 가독성).
    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries) setW(e.contentRect.width)
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])
    const wide = w >= 940
    const trending = useMemo(() => {
        const cnt: Record<string, number> = {}
        for (const it of overview) {
            const tk = String(it.ticker || "")
            if (tk) cnt[tk] = (cnt[tk] || 0) + 1
        }
        return Object.keys(cnt)
            .sort((a, b) => cnt[b] - cnt[a])
            .slice(0, 8)
            .map((tk) => [tk, cnt[tk]] as [string, number])
    }, [overview])

    const stanceStyle = (id: string): CSSProperties => {
        const col = id === "bull" ? C.up : id === "bear" ? C.down : C.faint
        const bgc = id === "bull" ? C.upS : id === "bear" ? C.downS : C.chipBg
        return { fontSize: 11, fontWeight: 800, color: col, background: bgc, borderRadius: 7, padding: "3px 8px", flexShrink: 0 }
    }

    const toggleLike = (it: any) => {
        if (onCanvas) return
        if (!token) {
            note("좋아요는 로그인 후 가능해요")
            return
        }
        const liked = !it.liked
        setFeed((f) =>
            f.map((x) => (x.id === it.id ? { ...x, liked, likes: Math.max(0, x.likes + (liked ? 1 : -1)) } : x))
        )
        fetch(base + "/api/thesis_feed", {
            method: "POST",
            headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({ action: liked ? "like" : "unlike", thesis_id: it.id }),
        }).catch(() => {})
    }
    /* 신고 — 사유 선택 후 전송(2026-07-25). 이전엔 reason:"" 하드코딩이라 /admin 모더레이션에서 사유가 안 보였음. */
    const openReport = (it: any) => {
        if (onCanvas || reported[it.id]) return
        setMenuId("")
        if (!token) {
            note("신고는 로그인 후 가능해요")
            return
        }
        setReportId(it.id)
    }
    const sendReport = (id: string, reason: string) => {
        setReportId("")
        if (onCanvas || !token || !id) return
        setReported((m) => ({ ...m, [id]: true }))
        fetch(base + "/api/thesis_feed", {
            method: "POST",
            headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({ action: "report", thesis_id: id, reason }),
        }).catch(() => {})
        note("신고가 접수됐어요 · 운영자가 확인해요")
    }

    /* 내 글 조작 — 비공개 전환(피드에서만 내림, 메모 보존) / 삭제(메모까지 제거).
       비공개는 thesis_feed unpublish 액션 사용 — /api/thesis POST 재사용 시 entry_price 가 NULL 로 덮임.
       🚨 낙관 제거 후 실패하면 원위치 복구. unpublish 액션 미배포 API(구버전)면 400 이 오는데,
          복구가 없으면 "내려간 것처럼 보이는데 새로고침하면 그대로" 상태가 됨. */
    const mutateMine = (it: any, req: () => Promise<Response>, okMsg: string) => {
        const idx = feed.findIndex((x) => x.id === it.id)
        setFeed((f) => f.filter((x) => x.id !== it.id))
        req()
            .then((r) => {
                if (r && r.ok) {
                    note(okMsg)
                    return
                }
                throw new Error("failed")
            })
            .catch(() => {
                setFeed((f) => {
                    if (f.some((x) => x.id === it.id)) return f
                    const next = f.slice()
                    next.splice(Math.max(0, Math.min(idx < 0 ? f.length : idx, f.length)), 0, it)
                    return next
                })
                note("처리하지 못했어요 · 잠시 후 다시 시도해 주세요")
            })
    }
    const unpublishItem = (it: any) => {
        setMenuId("")
        if (onCanvas) return
        if (!token) {
            note("로그인이 필요해요")
            return
        }
        mutateMine(
            it,
            () =>
                fetch(base + "/api/thesis_feed", {
                    method: "POST",
                    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
                    body: JSON.stringify({ action: "unpublish", thesis_id: it.id }),
                }),
            "피드에서 내렸어요 · 메모는 종목 페이지에 남아요"
        )
    }
    const deleteItem = (it: any) => {
        setMenuId("")
        if (onCanvas) return
        if (!token) {
            note("로그인이 필요해요")
            return
        }
        if (typeof window !== "undefined" && !window.confirm("이 관점을 삭제할까요? 메모도 함께 지워져요.")) return
        mutateMine(
            it,
            () =>
                fetch(base + "/api/thesis", {
                    method: "DELETE",
                    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
                    body: JSON.stringify({ ticker: it.ticker }),
                }),
            "삭제했어요"
        )
    }

    const submitSupport = () => {
        if (onCanvas || supportSending) return
        if (!token) {
            note("질문과 피드백은 로그인 후 보낼 수 있어요")
            return
        }
        const title = supportTitle.trim()
        const body = supportBody.trim()
        if (!title || !body) {
            note("제목과 내용을 입력해 주세요")
            return
        }
        setSupportSending(true)
        fetch(base + "/api/support", {
            method: "POST",
            headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({ kind: supportKind, title, body, publish_consent: supportKind === "question" && supportConsent }),
        })
            .then(async (r) => {
                const data = await r.json().catch(() => null)
                if (!r.ok) throw new Error(data?.error || "failed")
                setMySupport((items) => [data, ...items])
                setSupportTitle("")
                setSupportBody("")
                setSupportConsent(false)
                note(supportKind === "question" ? "질문을 접수했어요" : "피드백을 접수했어요")
            })
            .catch((e) => note(e?.message && e.message !== "failed" ? e.message : "접수하지 못했어요 · 잠시 후 다시 시도해 주세요"))
            .finally(() => setSupportSending(false))
    }

    const deleteSupport = (it: any) => {
        if (onCanvas || !token || it.status !== "open") return
        if (typeof window !== "undefined" && !window.confirm("이 접수 내용을 삭제할까요?")) return
        fetch(base + "/api/support", {
            method: "DELETE",
            headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({ id: it.id }),
        })
            .then((r) => {
                if (!r.ok) throw new Error("failed")
                setMySupport((items) => items.filter((x) => x.id !== it.id))
                note("삭제했어요")
            })
            .catch(() => note("삭제하지 못했어요"))
    }

    const updateLocalThesis = (ticker: string, patch: any, remove = false) => {
        try {
            const saved = JSON.parse(localStorage.getItem("verity_thesis_v1") || "{}") || {}
            if (remove) delete saved[ticker]
            else saved[ticker] = { ...(saved[ticker] || {}), ...patch }
            localStorage.setItem("verity_thesis_v1", JSON.stringify(saved))
            window.dispatchEvent(new Event("verity-thesis-changed"))
        } catch {}
    }

    const startMineEdit = (it: any) => {
        setEditingMine(String(it.id || it.ticker))
        setMineDraft({ stance: it.stance || "watch", note: it.note || "" })
    }

    const saveMineEdit = (it: any) => {
        const key = String(it.id || it.ticker)
        if (!mineDraft.note.trim()) {
            note("관점 메모를 입력해 주세요")
            return
        }
        setMineBusy(key)
        if (!token || it.local_only) {
            updateLocalThesis(it.ticker, { stance: mineDraft.stance, note: mineDraft.note.trim() })
            setMyTheses((items) => items.map((x) => x.ticker === it.ticker ? { ...x, stance: mineDraft.stance, note: mineDraft.note.trim() } : x))
            setEditingMine("")
            setMineBusy("")
            note("이 기기의 관점을 수정했어요")
            return
        }
        fetch(base + "/api/thesis", {
            method: "POST",
            headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({
                ticker: it.ticker, market: it.market || (/^\d{6}$/.test(it.ticker) ? "kr" : "us"),
                stance: mineDraft.stance, note: mineDraft.note.trim(), entry_price: it.entry_price,
                is_public: !!it.is_public,
            }),
        })
            .then(async (r) => {
                const data = await r.json().catch(() => null)
                if (!r.ok) throw new Error("failed")
                setMyTheses((items) => items.map((x) => x.ticker === it.ticker ? { ...x, ...data } : x))
                setEditingMine("")
                note("관점을 수정했어요")
            })
            .catch(() => note("수정하지 못했어요"))
            .finally(() => setMineBusy(""))
    }

    const setMinePublic = (it: any, nextPublic: boolean) => {
        const key = String(it.id || it.ticker)
        if (onCanvas) {
            setMyTheses((items) => items.map((x) => x.ticker === it.ticker ? { ...x, is_public: nextPublic } : x))
            return
        }
        if (!token || it.local_only) {
            note("공개 전환은 로그인 후 가능해요")
            return
        }
        setMineBusy(key)
        const request = nextPublic
            ? fetch(base + "/api/thesis", {
                method: "POST",
                headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
                body: JSON.stringify({
                    ticker: it.ticker, market: it.market || (/^\d{6}$/.test(it.ticker) ? "kr" : "us"),
                    stance: it.stance || "watch", note: it.note || "", entry_price: it.entry_price, is_public: true,
                }),
            })
            : fetch(base + "/api/thesis_feed", {
                method: "POST",
                headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
                body: JSON.stringify({ action: "unpublish", thesis_id: it.id }),
            })
        request
            .then(async (r) => {
                const data = await r.json().catch(() => null)
                if (!r.ok) throw new Error("failed")
                if (nextPublic && data?.nickname_required) {
                    note("프로필에서 별명을 정하면 공개할 수 있어요")
                    return
                }
                setMyTheses((items) => items.map((x) => x.ticker === it.ticker ? { ...x, ...data, is_public: nextPublic } : x))
                note(nextPublic ? "커뮤니티에 공개했어요" : "비공개로 전환했어요")
            })
            .catch(() => note("공개 설정을 바꾸지 못했어요"))
            .finally(() => setMineBusy(""))
    }

    const removeMyThesis = (it: any) => {
        const key = String(it.id || it.ticker)
        if (typeof window !== "undefined" && !window.confirm("이 관점을 삭제할까요?")) return
        if (!token || it.local_only) {
            updateLocalThesis(it.ticker, {}, true)
            setMyTheses((items) => items.filter((x) => x.ticker !== it.ticker))
            note("삭제했어요")
            return
        }
        setMineBusy(key)
        fetch(base + "/api/thesis", {
            method: "DELETE",
            headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({ ticker: it.ticker }),
        })
            .then((r) => {
                if (!r.ok) throw new Error("failed")
                setMyTheses((items) => items.filter((x) => x.ticker !== it.ticker))
                note("삭제했어요")
            })
            .catch(() => note("삭제하지 못했어요"))
            .finally(() => setMineBusy(""))
    }

    const visibleMyTheses = useMemo(() => myTheses.filter((it) =>
        mineVisibility === "all" || (mineVisibility === "public" ? !!it.is_public : !it.is_public)
    ), [myTheses, mineVisibility])

    const reuseExperiment = (it: any) => {
        if (typeof window === "undefined") return
        const visible = Array.isArray(it.assets) && it.assets.length === Number(it.asset_count || 0)
        if (!visible) {
            note("이 글은 종목 구성을 공개하지 않았어요")
            return
        }
        const draft = {
            assets: it.assets.map((x: any) => ({ ticker: x.ticker, name: x.name || x.ticker, market: x.market || "", weight: Number(x.weight || 0) })),
            amount: Number(it.contribution || 300000), start: it.start_date,
            frequency: it.frequency || "monthly", rebalance: it.rebalance || "yearly",
            dividend: !!it.dividend_reinvest, privacy: "private", savedAt: new Date().toISOString(),
        }
        localStorage.setItem("alphanest_portfolio_lab_draft", JSON.stringify(draft))
        window.location.href = "/lab"
    }

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, boxSizing: "border-box",
        color: C.ink, padding: "8px 16px 32px", display: "flex", justifyContent: "center",
        gap: wide ? 24 : 0, alignItems: "flex-start",
    }
    const col: CSSProperties = { width: "100%", maxWidth: 600, minWidth: 0 }
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 16px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 10 }

    const skBase = C.skBase
    const skHi = C.skHi
    const sk = (sw: any, sh: number, r = 6): CSSProperties => ({
        width: sw, height: sh, borderRadius: r, background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%", animation: "vcpShimmer 1.4s ease-in-out infinite", flexShrink: 0,
    })

    return (
        <div ref={rootRef} style={wrap}>
            <style>{AN_PALETTE}</style>
            <style>{`@keyframes vcpShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            {menuId && <div onClick={() => setMenuId("")} style={{ position: "fixed", inset: 0, zIndex: 20 }} />}

            {/* 신고 사유 시트 — 사유 없이 접수하던 경로 대체(2026-07-25) */}
            {reportId && (
                <div
                    onClick={() => setReportId("")}
                    style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(0,0,0,0.32)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
                >
                    <div
                        onClick={(e) => e.stopPropagation()}
                        style={{ width: "100%", maxWidth: 320, background: C.card, borderRadius: 16, padding: "16px 14px 10px", boxShadow: "0 12px 40px rgba(0,0,0,0.24)" }}
                    >
                        <div style={{ fontSize: 14.5, fontWeight: 800, color: C.ink, padding: "0 4px" }}>신고 사유</div>
                        <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 4, padding: "0 4px", lineHeight: 1.5 }}>
                            운영자가 확인 후 처리해요 · 허위 신고는 제재 대상
                        </div>
                        <div style={{ marginTop: 10 }}>
                            {REPORT_REASONS.map((r) => (
                                <button
                                    key={r}
                                    onClick={() => sendReport(reportId, r)}
                                    style={{ display: "block", width: "100%", textAlign: "left", border: "none", background: "transparent", cursor: "pointer", padding: "12px 10px", borderRadius: 10, fontFamily: FONT, fontSize: 13, fontWeight: 700, color: C.ink }}
                                >
                                    {r}
                                </button>
                            ))}
                        </div>
                        <button
                            onClick={() => setReportId("")}
                            style={{ width: "100%", marginTop: 6, border: "none", background: C.chipBg, color: C.sub, cursor: "pointer", padding: "11px 0", borderRadius: 10, fontFamily: FONT, fontSize: 12.5, fontWeight: 800 }}
                        >
                            취소
                        </button>
                    </div>
                </div>
            )}
            <div style={col}>
                {/* 헤더 */}
                <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>커뮤니티</div>
                <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>
                    함께 배우고, 질문하고, 내 투자 생각을 정리하는 공간이에요
                </div>

                {/* 메인 3탭 — 공개 피드 / 운영 소식·도움 / 개인 저널을 한 페이지 안에서 분리. */}
                <div role="tablist" aria-label="커뮤니티 메뉴" style={{ display: "flex", gap: 4, background: C.chipBg, borderRadius: 14, padding: 4, marginTop: 14 }}>
                    {([[
                        "community", "커뮤니티"
                    ], [
                        "support", "공지·Q&A"
                    ], [
                        "mine", "내 관점"
                    ]] as const).map(([key, label]) => (
                        <button
                            key={key}
                            role="tab"
                            aria-selected={mainTab === key}
                            onClick={() => setMainTab(key)}
                            style={{ flex: 1, border: "none", borderRadius: 10, padding: "10px 6px", background: mainTab === key ? C.card : "transparent", color: mainTab === key ? C.ink : C.faint, fontFamily: FONT, fontSize: 12.5, fontWeight: 850, cursor: "pointer", boxShadow: mainTab === key ? "0 1px 3px rgba(0,0,0,.06)" : "none", whiteSpace: "nowrap" }}
                        >
                            {label}
                        </button>
                    ))}
                </div>

                {/* 공지·이벤트 배너 — pinned 우선 1건. 닫으면 그 id 는 다시 안 뜸(localStorage). */}
                {(() => {
                    const nt = notices.filter((x) => String(x.id) !== seenNotice)[0]
                    if (!nt) return null
                    const ev = nt.kind === "event"
                    const body = (
                        <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                            <span style={{ flexShrink: 0, marginTop: 1, fontSize: 10.5, fontWeight: 800, color: ev ? C.onAccent : C.vg, background: ev ? C.vg : C.vgS, borderRadius: 6, padding: "3px 7px" }}>
                                {ev ? "이벤트" : "공지"}
                            </span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 13.5, fontWeight: 800, color: C.ink, letterSpacing: "-0.2px" }}>{nt.title}</div>
                                {nt.body ? (
                                    <div style={{ fontSize: 12, color: C.sub, fontWeight: 600, marginTop: 3, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{nt.body}</div>
                                ) : null}
                            </div>
                            <button
                                onClick={(e) => {
                                    e.preventDefault()
                                    e.stopPropagation()
                                    setSeenNotice(String(nt.id))
                                    try {
                                        localStorage.setItem("an_notice_seen", String(nt.id))
                                    } catch (err) {}
                                }}
                                aria-label="닫기"
                                style={{ flexShrink: 0, border: "none", background: "transparent", cursor: "pointer", color: C.faint, fontSize: 15, lineHeight: 1, padding: 2, fontFamily: FONT }}
                            >
                                ×
                            </button>
                        </div>
                    )
                    const box: CSSProperties = { ...card, marginTop: 12, padding: "13px 14px" }
                    return nt.link ? (
                        <a href={nt.link} target="_blank" rel="noopener noreferrer" style={{ ...box, display: "block", textDecoration: "none" }}>
                            {body}
                        </a>
                    ) : (
                        <div style={box}>{body}</div>
                    )
                })()}

                {mainTab === "community" && (
                <>
                {/* 종목 검색 */}
                <div style={{ position: "relative", marginTop: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 7, background: C.card, borderRadius: 999, padding: "9px 14px", boxSizing: "border-box" }}>
                        <span style={{ width: 13, height: 13, borderRadius: "50%", border: `2px solid ${C.faint}`, flexShrink: 0, position: "relative", display: "inline-block" }}>
                            <span style={{ position: "absolute", width: 2, height: 6, background: C.faint, right: -3, bottom: -3, transform: "rotate(-45deg)" }} />
                        </span>
                        <input
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            onFocus={() => setFocused(true)}
                            onBlur={() => setTimeout(() => setFocused(false), 160)}
                            placeholder="종목 검색 (이름·코드)"
                            style={{ border: "none", outline: "none", background: "transparent", color: C.ink, fontFamily: FONT, fontSize: 13.5, fontWeight: 600, width: "100%", minWidth: 0 }}
                        />
                        {q ? (
                            <button
                                onMouseDown={(e) => {
                                    e.preventDefault()
                                    setQ("")
                                }}
                                style={{ border: "none", background: "transparent", cursor: "pointer", color: C.faint, fontSize: 16, lineHeight: 1, flexShrink: 0, fontFamily: FONT }}
                            >
                                ×
                            </button>
                        ) : null}
                    </div>
                    {focused && !!q.trim() && matches.length > 0 ? (
                        <div style={{ position: "absolute", top: "100%", left: 0, right: 0, marginTop: 4, zIndex: 30, background: C.card, borderRadius: 12, boxShadow: "0 10px 30px rgba(0,0,0,0.16)", padding: 6, maxHeight: 300, overflowY: "auto" }}>
                            {matches.map(([tk, nm]) => (
                                <div
                                    key={tk}
                                    onMouseDown={() => {
                                        setFilterTk(tk)
                                        setQ("")
                                        setFocused(false)
                                    }}
                                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 9, cursor: "pointer" }}
                                >
                                    <StockLogo ticker={tk} name={nm || tk} C={C} size={24} />
                                    <span style={{ fontSize: 13.5, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{nm || tk}</span>
                                    <span style={{ marginLeft: "auto", flexShrink: 0, fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{tk}</span>
                                </div>
                            ))}
                        </div>
                    ) : null}
                </div>

                {/* 콘텐츠 유형 — 기존 관점과 포트폴리오 실험은 저장 구조·의미가 달라 탭으로 분리 */}
                <div style={{ display: "flex", gap: 4, background: C.chipBg, borderRadius: 12, padding: 4, marginTop: 12 }}>
                    {([["thesis", "종목 관점"], ["experiment", "포트폴리오 실험"]] as const).map(([key, label]) => (
                        <button key={key} onClick={() => setContentTab(key)} style={{ flex: 1, border: "none", borderRadius: 9, padding: "9px 10px", background: contentTab === key ? C.card : "transparent", color: contentTab === key ? C.ink : C.faint, fontFamily: FONT, fontSize: 12.5, fontWeight: 800, cursor: "pointer", boxShadow: contentTab === key ? "0 1px 3px rgba(0,0,0,.06)" : "none" }}>{label}</button>
                    ))}
                </div>

                {/* 정렬 세그먼트 + 종목 칩 (토스식) */}
                {contentTab === "thesis" && (
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
                    <div style={{ display: "flex", gap: 2, background: C.chipBg, borderRadius: 10, padding: 3, flexShrink: 0 }}>
                        {(
                            [
                                ["new", "최신"],
                                ["hot", "인기"],
                            ] as const
                        ).map(([k, lb]) => (
                            <button
                                key={k}
                                onClick={() => setSort(k)}
                                style={{ border: "none", cursor: "pointer", fontFamily: FONT, padding: "6px 13px", borderRadius: 8, fontSize: 12.5, fontWeight: 800, background: sort === k ? C.card : "transparent", color: sort === k ? C.ink : C.faint, boxShadow: sort === k ? "0 1px 2px rgba(0,0,0,0.06)" : "none" }}
                            >
                                {lb}
                            </button>
                        ))}
                    </div>
                    <div style={{ display: "flex", gap: 6, overflowX: "auto", scrollbarWidth: "none", minWidth: 0, flex: 1 }}>
                        <button
                            onClick={() => setFilterTk("")}
                            style={{ flexShrink: 0, border: "none", cursor: "pointer", fontFamily: FONT, padding: "6px 12px", borderRadius: 999, fontSize: 12, fontWeight: 700, background: !filterTk ? C.vg : C.card, color: !filterTk ? C.onAccent : C.sub }}
                        >
                            전체
                        </button>
                        {(filterTk && tickers.indexOf(filterTk) < 0 ? [filterTk, ...tickers] : tickers).map((tk) => (
                            <button
                                key={tk}
                                onClick={() => setFilterTk(filterTk === tk ? "" : tk)}
                                style={{ flexShrink: 0, border: "none", cursor: "pointer", fontFamily: FONT, padding: "6px 12px", borderRadius: 999, fontSize: 12, fontWeight: 700, background: filterTk === tk ? C.vg : C.card, color: filterTk === tk ? C.onAccent : C.sub, whiteSpace: "nowrap" }}
                            >
                                {tkName(tk)}
                            </button>
                        ))}
                    </div>
                </div>
                )}

                {/* 인기 = 전수 아님. 서버가 최근 window 개 안에서 좋아요순 집계 — 라벨로 명시(RULE 7 정합) */}
                {contentTab === "thesis" && sort === "hot" && hotWin > 0 && (
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 8 }}>
                        인기 = 최근 {hotWin}개 글 안에서 좋아요순 · 전체 기간 집계 아님
                    </div>
                )}

                {/* 좁은 화면(사이드바 없음) 또는 종목 필터 중 = 피드 위에 관점 온도 노출 */}
                {contentTab === "thesis" && stats && stats.total && (!wide || filterTk) ? (
                    <div style={{ ...card, marginTop: 10 }}>
                        <StanceBar
                            c={stats.total}
                            label={filterTk ? tkName(filterTk) + " 관점 온도" : "관점 온도"}
                            window={stats.window}
                        />
                    </div>
                ) : null}

                {msg && <div style={{ fontSize: 11.5, fontWeight: 700, color: C.up, marginTop: 10 }}>{msg}</div>}

                {/* 피드 */}
                {contentTab === "experiment" ? (
                    experimentsLoading ? (
                        [0, 1].map((i) => <div key={i} style={card}><div style={sk("45%", 14)} /><div style={{ ...sk("82%", 12), marginTop: 12 }} /><div style={{ ...sk("62%", 12), marginTop: 7 }} /></div>)
                    ) : experiments.length === 0 ? (
                        <div style={{ ...card, padding: "28px 18px", textAlign: "center" }}>
                            <div style={{ fontSize: 14, fontWeight: 800 }}>아직 공개된 포트폴리오 실험이 없어요</div>
                            <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.6 }}>/lab에서 조건을 만들고 공개 범위를 선택하면 이곳에서 함께 배울 수 있어요.</div>
                        </div>
                    ) : experiments.map((it) => (
                        <div key={it.id} style={card}>
                            <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                                {it.avatar ? <img src={it.avatar} alt="" width={36} height={36} style={{ width: 36, height: 36, borderRadius: 12, objectFit: "cover" }} /> : <div style={{ width: 36, height: 36, borderRadius: 12, background: C.vgS, color: C.vg, display: "flex", alignItems: "center", justifyContent: "center" }}><User size={18} weight="fill" /></div>}
                                <div><div style={{ fontSize: 13.5, fontWeight: 800 }}>{it.nickname || "익명"}</div><div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 2 }}>{fmtAgo(it.created_at)}</div></div>
                                <span style={{ marginLeft: "auto", borderRadius: 8, background: C.vgS, color: C.vg, padding: "4px 8px", fontSize: 10.5, fontWeight: 850 }}>투자 연습</span>
                            </div>
                            <div style={{ fontSize: 16, fontWeight: 900, marginTop: 13 }}>{it.title || "포트폴리오 실험"}</div>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginTop: 10 }}>
                                <span style={{ background: C.chipBg, borderRadius: 8, padding: "5px 8px", fontSize: 11.5, fontWeight: 750 }}>자산 {it.asset_count || 0}개</span>
                                <span style={{ background: C.chipBg, borderRadius: 8, padding: "5px 8px", fontSize: 11.5, fontWeight: 750 }}>{it.start_date || "시작일 미표시"}부터</span>
                                <span style={{ background: C.chipBg, borderRadius: 8, padding: "5px 8px", fontSize: 11.5, fontWeight: 750 }}>{Number(it.contribution || 0).toLocaleString("ko-KR")}원씩</span>
                            </div>
                            {Array.isArray(it.assets) && it.assets.length > 0 && <div style={{ display: "grid", gap: 6, marginTop: 11 }}>{it.assets.map((x: any, idx: number) => <div key={(x.ticker || x.market || "asset") + idx} style={{ display: "flex", justifyContent: "space-between", gap: 10, borderRadius: 10, background: C.chipBg, padding: "8px 10px", fontSize: 12, fontWeight: 700 }}><span>{x.name || x.market || "비공개 자산군"}{x.ticker ? ` · ${x.ticker}` : ""}</span><span style={{ color: C.vg }}>{Number(x.weight || 0).toFixed(2).replace(".00", "")}%</span></div>)}</div>}
                            <div style={{ marginTop: 11, color: C.sub, fontSize: 11.5, lineHeight: 1.6, fontWeight: 650 }}>수익률 계산 엔진 연결 전 조건 공유 단계예요. 공개된 수익률로 오해하지 마세요.</div>
                            <button onClick={() => reuseExperiment(it)} style={{ width: "100%", marginTop: 11, border: "none", borderRadius: 12, background: C.vgS, color: C.vg, padding: "11px 12px", fontFamily: FONT, fontSize: 12.5, fontWeight: 850, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>이 조건으로 연습하기 <ArrowRight size={15} weight="bold" /></button>
                        </div>
                    ))
                ) : loading ? (
                    [0, 1, 2].map((i) => (
                        <div key={i} style={card}>
                            <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                                <div style={sk(36, 36, 12)} />
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={sk("38%", 13)} />
                                    <div style={{ ...sk("22%", 10), marginTop: 6 }} />
                                </div>
                            </div>
                            <div style={{ ...sk("92%", 12), marginTop: 12 }} />
                            <div style={{ ...sk("70%", 12), marginTop: 7, marginBottom: 6 }} />
                        </div>
                    ))
                ) : shown.length === 0 ? (
                    <div style={{ ...card, padding: "26px 18px", textAlign: "center" }}>
                        <div style={{ fontSize: 14, fontWeight: 800 }}>
                            {filterTk ? "이 종목의 공개 관점이 아직 없어요" : "아직 공개된 관점이 없어요"}
                        </div>
                        <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.6 }}>
                            종목 페이지의 '내 관점 메모'에서 공개로 저장하면 여기에 실려요.
                        </div>
                    </div>
                ) : (
                    shown.map((it) => {
                        const noteLong = String(it.note || "").length > 220 || String(it.note || "").split("\n").length > 6
                        const open = !!expanded[it.id]
                        const noteShown = !noteLong || open ? it.note : String(it.note).slice(0, 220).replace(/\n[^\n]*$/, "") + "…"
                        return (
                            <div key={it.id} style={card}>
                                {/* 헤더 행 (인스타 틀: 아바타 + 별명 + 시간 + ⋯) */}
                                <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                                    {it.avatar ? (
                                        <img src={it.avatar} alt="" loading="lazy" decoding="async" width={36} height={36} style={{ width: 36, height: 36, borderRadius: 12, objectFit: "cover", flexShrink: 0 }} />
                                    ) : (
                                        <div style={{ width: 36, height: 36, borderRadius: 12, background: C.chipBg, color: C.faint, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                                            <User size={18} weight="fill" />
                                        </div>
                                    )}
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ fontSize: 13.5, fontWeight: 800, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                            {it.nickname}
                                            {it.mine ? " (나)" : ""}
                                        </div>
                                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 1 }}>{fmtAgo(it.created_at)}</div>
                                    </div>
                                    {/* ⋯ 메뉴 — 내 글: 비공개 전환·삭제 / 남의 글: 신고(2026-07-25. 이전엔 내 글에 메뉴 자체가 없어 피드에서 못 내렸음) */}
                                    <span style={{ position: "relative", flexShrink: 0, display: "inline-flex" }}>
                                        <button
                                            onClick={() => setMenuId(menuId === it.id ? "" : it.id)}
                                            aria-label="더보기"
                                            style={{ border: "none", background: "transparent", cursor: "pointer", padding: 2, margin: -2, display: "inline-flex", alignItems: "center", color: C.faint }}
                                        >
                                            <DotsThree size={20} weight="bold" />
                                        </button>
                                        {menuId === it.id && (
                                            <div style={{ position: "absolute", top: 24, right: 0, zIndex: 30, background: C.card, borderRadius: 10, boxShadow: "0 4px 14px rgba(0,0,0,0.12)", overflow: "hidden", minWidth: 132 }}>
                                                {it.mine ? (
                                                    <>
                                                        <button
                                                            onClick={() => unpublishItem(it)}
                                                            style={{ display: "block", width: "100%", textAlign: "left", border: "none", background: "transparent", cursor: "pointer", padding: "10px 14px", fontFamily: FONT, fontSize: 12, fontWeight: 700, color: C.ink, whiteSpace: "nowrap" }}
                                                        >
                                                            비공개로 전환
                                                        </button>
                                                        <button
                                                            onClick={() => deleteItem(it)}
                                                            style={{ display: "block", width: "100%", textAlign: "left", border: "none", borderTop: `1px solid ${C.line}`, background: "transparent", cursor: "pointer", padding: "10px 14px", fontFamily: FONT, fontSize: 12, fontWeight: 700, color: C.up, whiteSpace: "nowrap" }}
                                                        >
                                                            삭제
                                                        </button>
                                                    </>
                                                ) : (
                                                    <button
                                                        onClick={() => openReport(it)}
                                                        disabled={!!reported[it.id]}
                                                        style={{ display: "block", width: "100%", textAlign: "left", border: "none", background: "transparent", cursor: reported[it.id] ? "default" : "pointer", padding: "10px 14px", fontFamily: FONT, fontSize: 12, fontWeight: 700, color: reported[it.id] ? C.faint : C.up, whiteSpace: "nowrap" }}
                                                    >
                                                        {reported[it.id] ? "신고 접수됨" : "신고하기"}
                                                    </button>
                                                )}
                                            </div>
                                        )}
                                    </span>
                                </div>

                                {/* 종목 칩 + 스탠스 (토스식 정보 행) */}
                                {it.ticker && (
                                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
                                        <button
                                            onClick={() => goStock(it.ticker)}
                                            style={{ border: "none", cursor: "pointer", fontFamily: FONT, display: "inline-flex", alignItems: "center", gap: 6, background: C.chipBg, borderRadius: 8, padding: "4px 9px 4px 5px", fontSize: 11.5, fontWeight: 800, color: C.ink }}
                                        >
                                            <StockLogo ticker={it.ticker} name={tkName(it.ticker)} C={C} size={20} />
                                            {tkName(it.ticker)}
                                            <span style={{ color: C.faint, fontWeight: 600 }}>{it.ticker} ›</span>
                                        </button>
                                        <span style={stanceStyle(it.stance)}>{STANCE_LABEL[it.stance] || "관망"}</span>
                                    </div>
                                )}

                                {/* 본문 (쓰레드식 clamp + 더보기) */}
                                {it.note && (
                                    <div style={{ fontSize: 13.5, color: C.ink, fontWeight: 500, lineHeight: 1.6, marginTop: 9, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                                        {noteShown}
                                        {noteLong && (
                                            <button
                                                onClick={() => setExpanded((m) => ({ ...m, [it.id]: !open }))}
                                                style={{ border: "none", background: "transparent", cursor: "pointer", fontFamily: FONT, fontSize: 12, fontWeight: 700, color: C.faint, padding: "0 0 0 4px" }}
                                            >
                                                {open ? "접기" : "더보기"}
                                            </button>
                                        )}
                                    </div>
                                )}

                                {/* 액션 행 (인스타 틀: 하트 + 댓글 자리) */}
                                <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 10, paddingTop: 9, borderTop: `1px solid ${C.line}` }}>
                                    <button
                                        onClick={() => toggleLike(it)}
                                        style={{ display: "inline-flex", alignItems: "center", gap: 5, border: "none", background: "transparent", cursor: "pointer", padding: 0, fontFamily: FONT, fontSize: 12, fontWeight: 700, color: it.liked ? C.up : C.faint }}
                                    >
                                        <Heart size={17} weight={it.liked ? "fill" : "regular"} />
                                        {it.likes > 0 ? it.likes : "좋아요"}
                                    </button>
                                    <span
                                        title="댓글은 준비 중이에요"
                                        style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 700, color: C.faint, opacity: 0.45, cursor: "default" }}
                                    >
                                        <ChatCircle size={17} />
                                        댓글 곧
                                    </span>
                                </div>
                            </div>
                        )
                    })
                )}

                {/* 더보기 — 서버 offset 페이지네이션(2026-07-25). has_more=false 면 숨김 */}
                {contentTab === "thesis" && !loading && hasMore && (
                    <button
                        onClick={loadMore}
                        disabled={more}
                        style={{ width: "100%", marginTop: 10, border: "none", cursor: more ? "default" : "pointer", background: C.card, color: more ? C.faint : C.vg, borderRadius: 12, padding: "12px 0", fontFamily: FONT, fontSize: 12.5, fontWeight: 800, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}
                    >
                        {more ? "불러오는 중" : "더보기"}
                    </button>
                )}

                <div style={{ textAlign: "center", fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 16, lineHeight: 1.6 }}>
                    피드의 모든 글 = 이용자 개인 의견 · AlphaNest 의 분석·판단·추천 아님 · 부적절한 글은 ⋯ 메뉴로 신고
                </div>
                </>
                )}

                {mainTab === "support" && (
                    <div role="tabpanel" style={{ marginTop: 12 }}>
                        <section style={{ ...card, marginTop: 0, padding: "16px" }}>
                            <div style={{ fontSize: 15, fontWeight: 850 }}>공지사항</div>
                            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3 }}>서비스 변경과 데이터 점검 소식을 확인하세요.</div>
                            {notices.length === 0 ? (
                                <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 650, padding: "18px 0 4px" }}>현재 안내할 소식이 없어요.</div>
                            ) : notices.map((nt, i) => (
                                <div key={nt.id || i} style={{ background: C.chipBg, borderRadius: 12, padding: "12px 13px", marginTop: 9 }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                        <span style={{ borderRadius: 7, background: nt.kind === "event" ? C.vg : C.vgS, color: nt.kind === "event" ? C.onAccent : C.vg, padding: "3px 7px", fontSize: 10.5, fontWeight: 850 }}>{nt.kind === "event" ? "이벤트" : "공지"}</span>
                                        <span style={{ fontSize: 13.5, fontWeight: 850, minWidth: 0 }}>{nt.title}</span>
                                        <span style={{ marginLeft: "auto", color: C.faint, fontSize: 10.5, fontWeight: 650, flexShrink: 0 }}>{String(nt.created_at || "").slice(0, 10)}</span>
                                    </div>
                                    {nt.body ? <div style={{ color: C.sub, fontSize: 12.5, fontWeight: 600, lineHeight: 1.6, marginTop: 7, whiteSpace: "pre-wrap" }}>{nt.body}</div> : null}
                                    {nt.link ? <a href={nt.link} target="_blank" rel="noopener noreferrer" style={{ display: "inline-flex", color: C.vg, fontSize: 12, fontWeight: 800, textDecoration: "none", marginTop: 8 }}>자세히 보기 →</a> : null}
                                </div>
                            ))}
                        </section>

                        <section style={{ ...card, padding: "16px" }}>
                            <div style={{ fontSize: 15, fontWeight: 850 }}>질문·피드백 보내기</div>
                            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.55 }}>모르는 내용은 질문하고, 오류나 개선 의견은 비공개로 알려주세요.</div>
                            <div style={{ display: "flex", gap: 4, background: C.chipBg, borderRadius: 11, padding: 4, marginTop: 12 }}>
                                {([[
                                    "question", "Q&A 질문"
                                ], [
                                    "feedback", "비공개 피드백"
                                ]] as const).map(([key, label]) => (
                                    <button key={key} onClick={() => { setSupportKind(key); if (key === "feedback") setSupportConsent(false) }} style={{ flex: 1, border: "none", borderRadius: 8, background: supportKind === key ? C.card : "transparent", color: supportKind === key ? C.ink : C.faint, padding: "8px 8px", fontFamily: FONT, fontSize: 12, fontWeight: 800, cursor: "pointer" }}>{label}</button>
                                ))}
                            </div>
                            <input
                                value={supportTitle}
                                onChange={(e) => setSupportTitle(e.target.value.slice(0, 120))}
                                maxLength={120}
                                aria-label="질문 또는 피드백 제목"
                                placeholder={supportKind === "question" ? "무엇이 궁금한가요?" : "어떤 점을 개선하면 좋을까요?"}
                                style={{ width: "100%", boxSizing: "border-box", border: "none", outline: "none", borderRadius: 11, background: C.chipBg, color: C.ink, padding: "11px 12px", marginTop: 10, fontFamily: FONT, fontSize: 13, fontWeight: 650 }}
                            />
                            <textarea
                                value={supportBody}
                                onChange={(e) => setSupportBody(e.target.value.slice(0, 2000))}
                                maxLength={2000}
                                aria-label="질문 또는 피드백 내용"
                                placeholder="상황과 궁금한 점을 편하게 적어주세요. 계좌번호와 연락처 같은 개인정보는 입력하지 마세요."
                                style={{ width: "100%", minHeight: 112, resize: "vertical", boxSizing: "border-box", border: "none", outline: "none", borderRadius: 11, background: C.chipBg, color: C.ink, padding: "11px 12px", marginTop: 8, fontFamily: FONT, fontSize: 13, fontWeight: 600, lineHeight: 1.55 }}
                            />
                            {supportKind === "question" ? (
                                <label style={{ display: "flex", alignItems: "flex-start", gap: 8, color: C.sub, fontSize: 11.5, fontWeight: 650, lineHeight: 1.5, marginTop: 9, cursor: "pointer" }}>
                                    <input type="checkbox" checked={supportConsent} onChange={(e) => setSupportConsent(e.target.checked)} style={{ marginTop: 2, accentColor: C.vg }} />
                                    답변이 끝난 뒤 다른 이용자도 배울 수 있도록 질문과 답변 공개에 동의해요. 선택하지 않으면 나에게만 보여요.
                                </label>
                            ) : (
                                <div style={{ color: C.faint, fontSize: 11.5, fontWeight: 650, lineHeight: 1.5, marginTop: 9 }}>피드백은 작성자와 운영자만 확인할 수 있어요.</div>
                            )}
                            <button
                                onClick={submitSupport}
                                disabled={supportSending}
                                style={{ width: "100%", border: "none", borderRadius: 11, background: supportSending ? C.chipBg : C.vg, color: supportSending ? C.faint : C.onAccent, padding: "11px 12px", marginTop: 11, fontFamily: FONT, fontSize: 12.5, fontWeight: 850, cursor: supportSending ? "default" : "pointer" }}
                            >
                                {!token ? "로그인 후 보내기" : supportSending ? "보내는 중" : supportKind === "question" ? "질문 보내기" : "피드백 보내기"}
                            </button>
                        </section>

                        {msg && <div style={{ fontSize: 11.5, fontWeight: 750, color: C.up, marginTop: 10 }}>{msg}</div>}

                        <section style={{ ...card, padding: "16px" }}>
                            <div style={{ fontSize: 15, fontWeight: 850 }}>함께 보는 Q&A</div>
                            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3 }}>작성자가 공개에 동의했고 답변이 끝난 질문만 보여요.</div>
                            {supportLoading ? (
                                [0, 1].map((i) => <div key={i} style={{ marginTop: 13 }}><div style={sk("68%", 13)} /><div style={{ ...sk("92%", 11), marginTop: 8 }} /></div>)
                            ) : publicQna.length === 0 ? (
                                <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 650, padding: "18px 0 3px" }}>공개된 답변이 아직 없어요.</div>
                            ) : publicQna.map((qa, i) => (
                                <article key={qa.id || i} style={{ background: C.chipBg, borderRadius: 12, padding: "13px", marginTop: 9 }}>
                                    <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}><span style={{ color: C.vg, fontSize: 13, fontWeight: 900 }}>Q</span><div style={{ fontSize: 13.5, fontWeight: 850, lineHeight: 1.5 }}>{qa.title}</div></div>
                                    {qa.body ? <div style={{ color: C.sub, fontSize: 12, fontWeight: 600, lineHeight: 1.55, margin: "6px 0 0 21px", whiteSpace: "pre-wrap" }}>{qa.body}</div> : null}
                                    <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginTop: 10 }}><span style={{ color: C.up, fontSize: 13, fontWeight: 900 }}>A</span><div style={{ color: C.ink, fontSize: 12.5, fontWeight: 650, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{qa.answer}</div></div>
                                </article>
                            ))}
                        </section>

                        {token ? (
                            <section style={{ ...card, padding: "16px" }}>
                                <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}><span style={{ fontSize: 15, fontWeight: 850 }}>내 접수 내역</span><span style={{ color: C.faint, fontSize: 11, fontWeight: 700 }}>{mySupport.length}건</span></div>
                                {supportLoading ? <div style={{ color: C.faint, fontSize: 12.5, fontWeight: 650, padding: "16px 0 2px" }}>불러오는 중…</div> : mySupport.length === 0 ? (
                                    <div style={{ color: C.faint, fontSize: 12.5, fontWeight: 650, padding: "16px 0 2px" }}>접수한 내용이 없어요.</div>
                                ) : mySupport.map((it, i) => {
                                    const statusLabel = it.status === "answered" ? "답변 완료" : it.status === "closed" ? "종료" : "확인 중"
                                    const statusColor = it.status === "answered" ? C.vg : it.status === "closed" ? C.faint : C.down
                                    return (
                                        <div key={it.id || i} style={{ background: C.chipBg, borderRadius: 12, padding: "12px 13px", marginTop: 9 }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                                <span style={{ color: it.kind === "feedback" ? C.down : C.vg, fontSize: 10.5, fontWeight: 850 }}>{it.kind === "feedback" ? "피드백" : "질문"}</span>
                                                <span style={{ fontSize: 13, fontWeight: 800, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.title}</span>
                                                <span style={{ color: statusColor, background: C.card, borderRadius: 7, padding: "3px 7px", marginLeft: "auto", flexShrink: 0, fontSize: 10.5, fontWeight: 850 }}>{statusLabel}</span>
                                            </div>
                                            <div style={{ color: C.sub, fontSize: 12, fontWeight: 600, lineHeight: 1.55, marginTop: 7, whiteSpace: "pre-wrap" }}>{it.body}</div>
                                            {it.answer ? <div style={{ background: C.card, borderRadius: 10, color: C.ink, fontSize: 12, fontWeight: 650, lineHeight: 1.6, padding: "10px 11px", marginTop: 9, whiteSpace: "pre-wrap" }}><span style={{ color: C.vg, fontWeight: 850 }}>답변 · </span>{it.answer}</div> : null}
                                            {it.status === "open" ? <button onClick={() => deleteSupport(it)} style={{ border: "none", background: "transparent", color: C.faint, fontFamily: FONT, fontSize: 11, fontWeight: 750, padding: "8px 0 0", cursor: "pointer" }}>접수 취소</button> : null}
                                        </div>
                                    )
                                })}
                            </section>
                        ) : null}
                    </div>
                )}

                {mainTab === "mine" && (
                    <div role="tabpanel" style={{ marginTop: 12 }}>
                        <section style={{ ...card, marginTop: 0, padding: "16px" }}>
                            <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}><span style={{ fontSize: 15, fontWeight: 850 }}>내 관점</span><span style={{ color: C.faint, fontSize: 11, fontWeight: 700 }}>{myTheses.length}개</span></div>
                            <div style={{ color: C.faint, fontSize: 11.5, fontWeight: 600, lineHeight: 1.55, marginTop: 3 }}>{token ? "어느 기기에서든 저장한 관점을 확인하고 공개 여부를 관리할 수 있어요." : "로그인 전 기록은 현재 기기에만 저장돼요. 로그인하면 여러 기기에서 이어볼 수 있어요."}</div>
                            <div style={{ display: "flex", gap: 6, marginTop: 11, overflowX: "auto" }}>
                                {([[
                                    "all", `전체 ${myTheses.length}`
                                ], [
                                    "public", `공개 ${myTheses.filter((x) => x.is_public).length}`
                                ], [
                                    "private", `비공개 ${myTheses.filter((x) => !x.is_public).length}`
                                ]] as const).map(([key, label]) => (
                                    <button key={key} onClick={() => setMineVisibility(key)} style={{ flexShrink: 0, border: "none", borderRadius: 999, background: mineVisibility === key ? C.vg : C.chipBg, color: mineVisibility === key ? C.onAccent : C.sub, padding: "7px 11px", fontFamily: FONT, fontSize: 11.5, fontWeight: 800, cursor: "pointer" }}>{label}</button>
                                ))}
                            </div>
                        </section>

                        {msg && <div style={{ fontSize: 11.5, fontWeight: 750, color: C.up, marginTop: 10 }}>{msg}</div>}

                        {mineLoading ? (
                            [0, 1, 2].map((i) => <div key={i} style={card}><div style={sk("46%", 14)} /><div style={{ ...sk("88%", 11), marginTop: 10 }} /></div>)
                        ) : visibleMyTheses.length === 0 ? (
                            <div style={{ ...card, padding: "28px 18px", textAlign: "center" }}>
                                <div style={{ fontSize: 14, fontWeight: 850 }}>표시할 관점이 없어요</div>
                                <div style={{ color: C.faint, fontSize: 12, fontWeight: 600, lineHeight: 1.6, marginTop: 6 }}>종목 리포트에서 내 생각과 다시 확인할 조건을 기록해 보세요.</div>
                                <button onClick={() => { if (!onCanvas && typeof window !== "undefined") window.location.href = stockPath || "/stock" }} style={{ border: "none", borderRadius: 10, background: C.vgS, color: C.vg, padding: "9px 13px", marginTop: 12, fontFamily: FONT, fontSize: 12, fontWeight: 850, cursor: "pointer" }}>종목 찾아보기</button>
                            </div>
                        ) : visibleMyTheses.map((it, i) => {
                            const key = String(it.id || it.ticker)
                            const editing = editingMine === key
                            const busy = mineBusy === key
                            return (
                                <article key={key + i} style={{ ...card, padding: "15px 16px" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                                        <StockLogo ticker={it.ticker} name={tkName(it.ticker)} C={C} size={32} />
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ fontSize: 14, fontWeight: 850, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tkName(it.ticker)}</div>
                                            <div style={{ color: C.faint, fontSize: 10.5, fontWeight: 650, marginTop: 2 }}>{it.ticker} · {String(it.updated_at || it.created_at || "").slice(0, 10) || "날짜 없음"}</div>
                                        </div>
                                        <span style={stanceStyle(it.stance)}>{STANCE_LABEL[it.stance] || "관망"}</span>
                                        <span style={{ color: it.is_public ? C.vg : C.faint, background: it.is_public ? C.vgS : C.chipBg, borderRadius: 7, padding: "3px 7px", fontSize: 10.5, fontWeight: 850 }}>{it.is_public ? "공개" : "비공개"}</span>
                                    </div>

                                    {editing ? (
                                        <div style={{ marginTop: 11 }}>
                                            <div style={{ display: "flex", gap: 5 }}>
                                                {([[
                                                    "bull", "강세"
                                                ], [
                                                    "watch", "관망"
                                                ], [
                                                    "bear", "약세"
                                                ]] as const).map(([stance, label]) => (
                                                    <button key={stance} onClick={() => setMineDraft((d: any) => ({ ...d, stance }))} style={{ flex: 1, border: "none", borderRadius: 9, background: mineDraft.stance === stance ? (stance === "bull" ? C.upS : stance === "bear" ? C.downS : C.card) : C.chipBg, color: mineDraft.stance === stance ? (stance === "bull" ? C.up : stance === "bear" ? C.down : C.ink) : C.faint, padding: "7px 5px", fontFamily: FONT, fontSize: 11.5, fontWeight: 800, cursor: "pointer" }}>{label}</button>
                                                ))}
                                            </div>
                                            <textarea value={mineDraft.note} onChange={(e) => setMineDraft((d: any) => ({ ...d, note: e.target.value.slice(0, 2000) }))} maxLength={2000} aria-label={`${it.ticker} 관점 메모`} style={{ width: "100%", minHeight: 94, resize: "vertical", boxSizing: "border-box", border: "none", outline: "none", borderRadius: 11, background: C.chipBg, color: C.ink, padding: "10px 11px", marginTop: 8, fontFamily: FONT, fontSize: 12.5, fontWeight: 600, lineHeight: 1.55 }} />
                                            <div style={{ display: "flex", gap: 7, marginTop: 8 }}>
                                                <button onClick={() => setEditingMine("")} style={{ flex: 1, border: "none", borderRadius: 9, background: C.chipBg, color: C.sub, padding: "9px", fontFamily: FONT, fontSize: 11.5, fontWeight: 800, cursor: "pointer" }}>취소</button>
                                                <button onClick={() => saveMineEdit(it)} disabled={busy} style={{ flex: 1, border: "none", borderRadius: 9, background: C.vg, color: C.onAccent, padding: "9px", fontFamily: FONT, fontSize: 11.5, fontWeight: 850, cursor: busy ? "default" : "pointer" }}>{busy ? "저장 중" : "수정 저장"}</button>
                                            </div>
                                        </div>
                                    ) : (
                                        <>
                                            <div style={{ color: it.note ? C.ink : C.faint, fontSize: 12.5, fontWeight: 600, lineHeight: 1.6, marginTop: 10, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{it.note || "메모가 없어요."}</div>
                                            {Number(it.entry_price) > 0 ? <div style={{ color: C.faint, fontSize: 10.5, fontWeight: 650, marginTop: 7 }}>기록 기준가 {Math.round(Number(it.entry_price)).toLocaleString("ko-KR")}{/^\d{6}$/.test(it.ticker) ? "원" : ""}</div> : null}
                                            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 11 }}>
                                                <button onClick={() => goStock(it.ticker)} style={{ border: "none", borderRadius: 9, background: C.chipBg, color: C.sub, padding: "8px 10px", fontFamily: FONT, fontSize: 11.5, fontWeight: 800, cursor: "pointer" }}>리포트 열기</button>
                                                <button onClick={() => startMineEdit(it)} style={{ border: "none", borderRadius: 9, background: C.chipBg, color: C.sub, padding: "8px 10px", fontFamily: FONT, fontSize: 11.5, fontWeight: 800, cursor: "pointer" }}>수정</button>
                                                <button onClick={() => setMinePublic(it, !it.is_public)} disabled={busy || !!it.local_only} title={it.local_only ? "로그인 후 공개할 수 있어요" : ""} style={{ border: "none", borderRadius: 9, background: it.is_public ? C.downS : C.vgS, color: it.is_public ? C.down : C.vg, padding: "8px 10px", fontFamily: FONT, fontSize: 11.5, fontWeight: 850, cursor: busy || it.local_only ? "default" : "pointer", opacity: it.local_only ? 0.55 : 1 }}>{it.is_public ? "비공개로" : "공개하기"}</button>
                                                <button onClick={() => removeMyThesis(it)} disabled={busy} style={{ border: "none", borderRadius: 9, background: "transparent", color: C.faint, padding: "8px 6px", fontFamily: FONT, fontSize: 11.5, fontWeight: 750, cursor: busy ? "default" : "pointer" }}>삭제</button>
                                            </div>
                                        </>
                                    )}
                                </article>
                            )
                        })}
                    </div>
                )}
            </div>

            {/* 🚨 2026-07-24 우측 사이드바 — 넓은 화면만. 트렌딩 종목(관점 수 상위) → 클릭 시 피드 필터 */}
            {wide && mainTab === "community" && contentTab === "thesis" && (
                <aside style={{ width: 264, flexShrink: 0, position: "sticky", top: 20 }}>
                    {/* 관점 온도 — 사실 집계(글 수). 종목 필터 시 그 종목 기준으로 전환 */}
                    {stats && stats.total ? (
                        <div style={{ ...card, marginTop: 0 }}>
                            <StanceBar
                                c={stats.total}
                                label={filterTk ? tkName(filterTk) + " 관점 온도" : "관점 온도"}
                                window={stats.window}
                            />
                        </div>
                    ) : null}
                    <div style={{ ...card, marginTop: stats && stats.total ? 10 : 0 }}>
                        <div style={{ fontSize: 13.5, fontWeight: 800, color: C.ink, letterSpacing: "-0.2px" }}>트렌딩 종목</div>
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 2, marginBottom: 6 }}>관점이 많은 종목</div>
                        {trending.length === 0 ? (
                            <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, padding: "4px 0" }}>아직 없어요</div>
                        ) : (
                            trending.map(([tk, n], i) => (
                                <div
                                    key={tk}
                                    onClick={() => setFilterTk(filterTk === tk ? "" : tk)}
                                    role="button"
                                    style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}`, cursor: "pointer" }}
                                >
                                    <StockLogo ticker={tk} name={names[tk] || tk} C={C} size={26} />
                                    <span style={{ fontSize: 13, fontWeight: 700, color: filterTk === tk ? C.vg : C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>{names[tk] || tk}</span>
                                    <span style={{ marginLeft: "auto", flexShrink: 0, fontSize: 11.5, color: C.faint, fontWeight: 700 }}>{n}</span>
                                </div>
                            ))
                        )}
                    </div>
                </aside>
            )}
        </div>
    )
}

addPropertyControls(PublicCommunityPage, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    stockPath: { type: ControlType.String, title: "Stock Path (KR)", defaultValue: "/stock" },
    usStockPath: { type: ControlType.String, title: "Stock Path (US)", defaultValue: "/stock" },
    limit: { type: ControlType.Number, title: "글 수", defaultValue: 30, min: 5, max: 50, step: 5 },
    dark: { type: ControlType.Boolean, title: "Dark(미사용)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

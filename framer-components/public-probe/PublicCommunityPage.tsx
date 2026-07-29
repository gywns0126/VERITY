import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"
import { ChatCircle, DotsThree, Heart, User } from "@phosphor-icons/react"

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

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, boxSizing: "border-box",
        color: C.ink, padding: "20px 16px 32px", display: "flex", justifyContent: "center",
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
                    종목 관점을 나누는 공간 · 모든 글은 이용자 개인 의견이며 AlphaNest 의 분석·판단·추천이 아니에요
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
                    const box: CSSProperties = { ...card, marginTop: 12, padding: "13px 14px", border: `1px solid ${ev ? C.vg : C.line}` }
                    return nt.link ? (
                        <a href={nt.link} target="_blank" rel="noopener noreferrer" style={{ ...box, display: "block", textDecoration: "none" }}>
                            {body}
                        </a>
                    ) : (
                        <div style={box}>{body}</div>
                    )
                })()}

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

                {/* 정렬 세그먼트 + 종목 칩 (토스식) */}
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

                {/* 인기 = 전수 아님. 서버가 최근 window 개 안에서 좋아요순 집계 — 라벨로 명시(RULE 7 정합) */}
                {sort === "hot" && hotWin > 0 && (
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 8 }}>
                        인기 = 최근 {hotWin}개 글 안에서 좋아요순 · 전체 기간 집계 아님
                    </div>
                )}

                {/* 좁은 화면(사이드바 없음) 또는 종목 필터 중 = 피드 위에 관점 온도 노출 */}
                {stats && stats.total && (!wide || filterTk) ? (
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
                {loading ? (
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
                                            <div style={{ position: "absolute", top: 24, right: 0, zIndex: 30, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, boxShadow: "0 4px 14px rgba(0,0,0,0.12)", overflow: "hidden", minWidth: 132 }}>
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
                {!loading && hasMore && (
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
            </div>

            {/* 🚨 2026-07-24 우측 사이드바 — 넓은 화면만. 트렌딩 종목(관점 수 상위) → 클릭 시 피드 필터 */}
            {wide && (
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

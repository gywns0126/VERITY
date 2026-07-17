import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"
import { ChatCircle, DotsThree, Heart, User } from "@phosphor-icons/react"

/**
 * 커뮤니티 페이지 — 전 종목 공개 관점 글로벌 피드 (2026-07-10, PM 결정 = 비공개 초안).
 *
 * 🚨 배치 참조: 토스(중앙 단일 컬럼 + 세그먼트 정렬 + 종목 칩 필터 + 카드 리스트) × 인스타/쓰레드(아바타 헤더 + 본문 + 하트·⋯ 액션 행).
 * 🚨 공개 게이트: 이 컴포넌트를 올린 Framer 페이지 = 네비 미연결 초안 유지. 규모(글 수·이용자) 확인 후 PM 이 공개 결정.
 * 데이터 = /api/thesis_feed (ticker 생략 = 전 종목 최신). 종목명 = universe_search.json 매핑(실패 시 티커 그대로).
 * 댓글 = v2 예정 — 버튼 자리만(비활성). 좋아요/신고 = 종목 피드와 동일 API.
 * 🚨 RULE 7 — 피드 = 이용자 개인 의견 라벨 필수 (AlphaNest 분석·판단 아님). RULE 6 — LLM 0.
 */

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", up: "#f04452", upS: "#fdecee", down: "#3182f6", downS: "#e8f1fe",
    vg: "#6c5ce7", vgS: "#f0edff", chipBg: "#e8ebef", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", up: "#f04452", upS: "#31181c", down: "#5b9bff", downS: "#16233a",
    vg: "#a99bff", vgS: "#241f3a", chipBg: "#1e242c", onAccent: "#0f1318",
}

const STANCE_LABEL: Record<string, string> = { bull: "강세", watch: "관망", bear: "약세" }
const UNIVERSE_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
const DEFAULT_API = "https://project-yw131.vercel.app"

const DEMO_FEED = [
    { id: "d1", ticker: "005930", nickname: "길동무", avatar: "", stance: "bull", note: "수주 잔고 증가 + 부채비율 하향 추세. 다음 분기 마진 확인 후 재검토.", created_at: "2026-07-09T09:00:00Z", likes: 12, liked: false, mine: false },
    { id: "d2", ticker: "NVDA", nickname: "가치사냥", avatar: "", stance: "watch", note: "밸류는 부담스러운데 수요가 계속 확인됨. 조정 오면 다시 본다.", created_at: "2026-07-08T13:00:00Z", likes: 7, liked: true, mine: false },
    { id: "d3", ticker: "000660", nickname: "느린걸음", avatar: "", stance: "bull", note: "HBM 증설 스케줄 그대로면 하반기 실적 방향은 위라고 본다.\n리스크 = 환율.", created_at: "2026-07-07T02:00:00Z", likes: 4, liked: false, mine: false },
    { id: "d4", ticker: "035720", nickname: "관망러", avatar: "", stance: "bear", note: "신사업 비용이 아직 무겁다. 흑자 전환 확인 전까진 보수적으로.", created_at: "2026-07-05T10:00:00Z", likes: 1, liked: false, mine: false },
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

function readBodyDark(): boolean {
    // 첫 페인트 flash 방지 — body 속성 미설정(마운트 직후) 시 토글 저장 선호(localStorage) → OS 순 폴백.
    // PublicThemeToggle 이 verity_theme 로 저장 + body[data-framer-theme] 설정 = 동일 소스라 첫 페인트부터 정합.
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
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

// ── 종목 로고(Brandfetch logo_map) + 원형 국기(circle-flags) — 뉴스탭과 동일 소스 ──
const BF_CID = "1idalDez9T7KlggM8qX"
const BF_MAP_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
let __bfMap: Record<string, string> | null = null
let __bfP: Promise<Record<string, string>> | null = null
function fetchBfMap(): Promise<Record<string, string>> {
    if (__bfMap) return Promise.resolve(__bfMap)
    if (!__bfP) __bfP = fetch(BF_MAP_URL).then((r) => (r.ok ? r.json() : null)).then((d) => { __bfMap = (d && d.logos) || {}; return __bfMap as Record<string, string> }).catch(() => ({} as Record<string, string>))
    return __bfP
}
function useBfLogoMap(): Record<string, string> | null {
    const [m, setM] = useState<Record<string, string> | null>(__bfMap)
    useEffect(() => { let al = true; fetchBfMap().then((mm) => { if (al) setM(mm) }); return () => { al = false } }, [])
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
    const ch = (String(name || "?").trim().charAt(0)) || "?"
    const code = /^\d{6}$/.test(String(ticker || "")) ? "kr" : "us"
    const f = Math.round(size * 0.46)
    return (
        <span style={{ position: "relative", width: size, height: size, flexShrink: 0, display: "inline-block" }}>
            {!err && src ? (
                <img src={src} alt="" loading="lazy" decoding="async" width={size} height={size} onError={() => setErr(true)}
                    style={{ width: size, height: size, borderRadius: Math.round(size * 0.3), objectFit: "cover", background: "transparent", display: "block" }} />
            ) : (
                <span style={{ width: size, height: size, borderRadius: Math.round(size * 0.3), background: C.chipBg, color: C.faint, display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * 0.42), fontWeight: 800 }}>{ch}</span>
            )}
            <img src={FLAG_BASE + code + ".svg"} alt="" loading="lazy" decoding="async" width={f} height={f}
                style={{ position: "absolute", right: -3, bottom: -3, width: f, height: f, borderRadius: "50%", border: `1.5px solid ${C.card}`, background: C.card, display: "block" }} />
        </span>
    )
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicCommunityPage(props: Props) {
    const { apiBase, stockPath, usStockPath, limit, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")
    const cap = Math.max(5, Math.min(50, limit || 30))

    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))
    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT
    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const [token, setToken] = useState("")
    const [feed, setFeed] = useState<any[]>([])
    const [loading, setLoading] = useState(true)
    const [sort, setSort] = useState<"new" | "hot">("new")
    const [filterTk, setFilterTk] = useState("")
    const [names, setNames] = useState<Record<string, string>>({})
    const [msg, setMsg] = useState("")
    const [menuId, setMenuId] = useState("")
    const [reported, setReported] = useState<Record<string, boolean>>({})
    const [expanded, setExpanded] = useState<Record<string, boolean>>({})
    const [q, setQ] = useState("")            // 종목 검색어(이름/코드)
    const [focused, setFocused] = useState(false)

    // 세션 토큰 추적(로그인/로그아웃 반영 — AlphaNestAuth 가 dispatch)
    useEffect(() => {
        if (onCanvas) return
        const sync = () => setToken(getToken())
        sync()
        window.addEventListener("verity_auth_change", sync)
        window.addEventListener("storage", sync)
        return () => { window.removeEventListener("verity_auth_change", sync); window.removeEventListener("storage", sync) }
    }, [onCanvas])

    // 피드 로드 — ticker 생략 = 전 종목 최신
    useEffect(() => {
        if (onCanvas) { setFeed(DEMO_FEED); setLoading(false); return }
        setLoading(true)
        const h: Record<string, string> = {}
        const t = getToken()
        if (t) h.Authorization = "Bearer " + t
        fetch(base + "/api/thesis_feed?limit=" + cap, { headers: h, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (d && Array.isArray(d.items)) setFeed(d.items) })
            .catch(() => {})
            .finally(() => setLoading(false))
    }, [base, cap, onCanvas])

    // 종목명 매핑 (universe_search) — 실패해도 무해(티커 그대로 노출)
    useEffect(() => {
        if (onCanvas) { setNames({ "005930": "삼성전자", "000660": "SK하이닉스", NVDA: "NVIDIA", "035720": "카카오" }); return }
        let alive = true
        fetch(UNIVERSE_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const a = d && (Array.isArray(d) ? d : d.stocks)
                if (!alive || !Array.isArray(a)) return
                const m: Record<string, string> = {}
                for (const x of a) { const tk = String(x.ticker || ""); if (tk) m[tk] = x.name_ko || x.name || tk }
                setNames(m)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas])

    const tkName = (tk: string) => names[tk] || tk
    const goStock = (tk: string) => {
        if (onCanvas || typeof window === "undefined" || !tk) return
        const kr = /^\d{6}$/.test(tk)
        const p = (kr ? (stockPath || "/stock") : (usStockPath || "/us/stock")).replace(/\/+$/, "")
        window.location.href = p + "?q=" + encodeURIComponent(tk)
    }

    // 종목 칩 = 피드 등장 종목(글 수 내림차순)
    const tickers = useMemo(() => {
        const cnt: Record<string, number> = {}
        for (const it of feed) { const tk = String(it.ticker || ""); if (tk) cnt[tk] = (cnt[tk] || 0) + 1 }
        return Object.keys(cnt).sort((a, b) => cnt[b] - cnt[a]).slice(0, 12)
    }, [feed])

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
        const rk = (e: [string, string]) => (e[0].toLowerCase() === key ? 0 : e[0].toLowerCase().indexOf(key) === 0 ? 1 : e[1].toLowerCase().indexOf(key) === 0 ? 2 : 3)
        return out.sort((a, b) => rk(a) - rk(b)).slice(0, 8)
    }, [q, names])

    const shown = useMemo(() => {
        let arr = filterTk ? feed.filter((it) => it.ticker === filterTk) : feed.slice()
        if (sort === "hot") arr = arr.slice().sort((a, b) => (b.likes - a.likes) || String(b.created_at).localeCompare(String(a.created_at)))
        return arr
    }, [feed, filterTk, sort])

    const stanceStyle = (id: string): CSSProperties => {
        const col = id === "bull" ? C.up : id === "bear" ? C.down : C.faint
        const bgc = id === "bull" ? C.upS : id === "bear" ? C.downS : C.chipBg
        return { fontSize: 11, fontWeight: 800, color: col, background: bgc, borderRadius: 7, padding: "3px 8px", flexShrink: 0 }
    }

    const toggleLike = (it: any) => {
        if (onCanvas) return
        if (!token) { setMsg("좋아요는 로그인 후 가능해요"); return }
        const liked = !it.liked
        setFeed((f) => f.map((x) => (x.id === it.id ? { ...x, liked, likes: Math.max(0, x.likes + (liked ? 1 : -1)) } : x)))
        fetch(base + "/api/thesis_feed", { method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify({ action: liked ? "like" : "unlike", thesis_id: it.id }) }).catch(() => {})
    }
    const reportItem = (it: any) => {
        if (onCanvas || reported[it.id]) return
        if (!token) { setMenuId(""); setMsg("신고는 로그인 후 가능해요"); return }
        setReported((m) => ({ ...m, [it.id]: true }))
        setMenuId("")
        fetch(base + "/api/thesis_feed", { method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify({ action: "report", thesis_id: it.id, reason: "" }) }).catch(() => {})
    }

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, boxSizing: "border-box", color: C.ink, padding: "20px 16px 32px", display: "flex", justifyContent: "center" }
    const col: CSSProperties = { width: "100%", maxWidth: 600, minWidth: 0 }
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 16px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 10 }

    const skBase = (onCanvas ? !!dark : themeDark) ? "#222a33" : "#e9edf1"
    const skHi = (onCanvas ? !!dark : themeDark) ? "#2d3742" : "#f3f5f7"
    const sk = (sw: any, sh: number, r = 6): CSSProperties => ({
        width: sw, height: sh, borderRadius: r, background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%", animation: "vcpShimmer 1.4s ease-in-out infinite", flexShrink: 0,
    })

    return (
        <div style={wrap}>
            <style>{`@keyframes vcpShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            {menuId && <div onClick={() => setMenuId("")} style={{ position: "fixed", inset: 0, zIndex: 20 }} />}
            <div style={col}>
                {/* 헤더 */}
                <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.5px" }}>커뮤니티</div>
                <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>
                    종목 관점을 나누는 공간 · 모든 글은 이용자 개인 의견이며 AlphaNest 의 분석·판단·추천이 아니에요
                </div>

                {/* 종목 검색 — 아무 종목이나 검색해 그 종목 관점만 필터(상위 칩 밖 종목 접근) */}
                <div style={{ position: "relative", marginTop: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 7, background: C.card, borderRadius: 999, padding: "9px 14px", boxSizing: "border-box" }}>
                        <span style={{ width: 13, height: 13, borderRadius: "50%", border: `2px solid ${C.faint}`, flexShrink: 0, position: "relative", display: "inline-block" }}>
                            <span style={{ position: "absolute", width: 2, height: 6, background: C.faint, right: -3, bottom: -3, transform: "rotate(-45deg)" }} />
                        </span>
                        <input value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => setFocused(true)} onBlur={() => setTimeout(() => setFocused(false), 160)}
                            placeholder="종목 검색 (이름·코드)"
                            style={{ border: "none", outline: "none", background: "transparent", color: C.ink, fontFamily: FONT, fontSize: 13.5, fontWeight: 600, width: "100%", minWidth: 0 }} />
                        {q ? <button onMouseDown={(e) => { e.preventDefault(); setQ("") }} style={{ border: "none", background: "transparent", cursor: "pointer", color: C.faint, fontSize: 16, lineHeight: 1, flexShrink: 0, fontFamily: FONT }}>×</button> : null}
                    </div>
                    {focused && !!q.trim() && matches.length > 0 ? (
                        <div style={{ position: "absolute", top: "100%", left: 0, right: 0, marginTop: 4, zIndex: 30, background: C.card, borderRadius: 12, boxShadow: "0 10px 30px rgba(0,0,0,0.16)", padding: 6, maxHeight: 300, overflowY: "auto" }}>
                            {matches.map(([tk, nm]) => (
                                <div key={tk} onMouseDown={() => { setFilterTk(tk); setQ(""); setFocused(false) }}
                                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 9, cursor: "pointer" }}>
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
                        {([["new", "최신"], ["hot", "인기"]] as const).map(([k, lb]) => (
                            <button key={k} onClick={() => setSort(k)}
                                style={{ border: "none", cursor: "pointer", fontFamily: FONT, padding: "6px 13px", borderRadius: 8, fontSize: 12.5, fontWeight: 800, background: sort === k ? C.card : "transparent", color: sort === k ? C.ink : C.faint, boxShadow: sort === k ? "0 1px 2px rgba(0,0,0,0.06)" : "none" }}>{lb}</button>
                        ))}
                    </div>
                    <div style={{ display: "flex", gap: 6, overflowX: "auto", scrollbarWidth: "none", minWidth: 0, flex: 1 }}>
                        <button onClick={() => setFilterTk("")}
                            style={{ flexShrink: 0, border: "none", cursor: "pointer", fontFamily: FONT, padding: "6px 12px", borderRadius: 999, fontSize: 12, fontWeight: 700, background: !filterTk ? C.vg : C.card, color: !filterTk ? C.onAccent : C.sub }}>전체</button>
                        {(filterTk && tickers.indexOf(filterTk) < 0 ? [filterTk, ...tickers] : tickers).map((tk) => (
                            <button key={tk} onClick={() => setFilterTk(filterTk === tk ? "" : tk)}
                                style={{ flexShrink: 0, border: "none", cursor: "pointer", fontFamily: FONT, padding: "6px 12px", borderRadius: 999, fontSize: 12, fontWeight: 700, background: filterTk === tk ? C.vg : C.card, color: filterTk === tk ? C.onAccent : C.sub, whiteSpace: "nowrap" }}>{tkName(tk)}</button>
                        ))}
                    </div>
                </div>

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
                        <div style={{ fontSize: 14, fontWeight: 800 }}>{filterTk ? "이 종목의 공개 관점이 아직 없어요" : "아직 공개된 관점이 없어요"}</div>
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
                                        <div style={{ width: 36, height: 36, borderRadius: 12, background: C.chipBg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                                            <User size={18} color={C.faint} weight="fill" />
                                        </div>
                                    )}
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ fontSize: 13.5, fontWeight: 800, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{it.nickname}{it.mine ? " (나)" : ""}</div>
                                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 1 }}>{fmtAgo(it.created_at)}</div>
                                    </div>
                                    {!it.mine && (
                                        <span style={{ position: "relative", flexShrink: 0, display: "inline-flex" }}>
                                            <button onClick={() => setMenuId(menuId === it.id ? "" : it.id)} aria-label="더보기"
                                                style={{ border: "none", background: "transparent", cursor: "pointer", padding: 2, margin: -2, display: "inline-flex", alignItems: "center", color: C.faint }}>
                                                <DotsThree size={20} weight="bold" color={C.faint} />
                                            </button>
                                            {menuId === it.id && (
                                                <div style={{ position: "absolute", top: 24, right: 0, zIndex: 30, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, boxShadow: "0 4px 14px rgba(0,0,0,0.12)", overflow: "hidden", minWidth: 104 }}>
                                                    <button onClick={() => reportItem(it)} disabled={!!reported[it.id]}
                                                        style={{ display: "block", width: "100%", textAlign: "left", border: "none", background: "transparent", cursor: reported[it.id] ? "default" : "pointer", padding: "10px 14px", fontFamily: FONT, fontSize: 12, fontWeight: 700, color: reported[it.id] ? C.faint : C.up, whiteSpace: "nowrap" }}>
                                                        {reported[it.id] ? "신고 접수됨" : "신고하기"}
                                                    </button>
                                                </div>
                                            )}
                                        </span>
                                    )}
                                </div>

                                {/* 종목 칩 + 스탠스 (토스식 정보 행) */}
                                {it.ticker && (
                                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
                                        <button onClick={() => goStock(it.ticker)}
                                            style={{ border: "none", cursor: "pointer", fontFamily: FONT, display: "inline-flex", alignItems: "center", gap: 6, background: C.chipBg, borderRadius: 8, padding: "4px 9px 4px 5px", fontSize: 11.5, fontWeight: 800, color: C.ink }}>
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
                                            <button onClick={() => setExpanded((m) => ({ ...m, [it.id]: !open }))}
                                                style={{ border: "none", background: "transparent", cursor: "pointer", fontFamily: FONT, fontSize: 12, fontWeight: 700, color: C.faint, padding: "0 0 0 4px" }}>{open ? "접기" : "더보기"}</button>
                                        )}
                                    </div>
                                )}

                                {/* 액션 행 (인스타 틀: 하트 + 댓글 자리) */}
                                <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 10, paddingTop: 9, borderTop: `1px solid ${C.line}` }}>
                                    <button onClick={() => toggleLike(it)}
                                        style={{ display: "inline-flex", alignItems: "center", gap: 5, border: "none", background: "transparent", cursor: "pointer", padding: 0, fontFamily: FONT, fontSize: 12, fontWeight: 700, color: it.liked ? C.up : C.faint }}>
                                        <Heart size={17} weight={it.liked ? "fill" : "regular"} color={it.liked ? C.up : C.faint} />
                                        {it.likes > 0 ? it.likes : "좋아요"}
                                    </button>
                                    <span title="댓글은 준비 중이에요" style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 700, color: C.faint, opacity: 0.45, cursor: "default" }}>
                                        <ChatCircle size={17} color={C.faint} />
                                        댓글 곧
                                    </span>
                                </div>
                            </div>
                        )
                    })
                )}

                <div style={{ textAlign: "center", fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 16, lineHeight: 1.6 }}>
                    피드의 모든 글 = 이용자 개인 의견 · AlphaNest 의 분석·판단·추천 아님 · 부적절한 글은 ⋯ 메뉴로 신고
                </div>
            </div>
        </div>
    )
}

addPropertyControls(PublicCommunityPage, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    stockPath: { type: ControlType.String, title: "Stock Path (KR)", defaultValue: "/stock" },
    usStockPath: { type: ControlType.String, title: "Stock Path (US)", defaultValue: "/us/stock" },
    limit: { type: ControlType.Number, title: "글 수", defaultValue: 30, min: 5, max: 50, step: 5 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

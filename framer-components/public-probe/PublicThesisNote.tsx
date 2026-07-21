import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"
import { Heart, User } from "@phosphor-icons/react"

/**
 * 내 관점(thesis) 노트 — VERITY 공개 터미널. 종목 페이지에서 *사용자 본인*의 매매 결정 thesis 를 기록·재방문.
 *
 * 🚨 RULE 7 = 이건 **사용자 자기 저널**(관점/메모/날짜)이지 VERITY 의 추천·점수가 아님. 우리는 채점/판단 0.
 * 🚨 RULE 6 = LLM 0. 전부 사용자 입력 + 결정론적 가격 diff.
 * 저장 = localStorage `verity_thesis_v1` + "verity-thesis-changed" 이벤트 → PublicWatchlist 즉시 관점 배지 갱신.
 * 가격 = stock_flow_5d.json 마지막 close(종가, 네이버 소스·발행 유지 판정) — 기록 시점 entryPrice 동결 → 재방문 diff.
 * 🚨 시세 재배포 컴플라이언스(2026-07-03 Phase 1.5): /api/stock 실시간가 조회 제거(KIS 재배포 불가) → 종가 diff 로 전환. 커버리지 밖 = graceful "—".
 * ticker = prop → URL ?q= → localStorage `verity_last_ticker` 폴백(페이지 토글 시 종목 유지).
 *   + "verity-ticker-change" 이벤트 수신 → 같은 페이지 PublicDecisionPanel(검색 통합)이 종목 바꾸면 리로드 없이 따라옴(2026-06-23).
 * 커뮤니티 v1(2026-07-10, 020 migration): 공개 토글(기본 비공개·별명 필수) + 종목별 공개 관점 피드 + 좋아요 + 신고.
 *   피드 = /api/thesis_feed (익명 조회 가능, 별명·아바타만 노출 — 실명/이메일/기록가 비노출).
 *   🚨 피드 내용 = 이용자 개인 의견 라벨 필수 (AlphaNest 분석·판단 아님).
 */

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", up: "#f04452", down: "#3182f6", upS: "#fdecee", downS: "#eaf1fe", vg: "#0ca678", vgS: "#e7faf0", vt: "#6c5ce7", vtS: "#f0edff", chipBg: "#f2f4f6" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff", upS: "#2a1a1d", downS: "#17263c", vg: "#34e08a", vgS: "#11281d", vt: "#a99bff", vtS: "#241f3a", chipBg: "#0f1318" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const STORE_KEY = "verity_thesis_v1"
const LAST_TK_KEY = "verity_last_ticker"
const TK_EVENT = "verity-ticker-change"
const SESSION_KEY = "verity_supabase_session"
const MIGRATED_KEY = "verity_thesis_migrated_v1"

function loadToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return ""
        const s = JSON.parse(raw)
        if (s && s.expires_at && Date.now() / 1000 > s.expires_at) return ""   // 만료 가드 — 만료 토큰 반환 시 401 유발
        return typeof s.access_token === "string" ? s.access_token : ""
    } catch { return "" }
}
function mapServerRow(r: any): any {
    if (!r) return null
    return { stance: r.stance || "watch", note: r.note || "", date: (r.created_at || "").slice(0, 10), entryPrice: r.entry_price != null ? Number(r.entry_price) : null, isPublic: !!r.is_public, _server: true }
}

const STANCES: { id: string; label: string; key: "up" | "down" | "faint" }[] = [
    { id: "bull", label: "강세", key: "up" },
    { id: "watch", label: "관망", key: "faint" },
    { id: "bear", label: "약세", key: "down" },
]

interface Props {
    ticker: string
    apiBase: string
    dark: boolean
}

function loadAll(): Record<string, any> {
    if (typeof window === "undefined") return {}
    try { return JSON.parse(window.localStorage.getItem(STORE_KEY) || "{}") || {} } catch { return {} }
}
function saveAll(o: Record<string, any>) {
    if (typeof window === "undefined") return
    try { window.localStorage.setItem(STORE_KEY, JSON.stringify(o)); window.dispatchEvent(new Event("verity-thesis-changed")) } catch { /* quota/private */ }
}
function todayStr(): string {
    const d = new Date()
    const k = new Date(d.getTime() + (d.getTimezoneOffset() + 540) * 60000) // KST
    return k.toISOString().slice(0, 10)
}
function daysSince(dateStr: string): number {
    try {
        const a = new Date(dateStr + "T00:00:00+09:00").getTime()
        const b = new Date(todayStr() + "T00:00:00+09:00").getTime()
        return Math.max(0, Math.round((b - a) / 86400000))
    } catch { return 0 }
}
function won(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x === 0) return "—"
    return Math.round(x).toLocaleString("en-US") + "원"
}

const DEMO_THESIS = { stance: "bull", note: "PER·PBR 업종 이하 + 내부자 순매수. 부채 낮음. 실적발표 후 재검토.", date: "2026-06-14", entryPrice: 71200, name: "DL이앤씨", isPublic: true }
const DEMO_FEED = [
    { id: "d1", nickname: "길동무", avatar: "", stance: "bull", note: "수주 잔고 증가 + 부채비율 하향 추세. 다음 분기 마진 확인 후 재검토.", created_at: "2026-07-08", likes: 3, liked: false, mine: false },
    { id: "d2", nickname: "가치사냥", avatar: "", stance: "watch", note: "밸류는 싼데 거래량이 죽어 있음. 수급 돌아서면 다시 본다.", created_at: "2026-07-05", likes: 1, liked: true, mine: false },
]

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.
let __anHyd = false
function anReadDark(): boolean {
    if (typeof document === "undefined") return false
    if (!__anHyd) {
        __anHyd = true
        return false
    }
    const h = document.documentElement ? document.documentElement.dataset.anTheme : null
    if (h === "dark") return true
    if (h === "light") return false
    return !!(document.body && document.body.dataset.framerTheme === "dark")
}


// 마운트/토글 재판독 SoT — verity_theme(localStorage) 우선 → html[data-an-theme] → body[data-framer-theme].
// 791d29f7e 8개 fix 에서 누락됐던 body-only 재판독 버그 정정(다크에서 라이트 고정 방지, 2026-07-21 일괄).
function readBodyDark(): boolean {
    if (typeof document === "undefined") return false
    try {
        const pref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (pref === "dark") return true
        if (pref === "light") return false
        const h = document.documentElement ? document.documentElement.dataset.anTheme : null
        if (h === "dark") return true
        if (h === "light") return false
        if (document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

export default function PublicThesisNote(props: Props) {
    const { ticker, apiBase, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    // 테마 추종 — 사이트 다크모드(body[data-framer-theme]) 따라감. 캔버스는 dark prop 정적.
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : anReadDark()))
    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])
    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

    const resolveTk = (): string => {
        if (ticker && ticker.trim()) return ticker.trim()
        if (typeof window !== "undefined") {
            try {
                const q = (new URLSearchParams(window.location.search).get("q") || "").trim()
                if (q) { try { window.localStorage.setItem(LAST_TK_KEY, q) } catch { /* */ } ; return q }
                return (window.localStorage.getItem(LAST_TK_KEY) || "").trim()
            } catch { return "" }
        }
        return ""
    }
    const [tk, setTk] = useState<string>(resolveTk)

    // 통합 DecisionPanel 이 종목 바꾸면(이벤트) / 뒤로가기(popstate) 시 리로드 없이 추종
    useEffect(() => {
        if (onCanvas) return
        const reread = () => setTk(resolveTk())
        reread()
        window.addEventListener(TK_EVENT, reread)
        window.addEventListener("popstate", reread)
        return () => { window.removeEventListener(TK_EVENT, reread); window.removeEventListener("popstate", reread) }
    }, [ticker, onCanvas])

    // 로그인/토큰갱신 후 토큰 재읽기 → 서버 thesis·피드 재fetch (token 키 loader 자동 재실행). verity_auth_change=AuthGate dispatch · storage=타탭
    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        const onAuth = () => setToken(loadToken())
        window.addEventListener("verity_auth_change", onAuth)
        window.addEventListener("storage", onAuth)
        return () => {
            window.removeEventListener("verity_auth_change", onAuth)
            window.removeEventListener("storage", onAuth)
        }
    }, [onCanvas])

    const [thesis, setThesis] = useState<any>(null)   // 저장된 기록
    const [editing, setEditing] = useState(false)
    const [stance, setStance] = useState("watch")
    const [note, setNote] = useState("")
    const [curPrice, setCurPrice] = useState<number | null>(null)
    const [token, setToken] = useState<string>(loadToken)
    const [serverTheses, setServerTheses] = useState<Record<string, any> | null>(null)  // null=미로드(로그인 시)
    // 커뮤니티 v1 — 공개 토글 + 종목별 공개 피드 + 좋아요/신고
    const [isPublic, setIsPublic] = useState(false)
    const [pubMsg, setPubMsg] = useState("")     // 토글/저장 영역 메시지
    const [feedMsg, setFeedMsg] = useState("")   // 피드 영역 메시지(좋아요/신고 로그인 안내)
    const [feed, setFeed] = useState<any[]>([])
    const [reported, setReported] = useState<Record<string, boolean>>({})

    const loadFeed = (t: string) => {
        if (onCanvas || !t) return
        const h: Record<string, string> = {}
        if (token) h.Authorization = "Bearer " + token
        fetch(base + "/api/thesis_feed?ticker=" + encodeURIComponent(t), { headers: h, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (d && Array.isArray(d.items)) setFeed(d.items) })
            .catch(() => {})
    }
    useEffect(() => {
        setFeed([])
        setReported({})
        setPubMsg("")
        setFeedMsg("")
        if (onCanvas) { setFeed(DEMO_FEED); return }
        loadFeed(tk)
    }, [tk, onCanvas])

    // 로그인 시 서버 thesis 전량 로드 + localStorage 1회 마이그레이션 (cross-device)
    useEffect(() => {
        if (onCanvas || !token || !base) return
        let alive = true
        fetch(base + "/api/thesis", { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((rows) => {
                if (!alive) return
                if (!Array.isArray(rows)) { setServerTheses({}); return }
                const map: Record<string, any> = {}
                for (const r of rows) if (r && r.ticker) map[String(r.ticker)] = mapServerRow(r)
                try {
                    if (!localStorage.getItem(MIGRATED_KEY)) {
                        const local = loadAll()
                        Object.keys(local).forEach((t) => {
                            const v = local[t]
                            if (!map[t] && v) {
                                fetch(base + "/api/thesis", { method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify({ ticker: t, market: "kr", stance: v.stance, note: v.note, entry_price: v.entryPrice }) }).catch(() => {})
                                map[t] = { stance: v.stance, note: v.note, date: v.date, entryPrice: v.entryPrice, _server: true }
                            }
                        })
                        localStorage.setItem(MIGRATED_KEY, "1")
                    }
                } catch { /* */ }
                setServerTheses(map)
            })
            .catch(() => { if (alive) setServerTheses({}) })
        return () => { alive = false }
    }, [token, base, onCanvas])

    // 기록 로드 — dual: 로그인=서버맵 / 익명=localStorage
    useEffect(() => {
        if (onCanvas) { setThesis(DEMO_THESIS); return }
        if (!tk) { setThesis(null); setEditing(false); return }
        let t: any = null
        if (token) { if (serverTheses === null) return; t = serverTheses[tk] || null }
        else { t = loadAll()[tk] || null }
        setThesis(t)
        setEditing(!t)
        if (t) { setStance(t.stance); setNote(t.note || ""); setIsPublic(!!t.isPublic) } else { setStance("watch"); setNote(""); setIsPublic(false) }
    }, [tk, onCanvas, token, serverTheses])

    // 종가 (재방문 diff용 + 기록 시 entryPrice 동결) — stock_flow_5d 마지막 close(실시간 아님, 컴플라이언스)
    useEffect(() => {
        setCurPrice(null)
        if (onCanvas) { setCurPrice(73900); return }
        if (!tk) return
        let alive = true
        fetch("https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_flow_5d.json")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d) return
                const fm = d.flows || d
                const arr = fm && fm[tk]
                const last = Array.isArray(arr) && arr.length ? arr[arr.length - 1] : null
                const c = last && Number(last.close)
                if (c && isFinite(c)) setCurPrice(c)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [tk, onCanvas])

    const save = () => {
        if (onCanvas || !tk) return
        const ep = (thesis && thesis.entryPrice != null) ? thesis.entryPrice : (curPrice != null ? curPrice : null)
        const pub = token ? isPublic : false  // 익명 = 서버행 없음 → 공개 불가
        const rec = { stance, note: note.trim(), date: (thesis && thesis.date) || todayStr(), entryPrice: ep, updated: todayStr(), isPublic: pub }
        if (token) {
            fetch(base + "/api/thesis", { method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify({ ticker: tk, market: "kr", stance, note: note.trim(), entry_price: ep, is_public: pub }) })
                .then(async (r) => {
                    if (!r.ok) return
                    const d = await r.json().catch(() => null)
                    if (d && d.nickname_required) {
                        // 별명 없이 공개 시도 → 서버가 비공개로 저장. 안내 + 로컬 상태 정합.
                        setIsPublic(false)
                        setPubMsg("공개하려면 별명이 필요해요 — 내정보에서 별명을 설정해 주세요")
                        setThesis((t: any) => (t ? { ...t, isPublic: false } : t))
                        setServerTheses((m) => (m && m[tk] ? { ...m, [tk]: { ...m[tk], isPublic: false } } : m))
                    } else {
                        loadFeed(tk)
                    }
                })
                .catch(() => {})
            setServerTheses((m) => ({ ...(m || {}), [tk]: { ...rec, _server: true } }))
            try { window.dispatchEvent(new Event("verity-thesis-changed")) } catch { /* */ }
        } else {
            const all = loadAll(); all[tk] = rec; saveAll(all)
        }
        setThesis(rec)
        setEditing(false)
    }
    const remove = () => {
        if (onCanvas || !tk) return
        if (token) {
            fetch(base + "/api/thesis", { method: "DELETE", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify({ ticker: tk }) }).catch(() => {})
            setServerTheses((m) => { const n = { ...(m || {}) }; delete n[tk]; return n })
            try { window.dispatchEvent(new Event("verity-thesis-changed")) } catch { /* */ }
        } else {
            const all = loadAll(); delete all[tk]; saveAll(all)
        }
        setThesis(null); setEditing(true); setStance("watch"); setNote(""); setIsPublic(false)
        if (token) setTimeout(() => loadFeed(tk), 600)  // 내 공개 관점이 있었다면 피드에서 제거 반영
    }

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, padding: 16, boxSizing: "border-box", color: C.ink }
    const stanceColor = (id: string) => { const s = STANCES.find((x) => x.id === id); return s ? (C as any)[s.key] : C.faint }
    const stanceLabel = (id: string) => { const s = STANCES.find((x) => x.id === id); return s ? s.label : "관망" }

    if (!tk && !onCanvas) {
        return <div style={{ ...wrap, textAlign: "center", color: C.faint, fontSize: 12.5, fontWeight: 600, padding: "22px 16px" }}>종목을 선택하면 내 관점을 기록할 수 있어요.</div>
    }

    const card: CSSProperties = { background: C.card, borderRadius: 14, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const title = (
        <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 10 }}>
            <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>내 관점</span>
            <span style={{ fontSize: 11, fontWeight: 600, color: C.faint }}>· 본인 결정 저널</span>
        </div>
    )

    // ─── 커뮤니티: 좋아요 토글(낙관 갱신) / 신고 / 피드 섹션 ───
    const toggleLike = (it: any) => {
        if (onCanvas) return
        if (!token) { setFeedMsg("좋아요는 로그인 후 가능해요"); return }
        const liked = !it.liked
        setFeed((f) => f.map((x) => (x.id === it.id ? { ...x, liked, likes: Math.max(0, x.likes + (liked ? 1 : -1)) } : x)))
        fetch(base + "/api/thesis_feed", { method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify({ action: liked ? "like" : "unlike", thesis_id: it.id }) }).catch(() => {})
    }
    const reportItem = (it: any) => {
        if (onCanvas || reported[it.id]) return
        if (!token) { setFeedMsg("신고는 로그인 후 가능해요"); return }
        setReported((m) => ({ ...m, [it.id]: true }))
        fetch(base + "/api/thesis_feed", { method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify({ action: "report", thesis_id: it.id, reason: "" }) }).catch(() => {})
    }
    const feedSection = (
        <div style={{ ...card, marginTop: 10 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>공개 관점</span>
                <span style={{ fontSize: 11, fontWeight: 600, color: C.faint }}>· 이 종목을 기록한 사람들{feed.length ? ` ${feed.length}` : ""}</span>
            </div>
            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginTop: 4, marginBottom: 6 }}>
                이용자 개인 의견이며 AlphaNest 의 분석·판단·추천이 아니에요.
            </div>
            {feedMsg && <div style={{ fontSize: 11.5, fontWeight: 700, color: C.up, marginBottom: 6 }}>{feedMsg}</div>}
            {feed.length === 0 ? (
                <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, padding: "6px 0 2px" }}>아직 공개된 관점이 없어요. 위에서 내 관점을 공개해 보세요.</div>
            ) : (
                feed.map((it) => (
                    <div key={it.id} style={{ padding: "10px 0 8px", borderTop: `1px solid ${C.line}` }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            {it.avatar ? (
                                <img src={it.avatar} alt="" width={26} height={26} style={{ width: 26, height: 26, borderRadius: 9, objectFit: "cover", flexShrink: 0 }} />
                            ) : (
                                <div style={{ width: 26, height: 26, borderRadius: 9, background: C.chipBg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                                    <User size={14} color={C.faint} weight="fill" />
                                </div>
                            )}
                            <span style={{ fontSize: 12.5, fontWeight: 800, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{it.nickname}{it.mine ? " (나)" : ""}</span>
                            <span style={{ fontSize: 11, fontWeight: 800, color: stanceColor(it.stance), flexShrink: 0 }}>{stanceLabel(it.stance)}</span>
                            <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginLeft: "auto", flexShrink: 0 }}>{(it.created_at || "").slice(0, 10)}</span>
                        </div>
                        {it.note && <div style={{ fontSize: 12.5, color: C.ink, fontWeight: 500, lineHeight: 1.5, marginTop: 6, whiteSpace: "pre-wrap" }}>{it.note}</div>}
                        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 7 }}>
                            <button onClick={() => toggleLike(it)}
                                style={{ display: "inline-flex", alignItems: "center", gap: 4, border: "none", background: "transparent", cursor: "pointer", padding: 0, fontFamily: FONT, fontSize: 11.5, fontWeight: 700, color: it.liked ? C.up : C.faint }}>
                                <Heart size={14} weight={it.liked ? "fill" : "regular"} color={it.liked ? C.up : C.faint} />
                                {it.likes > 0 ? it.likes : "좋아요"}
                            </button>
                            {!it.mine && (
                                <button onClick={() => reportItem(it)}
                                    style={{ border: "none", background: "transparent", cursor: reported[it.id] ? "default" : "pointer", padding: 0, fontFamily: FONT, fontSize: 10.5, fontWeight: 600, color: C.faint }}>
                                    {reported[it.id] ? "신고 접수됨" : "신고"}
                                </button>
                            )}
                        </div>
                    </div>
                ))
            )}
        </div>
    )

    // 기록 표시 (재방문) ─ "그 후 변화"
    if (thesis && !editing) {
        const since = daysSince(thesis.date)
        const ep = thesis.entryPrice
        const diffPct = (ep != null && curPrice != null && ep > 0) ? ((curPrice - ep) / ep) * 100 : null
        const dCol = diffPct == null ? C.faint : diffPct > 0 ? C.up : diffPct < 0 ? C.down : C.faint
        return (
            <div style={wrap}>
                <div style={card}>
                    {title}
                    <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 12.5, fontWeight: 800, color: "#fff", background: stanceColor(thesis.stance), borderRadius: 999, padding: "4px 12px" }}>{stanceLabel(thesis.stance)}</span>
                        {thesis.isPublic && <span style={{ fontSize: 10.5, fontWeight: 800, color: C.vt, background: C.vtS, borderRadius: 999, padding: "3px 10px" }}>공개</span>}
                        <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{thesis.date} · {since === 0 ? "오늘" : since + "일 전"} 기록</span>
                    </div>
                    {thesis.note && <div style={{ fontSize: 13, color: C.ink, fontWeight: 500, lineHeight: 1.5, marginTop: 9, background: C.bg, borderRadius: 10, padding: "10px 12px", whiteSpace: "pre-wrap" }}>{thesis.note}</div>}

                    {/* 그 후 변화 */}
                    <div style={{ marginTop: 11, paddingTop: 11, borderTop: `1px solid ${C.line}` }}>
                        <div style={{ fontSize: 11, fontWeight: 800, color: C.faint, marginBottom: 5 }}>기록 후 변화</div>
                        {ep != null ? (
                            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                                <span style={{ fontSize: 12.5, color: C.sub, fontWeight: 600 }}>기록 시 {won(ep)} → 종가</span>
                                <span style={{ fontSize: 14.5, fontWeight: 800, color: C.ink }}>{curPrice != null ? won(curPrice) : "—"}</span>
                                {diffPct != null && isFinite(diffPct) && (
                                    <span style={{ fontSize: 13, fontWeight: 800, color: dCol }}>{(diffPct > 0 ? "+" : "") + diffPct.toFixed(1)}%</span>
                                )}
                            </div>
                        ) : (
                            <div style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>기록 시 가격 미저장 (다음 기록부터 추적)</div>
                        )}
                        <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>내 thesis 가 맞았는지 *스스로* 복기하는 용도 · 사실(공시·수급·내부자) 변화는 아래 리포트에서</div>
                    </div>

                    <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                        <button onClick={() => setEditing(true)} style={{ flex: 1, cursor: "pointer", fontFamily: FONT, padding: "9px 0", borderRadius: 10, fontSize: 12.5, fontWeight: 700, background: C.chipBg, color: C.ink, border: `1px solid ${C.line}` }}>수정</button>
                        <button onClick={remove} style={{ flexShrink: 0, cursor: "pointer", fontFamily: FONT, padding: "9px 16px", borderRadius: 10, fontSize: 12.5, fontWeight: 700, background: "transparent", color: C.faint, border: `1px solid ${C.line}` }}>삭제</button>
                    </div>
                </div>
                {feedSection}
            </div>
        )
    }

    // 입력 폼 (신규/수정)
    return (
        <div style={wrap}>
            <div style={card}>
                {title}
                <div style={{ fontSize: 11.5, fontWeight: 700, color: C.sub, marginBottom: 6 }}>내 관점</div>
                <div style={{ display: "flex", gap: 7, marginBottom: 12 }}>
                    {STANCES.map((st) => {
                        const on = stance === st.id
                        const col = (C as any)[st.key]
                        // 선택 시 외곽선 없음 + 연한 파스텔 칩(강세=연빨강 / 약세=연파랑 / 관망=중립)
                        const softBg = st.key === "up" ? C.upS : st.key === "down" ? C.downS : C.chipBg
                        return (
                            <button key={st.id} onClick={() => setStance(st.id)}
                                style={{ flex: 1, border: "none", cursor: "pointer", fontFamily: FONT, padding: "10px 0", borderRadius: 10, fontSize: 13, fontWeight: on ? 800 : 700, background: on ? softBg : C.bg, color: on ? col : C.sub }}>
                                {st.label}
                            </button>
                        )
                    })}
                </div>
                <div style={{ fontSize: 11.5, fontWeight: 700, color: C.sub, marginBottom: 6 }}>왜 이렇게 보는지 (근거·재검토 시점)</div>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3}
                    placeholder="예: PER·PBR 업종 이하 + 내부자 순매수. 부채 낮음. 다음 실적발표 후 재검토."
                    style={{ width: "100%", boxSizing: "border-box", border: `1px solid ${C.line}`, borderRadius: 10, padding: "10px 12px", fontSize: 12.5, fontFamily: FONT, fontWeight: 500, background: C.bg, color: C.ink, outline: "none", resize: "vertical", lineHeight: 1.5 }} />
                {/* 커뮤니티 공개 토글 — 기본 비공개. 익명(로컬 저장)은 서버행이 없어 공개 불가. */}
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 12, paddingTop: 11, borderTop: `1px solid ${C.line}` }}>
                    <button onClick={() => { if (onCanvas) return; if (!token) { setPubMsg("로그인하면 공개할 수 있어요"); return } setIsPublic(!isPublic); setPubMsg("") }}
                        aria-label="커뮤니티에 공개" role="switch" aria-checked={isPublic}
                        style={{ width: 42, height: 24, borderRadius: 999, border: "none", cursor: token ? "pointer" : "default", background: isPublic ? C.vt : C.line, position: "relative", flexShrink: 0, padding: 0, transition: "background 150ms", opacity: token ? 1 : 0.55 }}>
                        <span style={{ position: "absolute", top: 3, left: isPublic ? 21 : 3, width: 18, height: 18, borderRadius: "50%", background: "#fff", transition: "left 150ms", boxShadow: "0 1px 3px rgba(0,0,0,0.2)" }} />
                    </button>
                    <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: C.ink }}>커뮤니티에 공개</div>
                        <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.4 }}>{token ? "공개하면 별명으로 이 종목의 공개 관점에 보여요 · 개인 의견 표시" : "로그인 후 공개할 수 있어요"}</div>
                    </div>
                </div>
                {pubMsg && <div style={{ fontSize: 11.5, fontWeight: 700, color: C.up, marginTop: 6 }}>{pubMsg}</div>}
                <div style={{ display: "flex", gap: 8, marginTop: 11, alignItems: "center" }}>
                    <button onClick={save} style={{ flex: 1, border: "none", cursor: "pointer", fontFamily: FONT, padding: "11px 0", borderRadius: 11, fontSize: 13, fontWeight: 800, background: C.vt, color: "#fff" }}>기록</button>
                    {thesis && <button onClick={() => { setEditing(false); setStance(thesis.stance); setNote(thesis.note || ""); setIsPublic(!!thesis.isPublic) }} style={{ flexShrink: 0, cursor: "pointer", fontFamily: FONT, padding: "11px 16px", borderRadius: 11, fontSize: 13, fontWeight: 700, background: "transparent", color: C.faint, border: `1px solid ${C.line}` }}>취소</button>}
                </div>
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>{token ? "내 계정에 저장 — 어느 기기서나 동일" : "이 기기에 저장 · 로그인하면 계정에 저장돼 어디서나 보여요"} · 기록 시점 가격 동결로 재방문 시 변화 표시</div>
            </div>
            {feedSection}
        </div>
    )
}

addPropertyControls(PublicThesisNote, {
    ticker: { type: ControlType.String, title: "Ticker (빈칸=URL ?q=)", defaultValue: "" },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 관심종목 — VERITY 공개 터미널 (AlphaNest) 우측 상시 사이드바.
 *
 * 저장 = localStorage["verity_watchlist"] = [{ticker,name,market}] (로그인 불요·마찰 0).
 * 검색 universe = universe_search.json (통합 KR+US ~8.4천, nav/리포트/결정 검색과 동일 단일 소스. 2026-06-27 통일 — 괴리 제거).
 * 🚨 시세 재배포 컴플라이언스(2026-07-03 Phase 1.5): /api/stock 실시간가 폴링 제거 — KIS/yfinance 시세를 회원(제3자)에게 재배포 불가.
 *   가격 열 삭제. 시세·차트 = 행 클릭 → 종목 리포트(네이버 link-out + TV 위젯)에서.
 * 저장 시 "verity-watchlist-changed" 이벤트 → PublicDisclosureFeed 가 즉시 관심종목 핀 갱신(같은 페이지).
 * 행 탭 → 종목 리포트(stockPath?q=ticker). RULE 7 — 가격·등락(외부 사실)만, 점수·추천 0.
 * 🚨 내 관점 통합(2026-06-21) — localStorage `verity_thesis_v1`(PublicThesisNote) 읽어 각 종목에 관점 배지(강세/관망/약세).
 *   = "내가 어떻게 본 종목들" 한눈. *사용자 본인* 저널이지 VERITY 추천 아님. focus/이벤트 시 재읽기(다른 페이지서 기록 반영).
 * 🚨 둥지(보유) 연동(2026-07-18) — 로그인 시 /api/holdings 읽어 보유종목을 관심종목에 합쳐 '보유' 배지 표시.
 *   verity_holdings_change/verity_auth_change 시 재조회. 보유-only 종목은 × 없음(해제는 둥지에서).
 * 컴팩트 사이징(목업 정합). 반응형 — ResizeObserver. 캔버스 = SEED 데모.
 * 테마: Framer 네이티브 추종 — body[data-framer-theme] 읽어 dark 전환(캔버스는 dark prop 정적 프리뷰).
 * 🚨 배경 transparent + 하단 면책 푸터 제거(2026-06-26, PM) — 면책은 사이트 하단 단일 통합. 패딩 0(임베드 이중여백 해소).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968",
    faint: "#8b95a1", line: "#e5e8eb", up: "#f04452", down: "#3182f6",
    vg: "#0ca678", vgS: "#e7faf0", vt: "#6c5ce7", vtBox: "#f0edff", chip: "#f2f4f6",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1",
    faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff",
    vg: "#7fffa0", vgS: "#11281d", vt: "#a99bff", vtBox: "#1c1830", chip: "#1f262e",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const LS_KEY = "verity_watchlist"
const THESIS_KEY = "verity_thesis_v1"
const STANCE_META: Record<string, { label: string; key: "up" | "down" | "faint" }> = {
    bull: { label: "강세", key: "up" }, watch: { label: "관망", key: "faint" }, bear: { label: "약세", key: "down" },
}

interface Props {
    stockUrl: string
    apiBase: string
    stockPath: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
const DEFAULT_API = "https://project-yw131.vercel.app"

const SEED = [
    { ticker: "247540", name: "에코프로비엠", market: "kr" },
    { ticker: "034020", name: "두산에너빌리티", market: "kr" },
    { ticker: "033160", name: "엠케이전자", market: "kr" },
    { ticker: "042700", name: "한미반도체", market: "kr" },
    { ticker: "000660", name: "SK하이닉스", market: "kr" },
]

// 🚨 익명 로컬 스크래치 세션 초기화 (2026-07-13) — 공개 페이지는 로그인 없이 접근 → 공유기기 익명 누출 차단.
//   새 브라우저 세션(새 방문)마다 1회. 로그인 회원 = 서버(/api/watchgroups) 저장이라 로컬=스크래치 →
//   유효 세션 있으면 skip(회원 보존), 없으면 clear(익명 초기화). verity_theme(기기설정)은 유지.
function sessionResetScratch() {
    if (typeof window === "undefined") return
    try {
        if (sessionStorage.getItem("verity_session_init")) return
        sessionStorage.setItem("verity_session_init", "1")
        let member = false
        try {
            const s = JSON.parse(localStorage.getItem("verity_supabase_session") || "null")
            member = !!(s && s.access_token && (!s.expires_at || Date.now() / 1000 < s.expires_at))
        } catch (e) {}
        if (member) return
        for (const k of ["verity_watchlist", "verity_last_ticker", "verity_recent_tickers", "verity_thesis_v1", "verity_thesis_migrated_v1"]) localStorage.removeItem(k)
    } catch (e) {}
}
function loadWatch(): any[] {
    // 디폴트(SEED) 없음 — 라이브는 빈 상태로 시작. 추가분만 localStorage 저장, 새 세션 = sessionResetScratch 로 리셋(익명).
    if (typeof window === "undefined") return []
    try {
        const r = localStorage.getItem(LS_KEY)
        if (!r) return []
        const a = JSON.parse(r)
        if (!Array.isArray(a)) return []
        // 구버전 SEED 목업이 그대로 저장돼 있으면(사용자 미변경) 1회 자동 정리 — 목업 잔존 제거
        const seedSet = SEED.map((x) => String(x.ticker)).sort().join(",")
        const curSet = a.map((x: any) => String(x && x.ticker)).sort().join(",")
        if (a.length === SEED.length && curSet === seedSet) {
            try { localStorage.removeItem(LS_KEY) } catch (e) {}
            return []
        }
        return a
    } catch {
        return []
    }
}
function saveWatch(list: any[]) {
    if (typeof window === "undefined") return
    try {
        localStorage.setItem(LS_KEY, JSON.stringify(list))
        window.dispatchEvent(new Event("verity-watchlist-changed"))
    } catch {}
}
function loadTheses(): Record<string, any> {
    if (typeof window === "undefined") return {}
    try { return JSON.parse(localStorage.getItem(THESIS_KEY) || "{}") || {} } catch { return {} }
}
const SESSION_KEY = "verity_supabase_session"
function loadToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const s = JSON.parse(localStorage.getItem(SESSION_KEY) || "null")
        if (!s || typeof s.access_token !== "string") return ""
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return ""
        return s.access_token
    } catch { return "" }
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicWatchlist(props: Props) {
    const { stockUrl, apiBase, stockPath, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [watch, setWatch] = useState<any[]>([])
    const [held, setHeld] = useState<any[]>([])
    const [universe, setUniverse] = useState<any[]>([])
    const [theses, setTheses] = useState<Record<string, any>>({})
    const [adding, setAdding] = useState(false)
    const [query, setQuery] = useState("")
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 dark prop 정적) */
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
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    useEffect(() => { if (!onCanvas) { sessionResetScratch(); setWatch(loadWatch()) } }, [onCanvas])

    /* 보유종목(둥지, /api/holdings) — 로그인 시 관심종목에 합쳐 '보유' 표시. 로그인/보유변경 시 재조회. */
    useEffect(() => {
        if (onCanvas) { setHeld([]); return }
        const load = () => {
            const token = loadToken()
            if (!token) { setHeld([]); return }
            fetch(base + "/api/holdings", { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
                .then((r) => (r.ok ? r.json() : null))
                .then((d) => { const a = Array.isArray(d) ? d : (d && Array.isArray(d.holdings) ? d.holdings : []); setHeld(Array.isArray(a) ? a : []) })
                .catch(() => {})
        }
        load()
        if (typeof window === "undefined") return
        window.addEventListener("verity_auth_change", load)
        window.addEventListener("verity_holdings_change", load)
        window.addEventListener("storage", load)
        return () => { window.removeEventListener("verity_auth_change", load); window.removeEventListener("verity_holdings_change", load); window.removeEventListener("storage", load) }
    }, [onCanvas, base])

    /* 내 관점(thesis) 로드 — mount + focus/이벤트 재읽기(다른 페이지서 기록 반영) */
    useEffect(() => {
        if (onCanvas) { setTheses({ "247540": { stance: "bull", date: "2026-06-18" }, "000660": { stance: "watch", date: "2026-06-20" }, "034020": { stance: "bear", date: "2026-06-19" } }); return }
        const read = () => setTheses(loadTheses())
        read()
        if (typeof window === "undefined") return
        window.addEventListener("focus", read)
        window.addEventListener("verity-thesis-changed", read as any)
        return () => { window.removeEventListener("focus", read); window.removeEventListener("verity-thesis-changed", read as any) }
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas || !stockUrl) return
        let alive = true
        fetch(stockUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const arr = d && (Array.isArray(d) ? d : d.stocks)
                if (alive && Array.isArray(arr)) setUniverse(arr)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [stockUrl, onCanvas])

    const narrow = w > 0 && w < 320
    const pad = 0

    const matches = useMemo(() => {
        const q = query.trim().toLowerCase()
        if (!q) return []
        const rk = (x: any) => {
            const t = String(x.ticker || "").toLowerCase(), n = String(x.name || "").toLowerCase(), k = String(x.name_ko || "").toLowerCase()
            return t === q ? 0 : (n === q || k === q) ? 1 : t.indexOf(q) === 0 ? 2 : (n.indexOf(q) === 0 || (k && k.indexOf(q) === 0)) ? 3 : 4
        }
        const have = new Set(watch.map((x) => String(x.ticker)))
        return universe
            .filter((x) => !have.has(String(x.ticker)) && (String(x.name || "").toLowerCase().includes(q) || String(x.ticker || "").includes(q)))
            .sort((a: any, b: any) => rk(a) - rk(b)).slice(0, 12)
    }, [query, universe, watch])

    const addStock = useCallback((m: any) => {
        setWatch((prev) => {
            if (prev.some((x) => String(x.ticker) === String(m.ticker))) return prev
            const next = [...prev, { ticker: m.ticker, name: m.name, market: (m.market || "kr").toLowerCase().includes("us") ? "us" : "kr" }]
            saveWatch(next)
            return next
        })
        setQuery("")
        setAdding(false)
    }, [])

    const removeStock = useCallback((ticker: string) => {
        setWatch((prev) => {
            const next = prev.filter((x) => String(x.ticker) !== String(ticker))
            saveWatch(next)
            return next
        })
    }, [])

    const goStock = (h: any) => {
        if (typeof window === "undefined") return
        const p = (stockPath || "/stock").replace(/\/+$/, "")
        window.location.href = p + "?q=" + encodeURIComponent(String(h.ticker || "").trim())
    }

    /* 관심(로컬) ∪ 보유(둥지) 합집합 — 보유는 '보유' 배지, 관심(로컬)만 × 해제 가능 */
    const rows = useMemo(() => {
        const byTk = new Map<string, any>()
        for (const h of watch) {
            const tk = String(h.ticker || "").trim()
            if (!tk) continue
            byTk.set(tk, { ...h, ticker: tk, _watched: true, _held: false })
        }
        for (const h of held) {
            const tk = String(h.ticker || "").trim()
            if (!tk) continue
            const cur = byTk.get(tk)
            if (cur) cur._held = true
            else byTk.set(tk, { ticker: tk, name: h.name || tk, market: h.market || "", _watched: false, _held: true })
        }
        const arr = Array.from(byTk.values())
        arr.sort((a, b) => (b._held ? 1 : 0) - (a._held ? 1 : 0))
        return arr
    }, [watch, held])


    const wrap: CSSProperties = {
        width: "100%", height: "100%", maxHeight: "100%", overflowY: "auto", overflowX: "hidden",
        background: "transparent", fontFamily: FONT, padding: pad, boxSizing: "border-box", color: C.ink,
    }
    const inputStyle: CSSProperties = {
        width: "100%", border: `1px solid ${C.line}`, borderRadius: 9, padding: "8px 11px",
        fontSize: 13, fontFamily: FONT, background: C.card, color: C.ink, outline: "none", boxSizing: "border-box",
    }

    return (
        <div ref={rootRef} style={wrap}>
            {/* 관심종목 카드 */}
            <div style={{ background: C.card, borderRadius: 14, padding: "14px 14px 11px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.4px" }}>관심종목</div>
                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 3 }}>검색 → 추가 · 보유종목 자동 표시 · 내 관점 배지</div>

                <div style={{ marginTop: 9 }}>
                    {rows.length === 0 && (
                        <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, padding: "13px 0", textAlign: "center", lineHeight: 1.6 }}>
                            아직 관심종목이 없어요.<br />아래에서 추가해 보세요.
                        </div>
                    )}
                    {rows.map((h, i) => {
                        const th = theses[String(h.ticker)]
                        const sm = th ? (STANCE_META[th.stance] || STANCE_META.watch) : null
                        const smCol = sm ? (C as any)[sm.key] : C.faint
                        return (
                            <div key={h.ticker} onClick={() => goStock(h)} role="link" tabIndex={0}
                                style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}`, cursor: "pointer" }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "-0.2px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{h.name || h.ticker}</div>
                                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 1, display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
                                        <span>{h.ticker}</span>
                                        {h._held && <span style={{ fontSize: 9.5, fontWeight: 800, color: C.vg, background: C.vgS, borderRadius: 5, padding: "1px 6px", letterSpacing: "-0.1px" }}>보유</span>}
                                        {sm && <span style={{ fontSize: 9.5, fontWeight: 800, color: smCol, background: C.chip, borderRadius: 5, padding: "1px 6px", letterSpacing: "-0.1px" }}>내 관점 {sm.label}</span>}
                                    </div>
                                </div>
                                {/* 실시간가·등락 열 제거(2026-07-03 컴플라이언스) — 시세는 행 클릭 → 리포트의 네이버 link-out/TV 위젯 */}
                                <span style={{ flexShrink: 0, fontSize: 13, color: C.faint, fontWeight: 700 }}>›</span>
                                {h._watched ? (
                                    <button onClick={(e) => { e.stopPropagation(); removeStock(h.ticker) }} title="관심종목 삭제"
                                        style={{ border: "none", background: "transparent", cursor: "pointer", color: C.faint, fontSize: 14, fontWeight: 700, padding: "0 1px", flexShrink: 0 }}>×</button>
                                ) : (
                                    <span style={{ flexShrink: 0, width: 9 }} />
                                )}
                            </div>
                        )
                    })}
                </div>

                {/* 검색 추가 */}
                {adding ? (
                    <div style={{ marginTop: 9 }}>
                        <input style={inputStyle} autoFocus placeholder="종목 검색 (이름·코드)" value={query} onChange={(e) => setQuery(e.target.value)} />
                        {matches.length > 0 && (
                            <div style={{ marginTop: 5, background: C.card, borderRadius: 9, border: `1px solid ${C.line}`, padding: 4, maxHeight: 220, overflowY: "auto" }}>
                                {matches.map((m) => (
                                    <div key={m.ticker} onClick={() => addStock(m)}
                                        style={{ display: "flex", alignItems: "baseline", gap: 7, padding: "7px 8px", borderRadius: 7, cursor: "pointer" }}>
                                        <span style={{ fontSize: 12.5, fontWeight: 700 }}>{m.name}</span>
                                        <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{m.ticker} · {m.market}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                        <button onClick={() => { setAdding(false); setQuery("") }}
                            style={{ width: "100%", marginTop: 7, border: "none", cursor: "pointer", padding: "9px 0", borderRadius: 10, fontSize: 12.5, fontWeight: 700, fontFamily: FONT, background: C.chip, color: C.sub }}>
                            닫기
                        </button>
                    </div>
                ) : (
                    <button onClick={() => setAdding(true)}
                        style={{ width: "100%", marginTop: 10, border: "none", cursor: "pointer", padding: "11px 0", borderRadius: 10, fontSize: 12.5, fontWeight: 800, fontFamily: FONT, background: C.chip, color: C.sub }}>
                        + 관심종목 추가
                    </button>
                )}
            </div>
        </div>
    )
}

addPropertyControls(PublicWatchlist, {
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: DEFAULT_URL },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

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

function loadWatch(): any[] {
    if (typeof window === "undefined") return SEED
    try {
        const r = localStorage.getItem(LS_KEY)
        if (!r) return SEED
        const a = JSON.parse(r)
        return Array.isArray(a) ? a : SEED
    } catch {
        return SEED
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
export default function PublicWatchlist(props: Props) {
    const { stockUrl, apiBase, stockPath, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [watch, setWatch] = useState<any[]>(SEED)
    const [universe, setUniverse] = useState<any[]>([])
    const [theses, setTheses] = useState<Record<string, any>>({})
    const [adding, setAdding] = useState(false)
    const [query, setQuery] = useState("")
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))

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

    useEffect(() => { if (!onCanvas) setWatch(loadWatch()) }, [onCanvas])

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
        fetch(stockUrl)
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

    /* 스와이프 삭제 (2026-07-10 PM — 유튜브뮤직식): 행을 왼쪽으로 드래그 → 빨간 삭제 영역 노출,
       임계(72px) 넘겨 놓으면 슬라이드아웃 후 삭제, 못 미치면 스프링백. Pointer Events = 마우스·터치 공통.
       touchAction pan-y = 세로 스크롤은 살리고 가로 드래그만 캡처. 드래그(>6px) 후엔 행 클릭(리포트 이동) 억제. */
    const SW_TH = 72
    const [sw, setSw] = useState<{ t: string; dx: number; anim: boolean }>({ t: "", dx: 0, anim: false })
    const swRef = useRef<{ startX: number; active: string; moved: boolean; width: number }>({ startX: 0, active: "", moved: false, width: 320 })
    const swDown = (e: any, t: string) => {
        if (e.pointerType === "mouse" && e.button !== 0) return
        swRef.current = { startX: e.clientX, active: t, moved: false, width: (e.currentTarget && e.currentTarget.offsetWidth) || 320 }
        try { e.currentTarget.setPointerCapture(e.pointerId) } catch (err) {}
    }
    const swMove = (e: any, t: string) => {
        const r = swRef.current
        if (r.active !== t) return
        const dx = Math.min(0, e.clientX - r.startX)
        if (dx < -6) r.moved = true
        if (r.moved) setSw({ t, dx: Math.max(dx, -r.width), anim: false })
    }
    const swEnd = (e: any, t: string) => {
        const r = swRef.current
        if (r.active !== t) return
        r.active = ""
        const dx = Math.min(0, e.clientX - r.startX)
        if (dx <= -SW_TH) {
            setSw({ t, dx: -Math.round(r.width * 1.1), anim: true })   // 슬라이드아웃
            setTimeout(() => { removeStock(t); setSw({ t: "", dx: 0, anim: false }) }, 190)
        } else if (r.moved) {
            setSw({ t, dx: 0, anim: true })   // 스프링백
            setTimeout(() => setSw((p) => (p.t === t ? { t: "", dx: 0, anim: false } : p)), 220)
        }
    }
    const swCancel = (t: string) => {
        if (swRef.current.active !== t) return
        swRef.current.active = ""
        setSw({ t: "", dx: 0, anim: false })
    }

    const goStock = (h: any) => {
        if (typeof window === "undefined") return
        const p = (stockPath || "/stock").replace(/\/+$/, "")
        window.location.href = p + "?q=" + encodeURIComponent(String(h.ticker || "").trim())
    }


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
                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 3 }}>검색 → 추가 · 내 관점 기록한 종목엔 배지</div>

                <div style={{ marginTop: 9 }}>
                    {watch.length === 0 && (
                        <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, padding: "13px 0", textAlign: "center", lineHeight: 1.6 }}>
                            아직 관심종목이 없어요.<br />아래에서 추가해 보세요.
                        </div>
                    )}
                    {watch.map((h, i) => {
                        const th = theses[String(h.ticker)]
                        const sm = th ? (STANCE_META[th.stance] || STANCE_META.watch) : null
                        const smCol = sm ? (C as any)[sm.key] : C.faint
                        const tk = String(h.ticker)
                        const on = sw.t === tk
                        const dx = on ? sw.dx : 0
                        const armed = on && dx <= -SW_TH   // 임계 도달 = 삭제 확정 시각 피드백
                        return (
                            <div key={h.ticker} style={{ position: "relative", overflow: "hidden", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                {/* 뒤 레이어 — 스와이프로 드러나는 삭제 영역 (유튜브뮤직식) */}
                                {on && dx < 0 && (
                                    <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 14, background: armed ? "#f04452" : C.chip, transition: "background 140ms ease" }}>
                                        <span style={{ fontSize: 12, fontWeight: 800, color: armed ? "#ffffff" : C.faint, display: "inline-flex", alignItems: "center", gap: 5 }}>
                                            <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke={armed ? "#fff" : C.faint} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                                            </svg>
                                            삭제
                                        </span>
                                    </div>
                                )}
                                {/* 앞 레이어 — 원래 행. 드래그 시 translateX, card 배경으로 뒤 레이어 가림 */}
                                <div role="link" tabIndex={0}
                                    onClick={() => { if (swRef.current.moved) { swRef.current.moved = false; return } goStock(h) }}
                                    onPointerDown={(e) => swDown(e, tk)}
                                    onPointerMove={(e) => swMove(e, tk)}
                                    onPointerUp={(e) => swEnd(e, tk)}
                                    onPointerCancel={() => swCancel(tk)}
                                    style={{
                                        display: "flex", alignItems: "center", gap: 8, padding: "9px 0", cursor: "pointer",
                                        background: C.card, position: "relative",
                                        transform: `translateX(${dx}px)`,
                                        transition: on && sw.anim ? "transform 190ms ease" : "none",
                                        touchAction: "pan-y",
                                    }}>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "-0.2px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{h.name || h.ticker}</div>
                                        <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 1, display: "flex", alignItems: "center", gap: 5 }}>
                                            <span>{h.ticker}</span>
                                            {sm && <span style={{ fontSize: 9.5, fontWeight: 800, color: smCol, background: C.chip, borderRadius: 5, padding: "1px 6px", letterSpacing: "-0.1px" }}>내 관점 {sm.label}</span>}
                                        </div>
                                    </div>
                                    {/* 실시간가·등락 열 제거(2026-07-03 컴플라이언스) — 시세는 행 클릭 → 리포트의 네이버 link-out/TV 위젯 */}
                                    <span style={{ flexShrink: 0, fontSize: 13, color: C.faint, fontWeight: 700 }}>›</span>
                                    <button onClick={(e) => { e.stopPropagation(); removeStock(h.ticker) }} title="삭제"
                                        style={{ border: "none", background: "transparent", cursor: "pointer", color: C.faint, fontSize: 14, fontWeight: 700, padding: "0 1px", flexShrink: 0 }}>×</button>
                                </div>
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

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * AlphaNest '내 종목' 뷰 — 로그인 사용자의 관심종목 리스트(기기·세션 넘어 유지).
 *
 * 데이터 = 기존 백엔드 /api/watchgroups (JWT 인증, 본인 필터·IDOR 안전). DB 변경 0.
 * 세션 = verity_supabase_session(localStorage, AlphaNestAuth 가 기록). 미로그인=둘러보기 안내만.
 * 별표 추가/삭제(PublicStockReport) → window 'verity_watch_change' → 이 뷰 자동 새로고침.
 * 행 클릭 → reportPath?q=ticker. 삭제(×) → remove_item.
 * 🚨 시세 재배포 컴플라이언스(2026-07-03 Phase 1.5): /api/stock 실시간가 조회 제거 — KIS 시세 회원(제3자) 재배포 불가.
 *   가격 열 삭제. 시세 = 행 클릭 → 종목 리포트(네이버 link-out + TV 위젯)에서. 다크모드 = body[data-framer-theme] 추종.
 */

const SESSION_KEY = "verity_supabase_session"
const AUTH_EVENT = "verity_auth_change"
const WATCH_EVENT = "verity_watch_change"

// ── Brandfetch 로고 (토스 핫링킹 제거 2026-07-10) — logo_map(빌드타임 확정) + US 티커 규칙 + 이니셜 폴백 ──
const BF_CID = "1idalDez9T7KlggM8qX"  // 공개 임베드 client id (Logo Link 전용)
const BF_MAP_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
let __bfMap: Record<string, string> | null = null
let __bfColors: Record<string, string> = {}
let __bfShapes: Record<string, number> = {}
let __bfStyle: any = { padS: 8, padW: 15, wideRatio: 2.2 }  // 발행 데이터(style)로 조절 — 코드 수정 불요
let __bfP: Promise<Record<string, string>> | null = null
function fetchBfMap(): Promise<Record<string, string>> {
    if (__bfMap) return Promise.resolve(__bfMap)
    if (!__bfP) __bfP = fetch(BF_MAP_URL).then((r) => (r.ok ? r.json() : null)).then((d) => { __bfMap = (d && d.logos) || {}; __bfColors = (d && d.colors) || {}; __bfShapes = (d && d.shapes) || {}; __bfStyle = (d && d.style) || __bfStyle; return __bfMap as Record<string, string> }).catch(() => ({} as Record<string, string>))
    return __bfP
}
function useBfLogoMap(): Record<string, string> | null {
    const [m, setM] = useState<Record<string, string> | null>(__bfMap)
    useEffect(() => { let al = true; fetchBfMap().then((mm) => { if (al) setM(mm) }); return () => { al = false } }, [])
    return m
}
function bfLogoPad(ticker: any): string {
    // 모양 적응 패딩 — 심볼(정사각)은 크게, 워드마크(가로 김)는 여백 확보 (토스식 가시성)
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const r = __bfShapes[tk] || __bfShapes[tk.replace(/\./g, "-")] || 1
    if (r === 0) return "0%"  // 큐레이션 풀블리드 아이콘(자체 배경 포함) = 타일 꽉 채움
    return (r > (__bfStyle.wideRatio || 2.2) ? (__bfStyle.padW || 15) : (__bfStyle.padS || 8)) + "%"
}
function bfInitialBg(ticker: any): string {
    // 이니셜 타일 — 티커 해시 투톤 그라데이션 (미보유 4.6K 도 디자인 자산화, 종목별 고정색)
    let h = 0; const s = String(ticker || "?")
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360
    return "linear-gradient(135deg, hsl(" + h + ",62%,55%), hsl(" + ((h + 42) % 360) + ",68%,42%))"
}
function bfLogoBg(ticker: any): string {
    // 아이덴티티 색 틴트 타일 (토스식 참조 — 색은 로고 대표색/공식 브랜드색, 자산 복사 아님)
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    // 토스식 넉아웃 (기본): 브랜드색 솔리드 배경 + 로고 흰 실루엣(bfLogoFilter). 조건 미충족 = 솔리드 파스텔.
    // style.mode 노브: "knockout"(기본) | "pastel". mixPct = 파스텔 혼합비(기본 30).
    const p2 = (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    if (c && p2 && p2.indexOf("http") !== 0 && (__bfStyle.mode || "pastel") === "knockout") return c  // 솔리드 브랜드색
    if (!c) return "#ffffff"
    const mix = Number(__bfStyle.mixPct || 30)
    try { if (typeof CSS !== "undefined" && CSS.supports && CSS.supports("color", "color-mix(in srgb, red 50%, white)")) return `color-mix(in srgb, ${c} ${mix}%, #ffffff)` } catch (e2) {}
    return c + (__bfStyle.tintA || "4D")
}
function bfLogoFilter(ticker: any): string {
    // 넉아웃 조건과 동일할 때만 흰 실루엣 (Brandfetch 투명 로고 한정 — 파비콘류는 불투명이라 제외)
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    const p2 = (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    return (c && p2 && p2.indexOf("http") !== 0 && (__bfStyle.mode || "pastel") === "knockout") ? "brightness(0) invert(1)" : "none"
}
function bfLogoSrc(ticker: any, lm: Record<string, string> | null, size: number): string {
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    if (!tk) return ""
    // 로고 = 토스 종목 CDN (PM 결정: 완전 공개[런칭] 전까지 토스 사용, 2026-07-12). 404/차단 시 onError → 이니셜 폴백.
    return "https://static.toss.im/png-icons/securities/icn-sec-fill-" + tk + ".png"
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", up: "#f04452", down: "#3182f6", vg: "#0ca678", vgS: "#e7faf0", vt: "#6c5ce7", vtS: "#f0edff" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff", vg: "#7fffa0", vgS: "#11281d", vt: "#a99bff", vtS: "#241f3a" }
const DEFAULT_API = "https://project-yw131.vercel.app"
const DEFAULT_REPORT = "/stock"

interface Props {
    apiBase: string
    reportPath: string
    dark: boolean
}

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

function Logo({ ticker, name, C }: { ticker: string; name: string; C: any }) {
    const [err, setErr] = useState(false)
    const lm = useBfLogoMap()
    const bfSrc = bfLogoSrc(ticker, lm, 30)
    const ch = (String(name || "?").trim().charAt(0)) || "?"
    if (err || !ticker || !bfSrc) {
        return <span style={{ width: 30, height: 30, flexShrink: 0, borderRadius: 10, background: bfInitialBg(ticker), color: "#ffffff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 800 }}>{ch}</span>
    }
    return <img src={bfSrc} alt="" loading="lazy" decoding="async" width={30} height={30} onError={() => setErr(true)} style={{ width: 30, height: 30, flexShrink: 0, borderRadius: 10, objectFit: "cover", display: "block", background: "transparent"}} />
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

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function AlphaNestWatchlist(props: Props) {
    const { apiBase, reportPath, dark } = props
    const api = (apiBase || DEFAULT_API).replace(/\/+$/, "")
    const report = reportPath || DEFAULT_REPORT
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))
    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT
    useEffect(() => {
        if (onCanvas) return
        const readTheme = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        readTheme()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(readTheme)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const [token, setToken] = useState("")
    const [items, setItems] = useState<any[]>([])
    const [loading, setLoading] = useState(false)

    // 세션 토큰 추적(로그인/로그아웃 반영)
    useEffect(() => {
        if (onCanvas) return
        const sync = () => setToken(loadToken())
        sync()
        window.addEventListener(AUTH_EVENT, sync)
        window.addEventListener("storage", sync)
        return () => { window.removeEventListener(AUTH_EVENT, sync); window.removeEventListener("storage", sync) }
    }, [onCanvas])

    const fetchWatch = useCallback(() => {
        if (onCanvas || !token) { setItems([]); return }
        setLoading(true)
        fetch(`${api}/api/watchgroups`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((groups) => {
                if (!Array.isArray(groups)) { setItems([]); return }
                const flat: any[] = []
                const seen = new Set<string>()
                for (const g of groups) {
                    for (const it of (g.items || [])) {
                        const tk = String(it.ticker || "").trim()
                        if (!tk || seen.has(tk)) continue
                        seen.add(tk)
                        flat.push({ item_id: it.id, ticker: tk, name: it.name || tk, market: it.market || "" })
                    }
                }
                setItems(flat)
            })
            .catch(() => setItems([]))
            .finally(() => setLoading(false))
    }, [api, token, onCanvas])

    useEffect(() => { fetchWatch() }, [fetchWatch])

    // 별표 토글 시 새로고침
    useEffect(() => {
        if (onCanvas) return
        const onWatch = () => fetchWatch()
        window.addEventListener(WATCH_EVENT, onWatch)
        return () => window.removeEventListener(WATCH_EVENT, onWatch)
    }, [fetchWatch, onCanvas])

    // 실시간가 조회 = 2026-07-03 컴플라이언스로 제거 — 시세는 행 클릭 → 리포트에서

    const removeItem = (item_id: any) => {
        if (!token || !item_id) return
        setItems((prev) => prev.filter((x) => x.item_id !== item_id))
        fetch(`${api}/api/watchgroups`, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
            body: JSON.stringify({ action: "remove_item", item_id }),
        }).then(() => { if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(WATCH_EVENT)) }).catch(() => fetchWatch())
    }

    const wrap: CSSProperties = { width: "100%", height: "100%", background: C.bg, fontFamily: FONT, boxSizing: "border-box", color: C.ink, padding: 16, overflowY: "auto" }
    const title = <div style={{ fontSize: 15, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px", marginBottom: 10 }}>내 종목</div>

    if (onCanvas) {
        return <div style={wrap}>{title}<div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>로그인 시 관심종목이 여기 남아요 (Preview/Publish 동작)</div></div>
    }

    if (!token) {
        return (
            <div style={wrap}>
                {title}
                <div style={{ background: C.card, borderRadius: 14, padding: "18px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                    <div style={{ fontSize: 13.5, fontWeight: 700, color: C.ink, lineHeight: 1.5 }}>로그인하면 관심종목이 여기 남아요</div>
                    <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>종목 리포트에서 ☆를 눌러 담으면 기기·세션이 바뀌어도 유지됩니다.</div>
                </div>
            </div>
        )
    }

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10 }}>
                <span style={{ fontSize: 15, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px" }}>내 종목</span>
                {items.length > 0 && <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{items.length}종목</span>}
            </div>
            {items.length === 0 && loading ? (
                <>
                    <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                    <div style={{ background: C.card, borderRadius: 14, padding: "4px 14px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        {[0, 1, 2, 3, 4, 5].map((i) => {
                            const base = themeDark ? "#222a33" : "#e9edf1"
                            const hi = themeDark ? "#2d3742" : "#f3f5f7"
                            const shimmer: CSSProperties = {
                                background: base,
                                backgroundImage: `linear-gradient(90deg, ${base} 25%, ${hi} 37%, ${base} 63%)`,
                                backgroundSize: "800px 100%",
                                animation: "vsrShimmer 1.4s ease-in-out infinite",
                                borderRadius: 6,
                            }
                            return (
                                <div key={i} style={{ display: "flex", alignItems: "center", gap: 11, padding: "11px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                    <div style={{ ...shimmer, width: 30, height: 30, flexShrink: 0, borderRadius: 10 }} />
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ ...shimmer, width: "55%", height: 13, marginBottom: 6 }} />
                                        <div style={{ ...shimmer, width: "32%", height: 10 }} />
                                    </div>
                                    <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
                                        <div style={{ ...shimmer, width: 56, height: 13 }} />
                                        <div style={{ ...shimmer, width: 38, height: 11 }} />
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                </>
            ) : items.length === 0 ? (
                <div style={{ background: C.card, borderRadius: 14, padding: "18px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                    <div style={{ fontSize: 13.5, fontWeight: 700, color: C.ink }}>아직 관심종목이 없어요</div>
                    <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>종목 리포트에서 ☆를 눌러 담아보세요.</div>
                </div>
            ) : (
                <div style={{ background: C.card, borderRadius: 14, padding: "4px 14px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                    {items.map((it, i) => {
                        return (
                            <div key={it.ticker} style={{ display: "flex", alignItems: "center", gap: 11, padding: "11px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                <a href={`${report}?q=${encodeURIComponent(it.ticker)}`} style={{ display: "flex", alignItems: "center", gap: 11, flex: 1, minWidth: 0, textDecoration: "none", color: "inherit", cursor: "pointer" }}>
                                    <Logo ticker={it.ticker} name={it.name} C={C} />
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ fontSize: 13.5, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{it.name}</div>
                                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{it.ticker}{it.market ? " · " + it.market : ""}</div>
                                    </div>
                                    <span style={{ flexShrink: 0, fontSize: 14, color: C.faint, fontWeight: 700 }}>›</span>
                                </a>
                                <button onClick={() => removeItem(it.item_id)} title="관심종목 해제"
                                    style={{ flexShrink: 0, border: "none", background: "transparent", cursor: "pointer", color: C.faint, fontSize: 16, lineHeight: 1, padding: "4px 6px", fontWeight: 700 }}>×</button>
                            </div>
                        )
                    })}
                </div>
            )}
            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>가격·등락률 = 실시간 사실 · 점수 held(2027)</div>
        </div>
    )
}

addPropertyControls(AlphaNestWatchlist, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    reportPath: { type: ControlType.String, title: "Report Path", defaultValue: DEFAULT_REPORT },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
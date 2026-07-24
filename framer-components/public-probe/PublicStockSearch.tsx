import { addPropertyControls, ControlType, RenderTarget } from "framer"
import {
    useEffect,
    useLayoutEffect,
    useMemo,
    useRef,
    useState,
    type CSSProperties,
} from "react"
import { createPortal } from "react-dom"

/**
 * 종목 검색창 (독립) — VERITY 공개 터미널. Framer 네이티브 nav 안에 끼워 쓰는 검색 전용.
 * Enter → 입력 텍스트를 유니버스에서 *종목코드*로 정규화 → /stock?q=<코드> 이동.
 * 🚨 포커스(빈 검색어) = 최근 본 종목(localStorage) + "지금 거래 활발"(네이버 거래대금 상위 link-out).
 * 검색 universe = universe_search.json (통합 KR+US ~8.4천). 드롭다운 = document.body 포털(nav overflow 클리핑 탈출).
 *
 * 🚨 2026-07-24 테마 = 자체 내장 CSS 변수(--an-pss-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
 *   <style>{AN_PALETTE} = body{} 스코프라 포털 드롭다운(body 자식)도 함께 상속. SVG 화살표는 이미 style stroke(var). 되돌리지 말 것.
 */

const LIGHT = {
    ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", vg: "#0ca678", vt: "#6c5ce7", vtS: "#f0edff",
    field: "#f2f4f6", card: "#ffffff", bg: "#f2f4f6", line: "#f0f1f3", up: "#f04452", down: "#3182f6",
}
const DARK = {
    ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", vg: "#7fffa0", vt: "#a99bff", vtS: "#241f3a",
    field: "#0f1318", card: "#171c23", bg: "#0f1318", line: "#222730", up: "#f04452", down: "#5b9bff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEF_STOCK = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
// 🚨 시세 재배포 컴플라이언스(2026-07-02): trending_kr(KRX raw) 자체 발행 중단. "지금 거래 활발" = 네이버 link-out.
const NAVER_QUANT = "https://finance.naver.com/sise/sise_quant.naver"
const M_NAVER_QUANT = "https://m.stock.naver.com/sise/trade"
const LAST_TK_KEY = "verity_last_ticker"
const RECENTS_KEY = "verity_recent_tickers"
const RECENTS_CAP = 8

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-pss-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "pss"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

// 🚨 익명 로컬 스크래치 세션 초기화 (2026-07-13) — 공개 페이지 로그인 없이 접근 → 공유기기 익명 누출 차단.
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
        for (const k of ["verity_watchlist", "verity_last_ticker", "verity_recent_tickers", "verity_thesis_v1", "verity_thesis_migrated_v1"])
            localStorage.removeItem(k)
    } catch (e) {}
}

// ── Brandfetch 로고 — logo_map(빌드타임 확정) + US 티커 규칙 + 이니셜 폴백 ──
const BF_CID = "1idalDez9T7KlggM8qX"
const BF_MAP_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
let __bfMap: Record<string, string> | null = null
let __bfColors: Record<string, string> = {}
let __bfShapes: Record<string, number> = {}
let __bfStyle: any = { padS: 8, padW: 15, wideRatio: 2.2 }
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
function bfInitialBg(ticker: any): string {
    let h = 0
    const s = String(ticker || "?")
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360
    return "linear-gradient(135deg, hsl(" + h + ",62%,55%), hsl(" + ((h + 42) % 360) + ",68%,42%))"
}
function bfLogoSrc(ticker: any, lm: Record<string, string> | null, size: number): string {
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    if (!tk) return ""
    // 로고 = 토스 종목 CDN (PM 결정: 완전 공개[런칭] 전까지 토스 사용, 2026-07-12). 404/차단 시 onError → 이니셜 폴백.
    return "https://static.toss.im/png-icons/securities/icn-sec-fill-" + tk + ".png"
}
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
function flagFromTicker(ticker: any): string {
    return /^\d{6}$/.test(String(ticker || "")) ? "kr" : "us"
}
function Logo(props: { ticker: any; name: any; C: any; size?: number }) {
    const { ticker, name, C } = props
    const size = props.size || 22
    const [err, setErr] = useState(false)
    const lm = useBfLogoMap()
    const bfSrc = bfLogoSrc(ticker, lm, size)
    const ch = String(name || "?").trim().charAt(0) || "?"
    const code = flagFromTicker(ticker)
    const fsize = Math.round(size * 0.46)
    return (
        <span style={{ position: "relative", width: size, height: size, flexShrink: 0, display: "inline-block" }}>
            {!err && bfSrc ? (
                <img
                    src={bfSrc}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    width={size}
                    height={size}
                    onError={() => setErr(true)}
                    style={{ width: size, height: size, borderRadius: Math.round(size * 0.32), objectFit: "cover", display: "block", background: "transparent" }}
                />
            ) : (
                <span style={{ width: size, height: size, borderRadius: Math.round(size * 0.32), background: bfInitialBg(ticker), color: "#ffffff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * 0.42), fontWeight: 800 }}>
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
                style={{ position: "absolute", right: -3, bottom: -3, width: fsize, height: fsize, borderRadius: "50%", border: `1.5px solid ${C.card}`, background: C.card, display: "block", boxShadow: "0 1px 2px rgba(0,0,0,0.18)" }}
            />
        </span>
    )
}

function isMobileWidth(): boolean {
    if (typeof window === "undefined") return false
    return window.innerWidth > 0 && window.innerWidth < 560
}
function readRecents(): any[] {
    if (typeof window === "undefined") return []
    try {
        const a = JSON.parse(window.localStorage.getItem(RECENTS_KEY) || "[]")
        return Array.isArray(a) ? a.filter((x) => x && x.t) : []
    } catch {
        return []
    }
}

interface Props {
    placeholder: string
    stockPath: string
    stockUrl: string
    usStockUrl: string
    dark: boolean
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicStockSearch(props: Props) {
    const { placeholder, stockPath, stockUrl, usStockUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    /* 익명 로컬 스크래치 세션 초기화 — 검색 recents 읽기 전에 1회(공유기기 누출 차단, 회원은 skip) */
    useEffect(() => {
        if (!onCanvas) sessionResetScratch()
    }, [onCanvas])

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [q, setQ] = useState("")
    const [universe, setUniverse] = useState<any[]>([])
    const [focused, setFocused] = useState(false)
    const [recents, setRecents] = useState<any[]>([])
    // 드롭다운 앵커 — nav 박스 overflow 클리핑 탈출용 fixed 좌표(입력창 rect 기준). null=미측정.
    const [anchor, setAnchor] = useState<{ top: number; left: number; width: number } | null>(null)

    // 폭 측정 = 첫 페인트 전 동기(useLayoutEffect).
    useLayoutEffect(() => {
        const el = rootRef.current
        if (!el) return
        setW(el.getBoundingClientRect().width)
        if (typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries) setW(e.contentRect.width)
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    /* 유니버스 로드 — 통합 universe_search.json(KR+US 단일). */
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const urls = [stockUrl].filter(Boolean)
        Promise.all(
            urls.map((u) =>
                fetch(u)
                    .then((r) => (r.ok ? r.json() : null))
                    .catch(() => null)
            )
        ).then((docs) => {
            if (!alive) return
            const merged: any[] = []
            for (const d of docs) {
                const a = d && (Array.isArray(d) ? d : d.stocks)
                if (Array.isArray(a)) merged.push(...a)
            }
            if (merged.length) setUniverse(merged)
        })
        return () => {
            alive = false
        }
    }, [stockUrl, usStockUrl, onCanvas])

    /* 입력 → 종목코드. 코드/이름 정확 → 부분일치 → (실패 시) raw 텍스트. */
    const resolveTicker = (text: string): string => {
        const s = text.trim()
        if (!s || !universe.length) return s
        const lower = s.toLowerCase()
        let hit = universe.find(
            (x) => String(x.ticker).toLowerCase() === lower || String(x.name || "").toLowerCase() === lower || String((x as any).name_ko || "") === s
        )
        if (!hit)
            hit = universe.find(
                (x) => String(x.ticker).toLowerCase().includes(lower) || String(x.name || "").toLowerCase().includes(lower) || String((x as any).name_ko || "").includes(s)
            )
        return hit ? String(hit.ticker) : s
    }

    /* 라이브 연관검색어 — 코드·영문명·한글명 부분일치, 상위 12. */
    const matches = useMemo(() => {
        const s = q.trim().toLowerCase()
        if (!s || !universe.length) return []
        const rk = (x: any) => {
            const t = String(x.ticker || "").toLowerCase(),
                n = String(x.name || "").toLowerCase(),
                k = String(x.name_ko || "").toLowerCase()
            return t === s ? 0 : n === s || k === s ? 1 : t.indexOf(s) === 0 ? 2 : n.indexOf(s) === 0 || (k && k.indexOf(s) === 0) ? 3 : 4
        }
        return universe
            .filter((x) => String(x.ticker).toLowerCase().includes(s) || String(x.name || "").toLowerCase().includes(s) || String((x as any).name_ko || "").includes(q.trim()))
            .sort((a: any, b: any) => rk(a) - rk(b))
            .slice(0, 12)
    }, [q, universe])

    const pick = (tk: string, nm?: string) => {
        if (!tk || typeof window === "undefined") return
        const name = nm || (universe.find((x) => String(x.ticker) === String(tk)) || {}).name || tk
        try {
            window.localStorage.setItem(LAST_TK_KEY, tk)
            const cur = readRecents().filter((x) => String(x.t) !== String(tk))
            cur.unshift({ t: tk, n: name })
            window.localStorage.setItem(RECENTS_KEY, JSON.stringify(cur.slice(0, RECENTS_CAP)))
        } catch {
            /* private/quota */
        }
        const p = (stockPath || "/stock").replace(/\/+$/, "")
        window.location.href = p + "?q=" + encodeURIComponent(tk)
    }

    const go = () => {
        const raw = q.trim()
        if (!raw) return
        pick(resolveTicker(raw))
    }

    /* 드롭다운 fixed 좌표 측정 — 입력창 rect 기준(nav overflow:hidden 클리핑 탈출). */
    const measure = () => {
        const el = rootRef.current
        if (!el || typeof window === "undefined") return
        const r = el.getBoundingClientRect()
        setAnchor({ top: r.bottom + 6, left: r.left, width: r.width })
    }

    const onFocus = () => {
        setRecents(readRecents())
        setFocused(true)
        measure()
    }

    /* 포커스 동안 scroll/resize 시 좌표 재측정 (fixed 패널이 입력창 따라가게). */
    useEffect(() => {
        if (!focused || onCanvas) return
        const m = () => measure()
        window.addEventListener("scroll", m, true)
        window.addEventListener("resize", m)
        return () => {
            window.removeEventListener("scroll", m, true)
            window.removeEventListener("resize", m)
        }
    }, [focused, onCanvas])

    const narrow = w > 0 && w < 200
    const showQuery = !!q.trim()
    const showSuggest = !onCanvas && focused && !!anchor && !showQuery
    const showMatches = !onCanvas && focused && !!anchor && showQuery && matches.length > 0

    const wrap: CSSProperties = {
        width: "100%", height: "100%", boxSizing: "border-box", display: "flex", alignItems: "center", gap: 7,
        background: C.field, borderRadius: 999, padding: narrow ? "8px 12px" : "9px 14px", fontFamily: FONT,
    }
    // fixed + 입력창 rect 좌표 → nav 박스 overflow 에 안 잘림. zIndex 큰 값(nav 위).
    const panel: CSSProperties = {
        position: "fixed", top: anchor ? anchor.top : 0, left: anchor ? anchor.left : 0, width: anchor ? anchor.width : "auto",
        zIndex: 2147483000, background: C.card, borderRadius: 12, boxShadow: "0 10px 30px rgba(0,0,0,0.16)",
        padding: 6, maxHeight: 360, overflowY: "auto", minWidth: 240,
    }
    const secLabel = (t: string, hint?: string) => (
        <div style={{ display: "flex", alignItems: "baseline", gap: 6, padding: "8px 10px 4px" }}>
            <span style={{ fontSize: 11, fontWeight: 800, color: C.faint }}>{t}</span>
            {hint && <span style={{ fontSize: 10, fontWeight: 500, color: C.faint, opacity: 0.8 }}>{hint}</span>}
        </div>
    )
    const itemRow = (key: any, tk: any, nm: any, right: any) => (
        <div
            key={key}
            onMouseDown={() => pick(String(tk), String(nm))}
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 9, cursor: "pointer" }}
        >
            <Logo ticker={tk} name={nm} C={C} size={28} />
            <span style={{ fontSize: 13.5, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{nm}</span>
            <span style={{ marginLeft: "auto", flexShrink: 0 }}>{right}</span>
        </div>
    )

    return (
        <div ref={rootRef} style={{ position: "relative", width: "100%", height: "100%", fontFamily: FONT }}>
            <style>{AN_PALETTE}</style>
            <div style={wrap}>
                <span style={{ width: 14, height: 14, borderRadius: "50%", border: `2px solid ${C.faint}`, flexShrink: 0, display: "inline-block", position: "relative" }}>
                    <span style={{ position: "absolute", width: 2, height: 6, background: C.faint, right: -3, bottom: -3, transform: "rotate(-45deg)" }} />
                </span>
                <input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter") {
                            setFocused(false)
                            go()
                        }
                    }}
                    onFocus={onFocus}
                    onBlur={() => setTimeout(() => setFocused(false), 160)}
                    placeholder={placeholder || "종목 검색"}
                    style={{ border: "none", outline: "none", background: "transparent", color: C.ink, fontFamily: FONT, fontSize: narrow ? 13 : 14, fontWeight: 600, width: "100%", minWidth: 0 }}
                />
            </div>

            {/* 드롭다운 = document.body 포털(nav overflow 클리핑 탈출). AN_PALETTE 는 body{} 스코프라 포털도 상속. */}
            {typeof document !== "undefined" &&
                showMatches &&
                createPortal(
                    <div style={panel}>
                        {matches.map((m) =>
                            itemRow(
                                m.ticker,
                                m.ticker,
                                m.name,
                                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>
                                    {m.name_ko ? m.name_ko + " · " : ""}
                                    {m.ticker}
                                    {m.market ? " · " + m.market : ""}
                                </span>
                            )
                        )}
                    </div>,
                    document.body
                )}

            {typeof document !== "undefined" &&
                showSuggest &&
                createPortal(
                    <div style={panel}>
                        {recents.length > 0 && (
                            <>
                                {secLabel("최근 본 종목")}
                                {recents.slice(0, 6).map((r) =>
                                    itemRow("r:" + r.t, r.t, r.n, <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{r.t}</span>)
                                )}
                            </>
                        )}
                        {secLabel("지금 거래 활발", "거래대금 상위 · 네이버")}
                        {/* 화살표 = SVG (텍스트 "↗" 는 iOS 이모지 렌더 어색). 좁은 화면 줄바꿈 방지 */}
                        <div
                            onMouseDown={() => {
                                if (typeof window !== "undefined") window.open(isMobileWidth() ? M_NAVER_QUANT : NAVER_QUANT, "_blank", "noopener")
                            }}
                            style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 10px", borderRadius: 9, cursor: "pointer" }}
                        >
                            <span style={{ width: 22, height: 22, borderRadius: 7, background: C.vtS, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                                <svg width={11} height={11} viewBox="0 0 12 12" fill="none" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ stroke: C.vt }}>
                                    <line x1="2.5" y1="9.5" x2="9" y2="3" />
                                    <polyline points="4.2,2.8 9.2,2.8 9.2,7.8" />
                                </svg>
                            </span>
                            <span style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                실시간 거래대금 상위
                            </span>
                            <span style={{ flexShrink: 0, display: "inline-flex", alignItems: "center", gap: 3, fontSize: 11.5, fontWeight: 700, color: C.faint, whiteSpace: "nowrap" }}>
                                네이버 금융
                                <svg width={9} height={9} viewBox="0 0 12 12" fill="none" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ stroke: C.faint }}>
                                    <line x1="2.5" y1="9.5" x2="9" y2="3" />
                                    <polyline points="4.2,2.8 9.2,2.8 9.2,7.8" />
                                </svg>
                            </span>
                        </div>
                    </div>,
                    document.body
                )}
        </div>
    )
}

addPropertyControls(PublicStockSearch, {
    placeholder: { type: ControlType.String, title: "Placeholder", defaultValue: "종목 검색 (이름·코드)" },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: DEF_STOCK },
    usStockUrl: { type: ControlType.String, title: "US Stock URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json" },
    dark: { type: ControlType.Boolean, title: "Dark(미사용)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"
import { createPortal } from "react-dom"

/**
 * 종목 검색창 (독립) — VERITY 공개 터미널. Framer 네이티브 nav 안에 끼워 쓰는 검색 전용.
 * Enter → 입력 텍스트를 유니버스에서 *종목코드*로 정규화 → /stock?q=<코드> 이동.
 *   (정규화 이유: 결정 페이지 컴포넌트는 ticker 정확매칭만 함. 종목명 ?q 는 빈 화면이 됨.)
 *   코드/이름 매칭 실패 시에만 raw 텍스트 fallback(리포트가 자체 이름매칭 시도).
 * 🚨 포커스(빈 검색어) = 최근 본 종목(localStorage) + "지금 거래 활발"(네이버 거래대금 상위 link-out).
 *   시세 재배포 컴플라이언스(2026-07-02): trending_kr(KRX raw) 자체 발행 중단 → 네이버가 서빙(재배포 아님).
 *   RULE 7 / held-2027 / 법률: "인기·추천"이 아니라 사실(거래대금). "이런 종목 어때요" 류 추천 어조 금지.
 * 종목 공유 = ?q + localStorage `verity_last_ticker`/`verity_recent_tickers` 기록. nav 자체는 Framer 네이티브.
 * 검색 universe = universe_search.json (통합 KR+US ~8.4천, 2026-06-27 검색 4종 단일 소스 통일 — 괴리 제거). US 별도 dual-load 폐기(통합 파일에 포함).
 * 테마: Framer 네이티브 추종 — body[data-framer-theme] 읽어 dark 전환(캔버스는 dark prop 정적 프리뷰).
 */

const LIGHT = { ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", vg: "#0ca678", vt: "#6c5ce7", vtS: "#f0edff", field: "#f2f4f6", card: "#ffffff", bg: "#f2f4f6", line: "#f0f1f3", up: "#f04452", down: "#3182f6" }
const DARK = { ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", vg: "#7fffa0", vt: "#a99bff", vtS: "#241f3a", field: "#0f1318", card: "#171c23", bg: "#0f1318", line: "#222730", up: "#f04452", down: "#5b9bff" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEF_STOCK = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
// 🚨 시세 재배포 컴플라이언스(2026-07-02): trending_kr(KRX 거래대금·등락·종가 raw) 자체 발행 중단.
//   "지금 거래 활발" = 네이버 거래대금 상위 페이지로 link-out(네이버가 서빙 = 재배포 아님, 실시간·무료·합법).
const NAVER_QUANT = "https://finance.naver.com/sise/sise_quant.naver"
const M_NAVER_QUANT = "https://m.stock.naver.com/sise/trade"
const LAST_TK_KEY = "verity_last_ticker"
const RECENTS_KEY = "verity_recent_tickers"
const RECENTS_CAP = 8
/* 로고 — 토스 종목 CDN(404/차단 시 이니셜 폴백) + circle-flags 원형 국기. ticker 형식으로 국장/미장 판별. */

// ── Brandfetch 로고 (토스 핫링킹 제거 2026-07-10) — logo_map(빌드타임 확정) + US 티커 규칙 + 이니셜 폴백 ──
const BF_CID = "1idalDez9T7KlggM8qX"  // 공개 임베드 client id (Logo Link 전용)
const BF_MAP_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
let __bfMap: Record<string, string> | null = null
let __bfColors: Record<string, string> = {}
let __bfP: Promise<Record<string, string>> | null = null
function fetchBfMap(): Promise<Record<string, string>> {
    if (__bfMap) return Promise.resolve(__bfMap)
    if (!__bfP) __bfP = fetch(BF_MAP_URL).then((r) => (r.ok ? r.json() : null)).then((d) => { __bfMap = (d && d.logos) || {}; __bfColors = (d && d.colors) || {}; return __bfMap as Record<string, string> }).catch(() => ({} as Record<string, string>))
    return __bfP
}
function useBfLogoMap(): Record<string, string> | null {
    const [m, setM] = useState<Record<string, string> | null>(__bfMap)
    useEffect(() => { let al = true; fetchBfMap().then((mm) => { if (al) setM(mm) }); return () => { al = false } }, [])
    return m
}
function bfLogoBg(ticker: any): string {
    // 아이덴티티 색 틴트 타일 (토스식 참조 — 색은 로고 대표색/공식 브랜드색, 자산 복사 아님)
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    return c ? c + "26" : "#ffffff"  // 15% 알파 틴트, 무채색/미보유 = 흰 타일
}
function bfLogoSrc(ticker: any, lm: Record<string, string> | null, size: number): string {
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const p = (lm && (lm[tk] || lm[tk.replace(/\./g, "-")])) || ""  // 맵 전용 — 미검증 경로 = B 플레이스홀더 위험(2026-07-10)
    return p ? "https://cdn.brandfetch.io/" + p + "?c=" + BF_CID + "&w=" + size * 2 + "&h=" + size * 2 : ""
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
    const ch = (String(name || "?").trim().charAt(0)) || "?"
    const code = flagFromTicker(ticker)
    const fsize = Math.round(size * 0.46)
    return (
        <span style={{ position: "relative", width: size, height: size, flexShrink: 0, display: "inline-block" }}>
            {!err && bfSrc ? (
                <img src={bfSrc} alt="" width={size} height={size}
                    onError={() => setErr(true)}
                    style={{ width: size, height: size, borderRadius: 7, objectFit: "contain", padding: "13%", boxSizing: "border-box", display: "block", background: bfLogoBg(ticker)}} />
            ) : (
                <span style={{ width: size, height: size, borderRadius: 7, background: C.vtS, color: C.vt, display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * 0.42), fontWeight: 800 }}>{ch}</span>
            )}
            <img src={FLAG_BASE + code + ".svg"} alt="" width={fsize} height={fsize}
                style={{ position: "absolute", right: -3, bottom: -3, width: fsize, height: fsize, borderRadius: "50%", border: `1.5px solid ${C.card}`, background: C.card, display: "block", boxShadow: "0 1px 2px rgba(0,0,0,0.18)" }} />
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
    } catch { return [] }
}

interface Props {
    placeholder: string
    stockPath: string
    stockUrl: string
    usStockUrl: string
    dark: boolean
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
export default function PublicStockSearch(props: Props) {
    const { placeholder, stockPath, stockUrl, usStockUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 dark prop 정적) */
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))
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

    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [q, setQ] = useState("")
    const [universe, setUniverse] = useState<any[]>([])
    const [focused, setFocused] = useState(false)
    const [recents, setRecents] = useState<any[]>([])
    // 드롭다운 앵커 — nav 박스 overflow 클리핑 탈출용 fixed 좌표(입력창 rect 기준). null=미측정.
    const [anchor, setAnchor] = useState<{ top: number; left: number; width: number } | null>(null)

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    /* 유니버스 로드 — 통합 universe_search.json(KR+US 단일). usStockUrl=레거시(통합 파일에 US 포함, 미사용). */
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const urls = [stockUrl].filter(Boolean)
        Promise.all(urls.map((u) => fetch(u, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null)))
            .then((docs) => {
                if (!alive) return
                const merged: any[] = []
                for (const d of docs) { const a = d && (Array.isArray(d) ? d : d.stocks); if (Array.isArray(a)) merged.push(...a) }
                if (merged.length) setUniverse(merged)
            })
        return () => { alive = false }
    }, [stockUrl, usStockUrl, onCanvas])

    /* 입력 → 종목코드. 코드/이름 정확 → 부분일치 → (실패 시) raw 텍스트. */
    const resolveTicker = (text: string): string => {
        const s = text.trim()
        if (!s || !universe.length) return s
        const lower = s.toLowerCase()
        let hit = universe.find((x) => String(x.ticker).toLowerCase() === lower || String(x.name || "").toLowerCase() === lower || String((x as any).name_ko || "") === s)
        if (!hit) hit = universe.find((x) => String(x.ticker).toLowerCase().includes(lower) || String(x.name || "").toLowerCase().includes(lower) || String((x as any).name_ko || "").includes(s))
        return hit ? String(hit.ticker) : s
    }

    /* 라이브 연관검색어 — 코드·영문명·한글명 부분일치, 상위 12. */
    const matches = useMemo(() => {
        const s = q.trim().toLowerCase()
        if (!s || !universe.length) return []
        const rk = (x: any) => {
            const t = String(x.ticker || "").toLowerCase(), n = String(x.name || "").toLowerCase(), k = String(x.name_ko || "").toLowerCase()
            return t === s ? 0 : (n === s || k === s) ? 1 : t.indexOf(s) === 0 ? 2 : (n.indexOf(s) === 0 || (k && k.indexOf(s) === 0)) ? 3 : 4
        }
        return universe.filter((x) =>
            String(x.ticker).toLowerCase().includes(s) ||
            String(x.name || "").toLowerCase().includes(s) ||
            String((x as any).name_ko || "").includes(q.trim())
        ).sort((a: any, b: any) => rk(a) - rk(b)).slice(0, 12)
    }, [q, universe])

    const pick = (tk: string, nm?: string) => {
        if (!tk || typeof window === "undefined") return
        const name = nm || (universe.find((x) => String(x.ticker) === String(tk)) || {}).name || tk
        try {
            window.localStorage.setItem(LAST_TK_KEY, tk)
            const cur = readRecents().filter((x) => String(x.t) !== String(tk))
            cur.unshift({ t: tk, n: name })
            window.localStorage.setItem(RECENTS_KEY, JSON.stringify(cur.slice(0, RECENTS_CAP)))
        } catch { /* private/quota */ }
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

    const onFocus = () => { setRecents(readRecents()); setFocused(true); measure() }

    /* 포커스 동안 scroll/resize 시 좌표 재측정 (fixed 패널이 입력창 따라가게). */
    useEffect(() => {
        if (!focused || onCanvas) return
        const m = () => measure()
        window.addEventListener("scroll", m, true)
        window.addEventListener("resize", m)
        return () => { window.removeEventListener("scroll", m, true); window.removeEventListener("resize", m) }
    }, [focused, onCanvas])

    const narrow = w > 0 && w < 200
    const showQuery = !!q.trim()
    // anchor 필요 (fixed 좌표). onFocus 가 measure() 동기 호출 → 첫 포커스에도 anchor 존재.
    const showSuggest = !onCanvas && focused && !!anchor && !showQuery
    const showMatches = !onCanvas && focused && !!anchor && showQuery && matches.length > 0

    const wrap: CSSProperties = {
        width: "100%", height: "100%", boxSizing: "border-box",
        display: "flex", alignItems: "center", gap: 7,
        background: C.field, borderRadius: 999,
        padding: narrow ? "8px 12px" : "9px 14px",
        fontFamily: FONT,
    }
    // fixed + 입력창 rect 좌표 → nav 박스 overflow 에 안 잘림. zIndex 큰 값(nav 위).
    const panel: CSSProperties = {
        position: "fixed",
        top: anchor ? anchor.top : 0,
        left: anchor ? anchor.left : 0,
        width: anchor ? anchor.width : "auto",
        zIndex: 2147483000,
        background: C.card, borderRadius: 12, boxShadow: "0 10px 30px rgba(0,0,0,0.16)",
        padding: 6, maxHeight: 360, overflowY: "auto", minWidth: 240,
    }
    const secLabel = (t: string, hint?: string) => (
        <div style={{ display: "flex", alignItems: "baseline", gap: 6, padding: "8px 10px 4px" }}>
            <span style={{ fontSize: 11, fontWeight: 800, color: C.faint }}>{t}</span>
            {hint && <span style={{ fontSize: 10, fontWeight: 500, color: C.faint, opacity: 0.8 }}>{hint}</span>}
        </div>
    )
    const itemRow = (key: any, tk: any, nm: any, right: any) => (
        <div key={key} onMouseDown={() => pick(String(tk), String(nm))}
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 9, cursor: "pointer" }}>
            <Logo ticker={tk} name={nm} C={C} size={22} />
            <span style={{ fontSize: 13.5, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{nm}</span>
            <span style={{ marginLeft: "auto", flexShrink: 0 }}>{right}</span>
        </div>
    )

    return (
        <div ref={rootRef} style={{ position: "relative", width: "100%", height: "100%", fontFamily: FONT }}>
            <div style={wrap}>
                <span style={{ width: 14, height: 14, borderRadius: "50%", border: `2px solid ${C.faint}`, flexShrink: 0, display: "inline-block", position: "relative" }}>
                    <span style={{ position: "absolute", width: 2, height: 6, background: C.faint, right: -3, bottom: -3, transform: "rotate(-45deg)" }} />
                </span>
                <input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { setFocused(false); go() } }}
                    onFocus={onFocus}
                    onBlur={() => setTimeout(() => setFocused(false), 160)}
                    placeholder={placeholder || "종목 검색"}
                    style={{
                        border: "none", outline: "none", background: "transparent", color: C.ink,
                        fontFamily: FONT, fontSize: narrow ? 13 : 14, fontWeight: 600, width: "100%", minWidth: 0,
                    }}
                />
            </div>

            {/* 드롭다운 = document.body 포털. nav 박스의 overflow:hidden / transform 클리핑을
                탈출(fixed 좌표는 anchor=입력창 rect). 리포트 페이지는 풀페이지라 안 잘렸고,
                nav 검색은 잘려 안 보이던 문제 해소. onMouseDown pick 은 포털에서도 React 트리로 동작. */}
            {typeof document !== "undefined" && showMatches && createPortal(
                <div style={panel}>
                    {matches.map((m) => itemRow(m.ticker, m.ticker, m.name,
                        <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{m.name_ko ? m.name_ko + " · " : ""}{m.ticker}{m.market ? " · " + m.market : ""}</span>))}
                </div>, document.body)}

            {typeof document !== "undefined" && showSuggest && createPortal(
                <div style={panel}>
                    {recents.length > 0 && (
                        <>
                            {secLabel("최근 본 종목")}
                            {recents.slice(0, 6).map((r) => itemRow("r:" + r.t, r.t, r.n,
                                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{r.t}</span>))}
                        </>
                    )}
                    {secLabel("지금 거래 활발", "거래대금 상위 · 네이버")}
                    {/* 화살표 = SVG (텍스트 "↗" 는 iOS 에서 이모지 렌더 → 어색. PC 텍스트 글리프와 동일 룩 통일) · 좁은 화면 줄바꿈 방지 */}
                    <div onMouseDown={() => { if (typeof window !== "undefined") window.open(isMobileWidth() ? M_NAVER_QUANT : NAVER_QUANT, "_blank", "noopener") }}
                        style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 10px", borderRadius: 9, cursor: "pointer" }}>
                        <span style={{ width: 22, height: 22, borderRadius: 7, background: C.vtS, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                            <svg width={11} height={11} viewBox="0 0 12 12" fill="none" stroke={C.vt} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                <line x1="2.5" y1="9.5" x2="9" y2="3" />
                                <polyline points="4.2,2.8 9.2,2.8 9.2,7.8" />
                            </svg>
                        </span>
                        <span style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>실시간 거래대금 상위</span>
                        <span style={{ flexShrink: 0, display: "inline-flex", alignItems: "center", gap: 3, fontSize: 11.5, fontWeight: 700, color: C.faint, whiteSpace: "nowrap" }}>
                            네이버 금융
                            <svg width={9} height={9} viewBox="0 0 12 12" fill="none" stroke={C.faint} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                <line x1="2.5" y1="9.5" x2="9" y2="3" />
                                <polyline points="4.2,2.8 9.2,2.8 9.2,7.8" />
                            </svg>
                        </span>
                    </div>
                </div>, document.body)}
        </div>
    )
}

addPropertyControls(PublicStockSearch, {
    placeholder: { type: ControlType.String, title: "Placeholder", defaultValue: "종목 검색 (이름·코드)" },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: DEF_STOCK },
    usStockUrl: { type: ControlType.String, title: "US Stock URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

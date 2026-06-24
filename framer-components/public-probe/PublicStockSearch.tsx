import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 종목 검색창 (독립) — VERITY 공개 터미널. Framer 네이티브 nav 안에 끼워 쓰는 검색 전용.
 * Enter → 입력 텍스트를 유니버스에서 *종목코드*로 정규화 → /stock?q=<코드> 이동.
 *   (정규화 이유: 결정 페이지 컴포넌트는 ticker 정확매칭만 함. 종목명 ?q 는 빈 화면이 됨.)
 *   코드/이름 매칭 실패 시에만 raw 텍스트 fallback(리포트가 자체 이름매칭 시도).
 * 🚨 포커스(빈 검색어) = 최근 본 종목(localStorage) + "지금 거래 활발"(거래대금 상위, trending_kr.json) 노출.
 *   RULE 7 / held-2027 / 법률: "인기·추천"이 아니라 사실(거래대금/등락). "이런 종목 어때요" 류 추천 어조 금지.
 * 종목 공유 = ?q + localStorage `verity_last_ticker`/`verity_recent_tickers` 기록. nav 자체는 Framer 네이티브.
 * 테마: Framer 네이티브 추종 — body[data-framer-theme] 읽어 dark 전환(캔버스는 dark prop 정적 프리뷰).
 */

const LIGHT = { ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", vg: "#0ca678", vt: "#6c5ce7", vtS: "#f0edff", field: "#f2f4f6", card: "#ffffff", bg: "#f2f4f6", line: "#f0f1f3", up: "#f04452", down: "#3182f6" }
const DARK = { ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", vg: "#7fffa0", vt: "#a99bff", vtS: "#241f3a", field: "#0f1318", card: "#171c23", bg: "#0f1318", line: "#222730", up: "#f04452", down: "#5b9bff" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEF_STOCK = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
const DEF_TRENDING = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/trending_kr.json"
const LAST_TK_KEY = "verity_last_ticker"
const RECENTS_KEY = "verity_recent_tickers"
const RECENTS_CAP = 8
/* 로고 — 토스 종목 CDN(404/차단 시 이니셜 폴백) + circle-flags 원형 국기. ticker 형식으로 국장/미장 판별. */
const LOGO_BASE = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
function flagFromTicker(ticker: any): string {
    return /^\d{6}$/.test(String(ticker || "")) ? "kr" : "us"
}
function Logo(props: { ticker: any; name: any; C: any; size?: number }) {
    const { ticker, name, C } = props
    const size = props.size || 22
    const [err, setErr] = useState(false)
    const ch = (String(name || "?").trim().charAt(0)) || "?"
    const code = flagFromTicker(ticker)
    const fsize = Math.round(size * 0.46)
    return (
        <span style={{ position: "relative", width: size, height: size, flexShrink: 0, display: "inline-block" }}>
            {!err && ticker ? (
                <img src={LOGO_BASE + String(ticker).replace(/-/g, ".") + ".png"} alt="" width={size} height={size}
                    onError={() => setErr(true)}
                    style={{ width: size, height: size, borderRadius: 7, objectFit: "cover", display: "block", background: C.bg }} />
            ) : (
                <span style={{ width: size, height: size, borderRadius: 7, background: C.vtS, color: C.vt, display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * 0.42), fontWeight: 800 }}>{ch}</span>
            )}
            <img src={FLAG_BASE + code + ".svg"} alt="" width={fsize} height={fsize}
                style={{ position: "absolute", right: -3, bottom: -3, width: fsize, height: fsize, borderRadius: "50%", border: `1.5px solid ${C.card}`, background: C.card, display: "block", boxShadow: "0 1px 2px rgba(0,0,0,0.18)" }} />
        </span>
    )
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
    trendingUrl: string
    dark: boolean
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicStockSearch(props: Props) {
    const { placeholder, stockPath, stockUrl, usStockUrl, trendingUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 dark prop 정적) */
    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
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
    const [trending, setTrending] = useState<any[]>([])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    /* 유니버스 로드 — KR + US 동시(국장·미장 통합 검색). 2026-06-23. */
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const urls = [stockUrl, usStockUrl].filter(Boolean)
        Promise.all(urls.map((u) => fetch(u, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null)))
            .then((docs) => {
                if (!alive) return
                const merged: any[] = []
                for (const d of docs) { const a = d && (Array.isArray(d) ? d : d.stocks); if (Array.isArray(a)) merged.push(...a) }
                if (merged.length) setUniverse(merged)
            })
        return () => { alive = false }
    }, [stockUrl, usStockUrl, onCanvas])

    /* 거래대금 상위(지금 거래 활발) — 사실. trending_kr.json. */
    useEffect(() => {
        if (onCanvas || !trendingUrl) return
        let alive = true
        fetch(trendingUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { const t = d && Array.isArray(d.top) ? d.top : null; if (alive && t) setTrending(t.slice(0, 6)) })
            .catch(() => {})
        return () => { alive = false }
    }, [trendingUrl, onCanvas])

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
        return universe.filter((x) =>
            String(x.ticker).toLowerCase().includes(s) ||
            String(x.name || "").toLowerCase().includes(s) ||
            String((x as any).name_ko || "").includes(q.trim())
        ).slice(0, 12)
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

    const onFocus = () => { setRecents(readRecents()); setFocused(true) }

    const narrow = w > 0 && w < 200
    const showQuery = !!q.trim()
    const showSuggest = !onCanvas && focused && !showQuery && (recents.length > 0 || trending.length > 0)
    const showMatches = !onCanvas && focused && showQuery && matches.length > 0

    const wrap: CSSProperties = {
        width: "100%", height: "100%", boxSizing: "border-box",
        display: "flex", alignItems: "center", gap: 7,
        background: C.field, borderRadius: 999,
        padding: narrow ? "8px 12px" : "9px 14px",
        fontFamily: FONT,
    }
    const panel: CSSProperties = { position: "absolute", top: "calc(100% + 6px)", left: 0, right: 0, zIndex: 70, background: C.card, borderRadius: 12, boxShadow: "0 10px 30px rgba(0,0,0,0.16)", padding: 6, maxHeight: 360, overflowY: "auto", minWidth: 240 }
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

            {/* 연관검색어 (검색어 있을 때) */}
            {showMatches && (
                <div style={panel}>
                    {matches.map((m) => itemRow(m.ticker, m.ticker, m.name,
                        <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{m.name_ko ? m.name_ko + " · " : ""}{m.ticker}{m.market ? " · " + m.market : ""}</span>))}
                </div>
            )}

            {/* 포커스(빈 검색어) — 최근 본 종목 + 지금 거래 활발(사실) */}
            {showSuggest && (
                <div style={panel}>
                    {recents.length > 0 && (
                        <>
                            {secLabel("최근 본 종목")}
                            {recents.slice(0, 6).map((r) => itemRow("r:" + r.t, r.t, r.n,
                                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{r.t}</span>))}
                        </>
                    )}
                    {trending.length > 0 && (
                        <>
                            {secLabel("지금 거래 활발", "거래대금 상위 · 사실")}
                            {trending.map((t) => {
                                const chg = Number(t.chg)
                                const col = !isFinite(chg) ? C.faint : chg > 0 ? C.up : chg < 0 ? C.down : C.faint
                                return itemRow("t:" + t.ticker, t.ticker, t.name,
                                    <span style={{ fontSize: 12, fontWeight: 700, color: col, fontVariantNumeric: "tabular-nums" }}>{isFinite(chg) ? (chg > 0 ? "+" : "") + chg.toFixed(2) + "%" : "—"}</span>)
                            })}
                        </>
                    )}
                </div>
            )}
        </div>
    )
}

addPropertyControls(PublicStockSearch, {
    placeholder: { type: ControlType.String, title: "Placeholder", defaultValue: "종목 검색 (이름·코드)" },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: DEF_STOCK },
    usStockUrl: { type: ControlType.String, title: "US Stock URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json" },
    trendingUrl: { type: ControlType.String, title: "Trending URL", defaultValue: DEF_TRENDING },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

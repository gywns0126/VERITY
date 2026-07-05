import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * 퀵바 — 홈 3층 구조의 2·3층 (PM 2026-07-05): [최근 본 종목(자동)] + [고정 바로가기 4].
 *
 * 개인화 = 설정 0: localStorage("verity_recent_tickers") 최근 본 종목 칩 (없으면 행 숨김).
 * 이름 조인 = universe_search.json (sessionStorage 캐시). 커스텀 편집은 보류 (사용 데이터 후 판단).
 * 아이콘 = PublicPerspectiveMaps GIcon 도안 언어 동일(투톤 solid stroke + glass blur, 48 viewBox) —
 *   자작 이모지·外部 아이콘 금지 방침 정합, 퀵바 4종 신규 도안. 컴포넌트 자립 원칙으로 인라인.
 * RULE 7 — 동선 버튼만, 종목 나열 = 사용자 본인 방문 기록 (추천 아님).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", gTint: "rgba(108,92,231,0.22)",
}
const DARK = {
    bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440", gTint: "rgba(169,155,255,0.26)",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const SEARCH_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
const RECENT_KEY = "verity_recent_tickers"

/* ─── 아이콘 (GIcon 도안 언어 — solid stroke + glass 소프트 셰이프) ─── */
const _rr = (x: number, y: number, w: number, h: number, r: number): string =>
    `M${x + r} ${y} H${x + w - r} Q${x + w} ${y} ${x + w} ${y + r} V${y + h - r} Q${x + w} ${y + h} ${x + w - r} ${y + h} H${x + r} Q${x} ${y + h} ${x} ${y + h - r} V${y + r} Q${x} ${y} ${x + r} ${y} Z`
const _circ = (cx: number, cy: number, r: number): string =>
    `M${cx - r} ${cy} A${r} ${r} 0 1 0 ${cx + r} ${cy} A${r} ${r} 0 1 0 ${cx - r} ${cy} Z`

const QICONS: Record<string, { solid: (a: string) => any; glass: string }> = {
    search: {
        solid: (a) => (
            <g fill="none" stroke={a} strokeWidth={4} strokeLinecap="round">
                <circle cx={21} cy={21} r={10.5} />
                <line x1={29.5} y1={29.5} x2={40} y2={40} />
            </g>
        ),
        glass: _circ(21, 21, 13),
    },
    watch: {
        solid: (a) => (
            <path d="M15 7 H33 Q35.5 7 35.5 9.5 V41 L24 33 L12.5 41 V9.5 Q12.5 7 15 7 Z"
                fill="none" stroke={a} strokeWidth={4} strokeLinejoin="round" />
        ),
        glass: _rr(10, 5, 28, 38, 5),
    },
    filing: {
        solid: (a) => (
            <g fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round">
                <path d="M11 8 H29 L37 16 V40 Q37 42 35 42 H11 Q9 42 9 40 V10 Q9 8 11 8 Z" />
                <line x1={16} y1={22} x2={30} y2={22} />
                <line x1={16} y1={30} x2={30} y2={30} />
            </g>
        ),
        glass: _rr(6, 6, 34, 38, 5),
    },
    discover: {
        solid: (a) => (
            <g fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round">
                <circle cx={24} cy={24} r={16} />
                <path d="M30 18 L26.5 26.5 L18 30 L21.5 21.5 Z" />
            </g>
        ),
        glass: _circ(24, 24, 18),
    },
}

function QIcon(props: { k: string; size: number; a: string; g: string }) {
    const def = QICONS[props.k]
    if (!def) return null
    const fid = "vqbf-" + props.k
    const cid = "vqbc-" + props.k
    return (
        <svg width={props.size} height={props.size} viewBox="0 0 48 48" fill="none"
            style={{ display: "block", flexShrink: 0, overflow: "visible" }}>
            <defs>
                <filter id={fid} x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.1" /></filter>
                <clipPath id={cid}><path d={def.glass} /></clipPath>
            </defs>
            <g clipPath={`url(#${cid})`}>
                <g filter={`url(#${fid})`} opacity={0.85}>{def.solid(props.a)}</g>
                <path d={def.glass} fill={props.g} />
            </g>
            <g>{def.solid(props.a)}</g>
        </svg>
    )
}

const LINKS = [
    { k: "search", label: "종목 검색", path: "/stock" },
    { k: "watch", label: "내 관심종목", path: "/nest" },
    { k: "filing", label: "공시", path: "/disclosure" },
    { k: "discover", label: "발견", path: "/discover" },
]

const SAMPLE_RECENT = [
    { ticker: "005930", name: "삼성전자" },
    { ticker: "000660", name: "SK하이닉스" },
    { ticker: "NVDA", name: "NVIDIA" },
]

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicQuickBar(props: {
    width?: number; dark?: boolean; stockPath?: string; maxRecent?: number
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const [recent, setRecent] = useState<{ ticker: string; name: string }[]>(onCanvas ? SAMPLE_RECENT : [])

    useEffect(() => {
        if (onCanvas) return
        setThemeDark(readBodyDark())
        const obs = new MutationObserver(() => setThemeDark(readBodyDark()))
        if (document.body) obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        let alive = true
        let tickers: string[] = []
        try {
            const raw = window.localStorage.getItem(RECENT_KEY)
            const arr = raw ? JSON.parse(raw) : []
            if (Array.isArray(arr)) tickers = arr.map((t) => String(t)).filter(Boolean).slice(0, Math.max(1, props.maxRecent || 5))
        } catch (e) { /* ignore */ }
        if (!tickers.length) return
        const apply = (nameMap: Record<string, string>) => {
            if (!alive) return
            setRecent(tickers.map((t) => ({ ticker: t, name: nameMap[t] || t })))
        }
        try {
            const c = sessionStorage.getItem("universe_search_names")
            if (c) { apply(JSON.parse(c)); return }
        } catch (e) { /* ignore */ }
        fetch(SEARCH_URL, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const rows = (d && d.stocks) || []
                const m: Record<string, string> = {}
                for (const s of rows) { if (s && s.ticker) m[String(s.ticker)] = String(s.name || s.ticker) }
                try { sessionStorage.setItem("universe_search_names", JSON.stringify(m)) } catch (e) { /* ignore */ }
                apply(m)
            })
            .catch(() => apply({}))
        return () => { alive = false }
    }, [onCanvas, props.maxRecent])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const stockPath = props.stockPath || "/stock"

    const go = (path: string) => {
        if (onCanvas || typeof window === "undefined") return
        try { window.location.href = path } catch (e) { /* ignore */ }
    }

    const wrap: CSSProperties = {
        width: props.width || 380, maxWidth: "100%", fontFamily: FONT, background: C.bg,
        color: C.ink, padding: "0 14px", boxSizing: "border-box",
    }

    return (
        <div style={wrap}>
            {/* 최근 본 종목 — 본인 방문 기록 (자동, 설정 0) */}
            {recent.length > 0 && (
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: C.faint, flexShrink: 0 }}>최근 본</span>
                    {recent.map((r) => (
                        <span key={r.ticker} onClick={() => go(`${stockPath}?q=${encodeURIComponent(r.ticker)}`)}
                            style={{ cursor: "pointer", fontSize: 11.5, fontWeight: 700, color: C.violet, background: C.violetSoft, borderRadius: 8, padding: "4px 10px" }}>
                            {r.name}
                        </span>
                    ))}
                </div>
            )}

            {/* 고정 바로가기 4 */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
                {LINKS.map((l) => (
                    <button key={l.k} onClick={() => go(l.path)}
                        style={{ border: "none", cursor: "pointer", fontFamily: FONT, background: C.card, borderRadius: 14, padding: "12px 4px 10px", display: "flex", flexDirection: "column", alignItems: "center", gap: 6, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <QIcon k={l.k} size={22} a={C.violet} g={C.gTint} />
                        <span style={{ fontSize: 11, fontWeight: 700, color: C.sub }}>{l.label}</span>
                    </button>
                ))}
            </div>
        </div>
    )
}

addPropertyControls(PublicQuickBar, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
    maxRecent: { type: ControlType.Number, title: "최근 본 최대", defaultValue: 5 },
})

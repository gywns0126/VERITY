import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * 모바일 하단 네비 시안 — AlphaNest 공개. 하단 탭바 4핵심 + 더보기 시트(롱테일).
 *
 * 목적 = 13페이지를 5슬롯으로(홈·탐색·종목·내 것 + 더보기). 나머지는 시트로.
 * 🚨 Framer 제약: 코드 컴포넌트=iframe → position:fixed 뷰포트 고정 안 됨.
 *   실제 하단 고정은 이 컴포넌트를 Framer 네이티브 sticky 프레임에 넣어 처리.
 *   여기선 바 디자인·활성표시·더보기 시트 인터랙션 시안.
 * 아이콘 = 인라인 stroke SVG(자립, npm import 회피). 활성=보라, 비활성=faint.
 * 다크모드 = body[data-framer-theme] 자가감지. 경로 = props.
 */

const LIGHT = { bar: "#ffffff", ink: "#191f28", faint: "#8b95a1", line: "#e5e8eb", violet: "#6c5ce7", sheet: "#ffffff", scrim: "rgba(0,0,0,0.32)", chip: "#f2f4f6" }
const DARK = { bar: "#171c23", ink: "#e3e7ec", faint: "#828d9b", line: "#252b34", violet: "#a99bff", sheet: "#1e2128", scrim: "rgba(0,0,0,0.5)", chip: "#0f1318" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

/* 인라인 stroke 아이콘 — 24 viewBox, currentColor */
const ICONS: Record<string, any> = {
    home: <><path d="M4 11.5 12 4l8 7.5" /><path d="M6 10.5V20h12v-9.5" /></>,
    explore: <><circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></>,
    stock: <><polyline points="4,15 9,10 13,13 20,6" /><polyline points="15,6 20,6 20,11" /></>,
    me: <><circle cx="12" cy="8" r="3.4" /><path d="M5.5 20c0-4 3-6 6.5-6s6.5 2 6.5 6" /></>,
    more: <><circle cx="5" cy="12" r="1.4" /><circle cx="12" cy="12" r="1.4" /><circle cx="19" cy="12" r="1.4" /></>,
    market: <><line x1="4" y1="20" x2="20" y2="20" /><rect x="5.5" y="12" width="3" height="6" /><rect x="10.5" y="8" width="3" height="10" /><rect x="15.5" y="5" width="3" height="13" /></>,
    glassbox: <><rect x="5" y="5" width="14" height="14" rx="3" /><path d="M9 12l2 2 4-4" /></>,
    news: <><rect x="4" y="5" width="16" height="14" rx="2" /><line x1="7" y1="9" x2="14" y2="9" /><line x1="7" y1="13" x2="17" y2="13" /></>,
    disclosure: <><path d="M7 4h7l4 4v12H7z" /><polyline points="14,4 14,8 18,8" /></>,
    decision: <><path d="M12 3l3 6 6 .5-4.5 4 1.5 6-6-3.2L6 19.5 7.5 13.5 3 9.5 9 9z" /></>,
    nest: <><path d="M4 14c0-4 3.5-7 8-7s8 3 8 7" /><ellipse cx="12" cy="15" rx="8" ry="3.5" /></>,
    broker: <><rect x="3.5" y="8" width="17" height="11" rx="2" /><path d="M8 8V6.5A2.5 2.5 0 0 1 10.5 4h3A2.5 2.5 0 0 1 16 6.5V8" /></>,
    smallcap: <><circle cx="12" cy="12" r="8" /><path d="M12 8v8M9 10.5h4.5a1.8 1.8 0 0 1 0 3.5H9" /></>,
    policy: <><path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" /></>,
}
function Icon({ k, c, size = 23 }: { k: string; c: string; size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" style={{ display: "block" }}>
            {ICONS[k] || null}
        </svg>
    )
}

type Item = { key: string; label: string; path: string }

export default function PublicMobileNav(props: {
    homePath?: string; explorePath?: string; stockPath?: string; mePath?: string
    marketPath?: string; glassboxPath?: string; newsPath?: string; disclosurePath?: string
    decisionPath?: string; nestPath?: string; brokerPath?: string; smallcapPath?: string; policyPath?: string
    dark?: boolean; activePath?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const [moreOpen, setMoreOpen] = useState(false)
    const [path, setPath] = useState<string>(props.activePath || "/")

    useEffect(() => {
        if (onCanvas) return
        setThemeDark(readBodyDark())
        const obs = new MutationObserver(() => setThemeDark(readBodyDark()))
        if (document.body) obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        try { setPath(window.location.pathname || "/") } catch (e) {}
        return () => obs.disconnect()
    }, [onCanvas])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const core: Item[] = [
        { key: "home", label: "홈", path: props.homePath || "/" },
        { key: "explore", label: "탐색", path: props.explorePath || "/discover" },
        { key: "stock", label: "종목", path: props.stockPath || "/stock" },
        { key: "me", label: "내 것", path: props.mePath || "/me" },
    ]
    const more: Item[] = [
        { key: "market", label: "시장", path: props.marketPath || "/market" },
        { key: "glassbox", label: "유리박스", path: props.glassboxPath || "/glassbox" },
        { key: "news", label: "뉴스", path: props.newsPath || "/news" },
        { key: "decision", label: "결정", path: props.decisionPath || "/decision" },
        { key: "disclosure", label: "공시", path: props.disclosurePath || "/disclosure" },
        { key: "nest", label: "둥지", path: props.nestPath || "/nest" },
        { key: "broker", label: "증권사", path: props.brokerPath || "/broker" },
        { key: "smallcap", label: "소형주", path: props.smallcapPath || "/smallcap" },
        { key: "policy", label: "약관", path: props.policyPath || "/policy" },
    ]

    const norm = (p: string) => (p || "/").replace(/\/+$/, "") || "/"
    const cur = norm(path)
    const coreActive = core.findIndex((it) => norm(it.path) === cur)
    const moreActive = coreActive < 0 && more.some((it) => norm(it.path) === cur)

    const go = (p: string) => {
        setMoreOpen(false)
        if (onCanvas || typeof window === "undefined") return
        try { window.location.href = p } catch (e) {}
    }

    const wrap: CSSProperties = { width: "100%", maxWidth: "100%", boxSizing: "border-box", fontFamily: FONT, position: "relative" }
    const tab = (it: Item | { key: string; label: string }, active: boolean, onClick: () => void) => {
        const col = active ? C.violet : C.faint
        return (
            <button key={it.key} onClick={onClick}
                style={{ flex: 1, border: "none", background: "transparent", cursor: "pointer", fontFamily: FONT, padding: "8px 0 7px", display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                <Icon k={it.key} c={col} />
                <span style={{ fontSize: 10.5, fontWeight: active ? 800 : 600, color: col, letterSpacing: "-0.2px" }}>{it.label}</span>
            </button>
        )
    }

    return (
        <div style={wrap}>
            {/* 더보기 시트 (바 위로 펼침) */}
            {moreOpen && (
                <>
                    <div onClick={() => setMoreOpen(false)}
                        style={{ position: "absolute", left: 0, right: 0, bottom: "100%", height: 480, background: C.scrim, cursor: "pointer" }} />
                    <div style={{ position: "relative", zIndex: 2, background: C.sheet, borderTopLeftRadius: 18, borderTopRightRadius: 18, boxShadow: "0 -6px 24px rgba(0,0,0,0.14)", padding: "10px 16px 14px" }}>
                        <div style={{ width: 36, height: 4, borderRadius: 2, background: C.line, margin: "2px auto 12px" }} />
                        <div style={{ fontSize: 12, fontWeight: 800, color: C.faint, marginBottom: 10 }}>더보기</div>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
                            {more.map((it) => {
                                const active = norm(it.path) === cur
                                return (
                                    <button key={it.key} onClick={() => go(it.path)}
                                        style={{ border: "none", cursor: "pointer", fontFamily: FONT, background: active ? C.chip : "transparent", borderRadius: 12, padding: "12px 4px 10px", display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                                        <Icon k={it.key} c={active ? C.violet : C.ink} size={22} />
                                        <span style={{ fontSize: 11, fontWeight: 700, color: active ? C.violet : C.ink }}>{it.label}</span>
                                    </button>
                                )
                            })}
                        </div>
                    </div>
                </>
            )}

            {/* 하단 탭바 */}
            <div style={{ position: "relative", zIndex: 3, display: "flex", alignItems: "stretch", background: C.bar, borderTop: `1px solid ${C.line}`, paddingBottom: "env(safe-area-inset-bottom, 0px)" }}>
                {core.map((it, i) => tab(it, coreActive === i, () => go(it.path)))}
                {tab({ key: "more", label: "더보기" }, moreOpen || moreActive, () => setMoreOpen((v) => !v))}
            </div>
        </div>
    )
}

addPropertyControls(PublicMobileNav, {
    homePath: { type: ControlType.String, title: "홈", defaultValue: "/" },
    explorePath: { type: ControlType.String, title: "탐색", defaultValue: "/discover" },
    stockPath: { type: ControlType.String, title: "종목", defaultValue: "/stock" },
    mePath: { type: ControlType.String, title: "내 것", defaultValue: "/me" },
    marketPath: { type: ControlType.String, title: "시장", defaultValue: "/market" },
    glassboxPath: { type: ControlType.String, title: "유리박스", defaultValue: "/glassbox" },
    newsPath: { type: ControlType.String, title: "뉴스", defaultValue: "/news" },
    decisionPath: { type: ControlType.String, title: "결정", defaultValue: "/decision" },
    disclosurePath: { type: ControlType.String, title: "공시", defaultValue: "/disclosure" },
    nestPath: { type: ControlType.String, title: "둥지", defaultValue: "/nest" },
    brokerPath: { type: ControlType.String, title: "증권사", defaultValue: "/broker" },
    smallcapPath: { type: ControlType.String, title: "소형주", defaultValue: "/smallcap" },
    policyPath: { type: ControlType.String, title: "약관", defaultValue: "/policy" },
    activePath: { type: ControlType.String, title: "활성 경로(캔버스)", defaultValue: "/" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

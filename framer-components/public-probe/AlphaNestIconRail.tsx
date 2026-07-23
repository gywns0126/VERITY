import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

/**
 * AlphaNestIconRail — 좌측 아이콘 레일 내비 (프로토타입).
 *
 * 접힘 기본(아이콘만, ~64px) → hover 시 펼침(라벨, ~224px). 핀 고정 토글. 활성 항목 강조.
 * 펼침 = 콘텐츠 위 오버레이(레이아웃 안 밀림) → 콘텐츠 좌측 여백은 접힘폭(64px)만 주면 됨.
 * 모바일(minWidthPx 미만) = 자동 숨김 — 하단 탭(PublicMobileNav) 유지. 다크 = body[data-framer-theme] 추종.
 *
 * 아이콘 = 인라인 SVG(외부 의존 0, currentColor 상속) — Phosphor 스타일 라인 글리프.
 *   (@phosphor-icons/react import 가 Framer 생성 시점 resolve 에서 실패해 인라인으로 전환.)
 * ⚠ 데스크톱 패턴 프로토타입. 실제 배치·모바일 하단탭은 Framer 네이티브 유지.
 * ⚠ 보수 구문(옵셔널체이닝 ?. / 널병합 ?? / 옵셔널 catch{} / defaultProps 회피).
 *
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

// ── 인라인 아이콘 (24 그리드, stroke=currentColor) ──
function Icon(props: { name: string; size: number }) {
    const s = props.size
    const n = props.name
    let body = null
    if (n === "home") body = <><path d="M4 11.5 12 4l8 7.5" /><path d="M6 10.5V20h12v-9.5" /></>
    else if (n === "market") body = <><path d="M4 16l4.5-4.5 3.5 3L20 7" /><path d="M15 7h5v5" /></>
    else if (n === "disclosure") body = <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4" /><path d="M9 12h6M9 16h6" /></>
    else if (n === "report") body = <><circle cx="10.5" cy="10.5" r="6" /><path d="M15 15l5 5" /></>
    else if (n === "discover") body = <><circle cx="12" cy="12" r="8.5" /><path d="M9 15l1.6-4.4L15 9l-1.6 4.4z" /></>
    else if (n === "news") body = <><path d="M4 5h13v14H5a1 1 0 0 1-1-1z" /><path d="M17 8h3v9a2 2 0 0 1-2 2" /><path d="M7 9h7M7 12h7M7 15h4" /></>
    else if (n === "broker") body = <><path d="M4 9l8-5 8 5" /><path d="M5 9v9M9 9v9M15 9v9M19 9v9" /><path d="M3 20h18" /></>
    else if (n === "smallcap") body = <><circle cx="12" cy="12" r="8.5" /><path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3" /><circle cx="12" cy="12" r="1.3" /></>
    else if (n === "glassbox") body = <><path d="M12 3l7 3v6c0 4-3 7-7 8-4-1-7-4-7-8V6z" /><path d="M9 12l2 2 4-4" /></>
    else if (n === "nest") body = <><path d="M3 8.5A2.5 2.5 0 0 1 5.5 6H17a1 1 0 0 1 1 1v1" /><path d="M3 8.5V17a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-5a2 2 0 0 0-2-2H5a2 2 0 0 1-2-1.5z" /><path d="M16.5 14.5h.01" /></>
    else if (n === "community") body = <><path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-4 4z" /><path d="M8 9h8M8 12h5" /></>
    else if (n === "me") body = <><circle cx="12" cy="9" r="3.5" /><path d="M5.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6" /></>
    else if (n === "pin") body = <><path d="M9.5 3.5h5l-1 6.5 3 3.5H7.5l3-3.5z" /><path d="M12 13.5V21" /></>
    return (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ display: "block" }}>
            {body}
        </svg>
    )
}

const NAV = [
    { label: "홈", path: "/", icon: "home" },
    { label: "시장", path: "/market", icon: "market" },
    { label: "공시·수급", path: "/disclosure", icon: "disclosure" },
    { label: "리포트", path: "/stock", icon: "report" },
    { label: "발견", path: "/discover", icon: "discover" },
    { label: "뉴스", path: "/news", icon: "news" },
    { label: "증권사", path: "/broker", icon: "broker" },
    { label: "소형주", path: "/smallcap", icon: "smallcap" },
    { label: "검증", path: "/glassbox", icon: "glassbox" },
    { label: "둥지", path: "/nest", icon: "nest" },
]
const NAV_BOTTOM = [
    { label: "커뮤니티", path: "/community", icon: "community" },
    { label: "내정보", path: "/me", icon: "me" },
]

function bodyDark(): boolean {
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
        if (typeof window !== "undefined" && window.matchMedia) return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {}
    return false
}

function AlphaMark(props: { size: number }) {
    const size = props.size
    return (
        <svg width={(size * 870) / 830} height={size} viewBox="0 0 870 830" fill="none" aria-hidden="true" style={{ display: "block" }}>
            <path d="M74.9999 403.5C74.9999 617 249 754.5 434 754.5C619 754.5 794.5 617 794.5 403.5" stroke="#3A4268" strokeWidth="150" strokeLinecap="round" />
            <path d="M648.655 309.5C648.655 479 561.655 598 433.655 598C309.943 598 216.155 465 220.655 309.5C220.655 143.815 331.655 0 434.655 0C537.655 0 648.655 140 648.655 309.5Z" fill="#6B51EA" />
        </svg>
    )
}

export default function AlphaNestIconRail(props: any) {
    const brandLabel = props.brandLabel || "알파네스트"
    const accent = props.accent || "#6c5ce7"
    const COL = props.collapsedW > 0 ? props.collapsedW : 64
    const EXP = props.expandedW > 0 ? props.expandedW : 224
    const minWidthPx = props.minWidthPx > 0 ? props.minWidthPx : 820

    const isCanvas = RenderTarget.current() === RenderTarget.canvas
    const [dark, setDark] = useState<boolean>(isCanvas ? !!props.dark : bodyDark())
    const [hovered, setHovered] = useState<boolean>(false)
    const [pinned, setPinned] = useState<boolean>(!!props.pinnedDefault)
    const [path, setPath] = useState<string>("/")
    const [vw, setVw] = useState<number>(1200)

    useEffect(() => {
        if (isCanvas) { setDark(!!props.dark); return }
        if (typeof window !== "undefined") {
            if (window.location) setPath(window.location.pathname || "/")
            const onResize = () => setVw(window.innerWidth || 1200)
            onResize()
            window.addEventListener("resize", onResize)
            const read = () => setDark(bodyDark())
            read()
            let obs: MutationObserver | null = null
            if (typeof MutationObserver !== "undefined" && document.body) {
                obs = new MutationObserver(read)
                obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
            }
            return () => {
                window.removeEventListener("resize", onResize)
                if (obs) obs.disconnect()
            }
        }
    }, [isCanvas, props.dark])

    // 모바일 = 숨김(하단 탭 유지). 캔버스는 항상 표시.
    if (!isCanvas && vw < minWidthPx) return null

    const expanded = pinned || hovered
    const W = expanded ? EXP : COL

    // 팔레트 (토스톤)
    const navBg = dark ? "#171c23" : "#ffffff"
    const line = dark ? "#252b34" : "#eceef1"
    const ink = dark ? "#e3e7ec" : "#191f28"
    const sub = dark ? "#9aa4b1" : "#6b7684"
    const vt = dark ? "#a99bff" : accent
    const vtS = dark ? "#241f3a" : "#f0edff"
    const hoverBg = dark ? "#1e242c" : "#f5f6f8"
    const iconBoxW = COL - 20

    const row = (item: { label: string; path: string; icon: string }, key: string) => {
        const active = path === item.path || (item.path !== "/" && path.indexOf(item.path) === 0)
        return (
            <a key={key} href={item.path} className="arail-row"
                style={{ display: "flex", alignItems: "center", height: 46, textDecoration: "none", borderRadius: 12, margin: "2px 10px", overflow: "hidden", whiteSpace: "nowrap", color: active ? vt : sub, background: active ? vtS : "transparent", fontWeight: active ? 800 : 600 }}>
                <span style={{ width: iconBoxW, minWidth: iconBoxW, display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <Icon name={item.icon} size={22} />
                </span>
                <span style={{ fontSize: 14, letterSpacing: "-0.2px", opacity: expanded ? 1 : 0, transition: "opacity .14s ease" }}>{item.label}</span>
            </a>
        )
    }

    return (
        <nav onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
            style={{ position: "fixed", top: 0, left: 0, height: "100vh", width: W, background: navBg, borderRight: "1px solid " + line, boxSizing: "border-box", display: "flex", flexDirection: "column", fontFamily: FONT, zIndex: 9000, transition: "width .18s cubic-bezier(.4,0,.2,1)", boxShadow: expanded ? (dark ? "0 0 40px rgba(0,0,0,0.5)" : "0 0 40px rgba(17,24,39,0.1)") : "none", overflow: "hidden" }}>
            <style>{".arail-row:hover{background:" + hoverBg + " !important}"}</style>
            <a href="/" style={{ display: "flex", alignItems: "center", height: 58, margin: "8px 10px 6px", textDecoration: "none", overflow: "hidden", whiteSpace: "nowrap" }}>
                <span style={{ width: iconBoxW, minWidth: iconBoxW, display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <AlphaMark size={24} />
                </span>
                <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.4px", color: ink, opacity: expanded ? 1 : 0, transition: "opacity .14s ease" }}>{brandLabel}</span>
            </a>
            <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden", paddingTop: 4 }}>
                {NAV.map((it, i) => row(it, "n" + i))}
            </div>
            <div style={{ borderTop: "1px solid " + line, paddingTop: 6, paddingBottom: 8 }}>
                {NAV_BOTTOM.map((it, i) => row(it, "b" + i))}
                <div role="button" tabIndex={0} onClick={() => setPinned((v) => !v)} className="arail-row"
                    style={{ display: "flex", alignItems: "center", height: 42, cursor: "pointer", borderRadius: 12, margin: "2px 10px", overflow: "hidden", whiteSpace: "nowrap", color: pinned ? vt : sub, background: "transparent", fontWeight: 600, userSelect: "none" }}>
                    <span style={{ width: iconBoxW, minWidth: iconBoxW, display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <Icon name="pin" size={20} />
                    </span>
                    <span style={{ fontSize: 13, opacity: expanded ? 1 : 0, transition: "opacity .14s ease" }}>{pinned ? "고정 해제" : "메뉴 고정"}</span>
                </div>
            </div>
        </nav>
    )
}

addPropertyControls(AlphaNestIconRail, {
    brandLabel: { type: ControlType.String, title: "브랜드", defaultValue: "알파네스트" },
    accent: { type: ControlType.Color, title: "액센트", defaultValue: "#6c5ce7" },
    collapsedW: { type: ControlType.Number, title: "접힘 폭", min: 48, max: 96, step: 4, defaultValue: 64 },
    expandedW: { type: ControlType.Number, title: "펼침 폭", min: 160, max: 320, step: 8, defaultValue: 224 },
    minWidthPx: { type: ControlType.Number, title: "모바일 숨김(px 미만)", min: 0, max: 1200, step: 20, defaultValue: 820 },
    pinnedDefault: { type: ControlType.Boolean, title: "기본 고정", defaultValue: false },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})

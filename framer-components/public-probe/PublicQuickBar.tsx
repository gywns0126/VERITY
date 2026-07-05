import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * 퀵바 — 홈 3층 구조의 2·3층 (PM 2026-07-05): [최근 본 종목(자동)] + [고정 바로가기 4].
 *
 * 최근 본 종목 행 = 제거 (PM 2026-07-05 "별로네"). 고정 바로가기 4버튼만. 커스텀 편집 = 보류.
 * 아이콘 = Phosphor 정식 도안(regular, unpkg 추출 — 자작 SVG 금지 규칙) + GIcon 계열 glass 틴트 레이어.
 * RULE 7 — 동선 버튼만, 종목 나열 = 사용자 본인 방문 기록 (추천 아님).
 */

// 무채색 전환 (PM 2026-07-05 '홈 보라 난무') — violet 키 이름 유지, 값만 뉴트럴
const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#333d4b", violetSoft: "#eef0f3", gTint: "rgba(51,61,75,0.14)",
}
const DARK = {
    bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#d0d6dd", violetSoft: "#262b33", gTint: "rgba(208,214,221,0.18)",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

/* ─── 아이콘 (GIcon 도안 언어 — solid stroke + glass 소프트 셰이프) ─── */
const _rr = (x: number, y: number, w: number, h: number, r: number): string =>
    `M${x + r} ${y} H${x + w - r} Q${x + w} ${y} ${x + w} ${y + r} V${y + h - r} Q${x + w} ${y + h} ${x + w - r} ${y + h} H${x + r} Q${x} ${y + h} ${x} ${y + h - r} V${y + r} Q${x} ${y} ${x + r} ${y} Z`
const _circ = (cx: number, cy: number, r: number): string =>
    `M${cx - r} ${cy} A${r} ${r} 0 1 0 ${cx + r} ${cy} A${r} ${r} 0 1 0 ${cx - r} ${cy} Z`

// Phosphor 정식 도안 (regular, viewBox 256 — feedback_framer_icons_use_phosphor: 자작 SVG 금지) + glass 틴트 레이어
const QICONS: Record<string, { d: string; glass: string }> = {
    search: { d: "M229.66,218.34l-50.07-50.06a88.11,88.11,0,1,0-11.31,11.31l50.06,50.07a8,8,0,0,0,11.32-11.32ZM40,112a72,72,0,1,1,72,72A72.08,72.08,0,0,1,40,112Z", glass: _circ(112, 112, 76) },
    watch: { d: "M184,32H72A16,16,0,0,0,56,48V224a8,8,0,0,0,12.24,6.78L128,193.43l59.77,37.35A8,8,0,0,0,200,224V48A16,16,0,0,0,184,32Zm0,177.57-51.77-32.35a8,8,0,0,0-8.48,0L72,209.57V48H184Z", glass: _rr(56, 28, 144, 200, 16) },
    filing: { d: "M213.66,82.34l-56-56A8,8,0,0,0,152,24H56A16,16,0,0,0,40,40V216a16,16,0,0,0,16,16H200a16,16,0,0,0,16-16V88A8,8,0,0,0,213.66,82.34ZM160,51.31,188.69,80H160ZM200,216H56V40h88V88a8,8,0,0,0,8,8h48V216Zm-32-80a8,8,0,0,1-8,8H96a8,8,0,0,1,0-16h64A8,8,0,0,1,168,136Zm0,32a8,8,0,0,1-8,8H96a8,8,0,0,1,0-16h64A8,8,0,0,1,168,168Z", glass: _rr(48, 24, 160, 208, 16) },
    discover: { d: "M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216ZM172.42,72.84l-64,32a8.05,8.05,0,0,0-3.58,3.58l-32,64A8,8,0,0,0,80,184a8.1,8.1,0,0,0,3.58-.84l64-32a8.05,8.05,0,0,0,3.58-3.58l32-64a8,8,0,0,0-10.74-10.74ZM138,138,97.89,158.11,118,118l40.15-20.07Z", glass: _circ(128, 128, 100) },
}

function QIcon(props: { k: string; size: number; a: string; g: string }) {
    const def = QICONS[props.k]
    if (!def) return null
    const fid = "vqbf-" + props.k
    const cid = "vqbc-" + props.k
    return (
        <svg width={props.size} height={props.size} viewBox="0 0 256 256" fill="none"
            style={{ display: "block", flexShrink: 0, overflow: "visible" }}>
            <defs>
                <filter id={fid} x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="11" /></filter>
                <clipPath id={cid}><path d={def.glass} /></clipPath>
            </defs>
            <g clipPath={`url(#${cid})`}>
                <g filter={`url(#${fid})`} opacity={0.85}><path d={def.d} fill={props.a} /></g>
                <path d={def.glass} fill={props.g} />
            </g>
            <path d={def.d} fill={props.a} />
        </svg>
    )
}

const LINKS = [
    { k: "search", label: "종목 검색", path: "/stock" },
    { k: "watch", label: "내 관심종목", path: "/nest" },
    { k: "filing", label: "공시", path: "/disclosure" },
    { k: "discover", label: "발견", path: "/discover" },
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
    width?: number; dark?: boolean; stockPath?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)

    useEffect(() => {
        if (onCanvas) return
        setThemeDark(readBodyDark())
        const obs = new MutationObserver(() => setThemeDark(readBodyDark()))
        if (document.body) obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

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
})

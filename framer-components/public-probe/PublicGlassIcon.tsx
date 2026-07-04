import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

/**
 * 글래스 아이콘 15종 — VERITY 공개 터미널 (토스식 glassmorphism, 순수 SVG · 배경 없음).
 *
 * 용도 = 욕구 단계(매슬로) · 매출 안정성/흔들림 · 자사주 신호 라벨 아이콘 (2026-07-04 PM 요청).
 * 구조 = solid(선명 보라) + glass(반투명 틴트) 2레이어. glass 영역과 겹치는 solid 는
 *   블러 복제본(clipPath+feGaussianBlur)로 프로스트 효과 — backdrop-filter 없이 SVG 만으로 재현
 *   (배경 없음 요구 = 어떤 배경 위에서도 동작).
 * 테마 = body[data-framer-theme] 자가감지 (라이트 #6c5ce7 / 다크 #a99bff). 캔버스는 dark prop 프리뷰.
 * 사용 = 인스턴스 배치 후 Icon 드롭다운 선택. size 프레임 정합(정사각 권장).
 */

type IconKey =
    | "desire" | "survival" | "safety" | "belonging" | "esteem" | "selfActual" | "infra"
    | "revStable" | "volLow" | "volMid" | "volHigh"
    | "treasury" | "buySteady" | "buySome" | "sellBias"

interface Props {
    icon: IconKey
    size: number
    dark: boolean
    anim: string
}

const ACCENT_LIGHT = "#6c5ce7"
const ACCENT_DARK = "#a99bff"
const GLASS_LIGHT = "rgba(108,92,231,0.22)"
const GLASS_DARK = "rgba(169,155,255,0.26)"

/* 각 아이콘 = { solid: 선명 레이어 renderer, glass: 반투명 shape 의 path d (멀티 서브패스 허용) } */
const rr = (x: number, y: number, w: number, h: number, r: number): string =>
    `M${x + r} ${y} H${x + w - r} Q${x + w} ${y} ${x + w} ${y + r} V${y + h - r} Q${x + w} ${y + h} ${x + w - r} ${y + h} H${x + r} Q${x} ${y + h} ${x} ${y + h - r} V${y + r} Q${x} ${y} ${x + r} ${y} Z`
const circ = (cx: number, cy: number, r: number): string =>
    `M${cx - r} ${cy} a${r} ${r} 0 1 0 ${r * 2} 0 a${r} ${r} 0 1 0 ${-r * 2} 0 Z`
const CARD = rr(4, 9, 40, 30, 5)
const COIN = circ(20, 26, 13)
const coinBar = (y: number): string => rr(7.5, y, 28, 5.5, 2.75)

const ICONS: Record<IconKey, { solid: (a: string) => any; glass: string }> = {
    // 1. 욕구 — 매슬로 피라미드 (상단 solid 삼각 + 하단 glass 받침)
    desire: {
        solid: (a) => <path d="M24 6 L35 25 Q36.5 28 33 28 H15 Q11.5 28 13 25 Z" fill={a} />,
        glass: "M12.5 24 H35.5 L41.5 38.5 Q43 42 39.5 42 H8.5 Q5 42 6.5 38.5 Z",
    },
    // 2. 생존/심리 — 하트(glass) + 심전도 펄스(solid)
    survival: {
        solid: (a) => <polyline points="5,24 14,24 18.5,16.5 25,31.5 29,24 43,24" fill="none" stroke={a} strokeWidth={3.6} strokeLinecap="round" strokeLinejoin="round" />,
        glass: "M24 41 C10 32 6 22 10.5 15.5 C14.5 10 21 11 24 16 C27 11 33.5 10 37.5 15.5 C42 22 38 32 24 41 Z",
    },
    // 3. 안전 — 방패(glass) + 체크(solid)
    safety: {
        solid: (a) => <polyline points="16,24 22,30 33,17" fill="none" stroke={a} strokeWidth={4.5} strokeLinecap="round" strokeLinejoin="round" />,
        glass: "M24 5 L39 11 V22 C39 32 33 38.5 24 43 C15 38.5 9 32 9 22 V11 Z",
    },
    // 4. 소속/연결 — 뒷사람(solid) + 앞사람(glass)
    belonging: {
        solid: (a) => (
            <g fill={a}>
                <circle cx={31} cy={14} r={5.5} />
                <path d="M22 34 Q22 24 31 24 Q40 24 40 34 Q40 36 38 36 H24 Q22 36 22 34 Z" />
            </g>
        ),
        glass: circ(18, 18, 7) + " M6 40 Q6 27 18 27 Q30 27 30 40 Q30 42.5 27.5 42.5 H8.5 Q6 42.5 6 40 Z",
    },
    // 5. 존중/과시 — 빛나는 원(solid) + 왕관(glass)
    esteem: {
        solid: (a) => <circle cx={38} cy={12} r={6} fill={a} />,
        glass: "M10 36 L12 17 L20 25 L24 12.5 L28 25 L36 17 L38 36 Q38 38.5 35.5 38.5 H12.5 Q10 38.5 10 36 Z",
    },
    // 6. 자아실현 — 큰 별(glass) + 스파클(solid)
    selfActual: {
        solid: (a) => <path d="M34 6 L36.4 11.6 L42 14 L36.4 16.4 L34 22 L31.6 16.4 L26 14 L31.6 11.6 Z" fill={a} />,
        glass: "M22 12 L25.4 20.2 L34.2 20.8 L27.4 26.5 L29.6 35 L22 30.2 L14.4 35 L16.6 26.5 L9.8 20.8 L18.6 20.2 Z",
    },
    // 7. 기반/인프라 — 페디먼트(solid) + 기둥·기단(glass)
    infra: {
        solid: (a) => <path d="M8 15 L24 6 L40 15 Q41 17.5 38 17.5 H10 Q7 17.5 8 15 Z" fill={a} />,
        glass: rr(6, 38, 36, 4.5, 2.25) + " M11 16 H16 V36 H11 Z M21.5 16 H26.5 V36 H21.5 Z M32 16 H37 V36 H32 Z",
    },
    // 8. 매출 안정성 — 카드(glass) + 완만한 우상향 라인(solid)
    revStable: {
        solid: (a) => (
            <g>
                <polyline points="4,31 16,26 28,27.5 44,19" fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" />
                <circle cx={44} cy={19} r={3.2} fill={a} />
            </g>
        ),
        glass: CARD,
    },
    // 9~11. 매출 흔들림 — 카드(glass) + 진폭 S/M/L 파동(solid)
    volLow: {
        solid: (a) => <polyline points="4,25.5 11,22.5 18,25.5 25,22.5 32,25.5 39,22.5 44,24.5" fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" />,
        glass: CARD,
    },
    volMid: {
        solid: (a) => <polyline points="4,28 11,20 18,28 25,20 32,28 39,20 44,26" fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" />,
        glass: CARD,
    },
    volHigh: {
        solid: (a) => <polyline points="4,33 11,14 18,33 25,14 32,33 39,14 44,30" fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" />,
        glass: CARD,
    },
    // 12. 자사주 — 금고(glass) + 다이얼·핸들(solid)
    treasury: {
        solid: (a) => (
            <g>
                <circle cx={24} cy={24} r={7.5} fill={a} />
                <circle cx={24} cy={24} r={2.4} fill="#ffffff" fillOpacity={0.92} />
                <path d="M31 22.5 H41.5 Q43 22.5 43 24 Q43 25.5 41.5 25.5 H31 Z" fill={a} />
            </g>
        ),
        glass: rr(5, 8, 38, 32, 6),
    },
    // 13. 꾸준한 매입 — 코인 스택 3단(glass) + 굵은 상향 화살표(solid)
    buySteady: {
        solid: (a) => (
            <g fill="none" stroke={a} strokeWidth={4.5} strokeLinecap="round" strokeLinejoin="round">
                <line x1={36} y1={36} x2={36} y2={16} />
                <polyline points="29,22 36,14.5 43,22" />
            </g>
        ),
        glass: coinBar(19) + " " + coinBar(26) + " " + coinBar(33),
    },
    // 14. 매입 있음 — 코인(glass) + 작은 상향 화살표(solid)
    buySome: {
        solid: (a) => (
            <g fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round">
                <line x1={36} y1={30} x2={36} y2={18} />
                <polyline points="31,23 36,17.5 41,23" />
            </g>
        ),
        glass: COIN,
    },
    // 15. 처분 우위 — 코인(glass) + 하향 화살표(solid)
    sellBias: {
        solid: (a) => (
            <g fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round">
                <line x1={36} y1={18} x2={36} y2={30} />
                <polyline points="31,25 36,30.5 41,25" />
            </g>
        ),
        glass: COIN,
    },
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicGlassIcon(props: Props) {
    const { icon, size, dark, anim } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

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

    const isDark = onCanvas ? !!dark : themeDark
    const a = isDark ? ACCENT_DARK : ACCENT_LIGHT
    const gl = isDark ? GLASS_DARK : GLASS_LIGHT

    const def = ICONS[icon] || ICONS.desire
    const S = size || 48
    // 인스턴스 중복 배치 시 defs id 충돌 방지 — 아이콘 키 포함 (동일 키 중복 = 동일 정의라 무해)
    const fid = "gbf-" + icon
    const cid = "gbc-" + icon

    // 애니메이션 — pop(등장 스프링) / float(둥실 루프) / both / none. 재생 = icon·테마 전환 시 key 재마운트.
    const mode = anim || "pop"
    const doPop = mode === "pop" || mode === "both"
    const doFloat = mode === "float" || mode === "both"
    return (
        <svg width={S} height={S} viewBox="0 0 48 48" fill="none"
            style={{ display: "block", overflow: "visible", animation: doFloat && !onCanvas ? "pgiFloat 3.4s ease-in-out infinite" : undefined }}>
            <style>{`
                .pgiS{animation:pgiPop .5s cubic-bezier(.34,1.6,.64,1) both;transform-box:fill-box;transform-origin:center}
                .pgiG{animation:pgiRise .45s ease-out both}
                @keyframes pgiPop{0%{transform:scale(.45) rotate(-10deg);opacity:0}100%{transform:scale(1) rotate(0deg);opacity:1}}
                @keyframes pgiRise{0%{transform:translateY(5px);opacity:0}100%{transform:translateY(0);opacity:1}}
                @keyframes pgiFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-2.5px)}}
                @media (prefers-reduced-motion: reduce){.pgiS,.pgiG{animation:none}svg{animation:none!important}}
            `}</style>
            <defs>
                <filter id={fid} x="-40%" y="-40%" width="180%" height="180%">
                    <feGaussianBlur stdDeviation="2.1" />
                </filter>
                <clipPath id={cid}>
                    <path d={def.glass} />
                </clipPath>
            </defs>
            {/* 선명 레이어 */}
            <g key={"s" + icon + a} className={doPop ? "pgiS" : undefined}>{def.solid(a)}</g>
            {/* 글래스 영역 — 겹치는 solid 는 블러 복제 + 반투명 틴트 (프로스트) */}
            <g key={"g" + icon + a} className={doPop ? "pgiG" : undefined}>
                <g clipPath={`url(#${cid})`}>
                    <g filter={`url(#${fid})`} opacity={0.85}>{def.solid(a)}</g>
                    <path d={def.glass} fill={gl} />
                </g>
            </g>
        </svg>
    )
}

addPropertyControls(PublicGlassIcon, {
    icon: {
        type: ControlType.Enum,
        title: "Icon",
        defaultValue: "desire",
        options: [
            "desire", "survival", "safety", "belonging", "esteem", "selfActual", "infra",
            "revStable", "volLow", "volMid", "volHigh",
            "treasury", "buySteady", "buySome", "sellBias",
        ],
        optionTitles: [
            "욕구", "생존/심리", "안전", "소속/연결", "존중/과시", "자아실현", "기반/인프라",
            "매출 안정성", "흔들림 작음", "흔들림 중간", "흔들림 큼",
            "자사주", "꾸준한 매입", "매입 있음", "처분 우위",
        ],
    },
    size: { type: ControlType.Number, title: "Size", defaultValue: 48, min: 16, max: 200, step: 2 },
    anim: {
        type: ControlType.Enum,
        title: "Anim",
        defaultValue: "pop",
        options: ["pop", "float", "both", "none"],
        optionTitles: ["등장 팝", "둥실", "팝+둥실", "없음"],
    },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

import { addPropertyControls, ControlType } from "framer"
import type { CSSProperties } from "react"

/**
 * AlphaNest 마크 — 보라 타원(머리) + 네이비 U 아크(어깨).
 * Framer에 붙여넣어 로고·아바타·파비콘 대체 등에 사용.
 */

const HEAD = "#7B61FF"
const ARC = "#3F476C"
const BG = "#000000"

interface Props {
    size: number
    headColor: string
    arcColor: string
    background: string
    showBackground: boolean
}

function MarkSvg(props: {
    size: number
    headColor: string
    arcColor: string
    background: string
    showBackground: boolean
}) {
    const { size, headColor, arcColor, background, showBackground } = props

    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 100 100"
            fill="none"
            aria-hidden="true"
            style={{ display: "block" }}
        >
            {showBackground ? (
                <rect width="100" height="100" fill={background} />
            ) : null}
            <ellipse cx="50" cy="36" rx="18" ry="24" fill={headColor} />
            <path
                d="M 20 52 Q 20 84 50 84 Q 80 84 80 52"
                stroke={arcColor}
                strokeWidth="14"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    )
}

export default function AlphaNestMark(props: Partial<Props>) {
    const {
        size = 48,
        headColor = HEAD,
        arcColor = ARC,
        background = BG,
        showBackground = true,
    } = props

    const wrap: CSSProperties = {
        width: size,
        height: size,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        lineHeight: 0,
    }

    return (
        <div style={wrap}>
            <MarkSvg
                size={size}
                headColor={headColor}
                arcColor={arcColor}
                background={background}
                showBackground={showBackground}
            />
        </div>
    )
}

AlphaNestMark.defaultProps = {
    size: 48,
    headColor: HEAD,
    arcColor: ARC,
    background: BG,
    showBackground: true,
}

addPropertyControls(AlphaNestMark, {
    size: {
        type: ControlType.Number,
        title: "Size",
        min: 16,
        max: 256,
        step: 1,
        defaultValue: 48,
    },
    headColor: {
        type: ControlType.Color,
        title: "Head",
        defaultValue: HEAD,
    },
    arcColor: {
        type: ControlType.Color,
        title: "Arc",
        defaultValue: ARC,
    },
    background: {
        type: ControlType.Color,
        title: "Background",
        defaultValue: BG,
        hidden: (props) => !props.showBackground,
    },
    showBackground: {
        type: ControlType.Boolean,
        title: "Show BG",
        defaultValue: true,
    },
})

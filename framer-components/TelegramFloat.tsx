import { useState } from "react"
import { addPropertyControls, ControlType } from "framer"

interface Props {
    botUsername: string
    label: string
}

export default function TelegramFloat(props: Props) {
    const { botUsername, label } = props
    const [hovered, setHovered] = useState(false)
    const [showTooltip, setShowTooltip] = useState(true)

    const url = `https://t.me/${botUsername}`

    return (
        <div style={styles.wrapper}>
            {/* 툴팁 */}
            {(showTooltip || hovered) && (
                <div
                    style={{
                        ...styles.tooltip,
                        opacity: hovered ? 1 : 0.9,
                        transform: hovered ? "translateY(0)" : "translateY(4px)",
                    }}
                    onClick={() => setShowTooltip(false)}
                >
                    <span style={styles.tooltipText}>{label}</span>
                    <div style={styles.tooltipArrow} />
                </div>
            )}

            {/* 플로팅 버튼 */}
            <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                    ...styles.button,
                    transform: hovered ? "scale(1.08)" : "scale(1)",
                    boxShadow: hovered
                        ? "0 8px 32px rgba(181,255,25,0.3), 0 0 0 2px rgba(181,255,25,0.15)"
                        : "0 4px 20px rgba(0,0,0,0.4)",
                }}
                onMouseEnter={() => setHovered(true)}
                onMouseLeave={() => setHovered(false)}
                onClick={() => setShowTooltip(false)}
            >
                {/* 텔레그램 아이콘 */}
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
                    <path
                        d="M20.665 3.717l-17.73 6.837c-1.21.486-1.203 1.161-.222 1.462l4.552 1.42 10.532-6.645c.498-.303.953-.14.579.192l-8.533 7.701h-.002l.002.001-.314 4.692c.46 0 .663-.211.921-.46l2.211-2.15 4.599 3.397c.848.467 1.457.227 1.668-.785l3.019-14.228c.309-1.239-.473-1.8-1.282-1.434z"
                        fill="#B5FF19"
                    />
                </svg>
            </a>
        </div>
    )
}

TelegramFloat.defaultProps = {
    botUsername: "verity_stock_bot",
    label: "비서에게 물어보기",
}

addPropertyControls(TelegramFloat, {
    botUsername: {
        type: ControlType.String,
        title: "봇 Username",
        defaultValue: "verity_stock_bot",
    },
    label: {
        type: ControlType.String,
        title: "툴팁 문구",
        defaultValue: "비서에게 물어보기",
    },
})

const styles: Record<string, React.CSSProperties> = {
    wrapper: {
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-end",
        gap: 8,
        fontFamily: "'Inter', 'Pretendard', -apple-system, sans-serif",
    },
    tooltip: {
        position: "relative",
        background: "#111",
        border: "1px solid #222",
        borderRadius: 10,
        padding: "8px 14px",
        transition: "all 0.2s ease",
        cursor: "pointer",
    },
    tooltipText: {
        color: "#ccc",
        fontSize: 12,
        fontWeight: 600,
        whiteSpace: "nowrap",
    },
    tooltipArrow: {
        position: "absolute",
        bottom: -5,
        right: 22,
        width: 10,
        height: 10,
        background: "#111",
        border: "1px solid #222",
        borderTop: "none",
        borderLeft: "none",
        transform: "rotate(45deg)",
    },
    button: {
        width: 56,
        height: 56,
        borderRadius: 28,
        background: "#111",
        border: "1px solid #222",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        textDecoration: "none",
        transition: "all 0.25s ease",
        cursor: "pointer",
    },
}

import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

// Framer에서 Fixed 레이아웃으로 크기를 지정하면 그 크기를 100% 채웁니다.
// Vercel Authentication을 끈 상태에서 정상 동작합니다.

interface Props {
    mapUrl: string
    borderRadius: number
    showHeader: boolean
}

export default function GlobalMapEmbed(props: Props) {
    const { mapUrl, borderRadius, showHeader } = props
    const [clientReady, setClientReady] = useState(false)
    const [loaded, setLoaded] = useState(false)
    const [timedOut, setTimedOut] = useState(false)

    useEffect(() => {
        setClientReady(true)
    }, [])

    useEffect(() => {
        if (!clientReady) return
        setLoaded(false)
        setTimedOut(false)
        const t = window.setTimeout(() => setTimedOut(true), 15000)
        return () => window.clearTimeout(t)
    }, [mapUrl, clientReady])

    return (
        <div
            style={{
                ...container,
                borderRadius,
            }}
        >
            {showHeader && (
                <div style={header}>
                    <span style={titleText}>글로벌 마켓 맵</span>
                    <a
                        href={mapUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={expandLink}
                    >
                        새 창에서 열기 →
                    </a>
                </div>
            )}
            <div
                style={{
                    position: "relative",
                    width: "100%",
                    flex: 1,
                    overflow: "hidden",
                    borderRadius: showHeader
                        ? `0 0 ${borderRadius}px ${borderRadius}px`
                        : borderRadius,
                    background: "#0a0a0a",
                }}
            >
                {!clientReady && (
                    <div style={ssrPlaceholder}>
                        <span style={loadingText}>불러오는 중…</span>
                        <span style={fallbackText}>지도를 불러오고 있습니다.</span>
                        <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={fallbackBtn}>
                            새 창에서 지도 열기
                        </a>
                    </div>
                )}
                {clientReady && (
                    <>
                        <iframe
                            key={mapUrl}
                            title="VERITY Global Map"
                            src={mapUrl}
                            onLoad={() => setLoaded(true)}
                            referrerPolicy="no-referrer-when-downgrade"
                            style={{
                                position: "absolute",
                                top: 0,
                                left: 0,
                                width: "100%",
                                height: "100%",
                                border: "none",
                                display: "block",
                                zIndex: 1,
                            }}
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
                            loading="eager"
                        />
                        {!loaded && (
                            <div style={loadingOverlay}>
                                <span style={loadingText}>지도 로딩 중…</span>
                                {timedOut && (
                                    <div style={fallbackBox}>
                                        <span style={fallbackText}>
                                            15초 이상 로딩 중입니다. Vercel 프로젝트의 Authentication이 꺼져 있는지 확인하세요.
                                        </span>
                                        <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={fallbackBtn}>
                                            새 창에서 지도 열기
                                        </a>
                                    </div>
                                )}
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    )
}

const DEFAULT_MAP_URL = "https://map-page-l9qxa0n9c-kim-hyojuns-projects.vercel.app"

GlobalMapEmbed.defaultProps = {
    mapUrl: DEFAULT_MAP_URL,
    borderRadius: 16,
    showHeader: true,
}

addPropertyControls(GlobalMapEmbed, {
    mapUrl: {
        type: ControlType.String,
        title: "맵 URL",
        defaultValue: DEFAULT_MAP_URL,
    },
    borderRadius: {
        type: ControlType.Number,
        title: "모서리 곡률",
        defaultValue: 16,
        min: 0,
        max: 32,
        step: 2,
    },
    showHeader: {
        type: ControlType.Boolean,
        title: "헤더 표시",
        defaultValue: true,
    },
})

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const container: React.CSSProperties = {
    width: "100%",
    height: "100%",
    background: "#111",
    border: "1px solid #222",
    overflow: "hidden",
    fontFamily: font,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
}

const header: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 16px",
    borderBottom: "1px solid #222",
    flexShrink: 0,
}

const titleText: React.CSSProperties = {
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
    fontFamily: font,
}

const expandLink: React.CSSProperties = {
    color: "#B5FF19",
    fontSize: 11,
    fontWeight: 600,
    textDecoration: "none",
    fontFamily: font,
}

const loadingOverlay: React.CSSProperties = {
    position: "absolute",
    inset: 0,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    background: "rgba(10,10,10,0.92)",
    zIndex: 20,
    pointerEvents: "auto",
}

const loadingText: React.CSSProperties = {
    color: "#B5FF19",
    fontSize: 13,
    fontWeight: 600,
    fontFamily: font,
}

const fallbackBox: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 10,
    maxWidth: 280,
    textAlign: "center",
    padding: "0 12px",
}

const fallbackText: React.CSSProperties = {
    color: "#888",
    fontSize: 11,
    lineHeight: 1.5,
    fontFamily: font,
}

const fallbackBtn: React.CSSProperties = {
    color: "#000",
    background: "#B5FF19",
    fontSize: 12,
    fontWeight: 700,
    padding: "8px 14px",
    borderRadius: 8,
    textDecoration: "none",
    fontFamily: font,
}

const ssrPlaceholder: React.CSSProperties = {
    position: "absolute",
    inset: 0,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 14,
    padding: 20,
    zIndex: 5,
    textAlign: "center",
}

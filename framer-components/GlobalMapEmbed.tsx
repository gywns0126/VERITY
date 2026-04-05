import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

// map-page 연동: 저장소의 map-page/를 Vercel(또는 정적 호스팅)에 배포한 뒤, 아래 mapUrl에 그 HTTPS 주소를 넣습니다.
// 예) Vercel에서 Root Directory를 map-page로 지정 → 배포 URL을 Framer 속성「맵 URL」에 붙여넣기.
// 로컬만 테스트할 때는 map-page에서 npx serve . 후 http://127.0.0.1:포트 (Framer 클라우드 미리보기에서는 로컬 URL이 막힐 수 있음).

interface Props {
    mapUrl: string
    height: number
    borderRadius: number
    showHeader: boolean
}

export default function GlobalMapEmbed(props: Props) {
    const { mapUrl, height, borderRadius, showHeader } = props
    const [loaded, setLoaded] = useState(false)
    const [timedOut, setTimedOut] = useState(false)

    useEffect(() => {
        setLoaded(false)
        setTimedOut(false)
        const t = window.setTimeout(() => setTimedOut(true), 10000)
        return () => window.clearTimeout(t)
    }, [mapUrl])

    const headerH = showHeader ? 46 : 0
    const minTotal = headerH + height

    return (
        <div style={{ ...container, borderRadius, minHeight: minTotal }}>
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
                    height,
                    minHeight: height,
                    overflow: "hidden",
                    borderRadius: showHeader ? `0 0 ${borderRadius}px ${borderRadius}px` : borderRadius,
                }}
            >
                <iframe
                    title="VERITY Global Map"
                    src={mapUrl}
                    onLoad={() => setLoaded(true)}
                    referrerPolicy="no-referrer-when-downgrade"
                    style={{
                        position: "relative",
                        zIndex: 1,
                        width: "100%",
                        height: "100%",
                        border: "none",
                        display: "block",
                    }}
                    allow="fullscreen"
                />
                {!loaded && (
                    <div style={loadingOverlay}>
                        <span style={loadingText}>지도 로딩 중...</span>
                        {timedOut && (
                            <div style={fallbackBox}>
                                <span style={fallbackText}>
                                    편집기에서 iframe이 비어 보일 수 있습니다. Vercel에 map-page를 다시 배포한 뒤(CSP 헤더) 게시 페이지에서 확인하거나 아래를 눌러 주세요.
                                </span>
                                <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={fallbackBtn}>
                                    새 창에서 지도 열기
                                </a>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    )
}

GlobalMapEmbed.defaultProps = {
    mapUrl: "https://verity-map.vercel.app",
    height: 500,
    borderRadius: 16,
    showHeader: true,
}

addPropertyControls(GlobalMapEmbed, {
    mapUrl: {
        type: ControlType.String,
        title: "맵 URL",
        defaultValue: "https://verity-map.vercel.app",
    },
    height: {
        type: ControlType.Number,
        title: "높이(px)",
        defaultValue: 500,
        min: 200,
        max: 1200,
        step: 10,
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
    background: "#111",
    border: "1px solid #222",
    overflow: "hidden",
    fontFamily: font,
}

const header: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 16px",
    borderBottom: "1px solid #222",
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

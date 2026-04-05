import { addPropertyControls, ControlType } from "framer"
import { useState } from "react"

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

    return (
        <div style={{ ...container, borderRadius }}>
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
            <div style={{ position: "relative", width: "100%", height, overflow: "hidden", borderRadius: showHeader ? `0 0 ${borderRadius}px ${borderRadius}px` : borderRadius }}>
                {!loaded && (
                    <div style={loadingOverlay}>
                        <span style={loadingText}>지도 로딩 중...</span>
                    </div>
                )}
                <iframe
                    src={mapUrl}
                    onLoad={() => setLoaded(true)}
                    style={{
                        width: "100%",
                        height: "100%",
                        border: "none",
                        display: "block",
                    }}
                    allow="fullscreen"
                />
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
    alignItems: "center",
    justifyContent: "center",
    background: "#0a0a0a",
    zIndex: 1,
}

const loadingText: React.CSSProperties = {
    color: "#555",
    fontSize: 13,
    fontFamily: font,
}

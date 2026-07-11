import { addPropertyControls, ControlType } from "framer"
import { useState, useEffect } from "react"

/**
 * AlphaNestLiveEmbed
 *
 * 디바이스 목업 "스크린 안"에 넣는 라이브 임베드 창.
 * - 목업 프레임(아이맥/아이폰)은 Framer 네이티브 or 에셋으로 사용자가 배치.
 * - 이 컴포넌트는 그 스크린 영역에 얹어 실사이트(www.alphanest.kr)를 구동.
 *
 * 모드:
 * - lazy (권장, 기본): 포스터 + "직접 해보기" 버튼 → 탭할 때 iframe 로드. 랜딩 LCP 보호.
 * - eager: 마운트 즉시 iframe 로드.
 *
 * Framer 사용: 레이어 크기를 목업 스크린 크기에 맞춰 고정(iframe = 부모 100%, 고정높이 caveat 대응).
 *
 * @framerSupportedLayoutWidth any-prefer-fixed
 * @framerSupportedLayoutHeight any-prefer-fixed
 */
export default function AlphaNestLiveEmbed(props) {
    const {
        url,
        mode,
        showChrome,
        radius,
        posterBg,
        accent,
        ctaLabel,
        caption,
    } = props

    const [active, setActive] = useState(mode === "eager")
    const [loaded, setLoaded] = useState(false)

    // 캔버스에서 prop(mode/url) 토글 시 상태 동기화
    useEffect(() => {
        setActive(mode === "eager")
        setLoaded(false)
    }, [mode, url])

    const container = {
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        borderRadius: radius,
        background: "#ffffff",
        display: "flex",
        flexDirection: "column",
        fontFamily:
            '"Apple SD Gothic Neo", -apple-system, "Segoe UI", sans-serif',
    }

    const chromeBar = {
        display: "flex",
        alignItems: "center",
        gap: 8,
        height: 34,
        flex: "0 0 34px",
        background: "#111119",
        padding: "0 12px",
    }
    const dots = { display: "flex", gap: 6 }
    const dot = (c) => ({
        width: 11,
        height: 11,
        borderRadius: "50%",
        background: c,
    })
    const pill = {
        flex: 1,
        height: 22,
        background: "#23232e",
        borderRadius: 6,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#b9b6c8",
        fontSize: 12,
        letterSpacing: 0.2,
    }
    const liveTag = {
        display: "flex",
        alignItems: "center",
        gap: 5,
        fontSize: 11,
        color: "#7cf2a8",
    }
    const liveBlink = {
        width: 7,
        height: 7,
        borderRadius: "50%",
        background: "#28c840",
        boxShadow: "0 0 8px #28c840",
    }

    const screen = {
        position: "relative",
        flex: 1,
        width: "100%",
        background: "#ffffff",
    }
    const iframeStyle = {
        width: "100%",
        height: "100%",
        border: "0",
        display: "block",
    }

    const overlay = {
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 14,
        background: "#ffffff",
    }
    const spinner = {
        width: 34,
        height: 34,
        borderRadius: "50%",
        border: "3px solid #eeeeee",
        borderTopColor: accent,
        animation: "alphanest_spin 0.8s linear infinite",
    }

    const poster = {
        position: "absolute",
        inset: 0,
        border: "0",
        cursor: "pointer",
        background: posterBg,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 14,
        color: "#ffffff",
        fontFamily: "inherit",
    }
    const playRing = {
        width: 64,
        height: 64,
        borderRadius: "50%",
        background: "rgba(255,255,255,0.16)",
        border: "1px solid rgba(255,255,255,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
    }
    const playTri = {
        width: 0,
        height: 0,
        borderTop: "11px solid transparent",
        borderBottom: "11px solid transparent",
        borderLeft: "18px solid #ffffff",
        marginLeft: 5,
    }
    const ctaText = { fontSize: 16, fontWeight: 600, letterSpacing: -0.2 }
    const capText = { fontSize: 12, opacity: 0.72 }

    return (
        <div style={container}>
            <style>{"@keyframes alphanest_spin{to{transform:rotate(360deg)}}@keyframes alphanest_blink{0%,100%{opacity:1}50%{opacity:.35}}"}</style>

            {showChrome ? (
                <div style={chromeBar}>
                    <div style={dots}>
                        <span style={dot("#ff5f57")} />
                        <span style={dot("#febc2e")} />
                        <span style={dot("#28c840")} />
                    </div>
                    <div style={pill}>{prettyHost(url)}</div>
                    <div style={liveTag}>
                        <span
                            style={{
                                ...liveBlink,
                                animation: "alphanest_blink 1.6s infinite",
                            }}
                        />
                        LIVE
                    </div>
                </div>
            ) : null}

            <div style={screen}>
                {active ? (
                    <>
                        {!loaded ? (
                            <div style={overlay}>
                                <div style={spinner} />
                                <div style={{ color: "#9a95b5", fontSize: 14 }}>
                                    실시간 사이트 불러오는 중…
                                </div>
                            </div>
                        ) : null}
                        <iframe
                            src={url}
                            title="AlphaNest live"
                            style={iframeStyle}
                            onLoad={() => setLoaded(true)}
                            referrerPolicy="no-referrer-when-downgrade"
                            loading="eager"
                        />
                    </>
                ) : (
                    <button
                        type="button"
                        style={poster}
                        onClick={() => setActive(true)}
                    >
                        <div style={playRing}>
                            <div style={playTri} />
                        </div>
                        <div style={ctaText}>{ctaLabel}</div>
                        {caption ? <div style={capText}>{caption}</div> : null}
                    </button>
                )}
            </div>
        </div>
    )
}

function prettyHost(u) {
    try {
        const h = String(u).replace(/^https?:\/\//, "").replace(/\/.*$/, "")
        return h
    } catch (e) {
        return u
    }
}

AlphaNestLiveEmbed.defaultProps = {
    url: "https://www.alphanest.kr/",
    mode: "lazy",
    showChrome: true,
    radius: 0,
    posterBg:
        "linear-gradient(135deg, #6c5ce7 0%, #4a3aa8 100%)",
    accent: "#6c5ce7",
    ctaLabel: "직접 해보기",
    caption: "실제 사이트가 이 안에서 구동됩니다",
}

addPropertyControls(AlphaNestLiveEmbed, {
    url: {
        type: ControlType.String,
        title: "URL",
        defaultValue: "https://www.alphanest.kr/",
    },
    mode: {
        type: ControlType.Enum,
        title: "모드",
        options: ["lazy", "eager"],
        optionTitles: ["탭하면 라이브(권장)", "즉시 로드"],
        defaultValue: "lazy",
        displaySegmentedControl: true,
    },
    showChrome: {
        type: ControlType.Boolean,
        title: "URL 바",
        defaultValue: true,
    },
    radius: {
        type: ControlType.Number,
        title: "모서리",
        min: 0,
        max: 40,
        defaultValue: 0,
    },
    posterBg: {
        type: ControlType.String,
        title: "포스터 배경",
        defaultValue: "linear-gradient(135deg, #6c5ce7 0%, #4a3aa8 100%)",
    },
    accent: {
        type: ControlType.Color,
        title: "액센트",
        defaultValue: "#6c5ce7",
    },
    ctaLabel: {
        type: ControlType.String,
        title: "버튼 문구",
        defaultValue: "직접 해보기",
    },
    caption: {
        type: ControlType.String,
        title: "포스터 캡션",
        defaultValue: "실제 사이트가 이 안에서 구동됩니다",
    },
})

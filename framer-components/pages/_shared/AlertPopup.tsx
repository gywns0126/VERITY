// AlertPopup — 고영향 이벤트 긴급 팝업 (오퍼레이터 전역 오버레이).
// PM 예시: "하이닉스 최태원 회장 매수 정보를 늦게 들음 → 긴급 팝업으로".
// 데이터 = data/urgent_alerts.json (urgent_alerts_builder, 공시 사실 랭킹). RULE 7 = 사실만, 점수/예측 0.
// 되돌리지 말 것: 이 컴포넌트는 공개 blob(사실)만 읽음. 크라운주얼/인증데이터 절대 fetch 금지.
import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', system-ui, sans-serif"
const SEEN_KEY = "verity_urgent_seen"

// 한국 관행: 매수/상승 = 빨강, 매도/하락 = 파랑. 공시 = 브랜드 보라.
const C_BUY = "#f04452"
const C_SELL = "#3182f6"
const C_DISC = "#6c5ce7"

// 캔버스/미리보기용 샘플 (실데이터 검산본 — 최태원 47.9억 정합).
const SAMPLE = {
    alerts: [
        {
            ticker: "000660",
            name: "SK하이닉스",
            type: "insider_buy",
            headline: "최태원 회장 3,620주 매수 (약 47.9억)",
            date: "2026-07-31",
            source_url: "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260731000082",
        },
        {
            ticker: "082740",
            name: "한화엔진",
            type: "insider_buy",
            headline: "국민연금공단 8,398,911주 매수 (약 3300.8억)",
            date: "2026-07-31",
            source_url: "https://dart.fss.or.kr/dsaf001/main.do",
        },
        {
            ticker: "042660",
            name: "한화오션",
            type: "disclosure",
            headline: "단일판매ㆍ공급계약체결",
            severity: 3,
            date: "2026-07-31",
            source_url: "https://dart.fss.or.kr/dsaf001/main.do",
        },
    ],
}

function readBodyDark() {
    if (typeof document === "undefined") return false
    try {
        var attr = document.documentElement.getAttribute("data-theme")
        if (attr === "dark") return true
        if (attr === "light") return false
        var t = localStorage.getItem("verity_theme")
        if (t === "dark") return true
        if (t === "light") return false
        if (window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {
        return false
    }
    return false
}

function alertKey(a) {
    return String(a.source_url || "") + "|" + String(a.headline || "")
}

function accentFor(type) {
    if (type === "insider_buy") return C_BUY
    if (type === "insider_sell") return C_SELL
    return C_DISC
}

function tagFor(type) {
    if (type === "insider_buy") return "임원·대주주 매수"
    if (type === "insider_sell") return "임원·대주주 매도"
    return "긴급 공시"
}

// 인라인 SVG (npm import 회피 — Framer typecheck 안전).
function IconBell(props) {
    return (
        <svg width="15" height="15" viewBox="0 0 256 256" fill={props.color} aria-hidden="true">
            <path d="M221.8 175.9C216.3 166.4 208 139.5 208 104a80 80 0 1 0-160 0c0 35.5-8.3 62.4-13.8 71.9A16 16 0 0 0 48 200h40.8a40 40 0 0 0 78.4 0H208a16 16 0 0 0 13.8-24.1ZM128 216a24 24 0 0 1-22.6-16h45.2A24 24 0 0 1 128 216Z" />
        </svg>
    )
}

/**
 * @framerSupportedLayoutWidth auto
 * @framerSupportedLayoutHeight auto
 */
export default function AlertPopup(props) {
    var maxVisible = props && props.maxVisible ? props.maxVisible : 3
    var position = props && props.position ? props.position : "bottom-right"

    var isCanvas = RenderTarget.current() === RenderTarget.canvas
    var stateInit = []
    var alertsState = useState(stateInit)
    var alerts = alertsState[0]
    var setAlerts = alertsState[1]

    var dismissedState = useState({})
    var dismissed = dismissedState[0]
    var setDismissed = dismissedState[1]

    var darkState = useState(false)
    var dark = darkState[0]
    var setDark = darkState[1]

    useEffect(function () {
        setDark(readBodyDark())
    }, [])

    useEffect(
        function () {
            if (isCanvas) {
                setAlerts(SAMPLE.alerts)
                return
            }
            var seen = {}
            try {
                var raw = localStorage.getItem(SEEN_KEY)
                if (raw) seen = JSON.parse(raw) || {}
            } catch (e) {
                seen = {}
            }
            setDismissed(seen)
            var cancelled = false
            fetch(BLOB + "/urgent_alerts.json")
                .then(function (r) {
                    if (!r.ok) throw new Error("no feed")
                    return r.json()
                })
                .then(function (d) {
                    if (cancelled) return
                    var list = d && d.alerts ? d.alerts : []
                    setAlerts(list)
                })
                .catch(function () {
                    if (!cancelled) setAlerts([])
                })
            return function () {
                cancelled = true
            }
        },
        [isCanvas]
    )

    function dismiss(a) {
        var key = alertKey(a)
        var next = {}
        for (var k in dismissed) next[k] = dismissed[k]
        next[key] = 1
        setDismissed(next)
        try {
            localStorage.setItem(SEEN_KEY, JSON.stringify(next))
        } catch (e) {}
    }

    var visible = []
    for (var i = 0; i < alerts.length; i++) {
        var a = alerts[i]
        if (!isCanvas && dismissed[alertKey(a)]) continue
        visible.push(a)
    }
    var shown = visible.slice(0, maxVisible)
    var extra = visible.length - shown.length

    if (shown.length === 0) {
        // 라이브에서 알림 없음 = 아무것도 렌더 안 함(오버레이 투명). 캔버스는 위에서 샘플 채움.
        return <div style={{ width: 1, height: 1 }} />
    }

    var bg = dark ? "#17171c" : "#ffffff"
    var fg = dark ? "#f2f2f5" : "#1a1a1e"
    var sub = dark ? "#9a9aa5" : "#8a8a94"
    var border = dark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.06)"
    var shadow = dark
        ? "0 8px 30px rgba(0,0,0,0.5)"
        : "0 8px 30px rgba(0,0,0,0.14)"

    var wrapStyle = {
        fontFamily: FONT,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        width: "100%",
        maxWidth: 380,
    }
    if (!isCanvas) {
        wrapStyle.position = "fixed"
        wrapStyle.zIndex = 99999
        wrapStyle.bottom = position === "top-right" ? "auto" : 20
        wrapStyle.top = position === "top-right" ? 20 : "auto"
        wrapStyle.right = 20
    }

    return (
        <div style={wrapStyle}>
            {shown.map(function (a, idx) {
                var accent = accentFor(a.type)
                return (
                    <div
                        key={alertKey(a) + idx}
                        style={{
                            background: bg,
                            borderRadius: 16,
                            border: "1px solid " + border,
                            borderLeft: "3px solid " + accent,
                            boxShadow: shadow,
                            padding: "14px 15px",
                            display: "flex",
                            flexDirection: "column",
                            gap: 7,
                        }}
                    >
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 6,
                                justifyContent: "space-between",
                            }}
                        >
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 6,
                                }}
                            >
                                <IconBell color={accent} />
                                <span
                                    style={{
                                        fontSize: 11,
                                        fontWeight: 700,
                                        color: accent,
                                        letterSpacing: "-0.01em",
                                    }}
                                >
                                    {tagFor(a.type)}
                                </span>
                            </div>
                            <button
                                onClick={function () {
                                    dismiss(a)
                                }}
                                style={{
                                    border: "none",
                                    background: "transparent",
                                    color: sub,
                                    fontSize: 16,
                                    lineHeight: 1,
                                    cursor: "pointer",
                                    padding: 2,
                                }}
                                aria-label="닫기"
                            >
                                ×
                            </button>
                        </div>

                        <div
                            style={{
                                fontSize: 15,
                                fontWeight: 700,
                                color: fg,
                                letterSpacing: "-0.02em",
                            }}
                        >
                            {a.name}
                        </div>
                        <div
                            style={{
                                fontSize: 13,
                                fontWeight: 500,
                                color: fg,
                                lineHeight: 1.45,
                            }}
                        >
                            {a.headline}
                        </div>

                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                marginTop: 2,
                            }}
                        >
                            <span style={{ fontSize: 11, color: sub }}>
                                {a.date} · 공시 사실
                            </span>
                            {a.source_url ? (
                                <a
                                    href={a.source_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{
                                        fontSize: 11,
                                        fontWeight: 600,
                                        color: accent,
                                        textDecoration: "none",
                                    }}
                                >
                                    DART 원문 →
                                </a>
                            ) : null}
                        </div>
                    </div>
                )
            })}

            {extra > 0 ? (
                <div
                    style={{
                        fontSize: 11,
                        color: sub,
                        textAlign: "center",
                        fontFamily: FONT,
                    }}
                >
                    외 {extra}건 더
                </div>
            ) : null}
        </div>
    )
}

addPropertyControls(AlertPopup, {
    maxVisible: {
        type: ControlType.Number,
        title: "최대 표시",
        defaultValue: 3,
        min: 1,
        max: 6,
        step: 1,
        displayStepper: true,
    },
    position: {
        type: ControlType.Enum,
        title: "위치",
        options: ["bottom-right", "top-right"],
        optionTitles: ["우하단", "우상단"],
        defaultValue: "bottom-right",
    },
})

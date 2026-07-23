import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * 장 세션 태그 — VERITY 공개 터미널. 컴팩트 칩(네브바/우하단 배치용, auto-size).
 *
 * 한국 증시 세션 클라이언트 판정: 휴장 / 장전 / 장중 / 장후(시간외) / 장 마감.
 *  · 장전        ~ 09:00 전 (장전 동시호가 08:30–09:00 포함)
 *  · 장중        09:00–15:30 (정규장)
 *  · 장후·시간외 15:30–18:00 (장마감 후 시간외종가 + 시간외 단일가)
 *  · 장 마감     18:00 이후 ~ 자정
 *  · 휴장        주말·공휴일 (공휴일은 구체 명칭 표시)
 * 라이브 점(ping) = 장중·장후. KST 시계 + 카운트다운. RULE 7 = 거래소 운영시간 사실만, 자체 판단 0.
 * 🚨 공휴일 = 시점 의존 → holidays prop(휴장 판정). 명칭은 HOLIDAY_NAMES 정적 매핑(없으면 "공휴일"). 웹검증 2026-06-20.
 * 🚨 위치는 prop 미지정(Framer position:fixed 하드코딩 금지) — auto-size 칩, PM이 네브바/코너에 배치.
 * 테마: Framer 네이티브 추종 — body[data-framer-theme] 읽어 dark 전환(캔버스는 dark prop 정적 프리뷰).
 */

const LIGHT = {
    ink: "#191f28",
    sub: "#6b7684",
    chip: "#f2f4f6",
    bd: "#e5e8eb",
    open: "#15c47e",
    pre: "#ff9500",
    after: "#6c5ce7",
    closed: "#8b95a1",
    holiday: "#f04452",
}
const DARK = {
    ink: "#e3e7ec",
    sub: "#9aa4b1",
    chip: "#1e242c",
    bd: "#2d343d",
    open: "#34e08a",
    pre: "#ffb454",
    after: "#a99bff",
    closed: "#828d9b",
    holiday: "#ff5c68",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"

// 2026 KRX 휴장(평일 — 주말 자동) · 웹검증 2026-06-20.
const DEFAULT_HOLIDAYS =
    "2026-01-01,2026-02-16,2026-02-17,2026-02-18,2026-03-02,2026-05-01,2026-05-05,2026-05-25,2026-08-17,2026-09-24,2026-09-25,2026-10-05,2026-10-09,2026-12-25,2026-12-31"
// 휴장 사유 명칭 (date → 명칭). holidays prop 에 있어도 여기 없으면 "공휴일".
const HOLIDAY_NAMES: Record<string, string> = {
    "2026-01-01": "신정",
    "2026-02-16": "설날 연휴",
    "2026-02-17": "설날",
    "2026-02-18": "설날 연휴",
    "2026-03-02": "삼일절 대체",
    "2026-05-01": "근로자의날",
    "2026-05-05": "어린이날",
    "2026-05-25": "부처님오신날 대체",
    "2026-08-17": "광복절 대체",
    "2026-09-24": "추석 연휴",
    "2026-09-25": "추석",
    "2026-10-05": "개천절 대체",
    "2026-10-09": "한글날",
    "2026-12-25": "성탄절",
    "2026-12-31": "연말 휴장",
}

interface Props {
    dark: boolean
    holidays: string
    showClock: boolean
    showSub: boolean
    style?: CSSProperties
}

function kstNow(): Date {
    const d = new Date()
    return new Date(d.getTime() + (d.getTimezoneOffset() + 540) * 60000)
}
function ymd(k: Date): string {
    return `${k.getFullYear()}-${String(k.getMonth() + 1).padStart(2, "0")}-${String(k.getDate()).padStart(2, "0")}`
}
function pad2(n: number): string {
    return String(n).padStart(2, "0")
}
function hm(mins: number): string {
    return `${Math.floor(mins / 60)}:${pad2(mins % 60)}`
}

/**
 * @framerSupportedLayoutWidth auto
 * @framerSupportedLayoutHeight auto
 */
export default function PublicSessionTag(props: Props) {
    const { dark, holidays, showClock, showSub, style } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    /* 테마 추종: html[data-an-theme] 먼저(헤드 스크립트 pre-paint) → body[data-framer-theme] → verity_theme.
       🚨 body-first 금지 — 새로고침에 body 가 light 로 리셋돼도 html/verity 로 다크 유지(2026-07-23 부분 라이트 fix). 되돌리지 말 것. */
    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    useEffect(() => {
        if (onCanvas) return
        const read = () => {
            const h =
                typeof document !== "undefined" && document.documentElement
                    ? document.documentElement.dataset.anTheme
                    : ""
            const b =
                typeof document !== "undefined" && document.body
                    ? document.body.dataset.framerTheme
                    : ""
            let dk = false
            if (h === "dark") dk = true
            else if (h === "light") dk = false
            else if (b === "dark") dk = true
            else if (b === "light") dk = false
            else {
                try { dk = localStorage.getItem("verity_theme") === "dark" } catch (e) { dk = false }
            }
            setThemeDark(dk)
        }
        read()
        if (
            typeof MutationObserver === "undefined" ||
            typeof document === "undefined" ||
            !document.body
        )
            return
        const obs = new MutationObserver(read)
        obs.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-framer-theme"],
        })
        return () => obs.disconnect()
    }, [onCanvas])

    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT

    const [, setTick] = useState(0)
    useEffect(() => {
        if (onCanvas) return
        const t = setInterval(() => setTick((n) => n + 1), 1000)
        return () => clearInterval(t)
    }, [onCanvas])

    const holidaySet = useMemo(() => {
        const s = new Set<string>()
        for (const x of String(holidays || "").split(/[,\s]+/)) {
            const v = x.trim()
            if (v) s.add(v)
        }
        return s
    }, [holidays])

    const view = useMemo(() => {
        if (onCanvas)
            return {
                state: "장중",
                color: C.open,
                live: true,
                sub: "마감 1:08",
                clock: "14:22",
            }
        const k = kstNow()
        const day = k.getDay()
        const mins = k.getHours() * 60 + k.getMinutes()
        const clock = `${pad2(k.getHours())}:${pad2(k.getMinutes())}`
        const today = ymd(k)
        if (day === 0 || day === 6 || holidaySet.has(today)) {
            const reason = holidaySet.has(today)
                ? HOLIDAY_NAMES[today] || "공휴일"
                : "주말"
            return {
                state: "휴장",
                color: C.holiday,
                live: false,
                sub: reason,
                clock,
            }
        }
        if (mins < 540)
            return {
                state: "장전",
                color: C.pre,
                live: false,
                sub: `개장 ${hm(540 - mins)}`,
                clock,
            }
        if (mins < 930)
            return {
                state: "장중",
                color: C.open,
                live: true,
                sub: `마감 ${hm(930 - mins)}`,
                clock,
            }
        if (mins < 1080)
            return {
                state: "장후·시간외",
                color: C.after,
                live: true,
                sub: `종료 ${hm(1080 - mins)}`,
                clock,
            }
        return {
            state: "장 마감",
            color: C.closed,
            live: false,
            sub: "거래 종료",
            clock,
        }
    }, [onCanvas, holidaySet, C])

    const wrap: CSSProperties = {
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        borderRadius: 999,
        padding: "5px 11px",
        fontFamily: FONT,
        lineHeight: 1,
        whiteSpace: "nowrap",
        ...style,
    }

    return (
        <div style={wrap}>
            <span
                style={{
                    position: "relative",
                    display: "inline-flex",
                    width: 7,
                    height: 7,
                }}
            >
                {view.live && (
                    <span
                        style={{
                            position: "absolute",
                            inset: 0,
                            borderRadius: "50%",
                            background: view.color,
                            opacity: 0.35,
                            animation:
                                "vst-ping 1.4s cubic-bezier(0,0,0.2,1) infinite",
                        }}
                    />
                )}
                <span
                    style={{
                        position: "relative",
                        width: 7,
                        height: 7,
                        borderRadius: "50%",
                        background: view.color,
                    }}
                />
            </span>
            <span
                style={{
                    fontSize: 12,
                    fontWeight: 800,
                    color: C.ink,
                    letterSpacing: "-0.2px",
                }}
            >
                {view.state}
            </span>
            {showSub && view.sub && (
                <span style={{ fontSize: 11, fontWeight: 600, color: C.sub }}>
                    · {view.sub}
                </span>
            )}
            {showClock && (
                <span
                    style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: C.sub,
                        fontVariantNumeric: "tabular-nums",
                    }}
                >
                    {view.clock} KST
                </span>
            )}
            <style>{`@keyframes vst-ping{75%,100%{transform:scale(2.2);opacity:0}}`}</style>
        </div>
    )
}

addPropertyControls(PublicSessionTag, {
    dark: {
        type: ControlType.Boolean,
        title: "Dark",
        defaultValue: false,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
    holidays: {
        type: ControlType.String,
        title: "Holidays(2026)",
        defaultValue: DEFAULT_HOLIDAYS,
        displayTextArea: true,
    },
    showSub: {
        type: ControlType.Boolean,
        title: "Countdown·사유",
        defaultValue: true,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
    showClock: {
        type: ControlType.Boolean,
        title: "Clock",
        defaultValue: true,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
})

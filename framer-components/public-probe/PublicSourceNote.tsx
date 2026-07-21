import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * 출처·고지 노트 (공유) — VERITY 공개 터미널. 페이지당 1회 하단 배치.
 *
 * 목적 = 컴포넌트/카드마다 "자체 점수 아님 · 출처 DART" 류를 반복 첨부하던 것(난잡)을
 *   페이지 하단 단일 노트로 통합 (2026-07-04 PM 지시). 카드 밑 주저리 제거, 출처는 한 번에 정리.
 *
 * 🚨 RULE 7 경계: 여기로 옮기는 것 = "자체 분류·점수·등급 = 가설 / 추천 아님 / 출처" 일반 보일러플레이트만.
 *   숫자에 직접 붙는 통계 라벨(N=14 통계 무의미, hit rate+CI+expectancy 병기)은 각 컴포넌트 숫자 옆에 유지 —
 *   여기로 옮기면 안 됨(RULE 7 "hit rate 노출 시 병기 의무").
 *
 * 사용 = props.sources 로 그 페이지에 실제 쓰인 출처만 콤마로 명시. note 로 문구 override 가능.
 * 테마 = body[data-framer-theme] 자가감지. 토스식 소프트(무채색, 얇은 상단 구분선).
 */

const LIGHT = { bg: "#f2f4f6", ink: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", violet: "#6c5ce7" }
const DARK = { bg: "#16181d", ink: "#9aa4b1", faint: "#6b7684", line: "#2b2f37", violet: "#a99bff" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

function readBodyDark(): boolean {
    // 첫 페인트 flash 방지 — body 속성 미설정(마운트 직후) 시 토글 저장 선호(localStorage) → OS 순 폴백.
    // PublicThemeToggle 이 verity_theme 로 저장 + body[data-framer-theme] 설정 = 동일 소스라 첫 페인트부터 정합.
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

export default function PublicSourceNote(props: {
    width?: number
    sources?: string
    note?: string
    showHeld?: boolean
    dark?: boolean
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    // 첫 페인트부터 실제 테마로 시작(캔버스는 prop) — 반대색 flash 제거.
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    useEffect(() => {
        if (onCanvas) return
        setThemeDark(readBodyDark())
        const obs = new MutationObserver(() => setThemeDark(readBodyDark()))
        if (document.body) obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const sources = (props.sources || "DART 전자공시 · KRX · 금융위 공공데이터 · 네이버 금융 · SEC EDGAR").trim()
    const held = props.showHeld !== false
    const note = (props.note || "").trim()

    const wrap: CSSProperties = {
        width: props.width || "100%", maxWidth: "100%", boxSizing: "border-box",
        // 배경 = transparent: 하단 노트 스트립. 자기 bg hex 칠하면 Framer 네이티브 페이지 dark bg 와 어긋나 튐(다크 #0f1318 vs 하드코딩 #16181d). 상단 구분선만 유지.
        fontFamily: FONT, background: "transparent", color: C.ink,
        padding: "14px 16px", borderTop: `1px solid ${C.line}`,
        display: "flex", flexDirection: "column", gap: 4,
    }

    return (
        <div style={wrap}>
            <div style={{ fontSize: 11, fontWeight: 700, color: C.ink, letterSpacing: "-0.1px", lineHeight: 1.5 }}>
                출처 <span style={{ fontWeight: 600, color: C.faint }}>· {sources}</span>
            </div>
            <div style={{ fontSize: 10.5, fontWeight: 600, color: C.faint, lineHeight: 1.5 }}>
                {note || (
                    <>
                        자체 분류·점수·등급 = <span style={{ color: C.violet, fontWeight: 700 }}>가설</span>
                        {held ? " (검증 전 · 성과 원본은 게이트 도달 후 2027 공개)" : ""} · 매매 추천 아님 · 정보 제공 목적
                    </>
                )}
            </div>
        </div>
    )
}

addPropertyControls(PublicSourceNote, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    sources: { type: ControlType.String, title: "출처", defaultValue: "DART 전자공시 · KRX · 금융위 공공데이터 · 네이버 금융 · SEC EDGAR", displayTextArea: true },
    note: { type: ControlType.String, title: "문구(override)", defaultValue: "" },
    showHeld: { type: ControlType.Boolean, title: "2027 held 문구", defaultValue: true, enabledTitle: "On", disabledTitle: "Off" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

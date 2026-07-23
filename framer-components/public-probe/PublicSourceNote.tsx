import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { type CSSProperties } from "react"

/**
 * 출처·고지 노트 (공유) — VERITY 공개 터미널. 페이지당 1회 하단 배치.
 *
 * 목적 = 컴포넌트/카드마다 "자체 점수 아님 · 출처 DART" 류를 반복 첨부하던 것을
 *   페이지 하단 단일 노트로 통합 (2026-07-04 PM 지시).
 * 🚨 RULE 7 경계: 일반 보일러플레이트만. 숫자에 붙는 통계 라벨은 각 컴포넌트에 유지.
 *
 * 🚨 2026-07-24 테마 = 자체 내장 CSS 변수(--an-sn-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
 *   배경 = transparent(하단 노트 스트립, 상단 구분선만). <style>{AN_PALETTE} 로 정적 HTML 정합. 되돌리지 말 것.
 */

const LIGHT = { bg: "#f2f4f6", ink: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", violet: "#6c5ce7" }
const DARK = { bg: "#16181d", ink: "#9aa4b1", faint: "#6b7684", line: "#2b2f37", violet: "#a99bff" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-sn-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "sn"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

export default function PublicSourceNote(props: {
    width?: number
    sources?: string
    note?: string
    showHeld?: boolean
    dark?: boolean
}) {
    const sources = (props.sources || "DART 전자공시 · KRX · 금융위 공공데이터 · 네이버 금융 · SEC EDGAR").trim()
    const held = props.showHeld !== false
    const note = (props.note || "").trim()

    const wrap: CSSProperties = {
        width: props.width || "100%", maxWidth: "100%", boxSizing: "border-box",
        fontFamily: FONT, background: "transparent", color: C.ink,
        padding: "14px 16px", borderTop: `1px solid ${C.line}`,
        display: "flex", flexDirection: "column", gap: 4,
    }

    return (
        <div style={wrap}>
            <style>{AN_PALETTE}</style>
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
    dark: { type: ControlType.Boolean, title: "Dark(미사용)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

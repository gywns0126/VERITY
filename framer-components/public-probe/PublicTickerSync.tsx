import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

/**
 * 종목 동기화 브릿지 (초경량) — 리포트(/stock)와 결정 페이지(/decision-test) 사이 종목 컨텍스트를 잇는다.
 *
 * 왜 = Framer 네이티브 토글 Link 는 `?q` 를 안 실어 나름 → 페이지 토글 시 종목이 빠짐.
 *   이 컴포넌트가 ?q ↔ localStorage(`verity_last_ticker`) 를 양방향 동기화해서, 리포트를 수정하지 않고도
 *   리포트의 기존 `?q` 읽기로 종목이 유지되게 한다.
 *
 * 동작(클라이언트 마운트 1회):
 *  - `?q` 있음 → localStorage 에 기록(다른 페이지로 토글 시 운반용)
 *  - `?q` 없음 + localStorage 있음 → history.replaceState 로 `?q` 주입(리포트 list-load 가 읽음)
 *
 * 🚨 RULE 6/7 = 종속 없음. 점수·추천·LLM 0. 순수 URL↔스토리지 브릿지. 런타임 렌더 = null(투명).
 * 배치 = /stock 좌측 스택 아무 곳(리포트 위 권장). /decision-test 는 TickerPicker+결정도구가 자체 처리라 불필요.
 */

const LAST_TK_KEY = "verity_last_ticker"
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

interface Props { dark: boolean }

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicTickerSync(props: Props) {
    const { dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [synced, setSynced] = useState("")

    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        try {
            const params = new URLSearchParams(window.location.search)
            const q = (params.get("q") || "").trim()
            const stored = (window.localStorage.getItem(LAST_TK_KEY) || "").trim()
            if (q) {
                // ?q 가 canonical — 토글 운반용으로 localStorage 갱신
                if (q !== stored) window.localStorage.setItem(LAST_TK_KEY, q)
                setSynced(q)
            } else if (stored) {
                // ?q 없이 착지(토글로 넘어옴) — localStorage 의 마지막 종목을 ?q 로 복원
                params.set("q", stored)
                const url = window.location.pathname + "?" + params.toString() + window.location.hash
                window.history.replaceState(null, "", url)
                setSynced(stored)
            }
        } catch { /* private mode / quota */ }
    }, [onCanvas])

    // 캔버스에서만 배치용 힌트 표시. 런타임 = null(투명, 레이아웃 영향 최소).
    if (!onCanvas) return null
    const C = dark
        ? { bg: "#171c23", ink: "#9aa4b1", line: "#252b34", vt: "#a99bff" }
        : { bg: "#f0edff", ink: "#6c5ce7", line: "#e5e8eb", vt: "#6c5ce7" }
    return (
        <div style={{ width: "100%", fontFamily: FONT, padding: "7px 12px", boxSizing: "border-box", background: C.bg, border: `1px dashed ${C.line}`, borderRadius: 9, fontSize: 11.5, fontWeight: 700, color: C.ink }}>
            <span style={{ color: C.vt }}>⇄ 종목 동기화 브릿지</span> · 런타임 투명 · ?q ↔ localStorage(리포트 ↔ 결정 토글 유지)
        </div>
    )
}

addPropertyControls(PublicTickerSync, {
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

import { addPropertyControls, ControlType } from "framer"
import { useCallback, type CSSProperties } from "react"

/**
 * 리포트 PDF 추출 버튼 — VERITY 공개 터미널 (골든구스).
 *
 * 방식 = 무의존 window.print() (workflow whxa2vt29 PDF 리서치 권고). esbuild panic 노출면 0
 *   (html2canvas/jsPDF 같은 무거운 번들 회피 — feedback_framer_esbuild_modern_syntax_panic 정합).
 * 브라우저 인쇄 대화상자 → "PDF로 저장" → 벡터 텍스트(선명·검색가능). A4 세로 page hint 주입.
 * 페이지 chrome(nav 등) 숨김이 필요하면 = Framer Site Settings Custom Code 의 @media print
 *   전역 규칙으로 처리 (sandbox 가 형제 DOM 까지 안 닿을 수 있음 — 에이전트 caveat). 여기선 page hint만.
 * 어느 페이지에나 배치 가능 (window.print 는 페이지 전체 인쇄).
 *
 * size: "small" | "medium" — small 은 리포트 하단 등 보조 위치용 컴팩트 변형. 기본 medium(기존 호환).
 */

const PRINT_CSS_ID = "verity-print-page-hint"
const PRINT_CSS = "@media print { @page { size: A4 portrait; margin: 10mm; } [data-noprint] { display: none !important; } }"

type Size = "small" | "medium"

interface Props {
    label: string
    dark: boolean
    accent: string
    full: boolean
    size: Size
}

const SIZES: Record<Size, { padding: string; fontSize: number; gap: number; radius: number; icon: number }> = {
    small: { padding: "6px 11px", fontSize: 11.5, gap: 5, radius: 9, icon: 12 },
    medium: { padding: "10px 16px", fontSize: 13.5, gap: 7, radius: 12, icon: 15 },
}

function ensurePrintCss() {
    if (typeof document === "undefined") return
    if (document.getElementById(PRINT_CSS_ID)) return
    const el = document.createElement("style")
    el.id = PRINT_CSS_ID
    el.textContent = PRINT_CSS
    document.head.appendChild(el)
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicPrintButton(props: Props) {
    const { label, dark, accent, full } = props
    const sz = SIZES[props.size === "small" ? "small" : "medium"]

    const handlePrint = useCallback(() => {
        ensurePrintCss()
        if (typeof window !== "undefined" && typeof window.print === "function") {
            window.print()
        }
    }, [])

    const fg = "#ffffff"
    const bg = accent || (dark ? "#7fffa0" : "#0ca678")
    const style: CSSProperties = {
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: sz.gap,
        width: full ? "100%" : "auto", boxSizing: "border-box",
        border: "none", cursor: "pointer", padding: sz.padding, borderRadius: sz.radius,
        fontSize: sz.fontSize, fontWeight: 800, lineHeight: 1,
        fontFamily: "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif",
        background: bg, color: dark ? "#0f1318" : fg,
    }

    return (
        <button data-noprint onClick={handlePrint} style={style}>
            <svg width={sz.icon} height={sz.icon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="6 9 6 2 18 2 18 9" />
                <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
                <rect x="6" y="14" width="12" height="8" />
            </svg>
            {label || "리포트 PDF 추출"}
        </button>
    )
}

addPropertyControls(PublicPrintButton, {
    label: { type: ControlType.String, title: "Label", defaultValue: "리포트 PDF 추출" },
    size: { type: ControlType.Enum, title: "Size", options: ["small", "medium"], optionTitles: ["Small", "Medium"], defaultValue: "medium" },
    accent: { type: ControlType.Color, title: "Accent", defaultValue: "#0ca678" },
    full: { type: ControlType.Boolean, title: "Full Width", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

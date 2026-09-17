import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

/* 아이콘 = Phosphor 공식 path 인라인(fill=currentColor, 버튼 color 상속). npm import 는 Framer typecheck 실패. */
function PhPrinter({ size }: { size: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 256 256" fill="currentColor">
            <path d="M214.67,68H204V40a12,12,0,0,0-12-12H64A12,12,0,0,0,52,40V68H41.33C25.16,68,12,80.56,12,96v80a12,12,0,0,0,12,12H52v28a12,12,0,0,0,12,12H192a12,12,0,0,0,12-12V188h28a12,12,0,0,0,12-12V96C244,80.56,230.84,68,214.67,68ZM76,52H180V68H76ZM180,204H76V172H180Zm40-40H204v-4a12,12,0,0,0-12-12H64a12,12,0,0,0-12,12v4H36V96c0-2.17,2.44-4,5.33-4H214.67c2.89,0,5.33,1.83,5.33,4Zm-16-44a16,16,0,1,1-16-16A16,16,0,0,1,204,120Z" />
        </svg>
    )
}
/**
 * 2026-09-17: 기업 분석 자료 버튼 하나로 통합. 유료 AI 생성·자동 캐시 조회 재도입 금지.
 * 자체 내장 CSS 변수 테마와 URL/이벤트 종목 추종을 유지한다.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", red: "#f04452", green: "#0ca678", vtBtn: "#6c5ce7",
}
const DARK = {
    bg: "#0f1318", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440", red: "#ff6b76", green: "#3ecf8e", vtBtn: "#6c5ce7",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-sbf-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "sbf"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

function resolveTicker(): string {
    if (typeof window === "undefined") return ""
    let t = (new URLSearchParams(window.location.search).get("q") || "").trim()
    if (!t) {
        try {
            t = (window.localStorage.getItem("verity_last_ticker") || "").trim()
        } catch (e) {}
    }
    t = t.toUpperCase()
    return /^\d{6}$/.test(t) || /^[A-Z][A-Z0-9.\-]{0,9}$/.test(t) ? t : ""
}

export default function PublicStockBrief(props: {
    width?: number
    dark?: boolean
    apiBase?: string
}) {
    // ETF/ETN 선택 시 자기 숨김 — StockReport 가 body[data-verity-asset-kind] 신호 발행 (2026-07-10)
    const [assetKind, setAssetKind] = useState<string>("stock")
    useEffect(() => {
        if (typeof document === "undefined" || !document.body) return
        const read = () =>
            setAssetKind(document.body.dataset.verityAssetKind || "stock")
        read()
        if (typeof MutationObserver === "undefined") return
        const obs = new MutationObserver(read)
        obs.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-verity-asset-kind"],
        })
        return () => obs.disconnect()
    }, [])
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [tk, setTk] = useState<string>("")
    const base = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    useEffect(() => {
        if (onCanvas) return
        const reread = () => setTk(resolveTicker())
        reread()
        window.addEventListener("verity-ticker-change", reread)
        window.addEventListener("popstate", reread)
        return () => {
            window.removeEventListener("verity-ticker-change", reread)
            window.removeEventListener("popstate", reread)
        }
    }, [onCanvas])

    const wrap: any = {
        width: props.width || 380,
        fontFamily: FONT,
        background: "transparent",
        color: C.ink,
        padding: 14,
        boxSizing: "border-box",
    }
    const btnBase: any = {
        border: "none",
        fontFamily: FONT,
        padding: "10px 15px",
        borderRadius: 11,
        fontSize: 13,
        fontWeight: 700,
        lineHeight: 1,
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
    }

    if (assetKind === "etf" || assetKind === "etn" || /^CMD_/.test(String(tk).toUpperCase())) return null // ETF/ETN = 기업 전용 섹션 숨김

    return (
        <div style={wrap}>
            <style>{AN_PALETTE}</style>
            <div
                data-noprint
                style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}
            >
                <button
                    onClick={() => {
                        if (tk && typeof window !== "undefined")
                            window.open(
                                base + "/api/fact_report?ticker=" + encodeURIComponent(tk),
                                "_blank",
                                "noopener"
                            )
                    }}
                    disabled={!tk}
                    style={{
                        ...btnBase,
                        cursor: tk ? "pointer" : "default",
                        opacity: tk ? 1 : 0.5,
                        background: C.violetSoft,
                        color: C.violet,
                    }}
                >
                    <PhPrinter size={14} />
                    분석 리포트 PDF
                </button>
            </div>
            <div
                data-noprint
                style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 7, lineHeight: 1.5, textAlign: "center" }}
            >
                실적 변화·공시 원문·확인할 질문과 내 AI용 분석 자료
            </div>
        </div>
    )
}

addPropertyControls(PublicStockBrief, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark(미사용)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
})


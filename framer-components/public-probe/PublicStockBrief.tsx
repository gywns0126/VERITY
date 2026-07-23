import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

/* 아이콘 = Phosphor 공식 path 원본 인라인 (printer-bold / pencil-simple-line-bold, MIT).
 * npm import 는 Framer typecheck 에서 모듈 해석 실패(2307) — publish 리스크라 원본 데이터 직접 사용. 자작 SVG 아님. */
function PhPrinter({ size }: { size: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 256 256" fill="currentColor">
            <path d="M214.67,68H204V40a12,12,0,0,0-12-12H64A12,12,0,0,0,52,40V68H41.33C25.16,68,12,80.56,12,96v80a12,12,0,0,0,12,12H52v28a12,12,0,0,0,12,12H192a12,12,0,0,0,12-12V188h28a12,12,0,0,0,12-12V96C244,80.56,230.84,68,214.67,68ZM76,52H180V68H76ZM180,204H76V172H180Zm40-40H204v-4a12,12,0,0,0-12-12H64a12,12,0,0,0-12,12v4H36V96c0-2.17,2.44-4,5.33-4H214.67c2.89,0,5.33,1.83,5.33,4Zm-16-44a16,16,0,1,1-16-16A16,16,0,0,1,204,120Z" />
        </svg>
    )
}
function PhPencilLine({ size }: { size: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 256 256" fill="currentColor">
            <path d="M230.15,70.54,185.46,25.86a20,20,0,0,0-28.28,0L33.86,149.17A19.86,19.86,0,0,0,28,163.31V208a20,20,0,0,0,20,20H216a12,12,0,0,0,0-24H125L230.15,98.83A20,20,0,0,0,230.15,70.54ZM91,204H52V165l84-84,39,39ZM192,103,153,64l18.34-18.34,39,39Z" />
        </svg>
    )
}

/**
 * 리포트 추출 허브 — AlphaNest /stock. 두 버튼 = 서버 Typst 조판 PDF (2026-07-23, window.print 화면 캡쳐 폐기).
 *   [팩트 리포트 PDF]    = /api/fact_report — 100% 공개 데이터 · 점수·추천 0
 *   [AI 해석 리포트 PDF] = /api/ai_report  — 팩트 본문 + 맨 앞 AI 해석 서술 장
 * 둘 다 클릭 시 새 탭에서 서버 조판 PDF 열림 (캐시/생성은 서버가 처리). 화면 인쇄·인라인 브리핑 없음(PM 버튼만 노출).
 * 종목 추종 = URL ?q= + verity-ticker-change/popstate (PublicLiveChart 동일 패턴).
 * ETF/ETN 자기 숨김. 🚨 RULE 6 = 서버가 grounding 밖 생성 차단. RULE 7 = 출처·disclaimer 는 서버 PDF 에 고정. 다크모드 자가감지.
 */

const LIGHT = {
    ink: "#191f28", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff",
}
const DARK = {
    ink: "#f0f2f5", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
    } catch (e) {}
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function resolveTicker(): string {
    if (typeof window === "undefined") return ""
    let t = (new URLSearchParams(window.location.search).get("q") || "").trim()
    if (!t) { try { t = (window.localStorage.getItem("verity_last_ticker") || "").trim() } catch (e) {} }
    t = t.toUpperCase()
    return /^\d{6}$/.test(t) || /^[A-Z][A-Z0-9.\-]{0,9}$/.test(t) ? t : ""
}

// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.
let __anHyd = false
function anReadDark(): boolean {
    if (typeof document === "undefined") return false
    if (!__anHyd) {
        __anHyd = true
        return false
    }
    const h = document.documentElement ? document.documentElement.dataset.anTheme : null
    if (h === "dark") return true
    if (h === "light") return false
    return !!(document.body && document.body.dataset.framerTheme === "dark")
}


export default function PublicStockBrief(props: {
    width?: number; dark?: boolean; apiBase?: string
}) {
    // ETF/ETN 선택 시 자기 숨김 — StockReport 가 body[data-verity-asset-kind] 신호 발행 (2026-07-10)
    const [assetKind, setAssetKind] = useState<string>("stock")
    useEffect(() => {
        if (typeof document === "undefined" || !document.body) return
        const read = () => setAssetKind(document.body.dataset.verityAssetKind || "stock")
        read()
        if (typeof MutationObserver === "undefined") return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-verity-asset-kind"] })
        return () => obs.disconnect()
    }, [])
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : anReadDark()))
    const [tk, setTk] = useState<string>("")

    useEffect(() => {
        if (onCanvas) return
        setThemeDark(readBodyDark())
        const obs = new MutationObserver(() => setThemeDark(readBodyDark()))
        if (document.body) obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const base = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")

    // 종목 추종 — URL ?q= / verity-ticker-change / popstate 따라 tk 갱신
    useEffect(() => {
        if (onCanvas) return
        const reread = () => setTk(resolveTicker())
        reread()
        window.addEventListener("verity-ticker-change", reread)
        window.addEventListener("popstate", reread)
        return () => { window.removeEventListener("verity-ticker-change", reread); window.removeEventListener("popstate", reread) }
    }, [onCanvas])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    // 서버 Typst 조판 PDF 새 탭 열기 — 클릭 핸들러에서 동기 호출(팝업 차단 회피). 캐시/생성은 서버가 처리.
    const openReport = (path: string) => {
        if (tk && typeof window !== "undefined")
            window.open(base + path + "?ticker=" + encodeURIComponent(tk), "_blank", "noopener")
    }

    // 배경 = transparent: 페이지 위 스트립. 자기 bg hex 칠하면 Framer 네이티브 페이지 dark bg 와 어긋나 사각형으로 튐. 페이지 배경 그대로 비침.
    const wrap: any = { width: props.width || 380, fontFamily: FONT, background: "transparent", color: C.ink, padding: 14, boxSizing: "border-box" }
    const btnBase: any = {
        border: "none", fontFamily: FONT, padding: "10px 15px", borderRadius: 11,
        fontSize: 13, fontWeight: 800, lineHeight: 1, display: "inline-flex", alignItems: "center", gap: 6,
    }

    if (assetKind === "etf") return null  // ETF/ETN = 기업 전용 섹션 숨김

    return (
        <div style={wrap}>
            {/* ── 버튼 2개 — 상품 구분: 100% 데이터 vs 데이터+AI 해석. 둘 다 서버 조판 PDF. 아이콘 = Phosphor ── */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
                <button onClick={() => openReport("/api/fact_report")} disabled={!tk} style={{ ...btnBase, cursor: tk ? "pointer" : "default", opacity: tk ? 1 : 0.5, background: C.violetSoft, color: C.violet }}>
                    <PhPrinter size={14} />
                    팩트 리포트 PDF
                </button>
                <button onClick={() => openReport("/api/ai_report")} disabled={!tk} style={{ ...btnBase, cursor: tk ? "pointer" : "default", background: tk ? C.violet : C.line, color: tk ? "#fff" : C.faint }}>
                    <PhPencilLine size={14} />
                    AI 해석 리포트 PDF
                </button>
            </div>
            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 7, lineHeight: 1.5, textAlign: "center" }}>
                팩트 = 100% 공개 데이터 · AI 해석 = 같은 데이터 위에 요약 서술이 붙어요 (첫 생성 ~10초, 하루 1회 생성 후 캐시)
            </div>
        </div>
    )
}

addPropertyControls(PublicStockBrief, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
})

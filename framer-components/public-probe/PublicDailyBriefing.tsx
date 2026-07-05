import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * 모닝 브리핑 — 홈 최상단 카드 (단일 채널, PM 2026-07-05 · project_daily_briefing_design).
 *
 * 데이터 = daily_briefing.json (daily_briefing_builder — 기존 발행 피드 재조립, 아침 07:30 KST).
 * 🚨 RULE 7 — 전 항목 = 일어난 사실 + 예정 사실(자체계산 예상 창 라벨). 점수·추천 0.
 * 🚨 RULE 6 — LLM 0 (결정론 조립). 문구 전부 빌더 사전 작성.
 * 다크모드 = body[data-framer-theme] 추종. cache-fallback(sessionStorage). 캔버스 = SAMPLE.
 * 종목 클릭 → /stock?q= (리포트 딥링크).
 */

// 보라 = 기능 액센트만 (활성 상태·클릭 단서·아이콘). 텍스트·수치·라벨 = 무채 (PM 2026-07-05 '적절하게')
const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff",
}
const DARK = {
    bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DATA_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/daily_briefing.json"
const PER_SECTION = 4 // 섹션당 기본 노출, 초과 = "+N건" 접힘

const SAMPLE = {
    date: "2026-07-05", weekday: "일", warnings_n: 0,
    sections: [
        { title: "밤사이 미국 공시", note: "SEC EDGAR 일일 인덱스 감지분", items: [
            { ticker: "CNXC", name: "Concentrix", text: "10-K/Q 재무 공시 제출 → 재무 반영 완료" },
            { ticker: "SNX", name: "TD Synnex", text: "10-K/Q 재무 공시 제출 → 재무 반영 완료" },
        ] },
        { title: "이번 주 실적 공시 예상", note: "과거 제출 패턴 자체계산 ±7일 창", items: [
            { ticker: "DAL", name: "델타항공", date: "2026-07-08" },
            { ticker: "005930", name: "삼성전자", date: "2026-07-09" },
        ] },
        { title: "최근 7일 내부자 변동", note: "DART 보고 사실 · 증감 주식수", items: [
            { ticker: "402340", name: "SK스퀘어", text: "SK스퀘어 · 12,111,300주 매수 (07-01)" },
        ] },
    ],
    disclaimer: "전부 공시·수집 사실과 자체계산 예상 창 · 점수·추천·매매의견 아님",
}

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicDailyBriefing(props: {
    width?: number; dark?: boolean; dataUrl?: string; stockPath?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)
    const [failed, setFailed] = useState(false)
    const [openSec, setOpenSec] = useState<Record<string, boolean>>({})

    useEffect(() => {
        if (onCanvas) return
        setThemeDark(readBodyDark())
        const obs = new MutationObserver(() => setThemeDark(readBodyDark()))
        if (document.body) obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const fallback = () => {
            try {
                const c = sessionStorage.getItem("daily_briefing")
                if (alive && c) { setData(JSON.parse(c)); return }
            } catch (e) { /* ignore */ }
            if (alive) setFailed(true)
        }
        fetch(props.dataUrl || DATA_URL, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                if (d && Array.isArray(d.sections)) {
                    setData(d)
                    try { sessionStorage.setItem("daily_briefing", JSON.stringify(d)) } catch (e) { /* ignore */ }
                } else fallback()
            })
            .catch(fallback)
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const stockPath = props.stockPath || "/stock"

    const go = (tk: string) => {
        if (onCanvas || typeof window === "undefined" || !tk) return
        try { window.location.href = `${stockPath}?q=${encodeURIComponent(tk)}` } catch (e) { /* ignore */ }
    }

    const wrap: CSSProperties = {
        width: props.width || 380, maxWidth: "100%", fontFamily: FONT, background: C.bg,
        color: C.ink, padding: "0 14px", boxSizing: "border-box",
    }

    if (!data) {
        return (
            <div style={wrap}>
                <div style={{ background: C.card, borderRadius: 16, padding: "16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", fontSize: 12.5, color: C.faint, fontWeight: 600 }}>
                    {failed ? "브리핑을 불러오지 못했어요 — 새로고침 해주세요" : "모닝 브리핑 준비 중…"}
                </div>
            </div>
        )
    }

    const dateLabel = data.date ? `${String(data.date).slice(5, 7)}.${String(data.date).slice(8, 10)} (${data.weekday || ""})` : ""

    return (
        <div style={wrap}>
            <div style={{ background: C.card, borderRadius: 16, padding: "16px 16px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                {/* 헤더 */}
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.4px" }}>모닝 브리핑</span>
                    <span style={{ fontSize: 11.5, fontWeight: 700, color: C.sub, background: C.bg, borderRadius: 6, padding: "2px 8px" }}>{dateLabel}</span>
                    {Number(data.warnings_n) > 0 && (
                        <span style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>시장경보 {data.warnings_n}종목</span>
                    )}
                    <span style={{ marginLeft: "auto", fontSize: 10.5, fontWeight: 600, color: C.faint }}>매일 아침 07:30</span>
                </div>

                {/* 섹션 */}
                {(data.sections || []).map((s: any, si: number) => {
                    const open = !!openSec[s.title]
                    const items = open ? (s.items || []) : (s.items || []).slice(0, PER_SECTION)
                    const extra = (s.items || []).length - PER_SECTION
                    return (
                        <div key={si} style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${C.line}` }}>
                            <div style={{ display: "flex", alignItems: "baseline", gap: 7, flexWrap: "wrap" }}>
                                <span style={{ fontSize: 12.5, fontWeight: 800, color: C.ink }}>{s.title}</span>
                                <span style={{ fontSize: 10, fontWeight: 600, color: C.faint }}>{s.note}</span>
                            </div>
                            <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
                                {items.map((it: any, i: number) => (
                                    <div key={i} style={{ display: "flex", gap: 7, alignItems: "baseline", fontSize: 12, lineHeight: 1.45 }}>
                                        <span onClick={() => go(String(it.ticker || ""))}
                                            style={{ flexShrink: 0, fontWeight: 800, color: C.violet, cursor: it.ticker ? "pointer" : "default" }}>
                                            {it.name || it.ticker}
                                        </span>
                                        <span style={{ color: C.sub, fontWeight: 600, minWidth: 0 }}>
                                            {it.text || (it.date ? `예상일 ${String(it.date).slice(5)}` : "")}
                                        </span>
                                    </div>
                                ))}
                            </div>
                            {extra > 0 && (
                                <button onClick={() => setOpenSec((o) => ({ ...o, [s.title]: !open }))}
                                    style={{ border: "none", background: "transparent", cursor: "pointer", fontFamily: FONT, fontSize: 11, fontWeight: 700, color: C.sub, padding: "5px 0 0", }}>
                                    {open ? "접기" : `+${extra}건 더보기`}
                                </button>
                            )}
                        </div>
                    )
                })}

                {/* 푸터 */}
                <div style={{ fontSize: 10, color: C.faint, fontWeight: 600, marginTop: 12, paddingTop: 10, borderTop: `1px solid ${C.line}`, lineHeight: 1.5 }}>
                    {data.disclaimer || "전부 공시·수집 사실 · 점수·추천 아님"}
                </div>
            </div>
        </div>
    )
}

addPropertyControls(PublicDailyBriefing, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DATA_URL },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
})

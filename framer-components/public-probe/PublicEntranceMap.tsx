import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"

/**
 * 입구 지도 (Entrance Map) — AlphaNest 홈 첫 화면. "가진 것의 지도"를 3초 안에.
 * 데이터(Blob): entrance_map.json (~1KB — 발행 중 공개 자산들의 count·기준시각 집계, entrance_map_builder).
 * 카드 = 자산명 + 실측 숫자(오늘 기준) + 신선도 + 클릭 딥링크. 숫자가 영수증 — "많아 보이는" 게 아니라 세어볼 수 있게.
 *
 * 🚨 RULE 7 — 사실(개수·시각)만. 점수/등급/추천 0. 검증 게이트 카드 = 진척 %만(성과 봉인 정책 상속).
 * RULE 6 — LLM narrative 0. 다크모드 자가감지(body[data-framer-theme]). cache-fallback(sessionStorage).
 * 네비 아님 — 데이터 카드 그리드 (사이트 nav 는 Framer 네이티브, 사용자 영역).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", green: "#12b76a",
}
const DARK = {
    bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440", green: "#3ecf8e",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const DATA_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/entrance_map.json"

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch (e) {
        return ""
    }
}
function fmtN(n: any): string {
    const x = Number(n)
    if (!isFinite(x) || x <= 0) return "—"
    return Math.round(x).toLocaleString("en-US")
}

const SAMPLE = {
    assets: [
        { id: "universe", count: 8920, as_of: "" }, { id: "stock_report", count: 1621, as_of: "" },
        { id: "us_stock_report", count: 1505, as_of: "" }, { id: "quarterly", count: 854, as_of: "" },
        { id: "insider_kr", count: 1428, as_of: "" }, { id: "insider_us", count: 1304, as_of: "" },
        { id: "forensics", count: 646, as_of: "" }, { id: "flow_5d", count: 1642, as_of: "" },
        { id: "lending", count: 200, as_of: "" }, { id: "sectors", count: 11, as_of: "" },
    ],
    validation_gate: { target_n: 252, progress_pct: 98.7, signals: 5, as_of: "" },
}

export default function PublicEntranceMap(props: {
    width?: number; dark?: boolean; dataUrl?: string
    stockPath?: string; discoverPath?: string; explorePath?: string; validationPath?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)

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
        fetch(props.dataUrl || DATA_URL, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive && d && Array.isArray(d.assets)) {
                    setData(d)
                    try { sessionStorage.setItem("entrance_map", JSON.stringify(d)) } catch (e) {}
                }
            })
            .catch(() => {
                try { const c = sessionStorage.getItem("entrance_map"); if (alive && c) setData(JSON.parse(c)) } catch (e) {}
            })
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const stockPath = props.stockPath || "/stock"
    const discoverPath = props.discoverPath || "/discover"
    const explorePath = props.explorePath || "/market"
    const validationPath = props.validationPath || "/glassbox"

    const go = (path: string) => {
        if (onCanvas || typeof window === "undefined") return
        try { window.location.href = path } catch (e) {}
    }

    const wrap: any = { width: props.width || 380, fontFamily: FONT, background: C.bg, color: C.ink, padding: 14, boxSizing: "border-box" }
    if (!data) return <div style={wrap}><div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>지도 준비 중…</div></div>

    const byId: Record<string, any> = {}
    for (const a of data.assets || []) if (a && a.id) byId[a.id] = a
    const cnt = (id: string) => (byId[id] ? byId[id].count : null)
    const age = (id: string) => (byId[id] ? fmtAge(byId[id].as_of) : "")

    /* 카드 정의 — 실측 숫자 = 영수증. path 는 props 로 조정 가능. */
    const cards = [
        { t: "종목 검색", n: fmtN(cnt("universe")), u: "종목", d: "국내 + 미국 전 종목", a: age("universe"), p: stockPath },
        { t: "종목 리포트", n: fmtN((cnt("stock_report") || 0) + (cnt("us_stock_report") || 0)), u: "종목", d: "재무·수급·공시·내부자 한 페이지", a: age("stock_report"), p: stockPath },
        { t: "분기 재무 추이", n: fmtN(cnt("quarterly")), u: "종목", d: "최대 5년 20분기 · DART 원문", a: age("quarterly"), p: stockPath },
        { t: "내부자 거래", n: fmtN((cnt("insider_kr") || 0) + (cnt("insider_us") || 0)), u: "종목", d: "KR 임원·주요주주 + 美 SEC Form 4", a: age("insider_kr"), p: discoverPath },
        { t: "외인·기관 수급", n: fmtN(cnt("flow_5d")), u: "종목", d: "일별 순매매 5일 · 네이버", a: age("flow_5d"), p: stockPath },
        { t: "공시 포렌식", n: fmtN(cnt("forensics")), u: "종목", d: "유증·CB 희석, 리스크 공시 빈도", a: age("forensics"), p: stockPath },
        { t: "대차잔고", n: fmtN(cnt("lending")), u: "종목", d: "공매도 압력 proxy · 금융위", a: age("lending"), p: stockPath },
        { t: "업종 지도", n: fmtN(cnt("sectors")), u: "업종", d: "중앙값 PER·PBR + 대표주 + 수급", a: age("sectors"), p: explorePath },
    ]

    const gate = data.validation_gate

    return (
        <div style={wrap}>
            {/* 헤더 */}
            <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>알파네스트가 가진 것</div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>
                    전부 출처 있는 사실 · 숫자는 오늘 기준 실측 · 매일 자동 갱신
                </div>
            </div>

            {/* 자산 카드 그리드 */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 10 }}>
                {cards.map((c) => (
                    <div key={c.t} onClick={() => go(c.p)}
                        style={{ background: C.card, borderRadius: 14, padding: 13, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", cursor: "pointer" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 6 }}>
                            <span style={{ fontSize: 13.5, fontWeight: 800, color: C.ink }}>{c.t}</span>
                            <span style={{ fontSize: 12, fontWeight: 700, color: C.faint }}>›</span>
                        </div>
                        <div style={{ marginTop: 6 }}>
                            <span style={{ fontSize: 20, fontWeight: 800, color: C.violet, letterSpacing: "-0.4px" }}>{c.n}</span>
                            <span style={{ fontSize: 11, fontWeight: 700, color: C.faint, marginLeft: 3 }}>{c.u}</span>
                        </div>
                        <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 4, lineHeight: 1.45 }}>
                            {c.d}{c.a ? " · " + c.a : ""}
                        </div>
                    </div>
                ))}

                {/* 검증 게이트 카드 — 성과 봉인 정책 상속: 진척 %만 */}
                {gate && (
                    <div onClick={() => go(validationPath)}
                        style={{ background: C.violetSoft, borderRadius: 14, padding: 13, cursor: "pointer" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 6 }}>
                            <span style={{ fontSize: 13.5, fontWeight: 800, color: C.violet }}>검증 원장</span>
                            <span style={{ fontSize: 12, fontWeight: 700, color: C.violet }}>›</span>
                        </div>
                        <div style={{ marginTop: 6 }}>
                            <span style={{ fontSize: 20, fontWeight: 800, color: C.violet, letterSpacing: "-0.4px" }}>
                                {gate.progress_pct != null ? gate.progress_pct.toFixed(1) + "%" : "—"}
                            </span>
                        </div>
                        <div style={{ fontSize: 10.5, color: C.sub, fontWeight: 600, marginTop: 4, lineHeight: 1.45 }}>
                            신호 {gate.signals || 0}개 사전등록 · N={gate.target_n || 252} 게이트 진척
                        </div>
                    </div>
                )}
            </div>

            {/* RULE 7 footer */}
            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
                개수·기준시각 = 실측 사실 · 점수·등급·종목 추천 아님
            </div>
        </div>
    )
}

addPropertyControls(PublicEntranceMap, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DATA_URL },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
    discoverPath: { type: ControlType.String, title: "Discover Path", defaultValue: "/discover" },
    explorePath: { type: ControlType.String, title: "Explore Path", defaultValue: "/market" },
    validationPath: { type: ControlType.String, title: "Validation Path", defaultValue: "/glassbox" },
})

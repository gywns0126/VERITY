import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"
import {
    MagnifyingGlass, FileText, ChartLineUp, UserFocus, ArrowsLeftRight,
    ShieldWarning, Coins, Factory, Vault,
} from "@phosphor-icons/react"

/**
 * 입구 지도 — AlphaNest 홈 첫 화면. 자산명 + 실측 숫자 + 신선도 + 딥링크. 데이터(Blob): entrance_map.json.
 * 🚨 RULE 7 — 사실(개수·시각)만. 점수/추천 0. RULE 6 — LLM 0. 아이콘 = Phosphor 라인.
 *
 * 🚨 2026-07-24 테마 = 자체 내장 CSS 변수(--an-enm-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
 *   <style>{AN_PALETTE} 정적 HTML 정합. Phosphor 아이콘 = 부모 color(var) currentColor 상속. 되돌리지 말 것.
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

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-enm-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "enm"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

const ICON: Record<string, any> = {
    search: MagnifyingGlass, report: FileText, trend: ChartLineUp, people: UserFocus,
    flow: ArrowsLeftRight, shield: ShieldWarning, lend: Coins, sector: Factory, vault: Vault,
}
// 아이콘 = 부모 span 의 color(var) 를 currentColor 로 상속 (Phosphor 기본 currentColor). var 는 프레젠테이션 attribute 미해석이라 이 방식.
function cardIcon(key: string, size: number, color: string) {
    const Ic = ICON[key]
    return Ic ? <span style={{ color, display: "inline-flex" }}><Ic size={size} weight="bold" /></span> : null
}

function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch (e) { return "" }
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
    width?: number; dark?: boolean; dataUrl?: string; stockPath?: string
    discoverPath?: string; explorePath?: string; validationPath?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)

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

    const stockPath = props.stockPath || "/stock"
    const discoverPath = props.discoverPath || "/discover"
    const explorePath = props.explorePath || "/market"
    const validationPath = props.validationPath || "/glassbox"

    const go = (path: string) => {
        if (onCanvas || typeof window === "undefined") return
        try { window.location.href = path } catch (e) {}
    }

    const wrap: any = { width: props.width || 380, maxWidth: "100%", fontFamily: FONT, background: "transparent", color: C.ink, padding: "0 14px", boxSizing: "border-box" }
    if (!data)
        return (<div style={wrap}><style>{AN_PALETTE}</style><div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>지도 준비 중…</div></div>)

    const byId: Record<string, any> = {}
    for (const a of data.assets || []) if (a && a.id) byId[a.id] = a
    const cnt = (id: string) => (byId[id] ? byId[id].count : null)
    const age = (id: string) => (byId[id] ? fmtAge(byId[id].as_of) : "")

    const cards = [
        { k: "search", t: "종목 검색", n: fmtN(cnt("universe")), u: "종목", d: "국내 + 미국 전 종목", a: age("universe"), p: stockPath },
        { k: "report", t: "종목 리포트", n: fmtN((cnt("stock_report") || 0) + (cnt("us_stock_report") || 0)), u: "종목", d: "재무·수급·공시·내부자 한 페이지", a: age("stock_report"), p: stockPath },
        { k: "trend", t: "분기 재무 추이", n: fmtN(cnt("quarterly")), u: "종목", d: "최대 5년 20분기 · DART 원문", a: age("quarterly"), p: stockPath },
        { k: "people", t: "내부자 거래", n: fmtN((cnt("insider_kr") || 0) + (cnt("insider_us") || 0)), u: "종목", d: "KR 임원·주요주주 + 美 SEC Form 4", a: age("insider_kr"), p: discoverPath },
        { k: "flow", t: "외인·기관 수급", n: fmtN(cnt("flow_5d")), u: "종목", d: "일별 순매매 5일 · 네이버", a: age("flow_5d"), p: stockPath },
        { k: "shield", t: "공시 포렌식", n: fmtN(cnt("forensics")), u: "종목", d: "유증·CB 희석, 리스크 공시 빈도", a: age("forensics"), p: stockPath },
        { k: "lend", t: "대차잔고", n: fmtN(cnt("lending")), u: "종목", d: "공매도 압력 proxy · 금융위", a: age("lending"), p: stockPath },
        { k: "sector", t: "업종 지도", n: fmtN(cnt("sectors")), u: "업종", d: "중앙값 PER·PBR + 대표주 + 수급", a: age("sectors"), p: explorePath },
    ]

    const gate = data.validation_gate

    return (
        <div style={wrap}>
            <style>{AN_PALETTE}</style>
            <style>{`
                .entChip{animation:entPop .5s cubic-bezier(.34,1.6,.64,1) both;transform-box:fill-box;transform-origin:center}
                @keyframes entPop{0%{transform:scale(.5);opacity:0}100%{transform:scale(1);opacity:1}}
                .entCard{transition:transform .16s ease}
                .entCard:hover{transform:translateY(-2px)}
                @media (prefers-reduced-motion: reduce){.entChip{animation:none}.entCard{transition:none}}
            `}</style>
            <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>알파네스트가 가진 것</div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>
                    전부 출처 있는 사실 · 숫자는 오늘 기준 실측 · 매일 자동 갱신
                </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 10 }}>
                {cards.map((c) => (
                    <div key={c.t} className="entCard" onClick={() => go(c.p)}
                        style={{ background: C.card, borderRadius: 14, padding: 13, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", cursor: "pointer" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span className="entChip" style={{ width: 28, height: 28, borderRadius: 8, background: C.violetSoft, display: "grid", placeItems: "center", flexShrink: 0 }}>
                                {cardIcon(c.k, 16, C.violet)}
                            </span>
                            <span style={{ fontSize: 13.5, fontWeight: 800, color: C.ink }}>{c.t}</span>
                            <span style={{ fontSize: 12, fontWeight: 700, color: C.faint, marginLeft: "auto" }}>›</span>
                        </div>
                        <div style={{ marginTop: 6 }}>
                            <span style={{ fontSize: 20, fontWeight: 800, color: C.ink, letterSpacing: "-0.4px" }}>{c.n}</span>
                            <span style={{ fontSize: 11, fontWeight: 700, color: C.faint, marginLeft: 3 }}>{c.u}</span>
                        </div>
                        <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 4, lineHeight: 1.45 }}>
                            {c.d}{c.a ? " · " + c.a : ""}
                        </div>
                    </div>
                ))}

                {gate && (
                    <div className="entCard" onClick={() => go(validationPath)}
                        style={{ background: C.violetSoft, borderRadius: 14, padding: 13, cursor: "pointer" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span className="entChip" style={{ width: 28, height: 28, borderRadius: 8, background: C.card, display: "grid", placeItems: "center", flexShrink: 0 }}>
                                {cardIcon("vault", 16, C.violet)}
                            </span>
                            <span style={{ fontSize: 13.5, fontWeight: 800, color: C.ink }}>검증 원장</span>
                            <span style={{ fontSize: 12, fontWeight: 700, color: C.sub, marginLeft: "auto" }}>›</span>
                        </div>
                        <div style={{ marginTop: 6 }}>
                            <span style={{ fontSize: 20, fontWeight: 800, color: C.ink, letterSpacing: "-0.4px" }}>
                                {gate.progress_pct != null ? gate.progress_pct.toFixed(1) + "%" : "—"}
                            </span>
                        </div>
                        <div style={{ fontSize: 10.5, color: C.sub, fontWeight: 600, marginTop: 4, lineHeight: 1.45 }}>
                            신호 {gate.signals || 0}개 사전등록 · N={gate.target_n || 252} 게이트 진척
                        </div>
                    </div>
                )}
            </div>

            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
                개수·기준시각 = 실측 사실
            </div>
        </div>
    )
}

addPropertyControls(PublicEntranceMap, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark(미사용)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DATA_URL },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
    discoverPath: { type: ControlType.String, title: "Discover Path", defaultValue: "/discover" },
    explorePath: { type: ControlType.String, title: "Explore Path", defaultValue: "/market" },
    validationPath: { type: ControlType.String, title: "Validation Path", defaultValue: "/glassbox" },
})

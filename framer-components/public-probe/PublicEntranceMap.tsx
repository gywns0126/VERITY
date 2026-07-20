import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"
import {
    MagnifyingGlass, FileText, ChartLineUp, UserFocus, ArrowsLeftRight,
    ShieldWarning, Coins, Factory, Vault,
} from "@phosphor-icons/react"

/**
 * 입구 지도 (Entrance Map) — AlphaNest 홈 첫 화면. "가진 것의 지도"를 3초 안에.
 * 데이터(Blob): entrance_map.json (~1KB — 발행 중 공개 자산들의 count·기준시각 집계, entrance_map_builder).
 * 카드 = 자산명 + 실측 숫자(오늘 기준) + 신선도 + 클릭 딥링크. 숫자가 영수증 — "많아 보이는" 게 아니라 세어볼 수 있게.
 *
 * 🎨 아이콘 = Phosphor 라인(@phosphor-icons/react) + violetSoft 라운드 칩 — 관점 지도와 통일(2026-07-13 리디자인).
 *   자작 글래스 SVG(GICONS) 폐기. [[feedback_framer_icons_use_phosphor]] 정합.
 * 🚨 RULE 7 — 사실(개수·시각)만. 점수/등급/추천 0. 검증 게이트 카드 = 진척 %만(성과 봉인 정책 상속).
 * RULE 6 — LLM narrative 0. 다크모드 자가감지(body[data-framer-theme]). cache-fallback(sessionStorage).
 * 네비 아님 — 데이터 카드 그리드 (사이트 nav 는 Framer 네이티브, 사용자 영역).
 */

// 보라 = 기능 액센트만 (활성 상태·클릭 단서·아이콘). 텍스트·수치·라벨 = 무채 (PM 2026-07-05 '적절하게')
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

// 카드 key → Phosphor 아이콘 (라인, bold) — 관점 지도와 동일 문법.
const ICON: Record<string, any> = {
    search: MagnifyingGlass, report: FileText, trend: ChartLineUp, people: UserFocus,
    flow: ArrowsLeftRight, shield: ShieldWarning, lend: Coins, sector: Factory, vault: Vault,
}
function cardIcon(key: string, size: number, color: string) {
    const Ic = ICON[key]
    return Ic ? <Ic size={size} weight="bold" color={color} /> : null
}

function readBodyDark(): boolean {
    // body 속성 우선 → 미설정(토글 마운트 전 / 토글 없는 페이지) 시 localStorage(verity_theme)/OS 폴백.
    // 무-폴백이면 첫 로드에 body 미설정 → 항상 light → 다른 페이지 갔다와야(리마운트) 정상 (2026-07-13 fix).
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
        if (typeof window !== "undefined" && window.matchMedia) return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {}
    return false
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


export default function PublicEntranceMap(props: {
    width?: number; dark?: boolean; dataUrl?: string
    stockPath?: string; discoverPath?: string; explorePath?: string; validationPath?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : anReadDark()))
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

    // 배경 = 투명 (페이지 /Theme/PageBg 그대로 비침) — 자기 C.bg(#16181d) 칠하면 페이지 다크(#0f1318)와 불일치 (2026-07-13 fix)
    const wrap: any = { width: props.width || 380, maxWidth: "100%", fontFamily: FONT, background: "transparent", color: C.ink, padding: "0 14px", boxSizing: "border-box" }
    if (!data) return <div style={wrap}><div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>지도 준비 중…</div></div>

    const byId: Record<string, any> = {}
    for (const a of data.assets || []) if (a && a.id) byId[a.id] = a
    const cnt = (id: string) => (byId[id] ? byId[id].count : null)
    const age = (id: string) => (byId[id] ? fmtAge(byId[id].as_of) : "")

    /* 카드 정의 — 실측 숫자 = 영수증. path 는 props 로 조정 가능. */
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
            {/* 아이콘 = Phosphor 라인 칩 (관점 지도와 동일). 스프링 팝 + 카드 hover 부상 */}
            <style>{`
                .entChip{animation:entPop .5s cubic-bezier(.34,1.6,.64,1) both;transform-box:fill-box;transform-origin:center}
                @keyframes entPop{0%{transform:scale(.5);opacity:0}100%{transform:scale(1);opacity:1}}
                .entCard{transition:transform .16s ease}
                .entCard:hover{transform:translateY(-2px)}
                @media (prefers-reduced-motion: reduce){.entChip{animation:none}.entCard{transition:none}}
            `}</style>
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
                    <div key={c.t} className="entCard" onClick={() => go(c.p)}
                        style={{ background: C.card, borderRadius: 14, padding: 13, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", cursor: "pointer" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span className="entChip" style={{ width: 28, height: 28, borderRadius: 8, background: C.violetSoft, display: "grid", placeItems: "center", flexShrink: 0 }}>{cardIcon(c.k, 16, C.violet)}</span>
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

                {/* 검증 게이트 카드 — 성과 봉인 정책 상속: 진척 %만 */}
                {gate && (
                    <div className="entCard" onClick={() => go(validationPath)}
                        style={{ background: C.violetSoft, borderRadius: 14, padding: 13, cursor: "pointer" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span className="entChip" style={{ width: 28, height: 28, borderRadius: 8, background: C.card, display: "grid", placeItems: "center", flexShrink: 0 }}>{cardIcon("vault", 16, C.violet)}</span>
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

            {/* RULE 7 footer */}
            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
                개수·기준시각 = 실측 사실
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

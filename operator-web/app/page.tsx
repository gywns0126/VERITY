"use client"
// 알파파운더 v2 밀집 터미널 — 승인 목업(토스 기반 3컬럼) 실앱 포팅 (PM 2026-08-03 "디자인 롤백?" 정정).
// 좌 레일=관심·보유(실시간)+긴급 / 중앙=파이프라인→검색→추천→중용→제어판 / 우 레일=3종LLM+검증.
// 상단=지수 스트립 · 하단=매크로 티커 · 상담=우하단 도크 · 키보드 '/'=검색 · 테마 토글.
import { useEffect, useState } from "react"
import { useDark, palette, FONT, NUM, type Palette } from "@/lib/theme"
import AuthPanel from "./components/AuthPanel"
import MarketStrip from "./components/MarketStrip"
import BottomTicker from "./components/BottomTicker"
import AlertsSection from "./components/AlertsSection"
import StockSearch from "./components/StockSearch"
import OperatorPicks from "./components/OperatorPicks"
import TriSynthesisPanel from "./components/TriSynthesisPanel"
import VerificationPanel from "./components/VerificationPanel"
import RealtimeQuotes from "./components/RealtimeQuotes"
import ControlPanel from "./components/ControlPanel"
import ModerationPanel from "./components/ModerationPanel"
import ChatDock from "./components/ChatDock"

const PIPE: Array<[string, string]> = [
    ["스캔", "5,000"], ["거름망", "후보 25"], ["Brain+3LLM", "판단"], ["중용", "사이징"],
]

export default function Home() {
    const dark = useDark()
    const c = palette(dark)
    const [mounted, setMounted] = useState(false)

    useEffect(() => {
        setMounted(true)
        // 키보드: '/' = 검색 포커스 (입력 중이 아닐 때)
        function onKey(e: KeyboardEvent) {
            const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
            if (e.key === "/" && tag !== "input" && tag !== "textarea") {
                e.preventDefault()
                document.getElementById("af-search")?.focus()
            }
        }
        window.addEventListener("keydown", onKey)
        return () => window.removeEventListener("keydown", onKey)
    }, [])

    function toggleTheme() {
        const root = document.documentElement
        const cur = root.getAttribute("data-theme")
        const isDark = cur ? cur === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches
        const next = isDark ? "light" : "dark"
        root.setAttribute("data-theme", next)
        try {
            localStorage.setItem("verity_theme", next)
        } catch {}
        window.dispatchEvent(new Event("verity-theme-changed"))
    }

    return (
        <main style={{ minHeight: "100vh", background: c.bg, color: c.ink, fontFamily: FONT, WebkitFontSmoothing: "antialiased" }}>
            {/* 상단 바 */}
            <div style={{ position: "sticky", top: 0, zIndex: 40, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "11px 18px", background: c.card, boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                    <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.02em" }}>알파<span style={{ color: c.vt }}>파운더</span></span>
                    <span style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11, color: c.faint }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: c.green, boxShadow: `0 0 0 3px ${c.greenS}` }} />
                        자동 파이프라인 가동 · Brain=가설(N&lt;252)
                    </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ font: `600 10px ${FONT}`, color: c.faint, background: c.hi, borderRadius: 5, padding: "3px 6px" }}>/</span>
                    <span style={{ fontSize: 10.5, color: c.faint }}>검색</span>
                    {mounted ? (
                        <button onClick={toggleTheme} style={{ border: "none", background: c.hi, color: c.sub, borderRadius: 999, padding: "6px 12px", fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: FONT }}>
                            테마 전환
                        </button>
                    ) : null}
                </div>
            </div>

            <div style={{ maxWidth: 1440, margin: "0 auto", padding: "12px 18px 20px" }}>
                <AuthPanel />
                <MarketStrip />

                <div className="af-term">
                    {/* 좌 레일 — 지금 */}
                    <aside className="af-rail">
                        <RailTitle c={c} t="관심 · 보유" n="실시간 · 본인 KIS" />
                        <RealtimeQuotes />
                        <RailTitle c={c} t="긴급 공시·이벤트" n="고영향 사실" />
                        <AlertsSection maxItems={5} />
                    </aside>

                    {/* 중앙 — 판단·구성 척추 */}
                    <section className="af-center">
                        <div style={{ background: c.card, borderRadius: 14, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", padding: "11px 14px" }}>
                            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, marginBottom: 9, flexWrap: "wrap" }}>
                                <span style={{ fontSize: 13, fontWeight: 800 }}>오늘의 자동 선별</span>
                                <span style={{ fontSize: 10, color: c.faint }}>토스=당신이 고름 · 여기=최종 결정 전 과정 자동</span>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                                {PIPE.map(([l, n], i) => (
                                    <span key={l} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                        <span style={{ display: "flex", flexDirection: "column", gap: 1, background: i === PIPE.length - 1 ? c.vtS : c.hi, borderRadius: 9, padding: "6px 10px" }}>
                                            <span style={{ fontSize: 9.5, fontWeight: 700, color: i === PIPE.length - 1 ? c.vt : c.sub }}>{l}</span>
                                            <span style={{ fontSize: 11.5, fontWeight: 800, ...NUM }}>{n}</span>
                                        </span>
                                        {i < PIPE.length - 1 ? <span style={{ color: c.faint, fontSize: 11 }}>→</span> : null}
                                    </span>
                                ))}
                            </div>
                        </div>
                        <StockSearch />
                        <OperatorPicks />
                        <ModerationPanel />
                        <ControlPanel />
                    </section>

                    {/* 우 레일 — 선택 종목 판단 + 검증 */}
                    <aside className="af-rail">
                        <RailTitle c={c} t="선택 종목 — 3종 LLM 종합" n="검색·클릭 시 전환" />
                        <TriSynthesisPanel />
                        <RailTitle c={c} t="검증" n="LLM 못 가지는 자기 trail" />
                        <VerificationPanel />
                    </aside>
                </div>
            </div>

            <BottomTicker />
            <ChatDock />
        </main>
    )
}

function RailTitle({ c, t, n }: { c: Palette; t: string; n: string }) {
    return (
        <div style={{ display: "flex", alignItems: "baseline", gap: 7, padding: "0 2px" }}>
            <span style={{ fontSize: 12.5, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>{t}</span>
            <span style={{ fontSize: 10, color: c.faint }}>{n}</span>
        </div>
    )
}

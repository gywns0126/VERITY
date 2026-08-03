"use client"
// 알파파운더 v3.1 — 개인 AI 분석 종합 터미널 (승인 목업 fd9b80ed 정합, PM 2026-08-03).
// 문법 종합: Bloomberg(밀도·링크그룹·커맨드바) + 토스(위계·쉬운말) + 국내 HTS(호가 래더·체결강도)
//   + 기관 OMS(블로터·계좌 헤드업). 7결함 전면 반영: ①토스 로고 ②3종 LLM(#226) ③sticky 잘림 제거
//   ④tick 실시간 ⑤주문 티켓 ⑥/login 분리 ⑦포트폴리오 최상단.
// 데이터 소유: 이 페이지가 portfolio_full + urgent_alerts 를 1회 fetch → HUD/보유/추천/피드에 배분.
import { useEffect, useState } from "react"
import { useDark, palette, FONT, type Palette } from "@/lib/theme"
import { fetchOperator, fetchPublic } from "@/lib/api"
import { isAuthed } from "@/lib/auth"
import { captureOAuthHash, clearSession, loadSession, refreshIfNeeded } from "@/lib/supabase"
import type { AlertItem, PortfolioFull } from "@/lib/types"
import MarketStrip from "./components/MarketStrip"
import BottomTicker from "./components/BottomTicker"
import StockSearch from "./components/StockSearch"
import AccountHud from "./components/AccountHud"
import HoldingsTable from "./components/HoldingsTable"
import WatchTable from "./components/WatchTable"
import Workspace from "./components/Workspace"
import Blotter from "./components/Blotter"
import PicksTable from "./components/PicksTable"
import FeedPanel, { P0Line } from "./components/FeedPanel"
import ModerationPanel from "./components/ModerationPanel"
import ControlPanel from "./components/ControlPanel"
import VerificationPanel from "./components/VerificationPanel"
import ChatDock from "./components/ChatDock"

export default function Home() {
    const dark = useDark()
    const c = palette(dark)
    const [authed, setAuthed] = useState<boolean | null>(null)
    const [who, setWho] = useState("")
    const [pf, setPf] = useState<PortfolioFull | null>(null)
    const [pfStatus, setPfStatus] = useState<"loading" | "ok" | "error">("loading")
    const [alerts, setAlerts] = useState<AlertItem[]>([])
    const [alertsLoaded, setAlertsLoaded] = useState(false)

    // 인증 게이트 — 미인증 = /login (PM 결함 #6: 메인에 로그인 동거 금지)
    useEffect(() => {
        captureOAuthHash()
        if (!isAuthed()) {
            window.location.replace("/login")
            return
        }
        setAuthed(true)
        setWho(loadSession()?.user_email || "")
        refreshIfNeeded()
        const iv = setInterval(() => refreshIfNeeded(), 60_000)

        function onKey(e: KeyboardEvent) {
            const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
            if (e.key === "/" && tag !== "input" && tag !== "textarea") {
                e.preventDefault()
                document.getElementById("af-search")?.focus()
            }
        }
        window.addEventListener("keydown", onKey)
        return () => {
            clearInterval(iv)
            window.removeEventListener("keydown", onKey)
        }
    }, [])

    // 데이터 1회 소유 fetch — 하위 컴포넌트 중복 fetch 금지
    useEffect(() => {
        if (!authed) return
        let cancelled = false
        fetchOperator<PortfolioFull>("portfolio_full").then((r) => {
            if (cancelled) return
            if (r.ok) {
                setPf(r.data)
                setPfStatus("ok")
            } else {
                setPfStatus("error")
            }
        })
        fetchPublic<{ alerts?: AlertItem[] }>("urgent_alerts.json").then((r) => {
            if (cancelled) return
            setAlerts(r.ok && r.data.alerts ? r.data.alerts : [])
            setAlertsLoaded(true)
        })
        return () => {
            cancelled = true
        }
    }, [authed])

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

    function logout() {
        clearSession()
        window.location.replace("/login")
    }

    if (authed === null) {
        return <main style={{ minHeight: "100vh", background: c.bg }} />
    }

    const holdings = pf?.vams?.holdings || []
    const recs = pf?.recommendations || []
    const holdT = holdings.map((h) => h.ticker)
    const recT = recs.map((r) => String(r.ticker || "")).filter(Boolean)
    const names: Record<string, string> = {}
    holdings.forEach((h) => {
        if (h.name) names[h.ticker] = h.name
    })
    recs.forEach((r) => {
        if (r.ticker && r.name && !names[r.ticker]) names[String(r.ticker)] = r.name
    })

    return (
        <main style={{ minHeight: "100vh", background: c.bg, color: c.ink, fontFamily: FONT, WebkitFontSmoothing: "antialiased" }}>
            {/* R0 커맨드 바 — 브랜드 · 전역 검색 · 인증 칩 · 테마 */}
            <div style={{ position: "sticky", top: 0, zIndex: 40, display: "flex", alignItems: "center", gap: 14, padding: "9px 18px", background: c.card, boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
                <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.02em", flexShrink: 0 }}>
                    알파<span style={{ color: c.vt }}>파운더</span>
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10.5, color: c.faint, flexShrink: 0 }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: c.green, boxShadow: `0 0 0 3px ${c.greenS}` }} />
                    파이프라인 가동
                </span>
                <div style={{ flex: 1, maxWidth: 460, minWidth: 160 }}>
                    <StockSearch floating placeholder="종목 검색 — 이름·티커 ( / )" />
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto", flexShrink: 0 }}>
                    <span style={{ fontSize: 11, color: c.sub, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{who}</span>
                    <button onClick={logout} style={chip(c)}>로그아웃</button>
                    <button onClick={toggleTheme} style={chip(c)}>테마</button>
                </div>
            </div>

            <div style={{ maxWidth: 1560, margin: "0 auto", padding: "12px 18px 20px" }}>
                {/* R1 계좌 헤드업 — 포트폴리오 최상단 (결함 #7) */}
                <AccountHud vams={pf?.vams} status={pfStatus} />

                {/* R2 P0 라인 — 보유 직결 이벤트 있을 때만 */}
                <P0Line alerts={alerts} holdTickers={holdT} />

                {/* R3 시장 스트립 (거시 = 숲) */}
                <MarketStrip />

                <div className="af-term">
                    {/* 좌 — 모니터 (보유 + 관심, 실시간 tick) */}
                    <aside className="af-rail">
                        <HoldingsTable holdings={holdings} status={pfStatus} />
                        <WatchTable />
                    </aside>

                    {/* 중앙 — 워크스페이스 (선택 종목 · 호가 · 주문 · 3종 LLM) + 추천 + 중용 + 제어판 */}
                    <section className="af-center">
                        <Workspace defaultTicker={holdT.find((t) => /^\d{6}$/.test(t)) || "005930"} names={names} />
                        <Blotter />
                        <PicksTable recs={recs} status={pfStatus} />
                        <ModerationPanel />
                        <ControlPanel />
                    </section>

                    {/* 우 — 피드 (3-tier) + 검증 */}
                    <aside className="af-rail">
                        <RailTitle c={c} t="이벤트 피드" n="T1 보유 · T2 후보 · T3 참고" />
                        <FeedPanel alerts={alerts} holdTickers={holdT} recTickers={recT} loaded={alertsLoaded} />
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

function chip(c: Palette) {
    return {
        border: "none",
        background: c.hi,
        color: c.sub,
        borderRadius: 999,
        padding: "6px 12px",
        fontSize: 11,
        fontWeight: 700 as const,
        cursor: "pointer",
        fontFamily: FONT,
    }
}

function RailTitle({ c, t, n }: { c: Palette; t: string; n: string }) {
    return (
        <div style={{ display: "flex", alignItems: "baseline", gap: 7, padding: "0 2px" }}>
            <span style={{ fontSize: 12.5, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>{t}</span>
            <span style={{ fontSize: 10, color: c.faint }}>{n}</span>
        </div>
    )
}

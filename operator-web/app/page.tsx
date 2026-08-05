"use client"
// 알파네스트 오퍼레이터 터미널 v3.2 — 개인 AI 분석 종합 (구명 알파파운더 폐지, PM 2026-08-04).
// v3.2 (PM 2026-08-03): 토스식 섹션 고정 — 넓은 화면 = 뷰포트 고정 + 각 컬럼 내부 스크롤
//   (af-viewport/af-frame, 좁은 화면 = 문서 스크롤 폴백). 데이터 많은 패널(중용·제어판·검증) =
//   /system 페이지 분할. 크립토 카드(TIDE 트랙, Binance 24/7) 추가.
// v3.1: 7결함 반영 — 토스 로고·3종 LLM(#226)·sticky 제거·tick 실시간·주문 티켓·/login 분리·
//   포트폴리오 최상단. 링크그룹 = 행 클릭 → 전 패널 동기(verity-ticker).
import { useEffect, useState } from "react"
import { useDark, palette, FONT } from "@/lib/theme"
import { fetchPortfolioSlim, fetchPublic } from "@/lib/api"
import { isAuthed } from "@/lib/auth"
import { captureOAuthHash, refreshIfNeeded } from "@/lib/supabase"
import type { AlertItem, MarketExplain, PortfolioFull } from "@/lib/types"
import TopBar from "./components/TopBar"
import MarketStrip from "./components/MarketStrip"
import AccountHud from "./components/AccountHud"
import HoldingsTable from "./components/HoldingsTable"
import WatchTable from "./components/WatchTable"
import MacroPanel from "./components/MacroPanel"
import Workspace from "./components/Workspace"
import Blotter from "./components/Blotter"
import PicksTable from "./components/PicksTable"
import FeedPanel, { P0Line } from "./components/FeedPanel"
import NewsTicker, { type NewsItem } from "./components/NewsTicker"
import PanelBoundary from "./components/PanelBoundary"
import BalanceCard from "./components/BalanceCard"
import CandidatesDiff from "./components/CandidatesDiff"

export default function Home() {
    const dark = useDark()
    const c = palette(dark)
    const [authed, setAuthed] = useState<boolean | null>(null)
    const [pf, setPf] = useState<PortfolioFull | null>(null)
    const [pfStatus, setPfStatus] = useState<"loading" | "ok" | "error">("loading")
    const [alerts, setAlerts] = useState<AlertItem[]>([])
    const [alertsLoaded, setAlertsLoaded] = useState(false)

    // 인증 게이트 — 미인증 = /login
    useEffect(() => {
        captureOAuthHash()
        if (!isAuthed()) {
            window.location.replace("/login")
            return
        }
        setAuthed(true)
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
        fetchPortfolioSlim<PortfolioFull>().then((r) => {
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

    // 뉴스 티커 — 금융 필터 수집분만(국내·월가), 교차 배치로 다양성
    const newsItems: NewsItem[] = []
    const kr = (pf?.headlines || []).filter((h) => h && h.title)
    const us = (pf?.bloomberg_google_headlines || []).filter((h) => h && h.title)
    const maxLen = Math.max(kr.length, us.length)
    for (let k = 0; k < maxLen && newsItems.length < 40; k++) {
        if (k < kr.length) newsItems.push({ tag: "국내", title: String(kr[k].title), link: kr[k].link })
        if (k < us.length) newsItems.push({ tag: "월가", title: String(us[k].title), link: us[k].link })
    }

    const explain: MarketExplain = {
        analysis: pf?.daily_report?.market_analysis,
        strategy: pf?.daily_report?.strategy,
        risk: pf?.daily_report?.risk_watch,
        outlook: pf?.daily_report?.tomorrow_outlook,
        tone: pf?.briefing?.tone,
        headline: pf?.briefing?.headline,
    }

    return (
        <main className="af-viewport" style={{ minHeight: "100vh", background: c.bg, color: c.ink, fontFamily: FONT, WebkitFontSmoothing: "antialiased" }}>
            <TopBar active="terminal" />

            <div className="af-frame" style={{ maxWidth: 1560, margin: "0 auto", padding: "12px 18px 10px", boxSizing: "border-box" }}>
                {/* R1 계좌 헤드업 + R2 P0 + R3 시장 — 상단 고정 구역 */}
                <AccountHud vams={pf?.vams} status={pfStatus} />
                <P0Line alerts={alerts} holdTickers={holdT} />
                <MarketStrip explain={explain} />
                <NewsTicker items={newsItems} />

                {/* 3열 — 각 컬럼 내부 스크롤 (토스식 섹션 고정) */}
                <div className="af-term">
                    <aside className="af-rail">
                        <PanelBoundary name="보유">
                            <HoldingsTable holdings={holdings} status={pfStatus} />
                        </PanelBoundary>
                        <PanelBoundary name="관심">
                            <WatchTable />
                        </PanelBoundary>
                        <PanelBoundary name="실계좌">
                            <BalanceCard />
                        </PanelBoundary>
                    </aside>

                    <section className="af-center">
                        <PanelBoundary name="워크스페이스">
                            <Workspace defaultTicker={holdT.find((t) => /^\d{6}$/.test(t)) || "005930"} names={names} />
                        </PanelBoundary>
                        <PanelBoundary name="블로터">
                            <Blotter />
                        </PanelBoundary>
                        <PanelBoundary name="추천">
                            <PicksTable recs={recs} status={pfStatus} />
                        </PanelBoundary>
                    </section>

                    <aside className="af-rail">
                        <RailTitle t="거시 — 숲" n="레짐 · 지정학 · 속보" ink={c.ink} faint={c.faint} />
                        <PanelBoundary name="거시">
                            <MacroPanel data={pf} />
                        </PanelBoundary>
                        <PanelBoundary name="후보변경">
                            <CandidatesDiff />
                        </PanelBoundary>
                        <RailTitle t="이벤트 피드" n="T1 보유 · T2 후보 · T3 참고" ink={c.ink} faint={c.faint} />
                        <PanelBoundary name="피드">
                            <FeedPanel alerts={alerts} holdTickers={holdT} recTickers={recT} loaded={alertsLoaded} />
                        </PanelBoundary>
                    </aside>
                </div>
            </div>

        </main>
    )
}

function RailTitle({ t, n, ink, faint }: { t: string; n: string; ink: string; faint: string }) {
    return (
        <div style={{ display: "flex", alignItems: "baseline", gap: 7, padding: "0 2px", flexShrink: 0 }}>
            <span style={{ fontSize: 12.5, fontWeight: 800, color: ink, letterSpacing: "-0.02em" }}>{t}</span>
            <span style={{ fontSize: 10, color: faint }}>{n}</span>
        </div>
    )
}

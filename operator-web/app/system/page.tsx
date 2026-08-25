"use client"
// /system — 구성 · 검증 페이지 (PM 2026-08-03 "데이터가 많으면 페이지 분할").
// 터미널(/)=실시간 운용(보유·호가·주문·추천·피드) / 여기=낮은 빈도·높은 밀도(중용 목표비중 ·
// 매매기준 제어판 · 검증 trail). 문서 스크롤 페이지.
//
// 2026-08-12 — 구 프레이머 배리티 `/admin` 5개 카드 이관처(PM 지시). 콕핏 · 시스템 맵 · 자본 path ·
// AI 사용량 · Brain 관측. 이관 후 라이브 프레이머 프로젝트는 unpublish 대상(PM 액션).
// 🚨 데이터 1회 소유 fetch — 하위 컴포넌트 중복 fetch 금지(터미널 페이지와 같은 규율).
//    자체 fetch 는 blob 소스인 콕핏·시스템 맵과 authed 탭 전환형인 Brain 관측만 예외로 둔다.
import { useEffect, useState } from "react"
import { useDark, palette, FONT } from "@/lib/theme"
import { isAuthed } from "@/lib/auth"
import { fetchPortfolioSlim } from "@/lib/api"
import { captureOAuthHash, refreshIfNeeded } from "@/lib/supabase"
import type { PortfolioFull } from "@/lib/types"
import TopBar from "../components/TopBar"
import ModerationPanel from "../components/ModerationPanel"
import ControlPanel from "../components/ControlPanel"
import VerificationPanel from "../components/VerificationPanel"
import CockpitCard from "../components/CockpitCard"
import SystemMapCard from "../components/SystemMapCard"
import CapitalPathCard from "../components/CapitalPathCard"
import GateProgressPanel from "../components/GateProgressPanel"
import AiUsageCard from "../components/AiUsageCard"
import BrainMonitorPanel from "../components/BrainMonitorPanel"
import PanelBoundary from "../components/PanelBoundary"

export default function SystemPage() {
    const dark = useDark()
    const c = palette(dark)
    const [authed, setAuthed] = useState<boolean | null>(null)
    const [pf, setPf] = useState<PortfolioFull | null>(null)

    useEffect(() => {
        captureOAuthHash()
        if (!isAuthed()) {
            window.location.replace("/login")
            return
        }
        setAuthed(true)
        refreshIfNeeded()
        const iv = setInterval(() => refreshIfNeeded(), 60_000)
        return () => clearInterval(iv)
    }, [])

    useEffect(() => {
        if (!authed) return
        let cancelled = false
        fetchPortfolioSlim<PortfolioFull>().then((r) => {
            if (!cancelled && r.ok) setPf(r.data)
        })
        return () => {
            cancelled = true
        }
    }, [authed])

    if (authed === null) {
        return <main style={{ minHeight: "100vh", background: c.bg }} />
    }

    return (
        <main style={{ minHeight: "100vh", background: c.bg, color: c.ink, fontFamily: FONT, WebkitFontSmoothing: "antialiased" }}>
            <TopBar active="system" />
            <div style={{ maxWidth: 1560, margin: "0 auto", padding: "14px 18px 28px", display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(380px, 100%), 1fr))", gap: 12, alignItems: "start" }}>
                    <PanelBoundary name="운영 콕핏">
                        <CockpitCard />
                    </PanelBoundary>
                    <PanelBoundary name="한눈에 보기">
                        <SystemMapCard />
                    </PanelBoundary>
                    <PanelBoundary name="실자금 게이트">
                        <GateProgressPanel vams={pf?.vams} />
                    </PanelBoundary>
                    <PanelBoundary name="자본 path">
                        <CapitalPathCard vams={pf?.vams} />
                    </PanelBoundary>
                    <PanelBoundary name="AI 사용량">
                        <AiUsageCard cost={pf?.cost_monitor} brainQuality={pf?.brain_quality} />
                    </PanelBoundary>
                </div>

                <PanelBoundary name="Brain 관측">
                    <BrainMonitorPanel postmortem={pf?.postmortem} />
                </PanelBoundary>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(380px, 100%), 1fr))", gap: 12, alignItems: "start" }}>
                    <ModerationPanel />
                    <ControlPanel />
                    <VerificationPanel />
                </div>
            </div>
        </main>
    )
}

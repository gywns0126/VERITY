"use client"
// 홈 콕핏 셸 — 워크플로 IA: ①지금 ②판단 ③구성(척추) ④검증. 공개 알파네스트 디자인 전면 참고.
// ②판단 = 검색(입구)→3종 LLM 종합→추천. ①③④ 는 순차 포팅.
import { useDark, palette, FONT, type Palette } from "@/lib/theme"
import AlertsSection from "./components/AlertsSection"
import StockSearch from "./components/StockSearch"
import OperatorPicks from "./components/OperatorPicks"
import TriSynthesisPanel from "./components/TriSynthesisPanel"
import VerificationPanel from "./components/VerificationPanel"
import RealtimeQuotes from "./components/RealtimeQuotes"
import ChatConsult from "./components/ChatConsult"
import ControlPanel from "./components/ControlPanel"
import AuthPanel from "./components/AuthPanel"
import ModerationPanel from "./components/ModerationPanel"

export default function Home() {
    const dark = useDark()
    const c = palette(dark)
    return (
        <main
            style={{
                minHeight: "100vh",
                background: c.bg,
                color: c.ink,
                fontFamily: FONT,
                WebkitFontSmoothing: "antialiased",
            }}
        >
            <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 20px 96px" }}>
                <header style={{ marginBottom: 22 }}>
                    <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.02em", color: c.ink }}>알파파운더</div>
                    <div style={{ fontSize: 12, color: c.faint, marginTop: 4 }}>
                        워크플로 콕핏 · 지금 → 판단 → 구성 → 검증 · Brain=가설(N&lt;252)
                    </div>
                </header>

                <AuthPanel />

                <Section c={c} title="① 지금" note="실시간 시세 · 본인 KIS">
                    <RealtimeQuotes />
                </Section>

                <Section c={c} title="긴급 공시·이벤트" note="임원·대주주 대량매매 등 고영향 사실">
                    <AlertsSection />
                </Section>

                <Section c={c} title="② 판단" note="검색 → 3종 LLM 종합 → 추천">
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                        <StockSearch />
                        <TriSynthesisPanel />
                        <OperatorPicks />
                    </div>
                </Section>

                <Section c={c} title="③ 구성 (척추)" note="매매 기준 제어판 · 중용 사이징">
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        <ModerationPanel />
                        <ControlPanel />
                    </div>
                </Section>

                <Section c={c} title="④ 검증" note="학습루프·팩터건강·IC·2027 게이트">
                    <VerificationPanel />
                </Section>

                <Section c={c} title="상담" note="Brain 그라운딩 · 종목·전략 Q&A">
                    <ChatConsult />
                </Section>
            </div>
        </main>
    )
}

function Section({ c, title, note, children }: { c: Palette; title: string; note: string; children: React.ReactNode }) {
    return (
        <section style={{ marginBottom: 26 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
                <h2 style={{ fontSize: 15, fontWeight: 800, margin: 0, letterSpacing: "-0.02em", color: c.ink }}>{title}</h2>
                <span style={{ fontSize: 11, color: c.faint }}>{note}</span>
            </div>
            {children}
        </section>
    )
}


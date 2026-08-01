"use client"
// 홈 콕핏 셸 — 워크플로 IA: ①지금 ②판단 ③구성(척추) ④검증. 공개 알파네스트 디자인 전면 참고.
// ②판단 = 검색(입구)→3종 LLM 종합→추천. ①③④ 는 순차 포팅.
import { useDark, palette, FONT, type Palette } from "@/lib/theme"
import AlertPopup from "./components/AlertPopup"
import StockSearch from "./components/StockSearch"
import OperatorPicks from "./components/OperatorPicks"
import TriSynthesisPanel from "./components/TriSynthesisPanel"
import VerificationPanel from "./components/VerificationPanel"
import RealtimeQuotes from "./components/RealtimeQuotes"

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
                    <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.02em", color: c.ink }}>VERITY 오퍼레이터</div>
                    <div style={{ fontSize: 12, color: c.faint, marginTop: 4 }}>
                        워크플로 콕핏 · 지금 → 판단 → 구성 → 검증 · Brain=가설(N&lt;252)
                    </div>
                </header>

                <Section c={c} title="① 지금" note="실시간 시세·고영향 이벤트">
                    <RealtimeQuotes />
                </Section>

                <Section c={c} title="② 판단" note="검색 → 3종 LLM 종합 → 추천">
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                        <StockSearch />
                        <TriSynthesisPanel />
                        <OperatorPicks />
                    </div>
                </Section>

                <Section c={c} title="③ 구성 (척추)" note="중용 스캔→깔때기→사이징">
                    <Placeholder c={c} text="중용 포트폴리오 — US 일봉(#8)+사전등록 상수 승인 대기." />
                </Section>

                <Section c={c} title="④ 검증" note="학습루프·팩터건강·IC·2027 게이트">
                    <VerificationPanel />
                </Section>
            </div>

            <AlertPopup />
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

function Placeholder({ c, text }: { c: Palette; text: string }) {
    return (
        <div style={{ background: c.card, borderRadius: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", padding: "18px 20px", fontSize: 13, color: c.sub }}>
            {text}
        </div>
    )
}

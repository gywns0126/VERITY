import AlertPopup from "./components/AlertPopup"

// 홈 콕핏 셸 — 워크플로 IA: ①지금 ②판단 ③구성(척추) ④검증.
// v1 스캐폴드: ①지금(긴급 팝업)만 라이브. ②③④ 는 포팅/빌드 진행하며 채운다.
export default function Home() {
    return (
        <main
            style={{
                maxWidth: 1200,
                margin: "0 auto",
                padding: "24px 20px 80px",
                fontFamily:
                    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', system-ui, sans-serif",
            }}
        >
            <header style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.02em" }}>VERITY 오퍼레이터</div>
                <div style={{ fontSize: 12, opacity: 0.6, marginTop: 4 }}>
                    워크플로 콕핏 · 지금 → 판단 → 구성 → 검증 · Brain=가설(N&lt;252)
                </div>
            </header>

            {/* ① 지금 — 무슨 일 있나 (긴급 팝업은 전역 오버레이) */}
            <Section title="① 지금" note="고영향 이벤트·브리핑">
                <Placeholder text="긴급 팝업 라이브(우하단). 브리핑 카드는 포팅 중." />
            </Section>

            {/* ② 판단 — 추천·검색·리포트·3종 LLM 종합 */}
            <Section title="② 판단" note="추천·검색·심층·3종 LLM">
                <Placeholder text="OperatorPicks·StockSearch·TriSynthesisPanel 포팅 대기." />
            </Section>

            {/* ③ 구성 — 척추 (중용 스캔→깔때기→사이징) */}
            <Section title="③ 구성 (척추)" note="중용 스캔→깔때기→사이징">
                <Placeholder text="중용 포트폴리오 — US 일봉(#8)+사전등록 상수 승인 대기." />
            </Section>

            {/* ④ 검증 — N 진척·VAMS·IC 게이트 항상 노출 */}
            <Section title="④ 검증" note="N 진척·VAMS·2027 게이트">
                <Placeholder text="검증 trail 패널 포팅 대기." />
            </Section>

            <AlertPopup />
        </main>
    )
}

function Section({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
    return (
        <section style={{ marginBottom: 22 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
                <h2 style={{ fontSize: 15, fontWeight: 800, margin: 0, letterSpacing: "-0.02em" }}>{title}</h2>
                <span style={{ fontSize: 11, opacity: 0.5 }}>{note}</span>
            </div>
            {children}
        </section>
    )
}

function Placeholder({ text }: { text: string }) {
    return (
        <div
            style={{
                border: "1px dashed rgba(128,128,128,0.3)",
                borderRadius: 14,
                padding: "18px 16px",
                fontSize: 13,
                opacity: 0.65,
            }}
        >
            {text}
        </div>
    )
}

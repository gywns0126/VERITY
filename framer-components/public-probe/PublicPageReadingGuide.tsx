import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, type CSSProperties } from "react"

type GuideMode = "market" | "disclosure" | "nest"

interface Props {
    mode: GuideMode
    defaultOpen: boolean
    dark: boolean
}

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const LIGHT = {
    card: "#ffffff", card2: "#f8f9fa", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff",
}
const DARK = {
    card: "#171c23", card2: "#11161c", ink: "#e3e7ec", sub: "#a3acb8", faint: "#7f8a99",
    line: "#29313b", violet: "#aa9cff", violetSoft: "#211d38",
}

const GUIDES = {
    market: {
        eyebrow: "시장 읽기",
        title: "시장부터 종목까지 읽는 순서",
        summary: "시장 지표는 종목의 방향을 대신 결정하지 않습니다. 같은 기준시각의 큰 환경부터 자금 이동, 개별 종목 순서로 좁혀 보세요.",
        steps: [
            ["시장 온도", "금리·환율·원자재·주요 지수의 기준시각과 방향을 먼저 확인합니다."],
            ["자금 이동", "히트맵과 ETF 설정·환매를 함께 보고 어느 지역·업종으로 자금이 이동했는지 확인합니다."],
            ["일정과 제도", "IPO 일정과 채권 국면이 현재 수치와 시차가 있는 자료인지 확인합니다."],
            ["개별 종목", "시장 배경을 확인한 뒤 종목 페이지에서 실적·수급·공시가 같은 방향인지 비교합니다."],
        ],
        caution: "함께 볼 것: 기준시각 + 단위 + 자금 흐름. 시장 상승을 모든 종목의 상승 근거로 해석하지 않습니다.",
        links: [["종목 확인", "/stock"], ["공시 일정", "/disclosure"], ["분석 근거", "/glassbox"]],
    },
    disclosure: {
        eyebrow: "공시 읽기",
        title: "일정에서 원문까지 읽는 순서",
        summary: "공시 제목은 출발점입니다. 예정일과 실제 접수, 정정 여부, 원문 내용을 나눠 확인하세요.",
        steps: [
            ["예정 일정", "캘린더에서 실적·배당·IPO 등 앞으로 확인할 날짜를 찾습니다."],
            ["실제 접수", "피드에서 접수일·공시 유형·정정 표시를 확인합니다."],
            ["최신 원문", "정정 공시가 있으면 최초 문서가 아니라 가장 최근 원문을 확인합니다."],
            ["종목 맥락", "같은 종목의 실적·수급·기존 공시 이력과 함께 봅니다."],
        ],
        caution: "함께 볼 것: 접수일 + 사건 기준일 + 정정 여부. 색과 유형은 일반적 분류이며 실제 영향의 크기를 뜻하지 않습니다.",
        links: [["종목 맥락", "/stock"], ["시장 환경", "/market"], ["분석 근거", "/glassbox"]],
    },
    nest: {
        eyebrow: "보유 맥락 읽기",
        title: "자본 규모보다 먼저 확인할 순서",
        summary: "자본 규모는 무엇을 살지보다 확인 순서를 바꿉니다. 경험이 적을수록 평가손익보다 입력값·기준일·분모를 먼저 확인하세요.",
        steps: [
            ["입력값", "수량·평균단가·통화가 실제 계좌와 맞는지 먼저 확인합니다."],
            ["집중도", "자본이 클수록 단일 종목·업종·지역 집중과 현금화 가능성을 먼저 확인합니다."],
            ["평가손익", "현재가 기준일과 환율 기준일을 확인한 뒤 손익을 읽습니다."],
            ["공시·세금 사실", "보유 종목 공시와 세금 기준일을 별도 사실로 확인하고 예상 수익과 섞지 않습니다."],
        ],
        caution: "함께 볼 것: 원가 분모 + 가격·환율 기준일 + 집중도. 자본 규모나 경험 수준만으로 위험성향과 적합 자산을 판정하지 않습니다.",
        links: [["종목 확인", "/stock"], ["보유 종목 공시", "/disclosure"], ["시장 환경", "/market"]],
    },
} as const

/**
 * 정적 페이지 안내. 데이터 요청·점수·추천·LLM 해설을 추가하지 않는다.
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 */
export default function PublicPageReadingGuide(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [open, setOpen] = useState(() => onCanvas || !!props.defaultOpen)
    const guide = GUIDES[props.mode] || GUIDES.market
    const C = props.dark ? DARK : LIGHT
    const shell: CSSProperties = { width: "100%", padding: "0 clamp(12px, 2vw, 18px)", boxSizing: "border-box", fontFamily: FONT, color: C.ink }

    return (
        <div style={shell}>
            <section style={{ background: C.card, borderRadius: 16, padding: 16, boxSizing: "border-box", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <button
                    type="button"
                    onClick={() => setOpen((value) => !value)}
                    aria-expanded={open}
                    aria-controls={`page-reading-guide-${props.mode}`}
                    style={{ width: "100%", border: 0, padding: 0, background: "transparent", color: C.ink, fontFamily: FONT, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, textAlign: "left" }}
                >
                    <span style={{ minWidth: 0 }}>
                        <span style={{ display: "block", color: C.violet, fontSize: 10.5, fontWeight: 800 }}>{guide.eyebrow}</span>
                        <span style={{ display: "block", marginTop: 3, fontSize: 15, fontWeight: 800, letterSpacing: "-0.25px" }}>{guide.title}</span>
                    </span>
                    <span style={{ flexShrink: 0, color: C.violet, background: C.violetSoft, borderRadius: 999, padding: "6px 9px", fontSize: 10.5, fontWeight: 800 }}>{open ? "접기" : "처음이라면 · 펼치기"}</span>
                </button>

                {open ? (
                    <div id={`page-reading-guide-${props.mode}`}>
                        <p style={{ margin: "12px 0 0", color: C.sub, fontSize: 11.5, lineHeight: 1.65 }}>{guide.summary}</p>
                        <ol style={{ margin: "12px 0 0", paddingLeft: 20, display: "grid", gap: 9, color: C.sub, fontSize: 11.5, lineHeight: 1.55 }}>
                            {guide.steps.map(([title, text]) => <li key={title}><b style={{ color: C.ink }}>{title}</b> — {text}</li>)}
                        </ol>
                        <div style={{ marginTop: 12, padding: "9px 10px", borderRadius: 10, background: C.card2, color: C.faint, fontSize: 10.5, lineHeight: 1.55 }}>{guide.caution}</div>
                        <nav aria-label="다음으로 볼 페이지" style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
                            <span style={{ color: C.faint, fontSize: 10.5, fontWeight: 800 }}>다음으로 볼 곳</span>
                            {guide.links.map(([label, path]) => <a key={path} href={path} style={{ color: C.violet, background: C.violetSoft, borderRadius: 999, padding: "5px 9px", fontSize: 10.5, fontWeight: 800, textDecoration: "none" }}>{label}</a>)}
                        </nav>
                    </div>
                ) : null}
            </section>
        </div>
    )
}

addPropertyControls(PublicPageReadingGuide, {
    mode: {
        type: ControlType.Enum,
        title: "Page",
        options: ["market", "disclosure", "nest"],
        optionTitles: ["Market", "Disclosure", "Nest"],
        defaultValue: "market",
    },
    defaultOpen: { type: ControlType.Boolean, title: "Default Open", defaultValue: false },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false },
})

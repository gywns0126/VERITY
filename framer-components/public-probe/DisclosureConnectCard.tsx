import { addPropertyControls, ControlType } from "framer"

/**
 * 공시-first 연결 카드 — 골든구스 공개 probe (토스 디자인 언어)
 *
 * "내 종목에 방금 무슨 일이 일어났고, 왜 중요한지(우리 데이터로 *연결*)를 가장 먼저."
 * 공시(DART) = 원천이라 기사보다 빠름. 차별 = AI 요약 아님 → 오버행·수급·*과거 패턴* 연결.
 *
 * 🚨 점수·등급·추천·verdict 없음. "사라/팔라" 없음. 사실을 *모아서 연결*만 하고 판단은 사용자.
 *    (RULE 7 미검증 산식 비노출 + 유사투자자문 회피. 검증된 신호는 2027 별도 tier.)
 *    named 비판 아님 — 전부 공시/시세에서 나온 *사실*.
 *
 * Framer ID xmniHtS · insertUrl framer.com/m/DisclosureConnectCard-I3PHfy.js · 생성 2026-06-16.
 * 무료 Framer 프로젝트용 self-data(mock) 디자인 probe. 목적 = "공시 + 연결" 프레임이 먹히나 테스트.
 */

const C = {
  bg: "#f2f4f6",
  card: "#ffffff",
  ink: "#191f28",
  sub: "#4e5968",
  faint: "#8b95a1",
  line: "#e5e8eb",
  red: "#f04452",
  redSoft: "#fff0f1",
  amber: "#ff9500",
  amberSoft: "#fff6e9",
  blue: "#3182f6",
  blueSoft: "#eef4ff",
  green: "#15c47e",
  greenSoft: "#eafaf3",
  violet: "#6c5ce7",
  violetSoft: "#f0edff",
}

type Tone = "risk" | "flow" | "cal" | "good"
type Conn = { tone: Tone; tag: string; fact: string }
type Item = {
  name: string
  ticker: string
  ago: string
  disclosure: string
  dtone: "risk" | "good"
  conns: Conn[]
  pattern: string // 킬러 = "처음 아님" (사실, 추천 아님)
}

const TONE: Record<Tone, { fg: string; bg: string }> = {
  risk: { fg: C.red, bg: C.redSoft },
  flow: { fg: C.blue, bg: C.blueSoft },
  cal: { fg: C.amber, bg: C.amberSoft },
  good: { fg: C.green, bg: C.greenSoft },
}

const ITEMS: Item[] = [
  {
    name: "에코프로비엠",
    ticker: "247540",
    ago: "8분 전",
    disclosure: "유상증자 결정 · 3,200억",
    dtone: "risk",
    conns: [
      { tone: "risk", tag: "오버행", fact: "발행주식의 6.2% 희석" },
      { tone: "flow", tag: "수급", fact: "외국인 3일 연속 순매도 −142만주" },
      { tone: "cal", tag: "일정", fact: "전환사채 전환가능 D-9" },
    ],
    pattern: "2015년 이후 유상증자 3번째 — 직전 2회 공시 후 30일 −18% · −24% (사실)",
  },
  {
    name: "엠케이전자",
    ticker: "033160",
    ago: "23분 전",
    disclosure: "단일판매·공급계약 · 1,840억(매출 21%)",
    dtone: "good",
    conns: [
      { tone: "flow", tag: "수급", fact: "기관 2일 순매수 +38만주" },
      { tone: "cal", tag: "일정", fact: "실적발표 D-5" },
    ],
    pattern: "이 회사 공급계약 공시 5회 — 평균 공시당일 +6.1% (사실, 추천 아님)",
  },
]

export default function DisclosureConnectCard(props: { width?: number }) {
  const width = props.width || 380

  return (
    <div
      style={{
        width: width,
        fontFamily: "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif",
        background: C.bg,
        borderRadius: 24,
        padding: 16,
        boxSizing: "border-box",
        color: C.ink,
      }}
    >
      {/* 헤더 */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "4px 4px 12px" }}>
        <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: -0.4 }}>📡 내 종목 속보</div>
        <div style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>공시 + 연결</div>
      </div>

      {ITEMS.map((it, i) => {
        const dt = it.dtone === "risk" ? TONE.risk : TONE.good
        return (
          <div
            key={i}
            style={{
              background: C.card,
              borderRadius: 20,
              padding: 16,
              marginBottom: 12,
              boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
            }}
          >
            {/* 종목 + 시각 */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: -0.3 }}>{it.name}</span>
                <span style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>{it.ticker}</span>
              </div>
              <span style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>{it.ago}</span>
            </div>

            {/* 공시 (훅) */}
            <div
              style={{
                background: dt.bg,
                color: dt.fg,
                borderRadius: 12,
                padding: "10px 12px",
                fontSize: 14,
                fontWeight: 700,
                marginBottom: 12,
                letterSpacing: -0.2,
              }}
            >
              {it.disclosure}
            </div>

            {/* 연결 (차별) */}
            <div style={{ fontSize: 11, fontWeight: 700, color: C.faint, marginBottom: 8, letterSpacing: 0.2 }}>
              왜 중요한지 — 연결된 사실
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 12 }}>
              {it.conns.map((c, j) => {
                const t = TONE[c.tone]
                return (
                  <div key={j} style={{ display: "flex", alignItems: "center", gap: 9 }}>
                    <span
                      style={{
                        flexShrink: 0,
                        background: t.bg,
                        color: t.fg,
                        fontSize: 11,
                        fontWeight: 800,
                        padding: "3px 8px",
                        borderRadius: 7,
                        minWidth: 42,
                        textAlign: "center",
                      }}
                    >
                      {c.tag}
                    </span>
                    <span style={{ fontSize: 13.5, color: C.sub, fontWeight: 600, letterSpacing: -0.2 }}>{c.fact}</span>
                  </div>
                )
              })}
            </div>

            {/* 과거 패턴 — 킬러("처음 아님") */}
            <div
              style={{
                background: C.violetSoft,
                borderRadius: 12,
                padding: "10px 12px",
                display: "flex",
                gap: 8,
                alignItems: "flex-start",
              }}
            >
              <span style={{ fontSize: 13 }}>🕰️</span>
              <div>
                <div style={{ fontSize: 11, fontWeight: 800, color: C.violet, marginBottom: 2 }}>이게 처음이 아님</div>
                <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 600, lineHeight: 1.45, letterSpacing: -0.2 }}>
                  {it.pattern}
                </div>
              </div>
            </div>
          </div>
        )
      })}

      {/* 유리박스 정직 라벨 */}
      <div
        style={{
          textAlign: "center",
          fontSize: 11,
          color: C.faint,
          fontWeight: 600,
          padding: "6px 8px 2px",
          lineHeight: 1.5,
        }}
      >
        사실·연결만 — 점수·추천 아님 · VERITY 검증 진행 중
      </div>
    </div>
  )
}

addPropertyControls(DisclosureConnectCard, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380, min: 320, max: 720 },
})

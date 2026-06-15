import { addPropertyControls, ControlType } from "framer"
import { useState } from "react"

/**
 * 종목 리스크 레이더 — 공개 probe (토스 디자인 언어)
 *
 * "이 종목 지금 무슨 일이 일어나고 있나?" 를 한 화면 한 답으로.
 * 흩어진 공시(DART)·일정을 모아 → 리스크 사실 + 호재성 사실, 둘 다 *사실+일정만*.
 *
 * 🚨 점수·등급·추천 없음. "팔아라/사라" 없음. 사실과 일정만 보여주고 판단은 사용자.
 *    (RULE 7 미검증 산식 비노출 + 유사투자자문 회피. 검증된 신호는 2027 별도 tier.)
 *
 * 무료 Framer 프로젝트에 그대로 붙여 쓰는 자체 데이터(mock) 디자인 probe.
 * 목적 = ① 토스급 UX 가 실제로 뽑히나 ② "이 종목 위험한가" 프레임이 먹히나 테스트.
 */

// ── 토스 디자인 토큰 (밝고·부드럽고·큰 글씨) ──
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
}

type Flag = { kind: "risk" | "event"; tone: "high" | "mid" | "info"; tag: string; title: string; detail: string; when: string }

type Stock = { name: string; ticker: string; flags: Flag[]; clean: string[] }

// realistic mock — 3 상태(위험多 / 호재+리스크 / 깨끗)
const STOCKS: Stock[] = [
  {
    name: "에코프로비엠", ticker: "247540",
    flags: [
      { kind: "risk", tone: "high", tag: "오버행", title: "전환사채 전환가능일 임박", detail: "320억 · 유통주식의 4.1%", when: "D-12" },
      { kind: "risk", tone: "mid", tag: "정정공시", title: "정정공시 잦음", detail: "최근 90일 3건", when: "90일" },
      { kind: "event", tone: "info", tag: "수주", title: "대규모 공급계약 공시", detail: "1,840억 · 매출의 12%", when: "6/09" },
    ],
    clean: ["소송 없음", "감사의견 적정"],
  },
  {
    name: "삼성전자", ticker: "005930",
    flags: [
      { kind: "event", tone: "info", tag: "자사주", title: "자사주 매입 발표", detail: "3.0조 · 6개월 분할", when: "6/10" },
    ],
    clean: ["오버행 없음", "소송 없음", "감사의견 적정", "최대주주 매도 없음"],
  },
  {
    name: "코스닥A바이오", ticker: "900000",
    flags: [
      { kind: "risk", tone: "high", tag: "부실", title: "감사의견 '한정'", detail: "계속기업 불확실성 언급", when: "3/20" },
      { kind: "risk", tone: "high", tag: "거버넌스", title: "최대주주 지분 매도", detail: "−3.2%p (장내)", when: "5/28" },
      { kind: "risk", tone: "mid", tag: "오버행", title: "신주인수권(BW) 행사 도래", detail: "유통주식의 8.7%", when: "D-5" },
    ],
    clean: [],
  },
]

const toneColor = (t: Flag["tone"]) =>
  t === "high" ? { fg: C.red, bg: C.redSoft } : t === "mid" ? { fg: C.amber, bg: C.amberSoft } : { fg: C.blue, bg: C.blueSoft }

export default function StockRadarProbe(props: { width?: number }) {
  const [idx, setIdx] = useState(0)
  const s = STOCKS[idx]
  const risks = s.flags.filter((f) => f.kind === "risk")
  const events = s.flags.filter((f) => f.kind === "event")

  const headline =
    risks.length === 0
      ? { icon: "✓", text: "특이 리스크 없음", color: C.green }
      : { icon: "⚠️", text: `주의 신호 ${risks.length}개`, color: risks.some((r) => r.tone === "high") ? C.red : C.amber }

  return (
    <div style={{ width: "100%", background: C.bg, fontFamily: "Pretendard, -apple-system, sans-serif", padding: 16, boxSizing: "border-box" }}>
      {/* 종목 선택 (probe 용) */}
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {STOCKS.map((st, i) => (
          <button
            key={st.ticker}
            onClick={() => setIdx(i)}
            style={{
              border: "none", cursor: "pointer", padding: "7px 13px", borderRadius: 999, fontSize: 13, fontWeight: 600,
              background: i === idx ? C.ink : C.card, color: i === idx ? "#fff" : C.sub,
            }}
          >
            {st.name}
          </button>
        ))}
      </div>

      {/* 카드 */}
      <div style={{ background: C.card, borderRadius: 20, padding: 22, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
        {/* 종목명 */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 18 }}>
          <span style={{ fontSize: 21, fontWeight: 700, color: C.ink, letterSpacing: "-0.4px" }}>{s.name}</span>
          <span style={{ fontSize: 14, color: C.faint, fontWeight: 500 }}>{s.ticker}</span>
        </div>

        {/* 한눈 답 */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 22 }}>
          <span style={{ fontSize: 26 }}>{headline.icon}</span>
          <span style={{ fontSize: 24, fontWeight: 800, color: headline.color, letterSpacing: "-0.6px" }}>{headline.text}</span>
        </div>

        {/* 리스크 섹션 */}
        {risks.map((f, i) => {
          const c = toneColor(f.tone)
          return (
            <div key={i} style={{ display: "flex", gap: 12, padding: "13px 0", borderTop: i === 0 ? `1px solid ${C.line}` : "none" }}>
              <span style={{ flexShrink: 0, alignSelf: "flex-start", fontSize: 12, fontWeight: 700, color: c.fg, background: c.bg, padding: "4px 9px", borderRadius: 7 }}>
                {f.tag}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: C.ink, marginBottom: 2 }}>{f.title}</div>
                <div style={{ fontSize: 13, color: C.sub }}>{f.detail}</div>
              </div>
              <span style={{ flexShrink: 0, fontSize: 13, fontWeight: 700, color: f.tone === "high" ? C.red : C.faint }}>{f.when}</span>
            </div>
          )
        })}

        {/* 호재성 사실 (이벤트) — '사라'가 아니라 '이런 일이 있었다' */}
        {events.length > 0 && (
          <div style={{ marginTop: risks.length ? 6 : 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.faint, margin: "10px 0 2px" }}>관심 이벤트 (사실)</div>
            {events.map((f, i) => (
              <div key={i} style={{ display: "flex", gap: 12, padding: "13px 0", borderTop: `1px solid ${C.line}` }}>
                <span style={{ flexShrink: 0, alignSelf: "flex-start", fontSize: 12, fontWeight: 700, color: C.blue, background: C.blueSoft, padding: "4px 9px", borderRadius: 7 }}>
                  {f.tag}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 600, color: C.ink, marginBottom: 2 }}>{f.title}</div>
                  <div style={{ fontSize: 13, color: C.sub }}>{f.detail}</div>
                </div>
                <span style={{ flexShrink: 0, fontSize: 13, fontWeight: 600, color: C.faint }}>{f.when}</span>
              </div>
            ))}
          </div>
        )}

        {/* 깨끗한 항목 */}
        {s.clean.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16, paddingTop: 16, borderTop: `1px solid ${C.line}` }}>
            {s.clean.map((c, i) => (
              <span key={i} style={{ fontSize: 13, color: C.green, background: C.greenSoft, padding: "5px 11px", borderRadius: 8, fontWeight: 600 }}>
                ✓ {c}
              </span>
            ))}
          </div>
        )}

        {/* 정직 푸터 */}
        <div style={{ marginTop: 18, padding: "12px 14px", background: C.bg, borderRadius: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: C.sub, marginBottom: 3 }}>ⓘ 이건 '팔아라/사라'가 아닙니다</div>
          <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5 }}>
            점수·추천 아님 · 공시 사실과 일정만 · 판단은 직접. 검증된 신호는 별도.
          </div>
        </div>
      </div>

      <div style={{ textAlign: "center", fontSize: 11, color: C.faint, marginTop: 12 }}>
        샘플 데이터 · 디자인 probe
      </div>
    </div>
  )
}

addPropertyControls(StockRadarProbe, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380, min: 320, max: 720 },
})

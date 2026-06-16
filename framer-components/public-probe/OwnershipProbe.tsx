import { addPropertyControls, ControlType } from "framer"
import { useMemo, useState } from "react"

/**
 * 지분구조 유리박스 — 공개 probe (토스 디자인 언어)
 *
 * "이 종목 누가 쥐고 있나?" 를 공정위 공식 공시로 한 화면에.
 * 나무위키가 베끼는 그 원천(공정거래위원회 기업집단포털)을 직접.
 *
 * 🚨 점수·등급·추천 없음. "사라/팔아라" 없음. 공시된 지분 사실만, 판단은 사용자.
 *    (RULE 7 미검증 산식 비노출 + 유사투자자문 회피. §3 공개 경계 = L0 공시 사실.)
 *
 * 데이터 = 공정거래위원회 기업집단포털 OpenAPI(2026 지정) 실호출 검증값.
 *    주주구분(동일인/친족/소속회사) + 지분율 = 법적 강제공시 사실.
 */

// ── 토스 디자인 토큰 (StockRadarProbe 와 동일 언어) ──
const C = {
  bg: "#f2f4f6",
  card: "#ffffff",
  ink: "#191f28",
  sub: "#4e5968",
  faint: "#8b95a1",
  line: "#e5e8eb",
  red: "#f04452",
  amber: "#ff9500",
  blue: "#3182f6",
  blueSoft: "#eef4ff",
  green: "#15c47e",
  greenSoft: "#eafaf3",
  purple: "#8b5cf6",
  purpleSoft: "#f3effe",
}

type Holder = { name: string; type: "동일인" | "친족" | "소속회사" | "자기주식" | "기타"; rate: number }
type Stock = { name: string; ticker: string; group: string; holders: Holder[] }

// 공정위 기업집단포털 2026 지정 — 실호출 검증값 (data/ftc_group_equity.json)
const STOCKS: Stock[] = [
  {
    name: "삼성전자", ticker: "005930", group: "삼성",
    holders: [
      { name: "기타(소액주주 등)", type: "기타", rate: 81.81 },
      { name: "삼성생명보험", type: "소속회사", rate: 7.49 },
      { name: "삼성물산", type: "소속회사", rate: 4.49 },
      { name: "친족", type: "친족", rate: 2.42 },
      { name: "동일인(총수)", type: "동일인", rate: 1.47 },
    ],
  },
  {
    name: "SK하이닉스", ticker: "000660", group: "에스케이",
    holders: [
      { name: "기타(소액주주 등)", type: "기타", rate: 78.87 },
      { name: "SK스퀘어", type: "소속회사", rate: 20.5 },
      { name: "자기주식", type: "자기주식", rate: 0.39 },
    ],
  },
  {
    name: "현대자동차", ticker: "005380", group: "현대자동차",
    holders: [
      { name: "기타(소액주주 등)", type: "기타", rate: 75.12 },
      { name: "현대모비스", type: "소속회사", rate: 17.25 },
      { name: "친족", type: "친족", rate: 4.29 },
      { name: "동일인(총수)", type: "동일인", rate: 2.11 },
    ],
  },
]

const typeStyle = (t: Holder["type"]) =>
  t === "동일인" ? { fg: C.purple, bg: C.purpleSoft }
  : t === "친족" ? { fg: C.purple, bg: C.purpleSoft }
  : t === "소속회사" ? { fg: C.blue, bg: C.blueSoft }
  : t === "자기주식" ? { fg: C.faint, bg: C.bg }
  : { fg: C.faint, bg: C.bg }

export default function OwnershipProbe(props: { width?: number }) {
  const [idx, setIdx] = useState(0)
  const s = STOCKS[idx]

  // 계열 지배지분 = 동일인 + 친족 + 소속회사 합산 (공시 line item 의 단순 합, 자체 판정 아님)
  const controlRate = useMemo(() => {
    const sum = s.holders
      .filter((h) => h.type === "동일인" || h.type === "친족" || h.type === "소속회사")
      .reduce((a, h) => a + h.rate, 0)
    return Math.round(sum * 100) / 100
  }, [s])

  return (
    <div style={{ width: "100%", background: C.bg, fontFamily: "Pretendard, -apple-system, sans-serif", padding: 16, boxSizing: "border-box" }}>
      {/* 종목 선택 */}
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

      <div style={{ background: C.card, borderRadius: 20, padding: 22, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
        {/* 종목명 + 그룹 */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 18 }}>
          <span style={{ fontSize: 21, fontWeight: 700, color: C.ink, letterSpacing: "-0.4px" }}>{s.name}</span>
          <span style={{ fontSize: 14, color: C.faint, fontWeight: 500 }}>{s.ticker}</span>
          <span style={{ marginLeft: "auto", fontSize: 12, fontWeight: 600, color: C.blue, background: C.blueSoft, padding: "4px 9px", borderRadius: 7 }}>
            {s.group} 그룹
          </span>
        </div>

        {/* 한눈 답 — 계열 지배지분 */}
        <div style={{ marginBottom: 18 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span style={{ fontSize: 32, fontWeight: 800, color: C.purple, letterSpacing: "-1px" }}>{controlRate}%</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: C.ink }}>를 총수일가·계열이 보유</span>
          </div>
          <div style={{ fontSize: 12.5, color: C.faint, marginTop: 2 }}>
            동일인 + 친족 + 소속회사 지분 합산 · 나머지 {(100 - controlRate).toFixed(2)}%는 시장
          </div>
        </div>

        {/* 누적 막대 */}
        <div style={{ display: "flex", width: "100%", height: 10, borderRadius: 999, overflow: "hidden", marginBottom: 20 }}>
          {s.holders.map((h, i) => {
            const st = typeStyle(h.type)
            return (
              <div key={i} style={{ width: `${h.rate}%`, height: "100%", background: h.type === "기타" ? C.line : st.fg }} />
            )
          })}
        </div>

        {/* 주주 list */}
        {s.holders.map((h, i) => {
          const st = typeStyle(h.type)
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 0", borderTop: i === 0 ? `1px solid ${C.line}` : "none" }}>
              <span style={{ flexShrink: 0, fontSize: 11.5, fontWeight: 700, color: st.fg, background: st.bg, padding: "4px 9px", borderRadius: 7, minWidth: 52, textAlign: "center" }}>
                {h.type}
              </span>
              <span style={{ flex: 1, minWidth: 0, fontSize: 15, fontWeight: 600, color: C.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {h.name}
              </span>
              <span style={{ flexShrink: 0, fontSize: 15, fontWeight: 700, color: h.type === "기타" ? C.faint : C.ink, fontVariantNumeric: "tabular-nums" }}>
                {h.rate}%
              </span>
            </div>
          )
        })}

        {/* 정직 푸터 */}
        <div style={{ marginTop: 18, padding: "12px 14px", background: C.bg, borderRadius: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: C.sub, marginBottom: 3 }}>ⓘ 공정거래위원회 공식 공시</div>
          <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5 }}>
            기업집단포털 2026 지정 기준 · 법적 강제공시 사실 · 점수·추천 아님, 판단은 직접.
          </div>
        </div>
      </div>

      <div style={{ textAlign: "center", fontSize: 11, color: C.faint, marginTop: 12 }}>
        공정위 실데이터 · 디자인 probe
      </div>
    </div>
  )
}

addPropertyControls(OwnershipProbe, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380, min: 320, max: 720 },
})

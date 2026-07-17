import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

/**
 * 종목 리스크 레이더 — 공개 probe (토스 디자인 언어)
 *
 * "이 종목 지금 무슨 일이 일어나고 있나?" 를 한 화면 한 답으로.
 * 흩어진 공시(DART)·일정을 모아 → 리스크 사실 + 호재성 사실, 둘 다 *사실+일정만*.
 *
 * 🚨 점수·등급·추천 없음. "팔아라/사라" 없음. 사실과 일정만 보여주고 판단은 사용자.
 *    (RULE 7 미검증 산식 비노출 + 유사투자자문 회피. 검증된 신호는 2027 별도 tier.)
 *
 * ── 일반인 모드 (2026-06-17) ──
 *   ① "쉬운 말" 토글 — 켜면 각 사실을 평문 해설로 바꿔 보여줌.
 *      해설은 mock 데이터의 plain 필드에 *사전 작성* (런타임 LLM 호출 0).
 *      RULE 6 정합: LLM narrative 컴포넌트 아님 — 사전 큐레이션 텍스트.
 *   ② 용어 hover/tap — 오버행·전환사채·BW·감사의견 등 일반인이 모르는 용어에
 *      점선 밑줄 → 누르면 뜻 풀이. 사전 = data/verity_terms.json (category=public) 부분집합 인라인.
 *
 * 무료 Framer 프로젝트에 그대로 붙여 쓰는 자체 데이터(mock) 디자인 probe.
 */

// ── 토스 디자인 토큰 (밝고·부드럽고·큰 글씨) ── (LIGHT / DARK 쌍)
const LIGHT = {
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
const DARK = {
  bg: "#16181d",
  card: "#1e2128",
  ink: "#f0f2f5",
  sub: "#b0b8c1",
  faint: "#6b7684",
  line: "#2b2f37",
  red: "#ff6b76",
  redSoft: "#3a1f22",
  amber: "#ffb340",
  amberSoft: "#3a2e1a",
  blue: "#5a9cff",
  blueSoft: "#1b2740",
  green: "#3ddc97",
  greenSoft: "#16322a",
}

// ── 용어 사전 (data/verity_terms.json category=public 부분집합 인라인) ──
// 키 = 화면에 나타나는 표현. 값 = 일반인용 뜻 풀이.
const GLOSSARY: Record<string, string> = {
  오버행:
    "곧 시장에 풀릴 수 있는 대기 매도 물량. 풀리면 주식 수가 늘거나 매도 압력이 생겨 주가에 부담이 될 수 있어요.",
  전환사채:
    "회사가 빌린 돈(채권)을 정해진 가격에 주식으로 바꿀 수 있는 사채. 주식으로 바뀌면 전체 주식 수가 늘어 기존 주주 지분이 옅어질 수 있어요.",
  "신주인수권(BW)":
    "정해진 가격에 새 주식을 살 권리가 붙은 사채(BW). 권리가 행사되면 새 주식이 발행돼 주식 수가 늘고 기존 주주 지분이 옅어져요.",
  신주인수권:
    "정해진 가격에 새 주식을 살 권리. 행사되면 새 주식이 발행돼 주식 수가 늘어요.",
  유상증자:
    "회사가 새 주식을 발행해 투자자에게 돈을 받고 파는 것. 자금은 들어오지만 주식 수가 늘어 기존 주주 1주의 몫이 옅어져요.",
  무상증자:
    "기존 주주에게 공짜로 새 주식을 나눠주는 것. 회사 전체 가치는 그대로라 주당 가격은 늘어난 주식 수만큼 자동 조정돼요.",
  자사주:
    "회사가 보유하거나 사들이는 자기 회사 주식. 매입하면 시중에 도는 주식 수가 줄어 보통 주주에게 우호적인 사실로 봐요.",
  감사의견:
    "회계법인이 재무제표를 믿을 수 있는지 낸 의견. 적정(정상) → 한정 → 부적정 → 의견거절 순으로 나빠지며, '적정'이 아니면 경계 신호예요.",
  "계속기업 불확실성":
    "회사가 앞으로도 정상적으로 영업을 이어갈 수 있을지 의문이 있다는 회계상 경고. 자금난·적자 누적 등이 배경일 수 있어요.",
  최대주주:
    "회사 지분을 가장 많이 가진 주주. 보통 경영을 좌우하며, 이들의 매수·매도는 회사 내부 사정을 비추는 중요한 신호예요.",
  유통주식:
    "시장에서 실제로 거래되는 주식 수. 새 주식이 늘 때 이 수 대비 몇 %인지로 '희석(지분 옅어짐)' 정도를 따져요.",
  공급계약:
    "제품·서비스를 납품하기로 맺은 계약. 규모가 한 해 매출 대비 크면 앞으로 들어올 실적의 기대 요인이에요.",
  수주:
    "납품·공급 계약을 따내는 것. 규모가 매출 대비 크면 앞으로 들어올 실적의 기대 요인이에요.",
  정정공시:
    "이미 낸 공시를 고쳐 다시 내는 것. 잦으면 숫자·내용이 자주 바뀐다는 뜻이라 더 꼼꼼히 확인할 필요가 있어요.",
}

// 긴 표현부터 매칭 (예: "신주인수권(BW)" 가 "신주인수권" 보다 먼저).
const GLOSSARY_KEYS = Object.keys(GLOSSARY).sort((a, b) => b.length - a.length)
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
const TERM_RE = new RegExp(`(${GLOSSARY_KEYS.map(escapeRe).join("|")})`, "g")

type Flag = {
  kind: "risk" | "event"
  tone: "high" | "mid" | "info"
  tag: string
  title: string
  detail: string
  // 쉬운 말 모드에서 detail 을 대체하는 평문 해설 (사전 작성).
  plain: string
  when: string
}

type Stock = { name: string; ticker: string; flags: Flag[]; clean: string[] }

// realistic mock — 3 상태(위험多 / 호재+리스크 / 깨끗)
const STOCKS: Stock[] = [
  {
    name: "에코프로비엠",
    ticker: "247540",
    flags: [
      {
        kind: "risk",
        tone: "high",
        tag: "오버행",
        title: "전환사채 전환가능일 임박",
        detail: "320억 · 유통주식의 4.1%",
        plain:
          "회사가 빌린 돈(320억)을 주식으로 바꿀 수 있는 날이 다가와요. 바뀌면 주식 수가 약 4.1% 늘어, 기존 주주의 몫이 그만큼 옅어질 수 있어요.",
        when: "D-12",
      },
      {
        kind: "risk",
        tone: "mid",
        tag: "정정공시",
        title: "정정공시 잦음",
        detail: "최근 90일 3건",
        plain:
          "이미 낸 공시를 고쳐 다시 낸 게 90일간 3번. 숫자나 내용이 자주 바뀐다는 신호라 더 꼼꼼히 볼 필요가 있어요.",
        when: "90일",
      },
      {
        kind: "event",
        tone: "info",
        tag: "수주",
        title: "대규모 공급계약 공시",
        detail: "1,840억 · 매출의 12%",
        plain:
          "한 해 매출의 12%에 해당하는 1,840억짜리 납품 계약을 따냈어요. 앞으로 들어올 매출이 늘 수 있는 호재성 사실이에요.",
        when: "6/09",
      },
    ],
    clean: ["소송 없음", "감사의견 적정"],
  },
  {
    name: "삼성전자",
    ticker: "005930",
    flags: [
      {
        kind: "event",
        tone: "info",
        tag: "자사주",
        title: "자사주 매입 발표",
        detail: "3.0조 · 6개월 분할",
        plain:
          "회사가 자기 주식을 3조원어치 되사요(6개월에 나눠서). 시중 주식 수가 줄어 보통 주주에게 우호적인 사실이에요.",
        when: "6/10",
      },
    ],
    clean: ["오버행 없음", "소송 없음", "감사의견 적정", "최대주주 매도 없음"],
  },
  {
    name: "코스닥A바이오",
    ticker: "900000",
    flags: [
      {
        kind: "risk",
        tone: "high",
        tag: "부실",
        title: "감사의견 '한정'",
        detail: "계속기업 불확실성 언급",
        plain:
          "회계법인이 재무제표를 '완전히 믿기는 어렵다(한정)'고 했어요. 회사가 계속 영업할 수 있을지 의문이 있다는 뜻이라 위험 신호예요.",
        when: "3/20",
      },
      {
        kind: "risk",
        tone: "high",
        tag: "거버넌스",
        title: "최대주주 지분 매도",
        detail: "−3.2%p (장내)",
        plain:
          "회사를 가장 많이 가진 주주가 지분을 시장에서 3.2%p 팔았어요. 회사를 가장 잘 아는 내부자가 파는 건 보통 경계할 사실이에요.",
        when: "5/28",
      },
      {
        kind: "risk",
        tone: "mid",
        tag: "오버행",
        title: "신주인수권(BW) 행사 도래",
        detail: "유통주식의 8.7%",
        plain:
          "정해진 가격에 새 주식을 살 권리(BW)를 행사할 때가 됐어요. 행사되면 주식 수가 8.7% 늘어, 기존 주주의 몫이 옅어질 수 있어요.",
        when: "D-5",
      },
    ],
    clean: [],
  },
]

function readBodyDark(): boolean {
  if (typeof document === "undefined" || !document.body) return false
  return document.body.dataset.framerTheme === "dark"
}

const toneColor = (C: typeof LIGHT, t: Flag["tone"]) =>
  t === "high"
    ? { fg: C.red, bg: C.redSoft }
    : t === "mid"
    ? { fg: C.amber, bg: C.amberSoft }
    : { fg: C.blue, bg: C.blueSoft }

// ── 용어 칩 (점선 밑줄 + tap/hover 시 뜻 풀이) ──
function TermChip({ term, C }: { term: string; C: typeof LIGHT }) {
  const [open, setOpen] = useState(false)
  const def = GLOSSARY[term]
  if (!def) return <>{term}</>
  return (
    <span style={{ position: "relative", display: "inline" }}>
      <span
        role="button"
        tabIndex={0}
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        style={{
          borderBottom: `1.5px dotted ${C.faint}`,
          cursor: "help",
          color: "inherit",
          fontWeight: "inherit",
        }}
      >
        {term}
      </span>
      {open && (
        <>
          {/* tap 닫기용 투명 backdrop (모바일) */}
          <span
            onClick={(e) => {
              e.stopPropagation()
              setOpen(false)
            }}
            style={{ position: "fixed", inset: 0, zIndex: 40 }}
          />
          <span
            style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              left: 0,
              zIndex: 50,
              display: "block",
              width: 248,
              maxWidth: "78vw",
              background: C.ink,
              color: C.card,
              borderRadius: 12,
              padding: "11px 13px",
              fontSize: 12.5,
              fontWeight: 500,
              lineHeight: 1.55,
              letterSpacing: "-0.1px",
              boxShadow: "0 6px 20px rgba(0,0,0,0.18)",
              whiteSpace: "normal",
              textAlign: "left",
            }}
          >
            <span style={{ fontWeight: 700, display: "block", marginBottom: 3 }}>
              {term}
            </span>
            {def}
          </span>
        </>
      )}
    </span>
  )
}

// 문자열 안의 알려진 용어를 자동으로 TermChip 으로 감싸기.
function TermText({ text, C }: { text: string; C: typeof LIGHT }) {
  if (!text) return null
  const parts = text.split(TERM_RE)
  return (
    <>
      {parts.map((p, i) =>
        GLOSSARY[p] ? <TermChip key={i} term={p} C={C} /> : <span key={i}>{p}</span>
      )}
    </>
  )
}

export default function StockRadarProbe(props: { width?: number; dark?: boolean }) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))
  const isDark = onCanvas ? !!props.dark : themeDark
  const C = isDark ? DARK : LIGHT

  const [idx, setIdx] = useState(0)
  const [easy, setEasy] = useState(false) // 쉬운 말 모드
  const s = STOCKS[idx]

  /* 테마 추종 */
  useEffect(() => {
    if (onCanvas) return
    const read = () => setThemeDark(readBodyDark())
    read()
    if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
    const obs = new MutationObserver(read)
    obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
    return () => obs.disconnect()
  }, [onCanvas])
  const risks = s.flags.filter((f) => f.kind === "risk")
  const events = s.flags.filter((f) => f.kind === "event")

  const headline =
    risks.length === 0
      ? {
          icon: "✓",
          text: easy ? "지금 특별히 걱정할 일은 안 보여요" : "특이 리스크 없음",
          color: C.green,
        }
      : {
          icon: "⚠️",
          text: easy
            ? `조심해서 볼 일이 ${risks.length}개 있어요`
            : `주의 신호 ${risks.length}개`,
          color: risks.some((r) => r.tone === "high") ? C.red : C.amber,
        }

  return (
    <div
      style={{
        width: "100%",
        background: C.bg,
        fontFamily: "Pretendard, -apple-system, sans-serif",
        padding: 16,
        boxSizing: "border-box",
      }}
    >
      {/* 상단 컨트롤: 종목 선택 + 쉬운 말 토글 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          marginBottom: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {STOCKS.map((st, i) => (
            <button
              key={st.ticker}
              onClick={() => setIdx(i)}
              style={{
                border: "none",
                cursor: "pointer",
                padding: "7px 13px",
                borderRadius: 999,
                fontSize: 13,
                fontWeight: 600,
                background: i === idx ? C.ink : C.card,
                color: i === idx ? (isDark ? C.bg : "#fff") : C.sub,
              }}
            >
              {st.name}
            </button>
          ))}
        </div>

        {/* 쉬운 말 토글 */}
        <button
          onClick={() => setEasy((v) => !v)}
          aria-pressed={easy}
          style={{
            border: "none",
            cursor: "pointer",
            padding: "7px 14px",
            borderRadius: 999,
            fontSize: 13,
            fontWeight: 700,
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            background: easy ? C.blue : C.card,
            color: easy ? "#fff" : C.sub,
            transition: "all 160ms ease",
          }}
        >
          <span style={{ fontSize: 14 }}>{easy ? "💡" : "📖"}</span>
          쉬운 말 {easy ? "켜짐" : "꺼짐"}
        </button>
      </div>

      {/* 카드 */}
      <div
        style={{
          background: C.card,
          borderRadius: 20,
          padding: 22,
          boxShadow: isDark ? "0 1px 3px rgba(0,0,0,0.3)" : "0 1px 3px rgba(0,0,0,0.04)",
        }}
      >
        {/* 종목명 */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 18 }}>
          <span style={{ fontSize: 21, fontWeight: 700, color: C.ink, letterSpacing: "-0.4px" }}>
            {s.name}
          </span>
          <span style={{ fontSize: 14, color: C.faint, fontWeight: 500 }}>{s.ticker}</span>
        </div>

        {/* 한눈 답 */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 22 }}>
          <span style={{ fontSize: 26 }}>{headline.icon}</span>
          <span
            style={{
              fontSize: easy ? 19 : 24,
              fontWeight: 800,
              color: headline.color,
              letterSpacing: "-0.6px",
              lineHeight: 1.25,
            }}
          >
            {headline.text}
          </span>
        </div>

        {/* 리스크 섹션 */}
        {risks.map((f, i) => {
          const c = toneColor(C, f.tone)
          return (
            <div
              key={i}
              style={{
                display: "flex",
                gap: 12,
                padding: "13px 0",
                borderTop: i === 0 ? `1px solid ${C.line}` : "none",
              }}
            >
              <span
                style={{
                  flexShrink: 0,
                  alignSelf: "flex-start",
                  fontSize: 12,
                  fontWeight: 700,
                  color: c.fg,
                  background: c.bg,
                  padding: "4px 9px",
                  borderRadius: 7,
                }}
              >
                <TermText text={f.tag} C={C} />
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: C.ink, marginBottom: 2 }}>
                  <TermText text={f.title} C={C} />
                </div>
                <div
                  style={{
                    fontSize: easy ? 13.5 : 13,
                    color: C.sub,
                    lineHeight: easy ? 1.55 : 1.4,
                  }}
                >
                  <TermText text={easy ? f.plain : f.detail} C={C} />
                </div>
              </div>
              <span
                style={{
                  flexShrink: 0,
                  fontSize: 13,
                  fontWeight: 700,
                  color: f.tone === "high" ? C.red : C.faint,
                }}
              >
                {f.when}
              </span>
            </div>
          )
        })}

        {/* 호재성 사실 (이벤트) — '사라'가 아니라 '이런 일이 있었다' */}
        {events.length > 0 && (
          <div style={{ marginTop: risks.length ? 6 : 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: C.faint, margin: "10px 0 2px" }}>
              관심 이벤트 (사실)
            </div>
            {events.map((f, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  gap: 12,
                  padding: "13px 0",
                  borderTop: `1px solid ${C.line}`,
                }}
              >
                <span
                  style={{
                    flexShrink: 0,
                    alignSelf: "flex-start",
                    fontSize: 12,
                    fontWeight: 700,
                    color: C.blue,
                    background: C.blueSoft,
                    padding: "4px 9px",
                    borderRadius: 7,
                  }}
                >
                  <TermText text={f.tag} C={C} />
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 600, color: C.ink, marginBottom: 2 }}>
                    <TermText text={f.title} C={C} />
                  </div>
                  <div
                    style={{
                      fontSize: easy ? 13.5 : 13,
                      color: C.sub,
                      lineHeight: easy ? 1.55 : 1.4,
                    }}
                  >
                    <TermText text={easy ? f.plain : f.detail} C={C} />
                  </div>
                </div>
                <span style={{ flexShrink: 0, fontSize: 13, fontWeight: 600, color: C.faint }}>
                  {f.when}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* 깨끗한 항목 */}
        {s.clean.length > 0 && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
              marginTop: 16,
              paddingTop: 16,
              borderTop: `1px solid ${C.line}`,
            }}
          >
            {s.clean.map((c, i) => (
              <span
                key={i}
                style={{
                  fontSize: 13,
                  color: C.green,
                  background: C.greenSoft,
                  padding: "5px 11px",
                  borderRadius: 8,
                  fontWeight: 600,
                }}
              >
                ✓ <TermText text={c} C={C} />
              </span>
            ))}
          </div>
        )}

        {/* 정직 푸터 */}
        <div style={{ marginTop: 18, padding: "12px 14px", background: C.bg, borderRadius: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: C.sub, marginBottom: 3 }}>
            ⓘ 이건 '팔아라/사라'가 아닙니다
          </div>
          <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5 }}>
            점수·추천 아님 · 공시 사실과 일정만 · 판단은 직접. 검증된 신호는 별도.
            {easy && " · 밑줄 친 용어는 누르면 뜻이 나와요."}
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
  dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})

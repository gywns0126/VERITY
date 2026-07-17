import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

/**
 * AlphaNest 피드 — 공시-first 연결, 층위 공개(progressive disclosure). 토스 언어, 이모지 0.
 *
 * L0(기본): 답 하나 + 과거패턴 mini-viz(점 타임라인) + "근거 N개 ▾"(깊이 신호).
 * L1(탭): 연결된 사실 전체 + 출처(DART/KRX 원문).  → 표면 심플, 깊이 한 탭 아래.
 *
 * 🚨 점수·등급·추천·verdict 0(RULE7, 유사투자자문 회피). named 비판 0 — 전부 공시/시세 사실.
 *    "이게 처음 아님" 과거패턴 = 사실 병기(추천 아님). 유리박스 정직 라벨.
 *
 * Framer ID pX7cI0P · insertUrl framer.com/m/AlphaNestFeed-aZ2eF0.js · 생성 2026-06-16.
 */

// ── 토스 디자인 토큰 ── (LIGHT / DARK 쌍)
const LIGHT = {
  bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
  line: "#e5e8eb", red: "#f04452", redSoft: "#fff0f1", amber: "#ff9500", amberSoft: "#fff6e9",
  blue: "#3182f6", blueSoft: "#eef4ff", green: "#15c47e", greenSoft: "#eafaf3",
  violet: "#6c5ce7", violetSoft: "#f0edff",
}
const DARK = {
  bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
  line: "#2b2f37", red: "#ff6b76", redSoft: "#3a1f22", amber: "#ffb340", amberSoft: "#3a2e18",
  blue: "#5a9cff", blueSoft: "#1b2740", green: "#3ddc97", greenSoft: "#16322a",
  violet: "#a98bff", violetSoft: "#2a2440",
}

function readBodyDark(): boolean {
  if (typeof document === "undefined" || !document.body) return false
  return document.body.dataset.framerTheme === "dark"
}

type Tone = "risk" | "flow" | "cal" | "good"
type Conn = { tone: Tone; tag: string; fact: string }
type Hist = { label: string; ret: number | null; current: boolean }
type Item = {
  name: string; ticker: string; ago: string
  disclosure: string; dtone: "risk" | "good"
  glance: string
  conns: Conn[]
  sources: string[]
  patternLabel: string
  history: Hist[]
}

function toneMap(C: typeof LIGHT): Record<Tone, { fg: string; bg: string }> {
  return {
    risk: { fg: C.red, bg: C.redSoft }, flow: { fg: C.blue, bg: C.blueSoft },
    cal: { fg: C.amber, bg: C.amberSoft }, good: { fg: C.green, bg: C.greenSoft },
  }
}

const ITEMS: Item[] = [
  {
    name: "에코프로비엠", ticker: "247540", ago: "8분 전",
    disclosure: "유상증자 결정 · 3,200억", dtone: "risk",
    glance: "오버행 6.2% · 외인 3일 순매도 · 증자 3번째",
    conns: [
      { tone: "risk", tag: "오버행", fact: "발행주식의 6.2% 희석" },
      { tone: "flow", tag: "수급", fact: "외국인 3일 연속 순매도 −142만주" },
      { tone: "cal", tag: "일정", fact: "전환사채 전환가능 D-9" },
    ],
    sources: ["DART 2026-06-16 유상증자결정", "KRX 투자자별 매매동향"],
    patternLabel: "2015년 이후 유상증자 3번째",
    history: [
      { label: "'18", ret: -18, current: false },
      { label: "'21", ret: -24, current: false },
      { label: "현재", ret: null, current: true },
    ],
  },
  {
    name: "엠케이전자", ticker: "033160", ago: "23분 전",
    disclosure: "단일판매·공급계약 · 1,840억(매출 21%)", dtone: "good",
    glance: "기관 순매수 · 실적 D-5 · 공급계약 6번째",
    conns: [
      { tone: "flow", tag: "수급", fact: "기관 2일 순매수 +38만주" },
      { tone: "cal", tag: "일정", fact: "실적발표 D-5" },
    ],
    sources: ["DART 2026-06-16 공급계약체결", "KRX 투자자별 매매동향"],
    patternLabel: "공급계약 공시 6번째",
    history: [
      { label: "'22", ret: 8, current: false },
      { label: "'23", ret: 5, current: false },
      { label: "'24", ret: 6, current: false },
      { label: "현재", ret: null, current: true },
    ],
  },
]

function MiniHistory(props: { history: Hist[]; C: typeof LIGHT }) {
  const C = props.C
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 16, padding: "2px 2px 0" }}>
      {props.history.map((h, k) => {
        const col = h.current ? C.violet : h.ret !== null && h.ret < 0 ? C.red : C.green
        const txt = h.current ? "?" : (h.ret !== null && h.ret > 0 ? "+" + h.ret : "" + h.ret) + "%"
        return (
          <div key={k} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: col }}>{txt}</div>
            <div
              style={{
                width: 11, height: 11, borderRadius: 6,
                background: h.current ? C.card : col,
                border: h.current ? "2px solid " + C.violet : "none",
                boxSizing: "border-box",
              }}
            />
            <div style={{ fontSize: 10, fontWeight: 600, color: C.faint }}>{h.label}</div>
          </div>
        )
      })}
    </div>
  )
}

export default function AlphaNestFeed(props: { width?: number; dark?: boolean; reportPath?: string }) {
  const width = props.width || 380
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))
  const isDark = onCanvas ? !!props.dark : themeDark
  const C = isDark ? DARK : LIGHT
  const TONE = toneMap(C)

  const [open, setOpen] = useState(-1)

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

  return (
    <div
      style={{
        width: width, fontFamily: "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif",
        background: C.bg, borderRadius: 24, padding: 16, boxSizing: "border-box", color: C.ink,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "4px 4px 12px" }}>
        <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: -0.4 }}>내 종목 속보</div>
        <div style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>공시 + 연결</div>
      </div>

      {ITEMS.map((it, i) => {
        const dt = it.dtone === "risk" ? TONE.risk : TONE.good
        const isOpen = open === i
        return (
          <div
            key={i}
            style={{ background: C.card, borderRadius: 20, padding: 16, marginBottom: 12, boxShadow: isDark ? "0 1px 3px rgba(0,0,0,0.3)" : "0 1px 3px rgba(0,0,0,0.04)" }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: -0.3 }}>{it.name}</span>
                <span style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>{it.ticker}</span>
                {it.ticker && !onCanvas && (
                  <a href={(props.reportPath || "/stock") + "?q=" + encodeURIComponent(it.ticker)} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} style={{ fontSize: 11, fontWeight: 700, color: C.blue, textDecoration: "none" }}>분석 ↗</a>
                )}
              </div>
              <span style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>{it.ago}</span>
            </div>

            {/* 공시 = 훅 */}
            <div style={{ background: dt.bg, color: dt.fg, borderRadius: 12, padding: "10px 12px", fontSize: 14, fontWeight: 700, letterSpacing: -0.2 }}>
              {it.disclosure}
            </div>

            {/* L0 한눈 요약 */}
            <div style={{ fontSize: 13, color: C.sub, fontWeight: 600, letterSpacing: -0.2, padding: "11px 2px 4px" }}>
              {it.glance}
            </div>

            {/* 과거패턴 mini-viz — substance 한눈에 */}
            <div style={{ background: C.violetSoft, borderRadius: 12, padding: "11px 12px", marginTop: 6 }}>
              <div style={{ fontSize: 11, fontWeight: 800, color: C.violet, marginBottom: 8 }}>{it.patternLabel} — 이게 처음이 아님</div>
              <MiniHistory history={it.history} C={C} />
            </div>

            {/* 깊이 신호 = "근거 N개 ▾" (rigor 전달, 안 어지럽게) */}
            <div
              onClick={() => setOpen(isOpen ? -1 : i)}
              style={{
                cursor: "pointer", marginTop: 12, fontSize: 12.5, fontWeight: 700, color: C.blue,
                display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
                padding: "8px", borderRadius: 10, background: isOpen ? C.blueSoft : "transparent",
              }}
            >
              근거 {it.conns.length}개 · 어떻게 나왔나 {isOpen ? "▴" : "▾"}
            </div>

            {/* L1 펼침 = 연결된 사실 전체 + 출처 */}
            {isOpen ? (
              <div style={{ marginTop: 4, paddingTop: 12, borderTop: "1px solid " + C.line }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 12 }}>
                  {it.conns.map((c, j) => {
                    const t = TONE[c.tone]
                    return (
                      <div key={j} style={{ display: "flex", alignItems: "center", gap: 9 }}>
                        <span style={{ flexShrink: 0, background: t.bg, color: t.fg, fontSize: 11, fontWeight: 800, padding: "3px 8px", borderRadius: 7, minWidth: 42, textAlign: "center" }}>
                          {c.tag}
                        </span>
                        <span style={{ fontSize: 13.5, color: C.sub, fontWeight: 600, letterSpacing: -0.2 }}>{c.fact}</span>
                      </div>
                    )
                  })}
                </div>
                <div style={{ fontSize: 11, fontWeight: 700, color: C.faint, marginBottom: 6 }}>출처</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {it.sources.map((s, j) => (
                    <div key={j} style={{ fontSize: 12, color: C.sub, fontWeight: 600 }}>· {s}</div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )
      })}

      <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, padding: "6px 8px 2px", lineHeight: 1.5 }}>
        사실·연결만 — 점수·추천 아님 · VERITY 검증 진행 중
      </div>
    </div>
  )
}

addPropertyControls(AlphaNestFeed, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380, min: 320, max: 720 },
  dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
  reportPath: { type: ControlType.String, title: "리포트 경로", defaultValue: "/stock" },
})

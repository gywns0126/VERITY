import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState } from "react"

/**
 * 부동산 유리박스 — 공개 probe (토스 디자인 언어)
 *
 * "이 회사 부동산 얼마나 들고 있나?" 를 재무제표 공시 장부가로 한 화면에.
 * KR = OpenDART 재무상태표(투자부동산·사용권자산), US = SEC XBRL companyfacts.
 *
 * 🚨 점수·등급·추천 없음. "사라/팔아라" 없음. 공시된 장부가 사실만.
 *    (RULE 7 미검증 산식 비노출 + §3 공개 경계 = L0 공시 사실.)
 *
 * 데이터 = 실호출 검증 장부가 (DART fnlttSinglAcntAll / SEC companyfacts).
 *
 * 다크모드 = body[data-framer-theme] 자가감지 (PublicThemeToggle 소스 추종).
 */

// ── 토스 디자인 토큰 (OwnershipProbe 와 동일 언어) ── (LIGHT / DARK 쌍)
const LIGHT = {
  bg: "#f2f4f6",
  card: "#ffffff",
  ink: "#191f28",
  sub: "#4e5968",
  faint: "#8b95a1",
  line: "#e5e8eb",
  blue: "#3182f6",
  blueSoft: "#eef4ff",
  green: "#15c47e",
  greenSoft: "#eafaf3",
  teal: "#12b8a6",
  tealSoft: "#e7faf7",
}
const DARK = {
  bg: "#16181d",
  card: "#1e2128",
  ink: "#f0f2f5",
  sub: "#b0b8c1",
  faint: "#6b7684",
  line: "#2b2f37",
  blue: "#5a9cff",
  blueSoft: "#1b2740",
  green: "#3ddc97",
  greenSoft: "#16322a",
  teal: "#2fd6c2",
  tealSoft: "#143430",
}

function readBodyDark(): boolean {
  if (typeof document === "undefined" || !document.body) return false
  return document.body.dataset.framerTheme === "dark"
}

type Asset = { label: string; value: number; hint?: string }
type Stock = {
  name: string; ticker: string; market: "KR" | "US"
  unit: "조" | "B"; assets: Asset[]; source: string
}

// 실호출 검증 장부가 (2024 회계연도). KR=조원, US=$B.
const STOCKS: Stock[] = [
  {
    name: "롯데쇼핑", ticker: "023530", market: "KR", unit: "조",
    assets: [
      { label: "투자부동산", value: 1.86, hint: "임대·시세차익 목적 보유" },
      { label: "사용권자산(리스)", value: 3.11, hint: "장기 임차 매장 등" },
    ],
    source: "OpenDART 연결재무상태표",
  },
  {
    name: "신세계", ticker: "004170", market: "KR", unit: "조",
    assets: [
      { label: "투자부동산", value: 0.92 },
      { label: "사용권자산(리스)", value: 1.13 },
    ],
    source: "OpenDART 연결재무상태표",
  },
  {
    name: "Walmart", ticker: "WMT", market: "US", unit: "B",
    assets: [
      { label: "유형자산 순액(PP&E)", value: 136.1, hint: "토지·건물·설비" },
      { label: "리스 사용권", value: 14.8 },
    ],
    source: "SEC XBRL companyfacts",
  },
  {
    name: "Realty Income", ticker: "O", market: "US", unit: "B",
    assets: [
      { label: "투자부동산(REIT)", value: 53.4, hint: "임대 부동산 포트폴리오" },
      { label: "리스 사용권", value: 0.6 },
    ],
    source: "SEC XBRL companyfacts",
  },
]

const fmt = (v: number, unit: "조" | "B") =>
  unit === "조" ? `${v.toFixed(2)}조` : `$${v.toFixed(1)}B`

export default function RealtyProbe(props: { width?: number; dark?: boolean }) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
  const isDark = onCanvas ? !!props.dark : themeDark
  const C = isDark ? DARK : LIGHT

  const [idx, setIdx] = useState(0)
  const s = STOCKS[idx]
  const total = useMemo(() => s.assets.reduce((a, x) => a + x.value, 0), [s])
  const maxv = useMemo(() => Math.max(...s.assets.map((x) => x.value), 0.0001), [s])

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
    <div style={{ width: "100%", background: C.bg, fontFamily: "Pretendard, -apple-system, sans-serif", padding: 16, boxSizing: "border-box" }}>
      {/* 종목 선택 */}
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {STOCKS.map((st, i) => (
          <button
            key={st.ticker}
            onClick={() => setIdx(i)}
            style={{
              border: "none", cursor: "pointer", padding: "7px 13px", borderRadius: 999, fontSize: 13, fontWeight: 600,
              background: i === idx ? C.ink : C.card, color: i === idx ? (isDark ? C.bg : "#fff") : C.sub,
            }}
          >
            {st.name}
          </button>
        ))}
      </div>

      <div style={{ background: C.card, borderRadius: 20, padding: 22, boxShadow: isDark ? "0 1px 3px rgba(0,0,0,0.3)" : "0 1px 3px rgba(0,0,0,0.04)" }}>
        {/* 종목명 + 시장 */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 18 }}>
          <span style={{ fontSize: 21, fontWeight: 700, color: C.ink, letterSpacing: "-0.4px" }}>{s.name}</span>
          <span style={{ fontSize: 14, color: C.faint, fontWeight: 500 }}>{s.ticker}</span>
          <span style={{ marginLeft: "auto", fontSize: 12, fontWeight: 600, color: C.teal, background: C.tealSoft, padding: "4px 9px", borderRadius: 7 }}>
            {s.market === "KR" ? "국내" : "미국"}
          </span>
        </div>

        {/* 한눈 답 — 부동산 장부가 합 */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span style={{ fontSize: 32, fontWeight: 800, color: C.teal, letterSpacing: "-1px" }}>{fmt(total, s.unit)}</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: C.ink }}>의 부동산 자산</span>
          </div>
          <div style={{ fontSize: 12.5, color: C.faint, marginTop: 2 }}>
            재무제표 공시 장부가 기준 (시가 아님)
          </div>
        </div>

        {/* 자산 항목 + 막대 */}
        {s.assets.map((a, i) => (
          <div key={i} style={{ padding: "12px 0", borderTop: i === 0 ? `1px solid ${C.line}` : "none" }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 7 }}>
              <span style={{ fontSize: 15, fontWeight: 600, color: C.ink }}>{a.label}</span>
              <span style={{ fontSize: 15, fontWeight: 700, color: C.ink, fontVariantNumeric: "tabular-nums" }}>{fmt(a.value, s.unit)}</span>
            </div>
            <div style={{ width: "100%", height: 8, background: C.bg, borderRadius: 999, overflow: "hidden" }}>
              <div style={{ width: `${(a.value / maxv) * 100}%`, height: "100%", background: C.teal, borderRadius: 999 }} />
            </div>
            {a.hint && <div style={{ fontSize: 12, color: C.faint, marginTop: 5 }}>{a.hint}</div>}
          </div>
        ))}

        {/* 정직 푸터 */}
        <div style={{ marginTop: 18, padding: "12px 14px", background: C.bg, borderRadius: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: C.sub, marginBottom: 3 }}>ⓘ {s.source}</div>
          <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5 }}>
            장부가(취득원가 기준) · 시가 아님
          </div>
        </div>
      </div>

      <div style={{ textAlign: "center", fontSize: 11, color: C.faint, marginTop: 12 }}>
        공시 실데이터 · 디자인 probe
      </div>
    </div>
  )
}

addPropertyControls(RealtyProbe, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380, min: 320, max: 720 },
  dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})

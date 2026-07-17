import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState } from "react"

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
 *
 * 다크모드 = body[data-framer-theme] 자가감지 (PublicThemeToggle 소스 추종).
 * 주주명 링크 = 법인→네이버 회사 검색 / 개인→네이버 인물 검색 (제네릭 구분명은 링크 없음).
 */

// ── 토스 디자인 토큰 ── (LIGHT / DARK 쌍)
const LIGHT = {
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
const DARK = {
  bg: "#16181d",
  card: "#1e2128",
  ink: "#f0f2f5",
  sub: "#b0b8c1",
  faint: "#6b7684",
  line: "#2b2f37",
  red: "#ff6b76",
  amber: "#ffb340",
  blue: "#5a9cff",
  blueSoft: "#1b2740",
  green: "#3ddc97",
  greenSoft: "#16322a",
  purple: "#a98bff",
  purpleSoft: "#2a2440",
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

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
    } catch (e) {}
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

// 제네릭 구분명(특정 주체 아님) = 링크 없음
function isGenericHolder(name: string): boolean {
  return /기타|소액주주|자기주식|우리사주|^친족$|^동일인$|^임원$|기관|외국인|개인투자자/.test(name)
}
// 법인 여부 — 소속회사 type 이거나 회사형 접미사
function isCorp(name: string, type: Holder["type"]): boolean {
  if (type === "소속회사") return true
  return /(주식회사|\(주\)|㈜|회사|Ltd|LTD|Inc|INC|Limited|Corp|Company|생명|화재|증권|물산|홀딩스|투자|캐피탈|은행|보험|자산운용|에스케이|텔레콤|전자|중공업)/.test(name)
}
// 주주명 → 네이버 검색 URL (법인=회사 / 개인=인물). 제네릭이면 null.
function entityUrl(name: string, type: Holder["type"]): string | null {
  if (!name || isGenericHolder(name)) return null
  const q = isCorp(name, type) ? name : name + " 인물"
  return "https://search.naver.com/search.naver?query=" + encodeURIComponent(q)
}

export default function OwnershipProbe(props: { width?: number; dark?: boolean }) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))
  const isDark = onCanvas ? !!props.dark : themeDark
  const C = isDark ? DARK : LIGHT

  const [idx, setIdx] = useState(0)
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

  const typeStyle = (t: Holder["type"]) =>
    t === "동일인" ? { fg: C.purple, bg: C.purpleSoft }
    : t === "친족" ? { fg: C.purple, bg: C.purpleSoft }
    : t === "소속회사" ? { fg: C.blue, bg: C.blueSoft }
    : t === "자기주식" ? { fg: C.faint, bg: C.bg }
    : { fg: C.faint, bg: C.bg }

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
              background: i === idx ? C.ink : C.card, color: i === idx ? (isDark ? C.bg : "#fff") : C.sub,
            }}
          >
            {st.name}
          </button>
        ))}
      </div>

      <div style={{ background: C.card, borderRadius: 20, padding: 22, boxShadow: isDark ? "0 1px 3px rgba(0,0,0,0.3)" : "0 1px 3px rgba(0,0,0,0.04)" }}>
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
          const url = entityUrl(h.name, h.type)
          const nameStyle: any = { flex: 1, minWidth: 0, fontSize: 15, fontWeight: 600, color: url ? C.blue : C.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textDecoration: "none" }
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 0", borderTop: i === 0 ? `1px solid ${C.line}` : "none" }}>
              <span style={{ flexShrink: 0, fontSize: 11.5, fontWeight: 700, color: st.fg, background: st.bg, padding: "4px 9px", borderRadius: 7, minWidth: 52, textAlign: "center" }}>
                {h.type}
              </span>
              {url ? (
                <a href={url} target="_blank" rel="noopener noreferrer" title={`${h.name} 검색`} style={nameStyle}>
                  {h.name} ↗
                </a>
              ) : (
                <span style={nameStyle}>{h.name}</span>
              )}
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
  dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})

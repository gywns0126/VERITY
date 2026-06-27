import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"

/**
 * 소형주 코너 — 골든구스 공개면. 방치 우량 + 패턴 필터, 사실만(점수·등급·추천 0).
 *
 * 3단 해석: 쉬운이름(name) · 배지(badge) · 왜중요(why) · 투명기준(criteria_text).
 * L0: 필터 카드(이름/배지/한줄 이유/기준/N개). L1(탭): 종목 리스트 + 재무 사실(DART/KRX).
 *
 * 🚨 RULE 7 — 점수·등급·순위·verdict 0. 전부 공시/재무 사실. 검증 점수 held(2027). LLM 0(RULE 6).
 *    data: VERITY-data/smallcap_corner_filters.json (smallcap_corner_filters_builder 산출).
 *
 * 생성 2026-06-20 (Phase 4). cache-fallback(sessionStorage).
 */

const URL =
  "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/smallcap_corner_filters.json"

// ── 토스 디자인 토큰 ── (LIGHT / DARK 쌍). 다크모드 = body[data-framer-theme] 자가감지.
const LIGHT = {
  bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
  line: "#e5e8eb", red: "#f04452", redSoft: "#fff0f1", amber: "#ff9500", amberSoft: "#fff6e9",
  blue: "#3182f6", blueSoft: "#eef4ff", green: "#15c47e", greenSoft: "#eafaf3",
  violet: "#6c5ce7", violetSoft: "#f0edff",
}
const DARK = {
  bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
  line: "#2b2f37", red: "#ff6b76", redSoft: "#3a1f22", amber: "#ffb340", amberSoft: "#3a2c14",
  blue: "#5a9cff", blueSoft: "#1b2740", green: "#3ddc97", greenSoft: "#16322a",
  violet: "#a98bff", violetSoft: "#2a2440",
}

// 필터 key → 배지 색 (tone). 사실 분류만 — 좋고나쁨 점수 아님. (C 토큰 참조, 컴포넌트 내 isDark 분기)
function makeTone(C: typeof LIGHT): Record<string, { fg: string; bg: string }> {
  return {
    neglected_quality: { fg: C.green, bg: C.greenSoft },
    smallcap_dilution: { fg: C.amber, bg: C.amberSoft },
    smallcap_distress: { fg: C.red, bg: C.redSoft },
    clean_fin_risky_disc: { fg: C.violet, bg: C.violetSoft },
  }
}

function readBodyDark(): boolean {
  if (typeof document === "undefined" || !document.body) return false
  return document.body.dataset.framerTheme === "dark"
}

type Facts = { [k: string]: number }
type Ticker = { ticker: string; name: string; market: string; facts: Facts }
type Filter = {
  key: string; name: string; badge: string; why: string
  criteria_text: string; count: number; tickers: Ticker[]
}

function eok(won: number): string {
  // 원 → 억 표기 (정수 반올림)
  const v = Math.round(won / 1e8)
  return v.toLocaleString() + "억"
}

function FactRow(props: { t: Ticker; C: typeof LIGHT; reportPath?: string }) {
  const C = props.C
  const f = props.t.facts || {}
  const url = props.t.ticker ? (props.reportPath || "/stock") + "?q=" + encodeURIComponent(props.t.ticker) : ""
  const bits: string[] = []
  if (f["시총_억"] != null) bits.push("시총 " + Math.round(f["시총_억"]).toLocaleString() + "억")
  if (f["부채비율"] != null) bits.push("부채 " + f["부채비율"].toFixed(0) + "%")
  if (f["roa"] != null) bits.push("ROA " + f["roa"].toFixed(1) + "%")
  if (f["순이익"] != null) bits.push("순익 " + eok(f["순이익"]))
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 2px", borderTop: "1px solid " + C.line }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 7, flexShrink: 0 }}>
        {url ? (
          <a href={url} target="_blank" rel="noopener noreferrer" title={props.t.name + " 분석"} style={{ fontSize: 14, fontWeight: 700, color: C.violet, letterSpacing: -0.2, textDecoration: "none" }}>{props.t.name} ↗</a>
        ) : (
          <span style={{ fontSize: 14, fontWeight: 700, color: C.ink, letterSpacing: -0.2 }}>{props.t.name}</span>
        )}
        <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{props.t.ticker}</span>
      </div>
      <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, textAlign: "right", letterSpacing: -0.2 }}>
        {bits.join(" · ")}
      </div>
    </div>
  )
}

export default function SmallcapCornerCard(props: { width?: number; dark?: boolean; reportPath?: string; screenerPath?: string }) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
  const isDark = onCanvas ? !!props.dark : themeDark
  const C = isDark ? DARK : LIGHT
  const TONE = makeTone(C)

  const width = props.width || 380
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState<string>("")
  const [open, setOpen] = useState<number>(-1)

  /* 테마 추종 (fetch useEffect 와 별개) */
  useEffect(() => {
    if (onCanvas) return
    const read = () => setThemeDark(readBodyDark())
    read()
    if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
    const obs = new MutationObserver(read)
    obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
    return () => obs.disconnect()
  }, [onCanvas])

  useEffect(() => {
    let alive = true
    const KEY = "smallcap_corner_filters_cache"
    fetch(URL + "?t=" + Date.now())
      .then(function (r) {
        if (!r.ok) throw new Error("http " + r.status)
        return r.json()
      })
      .then(function (j) {
        if (!alive) return
        setData(j)
        try { sessionStorage.setItem(KEY, JSON.stringify(j)) } catch (e) {}
      })
      .catch(function (e) {
        if (!alive) return
        try {
          const c = sessionStorage.getItem(KEY)
          if (c) { setData(JSON.parse(c)); return }
        } catch (er) {}
        setErr(String(e))
      })
    return function () { alive = false }
  }, [])

  const shell = {
    width: width, fontFamily: "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif",
    background: "transparent", borderRadius: 24, padding: 16, boxSizing: "border-box" as const, color: C.ink,
  }

  if (err && !data) {
    return (
      <div style={shell}>
        <div style={{ fontSize: 13, color: C.faint, fontWeight: 600, padding: 20, textAlign: "center" }}>
          데이터 로드 실패 — {err}
        </div>
      </div>
    )
  }
  if (!data) {
    const base = isDark ? "#222a33" : "#e9edf1"
    const hi = isDark ? "#2d3742" : "#f3f5f7"
    const shimmer = {
      background: base,
      backgroundImage: "linear-gradient(90deg, " + base + " 25%, " + hi + " 37%, " + base + " 63%)",
      backgroundSize: "800px 100%",
      animation: "vsrShimmer 1.4s ease-in-out infinite",
    }
    const bar = function (w: number | string, h: number, r: number) {
      return { width: w, height: h, borderRadius: r, ...shimmer }
    }
    const rows = [0, 1, 2, 3, 4, 5, 6, 7]
    return (
      <div style={shell}>
        <style>{"@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}"}</style>
        {/* 헤더 자리 */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 4px 12px" }}>
          <div style={bar(120, 20, 6)} />
          <div style={bar(56, 14, 6)} />
        </div>
        {/* 필터 카드 자리 */}
        <div style={{ background: C.card, borderRadius: 20, padding: 16, marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={bar(60, 18, 8)} />
              <div style={bar(90, 16, 6)} />
            </div>
            <div style={bar(28, 16, 6)} />
          </div>
          <div style={{ ...bar("70%", 13, 6), marginBottom: 12 }} />
          {/* 종목 행 자리 (FactRow 6~8개) */}
          {rows.map(function (k) {
            return (
              <div
                key={k}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 2px", borderTop: "1px solid " + C.line }}
              >
                <div style={bar(96, 14, 6)} />
                <div style={bar(120, 11, 6)} />
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  const meta = data._meta || {}
  const filters: Filter[] = data.filters || []

  return (
    <div style={shell}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "4px 4px 4px" }}>
        <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: -0.4 }}>소형주 코너</div>
        <div style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>
          {meta.universe_n ? meta.universe_n.toLocaleString() + "종목" : "사실 필터"}
        </div>
      </div>
      <div style={{ fontSize: 12, color: C.sub, fontWeight: 600, padding: "0 4px 12px", letterSpacing: -0.2, lineHeight: 1.5 }}>
        시총 300~3000억 · 애널리스트·기관이 안 보는 코너. 사실·패턴만, 추천 아님.
      </div>

      {filters.map(function (flt, i) {
        const t = TONE[flt.key] || { fg: C.violet, bg: C.violetSoft }
        const isOpen = open === i
        const tickers = flt.tickers || []
        const limit = 8
        return (
          <div
            key={i}
            style={{ background: C.card, borderRadius: 20, padding: 16, marginBottom: 12, boxShadow: isDark ? "0 1px 3px rgba(0,0,0,0.3)" : "0 1px 3px rgba(0,0,0,0.04)" }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 9 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ background: t.bg, color: t.fg, fontSize: 11, fontWeight: 800, padding: "4px 9px", borderRadius: 8 }}>
                  {flt.badge}
                </span>
                <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: -0.3 }}>{flt.name}</span>
              </div>
              <span style={{ fontSize: 15, fontWeight: 800, color: t.fg }}>{flt.count}</span>
            </div>

            <div style={{ fontSize: 13, color: C.sub, fontWeight: 600, letterSpacing: -0.2, lineHeight: 1.5, padding: "0 1px 9px" }}>
              {flt.why}
            </div>

            <div style={{ background: C.bg, borderRadius: 12, padding: "9px 11px", fontSize: 11.5, color: C.faint, fontWeight: 700, letterSpacing: -0.2, lineHeight: 1.5 }}>
              기준 · {flt.criteria_text}
            </div>

            {tickers.length > 0 ? (
              <div
                onClick={function () { setOpen(isOpen ? -1 : i) }}
                style={{
                  cursor: "pointer", marginTop: 11, fontSize: 12.5, fontWeight: 700, color: t.fg,
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
                  padding: "8px", borderRadius: 10, background: isOpen ? t.bg : "transparent",
                }}
              >
                종목 {tickers.length}개 보기 {isOpen ? "▴" : "▾"}
              </div>
            ) : null}

            {isOpen ? (
              <div style={{ marginTop: 4 }}>
                {tickers.slice(0, limit).map(function (tk, j) {
                  return <FactRow key={j} t={tk} C={C} reportPath={props.reportPath} />
                })}
                {tickers.length > limit ? (
                  <a
                    href={(props.screenerPath || "/smallcap") + "?filter=" + flt.key}
                    target="_blank" rel="noopener noreferrer"
                    style={{ display: "block", cursor: "pointer", textAlign: "center", textDecoration: "none", fontSize: 12, fontWeight: 700, color: t.fg, padding: "10px 0 2px" }}
                  >
                    전체 {tickers.length}종목 스크리너 (검색·정렬) →
                  </a>
                ) : null}
              </div>
            ) : null}
          </div>
        )
      })}

      <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, padding: "6px 8px 2px", lineHeight: 1.5 }}>
        {meta.disclaimer || "사실·패턴만 — 점수·추천 아님 · VERITY 검증 진행 중"}
      </div>
    </div>
  )
}

addPropertyControls(SmallcapCornerCard, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380, min: 320, max: 720 },
  dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
  reportPath: { type: ControlType.String, title: "리포트 경로", defaultValue: "/stock" },
  screenerPath: { type: ControlType.String, title: "스크리너 경로", defaultValue: "/smallcap" },
})

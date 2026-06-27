import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect, useMemo } from "react"

/**
 * KR 소형주 스크리너 — 코너의 '전체 탐색' 짝 (US USSmallcapScreener 의 KR 대응).
 * 코너 카드(발견 미리보기 8) → 전체 N개 진입. 수백 종목을 더보기 노동 없이 탐색.
 *
 * 필터 탭(방치우량/희석/부실/교차) × 정렬(시총·ROA·순이익·부채비율, 사실 정렬) ×
 * 검색(티커/종목명) × 페이지(20). 카드 인라인 덤프 제거의 짝.
 *
 * 🚨 RULE 7 — 정렬은 사실 메트릭 정렬일 뿐(점수·등급·순위·추천 0). 검증 점수 held(2027).
 *    RULE 6 — LLM narrative 0. data: smallcap_corner_filters.json.
 * 생성 2026-06-26 (Phase 4 parity). 다크모드 자가감지. cache-fallback(sessionStorage).
 * 통일: 코너 카드와 같은 URL·토큰·키 inline 일치(공유모듈 Framer 불가 학습 반영).
 */

const URL =
  "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/smallcap_corner_filters.json"

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

function readBodyDark(): boolean {
  if (typeof document === "undefined" || !document.body) return false
  return document.body.dataset.framerTheme === "dark"
}

function eok(won: number): string {
  // 원 → 억 표기 (정수 반올림). 코너 카드 eok 와 동일.
  const v = Math.round(won / 1e8)
  return v.toLocaleString() + "억"
}

// 정렬 옵션 (사실 메트릭 — 점수/순위 아님). asc=작은순(시총=방치강도/부채=낮은순), desc=큰순.
const SORTS = [
  { key: "시총_억", label: "시총↑", dir: "asc" as const },
  { key: "roa", label: "ROA↓", dir: "desc" as const },
  { key: "순이익", label: "순이익↓", dir: "desc" as const },
  { key: "부채비율", label: "부채↑", dir: "asc" as const },
]
// 공시 신호(건수) — 필터별로만 존재. 표기 라벨 매핑.
const SIG_LABELS: [string, string][] = [
  ["유상증자", "유상증자"],
  ["CB_BW", "CB/BW"],
  ["회생·상폐·감자", "회생·상폐·감자"],
  ["구조공시", "구조공시"],
]
const PAGE = 20

type Facts = { [k: string]: any }
type Ticker = { ticker: string; name: string; market: string; facts: Facts }
type Filter = { key: string; name: string; badge: string; count: number; tickers: Ticker[] }

export default function SmallcapScreener(props: { width?: number; dark?: boolean; reportPath?: string; initialFilter?: string }) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
  const isDark = onCanvas ? !!props.dark : themeDark
  const C = isDark ? DARK : LIGHT
  const width = props.width || 380

  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState<string>("")
  const [fIdx, setFIdx] = useState<number>(0)
  const [sIdx, setSIdx] = useState<number>(0)
  const [q, setQ] = useState<string>("")
  const [page, setPage] = useState<number>(0)

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
    const KEY = "smallcap_screener_cache"
    fetch(URL + "?t=" + Date.now())
      .then((r) => { if (!r.ok) throw new Error("http " + r.status); return r.json() })
      .then((j) => { if (!alive) return; setData(j); try { sessionStorage.setItem(KEY, JSON.stringify(j)) } catch (e) {} })
      .catch((e) => {
        if (!alive) return
        try { const c = sessionStorage.getItem(KEY); if (c) { setData(JSON.parse(c)); return } } catch (er) {}
        setErr(String(e))
      })
    return () => { alive = false }
  }, [])

  // initialFilter(URL ?filter)로 진입 필터 선택
  useEffect(() => {
    if (!data) return
    const filters: Filter[] = data.filters || []
    let want = props.initialFilter || ""
    if (typeof window !== "undefined" && !want) {
      want = (new URLSearchParams(window.location.search).get("filter") || "").trim()
    }
    if (want) {
      const i = filters.findIndex((f) => f.key === want)
      if (i >= 0) setFIdx(i)
    }
  }, [data, props.initialFilter])

  const filters: Filter[] = (data && data.filters) || []
  const cur = filters[fIdx] || null

  const rows = useMemo(() => {
    if (!cur) return []
    const sort = SORTS[sIdx]
    const qq = q.trim().toLowerCase()
    let arr = cur.tickers || []
    if (qq) {
      arr = arr.filter((t) =>
        String(t.ticker).toLowerCase().includes(qq) ||
        String(t.name || "").toLowerCase().includes(qq)
      )
    }
    const val = (t: Ticker) => {
      const v = (t.facts || {})[sort.key]
      return typeof v === "number" ? v : (sort.dir === "asc" ? Infinity : -Infinity)
    }
    arr = [...arr].sort((a, b) => sort.dir === "asc" ? val(a) - val(b) : val(b) - val(a))
    return arr
  }, [cur, sIdx, q])

  useEffect(() => { setPage(0) }, [fIdx, sIdx, q])

  const shell = {
    width, fontFamily: "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif",
    background: "transparent", borderRadius: 24, padding: 16, boxSizing: "border-box" as const, color: C.ink,
  }

  if (err && !data) return <div style={shell}><div style={{ fontSize: 13, color: C.faint, fontWeight: 600, padding: 20, textAlign: "center" }}>로드 실패 — {err}</div></div>
  if (!data) return <div style={shell}><div style={{ fontSize: 13, color: C.faint, fontWeight: 600, padding: 30, textAlign: "center" }}>불러오는 중…</div></div>

  const shown = rows.slice(0, (page + 1) * PAGE)
  const reportPath = props.reportPath || "/stock"

  return (
    <div style={shell}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "2px 4px 10px" }}>
        <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: -0.4 }}>소형주 스크리너</div>
        <div style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>{rows.length.toLocaleString()}종목</div>
      </div>

      {/* 필터 탭 */}
      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 10 }}>
        {filters.map((f, i) => (
          <div key={i} onClick={() => setFIdx(i)} style={{
            cursor: "pointer", flexShrink: 0, fontSize: 12, fontWeight: 700, padding: "7px 12px", borderRadius: 10,
            background: i === fIdx ? C.ink : C.card, color: i === fIdx ? C.bg : C.sub, letterSpacing: -0.2,
          }}>{f.badge} {f.count}</div>
        ))}
      </div>

      {/* 검색 + 정렬 */}
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="티커·종목명 검색"
        style={{ width: "100%", boxSizing: "border-box", fontSize: 13, fontWeight: 600, padding: "10px 12px", borderRadius: 12, border: "none", background: C.card, color: C.ink, marginBottom: 8, outline: "none" }} />
      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 10 }}>
        {SORTS.map((s, i) => (
          <div key={i} onClick={() => setSIdx(i)} style={{
            cursor: "pointer", flexShrink: 0, fontSize: 11.5, fontWeight: 700, padding: "6px 11px", borderRadius: 9,
            background: i === sIdx ? C.violetSoft : "transparent", color: i === sIdx ? C.violet : C.faint, letterSpacing: -0.2,
          }}>{s.label}</div>
        ))}
      </div>

      {/* 종목 리스트 */}
      <div style={{ background: C.card, borderRadius: 16, padding: "4px 14px 12px" }}>
        {shown.length === 0 ? (
          <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600, padding: "20px 0", textAlign: "center" }}>해당 종목 없음</div>
        ) : shown.map((t, j) => {
          const f = t.facts || {}
          const url = (reportPath) + "?q=" + encodeURIComponent(t.ticker)
          const m: string[] = []
          if (f["시총_억"] != null) m.push("시총 " + Math.round(f["시총_억"]).toLocaleString() + "억")
          if (f["부채비율"] != null) m.push("부채 " + f["부채비율"].toFixed(0) + "%")
          if (f["roa"] != null) m.push("ROA " + f["roa"].toFixed(1) + "%")
          if (f["순이익"] != null) m.push("순익 " + eok(f["순이익"]))
          const sig: string[] = []
          for (const [k, lab] of SIG_LABELS) {
            if (f[k] != null) sig.push(lab + " " + f[k])
          }
          return (
            <div key={j} style={{ padding: "10px 0", borderTop: j === 0 ? "none" : "1px solid " + C.line }}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, marginBottom: 3, flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6, minWidth: 0, flexWrap: "wrap" }}>
                  <a href={url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 14, fontWeight: 700, color: C.violet, textDecoration: "none", letterSpacing: -0.2 }}>{t.name} ↗</a>
                  <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{t.ticker}</span>
                  {t.market ? <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 700 }}>{t.market}</span> : null}
                </div>
              </div>
              <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, letterSpacing: -0.2, lineHeight: 1.55 }}>{m.join(" · ")}</div>
              {sig.length > 0 ? <div style={{ fontSize: 11, color: C.amber, fontWeight: 700, marginTop: 2, letterSpacing: -0.2 }}>공시 · {sig.join(" · ")}</div> : null}
            </div>
          )
        })}
        {shown.length < rows.length ? (
          <div onClick={() => setPage(page + 1)} style={{ cursor: "pointer", textAlign: "center", fontSize: 12.5, fontWeight: 700, color: C.violet, padding: "12px 0 4px" }}>
            + {Math.min(PAGE, rows.length - shown.length)}개 더 ({shown.length}/{rows.length})
          </div>
        ) : null}
      </div>

      <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, padding: "10px 8px 2px", lineHeight: 1.5 }}>
        {(data._meta || {}).disclaimer || "사실·패턴만 — 점수·추천 아님 · 정렬=메트릭 정렬"}
      </div>
    </div>
  )
}

addPropertyControls(SmallcapScreener, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380, min: 320, max: 720 },
  dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
  reportPath: { type: ControlType.String, title: "리포트 경로", defaultValue: "/stock" },
  initialFilter: { type: ControlType.String, title: "진입 필터 key", defaultValue: "" },
})

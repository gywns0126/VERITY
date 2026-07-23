import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"

/**
 * 탐색 진입 허브 — AlphaNest 루프 1단계(탐색). "종목명을 몰라도 시작".
 * 업종(섹터) 카드 + 랭킹 2탭. 섹터 클릭 → Discovery `?sector=`, 종목 클릭 → StockReport `?q=`.
 * 데이터(Blob): sector_overview.json (섹터 집계 — DART 파생 medians + 수급). 랭킹 = 네이버 금융 link-out.
 * 🚨 시세 재배포 컴플라이언스(2026-07-02): ranking_board(KRX 거래대금·등락·시총 raw) 자체 발행 중단 →
 *   랭킹은 네이버가 서빙(재배포 아님). 섹터 카드의 avg_chg(KRX 등락)도 제거, DART 파생 medians·수급만 유지.
 *
 * 🚨 RULE 7 — 외부 사실(중앙값·수급)만. 자체 점수/등급/추천 0. 검증 점수 held(2027).
 *    RULE 6 — LLM narrative 0. 다크모드 자가감지(body[data-framer-theme]). cache-fallback(sessionStorage).
 */

const LIGHT = {
  bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
  line: "#e5e8eb", red: "#f04452", blue: "#3182f6", violet: "#6c5ce7", violetSoft: "#f0edff",
}
const DARK = {
  bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
  line: "#2b2f37", red: "#ff6b76", blue: "#5a9cff", violet: "#a98bff", violetSoft: "#2a2440",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const SECTOR_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/sector_overview.json"
// 랭킹 = 네이버 금융 link-out(네이버가 서빙 = 재배포 아님, 실시간·무료·합법). KRX raw 자체 발행 중단.
const NAVER_RANK = [
  { label: "거래대금 상위", url: "https://finance.naver.com/sise/sise_quant.naver" },
  { label: "상승률 상위", url: "https://finance.naver.com/sise/sise_rise.naver" },
  { label: "하락률 상위", url: "https://finance.naver.com/sise/sise_fall.naver" },
  { label: "시가총액 상위", url: "https://finance.naver.com/sise/sise_market_sum.naver" },
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
function sharesShort(v: any): string {
  const x = Number(v)
  if (!isFinite(x) || x === 0) return "0"
  const sign = x < 0 ? "-" : "+"
  const a = Math.abs(x)
  if (a >= 1e8) return sign + (a / 1e8).toFixed(1) + "억주"
  if (a >= 1e4) return sign + Math.round(a / 1e4).toLocaleString() + "만주"
  return sign + Math.round(a).toLocaleString() + "주"
}
function fmtAge(iso: any): string {
  if (!iso) return ""
  try {
    const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
    if (mins < 60) return mins + "분 전"
    const hrs = Math.round(mins / 60)
    if (hrs < 24) return hrs + "시간 전"
    return Math.round(hrs / 24) + "일 전"
  } catch (e) {
    return ""
  }
}

// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.
let __anHyd = false
function anReadDark(): boolean {
    if (typeof document === "undefined") return false
    if (!__anHyd) {
        __anHyd = true
        return false
    }
    const h = document.documentElement ? document.documentElement.dataset.anTheme : null
    if (h === "dark") return true
    if (h === "light") return false
    return !!(document.body && document.body.dataset.framerTheme === "dark")
}


export default function PublicExploreHub(props: {
  width?: number; dark?: boolean; sectorUrl?: string; discoverPath?: string; stockPath?: string
}) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : anReadDark()))
  const isDark = onCanvas ? !!props.dark : themeDark
  const C = isDark ? DARK : LIGHT
  const discoverPath = props.discoverPath || "/discover"
  const stockPath = props.stockPath || "/stock"

  const [tab, setTab] = useState<string>("sector")
  const [sectors, setSectors] = useState<any[]>([])
  const [asOf, setAsOf] = useState<string>("")

  useEffect(() => {
    if (onCanvas) return
    setThemeDark(readBodyDark())
    const obs = new MutationObserver(() => setThemeDark(readBodyDark()))
    if (document.body) obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
    return () => obs.disconnect()
  }, [onCanvas])

  useEffect(() => {
    if (onCanvas) return
    let alive = true
    const load = (url: string, cacheKey: string, setter: (v: any) => void, pick: (d: any) => any) => {
      fetch(url)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          const v = d && pick(d)
          if (alive && v) { setter(v); try { sessionStorage.setItem(cacheKey, JSON.stringify(v)) } catch (e) {} }
          const ts = d && d._meta && d._meta.generated_at
          if (alive && ts) setAsOf(String(ts))
        })
        .catch(() => {
          try { const c = sessionStorage.getItem(cacheKey); if (alive && c) setter(JSON.parse(c)) } catch (e) {}
        })
    }
    load(props.sectorUrl || SECTOR_URL, "explore_sectors", setSectors, (d) => d.sectors)
    return () => { alive = false }
  }, [onCanvas, props.sectorUrl])

  const go = (path: string, q: string, val: string) => {
    if (onCanvas) return
    try { window.location.href = path + "?" + q + "=" + encodeURIComponent(val) } catch (e) {}
  }

  const wrap: any = { width: props.width || 380, fontFamily: FONT, background: C.bg, color: C.ink, padding: 14, boxSizing: "border-box" }
  const tabBtn = (v: string, lb: string) => (
    <button onClick={() => setTab(v)} style={{
      border: "none", cursor: "pointer", fontFamily: FONT, padding: "8px 16px", borderRadius: 10,
      fontSize: 13, fontWeight: 800, background: tab === v ? C.violet : C.card, color: tab === v ? "#fff" : C.sub,
    }}>{lb}</button>
  )

  return (
    <div style={wrap}>
      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        {tabBtn("sector", "업종")}
        {tabBtn("ranking", "랭킹")}
      </div>

      {tab === "sector" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(168px, 1fr))", gap: 10 }}>
          {sectors.map((s: any) => (
            <div key={s.sector} style={{ background: C.card, borderRadius: 14, padding: 13, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
              <div onClick={() => go(discoverPath, "sector", s.sector)} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", cursor: "pointer" }}>
                <span style={{ fontSize: 14.5, fontWeight: 800, color: C.ink }}>{s.sector}</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: C.faint }}>›</span>
              </div>
              <div style={{ fontSize: 11, color: C.faint, fontWeight: 700, marginTop: 2 }}>{s.n}종목 · 중앙 PER {s.median_per != null ? s.median_per : "—"} · PBR {s.median_pbr != null ? s.median_pbr : "—"}</div>
              <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 3 }}>외인 {sharesShort(s.flow_foreign)} · 기관 {sharesShort(s.flow_inst)}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
                {(s.leaders || []).slice(0, 4).map((l: any) => (
                  <span key={l.ticker} onClick={() => go(stockPath, "q", l.ticker)} style={{
                    cursor: "pointer", fontSize: 10.5, fontWeight: 700, padding: "3px 7px", borderRadius: 7,
                    background: C.violetSoft, color: C.violet,
                  }}>{l.name}</span>
                ))}
              </div>
            </div>
          ))}
          {sectors.length === 0 && <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>업종 데이터 준비 중…</div>}
          {asOf && sectors.length > 0 && (
            <div style={{ gridColumn: "1 / -1", fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>
              데이터 {fmtAge(asOf)} 업데이트
            </div>
          )}
        </div>
      )}

      {tab === "ranking" && (
        <div>
          <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginBottom: 10, lineHeight: 1.5 }}>실시간 랭킹은 네이버 금융에서 · 클릭 시 새 탭</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(168px, 1fr))", gap: 10 }}>
            {NAVER_RANK.map((r) => (
              <div key={r.url} onClick={() => { if (typeof window !== "undefined") window.open(r.url, "_blank", "noopener") }}
                style={{ background: C.card, borderRadius: 14, padding: 15, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>{r.label}</span>
                <span style={{ fontSize: 11.5, fontWeight: 700, color: C.violet }}>네이버 ↗</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
        외부 사실(DART 중앙값·수급)만 · 랭킹=네이버 금융 · 자체 점수/추천 아님
      </div>
    </div>
  )
}

addPropertyControls(PublicExploreHub, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
  dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
  sectorUrl: { type: ControlType.String, title: "Sector URL", defaultValue: SECTOR_URL },
  discoverPath: { type: ControlType.String, title: "Discover Path", defaultValue: "/discover" },
  stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
})

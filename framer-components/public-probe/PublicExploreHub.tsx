import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"

/**
 * 탐색 진입 허브 — AlphaNest 루프 1단계(탐색). 업종 카드 + 랭킹 2탭.
 * 섹터 클릭 → Discovery ?sector=, 종목 클릭 → StockReport ?q=. 랭킹 = 네이버 금융 link-out(재배포 아님).
 * 🚨 RULE 7 — 외부 사실(중앙값·수급)만. 자체 점수/등급/추천 0. RULE 6 — LLM narrative 0.
 *
 * 🚨 2026-07-24 테마 = 자체 내장 CSS 변수(--an-exh-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
 *   <style>{AN_PALETTE} 정적 HTML 정합. vtBtn = 솔리드 액센트 버튼(양모드 순보라 #6c5ce7 + 흰 글자, 가시성). 되돌리지 말 것.
 */

const LIGHT = {
  bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
  line: "#e5e8eb", red: "#f04452", blue: "#3182f6", violet: "#6c5ce7", violetSoft: "#f0edff", vtBtn: "#6c5ce7",
}
const DARK = {
  bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
  line: "#2b2f37", red: "#ff6b76", blue: "#5a9cff", violet: "#a98bff", violetSoft: "#2a2440", vtBtn: "#6c5ce7",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-exh-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "exh"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

const SECTOR_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/sector_overview.json"
const NAVER_RANK = [
  { label: "거래대금 상위", url: "https://finance.naver.com/sise/sise_quant.naver" },
  { label: "상승률 상위", url: "https://finance.naver.com/sise/sise_rise.naver" },
  { label: "하락률 상위", url: "https://finance.naver.com/sise/sise_fall.naver" },
  { label: "시가총액 상위", url: "https://finance.naver.com/sise/sise_market_sum.naver" },
]

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

export default function PublicExploreHub(props: {
  width?: number; dark?: boolean; sectorUrl?: string; discoverPath?: string; stockPath?: string
}) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const discoverPath = props.discoverPath || "/discover"
  const stockPath = props.stockPath || "/stock"

  const [tab, setTab] = useState<string>("sector")
  const [sectors, setSectors] = useState<any[]>([])
  const [asOf, setAsOf] = useState<string>("")

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
      fontSize: 13, fontWeight: 800, background: tab === v ? C.vtBtn : C.card, color: tab === v ? "#fff" : C.sub,
    }}>{lb}</button>
  )

  return (
    <div style={wrap}>
      <style>{AN_PALETTE}</style>
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
  dark: { type: ControlType.Boolean, title: "Dark(미사용)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
  sectorUrl: { type: ControlType.String, title: "Sector URL", defaultValue: SECTOR_URL },
  discoverPath: { type: ControlType.String, title: "Discover Path", defaultValue: "/discover" },
  stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
})

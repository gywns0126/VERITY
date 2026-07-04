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
  line: "#e5e8eb", red: "#f04452", blue: "#3182f6", violet: "#6c5ce7", violetSoft: "#f0edff", gTint: "rgba(108,92,231,0.22)",
}
const DARK = {
  bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
  line: "#2b2f37", red: "#ff6b76", blue: "#5a9cff", violet: "#a98bff", violetSoft: "#2a2440", gTint: "rgba(169,155,255,0.26)",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const SECTOR_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/sector_overview.json"
// 랭킹 = 네이버 금융 link-out(네이버가 서빙 = 재배포 아님, 실시간·무료·합법). KRX raw 자체 발행 중단.
const NAVER_RANK = [
  { k: "quant", label: "거래대금 상위", url: "https://finance.naver.com/sise/sise_quant.naver" },
  { k: "rise", label: "상승률 상위", url: "https://finance.naver.com/sise/sise_rise.naver" },
  { k: "fall", label: "하락률 상위", url: "https://finance.naver.com/sise/sise_fall.naver" },
  { k: "mcap", label: "시가총액 상위", url: "https://finance.naver.com/sise/sise_market_sum.naver" },
]

/* 글래스 아이콘 (토스식, 2026-07-04) — PublicGlassIcon 세트 재사용 4종 (코인스택↑/코인↑/코인↓/금고). 인라인 자립. */
const _rr = (x: number, y: number, w: number, h: number, r: number): string =>
  `M${x + r} ${y} H${x + w - r} Q${x + w} ${y} ${x + w} ${y + r} V${y + h - r} Q${x + w} ${y + h} ${x + w - r} ${y + h} H${x + r} Q${x} ${y + h} ${x} ${y + h - r} V${y + r} Q${x} ${y} ${x + r} ${y} Z`
const _circ = (cx: number, cy: number, r: number): string =>
  `M${cx - r} ${cy} a${r} ${r} 0 1 0 ${r * 2} 0 a${r} ${r} 0 1 0 ${-r * 2} 0 Z`
const GICONS: Record<string, { solid: (a: string) => any; glass: string }> = {
  quant: {
    solid: (a) => (
      <g fill="none" stroke={a} strokeWidth={4.5} strokeLinecap="round" strokeLinejoin="round">
        <line x1={36} y1={36} x2={36} y2={16} />
        <polyline points="29,22 36,14.5 43,22" />
      </g>
    ),
    glass: _rr(7.5, 19, 28, 5.5, 2.75) + " " + _rr(7.5, 26, 28, 5.5, 2.75) + " " + _rr(7.5, 33, 28, 5.5, 2.75),
  },
  rise: {
    solid: (a) => (
      <g fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round">
        <line x1={36} y1={30} x2={36} y2={18} />
        <polyline points="31,23 36,17.5 41,23" />
      </g>
    ),
    glass: _circ(20, 26, 13),
  },
  fall: {
    solid: (a) => (
      <g fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round">
        <line x1={36} y1={18} x2={36} y2={30} />
        <polyline points="31,25 36,30.5 41,25" />
      </g>
    ),
    glass: _circ(20, 26, 13),
  },
  mcap: {
    solid: (a) => (
            <g>
                <path d="M30.5 27.5 V23.5 a4.75 4.75 0 0 1 9.5 0 V27.5" fill="none" stroke={a} strokeWidth={3.2} strokeLinecap="round" />
                <path d="M31 27 H40 Q43.5 27 43.5 30.5 V37 Q43.5 40.5 40 40.5 H31 Q27.5 40.5 27.5 37 V30.5 Q27.5 27 31 27 Z" fill={a} />
                <circle cx={35.5} cy={33.5} r={2.2} fill="#ffffff" fillOpacity={0.92} />
            </g>
        ),
    glass: _rr(6, 5, 34, 36, 6) + " " + _rr(10.5, 41.5, 8, 3.5, 1.75) + " " + _rr(27.5, 41.5, 8, 3.5, 1.75),
  },
}
function GIcon(props: { k: string; size: number; a: string; g: string }) {
  const def = GICONS[props.k]
  if (!def) return null
  const fid = "xhf-" + props.k
  const cid = "xhc-" + props.k
  return (
    <svg width={props.size} height={props.size} viewBox="0 0 48 48" fill="none" style={{ display: "block", flexShrink: 0, overflow: "visible" }}>
      <defs>
        <filter id={fid} x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.1" /></filter>
        <clipPath id={cid}><path d={def.glass} /></clipPath>
      </defs>
      <g className="xhGiS">{def.solid(props.a)}</g>
      <g className="xhGiG">
        <g clipPath={`url(#${cid})`}>
          <g filter={`url(#${fid})`} opacity={0.85}>{def.solid(props.a)}</g>
          <path d={def.glass} fill={props.g} />
        </g>
      </g>
    </svg>
  )
}

function readBodyDark(): boolean {
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

export default function PublicExploreHub(props: {
  width?: number; dark?: boolean; sectorUrl?: string; discoverPath?: string; stockPath?: string
}) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
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
      fetch(url, { cache: "no-store" })
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
          <style>{`
            .xhGiS{animation:xhPop .5s cubic-bezier(.34,1.6,.64,1) both;transform-box:fill-box;transform-origin:center}
            .xhGiG{animation:xhRise .45s ease-out both}
            @keyframes xhPop{0%{transform:scale(.45) rotate(-10deg);opacity:0}100%{transform:scale(1) rotate(0deg);opacity:1}}
            @keyframes xhRise{0%{transform:translateY(5px);opacity:0}100%{transform:translateY(0);opacity:1}}
            .xhCard svg{transition:transform .18s ease}
            .xhCard:hover svg{transform:translateY(-1.5px) scale(1.08)}
            @media (prefers-reduced-motion: reduce){.xhGiS,.xhGiG{animation:none}.xhCard svg{transition:none}}
          `}</style>
          <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginBottom: 10, lineHeight: 1.5 }}>실시간 랭킹은 네이버 금융에서 · 클릭 시 새 탭</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(168px, 1fr))", gap: 10 }}>
            {NAVER_RANK.map((r) => (
              <div key={r.url} className="xhCard" onClick={() => { if (typeof window !== "undefined") window.open(r.url, "_blank", "noopener") }}
                style={{ background: C.card, borderRadius: 14, padding: 15, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", cursor: "pointer", display: "flex", alignItems: "center", gap: 9 }}>
                <GIcon k={(r as any).k} size={22} a={C.violet} g={C.gTint} />
                <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>{r.label}</span>
                <span style={{ fontSize: 11.5, fontWeight: 700, color: C.violet, marginLeft: "auto" }}>네이버 ↗</span>
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

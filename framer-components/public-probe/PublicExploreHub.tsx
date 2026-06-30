import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"

/**
 * 탐색 진입 허브 — AlphaNest 루프 1단계(탐색). "종목명을 몰라도 시작".
 * 업종(섹터) 카드 + 랭킹 보드 2탭. 섹터 클릭 → Discovery `?sector=`, 종목 클릭 → StockReport `?q=`.
 * 데이터(Blob): sector_overview.json (섹터 집계) / ranking_board.json (거래대금·등락·수급·시총).
 *
 * 🚨 RULE 7 — 외부 사실(중앙값·랭킹·수급)만. 자체 점수/등급/추천 0. 검증 점수 held(2027).
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
const RANKING_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/ranking_board.json"

function readBodyDark(): boolean {
  if (typeof document === "undefined" || !document.body) return false
  return document.body.dataset.framerTheme === "dark"
}
function wonShort(v: any): string {
  const x = Number(v)
  if (!isFinite(x) || x <= 0) return "—"
  if (x >= 1e12) return (x / 1e12).toFixed(1) + "조"
  if (x >= 1e8) return Math.round(x / 1e8).toLocaleString() + "억"
  return Math.round(x).toLocaleString()
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
function pctStr(v: any): string {
  const x = Number(v)
  if (!isFinite(x)) return "—"
  return (x >= 0 ? "+" : "") + x.toFixed(2) + "%"
}
function fmtByUnit(v: any, unit: string): string {
  if (unit === "%") return pctStr(v)
  if (unit === "주") return sharesShort(v)
  return wonShort(v) + "원"
}

export default function PublicExploreHub(props: {
  width?: number; dark?: boolean; sectorUrl?: string; rankingUrl?: string; discoverPath?: string; stockPath?: string
}) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
  const isDark = onCanvas ? !!props.dark : themeDark
  const C = isDark ? DARK : LIGHT
  const discoverPath = props.discoverPath || "/discover"
  const stockPath = props.stockPath || "/stock"

  const [tab, setTab] = useState<string>("sector")
  const [sectors, setSectors] = useState<any[]>([])
  const [boards, setBoards] = useState<any[]>([])
  const [boardKey, setBoardKey] = useState<string>("")

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
        })
        .catch(() => {
          try { const c = sessionStorage.getItem(cacheKey); if (alive && c) setter(JSON.parse(c)) } catch (e) {}
        })
    }
    load(props.sectorUrl || SECTOR_URL, "explore_sectors", setSectors, (d) => d.sectors)
    load(props.rankingUrl || RANKING_URL, "explore_boards", (v: any) => { setBoards(v); if (v && v[0]) setBoardKey(v[0].key) }, (d) => d.boards)
    return () => { alive = false }
  }, [onCanvas, props.sectorUrl, props.rankingUrl])

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
  const chgColor = (v: any) => { const x = Number(v); if (!isFinite(x) || x === 0) return C.sub; return x > 0 ? C.red : C.blue }

  const activeBoard = boards.find((b) => b.key === boardKey) || boards[0]

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
                <span style={{ fontSize: 11.5, fontWeight: 700, color: chgColor(s.avg_chg) }}>{pctStr(s.avg_chg)}</span>
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
        </div>
      )}

      {tab === "ranking" && (
        <div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
            {boards.map((b: any) => (
              <button key={b.key} onClick={() => setBoardKey(b.key)} style={{
                border: "none", cursor: "pointer", fontFamily: FONT, padding: "6px 11px", borderRadius: 8, fontSize: 12, fontWeight: 700,
                background: (activeBoard && activeBoard.key === b.key) ? C.violetSoft : C.card, color: (activeBoard && activeBoard.key === b.key) ? C.violet : C.sub,
              }}>{b.label}</button>
            ))}
          </div>
          {activeBoard && activeBoard.note && <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginBottom: 8 }}>{activeBoard.note}</div>}
          <div style={{ background: C.card, borderRadius: 14, padding: "4px 14px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            {(activeBoard ? activeBoard.rows : []).map((r: any, i: number) => (
              <div key={r.ticker + i} onClick={() => go(stockPath, "q", r.ticker)} style={{
                display: "flex", gap: 10, alignItems: "center", padding: "10px 0", cursor: "pointer",
                borderTop: i === 0 ? "none" : "1px solid " + C.line,
              }}>
                <span style={{ flexShrink: 0, width: 20, fontSize: 12, fontWeight: 800, color: C.faint }}>{i + 1}</span>
                <span style={{ flex: 1, fontSize: 13.5, fontWeight: 700, color: C.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name || r.ticker}</span>
                {r.chg != null && <span style={{ flexShrink: 0, fontSize: 11.5, fontWeight: 700, color: chgColor(r.chg) }}>{pctStr(r.chg)}</span>}
                <span style={{ flexShrink: 0, width: 92, textAlign: "right", fontSize: 12.5, fontWeight: 800, color: C.ink }}>{fmtByUnit(r.value, activeBoard.unit)}</span>
              </div>
            ))}
            {(!activeBoard || activeBoard.rows.length === 0) && <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600, padding: "10px 0" }}>랭킹 데이터 준비 중…</div>}
          </div>
        </div>
      )}

      <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
        외부 사실(중앙값·랭킹·수급)만 · 자체 점수/추천 아님 · 클릭 시 종목 리포트로 이동
      </div>
    </div>
  )
}

addPropertyControls(PublicExploreHub, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
  dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
  sectorUrl: { type: ControlType.String, title: "Sector URL", defaultValue: SECTOR_URL },
  rankingUrl: { type: ControlType.String, title: "Ranking URL", defaultValue: RANKING_URL },
  discoverPath: { type: ControlType.String, title: "Discover Path", defaultValue: "/discover" },
  stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"

/**
 * 소형주 코너 (통합) — 🇰🇷 한국 / 🇺🇸 미국 국기 토글. 1개로 KR+US 둘 다.
 * 기존 SmallcapCornerCard(KR) + USSmallcapCornerCard(US) 통합 (2026-06-27). market별 config inline.
 *
 * 3단 해석: 쉬운이름 · 배지 · 왜중요(why) · 투명기준(criteria_text). L1(탭): 종목 + 재무 사실.
 * 🚨 RULE 7 — 점수·등급·순위·verdict 0. 전부 공시/재무 사실. 검증 점수 held(2027). LLM 0(RULE 6).
 *    data: smallcap_corner_filters.json / us_smallcap_corner_filters.json. 다크모드 자가감지. cache-fallback.
 */

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
const FLAG = "https://hatscripts.github.io/circle-flags/flags/"

function makeTone(C: typeof LIGHT): Record<string, { fg: string; bg: string }> {
  return {
    neglected_quality: { fg: C.green, bg: C.greenSoft },
    smallcap_dilution: { fg: C.amber, bg: C.amberSoft },
    smallcap_distress: { fg: C.red, bg: C.redSoft },
    clean_fin_risky_disc: { fg: C.violet, bg: C.violetSoft },
    accounting_red_flag: { fg: C.blue, bg: C.blueSoft },
  }
}
function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
    } catch (e) {}
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function eok(won: number): string { return Math.round(won / 1e8).toLocaleString() + "억" }
function musd(m: number): string {
  if (m == null) return "—"
  if (m >= 1000) return "$" + (m / 1000).toFixed(1) + "B"
  return "$" + Math.round(m).toLocaleString() + "M"
}
const ZONE_KO: Record<string, string> = { safe: "안전", grey: "주의", distress: "위험" }

type Facts = { [k: string]: any }
type Ticker = { ticker: string; name: string; market?: string; facts: Facts }
type MarketCfg = {
  label: string; flag: string; url: string; cacheKey: string; reportPath: string; screenerPath: string;
  subtitle: string; sigLabel: string; factBits: (f: Facts) => string[]; factSig: (f: Facts) => string[];
}

const MARKETS: Record<"kr" | "us", MarketCfg> = {
  kr: {
    label: "한국", flag: "kr",
    url: "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/smallcap_corner_filters.json",
    cacheKey: "smallcap_corner_filters_cache", reportPath: "/stock", screenerPath: "/smallcap",
    subtitle: "시총 300~3000억 · 애널리스트·기관이 안 보는 코너. 사실·패턴만.",
    sigLabel: "공시",
    factBits: (f) => {
      const m: string[] = []
      if (f["시총_억"] != null) m.push("시총 " + Math.round(f["시총_억"]).toLocaleString() + "억")
      if (f["부채비율"] != null) m.push("부채 " + f["부채비율"].toFixed(0) + "%")
      if (f["roa"] != null) m.push("ROA " + f["roa"].toFixed(1) + "%")
      if (f["순이익"] != null) m.push("순익 " + eok(f["순이익"]))
      return m
    },
    factSig: (f) => {
      const s: string[] = []
      const pairs: [string, string][] = [["유상증자", "유상증자"], ["CB_BW", "CB/BW"], ["회생·상폐·감자", "회생·상폐·감자"], ["구조공시", "구조공시"]]
      for (const [k, lab] of pairs) if (f[k] != null) s.push(lab + " " + f[k])
      return s
    },
  },
  us: {
    label: "미국", flag: "us",
    url: "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/us_smallcap_corner_filters.json",
    cacheKey: "us_smallcap_corner_filters_cache", reportPath: "/us", screenerPath: "/us-smallcap",
    subtitle: "시총 $50M~$5B · sell-side 가 안 보는 미국 소형주. SEC 8-K 사실·패턴만.",
    sigLabel: "8-K",
    factBits: (f) => {
      const m: string[] = []
      if (f["mktcap_musd"] != null) m.push("시총 " + musd(f["mktcap_musd"]))
      if (f["dollar_volume_musd"] != null) m.push("거래대금 " + musd(f["dollar_volume_musd"]))
      if (f["revenue_yoy_pct"] != null) m.push("매출 " + (f["revenue_yoy_pct"] >= 0 ? "+" : "") + f["revenue_yoy_pct"].toFixed(0) + "%")
      if (f["operating_margin_pct"] != null) m.push("영업 " + f["operating_margin_pct"].toFixed(0) + "%")
      if (f["net_margin_pct"] != null) m.push("순익 " + f["net_margin_pct"].toFixed(0) + "%")
      if (f["roe_pct"] != null) m.push("ROE " + f["roe_pct"].toFixed(0) + "%")
      if (f["debt_to_equity"] != null) m.push("D/E " + f["debt_to_equity"].toFixed(1))
      if (f["altman_zone"] && ZONE_KO[f["altman_zone"]]) m.push("Altman " + ZONE_KO[f["altman_zone"]])
      if (f["fscore"] != null) m.push("F " + f["fscore"] + "/9")
      if (f["lynch_class"]) m.push(String(f["lynch_class"]))
      return m
    },
    factSig: (f) => {
      const s: string[] = []
      if (f["dilution_8k"]) s.push("희석 " + f["dilution_8k"])
      if (f["distress_8k"]) s.push("부실 " + f["distress_8k"])
      if (f["structural_8k"]) s.push("구조 " + f["structural_8k"])
      if (f["restatement"]) s.push("재무재작성 " + f["restatement"])
      if (f["auditor_change"]) s.push("회계법인교체 " + f["auditor_change"])
      return s
    },
  },
}

function FactRow(props: { t: Ticker; C: typeof LIGHT; market: "kr" | "us"; cfg: MarketCfg; reportPath: string }) {
  const { C, t, market, cfg } = props
  const f = t.facts || {}
  const url = t.ticker ? props.reportPath + "?q=" + encodeURIComponent(t.ticker) : ""
  const m = cfg.factBits(f)
  const sig = cfg.factSig(f)
  const nameKo = market === "us" ? f["name_ko"] : null
  const bizKo = market === "us" ? f["business_ko"] : null
  return (
    <div style={{ padding: "10px 2px", borderTop: "1px solid " + C.line }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6, minWidth: 0, flexWrap: "wrap" }}>
          {url ? (
            <a href={url} target="_blank" rel="noopener noreferrer" title={t.name + " 분석"} style={{ fontSize: 14, fontWeight: 700, color: C.violet, letterSpacing: -0.2, textDecoration: "none" }}>{t.name} ↗</a>
          ) : (
            <span style={{ fontSize: 14, fontWeight: 700, color: C.ink, letterSpacing: -0.2 }}>{t.name}</span>
          )}
          {nameKo ? <span style={{ fontSize: 11.5, color: C.sub, fontWeight: 600 }}>{nameKo}</span> : null}
          <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{t.ticker}</span>
          {market === "kr" && t.market ? <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 700 }}>{t.market}</span> : null}
        </div>
        {bizKo ? <span style={{ fontSize: 11, color: C.faint, fontWeight: 600, flexShrink: 0, textAlign: "right" }}>{bizKo}</span> : null}
      </div>
      <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, letterSpacing: -0.2, lineHeight: 1.55 }}>{m.join(" · ")}</div>
      {sig.length > 0 ? <div style={{ fontSize: 11, color: C.amber, fontWeight: 700, marginTop: 3, letterSpacing: -0.2 }}>{cfg.sigLabel} · {sig.join(" · ")}</div> : null}
    </div>
  )
}

export default function SmallcapCornerCardAll(props: { width?: number; dark?: boolean; market?: string; krReportPath?: string; usReportPath?: string; krScreenerPath?: string; usScreenerPath?: string }) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))
  const isDark = onCanvas ? !!props.dark : themeDark
  const C = isDark ? DARK : LIGHT
  const TONE = makeTone(C)
  const width = props.width || 380

  const [market, setMarket] = useState<"kr" | "us">(props.market === "us" ? "us" : "kr")
  const cfg = MARKETS[market]
  const reportPath = market === "us" ? (props.usReportPath || cfg.reportPath) : (props.krReportPath || cfg.reportPath)
  const screenerPath = market === "us" ? (props.usScreenerPath || cfg.screenerPath) : (props.krScreenerPath || cfg.screenerPath)

  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState<string>("")
  const [open, setOpen] = useState<number>(-1)

  useEffect(() => {
    if (onCanvas) return
    const read = () => setThemeDark(readBodyDark())
    read()
    if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
    const obs = new MutationObserver(read)
    obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
    return () => obs.disconnect()
  }, [onCanvas])

  // 데이터 로드 — market 전환 시 재fetch (market별 cache key)
  useEffect(() => {
    let alive = true
    setData(null); setErr(""); setOpen(-1)
    fetch(cfg.url + "?t=" + Date.now())
      .then((r) => { if (!r.ok) throw new Error("http " + r.status); return r.json() })
      .then((j) => { if (!alive) return; setData(j); try { sessionStorage.setItem(cfg.cacheKey, JSON.stringify(j)) } catch (e) {} })
      .catch((e) => {
        if (!alive) return
        try { const c = sessionStorage.getItem(cfg.cacheKey); if (c) { setData(JSON.parse(c)); return } } catch (er) {}
        setErr(String(e))
      })
    return () => { alive = false }
  }, [cfg.url, cfg.cacheKey])

  const shell = {
    width, fontFamily: "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif",
    background: "transparent", borderRadius: 24, padding: "0 16px", boxSizing: "border-box" as const, color: C.ink,
  }
  const flagBtn = (mk: "kr" | "us") => {
    const active = market === mk
    return (
      <div onClick={() => { if (mk !== market) { setMarket(mk) } }} style={{
        cursor: "pointer", display: "flex", alignItems: "center", gap: 6, padding: "5px 11px 5px 7px", borderRadius: 999,
        background: active ? C.violet : C.card, color: active ? C.bg : C.sub, fontSize: 12.5, fontWeight: 800, letterSpacing: -0.2,
      }}>
        <img src={FLAG + MARKETS[mk].flag + ".svg"} alt="" width={18} height={18} style={{ width: 18, height: 18, borderRadius: "50%", display: "block" }} />
        {MARKETS[mk].label}
      </div>
    )
  }

  const meta = (data && data._meta) || {}
  const filters: any[] = (data && data.filters) || []

  return (
    <div style={shell}>
      <style>{"@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}"}</style>

      {/* 국기 토글 + 카운트 */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "2px 2px 8px", gap: 8 }}>
        <div style={{ display: "flex", gap: 6 }}>{flagBtn("kr")}{flagBtn("us")}</div>
        <div style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>{meta.universe_n ? meta.universe_n.toLocaleString() + "종목" : (data ? "사실 필터" : "")}</div>
      </div>

      {err && !data ? (
        <div style={{ fontSize: 13, color: C.faint, fontWeight: 600, padding: 20, textAlign: "center" }}>데이터 로드 실패 — {err}</div>
      ) : !data ? (
        (() => {
          const base = isDark ? "#222a33" : "#e9edf1"
          const hi = isDark ? "#2d3742" : "#f3f5f7"
          const shimmer = { background: base, backgroundImage: "linear-gradient(90deg, " + base + " 25%, " + hi + " 37%, " + base + " 63%)", backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite" }
          const bar = (w: number | string, h: number, r: number) => ({ width: w, height: h, borderRadius: r, ...shimmer })
          return (
            <div style={{ background: C.card, borderRadius: 20, padding: 16, marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}><div style={bar(60, 18, 8)} /><div style={bar(90, 16, 6)} /></div>
                <div style={bar(28, 16, 6)} />
              </div>
              <div style={{ ...bar("70%", 13, 6), marginBottom: 12 }} />
              {[0, 1, 2, 3, 4, 5, 6, 7].map((k) => (
                <div key={k} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 2px", borderTop: "1px solid " + C.line }}>
                  <div style={bar(96, 14, 6)} /><div style={bar(120, 11, 6)} />
                </div>
              ))}
            </div>
          )
        })()
      ) : (
        <>
          <div style={{ fontSize: 12, color: C.sub, fontWeight: 600, padding: "0 4px 12px", letterSpacing: -0.2, lineHeight: 1.5 }}>{cfg.subtitle}</div>

          {filters.map((flt, i) => {
            const t = TONE[flt.key] || { fg: C.violet, bg: C.violetSoft }
            const isOpen = open === i
            const tickers = flt.tickers || []
            return (
              <div key={i} style={{ background: C.card, borderRadius: 20, padding: 16, marginBottom: 12, boxShadow: isDark ? "0 1px 3px rgba(0,0,0,0.3)" : "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 9 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ background: t.bg, color: t.fg, fontSize: 11, fontWeight: 800, padding: "4px 9px", borderRadius: 8 }}>{flt.badge}</span>
                    <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: -0.3 }}>{flt.name}</span>
                  </div>
                  <span style={{ fontSize: 15, fontWeight: 800, color: t.fg }}>{flt.count}</span>
                </div>
                <div style={{ fontSize: 13, color: C.sub, fontWeight: 600, letterSpacing: -0.2, lineHeight: 1.5, padding: "0 1px 9px" }}>{flt.why}</div>
                <div style={{ background: C.bg, borderRadius: 12, padding: "9px 11px", fontSize: 11.5, color: C.faint, fontWeight: 700, letterSpacing: -0.2, lineHeight: 1.5 }}>기준 · {flt.criteria_text}</div>
                {tickers.length > 0 ? (
                  <div onClick={() => setOpen(isOpen ? -1 : i)} style={{ cursor: "pointer", marginTop: 11, fontSize: 12.5, fontWeight: 700, color: t.fg, display: "flex", alignItems: "center", justifyContent: "center", gap: 5, padding: "8px", borderRadius: 10, background: isOpen ? t.bg : "transparent" }}>
                    종목 {tickers.length}개 보기 {isOpen ? "▴" : "▾"}
                  </div>
                ) : null}
                {isOpen ? (
                  <div style={{ marginTop: 4 }}>
                    {tickers.slice(0, 8).map((tk: Ticker, j: number) => <FactRow key={j} t={tk} C={C} market={market} cfg={cfg} reportPath={reportPath} />)}
                    {tickers.length > 8 ? (
                      <a href={screenerPath + "?filter=" + flt.key} target="_blank" rel="noopener noreferrer" style={{ display: "block", textAlign: "center", fontSize: 12.5, fontWeight: 700, color: t.fg, padding: "11px 0 3px", textDecoration: "none" }}>
                        전체 {flt.count}종목 스크리너 (검색·정렬) →
                      </a>
                    ) : null}
                  </div>
                ) : null}
              </div>
            )
          })}

          <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, padding: "6px 8px 2px", lineHeight: 1.5 }}>
            {meta.disclaimer || "사실·패턴만 — 알파네스트 검증 진행 중"}
          </div>
        </>
      )}
    </div>
  )
}

addPropertyControls(SmallcapCornerCardAll, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380, min: 320, max: 720 },
  dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
  market: { type: ControlType.Enum, title: "기본 시장", options: ["kr", "us"], optionTitles: ["한국", "미국"], defaultValue: "kr" },
  krReportPath: { type: ControlType.String, title: "KR 리포트 경로", defaultValue: "/stock" },
  usReportPath: { type: ControlType.String, title: "US 리포트 경로", defaultValue: "/us" },
  krScreenerPath: { type: ControlType.String, title: "US 스크리너 경로", defaultValue: "/smallcap" },
  usScreenerPath: { type: ControlType.String, title: "US 스크리너 경로", defaultValue: "/us-smallcap" },
})

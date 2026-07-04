import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"

/**
 * 검증 원장 (Validation Ledger) — AlphaNest 공개 표면. "기록 후 채점" 시스템 자체를 공개.
 * 데이터(Blob): validation_summary.json (사전등록 시그널 원장 — 시그널명 + 표본 N + N=252 게이트 진척).
 *
 * 🚨 RULE 7 — raw 성과(IC·적중률·기댓값·CI)는 게이트(N≥252, 2027-05) 전 봉인. 여기서는
 *   "봉인되어 있다는 사실"과 표본 누적 진척만 노출. 점수·등급·추천 0.
 *   차별점 = 숫자를 못 보여줄 때 왜 못 보여주는지(표본 부족)를 숫자로 보여주는 것.
 * RULE 6 — LLM narrative 0. 다크모드 자가감지(body[data-framer-theme]). cache-fallback(sessionStorage).
 */

const LIGHT = {
  bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
  line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", green: "#12b76a",
}
const DARK = {
  bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
  line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440", green: "#3ecf8e",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const DATA_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/validation_summary.json"

function readBodyDark(): boolean {
  if (typeof document === "undefined" || !document.body) return false
  return document.body.dataset.framerTheme === "dark"
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

/* 시그널 내부명 → 사용자 라벨 (내부 codename 그대로 노출 X) */
const SIGNAL_LABELS: Record<string, string> = {
  brain_production: "종합 판단 (Brain)",
  xgb_ml: "머신러닝 보조 (shadow)",
  shadow_funnel: "깔때기 필터 (shadow)",
  factor: "팩터 IC",
  sector: "섹터 관측",
}

const SAMPLE = {
  generated_at: "",
  gate: { target_n: 252, milestone: "N=252 IC 게이트", best_signal_n: 249, progress_pct: 98.7 },
  signals: [
    { signal: "brain_production", status: "채점 진행 중", n: 1244, n_eff: 248.8, label: "표본 누적", gate_status: "가설 (진척 98.7%)" },
    { signal: "xgb_ml", status: "채점 진행 중", n: 362, n_eff: 72.4, label: "예비", gate_status: "가설 (진척 28.7%)" },
  ],
}

export default function PublicValidationLedger(props: {
  width?: number; dark?: boolean; dataUrl?: string
}) {
  const onCanvas = RenderTarget.current() === RenderTarget.canvas
  const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
  const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)

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
    fetch(props.dataUrl || DATA_URL, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive && d && Array.isArray(d.signals)) {
          setData(d)
          try { sessionStorage.setItem("validation_ledger", JSON.stringify(d)) } catch (e) {}
        }
      })
      .catch(() => {
        try { const c = sessionStorage.getItem("validation_ledger"); if (alive && c) setData(JSON.parse(c)) } catch (e) {}
      })
    return () => { alive = false }
  }, [onCanvas, props.dataUrl])

  const isDark = onCanvas ? !!props.dark : themeDark
  const C = isDark ? DARK : LIGHT

  const wrap: any = { width: props.width || 380, fontFamily: FONT, background: C.bg, color: C.ink, padding: 14, boxSizing: "border-box" }
  if (!data) return <div style={wrap}><div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>검증 원장 준비 중…</div></div>

  const gate = data.gate || {}
  const targetN = gate.target_n || 252
  const signals: any[] = Array.isArray(data.signals) ? data.signals : []

  return (
    <div style={wrap}>
      {/* 헤더 */}
      <div style={{ marginBottom: 4 }}>
        <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>검증 원장</div>
        <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>
          모든 신호는 등록 시점에 고정 — 결과를 보고 지우거나 바꾸지 않아요
          {data.generated_at ? " · " + fmtAge(data.generated_at) + " 갱신" : ""}
        </div>
      </div>

      {/* 게이트 진행도 카드 */}
      <div style={{ background: C.card, borderRadius: 14, padding: 15, marginTop: 10, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, fontWeight: 800, color: C.ink }}>통계 판정 게이트</span>
          <span style={{ fontSize: 12, fontWeight: 800, color: C.violet }}>
            대표 신호 {gate.progress_pct != null ? gate.progress_pct.toFixed(1) : "—"}%
          </span>
        </div>
        <div style={{ position: "relative", height: 6, background: C.line, borderRadius: 3, marginTop: 10, overflow: "hidden" }}>
          <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: Math.min(100, gate.progress_pct || 0) + "%", background: C.violet, borderRadius: 3 }} />
        </div>
        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>
          표본 N={targetN} 도달 시 적중률·기댓값·신뢰구간 원본 공개. 그 전에는 표본이 부족해 동전던지기와 통계적으로 구분할 수 없어서 성과 숫자를 봉인해요.
        </div>
      </div>

      {/* 시그널 원장 rows */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
        {signals.map((sg: any) => {
          const nEff = sg.n_eff != null ? Number(sg.n_eff) : null
          const pct = nEff != null ? Math.min(100, (nEff / targetN) * 100) : 0
          const name = SIGNAL_LABELS[sg.signal] || sg.signal
          return (
            <div key={sg.signal} style={{ background: C.card, borderRadius: 14, padding: 13, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 13.5, fontWeight: 800, color: C.ink }}>{name}</span>
                <span style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>
                  {nEff != null ? "유효표본 " + nEff.toFixed(0) + " / " + targetN : "표본 0"}
                </span>
              </div>
              <div style={{ position: "relative", height: 4, background: C.line, borderRadius: 2, marginTop: 8, overflow: "hidden" }}>
                <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: pct + "%", background: pct >= 100 ? C.green : C.violet, borderRadius: 2 }} />
              </div>
              <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>
                {sg.status}{sg.label ? " · " + sg.label : ""}
              </div>
            </div>
          )
        })}
        {signals.length === 0 && <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>등록된 신호 없음</div>}
      </div>

      {/* RULE 7 disclaimer */}
      <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
        전 항목 가설 · 관측 전용 · 성과 원본은 게이트 도달 후 공개
      </div>
    </div>
  )
}

addPropertyControls(PublicValidationLedger, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
  dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
  dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DATA_URL },
})

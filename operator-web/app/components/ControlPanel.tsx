"use client"
// ControlPanel — 매매 기준 제어판 (갭3, PREREG_TRADING_BANDS Part D · PM 승인 2026-08-02).
// 총액 → tier 자동 밴드(api/portfolio/band_scaler.py 와 동일 표 — 수정 시 양쪽 동기 의무) +
// 브라우저 로컬 시뮬레이션. 실제 band_scaler/rebalance 입력과 연결되지 않으므로 강제 override 로
// 오인시키지 않는다. 서버 연동 전까지 값과 이력은 이 브라우저에서만 유지한다.
// 표시값 철학 — 자동 매매 없음. 외곽선/이모지/좌측바 금지(경계=채움색).
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM } from "@/lib/theme"

const VAL_KEY = "af_total_value_krw"
const OVR_KEY = "af_band_overrides" // {values:{...}|null, log:[{ts,values,reason}]}

// band_scaler.py _TIERS 미러 (S<1천만×1.4 / M<1억×1.0 / L<10억×0.8 / XL×1.2)
const TIERS = [
    { upper: 10_000_000, tier: "S", mult: 1.4, drift: 30, minTrade: 300_000 },
    { upper: 100_000_000, tier: "M", mult: 1.0, drift: 20, minTrade: 500_000 },
    { upper: 1_000_000_000, tier: "L", mult: 0.8, drift: 12, minTrade: 1_000_000 },
    { upper: Infinity, tier: "XL", mult: 1.2, drift: 18, minTrade: 1_000_000 },
] as const

type Values = { entryMult: number; stopMult: number; driftPct: number; minTrade: number }
type LogRow = { ts: string; values: Values | null; reason: string }

function tierOf(v: number) {
    return TIERS.find((t) => v < t.upper) || TIERS[1]
}
function autoValues(total: number): Values {
    const t = tierOf(total > 0 ? total : 50_000_000)
    return { entryMult: t.mult, stopMult: t.mult, driftPct: t.drift, minTrade: t.minTrade }
}
function loadState(): { total: number; ovr: Values | null; log: LogRow[] } {
    let total = 0, ovr = null, log: LogRow[] = []
    try {
        total = Number(localStorage.getItem(VAL_KEY)) || 0
        const raw = localStorage.getItem(OVR_KEY)
        if (raw) {
            const d = JSON.parse(raw)
            ovr = d.values || null
            log = Array.isArray(d.log) ? d.log : []
        }
    } catch {}
    return { total, ovr, log }
}

export default function ControlPanel() {
    const dark = useDark()
    const c = palette(dark)
    const [total, setTotal] = useState(0)
    const [ovr, setOvr] = useState<Values | null>(null)
    const [log, setLog] = useState<LogRow[]>([])
    const [draft, setDraft] = useState<Values | null>(null)
    const [reason, setReason] = useState("")
    const [msg, setMsg] = useState("")

    useEffect(() => {
        const s = loadState()
        setTotal(s.total)
        setOvr(s.ovr)
        setLog(s.log)
    }, [])

    const auto = autoValues(total)
    const active = ovr || auto
    const t = tierOf(total > 0 ? total : 50_000_000)

    function persist(nextOvr: Values | null, nextLog: LogRow[]) {
        setOvr(nextOvr)
        setLog(nextLog)
        try {
            localStorage.setItem(OVR_KEY, JSON.stringify({ values: nextOvr, log: nextLog }))
        } catch {}
    }
    function saveTotal(v: number) {
        setTotal(v)
        try {
            localStorage.setItem(VAL_KEY, String(v))
        } catch {}
    }
    function apply() {
        if (!draft) return
        if (reason.trim().length < 4) {
            setMsg("사유 필수(4자 이상) — RULE 7 기록 의무")
            return
        }
        const row: LogRow = { ts: new Date().toISOString().slice(0, 16).replace("T", " "), values: draft, reason: reason.trim() }
        persist(draft, [row, ...log].slice(0, 50))
        setDraft(null)
        setReason("")
        setMsg("로컬 시뮬레이션 적용됨")
    }
    function resetDefault() {
        const row: LogRow = { ts: new Date().toISOString().slice(0, 16).replace("T", " "), values: null, reason: "기본값 복귀" }
        persist(null, [row, ...log].slice(0, 50))
        setDraft(null)
        setMsg("tier 자동값 복귀")
    }

    const num = (v: number) => v.toLocaleString()
    const field = (label: string, key: keyof Values, step: number) => {
        const d = draft || active
        return (
            <label style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, minWidth: 120 }}>
                <span style={{ fontSize: 10.5, fontWeight: 700, color: c.faint }}>{label}</span>
                <input
                    type="number"
                    step={step}
                    value={d[key]}
                    onChange={(e) => setDraft({ ...(draft || active), [key]: Number(e.target.value) })}
                    style={{ background: dark ? c.bg : c.track, color: c.ink, border: "none", borderRadius: 10, padding: "9px 11px", fontSize: 13, fontFamily: FONT, outline: "none", fontVariantNumeric: "tabular-nums" }}
                />
            </label>
        )
    }

    return (
        <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ ...cardStyle(c), display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 800, color: c.ink }}>매매 기준 시뮬레이터</span>
                    <span style={{ fontSize: 10, color: c.faint }}>이 브라우저에서만 계산 · 실제 주문·리밸런싱 미연동</span>
                </div>

                <div style={{ display: "flex", alignItems: "flex-end", gap: 10, flexWrap: "wrap" }}>
                    <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontSize: 10.5, fontWeight: 700, color: c.faint }}>보유 총액 (원)</span>
                        <input
                            type="number"
                            value={total || ""}
                            placeholder="예: 8000000"
                            onChange={(e) => saveTotal(Number(e.target.value) || 0)}
                            style={{ background: dark ? c.bg : c.track, color: c.ink, border: "none", borderRadius: 10, padding: "9px 11px", fontSize: 13, fontFamily: FONT, outline: "none", width: 150, ...NUM }}
                        />
                    </label>
                    <span style={{ fontSize: 11, fontWeight: 700, color: c.vt, background: c.vtS, borderRadius: 8, padding: "5px 10px" }}>
                        tier {t.tier} · 밴드 ×{t.mult} · 드리프트 ±{t.drift}% · 최소 {num(t.minTrade)}원
                    </span>
                    {ovr ? <span style={{ fontSize: 11, fontWeight: 700, color: c.amber, background: c.amberS, borderRadius: 8, padding: "5px 10px" }}>로컬 조정 활성</span> : null}
                </div>

                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    {field("진입폭 배율", "entryMult", 0.1)}
                    {field("손절폭 배율", "stopMult", 0.1)}
                    {field("드리프트 ±%", "driftPct", 1)}
                    {field("최소거래액", "minTrade", 100000)}
                </div>

                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <input
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="변경 사유 (필수 — RULE 7 기록)"
                        style={{ flex: 1, minWidth: 200, background: dark ? c.bg : c.track, color: c.ink, border: "none", borderRadius: 10, padding: "9px 11px", fontSize: 12.5, fontFamily: FONT, outline: "none" }}
                    />
                    <button onClick={apply} disabled={!draft} style={{ border: "none", borderRadius: 10, padding: "9px 14px", fontSize: 12.5, fontWeight: 800, fontFamily: FONT, cursor: draft ? "pointer" : "default", background: draft ? c.vt : c.hi, color: draft ? "#fff" : c.faint }}>
                        로컬 적용
                    </button>
                    <button onClick={resetDefault} style={{ border: "none", borderRadius: 10, padding: "9px 14px", fontSize: 12.5, fontWeight: 700, fontFamily: FONT, cursor: "pointer", background: c.hi, color: c.sub }}>
                        기본값 복귀
                    </button>
                </div>
                {msg ? <div style={{ fontSize: 11, color: c.amber }}>{msg}</div> : null}
                <div style={{ fontSize: 10.5, color: c.faint, lineHeight: 1.5 }}>
                    자동값과 조정값은 비교용입니다. 실제 설정은 서버의 사전등록 band_scaler를 사용합니다.
                </div>
            </div>

            {log.length ? (
                <div style={{ ...cardStyle(c, "12px 15px"), display: "flex", flexDirection: "column", gap: 6 }}>
                    <span style={{ fontSize: 11, fontWeight: 800, color: c.faint }}>이 브라우저의 시뮬레이션 이력</span>
                    {log.slice(0, 6).map((r, i) => (
                        <div key={i} style={{ display: "flex", gap: 8, fontSize: 11.5, paddingTop: i === 0 ? 0 : 5, borderTop: i === 0 ? "none" : `1px solid ${c.line}` }}>
                            <span style={{ color: c.faint, whiteSpace: "nowrap", ...NUM }}>{r.ts}</span>
                            <span style={{ color: c.ink }}>
                                {r.values ? `×${r.values.entryMult}/${r.values.stopMult} · ±${r.values.driftPct}% · ${num(r.values.minTrade)}` : "기본값 복귀"}
                                <span style={{ color: c.sub }}> — {r.reason}</span>
                            </span>
                        </div>
                    ))}
                </div>
            ) : null}
        </div>
    )
}

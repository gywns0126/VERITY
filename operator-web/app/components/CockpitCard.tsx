"use client"
// CockpitCard — 운영 콕핏 (구 프레이머 `pages/admin/OperatorCockpitCard.tsx` 이관, PM 2026-08-12).
// severity · 검증 N일 · 오퍼레이터 데드맨 · 24h 알림량 · 사전등록 대기.
// 소스 = 공개 Blob `metadata/cockpit_state.json` (데이터 로직 원본과 동일).
//
// 이관 시 바뀐 것 (되돌리지 말 것):
//   · 자체 LIGHT/DARK 토큰 + readBodyDark + MutationObserver → `@/lib/theme` 단일 소스
//   · 🚨 `?t=Date.now()` 캐시버스터 제거 — 공개 blob 에 캐시버스터 금지
//     ([[feedback_no_cachebuster_on_public_blobs]]). 원본 프레이머판은 매 로드마다 원본 전송을
//     유발했다. 콕핏은 cron 갱신이라 CDN 캐시로 충분하다.
//   · Framer 캔버스 분기 · SAMPLE 더미 · addPropertyControls 제거
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, CARD_TITLE, RAIL_PAD, FONT, NUM, type Palette } from "@/lib/theme"
import { fetchPublic } from "@/lib/api"

type PendingItem = { sha?: string; date?: string; subject?: string; missing?: string[] }
type CockpitState = {
    collected_at?: string
    severity?: "GREEN" | "YELLOW" | "RED"
    severity_reasons?: string[]
    n_verification_days?: number
    // 🚨 2026-08-18 — to_252 / to_365 제거. 폐기된 표본수 게이트(VALIDATION_METHODOLOGY §7-1)를
    //    향한 잔여일수였다. to_50 / to_100 은 방법론적 하한(IC 측정·PSR 적용)이라 유지.
    n_milestones?: { to_50?: number; to_100?: number }
    one_liner?: string
    operator_deadman?: { trigger?: string; days_git?: number; days_telegram?: number; days_uaq?: number; warn_days?: number }
    alert_volume_24h?: { sent?: number; dedupe_skip?: number; quiet_skip?: number; fp_repeat_max?: number }
    pre_registration_pending?: PendingItem[]
}

function n0(v: unknown): number {
    const x = Number(v)
    return isFinite(x) ? x : 0
}

export default function CockpitCard() {
    const dark = useDark()
    const c = palette(dark)
    const [state, setState] = useState<CockpitState | null>(null)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        let alive = true
        fetchPublic<CockpitState>("metadata/cockpit_state.json").then((r) => {
            if (!alive) return
            if (r.ok) {
                setState(r.data)
                setErr(null)
            } else setErr(r.error === "http" ? `HTTP ${r.status}` : r.error)
        })
        return () => {
            alive = false
        }
    }, [])

    const wrap = { ...cardStyle(c, RAIL_PAD), fontFamily: FONT, display: "flex", flexDirection: "column" as const, gap: 10 }

    if (err && !state) return <div style={wrap}><span style={{ fontSize: 12, color: c.down, fontWeight: 700 }}>콕핏 로드 실패 — {err}</span></div>
    if (!state) return <div style={wrap}><span style={{ fontSize: 12, color: c.faint }}>운영 콕핏 로딩…</span></div>

    const sev = state.severity || "GREEN"
    const sC = sev === "RED" ? c.down : sev === "YELLOW" ? c.amber : c.green
    const sBg = sev === "RED" ? c.downS : sev === "YELLOW" ? c.amberS : c.greenS
    const sLabel = sev === "RED" ? "위험" : sev === "YELLOW" ? "주의" : "정상"
    const odm = state.operator_deadman || {}
    const av = state.alert_volume_24h || {}
    const ms = state.n_milestones || {}
    const pending = state.pre_registration_pending || []
    const warn = n0(odm.warn_days) || 7

    const dayRow = (name: string, d: unknown) => {
        const v = n0(d)
        const col = v >= warn ? c.down : v >= warn * 0.7 ? c.amber : c.green
        return (
            <div key={name} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 11.5 }}>
                <span style={{ color: c.sub, fontWeight: 600 }}>{name}</span>
                <span style={{ ...NUM, color: col, fontWeight: 800 }}>{v.toFixed(1)}일</span>
            </div>
        )
    }
    const kv = (name: string, v: unknown, danger?: boolean) => (
        <div key={name} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 11.5 }}>
            <span style={{ color: c.sub, fontWeight: 600 }}>{name}</span>
            <span style={{ ...NUM, color: danger ? c.amber : c.ink, fontWeight: 800 }}>{n0(v)}</span>
        </div>
    )

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: sC }} />
                <span style={{ ...CARD_TITLE, color: c.ink }}>운영 콕핏</span>
                <span style={{ fontSize: 10.5, fontWeight: 800, color: sC, background: sBg, borderRadius: 6, padding: "2px 8px" }}>{sLabel}</span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: c.faint, ...NUM }}>
                    {(state.collected_at || "").slice(0, 16).replace("T", " ")}
                </span>
            </div>

            {state.one_liner ? <div style={{ fontSize: 12.5, color: c.sub, lineHeight: 1.5 }}>{state.one_liner}</div> : null}
            {(state.severity_reasons || []).map((r, i) => (
                <div key={i} style={{ fontSize: 11.5, color: sC, fontWeight: 700 }}>· {r}</div>
            ))}

            <div style={{ background: c.hi, borderRadius: 12, padding: "10px 12px" }}>
                <div style={{ fontSize: 10.5, fontWeight: 800, color: c.faint }}>검증 N일 (누적)</div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginTop: 2 }}>
                    <span style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-0.03em", color: c.ink, ...NUM }}>{n0(state.n_verification_days)}</span>
                    <span style={{ fontSize: 11, color: c.faint, fontWeight: 700 }}>일</span>
                </div>
                <div style={{ fontSize: 10.5, color: c.faint, fontWeight: 600, marginTop: 3, ...NUM }}>
                    50까지 {n0(ms.to_50)} · 100까지 {n0(ms.to_100)}
                </div>
            </div>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <div style={{ flex: "1 1 150px", background: c.hi, borderRadius: 12, padding: "9px 11px" }}>
                    <div style={{ fontSize: 10.5, fontWeight: 800, color: c.faint, marginBottom: 3 }}>오퍼레이터 데드맨</div>
                    {dayRow("git", odm.days_git)}
                    {dayRow("telegram", odm.days_telegram)}
                    {dayRow("uaq", odm.days_uaq)}
                    <div style={{ fontSize: 10, color: c.faint, fontWeight: 600, marginTop: 3 }}>trigger · {odm.trigger || "none"}</div>
                </div>
                <div style={{ flex: "1 1 150px", background: c.hi, borderRadius: 12, padding: "9px 11px" }}>
                    <div style={{ fontSize: 10.5, fontWeight: 800, color: c.faint, marginBottom: 3 }}>24시간 알림량</div>
                    {kv("전송(sent)", av.sent)}
                    {kv("중복 스킵", av.dedupe_skip)}
                    {kv("조용시간 스킵", av.quiet_skip)}
                    {kv("반복 최대", av.fp_repeat_max, n0(av.fp_repeat_max) > 10)}
                </div>
            </div>

            {pending.length > 0 ? (
                <div style={{ background: c.hi, borderRadius: 12, padding: "9px 11px" }}>
                    <div style={{ fontSize: 10.5, fontWeight: 800, color: c.faint, marginBottom: 4 }}>사전등록 대기 ({pending.length})</div>
                    {pending.slice(0, 5).map((p, i) => (
                        <div key={i} style={{ paddingTop: i === 0 ? 0 : 6, marginTop: i === 0 ? 0 : 6, borderTop: i === 0 ? "none" : `1px solid ${c.line}` }}>
                            <div style={{ display: "flex", gap: 7, alignItems: "baseline", flexWrap: "wrap" }}>
                                <span style={{ fontSize: 10.5, fontWeight: 800, color: c.vt, ...NUM }}>{p.sha}</span>
                                <span style={{ fontSize: 10, color: c.faint, fontWeight: 600, ...NUM }}>{p.date}</span>
                                <span style={{ fontSize: 11.5, color: c.ink, fontWeight: 600, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.subject}</span>
                            </div>
                            <div style={{ fontSize: 10, color: c.amber, fontWeight: 700, marginTop: 1 }}>missing: {(p.missing || []).join(", ")}</div>
                        </div>
                    ))}
                    {pending.length > 5 ? <div style={{ fontSize: 10.5, color: c.faint, fontWeight: 600, marginTop: 5 }}>+{pending.length - 5}건 더</div> : null}
                </div>
            ) : null}
        </div>
    )
}

export type { CockpitState, Palette }

"use client"
// TIDE (크립토 트랙) — 프론트 단일화 (PM 2026-08-04 "사이트 하나로 통합").
// 데이터 = 공개 blob tide/dashboard.json (TIDE repo 크론이 매 사이클 발행 — 백엔드 무변경).
// 구 tide-api/dashboard 사이트를 대체. TIDE 데이터의 자기 disclaimer(관측-only·가설·N 병기) 존중.
import { useEffect, useState } from "react"
import type { CSSProperties } from "react"
import { cardStyle, MAIN_PAD, NUM, type Palette } from "@/lib/theme"
import { fetchPublic } from "@/lib/api"

type TideDash = {
    generated_at?: string
    spec_version?: string
    phase0?: { a5_sharpe?: number; oos_sharpe_2024_2026?: number; oos_degradation_pct?: number; a5_mdd_pct?: number; a5_ann_return_pct?: number }
    paper?: { status?: string; cycles_count?: number; trades_count?: number }
    health?: {
        cron_status?: string; minutes_since_heartbeat?: number; last_heartbeat_kst?: string
        last_portfolio?: { total_value_krw?: number; cumulative_return_pct?: number | null; snapshot_date?: string }
        paper_validation?: { verdict?: string; eligible?: boolean; trades?: number; min_trades?: number }
    }
    regime?: { latest?: { label?: string; score?: number; regime_call?: string }; observation_only?: boolean }
}

function chip(bg: string, fg: string): CSSProperties {
    return { display: "inline-block", padding: "1px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700, background: bg, color: fg }
}

export default function TidePanel({ c }: { c: Palette }) {
    const [d, setD] = useState<TideDash | null>(null)
    const [err, setErr] = useState(false)
    useEffect(() => {
        fetchPublic<TideDash>("tide/dashboard.json").then((r) => {
            if (r.ok && r.data) setD(r.data)
            else setErr(true)
        }).catch(() => setErr(true))
    }, [])

    const k: CSSProperties = { fontSize: 12, color: c.faint, marginRight: 6 }
    const v: CSSProperties = { fontSize: 12.5, color: c.ink, ...NUM }
    const h = d?.health
    const pv = h?.paper_validation
    const healthy = h?.cron_status === "healthy"
    const won = (x?: number) => (typeof x === "number" ? Math.round(x).toLocaleString() + "원" : "—")

    return (
        <div style={{ ...cardStyle(c, MAIN_PAD) }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 10 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: c.down, alignSelf: "center", flexShrink: 0 }} />
                <span style={{ fontSize: 14, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>TIDE — 크립토 트랙</span>
                <span style={{ fontSize: 10, color: c.faint }}>
                    BTC/ETH TSM · 별도 트랙{d?.spec_version ? ` · ${d.spec_version}` : ""}{d?.generated_at ? ` · ${String(d.generated_at).slice(5, 16).replace("T", " ")}` : ""}
                </span>
                {d ? (
                    <span style={{ marginLeft: "auto" }}>
                        <span style={chip(healthy ? c.greenS : c.upS, healthy ? c.green : c.up)}>
                            {healthy ? `크론 정상 · HB ${h?.minutes_since_heartbeat ?? "?"}분 전` : `크론 이상 — ${h?.cron_status ?? "확인 안 됨"}`}
                        </span>
                    </span>
                ) : null}
            </div>

            {err ? (
                <div style={{ fontSize: 12.5, color: c.sub }}>tide/dashboard.json 불러오기 실패 — TIDE 크론 확인 필요.</div>
            ) : !d ? (
                <div style={{ fontSize: 12.5, color: c.sub }}>불러오는 중…</div>
            ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 22px", alignItems: "center" }}>
                    <span>
                        <span style={k}>페이퍼 자산</span>
                        <span style={v}>{won(h?.last_portfolio?.total_value_krw)}</span>
                        <span style={{ fontSize: 10, color: c.faint, marginLeft: 4 }}>
                            사이클 {d.paper?.cycles_count ?? "—"} · 거래 {d.paper?.trades_count ?? "—"}건
                        </span>
                    </span>
                    <span>
                        <span style={k}>게이트</span>
                        <span style={chip(pv?.eligible ? c.greenS : c.track, pv?.eligible ? c.green : c.sub)}>
                            {pv?.eligible ? "판정 가능" : "N 축적 중"}
                        </span>
                        <span style={{ fontSize: 10, color: c.faint, marginLeft: 4 }}>{pv?.verdict ?? ""}</span>
                    </span>
                    <span>
                        <span style={k}>백테스트</span>
                        <span style={v}>
                            Sharpe {d.phase0?.a5_sharpe ?? "—"} · OOS {d.phase0?.oos_sharpe_2024_2026 ?? "—"}
                            {typeof d.phase0?.oos_degradation_pct === "number" ? ` (열화 ${d.phase0.oos_degradation_pct}%)` : ""}
                            {typeof d.phase0?.a5_mdd_pct === "number" ? ` · MDD ${Math.abs(d.phase0.a5_mdd_pct).toFixed(1)}%` : ""}
                        </span>
                        <span style={{ fontSize: 10, color: c.faint, marginLeft: 3 }}>가설 · 백테스트</span>
                    </span>
                    <span>
                        <span style={k}>레짐 관측</span>
                        <span style={v}>{d.regime?.latest?.label ?? "—"} {d.regime?.latest?.score ?? ""}</span>
                        <span style={{ fontSize: 10, color: c.faint, marginLeft: 3 }}>관측-only · 매매 미연결</span>
                    </span>
                </div>
            )}
        </div>
    )
}

"use client"
// SystemMapCard — "이게 뭐고 얼마나 큰가" 구조 지도 (구 프레이머 `pages/admin/SystemMapCard.tsx` 이관, PM 2026-08-12).
// 경계 유지: CockpitCard = "지금 건강한가" / 여기 = 구조·규모만. 헬스·알림·N 상세는 중복하지 않는다.
// 소스 = 공개 Blob `metadata/system_map.json` (scripts/system_map.py 의 레포 실제 스캔 결과, 손그림 금지).
//
// 이관 시 바뀐 것 (되돌리지 말 것):
//   · 소스 raw.githubusercontent(VERITY-data) → 공개 Blob. 발행 경로 단일화 + `?t=` 캐시버스터 제거
//     ([[feedback_no_cachebuster_on_public_blobs]]).
//   · TIDE 다크 토큰(#0a0a0a·Lora·SF Mono·GREEN #7fffa0) → 오퍼레이터 팔레트. 토큰 자체 신설 금지 규율 정합.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, CARD_TITLE, RAIL_PAD, FONT, NUM, type Palette } from "@/lib/theme"
import { fetchPublic } from "@/lib/api"

type Scale = {
    code_lines_tsx_py?: number
    python_modules?: number
    tsx_components?: number
    json_data_files?: number
    workflows?: number
    scheduled_workflows?: number
    cron_triggers?: number
    git_tracked_files?: number
}
type Subsystem = {
    label?: string
    count?: number
    scheduled?: number
    n_trading_days?: number
    next_milestone?: { next_n?: number; days_remaining?: number; label?: string }
}
type SystemMap = {
    generated_at?: string
    scale?: Scale
    subsystems?: Partial<Record<"ingest" | "brain" | "automation" | "surface" | "data" | "validation", Subsystem>>
    funnel?: { stages?: number[]; labels?: string[]; status?: string }
}

function fmt(n?: number): string {
    return n == null ? "—" : n.toLocaleString("en-US")
}

export default function SystemMapCard() {
    const dark = useDark()
    const c = palette(dark)
    const [data, setData] = useState<SystemMap | null>(null)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        let alive = true
        fetchPublic<SystemMap>("metadata/system_map.json").then((r) => {
            if (!alive) return
            if (r.ok) {
                setData(r.data)
                setErr(null)
            } else setErr(r.error === "http" ? `HTTP ${r.status}` : r.error)
        })
        return () => {
            alive = false
        }
    }, [])

    const wrap = { ...cardStyle(c, RAIL_PAD), fontFamily: FONT, display: "flex", flexDirection: "column" as const, gap: 10 }
    if (err && !data) return <div style={wrap}><span style={{ fontSize: 12, color: c.down, fontWeight: 700 }}>시스템 맵 로드 실패 — {err}</span></div>
    if (!data) return <div style={wrap}><span style={{ fontSize: 12, color: c.faint }}>시스템 맵 로딩…</span></div>

    const s = data.scale || {}
    const sub = data.subsystems || {}
    const cnt = (k: keyof NonNullable<SystemMap["subsystems"]>) => sub[k]?.count ?? 0
    const valN = sub.validation?.n_trading_days ?? 0
    const valNext = sub.validation?.next_milestone || {}
    const scheduled = sub.automation?.scheduled ?? 0
    const stages = data.funnel?.stages || []
    const labels = data.funnel?.labels || []
    const maxStage = stages.length ? Math.max(...stages) : 1

    const stat = (v: string, label: string) => (
        <span key={label} style={{ display: "inline-flex", alignItems: "baseline", gap: 4 }}>
            <span style={{ fontSize: 14, fontWeight: 800, color: c.ink, ...NUM }}>{v}</span>
            <span style={{ fontSize: 10, color: c.faint, fontWeight: 600 }}>{label}</span>
        </span>
    )
    const box = (kr: string, en: string, value: string, note: string, accent?: boolean) => (
        <div style={{ flex: 1, minWidth: 0, background: accent ? c.vtS : c.hi, borderRadius: 12, padding: "10px 11px", display: "flex", flexDirection: "column", gap: 3 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
                <span style={{ fontSize: 12, fontWeight: 800, color: c.ink }}>{kr}</span>
                <span style={{ fontSize: 9.5, color: c.faint }}>{en}</span>
            </div>
            <div style={{ fontSize: 24, fontWeight: 800, lineHeight: 1.05, color: accent ? c.vt : c.ink, ...NUM }}>{value}</div>
            <div style={{ fontSize: 9.5, color: c.faint, lineHeight: 1.35 }}>{note}</div>
        </div>
    )

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ ...CARD_TITLE, color: c.ink }}>한눈에 보기</span>
                <span style={{ fontSize: 10, color: c.faint }}>구조 · 규모</span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: c.faint, ...NUM }}>{(data.generated_at || "—").slice(0, 16).replace("T", " ")}</span>
            </div>

            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "6px 10px", background: c.hi, borderRadius: 12, padding: "9px 11px" }}>
                {stat(fmt(s.code_lines_tsx_py), "코드 줄")}
                {stat(fmt(s.python_modules), "Python")}
                {stat(fmt(s.tsx_components), "컴포넌트")}
                {stat(fmt(s.json_data_files), "발행 데이터")}
                {stat(fmt(s.git_tracked_files), "추적 파일")}
            </div>

            <div style={{ display: "flex", alignItems: "stretch", gap: 6 }}>
                {box("수집", "ingest", fmt(cnt("ingest")), "KIS · DART · FRED · sentiment")}
                <span style={{ display: "flex", alignItems: "center", color: c.faint, fontSize: 15, fontWeight: 700 }}>→</span>
                {box("두뇌", "brain", fmt(cnt("brain")), "api/intelligence", true)}
                <span style={{ display: "flex", alignItems: "center", color: c.faint, fontSize: 15, fontWeight: 700 }}>→</span>
                {box("출력", "surface", fmt(cnt("surface")), "오퍼레이터 · 공개 컴포넌트")}
            </div>

            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10, background: c.vtS, borderRadius: 12, padding: "8px 11px" }}>
                <span style={{ fontSize: 11.5, fontWeight: 800, color: c.vt }}>자동화 엔진</span>
                <span style={{ fontSize: 11, color: c.ink, textAlign: "right", ...NUM }}>
                    {fmt(cnt("automation"))} 워크플로
                    <span style={{ color: c.faint }}> · {scheduled} 스케줄 / {fmt(s.cron_triggers)} cron — 위 파이프라인 구동</span>
                </span>
            </div>

            <div style={{ display: "flex", gap: 6 }}>
                {box("데이터", "data", fmt(cnt("data")), "발행 JSON")}
                {box("검증", "validation", `N=${valN}`, valNext.label ? String(valNext.label) : "거래일", true)}
            </div>

            {stages.length > 0 ? (
                <div style={{ background: c.hi, borderRadius: 12, padding: "9px 11px" }}>
                    <div style={{ fontSize: 10.5, fontWeight: 800, color: c.faint, marginBottom: 6 }}>UNIVERSE FUNNEL</div>
                    {stages.map((st, i) => {
                        const w = Math.max(8, Math.round((Math.log(st + 1) / Math.log(maxStage + 1)) * 100))
                        return (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                                <span style={{ fontSize: 11, color: c.sub, width: 46, textAlign: "right", ...NUM }}>{fmt(st)}</span>
                                <div style={{ flex: 1, height: 12, background: c.track, borderRadius: 4, overflow: "hidden" }}>
                                    <div style={{ height: "100%", width: `${w}%`, background: c.vt, borderRadius: 4 }} />
                                </div>
                                <span style={{ fontSize: 10.5, color: c.faint, width: 52 }}>{labels[i] || ""}</span>
                            </div>
                        )
                    })}
                    {data.funnel?.status ? <div style={{ fontSize: 10.5, color: c.amber, marginTop: 6, lineHeight: 1.5 }}>{data.funnel.status}</div> : null}
                </div>
            ) : null}
        </div>
    )
}

export type { SystemMap, Palette }

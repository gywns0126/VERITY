"use client"
// BrainMonitorPanel — Brain 관측 (구 프레이머 `pages/admin/BrainMonitor.tsx` 이관, PM 2026-08-12).
// 6탭 = 개요(노드 토폴로지 + KPI + 알림 + TRUST) · 데이터 · 모델 · 드리프트 · 발행 신뢰도 · 사후분석.
// 소스 = `/api/admin?type=brain_health|data_health|explain|drift|trust` (authed) + portfolio 의 postmortem.
//
// 이관 시 바뀐 것 (되돌리지 말 것):
//   · 자체 auth 헤더 파싱(verity_supabase_session 직접 읽기) → `fetchOperator` 단일 소스.
//   · 자체 다크 토큰 → 오퍼레이터 팔레트.
//   · 🚨 토폴로지 = 좌표 계산 SVG(ResizeObserver + 39노드 zigzag + 엣지선) → **CSS 그리드 클러스터 뷰**.
//     정보는 보존한다(입력/엔진/출력 3열 · sub_cluster 묶음 · 노드별 health 색 · 클릭 상세).
//     버린 것 = 노드 간 엣지 선분. 엣지는 파이프라인 순서를 그리는데 그건 3열 배치가 이미 말해준다.
//   · 사후분석 = portfolio_full 재요청 대신 페이지가 소유한 슬림 payload 의 postmortem 을 prop 으로.
import { useCallback, useEffect, useState } from "react"
import { useDark, palette, cardStyle, CARD_TITLE, MAIN_PAD, FONT, NUM, type Palette } from "@/lib/theme"
import { fetchOperator } from "@/lib/api"
import type { Postmortem } from "@/lib/types"

type Tab = "overview" | "data" | "model" | "drift" | "trust" | "postmortem"
const TABS: Array<[Tab, string]> = [
    ["overview", "개요"],
    ["data", "데이터"],
    ["model", "모델"],
    ["drift", "드리프트"],
    ["trust", "발행 신뢰도"],
    ["postmortem", "과거 사후분석"],
]
const TYPE_OF: Partial<Record<Tab, string>> = {
    overview: "brain_health",
    data: "data_health",
    model: "explain",
    drift: "drift",
    trust: "trust",
}

type NodeT = {
    id: string
    cluster?: string
    sub_cluster?: string
    label?: string
    health?: string
    health_score?: number
    metric?: { primary_value?: number | string; primary_label?: string; yesterday_change?: number }
    detail?: { description?: string; related_data_health_keys?: string[] }
}
type Trust = {
    verdict?: string
    satisfied?: number
    total?: number
    conditions?: Record<string, boolean>
    details?: Record<string, string>
    blocking_reasons?: string[]
    recommendation?: string
}
const SUB_LABEL: Record<string, string> = {
    price: "PRICE", financial: "FINANCIAL", macro: "MACRO", news: "NEWS", ai: "AI / NOTIFY",
    fact_score: "FACT SCORE", signal: "SIGNAL", result: "RESULT",
}
const CLUSTER_ORDER: Array<[string, string, string[]]> = [
    ["input", "입력", ["price", "financial", "macro", "news", "ai"]],
    ["engine", "엔진", ["fact_score", "signal"]],
    ["output", "출력", ["result"]],
]

function healthColor(c: Palette, h?: string): string {
    if (h === "critical") return c.down
    if (h === "warning") return c.amber
    if (h === "ok" || h === "healthy") return c.green
    return c.faint
}
function num(v: unknown, d = 2): string {
    const x = Number(v)
    return isFinite(x) ? x.toFixed(d) : "—"
}

export default function BrainMonitorPanel({ postmortem }: { postmortem?: Postmortem }) {
    const dark = useDark()
    const c = palette(dark)
    const [tab, setTab] = useState<Tab>("overview")
    const [store, setStore] = useState<Partial<Record<Tab, Record<string, unknown>>>>({})
    const [err, setErr] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)
    const [picked, setPicked] = useState<NodeT | null>(null)

    const load = useCallback(
        async (t: Tab) => {
            const type = TYPE_OF[t]
            if (!type || store[t]) return
            setLoading(true)
            const r = await fetchOperator<Record<string, unknown>>(type)
            setLoading(false)
            if (r.ok) {
                setStore((s) => ({ ...s, [t]: r.data }))
                setErr(null)
            } else setErr(r.error === "auth" ? "오퍼레이터 로그인이 필요합니다" : `${type} — ${r.error === "http" ? "HTTP " + r.status : r.error}`)
        },
        [store]
    )

    useEffect(() => {
        load(tab)
    }, [tab, load])

    const wrap = { ...cardStyle(c, MAIN_PAD), fontFamily: FONT, display: "flex", flexDirection: "column" as const, gap: 11 }
    const d = (store[tab] || {}) as Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ ...CARD_TITLE, color: c.ink }}>Brain 관측</span>
                {loading ? <span style={{ fontSize: 10, color: c.faint }}>불러오는 중…</span> : null}
                {err ? <span style={{ fontSize: 10.5, color: c.down, fontWeight: 700 }}>{err}</span> : null}
                <span style={{ marginLeft: "auto", fontSize: 10, color: c.faint }}>Brain=가설 · 사실+과정 우선</span>
            </div>

            <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                {TABS.map(([k, label]) => (
                    <button
                        key={k}
                        onClick={() => setTab(k)}
                        style={{ border: "none", borderRadius: 999, padding: "4px 11px", fontSize: 10.5, fontWeight: 800, cursor: "pointer", fontFamily: FONT, background: tab === k ? c.vtS : c.hi, color: tab === k ? c.vt : c.faint }}
                    >
                        {label}
                    </button>
                ))}
            </div>

            {tab === "overview" ? <Overview c={c} d={d} picked={picked} setPicked={setPicked} /> : null}
            {tab === "data" ? <DataHealth c={c} rows={d.rows || []} /> : null}
            {tab === "model" ? <ModelHealth c={c} d={d} /> : null}
            {tab === "drift" ? <Drift c={c} d={d} /> : null}
            {tab === "trust" ? <TrustTab c={c} t={d as Trust} /> : null}
            {tab === "postmortem" ? <PostmortemTab c={c} p={postmortem} /> : null}
        </div>
    )
}

function Empty({ c, msg }: { c: Palette; msg: string }) {
    return <div style={{ fontSize: 11.5, color: c.faint, padding: "10px 2px" }}>{msg}</div>
}
function Section({ c, title, children }: { c: Palette; title: string; children: React.ReactNode }) {
    return (
        <div style={{ background: c.hi, borderRadius: 12, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 7 }}>
            <div style={{ fontSize: 10.5, fontWeight: 800, color: c.faint }}>{title}</div>
            {children}
        </div>
    )
}

function Overview({ c, d, picked, setPicked }: { c: Palette; d: Record<string, any>; picked: NodeT | null; setPicked: (n: NodeT | null) => void }) { // eslint-disable-line @typescript-eslint/no-explicit-any
    if (d.status === "no_observability_data") return <Empty c={c} msg={String(d.hint || "관측 데이터 누적 대기")} />
    const kpi = d.kpi || {}
    const nodes: NodeT[] = d.topology?.nodes || []
    const alerts: Array<{ message?: string }> = d.alerts || []
    const trust: Trust = d.trust || {}
    if (!nodes.length && !Object.keys(kpi).length) return <Empty c={c} msg="로딩 중…" />

    const groups: Record<string, NodeT[]> = {}
    nodes.forEach((n) => {
        const k = n.sub_cluster || n.cluster || "etc"
        if (!groups[k]) groups[k] = []
        groups[k].push(n)
    })

    const kpiBox = (label: string, value: unknown, unit = "", good?: number, warn?: number, reverse?: boolean) => {
        const v = Number(value)
        let col = c.ink
        if (isFinite(v) && good != null && warn != null) {
            const ok = reverse ? v <= good : v >= good
            const mid = reverse ? v <= warn : v >= warn
            col = ok ? c.green : mid ? c.amber : c.down
        }
        return (
            <div key={label} style={{ background: c.card, borderRadius: 10, padding: "8px 10px" }}>
                <div style={{ fontSize: 9.5, color: c.faint, fontWeight: 700 }}>{label}</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: col, ...NUM }}>
                    {value == null || value === "" ? "—" : String(value)}
                    <span style={{ fontSize: 10, color: c.faint, fontWeight: 700 }}>{unit}</span>
                </div>
            </div>
        )
    }

    return (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,3fr) minmax(0,2fr)", gap: 11, alignItems: "start" }}>
            <Section c={c} title={`Brain 노드 상태 — ${nodes.length}개`}>
                {nodes.length === 0 ? (
                    <Empty c={c} msg="토폴로지 없음" />
                ) : (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8 }}>
                        {CLUSTER_ORDER.map(([cluster, krLabel, subs]) => {
                            const present = subs.filter((s) => (groups[s] || []).length > 0)
                            if (!present.length) return null
                            return (
                                <div key={cluster} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                    <div style={{ fontSize: 10, fontWeight: 800, color: c.vt }}>{krLabel}</div>
                                    {present.map((s) => (
                                        <div key={s} style={{ background: c.card, borderRadius: 10, padding: "7px 8px" }}>
                                            <div style={{ fontSize: 9, color: c.faint, fontWeight: 700, marginBottom: 4 }}>{SUB_LABEL[s] || s.toUpperCase()}</div>
                                            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                                                {groups[s].map((n) => (
                                                    <button
                                                        key={n.id}
                                                        onClick={() => setPicked(n)}
                                                        title={n.label || n.id}
                                                        style={{
                                                            border: "none", cursor: "pointer", fontFamily: FONT,
                                                            borderRadius: 6, padding: "3px 6px", fontSize: 9.5, fontWeight: 700,
                                                            background: picked?.id === n.id ? c.vtS : c.hi,
                                                            color: c.sub, display: "inline-flex", alignItems: "center", gap: 4,
                                                            maxWidth: "100%", overflow: "hidden",
                                                        }}
                                                    >
                                                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: healthColor(c, n.health), flexShrink: 0 }} />
                                                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{n.label || n.id}</span>
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )
                        })}
                    </div>
                )}
                {picked ? (
                    <div style={{ background: c.card, borderRadius: 10, padding: "9px 11px", display: "flex", flexDirection: "column", gap: 4 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                            <span style={{ width: 7, height: 7, borderRadius: "50%", background: healthColor(c, picked.health) }} />
                            <span style={{ fontSize: 12, fontWeight: 800, color: c.ink }}>{picked.label || picked.id}</span>
                            <button onClick={() => setPicked(null)} style={{ marginLeft: "auto", border: "none", background: c.hi, color: c.faint, borderRadius: 999, padding: "3px 9px", fontSize: 10, fontWeight: 800, cursor: "pointer", fontFamily: FONT }}>닫기</button>
                        </div>
                        {picked.metric?.primary_label ? (
                            <div style={{ fontSize: 11, color: c.sub, ...NUM }}>
                                {picked.metric.primary_label} <b style={{ color: c.ink }}>{String(picked.metric.primary_value ?? "—")}</b>
                                {typeof picked.metric.yesterday_change === "number" ? (
                                    <span style={{ color: picked.metric.yesterday_change >= 0 ? c.up : c.down }}> ({picked.metric.yesterday_change >= 0 ? "+" : ""}{picked.metric.yesterday_change})</span>
                                ) : null}
                            </div>
                        ) : null}
                        {picked.detail?.description ? <div style={{ fontSize: 11, color: c.sub, lineHeight: 1.5 }}>{picked.detail.description}</div> : null}
                        {typeof picked.health_score === "number" ? <div style={{ fontSize: 10, color: c.faint, ...NUM }}>health score {picked.health_score}</div> : null}
                    </div>
                ) : null}
            </Section>

            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                <Section c={c} title="KPI">
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                        {kpiBox("Brain Health", kpi.brain_health_score, "", 80, 50)}
                        {kpiBox("Freshness", kpi.data_freshness_minutes, "분", 30, 120, true)}
                        {kpiBox("Drift", isFinite(Number(kpi.drift_score)) ? num(kpi.drift_score, 3) : null)}
                        {kpiBox("Confidence", kpi.confidence)}
                    </div>
                </Section>
                <Section c={c} title="알림 (최근 24h)">
                    {alerts.length === 0 ? <Empty c={c} msg="알림 없음" /> : alerts.map((a, i) => <div key={i} style={{ fontSize: 11, color: c.sub, lineHeight: 1.5 }}>· {a.message || JSON.stringify(a)}</div>)}
                </Section>
                <Section c={c} title="TRUST — 오늘 발행 가능?">
                    <Verdict c={c} t={trust} />
                </Section>
            </div>
        </div>
    )
}

function Verdict({ c, t }: { c: Palette; t: Trust }) {
    const v = String(t.verdict || "—")
    const col = /go|pass|ok/i.test(v) ? c.green : /block|no|fail/i.test(v) ? c.down : c.amber
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: col }}>{v}</span>
                <span style={{ fontSize: 11, color: c.faint, ...NUM }}>{t.satisfied ?? "—"}/{t.total ?? "—"} 조건</span>
            </div>
            {(t.blocking_reasons || []).map((r, i) => <div key={i} style={{ fontSize: 10.5, color: c.down, fontWeight: 700 }}>· {r}</div>)}
            {t.recommendation ? <div style={{ fontSize: 11, color: c.sub, lineHeight: 1.5 }}>{t.recommendation}</div> : null}
        </div>
    )
}

function DataHealth({ c, rows }: { c: Palette; rows: Array<Record<string, any>> }) { // eslint-disable-line @typescript-eslint/no-explicit-any
    if (!rows.length) return <Empty c={c} msg="데이터 없음 — 첫 cron 후 표시" />
    const th = { padding: "6px 8px", textAlign: "left" as const, fontWeight: 700, fontSize: 9.5, color: c.faint, whiteSpace: "nowrap" as const }
    const td = { padding: "5px 8px", fontSize: 11, color: c.ink, whiteSpace: "nowrap" as const }
    return (
        <Section c={c} title={`데이터 소스 상태 — ${rows.length}개`}>
            <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                        <tr>
                            <th style={th}>소스</th><th style={th}>상태</th>
                            <th style={{ ...th, textAlign: "right" }}>신선도</th>
                            <th style={{ ...th, textAlign: "right" }}>결측률</th>
                            <th style={{ ...th, textAlign: "right" }}>지연(ms)</th>
                            <th style={{ ...th, textAlign: "right" }}>7일 성공/실패</th>
                            <th style={th}>비고</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((r, i) => (
                            <tr key={i}>
                                <td style={{ ...td, fontWeight: 800 }}>{r.source}</td>
                                <td style={td}>
                                    <span style={{ width: 7, height: 7, borderRadius: "50%", background: healthColor(c, r.status), display: "inline-block", marginRight: 5 }} />
                                    {r.status || "—"}
                                </td>
                                <td style={{ ...td, textAlign: "right", ...NUM }}>{r.freshness_minutes != null ? `${r.freshness_minutes}분` : "—"}</td>
                                <td style={{ ...td, textAlign: "right", ...NUM }}>{r.missing_pct != null ? `${(Number(r.missing_pct) * 100).toFixed(1)}%` : "—"}</td>
                                <td style={{ ...td, textAlign: "right", ...NUM }}>{r.latency_ms_p50 || "—"}</td>
                                <td style={{ ...td, textAlign: "right", ...NUM }}>{r.success_count_7d || 0}/{r.failure_count_7d || 0}</td>
                                <td style={{ ...td, color: c.faint, fontSize: 10.5, whiteSpace: "normal" }}>{String(r.detail || "").slice(0, 60)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </Section>
    )
}

function ModelHealth({ c, d }: { c: Palette; d: Record<string, any> }) { // eslint-disable-line @typescript-eslint/no-explicit-any
    const hist: Array<{ bin?: string; count?: number }> = d.brain_score_histogram || []
    const grade: Record<string, { count?: number }> = d.grade_distribution || {}
    const hr = d.hit_rate || {}
    const ai = d.ai_disagreements || {}
    if (!hist.length && !Object.keys(grade).length) return <Empty c={c} msg="로딩 중…" />
    const maxBin = Math.max(1, ...hist.map((h) => h.count || 0))
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
            <Section c={c} title="Brain Score 분포 (오늘)">
                <div style={{ display: "flex", alignItems: "flex-end", height: 110, gap: 4 }}>
                    {hist.map((h, i) => (
                        <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                            <div style={{ width: "100%", height: `${((h.count || 0) / maxBin) * 100}%`, background: (h.count || 0) === maxBin ? c.vt : c.track, borderRadius: 4, minHeight: 2 }} />
                            <span style={{ fontSize: 8.5, color: c.faint, ...NUM }}>{h.bin}</span>
                        </div>
                    ))}
                </div>
            </Section>
            <Section c={c} title="등급 분포">
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                    {Object.entries(grade).map(([g, v]) => (
                        <span key={g} style={{ fontSize: 11, color: c.faint }}>{g} <b style={{ color: c.ink, ...NUM }}>{v?.count ?? 0}</b></span>
                    ))}
                </div>
            </Section>
            <Section c={c} title="적중 · AI 일치">
                <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11, color: c.faint }}>
                    <span>매수 적중률 <b style={{ color: c.ink, ...NUM }}>{hr.buy_hit_rate != null ? `${num(hr.buy_hit_rate, 1)}%` : "—"}</b></span>
                    <span>회피 평균수익 <b style={{ color: c.ink, ...NUM }}>{hr.avoid_avg_return != null ? `${num(hr.avoid_avg_return, 2)}%` : "—"}</b></span>
                    <span>brain quality <b style={{ color: c.ink, ...NUM }}>{hr.brain_quality_score ?? "—"}</b></span>
                    <span>AI 일치율 <b style={{ color: c.ink, ...NUM }}>{ai.agreement_rate != null ? `${num(ai.agreement_rate, 1)}%` : "—"}</b></span>
                    <span>비교 <b style={{ color: c.ink, ...NUM }}>{ai.total_compared ?? "—"}</b></span>
                </div>
                <div style={{ fontSize: 10, color: c.faint }}>적중률 단독 판단 금지 — 표본·기대값과 함께 볼 것</div>
            </Section>
        </div>
    )
}

function Drift({ c, d }: { c: Palette; d: Record<string, any> }) { // eslint-disable-line @typescript-eslint/no-explicit-any
    const bars: Array<{ feature?: string; psi?: number; level?: string }> = d.feature_psi_bars || []
    if (!bars.length) return <Empty c={c} msg="drift 데이터 없음" />
    return (
        <Section c={c} title={`입력 Feature Drift — PSI (level: ${d.level || "—"})`}>
            {bars.map((b, i) => {
                const pct = Math.min(((b.psi || 0) / 0.5) * 100, 100)
                const col = b.level === "critical" ? c.down : b.level === "warning" ? c.amber : c.green
                return (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 10.5, color: c.sub, width: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{b.feature}</span>
                        <div style={{ flex: 1, height: 10, background: c.track, borderRadius: 4, overflow: "hidden" }}>
                            <div style={{ height: "100%", width: `${pct}%`, background: col, borderRadius: 4 }} />
                        </div>
                        <span style={{ fontSize: 10.5, color: col, fontWeight: 800, width: 46, textAlign: "right", ...NUM }}>{num(b.psi, 3)}</span>
                    </div>
                )
            })}
            {d.explanation?.summary ? <div style={{ fontSize: 11, color: c.sub, lineHeight: 1.5 }}>{String(d.explanation.summary)}</div> : null}
        </Section>
    )
}

const TRUST_LABELS: Array<[string, string]> = [
    ["data_freshness_ok", "데이터 신선도 < 30분"],
    ["core_sources_ok", "핵심 소스 모두 성공"],
    ["drift_below_threshold", "Drift score < 0.3"],
    ["ai_models_ok", "AI 모델 응답 정상"],
    ["brain_distribution_normal", "Brain Score 분포 정상"],
    ["pipeline_cron_ok", "파이프라인 cron 성공"],
    ["deadman_clear", "Deadman Switch 미발동"],
    ["pdf_generator_ok", "PDF 생성기 정상"],
]

function TrustTab({ c, t }: { c: Palette; t: Trust }) {
    if (!t || !Object.keys(t).length) return <Empty c={c} msg="로딩 중…" />
    const conditions = t.conditions || {}
    const details = t.details || {}
    return (
        <Section c={c} title="오늘 리포트 발행 신뢰도">
            <Verdict c={c} t={t} />
            <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 4 }}>
                {TRUST_LABELS.map(([k, label]) => {
                    const ok = conditions[k]
                    return (
                        <div key={k} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11 }}>
                            <span style={{ width: 6, height: 6, borderRadius: "50%", background: ok === true ? c.green : ok === false ? c.down : c.faint, flexShrink: 0 }} />
                            <span style={{ color: c.sub }}>{label}</span>
                            {details[k] ? <span style={{ color: c.faint, fontSize: 10 }}>· {details[k]}</span> : null}
                        </div>
                    )
                })}
            </div>
        </Section>
    )
}

function PostmortemTab({ c, p }: { c: Palette; p?: Postmortem }) {
    if (!p) return <Empty c={c} msg="과거 사후분석 없음 — 생성 경로는 종료됨" />
    const failures = p.failures || []
    const ml = Object.entries(p.misleading_factors || {})
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
            <div style={{ fontSize: 10.5, color: c.amber, fontWeight: 800 }}>
                과거 기록 · 갱신 종료 — 현재 판단 근거로 사용하지 않음
            </div>
            <Section c={c} title={`과거 사후분석 ${p.period ? `· ${p.period}` : ""}`}>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 11, color: c.faint }}>
                    <span>분석 <b style={{ color: c.ink, ...NUM }}>{p.analyzed_count ?? "—"}</b></span>
                    <span>커버리지 <b style={{ color: c.ink, ...NUM }}>{p.coverage_ratio != null ? `${num(Number(p.coverage_ratio) * 100, 0)}%` : "—"}</b></span>
                    {p.quality_label ? <span>품질 <b style={{ color: c.ink }}>{p.quality_label}</b></span> : null}
                    {p.trail_sufficient === false ? <span style={{ color: c.amber, fontWeight: 700 }}>표본 부족 — 결론 유보</span> : null}
                </div>
                {p.summary ? <div style={{ fontSize: 11.5, color: c.sub, lineHeight: 1.5 }}>{p.summary}</div> : null}
                {p.lesson ? <div style={{ fontSize: 11.5, color: c.ink, lineHeight: 1.5 }}><b>교훈</b> {p.lesson}</div> : null}
                {p.system_suggestion ? <div style={{ fontSize: 11.5, color: c.vt, lineHeight: 1.5 }}><b>시스템 제안</b> {p.system_suggestion}</div> : null}
            </Section>
            {ml.length ? (
                <Section c={c} title="오도 요인">
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 11, color: c.faint }}>
                        {ml.map(([k, v]) => <span key={k}>{k} <b style={{ color: c.ink, ...NUM }}>{String(v)}</b></span>)}
                    </div>
                </Section>
            ) : null}
            {failures.length ? (
                <Section c={c} title={`실패 사례 ${failures.length}건`}>
                    {failures.slice(0, 12).map((f, i) => (
                        <div key={i} style={{ borderTop: i === 0 ? "none" : `1px solid ${c.line}`, paddingTop: i === 0 ? 0 : 7, marginTop: i === 0 ? 0 : 7 }}>
                            <div style={{ display: "flex", gap: 7, alignItems: "baseline", flexWrap: "wrap" }}>
                                <span style={{ fontSize: 11.5, fontWeight: 800, color: c.ink }}>{f.name || f.ticker}</span>
                                <span style={{ fontSize: 10, color: c.faint, ...NUM }}>{f.ticker}</span>
                                {f.original_rec ? <span style={{ fontSize: 10, color: c.faint }}>{f.original_rec}</span> : null}
                                {typeof f.actual_return === "number" ? (
                                    <span style={{ fontSize: 11, fontWeight: 800, ...NUM, color: f.actual_return >= 0 ? c.up : c.down }}>{f.actual_return >= 0 ? "+" : ""}{f.actual_return.toFixed(2)}%</span>
                                ) : null}
                                {f.brain_grade ? <span style={{ fontSize: 10, color: c.vt, background: c.vtS, borderRadius: 5, padding: "1px 6px" }}>{f.brain_grade}</span> : null}
                            </div>
                            {f.lesson ? <div style={{ fontSize: 11, color: c.sub, lineHeight: 1.45, marginTop: 2 }}>{f.lesson}</div> : null}
                        </div>
                    ))}
                    {failures.length > 12 ? <div style={{ fontSize: 10.5, color: c.faint }}>+{failures.length - 12}건 더</div> : null}
                </Section>
            ) : null}
        </div>
    )
}

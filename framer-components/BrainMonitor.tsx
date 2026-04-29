import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useRef, useState } from "react"

/**
 * VERITY Brain Observatory — 관리자 전용 모니터링 대시보드
 * 단일 Framer 코드 컴포넌트 (iframe 우회). Sandbox 호환:
 *   - 무거운 애니메이션 X (Three.js / requestAnimationFrame loop 폐기)
 *   - 5분 setInterval polling
 *   - SVG 2D 토폴로지
 * 인증: props.adminToken → X-Admin-Token 헤더
 * API:  props.apiBaseUrl + "/api/admin?type=brain_health|data_health|drift|trust|explain"
 */

// ── 디자인 토큰 (인라인 — _shared-patterns 마스터 톤) ──
const C = {
    bgPage: "#0E0F11",
    bgCard: "#171820",
    bgElevated: "#22232B",
    border: "#23242C",
    borderStrong: "#34353D",
    textPrimary: "#F2F3F5",
    textSecondary: "#A8ABB2",
    textTertiary: "#6B6E76",
    accent: "#B5FF19",
    accentSoft: "rgba(181,255,25,0.12)",
    info: "#5BA9FF",
    success: "#22C55E",
    warn: "#F59E0B",
    danger: "#EF4444",
    clusterInput: "#5BA9FF",
    clusterEngine: "#A78BFA",
    clusterOutput: "#B5ff19",
}
const T = { cap: 11, body: 13, sub: 15, title: 17, h2: 22 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 4, md: 6, lg: 10 }

const HEALTH_HEX: Record<string, string> = {
    ok: C.success, warning: C.warn, critical: C.danger, unknown: C.textTertiary,
}
const CLUSTER_HEX: Record<string, string> = {
    input: C.clusterInput, engine: C.clusterEngine, output: C.clusterOutput,
}
const PROBLEM_SET = new Set(["warning", "critical"])

type Tab = "overview" | "data" | "model" | "drift" | "trust"
type NodeT = {
    id: string; cluster: string; sub_cluster?: string;
    label: string; health: string; health_score?: number;
    metric?: { primary_value?: number | string; primary_label?: string; yesterday_change?: number };
    detail?: { description?: string; related_data_health_keys?: string[] };
}
type EdgeT = { from: string; to: string; strength?: number; health: string }
type Topology = { nodes: NodeT[]; edges: EdgeT[] }
type Trust = {
    verdict?: string; satisfied?: number; total?: number;
    conditions?: Record<string, boolean>;
    details?: Record<string, string>;
    blocking_reasons?: string[];
    recommendation?: string;
}

interface Props {
    apiBaseUrl: string
    adminToken: string
    pollSec: number
}

export default function BrainMonitor(props: Props) {
    const { apiBaseUrl, adminToken, pollSec } = props
    const [tab, setTab] = useState<Tab>("overview")
    const [authError, setAuthError] = useState<string | null>(null)
    const [overview, setOverview] = useState<any>(null)
    const [dataHealth, setDataHealth] = useState<any>(null)
    const [model, setModel] = useState<any>(null)
    const [drift, setDrift] = useState<any>(null)
    const [trust, setTrust] = useState<any>(null)
    const [selected, setSelected] = useState<NodeT | null>(null)
    const [hovered, setHovered] = useState<NodeT | null>(null)
    const [refreshing, setRefreshing] = useState(false)

    const fetchTab = React.useCallback(async (kind: string) => {
        try {
            const r = await fetch(`${apiBaseUrl}/api/admin?type=${kind}`, {
                headers: adminToken ? { "X-Admin-Token": adminToken } : {},
            })
            if (r.status === 401) { setAuthError("인증 실패 — adminToken 확인"); return null }
            if (!r.ok) { setAuthError(`HTTP ${r.status}`); return null }
            setAuthError(null)
            return await r.json()
        } catch (e: any) {
            setAuthError(`network: ${e.message}`)
            return null
        }
    }, [apiBaseUrl, adminToken])

    const refresh = React.useCallback(async () => {
        setRefreshing(true)
        try {
            if (tab === "overview") setOverview(await fetchTab("brain_health"))
            else if (tab === "data") setDataHealth(await fetchTab("data_health"))
            else if (tab === "model") setModel(await fetchTab("explain"))
            else if (tab === "drift") setDrift(await fetchTab("drift"))
            else if (tab === "trust") setTrust(await fetchTab("trust"))
        } finally {
            setRefreshing(false)
        }
    }, [tab, fetchTab])

    useEffect(() => {
        refresh()
        const interval = Math.max(60, pollSec || 300) * 1000
        const h = window.setInterval(refresh, interval)
        return () => window.clearInterval(h)
    }, [refresh, pollSec])

    // 메인 layout
    return (
        <div style={{
            background: C.bgPage, color: C.textPrimary,
            fontFamily: '-apple-system, BlinkMacSystemFont, "Noto Sans KR", sans-serif',
            fontSize: T.body, width: "100%", height: "100%", overflow: "auto",
            display: "flex", flexDirection: "column",
        }}>
            <Header authError={authError} checkedAt={overview?.checked_at}
                    onRefresh={refresh} refreshing={refreshing} />
            <Tabs current={tab} onChange={setTab} />
            <main style={{ padding: S.lg, flex: 1 }}>
                {tab === "overview" && <OverviewTab data={overview}
                    selected={selected} setSelected={setSelected}
                    hovered={hovered} setHovered={setHovered} />}
                {tab === "data" && <DataHealthTab data={dataHealth} />}
                {tab === "model" && <ModelHealthTab data={model} />}
                {tab === "drift" && <DriftTab data={drift} />}
                {tab === "trust" && <ReportReadinessTab data={trust} />}
            </main>
        </div>
    )
}

// ──────────────────────────────────────────────────────────────
// Header / Tabs
// ──────────────────────────────────────────────────────────────

function Header({ authError, checkedAt, onRefresh, refreshing }: {
    authError: string | null; checkedAt?: string;
    onRefresh: () => void; refreshing: boolean;
}) {
    return (
        <header style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: `${S.md}px ${S.lg}px`, background: C.bgCard,
            borderBottom: `1px solid ${C.border}`,
        }}>
            <div style={{
                fontSize: T.title, fontWeight: 600, color: C.accent,
                letterSpacing: "0.04em",
            }}>VERITY BRAIN OBSERVATORY</div>
            <div style={{ display: "flex", gap: S.md, alignItems: "center", fontSize: T.cap, color: C.textSecondary }}>
                {checkedAt && <span style={{ fontFamily: "monospace" }}>{checkedAt.replace("T", " ").slice(0, 19)}</span>}
                {authError && <span style={{ color: C.danger }}>{authError}</span>}
                <button
                    onClick={onRefresh}
                    disabled={refreshing}
                    title="현재 탭 데이터 새로고침"
                    style={{
                        background: refreshing ? C.bgElevated : "transparent",
                        color: refreshing ? C.textTertiary : C.accent,
                        border: `1px solid ${C.borderStrong}`,
                        borderRadius: R.sm, padding: `${S.xs}px ${S.md}px`,
                        cursor: refreshing ? "not-allowed" : "pointer",
                        fontSize: T.cap, fontWeight: 500,
                        display: "inline-flex", alignItems: "center", gap: S.xs,
                    }}
                >
                    <span style={{
                        display: "inline-block",
                        animation: refreshing ? "spin 1s linear infinite" : "none",
                    }}>↻</span>
                    {refreshing ? "갱신 중..." : "새로고침"}
                </button>
                <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
            </div>
        </header>
    )
}

function Tabs({ current, onChange }: { current: Tab; onChange: (t: Tab) => void }) {
    const items: { id: Tab; label: string }[] = [
        { id: "overview", label: "Overview" },
        { id: "data", label: "Data Health" },
        { id: "model", label: "Model Health" },
        { id: "drift", label: "Drift" },
        { id: "trust", label: "Report Readiness" },
    ]
    return (
        <div style={{
            display: "flex", padding: `0 ${S.lg}px`, background: C.bgCard,
            borderBottom: `1px solid ${C.border}`, overflowX: "auto",
        }}>
            {items.map(it => {
                const active = it.id === current
                return (
                    <div key={it.id} onClick={() => onChange(it.id)} style={{
                        padding: `${S.md}px ${S.lg}px`, cursor: "pointer",
                        color: active ? C.accent : C.textSecondary,
                        borderBottom: `2px solid ${active ? C.accent : "transparent"}`,
                        fontWeight: 500, flexShrink: 0,
                    }}>{it.label}</div>
                )
            })}
        </div>
    )
}

// ──────────────────────────────────────────────────────────────
// Overview Tab — KPI + SVG Topology + Trust + Alerts
// ──────────────────────────────────────────────────────────────

function OverviewTab({ data, selected, setSelected, hovered, setHovered }: any) {
    if (!data) return <Empty msg="로딩 중..." />
    if (data.status === "no_observability_data") return <Empty msg={data.hint || "데이터 누적 대기"} />

    const kpi = data.kpi || {}
    const trust = data.trust || {}
    const alerts = data.alerts || []

    return (
        <div style={{
            display: "grid", gridTemplateColumns: "minmax(0,3fr) minmax(0,2fr)",
            gap: S.lg,
        }}>
            {/* 좌: 토폴로지 */}
            <Panel title="Brain — 노드 상태">
                <Topology2D topo={data.topology}
                    selected={selected} setSelected={setSelected}
                    hovered={hovered} setHovered={setHovered} />
                {selected && <NodeDetailCard node={selected} onClose={() => setSelected(null)} />}
            </Panel>

            {/* 우: KPI + Alert + Trust */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: S.sm }}>
                    <Kpi label="Brain Health" value={kpi.brain_health_score} unit="" thresholdGood={80} thresholdWarn={50} />
                    <Kpi label="Freshness" value={kpi.data_freshness_minutes} unit="분" thresholdGood={30} thresholdWarn={120} reverse />
                    <Kpi label="Drift" value={fmtNum(kpi.drift_score)} unit="" />
                    <Kpi label="Confidence" value={kpi.confidence} unit="" />
                </div>
                <Panel title={`알림 (최근 24h)`}>
                    {alerts.length === 0
                        ? <Empty msg="알림 없음" small />
                        : <div>{alerts.map((a: any, i: number) => (
                            <div key={i} style={{ padding: S.sm, borderBottom: `1px solid ${C.border}`, fontSize: T.cap }}>
                                {a.message || JSON.stringify(a)}
                            </div>
                        ))}</div>}
                </Panel>
                <Panel title="TRUST — 오늘 발행 가능?">
                    <TrustVerdict trust={trust} />
                </Panel>
            </div>
        </div>
    )
}

// ──────────────────────────────────────────────────────────────
// 2D Topology — 39 노드 zigzag, 호버 강조
// ──────────────────────────────────────────────────────────────

// sub_cluster 별 vertical 슬롯 정의 (위→아래 순서)
const SUB_CLUSTER_LAYOUT: Record<string, { cluster: string; label: string; cols: number }> = {
    // input 5 그룹
    price: { cluster: "input", label: "PRICE", cols: 3 },
    financial: { cluster: "input", label: "FINANCIAL", cols: 3 },
    macro: { cluster: "input", label: "MACRO", cols: 3 },
    news: { cluster: "input", label: "NEWS", cols: 2 },
    ai: { cluster: "input", label: "AI / NOTIFY", cols: 2 },
    // engine 2 그룹
    fact_score: { cluster: "engine", label: "FACT SCORE (13)", cols: 4 },
    signal: { cluster: "engine", label: "SIGNAL", cols: 4 },
    // output 1 그룹
    result: { cluster: "output", label: "RESULT", cols: 1 },
}

function Topology2D({ topo, selected, setSelected, hovered, setHovered }: any) {
    const wrapRef = useRef<HTMLDivElement>(null)
    const [width, setWidth] = useState(900)
    const HEIGHT = 600
    useEffect(() => {
        if (!wrapRef.current) return
        const ro = new ResizeObserver(entries => {
            for (const e of entries) setWidth(Math.max(360, e.contentRect.width))
        })
        ro.observe(wrapRef.current)
        return () => ro.disconnect()
    }, [])

    // sub_cluster 별 박스 좌표 + 노드 grid 좌표
    const layout = useMemo(() => {
        const out: {
            positions: Record<string, { x: number; y: number }>;
            boxes: Array<{ subId: string; cluster: string; label: string; x: number; y: number; w: number; h: number; nodes: NodeT[] }>;
        } = { positions: {}, boxes: [] }
        if (!topo?.nodes) return out
        const W = width, H = HEIGHT
        const COL_W = W / 3
        const PADX = 12, PADY = 36, GAP = 8
        const HEADER_H = 18
        const NODE_R = 6

        // sub_cluster 별 노드 모음
        const groups: Record<string, NodeT[]> = {}
        topo.nodes.forEach((n: NodeT) => {
            const sub = n.sub_cluster || n.cluster || "etc"
            if (!groups[sub]) groups[sub] = []
            groups[sub].push(n)
        })

        // 각 cluster 의 sub_cluster 들을 순서대로 vertical stack
        const clusterOrder: Record<string, string[]> = {
            input: ["price", "financial", "macro", "news", "ai"],
            engine: ["fact_score", "signal"],
            output: ["result"],
        }
        const clusterX: Record<string, number> = {
            input: PADX,
            engine: COL_W + PADX,
            output: 2 * COL_W + PADX,
        }
        const colWidth = COL_W - PADX * 2

        Object.keys(clusterOrder).forEach(cluster => {
            const subs = clusterOrder[cluster]
            // 각 sub 의 nodes 수에 비례하는 height 계산
            const subHeights = subs.map(sub => {
                const ns = groups[sub] || []
                const cols = SUB_CLUSTER_LAYOUT[sub]?.cols || 3
                const rows = Math.ceil(ns.length / cols)
                return HEADER_H + rows * 30 + 16  // 노드 1줄 = 30px
            })
            const totalH = subHeights.reduce((a, b) => a + b, 0) + (subs.length - 1) * GAP
            const startY = (H - totalH) / 2

            let curY = startY
            subs.forEach((sub, idx) => {
                const ns = groups[sub] || []
                const cfg = SUB_CLUSTER_LAYOUT[sub]
                if (!cfg) return
                const boxH = subHeights[idx]
                const boxX = clusterX[cluster]
                const boxY = curY
                const boxW = colWidth
                out.boxes.push({
                    subId: sub, cluster, label: cfg.label,
                    x: boxX, y: boxY, w: boxW, h: boxH, nodes: ns,
                })
                // 노드를 grid 로 배치
                const cols = cfg.cols
                const cellW = boxW / cols
                const innerY = boxY + HEADER_H + 14
                ns.forEach((n, i) => {
                    const col = i % cols
                    const row = Math.floor(i / cols)
                    out.positions[n.id] = {
                        x: boxX + cellW * (col + 0.5),
                        y: innerY + row * 30,
                    }
                })
                curY += boxH + GAP
            })
        })

        return out
    }, [topo, width])

    const adjacency = useMemo(() => {
        const adj = new Map<string, Set<string>>()
        if (!topo?.edges) return adj
        topo.edges.forEach((e: EdgeT) => {
            if (!adj.has(e.from)) adj.set(e.from, new Set())
            if (!adj.has(e.to)) adj.set(e.to, new Set())
            adj.get(e.from)!.add(e.to)
            adj.get(e.to)!.add(e.from)
        })
        return adj
    }, [topo])

    if (!topo?.nodes) return <Empty msg="topology 데이터 없음" />

    const active = hovered || selected
    const activeNeighbors: Set<string> = active
        ? new Set([active.id, ...(adjacency.get(active.id) || [])])
        : new Set()

    // sub_cluster 별 health 요약
    const subHealthSummary = (nodes: NodeT[]) => {
        const c = { ok: 0, warning: 0, critical: 0, unknown: 0 }
        nodes.forEach(n => { (c as any)[n.health || "unknown"]++ })
        return c
    }

    return (
        <div ref={wrapRef} style={{ position: "relative", width: "100%" }}>
            <svg width={width} height={HEIGHT} style={{ display: "block" }}>
                {/* sub_cluster 박스 (배경) */}
                {layout.boxes.map(b => {
                    const sum = subHealthSummary(b.nodes)
                    const hasProblem = sum.warning + sum.critical > 0
                    return (
                        <g key={b.subId}>
                            <rect
                                x={b.x} y={b.y} width={b.w} height={b.h}
                                fill={C.bgCard}
                                stroke={hasProblem ? HEALTH_HEX[sum.critical > 0 ? "critical" : "warning"] : C.border}
                                strokeWidth={hasProblem ? 1.2 : 0.8}
                                strokeOpacity={hasProblem ? 0.8 : 0.5}
                                rx={4}
                            />
                            {/* sub_cluster header: 라벨 + cluster 색 도트 + health 카운트 */}
                            <text x={b.x + 8} y={b.y + 13}
                                fill={CLUSTER_HEX[b.cluster]}
                                fontSize={10} fontWeight={600}
                                style={{ letterSpacing: "0.06em" }}>
                                {b.label}
                            </text>
                            <text x={b.x + b.w - 8} y={b.y + 13}
                                fill={C.textTertiary}
                                fontSize={9} textAnchor="end">
                                {sum.ok}/{b.nodes.length}{hasProblem ? `  ⚠ ${sum.warning + sum.critical}` : ""}
                            </text>
                        </g>
                    )
                })}

                {/* Edges */}
                {(topo.edges || []).map((e: EdgeT, i: number) => {
                    const f = layout.positions[e.from]
                    const t = layout.positions[e.to]
                    if (!f || !t) return null
                    const isProblem = PROBLEM_SET.has(e.health)
                    const isActiveEdge = active && (e.from === active.id || e.to === active.id)
                    const stroke = isActiveEdge
                        ? CLUSTER_HEX[active.cluster]
                        : (isProblem ? HEALTH_HEX[e.health] : C.borderStrong)
                    const opacity = isActiveEdge ? 0.95
                        : (active ? 0.03 : (isProblem ? 0.5 : 0.10))
                    const sw = isActiveEdge ? 1.4 : Math.max(0.3, (e.strength || 0.5) * 0.7)
                    return <line key={i}
                        x1={f.x} y1={f.y} x2={t.x} y2={t.y}
                        stroke={stroke} strokeOpacity={opacity} strokeWidth={sw} />
                })}

                {/* Nodes — 항상 라벨 표시 (작게) */}
                {(topo.nodes || []).map((n: NodeT) => {
                    const p = layout.positions[n.id]
                    if (!p) return null
                    const isProblem = PROBLEM_SET.has(n.health)
                    const isOn = active ? activeNeighbors.has(n.id) : true
                    const r = isProblem ? 5 : 4
                    const fill = isProblem
                        ? HEALTH_HEX[n.health]
                        : (active && n.id === active.id ? CLUSTER_HEX[n.cluster]
                            : (active && isOn ? CLUSTER_HEX[n.cluster] : C.textTertiary))
                    const opacity = active ? (isOn ? 1 : 0.18) : 1

                    return (
                        <g key={n.id} transform={`translate(${p.x}, ${p.y})`}
                            style={{ cursor: "pointer" }}
                            onClick={() => setSelected(n)}
                            onMouseEnter={() => setHovered(n)}
                            onMouseLeave={() => setHovered(null)}>
                            <circle r={r} fill={fill} fillOpacity={opacity}
                                stroke={active && n.id === active.id ? C.accent : "transparent"}
                                strokeWidth={1.5} />
                            {/* 라벨 항상 표시 — 노드 아래 */}
                            <text x={0} y={r + 9} textAnchor="middle"
                                fill={isProblem ? HEALTH_HEX[n.health]
                                    : (active && isOn ? C.textPrimary : C.textTertiary)}
                                fontSize={9}
                                fontWeight={isProblem ? 600 : 400}
                                opacity={opacity}
                                style={{ pointerEvents: "none" }}>
                                {n.label.length > 12 ? n.label.slice(0, 11) + "…" : n.label}
                            </text>
                        </g>
                    )
                })}
            </svg>

            {/* 범례 + 힌트 */}
            <div style={{
                display: "flex", gap: S.md, fontSize: T.cap, color: C.textTertiary,
                paddingTop: S.sm, alignItems: "center", flexWrap: "wrap",
            }}>
                <Legend color={C.clusterInput} label="Input" />
                <Legend color={C.clusterEngine} label="Engine" />
                <Legend color={C.clusterOutput} label="Output" />
                <span style={{ marginLeft: S.lg, color: C.warn }}>● warning</span>
                <span style={{ color: C.danger }}>● critical</span>
                <span style={{ marginLeft: "auto" }}>호버=흐름 강조 / 클릭=세부 / 문제 자동 강조</span>
            </div>
        </div>
    )
}

function Legend({ color, label }: { color: string; label: string }) {
    return (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
            {label}
        </span>
    )
}

// ──────────────────────────────────────────────────────────────
// 공통 컴포넌트 (Panel / Kpi / TrustVerdict / NodeDetail / Empty)
// ──────────────────────────────────────────────────────────────

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            padding: S.md, borderRadius: R.sm,
        }}>
            <div style={{
                fontSize: T.cap, color: C.textTertiary, textTransform: "uppercase",
                letterSpacing: "0.06em", marginBottom: S.sm,
            }}>{title}</div>
            {children}
        </div>
    )
}

function Kpi({ label, value, unit, thresholdGood, thresholdWarn, reverse }: any) {
    let color = C.textPrimary
    if (typeof value === "number" && thresholdGood !== undefined) {
        const okCond = reverse ? value < thresholdGood : value >= thresholdGood
        const warnCond = reverse ? value < thresholdWarn : value >= thresholdWarn
        color = okCond ? C.success : (warnCond ? C.warn : C.danger)
    }
    return (
        <div style={{
            background: C.bgElevated, padding: S.md, border: `1px solid ${C.border}`,
            borderRadius: R.sm,
        }}>
            <div style={{ fontSize: 10, color: C.textTertiary, textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</div>
            <div style={{
                fontSize: 24, fontWeight: 600, fontFamily: "monospace",
                marginTop: 4, color,
            }}>{value === null || value === undefined ? "—" : value}</div>
            {unit && <div style={{ fontSize: 10, color: C.textTertiary, marginTop: 2 }}>{unit}</div>}
        </div>
    )
}

function TrustVerdict({ trust }: { trust: Trust }) {
    const v = trust?.verdict || ""
    const verdictColor = v === "ready" ? C.success
        : v === "manual_review" ? C.warn : C.danger
    const label = v === "ready" ? "발행 가능"
        : v === "manual_review" ? "검수 필요"
            : v === "hold" ? "발행 차단" : "—"
    const icon = v === "ready" ? "✓"
        : v === "manual_review" ? "⚠" : "✗"
    return (
        <div style={{ textAlign: "center", padding: S.lg }}>
            <div style={{ fontSize: 32, color: verdictColor }}>{icon}</div>
            <div style={{ fontSize: T.title, fontWeight: 600, color: verdictColor, marginTop: S.xs }}>{label}</div>
            <div style={{ fontSize: T.cap, color: C.textTertiary, marginTop: 4 }}>
                조건 만족 {trust?.satisfied ?? "—"}/{trust?.total ?? 8}
            </div>
        </div>
    )
}

function NodeDetailCard({ node, onClose }: { node: NodeT; onClose: () => void }) {
    const m = node.metric || {}
    const d = node.detail || {}
    const change = m.yesterday_change || 0
    return (
        <div style={{
            marginTop: S.md, padding: S.md, background: C.bgElevated,
            border: `1px solid ${C.accent}`, borderRadius: R.sm,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: S.sm }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{
                        width: 8, height: 8, borderRadius: "50%", display: "inline-block",
                        background: HEALTH_HEX[node.health] || C.textTertiary,
                    }} />
                    <strong style={{ color: C.accent }}>{node.label}</strong>
                    <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                        ({node.cluster}{node.sub_cluster ? ` · ${node.sub_cluster}` : ""})
                    </span>
                </div>
                <span style={{ cursor: "pointer", color: C.textTertiary }} onClick={onClose}>✕</span>
            </div>
            <Row label="상태" value={node.health} valueColor={HEALTH_HEX[node.health]} />
            <Row label="Health Score" value={`${node.health_score ?? "—"}/100`} mono />
            {m.primary_label && <Row label={m.primary_label} value={m.primary_value ?? "—"} mono />}
            {change !== 0 && <Row label="어제 대비" value={change > 0 ? `+${change.toFixed(2)}` : change.toFixed(2)} mono />}
            {d.description && <Row label="설명" value={d.description} muted />}
            {d.related_data_health_keys && d.related_data_health_keys.length > 0 &&
                <Row label="관련 소스" value={d.related_data_health_keys.join(", ")} mono small />}
        </div>
    )
}

function Row({ label, value, mono, valueColor, muted, small }: any) {
    return (
        <div style={{
            display: "flex", justifyContent: "space-between",
            padding: `${S.xs}px 0`, borderBottom: `1px solid ${C.border}`,
            fontSize: small ? 11 : T.cap,
        }}>
            <span style={{ color: C.textSecondary }}>{label}</span>
            <span style={{
                color: valueColor || (muted ? C.textTertiary : C.textPrimary),
                fontFamily: mono ? "monospace" : "inherit",
                textAlign: "right", maxWidth: "60%",
            }}>{value}</span>
        </div>
    )
}

function Empty({ msg, small }: { msg: string; small?: boolean }) {
    return (
        <div style={{
            textAlign: "center", padding: small ? S.lg : S.xxl,
            color: C.textTertiary, fontSize: T.cap,
        }}>{msg}</div>
    )
}

// ──────────────────────────────────────────────────────────────
// Data Health Tab — 소스별 표
// ──────────────────────────────────────────────────────────────

function DataHealthTab({ data }: any) {
    if (!data) return <Empty msg="로딩 중..." />
    const rows = data.rows || []
    return (
        <Panel title={`데이터 소스 상태 — ${rows.length}개`}>
            {rows.length === 0 ? <Empty msg="데이터 없음 — 첫 cron 후 표시" /> : (
                <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: T.cap }}>
                        <thead>
                            <tr style={{ color: C.textTertiary, textTransform: "uppercase", fontSize: 10 }}>
                                <Th>소스</Th><Th>상태</Th><Th right>신선도</Th>
                                <Th right>결측률</Th><Th right>지연(ms)</Th>
                                <Th right>7일 성공/실패</Th><Th>비고</Th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r: any, i: number) => (
                                <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                                    <Td><strong>{r.source}</strong></Td>
                                    <Td><Dot status={r.status} />{r.status || "—"}</Td>
                                    <Td right mono>{r.freshness_minutes !== null ? `${r.freshness_minutes}분` : "—"}</Td>
                                    <Td right mono>{r.missing_pct !== null ? `${(r.missing_pct * 100).toFixed(1)}%` : "—"}</Td>
                                    <Td right mono>{r.latency_ms_p50 || "—"}</Td>
                                    <Td right mono>{r.success_count_7d || 0}/{r.failure_count_7d || 0}</Td>
                                    <Td muted small>{(r.detail || "").slice(0, 60)}</Td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </Panel>
    )
}

function Th({ children, right }: any) {
    return <th style={{
        padding: `${S.sm}px ${S.md}px`, textAlign: right ? "right" : "left",
        fontWeight: 500, fontSize: 10, letterSpacing: "0.06em",
    }}>{children}</th>
}
function Td({ children, right, mono, muted, small }: any) {
    return <td style={{
        padding: `${S.sm}px ${S.md}px`, textAlign: right ? "right" : "left",
        fontFamily: mono ? "monospace" : "inherit",
        color: muted ? C.textTertiary : C.textPrimary,
        fontSize: small ? 11 : T.cap,
    }}>{children}</td>
}
function Dot({ status }: { status: string }) {
    return <span style={{
        width: 8, height: 8, borderRadius: "50%", display: "inline-block",
        background: HEALTH_HEX[status] || C.textTertiary, marginRight: 6,
    }} />
}

// ──────────────────────────────────────────────────────────────
// Model Health Tab — Brain Score 분포 + 등급 + 적중률
// ──────────────────────────────────────────────────────────────

function ModelHealthTab({ data }: any) {
    if (!data) return <Empty msg="로딩 중..." />
    const hist = data.brain_score_histogram || []
    const grade = data.grade_distribution || {}
    const hr = data.hit_rate || {}
    const ai = data.ai_disagreements || {}
    const totalCount = Object.values(grade).reduce((s: number, x: any) => s + (x?.count || 0), 0)

    const maxBin = Math.max(1, ...hist.map((h: any) => h.count || 0))

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
            <Panel title="Brain Score 분포 (오늘)">
                <div style={{ display: "flex", alignItems: "flex-end", height: 120, gap: 4, padding: S.sm }}>
                    {hist.map((h: any, i: number) => {
                        const pct = (h.count || 0) / maxBin * 100
                        return (
                            <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                                <div style={{
                                    width: "100%", height: `${pct}%`, background: C.accent,
                                    borderRadius: 2,
                                }} title={`${h.count}`} />
                                <div style={{ fontSize: 9, color: C.textTertiary }}>{h.bin}</div>
                            </div>
                        )
                    })}
                </div>
            </Panel>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: S.md }}>
                <Panel title="등급 분포">
                    {["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"].map(g => {
                        const c = (grade as any)[g] || {}
                        const pct = totalCount ? (c.count || 0) / totalCount * 100 : 0
                        return <BarRow key={g} label={g} value={`${c.count || 0} (${pct.toFixed(1)}%)`} fillPct={pct} />
                    })}
                </Panel>

                <Panel title="적중률 / Brain Quality">
                    <Row label="Brain Quality Score" value={fmtNum(hr.brain_quality_score)} mono />
                    <Row label="BUY 적중률" value={`${fmtNum(hr.buy_hit_rate)}%`} mono />
                    <Row label="AVOID 평균 수익" value={`${fmtNum(hr.avoid_avg_return)}%`} mono />
                </Panel>
            </div>

            <Panel title="AI 모델 이견 통계">
                <Row label="총 비교" value={`${ai.total_compared || 0}건`} mono />
                <Row label="이견 발생" value={`${ai.disagreements || 0}건`} mono />
                <Row label="합치율" value={fmtNum(ai.agreement_rate)} mono />
            </Panel>
        </div>
    )
}

function BarRow({ label, value, fillPct }: any) {
    return (
        <div style={{ display: "flex", alignItems: "center", gap: S.sm, padding: `${S.xs}px 0`, fontSize: T.cap }}>
            <span style={{ width: 110, color: C.textSecondary }}>{label}</span>
            <span style={{ flex: 1, height: 8, background: C.bgElevated, border: `1px solid ${C.border}`, borderRadius: 2 }}>
                <span style={{ display: "block", height: "100%", width: `${fillPct}%`, background: C.accent }} />
            </span>
            <span style={{ width: 100, textAlign: "right", fontFamily: "monospace" }}>{value}</span>
        </div>
    )
}

// ──────────────────────────────────────────────────────────────
// Drift Tab — PSI bars + 양수/음수 기여
// ──────────────────────────────────────────────────────────────

function DriftTab({ data }: any) {
    if (!data) return <Empty msg="로딩 중..." />
    const bars = data.feature_psi_bars || []
    const e = data.explanation || {}
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
            <Panel title={`입력 Feature Drift — PSI per feature (level: ${data.level || "—"})`}>
                {bars.length === 0
                    ? <Empty msg="베이스라인 없음 — 2일째부터 표시" />
                    : bars.map((b: any, i: number) => {
                        const pct = Math.min((b.psi || 0) / 0.5 * 100, 100)
                        const color = b.level === "critical" ? C.danger
                            : b.level === "warning" ? C.warn : C.success
                        return (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: S.sm, padding: `${S.xs}px 0`, fontSize: T.cap }}>
                                <span style={{ width: 200, color: C.textSecondary }}>{b.feature}</span>
                                <span style={{ flex: 1, height: 8, background: C.bgElevated, border: `1px solid ${C.border}`, borderRadius: 2 }}>
                                    <span style={{ display: "block", height: "100%", width: `${pct}%`, background: color }} />
                                </span>
                                <span style={{ width: 80, textAlign: "right", fontFamily: "monospace", color }}>
                                    {(b.psi || 0).toFixed(3)}
                                </span>
                            </div>
                        )
                    })}
            </Panel>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: S.md }}>
                <Panel title="▲ 양수 기여 TOP 5">
                    {(e.positive_top5 || []).length === 0
                        ? <Empty msg="데이터 없음" small />
                        : (e.positive_top5 || []).map((c: any, i: number) => (
                            <Row key={i} label={c.feature} value={`+${fmtNum(c.avg_contribution)}`}
                                valueColor={C.success} mono />
                        ))}
                </Panel>
                <Panel title="▼ 음수 기여 TOP 5">
                    {(e.negative_top5 || []).length === 0
                        ? <Empty msg="없음 (정상)" small />
                        : (e.negative_top5 || []).map((c: any, i: number) => (
                            <Row key={i} label={c.feature} value={fmtNum(c.avg_contribution)}
                                valueColor={C.danger} mono />
                        ))}
                </Panel>
            </div>
        </div>
    )
}

// ──────────────────────────────────────────────────────────────
// Report Readiness Tab — 8 조건 + 최근 PDF
// ──────────────────────────────────────────────────────────────

function ReportReadinessTab({ data }: any) {
    if (!data) return <Empty msg="로딩 중..." />
    const conditions = data.conditions || {}
    const details = data.details || {}
    const labels: Record<string, string> = {
        data_freshness_ok: "데이터 신선도 < 30분",
        core_sources_ok: "핵심 소스 모두 성공",
        drift_below_threshold: "Drift score < 0.3",
        ai_models_ok: "AI 모델 응답 정상",
        brain_distribution_normal: "Brain Score 분포 정상",
        pipeline_cron_ok: "파이프라인 cron 성공",
        deadman_clear: "Deadman Switch 미발동",
        pdf_generator_ok: "PDF 생성기 정상",
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
            <Panel title="오늘 리포트 발행 신뢰도">
                <TrustVerdict trust={data} />
                <div style={{ marginTop: S.lg }}>
                    {Object.keys(labels).map(k => {
                        const ok = conditions[k]
                        return (
                            <div key={k} style={{
                                display: "flex", alignItems: "center", gap: S.sm,
                                padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}`,
                                fontSize: T.cap,
                            }}>
                                <span style={{
                                    width: 16, textAlign: "center",
                                    color: ok ? C.success : C.danger,
                                }}>{ok ? "✓" : "✗"}</span>
                                <span style={{ flex: 1 }}>{labels[k]}</span>
                                <span style={{ color: C.textTertiary, fontSize: 11 }}>{details[k] || ""}</span>
                            </div>
                        )
                    })}
                </div>
            </Panel>

            <Panel title="최근 PDF 생성 이력">
                {(data.recent_pdfs || []).length === 0
                    ? <Empty msg="portfolio.reports_meta 누적 후 표시" small />
                    : (data.recent_pdfs || []).map((p: any, i: number) => (
                        <Row key={i} label={p.name || p.kind || ""} value={p.created_at || ""} mono small />
                    ))}
            </Panel>
        </div>
    )
}

// ──────────────────────────────────────────────────────────────
// 유틸
// ──────────────────────────────────────────────────────────────

function fmtNum(v: any): string {
    if (v === null || v === undefined) return "—"
    if (typeof v !== "number") return String(v)
    if (Math.abs(v) < 0.01 && v !== 0) return v.toExponential(2)
    return Number.isInteger(v) ? v.toString() : v.toFixed(2)
}

// ──────────────────────────────────────────────────────────────
// Framer Property Controls
// ──────────────────────────────────────────────────────────────

addPropertyControls(BrainMonitor, {
    apiBaseUrl: {
        type: ControlType.String,
        title: "API Base URL",
        defaultValue: "https://vercel-api-alpha-umber.vercel.app",
        placeholder: "https://...",
    },
    adminToken: {
        type: ControlType.String,
        title: "Admin Token",
        defaultValue: "",
        placeholder: "ADMIN_BYPASS_TOKEN",
    },
    pollSec: {
        type: ControlType.Number,
        title: "Poll Sec",
        defaultValue: 300,
        min: 60,
        max: 3600,
        step: 60,
    },
})

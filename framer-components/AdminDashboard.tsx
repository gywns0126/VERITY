import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useCallback } from "react"

/* ══════════════════════════════════════════════════════════════════
 * VERITY ADMIN DASHBOARD
 * 관리자(=본인) 가 한 화면에서 시스템 건강·비용·Brain 품질·KB 인용·액션
 * 필요·최근 알림을 보고 즉시 무엇을 해야 하는지 판단하기 위한 컴포넌트.
 *
 * 데이터:
 *   - portfolio.json (raw GitHub URL)  →  cost_monitor / brain_quality / brain_accuracy / updated_at
 *   - brain_kb_usage.json (raw GitHub URL) → 책 인용 통계
 *
 * 본인 외 접근 차단은 이 컴포넌트가 배치된 Framer 페이지에 AuthGate 를 함께
 * 배치해서 처리. 컴포넌트 자체는 데이터 표시만.
 *
 * 5분 자동 새로고침 + 수동 reload 버튼.
 * ══════════════════════════════════════════════════════════════════ */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
/* ◆ DESIGN TOKENS END ◆ */
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const MONO = { fontFamily: "ui-monospace, SF Mono, Menlo, monospace" }

/* ─── 잠재 충돌 페어 (analyze_brain.py 와 동일 정의) ─── */
const CONFLICT_PAIRS: Array<[string, string, string]> = [
    ["graham_intelligent_investor", "oneil_canslim", "안전마진 ↔ 신고가 매수"],
    ["graham_intelligent_investor", "covel_turtle_trader", "내재가치 ↔ 가격만 추종"],
    ["buffett_essays", "nison_candlestick_psychology", "장기 holding ↔ 단기 반전"],
    ["buffett_essays", "carter_mastering_trade", "장기 가치 ↔ TTM 단기"],
    ["bogle_common_sense", "livermore_operator", "패시브 ↔ 피봇 타이밍"],
    ["bogle_common_sense", "antonacci_dual_momentum", "타이밍 무용 ↔ 모멘텀 자산배분"],
    ["malkiel_random_walk", "murphy_technical_analysis", "EMH ↔ 차트 분석"],
    ["malkiel_random_walk", "oneil_canslim", "EMH ↔ CANSLIM"],
    ["douglas_trading_in_zone", "lefevre_reminiscences", "시스템 ↔ 직관 추세"],
    ["aronson_evidence_based", "nison_candlestick_psychology", "통계 유의성 ↔ 주관 패턴"],
]

/* ─── Props ─── */
interface Props {
    portfolioUrl: string
    kbUsageUrl: string
    todosUrl: string
    refreshIntervalSec: number
    /** ESTATE/VERITY 가입 승인용 — 비우면 카드 숨김 */
    supabaseUrl: string
    supabaseAnonKey: string
}

// User Action Queue 자가-종결 — admin 만 효과 발생, 비-admin 은 silent no-op.
function fireQueueHeartbeat(supabaseUrl: string, anonKey: string, componentPath: string): void {
    if (typeof window === "undefined") return
    if (!supabaseUrl || !anonKey || !componentPath) return
    let jwt: string | null = null
    try {
        const raw = localStorage.getItem("verity_supabase_session")
        if (raw) {
            const s = JSON.parse(raw)
            if (!s.expires_at || Date.now() / 1000 <= s.expires_at) jwt = s.access_token || null
        }
    } catch { /* noop */ }
    if (!jwt) return
    fetch(`${supabaseUrl}/rest/v1/rpc/action_queue_heartbeat`, {
        method: "POST",
        headers: {
            apikey: anonKey,
            Authorization: `Bearer ${jwt}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ p_component_path: componentPath }),
    }).catch(() => { /* best-effort */ })
}

/* ─── 사용자 메모 (admin_todos.json) ─── */
type UserTodo = {
    id?: string
    bucket?: "today" | "week" | "soon" | "long"
    severity?: "danger" | "warn" | "info"
    text: string
    due?: string
    done?: boolean
    added?: string
}

function _bucketFromDue(due?: string): "today" | "week" | "soon" | "long" {
    if (!due) return "long"
    const t = Date.parse(due)
    if (Number.isNaN(t)) return "long"
    const days = (t - Date.now()) / (1000 * 60 * 60 * 24)
    if (days < 1) return "today"
    if (days < 7) return "week"
    if (days < 28) return "soon"
    return "long"
}

/* ─── 유틸 ─── */
function _fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    // raw.githubusercontent.com 은 "simple request" 만 허용 — custom header 붙이면
    // CORS preflight 가 걸려 차단됨 (Safari "Load failed" 의 원인).
    // 캐시 우회는 query param 의 timestamp 로만 처리.
    const sep = url.includes("?") ? "&" : "?"
    const finalUrl = `${url}${sep}t=${Date.now()}`
    return fetch(finalUrl, { signal })
        .then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            // GitHub raw 가 NaN/Infinity 보내는 경우 대비
            return r.text().then((t) => {
                const cleaned = t
                    .replace(/:\s*NaN\b/g, ": null")
                    .replace(/:\s*-?Infinity\b/g, ": null")
                return JSON.parse(cleaned)
            })
        })
}

function _hoursSince(iso: string): number | null {
    if (!iso) return null
    const t = Date.parse(iso)
    if (Number.isNaN(t)) return null
    return (Date.now() - t) / (1000 * 60 * 60)
}

function _daysSince(iso: string): number | null {
    const h = _hoursSince(iso)
    return h === null ? null : h / 24
}

function _todayKstDate(): number {
    // KST 일자 (1~31). 월 말 점검 룰 등에 사용.
    const utc = new Date()
    const kst = new Date(utc.getTime() + 9 * 60 * 60 * 1000)
    return kst.getUTCDate()
}

function _fmtKrw(n: number): string {
    return Math.round(n).toLocaleString() + "원"
}

function _statusColor(level: "ok" | "warn" | "danger"): string {
    return level === "ok" ? C.success : level === "warn" ? C.warn : C.danger
}

/* ─── 카드 공통 ─── */
function Card({ title, status, children }: { title: string; status?: "ok" | "warn" | "danger"; children: React.ReactNode }) {
    return (
        <div style={{
            background: C.bgCard, borderRadius: 14, border: `1px solid ${C.border}`,
            padding: "16px 18px", display: "flex", flexDirection: "column", gap: 10,
        }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{
                    color: C.textPrimary, fontSize: 14, fontWeight: 800, fontFamily: FONT,
                    letterSpacing: "-0.01em",
                }}>{title}</span>
                {status && (
                    <span style={{
                        width: 8, height: 8, borderRadius: 999,
                        background: _statusColor(status),
                        boxShadow: `0 0 6px ${_statusColor(status)}50`,
                    }} />
                )}
            </div>
            {children}
        </div>
    )
}

function Row({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) {
    return (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "3px 0", gap: 12 }}>
            <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{label}</span>
            <span style={{ color: color || C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT, ...MONO, textAlign: "right" }}>{value}</span>
        </div>
    )
}

function Bar({ pct, color }: { pct: number; color: string }) {
    const w = Math.max(0, Math.min(100, pct))
    return (
        <div style={{ width: "100%", height: 6, background: C.bgElevated, borderRadius: 3, overflow: "hidden" }}>
            <div style={{ width: `${w}%`, height: "100%", background: color, transition: "width 240ms ease" }} />
        </div>
    )
}

/* ─── 카드 1: 시스템 건강 ─── */
/* CardSystemHealth removed (Step 9 중복 정리, 2026-05-04) */

function CardBillingLinks({ portfolio }: { portfolio: any }) {
    // 호출 수는 정확하지만 USD 추정은 ±25-50% 오차 → 표시 안 하고 콘솔 진입점만 제공.
    const month = portfolio?.cost_monitor?.monthly_usage || {}
    const monthLabel = portfolio?.cost_monitor?.month_key || ""

    // 각 provider 의 사용량/cost 직접 확인 페이지 (사용자가 지정한 URL).
    const links: Array<{ name: string; calls: string; url: string; color: string }> = [
        {
            name: "Claude — Cost",
            calls: `Claude · ${(month.claude_deep_calls || 0) + (month.claude_light_calls || 0)}회 / ${(month.claude_tokens || 0).toLocaleString()} 토큰`,
            url: "https://platform.claude.com/workspaces/default/cost",
            color: C.warn,
        },
        {
            name: "Google AI Studio — Spend",
            calls: `Gemini · stock ${month.gemini_stock_calls || 0} / report ${month.gemini_report_calls || 0} / Pro ${month.gemini_pro_calls || 0}회`,
            url: "https://aistudio.google.com/app/spend",
            color: C.info,
        },
        {
            name: "Perplexity — Billing",
            calls: `Perplexity · ${month.perplexity_calls || 0}회 호출`,
            url: "https://console.perplexity.ai/group/ac387575-4266-40d5-96cc-d1e31462525f/billing",
            color: C.success,
        },
    ]

    return (
        <Card title=" AI 사용량 (각 콘솔 직접 확인)">
            <div style={{ color: C.textTertiary, fontSize: 11, fontFamily: FONT, lineHeight: 1.5 }}>
                내부 카운터는 호출 수만 정확. 토큰 단가·실 청구액은 각 provider
                콘솔의 사용량 페이지에서 확인.
                {monthLabel && <span> · {monthLabel}</span>}
            </div>
            {links.map((ln) => (
                <a
                    key={ln.name}
                    href={ln.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                        display: "flex", alignItems: "center", justifyContent: "space-between",
                        padding: "10px 12px", borderRadius: 10,
                        background: C.bgElevated, border: `1px solid ${C.border}`,
                        textDecoration: "none", marginTop: 4,
                        transition: "border-color 180ms ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = ln.color }}
                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.border }}
                >
                    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                        <span style={{ color: ln.color, fontSize: 13, fontWeight: 800, fontFamily: FONT }}>
                            {ln.name}
                        </span>
                        <span style={{
                            color: C.textSecondary, fontSize: 11, fontFamily: FONT,
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                            ...MONO,
                        }}>
                            {ln.calls}
                        </span>
                    </div>
                    <span style={{ color: ln.color, fontSize: 16, fontWeight: 700, flexShrink: 0, marginLeft: 8 }}>
                        ↗
                    </span>
                </a>
            ))}
        </Card>
    )
}

/* ─── 카드 3: Brain 품질 ─── */
/* CardBrainQuality removed (Step 9 중복 정리, 2026-05-04) */

function CardKBUsage({ kbUsage }: { kbUsage: any }) {
    const total = kbUsage?.total_calls || 0
    const books = kbUsage?.books || {}
    const combos = kbUsage?.combinations || {}

    const topBooks = Object.entries(books).sort((a: any, b: any) => b[1] - a[1]).slice(0, 5)
    const topCombos = Object.entries(combos).sort((a: any, b: any) => b[1] - a[1]).slice(0, 3)

    const conflictHits = CONFLICT_PAIRS.map(([a, b, desc]) => {
        let hits = 0
        for (const [k, v] of Object.entries(combos) as Array<[string, number]>) {
            const parts = k.split("+")
            if (parts.includes(a) && parts.includes(b)) hits += v
        }
        return { a, b, desc, hits }
    }).filter((x) => x.hits > 0).sort((x, y) => y.hits - x.hits).slice(0, 3)

    const cardStatus: "ok" | "warn" | "danger" = total === 0 ? "warn" : "ok"

    return (
        <Card title="📚 KB 인용 패턴" status={cardStatus}>
            {total === 0 ? (
                <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: FONT }}>
                    아직 인용 데이터 없음 — Full cron 며칠 더 누적 필요
                </div>
            ) : (
                <>
                    <Row label="총 인용 호출" value={`${total.toLocaleString()}건`} />
                    <div style={{ marginTop: 4, color: C.textSecondary, fontSize: 11, fontWeight: 700, fontFamily: FONT }}>
                        책 TOP 5
                    </div>
                    {topBooks.map(([book, n]: any) => {
                        const pct = total > 0 ? (n / total * 100) : 0
                        const shortName = String(book).split("_").slice(0, 2).join(" ")
                        return (
                            <div key={book}>
                                <Row label={shortName} value={`${n}회 (${pct.toFixed(1)}%)`} />
                            </div>
                        )
                    })}
                    {topCombos.length > 0 && (
                        <>
                            <div style={{ marginTop: 6, color: C.textSecondary, fontSize: 11, fontWeight: 700, fontFamily: FONT }}>
                                조합 TOP 3
                            </div>
                            {topCombos.map(([combo, n]: any) => {
                                const short = String(combo).split("+").map((b: string) => b.split("_")[0]).join(" + ")
                                return (
                                    <div key={combo}>
                                        <Row label={short} value={`${n}회`} />
                                    </div>
                                )
                            })}
                        </>
                    )}
                    {conflictHits.length > 0 && (
                        <>
                            <div style={{ marginTop: 6, color: C.warn, fontSize: 11, fontWeight: 700, fontFamily: FONT }}>
                                ⚠ 충돌 페어 (동시 인용)
                            </div>
                            {conflictHits.map((cf, i) => {
                                const sa = cf.a.split("_")[0]
                                const sb = cf.b.split("_")[0]
                                return (
                                    <div key={i} style={{ fontSize: 11, fontFamily: FONT, color: C.textSecondary, lineHeight: 1.5 }}>
                                        <span style={{ color: C.warn, fontWeight: 700 }}>{cf.hits}회</span>{" "}
                                        <span style={{ color: C.textPrimary }}>{sa} ↔ {sb}</span>
                                        <span style={{ color: C.textTertiary }}> · {cf.desc}</span>
                                    </div>
                                )
                            })}
                        </>
                    )}
                </>
            )}
        </Card>
    )
}

/* ─── 카드 5: 액션 필요 ─── */
/* CardActions removed (Step 9 중복 정리, 2026-05-04) */

function CardSchedule({ portfolio, kbUsage, userTodos }: { portfolio: any; kbUsage: any; userTodos: UserTodo[] }) {
    const items = _computeSchedule(portfolio, kbUsage, userTodos)
    const buckets: Array<{ key: Bucket; label: string; icon: string; color: string }> = [
        { key: "today", label: "오늘", icon: "", color: C.danger },
        { key: "week", label: "이번 주", icon: "", color: C.warn },
        { key: "soon", label: "2~4주", icon: "", color: C.success },
        { key: "long", label: "장기 / 월말", icon: "", color: C.info },
    ]
    const cardStatus: "ok" | "warn" | "danger" =
        items.some((x) => x.severity === "danger") ? "danger" :
        items.some((x) => x.severity === "warn") ? "warn" : "ok"

    return (
        <Card title="📅 일정 / TODO (자동)" status={cardStatus}>
            {items.length === 0 ? (
                <div style={{ color: C.success, fontSize: 12, fontFamily: FONT, fontWeight: 700 }}>
                    ✅ 룰 기준 즉시 처리할 항목 없음
                </div>
            ) : (
                buckets.map((b) => {
                    const inBucket = items.filter((x) => x.bucket === b.key)
                    if (inBucket.length === 0) return null
                    return (
                        <div key={b.key} style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
                            <div style={{ color: b.color, fontSize: 11, fontWeight: 800, fontFamily: FONT }}>
                                {b.icon} {b.label}
                            </div>
                            {inBucket.map((it, i) => (
                                <div key={i} style={{
                                    paddingLeft: 8, borderLeft: `2px solid ${_statusColor(it.severity)}40`,
                                    fontSize: 12, fontFamily: FONT, color: C.textPrimary, lineHeight: 1.5,
                                    display: "flex", flexDirection: "column", gap: 4,
                                }}>
                                    <span>{it.text}</span>
                                    {it.progress && (
                                        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                                            <span style={{ color: C.textTertiary, fontSize: 10, ...MONO }}>
                                                {it.progress.current.toLocaleString()} / {it.progress.target.toLocaleString()} {it.progress.unit}
                                                {" · "}
                                                {Math.round(it.progress.current / it.progress.target * 100)}%
                                            </span>
                                            <Bar
                                                pct={it.progress.current / it.progress.target * 100}
                                                color={_statusColor(it.severity)}
                                            />
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )
                })
            )}
            <div style={{
                marginTop: 8, paddingTop: 6, borderTop: `1px dashed ${C.border}`,
                color: C.textTertiary, fontSize: 10, fontFamily: FONT, lineHeight: 1.4,
            }}>
                자동: portfolio.json + brain_kb_usage.json 누적 상태 기반.
                📌 표시는 data/admin_todos.json 사용자 메모 (GitHub 직접 편집).
                5분마다 갱신.
            </div>
        </Card>
    )
}


/* ─── 카드 7: 최근 알림 / 운영 신호 ─── */
/* CardAlerts removed (Step 9 중복 정리, 2026-05-04) */

/* ─── 카드 8: Lynch 6분류 분포 (한국 기준) ─── */
const LYNCH_CLASS_META: Record<string, { label: string; color: string; emoji: string; summary: string }> = {
    FAST_GROWER: { label: "Fast Grower", color: C.success, emoji: "", summary: "매출 15%+ 고성장" },
    STALWART:    { label: "Stalwart",    color: C.info,    emoji: "🔵", summary: "안정 성장 5~15%" },
    TURNAROUND:  { label: "Turnaround",  color: C.warn,    emoji: "🟠", summary: "적자→흑자 전환" },
    CYCLICAL:    { label: "Cyclical",    color: C.watch,   emoji: "", summary: "업황 민감" },
    ASSET_PLAY:  { label: "Asset Play",  color: C.info, emoji: "🟣", summary: "저PBR 자산 할인" },
    SLOW_GROWER: { label: "Slow Grower", color: C.textTertiary, emoji: "", summary: "저성장 배당주" },
}

function CardLynchDistribution({ portfolio }: { portfolio: any }) {
    const dist = portfolio?.lynch_kr_distribution
    const counts: Record<string, number> = dist?.counts || {}
    const pct: Record<string, number> = dist?.pct || {}
    const total: number = dist?.total || 0
    const lowQ: number = dist?.low_quality_count || 0
    const lowQPct: number = dist?.low_quality_pct || 0
    const order = ["FAST_GROWER", "STALWART", "TURNAROUND", "CYCLICAL", "ASSET_PLAY", "SLOW_GROWER"]

    return (
        <Card title={`📚 Lynch 6분류 (한국) — ${total}종목`} status="ok">
            {total === 0 ? (
                <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: FONT }}>
                    분류 데이터 없음 — Full cron 1회 후 자동 채워짐
                </div>
            ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {order.map(cls => {
                        const meta = LYNCH_CLASS_META[cls]
                        const c = counts[cls] || 0
                        const p = pct[cls] || 0
                        const barW = Math.max(0, Math.min(100, p))
                        return (
                            <div key={cls} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, fontFamily: FONT }}>
                                <span style={{ width: 100, color: meta.color, fontWeight: 700 }}>
                                    {meta.emoji} {meta.label}
                                </span>
                                <span style={{ flex: 1, height: 6, background: C.bgElevated, border: `1px solid ${C.border}`, borderRadius: 3 }}>
                                    <span style={{ display: "block", height: "100%", width: `${barW}%`, background: meta.color, borderRadius: 2 }} />
                                </span>
                                <span style={{ width: 80, textAlign: "right", ...MONO, color: C.textPrimary }}>
                                    {c}종 ({p.toFixed(1)}%)
                                </span>
                            </div>
                        )
                    })}
                </div>
            )}
            {lowQ > 0 && (
                <div style={{
                    marginTop: 8, padding: "4px 8px", background: `${C.warn}15`,
                    border: `1px solid ${C.warn}40`, borderRadius: 4,
                    color: C.warn, fontSize: 10, fontFamily: FONT,
                }}>
                    ⚠ data_quality=low: {lowQ}종 ({lowQPct}%) — revenue_growth/market_cap/operating_margin 누락.
                    SLOW_GROWER 기본값으로 떨어졌으므로 분포 통계 왜곡 가능.
                </div>
            )}
            <div style={{
                marginTop: 8, paddingTop: 6, borderTop: `1px dashed ${C.border}`,
                color: C.textTertiary, fontSize: 10, fontFamily: FONT, lineHeight: 1.4,
            }}>
                한국 기준: GDP 1.9% × 8 = Fast Grower 15%+. 우선순위 Turnaround → Cyclical → Fast → Stalwart → Asset → Slow.
                lynch_classifier.py 자동 분류.
            </div>
        </Card>
    )
}


/* ─── 카드 9: Brain 진화 이력 ─── */
type EvolutionItem = {
    sha: string
    date: string
    author?: string
    category: string
    kind: string
    title: string
    subject_full?: string
    lines_added?: number
    lines_deleted?: number
}

const CATEGORY_COLOR: Record<string, string> = {
    brain: C.accent,
    observability: C.info,
    reports: C.warn,
    estate: C.success,
}
const CATEGORY_LABEL: Record<string, string> = {
    brain: "BRAIN",
    observability: "OBSERV",
    reports: "REPORTS",
    estate: "ESTATE",
}

/* CardBrainEvolution removed (Step 9 중복 정리, 2026-05-04) */

function CardTradePlanV0({ portfolio }: { portfolio: any }) {
    const meta = portfolio?.trade_plan_meta || null
    const evo = portfolio?.trade_plan_evolution_signals || null

    if (!meta || meta.status === "empty") {
        return (
            <Card title=" trade_plan v0 자체 검증" status="ok">
                <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                    운영 시작 전 — 진입 후보 누적 대기. BUY + entry_active 종목 발생 시 자동 로깅 시작.
                </div>
            </Card>
        )
    }

    const sample = meta.sample_size || {}
    const horizons = meta.horizon_summary || {}
    const evoStatus: string = evo?.status || "no_data"
    const evoSummary = evo?.summary || {}
    const candidates: string[] = evo?.change_candidates || []

    let cardStatus: "ok" | "warn" | "danger" = "ok"
    if (evoStatus === "rule_review_needed") cardStatus = "danger"
    else if (evoStatus === "monitoring") cardStatus = "warn"

    const total: number = sample.total || 0
    const minFor: number = sample.min_for_decompose || 30
    const insufficient = total < minFor

    const hrColor = (hr: number | null | undefined) =>
        hr == null ? C.textTertiary : hr >= 55 ? C.success : hr >= 45 ? C.warn : C.danger
    const fmtPct = (v: number | null | undefined) =>
        v == null ? "—" : `${v >= 0 ? "+" : ""}${v}%`
    const fmtIc = (v: number | null | undefined) =>
        v == null ? "—" : `${v >= 0 ? "+" : ""}${v}`

    const evoLabel: Record<string, string> = {
        rule_review_needed: "룰 재검토",
        monitoring: "관찰",
        healthy: "정상",
        insufficient_data: "데이터 부족",
        no_data: "—",
    }

    return (
        <Card title=" trade_plan v0 자체 검증" status={cardStatus}>
            <Row label="누적 진입 후보" value={`${total}건 (open ${sample.open || 0} · closed ${sample.closed || 0})`} />
            <Row label="채움 현황" value={`h5 ${sample.with_h5 || 0} · h14 ${sample.with_h14 || 0} · h30 ${sample.with_h30 || 0}`} />

            {/* Horizon 표 — n / Hit Rate / Median / IC */}
            <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 3 }}>
                <div style={{ display: "flex", color: C.textTertiary, fontSize: 11, fontFamily: FONT, paddingBottom: 3, borderBottom: `1px solid ${C.border}` }}>
                    <span style={{ flex: "0 0 44px" }}>호라이즌</span>
                    <span style={{ flex: "0 0 36px", textAlign: "right" }}>n</span>
                    <span style={{ flex: 1, textAlign: "right" }}>Hit</span>
                    <span style={{ flex: 1, textAlign: "right" }}>Med Ret</span>
                    <span style={{ flex: 1, textAlign: "right" }}>IC</span>
                </div>
                {(["h5", "h14", "h30"] as const).map((k) => {
                    const h = horizons[k] || {}
                    return (
                        <div key={k} style={{ display: "flex", fontSize: 11, fontFamily: FONT, ...MONO, padding: "2px 0" }}>
                            <span style={{ flex: "0 0 44px", color: C.textSecondary }}>{k}</span>
                            <span style={{ flex: "0 0 36px", textAlign: "right", color: C.textPrimary }}>{h.n || 0}</span>
                            <span style={{ flex: 1, textAlign: "right", color: hrColor(h.hit_rate_pct), fontWeight: 700 }}>
                                {h.hit_rate_pct == null ? "—" : `${h.hit_rate_pct}%`}
                            </span>
                            <span style={{ flex: 1, textAlign: "right", color: C.textPrimary }}>{fmtPct(h.median_return_pct)}</span>
                            <span style={{ flex: 1, textAlign: "right", color: C.textPrimary }}>{fmtIc(h.ic)}</span>
                        </div>
                    )
                })}
            </div>

            {/* 진화 상태 박스 */}
            {evoStatus !== "no_data" && (
                <div style={{ marginTop: 8, padding: "8px 10px", background: C.bgElevated, borderRadius: 6 }}>
                    <Row label="진화 상태" value={
                        <span style={{ color: cardStatus === "danger" ? C.danger : cardStatus === "warn" ? C.warn : C.textPrimary, fontWeight: 800 }}>
                            {evoLabel[evoStatus] || evoStatus}
                        </span>
                    } />
                    {(evoSummary.critical || 0) > 0 && (
                        <Row label="critical" value={<span style={{ color: C.danger }}>{evoSummary.critical}건</span>} />
                    )}
                    {(evoSummary.warning || 0) > 0 && (
                        <Row label="warning" value={<span style={{ color: C.warn }}>{evoSummary.warning}건</span>} />
                    )}
                </div>
            )}

            {/* 룰 변경 후보 (rule_review_needed 일 때) */}
            {candidates.length > 0 && (
                <div style={{ marginTop: 6, padding: "8px 10px", background: C.bgElevated, borderRadius: 6, display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ color: C.textSecondary, fontSize: 11, fontFamily: FONT, fontWeight: 700 }}>룰 변경 후보 (수동 검토)</span>
                    {candidates.slice(0, 3).map((c, i) => (
                        <span key={i} style={{ color: C.textPrimary, fontSize: 11, fontFamily: FONT, lineHeight: 1.45 }}>· {c}</span>
                    ))}
                </div>
            )}

            {insufficient && (
                <div style={{ marginTop: 4, color: C.warn, fontSize: 11, fontFamily: FONT }}>
                    ※ 분해 통계 임계 미달 ({total}/{minFor}) — {minFor - total}건 더 누적 후 진화 신호 활성
                </div>
            )}

            <div style={{ marginTop: 4, paddingTop: 6, borderTop: `1px dashed ${C.border}`, color: C.textTertiary, fontSize: 10, fontFamily: FONT, lineHeight: 1.4 }}>
                자동 룰 변경 X — 본인 검토 후 수동 적용 (4가드: commit/시간대/모니터링/롤백)
            </div>
        </Card>
    )
}


/* ──────────────────────────────────────────────────────────────
 * ◆ CardPendingApprovals — VERITY/ESTATE 가입 승인 ◆
 *   profiles.status='pending' 사용자 리스트 + approve/reject 버튼.
 *   본인이 admin 으로 setting 되어있어야 동작 (008 마이그레이션).
 *   Supabase REST 직접 호출 — anon key + 본인 JWT.
 * ────────────────────────────────────────────────────────────── */
type PendingProfile = {
    id: string
    email: string
    display_name: string
    phone: string
    created_at: string
    status: string
}

/* CardUserActions + UserAction type / _PRIORITY_ORDER / _PRIORITY_HEX
   removed (Step 9 중복 정리 — UserActionBell FAB 가 메인, 2026-05-04) */

function CardPendingApprovals({ supabaseUrl, anonKey }: { supabaseUrl: string; anonKey: string }) {
    const [pending, setPending] = React.useState<PendingProfile[]>([])
    const [error, setError] = React.useState<string>("")
    const [loading, setLoading] = React.useState(false)
    const [busy, setBusy] = React.useState<string | null>(null)  // RPC in-flight uuid

    const getJwt = (): string | null => {
        if (typeof window === "undefined") return null
        try {
            const raw = localStorage.getItem("verity_supabase_session")
            if (!raw) return null
            const s = JSON.parse(raw)
            if (s.expires_at && Date.now() / 1000 > s.expires_at) return null
            return s.access_token || null
        } catch { return null }
    }

    const fetchPending = React.useCallback(async () => {
        if (!supabaseUrl || !anonKey) {
            setError("Supabase URL/Key 미설정 — Framer property 확인")
            return
        }
        const jwt = getJwt()
        if (!jwt) {
            setError("로그인 필요 — verity_supabase_session 없음")
            return
        }
        setLoading(true); setError("")
        try {
            const r = await fetch(
                `${supabaseUrl}/rest/v1/profiles?status=eq.pending&select=id,email,display_name,phone,created_at,status&order=created_at.desc&limit=50`,
                { headers: { apikey: anonKey, Authorization: `Bearer ${jwt}` } }
            )
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            setPending(await r.json())
        } catch (e: any) {
            setError(e.message || "조회 실패")
        } finally {
            setLoading(false)
        }
    }, [supabaseUrl, anonKey])

    React.useEffect(() => { fetchPending() }, [fetchPending])

    const callRpc = async (action: "approve" | "reject", id: string) => {
        const jwt = getJwt()
        if (!jwt) { setError("세션 만료 — 다시 로그인"); return }
        setBusy(id)
        try {
            const fn = action === "approve" ? "admin_approve_profile" : "admin_reject_profile"
            const r = await fetch(`${supabaseUrl}/rest/v1/rpc/${fn}`, {
                method: "POST",
                headers: {
                    apikey: anonKey,
                    Authorization: `Bearer ${jwt}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ target_id: id }),
            })
            if (!r.ok) {
                const body = await r.text().catch(() => "")
                throw new Error(`RPC ${r.status}: ${body.slice(0, 120)}`)
            }
            // 성공 시 리스트에서 제거
            setPending((cur) => cur.filter((p) => p.id !== id))
        } catch (e: any) {
            setError(e.message || `${action} 실패`)
        } finally {
            setBusy(null)
        }
    }

    const status: "ok" | "warn" | "danger" = pending.length === 0 ? "ok" : pending.length >= 5 ? "warn" : "ok"

    return (
        <Card title={`가입 승인 대기 (${pending.length})`} status={status}>
            {error && (
                <div style={{
                    background: `${C.danger}15`, border: `1px solid ${C.danger}40`,
                    borderRadius: 8, padding: "8px 12px", marginBottom: 10,
                    color: C.danger, fontSize: 12,
                }}>
                    ⚠ {error}
                </div>
            )}
            {loading && pending.length === 0 && (
                <div style={{ color: C.textTertiary, fontSize: 12 }}>로드 중…</div>
            )}
            {!loading && pending.length === 0 && !error && (
                <div style={{ color: C.textTertiary, fontSize: 12 }}>대기 중인 가입 신청 없음 ✓</div>
            )}
            {pending.map((p) => (
                <div key={p.id} style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "10px 0", borderBottom: `1px solid ${C.border}`,
                }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {p.display_name || p.email.split("@")[0]}
                        </div>
                        <div style={{ color: C.textSecondary, fontSize: 11, marginTop: 2 }}>
                            {p.email} {p.phone && `· ${p.phone}`}
                        </div>
                        <div style={{ color: C.textTertiary, fontSize: 10, marginTop: 1 }}>
                            신청: {new Date(p.created_at).toLocaleString("ko-KR")}
                        </div>
                    </div>
                    <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                        <button onClick={() => callRpc("approve", p.id)} disabled={busy === p.id} style={{
                            padding: "6px 12px", borderRadius: 6,
                            background: C.success, color: "#0E0F11", border: "none",
                            fontSize: 12, fontWeight: 700, fontFamily: FONT,
                            cursor: busy === p.id ? "wait" : "pointer", opacity: busy === p.id ? 0.5 : 1,
                        }}>승인</button>
                        <button onClick={() => callRpc("reject", p.id)} disabled={busy === p.id} style={{
                            padding: "6px 12px", borderRadius: 6,
                            background: "transparent", color: C.danger,
                            border: `1px solid ${C.danger}60`,
                            fontSize: 12, fontWeight: 700, fontFamily: FONT,
                            cursor: busy === p.id ? "wait" : "pointer", opacity: busy === p.id ? 0.5 : 1,
                        }}>거절</button>
                    </div>
                </div>
            ))}
            <div style={{ marginTop: 10, display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: C.textTertiary, fontSize: 10 }}>
                    008 마이그레이션 + profiles.is_admin=true 필요
                </span>
                <button onClick={fetchPending} disabled={loading} style={{
                    background: "transparent", border: "none", color: C.accent,
                    fontSize: 11, fontFamily: FONT, cursor: loading ? "wait" : "pointer",
                }}>↻ 새로고침</button>
            </div>
        </Card>
    )
}


/* ─── 메인 컴포넌트 ─── */
export default function AdminDashboard(props: Props) {
    const {
        portfolioUrl,
        kbUsageUrl,
        todosUrl,
        refreshIntervalSec = 300,
        supabaseUrl = "",
        supabaseAnonKey = "",
    } = props

    const [portfolio, setPortfolio] = useState<any>(null)
    const [kbUsage, setKbUsage] = useState<any>(null)
    const [userTodos, setUserTodos] = useState<UserTodo[]>([])
    const [error, setError] = useState<string | null>(null)
    const [loadedAt, setLoadedAt] = useState<string>("")
    const [loading, setLoading] = useState(false)

    const load = useCallback(async () => {
        if (!portfolioUrl) {
            setError("portfolioUrl 미설정 — Framer 프로퍼티 확인")
            return
        }
        setLoading(true)
        setError(null)
        const ac = new AbortController()
        try {
            const [pf, kb, td] = await Promise.allSettled([
                _fetchJson(portfolioUrl, ac.signal),
                kbUsageUrl ? _fetchJson(kbUsageUrl, ac.signal) : Promise.resolve({}),
                todosUrl ? _fetchJson(todosUrl, ac.signal) : Promise.resolve({ items: [] }),
            ])
            if (pf.status === "fulfilled") {
                setPortfolio(pf.value)
            } else {
                const reason = (pf.reason as Error)?.message || "unknown"
                const hint = /Load failed|Failed to fetch|NetworkError/i.test(reason)
                    ? " (CORS 차단 또는 네트워크 오류 — URL 직접 브라우저에서 열어 확인)"
                    : ""
                setError(`portfolio fetch 실패: ${reason}${hint}`)
            }
            if (kb.status === "fulfilled") setKbUsage(kb.value)
            if (td.status === "fulfilled") {
                const items = (td.value && Array.isArray(td.value.items)) ? td.value.items : []
                setUserTodos(items as UserTodo[])
            }
            // kbUsage / todos 실패는 무시 (소음 방지)
            setLoadedAt(new Date().toISOString())
        } catch (e: any) {
            setError(e?.message || "로드 실패")
        } finally {
            setLoading(false)
        }
        return () => ac.abort()
    }, [portfolioUrl, kbUsageUrl, todosUrl])

    useEffect(() => {
        load()
        const sec = Math.max(60, Number(refreshIntervalSec) || 300)
        const id = globalThis.setInterval(load, sec * 1000)
        return () => globalThis.clearInterval(id)
    }, [load, refreshIntervalSec])

    // 자가-종결 heartbeat — admin 만 효과
    useEffect(() => {
        fireQueueHeartbeat(supabaseUrl, supabaseAnonKey, "framer-components/AdminDashboard.tsx")
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    return (
        <div style={{
            width: "100%", minHeight: "100vh", background: C.bgPage,
            padding: "20px 16px 40px", boxSizing: "border-box",
            fontFamily: FONT, color: C.textPrimary,
        }}>
            {/* 헤더 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20 }}>
                <div>
                    <div style={{ color: C.accent, fontSize: 22, fontWeight: 900, letterSpacing: "-0.02em" }}>
                        VERITY ADMIN
                    </div>
                    <div style={{ color: C.textSecondary, fontSize: 12, marginTop: 2 }}>
                        시스템 건강·비용·Brain·KB 한눈 모니터링
                    </div>
                </div>
                <button
                    onClick={load}
                    disabled={loading}
                    style={{
                        background: C.bgCard, border: `1px solid ${C.border}`,
                        color: loading ? C.textTertiary : C.accent, padding: "6px 12px",
                        borderRadius: 8, fontSize: 12, fontWeight: 700, fontFamily: FONT,
                        cursor: loading ? "wait" : "pointer",
                    }}
                >
                    {loading ? "갱신 중…" : "↻ 새로고침"}
                </button>
            </div>

            {error && (
                <div style={{
                    background: `${C.danger}15`, border: `1px solid ${C.danger}40`,
                    borderRadius: 10, padding: "10px 14px", marginBottom: 16,
                    color: C.danger, fontSize: 12,
                }}>
                    ⚠ {error}
                </div>
            )}

            {!portfolio && !error && (
                <div style={{ color: C.textSecondary, fontSize: 13, textAlign: "center", padding: 40 }}>
                    데이터 로드 중…
                </div>
            )}

            {portfolio && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 14 }}>
                    {supabaseUrl && supabaseAnonKey && (
                        <CardPendingApprovals
                            supabaseUrl={supabaseUrl}
                            anonKey={supabaseAnonKey}
                        />
                    )}
                    <CardBillingLinks portfolio={portfolio} />
                    <CardKBUsage kbUsage={kbUsage} />
                    <CardSchedule portfolio={portfolio} kbUsage={kbUsage} userTodos={userTodos} />
                    <CardLynchDistribution portfolio={portfolio} />
                    <CardTradePlanV0 portfolio={portfolio} />
                </div>
            )}

            <div style={{
                marginTop: 24, textAlign: "center",
                color: C.textTertiary, fontSize: 11, fontFamily: FONT,
            }}>
                {loadedAt && `마지막 로드: ${new Date(loadedAt).toLocaleString("ko-KR")} · 자동 ${refreshIntervalSec}초마다 갱신`}
            </div>
        </div>
    )
}

/* ─── Framer property controls ─── */
const _DEFAULT_PORTFOLIO = "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json"
const _DEFAULT_KB_USAGE = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/brain_kb_usage.json"
const _DEFAULT_TODOS = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/admin_todos.json"

AdminDashboard.defaultProps = {
    portfolioUrl: _DEFAULT_PORTFOLIO,
    kbUsageUrl: _DEFAULT_KB_USAGE,
    todosUrl: _DEFAULT_TODOS,
    refreshIntervalSec: 300,
    supabaseUrl: "",
    supabaseAnonKey: "",
}

addPropertyControls(AdminDashboard, {
    portfolioUrl: {
        type: ControlType.String, title: "Portfolio URL",
        defaultValue: _DEFAULT_PORTFOLIO,
        description: "data/portfolio.json raw URL",
    },
    kbUsageUrl: {
        type: ControlType.String, title: "KB Usage URL",
        defaultValue: _DEFAULT_KB_USAGE,
        description: "data/brain_kb_usage.json raw URL (선택)",
    },
    todosUrl: {
        type: ControlType.String, title: "Admin Todos URL",
        defaultValue: _DEFAULT_TODOS,
        description: "data/admin_todos.json raw URL — GitHub 직접 편집",
    },
    refreshIntervalSec: {
        type: ControlType.Number, title: "갱신 간격(초)",
        defaultValue: 300, min: 60, max: 3600, step: 60,
    },
    supabaseUrl: {
        type: ControlType.String, title: "Supabase URL",
        defaultValue: "",
        description: "가입 승인 카드용 (예: https://xxxxx.supabase.co). 비우면 카드 숨김.",
    },
    supabaseAnonKey: {
        type: ControlType.String, title: "Supabase Anon Key",
        defaultValue: "",
        description: "anon/public 키. 본인이 admin 으로 setting 되어있어야 동작.",
    },
})

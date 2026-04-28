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

/* ─── Design tokens (MobileApp 와 일관) ─── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B",
    border: "#23242C", borderStrong: "#34353D",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76",
    accent: "#B5FF19",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
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
function CardSystemHealth({ portfolio }: { portfolio: any }) {
    const updated = portfolio?.updated_at || portfolio?.cost_monitor?.updated_at || ""
    const hoursAgo = _hoursSince(updated)
    let status: "ok" | "warn" | "danger" = "ok"
    let healthLabel = "정상"
    if (hoursAgo === null) { status = "danger"; healthLabel = "데이터 없음" }
    else if (hoursAgo > 24) { status = "danger"; healthLabel = "24h+ 정체" }
    else if (hoursAgo > 6) { status = "warn"; healthLabel = "6h+ 경과" }

    const lastModeRaw = portfolio?.cost_monitor?.analysis_mode_last
    const monthRunsObj = portfolio?.cost_monitor?.monthly_usage || {}
    return (
        <Card title="🩺 시스템 건강" status={status}>
            <Row label="상태" value={healthLabel} color={_statusColor(status)} />
            <Row label="마지막 분석" value={
                hoursAgo !== null ? `${hoursAgo.toFixed(1)}h 전` : "—"
            } />
            <Row label="최근 모드" value={lastModeRaw || "—"} />
            <Row label="이번 달 run" value={`${monthRunsObj.runs || 0}회 (full ${monthRunsObj.full_runs || 0}, quick ${monthRunsObj.quick_runs || 0})`} />
        </Card>
    )
}

/* ─── 카드 2: AI 청구 페이지 (정확한 사용량은 각 콘솔에서) ─── */
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
            color: "#D97757",
        },
        {
            name: "Google AI Studio — Spend",
            calls: `Gemini · stock ${month.gemini_stock_calls || 0} / report ${month.gemini_report_calls || 0} / Pro ${month.gemini_pro_calls || 0}회`,
            url: "https://aistudio.google.com/app/spend",
            color: "#4285F4",
        },
        {
            name: "Perplexity — Billing",
            calls: `Perplexity · ${month.perplexity_calls || 0}회 호출`,
            url: "https://console.perplexity.ai/group/ac387575-4266-40d5-96cc-d1e31462525f/billing",
            color: "#20B5A8",
        },
    ]

    return (
        <Card title="📊 AI 사용량 (각 콘솔 직접 확인)">
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
function CardBrainQuality({ portfolio }: { portfolio: any }) {
    const bq = portfolio?.brain_quality || {}
    const ba = portfolio?.brain_accuracy || {}
    const score = bq.score
    const sStatus = bq.status

    let cardStatus: "ok" | "warn" | "danger" = "ok"
    let scoreLabel = ""
    if (sStatus === "no_data" || sStatus === "insufficient_data") {
        cardStatus = "warn"
        scoreLabel = "데이터 누적 중"
    } else if (typeof score === "number") {
        if (score >= 70) { cardStatus = "ok"; scoreLabel = `${score.toFixed(1)} 우수` }
        else if (score >= 50) { cardStatus = "warn"; scoreLabel = `${score.toFixed(1)} 보통` }
        else { cardStatus = "danger"; scoreLabel = `${score.toFixed(1)} 낮음` }
    } else {
        cardStatus = "danger"
        scoreLabel = "—"
    }

    const components = bq.components || {}
    const metrics = bq.metrics || {}
    return (
        <Card title="🧠 Brain 품질" status={cardStatus}>
            <Row label="종합 점수 / 100" value={scoreLabel} color={_statusColor(cardStatus)} />
            {sStatus === "ok" && (
                <>
                    <Row label="양성 적중률" value={`${(components.positive_hit_rate_score || 0).toFixed(1)}/40`} />
                    <Row label="AVOID 회피" value={`${(components.avoid_avoidance_score || 0).toFixed(1)}/30`} />
                    <Row label="등급 분리도" value={`${(components.grade_separation_score || 0).toFixed(1)}/30`} />
                    <Row label="총 표본" value={`${metrics.total_samples || 0}건`} />
                </>
            )}
            {sStatus !== "ok" && bq.note && (
                <div style={{ color: C.textTertiary, fontSize: 11, fontFamily: FONT, lineHeight: 1.5 }}>
                    {bq.note}
                </div>
            )}
            {ba.insight && (
                <div style={{
                    color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5,
                    paddingTop: 8, borderTop: `1px dashed ${C.border}`,
                }}>
                    💬 {ba.insight}
                </div>
            )}
        </Card>
    )
}

/* ─── 카드 4: KB 인용 TOP ─── */
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
function CardActions({ portfolio }: { portfolio: any }) {
    const items: Array<{ severity: "warn" | "danger"; text: string }> = []

    // 비용 진척률 경고 제거 — 내부 USD 추정이 부정확해서 false positive 가능.
    // 정확한 청구는 'AI 청구 / 사용량' 카드의 콘솔 링크에서 직접 확인.

    // 데이터 정체
    const updated = portfolio?.updated_at || portfolio?.cost_monitor?.updated_at || ""
    const hoursAgo = _hoursSince(updated)
    if (hoursAgo === null) items.push({ severity: "danger", text: "portfolio.json 갱신 시각 없음 — cron 점검" })
    else if (hoursAgo > 24) items.push({ severity: "danger", text: `${hoursAgo.toFixed(0)}h+ 정체 — Full cron 점검` })

    // STRONG_BUY 부재 + 점수 낮음
    const recs = portfolio?.recommendations || []
    const strongBuyCount = recs.filter((r: any) => (r?.verity_brain?.grade) === "STRONG_BUY").length
    if (strongBuyCount === 0 && recs.length > 0) {
        items.push({ severity: "warn", text: `STRONG_BUY 0개 (총 ${recs.length}종목) — Claude 호출 트리거 안 됨, 임계값 검토` })
    }

    // Brain quality 표본 부족
    const bq = portfolio?.brain_quality || {}
    if (bq.status === "insufficient_data") items.push({ severity: "warn", text: "Brain 품질 점수 표본 5건 미만 — 계속 누적" })
    else if (bq.status === "no_data") items.push({ severity: "warn", text: "Brain 품질 데이터 없음 — Full cron 1회+ 필요" })

    // Claude 호출 0
    const lb = portfolio?.ai_leaderboard?.by_source || []
    const hasClaude = lb.some((r: any) => r.source === "claude")
    if (!hasClaude && recs.length > 0) {
        items.push({ severity: "warn", text: "Claude 호출 표본 없음 — CLAUDE_MORNING_STRATEGY=1 / CLAUDE_MIN_BRAIN_SCORE 조정" })
    }

    const severity: "ok" | "warn" | "danger" =
        items.some((x) => x.severity === "danger") ? "danger" :
        items.length > 0 ? "warn" : "ok"

    return (
        <Card title="⚠️ 액션 필요" status={severity}>
            {items.length === 0 ? (
                <div style={{ color: C.success, fontSize: 12, fontFamily: FONT, fontWeight: 700 }}>
                    ✅ 즉시 조치 필요한 항목 없음
                </div>
            ) : (
                items.map((it, i) => (
                    <div key={i} style={{
                        display: "flex", gap: 8, alignItems: "flex-start",
                        padding: "6px 0",
                        borderBottom: i < items.length - 1 ? `1px solid ${C.border}` : "none",
                    }}>
                        <span style={{
                            width: 6, height: 6, borderRadius: 999, marginTop: 6,
                            background: _statusColor(it.severity), flexShrink: 0,
                        }} />
                        <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                            {it.text}
                        </span>
                    </div>
                ))
            )}
        </Card>
    )
}

/* ─── 카드 6: 일정 / TODO (룰 기반 자동) ─── */
type Bucket = "today" | "week" | "soon" | "long"
type ScheduleItem = {
    bucket: Bucket
    severity: "danger" | "warn" | "info"
    text: string
    progress?: { current: number; target: number; unit: string }
}

function _computeSchedule(portfolio: any, kbUsage: any, userTodos: UserTodo[] = []): ScheduleItem[] {
    const items: ScheduleItem[] = []

    // ── 사용자 메모 (admin_todos.json) — done=false 만 표시, 📌 prefix 로 시각 구분 ──
    for (const t of userTodos) {
        if (!t || t.done) continue
        const text = (t.text || "").trim()
        if (!text) continue
        const bucket = t.bucket || _bucketFromDue(t.due)
        items.push({
            bucket: bucket,
            severity: t.severity || "info",
            text: `📌 ${text}${t.due ? ` (마감: ${t.due})` : ""}`,
        })
    }

    // ── 오늘 ──
    const updated = portfolio?.updated_at || portfolio?.cost_monitor?.updated_at || ""
    const hoursAgo = _hoursSince(updated)
    if (hoursAgo === null) {
        items.push({ bucket: "today", severity: "danger", text: "portfolio 갱신 시각 없음 — cron 즉시 점검" })
    } else if (hoursAgo > 24) {
        items.push({ bucket: "today", severity: "danger", text: `${hoursAgo.toFixed(0)}h+ 정체 — Full cron 즉시 점검` })
    }

    // ── 이번 주 ──
    const bq = portfolio?.brain_quality || {}
    const totalSamples = bq?.metrics?.total_samples || 0
    if (bq.status === "no_data") {
        items.push({ bucket: "week", severity: "warn", text: "brain_quality 미산출 — 다음 Full cron 후 자동 채워짐" })
    } else if (bq.status === "insufficient_data" || (bq.status === "ok" && totalSamples < 5)) {
        items.push({
            bucket: "week", severity: "warn",
            text: "Brain 등급별 표본 누적 대기",
            progress: { current: totalSamples, target: 5, unit: "건" },
        })
    }

    // Claude 호출 0
    const monthUsage = portfolio?.cost_monitor?.monthly_usage || {}
    const claudeCalls = (monthUsage.claude_deep_calls || 0) + (monthUsage.claude_light_calls || 0)
    const recsCount = (portfolio?.recommendations || []).length
    if (claudeCalls === 0 && recsCount > 0) {
        items.push({
            bucket: "week", severity: "warn",
            text: "Claude 호출 0 — env (CLAUDE_MORNING_STRATEGY=1, CLAUDE_MIN_BRAIN_SCORE=55) 적용 후 다음 Full 결과 확인",
        })
    }

    // ── 2~4주 후 ──
    const totalKbCalls = kbUsage?.total_calls || 0
    const lastRunCalls = kbUsage?.last_run_calls || 0
    const KB_TARGET = 200
    if (totalKbCalls < KB_TARGET) {
        // 일평균 추정 — last_run_calls × 2 (Full cron 하루 2회 가정)
        const dailyRate = lastRunCalls > 0 ? lastRunCalls * 2 : 0
        const remaining = KB_TARGET - totalKbCalls
        const daysLeft = dailyRate > 0 ? Math.ceil(remaining / dailyRate) : null
        const eta = daysLeft !== null ? ` (~${daysLeft}일 후)` : ""
        items.push({
            bucket: "soon", severity: "info",
            text: `KB 충돌 페어 분석 시점${eta} — analyze_brain.py --conflicts`,
            progress: { current: totalKbCalls, target: KB_TARGET, unit: "회" },
        })
    } else {
        items.push({
            bucket: "soon", severity: "info",
            text: "✓ KB 누적 200+ — analyze_brain.py --conflicts 실행 적기",
        })
    }

    // brain_quality 점수 산출됐고 표본 5+ → 추이 평가 시점
    if (bq.status === "ok" && totalSamples >= 5) {
        const score = bq.score
        const scoreLabel = typeof score === "number" ? ` (현재 ${score.toFixed(1)}점)` : ""
        items.push({
            bucket: "soon", severity: "info",
            text: `Brain 점수 추이 평가 시점${scoreLabel} — 임계값 조정 검토`,
        })
    }

    // ── 장기 / 월말 점검 ──
    const dayOfMonth = _todayKstDate()
    if (dayOfMonth >= 25) {
        items.push({ bucket: "long", severity: "info", text: "이번 달 말 — Cap 사용 패턴 / 청구액 콘솔에서 점검" })
    }

    return items
}

function CardSchedule({ portfolio, kbUsage, userTodos }: { portfolio: any; kbUsage: any; userTodos: UserTodo[] }) {
    const items = _computeSchedule(portfolio, kbUsage, userTodos)
    const buckets: Array<{ key: Bucket; label: string; icon: string; color: string }> = [
        { key: "today", label: "오늘", icon: "🔴", color: C.danger },
        { key: "week", label: "이번 주", icon: "🟡", color: C.warn },
        { key: "soon", label: "2~4주", icon: "🟢", color: C.success },
        { key: "long", label: "장기 / 월말", icon: "💡", color: C.info },
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
function CardAlerts({ portfolio }: { portfolio: any }) {
    const items: Array<{ icon: string; text: string }> = []

    // weekly_report 의 risk_watch 가 fallback 메시지면 표시
    const wrRisk = portfolio?.weekly_report?.risk_watch || ""
    if (wrRisk.includes("AI 리포트 생성 실패") || wrRisk.includes("RESOURCE_EXHAUSTED")) {
        items.push({ icon: "🚨", text: "Gemini 할당량 초과 — 이번 주간 리포트 fallback" })
    }

    // 비용 status 신호 제거 — 내부 USD 추정 부정확. 청구 카드의 콘솔 링크 사용.

    // dual_model_weights 피드백
    const dmw = portfolio?.dual_model_weights || {}
    const fbStatus = dmw.feedback_status
    if (fbStatus === "applied") {
        items.push({ icon: "🎚", text: `AI 가중치 조정 적용 (Δhit=${dmw.delta_hit_rate || 0}%p)` })
    } else if (fbStatus === "insufficient_samples") {
        items.push({ icon: "📊", text: `AI 가중치 base 유지 — 샘플 부족 (gemini ${dmw.gemini_n || 0}, claude ${dmw.claude_n || 0})` })
    }

    // briefing alerts 카운트
    const alertCounts = portfolio?.briefing?.alert_counts || {}
    if (alertCounts.critical) items.push({ icon: "🔴", text: `긴급 알림 ${alertCounts.critical}건` })
    if (alertCounts.warning) items.push({ icon: "🟡", text: `주의 알림 ${alertCounts.warning}건` })

    return (
        <Card title="🔔 최근 신호">
            {items.length === 0 ? (
                <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: FONT }}>
                    표시할 신호 없음
                </div>
            ) : (
                items.slice(0, 8).map((it, i) => (
                    <div key={i} style={{ fontSize: 12, fontFamily: FONT, color: C.textSecondary, padding: "4px 0", lineHeight: 1.5 }}>
                        <span style={{ marginRight: 8 }}>{it.icon}</span>
                        <span style={{ color: C.textPrimary }}>{it.text}</span>
                    </div>
                ))
            )}
        </Card>
    )
}

/* ─── 카드 8: Lynch 6분류 분포 (한국 기준) ─── */
const LYNCH_CLASS_META: Record<string, { label: string; color: string; emoji: string; summary: string }> = {
    FAST_GROWER: { label: "Fast Grower", color: C.success, emoji: "🟢", summary: "매출 15%+ 고성장" },
    STALWART:    { label: "Stalwart",    color: C.info,    emoji: "🔵", summary: "안정 성장 5~15%" },
    TURNAROUND:  { label: "Turnaround",  color: C.warn,    emoji: "🟠", summary: "적자→흑자 전환" },
    CYCLICAL:    { label: "Cyclical",    color: C.watch,   emoji: "🟡", summary: "업황 민감" },
    ASSET_PLAY:  { label: "Asset Play",  color: "#A855F7", emoji: "🟣", summary: "저PBR 자산 할인" },
    SLOW_GROWER: { label: "Slow Grower", color: C.textTertiary, emoji: "⚪", summary: "저성장 배당주" },
}

function CardLynchDistribution({ portfolio }: { portfolio: any }) {
    const dist = portfolio?.lynch_kr_distribution
    const counts: Record<string, number> = dist?.counts || {}
    const pct: Record<string, number> = dist?.pct || {}
    const total: number = dist?.total || 0
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

function CardBrainEvolution({ portfolio }: { portfolio: any }) {
    const log: EvolutionItem[] = portfolio?.brain_evolution_log || []
    const recent = log.slice(0, 8)

    return (
        <Card title="🧬 Brain 진화 이력" status="ok">
            {recent.length === 0 ? (
                <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: FONT }}>
                    이력 없음 — Full cron 1회 후 자동 채워짐
                </div>
            ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {recent.map((it, i) => {
                        const color = CATEGORY_COLOR[it.category] || C.textSecondary
                        const label = CATEGORY_LABEL[it.category] || it.category.toUpperCase()
                        const diff = `+${it.lines_added || 0}/-${it.lines_deleted || 0}`
                        return (
                            <div key={`${it.sha}-${i}`} style={{
                                paddingBottom: 8,
                                borderBottom: i < recent.length - 1 ? `1px solid ${C.border}` : "none",
                                display: "flex", flexDirection: "column", gap: 4,
                            }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                    <span style={{
                                        background: `${color}20`, color, fontSize: 9, fontWeight: 800,
                                        padding: "2px 6px", borderRadius: 3, letterSpacing: "0.04em",
                                        fontFamily: FONT,
                                    }}>{label}</span>
                                    <span style={{ ...MONO, color: C.textTertiary, fontSize: 10 }}>
                                        {it.sha} · {it.date}
                                    </span>
                                    <span style={{ ...MONO, color: C.textTertiary, fontSize: 10, marginLeft: "auto" }}>
                                        {diff}
                                    </span>
                                </div>
                                <div style={{
                                    color: C.textPrimary, fontSize: 12, fontFamily: FONT,
                                    lineHeight: 1.45,
                                }}>
                                    {it.title}
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}
            <div style={{
                marginTop: 8, paddingTop: 6, borderTop: `1px dashed ${C.border}`,
                color: C.textTertiary, fontSize: 10, fontFamily: FONT, lineHeight: 1.4,
            }}>
                자동: git log 의 feat/fix/perf/refactor(brain|observability|reports|estate) commit 추적.
                Full cron 마다 갱신.
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
            // kbUsage / todos 실패는 무시 (소음 방지) — portfolio 만 있으면 핵심 카드 표시 가능
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
                    <CardSystemHealth portfolio={portfolio} />
                    <CardBillingLinks portfolio={portfolio} />
                    <CardBrainQuality portfolio={portfolio} />
                    <CardKBUsage kbUsage={kbUsage} />
                    <CardActions portfolio={portfolio} />
                    <CardSchedule portfolio={portfolio} kbUsage={kbUsage} userTodos={userTodos} />
                    <CardAlerts portfolio={portfolio} />
                    <CardLynchDistribution portfolio={portfolio} />
                    <CardBrainEvolution portfolio={portfolio} />
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
const _DEFAULT_PORTFOLIO = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"
const _DEFAULT_KB_USAGE = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/brain_kb_usage.json"
const _DEFAULT_TODOS = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/admin_todos.json"

AdminDashboard.defaultProps = {
    portfolioUrl: _DEFAULT_PORTFOLIO,
    kbUsageUrl: _DEFAULT_KB_USAGE,
    todosUrl: _DEFAULT_TODOS,
    refreshIntervalSec: 300,
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
})

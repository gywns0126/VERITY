import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"

/* ──────────────────────────────────────────────────────────────
 * VERITY ESTATE — Action Log
 *
 * data/estate_action_log.json 을 fetch 해서 표시.
 * - 우선순위 list (pending 만, high → mid → low)
 * - 캘린더 (due_date 있는 항목 — 월별 그리드)
 * - status 토글은 *읽기 전용* (GitHub commit 으로만 변경 — git history 가 진실)
 *
 * Framer property:
 *   - apiUrl: action_log JSON URL (기본: GitHub raw)
 *   - showCalendar: 캘린더 영역 표시 여부 (false 면 list 만)
 * ────────────────────────────────────────────────────────────── */

/* ESTATE 패밀리룩 v3 (2026-05-05) — Cluster A warm gold tone 통일.
   액션 카테고리 색 (high/mid/low/done/scheduled/cat_*) 은 도메인 색이라 보존. */
const C = {
    bgPage: "#0A0908", bgCard: "#0F0D0A", bgElevated: "#16130E",
    border: "transparent", borderStrong: "#3A3024",
    textPrimary: "#F2EFE9", textSecondary: "#A8A299", textTertiary: "#6B665E", textDisabled: "#4A453E",
    accent: "#B8864D", accentSoft: "rgba(184,134,77,0.15)", accentBright: "#D4A26B",
    high: "#EF4444", mid: "#F59E0B", low: "#5BA9FF",
    done: "#22C55E", scheduled: "#A78BFA",
    cat_supabase: "#3ECF8E", cat_github: "#EAEAEA",
    cat_framer: "#0099FF", cat_ops: "#FF6B6B", cat_general: "#A8A299",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_SERIF = "'Noto Serif KR', 'Times New Roman', serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"

/* Types */
interface Action {
    id: string
    created_at: string
    label: string
    body: string
    status: "pending" | "done" | "skipped" | "scheduled"
    priority: "high" | "mid" | "low"
    due_date: string | null
    category: "supabase" | "github" | "framer" | "ops" | "general"
    source: string
}

interface Payload {
    version: string
    generated_at: string
    items: Action[]
}

/* helpers */
function priorityColor(p: Action["priority"]) {
    return p === "high" ? C.high : p === "mid" ? C.mid : C.low
}
function statusColor(s: Action["status"]) {
    return s === "done" ? C.done : s === "scheduled" ? C.scheduled : s === "skipped" ? C.textTertiary : C.accent
}
function categoryColor(c: Action["category"]) {
    const map: Record<string, string> = {
        supabase: C.cat_supabase, github: C.cat_github, framer: C.cat_framer,
        ops: C.cat_ops, general: C.cat_general,
    }
    return map[c] || C.textTertiary
}
function categoryEmoji(c: Action["category"]): string {
    return c === "supabase" ? "DB"
        : c === "github" ? "GH"
        : c === "framer" ? "FR"
        : c === "ops" ? "OP"
        : "··"
}
function fmtDate(iso: string): string {
    if (!iso) return ""
    try { return new Date(iso).toLocaleDateString("ko-KR", { month: "short", day: "numeric" }) } catch { return iso }
}

/* Props */
interface Props {
    apiUrl: string
    showCalendar: boolean
    monthsAhead: number
}

/* Component */
export default function EstateActionLog(props: Props) {
    const { apiUrl, showCalendar = true, monthsAhead = 2 } = props
    const [data, setData] = useState<Payload | null>(null)
    const [error, setError] = useState<string>("")
    const [loading, setLoading] = useState(true)
    const [filter, setFilter] = useState<"pending" | "all">("pending")
    const [openId, setOpenId] = useState<string | null>(null)

    useEffect(() => {
        if (!apiUrl) {
            setError("apiUrl 미설정 — Framer property 확인")
            setLoading(false)
            return
        }
        setLoading(true); setError("")
        fetch(apiUrl, { cache: "no-store" })
            .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
            .then((j: Payload) => { setData(j); setLoading(false) })
            .catch((e) => { setError(e.message || "로드 실패"); setLoading(false) })
    }, [apiUrl])

    const items = useMemo(() => {
        if (!data) return []
        const arr = filter === "pending"
            ? data.items.filter((x) => x.status === "pending" || x.status === "scheduled")
            : data.items
        // priority 순 → due_date 빠른 순 → created_at 최신
        const pri = { high: 0, mid: 1, low: 2 }
        return [...arr].sort((a, b) => {
            const pa = (pri as any)[a.priority] ?? 9
            const pb = (pri as any)[b.priority] ?? 9
            if (pa !== pb) return pa - pb
            const da = a.due_date || "9999-99-99"
            const db = b.due_date || "9999-99-99"
            if (da !== db) return da.localeCompare(db)
            return (b.created_at || "").localeCompare(a.created_at || "")
        })
    }, [data, filter])

    const dated = useMemo(() => items.filter((x) => x.due_date), [items])

    const counts = useMemo(() => {
        if (!data) return { pending: 0, scheduled: 0, done: 0, total: 0 }
        const c = { pending: 0, scheduled: 0, done: 0, total: data.items.length }
        for (const it of data.items) {
            if (it.status === "pending") c.pending++
            else if (it.status === "scheduled") c.scheduled++
            else if (it.status === "done") c.done++
        }
        return c
    }, [data])

    return (
        <div style={pageStyle}>
            {/* Header */}
            <div style={{ marginBottom: 20 }}>
                <div style={{
                    color: C.textTertiary, fontSize: 11, fontFamily: FONT,
                    letterSpacing: "0.18em", textTransform: "uppercase",
                }}>
                    VERITY ESTATE
                </div>
                <div style={{
                    color: C.accent, fontSize: 26, fontWeight: 700,
                    fontFamily: FONT_SERIF, letterSpacing: "-0.01em", marginTop: 4,
                }}>
                    Action Log
                </div>
                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 6 }}>
                    펜딩 <span style={{ color: C.accent, fontWeight: 700 }}>{counts.pending}</span>
                    {" · "}예약 <span style={{ color: C.scheduled, fontWeight: 700 }}>{counts.scheduled}</span>
                    {" · "}완료 <span style={{ color: C.done, fontWeight: 700 }}>{counts.done}</span>
                    {" / 총 "}{counts.total}
                    {data?.generated_at && (
                        <span style={{ color: C.textTertiary, marginLeft: 12 }}>
                            (갱신 {fmtDate(data.generated_at)})
                        </span>
                    )}
                </div>
            </div>

            {/* Filter */}
            <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
                {(["pending", "all"] as const).map((f) => (
                    <button key={f} onClick={() => setFilter(f)} style={{
                        ...filterBtnStyle,
                        background: filter === f ? C.accent : "transparent",
                        color: filter === f ? "#0E0E0E" : C.textSecondary,
                        border: `1px solid ${filter === f ? C.accent : C.border}`,
                    }}>
                        {f === "pending" ? "펜딩만" : "전체"}
                    </button>
                ))}
            </div>

            {/* States */}
            {loading && <div style={emptyStyle}>로드 중…</div>}
            {error && !loading && (
                <div style={{ ...emptyStyle, border: `1px solid ${C.high}40`, background: `${C.high}10`, color: C.high }}>
                    {error}
                </div>
            )}

            {!loading && !error && data && (
                <>
                    {/* List */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 24 }}>
                        {items.length === 0 && (
                            <div style={emptyStyle}>액션 없음 ✓</div>
                        )}
                        {items.map((a) => {
                            const open = openId === a.id
                            return (
                                <div key={a.id} style={{
                                    ...itemStyle,
                                    borderLeft: `3px solid ${priorityColor(a.priority)}`,
                                }}>
                                    <div onClick={() => setOpenId(open ? null : a.id)} style={{
                                        display: "flex", alignItems: "center", gap: 10, cursor: "pointer",
                                    }}>
                                        {/* priority dot */}
                                        <div style={{
                                            width: 8, height: 8, borderRadius: 4,
                                            background: priorityColor(a.priority), flexShrink: 0,
                                        }} />
                                        {/* category badge */}
                                        <div style={{
                                            padding: "2px 6px", borderRadius: 4,
                                            background: `${categoryColor(a.category)}20`,
                                            color: categoryColor(a.category),
                                            fontSize: 9, fontWeight: 800, fontFamily: FONT_MONO,
                                            letterSpacing: 0.5, flexShrink: 0,
                                        }}>{categoryEmoji(a.category)}</div>
                                        {/* label */}
                                        <div style={{
                                            flex: 1, color: a.status === "done" ? C.textTertiary : C.textPrimary,
                                            fontSize: 13, fontWeight: 700, fontFamily: FONT,
                                            textDecoration: a.status === "done" ? "line-through" : "none",
                                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                                        }}>
                                            {a.label}
                                        </div>
                                        {/* due date */}
                                        {a.due_date && (
                                            <div style={{
                                                color: C.textSecondary, fontSize: 11, fontFamily: FONT_MONO,
                                                flexShrink: 0,
                                            }}>{a.due_date}</div>
                                        )}
                                        {/* status pill */}
                                        <div style={{
                                            padding: "2px 8px", borderRadius: 999,
                                            background: `${statusColor(a.status)}25`,
                                            color: statusColor(a.status),
                                            fontSize: 10, fontWeight: 800, fontFamily: FONT,
                                            flexShrink: 0,
                                        }}>{a.status}</div>
                                        {/* expand caret */}
                                        <div style={{
                                            color: C.textTertiary, fontSize: 11, flexShrink: 0,
                                            transform: open ? "rotate(90deg)" : "rotate(0deg)",
                                            transition: "transform 0.15s",
                                        }}>›</div>
                                    </div>
                                    {open && (
                                        <div style={{
                                            marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.border}`,
                                            color: C.textSecondary, fontSize: 12, fontFamily: FONT,
                                            lineHeight: 1.6, whiteSpace: "pre-wrap",
                                        }}>
                                            {a.body || "(상세 본문 없음)"}
                                            <div style={{ marginTop: 8, color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO }}>
                                                id={a.id.slice(0, 8)} · source={a.source} · created {fmtDate(a.created_at)}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                    </div>

                    {/* Calendar (due_date 있는 항목) */}
                    {showCalendar && dated.length > 0 && (
                        <Calendar items={dated} monthsAhead={monthsAhead} />
                    )}
                </>
            )}

            {/* Footer hint */}
            <div style={{
                marginTop: 20, padding: 12, borderRadius: 8,
                background: C.bgCard, border: `1px solid ${C.border}`,
                color: C.textTertiary, fontSize: 11, fontFamily: FONT, lineHeight: 1.6,
            }}>
                ↻ 상태 변경은 GitHub repo data/estate_action_log.json 직접 편집 또는
                다음 Claude 세션에서 자동 갱신.
            </div>
        </div>
    )
}

/* Calendar — 월별 그리드 */
function Calendar({ items, monthsAhead }: { items: Action[]; monthsAhead: number }) {
    // due_date 별 그룹
    const byDate = useMemo(() => {
        const m: Record<string, Action[]> = {}
        for (const it of items) {
            if (!it.due_date) continue
            ;(m[it.due_date] = m[it.due_date] || []).push(it)
        }
        return m
    }, [items])

    // 표시할 월 list (현재월 + monthsAhead)
    const months = useMemo(() => {
        const out: { y: number; m: number }[] = []
        const now = new Date()
        for (let i = 0; i <= monthsAhead; i++) {
            const d = new Date(now.getFullYear(), now.getMonth() + i, 1)
            out.push({ y: d.getFullYear(), m: d.getMonth() + 1 })
        }
        return out
    }, [monthsAhead])

    return (
        <div style={{ marginTop: 8 }}>
            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 10 }}>
                일정 캘린더
            </div>
            <div style={{
                display: "grid", gap: 16,
                gridTemplateColumns: `repeat(auto-fit, minmax(280px, 1fr))`,
            }}>
                {months.map(({ y, m }) => (
                    <MonthGrid key={`${y}-${m}`} year={y} month={m} byDate={byDate} />
                ))}
            </div>
        </div>
    )
}

function MonthGrid({ year, month, byDate }: { year: number; month: number; byDate: Record<string, Action[]> }) {
    const firstWeekday = new Date(year, month - 1, 1).getDay() // 0=일
    const daysInMonth = new Date(year, month, 0).getDate()
    const cells: { day: number | null; date: string | null }[] = []
    for (let i = 0; i < firstWeekday; i++) cells.push({ day: null, date: null })
    for (let d = 1; d <= daysInMonth; d++) {
        const date = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`
        cells.push({ day: d, date })
    }

    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            borderRadius: 10, padding: 12,
        }}>
            <div style={{
                color: C.accent, fontSize: 13, fontWeight: 700, fontFamily: FONT_SERIF,
                marginBottom: 8,
            }}>
                {year}년 {month}월
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2 }}>
                {["일", "월", "화", "수", "목", "금", "토"].map((d) => (
                    <div key={d} style={{
                        textAlign: "center", color: C.textTertiary, fontSize: 9,
                        fontFamily: FONT, padding: 4,
                    }}>{d}</div>
                ))}
                {cells.map((c, i) => {
                    const acts = c.date ? byDate[c.date] : null
                    const has = acts && acts.length > 0
                    const topPri = has ? acts!.reduce((p, a) =>
                        ({ high: 3, mid: 2, low: 1 } as any)[a.priority] >
                        ({ high: 3, mid: 2, low: 1 } as any)[p.priority] ? a : p
                    ).priority : null
                    return (
                        <div key={i} style={{
                            aspectRatio: "1 / 1",
                            display: "flex", flexDirection: "column",
                            alignItems: "center", justifyContent: "flex-start",
                            padding: 3, borderRadius: 4,
                            background: has ? `${priorityColor(topPri!)}15` : "transparent",
                            border: has ? `1px solid ${priorityColor(topPri!)}40` : "1px solid transparent",
                            color: c.day ? C.textSecondary : "transparent",
                            fontSize: 10, fontFamily: FONT_MONO,
                        }}>
                            <div>{c.day || ""}</div>
                            {has && (
                                <div style={{
                                    color: priorityColor(topPri!),
                                    fontSize: 9, fontWeight: 800, marginTop: 2,
                                }}>
                                    {acts!.length}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

/* Styles */
const pageStyle: React.CSSProperties = {
    width: "100%", minHeight: "100%",
    background: C.bgPage, padding: 24, fontFamily: FONT,
    boxSizing: "border-box",
}
const filterBtnStyle: React.CSSProperties = {
    padding: "6px 14px", borderRadius: 8, cursor: "pointer",
    fontSize: 12, fontWeight: 700, fontFamily: FONT,
}
const itemStyle: React.CSSProperties = {
    background: C.bgCard, borderRadius: 8,
    border: `1px solid ${C.border}`,
    padding: 12,
}
const emptyStyle: React.CSSProperties = {
    padding: 28, borderRadius: 10, textAlign: "center",
    background: C.bgCard, border: `1px solid ${C.border}`,
    color: C.textSecondary, fontSize: 13, fontFamily: FONT,
}

/* Property controls */
const _DEFAULT_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/estate_action_log.json"

EstateActionLog.defaultProps = {
    apiUrl: _DEFAULT_URL,
    showCalendar: true,
    monthsAhead: 2,
}

addPropertyControls(EstateActionLog, {
    apiUrl: {
        type: ControlType.String, title: "Action Log JSON URL",
        defaultValue: _DEFAULT_URL,
        description: "GitHub raw URL — 보통 기본값 그대로 사용.",
    },
    showCalendar: {
        type: ControlType.Boolean, title: "캘린더 표시",
        defaultValue: true,
    },
    monthsAhead: {
        type: ControlType.Number, title: "캘린더 개월 수",
        defaultValue: 2, min: 1, max: 6, step: 1,
    },
})

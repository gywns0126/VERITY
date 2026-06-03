import { addPropertyControls, ControlType } from "framer"
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"

/**
 * VERITY — User Action Bell (TIDE 디자인 풀카피, 2026-05-26).
 *
 * TIDE 톤 흡수: flat minimal, Lora serif heading, sep borderBottom 구분선.
 * 브랜드 TIDE 초록 #7fffa0 (PM 5/30 결단 — 라임 #B5FF17 폐기. 5/25 라임 차환 결정 번복).
 *
 * 기능 보존 (VERITY 자기 자산):
 *   - Supabase REST + JWT + RPC (action_queue_complete / action_queue_skip)
 *   - 시간 버킷팅 (today / tomorrow / later) — KST 자정 boundary
 *   - actor='user' 필터 (013_action_queue_actor)
 *   - 완료 / 스킵 / 경로 복사 버튼
 */

/* ─────────────────────────────────────────────────────────────
 * ◆ TIDE DESIGN TOKENS (풀카피) ◆ accent 만 VERITY 라임
 * ────────────────────────────────────────────────────────────── */
const T = {
    bgPage: "#0a0a0a",
    bgCard: "#141414",
    bgElevated: "#1a1a1a",
    border: "rgba(255,255,255,0.06)",
    borderStrong: "rgba(255,255,255,0.12)",
    text: "#ffffff",
    muted: "#6b7280",
    accent: "#7fffa0",
    accentDim: "#7A9F2E",
    accentSoft: "rgba(127, 255, 160,0.08)",
    danger: "#ff5a5a",
    warn: "#ffa05a",
    info: "#5BA9FF",
    sep: "rgba(255,255,255,0.05)",
}

const FONT = "'Pretendard', Inter, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', Menlo, monospace"
const FONT_SERIF = "Lora, serif"

type Category = "framer_paste" | "supabase_migration" | "verification" | "monitoring" | "misc"
type Priority = "p0" | "p1" | "p2"
type Status = "pending" | "in_progress" | "done" | "skipped"

interface QueueRow {
    id: string
    title: string
    detail?: string | null
    category: Category
    priority: Priority
    commit_hash?: string | null
    component_path?: string | null
    code_snippet?: string | null
    due_at?: string | null
    status: Status
    created_at: string
    completed_at?: string | null
    user_notes?: string | null
}

const CATEGORY_LABEL: Record<Category, string> = {
    framer_paste:       "FRAMER",
    supabase_migration: "SUPABASE",
    verification:       "VERIFY",
    monitoring:         "MONITOR",
    misc:               "MISC",
}

const PRIORITY_COLOR: Record<Priority, string> = {
    p0: T.danger,
    p1: T.warn,
    p2: T.muted,
}

function BellIcon({ color, size = 22 }: { color: string; size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
            <path
                d="M12 3v1.5M6.5 9a5.5 5.5 0 0 1 11 0c0 4 1.5 5 2 6h-15c.5-1 2-2 2-6Z M10 19a2 2 0 0 0 4 0"
                stroke={color}
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    )
}

function getJwt(): string | null {
    if (typeof window === "undefined") return null
    try {
        const raw = localStorage.getItem("verity_supabase_session")
        if (!raw) return null
        const s = JSON.parse(raw)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return null
        return s.access_token || null
    } catch {
        return null
    }
}

/** KST(UTC+9) 자정 — 오늘/내일 boundary */
function kstDayBoundaries(): { todayEnd: number; tomorrowEnd: number } {
    const now = new Date()
    const utcMs = now.getTime()
    const kstMs = utcMs + 9 * 3600_000
    const kstMidnightUtc = Math.floor(kstMs / 86400_000) * 86400_000 - 9 * 3600_000
    return {
        todayEnd: kstMidnightUtc + 86400_000,
        tomorrowEnd: kstMidnightUtc + 2 * 86400_000,
    }
}

type Bucket = "today" | "tomorrow" | "later"

function bucketOf(due: string | null | undefined): Bucket {
    const { todayEnd, tomorrowEnd } = kstDayBoundaries()
    if (!due) return "today"
    const t = new Date(due).getTime()
    if (Number.isNaN(t)) return "today"
    if (t <= todayEnd) return "today"
    if (t <= tomorrowEnd) return "tomorrow"
    return "later"
}

function dueShort(due: string | null | undefined): string {
    if (!due) return ""
    const d = new Date(due)
    const t = d.getTime()
    if (Number.isNaN(t)) return ""
    const now = Date.now()
    const days = Math.round((t - now) / 86400_000)
    const hhmm = d.toLocaleTimeString("en-GB", {
        timeZone: "Asia/Seoul",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    })
    const hasTime = hhmm !== "00:00"
    if (days < 0) return `⚠ ${-days}d ago`
    if (days === 0) return hasTime ? `Today ${hhmm}` : "Today"
    if (days === 1) return hasTime ? `Tmrw ${hhmm}` : "Tmrw"
    return `+${days}d`
}

async function copyToClipboard(text: string): Promise<boolean> {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
        try {
            await navigator.clipboard.writeText(text)
            return true
        } catch {
            /* fallthrough */
        }
    }
    return false
}

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    refreshIntervalSec: number
    maxRows: number
    popupDirection: "top" | "bottom"
    popupAlign: "left" | "right"
}

export default function UserActionBell(props: Props) {
    const {
        supabaseUrl = "",
        supabaseAnonKey = "",
        refreshIntervalSec = 60,
        maxRows = 12,
        popupDirection = "top",
        popupAlign = "right",
    } = props

    const [rows, setRows] = useState<QueueRow[]>([])
    const [open, setOpen] = useState(false)
    const [error, setError] = useState<string>("")
    const [busy, setBusy] = useState<string | null>(null)
    const [copied, setCopied] = useState<string | null>(null)
    const closeTimer = useRef<number | null>(null)

    const fetchRows = useCallback(async () => {
        if (!supabaseUrl || !supabaseAnonKey) {
            setError("Supabase 설정 누락")
            return
        }
        const jwt = getJwt()
        if (!jwt) {
            setError("로그인 필요")
            return
        }
        setError("")
        try {
            const url =
                `${supabaseUrl}/rest/v1/user_action_queue` +
                `?select=*&status=eq.pending&actor=eq.user` +
                `&order=priority.asc,due_at.asc.nullslast,created_at.desc&limit=100`
            const r = await fetch(url, {
                headers: { apikey: supabaseAnonKey, Authorization: `Bearer ${jwt}` },
            })
            if (!r.ok) {
                const body = await r.text().catch(() => "")
                throw new Error(`HTTP ${r.status}: ${body.slice(0, 120)}`)
            }
            const data: QueueRow[] = await r.json()
            setRows(data)
        } catch (e: any) {
            setError(e?.message || "조회 실패")
        }
    }, [supabaseUrl, supabaseAnonKey])

    useEffect(() => {
        fetchRows()
        const sec = Math.max(15, Number(refreshIntervalSec) || 60)
        const id = globalThis.setInterval(fetchRows, sec * 1000)
        return () => globalThis.clearInterval(id)
    }, [fetchRows, refreshIntervalSec])

    // self-heartbeat
    useEffect(() => {
        if (!supabaseUrl || !supabaseAnonKey) return
        const jwt = getJwt()
        if (!jwt) return
        fetch(`${supabaseUrl}/rest/v1/rpc/action_queue_heartbeat`, {
            method: "POST",
            headers: {
                apikey: supabaseAnonKey,
                Authorization: `Bearer ${jwt}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ p_component_path: "framer-components/UserActionBell.tsx" }),
        }).catch(() => {})
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    const buckets = useMemo(() => {
        const today: QueueRow[] = []
        const tomorrow: QueueRow[] = []
        const later: QueueRow[] = []
        for (const r of rows) {
            const b = bucketOf(r.due_at)
            if (b === "today") today.push(r)
            else if (b === "tomorrow") tomorrow.push(r)
            else later.push(r)
        }
        return { today, tomorrow, later }
    }, [rows])

    const todayCount = buckets.today.length
    const todayP0 = buckets.today.filter((r) => r.priority === "p0").length
    const hasPending = todayCount > 0
    const hasError = !!error

    const callRpc = async (action: "complete" | "skip", row: QueueRow) => {
        const jwt = getJwt()
        if (!jwt) {
            setError("세션 만료")
            return
        }
        setBusy(row.id)
        try {
            const fn = action === "complete" ? "action_queue_complete" : "action_queue_skip"
            const r = await fetch(`${supabaseUrl}/rest/v1/rpc/${fn}`, {
                method: "POST",
                headers: {
                    apikey: supabaseAnonKey,
                    Authorization: `Bearer ${jwt}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ target_id: row.id, note: null }),
            })
            if (!r.ok) {
                const body = await r.text().catch(() => "")
                throw new Error(`RPC ${r.status}: ${body.slice(0, 120)}`)
            }
            setRows((cur) => cur.filter((x) => x.id !== row.id))
        } catch (e: any) {
            setError(e?.message || `${action} 실패`)
        } finally {
            setBusy(null)
        }
    }

    const cancelClose = () => {
        if (closeTimer.current !== null) {
            globalThis.clearTimeout(closeTimer.current)
            closeTimer.current = null
        }
    }
    const scheduleClose = () => {
        cancelClose()
        closeTimer.current = globalThis.setTimeout(() => setOpen(false), 220) as unknown as number
    }

    const onCopyRow = async (r: QueueRow) => {
        const snip = r.code_snippet || r.component_path || ""
        if (!snip) return
        const ok = await copyToClipboard(snip)
        if (ok) {
            setCopied(r.id)
            globalThis.setTimeout(() => setCopied((c) => (c === r.id ? null : c)), 1500)
        }
    }

    /* ── TIDE 풀카피 styles ── */
    const fabIconColor = hasError ? T.danger : todayP0 > 0 ? T.danger : hasPending ? T.accent : T.muted

    const rootWrap: React.CSSProperties = {
        position: "relative",
        display: "inline-block",
        width: 52,
        height: 52,
        overflow: "visible",
        fontFamily: FONT,
    }

    const fab: React.CSSProperties = {
        position: "relative",
        width: 52,
        height: 52,
        borderRadius: "50%",
        background: T.bgCard,
        color: fabIconColor,
        border: "none",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        cursor: "pointer",
        boxShadow: "0 4px 14px rgba(0,0,0,0.4)",
        transition: "transform 180ms ease, background 180ms ease, box-shadow 180ms ease",
        userSelect: "none",
    }

    const showNumberBadge = todayCount >= 10
    const badge: React.CSSProperties = showNumberBadge
        ? {
            position: "absolute",
            top: -2,
            right: -2,
            minWidth: 18,
            height: 18,
            padding: "0 5px",
            borderRadius: 999,
            background: todayP0 > 0 ? T.danger : T.accent,
            color: T.bgPage,
            fontSize: 10,
            fontWeight: 800,
            fontFamily: FONT,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: `0 0 0 2px ${T.bgPage}`,
            boxSizing: "border-box",
            lineHeight: 1,
        }
        : {
            position: "absolute",
            top: 4,
            right: 4,
            width: 8,
            height: 8,
            borderRadius: 999,
            background: todayP0 > 0 ? T.danger : T.accent,
            boxShadow: `0 0 0 2px ${T.bgCard}, 0 0 6px ${todayP0 > 0 ? "rgba(255,90,90,0.5)" : "rgba(127, 255, 160,0.5)"}`,
        }

    const panel: React.CSSProperties = {
        position: "absolute",
        width: 380,
        maxWidth: "calc(100vw - 32px)",
        maxHeight: "min(560px, 100vh - 100px)",
        background: T.bgCard,
        border: `1px solid ${T.border}`,
        borderRadius: 14,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        zIndex: 9999,
        boxShadow: "0 18px 50px rgba(0,0,0,0.7)",
        pointerEvents: "auto",
        fontFamily: FONT,
    }
    if (popupDirection === "top") panel.bottom = 64
    else panel.top = 64
    if (popupAlign === "right") panel.right = 0
    else panel.left = 0

    const hasAnyRow = buckets.today.length + buckets.tomorrow.length + buckets.later.length > 0

    return (
        <div style={rootWrap} onMouseEnter={cancelClose} onMouseLeave={scheduleClose}>
            <div
                style={fab}
                onClick={() => setOpen((v) => !v)}
                onMouseEnter={() => {
                    cancelClose()
                    setOpen(true)
                }}
                role="button"
                aria-label={`사용자 작업 큐 — 오늘 ${todayCount}개`}
                title={
                    hasError ? `에러: ${error}` :
                    !hasAnyRow ? "오늘 할 일 없음" :
                    `오늘 ${todayCount} · 내일 ${buckets.tomorrow.length} · 이후 ${buckets.later.length}`
                }
            >
                <BellIcon color={fabIconColor} />
                {hasPending && (
                    showNumberBadge
                        ? <span style={badge}>{todayCount > 99 ? "99+" : todayCount}</span>
                        : <span style={badge} />
                )}
            </div>

            {open && (
                <div style={panel}>
                    {/* Header */}
                    <div style={{
                        padding: "16px 20px 14px",
                        borderBottom: `1px solid ${T.sep}`,
                        display: "flex",
                        alignItems: "baseline",
                        gap: 10,
                    }}>
                        <div style={{
                            fontFamily: FONT_SERIF,
                            fontSize: 17,
                            fontWeight: 600,
                            color: T.text,
                            letterSpacing: "-0.01em",
                        }}>
                            Action Queue
                        </div>
                        <div style={{ flex: 1 }} />
                        <div style={{
                            fontSize: 10,
                            color: hasPending ? T.accent : T.muted,
                            fontWeight: 600,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                        }}>
                            {todayCount} pending
                        </div>
                        <button
                            onClick={() => fetchRows()}
                            style={{
                                background: "transparent",
                                border: "none",
                                color: T.muted,
                                padding: "2px 6px",
                                borderRadius: 4,
                                fontSize: 12,
                                fontFamily: FONT,
                                cursor: "pointer",
                                letterSpacing: "0.05em",
                            }}
                            title="새로고침"
                        >
                            ↻
                        </button>
                    </div>

                    {/* Error */}
                    {error && (
                        <div style={{
                            padding: "8px 20px",
                            borderBottom: `1px solid ${T.sep}`,
                            color: T.danger,
                            fontSize: 11,
                            lineHeight: 1.4,
                        }}>
                            ⚠ {error}
                        </div>
                    )}

                    {/* Body */}
                    <div style={{ overflowY: "auto", flex: 1 }}>
                        {!error && !hasAnyRow && (
                            <div style={{
                                padding: "32px 20px",
                                color: T.muted,
                                textAlign: "center",
                                fontSize: 12,
                                letterSpacing: 0.3,
                            }}>
                                action 0건
                            </div>
                        )}

                        {buckets.today.length > 0 && (
                            <BucketSection
                                label="TODAY"
                                rows={buckets.today.slice(0, maxRows)}
                                busy={busy}
                                copied={copied}
                                onComplete={(r) => callRpc("complete", r)}
                                onSkip={(r) => callRpc("skip", r)}
                                onCopy={onCopyRow}
                            />
                        )}

                        {buckets.tomorrow.length > 0 && (
                            <BucketSection
                                label="TOMORROW"
                                rows={buckets.tomorrow.slice(0, 5)}
                                busy={busy}
                                copied={copied}
                                preview
                            />
                        )}

                        {buckets.later.length > 0 && (
                            <div style={{
                                padding: "10px 20px 14px",
                                borderTop: `1px solid ${T.sep}`,
                                color: T.muted,
                                fontSize: 11,
                                letterSpacing: 0.3,
                            }}>
                                + {buckets.later.length} later
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}

interface BucketSectionProps {
    label: string
    rows: QueueRow[]
    busy: string | null
    copied: string | null
    preview?: boolean
    onComplete?: (r: QueueRow) => void
    onSkip?: (r: QueueRow) => void
    onCopy?: (r: QueueRow) => void
}

function BucketSection(props: BucketSectionProps) {
    return (
        <div>
            <div style={{
                padding: "12px 20px 6px",
                fontSize: 9,
                fontWeight: 700,
                color: T.muted,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                fontFamily: FONT,
            }}>
                {props.label} · {props.rows.length}
            </div>
            {props.rows.map((r, i) => (
                <ActionRow
                    key={r.id}
                    row={r}
                    isLast={i === props.rows.length - 1}
                    busy={props.busy === r.id}
                    copied={props.copied === r.id}
                    preview={!!props.preview}
                    onComplete={props.onComplete}
                    onSkip={props.onSkip}
                    onCopy={props.onCopy}
                />
            ))}
        </div>
    )
}

interface ActionRowProps {
    row: QueueRow
    isLast: boolean
    busy: boolean
    copied: boolean
    preview: boolean
    onComplete?: (r: QueueRow) => void
    onSkip?: (r: QueueRow) => void
    onCopy?: (r: QueueRow) => void
}

function ActionRow(p: ActionRowProps) {
    const r = p.row
    const catLabel = CATEGORY_LABEL[r.category] || r.category.toUpperCase()
    const barColor = PRIORITY_COLOR[r.priority] || T.muted
    const due = dueShort(r.due_at)
    const dateStr = r.created_at ? r.created_at.slice(5, 10).replace("-", "/") : ""
    const snippet = r.code_snippet || r.component_path || ""

    return (
        <div style={{
            position: "relative",
            padding: "14px 20px 14px 22px",
            borderBottom: p.isLast ? "none" : `1px solid ${T.sep}`,
            opacity: p.preview ? 0.7 : 1,
        }}>
            <div style={{
                position: "absolute",
                left: 0,
                top: 14,
                bottom: 14,
                width: 3,
                background: barColor,
                borderRadius: 0,
            }} />

            <div style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 4,
            }}>
                <span style={{
                    fontSize: 9,
                    fontWeight: 700,
                    color: barColor,
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                }}>
                    {r.priority.toUpperCase()} · {catLabel}
                </span>
                <span style={{ flex: 1 }} />
                {due && (
                    <span style={{
                        fontSize: 10,
                        color: due.startsWith("⚠") ? T.danger : T.muted,
                        fontWeight: 600,
                    }}>
                        {due}
                    </span>
                )}
                <span style={{
                    fontSize: 10,
                    color: T.muted,
                    fontVariantNumeric: "tabular-nums",
                }}>
                    {dateStr}
                </span>
            </div>

            <div style={{
                color: T.text,
                fontWeight: 500,
                fontSize: 13,
                lineHeight: 1.45,
            }}>
                {r.title}
            </div>

            {r.detail && (
                <div style={{
                    color: T.muted,
                    fontSize: 11,
                    marginTop: 5,
                    lineHeight: 1.5,
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                }}>
                    {r.detail.length > 160 ? r.detail.slice(0, 160) + "…" : r.detail}
                </div>
            )}

            {r.component_path && (
                <div style={{
                    fontSize: 10,
                    fontFamily: FONT_MONO,
                    color: T.muted,
                    marginTop: 5,
                    wordBreak: "break-all",
                    opacity: 0.7,
                }}>
                    {r.component_path}
                </div>
            )}

            {!p.preview && (
                <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                    <button
                        onClick={() => p.onComplete && p.onComplete(r)}
                        disabled={p.busy}
                        style={{
                            background: "transparent",
                            color: T.accent,
                            border: `1px solid ${T.accent}`,
                            padding: "4px 10px",
                            borderRadius: 4,
                            fontSize: 10,
                            fontWeight: 600,
                            fontFamily: FONT,
                            cursor: p.busy ? "wait" : "pointer",
                            letterSpacing: "0.05em",
                            textTransform: "uppercase",
                        }}
                    >
                        Complete
                    </button>
                    <button
                        onClick={() => p.onSkip && p.onSkip(r)}
                        disabled={p.busy}
                        style={{
                            background: "transparent",
                            color: T.muted,
                            border: `1px solid ${T.border}`,
                            padding: "4px 10px",
                            borderRadius: 4,
                            fontSize: 10,
                            fontWeight: 600,
                            fontFamily: FONT,
                            cursor: p.busy ? "wait" : "pointer",
                            letterSpacing: "0.05em",
                            textTransform: "uppercase",
                        }}
                    >
                        Skip
                    </button>
                    {snippet && (
                        <button
                            onClick={() => p.onCopy && p.onCopy(r)}
                            style={{
                                background: "transparent",
                                color: p.copied ? T.accent : T.muted,
                                border: `1px solid ${T.border}`,
                                padding: "4px 10px",
                                borderRadius: 4,
                                fontSize: 10,
                                fontWeight: 600,
                                fontFamily: FONT,
                                cursor: "pointer",
                                letterSpacing: "0.05em",
                                textTransform: "uppercase",
                            }}
                        >
                            {p.copied ? "Copied" : "Copy"}
                        </button>
                    )}
                </div>
            )}
        </div>
    )
}

UserActionBell.defaultProps = {
    supabaseUrl: "",
    supabaseAnonKey: "",
    refreshIntervalSec: 60,
    maxRows: 12,
    popupDirection: "top",
    popupAlign: "right",
}

addPropertyControls(UserActionBell, {
    supabaseUrl: {
        title: "Supabase URL",
        type: ControlType.String,
        defaultValue: "",
        placeholder: "https://xxxx.supabase.co",
    },
    supabaseAnonKey: {
        title: "Supabase Anon Key",
        type: ControlType.String,
        defaultValue: "",
        placeholder: "eyJ...",
    },
    refreshIntervalSec: {
        title: "새로고침 (초)",
        type: ControlType.Number,
        defaultValue: 60,
        min: 15,
        max: 600,
        step: 15,
    },
    maxRows: {
        title: "Today 최대",
        type: ControlType.Number,
        defaultValue: 12,
        min: 3,
        max: 30,
        step: 1,
    },
    popupDirection: {
        title: "Popup 방향",
        type: ControlType.Enum,
        options: ["top", "bottom"],
        optionTitles: ["위쪽", "아래쪽"],
        defaultValue: "top",
    },
    popupAlign: {
        title: "Popup 정렬",
        type: ControlType.Enum,
        options: ["left", "right"],
        optionTitles: ["왼쪽", "오른쪽"],
        defaultValue: "right",
    },
})

import { addPropertyControls, ControlType } from "framer"
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"

/**
 * VERITY — User Action Bell (FAB + 빨간 카운트 배지)
 *
 * 카카오톡식 알림 패턴: 우하단 floating 56x56 (Verity 챗과 동일 사이즈), 빨간 점에 오늘 N개.
 * 호버 또는 클릭하면 패널 펼쳐서:
 *   - 오늘 미완료 액션 리스트 (✓ 완료 / ⊘ 스킵 / 📋 경로 복사)
 *   - 내일 / 모레 이후 preview (개수 + 제목 일부)
 *
 * 위치는 Framer 에서 직접 배치 (rootWrap 은 inline-block, popup 은 FAB 기준 absolute).
 * dockBottom/dockRight 폐기 (2026-05-04, feedback_no_hardcode_position 룰).
 *
 * UserActionQueueCard.tsx 와 동일한 Supabase RLS·RPC·heartbeat 사용.
 * Today/Tomorrow boundary = KST 자정.
 */

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
    success: "#22C55E",
    warn: "#F59E0B",
    danger: "#EF4444",
    info: "#5BA9FF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"

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

const CATEGORY_META: Record<Category, { label: string; color: string; emoji: string }> = {
    framer_paste:       { label: "Framer paste",   color: C.accent,  emoji: "📋" },
    supabase_migration: { label: "Supabase 마이그", color: C.info,    emoji: "🗄️" },
    verification:       { label: "검증",            color: C.warn,    emoji: "🔍" },
    monitoring:         { label: "모니터링",         color: C.info,    emoji: "📊" },
    misc:               { label: "기타",            color: C.textSecondary, emoji: "·" },
}

const PRIORITY_META: Record<Priority, { color: string }> = {
    p0: { color: C.danger },
    p1: { color: C.warn },
    p2: { color: C.textSecondary },
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

/** KST(UTC+9) 기준 자정 — 오늘/내일 boundary 산출용 */
function kstDayBoundaries(): { todayEnd: number; tomorrowEnd: number } {
    const now = new Date()
    // KST = UTC+9. KST 자정은 UTC 15:00 전날.
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
    if (!due) return "today" // due 없는 pending = 오늘 처리
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
    if (days < 0) return `⚠ ${-days}일 지남`
    if (days === 0) return hasTime ? `오늘 ${hhmm}` : "오늘"
    if (days === 1) return hasTime ? `내일 ${hhmm}` : "내일"
    return `${days}일 후`
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
}

export default function UserActionBell(props: Props) {
    const {
        supabaseUrl = "",
        supabaseAnonKey = "",
        refreshIntervalSec = 60,
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
            // actor='user' 만 노출 — Claude 가 끝내는 일정 마일스톤은 invisible (013_action_queue_actor)
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

    // 자가-종결 heartbeat
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
        }).catch(() => {
            /* swallow */
        })
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

    // hover open / leave delayed close
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

    /* ── styles ── */
    /* 위치는 Framer 에서 직접 배치. rootWrap 은 FAB 사이즈 (52x52) inline-block.
     * popup overflow 는 visible 로 허용 (FAB 위쪽으로 확장). */
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
        background: todayP0 > 0 ? C.danger : todayCount > 0 ? C.accent : C.bgElevated,
        color: todayCount > 0 ? "#000" : C.textSecondary,
        border: todayCount === 0 ? `1px solid ${C.borderStrong}` : "none",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        cursor: "pointer",
        boxShadow:
            todayP0 > 0
                ? "0 4px 20px rgba(239,68,68,0.45)"
                : todayCount > 0
                ? "0 4px 20px rgba(181,255,25,0.3)"
                : "0 4px 16px rgba(0,0,0,0.4)",
        transition: "transform 0.2s, background 0.2s",
    }

    const badge: React.CSSProperties = {
        position: "absolute",
        top: -4,
        right: -4,
        minWidth: 20,
        height: 20,
        padding: "0 6px",
        borderRadius: 999,
        background: C.danger,
        color: "#fff",
        fontSize: 11,
        fontWeight: 800,
        fontFamily: FONT,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "0 0 0 2px #0E0F11, 0 2px 6px rgba(239,68,68,0.5)",
        boxSizing: "border-box",
        lineHeight: 1,
    }

    /* popup 은 FAB 위쪽으로 확장 (FAB 가 페이지 하단에 배치된다는 가정).
     * FAB 가 다른 위치에 있어도 popup 은 항상 위쪽-오른쪽 정렬.
     * Framer 에서 FAB 를 상단에 배치 시 popup overflow 발생 가능 — 운영자 책임. */
    const panelWrap: React.CSSProperties = {
        position: "absolute",
        bottom: 64,
        right: 0,
        width: 360,
        maxWidth: "calc(100vw - 32px)",
        maxHeight: "min(560px, 100vh - 96px)",
        background: C.bgElevated,
        border: `1px solid ${C.border}`,
        borderRadius: 14,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        zIndex: 3,
        boxShadow: "0 12px 40px rgba(0,0,0,0.6)",
        pointerEvents: "auto",
        fontFamily: FONT,
    }

    const headerRow: React.CSSProperties = {
        padding: "14px 16px 10px",
        borderBottom: `1px solid ${C.border}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
    }

    return (
        <div
            style={rootWrap}
            onMouseEnter={cancelClose}
            onMouseLeave={scheduleClose}
        >
            <div
                onClick={() => setOpen((v) => !v)}
                onMouseEnter={(e) => {
                    cancelClose()
                    setOpen(true)
                    ;(e.currentTarget as HTMLElement).style.transform = "scale(1.08)"
                }}
                onMouseLeave={(e) => {
                    ;(e.currentTarget as HTMLElement).style.transform = "scale(1)"
                }}
                style={fab}
                role="button"
                aria-label={`사용자 작업 큐 — 오늘 ${todayCount}개`}
            >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
                    <path
                        d="M12 22a2.5 2.5 0 0 0 2.45-2H9.55A2.5 2.5 0 0 0 12 22zm6.5-6V11a6.5 6.5 0 1 0-13 0v5l-2 2v1h17v-1l-2-2z"
                        fill="currentColor"
                    />
                </svg>
                {todayCount > 0 && (
                    <span style={badge}>{todayCount > 99 ? "99+" : todayCount}</span>
                )}
            </div>

            {open && (
                <div style={panelWrap}>
                    <div style={headerRow}>
                        <div>
                            <div
                                style={{
                                    fontSize: 13,
                                    fontWeight: 800,
                                    color: C.accent,
                                    letterSpacing: "-0.01em",
                                }}
                            >
                                🛠 오늘 해야 할 것 ({todayCount})
                            </div>
                            <div style={{ fontSize: 10, color: C.textTertiary, marginTop: 2 }}>
                                Claude Code 가 추가 · 호버/클릭으로 펼침
                            </div>
                        </div>
                        <button
                            onClick={() => fetchRows()}
                            style={{
                                background: "transparent",
                                border: `1px solid ${C.border}`,
                                color: C.textSecondary,
                                padding: "4px 10px",
                                borderRadius: 6,
                                fontSize: 11,
                                fontFamily: FONT,
                                cursor: "pointer",
                            }}
                        >
                            ↻
                        </button>
                    </div>

                    {error && (
                        <div
                            style={{
                                background: `${C.danger}15`,
                                color: C.danger,
                                fontSize: 11,
                                padding: "6px 16px",
                                borderBottom: `1px solid ${C.border}`,
                            }}
                        >
                            ⚠ {error}
                        </div>
                    )}

                    <div
                        style={{
                            overflowY: "auto",
                            flex: 1,
                            padding: "4px 16px 12px",
                        }}
                    >
                        {buckets.today.length === 0 && !error && (
                            <div
                                style={{
                                    color: C.textTertiary,
                                    fontSize: 12,
                                    padding: "20px 4px",
                                    textAlign: "center",
                                }}
                            >
                                오늘 할 일 없음 ✓
                            </div>
                        )}

                        {buckets.today.map((row) => {
                            const cat = CATEGORY_META[row.category]
                            const pri = PRIORITY_META[row.priority]
                            const due = dueShort(row.due_at)
                            const isBusy = busy === row.id
                            const isCopied = copied === row.id
                            const snippet = row.code_snippet || row.component_path || ""
                            return (
                                <div
                                    key={row.id}
                                    style={{
                                        padding: "10px 0",
                                        borderBottom: `1px solid ${C.border}`,
                                    }}
                                >
                                    <div
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            gap: 6,
                                            marginBottom: 4,
                                            flexWrap: "wrap",
                                        }}
                                    >
                                        <span
                                            style={{
                                                background: pri.color,
                                                color: "#0E0F11",
                                                fontSize: 9,
                                                fontWeight: 800,
                                                padding: "2px 5px",
                                                borderRadius: 3,
                                                letterSpacing: "0.05em",
                                            }}
                                        >
                                            {row.priority.toUpperCase()}
                                        </span>
                                        <span style={{ color: cat.color, fontSize: 10, fontWeight: 600 }}>
                                            {cat.emoji} {cat.label}
                                        </span>
                                        {due && (
                                            <span
                                                style={{
                                                    color: due.startsWith("⚠") ? C.danger : C.textTertiary,
                                                    fontSize: 10,
                                                    fontWeight: 600,
                                                }}
                                            >
                                                {due}
                                            </span>
                                        )}
                                    </div>
                                    <div
                                        style={{
                                            color: C.textPrimary,
                                            fontSize: 12,
                                            fontWeight: 700,
                                            marginBottom: row.detail ? 3 : 6,
                                            lineHeight: 1.4,
                                        }}
                                    >
                                        {row.title}
                                    </div>
                                    {row.detail && (
                                        <div
                                            style={{
                                                color: C.textSecondary,
                                                fontSize: 11,
                                                lineHeight: 1.45,
                                                marginBottom: 6,
                                                display: "-webkit-box",
                                                WebkitLineClamp: 2,
                                                WebkitBoxOrient: "vertical",
                                                overflow: "hidden",
                                            }}
                                        >
                                            {row.detail}
                                        </div>
                                    )}
                                    {row.component_path && (
                                        <div
                                            style={{
                                                fontSize: 10,
                                                fontFamily: FONT_MONO,
                                                color: C.textTertiary,
                                                marginBottom: 6,
                                                wordBreak: "break-all",
                                            }}
                                        >
                                            {row.component_path}
                                        </div>
                                    )}
                                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                        <button
                                            onClick={() => callRpc("complete", row)}
                                            disabled={isBusy}
                                            style={{
                                                background: C.success,
                                                color: "#0E0F11",
                                                border: "none",
                                                padding: "5px 12px",
                                                borderRadius: 5,
                                                fontSize: 11,
                                                fontWeight: 700,
                                                fontFamily: FONT,
                                                cursor: isBusy ? "wait" : "pointer",
                                                opacity: isBusy ? 0.5 : 1,
                                            }}
                                        >
                                            ✓ 완료
                                        </button>
                                        <button
                                            onClick={() => callRpc("skip", row)}
                                            disabled={isBusy}
                                            style={{
                                                background: "transparent",
                                                color: C.textTertiary,
                                                border: `1px solid ${C.borderStrong}`,
                                                padding: "5px 10px",
                                                borderRadius: 5,
                                                fontSize: 11,
                                                fontWeight: 600,
                                                fontFamily: FONT,
                                                cursor: isBusy ? "wait" : "pointer",
                                                opacity: isBusy ? 0.5 : 1,
                                            }}
                                        >
                                            ⊘ 스킵
                                        </button>
                                        {snippet && (
                                            <button
                                                onClick={async () => {
                                                    const ok = await copyToClipboard(snippet)
                                                    if (ok) {
                                                        setCopied(row.id)
                                                        globalThis.setTimeout(
                                                            () =>
                                                                setCopied((c) =>
                                                                    c === row.id ? null : c,
                                                                ),
                                                            1500,
                                                        )
                                                    }
                                                }}
                                                style={{
                                                    background: "transparent",
                                                    color: isCopied ? C.success : C.accent,
                                                    border: `1px solid ${isCopied ? C.success : C.border}`,
                                                    padding: "5px 10px",
                                                    borderRadius: 5,
                                                    fontSize: 11,
                                                    fontWeight: 600,
                                                    fontFamily: FONT,
                                                    cursor: "pointer",
                                                }}
                                            >
                                                {isCopied ? "✓ 복사됨" : "📋 경로"}
                                            </button>
                                        )}
                                    </div>
                                </div>
                            )
                        })}

                        {/* Tomorrow + later preview */}
                        {(buckets.tomorrow.length > 0 || buckets.later.length > 0) && (
                            <div
                                style={{
                                    marginTop: 10,
                                    paddingTop: 10,
                                    borderTop: `1px dashed ${C.borderStrong}`,
                                }}
                            >
                                <div
                                    style={{
                                        fontSize: 10,
                                        fontWeight: 700,
                                        color: C.textTertiary,
                                        letterSpacing: "0.05em",
                                        marginBottom: 6,
                                    }}
                                >
                                    예고
                                </div>
                                {buckets.tomorrow.length > 0 && (
                                    <div style={{ marginBottom: 6 }}>
                                        <div
                                            style={{
                                                fontSize: 11,
                                                color: C.textSecondary,
                                                marginBottom: 3,
                                            }}
                                        >
                                            📅 내일 {buckets.tomorrow.length}개
                                        </div>
                                        {buckets.tomorrow.slice(0, 3).map((r) => (
                                            <div
                                                key={r.id}
                                                style={{
                                                    fontSize: 11,
                                                    color: C.textTertiary,
                                                    paddingLeft: 14,
                                                    lineHeight: 1.5,
                                                    overflow: "hidden",
                                                    textOverflow: "ellipsis",
                                                    whiteSpace: "nowrap",
                                                }}
                                            >
                                                · {r.title}
                                            </div>
                                        ))}
                                        {buckets.tomorrow.length > 3 && (
                                            <div
                                                style={{
                                                    fontSize: 10,
                                                    color: C.textTertiary,
                                                    paddingLeft: 14,
                                                    fontStyle: "italic",
                                                }}
                                            >
                                                … 외 {buckets.tomorrow.length - 3}개
                                            </div>
                                        )}
                                    </div>
                                )}
                                {buckets.later.length > 0 && (
                                    <div
                                        style={{
                                            fontSize: 11,
                                            color: C.textSecondary,
                                        }}
                                    >
                                        📆 모레 이후 {buckets.later.length}개
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}

UserActionBell.defaultProps = {
    supabaseUrl: "",
    supabaseAnonKey: "",
    refreshIntervalSec: 60,
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
})

import { addPropertyControls, ControlType } from "framer"
import React, { useCallback, useEffect, useState } from "react"

/**
 * VERITY — User Action Queue Card
 *
 * Claude Code 가 supabase.user_action_queue 에 작업을 insert 하면 이 카드에 표시됨.
 * 사용자는 paste/적용 후 Done 버튼 클릭 → action_queue_complete RPC 호출 → status='done'.
 * 다음 Claude Code 세션은 status='pending' 만 조회하므로 "뭐 해야 했지?" 가 사라짐.
 *
 * 의존성:
 *   - supabase/migrations/008_profile_is_admin.sql + 009_user_action_queue.sql 적용
 *   - profiles.is_admin = TRUE (운영자 본인)
 *   - localStorage 의 verity_supabase_session (AuthPage 가 저장)
 *
 * Framer property:
 *   - supabaseUrl
 *   - supabaseAnonKey
 *   - refreshIntervalSec (default 60)
 *   - showCompleted (default false — done/skipped 도 표시할지)
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

const PRIORITY_META: Record<Priority, { color: string; weight: number }> = {
    p0: { color: C.danger, weight: 0 },
    p1: { color: C.warn, weight: 1 },
    p2: { color: C.textSecondary, weight: 2 },
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

/**
 * 자가-종결 heartbeat — 다른 Framer 컴포넌트도 useEffect 첫 마운트에 한 줄 호출.
 *
 * 사용 예 (다른 카드):
 *   useEffect(() => {
 *     fireQueueHeartbeat(supabaseUrl, supabaseAnonKey, "framer-components/StockDashboard.tsx")
 *   }, [])
 *
 * - admin 만 효과 발생 (is_caller_admin RPC 체크). 비-admin 은 silent no-op.
 * - 매칭 pending 태스크 없어도 안전 (0 update). 멱등.
 * - 네트워크 실패는 무시 (best-effort). 사용자 흐름에 영향 없음.
 */
export function fireQueueHeartbeat(
    supabaseUrl: string,
    supabaseAnonKey: string,
    componentPath: string,
): void {
    if (!supabaseUrl || !supabaseAnonKey || !componentPath) return
    const jwt = getJwt()
    if (!jwt) return
    fetch(`${supabaseUrl}/rest/v1/rpc/action_queue_heartbeat`, {
        method: "POST",
        headers: {
            apikey: supabaseAnonKey,
            Authorization: `Bearer ${jwt}`,
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ p_component_path: componentPath }),
    }).catch(() => {
        /* swallow — heartbeat is best-effort */
    })
}

function dueLabel(due: string | null | undefined): { text: string; color: string } | null {
    if (!due) return null
    const d = new Date(due)
    const t = d.getTime()
    const now = Date.now()
    const days = Math.round((t - now) / 86400000)
    const hhmm = d.toLocaleTimeString("en-GB", {
        timeZone: "Asia/Seoul",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    })
    const hasTime = hhmm !== "00:00"
    if (days < 0) return { text: `⚠ ${-days}일 지남`, color: C.danger }
    if (days === 0) return { text: hasTime ? `오늘 ${hhmm} KST` : "오늘 마감", color: C.warn }
    if (days === 1) return { text: hasTime ? `내일 ${hhmm} KST` : "내일", color: C.warn }
    if (days <= 2) return { text: `${days}일 후`, color: C.warn }
    return { text: `${days}일 후`, color: C.textTertiary }
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
    showCompleted: boolean
}

export default function UserActionQueueCard(props: Props) {
    const {
        supabaseUrl = "",
        supabaseAnonKey = "",
        refreshIntervalSec = 60,
        showCompleted = false,
    } = props

    const [rows, setRows] = useState<QueueRow[]>([])
    const [error, setError] = useState<string>("")
    const [loading, setLoading] = useState(false)
    const [busy, setBusy] = useState<string | null>(null) // RPC in-flight id
    const [filter, setFilter] = useState<"all" | Category>("all")
    const [copied, setCopied] = useState<string | null>(null)
    const [loadedAt, setLoadedAt] = useState<string>("")

    const fetchRows = useCallback(async () => {
        if (!supabaseUrl || !supabaseAnonKey) {
            setError("Supabase URL / anon key 미설정 — Framer property 확인")
            return
        }
        const jwt = getJwt()
        if (!jwt) {
            setError("로그인 필요 (verity_supabase_session 없음)")
            return
        }
        setLoading(true)
        setError("")
        try {
            const statusFilter = showCompleted ? "" : "&status=eq.pending"
            const url =
                `${supabaseUrl}/rest/v1/user_action_queue` +
                `?select=*${statusFilter}` +
                `&order=priority.asc,created_at.desc&limit=100`
            const r = await fetch(url, {
                headers: { apikey: supabaseAnonKey, Authorization: `Bearer ${jwt}` },
            })
            if (!r.ok) {
                const body = await r.text().catch(() => "")
                throw new Error(`HTTP ${r.status}: ${body.slice(0, 160)}`)
            }
            const data: QueueRow[] = await r.json()
            setRows(data)
            setLoadedAt(new Date().toLocaleTimeString("ko-KR"))
        } catch (e: any) {
            setError(e?.message || "조회 실패")
        } finally {
            setLoading(false)
        }
    }, [supabaseUrl, supabaseAnonKey, showCompleted])

    useEffect(() => {
        fetchRows()
        const sec = Math.max(15, Number(refreshIntervalSec) || 60)
        const id = globalThis.setInterval(fetchRows, sec * 1000)
        return () => globalThis.clearInterval(id)
    }, [fetchRows, refreshIntervalSec])

    // 자가-종결: 본 카드가 처음 렌더되면 자기 자신의 paste 태스크 자동 done
    useEffect(() => {
        fireQueueHeartbeat(supabaseUrl, supabaseAnonKey, "framer-components/UserActionQueueCard.tsx")
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    const callRpc = async (action: "complete" | "skip", row: QueueRow) => {
        const jwt = getJwt()
        if (!jwt) {
            setError("세션 만료 — 다시 로그인")
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
                throw new Error(`RPC ${r.status}: ${body.slice(0, 160)}`)
            }
            // Optimistic: pending 모드면 리스트에서 제거, showCompleted 면 새로고침
            if (!showCompleted) {
                setRows((cur) => cur.filter((x) => x.id !== row.id))
            } else {
                fetchRows()
            }
        } catch (e: any) {
            setError(e?.message || `${action} 실패`)
        } finally {
            setBusy(null)
        }
    }

    const filtered =
        filter === "all" ? rows : rows.filter((r) => r.category === filter)

    const counts: Record<string, number> = { all: rows.length }
    for (const r of rows) counts[r.category] = (counts[r.category] || 0) + 1

    const pendingP0 = rows.filter((r) => r.status === "pending" && r.priority === "p0").length
    const overall: "ok" | "warn" | "danger" =
        pendingP0 > 0 ? "danger" : rows.length === 0 ? "ok" : "warn"

    return (
        <div
            style={{
                width: "100%",
                background: C.bgCard,
                border: `1px solid ${overall === "danger" ? C.danger : C.border}`,
                borderRadius: 14,
                padding: "16px 18px",
                fontFamily: FONT,
                color: C.textPrimary,
                boxSizing: "border-box",
            }}
        >
            {/* 헤더 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <div>
                    <div style={{ fontSize: 14, fontWeight: 800, color: C.accent, letterSpacing: "-0.01em" }}>
                        🛠 사용자 작업 큐 ({rows.length})
                    </div>
                    <div style={{ fontSize: 10, color: C.textTertiary, marginTop: 2 }}>
                        Claude Code 가 추가 · 사용자가 Done 클릭 처리
                        {loadedAt && ` · ${loadedAt}`}
                    </div>
                </div>
                <button
                    onClick={fetchRows}
                    disabled={loading}
                    style={{
                        background: "transparent",
                        border: "none",
                        color: C.accent,
                        fontSize: 11,
                        fontFamily: FONT,
                        cursor: loading ? "wait" : "pointer",
                    }}
                >
                    {loading ? "갱신…" : "↻"}
                </button>
            </div>

            {/* 카테고리 필터 칩 */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
                {(["all", "framer_paste", "supabase_migration", "verification", "monitoring", "misc"] as const).map((cat) => {
                    const active = filter === cat
                    const count = counts[cat] ?? 0
                    if (cat !== "all" && count === 0) return null
                    const meta = cat === "all" ? null : CATEGORY_META[cat]
                    return (
                        <button
                            key={cat}
                            onClick={() => setFilter(cat as any)}
                            style={{
                                background: active ? C.accentSoft : "transparent",
                                border: `1px solid ${active ? C.accent : C.border}`,
                                color: active ? C.accent : C.textSecondary,
                                padding: "4px 10px",
                                borderRadius: 999,
                                fontSize: 11,
                                fontFamily: FONT,
                                cursor: "pointer",
                                fontWeight: 600,
                            }}
                        >
                            {meta ? `${meta.emoji} ${meta.label}` : "전체"} ({count})
                        </button>
                    )
                })}
            </div>

            {/* 에러 */}
            {error && (
                <div
                    style={{
                        background: `${C.danger}15`,
                        border: `1px solid ${C.danger}40`,
                        borderRadius: 8,
                        padding: "8px 12px",
                        marginBottom: 10,
                        color: C.danger,
                        fontSize: 12,
                    }}
                >
                    ⚠ {error}
                </div>
            )}

            {/* 리스트 */}
            {!loading && filtered.length === 0 && !error && (
                <div style={{ color: C.textTertiary, fontSize: 12, padding: "16px 4px", textAlign: "center" }}>
                    {rows.length === 0
                        ? "비어있음. Claude Code 가 다음 작업을 큐잉하면 여기 표시됩니다 ✓"
                        : "이 필터에 해당하는 작업이 없습니다"}
                </div>
            )}

            {filtered.map((row) => {
                const cat = CATEGORY_META[row.category]
                const pri = PRIORITY_META[row.priority]
                const due = dueLabel(row.due_at)
                const isBusy = busy === row.id
                const isCopied = copied === row.id
                const isDone = row.status === "done" || row.status === "skipped"
                const snippet = row.code_snippet || row.component_path || ""

                return (
                    <div
                        key={row.id}
                        style={{
                            padding: "12px 0",
                            borderBottom: `1px solid ${C.border}`,
                            opacity: isDone ? 0.45 : 1,
                        }}
                    >
                        {/* row 1: priority + category + title */}
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                            <span
                                style={{
                                    background: pri.color,
                                    color: "#0E0F11",
                                    fontSize: 10,
                                    fontWeight: 800,
                                    padding: "2px 6px",
                                    borderRadius: 4,
                                    letterSpacing: "0.05em",
                                }}
                            >
                                {row.priority.toUpperCase()}
                            </span>
                            <span
                                style={{
                                    color: cat.color,
                                    fontSize: 11,
                                    fontWeight: 600,
                                }}
                            >
                                {cat.emoji} {cat.label}
                            </span>
                            {due && (
                                <span style={{ color: due.color, fontSize: 11, fontWeight: 600 }}>
                                    {due.text}
                                </span>
                            )}
                            {isDone && (
                                <span
                                    style={{
                                        color: row.status === "done" ? C.success : C.textTertiary,
                                        fontSize: 11,
                                        fontWeight: 600,
                                    }}
                                >
                                    {row.status === "done" ? "✓ 완료" : "⊘ 스킵"}
                                </span>
                            )}
                        </div>

                        <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
                            {row.title}
                        </div>

                        {row.detail && (
                            <div style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.5, marginBottom: 6 }}>
                                {row.detail}
                            </div>
                        )}

                        {(row.commit_hash || row.component_path) && (
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 8,
                                    flexWrap: "wrap",
                                    fontSize: 11,
                                    fontFamily: FONT_MONO,
                                    color: C.textTertiary,
                                    marginBottom: 8,
                                }}
                            >
                                {row.commit_hash && (
                                    <span style={{ color: C.info }}>
                                        {row.commit_hash.slice(0, 7)}
                                    </span>
                                )}
                                {row.component_path && (
                                    <span>{row.component_path}</span>
                                )}
                            </div>
                        )}

                        {/* 액션 버튼 */}
                        {!isDone && (
                            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                <button
                                    onClick={() => callRpc("complete", row)}
                                    disabled={isBusy}
                                    style={{
                                        background: C.success,
                                        color: "#0E0F11",
                                        border: "none",
                                        padding: "6px 14px",
                                        borderRadius: 6,
                                        fontSize: 12,
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
                                        padding: "6px 12px",
                                        borderRadius: 6,
                                        fontSize: 12,
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
                                                setTimeout(() => setCopied((c) => (c === row.id ? null : c)), 1500)
                                            }
                                        }}
                                        style={{
                                            background: "transparent",
                                            color: isCopied ? C.success : C.accent,
                                            border: `1px solid ${isCopied ? C.success : C.border}`,
                                            padding: "6px 12px",
                                            borderRadius: 6,
                                            fontSize: 12,
                                            fontWeight: 600,
                                            fontFamily: FONT,
                                            cursor: "pointer",
                                        }}
                                    >
                                        {isCopied ? "✓ 복사됨" : "📋 경로 복사"}
                                    </button>
                                )}
                            </div>
                        )}

                        {row.user_notes && (
                            <div style={{ color: C.textTertiary, fontSize: 11, marginTop: 6, fontStyle: "italic" }}>
                                메모: {row.user_notes}
                            </div>
                        )}
                    </div>
                )
            })}

            {/* footer */}
            <div
                style={{
                    marginTop: 10,
                    color: C.textTertiary,
                    fontSize: 10,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                }}
            >
                <span>
                    추가: <code style={{ fontFamily: FONT_MONO }}>python scripts/action_queue.py add ...</code>
                </span>
                <span>{rows.length}건 (p0:{pendingP0})</span>
            </div>
        </div>
    )
}

UserActionQueueCard.defaultProps = {
    supabaseUrl: "",
    supabaseAnonKey: "",
    refreshIntervalSec: 60,
    showCompleted: false,
}

addPropertyControls(UserActionQueueCard, {
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
    showCompleted: {
        title: "완료/스킵도 표시",
        type: ControlType.Boolean,
        defaultValue: false,
    },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * AuditLogCard — 관리자 조치 로그 (AlphaNest 스타일).
 * 소스: /api/admin?type=audit_log (본인 JWT · is_admin · service_role). 누가·뭘·누구를·언제.
 * admin_audit_log 기록(제재·삭제·수정·글삭제)을 최신순 표시. 읽기 전용. 접근차단 = 페이지 AdminGate.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", down: "#3182f6",
    green: "#15c47e", greenS: "#eafaf3", amber: "#ff9500", amberS: "#fff6e9", vt: "#6c5ce7", vtS: "#f0edff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", grid: "#1e242c", up: "#f04452", down: "#5b9bff",
    green: "#34e08a", greenS: "#0f241c", amber: "#ff9500", amberS: "#2a2113", vt: "#a99bff", vtS: "#241f3a",
}
// CSS가 body[data-framer-theme]를 직접 따라간다. 테마 변경에 React 상태/Observer를 사용하지 않는다.
const ADMIN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-admin-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-admin-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: any = {}
for (const k of Object.keys(LIGHT)) C[k] = "var(--an-admin-" + k + ")"

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const SESSION_KEY = "verity_supabase_session"
const PAGE_SIZE = 20
const ACTIONS: Record<string, { t: string; c: string }> = {
    ban_user: { t: "회원 제재", c: "amber" }, unban_user: { t: "제재 해제", c: "green" },
    delete_user: { t: "회원 삭제", c: "up" }, update_profile: { t: "정보 수정", c: "vt" },
    delete_post: { t: "글 삭제", c: "up" }, hide_post: { t: "글 숨김", c: "amber" }, unhide_post: { t: "숨김 해제", c: "green" },
}

function loadToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return ""
        const s = JSON.parse(raw)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return ""
        return typeof s.access_token === "string" ? s.access_token : ""
    } catch (e) { return "" }
}
function fmtTs(iso: any): string {
    if (!iso) return "—"
    try {
        const d = new Date(String(iso))
        return `${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
    } catch (e) { return "—" }
}

interface Row { id: string; actor_email?: string; action?: string; target_type?: string; target_id?: string; detail?: any; created_at?: string }

const SAMPLE: Row[] = [
    { id: "a1", actor_email: "admin@alphanest.kr", action: "ban_user", target_type: "user", target_id: "u3", detail: { ban_reason: "반복 홍보글" }, created_at: "2026-07-16T09:12:00" },
    { id: "a2", actor_email: "admin@alphanest.kr", action: "delete_post", target_type: "thesis", target_id: "t2", detail: {}, created_at: "2026-07-16T09:10:00" },
    { id: "a3", actor_email: "admin@alphanest.kr", action: "update_profile", target_type: "user", target_id: "u1", detail: { status: "approved" }, created_at: "2026-07-16T08:55:00" },
]

interface Props { apiBase: string; dark: boolean }


/* 🚨 2026-07-27 /admin 최초 로딩 스켈레톤 — 카드들이 순차로 튀어나와 시선이 튐(PM 지적).
   각 카드가 자기 자리에 같은 골격을 먼저 깔아 레이아웃이 흔들리지 않게 한다. */
const ADM_SK_KEYS = "@keyframes admSk{0%{background-position:-400px 0}100%{background-position:400px 0}}"
function admSk(C: any, w: any, h: number, r: number = 6): CSSProperties {
    return {
        width: w, height: h, borderRadius: r, flexShrink: 0,
        background: `linear-gradient(90deg, ${C.grid || C.line} 25%, ${C.line} 37%, ${C.grid || C.line} 63%)`,
        backgroundSize: "800px 100%", animation: "admSk 1.4s ease-in-out infinite",
    }
}
function AdmSkeletonRows(props: { C: any; rows?: number }) {
    const C = props.C
    const n = props.rows || 4
    return (
        <div aria-busy="true">
            <style>{ADM_SK_KEYS}</style>
            {Array.from({ length: n }).map((_, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 0",
                    borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                    <div style={admSk(C, 30, 30, 10)} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={admSk(C, "38%", 12)} />
                        <div style={{ ...admSk(C, "24%", 10), marginTop: 6 }} />
                    </div>
                    <div style={admSk(C, 56, 22, 8)} />
                </div>
            ))}
        </div>
    )
}

export default function AuditLogCard(props: Props) {
    const apiBase = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [rows, setRows] = useState<Row[]>(onCanvas ? SAMPLE : [])
    const [total, setTotal] = useState<number | null>(onCanvas ? SAMPLE.length : null)
    const [page, setPage] = useState(0)
    const [openId, setOpenId] = useState("")
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState("")

    const load = useCallback((pageIndex: number) => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setLoading(true); setErr("")
        fetch(`${apiBase}/api/admin?type=audit_log&limit=${PAGE_SIZE}&offset=${pageIndex * PAGE_SIZE}`, { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
            .then((d) => { setRows(Array.isArray(d.items) ? d.items : []); setTotal(d.total != null ? d.total : null) })
            .catch((e) => setErr("불러오기 실패: " + (e && e.message ? e.message : e)))
            .finally(() => setLoading(false))
    }, [apiBase, onCanvas])

    useEffect(() => { load(0) }, [load])

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: 16, display: "flex", flexDirection: "column", gap: 12 }
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const colorOf = (k?: string) => (k === "up" ? C.up : k === "green" ? C.green : k === "amber" ? C.amber : C.vt)
    const bgOf = (k?: string) => (k === "up" ? C.grid : k === "green" ? C.greenS : k === "amber" ? C.amberS : C.vtS)
    const totalCount = total == null ? rows.length : total
    const pageCount = Math.max(1, Math.ceil(totalCount / PAGE_SIZE))
    const rangeStart = totalCount === 0 ? 0 : page * PAGE_SIZE + 1
    const rangeEnd = Math.min(totalCount, page * PAGE_SIZE + rows.length)
    const movePage = (next: number) => {
        if (loading || next < 0 || next >= pageCount) return
        setPage(next); setOpenId(""); load(next)
    }

    return (
        <div style={wrap}>
            <style>{ADMIN_PALETTE}</style>
            <div style={card}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                    <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px" }}>관리자 조치 로그</span>
                    <button style={{ marginLeft: "auto", border: "none", background: "transparent", fontSize: 11, color: C.faint, fontWeight: 700, cursor: "pointer" }} onClick={() => load(page)}>{loading ? "불러오는 중…" : "새로고침"}</button>
                </div>
                {err && <div style={{ fontSize: 12, color: C.up, fontWeight: 700, marginTop: 10 }}>{err}</div>}
            </div>

            <div style={card}>
                {loading ? (
                    <AdmSkeletonRows C={C} rows={4} />
                ) : rows.length === 0 && !loading ? (
                    <div style={{ fontSize: 13, color: C.faint, fontWeight: 600 }}>기록된 조치가 없어요</div>
                ) : rows.map((r, i) => {
                    const a = ACTIONS[r.action || ""] || { t: r.action || "조치", c: "vt" }
                    const opened = openId === r.id
                    const detailStr = r.detail && typeof r.detail === "object" ? Object.keys(r.detail).map((k) => `${k}: ${r.detail[k]}`).join(" · ") : ""
                    return (
                        <div key={r.id} role="button" tabIndex={0} aria-expanded={opened}
                            onClick={() => setOpenId(opened ? "" : r.id)}
                            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpenId(opened ? "" : r.id) } }}
                            style={{ display: "flex", gap: 10, alignItems: "flex-start", paddingTop: i === 0 ? 0 : 11, marginTop: i === 0 ? 0 : 11, borderTop: i === 0 ? "none" : `1px solid ${C.line}`, cursor: "pointer", outline: "none" }}>
                            <span style={{ flexShrink: 0, fontSize: 11, fontWeight: 800, color: colorOf(a.c), background: bgOf(a.c), borderRadius: 7, padding: "3px 9px" }}>{a.t}</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 12.5, fontWeight: 700, color: C.ink }}>
                                    {r.target_type === "user" ? "회원" : "글"} <span style={{ color: C.faint, fontWeight: 600 }}>{r.target_id ? r.target_id.slice(0, 8) : "—"}</span>
                                    <span style={{ float: "right", color: C.faint, transform: opened ? "rotate(90deg)" : "none" }}>›</span>
                                </div>
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 2 }}>{r.actor_email || "—"} · {fmtTs(r.created_at)}</div>
                                {opened && detailStr && <div style={{ marginTop: 7, padding: "8px 10px", borderRadius: 9, background: C.grid, color: C.sub, fontSize: 11.5, fontWeight: 600, lineHeight: 1.55, overflowWrap: "anywhere" }}>{detailStr}</div>}
                            </div>
                        </div>
                    )
                })}
            </div>
            <div style={{ ...card, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 700 }}>표시 {rangeStart.toLocaleString()}–{rangeEnd.toLocaleString()} / 전체 {totalCount.toLocaleString()}</span>
                <span style={{ marginLeft: "auto", fontSize: 11, color: C.faint, fontWeight: 700 }}>{page + 1} / {pageCount}</span>
                <button disabled={page <= 0 || loading} onClick={() => movePage(page - 1)} style={{ border: "none", borderRadius: 9, padding: "7px 12px", background: C.grid, color: C.sub, fontWeight: 800, opacity: page <= 0 ? 0.45 : 1 }}>이전</button>
                <button disabled={page + 1 >= pageCount || loading} onClick={() => movePage(page + 1)} style={{ border: "none", borderRadius: 9, padding: "7px 12px", background: C.grid, color: C.sub, fontWeight: 800, opacity: page + 1 >= pageCount ? 0.45 : 1 }}>다음</button>
            </div>
            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600 }}>모든 관리자 조치는 여기 기록돼요 · 읽기 전용</div>
        </div>
    )
}

addPropertyControls(AuditLogCard, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})

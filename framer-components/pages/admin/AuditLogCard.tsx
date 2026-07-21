import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * AuditLogCard — 관리자 조치 로그 (AlphaNest 스타일).
 * 소스: /api/admin?type=audit_log (본인 JWT · is_admin · service_role). 누가·뭘·누구를·언제.
 * admin_audit_log 테이블 기록(제재·삭제·수정·글삭제)을 최신순 표시. 읽기 전용.
 * 다크모드 자동감지. 접근차단 = 페이지 AuthGate.
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
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const SESSION_KEY = "verity_supabase_session"
// action → 한글 라벨 + 색 키
const ACTIONS: Record<string, { t: string; c: string }> = {
    ban_user: { t: "회원 제재", c: "amber" }, unban_user: { t: "제재 해제", c: "green" },
    delete_user: { t: "회원 삭제", c: "up" }, update_profile: { t: "정보 수정", c: "vt" },
    delete_post: { t: "글 삭제", c: "up" }, hide_post: { t: "글 숨김", c: "amber" }, unhide_post: { t: "숨김 해제", c: "green" },
}

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {}
    return false
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

export default function AuditLogCard(props: Props) {
    const apiBase = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT
    const [rows, setRows] = useState<Row[]>(onCanvas ? SAMPLE : [])
    const [loading, setLoading] = useState(!onCanvas)  // 초기 = 로딩(스켈레톤 첫 페인트부터, "없어요" 번쩍임 제거)
    const [err, setErr] = useState("")

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || !document.body) return
        const o = new MutationObserver(read)
        o.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => o.disconnect()
    }, [onCanvas])

    const load = useCallback(() => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setLoading(true); setErr("")
        fetch(`${apiBase}/api/admin?type=audit_log&limit=100`, { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
            .then((d) => setRows(Array.isArray(d.items) ? d.items : []))
            .catch((e) => setErr("불러오기 실패: " + (e && e.message ? e.message : e)))
            .finally(() => setLoading(false))
    }, [apiBase, onCanvas])

    useEffect(() => { load() }, [load])

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: 16, display: "flex", flexDirection: "column", gap: 12 }
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const colorOf = (k?: string) => (k === "up" ? C.up : k === "green" ? C.green : k === "amber" ? C.amber : C.vt)
    const bgOf = (k?: string) => (k === "up" ? C.grid : k === "green" ? C.greenS : k === "amber" ? C.amberS : C.vtS)

    // 스켈레톤 — 최초 로딩(조치 로그 fetch) 동안 로그 행 형태를 본떠 표시.
    const dk = onCanvas ? !!props.dark : themeDark
    const skBase = dk ? "#232a33" : "#e7eaee", skHi = dk ? "#2f3742" : "#f3f5f8"
    const shim: CSSProperties = { background: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "alcShimmer 1.4s ease-in-out infinite" }
    const skRows = (
        <>
            <style>{`@keyframes alcShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            {[0, 1, 2, 3].map((i) => (
                <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start", paddingTop: i === 0 ? 0 : 11, marginTop: i === 0 ? 0 : 11, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                    <div style={{ ...shim, width: 48, height: 20, borderRadius: 7, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ ...shim, width: "70%", height: 13, borderRadius: 6 }} />
                        <div style={{ ...shim, width: 130, height: 11, borderRadius: 6, marginTop: 4 }} />
                    </div>
                </div>
            ))}
        </>
    )

    return (
        <div style={wrap}>
            <div style={card}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                    <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px" }}>관리자 조치 로그</span>
                    <span style={{ marginLeft: "auto", fontSize: 11, color: C.faint, fontWeight: 600, cursor: "pointer" }} onClick={load}>{loading ? "불러오는 중…" : "새로고침"}</span>
                </div>
                {err && <div style={{ fontSize: 12, color: C.up, fontWeight: 700, marginTop: 10 }}>{err}</div>}
            </div>

            <div style={card}>
                {rows.length === 0 && loading ? skRows
                 : rows.length === 0 && !loading ? (
                    <div style={{ fontSize: 13, color: C.faint, fontWeight: 600 }}>기록된 조치가 없어요</div>
                ) : rows.map((r, i) => {
                    const a = ACTIONS[r.action || ""] || { t: r.action || "조치", c: "vt" }
                    const detailStr = r.detail && typeof r.detail === "object" ? Object.keys(r.detail).map((k) => `${k}: ${r.detail[k]}`).join(" · ") : ""
                    return (
                        <div key={r.id} style={{ display: "flex", gap: 10, alignItems: "flex-start", paddingTop: i === 0 ? 0 : 11, marginTop: i === 0 ? 0 : 11, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                            <span style={{ flexShrink: 0, fontSize: 11, fontWeight: 800, color: colorOf(a.c), background: bgOf(a.c), borderRadius: 7, padding: "3px 9px" }}>{a.t}</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 12.5, fontWeight: 700, color: C.ink }}>
                                    {r.target_type === "user" ? "회원" : "글"} <span style={{ color: C.faint, fontWeight: 600 }}>{r.target_id ? r.target_id.slice(0, 8) : "—"}</span>
                                    {detailStr && <span style={{ color: C.sub, fontWeight: 600 }}> · {detailStr}</span>}
                                </div>
                                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 2 }}>{r.actor_email || "—"} · {fmtTs(r.created_at)}</div>
                            </div>
                        </div>
                    )
                })}
            </div>
            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600 }}>모든 관리자 조치는 여기 기록돼요 · 읽기 전용</div>
        </div>
    )
}

addPropertyControls(AuditLogCard, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * SecurityCard — IP 침입 시도 추적 · 차단 (AlphaNest 관리자).
 * 소스: /api/admin?type=security (본인 JWT · is_admin · service_role). Railway+Vercel 공유 blocked_ips.
 *   GET = 침입 로그 + 활성 차단 + 상위 공격 IP.  POST = 수동 block / unblock.
 * 방어층 — 민감 데이터는 이미 인증+RLS로 잠김. 여긴 가시화 + 차단 관리. 접근차단 = 페이지 AdminGate.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", upS: "#fdeef0", down: "#3182f6",
    green: "#15c47e", greenS: "#eafaf3", amber: "#ff9500", amberS: "#fff6e9", vt: "#6c5ce7", vtS: "#f0edff", field: "#f2f4f6",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", grid: "#1e242c", up: "#f04452", upS: "#2a1418", down: "#5b9bff",
    green: "#34e08a", greenS: "#0f241c", amber: "#ff9500", amberS: "#2a2113", vt: "#a99bff", vtS: "#241f3a", field: "#1e242c",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const SESSION_KEY = "verity_supabase_session"

const REASON: Record<string, { t: string; c: string }> = {
    env_probe: { t: "env 탐색", c: "up" }, git_probe: { t: ".git 탐색", c: "up" },
    wp_probe: { t: "WP 스캔", c: "amber" }, path_traversal: { t: "경로 순회", c: "up" },
    secret_probe: { t: "시크릿 탐색", c: "up" }, cgi_probe: { t: "파일 스캔", c: "amber" },
    admin_unauth: { t: "어드민 무단접근", c: "vt" },
}

function readBodyDark(): boolean {
    try {
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

interface Probe { ip: string; path?: string; method?: string; reason?: string; surface?: string; country?: string; created_at?: string }
interface Blocked { ip: string; reason?: string; hits?: number; auto?: boolean; surface?: string; created_by?: string; created_at?: string; expires_at?: string }
interface TopIp { ip: string; count: number; blocked: boolean }
interface Data { probes: Probe[]; blocked: Blocked[]; top_ips: TopIp[]; stats: { probes_recent: number; blocked_active: number } }

const SAMPLE: Data = {
    probes: [
        { ip: "45.88.90.12", path: "/.env", reason: "env_probe", surface: "railway", created_at: "2026-07-17T14:02:00" },
        { ip: "45.88.90.12", path: "/wp-admin/setup-config.php", reason: "wp_probe", surface: "railway", created_at: "2026-07-17T14:01:00" },
        { ip: "203.0.113.7", path: "/api/admin", reason: "admin_unauth", surface: "vercel", created_at: "2026-07-17T13:40:00" },
        { ip: "45.88.90.12", path: "/../../etc/passwd", reason: "path_traversal", surface: "railway", created_at: "2026-07-17T13:38:00" },
    ],
    blocked: [
        { ip: "45.88.90.12", reason: "env_probe", hits: 4, auto: true, surface: "railway", created_by: "auto", created_at: "2026-07-17T14:02:00", expires_at: "2026-07-18T14:02:00" },
        { ip: "185.220.101.5", reason: "manual", hits: 1, auto: false, surface: "manual", created_by: "admin@alphanest.kr", created_at: "2026-07-16T22:00:00" },
    ],
    top_ips: [{ ip: "45.88.90.12", count: 3, blocked: true }, { ip: "203.0.113.7", count: 1, blocked: false }],
    stats: { probes_recent: 4, blocked_active: 2 },
}

interface Props { apiBase: string; dark: boolean }

export default function SecurityCard(props: Props) {
    const apiBase = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT
    const [data, setData] = useState<Data | null>(onCanvas ? SAMPLE : null)
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState("")
    const [manualIp, setManualIp] = useState("")
    const [busy, setBusy] = useState("")

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
        fetch(`${apiBase}/api/admin?type=security`, { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
            .then((d) => setData({ probes: d.probes || [], blocked: d.blocked || [], top_ips: d.top_ips || [], stats: d.stats || { probes_recent: 0, blocked_active: 0 } }))
            .catch((e) => setErr("불러오기 실패: " + (e && e.message ? e.message : e)))
            .finally(() => setLoading(false))
    }, [apiBase, onCanvas])

    useEffect(() => { load() }, [load])

    const act = useCallback((action: string, ip: string, reason?: string) => {
        if (onCanvas || !ip) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setBusy(ip)
        fetch(`${apiBase}/api/admin?type=security`, {
            method: "POST", cache: "no-store",
            headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({ action, ip, reason }),
        })
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
            .then(() => { if (action === "block") setManualIp(""); load() })
            .catch((e) => setErr("처리 실패: " + (e && e.message ? e.message : e)))
            .finally(() => setBusy(""))
    }, [apiBase, onCanvas, load])

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: 16, display: "flex", flexDirection: "column", gap: 12 }
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const colorOf = (k?: string) => (k === "up" ? C.up : k === "green" ? C.green : k === "amber" ? C.amber : C.vt)
    const bgOf = (k?: string) => (k === "up" ? C.upS : k === "green" ? C.greenS : k === "amber" ? C.amberS : C.vtS)
    const surfBadge = (s?: string) => {
        const t = s === "railway" ? "Railway" : s === "vercel" ? "Vercel" : s === "manual" ? "수동" : (s || "—")
        return <span style={{ fontSize: 9.5, fontWeight: 800, color: C.faint, background: C.grid, borderRadius: 5, padding: "1.5px 5px" }}>{t}</span>
    }
    const btn = (label: string, onClick: () => void, danger?: boolean, on?: boolean): CSSProperties => ({
        fontSize: 11, fontWeight: 800, cursor: on ? "default" : "pointer", borderRadius: 8, padding: "5px 11px", border: "none",
        color: danger ? "#fff" : C.vt, background: danger ? C.up : C.vtS, opacity: on ? 0.5 : 1, whiteSpace: "nowrap",
    })

    // 스켈레톤 — 최초 로딩(보안 로그 fetch) 동안 헤더·통계·섹션 형태를 본떠 표시(빈 카드=오류처럼 보임 회피).
    //   에러(로그인 필요 등) 시엔 스켈레톤 대신 정상 렌더가 에러 메시지를 노출.
    if (!onCanvas && !data && !err) {
        const skBase = themeDark ? "#232a33" : "#e7eaee", skHi = themeDark ? "#2f3742" : "#f3f5f8"
        const shim: CSSProperties = { background: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "secShimmer 1.4s ease-in-out infinite" }
        const secSk = (rows: number) => (
            <div style={card}>
                <div style={{ ...shim, width: 110, height: 15, borderRadius: 6, marginBottom: 12 }} />
                {Array.from({ length: rows }).map((_, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, paddingTop: i === 0 ? 0 : 9, marginTop: i === 0 ? 0 : 9, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                        <div style={{ ...shim, width: 120, height: 14, borderRadius: 6 }} />
                        <div style={{ ...shim, width: 40, height: 12, borderRadius: 6 }} />
                        <div style={{ ...shim, width: 56, height: 22, borderRadius: 8, marginLeft: "auto" }} />
                    </div>
                ))}
            </div>
        )
        return (
            <div style={wrap} aria-busy="true" aria-label="보안 로그 불러오는 중">
                <style>{`@keyframes secShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={card}>
                    <div style={{ ...shim, width: 130, height: 18, borderRadius: 6 }} />
                    <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
                        <div style={{ ...shim, flex: 1, height: 58, borderRadius: 11 }} />
                        <div style={{ ...shim, flex: 1, height: 58, borderRadius: 11 }} />
                    </div>
                    <div style={{ ...shim, width: "100%", height: 38, borderRadius: 9, marginTop: 12 }} />
                </div>
                {secSk(2)}
                {secSk(3)}
            </div>
        )
    }

    const d = data || { probes: [], blocked: [], top_ips: [], stats: { probes_recent: 0, blocked_active: 0 } }

    return (
        <div style={wrap}>
            {/* 헤더 + 통계 */}
            <div style={card}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                    <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px" }}>보안 · 침입 시도</span>
                    <span style={{ marginLeft: "auto", fontSize: 11, color: C.faint, fontWeight: 700, cursor: "pointer" }} onClick={load}>{loading ? "불러오는 중…" : "새로고침"}</span>
                </div>
                <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
                    <div style={{ flex: 1, background: C.grid, borderRadius: 11, padding: "10px 12px" }}>
                        <div style={{ fontSize: 21, fontWeight: 800, color: C.ink, letterSpacing: "-0.5px" }}>{d.stats.probes_recent}</div>
                        <div style={{ fontSize: 10.5, color: C.sub, fontWeight: 700 }}>최근 침입 시도</div>
                    </div>
                    <div style={{ flex: 1, background: d.stats.blocked_active > 0 ? C.upS : C.grid, borderRadius: 11, padding: "10px 12px" }}>
                        <div style={{ fontSize: 21, fontWeight: 800, color: d.stats.blocked_active > 0 ? C.up : C.ink, letterSpacing: "-0.5px" }}>{d.stats.blocked_active}</div>
                        <div style={{ fontSize: 10.5, color: C.sub, fontWeight: 700 }}>활성 차단 IP</div>
                    </div>
                </div>
                {err && <div style={{ fontSize: 12, color: C.up, fontWeight: 700, marginTop: 10 }}>{err}</div>}
                {/* 수동 차단 */}
                <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                    <input value={manualIp} onChange={(e) => setManualIp(e.target.value)} placeholder="IP 직접 차단 (예: 45.88.90.12)"
                        style={{ flex: 1, background: C.field, border: "none", borderRadius: 9, padding: "9px 12px", fontSize: 12.5, fontWeight: 600, color: C.ink, fontFamily: FONT, outline: "none" }} />
                    <button onClick={() => act("block", manualIp.trim(), "manual")} disabled={!manualIp.trim() || !!busy}
                        style={btn("차단", () => {}, true, !manualIp.trim())}>차단</button>
                </div>
            </div>

            {/* 상위 공격 IP */}
            {d.top_ips.length > 0 && (
                <div style={card}>
                    <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 9 }}>상위 공격 IP</div>
                    {d.top_ips.map((t, i) => (
                        <div key={t.ip} style={{ display: "flex", alignItems: "center", gap: 10, paddingTop: i === 0 ? 0 : 9, marginTop: i === 0 ? 0 : 9, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                            <span style={{ fontSize: 13, fontWeight: 800, fontFamily: "monospace", color: C.ink }}>{t.ip}</span>
                            <span style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>{t.count}회</span>
                            <span style={{ marginLeft: "auto" }}>
                                {t.blocked
                                    ? <button onClick={() => act("unblock", t.ip)} disabled={busy === t.ip} style={btn("해제", () => {}, false, false)}>차단 해제</button>
                                    : <button onClick={() => act("block", t.ip, "manual")} disabled={busy === t.ip} style={btn("차단", () => {}, true, false)}>차단</button>}
                            </span>
                        </div>
                    ))}
                </div>
            )}

            {/* 활성 차단 목록 */}
            <div style={card}>
                <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 9 }}>차단 목록 <span style={{ color: C.faint, fontWeight: 700 }}>{d.blocked.length}</span></div>
                {d.blocked.length === 0 ? (
                    <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>차단된 IP가 없어요</div>
                ) : d.blocked.map((b, i) => (
                    <div key={b.ip} style={{ display: "flex", alignItems: "center", gap: 10, paddingTop: i === 0 ? 0 : 10, marginTop: i === 0 ? 0 : 10, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span style={{ fontSize: 13, fontWeight: 800, fontFamily: "monospace", color: C.ink }}>{b.ip}</span>
                                <span style={{ fontSize: 9.5, fontWeight: 800, color: b.auto ? C.amber : C.vt, background: b.auto ? C.amberS : C.vtS, borderRadius: 5, padding: "1.5px 5px" }}>{b.auto ? "자동" : "수동"}</span>
                                {surfBadge(b.surface)}
                            </div>
                            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>
                                {(REASON[b.reason || ""]?.t) || b.reason || "—"} · {b.expires_at ? `~${fmtTs(b.expires_at)} 만료` : "영구"} · {b.created_by || "—"}
                            </div>
                        </div>
                        <button onClick={() => act("unblock", b.ip)} disabled={busy === b.ip} style={btn("해제", () => {}, false, false)}>해제</button>
                    </div>
                ))}
            </div>

            {/* 최근 침입 로그 */}
            <div style={card}>
                <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 9 }}>최근 침입 로그</div>
                {d.probes.length === 0 ? (
                    <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>기록된 침입 시도가 없어요 · 조용한 게 정상이에요</div>
                ) : d.probes.slice(0, 60).map((p, i) => {
                    const rc = REASON[p.reason || ""] || { t: p.reason || "스캔", c: "amber" }
                    return (
                        <div key={i} style={{ display: "flex", gap: 9, alignItems: "flex-start", paddingTop: i === 0 ? 0 : 9, marginTop: i === 0 ? 0 : 9, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                            <span style={{ flexShrink: 0, fontSize: 10.5, fontWeight: 800, color: colorOf(rc.c), background: bgOf(rc.c), borderRadius: 6, padding: "3px 8px" }}>{rc.t}</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 12, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                    <span style={{ fontFamily: "monospace" }}>{p.ip}</span> <span style={{ color: C.sub, fontWeight: 600 }}>{p.path}</span>
                                </div>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
                                    {surfBadge(p.surface)}
                                    <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600 }}>{fmtTs(p.created_at)}</span>
                                </div>
                            </div>
                        </div>
                    )
                })}
            </div>

            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600 }}>
                자동 차단 = 스캔 반복 IP · 24시간 후 자동 해제 · 민감 데이터는 인증+RLS로 별도 보호
            </div>
        </div>
    )
}

addPropertyControls(SecurityCard, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})

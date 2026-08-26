import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * NoticeAdminCard — 공지·이벤트 발행 (AlphaNest 관리자).
 * 소스: /api/admin?type=notices (본인 JWT · is_admin 서버 재검증 · service_role 실행 · 감사 로그).
 *   GET 전량 목록 · POST 신규/수정(id 동봉 시) · DELETE. 공개 읽기는 /api/notices (027 RLS).
 * 노출 기간(시작/종료) 비우면 무기한. 종료 시각이 지나면 공개에서 자동으로 빠짐 = is_active 손댈 필요 없음.
 * 다크모드 자동감지. 접근차단 = 페이지 AdminGate(is_admin).
 *
 * 🚨 RULE 6 — 여기 쓰는 문구가 사이트에 그대로 나갑니다. LLM 생성 0, 관리자 작성 원문만.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", field: "#f7f8fa", up: "#f04452", upS: "#fff0f1",
    green: "#15c47e", greenS: "#eafaf3", vt: "#6c5ce7", vtS: "#f0edff", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", field: "#1e242c", up: "#f04452", upS: "#2a1a1d",
    green: "#34e08a", greenS: "#0f241c", vt: "#a99bff", vtS: "#241f3a", onAccent: "#0f1318",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const SESSION_KEY = "verity_supabase_session"

function readBodyDark(): boolean {
    // 🚨 판독 순서 고정 — 되돌리지 말 것 (2026-07-23 공개 컴포넌트 fix, 2026-08-27 관리자 이관).
    //   ① html[data-an-theme] = Custom Code 헤드 스크립트가 **페인트 전 동기** 세팅(레이스 제거)
    //   ② body[data-framer-theme] = 토글
    //   ③ localStorage
    //   🚨 body-first 로 되돌리지 말 것 — Framer 네이티브가 새로고침 때 body 를 OS 로 리셋해
    //     **부분 라이트 회귀**가 난다. 관리자 11개가 이 옛 방식으로 남아 있었다(2026-08-27 PM 신고
    //     "다크모드 시에 그 부분만 라이트가 됨").
    //   🚨 OS 설정(prefers-color-scheme)은 **보지 않는다** — 로드마다 뒤집힌다. 종전 관리자 변종이
    //     마지막 폴백으로 matchMedia 를 써서, 사이트가 다크여도 OS 가 라이트면 라이트로 그렸다.
    try {
        if (typeof document !== "undefined") {
            const h = document.documentElement ? document.documentElement.dataset.anTheme : null
            if (h === "dark") return true
            if (h === "light") return false
            if (document.body) {
                const a = document.body.dataset.framerTheme
                if (a === "dark") return true
                if (a === "light") return false
            }
        }
        const s = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (s === "dark") return true
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
function fmtDate(iso: any): string {
    if (!iso) return "—"
    try {
        const d = new Date(String(iso))
        return `${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`
    } catch (e) { return "—" }
}

interface Notice {
    id: string; kind?: string; title?: string; body?: string; link?: string
    pinned?: boolean; starts_at?: string; ends_at?: string; is_active?: boolean; created_at?: string
}

const SAMPLE: Notice[] = [
    { id: "n1", kind: "event", title: "첫 관점 남기기 이벤트", body: "이번 주 안에 관점을 남기면 커뮤니티 첫 기록으로 남아요.", pinned: true, is_active: true, created_at: "2026-07-26" },
    { id: "n2", kind: "notice", title: "커뮤니티 이용 안내", body: "모든 글은 이용자 개인 의견이며 투자 권유가 아닙니다.", pinned: false, is_active: true, created_at: "2026-07-20" },
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

export default function NoticeAdminCard(props: Props) {
    const apiBase = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT

    const [items, setItems] = useState<Notice[]>(onCanvas ? SAMPLE : [])
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState("")
    const [msg, setMsg] = useState("")
    const [busy, setBusy] = useState("")
    const [needMigration, setNeedMigration] = useState("")

    // 작성 폼
    const [kind, setKind] = useState<"notice" | "event">("notice")
    const [title, setTitle] = useState("")
    const [body, setBody] = useState("")
    const [link, setLink] = useState("")
    const [pinned, setPinned] = useState(false)
    const [endsAt, setEndsAt] = useState("") // 이벤트 종료(YYYY-MM-DD). 비우면 무기한

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
        fetch(`${apiBase}/api/admin?type=notices&limit=100`, { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
            .then((d) => {
                setItems(Array.isArray(d.items) ? d.items : [])
                // 🚨 마이그레이션 미적용은 "실패" 가 아니라 "설치 대기" — 원인을 그대로 안내한다.
                setNeedMigration(String(d.migration_required || ""))
            })
            .catch((e) => setErr("불러오기 실패: " + (e && e.message ? e.message : e)))
            .finally(() => setLoading(false))
    }, [apiBase, onCanvas])

    useEffect(() => { load() }, [load])

    const call = async (key: string, method: string, payload: any, okMsg: string) => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setBusy(key); setErr(""); setMsg("")
        try {
            const r = await fetch(`${apiBase}/api/admin?type=notices`, {
                method,
                headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            })
            const d = await r.json().catch(() => ({}))
            if (!r.ok) throw new Error(d.error || ("HTTP " + r.status))
            setMsg(okMsg); load()
        } catch (e: any) {
            setErr("실패: " + (e && e.message ? e.message : e))
        } finally {
            setBusy("")
        }
    }

    const publish = () => {
        const t = title.trim()
        if (!t) { setErr("제목을 입력해 주세요"); return }
        const payload: any = { kind, title: t, body: body.trim(), link: link.trim(), pinned, is_active: true }
        if (endsAt.trim()) payload.ends_at = endsAt.trim() + "T23:59:59+09:00" // 한국 기준 그날 끝까지
        call("new", "POST", payload, "발행했어요")
        setTitle(""); setBody(""); setLink(""); setPinned(false); setEndsAt("")
    }

    const wrap: CSSProperties = {
        background: C.card, borderRadius: 16, padding: "18px 18px 14px", fontFamily: FONT,
        color: C.ink, boxSizing: "border-box", width: "100%",
    }
    const label: CSSProperties = { fontSize: 11.5, fontWeight: 700, color: C.faint, marginBottom: 5 }
    const input: CSSProperties = {
        width: "100%", boxSizing: "border-box", border: "none", outline: "none", background: C.field,
        color: C.ink, fontFamily: FONT, fontSize: 13, fontWeight: 600, borderRadius: 10, padding: "10px 12px",
    }
    const btn = (bg: string, fg: string): CSSProperties => ({
        border: "none", cursor: "pointer", fontFamily: FONT, fontSize: 12.5, fontWeight: 800,
        borderRadius: 10, padding: "10px 16px", background: bg, color: fg,
    })

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span style={{ fontSize: 15.5, fontWeight: 800, letterSpacing: "-0.3px" }}>공지 · 이벤트</span>
                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>커뮤니티 상단 배너에 노출</span>
                <button onClick={load} disabled={loading} style={{ ...btn("transparent", C.vt), marginLeft: "auto", padding: "4px 8px" }}>
                    {loading ? "불러오는 중" : "새로고침"}
                </button>
            </div>

            {/* 작성 */}
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", gap: 8 }}>
                    {([["notice", "공지"], ["event", "이벤트"]] as const).map(([k, lb]) => (
                        <button
                            key={k}
                            onClick={() => setKind(k)}
                            style={btn(kind === k ? C.vt : C.field, kind === k ? C.onAccent : C.sub)}
                        >
                            {lb}
                        </button>
                    ))}
                    <label style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 700, color: C.sub, cursor: "pointer" }}>
                        <input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} />
                        상단 고정
                    </label>
                </div>
                <div>
                    <div style={label}>제목 (최대 120자)</div>
                    <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} placeholder="예: 커뮤니티 이용 안내" style={input} />
                </div>
                <div>
                    <div style={label}>본문 (선택 · 최대 2000자)</div>
                    <textarea value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} rows={3} placeholder="배너에 그대로 노출됩니다" style={{ ...input, resize: "vertical", lineHeight: 1.55 }} />
                </div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <div style={{ flex: "1 1 200px", minWidth: 0 }}>
                        <div style={label}>링크 (선택)</div>
                        <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://" style={input} />
                    </div>
                    <div style={{ flex: "0 1 170px" }}>
                        <div style={label}>종료일 (선택 · 비우면 무기한)</div>
                        <input value={endsAt} onChange={(e) => setEndsAt(e.target.value)} placeholder="2026-08-31" style={input} />
                    </div>
                </div>
                <button onClick={publish} disabled={busy === "new"} style={btn(C.vt, C.onAccent)}>
                    {busy === "new" ? "발행 중" : "발행"}
                </button>
            </div>

            {needMigration ? (
                <div style={{ marginTop: 10, fontSize: 12, fontWeight: 700, color: C.vt, background: C.vtS, borderRadius: 8, padding: "10px 12px", lineHeight: 1.55 }}>
                    아직 준비 단계예요 — Supabase SQL Editor 에서 <b>{needMigration}.sql</b> 을 실행하면 바로 사용할 수 있어요.
                </div>
            ) : null}
            {err ? <div style={{ marginTop: 10, fontSize: 12, fontWeight: 700, color: C.up, background: C.upS, borderRadius: 8, padding: "8px 10px" }}>{err}</div> : null}
            {msg ? <div style={{ marginTop: 10, fontSize: 12, fontWeight: 700, color: C.green, background: C.greenS, borderRadius: 8, padding: "8px 10px" }}>{msg}</div> : null}

            {/* 목록 */}
            <div style={{ marginTop: 16, borderTop: `1px solid ${C.line}`, paddingTop: 6 }}>
                {loading ? (
                    <AdmSkeletonRows C={C} rows={3} />
                ) : items.length === 0 ? (
                    <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600, padding: "14px 2px" }}>
                        발행한 공지가 없어요
                    </div>
                ) : (
                    items.map((n) => (
                        <div key={n.id} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "11px 2px", borderBottom: `1px solid ${C.line}` }}>
                            <span style={{ flexShrink: 0, marginTop: 2, fontSize: 10.5, fontWeight: 800, color: n.kind === "event" ? C.onAccent : C.vt, background: n.kind === "event" ? C.vt : C.vtS, borderRadius: 6, padding: "3px 7px" }}>
                                {n.kind === "event" ? "이벤트" : "공지"}
                            </span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 13, fontWeight: 800, color: n.is_active ? C.ink : C.faint }}>
                                    {n.title}
                                    {n.pinned ? <span style={{ marginLeft: 6, fontSize: 11, color: C.vt }}>고정</span> : null}
                                </div>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3 }}>
                                    {fmtDate(n.created_at)}
                                    {n.ends_at ? ` · ${fmtDate(n.ends_at)} 종료` : " · 무기한"}
                                    {n.is_active ? "" : " · 숨김"}
                                </div>
                            </div>
                            <button
                                onClick={() => call("t" + n.id, "POST", { id: n.id, is_active: !n.is_active }, n.is_active ? "숨겼어요" : "다시 노출해요")}
                                disabled={busy === "t" + n.id}
                                style={{ ...btn(C.field, C.sub), padding: "6px 10px", flexShrink: 0 }}
                            >
                                {n.is_active ? "숨김" : "노출"}
                            </button>
                            <button
                                onClick={() => {
                                    if (typeof window !== "undefined" && !window.confirm("삭제할까요? 되돌릴 수 없어요.")) return
                                    call("d" + n.id, "DELETE", { id: n.id }, "삭제했어요")
                                }}
                                disabled={busy === "d" + n.id}
                                style={{ ...btn(C.upS, C.up), padding: "6px 10px", flexShrink: 0 }}
                            >
                                삭제
                            </button>
                        </div>
                    ))
                )}
            </div>
        </div>
    )
}

addPropertyControls(NoticeAdminCard, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})

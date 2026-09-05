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
// CSS가 body[data-framer-theme]를 직접 따라간다. 테마 변경에 React 상태/Observer를 사용하지 않는다.
const ADMIN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-admin-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-admin-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: any = {}
for (const k of Object.keys(LIGHT)) C[k] = "var(--an-admin-" + k + ")"

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const SESSION_KEY = "verity_supabase_session"

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
const SAMPLE_SUPPORT = [
    { id: "s1", kind: "question", author: "길동무", title: "관점 공개 기준", body: "비공개로 저장하면 다른 사람에게 안 보이나요?", publish_consent: true, status: "open", answer: "", hidden: false, created_at: "2026-09-04" },
    { id: "s2", kind: "feedback", author: "회원", title: "모바일 간격", body: "작은 화면에서 카드 간격이 조금 넓어요.", publish_consent: false, status: "open", answer: "", hidden: false, created_at: "2026-09-03" },
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

    const [items, setItems] = useState<Notice[]>(onCanvas ? SAMPLE : [])
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState("")
    const [msg, setMsg] = useState("")
    const [busy, setBusy] = useState("")
    const [needMigration, setNeedMigration] = useState("")
    const [adminTab, setAdminTab] = useState<"notices" | "support">("notices")
    const [supportItems, setSupportItems] = useState<any[]>(onCanvas ? SAMPLE_SUPPORT : [])
    const [supportLoading, setSupportLoading] = useState(false)
    const [supportFilter, setSupportFilter] = useState<"all" | "open" | "answered" | "closed">("open")
    const [answerDrafts, setAnswerDrafts] = useState<Record<string, string>>({})

    // 작성 폼
    const [kind, setKind] = useState<"notice" | "event">("notice")
    const [title, setTitle] = useState("")
    const [body, setBody] = useState("")
    const [link, setLink] = useState("")
    const [pinned, setPinned] = useState(false)
    const [endsAt, setEndsAt] = useState("") // 이벤트 종료(YYYY-MM-DD). 비우면 무기한

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

    const loadSupport = useCallback(() => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setSupportLoading(true); setErr("")
        const suffix = supportFilter === "all" ? "" : "&status=" + supportFilter
        fetch(`${apiBase}/api/support?admin=1${suffix}`, { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
            .then((d) => {
                setSupportItems(Array.isArray(d.items) ? d.items : [])
                if (d.migration_required) setNeedMigration(String(d.migration_required))
            })
            .catch((e) => setErr("접수함 불러오기 실패: " + (e && e.message ? e.message : e)))
            .finally(() => setSupportLoading(false))
    }, [apiBase, onCanvas, supportFilter])

    useEffect(() => {
        if (adminTab === "support") loadSupport()
    }, [adminTab, loadSupport])

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

    const supportCall = async (it: any, action: string) => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        const key = action + it.id
        const payload: any = { id: it.id, action }
        if (action === "answer") {
            payload.answer = String(answerDrafts[it.id] || it.answer || "").trim()
            if (!payload.answer) { setErr("답변을 입력해 주세요"); return }
        }
        setBusy(key); setErr(""); setMsg("")
        try {
            const r = await fetch(`${apiBase}/api/support?admin=1`, {
                method: "POST",
                headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            })
            const data = await r.json().catch(() => ({}))
            if (!r.ok) throw new Error(data.error || ("HTTP " + r.status))
            setMsg(action === "answer" ? "답변을 저장했어요" : "상태를 변경했어요")
            setAnswerDrafts((drafts) => ({ ...drafts, [it.id]: "" }))
            loadSupport()
        } catch (e: any) {
            setErr("실패: " + (e && e.message ? e.message : e))
        } finally {
            setBusy("")
        }
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
            <style>{ADMIN_PALETTE}</style>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span style={{ fontSize: 15.5, fontWeight: 800, letterSpacing: "-0.3px" }}>커뮤니티 운영</span>
                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>공지 발행 · 질문 답변 · 피드백 확인</span>
                <button onClick={adminTab === "notices" ? load : loadSupport} disabled={loading || supportLoading} style={{ ...btn("transparent", C.vt), marginLeft: "auto", padding: "4px 8px" }}>
                    {loading || supportLoading ? "불러오는 중" : "새로고침"}
                </button>
            </div>

            <div role="tablist" aria-label="커뮤니티 운영 메뉴" style={{ display: "flex", gap: 4, background: C.field, borderRadius: 12, padding: 4, marginTop: 13 }}>
                {([[
                    "notices", "공지·이벤트"
                ], [
                    "support", "Q&A·피드백"
                ]] as const).map(([key, label]) => (
                    <button key={key} role="tab" aria-selected={adminTab === key} onClick={() => setAdminTab(key)} style={{ flex: 1, border: "none", borderRadius: 9, background: adminTab === key ? C.card : "transparent", color: adminTab === key ? C.ink : C.faint, padding: "9px 8px", fontFamily: FONT, fontSize: 12.5, fontWeight: 850, cursor: "pointer", boxShadow: adminTab === key ? "0 1px 3px rgba(0,0,0,.06)" : "none" }}>{label}</button>
                ))}
            </div>

            {adminTab === "notices" && (
            <>

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
            </>
            )}

            {adminTab === "support" && (
                <div role="tabpanel" style={{ marginTop: 14 }}>
                    <div style={{ display: "flex", gap: 6, overflowX: "auto" }}>
                        {([[
                            "open", "확인 전"
                        ], [
                            "answered", "답변 완료"
                        ], [
                            "closed", "종료"
                        ], [
                            "all", "전체"
                        ]] as const).map(([key, label]) => (
                            <button key={key} onClick={() => setSupportFilter(key)} style={{ ...btn(supportFilter === key ? C.vt : C.field, supportFilter === key ? C.onAccent : C.sub), padding: "7px 11px", flexShrink: 0 }}>{label}</button>
                        ))}
                    </div>

                    {needMigration ? (
                        <div style={{ marginTop: 10, fontSize: 12, fontWeight: 700, color: C.vt, background: C.vtS, borderRadius: 8, padding: "10px 12px", lineHeight: 1.55 }}>
                            Supabase SQL Editor에서 <b>{needMigration}.sql</b>을 실행하면 접수함을 사용할 수 있어요.
                        </div>
                    ) : null}
                    {err ? <div style={{ marginTop: 10, fontSize: 12, fontWeight: 700, color: C.up, background: C.upS, borderRadius: 8, padding: "8px 10px" }}>{err}</div> : null}
                    {msg ? <div style={{ marginTop: 10, fontSize: 12, fontWeight: 700, color: C.green, background: C.greenS, borderRadius: 8, padding: "8px 10px" }}>{msg}</div> : null}

                    {supportLoading ? (
                        <AdmSkeletonRows C={C} rows={3} />
                    ) : supportItems.length === 0 ? (
                        <div style={{ color: C.faint, fontSize: 12.5, fontWeight: 650, padding: "22px 2px 8px" }}>이 상태의 접수 내용이 없어요.</div>
                    ) : supportItems.map((it) => {
                        const answer = answerDrafts[it.id] !== undefined ? answerDrafts[it.id] : (it.answer || "")
                        const statusLabel = it.status === "answered" ? "답변 완료" : it.status === "closed" ? "종료" : "확인 전"
                        return (
                            <section key={it.id} style={{ background: C.field, borderRadius: 14, padding: "14px", marginTop: 10 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
                                    <span style={{ color: it.kind === "feedback" ? C.up : C.vt, background: it.kind === "feedback" ? C.upS : C.vtS, borderRadius: 7, padding: "3px 7px", fontSize: 10.5, fontWeight: 850 }}>{it.kind === "feedback" ? "피드백" : "질문"}</span>
                                    <span style={{ color: C.ink, fontSize: 13.5, fontWeight: 850 }}>{it.title}</span>
                                    <span style={{ color: C.faint, fontSize: 10.5, fontWeight: 650 }}>{it.author || "회원"} · {fmtDate(it.created_at)}</span>
                                    <span style={{ marginLeft: "auto", color: it.status === "answered" ? C.green : C.faint, background: C.card, borderRadius: 7, padding: "3px 7px", fontSize: 10.5, fontWeight: 800 }}>{statusLabel}</span>
                                </div>
                                <div style={{ color: C.sub, fontSize: 12.5, fontWeight: 600, lineHeight: 1.6, marginTop: 9, whiteSpace: "pre-wrap" }}>{it.body}</div>
                                <div style={{ color: C.faint, fontSize: 10.5, fontWeight: 650, marginTop: 7 }}>{it.kind === "question" && it.publish_consent ? "답변 완료 후 공개 Q&A 노출 동의" : "작성자와 운영자만 확인"}{it.hidden ? " · 공개 숨김" : ""}</div>

                                <textarea
                                    value={answer}
                                    onChange={(e) => setAnswerDrafts((drafts) => ({ ...drafts, [it.id]: e.target.value.slice(0, 3000) }))}
                                    maxLength={3000}
                                    rows={3}
                                    aria-label={`${it.title} 답변`}
                                    placeholder={it.kind === "feedback" ? "피드백 처리 결과를 남겨주세요" : "초보자도 이해할 수 있게 답변해 주세요"}
                                    style={{ ...input, resize: "vertical", lineHeight: 1.55, marginTop: 10, background: C.card }}
                                />
                                <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginTop: 8 }}>
                                    <button onClick={() => supportCall(it, "answer")} disabled={busy === "answer" + it.id} style={{ ...btn(C.vt, C.onAccent), padding: "8px 11px" }}>{busy === "answer" + it.id ? "저장 중" : it.status === "answered" ? "답변 수정" : "답변 완료"}</button>
                                    <button onClick={() => supportCall(it, it.status === "closed" ? "reopen" : "close")} disabled={busy === "close" + it.id || busy === "reopen" + it.id} style={{ ...btn(C.card, C.sub), padding: "8px 11px" }}>{it.status === "closed" ? "다시 열기" : "종료"}</button>
                                    {it.kind === "question" && it.status === "answered" && it.publish_consent ? <button onClick={() => supportCall(it, it.hidden ? "unhide" : "hide")} disabled={busy === "hide" + it.id || busy === "unhide" + it.id} style={{ ...btn(it.hidden ? C.greenS : C.upS, it.hidden ? C.green : C.up), padding: "8px 11px" }}>{it.hidden ? "공개 복원" : "공개 숨김"}</button> : null}
                                </div>
                            </section>
                        )
                    })}
                </div>
            )}
        </div>
    )
}

addPropertyControls(NoticeAdminCard, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})

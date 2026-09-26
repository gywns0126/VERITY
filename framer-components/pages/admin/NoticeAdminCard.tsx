import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react"
import { NoticeDialog, NoticeArtwork, NOTICE_THEMES, resolveNoticeTheme } from "https://framer.com/m/PublicNoticeBanner-WLqzZR.js"

/**
 * NoticeAdminCard — 공지·이벤트 발행 (AlphaNest 관리자).
 * 소스: /api/admin?type=notices (본인 JWT · is_admin 서버 재검증 · service_role 실행 · 감사 로그).
 *   GET 전량 목록 · POST 신규/수정(id 동봉 시) · DELETE. 공개 읽기는 /api/notices (027 RLS).
 * 노출 기간(시작/종료) 비우면 무기한. 종료 시각이 지나면 공개에서 자동으로 빠짐 = is_active 손댈 필요 없음.
 * 다크모드 자동감지. 접근차단 = 페이지 AdminGate(is_admin).
 *
 * 🚨 RULE 6 — 여기 쓰는 문구가 사이트에 그대로 나갑니다. LLM 생성 0, 관리자 작성 원문만.
 * 2026-09-20: 새 공지는 전체 알림 기본 선택. 수정은 저장된 설정·숨김·노출 기간을 보존한다.
 * 답변 저장 뒤 빈 초안으로 서버 답변을 가리지 않는다. 저장된 답변은 입력창과 별도로 표시한다.
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
function noticeEndDate(iso?: string): string {
    const time = Date.parse(iso || "")
    return Number.isFinite(time) ? new Date(time + 9 * 60 * 60 * 1000).toISOString().slice(0, 10) : ""
}

interface Notice {
    id: string; kind?: string; title?: string; body?: string; link?: string
    pinned?: boolean; site_wide?: boolean; starts_at?: string; ends_at?: string; is_active?: boolean; created_at?: string
    thumbnail_theme?: string; thumbnail_url?: string
    display_date?: string; home_visible?: boolean; related_tickers?: string[]; related_topics?: string[]
}

// Decode and re-encode locally: strip metadata; no upload until the admin saves.
async function prepareNoticeImage(file: File): Promise<string> {
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 8 * 1024 * 1024) throw new Error("PNG·JPG·WebP 이미지(8MB 이하)를 선택해 주세요")
    const url = URL.createObjectURL(file)
    try {
        const img = new Image()
        img.src = url
        await img.decode()
        if (img.naturalWidth * img.naturalHeight > 25_000_000) throw new Error("이미지가 너무 커요. 가로 5000px 이하로 줄여 주세요")
        for (const maxWidth of [1200, 900, 600, 400]) {
            const scale = Math.min(1, maxWidth / img.naturalWidth, 800 / img.naturalHeight)
            const canvas = document.createElement("canvas")
            canvas.width = Math.max(1, Math.round(img.naturalWidth * scale))
            canvas.height = Math.max(1, Math.round(img.naturalHeight * scale))
            const ctx = canvas.getContext("2d")
            if (!ctx) throw new Error("이미지를 준비하지 못했어요")
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
            const png = canvas.toDataURL("image/png")
            if (png.length < 340000) return png
        }
        throw new Error("용량이 큰 이미지예요. 크기를 줄여 다시 선택해 주세요")
    } finally { URL.revokeObjectURL(url) }
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
    const [siteWideReady, setSiteWideReady] = useState(onCanvas)
    const [siteWideMigration, setSiteWideMigration] = useState("")
    const [artworkReady, setArtworkReady] = useState(onCanvas)
    const [editorialReady, setEditorialReady] = useState(onCanvas)
    const [adminTab, setAdminTab] = useState<"notices" | "support">("notices")
    const [supportItems, setSupportItems] = useState<any[]>(onCanvas ? SAMPLE_SUPPORT : [])
    const [supportLoading, setSupportLoading] = useState(false)
    const [supportFilter, setSupportFilter] = useState<"all" | "open" | "answered" | "closed">("open")
    const [answerDrafts, setAnswerDrafts] = useState<Record<string, string>>({})
    const supportRequest = useRef(0)

    // 작성·수정 폼
    const [editingNotice, setEditingNotice] = useState<Notice | null>(null)
    const titleInput = useRef<HTMLInputElement>(null)
    const [kind, setKind] = useState<"notice" | "event">("notice")
    const [title, setTitle] = useState("")
    const [body, setBody] = useState("")
    const [link, setLink] = useState("")
    const [pinned, setPinned] = useState(false)
    const [siteWide, setSiteWide] = useState(true) // 새 공지 기본 선택. 기존 공지는 저장된 값을 불러온다.
    const [endsAt, setEndsAt] = useState("") // 이벤트 종료(YYYY-MM-DD). 비우면 무기한
    const [displayDate, setDisplayDate] = useState("")
    const [homeVisible, setHomeVisible] = useState(false)
    const [relatedTickers, setRelatedTickers] = useState("")
    const [relatedTopics, setRelatedTopics] = useState<string[]>([])
    const [thumbnailTheme, setThumbnailTheme] = useState("auto")
    const [thumbnailUrl, setThumbnailUrl] = useState("")
    const [preparedImage, setPreparedImage] = useState("")
    const [previewOpen, setPreviewOpen] = useState(false)
    const previewTrigger = useRef<HTMLButtonElement>(null)
    const imageInput = useRef<HTMLInputElement>(null)
    const draft = { id: editingNotice?.id || "notice-preview", title: title.trim() || "공지 제목을 입력해 주세요", body, kind, link,
        created_at: editingNotice?.created_at || new Date().toISOString(), display_date: displayDate, thumbnail_theme: thumbnailTheme, thumbnail_url: thumbnailUrl }
    const themeLabel = NOTICE_THEMES.find(([value]) => value === resolveNoticeTheme(draft))?.[1] || "소식"

    const resetForm = () => {
        setEditingNotice(null); setKind("notice"); setTitle(""); setBody(""); setLink("")
        setPinned(false); setSiteWide(true); setEndsAt("")
        setDisplayDate(""); setHomeVisible(false); setRelatedTickers(""); setRelatedTopics([])
        setThumbnailTheme("auto"); setThumbnailUrl(""); setPreparedImage(""); setPreviewOpen(false)
    }
    const editNotice = (notice: Notice) => {
        if (busy) return
        setEditingNotice(notice); setKind(notice.kind === "event" ? "event" : "notice")
        setTitle(notice.title || ""); setBody(notice.body || ""); setLink(notice.link || "")
        setPinned(notice.pinned === true); setSiteWide(notice.site_wide === true)
        setEndsAt(noticeEndDate(notice.ends_at)); setErr(""); setMsg("")
        setDisplayDate(notice.display_date || ""); setHomeVisible(notice.home_visible === true)
        setRelatedTickers((notice.related_tickers || []).join(", ")); setRelatedTopics(notice.related_topics || [])
        setThumbnailTheme(notice.thumbnail_theme || "auto"); setThumbnailUrl(notice.thumbnail_url || ""); setPreparedImage("")
        titleInput.current?.focus()
        titleInput.current?.scrollIntoView({ block: "center", behavior: "smooth" })
    }

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
                setSiteWideReady(d.site_wide_ready === true)
                setSiteWideMigration(String(d.site_wide_migration || ""))
                setArtworkReady(d.artwork_ready === true)
                setEditorialReady(d.editorial_ready === true)
            })
            .catch((e) => { setSiteWideReady(false); setErr("불러오기 실패: " + (e && e.message ? e.message : e)) })
            .finally(() => setLoading(false))
    }, [apiBase, onCanvas])

    useEffect(() => { load() }, [load])

    const loadSupport = useCallback(() => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setSupportLoading(true); setErr("")
        const request = ++supportRequest.current
        const suffix = supportFilter === "all" ? "" : "&status=" + supportFilter
        fetch(`${apiBase}/api/support?admin=1${suffix}`, { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
            .then((d) => {
                if (request !== supportRequest.current) return
                setSupportItems(Array.isArray(d.items) ? d.items : [])
                if (d.migration_required) setNeedMigration(String(d.migration_required))
            })
            .catch((e) => { if (request === supportRequest.current) setErr("접수함 불러오기 실패: " + (e && e.message ? e.message : e)) })
            .finally(() => { if (request === supportRequest.current) setSupportLoading(false) })
    }, [apiBase, onCanvas, supportFilter])

    useEffect(() => {
        if (adminTab === "support") loadSupport()
        return () => { supportRequest.current += 1 }
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
            if (method === "POST" && (!d.item?.id || (payload.id && d.item.id !== payload.id))) throw new Error("공지 저장을 확인하지 못했어요. 목록을 새로고침해 확인해 주세요")
            if (payload.site_wide === true && d.item?.site_wide !== true) throw new Error("전체 알림 저장을 확인하지 못했어요. 목록을 새로고침해 확인해 주세요")
            if (payload.site_wide === false && d.item?.site_wide !== false) throw new Error("전체 알림 해제를 확인하지 못했어요. 목록을 새로고침해 확인해 주세요")
            if (payload.thumbnail_theme !== undefined && (d.item?.thumbnail_theme !== payload.thumbnail_theme || d.item?.thumbnail_url !== payload.thumbnail_url)) throw new Error("썸네일 저장을 확인하지 못했어요. 초안을 유지했으니 목록을 새로고침해 주세요")
            for (const field of ["display_date", "home_visible", "related_tickers", "related_topics"]) {
                if (field in payload && JSON.stringify(d.item?.[field]) !== JSON.stringify(payload[field])) throw new Error("소식 표시 설정을 확인하지 못했어요. 초안을 유지했으니 목록을 새로고침해 주세요")
            }
            setMsg(okMsg); load()
            return true
        } catch (e: any) {
            setErr("실패: " + (e && e.message ? e.message : e))
            return false
        } finally {
            setBusy("")
        }
    }

    const publish = async () => {
        if (busy) return
        const t = title.trim()
        if (!t) { setErr("제목을 입력해 주세요"); return }
        if (siteWide && !siteWideReady) { setErr("전체 알림은 API와 038 마이그레이션 적용 후 사용할 수 있어요"); return }
        if (!artworkReady && (thumbnailTheme !== "auto" || thumbnailUrl || preparedImage)) { setErr("썸네일 저장 기능을 준비 중이에요. 새로고침 후 다시 저장해 주세요"); return }
        if (link.trim()) {
            const v = link.trim()
            let valid = v.startsWith("/") && !v.startsWith("//")
            try { const u = new URL(v); valid = u.protocol === "https:" && !!u.hostname && !u.username && !u.password } catch { /* Relative site path. */ }
            if (!valid || v.length > 500 || /[\u0000-\u001f\\]/.test(v)) { setErr("링크는 /로 시작하는 사이트 경로나 https 주소를 입력해 주세요"); return }
        }
        const payload: any = { kind, title: t, body: body.trim(), link: link.trim(), pinned }
        if (editingNotice) payload.id = editingNotice.id
        else payload.is_active = true
        if (siteWideReady) payload.site_wide = siteWide
        if (editorialReady) {
            const tickers = [...new Set(relatedTickers.split(/[,\s]+/).filter(Boolean).map(t => t.toUpperCase()))]
            if (tickers.length > 20 || tickers.some(t => !/^[A-Z0-9][A-Z0-9.^/-]{0,19}$/.test(t))) { setErr("종목코드·티커를 쉼표로 구분해 최대 20개 입력해 주세요"); return }
            if (displayDate && (!/^\d{4}-\d{2}-\d{2}$/.test(displayDate) || !Number.isFinite(Date.parse(displayDate)) || new Date(displayDate).toISOString().slice(0, 10) !== displayDate)) { setErr("표시 날짜를 올바르게 입력해 주세요"); return }
            if (displayDate) payload.display_date = displayDate
            else if (editingNotice?.display_date) payload.display_date = null
            payload.home_visible = homeVisible; payload.related_tickers = tickers; payload.related_topics = relatedTopics
        } else if (displayDate || homeVisible || relatedTickers.trim() || relatedTopics.length) { setErr("소식 표시 설정이 아직 준비되지 않았어요. API와 데이터베이스 반영 후 다시 저장해 주세요"); return }
        // 내용만 수정할 때는 기존 종료 시각과 숨김 상태를 변경하지 않는다.
        const endChanged = !editingNotice || endsAt !== noticeEndDate(editingNotice.ends_at)
        if (endChanged && endsAt.trim()) {
            const date = endsAt.trim()
            const parsed = new Date(date + "T00:00:00Z")
            if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date) { setErr("종료일을 올바르게 입력해 주세요"); return }
            payload.ends_at = date + "T23:59:59+09:00"
            if (Date.parse(payload.ends_at) <= Date.now()) { setErr("종료일이 이미 지났어요"); return }
        } else if (editingNotice && endChanged) payload.ends_at = null
        if (artworkReady) {
            let imageUrl = thumbnailUrl
            if (preparedImage) {
                const token = loadToken()
                if (!token) { setErr("관리자 로그인이 필요해요"); return }
                setBusy("upload-notice"); setErr("")
                try {
                    const response = await fetch(`${apiBase}/api/admin?type=notices`, { method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify({ action: "upload_thumbnail", image_base64: preparedImage.split(",")[1] }) })
                    const uploaded = await response.json().catch(() => ({}))
                    if (!response.ok || typeof uploaded.url !== "string" || !uploaded.url.startsWith("https://")) throw new Error("이미지 업로드에 실패했어요. 초안은 그대로 유지됩니다")
                    imageUrl = uploaded.url; setThumbnailUrl(imageUrl); setPreparedImage("")
                } catch (error: any) { setErr(error.message || "이미지 업로드에 실패했어요"); setBusy(""); return }
            }
            payload.thumbnail_theme = thumbnailTheme; payload.thumbnail_url = imageUrl
        }
        const saved = await call("save-notice", "POST", payload, editingNotice ? "공지를 수정했어요. 반영에는 최대 약 1분이 걸려요" : siteWide ? "전체 알림 공지를 발행했어요. 반영에는 최대 약 1분이 걸려요" : "발행했어요")
        if (saved) resetForm()
    }

    const supportCall = async (it: any, action: string) => {
        if (onCanvas || busy) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        const key = action + it.id
        const payload: any = { id: it.id, action }
        if (action === "answer") {
            payload.answer = String(answerDrafts[it.id] ?? it.answer ?? "").trim()
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
            if (data.id !== it.id || (action === "answer" && (data.status !== "answered" || typeof data.answer !== "string" || !data.answer.trim()))) {
                throw new Error("저장 결과를 확인하지 못했어요. 초안을 유지했으니 새로고침 후 확인해 주세요")
            }
            supportRequest.current += 1
            setSupportLoading(false)
            setSupportItems((rows) => rows.map((row) => row.id === it.id ? { ...row, ...data } : row))
            setMsg(action === "answer" ? "답변을 저장했어요" : "상태를 변경했어요")
            setAnswerDrafts((drafts) => {
                const next = { ...drafts }
                delete next[it.id]
                return next
            })
            if (action === "answer" && supportFilter !== "all" && supportFilter !== "answered") setSupportFilter("answered")
            else loadSupport()
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
                <button onClick={adminTab === "notices" ? load : loadSupport} disabled={loading || supportLoading || !!busy} style={{ ...btn("transparent", C.vt), marginLeft: "auto", padding: "4px 8px" }}>
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

            {/* 작성·수정: 저장 도중 입력 변경으로 초안이 사라지지 않도록 잠근다. */}
            <fieldset disabled={!!busy} aria-label={editingNotice ? "공지 수정" : "새 공지 작성"} style={{ border: "none", padding: 0, margin: "14px 0 0", minWidth: 0, display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ fontSize: 13, fontWeight: 800, color: C.ink }}>{editingNotice ? "공지 수정" : "새 공지 작성"}</div>
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
                        목록 상단 고정
                    </label>
                </div>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, fontWeight: 700, color: C.sub, cursor: "pointer" }}>
                    <input type="checkbox" checked={siteWide} onChange={(e) => setSiteWide(e.target.checked)} />
                    전체 페이지에 알림
                </label>
                <div style={{ fontSize: 11.5, fontWeight: 600, color: C.faint, lineHeight: 1.55 }}>
                    {siteWideReady ? "새 공지는 기본으로 전체 페이지에 알려요. 원하지 않으면 체크를 해제해 주세요. 이미 닫은 공지는 내용을 수정해도 다시 뜨지 않아요." : siteWideMigration ? `${siteWideMigration}.sql 적용 후 새로고침하면 전체 알림을 사용할 수 있어요.` : "전체 알림 준비 확인 중이에요. 확인 후 발행하거나 체크를 해제해 주세요."}
                </div>
                <div>
                    <div style={label}>제목 (최대 120자)</div>
                    <input ref={titleInput} aria-label="공지 제목" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} placeholder="예: 커뮤니티 이용 안내" style={input} />
                </div>
                <fieldset disabled={!editorialReady} style={{ border: 0, padding: 14, margin: 0, background: C.field, borderRadius: 14, display: "grid", gap: 10 }}>
                    <legend style={{ ...label, padding: 0 }}>소식 표시 설정</legend>
                    <label style={{ fontSize: 12, fontWeight: 700 }}><input type="checkbox" checked={homeVisible} onChange={e => setHomeVisible(e.target.checked)} /> 홈 소식에 표시</label>
                    <label style={label}>글에 표시할 날짜 · 비우면 등록일<input aria-label="공지 표시 날짜" type="date" value={displayDate} onChange={e => setDisplayDate(e.target.value)} style={{ ...input, background: C.card, marginTop: 5 }} /></label>
                    <label style={label}>관련 종목 · 쉼표로 구분<input aria-label="관련 종목" value={relatedTickers} onChange={e => setRelatedTickers(e.target.value)} placeholder="AAPL, NVDA, 000660" style={{ ...input, background: C.card, marginTop: 5 }} /></label>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                        {([["13f", "거장 보유 종목"], ["report", "기업 리포트"], ["disclosure", "공시"], ["macro", "시장·경제"]] as const).map(([value, text]) => <label key={value} style={{ fontSize: 12, fontWeight: 700 }}><input type="checkbox" checked={relatedTopics.includes(value)} onChange={e => setRelatedTopics(rows => e.target.checked ? [...rows, value] : rows.filter(row => row !== value))} /> {text}</label>)}
                    </div>
                    <span style={{ color: C.faint, fontSize: 11.5, fontWeight: 600, lineHeight: 1.6 }}>{editorialReady ? "표시 날짜를 바꿔도 실제 등록 기록은 유지됩니다. 관련 종목·주제를 선택하면 해당 리포트의 함께 읽기에 연결돼요." : "소식 표시 설정을 준비 중이에요. 기존 공지는 계속 작성할 수 있어요."}</span>
                </fieldset>
                <div>
                    <div style={label}>본문 (선택 · 최대 2000자)</div>
                    <textarea aria-label="공지 본문" value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} rows={6} placeholder={"달라진 점을 편하게 적어 주세요.\n\n## 소제목\n- 주요 내용\n**강조할 문장**"} style={{ ...input, resize: "vertical", lineHeight: 1.7 }} />
                    <div style={{ fontSize: 11.5, fontWeight: 600, color: C.faint, marginTop: 5 }}>## 소제목 · - 목록 · **강조**를 쓸 수 있어요. 줄바꿈은 그대로 보여요.</div>
                </div>
                <section aria-label="공지 썸네일" style={{ padding: 14, borderRadius: 14, background: C.field }}>
                    <div style={{ color: C.ink, fontSize: 13, fontWeight: 800, marginBottom: 10 }}>썸네일</div>
                    <div style={{ height: 112, borderRadius: 12, overflow: "hidden", marginBottom: 12 }}><NoticeArtwork notice={draft} previewImage={preparedImage} /></div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <select aria-label="썸네일 그림" value={thumbnailTheme} onChange={event => { setThumbnailTheme(event.target.value); setThumbnailUrl(""); setPreparedImage("") }} style={{ ...input, width: "auto", background: C.card, fontWeight: 700, paddingRight: 28 }}>
                            {NOTICE_THEMES.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
                        </select>
                        <button type="button" onClick={() => imageInput.current?.click()} style={btn(C.card, C.sub)}>내 이미지 선택</button>
                        <input ref={imageInput} type="file" accept="image/png,image/jpeg,image/webp" aria-label="썸네일 이미지 파일" style={{ display: "none" }} onChange={async event => {
                            const file = event.target.files?.[0]; event.target.value = ""
                            if (!file) return
                            setBusy("prepare-image"); setErr("")
                            try { setPreparedImage(await prepareNoticeImage(file)); setThumbnailUrl("") }
                            catch (error: any) { setErr(error.message || "이미지를 열지 못했어요") }
                            finally { setBusy("") }
                        }} />
                        {(thumbnailUrl || preparedImage) ? <button type="button" onClick={() => { setThumbnailUrl(""); setPreparedImage("") }} style={btn(C.card, C.sub)}>기본 그림으로</button> : null}
                    </div>
                    <div style={{ fontSize: 11.5, fontWeight: 600, lineHeight: 1.6, color: C.faint, marginTop: 9 }}>
                        {thumbnailUrl || preparedImage ? "선택한 이미지는 공지와 함께 공개돼요. 미리보기에서 잘리는 부분을 확인해 주세요." : thumbnailTheme === "auto" ? `제목·본문에 맞춰 ‘${themeLabel}’ 그림을 골랐어요. 원하면 직접 바꿀 수 있어요.` : `‘${themeLabel}’ 그림을 사용해요.`}
                    </div>
                </section>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <div style={{ flex: "1 1 200px", minWidth: 0 }}>
                        <div style={label}>링크 (선택)</div>
                        <input aria-label="공지 링크" value={link} onChange={(e) => setLink(e.target.value)} maxLength={500} placeholder="https:// 또는 /lab · 비우면 공지 본문" style={input} />
                    </div>
                    <div style={{ flex: "0 1 170px" }}>
                        <div style={label}>종료일 (선택 · 비우면 무기한)</div>
                        <input aria-label="공지 종료일" type="date" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} style={input} />
                    </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                    <button ref={previewTrigger} type="button" onClick={() => setPreviewOpen(true)} style={btn(C.vtS, C.vt)}>팝업 미리보기</button>
                    {editingNotice ? <button onClick={() => { resetForm(); setErr(""); setMsg("") }} style={btn(C.field, C.sub)}>수정 취소</button> : null}
                    <button onClick={publish} disabled={!!busy} style={{ ...btn(C.vt, C.onAccent), flex: 1 }}>
                        {busy === "upload-notice" ? "이미지 저장 중" : busy === "save-notice" ? "저장 중" : editingNotice ? "수정 저장" : "발행"}
                    </button>
                </div>
            </fieldset>
            {previewOpen && <NoticeDialog notice={draft} triggerRef={previewTrigger} onClose={() => setPreviewOpen(false)} preview previewImage={preparedImage} />}

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
                        <div key={n.id} style={{ display: "flex", alignItems: "flex-start", flexWrap: "wrap", gap: 10, padding: "11px 2px", borderBottom: `1px solid ${C.line}` }}>
                            <span style={{ flexShrink: 0, marginTop: 2, fontSize: 10.5, fontWeight: 800, color: n.kind === "event" ? C.onAccent : C.vt, background: n.kind === "event" ? C.vt : C.vtS, borderRadius: 6, padding: "3px 7px" }}>
                                {n.kind === "event" ? "이벤트" : "공지"}
                            </span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 13, fontWeight: 800, color: n.is_active ? C.ink : C.faint }}>
                                    {n.title}
                                    {n.pinned ? <span style={{ marginLeft: 6, fontSize: 11, color: C.vt }}>고정</span> : null}
                                    {n.site_wide ? <span style={{ marginLeft: 6, fontSize: 11, fontWeight: 700, color: C.vt }}>전체 알림</span> : null}
                                </div>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3 }}>
                                    {fmtDate(n.display_date || n.created_at)}
                                    {n.ends_at ? ` · ${fmtDate(n.ends_at)} 종료` : " · 무기한"}
                                    {n.is_active ? "" : " · 숨김"}
                                </div>
                            </div>
                            <button onClick={() => editNotice(n)} disabled={!!busy} aria-label={`${n.title || "공지"} 수정`} style={{ ...btn(C.vtS, C.vt), padding: "6px 10px", flexShrink: 0 }}>
                                {editingNotice?.id === n.id ? "수정 중" : "수정"}
                            </button>
                            <button
                                onClick={() => call("t" + n.id, "POST", { id: n.id, is_active: !n.is_active }, n.is_active ? "숨겼어요" : "다시 노출해요")}
                                disabled={!!busy || editingNotice?.id === n.id}
                                style={{ ...btn(C.field, C.sub), padding: "6px 10px", flexShrink: 0 }}
                            >
                                {n.is_active ? "숨김" : "노출"}
                            </button>
                            <button
                                onClick={() => {
                                    if (typeof window !== "undefined" && !window.confirm("삭제할까요? 되돌릴 수 없어요.")) return
                                    call("d" + n.id, "DELETE", { id: n.id }, "삭제했어요")
                                }}
                                disabled={!!busy || editingNotice?.id === n.id}
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
                            <button key={key} onClick={() => setSupportFilter(key)} disabled={!!busy} aria-pressed={supportFilter === key} style={{ ...btn(supportFilter === key ? C.vt : C.field, supportFilter === key ? C.onAccent : C.sub), padding: "7px 11px", flexShrink: 0 }}>{label}</button>
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

                                {it.answer ? (
                                    <div aria-label={`${it.title} 저장된 답변`} style={{ marginTop: 10, padding: "12px", borderRadius: 10, background: C.card }}>
                                        <div style={{ color: C.vt, fontSize: 11.5, fontWeight: 700, marginBottom: 6 }}>저장된 답변{it.answered_at ? ` · ${fmtDate(it.answered_at)}` : ""}</div>
                                        <div style={{ color: C.sub, fontSize: 12.5, fontWeight: 600, whiteSpace: "pre-wrap", overflowWrap: "anywhere", lineHeight: 1.6 }}>{it.answer}</div>
                                    </div>
                                ) : null}
                                <textarea
                                    value={answer}
                                    disabled={!!busy}
                                    onChange={(e) => setAnswerDrafts((drafts) => ({ ...drafts, [it.id]: e.target.value.slice(0, 3000) }))}
                                    maxLength={3000}
                                    rows={3}
                                    aria-label={`${it.title} 답변`}
                                    placeholder={it.kind === "feedback" ? "피드백 처리 결과를 남겨주세요" : "초보자도 이해할 수 있게 답변해 주세요"}
                                    style={{ ...input, resize: "vertical", lineHeight: 1.55, marginTop: 10, background: C.card }}
                                />
                                <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginTop: 8 }}>
                                    <button onClick={() => supportCall(it, "answer")} disabled={!!busy} style={{ ...btn(C.vt, C.onAccent), padding: "8px 11px" }}>{busy === "answer" + it.id ? "저장 중" : it.status === "answered" ? "답변 수정" : "답변 완료"}</button>
                                    <button onClick={() => supportCall(it, it.status === "closed" ? "reopen" : "close")} disabled={!!busy} style={{ ...btn(C.card, C.sub), padding: "8px 11px" }}>{it.status === "closed" ? "다시 열기" : "종료"}</button>
                                    {it.kind === "question" && it.status === "answered" && it.publish_consent ? <button onClick={() => supportCall(it, it.hidden ? "unhide" : "hide")} disabled={!!busy} style={{ ...btn(it.hidden ? C.greenS : C.upS, it.hidden ? C.green : C.up), padding: "8px 11px" }}>{it.hidden ? "공개 복원" : "공개 숨김"}</button> : null}
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

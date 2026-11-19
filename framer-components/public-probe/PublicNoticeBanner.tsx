import * as React from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"

// Keep: site_wide is an explicit admin opt-in (038), never inferred from pinned.
// Keep: the banner stays inline; clicks open its body, never skip to the related link.
// No notice/failed request = no banner. Dialog close does not dismiss the banner.
// CSS follows the shared body theme; dismissal contains IDs only, not notice text.
const DEFAULT_API = "https://project-yw131.vercel.app"
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const STORAGE_KEY = "an_site_notice_dismissed_v1"
const DISMISS_EVENT = "an-site-notice-dismissed"
const POLL_MS = 30_000
type Notice = {
    id: string
    title: string
    body?: string
    kind?: string
    link?: string
    pinned?: boolean
    site_wide?: boolean
    is_active?: boolean
    starts_at?: string
    ends_at?: string
    created_at?: string
    display_date?: string
    thumbnail_theme?: string
    thumbnail_url?: string
}
type Props = {
    apiBase?: string
    communityPath?: string
    updatesPath?: string
    previewNotice?: boolean
    paddingX?: number
    style?: React.CSSProperties
}
type CacheEntry = { at: number; items: Notice[]; pending?: Promise<Notice[]> }
const cache = new Map<string, CacheEntry>()
let memoryDismissed: string[] = []

function safeLink(value: unknown): string {
    if (typeof value !== "string") return ""
    const v = value.trim()
    if (!v || v.length > 500 || /[\u0000-\u001f\\]/.test(v)) return ""
    if (v.startsWith("/") && !v.startsWith("//")) return v
    try {
        const u = new URL(v)
        return u.protocol === "https:" &&
            u.hostname &&
            !u.username &&
            !u.password
            ? v
            : ""
    } catch {
        return ""
    }
}

function noticeHref(n: Notice, communityPath: string): string {
    const path = safeLink(communityPath) || "/community"
    const url = new URL(path, "https://alphanest.invalid")
    url.searchParams.set("tab", "support")
    url.searchParams.set("notice", n.id)
    url.hash = "an-notice-" + n.id
    return path.startsWith("/")
        ? url.pathname + url.search + url.hash
        : url.href
}

// Keep related links separate from the notice's own readable/shareable page.
function noticeArticleHref(n: Notice, updatesPath: string): string {
    const safe = safeLink(updatesPath)
    const path = safe.startsWith("/") ? safe : "/updates"
    const url = new URL(path, "https://alphanest.invalid")
    url.searchParams.set("notice", n.id)
    url.hash = ""
    return url.pathname + url.search
}

function activeNotices(
    items: Notice[],
    dismissed: string[],
    now: number
): Notice[] {
    const seen = new Set(dismissed)
    return items
        .filter((n) => {
            if (
                !n ||
                typeof n.id !== "string" ||
                !n.id ||
                typeof n.title !== "string" ||
                !n.title.trim()
            )
                return false
            if (n.site_wide !== true || n.is_active === false || seen.has(n.id))
                return false
            if (n.starts_at && !(Date.parse(n.starts_at) <= now)) return false
            if (n.ends_at && !(Date.parse(n.ends_at) > now)) return false
            return true
        })
        .sort(
            (a, b) =>
                Number(b.pinned === true) - Number(a.pinned === true) ||
                (Date.parse(b.created_at || "") || 0) -
                    (Date.parse(a.created_at || "") || 0)
        )
}

function readDismissed(): string[] {
    if (typeof window === "undefined") return []
    try {
        const parsed = JSON.parse(
            window.localStorage.getItem(STORAGE_KEY) || "[]"
        )
        if (Array.isArray(parsed))
            memoryDismissed = [
                ...new Set([
                    ...memoryDismissed,
                    ...parsed.filter(
                        (x) => typeof x === "string" && x.length <= 128
                    ),
                ]),
            ].slice(-200)
    } catch {
        /* Storage may be disabled; this tab still remembers. */
    }
    return memoryDismissed
}

function dismissNotice(id: string): void {
    if (typeof window === "undefined") return
    memoryDismissed = [...new Set([...readDismissed(), id])].slice(-200)
    try {
        window.localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify(memoryDismissed)
        )
    } catch {
        /* In-memory fallback. */
    }
    window.dispatchEvent(new Event(DISMISS_EVENT))
}

async function fetchNotices(base: string): Promise<Notice[]> {
    const previous = cache.get(base)
    if (previous?.pending) return previous.pending
    if (previous && Date.now() - previous.at < 15_000) return previous.items
    const entry: CacheEntry = { at: 0, items: [] }
    cache.set(base, entry)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 8_000)
    entry.pending = (async () => {
        try {
            const response = await fetch(base + "/api/notices?placement=site", {
                signal: controller.signal,
                credentials: "omit",
            })
            if (!response.ok) throw new Error("Notice fetch failed")
            const data = await response.json()
            entry.items = Array.isArray(data.items) ? data.items : []
        } catch {
            entry.items = []
        } finally {
            // Do not keep withdrawn/stale banners on failure.
            clearTimeout(timeout)
            entry.at = Date.now()
            entry.pending = undefined
        }
        return entry.items
    })()
    return entry.pending
}

const CSS = `
.an-site-notice{--sn-card:#fff;--sn-ink:#4e5968;--sn-muted:#8b95a1;--sn-accent:#6c5ce7;--sn-soft:#f0edff;container-type:inline-size}
body[data-framer-theme="dark"] .an-site-notice{--sn-card:#171c23;--sn-ink:#e3e7ec;--sn-muted:#9aa4b1;--sn-accent:#a99bff;--sn-soft:#241f3a}
.an-site-notice-bar{display:flex;align-items:center;gap:4px;min-height:52px;background:var(--sn-card);border:0;border-radius:18px;padding:4px 6px 4px 16px;box-sizing:border-box;color:var(--sn-ink)}
.an-site-notice-link{display:flex;align-items:center;gap:10px;flex:1;min-width:0;min-height:44px;color:inherit;text-decoration:none;font-weight:700}
.an-site-notice-badge{flex-shrink:0;border-radius:999px;padding:5px 9px;background:var(--sn-soft);color:var(--sn-accent);font-size:12px;font-weight:700;line-height:1.3}
.an-site-notice-title{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere;min-width:0;flex:1;font-size:14px;line-height:1.5;font-weight:700}
.an-site-notice-more{white-space:nowrap;color:var(--sn-muted);font-size:12px;font-weight:600}
.an-site-notice-close{display:grid;place-items:center;flex-shrink:0;width:44px;height:44px;border:0;border-radius:12px;background:transparent;color:var(--sn-muted);cursor:pointer;padding:0;font:inherit}
.an-site-notice a:focus-visible,.an-site-notice button:not(.an-site-notice-close):focus-visible{outline:0;box-shadow:inset 0 -2px 0 var(--sn-muted)}
/* Keep close controls icon-only, including native dialog autofocus. */
.an-site-notice .an-site-notice-close,.an-site-notice-dialog .an-site-notice-close{appearance:none;-webkit-appearance:none;border:0!important;outline:none!important;box-shadow:none!important;background:transparent!important}
.an-site-notice-close:focus-visible{color:var(--sn-ink)}
.an-site-notice-close:focus-visible path{stroke-width:2.4}
.an-site-notice-close:hover{color:var(--sn-ink)}
.an-site-notice-dialog{width:min(640px,calc(100vw - 32px));max-height:calc(100vh - 48px);max-height:calc(100dvh - 48px);margin:auto;padding:0;border:0;border-radius:24px;background:var(--sn-card);color:var(--sn-ink);font:inherit;box-shadow:0 24px 72px rgba(0,0,0,.18);overflow:hidden;box-sizing:border-box}
.an-site-notice-dialog[open]{display:flex;flex-direction:column}
.an-site-notice-dialog::backdrop{background:rgba(15,23,42,.36)}
.an-site-notice-dialog-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 20px 4px;flex-shrink:0}
.an-site-notice-dialog-scroll{padding:8px 28px 24px;overflow:auto;overscroll-behavior:contain;min-height:0;overflow-wrap:anywhere}
.an-site-notice-dialog h2{margin:0;font-size:24px;line-height:1.4;letter-spacing:-.5px;font-weight:800}
.an-site-notice-dialog time{display:block;margin-top:10px;font-size:13px;font-weight:600;color:var(--sn-muted)}
.an-site-notice-body{margin:24px 0 0;white-space:pre-wrap;font-size:15px;line-height:1.85;font-weight:600}
.an-site-notice-dialog-actions{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;padding:16px 28px 24px;flex-shrink:0}
.an-site-notice-archive{font-size:13px;font-weight:700;color:var(--sn-muted);text-decoration:none;padding:10px 0}
.an-site-notice-related{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 16px;box-sizing:border-box;border-radius:12px;background:var(--sn-soft);color:var(--sn-accent);text-decoration:none;font-size:14px;font-weight:700}
@media(max-width:480px){.an-site-notice-dialog{width:calc(100vw - 24px);max-height:calc(100dvh - 24px);border-radius:20px}.an-site-notice-dialog-scroll{padding:8px 20px 20px}.an-site-notice-dialog h2{font-size:21px}.an-site-notice-dialog-actions{padding:12px 20px 20px}.an-site-notice-dialog-head{padding:12px 12px 4px}}
@container (max-width:480px){.an-site-notice-more{display:none}.an-site-notice-bar{padding-left:12px}.an-site-notice-title{font-size:13px}.an-site-notice-link{gap:8px}}
`

// Shared by the banner and admin preview. Keep one renderer for both surfaces.
export const NOTICE_THEMES = [
    ["auto", "내용에 맞게"], ["report", "리포트"], ["feature", "새 기능"],
    ["event", "이벤트"], ["maintenance", "점검"], ["community", "커뮤니티"], ["general", "소식"],
] as const

export function resolveNoticeTheme(notice: Pick<Notice, "title" | "body" | "kind" | "thumbnail_theme">): string {
    const chosen = notice.thumbnail_theme
    if (chosen && chosen !== "auto" && NOTICE_THEMES.some(([id]) => id === chosen)) return chosen
    const rules = [
        ["maintenance", /점검|장애|복구|중단|접속 오류|maintenance/i],
        ["event", /이벤트|참여|선물|경품|당첨|event/i],
        ["report", /리포트|보고서|재무|공시|분석|report/i],
        ["community", /커뮤니티|소통|피드백|회원|community/i],
        ["feature", /업데이트|기능|추가|개선|차트|검색|update/i],
    ] as const
    // Title wins: a short body reference should not change the notice's subject.
    for (const text of [notice.title || "", notice.kind === "event" ? "이벤트" : "", notice.body || ""])
        for (const [theme, pattern] of rules) if (pattern.test(text)) return theme
    return "general"
}

export function NoticeArtwork({ notice, previewImage = "" }: { notice: Pick<Notice, "title" | "body" | "kind" | "thumbnail_theme" | "thumbnail_url">; previewImage?: string }) {
    const theme = resolveNoticeTheme(notice)
    const [failedUrl, setFailedUrl] = React.useState("")
    const custom = /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(previewImage) && previewImage.length < 350050 ? previewImage : safeLink(notice.thumbnail_url)
    if ((custom.startsWith("https://") || custom.startsWith("data:image/png;base64,")) && custom !== failedUrl)
        return <img className="an-notice-art" src={custom} alt="" referrerPolicy="no-referrer" onError={() => setFailedUrl(custom)} style={{ display: "block", width: "100%", height: "100%", objectFit: "contain" }} />
    return <svg className="an-notice-art" viewBox="0 0 600 180" fill="none" aria-hidden="true" style={{ display: "block", width: "100%", height: "100%" }}>
        <rect width="600" height="180" rx="20" fill="#F2F0FC" />
        <circle cx="310" cy="92" r="75" fill="#E7E1FF" />
        <circle cx="125" cy="56" r="5" fill="#B8ADF6" /><circle cx="475" cy="123" r="7" fill="#CEC6FA" />
        <path d="M450 36v16m-8-8h16M162 127v12m-6-6h12" stroke="#B3A6EF" strokeWidth="3" strokeLinecap="round" />
        {theme === "report" ? <>
            <g transform="rotate(-9 268 95)"><rect x="217" y="24" width="108" height="131" rx="13" fill="#B3A2F2" /></g>
            <rect x="250" y="20" width="114" height="140" rx="14" fill="white" />
            <rect x="268" y="39" width="46" height="7" rx="3.5" fill="#6750C7" /><rect x="268" y="55" width="73" height="5" rx="2.5" fill="#E4DFF5" />
            <rect x="269" y="104" width="14" height="33" rx="4" fill="#CDC2F7" /><rect x="293" y="88" width="14" height="49" rx="4" fill="#A18BE8" /><rect x="317" y="73" width="14" height="64" rx="4" fill="#7860D4" />
            <circle cx="374" cy="119" r="27" fill="#DFF4E9" /><path d="m361 119 9 9 16-18" stroke="#4D9274" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
        </> : theme === "feature" ? <>
            <rect x="209" y="36" width="172" height="119" rx="16" fill="white" /><path d="M209 65h172" stroke="#E7E1F7" strokeWidth="2" />
            <circle cx="225" cy="51" r="3" fill="#AA98E7" /><circle cx="237" cy="51" r="3" fill="#D0C4F3" />
            <rect x="225" y="79" width="58" height="59" rx="9" fill="#DFD7F7" /><rect x="295" y="81" width="65" height="8" rx="4" fill="#B4A2E9" /><rect x="295" y="99" width="48" height="6" rx="3" fill="#E8E2F8" /><rect x="295" y="116" width="58" height="6" rx="3" fill="#E8E2F8" />
            <path d="m380 20 8 23 24 8-24 8-8 24-8-24-24-8 24-8z" fill="#8268DA" /><path d="M245 103h18m-9-9v18" stroke="#8064CF" strokeWidth="4" strokeLinecap="round" />
        </> : theme === "event" ? <>
            <rect x="239" y="76" width="126" height="79" rx="10" fill="#AB96EB" /><rect x="230" y="62" width="144" height="30" rx="9" fill="#D3C7F7" /><path d="M301 65v89" stroke="white" strokeWidth="15" />
            <path d="M301 60c-33 1-48-14-37-25 12-12 34 2 37 25Zm0 0c33 1 48-14 37-25-12-12-34 2-37 25Z" stroke="#8265D1" strokeWidth="8" strokeLinejoin="round" />
            <path d="m203 62-9-13m204 57 14-6m-50-65 8-13" stroke="#AB96EB" strokeWidth="6" strokeLinecap="round" /><circle cx="203" cy="120" r="7" fill="#F1CC90" /><circle cx="403" cy="51" r="7" fill="#C9DFCD" />
        </> : theme === "maintenance" ? <>
            <rect x="222" y="35" width="156" height="110" rx="16" fill="white" /><rect x="239" y="53" width="122" height="64" rx="9" fill="#DFD7F7" /><path d="M285 145v14h32v-14" stroke="#A48AE3" strokeWidth="8" strokeLinejoin="round" />
            <path d="m280 79 12 13 24-28" stroke="#8F75D6" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="373" cy="126" r="27" fill="#F9EBCD" /><path d="M373 110v16l10 7" stroke="#AE854A" strokeWidth="4" strokeLinecap="round" />
        </> : theme === "community" ? <>
            <path d="M229 35h100a16 16 0 0 1 16 16v43a16 16 0 0 1-16 16h-61l-25 19v-19h-14a16 16 0 0 1-16-16V51a16 16 0 0 1 16-16Z" fill="white" />
            <path d="M304 83h70a14 14 0 0 1 14 14v30a14 14 0 0 1-14 14h-10v16l-22-16h-38a14 14 0 0 1-14-14V97a14 14 0 0 1 14-14Z" fill="#AF98EB" />
            <path d="M238 57h75m-75 16h52M311 105h54m-54 16h36" stroke="#D8CDF5" strokeWidth="6" strokeLinecap="round" />
        </> : <>
            <rect x="230" y="35" width="140" height="117" rx="18" fill="white" /><path d="M232 75 300 115l68-40" stroke="#C7B7EF" strokeWidth="4" strokeLinejoin="round" /><path d="m234 145 46-44m85 44-45-44" stroke="#E3DAF6" strokeWidth="3" />
            <circle cx="300" cy="54" r="29" fill="#A48ADE" /><path d="M300 40v15m0 11v1" stroke="white" strokeWidth="5" strokeLinecap="round" />
        </>}
    </svg>
}

function inlineNoticeText(text: string): React.ReactNode {
    return text.split(/(\*\*[^*\n]+\*\*)/g).map((part, index) => part.startsWith("**") && part.endsWith("**")
        ? <strong key={index}>{part.slice(2, -2)}</strong> : part)
}

export function NoticeBody({ text }: { text?: string }) {
    const lines = (text || "").trim().split(/\r?\n/)
    if (!text?.trim()) return <p>공지 내용이 아직 등록되지 않았습니다.</p>
    const blocks: React.ReactNode[] = []
    for (let i = 0; i < lines.length;) {
        if (!lines[i].trim()) { i++; continue }
        const heading = /^#{1,3}\s+(.+)$/.exec(lines[i])
        if (heading) { blocks.push(<h3 key={i}>{inlineNoticeText(heading[1])}</h3>); i++; continue }
        const list = /^\s*(?:[-*•]|\d+[.)])\s+/.test(lines[i])
        const start = i
        if (list) {
            const ordered = /^\s*\d+[.)]\s+/.test(lines[i])
            const pattern = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*•]\s+/
            const entries: React.ReactNode[] = []
            while (i < lines.length && pattern.test(lines[i])) { entries.push(<li key={i}>{inlineNoticeText(lines[i].replace(pattern, ""))}</li>); i++ }
            blocks.push(ordered ? <ol key={start}>{entries}</ol> : <ul key={start}>{entries}</ul>)
        } else {
            const paragraph: string[] = []
            while (i < lines.length && lines[i].trim() && !/^#{1,3}\s|^\s*(?:[-*•]|\d+[.)])\s+/.test(lines[i])) paragraph.push(lines[i++])
            blocks.push(<p key={start}>{inlineNoticeText(paragraph.join("\n"))}</p>)
        }
    }
    return <>{blocks}</>
}

const ARTICLE_CSS = `
.an-site-notice-dialog{--sn-card:#fff;--sn-ink:#333d4b;--sn-muted:#6b7684;--sn-accent:#6c5ce7;--sn-soft:#f0edff;width:min(660px,calc(100vw - 32px));font-family:${FONT}}
body[data-framer-theme="dark"] .an-site-notice-dialog{--sn-card:#171c23;--sn-ink:#e3e7ec;--sn-muted:#9aa4b1;--sn-accent:#a99bff;--sn-soft:#241f3a}
.an-site-notice-dialog-head{padding:14px 18px 6px 28px}
.an-site-notice-dialog-scroll{padding:8px 28px 12px}
.an-notice-cover{height:176px;overflow:hidden;border-radius:18px;margin-bottom:24px;background:var(--sn-soft)}
.an-site-notice-dialog h2{font-size:26px;line-height:1.4;color:var(--sn-ink);letter-spacing:-.7px}
.an-site-notice-body{margin-top:26px;white-space:normal;font-size:15px;line-height:1.85}
.an-site-notice-body p{margin:0 0 18px;white-space:pre-wrap}
.an-site-notice-body h3{font-size:17px;font-weight:800;margin:28px 0 10px;line-height:1.5;letter-spacing:-.3px}
.an-site-notice-body strong{font-weight:800}
.an-site-notice-body ul,.an-site-notice-body ol{padding-left:22px;margin:12px 0 22px}
.an-site-notice-body li{padding-left:3px;margin:8px 0;white-space:pre-wrap}
.an-site-notice-body li::marker{color:var(--sn-accent);font-weight:700}
.an-site-notice-dialog-actions{position:relative;padding:16px 28px 24px;gap:16px}.an-site-notice-dialog-actions::before{content:"";position:absolute;z-index:0;pointer-events:none;left:0;right:0;top:-10px;height:10px;background:linear-gradient(to bottom,transparent,var(--sn-card))}.an-site-notice-dialog-actions>*{position:relative;z-index:1}
.an-site-notice-related{background:#6c5ce7;color:white;padding:0 20px;margin-left:auto}
.an-site-notice-archive{font-size:12px}
.an-site-notice-dialog a:focus-visible,.an-site-notice-dialog button:not(.an-site-notice-close):focus-visible{outline:2px solid var(--sn-accent);outline-offset:2px}
@media(max-width:480px){.an-site-notice-dialog-head{padding:10px 12px 4px 20px}.an-site-notice-dialog-scroll{padding:8px 20px 8px}.an-notice-cover{height:124px;margin-bottom:20px}.an-site-notice-dialog h2{font-size:22px}.an-site-notice-body{font-size:14px;line-height:1.8}.an-site-notice-dialog-actions{padding:12px 20px 20px;gap:8px}.an-site-notice-related{padding:0 12px;font-size:13px}.an-site-notice-archive{font-size:11px}}
`

export function NoticeDialog({ notice, communityPath = "/community", updatesPath = "/updates", triggerRef, onClose, preview = false, previewImage = "" }: {
    notice: Notice
    communityPath?: string
    updatesPath?: string
    triggerRef: React.RefObject<HTMLElement | null>
    onClose: () => void
    preview?: boolean
    previewImage?: string
}) {
    const dialog = React.useRef<HTMLDialogElement>(null)
    const titleId = React.useId()
    React.useEffect(() => {
        const element = dialog.current
        if (!element) return
        element.showModal()
        return () => {
            if (element.open) element.close()
            triggerRef.current?.focus({ preventScroll: true })
        }
    }, [triggerRef])
    const related = safeLink(notice.link)
    const publishedAt = Date.parse(notice.display_date || notice.created_at || "")
    const date = Number.isFinite(publishedAt)
        ? new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "long", day: "numeric", timeZone: "Asia/Seoul" }).format(publishedAt)
        : ""
    return <dialog ref={dialog} className="an-site-notice-dialog" aria-labelledby={titleId}
        onCancel={event => { event.preventDefault(); onClose() }}
        onClose={event => { if (!event.currentTarget.open) onClose() }}
        onClick={event => {
            if (event.target !== event.currentTarget) return
            const rect = event.currentTarget.getBoundingClientRect()
            if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose()
        }}>
        <style>{CSS + ARTICLE_CSS}</style>
        <div className="an-site-notice-dialog-head">
            <span className="an-site-notice-badge">{preview ? "미리보기 · " : ""}{notice.kind === "event" ? "이벤트" : "공지"}</span>
            <button type="button" className="an-site-notice-close" aria-label="공지 본문 닫기" autoFocus onClick={onClose}>
                <svg width="20" height="20" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
            </button>
        </div>
        <div className="an-site-notice-dialog-scroll">
            <div className="an-notice-cover"><NoticeArtwork notice={notice} previewImage={preview ? previewImage : ""} /></div>
            <h2 id={titleId}>{notice.title}</h2>
            {date && <time dateTime={new Date(publishedAt).toISOString()}>{date}</time>}
            <div className="an-site-notice-body"><NoticeBody text={notice.body} /></div>
        </div>
        <div className="an-site-notice-dialog-actions">
            {preview ? <span className="an-site-notice-archive">발행 전 미리보기</span> : <a className="an-site-notice-archive" href={updatesPath ? noticeArticleHref(notice, updatesPath) : noticeHref(notice, communityPath)}>소식 페이지에서 보기</a>}
            {related && <a className="an-site-notice-related" href={related} target={related.startsWith("https://") ? "_blank" : undefined} rel="noopener noreferrer">관련 페이지 열기 ↗</a>}
        </div>
    </dialog>
}

/** @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 * @framerIntrinsicWidth 1000
 * @framerIntrinsicHeight 60
 */
export default function PublicNoticeBanner({
    apiBase = DEFAULT_API,
    communityPath = "/community",
    updatesPath = "/updates",
    previewNotice = true,
    paddingX = 14,
    style,
}: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const base = apiBase.replace(/\/+$/, "")
    const [items, setItems] = React.useState<Notice[]>([])
    const [dismissed, setDismissed] = React.useState<string[]>([])
    const [ready, setReady] = React.useState(false)
    const [now, setNow] = React.useState(0)
    const [openId, setOpenId] = React.useState<string | null>(null)
    const triggerRef = React.useRef<HTMLAnchorElement>(null)

    React.useEffect(() => {
        if (onCanvas) return
        let alive = true
        setItems([])
        setReady(false)
        const syncDismissed = () => {
            setDismissed([...readDismissed()])
            setNow(Date.now())
        }
        const refresh = async () => {
            const rows = await fetchNotices(base)
            if (alive) {
                setItems(rows)
                setReady(true)
                setNow(Date.now())
            }
        }
        const onVisible = () => {
            if (document.visibilityState === "visible") {
                syncDismissed()
                void refresh()
            }
        }
        syncDismissed()
        void refresh()
        const timer = window.setInterval(() => {
            if (document.visibilityState !== "hidden") void refresh()
        }, POLL_MS)
        window.addEventListener("storage", syncDismissed)
        window.addEventListener(DISMISS_EVENT, syncDismissed)
        document.addEventListener("visibilitychange", onVisible)
        return () => {
            alive = false
            window.clearInterval(timer)
            window.removeEventListener("storage", syncDismissed)
            window.removeEventListener(DISMISS_EVENT, syncDismissed)
            document.removeEventListener("visibilitychange", onVisible)
        }
    }, [base, onCanvas])

    // Expire already-rendered data at its boundary, not just on the next network poll.
    React.useEffect(() => {
        if (onCanvas || !ready) return
        const boundaries = items
            .flatMap((n) => [n.starts_at, n.ends_at])
            .map((v) => Date.parse(v || ""))
            .filter((t) => t > Date.now())
        if (!boundaries.length) return
        const timer = window.setTimeout(
            () => setNow(Date.now()),
            Math.min(
                2_147_000_000,
                Math.max(1, Math.min(...boundaries) - Date.now() + 1)
            )
        )
        return () => window.clearTimeout(timer)
    }, [items, now, ready, onCanvas])

    const notice =
        onCanvas && previewNotice
            ? {
                  id: "canvas-preview",
                  title: "미리보기 · 새 공지와 서비스 소식을 확인하세요",
                  kind: "notice",
                  site_wide: true,
              }
            : ready
              ? activeNotices(items, dismissed, now)[0]
              : undefined
    React.useEffect(() => setOpenId(null), [notice?.id])
    if (!notice) return null
    const href = updatesPath ? noticeArticleHref(notice, updatesPath) : noticeHref(notice, communityPath)
    const external = /^https:\/\//.test(href)
    return (
        <aside
            className="an-site-notice"
            aria-label="서비스 공지"
            style={{
                ...style,
                width: "100%",
                maxWidth: 1000,
                minWidth: 0,
                boxSizing: "border-box",
                paddingInline: Number.isFinite(paddingX)
                    ? Math.max(0, Math.min(80, paddingX))
                    : 14,
                fontFamily: FONT,
                fontWeight: 600,
            }}
        >
            <style>{CSS}</style>
            <div className="an-site-notice-bar">
                <a
                    ref={triggerRef}
                    className="an-site-notice-link"
                    href={onCanvas ? undefined : href}
                    target={external ? "_blank" : undefined}
                    rel={external ? "noopener noreferrer" : undefined}
                    aria-haspopup="dialog"
                    aria-expanded={openId === notice.id}
                    onClick={event => {
                        if (onCanvas || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return
                        event.preventDefault()
                        event.currentTarget.focus({ preventScroll: true })
                        setOpenId(notice.id)
                    }}
                >
                    <span className="an-site-notice-badge">
                        {notice.kind === "event" ? "이벤트" : "공지"}
                    </span>
                    <span className="an-site-notice-title">{notice.title}</span>
                    <span className="an-site-notice-more">자세히 보기 ›</span>
                </a>
                <button
                    type="button"
                    className="an-site-notice-close"
                    aria-label="이 공지 닫기"
                    onClick={() => {
                        if (!onCanvas) dismissNotice(notice.id)
                    }}
                >
                    <svg
                        width="16"
                        height="16"
                        viewBox="0 0 16 16"
                        fill="none"
                        aria-hidden="true"
                    >
                        <path
                            d="m4 4 8 8M12 4l-8 8"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                        />
                    </svg>
                </button>
            </div>
            {openId === notice.id && <NoticeDialog notice={notice} communityPath={communityPath} updatesPath={updatesPath} triggerRef={triggerRef} onClose={() => setOpenId(null)} />}
        </aside>
    )
}

addPropertyControls(PublicNoticeBanner, {
    apiBase: {
        type: ControlType.String,
        title: "API Base",
        defaultValue: DEFAULT_API,
    },
    communityPath: {
        type: ControlType.String,
        title: "공지 목록",
        defaultValue: "/community",
    },
    updatesPath: {
        type: ControlType.String,
        title: "소식 페이지",
        defaultValue: "/updates",
        description: "팝업에서 이어 읽는 경로. 비우면 기존 공지 목록을 사용합니다.",
    },
    previewNotice: {
        type: ControlType.Boolean,
        title: "캔버스 예시",
        defaultValue: true,
    },
    paddingX: {
        type: ControlType.Number,
        title: "좌우 패딩",
        defaultValue: 14,
        min: 0,
        max: 80,
        step: 1,
        unit: "px",
        description: "공지 카드 바깥쪽 좌우 여백",
    },
})

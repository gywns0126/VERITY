import * as React from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { NoticeArtwork, NoticeBody, resolveNoticeTheme } from "https://framer.com/m/PublicNoticeBanner-WLqzZR.js"

// Keep: service updates use the existing public notices API and its publication RLS.
// No second CMS, generated article text, auth token, or sample content in production.
// ends_at still means publication expiry. Do not silently republish expired notices.
const API = "https://project-yw131.vercel.app"
// Original AlphaNest logo asset, shared with the live PC navigation. Do not redraw.
const LOGO = "https://framerusercontent.com/images/h1Mv8kde2W0olUvTjfUYyU5pHEs.svg"
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i
type Notice = {
    id: string; title: string; body?: string; kind?: string; link?: string
    pinned?: boolean; is_active?: boolean; starts_at?: string; ends_at?: string; created_at?: string
    thumbnail_theme?: string; thumbnail_url?: string
    display_date?: string; home_visible?: boolean; related_tickers?: string[]; related_topics?: string[]
}
type Props = { apiBase?: string; updatesPath?: string; homePath?: string; style?: React.CSSProperties }
type Category = "전체" | "업데이트" | "안내" | "이벤트"
const CATEGORIES: Category[] = ["전체", "업데이트", "안내", "이벤트"]

function safeLink(value: unknown): string {
    if (typeof value !== "string") return ""
    const link = value.trim()
    if (!link || link.length > 500 || /[\u0000-\u001f\\]/.test(link)) return ""
    if (link.startsWith("/") && !link.startsWith("//")) return link
    try { const u = new URL(link); return u.protocol === "https:" && !u.username && !u.password ? u.href : "" } catch { return "" }
}
function localPath(value: string | undefined, fallback: string): string {
    const link = safeLink(value)
    return link.startsWith("/") ? link.split(/[?#]/)[0] || fallback : fallback
}
function articleHref(path: string, id: string): string {
    return localPath(path, "/updates") + "?notice=" + encodeURIComponent(id)
}
function visibleNotices(rows: unknown, now: number): Notice[] {
    if (!Array.isArray(rows)) return []
    const seen = new Set<string>()
    return rows.filter((n): n is Notice => {
        if (!n || typeof n.id !== "string" || !UUID.test(n.id) || typeof n.title !== "string" || !n.title.trim() || seen.has(n.id) || n.is_active === false) return false
        if (n.starts_at && !(Date.parse(n.starts_at) <= now)) return false
        if (n.ends_at && !(Date.parse(n.ends_at) > now)) return false
        seen.add(n.id)
        return true
    }).sort((a, b) => (Date.parse(b.display_date || b.created_at || "") || 0) - (Date.parse(a.display_date || a.created_at || "") || 0))
}
function category(notice: Notice): Exclude<Category, "전체"> {
    if (notice.kind === "event") return "이벤트"
    return ["feature", "report"].includes(resolveNoticeTheme(notice)) ? "업데이트" : "안내"
}
function excerpt(body?: string): string {
    return (body || "").replace(/^\s*(?:#{1,3}|[-*•]|\d+[.)])\s+/gm, "").replace(/\*\*/g, "").replace(/\s+/g, " ").trim().slice(0, 150)
}
function NoticeDate({ value }: { value?: string }) {
    const time = Date.parse(value || "")
    if (!Number.isFinite(time)) return null
    return <time dateTime={new Date(time).toISOString()}>{new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "Asia/Seoul" }).format(time)}</time>
}
function Arrow({ back = false }: { back?: boolean }) {
    return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true" style={back ? { transform: "rotate(180deg)" } : undefined}><path d="M4 12h15m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
}
function Cover({ notice }: { notice: Notice }) {
    return <div className="an-updates-art"><NoticeArtwork notice={notice} /></div>
}
function Card({ notice, href, open }: { notice: Notice; href: string; open: (event: React.MouseEvent<HTMLAnchorElement>, id: string) => void }) {
    return <a className="an-updates-card" href={href} onClick={event => open(event, notice.id)}>
        <Cover notice={notice} />
        <div className="an-updates-meta"><span>{category(notice)}</span><NoticeDate value={notice.display_date || notice.created_at} /></div>
        <h3>{notice.title}</h3>
        <p>{excerpt(notice.body)}</p>
    </a>
}
const CSS = `
.an-updates{--u-bg:#fff;--u-ink:#191f28;--u-sub:#4e5968;--u-muted:#6b7684;--u-line:#e5e8eb;--u-soft:#f5f6f8;--u-accent:#6c5ce7;--u-art:#f2f0fc;background:var(--u-bg);color:var(--u-ink);font-family:${FONT};font-weight:600;line-height:1.6;min-height:100vh;width:100%;container-type:inline-size;box-sizing:border-box}
body[data-framer-theme="dark"] .an-updates{--u-bg:#101419;--u-ink:#e3e7ec;--u-sub:#bdc5d0;--u-muted:#9aa4b1;--u-line:#2b323d;--u-soft:#1b222c;--u-accent:#a99bff}
.an-updates *{box-sizing:border-box}
.an-updates a{color:inherit;text-decoration:none}
.an-updates button{font:inherit;font-weight:700;cursor:pointer;border:0;color:inherit;background:none}
.an-updates :is(a,button):focus-visible{outline:2px solid var(--u-accent);outline-offset:5px}
.an-updates-shell{width:100%;max-width:1120px;margin:auto;padding:0 32px}
.an-updates-header{height:88px;display:flex;align-items:center;justify-content:space-between;gap:20px}
.an-updates-brand{display:inline-flex;align-items:center;gap:11px;font-size:19px;font-weight:800;letter-spacing:-.7px;white-space:nowrap}
.an-updates-brand img{display:block;width:30px;height:auto;flex-shrink:0}
.an-updates-header-links{display:flex;gap:26px;align-items:center;font-size:14px;font-weight:700;color:var(--u-sub)}
.an-updates-header-links a{min-height:44px;display:inline-flex;align-items:center;gap:8px}
.an-updates-header-links a:last-child{background:var(--u-soft);border-radius:12px;padding:0 16px}
.an-updates-main{padding-top:64px;padding-bottom:80px}
.an-updates-intro{margin-bottom:42px}
.an-updates-eyebrow{font-size:13px;font-weight:700;color:var(--u-accent);letter-spacing:.08em;margin:0 0 12px}
.an-updates h1{font-size:clamp(34px,5cqw,52px);font-weight:800;line-height:1.25;letter-spacing:-1.8px;margin:0;text-wrap:balance;word-break:keep-all;overflow-wrap:anywhere}
.an-updates-intro>p:last-child{color:var(--u-muted);font-size:17px;margin:16px 0 0;word-break:keep-all}
.an-updates-hero{display:grid;grid-template-columns:1.15fr 1fr;border-radius:28px;overflow:hidden;background:var(--u-soft);min-height:340px}
.an-updates-art{background:var(--u-art);overflow:hidden;position:relative;aspect-ratio:1.6}
.an-updates-art>svg{width:165%!important;max-width:none;position:absolute;left:-32.5%;top:0}
.an-updates-art>img{position:absolute;inset:0}
.an-updates-hero .an-updates-art{aspect-ratio:auto;min-height:340px}
.an-updates-hero-copy{padding:42px 36px;display:flex;flex-direction:column;justify-content:center;align-items:flex-start}
.an-updates-meta{display:flex;align-items:center;flex-wrap:wrap;gap:14px;color:var(--u-muted);font-size:13px;font-weight:600}
.an-updates-meta>span{color:var(--u-accent);font-weight:700}
.an-updates-hero h2{margin:16px 0 12px;font-size:30px;font-weight:800;line-height:1.42;letter-spacing:-1px;word-break:keep-all;overflow-wrap:anywhere}
.an-updates-hero p{margin:0;color:var(--u-sub);font-size:15px;line-height:1.8;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.an-updates-read{display:inline-flex;align-items:center;gap:9px;margin-top:26px;font-size:14px;font-weight:700}
.an-updates-hero:hover .an-updates-read,.an-updates-card:hover h3{color:var(--u-accent)}
.an-updates-list{margin-top:66px}
.an-updates-list-head{display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap;margin-bottom:28px}
.an-updates-list h2{font-size:25px;font-weight:800;margin:0;letter-spacing:-.7px}
.an-updates-filters{display:flex;gap:6px;flex-wrap:wrap}
.an-updates-filters button{padding:9px 14px;min-height:42px;border-radius:12px;font-size:14px;color:var(--u-muted)}
.an-updates-filters button[aria-pressed="true"]{background:var(--u-ink);color:var(--u-bg)}
.an-updates-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:40px 26px}
.an-updates-card{min-width:0;display:block}
.an-updates-card .an-updates-art{border-radius:20px;margin-bottom:20px}
.an-updates-card .an-updates-meta{font-size:12px;gap:10px}
.an-updates-card h3{font-size:21px;font-weight:800;line-height:1.45;letter-spacing:-.5px;margin:10px 0;overflow-wrap:anywhere;word-break:keep-all}
.an-updates-card p{font-size:14px;color:var(--u-muted);margin:0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;line-height:1.7}
.an-updates-back{display:inline-flex;align-items:center;gap:8px;min-height:44px;font-size:14px;font-weight:700;color:var(--u-muted)!important}
.an-updates-article{max-width:760px;margin:0 auto}
.an-updates-article-head{margin:34px 0}
.an-updates-article h1{font-size:clamp(30px,4cqw,44px);line-height:1.4;letter-spacing:-1.3px;margin:18px 0 22px}
.an-updates-article .an-updates-art{border-radius:24px;aspect-ratio:1.9;margin:36px 0 42px}
.an-updates-byline{display:flex;align-items:center;justify-content:space-between;gap:16px;color:var(--u-muted);font-size:13px}
.an-updates-share{display:inline-flex;align-items:center;gap:7px;min-height:40px;padding:0 12px!important;background:var(--u-soft)!important;border-radius:10px;font-size:13px!important}
.an-updates-copy-fallback{margin-top:12px;font-size:13px;color:var(--u-muted)}
.an-updates-copy-fallback input{width:100%;padding:12px;font:inherit;border:1px solid var(--u-line);border-radius:8px;margin-top:6px;color:var(--u-ink);background:var(--u-bg)}
.an-updates-body{color:var(--u-sub);font-size:17px;line-height:1.95;overflow-wrap:anywhere;word-break:keep-all}
.an-updates-body p{white-space:pre-wrap;margin:0 0 24px}
.an-updates-body h3{font-size:23px;font-weight:800;line-height:1.5;color:var(--u-ink);letter-spacing:-.5px;margin:40px 0 16px}
.an-updates-body strong{font-weight:800;color:var(--u-ink)}
.an-updates-body ul,.an-updates-body ol{margin:20px 0 28px;padding-left:24px}
.an-updates-body li{padding-left:4px;margin:9px 0;white-space:pre-wrap}
.an-updates-body li::marker{color:var(--u-accent)}
.an-updates-article-foot{margin-top:48px;padding-top:28px;border-top:1px solid var(--u-line);display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}
.an-updates-related{display:inline-flex;align-items:center;justify-content:center;gap:10px;background:var(--u-ink);color:var(--u-bg)!important;border-radius:14px;padding:14px 20px;font-size:14px;font-weight:700}
.an-updates-state{padding:60px 20px;text-align:center;background:var(--u-soft);border-radius:20px;color:var(--u-muted)}
.an-updates-state h2{font-size:22px;font-weight:800;color:var(--u-ink);margin:0 0 12px}
.an-updates-state p{font-size:15px;margin:0 0 20px}
.an-updates-state button{background:var(--u-bg);padding:10px 18px;border-radius:10px;min-height:44px}
.an-updates-sk{background:var(--u-soft);border-radius:16px;height:22px;margin-top:18px}
.an-updates-skeleton{min-height:430px}
.an-updates-skeleton .an-updates-sk:first-child{height:340px;border-radius:28px;margin:0}
.an-updates-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.an-updates-footer{padding:30px 0 38px;border-top:1px solid var(--u-line);display:flex;justify-content:space-between;gap:20px;font-size:13px;color:var(--u-muted)}
.an-updates-footer a{font-weight:700}
.an-updates-preview{color:var(--u-muted);font-size:12px;margin-bottom:20px}
@container(max-width:800px){.an-updates-main{padding-top:38px}.an-updates-hero{grid-template-columns:1fr 1fr;min-height:300px}.an-updates-hero .an-updates-art{min-height:300px}.an-updates-hero-copy{padding:28px}.an-updates-hero h2{font-size:25px}.an-updates-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.an-updates-header{height:76px}}
@container(max-width:580px){.an-updates-shell{padding-left:22px;padding-right:22px}.an-updates-header{height:72px;gap:12px}.an-updates-brand{font-size:17px;gap:8px}.an-updates-brand img{width:26px}.an-updates-header-links{gap:0;font-size:12px}.an-updates-header-links>a:first-child{display:none}.an-updates-header-links a:last-child{padding:0 10px;min-height:38px}.an-updates-main{padding-top:36px;padding-bottom:58px}.an-updates-intro{margin-bottom:28px}.an-updates-intro>p:last-child{font-size:15px;line-height:1.8}.an-updates-hero{display:block;border-radius:22px}.an-updates-hero .an-updates-art{min-height:0;aspect-ratio:1.5}.an-updates-hero-copy{padding:25px 24px 28px}.an-updates-hero h2{font-size:25px}.an-updates-hero p{font-size:14px;-webkit-line-clamp:2}.an-updates-read{margin-top:18px}.an-updates-list{margin-top:44px}.an-updates-list-head{gap:16px;margin-bottom:24px}.an-updates-list h2{font-size:23px;width:100%}.an-updates-filters button{font-size:13px;padding:8px 13px}.an-updates-grid{grid-template-columns:1fr;gap:36px}.an-updates-card .an-updates-art{aspect-ratio:1.7;margin-bottom:16px}.an-updates-card h3{font-size:22px}.an-updates-article-head{margin-top:24px}.an-updates-article .an-updates-art{border-radius:18px;aspect-ratio:1.5;margin:28px 0 30px}.an-updates-body{font-size:16px;line-height:1.9}.an-updates-body h3{font-size:21px;margin-top:32px}.an-updates-footer{font-size:12px}.an-updates-state{padding:42px 18px}}
`

/** @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 * @framerIntrinsicWidth 1200
 * @framerIntrinsicHeight 1000
 */
export default function PublicUpdates({ apiBase = API, updatesPath = "/updates", homePath = "/", style }: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const path = localPath(updatesPath, "/updates")
    const home = localPath(homePath, "/")
    const base = apiBase.replace(/\/+$/, "")
    const [route, setRoute] = React.useState<string | null>(null)
    const [items, setItems] = React.useState<Notice[]>([])
    const [status, setStatus] = React.useState<"loading" | "ready" | "error">("loading")
    const [filter, setFilter] = React.useState<Category>("전체")
    const [retry, setRetry] = React.useState(0)
    const [share, setShare] = React.useState("")
    const [copyFallback, setCopyFallback] = React.useState("")
    const [now, setNow] = React.useState(0)
    const content = React.useRef<HTMLElement>(null)
    const focusNext = React.useRef(false)

    React.useEffect(() => {
        if (onCanvas) { setRoute(""); setStatus("ready"); return }
        const sync = () => { setRoute(new URLSearchParams(window.location.search).get("notice") || ""); setStatus("loading"); setShare(""); setCopyFallback("") }
        sync()
        window.addEventListener("popstate", sync)
        return () => window.removeEventListener("popstate", sync)
    }, [onCanvas])

    React.useEffect(() => {
        if (onCanvas || route === null) return
        if (route && !UUID.test(route)) { setItems([]); setStatus("ready"); return }
        const controller = new AbortController()
        let alive = true
        const timer = window.setTimeout(() => controller.abort(), 10_000)
        setStatus("loading")
        setItems([])
        void (async () => {
            try {
                const response = await fetch(base + "/api/notices" + (route ? "?id=" + encodeURIComponent(route) : ""), { signal: controller.signal, credentials: "omit" })
                if (!response.ok) throw new Error("request_failed")
                const data = await response.json()
                if (data.error || data.migration_required || !Array.isArray(data.items)) throw new Error("unavailable")
                if (alive) { setItems(data.items); setNow(Date.now()); setStatus("ready") }
            } catch { if (alive) setStatus("error") }
            finally { window.clearTimeout(timer) }
        })()
        return () => { alive = false; window.clearTimeout(timer); controller.abort() }
    }, [base, route, retry, onCanvas])

    // Re-check visibility on expiry and when returning to this browser tab.
    React.useEffect(() => {
        if (onCanvas || status !== "ready") return
        const boundaries = items.flatMap(n => [n.starts_at, n.ends_at]).map(t => Date.parse(t || "")).filter(t => t > Date.now())
        const timer = boundaries.length ? window.setTimeout(() => setNow(Date.now()), Math.min(2_147_000_000, Math.max(1, Math.min(...boundaries) - Date.now() + 1))) : undefined
        const refresh = () => { if (document.visibilityState === "visible") setRetry(n => n + 1) }
        document.addEventListener("visibilitychange", refresh)
        return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", refresh) }
    }, [items, now, status, onCanvas])

    React.useEffect(() => {
        if (status !== "loading" && focusNext.current) {
            focusNext.current = false
            content.current?.focus({ preventScroll: true })
        }
    }, [status])

    const notices = visibleNotices(items, now)
    const selected = route ? notices.find(n => n.id.toLowerCase() === route.toLowerCase()) : undefined
    const featured = notices.find(n => n.pinned) || notices[0]
    const remaining = notices.filter(n => n.id !== featured?.id)
    const shown = (filter === "전체" ? remaining : notices.filter(n => category(n) === filter))
    const related = safeLink(selected?.link)

    React.useEffect(() => {
        if (onCanvas) return
        const previous = document.title
        document.title = selected ? selected.title + " | 알파네스트 소식" : "알파네스트 소식"
        return () => { document.title = previous }
    }, [selected?.title, onCanvas])

    function navigate(event: React.MouseEvent<HTMLAnchorElement>, id: string) {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || onCanvas) return
        event.preventDefault()
        window.history.pushState(null, "", id ? articleHref(path, id) : path)
        focusNext.current = true
        if (route === id) setRetry(n => n + 1)
        setRoute(id); setStatus("loading"); setShare(""); setCopyFallback(""); setFilter("전체")
        window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior })
    }
    async function copyLink() {
        if (!selected) return
        const url = new URL(articleHref(path, selected.id), window.location.origin).href
        try { await navigator.clipboard.writeText(url); setShare("링크를 복사했어요"); setCopyFallback("") }
        catch { setCopyFallback(url); setShare("아래 주소를 복사해 주세요") }
    }
    return <div className="an-updates" style={{ ...style, width: "100%" }}>
        <style>{CSS}</style>
        <div className="an-updates-shell">
            <header className="an-updates-header">
                <a href={home} className="an-updates-brand" aria-label="알파네스트 홈">
                    <img src={LOGO} width={30} height={32} alt="" />
                    알파네스트
                </a>
                <nav className="an-updates-header-links" aria-label="소식 페이지 메뉴"><a href={path} onClick={event => navigate(event, "")}>소식</a><a href={home}>서비스 둘러보기 <Arrow /></a></nav>
            </header>
            <main ref={content} tabIndex={-1} className="an-updates-main" style={{ outline: "none" }}>
                {onCanvas && <p className="an-updates-preview">소식 페이지 · 실제 미리보기에서는 공개된 공지와 이벤트를 불러옵니다.</p>}
                {!route && <div className="an-updates-intro"><p className="an-updates-eyebrow">ALPHANEST NEWSROOM</p><h1>알파네스트 소식</h1><p>더 나은 투자 공부를 위해, 조금씩 달라지고 있어요.</p></div>}
                {status === "loading" ? <div className="an-updates-skeleton" role="status" aria-label="소식을 불러오는 중"><span className="an-updates-sr">소식을 불러오는 중</span><div className="an-updates-sk" /><div className="an-updates-sk" style={{ width: "60%" }} /><div className="an-updates-sk" style={{ width: "35%" }} /></div>
                    : status === "error" ? <div className="an-updates-state" role="alert"><h2>소식을 불러오지 못했어요</h2><p>잠시 후 다시 확인해 주세요.</p><button onClick={() => setRetry(n => n + 1)}>다시 불러오기</button></div>
                    : route ? selected ? <article className="an-updates-article">
                        <a className="an-updates-back" href={path} onClick={event => navigate(event, "")}><Arrow back />소식 목록</a>
                        <header className="an-updates-article-head"><div className="an-updates-meta"><span>{category(selected)}</span><NoticeDate value={selected.display_date || selected.created_at} /></div><h1>{selected.title}</h1><div className="an-updates-byline"><span>알파네스트 팀</span><button className="an-updates-share" onClick={copyLink}><svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m10 13 4-4m-5 7-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 0 2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>링크 복사</button></div><span className="an-updates-sr" role="status">{share}</span>{copyFallback && <label className="an-updates-copy-fallback">아래 주소를 복사해 주세요<input value={copyFallback} readOnly onFocus={event => event.target.select()} /></label>}</header>
                        <Cover notice={selected} />
                        <div className="an-updates-body"><NoticeBody text={selected.body} /></div>
                        <footer className="an-updates-article-foot"><a className="an-updates-back" href={path} onClick={event => navigate(event, "")}><Arrow back />소식 목록</a>{related && <a className="an-updates-related" href={related} target={related.startsWith("https://") ? "_blank" : undefined} rel="noopener noreferrer">관련 페이지 살펴보기 <Arrow /></a>}</footer>
                    </article> : <div className="an-updates-state"><h2>지금 볼 수 없는 소식이에요</h2><p>공개가 종료되었거나 주소가 변경되었을 수 있어요.</p><a className="an-updates-back" href={path} onClick={event => navigate(event, "")}><Arrow back />소식 목록으로</a></div>
                    : notices.length ? <>
                        <a className="an-updates-hero" href={articleHref(path, featured.id)} onClick={event => navigate(event, featured.id)}>
                            <Cover notice={featured} /><div className="an-updates-hero-copy"><div className="an-updates-meta"><span>{featured.pinned ? "주요 소식" : "최근 소식"}</span><NoticeDate value={featured.display_date || featured.created_at} /></div><h2>{featured.title}</h2><p>{excerpt(featured.body)}</p><span className="an-updates-read">이야기 읽기 <Arrow /></span></div>
                        </a>
                        {notices.length > 1 && <section className="an-updates-list" aria-label="최근 소식"><div className="an-updates-list-head"><h2>더 많은 소식</h2><div className="an-updates-filters" aria-label="소식 분류">{CATEGORIES.map(name => <button key={name} aria-pressed={filter === name} onClick={() => setFilter(name)}>{name}</button>)}</div></div>{shown.length ? <div className="an-updates-grid">{shown.map(notice => <Card key={notice.id} notice={notice} href={articleHref(path, notice.id)} open={navigate} />)}</div> : <div className="an-updates-state">아직 이 분류의 소식이 없어요.</div>}</section>}
                    </> : <div className="an-updates-state"><h2>새로운 소식을 준비하고 있어요</h2><p>알파네스트의 업데이트와 이야기를 이곳에서 전할게요.</p><a className="an-updates-back" href={home}>알파네스트 둘러보기 <Arrow /></a></div>}
            </main>
            <footer className="an-updates-footer"><span>© AlphaNest</span><a href={home}>알파네스트로 돌아가기</a></footer>
        </div>
    </div>
}

addPropertyControls(PublicUpdates, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: API },
    updatesPath: { type: ControlType.String, title: "소식 경로", defaultValue: "/updates" },
    homePath: { type: ControlType.String, title: "홈 경로", defaultValue: "/" },
})

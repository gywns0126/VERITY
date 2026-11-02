import * as React from "react"
import { addPropertyControls, useIsStaticRenderer } from "framer"
import { SiteMap, readSiteMapSession, portfolioMapEntryPath } from "alphanest-site-map"
import CompanyStructureView, { useCompanyStructureBridge } from "./company-structure-view"

const CANVAS_URL = "https://project-yw131.vercel.app/member-map-canvas"
const CSS = `.an-site-map{font:600 13px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;color:#191f28;width:100%;min-width:0}.an-site-map-nav{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:8px 12px;background:#fff}.an-site-map-nav a,.an-site-map-nav button{font-family:inherit;font-weight:700;font-size:13px;line-height:1.5;text-decoration:none;color:inherit;min-height:44px;padding:10px 12px;border:0;border-radius:10px;background:#f8f9fb;cursor:pointer;box-sizing:border-box}.an-site-map-nav button{margin-left:auto}.an-site-map-nav a:focus-visible,.an-site-map-nav button:focus-visible{outline:0;background:#e9edf2}.an-site-map-status{padding:16px 20px}.an-site-map-status a{color:#6c5ce7;font-weight:700}body[data-framer-theme=dark] .an-site-map{color:#e3e7ec}body[data-framer-theme=dark] .an-site-map-nav{background:#171c23}body[data-framer-theme=dark] .an-site-map-nav a,body[data-framer-theme=dark] .an-site-map-nav button{background:#1d242c}body[data-framer-theme=dark] .an-site-map-nav a:focus-visible,body[data-framer-theme=dark] .an-site-map-nav button:focus-visible{background:#303945}@media(hover:hover){.an-site-map-nav a:hover,.an-site-map-nav button:not(:disabled):hover{background:#f1f3f5}body[data-framer-theme=dark] .an-site-map-nav a:hover,body[data-framer-theme=dark] .an-site-map-nav button:not(:disabled):hover{background:#252c35}}`

async function loadSiteCanvas(fetcher: typeof fetch = fetch, signal?: AbortSignal) {
    const response = await fetcher(CANVAS_URL, { credentials: "omit", redirect: "error", referrerPolicy: "no-referrer", signal })
    if (!response.ok || !response.headers.get("content-type")?.toLowerCase().startsWith("text/html") || !response.body) throw Error("canvas-response")
    const reader = response.body.getReader(), parts: Uint8Array[] = []
    let size = 0
    try {
        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            size += value.byteLength
            if (size > 2 * 1024 * 1024) throw Error("canvas-size")
            parts.push(value)
        }
    } finally { await reader.cancel().catch(() => {}) }
    const bytes = new Uint8Array(size)
    let offset = 0
    for (const part of parts) { bytes.set(part, offset); offset += part.length }
    const html = new TextDecoder("utf-8", { fatal: true }).decode(bytes)
    if (!html.startsWith("<!doctype html>") || !html.includes("__ALPHANEST_FRAME_NONCE__") || !html.includes("connect-src blob: data:")) throw Error("canvas-shape")
    return html
}

/** @preserve Same-origin mindmap entry: preserve existing sessions, data, notes, positions and drafts.
 * @framerIntrinsicWidth 1200
 * @framerIntrinsicHeight 900
 * @framerSupportedLayoutWidth any-prefer-fixed
 * @framerSupportedLayoutHeight auto
 */
export default function PublicMindmap({ style }: { style?: React.CSSProperties }) {
    const isStatic = useIsStaticRenderer()
    const [owner, setOwner] = React.useState<string | null>(null)
    const [template, setTemplate] = React.useState("")
    const [failed, setFailed] = React.useState(false)
    const [attempt, setAttempt] = React.useState(0)
    const structure = useCompanyStructureBridge(owner)
    const back = typeof window === "undefined" ? "/mindmap" : portfolioMapEntryPath(window.location.search).replace("/member-map-review", "/mindmap")
    React.useEffect(() => {
        if (isStatic) return
        const sync = () => React.startTransition(() => setOwner(readSiteMapSession()?.userId || null))
        sync()
        window.addEventListener("verity_auth_change", sync)
        window.addEventListener("storage", sync)
        return () => { window.removeEventListener("verity_auth_change", sync); window.removeEventListener("storage", sync) }
    }, [isStatic])
    React.useEffect(() => {
        if (isStatic) return
        const controller = new AbortController()
        React.startTransition(() => setFailed(false))
        void loadSiteCanvas(fetch, controller.signal).then(value => { if (!controller.signal.aborted) React.startTransition(() => setTemplate(value)) }, () => { if (!controller.signal.aborted) React.startTransition(() => setFailed(true)) })
        return () => controller.abort()
    }, [isStatic, attempt])
    return <section className="an-site-map" style={{ ...style, position: "relative" }} aria-label="마인드맵 베타">
        <style>{CSS}</style>
        <nav className="an-site-map-nav" aria-label="마인드맵 보기">
            <a href="/nest">둥지로</a>
            <strong>마인드맵 베타</strong>
            {owner && <button type="button" aria-pressed={!!structure.snapshot} disabled={structure.waiting || !template} onClick={structure.open}>{structure.waiting ? "지도 확인 중…" : "기업 구조"}</button>}
        </nav>
        {isStatic ? <p className="an-site-map-status">사이트의 기존 로그인으로 내 종목과 지도 기록을 불러옵니다.</p> : <>
            {!owner && <p className="an-site-map-status" role="status">로그인 상태를 확인해 주세요. <a href={"/login?next=" + encodeURIComponent(back)}>알파네스트 로그인</a></p>}
            {!template && <p className="an-site-map-status" role="status">{failed ? <>작업판을 불러오지 못했어요. <button type="button" onClick={() => React.startTransition(() => setAttempt(value => value + 1))}>다시 불러오기</button></> : "작업판을 준비하고 있어요."}</p>}
            {template && <SiteMap template={template} />}
            {owner && structure.snapshot && <CompanyStructureView snapshot={structure.snapshot} onClose={structure.close} />}
        </>}
    </section>
}

addPropertyControls(PublicMindmap, {})

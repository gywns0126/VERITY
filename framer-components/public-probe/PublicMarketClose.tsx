import * as React from "react"
import { addPropertyControls, ControlType, useIsStaticRenderer } from "framer"

const BLOB_ORIGIN = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const MEDIA_PATH = "/market-close/v1/"
const INDEX_URL = `${BLOB_ORIGIN}${MEDIA_PATH}index.json`
const DAY = /^\d{4}-\d{2}-\d{2}$/
const PUBLISHED_AT = /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?$/

type Market = "KR" | "US"
type Clip = {
    market: Market
    title: string
    publishedTime: number
    date: string
    dateLabel: string
    permalink: string
    posterUrl: string
    videoUrl: string
}

function httpsUrl(value: unknown) {
    if (typeof value !== "string" || !/^https:\/\//i.test(value) || /[\s\\\u0000-\u001f\u007f]/.test(value)) return
    try {
        const url = new URL(value)
        if (url.protocol === "https:" && !url.username && !url.password && !url.port) return url
    } catch {
        // Malformed URLs are treated as missing fields.
    }
}

function assetUrl(value: unknown) {
    const url = httpsUrl(value)
    if (
        url?.origin === BLOB_ORIGIN && url.pathname.startsWith(MEDIA_PATH) &&
        !url.pathname.endsWith("/") && !/%(?:2f|5c|25)/i.test(url.pathname) && !url.search && !url.hash
    ) return url.href
}

function instagramUrl(value: unknown) {
    const url = httpsUrl(value)
    if (
        url && (url.hostname === "www.instagram.com" || url.hostname === "instagram.com") &&
        /^\/(?:[\w.]+\/)?(?:p|reel|tv)\/[\w-]+\/?$/.test(url.pathname)
    ) return `${url.origin}${url.pathname}`
}

function validDay(value: unknown): value is string {
    if (typeof value !== "string" || !DAY.test(value)) return false
    const time = Date.parse(value)
    return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value
}

function readClips(value: unknown): Clip[] {
    const manifest = value as { version?: unknown; items?: unknown } | null
    if (manifest?.version !== 1 || !Array.isArray(manifest.items)) return []

    const latest: Partial<Record<Market, Clip>> = {}
    for (const item of manifest.items) {
        if (!item || typeof item !== "object") continue
        const record = item as Record<string, unknown>
        const { id, market, title, publishedAt, sessionDate } = record
        if (
            typeof id !== "string" || !id.trim() || (market !== "KR" && market !== "US") ||
            typeof title !== "string" || !title.trim() || typeof publishedAt !== "string" ||
            !PUBLISHED_AT.test(publishedAt) || !validDay(publishedAt.slice(0, 10))
        ) continue

        const publishedTime = Date.parse(publishedAt)
        const previous = latest[market]
        if (!Number.isFinite(publishedTime) || (previous && previous.publishedTime >= publishedTime)) continue

        const permalink = instagramUrl(record.permalink)
        const posterUrl = assetUrl(record.posterUrl)
        const videoUrl = assetUrl(record.videoUrl)
        if (!permalink || !posterUrl || !videoUrl) continue

        const hasSession = validDay(sessionDate)
        latest[market] = {
            market, title: title.trim(), publishedTime,
            date: hasSession ? sessionDate : publishedAt.slice(0, 10),
            dateLabel: hasSession ? "마감일" : "게시일",
            permalink, posterUrl, videoUrl,
        }
    }
    return Object.values(latest).sort((a, b) => b.publishedTime - a.publishedTime)
}

const styles = `
.an-market-close {
    --mc-card:#ffffff; --mc-stack:#f8f9fb; --mc-hover:#f1f3f5; --mc-focus:#e9edf2;
    --mc-ink:#191f28; --mc-sub:#6b7684; --mc-accent:#6c5ce7;
    width:100%; min-width:0; box-sizing:border-box; padding:20px; border-radius:20px;
    background:var(--mc-card); color:var(--mc-ink);
    font-family:Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;
}
html[data-an-theme="dark"] .an-market-close,
html:not([data-an-theme]) body[data-framer-theme="dark"] .an-market-close {
    --mc-card:#171c23; --mc-stack:#1d242c; --mc-hover:#252c35; --mc-focus:#303945;
    --mc-ink:#e3e7ec; --mc-sub:#9aa4b1; --mc-accent:#a99bff;
}
.an-market-close h2 { grid-row:1; grid-column:1/-1; margin:0; font-size:20px; line-height:1.4; font-weight:800 }
.an-market-close .mc-content {
    display:grid; grid-template-columns:min(30%,120px) minmax(0,1fr);
    gap:12px;
}
.an-market-close .mc-copy { display:contents }
.an-market-close .mc-frame { grid-row:2; grid-column:1; position:relative; aspect-ratio:9/16; align-self:start; overflow:hidden; border-radius:12px; background:var(--mc-stack) }
.an-market-close .mc-frame :is(img,video) { position:absolute; inset:0; display:block; width:100%; height:100%; object-fit:contain }
.an-market-close .mc-frame img { background:var(--mc-stack) }
.an-market-close .mc-frame[data-video-frame="true"] img { visibility:hidden }
.an-market-close .mc-details { grid-row:2; grid-column:2; display:flex; flex-direction:column; align-items:flex-start; justify-content:center; min-width:0 }
.an-market-close .mc-meta { display:flex; flex-wrap:wrap; gap:2px 8px; color:var(--mc-sub); font-size:12px; line-height:1.5; font-weight:600 }
.an-market-close .mc-meta span { color:var(--mc-accent); font-weight:700 }
.an-market-close h3 {
    display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; overflow:hidden;
    block-size:3em; margin:4px 0 2px; font-size:15px; line-height:1.5; font-weight:800;
    word-break:keep-all; overflow-wrap:anywhere;
}
.an-market-close .mc-controls { display:flex; flex-wrap:wrap; gap:4px; margin-top:4px }
.an-market-close :is(button,a) {
    display:inline-flex; align-items:center; justify-content:center; box-sizing:border-box;
    min-height:44px; min-width:44px; padding:6px 8px; border:0; border-radius:10px;
    font:inherit; font-size:12px; font-weight:700; line-height:1.4; white-space:nowrap;
    color:var(--mc-ink); background:var(--mc-stack); text-decoration:none;
    cursor:pointer; transition:background-color 160ms;
}
.an-market-close .mc-play { min-width:68px }
.an-market-close a { color:var(--mc-accent); background:transparent }
.an-market-close button:disabled { opacity:.55; cursor:default }
.an-market-close :is(button,a):focus-visible { outline:none; background:var(--mc-focus) }
@media (hover:hover) {
    .an-market-close :is(button,a):not(:disabled):not(:focus-visible):hover { background:var(--mc-hover) }
}
@media (prefers-reduced-motion:reduce) {
    .an-market-close :is(button,a) { transition:none }
}
.an-market-close p { margin:0; color:var(--mc-sub); font-size:13px; line-height:1.6; font-weight:600 }
@media (min-width:768px) {
    .an-market-close .mc-content {
        max-width:520px; margin-inline:auto; align-items:center;
        grid-template-columns:144px minmax(0,1fr); gap:24px;
    }
    .an-market-close .mc-frame { grid-row:1 }
    .an-market-close .mc-copy { display:block; grid-row:1; grid-column:2; min-width:0 }
    .an-market-close h2 { margin-bottom:12px }
    .an-market-close h3 { font-size:16px }
    .an-market-close .mc-controls { gap:8px }
}
`

/**
 * @framerIntrinsicWidth 390
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 */
export default function PublicMarketClose({ showSource = true, style }: { showSource?: boolean; style?: React.CSSProperties }) {
    const isStatic = useIsStaticRenderer()
    const [clips, setClips] = React.useState<Clip[] | null>(null)
    const [index, setIndex] = React.useState(0)
    const [isPlaying, setIsPlaying] = React.useState(false)
    const [frameClip, setFrameClip] = React.useState<Clip>()
    const frameRef = React.useRef<HTMLDivElement>(null)
    const videoRef = React.useRef<HTMLVideoElement>(null)
    const activeClip = React.useRef<Clip | undefined>(undefined)
    const loadedClip = React.useRef<Clip | undefined>(undefined)
    const blockedClip = React.useRef<Clip | undefined>(undefined)
    const intent = React.useRef<"auto" | "play" | "pause">("auto")
    const inView = React.useRef(false)
    const autoAllowed = React.useRef(false)
    const attempt = React.useRef(0)

    const clipCount = isStatic ? 0 : (clips?.length ?? 0)
    const hasClip = clipCount > 0
    const clip = hasClip ? clips?.[index] : undefined

    React.useEffect(() => {
        if (isStatic) return
        const controller = new AbortController()
        let disposed = false
        let frame = 0
        let timeout = 0
        let cancelIdle: (() => void) | undefined

        async function loadManifest() {
            timeout = window.setTimeout(() => controller.abort(), 8000)
            try {
                const response = await fetch(INDEX_URL, {
                    credentials: "omit", redirect: "error", cache: "no-cache", signal: controller.signal,
                })
                if (!response.ok) throw new Error("Manifest unavailable")
                const items = readClips(await response.json())
                if (!disposed) setClips(items)
            } catch {
                if (!disposed) setClips([])
            } finally {
                window.clearTimeout(timeout)
            }
        }

        function afterLoad() {
            frame = window.requestAnimationFrame(() => {
                if (typeof window.requestIdleCallback === "function") {
                    const idle = window.requestIdleCallback(() => void loadManifest(), { timeout: 1200 })
                    cancelIdle = () => window.cancelIdleCallback(idle)
                } else {
                    const timer = window.setTimeout(() => void loadManifest(), 0)
                    cancelIdle = () => window.clearTimeout(timer)
                }
            })
        }

        if (document.readyState === "complete") afterLoad()
        else window.addEventListener("load", afterLoad, { once: true })
        return () => {
            disposed = true
            window.removeEventListener("load", afterLoad)
            window.cancelAnimationFrame(frame)
            cancelIdle?.()
            window.clearTimeout(timeout)
            controller.abort()
        }
    }, [isStatic])

    const clearVideo = React.useCallback((video: HTMLVideoElement) => {
        attempt.current += 1
        loadedClip.current = undefined
        video.pause()
        video.removeAttribute("src")
        video.load()
        setIsPlaying(false)
        setFrameClip(undefined)
    }, [])

    const syncPlayback = React.useCallback(() => {
        const video = videoRef.current
        const current = activeClip.current
        if (!video || !current) return

        const eligible = inView.current && document.visibilityState === "visible" &&
            (intent.current === "play" || (intent.current === "auto" && autoAllowed.current))

        if (!eligible || blockedClip.current === current) {
            if (loadedClip.current && loadedClip.current !== current) clearVideo(video)
            else {
                attempt.current += 1
                video.pause()
                setIsPlaying(false)
            }
            return
        }

        // Attach only the selected clip, inside the same tap handler on mobile.
        if (loadedClip.current !== current) {
            if (loadedClip.current) video.pause()
            loadedClip.current = current
            setFrameClip(undefined)
            video.src = current.videoUrl
        } else if (!video.paused) return

        const request = ++attempt.current
        video.muted = true
        setIsPlaying(true)
        void video.play().then(() => {
            if (attempt.current === request) setFrameClip(current)
        }, () => {
            if (attempt.current !== request) return
            blockedClip.current = current
            clearVideo(video)
        })
    }, [clearVideo])

    React.useEffect(() => {
        activeClip.current = clip
        syncPlayback()
    }, [clip, syncPlayback])

    React.useEffect(() => {
        const frame = frameRef.current
        const video = videoRef.current
        if (!hasClip || !frame || !video) return

        const desktop = window.matchMedia("(min-width: 768px)")
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)")
        const queries = [desktop, reducedMotion]
        function syncPreference() {
            autoAllowed.current = desktop.matches && !reducedMotion.matches
            syncPlayback()
        }

        function measureFrame() {
            if (!frame) return
            const bounds = frame.getBoundingClientRect()
            inView.current = bounds.width > 0 && bounds.height > 0 && bounds.bottom > 0 &&
                bounds.right > 0 && bounds.top < window.innerHeight && bounds.left < window.innerWidth
            syncPlayback()
        }

        const observer = typeof IntersectionObserver === "function"
            ? new IntersectionObserver(([entry]) => {
                inView.current = !!entry?.isIntersecting && entry.intersectionRatio >= 0.01
                syncPlayback()
            }, { threshold: 0.01 })
            : null

        syncPreference()
        if (observer) observer.observe(frame)
        else {
            measureFrame()
            window.addEventListener("scroll", measureFrame, { capture: true, passive: true })
            window.addEventListener("resize", measureFrame)
        }
        for (const query of queries) {
            if (query.addEventListener) query.addEventListener("change", syncPreference)
            else query.addListener(syncPreference)
        }
        document.addEventListener("visibilitychange", syncPlayback)

        return () => {
            inView.current = false
            attempt.current += 1
            video.pause()
            observer?.disconnect()
            if (!observer) {
                window.removeEventListener("scroll", measureFrame, true)
                window.removeEventListener("resize", measureFrame)
            }
            for (const query of queries) {
                if (query.removeEventListener) query.removeEventListener("change", syncPreference)
                else query.removeListener(syncPreference)
            }
            document.removeEventListener("visibilitychange", syncPlayback)
        }
    }, [hasClip, syncPlayback])

    function step(direction: number) {
        if (clipCount > 1) setIndex(current => (current + direction + clipCount) % clipCount)
    }

    function togglePlayback() {
        intent.current = isPlaying ? "pause" : "play"
        if (!isPlaying) blockedClip.current = undefined
        syncPlayback()
    }

    return (
        <section className="an-market-close" aria-label="장 마감 브리핑" style={style}>
            <style>{styles}</style>
            <div className="mc-content">
                <div className="mc-frame" ref={frameRef} aria-hidden="true" data-video-frame={!!clip && frameClip === clip}>
                    {clip ? <>
                        <video
                            ref={videoRef}
                            preload="none"
                            muted
                            playsInline
                            loop={clipCount === 1}
                            onPause={event => { if (event.currentTarget.paused) setIsPlaying(false) }}
                            onEnded={event => { if (loadedClip.current === clip && event.currentTarget.ended) step(1) }}
                            onError={event => {
                                if (loadedClip.current !== clip || !event.currentTarget.error) return
                                blockedClip.current = clip
                                clearVideo(event.currentTarget)
                            }}
                        />
                        <img key={clip.posterUrl} src={clip.posterUrl} alt="" loading="lazy" decoding="async" />
                    </> : null}
                </div>
                <div className="mc-copy">
                    <h2>장 마감 브리핑</h2>
                    <div className="mc-details">
                        {clip ? <>
                            <div aria-live="polite" aria-atomic="true">
                                <div className="mc-meta">
                                    <span>{clip.market === "KR" ? "한국" : "미국"}</span>
                                    <time dateTime={clip.date}>{clip.dateLabel} {clip.date}</time>
                                </div>
                                <h3 title={clip.title}>{clip.title}</h3>
                            </div>
                            {showSource ? <a href={clip.permalink} target="_blank" rel="noopener noreferrer">Instagram 원문</a> : null}
                            <div className="mc-controls" role="group" aria-label="영상 재생 제어">
                                <button type="button" onClick={() => step(-1)} disabled={clipCount < 2} aria-label="이전 영상">이전</button>
                                <button type="button" className="mc-play" onClick={togglePlayback}>{isPlaying ? "일시정지" : "재생"}</button>
                                <button type="button" onClick={() => step(1)} disabled={clipCount < 2} aria-label="다음 영상">다음</button>
                            </div>
                        </> : (
                            <p role="status">{isStatic ? "미리보기에서 장 마감 브리핑을 확인할 수 있어요." : clips ? "지금 볼 수 있는 브리핑이 없어요." : "브리핑을 불러오는 중이에요."}</p>
                        )}
                    </div>
                </div>
            </div>
        </section>
    )
}

addPropertyControls(PublicMarketClose, {
    showSource: { type: ControlType.Boolean, title: "원문 링크", defaultValue: true },
})

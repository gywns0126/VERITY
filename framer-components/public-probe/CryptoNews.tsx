import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * 코인 뉴스 — TIDE 크립토 공개 표면. 팩트 헤드라인만.
 *
 * 🚨 RULE 6 (LLM narrative STOP): 제목 + 출처 + 시각 + 원문 링크만. 요약/해설/sentiment 0.
 * 데이터 = crypto_news.json (Cointelegraph + Google News RSS). 다크모드 자가감지 + shimmer 스켈레톤.
 */

const LIGHT = { bg: "#ffffff", card: "#f9fafb", text: "#191f28", sub: "#6b7280", faint: "#8b95a1", border: "#e5e8eb", accent: "#0ca678" }
const DARK = { bg: "#171c23", card: "#1e242c", text: "#f2f4f6", sub: "#9aa4b1", faint: "#6b7682", border: "#2b3138", accent: "#3ddc97" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function hostname(url: string): string {
    try { return (url || "").replace(/^https?:\/\//, "").split("/")[0].replace(/^www\./, "") } catch (e) { return "" }
}
function dateOnly(t: string): string {
    const m = String(t || "").match(/\d{1,2}\s\w{3}\s\d{4}|\d{4}-\d{2}-\d{2}/)
    return m ? m[0] : ""
}

const DEMO = { items: [
    { title: "Bitcoin weekly close above $63K amid RSI divergence may be bottom signal", link: "#", source: "Cointelegraph", time: "" },
    { title: "Ethereum ETF inflows hit record as staking yield debate heats up", link: "#", source: "Cointelegraph", time: "" },
    { title: "Why Google search can be a crypto wallet risk", link: "#", source: "Cointelegraph", time: "" },
    { title: "Solana network activity climbs to 6-month high on memecoin surge", link: "#", source: "Google News", time: "" },
] }

export default function CryptoNews(props: { dataUrl?: string; dark?: boolean; cardHeight?: number }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const [data, setData] = useState<any>(onCanvas ? DEMO : null)

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.dataUrl || BLOB + "/crypto_news.json", { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive && d) setData(d) })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    const items = useMemo(() => (data && Array.isArray(data.items) ? data.items : []), [data])
    const cardH = props.cardHeight || 92
    const wrap: CSSProperties = { width: "100%", maxWidth: 1180, marginLeft: "auto", marginRight: "auto", boxSizing: "border-box", fontFamily: FONT, color: C.text, background: C.bg, padding: "18px 16px" }
    const grid: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 8, alignItems: "start" }

    if (!data) {
        const skBase = isDark ? "#222a33" : "#e9edf1"
        const skHi = isDark ? "#2d3742" : "#f3f5f7"
        const bar = (w: any, h: number, mt = 0): CSSProperties => ({ width: w, height: h, borderRadius: 5, marginTop: mt, background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite" })
        return (
            <div style={wrap}>
                <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ ...bar(120, 19), marginBottom: 12 }} />
                <div style={grid}>
                    {[0, 1, 2, 3, 4, 5].map((i) => (
                        <div key={i} style={{ height: cardH, background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 12, boxSizing: "border-box" }}>
                            <div style={bar("92%", 14)} /><div style={bar("70%", 14, 6)} /><div style={bar(80, 11, 10)} />
                        </div>
                    ))}
                </div>
            </div>
        )
    }

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 12 }}>
                <span style={{ fontSize: 19, fontWeight: 800, letterSpacing: "-0.02em" }}>코인 뉴스</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>팩트 헤드라인</span>
            </div>
            {items.length === 0 ? (
                <div style={{ padding: 40, textAlign: "center", color: C.faint, fontSize: 14 }}>뉴스가 없어요.</div>
            ) : (
                <div style={grid}>
                    {items.map((it: any, i: number) => {
                        const body = (
                            <div style={{ padding: "11px 12px", borderRadius: 10 }}>
                                <span style={{ fontSize: 14, fontWeight: 600, color: C.text, lineHeight: 1.45, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", overflowWrap: "anywhere" }}>{it.title}</span>
                                <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 7 }}>
                                    <span style={{ fontSize: 11.5, fontWeight: 600, color: C.sub }}>{it.source || hostname(it.link)}</span>
                                    {dateOnly(it.time) && <><span style={{ width: 2, height: 2, borderRadius: 2, background: C.faint }} /><span style={{ fontSize: 11.5, color: C.faint }}>{dateOnly(it.time)}</span></>}
                                </div>
                            </div>
                        )
                        return (
                            <div key={i} style={{ height: cardH, overflow: "hidden", background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, display: "flex", flexDirection: "column", justifyContent: "center" }}>
                                {it.link && it.link !== "#" ? <a href={it.link} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none", display: "block" }}>{body}</a> : body}
                            </div>
                        )
                    })}
                </div>
            )}
            <div style={{ padding: "12px 4px 2px", fontSize: 10.5, color: C.faint, fontWeight: 600 }}>출처 RSS(Cointelegraph·Google News) · 제목·출처·시각·원문만 · 해설·추천 아님</div>
        </div>
    )
}

addPropertyControls(CryptoNews, {
    dataUrl: { type: ControlType.String, title: "데이터 URL", defaultValue: BLOB + "/crypto_news.json" },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
    cardHeight: { type: ControlType.Number, title: "카드 높이", defaultValue: 92, min: 70, max: 160, step: 4, unit: "px" },
})

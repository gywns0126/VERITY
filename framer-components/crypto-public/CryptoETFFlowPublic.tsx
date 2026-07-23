import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * 크립토 ETF 자금흐름 렌즈 — TIDE 공개 보조 카드 (AlphaNest 정본 디자인 복제).
 * 디자인 = 토스식 미니멀: 무채색 위주 + 방향값만 유입(빨강)/유출(파랑), 얇은 구분선, 색배경·외곽선·이모지 없음.
 *
 * 표시 = BTC·ETH 현물 ETF 일일 순플로(유입/유출) + 누적 순플로 + AUM.
 * 🚨 RULE 7: 순유입·AUM = SoSoValue 1차 사실. 점수·추천 0. 🚨 RULE 6: LLM narrative 0.
 * 데이터 = crypto_etf_flow.json (Vercel Blob). 테마 = body[data-framer-theme] 자가 추종.
 */

interface Props {
    dataUrl: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/crypto_etf_flow.json"
const CACHE_KEY = "verity_crypto_etf_cache"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#f0f1f3", up: "#f04452", down: "#3182f6",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#222730", up: "#f04452", down: "#5b9bff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const DEMO = {
    ok: true,
    btc: { daily_net_inflow_usd: -68_000_000, cumulative_net_inflow_usd: 36_400_000_000, total_aum_usd: 80_000_000_000, as_of: "2026-06-23" },
    eth: { daily_net_inflow_usd: -66_000_000, cumulative_net_inflow_usd: 3_900_000_000, total_aum_usd: 9_400_000_000, as_of: "2026-06-23" },
}

// USD 단위 포맷 — 달러. signed=true 시 방향 부호.
function fmtUSD(usd: any, signed = false): string {
    const n = Number(usd)
    if (!isFinite(n) || n === 0) return signed ? "$0" : "—"
    const a = Math.abs(n)
    const sign = signed ? (n > 0 ? "+" : "−") : ""
    if (a >= 1e9) return sign + "$" + (a / 1e9).toFixed(2) + "B"
    if (a >= 1e6) return sign + "$" + (a / 1e6).toFixed(1) + "M"
    if (a >= 1e3) return sign + "$" + (a / 1e3).toFixed(1) + "K"
    return sign + "$" + Math.round(a).toLocaleString("en-US")
}
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch {
        return ""
    }
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
// 마운트/토글 재판독 SoT — verity_theme(localStorage) 우선 → html[data-an-theme] → body[data-framer-theme].
// 791d29f7e 8개 fix 에서 누락됐던 body-only 재판독 버그 정정(다크에서 라이트 고정 방지, 2026-07-21 일괄).
function readBodyDark(): boolean {
    if (typeof document === "undefined") return false
    try {
        const pref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (pref === "dark") return true
        if (pref === "light") return false
        const h = document.documentElement ? document.documentElement.dataset.anTheme : null
        if (h === "dark") return true
        if (h === "light") return false
        if (document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

export default function CryptoETFFlowPublic(props: Props) {
    const { dataUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [data, setData] = useState<any>(onCanvas ? DEMO : null)

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    // cache-fallback: localStorage 먼저 표시 → fetch 성공 시 갱신
    useEffect(() => {
        if (onCanvas) return
        try {
            const raw = typeof localStorage !== "undefined" ? localStorage.getItem(CACHE_KEY) : null
            if (raw) {
                const cached = JSON.parse(raw)
                if (cached && cached.btc && cached.eth) setData(cached)
            }
        } catch {}
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas || !dataUrl) return
        let alive = true
        fetch(dataUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d || !d.btc || !d.eth) return
                setData(d)
                try { if (typeof localStorage !== "undefined") localStorage.setItem(CACHE_KEY, JSON.stringify(d)) } catch {}
            })
            .catch(() => {})
        return () => { alive = false }
    }, [dataUrl, onCanvas])

    const narrow = w > 0 && w < 560
    const loading = !data

    const skBase = isDark ? "#1e242c" : "#edeff2"
    const skHi = isDark ? "#2a313b" : "#f5f6f8"
    const sk = (bw: any, bh: number, br = 7): CSSProperties => ({
        width: bw, height: bh, borderRadius: br, background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%", animation: "cefShimmer 1.4s ease-in-out infinite", flexShrink: 0,
    })

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT,
        padding: narrow ? 16 : 22, boxSizing: "border-box", color: C.ink,
    }
    const card: CSSProperties = {
        background: C.card, borderRadius: 18, padding: narrow ? 16 : 20, boxSizing: "border-box",
    }

    if (loading) {
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes cefShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ ...sk(110, 12, 6), marginBottom: 12 }} />
                <div style={{ ...sk("64%", 24, 8), marginBottom: 22 }} />
                <div style={{ ...sk("100%", 120, 18), marginBottom: 12 }} />
                <div style={sk("100%", 120, 18)} />
            </div>
        )
    }

    const dirColor = (f: number) => (f > 0 ? C.up : C.down)
    const asOf = data.btc?.as_of || data.eth?.as_of
    const assets: Array<{ key: string; label: string; sub: string; d: any }> = [
        { key: "btc", label: "Bitcoin", sub: "BTC 현물 ETF", d: data.btc },
        { key: "eth", label: "Ethereum", sub: "ETH 현물 ETF", d: data.eth },
    ]

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>ETF 자금흐름</div>
            <div style={{ fontSize: narrow ? 20 : 23, fontWeight: 700, color: C.ink, letterSpacing: "-0.5px", marginTop: 6 }}>BTC·ETH 현물 ETF</div>
            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 7 }}>
                일일 순플로 · 누적 순플로 · 운용자산(AUM) · SoSoValue{asOf ? ` · ${fmtAge(asOf)}` : ""}
            </div>

            {/* 자산별 카드 */}
            {assets.map((a) => {
                const d = a.d || {}
                const net = Number(d.daily_net_inflow_usd)
                const hasNet = isFinite(net) && net !== 0
                const col = hasNet ? dirColor(net) : C.faint
                return (
                    <div key={a.key} style={{ ...card, marginTop: 12 }}>
                        {/* 자산 타이틀 + 일일 순플로 */}
                        <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 14, fontWeight: 600, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{a.label}</div>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 2 }}>{a.sub}</div>
                            </div>
                            <div style={{ flexShrink: 0, textAlign: "right" }}>
                                {hasNet ? (
                                    <>
                                        <div style={{ fontSize: narrow ? 17 : 19, fontWeight: 700, color: col, letterSpacing: "-0.3px", fontVariantNumeric: "tabular-nums" }}>{fmtUSD(net, true)}</div>
                                        <div style={{ fontSize: 11, fontWeight: 500, color: col, marginTop: 2 }}>{net > 0 ? "순유입" : "순유출"} · 일일</div>
                                    </>
                                ) : (
                                    <span style={{ fontSize: 12, fontWeight: 500, color: C.faint }}>변동 없음</span>
                                )}
                            </div>
                        </div>

                        {/* 누적 + AUM */}
                        <div style={{ display: "flex", gap: 12, marginTop: 14, paddingTop: 14, borderTop: `1px solid ${C.line}` }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500 }}>누적 순플로</div>
                                <div style={{ fontSize: narrow ? 14 : 15, fontWeight: 600, color: C.ink, marginTop: 3, fontVariantNumeric: "tabular-nums" }}>{fmtUSD(d.cumulative_net_inflow_usd, true)}</div>
                            </div>
                            <div style={{ flex: 1, minWidth: 0, textAlign: "right" }}>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500 }}>운용자산(AUM)</div>
                                <div style={{ fontSize: narrow ? 14 : 15, fontWeight: 600, color: C.ink, marginTop: 3, fontVariantNumeric: "tabular-nums" }}>{fmtUSD(d.total_aum_usd)}</div>
                            </div>
                        </div>
                    </div>
                )
            })}

            {/* 면책 */}
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 500, marginTop: 18, lineHeight: 1.6 }}>
                ETF 순유입·AUM은 SoSoValue 사실이에요. 점수·추천 아니에요. 자체 채점은 검증 후(2027) 공개해요.
            </div>
        </div>
    )
}

addPropertyControls(CryptoETFFlowPublic, {
    dataUrl: { type: ControlType.String, title: "Crypto ETF URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

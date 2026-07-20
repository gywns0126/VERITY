import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 스테이블코인 공급 렌즈 — 공개형 TIDE. AlphaNest 정본 디자인 결(PublicETFFlow) 복제.
 * 토스식 미니멀: 무채색 위주 + 얇은 구분선, 색배경·외곽선·이모지 없음.
 *
 * 차별 각도: USDT/USDC 발행사 직접 공급 = 크립토 유동성 레짐 1차 신호(스테이블 = dry powder).
 * 🚨 RULE 7: 공급량 = Tether·Circle 발행사 사실. 점수·추천 0. RULE 6: LLM 0.
 * 데이터 = crypto_stablecoins.json (Vercel Blob). 테마 = body[data-framer-theme] 자가 추종.
 */

interface Props { dataUrl: string; dark: boolean }
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/crypto_stablecoins.json"
const CACHE_KEY = "verity_crypto_stable_cache"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#f0f1f3", up: "#f04452", down: "#3182f6",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#222730", up: "#f04452", down: "#5b9bff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const NUM: CSSProperties = { fontVariantNumeric: "tabular-nums" }

const CHAIN_KO: Record<string, string> = {
    ethereum: "이더리움", tron: "트론", solana: "솔라나", binance: "BNB", "bnb smart chain": "BNB",
    avalanche: "아발란체", arbitrum: "아비트럼", base: "베이스", polygon: "폴리곤", ton: "톤",
    optimism: "옵티미즘", aptos: "앱토스", near: "니어", celo: "셀로", "hedera": "헤데라",
}

function fmtUsd(v: any): string {
    const n = Number(v)
    if (!isFinite(n) || n <= 0) return "—"
    if (n >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B"
    if (n >= 1e6) return "$" + (n / 1e6).toFixed(0) + "M"
    return "$" + Math.round(n).toLocaleString("en-US")
}
function chainKo(c: any): string {
    const k = String(c || "").toLowerCase()
    return CHAIN_KO[k] || String(c || "")
}

const DEMO = {
    total_supply_usd: 260431191468,
    usdt: { total_supply_usd: 186300000000, by_chain: [{ chain: "ethereum", supply: 97100000000 }, { chain: "tron", supply: 89300000000 }, { chain: "solana", supply: 2200000000 }] },
    usdc: { total_supply_usd: 74100000000, by_chain: [{ chain: "ethereum", supply: 51400000000 }, { chain: "solana", supply: 7100000000 }, { chain: "base", supply: 4200000000 }] },
}

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

export default function CryptoStablecoinsPublic(props: Props) {
    const { dataUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    const [data, setData] = useState<any>(onCanvas ? DEMO : null)
    const [cacheTs, setCacheTs] = useState<number | null>(null)
    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)

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
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    useEffect(() => {
        if (onCanvas || !dataUrl) return
        let alive = true
        if (typeof localStorage !== "undefined") {
            try { const c = localStorage.getItem(CACHE_KEY); if (c) { const o = JSON.parse(c); if (o && o.data) { setData(o.data); setCacheTs(o.ts || null) } } } catch {}
        }
        fetch(dataUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d) return
                setData(d); setCacheTs(null)
                if (typeof localStorage !== "undefined") { try { localStorage.setItem(CACHE_KEY, JSON.stringify({ data: d, ts: Date.now() })) } catch {} }
            })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas, dataUrl])

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT
    const narrow = w > 0 && w < 560

    const issuers = useMemo(() => {
        if (!data) return [] as any[]
        const out: any[] = []
        for (const key of ["usdt", "usdc"]) {
            const x = data[key]
            if (x && x.total_supply_usd) {
                const chains = Array.isArray(x.by_chain) ? [...x.by_chain].sort((a, b) => Number(b.supply) - Number(a.supply)).slice(0, 6) : []
                out.push({ sym: key.toUpperCase(), total: Number(x.total_supply_usd), chains })
            }
        }
        return out
    }, [data])

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, padding: narrow ? 16 : 22, boxSizing: "border-box", color: C.ink }
    const card: CSSProperties = { background: C.card, borderRadius: 18, padding: narrow ? 16 : 20, boxSizing: "border-box" }

    if (!data) {
        const skBase = isDark ? "#1e242c" : "#edeff2"
        const skHi = isDark ? "#2a313b" : "#f5f6f8"
        const sk = (bw: any, bh: number, br = 7): CSSProperties => ({ width: bw, height: bh, borderRadius: br, background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "vscShimmer 1.4s ease-in-out infinite" })
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes vscShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ ...sk(120, 12, 6), marginBottom: 12 }} />
                <div style={{ ...sk("60%", 24, 8), marginBottom: 22 }} />
                <div style={{ ...sk("100%", 150, 18), marginBottom: 12 }} />
                <div style={sk("100%", 150, 18)} />
            </div>
        )
    }

    const total = Number(data.total_supply_usd) || issuers.reduce((s, x) => s + x.total, 0)
    const maxTotal = issuers.length ? Math.max(...issuers.map((x) => x.total)) : 0

    return (
        <div ref={rootRef} style={wrap}>
            {cacheTs != null && <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginBottom: 8, ...NUM }}>오프라인 캐시</div>}

            {/* 헤더 */}
            <div style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>스테이블코인 공급</div>
            <div style={{ fontSize: narrow ? 20 : 23, fontWeight: 700, color: C.ink, letterSpacing: "-0.5px", marginTop: 6 }}>USDT·USDC 유동성</div>
            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 7, ...NUM }}>총 공급 {fmtUsd(total)} · 발행사 직접 · dry powder</div>

            {/* 발행사별 카드 */}
            {issuers.map((it, ii) => (
                <div key={it.sym} style={{ ...card, marginTop: ii === 0 ? 18 : 12 }}>
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 14 }}>
                        <div style={{ fontSize: 14.5, fontWeight: 700, color: C.ink }}>{it.sym}</div>
                        <div style={{ fontSize: 15, fontWeight: 700, color: C.ink, ...NUM }}>{fmtUsd(it.total)}</div>
                    </div>
                    {it.chains.map((ch: any, ci: number) => {
                        const sup = Number(ch.supply) || 0
                        const pct = it.total ? Math.max(3, (sup / it.total) * 100) : 0
                        return (
                            <div key={ci} style={{ display: "flex", alignItems: "center", gap: 12, padding: "7px 0" }}>
                                <div style={{ width: narrow ? 64 : 78, flexShrink: 0, fontSize: 12.5, fontWeight: 500, color: C.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{chainKo(ch.chain)}</div>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ width: `${pct}%`, height: 8, borderRadius: 4, background: C.sub, opacity: 0.55 }} />
                                </div>
                                <div style={{ width: narrow ? 64 : 78, flexShrink: 0, textAlign: "right", fontSize: 12.5, fontWeight: 600, color: C.sub, ...NUM }}>{fmtUsd(sup)}</div>
                            </div>
                        )
                    })}
                </div>
            ))}

            {/* 면책 */}
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 500, marginTop: 18, lineHeight: 1.6 }}>
                공급량은 Tether·Circle 발행사 사실이에요. 스테이블 공급은 크립토 매수 여력(dry powder)의 1차 단서예요. 등급·추천이 아니며 자체 점수는 검증 후(2027) 공개해요.
            </div>
        </div>
    )
}

addPropertyControls(CryptoStablecoinsPublic, {
    dataUrl: { type: ControlType.String, title: "Stablecoins URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

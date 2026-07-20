import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * DAO 거버넌스 렌즈 — VERITY 공개 터미널 (AlphaNest / TIDE 보조). PublicETFFlow 디자인 정본 복제.
 * 디자인 = 토스식 미니멀: 무채색(ink/sub/faint) 위주, 색배경·외곽선·이모지 없음, 흰 카드 on 회색 배경.
 *
 * 🚨 차별 각도: 주요 DAO 거버넌스 제안(Snapshot)의 진행 중 투표를 리스트로. 토큰 가격이 아닌 "프로토콜 의사결정".
 * 🚨 RULE 7 / 6: 제안·투표수·마감은 Snapshot 사실. 점수·추천·LLM narrative 0. 테마 = body[data-framer-theme] 자가 추종.
 * 데이터 = crypto_governance.json (Snapshot 수집). title 클릭 → link 새 탭.
 */

interface Props {
    dataUrl: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/crypto_governance.json"
const CACHE_KEY = "verity_crypto_gov_cache"
const COLLAPSED = 6

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
    proposals: [
        { id: "d1", title: "Arbitrum DAO: Constitutional AIP — Treasury management framework update", space_name: "Arbitrum DAO", state: "active", start: 0, end: Math.floor(Date.now() / 1000) + 2 * 86400, scores_total: 0, votes: 1140, choices: ["For", "Against", "Abstain"], link: "https://snapshot.org" },
        { id: "d2", title: "Aave: Onboard new collateral and adjust risk parameters", space_name: "Aave", state: "active", start: 0, end: Math.floor(Date.now() / 1000) + 4 * 86400, scores_total: 0, votes: 152, choices: ["YAE", "NAY"], link: "https://snapshot.org" },
        { id: "d3", title: "Spark: Allocate liquidity to savings rate vault", space_name: "Spark", state: "active", start: 0, end: Math.floor(Date.now() / 1000) + 6 * 3600, scores_total: 0, votes: 1, choices: ["For", "Against"], link: "https://snapshot.org" },
    ],
}

function fmtVotes(v: any): string {
    const n = Number(v)
    if (!isFinite(n) || n < 0) return "—"
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M"
    if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K"
    return String(Math.round(n))
}
// 마감까지 남은 시간 — end = unix seconds.
function fmtEnd(end: any): string {
    const e = Number(end)
    if (!isFinite(e) || e <= 0) return ""
    const mins = Math.round((e * 1000 - Date.now()) / 60000)
    if (mins <= 0) return "마감"
    if (mins < 60) return mins + "분 남음"
    const hrs = Math.round(mins / 60)
    if (hrs < 24) return hrs + "시간 남음"
    return Math.round(hrs / 24) + "일 남음"
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

export default function CryptoGovernancePublic(props: Props) {
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
    const [showAll, setShowAll] = useState(false)

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
        // cache-fallback: 캐시 먼저 표시 후 네트워크로 갱신.
        try {
            const raw = typeof localStorage !== "undefined" ? localStorage.getItem(CACHE_KEY) : null
            if (raw) {
                const cached = JSON.parse(raw)
                if (cached && Array.isArray(cached.proposals)) setData(cached)
            }
        } catch {}
        fetch(dataUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d || !Array.isArray(d.proposals)) return
                setData(d)
                try { if (typeof localStorage !== "undefined") localStorage.setItem(CACHE_KEY, JSON.stringify(d)) } catch {}
            })
            .catch(() => {})
        return () => { alive = false }
    }, [dataUrl, onCanvas])

    const narrow = w > 0 && w < 560
    const loading = !data

    // 진행 중(active) 우선 + 투표수 내림차순.
    const rows = useMemo(() => {
        if (!data || !Array.isArray(data.proposals)) return [] as any[]
        return data.proposals
            .filter((p: any) => p && p.title)
            .slice()
            .sort((a: any, b: any) => {
                const aa = a.state === "active" ? 1 : 0
                const bb = b.state === "active" ? 1 : 0
                if (aa !== bb) return bb - aa
                return (Number(b.votes) || 0) - (Number(a.votes) || 0)
            })
    }, [data])

    const skBase = isDark ? "#1e242c" : "#edeff2"
    const skHi = isDark ? "#2a313b" : "#f5f6f8"
    const sk = (bw: any, bh: number, br = 7): CSSProperties => ({
        width: bw, height: bh, borderRadius: br, background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%", animation: "vcgShimmer 1.4s ease-in-out infinite", flexShrink: 0,
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
                <style>{`@keyframes vcgShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ ...sk(110, 12, 6), marginBottom: 12 }} />
                <div style={{ ...sk("64%", 24, 8), marginBottom: 22 }} />
                <div style={sk("100%", 280, 18)} />
            </div>
        )
    }

    const total = rows.length

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>DAO 거버넌스</div>
            <div style={{ fontSize: narrow ? 20 : 23, fontWeight: 700, color: C.ink, letterSpacing: "-0.5px", marginTop: 6 }}>진행 중 제안·투표</div>
            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 7 }}>
                주요 DAO 온체인 거버넌스 · Snapshot 진행 중 투표
            </div>

            {/* 비어 있음 */}
            {total === 0 && (
                <div style={{ ...card, marginTop: 18 }}>
                    <div style={{ fontSize: 14.5, fontWeight: 700, color: C.ink }}>진행 중 제안이 없어요</div>
                    <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 500, marginTop: 6, lineHeight: 1.55 }}>
                        지금은 주요 DAO에 활성 투표가 없어요. 새 제안이 올라오면 여기에 표시돼요.
                    </div>
                </div>
            )}

            {/* 제안 리스트 — 상위 6개 + 더보기 */}
            {total > 0 && (
                <div style={{ ...card, marginTop: 18, paddingTop: 6, paddingBottom: showAll || total <= COLLAPSED ? 6 : 0 }}>
                    {(showAll ? rows : rows.slice(0, COLLAPSED)).map((p: any, idx: number) => {
                        const endStr = fmtEnd(p.end)
                        const closed = endStr === "마감"
                        const titleStyle: CSSProperties = {
                            fontSize: 14, fontWeight: 600, color: C.ink, lineHeight: 1.4,
                            display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                            overflow: "hidden", textOverflow: "ellipsis",
                        }
                        return (
                            <div key={p.id || idx} style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "13px 0", borderTop: idx === 0 ? "none" : `1px solid ${C.line}` }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    {p.link ? (
                                        <a href={String(p.link)} target="_blank" rel="noopener noreferrer" style={{ ...titleStyle, textDecoration: "none" }}>{p.title}</a>
                                    ) : (
                                        <div style={titleStyle}>{p.title}</div>
                                    )}
                                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 4 }}>
                                        {p.space_name || "—"} · 투표 {fmtVotes(p.votes)}
                                    </div>
                                </div>
                                <div style={{ flexShrink: 0, textAlign: "right", paddingTop: 1 }}>
                                    <div style={{ fontSize: 12.5, fontWeight: 600, color: closed ? C.faint : C.sub, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{endStr || "—"}</div>
                                </div>
                            </div>
                        )
                    })}
                    {total > COLLAPSED && (
                        <button onClick={() => setShowAll((s) => !s)}
                            style={{ width: "100%", border: "none", cursor: "pointer", fontFamily: FONT, background: "transparent", padding: "13px 0", borderTop: `1px solid ${C.line}`, fontSize: 13, fontWeight: 600, color: C.sub }}>
                            {showAll ? "접기" : `더보기 (${total - COLLAPSED}개)`}
                        </button>
                    )}
                </div>
            )}

            {/* 면책 */}
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 500, marginTop: 18, lineHeight: 1.6 }}>
                제안·투표수는 Snapshot 사실이에요. 점수·추천 아니에요.
            </div>
        </div>
    )
}

addPropertyControls(CryptoGovernancePublic, {
    dataUrl: { type: ControlType.String, title: "Governance URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

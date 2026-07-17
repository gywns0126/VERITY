import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * GrowthCard — AlphaNest 성장·사용 통계 (AlphaNest 스타일).
 * 소스: /api/admin?type=growth_stats (is_admin · service_role). 가입 추이·회원·커뮤니티 활동.
 * 핵심 #1 = "사이트가 성장하고 있는가" (feedback_site_growth_is_core).
 * ⚠ 방문자/페이지뷰(트래픽)는 Framer 애널리틱스 탭에서 별도 확인 — API 부재로 여기 미포함.
 * 다크감지. 접근차단 = 페이지 AdminGate.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", down: "#3182f6",
    green: "#15c47e", amber: "#ff9500", vt: "#6c5ce7", vtS: "#f0edff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", grid: "#1e242c", up: "#f04452", down: "#5b9bff",
    green: "#34e08a", amber: "#ff9500", vt: "#a99bff", vtS: "#241f3a",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const SESSION_KEY = "verity_supabase_session"

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {}
    return false
}
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
function nStr(v: any): string {
    if (v == null) return "—"
    const x = Number(v)
    return isFinite(x) ? x.toLocaleString("en-US") : "—"
}
// Catmull-Rom → 부드러운 곡선 (가입 추이)
function smooth(pts: { x: number; y: number }[]): string {
    if (pts.length === 0) return ""
    if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`
    let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`
    for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2
        const c1x = p1.x + (p2.x - p0.x) / 6, c1y = p1.y + (p2.y - p0.y) / 6
        const c2x = p2.x - (p3.x - p1.x) / 6, c2y = p2.y - (p3.y - p1.y) / 6
        d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`
    }
    return d
}

interface Stats {
    members?: { total?: number; d1?: number; d7?: number; d30?: number; pending?: number; banned?: number }
    community?: { total?: number; public?: number; d7?: number }
    signups_daily?: Array<{ date: string; count: number }>
}

const SAMPLE: Stats = {
    members: { total: 342, d1: 4, d7: 28, d30: 121, pending: 6, banned: 2 },
    community: { total: 156, public: 89, d7: 17 },
    signups_daily: (() => {
        const a: Array<{ date: string; count: number }> = []
        for (let i = 29; i >= 0; i--) a.push({ date: "d" + i, count: Math.round(2 + 4 * Math.abs(Math.sin(i * 0.7)) + (i < 10 ? 3 : 0)) })
        return a
    })(),
}

interface Props { apiBase: string; dark: boolean }

export default function GrowthCard(props: Props) {
    const apiBase = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT
    const [st, setSt] = useState<Stats | null>(onCanvas ? SAMPLE : null)
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState("")

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || !document.body) return
        const o = new MutationObserver(read)
        o.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => o.disconnect()
    }, [onCanvas])

    const load = useCallback(() => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setLoading(true); setErr("")
        fetch(`${apiBase}/api/admin?type=growth_stats`, { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
            .then((d) => setSt(d as Stats))
            .catch((e) => setErr("불러오기 실패: " + (e && e.message ? e.message : e)))
            .finally(() => setLoading(false))
    }, [apiBase, onCanvas])

    useEffect(() => { load() }, [load])

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: 16, display: "flex", flexDirection: "column", gap: 12 }
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const num: CSSProperties = { fontVariantNumeric: "tabular-nums" }

    if (err && !st) return <div style={wrap}><div style={{ ...card, color: C.up, fontSize: 13, fontWeight: 700 }}>성장 통계 로드 실패: {err.slice(0, 90)}</div></div>
    if (!st) return <div style={wrap}><div style={{ ...card, color: C.faint, fontSize: 13, fontWeight: 600 }}>성장 통계 로딩…</div></div>

    const m = st.members || {}
    const c = st.community || {}
    const series = st.signups_daily || []
    const counts = series.map((s) => Number(s.count) || 0)
    const mx = Math.max(1, ...counts)
    const CW = 640, CH = 90, PX = 4, PY = 10
    const pts = series.map((s, i) => ({ x: PX + (i / Math.max(1, series.length - 1)) * (CW - PX * 2), y: PY + (1 - (Number(s.count) || 0) / mx) * (CH - PY * 2) }))
    const linePath = smooth(pts)
    const areaPath = pts.length >= 2 ? `${linePath} L ${pts[pts.length - 1].x.toFixed(1)} ${CH} L ${pts[0].x.toFixed(1)} ${CH} Z` : ""
    const sum30 = counts.reduce((a, b) => a + b, 0)

    const tile = (label: string, val: any, accent?: string) => (
        <div style={{ flex: "1 1 90px", background: C.grid, borderRadius: 12, padding: "12px 13px" }}>
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 700 }}>{label}</div>
            <div style={{ ...num, fontSize: 22, fontWeight: 800, letterSpacing: "-0.6px", color: accent || C.ink, marginTop: 3 }}>{nStr(val)}</div>
        </div>
    )

    return (
        <div style={wrap}>
            {/* 헤더 + 핵심 타일 */}
            <div style={card}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 12 }}>
                    <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px" }}>성장 · 사용</span>
                    <span style={{ marginLeft: "auto", fontSize: 11, color: C.faint, fontWeight: 600, cursor: "pointer" }} onClick={load}>{loading ? "불러오는 중…" : "새로고침"}</span>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {tile("총 회원", m.total, C.vt)}
                    {tile("오늘 신규", m.d1, C.green)}
                    {tile("7일 신규", m.d7, C.green)}
                    {tile("30일 신규", m.d30)}
                </div>
                {err && <div style={{ fontSize: 12, color: C.up, fontWeight: 700, marginTop: 10 }}>{err}</div>}
            </div>

            {/* 가입 추이 */}
            <div style={card}>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10 }}>
                    <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.3px" }}>가입 추이</span>
                    <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>최근 30일 · 합 {nStr(sum30)}</span>
                </div>
                {pts.length >= 2 ? (
                    <svg width="100%" viewBox={`0 0 ${CW} ${CH}`} style={{ display: "block" }} preserveAspectRatio="none">
                        {areaPath && <path d={areaPath} fill={C.vt} fillOpacity={0.1} />}
                        <path d={linePath} fill="none" stroke={C.vt} strokeWidth={2.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                        <circle cx={pts[pts.length - 1].x} cy={pts[pts.length - 1].y} r={3.4} fill={C.vt} />
                    </svg>
                ) : (
                    <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>추이 데이터가 아직 부족해요</div>
                )}
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>실가입 기준(전환) · 방문자·페이지뷰는 Framer 애널리틱스에서 확인</div>
            </div>

            {/* 커뮤니티 + 상태 */}
            <div style={card}>
                <div style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.3px", marginBottom: 12 }}>커뮤니티 · 상태</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {tile("공개 글", c.public, C.vt)}
                    {tile("7일 글", c.d7, C.green)}
                    {tile("승인 대기", m.pending, (Number(m.pending) || 0) > 0 ? C.amber : undefined)}
                    {tile("제재됨", m.banned, (Number(m.banned) || 0) > 0 ? C.up : undefined)}
                </div>
            </div>
        </div>
    )
}

addPropertyControls(GrowthCard, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})

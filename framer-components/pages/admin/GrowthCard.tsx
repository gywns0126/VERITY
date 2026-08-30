import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * GrowthCard — AlphaNest 성장·사용 통계 (AlphaNest 스타일).
 * 소스: /api/admin?type=growth_stats (is_admin · service_role). 익명 방문·가입 추이·회원·커뮤니티 활동.
 * 핵심 #1 = "사이트가 성장하고 있는가" (feedback_site_growth_is_core).
 * 방문자 = PublicSessionKeeper → site_visit_days. 페이지·검색어·종목·IP는 저장하지 않는다.
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
// CSS가 body[data-framer-theme]를 직접 따라간다. 테마 변경에 React 상태/Observer를 사용하지 않는다.
const ADMIN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-admin-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-admin-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: any = {}
for (const k of Object.keys(LIGHT)) C[k] = "var(--an-admin-" + k + ")"

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const SESSION_KEY = "verity_supabase_session"
const AUTH_EVENT = "verity_auth_change"

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
function pctStr(v: any): string {
    if (v == null) return "—"
    const x = Number(v)
    return isFinite(x) ? `${x.toLocaleString("en-US")}%` : "—"
}
function smooth(pts: { x: number; y: number }[]): string {
    if (pts.length === 0) return ""
    if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`
    let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`
    for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2
        const c1x = p1.x + (p2.x - p0.x) / 6
        const c2x = p2.x - (p3.x - p1.x) / 6
        // 🚨 2026-07-27 오버슛 제거 — Catmull-Rom 제어점이 구간 밖으로 나가면 값이 평평하다가
        //   아래로 파인 뒤 솟는다(PM 지적: 30일 합 1인데 내려갔다 올라감).
        //   실측: 두 점 모두 y=80 인데 c2y=91.67. 제어점을 구간 [min,max] 로 클램프해 단조성 보존.
        const lo = Math.min(p1.y, p2.y), hi = Math.max(p1.y, p2.y)
        const clamp = (v: number) => Math.min(hi, Math.max(lo, v))
        const c1y = clamp(p1.y + (p2.y - p0.y) / 6)
        const c2y = clamp(p2.y - (p3.y - p1.y) / 6)
        d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`
    }
    return d
}

interface Stats {
    visitors?: { status?: string; today?: number; d7?: number; d30?: number; returning_30d?: number; return_rate_30d_pct?: number; visitor_days_30d?: number; visits_30d?: number; daily?: Array<{ date: string; count: number }> }
    members?: { total?: number; d1?: number; d7?: number; d30?: number; pending?: number; banned?: number }
    community?: { total?: number; public?: number; d7?: number }
    signups_daily?: Array<{ date: string; count: number }>
}

const SAMPLE: Stats = {
    visitors: { status: "measured", today: 128, d7: 684, d30: 2140, returning_30d: 512, return_rate_30d_pct: 23.9, visitor_days_30d: 3188, visits_30d: 3324 },
    members: { total: 342, d1: 4, d7: 28, d30: 121, pending: 6, banned: 2 },
    community: { total: 156, public: 89, d7: 17 },
    signups_daily: (() => {
        const a: Array<{ date: string; count: number }> = []
        for (let i = 29; i >= 0; i--) a.push({ date: "d" + i, count: Math.round(2 + 4 * Math.abs(Math.sin(i * 0.7)) + (i < 10 ? 3 : 0)) })
        return a
    })(),
}

interface Props { apiBase: string; dark: boolean }


/* 🚨 2026-07-27 /admin 최초 로딩 스켈레톤 — "…로딩" 텍스트 한 줄이면 카드 높이가 0에 가깝다가
   데이터 도착 순간 튀어오른다. 실제 레이아웃과 같은 골격을 먼저 깔아 점프를 없앤다(PM 지적). */
const ADM_SK_KEYS = "@keyframes admSk{0%{background-position:-400px 0}100%{background-position:400px 0}}"
function admSk(C: any, w: any, h: number, r: number = 6): CSSProperties {
    return {
        width: w, height: h, borderRadius: r, flexShrink: 0,
        background: `linear-gradient(90deg, ${C.grid || C.line} 25%, ${C.line} 37%, ${C.grid || C.line} 63%)`,
        backgroundSize: "800px 100%", animation: "admSk 1.4s ease-in-out infinite",
    }
}
function AdmSkeletonTiles(props: { C: any; card: CSSProperties; groups?: number; tiles?: number }) {
    const { C, card } = props
    const g = props.groups || 2
    const t = props.tiles || 4
    return (
        <div aria-busy="true" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <style>{ADM_SK_KEYS}</style>
            {Array.from({ length: g }).map((_, gi) => (
                <div key={gi} style={card}>
                    <div style={{ ...admSk(C, 96, 14), marginBottom: 12 }} />
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        {Array.from({ length: t }).map((_, ti) => (
                            <div key={ti} style={{ flex: "1 1 120px", minWidth: 110, padding: "12px 14px",
                                borderRadius: 12, background: C.grid || C.line }}>
                                <div style={admSk(C, "60%", 11)} />
                                <div style={{ ...admSk(C, "40%", 20), marginTop: 8 }} />
                            </div>
                        ))}
                    </div>
                </div>
            ))}
        </div>
    )
}

export default function GrowthCard(props: Props) {
    const apiBase = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [st, setSt] = useState<Stats | null>(onCanvas ? SAMPLE : null)
    const [detailsOpen, setDetailsOpen] = useState(false)
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState("")

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

    // PublicSessionKeeper가 만료 토큰을 갱신하면 새 access token으로 즉시 재조회한다.
    // 이 리스너가 없으면 최초 403이 화면에 남아 수동 새로고침 전까지 복구되지 않는다.
    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        const onAuth = () => load()
        window.addEventListener(AUTH_EVENT, onAuth)
        window.addEventListener("storage", onAuth)
        return () => {
            window.removeEventListener(AUTH_EVENT, onAuth)
            window.removeEventListener("storage", onAuth)
        }
    }, [load, onCanvas])

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: 16, display: "flex", flexDirection: "column", gap: 12 }
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const num: CSSProperties = { fontVariantNumeric: "tabular-nums" }

    if (err && !st) return <div style={wrap}>
            <style>{ADMIN_PALETTE}</style><div style={{ ...card, color: C.up, fontSize: 13, fontWeight: 700 }}>성장 통계 로드 실패: {err.slice(0, 90)}</div></div>
    if (!st) return <div style={wrap}>
            <style>{ADMIN_PALETTE}</style><AdmSkeletonTiles C={C} card={card} groups={2} tiles={4} /></div>

    const m = st.members || {}
    const c = st.community || {}
    const v = st.visitors || {}
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
            <style>{ADMIN_PALETTE}</style>
            <div style={card}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 12 }}>
                    <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px" }}>한눈에 보기</span>
                    <button onClick={() => setDetailsOpen((x) => !x)} style={{ marginLeft: "auto", border: "none", background: "transparent", color: C.vt, fontSize: 11, fontWeight: 800, cursor: "pointer" }}>{detailsOpen ? "상세 접기" : "상세 보기"}</button>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {tile("오늘 방문", v.today, C.green)}
                    {tile("7일 방문", v.d7, C.vt)}
                    {tile("총 회원", m.total, C.vt)}
                    {tile("7일 신규", m.d7, C.green)}
                    {tile("제재", m.banned, (Number(m.banned) || 0) > 0 ? C.up : undefined)}
                    {tile("공개 글", c.public)}
                </div>
                {v.status !== "measured" && <div style={{ fontSize: 11, color: C.amber, fontWeight: 700, marginTop: 8 }}>방문 측정 연결을 확인해주세요</div>}
                {err && <div style={{ fontSize: 12, color: C.up, fontWeight: 700, marginTop: 10 }}>{err}</div>}
            </div>

            {detailsOpen && <>
                <div style={card}>
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10 }}>
                        <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.3px" }}>방문 · 가입 상세</span>
                        <button onClick={load} style={{ border: "none", background: "transparent", color: C.faint, fontSize: 11, fontWeight: 700, cursor: "pointer" }}>{loading ? "불러오는 중…" : "새로고침"}</button>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        {tile("30일 방문", v.d30)}
                        {tile("30일 재방문", v.returning_30d, C.green)}
                        {tile("오늘 신규", m.d1, C.green)}
                        {tile("30일 신규", m.d30)}
                    </div>
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>재방문율 {pctStr(v.return_rate_30d_pct)} · 방문일수 {nStr(v.visitor_days_30d)} · 방문 기록 {nStr(v.visits_30d)}회 · 7일 글 {nStr(c.d7)}</div>
                </div>
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
                    ) : <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>추이 데이터가 아직 부족해요</div>}
                </div>
            </>}
        </div>
    )
}

addPropertyControls(GrowthCard, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})

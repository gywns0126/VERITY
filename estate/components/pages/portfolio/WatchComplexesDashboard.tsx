// WatchComplexesDashboard — 단지 watchlist CRUD (V0_WATCHLIST 동적 등록)
// estate/components/pages/portfolio/ 도메인.
//
// 단지 등록 → estate_brain_builder cron 다음 발화 시 자동 산출 (KST 10:00 평일)
// → /api/estate/brain?complex_id=... 에서 read-through 가능.
//
// API: /api/estate/watch-complexes (GET/POST/DELETE)
// Auth: Supabase access token (verity-terminal.framer.website 세션 공유)

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useMemo } from "react"

/* ◆ ESTATE 패밀리룩 v3 (accent gold #B8864D) ◆ */
const C = {
    bgPage: "#0A0908", bgCard: "#0F0D0A", bgElevated: "#16130E", bgInput: "#1F1B14",
    border: "transparent", borderStrong: "#3A3024",
    textPrimary: "#F2EFE9", textSecondary: "#A8A299", textTertiary: "#6B665E", textDisabled: "#4A453E",
    accent: "#B8864D", accentBright: "#D4A26B", accentSoft: "rgba(184,134,77,0.15)",
    statusPos: "#22C55E", statusNeut: "#A8A299", statusNeg: "#EF4444",
    info: "#5BA9FF",
}
const T = { cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 6, md: 10, lg: 14 }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
const MOTION: React.CSSProperties = { transition: "all 200ms ease" }

const SEOUL_25 = [
    "강남구", "서초구", "송파구", "강동구", "마포구",
    "용산구", "성동구", "광진구", "중구", "종로구",
    "서대문구", "은평구", "강서구", "양천구", "영등포구",
    "구로구", "금천구", "관악구", "동작구", "성북구",
    "동대문구", "중랑구", "노원구", "도봉구", "강북구",
] as const

/* ◆ JWT 인증 — verity-terminal 패턴 정합 (localStorage access_token 직접 읽기) ◆ */
const SUPABASE_SESSION_KEY = "verity_supabase_session"

function getAccessToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const raw = localStorage.getItem(SUPABASE_SESSION_KEY)
        if (!raw) return ""
        const s = JSON.parse(raw)
        return s && typeof s.access_token === "string" ? s.access_token : ""
    } catch {
        return ""
    }
}

const REDEV_STAGES = [
    { value: "", label: "해당 없음 (재건축/재개발 대상 X)" },
    { value: "district_designation", label: "정비구역 지정" },
    { value: "union_setup", label: "조합설립 인가" },
    { value: "business_plan", label: "사업시행 인가" },
    { value: "management_plan", label: "관리처분 인가" },
    { value: "relocation", label: "이주·철거" },
    { value: "completion", label: "준공·입주" },
] as const

const PROJECT_TYPES = [
    { value: "", label: "—" },
    { value: "reconstruction", label: "재건축" },
    { value: "redevelopment", label: "재개발" },
] as const


/* ◆ TYPES ◆ */
interface Complex {
    id: string
    gu: string
    dong: string
    apt: string
    apt_normalized: string
    build_year: number
    project_type: string | null
    redev_stage: string | null
    months_in_stage: number
    valuation_pending: boolean
    subscription_announced: boolean
    memo: string
    created_at: string
    updated_at: string
}


/* ◆ UTILS ◆ */
function complexId(c: Pick<Complex, "gu" | "dong" | "apt_normalized" | "build_year">): string {
    return `${c.gu}_${c.dong}_${c.apt_normalized}_${c.build_year || 0}`
}


/* ◆ ENTRY FORM ◆ */
function EntryForm({ apiUrl, token, onAdded }: {
    apiUrl: string; token: string; onAdded: (c: Complex) => void
}) {
    const [gu, setGu] = useState("강남구")
    const [dong, setDong] = useState("")
    const [apt, setApt] = useState("")
    const [buildYear, setBuildYear] = useState("")
    const [projectType, setProjectType] = useState("")
    const [redevStage, setRedevStage] = useState("")
    const [monthsInStage, setMonthsInStage] = useState("")
    const [valuationPending, setValuationPending] = useState(false)
    const [subscriptionAnnounced, setSubscriptionAnnounced] = useState(false)
    const [memo, setMemo] = useState("")
    const [submitting, setSubmitting] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    const reset = () => {
        setDong(""); setApt(""); setBuildYear("")
        setProjectType(""); setRedevStage(""); setMonthsInStage("")
        setValuationPending(false); setSubscriptionAnnounced(false)
        setMemo("")
    }

    const submit = async () => {
        setErr(null)
        if (!apt.trim() || !dong.trim()) {
            setErr("동 / 단지명 필수")
            return
        }
        setSubmitting(true)
        try {
            const r = await fetch(`${apiUrl.replace(/\/$/, "")}/api/estate/watch-complexes`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
                body: JSON.stringify({
                    gu, dong: dong.trim(), apt: apt.trim(),
                    build_year: buildYear ? parseInt(buildYear) : 0,
                    project_type: projectType || null,
                    redev_stage: redevStage || null,
                    months_in_stage: monthsInStage ? parseInt(monthsInStage) : 0,
                    valuation_pending: valuationPending,
                    subscription_announced: subscriptionAnnounced,
                    memo: memo.trim(),
                }),
            })
            const j = await r.json().catch(() => ({}))
            if (!r.ok) {
                setErr(j?.error === "duplicate" ? "이미 등록된 단지" : (j?.message || `HTTP ${r.status}`))
                return
            }
            onAdded(j.complex)
            reset()
        } catch (e: any) {
            setErr(e?.message || "fetch failed")
        } finally {
            setSubmitting(false)
        }
    }

    const inputStyle: React.CSSProperties = {
        background: C.bgInput, color: C.textPrimary,
        border: `1px solid ${C.borderStrong}`, borderRadius: R.sm,
        padding: `${S.sm}px ${S.md}px`, fontSize: T.body,
        fontFamily: FONT, outline: "none", ...MOTION,
    }

    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: S.md,
            padding: S.lg, background: C.bgCard, borderRadius: R.md,
            border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.accent}`,
        }}>
            <span style={{ fontSize: T.cap, color: C.textTertiary,
                textTransform: "uppercase", letterSpacing: 1 }}>
                관심 단지 등록
            </span>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: S.sm }}>
                <select value={gu} onChange={e => setGu(e.target.value)} style={inputStyle}>
                    {SEOUL_25.map(g => <option key={g} value={g}>{g}</option>)}
                </select>
                <input value={dong} onChange={e => setDong(e.target.value)}
                    placeholder="동 (예: 대치동)" style={inputStyle} maxLength={50} />
                <input value={apt} onChange={e => setApt(e.target.value)}
                    placeholder="단지명 (예: 은마)" style={inputStyle} maxLength={100} />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: S.sm }}>
                <input value={buildYear} onChange={e => setBuildYear(e.target.value.replace(/[^0-9]/g, ""))}
                    placeholder="건축연도" style={inputStyle} maxLength={4} inputMode="numeric" />
                <select value={projectType} onChange={e => setProjectType(e.target.value)} style={inputStyle}>
                    {PROJECT_TYPES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
                <select value={redevStage} onChange={e => setRedevStage(e.target.value)} style={inputStyle}>
                    {REDEV_STAGES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
                <input value={monthsInStage}
                    onChange={e => setMonthsInStage(e.target.value.replace(/[^0-9]/g, ""))}
                    placeholder="현 단계 진행 M" style={inputStyle} maxLength={3} inputMode="numeric" />
            </div>

            {redevStage && (
                <div style={{ display: "flex", gap: S.lg, fontSize: T.cap, color: C.textSecondary }}>
                    <label style={{ display: "flex", alignItems: "center", gap: S.xs, cursor: "pointer" }}>
                        <input type="checkbox" checked={valuationPending}
                            onChange={e => setValuationPending(e.target.checked)} />
                        종전자산평가 발표 대기
                    </label>
                    <label style={{ display: "flex", alignItems: "center", gap: S.xs, cursor: "pointer" }}>
                        <input type="checkbox" checked={subscriptionAnnounced}
                            onChange={e => setSubscriptionAnnounced(e.target.checked)} />
                        일반분양 공고
                    </label>
                </div>
            )}

            <input value={memo} onChange={e => setMemo(e.target.value)}
                placeholder="메모 (선택)" style={inputStyle} maxLength={500} />

            {err && (
                <span style={{ fontSize: T.cap, color: C.statusNeg, fontWeight: T.w_semi }}>
                    ⚠ {err}
                </span>
            )}

            <button onClick={submit} disabled={submitting}
                style={{
                    padding: `${S.sm}px ${S.lg}px`, fontSize: T.body,
                    fontWeight: T.w_semi,
                    background: submitting ? C.bgInput : C.accent,
                    color: submitting ? C.textTertiary : "#0A0908",
                    border: "none", borderRadius: R.sm, cursor: submitting ? "wait" : "pointer",
                    fontFamily: FONT, ...MOTION,
                }}>
                {submitting ? "등록 중…" : "+ 단지 등록"}
            </button>
        </div>
    )
}


/* ◆ COMPLEX LIST ◆ */
function ComplexCard({ complex, apiUrl, token, onDeleted, brainPageUrl }: {
    complex: Complex; apiUrl: string; token: string;
    onDeleted: (id: string) => void; brainPageUrl: string
}) {
    const [deleting, setDeleting] = useState(false)
    const cid = useMemo(() => complexId(complex), [complex])

    const remove = async () => {
        if (!confirm(`${complex.apt} 삭제?`)) return
        setDeleting(true)
        try {
            const r = await fetch(`${apiUrl.replace(/\/$/, "")}/api/estate/watch-complexes`, {
                method: "DELETE",
                headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
                body: JSON.stringify({ id: complex.id }),
            })
            if (r.ok) onDeleted(complex.id)
        } finally {
            setDeleting(false)
        }
    }

    const drillDownUrl = useMemo(() => {
        if (!brainPageUrl) return ""
        const sep = brainPageUrl.includes("?") ? "&" : "?"
        return `${brainPageUrl}${sep}complex_id=${encodeURIComponent(cid)}`
    }, [brainPageUrl, cid])

    const stageLabel = REDEV_STAGES.find(s => s.value === complex.redev_stage)?.label
    const projectLabel = complex.project_type === "reconstruction" ? "재건축"
        : complex.project_type === "redevelopment" ? "재개발" : null

    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: S.sm,
            padding: S.md, background: C.bgCard, borderRadius: R.md,
            border: `1px solid ${C.border}`, ...MOTION,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: T.title, fontWeight: T.w_bold, color: C.textPrimary }}>
                    {complex.apt}
                </span>
                <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO }}>
                    {complex.build_year || "—"}
                </span>
            </div>
            <span style={{ fontSize: T.cap, color: C.textSecondary }}>
                {complex.gu} {complex.dong}
            </span>
            {(stageLabel || projectLabel) && (
                <div style={{ display: "flex", gap: S.sm, flexWrap: "wrap" }}>
                    {projectLabel && (
                        <span style={{
                            padding: "2px 8px", borderRadius: R.sm,
                            background: C.accentSoft, color: C.accent,
                            fontSize: T.cap - 1, fontWeight: T.w_semi,
                        }}>{projectLabel}</span>
                    )}
                    {stageLabel && (
                        <span style={{
                            padding: "2px 8px", borderRadius: R.sm,
                            background: C.bgElevated, color: C.textSecondary,
                            fontSize: T.cap - 1,
                        }}>{stageLabel}</span>
                    )}
                </div>
            )}
            {complex.memo && (
                <span style={{ fontSize: T.cap, color: C.textSecondary,
                    fontStyle: "italic" }}>"{complex.memo}"</span>
            )}
            <div style={{ display: "flex", justifyContent: "space-between",
                alignItems: "center", marginTop: S.xs, gap: S.xs }}>
                <code style={{ ...MONO, fontSize: T.cap - 1, color: C.textTertiary,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    flex: 1, minWidth: 0 }}>
                    {cid}
                </code>
                <div style={{ display: "flex", gap: S.xs, flexShrink: 0 }}>
                    {drillDownUrl && (
                        <a href={drillDownUrl}
                            style={{
                                padding: `${S.xs}px ${S.sm}px`, fontSize: T.cap,
                                background: C.accentSoft, color: C.accent,
                                border: `1px solid ${C.accent}`, borderRadius: R.sm,
                                cursor: "pointer", fontFamily: FONT, fontWeight: T.w_semi,
                                textDecoration: "none", ...MOTION,
                            }}>
                            Brain →
                        </a>
                    )}
                    <button onClick={remove} disabled={deleting}
                        style={{
                            padding: `${S.xs}px ${S.sm}px`, fontSize: T.cap,
                            background: "transparent", color: C.textTertiary,
                            border: `1px solid ${C.borderStrong}`, borderRadius: R.sm,
                            cursor: deleting ? "wait" : "pointer", fontFamily: FONT,
                            ...MOTION,
                        }}>
                        {deleting ? "…" : "삭제"}
                    </button>
                </div>
            </div>
        </div>
    )
}


/* ◆ MAIN ◆ */
interface Props {
    apiUrl: string
    brainPageUrl: string   // EstateBrainPanel 페이지 URL — 카드 → Brain drill-down (?complex_id=... 자동 부착)
}

export default function WatchComplexesDashboard(props: Props) {
    const { apiUrl, brainPageUrl } = props
    const [token, setToken] = useState<string>(() => getAccessToken())
    const [complexes, setComplexes] = useState<Complex[]>([])
    const [loading, setLoading] = useState(true)
    const [err, setErr] = useState<string | null>(null)

    // localStorage 세션 변경 감지 — storage 이벤트는 *다른* 탭만 발생.
    // 같은 탭에서 EstateAuthPage 로그인 후 페이지 이동 시 mount 시점 token 빈 채 유지되는 결함.
    // → visibilitychange + focus + 2초 polling 으로 같은 탭 갱신 보강.
    useEffect(() => {
        if (typeof window === "undefined") return
        const refresh = () => {
            const t = getAccessToken()
            setToken(prev => prev === t ? prev : t)
        }
        const onStorage = (e: StorageEvent) => {
            if (e.key === SUPABASE_SESSION_KEY) refresh()
        }
        window.addEventListener("storage", onStorage)
        window.addEventListener("focus", refresh)
        document.addEventListener("visibilitychange", refresh)
        const id = window.setInterval(refresh, 2000)
        return () => {
            window.removeEventListener("storage", onStorage)
            window.removeEventListener("focus", refresh)
            document.removeEventListener("visibilitychange", refresh)
            window.clearInterval(id)
        }
    }, [])

    useEffect(() => {
        if (!token) {
            setErr("로그인 필요 — 세션 토큰 없음")
            setLoading(false)
            return
        }
        if (!apiUrl) {
            setErr("apiUrl 필요")
            setLoading(false)
            return
        }
        const ctl = new AbortController()
        ;(async () => {
            setLoading(true); setErr(null)
            try {
                const r = await fetch(`${apiUrl.replace(/\/$/, "")}/api/estate/watch-complexes`, {
                    headers: { "Authorization": `Bearer ${token}` },
                    signal: ctl.signal,
                })
                const j = await r.json().catch(() => ({}))
                if (!r.ok) {
                    setErr(j?.message || `HTTP ${r.status}`)
                } else {
                    setComplexes(j.complexes || [])
                }
            } catch (e: any) {
                if (e?.name !== "AbortError") setErr(e?.message || "fetch failed")
            } finally {
                setLoading(false)
            }
        })()
        return () => ctl.abort()
    }, [apiUrl, token])

    const onAdded = (c: Complex) => setComplexes(prev => [c, ...prev])
    const onDeleted = (id: string) => setComplexes(prev => prev.filter(c => c.id !== id))

    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: S.lg,
            padding: S.lg, background: C.bgPage,
            fontFamily: FONT, color: C.textPrimary,
            width: "100%", boxSizing: "border-box",
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary }}>
                    관심 단지
                </span>
                <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO }}>
                    {loading ? "loading…" : `${complexes.length} 단지`}
                </span>
            </div>

            {token && <EntryForm apiUrl={apiUrl} token={token} onAdded={onAdded} />}

            {err && (
                <div style={{
                    padding: `${S.sm}px ${S.md}px`, borderRadius: R.sm,
                    background: C.statusNeg + "1A", color: C.statusNeg,
                    fontSize: T.cap, fontWeight: T.w_semi,
                }}>⚠ {err}</div>
            )}

            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                gap: S.md,
            }}>
                {complexes.map(c => (
                    <ComplexCard key={c.id} complex={c} apiUrl={apiUrl}
                        token={token} onDeleted={onDeleted}
                        brainPageUrl={brainPageUrl} />
                ))}
            </div>

            {!loading && complexes.length === 0 && !err && (
                <span style={{ fontSize: T.body, color: C.textTertiary,
                    textAlign: "center", padding: S.xl }}>
                    등록된 단지 없음. 위 폼에서 첫 단지 등록.
                </span>
            )}
        </div>
    )
}


addPropertyControls(WatchComplexesDashboard, {
    apiUrl: {
        type: ControlType.String,
        title: "API URL",
        defaultValue: "https://project-yw131.vercel.app",
    },
    brainPageUrl: {
        type: ControlType.String,
        title: "Brain Page URL",
        defaultValue: "/estate/residential",
        description: "EstateBrainPanel 페이지 URL — 카드 클릭 시 ?complex_id=... 자동 부착",
    },
})

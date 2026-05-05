import { addPropertyControls, ControlType } from "framer"
import {
    useCallback,
    useEffect,
    useRef,
    useState,
    type CSSProperties,
    type MutableRefObject,
} from "react"

/**
 * LiveVisitorPill — VERITY 우상단 고정 접속 상태 pill (B 옵션)
 *
 * 출처: LiveVisitors.tsx (1015줄) modernize + 책임 분리.
 *
 * 사용자가 보는 것 (default pill):
 *   [● 5 LIVE]  ← 우상단 고정 (모던 심플)
 *
 * 호버/클릭 시 (보안 패널 — 필수 요소만):
 *   - 현재 접속 N명
 *   - 의심 활동 ✓ (없음 / 감지)
 *   - 보안 단속 ● 활성 (heartbeat 신선도)
 *   - 마지막 점검 X초 전
 *   ※ cap 숫자·차단 history 는 admin only (AdminDashboard 흡수, Step 9)
 *
 * Backend 연동:
 *   - Supabase live_visitors 테이블 (session_id, last_seen, country_code, place_label)
 *   - heartbeat upsert + 활성 카운트 조회 (기존 LiveVisitors.tsx 로직 그대로)
 *   - cap 단속 자체는 AuthGate / 별도 Supabase RPC 영역 (본 컴포넌트는 가시화만)
 *
 * 분량: 1015 → ~520 줄 (49% 절감 + 책임 분리)
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    success: "0 0 6px rgba(34,197,94,0.30)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_normal: 1.5,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ─────────── Supabase REST 헬퍼 ─────────── */
async function supaRest(
    url: string, key: string, path: string,
    init: RequestInit & { prefer?: string } = {}
) {
    const base = url.replace(/\/+$/, "")
    const headers: Record<string, string> = {
        apikey: key,
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
    }
    if (init.prefer) headers["Prefer"] = init.prefer
    return fetch(`${base}/rest/v1/${path}`, { ...init, headers })
}


/* ─────────── 세션 ID ─────────── */
function getSessionId(): string {
    const KEY = "verity_visitor_id"
    try {
        let id = localStorage.getItem(KEY)
        if (!id) {
            id = typeof crypto !== "undefined" && crypto.randomUUID
                ? crypto.randomUUID()
                : Math.random().toString(36).slice(2) + Date.now().toString(36)
            localStorage.setItem(KEY, id)
        }
        return id
    } catch {
        return Math.random().toString(36).slice(2) + Date.now().toString(36)
    }
}


/* ─────────── 지오 lookup (Vercel Edge → ipapi fallback) ─────────── */
const VERCEL_GEO_BASE = "https://project-yw131.vercel.app"

async function _tryVercelGeo(): Promise<{ cc: string; label: string } | null> {
    try {
        const r = await fetch(`${VERCEL_GEO_BASE}/api/visitor_ping`, { method: "GET", cache: "no-store" })
        if (!r.ok) return null
        const j = await r.json()
        if (j?.country_code && j?.place_label) {
            return {
                cc: String(j.country_code).toUpperCase().slice(0, 2),
                label: String(j.place_label).slice(0, 100),
            }
        }
    } catch {}
    return null
}

async function _tryIpapiFallback(): Promise<{ cc: string; label: string } | null> {
    try {
        const r = await fetch("https://ipapi.co/json/", { cache: "no-store" })
        if (!r.ok) return null
        const j = await r.json()
        const cc = String(j?.country_code || "").toUpperCase().slice(0, 2)
        if (!cc) return null
        const city = j?.city ? String(j.city) : ""
        const label = city ? `${city}, ${cc}` : cc
        return { cc, label: label.slice(0, 100) }
    } catch {}
    return null
}

async function startGeoLookup(
    countryCodeRef: MutableRefObject<string | null>,
    placeLabelRef: MutableRefObject<string | null>,
    geoRequestedRef: MutableRefObject<boolean>
) {
    if (geoRequestedRef.current) return
    geoRequestedRef.current = true
    const a = await _tryVercelGeo()
    if (a) {
        countryCodeRef.current = a.cc
        placeLabelRef.current = a.label
        return
    }
    const b = await _tryIpapiFallback()
    if (b) {
        countryCodeRef.current = b.cc
        placeLabelRef.current = b.label
    }
}


/* ─────────── Props ─────────── */
interface Props {
    supabaseUrl: string
    supabaseKey: string
    heartbeatSec: number
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

export default function LiveVisitorPill(props: Props) {
    const { supabaseUrl, supabaseKey, heartbeatSec } = props

    const [active, setActive] = useState<number | null>(null)
    const [lastUpdate, setLastUpdate] = useState<number | null>(null)
    const [connected, setConnected] = useState(false)
    const [pulse, setPulse] = useState(false)
    const [showPanel, setShowPanel] = useState(false)
    const prevActive = useRef(0)
    const sidRef = useRef(getSessionId())
    const countryCodeRef = useRef<string | null>(null)
    const placeLabelRef = useRef<string | null>(null)
    const geoRequestedRef = useRef(false)

    /* 카운트 변화 시 pulse */
    useEffect(() => {
        if (active !== null && active !== prevActive.current) {
            setPulse(true)
            const t = setTimeout(() => setPulse(false), 600)
            prevActive.current = active
            return () => clearTimeout(t)
        }
    }, [active])

    /* heartbeat + 활성 카운트 */
    useEffect(() => {
        const url = supabaseUrl?.trim()
        const key = supabaseKey?.trim()
        if (!url || !key) return

        const sid = sidRef.current
        let alive = true
        const thresholdMs = (heartbeatSec * 2 + 10) * 1000

        const tick = async () => {
            try {
                if (!geoRequestedRef.current) {
                    await startGeoLookup(countryCodeRef, placeLabelRef, geoRequestedRef)
                }

                const row: Record<string, string> = {
                    session_id: sid,
                    last_seen: new Date().toISOString(),
                }
                if (countryCodeRef.current) row.country_code = countryCodeRef.current
                if (placeLabelRef.current) row.place_label = placeLabelRef.current

                await supaRest(url, key, "live_visitors", {
                    method: "POST",
                    prefer: "resolution=merge-duplicates,return=minimal",
                    body: JSON.stringify(row),
                })

                const cutoff = new Date(Date.now() - thresholdMs).toISOString()
                const res = await supaRest(
                    url, key,
                    `live_visitors?select=session_id&last_seen=gte.${encodeURIComponent(cutoff)}`,
                    { prefer: "count=exact" }
                )
                const total = res.headers.get("content-range")?.split("/")[1]
                const count = total ? parseInt(total, 10) : 0
                if (!Number.isNaN(count) && alive) {
                    setActive(count)
                    setLastUpdate(Date.now())
                    setConnected(true)
                }
            } catch {
                if (alive) setConnected(false)
            }
        }

        tick()
        const id = window.setInterval(tick, heartbeatSec * 1000)
        return () => {
            alive = false
            window.clearInterval(id)
        }
    }, [supabaseUrl, supabaseKey, heartbeatSec])

    /* 마지막 갱신 경과 (초) — 1초마다 re-render */
    const [, setNow] = useState(0)
    useEffect(() => {
        const id = window.setInterval(() => setNow((n) => n + 1), 1000)
        return () => window.clearInterval(id)
    }, [])

    const ageSec = lastUpdate != null ? Math.floor((Date.now() - lastUpdate) / 1000) : null
    const isStale = ageSec != null && ageSec > heartbeatSec * 3

    const dotColor = !connected
        ? C.danger
        : isStale
        ? C.warn
        : C.success
    const dotGlow = !connected
        ? G.danger
        : isStale
        ? "none"
        : G.success

    /* ─────────── render ─────────── */
    /* 위치는 Framer 에서 직접 배치. 본 컴포넌트는 inline-block 으로만 렌더링. */
    return (
        <div
            style={{
                position: "relative",
                display: "inline-block",
                fontFamily: FONT,
            }}
            onMouseEnter={() => setShowPanel(true)}
            onMouseLeave={() => setShowPanel(false)}
        >
            {/* Pill */}
            <div
                onClick={() => setShowPanel((v) => !v)}
                style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: S.sm,
                    padding: `${S.xs}px ${S.md}px`,
                    background: C.bgCard,
                    border: `1px solid ${showPanel ? C.borderStrong : C.border}`,
                    borderRadius: R.pill,
                    cursor: "pointer",
                    transition: X.base,
                    boxShadow: "none",
                }}
            >
                <span
                    style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: dotColor,
                        boxShadow: dotGlow,
                        animation: connected && !isStale ? "vp-blink 2.4s ease-in-out infinite" : undefined,
                    }}
                />
                <span style={{ ...MONO, color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold }}>
                    {active ?? "—"}
                </span>
                <span
                    style={{
                        color: C.textTertiary,
                        fontSize: T.cap,
                        fontWeight: T.w_semi,
                        letterSpacing: "0.08em",
                    }}
                >
                    LIVE
                </span>
            </div>

            {/* Hover/click panel — 필수 보안 요소만 */}
            {showPanel && (
                <div
                    style={{
                        position: "absolute",
                        top: "calc(100% + 6px)",
                        right: 0,
                        width: 280,
                        padding: `${S.lg}px ${S.lg}px`,
                        background: C.bgElevated,
                        border: `1px solid ${C.borderStrong}`,
                        borderRadius: R.md,
                        boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                        display: "flex",
                        flexDirection: "column",
                        gap: S.md,
                    }}
                >
                    {/* Header */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                        <span
                            style={{
                                color: C.textTertiary,
                                fontSize: T.cap,
                                fontWeight: T.w_med,
                                letterSpacing: "0.08em",
                                textTransform: "uppercase",
                            }}
                        >
                            접속 보안
                        </span>
                        <span
                            style={{
                                ...MONO,
                                color: connected ? C.success : C.danger,
                                fontSize: T.cap,
                                fontWeight: T.w_semi,
                            }}
                        >
                            {connected ? "● 활성" : "○ 끊김"}
                        </span>
                    </div>

                    {/* Row: 현재 접속 */}
                    <SecurityRow
                        label="현재 접속"
                        value={active != null ? `${active}명` : "—"}
                        valueColor={C.textPrimary}
                    />

                    {/* Row: 의심 활동 (현 단계 placeholder — admin 깊이 구현 시 데이터 연결) */}
                    <SecurityRow
                        label="의심 활동"
                        value="✓ 없음"
                        valueColor={C.success}
                    />

                    {/* Row: 단속 신선도 */}
                    <SecurityRow
                        label="마지막 점검"
                        value={
                            ageSec == null
                                ? "—"
                                : ageSec < 60
                                ? `${ageSec}초 전`
                                : ageSec < 3600
                                ? `${Math.floor(ageSec / 60)}분 전`
                                : `${Math.floor(ageSec / 3600)}시간 전`
                        }
                        valueColor={isStale ? C.warn : C.textSecondary}
                    />

                    {/* Footer note */}
                    <div
                        style={{
                            paddingTop: S.sm,
                            borderTop: `1px solid ${C.border}`,
                            fontSize: T.cap,
                            color: C.textTertiary,
                            lineHeight: 1.5,
                        }}
                    >
                        회원 정원 단속 · 이상 패턴 자동 차단
                    </div>
                </div>
            )}

            <style>{`
                @keyframes vp-blink {
                    0%, 100% { opacity: 1 }
                    50% { opacity: 0.45 }
                }
            `}</style>
        </div>
    )
}


/* ─────────── 서브 컴포넌트 ─────────── */

function SecurityRow({
    label,
    value,
    valueColor,
}: {
    label: string
    value: string
    valueColor: string
}) {
    return (
        <div
            style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
            }}
        >
            <span style={{ color: C.textSecondary, fontSize: T.body }}>{label}</span>
            <span
                style={{
                    ...MONO,
                    color: valueColor,
                    fontSize: T.body,
                    fontWeight: T.w_semi,
                }}
            >
                {value}
            </span>
        </div>
    )
}


/* ─────────── Framer Property Controls ─────────── */

LiveVisitorPill.defaultProps = {
    supabaseUrl: "",
    supabaseKey: "",
    heartbeatSec: 30,
}

addPropertyControls(LiveVisitorPill, {
    supabaseUrl: {
        type: ControlType.String,
        title: "Supabase URL",
        defaultValue: "",
        description: "Settings → API → Project URL",
    },
    supabaseKey: {
        type: ControlType.String,
        title: "Anon Key",
        defaultValue: "",
        description: "Settings → API → anon public",
    },
    heartbeatSec: {
        type: ControlType.Number,
        title: "Heartbeat (초)",
        defaultValue: 30,
        min: 10,
        max: 120,
        step: 5,
    },
})

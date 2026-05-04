/**
 * ⚠️ DEPRECATED (2026-05-05 Plan v0.1 §3 [Top bar] 폐기 결정)
 *
 * LiveVisitorPill (footer 강등 split) 으로 대체. 1015줄 풀 컴포넌트 → 작은 pill
 *
 * Framer 페이지에서 인스턴스 제거. 추후 일괄 cleanup commit 시 git rm.
 *
 * ────────────────────────────────────────────────────────────
 */
import {
    useCallback,
    useEffect,
    useLayoutEffect,
    useState,
    useRef,
    type MutableRefObject,
    type ReactNode,
    type CSSProperties,
} from "react"
import { createPortal } from "react-dom"
import { addPropertyControls, ControlType } from "framer"

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    accentStrong: "0 0 12px rgba(181,255,25,0.50)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/*
 * ── Supabase 초기 설정 (1회) ──
 *
 * 1) https://supabase.com 에서 무료 프로젝트 생성
 * 2) SQL Editor 에서 아래 실행:
 *
 *    create table live_visitors (
 *      session_id text primary key,
 *      last_seen  timestamptz not null default now(),
 *      country_code text,
 *      place_label text
 *    );
 *
 *    -- 이미 만든 테이블이면:
 *    alter table live_visitors add column if not exists country_code text;
 *    alter table live_visitors add column if not exists place_label text;
 *
 *    alter table live_visitors enable row level security;
 *    create policy "anon_rw" on live_visitors
 *      for all using (true) with check (true);
 *
 * 3) Settings → API 에서 Project URL / anon public key 복사
 * 4) Framer 속성 패널에 붙여넣기
 */

interface Props {
    supabaseUrl: string
    supabaseKey: string
    mode: "badge" | "bar" | "minimal"
    showTodayTotal: boolean
    heartbeatSec: number
    /** 뱃지/바: 클릭 시 접속 중 세션의 지역 분포(국가·시·도, Vercel Edge Geo 헤더 기반) */
    showRegionBreakdown: boolean
}

function getSessionId(): string {
    const KEY = "verity_visitor_id"
    try {
        let id = localStorage.getItem(KEY)
        if (!id) {
            id =
                typeof crypto !== "undefined" && crypto.randomUUID
                    ? crypto.randomUUID()
                    : Math.random().toString(36).slice(2) + Date.now().toString(36)
            localStorage.setItem(KEY, id)
        }
        return id
    } catch {
        return Math.random().toString(36).slice(2) + Date.now().toString(36)
    }
}

async function supaRest(
    url: string,
    key: string,
    path: string,
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

/* ── Visitor geolocation: Vercel Edge Geo (주) + ipapi.co (fallback) ── */
const API_BASE = "https://project-yw131.vercel.app"

// 해외 fallback (ipapi.co 직접) 에서 KR 간이 매핑 — 서버 매핑이 주, 클라는 backup
const _KR_REGION_MINI: Record<string, string> = {
    "gyeonggi-do": "경기", "gyeonggi": "경기",
    "gangwon-do": "강원", "gangwon": "강원", "gangwon-state": "강원",
    "chungcheongbuk-do": "충북", "chungcheongnam-do": "충남",
    "jeollabuk-do": "전북", "jeollanam-do": "전남",
    "gyeongsangbuk-do": "경북", "gyeongsangnam-do": "경남",
    "jeju-do": "제주", "jeju": "제주",
    "seoul": "서울", "busan": "부산", "incheon": "인천", "daegu": "대구",
    "daejeon": "대전", "gwangju": "광주", "ulsan": "울산", "sejong": "세종",
}

async function _tryVercelGeo(): Promise<{ cc: string; label: string } | null> {
    try {
        const r = await fetch(`${API_BASE}/api/visitor_ping`, { method: "GET", cache: "no-store" })
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
        if (cc === "KR") {
            const regionKey = String(j?.region || "").toLowerCase().replace(/\s+/g, "-")
            const regionKo = _KR_REGION_MINI[regionKey] || j?.region || ""
            const cityKey = String(j?.city || "").toLowerCase().replace(/\s+/g, "-").replace(/-si$/, "")
            const cityKo = _KR_REGION_MINI[cityKey] || j?.city || ""
            const parts = [regionKo, cityKo].filter(Boolean)
            const label = parts.length > 0 ? parts.join(" ") : "한국"
            return { cc, label: label.slice(0, 100) }
        }
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
): Promise<void> {
    if (geoRequestedRef.current) return
    geoRequestedRef.current = true
    // 1차: Vercel API (서버측 Vercel geo + ipapi 서버 fallback 포함)
    const a = await _tryVercelGeo()
    if (a) {
        countryCodeRef.current = a.cc
        placeLabelRef.current = a.label
        return
    }
    // 2차: 클라이언트 직접 ipapi.co (Vercel API 미배포/실패 대비)
    const b = await _tryIpapiFallback()
    if (b) {
        countryCodeRef.current = b.cc
        placeLabelRef.current = b.label
    }
}


export default function LiveVisitors(props: Props) {
    const { supabaseUrl, supabaseKey, mode, showTodayTotal, heartbeatSec, showRegionBreakdown } = props

    const [active, setActive] = useState<number | null>(null)
    const [todayTotal, setTodayTotal] = useState(0)
    const [connected, setConnected] = useState(false)
    const [error, setError] = useState("")
    const [pulse, setPulse] = useState(false)
    const [regionOpen, setRegionOpen] = useState(false)
    const [regionCounts, setRegionCounts] = useState<Record<string, number>>({})
    const [regionLoading, setRegionLoading] = useState(false)
    const prevActive = useRef(0)
    const sidRef = useRef(getSessionId())
    const countryCodeRef = useRef<string | null>(null)
    const placeLabelRef = useRef<string | null>(null)
    const geoRequestedRef = useRef(false)
    const regionTriggerRef = useRef<HTMLDivElement>(null)
    const [regionPopoverLayout, setRegionPopoverLayout] = useState<null | {
        left: number
        width: number
        top?: number
        bottom?: number
        maxHeight: number
    }>(null)

    useEffect(() => {
        if (active !== null && active !== prevActive.current) {
            setPulse(true)
            const t = setTimeout(() => setPulse(false), 600)
            prevActive.current = active
            return () => clearTimeout(t)
        }
    }, [active])

    useEffect(() => {
        const url = supabaseUrl?.trim()
        const key = supabaseKey?.trim()
        if (!url || !key) {
            setError("Supabase URL / Key를 설정하세요")
            return
        }
        setError("")

        const sid = sidRef.current
        let alive = true
        const thresholdMs = (heartbeatSec * 2 + 10) * 1000

        const heartbeat = async () => {
            try {
                // 첫 heartbeat: geo 완료까지 await (place_label null 로 저장되는 문제 해소)
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
                    url,
                    key,
                    `live_visitors?select=session_id&last_seen=gte.${cutoff}`,
                    { method: "GET", prefer: "count=exact" }
                )

                if (!alive) return

                const range = res.headers.get("content-range")
                if (range) {
                    const total = parseInt(range.split("/").pop() || "0", 10)
                    if (!isNaN(total)) setActive(total)
                } else {
                    const rows = await res.json()
                    if (Array.isArray(rows)) setActive(rows.length)
                }

                if (showTodayTotal) {
                    const todayStart = new Date()
                    todayStart.setHours(0, 0, 0, 0)
                    const todayRes = await supaRest(
                        url,
                        key,
                        `live_visitors?select=session_id&last_seen=gte.${todayStart.toISOString()}`,
                        { method: "GET", prefer: "count=exact" }
                    )
                    const todayRange = todayRes.headers.get("content-range")
                    if (todayRange) {
                        const t = parseInt(todayRange.split("/").pop() || "0", 10)
                        if (!isNaN(t)) setTodayTotal(t)
                    } else {
                        const rows = await todayRes.json()
                        if (Array.isArray(rows)) setTodayTotal(rows.length)
                    }
                }

                setConnected(true)
                setError("")
            } catch (e: any) {
                if (!alive) return
                setConnected(false)
                setError("연결 실패")
            }
        }

        heartbeat()
        const iv = setInterval(heartbeat, heartbeatSec * 1000)

        const onVisChange = () => {
            if (document.visibilityState === "visible") heartbeat()
        }
        document.addEventListener("visibilitychange", onVisChange)

        return () => {
            alive = false
            clearInterval(iv)
            document.removeEventListener("visibilitychange", onVisChange)
        }
    }, [supabaseUrl, supabaseKey, heartbeatSec, showTodayTotal])

    useEffect(() => {
        if (!regionOpen) return
        const url = supabaseUrl?.trim()
        const key = supabaseKey?.trim()
        if (!url || !key) return

        let alive = true
        const thresholdMs = (heartbeatSec * 2 + 10) * 1000

        const load = async () => {
            setRegionLoading(true)
            try {
                const cutoff = new Date(Date.now() - thresholdMs).toISOString()
                const res = await supaRest(
                    url,
                    key,
                    `live_visitors?select=place_label,country_code&last_seen=gte.${cutoff}`,
                    { method: "GET" }
                )
                if (!alive) return
                const rows = await res.json()
                if (!Array.isArray(rows)) {
                    setRegionCounts({})
                    return
                }
                const next: Record<string, number> = {}
                for (const r of rows) {
                    let key =
                        r && typeof r.place_label === "string" && r.place_label.trim()
                            ? r.place_label.trim()
                            : ""
                    if (!key) {
                        const raw = r && typeof r.country_code === "string" ? r.country_code.trim() : ""
                        key = raw.length >= 2 ? raw.toUpperCase().slice(0, 2) : "—"
                    }
                    next[key] = (next[key] || 0) + 1
                }
                setRegionCounts(next)
            } catch {
                if (alive) setRegionCounts({})
            } finally {
                if (alive) setRegionLoading(false)
            }
        }

        load()
        const iv = setInterval(load, heartbeatSec * 1000)
        return () => {
            alive = false
            clearInterval(iv)
        }
    }, [regionOpen, supabaseUrl, supabaseKey, heartbeatSec])

    const updateRegionPopoverLayout = useCallback(() => {
        const canExpand = showRegionBreakdown && mode !== "minimal"
        if (!regionOpen || !canExpand) {
            setRegionPopoverLayout(null)
            return
        }
        const el = regionTriggerRef.current
        if (!el || typeof window === "undefined") {
            setRegionPopoverLayout(null)
            return
        }
        const r = el.getBoundingClientRect()
        const gap = 8
        const pad = 10
        const maxPanel = 400
        const minComfort = 72
        const w =
            mode === "bar"
                ? Math.max(r.width, 200)
                : Math.max(220, r.width)
        let left = r.left
        if (left + w > window.innerWidth - pad) left = window.innerWidth - pad - w
        if (left < pad) left = pad

        const belowTop = r.bottom + gap
        const availBelow = window.innerHeight - belowTop - pad
        const availAbove = r.top - gap - pad

        if (availBelow >= minComfort || availBelow >= availAbove) {
            setRegionPopoverLayout({
                left,
                width: w,
                top: belowTop,
                maxHeight: Math.min(maxPanel, Math.max(80, availBelow)),
            })
        } else {
            setRegionPopoverLayout({
                left,
                width: w,
                bottom: window.innerHeight - r.top + gap,
                maxHeight: Math.min(maxPanel, Math.max(80, availAbove)),
            })
        }
    }, [regionOpen, mode, showRegionBreakdown])

    useLayoutEffect(() => {
        updateRegionPopoverLayout()
    }, [updateRegionPopoverLayout, regionCounts, regionLoading])

    useEffect(() => {
        if (!regionOpen) {
            setRegionPopoverLayout(null)
            return
        }
        updateRegionPopoverLayout()
        const onWin = () => updateRegionPopoverLayout()
        window.addEventListener("resize", onWin)
        window.addEventListener("scroll", onWin, true)
        return () => {
            window.removeEventListener("resize", onWin)
            window.removeEventListener("scroll", onWin, true)
        }
    }, [regionOpen, updateRegionPopoverLayout])

    if (error) return <ErrorView message={error} />
    if (active === null) return <LoadingView mode={mode} />

    const expandable = showRegionBreakdown && mode !== "minimal"
    const wrapMain = (node: ReactNode) => {
        if (!expandable) return node
        /* 지역 패널은 document.body 포털 + fixed 로 그려 overflow:hidden 조상에 잘리지 않음 */
        return (
            <div
                ref={regionTriggerRef}
                style={{
                    position: "relative",
                    display: mode === "bar" ? "flex" : "inline-flex",
                    flexDirection: "column",
                    alignItems: mode === "bar" ? "stretch" : "flex-start",
                    alignSelf: "flex-start",
                    width: mode === "bar" ? "100%" : "fit-content",
                    maxWidth: mode === "bar" ? undefined : "100%",
                    boxSizing: "border-box",
                    direction: "ltr",
                    textAlign: "left",
                    overflow: "visible",
                }}
            >
                {node}
            </div>
        )
    }

    const regionPopoverPortal =
        expandable &&
        regionOpen &&
        regionPopoverLayout &&
        typeof document !== "undefined"
            ? createPortal(
                  <div
                      style={{
                          position: "fixed",
                          left: regionPopoverLayout.left,
                          width: regionPopoverLayout.width,
                          maxHeight: regionPopoverLayout.maxHeight,
                          zIndex: 10000,
                          overflowY: "auto",
                          overflowX: "hidden",
                          boxSizing: "border-box",
                          ...(regionPopoverLayout.top !== undefined
                              ? { top: regionPopoverLayout.top }
                              : {}),
                          ...(regionPopoverLayout.bottom !== undefined
                              ? { bottom: regionPopoverLayout.bottom }
                              : {}),
                      }}
                  >
                      <RegionBreakdownPanel
                          counts={regionCounts}
                          loading={regionLoading}
                          wide={mode === "bar"}
                      />
                  </div>,
                  document.body
              )
            : null

    if (mode === "minimal")
        return <MinimalView active={active} pulse={pulse} connected={connected} />
    if (mode === "bar")
        return (
            <>
                {wrapMain(
                    <BarView
                        active={active}
                        todayTotal={todayTotal}
                        showTodayTotal={showTodayTotal}
                        pulse={pulse}
                        connected={connected}
                        expandable={expandable}
                        regionOpen={regionOpen}
                        onToggleRegion={() => setRegionOpen((v) => !v)}
                    />
                )}
                {regionPopoverPortal}
            </>
        )
    return (
        <>
            {wrapMain(
                <BadgeView
                    active={active}
                    pulse={pulse}
                    connected={connected}
                    expandable={expandable}
                    regionOpen={regionOpen}
                    onToggleRegion={() => setRegionOpen((v) => !v)}
                />
            )}
            {regionPopoverPortal}
        </>
    )
}

/* ── UI Sub-components ── */

function RegionBreakdownPanel({
    counts,
    loading,
    wide,
}: {
    counts: Record<string, number>
    loading: boolean
    wide: boolean
}) {
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1])
    let regionNames: Intl.DisplayNames | null = null
    try {
        regionNames = new Intl.DisplayNames(["ko"], { type: "region" })
    } catch {
        regionNames = null
    }
    const label = (key: string) => {
        if (key === "—") return "미확인"
        if (/^[A-Z]{2}$/.test(key) && regionNames) {
            try {
                const n = regionNames.of(key)
                if (n) return `${n} (${key})`
            } catch {
                /* ignore */
            }
        }
        return key
    }

    return (
        <div
            style={{
                ...STYLES.regionPanel,
                width: wide ? "100%" : undefined,
                minWidth: wide ? 0 : 220,
                maxWidth: wide ? "100%" : 400,
                boxSizing: "border-box",
            }}
        >
            <div style={STYLES.regionTitle}>접속 중 · 시·도 분포</div>
            {loading && sorted.length === 0 ? (
                <span style={STYLES.regionMuted}>불러오는 중…</span>
            ) : sorted.length === 0 ? (
                <span style={STYLES.regionMuted}>데이터 없음</span>
            ) : (
                <ul style={STYLES.regionList}>
                    {sorted.map(([code, n]) => (
                        <li key={code} style={STYLES.regionRow}>
                            <span style={STYLES.regionName}>{label(code)}</span>
                            <span style={STYLES.regionNum}>{n}</span>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    )
}

function LiveDot({ pulse, connected }: { pulse: boolean; connected: boolean }) {
    return (
        <span style={{ position: "relative", display: "inline-flex", alignItems: "center", justifyContent: "center", width: 10, height: 10, flexShrink: 0 }}>
            {connected && (
                <span
                    style={{
                        position: "absolute",
                        width: pulse ? 18 : 10,
                        height: pulse ? 18 : 10,
                        borderRadius: "50%",
                        background: "rgba(181,255,25,0.25)",
                        transition: "all 0.6s ease-out",
                        opacity: pulse ? 0 : 0.4,
                    }}
                />
            )}
            <span
                style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: connected ? "#B5FF19" : "#555",
                    boxShadow: connected ? "0 0 6px rgba(181,255,25,0.5)" : "none",
                    transition: "background 0.3s",
                }}
            />
        </span>
    )
}

function AnimatedNumber({ value }: { value: number }) {
    const [display, setDisplay] = useState(value)
    const raf = useRef<number>()

    useEffect(() => {
        const from = display
        const to = value
        if (from === to) return
        const start = performance.now()
        const dur = 400
        const tick = (now: number) => {
            const t = Math.min((now - start) / dur, 1)
            const ease = 1 - Math.pow(1 - t, 3)
            setDisplay(Math.round(from + (to - from) * ease))
            if (t < 1) raf.current = requestAnimationFrame(tick)
        }
        raf.current = requestAnimationFrame(tick)
        return () => { if (raf.current) cancelAnimationFrame(raf.current) }
    }, [value])

    return <>{display.toLocaleString()}</>
}

function ErrorView({ message }: { message: string }) {
    return (
        <div style={{ ...STYLES.badgeWrap, borderColor: "#331" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#555", flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: C.textTertiary, fontFamily: FONT }}>{message}</span>
        </div>
    )
}

function LoadingView({ mode }: { mode: string }) {
    return (
        <div style={mode === "bar" ? STYLES.barWrap : STYLES.badgeWrap}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#333", flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: C.textTertiary, fontFamily: FONT }}>연결 중…</span>
        </div>
    )
}

function MinimalView({ active, pulse, connected }: { active: number; pulse: boolean; connected: boolean }) {
    return (
        <div style={STYLES.minimalWrap}>
            <LiveDot pulse={pulse} connected={connected} />
            <span style={STYLES.minimalNum}><AnimatedNumber value={active} /></span>
        </div>
    )
}

function BadgeView({
    active,
    pulse,
    connected,
    expandable,
    regionOpen,
    onToggleRegion,
}: {
    active: number
    pulse: boolean
    connected: boolean
    expandable?: boolean
    regionOpen?: boolean
    onToggleRegion?: () => void
}) {
    const [hovered, setHovered] = useState(false)
    return (
        <div
            role={expandable ? "button" : undefined}
            tabIndex={expandable ? 0 : undefined}
            aria-expanded={expandable ? regionOpen : undefined}
            aria-label={expandable ? "접속 현황, 클릭하면 지역 분포" : undefined}
            onKeyDown={
                expandable && onToggleRegion
                    ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault()
                              onToggleRegion()
                          }
                      }
                    : undefined
            }
            onClick={expandable && onToggleRegion ? () => onToggleRegion() : undefined}
            style={{
                ...STYLES.badgeWrap,
                borderColor: hovered ? "#333" : "#222",
                background: hovered ? "#151515" : "#111",
                cursor: expandable ? "pointer" : "default",
            }}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
        >
            <LiveDot pulse={pulse} connected={connected} />
            <span style={STYLES.badgeNum}><AnimatedNumber value={active} /></span>
            <span style={STYLES.badgeLabel}>online</span>
            {expandable && (
                <span style={STYLES.expandHint} aria-hidden>
                    {regionOpen ? "▲" : "▼"}
                </span>
            )}
        </div>
    )
}

interface BarProps {
    active: number
    todayTotal: number
    showTodayTotal: boolean
    pulse: boolean
    connected: boolean
    expandable?: boolean
    regionOpen?: boolean
    onToggleRegion?: () => void
}

function BarView({
    active,
    todayTotal,
    showTodayTotal,
    pulse,
    connected,
    expandable,
    regionOpen,
    onToggleRegion,
}: BarProps) {
    const [hovered, setHovered] = useState(false)
    return (
        <div
            role={expandable ? "button" : undefined}
            tabIndex={expandable ? 0 : undefined}
            aria-expanded={expandable ? regionOpen : undefined}
            aria-label={expandable ? "접속 현황, 클릭하면 지역 분포" : undefined}
            onKeyDown={
                expandable && onToggleRegion
                    ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault()
                              onToggleRegion()
                          }
                      }
                    : undefined
            }
            onClick={expandable && onToggleRegion ? () => onToggleRegion() : undefined}
            style={{
                ...STYLES.barWrap,
                borderColor: hovered && expandable ? "#333" : "#222",
                background: hovered && expandable ? "#151515" : "#111",
                cursor: expandable ? "pointer" : "default",
            }}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
        >
            <div style={STYLES.barLeft}>
                <LiveDot pulse={pulse} connected={connected} />
                <span style={STYLES.barActiveNum}><AnimatedNumber value={active} /></span>
                <span style={STYLES.barActiveLabel}>접속 중</span>
            </div>
            {showTodayTotal && (
                <>
                    <div style={STYLES.barDivider} />
                    <div style={STYLES.barRight}>
                        <div style={STYLES.barStat}>
                            <span style={STYLES.barStatLabel}>오늘 방문</span>
                            <span style={STYLES.barStatValue}><AnimatedNumber value={todayTotal} /></span>
                        </div>
                    </div>
                </>
            )}
            {expandable && (
                <span style={{ ...STYLES.expandHint, marginLeft: "auto" }} aria-hidden>
                    {regionOpen ? "▲" : "▼"}
                </span>
            )}
        </div>
    )
}

/* ── Framer Controls ── */

LiveVisitors.defaultProps = {
    supabaseUrl: "",
    supabaseKey: "",
    mode: "badge",
    showTodayTotal: true,
    heartbeatSec: 15,
    showRegionBreakdown: true,
}

addPropertyControls(LiveVisitors, {
    supabaseUrl: {
        type: ControlType.String,
        title: "Supabase URL",
        defaultValue: "",
        description: "https://xxxx.supabase.co",
    },
    supabaseKey: {
        type: ControlType.String,
        title: "Supabase Key",
        defaultValue: "",
        description: "anon public key",
    },
    mode: {
        type: ControlType.Enum,
        title: "표시 모드",
        options: ["badge", "bar", "minimal"],
        optionTitles: ["뱃지", "바", "미니멀"],
        defaultValue: "badge",
    },
    showTodayTotal: {
        type: ControlType.Boolean,
        title: "오늘 방문수",
        defaultValue: true,
        hidden: (p) => p.mode !== "bar",
    },
    heartbeatSec: {
        type: ControlType.Number,
        title: "갱신 주기(초)",
        defaultValue: 15,
        min: 5,
        max: 60,
        step: 1,
    },
    showRegionBreakdown: {
        type: ControlType.Boolean,
        title: "지역 분포 패널",
        defaultValue: true,
        description: "뱃지/바 클릭 시 시·도·국가 분포(place_label)",
        hidden: (p) => p.mode === "minimal",
    },
})

/* ── Styles ── */

const STYLES: Record<string, CSSProperties> = {
    minimalWrap: {
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontFamily: FONT,
    },
    minimalNum: {
        fontSize: 13,
        fontWeight: 700,
        color: "#B5FF19",
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "-0.02em",
    },
    badgeWrap: {
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 14px 6px 10px",
        borderRadius: 20,
        background: C.bgElevated,
        border: `1px solid ${C.border}`,
        fontFamily: FONT,
        transition: "all 0.2s ease",
        cursor: "default",
        userSelect: "none",
    },
    badgeNum: {
        fontSize: 14,
        fontWeight: 700,
        color: C.textPrimary,
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "-0.02em",
    },
    badgeLabel: {
        fontSize: 12,
        fontWeight: 500,
        color: C.textTertiary,
        textTransform: "uppercase" as const,
        letterSpacing: "0.06em",
    },
    barWrap: {
        display: "flex",
        alignItems: "center",
        gap: 0,
        padding: "10px 20px",
        borderRadius: 14,
        background: C.bgElevated,
        border: `1px solid ${C.border}`,
        fontFamily: FONT,
        width: "100%",
        boxSizing: "border-box" as const,
    },
    barLeft: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        flexShrink: 0,
    },
    barActiveNum: {
        fontSize: 22,
        fontWeight: 800,
        color: C.textPrimary,
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "-0.03em",
        lineHeight: 1,
    },
    barActiveLabel: {
        fontSize: 12,
        fontWeight: 500,
        color: C.textTertiary,
        marginLeft: 2,
    },
    barDivider: {
        width: 1,
        height: 28,
        background: "#222",
        margin: "0 16px",
        flexShrink: 0,
    },
    barRight: {
        display: "flex",
        alignItems: "center",
        gap: 20,
    },
    barStat: {
        display: "flex",
        flexDirection: "column" as const,
        gap: 2,
    },
    barStatLabel: {
        fontSize: 12,
        fontWeight: 500,
        color: C.textTertiary,
        textTransform: "uppercase" as const,
        letterSpacing: "0.08em",
    },
    barStatValue: {
        fontSize: 15,
        fontWeight: 700,
        color: C.textSecondary,
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "-0.02em",
    },
    expandHint: {
        fontSize: 12,
        fontWeight: 600,
        color: C.textTertiary,
        marginLeft: 4,
        flexShrink: 0,
    },
    regionPanel: {
        padding: "12px 14px",
        borderRadius: 12,
        background: C.bgElevated,
        border: `1px solid ${C.border}`,
        fontFamily: FONT,
    },
    regionTitle: {
        fontSize: 12,
        fontWeight: 600,
        color: C.textTertiary,
        textTransform: "uppercase" as const,
        letterSpacing: "0.08em",
        marginBottom: 8,
    },
    regionMuted: {
        fontSize: 12,
        color: C.textTertiary,
    },
    regionList: {
        listStyle: "none",
        margin: 0,
        padding: 0,
        display: "flex",
        flexDirection: "column" as const,
        gap: 6,
    },
    regionRow: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        fontSize: 12,
    },
    regionName: {
        color: C.textPrimary,
        flex: 1,
        minWidth: 0,
    },
    regionNum: {
        color: "#B5FF19",
        fontWeight: 700,
        fontVariantNumeric: "tabular-nums",
        flexShrink: 0,
    },
}

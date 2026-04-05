import { useEffect, useState, useRef } from "react"
import { addPropertyControls, ControlType } from "framer"

/*
 * ── Supabase 초기 설정 (1회) ──
 *
 * 1) https://supabase.com 에서 무료 프로젝트 생성
 * 2) SQL Editor 에서 아래 실행:
 *
 *    create table live_visitors (
 *      session_id text primary key,
 *      last_seen  timestamptz not null default now()
 *    );
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

export default function LiveVisitors(props: Props) {
    const { supabaseUrl, supabaseKey, mode, showTodayTotal, heartbeatSec } = props

    const [active, setActive] = useState<number | null>(null)
    const [todayTotal, setTodayTotal] = useState(0)
    const [connected, setConnected] = useState(false)
    const [error, setError] = useState("")
    const [pulse, setPulse] = useState(false)
    const prevActive = useRef(0)
    const sidRef = useRef(getSessionId())

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
                await supaRest(url, key, "live_visitors", {
                    method: "POST",
                    prefer: "resolution=merge-duplicates,return=minimal",
                    body: JSON.stringify({
                        session_id: sid,
                        last_seen: new Date().toISOString(),
                    }),
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

    if (error) return <ErrorView message={error} />
    if (active === null) return <LoadingView mode={mode} />

    if (mode === "minimal")
        return <MinimalView active={active} pulse={pulse} connected={connected} />
    if (mode === "bar")
        return (
            <BarView
                active={active}
                todayTotal={todayTotal}
                showTodayTotal={showTodayTotal}
                pulse={pulse}
                connected={connected}
            />
        )
    return <BadgeView active={active} pulse={pulse} connected={connected} />
}

/* ── UI Sub-components ── */

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
        <div style={{ ...S.badgeWrap, borderColor: "#331" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#555", flexShrink: 0 }} />
            <span style={{ fontSize: 11, color: "#666", fontFamily: FONT }}>{message}</span>
        </div>
    )
}

function LoadingView({ mode }: { mode: string }) {
    return (
        <div style={mode === "bar" ? S.barWrap : S.badgeWrap}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#333", flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: "#444", fontFamily: FONT }}>연결 중…</span>
        </div>
    )
}

function MinimalView({ active, pulse, connected }: { active: number; pulse: boolean; connected: boolean }) {
    return (
        <div style={S.minimalWrap}>
            <LiveDot pulse={pulse} connected={connected} />
            <span style={S.minimalNum}><AnimatedNumber value={active} /></span>
        </div>
    )
}

function BadgeView({ active, pulse, connected }: { active: number; pulse: boolean; connected: boolean }) {
    const [hovered, setHovered] = useState(false)
    return (
        <div
            style={{
                ...S.badgeWrap,
                borderColor: hovered ? "#333" : "#222",
                background: hovered ? "#151515" : "#111",
            }}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
        >
            <LiveDot pulse={pulse} connected={connected} />
            <span style={S.badgeNum}><AnimatedNumber value={active} /></span>
            <span style={S.badgeLabel}>online</span>
        </div>
    )
}

interface BarProps {
    active: number
    todayTotal: number
    showTodayTotal: boolean
    pulse: boolean
    connected: boolean
}

function BarView({ active, todayTotal, showTodayTotal, pulse, connected }: BarProps) {
    return (
        <div style={S.barWrap}>
            <div style={S.barLeft}>
                <LiveDot pulse={pulse} connected={connected} />
                <span style={S.barActiveNum}><AnimatedNumber value={active} /></span>
                <span style={S.barActiveLabel}>접속 중</span>
            </div>
            {showTodayTotal && (
                <>
                    <div style={S.barDivider} />
                    <div style={S.barRight}>
                        <div style={S.barStat}>
                            <span style={S.barStatLabel}>오늘 방문</span>
                            <span style={S.barStatValue}><AnimatedNumber value={todayTotal} /></span>
                        </div>
                    </div>
                </>
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
})

/* ── Styles ── */

const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"

const S: Record<string, React.CSSProperties> = {
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
        background: "#111",
        border: "1px solid #222",
        fontFamily: FONT,
        transition: "all 0.2s ease",
        cursor: "default",
        userSelect: "none",
    },
    badgeNum: {
        fontSize: 14,
        fontWeight: 700,
        color: "#fff",
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "-0.02em",
    },
    badgeLabel: {
        fontSize: 11,
        fontWeight: 500,
        color: "#666",
        textTransform: "uppercase" as const,
        letterSpacing: "0.06em",
    },
    barWrap: {
        display: "flex",
        alignItems: "center",
        gap: 0,
        padding: "10px 20px",
        borderRadius: 14,
        background: "#111",
        border: "1px solid #222",
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
        color: "#fff",
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "-0.03em",
        lineHeight: 1,
    },
    barActiveLabel: {
        fontSize: 12,
        fontWeight: 500,
        color: "#666",
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
        fontSize: 10,
        fontWeight: 500,
        color: "#555",
        textTransform: "uppercase" as const,
        letterSpacing: "0.08em",
    },
    barStatValue: {
        fontSize: 15,
        fontWeight: 700,
        color: "#aaa",
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "-0.02em",
    },
}

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useRef, useCallback } from "react"

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


/**
 * VERITY Mobile — Toss-style 통합 모바일 앱
 * 5 tab: Home / Market / Reco / AI / More
 */

/* ─── Inline fetch ─── */
function _bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    return `${u}${u.includes("?") ? "&" : "?"}_=${Date.now()}`
}
function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(_bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

/* ─── Auth session ─── */
const SESSION_KEY = "verity_supabase_session"
interface AuthSession { access_token: string; refresh_token: string; expires_at: number; user: { id: string; email: string; user_metadata?: any } }
/** 만료 여부와 상관없이 저장된 세션을 반환. 자동 로그인용. */
function _loadSessionRaw(): AuthSession | null {
    if (typeof window === "undefined") return null
    try { const raw = localStorage.getItem(SESSION_KEY); if (!raw) return null; return JSON.parse(raw) } catch { return null }
}
/** 만료된 세션은 null 반환 (레거시 동기 로드용). */
function _loadSession(): AuthSession | null {
    const s = _loadSessionRaw()
    if (!s) return null
    if (s.expires_at && Date.now() / 1000 > s.expires_at) return null
    return s
}
function _saveSession(s: AuthSession) {
    if (typeof window !== "undefined") localStorage.setItem(SESSION_KEY, JSON.stringify(s))
}
function _clearSession() { if (typeof window !== "undefined") localStorage.removeItem(SESSION_KEY) }

/* ─── Supabase helpers (승인 기반) ─── */
async function _supaReq(url: string, anonKey: string, opts: RequestInit = {}): Promise<any> {
    const res = await fetch(url, {
        ...opts,
        headers: {
            "Content-Type": "application/json",
            apikey: anonKey,
            Authorization: `Bearer ${anonKey}`,
            ...((opts.headers as Record<string, string>) || {}),
        },
    })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(body.error_description || body.msg || body.message || `HTTP ${res.status}`)
    return body
}

async function _fetchProfileStatus(supabaseUrl: string, anonKey: string, accessToken: string, userId: string): Promise<"pending" | "approved" | "rejected" | "missing"> {
    try {
        const res = await fetch(`${supabaseUrl}/rest/v1/profiles?id=eq.${userId}&select=status`, {
            headers: { apikey: anonKey, Authorization: `Bearer ${accessToken}`, Accept: "application/json" },
        })
        if (!res.ok) return "missing"
        const rows = await res.json()
        if (!Array.isArray(rows) || rows.length === 0) return "missing"
        const st = rows[0]?.status
        if (st === "approved" || st === "pending" || st === "rejected") return st
        return "missing"
    } catch { return "missing" }
}

interface _SignUpExtras { phone: string; consent: boolean }

async function _ensureProfile(
    supabaseUrl: string, anonKey: string, accessToken: string,
    userId: string, email: string, displayName: string,
    extras?: _SignUpExtras
) {
    try {
        const payload: Record<string, any> = {
            id: userId, email,
            display_name: displayName || email.split("@")[0],
            status: "pending",
        }
        if (extras) {
            if (extras.phone) payload.phone = extras.phone
            if (extras.consent) payload.consent_given_at = new Date().toISOString()
        }
        await fetch(`${supabaseUrl}/rest/v1/profiles`, {
            method: "POST",
            headers: {
                apikey: anonKey, Authorization: `Bearer ${accessToken}`,
                "Content-Type": "application/json",
                Prefer: "resolution=ignore-duplicates,return=minimal",
            },
            body: JSON.stringify(payload),
        })
    } catch { /* no-op */ }
}

async function _mobileSignUp(
    supabaseUrl: string, anonKey: string, email: string, password: string,
    displayName: string, extras: _SignUpExtras
): Promise<"pending" | "email_confirm"> {
    const body = await _supaReq(`${supabaseUrl}/auth/v1/signup`, anonKey, {
        method: "POST",
        body: JSON.stringify({
            email, password,
            data: {
                name: displayName || email.split("@")[0],
                phone: extras.phone,
                consent: extras.consent,
            },
        }),
    })
    const userId: string | undefined = body.user?.id || body.id
    const accessToken: string | undefined = body.access_token
    if (!accessToken) return "email_confirm"
    if (userId) await _ensureProfile(supabaseUrl, anonKey, accessToken, userId, email, displayName, extras)
    _clearSession()
    return "pending"
}

/** 만료된 access_token을 refresh_token으로 갱신. 자동 로그인용. */
async function _refreshSession(supabaseUrl: string, anonKey: string, refreshToken: string): Promise<AuthSession | null> {
    try {
        const body = await _supaReq(`${supabaseUrl}/auth/v1/token?grant_type=refresh_token`, anonKey, {
            method: "POST",
            body: JSON.stringify({ refresh_token: refreshToken }),
        })
        const session: AuthSession = {
            access_token: body.access_token,
            refresh_token: body.refresh_token,
            expires_at: body.expires_at || (Date.now() / 1000 + 3600),
            user: body.user,
        }
        _saveSession(session)
        return session
    } catch { return null }
}

async function _mobileSignIn(supabaseUrl: string, anonKey: string, email: string, password: string): Promise<AuthSession> {
    const body = await _supaReq(`${supabaseUrl}/auth/v1/token?grant_type=password`, anonKey, {
        method: "POST",
        body: JSON.stringify({ email, password }),
    })
    const session: AuthSession = {
        access_token: body.access_token,
        refresh_token: body.refresh_token,
        expires_at: body.expires_at || (Date.now() / 1000 + 3600),
        user: body.user,
    }
    const status = await _fetchProfileStatus(supabaseUrl, anonKey, session.access_token, session.user.id)
    if (status === "approved") { _saveSession(session); return session }
    if (status === "missing") {
        await _ensureProfile(supabaseUrl, anonKey, session.access_token, session.user.id, email, session.user.user_metadata?.name || "")
        _clearSession()
        throw new Error("관리자 승인 대기 중입니다.")
    }
    _clearSession()
    if (status === "rejected") throw new Error("가입이 거절되었습니다.")
    throw new Error("관리자 승인 대기 중입니다.")
}

/* ─── Design tokens ─── */
const GRADE_COLOR: Record<string, string> = { STRONG_BUY: "#22C55E", BUY: "#B5FF19", WATCH: "#FFD600", CAUTION: "#F59E0B", AVOID: "#EF4444" }
const GRADE_LABEL: Record<string, string> = { STRONG_BUY: "강력매수", BUY: "매수", WATCH: "관망", CAUTION: "주의", AVOID: "회피" }

// §8 AVOID 라벨 의미 — 펀더멘털 결함 전용
const AVOID_TOOLTIP =
    "AVOID = 펀더멘털 결함 (감사거절·분식·상폐 위험 등 has_critical) 또는 매크로 위기 cap. 단순 저점수는 CAUTION."

// §11~§14 audit overrides
const OVERRIDE_LABELS: Record<string, string> = {
    contrarian_upgrade: "역발상↑", quadrant_unfavored: "분면불리↓",
    cape_bubble: "CAPE버블", panic_stage_3: "패닉3", panic_stage_4: "패닉4",
    vix_spread_panic: "VIX패닉", yield_defense: "수익률방어",
    sector_quadrant_drift: "섹터드리프트", ai_upside_relax: "AI호재완화",
}
const TONE_STYLE: Record<string, { color: string; label: string }> = {
    urgent: { color: "#EF4444", label: "긴급" }, cautious: { color: "#EAB308", label: "주의" },
    defensive: { color: "#F59E0B", label: "방어" }, positive: { color: "#22C55E", label: "양호" },
    neutral: { color: C.textSecondary, label: "중립" },
}
const LEVEL_COLOR: Record<string, string> = { CRITICAL: "#EF4444", WARNING: "#EAB308", INFO: "#60A5FA" }

type TabId = "home" | "market" | "reco" | "ai" | "more"
const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"
const CHAT_API = "https://vercel-api-alpha-umber.vercel.app/api/chat"

interface Props {
    dataUrl: string
    refreshIntervalSec: number
    defaultTab: TabId
    supabaseUrl: string
    supabaseAnonKey: string
    chatApiUrl: string
}

/* ══════════════════════════════════════════════════════════════════
   UTILITY
   ══════════════════════════════════════════════════════════════════ */
function fmtKRW(n: number | null | undefined): string {
    if (n == null) return "—"
    return n.toLocaleString("ko-KR") + "원"
}
function fmtNum(n: number | null | undefined, dec = 0): string {
    if (n == null) return "—"
    return n.toLocaleString(undefined, { maximumFractionDigits: dec })
}
function fmtCap(n: number | null | undefined, currency: "KRW" | "USD" = "KRW"): string {
    if (n == null || n === 0) return "—"
    if (currency === "USD") {
        if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`
        if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`
        if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`
        return `$${n.toLocaleString()}`
    }
    if (n >= 1e12) return `${(n / 1e12).toFixed(1)}조`
    if (n >= 1e8) return `${Math.round(n / 1e8).toLocaleString()}억`
    return n.toLocaleString("ko-KR")
}
function isUS(r: any): boolean {
    return r?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r?.market || "")
}
function timeAgo(iso: string): string {
    const diff = (Date.now() - new Date(iso).getTime()) / 60000
    if (diff < 1) return "방금"
    if (diff < 60) return `${Math.floor(diff)}분 전`
    if (diff < 1440) return `${Math.floor(diff / 60)}시간 전`
    return `${Math.floor(diff / 1440)}일 전`
}
function calcSparkChange(arr: number[] | undefined): number | null {
    if (!arr || arr.length < 2) return null
    const last = arr[arr.length - 1], prev = arr[arr.length - 2]
    if (!prev) return null
    return ((last - prev) / prev) * 100
}
function calcSparkChangeFromStart(arr: number[] | undefined): number | null {
    if (!arr || arr.length < 2) return null
    const last = arr[arr.length - 1], first = arr[0]
    if (!first) return null
    return ((last - first) / first) * 100
}

/* ══════════════════════════════════════════════════════════════════
   SHARED UI
   ══════════════════════════════════════════════════════════════════ */

function Sparkline({ data, width = 60, height = 24, color = "#888", fill = true }: { data: number[]; width?: number; height?: number; color?: string; fill?: boolean }) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data), max = Math.max(...data), range = max - min || 1
    const pts = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * (height - 4) - 2}`).join(" ")
    const gid = `mg-${color.replace("#", "")}-${width}${height}`
    return (
        <svg width={width} height={height} style={{ display: "block", flexShrink: 0 }}>
            {fill && (
                <>
                    <defs>
                        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={color} stopOpacity={0.22} />
                            <stop offset="100%" stopColor={color} stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <polygon points={`${pts} ${width},${height} 0,${height}`} fill={`url(#${gid})`} />
                </>
            )}
            <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
        </svg>
    )
}

/**
 * RingGauge — 숫자가 원 내부 중앙에 정확히 위치 (position: absolute)
 */
function RingGauge({ value, size = 48, color, label, strokeWidth }: { value: number; size?: number; color: string; label?: string; strokeWidth?: number }) {
    const sw = strokeWidth ?? Math.max(3, Math.round(size * 0.08))
    const r = (size - sw) / 2
    const circ = 2 * Math.PI * r
    const v = Math.min(Math.max(value, 0), 100)
    const offset = circ * (1 - v / 100)
    const numFontSize = Math.max(11, Math.round(size * 0.32))
    const totalH = size + (label ? 16 : 0)
    return (
        <div style={{ position: "relative", width: size, height: totalH, flexShrink: 0 }}>
            <svg width={size} height={size} style={{ display: "block" }}>
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={C.border} strokeWidth={sw} />
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={sw}
                    strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
                    transform={`rotate(-90 ${size / 2} ${size / 2})`}
                    style={{ transition: "stroke-dashoffset 0.6s ease" }} />
            </svg>
            <div style={{ position: "absolute", left: 0, top: 0, width: size, height: size, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
                <span style={{ color, fontSize: numFontSize, fontWeight: 800, fontFamily: FONT, lineHeight: 1, letterSpacing: "-0.02em" }}>{Math.round(value)}</span>
            </div>
            {label && (
                <div style={{ position: "absolute", left: 0, bottom: 0, width: size, textAlign: "center", color: C.textSecondary, fontSize: 12, fontWeight: 600, fontFamily: FONT, letterSpacing: "0.02em" }}>{label}</div>
            )}
        </div>
    )
}

function Card({ children, style, onClick }: { children: React.ReactNode; style?: React.CSSProperties; onClick?: () => void }) {
    return (
        <div onClick={onClick} style={{
            background: C.bgCard, borderRadius: 16, border: `1px solid ${C.border}`,
            padding: "16px 18px", cursor: onClick ? "pointer" : "default",
            transition: "transform 0.15s, border-color 0.15s",
            boxSizing: "border-box", minWidth: 0,
            ...style,
        }}>{children}</div>
    )
}

function CardTitle({ children, color, right }: { children: React.ReactNode; color?: string; right?: React.ReactNode }) {
    return (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <span style={{ color: color || C.accent, fontSize: 12, fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase" as const, fontFamily: FONT }}>{children}</span>
            {right}
        </div>
    )
}

function Pill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
    return (
        <button onClick={onClick} style={{
            border: "none", borderRadius: 20, padding: "6px 14px",
            fontSize: 12, fontWeight: 700, fontFamily: FONT, cursor: "pointer",
            background: active ? C.accent : "#1A1A1A", color: active ? "#000" : C.textSecondary,
            transition: "all 0.2s",
        }}>{label}</button>
    )
}

function PctText({ value, fontSize = 13, bold = true }: { value: number | null | undefined; fontSize?: number; bold?: boolean }) {
    if (value == null) return <span style={{ color: C.textSecondary, fontSize, fontFamily: FONT }}>—</span>
    const color = value >= 0 ? C.success : C.danger
    return <span style={{ color, fontSize, fontWeight: bold ? 700 : 500, fontFamily: FONT }}>{value >= 0 ? "+" : ""}{Number(value).toFixed(2)}%</span>
}

function Badge({ text, color }: { text: string; color: string }) {
    return (
        <span style={{ fontSize: 12, fontWeight: 700, padding: "2px 8px", borderRadius: 6, background: `${color}18`, color, fontFamily: FONT }}>{text}</span>
    )
}

function Stat({ label, value, accent }: { label: string; value: React.ReactNode; accent?: string }) {
    return (
        <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 600, marginBottom: 3, fontFamily: FONT, letterSpacing: "0.02em", textTransform: "uppercase" as const }}>{label}</div>
            <div style={{ color: accent || C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{value}</div>
        </div>
    )
}

function BottomSheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode }) {
    useEffect(() => {
        if (!open) return
        const prev = document.body.style.overflow
        document.body.style.overflow = "hidden"
        return () => { document.body.style.overflow = prev }
    }, [open])
    if (!open) return null
    return (
        <div style={{ position: "fixed", inset: 0, zIndex: 9999, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
            <div onClick={onClose} style={{ flex: 1, background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)", WebkitBackdropFilter: "blur(4px)" }} />
            <div style={{
                background: C.bgCard, borderTopLeftRadius: 20, borderTopRightRadius: 20,
                padding: "14px 20px 32px", maxHeight: "82vh", overflowY: "auto",
                borderTop: `1px solid ${C.border}`, animation: "slideUp 0.25s ease-out",
                WebkitOverflowScrolling: "touch",
            }}>
                <div style={{ width: 36, height: 4, borderRadius: 2, background: C.border, margin: "0 auto 14px" }} />
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                    <span style={{ color: C.textPrimary, fontSize: 17, fontWeight: 800, fontFamily: FONT, letterSpacing: "-0.01em" }}>{title}</span>
                    <button onClick={onClose} style={{ border: "none", background: "transparent", color: C.textSecondary, fontSize: 22, cursor: "pointer", padding: 4, lineHeight: 1 }}>✕</button>
                </div>
                {children}
            </div>
        </div>
    )
}

/* ─── ErrorBoundary (런타임 에러 시 빈 화면 방지) ─── */
interface EBProps { children: React.ReactNode; label: string }
interface EBState { error: Error | null }
class ErrorBoundary extends React.Component<EBProps, EBState> {
    declare props: EBProps
    declare state: EBState
    declare setState: React.Component<EBProps, EBState>["setState"]
    constructor(props: EBProps) {
        super(props)
        this.state = { error: null }
    }
    static getDerivedStateFromError(error: Error): EBState { return { error } }
    componentDidCatch(error: Error, info: any) {
        console.error(`[MobileApp:${this.props.label}]`, error, info)
    }
    render() {
        if (this.state.error) {
            const err = this.state.error
            return (
                <div style={{ padding: 20, background: "#1a0000", border: "1px solid #EF4444", borderRadius: 12, margin: "10px 0" }}>
                    <div style={{ color: "#EF4444", fontSize: 13, fontWeight: 800, fontFamily: FONT, marginBottom: 8 }}>
                        ⚠ {this.props.label} 렌더링 에러
                    </div>
                    <div style={{ color: C.textPrimary, fontSize: 12, fontFamily: "monospace", lineHeight: 1.5, wordBreak: "break-word" }}>
                        {err.message}
                    </div>
                    {err.stack && (
                        <pre style={{ color: C.textSecondary, fontSize: 12, fontFamily: "monospace", lineHeight: 1.4, marginTop: 8, maxHeight: 200, overflow: "auto", whiteSpace: "pre-wrap" }}>
                            {err.stack.split("\n").slice(0, 5).join("\n")}
                        </pre>
                    )}
                </div>
            )
        }
        return this.props.children as any
    }
}

/* ─── Tab Icons ─── */
function IconHome({ active }: { active: boolean }) { const c = active ? C.accent : C.textSecondary; return <svg width={22} height={22} viewBox="0 0 24 24" fill="none"><path d="M3 10.5L12 3l9 7.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V10.5z" stroke={c} strokeWidth={2} strokeLinejoin="round" fill={active ? `${c}20` : "none"}/><path d="M9 21V14h6v7" stroke={c} strokeWidth={2} strokeLinejoin="round"/></svg> }
function IconMarket({ active }: { active: boolean }) { const c = active ? C.accent : C.textSecondary; return <svg width={22} height={22} viewBox="0 0 24 24" fill="none"><path d="M3 20h18M6 16v-4m5 4V8m5 8v-6" stroke={c} strokeWidth={2} strokeLinecap="round"/></svg> }
function IconReco({ active }: { active: boolean }) { const c = active ? C.accent : C.textSecondary; return <svg width={22} height={22} viewBox="0 0 24 24" fill="none"><path d="M12 2l2.4 7.2H22l-6 4.8 2.4 7.2L12 16.4 5.6 21.2 8 14 2 9.2h7.6L12 2z" stroke={c} strokeWidth={2} strokeLinejoin="round" fill={active ? `${c}20` : "none"}/></svg> }
function IconAI({ active }: { active: boolean }) { const c = active ? C.accent : C.textSecondary; return <svg width={22} height={22} viewBox="0 0 24 24" fill="none"><circle cx={12} cy={12} r={9} stroke={c} strokeWidth={2}/><path d="M12 7v5l3 3" stroke={c} strokeWidth={2} strokeLinecap="round"/></svg> }
function IconMore({ active }: { active: boolean }) { const c = active ? C.accent : C.textSecondary; return <svg width={22} height={22} viewBox="0 0 24 24" fill="none"><circle cx={12} cy={5} r={1.5} fill={c}/><circle cx={12} cy={12} r={1.5} fill={c}/><circle cx={12} cy={19} r={1.5} fill={c}/></svg> }

const TAB_ICONS: Record<TabId, (active: boolean) => React.ReactNode> = {
    home: (a) => <IconHome active={a} />, market: (a) => <IconMarket active={a} />,
    reco: (a) => <IconReco active={a} />, ai: (a) => <IconAI active={a} />, more: (a) => <IconMore active={a} />,
}
const TAB_LABELS: Record<TabId, string> = { home: "홈", market: "시장", reco: "추천", ai: "VERITY", more: "더보기" }

/* ══════════════════════════════════════════════════════════════════
   HOME TAB
   ══════════════════════════════════════════════════════════════════ */
function HomeTab({ data, session }: { data: any; session: AuthSession | null }) {
    const vams = data?.vams || {}
    const briefing = data?.briefing || {}
    const macro = data?.macro || {}
    const mood = macro.market_mood || {}
    const holdings: any[] = vams.holdings || []
    const alerts: any[] = (briefing.alerts || []).filter((a: any) => a.level === "CRITICAL" || a.level === "WARNING")
    const totalAsset = vams.total_asset ?? 0
    const cash = vams.cash ?? 0
    const holdingsValue = totalAsset - cash
    const weightedReturn = holdings.length > 0
        ? holdings.reduce((s: number, h: any) => s + (h.return_pct ?? 0) * ((h.current_price ?? 0) * (h.quantity ?? 0)), 0) /
          (holdings.reduce((s: number, h: any) => s + ((h.current_price ?? 0) * (h.quantity ?? 0)), 0) || 1)
        : 0
    const pnl = holdings.reduce((s: number, h: any) => s + ((h.current_price ?? 0) - (h.buy_price ?? 0)) * (h.quantity ?? 0), 0)
    const pnlSign = pnl > 0 ? "+" : pnl < 0 ? "-" : ""
    const tone = TONE_STYLE[briefing.tone] || TONE_STYLE.neutral
    const winners = holdings.filter((h: any) => (h.return_pct ?? 0) > 0).length
    const losers = holdings.filter((h: any) => (h.return_pct ?? 0) < 0).length

    const morning = data?.claude_morning_strategy || {}
    const dailyReport = data?.daily_report || {}
    const hasMorning = !!(morning.scenario || morning.top_pick_comment)

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {/* 업데이트 시간만 간단히 */}
            <div style={{ padding: "0 2px", color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>
                {data?.updated_at ? `${timeAgo(data.updated_at)} · ${new Date(data.updated_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })} 업데이트` : "데이터 로딩 중"}
            </div>

            {/* Asset summary */}
            <Card>
                <CardTitle right={<Badge text={weightedReturn >= 0 ? "수익중" : "손실중"} color={weightedReturn >= 0 ? C.success : C.danger} />}>내 자산</CardTitle>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 14 }}>
                    <div style={{ minWidth: 0 }}>
                        <div style={{ color: C.textPrimary, fontSize: 28, fontWeight: 900, fontFamily: FONT, letterSpacing: "-0.03em" }}>{fmtKRW(totalAsset)}</div>
                        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
                            <PctText value={weightedReturn} fontSize={14} />
                            {pnl !== 0 && (
                                <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>
                                    {pnlSign}{fmtCap(Math.abs(pnl))}
                                </span>
                            )}
                        </div>
                    </div>
                    <RingGauge value={mood.score ?? 50} size={56} color={(mood.score ?? 50) >= 55 ? C.success : (mood.score ?? 50) >= 40 ? C.warn : C.danger} label="시장무드" />
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                    <div style={{ flex: 1, background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                        <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 600, marginBottom: 4, fontFamily: FONT, letterSpacing: "0.02em", textTransform: "uppercase" as const }}>투자금</div>
                        <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, fontFamily: FONT }}>{fmtKRW(holdingsValue)}</div>
                    </div>
                    <div style={{ flex: 1, background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                        <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 600, marginBottom: 4, fontFamily: FONT, letterSpacing: "0.02em", textTransform: "uppercase" as const }}>현금</div>
                        <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, fontFamily: FONT }}>{fmtKRW(cash)}</div>
                    </div>
                    <div style={{ flex: 1, background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                        <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 600, marginBottom: 4, fontFamily: FONT, letterSpacing: "0.02em", textTransform: "uppercase" as const }}>승/패</div>
                        <div style={{ fontSize: 13, fontWeight: 700, fontFamily: FONT }}>
                            <span style={{ color: C.success }}>{winners}</span>
                            <span style={{ color: C.textSecondary }}> / </span>
                            <span style={{ color: C.danger }}>{losers}</span>
                        </div>
                    </div>
                </div>
            </Card>

            {/* AI Briefing */}
            <Card style={{ borderColor: `${tone.color}30` }}>
                <CardTitle color={tone.color} right={<Badge text={tone.label} color={tone.color} />}>AI 브리핑</CardTitle>
                <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700, lineHeight: 1.5, fontFamily: FONT, marginBottom: 8 }}>
                    {briefing.headline || "브리핑 대기 중"}
                </div>
                {briefing.portfolio_status && (
                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.6 }}>{briefing.portfolio_status}</div>
                )}
                {briefing.action_items?.length > 0 && (
                    <div style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.border}` }}>
                        {briefing.action_items.slice(0, 2).map((a: string, i: number) => (
                            <div key={i} style={{ color: tone.color, fontSize: 12, fontFamily: FONT, lineHeight: 1.5, marginBottom: 2 }}>· {a}</div>
                        ))}
                    </div>
                )}
            </Card>

            {/* Claude 모닝 시나리오 */}
            {hasMorning && (
                <Card style={{ borderColor: `${"#A855F7"}30` }}>
                    <CardTitle color={"#A855F7"} right={<Badge text="Claude" color={"#A855F7"} />}>오늘의 시나리오</CardTitle>
                    {morning.scenario && (
                        <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 600, lineHeight: 1.6, fontFamily: FONT, marginBottom: 10 }}>
                            {morning.scenario}
                        </div>
                    )}
                    {morning.watch_points?.length > 0 && (
                        <div style={{ marginBottom: 10 }}>
                            <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 700, marginBottom: 5, fontFamily: FONT, letterSpacing: "0.04em", textTransform: "uppercase" as const }}>관찰 포인트</div>
                            {morning.watch_points.slice(0, 2).map((w: string, i: number) => (
                                <div key={i} style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5, marginBottom: 3 }}>· {w}</div>
                            ))}
                        </div>
                    )}
                    {morning.top_pick_comment && (
                        <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px", marginTop: 8 }}>
                            <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 4, fontFamily: FONT, letterSpacing: "0.04em", textTransform: "uppercase" as const }}>TOP PICK</div>
                            <div style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>{morning.top_pick_comment}</div>
                        </div>
                    )}
                    {morning.risk_note && (
                        <div style={{ color: C.warn, fontSize: 12, fontFamily: FONT, lineHeight: 1.5, marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.border}` }}>
                            ⚠ {morning.risk_note}
                        </div>
                    )}
                </Card>
            )}

            {/* 오늘/내일 요약 (daily_report 짧은 것만) */}
            {(dailyReport.hot_theme || dailyReport.tomorrow_outlook) && (
                <Card>
                    <CardTitle>오늘 · 내일</CardTitle>
                    {dailyReport.hot_theme && (
                        <div style={{ color: C.warn, fontSize: 12, fontFamily: FONT, lineHeight: 1.6, marginBottom: 8 }}>
                            🔥 {dailyReport.hot_theme}
                        </div>
                    )}
                    {dailyReport.tomorrow_outlook && (
                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                            <span style={{ color: C.info, fontWeight: 700, marginRight: 4 }}>내일</span>{dailyReport.tomorrow_outlook}
                        </div>
                    )}
                </Card>
            )}

            {/* Holdings */}
            {holdings.length > 0 && (
                <Card>
                    <CardTitle right={<span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{holdings.length}종목</span>}>보유 종목</CardTitle>
                    {holdings.slice(0, 4).map((h: any, i: number) => {
                        const r = h.return_pct ?? 0
                        const col = r >= 0 ? C.success : C.danger
                        const holdingValue = (h.current_price ?? 0) * (h.quantity ?? 0)
                        return (
                            <div key={h.ticker || i} style={{
                                display: "flex", alignItems: "center", gap: 10, padding: "11px 0",
                                borderBottom: i < Math.min(holdings.length, 4) - 1 ? `1px solid ${C.border}` : "none",
                            }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700, fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.name}</div>
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{h.quantity}주 · 평단 {fmtKRW(h.buy_price)}</div>
                                </div>
                                <div style={{ textAlign: "right", flexShrink: 0 }}>
                                    <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, fontFamily: FONT }}>{fmtKRW(holdingValue)}</div>
                                    <div style={{ fontSize: 12, fontWeight: 700, fontFamily: FONT, color: col }}>
                                        {r >= 0 ? "+" : ""}{r.toFixed(2)}%
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </Card>
            )}

            {/* Alerts */}
            {alerts.length > 0 && (
                <Card>
                    <CardTitle color={C.warn}>주요 알림</CardTitle>
                    {alerts.slice(0, 3).map((a: any, i: number) => {
                        const lc = LEVEL_COLOR[a.level] || C.textSecondary
                        return (
                            <div key={i} style={{
                                padding: "10px 12px", borderRadius: 10, marginBottom: i < 2 ? 8 : 0,
                                background: `${lc}10`, border: `1px solid ${lc}30`,
                            }}>
                                <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
                                    <Badge text={a.level} color={lc} />
                                    <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{a.category}</span>
                                </div>
                                <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.5, fontFamily: FONT }}>{a.message}</div>
                                {a.action && <div style={{ color: lc, fontSize: 12, marginTop: 4, fontFamily: FONT, fontWeight: 600 }}>→ {a.action}</div>}
                            </div>
                        )
                    })}
                </Card>
            )}
        </div>
    )
}

/* ══════════════════════════════════════════════════════════════════
   MARKET TAB
   ══════════════════════════════════════════════════════════════════ */
function MarketTab({ data }: { data: any }) {
    const [seg, setSeg] = useState<"kr" | "us">("kr")
    const ms = data?.market_summary || {}
    const macro = data?.macro || {}
    const sectors: any[] = data?.sectors || []
    const rotation = data?.sector_rotation || {}
    const events: any[] = data?.global_events || []
    const fundFlows = data?.fund_flows || {}
    const etfFlows = fundFlows?.etf_flows || {}
    const cftc = data?.cftc_cot?.summary || {}
    const pcr = data?.cboe_pcr || {}
    const fgCnn = data?.market_fear_greed || {}
    const usHeadlines: any[] = data?.us_headlines || []
    const capFlow = macro.capital_flow || {}
    const yieldSp = macro.yield_spread || {}
    const bondRegime = data?.bond_analysis?.bond_regime || {}
    const cryptoMacro = data?.crypto_macro || {}
    const kisMarket = data?.kis_market || {}
    const foreignInst: any[] = kisMarket.foreign_institution || []
    const fluctUp: any[] = kisMarket.fluctuation_up || []
    const fluctDown: any[] = kisMarket.fluctuation_down || []

    const indices = seg === "kr"
        ? [{ label: "KOSPI", ...(ms.kospi || {}) }, { label: "KOSDAQ", ...(ms.kosdaq || {}) }]
        : [{ label: "NASDAQ", ...(ms.ndx || {}) }, { label: "S&P 500", ...(ms.sp500 || {}) }]

    // 시장 심리 — 국가별로 다른 소스
    const mood = seg === "kr" ? (macro.market_mood || {}) : (macro.market_mood_us || {})
    const moodScore = mood.score ?? 50
    const moodColor = moodScore >= 65 ? C.success : moodScore >= 45 ? C.warn : C.danger

    // 매크로 진단 — 국가별로 다른 소스
    const diagnosis: any[] = seg === "kr" ? (macro.macro_diagnosis || []) : (macro.macro_diagnosis_us || [])

    // 매크로 칩 — 국가별 구성
    const krMacroChips = [
        { label: "USD/KRW", value: macro.usd_krw?.value, pct: macro.usd_krw?.change_pct, dec: 1 },
        { label: "한국 10Y", value: macro.ecos?.korea_gov_10y?.value, pct: null, dec: 2, suffix: "%" },
        { label: "정책금리", value: macro.ecos?.korea_policy_rate?.value, pct: null, dec: 2, suffix: "%" },
        { label: "Gold", value: macro.gold?.value, pct: macro.gold?.change_pct, dec: 1 },
        { label: "WTI유가", value: macro.wti_oil?.value ?? macro.oil?.value, pct: macro.wti_oil?.change_pct ?? macro.oil?.change_pct, dec: 1 },
        { label: "USD/JPY", value: macro.usd_jpy?.value, pct: macro.usd_jpy?.change_pct, dec: 2 },
    ]
    const usMacroChips = [
        { label: "VIX", value: macro.vix?.value, pct: macro.vix?.change_pct, dec: 2 },
        { label: "US 10Y", value: macro.us_10y?.value, pct: null, dec: 2, suffix: "%" },
        { label: "US 2Y", value: macro.us_2y?.value, pct: null, dec: 2, suffix: "%" },
        { label: "Gold", value: macro.gold?.value, pct: macro.gold?.change_pct, dec: 1 },
        { label: "WTI유가", value: macro.wti_oil?.value ?? macro.oil?.value, pct: macro.wti_oil?.change_pct ?? macro.oil?.change_pct, dec: 1 },
        { label: "DXY/JPY", value: macro.usd_jpy?.value, pct: macro.usd_jpy?.change_pct, dec: 2 },
    ]
    const chips = (seg === "kr" ? krMacroChips : usMacroChips).filter((m) => m.value != null)

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", gap: 8, padding: "0 2px" }}>
                <Pill label="국내" active={seg === "kr"} onClick={() => setSeg("kr")} />
                <Pill label="미국" active={seg === "us"} onClick={() => setSeg("us")} />
            </div>

            {/* 지수 카드 */}
            <div style={{ display: "flex", gap: 10, width: "100%" }}>
                {indices.map((idx) => {
                    const trend = idx.trend || {}
                    const pct = idx.change_pct
                    const col = (pct ?? 0) >= 0 ? C.success : C.danger
                    return (
                        <Card key={idx.label} style={{ flex: "1 1 0", minWidth: 0, padding: "14px 14px" }}>
                            <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 700, marginBottom: 6, fontFamily: FONT, letterSpacing: "0.03em" }}>{idx.label}</div>
                            <div style={{ color: C.textPrimary, fontSize: 20, fontWeight: 900, fontFamily: FONT, marginBottom: 2, letterSpacing: "-0.02em" }}>
                                {fmtNum(idx.value, (idx.value ?? 0) >= 100 ? 0 : 1)}
                            </div>
                            <div style={{ fontSize: 13, fontWeight: 700, fontFamily: FONT, color: col }}>
                                {pct != null ? `${pct >= 0 ? "+" : ""}${Number(pct).toFixed(2)}%` : "—"}
                            </div>
                            <div style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", gap: 4 }}>
                                <Stat label="1M" value={<PctText value={trend?.["1m"]?.change_pct} fontSize={11} bold={false} />} />
                                <Stat label="3M" value={<PctText value={trend?.["3m"]?.change_pct} fontSize={11} bold={false} />} />
                                <Stat label="1Y" value={<PctText value={trend?.["1y"]?.change_pct} fontSize={11} bold={false} />} />
                            </div>
                        </Card>
                    )
                })}
            </div>

            {/* 매크로 칩 */}
            {chips.length > 0 && (
                <Card>
                    <CardTitle>{seg === "kr" ? "국내 매크로" : "US 매크로"}</CardTitle>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                        {chips.slice(0, 6).map((m: any) => (
                            <div key={m.label} style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 10px" }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 600, marginBottom: 4, fontFamily: FONT }}>{m.label}</div>
                                <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                                    {fmtNum(m.value, m.dec)}{m.suffix || ""}
                                </div>
                                {m.pct != null && <PctText value={m.pct} fontSize={10} />}
                            </div>
                        ))}
                    </div>
                </Card>
            )}

            {/* 시장 심리 — 국가별 모델 */}
            <Card>
                <CardTitle>{seg === "kr" ? "국내 투자 심리" : "미국 투자 심리"}</CardTitle>
                <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                    <RingGauge value={moodScore} size={72} color={moodColor} strokeWidth={6} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ color: moodColor, fontSize: 17, fontWeight: 800, fontFamily: FONT, letterSpacing: "-0.02em" }}>
                            {mood.label || (moodScore >= 65 ? "낙관" : moodScore >= 45 ? "중립" : "불안")}
                        </div>
                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>
                            Market Mood {moodScore}/100 · {seg === "kr" ? "KR" : "US"}
                        </div>
                        {seg === "us" && fgCnn.value != null && (
                            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 6, lineHeight: 1.5 }}>
                                CNN Fear &amp; Greed {fgCnn.value}/100 · {fgCnn.description_kr || fgCnn.description || "—"}
                            </div>
                        )}
                        {seg === "kr" && (
                            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 6, lineHeight: 1.5 }}>
                                {moodScore >= 65 ? "리스크 자산 선호" : moodScore >= 45 ? "균형 유지" : "방어적 포지션"}
                            </div>
                        )}
                    </div>
                </div>
            </Card>

            {/* 자본 흐름 + Yield Spread (공통) */}
            {(capFlow.interpretation || yieldSp.value != null || bondRegime.rate_environment) && (
                <Card>
                    <CardTitle color={C.accent}>자본 흐름 · 금리 환경</CardTitle>
                    {capFlow.interpretation && (
                        <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, fontFamily: FONT, marginBottom: 4, lineHeight: 1.5 }}>
                            {capFlow.interpretation}
                        </div>
                    )}
                    {capFlow.flow_direction && (
                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 10 }}>
                            방향: {capFlow.flow_direction.replace(/_/g, " → ")}
                        </div>
                    )}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                        {yieldSp.value != null && (
                            <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 4 }}>10Y-2Y 스프레드</div>
                                <div style={{ color: yieldSp.signal === "정상" ? C.success : C.warn, fontSize: 13, fontWeight: 800, fontFamily: FONT }}>
                                    {Number(yieldSp.value).toFixed(2)}
                                </div>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>{yieldSp.signal}</div>
                            </div>
                        )}
                        {bondRegime.rate_environment && (
                            <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 4 }}>금리 환경</div>
                                <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                                    {bondRegime.rate_environment.replace("rate_", "").replace("elevated", "고금리").replace("low", "저금리").replace("normal", "정상")}
                                </div>
                                {bondRegime.recession_signal && (
                                    <div style={{ color: C.danger, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>⚠ 침체 신호</div>
                                )}
                            </div>
                        )}
                        {bondRegime.credit_cycle && (
                            <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 4 }}>크레딧 사이클</div>
                                <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                                    {bondRegime.credit_cycle === "tightening" ? "긴축" : bondRegime.credit_cycle === "easing" ? "완화" : bondRegime.credit_cycle}
                                </div>
                            </div>
                        )}
                    </div>
                </Card>
            )}

            {/* 매크로 진단 — 시장 심리 바로 아래로 이동 */}
            {diagnosis.length > 0 && (
                <Card>
                    <CardTitle color={"#A855F7"}>매크로 진단</CardTitle>
                    {diagnosis.slice(0, 4).map((dx: any, i: number, arr: any[]) => {
                        const isPos = dx.type === "positive"
                        const isWarn = dx.type === "warning" || dx.type === "negative"
                        const col = isPos ? C.success : isWarn ? C.warn : C.textSecondary
                        return (
                            <div key={i} style={{ display: "flex", gap: 8, padding: "7px 0", borderBottom: i < Math.min(arr.length, 4) - 1 ? `1px solid ${C.border}` : "none" }}>
                                <span style={{ width: 4, background: col, borderRadius: 2, flexShrink: 0, alignSelf: "stretch" }} />
                                <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5, flex: 1 }}>{dx.text}</span>
                            </div>
                        )
                    })}
                </Card>
            )}

            {/* ───── 국내 전용 섹션 ───── */}
            {seg === "kr" && (fluctUp.length > 0 || fluctDown.length > 0) && (
                <Card>
                    <CardTitle color={C.accent}>오늘의 급등락 TOP</CardTitle>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                        <div style={{ minWidth: 0, overflow: "hidden" }}>
                            <div style={{ color: C.success, fontSize: 12, fontWeight: 700, marginBottom: 6, fontFamily: FONT }}>급등 TOP 5</div>
                            {fluctUp.slice(0, 5).map((s: any, i: number) => (
                                <div key={s.stck_shrn_iscd || i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0", gap: 6, minWidth: 0 }}>
                                    <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: "1 1 auto", minWidth: 0 }}>{s.hts_kor_isnm}</span>
                                    <span style={{ color: C.success, fontSize: 12, fontWeight: 700, fontFamily: FONT, flexShrink: 0, ...MONO }}>+{Number(s.prdy_ctrt).toFixed(1)}%</span>
                                </div>
                            ))}
                        </div>
                        <div style={{ minWidth: 0, overflow: "hidden" }}>
                            <div style={{ color: C.danger, fontSize: 12, fontWeight: 700, marginBottom: 6, fontFamily: FONT }}>급락 TOP 5</div>
                            {fluctDown.slice(0, 5).map((s: any, i: number) => (
                                <div key={s.stck_shrn_iscd || i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0", gap: 6, minWidth: 0 }}>
                                    <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: "1 1 auto", minWidth: 0 }}>{s.hts_kor_isnm}</span>
                                    <span style={{ color: C.danger, fontSize: 12, fontWeight: 700, fontFamily: FONT, flexShrink: 0, ...MONO }}>{Number(s.prdy_ctrt).toFixed(1)}%</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </Card>
            )}

            {seg === "kr" && foreignInst.length > 0 && (
                <Card>
                    <CardTitle color={C.info}>외국인·기관 순매수</CardTitle>
                    {foreignInst.slice(0, 6).map((f: any, i: number, arr: any[]) => (
                        <div key={i} style={{
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                            padding: "7px 0", borderBottom: i < Math.min(arr.length, 6) - 1 ? `1px solid ${C.border}` : "none",
                        }}>
                            <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1, minWidth: 0 }}>{f.name || f.hts_kor_isnm}</span>
                            <span style={{ color: C.info, fontSize: 12, fontWeight: 700, fontFamily: FONT, flexShrink: 0 }}>{f.net_qty || f.acml_vol || "—"}</span>
                        </div>
                    ))}
                </Card>
            )}

            {seg === "kr" && rotation.cycle && (
                <Card>
                    <CardTitle color={"#A855F7"}>경기 사이클</CardTitle>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
                        <Badge text={rotation.cycle_label || rotation.cycle} color={"#A855F7"} />
                        <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, flex: 1, minWidth: 0 }}>{rotation.cycle_desc}</span>
                    </div>
                    {(rotation.recommended_sectors || []).slice(0, 5).map((s: any, i: number, arr: any[]) => (
                        <div key={i} style={{
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                            padding: "7px 0", borderBottom: i < arr.length - 1 ? `1px solid ${C.border}` : "none",
                        }}>
                            <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT }}>{s.name}</span>
                            <PctText value={s.change_pct} fontSize={11} />
                        </div>
                    ))}
                </Card>
            )}

            {seg === "kr" && sectors.length > 0 && (
                <Card>
                    <CardTitle>KRX 섹터 현황</CardTitle>
                    {sectors.slice(0, 7).map((s: any, i: number, arr: any[]) => (
                        <div key={i} style={{
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                            padding: "7px 0", borderBottom: i < Math.min(arr.length, 7) - 1 ? `1px solid ${C.border}` : "none",
                        }}>
                            <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT }}>{s.name}</span>
                            <PctText value={s.change_pct} fontSize={12} />
                        </div>
                    ))}
                </Card>
            )}

            {/* Crypto Macro (공통이지만 KR 유저에게 특히 유용) */}
            {cryptoMacro.available && cryptoMacro.composite?.score != null && (
                <Card>
                    <CardTitle color={C.warn}>크립토 매크로</CardTitle>
                    <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 10 }}>
                        <RingGauge
                            value={cryptoMacro.composite.score}
                            size={56}
                            color={cryptoMacro.composite.risk_level === "high" ? C.danger : cryptoMacro.composite.risk_level === "normal" ? C.warn : C.success}
                            strokeWidth={5}
                        />
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 800, fontFamily: FONT }}>{cryptoMacro.composite.label}</div>
                            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>리스크 {cryptoMacro.composite.risk_level}</div>
                            {cryptoMacro.composite.signals?.length > 0 && (
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 4, lineHeight: 1.4 }}>
                                    {cryptoMacro.composite.signals.slice(0, 2).join(" · ")}
                                </div>
                            )}
                        </div>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                        {cryptoMacro.fear_and_greed?.ok && (
                            <div style={{ background: C.bgElevated, borderRadius: 10, padding: "9px 12px" }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 3 }}>BTC F&G</div>
                                <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                                    {cryptoMacro.fear_and_greed.value} · {cryptoMacro.fear_and_greed.label}
                                </div>
                            </div>
                        )}
                        {cryptoMacro.stablecoin_mcap?.total_mcap_b && (
                            <div style={{ background: C.bgElevated, borderRadius: 10, padding: "9px 12px" }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 3 }}>스테이블 시총</div>
                                <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                                    ${Number(cryptoMacro.stablecoin_mcap.total_mcap_b).toFixed(0)}B
                                </div>
                            </div>
                        )}
                        {cryptoMacro.kimchi_premium?.ok && (
                            <div style={{ background: C.bgElevated, borderRadius: 10, padding: "9px 12px" }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 3 }}>김치 프리미엄</div>
                                <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                                    {Number(cryptoMacro.kimchi_premium.value).toFixed(2)}%
                                </div>
                            </div>
                        )}
                        {cryptoMacro.funding_rate?.ok && (
                            <div style={{ background: C.bgElevated, borderRadius: 10, padding: "9px 12px" }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 3 }}>펀딩레이트</div>
                                <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                                    {Number(cryptoMacro.funding_rate.avg).toFixed(4)}%
                                </div>
                            </div>
                        )}
                    </div>
                </Card>
            )}

            {/* ───── 미국 전용 섹션 ───── */}
            {seg === "us" && Object.keys(etfFlows).length > 0 && (
                <Card>
                    <CardTitle color={C.info}>ETF 자금 흐름 (1주)</CardTitle>
                    {fundFlows.rotation_signal && (
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                            <Badge text={fundFlows.rotation_signal} color={C.info} />
                            {(typeof fundFlows.rotation_detail === "string" ? fundFlows.rotation_detail : fundFlows.rotation_detail?.detail) && (
                                <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, flex: 1, minWidth: 0, lineHeight: 1.4 }}>
                                    {typeof fundFlows.rotation_detail === "string" ? fundFlows.rotation_detail : fundFlows.rotation_detail?.detail}
                                </span>
                            )}
                        </div>
                    )}
                    {[
                        { k: "SPY", label: "SPY · S&P500" },
                        { k: "QQQ", label: "QQQ · 나스닥100" },
                        { k: "IWM", label: "IWM · 소형주" },
                        { k: "TLT", label: "TLT · 장기국채" },
                        { k: "GLD", label: "GLD · 금" },
                    ].filter((x) => etfFlows[x.k]?.ok).map((x, i, arr) => {
                        const f = etfFlows[x.k]
                        const inflow = f.flow_signal === "inflow"
                        const col = inflow ? C.success : C.danger
                        return (
                            <div key={x.k} style={{
                                display: "flex", justifyContent: "space-between", alignItems: "center",
                                padding: "8px 0", borderBottom: i < arr.length - 1 ? `1px solid ${C.border}` : "none",
                            }}>
                                <div style={{ minWidth: 0 }}>
                                    <div style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT, fontWeight: 600 }}>{x.label}</div>
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>
                                        1W {f.price_1w_pct >= 0 ? "+" : ""}{Number(f.price_1w_pct).toFixed(2)}% · 거래량 {Number(f.volume_change_pct).toFixed(0)}%
                                    </div>
                                </div>
                                <div style={{ textAlign: "right" }}>
                                    <div style={{ color: col, fontSize: 12, fontWeight: 800, fontFamily: FONT }}>
                                        {inflow ? "유입" : "유출"}
                                    </div>
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>
                                        ${Number(f.money_flow_1w).toFixed(1)}M
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </Card>
            )}

            {seg === "us" && (cftc.overall_signal || pcr.signal) && (
                <Card>
                    <CardTitle color={C.warn}>기관 포지션</CardTitle>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                        {cftc.overall_signal && (
                            <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 4 }}>CFTC COT</div>
                                <div style={{
                                    color: cftc.overall_signal === "bullish" ? C.success
                                        : cftc.overall_signal === "bearish" ? C.danger : C.textPrimary,
                                    fontSize: 13, fontWeight: 800, fontFamily: FONT, textTransform: "uppercase",
                                }}>
                                    {cftc.overall_signal}
                                </div>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 4 }}>
                                    확신 {cftc.conviction_level ?? 0} · 종목 {cftc.total_instruments ?? 0}
                                </div>
                            </div>
                        )}
                        {pcr.signal && (
                            <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 4 }}>CBOE P/C Ratio</div>
                                <div style={{
                                    color: pcr.signal === "FEAR" || pcr.signal === "PANIC" ? C.danger
                                        : pcr.signal === "GREED" ? C.warn : C.textPrimary,
                                    fontSize: 13, fontWeight: 800, fontFamily: FONT,
                                }}>
                                    {pcr.signal}
                                </div>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 4 }}>
                                    {pcr.panic_trigger ? "패닉 신호" : "옵션 수급 정상"}
                                </div>
                            </div>
                        )}
                    </div>
                </Card>
            )}

            {seg === "us" && usHeadlines.length > 0 && (
                <Card>
                    <CardTitle color={C.info}>미국 주요 헤드라인</CardTitle>
                    {usHeadlines.slice(0, 4).map((h: any, i: number, arr: any[]) => {
                        const sCol = h.sentiment === "positive" ? C.success : h.sentiment === "negative" ? C.danger : C.textSecondary
                        const inner = (
                            <>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: sCol, flexShrink: 0 }} />
                                    <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{h.source}</span>
                                </div>
                                <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600, fontFamily: FONT, lineHeight: 1.45 }}>{h.title}</div>
                            </>
                        )
                        return h.link ? (
                            <a key={i} href={h.link} target="_blank" rel="noopener noreferrer" style={{
                                display: "block", padding: "8px 0",
                                borderBottom: i < Math.min(arr.length, 4) - 1 ? `1px solid ${C.border}` : "none",
                                textDecoration: "none",
                            }}>{inner}</a>
                        ) : (
                            <div key={i} style={{ padding: "8px 0", borderBottom: i < Math.min(arr.length, 4) - 1 ? `1px solid ${C.border}` : "none" }}>{inner}</div>
                        )
                    })}
                </Card>
            )}

            {events.length > 0 && (
                <Card>
                    <CardTitle color={C.info}>주요 경제 이벤트</CardTitle>
                    {events.slice(0, 4).map((e: any, i: number, arr: any[]) => (
                        <div key={i} style={{ padding: "8px 0", borderBottom: i < Math.min(arr.length, 4) - 1 ? `1px solid ${C.border}` : "none" }}>
                            <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600, fontFamily: FONT, lineHeight: 1.5 }}>{e.name || e.event}</div>
                            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>{e.date} · {e.country || "글로벌"}</div>
                        </div>
                    ))}
                </Card>
            )}
        </div>
    )
}

/* ══════════════════════════════════════════════════════════════════
   RECO TAB — 정보 풍부한 카드 + 바텀시트 상세
   ══════════════════════════════════════════════════════════════════ */

function RecoCard({ r, onClick }: { r: any; onClick: () => void }) {
    const g = (r.recommendation || r.verity_brain?.grade || "WATCH").toUpperCase()
    const gc = GRADE_COLOR[g] || C.textSecondary
    const brain = r.verity_brain?.brain_score ?? r.multi_factor?.multi_score ?? r.confidence ?? null
    const isusd = isUS(r)
    const price = r.price ?? r.current_price
    const cur = isusd ? "USD" : "KRW"
    const sparkSource: number[] | undefined = r.sparkline || r.sparkline_weekly
    const changePct = r.change_pct ?? calcSparkChange(sparkSource)
    const changeCol = (changePct ?? 0) >= 0 ? C.success : C.danger

    const per = r.per, roe = r.roe, cap = r.market_cap
    const drop = r.drop_from_high_pct
    const gold = r.gold_insight
    const timing = r.timing || {}
    const riskFlags: string[] = r.risk_flags || []
    const targetUpside = (r.target_price != null && price) ? ((r.target_price - price) / price) * 100 : null

    return (
        <Card onClick={onClick} style={{ padding: "14px 16px" }}>
            {/* Row 1: score · name · badge · price */}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{
                    width: 42, height: 42, borderRadius: 12, background: `${gc}18`,
                    border: `1px solid ${gc}30`,
                    display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                }}>
                    <span style={{ color: gc, fontSize: 14, fontWeight: 800, fontFamily: FONT, lineHeight: 1 }}>{brain ?? "—"}</span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                        <span style={{ color: C.textPrimary, fontSize: 15, fontWeight: 800, fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", letterSpacing: "-0.01em" }}>{r.name}</span>
                        <span title={g === "AVOID" ? AVOID_TOOLTIP : undefined} style={{ cursor: g === "AVOID" ? "help" : "default" }}>
                            <Badge text={GRADE_LABEL[g] || g} color={gc} />
                        </span>
                        {Array.isArray(r.overrides_applied) && r.overrides_applied.length > 0 && (
                            <span style={{ color: "#7DD3FC", fontSize: 12, fontWeight: 600 }} title={`overrides: ${r.overrides_applied.join(", ")}`}>
                                {(r.overrides_applied as string[]).slice(0, 1).map((o) => OVERRIDE_LABELS[o] || o).join("")}
                            </span>
                        )}
                    </div>
                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {r.ticker} · {r.market || "—"}{r.company_type ? ` · ${r.company_type}` : ""}
                    </div>
                </div>
                <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 800, fontFamily: FONT, letterSpacing: "-0.01em" }}>
                        {isusd ? `$${fmtNum(price, 2)}` : fmtKRW(price)}
                    </div>
                    {changePct != null ? (
                        <div style={{ color: changeCol, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                            {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
                        </div>
                    ) : (
                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>—</div>
                    )}
                    {targetUpside != null && (
                        <div style={{ color: targetUpside >= 0 ? C.accent : C.textSecondary, fontSize: 12, fontWeight: 700, fontFamily: FONT, marginTop: 2 }}>
                            🎯 {targetUpside >= 0 ? "+" : ""}{targetUpside.toFixed(1)}%
                        </div>
                    )}
                </div>
            </div>

            {/* Row 2: stats grid (PER · ROE · Cap · 52w drop) */}
            <div style={{ display: "flex", gap: 8, marginTop: 12, padding: "10px 12px", background: C.bgElevated, borderRadius: 10 }}>
                <Stat label="PER" value={per != null && per !== 0 ? `${Number(per).toFixed(1)}배` : "—"} />
                <Stat label="ROE" value={roe != null && roe !== 0 ? `${Number(roe).toFixed(1)}%` : "—"} accent={roe >= 15 ? C.success : undefined} />
                <Stat label="시총" value={fmtCap(cap, cur)} />
                <Stat label="52w 저점" value={drop != null ? `${drop >= 0 ? "+" : ""}${Number(drop).toFixed(1)}%` : "—"} accent={drop != null && drop <= -20 ? C.warn : undefined} />
            </div>

            {/* Row 3: insight or tagline + mini sparkline */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10 }}>
                {gold ? (
                    <div style={{ flex: 1, minWidth: 0, color: C.textPrimary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2 as any, WebkitBoxOrient: "vertical" as any }}>
                        <span style={{ color: C.accent, marginRight: 4 }}>●</span>{gold}
                    </div>
                ) : (
                    <div style={{ flex: 1, minWidth: 0, color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                        {r.ai_verdict || timing.reasons?.[0] || "분석 데이터 없음"}
                    </div>
                )}
                {sparkSource && (
                    <Sparkline data={sparkSource.slice(-20)} width={64} height={22} color={(changePct ?? 0) >= 0 ? C.success : C.danger} fill={false} />
                )}
            </div>

            {/* Row 4: risk flags if any */}
            {riskFlags.length > 0 && (
                <div style={{ display: "flex", gap: 4, marginTop: 10, flexWrap: "wrap" }}>
                    {riskFlags.slice(0, 3).map((rf, i) => (
                        <span key={i} style={{ fontSize: 12, fontWeight: 700, padding: "2px 6px", borderRadius: 6, background: `${C.danger}15`, color: C.danger, fontFamily: FONT }}>⚠ {rf}</span>
                    ))}
                </div>
            )}
        </Card>
    )
}

function RecoDetail({ stock: s }: { stock: any }) {
    const brain = s.verity_brain || {}, mf = s.multi_factor || {}, niche = s.niche_data || {}, trends = s.trends || {}
    const isusd = isUS(s)
    const cur = isusd ? "USD" : "KRW"
    const g = (s.recommendation || brain.grade || "WATCH").toUpperCase()
    const gc = GRADE_COLOR[g] || C.textSecondary
    const price = s.price ?? s.current_price
    const priceFmt = isusd ? `$${fmtNum(price, 2)}` : fmtKRW(price)
    const sparkSource: number[] | undefined = s.sparkline || s.sparkline_weekly

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {/* Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <Badge text={GRADE_LABEL[g] || g} color={gc} />
                    <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{s.ticker} · {s.market}</span>
                </div>
                <div style={{ textAlign: "right" }}>
                    <div style={{ color: C.textPrimary, fontSize: 20, fontWeight: 900, fontFamily: FONT, letterSpacing: "-0.02em" }}>{priceFmt}</div>
                    {s.target_price != null && (
                        <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                            목표 {isusd ? `$${fmtNum(s.target_price, 2)}` : fmtKRW(s.target_price)}
                        </div>
                    )}
                </div>
            </div>

            {/* Sparkline full width */}
            {sparkSource && sparkSource.length > 2 && (
                <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                        <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, fontWeight: 600, letterSpacing: "0.03em" }}>추세 ({sparkSource.length}일)</span>
                        <PctText value={calcSparkChangeFromStart(sparkSource)} fontSize={11} />
                    </div>
                    <Sparkline data={sparkSource} width={300} height={48} color={(calcSparkChangeFromStart(sparkSource) ?? 0) >= 0 ? C.success : C.danger} />
                </div>
            )}

            {/* Brain score */}
            {brain.brain_score != null && (
                <Card style={{ padding: 14 }}>
                    <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
                        <RingGauge value={brain.brain_score} size={64} color={gc} strokeWidth={5} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 3, fontFamily: FONT }}>VERITY BRAIN</div>
                            <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, fontFamily: FONT, marginBottom: 2 }}>{brain.summary || s.ai_verdict || "종합 분석 점수"}</div>
                            {brain.fact_score?.score != null && (
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>팩트 {brain.fact_score.score} · 확신도 {s.confidence ?? brain.confidence ?? "—"}</div>
                            )}
                        </div>
                    </div>
                </Card>
            )}

            {/* Fundamentals */}
            <Card style={{ padding: 14 }}>
                <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 10, fontFamily: FONT }}>재무 지표</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, rowGap: 12 }}>
                    <Stat label="PER" value={s.per != null && s.per !== 0 ? `${Number(s.per).toFixed(1)}배` : "—"} />
                    {/* §13 PBR normalize 마커 — pbr_normalized_neutral=true 면 데이터 보정 표기 */}
                    <Stat
                        label={s.pbr_normalized_neutral ? "PBR ⚠" : "PBR"}
                        value={s.pbr != null && s.pbr !== 0 ? `${Number(s.pbr).toFixed(2)}배` : "—"}
                        accent={s.pbr_normalized_neutral ? C.warn : undefined}
                    />
                    <Stat label="배당률" value={s.div_yield != null && s.div_yield !== 0 ? `${Number(s.div_yield).toFixed(2)}%` : "—"} />
                    <Stat label="ROE" value={s.roe != null && s.roe !== 0 ? `${Number(s.roe).toFixed(1)}%` : "—"} accent={s.roe >= 15 ? C.success : undefined} />
                    <Stat label="영업이익률" value={s.operating_margin != null && s.operating_margin !== 0 ? `${Number(s.operating_margin).toFixed(1)}%` : "—"} />
                    <Stat label="매출성장" value={s.revenue_growth != null ? `${s.revenue_growth >= 0 ? "+" : ""}${Number(s.revenue_growth).toFixed(1)}%` : "—"} accent={s.revenue_growth > 0 ? C.success : undefined} />
                    <Stat label="시총" value={fmtCap(s.market_cap, cur)} />
                    <Stat label="거래대금" value={fmtCap(s.trading_value, cur)} />
                    <Stat label="부채비율" value={s.debt_ratio != null ? `${Number(s.debt_ratio).toFixed(1)}%` : "—"} />
                </div>
            </Card>

            {/* 52w range */}
            {(s.high_52w || s.low_52w) && (
                <Card style={{ padding: 14 }}>
                    <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 10, fontFamily: FONT }}>52주 레인지</div>
                    {(() => {
                        const low = s.low_52w ?? 0, high = s.high_52w ?? 0
                        const range = high - low || 1
                        const pos = Math.max(0, Math.min(100, ((price - low) / range) * 100))
                        return (
                            <>
                                <div style={{ position: "relative", height: 6, background: C.border, borderRadius: 3, marginBottom: 8 }}>
                                    <div style={{ position: "absolute", left: `${pos}%`, top: -3, width: 12, height: 12, borderRadius: "50%", background: gc, transform: "translateX(-50%)", boxShadow: `0 0 8px ${gc}80` }} />
                                </div>
                                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, fontFamily: FONT }}>
                                    <div><div style={{ color: C.textSecondary }}>저점</div><div style={{ color: C.textPrimary, fontWeight: 700, marginTop: 2 }}>{isusd ? `$${fmtNum(low, 2)}` : fmtKRW(low)}</div></div>
                                    <div style={{ textAlign: "center" }}><div style={{ color: C.textSecondary }}>현재 위치</div><div style={{ color: gc, fontWeight: 800, marginTop: 2 }}>{pos.toFixed(0)}%</div></div>
                                    <div style={{ textAlign: "right" }}><div style={{ color: C.textSecondary }}>고점</div><div style={{ color: C.textPrimary, fontWeight: 700, marginTop: 2 }}>{isusd ? `$${fmtNum(high, 2)}` : fmtKRW(high)}</div></div>
                                </div>
                            </>
                        )
                    })()}
                </Card>
            )}

            {/* Multi factor */}
            {mf.multi_score != null && (
                <Card style={{ padding: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                        <span style={{ color: C.accent, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>멀티팩터 분석</span>
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <span style={{ color: C.textPrimary, fontSize: 16, fontWeight: 800, fontFamily: FONT }}>{mf.multi_score}</span>
                            <span style={{ color: gc, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>{mf.grade || GRADE_LABEL[g]}</span>
                        </div>
                    </div>
                    {mf.factor_breakdown && (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                            {Object.entries(mf.factor_breakdown).slice(0, 6).map(([k, v]: any) => {
                                const pct = typeof v === "number" ? Math.min(100, Math.max(0, v)) : 0
                                const col = pct >= 70 ? C.success : pct >= 40 ? C.warn : C.danger
                                return (
                                    <div key={k}>
                                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                                            <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{k}</span>
                                            <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>{pct.toFixed(0)}</span>
                                        </div>
                                        <div style={{ height: 3, background: C.border, borderRadius: 2, overflow: "hidden" }}>
                                            <div style={{ height: "100%", width: `${pct}%`, background: col, transition: "width 0.4s" }} />
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </Card>
            )}

            {/* Insights */}
            {(s.gold_insight || s.silver_insight) && (
                <Card style={{ padding: 14 }}>
                    <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 8, fontFamily: FONT }}>핵심 인사이트</div>
                    {s.gold_insight && <div style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5, marginBottom: 6 }}>● {s.gold_insight}</div>}
                    {s.silver_insight && <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>· {s.silver_insight}</div>}
                </Card>
            )}

            {/* Niche / Trends */}
            {(niche.trends || trends.keyword) && (
                <Card style={{ padding: 14 }}>
                    <div style={{ color: C.info, fontSize: 12, fontWeight: 700, marginBottom: 8, fontFamily: FONT }}>니치 인텔</div>
                    {(niche.trends?.keyword || trends.keyword) && (
                        <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600, fontFamily: FONT, marginBottom: 4 }}>키워드: {niche.trends?.keyword || trends.keyword}</div>
                    )}
                    {(niche.trends?.summary || trends.summary) && (
                        <div style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.5, fontFamily: FONT }}>{niche.trends?.summary || trends.summary}</div>
                    )}
                </Card>
            )}

            {/* AI analysis */}
            {s.ai_analysis?.summary && (
                <Card style={{ padding: 14 }}>
                    <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 8, fontFamily: FONT }}>AI 분석</div>
                    <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.6, fontFamily: FONT }}>{s.ai_analysis.summary}</div>
                </Card>
            )}

            {/* Timing reasons */}
            {s.timing?.reasons?.length > 0 && (
                <Card style={{ padding: 14 }}>
                    <div style={{ color: s.timing.color || C.accent, fontSize: 12, fontWeight: 700, marginBottom: 8, fontFamily: FONT }}>
                        타이밍: {s.timing.label || s.timing.action}
                    </div>
                    {s.timing.reasons.slice(0, 4).map((rr: string, i: number) => (
                        <div key={i} style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5, marginBottom: 2 }}>· {rr}</div>
                    ))}
                </Card>
            )}
        </div>
    )
}

function RecoTab({ data }: { data: any }) {
    const [category, setCategory] = useState<"reco" | "safe" | "value">("reco")
    const [region, setRegion] = useState<"all" | "kr" | "us">("all")
    const [filter, setFilter] = useState<"all" | "buy" | "watch" | "avoid">("all")
    const [sortBy, setSortBy] = useState<"score" | "return" | "upside">("score")
    const [selectedIdx, setSelectedIdx] = useState<number | null>(null)

    const allRecs: any[] = data?.recommendations || []
    const dividendStocks: any[] = data?.safe_recommendations?.dividend_stocks || []
    const parkingOptions: any[] = data?.safe_recommendations?.parking_options || []
    const valueCandidates: any[] = data?.value_hunt?.value_candidates || []
    const valueGate = data?.value_hunt?.gate_open
    const valueReason = data?.value_hunt?.gate_reason

    const gradeOf = (r: any) => (r.recommendation || r.verity_brain?.grade || "WATCH").toUpperCase()
    const scoreOf = (r: any) => r.verity_brain?.brain_score ?? r.multi_factor?.multi_score ?? r.confidence ?? 0
    const upsideOf = (r: any) => {
        const p = r.price ?? r.current_price
        if (r.target_price == null || !p) return -Infinity
        return ((r.target_price - p) / p) * 100
    }

    // 카테고리별 소스
    const source = category === "safe" ? [...dividendStocks, ...parkingOptions]
        : category === "value" ? valueCandidates
        : allRecs

    // 지역 필터
    const regionFiltered = region === "all" ? source
        : region === "us" ? source.filter((r) => isUS(r))
        : source.filter((r) => !isUS(r))

    // 등급 필터 (reco 카테고리에서만 의미)
    const filtered = ((category !== "reco" || filter === "all") ? regionFiltered : regionFiltered.filter((r) => {
        const g = gradeOf(r)
        if (filter === "buy") return g === "STRONG_BUY" || g === "BUY"
        if (filter === "watch") return g === "WATCH"
        if (filter === "avoid") return g === "AVOID" || g === "CAUTION"
        return true
    })).slice().sort((a, b) => {
        if (sortBy === "score") return scoreOf(b) - scoreOf(a)
        if (sortBy === "return") return (b.change_pct ?? calcSparkChange(b.sparkline) ?? 0) - (a.change_pct ?? calcSparkChange(a.sparkline) ?? 0)
        if (sortBy === "upside") return upsideOf(b) - upsideOf(a)
        return 0
    })

    const selected = selectedIdx != null ? filtered[selectedIdx] : null

    const counts = {
        all: allRecs.length,
        buy: allRecs.filter((r) => { const g = gradeOf(r); return g === "STRONG_BUY" || g === "BUY" }).length,
        watch: allRecs.filter((r) => gradeOf(r) === "WATCH").length,
        avoid: allRecs.filter((r) => { const g = gradeOf(r); return g === "AVOID" || g === "CAUTION" }).length,
        safe: dividendStocks.length + parkingOptions.length,
        value: valueCandidates.length,
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* Category pills */}
            <div style={{ display: "flex", gap: 6, padding: "0 2px" }}>
                <Pill label={`AI 추천 ${counts.all}`} active={category === "reco"} onClick={() => { setCategory("reco"); setSelectedIdx(null) }} />
                <Pill label={`안전 ${counts.safe}`} active={category === "safe"} onClick={() => { setCategory("safe"); setSelectedIdx(null) }} />
                <Pill label={`가치 ${counts.value}`} active={category === "value"} onClick={() => { setCategory("value"); setSelectedIdx(null) }} />
            </div>

            {/* Region + Grade filters */}
            <div style={{ display: "flex", gap: 6, padding: "0 2px", flexWrap: "wrap" }}>
                {([["all", "전체"], ["kr", "국내"], ["us", "미국"]] as const).map(([k, l]) => (
                    <button key={k} onClick={() => setRegion(k)} style={{
                        border: "none", padding: "5px 12px", borderRadius: 16,
                        fontSize: 12, fontWeight: region === k ? 800 : 600, fontFamily: FONT, cursor: "pointer",
                        background: region === k ? C.accent : C.bgCard,
                        color: region === k ? "#000" : C.textSecondary,
                    }}>{l}</button>
                ))}
                {category === "reco" && (
                    <>
                        <span style={{ color: C.textTertiary, margin: "0 2px", alignSelf: "center" }}>|</span>
                        <button onClick={() => setFilter("all")} style={{
                            border: "none", padding: "5px 10px", borderRadius: 16, fontSize: 12,
                            fontWeight: filter === "all" ? 800 : 600, fontFamily: FONT, cursor: "pointer",
                            background: filter === "all" ? C.border : "transparent", color: filter === "all" ? C.textPrimary : C.textSecondary,
                        }}>전체등급</button>
                        <button onClick={() => setFilter("buy")} style={{
                            border: "none", padding: "5px 10px", borderRadius: 16, fontSize: 12,
                            fontWeight: filter === "buy" ? 800 : 600, fontFamily: FONT, cursor: "pointer",
                            background: filter === "buy" ? C.border : "transparent", color: filter === "buy" ? C.success : C.textSecondary,
                        }}>매수 {counts.buy}</button>
                        <button onClick={() => setFilter("watch")} style={{
                            border: "none", padding: "5px 10px", borderRadius: 16, fontSize: 12,
                            fontWeight: filter === "watch" ? 800 : 600, fontFamily: FONT, cursor: "pointer",
                            background: filter === "watch" ? C.border : "transparent", color: filter === "watch" ? C.warn : C.textSecondary,
                        }}>관망 {counts.watch}</button>
                        <button onClick={() => setFilter("avoid")} style={{
                            border: "none", padding: "5px 10px", borderRadius: 16, fontSize: 12,
                            fontWeight: filter === "avoid" ? 800 : 600, fontFamily: FONT, cursor: "pointer",
                            background: filter === "avoid" ? C.border : "transparent", color: filter === "avoid" ? C.danger : C.textSecondary,
                        }}>회피 {counts.avoid}</button>
                    </>
                )}
            </div>

            {/* Sort */}
            <div style={{ display: "flex", gap: 6, padding: "0 2px", alignItems: "center" }}>
                <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginRight: 4, fontWeight: 600 }}>정렬</span>
                {([["score", "점수순"], ["return", "수익순"], ["upside", "목표가여유"]] as const).map(([k, l]) => (
                    <button key={k} onClick={() => setSortBy(k)} style={{
                        border: "none", padding: "4px 8px", borderRadius: 6,
                        fontSize: 12, fontWeight: sortBy === k ? 700 : 500, fontFamily: FONT, cursor: "pointer",
                        color: sortBy === k ? C.textPrimary : C.textSecondary,
                        background: sortBy === k ? C.border : "transparent",
                    }}>{l}</button>
                ))}
            </div>

            {/* Category intro */}
            {category === "safe" && (
                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, padding: "0 4px", lineHeight: 1.5 }}>
                    배당·저부채 중심의 보수적 추천. 기준 배당률 2.6% 이상.
                </div>
            )}
            {category === "value" && (
                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, padding: "0 4px", lineHeight: 1.5 }}>
                    가치 헌팅 게이트 {valueGate ? <span style={{ color: C.success, fontWeight: 700 }}>ON</span> : <span style={{ color: C.textSecondary, fontWeight: 700 }}>OFF</span>}
                    {valueReason ? ` · ${valueReason}` : ""}
                </div>
            )}

            {/* Cards */}
            {category === "safe"
                ? filtered.map((r: any, i: number) => (
                    <SafeCard key={r.ticker || i} r={r} isDividend={dividendStocks.includes(r)} />
                ))
                : filtered.map((r: any, i: number) => (
                    <RecoCard key={r.ticker || i} r={r} onClick={() => setSelectedIdx(i)} />
                ))
            }

            {filtered.length === 0 && (
                <div style={{ textAlign: "center", padding: 40, color: C.textSecondary, fontSize: 13, fontFamily: FONT }}>
                    {category === "value" && !valueGate ? "가치 헌팅 게이트가 닫혀있습니다" : "해당 조건의 종목이 없습니다"}
                </div>
            )}

            {/* Detail sheet */}
            <BottomSheet open={selected != null} onClose={() => setSelectedIdx(null)} title={selected?.name || ""}>
                {selected && <RecoDetail stock={selected} />}
            </BottomSheet>
        </div>
    )
}

function SafeCard({ r, isDividend }: { r: any; isDividend: boolean }) {
    const isusd = isUS(r)
    const tier = r.safety_tier || "B"
    const tierColor = tier === "S" ? C.accent : tier === "A" ? C.success : C.warn
    return (
        <Card style={{ padding: "14px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{
                    width: 40, height: 40, borderRadius: 12, background: `${tierColor}18`,
                    border: `1px solid ${tierColor}40`,
                    display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                }}>
                    <span style={{ color: tierColor, fontSize: 15, fontWeight: 900, fontFamily: FONT }}>{tier}</span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ color: C.textPrimary, fontSize: 14, fontWeight: 800, fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name}</span>
                        <Badge text={isDividend ? "배당" : "파킹"} color={tierColor} />
                    </div>
                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>
                        {r.ticker} · {r.market || "—"}
                    </div>
                </div>
                <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 800, fontFamily: FONT }}>
                        {isusd ? `$${fmtNum(r.price, 2)}` : fmtKRW(r.price)}
                    </div>
                    {r.div_yield != null && (
                        <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                            배당 {Number(r.div_yield).toFixed(2)}%
                        </div>
                    )}
                </div>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 12, padding: "10px 12px", background: C.bgElevated, borderRadius: 10 }}>
                <Stat label="ROE" value={r.roe != null ? `${Number(r.roe).toFixed(1)}%` : "—"} accent={r.roe >= 10 ? C.success : undefined} />
                <Stat label="영업이익률" value={r.operating_margin != null ? `${Number(r.operating_margin).toFixed(1)}%` : "—"} />
                <Stat label="부채비율" value={r.debt_ratio != null ? `${Number(r.debt_ratio).toFixed(1)}%` : "—"} accent={r.debt_ratio > 100 ? C.warn : undefined} />
                <Stat label="안전점수" value={r.safety_score ?? "—"} accent={tierColor} />
            </div>
            {r.reason && (
                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5, marginTop: 8 }}>
                    <span style={{ color: tierColor, marginRight: 4 }}>●</span>{r.reason}
                </div>
            )}
        </Card>
    )
}

/* ══════════════════════════════════════════════════════════════════
   AI TAB
   ══════════════════════════════════════════════════════════════════ */
type PeriodId = "daily" | "weekly" | "monthly" | "quarterly" | "semi" | "annual"
const PERIOD_OPTIONS: { id: PeriodId; label: string; nextTrigger?: string }[] = [
    { id: "daily", label: "일일" },
    { id: "weekly", label: "주간" },
    { id: "monthly", label: "월간", nextTrigger: "매월 1일 자동 생성" },
    { id: "quarterly", label: "분기", nextTrigger: "1·4·7·10월 2일 생성" },
    { id: "semi", label: "반기", nextTrigger: "1·7월 3일 생성" },
    { id: "annual", label: "연간", nextTrigger: "매년 1월 4일 생성" },
]

/* ─── VERITY Chat (inline) ─── */
interface ChatMsg { role: "user" | "assistant"; text: string }

function VerityChatCard({ apiUrl }: { apiUrl: string }) {
    const [messages, setMessages] = useState<ChatMsg[]>([])
    const [input, setInput] = useState("")
    const [loading, setLoading] = useState(false)
    const [streaming, setStreaming] = useState(false)
    const bodyRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" })
    }, [messages, loading, streaming])

    const send = async () => {
        const q = input.trim()
        if (!q || loading || streaming || !apiUrl) return
        setInput("")
        setMessages((prev) => [...prev, { role: "user", text: q }])
        setLoading(true)
        setStreaming(false)

        const appendAssistant = (text: string) => {
            setMessages((prev) => {
                const n = [...prev]
                const last = n[n.length - 1]
                if (last?.role === "assistant") n[n.length - 1] = { role: "assistant", text }
                else n.push({ role: "assistant", text })
                return n
            })
        }

        try {
            const resp = await fetch(apiUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question: q, stream: true }),
            })
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({} as { error?: string }))
                throw new Error(err.error || `HTTP ${resp.status}`)
            }
            const ct = resp.headers.get("content-type") || ""
            if (!ct.includes("ndjson") && ct.includes("json")) {
                const data = await resp.json()
                setMessages((prev) => [...prev, { role: "assistant", text: data.ok ? data.answer : (data.error || "응답 없음") }])
                return
            }
            const reader = resp.body?.getReader()
            if (!reader) throw new Error("스트림을 읽을 수 없습니다")
            const dec = new TextDecoder()
            let buf = ""
            let acc = ""
            while (true) {
                const { done, value } = await reader.read()
                if (done) break
                buf += dec.decode(value, { stream: true })
                const lines = buf.split("\n")
                buf = lines.pop() || ""
                for (const line of lines) {
                    const t = line.trim()
                    if (!t) continue
                    try {
                        const ev = JSON.parse(t) as { type?: string; text?: string; message?: string }
                        if (ev.type === "delta" && ev.text) {
                            acc += ev.text
                            setLoading(false)
                            setStreaming(true)
                            appendAssistant(acc)
                        } else if (ev.type === "error") {
                            throw new Error(ev.message || "오류")
                        } else if (ev.type === "end") {
                            setStreaming(false)
                            setLoading(false)
                        }
                    } catch (err) {
                        // JSON 아닌 라인은 무시
                    }
                }
            }
            if (!acc) setMessages((prev) => [...prev, { role: "assistant", text: "응답이 비어 있습니다" }])
        } catch (e: any) {
            setMessages((prev) => [...prev, { role: "assistant", text: `오류: ${e?.message || "연결 실패"}` }])
        } finally {
            setLoading(false)
            setStreaming(false)
        }
    }

    const canSend = input.trim().length > 0 && !loading && !streaming

    return (
        <Card style={{ borderColor: `${C.accent}30` }}>
            <CardTitle color={C.accent} right={<Badge text="CHAT" color={C.accent} />}>VERITY에게 질문</CardTitle>

            {messages.length > 0 && (
                <div ref={bodyRef} style={{
                    maxHeight: 320, overflowY: "auto",
                    display: "flex", flexDirection: "column", gap: 8,
                    padding: "4px 2px", marginBottom: 10,
                    WebkitOverflowScrolling: "touch",
                }}>
                    {messages.map((m, i) => (
                        <div key={i} style={{
                            alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                            background: m.role === "user" ? C.accent : C.bgElevated,
                            color: m.role === "user" ? "#000" : C.textPrimary,
                            fontSize: 12, fontFamily: FONT, lineHeight: 1.5,
                            padding: "8px 12px", borderRadius: 12,
                            borderBottomRightRadius: m.role === "user" ? 4 : 12,
                            borderBottomLeftRadius: m.role === "assistant" ? 4 : 12,
                            maxWidth: "86%", whiteSpace: "pre-wrap", wordBreak: "break-word",
                        }}>
                            {m.text}
                            {streaming && i === messages.length - 1 && m.role === "assistant" && (
                                <span style={{ color: C.accent, marginLeft: 2, opacity: 0.8 }}>▌</span>
                            )}
                        </div>
                    ))}
                    {loading && (
                        <div style={{
                            alignSelf: "flex-start", background: C.bgElevated, color: C.accent,
                            fontSize: 12, fontFamily: "ui-monospace, monospace", lineHeight: 1.4,
                            padding: "8px 12px", borderRadius: 12,
                        }}>portfolio.json 대조 중…</div>
                    )}
                </div>
            )}

            {messages.length === 0 && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
                    {["지금 시장 어때?", "포트폴리오 점검", "오늘 추천 종목?"].map((s) => (
                        <button key={s} onClick={() => setInput(s)} style={{
                            background: C.bgElevated, border: `1px solid ${C.border}`, color: C.textSecondary,
                            fontSize: 12, fontFamily: FONT, padding: "6px 12px", borderRadius: 14, cursor: "pointer",
                        }}>{s}</button>
                    ))}
                </div>
            )}

            <div style={{ display: "flex", gap: 6 }}>
                <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") send() }}
                    placeholder="VERITY에게 질문…"
                    disabled={loading || streaming}
                    style={{
                        flex: 1, background: C.bgElevated, border: `1px solid ${C.border}`,
                        borderRadius: 10, padding: "10px 12px", color: C.textPrimary,
                        fontSize: 13, fontFamily: FONT, outline: "none",
                    }}
                />
                <button
                    onClick={send}
                    disabled={!canSend}
                    style={{
                        background: canSend ? C.accent : C.border,
                        color: canSend ? "#000" : C.textSecondary,
                        border: "none", padding: "0 16px", borderRadius: 10,
                        fontSize: 15, fontWeight: 900, fontFamily: FONT,
                        cursor: canSend ? "pointer" : "not-allowed",
                        minWidth: 46,
                    }}
                >↑</button>
            </div>
            {messages.length > 0 && (
                <button onClick={() => setMessages([])} style={{
                    marginTop: 8, background: "transparent", border: "none",
                    color: C.textSecondary, fontSize: 12, fontFamily: FONT, cursor: "pointer",
                    textAlign: "right", width: "100%", padding: "2px 4px",
                }}>대화 초기화</button>
            )}
        </Card>
    )
}

function AITab({ data, chatApiUrl }: { data: any; chatApiUrl: string }) {
    const [period, setPeriod] = useState<PeriodId>("daily")
    const isDaily = period === "daily"
    const report = data?.[`${period}_report`] || {}
    const reportUS = data?.[`${period}_report_us`] || {}
    const brain = data?.verity_brain || {}, leader = data?.ai_leaderboard || {}
    const morning = data?.claude_morning_strategy || {}
    const postmortem = data?.postmortem || {}
    const crossVerify = data?.cross_verification || {}
    const factorIC = data?.factor_ic || {}
    const hasMorning = isDaily && !!(morning.scenario || morning.watch_points?.length)
    const hasReport = isDaily
        ? !!(report.market_summary || report.market_analysis || report.strategy)
        : !!(report.executive_summary || report.performance_review || report.strategy)
    const currentOption = PERIOD_OPTIONS.find((p) => p.id === period)

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <VerityChatCard apiUrl={chatApiUrl} />

            <div style={{
                display: "flex", gap: 6, padding: "0 2px",
                overflowX: "auto", overflowY: "hidden",
                WebkitOverflowScrolling: "touch",
                scrollbarWidth: "none" as const, msOverflowStyle: "none" as const,
            }}>
                <style>{`
                    div::-webkit-scrollbar { display: none; }
                `}</style>
                {PERIOD_OPTIONS.map((opt) => (
                    <div key={opt.id} style={{ flexShrink: 0 }}>
                        <Pill label={opt.label} active={period === opt.id} onClick={() => setPeriod(opt.id)} />
                    </div>
                ))}
            </div>

            {/* 데이터 없을 때 안내 */}
            {!hasReport && !isDaily && (
                <Card style={{ borderColor: `${C.textSecondary}30` }}>
                    <div style={{ textAlign: "center", padding: "20px 0" }}>
                        <div style={{ fontSize: 28, marginBottom: 10 }}>📋</div>
                        <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700, fontFamily: FONT, marginBottom: 6 }}>
                            {currentOption?.label} 리포트 생성 대기 중
                        </div>
                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.6 }}>
                            {currentOption?.nextTrigger || "정기 생성 스케줄 대기 중입니다"}
                        </div>
                    </div>
                </Card>
            )}

            {/* 성과표 + 기대수익률 — 주기 리포트 최상단 */}
            {!isDaily && hasReport && (() => {
                const stats = (report as any)._raw_stats || {}
                const expected = (report as any).expected_return || {}
                const realized = {
                    hit: stats.hit_rate_pct,
                    ret: stats.avg_return_pct,
                    total: stats.total_buy_recs,
                }
                const hasRealized = realized.total != null && realized.total > 0
                const hasExpected = expected.count != null && expected.count > 0
                if (!hasRealized && !hasExpected) return null
                const retCol = (realized.ret ?? 0) >= 0 ? C.success : C.danger
                const expCol = (expected.avg_upside_pct ?? 0) >= 0 ? C.success : C.danger
                const topPick = expected.top_picks?.[0]
                return (
                    <Card style={{ borderColor: `${C.accent}40` }}>
                        <CardTitle color={C.accent} right={<Badge text={currentOption?.label || "정기"} color={C.accent} />}>
                            리포트 성과표
                        </CardTitle>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                            {/* 지난 기간 실현 */}
                            <div style={{ background: C.bgElevated, borderRadius: 10, padding: "12px 12px", minWidth: 0 }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 700, marginBottom: 6, fontFamily: FONT, letterSpacing: "0.04em" }}>
                                    지난 기간 실적
                                </div>
                                {hasRealized ? (
                                    <>
                                        <div style={{ color: retCol, fontSize: 22, fontWeight: 900, fontFamily: FONT, lineHeight: 1.1, letterSpacing: "-0.02em" }}>
                                            {(realized.ret ?? 0) >= 0 ? "+" : ""}{Number(realized.ret || 0).toFixed(1)}%
                                        </div>
                                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 6, lineHeight: 1.4 }}>
                                            <b style={{ color: C.textPrimary }}>{realized.total}</b>종목 매수 추천 · 적중률 <b style={{ color: (realized.hit ?? 0) >= 50 ? C.success : C.warn }}>{realized.hit ?? 0}%</b>
                                        </div>
                                    </>
                                ) : (
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, padding: "8px 0" }}>데이터 누적 중</div>
                                )}
                            </div>

                            {/* 이번 리포트 기대 */}
                            <div style={{ background: `${C.accent}10`, borderRadius: 10, padding: "12px 12px", border: `1px solid ${C.accent}30`, minWidth: 0 }}>
                                <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 6, fontFamily: FONT, letterSpacing: "0.04em" }}>
                                    이번 기대수익률
                                </div>
                                {hasExpected ? (
                                    <>
                                        <div style={{ color: expCol, fontSize: 22, fontWeight: 900, fontFamily: FONT, lineHeight: 1.1, letterSpacing: "-0.02em" }}>
                                            {(expected.avg_upside_pct ?? 0) >= 0 ? "+" : ""}{Number(expected.avg_upside_pct || 0).toFixed(1)}%
                                        </div>
                                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 6, lineHeight: 1.4 }}>
                                            <b style={{ color: C.textPrimary }}>{expected.count}</b>종목 · 최대 <b style={{ color: C.accent }}>+{Number(expected.max_upside_pct || 0).toFixed(1)}%</b>
                                        </div>
                                    </>
                                ) : (
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, padding: "8px 0" }}>추천 종목 없음</div>
                                )}
                            </div>
                        </div>
                        {topPick && (
                            <div style={{
                                marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.border}`,
                                display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10,
                            }}>
                                <div style={{ minWidth: 0 }}>
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 700, fontFamily: FONT, letterSpacing: "0.04em", marginBottom: 2 }}>TOP PICK</div>
                                    <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, fontFamily: FONT, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                        {topPick.name} <span style={{ color: C.textSecondary, fontSize: 12, marginLeft: 4 }}>{topPick.ticker}</span>
                                    </div>
                                </div>
                                <div style={{ color: C.accent, fontSize: 16, fontWeight: 900, fontFamily: FONT, flexShrink: 0 }}>
                                    +{Number(topPick.upside_pct || 0).toFixed(1)}%
                                </div>
                            </div>
                        )}
                        <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: FONT, marginTop: 8, lineHeight: 1.4 }}>
                            ※ 기대수익률은 목표가 대비 업사이드이며 실현을 보장하지 않습니다
                        </div>
                    </Card>
                )
            })()}

            {/* Claude 모닝 전략 — 일일 탭에서만 */}
            {hasMorning && (
                <Card style={{ borderColor: `${"#A855F7"}30` }}>
                    <CardTitle color={"#A855F7"} right={<Badge text="Claude AI" color={"#A855F7"} />}>오늘의 전략 시나리오</CardTitle>
                    {morning.scenario && (
                        <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 600, lineHeight: 1.6, fontFamily: FONT, marginBottom: 10 }}>
                            {morning.scenario}
                        </div>
                    )}
                    {morning.watch_points?.length > 0 && (
                        <div style={{ paddingTop: 8, borderTop: `1px solid ${C.border}` }}>
                            <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 6, fontFamily: FONT, letterSpacing: "0.04em", textTransform: "uppercase" as const }}>관찰 포인트</div>
                            {morning.watch_points.map((w: string, i: number) => (
                                <div key={i} style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5, marginBottom: 4 }}>· {w}</div>
                            ))}
                        </div>
                    )}
                    {morning.top_pick_comment && (
                        <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px", marginTop: 10 }}>
                            <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 4, fontFamily: FONT, letterSpacing: "0.04em", textTransform: "uppercase" as const }}>TOP PICK 코멘트</div>
                            <div style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>{morning.top_pick_comment}</div>
                        </div>
                    )}
                    {morning.risk_note && (
                        <div style={{ color: C.warn, fontSize: 12, fontFamily: FONT, lineHeight: 1.5, marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.border}` }}>
                            ⚠ <b>리스크:</b> {morning.risk_note}
                        </div>
                    )}
                </Card>
            )}

            <Card>
                <CardTitle>국내 시장</CardTitle>
                {report.market_summary && (
                    <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700, lineHeight: 1.5, fontFamily: FONT, marginBottom: 8 }}>{report.market_summary}</div>
                )}
                {!isDaily && (report as any).executive_summary && (
                    <div style={{ background: `${C.accent}10`, borderLeft: `3px solid ${C.accent}`, borderRadius: 6, padding: "10px 12px", marginBottom: 10 }}>
                        <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 4, fontFamily: FONT }}>EXECUTIVE SUMMARY</div>
                        <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.6, fontFamily: FONT }}>{(report as any).executive_summary}</div>
                    </div>
                )}
                {!isDaily && (report as any).performance_review && (
                    <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px", marginBottom: 8 }}>
                        <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 4, fontFamily: FONT }}>성과 복기</div>
                        <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.6, fontFamily: FONT }}>{(report as any).performance_review}</div>
                    </div>
                )}
                {!isDaily && (report as any).sector_analysis && (
                    <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px", marginBottom: 8 }}>
                        <div style={{ color: C.info, fontSize: 12, fontWeight: 700, marginBottom: 4, fontFamily: FONT }}>섹터 분석</div>
                        <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.6, fontFamily: FONT }}>{(report as any).sector_analysis}</div>
                    </div>
                )}
                {!isDaily && (report as any).macro_outlook && (
                    <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px", marginBottom: 8 }}>
                        <div style={{ color: "#A855F7", fontSize: 12, fontWeight: 700, marginBottom: 4, fontFamily: FONT }}>매크로 전망</div>
                        <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.6, fontFamily: FONT }}>{(report as any).macro_outlook}</div>
                    </div>
                )}
                {!isDaily && (report as any).brain_review && (
                    <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px", marginBottom: 8 }}>
                        <div style={{ color: "#A855F7", fontSize: 12, fontWeight: 700, marginBottom: 4, fontFamily: FONT }}>브레인 복기</div>
                        <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.6, fontFamily: FONT }}>{(report as any).brain_review}</div>
                    </div>
                )}
                {report.market_analysis && (
                    <div style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.6, fontFamily: FONT, marginBottom: 8 }}>{report.market_analysis}</div>
                )}
                {report.strategy && (
                    <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px", marginBottom: 6 }}>
                        <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 4, fontFamily: FONT }}>전략</div>
                        <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.5, fontFamily: FONT }}>{report.strategy}</div>
                    </div>
                )}
                {report.risk_watch && (
                    <div style={{ background: `${C.warn}10`, borderRadius: 10, padding: "10px 12px", marginTop: 8 }}>
                        <div style={{ color: C.warn, fontSize: 12, fontWeight: 700, marginBottom: 4, fontFamily: FONT }}>RISK WATCH</div>
                        <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.5, fontFamily: FONT }}>{report.risk_watch}</div>
                    </div>
                )}
                {isDaily && report.tomorrow_outlook && (
                    <div style={{ background: `${C.info}10`, borderRadius: 10, padding: "10px 12px", marginTop: 8 }}>
                        <div style={{ color: C.info, fontSize: 12, fontWeight: 700, marginBottom: 4, fontFamily: FONT }}>TOMORROW</div>
                        <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.5, fontFamily: FONT }}>{report.tomorrow_outlook}</div>
                    </div>
                )}
                {isDaily && report.hot_theme && <div style={{ color: C.warn, fontSize: 12, fontFamily: FONT, marginTop: 8 }}>🔥 {report.hot_theme}</div>}
            </Card>

            {/* 주기 리포트 META 인사이트 */}
            {!isDaily && (report as any).meta_insight && (
                <Card style={{ borderColor: `${"#A855F7"}30` }}>
                    <CardTitle color={"#A855F7"}>META 인사이트</CardTitle>
                    <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.7, fontFamily: FONT, whiteSpace: "pre-wrap" as const }}>
                        {(report as any).meta_insight}
                    </div>
                </Card>
            )}

            {(reportUS.market_summary || reportUS.strategy) && (
                <Card>
                    <CardTitle color={C.info}>미국 시장</CardTitle>
                    {reportUS.market_summary && (
                        <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700, lineHeight: 1.5, fontFamily: FONT, marginBottom: 8 }}>{reportUS.market_summary}</div>
                    )}
                    {reportUS.market_analysis && (
                        <div style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.6, fontFamily: FONT, marginBottom: 8 }}>{reportUS.market_analysis}</div>
                    )}
                    {reportUS.strategy && (
                        <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                            <div style={{ color: C.info, fontSize: 12, fontWeight: 700, marginBottom: 4, fontFamily: FONT }}>전략</div>
                            <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.5, fontFamily: FONT }}>{reportUS.strategy}</div>
                        </div>
                    )}
                </Card>
            )}

            {/* Cross Verification — AI 간 이견 (일일 한정) */}
            {isDaily && crossVerify.disagreements?.length > 0 && (
                <Card style={{ borderColor: `${C.warn}30` }}>
                    <CardTitle color={C.warn} right={<Badge text={`${crossVerify.override_count || 0}건 변경`} color={C.warn} />}>AI 이견 리포트</CardTitle>
                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 10 }}>
                        {crossVerify.total_analyzed}개 종목 중 Gemini와 Claude가 다르게 판단
                    </div>
                    {crossVerify.disagreements.slice(0, 3).map((d: any, i: number, arr: any[]) => (
                        <div key={i} style={{
                            padding: "10px 0", borderBottom: i < Math.min(arr.length, 3) - 1 ? `1px solid ${C.border}` : "none",
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                                <span style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, fontFamily: FONT }}>{d.name}</span>
                                <div style={{ display: "flex", gap: 4 }}>
                                    <Badge text={`Gemini ${GRADE_LABEL[d.gemini_rec] || d.gemini_rec}`} color={GRADE_COLOR[d.gemini_rec] || C.textSecondary} />
                                    <Badge text={`Claude ${GRADE_LABEL[d.claude_rec] || d.claude_rec}`} color={GRADE_COLOR[d.claude_rec] || C.textSecondary} />
                                </div>
                            </div>
                            {d.reason && (
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>{d.reason}</div>
                            )}
                        </div>
                    ))}
                </Card>
            )}

            {/* Postmortem — 실패 복기 */}
            {postmortem.status && (
                <Card>
                    <CardTitle color={postmortem.status === "clean" ? C.success : C.danger}>AI 복기</CardTitle>
                    {postmortem.status === "clean" ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ fontSize: 22 }}>✓</span>
                            <div>
                                <div style={{ color: C.success, fontSize: 13, fontWeight: 700, fontFamily: FONT }}>{postmortem.message || "최근 유의미한 오심 없음"}</div>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>최근 7일 기준</div>
                            </div>
                        </div>
                    ) : (
                        <>
                            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 8 }}>{postmortem.message}</div>
                            {postmortem.failures?.slice(0, 3).map((f: any, i: number, arr: any[]) => (
                                <div key={i} style={{
                                    padding: "8px 0", borderBottom: i < Math.min(arr.length, 3) - 1 ? `1px solid ${C.border}` : "none",
                                }}>
                                    <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>{f.name || f.ticker}</div>
                                    <div style={{ color: C.danger, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>{f.reason || f.summary}</div>
                                </div>
                            ))}
                        </>
                    )}
                </Card>
            )}

            {/* Factor IC — 주기 리포트에서만 */}
            {!isDaily && factorIC.ranking?.length > 0 && (
                <Card>
                    <CardTitle color={C.info}>팩터 효용도 (IC)</CardTitle>
                    {factorIC.significant_factors?.length > 0 && (
                        <div style={{ display: "flex", gap: 4, marginBottom: 10, flexWrap: "wrap" }}>
                            <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginRight: 4 }}>유효:</span>
                            {factorIC.significant_factors.map((f: string, i: number) => (
                                <Badge key={i} text={f} color={C.success} />
                            ))}
                        </div>
                    )}
                    {factorIC.ranking.slice(0, 5).map((f: any, i: number, arr: any[]) => {
                        const v = f.icir ?? f.ic ?? 0
                        const col = v > 0.1 ? C.success : v < -0.1 ? C.danger : C.textSecondary
                        return (
                            <div key={i} style={{
                                display: "flex", justifyContent: "space-between", alignItems: "center",
                                padding: "7px 0", borderBottom: i < Math.min(arr.length, 5) - 1 ? `1px solid ${C.border}` : "none",
                            }}>
                                <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT }}>{f.factor}</span>
                                <span style={{ color: col, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                                    {v >= 0 ? "+" : ""}{Number(v).toFixed(3)}
                                </span>
                            </div>
                        )
                    })}
                </Card>
            )}

            {brain.avg_score != null && (
                <Card>
                    <CardTitle color={"#A855F7"} right={brain.market_bias && <Badge text={brain.market_bias} color={"#A855F7"} />}>VERITY Brain 종합</CardTitle>
                    <div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 12 }}>
                        <RingGauge value={brain.avg_score} size={68} color={"#A855F7"} strokeWidth={5} label="평균" />
                        {brain.grade_distribution && (
                            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 3 }}>
                                {Object.entries(brain.grade_distribution).map(([k, v]: any) => {
                                    const total: number = Object.values(brain.grade_distribution).reduce((a: number, b: any) => a + Number(b), 0) as number
                                    const pct = total > 0 ? (Number(v) / total) * 100 : 0
                                    return (
                                        <div key={k} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                            <span style={{ color: GRADE_COLOR[k] || C.textSecondary, fontSize: 12, fontWeight: 700, fontFamily: FONT, width: 48 }}>{GRADE_LABEL[k] || k}</span>
                                            <div style={{ flex: 1, height: 4, background: C.border, borderRadius: 2, overflow: "hidden" }}>
                                                <div style={{ height: "100%", width: `${pct}%`, background: GRADE_COLOR[k] || C.textSecondary }} />
                                            </div>
                                            <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT, width: 22, textAlign: "right" }}>{v}</span>
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                    </div>
                    {brain.top_picks?.length > 0 && (
                        <>
                            <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, marginBottom: 6, fontFamily: FONT, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>TOP PICKS</div>
                            {brain.top_picks.slice(0, 5).map((p: any, i: number, arr: any[]) => (
                                <div key={i} style={{
                                    display: "flex", justifyContent: "space-between", alignItems: "center",
                                    padding: "7px 0", borderBottom: i < arr.length - 1 ? `1px solid ${C.border}` : "none",
                                }}>
                                    <div style={{ minWidth: 0, flex: 1 }}>
                                        <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>{p.name || p.ticker}</span>
                                        <span style={{ color: C.textSecondary, fontSize: 12, marginLeft: 6, fontFamily: FONT }}>{p.ticker}</span>
                                    </div>
                                    <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
                                        <Badge text={GRADE_LABEL[p.grade] || p.grade} color={GRADE_COLOR[p.grade] || C.textSecondary} />
                                        <span style={{ color: C.textPrimary, fontSize: 13, fontWeight: 800, fontFamily: FONT, minWidth: 24, textAlign: "right" }}>{p.brain_score || p.score}</span>
                                    </div>
                                </div>
                            ))}
                        </>
                    )}
                </Card>
            )}

            {leader.by_source?.length > 0 && (
                <Card>
                    <CardTitle right={<span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{leader.window_days}일</span>}>AI 리더보드</CardTitle>
                    {leader.by_source.map((s: any, i: number, arr: any[]) => (
                        <div key={i} style={{
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                            padding: "10px 0", borderBottom: i < arr.length - 1 ? `1px solid ${C.border}` : "none",
                        }}>
                            <span style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, fontFamily: FONT, textTransform: "capitalize" as const }}>{s.source}</span>
                            <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
                                <div style={{ textAlign: "center" }}>
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>적중</div>
                                    <div style={{ color: C.success, fontSize: 12, fontWeight: 800, fontFamily: FONT }}>{s.hit_rate?.toFixed(0)}%</div>
                                </div>
                                <div style={{ textAlign: "center" }}>
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>수익</div>
                                    <div style={{ color: (s.avg_return ?? 0) >= 0 ? C.success : C.danger, fontSize: 12, fontWeight: 800, fontFamily: FONT }}>
                                        {(s.avg_return ?? 0) >= 0 ? "+" : ""}{s.avg_return?.toFixed(1)}%
                                    </div>
                                </div>
                                <div style={{ textAlign: "center" }}>
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>샤프</div>
                                    <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 800, fontFamily: FONT }}>{s.sharpe?.toFixed(2)}</div>
                                </div>
                            </div>
                        </div>
                    ))}
                </Card>
            )}
        </div>
    )
}

/* ══════════════════════════════════════════════════════════════════
   MORE TAB
   ══════════════════════════════════════════════════════════════════ */
function InlineAuth({ supabaseUrl, supabaseAnonKey, onAuthChange }: { supabaseUrl: string; supabaseAnonKey: string; onAuthChange: (s: AuthSession | null) => void }) {
    const [mode, setMode] = useState<"login" | "signup">("login")
    const [email, setEmail] = useState("")
    const [password, setPassword] = useState("")
    const [displayName, setDisplayName] = useState("")
    const [phone, setPhone] = useState("")
    const [consent, setConsent] = useState(false)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState("")
    const [success, setSuccess] = useState("")

    const submit = useCallback(async () => {
        if (!supabaseUrl || !supabaseAnonKey) { setError("Supabase 설정이 필요합니다"); return }
        if (password.length < 6) { setError("비밀번호는 6자 이상 입력해주세요"); return }
        if (mode === "signup") {
            if (!displayName.trim()) { setError("이름을 입력해주세요"); return }
            if (!phone.trim()) { setError("전화번호를 입력해주세요"); return }
            if (!consent) { setError("개인정보 수집·이용에 동의해주세요"); return }
        }
        setLoading(true); setError(""); setSuccess("")
        try {
            if (mode === "signup") {
                const r = await _mobileSignUp(supabaseUrl, supabaseAnonKey, email, password, displayName, {
                    phone: phone.trim(), consent,
                })
                setSuccess(r === "email_confirm"
                    ? "가입 요청 접수. 이메일 확인 후 관리자 승인을 기다려주세요."
                    : "가입 신청이 접수되었습니다. 관리자 승인 후 로그인 가능합니다.")
                setPassword(""); setPhone(""); setConsent(false)
                setMode("login")
            } else {
                const s = await _mobileSignIn(supabaseUrl, supabaseAnonKey, email, password)
                onAuthChange(s)
            }
        } catch (e: any) {
            setError(e?.message || "오류가 발생했습니다")
        } finally { setLoading(false) }
    }, [mode, email, password, displayName, phone, consent, supabaseUrl, supabaseAnonKey, onAuthChange])

    const inputStyle: React.CSSProperties = {
        width: "100%", padding: "11px 13px", borderRadius: 10,
        border: `1px solid ${C.border}`, background: C.bgElevated, color: C.textPrimary,
        fontSize: 13, fontFamily: FONT, outline: "none", boxSizing: "border-box",
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", gap: 0, borderRadius: 10, overflow: "hidden", border: `1px solid ${C.border}` }}>
                {(["login", "signup"] as const).map((m) => (
                    <button key={m} onClick={() => { setMode(m); setError(""); setSuccess("") }} style={{
                        flex: 1, border: "none", padding: "9px 0",
                        background: mode === m ? C.accent : "transparent",
                        color: mode === m ? "#000" : C.textSecondary,
                        fontSize: 12, fontWeight: 700, fontFamily: FONT, cursor: "pointer",
                    }}>{m === "login" ? "로그인" : "가입 신청"}</button>
                ))}
            </div>

            {mode === "signup" && (
                <div style={{ padding: "8px 11px", borderRadius: 8, background: `${C.accent}10`, border: `1px solid ${C.accent}25` }}>
                    <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, fontFamily: FONT, marginBottom: 2 }}>승인제 가입</div>
                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                        가입 신청 후 관리자 승인이 완료되어야 로그인할 수 있습니다.
                    </div>
                </div>
            )}

            {mode === "signup" && (
                <input type="text" placeholder="이름" value={displayName} onChange={(e) => setDisplayName(e.target.value)} style={inputStyle} />
            )}
            <input type="email" placeholder="이메일" value={email} onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} style={inputStyle} />
            <input type="password" placeholder="비밀번호 (6자 이상)" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} style={inputStyle} />

            {mode === "signup" && (
                <>
                    <input type="tel" placeholder="전화번호 (010-1234-5678)" value={phone} onChange={(e) => setPhone(e.target.value)} style={inputStyle} />
                    <label style={{
                        display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer",
                        padding: "9px 11px", borderRadius: 8,
                        background: C.bgElevated, border: `1px solid ${consent ? C.accent : C.border}`,
                    }}>
                        <input
                            type="checkbox"
                            checked={consent}
                            onChange={(e) => setConsent(e.target.checked)}
                            style={{ marginTop: 2, width: 15, height: 15, accentColor: C.accent as string, cursor: "pointer", flexShrink: 0 }}
                        />
                        <div style={{ flex: 1 }}>
                            <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT, marginBottom: 2 }}>
                                개인정보 수집·이용 동의 (필수)
                            </div>
                            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                                이메일·이름·전화번호. 회원 식별·승인·서비스 제공 목적. 탈퇴 시 삭제.
                            </div>
                        </div>
                    </label>
                </>
            )}

            {error && (
                <div style={{ padding: "8px 11px", borderRadius: 8, background: `${C.danger}15`, border: `1px solid ${C.danger}30` }}>
                    <span style={{ color: C.danger, fontSize: 12, fontFamily: FONT }}>{error}</span>
                </div>
            )}
            {success && (
                <div style={{ padding: "8px 11px", borderRadius: 8, background: `${C.success}15`, border: `1px solid ${C.success}30` }}>
                    <span style={{ color: C.success, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>{success}</span>
                </div>
            )}

            <button onClick={submit} disabled={loading || !email || !password} style={{
                width: "100%", padding: "11px 0", borderRadius: 10, border: "none",
                background: C.accent, color: "#000", fontSize: 13, fontWeight: 800, fontFamily: FONT,
                cursor: (loading || !email || !password) ? "not-allowed" : "pointer",
                opacity: (loading || !email || !password) ? 0.5 : 1,
            }}>{loading ? "처리 중..." : mode === "login" ? "로그인" : "가입 신청"}</button>
        </div>
    )
}

function MoreTab({ data, session, onLogout, onAuthChange, supabaseUrl, supabaseAnonKey }: { data: any; session: AuthSession | null; onLogout: () => void; onAuthChange: (s: AuthSession | null) => void; supabaseUrl: string; supabaseAnonKey: string }) {
    const [section, setSection] = useState<"events" | "news" | "sec" | "alerts" | "settings">("events")
    const [newsRegion, setNewsRegion] = useState<"all" | "kr" | "us">("all")
    const events: any[] = data?.global_events || []
    const expiry = data?.expiry_status || {}
    const krNews = data?.headlines || []
    const usNews = data?.us_headlines || []
    const allNews = newsRegion === "kr" ? krNews : newsRegion === "us" ? usNews : [...krNews, ...usNews]
    const allAlerts: any[] = data?.briefing?.alerts || []
    const secRisk = data?.sec_risk_scan || {}
    const secFilings: any[] = secRisk.filings || []
    const dailyReport = data?.daily_report || {}

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", padding: "0 2px" }}>
                {([["events", "경제지표"], ["news", "뉴스"], ["sec", `SEC ${secRisk.count || 0}`], ["alerts", "알림이력"], ["settings", "설정"]] as const).map(([k, l]) => (
                    <Pill key={k} label={l} active={section === k} onClick={() => setSection(k)} />
                ))}
            </div>

            {section === "events" && (
                <>
                    {/* 옵션·선물 만기 요약 */}
                    {(expiry.next_kr_expiry || expiry.next_us_expiry) && (
                        <Card>
                            <CardTitle color={C.warn}>파생상품 만기</CardTitle>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                                {expiry.next_kr_expiry && (
                                    <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 4 }}>국내 다음 만기</div>
                                        <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>{expiry.next_kr_expiry}</div>
                                        {expiry.kr_days_left != null && (
                                            <div style={{ color: C.warn, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>D-{expiry.kr_days_left}</div>
                                        )}
                                    </div>
                                )}
                                {expiry.next_us_expiry && (
                                    <div style={{ background: C.bgElevated, borderRadius: 10, padding: "10px 12px" }}>
                                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 4 }}>미국 다음 만기</div>
                                        <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>{expiry.next_us_expiry}</div>
                                        {expiry.us_days_left != null && (
                                            <div style={{ color: C.warn, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>D-{expiry.us_days_left}</div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </Card>
                    )}

                    {/* 오늘의 주요 이벤트 (daily_report) */}
                    {(dailyReport.hot_theme || dailyReport.tomorrow_outlook) && (
                        <Card>
                            <CardTitle>리포트 이벤트</CardTitle>
                            {dailyReport.hot_theme && (
                                <div style={{ color: C.warn, fontSize: 12, fontFamily: FONT, lineHeight: 1.5, marginBottom: 8 }}>🔥 {dailyReport.hot_theme}</div>
                            )}
                            {dailyReport.tomorrow_outlook && (
                                <div style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                                    <span style={{ color: C.info, fontWeight: 700, marginRight: 4 }}>내일 ›</span>{dailyReport.tomorrow_outlook}
                                </div>
                            )}
                        </Card>
                    )}

                    {events.length > 0 && (
                        <>
                            <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 700, padding: "4px 4px 0", fontFamily: FONT, letterSpacing: "0.04em" }}>글로벌 이벤트</div>
                            {events.map((e: any, i: number) => (
                                <Card key={i} style={{ padding: "12px 16px" }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, fontFamily: FONT }}>{e.name || e.event}</div>
                                            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>{e.date} · {e.country || "글로벌"}</div>
                                            {e.impact && <div style={{ color: C.warn, fontSize: 12, fontFamily: FONT, marginTop: 4, lineHeight: 1.5 }}>{e.impact}</div>}
                                        </div>
                                        {e.severity && <Badge text={e.severity} color={e.severity === "high" ? C.danger : e.severity === "medium" ? C.warn : C.textSecondary} />}
                                    </div>
                                </Card>
                            ))}
                        </>
                    )}

                    {events.length === 0 && !expiry.next_kr_expiry && !expiry.next_us_expiry && !dailyReport.hot_theme && (
                        <div style={{ textAlign: "center", padding: 40, color: C.textSecondary, fontSize: 13, fontFamily: FONT }}>예정된 이벤트가 없습니다</div>
                    )}
                </>
            )}

            {section === "news" && (
                <>
                    <div style={{ display: "flex", gap: 6, padding: "0 2px" }}>
                        {([["all", `전체 ${krNews.length + usNews.length}`], ["kr", `국내 ${krNews.length}`], ["us", `해외 ${usNews.length}`]] as const).map(([k, l]) => (
                            <button key={k} onClick={() => setNewsRegion(k)} style={{
                                border: "none", padding: "5px 12px", borderRadius: 16,
                                fontSize: 12, fontWeight: newsRegion === k ? 800 : 600, fontFamily: FONT, cursor: "pointer",
                                background: newsRegion === k ? C.accent : C.bgCard,
                                color: newsRegion === k ? "#000" : C.textSecondary,
                            }}>{l}</button>
                        ))}
                    </div>
                    {allNews.length > 0 ? allNews.slice(0, 25).map((h: any, i: number) => {
                        const sc = h.sentiment === "positive" ? C.success : h.sentiment === "negative" ? C.danger : C.textSecondary
                        const sl = h.sentiment === "positive" ? "호재" : h.sentiment === "negative" ? "악재" : "중립"
                        const inner = (
                            <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                                <Badge text={sl} color={sc} />
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 600, lineHeight: 1.5, fontFamily: FONT }}>{h.title}</div>
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 4 }}>{h.source || ""} {h.time || h.date ? `· ${h.time || h.date}` : ""}</div>
                                </div>
                                {h.link && (
                                    <span style={{ color: C.textSecondary, fontSize: 14, flexShrink: 0, marginLeft: 4 }}>↗</span>
                                )}
                            </div>
                        )
                        return h.link ? (
                            <a key={i} href={h.link} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none" }}>
                                <Card style={{ padding: "12px 16px" }}>{inner}</Card>
                            </a>
                        ) : (
                            <Card key={i} style={{ padding: "12px 16px" }}>{inner}</Card>
                        )
                    }) : <div style={{ textAlign: "center", padding: 40, color: C.textSecondary, fontSize: 13, fontFamily: FONT }}>뉴스가 없습니다</div>}
                </>
            )}

            {section === "sec" && (
                <>
                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, padding: "0 4px", lineHeight: 1.5 }}>
                        SEC 공시에서 감지된 리스크 키워드. 미국 보유 종목이 있다면 주의 깊게 확인하세요.
                        {secRisk.date_range && <div style={{ color: C.textSecondary, fontSize: 12, marginTop: 4 }}>{secRisk.date_range}</div>}
                    </div>
                    {secFilings.length > 0 ? secFilings.slice(0, 20).map((f: any, i: number) => {
                        const inner = (
                            <>
                                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                                    <Badge text={f.keyword_matched} color={C.danger} />
                                    <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{f.form_type}</span>
                                    <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginLeft: "auto" }}>{f.filed_date}</span>
                                </div>
                                <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600, fontFamily: FONT, lineHeight: 1.4 }}>{f.company}</div>
                                {f.description && (
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 4, lineHeight: 1.5 }}>{f.description}</div>
                                )}
                            </>
                        )
                        return f.url ? (
                            <a key={i} href={f.url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none" }}>
                                <Card style={{ padding: "12px 16px", borderColor: `${C.danger}30` }}>{inner}</Card>
                            </a>
                        ) : (
                            <Card key={i} style={{ padding: "12px 16px", borderColor: `${C.danger}30` }}>{inner}</Card>
                        )
                    }) : <div style={{ textAlign: "center", padding: 40, color: C.textSecondary, fontSize: 13, fontFamily: FONT }}>감지된 SEC 리스크가 없습니다</div>}
                </>
            )}

            {section === "alerts" && (allAlerts.length > 0 ? allAlerts.map((a: any, i: number) => {
                const lc = LEVEL_COLOR[a.level] || C.textSecondary
                return (
                    <Card key={i} style={{ padding: "12px 16px", borderColor: `${lc}30` }}>
                        <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
                            <Badge text={a.level} color={lc} />
                            <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{a.category}</span>
                        </div>
                        <div style={{ color: C.textPrimary, fontSize: 12, lineHeight: 1.5, fontFamily: FONT }}>{a.message}</div>
                        {a.action && <div style={{ color: lc, fontSize: 12, marginTop: 4, fontFamily: FONT }}>{a.action}</div>}
                    </Card>
                )
            }) : <div style={{ textAlign: "center", padding: 40, color: C.textSecondary, fontSize: 13, fontFamily: FONT }}>알림 이력이 없습니다</div>)}

            {section === "settings" && (
                <>
                    <Card>
                        <CardTitle>계정</CardTitle>
                        {session ? (
                            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 12, paddingBottom: 12, borderBottom: `1px solid ${C.border}` }}>
                                    <div style={{ width: 44, height: 44, borderRadius: "50%", background: `${C.accent}20`, border: `2px solid ${C.accent}`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                                        <span style={{ color: C.accent, fontSize: 18, fontWeight: 800, fontFamily: FONT }}>{(session.user.user_metadata?.name || session.user.email || "U").charAt(0).toUpperCase()}</span>
                                    </div>
                                    <div style={{ minWidth: 0 }}>
                                        <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700, fontFamily: FONT }}>{session.user.user_metadata?.name || session.user.email?.split("@")[0]}</div>
                                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{session.user.email}</div>
                                    </div>
                                </div>
                                <button onClick={onLogout} style={{
                                    width: "100%", padding: "11px 0", borderRadius: 10,
                                    border: `1px solid ${C.danger}40`, background: `${C.danger}10`,
                                    color: C.danger, fontSize: 13, fontWeight: 700, fontFamily: FONT, cursor: "pointer",
                                }}>로그아웃</button>
                            </div>
                        ) : supabaseUrl && supabaseAnonKey ? (
                            <InlineAuth supabaseUrl={supabaseUrl} supabaseAnonKey={supabaseAnonKey} onAuthChange={onAuthChange} />
                        ) : (
                            <div style={{ textAlign: "center", padding: "8px 0" }}>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginBottom: 6 }}>
                                    Supabase 설정이 필요합니다
                                </div>
                                <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>
                                    프로퍼티에서 Supabase URL과 Anon Key를 입력해주세요
                                </span>
                            </div>
                        )}
                    </Card>

                    <Card>
                        <CardTitle>시스템</CardTitle>
                        {[
                            ["버전", data?.system_health?.version || "—"],
                            ["마지막 업데이트", data?.updated_at ? new Date(data.updated_at).toLocaleString("ko-KR") : "—"],
                            ["데이터 포인트", `${Object.keys(data || {}).length}개 섹션`],
                        ].map(([label, value], i) => (
                            <div key={i} style={{
                                display: "flex", justifyContent: "space-between", alignItems: "center",
                                padding: "12px 0", borderBottom: `1px solid ${C.border}`,
                            }}>
                                <span style={{ color: C.textPrimary, fontSize: 14, fontFamily: FONT }}>{label}</span>
                                <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>{value}</span>
                            </div>
                        ))}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0" }}>
                            <span style={{ color: C.textPrimary, fontSize: 14, fontFamily: FONT }}>시스템 상태</span>
                            <Badge text={data?.system_health?.status === "ok" ? "정상" : "점검 중"} color={data?.system_health?.status === "ok" ? C.success : C.warn} />
                        </div>
                    </Card>
                </>
            )}
        </div>
    )
}

/* ══════════════════════════════════════════════════════════════════
   MAIN SHELL
   ══════════════════════════════════════════════════════════════════ */
export default function MobileApp(props: Props) {
    const { dataUrl, refreshIntervalSec = 180, defaultTab = "home", supabaseUrl = "", supabaseAnonKey = "", chatApiUrl = CHAT_API } = props
    const [tab, setTab] = useState<TabId>(defaultTab)
    const [data, setData] = useState<any>(null)
    const [loadError, setLoadError] = useState<string | null>(null)
    const [session, setSession] = useState<AuthSession | null>(null)
    const scrollRef = useRef<HTMLDivElement>(null)

    // 자동 로그인: mount 시 세션 로드 + 필요 시 refresh_token 으로 갱신
    useEffect(() => {
        const raw = _loadSessionRaw()
        if (!raw) return
        const now = Date.now() / 1000
        const nearExpiry = raw.expires_at && now > raw.expires_at - 300
        if (nearExpiry) {
            if (supabaseUrl && supabaseAnonKey && raw.refresh_token) {
                _refreshSession(supabaseUrl, supabaseAnonKey, raw.refresh_token).then((s) => {
                    if (s) setSession(s)
                    else { _clearSession(); setSession(null) }
                })
            } else {
                _clearSession()
            }
        } else {
            setSession(raw)
        }
    }, [supabaseUrl, supabaseAnonKey])

    // 주기적 refresh: 5분 이내 만료 시 갱신
    useEffect(() => {
        if (!session || !supabaseUrl || !supabaseAnonKey) return
        const id = globalThis.setInterval(() => {
            const cur = _loadSessionRaw()
            if (!cur?.refresh_token) return
            const now = Date.now() / 1000
            if (cur.expires_at && now > cur.expires_at - 300) {
                _refreshSession(supabaseUrl, supabaseAnonKey, cur.refresh_token).then((s) => {
                    if (s) setSession(s)
                })
            }
        }, 60 * 1000)
        return () => globalThis.clearInterval(id)
    }, [session, supabaseUrl, supabaseAnonKey])

    useEffect(() => {
        if (!dataUrl) { setLoadError("dataUrl이 비어 있습니다"); return }
        const ac = new AbortController()
        const load = () => fetchPortfolioJson(dataUrl, ac.signal)
            .then((d) => { if (!ac.signal.aborted) { setData(d); setLoadError(null) } })
            .catch((e) => { if (!ac.signal.aborted) setLoadError(e?.message || "fetch 실패") })
        load()
        const sec = Math.max(30, Number(refreshIntervalSec) || 180)
        const id = globalThis.setInterval(load, sec * 1000)
        return () => { ac.abort(); globalThis.clearInterval(id) }
    }, [dataUrl, refreshIntervalSec])

    useEffect(() => { scrollRef.current?.scrollTo(0, 0) }, [tab])

    const handleLogout = useCallback(() => {
        if (session && supabaseUrl && supabaseAnonKey) {
            fetch(`${supabaseUrl}/auth/v1/logout`, {
                method: "POST",
                headers: { "Content-Type": "application/json", apikey: supabaseAnonKey, Authorization: `Bearer ${session.access_token}` },
            }).catch(() => {})
        }
        _clearSession()
        setSession(null)
    }, [session, supabaseUrl, supabaseAnonKey])

    const renderTab = () => {
        if (!data) {
            return (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 300 }}>
                    <div style={{ textAlign: "center" }}>
                        {loadError ? (
                            <>
                                <div style={{ color: C.danger, fontSize: 22, marginBottom: 8 }}>⚠</div>
                                <div style={{ color: C.danger, fontSize: 13, fontFamily: FONT, fontWeight: 700, marginBottom: 4 }}>데이터 로딩 실패</div>
                                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>{loadError}</div>
                            </>
                        ) : (
                            <>
                                <div style={{
                                    width: 40, height: 40, border: `3px solid ${C.border}`, borderTopColor: C.accent,
                                    borderRadius: "50%", margin: "0 auto 12px",
                                    animation: "spin 1s linear infinite",
                                }} />
                                <div style={{ color: C.textSecondary, fontSize: 13, fontFamily: FONT }}>데이터 로딩 중...</div>
                            </>
                        )}
                    </div>
                </div>
            )
        }
        switch (tab) {
            case "home": return <ErrorBoundary label="HomeTab"><HomeTab data={data} session={session} /></ErrorBoundary>
            case "market": return <ErrorBoundary label="MarketTab"><MarketTab data={data} /></ErrorBoundary>
            case "reco": return <ErrorBoundary label="RecoTab"><RecoTab data={data} /></ErrorBoundary>
            case "ai": return <ErrorBoundary label="AITab"><AITab data={data} chatApiUrl={chatApiUrl} /></ErrorBoundary>
            case "more": return <ErrorBoundary label="MoreTab"><MoreTab data={data} session={session} onLogout={handleLogout} onAuthChange={setSession} supabaseUrl={supabaseUrl} supabaseAnonKey={supabaseAnonKey} /></ErrorBoundary>
        }
    }

    // ─── 하드 게이트: 미로그인 시 로그인 화면만 표시 ───
    if (!session) {
        return (
            <div style={{
                width: "100%", height: "100%", minHeight: "100vh",
                background: C.bgPage, fontFamily: FONT,
                display: "flex", alignItems: "center", justifyContent: "center",
                padding: "24px 18px", boxSizing: "border-box",
            }}>
                <div style={{ width: "100%", maxWidth: 380, display: "flex", flexDirection: "column", gap: 20 }}>
                    {/* 브랜딩 */}
                    <div style={{ textAlign: "center", marginBottom: 4 }}>
                        <div style={{ color: C.accent, fontSize: 30, fontWeight: 900, fontFamily: FONT, letterSpacing: "-0.03em" }}>
                            VERITY
                        </div>
                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 6 }}>
                            AI 자산 보안 비서
                        </div>
                    </div>

                    {supabaseUrl && supabaseAnonKey ? (
                        <div style={{
                            background: C.bgCard, borderRadius: 18, border: `1px solid ${C.border}`,
                            padding: "22px 18px",
                        }}>
                            <InlineAuth
                                supabaseUrl={supabaseUrl}
                                supabaseAnonKey={supabaseAnonKey}
                                onAuthChange={setSession}
                            />
                        </div>
                    ) : (
                        <div style={{
                            background: C.bgCard, borderRadius: 14, border: `1px solid ${C.danger}40`,
                            padding: "16px 18px", textAlign: "center",
                        }}>
                            <div style={{ color: C.danger, fontSize: 13, fontWeight: 700, fontFamily: FONT, marginBottom: 6 }}>
                                Supabase 설정이 필요합니다
                            </div>
                            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                                Framer 프로퍼티에서 Supabase URL과 Anon Key를 입력해주세요
                            </div>
                        </div>
                    )}

                    <div style={{ textAlign: "center", color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.6 }}>
                        승인제로 운영됩니다.<br />가입 후 관리자 승인까지 시간이 걸릴 수 있습니다.
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div style={{
            width: "100%", height: "100%", minHeight: "100vh",
            background: C.bgPage, fontFamily: FONT,
            display: "flex", flexDirection: "column",
            position: "relative",
        }}>
            <style>{`
                @keyframes spin { to { transform: rotate(360deg) } }
                @keyframes slideUp { from { transform: translateY(100%) } to { transform: translateY(0) } }
            `}</style>

            <div ref={scrollRef} style={{
                flex: 1, overflowY: "auto", overflowX: "hidden",
                padding: "22px 14px 80px",
                WebkitOverflowScrolling: "touch",
                minHeight: 0,
            }}>
                <ErrorBoundary label="MobileApp">{renderTab()}</ErrorBoundary>
            </div>

            <div style={{
                position: "sticky", bottom: 0, left: 0, right: 0, zIndex: 900,
                flexShrink: 0,
                background: "rgba(0,0,0,0.92)", backdropFilter: "blur(12px)",
                WebkitBackdropFilter: "blur(12px)",
                borderTop: `1px solid ${C.border}`,
                display: "flex", justifyContent: "space-around", alignItems: "center",
                padding: "10px 0 calc(env(safe-area-inset-bottom, 0px) + 14px)",
                minHeight: 64,
            }}>
                {(["home", "market", "reco", "ai", "more"] as TabId[]).map((t) => {
                    const active = tab === t
                    return (
                        <button key={t} onClick={() => setTab(t)} style={{
                            border: "none", background: "transparent", cursor: "pointer",
                            display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
                            padding: "4px 12px", minWidth: 48,
                            transition: "transform 0.15s",
                            transform: active ? "scale(1.08)" : "scale(1)",
                        }}>
                            {TAB_ICONS[t](active)}
                            <span style={{
                                fontSize: 12, fontWeight: active ? 800 : 500,
                                color: active ? C.accent : C.textSecondary,
                                fontFamily: FONT, letterSpacing: active ? "0.02em" : 0,
                            }}>{TAB_LABELS[t]}</span>
                        </button>
                    )
                })}
            </div>
        </div>
    )
}

MobileApp.defaultProps = {
    dataUrl: DATA_URL,
    refreshIntervalSec: 180,
    defaultTab: "home",
    supabaseUrl: "",
    supabaseAnonKey: "",
    chatApiUrl: CHAT_API,
}

addPropertyControls(MobileApp, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: DATA_URL },
    refreshIntervalSec: { type: ControlType.Number, title: "갱신 간격(초)", defaultValue: 180, min: 30, max: 3600, step: 30 },
    defaultTab: {
        type: ControlType.Enum, title: "기본 탭",
        options: ["home", "market", "reco", "ai", "more"],
        optionTitles: ["홈", "시장", "추천", "VERITY AI", "더보기"],
        defaultValue: "home",
    },
    supabaseUrl: { type: ControlType.String, title: "Supabase URL", defaultValue: "", description: "https://xxxxx.supabase.co" },
    supabaseAnonKey: { type: ControlType.String, title: "Supabase Anon Key", defaultValue: "", description: "비워두면 인증 기능 비활성화" },
    chatApiUrl: { type: ControlType.String, title: "Chat API URL", defaultValue: CHAT_API, description: "VERITY 챗 API 엔드포인트" },
})

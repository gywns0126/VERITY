import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useCallback } from "react"

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
    hoverOverlay: "rgba(255,255,255,0.04)", activeOverlay: "rgba(255,255,255,0.08)",
    focusRing: "rgba(181,255,25,0.35)", scrim: "rgba(0,0,0,0.5)",
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

/* ─── Shared constant (used by sub-components defined below) ─── */
const font = FONT

/** Framer 단일 파일 붙여넣기용 인라인 (fetchPortfolioJson.ts와 동일 로직 — 수정 시 맞춰 주세요) */
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000

function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

const PORTFOLIO_FETCH_INIT: RequestInit = {
    cache: "no-store",
    mode: "cors",
    credentials: "omit",
}

function _withTimeout<T>(p: Promise<T>, ms: number, ac: AbortController): Promise<T> {
    const timer = setTimeout(() => ac.abort(), ms)
    return p.finally(() => clearTimeout(timer))
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    return _withTimeout(
        fetch(bustPortfolioUrl(url), { ...PORTFOLIO_FETCH_INIT, signal: ac.signal })
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.text()
            })
            .then((txt) =>
                JSON.parse(
                    txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
                ),
            ),
        PORTFOLIO_FETCH_TIMEOUT_MS,
        ac,
    )
}

const DATA_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"
const REC_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/recommendations.json"
const API_BASE = "https://project-yw131.vercel.app"

// WARN-21: NaN/undefined 방어 숫자 포매터
function fmtFixed(n: any, digits: number = 1, suffix: string = ""): string {
    const x = typeof n === "number" ? n : Number(n)
    if (!Number.isFinite(x)) return "—"
    return `${x.toFixed(digits)}${suffix}`
}
function fmtLocale(n: any, suffix: string = ""): string {
    const x = typeof n === "number" ? n : Number(n)
    if (!Number.isFinite(x)) return "—"
    return `${x.toLocaleString()}${suffix}`
}

// WARN-23: updated_at 기준 stale 경고 정보
function stalenessInfo(updatedAt: any): { label: string; color: string; stale: boolean } {
    if (!updatedAt) return { label: "", color: C.textTertiary, stale: false }
    const t = new Date(String(updatedAt)).getTime()
    if (!Number.isFinite(t)) return { label: "", color: C.textTertiary, stale: false }
    const hours = (Date.now() - t) / 3_600_000
    if (hours < 1) return { label: `방금 갱신 (${Math.round(hours * 60)}분 전)`, color: "#22C55E", stale: false }
    if (hours < 3) return { label: `${Math.round(hours)}시간 전`, color: "#B5FF19", stale: false }
    if (hours < 12) return { label: `${Math.round(hours)}시간 전`, color: "#FFD600", stale: false }
    if (hours < 24) return { label: `${Math.round(hours)}시간 전 (⚠️ stale 경계)`, color: "#F59E0B", stale: true }
    const days = hours / 24
    return { label: `${days.toFixed(1)}일 전 (⚠️ stale)`, color: "#FF4D4D", stale: true }
}

function isKRX(market: string): boolean { return /KOSPI|KOSDAQ|KRX|코스피|코스닥/i.test(market || "") }
function isUSMarket(market: string, currency?: string): boolean {
    if (currency === "USD") return true
    return /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(market || "")
}

interface Props {
    dataUrl: string
    recUrl: string
    apiBase: string
    market: "kr" | "us"
}

/* ─── Sub-components outside StockDashboard to prevent state reset on re-render ─── */

function Sparkline({ data, width = 60, height = 24, color = "#888" }: { data: number[]; width?: number; height?: number; color?: string }) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1
    const points = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`).join(" ")
    return (
        <svg width={width} height={height} style={{ display: "block" }}>
            <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
        </svg>
    )
}

function TrendBlock({ stock: s, isUS: usd }: { stock: any; isUS: boolean }) {
    const trends = s?.trends
    const weeklyData: number[] = s?.sparkline_weekly || []
    const [tp, setTp] = useState<"1m" | "3m" | "6m" | "1y">("3m")
    if (!trends) return null
    const t = trends[tp]
    if (!t) return null
    const sliceMap = { "1m": 4, "3m": 13, "6m": 26, "1y": 52 }
    const chartData = weeklyData.slice(-sliceMap[tp])
    const pctColor = (t.change_pct ?? 0) >= 0 ? C.up : C.down
    return (
        <div style={{ marginTop: 8, padding: "8px 10px", background: C.bgPage, borderRadius: 8, border: `1px solid ${C.border}` }}>
            <div style={{ display: "flex", gap: 4, marginBottom: 6 }}>
                {(["1m", "3m", "6m", "1y"] as const).map((p) => (
                    <button key={p} onClick={() => setTp(p)} style={{
                        border: "none", borderRadius: 6, padding: "3px 8px", fontSize: 12, fontWeight: 700, fontFamily: font,
                        cursor: "pointer", background: tp === p ? "#B5FF19" : "#1A1A1A", color: tp === p ? "#000" : "#666",
                    }}>{p.toUpperCase()}</button>
                ))}
            </div>
            {chartData.length > 1 && <Sparkline data={chartData} width={200} height={32} color={pctColor} />}
            <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
                <span style={{ color: pctColor, fontSize: 12, fontWeight: 800, fontFamily: font }}>{(t.change_pct ?? 0) >= 0 ? "+" : ""}{t.change_pct}%</span>
                <span style={{ color: C.textTertiary, fontSize: 12, fontFamily: font }}>H {usd ? `$${fmtFixed(t.high, 2)}` : fmtLocale(t.high)}</span>
                <span style={{ color: C.textTertiary, fontSize: 12, fontFamily: font }}>L {usd ? `$${fmtFixed(t.low, 2)}` : fmtLocale(t.low)}</span>
                <span style={{ color: C.textTertiary, fontSize: 12, fontFamily: font }}>Vol {Number.isFinite(Number(t.avg_volume)) && Number(t.avg_volume) > 0 ? (Number(t.avg_volume) / 1e6).toFixed(1) + "M" : "—"}</span>
            </div>
        </div>
    )
}

function SectorTrendView({ sectorTrends }: { sectorTrends: any }) {
    const [sp, setSp] = useState<"1m" | "3m" | "6m" | "1y">("3m")
    if (!sectorTrends) return null
    const st = sectorTrends[sp]
    if (!st) return (
        <div style={{ marginTop: 12, padding: 10, background: C.bgPage, borderRadius: 8, border: `1px solid ${C.border}` }}>
            <span style={{ color: C.textTertiary, fontSize: 12, fontFamily: font }}>{sp.toUpperCase()} 섹터 데이터 아직 없음 (스냅샷 축적 중)</span>
        </div>
    )
    return (
        <div style={{ marginTop: 12, padding: "10px 12px", background: C.bgPage, borderRadius: 8, border: `1px solid ${C.border}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ color: "#A78BFA", fontSize: 12, fontWeight: 700, fontFamily: font }}>섹터 추이</span>
                <div style={{ display: "flex", gap: 3 }}>
                    {(["1m", "3m", "6m", "1y"] as const).map((p) => (
                        <button key={p} onClick={() => setSp(p)} style={{
                            border: "none", borderRadius: 6, padding: "2px 7px", fontSize: 12, fontWeight: 700, fontFamily: font,
                            cursor: "pointer", background: sp === p ? "#A78BFA" : "#1A1A1A", color: sp === p ? "#000" : "#666",
                        }}>{p.toUpperCase()}</button>
                    ))}
                </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
                <div style={{ flex: 1 }}>
                    <span style={{ color: "#22C55E", fontSize: 12, fontWeight: 700, display: "block", marginBottom: 4 }}>TOP</span>
                    {(st.top3_sectors || []).map((s: any, i: number) => (
                        <div key={s.name ?? i} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: `1px solid ${C.border}` }}>
                            <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: font }}>{s.name}</span>
                            <span style={{ color: "#22C55E", fontSize: 12, fontWeight: 700, fontFamily: font }}>{(s.avg_change_pct ?? 0) >= 0 ? "+" : ""}{s.avg_change_pct}%</span>
                        </div>
                    ))}
                </div>
                <div style={{ width: 1, background: "#222" }} />
                <div style={{ flex: 1 }}>
                    <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 700, display: "block", marginBottom: 4 }}>BOTTOM</span>
                    {(st.bottom3_sectors || []).map((s: any, i: number) => (
                        <div key={s.name ?? i} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: `1px solid ${C.border}` }}>
                            <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: font }}>{s.name}</span>
                            <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 700, fontFamily: font }}>{s.avg_change_pct}%</span>
                        </div>
                    ))}
                </div>
            </div>
            {(st.rotation_in?.length > 0 || st.rotation_out?.length > 0) && (
                <div style={{ marginTop: 6, display: "flex", gap: 12, flexWrap: "wrap" }}>
                    {st.rotation_in?.length > 0 && (
                        <span style={{ color: "#22C55E", fontSize: 12, fontFamily: font }}>IN: {st.rotation_in.join(", ")}</span>
                    )}
                    {st.rotation_out?.length > 0 && (
                        <span style={{ color: "#EF4444", fontSize: 12, fontFamily: font }}>OUT: {st.rotation_out.join(", ")}</span>
                    )}
                </div>
            )}
        </div>
    )
}

function formatPrice(price: number, usd?: boolean): string {
    if (usd) return `$${Number(price).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    return `${price?.toLocaleString()}원`
}

function formatVolume(value: number, usd?: boolean): string {
    if (usd) return `$${(value / 1e6).toFixed(1)}M`
    return `${(value / 1e8).toFixed(0)}억`
}

function formatMarketCap(value: number, usd?: boolean): string {
    if (usd) return `$${(value / 1e9).toFixed(1)}B`
    return `${(value / 1e12).toFixed(2)}조`
}

function _normalizeApi(raw: string): string {
    let s = (raw || "").trim().replace(/\/+$/, "")
    if (!s) return ""
    if (!/^https?:\/\//i.test(s)) s = `https://${s.replace(/^\/+/, "")}`
    return s.replace(/\/+$/, "")
}

// JWT 인증: verity_supabase_session(localStorage)의 access_token을 Authorization 헤더로 사용.
// (WatchGroupsCard.tsx 와 동일 패턴)
const SUPABASE_SESSION_KEY = "verity_supabase_session"
const AUTH_LOGIN_PATH = "/login"

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

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
    const token = getAccessToken()
    const h: Record<string, string> = { ...extra }
    if (token) h["Authorization"] = `Bearer ${token}`
    return h
}

/** AuthPage로 리다이렉트 (AuthGate 컨벤션: ?next=<원래경로>). */
function redirectToAuth(): void {
    if (typeof window === "undefined") return
    const next = encodeURIComponent(window.location.pathname + window.location.search)
    const url = AUTH_LOGIN_PATH + (AUTH_LOGIN_PATH.includes("?") ? "&" : "?") + "next=" + next
    window.location.href = url
}

/** @deprecated JWT로 교체됨. 구 호출부 호환용. */
function _getVerityUserId(): string {
    if (typeof window === "undefined") return "anon"
    let uid = localStorage.getItem("verity_user_id")
    if (!uid) {
        uid = crypto.randomUUID?.() || `u-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
        localStorage.setItem("verity_user_id", uid)
    }
    return uid
}

const BUSINESS_NODE_LABELS: Record<string, string> = {
    "메모리·파운드리 리드": "메모리·파운드리 핵심",
    "장비/소재": "장비·소재",
}

function _cleanBusinessLabel(v: string): string {
    return String(v || "")
        .replace(/\s+/g, " ")
        .replace(/[|]/g, " ")
        .trim()
}

function getBusinessTagline(stock: any): string {
    const tagline = (stock?.company_tagline || "").trim()
    if (tagline) return tagline

    const roles = Array.isArray(stock?.value_chain?.roles) ? stock.value_chain.roles : []
    if (roles.length > 0) {
        const first = roles[0] || {}
        const sector = _cleanBusinessLabel(first?.sector_label_ko || "")
        const rawNode = _cleanBusinessLabel(first?.node_label_ko || "")
        const node = BUSINESS_NODE_LABELS[rawNode] || rawNode
        if (sector && node) return `${sector} ${node} 기업`
        if (sector) return `${sector} 관련 기업`
    }

    const nicheKeyword = _cleanBusinessLabel(stock?.niche_data?.trends?.keyword || "")
    if (nicheKeyword) return `${nicheKeyword} 관련 기업`

    const ctype = _cleanBusinessLabel(stock?.company_type || "")
    if (ctype) return ctype.includes("기업") ? ctype : `${ctype} 기업`

    return isUSMarket(stock?.market || "", stock?.currency) ? "미국 상장 기업" : "국내 상장 기업"
}

export default function StockDashboard(props: Props) {
    const { dataUrl, recUrl, market = "kr" } = props
    const api = _normalizeApi(props.apiBase) || _normalizeApi(API_BASE)
    const isUS = market === "us"
    const [data, setData] = useState<any>(null)
    // CRIT-17: fetch 성공/실패/로딩 구분 상태
    const [loadState, setLoadState] = useState<"loading" | "ok" | "error">("loading")
    const [loadError, setLoadError] = useState<string>("")
    const [retryNonce, setRetryNonce] = useState(0)
    const [fullRecMap, setFullRecMap] = useState<Record<string, any>>({})
    const [selected, setSelected] = useState(0)
    const [tab, setTab] = useState<"all" | "buy" | "watch" | "avoid">("all")
    const [detailTab, setDetailTab] = useState<
        "overview" | "brain" | "technical" | "sentiment" | "macro" | "predict" | "timing" | "niche" | "property" | "quant" | "group"
    >("overview")

    const [watchGroups, setWatchGroups] = useState<any[]>([])
    const [showGroupPicker, setShowGroupPicker] = useState(false)

    const loadWatchGroups = useCallback(() => {
        if (!api) return
        // 미로그인 상태면 서버 호출 스킵 (401 방지) — 그룹 목록은 빈 상태로 유지
        if (!getAccessToken()) return
        fetch(`${api}/api/watchgroups`, {
            mode: "cors", credentials: "omit",
            headers: authHeaders(),
        })
            .then(r => {
                if (r.status === 401) { redirectToAuth(); throw new Error("unauthorized") }
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.json()
            })
            .then(d => { if (Array.isArray(d)) setWatchGroups(d) })
            .catch(() => {})
    }, [api])

    useEffect(() => { loadWatchGroups() }, [loadWatchGroups])

    const addToWatchGroup = useCallback((groupId: string, ticker: string, name: string) => {
        if (!api) return
        // 미로그인 상태면 AuthPage로 리다이렉트
        if (!getAccessToken()) { redirectToAuth(); return }
        fetch(`${api}/api/watchgroups`, {
            method: "POST",
            headers: authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({
                action: "add_item",
                group_id: groupId,
                ticker,
                name,
                market: isUS ? "us" : "kr",
            }),
            mode: "cors", credentials: "omit",
        })
            .then(r => {
                if (r.status === 401) { redirectToAuth(); throw new Error("unauthorized") }
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.json().catch(() => ({}))
            })
            .then(() => { setShowGroupPicker(false); loadWatchGroups() })
            .catch(() => {})
    }, [api, isUS, loadWatchGroups])

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        setLoadState("loading")
        setLoadError("")
        fetchPortfolioJson(dataUrl, ac.signal)
            .then(d => {
                if (ac.signal.aborted) return
                setData(d)
                setLoadState("ok")
            })
            .catch((err: any) => {
                if (ac.signal.aborted) return
                setLoadState("error")
                setLoadError((err && (err as Error).message) || "fetch failed")
            })
        return () => ac.abort()
    }, [dataUrl, retryNonce])

    useEffect(() => {
        const url = recUrl || REC_URL
        if (!url) return
        const ac = new AbortController()
        fetchPortfolioJson(url, ac.signal)
            .then((arr: any) => {
                if (ac.signal.aborted || !Array.isArray(arr)) return
                const m: Record<string, any> = {}
                arr.forEach((r: any) => { if (r?.ticker) m[r.ticker] = r })
                setFullRecMap(m)
            })
            .catch(() => {})
        return () => ac.abort()
    }, [recUrl])

    const allRecs: any[] = data?.recommendations || []
    const recs = isUS
        ? allRecs.filter((r) => isUSMarket(r.market, r.currency))
        : allRecs.filter((r) => isKRX(r.market || ""))
    const macro: any = data?.macro || {}

    const filtered =
        tab === "all"
            ? recs
            : recs.filter((r) => r.recommendation === tab.toUpperCase())
    // slim rec에 fullRecMap의 상세 데이터 병합 (ticker 기준)
    const rawStock = recs[selected] || null
    const stock = rawStock ? { ...rawStock, ...(fullRecMap[rawStock.ticker] || {}) } : null
    const mf = stock?.multi_factor || {}
    const tech = stock?.technical || {}
    const sent = stock?.sentiment || {}
    const flow = stock?.flow || {}
    const breakdown = mf.factor_breakdown || {}

    const multiScore = mf.multi_score ?? 0
    const multiColor =
        multiScore >= 65 ? "#B5FF19" : multiScore >= 45 ? "#FFD600" : "#FF4D4D"

    const radius = 48
    const stroke = 7
    const circumference = 2 * Math.PI * radius
    const progress = (multiScore / 100) * circumference

    const buyCount = recs.filter((r) => r.recommendation === "BUY").length
    const watchCount = recs.filter((r) => r.recommendation === "WATCH").length
    const avoidCount = recs.filter((r) => r.recommendation === "AVOID").length

    if (loadState === "error") {
        return (
            <div style={{ ...wrap, justifyContent: "center", alignItems: "center", minHeight: 500, flexDirection: "column" as const, gap: 12 }}>
                <span style={{ color: "#FF4D4D", fontSize: 14, fontWeight: 700 }}>데이터 로드 실패</span>
                <span style={{ color: C.textSecondary, fontSize: 12 }}>{loadError || "네트워크 오류"}</span>
                <button
                    onClick={() => setRetryNonce(n => n + 1)}
                    style={{ marginTop: 8, background: "#B5FF19", color: "#000", border: "none", borderRadius: 8, padding: "8px 14px", fontWeight: 700, cursor: "pointer" }}
                >다시 시도</button>
            </div>
        )
    }
    if (!data) {
        return (
            <div style={{ ...wrap, justifyContent: "center", alignItems: "center", minHeight: 500 }}>
                <span style={{ color: C.textTertiary, fontSize: 14 }}>데이터 로딩 중...</span>
            </div>
        )
    }

    const rec = stock?.recommendation || "WATCH"
    const recColor = rec === "BUY" ? "#B5FF19" : rec === "AVOID" ? "#FF4D4D" : "#888"

    return (
        <div style={wrap}>
            {/* WARN-23: stale 데이터 경고 배지 */}
            {(() => {
                const s = stalenessInfo(data?.updated_at)
                if (!s.label) return null
                return (
                    <div style={{ padding: "6px 14px", background: s.stale ? "rgba(255,77,77,0.08)" : "#0A0A0A", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "flex-end" }}>
                        <span style={{ color: s.color, fontSize: 12, fontWeight: s.stale ? 800 : 500, fontFamily: font }}>
                            데이터 갱신: {s.label}
                        </span>
                    </div>
                )
            })()}
            {/* 탭 필터 */}
            <div style={tabBar}>
                {([
                    ["all", `전체 ${recs.length}`],
                    ["buy", `매수 ${buyCount}`],
                    ["watch", `관망 ${watchCount}`],
                    ["avoid", `회피 ${avoidCount}`],
                ] as const).map(([key, label]) => (
                    <button
                        key={key}
                        onClick={() => setTab(key)}
                        style={{
                            ...tabBtn,
                            background: tab === key ? "#B5FF19" : "#1A1A1A",
                            color: tab === key ? "#000" : "#888",
                        }}
                    >
                        {label}
                    </button>
                ))}
            </div>

            <div style={body}>
                {/* 좌측: 종목 리스트 */}
                <div style={listPanel}>
                    {filtered.map((s: any) => {
                        const idx = recs.indexOf(s)
                        const isActive = idx === selected
                        const ms = s.multi_factor?.multi_score ?? s.safety_score ?? 0
                        const msColor = ms >= 65 ? "#B5FF19" : ms >= 45 ? "#FFD600" : "#FF4D4D"
                        const rBadge = s.recommendation === "BUY" ? "#B5FF19" : s.recommendation === "AVOID" ? "#FF4D4D" : "#555"
                        const whyText = s.gold_insight || s.silver_insight || ""
                        const whyIsGold = !!s.gold_insight
                        const hasClaude = !!s.claude_analysis
                        return (
                            <div
                                key={s.ticker}
                                onClick={() => { setSelected(idx); setDetailTab("overview") }}
                                style={{
                                    ...listItem,
                                    background: isActive ? "#1A1A1A" : "transparent",
                                    borderLeft: isActive ? "3px solid #B5FF19" : "3px solid transparent",
                                    cursor: "pointer",
                                }}
                            >
                                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
                                    <span style={{ ...listRecDot, background: rBadge }} />
                                    <div style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1, minWidth: 0 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 4, minWidth: 0 }}>
                                            <span style={listName}>{s.name}</span>
                                            {s.company_type && (
                                                <span style={{ fontSize: 12, fontWeight: 700, color: "#B5FF19", background: C.accentSoft, border: "1px solid #1A2A00", borderRadius: 3, padding: "1px 5px", whiteSpace: "nowrap" as const, flexShrink: 0 }}>{s.company_type}</span>
                                            )}
                                        </div>
                                        <span style={listTicker}>{s.ticker} · {s.market} · {getBusinessTagline(s)}{hasClaude ? " · 🔬" : ""}</span>
                                        {whyText && (
                                            <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 1 }}>
                                                <span style={{
                                                    fontSize: 8, fontWeight: 800, padding: "1px 4px", borderRadius: 3,
                                                    background: whyIsGold ? "#FFD600" : "#666",
                                                    color: "#000", lineHeight: 1.2, flexShrink: 0,
                                                }}>
                                                    {whyIsGold ? "G" : "S"}
                                                </span>
                                                <span style={{
                                                    fontSize: 12, color: "#777", lineHeight: 1.2,
                                                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                                                }}>
                                                    {whyText}
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                    <div style={listRight}>
                                        {s.sparkline?.length > 1 && (
                                            <Sparkline data={s.sparkline} width={32} height={16}
                                                color={s.sparkline[s.sparkline.length - 1] >= s.sparkline[0] ? C.up : C.down} />
                                        )}
                                        <span style={listPrice}>{formatPrice(s.price, isUS)}</span>
                                        <span style={{ ...listScore, color: msColor }}>{ms}점</span>
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>

                {/* 우측: 상세 패널 */}
                {stock && (
                    <div style={detailPanel}>
                        {/* 헤더: 게이지 + 기본정보 */}
                        <div style={detailTop}>
                            <div style={gaugeWrap}>
                                <svg width={120} height={120} viewBox={`0 0 ${(radius + stroke) * 2} ${(radius + stroke) * 2}`}>
                                    <circle cx={radius + stroke} cy={radius + stroke} r={radius} fill="none" stroke="#222" strokeWidth={stroke} />
                                    <circle cx={radius + stroke} cy={radius + stroke} r={radius} fill="none" stroke={multiColor} strokeWidth={stroke}
                                        strokeDasharray={circumference} strokeDashoffset={circumference - progress}
                                        strokeLinecap="round" transform={`rotate(-90 ${radius + stroke} ${radius + stroke})`}
                                        style={{ transition: "stroke-dashoffset 0.5s ease" }} />
                                </svg>
                                <div style={gaugeCenter}>
                                    <span style={{ ...gaugeNum, color: multiColor }}>{multiScore}</span>
                                    <span style={gaugeGrade}>{mf.grade || "—"}</span>
                                </div>
                            </div>
                            <div style={detailInfo}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    <span style={{ ...badge, background: recColor }}>{rec}</span>
                                    <span style={{ color: C.textTertiary, fontSize: 12 }}>{stock.market}</span>
                                    {stock.company_type && (
                                        <span style={{ fontSize: 12, fontWeight: 700, color: "#B5FF19", background: C.accentSoft, border: "1px solid #1A2A00", borderRadius: 6, padding: "2px 8px" }}>{stock.company_type}</span>
                                    )}
                                </div>
                                <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                                    <span style={detailName}>{stock.name}</span>
                                    <span style={detailBusiness}>{getBusinessTagline(stock)}</span>
                                    {watchGroups.length > 0 && (
                                        <div style={{ position: "relative" as const }}>
                                            <button
                                                onClick={() => setShowGroupPicker(!showGroupPicker)}
                                                style={{ background: C.bgElevated, border: "1px solid #333", borderRadius: 8, padding: "4px 10px", color: "#B5FF19", fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: font, whiteSpace: "nowrap" as const }}
                                            >
                                                {showGroupPicker ? "✕" : "⭐ 관심"}
                                            </button>
                                            {showGroupPicker && (
                                                <div style={{ position: "absolute" as const, top: 30, left: 0, zIndex: 20, background: C.bgElevated, border: "1px solid #333", borderRadius: 10, padding: 6, minWidth: 160 }}>
                                                    {watchGroups.map((g: any) => (
                                                        <div
                                                            key={g.id}
                                                            onClick={() => addToWatchGroup(g.id, stock.ticker, stock.name)}
                                                            style={{ padding: "6px 10px", borderRadius: 6, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}
                                                            onMouseEnter={e => (e.currentTarget.style.background = "#1A1A1A")}
                                                            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                                                        >
                                                            <span style={{ fontSize: 14 }}>{g.icon}</span>
                                                            <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600 }}>{g.name}</span>
                                                            <span style={{ color: C.textTertiary, fontSize: 12, marginLeft: "auto" }}>{g.items?.length || 0}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                                <span style={detailTicker}>{stock.ticker} · {formatPrice(stock.price, isUS)}</span>
                                {stock.sparkline?.length > 1 && (
                                    <div style={{ marginTop: 4 }}>
                                        <Sparkline data={stock.sparkline} width={180} height={36}
                                            color={stock.sparkline[stock.sparkline.length - 1] >= stock.sparkline[0] ? C.up : C.down} />
                                    </div>
                                )}
                                <p style={detailVerdict}>{stock.ai_verdict || "분석 대기 중"}</p>
                                <TrendBlock stock={stock} isUS={isUS} />
                            </div>
                        </div>

                        {/* 5팩터 바 */}
                        <div style={factorBarSection}>
                            {(["fundamental", "technical", "sentiment", "flow", "macro"] as const).map((key) => {
                                const val = breakdown[key] || 0
                                const labels: Record<string, string> = { fundamental: "펀더멘털", technical: "기술적", sentiment: "뉴스", flow: "수급", macro: "매크로" }
                                const c = val >= 65 ? "#B5FF19" : val >= 45 ? "#FFD600" : "#FF4D4D"
                                return (
                                    <div key={key} style={factorItem}>
                                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                                            <span style={factorLabel}>{labels[key]}</span>
                                            <span style={{ ...factorVal, color: c }}>{val}</span>
                                        </div>
                                        <div style={factorBarBg}>
                                            <div style={{ ...factorBarFill, width: `${val}%`, background: c }} />
                                        </div>
                                    </div>
                                )
                            })}
                        </div>

                        {/* 상세 탭 */}
                        <div style={subTabBar}>
                            {([["overview", "개요"], ["brain", "브레인"], ["quant", "퀀트"], ["timing", "매매시점"], ["technical", "기술적"], ["sentiment", "뉴스/수급"], ["macro", "매크로"], ["property", "부동산"], ["group", "관계회사"], ["niche", "틈새"], ["predict", "예측"]] as const).map(([k, l]) => (
                                <button key={k} onClick={() => setDetailTab(k)} style={{
                                    ...subTabBtn,
                                    borderBottom: detailTab === k ? "2px solid #B5FF19" : "2px solid transparent",
                                    color: detailTab === k ? "#fff" : "#666",
                                }}>
                                    {l}
                                </button>
                            ))}
                        </div>

                        <div style={tabContent}>
                            {detailTab === "overview" && (
                                <>
                                    <div style={insightSection}>
                                        <div style={insightRow}>
                                            <span style={goldBadge}>GOLD</span>
                                            <span style={insightText}>{stock.gold_insight || "데이터 수집 중"}</span>
                                        </div>
                                        <div style={insightRow}>
                                            <span style={silverBadge}>SILVER</span>
                                            <span style={insightText}>{stock.silver_insight || "데이터 수집 중"}</span>
                                        </div>
                                        {stock.claude_analysis && (
                                            <div style={{ marginTop: 8, padding: "8px 10px", background: stock.claude_analysis.agrees ? "#0A1A0A" : "#1A0A0A", border: `1px solid ${stock.claude_analysis.agrees ? "#1A3A1A" : "#3A1A1A"}`, borderRadius: 8 }}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                                                    <span style={{ background: "#6B21A8", color: "#E9D5FF", fontSize: 12, fontWeight: 800, padding: "2px 6px", borderRadius: 6, fontFamily: font }}>CLAUDE</span>
                                                    <span style={{ color: stock.claude_analysis.agrees ? "#22C55E" : "#F59E0B", fontSize: 12, fontWeight: 700, fontFamily: font }}>
                                                        {stock.claude_analysis.agrees ? "Gemini 동의" : "Gemini 반론"}
                                                    </span>
                                                    {stock.claude_analysis.override && (
                                                        <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 800, fontFamily: font }}>
                                                            → {stock.claude_analysis.override}
                                                        </span>
                                                    )}
                                                </div>
                                                <span style={{ color: C.textPrimary, fontSize: 12, lineHeight: "1.5", fontFamily: font }}>{stock.claude_analysis.verdict}</span>
                                                {stock.claude_analysis.conviction_note && (
                                                    <div style={{ color: C.textSecondary, fontSize: 12, marginTop: 4, fontFamily: font }}>{stock.claude_analysis.conviction_note}</div>
                                                )}
                                                {stock.claude_analysis.hidden_risks?.length > 0 && (
                                                    <div style={{ color: "#EF4444", fontSize: 12, marginTop: 4, fontFamily: font }}>숨겨진 리스크: {stock.claude_analysis.hidden_risks.join(" · ")}</div>
                                                )}
                                                {stock.claude_analysis.hidden_opportunities?.length > 0 && (
                                                    <div style={{ color: "#22C55E", fontSize: 12, marginTop: 2, fontFamily: font }}>숨겨진 기회: {stock.claude_analysis.hidden_opportunities.join(" · ")}</div>
                                                )}
                                            </div>
                                        )}
                                        {stock.dual_consensus && (
                                            <div style={{
                                                marginTop: 8,
                                                padding: "8px 10px",
                                                background: stock.dual_consensus.manual_review_required ? "#1A0A0A" : "#0A111A",
                                                border: `1px solid ${stock.dual_consensus.manual_review_required ? "#3A1A1A" : "#1A2F45"}`,
                                                borderRadius: 8,
                                            }}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
                                                    <span style={{ background: "#0EA5E9", color: "#001018", fontSize: 12, fontWeight: 800, padding: "2px 6px", borderRadius: 6, fontFamily: font }}>
                                                        HYBRID
                                                    </span>
                                                    <span style={{ color: "#93C5FD", fontSize: 12, fontWeight: 700, fontFamily: font }}>
                                                        최종 {stock.dual_consensus.final_recommendation} · 신뢰 {stock.dual_consensus.final_confidence}
                                                    </span>
                                                    <span style={{ color: stock.dual_consensus.manual_review_required ? "#EF4444" : "#22C55E", fontSize: 12, fontWeight: 700, fontFamily: font }}>
                                                        {stock.dual_consensus.manual_review_required ? "수동검토 필요" : `합의 ${stock.dual_consensus.conflict_level}`}
                                                    </span>
                                                </div>
                                                <div style={{ color: C.textSecondary, fontSize: 12, lineHeight: "1.4", fontFamily: font }}>
                                                    Gemini {stock.dual_consensus.gemini_recommendation} ({stock.dual_consensus.gemini_confidence}) · Claude {stock.dual_consensus.claude_recommendation} ({stock.dual_consensus.claude_confidence})
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                    <div style={metricsGrid}>
                                        <MetricCard label="PER" value={fmtFixed(stock.per, 1)} />
                                        <MetricCard label="고점대비" value={fmtFixed(stock.drop_from_high_pct, 1, "%")}
                                            color={(Number.isFinite(Number(stock.drop_from_high_pct)) ? Number(stock.drop_from_high_pct) : 0) <= -20 ? "#B5FF19" : "#fff"} />
                                        <MetricCard label="배당률" value={fmtFixed(stock.div_yield, 1, "%")} />
                                        <MetricCard label="거래대금" value={stock.trading_value ? formatVolume(stock.trading_value, isUS) : "—"} />
                                        <MetricCard label="시총" value={stock.market_cap ? formatMarketCap(stock.market_cap, isUS) : "—"} />
                                        <MetricCard label="안심점수" value={`${stock.safety_score || 0}`} />
                                        <MetricCard label="부채비율" value={fmtFixed(stock.debt_ratio, 0, "%")}
                                            color={(Number.isFinite(Number(stock.debt_ratio)) ? Number(stock.debt_ratio) : 0) > 100 ? "#FF4D4D" : "#22C55E"} />
                                        <MetricCard label="영업이익률" value={fmtFixed(stock.operating_margin != null && Number.isFinite(Number(stock.operating_margin)) ? Number(stock.operating_margin) * 100 : NaN, 1, "%")}
                                            color={(Number(stock.operating_margin) || 0) > 0.1 ? "#22C55E" : (Number(stock.operating_margin) || 0) < 0 ? "#FF4D4D" : "#FFD600"} />
                                        <MetricCard label="ROE" value={fmtFixed(stock.roe != null && Number.isFinite(Number(stock.roe)) ? Number(stock.roe) * 100 : NaN, 1, "%")}
                                            color={(Number(stock.roe) || 0) > 0.15 ? "#22C55E" : (Number(stock.roe) || 0) < 0 ? "#FF4D4D" : "#fff"} />
                                    </div>

                                    {/* 실적발표일 */}
                                    {stock.earnings?.next_earnings && (
                                        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#1A1200", border: "1px solid #332A00", borderRadius: 8, padding: "8px 12px", marginTop: 4 }}>
                                            <span style={{ color: "#FFD600", fontSize: 13, fontWeight: 700 }}>실적발표</span>
                                            <span style={{ color: C.textPrimary, fontSize: 12 }}>{stock.earnings.next_earnings}</span>
                                        </div>
                                    )}

                                    {/* 타이밍 요약 */}
                                    {stock.timing && (
                                        <div style={{ display: "flex", alignItems: "center", gap: 12, background: C.bgElevated, borderRadius: 10, padding: "10px 14px", marginTop: 4 }}>
                                            <div style={{ width: 36, height: 36, borderRadius: 18, background: stock.timing.color || "#888", display: "flex", alignItems: "center", justifyContent: "center" }}>
                                                <span style={{ color: "#000", fontSize: 14, fontWeight: 900 }}>{stock.timing.timing_score}</span>
                                            </div>
                                            <div style={{ flex: 1 }}>
                                                <span style={{ color: stock.timing.color || "#888", fontSize: 13, fontWeight: 700 }}>
                                                    {stock.timing.label || "—"}
                                                </span>
                                                <span style={{ color: C.textTertiary, fontSize: 12, marginLeft: 8 }}>
                                                    {stock.timing.reasons?.[0] || ""}
                                                </span>
                                            </div>
                                        </div>
                                    )}
                                    {mf.all_signals?.length > 0 && (
                                        <div style={signalWrap}>
                                            {mf.all_signals.map((sig: string, i: number) => (
                                                <span key={i} style={signalTag}>{sig}</span>
                                            ))}
                                        </div>
                                    )}

                                    {/* 종목 최신 뉴스 */}
                                    {(() => {
                                        const links: any[] = stock?.sentiment?.top_headline_links || []
                                        const details: any[] = stock?.sentiment?.detail || []
                                        const plain: string[] = stock?.sentiment?.top_headlines || []
                                        const richItems = links.length > 0
                                            ? links.slice(0, 5)
                                            : details.filter((d: any) => d.url).slice(0, 5)

                                        if (richItems.length === 0 && plain.length === 0) return null
                                        return (
                                            <div style={{ marginTop: 4 }}>
                                                <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>최신 뉴스</div>
                                                {richItems.length > 0
                                                    ? richItems.map((item: any, i: number) => {
                                                        const sentColor = item.label === "positive" ? "#22C55E" : item.label === "negative" ? "#EF4444" : "#555"
                                                        return (
                                                            <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                                                                style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", background: C.bgElevated, borderRadius: 8, marginBottom: 4, textDecoration: "none", transition: "background 0.15s", cursor: "pointer" }}
                                                                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#1A1A1A" }}
                                                                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "#111" }}>
                                                                {item.label && <span style={{ width: 4, height: 4, borderRadius: 2, background: sentColor, flexShrink: 0 }} />}
                                                                <span style={{ color: "#bbb", fontSize: 12, lineHeight: 1.4, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.title}</span>
                                                                <span style={{ color: C.textTertiary, fontSize: 12, flexShrink: 0 }}>↗</span>
                                                            </a>
                                                        )
                                                    })
                                                    : plain.slice(0, 5).map((h: string, i: number) => (
                                                        <div key={i} style={{ ...newsRow, marginBottom: 4 }}>
                                                            <span style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.4 }}>{h}</span>
                                                        </div>
                                                    ))
                                                }
                                            </div>
                                        )
                                    })()}

                                    {/* 글로벌 시장 뉴스 */}
                                    {(() => {
                                        const globalNews: any[] = data?.headlines || []
                                        if (globalNews.length === 0) return null
                                        const rowBase: React.CSSProperties = { display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", background: C.bgElevated, borderRadius: 8, marginBottom: 4, textDecoration: "none", transition: "background 0.15s" }
                                        return (
                                            <div style={{ marginTop: 4 }}>
                                                <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>시장 뉴스</div>
                                                {globalNews.slice(0, 6).map((h: any, i: number) => {
                                                    const sc = h.sentiment === "positive" ? "#22C55E" : h.sentiment === "negative" ? "#EF4444" : "#555"
                                                    const href = h.link || h.url || ""
                                                    const inner = (
                                                        <>
                                                            <span style={{ width: 4, height: 4, borderRadius: 2, background: sc, flexShrink: 0 }} />
                                                            <span style={{ color: "#bbb", fontSize: 12, lineHeight: 1.4, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.title}</span>
                                                            {h.source && <span style={{ color: C.textTertiary, fontSize: 12, flexShrink: 0 }}>{h.source}</span>}
                                                            {h.time && <span style={{ color: C.textDisabled, fontSize: 12, flexShrink: 0 }}>{h.time.slice(5, 16)}</span>}
                                                            {href && <span style={{ color: C.textTertiary, fontSize: 12, flexShrink: 0 }}>↗</span>}
                                                        </>
                                                    )
                                                    return href ? (
                                                        <a key={i} href={href} target="_blank" rel="noopener noreferrer" style={{ ...rowBase, cursor: "pointer" }}
                                                            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#1A1A1A" }}
                                                            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "#111" }}>
                                                            {inner}
                                                        </a>
                                                    ) : (
                                                        <div key={i} style={rowBase}>{inner}</div>
                                                    )
                                                })}
                                            </div>
                                        )
                                    })()}

                                    {/* US 전용: 프리/애프터마켓, 애널리스트, 실적 서프라이즈 */}
                                    {isUS && stock.pre_after_market && (stock.pre_after_market.pre_price || stock.pre_after_market.after_price) && (
                                        <div style={{ marginTop: 4 }}>
                                            <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>프리/애프터마켓</div>
                                            <div style={metricsGrid}>
                                                {stock.pre_after_market.pre_price != null && <MetricCard label="프리마켓" value={formatPrice(stock.pre_after_market.pre_price, true)} color={stock.pre_after_market.pre_change_pct > 0 ? "#22C55E" : stock.pre_after_market.pre_change_pct < 0 ? "#FF4D4D" : "#fff"} />}
                                                {stock.pre_after_market.pre_change_pct != null && <MetricCard label="프리 변동" value={`${stock.pre_after_market.pre_change_pct > 0 ? "+" : ""}${stock.pre_after_market.pre_change_pct.toFixed(2)}%`} color={stock.pre_after_market.pre_change_pct > 0 ? C.up : C.down} />}
                                                {stock.pre_after_market.after_price != null && <MetricCard label="애프터마켓" value={formatPrice(stock.pre_after_market.after_price, true)} color={(stock.pre_after_market.after_change_pct || 0) > 0 ? "#22C55E" : (stock.pre_after_market.after_change_pct || 0) < 0 ? "#FF4D4D" : "#fff"} />}
                                            </div>
                                        </div>
                                    )}
                                    {isUS && stock.analyst_consensus && (stock.analyst_consensus.buy > 0 || stock.analyst_consensus.hold > 0 || stock.analyst_consensus.sell > 0) && (
                                        <div style={{ marginTop: 8 }}>
                                            <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>애널리스트 의견</div>
                                            <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
                                                <span style={{ background: "#22C55E", color: "#000", fontSize: 12, fontWeight: 800, padding: "2px 8px", borderRadius: 6 }}>매수 {stock.analyst_consensus.buy}</span>
                                                <span style={{ background: "#FFD600", color: "#000", fontSize: 12, fontWeight: 800, padding: "2px 8px", borderRadius: 6 }}>중립 {stock.analyst_consensus.hold}</span>
                                                <span style={{ background: "#FF4D4D", color: "#000", fontSize: 12, fontWeight: 800, padding: "2px 8px", borderRadius: 6 }}>매도 {stock.analyst_consensus.sell}</span>
                                            </div>
                                            {stock.analyst_consensus.target_mean > 0 && (
                                                <div style={{ display: "flex", gap: 6 }}>
                                                    <MetricCard label="목표가" value={formatPrice(stock.analyst_consensus.target_mean, true)} />
                                                    <MetricCard label="업사이드" value={`${stock.analyst_consensus.upside_pct > 0 ? "+" : ""}${stock.analyst_consensus.upside_pct}%`} color={stock.analyst_consensus.upside_pct > 0 ? C.up : C.down} />
                                                </div>
                                            )}
                                        </div>
                                    )}
                                    {isUS && Array.isArray(stock.earnings_surprises) && stock.earnings_surprises.length > 0 && (
                                        <div style={{ marginTop: 8 }}>
                                            <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>실적 서프라이즈</div>
                                            <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(stock.earnings_surprises.length, 4)}, 1fr)`, gap: 6 }}>
                                                {stock.earnings_surprises.slice(0, 4).map((es: any, i: number) => {
                                                    const sp = es.surprise_pct || 0
                                                    return <div key={i}><MetricCard label={es.period || `Q${4 - i}`} value={`${sp > 0 ? "+" : ""}${sp.toFixed(1)}%`} color={sp > 0 ? "#22C55E" : sp < 0 ? "#FF4D4D" : "#888"} /></div>
                                                })}
                                            </div>
                                        </div>
                                    )}
                                    {isUS && (
                                        <a href={`https://finance.yahoo.com/quote/${stock.ticker}`} target="_blank" rel="noopener noreferrer"
                                            style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 8, padding: "8px 14px", background: C.bgElevated, border: `1px solid ${C.border}`, borderRadius: 8, color: "#60A5FA", fontSize: 12, fontWeight: 700, textDecoration: "none" }}>
                                            Yahoo Finance ↗
                                        </a>
                                    )}
                                </>
                            )}

                            {detailTab === "technical" && (
                                <>
                                    <div style={metricsGrid}>
                                        <MetricCard label="RSI(14)" value={tech.rsi?.toString() || "—"}
                                            color={tech.rsi <= 30 ? "#B5FF19" : tech.rsi >= 70 ? "#FF4D4D" : "#fff"} />
                                        <MetricCard label="MACD" value={tech.macd?.toString() || "—"}
                                            color={tech.macd_hist > 0 ? "#B5FF19" : "#FF4D4D"} />
                                        <MetricCard label="볼린저 위치" value={`${tech.bb_position}%`}
                                            color={tech.bb_position <= 20 ? "#B5FF19" : tech.bb_position >= 80 ? "#FF4D4D" : "#fff"} />
                                        <MetricCard label="거래량비" value={`${tech.vol_ratio}x`}
                                            color={tech.vol_ratio >= 2 ? "#FFD600" : "#fff"} />
                                        <MetricCard label="MA20" value={tech.ma20?.toLocaleString() || "—"} />
                                        <MetricCard label="MA60" value={tech.ma60?.toLocaleString() || "—"} />
                                    </div>
                                    <div style={{ marginTop: 12 }}>
                                        <span style={{ color: C.textTertiary, fontSize: 12 }}>이동평균선 배열</span>
                                        <div style={{ ...maBar, marginTop: 8 }}>
                                            {[["MA5", tech.ma5], ["MA20", tech.ma20], ["MA60", tech.ma60], ["MA120", tech.ma120]].map(([lbl, val]) => (
                                                <div key={lbl as string} style={maItem}>
                                                    <span style={{ color: C.textSecondary, fontSize: 12 }}>{lbl as string}</span>
                                                    <span style={{ color: Number(val) < (tech.price || 0) ? "#B5FF19" : "#FF4D4D", fontSize: 13, fontWeight: 700 }}>
                                                        {fmtLocale(val)}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                    {tech.signals?.length > 0 && (
                                        <div style={signalWrap}>
                                            {tech.signals.map((s: string, i: number) => (
                                                <span key={i} style={signalTag}>{s}</span>
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}

                            {detailTab === "sentiment" && (() => {
                                const social = stock?.social_sentiment || {}
                                const hasSSocial = social.score != null
                                const newsS = social.news || {}
                                const commS = social.community || {}
                                const redditS = social.reddit || {}
                                return (
                                    <>
                                        <div style={metricsGrid}>
                                            {hasSSocial ? (
                                                <>
                                                    <MetricCard label="종합 감성" value={`${social.score}`}
                                                        color={social.score >= 60 ? "#B5FF19" : social.score <= 40 ? "#FF4D4D" : "#FFD600"} />
                                                    <MetricCard label="추세" value={social.trend === "bullish" ? "강세" : social.trend === "bearish" ? "약세" : "중립"}
                                                        color={social.trend === "bullish" ? "#B5FF19" : social.trend === "bearish" ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="뉴스" value={`${newsS.score || sent.score || 50}`}
                                                        color={((newsS.score || sent.score || 50)) >= 60 ? "#B5FF19" : ((newsS.score || sent.score || 50)) <= 40 ? "#FF4D4D" : "#FFD600"} />
                                                    <MetricCard label="커뮤니티" value={`${commS.score || "—"}`}
                                                        color={commS.score >= 60 ? "#B5FF19" : commS.score <= 40 ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="Reddit" value={`${redditS.score || "—"}`}
                                                        color={redditS.score >= 60 ? "#B5FF19" : redditS.score <= 40 ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="수급 점수" value={`${flow.flow_score || 50}`} />
                                                </>
                                            ) : (
                                                <>
                                                    <MetricCard label="뉴스 감성" value={`${sent.score || 50}`}
                                                        color={sent.score >= 60 ? "#B5FF19" : sent.score <= 40 ? "#FF4D4D" : "#FFD600"} />
                                                    <MetricCard label="긍정 키워드" value={`${sent.positive || 0}건`} color="#B5FF19" />
                                                    <MetricCard label="부정 키워드" value={`${sent.negative || 0}건`} color="#FF4D4D" />
                                                    <MetricCard label="외국인" value={flow.foreign_net > 0 ? "순매수" : flow.foreign_net < 0 ? "순매도" : "중립"}
                                                        color={flow.foreign_net > 0 ? "#B5FF19" : flow.foreign_net < 0 ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="기관" value={flow.institution_net > 0 ? "순매수" : flow.institution_net < 0 ? "순매도" : "중립"}
                                                        color={flow.institution_net > 0 ? "#B5FF19" : flow.institution_net < 0 ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="수급 점수" value={`${flow.flow_score || 50}`} />
                                                </>
                                            )}
                                        </div>
                                        {hasSSocial && (commS.volume > 0 || redditS.volume > 0) && (
                                            <div style={{ marginTop: 10, display: "flex", gap: 16, fontSize: 12, color: C.textTertiary }}>
                                                {commS.volume > 0 && <span>커뮤니티 {commS.volume}건 (긍정 {commS.positive} / 부정 {commS.negative})</span>}
                                                {redditS.volume > 0 && <span>Reddit {redditS.volume}건 (긍정 {redditS.positive} / 부정 {redditS.negative})</span>}
                                            </div>
                                        )}
                                        {redditS.top_posts?.length > 0 && (
                                            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                                                <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>Reddit 인기글</span>
                                                {redditS.top_posts.map((p: any, i: number) => (
                                                    <div key={i} style={{ ...newsRow, padding: "4px 0" }}>
                                                        <span style={{ color: C.textSecondary, fontSize: 12 }}>r/{p.sub} · {p.title}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                        {(() => {
                                            const links: any[] = sent.top_headline_links || []
                                            const details: any[] = sent.detail || []
                                            const plain: string[] = sent.top_headlines || []
                                            const hasLinks = links.length > 0 || details.some((d: any) => d.url)

                                            if (!hasLinks && plain.length === 0) return null
                                            const newsItems = hasLinks
                                                ? (links.length > 0 ? links : details.filter((d: any) => d.url)).slice(0, 8)
                                                : []

                                            return (
                                                <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                                                    <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>최근 뉴스</span>
                                                    {newsItems.length > 0
                                                        ? newsItems.map((item: any, i: number) => {
                                                            const sc = item.label === "positive" ? "#22C55E" : item.label === "negative" ? "#EF4444" : "#555"
                                                            return (
                                                                <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                                                                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: C.bgElevated, borderRadius: 8, textDecoration: "none", transition: "background 0.15s", cursor: "pointer" }}
                                                                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#1A1A1A" }}
                                                                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "#111" }}>
                                                                    {item.label && <span style={{ width: 5, height: 5, borderRadius: 3, background: sc, flexShrink: 0 }} />}
                                                                    <span style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.5, flex: 1 }}>{item.title}</span>
                                                                    <span style={{ color: C.textTertiary, fontSize: 12, flexShrink: 0 }}>↗</span>
                                                                </a>
                                                            )
                                                        })
                                                        : plain.map((h: string, i: number) => (
                                                            <div key={i} style={newsRow}>
                                                                <span style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.5 }}>{h}</span>
                                                            </div>
                                                        ))
                                                    }
                                                </div>
                                            )
                                        })()}
                                        {/* US: 내부자 심리 */}
                                        {isUS && stock.insider_sentiment && (stock.insider_sentiment.positive_count > 0 || stock.insider_sentiment.negative_count > 0) && (
                                            <div style={{ marginTop: 12 }}>
                                                <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>내부자 심리 (90일)</div>
                                                <div style={metricsGrid}>
                                                    <MetricCard label="MSPR" value={fmtFixed(stock.insider_sentiment?.mspr, 4)} color={Number(stock.insider_sentiment?.mspr) > 0 ? "#22C55E" : Number(stock.insider_sentiment?.mspr) < 0 ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="순매수" value={String(stock.insider_sentiment.positive_count)} color="#22C55E" />
                                                    <MetricCard label="순매도" value={String(stock.insider_sentiment.negative_count)} color="#FF4D4D" />
                                                </div>
                                            </div>
                                        )}
                                        {/* US: 기관 보유 */}
                                        {isUS && stock.institutional_ownership && stock.institutional_ownership.total_holders > 0 && (
                                            <div style={{ marginTop: 12 }}>
                                                <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>기관 보유 현황</div>
                                                <div style={metricsGrid}>
                                                    <MetricCard label="기관수" value={String(stock.institutional_ownership.total_holders)} />
                                                    <MetricCard label="변동률" value={stock.institutional_ownership.change_pct ? `${stock.institutional_ownership.change_pct > 0 ? "+" : ""}${stock.institutional_ownership.change_pct}%` : "—"} color={(stock.institutional_ownership.change_pct || 0) > 0 ? "#22C55E" : (stock.institutional_ownership.change_pct || 0) < 0 ? "#FF4D4D" : "#888"} />
                                                </div>
                                            </div>
                                        )}
                                        {/* US: 공매도 현황 (yfinance 기반, NYSE/NASDAQ 공시) */}
                                        {isUS && stock.short_interest && (stock.short_interest.short_pct != null || stock.short_interest.days_to_cover != null) && (() => {
                                            const si = stock.short_interest
                                            const sp = Number(si.short_pct)
                                            const shortColor = sp >= 20 ? "#FF4D4D" : sp >= 10 ? "#FFD600" : "#B5FF19"
                                            const trendMap: Record<string, { label: string; color: string }> = {
                                                surge: { label: "급증", color: "#FF4D4D" },
                                                up: { label: "증가", color: "#FFD600" },
                                                flat: { label: "유지", color: C.textSecondary },
                                                down: { label: "감소", color: "#60A5FA" },
                                                drop: { label: "급감", color: "#22C55E" },
                                            }
                                            const tr = si.trend ? trendMap[si.trend] : null
                                            return (
                                                <div style={{ marginTop: 12 }}>
                                                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                                                        <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>공매도 현황</span>
                                                        {si.report_date && <span style={{ color: C.textTertiary, fontSize: 12 }}>기준 {si.report_date}</span>}
                                                    </div>
                                                    <div style={metricsGrid}>
                                                        {si.short_pct != null && (
                                                            <MetricCard label="Short % Float" value={`${si.short_pct}%`} color={shortColor} />
                                                        )}
                                                        {si.days_to_cover != null && (
                                                            <MetricCard label="Days to Cover" value={String(si.days_to_cover)} color={si.days_to_cover >= 5 ? "#FF4D4D" : si.days_to_cover >= 2 ? "#FFD600" : "#888"} />
                                                        )}
                                                        {tr && (
                                                            <MetricCard label="전월 대비" value={tr.label} color={tr.color} />
                                                        )}
                                                    </div>
                                                    {sp >= 20 && (
                                                        <div style={{ marginTop: 6, padding: "6px 10px", background: "#2A0000", border: "1px solid #5A0000", borderRadius: 6, color: "#FF9999", fontSize: 12 }}>
                                                            Short % 20% 초과 — 스퀴즈·하락 리스크 모두 주의
                                                        </div>
                                                    )}
                                                    {si.trend === "surge" && (
                                                        <div style={{ marginTop: 6, padding: "6px 10px", background: "#2A1800", border: "1px solid #5A3A00", borderRadius: 6, color: "#FFC266", fontSize: 12 }}>
                                                            공매도 전월比 +15% 이상 급증 — 기관 하락 베팅 확대
                                                        </div>
                                                    )}
                                                </div>
                                            )
                                        })()}
                                        {/* US: Finnhub 기업 뉴스 */}
                                        {isUS && Array.isArray(stock.company_news) && stock.company_news.length > 0 && (
                                            <div style={{ marginTop: 8 }}>
                                                <div style={{ color: "#60A5FA", fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Finnhub 뉴스</div>
                                                {stock.company_news.slice(0, 5).map((n: any, i: number) => (
                                                    <a key={i} href={n.url || "#"} target="_blank" rel="noopener noreferrer"
                                                        style={{ display: "block", padding: "6px 10px", background: C.bgElevated, borderRadius: 6, marginBottom: 3, textDecoration: "none" }}>
                                                        <span style={{ color: "#bbb", fontSize: 12, lineHeight: 1.4 }}>{n.title}</span>
                                                        {n.source && <span style={{ color: C.textTertiary, fontSize: 12, marginLeft: 6 }}>{n.source}</span>}
                                                    </a>
                                                ))}
                                            </div>
                                        )}
                                    </>
                                )
                            })()}

                            {detailTab === "macro" && (
                                <>
                                    <div style={metricsGrid}>
                                        <MetricCard label="시장 분위기" value={macro.market_mood?.label || "—"}
                                            color={macro.market_mood?.score >= 60 ? "#B5FF19" : macro.market_mood?.score <= 40 ? "#FF4D4D" : "#FFD600"} />
                                        <MetricCard label="USD/KRW" value={`${fmtLocale(macro.usd_krw?.value)}원`} />
                                        <MetricCard label="VIX" value={`${macro.vix?.value || "—"}`}
                                            color={macro.vix?.value > 25 ? "#FF4D4D" : macro.vix?.value < 18 ? "#B5FF19" : "#FFD600"} />
                                        <MetricCard label="WTI 원유" value={`$${macro.wti_oil?.value || "—"}`} />
                                        <MetricCard label="S&P500" value={`${macro.sp500?.change_pct >= 0 ? "+" : ""}${macro.sp500?.change_pct || 0}%`}
                                            color={macro.sp500?.change_pct >= 0 ? "#B5FF19" : "#FF4D4D"} />
                                        <MetricCard label="미10년(DGS10·표시)" value={`${macro.us_10y?.value || "—"}%`} />
                                        <MetricCard label="10년 출처" value={`${macro.us_10y?.source || "—"}`} />
                                        <MetricCard label="근원 CPI YoY" value={macro.fred?.core_cpi?.yoy_pct != null ? `${macro.fred.core_cpi.yoy_pct}%` : "—"}
                                            color="#A78BFA" />
                                        <MetricCard label="M2 YoY" value={macro.fred?.m2?.yoy_pct != null ? `${macro.fred.m2.yoy_pct}%` : "—"}
                                            color="#94A3B8" />
                                        <MetricCard label="VIXCLS(FRED)" value={macro.fred?.vix_close?.value != null ? `${macro.fred.vix_close.value}` : "—"}
                                            color="#F472B6" />
                                        <MetricCard label="한국10Y OECD" value={macro.fred?.korea_gov_10y?.value != null ? `${macro.fred.korea_gov_10y.value}%` : "—"}
                                            color="#22D3EE" />
                                        <MetricCard label="IMF할인율 KR" value={macro.fred?.korea_discount_rate?.value != null ? `${macro.fred.korea_discount_rate.value}%` : "—"}
                                            color="#94A3B8" />
                                        <MetricCard label="미 리세션확률" value={macro.fred?.us_recession_smoothed_prob?.pct != null ? `${macro.fred.us_recession_smoothed_prob.pct}%` : "—"}
                                            color={(macro.fred?.us_recession_smoothed_prob?.pct || 0) >= 25 ? "#EF4444" : "#888"} />
                                        <MetricCard label="나스닥" value={`${macro.nasdaq?.change_pct >= 0 ? "+" : ""}${macro.nasdaq?.change_pct || 0}%`}
                                            color={(macro.nasdaq?.change_pct || 0) >= 0 ? "#B5FF19" : "#FF4D4D"} />
                                        <MetricCard label="금" value={`$${fmtLocale(macro.gold?.value)}`} />
                                        <MetricCard label="금리 스프레드" value={macro.yield_spread ? `${macro.yield_spread.value}%p` : "—"}
                                            color={(macro.yield_spread?.value || 0) < 0 ? "#FF4D4D" : "#22C55E"} />
                                    </div>
                                    {macro.macro_diagnosis?.length > 0 && (
                                        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                                            <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>매크로 진단</span>
                                            {macro.macro_diagnosis.map((d: any, i: number) => (
                                                <div key={i} style={{ ...newsRow, borderLeft: `3px solid ${d.type === "positive" ? "#22C55E" : d.type === "risk" ? "#EF4444" : d.type === "warning" ? "#F59E0B" : "#555"}` }}>
                                                    <span style={{ color: "#bbb", fontSize: 12, lineHeight: "1.5" }}>{d.text}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                    <SectorTrendView sectorTrends={data?.sector_trends} />
                                </>
                            )}

                            {detailTab === "timing" && (() => {
                                const timing = stock?.timing || {}
                                const ts = timing.timing_score || 50
                                const actionColors: Record<string, string> = {
                                    STRONG_BUY: "#22C55E", BUY: "#86EFAC", HOLD: "#888",
                                    SELL: "#FCA5A5", STRONG_SELL: "#EF4444",
                                }
                                const ac = actionColors[timing.action] || "#888"
                                const gaugeR = 50, gaugeS = 8, gaugeC = 2 * Math.PI * gaugeR, gaugeP = (ts / 100) * gaugeC
                                return (
                                    <>
                                        <div style={{ display: "flex", alignItems: "center", gap: 20, padding: "8px 0" }}>
                                            <div style={{ position: "relative", width: 116, height: 116, flexShrink: 0 }}>
                                                <svg width={116} height={116} viewBox={`0 0 ${(gaugeR + gaugeS) * 2} ${(gaugeR + gaugeS) * 2}`}>
                                                    <circle cx={gaugeR + gaugeS} cy={gaugeR + gaugeS} r={gaugeR} fill="none" stroke="#222" strokeWidth={gaugeS} />
                                                    <circle cx={gaugeR + gaugeS} cy={gaugeR + gaugeS} r={gaugeR} fill="none" stroke={ac} strokeWidth={gaugeS}
                                                        strokeDasharray={gaugeC} strokeDashoffset={gaugeC - gaugeP} strokeLinecap="round"
                                                        transform={`rotate(-90 ${gaugeR + gaugeS} ${gaugeR + gaugeS})`}
                                                        style={{ transition: "stroke-dashoffset 0.5s ease" }} />
                                                </svg>
                                                <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                                                    <span style={{ color: ac, fontSize: 26, fontWeight: 900 }}>{ts}</span>
                                                    <span style={{ color: ac, fontSize: 12, fontWeight: 700 }}>{timing.label || "—"}</span>
                                                </div>
                                            </div>
                                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                                <span style={{ color: C.textPrimary, fontSize: 16, fontWeight: 800 }}>
                                                    {timing.label || "데이터 대기"}
                                                </span>
                                                <span style={{ color: C.textSecondary, fontSize: 12 }}>
                                                    {timing.action === "STRONG_BUY" ? "강한 매수 신호 — 적극적 진입 고려" :
                                                     timing.action === "BUY" ? "매수 우위 — 분할 매수 고려" :
                                                     timing.action === "HOLD" ? "방향성 불명확 — 관망 권고" :
                                                     timing.action === "SELL" ? "매도 우위 — 비중 축소 고려" :
                                                     timing.action === "STRONG_SELL" ? "강한 매도 신호 — 손절/청산 고려" :
                                                     "분석 데이터 수집 중"}
                                                </span>
                                            </div>
                                        </div>

                                        {/* 스코어 바 */}
                                        <div style={{ padding: "8px 0" }}>
                                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                                <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 600 }}>매도</span>
                                                <span style={{ color: C.textSecondary, fontSize: 12 }}>관망</span>
                                                <span style={{ color: "#22C55E", fontSize: 12, fontWeight: 600 }}>매수</span>
                                            </div>
                                            <div style={{ height: 8, background: "linear-gradient(to right, #EF4444, #F59E0B, #888, #86EFAC, #22C55E)", borderRadius: 6, position: "relative" }}>
                                                <div style={{
                                                    position: "absolute", top: -3, left: `${ts}%`, width: 14, height: 14,
                                                    borderRadius: 7, background: "#fff", border: `2px solid ${ac}`,
                                                    transform: "translateX(-50%)", transition: "left 0.5s ease",
                                                }} />
                                            </div>
                                        </div>

                                        {/* 판단 근거 */}
                                        {timing.reasons?.length > 0 && (
                                            <div style={{ marginTop: 8 }}>
                                                <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>판단 근거</span>
                                                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
                                                    {timing.reasons.map((r: string, i: number) => (
                                                        <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                                                            <span style={{ color: C.textTertiary, fontSize: 12, marginTop: 1 }}>•</span>
                                                            <span style={{ color: "#bbb", fontSize: 12, lineHeight: "1.5" }}>{r}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        <div style={{ ...newsRow, marginTop: 8 }}>
                                            <span style={{ color: C.textTertiary, fontSize: 12 }}>
                                                타이밍 스코어는 RSI, MACD, 볼린저밴드, 이동평균, 거래량, AI 상승확률, 수급을 종합한 점수입니다. 투자 판단의 참고용으로만 사용하세요.
                                            </span>
                                        </div>
                                    </>
                                )
                            })()}

                            {detailTab === "brain" && (() => {
                                const brain = stock?.verity_brain || {}
                                const bs = brain.brain_score ?? null
                                const fs = brain.fact_score || {}
                                const ss = brain.sentiment_score || {}
                                const vci = brain.vci || {}
                                const rf = brain.red_flags || {}
                                const gradeLabel = brain.grade_label || "—"
                                const grade = brain.grade || "WATCH"
                                const gradeColors: Record<string, string> = { STRONG_BUY: "#22C55E", BUY: "#B5FF19", WATCH: "#FFD600", CAUTION: "#F59E0B", AVOID: "#EF4444" }
                                const gc = gradeColors[grade] || "#888"
                                // §8 AVOID 의미: 펀더멘털 결함만
                                const AVOID_TOOLTIP = "AVOID 부여 조건: 펀더멘털 결함 (감사거절·분식·상폐 위험 등 has_critical) 또는 매크로 위기 cap. 단순 저점수는 CAUTION."
                                const OVERRIDE_LABELS: Record<string, string> = {
                                    contrarian_upgrade: "역발상↑", quadrant_unfavored: "분면불리↓",
                                    cape_bubble: "CAPE버블cap", panic_stage_3: "패닉3cap", panic_stage_4: "패닉4cap",
                                    vix_spread_panic: "VIX패닉cap", yield_defense: "수익률방어cap",
                                    sector_quadrant_drift: "섹터드리프트", ai_upside_relax: "AI호재완화",
                                }
                                const overrides: string[] = Array.isArray(stock?.overrides_applied) ? stock.overrides_applied : []
                                const sb = stock?.score_breakdown || null
                                const formatRedFlagDetail = (d: any): string => {
                                    if (!d || typeof d !== "object") return String(d || "")
                                    const text = d.text || String(d)
                                    const fresh = d.freshness
                                    if (!fresh || fresh === "FRESH") return text
                                    const days = d.days_since_event != null ? `${d.days_since_event}d` : ""
                                    return `${text} [${fresh === "EXPIRED" ? "EXPIRED" : "STALE"}${days ? " " + days : ""}]`
                                }
                                const vciVal = vci.vci ?? 0
                                const vciColor = vciVal > 15 ? "#B5FF19" : vciVal < -15 ? "#FF4D4D" : "#888"

                                if (bs === null) {
                                    return (
                                        <div style={{ color: C.textTertiary, fontSize: 12, textAlign: "center", padding: 20 }}>
                                            Verity Brain 데이터는 파이프라인 실행 후 표시됩니다
                                        </div>
                                    )
                                }

                                const brainR = 50, brainS = 8, brainC = 2 * Math.PI * brainR, brainP = (bs / 100) * brainC
                                return (
                                    <>
                                        <div style={{ display: "flex", alignItems: "center", gap: 20, padding: "8px 0" }}>
                                            <div style={{ position: "relative", width: 116, height: 116, flexShrink: 0 }}>
                                                <svg width={116} height={116} viewBox={`0 0 ${(brainR + brainS) * 2} ${(brainR + brainS) * 2}`}>
                                                    <circle cx={brainR + brainS} cy={brainR + brainS} r={brainR} fill="none" stroke="#222" strokeWidth={brainS} />
                                                    <circle cx={brainR + brainS} cy={brainR + brainS} r={brainR} fill="none" stroke={gc} strokeWidth={brainS}
                                                        strokeDasharray={brainC} strokeDashoffset={brainC - brainP} strokeLinecap="round"
                                                        transform={`rotate(-90 ${brainR + brainS} ${brainR + brainS})`}
                                                        style={{ transition: "stroke-dashoffset 0.5s ease" }} />
                                                </svg>
                                                <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                                                    <span style={{ color: gc, fontSize: 26, fontWeight: 900 }}>{bs}</span>
                                                    <span
                                                        style={{ color: gc, fontSize: 12, fontWeight: 700, cursor: grade === "AVOID" ? "help" : "default" }}
                                                        title={grade === "AVOID" ? AVOID_TOOLTIP : undefined}
                                                    >{gradeLabel}</span>
                                                </div>
                                            </div>
                                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                <span style={{ color: C.textPrimary, fontSize: 16, fontWeight: 800 }}>Verity Brain</span>
                                                <div style={{ display: "flex", gap: 12 }}>
                                                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                                        <span style={{ color: C.textTertiary, fontSize: 12 }}>팩트</span>
                                                        <span style={{ color: "#22C55E", fontSize: 18, fontWeight: 800 }}>{fs.score ?? "—"}</span>
                                                    </div>
                                                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                                        <span style={{ color: C.textTertiary, fontSize: 12 }}>심리</span>
                                                        <span style={{ color: "#60A5FA", fontSize: 18, fontWeight: 800 }}>{ss.score ?? "—"}</span>
                                                    </div>
                                                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                                        <span style={{ color: C.textTertiary, fontSize: 12 }}>VCI</span>
                                                        <span style={{ color: vciColor, fontSize: 18, fontWeight: 800 }}>{vciVal >= 0 ? "+" : ""}{vciVal}</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* VCI 시그널 */}
                                        {vci.signal && vci.signal !== "ALIGNED" && (
                                            <div style={{
                                                background: vciVal > 15 ? "rgba(181,255,25,0.06)" : "rgba(255,77,77,0.06)",
                                                border: `1px solid ${vciColor}40`,
                                                borderRadius: 10, padding: "10px 14px",
                                            }}>
                                                <span style={{ color: vciColor, fontSize: 12, fontWeight: 700 }}>
                                                    VCI {vciVal >= 0 ? "+" : ""}{vciVal}: {vci.label}
                                                </span>
                                            </div>
                                        )}

                                        {/* 13F 스마트머니 보너스 (US 종목 분기 데이터 존재 시) */}
                                        {typeof brain.inst_13f_bonus === "number" && brain.inst_13f_bonus > 0 && (
                                            <div style={{
                                                background: "rgba(96,165,250,0.06)",
                                                border: "1px solid #60A5FA40",
                                                borderRadius: 10, padding: "10px 14px",
                                            }}>
                                                <span style={{ color: "#60A5FA", fontSize: 12, fontWeight: 700 }}>
                                                    13F 스마트머니 +{brain.inst_13f_bonus}
                                                </span>
                                                <span style={{ color: C.textTertiary, fontSize: 12, marginLeft: 8 }}>
                                                    (기관 분기 포지션 보너스)
                                                </span>
                                            </div>
                                        )}

                                        {/* 팩트 컴포넌트 분해 */}
                                        {fs.components && (
                                            <div style={{ marginTop: 4 }}>
                                                <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>팩트 스코어 구성</span>
                                                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
                                                    {Object.entries(fs.components as Record<string, number>).map(([key, val]) => {
                                                        // §11/§U-* 신규 컴포넌트 라벨 추가
                                                        const labels: Record<string, string> = {
                                                            multi_factor: "멀티팩터", consensus: "내부모델합의", prediction: "AI예측",
                                                            backtest: "백테스트", timing: "타이밍",
                                                            commodity_margin: "원자재", export_trade: "수출입",
                                                            moat_quality: "모트(해자)", graham_value: "그레이엄가치", canslim_growth: "CANSLIM성장",
                                                            kis_analysis: "KIS분석", alpha_combined: "퀀트알파",
                                                            technical_mean_reversion: "기술MR(IC)", kr_fundamental_mean_reversion: "KR펀더멘털MR(DART)",
                                                            analyst_report: "증권사리포트", dart_health: "DART건전성",
                                                        }
                                                        const c = val >= 65 ? "#B5FF19" : val >= 45 ? "#FFD600" : "#FF4D4D"
                                                        return (
                                                            <div key={key} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                                                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                                                    <span style={{ color: C.textSecondary, fontSize: 12 }}>{labels[key] || key}</span>
                                                                    <span style={{ color: c, fontSize: 12, fontWeight: 700 }}>{val}</span>
                                                                </div>
                                                                <div style={{ height: 3, background: "#222", borderRadius: 2, overflow: "hidden" }}>
                                                                    <div style={{ height: "100%", width: `${val}%`, background: c, borderRadius: 2, transition: "width 0.5s ease" }} />
                                                                </div>
                                                            </div>
                                                        )
                                                    })}
                                                </div>
                                            </div>
                                        )}

                                        {/* 레드플래그 — §U-3 freshness 적용 (auto_avoid_detail 우선) */}
                                        {(rf.auto_avoid?.length > 0 || rf.downgrade?.length > 0 ||
                                          rf.auto_avoid_detail?.length > 0 || rf.downgrade_detail?.length > 0) && (
                                            <div style={{ marginTop: 4 }}>
                                                <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 700 }}>레드플래그</span>
                                                <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
                                                    {(Array.isArray(rf.auto_avoid_detail) ? rf.auto_avoid_detail : (rf.auto_avoid || []))
                                                        .map((f: any, i: number) => (
                                                        <div key={`a${i}`} style={{ background: "rgba(239,68,68,0.08)", borderRadius: 6, padding: "6px 10px", borderLeft: "3px solid #EF4444" }}>
                                                            <span style={{ color: "#FF6B6B", fontSize: 12 }}>⛔ {formatRedFlagDetail(f)}</span>
                                                        </div>
                                                    ))}
                                                    {(Array.isArray(rf.downgrade_detail) ? rf.downgrade_detail : (rf.downgrade || []))
                                                        .map((f: any, i: number) => (
                                                        <div key={`d${i}`} style={{ background: "rgba(234,179,8,0.06)", borderRadius: 6, padding: "6px 10px", borderLeft: "3px solid #EAB308" }}>
                                                            <span style={{ color: "#EAB308", fontSize: 12 }}>⚠️ {formatRedFlagDetail(f)}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {/* §11~§14 overrides_applied 감사 배지 */}
                                        {overrides.length > 0 && (
                                            <div style={{ marginTop: 4 }}>
                                                <span style={{ color: "#7DD3FC", fontSize: 12, fontWeight: 700 }}>적용된 오버라이드</span>
                                                <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
                                                    {overrides.map((o: string, i: number) => (
                                                        <span key={i} style={{
                                                            background: "rgba(125,211,252,0.10)", color: "#7DD3FC",
                                                            fontSize: 12, fontWeight: 600, padding: "3px 8px", borderRadius: 6,
                                                            border: "1px solid #7DD3FC40",
                                                        }} title={o}>
                                                            {OVERRIDE_LABELS[o] || o}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {/* §6 score_breakdown — XAI 점수 분해 (있을 때만) */}
                                        {sb && (
                                            <div style={{ marginTop: 4, background: C.bgPage, border: `1px solid ${C.border}`, borderRadius: 8, padding: 10 }}>
                                                <span style={{ color: C.textSecondary, fontSize: 12, fontWeight: 700 }}>점수 분해 (XAI)</span>
                                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, marginTop: 6, fontSize: 12, color: C.textSecondary }}>
                                                    <span>팩트 기여: <b style={{ color: "#22C55E" }}>{sb.fact_contribution}</b></span>
                                                    <span>심리 기여: <b style={{ color: "#60A5FA" }}>{sb.sentiment_contribution}</b></span>
                                                    <span>VCI 보너스: <b>{sb.vci_bonus >= 0 ? "+" : ""}{sb.vci_bonus}</b></span>
                                                    <span>캔들 보너스: <b>{sb.candle_bonus >= 0 ? "+" : ""}{sb.candle_bonus}</b></span>
                                                    <span>그룹 보너스: <b>{sb.gs_bonus >= 0 ? "+" : ""}{sb.gs_bonus}</b></span>
                                                    <span>기관 보너스: <b>{sb.inst_bonus >= 0 ? "+" : ""}{sb.inst_bonus}</b></span>
                                                </div>
                                                <div style={{ marginTop: 6, fontSize: 12, color: C.textSecondary }}>
                                                    합계 (페널티 전): <b style={{ color: C.textPrimary }}>{sb.raw_before_penalty}</b>
                                                    <span style={{ marginLeft: 8 }}>red_flag: <b style={{ color: "#FF6B6B" }}>{sb.penalties?.red_flag}</b></span>
                                                    {sb.penalties?.quadrant_unfavored !== 0 && (
                                                        <span style={{ marginLeft: 8 }}>분면불리: <b style={{ color: "#FF6B6B" }}>{sb.penalties?.quadrant_unfavored}</b></span>
                                                    )}
                                                </div>
                                                <div style={{ marginTop: 4, fontSize: 12, color: C.textSecondary }}>
                                                    raw: <b>{sb.raw_brain_score}</b> → 최종 (clip 0~100): <b style={{ color: gc }}>{sb.final_score}</b>
                                                </div>
                                                {Array.isArray(sb.grade_caps_applied) && sb.grade_caps_applied.length > 0 && (
                                                    <div style={{ marginTop: 4, fontSize: 12, color: "#F59E0B" }}>
                                                        등급 cap: {sb.grade_caps_applied.map((c: string) => OVERRIDE_LABELS[c] || c).join(" · ")}
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {/* §25 증권사 리포트 AI 요약 */}
                                        {stock?.analyst_report_summary?.report_count > 0 && (() => {
                                            const ar = stock.analyst_report_summary
                                            const dirColor = ar.signal_direction === "bullish" ? "#22C55E"
                                                : ar.signal_direction === "bearish" ? "#EF4444" : "#888"
                                            const dirLabel = ar.signal_direction === "bullish" ? "강세 우세"
                                                : ar.signal_direction === "bearish" ? "약세 우세" : "혼조"
                                            return (
                                                <div style={{ marginTop: 4, background: C.bgPage, border: `1px solid ${C.border}`, borderRadius: 8, padding: 10 }}>
                                                    <span style={{ color: "#60A5FA", fontSize: 12, fontWeight: 700 }}>
                                                        증권사 리포트 AI 요약 (최근 7일 {ar.report_count}건)
                                                    </span>
                                                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 6, fontSize: 12, color: C.textSecondary }}>
                                                        <span>센티먼트: <b style={{ color: C.textPrimary }}>{ar.analyst_sentiment_score}/100</b></span>
                                                        <span>평균 목표가: <b style={{ color: C.textPrimary }}>{ar.avg_target_price != null ? `${Number(ar.avg_target_price).toLocaleString()}원` : "—"}</b></span>
                                                        <span>의견 강도: <b style={{ color: dirColor }}>{ar.consensus_strength_index ?? "—"}</b> / {dirLabel}</span>
                                                        <span>실적 추정: <b>{ar.revision_ratio != null ? (ar.revision_ratio > 0.5 ? "상향 우세" : "하향/혼조") : "—"}</b></span>
                                                    </div>
                                                    {Array.isArray(ar.recent_reports) && ar.recent_reports.length > 0 && ar.recent_reports[0].summary && (
                                                        <div style={{ marginTop: 6, fontSize: 12, color: C.textSecondary, lineHeight: "1.5" }}>
                                                            <b style={{ color: "#60A5FA" }}>{ar.recent_reports[0].firm}</b>
                                                            <span style={{ marginLeft: 4 }}>— "{String(ar.recent_reports[0].summary).slice(0, 100)}"</span>
                                                        </div>
                                                    )}
                                                </div>
                                            )
                                        })()}

                                        {/* §25 DART 사업 건전성 AI 분석 */}
                                        {stock?.dart_business_analysis?.business_health_score != null && (() => {
                                            const da = stock.dart_business_analysis
                                            const moats = Array.isArray(da.moat_indicators) ? da.moat_indicators.slice(0, 3) : []
                                            return (
                                                <div style={{ marginTop: 4, background: C.bgPage, border: `1px solid ${C.border}`, borderRadius: 8, padding: 10 }}>
                                                    <span style={{ color: "#B5FF19", fontSize: 12, fontWeight: 700 }}>
                                                        사업 건전성 (DART AI)
                                                    </span>
                                                    <div style={{ display: "flex", gap: 12, marginTop: 6, fontSize: 12, color: C.textSecondary, alignItems: "center" }}>
                                                        <span>점수: <b style={{ color: "#B5FF19" }}>{da.business_health_score}/100</b></span>
                                                        <span>설비투자: <b style={{ color: C.textPrimary }}>{da.capex_direction || "—"}</b></span>
                                                    </div>
                                                    {moats.length > 0 && (
                                                        <div style={{ marginTop: 4, fontSize: 12, color: C.textSecondary, lineHeight: "1.5" }}>
                                                            해자: {moats.join(" · ")}
                                                        </div>
                                                    )}
                                                    {da.one_line_summary && (
                                                        <div style={{ marginTop: 4, fontSize: 12, color: C.textSecondary, fontStyle: "italic" }}>
                                                            {da.one_line_summary}
                                                        </div>
                                                    )}
                                                </div>
                                            )
                                        })()}

                                        {/* 판단 근거 */}
                                        {brain.reasoning && (
                                            <div style={{ ...newsRow, marginTop: 4 }}>
                                                <span style={{ color: C.textSecondary, fontSize: 12, lineHeight: "1.5" }}>{brain.reasoning}</span>
                                            </div>
                                        )}
                                    </>
                                )
                            })()}

                            {detailTab === "niche" && (() => {
                                const n = stock?.niche_data || {}
                                const mc = macro?.niche_credit || {}
                                const secFilings: any[] = stock?.sec_filings || []
                                const insiderSent = stock?.insider_sentiment || {}
                                const instOwn = stock?.institutional_ownership || {}
                                const finFacts = stock?.sec_financials || stock?.financial_facts || {}
                                const hasUSDeep = secFilings.length > 0 || insiderSent.mspr != null || instOwn.total_holders > 0 || finFacts.fcf != null
                                const hasAny =
                                    (n.trends && Object.keys(n.trends).length > 0) ||
                                    (n.legal && (n.legal.hits?.length > 0 || n.legal.risk_flag)) ||
                                    (n.credit && (n.credit.ig_spread_pp != null || n.credit.debt_ratio_pct != null || n.credit.note)) ||
                                    (mc.corporate_spread_vs_gov_pp != null || mc.alert) ||
                                    (isUS && hasUSDeep)

                                const nicheCardStyle: React.CSSProperties = { background: C.bgPage, border: `1px solid ${C.border}`, borderRadius: 10, padding: 12 }
                                const nicheChip: React.CSSProperties = { background: C.accentSoft, color: "#B5FF19", fontSize: 12, fontWeight: 800, padding: "2px 6px", borderRadius: 6, letterSpacing: 0.5 }
                                const nicheCardTitle: React.CSSProperties = { color: C.textPrimary, fontSize: 12, fontWeight: 700 }
                                const nicheRowStyle: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }
                                const nicheMuted: React.CSSProperties = { color: C.textTertiary, fontSize: 12, lineHeight: 1.5 }
                                const nicheBidRow: React.CSSProperties = { background: C.bgElevated, borderRadius: 8, padding: "8px 10px", border: `1px solid ${C.border}` }

                                return (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                                        <span style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700 }}>
                                            {isUS ? "Deep Intel" : "틈새 정보"} — {stock.name}
                                        </span>

                                        {!hasAny && (
                                            <div style={{ background: C.bgPage, borderRadius: 10, padding: 12, border: "1px dashed #333" }}>
                                                <span style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.5 }}>
                                                    틈새 데이터(트렌드·법 리스크·신용)는 백엔드 수집기 연동 후 표시됩니다.
                                                </span>
                                            </div>
                                        )}

                                        {/* Trends */}
                                        <div style={nicheCardStyle}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                <span style={nicheChip}>Trends</span>
                                                <span style={nicheCardTitle}>검색·관심도</span>
                                            </div>
                                            {n.trends?.keyword || n.trends?.interest_index != null ? (
                                                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                                    <div style={nicheRowStyle}>
                                                        <span style={{ color: C.textTertiary, fontSize: 12 }}>키워드</span>
                                                        <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700 }}>{n.trends.keyword || "—"}</span>
                                                    </div>
                                                    <div style={nicheRowStyle}>
                                                        <span style={{ color: C.textTertiary, fontSize: 12 }}>관심 지수</span>
                                                        <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700 }}>{String(n.trends.interest_index ?? "—")}</span>
                                                    </div>
                                                    {n.trends.week_change_pct != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: C.textTertiary, fontSize: 12 }}>주간 변화</span>
                                                            <span style={{ color: n.trends.week_change_pct >= 0 ? C.up : C.down, fontSize: 12, fontWeight: 700 }}>
                                                                {n.trends.week_change_pct >= 0 ? "+" : ""}{n.trends.week_change_pct}%
                                                            </span>
                                                        </div>
                                                    )}
                                                    {n.trends.note && <p style={{ color: "#777", fontSize: 12, lineHeight: 1.45, margin: "6px 0 0" }}>{n.trends.note}</p>}
                                                </div>
                                            ) : (
                                                <span style={nicheMuted}>주 1회 수집 예정 (소비·게임·뷰티 등)</span>
                                            )}
                                        </div>

                                        {/* Risk */}
                                        <div style={nicheCardStyle}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                <span style={nicheChip}>Risk</span>
                                                <span style={nicheCardTitle}>소송·리스크 키워드</span>
                                            </div>
                                            {n.legal?.risk_flag && (
                                                <div style={{ background: "#1A0A0A", border: "1px solid #3A1515", borderRadius: 8, padding: "8px 10px", marginBottom: 8 }}>
                                                    <span style={{ color: "#FF4D4D", fontSize: 12, fontWeight: 700 }}>리스크 플래그 ON</span>
                                                </div>
                                            )}
                                            {n.legal?.hits?.length > 0 ? (
                                                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                    {n.legal.hits.slice(0, 6).map((h: any, i: number) => (
                                                        <div key={i} style={{ background: C.bgElevated, borderRadius: 8, padding: "8px 10px" }}>
                                                            <span style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.45 }}>
                                                                {typeof h === "string" ? h : h != null ? String(h) : "—"}
                                                            </span>
                                                        </div>
                                                    ))}
                                                </div>
                                            ) : (
                                                <span style={nicheMuted}>뉴스 RSS에서 소송·판결·가압류 등 매칭 시 표시</span>
                                            )}
                                        </div>

                                        {/* Credit */}
                                        <div style={nicheCardStyle}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                <span style={nicheChip}>Credit</span>
                                                <span style={nicheCardTitle}>신용·유동성</span>
                                            </div>
                                            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                                {n.credit?.ig_spread_pp != null && (
                                                    <div style={nicheRowStyle}>
                                                        <span style={{ color: C.textTertiary, fontSize: 12 }}>IG 스프레드</span>
                                                        <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700 }}>{n.credit.ig_spread_pp}%p</span>
                                                    </div>
                                                )}
                                                {n.credit?.debt_ratio_pct != null && (
                                                    <div style={nicheRowStyle}>
                                                        <span style={{ color: C.textTertiary, fontSize: 12 }}>부채비율</span>
                                                        <span style={{ color: n.credit.debt_ratio_pct > 100 ? "#FF4D4D" : "#22C55E", fontSize: 12, fontWeight: 700 }}>{n.credit.debt_ratio_pct.toFixed(0)}%</span>
                                                    </div>
                                                )}
                                                {n.credit?.alert && (
                                                    <div style={{ color: "#FF9F40", fontSize: 12 }}>종목 단위 신용 알림</div>
                                                )}
                                                {n.credit?.note && <p style={{ color: "#777", fontSize: 12, lineHeight: 1.45, margin: "6px 0 0" }}>{n.credit.note}</p>}
                                                {(mc.corporate_spread_vs_gov_pp != null || mc.alert) && (
                                                    <div style={{ borderTop: "1px solid #222", marginTop: 4, paddingTop: 8 }}>
                                                        <span style={{ color: C.textTertiary, fontSize: 12, display: "block", marginBottom: 6 }}>시장 전체 (macro)</span>
                                                        {mc.corporate_spread_vs_gov_pp != null && (
                                                            <div style={nicheRowStyle}>
                                                                <span style={{ color: C.textTertiary, fontSize: 12 }}>회사채-국고 스프레드</span>
                                                                <span style={{ color: mc.alert || mc.corporate_spread_vs_gov_pp >= 2 ? "#FF4D4D" : "#22C55E", fontSize: 12, fontWeight: 700 }}>
                                                                    {mc.corporate_spread_vs_gov_pp}%p{mc.alert ? " · 경고" : ""}
                                                                </span>
                                                            </div>
                                                        )}
                                                        {mc.updated_at && <span style={{ color: C.textTertiary, fontSize: 12 }}>{mc.updated_at}</span>}
                                                    </div>
                                                )}
                                                {n.credit?.ig_spread_pp == null && n.credit?.debt_ratio_pct == null && mc.corporate_spread_vs_gov_pp == null && !mc.alert && (
                                                    <span style={nicheMuted}>중소형주는 개별 데이터가 없을 수 있음. 시장 전체 지표 위주.</span>
                                                )}
                                            </div>
                                        </div>

                                        {/* US: SEC Filings */}
                                        {isUS && (
                                            <div style={nicheCardStyle}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                    <span style={nicheChip}>SEC</span>
                                                    <span style={nicheCardTitle}>Recent Filings</span>
                                                </div>
                                                {secFilings.length > 0 ? (
                                                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                        {secFilings.slice(0, 5).map((f: any, i: number) => (
                                                            <div key={i} style={nicheBidRow}>
                                                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                                                    <span style={{ color: "#A78BFA", fontSize: 12, fontWeight: 700 }}>{f.form_type || "Filing"}</span>
                                                                    <span style={{ color: C.textTertiary, fontSize: 12 }}>{f.filed_date || ""}</span>
                                                                </div>
                                                                {f.description && <span style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.4 }}>{f.description}</span>}
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <span style={nicheMuted}>SEC 공시 데이터 없음</span>
                                                )}
                                            </div>
                                        )}

                                        {/* US: Insider Sentiment */}
                                        {isUS && (
                                            <div style={nicheCardStyle}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                    <span style={nicheChip}>Insider</span>
                                                    <span style={nicheCardTitle}>Insider Activity</span>
                                                </div>
                                                {insiderSent.mspr != null ? (
                                                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: C.textTertiary, fontSize: 12 }}>MSPR</span>
                                                            <span style={{ color: insiderSent.mspr > 0 ? "#22C55E" : insiderSent.mspr < 0 ? "#EF4444" : "#888", fontSize: 12, fontWeight: 700 }}>
                                                                {typeof insiderSent.mspr === "number" && Number.isFinite(insiderSent.mspr) ? `${insiderSent.mspr > 0 ? "+" : ""}${insiderSent.mspr.toFixed(4)}` : "—"}
                                                            </span>
                                                        </div>
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: C.textTertiary, fontSize: 12 }}>Buy Count</span>
                                                            <span style={{ color: "#22C55E", fontSize: 12, fontWeight: 700 }}>{insiderSent.positive_count || 0}</span>
                                                        </div>
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: C.textTertiary, fontSize: 12 }}>Sell Count</span>
                                                            <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 700 }}>{insiderSent.negative_count || 0}</span>
                                                        </div>
                                                        {insiderSent.net_shares != null && (
                                                            <div style={nicheRowStyle}>
                                                                <span style={{ color: C.textTertiary, fontSize: 12 }}>Net Shares</span>
                                                                <span style={{ color: insiderSent.net_shares > 0 ? C.up : C.down, fontSize: 12, fontWeight: 700 }}>
                                                                    {typeof insiderSent.net_shares === "number" ? insiderSent.net_shares.toLocaleString() : "—"}
                                                                </span>
                                                            </div>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <span style={nicheMuted}>내부자 거래 데이터 없음</span>
                                                )}
                                            </div>
                                        )}

                                        {/* US: Institutional & Financials */}
                                        {isUS && (
                                            <div style={nicheCardStyle}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                    <span style={nicheChip}>Inst</span>
                                                    <span style={nicheCardTitle}>Institutional & Financials</span>
                                                </div>
                                                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                                    {instOwn.total_holders > 0 && (
                                                        <>
                                                            <div style={nicheRowStyle}>
                                                                <span style={{ color: C.textTertiary, fontSize: 12 }}>Inst. Holders</span>
                                                                <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700 }}>{instOwn.total_holders}</span>
                                                            </div>
                                                            {instOwn.change_pct != null && (
                                                                <div style={nicheRowStyle}>
                                                                    <span style={{ color: C.textTertiary, fontSize: 12 }}>Holdings Chg</span>
                                                                    <span style={{ color: instOwn.change_pct > 0 ? C.up : C.down, fontSize: 12, fontWeight: 700 }}>
                                                                        {instOwn.change_pct > 0 ? "+" : ""}{instOwn.change_pct}%
                                                                    </span>
                                                                </div>
                                                            )}
                                                        </>
                                                    )}
                                                    {finFacts.fcf != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: C.textTertiary, fontSize: 12 }}>FCF</span>
                                                            <span style={{ color: finFacts.fcf >= 0 ? C.up : C.down, fontSize: 12, fontWeight: 700 }}>${(finFacts.fcf / 1e9).toFixed(1)}B</span>
                                                        </div>
                                                    )}
                                                    {finFacts.revenue != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: C.textTertiary, fontSize: 12 }}>Revenue</span>
                                                            <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700 }}>${(finFacts.revenue / 1e9).toFixed(1)}B</span>
                                                        </div>
                                                    )}
                                                    {finFacts.net_income != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: C.textTertiary, fontSize: 12 }}>Net Income</span>
                                                            <span style={{ color: finFacts.net_income >= 0 ? C.up : C.down, fontSize: 12, fontWeight: 700 }}>${(finFacts.net_income / 1e9).toFixed(1)}B</span>
                                                        </div>
                                                    )}
                                                    {finFacts.operating_income != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: C.textTertiary, fontSize: 12 }}>Op. Income</span>
                                                            <span style={{ color: finFacts.operating_income >= 0 ? C.up : C.down, fontSize: 12, fontWeight: 700 }}>${(finFacts.operating_income / 1e9).toFixed(1)}B</span>
                                                        </div>
                                                    )}
                                                    {finFacts.debt_ratio != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: C.textTertiary, fontSize: 12 }}>Debt Ratio</span>
                                                            <span style={{ color: finFacts.debt_ratio > 100 ? "#EF4444" : "#22C55E", fontSize: 12, fontWeight: 700 }}>
                                                                {finFacts.debt_ratio.toFixed(0)}%
                                                            </span>
                                                        </div>
                                                    )}
                                                    {!instOwn.total_holders && finFacts.fcf == null && (
                                                        <span style={nicheMuted}>기관/재무 데이터 대기 중</span>
                                                    )}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )
                            })()}

                            {detailTab === "property" && isUS && (() => {
                                const props10k = stock?.properties_10k || {}
                                const d = props10k.data || {}
                                const owned: any[] = Array.isArray(d.owned_properties) ? d.owned_properties : []
                                const leased: any[] = Array.isArray(d.leased_properties) ? d.leased_properties : []
                                const hq = d.headquarters || {}
                                const fc = d.facility_count || {}
                                const fmtSqft = (v: any) => {
                                    const n = Number(v)
                                    if (!n || !isFinite(n)) return "—"
                                    if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M sqft`
                                    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K sqft`
                                    return `${n} sqft`
                                }
                                const useColor = (u: string) => {
                                    const m: Record<string, string> = {
                                        "본사": "#FFD700", "HQ": "#FFD700",
                                        "공장": "#FF9800", "manufacturing": "#FF9800",
                                        "데이터센터": "#60A5FA", "data center": "#60A5FA",
                                        "R&D": "#A78BFA", "연구": "#A78BFA",
                                        "물류센터": "#22C55E", "물류": "#22C55E",
                                        "매장": "#F472B6", "retail": "#F472B6",
                                        "오피스": "#94A3B8", "office": "#94A3B8",
                                    }
                                    for (const k in m) if (u && String(u).toLowerCase().includes(k.toLowerCase())) return m[k]
                                    return "#888"
                                }
                                const hasAny = owned.length > 0 || leased.length > 0 || d.total_owned_sqft || d.total_leased_sqft
                                return (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                            <span style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700 }}>부동산 자산 — {stock.name}</span>
                                            {props10k.filed_date && (
                                                <span style={{ color: C.textTertiary, fontSize: 12 }}>10-K Item 2 · {props10k.filed_date}</span>
                                            )}
                                        </div>
                                        {hasAny ? (
                                            <>
                                                <div style={metricsGrid}>
                                                    <MetricCard label="소유 총면적" value={fmtSqft(d.total_owned_sqft)} color="#FFD700" />
                                                    <MetricCard label="임차 총면적" value={fmtSqft(d.total_leased_sqft)} color="#60A5FA" />
                                                    <MetricCard label="자산 수" value={`${fc.owned ?? owned.length}/${fc.leased ?? leased.length}`} />
                                                </div>
                                                {hq.location && (
                                                    <div style={{ padding: "10px 12px", background: C.bgElevated, border: `1px solid ${C.border}`, borderRadius: 8 }}>
                                                        <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, marginBottom: 4 }}>본사</div>
                                                        <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 600 }}>{hq.location}</div>
                                                        <div style={{ color: C.textSecondary, fontSize: 12, marginTop: 2 }}>
                                                            {hq.size_sqft ? fmtSqft(hq.size_sqft) + " · " : ""}
                                                            {hq.status || ""}
                                                            {hq.description ? ` — ${hq.description}` : ""}
                                                        </div>
                                                    </div>
                                                )}
                                                {owned.length > 0 && (
                                                    <div>
                                                        <div style={{ color: "#FFD700", fontSize: 12, fontWeight: 600, marginBottom: 6 }}>소유 부동산 ({owned.length})</div>
                                                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                            {owned.slice(0, 30).map((p: any, i: number) => (
                                                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "8px 10px", background: "#0B0B0B", borderLeft: `2px solid ${useColor(p.use)}`, borderRadius: 6 }}>
                                                                    <div style={{ flex: 1, minWidth: 0 }}>
                                                                        <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600 }}>{p.location || "—"}</div>
                                                                        <div style={{ color: C.textTertiary, fontSize: 12, marginTop: 2 }}>
                                                                            {p.use || "기타"}{p.segment ? ` · ${p.segment}` : ""}
                                                                            {p.notes ? ` · ${p.notes}` : ""}
                                                                        </div>
                                                                    </div>
                                                                    <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, whiteSpace: "nowrap", marginLeft: 8 }}>
                                                                        {fmtSqft(p.size_sqft)}
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                                {leased.length > 0 && (
                                                    <div>
                                                        <div style={{ color: "#60A5FA", fontSize: 12, fontWeight: 600, marginBottom: 6 }}>임차 부동산 ({leased.length})</div>
                                                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                            {leased.slice(0, 30).map((p: any, i: number) => (
                                                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "8px 10px", background: "#0B0B0B", borderLeft: `2px solid ${useColor(p.use)}`, borderRadius: 6 }}>
                                                                    <div style={{ flex: 1, minWidth: 0 }}>
                                                                        <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600 }}>{p.location || "—"}</div>
                                                                        <div style={{ color: C.textTertiary, fontSize: 12, marginTop: 2 }}>
                                                                            {p.use || "기타"}{p.segment ? ` · ${p.segment}` : ""}
                                                                            {p.notes ? ` · ${p.notes}` : ""}
                                                                        </div>
                                                                    </div>
                                                                    <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, whiteSpace: "nowrap", marginLeft: 8 }}>
                                                                        {fmtSqft(p.size_sqft)}
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                                {d.key_insights && (
                                                    <div style={{ padding: "10px 12px", background: "#0A1A0F", border: "1px solid #1A3A1F", borderRadius: 8 }}>
                                                        <div style={{ color: "#B5FF19", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>투자자 인사이트</div>
                                                        <div style={{ color: "#cce", fontSize: 12, lineHeight: 1.5 }}>{d.key_insights}</div>
                                                    </div>
                                                )}
                                                {d.summary_ko && (
                                                    <div style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.5, padding: "4px 0" }}>
                                                        {d.summary_ko}
                                                    </div>
                                                )}
                                                {props10k.source_url && (
                                                    <a href={props10k.source_url} target="_blank" rel="noopener noreferrer"
                                                        style={{ color: C.textTertiary, fontSize: 12, textDecoration: "none" }}>
                                                        원문 10-K ↗
                                                    </a>
                                                )}
                                                <div style={{ color: C.textTertiary, fontSize: 12, padding: "4px 0" }}>
                                                    SEC EDGAR 10-K Item 2 Properties 기준 (연 1회 공시). Gemini로 구조화 파싱.
                                                </div>
                                            </>
                                        ) : (
                                            <div style={{ color: C.textTertiary, fontSize: 12, textAlign: "center", padding: 20 }}>
                                                {props10k.accession
                                                    ? "최신 10-K에서 부동산 세부 정보를 찾지 못했습니다."
                                                    : "10-K Item 2 데이터가 아직 없습니다. full 모드 파이프라인 실행 후 표시됩니다."}
                                            </div>
                                        )}
                                    </div>
                                )
                            })()}

                            {detailTab === "property" && !isUS && (() => {
                                const prop =
                                    stock?.dart_financials?.property_assets ||
                                    stock?.dart_data?.property_assets ||
                                    stock?.property_assets ||
                                    {}
                                const items: any[] = prop.items || []
                                const totalCurr = prop.total_current || 0
                                const totalPrev = prop.total_previous || 0
                                const propRatio = prop.property_to_asset_pct
                                const totalChgPct = prop.total_change_pct
                                const fmtBillion = (v: number) => {
                                    if (v === 0) return "—"
                                    const billion = v / 1e8
                                    if (billion >= 10000) return `${(billion / 10000).toFixed(1)}조`
                                    return `${billion.toFixed(0)}억`
                                }
                                const fmtSqm = (v: any) => {
                                    const n = Number(v)
                                    if (!n || !isFinite(n)) return "—"
                                    if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M㎡`
                                    if (n >= 1e4) return `${(n / 1e4).toFixed(1)}만㎡`
                                    if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K㎡`
                                    return `${Math.round(n)}㎡`
                                }
                                const useColorKr = (u: string) => {
                                    const m: Record<string, string> = {
                                        "본사": "#FFD700", "공장": "#FF9800", "R&D": "#A78BFA",
                                        "연구": "#A78BFA", "물류": "#22C55E", "매장": "#F472B6",
                                        "투자부동산": "#60A5FA", "오피스": "#94A3B8",
                                    }
                                    for (const k in m) if (u && u.includes(k)) return m[k]
                                    return "#888"
                                }
                                const facRaw = stock?.facilities_dart || {}
                                const fac = facRaw.data || {}
                                const domestic: any[] = Array.isArray(fac.domestic_facilities) ? fac.domestic_facilities : []
                                const overseas: any[] = Array.isArray(fac.overseas_facilities) ? fac.overseas_facilities : []
                                const invProps: any[] = Array.isArray(fac.investment_properties) ? fac.investment_properties : []
                                const countryExp: Record<string, number> = (fac.country_exposure && typeof fac.country_exposure === "object") ? fac.country_exposure : {}
                                const expEntries = Object.entries(countryExp)
                                    .filter(([_, v]) => Number(v) > 0)
                                    .sort((a, b) => Number(b[1]) - Number(a[1]))
                                const hasFac = domestic.length > 0 || overseas.length > 0 || invProps.length > 0
                                return (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                                        <span style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700 }}>부동산 자산 — {stock.name}</span>

                                        {/* ESTATE LANDEX 가중평균 — 상장사 보유 부동산의 위치별 LANDEX 점수 */}
                                        <EstateLandexCard ticker={String(stock?.ticker || "").trim()} apiBase={api} />

                                        {/* 사업장/해외 거점 블록 */}
                                        {hasFac && (
                                            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                                    <span style={{ color: "#B5FF19", fontSize: 12, fontWeight: 700 }}>사업장·해외 거점</span>
                                                    {facRaw.rcept_dt && (
                                                        <span style={{ color: C.textTertiary, fontSize: 12 }}>사업보고서 {String(facRaw.rcept_dt).replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")}</span>
                                                    )}
                                                </div>

                                                {expEntries.length > 0 && (
                                                    <div>
                                                        <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>국가별 노출</div>
                                                        <div style={{ display: "flex", height: 10, borderRadius: 6, overflow: "hidden", background: C.bgElevated }}>
                                                            {expEntries.map(([cc, pct]) => {
                                                                const colorMap: Record<string, string> = {
                                                                    KR: "#B5FF19", US: "#60A5FA", CN: "#FF4D4D",
                                                                    VN: "#22C55E", JP: "#F472B6", IN: "#FFD700",
                                                                    DE: "#A78BFA", MX: "#FF9800", ID: "#14B8A6",
                                                                }
                                                                return (
                                                                    <div key={cc} title={`${cc} ${pct}%`}
                                                                        style={{ width: `${Number(pct)}%`, background: colorMap[cc] || "#888" }} />
                                                                )
                                                            })}
                                                        </div>
                                                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
                                                            {expEntries.map(([cc, pct]) => (
                                                                <span key={cc} style={{ color: C.textPrimary, fontSize: 12 }}>
                                                                    <b>{cc}</b> {Number(pct)}%
                                                                </span>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}

                                                <div style={metricsGrid}>
                                                    <MetricCard label="국내 사업장" value={`${domestic.length}개`} color="#B5FF19" />
                                                    <MetricCard label="해외 사업장" value={`${overseas.length}개`}
                                                        color={overseas.length > 0 ? "#60A5FA" : "#888"} />
                                                    {fac.total_domestic_sqm != null && (
                                                        <MetricCard label="국내 면적" value={fmtSqm(fac.total_domestic_sqm)} color="#ccc" />
                                                    )}
                                                </div>

                                                {fac.headquarters?.location && (
                                                    <div style={{ padding: "10px 12px", background: C.bgElevated, border: `1px solid ${C.border}`, borderRadius: 8 }}>
                                                        <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, marginBottom: 4 }}>본사</div>
                                                        <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 600 }}>{fac.headquarters.location}</div>
                                                        {fac.headquarters.ownership && (
                                                            <div style={{ color: C.textSecondary, fontSize: 12, marginTop: 2 }}>{fac.headquarters.ownership}</div>
                                                        )}
                                                    </div>
                                                )}

                                                {overseas.length > 0 && (
                                                    <div>
                                                        <div style={{ color: "#60A5FA", fontSize: 12, fontWeight: 600, marginBottom: 6 }}>해외 거점 ({overseas.length})</div>
                                                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                            {overseas.slice(0, 25).map((p: any, i: number) => (
                                                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "8px 10px", background: "#0B0B0B", borderLeft: `2px solid ${useColorKr(p.use)}`, borderRadius: 6 }}>
                                                                    <div style={{ flex: 1, minWidth: 0 }}>
                                                                        <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600 }}>
                                                                            {p.country ? <span style={{ color: "#60A5FA", marginRight: 6 }}>[{p.country_code || p.country}]</span> : null}
                                                                            {p.name || p.location || "—"}
                                                                        </div>
                                                                        <div style={{ color: C.textTertiary, fontSize: 12, marginTop: 2 }}>
                                                                            {[p.location, p.use, p.segment, p.ownership].filter(Boolean).join(" · ")}
                                                                            {p.notes ? ` · ${p.notes}` : ""}
                                                                        </div>
                                                                    </div>
                                                                    {p.size_sqm != null && (
                                                                        <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, whiteSpace: "nowrap", marginLeft: 8 }}>
                                                                            {fmtSqm(p.size_sqm)}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}

                                                {domestic.length > 0 && (
                                                    <div>
                                                        <div style={{ color: "#B5FF19", fontSize: 12, fontWeight: 600, marginBottom: 6 }}>국내 사업장 ({domestic.length})</div>
                                                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                            {domestic.slice(0, 30).map((p: any, i: number) => (
                                                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "8px 10px", background: "#0B0B0B", borderLeft: `2px solid ${useColorKr(p.use)}`, borderRadius: 6 }}>
                                                                    <div style={{ flex: 1, minWidth: 0 }}>
                                                                        <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600 }}>{p.name || p.location || "—"}</div>
                                                                        <div style={{ color: C.textTertiary, fontSize: 12, marginTop: 2 }}>
                                                                            {[p.location, p.use, p.segment, p.ownership].filter(Boolean).join(" · ")}
                                                                            {p.notes ? ` · ${p.notes}` : ""}
                                                                        </div>
                                                                    </div>
                                                                    {p.size_sqm != null && (
                                                                        <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, whiteSpace: "nowrap", marginLeft: 8 }}>
                                                                            {fmtSqm(p.size_sqm)}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}

                                                {invProps.length > 0 && (
                                                    <div>
                                                        <div style={{ color: "#FFD700", fontSize: 12, fontWeight: 600, marginBottom: 6 }}>투자부동산 상세 ({invProps.length})</div>
                                                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                            {invProps.slice(0, 30).map((p: any, i: number) => (
                                                                <div key={i} style={{ padding: "8px 10px", background: "#0B0B0B", borderLeft: "2px solid #FFD700", borderRadius: 6 }}>
                                                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                                                                        <div style={{ flex: 1, minWidth: 0 }}>
                                                                            <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600 }}>{p.name || p.location}</div>
                                                                            <div style={{ color: C.textTertiary, fontSize: 12, marginTop: 2 }}>
                                                                                {p.location ? `${p.location} · ` : ""}
                                                                                {p.size_sqm != null ? `${fmtSqm(p.size_sqm)} · ` : ""}
                                                                                {p.occupancy_rate != null ? `임대율 ${p.occupancy_rate}%` : ""}
                                                                            </div>
                                                                        </div>
                                                                        {p.fair_value_krw != null && (
                                                                            <div style={{ color: "#FFD700", fontSize: 12, fontWeight: 700, whiteSpace: "nowrap", marginLeft: 8 }}>
                                                                                {fmtBillion(Number(p.fair_value_krw))}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                    {Array.isArray(p.major_tenants) && p.major_tenants.length > 0 && (
                                                                        <div style={{ color: C.textSecondary, fontSize: 12, marginTop: 4 }}>임차인: {p.major_tenants.join(", ")}</div>
                                                                    )}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}

                                                {fac.geopolitical_risk && (
                                                    <div style={{ padding: "10px 12px", background: "#2A1800", border: "1px solid #5A3A00", borderRadius: 8 }}>
                                                        <div style={{ color: "#FFC266", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>지정학 리스크</div>
                                                        <div style={{ color: "#FFE0B0", fontSize: 12, lineHeight: 1.5 }}>{fac.geopolitical_risk}</div>
                                                    </div>
                                                )}
                                                {fac.key_insights && (
                                                    <div style={{ padding: "10px 12px", background: "#0A1A0F", border: "1px solid #1A3A1F", borderRadius: 8 }}>
                                                        <div style={{ color: "#B5FF19", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>투자자 인사이트</div>
                                                        <div style={{ color: "#cce", fontSize: 12, lineHeight: 1.5 }}>{fac.key_insights}</div>
                                                    </div>
                                                )}
                                                {fac.summary_ko && (
                                                    <div style={{ color: C.textSecondary, fontSize: 12, lineHeight: 1.5 }}>{fac.summary_ko}</div>
                                                )}
                                                <div style={{ color: C.textTertiary, fontSize: 12 }}>
                                                    OpenDART 사업보고서 "II. 사업의 내용" 기준, Gemini 구조화 파싱.
                                                </div>
                                            </div>
                                        )}

                                        {/* 재무상태표 계정 합계 — 사업장 정보와 독립적인 장부가 요약 */}
                                        {items.length > 0 ? (
                                            <>
                                                <div style={metricsGrid}>
                                                    <MetricCard label="부동산 총계" value={fmtBillion(totalCurr)} color="#FFD700" />
                                                    <MetricCard label="전년 대비" value={totalChgPct != null ? `${totalChgPct >= 0 ? "+" : ""}${totalChgPct}%` : "—"}
                                                        color={totalChgPct > 0 ? "#22C55E" : totalChgPct < 0 ? "#EF4444" : "#888"} />
                                                    <MetricCard label="자산 대비 비중" value={propRatio != null ? `${propRatio}%` : "—"} color="#60A5FA" />
                                                </div>
                                                <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 10 }}>
                                                    <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>계정과목별 상세</span>
                                                    {items.map((item: any, idx: number) => (
                                                        <div key={idx} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid #1a1a1a" }}>
                                                            <div>
                                                                <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600 }}>{item.account}</span>
                                                                <div style={{ color: C.textTertiary, fontSize: 12, marginTop: 2 }}>
                                                                    전기: {fmtBillion(item.previous)}
                                                                </div>
                                                            </div>
                                                            <div style={{ textAlign: "right" }}>
                                                                <span style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700 }}>{fmtBillion(item.current)}</span>
                                                                {item.change_pct != null && (
                                                                    <div style={{ color: item.change_pct >= 0 ? C.up : C.down, fontSize: 12, fontWeight: 600 }}>
                                                                        {item.change_pct >= 0 ? "+" : ""}{item.change_pct}%
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                                <div style={{ color: C.textTertiary, fontSize: 12, padding: "8px 0" }}>
                                                    OpenDART 재무상태표 기준. 투자부동산·토지·건물·사용권자산 합산.
                                                </div>
                                            </>
                                        ) : !hasFac ? (
                                            <div style={{ color: C.textTertiary, fontSize: 12, textAlign: "center", padding: 20 }}>
                                                {stock?.dart_financials
                                                    ? "OpenDART 재무제표·사업보고서에서 부동산 정보를 확인할 수 없습니다."
                                                    : "DART 데이터가 아직 없습니다. full 모드 파이프라인 실행 후 표시됩니다."}
                                            </div>
                                        ) : null}
                                    </div>
                                )
                            })()}

                            {detailTab === "quant" && (() => {
                                const qfScalar = stock?.multi_factor?.quant_factors || {}
                                const qfFull = stock?.quant_factors || {}

                                const toNum = (v: any, fallback = 50) => typeof v === "number" ? v : (typeof v === "object" && v != null ? (v.momentum_score ?? v.quality_score ?? v.volatility_score ?? v.mean_reversion_score ?? fallback) : fallback)
                                const mom = toNum(qfScalar.momentum ?? qfFull.momentum?.momentum_score)
                                const qual = toNum(qfScalar.quality ?? qfFull.quality?.quality_score)
                                const vol = toNum(qfScalar.volatility ?? qfFull.volatility?.volatility_score)
                                const mr = toNum(qfScalar.mean_reversion ?? qfFull.mean_reversion?.mean_reversion_score)

                                const momData = qfFull.momentum || {}
                                const qualData = qfFull.quality || {}
                                const volData = qfFull.volatility || {}
                                const mrData = qfFull.mean_reversion || {}

                                const qColor = (v: number) => v >= 70 ? "#B5FF19" : v >= 50 ? "#FFD600" : "#FF4D4D"

                                const QuantBar = ({ label, score, signals }: { label: string; score: number; signals?: string[] }) => (
                                    <div style={{ marginBottom: 14 }}>
                                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                                            <span style={{ color: C.textSecondary, fontSize: 12, fontWeight: 600 }}>{label}</span>
                                            <span style={{ color: qColor(score), fontSize: 14, fontWeight: 800 }}>{score}</span>
                                        </div>
                                        <div style={{ height: 6, background: C.bgElevated, borderRadius: 3 }}>
                                            <div style={{ height: 6, borderRadius: 3, background: qColor(score), width: `${score}%`, transition: "width 0.3s" }} />
                                        </div>
                                        {signals && signals.length > 0 && (
                                            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 5 }}>
                                                {signals.slice(0, 3).map((s: string, i: number) => (
                                                    <span key={i} style={{ ...signalTag, background: "#0A1A0D", border: "1px solid #1A2A1A", fontSize: 12 }}>{s}</span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )

                                const statArb = data?.stat_arb || {}
                                const pairs = statArb.actionable_pairs || []
                                const factorIc = data?.factor_ic || {}
                                const icRanking = factorIc.ranking || []

                                return (
                                    <>
                                        <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, marginBottom: 8 }}>학술 퀀트 팩터</div>
                                        <QuantBar label="모멘텀 (Jegadeesh & Titman)" score={mom} signals={momData.signals} />
                                        <QuantBar label="퀄리티 (Piotroski F-Score)" score={qual} signals={qualData.signals} />
                                        <QuantBar label="저변동성 (Ang et al.)" score={vol} signals={volData.signals} />
                                        <QuantBar label="평균회귀 (Hurst)" score={mr} signals={mrData.signals} />

                                        {qualData.piotroski_f !== undefined && (
                                            <div style={{ marginTop: 12, padding: "8px 10px", background: C.bgPage, borderRadius: 8, border: `1px solid ${C.border}` }}>
                                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                                    <span style={{ color: C.textSecondary, fontSize: 12 }}>Piotroski F-Score</span>
                                                    <span style={{ color: qualData.piotroski_f >= 7 ? "#B5FF19" : qualData.piotroski_f >= 4 ? "#FFD600" : "#FF4D4D", fontSize: 13, fontWeight: 800 }}>{qualData.piotroski_f}/9</span>
                                                </div>
                                                {qualData.altman?.z_score != null && (
                                                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                                                        <span style={{ color: C.textSecondary, fontSize: 12 }}>Altman Z-Score</span>
                                                        <span style={{ color: qualData.altman.zone === "safe" ? "#B5FF19" : qualData.altman.zone === "grey" ? "#FFD600" : "#FF4D4D", fontSize: 13, fontWeight: 800 }}>{qualData.altman.z_score}</span>
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {mrData.metrics?.hurst != null && (
                                            <div style={{ marginTop: 8, padding: "6px 10px", background: C.bgPage, borderRadius: 8, border: `1px solid ${C.border}` }}>
                                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                                    <span style={{ color: C.textSecondary, fontSize: 12 }}>Hurst Exponent</span>
                                                    <span style={{ color: mrData.metrics.hurst < 0.5 ? "#B5FF19" : "#FF4D4D", fontSize: 13, fontWeight: 800 }}>{mrData.metrics.hurst.toFixed(3)}</span>
                                                </div>
                                                <span style={{ color: C.textTertiary, fontSize: 12 }}>{mrData.metrics.hurst < 0.5 ? "회귀형 — 평균회귀 전략 유리" : "추세형 — 모멘텀 전략 유리"}</span>
                                            </div>
                                        )}

                                        {pairs.length > 0 && (
                                            <div style={{ marginTop: 16, borderTop: `1px solid ${C.border}`, paddingTop: 12 }}>
                                                <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>통계적 차익거래 페어</span>
                                                {pairs.slice(0, 5).map((p: any, i: number) => (
                                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #111" }}>
                                                        <span style={{ color: C.textPrimary, fontSize: 12 }}>{p.name_a} ↔ {p.name_b}</span>
                                                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                                            <span style={{ color: Math.abs(p.spread_zscore) >= 2 ? "#B5FF19" : "#888", fontSize: 12, fontWeight: 700 }}>Z={p.spread_zscore?.toFixed(2)}</span>
                                                            <span style={{ fontSize: 12, color: C.textTertiary, background: C.bgElevated, padding: "2px 6px", borderRadius: 6 }}>{p.spread_signal}</span>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {icRanking.length > 0 && (() => {
                                            const thStyle: React.CSSProperties = { padding: "5px 6px", textAlign: "left", fontSize: 12, fontWeight: 700, color: C.textTertiary, borderBottom: `1px solid ${C.border}` }
                                            const tdStyle: React.CSSProperties = { padding: "4px 6px", fontSize: 12, borderBottom: "1px solid #111" }
                                            const sigFactors = factorIc.significant_factors || factorIc.significant || []
                                            const decFactors = factorIc.decaying_factors || factorIc.decaying || []
                                            const monthly = factorIc.monthly_rollup || {}
                                            const mFactors = monthly.by_factor || []

                                            return (
                                                <div style={{ marginTop: 16, borderTop: `1px solid ${C.border}`, paddingTop: 12 }}>
                                                    <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>팩터 예측력 순위 (ICIR)</span>
                                                    <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 8 }}>
                                                        <thead>
                                                            <tr>
                                                                <th style={thStyle}>#</th>
                                                                <th style={thStyle}>팩터</th>
                                                                <th style={{ ...thStyle, textAlign: "right" }}>ICIR</th>
                                                                <th style={{ ...thStyle, textAlign: "center" }}>상태</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {icRanking.slice(0, 10).map((r: any, i: number) => {
                                                                const isSig = sigFactors.includes(r.factor)
                                                                const isDec = decFactors.includes(r.factor)
                                                                return (
                                                                    <tr key={i}>
                                                                        <td style={{ ...tdStyle, color: C.textTertiary, fontSize: 12 }}>{i + 1}</td>
                                                                        <td style={{ ...tdStyle, color: C.textPrimary }}>{r.factor}</td>
                                                                        <td style={{ ...tdStyle, textAlign: "right", color: Math.abs(r.icir) > 0.5 ? "#B5FF19" : "#888", fontWeight: 700 }}>{r.icir?.toFixed(3)}</td>
                                                                        <td style={{ ...tdStyle, textAlign: "center", fontSize: 12 }}>
                                                                            {isDec && <span style={{ color: "#FF4D4D" }}>붕괴</span>}
                                                                            {isSig && !isDec && <span style={{ color: "#B5FF19" }}>유의미</span>}
                                                                        </td>
                                                                    </tr>
                                                                )
                                                            })}
                                                        </tbody>
                                                    </table>

                                                    {mFactors.length > 0 && (
                                                        <div style={{ marginTop: 12 }}>
                                                            <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>{monthly.period_label || "월간"} 평균 ICIR ({monthly.obs_entries || 0}일 기준)</span>
                                                            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 6 }}>
                                                                <thead>
                                                                    <tr>
                                                                        <th style={thStyle}>#</th>
                                                                        <th style={thStyle}>팩터</th>
                                                                        <th style={{ ...thStyle, textAlign: "right" }}>평균 ICIR</th>
                                                                        <th style={{ ...thStyle, textAlign: "right" }}>관측</th>
                                                                    </tr>
                                                                </thead>
                                                                <tbody>
                                                                    {mFactors.slice(0, 10).map((f: any, i: number) => (
                                                                        <tr key={i}>
                                                                            <td style={{ ...tdStyle, color: C.textTertiary, fontSize: 12 }}>{i + 1}</td>
                                                                            <td style={{ ...tdStyle, color: C.textPrimary }}>{f.factor}</td>
                                                                            <td style={{ ...tdStyle, textAlign: "right", color: Math.abs(f.avg_icir) > 0.5 ? "#B5FF19" : "#888", fontWeight: 700 }}>{f.avg_icir?.toFixed(3)}</td>
                                                                            <td style={{ ...tdStyle, textAlign: "right", color: C.textTertiary, fontSize: 12 }}>{f.obs_days}일</td>
                                                                        </tr>
                                                                    ))}
                                                                </tbody>
                                                            </table>
                                                        </div>
                                                    )}
                                                </div>
                                            )
                                        })()}
                                    </>
                                )
                            })()}

                            {detailTab === "group" && (() => {
                                const gs = stock?.group_structure
                                if (!gs || (!gs.parent && (!gs.subsidiaries || gs.subsidiaries.length === 0))) {
                                    return <div style={{ color: C.textTertiary, fontSize: 13, textAlign: "center" as const, padding: 32 }}>관계회사 데이터가 없습니다</div>
                                }
                                const nav = gs.nav_analysis || {}
                                const subs: any[] = gs.subsidiaries || []
                                const discountPct = nav.nav_discount_pct
                                const discountColor = discountPct == null ? "#666" : discountPct < -10 ? "#FF4D4D" : discountPct < 0 ? "#FFD600" : "#B5FF19"
                                const discountLabel = discountPct == null ? "-" : discountPct > 0 ? `+${discountPct}% 할증` : `${discountPct}% 할인`

                                const nodeStyle: React.CSSProperties = {
                                    background: "#1a1a1a", border: "1px solid #333", borderRadius: 10,
                                    padding: "10px 14px", textAlign: "center" as const, minWidth: 120,
                                }
                                const activeNodeStyle: React.CSSProperties = {
                                    ...nodeStyle, border: "1.5px solid #B5FF19", background: C.bgElevated,
                                }
                                const edgeLabel: React.CSSProperties = {
                                    color: "#B5FF19", fontSize: 12, fontWeight: 700, padding: "2px 6px",
                                    background: "#000", borderRadius: 6, position: "relative" as const,
                                }
                                const lineV: React.CSSProperties = {
                                    width: 1, height: 20, background: "#444", margin: "0 auto",
                                }

                                const shareholders: any[] = gs.major_shareholders || (gs.parent ? [gs.parent] : [])
                                const linkBtn: React.CSSProperties = {
                                    display: "inline-flex", alignItems: "center", gap: 3,
                                    background: C.bgElevated, border: "1px solid #333", borderRadius: 6,
                                    padding: "2px 6px", color: "#B5FF19", fontSize: 12, fontWeight: 600,
                                    cursor: "pointer", textDecoration: "none",
                                }

                                return (
                                    <>
                                        {/* 구조도 — 상위 대주주 (최대 5명) */}
                                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 0, marginBottom: 16 }}>
                                            {shareholders.length > 0 && (
                                                <>
                                                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const, justifyContent: "center", marginBottom: 0 }}>
                                                        {shareholders.slice(0, 5).map((sh: any, si: number) => {
                                                            const links = sh.links || {}
                                                            return (
                                                                <div key={si} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 0 }}>
                                                                    <div style={{ ...nodeStyle, minWidth: 110, maxWidth: 160 }}>
                                                                        <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700 }}>{sh.name}</div>
                                                                        {sh.ownership_pct > 0 && <div style={{ color: "#B5FF19", fontSize: 12, fontWeight: 700 }}>{sh.ownership_pct}%</div>}
                                                                        {sh.market_cap && <div style={{ color: C.textSecondary, fontSize: 12 }}>시총: {sh.market_cap.toLocaleString()}억</div>}
                                                                        {sh.relate && <div style={{ color: C.textTertiary, fontSize: 12 }}>{sh.relate}</div>}
                                                                        {(links.official || links.namuwiki || links.profile) && (
                                                                            <div style={{ display: "flex", gap: 3, marginTop: 4, flexWrap: "wrap" as const, justifyContent: "center" }}>
                                                                                {links.official && <a href={links.official} target="_blank" rel="noopener noreferrer" style={linkBtn}>공식</a>}
                                                                                {links.namuwiki && <a href={links.namuwiki} target="_blank" rel="noopener noreferrer" style={linkBtn}>나무위키</a>}
                                                                                {links.profile && <a href={links.profile} target="_blank" rel="noopener noreferrer" style={linkBtn}>회사소개</a>}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                    <div style={lineV} />
                                                                </div>
                                                            )
                                                        })}
                                                    </div>
                                                    <div style={{ display: "flex", gap: 16, justifyContent: "center", marginBottom: 0 }}>
                                                        {shareholders.slice(0, 5).map((_: any, si: number) => (
                                                            <div key={si} style={{ width: 1, height: 12, background: "#444" }} />
                                                        ))}
                                                    </div>
                                                </>
                                            )}

                                            <div style={activeNodeStyle}>
                                                <div style={{ color: "#B5FF19", fontSize: 14, fontWeight: 800 }}>{stock.name}</div>
                                                {gs.market_cap_억 && <div style={{ color: C.textSecondary, fontSize: 12 }}>시총: {gs.market_cap_억.toLocaleString()}억</div>}
                                                {gs.group_name && <div style={{ color: C.textTertiary, fontSize: 12 }}>{gs.group_name} 그룹</div>}
                                            </div>

                                            {subs.length > 0 && (
                                                <>
                                                    <div style={lineV} />
                                                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const, justifyContent: "center", maxWidth: "100%" }}>
                                                        {subs.slice(0, 8).map((sub: any, si: number) => {
                                                            const subLinks = sub.links || {}
                                                            return (
                                                                <div key={si} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 0 }}>
                                                                    <div style={edgeLabel}>{sub.ownership_pct}%</div>
                                                                    <div style={lineV} />
                                                                    <div style={{ ...nodeStyle, minWidth: 100, maxWidth: 140 }}>
                                                                        <div style={{ color: sub.is_listed ? "#fff" : "#999", fontSize: 12, fontWeight: 600 }}>{sub.name}</div>
                                                                        {sub.is_listed && sub.market_cap_억 && <div style={{ color: C.textSecondary, fontSize: 12 }}>시총: {sub.market_cap_억.toLocaleString()}억</div>}
                                                                        {sub.stake_value_억 ? <div style={{ color: "#B5FF19", fontSize: 12 }}>지분가치: {sub.stake_value_억.toLocaleString()}억</div> : null}
                                                                        {!sub.is_listed && <div style={{ color: C.textTertiary, fontSize: 8 }}>비상장</div>}
                                                                        {(subLinks.official || subLinks.namuwiki || subLinks.profile) && (
                                                                            <div style={{ display: "flex", gap: 3, marginTop: 3, flexWrap: "wrap" as const, justifyContent: "center" }}>
                                                                                {subLinks.official && <a href={subLinks.official} target="_blank" rel="noopener noreferrer" style={linkBtn}>공식</a>}
                                                                                {subLinks.namuwiki && <a href={subLinks.namuwiki} target="_blank" rel="noopener noreferrer" style={linkBtn}>나무위키</a>}
                                                                                {subLinks.profile && <a href={subLinks.profile} target="_blank" rel="noopener noreferrer" style={linkBtn}>회사소개</a>}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            )
                                                        })}
                                                    </div>
                                                </>
                                            )}
                                        </div>

                                        {/* NAV 분석 카드 */}
                                        {nav.sum_of_parts_억 > 0 && (
                                            <div style={{ background: "#1a1a1a", border: `1px solid ${C.border}`, borderRadius: 10, padding: 14, marginTop: 8 }}>
                                                <div style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, marginBottom: 10 }}>NAV 분석 (Sum-of-Parts)</div>
                                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                                                    <div>
                                                        <div style={{ color: C.textTertiary, fontSize: 12 }}>상장 지분가치</div>
                                                        <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700 }}>{(nav.listed_stake_value_억 || 0).toLocaleString()}억</div>
                                                    </div>
                                                    <div>
                                                        <div style={{ color: C.textTertiary, fontSize: 12 }}>비상장 지분가치</div>
                                                        <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700 }}>{(nav.unlisted_stake_value_억 || 0).toLocaleString()}억</div>
                                                    </div>
                                                    <div>
                                                        <div style={{ color: C.textTertiary, fontSize: 12 }}>지분합산 NAV</div>
                                                        <div style={{ color: "#B5FF19", fontSize: 14, fontWeight: 700 }}>{nav.sum_of_parts_억.toLocaleString()}억</div>
                                                    </div>
                                                    <div>
                                                        <div style={{ color: C.textTertiary, fontSize: 12 }}>NAV 대비</div>
                                                        <div style={{ color: discountColor, fontSize: 14, fontWeight: 700 }}>{discountLabel}</div>
                                                    </div>
                                                </div>
                                            </div>
                                        )}

                                        {/* Sensitivity 테이블 */}
                                        {nav.sensitivity && nav.sensitivity.length > 0 && (
                                            <div style={{ marginTop: 12 }}>
                                                <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>자회사 변동 영향도</div>
                                                {nav.sensitivity.map((s: any, si: number) => (
                                                    <div key={si} style={{
                                                        display: "flex", justifyContent: "space-between", alignItems: "center",
                                                        padding: "6px 0", borderBottom: "1px solid #1a1a1a",
                                                    }}>
                                                        <div>
                                                            <span style={{ color: C.textPrimary, fontSize: 12 }}>{s.subsidiary}</span>
                                                            {s.stake_value_억 && <span style={{ color: C.textTertiary, fontSize: 12, marginLeft: 6 }}>{s.stake_value_억.toLocaleString()}억</span>}
                                                        </div>
                                                        <div style={{ color: "#B5FF19", fontSize: 12, fontWeight: 600 }}>
                                                            1% → {(s.impact_per_1pct * 100).toFixed(2)}%
                                                        </div>
                                                    </div>
                                                ))}
                                                <div style={{ color: C.textTertiary, fontSize: 12, marginTop: 6, lineHeight: 1.4 }}>
                                                    자회사 주가 1% 변동 시 모회사 NAV에 미치는 영향(%)
                                                </div>
                                            </div>
                                        )}

                                        {/* 자회사 상세 리스트 */}
                                        {subs.length > 0 && (
                                            <div style={{ marginTop: 12 }}>
                                                <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>타법인 출자 현황 ({subs.length}건)</div>
                                                {subs.map((sub: any, si: number) => (
                                                    <div key={si} style={{
                                                        display: "flex", justifyContent: "space-between", alignItems: "center",
                                                        padding: "8px 0", borderBottom: "1px solid #1a1a1a",
                                                    }}>
                                                        <div style={{ flex: 1 }}>
                                                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                                                <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600 }}>{sub.name}</span>
                                                                {sub.is_listed && <span style={{ color: "#B5FF19", fontSize: 8, border: "1px solid #B5FF19", borderRadius: 3, padding: "1px 4px" }}>상장</span>}
                                                            </div>
                                                            <div style={{ color: C.textTertiary, fontSize: 12, marginTop: 2 }}>
                                                                지분 {sub.ownership_pct}% · 장부가 {sub.book_value_억}억
                                                                {sub.revenue_억 ? ` · 매출 ${sub.revenue_억}억` : ""}
                                                            </div>
                                                        </div>
                                                        <div style={{ textAlign: "right" as const }}>
                                                            {sub.stake_value_억 ? (
                                                                <div style={{ color: "#B5FF19", fontSize: 13, fontWeight: 700 }}>{sub.stake_value_억.toLocaleString()}억</div>
                                                            ) : (
                                                                <div style={{ color: C.textTertiary, fontSize: 12 }}>-</div>
                                                            )}
                                                            {sub.is_listed && sub.price && (
                                                                <div style={{ color: C.textSecondary, fontSize: 12 }}>{sub.price.toLocaleString()}원</div>
                                                            )}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </>
                                )
                            })()}

                            {detailTab === "predict" && (() => {
                                const pred = stock?.prediction || {}
                                const bt = stock?.backtest || {}
                                const upProb = pred.up_probability || 50
                                const probColor = upProb >= 65 ? "#B5FF19" : upProb >= 45 ? "#FFD600" : "#FF4D4D"
                                return (
                                    <>
                                        <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "8px 0" }}>
                                            <div style={{ width: 80, height: 80, borderRadius: 40, border: `3px solid ${probColor}`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                                                <span style={{ color: probColor, fontSize: 22, fontWeight: 900 }}>{upProb}%</span>
                                                <span style={{ color: C.textTertiary, fontSize: 12 }}>상승확률</span>
                                            </div>
                                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                                <span style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700 }}>1주 후 상승 확률</span>
                                                <span style={{ color: C.textSecondary, fontSize: 12 }}>
                                                    {pred.method === "xgboost" ? `XGBoost (정확도 ${pred.model_accuracy}%)` : "규칙 기반 추정"}
                                                </span>
                                                <span style={{ color: C.textTertiary, fontSize: 12 }}>
                                                    {pred.train_samples ? `학습: ${pred.train_samples}건 / 테스트: ${pred.test_samples}건` : ""}
                                                </span>
                                            </div>
                                        </div>

                                        {pred.top_features && Object.keys(pred.top_features).length > 0 && (
                                            <div style={{ marginTop: 8 }}>
                                                <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>주요 예측 피처</span>
                                                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                                                    {Object.entries(pred.top_features).map(([k, v]: [string, any]) => (
                                                        <span key={k} style={{ ...signalTag, background: "#001A0D", border: "1px solid #0A2A1A" }}>
                                                            {k}: {(v * 100).toFixed(0)}%
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {bt.total_trades > 0 && (
                                            <div style={{ marginTop: 16, borderTop: `1px solid ${C.border}`, paddingTop: 12 }}>
                                                <span style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600 }}>백테스트 (1년)</span>
                                                <div style={{ ...metricsGrid, marginTop: 8 }}>
                                                    <MetricCard label="승률" value={`${bt.win_rate}%`}
                                                        color={bt.win_rate >= 55 ? "#B5FF19" : bt.win_rate >= 45 ? "#FFD600" : "#FF4D4D"} />
                                                    <MetricCard label="총 매매" value={`${bt.total_trades}회`} />
                                                    <MetricCard label="평균수익" value={`${bt.avg_return >= 0 ? "+" : ""}${bt.avg_return}%`}
                                                        color={bt.avg_return >= 0 ? "#B5FF19" : "#FF4D4D"} />
                                                    <MetricCard label="최대낙폭" value={`-${bt.max_drawdown}%`} color="#FF4D4D" />
                                                    <MetricCard label="샤프비율" value={`${bt.sharpe_ratio}`}
                                                        color={bt.sharpe_ratio >= 1 ? "#B5FF19" : bt.sharpe_ratio >= 0.5 ? "#FFD600" : "#FF4D4D"} />
                                                    <MetricCard label="누적수익" value={`${bt.total_return >= 0 ? "+" : ""}${bt.total_return}%`}
                                                        color={bt.total_return >= 0 ? "#B5FF19" : "#FF4D4D"} />
                                                </div>
                                                {bt.recent_trades?.length > 0 && (
                                                    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                                                        <span style={{ color: C.textTertiary, fontSize: 12 }}>최근 매매</span>
                                                        {bt.recent_trades.map((tr: any, i: number) => (
                                                            <div key={i} style={{ ...newsRow, display: "flex", justifyContent: "space-between" }}>
                                                                <span style={{ color: C.textSecondary, fontSize: 12 }}>{tr.entry_date} → {tr.exit_date}</span>
                                                                <span style={{ color: tr.return_pct >= 0 ? "#B5FF19" : "#FF4D4D", fontSize: 12, fontWeight: 700 }}>
                                                                    {tr.return_pct >= 0 ? "+" : ""}{tr.return_pct}%
                                                                </span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {(!bt.total_trades || bt.total_trades === 0) && (
                                            <div style={{ color: C.textTertiary, fontSize: 12, padding: "16px 0", textAlign: "center" }}>
                                                백테스트 데이터는 장 마감 후(16시) 전체 분석 시 생성됩니다
                                            </div>
                                        )}
                                    </>
                                )
                            })()}
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}

function MetricCard({ label, value, color = "#fff" }: { label: string; value: string; color?: string }) {
    return (
        <div style={metricCard}>
            <span style={mLabel}>{label}</span>
            <span style={{ ...mValue, color }}>{value}</span>
        </div>
    )
}

/* ─── ESTATE LANDEX 가중평균 카드 (KR 부동산 탭 전용) ─── */
type EstateGuRow = {
    gu: string; count: number; total_area_sqm: number
    landex: number | null; tier5: string | null; snapshot_month: string | null
}
type EstateFacResp = {
    ticker: string; company_name: string | null
    facilities: any[]; by_gu: EstateGuRow[]
    summary: {
        total_facilities: number; total_area_sqm: number; covered_gus: number
        landex_weighted_avg: number | null; landex_simple_avg: number | null
        missing_landex_gus: string[]
    }
}

const ESTATE_TIER_COLOR: Record<string, string> = {
    HOT: "#EF4444", WARM: "#F59E0B", NEUT: "#A8ABB2", COOL: "#5BA9FF", AVOID: "#6B6E76",
}
function estateTierFromScore(s: number | null | undefined): string | null {
    if (s === null || s === undefined || isNaN(s)) return null
    if (s >= 80) return "HOT"
    if (s >= 60) return "WARM"
    if (s >= 40) return "NEUT"
    if (s >= 20) return "COOL"
    return "AVOID"
}

function EstateLandexCard({ ticker, apiBase }: { ticker: string; apiBase: string }) {
    const [data, setData] = useState<EstateFacResp | null>(null)
    const [loading, setLoading] = useState(true)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        if (!ticker || !/^\d{6}$/.test(ticker)) {
            setLoading(false); setErr(null); setData(null); return
        }
        let cancelled = false
        setLoading(true); setErr(null)
        fetch(`${apiBase}/api/estate/corp-facilities?ticker=${ticker}`)
            .then((r) => r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`))
            .then((j: EstateFacResp) => { if (!cancelled) setData(j) })
            .catch((e) => { if (!cancelled) setErr(String(e)) })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [ticker, apiBase])

    if (loading) return null
    if (err || !data) return null
    if (!data.summary || data.summary.total_facilities === 0) return null

    const wa = data.summary.landex_weighted_avg
    const sa = data.summary.landex_simple_avg
    const tier = estateTierFromScore(wa)
    const tierColor = tier ? ESTATE_TIER_COLOR[tier] : "#A8ABB2"
    const top3 = (data.by_gu || []).slice(0, 3)
    const fmtArea = (sqm: number): string => {
        if (!sqm) return "—"
        if (sqm >= 1e6) return `${(sqm / 1e6).toFixed(2)}M㎡`
        if (sqm >= 1e4) return `${(sqm / 1e4).toFixed(1)}만㎡`
        return `${Math.round(sqm)}㎡`
    }

    return (
        <div style={{
            display: "grid", gridTemplateColumns: "auto 1fr", gap: S.lg,
            padding: S.lg, background: C.bgElevated,
            border: `1px solid ${C.border}`, borderRadius: R.md, alignItems: "center",
        }}>
            {/* 좌: 가중평균 큰 숫자 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start", minWidth: 140 }}>
                <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med, letterSpacing: 0.3 }}>
                    LANDEX 가중평균
                </span>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                    <span style={{
                        color: tierColor, fontSize: 36, fontWeight: 700,
                        fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums", lineHeight: 1,
                    }}>
                        {wa !== null ? wa.toFixed(1) : "—"}
                    </span>
                    <span style={{ color: C.textTertiary, fontSize: T.cap }}>/100</span>
                </div>
                {tier && (
                    <span style={{
                        display: "inline-block", padding: "2px 8px",
                        background: `${tierColor}1A`, color: tierColor,
                        fontSize: T.cap, fontWeight: T.w_semi, borderRadius: 4, letterSpacing: 0.3,
                    }}>{tier}</span>
                )}
            </div>

            {/* 우: 분포 + Top 3 */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.sm, minWidth: 0 }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: S.lg, fontSize: T.cap, color: C.textSecondary }}>
                    <span>시설 <b style={{ color: C.textPrimary, ...{ fontFamily: FONT_MONO } }}>{data.summary.total_facilities}</b>개</span>
                    <span>면적 <b style={{ color: C.textPrimary, ...{ fontFamily: FONT_MONO } }}>{fmtArea(data.summary.total_area_sqm)}</b></span>
                    <span>분포 <b style={{ color: C.textPrimary, ...{ fontFamily: FONT_MONO } }}>{data.summary.covered_gus}</b>구</span>
                    {sa !== null && (
                        <span>단순평균 <b style={{ color: C.textPrimary, ...{ fontFamily: FONT_MONO } }}>{sa.toFixed(1)}</b></span>
                    )}
                </div>
                {top3.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ color: C.textTertiary, fontSize: 11, fontWeight: T.w_med, letterSpacing: 0.3 }}>
                            주요 위치 (면적 순)
                        </span>
                        <div style={{ display: "flex", gap: S.sm, flexWrap: "wrap" }}>
                            {top3.map((g) => {
                                const t = g.tier5 ?? estateTierFromScore(g.landex)
                                const tc = t ? ESTATE_TIER_COLOR[t] : C.textTertiary
                                return (
                                    <div key={g.gu} style={{
                                        display: "flex", alignItems: "center", gap: 6,
                                        padding: "4px 8px", background: C.bgPage,
                                        border: `1px solid ${C.border}`, borderRadius: 4,
                                    }}>
                                        <span style={{ color: C.textPrimary, fontSize: T.cap, fontWeight: T.w_semi }}>
                                            {g.gu}
                                        </span>
                                        <span style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: FONT_MONO }}>
                                            {g.count}시설
                                        </span>
                                        <span style={{
                                            color: tc, fontSize: T.cap, fontWeight: T.w_semi,
                                            fontFamily: FONT_MONO,
                                        }}>
                                            {g.landex !== null ? g.landex.toFixed(0) : "—"}
                                        </span>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                )}
                <span style={{ color: C.textTertiary, fontSize: 11, fontStyle: "italic" }}>
                    면적 가중. VERITY ESTATE LANDEX (V/D/S/C/R) 25구 점수 — 0~100 / HOT WARM NEUT COOL AVOID.
                </span>
            </div>
        </div>
    )
}

StockDashboard.defaultProps = { dataUrl: DATA_URL, apiBase: API_BASE, market: "kr" }
addPropertyControls(StockDashboard, {
    dataUrl: { type: ControlType.String, title: "Portfolio URL", defaultValue: DATA_URL },
    recUrl:  { type: ControlType.String, title: "Recommendations URL", defaultValue: REC_URL },
    apiBase: { type: ControlType.String, title: "API Base URL", defaultValue: API_BASE },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["국장 (KR)", "미장 (US)"],
        defaultValue: "kr",
    },
})

/* ─── Styles ─── */
const wrap: React.CSSProperties = { width: "100%", background: C.bgPage, borderRadius: R.lg, fontFamily: font, display: "flex", flexDirection: "column", overflow: "hidden", color: C.textPrimary }
const tabBar: React.CSSProperties = { display: "flex", gap: S.sm, padding: `${S.lg}px ${S.xl}px 0` }
const tabBtn: React.CSSProperties = { border: "none", borderRadius: R.md, padding: `${S.sm}px ${S.md}px`, fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font, cursor: "pointer", transition: X.fast }
const body: React.CSSProperties = { display: "flex", gap: 0, minHeight: 560 }
const listPanel: React.CSSProperties = {
    width: 280,
    minWidth: 280,
    borderRight: `1px solid ${C.border}`,
    padding: `${S.xxl}px 0`,
    maxHeight: 720,
    alignSelf: "flex-start",
    overflowY: "auto",
    overscrollBehavior: "contain",
    WebkitOverflowScrolling: "touch",
    scrollbarWidth: "thin",
    WebkitMaskImage:
        "linear-gradient(to bottom, transparent 0, #000 28px, #000 calc(100% - 28px), transparent 100%)",
    maskImage:
        "linear-gradient(to bottom, transparent 0, #000 28px, #000 calc(100% - 28px), transparent 100%)",
}
const listItem: React.CSSProperties = { display: "flex", alignItems: "center", padding: `${S.md}px ${S.lg}px ${S.md}px ${S.md}px`, transition: X.fast }
const listRecDot: React.CSSProperties = { width: 8, height: 8, borderRadius: 6, flexShrink: 0 }
const listName: React.CSSProperties = { color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }
const listTicker: React.CSSProperties = { color: C.textTertiary, fontSize: T.cap, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
const listRight: React.CSSProperties = { display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2, flexShrink: 0, minWidth: 76 }
const listPrice: React.CSSProperties = { color: C.textPrimary, fontSize: T.cap, fontWeight: T.w_semi, whiteSpace: "nowrap", fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
const listScore: React.CSSProperties = { fontSize: T.cap, fontWeight: T.w_bold, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
const detailPanel: React.CSSProperties = { flex: 1, padding: `${S.lg}px ${S.xl}px`, display: "flex", flexDirection: "column", gap: S.lg, overflowY: "auto" }
const detailTop: React.CSSProperties = { display: "flex", gap: S.xl, alignItems: "flex-start" }
const gaugeWrap: React.CSSProperties = { position: "relative", width: 120, height: 120, flexShrink: 0, display: "flex", justifyContent: "center", alignItems: "center" }
const gaugeCenter: React.CSSProperties = { position: "absolute", display: "flex", flexDirection: "column", alignItems: "center" }
const gaugeNum: React.CSSProperties = { fontSize: T.h1, fontWeight: T.w_black, lineHeight: 1, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
const gaugeGrade: React.CSSProperties = { color: C.textSecondary, fontSize: T.cap, fontWeight: T.w_med, marginTop: 2, fontFamily: FONT_MONO, letterSpacing: "0.05em" }
const detailInfo: React.CSSProperties = { display: "flex", flexDirection: "column", gap: S.xs, flex: 1, paddingTop: S.xs }
const badge: React.CSSProperties = { color: "#000", fontSize: T.cap, fontWeight: T.w_black, padding: `3px ${S.md}px`, borderRadius: R.sm }
const detailName: React.CSSProperties = { color: C.textPrimary, fontSize: T.h2 + 2, fontWeight: T.w_black, letterSpacing: -1, lineHeight: 1.1 }
const detailBusiness: React.CSSProperties = {
    color: C.textSecondary,
    fontSize: T.cap,
    fontWeight: T.w_med,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: 260,
}
const detailTicker: React.CSSProperties = { color: C.textTertiary, fontSize: T.cap, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
const detailVerdict: React.CSSProperties = { color: C.textPrimary, fontSize: T.body, lineHeight: T.lh_normal, margin: 0 }

const factorBarSection: React.CSSProperties = { display: "flex", flexDirection: "column", gap: S.sm, padding: `${S.md}px 0`, borderTop: `1px solid ${C.border}`, borderBottom: `1px solid ${C.border}` }
const factorItem: React.CSSProperties = { display: "flex", flexDirection: "column", gap: S.xs }
const factorLabel: React.CSSProperties = { color: C.textSecondary, fontSize: T.cap, fontWeight: T.w_med }
const factorVal: React.CSSProperties = { fontSize: T.cap, fontWeight: T.w_bold, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
const factorBarBg: React.CSSProperties = { height: 4, background: C.bgElevated, borderRadius: 2, overflow: "hidden" }
const factorBarFill: React.CSSProperties = { height: "100%", borderRadius: 2, transition: "width 0.5s ease" }

const subTabBar: React.CSSProperties = { display: "flex", gap: 0, flexWrap: "wrap", rowGap: S.xs }
const subTabBtn: React.CSSProperties = { border: "none", background: "transparent", padding: `${S.sm}px ${S.lg}px`, fontSize: T.body, fontWeight: T.w_semi, fontFamily: font, cursor: "pointer", transition: X.fast }
const tabContent: React.CSSProperties = { display: "flex", flexDirection: "column", gap: S.md }

const insightSection: React.CSSProperties = { display: "flex", flexDirection: "column", gap: S.sm }
const insightRow: React.CSSProperties = { display: "flex", alignItems: "center", gap: S.md }
const goldBadge: React.CSSProperties = { background: C.watch, color: "#000", fontSize: T.cap, fontWeight: T.w_black, padding: `3px ${S.sm}px`, borderRadius: R.sm, minWidth: 48, textAlign: "center", fontFamily: FONT_MONO, letterSpacing: "0.03em" }
const silverBadge: React.CSSProperties = { background: C.textSecondary, color: "#000", fontSize: T.cap, fontWeight: T.w_black, padding: `3px ${S.sm}px`, borderRadius: R.sm, minWidth: 48, textAlign: "center", fontFamily: FONT_MONO, letterSpacing: "0.03em" }
const insightText: React.CSSProperties = { color: C.textPrimary, fontSize: T.body }

const metricsGrid: React.CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: S.sm }
const metricCard: React.CSSProperties = { background: C.bgElevated, borderRadius: R.md, padding: `${S.md}px ${S.md}px`, display: "flex", flexDirection: "column", gap: S.xs, border: `1px solid ${C.border}` }
const mLabel: React.CSSProperties = { color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med }
const mValue: React.CSSProperties = { color: C.textPrimary, fontSize: T.sub, fontWeight: T.w_bold, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }

const signalWrap: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: S.sm, marginTop: S.xs }
const signalTag: React.CSSProperties = { background: C.accentSoft, border: `1px solid rgba(181,255,25,0.25)`, color: C.accent, fontSize: T.cap, fontWeight: T.w_semi, padding: `${S.xs}px ${S.md}px`, borderRadius: R.sm }

const newsRow: React.CSSProperties = { background: C.bgElevated, borderRadius: R.md, padding: `${S.md}px ${S.lg}px`, border: `1px solid ${C.border}` }
const maBar: React.CSSProperties = { display: "flex", gap: S.sm }
const maItem: React.CSSProperties = { flex: 1, background: C.bgElevated, borderRadius: R.md, padding: `${S.md}px ${S.lg}px`, display: "flex", flexDirection: "column", alignItems: "center", gap: S.xs, border: `1px solid ${C.border}` }


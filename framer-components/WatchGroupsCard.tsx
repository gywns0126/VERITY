import { addPropertyControls, ControlType } from "framer"
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"

const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
const BG = "#000"
const CARD = "#111"
const BORDER = "#222"
const ACCENT = "#B5FF19"
const MUTED = "#8B95A1"
const UP = "#F04452"
const DOWN = "#3182F6"

const DEFAULT_COLORS = ["#B5FF19", "#3182F6", "#F04452", "#FFD600", "#A78BFA", "#34D399"]
const DEFAULT_ICONS = ["⭐", "🔥", "💎", "🚀", "📊", "🏦", "💰", "🎯"]

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    return `${u}${u.includes("?") ? "&" : "?"}_=${Date.now()}`
}

function safeJsonParse(text: string): any {
    if (!text || text.trim().length === 0) return null
    try { return JSON.parse(text) } catch (_e) { return null }
}

function fetchJson(url: string): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit" })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => {
            const cleaned = (t || "").replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")
            return safeJsonParse(cleaned)
        })
}

function getVerityUserId(): string {
    if (typeof window === "undefined") return "anon"
    let uid = localStorage.getItem("verity_user_id")
    if (!uid) {
        uid = crypto.randomUUID?.() || `u-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
        localStorage.setItem("verity_user_id", uid)
    }
    return uid
}

const LS_KEY = "verity_watchlist"
const WATCH_EVENT = "verity-watchlist-change"

interface LocalWatchItem {
    ticker: string
    name: string
    market: string
    addedAt: number
}

function readLocalWatchlist(): LocalWatchItem[] {
    if (typeof window === "undefined") return []
    try {
        const raw = localStorage.getItem(LS_KEY)
        if (!raw || raw.length < 2) return []
        const parsed = JSON.parse(raw)
        return Array.isArray(parsed) ? parsed : []
    } catch (_e) {
        return []
    }
}

function writeLocalWatchlist(items: LocalWatchItem[]) {
    if (typeof window === "undefined") return
    localStorage.setItem(LS_KEY, JSON.stringify(items))
    window.dispatchEvent(new CustomEvent(WATCH_EVENT, { detail: items }))
}

interface WatchItem {
    id: string
    ticker: string
    name: string
    market: string
    memo: string
    sort_order: number
    _price?: number
    _change_pct?: number
    _rec?: string
    _score?: number
    _rsi?: number
    _per?: number
    _loading?: boolean
}

interface WatchGroup {
    id: string
    name: string
    color: string
    icon: string
    sort_order: number
    items: WatchItem[]
}

interface Props {
    apiBase: string
    portfolioUrl: string
}

export default function WatchGroupsCard(props: Props) {
    const { apiBase, portfolioUrl } = props
    const [groups, setGroups] = useState<WatchGroup[]>([])
    const [portfolio, setPortfolio] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [expandedId, setExpandedId] = useState<string | null>(null)
    const [showCreate, setShowCreate] = useState(false)
    const [newName, setNewName] = useState("")
    const [newColor, setNewColor] = useState(DEFAULT_COLORS[0])
    const [newIcon, setNewIcon] = useState(DEFAULT_ICONS[0])
    const [addTicker, setAddTicker] = useState("")
    const [addGroupId, setAddGroupId] = useState<string | null>(null)
    const [addMarket, setAddMarket] = useState<"kr" | "us">("kr")
    const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
    const [toast, setToast] = useState<string | null>(null)
    const toastTimer = useRef<ReturnType<typeof setTimeout>>()

    const showToast = useCallback((msg: string) => {
        setToast(msg)
        if (toastTimer.current) clearTimeout(toastTimer.current)
        toastTimer.current = setTimeout(() => setToast(null), 3000)
    }, [])

    const api = useMemo(() => {
        let s = (apiBase || "").trim().replace(/\/+$/, "")
        if (!s) return ""
        if (!/^https?:\/\//i.test(s)) s = `https://${s}`
        return s
    }, [apiBase])

    const userId = useMemo(() => getVerityUserId(), [])

    const loadGroups = useCallback(() => {
        if (!api) { setLoading(false); return }
        setLoading(true)
        fetch(`${api}/api/watchgroups?user_id=${encodeURIComponent(userId)}`, { mode: "cors", credentials: "omit" })
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.text()
            })
            .then(txt => {
                const data = safeJsonParse(txt)
                if (Array.isArray(data)) setGroups(data)
            })
            .catch(() => {})
            .finally(() => setLoading(false))
    }, [api, userId])

    useEffect(() => { loadGroups() }, [loadGroups])

    const [localWatch, setLocalWatch] = useState<LocalWatchItem[]>(() => readLocalWatchlist())

    useEffect(() => {
        const onSync = () => {
            const items = readLocalWatchlist()
            setLocalWatch(items)
            if (items.length > 0 && !expandedId) setExpandedId("__local__")
        }
        window.addEventListener(WATCH_EVENT, onSync)
        window.addEventListener("storage", (e: StorageEvent) => { if (e.key === LS_KEY) onSync() })
        return () => { window.removeEventListener(WATCH_EVENT, onSync) }
    }, [expandedId])

    useEffect(() => {
        if (portfolioUrl) fetchJson(portfolioUrl).then(setPortfolio).catch(() => {})
    }, [portfolioUrl])

    const priceMap = useMemo(() => {
        const m: Record<string, { price: number; change_pct: number }> = {}
        if (!portfolio) return m
        for (const r of (portfolio.recommendations || [])) {
            const t = String(r.ticker || "").trim()
            if (t) {
                const tech = r.technical || {}
                m[t] = { price: r.price || 0, change_pct: tech.price_change_pct || 0 }
            }
        }
        for (const h of (portfolio.holdings || [])) {
            const t = String(h.ticker || "").trim()
            if (t && !m[t]) {
                m[t] = { price: h.current_price || h.price || 0, change_pct: h.change_pct || h.profit_pct || 0 }
            }
        }
        return m
    }, [portfolio])

    const [liveData, setLiveData] = useState<Record<string, any>>({})
    const fetchingRef = useRef<Set<string>>(new Set())

    const fetchLiveData = useCallback((ticker: string, market: string) => {
        if (!api || fetchingRef.current.has(ticker)) return
        fetchingRef.current.add(ticker)
        setLiveData(prev => ({ ...prev, [ticker]: { _loading: true } }))
        const mkt = (market || "").toLowerCase().includes("us") || (market || "").toLowerCase().includes("nyse") || (market || "").toLowerCase().includes("nasdaq") ? "us" : "kr"
        fetch(`${api}/api/stock?q=${encodeURIComponent(ticker)}&market=${mkt}`, { mode: "cors", credentials: "omit" })
            .then(async r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                const txt = await r.text()
                const parsed = safeJsonParse(txt)
                if (parsed === null) throw new Error("빈 응답")
                return parsed
            })
            .then(res => {
                if (res && !res.error) {
                    setLiveData(prev => ({ ...prev, [ticker]: res }))
                } else {
                    setLiveData(prev => ({ ...prev, [ticker]: { _error: true } }))
                }
            })
            .catch(() => {
                setLiveData(prev => ({ ...prev, [ticker]: { _error: true } }))
            })
            .finally(() => { fetchingRef.current.delete(ticker) })
    }, [api])

    const allGroups = useMemo(() => {
        const apiGroups = [...groups]
        if (localWatch.length > 0) {
            const localItems: WatchItem[] = localWatch.map((lw, i) => ({
                id: `local-${lw.ticker}`,
                ticker: lw.ticker,
                name: lw.name,
                market: lw.market,
                memo: "",
                sort_order: i,
            }))
            apiGroups.unshift({
                id: "__local__",
                name: "관심종목",
                color: ACCENT,
                icon: "❤️",
                sort_order: -1,
                items: localItems,
            })
        }
        return apiGroups
    }, [groups, localWatch])

    useEffect(() => {
        if (!expandedId) return
        const group = allGroups.find(g => g.id === expandedId)
        if (!group) return
        for (const item of group.items) {
            if (!priceMap[item.ticker] && !liveData[item.ticker] && !fetchingRef.current.has(item.ticker)) {
                fetchLiveData(item.ticker, item.market)
            }
        }
    }, [expandedId, allGroups, priceMap, liveData, fetchLiveData])

    const enrichedGroups = useMemo(() => {
        return allGroups.map(g => ({
            ...g,
            items: g.items.map(it => {
                const pm = priceMap[it.ticker]
                const ld = liveData[it.ticker]
                const isLdLoading = ld?._loading === true
                const hasLd = ld && !ld._loading && !ld._error
                return {
                    ...it,
                    _price: pm?.price ?? (hasLd ? ld.price : undefined),
                    _change_pct: pm?.change_pct ?? (hasLd ? (ld.technical?.price_change_pct ?? ld.change_pct) : undefined),
                    _rec: hasLd ? ld.recommendation : undefined,
                    _score: hasLd ? (ld.multi_factor?.multi_score ?? ld.safety_score) : undefined,
                    _rsi: hasLd ? ld.technical?.rsi : undefined,
                    _per: hasLd ? ld.per : undefined,
                    _loading: isLdLoading,
                }
            }),
        }))
    }, [allGroups, priceMap, liveData])

    const createGroup = useCallback(() => {
        if (!api || !newName.trim()) return
        fetch(`${api}/api/watchgroups`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: userId, name: newName.trim(), color: newColor, icon: newIcon }),
            mode: "cors", credentials: "omit",
        })
            .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
            .then(() => { setShowCreate(false); setNewName(""); loadGroups() })
            .catch(() => showToast("그룹 생성에 실패했습니다"))
    }, [api, userId, newName, newColor, newIcon, loadGroups, showToast])

    const deleteGroup = useCallback((id: string) => {
        if (id === "__local__") {
            writeLocalWatchlist([])
            setLocalWatch([])
            setExpandedId(null)
            return
        }
        if (!api) return
        fetch(`${api}/api/watchgroups`, {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id, user_id: userId }),
            mode: "cors", credentials: "omit",
        })
            .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r })
            .then(() => { loadGroups(); setExpandedId(null) })
            .catch(() => showToast("그룹 삭제에 실패했습니다"))
    }, [api, loadGroups, userId, showToast])

    const addItem = useCallback((groupId: string) => {
        if (!api || !addTicker.trim()) return
        const ticker = addTicker.trim()
        const group = groups.find(g => g.id === groupId)
        if (group?.items.some(it => it.ticker === ticker)) {
            showToast("이미 추가된 종목입니다")
            return
        }
        fetch(`${api}/api/watchgroups`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                action: "add_item",
                user_id: userId,
                group_id: groupId,
                ticker,
                name: ticker,
                market: addMarket,
            }),
            mode: "cors", credentials: "omit",
        })
            .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
            .then(() => { setAddTicker(""); setAddGroupId(null); setAddMarket("kr"); loadGroups() })
            .catch(() => showToast("종목 추가에 실패했습니다"))
    }, [api, addTicker, addMarket, groups, loadGroups, userId, showToast])

    const removeItem = useCallback((itemId: string) => {
        if (itemId.startsWith("local-")) {
            const ticker = itemId.replace("local-", "")
            writeLocalWatchlist(readLocalWatchlist().filter(it => it.ticker !== ticker))
            setLocalWatch(readLocalWatchlist())
            return
        }
        if (!api) return
        fetch(`${api}/api/watchgroups`, {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "remove_item", item_id: itemId, user_id: userId }),
            mode: "cors", credentials: "omit",
        })
            .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r })
            .then(() => loadGroups())
            .catch(() => showToast("종목 삭제에 실패했습니다"))
    }, [api, loadGroups, userId, showToast])

    return (
        <div style={wrapStyle}>
            {toast && (
                <div style={{
                    position: "absolute" as const, bottom: 16, left: "50%", transform: "translateX(-50%)",
                    background: "#FF4D4D", color: "#fff", padding: "8px 18px", borderRadius: 10,
                    fontSize: 12, fontWeight: 700, fontFamily: FONT, zIndex: 10, whiteSpace: "nowrap" as const,
                    boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
                }}>{toast}</div>
            )}
            {/* Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 16px", borderBottom: `1px solid ${BORDER}` }}>
                <span style={{ color: "#fff", fontSize: 16, fontWeight: 800, fontFamily: FONT }}>관심종목</span>
                <button
                    onClick={() => setShowCreate(!showCreate)}
                    style={{ background: ACCENT, color: "#000", border: "none", borderRadius: 8, padding: "6px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: FONT }}
                >
                    {showCreate ? "취소" : "+ 그룹"}
                </button>
            </div>

            {/* Create form */}
            {showCreate && (
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${BORDER}`, display: "flex", flexDirection: "column" as const, gap: 10 }}>
                    <input
                        type="text"
                        placeholder="그룹 이름"
                        value={newName}
                        onChange={e => setNewName(e.target.value)}
                        onKeyDown={e => { if (e.key === "Enter") createGroup() }}
                        style={inputStyle}
                    />
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        <span style={{ color: MUTED, fontSize: 10 }}>색상</span>
                        {DEFAULT_COLORS.map(c => (
                            <div
                                key={c}
                                onClick={() => setNewColor(c)}
                                style={{
                                    width: 20, height: 20, borderRadius: 10, background: c, cursor: "pointer",
                                    border: newColor === c ? "2px solid #fff" : "2px solid transparent",
                                }}
                            />
                        ))}
                    </div>
                    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                        <span style={{ color: MUTED, fontSize: 10 }}>아이콘</span>
                        {DEFAULT_ICONS.map(ic => (
                            <span
                                key={ic}
                                onClick={() => setNewIcon(ic)}
                                style={{
                                    fontSize: 16, cursor: "pointer", padding: "2px 4px", borderRadius: 6,
                                    background: newIcon === ic ? "#333" : "transparent",
                                }}
                            >{ic}</span>
                        ))}
                    </div>
                    <button
                        onClick={createGroup}
                        disabled={!newName.trim()}
                        style={{
                            background: newName.trim() ? ACCENT : "#333", color: newName.trim() ? "#000" : MUTED,
                            border: "none", borderRadius: 10, padding: "10px 0", fontSize: 13, fontWeight: 700, cursor: newName.trim() ? "pointer" : "default", fontFamily: FONT,
                        }}
                    >
                        그룹 만들기
                    </button>
                </div>
            )}

            {/* Groups */}
            <div style={{ flex: 1, overflowY: "auto" as any, padding: "8px 12px" }}>
                {loading && (
                    <div style={{ textAlign: "center" as const, padding: "24px 0", color: MUTED, fontSize: 12, fontFamily: FONT }}>불러오는 중...</div>
                )}

                {!loading && enrichedGroups.length === 0 && (
                    <div style={{ textAlign: "center" as const, padding: "32px 0", display: "flex", flexDirection: "column" as const, alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 32 }}>📂</span>
                        <span style={{ color: MUTED, fontSize: 13, fontFamily: FONT }}>관심종목 그룹을 만들어보세요</span>
                        <span style={{ color: "#444", fontSize: 11, fontFamily: FONT }}>+ 그룹 버튼으로 시작</span>
                    </div>
                )}

                {enrichedGroups.map(g => {
                    const isExpanded = expandedId === g.id
                    const itemCount = g.items.length
                    const avgChange = itemCount > 0
                        ? g.items.reduce((sum, it) => sum + (it._change_pct || 0), 0) / itemCount
                        : 0
                    const changeColor = avgChange > 0.3 ? UP : avgChange < -0.3 ? DOWN : MUTED

                    return (
                        <div key={g.id} style={{ marginBottom: 8 }}>
                            {/* Group card */}
                            <div
                                onClick={() => setExpandedId(isExpanded ? null : g.id)}
                                style={{
                                    background: CARD, border: `1px solid ${BORDER}`, borderRadius: 14,
                                    padding: "12px 14px", cursor: "pointer",
                                    borderLeft: `3px solid ${g.color}`,
                                }}
                            >
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                        <span style={{ fontSize: 18 }}>{g.icon}</span>
                                        <div>
                                            <div style={{ color: "#fff", fontSize: 14, fontWeight: 700, fontFamily: FONT }}>{g.name}</div>
                                            <div style={{ color: MUTED, fontSize: 10, fontFamily: FONT }}>{itemCount}종목</div>
                                        </div>
                                    </div>
                                    <div style={{ textAlign: "right" as const }}>
                                        {itemCount > 0 && (
                                            <div style={{ color: changeColor, fontSize: 13, fontWeight: 700, fontFamily: FONT }}>
                                                {avgChange >= 0 ? "+" : ""}{avgChange.toFixed(2)}%
                                            </div>
                                        )}
                                        <span style={{ color: "#444", fontSize: 10 }}>{isExpanded ? "▲" : "▼"}</span>
                                    </div>
                                </div>

                                {!isExpanded && itemCount > 0 && (
                                    <div style={{ display: "flex", gap: 4, marginTop: 8, flexWrap: "wrap" as const }}>
                                        {g.items.slice(0, 5).map(it => (
                                            <span key={it.id} style={{
                                                background: "#1A1A1A", borderRadius: 6, padding: "3px 8px",
                                                fontSize: 10, fontWeight: 600, fontFamily: FONT,
                                                color: (it._change_pct || 0) >= 0 ? UP : DOWN,
                                            }}>
                                                {it.name || it.ticker} {(it._change_pct || 0) >= 0 ? "+" : ""}{(it._change_pct || 0).toFixed(1)}%
                                            </span>
                                        ))}
                                        {itemCount > 5 && <span style={{ color: "#555", fontSize: 9, alignSelf: "center" }}>+{itemCount - 5}</span>}
                                    </div>
                                )}
                            </div>

                            {/* Expanded items — mini dashboard */}
                            {isExpanded && (
                                <div style={{ background: "#0A0A0A", border: `1px solid ${BORDER}`, borderTop: "none", borderRadius: "0 0 14px 14px", padding: "8px 8px" }}>
                                    {g.items.map(it => {
                                        const isUS = (it.market || "").toLowerCase().includes("us") || /NYSE|NASDAQ|AMEX/i.test(it.market || "")
                                        const score = it._score
                                        const scoreColor = score != null ? (score >= 65 ? ACCENT : score >= 45 ? "#FFD600" : "#FF4D4D") : "#333"
                                        const recLabel = it._rec || ""
                                        const recColor = recLabel === "BUY" ? ACCENT : recLabel === "AVOID" ? "#FF4D4D" : "#888"
                                        const chg = it._change_pct
                                        const chgColor = chg != null ? (chg >= 0 ? UP : DOWN) : MUTED

                                        if (it._loading) {
                                            return (
                                                <div key={it.id} style={miniCardStyle}>
                                                    <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
                                                        <div style={{ width: 36, height: 36, borderRadius: 18, background: "#1A1A1A", animation: "pulse 1.5s ease-in-out infinite" }} />
                                                        <div style={{ display: "flex", flexDirection: "column" as const, gap: 4 }}>
                                                            <span style={{ color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: FONT }}>{it.name || it.ticker}</span>
                                                            <div style={{ display: "flex", gap: 6 }}>
                                                                <span style={{ width: 48, height: 10, borderRadius: 3, background: "#1A1A1A", display: "inline-block", animation: "pulse 1.5s ease-in-out infinite" }} />
                                                                <span style={{ width: 32, height: 10, borderRadius: 3, background: "#1A1A1A", display: "inline-block", animation: "pulse 1.5s ease-in-out infinite" }} />
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <button onClick={(e) => { e.stopPropagation(); removeItem(it.id) }}
                                                        style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: 12, padding: "2px 4px", flexShrink: 0 }}>✕</button>
                                                    <style>{`@keyframes pulse { 0%,100% { opacity: 0.4 } 50% { opacity: 1 } }`}</style>
                                                </div>
                                            )
                                        }

                                        return (
                                            <div key={it.id} style={miniCardStyle}>
                                                {/* Mini score gauge */}
                                                {score != null ? (
                                                    <div style={{ width: 36, height: 36, position: "relative" as const, flexShrink: 0 }}>
                                                        <svg width={36} height={36} viewBox="0 0 36 36">
                                                            <circle cx={18} cy={18} r={15} fill="none" stroke="#1A1A1A" strokeWidth={3} />
                                                            <circle cx={18} cy={18} r={15} fill="none" stroke={scoreColor} strokeWidth={3}
                                                                strokeDasharray={`${(score / 100) * 94.2} 94.2`}
                                                                strokeLinecap="round" transform="rotate(-90 18 18)" />
                                                        </svg>
                                                        <div style={{ position: "absolute" as const, inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
                                                            <span style={{ color: scoreColor, fontSize: 10, fontWeight: 900, fontFamily: FONT }}>{score}</span>
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <div style={{ width: 36, height: 36, borderRadius: 18, border: "2px solid #1A1A1A", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                                                        <span style={{ color: "#444", fontSize: 9, fontFamily: FONT }}>—</span>
                                                    </div>
                                                )}

                                                {/* Info block */}
                                                <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" as const, gap: 3 }}>
                                                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                                        {recLabel && (
                                                            <span style={{ background: recColor, color: "#000", fontSize: 8, fontWeight: 800, padding: "1px 6px", borderRadius: 4, flexShrink: 0 }}>{recLabel}</span>
                                                        )}
                                                        <span style={{ color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const }}>{it.name || it.ticker}</span>
                                                        <span style={{ color: "#555", fontSize: 9, fontFamily: FONT, flexShrink: 0 }}>{it.ticker}</span>
                                                    </div>
                                                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" as const }}>
                                                        {it._price != null && (
                                                            <span style={{ color: "#ccc", fontSize: 11, fontWeight: 700, fontFamily: FONT }}>
                                                                {isUS ? `$${it._price.toLocaleString("en-US", { minimumFractionDigits: 2 })}` : `${it._price.toLocaleString()}원`}
                                                            </span>
                                                        )}
                                                        {chg != null && (
                                                            <span style={{ color: chgColor, fontSize: 10, fontWeight: 700, fontFamily: FONT }}>
                                                                {chg >= 0 ? "+" : ""}{chg.toFixed(2)}%
                                                            </span>
                                                        )}
                                                        {it._rsi != null && (
                                                            <span style={{ color: it._rsi <= 30 ? ACCENT : it._rsi >= 70 ? "#FF4D4D" : "#888", fontSize: 9, fontWeight: 600, fontFamily: FONT }}>
                                                                RSI {it._rsi}
                                                            </span>
                                                        )}
                                                        {it._per != null && (
                                                            <span style={{ color: "#888", fontSize: 9, fontWeight: 600, fontFamily: FONT }}>
                                                                PER {it._per.toFixed(1)}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>

                                                {/* Delete */}
                                                <button onClick={(e) => { e.stopPropagation(); removeItem(it.id) }}
                                                    style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: 12, padding: "2px 4px", flexShrink: 0 }}>✕</button>
                                            </div>
                                        )
                                    })}

                                    {/* Add ticker input */}
                                    <div style={{ display: "flex", gap: 6, marginTop: 8, alignItems: "center", flexWrap: "wrap" as const }}>
                                        {addGroupId === g.id ? (
                                            <>
                                                <div style={{ display: "flex", gap: 0, borderRadius: 6, overflow: "hidden", border: `1px solid ${BORDER}` }}>
                                                    {(["kr", "us"] as const).map(m => (
                                                        <button
                                                            key={m}
                                                            onClick={() => setAddMarket(m)}
                                                            style={{
                                                                background: addMarket === m ? ACCENT : "#1A1A1A",
                                                                color: addMarket === m ? "#000" : MUTED,
                                                                border: "none", padding: "6px 10px", fontSize: 10,
                                                                fontWeight: 700, cursor: "pointer", fontFamily: FONT,
                                                            }}
                                                        >{m.toUpperCase()}</button>
                                                    ))}
                                                </div>
                                                <input
                                                    type="text"
                                                    placeholder={addMarket === "kr" ? "종목코드 (예: 005930)" : "Ticker (예: AAPL)"}
                                                    value={addTicker}
                                                    onChange={e => setAddTicker(e.target.value)}
                                                    onKeyDown={e => { if (e.key === "Enter") addItem(g.id) }}
                                                    style={{ ...inputStyle, flex: 1, padding: "8px 10px", fontSize: 11, minWidth: 0 }}
                                                    autoFocus
                                                />
                                                <button
                                                    onClick={() => addItem(g.id)}
                                                    style={{ background: ACCENT, color: "#000", border: "none", borderRadius: 8, padding: "8px 12px", fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: FONT }}
                                                >추가</button>
                                                <button
                                                    onClick={() => { setAddGroupId(null); setAddTicker(""); setAddMarket("kr") }}
                                                    style={{ background: "none", border: "none", color: MUTED, cursor: "pointer", fontSize: 11, fontFamily: FONT }}
                                                >취소</button>
                                            </>
                                        ) : (
                                            <button
                                                onClick={() => setAddGroupId(g.id)}
                                                style={{ background: "#1A1A1A", border: `1px dashed #333`, borderRadius: 8, padding: "8px 0", width: "100%", color: MUTED, fontSize: 11, cursor: "pointer", fontFamily: FONT }}
                                            >+ 종목 추가</button>
                                        )}
                                    </div>

                                    {/* Delete group */}
                                    <div style={{ textAlign: "right" as const, marginTop: 8, display: "flex", justifyContent: "flex-end", gap: 6 }}>
                                        {confirmDeleteId === g.id ? (
                                            <>
                                                <span style={{ color: "#FF4D4D", fontSize: 10, fontFamily: FONT, alignSelf: "center" }}>삭제할까요?</span>
                                                <button
                                                    onClick={() => { deleteGroup(g.id); setConfirmDeleteId(null) }}
                                                    style={{ background: "#FF4D4D", border: "none", color: "#fff", borderRadius: 6, padding: "4px 10px", fontSize: 10, fontWeight: 700, cursor: "pointer", fontFamily: FONT }}
                                                >확인</button>
                                                <button
                                                    onClick={() => setConfirmDeleteId(null)}
                                                    style={{ background: "none", border: "1px solid #333", color: MUTED, borderRadius: 6, padding: "4px 10px", fontSize: 10, cursor: "pointer", fontFamily: FONT }}
                                                >취소</button>
                                            </>
                                        ) : (
                                            <button
                                                onClick={() => setConfirmDeleteId(g.id)}
                                                style={{ background: "none", border: "none", color: "#FF4D4D", cursor: "pointer", fontSize: 10, fontFamily: FONT }}
                                            >그룹 삭제</button>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

WatchGroupsCard.defaultProps = {
    apiBase: "https://vercel-api-alpha-umber.vercel.app",
    portfolioUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
}

addPropertyControls(WatchGroupsCard, {
    apiBase: {
        type: ControlType.String,
        title: "API Base URL",
        defaultValue: "https://vercel-api-alpha-umber.vercel.app",
    },
    portfolioUrl: {
        type: ControlType.String,
        title: "portfolio.json URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
})

const wrapStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    minHeight: 400,
    background: BG,
    borderRadius: 20,
    border: `1px solid ${BORDER}`,
    overflow: "hidden",
    fontFamily: FONT,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
    position: "relative",
}

const inputStyle: React.CSSProperties = {
    background: CARD,
    border: `1px solid ${BORDER}`,
    borderRadius: 10,
    padding: "10px 14px",
    color: "#fff",
    fontSize: 13,
    fontWeight: 600,
    fontFamily: FONT,
    outline: "none",
    boxSizing: "border-box",
}

const miniCardStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "8px 6px",
    borderBottom: "1px solid #1A1A1A",
}

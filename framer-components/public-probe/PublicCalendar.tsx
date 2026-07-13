import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 투자 캘린더 — AlphaNest 공개 터미널. 이미지 참고 = 깔끔 월 그리드(토스식).
 *
 * 🚨 차별점(RULE 6/7): 범용 실적 캘린더(네이버·토스 강자영역) 흉내 X.
 *   우리 강점 = 공시 포렌식. 각 이벤트에 사실 카테고리 태그(희석/자사주/구조/배당/IPO) + 종목 로고 + DART 원문.
 *   점수·등급·추천 0 (사실 분류 태그만).
 * 데이터 = calendar_public.json (calendar_public_builder — 공시·배당락·IPO 병합, 신규수집 0).
 *   실적발표 예정일·락업해제 = 소스 미보유로 미포함(가짜 이벤트 방지).
 * 로고 = 토스 종목 CDN + 이니셜 폴백. 다크모드 자가감지. cache-fallback.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", track: "#eef0f3", hi: "#f6f7f9", vt: "#6c5ce7", vtS: "#f0edff",
    today: "#191f28", todayInk: "#ffffff", cellHover: "#f6f7f9",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", track: "#222a33", hi: "#1e242c", vt: "#a99bff", vtS: "#241f3a",
    today: "#e3e7ec", todayInk: "#0f1318", cellHover: "#1e242c",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DATA_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/calendar_public.json"

// 이벤트 카테고리 = 사실 분류(색은 가독용, 좋다·나쁘다 라벨 아님)
const CAT: Record<string, { label: string; c: string; s: string }> = {
    dilution: { label: "희석", c: "#f04452", s: "#fdecee" },      // 유증·CB·BW
    buyback: { label: "자사주", c: "#3182f6", s: "#eaf1fe" },     // 취득·소각(수급+)
    supply: { label: "자사주처분", c: "#8b95a1", s: "#eef0f3" },  // 처분(수급-)
    dividend: { label: "배당", c: "#0ca678", s: "#e7faf0" },
    ipo: { label: "IPO", c: "#6c5ce7", s: "#f0edff" },
    capital: { label: "자본변동", c: "#ff9500", s: "#fff4e0" },
    structural: { label: "구조", c: "#00a8b5", s: "#e3f7f9" },
    governance: { label: "지배구조", c: "#e6820a", s: "#fdf0dc" },
}
const CAT_DARK_S: Record<string, string> = {
    dilution: "#2a1518", buyback: "#17263c", supply: "#252b34", dividend: "#11281d",
    ipo: "#241f3a", capital: "#2a2113", structural: "#0f2a2d", governance: "#2a2010",
}
const WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

// ── 종목 로고 = 토스 CDN + 이니셜 폴백 ──
function tossLogo(ticker: any): string {
    const tk = String(ticker || "").trim()
    return tk ? "https://static.toss.im/png-icons/securities/icn-sec-fill-" + tk + ".png" : ""
}
function initialBg(seed: any): string {
    let h = 0; const s = String(seed || "?")
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360
    return "linear-gradient(135deg, hsl(" + h + ",60%,55%), hsl(" + ((h + 42) % 360) + ",64%,44%))"
}
function StockDot(props: { ticker: any; name: any; size?: number }) {
    const size = props.size || 22
    const [err, setErr] = useState(false)
    const src = tossLogo(props.ticker)
    const ch = (String(props.name || "?").trim().charAt(0)) || "?"
    if (!props.ticker || err || !src) {
        return <span style={{ width: size, height: size, borderRadius: Math.round(size * 0.3), background: initialBg(props.name || props.ticker), color: "#fff", fontSize: Math.round(size * 0.42), fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{ch}</span>
    }
    return <img src={src} alt="" width={size} height={size} loading="lazy" decoding="async" onError={() => setErr(true)}
        style={{ width: size, height: size, borderRadius: Math.round(size * 0.3), objectFit: "contain", display: "block", flexShrink: 0 }} />
}

// 날짜 셀용 초미니 로고 — 카테고리 색 링으로 '무슨 이벤트'까지 전달. 티커 없으면(IPO 등) 색 점.
function DayLogo(props: { ev: any; size: number; ringOnDark?: boolean }) {
    const { ev, size } = props
    const [err, setErr] = useState(false)
    const src = tossLogo(ev.ticker)
    const c = CAT[ev.cat] ? CAT[ev.cat].c : "#8b95a1"
    if (!ev.ticker || err || !src) {
        return <span style={{ width: size, height: size, borderRadius: "50%", background: c, flexShrink: 0, display: "block" }} />
    }
    return <img src={src} alt="" width={size} height={size} loading="lazy" decoding="async" onError={() => setErr(true)}
        style={{ width: size, height: size, borderRadius: Math.round(size * 0.28), objectFit: "contain", display: "block", flexShrink: 0, boxShadow: "0 0 0 1.5px " + c }} />
}

function readBodyDark(): boolean {
    try {
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
function ymd(d: Date): string {
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0")
}

const DEMO = {
    _meta: { generated_at: "2026-07-12T16:00:00+09:00", counts: { total: 6 } },
    events: [
        { date: "2026-07-13", type: "ipo", cat: "ipo", tag: "IPO 청약 시작", ticker: "", name: "에이치엘지노믹스", title: "에이치엘지노믹스 공모 청약 시작", url: "" },
        { date: "2026-07-14", type: "disclosure", cat: "dilution", tag: "유상증자", ticker: "005930", name: "삼성전자", title: "주요사항보고서(유상증자결정)", url: "" },
        { date: "2026-07-14", type: "disclosure", cat: "buyback", tag: "자사주 취득", ticker: "000660", name: "SK하이닉스", title: "주요사항보고서(자기주식취득결정)", url: "" },
        { date: "2026-07-16", type: "disclosure", cat: "dilution", tag: "CB", ticker: "035720", name: "카카오", title: "주요사항보고서(전환사채발행결정)", url: "" },
        { date: "2026-07-17", type: "dividend", cat: "dividend", tag: "배당락", ticker: "005380", name: "현대차", title: "주당 3,000원 배당락", url: "" },
        { date: "2026-07-24", type: "disclosure", cat: "structural", tag: "합병", ticker: "373220", name: "LG에너지솔루션", title: "주요사항보고서(회사합병결정)", url: "" },
    ],
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicCalendar(props: { dataUrl?: string; stockPath?: string; dark?: boolean }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const [data, setData] = useState<any>(onCanvas ? DEMO : null)
    const [cur, setCur] = useState<{ y: number; m: number }>(() => ({ y: 2026, m: 6 })) // m=0-index (6=July)
    const [selDate, setSelDate] = useState<string>("")
    const [catFilter, setCatFilter] = useState<string>("")
    const [w, setW] = useState(0)
    const [listOpen, setListOpen] = useState(false)   // 모바일 리스트 더보기 펼침
    const rootRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((e) => { for (const x of e) setW(x.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.dataUrl || DATA_URL).then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d || !Array.isArray(d.events)) return
                setData(d)
                try { sessionStorage.setItem("calendar_public", JSON.stringify(d)) } catch (e) {}
                // 데이터 있는 가장 가까운 달로 초기 이동 (오늘 포함 월 우선)
            })
            .catch(() => { try { const c = sessionStorage.getItem("calendar_public"); if (alive && c) setData(JSON.parse(c)) } catch (e) {} })
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    // 리스트 더보기 = 달/선택일/필터가 바뀌면 다시 접기
    useEffect(() => { setListOpen(false) }, [selDate, cur, catFilter])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const narrow = w > 0 && w < 560
    const stockPath = props.stockPath || "/stock"

    const events: any[] = (data && data.events) || []
    // 날짜별 이벤트 맵 (+ 카테고리 필터)
    const byDate = useMemo(() => {
        const m: Record<string, any[]> = {}
        for (const e of events) {
            if (catFilter && e.cat !== catFilter) continue
            if (!e.date) continue
                ; (m[e.date] = m[e.date] || []).push(e)
        }
        return m
    }, [events, catFilter])

    // 현재 월 그리드 (월요일 시작)
    const grid = useMemo(() => {
        const first = new Date(cur.y, cur.m, 1)
        const startDow = (first.getDay() + 6) % 7 // Mon=0
        const start = new Date(cur.y, cur.m, 1 - startDow)
        const cells: Date[] = []
        for (let i = 0; i < 42; i++) { const d = new Date(start); d.setDate(start.getDate() + i); cells.push(d) }
        // 마지막 주가 전부 다음달이면 제거 (5주로 축소)
        while (cells.length >= 42 && cells[cells.length - 7].getMonth() !== cur.m && cells[35] && cells[35].getMonth() !== cur.m) cells.splice(35, 7)
        return cells
    }, [cur])

    const monthEventCount = useMemo(() => {
        let n = 0
        for (const d in byDate) { const dt = new Date(d); if (dt.getFullYear() === cur.y && dt.getMonth() === cur.m) n += byDate[d].length }
        return n
    }, [byDate, cur])

    const shiftMonth = (delta: number) => {
        setSelDate("")
        setCur((s) => { const d = new Date(s.y, s.m + delta, 1); return { y: d.getFullYear(), m: d.getMonth() } })
    }
    const goStock = (tk: string) => {
        if (onCanvas || typeof window === "undefined" || !tk) return
        try { window.location.href = `${stockPath}?q=${encodeURIComponent(tk)}` } catch (e) {}
    }
    const catS = (cat: string) => (isDark ? (CAT_DARK_S[cat] || C.track) : (CAT[cat]?.s || C.track))

    const todayStr = onCanvas ? "2026-07-17" : ymd(new Date())
    const selEvents: any[] = selDate ? (byDate[selDate] || []) : []
    // 선택 안 했으면 이 달 이벤트 전체를 날짜순으로 (하단 리스트)
    const monthList = useMemo(() => {
        const rows = events.filter((e) => { if (catFilter && e.cat !== catFilter) return false; const dt = new Date(e.date); return dt.getFullYear() === cur.y && dt.getMonth() === cur.m })
        rows.sort((a, b) => a.date.localeCompare(b.date))
        return rows
    }, [events, cur, catFilter])
    const listShown = selDate ? selEvents : monthList
    // 🚨 모바일 = 이벤트가 많으면 나열이 길어 불편 → 6건 컷 + 더보기. 데스크톱은 스크롤 카드라 전량.
    // 🔔 향후: 보유종목(holdings) 연동 시 = 사용자 보유 종목 이벤트 우선/필터 (개인화). 지금은 전 종목.
    const LIST_CAP = 6
    const listCapped = narrow && !listOpen && listShown.length > LIST_CAP
    const listRows = listCapped ? listShown.slice(0, LIST_CAP) : listShown

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, padding: narrow ? 14 : 20, boxSizing: "border-box", color: C.ink }
    const cardS: CSSProperties = { background: C.card, borderRadius: 18, padding: narrow ? "16px 14px" : "22px 24px", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }

    if (!data) {
        const sk: CSSProperties = { background: C.track, borderRadius: 10 }
        return (
            <div ref={rootRef} style={wrap}>
                <div style={cardS}>
                    <div style={{ ...sk, width: 120, height: 22 }} />
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 8, marginTop: 20 }}>
                        {Array.from({ length: 35 }).map((_, i) => <div key={i} style={{ ...sk, height: narrow ? 34 : 46 }} />)}
                    </div>
                </div>
            </div>
        )
    }

    const navBtn: CSSProperties = { width: 34, height: 34, borderRadius: 10, border: "none", cursor: "pointer", background: C.hi, color: C.sub, display: "inline-flex", alignItems: "center", justifyContent: "center", fontFamily: FONT }

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: narrow ? 19 : 22, fontWeight: 800, letterSpacing: "-0.5px" }}>투자 캘린더</div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>
                    공시·배당락·IPO 일정 · 각 이벤트에 <b style={{ color: C.sub }}>포렌식 태그</b> — 사실 분류일 뿐 추천 아님
                </div>
            </div>

            {/* 카테고리 필터 칩 */}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
                <button onClick={() => setCatFilter("")} style={{ border: "none", cursor: "pointer", fontFamily: FONT, padding: "6px 12px", borderRadius: 999, fontSize: 12, fontWeight: 800, background: !catFilter ? C.vt : C.card, color: !catFilter ? "#fff" : C.sub, boxShadow: !catFilter ? "none" : "0 1px 2px rgba(0,0,0,0.04)" }}>전체</button>
                {Object.keys(CAT).map((k) => {
                    const on = catFilter === k
                    return (
                        <button key={k} onClick={() => setCatFilter(on ? "" : k)}
                            style={{ border: "none", cursor: "pointer", fontFamily: FONT, padding: "6px 12px", borderRadius: 999, fontSize: 12, fontWeight: 700, background: on ? CAT[k].c : C.card, color: on ? "#fff" : C.sub, display: "inline-flex", alignItems: "center", gap: 5, boxShadow: on ? "none" : "0 1px 2px rgba(0,0,0,0.04)" }}>
                            <span style={{ width: 7, height: 7, borderRadius: "50%", background: on ? "#fff" : CAT[k].c }} />
                            {CAT[k].label}
                        </button>
                    )
                })}
            </div>

            <div style={{ display: narrow ? "block" : "grid", gridTemplateColumns: narrow ? undefined : "1.35fr 1fr", gap: 16, alignItems: "start" }}>
                {/* 월 그리드 */}
                <div style={cardS}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                        <div>
                            <span style={{ fontSize: narrow ? 18 : 21, fontWeight: 800, letterSpacing: "-0.4px" }}>
                                {["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][cur.m]} {cur.y}
                            </span>
                            <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 700, marginLeft: 8 }}>{monthEventCount}건</span>
                        </div>
                        <div style={{ display: "flex", gap: 6 }}>
                            <button onClick={() => shiftMonth(-1)} style={navBtn} aria-label="이전 달">
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
                            </button>
                            <button onClick={() => shiftMonth(1)} style={navBtn} aria-label="다음 달">
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6" /></svg>
                            </button>
                        </div>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: narrow ? 2 : 4 }}>
                        {WEEK.map((wd, i) => (
                            <div key={wd} style={{ textAlign: "center", fontSize: 11, fontWeight: 700, color: i >= 5 ? C.faint : C.sub, paddingBottom: 8 }}>{wd}</div>
                        ))}
                        {grid.map((d, i) => {
                            const ds = ymd(d)
                            const inMonth = d.getMonth() === cur.m
                            const evs = byDate[ds] || []
                            const isToday = ds === todayStr
                            const isSel = ds === selDate
                            const maxLogos = narrow ? 2 : 3
                            return (
                                <button key={i} onClick={() => setSelDate(isSel ? "" : ds)} disabled={!inMonth && evs.length === 0}
                                    style={{
                                        position: "relative", border: "none", cursor: inMonth || evs.length ? "pointer" : "default", fontFamily: FONT,
                                        height: narrow ? 44 : 56, borderRadius: 12, background: isSel ? C.today : (evs.length ? C.hi : "transparent"),
                                        color: isSel ? C.todayInk : inMonth ? C.ink : C.faint, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 3,
                                        fontWeight: isToday ? 800 : 600, transition: "background 0.12s",
                                    }}>
                                    <span style={{ fontSize: narrow ? 12 : 13, opacity: inMonth ? 1 : 0.45, position: "relative", lineHeight: 1 }}>
                                        {d.getDate()}
                                        {isToday && !isSel && <span style={{ position: "absolute", left: "50%", bottom: -3, transform: "translateX(-50%)", width: 3, height: 3, borderRadius: "50%", background: C.vt }} />}
                                    </span>
                                    {evs.length > 0 && (
                                        <span style={{ display: "flex", gap: 2, alignItems: "center", maxWidth: "100%" }}>
                                            {evs.slice(0, maxLogos).map((e, j) => <DayLogo key={j} ev={e} size={narrow ? 11 : 14} />)}
                                            {evs.length > maxLogos && <span style={{ fontSize: 8.5, fontWeight: 800, color: isSel ? C.todayInk : C.faint, marginLeft: 1 }}>+{evs.length - maxLogos}</span>}
                                        </span>
                                    )}
                                </button>
                            )
                        })}
                    </div>
                </div>

                {/* 이벤트 리스트 (선택일 or 이 달 전체) */}
                <div style={{ ...cardS, marginTop: narrow ? 16 : 0, padding: narrow ? "14px 14px" : "18px 18px", maxHeight: narrow ? undefined : 560, overflowY: narrow ? undefined : "auto" }}>
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
                        <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>
                            {selDate ? selDate.slice(5).replace("-", "/") + " 이벤트" : "이 달 이벤트"}
                        </span>
                        <span style={{ fontSize: 11, color: C.faint, fontWeight: 700 }}>{listShown.length}건{selDate ? "" : " · 날짜순"}</span>
                    </div>
                    {listShown.length === 0 ? (
                        <div style={{ padding: "24px 8px", textAlign: "center", color: C.faint, fontSize: 12.5, fontWeight: 600 }}>
                            {selDate ? "이 날은 이벤트가 없어요." : "이 달 이벤트가 없어요. 다른 달을 확인해 보세요."}
                        </div>
                    ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {listRows.map((e, i) => {
                                const cat = CAT[e.cat] || { label: e.cat, c: C.faint, s: C.track }
                                return (
                                    <div key={i} onClick={() => goStock(e.ticker)} role={e.ticker ? "button" : undefined}
                                        style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 11px", borderRadius: 12, background: isDark ? C.hi : C.hi, cursor: e.ticker ? "pointer" : "default" }}>
                                        <StockDot ticker={e.ticker} name={e.name} size={26} />
                                        <div style={{ minWidth: 0, flex: 1 }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                                                <span style={{ fontSize: 13, fontWeight: 800, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 140 }}>{e.name || e.tag}</span>
                                                <span style={{ fontSize: 10, fontWeight: 800, color: cat.c, background: catS(e.cat), borderRadius: 6, padding: "2px 7px", flexShrink: 0 }}>{e.tag}</span>
                                                {!selDate && <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 700, marginLeft: "auto", flexShrink: 0 }}>{e.date.slice(5).replace("-", "/")}</span>}
                                            </div>
                                            <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, marginTop: 3, lineHeight: 1.4, wordBreak: "break-word" }}>{e.title}</div>
                                            {e.url ? (
                                                <a href={e.url} target="_blank" rel="noopener noreferrer" onClick={(ev) => ev.stopPropagation()}
                                                    style={{ fontSize: 10.5, color: C.vt, fontWeight: 700, textDecoration: "none", marginTop: 3, display: "inline-block" }}>DART 원문 ›</a>
                                            ) : null}
                                        </div>
                                    </div>
                                )
                            })}
                            {narrow && listShown.length > LIST_CAP ? (
                                <button onClick={() => setListOpen((v) => !v)}
                                    style={{ width: "100%", marginTop: 2, border: "none", cursor: "pointer", fontFamily: FONT, background: C.hi, color: C.vt, borderRadius: 12, padding: "11px 0", fontSize: 12.5, fontWeight: 800 }}>
                                    {listOpen ? "접기" : `더보기 (${listShown.length - LIST_CAP}건 더)`}
                                </button>
                            ) : null}
                        </div>
                    )}
                </div>
            </div>

            <div style={{ textAlign: "center", fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 14, lineHeight: 1.55 }}>
                이벤트 = 공개 사실(DART·배당·IPO) · 포렌식 태그 = 공시 분류 · 실적발표 예정일·락업은 준비 중
                {data._meta && data._meta.generated_at ? " · " + String(data._meta.generated_at).slice(0, 10) + " 기준" : ""}
            </div>
        </div>
    )
}

addPropertyControls(PublicCalendar, {
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DATA_URL },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

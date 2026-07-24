import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 투자 캘린더 — AlphaNest 공개 터미널. 이미지 참고 = 깔끔 월 그리드(토스식).
 *
 * 🚨 차별점(RULE 6/7): 범용 실적 캘린더(네이버·토스 강자영역) 흉내 X.
 *   우리 강점 = 공시 포렌식. 각 이벤트에 사실 카테고리 태그(희석/자사주/구조/배당/IPO) + 종목 로고 + DART 원문.
 *   점수·등급·추천 0 (사실 분류 태그만).
 * 데이터 = calendar_public.json (calendar_public_builder — 공시·배당락·IPO 병합, 신규수집 0).
 * 로고 = 토스 종목 CDN + 이니셜 폴백. cache-fallback.
 */

/* 🚨🚨 롤백 방지 가드 (2026-07-23) — CLAUDE.md RULE 11. 지우거나 되돌리지 말 것. 🚨🚨
 *
 * 이 repo .tsx = 라이브 Framer(AlphaNest 공개 프로젝트)의 미러. 양방향 stale 가능(라이브 편집 미반영 또는 그 반대).
 * 되돌리면 안 되는 레이아웃:
 *   · 우측 이벤트 리스트("종목 스크롤창") = 데스크톱에서 height = 좌측 캘린더 카드 offsetHeight(calH, calRef ResizeObserver, border-box) 정확 매칭 + overflowY:auto(스크롤).
 *     static height/maxHeight(560 등)나 alignItems 로 되돌리지 말 것 — 정적값은 캘린더 높이와 안 맞음(2026-07-23 사고).
 *
 * 편집/붙여넣기 전 의무 (RULE 11):
 *   1. Framer 데스크탑 = AlphaNest 공개 프로젝트 탭 focus 확인. 2. MCP readCodeFile 로 라이브 먼저 읽어 3-way diff.
 *   3. 라이브 더 신선하면 라이브 base 로 갱신. 4. 3소스 동시 동기화(라이브 MCP + repo + 메모리).
 *
 * 🚨 2026-07-24 다크모드 = 자체 내장 CSS 변수(--an-cal-*) 구동 (readBodyDark JS 감지 전면 제거, durable fix).
 *   <style>{AN_PALETTE} 정적 HTML 정합 → 새로고침/무거운 페이지 stuck-라이트 근본 제거. 카테고리 soft-bg도 변수화. 되돌리지 말 것.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", track: "#eef0f3", hi: "#f6f7f9", vt: "#6c5ce7", vtS: "#f0edff", vtSolid: "#6c5ce7",
    today: "#191f28", todayInk: "#ffffff", cellHover: "#f6f7f9",
    dilutionS: "#fdecee", buybackS: "#eaf1fe", supplyS: "#eef0f3", dividendS: "#e7faf0",
    ipoS: "#f0edff", capitalS: "#fff4e0", structuralS: "#e3f7f9", governanceS: "#fdf0dc",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", track: "#222a33", hi: "#1e242c", vt: "#a99bff", vtS: "#241f3a", vtSolid: "#6c5ce7",
    today: "#e3e7ec", todayInk: "#0f1318", cellHover: "#1e242c",
    dilutionS: "#2a1518", buybackS: "#17263c", supplyS: "#252b34", dividendS: "#11281d",
    ipoS: "#241f3a", capitalS: "#2a2113", structuralS: "#0f2a2d", governanceS: "#2a2010",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DATA_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/calendar_public.json"

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-cal-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "cal"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

// 이벤트 카테고리 = 사실 분류(색은 가독용, 좋다·나쁘다 라벨 아님). soft-bg 는 --an-cal-<cat>S 변수(테마 플립).
const CAT: Record<string, { label: string; c: string }> = {
    dilution: { label: "희석", c: "#f04452" },      // 유증·CB·BW
    buyback: { label: "자사주", c: "#3182f6" },     // 취득·소각(수급+)
    supply: { label: "자사주처분", c: "#8b95a1" },  // 처분(수급-)
    dividend: { label: "배당", c: "#0ca678" },
    ipo: { label: "IPO", c: "#6c5ce7" },
    capital: { label: "자본변동", c: "#ff9500" },
    structural: { label: "구조", c: "#00a8b5" },
    governance: { label: "지배구조", c: "#e6820a" },
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
    const [data, setData] = useState<any>(onCanvas ? DEMO : null)
    const [cur, setCur] = useState<{ y: number; m: number }>(() => ({ y: 2026, m: 6 })) // m=0-index (6=July)
    const [selDate, setSelDate] = useState<string>("")
    const [catFilter, setCatFilter] = useState<string>("")
    const [w, setW] = useState(0)
    const [calH, setCalH] = useState(0)   // 좌측 캘린더 카드 실측 높이 → 우측 리스트 매칭
    const [listOpen, setListOpen] = useState(false)   // 모바일 리스트 더보기 펼침
    const rootRef = useRef<HTMLDivElement>(null)
    const calRef = useRef<HTMLDivElement>(null)   // 좌측 캘린더 카드(높이 소스)

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((e) => { for (const x of e) setW(x.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    // 좌측 캘린더 카드 높이 실측(offsetHeight=border-box) → 우측 이벤트 리스트("종목 스크롤창") 높이 정확 매칭. data 로드 후 calRef 부착.
    useEffect(() => {
        const el = calRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver(() => setCalH(el.offsetHeight))
        ro.observe(el)
        return () => ro.disconnect()
    }, [data])

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
    // 카테고리 soft-bg = --an-cal-<cat>S 변수(라이트/다크 자동 플립). 미지정 카테고리 = track.
    const catS = (cat: string) => (C as any)[cat + "S"] || C.track

    const todayStr = onCanvas ? "2026-07-17" : ymd(new Date())
    const selEvents: any[] = selDate ? (byDate[selDate] || []) : []
    // 선택 안 했으면 이 달 이벤트 전체를 날짜순으로 (하단 리스트)
    const monthList = useMemo(() => {
        const rows = events.filter((e) => { if (catFilter && e.cat !== catFilter) return false; const dt = new Date(e.date); return dt.getFullYear() === cur.y && dt.getMonth() === cur.m })
        rows.sort((a, b) => a.date.localeCompare(b.date))
        return rows
    }, [events, cur, catFilter])
    const listShown = selDate ? selEvents : monthList
    const LIST_CAP = 6
    const listCapped = narrow && !listOpen && listShown.length > LIST_CAP
    const listRows = listCapped ? listShown.slice(0, LIST_CAP) : listShown

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, padding: narrow ? 14 : 20, boxSizing: "border-box", color: C.ink }
    const cardS: CSSProperties = { background: C.card, borderRadius: 18, padding: narrow ? "16px 14px" : "22px 24px", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }

    if (!data) {
        const sk: CSSProperties = { background: C.track, borderRadius: 10 }
        return (
            <div ref={rootRef} style={wrap}>
                <style>{AN_PALETTE}</style>
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
            <style>{AN_PALETTE}</style>
            {/* 헤더 */}
            <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: narrow ? 19 : 22, fontWeight: 800, letterSpacing: "-0.5px" }}>투자 캘린더</div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>
                    공시·배당락·IPO 일정 · 각 이벤트에 <b style={{ color: C.sub }}>포렌식 태그</b> — 사실 분류일 뿐 추천 아님
                </div>
            </div>

            {/* 카테고리 필터 칩 */}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
                <button onClick={() => setCatFilter("")} style={{ border: "none", cursor: "pointer", fontFamily: FONT, padding: "6px 12px", borderRadius: 999, fontSize: 12, fontWeight: 800, background: !catFilter ? C.vtSolid : C.card, color: !catFilter ? "#fff" : C.sub, boxShadow: !catFilter ? "none" : "0 1px 2px rgba(0,0,0,0.04)" }}>전체</button>
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
                <div ref={calRef} style={cardS}>
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
                            const cats = Array.from(new Set(evs.map((e: any) => e.cat))).slice(0, 3)
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
                                        <span style={{ display: "flex", gap: 3, alignItems: "center" }}>
                                            {cats.map((cat, j) => <span key={j} style={{ width: 5, height: 5, borderRadius: "50%", background: isSel ? C.todayInk : (CAT[cat] ? CAT[cat].c : C.faint) }} />)}
                                            {evs.length > 3 && <span style={{ fontSize: 8.5, fontWeight: 800, color: isSel ? C.todayInk : C.faint, marginLeft: 1 }}>+{evs.length - 3}</span>}
                                        </span>
                                    )}
                                </button>
                            )
                        })}
                    </div>
                </div>

                {/* 이벤트 리스트 (선택일 or 이 달 전체) — height = 캘린더 카드 높이 정확 매칭 + 스크롤 */}
                <div style={{ ...cardS, boxSizing: "border-box", marginTop: narrow ? 16 : 0, padding: narrow ? "14px 14px" : "18px 18px", height: narrow ? undefined : (calH || 560), overflowY: narrow ? undefined : "auto" }}>
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
                                const cat = CAT[e.cat] || { label: e.cat, c: C.faint }
                                return (
                                    <div key={i} onClick={() => goStock(e.ticker)} role={e.ticker ? "button" : undefined}
                                        style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 11px", borderRadius: 12, background: C.hi, cursor: e.ticker ? "pointer" : "default" }}>
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
    dark: { type: ControlType.Boolean, title: "Dark(미사용)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

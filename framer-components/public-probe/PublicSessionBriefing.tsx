// AlphaNest Design v1: .cursor/rules/alphanest-interaction.mdc
// Preserve: trading date = three cards; closed date = one card. Never synthesize historical facts.
// Current-session emphasis follows verified time, independently of the card selected for reading.
// Expanded detail follows its reading card in DOM order; CSS places it below the row on desktop.
import * as React from "react"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"

type Phase = "pre" | "open" | "post" | "closed"
type TradingStatus = "open" | "closed" | "unknown"
type Item = { id: string; category: string; ticker?: string; name?: string; title: string; text: string; as_of?: string; event_date?: string; date_kind?: string; url?: string; values?: Record<string, unknown> }
type Snapshot = { snapshot_id: string; generated_at: string; phase: Phase | "unknown"; items: Item[] }
type Calendar = { valid_from: string; valid_until: string; holidays: string[]; unknown_dates?: string[]; open_minute: number; close_minute: number }
type Day = { schema_version: number; date: string; trading_day: { status: TradingStatus }; snapshots: Snapshot[]; cards: Partial<Record<Phase, string | null>>; day_summary?: { status: string; generated_at?: string; cutoff_at?: string; snapshot_ids?: string[]; observed_changes?: unknown[] } }
type Index = { schema_version: number; generated_at: string; calendar?: Calendar; days: { date: string; trading_day: { status: TradingStatus }; latest_at?: string }[] }
type Props = { dark?: boolean; archiveBaseUrl?: string; holdingsTickers?: string[]; personalizationState?: "loading" | "market" | "holdings" | "error"; style?: CSSProperties }
const BASE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/briefing_days"
const LABEL: Record<Phase, string> = { pre: "장전", open: "장중", post: "장후", closed: "휴장" }
const QUESTION: Record<Phase, string> = { pre: "시작 전에 살펴볼 것", open: "장전과 달라진 것", post: "오늘 확인한 변화", closed: "쉬는 날에도 이어지는 변화" }
const HINT: Record<Phase, string> = { pre: "새 공시와 예정된 일정을 먼저 살펴봐요.", open: "앞선 기록과 새로 확인한 내용을 비교해요.", post: "마감 이후 소식까지 모아 하루를 돌아봐요.", closed: "새로 들어온 자료와 다음 거래일의 확인거리를 모아요." }
const ORDER: Phase[] = ["pre", "open", "post"]
const LIGHT_TONE = { card: "#ffffff", back: "#f8f9fb", hover: "#f1f3f5", focus: "#e9edf2", ink: "#191f28", sub: "#6b7684", accent: "#6c5ce7", pre: "#ff9500", open: "#15c47e", post: "#6c5ce7", closed: "#f04452" }
const DARK_TONE = { card: "#171c23", back: "#1d242c", hover: "#252c35", focus: "#303945", ink: "#e3e7ec", sub: "#9aa4b1", accent: "#a99bff", pre: "#ffb454", open: "#34e08a", post: "#a99bff", closed: "#ff5c68" }
const themeVars = (tone: Record<string, string>) => Object.entries(tone).map(([key, value]) => `--asb-${key}:${value}`).join(";")
const datePattern = /^\d{4}-\d{2}-\d{2}$/
const tickerPattern = /^(\d{6}|[A-Z][A-Z0-9.-]{0,11})$/
const list = <T,>(value: unknown): T[] => Array.isArray(value) ? value : []
export function validDate(value: unknown): value is string { return typeof value === "string" && datePattern.test(value) && Number.isFinite(Date.parse(value)) && new Date(value + "T00:00:00Z").toISOString().slice(0, 10) === value }
const validStamp = (value: unknown) => typeof value === "string" && /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))
const validStatus = (value: unknown) => ["open", "closed", "unknown"].includes(String(value))
export function normalizeIndex(value: any): Index {
    if (value?.schema_version !== 1 || !validStamp(value.generated_at) || !Array.isArray(value.days) || value.days.some((d: any) => !validDate(d?.date) || !validStatus(d?.trading_day?.status))) throw Error("Invalid index")
    const c = value.calendar
    if (c && (!validDate(c.valid_from) || !validDate(c.valid_until) || !Array.isArray(c.holidays) || c.holidays.some((d: unknown) => !validDate(d)) || (c.unknown_dates && (!Array.isArray(c.unknown_dates) || c.unknown_dates.some((d: unknown) => !validDate(d)))) || !Number.isFinite(c.open_minute) || !Number.isFinite(c.close_minute) || c.open_minute < 0 || c.close_minute > 1440 || c.open_minute >= c.close_minute)) throw Error("Invalid calendar")
    return { ...value, days: [...value.days].sort((a, b) => b.date.localeCompare(a.date)) }
}
export function normalizeDay(value: any, date: string): Day {
    if (value?.schema_version !== 1 || !validDate(value.date) || value.date !== date || !validStatus(value.trading_day?.status) || !Array.isArray(value.snapshots) || !value.cards || typeof value.cards !== "object" || Array.isArray(value.cards)) throw Error("Invalid day")
    const ids = new Set<string>()
    for (const s of value.snapshots) {
        if (typeof s?.snapshot_id !== "string" || ids.has(s.snapshot_id) || !validStamp(s.generated_at) || kstDate(Date.parse(s.generated_at)) !== date || !["pre", "open", "post", "closed", "unknown"].includes(s.phase) || !Array.isArray(s.items)) throw Error("Invalid snapshot")
        ids.add(s.snapshot_id)
        const items = new Set<string>()
        for (const i of s.items) {
            if (!i || ["id", "title", "text", "category"].some(k => typeof i[k] !== "string") || items.has(i.id) || (i.ticker != null && (typeof i.ticker !== "string" || !tickerPattern.test(i.ticker))) || ["name", "as_of", "url"].some(k => i[k] != null && typeof i[k] !== "string")) throw Error("Invalid item")
            if (i.event_date != null && !validDate(i.event_date)) throw Error("Invalid event date")
            items.add(i.id)
        }
    }
    for (const p of ["pre", "open", "post", "closed"]) if (value.cards[p] != null && !value.snapshots.some((s: Snapshot) => s.snapshot_id === value.cards[p] && s.phase === p)) throw Error("Invalid card")
    return value
}
export function dayItems(day: Day | null, phase: Phase): Item[] {
    if (phase === "post" && day?.day_summary?.status === "closed") {
        const items = new Map<string, Item>()
        for (const s of [...day.snapshots].sort((a, b) => Date.parse(a.generated_at) - Date.parse(b.generated_at))) for (const item of s.items) items.set(item.id, item)
        return [...items.values()]
    }
    return list<Item>(day?.snapshots.find(s => s.snapshot_id === day.cards[phase])?.items)
}
export function phaseCards(status: TradingStatus): Phase[] { return status === "closed" ? ["closed"] : status === "open" ? ORDER : [] }
export function tradingStatus(date: string, calendar?: Calendar): TradingStatus {
    if (!calendar || !validDate(date) || date < calendar.valid_from || date > calendar.valid_until || list<string>(calendar.unknown_dates).includes(date)) return "unknown"
    const weekday = new Date(date + "T12:00:00Z").getUTCDay()
    return weekday === 0 || weekday === 6 || list<string>(calendar.holidays).includes(date) ? "closed" : "open"
}
export function kstDate(epoch: number): string { return new Date(epoch + 9 * 3600000).toISOString().slice(0, 10) }
export function activePhase(epoch: number | null, status: TradingStatus, calendar?: Calendar): Phase | null {
    if (!epoch || !Number.isFinite(epoch) || epoch < 0 || status === "unknown") return null
    if (status === "closed") return "closed"
    if (!calendar || !Number.isFinite(calendar.open_minute) || !Number.isFinite(calendar.close_minute) || calendar.open_minute < 0 || calendar.close_minute > 1440 || calendar.open_minute >= calendar.close_minute) return null
    const d = new Date(epoch + 9 * 3600000), minute = d.getUTCHours() * 60 + d.getUTCMinutes()
    return minute < calendar.open_minute ? "pre" : minute < calendar.close_minute ? "open" : "post"
}
export function phaseRelation(phase: Phase, date: string, today: string, current: Phase | null): "past" | "current" | "future" | "unknown" {
    if (!validDate(date) || !validDate(today)) return "unknown"
    if (date < today) return "past"
    if (date > today) return "future"
    if (!current) return "unknown"
    if (phase === current) return "current"
    if (!ORDER.includes(phase) || !ORDER.includes(current)) return "unknown"
    return ORDER.indexOf(phase) < ORDER.indexOf(current) ? "past" : "future"
}
function durationText(milliseconds: number, remaining: boolean) {
    if (milliseconds < 60000) return "1분 미만"
    const minutes = remaining ? Math.ceil(milliseconds / 60000) : Math.floor(milliseconds / 60000)
    const days = Math.floor(minutes / 1440), hours = Math.floor(minutes % 1440 / 60), rest = minutes % 60
    return [days && `${days}일`, hours && `${hours}시간`, rest && `${rest}분`].filter(Boolean).join(" ")
}
export function sessionTimeLabel(epoch: number | null, status: TradingStatus, calendar?: Calendar): string {
    if (!epoch || !Number.isFinite(epoch) || epoch < 0) return "시각 확인 중"
    const date = kstDate(epoch), phase = activePhase(epoch, status, calendar)
    if (!calendar || !phase || tradingStatus(date, calendar) !== status || !Number.isFinite(calendar.open_minute) || !Number.isFinite(calendar.close_minute) || calendar.open_minute < 0 || calendar.close_minute > 1440 || calendar.open_minute >= calendar.close_minute) return "장 일정 확인 중"
    const midnight = Date.parse(date + "T00:00:00+09:00"), opens = midnight + calendar.open_minute * 60000, closes = midnight + calendar.close_minute * 60000
    if (phase === "pre") return `개장 ${durationText(opens - epoch, true)} 전`
    if (phase === "open") return `장 마감 ${durationText(closes - epoch, true)} 전`
    if (phase === "post") return `장 마감 ${durationText(epoch - closes, false)} 경과`
    // Stop at any unverified date rather than skipping it and guessing the next opening.
    for (let offset = 1; offset <= 14; offset++) {
        const next = kstDate(midnight + offset * 86400000), nextStatus = tradingStatus(next, calendar)
        if (nextStatus === "unknown") break
        if (nextStatus === "open") return `다음 개장 ${durationText(midnight + offset * 86400000 + calendar.open_minute * 60000 - epoch, true)} 전`
    }
    return "다음 개장 일정 확인 중"
}
function sessionWindow(phase: Phase, date: string, calendar?: Calendar): string {
    if (!calendar || tradingStatus(date, calendar) === "unknown") return ""
    const hhmm = (minute: number) => `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`
    return phase === "pre" ? `${hhmm(calendar.open_minute)} 개장 전` : phase === "open" ? `${hhmm(calendar.open_minute)}–${hhmm(calendar.close_minute)}` : phase === "post" ? `${hhmm(calendar.close_minute)} 마감 이후` : "휴장일 기록"
}
export function serverEpoch(date: string | null, age: string | null, roundTrip: number): number | null {
    const stamp = date ? Date.parse(date) : NaN, seconds = age == null ? 0 : Number(age)
    return Number.isFinite(stamp) && Number.isFinite(seconds) && seconds >= 0 && roundTrip >= 0 && roundTrip < 10000 ? stamp + seconds * 1000 + roundTrip / 2 : null
}
function useInternetTime() {
    const [epoch, setEpoch] = useState<number | null>(null), anchor = useRef<{ epoch: number; monotonic: number } | null>(null)
    useEffect(() => {
        if (RenderTarget.current() === RenderTarget.canvas) return
        let disposed = false, busy = false
        const controller = new AbortController()
        const tick = () => { const a = anchor.current; setEpoch(a && performance.now() - a.monotonic < 15 * 60000 ? a.epoch + performance.now() - a.monotonic : null) }
        const sync = async () => {
            if (busy || document.hidden) return
            busy = true
            const start = performance.now(), request = new AbortController(), timeout = setTimeout(() => request.abort(), 8000)
            const cancel = () => request.abort(); controller.signal.addEventListener("abort", cancel, { once: true })
            try {
                // Same-origin Date is readable without exposing cross-origin headers. No account data is sent.
                const response = await fetch(window.location.origin + "/", { method: "HEAD", cache: "no-store", credentials: "omit", signal: request.signal })
                const value = response.ok ? serverEpoch(response.headers.get("Date"), response.headers.get("Age"), performance.now() - start) : null
                if (!disposed && value) { anchor.current = { epoch: value, monotonic: performance.now() }; tick() }
            } catch { if (!disposed) tick() } finally { clearTimeout(timeout); controller.signal.removeEventListener("abort", cancel); busy = false }
        }
        const resume = () => { tick(); void sync() }
        void sync()
        const seconds = setInterval(tick, 15000), refresh = setInterval(sync, 300000)
        window.addEventListener("focus", resume); window.addEventListener("online", resume); document.addEventListener("visibilitychange", resume)
        return () => { disposed = true; controller.abort(); clearInterval(seconds); clearInterval(refresh); window.removeEventListener("focus", resume); window.removeEventListener("online", resume); document.removeEventListener("visibilitychange", resume) }
    }, [])
    return epoch
}
function safeURL(value?: string) { try { const u = new URL(value || ""); return ["http:", "https:"].includes(u.protocol) && !u.username && !u.password ? u.href : "" } catch { return "" } }
function stamp(value?: string) { if (!value) return "기준 미제공"; if (datePattern.test(value)) return value; const d = new Date(value); return Number.isFinite(d.getTime()) ? d.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) + " KST" : "기준 미제공" }
function itemText(item: Item) { return item.text || (item.category === "earnings" ? "실적 공시 예상 일정" : item.title) || "내용 미제공" }
export function changedFragments(before: string, after: string) {
    const a = before.match(/\d[\d,.]*|\p{L}+|\s+|[^\s]/gu) || [], b = after.match(/\d[\d,.]*|\p{L}+|\s+|[^\s]/gu) || []
    let start = 0, end = 0
    while (start < Math.min(a.length, b.length) && a[start] === b[start]) start++
    while (end < Math.min(a.length, b.length) - start && a[a.length - end - 1] === b[b.length - end - 1]) end++
    return { prefix: a.slice(0, start).join(""), before: a.slice(start, a.length - end).join(""), after: b.slice(start, b.length - end).join(""), suffix: end ? a.slice(-end).join("") : "" }
}
export function itemChange(before: Item, after?: Item): "revision" | "observation" | null {
    if (!after || before.id !== after.id || (itemText(before) === itemText(after) && JSON.stringify(before.values || {}) === JSON.stringify(after.values || {}))) return null
    return before.as_of && before.as_of === after.as_of ? "revision" : "observation"
}
function visibleItems(items: Item[], holdings: string[], personal: boolean) {
    if (!personal) return items
    const held = items.filter(i => i.ticker && holdings.includes(i.ticker)), market = items.filter(i => !i.ticker)
    return held.length && market.length ? [held[0], market[0], ...held.slice(1), ...market.slice(1)] : [...held, ...market]
}
function Identity({ item }: { item: Item }) {
    const [failed, setFailed] = useState(false)
    useEffect(() => setFailed(false), [item.ticker])
    return <span className="asb-identity">{item.ticker && tickerPattern.test(item.ticker) && <span className="asb-logo">{failed ? (item.name || item.ticker).slice(0, 1) : <img alt="" src={`https://static.toss.im/png-icons/securities/icn-sec-fill-${item.ticker}.png`} onError={() => setFailed(true)} loading="lazy" />}</span>}<span>{item.name || item.category || "시장"}</span></span>
}
function Fact({ item, later, previous, compact = false }: { item: Item; later?: Item; previous?: Item; compact?: boolean }) {
    const revision = itemChange(item, later), incoming = previous ? itemChange(previous, item) : null
    const diff = revision === "revision" && later ? changedFragments(itemText(item), itemText(later)) : null, url = safeURL(item.url)
    return <div className="asb-fact"><Identity item={item} /><p className={compact ? "asb-clamp" : ""}>{diff && diff.before !== diff.after ? <>{diff.prefix}<del aria-label="변경 전">{diff.before}</del>{" "}<ins aria-label="변경 후">{diff.after}</ins>{diff.suffix}</> : itemText(item)}</p>{revision && <span className="asb-change">{revision === "revision" ? "이후 기록에서 내용 변경" : "이후 시점의 새 관측 있음"}</span>}{incoming && <span className="asb-change">{incoming === "revision" ? "앞선 기록에서 변경됨" : "기준 시점 갱신"}</span>}{item.event_date && <small>{item.date_kind === "expected" ? "예상 일정" : "사건 날짜"} {stamp(item.event_date)}</small>}<small>{item.as_of ? `자료 기준 ${stamp(item.as_of)}` : "자료 기준 미제공"}</small>{!compact && revision === "observation" && later && <p className="asb-change">이후 {stamp(later.as_of)} · {itemText(later)}</p>}{!compact && incoming === "revision" && previous && <p className="asb-change">이전 기록: {itemText(previous)}</p>}{!compact && url && <a href={url} target="_blank" rel="noopener noreferrer">원문 확인 ↗</a>}</div>
}
/** @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 * @framerIntrinsicWidth 1080
 * @framerIntrinsicHeight 420
 */
export default function PublicSessionBriefing({ dark = false, archiveBaseUrl = BASE, holdingsTickers = [], personalizationState = "market", style }: Props) {
    const epoch = useInternetTime(), today = epoch ? kstDate(epoch) : ""
    const [index, setIndex] = useState<Index | null>(null), [storedDay, setDay] = useState<Day | null>(null), [dateChoice, setDateChoice] = useState("")
    const [indexFailed, setIndexFailed] = useState(false), [dayFailed, setDayFailed] = useState(false), [indexPending, setIndexPending] = useState(true), [dayPending, setDayPending] = useState(false), [revision, setRevision] = useState(0), [selected, setSelected] = useState<Phase | null>(null), [expanded, setExpanded] = useState(false), [marketView, setMarketView] = useState(false)
    const failed = indexFailed || dayFailed, pending = indexPending || dayPending
    const base = safeURL(archiveBaseUrl)?.replace(/\/$/, "") || BASE, latestDate = index?.days[0]?.date || "", chosenDate = dateChoice || today || latestDate
    const day = storedDay?.date === chosenDate ? storedDay : null
    useEffect(() => { const refresh = () => { if (!document.hidden) setRevision(n => n + 1) }; const id = setInterval(refresh, 300000); window.addEventListener("focus", refresh); document.addEventListener("visibilitychange", refresh); return () => { clearInterval(id); window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh) } }, [])
    useEffect(() => {
        if (RenderTarget.current() === RenderTarget.canvas) { setIndexPending(false); return }
        let alive = true
        const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 10000)
        fetch(`${base}/index.json`, { signal: controller.signal, credentials: "omit", cache: "no-cache" }).then(r => { if (!r.ok) throw Error("index"); return r.json() }).then(normalizeIndex).then(value => { if (alive) { setIndex(value); setIndexFailed(false) } }).catch(() => { if (alive) setIndexFailed(true) }).finally(() => { clearTimeout(timeout); if (alive) setIndexPending(false) })
        return () => { alive = false; controller.abort(); clearTimeout(timeout) }
    }, [base, revision, today])
    useEffect(() => {
        setDay(null); setDayFailed(false); setSelected(null); setExpanded(false)
    }, [chosenDate, base])
    useEffect(() => {
        if (!index || !chosenDate || !index.days.some(d => d.date === chosenDate)) { setDayPending(false); return }
        let alive = true
        const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 10000)
        setDayPending(true)
        fetch(`${base}/${chosenDate}.json`, { signal: controller.signal, credentials: "omit", cache: "no-cache" }).then(r => { if (!r.ok) throw Error("day"); return r.json() }).then(value => normalizeDay(value, chosenDate)).then(value => { if (alive) { setDay(value); setDayFailed(false) } }).catch(() => { if (alive) setDayFailed(true) }).finally(() => { clearTimeout(timeout); if (alive) setDayPending(false) })
        return () => { alive = false; controller.abort(); clearTimeout(timeout) }
    }, [index, chosenDate, base, revision])
    const historical = !!chosenDate && !!today && chosenDate < today
    const status = day?.trading_day.status || tradingStatus(chosenDate, index?.calendar), phases = phaseCards(status)
    const current = chosenDate === today ? activePhase(epoch, status, index?.calendar) : null
    const snapshots = list<Snapshot>(day?.snapshots).filter(s => s && Array.isArray(s.items) && (!epoch || Date.parse(s.generated_at) <= epoch + 1000)).sort((a, b) => Date.parse(a.generated_at) - Date.parse(b.generated_at))
    const viewDay = day ? { ...day, snapshots } : null
    const latestById = new Map<string, Item>()
    for (const s of snapshots) for (const item of s.items) latestById.set(item.id, item)
    const latest = snapshots[snapshots.length - 1], preferred = phases.includes(current as Phase) ? current : [...phases].reverse().find(p => !!day?.cards[p] || (p === "post" && day?.day_summary?.status === "closed")) || phases[0], active = phases.includes(selected as Phase) ? selected : preferred
    const holdings = useMemo(() => holdingsTickers.filter(t => tickerPattern.test(t)), [holdingsTickers]), personal = personalizationState === "holdings" && holdings.length > 0 && !marketView
    const dates = Array.from(new Set([today, ...list<Index["days"][number]>(index?.days).map(d => d.date)].filter(Boolean))).sort().reverse()
    const scopeText = personalizationState === "loading" ? "보유종목 확인 중 · 시장 정보 먼저" : personalizationState === "error" ? "보유종목을 불러오지 못해 시장 정보 표시" : personal ? `내 보유종목 ${holdings.length}개와 시장` : "시장 전체"
    const selectedSnapshot = snapshots.find(s => s.snapshot_id === day?.cards[active as Phase]), chosenItems = visibleItems(dayItems(viewDay, active as Phase), holdings, personal)
    const phasePosition = (p?: string) => ORDER.indexOf(p as Phase)
    const earlierSnapshot = selectedSnapshot ? snapshots.filter(s => Date.parse(s.generated_at) < Date.parse(selectedSnapshot.generated_at) && phasePosition(s.phase) < phasePosition(selectedSnapshot.phase)).slice(-1)[0] : undefined
    const summaryClosed = day?.day_summary?.status === "closed"
    const detail = expanded && active ? <div className="asb-detail" data-phase={active} data-edge={phases.indexOf(active) === 0 ? "first" : phases.indexOf(active) === phases.length - 1 ? "last" : "middle"}><div className="asb-detail-heading"><h3>{LABEL[active]} 기록{historical ? ` · ${chosenDate}` : ""}</h3><button type="button" aria-label="상세 기록 접기" onClick={() => setExpanded(false)}>닫기 ×</button></div>{active === "post" && summaryClosed && <p className="asb-summary">{day?.day_summary?.snapshot_ids?.length || 0}개 기록을 모았어요. 하루 동안 새로 들어오거나 달라진 내용 {day?.day_summary?.observed_changes?.length || 0}건 · 종합 {stamp(day?.day_summary?.generated_at)}</p>}{chosenItems.length ? chosenItems.map(item => <Fact key={item.id} item={item} later={selectedSnapshot !== latest ? latestById.get(item.id) : undefined} previous={earlierSnapshot?.items.find(v => v.id === item.id)} />) : <p className="asb-empty">표시할 기록이 없어요.</p>}<p className="asb-note">원래 기록은 보존해요. 같은 자료의 내용이 바뀌면 취소선과 보라색으로, 기준 시점이 달라지면 ‘이후 관측’으로 구분해요.</p></div> : null
    const clock = epoch ? new Date(epoch + 9 * 3600000).toISOString().slice(11, 16) : ""
    return <section className="asb" data-session-timeline data-trading-status={status} data-theme={dark ? "dark" : undefined} style={style} aria-label="하루 시장 흐름">
        <style>{CSS}</style><header className="asb-heading"><div><span className="asb-eyebrow">하루의 흐름</span><h2>지금, 무엇을 살펴볼까요?</h2><p>{scopeText}</p></div><label className="asb-date"><span>기록 날짜</span><span className="asb-date-select"><select aria-label="브리핑 기록 날짜" value={chosenDate} disabled={!dates.length} onChange={e => setDateChoice(e.target.value === today ? "" : e.target.value)}>{dates.length ? dates.map(d => <option key={d} value={d}>{d === today ? "오늘 · " : ""}{d.replaceAll("-", ".")}</option>) : <option value="">날짜 확인 중</option>}</select><span className="asb-select-chevron" aria-hidden="true" /></span></label></header>
        <div className="asb-meta"><span>국내 정규장 기준 · {epoch ? <>현재 <time className="asb-clock" dateTime={new Date(epoch).toISOString()}>{clock} KST</time></> : "시각 확인 중"}{historical ? " · 이전 기록" : ""}</span>{personalizationState === "holdings" && holdings.length > 0 && <button type="button" aria-pressed={marketView} onClick={() => setMarketView(v => !v)}>{marketView ? "내 보유종목 기준" : "시장 전체 보기"}</button>}</div>
        {failed && <div className="asb-status" role="status">기록을 불러오지 못했어요.{day ? " 마지막으로 받은 기록을 표시해요." : " 잠시 뒤 다시 확인해 주세요."}<button type="button" onClick={() => setRevision(n => n + 1)}>다시 불러오기</button></div>}
        {!phases.length ? <div className="asb-status" role="status">{pending ? "하루 기록을 불러오는 중이에요." : "거래일 일정을 확인한 뒤 시간대별 기록을 보여드릴게요."}</div> : <div className="asb-track" data-card-count={phases.length} data-expanded={!!detail}>{phases.map((phase, i) => {
            const snapshot = snapshots.find(s => s.snapshot_id === day?.cards[phase]), items = visibleItems(dayItems(viewDay, phase), holdings, personal)
            const previousPhase = snapshot ? snapshots.filter(s => Date.parse(s.generated_at) < Date.parse(snapshot.generated_at) && phasePosition(s.phase) < phasePosition(snapshot.phase)).slice(-1)[0] : undefined
            const relation = phaseRelation(phase, chosenDate, today, current), future = relation === "future", isActive = phase === active
            const relationLabel = { past: "이전", current: "지금", future: "예정", unknown: "시각 확인 중" }[relation]
            return <React.Fragment key={phase}><article className="asb-card" data-phase={phase} data-active={isActive} data-time-state={relation} data-expanded={isActive && expanded} data-edge={i === 0 ? "first" : i === phases.length - 1 ? "last" : "middle"} style={{ "--asb-position": i + 1 } as CSSProperties}><button className="asb-card-head" type="button" aria-pressed={isActive} aria-current={relation === "current" ? "step" : undefined} onClick={() => { setSelected(phase); setExpanded(true) }}><span className="asb-phase"><span className="asb-session-tag"><span className="asb-session-dot" aria-hidden="true" />{LABEL[phase]}{phase === "closed" && tradingStatus(chosenDate, index?.calendar) === "closed" && <span className="asb-session-sub">· {[0, 6].includes(new Date(chosenDate + "T12:00:00Z").getUTCDay()) ? "주말" : "휴장일"}</span>}</span><span className="asb-time-label">{relationLabel}</span></span><span className="asb-phase-time">{relation === "current" ? <span className="asb-countdown">{sessionTimeLabel(epoch, status, index?.calendar)}</span> : sessionWindow(phase, chosenDate, index?.calendar)}</span><h3>{QUESTION[phase]}</h3></button><div className="asb-card-body">{items.length ? items.slice(0, 2).map(item => <Fact key={item.id} item={item} compact previous={previousPhase?.items.find(v => v.id === item.id)} later={snapshot !== latest ? latestById.get(item.id) : undefined} />) : <p className="asb-empty">{pending ? "기록을 불러오는 중이에요." : future ? "아직 시작 전이에요. 이 시간대에 모인 기록이 여기에 이어져요." : snapshot ? personal ? "이 기록에는 보유종목의 새 소식이 없어요." : "수신된 새 항목이 없어요." : "이 시간대에 저장된 기록이 아직 없어요."}</p>}</div><footer><small>{snapshot ? `기록 ${stamp(snapshot.generated_at)}` : HINT[phase]}</small>{phase === "post" && <small className="asb-change">{summaryClosed ? "하루 종합 저장됨" : "자정까지 모은 뒤 하루 종합"}</small>}<button type="button" disabled={!snapshot && !(phase === "post" && summaryClosed)} onClick={() => { setSelected(phase); setExpanded(v => phase === selected ? !v : true) }} aria-expanded={isActive && expanded}>기록 자세히 <svg className="asb-expand-chevron" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true" focusable="false" style={{ transform: isActive && expanded ? "rotate(180deg)" : undefined }}><path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></button></footer><div className="asb-step" aria-hidden="true"><span>{phase === "closed" ? "휴장" : `0${i + 1}`}</span></div></article>{isActive && detail}</React.Fragment>
        })}</div>}
        <p className="asb-note">{latest ? `최근 기록 ${stamp(latest.generated_at)} · ` : ""}각 자료의 기준일은 다를 수 있어요. 장후에도 새 기록을 모으며, 다음 수집 때 전날의 하루 종합을 저장해요.</p>
    </section>
}
const CSS = `
.asb{${themeVars(LIGHT_TONE)};width:100%;box-sizing:border-box;color:var(--asb-ink);font-family:Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Segoe UI",sans-serif;font-size:13px;font-weight:600;line-height:1.6;container-type:inline-size}
body[data-framer-theme="dark"] .asb,html[data-an-theme="dark"] .asb,.asb[data-theme="dark"]{${themeVars(DARK_TONE)}}
.asb *{box-sizing:border-box}.asb h2,.asb h3,.asb p{margin:0}.asb h2{font-size:20px;font-weight:800;letter-spacing:-.6px;line-height:1.4}.asb h3{font-size:16px;font-weight:800;line-height:1.5}.asb p{overflow-wrap:anywhere}.asb small{display:block;font-size:11px;color:var(--asb-sub);font-weight:600;line-height:1.6}
.asb-heading,.asb-meta,.asb-detail-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.asb-heading p,.asb-note{color:var(--asb-sub);font-size:12px}.asb-eyebrow{color:var(--asb-accent);font-size:12px;font-weight:700;display:block;margin-bottom:4px}.asb-heading p{margin-top:6px}.asb-date{display:grid;gap:2px;font-size:11px;color:var(--asb-sub);text-align:center}.asb-date-select{position:relative;display:block;width:140px;min-width:140px;max-width:100%}.asb-select-chevron{position:absolute;right:13px;top:50%;margin-top:-5px;width:7px;height:7px;border:solid currentColor;border-width:0 1.5px 1.5px 0;transform:rotate(45deg);pointer-events:none}
.asb button,.asb a,.asb select{font:inherit;font-weight:700;color:inherit;background:transparent;border:0;border-radius:10px;min-height:44px;padding:8px 12px;transition:background-color 160ms;cursor:pointer;text-decoration:none;box-shadow:none}.asb select{min-height:36px;font-size:12px;line-height:1.3;background:var(--asb-card);width:100%;max-width:100%;color:var(--asb-ink);appearance:none;-webkit-appearance:none;text-align:center;text-align-last:center;padding:8px 32px 8px 12px}.asb button:disabled{cursor:default;opacity:.55}.asb :is(button,a,select):focus-visible{outline:0;background:var(--asb-focus)}.asb-meta{margin:12px 0 18px;min-height:44px;font-size:11px;color:var(--asb-sub)}.asb-meta button{font-size:12px;color:var(--asb-accent)}
.asb-track{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));column-gap:12px;row-gap:24px;padding:24px 16px 52px;background:var(--asb-back);border-radius:24px}.asb-track[data-card-count="1"]{grid-template-columns:1fr;padding-bottom:24px}.asb-card{--asb-surface:var(--asb-card);position:relative;isolation:isolate;grid-row:1;grid-column:var(--asb-position);display:flex;flex-direction:column;min-width:0;background:var(--asb-card);border-radius:18px;transition:transform 280ms;transform:translateY(0)}.asb-card[data-time-state="current"]{transform:translateY(-6px)}.asb-card[data-time-state="past"]{--asb-surface:color-mix(in srgb,var(--asb-card) 78%,var(--asb-back));color:color-mix(in srgb,var(--asb-ink) 86%,var(--asb-sub))}.asb-card[data-time-state="future"] h3{color:var(--asb-sub)}.asb-track[data-card-count="1"] .asb-card{transform:none}.asb-track[data-card-count="1"] .asb-card-body{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.asb-track[data-card-count="1"] .asb-fact+.asb-fact{margin-top:0}.asb-card-head{text-align:left!important;border-radius:18px 18px 12px 12px!important;padding:20px 20px 10px!important;width:100%;display:block}.asb-card-head:before{content:"";position:absolute;inset:0;border-radius:18px;background:var(--asb-surface);z-index:-1;pointer-events:none;transition:background-color 160ms}.asb-card-head:after{content:"";position:absolute;inset:0;border-radius:18px}.asb-phase{display:flex;align-items:center;gap:8px;margin-bottom:12px;font-size:13px;font-weight:700;color:var(--asb-sub)}.asb-card[data-phase="pre"]{--asb-session:var(--asb-pre)}.asb-card[data-phase="open"]{--asb-session:var(--asb-open)}.asb-card[data-phase="post"]{--asb-session:var(--asb-post)}.asb-card[data-phase="closed"]{--asb-session:var(--asb-closed)}.asb-session-tag{display:inline-flex;align-items:center;gap:6px;padding:0;background:transparent;font-size:12px;font-weight:800;letter-spacing:-.2px;line-height:1.6}.asb-session-sub{font-size:11px;font-weight:600;color:var(--asb-sub);white-space:nowrap}.asb-session-dot{width:7px;height:7px;border-radius:50%;flex:none;background:var(--asb-sub)}.asb-card[data-time-state="current"] .asb-session-tag{color:var(--asb-ink)}.asb-card[data-time-state="current"] .asb-session-dot{background:var(--asb-session)}.asb-card:is([data-time-state="future"],[data-time-state="unknown"]) .asb-session-dot{background:transparent;border:1px solid var(--asb-sub)}.asb-time-label{font-size:11px;border-radius:8px;padding:3px 8px;margin-left:auto;font-weight:700}.asb-card[data-time-state="current"] .asb-time-label{background:var(--asb-accent);color:var(--asb-card)}.asb-card-body{padding:4px 20px 12px;flex:1}.asb-fact{padding:12px 0}.asb-fact+.asb-fact{margin-top:4px}.asb-identity{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:700;color:var(--asb-sub);margin-bottom:6px}.asb-logo{width:24px;height:24px;flex:none;border-radius:8px;background:var(--asb-back);display:grid;place-items:center;overflow:hidden}.asb-logo img{width:100%;height:100%;object-fit:contain}.asb-fact p{font-size:13px;line-height:1.65}.asb-fact small{margin-top:6px}.asb-clamp{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.asb del{color:var(--asb-sub);text-decoration-thickness:1px}.asb ins{text-decoration:none;color:var(--asb-accent);font-weight:800}.asb-change{color:var(--asb-accent)!important;font-size:11px;display:block;margin-top:6px}.asb-empty{color:var(--asb-sub);padding:12px 0;min-height:80px}.asb-card footer{padding:0 20px 14px}.asb-card footer button{position:relative;z-index:1;width:100%;display:flex;justify-content:center;align-items:center;gap:8px;margin-top:8px;background:var(--asb-back);font-size:12px}.asb-step{position:absolute;top:calc(100% + 17px);left:0;width:100%;display:flex;justify-content:center;transform:translateY(0);transition:transform 280ms}.asb-card[data-time-state="current"] .asb-step{transform:translateY(6px)}.asb-step:before{content:"";position:absolute;top:50%;transform:translateY(-50%);width:calc(100% + 12px);height:1px;background:var(--asb-focus)}.asb-step span{z-index:1;background:var(--asb-card);border-radius:11px;padding:4px 14px;font-size:11px;color:var(--asb-sub)}.asb-card[data-time-state="current"] .asb-step span{background:var(--asb-accent);color:var(--asb-card)}.asb-track[data-card-count="1"] .asb-step{display:none}.asb-detail{grid-row:2;grid-column:1 / -1;min-width:0;border-radius:20px;background:var(--asb-card);padding:20px 24px;animation:asb-appear 280ms ease}.asb-track[data-expanded="true"]{padding-bottom:16px}.asb-track[data-expanded="true"] .asb-card{transform:none}.asb-track[data-expanded="true"] .asb-step{display:none}.asb-card[data-expanded="true"]{border-radius:18px 18px 0 0;--asb-surface:var(--asb-card)}.asb-card[data-expanded="true"]:after{content:"";position:absolute;top:100%;left:0;right:0;height:24px;background:var(--asb-card);pointer-events:none}.asb-card[data-expanded="true"]:before{content:"";position:absolute;top:100%;left:-24px;right:-24px;height:24px;background-image:radial-gradient(circle at top left,transparent 23.5px,var(--asb-card) 24px),radial-gradient(circle at top right,transparent 23.5px,var(--asb-card) 24px);background-position:left bottom,right bottom;background-size:24px 24px;background-repeat:no-repeat;pointer-events:none}.asb-card[data-expanded="true"][data-edge="first"]:before{background-image:none,radial-gradient(circle at top right,transparent 23.5px,var(--asb-card) 24px)}.asb-card[data-expanded="true"][data-edge="last"]:before{background-image:radial-gradient(circle at top left,transparent 23.5px,var(--asb-card) 24px),none}.asb-track[data-card-count="1"] .asb-card:before{display:none}.asb-detail[data-edge="first"]{border-top-left-radius:0}.asb-detail[data-edge="last"]{border-top-right-radius:0}.asb-track[data-card-count="1"] .asb-detail{border-top-left-radius:0;border-top-right-radius:0}.asb-card footer button[aria-expanded="true"]{background:var(--asb-focus)}.asb-clock,.asb-countdown{font-variant-numeric:tabular-nums}.asb-phase-time{display:block;min-height:18px;margin:0 0 10px;font-size:11px;font-weight:600;color:var(--asb-sub)}.asb-countdown{color:var(--asb-ink);font-weight:700}.asb-detail .asb-fact{padding:16px;border-radius:14px;background:var(--asb-back);margin-top:12px}.asb-detail .asb-fact a{display:inline-flex;align-items:center;margin-top:6px;color:var(--asb-accent)}.asb-note{margin-top:12px!important;font-size:11px;line-height:1.7}.asb-summary,.asb-status{color:var(--asb-sub);background:var(--asb-back);border-radius:16px;padding:16px;margin:12px 0!important}.asb-status button{margin-left:6px}.asb-summary{font-size:12px}
@media(hover:hover){.asb :is(button,a,select):not(:disabled):not(.asb-card-head):hover{background:var(--asb-hover)}.asb-card:has(.asb-card-head:hover){--asb-surface:var(--asb-hover)}}
.asb .asb-card-head:focus-visible{background:transparent}.asb-card:has(.asb-card-head:focus-visible){--asb-surface:var(--asb-focus)}
@container(max-width:680px){.asb-card[data-expanded="true"]:before{display:none}.asb-track[data-card-count="1"] .asb-card-body{grid-template-columns:1fr;gap:0}.asb-heading{align-items:flex-start;flex-direction:column;gap:12px}.asb-date{width:auto;grid-template-columns:auto auto;align-items:center;gap:8px}.asb select{min-height:44px}.asb-track{grid-template-columns:1fr;padding:16px;row-gap:24px}.asb-card,.asb-detail{grid-column:1;grid-row:auto}.asb-detail{border-top-left-radius:0;border-top-right-radius:0}.asb-card[data-time-state="current"]{transform:none}.asb-step{display:none}.asb-card-head{padding:16px 16px 6px!important}.asb-card-body{padding:4px 16px 8px}.asb-card footer{padding:0 16px 14px}.asb-phase{margin-bottom:6px}.asb-detail{padding:16px}.asb-meta{gap:8px;flex-wrap:wrap}.asb h2{font-size:20px}}
@keyframes asb-appear{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}@media(prefers-reduced-motion:reduce){.asb *{transition:none!important;animation:none!important}}
`
addPropertyControls(PublicSessionBriefing, {
    dark: { type: ControlType.Boolean, title: "다크 모드", defaultValue: false },
    archiveBaseUrl: { type: ControlType.String, title: "기록 주소", defaultValue: BASE },
    holdingsTickers: { type: ControlType.Array, title: "보유 코드", control: { type: ControlType.String }, defaultValue: [] },
    personalizationState: { type: ControlType.Enum, title: "정보 기준", options: ["loading", "market", "holdings", "error"], defaultValue: "market" },
})

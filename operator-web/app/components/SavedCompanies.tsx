"use client"

import { useEffect, useRef, useState } from "react"
import { API_BASE } from "@/lib/api"
import { authHeaders, refreshAuth } from "@/lib/auth"
import { CARD_TITLE, FONT, RAIL_PAD, cardStyle, palette, useDark } from "@/lib/theme"
import { selectTicker } from "@/lib/types"

type Item = { id: string; group_id: string; ticker: string; name: string; market: string }
type Group = { id: string; user_id: string; name: string; items: Item[] }
type Snapshot = { owner: string; groups: Group[] }
type Action = { action: "create_group"; name: string } | { action: "add_item"; group_id: string; ticker: string; name: string; market: string } | { action: "remove_item"; item_id: string }
type FailureKind = "auth" | "session" | "timeout" | "cancel" | "rejected" | "transport" | "invalid"
class RequestFailure extends Error {
    constructor(readonly kind: FailureKind, readonly sent = false) { super(kind) }
}

// This identity only guards stale responses. The API, not this decoded payload, verifies JWT ownership.
function identity(): { owner: string; headers: Record<string, string> } {
    const headers = authHeaders()
    try {
        const token = headers.Authorization?.replace(/^Bearer /, "")
        const payload = token?.split(".")[1]?.replace(/-/g, "+").replace(/_/g, "/")
        const owner: unknown = payload ? JSON.parse(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, "="))).sub : null
        if (typeof owner === "string" && owner) return { owner, headers }
    } catch { /* Missing or changed session must fail closed. */ }
    throw new RequestFailure("auth")
}
function sameOwner(owner: string) {
    if (identity().owner !== owner) throw new RequestFailure("session")
}
function groupsFrom(value: unknown, owner: string): Group[] {
    if (!Array.isArray(value)) throw new RequestFailure("invalid")
    const ids = new Set<string>(), itemIds = new Set<string>()
    return value.map(group => {
        if (!group || typeof group.id !== "string" || !group.id || group.user_id !== owner || typeof group.name !== "string" || !Array.isArray(group.items) || ids.has(group.id)) throw new RequestFailure("invalid")
        ids.add(group.id)
        const items = group.items.map((item: Item) => {
            if (!item || typeof item.id !== "string" || !item.id || item.group_id !== group.id || typeof item.ticker !== "string" || !item.ticker.trim() || itemIds.has(item.id)) throw new RequestFailure("invalid")
            itemIds.add(item.id)
            return { id: item.id, group_id: item.group_id, ticker: item.ticker, name: typeof item.name === "string" ? item.name : "", market: typeof item.market === "string" ? item.market : "" }
        })
        return { id: group.id, user_id: group.user_id, name: group.name, items }
    })
}
async function request(method: "GET" | "POST" | "DELETE", signal: AbortSignal, payload?: Action, expectedOwner?: string): Promise<{ owner: string; body: unknown }> {
    const controller = new AbortController()
    let sent = false, timedOut = false
    const onAbort = () => controller.abort()
    const cancelled = new Promise<never>((_, reject) => controller.signal.addEventListener("abort", () => reject(new RequestFailure(timedOut ? "timeout" : "cancel", sent)), { once: true }))
    const timer = setTimeout(() => { timedOut = true; controller.abort() }, 30000)
    signal.addEventListener("abort", onAbort, { once: true })
    if (signal.aborted) onAbort()
    const work = async () => {
        controller.signal.throwIfAborted()
        await refreshAuth()
        controller.signal.throwIfAborted()
        const { owner, headers } = identity()
        if (expectedOwner && expectedOwner !== owner) throw new RequestFailure("session")
        sent = true
        const response = await fetch(`${API_BASE}/api/watchgroups`, {
            method, headers: { ...headers, ...(payload ? { "Content-Type": "application/json" } : {}) },
            ...(payload ? { body: JSON.stringify(payload) } : {}), signal: controller.signal,
            cache: "no-store", credentials: "omit", redirect: "error",
        })
        controller.signal.throwIfAborted()
        sameOwner(owner)
        if (response.status === 401 || response.status === 403) throw new RequestFailure("auth", sent)
        if (!response.ok) throw new RequestFailure(response.status < 500 ? "rejected" : "transport", sent)
        const body: unknown = await response.json()
        controller.signal.throwIfAborted()
        sameOwner(owner)
        return { owner, body }
    }
    try { return await Promise.race([work(), cancelled]) }
    catch (error) {
        if (error instanceof RequestFailure) throw error
        throw new RequestFailure("transport", sent)
    } finally {
        clearTimeout(timer); signal.removeEventListener("abort", onAbort); controller.abort()
    }
}

export default function SavedCompanies() {
    const c = palette(useDark())
    const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
    const [phase, setPhase] = useState<"loading" | "ready" | "auth" | "error">("loading")
    const [selected, setSelected] = useState("")
    const [groupName, setGroupName] = useState("")
    const [ticker, setTicker] = useState("")
    const [companyName, setCompanyName] = useState("")
    const [market, setMarket] = useState("us")
    const [confirm, setConfirm] = useState<string | null>(null)
    const [busy, setBusy] = useState(false)
    const [unresolved, setUnresolved] = useState(false)
    const [notice, setNotice] = useState("")
    const flight = useRef<{ id: number; controller: AbortController } | null>(null)
    const generation = useRef(0)
    const mounted = useRef(false)
    const lock = useRef(false)
    const uncertain = useRef(false)

    function start() {
        if (!mounted.current || lock.current) return null
        lock.current = true; setBusy(true)
        const op = { id: ++generation.current, controller: new AbortController() }
        flight.current = op
        return op
    }
    function current(op: NonNullable<typeof flight.current>) { return mounted.current && generation.current === op.id && !op.controller.signal.aborted }
    function finish(op: NonNullable<typeof flight.current>) {
        if (current(op)) { lock.current = false; flight.current = null; setBusy(false) }
    }
    function needsReadback(value: boolean) { uncertain.current = value; setUnresolved(value) }
    function publish(owner: string, groups: Group[], preferred?: string) {
        sameOwner(owner)
        setSnapshot({ owner, groups }); setPhase("ready"); setConfirm(null)
        setSelected(previous => groups.some(g => g.id === (preferred || previous)) ? (preferred || previous) : (groups[0]?.id || ""))
    }
    function readError(error: unknown) {
        const auth = error instanceof RequestFailure && ["auth", "session"].includes(error.kind)
        if (auth) { setSnapshot(null); setPhase("auth"); setConfirm(null) }
        else setPhase("error")
        return auth ? "로그인 상태가 바뀌었거나 권한을 확인할 수 없습니다. 다시 로그인한 뒤 목록을 확인해 주세요." : "관심 그룹을 읽지 못했습니다. 표시된 목록이 있으면 이전 수신본입니다."
    }
    async function reload() {
        const op = start()
        if (!op) return
        setPhase("loading")
        try {
            const result = await request("GET", op.controller.signal)
            const groups = groupsFrom(result.body, result.owner)
            if (!current(op)) return
            publish(result.owner, groups)
            setNotice(uncertain.current ? "최신 목록을 다시 읽었습니다. 방금 요청한 변경이 반영되었는지 확인해 주세요." : "")
            needsReadback(false)
        } catch (error) { if (current(op)) setNotice(readError(error)) }
        finally { finish(op) }
    }
    useEffect(() => {
        mounted.current = true
        void reload()
        const changed = (event: StorageEvent) => {
            if (event.key !== null && event.key !== "verity_supabase_session") return
            generation.current++; flight.current?.controller.abort(); flight.current = null; lock.current = false
            setBusy(false); setSnapshot(null); setConfirm(null); setPhase("auth")
            setNotice("로그인 상태가 변경되었습니다. 목록을 새로고침해 주세요.")
        }
        window.addEventListener("storage", changed)
        return () => { mounted.current = false; generation.current++; flight.current?.controller.abort(); flight.current = null; lock.current = false; window.removeEventListener("storage", changed) }
        // Mount reads only. All writes below require an explicit submit/confirmation.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    async function mutate(action: Action) {
        if (!snapshot || phase !== "ready" || uncertain.current) return
        const op = start()
        if (!op) return
        let acknowledged = false
        try {
            const result = await request(action.action === "remove_item" ? "DELETE" : "POST", op.controller.signal, action, snapshot.owner)
            const row = result.body as Record<string, unknown> | null
            if (!row || Array.isArray(row) || (action.action === "remove_item" ? row.ok !== true : typeof row.id !== "string" || !row.id)) throw new RequestFailure("invalid", true)
            if (action.action === "create_group" && (row.user_id !== result.owner || row.name !== action.name)) throw new RequestFailure("invalid", true)
            if (action.action === "add_item" && (row.group_id !== action.group_id || row.ticker !== action.ticker)) throw new RequestFailure("invalid", true)
            acknowledged = true
            if (!current(op)) return
            if (action.action === "create_group") setGroupName("")
            if (action.action === "add_item") { setTicker(""); setCompanyName("") }
            setConfirm(null); setNotice("변경 응답을 받았습니다. 최신 목록 확인 중…")
            const readback = await request("GET", op.controller.signal, undefined, result.owner)
            const groups = groupsFrom(readback.body, readback.owner)
            const reflected = action.action === "create_group" ? groups.some(g => g.id === row.id) : action.action === "add_item" ? groups.some(g => g.id === action.group_id && g.items.some(i => i.id === row.id && i.ticker === action.ticker)) : !groups.some(g => g.items.some(i => i.id === action.item_id))
            if (!reflected) throw new RequestFailure("invalid")
            if (!current(op)) return
            publish(readback.owner, groups, action.action === "create_group" ? row.id as string : undefined)
            needsReadback(false); setNotice("변경을 저장하고 최신 목록에서 확인했습니다.")
        } catch (error) {
            if (!current(op)) return
            const failure = error instanceof RequestFailure ? error : new RequestFailure("transport", true)
            if (["auth", "session"].includes(failure.kind)) {
                setNotice(acknowledged ? "변경 응답은 받았지만 로그인 상태가 바뀌어 목록을 확인하지 못했습니다." : readError(failure))
                setSnapshot(null); setPhase("auth"); setConfirm(null)
            } else if (acknowledged || (failure.sent && failure.kind !== "rejected")) {
                setNotice(acknowledged ? "변경 응답은 받았지만 최신 목록 확인에 실패했습니다. 다시 저장하지 말고 목록을 새로고침해 주세요." : "요청 결과를 확인하지 못했습니다. 변경이 반영되었을 수 있으니 다시 저장하지 말고 목록을 새로고침해 주세요.")
                needsReadback(true)
            } else setNotice(failure.kind === "timeout" ? "로그인 확인 시간이 초과되어 저장 요청을 보내지 않았습니다." : "요청이 거절되어 변경하지 못했습니다. 입력과 권한을 확인해 주세요.")
        } finally { finish(op) }
    }
    const group = snapshot?.groups.find(g => g.id === selected)
    const disabled = busy || unresolved || phase !== "ready"
    const button = { fontFamily: FONT, fontSize: 12, fontWeight: 700, color: c.ink, background: c.hi, border: `1px solid ${c.line}`, borderRadius: 8, padding: "8px 10px", cursor: "pointer" }
    const input = { ...button, background: c.card, minWidth: 0, width: "100%", boxSizing: "border-box" as const }
    return <section data-saved-companies="v1" style={{ ...cardStyle(c, RAIL_PAD), color: c.ink, fontFamily: FONT }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <h3 style={{ ...CARD_TITLE, margin: 0 }}>관심 기업</h3>
            <button type="button" style={button} disabled={busy} onClick={() => void reload()}>목록 새로고침</button>
        </div>
        <p style={{ color: c.sub, fontSize: 11, margin: "6px 0 12px" }}>AlphaNest 계정과 공유하는 관심 그룹 · 기업을 선택하면 분석으로 이동합니다.</p>
        {(notice || phase === "loading") && <p role="status" aria-live="polite" style={{ fontSize: 12, color: unresolved || phase === "auth" || phase === "error" ? c.amber : c.sub, lineHeight: 1.6 }}>{busy && phase === "loading" ? "관심 그룹 확인 중…" : notice}</p>}
        {snapshot && <label style={{ display: "block", fontSize: 11, color: c.sub }}>관심 그룹
            <select aria-label="관심 그룹" value={selected} disabled={busy} style={{ ...input, marginTop: 5 }} onChange={event => { setSelected(event.target.value); setConfirm(null) }}>
                {snapshot.groups.length === 0 ? <option value="">아직 그룹 없음</option> : snapshot.groups.map(g => <option key={g.id} value={g.id}>{g.name} · {g.items.length}개</option>)}
            </select>
        </label>}
        {group && <ul style={{ listStyle: "none", margin: "10px 0", padding: 0 }}>
            {group.items.map(item => <li key={item.id} style={{ padding: "9px 0", borderBottom: `1px solid ${c.line}` }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                    <button type="button" style={{ ...button, textAlign: "left", background: "transparent", border: "none", padding: "4px 0", overflowWrap: "anywhere" }} aria-label={`${item.name || item.ticker} 분석 보기`} onClick={() => {
                        try { sameOwner(snapshot!.owner) } catch (error) { setNotice(readError(error)); return }
                        selectTicker(item.ticker, item.name)
                        document.getElementById("console-analysis")?.scrollIntoView({ block: "start", behavior: "instant" })
                    }}>{item.name || item.ticker}<span style={{ color: c.faint, fontSize: 10, marginLeft: 6 }}>{item.ticker}</span></button>
                    <button type="button" disabled={disabled} style={button} aria-label={`${item.name || item.ticker} 그룹에서 제외`} onClick={() => setConfirm(item.id)}>제외</button>
                </div>
                {confirm === item.id && <div style={{ fontSize: 12, paddingTop: 7 }}><span>이 그룹에서 제외할까요? </span><button type="button" disabled={disabled} style={button} onClick={() => void mutate({ action: "remove_item", item_id: item.id })}>제외 확인</button> <button type="button" disabled={busy} style={button} onClick={() => setConfirm(null)}>취소</button></div>}
            </li>)}
            {group.items.length === 0 && <li style={{ color: c.faint, fontSize: 12, padding: "8px 0" }}>이 그룹에 저장된 기업이 없습니다.</li>}
        </ul>}
        <form onSubmit={event => {
            event.preventDefault()
            const value = ticker.trim().toUpperCase()
            if (!group || !value || disabled) return
            if (!(market === "kr" ? /^\d{6}$/.test(value) : /^[A-Z][A-Z0-9.^-]{0,19}$/.test(value))) {
                setNotice(market === "kr" ? "한국 종목코드는 숫자 6자리로 입력해 주세요." : "미국 티커는 영문으로 시작하는 20자 이내의 종목코드로 입력해 주세요.")
                return
            }
            if (group.items.some(i => i.ticker.trim().toUpperCase() === value)) { setNotice("이 그룹에 이미 저장된 종목입니다."); return }
            void mutate({ action: "add_item", group_id: group.id, ticker: value, name: companyName.trim(), market })
        }} style={{ display: "flex", flexWrap: "wrap", alignItems: "end", gap: 7, marginTop: 12 }}>
            <label style={{ flex: "1 1 90px", fontSize: 11, color: c.sub }}>티커 / 종목코드<input aria-label="저장할 티커 또는 종목코드" value={ticker} disabled={disabled || !group} maxLength={32} required autoComplete="off" placeholder="MSFT / 005930" style={{ ...input, marginTop: 5 }} onChange={event => setTicker(event.target.value)} /></label>
            <label style={{ flex: "1 1 110px", fontSize: 11, color: c.sub }}>기업명 (선택)<input aria-label="저장할 기업명" value={companyName} disabled={disabled || !group} maxLength={100} autoComplete="off" style={{ ...input, marginTop: 5 }} onChange={event => setCompanyName(event.target.value)} /></label>
            <label style={{ flex: "0 0 64px", fontSize: 11, color: c.sub }}>시장<select aria-label="저장할 종목 시장" value={market} disabled={disabled || !group} style={{ ...input, marginTop: 5 }} onChange={event => setMarket(event.target.value)}><option value="us">미국</option><option value="kr">한국</option></select></label>
            <button type="submit" disabled={disabled || !group || !ticker.trim()} style={button}>기업 추가</button>
        </form>
        <details style={{ color: c.sub, fontSize: 12, marginTop: 14 }}><summary style={{ cursor: "pointer", fontWeight: 700 }}>이름을 정해 새 그룹 만들기</summary>
            <form style={{ display: "flex", gap: 7, marginTop: 8 }} onSubmit={event => {
                event.preventDefault()
                const name = groupName.trim()
                if (!name || disabled) return
                if (snapshot?.groups.some(g => g.name.trim() === name)) { setNotice("같은 이름의 그룹이 있습니다. 해당 그룹을 선택해 주세요."); return }
                void mutate({ action: "create_group", name })
            }}><input aria-label="새 관심 그룹 이름" value={groupName} disabled={disabled} required maxLength={80} autoComplete="off" placeholder="예: 장기 검토" style={input} onChange={event => setGroupName(event.target.value)} /><button type="submit" disabled={disabled || !groupName.trim()} style={{ ...button, flexShrink: 0 }}>그룹 만들기</button></form>
        </details>
    </section>
}

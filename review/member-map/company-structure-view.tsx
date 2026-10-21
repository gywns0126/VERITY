import * as React from "react"

type Company = { id: string; name: string; ticker?: string; market?: string; country?: string }
type Evidence = { title: string; url: string; asOf?: string | null }
type Relation = { id: string; from: string; to: string; type: string; label: string; asOf: string | null; observedAt?: string; status: string; ownershipPct: number | null; evidence: Evidence[] }
type Catalogue = { schema: string; companies: Company[]; relations: Relation[]; coverage?: Record<string, unknown> }
type Stock = Company & { logo?: string }
type Snapshot = { stocks: Stock[]; flags: Record<string, string> }
type TreeNode = { company: Company; relation?: Relation; parent?: string; children: string[]; x: number; y: number; depth: number }
type Layout = { byId: Map<string, TreeNode>; roots: string[]; omitted: number; total: number }

const CSS = `
.acs-view{--acs-card:#fff;--acs-bg:#f8f9fb;--acs-text:#191f28;--acs-sub:#6b7684;--acs-hover:#f1f3f5;--acs-focus:#e9edf2;--acs-accent:#6c5ce7;--acs-line:#c8cdd4;--acs-selected:#f0edff;position:fixed;inset:0;z-index:10000;display:flex;flex-direction:column;background:var(--acs-bg);color:var(--acs-text);font:600 13px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif}
html[data-an-theme=dark] .acs-view,body[data-framer-theme=dark] .acs-view{--acs-card:#171c23;--acs-bg:#1d242c;--acs-text:#e3e7ec;--acs-sub:#9aa4b1;--acs-hover:#252c35;--acs-focus:#303945;--acs-accent:#a99bff;--acs-line:#4c5662;--acs-selected:#302948}
.acs-view *{box-sizing:border-box}.acs-view button,.acs-view select{font:700 13px/1.5 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;color:inherit;border:0;background:var(--acs-card);border-radius:10px;min-height:36px;padding:7px 11px;cursor:pointer;transition:background-color 160ms}.acs-view button:focus-visible,.acs-view select:focus-visible,.acs-view a:focus-visible{outline:0;background:var(--acs-focus)}.acs-view button:disabled{opacity:.45;cursor:default}.acs-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:14px 22px;background:var(--acs-card)}.acs-brand{font-size:15px;font-weight:800;letter-spacing:-.5px}.acs-brand i{font-style:normal;color:var(--acs-accent)}.acs-tabs{display:flex;gap:4px;background:var(--acs-bg);padding:3px;border-radius:12px}.acs-tabs button{background:transparent}.acs-tabs button[aria-current=page]{background:var(--acs-card);box-shadow:0 2px 6px #191f2808}.acs-head label{display:flex;gap:8px;align-items:center;margin-left:auto;color:var(--acs-sub);font-size:12px}.acs-head select{background:var(--acs-bg);max-width:220px}.acs-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:10px 22px}.acs-toolbar>span{color:var(--acs-sub);font-size:12px;margin-right:auto}.acs-toolbar output{min-width:40px;text-align:center;font-size:12px}.acs-main{flex:1;min-height:0;display:flex;position:relative}.acs-space{position:relative;flex:1;min-width:0;overflow:hidden;touch-action:none;cursor:grab}.acs-space:active{cursor:grabbing}.acs-space:focus-visible{outline:0;background-color:var(--acs-focus)}.acs-world{position:absolute;left:0;top:0;transform-origin:0 0}.acs-lines{position:absolute;inset:0;overflow:visible;pointer-events:none}.acs-lines path{fill:none;stroke:var(--acs-line);stroke-width:1.5;stroke-linejoin:round}.acs-lines path[data-undated=true]{stroke-dasharray:4 4}.acs-card{position:absolute;width:224px;min-height:86px;border-radius:15px;background:var(--acs-card);box-shadow:0 5px 14px #191f280b;display:flex;gap:12px;padding:15px 16px;text-align:left;align-items:center}.acs-card:before{content:'';position:absolute;top:0;left:15px;right:15px;height:3px;background:var(--acs-line);border-radius:2px}.acs-card[data-focus=true]:before{background:var(--acs-accent)}.acs-card[data-focus=true]{background:var(--acs-selected)}.acs-card[data-dated=true]:not([data-focus=true]):before{background:#8dbda9}.acs-face{position:relative;flex:0 0 36px;width:36px;height:36px;display:grid;place-items:center;border-radius:11px;background:var(--acs-bg);font-weight:800;color:var(--acs-sub)}.acs-logo{width:100%;height:100%;object-fit:contain;border-radius:10px;display:block}.acs-flag{position:absolute;right:-4px;bottom:-4px;display:block;width:15px;height:15px;border-radius:50%;box-shadow:0 0 0 2px var(--acs-card)}.acs-copy{flex:1;min-width:0}.acs-name{display:block;font-size:14px;font-weight:800;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.acs-role{display:block;font-size:11px;color:var(--acs-sub);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.acs-card-main{border:0;background:transparent!important;min-height:0!important;padding:0!important;text-align:left;width:100%;border-radius:4px!important}.acs-card-main:focus-visible{background:var(--acs-focus)!important}.acs-card .acs-branch{position:absolute;left:calc(50% - 12px);bottom:-12px;width:24px;height:24px;min-height:24px;padding:0;border-radius:50%;background:var(--acs-card);box-shadow:0 2px 7px #191f2812;display:grid;place-items:center;font-size:16px;line-height:1}.acs-child-count{position:absolute;top:100%;left:calc(50% + 18px);font-size:10px;white-space:nowrap;color:var(--acs-sub);pointer-events:none}.acs-inspector{width:286px;max-width:40%;padding:20px;background:var(--acs-card);overflow:auto;scrollbar-gutter:stable}.acs-inspector h2{font-size:16px;font-weight:800;margin:0 0 8px}.acs-inspector p{font-size:12px;white-space:pre-line;margin:10px 0;color:var(--acs-sub)}.acs-inspector strong{color:var(--acs-text);font-weight:700}.acs-inspector a{display:block;padding:10px 12px;margin-top:8px;border-radius:12px;background:var(--acs-bg);color:var(--acs-text);text-decoration:none;overflow-wrap:anywhere;font-size:12px}.acs-inspector .acs-inspector-close{float:right}.acs-empty{align-self:center;max-width:460px;padding:24px;margin:auto;color:var(--acs-sub)}.acs-empty strong{display:block;color:var(--acs-text);font-size:16px;margin-bottom:8px}.acs-foot{display:flex;gap:16px;flex-wrap:wrap;padding:10px 22px;color:var(--acs-sub);font-size:11px;background:var(--acs-card)}.acs-key{display:flex;gap:7px;align-items:center}.acs-key i{width:20px;border-top:2px solid var(--acs-line)}.acs-key[data-kind=undated] i{border-top-style:dashed}.acs-status{margin-left:auto}.acs-close{background:var(--acs-bg)!important}.review-structure-toggle{margin-left:auto;margin-right:10px}.review-structure-toggle[aria-pressed=true]{background:#e9edf2}
@media(hover:hover){.acs-view button:not(.acs-card-main):not(:disabled):hover,.acs-view a:hover{background:var(--acs-hover)}}
@media(max-width:700px){.acs-head{padding:10px 12px;gap:8px}.acs-brand{display:none}.acs-head label{margin-left:auto}.acs-head select{max-width:145px}.acs-toolbar{padding:8px 12px;gap:6px}.acs-toolbar>span{flex-basis:100%}.acs-inspector{position:absolute;bottom:0;left:0;right:0;width:auto;max-width:none;max-height:40%;box-shadow:0 -4px 16px #191f280b;padding:14px 16px}.acs-foot{padding:8px 12px;gap:6px 14px}.acs-status{margin-left:0;flex-basis:100%}}
@media(pointer:coarse){.acs-view button,.acs-view select{min-height:44px}.acs-card .acs-branch:after{content:'';position:absolute;inset:-10px}}
@media(prefers-reduced-motion:reduce){.acs-view button,.acs-view select{transition:none}}
.acs-space{background-image:linear-gradient(var(--acs-focus) 1px,transparent 1px),linear-gradient(90deg,var(--acs-focus) 1px,transparent 1px)}
`

export function makeStructureLayout(catalogue: Catalogue, focus: Company): Layout {
    const companies = new Map(catalogue.companies.map(c => [c.id, c]))
    companies.set(focus.id, { ...companies.get(focus.id), ...focus })
    const byId = new Map<string, TreeNode>(), used = new Set<string>()
    const all = catalogue.relations.filter(r => companies.has(r.from) && companies.has(r.to) && r.from !== r.to)
    const incoming = all.filter(r => r.to === focus.id && (r.type === "major-shareholder" || r.type === "subsidiary")).slice(0, 3)
    const parent = incoming[0]
    const rootId = parent?.from || focus.id
    let omitted = 0
    function walk(id: string, depth: number, relation?: Relation, parentId?: string): string | null {
        if (used.has(id) || used.size >= 160) { omitted++; return null }
        used.add(id)
        const node: TreeNode = { company: companies.get(id)!, relation, parent: parentId, children: [], x: 0, y: depth * 154, depth }
        byId.set(id, node)
        const children = id === rootId && rootId !== focus.id ? all.filter(r => r.from === id && r.to === focus.id) : all.filter(r => r.from === id)
        if (depth < 3) for (const child of children.slice(0, 6)) { const next = walk(child.to, depth + 1, child, id); if (next) node.children.push(next) }
        omitted += Math.max(0, children.length - (depth < 3 ? 6 : 0))
        return id
    }
    walk(rootId, 0)
    let leaf = 0
    function place(id: string) {
        const n = byId.get(id)!
        if (!n.children.length) n.x = leaf++ * 258
        else { n.children.forEach(place); n.x = (byId.get(n.children[0])!.x + byId.get(n.children[n.children.length - 1])!.x) / 2 }
    }
    place(rootId)
    return { byId, roots: [rootId], omitted, total: all.filter(r => used.has(r.from) || used.has(r.to)).length }
}

const safeEvidence = (value: unknown): value is Evidence => {
    if (!value || typeof value !== "object") return false
    const e = value as Evidence
    if (typeof e.title !== "string" || typeof e.url !== "string" || e.url.length > 2048 || /[\u0000-\u001f\u007f]/.test(e.url)) return false
    try { const u = new URL(e.url); return u.protocol === "https:" && !u.username && !u.password } catch { return false }
}
const officialRelation = (r: Relation) => r.evidence.length > 0 && (r.status === "source-dated" || r.status === "official-undated")
const relationDate = (r: Relation) => r.asOf ? `자료 기준 ${r.asOf}` : r.status === "official-undated" ? "공식 안내 · 원문 기준일 미표시" : "원문 기준일이 확인되지 않은 저장 자료입니다."

function RelationshipProof({ relation: r }: { relation: Relation }) {
    return <><p><strong>{r.label}</strong>{r.status === "source-dated" && r.ownershipPct !== null ? ` · ${r.ownershipPct}%` : ""}{"\n" + relationDate(r)}{r.observedAt ? `\n자료 수집 ${r.observedAt.slice(0, 10)}` : ""}</p><p>{r.type === "investment" ? "타법인 출자 내역입니다. 자회사 여부와 현재 지배 관계는 이 항목만으로 확정하지 않습니다." : "관계 유형과 원문 기준일을 함께 확인해 주세요."}</p>{r.evidence.length ? r.evidence.map((e, i) => <a key={i} href={e.url} target="_blank" rel="noopener noreferrer">{e.title} ↗</a>) : <p>이 저장 항목에는 검증 가능한 원문 주소가 제공되지 않았어요.</p>}</>
}
export function validateStructure(value: unknown): Catalogue {
    const c = value as Catalogue
    if (!c || c.schema !== "alphanest-company-structure-v1" || !Array.isArray(c.companies) || !Array.isArray(c.relations) || c.companies.length > 3000 || c.relations.length > 3000) throw Error("catalogue")
    const ids = new Set<string>()
    for (const n of c.companies) {
        if (!n || typeof n.id !== "string" || !n.id || n.id.length > 180 || typeof n.name !== "string" || !n.name || n.name.length > 300 || ids.has(n.id)) throw Error("company")
        ids.add(n.id)
    }
    for (const r of c.relations) if (!r || !ids.has(r.from) || !ids.has(r.to) || !["major-shareholder", "investment", "subsidiary"].includes(r.type) || typeof r.label !== "string" || !Array.isArray(r.evidence) || r.evidence.length > 10 || !r.evidence.every(safeEvidence) || (r.asOf !== null && !/^\d{4}-\d{2}-\d{2}$/.test(r.asOf))) throw Error("relation")
    return c
}

const LOGO_MANIFEST = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
const PNG_PREFIX = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
const imageData = (v: unknown) => typeof v === "string" && v.length <= 180000 && /^data:image\/(png|svg\+xml|webp|jpeg);base64,[A-Za-z0-9+/=]+$/.test(v) ? v : undefined
async function boundedBytes(response: Response, max: number) {
    if (!response.ok || !response.body) throw Error("response")
    const reader = response.body.getReader(), parts: Uint8Array[] = []; let size = 0
    try { while (true) { const { done, value } = await reader.read(); if (done) break; size += value.byteLength; if (size > max) throw Error("size"); parts.push(value) } }
    finally { await reader.cancel().catch(() => {}) }
    const all = new Uint8Array(size); let cursor = 0; for (const part of parts) { all.set(part, cursor); cursor += part.length } return all
}
async function loadLogos(companies: Company[], signal: AbortSignal): Promise<Record<string, string>> {
    const manifestResponse = await fetch(LOGO_MANIFEST, { credentials: "omit", referrerPolicy: "no-referrer", redirect: "error", signal })
    const manifest = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(await boundedBytes(manifestResponse, 2 * 1024 * 1024)))
    const logos: Record<string, string> = {}, queue = companies.filter(c => c.ticker && c.market).slice(0, 160)
    let index = 0
    await Promise.all(Array.from({ length: 4 }, async () => { while (index < queue.length && !signal.aborted) {
        const company = queue[index++], entry = manifest?.logos?.[company.ticker!]
        const expected = PNG_PREFIX + company.ticker + ".png"
        const raw = entry === undefined ? expected : typeof entry === "string" ? entry : entry?.url
        if (raw !== expected) continue
        if (typeof raw !== "string" || !raw.startsWith(PNG_PREFIX) || !/^https:\/\/static\.toss\.im\/png-icons\/securities\/icn-sec-fill-[A-Za-z0-9_.-]+\.png$/.test(raw)) continue
        try { const response = await fetch(raw, { credentials: "omit", referrerPolicy: "no-referrer", redirect: "error", signal }); if (!(response.headers.get("content-type") || "").startsWith("image/png")) continue; const bytes = await boundedBytes(response, 128 * 1024); if (bytes[0] !== 137 || bytes[1] !== 80 || bytes[2] !== 78 || bytes[3] !== 71) continue; let binary = ""; for (const byte of bytes) binary += String.fromCharCode(byte); logos[company.id] = "data:image/png;base64," + btoa(binary) } catch { /* Keep a named fallback on an image-only failure. */ }
    } }))
    return logos
}

function resolveFocus(catalogue: Catalogue, stock: Stock): Company {
    return catalogue.companies.find(c => c.ticker === stock.ticker && c.market === stock.market) || { ...stock, id: stock.market + ":" + stock.ticker }
}

export default function CompanyStructureView({ snapshot, onClose }: { snapshot: Snapshot; onClose: () => void }) {
    const [catalogue, setCatalogue] = React.useState<Catalogue | null>(null), [error, setError] = React.useState(false)
    const [focusIndex, setFocusIndex] = React.useState(0), [collapsed, setCollapsed] = React.useState<Set<string>>(new Set())
    const [includeStored, setIncludeStored] = React.useState(false)
    const [selected, setSelected] = React.useState<string | null>(null), [camera, setCamera] = React.useState({ x: 0, y: 0, zoom: 1 })
    const [logos, setLogos] = React.useState<Record<string, string>>({})
    const [brokenLogos, setBrokenLogos] = React.useState<Set<string>>(new Set())
    const cameraRef = React.useRef(camera); cameraRef.current = camera
    const space = React.useRef<HTMLDivElement>(null), host = React.useRef<HTMLElement>(null), initialFocus = React.useRef<string | null>(null)
    const drag = React.useRef<{ x: number; y: number; startX: number; startY: number; pointer: number } | null>(null)
    const current = snapshot.stocks[focusIndex] || snapshot.stocks[0]
    const focus = React.useMemo(() => catalogue && current ? resolveFocus(catalogue, current) : null, [catalogue, current])
    const layout = React.useMemo(() => catalogue && focus ? makeStructureLayout({ ...catalogue, relations: catalogue.relations.filter(r => includeStored || officialRelation(r)) }, focus) : null, [catalogue, focus, includeStored])
    const visible = React.useMemo(() => {
        if (!layout) return []
        const result: TreeNode[] = []; function add(id: string) { const n = layout!.byId.get(id)!; result.push(n); if (!collapsed.has(id)) n.children.forEach(add) } layout.roots.forEach(add); return result
    }, [layout, collapsed])
    React.useEffect(() => {
        const c = new AbortController(), timer = setTimeout(() => c.abort(), 12000)
        fetch("/member-map-review/company-structure.json", { credentials: "omit", redirect: "error", signal: c.signal }).then(r => boundedBytes(r, 2 * 1024 * 1024)).then(bytes => validateStructure(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)))).then(value => { if (!c.signal.aborted) setCatalogue(value) }).catch(() => setError(true)).finally(() => clearTimeout(timer))
        return () => { c.abort(); clearTimeout(timer) }
    }, [])
    React.useEffect(() => {
        if (!layout) return
        const c = new AbortController(), timer = setTimeout(() => c.abort(), 18000)
        loadLogos([...layout.byId.values()].map(n => n.company), c.signal).then(value => { if (!c.signal.aborted) setLogos(value) }).catch(() => {}).finally(() => clearTimeout(timer))
        return () => { c.abort(); clearTimeout(timer) }
    }, [layout])
    function fit() {
        const r = space.current?.getBoundingClientRect(); if (!r || !visible.length) return
        const left = Math.min(...visible.map(n => n.x)), right = Math.max(...visible.map(n => n.x)) + 224
        const top = Math.min(...visible.map(n => n.y)), bottom = Math.max(...visible.map(n => n.y)) + 98
        const zoom = Math.max(.12, Math.min(1, (r.width - 64) / (right - left), (r.height - 72) / (bottom - top)))
        setCamera({ x: (r.width - (right - left) * zoom) / 2 - left * zoom, y: Math.max(32, (r.height - (bottom - top) * zoom) / 2 - top * zoom), zoom })
    }
    React.useLayoutEffect(() => {
        const focusKey = focus?.id + ":" + includeStored
        if (!layout || !focus || initialFocus.current === focusKey || !space.current) return
        // Begin with the focus branch; its descendants remain in reserved world positions.
        const start = new Set<string>(); for (const [id, n] of layout.byId) if (id !== focus?.id && n.depth > 0 && n.children.length) start.add(id)
        setCollapsed(start); setSelected(null); initialFocus.current = focusKey
        const frame = requestAnimationFrame(() => {
            const shown: TreeNode[] = []; function visit(id: string) { const node = layout!.byId.get(id)!; shown.push(node); if (!start.has(id)) node.children.forEach(visit) } layout.roots.forEach(visit)
            const r = space.current?.getBoundingClientRect(); if (!r || !shown.length) return
            const left = Math.min(...shown.map(n => n.x)), right = Math.max(...shown.map(n => n.x)) + 224, bottom = Math.max(...shown.map(n => n.y)) + 110
            const zoom = Math.max(.12, Math.min(1, (r.width - 64) / (right - left), (r.height - 64) / bottom))
            setCamera({ x: (r.width - (right - left) * zoom) / 2 - left * zoom, y: Math.max(32, (r.height - bottom * zoom) / 2), zoom })
        })
        return () => cancelAnimationFrame(frame)
    }, [layout])
    React.useEffect(() => {
        const prior = document.activeElement as HTMLElement | null
        const previous = [...document.querySelectorAll("#root > *")].filter(el => el !== host.current && !el.contains(host.current)).map(el => [el as HTMLElement, (el as HTMLElement).inert] as const)
        previous.forEach(([el]) => { el.inert = true })
        host.current?.querySelector<HTMLButtonElement>(".acs-close")?.focus({ preventScroll: true })
        return () => { previous.forEach(([el, inert]) => { if (el.isConnected) el.inert = inert }); prior?.isConnected && prior.focus({ preventScroll: true }) }
    }, [])
    function zoomTo(zoom: number, px?: number, py?: number) {
        const rect = space.current?.getBoundingClientRect(); if (!rect) return
        setCamera(c => { const z = Math.max(.12, Math.min(2.5, zoom)), ratio = z / c.zoom, x = px ?? rect.width / 2, y = py ?? rect.height / 2; return { x: x - (x - c.x) * ratio, y: y - (y - c.y) * ratio, zoom: z } })
    }
    React.useEffect(() => {
        const element = space.current; if (!element) return
        const wheel = (event: WheelEvent) => { event.preventDefault(); const r = element.getBoundingClientRect(); zoomTo(cameraRef.current.zoom * Math.exp(-event.deltaY * .0015), event.clientX - r.left, event.clientY - r.top) }
        element.addEventListener("wheel", wheel, { passive: false }); return () => element.removeEventListener("wheel", wheel)
    }, [])
    function keyDown(e: React.KeyboardEvent) {
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onClose(); return }
        if (e.key === "Tab") {
            const elements = [...(host.current?.querySelectorAll<HTMLElement>("button:not(:disabled),select,summary,a[href],[tabindex='0']") || [])].filter(el => el.offsetParent !== null)
            if (e.shiftKey && document.activeElement === elements[0]) { e.preventDefault(); elements.at(-1)?.focus() }
            else if (!e.shiftKey && document.activeElement === elements.at(-1)) { e.preventDefault(); elements[0]?.focus() }
        }
    }
    const selectedNode = selected ? layout?.byId.get(selected) : null
    const selectedConnections = React.useMemo(() => catalogue?.relations.filter(r => r.from === selected && (includeStored || officialRelation(r))) || [], [catalogue, selected, includeStored])
    const companyNames = React.useMemo(() => new Map(catalogue?.companies.map(c => [c.id, c.name])), [catalogue])
    return <section className="acs-view" ref={host} role="dialog" aria-modal="true" aria-label="기업 구조 전용 보기" onKeyDown={keyDown} onClick={e => e.stopPropagation()}>
        <style>{CSS}</style>
        <header className="acs-head"><strong className="acs-brand"><i>α</i> ALPHANEST</strong><nav className="acs-tabs" aria-label="지도 보기"><button type="button" className="acs-close" onClick={onClose}>핵심 지도</button><button type="button" aria-current="page">기업 구조</button></nav><label>중심 종목<select aria-label="기업 구조 중심 종목" value={focusIndex} onChange={e => setFocusIndex(Number(e.target.value))}>{snapshot.stocks.map((s, i) => <option key={s.id} value={i}>{s.name}</option>)}</select></label></header>
        <div className="acs-toolbar"><span>{focus?.name || "기업 구조"}의 주주·출자 연결</span><button type="button" aria-pressed={includeStored} onClick={() => setIncludeStored(v => !v)}>{includeStored ? "저장 자료 포함" : "저장 자료 함께 보기"}</button><button type="button" aria-label="기업 구조 축소" onClick={() => zoomTo(camera.zoom / 1.2)}>−</button><output aria-label="기업 구조 배율">{Math.round(camera.zoom * 100)}%</output><button type="button" aria-label="기업 구조 확대" onClick={() => zoomTo(camera.zoom * 1.2)}>+</button><button type="button" onClick={fit}>한눈에</button><button type="button" onClick={() => setCollapsed(new Set(layout ? [...layout.byId].filter(([id, n]) => n.depth > 0 && id !== focus?.id).map(([id]) => id) : []))}>가지 접기</button></div>
        <div className="acs-main">
            <div className="acs-space" ref={space} tabIndex={0} role="group" aria-label="기업 구조 작업판 · 빈 공간 드래그로 이동, 휠로 확대축소" style={{ backgroundSize: `${40 * camera.zoom}px ${40 * camera.zoom}px`, backgroundPosition: `${camera.x}px ${camera.y}px` }}
                onPointerDown={e => { if ((e.target as HTMLElement).closest("button,a,select")) return; drag.current = { x: e.clientX, y: e.clientY, startX: camera.x, startY: camera.y, pointer: e.pointerId }; e.currentTarget.setPointerCapture(e.pointerId) }}
                onPointerMove={e => { const d = drag.current; if (d?.pointer === e.pointerId) setCamera(c => ({ ...c, x: d.startX + e.clientX - d.x, y: d.startY + e.clientY - d.y })) }}
                onPointerUp={e => { drag.current = null; if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId) }} onPointerCancel={() => { drag.current = null }}
                onKeyDown={e => { if (e.target !== e.currentTarget) return; const d = ({ ArrowLeft: [40, 0], ArrowRight: [-40, 0], ArrowUp: [0, 40], ArrowDown: [0, -40] } as Record<string, number[]>)[e.key]; if (d) { e.preventDefault(); setCamera(c => ({ ...c, x: c.x + d[0], y: c.y + d[1] })) } if (["+", "=", "-"].includes(e.key)) { e.preventDefault(); zoomTo(camera.zoom * (e.key === "-" ? 1 / 1.2 : 1.2)) } }}>
                {!catalogue || error ? <div className="acs-empty" role="status"><strong>{error ? "기업 구조를 불러오지 못했어요" : "기업 구조를 불러오고 있어요"}</strong>{error ? "핵심 지도로 돌아가거나 잠시 후 다시 열어 주세요." : "공개 자료의 회사와 관계를 확인합니다."}</div> : <div className="acs-world" style={{ transform: `translate(${camera.x}px,${camera.y}px) scale(${camera.zoom})` }}>
                    <svg className="acs-lines" aria-hidden="true" width="1" height="1">{visible.filter(n => n.parent).map(n => { const p = layout!.byId.get(n.parent!)!; const x1 = p.x + 112, y1 = p.y + 86, x2 = n.x + 112, y2 = n.y, middle = (y1 + y2) / 2; return <path key={n.company.id} d={`M${x1} ${y1} V${middle} H${x2} V${y2}`} data-undated={n.relation?.status === "undated-snapshot"} /> })}</svg>
                    {visible.map(n => {
                        const stock = snapshot.stocks.find(s => s.ticker === n.company.ticker && s.market === n.company.market)
                        const logo = brokenLogos.has(n.company.id) ? undefined : n.company.id === "FOREIGN:solidigm-inc" ? "/member-map-review/solidigm-logo.png" : imageData(stock?.logo) || logos[n.company.id]
                        const flag = imageData(snapshot.flags[n.company.market || n.company.country || ""])
                        const r = n.relation, dated = r?.status === "source-dated" || r?.status === "official-undated", pct = r?.status === "source-dated" && typeof r?.ownershipPct === "number" ? ` · ${r.ownershipPct}%` : ""
                        return <article key={n.company.id} className="acs-card" data-company={n.company.id} data-focus={n.company.id === focus?.id} data-dated={dated} style={{ left: n.x, top: n.y }}>
                            <span className="acs-face" aria-hidden="true">{logo ? <img className="acs-logo" src={logo} alt="" draggable={false} style={n.company.id === "FOREIGN:solidigm-inc" ? { objectFit: "cover", objectPosition: "left", height: 32 } : undefined} onError={() => setBrokenLogos(old => new Set(old).add(n.company.id))} /> : n.company.name.slice(0, 1)}{flag && <img className="acs-flag" src={flag} alt="" title={n.company.market === "KR" ? "한국 상장" : n.company.market === "US" ? "미국 상장" : "소재 국가"} draggable={false} />}</span>
                            <button type="button" className="acs-card-main" aria-label={`${n.company.name} · ${r?.label || "중심 회사"}${pct} · 근거 보기`} onClick={() => setSelected(n.company.id)}><span className="acs-name" title={n.company.name}>{n.company.name}</span><span className="acs-role">{n.company.id === focus?.id && r?.type === "major-shareholder" ? "주요 주주 지분" : n.company.id === focus?.id ? "선택 종목" : r?.label || "주요 주주"}{pct}</span><span className="acs-role">{r ? r.asOf ? `기준 ${r.asOf}` : r.status === "official-undated" ? "공식 안내 · 기준일 미표시" : "원문 기준일 미확인" : n.company.id === focus?.id ? "중심 종목" : "주주 연결"}</span></button>
                            {!!n.children.length && <><button type="button" className="acs-branch" aria-label={`${n.company.name} 가지 ${collapsed.has(n.company.id) ? "펼치기" : "접기"}`} aria-expanded={!collapsed.has(n.company.id)} onClick={() => setCollapsed(old => { const next = new Set(old); next.has(n.company.id) ? next.delete(n.company.id) : next.add(n.company.id); return next })}>{collapsed.has(n.company.id) ? "+" : "−"}</button><span className="acs-child-count">{n.children.length}개</span></>}
                        </article>
                    })}
                </div>}
            </div>
            {selectedNode && <aside className="acs-inspector" aria-label="기업 관계 근거"><button className="acs-inspector-close" type="button" aria-label="관계 근거 닫기" onClick={() => setSelected(null)}>×</button><h2>{selectedNode.company.name}</h2>{selectedNode.relation ? <RelationshipProof relation={selectedNode.relation} /> : <p>주요 주주와 출자 자료를 중심으로 연결합니다. 회사 이름이나 같은 그룹명만으로 소유 관계를 추가하지 않습니다.</p>}
                {!!selectedConnections.length && <section aria-label="선택 회사의 연결 자료"><h3 style={{ fontSize: 13, fontWeight: 700, margin: "22px 0 8px" }}>연결 자료 {selectedConnections.length}건</h3><p>화면에서 생략된 연결도 이 목록에서 확인할 수 있어요.</p>{selectedConnections.map(r => <details key={r.id} style={{ padding: "10px 0" }}><summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 700 }}>{companyNames.get(r.to)} · {r.label}</summary><RelationshipProof relation={r} /></details>)}</section>}
            </aside>}
        </div>
        <footer className="acs-foot"><span className="acs-key"><i />공식 근거 · 날짜는 관계별 확인</span><span className="acs-key" data-kind="undated"><i />기준일 미확인 저장 자료</span><span className="acs-status" role="status">{visible.length}개 회사{layout?.omitted ? ` · ${layout.omitted}개 연결은 표시 범위 밖` : ""}{layout && layout.byId.size === 1 ? " · 공식 연결 근거가 제공되지 않았어요" : ""}</span></footer>
    </section>
}

export function useCompanyStructureBridge(owner: string | null) {
    const [view, setView] = React.useState<{ owner: string; snapshot: Snapshot } | null>(null)
    const [waiting, setWaiting] = React.useState(false)
    const request = React.useRef<string | null>(null), timer = React.useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
    React.useEffect(() => {
        setView(null); setWaiting(false); request.current = null
        if (!owner) return
        const receive = (event: MessageEvent) => {
            const frame = [...document.querySelectorAll("iframe")].find(f => { try { return new URL(f.src).pathname === "/member-map-canvas" && f.contentWindow === event.source } catch { return false } })
            if (!frame || event.origin !== "null" || !event.data || event.data.type !== "an-company-structure-snapshot" || event.data.request !== request.current || !Array.isArray(event.data.stocks) || event.data.stocks.length > 30) return
            const stocks = event.data.stocks.filter((s: Stock) => s && typeof s.name === "string" && s.name.length < 301 && typeof s.ticker === "string" && (s.market === "KR" && /^\d{6}$/.test(s.ticker) || s.market === "US" && /^[A-Z][A-Z0-9.-]{0,11}$/.test(s.ticker))).map((s: Stock) => ({ id: s.market + ":" + s.ticker, ticker: s.ticker, market: s.market, name: s.name, logo: imageData(s.logo) }))
            if (!stocks.length) { setWaiting(false); return }
            const flags: Record<string, string> = {}; for (const code of ["KR", "US", "TW"]) { const data = imageData(event.data.flags?.[code]); if (data) flags[code] = data }
            clearTimeout(timer.current); request.current = null; setWaiting(false); setView({ owner, snapshot: { stocks, flags } })
        }
        window.addEventListener("message", receive)
        return () => { window.removeEventListener("message", receive); clearTimeout(timer.current) }
    }, [owner])
    function open() {
        const frame = [...document.querySelectorAll("iframe")].find(f => { try { return new URL(f.src).pathname === "/member-map-canvas" } catch { return false } })
        if (!frame?.contentWindow) return
        request.current = crypto.randomUUID(); setWaiting(true)
        frame.contentWindow.postMessage({ type: "an-company-structure-request", request: request.current }, "*")
        clearTimeout(timer.current); timer.current = setTimeout(() => { request.current = null; setWaiting(false) }, 4000)
    }
    return { snapshot: view?.owner === owner ? view.snapshot : null, waiting, open, close: () => setView(null) }
}

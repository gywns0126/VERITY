import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { startTransition, useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 종목 변화 센터 — 가격·사업·고용·자본조달 사실을 기준일과 함께 표시한다.
 * 추천·점수·전망을 만들지 않으며 결손 소스도 커버리지에 그대로 신고한다.
 */

const DEFAULT_URL = "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/stock_change_public"
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const LIGHT = {
    card: "#ffffff", card2: "#f8f9fa", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", up: "#f04452", down: "#3182f6",
}
const DARK = {
    card: "#171c23", card2: "#11161c", ink: "#e3e7ec", sub: "#a3acb8", faint: "#7f8a99",
    line: "#29313b", violet: "#aa9cff", violetSoft: "#211d38", up: "#ff6570", down: "#69a8ff",
}

interface Props {
    dataUrl: string
    ticker: string
    dark: boolean
}

const SAMPLE: any = {
    _meta: {
        generated_at: "2026-08-28T01:12:37+09:00",
        denominators: { report_universe: 2495, daily_pair: 1832, business_current: 2355, business_previous: 0, employment: 1501, employment_month_pair: 1313, capital_history: 1509 },
    },
    stocks: {
        "005930": {
            ticker: "005930", name: "삼성전자", market: "KOSPI",
            today: { status: "changed", as_of: "2026-08-27", previous_as_of: "2026-08-26", fields: [{ key: "price", label: "가격", before: 261500, after: 264500, delta: 3000, delta_pct: 1.15 }], disclosures: [] },
            business_report: { status: "baseline", current: { fiscal_year: "2025", filed_at: "20260310", report: "사업보고서 (2025.12)", text: "글로벌 전자 기업으로 DX, DS, SDC 및 Harman 사업을 운영합니다.", url: "https://dart.fss.or.kr/" }, previous: null, added: [], removed: [] },
            employment_performance: { employment: { as_of: "202607", count: 125594, previous_as_of: "202606", previous_count: 125592, growth_pct: 0, hire: 445, leave: 421, net: 24 }, performance: { as_of: 2025, previous_as_of: 2024, revenue_growth_pct: 11.3, operating_profit_growth_pct: 8.4 }, relationship: "mixed_direction", note: "고용과 실적의 방향을 나란히 놓은 사실 비교이며 인과관계나 전망이 아니다." },
            capital_timeline: { status: "ready", event_total: 2, events: [{ date: "2026-06-11", category: "자기주식처분", title: "주요사항보고서", source_url: "https://dart.fss.or.kr/" }], instruments: [], dilution_pct: null, note: "공시 제목 분류 이력" },
            coverage: { hit: 5, total: 6, fields: { daily_pair: true, business_report: true, business_previous: false, employment: true, financial_pair: true, capital_history: true } },
        },
    },
}

const COVERAGE_LABEL: Record<string, string> = {
    daily_pair: "거래일 비교", business_report: "사업 개요", business_previous: "이전 수집본",
    employment: "고용", financial_pair: "연간 실적", capital_history: "자본조달 이력",
}

function compactTicker(value: unknown): string {
    const text = String(value || "").trim().toUpperCase()
    return /^\d{1,6}$/.test(text) ? text.padStart(6, "0") : text
}

function readTicker(fallback: string): string {
    if (typeof window === "undefined") return compactTicker(fallback)
    const q = new URLSearchParams(window.location.search).get("q") || ""
    let stored = ""
    try { stored = localStorage.getItem("verity_last_ticker") || "" } catch {}
    // Framer의 prop 기본값이 현재 선택 종목을 가로막지 않게 URL/공유 저장값을 우선한다.
    return compactTicker(q || stored || fallback || "005930")
}

function numberText(value: unknown, digits = 1): string {
    const n = Number(value)
    if (!Number.isFinite(n)) return "—"
    return n.toLocaleString("ko-KR", { maximumFractionDigits: digits })
}

function percentText(value: unknown): string {
    const n = Number(value)
    if (!Number.isFinite(n)) return "—"
    return `${n > 0 ? "+" : ""}${n.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`
}

function dateText(value: unknown): string {
    const raw = String(value || "")
    if (/^\d{8}$/.test(raw)) return `${raw.slice(0, 4)}.${raw.slice(4, 6)}.${raw.slice(6, 8)}`
    if (/^\d{6}$/.test(raw)) return `${raw.slice(0, 4)}.${raw.slice(4, 6)}`
    return raw || "—"
}

function ValueChange({ label, before, after, pct, colors }: any) {
    const n = Number(pct)
    const color = Number.isFinite(n) && n !== 0 ? (n > 0 ? colors.up : colors.down) : colors.sub
    return (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(62px,.8fr) minmax(0,1.6fr) auto", gap: 8, alignItems: "center", padding: "8px 0", borderTop: `1px solid ${colors.line}` }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: colors.sub }}>{label}</span>
            <span style={{ minWidth: 0, fontSize: 11.5, color: colors.faint, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{numberText(before, 3)} → <b style={{ color: colors.ink }}>{numberText(after, 3)}</b></span>
            <span style={{ color, fontSize: 11.5, fontWeight: 800 }}>{percentText(pct)}</span>
        </div>
    )
}

function FactCell({ title, period, value, colors }: any) {
    const n = Number(value)
    const color = Number.isFinite(n) && n !== 0 ? (n > 0 ? colors.up : colors.down) : colors.ink
    return (
        <div style={{ minWidth: 0, padding: 10, borderRadius: 10, background: colors.card2 }}>
            <div style={{ fontSize: 10.5, color: colors.faint, fontWeight: 700 }}>{title}</div>
            <div style={{ marginTop: 4, fontSize: 17, color, fontWeight: 800 }}>{percentText(value)}</div>
            <div style={{ marginTop: 3, fontSize: 9.5, color: colors.faint }}>{period}</div>
        </div>
    )
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 */
export default function PublicStockChangeCenter(props: Props) {
    const rootRef = useRef<HTMLDivElement>(null)
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [ticker, setTicker] = useState(() => onCanvas ? compactTicker(props.ticker || "005930") : readTicker(props.ticker))
    const [payload, setPayload] = useState<any>(() => onCanvas ? SAMPLE : null)
    const [error, setError] = useState("")
    const [expanded, setExpanded] = useState(false)
    const [themeDark, setThemeDark] = useState(!!props.dark)
    const [width, setWidth] = useState(0)
    const dark = onCanvas ? !!props.dark : themeDark
    const C = dark ? DARK : LIGHT

    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        const sync = () => startTransition(() => setTicker(readTicker(props.ticker)))
        sync()
        window.addEventListener("popstate", sync)
        window.addEventListener("storage", sync)
        window.addEventListener("verity-ticker-change", sync as EventListener)
        window.addEventListener("focus", sync)
        return () => {
            window.removeEventListener("popstate", sync)
            window.removeEventListener("storage", sync)
            window.removeEventListener("verity-ticker-change", sync as EventListener)
            window.removeEventListener("focus", sync)
        }
    }, [onCanvas, props.ticker])

    useEffect(() => {
        if (onCanvas || typeof document === "undefined" || !document.body) return
        const read = () => startTransition(() => setThemeDark(document.documentElement?.dataset.anTheme === "dark" || document.body.dataset.framerTheme === "dark"))
        read()
        const observer = new MutationObserver(read)
        observer.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-an-theme"] })
        return () => observer.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let active = true
        const root = (props.dataUrl || DEFAULT_URL).replace(/\/+$/, "")
        const prefix = ticker.slice(0, 3)
        Promise.all([
            fetch(`${root}/_summary.json`, { cache: "no-store" }).then((response) => response.ok ? response.json() : Promise.reject(new Error(String(response.status)))),
            fetch(`${root}/${prefix}.json`, { cache: "no-store" }).then((response) => response.ok ? response.json() : Promise.reject(new Error(String(response.status)))),
        ])
            .then(([summary, chunk]) => {
                if (!active) return
                startTransition(() => { setPayload({ _meta: summary?._meta || {}, stocks: chunk?.stocks || {} }); setError("") })
            })
            .catch(() => { if (active) startTransition(() => setError("변화 데이터를 불러오지 못했습니다.")) })
        return () => { active = false }
    }, [props.dataUrl, onCanvas, ticker])

    useEffect(() => { startTransition(() => setExpanded(false)) }, [ticker])

    useEffect(() => {
        const root = rootRef.current
        if (!root || typeof ResizeObserver === "undefined") return
        const observer = new ResizeObserver(([entry]) => {
            const next = entry?.contentRect.width || 0
            startTransition(() => setWidth(next))
        })
        observer.observe(root)
        return () => observer.disconnect()
    }, [])

    const stock = payload?.stocks?.[ticker]
    const meta = payload?._meta || {}
    const coverage = stock?.coverage || { hit: 0, total: 6, fields: {} }
    const missing = useMemo(() => Object.entries(coverage.fields || {}).filter(([, hit]) => !hit).map(([key]) => COVERAGE_LABEL[key] || key), [coverage.fields])
    const today = stock?.today || {}
    const business = stock?.business_report || {}
    const currentBusiness = business.current || null
    const employment = stock?.employment_performance?.employment || {}
    const performance = stock?.employment_performance?.performance || {}
    const capital = stock?.capital_timeline || {}
    const fields = Array.isArray(today.fields) ? today.fields : []
    const events = Array.isArray(capital.events) ? capital.events : []
    const narrow = width > 0 && width < 460

    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: 16, boxSizing: "border-box", minWidth: 0 }
    // 인접 /stock 컴포넌트와 동일한 외곽 여백. 되돌리지 말 것.
    const shell: CSSProperties = { width: "100%", padding: `0 ${narrow ? 12 : 18}px`, boxSizing: "border-box", fontFamily: FONT }
    const title: CSSProperties = { margin: 0, color: C.ink, fontSize: 15, fontWeight: 800, letterSpacing: "-0.25px" }
    const sub: CSSProperties = { color: C.faint, fontSize: 10.5, lineHeight: 1.5 }

    if (error) return <div ref={rootRef} style={shell}><div style={{ ...card, color: C.sub }}>{error}</div></div>
    if (!payload) return <div ref={rootRef} style={shell}><div style={{ ...card, color: C.faint }}>변화 데이터 확인 중…</div></div>
    if (!stock) return <div ref={rootRef} style={shell}><div style={{ ...card, color: C.sub }}>{ticker || "선택 종목"}의 결합 데이터가 없습니다.</div></div>

    return (
        <div ref={rootRef} style={{ ...shell, color: C.ink, display: "grid", gap: 12 }}>
            <header style={{ ...card, display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                <div style={{ minWidth: 0 }}>
                    <div style={{ color: C.violet, fontSize: 10.5, fontWeight: 800 }}>종목 변화 센터</div>
                    <h2 style={{ margin: "3px 0 0", fontSize: 20, fontWeight: 850, letterSpacing: "-0.5px" }}>{stock.name} <span style={{ color: C.faint, fontSize: 12 }}>{ticker}</span></h2>
                    <div style={{ ...sub, marginTop: 5 }}>생성 {dateText(String(meta.generated_at || "").slice(0, 10))} · 기존 사실 조인 · 추천·점수 없음</div>
                </div>
                <div style={{ flexShrink: 0, borderRadius: 999, padding: "6px 9px", background: C.violetSoft, color: C.violet, fontSize: 10.5, fontWeight: 800 }}>표시 소스 {coverage.hit}/{coverage.total}</div>
            </header>

            {missing.length > 0 && <div role="status" style={{ padding: "9px 12px", borderRadius: 10, background: C.card2, color: C.faint, fontSize: 10.5 }}>미조회·결손: {missing.join(", ")}</div>}

            <section style={card} aria-labelledby="today-change-title">
                <h3 id="today-change-title" style={title}>오늘 달라진 것</h3>
                <div style={{ ...sub, marginTop: 4 }}>{dateText(today.previous_as_of)} → {dateText(today.as_of)} · 종목별 최근 두 거래일</div>
                {fields.length > 0 ? fields.map((field: any) => <ValueChange key={field.key} label={field.label} before={field.before} after={field.after} pct={field.delta_pct} colors={C} />) : <div style={{ ...sub, marginTop: 12 }}>{today.status === "unchanged" ? "비교 필드 변화 없음" : "비교 가능한 두 거래일이 없습니다."}</div>}
                {(today.disclosures || []).map((event: any, index: number) => <a key={`${event.date}-${index}`} href={event.source_url || undefined} target="_blank" rel="noopener noreferrer" style={{ display: "block", marginTop: 8, color: C.violet, fontSize: 11, fontWeight: 700, textDecoration: "none" }}>{event.is_correction ? "정정 · " : ""}{event.label} · {event.title}</a>)}
            </section>

            <section style={card} aria-labelledby="business-change-title">
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
                    <div>
                        <h3 id="business-change-title" style={title}>사업보고서 변경 비교</h3>
                        <div style={{ ...sub, marginTop: 4 }}>{currentBusiness ? `${currentBusiness.report || "사업보고서"} · 제출 ${dateText(currentBusiness.filed_at)}` : "사업 개요 결손"}</div>
                    </div>
                    {currentBusiness?.url && <a href={currentBusiness.url} target="_blank" rel="noopener noreferrer" style={{ color: C.violet, fontSize: 10.5, fontWeight: 800, textDecoration: "none", whiteSpace: "nowrap" }}>DART 원문 ↗</a>}
                </div>
                {business.status === "baseline" && <div style={{ ...sub, marginTop: 10 }}>현재 수집본을 기준선으로 저장했습니다. 다음 수집부터 문장 변경을 비교합니다.</div>}
                {business.status === "changed" && <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
                    {(business.added || []).map((text: string, i: number) => <div key={`a${i}`} style={{ color: C.sub, fontSize: 11, lineHeight: 1.5 }}><b style={{ color: C.up }}>추가</b> · {text}</div>)}
                    {(business.removed || []).map((text: string, i: number) => <div key={`r${i}`} style={{ color: C.sub, fontSize: 11, lineHeight: 1.5 }}><b style={{ color: C.down }}>삭제</b> · {text}</div>)}
                </div>}
                {currentBusiness?.text && <>
                    <button type="button" onClick={() => startTransition(() => setExpanded((value) => !value))} aria-expanded={expanded} style={{ marginTop: 10, border: "none", padding: 0, background: "transparent", color: C.violet, fontFamily: FONT, fontSize: 10.5, fontWeight: 800, cursor: "pointer" }}>{expanded ? "사업 개요 접기" : "사업 개요 보기"}</button>
                    {expanded && <p style={{ margin: "9px 0 0", color: C.sub, fontSize: 11.5, lineHeight: 1.7, whiteSpace: "pre-wrap" }}>{currentBusiness.text}</p>}
                </>}
                <div style={{ ...sub, marginTop: 10 }}>전체 커버리지: 현재 {numberText(meta.denominators?.business_current, 0)}/{numberText(meta.denominators?.report_universe, 0)} · 이전 수집본 {numberText(meta.denominators?.business_previous, 0)}/{numberText(meta.denominators?.report_universe, 0)}</div>
            </section>

            <section style={card} aria-labelledby="employment-performance-title">
                <h3 id="employment-performance-title" style={title}>고용–실적 비교</h3>
                <div style={{ ...sub, marginTop: 4 }}>서로 다른 공시 주기를 독립 기준일로 표시합니다.</div>
                <div style={{ marginTop: 11, display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 7 }}>
                    <FactCell title="가입자 변화" value={employment.growth_pct} period={`${dateText(employment.previous_as_of)}→${dateText(employment.as_of)}`} colors={C} />
                    <FactCell title="매출 변화" value={performance.revenue_growth_pct} period={`${dateText(performance.previous_as_of)}→${dateText(performance.as_of)}`} colors={C} />
                    <FactCell title="영업익 변화" value={performance.operating_profit_growth_pct} period={`${dateText(performance.previous_as_of)}→${dateText(performance.as_of)}`} colors={C} />
                </div>
                <div style={{ ...sub, marginTop: 9 }}>가입자 {numberText(employment.previous_count, 0)}명→{numberText(employment.count, 0)}명 · 입사 {numberText(employment.hire, 0)} · 퇴사 {numberText(employment.leave, 0)} · 순증감 {numberText(employment.net, 0)}</div>
                <div style={{ ...sub, marginTop: 5 }}>{stock.employment_performance?.note}</div>
            </section>

            <section style={card} aria-labelledby="capital-timeline-title">
                <h3 id="capital-timeline-title" style={title}>자본조달·희석 연대기</h3>
                <div style={{ ...sub, marginTop: 4 }}>분류 공시 {numberText(capital.event_total, 0)}건 · 화면에는 최근 {Math.min(events.length, 20)}건</div>
                {events.length ? <div style={{ marginTop: 8 }}>
                    {events.map((event: any, i: number) => <div key={`${event.date}-${event.title}-${i}`} style={{ display: "grid", gridTemplateColumns: "76px minmax(0,1fr)", gap: 8, padding: "8px 0", borderTop: `1px solid ${C.line}` }}>
                        <span style={{ color: C.faint, fontSize: 10.5 }}>{dateText(event.date)}</span>
                        <a href={event.source_url || undefined} target={event.source_url ? "_blank" : undefined} rel="noopener noreferrer" style={{ minWidth: 0, color: C.sub, fontSize: 11, fontWeight: 650, lineHeight: 1.45, textDecoration: "none" }}><b style={{ color: C.violet }}>{event.is_correction ? "정정 · " : ""}{event.category}</b> · {event.title}</a>
                    </div>)}
                </div> : <div style={{ ...sub, marginTop: 10 }}>결합된 자본조달 분류 이력이 없습니다.</div>}
                {Number.isFinite(Number(capital.dilution_pct)) && <div style={{ ...sub, marginTop: 8 }}>현재 공개 산출물의 잠재 희석률: {percentText(capital.dilution_pct)}</div>}
                <div style={{ ...sub, marginTop: 5 }}>{capital.note}</div>
            </section>
        </div>
    )
}

addPropertyControls(PublicStockChangeCenter, {
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DEFAULT_URL },
    ticker: { type: ControlType.String, title: "Ticker", defaultValue: "" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

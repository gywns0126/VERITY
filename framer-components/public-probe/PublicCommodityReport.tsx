import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState } from "react"
import PublicStockSearch from "https://framer.com/m/PublicStockSearch-iqt9J1.js"

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const BASE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const DEFAULT_MACRO = BASE + "/macro_snapshot.json"
const DEFAULT_EXPOSURE = BASE + "/commodity_exposure.json"
const SEARCH_UNIVERSE = BASE + "/universe_search.json"
const US_REPORT = BASE + "/us_stock_report_public.json"
const LIGHT = { card: "#fff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", field: "#f2f4f6", blue: "#3182f6", blueS: "#e8f1fe", red: "#f04452", shadow: "rgba(0,0,0,.05)" }
const DARK = { card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", field: "#222831", blue: "#5b9bff", blueS: "#16233a", red: "#f05b67", shadow: "rgba(0,0,0,.24)" }
const P = "cmdrep"
const PALETTE = "body{" + Object.keys(LIGHT).map((key) => "--an-" + P + "-" + key + ":" + (LIGHT as any)[key]).join(";") + "}" + 'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((key) => "--an-" + P + "-" + key + ":" + (DARK as any)[key]).join(";") + "}"
const C: Record<string, string> = {}
for (const key of Object.keys(LIGHT)) C[key] = "var(--an-" + P + "-" + key + ")"

type Commodity = {
    ticker: string
    name: string
    symbol: string
    group: string
    unit: string
    exchange: string
    macroKey: string
    exposureKey?: string
    corrKey?: "gold" | "oil"
    drivers: string[]
    calendar: string
    related: string
}

const COMMODITIES: Commodity[] = [
    { ticker: "CMD_GOLD", name: "금", symbol: "GC=F", group: "귀금속", unit: "USD/트로이온스", exchange: "COMEX", macroKey: "gold", exposureKey: "gold", corrKey: "gold", drivers: ["달러", "실질금리", "중앙은행 수요"], calendar: "미국 물가·고용·연준 일정", related: "금광·귀금속 ETF" },
    { ticker: "CMD_SILVER", name: "은", symbol: "SI=F", group: "귀금속", unit: "USD/트로이온스", exchange: "COMEX", macroKey: "silver", exposureKey: "silver", drivers: ["달러", "태양광·산업 수요", "금 가격"], calendar: "미국 물가·제조업 지표", related: "은광·귀금속 ETF" },
    { ticker: "CMD_COPPER", name: "구리", symbol: "HG=F", group: "산업금속", unit: "USD/파운드", exchange: "COMEX", macroKey: "copper", exposureKey: "copper", drivers: ["중국 경기", "재고", "전력망·건설 수요"], calendar: "중국 PMI·LME 재고", related: "비철금속·전선·구리 ETF" },
    { ticker: "CMD_WTI", name: "WTI 원유", symbol: "CL=F", group: "에너지", unit: "USD/배럴", exchange: "NYMEX", macroKey: "wti_oil", exposureKey: "wti_oil", corrKey: "oil", drivers: ["OPEC+", "미국 원유 재고", "지정학"], calendar: "EIA 주간 원유재고·OPEC 일정", related: "정유·항공·석유화학" },
    { ticker: "CMD_BRENT", name: "브렌트유", symbol: "BZ=F", group: "에너지", unit: "USD/배럴", exchange: "ICE", macroKey: "brent", corrKey: "oil", drivers: ["OPEC+", "유럽·아시아 수요", "지정학"], calendar: "OPEC 월간보고서·IEA 보고서", related: "글로벌 에너지·운송" },
    { ticker: "CMD_NATGAS", name: "천연가스", symbol: "NG=F", group: "에너지", unit: "USD/MMBtu", exchange: "NYMEX", macroKey: "natural_gas", drivers: ["기온", "저장량", "LNG 수출"], calendar: "EIA 주간 천연가스 저장량", related: "가스·발전·비료" },
    { ticker: "CMD_CORN", name: "옥수수", symbol: "ZC=F", group: "농산물", unit: "USD/부셸", exchange: "CBOT", macroKey: "corn", drivers: ["미국·브라질 작황", "에탄올 수요", "날씨"], calendar: "USDA WASDE·주간 작황", related: "사료·식품·에탄올" },
    { ticker: "CMD_WHEAT", name: "밀", symbol: "ZW=F", group: "농산물", unit: "USD/부셸", exchange: "CBOT", macroKey: "wheat", drivers: ["흑해 수출", "작황", "재고"], calendar: "USDA WASDE·수출 검사", related: "제분·식품" },
    { ticker: "CMD_SOYBEAN", name: "대두", symbol: "ZS=F", group: "농산물", unit: "USD/부셸", exchange: "CBOT", macroKey: "soybean", drivers: ["중국 수입", "남미 작황", "대두유 수요"], calendar: "USDA WASDE·수출 판매", related: "사료·식용유" },
    { ticker: "CMD_COFFEE", name: "커피", symbol: "KC=F", group: "농산물", unit: "USD/파운드", exchange: "ICE", macroKey: "coffee", drivers: ["브라질·베트남 작황", "기온", "재고"], calendar: "ICE 재고·주요 생산국 수확", related: "음료·식품" },
    { ticker: "CMD_SUGAR", name: "설탕", symbol: "SB=F", group: "농산물", unit: "USD/파운드", exchange: "ICE", macroKey: "sugar", drivers: ["브라질 생산", "에탄올 전환", "인도 수출"], calendar: "주요 생산국 생산·수출 발표", related: "식품·음료" },
    { ticker: "CMD_COTTON", name: "면화", symbol: "CT=F", group: "농산물", unit: "USD/파운드", exchange: "ICE", macroKey: "cotton", drivers: ["미국 작황", "중국 섬유 수요", "재고"], calendar: "USDA 면화 수급·주간 작황", related: "섬유·의류" },
]
const BY_TICKER = new Map(COMMODITIES.map((item) => [item.ticker, item]))

interface Props {
    macroUrl: string
    exposureUrl: string
    previewTicker: string
    dark: boolean
}

function readTicker(previewTicker: string, onCanvas: boolean) {
    if (onCanvas) return previewTicker || "CMD_GOLD"
    if (typeof window === "undefined") return ""
    return String(new URLSearchParams(window.location.search).get("q") || "").trim().toUpperCase()
}
function num(value: unknown): number | null {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
}
function fmt(value: unknown, digits = 2) {
    const parsed = num(value)
    return parsed === null ? "—" : parsed.toLocaleString("ko-KR", { maximumFractionDigits: digits })
}
function pct(values: number[], offset: number) {
    if (values.length <= offset) return null
    const first = values[values.length - 1 - offset]
    const last = values[values.length - 1]
    return first ? ((last - first) / Math.abs(first)) * 100 : null
}
function fmtPct(value: unknown) {
    const parsed = num(value)
    return parsed === null ? "—" : (parsed > 0 ? "+" : "") + parsed.toFixed(2) + "%"
}
function fmtTimestamp(value: unknown) {
    if (!value) return "기준시각 확인 중"
    const date = new Date(String(value))
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }) + " KST"
}
function labelAsset(key: string) {
    return ({ stock: "미국 주식", bond_yield: "미 10년물", usd: "달러", oil: "유가", gold: "금", btc: "비트코인" } as any)[key] || key
}

export default function PublicCommodityReport(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [ticker, setTicker] = useState(() => readTicker(props.previewTicker, onCanvas))
    const [macro, setMacro] = useState<any>(null)
    const [exposure, setExposure] = useState<any>(null)
    const item = useMemo(() => BY_TICKER.get(ticker), [ticker])

    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        const sync = () => setTicker(readTicker(props.previewTicker, false))
        window.addEventListener("verity-ticker-change", sync)
        window.addEventListener("popstate", sync)
        return () => {
            window.removeEventListener("verity-ticker-change", sync)
            window.removeEventListener("popstate", sync)
        }
    }, [onCanvas, props.previewTicker])

    useEffect(() => {
        if (!item) {
            setMacro(null)
            setExposure(null)
            return
        }
        let alive = true
        Promise.all([
            fetch(props.macroUrl || DEFAULT_MACRO)
                .then((response) => response.ok ? response.json() : null)
                .catch(() => null),
            fetch(props.exposureUrl || DEFAULT_EXPOSURE)
                .then((response) => response.ok ? response.json() : null)
                .catch(() => null),
        ]).then(([macroData, exposureData]) => {
            if (!alive) return
            setMacro(macroData)
            setExposure(exposureData)
        }).catch(() => {
            if (!alive) return
            setMacro(null)
            setExposure(null)
        })
        return () => { alive = false }
    }, [item?.ticker, props.macroUrl, props.exposureUrl])

    if (!item) return null

    const quote = macro?.macro?.[item.macroKey] || macro?.[item.macroKey] || null
    const benchmark = macro?.commodity_benchmarks?.items?.[ticker]
    const benchmarkQuote = benchmark?.latest ? { value: benchmark.latest.value, change_pct: benchmark.change_pct, as_of: benchmark.latest.period, source: "World Bank Pink Sheet" } : null
    const displayQuote = quote || benchmarkQuote
    const usesBenchmark = !quote && Boolean(benchmarkQuote)
    const generatedAt = displayQuote?.as_of || macro?.collected_at || macro?._meta?.generated_at || macro?.generated_at
    const value = num(displayQuote?.value)
    const change = num(displayQuote?.change_pct)
    const source = String(displayQuote?.source || "출처 확인 중")
    const history = Array.isArray(quote?.history_daily)
        ? quote.history_daily.map((row: any) => num(row?.close)).filter((row: any) => row !== null)
        : Array.isArray(quote?.sparkline)
          ? quote.sparkline.map(num).filter((row: any) => row !== null)
          : []
    const returns = {
        month: pct(history, 21),
        quarter: pct(history, 65),
        year: history.length >= 180 ? pct(history, Math.min(251, history.length - 1)) : null,
    }
    const corrMatrix = item.corrKey ? macro?.macro?.cross_asset_corr?.matrix?.[item.corrKey] : null
    const correlations = corrMatrix
        ? Object.entries(corrMatrix)
              .filter(([key, val]) => key !== item.corrKey && num(val) !== null)
              .sort((a, b) => Math.abs(Number(b[1])) - Math.abs(Number(a[1])))
              .slice(0, 4)
        : []
    const events = Array.isArray(macro?.global_events)
        ? macro.global_events.filter((event: any) => num(event?.d_day) !== null && Number(event.d_day) >= 0).slice(0, 3)
        : []
    const exposureBlock = item.exposureKey ? exposure?.commodities?.[item.exposureKey] : null
    const card = { background: C.card, borderRadius: 20, padding: "18px clamp(16px,2.4vw,24px)", boxShadow: "0 8px 28px " + C.shadow }
    const stat = (label: string, display: string, note?: string) => (
        <div style={{ background: C.field, borderRadius: 14, padding: "11px 12px", minWidth: 0 }}>
            <div style={{ color: C.faint, fontSize: 10, fontWeight: 750 }}>{label}</div>
            <div style={{ color: C.ink, fontSize: 13, fontWeight: 850, marginTop: 4 }}>{display}</div>
            {note ? <div style={{ color: C.faint, fontSize: 9.5, marginTop: 3 }}>{note}</div> : null}
        </div>
    )

    return <div style={{ width: "100%", padding: "0 clamp(14px, 2vw, 20px)", boxSizing: "border-box", fontFamily: FONT, color: C.ink }}>
        <style>{PALETTE}</style>
        <main style={{ maxWidth: 1100, margin: "0 auto", display: "grid", gap: 14 }}>
            <div style={{ width: "100%", height: 41, minWidth: 0 }}>
                <PublicStockSearch placeholder="종목·ETF·원자재 검색" stockPath="/stock" stockUrl={SEARCH_UNIVERSE} usStockUrl={US_REPORT} dark={props.dark} reportStyle={true} />
            </div>

            <section style={card}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
                    <div>
                        <div style={{ color: C.blue, fontSize: 12, fontWeight: 850 }}>{item.group} · {usesBenchmark ? "월평균 기준선" : "선물 연속물"}</div>
                        <h1 style={{ margin: "5px 0 0", fontSize: 25, letterSpacing: "-.6px" }}>{item.name}</h1>
                        <div style={{ color: C.faint, fontSize: 12, fontWeight: 700, marginTop: 5 }}>{item.symbol} · {item.exchange} · {usesBenchmark ? String(benchmark?.unit || "USD 기준") : item.unit}</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 25, fontWeight: 900 }}>{fmt(value, 3)}</div>
                        <div style={{ marginTop: 4, color: change !== null && change > 0 ? C.red : C.blue, fontSize: 13, fontWeight: 850 }}>{fmtPct(change)}</div>
                        <div style={{ color: C.faint, fontSize: 10.5, marginTop: 5 }}>{source} · {fmtTimestamp(generatedAt)}</div>
                    </div>
                </div>
                <div style={{ marginTop: 16, borderRadius: 16, background: C.blueS, padding: "13px 15px", color: C.sub, fontSize: 12.5, lineHeight: 1.65, fontWeight: 650 }}>
                    {usesBenchmark ? "세계은행 월평균 벤치마크입니다. 선물 현재가와 직접 비교하지 않습니다." : "여러 만기 계약을 이어 만든 선물 연속물입니다. ETF·ETN 수익률은 환율·보수·추적오차·롤오버의 영향을 받습니다."}
                </div>
            </section>

            <section style={card}>
                <b>가격 맥락</b>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(118px,1fr))", gap: 8, marginTop: 12 }}>
                    {stat("1개월", fmtPct(returns.month), history.length >= 22 ? "22관측 기준" : "가용 관측 기준")}
                    {stat("3개월", fmtPct(returns.quarter), "66관측 기준")}
                    {stat("1년", fmtPct(returns.year), history.length + "관측")}
                    {stat("30일 최고종가", fmt(quote?.high_30d, 3))}
                    {stat("30일 최저종가", fmt(quote?.low_30d, 3))}
                    {stat("52주 범위", fmt(quote?.low_52w, 3) + "–" + fmt(quote?.high_52w, 3))}
                </div>
            </section>

            <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(250px,1fr))", gap: 14 }}>
                <div style={card}>
                    <b>거시 연결</b>
                    <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
                        {stat("원/달러", fmt(macro?.macro?.usd_krw?.value, 2), fmtPct(macro?.macro?.usd_krw?.change_pct))}
                        {stat("미국 10년물", fmt(macro?.macro?.us_10y?.value, 3) + "%", String(macro?.macro?.us_10y?.as_of || "기준일 확인 중"))}
                        {stat("VIX", fmt(macro?.macro?.vix?.value, 2), fmtPct(macro?.macro?.vix?.change_pct))}
                    </div>
                    {correlations.length ? <div style={{ marginTop: 12 }}>
                        <div style={{ color: C.faint, fontSize: 10.5, fontWeight: 750 }}>30일 상관 · {macro?.macro?.cross_asset_corr?.as_of}</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 7 }}>
                            {correlations.map(([key, val]) => <span key={key} style={{ background: C.field, borderRadius: 999, padding: "7px 9px", color: C.sub, fontSize: 11, fontWeight: 750 }}>{labelAsset(key)} {Number(val).toFixed(2)}</span>)}
                        </div>
                    </div> : null}
                </div>

                <div style={card}>
                    <b>다가오는 일정</b>
                    <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
                        {events.length ? events.map((event: any) => <div key={String(event.name) + String(event.date)}>
                            <div style={{ fontSize: 12.5, fontWeight: 800 }}>{event.name}</div>
                            <div style={{ color: C.faint, fontSize: 10.5, marginTop: 3 }}>{event.date} · D{Number(event.d_day) >= 0 ? "+" : ""}{event.d_day} · {event.source}</div>
                            <div style={{ color: C.sub, fontSize: 11.5, lineHeight: 1.5, marginTop: 3 }}>{event.impact}</div>
                        </div>) : <div style={{ color: C.faint, fontSize: 12 }}>연결된 일정을 확인 중입니다.</div>}
                    </div>
                </div>
            </section>

            <section style={card}>
                <b>무엇이 움직이나요?</b>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginTop: 12 }}>
                    {item.drivers.map((driver) => <span key={driver} style={{ borderRadius: 999, background: C.field, padding: "8px 11px", color: C.sub, fontSize: 11.5, fontWeight: 750 }}>{driver}</span>)}
                </div>
                <div style={{ color: C.sub, fontSize: 12, marginTop: 12 }}>{item.calendar} · {item.related}</div>
            </section>

            <section style={card}>
                <b>국내 연결 기업</b>
                {exposureBlock ? <>
                    <div style={{ color: C.sub, fontSize: 11.5, lineHeight: 1.55, marginTop: 8 }}>{exposureBlock.note}</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginTop: 12 }}>
                        {(exposureBlock.stocks || []).slice(0, 8).map((stock: any) => <a key={stock.ticker} href={"/stock?q=" + encodeURIComponent(stock.ticker)} style={{ borderRadius: 999, background: C.field, padding: "8px 10px", color: C.sub, fontSize: 11.5, fontWeight: 750, textDecoration: "none" }}>{stock.name} · {stock.ticker}</a>)}
                    </div>
                    <div style={{ color: C.faint, fontSize: 10, marginTop: 10 }}>산업 분류상 연결 {Number(exposureBlock.count || 0).toLocaleString("ko-KR")}개 · 수혜·추천이 아닌 원가·매출 연관 정보</div>
                </> : <div style={{ color: C.faint, fontSize: 12, marginTop: 10 }}>공개 산업 매핑은 아직 준비되지 않았습니다.</div>}
            </section>

            <section style={card}>
                <b>읽는 순서</b>
                <div style={{ marginTop: 11, display: "grid", gap: 8, color: C.sub, fontSize: 12.5, lineHeight: 1.6 }}>
                    <div>1. 통화·단위·기준시각과 연속물 여부를 확인해요.</div>
                    <div>2. 1개월·3개월·1년 수익률과 52주 범위를 함께 봐요.</div>
                    <div>3. 달러·금리·VIX와의 동행 여부를 확인해요.</div>
                    <div>4. 국내 연결 기업은 원가와 매출 중 어느 쪽인지 직접 확인해요.</div>
                </div>
            </section>
        </main>
    </div>
}

addPropertyControls(PublicCommodityReport, {
    macroUrl: { type: ControlType.String, title: "Macro URL", defaultValue: DEFAULT_MACRO },
    exposureUrl: { type: ControlType.String, title: "Exposure URL", defaultValue: DEFAULT_EXPOSURE },
    previewTicker: { type: ControlType.Enum, title: "Preview", options: COMMODITIES.map((item) => item.ticker), optionTitles: COMMODITIES.map((item) => item.name), defaultValue: "CMD_GOLD" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState } from "react"
import PublicStockSearch from "https://framer.com/m/PublicStockSearch-iqt9J1.js"

/** 직접 원자재 교육형 리포트. CMD_* 검색 진입에서만 표시한다. */
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_MACRO = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/macro_snapshot.json"
const SEARCH_UNIVERSE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
const US_REPORT = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json"
const LIGHT = { card: "#fff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", field: "#f2f4f6", blue: "#3182f6", blueS: "#e8f1fe", red: "#f04452", shadow: "rgba(0,0,0,.05)" }
const DARK = { card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", field: "#222831", blue: "#5b9bff", blueS: "#16233a", red: "#f05b67", shadow: "rgba(0,0,0,.24)" }
const P = "cmdrep"
const PALETTE = "body{" + Object.keys(LIGHT).map((key) => `--an-${P}-${key}:${(LIGHT as any)[key]}`).join(";") + "}" + 'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((key) => `--an-${P}-${key}:${(DARK as any)[key]}`).join(";") + "}"
const C: Record<string, string> = {}
for (const key of Object.keys(LIGHT)) C[key] = `var(--an-${P}-${key})`

type Commodity = { ticker: string; name: string; symbol: string; group: string; unit: string; exchange: string; macroKey?: string; drivers: string[]; calendar: string; related: string }
const COMMODITIES: Commodity[] = [
    { ticker: "CMD_GOLD", name: "금", symbol: "GC=F", group: "귀금속", unit: "USD/트로이온스", exchange: "COMEX", macroKey: "gold", drivers: ["달러", "실질금리", "중앙은행 수요"], calendar: "미국 물가·고용·연준 일정", related: "금광·귀금속 ETF" },
    { ticker: "CMD_SILVER", name: "은", symbol: "SI=F", group: "귀금속", unit: "USD/트로이온스", exchange: "COMEX", macroKey: "silver", drivers: ["달러", "태양광·산업 수요", "금 가격"], calendar: "미국 물가·제조업 지표", related: "은광·귀금속 ETF" },
    { ticker: "CMD_COPPER", name: "구리", symbol: "HG=F", group: "산업금속", unit: "USD/파운드", exchange: "COMEX", macroKey: "copper", drivers: ["중국 경기", "재고", "전력망·건설 수요"], calendar: "중국 PMI·LME 재고", related: "비철금속·전선·구리 ETF" },
    { ticker: "CMD_WTI", name: "WTI 원유", symbol: "CL=F", group: "에너지", unit: "USD/배럴", exchange: "NYMEX", macroKey: "wti_oil", drivers: ["OPEC+", "미국 원유 재고", "지정학"], calendar: "EIA 주간 원유재고·OPEC 일정", related: "정유·항공·석유화학" },
    { ticker: "CMD_BRENT", name: "브렌트유", symbol: "BZ=F", group: "에너지", unit: "USD/배럴", exchange: "ICE", drivers: ["OPEC+", "유럽·아시아 수요", "지정학"], calendar: "OPEC 월간보고서·IEA 보고서", related: "글로벌 에너지·운송" },
    { ticker: "CMD_NATGAS", name: "천연가스", symbol: "NG=F", group: "에너지", unit: "USD/MMBtu", exchange: "NYMEX", drivers: ["기온", "저장량", "LNG 수출"], calendar: "EIA 주간 천연가스 저장량", related: "가스·발전·비료" },
    { ticker: "CMD_CORN", name: "옥수수", symbol: "ZC=F", group: "농산물", unit: "USD/부셸", exchange: "CBOT", drivers: ["미국·브라질 작황", "에탄올 수요", "날씨"], calendar: "USDA WASDE·주간 작황", related: "사료·식품·에탄올" },
    { ticker: "CMD_WHEAT", name: "밀", symbol: "ZW=F", group: "농산물", unit: "USD/부셸", exchange: "CBOT", drivers: ["흑해 수출", "작황", "재고"], calendar: "USDA WASDE·수출 검사", related: "제분·식품" },
    { ticker: "CMD_SOYBEAN", name: "대두", symbol: "ZS=F", group: "농산물", unit: "USD/부셸", exchange: "CBOT", drivers: ["중국 수입", "남미 작황", "대두유 수요"], calendar: "USDA WASDE·수출 판매", related: "사료·식용유" },
    { ticker: "CMD_COFFEE", name: "커피", symbol: "KC=F", group: "농산물", unit: "USD/파운드", exchange: "ICE", drivers: ["브라질·베트남 작황", "기온", "재고"], calendar: "ICE 재고·주요 생산국 수확", related: "음료·식품" },
    { ticker: "CMD_SUGAR", name: "설탕", symbol: "SB=F", group: "농산물", unit: "USD/파운드", exchange: "ICE", drivers: ["브라질 생산", "에탄올 전환", "인도 수출"], calendar: "주요 생산국 생산·수출 발표", related: "식품·음료" },
    { ticker: "CMD_COTTON", name: "면화", symbol: "CT=F", group: "농산물", unit: "USD/파운드", exchange: "ICE", drivers: ["미국 작황", "중국 섬유 수요", "재고"], calendar: "USDA 면화 수급·주간 작황", related: "섬유·의류" },
]
const BY_TICKER = new Map(COMMODITIES.map((item) => [item.ticker, item]))
interface Props { macroUrl: string; previewTicker: string; dark: boolean }

function readTicker(previewTicker: string, onCanvas: boolean) {
    if (onCanvas) return previewTicker || "CMD_GOLD"
    if (typeof window === "undefined") return ""
    return String(new URLSearchParams(window.location.search).get("q") || "").trim().toUpperCase()
}
function fmtTimestamp(value: unknown) {
    if (!value) return "기준시각 확인 중"
    const date = new Date(String(value))
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }) + " KST"
}

export default function PublicCommodityReport(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [ticker, setTicker] = useState(() => readTicker(props.previewTicker, onCanvas))
    const [macro, setMacro] = useState<any>(null)
    const item = useMemo(() => BY_TICKER.get(ticker), [ticker])
    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        const sync = () => setTicker(readTicker(props.previewTicker, false))
        window.addEventListener("verity-ticker-change", sync)
        window.addEventListener("popstate", sync)
        return () => { window.removeEventListener("verity-ticker-change", sync); window.removeEventListener("popstate", sync) }
    }, [onCanvas, props.previewTicker])
    useEffect(() => {
        if (!item) { setMacro(null); return }
        let alive = true
        fetch(props.macroUrl || DEFAULT_MACRO).then((response) => response.ok ? response.json() : null).then((data) => { if (alive) setMacro(data) }).catch(() => { if (alive) setMacro(null) })
        return () => { alive = false }
    }, [item?.ticker, props.macroUrl])
    if (!item) return null
    const quote = item.macroKey ? (macro?.macro?.[item.macroKey] || macro?.[item.macroKey]) : null
    const benchmark = macro?.commodity_benchmarks?.items?.[ticker]
    const benchmarkQuote = benchmark?.latest ? { value: benchmark.latest.value, change_pct: benchmark.change_pct, as_of: benchmark.latest.period, source: "World Bank Pink Sheet" } : null
    const displayQuote = quote || benchmarkQuote
    const usesBenchmark = !quote && Boolean(benchmarkQuote)
    const generatedAt = displayQuote?.as_of || macro?.collected_at || macro?._meta?.generated_at || macro?.generated_at
    const value = Number(displayQuote?.value), change = Number(displayQuote?.change_pct), source = String(displayQuote?.source || "출처 확인 중")
    const hasValue = Number.isFinite(value), hasChange = Number.isFinite(change)
    const displayUnit = usesBenchmark ? String(benchmark?.unit || "USD 기준") : item.unit
    const dataKind = usesBenchmark ? "월평균 기준선" : "선물 연속물"
    const dataNote = usesBenchmark ? "세계은행이 공개한 월평균 벤치마크입니다. 선물 현재가와 같은 값이 아니며, 실제 ETF·ETN 수익률은 환율·운용보수·추적오차의 영향을 받아요." : "지금 보고 있는 값은 특정 만기 계약이 아니라 여러 만기를 이어 만든 연속물입니다. 실제 ETF·ETN 수익률은 환율, 운용보수, 추적오차와 롤오버 영향으로 달라질 수 있어요."
    const card = { background: C.card, borderRadius: 20, padding: "18px clamp(16px,2.4vw,24px)", boxShadow: `0 8px 28px ${C.shadow}` }
    return <div style={{ width: "100%", padding: "0 clamp(14px, 2vw, 20px)", boxSizing: "border-box", fontFamily: FONT, color: C.ink }}><style>{PALETTE}</style><main style={{ maxWidth: 1100, margin: "0 auto", display: "grid", gap: 14 }}>
        <div style={{ width: "100%", height: 41, minWidth: 0 }}><PublicStockSearch placeholder="종목·ETF·원자재 검색" stockPath="/stock" stockUrl={SEARCH_UNIVERSE} usStockUrl={US_REPORT} dark={props.dark} reportStyle={true} /></div>
        <section style={card}><div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}><div><div style={{ color: C.blue, fontSize: 12, fontWeight: 850 }}>{item.group} · {dataKind}</div><h1 style={{ margin: "5px 0 0", fontSize: 25, letterSpacing: "-.6px" }}>{item.name}</h1><div style={{ color: C.faint, fontSize: 12, fontWeight: 700, marginTop: 5 }}>{usesBenchmark ? String(benchmark?.benchmark || item.name) : item.symbol} · {usesBenchmark ? "World Bank" : item.exchange} · {displayUnit}</div></div><div style={{ textAlign: "right" }}>{hasValue ? <><div style={{ fontSize: 25, fontWeight: 900 }}>{value.toLocaleString("ko-KR", { maximumFractionDigits: 3 })}</div>{hasChange ? <div style={{ marginTop: 4, color: change > 0 ? C.red : change < 0 ? C.blue : C.sub, fontSize: 13, fontWeight: 850 }}>{change > 0 ? "+" : ""}{change.toFixed(2)}%</div> : null}</> : <div style={{ color: C.faint, fontSize: 12, fontWeight: 750 }}>가격 데이터 미연결</div>}<div style={{ color: C.faint, fontSize: 10.5, marginTop: 5 }}>{source} · {usesBenchmark ? String(generatedAt || "최신월 확인 중") : fmtTimestamp(generatedAt)} · {usesBenchmark ? "월간" : "지연 가능"}</div></div></div><div style={{ marginTop: 16, borderRadius: 16, background: C.blueS, padding: "13px 15px", color: C.sub, fontSize: 12.5, lineHeight: 1.65, fontWeight: 650 }}>{dataNote}</div></section>
        <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 14 }}><div style={card}><b>무엇이 움직이나요?</b><div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginTop: 12 }}>{item.drivers.map((driver) => <span key={driver} style={{ borderRadius: 999, background: C.field, padding: "8px 11px", color: C.sub, fontSize: 11.5, fontWeight: 750 }}>{driver}</span>)}</div></div><div style={card}><b>중요 일정</b><p style={{ margin: "10px 0 0", color: C.sub, fontSize: 12.5, lineHeight: 1.65 }}>{item.calendar}</p></div><div style={card}><b>관련 자산</b><p style={{ margin: "10px 0 0", color: C.sub, fontSize: 12.5, lineHeight: 1.65 }}>{item.related}</p><div style={{ color: C.faint, fontSize: 11, lineHeight: 1.55 }}>매출과 원가 중 어느 쪽에 연결되는지도 확인하세요.</div></div></section>
        <section style={card}><b>읽는 순서</b><div style={{ marginTop: 11, display: "grid", gap: 8, color: C.sub, fontSize: 12.5, lineHeight: 1.6 }}><div>1. 가격의 통화·단위·기준시각을 확인해요.</div><div>2. 현물인지 선물 연속물인지 확인해요.</div><div>3. 선물 곡선과 롤오버 영향을 확인해요.</div><div>4. ETF·ETN은 환율·보수·추적오차를 따로 비교해요.</div></div></section>
    </main></div>
}
addPropertyControls(PublicCommodityReport, { macroUrl: { type: ControlType.String, title: "Macro URL", defaultValue: DEFAULT_MACRO }, previewTicker: { type: ControlType.Enum, title: "Preview", options: COMMODITIES.map((item) => item.ticker), optionTitles: COMMODITIES.map((item) => item.name), defaultValue: "CMD_GOLD" }, dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false } })

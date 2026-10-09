import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState } from "react"

/**
 * 국민연금(NPS) 보유종목 + 운용현황 — 공개 probe.
 *
 * "국민연금이 어디에 투자하나 / 수익은 얼마나" 를 공시 사실로 한 화면에.
 * 🚨 점수·추천 없음. 지분율·수익률 = 공시 사실 (RULE 7).
 *
 * 데이터 = data/nps_holdings.json (DART 5% 대량보유 공시 + data.go.kr 국민연금 대량보유).
 *   한계 = 5% 이상 보유 기준(전체 ~1,200종목 아님) · 분기 지연. 컴포넌트가 라벨로 명시.
 *
 * 다크모드 = body[data-framer-theme] 자가감지. 회사명 누르면 리포트(reportPath?q=ticker).
 * 🚨 면책 문구 제거(2026-06-26, PM) — "점수·추천 아님 / 판단은 직접" 류는 사이트 하단 단일 면책으로 통합. 출처·데이터 한계(전체 아님·분기지연)는 유지.
 */

const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"

// 되돌리지 말 것: 공개 JSON의 연간 필드가 없어도 확인한 과거 공시로 그래프를 표시한다.
// 2025년 말까지의 공식 기록. 새 연간 데이터가 발행되면 원격 자료를 우선한다.
const VERIFIED_ANNUAL_RETURNS: any = {
    as_of: "2025-12-31",
    source: "국민연금기금운용본부 성과 현황 공시 (fund.nps.or.kr)",
    source_url: "https://fund.nps.or.kr/oprtprcn/oprtotcm/getOHED0011M0.do",
    annual: [
        { year: 1988, return_pct: 11.98, profit_bil: 27.1 },
        { year: 1989, return_pct: 12.79, profit_bil: 108.5 },
        { year: 1990, return_pct: 12.55, profit_bil: 213.6 },
        { year: 1991, return_pct: 12.76, profit_bil: 348 },
        { year: 1992, return_pct: 12.68, profit_bil: 507.4 },
        { year: 1993, return_pct: 11.99, profit_bil: 725 },
        { year: 1994, return_pct: 12.12, profit_bil: 1141.8 },
        { year: 1995, return_pct: 11.81, profit_bil: 1576.7 },
        { year: 1996, return_pct: 10.55, profit_bil: 1973.9 },
        { year: 1997, return_pct: 8.84, profit_bil: 2187.3 },
        { year: 1998, return_pct: 14.41, profit_bil: 4635.6 },
        { year: 1999, return_pct: 12.8, profit_bil: 5324 },
        { year: 2000, return_pct: 5.87, profit_bil: 3205.5 },
        { year: 2001, return_pct: 9.01, profit_bil: 6069.2 },
        { year: 2002, return_pct: 7.67, profit_bil: 6497.6 },
        { year: 2003, return_pct: 7.03, profit_bil: 7203.8 },
        { year: 2004, return_pct: 8.28, profit_bil: 10311.5 },
        { year: 2005, return_pct: 5.63, profit_bil: 8256.3 },
        { year: 2006, return_pct: 5.77, profit_bil: 10129 },
        { year: 2007, return_pct: 6.79, profit_bil: 13718.9 },
        { year: 2008, return_pct: -0.18, profit_bil: -419.1 },
        { year: 2009, return_pct: 10.39, profit_bil: 26246.2 },
        { year: 2010, return_pct: 10.37, profit_bil: 30105.8 },
        { year: 2011, return_pct: 2.31, profit_bil: 7671.7 },
        { year: 2012, return_pct: 6.99, profit_bil: 24991.6 },
        { year: 2013, return_pct: 4.19, profit_bil: 16651.3 },
        { year: 2014, return_pct: 5.25, profit_bil: 23032.6 },
        { year: 2015, return_pct: 4.57, profit_bil: 21741.4 },
        { year: 2016, return_pct: 4.75, profit_bil: 24543.9 },
        { year: 2017, return_pct: 7.26, profit_bil: 41194.1 },
        { year: 2018, return_pct: -0.92, profit_bil: -5867.1 },
        { year: 2019, return_pct: 11.31, profit_bil: 73424.7 },
        { year: 2020, return_pct: 9.7, profit_bil: 72143.7 },
        { year: 2021, return_pct: 10.77, profit_bil: 91214.4 },
        { year: 2022, return_pct: -8.22, profit_bil: -79551.8 },
        { year: 2023, return_pct: 13.59, profit_bil: 126715.3 },
        { year: 2024, return_pct: 15, profit_bil: 159711.5 },
        {
            year: 2025,
            return_pct: 18.82,
            profit_bil: 231634.3,
            provisional: false,
        },
    ],
    cumulative_avg_pct: 8.04,
    cumulative_profit_bil: 969345,
    year_context: {
        "2020": {
            kind: "largest_asset_profit",
            label: "공식 수익금 최대 자산군",
            asset: "국내주식",
            profit_bil: 46860,
            period: "2020-01-01/2020-12-31",
            source_url:
                "https://www.nps.or.kr/html/download/obligation/2021_NPS_SR_KOR.pdf#page=6",
            source_title: "2021 지속가능경영보고서 · 7쪽",
            summary:
                "공단 설명: 경기부양책과 기업 실적 개선 속에서 국내 주식시장이 반등했어요.",
            asset_profits_bil: {
                국내주식: 46860,
                해외주식: 18448.2,
                국내채권: 5376.2,
                해외채권: -573.1,
                대체투자: 2107.9,
                단기자금: -1.7,
            },
        },
        "2021": {
            kind: "largest_asset_profit",
            label: "공식 수익금 최대 자산군",
            asset: "해외주식",
            profit_bil: 58493.2,
            period: "2021-01-01/2021-12-31",
            source_url:
                "https://www.nps.or.kr/html/download/obligation/2022_NPS_SR_KOR.pdf#page=31",
            source_title: "2022 지속가능경영보고서 · 58쪽",
            summary:
                "공단 설명: 세계 증시 강세와 원·달러 환율 상승이 해외주식 성과에 도움을 줬어요.",
            asset_profits_bil: {
                국내주식: 10974.6,
                해외주식: 58493.2,
                국내채권: -4344.8,
                해외채권: 3721.8,
                대체투자: 22417.4,
                단기자금: 46.7,
            },
        },
        "2024": {
            kind: "largest_asset_profit",
            label: "공식 수익금 최대 자산군",
            asset: "해외주식",
            profit_bil: 112096.9,
            period: "2024-01-01/2024-12-31",
            source_url:
                "https://fund.nps.or.kr/fileDown.do?atchFileId=FL25002684&atchFileSn=1#page=15",
            source_title: "2024 기금운용보고서 · 13쪽",
            summary:
                "공단 설명: 기술주 강세와 원·달러 환율 상승이 해외자산의 원화 수익에 도움을 줬어요.",
            asset_profits_bil: {
                국내주식: -10240,
                해외주식: 112096.9,
                국내채권: 17611.5,
                해외채권: 13309.3,
                대체투자: 29535,
                단기자금: 262.6,
            },
        },
        "2025": {
            kind: "largest_asset_profit",
            label: "공식 수익금 최대 자산군",
            asset: "국내주식",
            profit_bil: 119411,
            period: "2025-01-01/2025-12-31",
            note: "공단의 자산군별 수익금입니다. 개별 종목별 성과 기여도는 공시하지 않습니다.",
        },
    },
    note: "연도별 전체 수익률은 1988~2025년 말 공식 공시값입니다. 자산군별 수익금은 2020·2021·2024·2025년을 확인했으며, 연도별 개별 종목 수익 기여도는 공식 미공개입니다.",
}
const VERIFIED_HIGHLIGHT = {
    kind: "highest_asset_return",
    label: "수익률 최고 자산군",
    asset: "국내주식",
    return_pct: 107.37,
    period: "2026-01-01/2026-06-30",
    provisional: true,
    note: "공단 공시의 자산군별 금액가중수익률입니다. 기금 전체 수익금 기여도나 개별 종목 기여도와는 다릅니다.",
}

const LIGHT = {
    bg: "#f2f4f6",
    card: "#ffffff",
    ink: "#191f28",
    sub: "#4e5968",
    faint: "#8b95a1",
    line: "#e5e8eb",
    up: "#f04452",
    down: "#3182f6",
    blue: "#3182f6",
    blueSoft: "#eef4ff",
    green: "#15c47e",
    greenSoft: "#eafaf3",
    accent: "#6c5ce7",
}
const DARK = {
    // 배경/카드/잉크 = 공시 피드·사이트 PageBg/NavBg 와 통일 (2026-06-22)
    bg: "#0f1318",
    card: "#171c23",
    ink: "#e3e7ec",
    sub: "#9aa4b1",
    faint: "#828d9b",
    line: "#252b34",
    up: "#ff6b76",
    down: "#5a9cff",
    blue: "#5a9cff",
    blueSoft: "#1b2740",
    green: "#3ddc97",
    greenSoft: "#16322a",
    accent: "#a99bff",
}

function readBodyDark(): boolean {
    try {
        if (typeof document !== "undefined") {
            const h = document.documentElement
                ? document.documentElement.dataset.anTheme
                : null
            if (h === "dark") return true
            if (h === "light") return false
            if (document.body) {
                const a = document.body.dataset.framerTheme
                if (a === "dark") return true
                if (a === "light") return false
            }
        }
        const s =
            typeof localStorage !== "undefined"
                ? localStorage.getItem("verity_theme")
                : null
        if (s === "dark") return true
    } catch (e) {}
    return false
}

function fmtPct(v: any): string {
    const n = Number(v)
    if (!isFinite(n)) return "—"
    return n.toFixed(2) + "%"
}

const DEMO = {
    coverage: "operating_pool",
    count: 3,
    source: "DART 5% 대량보유 공시",
    note: "국민연금 5% 이상 대량보유 공시 기준 — 전체 보유종목 아님 · 분기 지연.",
    fund: {
        as_of: "2026-03-31",
        aum_krw_trillion: 1526.1,
        return_total_pct: 18.82,
        return_total_note: "2025년 전체(잠정)",
        return_cumulative_annualized_pct: 8.04,
        asset_returns_pct: {
            국내주식: 8.24,
            해외주식: 19.74,
            국내채권: 0.84,
            해외채권: 3.77,
            대체투자: 8.03,
        },
        current_highlight: {
            kind: "highest_asset_return",
            label: "수익률 최고 자산군",
            asset: "국내주식",
            return_pct: 107.37,
            period: "2026-01-01/2026-06-30",
            provisional: true,
        },
        annual_returns: {
            cumulative_avg_pct: 8.04,
            cumulative_profit_bil: 969345,
            annual: [
                { year: 2020, return_pct: 9.7 },
                { year: 2021, return_pct: 10.77 },
                { year: 2022, return_pct: -8.22 },
                { year: 2023, return_pct: 13.59 },
                { year: 2024, return_pct: 15.0 },
                { year: 2025, return_pct: 18.82 },
            ],
            year_context: {
                "2025": {
                    kind: "largest_asset_profit",
                    label: "공식 수익금 최대 자산군",
                    asset: "국내주식",
                    profit_bil: 119411,
                    note: "개별 종목별 성과 기여도는 공시하지 않습니다.",
                },
            },
        },
        source: "국민연금기금운용본부 운용현황 공시",
    },
    holdings: [
        {
            ticker: "017960",
            name: "한국카본",
            pct: 10.49,
            qty_change: 521052,
            date: "2026-04-01",
            src: "DART majorstock",
        },
        {
            ticker: "375500",
            name: "DL이앤씨",
            pct: 8.06,
            qty_change: -120000,
            date: "2026-03-20",
            src: "DART majorstock",
        },
        {
            ticker: "000270",
            name: "기아",
            pct: 6.61,
            qty_change: 0,
            date: "2026-02-14",
            src: "DART majorstock",
        },
    ],
}

// 되돌리지 말 것: 접수일은 매매일이 아니며, 공시 사이 실제 지분·매매단가·평단을 추정하지 않는다.
function npsNumber(value: any): number | null {
    if (value == null || value === "" || typeof value === "boolean") return null
    const n = Number(String(value).replace(/,/g, ""))
    return Number.isFinite(n) ? n : null
}

function npsDate(value: any): string {
    const s = String(value || "")
    return /^\d{8}$/.test(s) ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6)}` : s.slice(0, 10)
}

function NpsHistoryPanel({ history, isDark }: { history: any; isDark: boolean }) {
    const [query, setQuery] = useState("")
    const [ticker, setTicker] = useState("")
    const [period, setPeriod] = useState("all")
    const stocks: any[] = Array.isArray(history?.stocks) ? history.stocks : []
    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase()
        return stocks.filter((s: any) => `${s.name} ${s.ticker}`.toLowerCase().includes(q))
    }, [stocks, query])
    const selected = filtered.find((s: any) => s.ticker === ticker) || filtered[0] || null
    const events = useMemo(() => {
        const cutoff = new Date()
        cutoff.setUTCFullYear(cutoff.getUTCFullYear() - Number(period === "all" ? 100 : period))
        const from = cutoff.toISOString().slice(0, 10)
        return (Array.isArray(selected?.events) ? selected.events : [])
            .filter((e: any) => /^\d{4}-\d{2}-\d{2}$/.test(npsDate(e.filed_at)) && (period === "all" || npsDate(e.filed_at) >= from))
            .slice().sort((a: any, b: any) => npsDate(a.filed_at).localeCompare(npsDate(b.filed_at)) || String(a.rcept_no).localeCompare(String(b.rcept_no)))
    }, [selected, period])
    const points = events.filter((e: any) => npsNumber(e.pct) != null && npsNumber(e.pct)! >= 0)
    const correctionUnverified = Boolean(selected?.observed_pct?.correction_links_unverified) || events.some((e: any) => e.is_correction)
    const highest = correctionUnverified ? null : points.reduce((best: any, e: any) => !best || npsNumber(e.pct)! > npsNumber(best.pct)! ? e : best, null)
    const lowest = correctionUnverified ? null : points.reduce((best: any, e: any) => !best || npsNumber(e.pct)! < npsNumber(best.pct)! ? e : best, null)
    const latest = points[points.length - 1]
    const firstDate = npsDate(events[0]?.filed_at)
    const lastDate = npsDate(events[events.length - 1]?.filed_at)
    const formatPct = (v: any) => npsNumber(v) == null ? "—" : npsNumber(v)!.toFixed(2) + "%"
    const covered = stocks.filter((s: any) => Array.isArray(s.events) && s.events.length > 0).length
    const selectionDate = history?.selection?.as_of || selected?.selection_as_of || "기준일 미확인"
    const css = `.nps-history{--nh-ink:${isDark ? "#e3e7ec" : "#191f28"};--nh-sub:${isDark ? "#9aa4b1" : "#6b7684"};--nh-card:${isDark ? "#171c23" : "#ffffff"};--nh-stack:${isDark ? "#1d242c" : "#f8f9fb"};--nh-hover:${isDark ? "#252c35" : "#f1f3f5"};--nh-focus:${isDark ? "#303945" : "#e9edf2"};--nh-accent:${isDark ? "#a99bff" : "#6c5ce7"};background:var(--nh-card);color:var(--nh-ink);padding:20px;border-radius:20px;margin:12px 0;font-size:13px;font-weight:600;line-height:1.65;container-type:inline-size}
.nps-history *{box-sizing:border-box}.nps-history h3{font-size:20px;font-weight:800;margin:0}.nps-history p{margin:4px 0;color:var(--nh-sub)}.nps-history .nh-badge{font-size:11px;color:var(--nh-accent);font-weight:700}.nps-history .nh-controls{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:16px 0}.nps-history label{display:grid;gap:5px;color:var(--nh-sub);font-size:12px;font-weight:700}.nps-history :is(input,select,button,a){font-family:inherit;font-weight:700;font-size:13px;border:0;text-decoration:none;outline:none;transition:background-color .16s ease,color .16s ease;box-shadow:none}.nps-history :is(input,select){width:100%;height:44px;min-width:0;color:var(--nh-ink);background:var(--nh-stack);border-radius:12px;padding:10px 12px}.nps-history select{appearance:none;padding-right:36px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%236b7684' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center}.nps-history .nh-periods{display:flex;gap:6px;margin:12px 0}.nps-history button{min-height:44px;padding:8px 12px;border-radius:10px;color:var(--nh-sub);background:var(--nh-stack);cursor:pointer}.nps-history button[aria-pressed=true]{color:white;background:#6c5ce7}.nps-history :is(input,select,button,a,summary):focus-visible{background-color:var(--nh-focus)}.nps-history button[aria-pressed=true]:focus-visible{background:#6c5ce7;outline:2px solid var(--nh-sub);outline-offset:2px}.nps-history .nh-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.nps-history .nh-metric{padding:12px;border-radius:14px;background:var(--nh-stack)}.nps-history .nh-metric span{color:var(--nh-sub);font-size:11px}.nps-history .nh-metric b{display:block;font-size:22px;font-weight:800;line-height:1.5;font-variant-numeric:tabular-nums}.nps-history small{display:block;color:var(--nh-sub);font-size:11px;font-weight:600}.nps-history .nh-chart{padding:16px 0 8px}.nps-history .nh-chart svg{display:block;width:100%;height:130px}.nps-history .nh-dates{display:flex;justify-content:space-between;font-size:11px;color:var(--nh-sub)}.nps-history .nh-summary{padding:12px;border-radius:14px;background:var(--nh-stack);margin:12px 0}.nps-history .nh-summary strong{font-weight:800}.nps-history .nh-events{display:grid;gap:8px}.nps-history .nh-event{background:var(--nh-stack);padding:12px;border-radius:14px}.nps-history .nh-event-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.nps-history .nh-event-head b{font-weight:800;font-variant-numeric:tabular-nums}.nps-history .nh-event p{margin:4px 0;overflow-wrap:anywhere}.nps-history a{display:inline-flex;min-height:44px;align-items:center;padding:6px 10px;border-radius:10px;color:var(--nh-accent)}.nps-history details>summary{padding:10px 12px;min-height:44px;border-radius:12px;cursor:pointer;font-weight:700;list-style:none}.nps-history details>summary::-webkit-details-marker{display:none}.nps-history .nh-empty{padding:20px 12px;border-radius:14px;background:var(--nh-stack);margin:12px 0;color:var(--nh-sub)}@media(hover:hover){.nps-history :is(button:not([aria-pressed=true]),a,summary,select):hover{background-color:var(--nh-hover)}}@media(prefers-reduced-motion:reduce){.nps-history :is(input,select,button,a){transition:none}}@container(max-width:440px){.nps-history .nh-controls{grid-template-columns:1fr}.nps-history .nh-metric{padding:10px}.nps-history .nh-metric b{font-size:18px}}`
    const renderEvent = (e: any) => {
        const qtyChange = npsNumber(e.qty_change)
        const pctChange = npsNumber(e.pct_change_pp)
        const source = /^\d{14}$/.test(String(e.rcept_no)) ? `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${e.rcept_no}` : ""
        return <article className="nh-event" key={e.rcept_no}>
            <div className="nh-event-head"><span>공시 접수 {npsDate(e.filed_at)}</span><b>{formatPct(e.pct)}</b></div>
            <p>{qtyChange == null ? "보유 수량 증감 미확인" : qtyChange > 0 ? `보유 수량 ${qtyChange.toLocaleString()}주 증가` : qtyChange < 0 ? `보유 수량 ${Math.abs(qtyChange).toLocaleString()}주 감소` : "보유 수량 변동 없음"}{pctChange != null ? ` · 지분 ${pctChange > 0 ? "+" : ""}${pctChange.toFixed(2)}%p` : ""}</p>
            {npsNumber(e.qty) != null && <small>보고 보유 수량 {npsNumber(e.qty)!.toLocaleString()}주</small>}
            <small>{e.as_of ? `보유 기준일 ${npsDate(e.as_of)}` : "보유 기준일: 원문 확인 전 · 접수일은 매매일이 아니에요"}</small>
            {e.reason && <p>{e.reason}</p>}
            {e.is_correction && <small>정정 공시 · 이전 공시와의 연결은 확인 전이에요.</small>}
            {source && <a href={source} target="_blank" rel="noopener noreferrer">공시 원문 ↗</a>}
        </article>
    }
    return <section className="nps-history" aria-label="국민연금 종목별 공시 이력">
        <style>{css}</style>
        <span className="nh-badge">공개 평가액 상위 {history?.selection?.limit || 100}종목</span>
        <h3>이 기업의 지분은 어떻게 바뀌었을까요?</h3>
        <p>{selectionDate} 연말 보유 평가액 기준 · 현재 순위가 아니에요</p>
        <small>이력 확인 {covered}/{history?.selection?.limit || 100}종목 · 공시 이력이 없는 종목도 대상에서 제외하지 않아요.</small>
        {history?.selection?.annual_top100_unmatched_n > 0 && <small>종목코드 연결 확인 중 {history.selection.annual_top100_unmatched_n}개 · 하위 종목으로 대체하지 않아요.</small>}
        {stocks.length ? <>
            <div className="nh-controls">
                <label>기업 찾기<input type="search" aria-label="국민연금 상세 종목 검색" placeholder="종목명·코드 검색" value={query} onChange={(e) => setQuery(e.target.value)} /></label>
                <label>기업 선택<select aria-label="국민연금 상세 종목 선택" value={selected?.ticker || ""} onChange={(e) => setTicker(e.target.value)}>{filtered.length ? filtered.map((s: any) => <option value={s.ticker} key={s.ticker}>{s.rank} · {s.name}</option>) : <option value="">검색 결과 없음</option>}</select></label>
            </div>
            {selected ? <>
                <strong style={{ fontSize: 16, fontWeight: 800 }}>{selected.name} <span style={{ fontSize: 12, color: "var(--nh-sub)" }}>{selected.ticker}</span></strong>
                <small>선정 당시 지분 {formatPct(selected.selection_pct)} · 연말 평가액 약 {npsNumber(selected.eval_amt_100m)?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? "—"}억원</small>
                <div className="nh-periods" aria-label="공시 조회 기간">{[["all", "확보 이력"], ["3", "최근 3년"], ["1", "최근 1년"]].map(([v, label]) => <button type="button" key={v} aria-pressed={period === v} onClick={() => setPeriod(v)}>{label}</button>)}</div>
                {events.length ? <>
                    <div className="nh-metrics">{[["최근 확보 공시", latest], ["관측 최고 지분", highest], ["관측 최저 지분", lowest]].map(([label, e]: any) => <div className="nh-metric" key={label}><span>{label}</span><b>{formatPct(e?.pct)}</b><small>{e ? npsDate(e.filed_at) : correctionUnverified ? "정정 연결 확인 전" : "지분 미확인"}</small></div>)}</div>
                    {points.length > 1 && !correctionUnverified && (() => {
                        const min = Math.min(...points.map((e: any) => npsNumber(e.pct)!))
                        const max = Math.max(...points.map((e: any) => npsNumber(e.pct)!))
                        const start = Date.parse(npsDate(points[0].filed_at) + "T00:00:00Z")
                        const end = Date.parse(npsDate(points[points.length - 1].filed_at) + "T00:00:00Z")
                        const coords = points.map((e: any, i: number) => ({x: end > start ? 12 + (Date.parse(npsDate(e.filed_at) + "T00:00:00Z") - start) / (end - start) * 476 : 12 + i / (points.length - 1) * 476, y: max > min ? 112 - (npsNumber(e.pct)! - min) / (max - min) * 92 : 66, e}))
                        return <div className="nh-chart"><svg role="img" aria-label={`${selected.name} 공시 접수일 기준 보고 지분 변화`} viewBox="0 0 500 130"><polyline points={coords.map(p => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ")} stroke="var(--nh-accent)" strokeWidth="2" strokeDasharray="4 4" fill="none" />{coords.map(p => <circle key={p.e.rcept_no} cx={p.x} cy={p.y} r="3.5" fill="var(--nh-accent)"><title>{npsDate(p.e.filed_at)} 접수 · {formatPct(p.e.pct)}</title></circle>)}</svg><div className="nh-dates"><span>{firstDate}</span><span>{lastDate}</span></div><small>접수일 기준 공시값이에요. 점 사이의 실제 지분과 매매 시점은 확인되지 않았어요.</small></div>
                    })()}
                    <div className="nh-summary"><strong>확보한 공시 {events.length}건에서 확인했어요</strong><small>{firstDate}~{lastDate} 접수 · {correctionUnverified ? "정정 연결을 확인할 때까지 최고·최저 비교를 보류해요." : "최고·최저는 이 범위의 보고값이며 역대 기록이나 매매 가격이 아니에요."}</small>{selected.status !== "ok" && selected.status !== "success" && selected.last_success_at && <small>마지막 확인 {npsDate(selected.last_success_at)} · 기존에 수집한 이력을 표시해요.</small>}</div>
                    <div className="nh-events">{events.slice(-3).reverse().map(renderEvent)}</div>
                    {events.length > 3 && <details style={{ marginTop: 8 }}><summary>이전 공시 {events.length - 3}건 보기</summary><div className="nh-events">{events.slice(0, -3).reverse().map(renderEvent)}</div></details>}
                </> : <div className="nh-empty">{selected.missing_reason === "corp_code_missing" ? "이 종목과 공시 발행사를 아직 연결하지 못했어요." : selected.status === "not_collected" && !selected.last_success_at ? "이 종목의 공시 이력은 아직 수집 전이에요." : selected.status === "error" || selected.status === "stale" ? "공시 이력을 확보하지 못했어요. 기존에 확보한 자료는 유지해요." : "이 기간에 확보한 국민연금 공시가 없어요."}{selected.missing_reason === "corp_code_missing" && <small>우선주 등 개별 주식종류의 지분을 발행사 전체 지분으로 대신하지 않아요.</small>}<small>공시 없음은 미보유·전량 매도를 뜻하지 않아요.</small></div>}
            </> : <div className="nh-empty">검색 결과가 없어요. 다른 이름이나 종목 코드를 입력해 주세요.</div>}
        </> : <div className="nh-empty">상세 공시 이력을 아직 불러오지 못했어요. 아래 기본 보유 정보는 계속 볼 수 있어요.</div>}
        <small style={{ marginTop: 14 }}>공시상 보유 변화만 보여드려요. 첫 공시는 첫 매수일이 아니고, 지분 감소를 실제 매도로 단정하지 않아요. 매매 단가·평단은 추정하지 않아요.</small>
    </section>
}

export default function PublicNPSHoldings(props: {
    width?: number
    dark?: boolean
    dataUrl?: string
    reportPath?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() =>
        RenderTarget.current() === RenderTarget.canvas
            ? !!props.dark
            : readBodyDark()
    )
    // 국민연금공단 로고 — 파비콘 핫링크 + 실패 시 NPS 배지. 🚨 훅은 조건부 return 위 (framer_hooks_top_level — 스켈레톤 return 뒤에 두면 라이브 크래시, 2026-07-07 실사고)
    const [logoErr, setLogoErr] = useState(false)
    // 내 종목 교집합 (PM 2026-07-07) — 관심 = localStorage(로그인 불요) / 보유 = /api/holdings(로그인 시)
    const [myWatch, setMyWatch] = useState<Set<string>>(new Set())
    const [myHold, setMyHold] = useState<Set<string>>(new Set())
    // 그래프에서 선택한 연도. 종목 성과가 아닌 공시 범위의 자산군 성과만 보여 준다.
    const [selectedReturnYear, setSelectedReturnYear] = useState<number | null>(
        null
    )
    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        let alive = true
        const syncMine = () => {
            try {
                const raw = window.localStorage.getItem("verity_watchlist")
                const arr = raw ? JSON.parse(raw) : []
                if (alive && Array.isArray(arr))
                    setMyWatch(
                        new Set(
                            arr
                                .map((x: any) => String((x && x.ticker) || x))
                                .filter(Boolean)
                        )
                    )
            } catch (e) {
                /* ignore */
            }
            try {
                const sraw = window.localStorage.getItem(
                    "verity_supabase_session"
                )
                const sess = sraw ? JSON.parse(sraw) : null
                // 만료 토큰 = 미로그인 취급 (2026-07-14, getToken 동기) — 공개 페이지 refresh 부재로 만료 방치.
                const token =
                    sess &&
                    typeof sess.access_token === "string" &&
                    !(sess.expires_at && Date.now() / 1000 > sess.expires_at)
                        ? sess.access_token
                        : ""
                if (!token) {
                    if (alive) setMyHold(new Set())
                    return
                }
                fetch("https://project-yw131.vercel.app/api/holdings", {
                    headers: { Authorization: "Bearer " + token },
                })
                    .then((r) => (r.ok ? r.json() : null))
                    .then((d) => {
                        const hs = (d && (d.holdings || d.rows || d)) || []
                        if (alive && Array.isArray(hs))
                            setMyHold(
                                new Set(
                                    hs
                                        .map((x: any) =>
                                            String((x && x.ticker) || "")
                                        )
                                        .filter(Boolean)
                                )
                            )
                    })
                    .catch(() => {})
            } catch (e) {
                /* ignore */
            }
        }
        syncMine()
        // 로그인/로그아웃 재평가(verity_auth_change · 다른 탭 storage) — 리스너 없으면 로그인 후 "내 보유 겹침" 하이라이트가 재방문 전까지 미표시 (MorningBriefing 동일 버그 클래스, 2026-07-14).
        const onAuth = () => syncMine()
        window.addEventListener("verity_auth_change", onAuth)
        window.addEventListener("storage", onAuth)
        return () => {
            alive = false
            window.removeEventListener("verity_auth_change", onAuth)
            window.removeEventListener("storage", onAuth)
        }
    }, [onCanvas])
    const NpsLogo = () =>
        logoErr ? (
            <span
                style={{
                    width: 26,
                    height: 26,
                    borderRadius: 8,
                    background: "#0B5FAE",
                    color: "#fff",
                    fontSize: 10,
                    fontWeight: 800,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                }}
            >
                NPS
            </span>
        ) : (
            <img
                src="https://www.google.com/s2/favicons?domain=nps.or.kr&sz=64"
                alt="국민연금공단"
                width={26}
                height={26}
                onError={() => setLogoErr(true)}
                style={{
                    width: 26,
                    height: 26,
                    borderRadius: 8,
                    background: "#fff",
                    padding: 2,
                    boxSizing: "border-box",
                    display: "block",
                    flexShrink: 0,
                }}
            />
        )

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const [data, setData] = useState<any>(onCanvas ? DEMO : null)
    const [loading, setLoading] = useState<boolean>(!onCanvas)
    const [query, setQuery] = useState<string>("")
    const [npsAll, setNpsAll] = useState<boolean>(false) // 보유종목 더보기 토글

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (
            typeof MutationObserver === "undefined" ||
            typeof document === "undefined" ||
            !document.body
        )
            return
        const obs = new MutationObserver(read)
        obs.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-framer-theme"],
        })
        obs.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["data-an-theme"],
        })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const url = props.dataUrl || BLOB + "/nps_holdings.json"
        fetch(url)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive) {
                    setData(d)
                    setLoading(false)
                }
            })
            .catch(() => {
                if (alive) setLoading(false)
            })
        return () => {
            alive = false
        }
    }, [onCanvas, props.dataUrl])

    const holdings = useMemo(
        () => (data && Array.isArray(data.holdings) ? data.holdings : []),
        [data]
    )
    // 검색 필터 — 종목명·코드
    const shownHoldings = useMemo(() => {
        const q = query.trim().toLowerCase()
        if (!q) return holdings
        return holdings.filter(
            (h: any) =>
                String(h.name || "")
                    .toLowerCase()
                    .includes(q) ||
                String(h.ticker || "")
                    .toLowerCase()
                    .includes(q)
        )
    }, [holdings, query])
    // 더보기 — 검색 중이 아니고 미리보기 초과 시 접힘(너무 많은 종목 정리)
    const NPS_PREVIEW = 12
    const npsCollapsed =
        !npsAll && !query.trim() && shownHoldings.length > NPS_PREVIEW
    const displayHoldings = npsCollapsed
        ? shownHoldings.slice(0, NPS_PREVIEW)
        : shownHoldings
    const fund = data && data.fund ? data.fund : null
    // 별도 Blob이 아니라 nps_holdings의 공식 기금 개요에 함께 실어, 은퇴된 nps_fund_returns 404를 재발시키지 않는다.
    const annualReturns =
        fund &&
        fund.annual_returns &&
        Array.isArray(fund.annual_returns.annual) &&
        fund.annual_returns.annual.length > 5
            ? fund.annual_returns
            : VERIFIED_ANNUAL_RETURNS
    const currentHighlight =
        fund?.current_highlight ||
        (fund?.as_of === "2026-06-30" ? VERIFIED_HIGHLIGHT : null)
    const reportPath = props.reportPath || "/stock"

    const wrap: any = {
        width: "100%",
        background: C.bg,
        fontFamily:
            "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif",
        padding: "0 14px",
        boxSizing: "border-box",
        color: C.ink,
    }

    if (loading) {
        const skBase = isDark ? "#222a33" : "#e9edf1"
        const skHi = isDark ? "#2d3742" : "#f3f5f7"
        const sk = (w: any, h: number, r = 8, mt = 0) => ({
            width: w,
            height: h,
            borderRadius: r,
            marginTop: mt,
            background: skBase,
            backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
            backgroundSize: "800px 100%",
            animation: "vsrShimmer 1.4s ease-in-out infinite",
        })
        const skCard: any = {
            background: C.card,
            borderRadius: 16,
            padding: "14px 16px",
            marginTop: 12,
            boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        }
        return (
            <div style={wrap}>
                <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={sk(120, 18, 6)} />
                <div
                    style={{
                        ...skCard,
                        display: "flex",
                        gap: 18,
                        flexWrap: "wrap",
                    }}
                >
                    {[0, 1, 2].map((i) => (
                        <div key={i}>
                            <div style={sk(70, 11, 4)} />
                            <div style={sk(90, 22, 6, 6)} />
                        </div>
                    ))}
                </div>
                <div style={skCard}>
                    <div style={sk(150, 14, 6)} />
                    {[0, 1, 2, 3, 4].map((i) => (
                        <div
                            key={i}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 10,
                                padding: "10px 0",
                                borderTop:
                                    i === 0 ? "none" : `1px solid ${C.line}`,
                            }}
                        >
                            <div style={{ flex: 1 }}>
                                <div style={sk(130, 14, 5)} />
                            </div>
                            <div style={sk(56, 15, 5)} />
                        </div>
                    ))}
                </div>
            </div>
        )
    }
    // 최근 공시 판정 = 최신 기준일 - 90일 · 겹침 집계 (전부 사실)
    const allRows: any[] = (data && (data.holdings || [])) || []
    // 겹침 검사 = 전체 투자현황(full, 연말 ~1,400종목 — 5% 미만 포함) 우선, 부재 시 5%+ 리스트 (PM 2026-07-07)
    const fullRows: any[] = (data && (data.full || [])) || []
    const fullUsRows: any[] = (data && (data.full_us || [])) || []
    const overlapBase: any[] = (fullRows.length ? fullRows : allRows).concat(
        fullUsRows
    )
    const maxDate = allRows.reduce(
        (m: string, r: any) =>
            String(r.date || "") > m ? String(r.date || "") : m,
        ""
    )
    const recentCut = maxDate
        ? new Date(
              new Date(maxDate + "T00:00:00+09:00").getTime() - 90 * 86400000
          )
              .toISOString()
              .slice(0, 10)
        : "9999"
    const overlapHold = overlapBase.filter((r: any) =>
        myHold.has(String(r.ticker))
    ).length
    const overlapWatch = overlapBase.filter(
        (r: any) =>
            !myHold.has(String(r.ticker)) && myWatch.has(String(r.ticker))
    ).length
    const in5p = new Set(allRows.map((r: any) => String(r.ticker)))
    // 5%+ 리스트 밖(=5% 미만)인데 내 보유/관심과 겹치는 전체 투자현황 행
    const myBelow5: any[] = fullRows
        .concat(fullUsRows)
        .filter(
            (r: any) =>
                !in5p.has(String(r.ticker)) &&
                (myHold.has(String(r.ticker)) || myWatch.has(String(r.ticker)))
        )

    if (!data)
        return (
            <div
                style={{
                    ...wrap,
                    textAlign: "center",
                    color: C.faint,
                    fontSize: 14,
                    padding: 40,
                }}
            >
                데이터를 불러오지 못했어요.
            </div>
        )

    return (
        <div style={wrap}>
            <div
                style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 9,
                    marginBottom: 12,
                    flexWrap: "wrap",
                }}
            >
                <NpsLogo />
                <span
                    style={{
                        fontSize: 18,
                        fontWeight: 800,
                        letterSpacing: "-0.4px",
                    }}
                >
                    국민연금공단 보유종목
                </span>
                <span
                    style={{ fontSize: 11.5, fontWeight: 600, color: C.faint }}
                >
                    공단 공시 사실
                </span>
            </div>
            {(overlapHold > 0 || overlapWatch > 0) && (
                <div
                    style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: C.sub,
                        background: C.card,
                        borderRadius: 12,
                        padding: "9px 13px",
                        marginBottom: 10,
                        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                    }}
                >
                    {overlapHold > 0 && (
                        <>
                            내 보유 중{" "}
                            <b style={{ color: C.ink }}>{overlapHold}종목</b>이
                            국민연금 보유와 겹칩니다
                        </>
                    )}
                    {overlapHold > 0 && overlapWatch > 0 && " · "}
                    {overlapWatch > 0 && (
                        <>
                            관심종목 겹침{" "}
                            <b style={{ color: C.ink }}>{overlapWatch}</b>
                        </>
                    )}
                    <span style={{ color: C.faint, fontWeight: 600 }}>
                        {" "}
                        —{" "}
                        {fullRows.length
                            ? "전체 투자현황(연말 기준 · 국내+해외 · 5% 미만 포함)"
                            : "5%+ 대량보유 공시"}{" "}
                        대조 · 사실 비교(추천 아님)
                    </span>
                </div>
            )}
            {myBelow5.length > 0 && (
                <div
                    style={{
                        background: C.card,
                        borderRadius: 12,
                        padding: "10px 13px",
                        marginBottom: 10,
                        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                    }}
                >
                    <div
                        style={{
                            fontSize: 11.5,
                            fontWeight: 800,
                            color: C.sub,
                            marginBottom: 5,
                        }}
                    >
                        내 종목 중 국민연금 보유 (5% 미만 · 해외 포함)
                    </div>
                    {myBelow5.slice(0, 8).map((r: any, i: number) => (
                        <div
                            key={i}
                            style={{
                                display: "flex",
                                alignItems: "baseline",
                                gap: 8,
                                padding: "4px 0",
                                fontSize: 12.5,
                            }}
                        >
                            <span style={{ fontWeight: 700, color: C.ink }}>
                                {r.name}
                            </span>
                            <span
                                style={{
                                    fontSize: 10.5,
                                    color: C.faint,
                                    fontWeight: 600,
                                }}
                            >
                                {r.ticker}
                            </span>
                            <span
                                style={{
                                    fontSize: 9.5,
                                    fontWeight: 800,
                                    color: myHold.has(String(r.ticker))
                                        ? C.green || "#0ca678"
                                        : C.blue,
                                    background: myHold.has(String(r.ticker))
                                        ? C.greenSoft || "#eafaf3"
                                        : C.blueSoft || "#eef4ff",
                                    borderRadius: 5,
                                    padding: "1.5px 6px",
                                }}
                            >
                                {myHold.has(String(r.ticker))
                                    ? "내 보유"
                                    : "관심"}
                            </span>
                            <span
                                style={{
                                    marginLeft: "auto",
                                    fontWeight: 800,
                                    color: C.ink,
                                    fontVariantNumeric: "tabular-nums",
                                }}
                            >
                                {r.pct != null
                                    ? Number(r.pct).toFixed(2) + "%"
                                    : "—"}
                            </span>
                        </div>
                    ))}
                    <div
                        style={{
                            fontSize: 10,
                            color: C.faint,
                            fontWeight: 600,
                            marginTop: 4,
                        }}
                    >
                        전체 투자현황 연말 기준(
                        {(fullRows[0] || {}).as_of || "연 1회 공시"}) · 사실
                    </div>
                </div>
            )}

            {/* 연도별 운용수익률 — 유선형 곡선 (1988~ 공단 공시 실값, PM 2026-07-07) */}
            {annualReturns &&
                Array.isArray(annualReturns.annual) &&
                annualReturns.annual.length > 5 &&
                (() => {
                    const ann: any[] = annualReturns.annual
                    const vmax = Math.max(
                        ...ann.map((a: any) => a.return_pct || 0),
                        1
                    )
                    const vmin = Math.min(
                        ...ann.map((a: any) => a.return_pct || 0),
                        0
                    )
                    const span = vmax - vmin || 1
                    const H = 110,
                        PADV = 8
                    const yOf = (v: number) =>
                        PADV + (1 - (v - vmin) / span) * (H - 2 * PADV)
                    const xOf = (i: number) => (i / (ann.length - 1)) * 100
                    const pts = ann.map((a: any, i: number) => ({
                        x: +xOf(i).toFixed(2),
                        y: +yOf(a.return_pct || 0).toFixed(2),
                    }))
                    // Catmull-Rom 곡선
                    let d = `M ${pts[0].x} ${pts[0].y}`
                    for (let i = 0; i < pts.length - 1; i++) {
                        const p0 = pts[i === 0 ? 0 : i - 1],
                            p1 = pts[i],
                            p2 = pts[i + 1],
                            p3 =
                                pts[i + 2 < pts.length ? i + 2 : pts.length - 1]
                        d += ` C ${(p1.x + (p2.x - p0.x) / 4.5).toFixed(2)} ${(p1.y + (p2.y - p0.y) / 4.5).toFixed(2)} ${(p2.x - (p3.x - p1.x) / 4.5).toFixed(2)} ${(p2.y - (p3.y - p1.y) / 4.5).toFixed(2)} ${p2.x} ${p2.y}`
                    }
                    const area =
                        d +
                        ` L ${pts[pts.length - 1].x} ${yOf(0)} L ${pts[0].x} ${yOf(0)} Z`
                    const zeroY = yOf(0)
                    const best = ann.reduce((a: any, b: any) =>
                        (b.return_pct || 0) > (a.return_pct || 0) ? b : a
                    )
                    const worst = ann.reduce((a: any, b: any) =>
                        (b.return_pct || 0) < (a.return_pct || 0) ? b : a
                    )
                    const last = ann[ann.length - 1]
                    const selected =
                        ann.find(
                            (a: any) =>
                                Number(a.year) ===
                                Number(selectedReturnYear || last.year)
                        ) || last
                    const selectedContext =
                        (annualReturns.year_context || {})[
                            String(selected.year)
                        ] ||
                        VERIFIED_ANNUAL_RETURNS.year_context[
                            String(selected.year)
                        ] ||
                        null
                    const contextCount = ann.filter(
                        (a: any) =>
                            (annualReturns.year_context || {})[
                                String(a.year)
                            ] ||
                            VERIFIED_ANNUAL_RETURNS.year_context[String(a.year)]
                    ).length
                    return (
                        <div
                            style={{
                                background: C.card,
                                borderRadius: 16,
                                padding: "14px 16px",
                                boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                                marginBottom: 12,
                            }}
                        >
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "baseline",
                                    gap: 8,
                                    flexWrap: "wrap",
                                }}
                            >
                                <span
                                    style={{ fontSize: 13.5, fontWeight: 800 }}
                                >
                                    연도별 운용수익률
                                </span>
                                <span
                                    style={{
                                        fontSize: 11,
                                        fontWeight: 600,
                                        color: C.faint,
                                    }}
                                >
                                    {ann[0].year}~{last.year} · 공단 공시
                                </span>
                                <span
                                    style={{
                                        marginLeft: "auto",
                                        fontSize: 11.5,
                                        fontWeight: 800,
                                        color: C.ink,
                                    }}
                                >
                                    연평균 {annualReturns.cumulative_avg_pct}%
                                </span>
                            </div>
                            <div
                                style={{
                                    position: "relative",
                                    height: H,
                                    marginTop: 10,
                                }}
                            >
                                <svg
                                    role="img"
                                    aria-label="국민연금 연도별 운용수익률"
                                    viewBox={`0 0 100 ${H}`}
                                    preserveAspectRatio="none"
                                    style={{
                                        width: "100%",
                                        height: H,
                                        display: "block",
                                        overflow: "visible",
                                    }}
                                >
                                    <line
                                        x1={0}
                                        y1={zeroY}
                                        x2={100}
                                        y2={zeroY}
                                        stroke={C.line}
                                        strokeWidth={1}
                                        vectorEffect="non-scaling-stroke"
                                    />
                                    <path
                                        d={area}
                                        fill={C.accent || "#6c5ce7"}
                                        fillOpacity={0.08}
                                        stroke="none"
                                    />
                                    <path
                                        d={d}
                                        fill="none"
                                        stroke={C.accent || "#6c5ce7"}
                                        strokeWidth={2}
                                        strokeLinejoin="round"
                                        strokeLinecap="round"
                                        vectorEffect="non-scaling-stroke"
                                    />
                                </svg>
                                {ann.map((a: any, i: number) => {
                                    const point = pts[i]
                                    const active =
                                        Number(a.year) === Number(selected.year)
                                    return (
                                        <button
                                            type="button"
                                            key={a.year}
                                            aria-label={`${a.year}년 수익률 ${Number(a.return_pct).toFixed(2)}%`}
                                            aria-pressed={active}
                                            title={`${a.year}년 · ${Number(a.return_pct).toFixed(2)}%`}
                                            style={{
                                                position: "absolute",
                                                left: `${point.x}%`,
                                                top: point.y,
                                                transform:
                                                    "translate(-50%, -50%)",
                                                width: 12,
                                                height: 16,
                                                padding: 0,
                                                border: 0,
                                                background: "transparent",
                                                cursor: "pointer",
                                                display: "flex",
                                                alignItems: "center",
                                                justifyContent: "center",
                                            }}
                                            onClick={() =>
                                                setSelectedReturnYear(
                                                    Number(a.year)
                                                )
                                            }
                                        >
                                            <span
                                                style={{
                                                    width: active ? 7 : 4,
                                                    height: active ? 7 : 4,
                                                    borderRadius: "50%",
                                                    background: active
                                                        ? C.accent
                                                        : C.card,
                                                    boxShadow: `0 0 0 1px ${C.accent}`,
                                                    flexShrink: 0,
                                                }}
                                            />
                                        </button>
                                    )
                                })}
                            </div>
                            <div
                                style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    marginTop: 5,
                                    fontSize: 9.5,
                                    color: C.faint,
                                    fontWeight: 700,
                                }}
                            >
                                {ann
                                    .filter(
                                        (a: any) =>
                                            a.year % 5 === 0 ||
                                            a.year === last.year
                                    )
                                    .map((a: any) => (
                                        <span key={a.year}>
                                            {"'" + String(a.year).slice(2)}
                                        </span>
                                    ))}
                            </div>
                            <div
                                style={{
                                    display: "flex",
                                    gap: 14,
                                    flexWrap: "wrap",
                                    marginTop: 8,
                                    fontSize: 11,
                                    color: C.sub,
                                    fontWeight: 600,
                                }}
                            >
                                <span>
                                    최고{" "}
                                    <b style={{ color: C.up }}>
                                        {best.year} +
                                        {Number(best.return_pct).toFixed(1)}%
                                    </b>
                                </span>
                                <span>
                                    최저{" "}
                                    <b style={{ color: C.down }}>
                                        {worst.year}{" "}
                                        {Number(worst.return_pct).toFixed(1)}%
                                    </b>
                                </span>
                                <span>
                                    최근 {last.year}{" "}
                                    {Number(last.return_pct) >= 0 ? "+" : ""}
                                    {Number(last.return_pct).toFixed(1)}%
                                    {last.provisional ? " (잠정)" : ""}
                                </span>
                                {annualReturns.cumulative_profit_bil !=
                                    null && (
                                    <span>
                                        누적 수익금{" "}
                                        {(
                                            annualReturns.cumulative_profit_bil /
                                            1000
                                        ).toFixed(0)}
                                        조원
                                    </span>
                                )}
                            </div>
                            <div
                                style={{
                                    marginTop: 11,
                                    padding: "9px 10px",
                                    borderRadius: 10,
                                    background: C.bg,
                                    color: C.sub,
                                    fontSize: 11,
                                    fontWeight: 600,
                                    lineHeight: 1.5,
                                }}
                            >
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "baseline",
                                        gap: 6,
                                        flexWrap: "wrap",
                                    }}
                                >
                                    <b
                                        style={{
                                            color: C.ink,
                                            fontWeight: 800,
                                        }}
                                    >
                                        {selected.year}년 성과 맥락
                                    </b>
                                    <span>
                                        전체{" "}
                                        {Number(selected.return_pct) >= 0
                                            ? "+"
                                            : ""}
                                        {Number(selected.return_pct).toFixed(2)}
                                        %
                                    </span>
                                </div>
                                {selectedContext ? (
                                    <div style={{ marginTop: 2 }}>
                                        {selectedContext.label}:{" "}
                                        <b
                                            style={{
                                                color: C.ink,
                                                fontWeight: 800,
                                            }}
                                        >
                                            {selectedContext.asset}
                                            {selectedContext.profit_bil != null
                                                ? " +" +
                                                  (
                                                      Number(
                                                          selectedContext.profit_bil
                                                      ) / 1000
                                                  ).toFixed(1) +
                                                  "조원"
                                                : ""}
                                        </b>
                                        <span style={{ color: C.faint }}>
                                            {" "}
                                            · 개별 종목별 수익 기여도는 공식
                                            미공개
                                        </span>
                                    </div>
                                ) : (
                                    <div
                                        style={{ marginTop: 2, color: C.faint }}
                                    >
                                        이 연도의 자산군별 수익금·종목별
                                        기여도는 아직 확인한 자료가 없어요.
                                    </div>
                                )}
                                {selectedContext?.summary && (
                                    <div style={{ marginTop: 5, color: C.sub }}>
                                        {selectedContext.summary}
                                    </div>
                                )}
                                <div
                                    style={{
                                        marginTop: 3,
                                        color: C.faint,
                                        fontSize: 10,
                                    }}
                                >
                                    성과 설명 {contextCount}/{ann.length}년 ·
                                    점을 눌러 연도 선택{" "}
                                    <a
                                        href={
                                            selectedContext?.source_url ||
                                            annualReturns.source_url ||
                                            VERIFIED_ANNUAL_RETURNS.source_url
                                        }
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        style={{
                                            color: C.sub,
                                            fontWeight: 700,
                                        }}
                                    >
                                        {selectedContext?.source_title ||
                                            "국민연금 원문"}
                                    </a>
                                </div>
                            </div>
                        </div>
                    )
                })()}

            {/* 운용현황 카드 */}
            {fund && (
                <div
                    style={{
                        background: C.card,
                        borderRadius: 16,
                        padding: "14px 16px",
                        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                        marginBottom: 12,
                    }}
                >
                    <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
                        {fund.aum_krw_trillion != null && (
                            <div>
                                <div
                                    style={{
                                        fontSize: 11,
                                        fontWeight: 700,
                                        color: C.faint,
                                    }}
                                >
                                    운용 규모(AUM)
                                </div>
                                <div
                                    style={{
                                        fontSize: 20,
                                        fontWeight: 800,
                                        letterSpacing: "-0.5px",
                                    }}
                                >
                                    {Number(
                                        fund.aum_krw_trillion
                                    ).toLocaleString()}
                                    <span
                                        style={{
                                            fontSize: 13,
                                            fontWeight: 700,
                                        }}
                                    >
                                        조원
                                    </span>
                                </div>
                            </div>
                        )}
                        {fund.return_total_pct != null && (
                            <div>
                                <div
                                    style={{
                                        fontSize: 11,
                                        fontWeight: 700,
                                        color: C.faint,
                                    }}
                                >
                                    {fund.return_total_note || "수익률"}
                                </div>
                                <div
                                    style={{
                                        fontSize: 20,
                                        fontWeight: 800,
                                        color:
                                            Number(fund.return_total_pct) >= 0
                                                ? C.up
                                                : C.down,
                                        letterSpacing: "-0.5px",
                                    }}
                                >
                                    {Number(fund.return_total_pct) >= 0
                                        ? "+"
                                        : ""}
                                    {fmtPct(fund.return_total_pct)}
                                </div>
                            </div>
                        )}
                        {fund.return_cumulative_annualized_pct != null && (
                            <div>
                                <div
                                    style={{
                                        fontSize: 11,
                                        fontWeight: 700,
                                        color: C.faint,
                                    }}
                                >
                                    누적 연환산
                                </div>
                                <div
                                    style={{
                                        fontSize: 20,
                                        fontWeight: 800,
                                        letterSpacing: "-0.5px",
                                    }}
                                >
                                    {fmtPct(
                                        fund.return_cumulative_annualized_pct
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* 자산배분 스택 바 (기금 포트폴리오 현황 CSV — 분기 사실) */}
                    {(() => {
                        const am =
                            (data && data.asset_mix && data.asset_mix[0]) ||
                            null
                        const mix = ((am && am.mix) || []).filter(
                            (m: any) => (m.pct || 0) >= 0.5
                        )
                        if (!mix.length) return null
                        const PAL = [
                            "#f04452",
                            "#3182f6",
                            "#0ca678",
                            "#ff9500",
                            "#6c5ce7",
                            "#8b95a1",
                        ]
                        return (
                            <div style={{ marginTop: 14 }}>
                                <div
                                    style={{
                                        display: "flex",
                                        justifyContent: "space-between",
                                        alignItems: "baseline",
                                    }}
                                >
                                    <span
                                        style={{
                                            fontSize: 11,
                                            fontWeight: 700,
                                            color: C.faint,
                                        }}
                                    >
                                        자산배분 · {am.as_of} 기준
                                    </span>
                                    {am.total_bil && (
                                        <span
                                            style={{
                                                fontSize: 10.5,
                                                fontWeight: 700,
                                                color: C.faint,
                                            }}
                                        >
                                            전체{" "}
                                            {(am.total_bil / 1000).toFixed(0)}
                                            조원
                                        </span>
                                    )}
                                </div>
                                <div
                                    style={{
                                        display: "flex",
                                        height: 10,
                                        borderRadius: 5,
                                        overflow: "hidden",
                                        marginTop: 6,
                                    }}
                                >
                                    {mix.map((m: any, i: number) => (
                                        <div
                                            key={m.name}
                                            title={`${m.name} ${m.pct}%`}
                                            style={{
                                                width: m.pct + "%",
                                                background: PAL[i % PAL.length],
                                                opacity: 0.85,
                                            }}
                                        />
                                    ))}
                                </div>
                                <div
                                    style={{
                                        display: "flex",
                                        gap: 10,
                                        flexWrap: "wrap",
                                        marginTop: 6,
                                    }}
                                >
                                    {mix.map((m: any, i: number) => (
                                        <span
                                            key={m.name}
                                            style={{
                                                display: "inline-flex",
                                                alignItems: "center",
                                                gap: 4,
                                                fontSize: 10.5,
                                                fontWeight: 700,
                                                color: C.sub,
                                            }}
                                        >
                                            <span
                                                style={{
                                                    width: 8,
                                                    height: 8,
                                                    borderRadius: 2,
                                                    background:
                                                        PAL[i % PAL.length],
                                                    opacity: 0.85,
                                                }}
                                            />
                                            {m.name} {m.pct}%
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )
                    })()}
                    {fund.asset_returns_pct && (
                        <div
                            style={{
                                display: "flex",
                                gap: 7,
                                flexWrap: "wrap",
                                marginTop: 11,
                            }}
                        >
                            {Object.keys(fund.asset_returns_pct).map((k) => {
                                const v = fund.asset_returns_pct[k]
                                return (
                                    <span
                                        key={k}
                                        style={{
                                            fontSize: 11,
                                            fontWeight: 700,
                                            color: C.sub,
                                            background: C.bg,
                                            borderRadius: 8,
                                            padding: "5px 9px",
                                        }}
                                    >
                                        {k}{" "}
                                        <b
                                            style={{
                                                color:
                                                    Number(v) >= 0
                                                        ? C.up
                                                        : C.down,
                                            }}
                                        >
                                            {Number(v) >= 0 ? "+" : ""}
                                            {fmtPct(v)}
                                        </b>
                                    </span>
                                )
                            })}
                        </div>
                    )}
                    {currentHighlight && (
                        <div
                            style={{
                                marginTop: 10,
                                padding: "8px 10px",
                                borderRadius: 10,
                                background: C.bg,
                                fontSize: 11,
                                fontWeight: 600,
                                color: C.sub,
                                lineHeight: 1.5,
                            }}
                        >
                            <b style={{ color: C.ink, fontWeight: 800 }}>
                                {currentHighlight.label}
                            </b>
                            {" · "}
                            {currentHighlight.asset}{" "}
                            <b style={{ color: C.up, fontWeight: 800 }}>
                                +{fmtPct(currentHighlight.return_pct)}
                            </b>
                            <span style={{ color: C.faint }}>
                                {" "}
                                · {currentHighlight.period}
                                {currentHighlight.provisional ? " 잠정" : ""}
                            </span>
                        </div>
                    )}
                    <div
                        style={{
                            fontSize: 10.5,
                            color: C.faint,
                            fontWeight: 600,
                            marginTop: 9,
                            lineHeight: 1.5,
                        }}
                    >
                        {fund.as_of ? fund.as_of + " 기준 · " : ""}
                        {fund.source || "국민연금 공시"}
                    </div>
                </div>
            )}

            <NpsHistoryPanel history={data.detail_history} isDark={isDark} />

            {/* 보유종목 */}
            <div
                style={{
                    background: C.card,
                    borderRadius: 16,
                    padding: "8px 16px 12px",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                }}
            >
                <div
                    style={{
                        display: "flex",
                        alignItems: "baseline",
                        justifyContent: "space-between",
                        padding: "8px 0 4px",
                    }}
                >
                    <span style={{ fontSize: 13, fontWeight: 800 }}>
                        보유종목 (5%+ 공시)
                    </span>
                    <span
                        style={{
                            fontSize: 11,
                            fontWeight: 700,
                            color: C.accent,
                        }}
                    >
                        {query.trim()
                            ? `${shownHoldings.length} / ${holdings.length}`
                            : holdings.length}
                        종목
                    </span>
                </div>
                {/* 검색 — 종목명·코드 */}
                <div style={{ position: "relative", margin: "2px 0 8px" }}>
                    <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke={C.faint}
                        strokeWidth="2.4"
                        strokeLinecap="round"
                        style={{
                            position: "absolute",
                            left: 13,
                            top: "50%",
                            transform: "translateY(-50%)",
                            pointerEvents: "none",
                        }}
                    >
                        <circle cx="11" cy="11" r="7" />
                        <line x1="21" y1="21" x2="16.65" y2="16.65" />
                    </svg>
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="종목명·코드 검색"
                        style={{
                            width: "100%",
                            boxSizing: "border-box",
                            border: "none",
                            background: C.bg,
                            color: C.ink,
                            borderRadius: 12,
                            padding: "11px 32px 11px 36px",
                            fontSize: 13,
                            fontFamily: "Pretendard, -apple-system, sans-serif",
                            outline: "none",
                            WebkitAppearance: "none",
                        }}
                    />
                    {query && (
                        <span
                            role="button"
                            tabIndex={0}
                            onClick={() => setQuery("")}
                            style={{
                                position: "absolute",
                                right: 10,
                                top: "50%",
                                transform: "translateY(-50%)",
                                color: C.faint,
                                fontSize: 14,
                                fontWeight: 700,
                                cursor: "pointer",
                                lineHeight: 1,
                            }}
                        >
                            ×
                        </span>
                    )}
                </div>
                {shownHoldings.length === 0 ? (
                    <div
                        style={{
                            padding: "20px 0",
                            textAlign: "center",
                            color: C.faint,
                            fontSize: 13,
                            fontWeight: 600,
                        }}
                    >
                        {query.trim()
                            ? `"${query.trim()}" 검색 결과 없음`
                            : "공시된 5%+ 보유종목 없음"}
                    </div>
                ) : (
                    displayHoldings.map((h: any, i: number) => {
                        const url = h.ticker
                            ? reportPath + "?q=" + encodeURIComponent(h.ticker)
                            : ""
                        const chg = h.qty_change
                        const chgCol =
                            chg == null
                                ? C.faint
                                : Number(chg) > 0
                                  ? C.up
                                  : Number(chg) < 0
                                    ? C.down
                                    : C.faint
                        return (
                            <div
                                key={i}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 10,
                                    padding: "10px 0",
                                    borderTop:
                                        i === 0
                                            ? "none"
                                            : `1px solid ${C.line}`,
                                }}
                            >
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    {url && !onCanvas ? (
                                        <a
                                            href={url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            title={h.name + " 분석"}
                                            style={{
                                                fontSize: 14,
                                                fontWeight: 700,
                                                color: C.blue,
                                                textDecoration: "none",
                                            }}
                                        >
                                            {h.name} ↗
                                        </a>
                                    ) : (
                                        <span
                                            style={{
                                                fontSize: 14,
                                                fontWeight: 700,
                                                color: C.ink,
                                            }}
                                        >
                                            {h.name}
                                        </span>
                                    )}
                                    <span
                                        style={{
                                            fontSize: 11,
                                            fontWeight: 600,
                                            color: C.faint,
                                            marginLeft: 6,
                                        }}
                                    >
                                        {h.ticker}
                                    </span>
                                    {myHold.has(String(h.ticker)) && (
                                        <span
                                            style={{
                                                fontSize: 9.5,
                                                fontWeight: 800,
                                                color: C.green || "#0ca678",
                                                background:
                                                    C.greenSoft ||
                                                    "rgba(18,183,106,0.12)",
                                                borderRadius: 5,
                                                padding: "1.5px 6px",
                                                marginLeft: 6,
                                                verticalAlign: "1px",
                                            }}
                                        >
                                            내 보유
                                        </span>
                                    )}
                                    {!myHold.has(String(h.ticker)) &&
                                        myWatch.has(String(h.ticker)) && (
                                            <span
                                                style={{
                                                    fontSize: 9.5,
                                                    fontWeight: 800,
                                                    color: C.blue,
                                                    background:
                                                        C.blueSoft ||
                                                        "rgba(49,130,246,0.10)",
                                                    borderRadius: 5,
                                                    padding: "1.5px 6px",
                                                    marginLeft: 6,
                                                    verticalAlign: "1px",
                                                }}
                                            >
                                                관심
                                            </span>
                                        )}
                                    {String(h.date || "") >= recentCut && (
                                        <span
                                            style={{
                                                fontSize: 9.5,
                                                fontWeight: 800,
                                                color: "#b26a00",
                                                background:
                                                    "rgba(255,149,0,0.12)",
                                                borderRadius: 5,
                                                padding: "1.5px 6px",
                                                marginLeft: 6,
                                                verticalAlign: "1px",
                                            }}
                                        >
                                            최근 공시
                                        </span>
                                    )}
                                    {h.date && (
                                        <div
                                            style={{
                                                fontSize: 10.5,
                                                color: C.faint,
                                                fontWeight: 600,
                                                marginTop: 1,
                                            }}
                                        >
                                            {h.date} · {h.src || "DART"}
                                        </div>
                                    )}
                                </div>
                                {chg != null && Number(chg) !== 0 && (
                                    <span
                                        style={{
                                            flexShrink: 0,
                                            fontSize: 11,
                                            fontWeight: 700,
                                            color: chgCol,
                                        }}
                                    >
                                        {Number(chg) > 0 ? "▲" : "▼"}
                                        {Math.abs(Number(chg)).toLocaleString()}
                                    </span>
                                )}
                                <span
                                    style={{
                                        flexShrink: 0,
                                        fontSize: 15,
                                        fontWeight: 800,
                                        color: C.ink,
                                        fontVariantNumeric: "tabular-nums",
                                        minWidth: 56,
                                        textAlign: "right",
                                    }}
                                >
                                    {fmtPct(h.pct)}
                                </span>
                            </div>
                        )
                    })
                )}
                {!query.trim() && shownHoldings.length > NPS_PREVIEW && (
                    <div
                        role="button"
                        tabIndex={0}
                        onClick={() => setNpsAll((v) => !v)}
                        style={{
                            marginTop: 4,
                            padding: "11px 0 5px",
                            textAlign: "center",
                            cursor: "pointer",
                            fontSize: 12.5,
                            fontWeight: 800,
                            color: C.accent,
                            borderTop: `1px solid ${C.line}`,
                        }}
                    >
                        <span
                            style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 5,
                            }}
                        >
                            {npsAll
                                ? "접기"
                                : `더보기 (${shownHoldings.length - NPS_PREVIEW}개 더)`}
                            <svg
                                width="13"
                                height="13"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke={C.accent}
                                strokeWidth="2.6"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                style={{
                                    transform: npsAll
                                        ? "rotate(180deg)"
                                        : "none",
                                    transition: "transform 150ms ease",
                                }}
                            >
                                <path d="M6 9l6 6 6-6" />
                            </svg>
                        </span>
                    </div>
                )}
            </div>

            {/* 한계 라벨 — 데이터 커버리지 사실 */}
            <div
                style={{
                    marginTop: 12,
                    padding: "11px 13px",
                    background: C.card,
                    borderRadius: 12,
                    border: `1px solid ${C.line}`,
                }}
            >
                <div
                    style={{
                        fontSize: 11.5,
                        fontWeight: 700,
                        color: C.sub,
                        lineHeight: 1.55,
                    }}
                >
                    ⓘ{" "}
                    {data.note ||
                        "국민연금 5% 이상 대량보유 공시 기준 — 전체 보유종목 아님 · 분기 지연."}
                </div>
                {data.coverage === "operating_pool" && (
                    <div
                        style={{
                            fontSize: 10.5,
                            color: C.faint,
                            fontWeight: 600,
                            marginTop: 5,
                            lineHeight: 1.5,
                        }}
                    >
                        현재 = 운영풀 종목 한정. 전체 5%+ 공시(약 111종목)는
                        data.go.kr 연동 시 확대.
                    </div>
                )}
            </div>

            <div
                style={{
                    textAlign: "center",
                    fontSize: 10.5,
                    color: C.faint,
                    marginTop: 10,
                    fontWeight: 600,
                }}
            >
                {data.source || "DART·data.go.kr"} · 공시 사실(지분율)
            </div>
        </div>
    )
}

addPropertyControls(PublicNPSHoldings, {
    width: {
        type: ControlType.Number,
        title: "Width",
        defaultValue: 420,
        min: 320,
        max: 760,
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark (canvas)",
        defaultValue: false,
    },
    dataUrl: {
        type: ControlType.String,
        title: "데이터 URL",
        defaultValue: BLOB + "/nps_holdings.json",
    },
    reportPath: {
        type: ControlType.String,
        title: "리포트 경로",
        defaultValue: "/stock",
    },
})

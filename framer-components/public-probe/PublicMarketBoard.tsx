import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 글로벌 시세 보드 — VERITY 공개 터미널. 지수·환율·원자재·금리·크립토 카드 + 미니 추세선(팩트만).
 *
 * 🚨 RULE 7 = 사실만(이름+값+등락%+추세선). 토스식 "금리 동결 결정" 류 AI 사유 태그 없음(RULE 6 — LLM 영역, 차별점 0).
 * 데이터 = price_pulse.json(국내·해외지수·VIX·환율, 1분 fresh) + macro_snapshot.json(원자재·금리·SOX·코인·sparkline·cross_asset_corr).
 *   + commodity_exposure.json(원자재→KR 노출 산업/종목 — 엣지).
 * 🚨 추측 0: sparkline 배열(length≥2)이 실제로 있는 지표만 추세선을 그림. 없으면 카드만.
 * 🚨 wrap = minHeight:100% 자연흐름(페이지서 자라남). height:100% 쓰면 fit-content 부모서 0px 붕괴 = 프리뷰 안 보임.
 * 🚨 컴팩트 타일 — 한눈 스캔: padding 8/10·value 15·spark 40x24·행당 최대 5열. 밀도 우선.
 * 🚨 ⓘ = 상관 섹션 1개만(비자명 개념). 시세 타일은 이름이 자설명(VIX 공포지수 등)이라 per-타일 ⓘ 없음(스캔 속도 우선).
 * 크립토 = 업비트 KRW 일봉 5코인(BTC 디지털금/ETH 스마트컨트랙트/XRP 결제/SOL L1/DOGE 밈). SOX = yfinance ^SOX. KR 색 = 상승 빨강 / 하락 파랑.
 *
 * 다크모드 = body[data-framer-theme] 추종(다른 public 컴포넌트와 동일 패턴). 캔버스 에디터선 dark prop 정적 프리뷰.
 *
 * 🚨 카드 선택(2026-06-22) = 상세 펼침 시 초록 외곽선 X → 회색 pressed(배경 chipBg 틴트 + inset 그림자, 눌린 느낌)로 표시.
 *   상세는 추세선·상관·절대변동 중 추가 정보가 있을 때만 클릭 가능(hasDetail) — 카드와 같은 값 반복 방지.
 *   2026-06-22: 코스피(^KS11)·코스닥(^KQ11)·달러환율(KRW=X) 30일 sparkline 추가(macro_data.py) → 값은 price_pulse 실시간 유지, 추세선만 macro. 전 카드 추세선·상세 일관.
 *
 * 🚨 엣지 (토스·증권사 구조적 불가, 2026-06-21):
 *  - 자산 간 상관(30일) = macro.cross_asset_corr — 금·원유 ↔ 코스피/달러/BTC/금리 상관(시세로 계산한 사실). 가격 나열이 아닌 quant 관계.
 *  - 원자재 → KR 노출 = 원자재 카드 클릭 시 원가·매출 연관 KR 산업/종목(commodity_exposure). RULE 7 = 산업 멤버십 사실, 수혜·추천 0(방향 종목별 상이).
 */

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#6b7684", faint: "#8b95a1", line: "#eef1f4", up: "#f04452", down: "#3182f6", flat: "#8b95a1", cPos: "#0ca678", cNeg: "#6c5ce7", chipBg: "#f2f4f6", tipBg: "#191f28" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff", flat: "#828d9b", cPos: "#34e08a", cNeg: "#a99bff", chipBg: "#0f1318", tipBg: "#222a33" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const DEFAULT_PULSE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/price_pulse.json"
const DEFAULT_MACRO = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/macro_snapshot.json"
const DEFAULT_EXPO = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/commodity_exposure.json"
const DEFAULT_REPORT = "/stock"

interface Props {
    pulseUrl: string
    macroUrl: string
    commodityUrl: string
    reportPath: string
    dark: boolean
    refreshSec: number
}

// 자산 간 상관 — 원자재(금·원유) 중심 pair. asset key = macro.cross_asset_corr.assets.
const CORR_LABELS: Record<string, string> = { stock: "코스피", bond_yield: "미 10Y", gold: "금", usd: "달러", oil: "원유", btc: "비트코인" }
const CORR_PAIRS: [string, string][] = [["gold", "stock"], ["gold", "usd"], ["gold", "oil"], ["gold", "btc"], ["oil", "stock"], ["oil", "usd"]]

// src = 값 출처(pulse=price_pulse.indices / macro=macro_snapshot.macro). spark = macro 내 sparkline 경로(없으면 추세선 생략). dec=소수자릿수. unit=접미.
const GROUPS: { title: string; items: { key: string; name: string; src: "pulse" | "macro"; spark?: string; dec?: number; unit?: string }[] }[] = [
    {
        title: "국내", items: [
            { key: "kospi", name: "코스피", src: "pulse", spark: "kospi", dec: 2 },
            { key: "kosdaq", name: "코스닥", src: "pulse", spark: "kosdaq", dec: 2 },
        ],
    },
    {
        title: "해외 지수", items: [
            { key: "sp500", name: "S&P 500", src: "pulse", spark: "sp500", dec: 2 },
            { key: "nasdaq", name: "나스닥", src: "pulse", spark: "nasdaq", dec: 2 },
            { key: "dow", name: "다우존스", src: "pulse", spark: "dji", dec: 2 },
            { key: "sox", name: "필라델피아 반도체", src: "macro", spark: "sox", dec: 2 },
            { key: "nikkei", name: "니케이225", src: "macro", spark: "nikkei", dec: 2 },
            { key: "dax", name: "독일 DAX", src: "macro", spark: "dax", dec: 2 },
        ],
    },
    {
        title: "변동성·환율·금리", items: [
            { key: "vix", name: "VIX 공포지수", src: "pulse", spark: "fred.vix_close", dec: 2 },
            { key: "usdkrw", name: "달러 환율", src: "pulse", spark: "usd_krw", dec: 2, unit: "원" },
            { key: "us_10y", name: "미국 10년물", src: "macro", spark: "us_10y", dec: 3, unit: "%" },
            { key: "us_2y", name: "미국 2년물", src: "macro", spark: "us_2y", dec: 3, unit: "%" },
        ],
    },
    {
        title: "원자재", items: [
            { key: "gold", name: "금", src: "macro", spark: "gold", dec: 2 },
            { key: "silver", name: "은", src: "macro", spark: "silver", dec: 2 },
            { key: "copper", name: "구리", src: "macro", spark: "copper", dec: 3 },
            { key: "wti_oil", name: "WTI 유가", src: "macro", spark: "wti_oil", dec: 2 },
        ],
    },
    {
        title: "크립토", items: [
            { key: "btc", name: "비트코인", src: "macro", spark: "btc", dec: 0, unit: "원" },
            { key: "eth", name: "이더리움", src: "macro", spark: "eth", dec: 0, unit: "원" },
            { key: "xrp", name: "리플 XRP", src: "macro", spark: "xrp", dec: 0, unit: "원" },
            { key: "sol", name: "솔라나", src: "macro", spark: "sol", dec: 0, unit: "원" },
            { key: "doge", name: "도지코인", src: "macro", spark: "doge", dec: 0, unit: "원" },
        ],
    },
]

function dig(obj: any, path: string): any {
    if (!obj || !path) return undefined
    return path.split(".").reduce((o: any, k: string) => (o && o[k] != null ? o[k] : undefined), obj)
}
function fmtNum(v: any, dec: number): string {
    const x = Number(v)
    if (!isFinite(x)) return "—"
    return x.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

function Spark({ data, color, w, h }: { data: number[]; color: string; w: number; h: number }) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data), max = Math.max(...data), rng = (max - min) || 1
    const pad = 2
    const pts = data.map((v, i) => `${((i / (data.length - 1)) * w).toFixed(1)},${(h - pad - ((v - min) / rng) * (h - pad * 2)).toFixed(1)}`)
    const line = pts.join(" ")
    const area = `${line} ${w.toFixed(1)},${h} 0,${h}`
    const gid = "vmb-" + color.replace(/[^a-z0-9]/gi, "")
    return (
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block", flexShrink: 0 }}>
            <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
            </defs>
            <polygon points={area} fill={`url(#${gid})`} stroke="none" />
            <polyline points={line} fill="none" stroke={color} strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        </svg>
    )
}

// 상관 막대 — 중앙(0)에서 좌(역행, 보라)/우(동행, 초록)로. |r|≥0.5 진하게.
function CorrBar({ v, C }: { v: number; C: any }) {
    const x = Math.max(-1, Math.min(1, Number(v) || 0))
    const col = x >= 0 ? C.cPos : C.cNeg
    const w = Math.abs(x) * 50  // 0~50% (반폭)
    const strong = Math.abs(x) >= 0.5
    return (
        <div style={{ position: "relative", flex: 1, height: 6, background: C.line, borderRadius: 4, minWidth: 36 }}>
            <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: C.faint, opacity: 0.5 }} />
            <div style={{ position: "absolute", top: 0, height: "100%", borderRadius: 4, background: col, opacity: strong ? 1 : 0.55, ...(x >= 0 ? { left: "50%", width: w + "%" } : { right: "50%", width: w + "%" }) }} />
        </div>
    )
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicMarketBoard(props: Props) {
    const { pulseUrl, macroUrl, commodityUrl, reportPath, dark, refreshSec } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [pulse, setPulse] = useState<any>(null)
    const [macro, setMacro] = useState<any>(null)
    const [pulseLoaded, setPulseLoaded] = useState(false)   // 최초 성공 로드 여부 — 로딩 중 카드 vanish 대신 스켈레톤
    const [macroLoaded, setMacroLoaded] = useState(false)   // macro 늦게 와도 원자재·크립토·SOX 등 자리 유지(스켈레톤)
    const [expo, setExpo] = useState<any>(null)
    const [openCommodity, setOpenCommodity] = useState<string>("")
    const [openDetail, setOpenDetail] = useState<string>("")
    const [corrTip, setCorrTip] = useState(false)

    // 테마 추종 — body[data-framer-theme] 변경 구독
    useEffect(() => {
        if (onCanvas) return
        const read = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    // 바깥 탭/클릭 시 상관 ⓘ 닫기 (모바일)
    useEffect(() => {
        if (typeof document === "undefined") return
        const close = () => setCorrTip(false)
        document.addEventListener("click", close)
        return () => document.removeEventListener("click", close)
    }, [])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const load = () => {
            fetch(pulseUrl, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((d) => { if (alive && d) { setPulse(d); setPulseLoaded(true) } }).catch(() => {})
            fetch(macroUrl, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((d) => { if (alive && d) { setMacro(d); setMacroLoaded(true) } }).catch(() => {})
        }
        load()
        const sec = Math.max(15, refreshSec || 60)
        const t = setInterval(load, sec * 1000)
        return () => { alive = false; clearInterval(t) }
    }, [pulseUrl, macroUrl, refreshSec, onCanvas])

    useEffect(() => {
        if (onCanvas || !commodityUrl) return
        let alive = true
        fetch(commodityUrl, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null))
            .then((d) => { const c = d && (d.commodities || d); if (alive && c && typeof c === "object") setExpo(c) }).catch(() => {})
        return () => { alive = false }
    }, [commodityUrl, onCanvas])

    const M = useMemo(() => (macro && (macro.macro || macro)) || null, [macro])
    const cac = useMemo(() => {
        if (onCanvas) return { window_days: 30, as_of: "2026-06-20", matrix: { gold: { stock: 0.13, usd: -0.55, oil: -0.34, btc: 0.08 }, oil: { stock: -0.14, usd: 0.33 } }, max_abs_pair: { pair: "gold_usd", abs_corr: 0.55 } }
        return (M && M.cross_asset_corr && M.cross_asset_corr.available !== false) ? M.cross_asset_corr : null
    }, [M, onCanvas])
    const expoData = useMemo(() => {
        if (onCanvas) return { wti_oil: { label: "WTI 원유", note: "정유·항공·석유화학 — 원유 가격에 원가·매출 연관(방향 상이).", count: 68, stocks: [{ ticker: "051910", name: "LG화학", industry: "Specialty Chemicals" }, { ticker: "096770", name: "SK이노베이션", industry: "Oil & Gas Refining & Marketing" }, { ticker: "010140", name: "삼성중공업", industry: "Chemicals" }] }, copper: { label: "구리", note: "비철금속·금속가공.", count: 17, stocks: [{ ticker: "010130", name: "고려아연", industry: "Other Industrial Metals & Mining" }, { ticker: "103140", name: "풍산", industry: "Copper" }] } }
        return expo
    }, [expo, onCanvas])

    const go = (ticker: string) => {
        if (onCanvas || typeof window === "undefined" || !ticker) return
        const p = (reportPath || DEFAULT_REPORT).replace(/\/+$/, "") || "/"
        window.location.href = p + "?q=" + encodeURIComponent(ticker)
    }

    const rows = useMemo(() => {
        const seed = (base: number, n: number, drift: number) => Array.from({ length: n }, (_, i) => base * (1 + Math.sin(i / 3) * 0.01 + (i / n) * drift))
        return GROUPS.map((g) => ({
            title: g.title,
            items: g.items.map((it) => {
                if (onCanvas) {
                    const demo: Record<string, [number, number]> = { kospi: [2950.4, 0.62], kosdaq: [845.1, -0.31], sp500: [7500.58, 1.08], nasdaq: [26517.93, 1.9], dow: [51564.7, 0.14], sox: [14341.78, 1.2], nikkei: [42180.0, 0.4], dax: [24310.5, -0.2], vix: [16.78, 2.31], usdkrw: [1531.5, 0.53], us_10y: [4.213, 0.0], us_2y: [3.842, 0.0], gold: [4174.3, -0.5], silver: [52.1, 0.8], copper: [4.62, 0.3], wti_oil: [78.4, -1.1], btc: [95026000, 0.6], eth: [2632000, -0.11], xrp: [1739, 0.06], sol: [111600, 0.81], doge: [126, 0.0] }
                    const [v, cp] = demo[it.key] || [100, 0]
                    return { ...it, value: v, change_pct: cp, change: undefined as any, spark: it.spark ? seed(v, 24, cp / 100) : null, hasVal: true, pending: false }
                }
                const node = it.src === "pulse" ? dig(pulse, "indices." + it.key) : (M ? M[it.key] : undefined)
                const value = node && node.value
                const change_pct = node && (node.change_pct != null ? node.change_pct : node.change_percent)
                const change = node && node.change
                const sn = it.spark ? dig(M, it.spark) : undefined
                const arr = sn && Array.isArray(sn.sparkline) ? sn.sparkline.map((x: any) => Number(x)).filter((x: number) => isFinite(x)) : null
                const hasVal = value != null && isFinite(Number(value)) && Number(value) !== 0
                // 값 소스(pulse=값, macro=값) 아직 안 온 아이템 = pending(스켈레톤). 로드 끝났는데 값 없으면 absent(드롭).
                const srcLoaded = it.src === "pulse" ? pulseLoaded : macroLoaded
                return { ...it, value, change_pct, change, spark: arr && arr.length >= 2 ? arr : null, hasVal, pending: !hasVal && !srcLoaded }
            }).filter((it: any) => it.hasVal || it.pending),
        })).filter((g) => g.items.length > 0)
    }, [pulse, M, onCanvas, pulseLoaded, macroLoaded])

    const narrow = w > 0 && w < 560
    const cols = w <= 0 ? 4 : w < 440 ? 2 : w < 700 ? 3 : w < 1000 ? 4 : 5
    const pad = narrow ? 11 : 15

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", overflowX: "hidden",
        background: C.bg, fontFamily: FONT, padding: pad, boxSizing: "border-box", color: C.ink,
    }

    const card = (it: any) => {
        const cp = Number(it.change_pct)
        const col = !isFinite(cp) ? C.flat : cp > 0 ? C.up : cp < 0 ? C.down : C.flat
        const sign = isFinite(cp) && cp > 0 ? "+" : ""
        const expoHit = expoData && expoData[it.key] && Number(expoData[it.key].count) > 0
        const open = openCommodity === it.key
        const openD = openDetail === it.key
        // 상세 패널이 카드보다 더 줄 게 있을 때만 클릭 가능 (추세선·상관·절대변동). 없으면(코스피·코스닥 등) 비활성 — 같은 정보 반복 방지.
        const hasDetail = !!(it.spark && it.spark.length >= 2) || !!assetCorr(it.key) || (it.change != null && isFinite(Number(it.change)))
        const detailable = it.value != null && hasDetail
        const clickable = expoHit || detailable
        const onCardClick = expoHit
            ? () => { setOpenDetail(""); setOpenCommodity(open ? "" : it.key) }
            : (detailable ? () => { setOpenCommodity(""); setOpenDetail(openD ? "" : it.key) } : undefined)
        return (
            <div key={it.key} onClick={onCardClick}
                style={{ background: (open || openD) ? C.chipBg : C.card, borderRadius: 11, padding: "8px 10px", boxShadow: (open || openD) ? "inset 0 1px 3px rgba(0,0,0,0.12)" : "0 1px 2px rgba(0,0,0,0.04)", display: "flex", alignItems: "center", gap: 9, minWidth: 0, cursor: clickable ? "pointer" : "default", transition: "background 0.12s, box-shadow 0.12s" }}>
                {it.spark && <Spark data={it.spark} color={col} w={40} h={24} />}
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: C.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {it.name}{expoHit && <span style={{ marginLeft: 4, fontSize: 9.5, fontWeight: 700, color: C.cPos }}>·{expoData[it.key].count}</span>}
                    </div>
                    <div style={{ fontSize: 15, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px", marginTop: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{fmtNum(it.value, it.dec ?? 2)}{it.unit || ""}</div>
                    <div style={{ fontSize: 11, fontWeight: 800, color: col, marginTop: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {isFinite(cp) ? `${sign}${cp.toFixed(2)}%` : "—"}
                    </div>
                </div>
                {expoHit && <span style={{ flexShrink: 0, fontSize: 12, color: open ? C.cPos : C.faint, fontWeight: 700 }}>{open ? "−" : "›"}</span>}
            </div>
        )
    }

    // 원자재 → KR 노출 종목 패널 (엣지 2)
    const exposurePanel = () => {
        const e = expoData && openCommodity ? expoData[openCommodity] : null
        if (!e) return null
        const stocks = e.stocks || []
        return (
            <div style={{ background: C.card, borderRadius: 11, padding: "10px 12px", boxShadow: "0 1px 2px rgba(0,0,0,0.04)", marginTop: 8, marginBottom: 2, border: `1px solid ${C.line}` }}>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 800, color: C.ink }}>{e.label} — KR 노출 <span style={{ color: C.cPos }}>{e.count}</span></span>
                    <span onClick={() => setOpenCommodity("")} style={{ cursor: "pointer", fontSize: 13, color: C.faint, fontWeight: 700 }}>×</span>
                </div>
                <div style={{ fontSize: 10.5, color: C.sub, fontWeight: 600, marginTop: 2, lineHeight: 1.45 }}>{e.note}</div>
                {stocks.length === 0 ? (
                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700, padding: "8px 0 2px" }}>KR 상장 노출 종목 없음 (제한적)</div>
                ) : (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                        {stocks.map((s: any) => (
                            <span key={s.ticker} onClick={() => go(s.ticker)} role="button" tabIndex={0}
                                style={{ display: "inline-flex", alignItems: "baseline", gap: 5, background: C.chipBg, borderRadius: 8, padding: "5px 9px", cursor: "pointer", border: `1px solid ${C.line}` }}>
                                <span style={{ fontSize: 12, fontWeight: 700, color: C.ink }}>{s.name}</span>
                                <span style={{ fontSize: 9.5, fontWeight: 600, color: C.faint }}>{s.industry}</span>
                            </span>
                        ))}
                    </div>
                )}
                <div style={{ fontSize: 9.5, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.45 }}>산업 멤버십 사실 · 시총순 · 누르면 리포트</div>
            </div>
        )
    }

    // 자산의 최대 상관 페어 (cac.matrix 에서)
    const assetCorr = (key: string) => {
        if (!cac || !cac.matrix) return null
        const row = cac.matrix[key]
        if (!row || typeof row !== "object") return null
        let best: { k: string; v: number } | null = null
        for (const k in row) {
            const v = Number(row[k])
            if (!isFinite(v)) continue
            if (!best || Math.abs(v) > Math.abs(best.v)) best = { k, v }
        }
        return best
    }

    // 시세 카드 상세 — 큰 추세선 + 절대변동 + 시계열 파생 사실 1줄 (자체 계산, 해석·추천 아님)
    const detailPanel = (it: any) => {
        const cp = Number(it.change_pct)
        const col = !isFinite(cp) ? C.flat : cp > 0 ? C.up : cp < 0 ? C.down : C.flat
        const s: number[] | null = it.spark && it.spark.length >= 2 ? it.spark : null
        let trail: string | null = null
        if (s) {
            const first = s[0], last = s[s.length - 1]
            const min = Math.min(...s), max = Math.max(...s)
            const chg = first ? ((last - first) / Math.abs(first)) * 100 : 0
            const posInRange = (max - min) ? ((last - min) / (max - min)) * 100 : 50
            trail = `최근 ${s.length}봉 ${chg >= 0 ? "+" : ""}${chg.toFixed(1)}% · 구간 저점대비 ${posInRange.toFixed(0)}% 지점`
        }
        const corr = assetCorr(it.key)
        const chgAbs = it.change != null && isFinite(Number(it.change)) ? Number(it.change) : null
        return (
            <div onClick={(e) => e.stopPropagation()} style={{ background: C.card, borderRadius: 11, padding: "10px 12px", boxShadow: "0 1px 2px rgba(0,0,0,0.04)", marginTop: 8, marginBottom: 2, border: `1px solid ${C.line}` }}>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 800, color: C.ink }}>{it.name} 상세</span>
                    <span onClick={() => setOpenDetail("")} style={{ cursor: "pointer", fontSize: 13, color: C.faint, fontWeight: 700 }}>×</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 9, flexWrap: "wrap" }}>
                    {s && <Spark data={s} color={col} w={130} h={42} />}
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <span style={{ fontSize: 19, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px" }}>{fmtNum(it.value, it.dec ?? 2)}{it.unit || ""}</span>
                        <span style={{ fontSize: 12.5, fontWeight: 800, color: col }}>
                            {chgAbs != null ? `${chgAbs > 0 ? "+" : ""}${fmtNum(chgAbs, it.dec ?? 2)} · ` : ""}
                            {isFinite(cp) ? `${cp > 0 ? "+" : ""}${cp.toFixed(2)}%` : "—"}
                        </span>
                    </div>
                </div>
                {trail && (
                    <div style={{ marginTop: 9, padding: "7px 10px", background: C.bg, borderRadius: 8, fontSize: 11.5, fontWeight: 700, color: C.sub }}>{trail}</div>
                )}
                {corr && CORR_LABELS[corr.k] && (
                    <div style={{ marginTop: 6, fontSize: 11, fontWeight: 700, color: C.sub }}>
                        {(cac.window_days || 30)}일 상관 최대 · {CORR_LABELS[corr.k]} {corr.v > 0 ? "+" : ""}{corr.v.toFixed(2)} ({corr.v >= 0 ? "동행" : "역행"})
                    </div>
                )}
                <div style={{ fontSize: 9.5, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.45 }}>시세 시계열로 계산한 사실</div>
            </div>
        )
    }

    // 자산 간 상관 (엣지 1)
    const corrSection = () => {
        if (!cac || !cac.matrix) return null
        const items = CORR_PAIRS.map(([a, b]) => {
            const v = dig(cac, `matrix.${a}.${b}`)
            return v == null ? null : { a, b, v: Number(v) }
        }).filter(Boolean) as { a: string; b: string; v: number }[]
        if (!items.length) return null
        const strength = (x: number) => { const ax = Math.abs(x); return ax >= 0.5 ? "강함" : ax >= 0.3 ? "보통" : "약함" }
        return (
            <div style={{ marginBottom: 12 }}>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "0 2px 6px", gap: 8 }}>
                    <span style={{ fontSize: 11.5, fontWeight: 800, color: C.faint, display: "inline-flex", alignItems: "center", gap: 5 }}>
                        자산 간 상관 {cac.window_days ? `(${cac.window_days}일)` : ""}
                        <span style={{ position: "relative", display: "inline-block" }}>
                            <span role="button" tabIndex={0}
                                onMouseEnter={() => setCorrTip(true)} onMouseLeave={() => setCorrTip(false)}
                                onClick={(e) => { e.stopPropagation(); setCorrTip((v) => !v) }}
                                style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 14, height: 14, borderRadius: "50%", background: "#6c5ce7", color: "#fff", fontSize: 9, fontWeight: 700, lineHeight: 1, cursor: "help" }}>i</span>
                            {corrTip && (
                                <span onClick={(e) => e.stopPropagation()} style={{ position: "absolute", top: "calc(100% + 5px)", left: 0, zIndex: 50, display: "block", width: 246, background: C.tipBg, color: "#fff", borderRadius: 10, padding: "10px 12px", fontSize: 11.5, fontWeight: 500, lineHeight: 1.55, boxShadow: "0 6px 20px rgba(0,0,0,0.18)", whiteSpace: "normal", textAlign: "left" }}>
                                    <span style={{ fontWeight: 700, color: C.cPos, display: "block", marginBottom: 3 }}>자산 간 상관 ({cac.window_days || 30}일)</span>
                                    두 자산이 최근 같이 움직인 정도예요. <b>+1</b>=완전히 같이, <b>0</b>=무관, <b>−1</b>=정반대. 분산·헤지 볼 때 참고하는 사실이고, 미래 예측은 아니에요.
                                </span>
                            )}
                        </span>
                    </span>
                    <span style={{ fontSize: 9.5, fontWeight: 600, color: C.faint }}>+동행 / −역행 · 시세로 계산</span>
                </div>
                <div style={{ background: C.card, borderRadius: 11, padding: "4px 12px", boxShadow: "0 1px 2px rgba(0,0,0,0.04)" }}>
                    {items.map((it, i) => (
                        <div key={it.a + it.b} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                            <span style={{ flexShrink: 0, width: 108, fontSize: 12, fontWeight: 700, color: C.ink }}>{CORR_LABELS[it.a]} <span style={{ color: C.faint }}>↔</span> {CORR_LABELS[it.b]}</span>
                            <CorrBar v={it.v} C={C} />
                            <span style={{ flexShrink: 0, width: 80, textAlign: "right", fontSize: 12, fontWeight: 800, fontVariantNumeric: "tabular-nums", color: it.v >= 0 ? C.cPos : C.cNeg }}>
                                {(it.v > 0 ? "+" : "") + it.v.toFixed(2)} <span style={{ fontSize: 9.5, color: C.faint, fontWeight: 600 }}>{strength(it.v)}</span>
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        )
    }

    // 로딩 스켈레톤 — 실제 카드 그리드(지수/환율/원자재/크립토)와 같은 형태. shimmer 회색 카드.
    const isDark = onCanvas ? !!dark : themeDark
    const skBase = isDark ? "#222a33" : "#e9edf1"
    const skHi = isDark ? "#2d3742" : "#f3f5f7"
    const skBlock = (bw: number | string, bh: number, mt?: number): CSSProperties => ({
        width: bw, height: bh, marginTop: mt, borderRadius: 5,
        background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%",
        animation: "vsrShimmer 1.4s ease-in-out infinite",
    })
    // 단일 스켈레톤 타일 — 로딩 중 아이템 자리(카드와 동일 레이아웃). macro 늦어도 원자재·크립토·SOX 등 자리 유지.
    const skTile = (key: string) => (
        <div key={key} style={{ background: C.card, borderRadius: 11, padding: "8px 10px", boxShadow: "0 1px 2px rgba(0,0,0,0.04)", display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
            <div style={skBlock(40, 24)} />
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={skBlock("60%", 11)} />
                <div style={skBlock("80%", 15, 4)} />
                <div style={skBlock("40%", 11, 4)} />
            </div>
        </div>
    )

    const skeleton = () => {
        const skGroups: number[] = [2, 6, 4]  // 국내 / 해외 지수 / 변동성·환율 카드 수 (12장)
        let n = 0
        return (
            <div>
                {skGroups.map((cnt, gi) => (
                    <div key={gi} style={{ marginBottom: 12 }}>
                        <div style={skBlock(54, 11)} />
                        <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: 8, marginTop: 5 }}>
                            {Array.from({ length: cnt }).map((_, i) => (
                                <div key={n++} style={{ background: C.card, borderRadius: 11, padding: "8px 10px", boxShadow: "0 1px 2px rgba(0,0,0,0.04)", display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
                                    <div style={skBlock(40, 24)} />
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={skBlock("60%", 11)} />
                                        <div style={skBlock("80%", 15, 4)} />
                                        <div style={skBlock("40%", 11, 4)} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        )
    }

    return (
        <div ref={rootRef} style={wrap}>
            <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.4px" }}>글로벌 시세</span>
                <span style={{ fontSize: 10.5, fontWeight: 600, color: C.faint }}>지수·환율·원자재·크립토 · 사실</span>
            </div>

            {rows.length === 0 ? (
                skeleton()
            ) : (
                rows.map((g) => (
                    <div key={g.title} style={{ marginBottom: 12 }}>
                        <div style={{ fontSize: 11, fontWeight: 800, color: C.faint, padding: "0 2px 5px" }}>
                            {g.title}{g.title === "원자재" ? <span style={{ marginLeft: 6, fontWeight: 600, color: C.cPos }}>· 누르면 KR 노출 종목</span> : ""}
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: 8 }}>
                            {g.items.map((it: any) => it.pending ? skTile("sk:" + it.key) : card(it))}
                        </div>
                        {g.title === "원자재" && exposurePanel()}
                        {openDetail && g.items.some((it: any) => it.key === openDetail) && detailPanel(g.items.find((it: any) => it.key === openDetail))}
                    </div>
                ))
            )}

            {corrSection()}

            <div style={{ fontSize: 10, color: C.faint, fontWeight: 600, marginTop: 2, lineHeight: 1.5 }}>
                추세선 = 실제 30일 시계열 보유 지표만 · 상관 = 가격 시계열로 계산한 사실 · 원자재 노출 = 산업 멤버십(수혜 아님) · 상승 빨강/하락 파랑 · 출처 yfinance·FRED·KIS·업비트
            </div>
        </div>
    )
}

addPropertyControls(PublicMarketBoard, {
    pulseUrl: { type: ControlType.String, title: "Pulse URL", defaultValue: DEFAULT_PULSE },
    macroUrl: { type: ControlType.String, title: "Macro URL", defaultValue: DEFAULT_MACRO },
    commodityUrl: { type: ControlType.String, title: "Commodity URL", defaultValue: DEFAULT_EXPO },
    reportPath: { type: ControlType.String, title: "Report Path", defaultValue: DEFAULT_REPORT },
    refreshSec: { type: ControlType.Number, title: "Refresh(s)", defaultValue: 60, min: 15, max: 600, step: 5 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

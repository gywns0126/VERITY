"use client"
// MarketStrip — 상단 지수 스트립. 공개 사실(macro_snapshot, 약 30분 주기)만. 외곽선 0.
// v3.4 (PM 2026-08-03 "그래프 세로로 배치, 각 시세 누르면 상세 그래프"):
//   카드 내부 = 세로 스택(이름 → 값·등락 한 줄 → 전폭 그래프). 카드 클릭 = ChartModal
//   (크립토=Binance 분봉 실시간 / 지수·환율=수집 시계열 확대). BTC/ETH = 코스닥 옆 상주(5초 tick).
import { useEffect, useRef, useState } from "react"
import { useDark, palette, FONT, NUM, type Palette } from "@/lib/theme"
import { fetchPublic, fetchRailway } from "@/lib/api"
import ChartModal, { type ChartTarget } from "./ChartModal"
import type { MarketExplain } from "@/lib/types"

const IDX_POLL_MS = 10000 // KR 지수 실시간 — Railway /index_quotes (KIS 공유토큰 소비, RULE 1 안전)

type IdxQuote = { price?: number; change?: number; change_pct?: number }

const LEAD: Array<{ key: string; name: string; unit?: string }> = [
    { key: "kospi", name: "코스피" },
    { key: "kosdaq", name: "코스닥" },
]
const REST: Array<{ key: string; name: string; unit?: string }> = [
    { key: "nasdaq", name: "나스닥" },
    { key: "sp500", name: "S&P 500" },
    { key: "sox", name: "필라델피아 반도체" },
    { key: "vix", name: "VIX" },
    { key: "usd_krw", name: "달러 환율", unit: "원" },
    { key: "us_10y", name: "미 10년물", unit: "%" },
]

const CRYPTO_ENDPOINT =
    'https://data-api.binance.vision/api/v3/ticker/24hr?symbols=["BTCUSDT","ETHUSDT"]'
const CRYPTO_POLL_MS = 5000
const CRYPTO_NAMES: Record<string, string> = { BTCUSDT: "비트코인", ETHUSDT: "이더리움" }

type Node = { value?: number; change_pct?: number; change_percent?: number; sparkline?: number[] }
type CryptoRow = { symbol: string; lastPrice?: string; priceChangePercent?: string }

// 전폭 스파크 — viewBox 정규화(0~100) + width 100%
function Spark({ data, color }: { data: number[]; color: string }) {
    if (!data || data.length < 2) return null
    const W = 100, H = 26, PAD = 1.5
    const mn = Math.min(...data), mx = Math.max(...data), rng = mx - mn || 1
    const pts = data.map((v, i) => `${((i / (data.length - 1)) * W).toFixed(1)},${(H - PAD - ((v - mn) / rng) * (H - PAD * 2)).toFixed(1)}`)
    return (
        <svg width="100%" height={26} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: "block" }}>
            {/* area fill — 알파네스트 차트 문법 (라인만 = 밋밋) */}
            <polyline points={`0,${H - PAD} ${pts.join(" ")} ${W},${H - PAD}`} fill={color} opacity={0.09} stroke="none" />
            <polyline points={pts.join(" ")} fill="none" strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" style={{ stroke: color }} />
        </svg>
    )
}

export default function MarketStrip({ explain }: { explain?: MarketExplain }) {
    const dark = useDark()
    const c = palette(dark)
    const [m, setM] = useState<Record<string, Node>>({})
    const [crypto, setCrypto] = useState<CryptoRow[]>([])
    const [idxLive, setIdxLive] = useState<Record<string, IdxQuote>>({})
    const [target, setTarget] = useState<ChartTarget | null>(null)
    const prevPx = useRef<Record<string, number>>({})

    useEffect(() => {
        let cancelled = false
        fetchPublic<{ macro?: Record<string, Node> }>("macro_snapshot.json").then((r) => {
            if (cancelled) return
            setM((r.ok && (r.data.macro || (r.data as unknown as Record<string, Node>))) || {})
        })
        async function pull() {
            try {
                const r = await fetch(CRYPTO_ENDPOINT, { cache: "no-store" })
                if (!r.ok) return
                const d = await r.json()
                if (!cancelled && Array.isArray(d)) setCrypto(d)
            } catch {}
        }
        pull()
        const t = setInterval(pull, CRYPTO_POLL_MS)
        // KR 지수 실시간 (PM "레일웨이 돈 주고 쓰는데 당연히") — 값 0/실패 = macro_snapshot 유지
        async function pullIdx() {
            const r = await fetchRailway<{ quotes?: Record<string, IdxQuote> }>("index_quotes")
            if (!cancelled && r.ok && r.data.quotes) setIdxLive(r.data.quotes)
        }
        pullIdx()
        const t2 = setInterval(pullIdx, IDX_POLL_MS)
        return () => {
            cancelled = true
            clearInterval(t)
            clearInterval(t2)
        }
    }, [])

    useEffect(() => {
        crypto.forEach((r) => {
            const p = parseFloat(r.lastPrice || "")
            if (isFinite(p)) prevPx.current[r.symbol] = p
        })
        Object.keys(idxLive).forEach((k) => {
            const p = idxLive[k]?.price
            if (typeof p === "number" && p > 0) prevPx.current[`idx:${k}`] = p
        })
    })

    // 카드 = 세로 스택: 이름 / 값·등락 / 전폭 그래프. 클릭 = 상세 차트.
    function Card({ name, tag, value, cp, spark, flashKey, dir, onOpen }: { name: string; tag?: string; value: string; cp: number | null; spark?: number[]; flashKey?: string; dir?: string; onOpen: () => void }) {
        const col = cp == null ? c.faint : cp > 0 ? c.up : cp < 0 ? c.down : c.faint
        const sign = cp != null && cp > 0 ? "+" : ""
        return (
            <div
                onClick={onOpen}
                style={{ background: c.card, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", padding: "9px 12px 7px", display: "flex", flexDirection: "column", gap: 3, minWidth: 0, cursor: "pointer" }}
            >
                <div style={{ fontSize: 10.5, fontWeight: 700, color: c.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {name}{tag ? <span style={{ color: c.faint, fontWeight: 500 }}> {tag}</span> : null}
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6, whiteSpace: "nowrap" }}>
                    <span key={flashKey} className={dir ? `af-flash-${dir}` : undefined} style={{ fontSize: 14, fontWeight: 800, color: c.ink, ...NUM, whiteSpace: "nowrap" }}>
                        {value}
                    </span>
                    <span style={{ fontSize: 10.5, fontWeight: 700, color: col, ...NUM, whiteSpace: "nowrap", flexShrink: 0 }}>
                        {cp != null ? `${sign}${cp.toFixed(2)}%` : ""}
                    </span>
                </div>
                {spark && spark.length > 1 ? <Spark data={spark} color={col} /> : <div style={{ height: 26 }} />}
            </div>
        )
    }

    function idx(k: string, name: string, unit?: string) {
        const n = m[k] || {}
        // KR 지수 = Railway 실시간 우선 (KIS 10초), 실패/0 = 스냅샷 폴백
        const live = idxLive[k]
        const liveOk = live && typeof live.price === "number" && live.price > 0
        const v = liveOk ? (live.price as number) : typeof n.value === "number" ? n.value : null
        const cp = liveOk && typeof live.change_pct === "number"
            ? live.change_pct
            : typeof n.change_pct === "number" ? n.change_pct : typeof n.change_percent === "number" ? n.change_percent : null
        const was = prevPx.current[`idx:${k}`]
        const dir = liveOk && typeof was === "number" && v !== null && v !== was ? (v > was ? "up" : "dn") : ""
        return (
            <Card
                key={k}
                name={name}
                tag={liveOk ? "실시간" : undefined}
                value={v != null ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) + (unit || "") : "—"}
                cp={cp}
                spark={n.sparkline}
                flashKey={liveOk ? `${k}-${v}` : undefined}
                dir={dir}
                onOpen={() =>
                    setTarget(
                        k === "kospi" || k === "kosdaq"
                            ? { kind: "krindex", name, indexCd: k === "kospi" ? "0001" : "1001", value: v, changePct: cp, explain }
                            : { kind: "macro", name, unit, series: n.sparkline || [], value: v, changePct: cp }
                    )
                }
            />
        )
    }

    return (
        <div style={{ fontFamily: FONT, marginBottom: 12 }}>
            <div className="af-mkt" style={{ marginBottom: 0 }}>
                {LEAD.map(({ key, name, unit }) => idx(key, name, unit))}
                {crypto.map((row) => {
                    const px = parseFloat(row.lastPrice || "")
                    const cp = parseFloat(row.priceChangePercent || "")
                    const was = prevPx.current[row.symbol]
                    const dir = isFinite(px) && typeof was === "number" && px !== was ? (px > was ? "up" : "dn") : ""
                    const name = CRYPTO_NAMES[row.symbol] || row.symbol
                    return (
                        <Card
                            key={row.symbol}
                            name={name}
                            tag="실시간"
                            value={isFinite(px) ? "$" + px.toLocaleString(undefined, { maximumFractionDigits: px >= 1000 ? 0 : 2 }) : "—"}
                            cp={isFinite(cp) ? cp : null}
                            flashKey={`${row.symbol}-${row.lastPrice}`}
                            dir={dir}
                            onOpen={() => setTarget({ kind: "crypto", name, symbol: row.symbol, value: isFinite(px) ? px : null, changePct: isFinite(cp) ? cp : null })}
                        />
                    )
                })}
                {REST.map(({ key, name, unit }) => idx(key, name, unit))}
            </div>
            <div style={{ fontSize: 9.5, color: c.faint, padding: "5px 2px 0" }}>
                카드 클릭 = 상세 차트 · KR 지수 = 실시간(KIS 10초) · 크립토 = 실시간(5초) · 미장·환율·금리 = 약 30분 주기, 미장은 장중 외 전일 종가
            </div>
            {target ? <ChartModal target={target} onClose={() => setTarget(null)} /> : null}
        </div>
    )
}

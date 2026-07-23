import { addPropertyControls, ControlType } from "framer"
import { useEffect, useMemo, useRef, useState } from "react"

/**
 * 실시간 시세 차트 — 공개 probe (토스 디자인 언어)
 * 기존 인프라 100% 재사용: Railway KIS WS → SSE /stream/{ticker}, 폴백 = 공개 recommendations.json sparkline.
 * 점수·추천 없음 (RULE 7). 실 KR 6자리 ticker 만 스트리밍.
 */

const C = {
  bg: "#f2f4f6",
  card: "#ffffff",
  ink: "#191f28",
  sub: "#4e5968",
  faint: "#8b95a1",
  line: "#e5e8eb",
  grid: "#eef1f4",
  red: "#f04452",
  blue: "#3182f6",
}
const UP = C.red
const DOWN = C.blue

const RELAY = "https://verity-production-1e44.up.railway.app"
const REC_URL =
  "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/recommendations.json"
const KR_TICKER_RE = /^[0-9]{6}$/

const STOCKS: { name: string; ticker: string }[] = [
  { name: "삼성전자", ticker: "005930" },
  { name: "SK하이닉스", ticker: "000660" },
  { name: "에코프로비엠", ticker: "247540" },
  { name: "현대차", ticker: "005380" },
]

interface Candle {
  o: number
  h: number
  l: number
  c: number
  up: boolean
  vol?: number
}

function fmtPrice(n: number): string {
  if (!Number.isFinite(n)) return "—"
  return Math.round(n).toLocaleString("ko-KR")
}

function fmtAxis(n: number): string {
  if (n >= 1e4) return `${(n / 1e4).toFixed(n >= 1e5 ? 0 : 1)}만`
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return String(Math.round(n))
}

function CandleChart({ candles }: { candles: Candle[] }) {
  const w = 600,
    h = 240
  if (!candles || candles.length < 2) return null
  const hasVol = candles.some((c) => (c.vol || 0) > 0)
  const volH = hasVol ? h * 0.18 : 0
  const chartH = h - volH
  const padT = 12,
    padB = 8,
    padR = 52,
    padL = 4
  const usableW = w - padL - padR
  const usableH = chartH - padT - padB

  const mn = Math.min(...candles.map((c) => c.l))
  const mx = Math.max(...candles.map((c) => c.h))
  const rng = mx - mn || 1
  const step = usableW / candles.length
  const gap = Math.max(1, step * 0.15)
  const bodyW = Math.max(1.5, step - gap)
  const xC = (i: number) => padL + i * step + step / 2
  const yOf = (v: number) => padT + (1 - (v - mn) / rng) * usableH

  const grid: { y: number; label: string }[] = []
  for (let g = 0; g <= 4; g++) {
    const val = mn + (rng * g) / 4
    grid.push({ y: yOf(val), label: fmtAxis(val) })
  }
  const maxVol = hasVol ? Math.max(...candles.map((c) => c.vol || 0), 1) : 1

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ display: "block" }}
    >
      {grid.map((g, i) => (
        <g key={i}>
          <line x1={padL} y1={g.y} x2={w - padR + 4} y2={g.y} stroke={C.grid} strokeWidth={1} />
          <text x={w - padR + 8} y={g.y + 3.5} fill={C.faint} fontSize={9}>
            {g.label}
          </text>
        </g>
      ))}
      {candles.map((c, i) => {
        const x = xC(i),
          yH = yOf(c.h),
          yL = yOf(c.l),
          yO = yOf(c.o),
          yClose = yOf(c.c)
        const bT = Math.min(yO, yClose),
          bB = Math.max(yO, yClose),
          bH = Math.max(1, bB - bT)
        const clr = c.up ? UP : DOWN
        return (
          <g key={i}>
            <line x1={x} y1={yH} x2={x} y2={yL} stroke={clr} strokeWidth={1} />
            <rect x={x - bodyW / 2} y={bT} width={bodyW} height={bH} fill={clr} opacity={0.95} rx={0.5} />
          </g>
        )
      })}
      {hasVol && (
        <g>
          <line x1={padL} y1={chartH} x2={w - padR + 4} y2={chartH} stroke={C.grid} strokeWidth={1} />
          {candles.map((c, i) => {
            const barH = ((c.vol || 0) / maxVol) * (volH - 4)
            return (
              <rect
                key={i}
                x={xC(i) - bodyW / 2}
                y={h - barH - 2}
                width={bodyW}
                height={barH}
                fill={c.up ? UP : DOWN}
                opacity={0.4}
                rx={0.5}
              />
            )
          })}
        </g>
      )}
    </svg>
  )
}

function MiniLine({ data }: { data: number[] }) {
  const w = 600,
    h = 240
  if (!data || data.length < 2) return null
  const padT = 14,
    padB = 16,
    padR = 52,
    padL = 4
  const usableW = w - padL - padR
  const usableH = h - padT - padB
  const mn = Math.min(...data),
    mx = Math.max(...data),
    rng = mx - mn || 1
  const xOf = (i: number) => padL + (i / (data.length - 1)) * usableW
  const yOf = (v: number) => padT + (1 - (v - mn) / rng) * usableH
  const up = data[data.length - 1] >= data[0]
  const clr = up ? UP : DOWN
  const pts = data.map((v, i) => `${xOf(i)},${yOf(v)}`).join(" ")
  const fill = `${xOf(0)},${padT + usableH} ${pts} ${xOf(data.length - 1)},${padT + usableH}`
  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ display: "block" }}
    >
      <defs>
        <linearGradient id="rcp_fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={clr} stopOpacity={0.22} />
          <stop offset="100%" stopColor={clr} stopOpacity={0.02} />
        </linearGradient>
      </defs>
      <polygon points={fill} fill="url(#rcp_fill)" />
      <polyline points={pts} fill="none" stroke={clr} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

function useRecData() {
  const [map, setMap] = useState<Record<string, any>>({})
  useEffect(() => {
    let alive = true
    fetch(REC_URL)
      .then((r) => (r.ok ? r.json() : []))
      .then((arr: any[]) => {
        if (!alive || !Array.isArray(arr)) return
        const m: Record<string, any> = {}
        for (const r of arr) {
          const t = String(r?.ticker || "").padStart(6, "0")
          if (t) m[t] = r
        }
        setMap(m)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])
  return map
}

function useLiveChart(ticker: string) {
  const [candles, setCandles] = useState<Candle[]>([])
  const [price, setPrice] = useState<number | null>(null)
  const [connected, setConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    setCandles([])
    setPrice(null)
    setConnected(false)
    if (!KR_TICKER_RE.test(ticker)) return

    let disposed = false
    let retry = 0
    let timer: any = null

    const schedule = () => {
      if (disposed || retry >= 8) return
      const d = Math.min(30000, 1000 * Math.pow(2, retry))
      retry++
      timer = setTimeout(connect, d)
    }

    const connect = () => {
      if (disposed) return
      try {
        const es = new EventSource(`${RELAY}/stream/${ticker}`)
        esRef.current = es
        es.onopen = () => {
          setConnected(true)
          retry = 0
        }
        es.onerror = () => {
          setConnected(false)
          es.close()
          esRef.current = null
          schedule()
        }
        es.addEventListener("candles", (e: MessageEvent) => {
          try {
            const arr = JSON.parse(e.data)
            if (Array.isArray(arr) && arr.length > 0) {
              const mapped = arr.map((c: any) => ({
                o: c.o,
                h: c.h,
                l: c.l,
                c: c.c,
                up: c.c >= c.o,
                vol: c.vol || 0,
              }))
              setCandles(mapped)
              setPrice(mapped[mapped.length - 1].c)
            }
          } catch {}
        })
        es.addEventListener("candle", (e: MessageEvent) => {
          try {
            const c = JSON.parse(e.data)
            if (c.o && c.h && c.l && c.c) {
              setCandles((prev) =>
                [...prev, { o: c.o, h: c.h, l: c.l, c: c.c, up: c.c >= c.o, vol: c.vol || 0 }].slice(-240)
              )
              setPrice(c.c)
            }
          } catch {}
        })
        es.addEventListener("trade", (e: MessageEvent) => {
          try {
            const t = JSON.parse(e.data)
            const p = Number(t.price)
            const vol = Number(t.volume) || 0
            if (!Number.isFinite(p) || p <= 0) return
            setPrice(p)
            setCandles((prev) => {
              if (prev.length === 0) return prev
              const last = { ...prev[prev.length - 1] }
              last.h = Math.max(last.h, p)
              last.l = Math.min(last.l, p)
              last.c = p
              last.up = p >= last.o
              last.vol = (last.vol || 0) + vol
              return [...prev.slice(0, -1), last]
            })
          } catch {}
        })
      } catch {
        schedule()
      }
    }
    connect()

    return () => {
      disposed = true
      if (timer) clearTimeout(timer)
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [ticker])

  return { candles, price, connected }
}

export default function RealtimeChartProbe(props: { width?: number }) {
  const [idx, setIdx] = useState(0)
  const s = STOCKS[idx]
  const rec = useRecData()
  const { candles, price, connected } = useLiveChart(s.ticker)

  const recRow = rec[s.ticker] || null
  const spark: number[] = useMemo(() => {
    const sp = recRow?.sparkline
    return Array.isArray(sp) ? sp.filter((x: any) => Number.isFinite(x)) : []
  }, [recRow])

  const hasLive = candles.length >= 2
  const basePrice = price ?? recRow?.current_price ?? recRow?.price ?? null
  const changePct: number | null = hasLive
    ? ((candles[candles.length - 1].c - candles[0].o) / candles[0].o) * 100
    : Number.isFinite(recRow?.change_pct)
    ? Number(recRow.change_pct)
    : null
  const chgClr = changePct == null ? C.faint : changePct >= 0 ? UP : DOWN

  return (
    <div
      style={{
        width: "100%",
        background: C.bg,
        fontFamily: "Pretendard, -apple-system, sans-serif",
        padding: 16,
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        {STOCKS.map((st, i) => (
          <button
            key={st.ticker}
            onClick={() => setIdx(i)}
            style={{
              border: "none",
              cursor: "pointer",
              padding: "7px 13px",
              borderRadius: 999,
              fontSize: 13,
              fontWeight: 600,
              background: i === idx ? C.ink : C.card,
              color: i === idx ? "#fff" : C.sub,
            }}
          >
            {st.name}
          </button>
        ))}
      </div>

      <div style={{ background: C.card, borderRadius: 20, padding: 22, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 8, marginBottom: 14 }}>
          <div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span style={{ fontSize: 20, fontWeight: 700, color: C.ink, letterSpacing: "-0.4px" }}>{s.name}</span>
              <span style={{ fontSize: 13, color: C.faint, fontWeight: 500 }}>{s.ticker}</span>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 4 }}>
              <span style={{ fontSize: 26, fontWeight: 800, color: C.ink, letterSpacing: "-0.6px" }}>
                {basePrice != null ? `${fmtPrice(basePrice)}원` : "—"}
              </span>
              {changePct != null && (
                <span style={{ fontSize: 15, fontWeight: 700, color: chgClr }}>
                  {changePct >= 0 ? "▲" : "▼"} {Math.abs(changePct).toFixed(2)}%
                </span>
              )}
            </div>
          </div>
          <span
            style={{
              flexShrink: 0,
              fontSize: 11.5,
              fontWeight: 700,
              color: connected ? C.red : C.faint,
              background: connected ? "#fff0f1" : C.bg,
              padding: "4px 10px",
              borderRadius: 999,
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
            }}
          >
            <span style={{ fontSize: 9 }}>●</span>
            {connected ? "LIVE" : "장 마감"}
          </span>
        </div>

        <div style={{ width: "100%", height: 240 }}>
          {hasLive ? (
            <CandleChart candles={candles} />
          ) : spark.length >= 2 ? (
            <MiniLine data={spark} />
          ) : (
            <div
              style={{
                width: "100%",
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: C.faint,
                fontSize: 13,
                fontWeight: 500,
              }}
            >
              {connected ? "시세 수신 대기 중…" : "장 마감 · 시세 데이터 없음"}
            </div>
          )}
        </div>

        <div style={{ marginTop: 16, padding: "11px 14px", background: C.bg, borderRadius: 12 }}>
          <div style={{ fontSize: 12.5, color: C.faint, lineHeight: 1.5 }}>
            {hasLive
              ? "실시간 시세 (장중, 1분봉) · 사실 데이터"
              : "장 마감 — 최근 종가 추이 (sparkline)"}{" "}
            · 점수·추천 아님, 판단은 직접.
          </div>
        </div>
      </div>

      <div style={{ textAlign: "center", fontSize: 11, color: C.faint, marginTop: 12 }}>
        실시간 = 기존 KIS 중계 · 디자인 probe
      </div>
    </div>
  )
}

addPropertyControls(RealtimeChartProbe, {
  width: { type: ControlType.Number, title: "Width", defaultValue: 380, min: 320, max: 720 },
})

"use client"
// BalanceCard — 실계좌(KIS) 잔고 (태스크 #14-④). VAMS(모의)와 별개 — 라벨로 명확 구분.
// 경로 = vercel /api/order GET(Supabase JWT 검증 → Railway 프록시 → KIS TTTC8434R raw).
// KIS raw 방어 파싱: output2[0] 요약(예수금·총평가·평가손익) + output1[] 보유.
// 폴링 없음(잔고 API 남용 방지) — 1회 로드 + 수동 새로고침.
import { useCallback, useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, CARD_TITLE, RAIL_PAD } from "@/lib/theme"
import { API_BASE } from "@/lib/api"
import { authHeaders } from "@/lib/auth"
import StockLogo from "./StockLogo"
import { selectTicker } from "@/lib/types"

type KisRow = Record<string, string>
type Bal = {
    cash: number | null      // dnca_tot_amt 예수금
    totalEval: number | null // tot_evlu_amt 총평가
    pnl: number | null       // evlu_pfls_smtl_amt 평가손익 합계
    holdings: Array<{ ticker: string; name: string; qty: number; avg: number; px: number; pnlRt: number; evalAmt: number }>
}

function num(v: unknown): number {
    const n = parseFloat(String(v ?? "").replace(/,/g, ""))
    return isFinite(n) ? n : 0
}

function parse(d: Record<string, unknown>): Bal | { error: string } {
    if (String(d.rt_cd ?? "") !== "0" && d.rt_cd !== undefined) {
        return { error: String(d.msg1 || d.error || "잔고 조회 거부") }
    }
    const o2 = Array.isArray(d.output2) ? (d.output2[0] as KisRow) || {} : {}
    const o1 = Array.isArray(d.output1) ? (d.output1 as KisRow[]) : []
    const holdings = o1
        .filter((r) => num(r.hldg_qty) > 0)
        .map((r) => ({
            ticker: String(r.pdno || ""),
            name: String(r.prdt_name || r.pdno || ""),
            qty: num(r.hldg_qty),
            avg: num(r.pchs_avg_pric),
            px: num(r.prpr),
            pnlRt: num(r.evlu_pfls_rt),
            evalAmt: num(r.evlu_amt),
        }))
    return {
        cash: o2.dnca_tot_amt !== undefined ? num(o2.dnca_tot_amt) : null,
        totalEval: o2.tot_evlu_amt !== undefined ? num(o2.tot_evlu_amt) : null,
        pnl: o2.evlu_pfls_smtl_amt !== undefined ? num(o2.evlu_pfls_smtl_amt) : null,
        holdings,
    }
}

export default function BalanceCard() {
    const dark = useDark()
    const c = palette(dark)
    const [bal, setBal] = useState<Bal | null>(null)
    const [err, setErr] = useState("")
    const [busy, setBusy] = useState(false)

    const load = useCallback(async () => {
        setBusy(true)
        setErr("")
        try {
            const r = await fetch(`${API_BASE}/api/order?market=kr`, { headers: authHeaders(), cache: "no-store" })
            const d = await r.json().catch(() => ({}))
            if (!r.ok) {
                setErr(String((d as { error?: string }).error || `HTTP ${r.status}`).slice(0, 120))
                return
            }
            const p = parse(d as Record<string, unknown>)
            if ("error" in p) setErr(p.error.slice(0, 120))
            else setBal(p)
        } catch (e) {
            setErr(String((e as Error).message || e).slice(0, 100))
        } finally {
            setBusy(false)
        }
    }, [])

    useEffect(() => {
        load()
    }, [load])

    return (
        <div style={{ ...cardStyle(c, RAIL_PAD), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 5 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 3 }}>
                <span style={{ ...CARD_TITLE, color: c.ink }}>실계좌</span>
                <span style={{ fontSize: 10, color: c.faint }}>KIS 실잔고 · VAMS(모의)와 별개</span>
                <button onClick={load} disabled={busy} style={{ marginLeft: "auto", border: "none", background: c.hi, color: c.sub, borderRadius: 999, padding: "3px 10px", fontSize: 10, fontWeight: 700, cursor: busy ? "default" : "pointer", fontFamily: FONT }}>
                    {busy ? "조회 중" : "새로고침"}
                </button>
            </div>

            {err ? (
                <div style={{ fontSize: 11.5, color: c.sub, lineHeight: 1.5 }}>조회 불가 — {err}</div>
            ) : !bal ? (
                <div style={{ fontSize: 12, color: c.faint }}>불러오는 중…</div>
            ) : (
                <>
                    <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                        <Stat c={c.faint} ink={c.ink} k="총평가" v={bal.totalEval != null ? Math.round(bal.totalEval).toLocaleString() + "원" : "—"} />
                        <Stat c={c.faint} ink={c.ink} k="예수금" v={bal.cash != null ? Math.round(bal.cash).toLocaleString() + "원" : "—"} />
                        <Stat c={c.faint} ink={bal.pnl != null && bal.pnl > 0 ? "#f04452" : bal.pnl != null && bal.pnl < 0 ? "#3182f6" : c.ink} k="평가손익" v={bal.pnl != null ? `${bal.pnl > 0 ? "+" : ""}${Math.round(bal.pnl).toLocaleString()}원` : "—"} />
                    </div>
                    {bal.holdings.length ? (
                        bal.holdings.map((h, i) => {
                            const col = h.pnlRt > 0 ? "#f04452" : h.pnlRt < 0 ? "#3182f6" : c.faint
                            return (
                                <div key={h.ticker + i} onClick={() => selectTicker(h.ticker, h.name)} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 2px", borderTop: `1px solid ${c.line}`, cursor: "pointer" }}>
                                    <StockLogo ticker={h.ticker} name={h.name} size={20} />
                                    <div style={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1 }}>
                                        <span style={{ fontSize: 12, fontWeight: 700, color: c.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{h.name}</span>
                                        <span style={{ fontSize: 10, color: c.faint, ...NUM }}>{h.qty.toLocaleString()}주 · 평단 {Math.round(h.avg).toLocaleString()}</span>
                                    </div>
                                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", flexShrink: 0 }}>
                                        <span style={{ fontSize: 12, fontWeight: 800, color: c.ink, ...NUM }}>{Math.round(h.px).toLocaleString()}</span>
                                        <span style={{ fontSize: 10, fontWeight: 700, color: col, ...NUM }}>{h.pnlRt > 0 ? "+" : ""}{h.pnlRt.toFixed(1)}%</span>
                                    </div>
                                </div>
                            )
                        })
                    ) : (
                        <div style={{ fontSize: 11.5, color: c.sub, paddingTop: 2 }}>실계좌 보유 종목 없음.</div>
                    )}
                </>
            )}
            <div style={{ fontSize: 9.5, color: c.faint, paddingTop: 3 }}>수동 새로고침만(잔고 API 절약) · 사실</div>
        </div>
    )
}

function Stat({ c, ink, k, v }: { c: string; ink: string; k: string; v: string }) {
    return (
        <span style={{ fontSize: 11, color: c }}>
            {k} <span style={{ fontWeight: 800, color: ink, fontVariantNumeric: "tabular-nums" }}>{v}</span>
        </span>
    )
}

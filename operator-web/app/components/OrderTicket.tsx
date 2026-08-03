"use client"
// OrderTicket — 실주문 티켓 (PM 결함 #5). vercel /api/order 프록시 = Supabase JWT 검증 →
// profiles.order_enabled 게이트 → Railway(서버 시크릿) → KIS 실주문. 클라에 시크릿 0.
// 계약(1차 검증 order.py): {ticker, side:BUY/SELL, order_type:"00"지정가|"01"시장가, qty:int, price:int, market:"kr"}.
// 오발주 가드 = 2단 확정(4초 내 재클릭). 체결 확인 = 블로터(localStorage af_blotter) 기록.
import { useEffect, useState } from "react"
import { useDark, palette, FONT, NUM } from "@/lib/theme"
import { API_BASE } from "@/lib/api"
import { authHeaders } from "@/lib/auth"

type Props = { ticker: string; name?: string; presetPrice?: number | null; livePrice?: number | null }

export default function OrderTicket({ ticker, name, presetPrice, livePrice }: Props) {
    const dark = useDark()
    const c = palette(dark)
    const [side, setSide] = useState<"BUY" | "SELL">("BUY")
    const [otype, setOtype] = useState<"00" | "01">("00")
    const [qty, setQty] = useState("")
    const [price, setPrice] = useState("")
    const [arming, setArming] = useState(false)
    const [busy, setBusy] = useState(false)
    const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

    const isKR = /^\d{6}$/.test(ticker)

    // 호가 클릭 → 가격 채움 (스피드주문 문법)
    useEffect(() => {
        if (typeof presetPrice === "number" && presetPrice > 0) setPrice(String(Math.round(presetPrice)))
    }, [presetPrice])

    // 종목 전환 시 티켓 리셋 (오발주 방지)
    useEffect(() => {
        setQty("")
        setPrice("")
        setArming(false)
        setMsg(null)
    }, [ticker])

    useEffect(() => {
        if (!arming) return
        const t = setTimeout(() => setArming(false), 4000)
        return () => clearTimeout(t)
    }, [arming])

    const qn = parseInt(qty, 10) || 0
    const pn = otype === "01" ? 0 : parseInt(price, 10) || 0
    const estBase = otype === "01" ? (typeof livePrice === "number" ? livePrice : 0) : pn
    const est = qn * estBase
    const valid = isKR && qn > 0 && (otype === "01" || pn > 0)

    async function submit() {
        if (!valid || busy) return
        if (!arming) {
            setArming(true)
            setMsg(null)
            return
        }
        setArming(false)
        setBusy(true)
        try {
            const r = await fetch(`${API_BASE}/api/order`, {
                method: "POST",
                headers: { ...authHeaders(), "Content-Type": "application/json" },
                body: JSON.stringify({ ticker, side, order_type: otype, qty: qn, price: pn, market: "kr" }),
            })
            const d = await r.json().catch(() => ({}))
            const ok = r.ok && !d.error
            const detail = d.error || d.msg || d.message || (ok ? "접수" : `HTTP ${r.status}`)
            setMsg({ ok, text: ok ? `주문 접수 — ${side === "BUY" ? "매수" : "매도"} ${qn}주${pn ? ` @ ${pn.toLocaleString()}` : " (시장가)"}` : `거부 — ${String(detail).slice(0, 140)}` })
            // 블로터 기록
            try {
                const raw = localStorage.getItem("af_blotter")
                const arr = raw ? JSON.parse(raw) : []
                const entry = {
                    ts: new Date().toISOString(),
                    ticker,
                    name: name || ticker,
                    side,
                    order_type: otype,
                    qty: qn,
                    price: pn,
                    status: ok ? "접수" : "거부",
                    msg: String(detail).slice(0, 200),
                }
                const next = [entry, ...(Array.isArray(arr) ? arr : [])].slice(0, 50)
                localStorage.setItem("af_blotter", JSON.stringify(next))
                window.dispatchEvent(new Event("af-blotter"))
            } catch {}
        } catch (e) {
            setMsg({ ok: false, text: "요청 실패: " + String((e as Error).message || e).slice(0, 120) })
        } finally {
            setBusy(false)
        }
    }

    const seg = (active: boolean, col: string, colS: string) => ({
        flex: 1,
        border: "none",
        borderRadius: 9,
        padding: "8px 0",
        fontSize: 12.5,
        fontWeight: 800,
        fontFamily: FONT,
        cursor: "pointer",
        background: active ? colS : c.hi,
        color: active ? col : c.faint,
    })
    const inputSt = {
        width: "100%",
        boxSizing: "border-box" as const,
        background: dark ? c.bg : c.track,
        color: c.ink,
        border: "none",
        borderRadius: 10,
        padding: "9px 12px",
        fontSize: 13,
        fontFamily: FONT,
        outline: "none",
        fontVariantNumeric: "tabular-nums" as const,
    }

    if (!isKR) {
        return (
            <div style={{ fontFamily: FONT, fontSize: 11.5, color: c.sub, lineHeight: 1.55, background: c.hi, borderRadius: 12, padding: "12px 14px" }}>
                주문 티켓은 KR 종목만 지원합니다 (v1). US 주문은 후속.
            </div>
        )
    }

    return (
        <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", gap: 6 }}>
                <button onClick={() => setSide("BUY")} style={seg(side === "BUY", c.up, c.upS)}>매수</button>
                <button onClick={() => setSide("SELL")} style={seg(side === "SELL", c.down, c.downS)}>매도</button>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
                <button onClick={() => setOtype("00")} style={seg(otype === "00", c.vt, c.vtS)}>지정가</button>
                <button onClick={() => setOtype("01")} style={seg(otype === "01", c.vt, c.vtS)}>시장가</button>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
                <input value={qty} onChange={(e) => setQty(e.target.value.replace(/[^\d]/g, ""))} placeholder="수량" inputMode="numeric" style={inputSt} />
                <input
                    value={otype === "01" ? "" : price}
                    onChange={(e) => setPrice(e.target.value.replace(/[^\d]/g, ""))}
                    placeholder={otype === "01" ? "시장가" : "가격 (호가 클릭)"}
                    inputMode="numeric"
                    disabled={otype === "01"}
                    style={{ ...inputSt, opacity: otype === "01" ? 0.5 : 1 }}
                />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: c.sub }}>
                <span>예상 금액{otype === "01" ? " (현재가 기준)" : ""}</span>
                <span style={{ fontWeight: 800, color: c.ink, ...NUM }}>{est > 0 ? Math.round(est).toLocaleString() + "원" : "—"}</span>
            </div>
            <button
                onClick={submit}
                disabled={!valid || busy}
                style={{
                    border: "none",
                    borderRadius: 11,
                    padding: "11px 0",
                    fontSize: 13.5,
                    fontWeight: 800,
                    fontFamily: FONT,
                    cursor: valid && !busy ? "pointer" : "default",
                    background: !valid ? c.track : arming ? c.amber : side === "BUY" ? c.up : c.down,
                    color: !valid ? c.faint : "#fff",
                }}
            >
                {busy ? "전송 중…" : arming ? "한 번 더 눌러 확정" : side === "BUY" ? "매수 주문" : "매도 주문"}
            </button>
            {msg ? <div style={{ fontSize: 11.5, fontWeight: 600, color: msg.ok ? c.green : c.up, lineHeight: 1.45 }}>{msg.text}</div> : null}
            <div style={{ fontSize: 9.5, color: c.faint, lineHeight: 1.5 }}>
                실주문 — KIS 계좌 집행. 서버가 주문 권한·중복·일일 상한을 재검증합니다.
            </div>
        </div>
    )
}

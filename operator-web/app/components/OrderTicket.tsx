"use client"
// OrderTicket — 실주문 티켓 (PM 2026-08-05 "디자인 그게 최선인지" → 오퍼레이터급 재작성).
// 경로: POST /api/order (Supabase JWT → profiles.order_enabled 게이트 → Railway → KIS 실주문).
// 계약(1차 검증): {ticker, side:BUY/SELL, order_type:"00"지정가|"01"시장가, qty:int, price, market}.
//
// 오퍼레이터 차별점 — 증권사 폼에 없는 것을 붙인다:
//   · 중용 목표비중 갭 → "목표 8.5% · 현재 0% · 필요 34주" (moderation_portfolio, 우리 산식)
//   · 실계좌 예수금 기반 주문가능 수량 + 10/25/50/최대
//   · KRX 호가단위 ± 스테퍼(가격대별 자동)
//   · 체결 시 평단 시뮬 · 수수료·세금 추정
// 오발주 가드 = 2단 확정(4초). 블로터 기록 유지.
import { useCallback, useEffect, useMemo, useState } from "react"
import { useDark, palette, FONT, NUM, type Palette } from "@/lib/theme"
import { API_BASE, fetchOperator } from "@/lib/api"
import { authHeaders } from "@/lib/auth"
import { fetchMyProfile } from "@/lib/supabase"

type Props = {
    ticker: string
    name?: string
    presetPrice?: number | null
    livePrice?: number | null
}

/** KRX 호가단위 (2023-01-25 개편) — 가격대별. */
function tickSize(px: number): number {
    if (px < 2000) return 1
    if (px < 5000) return 5
    if (px < 20000) return 10
    if (px < 50000) return 50
    if (px < 200000) return 100
    if (px < 500000) return 500
    return 1000
}

/** 매수 수수료(추정) + 매도 시 거래세 — 실집행 금액 감각용(정산은 증권사 기준). */
const FEE_RATE = 0.00015   // 0.015% 가정
const TAX_RATE = 0.0015    // 매도 거래세 — 2025.1.1 인하율 0.15% (추정 표시용, 정산은 증권사 기준)

type ModTarget = { ticker?: string; weight?: number; target_weight?: number; name?: string }

export default function OrderTicket({ ticker, name, presetPrice, livePrice }: Props) {
    const dark = useDark()
    const c = palette(dark)
    const [side, setSide] = useState<"BUY" | "SELL">("BUY")
    const [otype, setOtype] = useState<"00" | "01">("00")
    const [qty, setQty] = useState("")
    const [amountInput, setAmountInput] = useState("")   // 토스 문법: 금액 입력 → 수량 역산
    const [price, setPrice] = useState("")
    const [arming, setArming] = useState(false)
    const [busy, setBusy] = useState(false)
    const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
    const [cash, setCash] = useState<number | null>(null)
    const [targets, setTargets] = useState<ModTarget[]>([])
    const [totalAsset, setTotalAsset] = useState<number | null>(null)
    // 배분 분모 — 이 전략에 배정한 시드(profiles.seed_krw). null 이면 실계좌 총액 전액.
    // 계좌 일부만 이 전략에 쓰는 경우를 위한 것. 회원마다 시드가 다르므로 같은 목표비중이
    // 각자 규모에 비례한 금액으로 환산된다(PM 2026-08-07 "각자 시드 규모 비례 배분").
    const [seedKrw, setSeedKrw] = useState<number | null>(null)
    // 연결된 계좌(profiles.broker_slug). null = 미연결 → 주문·잔고 모두 403.
    // 회원이 2명이라 "지금 이 주문이 누구 계좌로 나가는지"가 화면에 보여야 한다.
    const [broker, setBroker] = useState<string | null>(null)
    const [profileLoaded, setProfileLoaded] = useState(false)
    // 실계좌 보유 (KIS inquire-balance output1) — 검수 fix: 매도 수량·평단은 반드시
    // 실보유 기준. 이전엔 VAMS 가상 보유(pf.vams.holdings)로 계산 = 실주문 오발주 위험.
    const [acctHoldings, setAcctHoldings] = useState<Array<{ pdno?: string; hldg_qty?: string; pchs_avg_pric?: string }>>([])

    const isKR = /^\d{6}$/.test(ticker)

    // 예수금(실계좌) — 주문가능 수량 계산용. 1회만.
    useEffect(() => {
        let stop = false
        fetch(`${API_BASE}/api/order?market=kr`, { headers: authHeaders(), cache: "no-store" })
            .then((r) => r.json())
            .then((d) => {
                if (stop) return
                const o2 = Array.isArray(d?.output2) ? d.output2[0] : null
                const v = o2 ? parseFloat(String(o2.dnca_tot_amt ?? "").replace(/,/g, "")) : NaN
                if (isFinite(v)) setCash(v)
                const ta = o2 ? parseFloat(String(o2.tot_evlu_amt ?? "").replace(/,/g, "")) : NaN
                if (isFinite(ta)) setTotalAsset(ta)
                if (Array.isArray(d?.output1)) setAcctHoldings(d.output1)
            })
            .catch(() => {})
        return () => {
            stop = true
        }
    }, [])

    // 내 시드 배정액 — 배분 분모. 실패 시 null 로 두고 실계좌 총액으로 폴백한다.
    useEffect(() => {
        let stop = false
        fetchMyProfile().then((p) => {
            if (stop) return
            if (p?.seed_krw) setSeedKrw(p.seed_krw)
            setBroker(p?.broker_slug ?? null)
            setProfileLoaded(true)
        })
        return () => {
            stop = true
        }
    }, [])

    // 중용 목표비중 — 우리 산식 결과(오퍼레이터 차별점)
    useEffect(() => {
        let stop = false
        fetchOperator<Record<string, unknown>>("moderation_portfolio").then((r) => {
            if (stop || !r.ok || !r.data) return
            // 검수 fix: 실파일의 weights 는 배열이 아니라 dict {ticker: 비중(0~1)} —
            // (moderation_portfolio.py:289 실측). 원안의 Array.isArray 검사는 영구 false
            // → 간판 기능(목표비중 갭)이 조용히 죽어 있었다.
            const w = (r.data as { weights?: Record<string, number> }).weights
            if (w && typeof w === "object" && !Array.isArray(w)) {
                setTargets(Object.entries(w).map(([tk, wt]) => ({ ticker: tk, weight: Number(wt) })))
            }
        })
        return () => {
            stop = true
        }
    }, [])

    // 호가 클릭 → 가격 채움 / 종목 전환 → 리셋
    useEffect(() => {
        if (typeof presetPrice === "number" && presetPrice > 0) setPrice(String(Math.round(presetPrice)))
    }, [presetPrice])
    useEffect(() => {
        setQty("")
        setPrice("")
        setAmountInput("")
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
    const refPx = otype === "01" ? (typeof livePrice === "number" ? livePrice : 0) : pn
    const est = qn * refPx
    const fee = Math.floor(est * FEE_RATE)
    const tax = side === "SELL" ? Math.floor(est * TAX_RATE) : 0
    const netCost = side === "BUY" ? est + fee : est - fee - tax
    const valid = isKR && qn > 0 && (otype === "01" || pn > 0)

    // 실보유 (실계좌 output1 기준 — VAMS 가상 보유 아님)
    const acct = useMemo(() => {
        const h = acctHoldings.find((x) => String(x.pdno || "") === ticker)
        const q = h ? parseInt(String(h.hldg_qty ?? "").replace(/,/g, ""), 10) : 0
        const ap = h ? parseFloat(String(h.pchs_avg_pric ?? "").replace(/,/g, "")) : 0
        return { qty: isFinite(q) ? q : 0, avgPrice: isFinite(ap) ? ap : 0 }
    }, [acctHoldings, ticker])

    // 주문가능 수량 — 매수=예수금/가격, 매도=실보유수량
    const maxQty = useMemo(() => {
        if (side === "SELL") return acct.qty
        if (!refPx || !cash) return 0
        return Math.floor(cash / (refPx * (1 + FEE_RATE)))
    }, [side, acct, cash, refPx])

    // 중용 목표비중 갭 — 같은 목표비중을 **각자 시드 규모에 비례**해 금액으로 환산한다.
    // 분모 = seed_krw(배정액) 우선, 없으면 실계좌 총평가액. 두 사람이 같은 종목을 봐도
    // 각자 자기 규모의 필요 수량이 나온다. 잔고는 이미 계좌별로 라우팅되므로(X-Verity-Broker)
    // totalAsset 도 본인 것이다.
    const modGap = useMemo(() => {
        const t = targets.find((x) => String(x.ticker || "") === ticker)
        const tw = typeof t?.target_weight === "number" ? t.target_weight : typeof t?.weight === "number" ? t.weight : null
        const base = seedKrw ?? totalAsset
        if (tw == null || !base || base <= 0 || !refPx) return null
        const targetPct = tw <= 1 ? tw * 100 : tw            // 0.085 / 8.5 양쪽 수용
        const curVal = acct.qty * refPx
        const curPct = (curVal / base) * 100
        const needVal = (targetPct / 100) * base - curVal
        return { targetPct, curPct, needQty: Math.floor(needVal / refPx), base, seedScoped: seedKrw != null }
    }, [targets, ticker, totalAsset, seedKrw, refPx, acct])

    // 체결 시 평단 시뮬 (매수)
    const avgAfter = useMemo(() => {
        if (side !== "BUY" || !qn || !refPx) return null
        const hq = acct.qty
        const hp = acct.avgPrice
        if (!hq || !hp) return refPx
        return (hq * hp + qn * refPx) / (hq + qn)
    }, [side, qn, refPx, acct])

    const stepPrice = useCallback(
        (dir: 1 | -1) => {
            const base = pn || Math.round(livePrice || 0)
            if (!base) return
            const t = tickSize(base)
            const next = Math.max(t, Math.round((base + dir * t) / t) * t)
            setPrice(String(next))
        },
        [pn, livePrice]
    )

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
            setMsg({
                ok,
                text: ok
                    ? `주문 접수 — ${side === "BUY" ? "매수" : "매도"} ${qn}주${pn ? ` @ ${pn.toLocaleString()}` : " (시장가)"}`
                    : `거부 — ${String(detail).slice(0, 150)}`,
            })
            try {
                const raw = localStorage.getItem("af_blotter")
                const arr = raw ? JSON.parse(raw) : []
                const entry = {
                    ts: new Date().toISOString(), ticker, name: name || ticker, side,
                    order_type: otype, qty: qn, price: pn,
                    status: ok ? "접수" : "거부", msg: String(detail).slice(0, 200),
                }
                localStorage.setItem("af_blotter", JSON.stringify([entry, ...(Array.isArray(arr) ? arr : [])].slice(0, 50)))
                window.dispatchEvent(new Event("af-blotter"))
            } catch {}
        } catch (e) {
            setMsg({ ok: false, text: "요청 실패: " + String((e as Error).message || e).slice(0, 120) })
        } finally {
            setBusy(false)
        }
    }

    const seg = (active: boolean, col: string, colS: string) => ({
        flex: 1, border: "none", borderRadius: 9, padding: "8px 0",
        fontSize: 12.5, fontWeight: 800 as const, fontFamily: FONT, cursor: "pointer",
        background: active ? colS : c.hi, color: active ? col : c.faint,
    })
    const inputSt = {
        width: "100%", boxSizing: "border-box" as const,
        background: c.field, color: c.ink, border: "none", borderRadius: 10,
        padding: "9px 12px", fontSize: 13, fontFamily: FONT, outline: "none",
        fontVariantNumeric: "tabular-nums" as const,
    }
    const miniBtn = {
        border: "none", borderRadius: 7, padding: "4px 8px", fontSize: 10.5,
        fontWeight: 700 as const, cursor: "pointer", fontFamily: FONT,
        background: c.hi, color: c.sub,
    }

    if (!isKR) {
        return (
            <div style={{ fontFamily: FONT, fontSize: 11.5, color: c.sub, lineHeight: 1.55, background: c.hi, borderRadius: 12, padding: "12px 14px" }}>
                주문 티켓은 KR 종목만 지원합니다 (US 백엔드 준비 완료, UI 개통은 대기).
            </div>
        )
    }

    return (
        <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 8 }}>
            {/* 계좌 연결 상태 — 미연결이면 주문이 403 으로 떨어진다. 눌러보고 알게 하지 않는다. */}
            {profileLoaded && !broker ? (
                <div style={{ background: c.amberS, borderRadius: 9, padding: "7px 10px", fontSize: 11, color: c.amber, fontWeight: 700 }}>
                    증권계좌 미연결 — 주문·잔고 조회 불가. 서버에서 계좌 연결 후 이용 가능합니다.
                </div>
            ) : null}
            {/* 중용 목표비중 갭 — 우리 시스템만 아는 정보 */}
            {modGap ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8, background: c.vtS, borderRadius: 9, padding: "7px 10px", flexWrap: "wrap" }}>
                    <span style={{ fontSize: 10, fontWeight: 800, color: c.vt }}>중용 목표</span>
                    <span style={{ fontSize: 11, color: c.sub, ...NUM }}>
                        목표 <b style={{ color: c.ink }}>{modGap.targetPct.toFixed(1)}%</b> · 현재 <b style={{ color: c.ink }}>{modGap.curPct.toFixed(1)}%</b>
                    </span>
                    {/* 분모를 밝힌다 — 같은 비중이라도 사람마다 금액이 다르므로, 무엇에 대한
                        %인지 모르면 수량을 검산할 수 없다. */}
                    <span style={{ fontSize: 10, color: c.sub, ...NUM }}>
                        / {modGap.seedScoped ? "배정 시드" : "계좌 총액"} {(modGap.base / 1e4).toLocaleString(undefined, { maximumFractionDigits: 0 })}만
                        {broker ? ` · ${broker}` : ""}
                    </span>
                    {modGap.needQty !== 0 ? (
                        <button
                            onClick={() => { setSide(modGap.needQty > 0 ? "BUY" : "SELL"); setQty(String(Math.abs(modGap.needQty))) }}
                            style={{ ...miniBtn, marginLeft: "auto", background: c.vt, color: "#fff", fontWeight: 800 }}
                        >
                            {modGap.needQty > 0 ? "매수" : "매도"} {Math.abs(modGap.needQty).toLocaleString()}주 채우기
                        </button>
                    ) : (
                        <span style={{ marginLeft: "auto", fontSize: 10.5, color: c.green, fontWeight: 700 }}>목표 도달</span>
                    )}
                </div>
            ) : null}

            <div style={{ display: "flex", gap: 6 }}>
                <button onClick={() => setSide("BUY")} style={seg(side === "BUY", c.up, c.upS)}>매수</button>
                <button onClick={() => setSide("SELL")} style={seg(side === "SELL", c.down, c.downS)}>매도</button>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
                <button onClick={() => setOtype("00")} style={seg(otype === "00", c.vt, c.vtS)}>지정가</button>
                <button onClick={() => setOtype("01")} style={seg(otype === "01", c.vt, c.vtS)}>시장가</button>
            </div>

            {/* 가격 — 호가단위 스테퍼 */}
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                    value={otype === "01" ? "" : price}
                    onChange={(e) => setPrice(e.target.value.replace(/[^\d]/g, ""))}
                    placeholder={otype === "01" ? "시장가" : "가격 (호가 클릭)"}
                    inputMode="numeric"
                    disabled={otype === "01"}
                    style={{ ...inputSt, opacity: otype === "01" ? 0.5 : 1 }}
                />
                {otype === "00" ? (
                    <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                        <button onClick={() => stepPrice(-1)} style={{ ...miniBtn, padding: "8px 11px", fontSize: 13 }}>−</button>
                        <button onClick={() => stepPrice(1)} style={{ ...miniBtn, padding: "8px 11px", fontSize: 13 }}>+</button>
                    </div>
                ) : null}
            </div>

            {/* 수량 — 입력 + ± 스테퍼 (토스 동등) */}
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                    value={qty}
                    onChange={(e) => { setQty(e.target.value.replace(/[^\d]/g, "")); setAmountInput("") }}
                    placeholder="수량"
                    inputMode="numeric"
                    style={inputSt}
                />
                <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                    <button onClick={() => { setQty(String(Math.max(0, qn - 1))); setAmountInput("") }} style={{ ...miniBtn, padding: "8px 11px", fontSize: 13 }}>−</button>
                    <button onClick={() => { setQty(String(qn + 1)); setAmountInput("") }} style={{ ...miniBtn, padding: "8px 11px", fontSize: 13 }}>+</button>
                </div>
            </div>

            {/* 비율 버튼 — 항상 노출(토스 동등). 가능수량 미확보 시 안내로 대체하지 않고 비활성 표시. */}
            <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
                {[10, 25, 50, 100].map((p) => (
                    <button
                        key={p}
                        disabled={maxQty <= 0}
                        onClick={() => { setQty(String(Math.max(1, Math.floor((maxQty * p) / 100)))); setAmountInput("") }}
                        style={{ ...miniBtn, flex: 1, opacity: maxQty > 0 ? 1 : 0.45, cursor: maxQty > 0 ? "pointer" : "default" }}
                    >
                        {p === 100 ? "최대" : `${p}%`}
                    </button>
                ))}
                <span style={{ fontSize: 10, color: c.faint, whiteSpace: "nowrap", ...NUM }}>
                    {maxQty > 0
                        ? `가능 ${maxQty.toLocaleString()}주`
                        : side === "SELL" ? "보유 0주" : refPx ? "예수금 확인 중" : "가격 입력"}
                </span>
            </div>

            {/* 총 주문 금액 — 입력하면 수량 역산 (토스 핵심 UX) */}
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                    value={amountInput}
                    onChange={(e) => {
                        const raw = e.target.value.replace(/[^\d]/g, "")
                        setAmountInput(raw)
                        const amt = parseInt(raw, 10) || 0
                        if (amt > 0 && refPx > 0) setQty(String(Math.max(0, Math.floor(amt / refPx))))
                    }}
                    placeholder="총 주문 금액 (입력 시 수량 자동)"
                    inputMode="numeric"
                    style={inputSt}
                />
                <span style={{ fontSize: 11, color: c.faint, flexShrink: 0 }}>원</span>
            </div>

            {/* 금액 요약 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 3, background: c.hi, borderRadius: 9, padding: "8px 10px" }}>
                <Row c={c} k={side === "BUY" ? "주문 금액" : "매도 금액"} v={est > 0 ? Math.round(est).toLocaleString() + "원" : "—"} bold />
                <Row c={c} k={side === "BUY" ? `수수료(약 ${(FEE_RATE * 100).toFixed(3)}%)` : "수수료·세금"} v={est > 0 ? "-" + (fee + tax).toLocaleString() + "원" : "—"} />
                <Row c={c} k={side === "BUY" ? "총 필요" : "실수령(추정)"} v={est > 0 ? Math.round(netCost).toLocaleString() + "원" : "—"} bold />
                <Row c={c} k="예수금" v={cash !== null ? Math.round(cash).toLocaleString() + "원" : "조회 실패"} />
                {side === "BUY" && cash !== null && est > 0 ? (
                    <Row c={c} k="주문 후 잔여" v={Math.round(cash - netCost).toLocaleString() + "원"} />
                ) : null}
                {avgAfter && acct.qty > 0 && acct.avgPrice > 0 ? (
                    <Row c={c} k="체결 후 평단(실계좌)" v={`${Math.round(acct.avgPrice).toLocaleString()} → ${Math.round(avgAfter).toLocaleString()}`} />
                ) : null}
            </div>

            <button
                onClick={submit}
                disabled={!valid || busy}
                style={{
                    border: "none", borderRadius: 11, padding: "12px 0", fontSize: 13.5, fontWeight: 800,
                    fontFamily: FONT, cursor: valid && !busy ? "pointer" : "default",
                    background: !valid ? c.track : arming ? c.amber : side === "BUY" ? c.up : c.down,
                    color: !valid ? c.faint : "#fff",
                }}
            >
                {busy ? "전송 중…" : arming ? "한 번 더 눌러 확정" : side === "BUY" ? "매수 주문" : "매도 주문"}
            </button>
            {msg ? <div style={{ fontSize: 11.5, fontWeight: 600, color: msg.ok ? c.green : c.up, lineHeight: 1.45 }}>{msg.text}</div> : null}
            <div style={{ fontSize: 9.5, color: c.faint, lineHeight: 1.5 }}>
                실주문 — KIS 계좌 집행. 서버가 주문 권한·건당 상한·일일 횟수를 재검증합니다.
            </div>
        </div>
    )
}

function Row({ c, k, v, bold }: { c: Palette; k: string; v: string; bold?: boolean }) {
    return (
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: c.sub }}>
            <span>{k}</span>
            <span style={{ fontWeight: bold ? 800 : 600, color: bold ? c.ink : c.sub, ...NUM }}>{v}</span>
        </div>
    )
}

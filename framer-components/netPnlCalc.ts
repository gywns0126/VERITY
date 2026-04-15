/**
 * KR/US 실순수익(Net P&L) 계산기.
 *
 * 국내(KR): 증권거래세 + 위탁수수료
 * 미국(US): 위탁수수료 + SEC Fee + 환전수수료(단순화)
 *
 * 정책값은 한국투자증권 기준 기본값. 환경에 따라 오버라이드 가능.
 */

export interface FeePolicy {
    /** 위탁수수료율 (매수·매도 동일, 0.0035 = 0.35%) */
    brokerFeePct: number
    /** [KR] 증권거래세율 (매도 시, 0.0018 = 0.18%) - 2026 기준 코스피 */
    krTransactionTaxPct: number
    /** [KR] 농특세율 (매도 시, 0.0015 = 0.15%) - 코스피만 */
    krAgriTaxPct: number
    /** [US] SEC Fee 기본 단가 (매도금액 × rate, 약 $0.0000278/달러 → 0.00278%) */
    usSecFeePct: number
    /** [US] 환전 수수료율 (편도, 0.002 = 0.2%) */
    usFxSpreadPct: number
    /** [US] 원/달러 환율 (순수익을 원화로 표시할 때 사용) */
    usdKrw: number
}

export const DEFAULT_KR_POLICY: FeePolicy = {
    brokerFeePct: 0.00015,
    krTransactionTaxPct: 0.0018,
    krAgriTaxPct: 0.0015,
    usSecFeePct: 0,
    usFxSpreadPct: 0,
    usdKrw: 1,
}

export const DEFAULT_US_POLICY: FeePolicy = {
    brokerFeePct: 0.00025,
    krTransactionTaxPct: 0,
    krAgriTaxPct: 0,
    usSecFeePct: 0.0000278,
    usFxSpreadPct: 0.002,
    usdKrw: 1370,
}

export interface NetPnlResult {
    grossPnL: number
    buyFee: number
    sellFee: number
    sellTax: number
    fxCost: number
    totalCost: number
    netPnL: number
    netReturnPct: number
}

export type Side = "buy" | "sell"

/**
 * 실순수익 계산.
 * 매수/매도 쌍으로 시뮬레이션하거나, 단일 매수/매도 비용만 산출.
 *
 * - roundTrip: true면 entry→exit 왕복, false면 side 한 방향만
 */
export function calcNetPnl(params: {
    market: "kr" | "us"
    qty: number
    entryPrice: number
    exitPrice: number
    policy?: Partial<FeePolicy>
}): NetPnlResult {
    const { market, qty, entryPrice, exitPrice, policy: overrides } = params
    const base = market === "us" ? { ...DEFAULT_US_POLICY } : { ...DEFAULT_KR_POLICY }
    const p: FeePolicy = { ...base, ...overrides }

    const buyAmount = entryPrice * qty
    const sellAmount = exitPrice * qty
    const grossPnL = sellAmount - buyAmount

    const buyFee = buyAmount * p.brokerFeePct
    const sellFee = sellAmount * p.brokerFeePct

    let sellTax = 0
    if (market === "kr") {
        sellTax = sellAmount * (p.krTransactionTaxPct + p.krAgriTaxPct)
    } else {
        sellTax = sellAmount * p.usSecFeePct
    }

    let fxCost = 0
    if (market === "us") {
        fxCost = (buyAmount + sellAmount) * p.usFxSpreadPct
    }

    const totalCost = buyFee + sellFee + sellTax + fxCost
    const netPnL = grossPnL - totalCost
    const netReturnPct = buyAmount > 0 ? (netPnL / buyAmount) * 100 : 0

    return {
        grossPnL: Math.round(grossPnL * 100) / 100,
        buyFee: Math.round(buyFee * 100) / 100,
        sellFee: Math.round(sellFee * 100) / 100,
        sellTax: Math.round(sellTax * 100) / 100,
        fxCost: Math.round(fxCost * 100) / 100,
        totalCost: Math.round(totalCost * 100) / 100,
        netPnL: Math.round(netPnL * 100) / 100,
        netReturnPct: Math.round(netReturnPct * 100) / 100,
    }
}

/**
 * 단일 주문(매수 또는 매도)의 비용만 간단히 산출.
 */
export function calcOrderCost(params: {
    market: "kr" | "us"
    side: Side
    qty: number
    price: number
    policy?: Partial<FeePolicy>
}): { fee: number; tax: number; fxCost: number; totalCost: number; netAmount: number } {
    const { market, side, qty, price, policy: overrides } = params
    const base = market === "us" ? { ...DEFAULT_US_POLICY } : { ...DEFAULT_KR_POLICY }
    const p: FeePolicy = { ...base, ...overrides }

    const amount = price * qty
    const fee = amount * p.brokerFeePct

    let tax = 0
    if (side === "sell") {
        tax = market === "kr"
            ? amount * (p.krTransactionTaxPct + p.krAgriTaxPct)
            : amount * p.usSecFeePct
    }

    let fxCost = 0
    if (market === "us") {
        fxCost = amount * p.usFxSpreadPct
    }

    const totalCost = fee + tax + fxCost
    const netAmount = side === "buy" ? amount + totalCost : amount - totalCost

    return {
        fee: Math.round(fee * 100) / 100,
        tax: Math.round(tax * 100) / 100,
        fxCost: Math.round(fxCost * 100) / 100,
        totalCost: Math.round(totalCost * 100) / 100,
        netAmount: Math.round(netAmount * 100) / 100,
    }
}

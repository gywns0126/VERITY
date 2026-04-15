/**
 * 순수익 계산기 단위 테스트 (jest 또는 vitest).
 *
 * 실행: npx vitest run __tests__/netPnlCalc.test.ts
 */
import { calcNetPnl, calcOrderCost } from "../netPnlCalc"

describe("calcNetPnl — KR", () => {
    it("매수 70,000 → 매도 75,000 × 10주 (코스피)", () => {
        const r = calcNetPnl({ market: "kr", qty: 10, entryPrice: 70000, exitPrice: 75000 })
        expect(r.grossPnL).toBe(50000)
        expect(r.buyFee).toBeGreaterThan(0)
        expect(r.sellFee).toBeGreaterThan(0)
        expect(r.sellTax).toBeGreaterThan(0)
        expect(r.fxCost).toBe(0)
        expect(r.netPnL).toBeLessThan(r.grossPnL)
        expect(r.netReturnPct).toBeGreaterThan(0)
    })

    it("손실 케이스 — 매수 80,000 → 매도 70,000 × 5주", () => {
        const r = calcNetPnl({ market: "kr", qty: 5, entryPrice: 80000, exitPrice: 70000 })
        expect(r.grossPnL).toBe(-50000)
        expect(r.netPnL).toBeLessThan(r.grossPnL)
    })

    it("수량 0이면 모든 값 0", () => {
        const r = calcNetPnl({ market: "kr", qty: 0, entryPrice: 50000, exitPrice: 55000 })
        expect(r.grossPnL).toBe(0)
        expect(r.totalCost).toBe(0)
        expect(r.netPnL).toBe(0)
    })
})

describe("calcNetPnl — US", () => {
    it("AAPL 매수 $180 → 매도 $200 × 50주", () => {
        const r = calcNetPnl({ market: "us", qty: 50, entryPrice: 180, exitPrice: 200 })
        expect(r.grossPnL).toBe(1000)
        expect(r.fxCost).toBeGreaterThan(0)
        expect(r.netPnL).toBeLessThan(r.grossPnL)
    })
})

describe("calcOrderCost", () => {
    it("KR 매수 — 세금 0, 수수료만", () => {
        const c = calcOrderCost({ market: "kr", side: "buy", qty: 100, price: 50000 })
        expect(c.fee).toBeGreaterThan(0)
        expect(c.tax).toBe(0)
        expect(c.fxCost).toBe(0)
    })

    it("KR 매도 — 세금 포함", () => {
        const c = calcOrderCost({ market: "kr", side: "sell", qty: 100, price: 50000 })
        expect(c.tax).toBeGreaterThan(0)
        expect(c.totalCost).toBeGreaterThan(c.fee)
    })

    it("US 매수 — 환전비용 포함", () => {
        const c = calcOrderCost({ market: "us", side: "buy", qty: 10, price: 200 })
        expect(c.fxCost).toBeGreaterThan(0)
    })

    it("정책 오버라이드", () => {
        const c1 = calcOrderCost({ market: "kr", side: "sell", qty: 100, price: 50000 })
        const c2 = calcOrderCost({ market: "kr", side: "sell", qty: 100, price: 50000, policy: { brokerFeePct: 0 } })
        expect(c2.fee).toBe(0)
        expect(c2.totalCost).toBeLessThan(c1.totalCost)
    })
})

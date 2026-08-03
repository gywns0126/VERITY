// 공유 타입 — portfolio_full(/api/admin authed) 1차 자료 검증 shape (data/portfolio.json 실측 2026-08-03).
// page.tsx 가 한 번 fetch 해 HUD/보유/추천/피드에 내려줌 (중복 fetch 금지).

export type Holding = {
    ticker: string
    name?: string
    currency?: string
    buy_price?: number
    current_price?: number
    quantity?: number
    total_cost?: number
    return_pct?: number
}

export type Vams = {
    total_asset?: number
    cash?: number
    holdings?: Holding[]
    total_return_pct?: number
}

export type Brain = { brain_score?: number; grade_label?: string; grade?: string }

export type Rec = {
    name?: string
    ticker?: string
    currency?: string
    recommendation?: string
    verity_brain?: Brain
    brain_score?: number
    per?: number
    pbr?: number
    roe?: number
    rec_price?: number
    ai_verdict?: string
    drop_from_high_pct?: number
    flow?: { foreign_net?: number }
    lynch_kr?: { label?: string }
    dart_disclosure_events?: { severity?: number }
}

export type PortfolioFull = {
    updated_at?: string
    vams?: Vams
    recommendations?: Rec[]
}

export type AlertItem = {
    ticker: string
    name: string
    type: string
    headline: string
    date?: string
    krw?: number
    source_url?: string
}

/** verity-ticker 링크그룹 발신 — 행 클릭 = 전 패널 동기 전환 (Bloomberg Launchpad 그룹 문법). */
export function selectTicker(ticker: string, name?: string): void {
    try {
        localStorage.setItem("verity_last_ticker", ticker)
    } catch {}
    try {
        window.dispatchEvent(new CustomEvent("verity-ticker", { detail: { ticker, item: { ticker, name } } }))
    } catch {}
}

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

export type Headline = { title?: string; link?: string }

export type GlobalEvent = {
    name?: string
    severity?: string
    country?: string
    impact?: string
    impact_area?: string[]
    action?: string
}

export type Briefing = { headline?: string; tone?: string }

/** 🚨 recommended/avoid_sectors = 객체 배열 (실측 2026-08-03). 문자열로 렌더하면
 *  "Objects are not valid as a React child" 크래시 — 거시 패널 오류 실사고 근인. */
export type RotSector = { name?: string; change_pct?: number; reason?: string; theme?: string }

export type SectorRotation = {
    cycle?: string
    cycle_label?: string
    cycle_desc?: string
    recommended_sectors?: RotSector[]
    avoid_sectors?: RotSector[]
}

export type SectorTopStock = { name?: string; price?: number; change_pct?: number }

export type SectorRow = {
    name?: string
    market?: string
    change_pct?: number
    top_stocks?: SectorTopStock[]
}

export type MacroNode = {
    value?: number
    change?: number
    change_pct?: number
    week_high?: number
    week_low?: number
    sparkline?: number[]
}

export type Analog = {
    name?: string
    date?: string
    distance?: number
    cape?: number
    vix?: number
    unemployment?: number
}

export type HorizonBand = { median?: number; p25?: number; p75?: number; p5?: number; p95?: number }

export type MarketHorizon = {
    verdict?: string
    recession_prob_12m?: number
    cape_percentile?: number
    cape_value?: number
    cycle_stage_label_ko?: string
    horizons?: Record<string, HorizonBand>
    analogs?: Analog[]
}

export type DailyReport = {
    market_analysis?: string
    strategy?: string
    risk_watch?: string
    tomorrow_outlook?: string
}

export type PortfolioFull = {
    updated_at?: string
    vams?: Vams
    recommendations?: Rec[]
    // 거시(숲) — portfolio.json 실측 shape (2026-08-03). 별도 fetch 불요.
    headlines?: Headline[]
    bloomberg_google_headlines?: Headline[]
    global_events?: GlobalEvent[]
    briefing?: Briefing
    sector_rotation?: SectorRotation
    market_horizon?: MarketHorizon
    daily_report?: DailyReport
    sectors?: SectorRow[]
    macro?: Record<string, MacroNode>
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

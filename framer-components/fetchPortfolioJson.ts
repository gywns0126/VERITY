/**
 * GitHub raw·브라우저 HTTP 캐시를 우회해 최신 portfolio.json을 가져옵니다.
 * Framer에서 이 파일을 동일 코드 패키지에 두고 `import { fetchPortfolioJson } from "./fetchPortfolioJson"` 로 사용하세요.
 * (StockDashboard·CompareCard·MarketBar·NicheIntelPanel·AlertDashboard 등은 Framer 단일 파일용으로 동일 로직을 인라인해 둡니다. 수정 시 맞춰 주세요.)
 */
export function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

export const PORTFOLIO_FETCH_INIT: RequestInit = {
    cache: "no-store",
    mode: "cors",
    credentials: "omit",
}

export function fetchPortfolioJson(url: string): Promise<any> {
    return fetch(bustPortfolioUrl(url), PORTFOLIO_FETCH_INIT)
        .then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.text()
        })
        .then((txt) =>
            JSON.parse(
                txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
            ),
        )
}

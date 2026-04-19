/**
 * GitHub raw·브라우저 HTTP 캐시를 우회해 최신 portfolio.json을 가져옵니다.
 * primary URL 실패 시 .bak 백업 파일로 자동 폴백하며, 15초 timeout 으로 무한 대기를 방지합니다.
 *
 * Framer에서 이 파일을 동일 코드 패키지에 두고 `import { fetchPortfolioJson } from "./fetchPortfolioJson"` 로 사용하세요.
 * (NewsHeadline·StockDashboard·VerityReport·CompareCard·MarketBar·NicheIntelPanel·AlertDashboard 등은 Framer 단일 파일용으로 동일 로직을 인라인해 둡니다. 수정 시 맞춰 주세요.)
 */
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000

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

function toBackupUrl(url: string): string {
    return url.replace(/portfolio\.json$/, "portfolio.json.bak")
}

function parsePortfolioText(txt: string): any {
    return JSON.parse(
        txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
    )
}

function withTimeout<T>(p: Promise<T>, ms: number, ac: AbortController): Promise<T> {
    const timer = setTimeout(() => ac.abort(), ms)
    return p.finally(() => clearTimeout(timer))
}

function fetchRaw(url: string, externalSignal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (externalSignal) {
        if (externalSignal.aborted) ac.abort()
        else externalSignal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    const init: RequestInit = { ...PORTFOLIO_FETCH_INIT, signal: ac.signal }
    return withTimeout(
        fetch(bustPortfolioUrl(url), init).then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.text()
        }).then(parsePortfolioText),
        PORTFOLIO_FETCH_TIMEOUT_MS,
        ac,
    )
}

export function fetchPortfolioJson(url: string, externalSignal?: AbortSignal): Promise<any> {
    return fetchRaw(url, externalSignal).catch(() => {
        const backup = toBackupUrl(url)
        if (backup === url) throw new Error("no backup available")
        return fetchRaw(backup, externalSignal)
    })
}

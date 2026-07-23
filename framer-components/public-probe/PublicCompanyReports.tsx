import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 기업 리포트·자료 — VERITY 공개 터미널 (AlphaNest). 그 회사가 발행하는 공식 리포트/자료를 한곳에 모아 외부 소스로 딥링크.
 *
 * 🚨 RULE 7 / held-2027 / feedback_scope: 전부 **외부 소스 링크 모음**(공시·정기보고서·증권사 리포트·IR). VERITY 자체 점수·추천·작문 0.
 *   링크 = 공식/공개 출처(DART·네이버 금융·SEC EDGAR). 클릭 시 원문으로 이동(새 탭).
 * 종목 = prop ticker → 없으면 URL ?q → verity_last_ticker. 6자리=KR / 그 외=US 소스 분기.
 *
 * 🚨 2026-07-24 테마 = Framer 네이티브 CSS 변수(--an-*) 구동. JS 다크 감지 전면 제거.
 *   헤드 Custom Code 의 <style id="an-theme-palette"> 가 body[data-framer-theme] 기준으로 색을 몰아줌 →
 *   하이드레이션/JS 실행과 무관하게 CSS 라 항상 정합(정적 export stuck-라이트 근본 해결). 되돌리지 말 것.
 */

interface Props {
    ticker: string
    krUniverseUrl: string
    usUniverseUrl: string
    dark: boolean
}
const DEF_KR =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
const DEF_US =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json"

// 색 = 헤드 #an-theme-palette 의 CSS 변수. body[data-framer-theme] 가 light/dark 를 결정(JS 불필요).
const C = {
    bg: "var(--an-bg)",
    card: "var(--an-card)",
    ink: "var(--an-ink)",
    sub: "var(--an-sub)",
    faint: "var(--an-faint)",
    line: "var(--an-line)",
    vt: "var(--an-vt)",
    vtS: "var(--an-vtS)",
    chip: "var(--an-chip)",
}
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

function readTickerFromUrl(): string {
    if (typeof window === "undefined") return ""
    try {
        const q = (
            new URLSearchParams(window.location.search).get("q") || ""
        ).trim()
        if (q) return q.toUpperCase()
        const ls = (
            window.localStorage.getItem("verity_last_ticker") || ""
        ).trim()
        return ls.toUpperCase()
    } catch {
        return ""
    }
}

// 외부 리포트·자료 링크 — KR(네이버 금융·DART) / US(SEC EDGAR·Yahoo). 종목코드/티커로 딥링크.
function linksFor(tk: string): { label: string; src: string; url: string }[] {
    const t = String(tk || "").trim()
    if (!t) return []
    const isKR = /^\d{6}$/.test(t)
    if (isKR) {
        const c = encodeURIComponent(t)
        return [
            {
                label: "공시·정기보고서 (사업·분기보고서)",
                src: "전자공시 DART · 네이버",
                url: `https://finance.naver.com/item/news_notice.naver?code=${c}`,
            },
            {
                label: "증권사 리포트",
                src: "네이버 금융 리서치",
                url: `https://finance.naver.com/research/company_list.naver?itemCode=${c}`,
            },
            {
                label: "종목 종합 (시세·재무·IR·뉴스)",
                src: "네이버 금융",
                url: `https://finance.naver.com/item/main.naver?code=${c}`,
            },
        ]
    }
    const c = encodeURIComponent(t)
    return [
        {
            label: "공시·연차보고서 (10-K·10-Q·8-K)",
            src: "SEC EDGAR",
            url: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker=${c}&type=&dateb=&owner=include&count=40`,
        },
        {
            label: "종목·재무·애널리스트 분석",
            src: "Yahoo Finance",
            url: `https://finance.yahoo.com/quote/${c}`,
        },
    ]
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicCompanyReports(props: Props) {
    // ETF/ETN 선택 시 자기 숨김 — StockReport 가 body[data-verity-asset-kind] 신호 발행 (2026-07-10)
    const [assetKind, setAssetKind] = useState<string>("stock")
    useEffect(() => {
        if (typeof document === "undefined" || !document.body) return
        const read = () =>
            setAssetKind(document.body.dataset.verityAssetKind || "stock")
        read()
        if (typeof MutationObserver === "undefined") return
        const obs = new MutationObserver(read)
        obs.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-verity-asset-kind"],
        })
        return () => obs.disconnect()
    }, [])
    const { ticker, krUniverseUrl, usUniverseUrl } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [tk, setTk] = useState<string>(
        () =>
            String(ticker || "")
                .trim()
                .toUpperCase() || (onCanvas ? "005930" : "")
    )
    const [nameMap, setNameMap] = useState<Record<string, string>>({})

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries) setW(e.contentRect.width)
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    /* 종목 = prop 우선, 없으면 URL ?q. in-page replaceState 추종 위해 1s 폴링. */
    useEffect(() => {
        if (onCanvas) return
        const propTk = String(ticker || "")
            .trim()
            .toUpperCase()
        if (propTk) {
            setTk(propTk)
            return
        }
        const sync = () => {
            const u = readTickerFromUrl()
            if (u) setTk((cur) => (cur === u ? cur : u))
        }
        sync()
        window.addEventListener("popstate", sync)
        const iv = setInterval(sync, 1000)
        return () => {
            window.removeEventListener("popstate", sync)
            clearInterval(iv)
        }
    }, [ticker, onCanvas])

    /* 이름 매핑(있으면) — KR/US 유니버스에서 ticker→name. 링크는 이름 없어도 동작. */
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const urls = [krUniverseUrl, usUniverseUrl].filter(Boolean)
        Promise.all(
            urls.map((u) =>
                fetch(u, { cache: "no-store" })
                    .then((r) => (r.ok ? r.json() : null))
                    .catch(() => null)
            )
        ).then((docs) => {
            if (!alive) return
            const m: Record<string, string> = {}
            for (const d of docs) {
                const a = d && (Array.isArray(d) ? d : d.stocks)
                if (Array.isArray(a))
                    for (const x of a) {
                        if (x && x.ticker && x.name)
                            m[String(x.ticker).toUpperCase()] = String(x.name)
                    }
            }
            if (Object.keys(m).length) setNameMap(m)
        })
        return () => {
            alive = false
        }
    }, [krUniverseUrl, usUniverseUrl, onCanvas])

    const links = useMemo(() => linksFor(tk), [tk])
    const name = nameMap[String(tk).toUpperCase()] || ""
    const narrow = w > 0 && w < 420

    const wrap: CSSProperties = {
        width: "100%",
        minHeight: "100%",
        background: C.bg,
        fontFamily: FONT,
        padding: narrow ? 14 : 18,
        boxSizing: "border-box",
        color: C.ink,
    }
    const card: CSSProperties = {
        background: C.card,
        borderRadius: 16,
        padding: narrow ? 14 : 18,
        boxSizing: "border-box",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
    }

    if (!tk) {
        return (
            <div ref={rootRef} style={wrap}>
                <div
                    style={{
                        ...card,
                        fontSize: 12.5,
                        color: C.faint,
                        fontWeight: 600,
                    }}
                >
                    종목을 선택하면 그 회사의 공시·리포트 링크가 떠요.
                </div>
            </div>
        )
    }

    if (assetKind === "etf") return null // ETF/ETN = 기업 전용 섹션 숨김

    return (
        <div ref={rootRef} style={wrap}>
            <div style={card}>
                <div
                    style={{
                        display: "flex",
                        alignItems: "baseline",
                        gap: 8,
                        marginBottom: 4,
                    }}
                >
                    <span
                        style={{
                            fontSize: 13.5,
                            fontWeight: 800,
                            color: C.ink,
                            letterSpacing: "-0.2px",
                        }}
                    >
                        기업 리포트·자료
                    </span>
                    <span
                        style={{
                            fontSize: 11.5,
                            fontWeight: 600,
                            color: C.faint,
                        }}
                    >
                        {name ? `${name} · ${tk}` : tk}
                    </span>
                </div>
                <div
                    style={{
                        fontSize: 11.5,
                        color: C.sub,
                        fontWeight: 500,
                        marginBottom: 10,
                        lineHeight: 1.5,
                    }}
                >
                    회사가 발행한 공식 공시·정기보고서와 외부 리서치를 원문으로
                    바로 봐요.
                </div>

                <div style={{ display: "flex", flexDirection: "column" }}>
                    {links.map((l, i) => (
                        <a
                            key={l.url + i}
                            href={l.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 10,
                                padding: "12px 4px",
                                borderTop:
                                    i === 0 ? "none" : `1px solid ${C.line}`,
                                textDecoration: "none",
                                cursor: "pointer",
                            }}
                        >
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div
                                    style={{
                                        fontSize: 13.5,
                                        fontWeight: 700,
                                        color: C.ink,
                                        whiteSpace: "nowrap",
                                        overflow: "hidden",
                                        textOverflow: "ellipsis",
                                    }}
                                >
                                    {l.label}
                                </div>
                                <div
                                    style={{
                                        fontSize: 11,
                                        color: C.faint,
                                        fontWeight: 500,
                                        marginTop: 1,
                                    }}
                                >
                                    {l.src}
                                </div>
                            </div>
                            <span
                                style={{
                                    flexShrink: 0,
                                    fontSize: 11.5,
                                    fontWeight: 700,
                                    color: C.vt,
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: 3,
                                }}
                            >
                                원문
                                <svg
                                    width="13"
                                    height="13"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2.4"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                >
                                    <path d="M7 17L17 7M17 7H8M17 7v9" />
                                </svg>
                            </span>
                        </a>
                    ))}
                </div>

                <div
                    style={{
                        fontSize: 10.5,
                        color: C.faint,
                        fontWeight: 500,
                        marginTop: 12,
                        lineHeight: 1.55,
                    }}
                >
                    공식·공개 출처(DART·네이버 금융·SEC EDGAR) 링크 모음. 원문은
                    각 기관 발행.
                </div>
            </div>
        </div>
    )
}

addPropertyControls(PublicCompanyReports, {
    ticker: {
        type: ControlType.String,
        title: "Ticker(빈값=URL ?q)",
        defaultValue: "",
    },
    krUniverseUrl: {
        type: ControlType.String,
        title: "KR Universe",
        defaultValue: DEF_KR,
    },
    usUniverseUrl: {
        type: ControlType.String,
        title: "US Universe",
        defaultValue: DEF_US,
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark(미사용)",
        defaultValue: false,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
})

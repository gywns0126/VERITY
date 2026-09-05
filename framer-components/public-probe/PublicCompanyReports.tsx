import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 기업 리포트·자료 — VERITY 공개 터미널 (AlphaNest). 그 회사가 발행하는 공식 리포트/자료를 한곳에 모아 외부 소스로 딥링크.
 *
 * 🚨 RULE 7 / held-2027 / feedback_scope: 전부 **외부 소스 링크 모음**(공시·정기보고서·증권사 리포트·IR). VERITY 자체 점수·추천·작문 0.
 *   링크 = 공식/공개 출처(DART·네이버 금융·SEC EDGAR). 클릭 시 원문으로 이동(새 탭).
 * 종목 = prop ticker → 없으면 URL ?q → verity_last_ticker. 숫자로 시작하는 6자리 영숫자=KRX / 그 외=US 소스 분기.
 *   리포트 페이지 in-page 전환(replaceState) 추종 위해 ?q 폴링(1s)으로 종목 동기화.
 * 이름 = stock_report_public(KR)/us_stock_report_public(US)에서 ticker→name 매핑(있으면). 없어도 링크는 ticker로 동작.
 * 🚨 2026-08-21 테마 = 자체 내장 CSS 변수(--an-cr-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
 *   <style>{AN_PALETTE} 를 두 반환 분기 모두에 넣는다(조기 반환 누락 = 그 화면만 색 죽음).
 *   SVG 는 stroke 프레젠테이션 attribute 대신 style 로 준다 — 거기서는 CSS 변수가 해석되지 않는다.
 *   되돌리지 말 것.
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

const LIGHT = {
    bg: "#f2f4f6",
    card: "#ffffff",
    ink: "#191f28",
    sub: "#4e5968",
    faint: "#8b95a1",
    line: "#f0f1f3",
    vt: "#6c5ce7",
    vtS: "#f0edff",
    chip: "#f2f4f6",
}
const DARK = {
    bg: "#0f1318",
    card: "#171c23",
    ink: "#e3e7ec",
    sub: "#9aa4b1",
    faint: "#828d9b",
    line: "#222730",
    vt: "#a99bff",
    vtS: "#241f3a",
    chip: "#0f1318",
}
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-cr-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
//   prefix `cr` = CompanyReports. 기존 사용 중 prefix(exh hld mb mbr mkt nws plc psm thn trv vcp)와 충돌 없음.
const _ANP = "cr"
const AN_PALETTE =
    "body{" +
    Object.keys(LIGHT)
        .map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k])
        .join(";") +
    "}" +
    'body[data-framer-theme="dark"]{' +
    Object.keys(DARK)
        .map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k])
        .join(";") +
    "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

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
function isKrSecurityCode(tk: any): boolean {
    return /^\d[0-9A-Z]{5}$/i.test(String(tk || "").trim())
}

// 외부 리포트·자료 링크 — KR(네이버 금융·DART) / US(SEC EDGAR·Yahoo). 종목코드/티커로 딥링크.
function linksFor(tk: string): { label: string; src: string; url: string }[] {
    const t = String(tk || "").trim()
    if (!t) return []
    const isKR = isKrSecurityCode(t)
    if (isKR) {
        const c = encodeURIComponent(t)
        // 공시 목록과 리서치 목록 모두 종목 코드를 실제 필터 파라미터로 전달한다.
        return [
            {
                label: "공시·정기보고서 (사업·분기보고서)",
                src: "네이버 금융 · KOSCOM 공시 목록",
                url: `https://finance.naver.com/item/news_notice.naver?code=${c}`,
            },
            {
                label: "증권사 리포트",
                src: "네이버 금융 리서치",
                url: `https://finance.naver.com/research/company_list.naver?searchType=itemCode&itemCode=${c}`,
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
// 🚨 2026-08-21 — JS 다크 감지 전면 제거. 종전에는 `__anHyd`/`anReadDark`/`readBodyDark` +
//   MutationObserver 로 테마를 자바스크립트가 읽어 상태에 넣고, 색을 그 상태로 갈랐다.
//   그 방식은 첫 페인트가 항상 라이트여서 페이지 이동마다 번쩍였고(그래서 __anHyd 같은
//   회피 코드가 붙었다), 정적 HTML 에서는 아예 라이트로 굳었다.
//   이제 색은 `body[data-framer-theme]` 에 걸린 **CSS 변수**가 정한다 — 자바스크립트가
//   테마를 알 필요도, 리렌더할 필요도 없다. 되돌리지 말 것.

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
    // 🚨 테마 상태 없음 — 색은 모듈 최상단 `C`(= CSS 변수 참조)가 정한다.
    //   `dark` prop 은 캔버스 잔존물이라 property control 라벨이 "Dark(미사용)" 이다.

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
                fetch(u)
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
        background: "transparent",
        fontFamily: FONT,
        padding: w > 0 && w < 560 ? "0 12px" : "0 18px",
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
                {/* 🚨 이 분기에도 팔레트가 필요하다 — 조기 반환에서 빠지면 이 화면만 색이 죽는다 */}
                <style>{AN_PALETTE}</style>
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

    if (assetKind === "etf" || /^CMD_/.test(String(tk).toUpperCase())) return null // ETF/ETN = 기업 전용 섹션 숨김

    return (
        <div ref={rootRef} style={wrap}>
            <style>{AN_PALETTE}</style>
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
                                {/* 🚨 stroke 를 프레젠테이션 attribute 로 주면 안 된다 —
                                    CSS 변수가 거기서는 해석되지 않아 선이 사라진다.
                                    반드시 style 로 넘긴다(테마 codemod 3번 항목). */}
                                <svg
                                    width="13"
                                    height="13"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    style={{ stroke: C.vt }}
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
    // 🚨 CSS 변수 전환 후 이 토글은 색을 바꾸지 않는다(캔버스 잔존). 지우면 기존 인스턴스의
    //   저장된 prop 이 깨지므로 라벨만 바꿔 남긴다.
    dark: {
        type: ControlType.Boolean,
        title: "Dark(미사용)",
        defaultValue: false,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
})

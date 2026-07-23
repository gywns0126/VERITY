import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect, useMemo } from "react"

/**
 * 소형주 스크리너 (통합) — 🇰🇷 한국 / 🇺🇸 미국 국기 토글로 전환. 1개로 KR+US 둘 다.
 * 기존 SmallcapScreener(KR) + USSmallcapScreener(US) 통합 (2026-06-27). market별 config inline.
 *
 * 2026-07-19 리디자인 v2 (토스식 클린): 필터 2렌즈(기회/위험) 그룹 + 선택 필터 설명 카드.
 *   색 절제 — 카드=중립 흰색, 기준·읽는법=muted, 렌즈 강조=섹션 라벨 작은 점 + 뱃지만. 앰버 떡칠 제거.
 * 🚨 외곽선 금지(feedback_no_border_outline) — 보더 0, 분리/강조=채움색·여백·타이포만. ship 전 border grep 의무.
 * 🚨 RULE 7 — 정렬은 사실 메트릭 정렬(점수·등급·순위·추천 0). RULE 6 — LLM narrative 0.
 * data: smallcap_corner_filters.json / us_smallcap_corner_filters.json. 다크모드 자가감지.
 */

const LIGHT = {
    bg: "#f2f4f6",
    card: "#ffffff",
    ink: "#191f28",
    sub: "#4e5968",
    faint: "#8b95a1",
    line: "#e5e8eb",
    red: "#f04452",
    redSoft: "#fff0f1",
    amber: "#ff9500",
    amberSoft: "#fff6e9",
    blue: "#3182f6",
    blueSoft: "#eef4ff",
    green: "#15c47e",
    greenSoft: "#eafaf3",
    violet: "#6c5ce7",
    violetSoft: "#f0edff",
}
const DARK = {
    bg: "#0f1318",
    card: "#1e2128",
    ink: "#f0f2f5",
    sub: "#b0b8c1",
    faint: "#6b7684",
    line: "#2b2f37",
    red: "#ff6b76",
    redSoft: "#3a1f22",
    amber: "#ffb340",
    amberSoft: "#3a2c14",
    blue: "#5a9cff",
    blueSoft: "#1b2740",
    green: "#3ddc97",
    greenSoft: "#16322a",
    violet: "#a98bff",
    violetSoft: "#2a2440",
}
const FLAG = "https://hatscripts.github.io/circle-flags/flags/"

// 렌즈 — 방치·우량 = 기회(발굴), 나머지 = 위험(회피). 필터 key 기준.
const LENS: Record<string, "opp" | "risk"> = {
    neglected_quality: "opp",
    smallcap_dilution: "risk",
    smallcap_distress: "risk",
    clean_fin_risky_disc: "risk",
    accounting_red_flag: "risk",
}
const LENS_META: Record<"opp" | "risk", { label: string }> = {
    opp: { label: "기회 · 숨은 우량주 발굴" },
    risk: { label: "위험 · 피할 것 거르기" },
}
// 읽는 법 — UI 가이드(사실 프레이밍, 예측 아님). data.read_how 있으면 그게 우선.
const READ_HOW: Record<string, string> = {
    neglected_quality:
        "\"싸다\"가 아니라 \"안 알려졌고 재무가 깨끗하다\"는 뜻. 저평가 여부는 직접 판단하세요.",
    smallcap_dilution:
        "성장 자금인지 연명인지는 공시 원문 확인. 계속 찍는 회사는 실적이 늘어도 주당가치가 제자리일 수 있어요.",
    smallcap_distress:
        "기본은 회피 리스트로 쓰세요. 턴어라운드 베팅은 고위험이라 별도 판단.",
    clean_fin_risky_disc:
        "\"재무 좋아서 샀는데 왜 물리지\"의 예방. 재무 통과가 안전을 뜻하진 않아요.",
    accounting_red_flag:
        "재무제표 재작성·감사인 교체는 회계 부정의 선행 신호. 재무 숫자 자체를 의심하는 구간.",
}

function readBodyDark(): boolean {
    // 기본 = 라이트(사이트 첫 시작 라이트 결정, 2026-07-19). 명시적 'dark' 신호가 있을 때만 다크.
    //   판독 순서 = html[data-an-theme](Custom Code 헤드 스크립트가 페인트 전 동기 세팅, 레이스 제거)
    //   → body[data-framer-theme](토글) → localStorage. OS 설정은 안 봄(로드마다 뒤집힘 방지).
    //   🚨 body-first 로 되돌리지 말 것 — Framer 네이티브가 새로고침 때 body 를 OS 로 리셋 → 부분 라이트 회귀(2026-07-23).
    try {
        if (typeof document !== "undefined") {
            const h = document.documentElement ? document.documentElement.dataset.anTheme : null
            if (h === "dark") return true
            if (h === "light") return false
            if (document.body) {
                const a = document.body.dataset.framerTheme
                if (a === "dark") return true
                if (a === "light") return false
            }
        }
        const s = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (s === "dark") return true
    } catch (e) {}
    return false
}
function eok(won: number): string {
    const v = Math.round(won / 1e8)
    return v.toLocaleString() + "억"
}
function musd(m: number): string {
    if (m == null) return "—"
    if (m >= 1000) return "$" + (m / 1000).toFixed(1) + "B"
    return "$" + Math.round(m).toLocaleString() + "M"
}
const ZONE_KO: Record<string, string> = {
    safe: "안전",
    grey: "주의",
    distress: "위험",
}
const PAGE = 20

type Facts = { [k: string]: any }
type Ticker = { ticker: string; name: string; market?: string; facts: Facts }
type Sort = { key: string; label: string; dir: "asc" | "desc" }
type MarketCfg = {
    label: string
    flag: string
    title: string
    url: string
    cacheKey: string
    reportPath: string
    placeholder: string
    sorts: Sort[]
    sigLabel: string
    search: (t: Ticker, qq: string) => boolean
    metrics: (f: Facts) => string[]
    signals: (f: Facts) => string[]
}

const MARKETS: Record<"kr" | "us", MarketCfg> = {
    kr: {
        label: "한국",
        flag: "kr",
        title: "소형주 스크리너",
        url: "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/smallcap_corner_filters.json",
        cacheKey: "smallcap_screener_cache",
        reportPath: "/stock",
        placeholder: "티커·종목명 검색",
        sigLabel: "공시",
        sorts: [
            { key: "시총_억", label: "시총↑", dir: "asc" },
            { key: "roa", label: "ROA↓", dir: "desc" },
            { key: "순이익", label: "순이익↓", dir: "desc" },
            { key: "부채비율", label: "부채↑", dir: "asc" },
        ],
        search: (t, qq) =>
            String(t.ticker).toLowerCase().includes(qq) ||
            String(t.name || "")
                .toLowerCase()
                .includes(qq),
        metrics: (f) => {
            const m: string[] = []
            if (f["시총_억"] != null)
                m.push(
                    "시총 " + Math.round(f["시총_억"]).toLocaleString() + "억"
                )
            if (f["부채비율"] != null)
                m.push("부채 " + f["부채비율"].toFixed(0) + "%")
            if (f["roa"] != null) m.push("ROA " + f["roa"].toFixed(1) + "%")
            if (f["순이익"] != null) m.push("순익 " + eok(f["순이익"]))
            return m
        },
        signals: (f) => {
            const s: string[] = []
            const pairs: [string, string][] = [
                ["유상증자", "유상증자"],
                ["CB_BW", "CB/BW"],
                ["회생·상폐·감자", "회생·상폐·감자"],
                ["구조공시", "구조공시"],
            ]
            for (const [k, lab] of pairs)
                if (f[k] != null) s.push(lab + " " + f[k])
            return s
        },
    },
    us: {
        label: "미국",
        flag: "us",
        title: "미장 소형주 스크리너",
        url: "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/us_smallcap_corner_filters.json",
        cacheKey: "us_smallcap_screener_cache",
        reportPath: "/us",
        placeholder: "티커·종목명·업종 검색",
        sigLabel: "8-K",
        sorts: [
            { key: "mktcap_musd", label: "시총↑", dir: "asc" },
            { key: "dollar_volume_musd", label: "거래대금↓", dir: "desc" },
            { key: "revenue_yoy_pct", label: "매출성장↓", dir: "desc" },
            { key: "fscore", label: "F-Score↓", dir: "desc" },
            { key: "debt_to_equity", label: "부채↑", dir: "asc" },
        ],
        search: (t, qq) =>
            String(t.ticker).toLowerCase().includes(qq) ||
            String(t.name || "")
                .toLowerCase()
                .includes(qq) ||
            String((t.facts || {}).business_ko || "")
                .toLowerCase()
                .includes(qq) ||
            String((t.facts || {}).name_ko || "").includes(qq),
        metrics: (f) => {
            const m: string[] = []
            if (f.mktcap_musd != null) m.push("시총 " + musd(f.mktcap_musd))
            if (f.dollar_volume_musd != null)
                m.push("거래 " + musd(f.dollar_volume_musd))
            if (f.revenue_yoy_pct != null)
                m.push(
                    "매출 " +
                        (f.revenue_yoy_pct >= 0 ? "+" : "") +
                        f.revenue_yoy_pct.toFixed(0) +
                        "%"
                )
            if (f.operating_margin_pct != null)
                m.push("영업 " + f.operating_margin_pct.toFixed(0) + "%")
            if (f.roe_pct != null) m.push("ROE " + f.roe_pct.toFixed(0) + "%")
            if (f.debt_to_equity != null)
                m.push("D/E " + f.debt_to_equity.toFixed(1))
            if (f.altman_zone && ZONE_KO[f.altman_zone])
                m.push("Altman " + ZONE_KO[f.altman_zone])
            if (f.fscore != null) m.push("F " + f.fscore + "/9")
            return m
        },
        signals: (f) => {
            const s: string[] = []
            if (f.dilution_8k) s.push("희석 " + f.dilution_8k)
            if (f.distress_8k) s.push("부실 " + f.distress_8k)
            if (f.restatement) s.push("재무재작성 " + f.restatement)
            if (f.auditor_change) s.push("회계법인교체 " + f.auditor_change)
            return s
        },
    },
}

export default function SmallcapScreenerAll(props: {
    width?: number
    dark?: boolean
    market?: string
    krReportPath?: string
    usReportPath?: string
    initialFilter?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const width = props.width || 380

    const [market, setMarket] = useState<"kr" | "us">(
        props.market === "us" ? "us" : "kr"
    )
    const cfg = MARKETS[market]
    const reportPath =
        market === "us"
            ? props.usReportPath || cfg.reportPath
            : props.krReportPath || cfg.reportPath

    const [data, setData] = useState<any>(null)
    const [err, setErr] = useState<string>("")
    const [fIdx, setFIdx] = useState<number>(0)
    const [sIdx, setSIdx] = useState<number>(0)
    const [q, setQ] = useState<string>("")
    const [page, setPage] = useState<number>(0)

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (
            typeof MutationObserver === "undefined" ||
            typeof document === "undefined" ||
            !document.body
        )
            return
        const obs = new MutationObserver(read)
        obs.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-framer-theme"],
        })
        return () => obs.disconnect()
    }, [onCanvas])

    // 데이터 로드 — market 전환 시 재fetch (market별 cache key)
    useEffect(() => {
        let alive = true
        setData(null)
        setErr("")
        fetch(cfg.url + "?t=" + Date.now())
            .then((r) => {
                if (!r.ok) throw new Error("http " + r.status)
                return r.json()
            })
            .then((j) => {
                if (!alive) return
                setData(j)
                try {
                    sessionStorage.setItem(cfg.cacheKey, JSON.stringify(j))
                } catch (e) {}
            })
            .catch((e) => {
                if (!alive) return
                try {
                    const c = sessionStorage.getItem(cfg.cacheKey)
                    if (c) {
                        setData(JSON.parse(c))
                        return
                    }
                } catch (er) {}
                setErr(String(e))
            })
        return () => {
            alive = false
        }
    }, [cfg.url, cfg.cacheKey])

    useEffect(() => {
        if (!data) return
        const filters: any[] = data.filters || []
        let want = props.initialFilter || ""
        if (typeof window !== "undefined" && !want)
            want = (
                new URLSearchParams(window.location.search).get("filter") || ""
            ).trim()
        if (want) {
            const i = filters.findIndex((f) => f.key === want)
            if (i >= 0) setFIdx(i)
        }
    }, [data, props.initialFilter])

    const filters: any[] = (data && data.filters) || []
    const cur = filters[fIdx] || null

    const rows = useMemo(() => {
        if (!cur) return []
        const sort = cfg.sorts[sIdx] || cfg.sorts[0]
        const qq = q.trim().toLowerCase()
        let arr: Ticker[] = cur.tickers || []
        if (qq) arr = arr.filter((t) => cfg.search(t, qq))
        const val = (t: Ticker) => {
            const v = (t.facts || {})[sort.key]
            return typeof v === "number"
                ? v
                : sort.dir === "asc"
                  ? Infinity
                  : -Infinity
        }
        return [...arr].sort((a, b) =>
            sort.dir === "asc" ? val(a) - val(b) : val(b) - val(a)
        )
    }, [cur, sIdx, q, market])

    useEffect(() => {
        setPage(0)
    }, [fIdx, sIdx, q, market])

    const switchMarket = (mk: "kr" | "us") => {
        if (mk === market) return
        setMarket(mk)
        setFIdx(0)
        setSIdx(0)
        setQ("")
        setPage(0)
    }

    const shell = {
        width,
        fontFamily: "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif",
        background: "transparent",
        borderRadius: 24,
        padding: "0 16px",
        boxSizing: "border-box" as const,
        color: C.ink,
    }
    const flagBtn = (mk: "kr" | "us") => {
        const active = market === mk
        return (
            <div
                onClick={() => switchMarket(mk)}
                style={{
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "5px 11px 5px 7px",
                    borderRadius: 999,
                    background: active ? C.violet : C.card,
                    color: active ? C.bg : C.sub,
                    fontSize: 12.5,
                    fontWeight: 800,
                    letterSpacing: -0.2,
                }}
            >
                <img
                    src={FLAG + MARKETS[mk].flag + ".svg"}
                    alt=""
                    width={18}
                    height={18}
                    style={{
                        width: 18,
                        height: 18,
                        borderRadius: "50%",
                        display: "block",
                    }}
                />
                {MARKETS[mk].label}
            </div>
        )
    }
    const lensTone = (lens: "opp" | "risk") =>
        lens === "opp"
            ? { c: C.green, bg: C.greenSoft }
            : { c: C.amber, bg: C.amberSoft }

    const shown = rows.slice(0, (page + 1) * PAGE)

    return (
        <div style={shell}>
            {/* 국기 토글 + 카운트 */}
            <div
                style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "2px 2px 12px",
                    gap: 8,
                }}
            >
                <div style={{ display: "flex", gap: 6 }}>
                    {flagBtn("kr")}
                    {flagBtn("us")}
                </div>
                <div style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>
                    {data ? rows.length.toLocaleString() + "종목" : ""}
                </div>
            </div>

            {err && !data ? (
                <div
                    style={{
                        fontSize: 13,
                        color: C.faint,
                        fontWeight: 600,
                        padding: 20,
                        textAlign: "center",
                    }}
                >
                    로드 실패 — {err}
                </div>
            ) : !data ? (
                (() => {
                    const skB = isDark ? "#242830" : "#e9edf1"
                    const skH = isDark ? "#2e333c" : "#f3f5f7"
                    const bar = (w: any, h: number, r = 8) => ({
                        width: w,
                        height: h,
                        borderRadius: r,
                        background: skB,
                        flexShrink: 0,
                        backgroundImage:
                            "linear-gradient(90deg, " +
                            skB +
                            " 25%, " +
                            skH +
                            " 37%, " +
                            skB +
                            " 63%)",
                        backgroundSize: "800px 100%",
                        animation: "vsaShimmer 1.4s ease-in-out infinite",
                    })
                    return (
                        <div>
                            <style>
                                {
                                    "@keyframes vsaShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}"
                                }
                            </style>
                            <div
                                style={{
                                    display: "flex",
                                    gap: 6,
                                    paddingBottom: 10,
                                }}
                            >
                                {[64, 52, 48, 56].map((w, i) => (
                                    <div key={i} style={bar(w, 30, 10)} />
                                ))}
                            </div>
                            <div
                                style={{
                                    ...bar("100%", 84, 14),
                                    marginBottom: 8,
                                }}
                            />
                            <div
                                style={{
                                    ...bar("100%", 38, 12),
                                    marginBottom: 8,
                                }}
                            />
                            <div
                                style={{
                                    background: C.card,
                                    borderRadius: 16,
                                    padding: "12px 14px",
                                }}
                            >
                                {[0, 1, 2, 3, 4, 5].map((j) => (
                                    <div
                                        key={j}
                                        style={{
                                            padding: "10px 0",
                                            borderTop:
                                                j === 0
                                                    ? "none"
                                                    : "1px solid " + C.line,
                                        }}
                                    >
                                        <div
                                            style={{
                                                ...bar(140, 14, 5),
                                                marginBottom: 6,
                                            }}
                                        />
                                        <div style={bar("70%", 11, 4)} />
                                    </div>
                                ))}
                            </div>
                        </div>
                    )
                })()
            ) : (
                <>
                    {/* 이 코너 읽는 법 */}
                    <div
                        style={{
                            fontSize: 11.5,
                            color: C.faint,
                            fontWeight: 600,
                            lineHeight: 1.55,
                            padding: "0 2px 12px",
                            letterSpacing: -0.2,
                        }}
                    >
                        방치·우량 = 숨은 우량주 발굴 · 희석/부실/교차 = 피할 위험
                        거르기. 전부 사실 기준 필터(추천·점수 아님).
                    </div>

                    {/* 필터 탭 — 렌즈(기회/위험) 그룹 · 라벨=회색+작은 점 */}
                    {(["opp", "risk"] as const).map((lens) => {
                        const group = filters
                            .map((f, i) => ({ f, i }))
                            .filter((x) => (LENS[x.f.key] || "risk") === lens)
                        if (!group.length) return null
                        const tone = lensTone(lens)
                        return (
                            <div key={lens} style={{ marginBottom: 10 }}>
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 5,
                                        padding: "0 2px 6px",
                                    }}
                                >
                                    <span
                                        style={{
                                            width: 5,
                                            height: 5,
                                            borderRadius: "50%",
                                            background: tone.c,
                                            flexShrink: 0,
                                        }}
                                    />
                                    <span
                                        style={{
                                            fontSize: 11,
                                            fontWeight: 800,
                                            color: C.sub,
                                            letterSpacing: -0.2,
                                        }}
                                    >
                                        {LENS_META[lens].label}
                                    </span>
                                </div>
                                <div
                                    style={{
                                        display: "flex",
                                        gap: 6,
                                        overflowX: "auto",
                                        paddingBottom: 2,
                                    }}
                                >
                                    {group.map(({ f, i }) => {
                                        const sel = i === fIdx
                                        return (
                                            <div
                                                key={i}
                                                onClick={() => setFIdx(i)}
                                                style={{
                                                    cursor: "pointer",
                                                    flexShrink: 0,
                                                    fontSize: 12,
                                                    fontWeight: sel ? 800 : 700,
                                                    padding: "7px 12px",
                                                    borderRadius: 10,
                                                    background: sel
                                                        ? C.violetSoft
                                                        : C.card,
                                                    color: sel
                                                        ? C.violet
                                                        : C.sub,
                                                    letterSpacing: -0.2,
                                                }}
                                            >
                                                {f.badge} {f.count}
                                            </div>
                                        )
                                    })}
                                </div>
                            </div>
                        )
                    })}

                    {/* 선택 필터 설명 카드 — 중립 흰 카드, 색은 뱃지 악센트만 */}
                    {cur
                        ? (() => {
                              const lens = LENS[cur.key] || "risk"
                              const tone = lensTone(lens)
                              const readHow =
                                  cur.read_how || READ_HOW[cur.key] || ""
                              return (
                                  <div
                                      style={{
                                          background: C.card,
                                          borderRadius: 14,
                                          padding: "15px 16px",
                                          marginBottom: 10,
                                      }}
                                  >
                                      <div
                                          style={{
                                              display: "flex",
                                              alignItems: "baseline",
                                              gap: 7,
                                              marginBottom: 7,
                                              flexWrap: "wrap",
                                          }}
                                      >
                                          <span
                                              style={{
                                                  fontSize: 14.5,
                                                  fontWeight: 800,
                                                  color: C.ink,
                                                  letterSpacing: -0.3,
                                              }}
                                          >
                                              {cur.name || cur.badge}
                                          </span>
                                          <span
                                              style={{
                                                  fontSize: 10,
                                                  fontWeight: 800,
                                                  color: tone.c,
                                                  background: tone.bg,
                                                  borderRadius: 6,
                                                  padding: "2px 7px",
                                              }}
                                          >
                                              {cur.badge}
                                          </span>
                                          <span
                                              style={{
                                                  fontSize: 11,
                                                  color: C.faint,
                                                  fontWeight: 700,
                                                  marginLeft: "auto",
                                              }}
                                          >
                                              {cur.count}종목
                                          </span>
                                      </div>
                                      {cur.why ? (
                                          <div
                                              style={{
                                                  fontSize: 12.5,
                                                  color: C.sub,
                                                  fontWeight: 600,
                                                  lineHeight: 1.6,
                                                  marginBottom: 9,
                                                  letterSpacing: -0.2,
                                              }}
                                          >
                                              {cur.why}
                                          </div>
                                      ) : null}
                                      {cur.criteria_text ? (
                                          <div
                                              style={{
                                                  fontSize: 11,
                                                  color: C.faint,
                                                  fontWeight: 600,
                                                  lineHeight: 1.6,
                                                  marginBottom: readHow ? 5 : 0,
                                                  letterSpacing: -0.2,
                                              }}
                                          >
                                              <span
                                                  style={{
                                                      fontWeight: 800,
                                                      color: C.sub,
                                                  }}
                                              >
                                                  기준
                                              </span>
                                              {"  "}
                                              {cur.criteria_text}
                                          </div>
                                      ) : null}
                                      {readHow ? (
                                          <div
                                              style={{
                                                  fontSize: 11,
                                                  color: C.faint,
                                                  fontWeight: 600,
                                                  lineHeight: 1.6,
                                                  letterSpacing: -0.2,
                                              }}
                                          >
                                              <span
                                                  style={{
                                                      fontWeight: 800,
                                                      color: C.sub,
                                                  }}
                                              >
                                                  읽는 법
                                              </span>
                                              {"  "}
                                              {readHow}
                                          </div>
                                      ) : null}
                                  </div>
                              )
                          })()
                        : null}

                    {/* 검색 + 정렬 */}
                    <input
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        placeholder={cfg.placeholder}
                        style={{
                            width: "100%",
                            boxSizing: "border-box",
                            fontSize: 13,
                            fontWeight: 600,
                            padding: "10px 12px",
                            borderRadius: 12,
                            border: "none",
                            background: C.card,
                            color: C.ink,
                            marginBottom: 8,
                            outline: "none",
                        }}
                    />
                    <div
                        style={{
                            display: "flex",
                            gap: 6,
                            overflowX: "auto",
                            paddingBottom: 10,
                        }}
                    >
                        {cfg.sorts.map((s, i) => (
                            <div
                                key={i}
                                onClick={() => setSIdx(i)}
                                style={{
                                    cursor: "pointer",
                                    flexShrink: 0,
                                    fontSize: 11.5,
                                    fontWeight: 700,
                                    padding: "6px 11px",
                                    borderRadius: 9,
                                    background:
                                        i === sIdx
                                            ? C.violetSoft
                                            : "transparent",
                                    color: i === sIdx ? C.violet : C.faint,
                                    letterSpacing: -0.2,
                                }}
                            >
                                {s.label}
                            </div>
                        ))}
                    </div>

                    {/* 종목 리스트 */}
                    <div
                        style={{
                            background: C.card,
                            borderRadius: 16,
                            padding: "4px 14px 12px",
                        }}
                    >
                        {shown.length === 0 ? (
                            <div
                                style={{
                                    fontSize: 12.5,
                                    color: C.faint,
                                    fontWeight: 600,
                                    padding: "20px 0",
                                    textAlign: "center",
                                }}
                            >
                                해당 종목 없음
                            </div>
                        ) : (
                            shown.map((t, j) => {
                                const f = t.facts || {}
                                const url =
                                    reportPath +
                                    "?q=" +
                                    encodeURIComponent(t.ticker)
                                const m = cfg.metrics(f)
                                const sig = cfg.signals(f)
                                return (
                                    <div
                                        key={j}
                                        style={{
                                            padding: "10px 0",
                                            borderTop:
                                                j === 0
                                                    ? "none"
                                                    : "1px solid " + C.line,
                                        }}
                                    >
                                        <div
                                            style={{
                                                display: "flex",
                                                alignItems: "baseline",
                                                justifyContent: "space-between",
                                                gap: 8,
                                                marginBottom: 3,
                                                flexWrap: "wrap",
                                            }}
                                        >
                                            <div
                                                style={{
                                                    display: "flex",
                                                    alignItems: "baseline",
                                                    gap: 6,
                                                    minWidth: 0,
                                                    flexWrap: "wrap",
                                                }}
                                            >
                                                <a
                                                    href={url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    style={{
                                                        fontSize: 14,
                                                        fontWeight: 700,
                                                        color: C.violet,
                                                        textDecoration: "none",
                                                        letterSpacing: -0.2,
                                                    }}
                                                >
                                                    {t.name} ↗
                                                </a>
                                                {market === "us" &&
                                                f.name_ko ? (
                                                    <span
                                                        style={{
                                                            fontSize: 11.5,
                                                            color: C.sub,
                                                            fontWeight: 600,
                                                        }}
                                                    >
                                                        {f.name_ko}
                                                    </span>
                                                ) : null}
                                                <span
                                                    style={{
                                                        fontSize: 11,
                                                        color: C.faint,
                                                        fontWeight: 600,
                                                    }}
                                                >
                                                    {t.ticker}
                                                </span>
                                                {market === "kr" && t.market ? (
                                                    <span
                                                        style={{
                                                            fontSize: 10.5,
                                                            color: C.faint,
                                                            fontWeight: 700,
                                                        }}
                                                    >
                                                        {t.market}
                                                    </span>
                                                ) : null}
                                            </div>
                                            {market === "us" &&
                                            f.business_ko ? (
                                                <span
                                                    style={{
                                                        fontSize: 11,
                                                        color: C.faint,
                                                        fontWeight: 600,
                                                    }}
                                                >
                                                    {f.business_ko}
                                                </span>
                                            ) : null}
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 11.5,
                                                color: C.sub,
                                                fontWeight: 600,
                                                letterSpacing: -0.2,
                                                lineHeight: 1.55,
                                            }}
                                        >
                                            {m.join(" · ")}
                                        </div>
                                        {sig.length > 0 ? (
                                            <div
                                                style={{
                                                    fontSize: 11,
                                                    color: C.amber,
                                                    fontWeight: 700,
                                                    marginTop: 2,
                                                    letterSpacing: -0.2,
                                                }}
                                            >
                                                {cfg.sigLabel} ·{" "}
                                                {sig.join(" · ")}
                                            </div>
                                        ) : null}
                                    </div>
                                )
                            })
                        )}
                        {shown.length < rows.length ? (
                            <div
                                onClick={() => setPage(page + 1)}
                                style={{
                                    cursor: "pointer",
                                    textAlign: "center",
                                    fontSize: 12.5,
                                    fontWeight: 700,
                                    color: C.violet,
                                    padding: "12px 0 4px",
                                }}
                            >
                                + {Math.min(PAGE, rows.length - shown.length)}개
                                더 ({shown.length}/{rows.length})
                            </div>
                        ) : null}
                    </div>

                    <div
                        style={{
                            textAlign: "center",
                            fontSize: 11,
                            color: C.faint,
                            fontWeight: 600,
                            padding: "10px 8px 2px",
                            lineHeight: 1.5,
                        }}
                    >
                        {(data._meta || {}).disclaimer ||
                            "사실·패턴만 · 정렬=메트릭 정렬"}
                    </div>
                </>
            )}
        </div>
    )
}

addPropertyControls(SmallcapScreenerAll, {
    width: {
        type: ControlType.Number,
        title: "Width",
        defaultValue: 380,
        min: 320,
        max: 720,
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark (canvas)",
        defaultValue: false,
    },
    market: {
        type: ControlType.Enum,
        title: "기본 시장",
        options: ["kr", "us"],
        optionTitles: ["한국", "미국"],
        defaultValue: "kr",
    },
    krReportPath: {
        type: ControlType.String,
        title: "KR 리포트 경로",
        defaultValue: "/stock",
    },
    usReportPath: {
        type: ControlType.String,
        title: "US 리포트 경로",
        defaultValue: "/us",
    },
    initialFilter: {
        type: ControlType.String,
        title: "진입 필터 key",
        defaultValue: "",
    },
})

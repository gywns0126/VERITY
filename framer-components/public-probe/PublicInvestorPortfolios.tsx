import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState } from "react"

/**
 * 거장의 포트폴리오 — SEC 13F 공시 기반 인물 축 뷰 (공개 probe).
 *
 * 데이터 = data/us_investor_portfolios.json (SEC EDGAR 13F-HR + OpenFIGI CUSIP→ticker).
 * 기존 us_smart_money_13f 는 종목 축("이 종목을 누가 들고 있나")이고, 본 컴포넌트는
 * 인물/기관 축("이 사람이 뭘 들고 있나")이다. 원천 동일.
 *
 * 🚨 RULE 7 = 공시 사실 + 공시 유래 계산값만. 자체 점수·매매신호 0.
 *
 * 🚨🚨 '실시간 수익률 랭킹' 을 만들지 말 것 (이 컴포넌트의 설계 전제):
 *   · 13F 는 분기말 보유를 최대 45일 뒤 제출 — 실측 Berkshire reportDate 2026-03-31 /
 *     filingDate 2026-05-15. 조회 시점엔 이미 수개월 전 스냅샷이다.
 *   · 롱 미국주식만 담긴다(숏·채권·현금·비미국·대부분 파생 제외).
 *   → 랭킹 기준은 공시 총액. 수익률은 '복제'(분기말 포지션을 다음 분기말까지 그대로 보유
 *     가정)만 노출하고 실제 성과가 아님을 화면에 명시한다.
 *
 * 원화 토글 = macro_snapshot.json 의 macro.usd_krw 실시간 조회(PublicMorningBriefing 동일 관례).
 * 실패 시 FX_FALLBACK. 적용 환율·기준시각을 화면에 표기해 환산값의 출처를 감추지 않는다.
 *
 * 다크모드 = body[data-framer-theme] 자가감지 (기존 컴포넌트와 동일 — 손복사 드리프트 금지).
 */

const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const FX_FALLBACK = 1450

const LIGHT = {
    bg: "#faf9fd",
    card: "#ffffff",
    sunken: "#f3f2f8",
    ink: "#17161f",
    sub: "#4a4857",
    faint: "#7b7889",
    line: "#e9e7f1",
    accent: "#6c5ce7",
    accentSoft: "#efedfd",
    accentInk: "#4e3fd0",
    up: "#0f8f6c",
    down: "#c0554f",
}
const DARK = {
    bg: "#101018",
    card: "#191922",
    sunken: "#20202b",
    ink: "#eceaf5",
    sub: "#b3b0c4",
    faint: "#807d92",
    line: "#2a2a37",
    accent: "#8d7ffb",
    accentSoft: "#241f3d",
    accentInk: "#b3a8ff",
    up: "#3fc79a",
    down: "#e2726b",
}

const MONO =
    'ui-monospace, SFMono-Regular, Menlo, "SF Mono", monospace'

const KO_CHANGE: Record<string, string> = {
    NEW: "신규",
    INCREASED: "증액",
    DECREASED: "감액",
    HELD: "유지",
}

function readBodyDark(): boolean {
    try {
        const _lsPref =
            typeof localStorage !== "undefined"
                ? localStorage.getItem("verity_theme")
                : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
    } catch (e) {}
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

const dot = (s?: string | null) => (s || "").replace(/-/g, ".")

function daysBetween(a?: string | null, b?: string | null): number | null {
    if (!a || !b) return null
    const d = (new Date(b).getTime() - new Date(a).getTime()) / 86400000
    return Number.isFinite(d) ? Math.round(d) : null
}

function fmtMoney(v: number | null | undefined, krw: boolean, fx: number): string {
    if (v == null || !Number.isFinite(v)) return "—"
    if (!krw) {
        if (v >= 1e9) return "$" + (v / 1e9).toFixed(1) + "B"
        if (v >= 1e6) return "$" + (v / 1e6).toFixed(0) + "M"
        return "$" + Math.round(v).toLocaleString()
    }
    const w = v * fx
    if (w >= 1e12) return (w / 1e12).toFixed(1) + "조원"
    if (w >= 1e8) return Math.round(w / 1e8).toLocaleString() + "억원"
    return Math.round(w / 1e4).toLocaleString() + "만원"
}

const signed = (v: number | null | undefined) =>
    v == null || !Number.isFinite(v) ? "—" : (v > 0 ? "+" : "") + v.toFixed(1) + "%"

// 캔버스 미리보기용 최소 표본 — 빈 렌더 금지([[feedback_framer_layout_annotation_required]]).
// 실데이터 형태와 동일한 키만 사용(형태 drift 방지).
const CANVAS_SAMPLE = {
    _meta: { caveat: "", return_caveat: "" },
    investors: [
        {
            cik: "1067983",
            institution: "Berkshire Hathaway",
            person: "워런 버핏",
            report_date: "2026-03-31",
            filed_at: "2026-05-15",
            prev_report_date: "2025-12-31",
            holdings_count: 29,
            disclosed_value_usd: 263095703570,
            disclosed_value_change_pct: -4.04,
            top10_concentration_pct: 90.7,
            new_count: 1,
            increased_count: 4,
            decreased_count: 6,
            unresolved_ticker_count: 0,
            trailing_4q_replication_pct: 11.37,
            quarterly_replication_returns: [
                { to: "2025-06-30", return_pct: 0.32, coverage_pct: 99.6 },
                { to: "2025-09-30", return_pct: 7.07, coverage_pct: 99.9 },
                { to: "2025-12-31", return_pct: 4.58, coverage_pct: 99.3 },
                { to: "2026-03-31", return_pct: -0.86, coverage_pct: 95.7 },
            ],
            profile: null,
            top_holdings: [
                {
                    ticker: "AAPL",
                    cusip: "037833100",
                    weight_pct: 21.99,
                    value_usd: 57843260493,
                    shares: 227917808,
                    change_type: "HELD",
                },
                {
                    ticker: "AXP",
                    cusip: "025816109",
                    weight_pct: 17.43,
                    value_usd: 45859204536,
                    shares: 151610700,
                    change_type: "HELD",
                },
            ],
        },
    ],
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicInvestorPortfolios(props: {
    dataUrl?: string
    macroUrl?: string
    dark?: boolean
    topN?: number
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() =>
        onCanvas ? !!props.dark : readBodyDark()
    )
    // 🚨 훅은 전부 조건부 return 위 ([[feedback_framer_hooks_top_level]] — 2026-07-07 실사고)
    const [data, setData] = useState<any>(onCanvas ? CANVAS_SAMPLE : null)
    const [sel, setSel] = useState(0)
    const [krw, setKrw] = useState(false)
    const [fx, setFx] = useState<{ rate: number; asOf: string | null }>({
        rate: FX_FALLBACK,
        asOf: null,
    })

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

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.dataUrl || BLOB + "/us_investor_portfolios.json")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive && d && Array.isArray(d.investors)) setData(d)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas, props.dataUrl])

    // 실시간 환율 — macro_snapshot.macro.usd_krw (PublicMorningBriefing 과 동일 소스)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.macroUrl || BLOB + "/macro_snapshot.json")
            .then((r) => (r.ok ? r.json() : null))
            .then((m) => {
                const u = m && m.macro && m.macro.usd_krw
                const v = u && Number(u.value)
                if (alive && v && Number.isFinite(v) && v > 0)
                    setFx({ rate: v, asOf: u.as_of || m.collected_at || null })
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas, props.macroUrl])

    const C = themeDark ? DARK : LIGHT
    const list: any[] = useMemo(
        () => (data && Array.isArray(data.investors) ? data.investors : []),
        [data]
    )
    const cur = list[Math.min(sel, Math.max(list.length - 1, 0))] || null
    const topN = Math.max(3, props.topN ?? 25)

    const money = (v: any) => fmtMoney(v, krw, fx.rate)
    const tone = (v: any) =>
        v == null ? C.faint : v > 0 ? C.up : v < 0 ? C.down : C.sub

    if (!list.length) {
        return (
            <div
                style={{
                    background: C.bg,
                    color: C.faint,
                    padding: 28,
                    borderRadius: 16,
                    fontFamily: "inherit",
                    fontSize: 14,
                }}
            >
                거장 포트폴리오를 불러오는 중입니다.
            </div>
        )
    }

    const lagDays = daysBetween(cur?.report_date, cur?.filed_at)
    const rs: any[] = Array.isArray(cur?.quarterly_replication_returns)
        ? cur.quarterly_replication_returns
        : []
    const maxAbs = Math.max(1, ...rs.map((q) => Math.abs(q.return_pct || 0)))

    const chipBg = (t: string) =>
        t === "NEW"
            ? C.accentSoft
            : t === "INCREASED"
              ? themeDark
                  ? "rgba(63,199,154,.16)"
                  : "rgba(15,143,108,.12)"
              : t === "DECREASED"
                ? themeDark
                    ? "rgba(226,114,107,.16)"
                    : "rgba(192,85,79,.12)"
                : C.sunken
    const chipFg = (t: string) =>
        t === "NEW"
            ? C.accentInk
            : t === "INCREASED"
              ? C.up
              : t === "DECREASED"
                ? C.down
                : C.faint

    return (
        <div
            style={{
                width: "100%",
                background: C.bg,
                color: C.ink,
                fontFamily: "inherit",
                fontSize: 15,
                lineHeight: 1.6,
                padding: "4px 0 8px",
            }}
        >
            {/* 헤더 + 통화 토글 */}
            <div
                style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 14,
                    justifyContent: "space-between",
                    alignItems: "flex-end",
                    marginBottom: 18,
                }}
            >
                <div>
                    <div
                        style={{
                            fontSize: 24,
                            fontWeight: 800,
                            letterSpacing: "-0.022em",
                        }}
                    >
                        거장의 포트폴리오
                    </div>
                    <div style={{ color: C.faint, fontSize: 13.5, marginTop: 5 }}>
                        미국 증권거래위원회(SEC) 13F 공시로 확인되는 {list.length}개 운용사의 보유 종목
                    </div>
                </div>
                <div>
                    <div
                        style={{
                            display: "flex",
                            background: C.sunken,
                            borderRadius: 999,
                            padding: 3,
                            gap: 2,
                        }}
                    >
                        {[
                            { k: false, t: "USD" },
                            { k: true, t: "KRW" },
                        ].map((o) => (
                            <button
                                key={o.t}
                                type="button"
                                onClick={() => setKrw(o.k)}
                                aria-pressed={krw === o.k}
                                style={{
                                    border: 0,
                                    cursor: "pointer",
                                    font: "inherit",
                                    fontSize: 13,
                                    fontWeight: 600,
                                    padding: "6px 15px",
                                    borderRadius: 999,
                                    background: krw === o.k ? C.card : "transparent",
                                    color: krw === o.k ? C.accentInk : C.faint,
                                }}
                            >
                                {o.t}
                            </button>
                        ))}
                    </div>
                    {krw ? (
                        <div
                            style={{
                                fontSize: 11.5,
                                color: C.faint,
                                marginTop: 5,
                                textAlign: "right",
                            }}
                        >
                            1달러 = {fx.rate.toLocaleString()}원
                            {fx.asOf ? " · " + dot(fx.asOf.slice(0, 10)) + " 기준" : " · 근사값"}
                        </div>
                    ) : null}
                </div>
            </div>

            {/* 신선도 = 각주가 아니라 상단 1급 정보 */}
            <div
                style={{
                    background: C.card,
                    borderRadius: 16,
                    padding: "16px 18px",
                    marginBottom: 18,
                }}
            >
                <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: "-0.01em" }}>
                    지금 보는 건 실시간이 아니라 {dot(cur?.report_date)} 시점의 보유입니다.
                </div>
                <div style={{ color: C.sub, fontSize: 13, marginTop: 5 }}>
                    13F는 분기말 보유를 최대 45일 뒤에 제출합니다. 공시에는 미국 상장주식 매수
                    포지션만 담기고 공매도·채권·현금·해외자산은 빠집니다.
                </div>
                <div
                    style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 7,
                        marginTop: 10,
                        background: C.sunken,
                        borderRadius: 999,
                        padding: "5px 12px",
                        fontSize: 12.5,
                        color: C.sub,
                    }}
                >
                    <span
                        style={{
                            width: 6,
                            height: 6,
                            borderRadius: "50%",
                            background: C.accent,
                        }}
                    />
                    보유 기준일 {dot(cur?.report_date)} · 제출일 {dot(cur?.filed_at)}
                    {lagDays != null ? ` — 공시까지 ${lagDays}일` : ""}
                </div>
            </div>

            <div
                style={{
                    display: "grid",
                    gridTemplateColumns: "minmax(0,330px) minmax(0,1fr)",
                    gap: 18,
                    alignItems: "start",
                }}
            >
                {/* 좌: 운용사 목록 */}
                <div
                    style={{
                        background: C.card,
                        borderRadius: 16,
                        overflow: "hidden",
                        minWidth: 0,
                    }}
                >
                    <div
                        style={{
                            padding: "14px 16px 10px",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "baseline",
                        }}
                    >
                        <span
                            style={{
                                fontSize: 11.5,
                                fontWeight: 700,
                                letterSpacing: "0.09em",
                                color: C.faint,
                            }}
                        >
                            운용사
                        </span>
                        <span style={{ fontSize: 12, color: C.faint }}>공시 총액순</span>
                    </div>
                    <div style={{ maxHeight: 640, overflowY: "auto" }}>
                        {list.map((v, i) => {
                            const on = i === sel
                            return (
                                <button
                                    key={v.cik}
                                    type="button"
                                    onClick={() => setSel(i)}
                                    style={{
                                        width: "100%",
                                        textAlign: "left",
                                        border: 0,
                                        cursor: "pointer",
                                        font: "inherit",
                                        color: C.ink,
                                        background: on ? C.accentSoft : "transparent",
                                        padding: "11px 16px",
                                        display: "grid",
                                        gridTemplateColumns: "20px minmax(0,1fr) auto",
                                        gap: 10,
                                        alignItems: "center",
                                    }}
                                >
                                    <span
                                        style={{
                                            fontFamily: MONO,
                                            fontSize: 12,
                                            textAlign: "right",
                                            color: on ? C.accentInk : C.faint,
                                            fontWeight: on ? 700 : 400,
                                        }}
                                    >
                                        {i + 1}
                                    </span>
                                    <span style={{ minWidth: 0 }}>
                                        <span
                                            style={{
                                                display: "block",
                                                fontSize: 14,
                                                fontWeight: 650,
                                                whiteSpace: "nowrap",
                                                overflow: "hidden",
                                                textOverflow: "ellipsis",
                                            }}
                                        >
                                            {v.person || v.institution}
                                        </span>
                                        <span
                                            style={{
                                                display: "block",
                                                fontSize: 11.5,
                                                color: C.faint,
                                                whiteSpace: "nowrap",
                                                overflow: "hidden",
                                                textOverflow: "ellipsis",
                                            }}
                                        >
                                            {v.institution}
                                        </span>
                                        <span
                                            style={{
                                                display: "block",
                                                height: 3,
                                                borderRadius: 2,
                                                background: C.sunken,
                                                marginTop: 5,
                                                overflow: "hidden",
                                            }}
                                        >
                                            <span
                                                style={{
                                                    display: "block",
                                                    height: "100%",
                                                    width: `${v.top10_concentration_pct || 0}%`,
                                                    background: C.accent,
                                                    borderRadius: 2,
                                                }}
                                            />
                                        </span>
                                    </span>
                                    <span style={{ textAlign: "right" }}>
                                        <span
                                            style={{
                                                display: "block",
                                                fontFamily: MONO,
                                                fontSize: 13,
                                                fontWeight: 650,
                                            }}
                                        >
                                            {money(v.disclosed_value_usd)}
                                        </span>
                                        <span
                                            style={{
                                                display: "block",
                                                fontFamily: MONO,
                                                fontSize: 11,
                                                color: C.faint,
                                            }}
                                        >
                                            {v.holdings_count}종목
                                        </span>
                                    </span>
                                </button>
                            )
                        })}
                    </div>
                </div>

                {/* 우: 상세 */}
                <div
                    style={{
                        background: C.card,
                        borderRadius: 16,
                        padding: "18px 20px 22px",
                        minWidth: 0,
                    }}
                >
                    <div
                        style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: "10px 16px",
                            justifyContent: "space-between",
                            alignItems: "flex-start",
                        }}
                    >
                        <div>
                            <div
                                style={{
                                    fontSize: 20,
                                    fontWeight: 800,
                                    letterSpacing: "-0.02em",
                                }}
                            >
                                {cur.person || cur.institution}
                            </div>
                            <div style={{ color: C.faint, fontSize: 12.5, marginTop: 3 }}>
                                {cur.institution} · CIK {cur.cik}
                            </div>
                        </div>
                        <div
                            style={{
                                background: C.sunken,
                                borderRadius: 12,
                                padding: "8px 12px",
                                fontSize: 12,
                                color: C.sub,
                                textAlign: "right",
                            }}
                        >
                            <span
                                style={{
                                    display: "block",
                                    fontFamily: MONO,
                                    fontSize: 13,
                                    color: C.ink,
                                }}
                            >
                                {dot(cur.report_date)}
                            </span>
                            기준 보유 · {dot(cur.filed_at)} 제출
                        </div>
                    </div>

                    {cur.profile && cur.profile.summary ? (
                        <div
                            style={{
                                marginTop: 14,
                                background: C.sunken,
                                borderRadius: 13,
                                padding: "12px 14px",
                                fontSize: 13,
                                color: C.sub,
                                lineHeight: 1.68,
                            }}
                        >
                            {cur.profile.summary}
                            {cur.profile.source_url ? (
                                <div style={{ marginTop: 7 }}>
                                    <a
                                        href={cur.profile.source_url}
                                        target="_blank"
                                        rel="noopener"
                                        style={{
                                            color: C.accentInk,
                                            textDecoration: "none",
                                            fontSize: 12,
                                        }}
                                    >
                                        위키백과 · {cur.profile.name}
                                    </a>
                                </div>
                            ) : null}
                        </div>
                    ) : null}

                    {/* 요약 지표 */}
                    <div
                        style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))",
                            gap: 8,
                            marginTop: 15,
                        }}
                    >
                        {[
                            { l: "공시 총액", v: money(cur.disclosed_value_usd) },
                            { l: "보유 종목", v: String(cur.holdings_count) },
                            {
                                l: "상위 10종목 비중",
                                v: (cur.top10_concentration_pct ?? "—") + "%",
                            },
                            {
                                l: "최근 4분기 복제",
                                v: signed(cur.trailing_4q_replication_pct),
                                c: tone(cur.trailing_4q_replication_pct),
                                sub: "실제 성과 아님",
                            },
                            {
                                l: "분기 중 움직임",
                                v: `${cur.new_count}·${cur.increased_count}·${cur.decreased_count}`,
                                sub: "신규·증액·감액",
                            },
                        ].map((s) => (
                            <div
                                key={s.l}
                                style={{
                                    background: C.sunken,
                                    borderRadius: 12,
                                    padding: "10px 12px",
                                }}
                            >
                                <span
                                    style={{ display: "block", fontSize: 11.5, color: C.faint }}
                                >
                                    {s.l}
                                </span>
                                <span
                                    style={{
                                        display: "block",
                                        fontFamily: MONO,
                                        fontSize: 16.5,
                                        fontWeight: 700,
                                        marginTop: 3,
                                        color: (s as any).c || C.ink,
                                    }}
                                >
                                    {s.v}
                                </span>
                                {(s as any).sub ? (
                                    <span
                                        style={{ display: "block", fontSize: 11.5, color: C.faint }}
                                    >
                                        {(s as any).sub}
                                    </span>
                                ) : null}
                            </div>
                        ))}
                    </div>

                    {/* 분기 복제 수익률 그래프 */}
                    {rs.length ? (
                        <div
                            style={{
                                marginTop: 16,
                                background: C.sunken,
                                borderRadius: 13,
                                padding: "14px 14px 8px",
                            }}
                        >
                            <div style={{ fontSize: 12.5, fontWeight: 700 }}>
                                분기별 공시 롱 북 복제 수익률
                            </div>
                            <div
                                style={{
                                    fontSize: 11.5,
                                    color: C.faint,
                                    margin: "3px 0 12px",
                                    lineHeight: 1.55,
                                }}
                            >
                                각 분기말 공시 포지션을 다음 분기말까지 그대로 보유했다고 가정한
                                계산값입니다. 분기 중 매매가 반영되지 않아 실제 운용 성과와 다릅니다.
                            </div>
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "flex-end",
                                    gap: 6,
                                    height: 116,
                                }}
                            >
                                {rs.map((q) => {
                                    const up = (q.return_pct || 0) >= 0
                                    const h = Math.max(
                                        2,
                                        (Math.abs(q.return_pct || 0) / maxAbs) * 40
                                    )
                                    return (
                                        <div
                                            key={q.to}
                                            title={`커버리지 ${q.coverage_pct}%`}
                                            style={{
                                                flex: 1,
                                                minWidth: 0,
                                                display: "flex",
                                                flexDirection: "column",
                                                alignItems: "center",
                                                gap: 5,
                                            }}
                                        >
                                            <div
                                                style={{
                                                    width: "100%",
                                                    height: 86,
                                                    display: "flex",
                                                    flexDirection: "column",
                                                    justifyContent: "flex-end",
                                                }}
                                            >
                                                {up ? (
                                                    <span
                                                        style={{
                                                            fontSize: 10.5,
                                                            fontWeight: 650,
                                                            color: C.up,
                                                            textAlign: "center",
                                                        }}
                                                    >
                                                        {signed(q.return_pct)}
                                                    </span>
                                                ) : null}
                                                <span
                                                    style={{
                                                        height: h,
                                                        background: up ? C.up : C.down,
                                                        borderRadius: up ? "4px 4px 0 0" : "0 0 4px 4px",
                                                        marginTop: up ? "auto" : 0,
                                                    }}
                                                />
                                                {!up ? (
                                                    <span
                                                        style={{
                                                            fontSize: 10.5,
                                                            fontWeight: 650,
                                                            color: C.down,
                                                            textAlign: "center",
                                                        }}
                                                    >
                                                        {signed(q.return_pct)}
                                                    </span>
                                                ) : null}
                                            </div>
                                            <span
                                                style={{
                                                    fontSize: 10,
                                                    color: C.faint,
                                                    whiteSpace: "nowrap",
                                                }}
                                            >
                                                {dot(q.to).slice(2, 7)}
                                            </span>
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    ) : null}

                    <div
                        style={{
                            marginTop: 12,
                            fontSize: 12.5,
                            color: C.faint,
                            lineHeight: 1.6,
                        }}
                    >
                        직전 공시({dot(cur.prev_report_date) || "—"}) 대비 공시 총액 변동{" "}
                        {signed(cur.disclosed_value_change_pct)} — 주가 등락과 실제 매매가 함께
                        반영된 값이라 수익률이 아닙니다.
                    </div>
                    {cur.unresolved_ticker_count ? (
                        <div style={{ marginTop: 8, fontSize: 12.5, color: C.faint }}>
                            티커로 변환되지 않은 보유 {cur.unresolved_ticker_count}건은 CUSIP으로
                            표시됩니다.
                        </div>
                    ) : null}

                    {/* 보유 종목 */}
                    <div style={{ width: "100%", overflowX: "auto", marginTop: 12 }}>
                        <table
                            style={{
                                width: "100%",
                                borderCollapse: "collapse",
                                minWidth: 460,
                            }}
                        >
                            <thead>
                                <tr>
                                    {["종목", "비중", "평가액", "주식수", "분기 변동"].map(
                                        (h, i) => (
                                            <th
                                                key={h}
                                                style={{
                                                    fontSize: 11,
                                                    fontWeight: 600,
                                                    letterSpacing: "0.07em",
                                                    color: C.faint,
                                                    textAlign: i === 0 ? "left" : "right",
                                                    padding: "8px 9px",
                                                }}
                                            >
                                                {h}
                                            </th>
                                        )
                                    )}
                                </tr>
                            </thead>
                            <tbody>
                                {(cur.top_holdings || []).slice(0, topN).map((h: any) => (
                                    <tr key={h.cusip}>
                                        <td
                                            style={{
                                                padding: "9px 9px",
                                                fontSize: 13.5,
                                                borderTop: `1px solid ${C.line}`,
                                                fontWeight: h.ticker ? 650 : 500,
                                                color: h.ticker ? C.ink : C.faint,
                                            }}
                                        >
                                            {h.ticker || h.cusip}
                                        </td>
                                        <td
                                            style={{
                                                padding: "9px 9px",
                                                fontSize: 13.5,
                                                textAlign: "right",
                                                borderTop: `1px solid ${C.line}`,
                                            }}
                                        >
                                            {h.weight_pct == null
                                                ? "—"
                                                : h.weight_pct.toFixed(2) + "%"}
                                            <span
                                                style={{
                                                    display: "block",
                                                    height: 3,
                                                    width: 100,
                                                    marginLeft: "auto",
                                                    marginTop: 4,
                                                    borderRadius: 2,
                                                    background: C.sunken,
                                                    overflow: "hidden",
                                                }}
                                            >
                                                <span
                                                    style={{
                                                        display: "block",
                                                        height: "100%",
                                                        width: `${Math.min(100, (h.weight_pct || 0) * 3)}%`,
                                                        background: C.accent,
                                                    }}
                                                />
                                            </span>
                                        </td>
                                        <td
                                            style={{
                                                padding: "9px 9px",
                                                fontFamily: MONO,
                                                fontSize: 13.5,
                                                textAlign: "right",
                                                borderTop: `1px solid ${C.line}`,
                                            }}
                                        >
                                            {money(h.value_usd)}
                                        </td>
                                        <td
                                            style={{
                                                padding: "9px 9px",
                                                fontFamily: MONO,
                                                fontSize: 13.5,
                                                textAlign: "right",
                                                borderTop: `1px solid ${C.line}`,
                                            }}
                                        >
                                            {Math.round(h.shares || 0).toLocaleString()}
                                        </td>
                                        <td
                                            style={{
                                                padding: "9px 9px",
                                                textAlign: "right",
                                                borderTop: `1px solid ${C.line}`,
                                            }}
                                        >
                                            <span
                                                style={{
                                                    display: "inline-block",
                                                    padding: "2.5px 9px",
                                                    borderRadius: 999,
                                                    fontSize: 11.5,
                                                    fontWeight: 650,
                                                    background: chipBg(h.change_type),
                                                    color: chipFg(h.change_type),
                                                }}
                                            >
                                                {KO_CHANGE[h.change_type] || h.change_type}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div style={{ marginTop: 10, fontSize: 12.5, color: C.faint }}>
                        평가액 상위 {Math.min(topN, (cur.top_holdings || []).length)}종목입니다.
                    </div>
                </div>
            </div>

            <div
                style={{
                    marginTop: 18,
                    fontSize: 12,
                    color: C.faint,
                    lineHeight: 1.65,
                }}
            >
                출처 — SEC EDGAR 13F-HR. 티커는 OpenFIGI로 CUSIP을 변환했으며 변환되지 않은
                항목은 CUSIP으로 표시합니다. 인물 소개 출처는 각 카드에 표기했습니다.
                운용사명 옆 인물은 대표 연관 인물이며 현재 운용 주체와 다를 수 있습니다.
            </div>
        </div>
    )
}

addPropertyControls(PublicInvestorPortfolios, {
    dark: {
        type: ControlType.Boolean,
        title: "Dark (canvas)",
        defaultValue: false,
    },
    dataUrl: {
        type: ControlType.String,
        title: "데이터 URL",
        defaultValue: BLOB + "/us_investor_portfolios.json",
    },
    macroUrl: {
        type: ControlType.String,
        title: "환율 URL",
        defaultValue: BLOB + "/macro_snapshot.json",
    },
    topN: {
        type: ControlType.Number,
        title: "표시 종목 수",
        defaultValue: 25,
        min: 3,
        max: 50,
        step: 1,
    },
})

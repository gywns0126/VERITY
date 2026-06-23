import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useMemo, useState } from "react"

/**
 * 골든구스 증권사 가이드 (공개) — broker-neutral 사실 비교.
 *
 * 데이터 = Blob broker_guide.json (api/collectors/broker_guide.py = Perplexity sonar-pro 월 1회 자동집계).
 *
 * RULE 6/7: 우리 의견·별점·추천 0. 노출은 사실 + 출처만. "자동집계 · 권유 아님 · as-of" 라벨 의무.
 * 노출 컬럼(2026-06-23 확장) = 국내수수료·해외수수료·ISA·신용대주·실시간뉴스·커뮤니티·앱 (전부 수집된 사실+출처).
 *   별점(app_rating)만 보류 유지 = 수집값 0/6 + 별점 자체가 RULE7 의견 영역. (PM 요청 "내용 풍부하게" → 사실 컬럼만 추가)
 * 로고 = 증권사 공식 도메인 Clearbit + 구글 파비콘 fallback (상장/비상장 무관 안정).
 * 다크모드: body[data-framer-theme] 추종. 캔버스=dark prop 정적.
 */

const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"

interface Props {
    dark: boolean
    dataUrl: string
    height: number
    typeCardHeight: number
    tableCardHeight: number
}

const LIGHT = {
    bg: "#ffffff",
    card: "#f9fafb",
    sub: "#f2f4f6",
    text: "#191f28",
    subtext: "#6b7280",
    faint: "#8b95a1",
    border: "#e5e8eb",
    accent: "#15c47e",
    chipBg: "#f2f4f6",
    good: "#0ca678",
    goodBg: "#e7f7f0",
}
const DARK = {
    bg: "#171c23",
    card: "#1e242c",
    sub: "#222933",
    text: "#f2f4f6",
    subtext: "#9aa4b1",
    faint: "#6b7682",
    border: "#2b3138",
    accent: "#15c47e",
    chipBg: "#222933",
    good: "#34e08a",
    goodBg: "#16302a",
}

// 증권사명 substring → 공식 도메인 (로고용). 데이터 명칭 변형 대비 substring 매칭.
const BROKER_DOMAINS: [string, string][] = [
    ["한국투자", "truefriend.com"],
    ["한투", "truefriend.com"],
    ["토스", "tossinvest.com"],
    ["키움", "kiwoom.com"],
    ["미래에셋", "miraeasset.com"],
    ["삼성", "samsung.com"],
    ["NH", "nonghyup.com"],
    ["농협", "nonghyup.com"],
]
function brokerDomain(name: string): string {
    const n = name || ""
    for (let i = 0; i < BROKER_DOMAINS.length; i++) {
        if (n.indexOf(BROKER_DOMAINS[i][0]) >= 0) return BROKER_DOMAINS[i][1]
    }
    return ""
}

// 직접 로고 URL override — Clearbit 저화질/오로고 사인 곳만. 삼성·NH = 상장사라 토스 종목아이콘(증권사 로고)이 고해상도.
const TOSS_SEC = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
const BROKER_LOGO_OVERRIDE: [string, string][] = [
    ["삼성", TOSS_SEC + "016360.png"], // 삼성증권 016360
    ["NH", TOSS_SEC + "005940.png"], // NH투자증권 005940
    ["농협", TOSS_SEC + "005940.png"],
]
function brokerLogoOverride(name: string): string {
    const n = name || ""
    for (let i = 0; i < BROKER_LOGO_OVERRIDE.length; i++) {
        if (n.indexOf(BROKER_LOGO_OVERRIDE[i][0]) >= 0) return BROKER_LOGO_OVERRIDE[i][1]
    }
    return ""
}
function splitBrokers(best: string): string[] {
    return String(best || "")
        .split(/[/,·、]| 및 | 또는 /)
        .map((s) => s.trim())
        .filter(Boolean)
}

interface Broker {
    name: string
    app: string
    domestic_fee: string
    overseas_fee: string
    isa: string
    credit_short: string
    app_rating: string
    community: string
    realtime_news: string
    source_url: string
}
interface TradeType {
    type: string
    best: string
    reason: string
}
interface Guide {
    as_of: string
    source: string
    disclaimer: string
    brokers: Broker[]
    by_trade_type: TradeType[]
    citations: string[]
}

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

function asArray(x: any): any[] {
    return Array.isArray(x) ? x : []
}

function dateOnly(t: string): string {
    if (!t) return ""
    const m = String(t).match(/\d{4}-\d{2}-\d{2}/)
    return m ? m[0] : ""
}

// 인용 마커 [1][2] 제거 + 공백 정리 (Perplexity citation 흔적). 사실 텍스트만 노출.
function clean(s: any): string {
    return String(s || "").replace(/\[\d+\]/g, "").replace(/\s+/g, " ").trim()
}
// 사실상 "값 없음"인지 (— 로 표시할지)
function isEmptyVal(s: string): boolean {
    const v = clean(s)
    return !v || /^(없음|미제공|정보 ?없음|n\/?a|해당없음|불명)$/i.test(v)
}
// 해외수수료 요점만 — 첫 %(range 포함) + "미국" + 이벤트무료 플래그. 전문은 title(hover)/출처.
function briefOverseas(s: any): string {
    const v = clean(s)
    if (!v) return ""
    const pct = v.match(/\d+(?:\.\d+)?(?:\s*~\s*\d+(?:\.\d+)?)?\s*%/)
    const us = /미국|미장|US\b|달러/.test(v)
    const free = /이벤트/.test(v) && /무료/.test(v)
    if (pct) {
        let out = (us ? "미국 " : "") + pct[0].replace(/\s+/g, "")
        if (free) out += " · 이벤트 무료"
        return out
    }
    if (/무료/.test(v)) return us ? "미국 무료" : "무료"
    const head = v.split(/[/·]/)[0].trim()
    return head.length > 20 ? head.slice(0, 20) + "…" : head
}

const DEMO: Guide = {
    as_of: "2026-06-22T00:00:00+09:00",
    source: "perplexity sonar-pro (자동집계) · 예시",
    disclaimer: "Perplexity 자동집계 · 수수료는 수시 변동 · 사실 비교일 뿐 권유 아님 · 거래 전 각 사 공식 고지 확인",
    by_trade_type: [
        { type: "소형주(코스닥) 단기", best: "미래에셋증권, 삼성증권, NH투자증권", reason: "비대면 국내주식 온라인 위탁수수료가 0.0036%로 최저 구간." },
        { type: "미국주식 소액", best: "토스증권", reason: "최소수수료 부담이 적고 이벤트 시 무료가 확인됨." },
        { type: "ISA 장기", best: "한국투자증권, 키움증권, 미래에셋증권", reason: "ISA 지원 + 운용 상품군." },
        { type: "단타/고빈도", best: "미래에셋증권, 삼성증권", reason: "비대면 수수료 0.0036% + 반복매매 비용 부담 적음." },
        { type: "중장기/배당", best: "한국투자증권, NH투자증권", reason: "리서치·정보 제공 + 비대면 우대." },
    ],
    brokers: [
        { name: "한국투자증권", app: "한국투자 m.Stock · 뱅키스", domestic_fee: "0.0140%", overseas_fee: "미국 0.25% (기본 온라인) · 환전우대 자료 부족", isa: "지원", credit_short: "신용·대주 지원", app_rating: "", community: "없음", realtime_news: "실시간시세·속보 제공", source_url: "" },
        { name: "토스증권", app: "토스", domestic_fee: "이벤트 시 무료", overseas_fee: "미국 0.1% · 이벤트 시 무료", isa: "미지원", credit_short: "일부", app_rating: "", community: "토스 피드", realtime_news: "실시간시세 제공", source_url: "" },
        { name: "키움증권", app: "영웅문S#", domestic_fee: "0.015%", overseas_fee: "미국 0.07%", isa: "지원", credit_short: "신용·대주 지원", app_rating: "", community: "종목토론", realtime_news: "실시간시세·속보 제공", source_url: "" },
        { name: "미래에셋증권", app: "M-STOCK", domestic_fee: "0.0036%", overseas_fee: "미국 0.07~0.25%", isa: "지원", credit_short: "신용·대주 지원", app_rating: "", community: "없음", realtime_news: "리서치·속보 제공", source_url: "" },
        { name: "삼성증권", app: "mPOP", domestic_fee: "0.0036%", overseas_fee: "미국 0.25%", isa: "지원", credit_short: "신용·대주 지원", app_rating: "", community: "없음", realtime_news: "리서치·속보 제공", source_url: "" },
        { name: "NH투자증권", app: "나무증권 · QV", domestic_fee: "0.0036%", overseas_fee: "미국 0.25%", isa: "지원", credit_short: "신용·대주 지원", app_rating: "", community: "없음", realtime_news: "리서치·속보 제공", source_url: "" },
    ],
    citations: [],
}

/* 증권사 로고 — Clearbit 우선, 실패 시 구글 파비콘, 그래도 없으면 이니셜 원. */
function BrokerLogo(props: { name: string; size: number; C: typeof LIGHT }) {
    const { name, size, C } = props
    const override = brokerLogoOverride(name)
    const dom = brokerDomain(name)
    const initial = (name || "?").slice(0, 1)
    const primary = override || (dom ? "https://logo.clearbit.com/" + dom + "?size=128" : "")
    if (!primary) {
        return (
            <span
                style={{
                    width: size,
                    height: size,
                    borderRadius: 7,
                    background: C.chipBg,
                    color: C.subtext,
                    fontSize: Math.round(size * 0.46),
                    fontWeight: 800,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                }}
            >
                {initial}
            </span>
        )
    }
    return (
        <img
            src={primary}
            alt=""
            width={size}
            height={size}
            loading="lazy"
            onError={(e) => {
                const img = e.currentTarget as HTMLImageElement
                // 1차 실패 → 도메인 파비콘, 그 다음 실패 → 숨김
                if (img.dataset.fb === "1" || !dom) {
                    img.style.visibility = "hidden"
                    return
                }
                img.dataset.fb = "1"
                img.src = "https://www.google.com/s2/favicons?domain=" + dom + "&sz=128"
            }}
            style={{
                width: size,
                height: size,
                borderRadius: 7,
                objectFit: "contain",
                background: "#ffffff",
                flexShrink: 0,
            }}
        />
    )
}

function Chip(props: { label: string; value: string; C: typeof LIGHT }) {
    const { label, C } = props
    const v = clean(props.value)
    const pos = /지원|있음|가능|포함|제공/.test(v) && !/미지원|불가|없음|불가능|미제공/.test(v)
    return (
        <span
            style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
                background: pos ? C.goodBg : C.chipBg,
                borderRadius: 8,
                padding: "4px 9px",
            }}
        >
            <span style={{ fontSize: 11, fontWeight: 600, color: C.faint }}>{label}</span>
            <span style={{ fontSize: 11.5, fontWeight: 700, color: pos ? C.good : C.subtext }}>{v || "—"}</span>
        </span>
    )
}

/* 라벨 + 사실 텍스트 한 줄 (실시간뉴스·커뮤니티·앱 등 문장형 사실). 2줄 클램프. */
function InfoLine(props: { label: string; value: string; C: typeof LIGHT }) {
    const { label, value, C } = props
    return (
        <div style={{ display: "flex", gap: 8, fontSize: 11.5, lineHeight: 1.45, alignItems: "baseline" }}>
            <span style={{ flexShrink: 0, color: C.faint, fontWeight: 700, width: 60 }}>{label}</span>
            <span
                style={{
                    color: C.subtext,
                    fontWeight: 500,
                    overflowWrap: "anywhere",
                    display: "-webkit-box",
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                }}
            >
                {value}
            </span>
        </div>
    )
}

/* 토스식 shimmer 스켈레톤 — 증권사 비교 카드 레이아웃(로고+이름 막대 + 수치 막대 몇 개) 모사. */
function LoadingSkeleton(props: { C: typeof LIGHT; isDark: boolean }) {
    const { C, isDark } = props
    const base = isDark ? "#222a33" : "#e9edf1"
    const hi = isDark ? "#2d3742" : "#f3f5f7"
    const shimmer: React.CSSProperties = {
        background: base,
        backgroundImage: "linear-gradient(90deg, " + base + " 25%, " + hi + " 37%, " + base + " 63%)",
        backgroundSize: "800px 100%",
        animation: "vsrShimmer 1.4s ease-in-out infinite",
        borderRadius: 6,
    }
    const bar = (w: number | string, h: number, mt?: number): React.CSSProperties => ({
        ...shimmer,
        width: w,
        height: h,
        marginTop: mt || 0,
    })
    const rows = [0, 1, 2, 3, 4, 5]
    return (
        <div>
            <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12, alignItems: "start", paddingTop: 6 }}>
                {rows.map((i) => (
                    <div
                        key={i}
                        style={{
                            height: 210,
                            background: C.card,
                            borderRadius: 16,
                            padding: "16px 17px",
                            boxSizing: "border-box",
                        }}
                    >
                        {/* 헤더: 로고 + 증권사명 막대 */}
                        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 14 }}>
                            <div style={{ ...shimmer, width: 26, height: 26, borderRadius: 7 }} />
                            <div style={bar(110, 15)} />
                        </div>
                        {/* 수수료 2단 */}
                        <div style={{ display: "flex", gap: 14 }}>
                            <div style={{ flex: 1 }}><div style={bar(60, 11)} /><div style={bar("80%", 17, 6)} /></div>
                            <div style={{ flex: 1 }}><div style={bar(60, 11)} /><div style={bar("90%", 17, 6)} /></div>
                        </div>
                        {/* 칩 막대 2개 */}
                        <div style={{ display: "flex", gap: 6, marginTop: 14 }}>
                            <div style={{ ...shimmer, width: 72, height: 24, borderRadius: 8 }} />
                            <div style={{ ...shimmer, width: 92, height: 24, borderRadius: 8 }} />
                        </div>
                        <div style={bar("100%", 11, 14)} />
                        <div style={bar("70%", 11, 7)} />
                    </div>
                ))}
            </div>
        </div>
    )
}

export default function PublicBrokerGuide(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const [tab, setTab] = useState<"type" | "table">("type")
    const [guide, setGuide] = useState<Guide | null>(onCanvas ? DEMO : null)
    const [loading, setLoading] = useState<boolean>(!onCanvas)

    /* 테마 추종 */
    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    /* 데이터 로드 */
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const url = props.dataUrl || BLOB + "/broker_guide.json"
        fetch(url)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                setGuide(d && Array.isArray(d.brokers) ? d : null)
                setLoading(false)
            })
            .catch(() => {
                if (alive) setLoading(false)
            })
        return () => {
            alive = false
        }
    }, [onCanvas, props.dataUrl])

    const wrap: React.CSSProperties = {
        width: "100%",
        maxWidth: 1180,
        marginLeft: "auto",
        marginRight: "auto",
        height: props.height || 720,
        background: C.bg,
        borderRadius: 20,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        fontFamily:
            "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif",
        boxSizing: "border-box",
    }

    const tabs: { key: "type" | "table"; label: string }[] = [
        { key: "type", label: "거래유형별" },
        { key: "table", label: "증권사 비교" },
    ]

    return (
        <div style={wrap}>
            <div style={{ padding: "20px 22px 12px 22px" }}>
                <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                    <span style={{ fontSize: 19, fontWeight: 800, color: C.text, letterSpacing: "-0.02em" }}>
                        증권사 가이드
                    </span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>거래유형별 · 사실 비교</span>
                    {guide && guide.as_of ? (
                        <span style={{ fontSize: 11, fontWeight: 600, color: C.faint, marginLeft: "auto" }}>
                            기준 {dateOnly(guide.as_of)}
                        </span>
                    ) : null}
                </div>
                <div
                    style={{
                        marginTop: 14,
                        display: "inline-flex",
                        background: C.sub,
                        borderRadius: 10,
                        padding: 3,
                        gap: 2,
                    }}
                >
                    {tabs.map((t) => {
                        const active = tab === t.key
                        return (
                            <button
                                key={t.key}
                                type="button"
                                onClick={() => setTab(t.key)}
                                style={{
                                    border: "none",
                                    cursor: "pointer",
                                    background: active ? C.bg : "transparent",
                                    color: active ? C.text : C.subtext,
                                    fontWeight: active ? 700 : 600,
                                    fontSize: 13,
                                    padding: "7px 14px",
                                    borderRadius: 8,
                                    boxShadow: active ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
                                    transition: "all 140ms ease",
                                }}
                            >
                                {t.label}
                            </button>
                        )
                    })}
                </div>
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "4px 16px 18px 16px" }}>
                {loading ? (
                    <LoadingSkeleton C={C} isDark={isDark} />
                ) : !guide ? (
                    <div style={{ padding: 40, textAlign: "center", color: C.faint, fontSize: 14, lineHeight: 1.6 }}>
                        가이드 데이터 준비 중이에요.
                        <br />
                        (월 1회 자동집계 — 첫 수집 후 표시)
                    </div>
                ) : tab === "type" ? (
                    <TradeTypeView items={asArray(guide.by_trade_type)} C={C} cardH={props.typeCardHeight || 158} />
                ) : (
                    <BrokerTable brokers={asArray(guide.brokers)} C={C} cardH={props.tableCardHeight || 250} />
                )}
            </div>

            {guide ? (
                <div style={{ padding: "10px 18px 18px 18px", borderTop: "1px solid " + C.border }}>
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>
                        {guide.disclaimer || "사실 비교일 뿐 권유 아님"}
                    </div>
                    {asArray(guide.citations).length ? (
                        <div style={{ marginTop: 5, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                            <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 700 }}>출처</span>
                            {asArray(guide.citations).slice(0, 6).map((u, i) => (
                                <a
                                    key={i}
                                    href={String(u)}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ fontSize: 10.5, color: C.accent, fontWeight: 600, textDecoration: "none" }}
                                >
                                    [{i + 1}]
                                </a>
                            ))}
                        </div>
                    ) : null}
                </div>
            ) : null}
        </div>
    )
}

function BrokerPills(props: { best: string; C: typeof LIGHT }) {
    const { best, C } = props
    const names = splitBrokers(best)
    if (!names.length) {
        return <span style={{ fontSize: 15, fontWeight: 800, color: C.good }}>{best || "—"}</span>
    }
    return (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {names.map((bn, i) => (
                <span
                    key={i}
                    style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        background: C.sub,
                        borderRadius: 9,
                        padding: "4px 10px 4px 4px",
                    }}
                >
                    <BrokerLogo name={bn} size={20} C={C} />
                    <span style={{ fontSize: 12.5, fontWeight: 700, color: C.text }}>{bn}</span>
                </span>
            ))}
        </div>
    )
}

function TradeTypeView(props: { items: TradeType[]; C: typeof LIGHT; cardH: number }) {
    const { items, C, cardH } = props
    if (!items.length) {
        return <div style={{ padding: 40, textAlign: "center", color: C.faint, fontSize: 14 }}>거래유형 데이터가 없어요.</div>
    }
    return (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 10, alignItems: "start", paddingTop: 6 }}>
            {items.map((it, i) => (
                <div
                    key={i}
                    style={{
                        height: cardH,
                        overflow: "hidden",
                        background: C.card,
                        borderRadius: 16,
                        padding: "15px 16px",
                        boxSizing: "border-box",
                    }}
                >
                    <div style={{ fontSize: 13.5, fontWeight: 800, color: C.text, letterSpacing: "-0.01em", marginBottom: 9 }}>{it.type}</div>
                    <BrokerPills best={it.best} C={C} />
                    <div
                        style={{
                            marginTop: 10,
                            fontSize: 12.5,
                            color: C.subtext,
                            fontWeight: 500,
                            lineHeight: 1.55,
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                        }}
                    >
                        {it.reason || ""}
                    </div>
                </div>
            ))}
        </div>
    )
}

function BrokerTable(props: { brokers: Broker[]; C: typeof LIGHT; cardH: number }) {
    const { brokers, C, cardH } = props
    if (!brokers.length) {
        return <div style={{ padding: 40, textAlign: "center", color: C.faint, fontSize: 14 }}>증권사 데이터가 없어요.</div>
    }
    return (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12, alignItems: "start", paddingTop: 6 }}>
            {brokers.map((b, i) => {
                const overseas = clean(b.overseas_fee)
                const overseasBrief = briefOverseas(b.overseas_fee)
                const news = clean(b.realtime_news)
                const comm = clean(b.community)
                const app = clean(b.app)
                return (
                    <div
                        key={i}
                        style={{
                            minHeight: cardH,
                            background: C.card,
                            borderRadius: 16,
                            padding: "16px 17px",
                            boxSizing: "border-box",
                        }}
                    >
                        {/* 헤더: 로고 + 이름 */}
                        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 13 }}>
                            <BrokerLogo name={b.name} size={26} C={C} />
                            <span style={{ fontSize: 15, fontWeight: 700, color: C.text, letterSpacing: "-0.01em" }}>{b.name}</span>
                        </div>

                        {/* 수수료 2단 (국내 / 해외 요점) — 해외 전문은 hover(title)/출처 */}
                        <div style={{ display: "flex", gap: 16, marginBottom: 13 }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 11, fontWeight: 600, color: C.faint, marginBottom: 3 }}>국내주식</div>
                                <div style={{ fontSize: 16.5, fontWeight: 700, color: C.text, letterSpacing: "-0.01em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                    {clean(b.domestic_fee) || "—"}
                                </div>
                            </div>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 11, fontWeight: 600, color: C.faint, marginBottom: 3 }}>해외주식</div>
                                <div title={overseas || ""} style={{ fontSize: 15, fontWeight: 700, color: overseasBrief ? C.text : C.faint, letterSpacing: "-0.01em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                    {overseasBrief || "—"}
                                </div>
                            </div>
                        </div>

                        {/* 칩 = ISA / 신용·대주 */}
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 11 }}>
                            <Chip label="ISA" value={b.isa} C={C} />
                            <Chip label="신용·대주" value={b.credit_short} C={C} />
                        </div>

                        {/* 사실 라인 = 실시간뉴스 / 커뮤니티 / 앱 */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            {news ? <InfoLine label="실시간뉴스" value={news} C={C} /> : null}
                            {comm && !isEmptyVal(comm) ? <InfoLine label="커뮤니티" value={comm} C={C} /> : null}
                            {app ? <InfoLine label="앱" value={app} C={C} /> : null}
                        </div>

                        {b.source_url ? (
                            <a
                                href={String(b.source_url)}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{ display: "inline-block", marginTop: 11, fontSize: 11, fontWeight: 600, color: C.accent, textDecoration: "none" }}
                            >
                                출처 ↗
                            </a>
                        ) : null}
                    </div>
                )
            })}
        </div>
    )
}

addPropertyControls(PublicBrokerGuide, {
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
    dataUrl: { type: ControlType.String, title: "데이터 JSON", defaultValue: BLOB + "/broker_guide.json" },
    height: { type: ControlType.Number, title: "높이", defaultValue: 720, min: 320, max: 1600, step: 20, unit: "px" },
    typeCardHeight: { type: ControlType.Number, title: "거래유형 카드 높이", defaultValue: 158, min: 110, max: 320, step: 4, unit: "px" },
    tableCardHeight: { type: ControlType.Number, title: "증권사 카드 최소높이", defaultValue: 250, min: 140, max: 400, step: 4, unit: "px" },
})

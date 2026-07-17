import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useMemo, useState } from "react"

/**
 * AlphaNest 증권사 가이드 (공개) — broker-neutral 사실 비교.
 *
 * 데이터 = Blob broker_guide.json (api/collectors/broker_guide.py = Perplexity sonar-pro 월 1회 자동집계 + sticky merge).
 *
 * RULE 6/7: 우리 의견·별점·추천 0. 노출은 사실 + 출처만. "자동집계 · 권유 아님 · as-of" 라벨 의무.
 * 🚨 수수료 = 숫자 assert 금지(자동/큐레이션 모두 진짜 보장 불가·등급/이벤트/온오프라인 상이) → 각 사 공식 고지 deep-link.
 *   신뢰 정성사실만 노출: ISA·신용대주·실시간뉴스·커뮤니티·앱·이벤트.
 * 🚨 이벤트 = 진행 중 사실(기간 포함) · 권유 아님. 시효성 → as-of + disclaimer.
 * 🚨 거래유형 best 공란 = "집계 중" 안내(빈 카드 깨짐 방지).
 * 로고 = 증권사 공식 도메인 Clearbit + 구글 파비콘 fallback. 다크모드: body[data-framer-theme] 추종.
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
    accent: "#6c5ce7",
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
    accent: "#a99bff",
    chipBg: "#222933",
    good: "#34e08a",
    goodBg: "#16302a",
}

// 증권사명 substring → 공식 도메인 (로고·수수료 링크 fallback). 데이터 명칭 변형 대비 substring 매칭.
const BROKER_DOMAINS: [string, string][] = [
    ["한국투자", "truefriend.com"],
    ["한투", "truefriend.com"],
    ["토스", "tossinvest.com"],
    ["키움", "kiwoom.com"],
    ["미래에셋", "miraeasset.com"],
    ["삼성", "samsungpop.com"],
    ["NH", "nhqv.com"],
    ["농협", "nhqv.com"],
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
    fx_fee: string
    isa: string
    credit_short: string
    app_rating: string
    community: string
    realtime_news: string
    event: string
    source_url: string
    // 수수료 tile 전용 검증 링크 (collector focused 추출 출처). 하이브리드 = 출처 있는 값만 tile 노출.
    domestic_source: string
    overseas_source: string
    fx_source: string
    // hover 상세 (조건/스프레드 등)
    fee_basis: string
    overseas_basis: string
    fx_basis: string
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
// 실제 http(s) URL 인지 — collector source 에 산문이 섞이는 경우가 있어 링크 렌더 전 가드.
function isUrl(s: any): boolean {
    return /^https?:\/\/\S+$/i.test(String(s || "").trim())
}
// 해외수수료 요점만 — 첫 %(range 포함). 전문은 title(hover).
function briefOverseas(s: any): string {
    const v = clean(s)
    if (!v) return ""
    const pct = v.match(/\d+(?:\.\d+)?(?:\s*~\s*\d+(?:\.\d+)?)?\s*%/)
    if (pct) return pct[0].replace(/\s+/g, "")
    if (/무료/.test(v)) return "무료"
    return ""
}
// 환전우대 요점만 — 첫 %(우대율)만. 라벨이 "환전"이라 값은 % 만.
function briefFx(s: any): string {
    const v = clean(s)
    if (!v) return ""
    const pct = v.match(/\d+(?:\.\d+)?\s*%/)
    if (pct) return pct[0].replace(/\s+/g, "")
    if (/무료/.test(v)) return "무료"
    return ""
}
// 국내수수료 요점만 — 첫 %(복합 "KRX 0.015%, NXT 0.014%" 등 대비). 전문은 hover. 무료 이벤트 대응.
function briefDomestic(s: any): string {
    const v = clean(s)
    if (!v) return ""
    const pct = v.match(/\d+(?:\.\d+)?\s*%/)
    if (pct) return pct[0].replace(/\s+/g, "")
    if (/무료/.test(v)) return "무료"
    return v
}

const DEMO: Guide = {
    as_of: "2026-06-22T00:00:00+09:00",
    source: "perplexity sonar-pro (자동집계) · 예시",
    disclaimer: "Perplexity 자동집계 · 수수료·이벤트는 수시 변동 · 사실 비교일 뿐 권유 아님 · 거래 전 각 사 공식 고지 확인",
    by_trade_type: [
        { type: "소형주(코스닥) 단기", best: "미래에셋증권, 삼성증권, NH투자증권", reason: "비대면 국내주식 온라인 위탁수수료가 최저 구간(공식 고지 기준)." },
        { type: "미국주식 소액", best: "토스증권", reason: "최소수수료 부담이 적고 이벤트 시 무료가 확인됨." },
        { type: "ISA 장기", best: "한국투자증권, 키움증권, 미래에셋증권", reason: "ISA 지원 + 운용 상품군." },
        { type: "단타/고빈도", best: "미래에셋증권, 삼성증권", reason: "비대면 온라인 수수료 최저 구간 + 반복매매 비용 부담 적음." },
        { type: "중장기/배당", best: "한국투자증권, NH투자증권", reason: "리서치·정보 제공 + 비대면 우대." },
    ],
    brokers: [
        { name: "한국투자증권", app: "한국투자 m.Stock · 뱅키스", domestic_fee: "0.0140%", overseas_fee: "0.25%", fx_fee: "", isa: "지원", credit_short: "신용·대주 지원", app_rating: "", community: "없음", realtime_news: "실시간시세·속보 제공", event: "", source_url: "https://securities.koreainvestment.com", domestic_source: "https://securities.koreainvestment.com", overseas_source: "https://securities.koreainvestment.com", fx_source: "", fee_basis: "온라인 위탁수수료", overseas_basis: "온라인 미국주식 0.25%", fx_basis: "" },
        { name: "토스증권", app: "토스", domestic_fee: "0.015%", overseas_fee: "0.1%", fx_fee: "", isa: "미지원", credit_short: "일부", app_rating: "", community: "토스 피드", realtime_news: "실시간시세 제공", event: "미국주식 수수료 무료 이벤트 (~2026-07-31)", source_url: "https://tossinvest.com", domestic_source: "https://tossinvest.com", overseas_source: "", fx_source: "https://tossinvest.com", fee_basis: "온라인 위탁수수료", overseas_basis: "미국주식 0.1%", fx_basis: "매매기준율 대비 편도 1% · 온라인 우대 95%" },
        { name: "키움증권", app: "영웅문S#", domestic_fee: "0.015%", overseas_fee: "0.07%", fx_fee: "95%", isa: "지원", credit_short: "신용·대주 지원", app_rating: "", community: "종목토론", realtime_news: "실시간시세·속보 제공", event: "신규 개설 시 해외주식 환전우대 (~2026-08-15)", source_url: "https://www.kiwoom.com", domestic_source: "https://www.kiwoom.com", overseas_source: "https://www.kiwoom.com", fx_source: "https://www.kiwoom.com", fee_basis: "온라인 위탁수수료", overseas_basis: "미국주식 0.07% (이벤트)", fx_basis: "온라인 환전우대 95%" },
        { name: "미래에셋증권", app: "M-STOCK", domestic_fee: "0.0140%", overseas_fee: "0.25%", fx_fee: "95%", isa: "지원", credit_short: "신용·대주 지원", app_rating: "", community: "없음", realtime_news: "리서치·속보 제공", event: "", source_url: "https://securities.miraeasset.com", domestic_source: "https://securities.miraeasset.com", overseas_source: "https://securities.miraeasset.com", fx_source: "", fee_basis: "온라인 위탁수수료", overseas_basis: "미국주식 0.25%", fx_basis: "온라인 환전우대 95%" },
        { name: "삼성증권", app: "mPOP", domestic_fee: "0.0147%", overseas_fee: "0.25%", fx_fee: "95%", isa: "지원", credit_short: "신용·대주 지원", app_rating: "", community: "없음", realtime_news: "리서치·속보 제공", event: "", source_url: "https://www.samsungpop.com", domestic_source: "https://www.samsungpop.com", overseas_source: "https://www.samsungpop.com", fx_source: "https://www.samsungpop.com", fee_basis: "온라인 위탁수수료", overseas_basis: "미국주식 0.25%", fx_basis: "온라인 환전우대 95%" },
        { name: "NH투자증권", app: "나무증권 · QV", domestic_fee: "0.015%", overseas_fee: "0.198%", fx_fee: "95%", isa: "지원", credit_short: "신용·대주 지원", app_rating: "", community: "없음", realtime_news: "리서치·속보 제공", event: "", source_url: "https://www.nhqv.com", domestic_source: "https://www.nhqv.com", overseas_source: "https://www.nhqv.com", fx_source: "", fee_basis: "온라인 위탁수수료", overseas_basis: "미국주식 0.198%", fx_basis: "온라인 환전우대 95%" },
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

/* 라벨 + 사실 텍스트 한 줄 (실시간뉴스·커뮤니티·앱 등 문장형 사실). 3줄 클램프. */
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

/* 토스식 shimmer 스켈레톤 */
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
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 300px), 1fr))", gap: 12, alignItems: "start", paddingTop: 6 }}>
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
                        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 14 }}>
                            <div style={{ ...shimmer, width: 26, height: 26, borderRadius: 7 }} />
                            <div style={bar(110, 15)} />
                        </div>
                        <div style={bar("100%", 40, 4)} />
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

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicBrokerGuide(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const [tab, setTab] = useState<"type" | "table">("type")
    const [guide, setGuide] = useState<Guide | null>(onCanvas ? DEMO : null)
    const [loading, setLoading] = useState<boolean>(!onCanvas)

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

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
                        {guide.disclaimer || "사실 비교일 뿐 권유 아님 · 수수료는 각 사 공식 고지 확인"}
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
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 340px), 1fr))", gap: 10, alignItems: "start", paddingTop: 6 }}>
            {items.map((it, i) => (
                <div
                    key={i}
                    style={{
                        minHeight: cardH,
                        background: C.card,
                        borderRadius: 16,
                        padding: "15px 16px",
                        boxSizing: "border-box",
                    }}
                >
                    <div style={{ fontSize: 13.5, fontWeight: 800, color: C.text, letterSpacing: "-0.01em", marginBottom: 9 }}>{it.type}</div>
                    {isEmptyVal(it.best) ? (
                        <div style={{ fontSize: 12, color: C.faint, fontWeight: 500, lineHeight: 1.55 }}>
                            공개 출처 기준 뚜렷한 우위 집계 중 — 각 사 공식 수수료 고지를 확인하세요.
                        </div>
                    ) : (
                        <>
                            <BrokerPills best={it.best} C={C} />
                            <div
                                style={{
                                    marginTop: 10,
                                    fontSize: 12.5,
                                    color: C.subtext,
                                    fontWeight: 500,
                                    lineHeight: 1.55,
                                    overflowWrap: "anywhere",
                                }}
                            >
                                {clean(it.reason)}
                            </div>
                        </>
                    )}
                </div>
            ))}
        </div>
    )
}

/* 대표 수수료 1칸 — 라벨 + 값(공식 출처 링크 ↗). 상세는 title(hover). 하이브리드 = 호출측에서 값+출처 있을 때만 렌더. */
function FeeTile(props: { label: string; value: string; url: string; basis?: string; C: typeof LIGHT }) {
    const { label, value, url, basis, C } = props
    const v = clean(value)
    const numStyle: React.CSSProperties = {
        fontSize: 14.5,
        fontWeight: 700,
        letterSpacing: "-0.01em",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
    }
    return (
        <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: C.faint, marginBottom: 3 }}>{label}</div>
            <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                title={(basis ? clean(basis) + " · " : "") + "공식 출처에서 확인 ↗"}
                style={{ ...numStyle, display: "flex", alignItems: "center", gap: 3, color: C.text, textDecoration: "none" }}
            >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{v}</span>
                <span style={{ fontSize: 10, color: C.accent, flexShrink: 0, fontWeight: 700 }}>↗</span>
            </a>
        </div>
    )
}

function BrokerTable(props: { brokers: Broker[]; C: typeof LIGHT; cardH: number }) {
    const { brokers, C, cardH } = props
    if (!brokers.length) {
        return <div style={{ padding: 40, textAlign: "center", color: C.faint, fontSize: 14 }}>증권사 데이터가 없어요.</div>
    }
    return (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))", gap: 12, alignItems: "start", paddingTop: 6 }}>
            {brokers.map((b, i) => {
                const feeUrl = clean(b.source_url) || (brokerDomain(b.name) ? "https://" + brokerDomain(b.name) : "")
                const news = clean(b.realtime_news)
                const comm = clean(b.community)
                const app = clean(b.app)
                // 대표 수수료 — 값이 있으면 항상 tile 노출. 링크 = 전용 출처 우선, 없으면 증권사 공식 페이지(feeUrl).
                const domSrc = isUrl(b.domestic_source) ? b.domestic_source : feeUrl
                const feeTiles: { label: string; value: string; url: string; basis: string }[] = []
                const domRaw = clean(b.domestic_fee)
                const domV = briefDomestic(b.domestic_fee)
                // 복합값(KRX/NXT 등)은 전문을 hover 로, 아니면 fee_basis
                if (domV) feeTiles.push({ label: "국내주식", value: domV, url: domSrc, basis: domRaw !== domV ? domRaw : b.fee_basis })
                const ovV = briefOverseas(b.overseas_fee)
                if (ovV) feeTiles.push({ label: "미국주식", value: ovV, url: isUrl(b.overseas_source) ? b.overseas_source : feeUrl, basis: b.overseas_basis })
                const fxV = briefFx(b.fx_fee)
                if (fxV) feeTiles.push({ label: "환전우대", value: fxV, url: isUrl(b.fx_source) ? b.fx_source : feeUrl, basis: b.fx_basis })
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

                        {/* 이벤트/할인 (진행 중 사실 · 기간 포함 · 권유 아님) */}
                        {!isEmptyVal(b.event) ? (
                            <div style={{ display: "flex", alignItems: "flex-start", gap: 6, background: C.goodBg, borderRadius: 9, padding: "7px 10px", marginBottom: 13 }}>
                                <span style={{ flexShrink: 0, fontSize: 10, fontWeight: 800, color: C.good, background: C.bg, borderRadius: 5, padding: "1px 6px", marginTop: 1 }}>이벤트</span>
                                <span style={{ fontSize: 11.5, fontWeight: 600, color: C.text, lineHeight: 1.45, overflowWrap: "anywhere" }}>{clean(b.event)}</span>
                            </div>
                        ) : null}

                        {/* 대표 수수료 — 하이브리드: 공식 출처 링크가 붙은 값만 tile(클릭 검증). 없으면 공식 고지 링크 fallback. */}
                        {/* 자동 숫자 단독 assert 금지(등급·이벤트·온오프라인 상이) → 반드시 출처 동반 값만 노출. */}
                        {feeTiles.length ? (
                            <div style={{ marginBottom: 11 }}>
                                <div style={{ display: "flex", gap: 12 }}>
                                    {feeTiles.map((t, ti) => (
                                        <FeeTile key={ti} label={t.label} value={t.value} url={t.url} basis={t.basis} C={C} />
                                    ))}
                                </div>
                                <div style={{ fontSize: 9.5, color: C.faint, fontWeight: 500, marginTop: 6 }}>
                                    온라인 위탁 기준 · 값 클릭 시 공식 출처
                                </div>
                            </div>
                        ) : feeUrl ? (
                            <a href={feeUrl} target="_blank" rel="noopener noreferrer"
                                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, background: C.sub, borderRadius: 10, padding: "10px 12px", marginBottom: 11, textDecoration: "none" }}>
                                <div>
                                    <div style={{ fontSize: 11, fontWeight: 600, color: C.faint, marginBottom: 2 }}>수수료</div>
                                    <div style={{ fontSize: 12.5, fontWeight: 700, color: C.text }}>공식 수수료 고지 확인</div>
                                </div>
                                <span style={{ fontSize: 13, fontWeight: 800, color: C.accent, flexShrink: 0 }}>→</span>
                            </a>
                        ) : (
                            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginBottom: 11, lineHeight: 1.45 }}>수수료는 각 사 공식 고지에서 확인하세요.</div>
                        )}

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

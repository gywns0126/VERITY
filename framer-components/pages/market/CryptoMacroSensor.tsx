import { addPropertyControls, ControlType } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * CryptoMacroSensor — 크립토 매크로 센서 (모던 심플 정정)
 *
 * 출처: CryptoMacroSensor.tsx (619줄) 통째 재작성.
 *
 * 5 지표 + 종합 온도계:
 *   - F&G (Fear & Greed) — CNN 코인 지수
 *   - 펀딩비 (Funding Rate) — 롱/숏 과열
 *   - 김치 프리미엄 (Kimchi Premium) — 업비트 vs 바이낸스
 *   - BTC-NQ 상관계수 (-1 ~ +1)
 *   - 스테이블코인 시총 (USDT + USDC)
 *
 * Layout: compact (1줄 chip) / full (5 카드 + 종합 온도계)
 *
 * 모던 심플 6원칙:
 *   1. No card-in-card — panel 1개 + 카드 grid
 *   2. Flat hierarchy — title + composite + 5 카드
 *   3. Mono numerics — 점수 / % / 시총
 *   4. Color discipline — danger/warn/caution/success/down 토큰
 *   5. Emoji 0 (◈ → 토큰 dot, ▲▼ → 텍스트)
 *   6. 자체 색 (#EF4444 / #F97316 / #EAB308 / #22C55E / #3B82F6 /
 *      #60A5FA / #B5FF19 / #fff / #000 / #888 / #eee 등) 모두 토큰
 *
 * feedback_no_hardcode_position 적용: inline 렌더링.
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    success: "0 0 6px rgba(34,197,94,0.30)",
    warn: "0 0 6px rgba(245,158,11,0.30)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_normal: 1.5,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMS START ◆
 * ────────────────────────────────────────────────────────────── */
interface Term { label: string; definition: string }
const TERMS: Record<string, Term> = {
    FNG_CRYPTO: {
        label: "Fear & Greed (Crypto)",
        definition: "코인 시장 sentiment 지수 (alternative.me). 0 극도공포 ~ 100 극도탐욕.",
    },
    FUNDING_RATE: {
        label: "Funding Rate (펀딩비)",
        definition: "코인 무기한 선물 펀딩비. 양수 = 롱 우세 (롱이 숏에 비용 지불), 음수 = 숏 우세. 0.1% 이상 = 과열.",
    },
    KIMCHI_PREMIUM: {
        label: "Kimchi Premium (김치 프리미엄)",
        definition: "업비트 KRW 가격 vs 바이낸스 USD 가격 차이. 양수 = 한국 비싸 (자본 통제 + 매수 강도), 음수 = 역프.",
    },
    BTC_NQ_CORR: {
        label: "BTC-NQ 상관계수",
        definition: "BTC와 나스닥(NDX)의 30일 상관계수. +0.7+ 강결합 (위험자산 동조), -0.3- 역상관 (디커플링).",
    },
    STABLE_MCAP: {
        label: "스테이블코인 시총",
        definition: "USDT + USDC 합계 시총 (B$). 증가 = 코인 시장 자본 유입, 감소 = 유출.",
    },
}
/* ◆ TERMS END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMTOOLTIP START ◆
 * ────────────────────────────────────────────────────────────── */
function TermTooltip({ termKey, children }: { termKey: string; children: React.ReactNode }) {
    const [show, setShow] = useState(false)
    const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
    const anchorRef = useRef<HTMLSpanElement>(null)
    const term = TERMS[termKey]
    if (!term) return <>{children}</>
    const TIP_W = 320, TIP_H = 160
    const handleEnter = () => {
        const el = anchorRef.current
        if (!el || typeof window === "undefined") { setShow(true); return }
        const rect = el.getBoundingClientRect()
        const vw = window.innerWidth, vh = window.innerHeight
        const margin = 8
        let left = rect.left
        if (left + TIP_W + margin > vw) left = Math.max(margin, rect.right - TIP_W)
        let top = rect.bottom + 6
        if (top + TIP_H + margin > vh) top = Math.max(margin, rect.top - TIP_H - 6)
        setPos({ top, left })
        setShow(true)
    }
    const handleLeave = () => { setShow(false); setPos(null) }
    return (
        <span
            ref={anchorRef}
            onMouseEnter={handleEnter} onMouseLeave={handleLeave}
            onFocus={handleEnter} onBlur={handleLeave}
            tabIndex={0}
            style={{
                position: "relative", display: "inline-block",
                borderBottom: `1px dotted ${C.textTertiary}`,
                cursor: "help", outline: "none",
            }}
        >
            {children}
            {show && pos && (
                <div style={{
                    position: "fixed", top: pos.top, left: pos.left,
                    width: TIP_W, zIndex: 100,
                    padding: "10px 12px", borderRadius: R.md,
                    background: C.bgElevated, border: `1px solid ${C.borderStrong}`,
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                    fontFamily: FONT, fontSize: 12, lineHeight: 1.5,
                    whiteSpace: "normal", pointerEvents: "none",
                }}>
                    <div style={{ color: C.textPrimary, fontWeight: T.w_bold, fontSize: 13, marginBottom: 4 }}>
                        {term.label}
                    </div>
                    <div style={{ color: C.textSecondary }}>{term.definition}</div>
                </div>
            )}
        </span>
    )
}
/* ◆ TERMTOOLTIP END ◆ */


/* ─────────── fetch ─────────── */
function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}
function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}


/* ─────────── 색 매핑 ─────────── */
function fngColor(value: number): string {
    if (value >= 75) return C.danger
    if (value >= 55) return C.caution
    if (value >= 45) return C.warn
    if (value >= 25) return C.success
    return C.down
}

function fundingColor(signal: string, ratePct: number): string {
    if (signal === "long_overheat") return C.danger
    if (signal === "short_overheat") return C.down
    if (ratePct >= 0) return C.caution
    return C.info
}

function kimchiColor(signal: string): string {
    if (signal === "overheated") return C.danger
    if (signal === "elevated") return C.caution
    if (signal === "discount") return C.down
    return C.success
}

function corrColor(correlation: number): string {
    if (correlation >= 0.7) return C.danger
    if (correlation >= 0.4) return C.caution
    if (correlation <= -0.3) return C.down
    return C.success
}

function thermoColor(score: number): string {
    if (score >= 75) return C.danger
    if (score >= 60) return C.caution
    if (score >= 40) return C.accent
    if (score >= 25) return C.success
    return C.down
}


/* ─────────── 미니 헬퍼 ─────────── */
function fmtPct(n: number | null | undefined, digits = 2): string {
    if (n == null || !Number.isFinite(n)) return "—"
    const sign = n > 0 ? "+" : ""
    return `${sign}${n.toFixed(digits)}%`
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

interface Props {
    dataUrl: string
    refreshIntervalSec: number
    layout: "compact" | "full"
}

export default function CryptoMacroSensor(props: Props) {
    const { dataUrl, refreshIntervalSec = 180, layout = "full" } = props
    const [data, setData] = useState<any>(null)
    const [fetchErr, setFetchErr] = useState<string | null>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        setFetchErr(null)
        fetchJson(dataUrl, ac.signal)
            .then((d) => { if (!ac.signal.aborted) setData(d) })
            .catch((e) => { if (!ac.signal.aborted) setFetchErr(e instanceof Error ? e.message : String(e)) })
        const sec = Math.max(30, refreshIntervalSec)
        const id = setInterval(() => {
            fetchJson(dataUrl).then((d) => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        }, sec * 1000)
        return () => { ac.abort(); clearInterval(id) }
    }, [dataUrl, refreshIntervalSec])

    if (!dataUrl) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>dataUrl 미설정</span>
                </div>
            </div>
        )
    }

    if (data === null && !fetchErr) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>portfolio.json 로딩 중…</span>
                </div>
            </div>
        )
    }

    if (fetchErr) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.danger, fontSize: T.body }}>JSON 로드 실패: {fetchErr}</span>
                </div>
            </div>
        )
    }

    const crypto = data?.crypto_macro
    if (!crypto || typeof crypto !== "object") {
        return (
            <div style={shell}>
                <div style={{ padding: S.lg, color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                    이 portfolio.json 에 <span style={{ color: C.accent }}>crypto_macro</span> 블록이 없습니다.
                    <br /><br />
                    GitHub Actions 로 <span style={{ color: C.textPrimary }}>main.py</span> 가 돌고 나온 최신
                    {" "}<span style={{ color: C.textPrimary }}>data/portfolio.json</span> 이 푸시됐는지 확인.
                </div>
            </div>
        )
    }

    const fng = crypto.fear_and_greed || {}
    const funding = crypto.funding_rate || {}
    const kimchi = crypto.kimchi_premium || {}
    const corr = crypto.btc_nasdaq_corr || {}
    const stable = crypto.stablecoin_mcap || {}
    const composite = crypto.composite || {}

    const hasAnyOk = !!(fng.ok || funding.ok || kimchi.ok || corr.ok || stable.ok)

    if (!hasAnyOk) {
        const hints = [
            fng.error && `F&G: ${fng.error}`,
            funding.error && `펀딩: ${funding.error}`,
            kimchi.error && `김프: ${kimchi.error}`,
            corr.error && `상관: ${corr.error}`,
            stable.error && `스테이블: ${stable.error}`,
        ].filter(Boolean) as string[]
        return (
            <div style={shell}>
                <div style={{ padding: S.lg, color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                    <div style={{ marginBottom: S.sm }}>
                        크립토 센서 5 소스 모두 실패. (백엔드 수집 시 일시 차단·타임아웃 가능)
                    </div>
                    {hints.slice(0, 3).map((h, i) => (
                        <div key={i} style={{ color: C.textTertiary, fontSize: T.cap, marginTop: S.xs }}>{h}</div>
                    ))}
                </div>
            </div>
        )
    }

    /* compact layout — 한 줄 chip */
    if (layout === "compact") {
        return (
            <div style={shell}>
                <div style={{ display: "flex", alignItems: "center", gap: S.lg, flexWrap: "wrap" }}>
                    <span style={{
                        color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_bold,
                        letterSpacing: "0.08em", textTransform: "uppercase",
                    }}>
                        Crypto Sensor
                    </span>
                    {fng.ok && <CompactChip label="F&G" value={String(fng.value)} color={fngColor(fng.value)} />}
                    {funding.ok && (
                        <CompactChip
                            label="펀딩"
                            value={`${funding.rate_pct >= 0 ? "+" : ""}${funding.rate_pct.toFixed(3)}%`}
                            color={fundingColor(funding.signal, funding.rate_pct)}
                        />
                    )}
                    {kimchi.ok && (
                        <CompactChip
                            label="김프"
                            value={`${kimchi.premium_pct >= 0 ? "+" : ""}${kimchi.premium_pct.toFixed(1)}%`}
                            color={kimchiColor(kimchi.signal)}
                        />
                    )}
                    {corr.ok && (
                        <CompactChip
                            label="BTC-NQ"
                            value={corr.correlation.toFixed(2)}
                            color={corrColor(corr.correlation)}
                        />
                    )}
                    {stable.ok && stable.total_mcap_b != null && (
                        <CompactChip
                            label="스테이블"
                            value={`$${stable.total_mcap_b.toFixed(0)}B`}
                            color={C.accent}
                        />
                    )}
                </div>
            </div>
        )
    }

    /* full layout — 컴팩트 단일 column row 패턴 (펜타그램 톤) */
    const fngLabelKo = fng.ok ? (
        fng.label === "Extreme Greed" ? "극단탐욕"
        : fng.label === "Greed" ? "탐욕"
        : fng.label === "Neutral" ? "중립"
        : fng.label === "Fear" ? "공포"
        : fng.label === "Extreme Fear" ? "극단공포"
        : fng.label
    ) : ""
    const fundingSig = funding.ok ? (
        funding.signal === "long_overheat" ? "롱 과열"
        : funding.signal === "short_overheat" ? "숏 과열"
        : "정상"
    ) : ""
    const kimchiSig = kimchi.ok ? (
        kimchi.signal === "overheated" ? "과열"
        : kimchi.signal === "elevated" ? "주의"
        : kimchi.signal === "discount" ? "역프"
        : "정상"
    ) : ""
    const corrSig = corr.ok ? (
        corr.signal === "strongly_coupled" ? "강결합"
        : corr.signal === "moderately_coupled" ? "연동"
        : corr.signal === "inversely_correlated" ? "역상관"
        : "독립"
    ) : ""

    return (
        <div style={shell}>
            {/* Header — 단순 한 줄 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", paddingBottom: S.sm, borderBottom: `1px solid ${C.border}` }}>
                <span style={{ fontSize: T.cap, color: C.textPrimary, fontWeight: T.w_bold, letterSpacing: 0.5, textTransform: "uppercase" }}>크립토 센서</span>
                <span style={{ ...MONO, fontSize: T.cap, color: C.textTertiary, letterSpacing: 0.3 }}>{crypto.ok_count}/{crypto.total} 활성</span>
            </div>

            {/* Composite — 라인 1: dot + label + bar + score + label, 라인 2: signals inline */}
            <CompositeThermo
                score={composite.score ?? 50}
                label={composite.label || "중립"}
                signals={composite.signals || []}
            />

            {/* 5 metric — row + mini viz (그림책 톤) */}
            {fng.ok && <MetricRow
                label={<TermTooltip termKey="FNG_CRYPTO">F &amp; G</TermTooltip>}
                value={String(fng.value)}
                signal={fngLabelKo}
                color={fngColor(fng.value)}
                viz={<FngArc value={fng.value} color={fngColor(fng.value)} />}
                delta={fng.change}
            />}
            {funding.ok && <MetricRow
                label={<TermTooltip termKey="FUNDING_RATE">펀딩비</TermTooltip>}
                value={`${funding.rate_pct >= 0 ? "+" : ""}${funding.rate_pct.toFixed(3)}%`}
                signal={fundingSig}
                color={fundingColor(funding.signal, funding.rate_pct)}
                viz={<BipolarBar fillPct={funding.rate_pct / 0.1 * 100} color={fundingColor(funding.signal, funding.rate_pct)} />}
            />}
            {kimchi.ok && <MetricRow
                label={<TermTooltip termKey="KIMCHI_PREMIUM">김프</TermTooltip>}
                value={`${kimchi.premium_pct >= 0 ? "+" : ""}${kimchi.premium_pct.toFixed(2)}%`}
                signal={kimchiSig}
                color={kimchiColor(kimchi.signal)}
                viz={<BipolarBar fillPct={kimchi.premium_pct / 5 * 100} color={kimchiColor(kimchi.signal)} />}
            />}
            {corr.ok && <MetricRow
                label={<TermTooltip termKey="BTC_NQ_CORR">BTC·NQ</TermTooltip>}
                value={`${corr.correlation >= 0 ? "+" : ""}${corr.correlation.toFixed(2)}`}
                signal={corrSig}
                color={corrColor(corr.correlation)}
                viz={<CorrSpectrum correlation={corr.correlation} color={corrColor(corr.correlation)} />}
            />}
            {stable.ok && stable.total_mcap_b != null && <MetricRow
                label={<TermTooltip termKey="STABLE_MCAP">스테이블</TermTooltip>}
                value={`$${stable.total_mcap_b.toFixed(0)}B`}
                signal={`USDT ${(stable.usdt_mcap_b / stable.total_mcap_b * 100).toFixed(0)}%`}
                color={C.accent}
                viz={<StableStack usdtPct={(stable.usdt_mcap_b / stable.total_mcap_b) * 100} color={C.success} />}
            />}
        </div>
    )
}


/* ─────────── 종합 온도계 — circle progress mini viz 부활 ─────────── */
function CompositeThermo({ score, label, signals }: { score: number; label: string; signals: string[] }) {
    const c = thermoColor(score)
    const C_R = 14
    const dash = 2 * Math.PI * C_R
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.xs, paddingBottom: S.sm, borderBottom: `1px solid ${C.border}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: S.md }}>
                {/* 32x32 circle progress (그림책: 한눈에 0-100) */}
                <div style={{ position: "relative", width: 32, height: 32, flexShrink: 0 }}>
                    <svg viewBox="0 0 32 32" width="32" height="32">
                        <circle cx="16" cy="16" r={C_R} fill="none" stroke={C.border} strokeWidth="2" />
                        <circle cx="16" cy="16" r={C_R} fill="none"
                            stroke={c} strokeWidth="2" strokeLinecap="round"
                            strokeDasharray={`${(score / 100) * dash} ${dash}`}
                            transform="rotate(-90 16 16)"
                            style={{ transition: "stroke-dasharray 200ms ease" }}
                        />
                    </svg>
                </div>
                <span style={{ flex: 1, fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med, letterSpacing: 0.5, textTransform: "uppercase" }}>
                    매크로 온도
                </span>
                <span style={{ ...MONO, color: c, fontSize: T.h2, fontWeight: T.w_bold, letterSpacing: -0.3, minWidth: 44, textAlign: "right" }}>{score}</span>
                <span style={{ color: c, fontSize: T.cap, fontWeight: T.w_bold, minWidth: 56, textAlign: "right", letterSpacing: 0.4 }}>{label}</span>
            </div>
            {signals.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: S.md, paddingLeft: 44 }}>
                    {signals.map((s, i) => (
                        <span key={i} style={{ color: C.textSecondary, fontSize: T.cap, letterSpacing: 0.3 }}>· {s}</span>
                    ))}
                </div>
            )}
        </div>
    )
}


/* ─────────── Mini Viz — 그림책 시각 자료 ─────────── */
function FngArc({ value, color }: { value: number; color: string }) {
    /* 60x32 반원 arc + needle. F&G 0-100 spectrum 에서 가장 아이콘적 */
    const angle = -90 + (value / 100) * 180
    return (
        <span style={{ width: 60, height: 32, flexShrink: 0, display: "block" }}>
            <svg viewBox="0 0 60 36" width="60" height="32">
                <path d="M 6 32 A 24 24 0 0 1 54 32" fill="none" stroke={C.border} strokeWidth="3" strokeLinecap="round" />
                <path d="M 6 32 A 24 24 0 0 1 54 32" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round"
                    strokeDasharray={`${(value / 100) * 75.4} 75.4`}
                    style={{ transition: "stroke-dasharray 200ms ease" }} />
                <line x1="30" y1="32" x2="30" y2="14" stroke={color} strokeWidth="1.5" strokeLinecap="round"
                    transform={`rotate(${angle}, 30, 32)`}
                    style={{ transition: "transform 200ms ease" }} />
                <circle cx="30" cy="32" r="2" fill={color} />
            </svg>
        </span>
    )
}

function StableStack({ usdtPct, color }: { usdtPct: number; color: string }) {
    /* 60x4 USDT/USDC 비율 stack */
    return (
        <span style={{ width: 60, height: 4, flexShrink: 0, display: "flex", overflow: "hidden" }}>
            <span style={{ width: `${usdtPct}%`, background: color, transition: "width 200ms ease" }} />
            <span style={{ width: `${100 - usdtPct}%`, background: C.info, transition: "width 200ms ease" }} />
        </span>
    )
}

function CorrSpectrum({ correlation, color }: { correlation: number; color: string }) {
    /* 60x4 -1 ~ +1 spectrum + indicator dot. gradient 보존 (그림책 톤) */
    const fillPct = ((correlation + 1) / 2) * 100
    return (
        <span style={{ width: 60, height: 4, flexShrink: 0, position: "relative" }}>
            <span style={{ position: "absolute", inset: 0, background: `linear-gradient(90deg, ${C.down}, ${C.success}, ${C.warn}, ${C.danger})`, opacity: 0.3 }} />
            <span style={{
                position: "absolute", left: `${fillPct}%`, top: -3, bottom: -3, width: 2,
                background: color, transform: "translateX(-50%)",
                transition: "left 200ms ease",
            }} />
        </span>
    )
}

function BipolarBar({ fillPct, color }: { fillPct: number; color: string }) {
    /* 60x4 좌우 분기 (펀딩비: long/short 과열) */
    return (
        <span style={{ width: 60, height: 4, flexShrink: 0, position: "relative", background: C.border }}>
            <span style={{ position: "absolute", left: "50%", top: -2, bottom: -2, width: 1, background: C.borderStrong }} />
            <span style={{
                position: "absolute", height: "100%", background: color, transition: "width 200ms ease",
                ...(fillPct >= 0
                    ? { left: "50%", width: `${Math.min(50, fillPct / 2)}%` }
                    : { right: "50%", width: `${Math.min(50, -fillPct / 2)}%` }),
            }} />
        </span>
    )
}

/* ─────────── 통합 MetricRow — viz prop 부활 (그림책 시각 자료) ─────────── */
function MetricRow({ label, value, signal, color, viz, delta }: {
    label: React.ReactNode
    value: string
    signal?: string
    color: string
    viz?: React.ReactNode
    delta?: number | null
}) {
    return (
        <div style={{ display: "flex", alignItems: "center", gap: S.md, padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: color, flexShrink: 0 }} />
            <span style={{ flex: 1, fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med, letterSpacing: 0.5, textTransform: "uppercase" }}>
                {label}
            </span>
            {viz}
            <span style={{ ...MONO, color, fontSize: T.body, fontWeight: T.w_bold, minWidth: 64, textAlign: "right", letterSpacing: 0.3 }}>
                {value}
            </span>
            {delta != null && (
                <span style={{ ...MONO, color: delta >= 0 ? C.danger : C.success, fontSize: T.cap, fontWeight: T.w_bold, minWidth: 32, textAlign: "right", letterSpacing: 0.3 }}>
                    {delta >= 0 ? "+" : ""}{delta}
                </span>
            )}
            {signal && (
                <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med, minWidth: 56, textAlign: "right", letterSpacing: 0.4 }}>
                    {signal}
                </span>
            )}
        </div>
    )
}


function CompactChip({ label, value, color }: { label: string; value: string; color: string }) {
    return (
        <div style={{ display: "flex", alignItems: "center", gap: S.xs }}>
            <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med }}>
                {label}
            </span>
            <span style={{ ...MONO, color, fontSize: T.cap, fontWeight: T.w_bold }}>
                {value}
            </span>
        </div>
    )
}


/* ─────────── 스타일 ─────────── */

const shell: CSSProperties = {
    width: "100%", boxSizing: "border-box",
    fontFamily: FONT, color: C.textPrimary,
    background: C.bgPage,
    border: `1px solid ${C.border}`,
    borderRadius: 16,
    padding: `${S.lg}px ${S.xl}px`,
    display: "flex", flexDirection: "column",
    gap: 0,
}

const loadingBox: CSSProperties = {
    minHeight: 200,
    display: "flex", alignItems: "center", justifyContent: "center",
    padding: S.lg,
}


/* ─────────── Framer Property Controls ─────────── */

CryptoMacroSensor.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    refreshIntervalSec: 180,
    layout: "full",
}

addPropertyControls(CryptoMacroSensor, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    },
    refreshIntervalSec: {
        type: ControlType.Number,
        title: "갱신 간격(초)",
        defaultValue: 180,
        min: 30, max: 3600, step: 30,
    },
    layout: {
        type: ControlType.Enum,
        title: "레이아웃",
        options: ["compact", "full"],
        optionTitles: ["컴팩트 (1줄 chip)", "전체 (5 카드 + 종합)"],
        defaultValue: "full",
    },
})

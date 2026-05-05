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

    /* full layout */
    return (
        <div style={shell}>
            {/* Header */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <span style={titleStyle}>크립토 센서</span>
                    <span style={metaStyle}>주식 분석 보조 지표 · {crypto.ok_count}/{crypto.total} 활성</span>
                </div>
            </div>

            {/* Composite thermometer */}
            <CompositeThermo
                score={composite.score ?? 50}
                label={composite.label || "중립"}
                signals={composite.signals || []}
            />

            <div style={hr} />

            {/* 5 metrics grid — row 별 활성 카드 수에 따라 1fr / 1fr 1fr 자동 분기 */}
            {(fng.ok || funding.ok) && (
                <div style={gridRowFor(fng.ok, funding.ok)}>
                    {fng.ok && <FearGreedGauge value={fng.value} label={fng.label} change={fng.change} />}
                    {funding.ok && <FundingRateBar ratePct={funding.rate_pct} signal={funding.signal} />}
                </div>
            )}

            {(kimchi.ok || corr.ok) && (
                <div style={gridRowFor(kimchi.ok, corr.ok)}>
                    {kimchi.ok && <KimchiPremiumBadge premiumPct={kimchi.premium_pct} signal={kimchi.signal} />}
                    {corr.ok && <CorrelationMeter correlation={corr.correlation} signal={corr.signal} />}
                </div>
            )}

            {stable.ok && (
                <StablecoinBar
                    totalB={stable.total_mcap_b}
                    usdtB={stable.usdt_mcap_b}
                    usdcB={stable.usdc_mcap_b}
                />
            )}
        </div>
    )
}


/* ─────────── 종합 온도계 ─────────── */
function CompositeThermo({ score, label, signals }: { score: number; label: string; signals: string[] }) {
    const c = thermoColor(score)
    return (
        <div style={{
            background: C.bgCard,
            border: `1px solid ${c}33`,
            borderRadius: R.md,
            padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: S.md }}>
                {/* 원형 progress */}
                <div style={{ position: "relative", width: 44, height: 44, flexShrink: 0 }}>
                    <svg viewBox="0 0 44 44" width="44" height="44">
                        <circle cx="22" cy="22" r="19" fill="none" stroke={C.bgElevated} strokeWidth="3" />
                        <circle
                            cx="22" cy="22" r="19" fill="none"
                            stroke={c} strokeWidth="3" strokeLinecap="round"
                            strokeDasharray={`${(score / 100) * 119.4} 119.4`}
                            transform="rotate(-90 22 22)"
                        />
                    </svg>
                    <span style={{
                        position: "absolute", top: "50%", left: "50%",
                        transform: "translate(-50%, -50%)",
                        ...MONO,
                        color: c, fontSize: T.cap, fontWeight: T.w_black,
                    }}>{score}</span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{
                        color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
                        letterSpacing: "0.05em", textTransform: "uppercase",
                    }}>
                        매크로 온도
                    </span>
                    <span style={{ color: c, fontSize: T.body, fontWeight: T.w_bold }}>
                        {label}
                    </span>
                </div>
            </div>
            {signals.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    {signals.map((s, i) => (
                        <span
                            key={i}
                            style={{
                                color: C.textSecondary,
                                fontSize: T.cap,
                                paddingLeft: S.sm,
                                borderLeft: `2px solid ${c}33`,
                            }}
                        >
                            {s}
                        </span>
                    ))}
                </div>
            )}
        </div>
    )
}


/* ─────────── F&G 게이지 ─────────── */
function FearGreedGauge({ value, label, change }: { value: number; label: string; change: number | null }) {
    const angle = -90 + (value / 100) * 180
    const c = fngColor(value)
    const labelKo = label === "Extreme Greed" ? "극단적 탐욕"
        : label === "Greed" ? "탐욕"
        : label === "Neutral" ? "중립"
        : label === "Fear" ? "공포"
        : label === "Extreme Fear" ? "극단적 공포"
        : label

    return (
        <div style={metricCard}>
            <div style={metricHead}>
                <span style={metricLabel}>
                    <TermTooltip termKey="FNG_CRYPTO">F &amp; G</TermTooltip>
                </span>
                {change != null && (
                    <span
                        style={{
                            ...MONO,
                            color: change >= 0 ? C.danger : C.success,
                            fontSize: T.cap, fontWeight: T.w_bold,
                        }}
                    >
                        {change >= 0 ? "+" : ""}{change}
                    </span>
                )}
            </div>
            <div style={{ display: "flex", justifyContent: "center", padding: `${S.xs}px 0` }}>
                <svg viewBox="0 0 120 70" width="120" height="70">
                    <defs>
                        <linearGradient id="fng-arc" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0%" stopColor={C.down} />
                            <stop offset="25%" stopColor={C.success} />
                            <stop offset="50%" stopColor={C.warn} />
                            <stop offset="75%" stopColor={C.caution} />
                            <stop offset="100%" stopColor={C.danger} />
                        </linearGradient>
                    </defs>
                    <path d="M 10 65 A 50 50 0 0 1 110 65" fill="none" stroke={C.bgElevated} strokeWidth="8" strokeLinecap="round" />
                    <path
                        d="M 10 65 A 50 50 0 0 1 110 65"
                        fill="none" stroke="url(#fng-arc)" strokeWidth="8" strokeLinecap="round"
                        strokeDasharray={`${(value / 100) * 157} 157`}
                    />
                    <line
                        x1="60" y1="65" x2="60" y2="22"
                        stroke={c} strokeWidth="2" strokeLinecap="round"
                        transform={`rotate(${angle}, 60, 65)`}
                    />
                    <circle cx="60" cy="65" r="4" fill={c} />
                </svg>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: S.xs, justifyContent: "center" }}>
                <span style={{ ...MONO, color: c, fontSize: T.h2, fontWeight: T.w_black }}>{value}</span>
                <span style={{ color: C.textSecondary, fontSize: T.cap, fontWeight: T.w_semi }}>{labelKo}</span>
            </div>
        </div>
    )
}


/* ─────────── 펀딩비 바 ─────────── */
function FundingRateBar({ ratePct, signal }: { ratePct: number; signal: string }) {
    const isLong = ratePct >= 0
    const absWidth = Math.min(Math.abs(ratePct) / 0.1 * 100, 100)
    const c = fundingColor(signal, ratePct)
    const signalLabel = signal === "long_overheat" ? "롱 과열"
        : signal === "short_overheat" ? "숏 과열"
        : "정상"

    return (
        <div style={metricCard}>
            <div style={metricHead}>
                <span style={metricLabel}>
                    <TermTooltip termKey="FUNDING_RATE">펀딩비</TermTooltip>
                </span>
                <SignalBadge label={signalLabel} color={c} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: S.sm, marginTop: S.xs }}>
                <div style={fundingBarBg}>
                    <div style={{
                        position: "absolute", left: "50%", top: 0, bottom: 0,
                        width: 1, background: C.borderStrong,
                    }} />
                    <div style={{
                        position: "absolute", top: 1, bottom: 1,
                        borderRadius: 3, background: c,
                        boxShadow: `0 0 8px ${c}60`,
                        ...(isLong
                            ? { left: "50%", width: `${absWidth / 2}%` }
                            : { right: "50%", width: `${absWidth / 2}%` }),
                    }} />
                </div>
                <span style={{
                    ...MONO, color: c, fontSize: T.body, fontWeight: T.w_bold,
                    minWidth: 64, textAlign: "right",
                }}>
                    {ratePct >= 0 ? "+" : ""}{ratePct.toFixed(4)}%
                </span>
            </div>
        </div>
    )
}


/* ─────────── 김치 프리미엄 ─────────── */
function KimchiPremiumBadge({ premiumPct, signal }: { premiumPct: number; signal: string }) {
    const c = kimchiColor(signal)
    const isFlashing = signal === "overheated"
    const signalLabel = signal === "overheated" ? "과열"
        : signal === "elevated" ? "주의"
        : signal === "discount" ? "역프"
        : "정상"

    return (
        <div
            style={{
                ...metricCard,
                borderColor: isFlashing ? `${c}66` : C.border,
            }}
        >
            <div style={metricHead}>
                <span style={metricLabel}>
                    <TermTooltip termKey="KIMCHI_PREMIUM">김치 프리미엄</TermTooltip>
                </span>
                <SignalBadge label={signalLabel} color={c} />
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: S.xs, marginTop: S.sm }}>
                <span
                    style={{
                        ...MONO,
                        color: c,
                        fontSize: T.h2,
                        fontWeight: T.w_black,
                        animation: isFlashing ? "cms-pulse 1.5s ease-in-out infinite" : undefined,
                    }}
                >
                    {premiumPct >= 0 ? "+" : ""}{premiumPct.toFixed(2)}%
                </span>
                <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                    업비트 vs 바이낸스
                </span>
            </div>
            <style>{`@keyframes cms-pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }`}</style>
        </div>
    )
}


/* ─────────── BTC-NQ 상관 ─────────── */
function CorrelationMeter({ correlation, signal }: { correlation: number; signal: string }) {
    const normalized = (correlation + 1) / 2
    const fillPct = normalized * 100
    const c = corrColor(correlation)
    const signalLabel = signal === "strongly_coupled" ? "강결합"
        : signal === "moderately_coupled" ? "연동"
        : signal === "inversely_correlated" ? "역상관"
        : "독립"

    return (
        <div style={metricCard}>
            <div style={metricHead}>
                <span style={metricLabel}>
                    <TermTooltip termKey="BTC_NQ_CORR">BTC · 나스닥 상관</TermTooltip>
                </span>
                <SignalBadge label={signalLabel} color={c} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: S.sm, marginTop: S.xs }}>
                <div style={corrBarBg}>
                    <div style={{
                        position: "absolute", top: 1, bottom: 1, left: 1,
                        width: `${fillPct}%`, borderRadius: 3,
                        background: `linear-gradient(90deg, ${C.down}, ${C.success}, ${C.caution}, ${C.danger})`,
                        opacity: 0.7,
                    }} />
                    <div style={{
                        position: "absolute", top: -2, bottom: -2,
                        left: `${fillPct}%`, width: 3,
                        background: C.textPrimary, borderRadius: 2,
                        boxShadow: `0 0 6px ${C.textPrimary}80`,
                        transform: "translateX(-50%)",
                    }} />
                </div>
                <span style={{
                    ...MONO, color: c, fontSize: T.body, fontWeight: T.w_bold,
                    minWidth: 48, textAlign: "right",
                }}>
                    {correlation >= 0 ? "+" : ""}{correlation.toFixed(2)}
                </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                <span style={{ ...MONO, color: C.textDisabled, fontSize: 9 }}>-1.0</span>
                <span style={{ ...MONO, color: C.textDisabled, fontSize: 9 }}>0</span>
                <span style={{ ...MONO, color: C.textDisabled, fontSize: 9 }}>+1.0</span>
            </div>
        </div>
    )
}


/* ─────────── 스테이블코인 ─────────── */
function StablecoinBar({ totalB, usdtB, usdcB }: { totalB: number; usdtB: number; usdcB: number }) {
    const usdtPct = totalB > 0 ? (usdtB / totalB) * 100 : 50
    return (
        <div style={metricCard}>
            <div style={metricHead}>
                <span style={metricLabel}>
                    <TermTooltip termKey="STABLE_MCAP">스테이블코인 시총</TermTooltip>
                </span>
                <span style={{ ...MONO, color: C.accent, fontSize: T.body, fontWeight: T.w_bold }}>
                    ${totalB.toFixed(0)}B
                </span>
            </div>
            <div style={{
                display: "flex", height: 8, borderRadius: 4, overflow: "hidden", marginTop: S.sm,
            }}>
                <div style={{ width: `${usdtPct}%`, background: C.success }} />
                <div style={{ width: `${100 - usdtPct}%`, background: C.info }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: S.xs }}>
                <span style={{ ...MONO, color: C.success, fontSize: T.cap, fontWeight: T.w_semi }}>
                    USDT ${usdtB.toFixed(0)}B
                </span>
                <span style={{ ...MONO, color: C.info, fontSize: T.cap, fontWeight: T.w_semi }}>
                    USDC ${usdcB.toFixed(0)}B
                </span>
            </div>
        </div>
    )
}


/* ─────────── 서브 컴포넌트 ─────────── */

function SignalBadge({ label, color }: { label: string; color: string }) {
    return (
        <span style={{
            color, border: `1px solid ${color}44`,
            background: `${color}1A`,
            fontSize: T.cap, fontWeight: T.w_bold,
            padding: `1px ${S.xs}px`,
            borderRadius: R.sm,
            letterSpacing: "0.03em",
            fontFamily: FONT,
        }}>
            {label}
        </span>
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
    padding: S.xxl,
    display: "flex", flexDirection: "column",
    gap: S.lg,
}

const headerRow: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
}

const headerLeft: CSSProperties = {
    display: "flex", flexDirection: "column", gap: 2,
}

const titleStyle: CSSProperties = {
    fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary,
    letterSpacing: "-0.5px",
}

const metaStyle: CSSProperties = {
    fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med,
}

const hr: CSSProperties = {
    height: 1, background: C.border, margin: 0,
}

const gridRow: CSSProperties = {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: S.md,
}

/* row 의 두 카드 활성 여부에 따라 grid 분기.
 * 둘 다 활성: 1fr 1fr (좌우 분할).  단일 활성: 1fr (풀폭, 중앙 균형).
 * 시각 좌측 치우침 정정 (2026-05-05) */
function gridRowFor(a: boolean, b: boolean): CSSProperties {
    const both = a && b
    return {
        ...gridRow,
        gridTemplateColumns: both ? "1fr 1fr" : "1fr",
    }
}

const metricCard: CSSProperties = {
    background: C.bgCard,
    border: `1px solid ${C.border}`,
    borderRadius: R.md,
    padding: `${S.md}px ${S.lg}px`,
    display: "flex", flexDirection: "column", gap: S.xs,
}

const metricHead: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    gap: S.sm,
}

const metricLabel: CSSProperties = {
    color: C.textSecondary,
    fontSize: T.cap,
    fontWeight: T.w_semi,
    letterSpacing: "0.03em",
}

const fundingBarBg: CSSProperties = {
    position: "relative",
    flex: 1,
    height: 10,
    background: C.bgElevated,
    borderRadius: 5,
    overflow: "hidden",
}

const corrBarBg: CSSProperties = {
    position: "relative",
    flex: 1,
    height: 8,
    background: C.bgElevated,
    borderRadius: 4,
    overflow: "visible",
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

/**
 * ⚠️ DEPRECATED (2026-05-05 Plan v0.1 §3 [Stock] 폐기 결정)
 *
 * Brain v5 5등급 (STRONG_BUY/BUY/WATCH/CAUTION/AVOID) 이 저가주 위험도 자동 분류. 별도 컴포넌트 X
 *
 * Framer 페이지에서 인스턴스 제거. 추후 일괄 cleanup commit 시 git rm.
 *
 * ────────────────────────────────────────────────────────────
 */
import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useCallback } from "react"

/* ══════════════════════════════════════════════════════════════════
 * VERITY PennyScout — US 페니주 데일리 워치리스트 (스탠드얼론)
 *
 * .github/workflows/scout_penny.yml 가 매일 KST 06:30 자동 실행:
 *   Perplexity sonar-pro × 5쿼리 → NASDAQ 화이트리스트 ∩ 빈도 ≥3
 *   → data/penny_watchlist.json 자동 커밋
 *
 * 이 컴포넌트는 raw URL 만 fetch 해서 표시. AdminDashboard 와 독립.
 * VAMS 검증 기간 — 워치리스트 전용 (Brain 파이프라인 inject 안 함).
 * ══════════════════════════════════════════════════════════════════ */

const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO = FONT_MONO

interface Props {
    pennyUrl: string
    refreshIntervalSec: number
    showAllCandidates: boolean
}

type WatchItem = { ticker: string; frequency: number; sources: string }
type Candidate = { ticker: string; frequency: number }

interface PennyData {
    generated_at?: string
    queries_run?: number
    min_frequency?: number
    candidates_total?: number
    watchlist?: WatchItem[]
    all_candidates_top20?: Candidate[]
    perplexity_session?: { calls: number; cost_usd: number }
    whitelist_size?: number
    note?: string
}

function _fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    // raw.githubusercontent.com — simple request 만 허용. custom header 금지.
    const sep = url.includes("?") ? "&" : "?"
    return fetch(`${url}${sep}t=${Date.now()}`, { signal }).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.text().then((t) => {
            const cleaned = t
                .replace(/:\s*NaN\b/g, ": null")
                .replace(/:\s*-?Infinity\b/g, ": null")
            return JSON.parse(cleaned)
        })
    })
}

function _hoursSince(iso: string): number | null {
    if (!iso) return null
    const t = Date.parse(iso)
    if (Number.isNaN(t)) return null
    return (Date.now() - t) / (1000 * 60 * 60)
}

function _humanizeAge(iso: string): string {
    const h = _hoursSince(iso)
    if (h === null) return "—"
    if (h < 1) return `${Math.round(h * 60)}분 전`
    if (h < 24) return `${Math.round(h)}시간 전`
    return `${Math.round(h / 24)}일 전`
}

function _ageStatus(iso: string): "ok" | "warn" | "danger" {
    const h = _hoursSince(iso)
    if (h === null) return "warn"
    if (h < 36) return "ok"          // 일 1회 cron 기준 — 36h 이내면 정상
    if (h < 72) return "warn"        // 1.5일~3일 → cron 한두번 실패 신호
    return "danger"
}

function _statusColor(s: "ok" | "warn" | "danger") {
    return s === "ok" ? C.success : s === "warn" ? C.warn : C.danger
}

/* ─── TOP 5 행 ─── */
function WatchRow({ item, rank, total }: { item: WatchItem; rank: number; total: number }) {
    const pct = total > 0 ? (item.frequency / total) * 100 : 0
    return (
        <div style={{
            display: "flex", alignItems: "center", gap: 14,
            padding: "12px 14px", background: C.bgElevated,
            borderRadius: 10, border: `1px solid ${C.border}`,
        }}>
            <div style={{
                color: C.textTertiary, fontSize: 14, fontWeight: 700,
                minWidth: 22, textAlign: "right", fontFamily: MONO,
            }}>{rank}.</div>
            <div style={{ flex: "0 0 auto", minWidth: 72 }}>
                <span style={{
                    color: C.textPrimary, fontSize: 18, fontWeight: 800,
                    fontFamily: MONO, letterSpacing: "0.02em",
                }}>{item.ticker}</span>
            </div>
            <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{
                    flex: 1, height: 8, background: C.bgPage, borderRadius: 999, overflow: "hidden",
                }}>
                    <div style={{
                        width: `${pct}%`, height: "100%",
                        background: `linear-gradient(90deg, ${C.accent}, ${C.success})`,
                    }} />
                </div>
                <span style={{
                    color: C.textSecondary, fontSize: 12, fontFamily: MONO,
                    minWidth: 52, textAlign: "right",
                }}>{item.sources}</span>
            </div>
        </div>
    )
}

/* ─── 컴포넌트 ─── */
export default function PennyScout(props: Props) {
    const { pennyUrl, refreshIntervalSec = 300, showAllCandidates = false } = props
    const [data, setData] = useState<PennyData | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)
    const [showAll, setShowAll] = useState<boolean>(showAllCandidates)

    const load = useCallback(async () => {
        if (!pennyUrl) {
            setError("pennyUrl 미설정")
            return
        }
        setLoading(true)
        setError(null)
        const ac = new AbortController()
        try {
            const json = await _fetchJson(pennyUrl, ac.signal)
            setData(json)
        } catch (e: any) {
            const msg = e?.message || "fetch 실패"
            const hint = /HTTP 404/.test(msg)
                ? " — scout_penny.yml 첫 실행 대기중 (KST 06:30)"
                : /Load failed|Failed to fetch/i.test(msg)
                ? " — 네트워크/CORS 차단. URL 직접 열어 확인."
                : ""
            setError(`${msg}${hint}`)
        } finally {
            setLoading(false)
        }
        return () => ac.abort()
    }, [pennyUrl])

    useEffect(() => {
        load()
        const sec = Math.max(60, Number(refreshIntervalSec) || 300)
        const id = globalThis.setInterval(load, sec * 1000)
        return () => globalThis.clearInterval(id)
    }, [load, refreshIntervalSec])

    const watchlist = data?.watchlist || []
    const top20 = data?.all_candidates_top20 || []
    const queriesRun = data?.queries_run || 5
    const minFreq = data?.min_frequency || 3
    const generatedAt = data?.generated_at || ""
    const ageStatus = generatedAt ? _ageStatus(generatedAt) : "warn"
    const session = data?.perplexity_session

    return (
        <div style={{
            width: "100%", boxSizing: "border-box",
            background: C.bgPage, color: C.textPrimary,
            border: `1px solid ${C.border}`, borderRadius: R.lg,
            padding: S.xxl, fontFamily: FONT,
            display: "flex", flexDirection: "column", gap: S.lg,
        }}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: S.md }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <div style={{ color: C.textPrimary, fontSize: T.h2, fontWeight: T.w_bold, letterSpacing: "-0.5px" }}>
                        Penny Scout
                    </div>
                    <div style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med }}>
                        US 페니주 데일리 · Perplexity 다중쿼리 빈도 집계
                    </div>
                </div>
                <button
                    onClick={load}
                    disabled={loading}
                    style={{
                        background: "transparent", border: `1px solid ${C.border}`,
                        color: loading ? C.textTertiary : C.textSecondary,
                        padding: `${S.xs}px ${S.md}px`,
                        borderRadius: R.md, fontSize: T.cap, fontWeight: T.w_semi, fontFamily: FONT,
                        cursor: loading ? "wait" : "pointer",
                        flexShrink: 0,
                        letterSpacing: "0.05em",
                    }}
                >
                    {loading ? "갱신 중…" : "새로고침"}
                </button>
            </div>

            {/* VAMS 경고 배지 */}
            <div style={{
                display: "inline-flex", alignItems: "center", gap: S.sm,
                padding: `${S.xs}px ${S.md}px`, borderRadius: R.sm,
                background: `${C.warn}1A`, border: `1px solid ${C.warn}33`,
                color: C.warn, fontSize: T.cap, fontWeight: T.w_semi,
                alignSelf: "flex-start",
                letterSpacing: "0.03em",
            }}>
                <span style={{
                    width: 6, height: 6, borderRadius: "50%", background: C.warn,
                    boxShadow: `0 0 6px ${C.warn}80`,
                }} />
                VAMS 검증중 · 워치리스트 전용 (Brain inject 안 함)
            </div>

            {error && (
                <div style={{
                    background: `${C.danger}1A`, border: `1px solid ${C.danger}33`,
                    borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
                    color: C.danger, fontSize: T.cap, fontFamily: FONT,
                    display: "flex", alignItems: "center", gap: S.sm,
                }}>
                    <span style={{
                        width: 6, height: 6, borderRadius: "50%", background: C.danger,
                    }} />
                    {error}
                </div>
            )}

            {!data && !error && (
                <div style={{ color: C.textTertiary, fontSize: T.body, textAlign: "center", padding: S.xxl }}>
                    데이터 로드 중…
                </div>
            )}

            {data && (
                <>
                    {/* 메타 정보 */}
                    <div style={{
                        display: "flex", flexWrap: "wrap", gap: S.md, alignItems: "center",
                        padding: `${S.sm}px ${S.lg}px`,
                        background: C.bgCard, borderRadius: R.md,
                        border: `1px solid ${C.border}`,
                        fontSize: T.cap,
                    }}>
                        <div style={{ display: "flex", alignItems: "center", gap: S.xs }}>
                            <span style={{
                                width: 8, height: 8, borderRadius: "50%",
                                background: _statusColor(ageStatus),
                                boxShadow: `0 0 6px ${_statusColor(ageStatus)}50`,
                            }} />
                            <span style={{ color: C.textSecondary }}>
                                {generatedAt ? `${_humanizeAge(generatedAt)} 갱신` : "갱신 시각 미기록"}
                            </span>
                        </div>
                        <span style={{ color: C.textDisabled }}>·</span>
                        <span style={{ ...({ fontFamily: MONO, fontVariantNumeric: "tabular-nums" } as React.CSSProperties), color: C.textSecondary }}>
                            {queriesRun}쿼리 · 빈도 ≥{minFreq}
                        </span>
                        <span style={{ color: C.textDisabled }}>·</span>
                        <span style={{ ...({ fontFamily: MONO, fontVariantNumeric: "tabular-nums" } as React.CSSProperties), color: C.textSecondary }}>
                            {top20.length}개 후보
                        </span>
                    </div>

                    {/* TOP 5 */}
                    <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
                        <div style={{
                            color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
                            letterSpacing: "0.08em", textTransform: "uppercase",
                        }}>
                            TOP {watchlist.length} 워치리스트
                        </div>
                        {watchlist.length === 0 ? (
                            <div style={{
                                padding: `${S.lg}px ${S.lg}px`,
                                background: C.bgCard,
                                borderRadius: R.md, border: `1px dashed ${C.border}`,
                                color: C.textTertiary, fontSize: T.cap, fontFamily: FONT,
                                textAlign: "center",
                            }}>
                                조건 충족 종목 없음 (빈도 ≥{minFreq}). 다음 cron 실행 대기.
                            </div>
                        ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                                {watchlist.map((w, i) => (
                                    <WatchRow key={w.ticker} item={w} rank={i + 1} total={queriesRun} />
                                ))}
                            </div>
                        )}
                    </div>

                    {/* 전체 TOP 20 토글 */}
                    {top20.length > watchlist.length && (
                        <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
                            <button
                                onClick={() => setShowAll((v) => !v)}
                                style={{
                                    background: "transparent", border: `1px solid ${C.border}`,
                                    color: C.textSecondary,
                                    padding: `${S.xs}px ${S.md}px`,
                                    borderRadius: R.md,
                                    fontSize: T.cap, fontWeight: T.w_semi,
                                    fontFamily: FONT,
                                    cursor: "pointer", width: "100%",
                                    letterSpacing: "0.03em",
                                }}
                            >
                                {showAll ? "▾ 전체 후보 접기" : `▸ 전체 후보 TOP ${top20.length} 보기`}
                            </button>
                            {showAll && (
                                <div style={{
                                    padding: `${S.md}px ${S.lg}px`,
                                    background: C.bgCard, borderRadius: R.md,
                                    border: `1px solid ${C.border}`,
                                    display: "grid",
                                    gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
                                    gap: S.sm, fontSize: T.cap,
                                }}>
                                    {top20.map((c) => (
                                        <div key={c.ticker} style={{
                                            display: "flex", justifyContent: "space-between", gap: S.sm,
                                            padding: `${S.xs}px ${S.sm}px`,
                                            background: C.bgPage, borderRadius: R.sm,
                                        }}>
                                            <span style={{ color: C.textPrimary, fontFamily: MONO, fontWeight: T.w_bold }}>
                                                {c.ticker}
                                            </span>
                                            <span style={{ ...({ fontFamily: MONO, fontVariantNumeric: "tabular-nums" } as React.CSSProperties), color: C.textTertiary }}>
                                                {c.frequency}/{queriesRun}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* 방법론 + 비용 footnote */}
                    <div style={{
                        paddingTop: S.lg, borderTop: `1px solid ${C.border}`,
                        color: C.textTertiary, fontSize: T.cap, fontFamily: FONT, lineHeight: 1.6,
                        display: "flex", flexDirection: "column", gap: S.xs,
                    }}>
                        <div style={{
                            color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
                            letterSpacing: "0.08em", textTransform: "uppercase",
                            marginBottom: S.xs,
                        }}>
                            방법론
                        </div>
                        <div>· Perplexity sonar-pro × {queriesRun}쿼리 (best / momentum / Reddit / fundamentals / hot)</div>
                        <div>· NASDAQ trader 화이트리스트 {data?.whitelist_size ? `${data.whitelist_size.toLocaleString()}` : "12k"} 심볼 ∩ 빈도 ≥{minFreq}</div>
                        <div>· common-word 블록리스트 — USA / AI / CEO / FED 등 prose 약어 차단</div>
                        <div>· Brain 파이프라인 inject <span style={{ color: C.warn, fontWeight: T.w_semi }}>안 함</span> (VAMS 검증중)</div>
                        {session && (
                            <div style={{ marginTop: S.xs }}>
                                Perplexity 세션: {session.calls}회 호출 · ${session.cost_usd?.toFixed(4) || "0.0000"}
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    )
}

/* ─── Framer property controls ─── */
const _DEFAULT_PENNY = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/penny_watchlist.json"

PennyScout.defaultProps = {
    pennyUrl: _DEFAULT_PENNY,
    refreshIntervalSec: 300,
    showAllCandidates: false,
}

addPropertyControls(PennyScout, {
    pennyUrl: {
        type: ControlType.String, title: "PennyScout URL",
        defaultValue: _DEFAULT_PENNY,
        description: "data/penny_watchlist.json raw URL",
    },
    refreshIntervalSec: {
        type: ControlType.Number, title: "갱신 간격(초)",
        defaultValue: 300, min: 60, max: 3600, step: 60,
    },
    showAllCandidates: {
        type: ControlType.Boolean, title: "전체 TOP20 펼치기 기본값",
        defaultValue: false,
    },
})

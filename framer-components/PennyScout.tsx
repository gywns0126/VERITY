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
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B",
    border: "#23242C", borderStrong: "#34353D",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76",
    accent: "#B5FF19",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const MONO = "ui-monospace, SF Mono, Menlo, monospace"

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
            width: "100%", background: C.bgPage, padding: "20px 16px 32px",
            boxSizing: "border-box", fontFamily: FONT, color: C.textPrimary,
        }}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 14 }}>
                <div>
                    <div style={{ color: C.accent, fontSize: 20, fontWeight: 900, letterSpacing: "-0.02em" }}>
                        🔍 Penny Scout
                    </div>
                    <div style={{ color: C.textSecondary, fontSize: 12, marginTop: 2 }}>
                        US 페니주 데일리 — Perplexity 다중쿼리 빈도 집계
                    </div>
                </div>
                <button
                    onClick={load}
                    disabled={loading}
                    style={{
                        background: C.bgCard, border: `1px solid ${C.border}`,
                        color: loading ? C.textTertiary : C.accent, padding: "6px 12px",
                        borderRadius: 8, fontSize: 12, fontWeight: 700, fontFamily: FONT,
                        cursor: loading ? "wait" : "pointer",
                    }}
                >
                    {loading ? "갱신 중…" : "↻ 새로고침"}
                </button>
            </div>

            {/* VAMS 경고 배지 */}
            <div style={{
                display: "inline-block", padding: "4px 10px", borderRadius: 6,
                background: `${C.warn}1F`, border: `1px solid ${C.warn}55`,
                color: C.warn, fontSize: 11, fontWeight: 700, marginBottom: 14,
            }}>
                ⚠ VAMS 검증중 — 워치리스트 전용 (Brain inject 안 함)
            </div>

            {error && (
                <div style={{
                    background: `${C.danger}15`, border: `1px solid ${C.danger}40`,
                    borderRadius: 10, padding: "10px 14px", marginBottom: 14,
                    color: C.danger, fontSize: 12, fontFamily: FONT,
                }}>
                    ⚠ {error}
                </div>
            )}

            {!data && !error && (
                <div style={{ color: C.textSecondary, fontSize: 13, textAlign: "center", padding: 40 }}>
                    데이터 로드 중…
                </div>
            )}

            {data && (
                <>
                    {/* 메타 정보 */}
                    <div style={{
                        display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center",
                        padding: "10px 14px", background: C.bgCard, borderRadius: 10,
                        border: `1px solid ${C.border}`, marginBottom: 14, fontSize: 12,
                    }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span style={{
                                width: 8, height: 8, borderRadius: 999,
                                background: _statusColor(ageStatus),
                                boxShadow: `0 0 6px ${_statusColor(ageStatus)}50`,
                            }} />
                            <span style={{ color: C.textSecondary }}>
                                {generatedAt ? `${_humanizeAge(generatedAt)} 갱신` : "갱신 시각 미기록"}
                            </span>
                        </div>
                        <div style={{ color: C.textTertiary }}>·</div>
                        <div style={{ color: C.textSecondary }}>
                            {queriesRun}쿼리 · 빈도 ≥{minFreq}
                        </div>
                        <div style={{ color: C.textTertiary }}>·</div>
                        <div style={{ color: C.textSecondary }}>
                            {top20.length}개 후보 추출
                        </div>
                    </div>

                    {/* TOP 5 */}
                    <div style={{ marginBottom: 18 }}>
                        <div style={{
                            color: C.textPrimary, fontSize: 13, fontWeight: 800,
                            marginBottom: 10, letterSpacing: "-0.01em",
                        }}>
                            TOP {watchlist.length} 워치리스트
                        </div>
                        {watchlist.length === 0 ? (
                            <div style={{
                                padding: "14px 16px", background: C.bgCard,
                                borderRadius: 10, border: `1px dashed ${C.border}`,
                                color: C.textSecondary, fontSize: 12, fontFamily: FONT,
                                textAlign: "center",
                            }}>
                                조건 충족 종목 없음 (빈도 ≥{minFreq}). 다음 cron 실행 대기.
                            </div>
                        ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                {watchlist.map((w, i) => (
                                    <WatchRow key={w.ticker} item={w} rank={i + 1} total={queriesRun} />
                                ))}
                            </div>
                        )}
                    </div>

                    {/* 전체 TOP 20 토글 */}
                    {top20.length > watchlist.length && (
                        <div style={{ marginBottom: 16 }}>
                            <button
                                onClick={() => setShowAll((v) => !v)}
                                style={{
                                    background: "transparent", border: `1px solid ${C.border}`,
                                    color: C.textSecondary, padding: "6px 12px",
                                    borderRadius: 8, fontSize: 12, fontFamily: FONT,
                                    cursor: "pointer", width: "100%",
                                }}
                            >
                                {showAll ? "▲ 전체 후보 접기" : `▼ 전체 후보 TOP ${top20.length} 보기`}
                            </button>
                            {showAll && (
                                <div style={{
                                    marginTop: 10, padding: "12px 14px",
                                    background: C.bgCard, borderRadius: 10,
                                    border: `1px solid ${C.border}`,
                                    display: "grid",
                                    gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
                                    gap: 8, fontSize: 12,
                                }}>
                                    {top20.map((c) => (
                                        <div key={c.ticker} style={{
                                            display: "flex", justifyContent: "space-between", gap: 8,
                                            padding: "4px 8px", background: C.bgPage, borderRadius: 6,
                                        }}>
                                            <span style={{ color: C.textPrimary, fontFamily: MONO, fontWeight: 700 }}>
                                                {c.ticker}
                                            </span>
                                            <span style={{ color: C.textTertiary, fontFamily: MONO }}>
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
                        marginTop: 18, paddingTop: 14, borderTop: `1px solid ${C.border}`,
                        color: C.textTertiary, fontSize: 11, fontFamily: FONT, lineHeight: 1.6,
                    }}>
                        <div style={{ marginBottom: 4, fontWeight: 700, color: C.textSecondary }}>
                            방법론
                        </div>
                        <div>• Perplexity sonar-pro × {queriesRun}쿼리 (best / momentum / Reddit / fundamentals / hot)</div>
                        <div>• NASDAQ trader 화이트리스트 {data?.whitelist_size ? `${data.whitelist_size.toLocaleString()}` : "12k"} 심볼 ∩ 빈도 ≥{minFreq}</div>
                        <div>• common-word 블록리스트 — USA / AI / CEO / FED 등 prose 약어 차단</div>
                        <div>• Brain 파이프라인 inject <strong style={{ color: C.warn }}>안 함</strong> (VAMS 검증중)</div>
                        {session && (
                            <div style={{ marginTop: 8, color: C.textTertiary }}>
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

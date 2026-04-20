import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useRef } from "react"

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

/** Framer 단일 파일 붙여넣기용 인라인 (fetchPortfolioJson.ts와 동일 로직 — 수정 시 맞춰 주세요) */
// §8 AVOID 라벨 의미 — 펀더멘털 결함 전용
const AVOID_TOOLTIP =
    "AVOID = 펀더멘털 결함 (감사거절·분식·상폐 위험 등 has_critical) 또는 매크로 위기 cap. 단순 저점수는 CAUTION."

// §11~§14 audit overrides
const OVERRIDE_LABELS: Record<string, string> = {
    contrarian_upgrade: "역발상↑", quadrant_unfavored: "분면불리↓",
    cape_bubble: "CAPE버블cap", panic_stage_3: "패닉3cap", panic_stage_4: "패닉4cap",
    vix_spread_panic: "VIX패닉cap", yield_defense: "수익률방어cap",
    sector_quadrant_drift: "섹터드리프트", ai_upside_relax: "AI호재완화",
}

function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

const PORTFOLIO_FETCH_INIT: RequestInit = {
    cache: "no-store",
    mode: "cors",
    credentials: "omit",
}

// WARN-24: 15초 timeout + AbortController — 네트워크 hang 방지
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000

function _withTimeout<T>(p: Promise<T>, ms: number, ac: AbortController): Promise<T> {
    const timer = setTimeout(() => ac.abort(), ms)
    return p.finally(() => clearTimeout(timer))
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    return _withTimeout(
        fetch(bustPortfolioUrl(url), { ...PORTFOLIO_FETCH_INIT, signal: ac.signal })
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.text()
            })
            .then((txt) =>
                JSON.parse(
                    txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
                ),
            ),
        PORTFOLIO_FETCH_TIMEOUT_MS,
        ac,
    )
}

const DATA_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

type Period = "daily" | "weekly" | "monthly" | "quarterly" | "semi" | "annual"
const PERIOD_LABELS: Record<Period, string> = {
    daily: "일일",
    weekly: "주간",
    monthly: "월간",
    quarterly: "분기",
    semi: "반기",
    annual: "연간",
}
const PERIOD_DESC: Record<Period, string> = {
    daily: "오늘의 시장과 종목 분석",
    weekly: "섹터의 흐름을 읽다 — 주간 전략",
    monthly: "복기와 예측 — 추천 성과 측정",
    quarterly: "거시적 안목 — 실적 시즌 총평",
    semi: "6개월 투자 전략 종합 리뷰",
    annual: "1년 투자 성과 종합 보고서",
}
const PERIOD_REPORT_KEY: Record<Period, string> = {
    daily: "",
    weekly: "weekly_report",
    monthly: "monthly_report",
    quarterly: "quarterly_report",
    semi: "semi_report",
    annual: "annual_report",
}

const PDF_BASE_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/"
const PERIOD_PDF_FILES: Record<Period, string> = {
    daily: "verity_report_daily.pdf",
    weekly: "verity_report_weekly.pdf",
    monthly: "verity_report_monthly.pdf",
    quarterly: "verity_report_quarterly.pdf",
    semi: "verity_report_semi.pdf",
    annual: "verity_report_annual.pdf",
}

interface Props {
    dataUrl: string
    market: "kr" | "us"
}

const US_EVENT_KW = ["FOMC", "CPI", "GDP", "PCE", "NFP", "Fed", "고용", "비농업", "소비자물가", "금리결정", "PPI", "ISM", "PMI"]
const KR_EVENT_KW = ["한국", "코스피", "코스닥", "한국은행", "기준금리", "수출", "무역수지", "원달러"]
const US_ALERT_KW = ["미국", "연준", "Fed", "NASDAQ", "NYSE", "S&P", "다우", "국채", "VIX", "달러"]
const KR_ALERT_KW = ["한국", "국내", "코스피", "코스닥", "KRX", "원달러", "원화", "한국은행", "기준금리"]

function _isUSTicker(ticker: string): boolean {
    return /^[A-Z]{1,5}$/.test(String(ticker || "").trim())
}

function _isUSStock(s: any): boolean {
    return s?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(s?.market || "") || _isUSTicker(s?.ticker || "")
}

function _toText(v: any): string {
    if (v == null) return ""
    if (Array.isArray(v)) return v.map(_toText).join(" ")
    return String(v)
}

function _containsAny(text: string, kws: string[]): boolean {
    const t = String(text || "").toLowerCase()
    return kws.some((kw) => t.includes(kw.toLowerCase()))
}

function _containsToken(text: string, tokens: Set<string>): boolean {
    const t = String(text || "").toLowerCase()
    for (const token of tokens) {
        if (token && t.includes(token)) return true
    }
    return false
}

function _isUSEvent(e: any): boolean {
    const txt = `${_toText(e?.name)} ${_toText(e?.impact)} ${_toText(e?.country)}`
    if (_containsAny(txt, US_EVENT_KW)) return true
    if ((e?.country || "").toLowerCase().includes("미국")) return true
    if (_containsAny(txt, KR_EVENT_KW)) return false
    return false
}

function _isUSAlert(a: any, usTokens: Set<string>, krTokens: Set<string>): boolean {
    const cat = String(a?.category || "").toLowerCase()
    const ticker = String(a?.ticker || "").trim()
    const txt = `${_toText(a?.message)} ${_toText(a?.action)} ${_toText(a?.ticker)}`

    if (ticker) return _isUSTicker(ticker)
    if (_containsToken(txt, usTokens)) return true
    if (_containsToken(txt, krTokens)) return false
    if (_containsAny(txt, US_ALERT_KW)) return true
    if (_containsAny(txt, KR_ALERT_KW)) return false

    if (["holding", "earnings", "opportunity", "price_target", "value_chain"].includes(cat)) {
        return false
    }
    return false
}

/* ─── Sub-components (defined outside VerityReport to prevent remount on re-render) ─── */
function SectionIcon({ icon, color }: { icon: string; color: string }) {
    return (
        <div style={{
            width: 28, height: 28, borderRadius: 6,
            background: `${color}20`, border: `1px solid ${color}40`,
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        }}>
            <span style={{ color, fontSize: 12, fontWeight: 800, fontFamily: font }}>{icon}</span>
        </div>
    )
}

function Section({ icon, iconColor, label, children }: { icon: string; iconColor: string; label: string; children?: any }) {
    return (
        <div style={{ padding: "12px 14px", background: "#111", borderRadius: 12, border: "1px solid #1A1A1A" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                <SectionIcon icon={icon} color={iconColor} />
                <span style={{ color: iconColor, fontSize: 12, fontWeight: 700, fontFamily: font }}>{label}</span>
            </div>
            {children}
        </div>
    )
}

function MetricRow({ items }: { items: { label: string; value: string; color?: string }[] }) {
    return (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6, marginBottom: 4 }}>
            {items.map((m, i) => (
                <div key={i} style={{ background: "#0A0A0A", borderRadius: 8, padding: "8px 10px", display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ color: "#666", fontSize: 9, fontWeight: 500 }}>{m.label}</span>
                    <span style={{ color: m.color || "#fff", fontSize: 13, fontWeight: 700 }}>{m.value}</span>
                </div>
            ))}
        </div>
    )
}

function RingGauge({ value, label, size = 56, color }: { value: number; label: string; size?: number; color: string }) {
    const r = (size - 6) / 2
    const circ = 2 * Math.PI * r
    const offset = circ * (1 - Math.min(value, 100) / 100)
    return (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
            <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1A1A1A" strokeWidth={5} />
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={5}
                    strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" />
            </svg>
            <span style={{ color, fontSize: 14, fontWeight: 800, fontFamily: font, marginTop: -38 }}>{value}</span>
            <span style={{ color: "#666", fontSize: 9, fontFamily: font, marginTop: 16 }}>{label}</span>
        </div>
    )
}

function BarChart({ items, maxValue }: { items: { label: string; value: number; color: string }[]; maxValue?: number }) {
    const mv = maxValue || Math.max(...items.map(i => Math.abs(i.value)), 1)
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {items.map((item, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ color: "#888", fontSize: 10, fontFamily: font, width: 70, textAlign: "right", flexShrink: 0 }}>{item.label}</span>
                    <div style={{ flex: 1, height: 14, background: "#1A1A1A", borderRadius: 4, overflow: "hidden" }}>
                        <div style={{ width: `${Math.min(Math.abs(item.value) / mv * 100, 100)}%`, height: "100%", background: item.color, borderRadius: 4, transition: "width 0.5s" }} />
                    </div>
                    <span style={{ color: item.color, fontSize: 11, fontWeight: 700, fontFamily: font, width: 45, textAlign: "right" }}>{item.value}%</span>
                </div>
            ))}
        </div>
    )
}

export default function VerityReport(props: Props) {
    const { dataUrl, market } = props
    const [data, setData] = useState<any>(null)
    const [period, setPeriod] = useState<Period>("daily")
    const [pdfStatus, setPdfStatus] = useState<"idle" | "not_found">("idle")
    const reportRef = useRef<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 200, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#999", fontSize: 14, fontFamily: font }}>리포트 로딩 중...</span>
            </div>
        )
    }

    const downloadPdf = () => {
        const url = PDF_BASE_URL + PERIOD_PDF_FILES[period]
        const w = window.open(url, "_blank")
        if (!w) {
            setPdfStatus("not_found")
            setTimeout(() => setPdfStatus("idle"), 5000)
        }
    }

    const pdfUpdated = data?.updated_at
        ? new Date(data.updated_at).toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" })
        : ""
    const dailyReportData = data?.daily_report || {}
    const hasDailyReport = Boolean(dailyReportData?.market_summary)
    const hasPdfHint = period === "daily" ? hasDailyReport : Boolean(data?.[PERIOD_REPORT_KEY[period]])

    const gradeLabels: Record<string, string> = { STRONG_BUY: "강력매수", BUY: "매수", WATCH: "관망", CAUTION: "주의", AVOID: "회피" }
    const gradeColors: Record<string, string> = { STRONG_BUY: "#22C55E", BUY: "#B5FF19", WATCH: "#FFD600", CAUTION: "#F59E0B", AVOID: "#EF4444" }

    const updated = data?.updated_at
        ? new Date(data.updated_at).toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric", weekday: "long" })
        : "—"
    const dateShort = data?.updated_at
        ? new Date(data.updated_at).toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" })
        : ""

    const periodicReport = period !== "daily" ? data[PERIOD_REPORT_KEY[period]] : null
    const isPeriodic = period !== "daily" && periodicReport

    return (
        <div style={card}>
            <style>{`
                @media print {
                    .verity-report-no-print { display: none !important; }
                    body * { visibility: hidden !important; }
                    #verity-report, #verity-report * { visibility: visible !important; }
                    #verity-report {
                        position: absolute !important;
                        left: 0 !important; top: 0 !important; width: 100% !important;
                        border: none !important;
                        -webkit-print-color-adjust: exact !important;
                        print-color-adjust: exact !important;
                    }
                }
            `}</style>

            {/* 기간 선택 탭 */}
            <div className="verity-report-no-print" style={periodBar}>
                {(Object.keys(PERIOD_LABELS) as Period[]).map((p) => (
                    <button key={p} onClick={() => setPeriod(p)} style={{
                        ...periodBtn,
                        background: period === p ? "#B5FF19" : "#1A1A1A",
                        color: period === p ? "#000" : "#888",
                    }}>
                        {PERIOD_LABELS[p]}
                    </button>
                ))}
            </div>

            <div id="verity-report" ref={reportRef}>
                {/* 헤더 */}
                <div style={header}>
                    <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                            <span style={{ color: "#B5FF19", fontSize: 11, fontWeight: 800, letterSpacing: 1, fontFamily: font }}>VERITY TERMINAL</span>
                            <span style={{ color: "#333", fontSize: 10, fontFamily: font }}>v2.0</span>
                        </div>
                        <span style={{ color: "#fff", fontSize: 20, fontWeight: 800, fontFamily: font, display: "block" }}>
                            {isPeriodic ? (periodicReport.title || `${PERIOD_LABELS[period]} 종합 분석 리포트`) : `${PERIOD_LABELS[period]} 종합 분석 리포트`}
                        </span>
                        <span style={{ color: "#666", fontSize: 12, fontFamily: font }}>
                            {isPeriodic && periodicReport._date_range
                                ? `${periodicReport._date_range.start} ~ ${periodicReport._date_range.end} · ${PERIOD_DESC[period]}`
                                : `${updated} · ${PERIOD_DESC[period]}`}
                        </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "flex-end", gap: 6, flexDirection: "column" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            {hasPdfHint ? (
                                <button type="button" className="verity-report-no-print" title="AI 종합 분석 PDF 다운로드 (새 탭)" onClick={downloadPdf} style={pdfBtn}>
                                    PDF 다운로드
                                </button>
                            ) : (
                                <span className="verity-report-no-print" style={{ color: "#555", fontSize: 10, fontFamily: font }}>
                                    PDF 준비 중
                                </span>
                            )}
                            <span style={aiBadge}>GEMINI + BRAIN</span>
                        </div>
                        {pdfStatus === "not_found" && (
                            <span className="verity-report-no-print" style={{ color: "#F59E0B", fontSize: 10, fontFamily: font }}>
                                PDF 파일이 아직 없습니다 — 장 마감 full 분석 후 자동 생성됩니다
                            </span>
                        )}
                    </div>
                </div>

                {/* ===== 정기 리포트 뷰 ===== */}
                {isPeriodic ? (
                    <div style={bodyWrap}>
                        {/* 핵심 요약 배너 */}
                        {periodicReport.executive_summary && (
                            <div style={{ padding: "16px 20px", background: "linear-gradient(135deg, #0A1A00, #1A2A00)", borderRadius: 12, border: "1px solid #1A3300" }}>
                                <span style={{ color: "#B5FF19", fontSize: 15, fontWeight: 800, fontFamily: font, lineHeight: "1.5" }}>
                                    {periodicReport.executive_summary}
                                </span>
                            </div>
                        )}

                        {/* 성과표: 지난 실현 + 이번 기대수익률 */}
                        {(() => {
                            const stats = periodicReport._raw_stats || {}
                            const expected = (periodicReport as any).expected_return || {}
                            const hasRealized = (stats.total_buy_recs || 0) > 0
                            const hasExpected = (expected.count || 0) > 0
                            if (!hasRealized && !hasExpected) return null
                            const retVal = stats.avg_return_pct ?? 0
                            const expVal = expected.avg_upside_pct ?? 0
                            const retCol = retVal >= 0 ? "#22C55E" : "#EF4444"
                            const expCol = expVal >= 0 ? "#B5FF19" : "#EF4444"
                            const topPick = expected.top_picks?.[0]
                            return (
                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                                    <div style={{ padding: "16px 18px", background: "#0A0A0A", borderRadius: 12, border: "1px solid #222" }}>
                                        <div style={{ color: "#888", fontSize: 10, fontWeight: 700, letterSpacing: "0.05em", marginBottom: 8, fontFamily: font }}>
                                            지난 기간 실현 수익률
                                        </div>
                                        {hasRealized ? (
                                            <>
                                                <div style={{ color: retCol, fontSize: 32, fontWeight: 900, fontFamily: font, letterSpacing: "-0.02em", lineHeight: 1 }}>
                                                    {retVal >= 0 ? "+" : ""}{Number(retVal).toFixed(1)}%
                                                </div>
                                                <div style={{ color: "#888", fontSize: 11, fontFamily: font, marginTop: 8, lineHeight: 1.5 }}>
                                                    <b style={{ color: "#ccc" }}>{stats.total_buy_recs}</b>종목 매수 추천 · 적중률 <b style={{ color: (stats.hit_rate_pct ?? 0) >= 50 ? "#22C55E" : "#FFD600" }}>{stats.hit_rate_pct ?? 0}%</b>
                                                </div>
                                            </>
                                        ) : (
                                            <div style={{ color: "#666", fontSize: 12, fontFamily: font, padding: "10px 0" }}>데이터 누적 중</div>
                                        )}
                                    </div>
                                    <div style={{ padding: "16px 18px", background: "linear-gradient(135deg, #0A1A00, #0A0A0A)", borderRadius: 12, border: "1px solid #1A3300" }}>
                                        <div style={{ color: "#B5FF19", fontSize: 10, fontWeight: 700, letterSpacing: "0.05em", marginBottom: 8, fontFamily: font }}>
                                            이번 리포트 기대수익률
                                        </div>
                                        {hasExpected ? (
                                            <>
                                                <div style={{ color: expCol, fontSize: 32, fontWeight: 900, fontFamily: font, letterSpacing: "-0.02em", lineHeight: 1 }}>
                                                    {expVal >= 0 ? "+" : ""}{Number(expVal).toFixed(1)}%
                                                </div>
                                                <div style={{ color: "#888", fontSize: 11, fontFamily: font, marginTop: 8, lineHeight: 1.5 }}>
                                                    <b style={{ color: "#ccc" }}>{expected.count}</b>종목 · 최대 <b style={{ color: "#B5FF19" }}>+{Number(expected.max_upside_pct ?? 0).toFixed(1)}%</b>
                                                    {topPick && <> · TOP <b style={{ color: "#ccc" }}>{topPick.name}</b> <span style={{ color: "#B5FF19", fontWeight: 700 }}>+{Number(topPick.upside_pct).toFixed(1)}%</span></>}
                                                </div>
                                            </>
                                        ) : (
                                            <div style={{ color: "#666", fontSize: 12, fontFamily: font, padding: "10px 0" }}>현재 매수 추천 종목 없음</div>
                                        )}
                                        <div style={{ color: "#555", fontSize: 9, fontFamily: font, marginTop: 10, lineHeight: 1.4 }}>
                                            ※ 목표가 대비 업사이드 (실현 보장 아님)
                                        </div>
                                    </div>
                                </div>
                            )
                        })()}

                        {/* 추천 성과 복기 */}
                        {periodicReport._raw_stats && (
                            <Section icon="📊" iconColor="#22C55E" label={`추천 성과 복기 — 적중률 ${periodicReport._raw_stats.hit_rate_pct || 0}%`}>
                                <MetricRow items={[
                                    { label: "BUY 추천", value: `${periodicReport._raw_stats.total_buy_recs || 0}건` },
                                    { label: "적중률", value: `${periodicReport._raw_stats.hit_rate_pct || 0}%`, color: (periodicReport._raw_stats.hit_rate_pct || 0) >= 50 ? "#22C55E" : "#EF4444" },
                                    { label: "평균 수익률", value: `${(periodicReport._raw_stats.avg_return_pct || 0) >= 0 ? "+" : ""}${periodicReport._raw_stats.avg_return_pct || 0}%`, color: (periodicReport._raw_stats.avg_return_pct || 0) >= 0 ? "#22C55E" : "#EF4444" },
                                    { label: "포트폴리오", value: `${(periodicReport._raw_stats.portfolio_return || 0) >= 0 ? "+" : ""}${periodicReport._raw_stats.portfolio_return || 0}%`, color: (periodicReport._raw_stats.portfolio_return || 0) >= 0 ? "#22C55E" : "#EF4444" },
                                ]} />
                                {periodicReport._raw_stats.best_picks?.length > 0 && (
                                    <div style={{ marginTop: 10 }}>
                                        <span style={{ color: "#22C55E", fontSize: 10, fontWeight: 700, display: "block", marginBottom: 6 }}>최고 수익 종목</span>
                                        {periodicReport._raw_stats.best_picks.slice(0, 5).map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #1A1A1A" }}>
                                                <span style={{ color: "#ccc", fontSize: 12, fontFamily: font }}>{i + 1}. {s.name}</span>
                                                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                                                    <span style={{ color: "#888", fontSize: 10 }}>브레인 {s.orig_brain_score}</span>
                                                    <span style={{ color: s.return_pct >= 0 ? "#22C55E" : "#EF4444", fontSize: 13, fontWeight: 800, fontFamily: font }}>
                                                        {s.return_pct >= 0 ? "+" : ""}{s.return_pct}%
                                                    </span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {periodicReport._raw_stats.worst_picks?.length > 0 && (
                                    <div style={{ marginTop: 10 }}>
                                        <span style={{ color: "#EF4444", fontSize: 10, fontWeight: 700, display: "block", marginBottom: 6 }}>손실 종목</span>
                                        {periodicReport._raw_stats.worst_picks.map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #1A1A1A" }}>
                                                <span style={{ color: "#888", fontSize: 12, fontFamily: font }}>{s.name}</span>
                                                <span style={{ color: "#EF4444", fontSize: 13, fontWeight: 800, fontFamily: font }}>{s.return_pct}%</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {periodicReport.performance_review && (
                                    <p style={{ ...sectionText, marginTop: 10, paddingTop: 10, borderTop: "1px solid #1A1A1A" }}>{periodicReport.performance_review}</p>
                                )}
                            </Section>
                        )}

                        {/* 섹터 동향 분석 */}
                        {periodicReport._raw_stats?.top3_sectors?.length > 0 && (
                            <Section icon="📈" iconColor="#A78BFA" label="섹터 동향 — 돈의 흐름">
                                <BarChart items={periodicReport._raw_stats.top3_sectors.map((s: any) => ({
                                    label: s.name,
                                    value: s.avg_change_pct,
                                    color: s.avg_change_pct >= 0 ? "#22C55E" : "#EF4444",
                                }))} />
                                {periodicReport.sector_analysis && (
                                    <p style={{ ...sectionText, marginTop: 10 }}>{periodicReport.sector_analysis}</p>
                                )}
                            </Section>
                        )}

                        {/* 메타 분석 — 데이터 소스 정확도 */}
                        {periodicReport._raw_stats?.meta_findings?.length > 0 && (
                            <Section icon="🔬" iconColor="#60A5FA" label="메타 분석 — 어떤 지표가 맞았나?">
                                <BarChart items={periodicReport._raw_stats.meta_findings.map((f: any) => {
                                    const labels: Record<string, string> = {
                                        multi_factor: "멀티팩터", consensus: "내부모델합의", timing: "타이밍",
                                        prediction: "XGBoost", sentiment: "뉴스 감성", brain: "브레인",
                                    }
                                    return {
                                        label: labels[f.source] || f.source,
                                        value: f.accuracy_pct,
                                        color: f.accuracy_pct >= 60 ? "#22C55E" : f.accuracy_pct >= 50 ? "#FFD600" : "#EF4444",
                                    }
                                })} maxValue={100} />
                                {periodicReport.meta_insight && (
                                    <p style={{ ...sectionText, marginTop: 10, padding: "10px 12px", background: "#0A0A0A", borderRadius: 8, border: "1px solid #222" }}>
                                        {periodicReport.meta_insight}
                                    </p>
                                )}
                            </Section>
                        )}

                        {/* 브레인 정확도 평가 */}
                        {periodicReport._raw_stats?.brain_grades && Object.keys(periodicReport._raw_stats.brain_grades).length > 0 && (
                            <Section icon="🧠" iconColor="#B5FF19" label="AI 브레인 등급별 실적">
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
                                    {Object.entries(periodicReport._raw_stats.brain_grades as Record<string, any>).map(([grade, stats]) => (
                                        <div key={grade} style={{
                                            padding: "8px 12px", borderRadius: 8, background: "#0A0A0A", border: `1px solid ${gradeColors[grade] || "#333"}30`,
                                            display: "flex", flexDirection: "column", gap: 2, minWidth: 80,
                                        }}>
                                            <span
                                                style={{ color: gradeColors[grade] || "#888", fontSize: 10, fontWeight: 700, fontFamily: font, cursor: grade === "AVOID" ? "help" : "default" }}
                                                title={grade === "AVOID" ? AVOID_TOOLTIP : undefined}
                                            >{gradeLabels[grade] || grade}</span>
                                            <span style={{ color: "#fff", fontSize: 14, fontWeight: 800, fontFamily: font }}>{stats.avg_return >= 0 ? "+" : ""}{stats.avg_return}%</span>
                                            <span style={{ color: "#666", fontSize: 9 }}>적중 {stats.hit_rate}% · {stats.count}종목</span>
                                        </div>
                                    ))}
                                </div>
                                {periodicReport.brain_review && (
                                    <p style={sectionText}>{periodicReport.brain_review}</p>
                                )}
                            </Section>
                        )}

                        {/* 매크로 전망 */}
                        {periodicReport.macro_outlook && (
                            <Section icon="M" iconColor="#A78BFA" label="매크로 환경 변화">
                                <p style={sectionText}>{periodicReport.macro_outlook}</p>
                            </Section>
                        )}

                        {/* 전략 제안 */}
                        {periodicReport.strategy && (
                            <Section icon="T" iconColor="#22C55E" label={`다음 ${PERIOD_LABELS[period]} 전략`}>
                                <p style={sectionText}>{periodicReport.strategy}</p>
                            </Section>
                        )}

                        {/* 리스크 주의 */}
                        {periodicReport.risk_watch && (
                            <Section icon="!" iconColor="#EF4444" label="리스크 주의">
                                <p style={sectionText}>{periodicReport.risk_watch}</p>
                            </Section>
                        )}
                    </div>
                ) : (
                    /* ===== 일일 리포트 뷰 (기존) ===== */
                    <DailyReportView data={data} market={market} Section={Section} MetricRow={MetricRow} RingGauge={RingGauge} gradeLabels={gradeLabels} gradeColors={gradeColors} />
                )}

                {/* 미생성 안내 (정기 리포트 데이터 없는 경우) */}
                {period !== "daily" && !periodicReport && (
                    <div style={{ padding: "40px 20px", textAlign: "center" }}>
                        <div style={{ color: "#333", fontSize: 40, marginBottom: 12 }}>📋</div>
                        <span style={{ color: "#666", fontSize: 14, fontFamily: font, display: "block", marginBottom: 6 }}>
                            {PERIOD_LABELS[period]} 리포트가 아직 생성되지 않았습니다
                        </span>
                        <span style={{ color: "#444", fontSize: 12, fontFamily: font, display: "block" }}>
                            데이터가 충분히 누적되면 자동 생성됩니다
                        </span>
                    </div>
                )}

                {/* 푸터 */}
                <div style={footer}>
                    <span style={{ color: "#444", fontSize: 10, fontFamily: font, display: "block", lineHeight: 1.5 }}>
                        본 리포트는 VERITY AI가 자동 생성한 {PERIOD_LABELS[period]} 종합 분석이며, 투자 판단의 참고용입니다. {dateShort}
                    </span>
                    <span className="verity-report-no-print" style={{ color: "#333", fontSize: 9, fontFamily: font, display: "block", marginTop: 6 }}>
                        PDF는 매일 장 마감 full 분석 완료 후 자동 생성됩니다
                    </span>
                </div>
            </div>
        </div>
    )
}

function _MiniSpark({ data, color = "#888", w = 80, h = 20 }: { data: number[]; color?: string; w?: number; h?: number }) {
    if (!data || data.length < 2) return null
    const mn = Math.min(...data), mx = Math.max(...data), rng = mx - mn || 1
    const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - mn) / rng) * h}`).join(" ")
    return (
        <svg width={w} height={h} style={{ display: "block" }}>
            <polyline points={pts} fill="none" stroke={color} strokeWidth={1.2} strokeLinejoin="round" strokeLinecap="round" />
        </svg>
    )
}

function MacroSparklines({ macro }: { macro: any }) {
    const fred = macro?.fred || {}
    const items: { label: string; spark: number[]; color: string }[] = []
    if (fred.dgs10?.sparkline?.length > 2) items.push({ label: "US 10Y", spark: fred.dgs10.sparkline, color: "#38BDF8" })
    if (fred.vix_close?.sparkline?.length > 2) items.push({ label: "VIX", spark: fred.vix_close.sparkline, color: "#EF4444" })
    if (fred.hy_spread?.sparkline?.length > 2) items.push({ label: "HY Spread", spark: fred.hy_spread.sparkline, color: "#F59E0B" })
    if (macro.sp500?.sparkline_weekly?.length > 2) items.push({ label: "S&P 500", spark: macro.sp500.sparkline_weekly, color: "#22C55E" })
    if (macro.nasdaq?.sparkline_weekly?.length > 2) items.push({ label: "NASDAQ", spark: macro.nasdaq.sparkline_weekly, color: "#B5FF19" })
    if (macro.usd_krw?.sparkline_weekly?.length > 2) items.push({ label: "USD/KRW", spark: macro.usd_krw.sparkline_weekly, color: "#A78BFA" })
    if (items.length === 0) return null
    return (
        <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6 }}>
            {items.map((it, i) => (
                <div key={i} style={{ background: "#0A0A0A", borderRadius: 6, padding: "6px 8px" }}>
                    <span style={{ color: "#666", fontSize: 9, fontWeight: 500 }}>{it.label}</span>
                    <_MiniSpark data={it.spark.slice(-13)} color={it.color} w={70} h={18} />
                </div>
            ))}
        </div>
    )
}

function DailyReportView({ data, market, Section, MetricRow, RingGauge, gradeLabels, gradeColors }: any) {
    const report = data?.daily_report || {}
    const macro = data?.macro || {}
    const mood = macro.market_mood || {}
    const brain = data?.verity_brain || {}
    const marketBrain = brain.market_brain || {}
    const macroOv = brain.macro_override || {}
    const recs: any[] = data?.recommendations || []
    const vams = data?.vams || {}
    const sectors: any[] = data?.sectors || []
    const krHeadlines: any[] = data?.headlines || []
    const usHeadlines: any[] = data?.us_headlines || []
    const allHeadlines = [...krHeadlines, ...usHeadlines.filter((u: any) => !krHeadlines.some((k: any) => k.title === u.title))]
    const isUS = market === "us"
    const briefing = data?.briefing || {}
    const allEvents: any[] = data?.global_events || []
    const events: any[] = allEvents.filter((e) => (isUS ? _isUSEvent(e) : !_isUSEvent(e)))
    const allAlerts: any[] = briefing.alerts || []
    const usTokens = new Set<string>()
    const krTokens = new Set<string>()
    for (const r of recs) {
        const ticker = String(r?.ticker || "").trim().toLowerCase()
        const name = String(r?.name || "").trim().toLowerCase()
        const target = _isUSStock(r) ? usTokens : krTokens
        if (ticker.length >= 1) target.add(ticker)
        if (name.length >= 2) target.add(name)
    }
    const scopedAlerts: any[] = allAlerts.filter((a) => (isUS ? _isUSAlert(a, usTokens, krTokens) : !_isUSAlert(a, usTokens, krTokens)))
    const briefingHeadline = scopedAlerts[0]?.message || briefing.headline
    const briefingActions: string[] = scopedAlerts.map((a) => String(a?.action || "").trim()).filter(Boolean).slice(0, 3)
    const rotation = data?.sector_rotation || {}
    const holdings: any[] = vams.holdings || []
    const topPicks: any[] = marketBrain.top_picks || []

    const brainScore = marketBrain.avg_brain_score ?? null
    const factScore = marketBrain.avg_fact_score ?? null
    const sentScore = marketBrain.avg_sentiment_score ?? null
    const avgVci = marketBrain.avg_vci ?? 0
    const gradeDist: Record<string, number> = marketBrain.grade_distribution || {}

    const totalReturn = vams.total_return_pct || 0
    const totalAsset = vams.total_asset || 0
    const cash = vams.cash || 0

    const krRecs = recs.filter((r: any) => !_isUSStock(r))
    const usRecs = recs.filter(_isUSStock)
    const dualRows = recs.filter((r: any) => !!r.dual_consensus)
    const dualAgree = dualRows.filter((r: any) => r.dual_consensus?.agreement).length
    const dualManual = dualRows.filter((r: any) => r.dual_consensus?.manual_review_required).length
    const dualConflictHigh = dualRows.filter((r: any) => r.dual_consensus?.conflict_level === "high").length

    const _isUSSector = (s: any) => (s.market || "").toUpperCase() === "US"
    const krSectors = sectors.filter((s: any) => !_isUSSector(s))
    const usSectors = sectors.filter(_isUSSector)
    const topKrSectors = [...krSectors].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0)).slice(0, 5)
    const bottomKrSectors = [...krSectors].sort((a, b) => (a.change_pct || 0) - (b.change_pct || 0)).slice(0, 3)
    const topUsSectors = [...usSectors].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0)).slice(0, 5)
    const bottomUsSectors = [...usSectors].sort((a, b) => (a.change_pct || 0) - (b.change_pct || 0)).slice(0, 3)

    const posHeadlines = allHeadlines.filter((h) => h.sentiment === "positive").length
    const negHeadlines = allHeadlines.filter((h) => h.sentiment === "negative").length

    const hasReport = report.market_summary || report.market_analysis

    return (
        <>
            {/* 매크로 오버라이드 */}
            {macroOv.mode && (() => {
                const m = String(macroOv.mode).toLowerCase()
                const isPanic = m === "panic"
                const isYield = m === "yield_defense"
                const bg = isPanic ? "rgba(239,68,68,0.08)" : isYield ? "rgba(56,189,248,0.08)" : "rgba(234,179,8,0.08)"
                const bd = isPanic ? "#EF4444" : isYield ? "#38BDF8" : "#EAB308"
                const fg = isPanic ? "#EF4444" : isYield ? "#38BDF8" : "#EAB308"
                const title = isPanic ? "PANIC MODE" : isYield ? "YIELD DEFENSE" : "EUPHORIA MODE"
                const sub = macroOv.reason || macroOv.message || ""
                return (
                    <div style={{ padding: "10px 20px", background: bg, borderBottom: `2px solid ${bd}` }}>
                        <span style={{ color: fg, fontSize: 12, fontWeight: 800, fontFamily: font }}>{title} — {sub}</span>
                    </div>
                )
            })()}

            {hasReport && (
                <div style={{ padding: "16px 20px", background: "linear-gradient(135deg, #0A1A00, #1A2A00)", borderBottom: "1px solid #222" }}>
                    <span style={{ color: "#B5FF19", fontSize: 17, fontWeight: 800, fontFamily: font, lineHeight: "1.4" }}>{report.market_summary || "—"}</span>
                </div>
            )}

            <div style={bodyWrap}>
                {brainScore !== null && (
                    <Section icon="🧠" iconColor="#B5FF19" label="Verity Brain 종합">
                        <MetricRow items={[
                            { label: "종합 점수", value: `${brainScore}`, color: brainScore >= 65 ? "#B5FF19" : brainScore >= 45 ? "#FFD600" : "#FF4D4D" },
                            { label: "팩트", value: `${factScore ?? "—"}`, color: "#22C55E" },
                            { label: "심리", value: `${sentScore ?? "—"}`, color: "#60A5FA" },
                            { label: "VCI", value: `${avgVci >= 0 ? "+" : ""}${avgVci?.toFixed(1)}`, color: avgVci > 15 ? "#B5FF19" : avgVci < -15 ? "#FF4D4D" : "#888" },
                        ]} />
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                            {Object.entries(gradeDist).map(([g, count]) => count > 0 ? (
                                <span key={g} style={{
                                    fontSize: 10, fontWeight: 700, fontFamily: font, padding: "3px 8px", borderRadius: 4,
                                    background: `${gradeColors[g]}15`, color: gradeColors[g],
                                }}>{gradeLabels[g]} {count}</span>
                            ) : null)}
                        </div>
                        {topPicks.length > 0 && (
                            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
                                <span style={{ color: "#555", fontSize: 10, fontWeight: 600 }}>탑픽</span>
                                {topPicks.slice(0, 5).map((s: any, i: number) => (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #1A1A1A" }}>
                                        <span style={{ color: "#ccc", fontSize: 12, fontFamily: font }}>{i + 1}. {s.name}</span>
                                        <span
                                            style={{ color: gradeColors[s.grade] || "#888", fontSize: 12, fontWeight: 800, fontFamily: font, cursor: s.grade === "AVOID" ? "help" : "default" }}
                                            title={s.grade === "AVOID" ? AVOID_TOOLTIP : undefined}
                                        >{s.brain_score} · {gradeLabels[s.grade] || s.grade}{Array.isArray(s.overrides_applied) && s.overrides_applied.length > 0 ? ` · ${(s.overrides_applied as string[]).map((o) => OVERRIDE_LABELS[o] || o).join("·")}` : ""}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </Section>
                )}

                {dualRows.length > 0 && (
                    <Section icon="H" iconColor="#38BDF8" label="듀얼 모델 합의 상태">
                        <MetricRow items={[
                            { label: "합의율", value: `${Math.round((dualAgree / Math.max(dualRows.length, 1)) * 100)}%`, color: dualAgree / Math.max(dualRows.length, 1) >= 0.7 ? "#22C55E" : "#FFD600" },
                            { label: "수동검토", value: `${dualManual}종목`, color: dualManual > 0 ? "#EF4444" : "#22C55E" },
                            { label: "High 충돌", value: `${dualConflictHigh}종목`, color: dualConflictHigh > 0 ? "#EF4444" : "#888" },
                            { label: "분석대상", value: `${dualRows.length}종목`, color: "#38BDF8" },
                        ]} />
                        {dualRows
                            .filter((r: any) => r.dual_consensus?.manual_review_required)
                            .slice(0, 5)
                            .map((s: any, i: number) => {
                                const dc = s.dual_consensus || {}
                                return (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #1A1A1A" }}>
                                        <div>
                                            <span style={{ color: "#fff", fontSize: 12, fontWeight: 600, fontFamily: font }}>{s.name}</span>
                                            <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{s.ticker}</span>
                                        </div>
                                        <span style={{ color: "#EF4444", fontSize: 11, fontWeight: 700, fontFamily: font }}>
                                            G:{dc.gemini_recommendation} / C:{dc.claude_recommendation} ({dc.conflict_level})
                                        </span>
                                    </div>
                                )
                            })}
                    </Section>
                )}

                {report.market_analysis && (
                    <Section icon="A" iconColor="#60A5FA" label="시장 분석">
                        <p style={sectionText}>{report.market_analysis}</p>
                    </Section>
                )}

                <Section icon="M" iconColor="#A78BFA" label="글로벌 매크로">
                    <MetricRow items={[
                        { label: "시장 분위기", value: mood.label || "—", color: (mood.score || 50) >= 60 ? "#22C55E" : (mood.score || 50) <= 40 ? "#EF4444" : "#FFD600" },
                        { label: "VIX", value: `${macro.vix?.value || "—"}`, color: (macro.vix?.value || 0) > 25 ? "#EF4444" : "#22C55E" },
                        { label: "US 10Y", value: macro.fred?.dgs10?.value != null ? `${macro.fred.dgs10.value}%` : "—", color: "#38BDF8" },
                        { label: "USD/KRW", value: `${macro.usd_krw?.value?.toLocaleString() || "—"}원` },
                    ]} />
                    <MetricRow items={[
                        { label: "S&P 500", value: `${(macro.sp500?.change_pct || 0) >= 0 ? "+" : ""}${(macro.sp500?.change_pct || 0).toFixed(2)}%`, color: (macro.sp500?.change_pct || 0) >= 0 ? "#22C55E" : "#EF4444" },
                        { label: "NASDAQ", value: `${(macro.nasdaq?.change_pct || 0) >= 0 ? "+" : ""}${(macro.nasdaq?.change_pct || 0).toFixed(2)}%`, color: (macro.nasdaq?.change_pct || 0) >= 0 ? "#22C55E" : "#EF4444" },
                        { label: "Gold", value: `$${macro.gold?.value?.toLocaleString() || "—"}` },
                        { label: "WTI", value: `$${macro.wti_oil?.value || "—"}` },
                    ]} />
                    {/* 확장 FRED 지표 */}
                    {(macro.fred?.unemployment_rate || macro.fred?.consumer_sentiment || macro.fred?.hy_spread) && (
                        <MetricRow items={[
                            { label: "실업률", value: macro.fred?.unemployment_rate?.pct != null ? `${macro.fred.unemployment_rate.pct}%` : "—", color: (macro.fred?.unemployment_rate?.pct || 0) > 5 ? "#EF4444" : "#22C55E" },
                            { label: "소비자 심리", value: macro.fred?.consumer_sentiment?.value != null ? `${macro.fred.consumer_sentiment.value}` : "—", color: (macro.fred?.consumer_sentiment?.value || 50) >= 70 ? "#22C55E" : (macro.fred?.consumer_sentiment?.value || 50) <= 50 ? "#EF4444" : "#FFD600" },
                            { label: "HY 스프레드", value: macro.fred?.hy_spread?.pct != null ? `${macro.fred.hy_spread.pct}%` : "—", color: (macro.fred?.hy_spread?.pct || 0) > 5 ? "#EF4444" : "#22C55E" },
                            { label: "기대 인플레", value: macro.fred?.breakeven_inflation_10y?.pct != null ? `${macro.fred.breakeven_inflation_10y.pct}%` : "—" },
                        ]} />
                    )}
                    {macro.fred?.fed_balance_sheet?.trillions_usd != null && (
                        <MetricRow items={[
                            { label: "Fed B/S", value: `$${macro.fred.fed_balance_sheet.trillions_usd}T`, color: "#A78BFA" },
                            { label: "4주 변동", value: macro.fred.fed_balance_sheet.change_4w_pct != null ? `${macro.fred.fed_balance_sheet.change_4w_pct > 0 ? "+" : ""}${macro.fred.fed_balance_sheet.change_4w_pct}%` : "—", color: (macro.fred?.fed_balance_sheet?.change_4w_pct || 0) > 0 ? "#22C55E" : "#EF4444" },
                            { label: "리세션 확률", value: macro.fred?.us_recession_smoothed_prob?.pct != null ? `${macro.fred.us_recession_smoothed_prob.pct}%` : "—", color: (macro.fred?.us_recession_smoothed_prob?.pct || 0) > 20 ? "#EF4444" : "#22C55E" },
                        ]} />
                    )}
                    <MacroSparklines macro={macro} />
                </Section>

                {report.strategy && (
                    <Section icon="T" iconColor="#22C55E" label="투자 전략">
                        <p style={sectionText}>{report.strategy}</p>
                    </Section>
                )}

                {holdings.length > 0 && (
                    <Section icon="P" iconColor="#F59E0B" label="포트폴리오 현황">
                        <MetricRow items={[
                            { label: "총 자산", value: totalAsset ? `${totalAsset.toLocaleString()}원` : "—" },
                            { label: "수익률", value: `${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%`, color: totalReturn >= 0 ? "#22C55E" : "#EF4444" },
                            { label: "현금", value: cash ? `${cash.toLocaleString()}원` : "—" },
                            { label: "보유 종목", value: `${holdings.length}개` },
                        ]} />
                        {holdings.map((h: any, i: number) => {
                            const pct = h.return_pct || 0
                            return (
                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #1A1A1A" }}>
                                    <span style={{ color: "#ccc", fontSize: 12, fontFamily: font }}>{h.name} · {h.quantity}주</span>
                                    <span style={{ color: pct >= 0 ? "#22C55E" : "#EF4444", fontSize: 12, fontWeight: 700, fontFamily: font }}>{pct >= 0 ? "+" : ""}{pct.toFixed(2)}%</span>
                                </div>
                            )
                        })}
                    </Section>
                )}

                <Section icon="R" iconColor="#B5FF19" label={`추천 종목 요약 (KR ${krRecs.length} · US ${usRecs.length})`}>
                    {krRecs.length > 0 && (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                                <span style={{ padding: "2px 6px", borderRadius: 4, background: "rgba(181,255,25,0.1)", color: "#B5FF19", fontSize: 10, fontWeight: 700, fontFamily: font }}>국장</span>
                                <span style={{ color: "#888", fontSize: 10, fontFamily: font }}>
                                    매수 {krRecs.filter((r: any) => r.recommendation === "BUY").length} · 회피 {krRecs.filter((r: any) => r.recommendation === "AVOID").length}
                                </span>
                            </div>
                            {krRecs.filter((r: any) => r.recommendation === "BUY").slice(0, 5).map((s: any, i: number) => (
                                <div key={`kr-${i}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #1A1A1A" }}>
                                    <div>
                                        <span style={{ color: "#fff", fontSize: 12, fontWeight: 600, fontFamily: font }}>{s.name}</span>
                                        <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{s.ticker}</span>
                                    </div>
                                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                        <span style={{ color: "#888", fontSize: 11, fontFamily: font }}>{s.price?.toLocaleString()}원</span>
                                        <span style={{ color: "#B5FF19", fontSize: 12, fontWeight: 700, fontFamily: font }}>{s.multi_factor?.multi_score || s.safety_score || 0}점</span>
                                    </div>
                                </div>
                            ))}
                        </>
                    )}
                    {usRecs.length > 0 && (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, marginTop: krRecs.length > 0 ? 12 : 0 }}>
                                <span style={{ padding: "2px 6px", borderRadius: 4, background: "rgba(96,165,250,0.1)", color: "#60A5FA", fontSize: 10, fontWeight: 700, fontFamily: font }}>미장</span>
                                <span style={{ color: "#888", fontSize: 10, fontFamily: font }}>
                                    매수 {usRecs.filter((r: any) => r.recommendation === "BUY").length} · 회피 {usRecs.filter((r: any) => r.recommendation === "AVOID").length}
                                </span>
                            </div>
                            {usRecs.filter((r: any) => r.recommendation === "BUY").slice(0, 5).map((s: any, i: number) => (
                                <div key={`us-${i}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #1A1A1A" }}>
                                    <div>
                                        <span style={{ color: "#fff", fontSize: 12, fontWeight: 600, fontFamily: font }}>{s.name}</span>
                                        <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{s.ticker}</span>
                                    </div>
                                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                        <span style={{ color: "#888", fontSize: 11, fontFamily: font }}>${s.price?.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                                        <span style={{ color: "#60A5FA", fontSize: 12, fontWeight: 700, fontFamily: font }}>{s.multi_factor?.multi_score || s.safety_score || 0}점</span>
                                    </div>
                                </div>
                            ))}
                        </>
                    )}
                    {krRecs.length === 0 && usRecs.length === 0 && (
                        <span style={{ color: "#555", fontSize: 12, fontFamily: font }}>추천 종목 없음</span>
                    )}
                </Section>

                {sectors.length > 0 && (
                    <Section icon="S" iconColor="#A78BFA" label="섹터 동향">
                        {krSectors.length > 0 && (
                            <>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                                    <span style={{ padding: "2px 6px", borderRadius: 4, background: "rgba(181,255,25,0.1)", color: "#B5FF19", fontSize: 10, fontWeight: 700, fontFamily: font }}>국장</span>
                                </div>
                                <div style={{ display: "flex", gap: 8 }}>
                                    <div style={{ flex: 1 }}>
                                        <span style={{ color: "#22C55E", fontSize: 10, fontWeight: 700, display: "block", marginBottom: 6 }}>상승 TOP</span>
                                        {topKrSectors.map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #1A1A1A" }}>
                                                <span style={{ color: "#ccc", fontSize: 11, fontFamily: font }}>{s.name}</span>
                                                <span style={{ color: "#22C55E", fontSize: 11, fontWeight: 700, fontFamily: font }}>+{(s.change_pct || 0).toFixed(2)}%</span>
                                            </div>
                                        ))}
                                    </div>
                                    <div style={{ width: 1, background: "#222" }} />
                                    <div style={{ flex: 1 }}>
                                        <span style={{ color: "#EF4444", fontSize: 10, fontWeight: 700, display: "block", marginBottom: 6 }}>하락 TOP</span>
                                        {bottomKrSectors.map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #1A1A1A" }}>
                                                <span style={{ color: "#888", fontSize: 11, fontFamily: font }}>{s.name}</span>
                                                <span style={{ color: "#EF4444", fontSize: 11, fontWeight: 700, fontFamily: font }}>{(s.change_pct || 0).toFixed(2)}%</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </>
                        )}
                        {usSectors.length > 0 && (
                            <>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, marginTop: krSectors.length > 0 ? 14 : 0 }}>
                                    <span style={{ padding: "2px 6px", borderRadius: 4, background: "rgba(96,165,250,0.1)", color: "#60A5FA", fontSize: 10, fontWeight: 700, fontFamily: font }}>미장</span>
                                </div>
                                <div style={{ display: "flex", gap: 8 }}>
                                    <div style={{ flex: 1 }}>
                                        <span style={{ color: "#22C55E", fontSize: 10, fontWeight: 700, display: "block", marginBottom: 6 }}>상승 TOP</span>
                                        {topUsSectors.map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #1A1A1A" }}>
                                                <span style={{ color: "#ccc", fontSize: 11, fontFamily: font }}>{s.name}</span>
                                                <span style={{ color: "#22C55E", fontSize: 11, fontWeight: 700, fontFamily: font }}>+{(s.change_pct || 0).toFixed(2)}%</span>
                                            </div>
                                        ))}
                                    </div>
                                    <div style={{ width: 1, background: "#222" }} />
                                    <div style={{ flex: 1 }}>
                                        <span style={{ color: "#EF4444", fontSize: 10, fontWeight: 700, display: "block", marginBottom: 6 }}>하락 TOP</span>
                                        {bottomUsSectors.map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #1A1A1A" }}>
                                                <span style={{ color: "#888", fontSize: 11, fontFamily: font }}>{s.name}</span>
                                                <span style={{ color: "#EF4444", fontSize: 11, fontWeight: 700, fontFamily: font }}>{(s.change_pct || 0).toFixed(2)}%</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </>
                        )}
                        {rotation.cycle_label && (
                            <div style={{ marginTop: 8, background: "#111", borderRadius: 8, padding: "8px 12px", border: "1px solid #222" }}>
                                <span style={{ color: "#A78BFA", fontSize: 11, fontWeight: 700, fontFamily: font }}>섹터 전략: {rotation.cycle_label}</span>
                                {rotation.cycle_desc && <p style={{ color: "#888", fontSize: 11, lineHeight: "1.5", margin: "4px 0 0", fontFamily: font }}>{rotation.cycle_desc}</p>}
                            </div>
                        )}
                    </Section>
                )}

                {report.risk_watch && (
                    <Section icon="!" iconColor="#EF4444" label="리스크 주의">
                        <p style={sectionText}>{report.risk_watch}</p>
                    </Section>
                )}

                {allHeadlines.length > 0 && (
                    <Section icon="N" iconColor="#60A5FA" label={`뉴스 요약 (호재 ${posHeadlines} / 악재 ${negHeadlines})`}>
                        {krHeadlines.slice(0, 4).map((h: any, i: number) => {
                            const sc = h.sentiment === "positive" ? "#22C55E" : h.sentiment === "negative" ? "#EF4444" : "#888"
                            return (
                                <div key={`kr-${i}`} style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "5px 0", borderBottom: "1px solid #1A1A1A" }}>
                                    <span style={{ width: 6, height: 6, borderRadius: 3, background: sc, marginTop: 5, flexShrink: 0 }} />
                                    <span style={{ color: "#ccc", fontSize: 11, lineHeight: "1.5", fontFamily: font }}>{h.title}</span>
                                </div>
                            )
                        })}
                        {usHeadlines.length > 0 && (
                            <>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, margin: "8px 0 4px" }}>
                                    <span style={{ padding: "2px 6px", borderRadius: 4, background: "rgba(96,165,250,0.1)", color: "#60A5FA", fontSize: 9, fontWeight: 700, fontFamily: font }}>US</span>
                                </div>
                                {usHeadlines.slice(0, 4).map((h: any, i: number) => {
                                    const sc = h.sentiment === "positive" ? "#22C55E" : h.sentiment === "negative" ? "#EF4444" : "#888"
                                    return (
                                        <div key={`us-${i}`} style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "5px 0", borderBottom: "1px solid #1A1A1A" }}>
                                            <span style={{ width: 6, height: 6, borderRadius: 3, background: sc, marginTop: 5, flexShrink: 0 }} />
                                            <span style={{ color: "#ccc", fontSize: 11, lineHeight: "1.5", fontFamily: font }}>{h.title}</span>
                                        </div>
                                    )
                                })}
                            </>
                        )}
                    </Section>
                )}

                {report.hot_theme && (
                    <Section icon="H" iconColor="#F59E0B" label="주목 테마">
                        <p style={sectionText}>{report.hot_theme}</p>
                    </Section>
                )}

                {events.filter((e: any) => (e.d_day ?? 99) <= 14).length > 0 && (
                    <Section icon="E" iconColor="#A855F7" label="주요 이벤트">
                        {events.filter((e: any) => (e.d_day ?? 99) <= 14).slice(0, 5).map((e: any, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #1A1A1A" }}>
                                <div style={{ flex: 1 }}>
                                    <span style={{ color: "#ccc", fontSize: 12, fontFamily: font }}>{e.name}</span>
                                    {e.impact && <div style={{ color: "#666", fontSize: 10, marginTop: 2 }}>{e.impact}</div>}
                                </div>
                                <span style={{ color: "#A855F7", fontSize: 11, fontWeight: 700, fontFamily: font, flexShrink: 0 }}>D-{e.d_day ?? "?"}</span>
                            </div>
                        ))}
                    </Section>
                )}

                {briefingHeadline && (
                    <Section icon="V" iconColor="#FFD700" label="비서의 한마디">
                        <p style={{ ...sectionText, color: "#FFD700", fontWeight: 600 }}>{briefingHeadline}</p>
                        {briefingActions.length > 0 && (
                            <div style={{ marginTop: 6 }}>
                                {briefingActions.map((a: string, i: number) => (
                                    <div key={i} style={{ color: "#ccc", fontSize: 12, lineHeight: "1.6", fontFamily: font }}>→ {a}</div>
                                ))}
                            </div>
                        )}
                    </Section>
                )}

                {report.tomorrow_outlook && (
                    <Section icon="→" iconColor="#A78BFA" label="향후 전망">
                        <p style={sectionText}>{report.tomorrow_outlook}</p>
                    </Section>
                )}

                {/* 저평가 발굴 (Value Hunter) */}
                {data?.value_hunt?.gate_open && Array.isArray(data.value_hunt.value_candidates) && data.value_hunt.value_candidates.length > 0 && (
                    <Section icon="V" iconColor="#22D3EE" label={`저평가 발굴 (${data.value_hunt.value_candidates.length}종목)`}>
                        <p style={{ color: "#22D3EE", fontSize: 11, fontWeight: 600, fontFamily: font, margin: "0 0 8px" }}>{data.value_hunt.gate_reason || ""}</p>
                        {data.value_hunt.value_candidates.slice(0, 5).map((vc: any, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #1A1A1A" }}>
                                <span style={{ color: "#ccc", fontSize: 12, fontFamily: font }}>{vc.name || vc.ticker}</span>
                                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                    {typeof vc.value_score === "number" && <span style={{ color: "#22D3EE", fontSize: 11, fontWeight: 700, fontFamily: font }}>{vc.value_score}점</span>}
                                    {typeof vc.per === "number" && <span style={{ color: "#888", fontSize: 10, fontFamily: font }}>PER {vc.per.toFixed(1)}</span>}
                                </div>
                            </div>
                        ))}
                    </Section>
                )}

                {/* AI 포스트모텀 */}
                {data?.postmortem?.failures && data.postmortem.failures.length > 0 && (
                    <Section icon="X" iconColor="#F87171" label={`AI 오심 분석 (${data.postmortem.analyzed_count || data.postmortem.failures.length}건)`}>
                        {data.postmortem.lesson && <p style={{ ...sectionText, color: "#F87171" }}>{data.postmortem.lesson}</p>}
                        {data.postmortem.system_suggestion && <p style={{ ...sectionText, color: "#FBBF24", marginTop: 6 }}>개선: {data.postmortem.system_suggestion}</p>}
                        {data.postmortem.failures.slice(0, 3).map((f: any, i: number) => (
                            <div key={i} style={{ padding: "6px 0", borderBottom: "1px solid #1A1A1A" }}>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "#ccc", fontSize: 12, fontFamily: font }}>{f.name || f.ticker || "?"}</span>
                                    <span style={{ color: "#F87171", fontSize: 11, fontWeight: 700, fontFamily: font }}>{f.recommendation || ""} → {typeof f.actual_return_pct === "number" ? `${f.actual_return_pct.toFixed(1)}%` : "?"}</span>
                                </div>
                                {f.reason && <div style={{ color: "#888", fontSize: 10, marginTop: 2 }}>{f.reason}</div>}
                            </div>
                        ))}
                    </Section>
                )}

                {/* 팩터 IC 순위 */}
                {data?.factor_ic?.ranking?.length > 0 && (() => {
                    const ic = data.factor_ic
                    const ranking = ic.ranking || []
                    const monthly = ic.monthly_rollup || {}
                    const mFactors = monthly.by_factor || []
                    const thStyle: React.CSSProperties = { padding: "4px 6px", textAlign: "left", fontSize: 10, fontWeight: 700, color: "#555", borderBottom: "1px solid #1A1A1A" }
                    const tdStyle: React.CSSProperties = { padding: "3px 6px", fontSize: 11, borderBottom: "1px solid #111" }
                    const sigFactors = ic.significant_factors || []
                    const decFactors = ic.decaying_factors || []

                    return (
                        <Section icon="Q" iconColor="#60A5FA" label="팩터 예측력 순위">
                            <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                <thead>
                                    <tr>
                                        <th style={thStyle}>#</th>
                                        <th style={thStyle}>팩터</th>
                                        <th style={{ ...thStyle, textAlign: "right" }}>ICIR</th>
                                        <th style={{ ...thStyle, textAlign: "center" }}>상태</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {ranking.slice(0, 8).map((r: any, i: number) => (
                                        <tr key={i}>
                                            <td style={{ ...tdStyle, color: "#555", fontSize: 10 }}>{i + 1}</td>
                                            <td style={{ ...tdStyle, color: "#ccc" }}>{r.factor}</td>
                                            <td style={{ ...tdStyle, textAlign: "right", color: Math.abs(r.icir) > 0.5 ? "#B5FF19" : "#888", fontWeight: 700 }}>{r.icir?.toFixed(3)}</td>
                                            <td style={{ ...tdStyle, textAlign: "center", fontSize: 9 }}>
                                                {decFactors.includes(r.factor) && <span style={{ color: "#FF4D4D" }}>붕괴</span>}
                                                {sigFactors.includes(r.factor) && !decFactors.includes(r.factor) && <span style={{ color: "#B5FF19" }}>유의미</span>}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {mFactors.length > 0 && (
                                <div style={{ marginTop: 10 }}>
                                    <span style={{ color: "#555", fontSize: 10, fontWeight: 600 }}>{monthly.period_label || "월간"} 평균 ({monthly.obs_entries || 0}일)</span>
                                    <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 4 }}>
                                        <thead>
                                            <tr>
                                                <th style={thStyle}>#</th>
                                                <th style={thStyle}>팩터</th>
                                                <th style={{ ...thStyle, textAlign: "right" }}>평균 ICIR</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {mFactors.slice(0, 5).map((f: any, i: number) => (
                                                <tr key={i}>
                                                    <td style={{ ...tdStyle, color: "#555", fontSize: 10 }}>{i + 1}</td>
                                                    <td style={{ ...tdStyle, color: "#ccc" }}>{f.factor}</td>
                                                    <td style={{ ...tdStyle, textAlign: "right", color: Math.abs(f.avg_icir) > 0.5 ? "#B5FF19" : "#888", fontWeight: 700 }}>{f.avg_icir?.toFixed(3)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </Section>
                    )
                })()}

                {/* AI 소스별 리더보드 */}
                {data?.ai_leaderboard?.by_source?.length > 0 && (() => {
                    const lb = data.ai_leaderboard
                    const sources = lb.by_source || []
                    const thStyle: React.CSSProperties = { padding: "4px 6px", textAlign: "left", fontSize: 10, fontWeight: 700, color: "#555", borderBottom: "1px solid #1A1A1A" }
                    const tdStyle: React.CSSProperties = { padding: "4px 6px", fontSize: 11, borderBottom: "1px solid #111" }
                    const sourceLabel: Record<string, string> = { gemini: "Gemini", claude: "Claude", gemini_disputed: "Gemini (이견)" }

                    return (
                        <Section icon="AI" iconColor="#F59E0B" label={`AI 소스별 성과 (${lb.window_days || 30}일)`}>
                            <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                <thead>
                                    <tr>
                                        <th style={thStyle}>소스</th>
                                        <th style={{ ...thStyle, textAlign: "right" }}>추천 수</th>
                                        <th style={{ ...thStyle, textAlign: "right" }}>적중률</th>
                                        <th style={{ ...thStyle, textAlign: "right" }}>평균 수익</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {sources.map((s: any, i: number) => (
                                        <tr key={i}>
                                            <td style={{ ...tdStyle, color: "#ccc", fontWeight: 600 }}>{sourceLabel[s.source] || s.source}</td>
                                            <td style={{ ...tdStyle, textAlign: "right", color: "#888" }}>{s.n}건</td>
                                            <td style={{ ...tdStyle, textAlign: "right", color: s.hit_rate >= 60 ? "#B5FF19" : s.hit_rate >= 40 ? "#FFD600" : "#FF4D4D", fontWeight: 700 }}>{s.hit_rate}%</td>
                                            <td style={{ ...tdStyle, textAlign: "right", color: s.avg_return >= 0 ? "#B5FF19" : "#FF4D4D", fontWeight: 700 }}>{s.avg_return > 0 ? "+" : ""}{s.avg_return}%</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {lb.suggested_note && (
                                <p style={{ color: "#888", fontSize: 10, marginTop: 8, lineHeight: "1.5", fontFamily: font }}>
                                    {lb.suggested_note}
                                </p>
                            )}
                            <p style={{ color: "#555", fontSize: 9, marginTop: 4, fontFamily: font }}>
                                모델 전환은 수동으로 진행하세요 (.env GEMINI_MODEL / ANTHROPIC 설정)
                            </p>
                        </Section>
                    )
                })()}

                {/* 전략 진화 */}
                {data?.strategy_evolution && data.strategy_evolution.status && data.strategy_evolution.status !== "no_change" && (
                    <Section icon="⚙" iconColor="#A78BFA" label="전략 진화">
                        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                            <span style={{ padding: "3px 8px", borderRadius: 4, fontSize: 10, fontWeight: 700, fontFamily: font, background: data.strategy_evolution.status === "auto_applied" ? "rgba(34,197,94,0.15)" : "rgba(234,179,8,0.12)", color: data.strategy_evolution.status === "auto_applied" ? "#22C55E" : "#EAB308" }}>
                                {data.strategy_evolution.status === "auto_applied" ? "자동 적용" : data.strategy_evolution.status === "pending_approval" ? "승인 대기" : data.strategy_evolution.status}
                            </span>
                            {data.strategy_evolution.new_version && <span style={{ color: "#888", fontSize: 10, fontFamily: font }}>v{data.strategy_evolution.new_version}</span>}
                        </div>
                        {data.strategy_evolution.reason && <p style={sectionText}>{data.strategy_evolution.reason}</p>}
                        {data.strategy_evolution.summary && <p style={sectionText}>{data.strategy_evolution.summary}</p>}
                    </Section>
                )}

                {/* 실적 캘린더 요약 */}
                {recs.some((r: any) => r.earnings?.next_earnings) && (
                    <Section icon="📅" iconColor="#F59E0B" label="실적 발표 예정">
                        {recs.filter((r: any) => r.earnings?.next_earnings).slice(0, 5).map((r: any, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0", borderBottom: "1px solid #1A1A1A" }}>
                                <span style={{ color: "#ccc", fontSize: 12, fontFamily: font }}>{r.name}</span>
                                <span style={{ color: "#F59E0B", fontSize: 11, fontWeight: 700, fontFamily: font }}>{r.earnings.next_earnings}</span>
                            </div>
                        ))}
                    </Section>
                )}
            </div>
        </>
    )
}

VerityReport.defaultProps = { dataUrl: DATA_URL, market: "kr" }
addPropertyControls(VerityReport, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: DATA_URL,
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})

const card: React.CSSProperties = {
    width: "100%",
    background: "#0A0A0A",
    borderRadius: 16,
    border: "1px solid #222",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: font,
}

const periodBar: React.CSSProperties = {
    display: "flex",
    gap: 4,
    padding: "12px 16px",
    borderBottom: "1px solid #222",
    overflowX: "auto",
}

const periodBtn: React.CSSProperties = {
    border: "none",
    borderRadius: 8,
    padding: "7px 16px",
    fontSize: 12,
    fontWeight: 700,
    fontFamily: font,
    cursor: "pointer",
    transition: "all 0.2s",
    whiteSpace: "nowrap",
    flexShrink: 0,
}

const header: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    padding: "16px 20px",
    borderBottom: "1px solid #222",
}

const pdfBtn: React.CSSProperties = {
    background: "#0D1A00",
    border: "1px solid #B5FF19",
    color: "#B5FF19",
    fontSize: 11,
    fontWeight: 700,
    fontFamily: font,
    padding: "6px 14px",
    borderRadius: 8,
    cursor: "pointer",
    whiteSpace: "nowrap",
}

const aiBadge: React.CSSProperties = {
    color: "#B5FF19",
    fontSize: 9,
    fontWeight: 700,
    fontFamily: font,
    background: "#0D1A00",
    border: "1px solid #1A2A00",
    padding: "4px 8px",
    borderRadius: 4,
    whiteSpace: "nowrap",
}

const bodyWrap: React.CSSProperties = {
    padding: "12px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
}

const sectionWrap: React.CSSProperties = {
    padding: "12px 14px",
    background: "#111",
    borderRadius: 12,
    border: "1px solid #1A1A1A",
}

const sectionText: React.CSSProperties = {
    color: "#ccc",
    fontSize: 13,
    lineHeight: "1.65",
    margin: 0,
    fontFamily: font,
}

const metricGrid: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "repeat(4, 1fr)",
    gap: 6,
    marginBottom: 4,
}

const metricCell: React.CSSProperties = {
    background: "#0A0A0A",
    borderRadius: 8,
    padding: "8px 10px",
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const footer: React.CSSProperties = {
    padding: "10px 16px 14px",
    borderTop: "1px solid #1A1A1A",
}

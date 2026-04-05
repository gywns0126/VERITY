import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState, useRef } from "react"

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

interface Props { dataUrl: string }

export default function VerityReport(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [period, setPeriod] = useState<Period>("daily")
    const reportRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.text())
            .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 200, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#999", fontSize: 14, fontFamily: font }}>리포트 로딩 중...</span>
            </div>
        )
    }

    const openPrintForPdf = () => { try { window.print() } catch (e) { console.error(e) } }

    const gradeLabels: Record<string, string> = { STRONG_BUY: "강력매수", BUY: "매수", WATCH: "관망", CAUTION: "주의", AVOID: "회피" }
    const gradeColors: Record<string, string> = { STRONG_BUY: "#22C55E", BUY: "#B5FF19", WATCH: "#FFD600", CAUTION: "#F59E0B", AVOID: "#EF4444" }

    const updated = data?.updated_at
        ? new Date(data.updated_at).toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric", weekday: "long" })
        : "—"
    const dateShort = data?.updated_at
        ? new Date(data.updated_at).toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" })
        : ""

    const SectionIcon = ({ icon, color }: { icon: string; color: string }) => (
        <div style={{
            width: 28, height: 28, borderRadius: 6,
            background: `${color}20`, border: `1px solid ${color}40`,
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        }}>
            <span style={{ color, fontSize: 12, fontWeight: 800, fontFamily: font }}>{icon}</span>
        </div>
    )

    const Section = ({ icon, iconColor, label, children }: { icon: string; iconColor: string; label: string; children: React.ReactNode }) => (
        <div style={sectionWrap}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                <SectionIcon icon={icon} color={iconColor} />
                <span style={{ color: iconColor, fontSize: 12, fontWeight: 700, fontFamily: font }}>{label}</span>
            </div>
            {children}
        </div>
    )

    const MetricRow = ({ items }: { items: { label: string; value: string; color?: string }[] }) => (
        <div style={metricGrid}>
            {items.map((m, i) => (
                <div key={i} style={metricCell}>
                    <span style={{ color: "#666", fontSize: 9, fontWeight: 500 }}>{m.label}</span>
                    <span style={{ color: m.color || "#fff", fontSize: 13, fontWeight: 700 }}>{m.value}</span>
                </div>
            ))}
        </div>
    )

    const RingGauge = ({ value, label, size = 56, color }: { value: number; label: string; size?: number; color: string }) => {
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

    const BarChart = ({ items, maxValue }: { items: { label: string; value: number; color: string }[]; maxValue?: number }) => {
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
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <button type="button" className="verity-report-no-print" title="인쇄 창에서 대상을 'PDF로 저장'으로 선택하세요" onClick={openPrintForPdf} style={pdfBtn}>PDF 저장</button>
                        <span style={aiBadge}>GEMINI + BRAIN</span>
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
                                        multi_factor: "멀티팩터", consensus: "컨센서스", timing: "타이밍",
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
                                            <span style={{ color: gradeColors[grade] || "#888", fontSize: 10, fontWeight: 700, fontFamily: font }}>{gradeLabels[grade] || grade}</span>
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
                    <DailyReportView data={data} Section={Section} MetricRow={MetricRow} RingGauge={RingGauge} gradeLabels={gradeLabels} gradeColors={gradeColors} />
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
                        PDF 저장: 상단 버튼 클릭 → 인쇄 창에서 저장 대상을 PDF로 선택
                    </span>
                </div>
            </div>
        </div>
    )
}

function DailyReportView({ data, Section, MetricRow, RingGauge, gradeLabels, gradeColors }: any) {
    const report = data?.daily_report || {}
    const macro = data?.macro || {}
    const mood = macro.market_mood || {}
    const brain = data?.verity_brain || {}
    const marketBrain = brain.market_brain || {}
    const macroOv = brain.macro_override || {}
    const recs: any[] = data?.recommendations || []
    const vams = data?.vams || {}
    const sectors: any[] = data?.sectors || []
    const headlines: any[] = data?.headlines || []
    const briefing = data?.briefing || {}
    const events: any[] = data?.global_events || []
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

    const buyCount = recs.filter((r) => r.recommendation === "BUY").length
    const avoidCount = recs.filter((r) => r.recommendation === "AVOID").length
    const topSectors = [...sectors].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0)).slice(0, 5)
    const bottomSectors = [...sectors].sort((a, b) => (a.change_pct || 0) - (b.change_pct || 0)).slice(0, 3)
    const posHeadlines = headlines.filter((h) => h.sentiment === "positive").length
    const negHeadlines = headlines.filter((h) => h.sentiment === "negative").length

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
                                        <span style={{ color: gradeColors[s.grade] || "#888", fontSize: 12, fontWeight: 800, fontFamily: font }}>{s.brain_score} · {gradeLabels[s.grade] || s.grade}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </Section>
                )}

                {report.market_analysis && (
                    <Section icon="A" iconColor="#60A5FA" label="시장 분석">
                        <p style={sectionText}>{report.market_analysis}</p>
                    </Section>
                )}

                <Section icon="M" iconColor="#A78BFA" label="매크로 지표">
                    <MetricRow items={[
                        { label: "시장 분위기", value: mood.label || "—", color: (mood.score || 50) >= 60 ? "#22C55E" : (mood.score || 50) <= 40 ? "#EF4444" : "#FFD600" },
                        { label: "FRED DGS10", value: macro.fred?.dgs10?.value != null ? `${macro.fred.dgs10.value}%` : "—", color: "#38BDF8" },
                        { label: "VIX", value: `${macro.vix?.value || "—"}`, color: (macro.vix?.value || 0) > 25 ? "#EF4444" : "#22C55E" },
                        { label: "USD/KRW", value: `${macro.usd_krw?.value?.toLocaleString() || "—"}원` },
                    ]} />
                    <MetricRow items={[
                        { label: "S&P500", value: `${(macro.sp500?.change_pct || 0) >= 0 ? "+" : ""}${(macro.sp500?.change_pct || 0).toFixed(2)}%`, color: (macro.sp500?.change_pct || 0) >= 0 ? "#22C55E" : "#EF4444" },
                        { label: "NASDAQ", value: `${(macro.nasdaq?.change_pct || 0) >= 0 ? "+" : ""}${(macro.nasdaq?.change_pct || 0).toFixed(2)}%`, color: (macro.nasdaq?.change_pct || 0) >= 0 ? "#22C55E" : "#EF4444" },
                        { label: "금", value: `$${macro.gold?.value?.toLocaleString() || "—"}` },
                        { label: "WTI", value: `$${macro.wti_oil?.value || "—"}` },
                    ]} />
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

                <Section icon="R" iconColor="#B5FF19" label={`추천 종목 요약 (${recs.length}개)`}>
                    <MetricRow items={[
                        { label: "매수", value: `${buyCount}종목`, color: "#B5FF19" },
                        { label: "관망", value: `${recs.length - buyCount - avoidCount}종목`, color: "#FFD600" },
                        { label: "회피", value: `${avoidCount}종목`, color: "#EF4444" },
                    ]} />
                    {recs.filter((r) => r.recommendation === "BUY").slice(0, 5).map((s: any, i: number) => (
                        <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #1A1A1A" }}>
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
                </Section>

                {sectors.length > 0 && (
                    <Section icon="S" iconColor="#A78BFA" label="섹터 동향">
                        <div style={{ display: "flex", gap: 8 }}>
                            <div style={{ flex: 1 }}>
                                <span style={{ color: "#22C55E", fontSize: 10, fontWeight: 700, display: "block", marginBottom: 6 }}>상승 TOP</span>
                                {topSectors.map((s: any, i: number) => (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #1A1A1A" }}>
                                        <span style={{ color: "#ccc", fontSize: 11, fontFamily: font }}>{s.name}</span>
                                        <span style={{ color: "#22C55E", fontSize: 11, fontWeight: 700, fontFamily: font }}>+{(s.change_pct || 0).toFixed(2)}%</span>
                                    </div>
                                ))}
                            </div>
                            <div style={{ width: 1, background: "#222" }} />
                            <div style={{ flex: 1 }}>
                                <span style={{ color: "#EF4444", fontSize: 10, fontWeight: 700, display: "block", marginBottom: 6 }}>하락 TOP</span>
                                {bottomSectors.map((s: any, i: number) => (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #1A1A1A" }}>
                                        <span style={{ color: "#888", fontSize: 11, fontFamily: font }}>{s.name}</span>
                                        <span style={{ color: "#EF4444", fontSize: 11, fontWeight: 700, fontFamily: font }}>{(s.change_pct || 0).toFixed(2)}%</span>
                                    </div>
                                ))}
                            </div>
                        </div>
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

                {headlines.length > 0 && (
                    <Section icon="N" iconColor="#60A5FA" label={`뉴스 요약 (호재 ${posHeadlines} / 악재 ${negHeadlines})`}>
                        {headlines.slice(0, 6).map((h: any, i: number) => {
                            const sc = h.sentiment === "positive" ? "#22C55E" : h.sentiment === "negative" ? "#EF4444" : "#888"
                            return (
                                <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "5px 0", borderBottom: "1px solid #1A1A1A" }}>
                                    <span style={{ width: 6, height: 6, borderRadius: 3, background: sc, marginTop: 5, flexShrink: 0 }} />
                                    <span style={{ color: "#ccc", fontSize: 11, lineHeight: "1.5", fontFamily: font }}>{h.title}</span>
                                </div>
                            )
                        })}
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

                {briefing.headline && (
                    <Section icon="V" iconColor="#FFD700" label="비서의 한마디">
                        <p style={{ ...sectionText, color: "#FFD700", fontWeight: 600 }}>{briefing.headline}</p>
                        {briefing.action_items?.length > 0 && (
                            <div style={{ marginTop: 6 }}>
                                {briefing.action_items.map((a: string, i: number) => (
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
            </div>
        </>
    )
}

VerityReport.defaultProps = { dataUrl: DATA_URL }
addPropertyControls(VerityReport, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: DATA_URL,
    },
})

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

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

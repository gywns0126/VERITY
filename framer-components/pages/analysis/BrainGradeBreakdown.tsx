// Framer canvas mirror — codeFile/OUAKBZw (BrainGradeBreakdown.tsx)
// source-of-truth: Framer canvas. 본 파일 = 로컬 grep / audit 용 mirror.
// 변경 시: Framer MCP updateCodeFile 가 SoT, 이 파일은 post-update mirror sync.
// [[feedback_framer_stubs_permanent]] 정합 — publish 깨지면 즉시 git checkout 복원.
import * as React from "react"
import { addPropertyControls, ControlType } from "framer"

interface Component {
    name: string
    score: number
    status?: string
}

interface Props {
    apiUrl: string
    portfolioUrl: string
    showIcDead: boolean
    defaultTicker: string
}

interface BrainData {
    ticker: string
    name: string
    brain_score: number
    grade: string
    grade_label: string
    fact_score: number
    sentiment_score: number
    fact_contribution: number
    sentiment_contribution: number
    bonus: number
    penalty: number
    fact_components: Component[]
    sentiment_components: Component[]
    ic_dead: string[]
    regime: string
    // 2026-05-27 v2 — footnote 동적 산출
    validation_days?: number
    validation_target?: number
    validation_sample?: number
    vams_reset_at?: string
    vams_days_since_reset?: number
}

interface TickerOption {
    ticker: string
    name: string
}

/**
 * BrainGradeBreakdown — Prospero drill-down (self-contained dynamic).
 * source: [[project_prospero_component_grade_2026_05_27]]
 * v2 (2026-05-27): footnote 동적화 — endpoint 의 validation_days /
 *   validation_target / validation_sample / vams_days_since_reset 반영.
 *   옛 "N=14 / reset 후 0일" static drift 회복.
 * v3 (2026-06-06): stale defaultTicker desync fix — 추천 rotation 에서 빠진
 *   ticker 가 selected 에 남아 404 나던 결함을 첫 유효 ticker self-heal 로 해결.
 */
export default function BrainGradeBreakdown(props: Props) {
    const { apiUrl, portfolioUrl, showIcDead, defaultTicker } = props
    const [tickers, setTickers] = React.useState<TickerOption[]>([])
    const [selected, setSelected] = React.useState<string>(defaultTicker)
    const [data, setData] = React.useState<BrainData | null>(null)
    const [error, setError] = React.useState<string | null>(null)
    const [loading, setLoading] = React.useState<boolean>(false)

    React.useEffect(() => {
        fetch(portfolioUrl)
            .then((r) => r.json())
            .then((d) => {
                const recs = (d?.recommendations || []) as any[]
                const opts: TickerOption[] = recs.map((r) => ({
                    ticker: String(r.ticker || ""),
                    name: String(r.name || r.ticker || ""),
                }))
                setTickers(opts)
                // self-heal: selected 가 현 추천 세트에 없으면 (rotation 으로 빠진
                // stale defaultTicker 등) 첫 유효 ticker 로 교정. <select> value 가
                // 옵션에 없으면 브라우저가 첫 옵션을 표시하지만 state 는 stale 유지 →
                // 표시(BRK-B)와 breakdown fetch(stale) 불일치 + 404 발생. 이를 차단.
                setSelected((cur) =>
                    opts.some((o) => o.ticker === cur) ? cur : (opts[0]?.ticker || "")
                )
            })
            .catch((e) => setError("portfolio: " + String(e)))
    }, [portfolioUrl])

    React.useEffect(() => {
        if (!selected) return
        setLoading(true)
        setError(null)
        // Vercel Python wrapper 는 비-200 status 에도 정상 JSON body 를 반환할 수 있음.
        // status 무시, body 를 parse 한 후 error 키만 확인.
        fetch(apiUrl + "?ticker=" + encodeURIComponent(selected))
            .then((r) => r.json())
            .then((d) => {
                if (d?.error) throw new Error(d.error)
                setData(d)
                setLoading(false)
            })
            .catch((e) => {
                setError("breakdown: " + String(e))
                setLoading(false)
            })
    }, [selected, apiUrl])

    const grade = data?.grade || ""
    const gradeColor =
        grade === "BUY" ? "#7fffa0" :
        grade === "HOLD" || grade === "CAUTION" ? "#ffa05a" :
        grade === "AVOID" ? "#ff5a5a" : "#6b7280"

    // Footnote 동적 산출 — endpoint v2 필드 부재 시 fallback (옛 static 유지)
    const phaseDays = data?.validation_days
    const phaseTarget = data?.validation_target || 90
    const phaseSample = data?.validation_sample
    const vamsDays = data?.vams_days_since_reset
    const vamsResetAt = data?.vams_reset_at || ""
    const vamsResetShort = vamsResetAt ? vamsResetAt.slice(0, 10) : "2026-05-17"
    const phaseLine =
        phaseDays !== undefined && phaseDays !== null
            ? `가설 단계 (Phase 0 N=${phaseDays}/${phaseTarget}일 · 표본 ${phaseSample ?? 0}건 · VAMS reset ${vamsResetShort} 후 ${vamsDays ?? 0}일)`
            : "가설 단계 (Phase 0 누적 측정 중 · 365일 trail 도달 ~2027-05)"

    return (
        <div style={containerStyle}>
            <div style={selectorRowStyle}>
                <span style={labelStyle}>SELECT TICKER</span>
                <select
                    value={selected}
                    onChange={(e) => setSelected(e.target.value)}
                    style={selectStyle}
                >
                    {tickers.map((t) => (
                        <option key={t.ticker} value={t.ticker}>
                            {t.ticker} · {t.name}
                        </option>
                    ))}
                </select>
            </div>

            {error && <div style={errorStyle}>error: {error}</div>}
            {loading && !data && <div style={loadingStyle}>loading {selected}...</div>}

            {data && (
                <>
                    <div style={headerStyle}>
                        <div>
                            <div style={labelStyle}>BRAIN SCORE</div>
                            <div style={{ ...numberStyle, color: gradeColor }}>
                                {Math.round(data.brain_score)}
                            </div>
                            <div style={{ fontSize: 14, color: gradeColor, marginTop: 4 }}>
                                {data.grade} · {data.grade_label}
                            </div>
                        </div>
                        <div style={{ textAlign: "right" }}>
                            <div style={labelStyle}>{data.name}</div>
                            <div style={{ fontSize: 13, color: "#6b7280" }}>{data.ticker}</div>
                            <div style={{ fontSize: 12, color: "#6b7280", marginTop: 8 }}>
                                regime: {data.regime}
                            </div>
                        </div>
                    </div>

                    <div style={breakdownStyle}>
                        <div style={labelStyle}>Score Composition</div>
                        <div style={{ display: "flex", marginTop: 8, gap: 2 }}>
                            <Bar label="fact" value={data.fact_contribution} color="#7fffa0" />
                            <Bar label="sent" value={data.sentiment_contribution} color="#84a59d" />
                            {data.bonus > 0 && (
                                <Bar label="bonus" value={data.bonus} color="#2a4f37" />
                            )}
                            {data.penalty < 0 && (
                                <Bar label="penalty" value={Math.abs(data.penalty)} color="#ff5a5a" />
                            )}
                        </div>
                    </div>

                    <div style={sectionStyle}>
                        <div style={{ ...labelStyle, marginBottom: 8 }}>
                            Fact Score: {Math.round(data.fact_score)}
                        </div>
                        {data.fact_components
                            .slice()
                            .sort((a, b) => b.score - a.score)
                            .slice(0, 8)
                            .map((c) => (
                                <ComponentRow key={c.name} c={c} showIcDead={showIcDead} />
                            ))}
                    </div>

                    <div style={sectionStyle}>
                        <div style={{ ...labelStyle, marginBottom: 8 }}>
                            Sentiment Score: {Math.round(data.sentiment_score)}
                        </div>
                        {data.sentiment_components
                            .slice()
                            .sort((a, b) => b.score - a.score)
                            .slice(0, 6)
                            .map((c) => (
                                <ComponentRow key={c.name} c={c} showIcDead={false} />
                            ))}
                    </div>

                    {showIcDead && data.ic_dead && data.ic_dead.length > 0 && (
                        <div style={icDeadStyle}>
                            <div style={labelStyle}>IC-DEAD freeze (2026-05-23)</div>
                            <div style={{ fontSize: 12, color: "#ff5a5a", marginTop: 4 }}>
                                {data.ic_dead.join(" · ")} — multiplier 0.0
                            </div>
                        </div>
                    )}
                </>
            )}

            <div style={footerStyle}>
                {phaseLine}
                <br />
                Bailey-Lopez de Prado N≥252 (2027-05) 도달 전 통계 무의미
            </div>
        </div>
    )
}

function Bar(props: { label: string; value: number; color: string }) {
    return (
        <div
            style={{
                flex: props.value,
                background: props.color,
                height: 24,
                borderRadius: 2,
                color: "#0a0a0a",
                fontSize: 11,
                fontWeight: 600,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                whiteSpace: "nowrap",
                overflow: "hidden",
            }}
        >
            {props.label} {props.value.toFixed(1)}
        </div>
    )
}

function ComponentRow(props: { c: Component; showIcDead: boolean }) {
    const isDead = props.c.status === "DEAD"
    return (
        <div style={rowStyle}>
            <span
                style={{
                    color: isDead ? "#6b7280" : "#ffffff",
                    textDecoration: isDead ? "line-through" : "none",
                }}
            >
                {props.c.name}
                {isDead && props.showIcDead ? " (DEAD)" : ""}
            </span>
            <span
                style={{
                    color:
                        props.c.score >= 60 ? "#7fffa0" :
                        props.c.score >= 40 ? "#ffa05a" : "#ff5a5a",
                    fontWeight: 600,
                }}
            >
                {Math.round(props.c.score)}
            </span>
        </div>
    )
}

const containerStyle: React.CSSProperties = {
    width: "100%",
    minHeight: 600,
    background: "#0a0a0a",
    color: "#ffffff",
    fontFamily: "'Pretendard', 'Inter', -apple-system, sans-serif",
    padding: 24,
    boxSizing: "border-box",
}
const selectorRowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    paddingBottom: 16,
    borderBottom: "1px solid rgba(255,255,255,0.06)",
}
const selectStyle: React.CSSProperties = {
    background: "#141414",
    color: "#ffffff",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: 4,
    padding: "8px 12px",
    fontSize: 13,
    cursor: "pointer",
    outline: "none",
    flex: 1,
    maxWidth: 320,
}
const headerStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    paddingTop: 16,
    paddingBottom: 16,
    borderBottom: "1px solid rgba(255,255,255,0.06)",
}
const labelStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#6b7280",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
}
const numberStyle: React.CSSProperties = {
    fontSize: 56,
    fontFamily: "'Lora', serif",
    fontWeight: 600,
    lineHeight: 1.1,
    marginTop: 4,
}
const breakdownStyle: React.CSSProperties = {
    marginTop: 20,
    paddingBottom: 16,
    borderBottom: "1px solid rgba(255,255,255,0.06)",
}
const sectionStyle: React.CSSProperties = {
    marginTop: 20,
    paddingBottom: 16,
    borderBottom: "1px solid rgba(255,255,255,0.06)",
}
const rowStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    fontSize: 13,
    padding: "6px 0",
}
const icDeadStyle: React.CSSProperties = {
    marginTop: 16,
    padding: 12,
    background: "rgba(255, 90, 90, 0.06)",
    borderRadius: 4,
}
const footerStyle: React.CSSProperties = {
    marginTop: 24,
    paddingTop: 16,
    borderTop: "1px solid rgba(255,255,255,0.06)",
    fontSize: 11,
    color: "#6b7280",
    lineHeight: 1.6,
}
const errorStyle: React.CSSProperties = {
    color: "#ff5a5a",
    padding: 16,
    fontSize: 13,
}
const loadingStyle: React.CSSProperties = {
    color: "#6b7280",
    padding: 16,
    fontSize: 13,
}

BrainGradeBreakdown.defaultProps = {
    apiUrl: "https://verity-api-kim-hyojuns-projects.vercel.app/api/brain_breakdown",
    portfolioUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
    showIcDead: true,
    defaultTicker: "",
}

addPropertyControls(BrainGradeBreakdown, {
    apiUrl: {
        type: ControlType.String,
        title: "API URL",
        defaultValue: "https://verity-api-kim-hyojuns-projects.vercel.app/api/brain_breakdown",
    },
    portfolioUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
    },
    defaultTicker: {
        type: ControlType.String,
        title: "초기 Ticker (빈값 = 첫 추천 ticker 자동)",
        defaultValue: "",
    },
    showIcDead: {
        type: ControlType.Boolean,
        title: "IC-DEAD 표시",
        defaultValue: true,
    },
})

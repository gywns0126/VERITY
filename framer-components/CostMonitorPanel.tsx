import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"
import type { CSSProperties } from "react"

function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchPortfolioJson(url: string): Promise<any> {
    return fetch(bustPortfolioUrl(url), { cache: "no-store", mode: "cors", credentials: "omit" })
        .then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.text()
        })
        .then((txt) =>
            JSON.parse(
                txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
            ),
        )
}

interface Props {
    dataUrl: string
    title: string
}

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

function formatKrw(v: number): string {
    return `${Math.round(v || 0).toLocaleString("ko-KR")}원`
}

function formatUsd(v: number): string {
    return `$${Number(v || 0).toFixed(2)}`
}

export default function CostMonitorPanel(props: Props) {
    const { dataUrl, title } = props
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetchPortfolioJson(dataUrl).then(setData).catch(console.error)
    }, [dataUrl])

    const cm = data?.cost_monitor || {}
    const budget = cm?.budget || {}
    const est = cm?.estimated_cost || {}
    const usage = cm?.monthly_usage || {}
    const breakdown = est?.breakdown_usd || {}
    const monthKey = cm?.month_key || "-"
    const status = String(est?.status || "ok").toLowerCase()

    const statusColor = useMemo(() => {
        if (status === "critical") return "#EF4444"
        if (status === "warning") return "#F59E0B"
        return "#22C55E"
    }, [status])

    const progress = Math.max(0, Math.min(100, Number(est?.progress_pct || 0)))

    if (!data) {
        return (
            <div style={{ ...panel, justifyContent: "center", alignItems: "center" }}>
                <span style={{ color: "#666", fontSize: 12 }}>비용 데이터 로딩 중...</span>
            </div>
        )
    }

    if (!data?.cost_monitor) {
        return (
            <div style={{ ...panel, justifyContent: "center", alignItems: "center" }}>
                <span style={{ color: "#888", fontSize: 12 }}>cost_monitor 데이터가 아직 없습니다.</span>
            </div>
        )
    }

    return (
        <div style={panel}>
            <div style={header}>
                <span style={titleStyle}>{title}</span>
                <span style={{ ...statusBadge, borderColor: statusColor, color: statusColor }}>
                    {status.toUpperCase()}
                </span>
            </div>

            <div style={{ color: "#666", fontSize: 10 }}>기준 월: {monthKey}</div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <Metric label="월 목표" value={formatKrw(budget?.target_monthly_krw || 0)} />
                <Metric label="현재 추정" value={formatKrw(est?.total_krw || 0)} />
                <Metric label="고정비" value={formatKrw(est?.fixed_krw || 0)} />
                <Metric label="변동비(추정)" value={formatKrw(est?.variable_krw || 0)} />
            </div>

            <div style={progressWrap}>
                <div style={progressHeader}>
                    <span style={{ color: "#888", fontSize: 10 }}>월 예산 진행률</span>
                    <span style={{ color: statusColor, fontSize: 10, fontWeight: 700 }}>{progress.toFixed(1)}%</span>
                </div>
                <div style={progressTrack}>
                    <div style={{ ...progressFill, width: `${progress}%`, background: statusColor }} />
                </div>
            </div>

            <div style={subTitle}>API 비용 추정 (USD)</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                <Mini label="Gemini" value={formatUsd(breakdown?.gemini_api || 0)} />
                <Mini label="Claude" value={formatUsd(breakdown?.claude_console || 0)} />
                <Mini label="US Data" value={formatUsd(breakdown?.us_data_api || 0)} />
            </div>

            <div style={subTitle}>이번 달 실행량</div>
            <div style={{ color: "#888", fontSize: 10, lineHeight: 1.5 }}>
                실행 {usage?.runs || 0}회 · Gemini 종목 {usage?.gemini_stock_calls || 0}회 · Claude 호출 {(usage?.claude_deep_calls || 0) + (usage?.claude_light_calls || 0)}회 · US 심볼 {usage?.us_data_symbols || 0}개
            </div>
        </div>
    )
}

function Metric({ label, value }: { label: string; value: string }) {
    return (
        <div style={metricBox}>
            <div style={{ color: "#666", fontSize: 10 }}>{label}</div>
            <div style={{ color: "#E5E7EB", fontSize: 12, fontWeight: 700 }}>{value}</div>
        </div>
    )
}

function Mini({ label, value }: { label: string; value: string }) {
    return (
        <div style={{ ...metricBox, padding: "6px 8px" }}>
            <div style={{ color: "#666", fontSize: 9 }}>{label}</div>
            <div style={{ color: "#93C5FD", fontSize: 11, fontWeight: 700 }}>{value}</div>
        </div>
    )
}

CostMonitorPanel.defaultProps = {
    dataUrl: DATA_URL,
    title: "월 비용 모니터",
}

addPropertyControls(CostMonitorPanel, {
    dataUrl: {
        type: ControlType.String,
        title: "데이터 URL",
        defaultValue: DATA_URL,
    },
    title: {
        type: ControlType.String,
        title: "제목",
        defaultValue: "월 비용 모니터",
    },
})

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const panel: CSSProperties = {
    width: "100%",
    minHeight: 260,
    background: "#111",
    border: "1px solid #222",
    borderRadius: 16,
    padding: 14,
    boxSizing: "border-box",
    fontFamily: font,
    display: "flex",
    flexDirection: "column",
    gap: 10,
}

const header: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
}

const titleStyle: CSSProperties = {
    color: "#E5E7EB",
    fontSize: 14,
    fontWeight: 800,
}

const statusBadge: CSSProperties = {
    border: "1px solid #22C55E",
    borderRadius: 999,
    padding: "2px 8px",
    fontSize: 10,
    fontWeight: 700,
}

const metricBox: CSSProperties = {
    background: "#0B0B0B",
    border: "1px solid #1F2937",
    borderRadius: 8,
    padding: "8px 10px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
}

const progressWrap: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 6,
}

const progressHeader: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
}

const progressTrack: CSSProperties = {
    width: "100%",
    height: 8,
    borderRadius: 999,
    background: "#1F2937",
    overflow: "hidden",
}

const progressFill: CSSProperties = {
    height: "100%",
    borderRadius: 999,
    background: "#22C55E",
    transition: "width 220ms ease",
}

const subTitle: CSSProperties = {
    color: "#9CA3AF",
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 0.2,
}

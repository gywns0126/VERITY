"use client"

import { useEffect, useState } from "react"
import { API_BASE } from "@/lib/api"
import { authHeaders } from "@/lib/auth"
import { useDark, palette } from "@/lib/theme"
import { useDataRefreshEpoch } from "@/lib/useDataRefreshEpoch"

type Holding = { ticker: string; name: string; reported_shares: number | null; target_shares: number | null; target_krw: number | null; target_pct: number | null }
type PersonalView = {
    schema: "personal-portfolio-view-v1"
    version: string
    published_at: string
    reviewed_at: string | null
    proposal_as_of: string
    holdings_as_of: string
    account_label: string
    horizon_label: string
    summary: string
    status_label: string
    funding_note: string
    cash_reported_krw: number | null
    cash_target_krw: number | null
    rows: Holding[]
    review?: { summary: string; reviewed_at: string; invalidators: string[] }
    adapter?: { checked_at?: string; available: number; total: number; missing: number; not_requested: number; errors: number; source_scope: string }
    monitor?: { completed_at?: string; sources_ok?: number; sources_total?: number }
}

const number = (v: number | null) => v === null ? "—" : v.toLocaleString("ko-KR", { maximumFractionDigits: 6 })
const amount = (v: number | null) => v === null ? "—" : `${Math.round(v / 10_000).toLocaleString("ko-KR")}만원`
const time = (value?: string | null) => {
    if (!value) return "미확인"
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
}

export default function PersonalPortfolio() {
    const c = palette(useDark())
    const epoch = useDataRefreshEpoch()
    const [view, setView] = useState<PersonalView | null>(null)
    const [state, setState] = useState<"loading" | "ok" | "empty" | "auth" | "error">("loading")
    const [retry, setRetry] = useState(0)
    useEffect(() => {
        const controller = new AbortController()
        const timeout = setTimeout(() => controller.abort(), 15_000)
        let cancelled = false
        const headers = authHeaders()
        if (!headers.Authorization) {
            setView(null)
            setState("auth")
            clearTimeout(timeout)
            return
        }
        fetch(`${API_BASE}/api/personal_portfolio`, { headers, cache: "no-store", signal: controller.signal })
            .then(async (response) => {
                if (cancelled) return
                if (!response.ok) {
                    if ([401, 403, 404].includes(response.status)) setView(null)
                    setState(response.status === 404 ? "empty" : response.status === 401 || response.status === 403 ? "auth" : "error")
                    return
                }
                const data = await response.json()
                if (cancelled) return
                if (data.schema !== "personal-portfolio-view-v1" || !Array.isArray(data.rows)) throw new Error("schema")
                setView(data)
                setState("ok")
            })
            .catch(() => { if (!cancelled) setState("error") })
            .finally(() => clearTimeout(timeout))
        return () => { cancelled = true; clearTimeout(timeout); controller.abort() }
    }, [epoch, retry])

    const monitorTime = Date.parse(view?.monitor?.completed_at || "")
    const monitorOld = !Number.isFinite(monitorTime) || Date.now() - monitorTime > 3_600_000
    return <section data-personal-portfolio="v1" style={{ background: c.card, border: `1px solid ${c.line}`, borderRadius: 14, padding: 16, color: c.ink }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
            <div><strong style={{ fontSize: 16 }}>내 운용안</strong><div style={{ color: c.faint, fontSize: 11, marginTop: 4 }}>{view?.account_label || "개인 포트폴리오"} · {view?.horizon_label || "저장된 판단 확인"}</div></div>
            <button type="button" onClick={() => setRetry(n => n + 1)} style={{ background: "transparent", color: c.ink, border: `1px solid ${c.line}`, borderRadius: 8, padding: "6px 10px", cursor: "pointer", flexShrink: 0 }}>새로고침</button>
        </div>
        {state !== "ok" && <p role="status" style={{ color: c.sub, fontSize: 12 }}>
            {state === "loading" ? "저장된 운용안을 불러오는 중입니다." : state === "auth" ? "로그인 상태를 확인해 주세요." : state === "empty" ? "아직 이 계정에 연결된 개인 운용안이 없습니다." : "최신 운용안을 불러오지 못했습니다. 아래 내용이 있으면 이전 수신본입니다."}
        </p>}
        {view && <>
            <p style={{ fontSize: 13, lineHeight: 1.6, margin: "14px 0 8px" }}>{view.review?.summary || view.summary}</p>
            <div style={{ fontSize: 11, color: c.sub, lineHeight: 1.8 }}>{view.status_label} · 검토 {time(view.review?.reviewed_at || view.reviewed_at)}<br />보유 확인: {view.holdings_as_of}</div>
            <div style={{ overflowX: "auto", marginTop: 12 }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, minWidth: 390 }}>
                    <thead><tr style={{ color: c.faint, textAlign: "right" }}><th style={{ textAlign: "left", padding: "8px 4px" }}>종목</th><th>확인 보유</th><th>제안 수량 / 금액</th><th>목표 비중</th></tr></thead>
                    <tbody>{view.rows.map(row => <tr key={row.ticker} style={{ borderTop: `1px solid ${c.line}` }}>
                        <td style={{ padding: "9px 4px" }}>{row.name}<span style={{ color: c.faint, fontSize: 10, marginLeft: 6 }}>{row.ticker}</span></td>
                        <td style={{ textAlign: "right" }}>{row.reported_shares === null ? "미확인" : `${number(row.reported_shares)}주`}</td>
                        <td style={{ textAlign: "right" }}>{row.target_shares !== null ? `${number(row.target_shares)}주` : amount(row.target_krw)}</td>
                        <td style={{ textAlign: "right" }}>{row.target_pct === null ? "—" : `${row.target_pct.toFixed(1)}%`}</td>
                    </tr>)}</tbody>
                </table>
            </div>
            <p style={{ fontSize: 11, color: c.sub, lineHeight: 1.7 }}>확인 현금 {amount(view.cash_reported_krw)} · 제안 현금 {amount(view.cash_target_krw)}<br />{view.funding_note}</p>
            <details style={{ fontSize: 11, color: c.sub, lineHeight: 1.8 }}>
                <summary style={{ cursor: "pointer" }}>근거 연결과 점검 상태</summary>
                <div>추천 기준 {time(view.proposal_as_of)} · 화면 자료 갱신 {time(view.published_at)}</div>
                {view.adapter && <div>자료 접근 가능 {view.adapter.available}/{view.adapter.total} · 미수집 {view.adapter.missing} · 미조회 {view.adapter.not_requested} · 오류 {view.adapter.errors}<br />{view.adapter.source_scope}</div>}
                <div>감시 수집 {view.monitor?.sources_ok ?? "—"}/{view.monitor?.sources_total ?? "—"} · {time(view.monitor?.completed_at)}{monitorOld ? " · 최근 실행 확인 필요" : ""}</div>
                {view.review?.invalidators?.map((value, i) => <div key={i}>재검토 조건: {value}</div>)}
                <div>자동 주문 연결 전 · 화면 조회는 AI를 호출하지 않습니다.</div>
            </details>
        </>}
    </section>
}

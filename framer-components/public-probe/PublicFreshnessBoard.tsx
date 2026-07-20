import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"

/**
 * 데이터 신선도 board — 전 공개 스트림의 SLA 실측 상태 페이지 (나박 대응, 2026-07-07).
 * 데이터(Blob): freshness_board.json (freshness_board_builder — 매시 cron_health 사이클 갱신).
 * 행 = 스트림 한글명 + 갱신 주기 + 상태점(신선/지연/휴장/중단) + 마지막 갱신 나이 + SLA 임계.
 *   휴장 = 주말·장 마감 무생산(정상, 개장 시 재개) · 중단 = 수집 정지(은퇴·권리검토). "휴지"→"휴장" 정정 2026-07-12.
 *
 * 🚨 RULE 7 — 사실만: 상태 = 마지막 갱신 시각 실측 vs SLA 임계 비교. 점수/예측 0.
 * RULE 6 — LLM narrative 0. 다크모드 자가감지(body[data-framer-theme]). cache-fallback(sessionStorage).
 * 지연(stale)도 숨기지 않고 그대로 노출 — 유리박스가 차별점 (경쟁 대시보드는 신선도 무표기).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", green: "#12b76a", red: "#f04438", gray: "#98a2b3",
    // 휴장(장 마감 정상) = 차분한 슬레이트(알람 아님, 개장 시 재개) · 배너 소프트 배경
    closed: "#7e8db3", closedSoft: "#eef1f8",
}
const DARK = {
    bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440", green: "#3ecf8e", red: "#f97066", gray: "#667085",
    closed: "#8b97bd", closedSoft: "#222738",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const DATA_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/freshness_board.json"

const CRIT_LABEL: Record<string, string> = { P0: "핵심 데이터", P1: "보조 데이터", P2: "배경 데이터" }
// 휴장 = 주말·장 마감 무생산(정상, 개장 시 재개) · 중단 = 수집 정지(은퇴·권리검토). paused 는 구 데이터 폴백.
const STATUS_LABEL: Record<string, string> = { fresh: "신선", stale: "지연", closed: "휴장", discontinued: "중단", paused: "휴장" }

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
    } catch (e) {}
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function fmtMins(m: any): string {
    const x = Number(m)
    if (!isFinite(x) || x < 0) return ""
    if (x < 60) return Math.round(x) + "분"
    if (x < 2880) return Math.round(x / 60) + "시간"
    return Math.round(x / 1440) + "일"
}
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        return fmtMins(mins) + " 전"
    } catch (e) {
        return ""
    }
}

const SAMPLE = {
    _meta: { generated_at: "", count: 27, note: "" },
    summary: { fresh: 22, stale: 1, closed: 2, discontinued: 1 },
    streams: [
        // 주말 프리뷰 — 시세·공시류가 휴장으로 뜨는 정상 케이스를 보이게
        { id: "price_pulse", label: "실시간 가격 펄스", criticality: "P0", cadence: "장중 1분", age_eff_min: 3, max_age_min: 30, status: "closed" },
        { id: "macro_snapshot", label: "매크로 스냅샷", criticality: "P0", cadence: "1~2시간 주기", age_eff_min: 21, max_age_min: 360, status: "fresh" },
        { id: "crypto", label: "크립토 시세·파생", criticality: "P0", cadence: "30분 목표", age_eff_min: 145, max_age_min: 90, status: "stale" },
        { id: "stock_report_public", label: "KR 종목 리포트", criticality: "P0", cadence: "매일 1회", age_eff_min: 142, max_age_min: 4320, status: "closed" },
        { id: "us_insider_trades", label: "US 내부자 거래 (Form 4)", criticality: "P1", cadence: "매일 1회", age_eff_min: 610, max_age_min: 2160, status: "fresh" },
        { id: "us_analyst_consensus", label: "US 애널리스트 컨센서스", criticality: "P1", cadence: "수집 중단 — 재배포 권리 검토 중", status: "discontinued" },
        { id: "broker_guide", label: "증권사 가이드", criticality: "P2", cadence: "월 1회", age_eff_min: 8000, max_age_min: 50400, status: "fresh" },
    ],
}

// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.
let __anHyd = false
function anReadDark(): boolean {
    if (typeof document === "undefined") return false
    if (!__anHyd) {
        __anHyd = true
        return false
    }
    const h = document.documentElement ? document.documentElement.dataset.anTheme : null
    if (h === "dark") return true
    if (h === "light") return false
    return !!(document.body && document.body.dataset.framerTheme === "dark")
}


export default function PublicFreshnessBoard(props: { width?: number; dark?: boolean; dataUrl?: string }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : anReadDark()))
    const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)
    const [showP2, setShowP2] = useState<boolean>(false)

    useEffect(() => {
        if (onCanvas) return
        setThemeDark(readBodyDark())
        const obs = new MutationObserver(() => setThemeDark(readBodyDark()))
        if (document.body) obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.dataUrl || DATA_URL, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive && d && Array.isArray(d.streams)) {
                    setData(d)
                    try { sessionStorage.setItem("freshness_board", JSON.stringify(d)) } catch (e) {}
                }
            })
            .catch(() => {
                try { const c = sessionStorage.getItem("freshness_board"); if (alive && c) setData(JSON.parse(c)) } catch (e) {}
            })
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const wrap: any = { width: props.width || 380, maxWidth: "100%", fontFamily: FONT, background: C.bg, color: C.ink, padding: "0 14px", boxSizing: "border-box" }
    if (!data) return <div style={wrap}><div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>신선도 집계 준비 중…</div></div>

    const meta = data._meta || {}
    const sum = data.summary || {}
    const streams: any[] = data.streams || []
    const dotColor = (st: string) => (st === "fresh" ? C.green : st === "stale" ? C.red : (st === "closed" || st === "paused") ? C.closed : C.gray)

    const row = (s: any) => (
        <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 0", borderBottom: "1px solid " + C.line }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: dotColor(s.status), flexShrink: 0 }} />
            <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: C.ink, lineHeight: 1.35 }}>{s.label}</div>
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 1.5, lineHeight: 1.4 }}>
                    {s.cadence || ""}
                    {s.max_age_min ? " · SLA " + fmtMins(s.max_age_min) : ""}
                </div>
            </div>
            <div style={{ textAlign: "right", flexShrink: 0 }}>
                <div style={{ fontSize: 11.5, fontWeight: 800, color: dotColor(s.status) }}>{STATUS_LABEL[s.status] || s.status}</div>
                {s.last_ts ? (
                    <div style={{ fontSize: 10, color: C.faint, fontWeight: 600, marginTop: 1 }}>{fmtAge(s.last_ts)}</div>
                ) : null}
            </div>
        </div>
    )

    const group = (crit: string, rows: any[]) => (
        <div key={crit} style={{ background: C.card, borderRadius: 14, padding: "4px 14px", marginTop: 10, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "10px 0 6px" }}>
                <span style={{ fontSize: 12, fontWeight: 800, color: C.sub }}>{CRIT_LABEL[crit] || crit}</span>
                <span style={{ fontSize: 10.5, fontWeight: 700, color: C.faint }}>{rows.length}개</span>
                {(() => {
                    const nClosed = rows.filter((r) => r.status === "closed" || r.status === "paused").length
                    return nClosed > 0 ? <span style={{ fontSize: 10.5, fontWeight: 700, color: C.closed }}>· 휴장 {nClosed}</span> : null
                })()}
            </div>
            {rows.map(row)}
            <div style={{ height: 6 }} />
        </div>
    )

    const p0 = streams.filter((s) => s.criticality === "P0")
    const p1 = streams.filter((s) => s.criticality === "P1")
    const p2 = streams.filter((s) => s.criticality === "P2")

    return (
        <div style={wrap}>
            {/* 헤더 + 요약 칩 */}
            <div style={{ marginBottom: 4 }}>
                <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>데이터 신선도</div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>
                    {"전 스트림 SLA 실측 · 매시간 자동 점검"}{meta.generated_at ? " · " + fmtAge(meta.generated_at) + " 집계" : ""}
                </div>
                <div style={{ display: "flex", gap: 6, marginTop: 9, flexWrap: "wrap" }}>
                    {[
                        { t: "신선", n: sum.fresh, c: C.green },
                        { t: "지연", n: sum.stale, c: C.red },
                        // 휴장(정상) — 구 board(paused) 폴백 합산. 중단은 있을 때만 별도 노출.
                        { t: "휴장", n: (Number(sum.closed) || 0) + (Number(sum.paused) || 0), c: C.closed },
                        { t: "중단", n: sum.discontinued, c: C.gray },
                    ].filter((x) => Number(x.n) > 0 || x.t === "신선" || x.t === "지연").map((x) => (
                        <span key={x.t} style={{ display: "inline-flex", alignItems: "center", gap: 5, background: C.card, borderRadius: 999, padding: "4px 10px", fontSize: 11, fontWeight: 800, color: C.sub, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                            <span style={{ width: 6, height: 6, borderRadius: "50%", background: x.c }} />
                            {x.t} {Number(x.n) >= 0 ? x.n : "—"}
                        </span>
                    ))}
                </div>
            </div>

            {/* 휴장 안내 — 주말·장 마감이라 무생산인 스트림이 있을 때만. "고장" 오해 차단(정상 · 개장 시 재개) */}
            {((Number(sum.closed) || 0) + (Number(sum.paused) || 0)) > 0 && (
                <div style={{ background: C.closedSoft, borderRadius: 12, padding: "10px 12px", marginTop: 10 }}>
                    <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, lineHeight: 1.5 }}>
                        <b style={{ color: C.ink, fontWeight: 800 }}>휴장</b> = 주말·장 마감이라 새 데이터가 없는 <b style={{ color: C.ink, fontWeight: 700 }}>정상</b> 상태예요. 시세·공시 스트림은 개장(평일 09:00) 시 자동 재개됩니다.
                    </div>
                </div>
            )}

            {p0.length > 0 && group("P0", p0)}
            {p1.length > 0 && group("P1", p1)}

            {/* P2 = 배경 데이터, 접힘 기본 (본질은 존재 증명) */}
            {p2.length > 0 && !showP2 && (
                <div onClick={() => setShowP2(true)}
                    style={{ background: C.card, borderRadius: 14, padding: "12px 14px", marginTop: 10, cursor: "pointer", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", display: "flex", alignItems: "center" }}>
                    <span style={{ fontSize: 12, fontWeight: 800, color: C.sub }}>배경 데이터 {p2.length}개 펼치기</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: C.faint, marginLeft: "auto" }}>›</span>
                </div>
            )}
            {p2.length > 0 && showP2 && group("P2", p2)}

            {/* RULE 7 footer */}
            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.55 }}>
                상태 = 마지막 갱신 시각 실측을 스트림별 SLA 임계와 비교한 사실 · 주말·장 마감 무생산 구간은
                유효 나이에서 제외 (휴장 = 정상, 개장 시 재개) · 수집 정지 스트림은 중단 · 지연도 그대로 표시
            </div>
        </div>
    )
}

addPropertyControls(PublicFreshnessBoard, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DATA_URL },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 시장 — VERITY 공개 터미널 (골든구스) 탭.
 *
 * 데이터 = macro_snapshot.json (Blob) + ipo_watch.json (Blob, IPO 파이프라인).
 * RULE 7 가드 — 노출 제외: market_mood / cross_asset.interpretation / global_events.impact·action.
 * RULE 6 — ⓘ 분석 설명 사전 작성. 런타임 LLM 0.
 * ⓘ = 항상 표시. 도움말 인터랙션 = PC(hover) 커서 / 모바일(touch) 탭. 토글 없음.
 * 반응형 — ResizeObserver + 100%/maxHeight/overflow.
 * 테마: init=false(SSG 라이트)→effect가 body 판독으로 교정(리렌더 강제). 캔버스는 dark prop 정적.
 * 🚨 중복 정리(2026-06-21): 글로벌 시세 보드(PublicMarketBoard)와 겹치는 시세 타일(USD/KRW·VIX·국채10Y·S&P·나스닥·금·WTI)
 *   제거 → 여긴 보드에 없는 **매크로 레짐 신호(금리차·밸류·신용) + 이벤트 일정 + IPO** 만. 보드=한눈 시세, 탭=심화 매크로.
 * 🚨 브랜드 = 보라(vg #6c5ce7/#a99bff, 2026-06-26). 링크·툴팁=보라 / D-day=시간신호라 green 유지. 면책("판단 제공 안 함·권유 아님·비노출")=제거 → 사이트 하단 단일 면책.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968",
    faint: "#8b95a1", line: "#e5e8eb", up: "#f04452", down: "#3182f6",
    amber: "#ff9500", green: "#15c47e", vg: "#6c5ce7", vgS: "#f0edff",
    vt: "#6c5ce7", vtS: "#f0edff", tipBg: "#191f28", tipFg: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1",
    faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff",
    amber: "#ff9500", green: "#34e08a", vg: "#a99bff", vgS: "#241f3a",
    vt: "#a99bff", vtS: "#241f3a", tipBg: "#222a33", tipFg: "#e3e7ec",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

/* 🚨 테마 = 자체 내장 CSS 변수(--an-mkt-*) 구동. JS 다크 감지 없음. 되돌리지 말 것.
   <style>{AN_PALETTE}</style> 로 팔레트를 정적 HTML 에 실으면 하이드레이션·JS 무관하게
   항상 정합이다. JS 감지판은 첫 마운트에 라이트로 그렸다가 뒤집혀 플래시가 난다.
   🚨 2026-08-18 — 디스크 미러가 구세대 JS 감지판이라 라이브(CSS 변수판)와 갈려 있었다.
   라이브 기준으로 맞춘 것이다. 미러를 통짜 복붙해 라이브를 덮지 말 것(같은 날 실사고). */
const _ANP = "mkt"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

const INFO: Record<string, string> = {
    "美 10Y-2Y": "장기-단기 국채 금리차. 마이너스(역전)면 경기 침체 선행 신호로 봐요. 플러스면 정상.",
    "CAPE": "경기조정 주가수익비율(실러 PER). 높을수록 증시가 역사적으로 비싼 편이라는 뜻이에요.",
    "HY 스프레드": "고위험 회사채와 국채의 금리차. 벌어지면 신용·경기 경계 신호예요.",
}

interface MetricBox { key: string; label: string; value: string; changePct?: number | null; desc?: string }
interface EventItem { name: string; date: string; d_day?: number | null; country?: string; severity?: string }

interface Props {
    snapshotUrl: string
    ipoUrl: string
    usIpoUrl: string
    dark: boolean
}

const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/macro_snapshot.json"
const DEFAULT_IPO = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/ipo_watch.json"
/* 🚨 미국 IPO — 소스가 **SEC EDGAR 단독**이라 미국 연방정부 저작물 = public domain.
   재배포 약관 이슈가 없다(FINRA·거래소 데이터와 다르다). 상세 = api/collectors/us_ipo_scout.py */
const DEFAULT_US_IPO = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_ipo_watch.json"

const SAMPLE = {
    macro: {
        yield_spread: { value: 0.85, signal: "정상" },
        fred: { cape: { value: 38.2 }, cpi_yoy: { value: 2.9 } },
        hy_spread: { value: 2.66 },
    },
    global_events: [
        { name: "미국 FOMC 금리결정", date: "2026-06-17", d_day: 0, country: "미국", severity: "high" },
        { name: "미국 CPI 발표", date: "2026-06-22", d_day: 5, country: "미국", severity: "high" },
        { name: "한국 금통위", date: "2026-06-26", d_day: 9, country: "한국", severity: "mid" },
    ],
}
const SAMPLE_IPO = [
    { corp_name: "케이앤에스아이앤씨", report_nm: "증권신고서(지분증권)", rcept_dt: "20260612", stage: "확정",
      dart_url: "https://dart.fss.or.kr",
      profile: { available: true, sector_ko: "IT·기술", est_dt: "20121228", region: "대전광역시 유성구" },
      offering: { shares: 3000000, price_planned: 12400, total_planned: 37200000000, subscribe_start: "2026.09.16", subscribe_end: "2026.09.17", payment_date: "2026.09.21" } },
]

/* 미국 IPO 캔버스 데모 — 실제 산출 형태와 동일 키. */
const SAMPLE_US_IPO = [
    { name: "Vogenx, Inc.", stage: 4, stage_ko: "거래소등록", last_filed: "20260812", amend_count: 2,
      edgar_url: "https://www.sec.gov/cgi-bin/browse-edgar",
      profile: { available: true, ticker: "VOGX", sic_desc: "Pharmaceutical Preparations" },
      pricing: { parse_ok: true, shares: 6250000, price_usd: 13, gross_usd: 81250000 } },
    { name: "Latigo Biotherapeutics, Inc.", stage: 3, stage_ko: "가격확정", last_filed: "20260807", amend_count: 1,
      edgar_url: "https://www.sec.gov/cgi-bin/browse-edgar",
      profile: { available: true, ticker: "LTGO", sic_desc: "Pharmaceutical Preparations" },
      pricing: { parse_ok: true, shares: 19200000, price_usd: 18, gross_usd: 345600000 } },
]

function fmtNum(v: any): string {
    const x = typeof v === "number" ? v : Number(v)
    if (!isFinite(x)) return "—"
    if (Math.abs(x) >= 1000) return x.toLocaleString("en-US", { maximumFractionDigits: 0 })
    if (Math.abs(x) >= 100) return x.toFixed(1)
    return x.toFixed(2)
}
function fmtPct(v: any): string {
    const x = typeof v === "number" ? v : Number(v)
    if (!isFinite(x)) return ""
    return (x > 0 ? "+" : "") + x.toFixed(2) + "%"
}
function fmtDate(s: any): string {
    const x = String(s || "")
    return x.length === 8 ? `${x.slice(0, 4)}-${x.slice(4, 6)}-${x.slice(6, 8)}` : x
}

/* 🚨 IPO 강화 (2026-08-18) — 데이터는 이미 다 있는데 화면이 회사명·날짜·링크만 썼다.
   `ipo_watch.json` 의 offering 은 실측 **10/10 전 필드 채움**(공모가·주식수·규모·청약·납입).
   IPO 에서 사람이 실제로 보는 건 공모가와 청약일인데 그게 안 보이고 있었다.
   🚨 RULE 7 — 전부 DART 공시 원문 사실이다. 자기 산식·점수·추천 없음. */

// "2026.09.16" / "20260916" 둘 다 받는다 (DART 표기가 섞인다).
function ipoDate(s: any): Date | null {
    const x = String(s || "").replace(/[.\-]/g, "")
    if (x.length !== 8) return null
    const d = new Date(+x.slice(0, 4), +x.slice(4, 6) - 1, +x.slice(6, 8))
    return isNaN(d.getTime()) ? null : d
}
// 청약 시작까지 남은 일수. 지난 건 음수 → 정렬·배지에서 뒤로 민다.
function daysTo(s: any): number | null {
    const d = ipoDate(s)
    if (!d) return null
    const t = new Date()
    t.setHours(0, 0, 0, 0)
    return Math.round((d.getTime() - t.getTime()) / 86400000)
}
function fmtDay(s: any): string {
    const d = ipoDate(s)
    return d ? `${d.getMonth() + 1}/${d.getDate()}` : "—"
}
// "20151203" → "2015 설립 · 11년차". 업력은 회사 성격을 가르는 값이라 카드에 같이 낸다.
function fmtEst(s: any): string {
    const x = String(s || "")
    if (x.length !== 8) return ""
    const y = Number(x.slice(0, 4))
    if (!y) return ""
    const age = new Date().getFullYear() - y
    return `${y} 설립` + (age > 0 ? ` · ${age}년차` : "")
}
// 372억 / 1,240억 — 억 단위 반올림. 공모규모는 억 단위가 관례다.
function fmtEok(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x <= 0) return "—"
    return Math.round(x / 1e8).toLocaleString("en-US") + "억"
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicMarketTab(props: Props) {
    const { snapshotUrl, ipoUrl, usIpoUrl } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [data, setData] = useState<any>(SAMPLE)
    const [ipos, setIpos] = useState<any[]>(SAMPLE_IPO)
    const [usIpos, setUsIpos] = useState<any[]>(SAMPLE_US_IPO)
    const [openTip, setOpenTip] = useState<string>("")
    const [tipBox, setTipBox] = useState<{ left: number; width: number }>({ left: 0, width: 240 })
    const [hoverCapable, setHoverCapable] = useState(true)

    useEffect(() => {
        if (typeof window === "undefined" || !window.matchMedia) return
        try { setHoverCapable(window.matchMedia("(hover: hover) and (pointer: fine)").matches) } catch { /* keep default */ }
    }, [])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    // 바깥 탭/클릭 시 열린 툴팁 닫기 (모바일 탭 후 닫힘)
    useEffect(() => {
        if (typeof document === "undefined") return
        const close = () => setOpenTip("")
        document.addEventListener("click", close)
        return () => document.removeEventListener("click", close)
    }, [])

    useEffect(() => {
        if (onCanvas || !snapshotUrl) return
        let alive = true
        fetch(snapshotUrl)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive && d && d.macro) setData(d) })
            .catch(() => {})
        return () => { alive = false }
    }, [snapshotUrl, onCanvas])

    useEffect(() => {
        if (onCanvas || !ipoUrl) return
        let alive = true
        fetch(ipoUrl)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const arr = d && (Array.isArray(d.watch) ? d.watch : (Array.isArray(d) ? d : null))
                if (alive && Array.isArray(arr)) setIpos(arr)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [ipoUrl, onCanvas])

    useEffect(() => {
        if (onCanvas || !usIpoUrl) return
        let alive = true
        fetch(usIpoUrl)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const arr = d && Array.isArray(d.items) ? d.items : null
                if (alive && arr) setUsIpos(arr)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [usIpoUrl, onCanvas])

    const narrow = w > 0 && w < 560
    const pad = narrow ? 12 : 18

    // 🚨 보드(글로벌 시세)와 중복되는 시세 타일은 제외 — 여긴 보드에 없는 매크로 레짐 신호만(금리차·밸류·신용).
    const tiles: MetricBox[] = useMemo(() => {
        const m = (data && data.macro) || {}
        const g = (m.fred && m.fred) || {}
        const pick = (o: any) => (o && typeof o.value !== "undefined" ? o : null)
        const out: MetricBox[] = []
        const ys = pick(m.yield_spread)
        if (ys) out.push({ key: "美 10Y-2Y", label: "美 10Y-2Y", value: (ys.value > 0 ? "+" : "") + Number(ys.value).toFixed(2) + "%p", desc: ys.signal || "장단기 금리차" })
        const cape = pick(g.cape)
        if (cape) out.push({ key: "CAPE", label: "CAPE", value: fmtNum(cape.value), desc: "실러 PER" })
        const hy = pick(m.hy_spread)
        if (hy) out.push({ key: "HY 스프레드", label: "HY 스프레드", value: fmtNum(hy.value) + "%p", desc: "신용 경계" })
        return out
    }, [data])

    const events: EventItem[] = useMemo(() => {
        const ev = (data && data.global_events) || []
        return Array.isArray(ev) ? ev.slice(0, 8) : []
    }, [data])

    const pctColor = (p?: number | null) => {
        if (p == null || !isFinite(p as number)) return C.faint
        if (p > 0) return C.up
        if (p < 0) return C.down
        return C.faint
    }

    // 툴팁 열기 — 가로 위치·폭을 컨테이너 안으로 clamp (좌우 안 잘림)
    const openTipAt = (e: any, id: string) => {
        try {
            const root = rootRef.current?.getBoundingClientRect()
            const icon = e?.currentTarget?.getBoundingClientRect?.()
            if (root && icon && root.width > 0) {
                const M = 8
                const width = Math.min(240, Math.max(170, root.width - M * 2))
                const iconLeftC = icon.left - root.left
                const clampedLeftC = Math.max(M, Math.min(iconLeftC, root.width - width - M))
                setTipBox({ left: Math.round(clampedLeftC - iconLeftC), width })
            }
        } catch { /* ignore */ }
        setOpenTip(id)
    }

    // ⓘ — 항상 표시. PC: hover, 모바일: 탭. (click 은 stopPropagation 으로 바깥 닫힘과 분리)
    const Info = ({ k, uid }: { k: string; uid: string }) => {
        if (!INFO[k]) return null
        const id = "i:" + k + ":" + uid
        const isOpen = openTip === id
        const hov = hoverCapable
            ? { onMouseEnter: (e: any) => openTipAt(e, id), onMouseLeave: () => setOpenTip("") }
            : {}
        return (
            <span style={{ position: "relative", display: "inline-block" }}>
                <span
                    role="button" tabIndex={0}
                    onClick={(e) => { e.stopPropagation(); if (isOpen) setOpenTip(""); else openTipAt(e, id) }}
                    {...hov}
                    style={{
                        display: "inline-flex", alignItems: "center", justifyContent: "center",
                        width: "1.5em", height: "1.5em", borderRadius: "50%",
                        background: "#6c5ce7", color: "#fff", fontSize: "0.62em", fontWeight: 700,
                        lineHeight: 1, cursor: "help",
                    }}
                >i</span>
                {isOpen && (
                    <span onClick={(e) => e.stopPropagation()} style={{
                        position: "absolute", top: "calc(100% + 5px)", left: tipBox.left, zIndex: 50, display: "block",
                        width: tipBox.width, background: C.tipBg, color: C.tipFg, borderRadius: 12,
                        padding: "11px 13px", fontSize: 12.5, fontWeight: 500, lineHeight: 1.55,
                        boxShadow: "0 6px 20px rgba(0,0,0,0.18)", whiteSpace: "normal", textAlign: "left",
                    }}>
                        <span style={{ fontWeight: 700, display: "block", marginBottom: 3, color: C.vt }}>{k}</span>
                        {INFO[k]}
                    </span>
                )}
            </span>
        )
    }

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", overflowX: "hidden",
        background: C.bg, fontFamily: FONT, padding: `0 ${pad}px`, boxSizing: "border-box", color: C.ink,
    }

    return (
        <div ref={rootRef} style={wrap}>
            <style>{AN_PALETTE}</style>
            <div style={{ marginBottom: 4 }}>
                <div style={{ fontSize: narrow ? 18 : 20, fontWeight: 800, letterSpacing: "-0.5px" }}>시장</div>
                <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 3 }}>
                    매크로 레짐(금리차·밸류·신용) · 일정 · IPO — 사실만 · ⓘ {hoverCapable ? "위에 커서" : "탭"}하면 설명
                </div>
            </div>

            {/* 매크로 레짐 타일 — ⓘ 호버(PC)/탭(모바일) 시 설명 팝업. 시세 타일은 글로벌 시세 보드로 이관(중복 제거) */}
            {tiles.length > 0 && (
                <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(${narrow ? 130 : 150}px, 1fr))`, gap: 10, marginTop: 12 }}>
                    {tiles.map((t, ti) => (
                        <div key={t.key}
                            style={{ background: C.card, borderRadius: 14, padding: "13px 14px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                <span>{t.label}</span>
                                <Info k={t.key} uid={"tile" + ti} />
                            </div>
                            <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.5px", margin: "3px 0" }}>{t.value}</div>
                            <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                                {t.changePct != null && isFinite(t.changePct) && (
                                    <span style={{ fontSize: 12, fontWeight: 800, color: pctColor(t.changePct) }}>{fmtPct(t.changePct)}</span>
                                )}
                                {t.desc && <span style={{ fontSize: 11.5, color: C.sub, fontWeight: 600 }}>{t.desc}</span>}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* 글로벌 이벤트 일정 */}
            {events.length > 0 && (
                <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 12 }}>
                    <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 8 }}>글로벌 이벤트 일정</div>
                    {events.map((e, i) => {
                        const dd = e.d_day
                        const ddLabel = dd == null ? "" : dd === 0 ? "D-day" : dd > 0 ? "D-" + dd : "D+" + Math.abs(dd)
                        const hot = e.severity === "high"
                        return (
                            <div key={i} style={{ display: "flex", gap: 12, padding: "9px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}`, alignItems: "baseline" }}>
                                <span style={{ flexShrink: 0, width: 56, fontSize: 12.5, fontWeight: 800, color: hot ? C.up : C.green }}>{ddLabel}</span>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: 13.5, fontWeight: 700, color: C.ink }}>{e.name}</div>
                                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>{(e.country ? e.country + " · " : "") + e.date}</div>
                                </div>
                            </div>
                        )
                    })}
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>
                        일정·사실만
                    </div>
                </div>
            )}

            {/* IPO 파이프라인 — 공모가·규모·청약일 노출 + 임박순 정렬 (2026-08-18 강화) */}
            {ipos.length > 0 && (
                <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 12 }}>
                    <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 8 }}>IPO 파이프라인 <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>· 상장 전 · DART</span></div>
                    {/* 🚨 접수일순이면 **청약이 이미 끝난 건**이 위로 온다(실측 10건 중 5건).
                        다가오는 청약을 앞에 두고, 지난 건은 뒤로 민다. 원본 배열은 건드리지 않는다. */}
                    {ipos
                        .slice()
                        .sort((a: any, b: any) => {
                            const da = daysTo((a.offering || {}).subscribe_start)
                            const db = daysTo((b.offering || {}).subscribe_start)
                            const ka = da == null ? 9999 : da < 0 ? 5000 - da : da
                            const kb = db == null ? 9999 : db < 0 ? 5000 - db : db
                            return ka - kb
                        })
                        .slice(0, 10)
                        .map((p: any, i: number) => {
                            const o = p.offering || {}
                            const dd = daysTo(o.subscribe_start)
                            const soon = dd != null && dd >= 0 && dd <= 7
                            const past = dd != null && dd < 0
                            return (
                                <div key={i} style={{ display: "flex", gap: 12, padding: "11px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}`, alignItems: "flex-start", opacity: past ? 0.55 : 1 }}>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                                            <span style={{ fontSize: 13.5, fontWeight: 700, color: C.ink }}>{p.corp_name || p.name}</span>
                                            {p.stage && (
                                                <span style={{ fontSize: 9.5, fontWeight: 800, color: p.stage === "확정" ? C.green : C.faint, background: C.bg, borderRadius: 5, padding: "2px 6px" }}>{p.stage}</span>
                                            )}
                                            {soon && (
                                                <span style={{ fontSize: 9.5, fontWeight: 800, color: C.vg, background: C.vgS, borderRadius: 5, padding: "2px 6px" }}>
                                                    {dd === 0 ? "청약 오늘" : `청약 D-${dd}`}
                                                </span>
                                            )}
                                        </div>
                                        {/* 🚨 회사 성격 — 업종·업력·소재지. 카드에 이름·숫자·날짜만
                                            있어 "무슨 회사인지" 를 알 수 없었다(PM 지적).
                                            정기공시 재무는 상장 전이라 실측 1/10 만 채워져 그 자리를
                                            못 메운다 — DART 기업개황은 10/10 채워진다.
                                            업종은 회사가 공시한 KSIC 를 표준 대응한 값이다(자체 판단 아님). */}
                                        {(p.profile || {}).available && (
                                            <div style={{ fontSize: 11.5, fontWeight: 600, color: C.faint, marginTop: 2 }}>
                                                {[p.profile.sector_ko, fmtEst(p.profile.est_dt), p.profile.region].filter(Boolean).join(" · ")}
                                            </div>
                                        )}
                                        {/* 공모 조건 — 전부 DART 신고서 기재값 */}
                                        <div style={{ fontSize: 12, fontWeight: 700, color: C.sub, marginTop: 3 }}>
                                            {o.price_planned ? `${Number(o.price_planned).toLocaleString("en-US")}원` : "공모가 미정"}
                                            {o.total_planned ? ` · ${fmtEok(o.total_planned)}` : ""}
                                            {o.shares ? ` · ${Number(o.shares).toLocaleString("en-US")}주` : ""}
                                        </div>
                                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 2 }}>
                                            {o.subscribe_start ? `청약 ${fmtDay(o.subscribe_start)}${o.subscribe_end ? `~${fmtDay(o.subscribe_end)}` : ""}` : ""}
                                            {o.payment_date ? ` · 납입 ${fmtDay(o.payment_date)}` : ""}

                                        </div>
                                    </div>
                                    {p.dart_url && (
                                        <a href={p.dart_url} target="_blank" rel="noopener" style={{ flexShrink: 0, fontSize: 10.5, fontWeight: 800, color: C.vg, background: C.vgS, borderRadius: 6, padding: "3px 9px", textDecoration: "none", whiteSpace: "nowrap" }}>원문</a>
                                    )}
                                </div>
                            )
                        })}
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>
                        상장 전 파이프라인(증권신고서 제출) · 공모가·청약일 = DART 신고서 기재값 · 사실만
                    </div>
                </div>
            )}

            {/* 미국 IPO — SEC EDGAR 단계 추적 (2026-08-18 신설) */}
            {usIpos.length > 0 && (
                <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 12 }}>
                    <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 8 }}>미국 IPO <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>· 상장 전 · SEC EDGAR</span></div>
                    {/* 🚨 정렬 = 공모조건 있는 건 우선 → SPAC 뒤로 → 단계 내림 → 최근순.
                        단계만으로 정렬하면 거래소등록(8-A) 이 위를 다 차지하는데 그쪽은
                        공모가가 안 붙어 상위 8건이 전부 "공모조건 —" 로 나온다(실측).
                        공모조건이 파싱된 건을 앞에 두면 Jersey Mike's($683M)·Csquare($1.05B)
                        같은 실제 IPO 가 숫자와 함께 올라온다.
                        🚨 is_spac_likely 는 **정렬에만** 쓴다 — 회사명 휴리스틱이라 화면에
                        표기하지 않는다(RULE 7). 순서 조정은 화면상 주장이 아니다. */}
                    {usIpos
                        .slice()
                        .sort((a: any, b: any) => {
                            const pa = ((a.pricing || {}).parse_ok ? 0 : 1) - ((b.pricing || {}).parse_ok ? 0 : 1)
                            if (pa) return pa
                            const sp = (a.is_spac_likely ? 1 : 0) - (b.is_spac_likely ? 1 : 0)
                            if (sp) return sp
                            return (b.stage - a.stage) || String(b.last_filed).localeCompare(String(a.last_filed))
                        })
                        .slice(0, 8)
                        .map((p: any, i: number) => {
                            const pr = (p.pricing && p.pricing.parse_ok) ? p.pricing : null
                            const near = p.stage >= 3
                            return (
                                <div key={i} style={{ display: "flex", gap: 12, padding: "11px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}`, alignItems: "flex-start" }}>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                                            <span style={{ fontSize: 13.5, fontWeight: 700, color: C.ink }}>{p.name}</span>
                                            {/* 상장 예정 심볼 — SEC submissions.tickers 기재값 */}
                                            {(p.profile || {}).ticker && (
                                                <span style={{ fontSize: 11, fontWeight: 800, color: C.vg, letterSpacing: "0.02em" }}>{p.profile.ticker}</span>
                                            )}
                                            {p.stage_ko && (
                                                <span style={{ fontSize: 9.5, fontWeight: 800, color: near ? C.green : C.faint, background: C.bg, borderRadius: 5, padding: "2px 6px" }}>{p.stage_ko}</span>
                                            )}
                                        </div>
                                        {/* 🚨 업종 — SEC sicDescription 그대로다. 우리 번역·분류가 아니다.
                                            SPAC 은 SEC 가 "Blank Checks"(SIC 6770)로 직접 분류하므로
                                            별도 라벨 없이 이 줄에서 드러난다. */}
                                        {(p.profile || {}).sic_desc && (
                                            <div style={{ fontSize: 11.5, fontWeight: 600, color: C.faint, marginTop: 2 }}>
                                                {p.profile.sic_desc}
                                            </div>
                                        )}
                                        {/* 공모 조건 — 424B4 표지 기재값. 파싱 성공분만 노출한다(추정 금지). */}
                                        {pr && (
                                            <div style={{ fontSize: 12, fontWeight: 700, color: C.sub, marginTop: 3 }}>
                                                ${Number(pr.price_usd).toLocaleString("en-US")} · {Number(pr.shares).toLocaleString("en-US")}주 · ${Math.round(Number(pr.gross_usd) / 1e6).toLocaleString("en-US")}M
                                            </div>
                                        )}
                                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 2 }}>
                                            {p.last_filed ? `최근 접수 ${fmtDate(p.last_filed).slice(5)}` : ""}
                                            {p.amend_count ? ` · 정정 ${p.amend_count}회` : ""}
                                        </div>
                                    </div>
                                    {p.edgar_url && (
                                        <a href={p.edgar_url} target="_blank" rel="noopener" style={{ flexShrink: 0, fontSize: 10.5, fontWeight: 800, color: C.vg, background: C.vgS, borderRadius: 6, padding: "3px 9px", textDecoration: "none", whiteSpace: "nowrap" }}>EDGAR</a>
                                    )}
                                </div>
                            )
                        })}
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>
                        단계 = S-1 신청 → 정정 → 424B4 가격확정 → 8-A 거래소등록 · 공모 조건은 신고서 기재값 · 사실만
                    </div>
                </div>
            )}

            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
                출처 FRED · yfinance · DART · SEC EDGAR · 사실 지표만
            </div>
        </div>
    )
}

addPropertyControls(PublicMarketTab, {
    snapshotUrl: { type: ControlType.String, title: "Snapshot URL", defaultValue: DEFAULT_URL },
    ipoUrl: { type: ControlType.String, title: "IPO URL", defaultValue: DEFAULT_IPO },
    usIpoUrl: { type: ControlType.String, title: "US IPO URL", defaultValue: DEFAULT_US_IPO },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

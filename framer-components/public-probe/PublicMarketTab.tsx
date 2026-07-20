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
 * 테마: Framer 네이티브 추종 — body[data-framer-theme] 읽어 dark 전환(캔버스는 dark prop 정적 프리뷰).
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
    dark: boolean
}

const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/macro_snapshot.json"
const DEFAULT_IPO = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/ipo_watch.json"

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
    { corp_name: "케이앤에스아이앤씨", report_nm: "증권신고서(지분증권)", rcept_dt: "20260612", dart_url: "https://dart.fss.or.kr" },
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

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
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


// 마운트/토글 재판독 SoT — verity_theme(localStorage) 우선 → html[data-an-theme] → body[data-framer-theme].
// 791d29f7e 8개 fix 에서 누락됐던 body-only 재판독 버그 정정(다크에서 라이트 고정 방지, 2026-07-21 일괄).
function readBodyDark(): boolean {
    if (typeof document === "undefined") return false
    try {
        const pref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (pref === "dark") return true
        if (pref === "light") return false
        const h = document.documentElement ? document.documentElement.dataset.anTheme : null
        if (h === "dark") return true
        if (h === "light") return false
        if (document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

export default function PublicMarketTab(props: Props) {
    const { snapshotUrl, ipoUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [data, setData] = useState<any>(SAMPLE)
    const [ipos, setIpos] = useState<any[]>(SAMPLE_IPO)
    const [openTip, setOpenTip] = useState<string>("")
    const [tipBox, setTipBox] = useState<{ left: number; width: number }>({ left: 0, width: 240 })
    const [hoverCapable, setHoverCapable] = useState(true)
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : anReadDark()))

    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 dark prop 정적) */
    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

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
        fetch(snapshotUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive && d && d.macro) setData(d) })
            .catch(() => {})
        return () => { alive = false }
    }, [snapshotUrl, onCanvas])

    useEffect(() => {
        if (onCanvas || !ipoUrl) return
        let alive = true
        fetch(ipoUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const arr = d && (Array.isArray(d.watch) ? d.watch : (Array.isArray(d) ? d : null))
                if (alive && Array.isArray(arr)) setIpos(arr)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [ipoUrl, onCanvas])

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

            {/* IPO 파이프라인 */}
            {ipos.length > 0 && (
                <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginTop: 12 }}>
                    <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 8 }}>IPO 파이프라인 <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>· 상장 전 · DART</span></div>
                    {ipos.slice(0, 10).map((p, i) => (
                        <div key={i} style={{ display: "flex", gap: 12, padding: "10px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}`, alignItems: "flex-start" }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 13.5, fontWeight: 700, color: C.ink }}>{p.corp_name || p.name}</div>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>
                                    {(p.report_nm || "증권신고서")}{p.rcept_dt ? " · " + fmtDate(p.rcept_dt) : ""}
                                </div>
                            </div>
                            {p.dart_url && (
                                <a href={p.dart_url} target="_blank" rel="noopener" style={{ flexShrink: 0, fontSize: 10.5, fontWeight: 800, color: C.vg, background: C.vgS, borderRadius: 6, padding: "3px 9px", textDecoration: "none", whiteSpace: "nowrap" }}>원문</a>
                            )}
                        </div>
                    ))}
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>
                        상장 전 파이프라인(증권신고서 제출) · 사실만
                    </div>
                </div>
            )}

            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
                출처 FRED · yfinance · DART · 사실 지표만
            </div>
        </div>
    )
}

addPropertyControls(PublicMarketTab, {
    snapshotUrl: { type: ControlType.String, title: "Snapshot URL", defaultValue: DEFAULT_URL },
    ipoUrl: { type: ControlType.String, title: "IPO URL", defaultValue: DEFAULT_IPO },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

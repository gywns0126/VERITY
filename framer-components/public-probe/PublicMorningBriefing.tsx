import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 모닝 브리핑 — 홈 최상단 단일 채널 (PM 2026-07-05 · 2026-07-11 통합 지시).
 *   구성 = 제호(카드 밖) + [① 내 자산 카드] + [② 시장 브리핑 카드] — 형제 카드 2장.
 *   🚨 2026-07-11 PM: 사파리 창/신문 제호 목업 제거 — 토스식 플랫 카드, 정보 가독성 우선.
 *      기존 PublicDailyBriefing(s1NvKbN) 데이터 로직(1면 배너·섹션·mover·접힘·cache-fallback) 이식,
 *      연출(스트림 애니·창 크롬·마스트헤드)만 제거. s1NvKbN 인스턴스는 홈에서 제거(코드파일 보존).
 *   🚨 2026-07-11 PM 가독성 — 통합 카드 1장(블록 7개) = 섹션 경계 소실. 처방 3종:
 *      (a) 카드 2장 분할 — 개인(자산) / 시장 = 성격이 다름. 중첩 tint 박스는 카드로 승격.
 *      (b) 보라(C.vg) = 액션 전용 — 종목명 보라 800 이 섹션 제목(검정 800)보다 튀어 위계가 역전됨.
 *          종목명 = C.ink 700 + 흐린 밑줄(클릭 어포던스). 보라는 버튼/CTA 에만.
 *      (c) 섹션 경계 = hairline + 여백. 섹션 사이:안 = 32:7 (기존 15:7 = 근접성 대비 부족).
 *
 * ① 내 자산 — 사용자 개인 보유종목 (VERITY 시스템 성과 아님). PublicHoldingsTab 계산 재사용.
 *   인증 — localStorage["verity_supabase_session"].access_token → /api/holdings.
 *   총 자산 = Σ(종가 × 수량), 종가 = stock_flow_5d 마지막 close → h.price → avg_cost graceful.
 *   전일 증감 = Σ(마지막 close − 직전 close) × 수량 — 🚨 전일 "종가" 대비만(실시간 아님).
 *     시세 재배포 컴플라이언스(2026-07-03 Phase 1.5): 실시간 폴링 0, EOD 종가 재사용만.
 *     stock_flow_5d = KR·커버리지 한정 → 증감 집계 = 국내 커버 종목만(US·미커버 = 총액엔 포함, 증감 제외).
 *   미로그인(라이브) = 컴팩트 CTA 한 줄. 캔버스 = SAMPLE 미리보기.
 *
 * ② 시장 브리핑 — daily_briefing.json (빌더 미착수 → 라이브 404 시 "준비 중" 한 줄, SAMPLE 은 캔버스 전용).
 *   1면 recap(지수 레벨+등락%, 금융위 공공데이터) + 섹션(아이템·mover 등락색·"+N건" 접힘).
 *   sessionStorage cache-fallback. 종목 클릭 → stockPath?q=.
 *
 * RULE 6 = LLM 0 (결정론 조립). RULE 7 = 사실만 (점수·추천·매매의견 0), 면책 푸터.
 * KR 등락색 관례 = 상승 빨강 / 하락 파랑. 테마 = body[data-framer-theme] 자가감지. 반응형 = ResizeObserver.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968",
    faint: "#8b95a1", line: "#e5e8eb", up: "#f04452", down: "#3182f6",
    vg: "#6c5ce7", vgS: "#f0edff", warn: "#ff9500", onAccent: "#ffffff",
}
const DARK = {
    bg: "#10141a", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1",
    faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff",
    vg: "#a99bff", vgS: "#241f3a", warn: "#ffb340", onAccent: "#0f1318",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const FX = 1380  // 미국주식 KRW 환산 가정 (PublicHoldingsTab 동기)
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
const KR_MK = ["KOSPI", "KOSDAQ", "KONEX"]
const DEFAULT_API = "https://project-yw131.vercel.app"
const FLOW_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_flow_5d.json"
const BRIEF_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/daily_briefing.json"
const PER_SECTION = 3  // 섹션당 기본 노출, 초과 = "+N건" 접힘

interface Props {
    apiBase: string
    loginUrl: string
    holdingsUrl: string
    stockPath: string
    usStockPath: string
    briefUrl: string
    dark: boolean
}

// ── 캔버스/데모 샘플 (실제 숫자 아님) ──
const SAMPLE_HOLD = [
    { ticker: "005930", name: "삼성전자", shares: 100, avg_cost: 68000, price: 81200, market: "kr" },
    { ticker: "000660", name: "SK하이닉스", shares: 15, avg_cost: 215000, price: 241000, market: "kr" },
    { ticker: "NVDA", name: "NVIDIA", shares: 20, avg_cost: 120, price: 172.4, market: "us" },
]
const SAMPLE_PREV: Record<string, number> = { "005930": 80720, "000660": 242000 }
const SAMPLE_BRIEF = {
    date: "2026-07-11", weekday: "금", warnings_n: 0,
    sections: [
        { title: "지난 거래일 시장", note: "금융위 공공데이터 · 공시 병기 = 사실, 인과 해석 아님",
          recap: { date: "07/10", kospi: 0.62, kosdaq: 1.15, kospi_close: 7291.91, kosdaq_close: 794.0,
                   headline: "코스피는 올랐지만 종목 2,633개 중 1,587개는 내렸어요" },
          items: [
            { name: "내린 쪽", text: "경기소비재 -4.5% · 생활소비재 -4.3%" },
            { name: "올린 쪽", text: "정보기술 +1.9%" },
            { ticker: "000660", name: "SK하이닉스", text: "거래대금 1위" },
            { ticker: "049960", name: "오픈베이스", text: "+13.2% · 같은 날 공시: 단일판매ㆍ공급계약체결", mover: true },
        ] },
        { title: "밤사이 미국 공시", note: "SEC EDGAR 일일 인덱스 감지분", items: [
            { ticker: "CNXC", name: "Concentrix", text: "10-K/Q 재무 공시 제출 → 재무 반영 완료" },
        ] },
        { title: "최근 7일 내부자 변동", note: "DART 보고 사실 · 증감 주식수", items: [
            { ticker: "402340", name: "SK스퀘어", text: "12,111,300주 매수 (07-01)" },
        ] },
    ],
    disclaimer: "전부 공시·수집 사실과 자체계산 예상 창 · 점수·추천·매매의견 아님",
}

function getToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const r = localStorage.getItem("verity_supabase_session")
        if (!r) return ""
        const s = JSON.parse(r)
        return (s && typeof s.access_token === "string") ? s.access_token : ""
    } catch {
        return ""
    }
}
function money(v: number): string {
    if (!isFinite(v)) return "—"
    return Math.round(v).toLocaleString("en-US") + "원"
}
function wonCompact(v: number): string {
    const a = Math.abs(Math.round(v))
    const sign = v < 0 ? "-" : ""
    if (a >= 1e8) return sign + (a / 1e8).toFixed(a >= 1e9 ? 0 : 1) + "억원"
    if (a >= 1e4) return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만원"
    return sign + a.toLocaleString("en-US") + "원"
}
function flagCode(market: any): string {
    const m = String(market || "").toUpperCase()
    if (KR_MK.indexOf(m) >= 0 || m.indexOf("KOS") >= 0 || m.indexOf("KONEX") >= 0) return "kr"
    if (m.indexOf("NAS") >= 0 || m.indexOf("NYSE") >= 0 || m.indexOf("AMEX") >= 0 || m.indexOf("US") >= 0) return "us"
    return "kr"
}
function isUsMkt(h: any): boolean {
    return h.market === "us" || h.currency === "USD" || flagCode(h.market) === "us"
}
function FlagIcon(props: { code: string; size?: number }) {
    const size = props.size || 15
    return (
        <img src={FLAG_BASE + props.code + ".svg"} alt="" loading="lazy" decoding="async" width={size} height={size}
            style={{ width: size, height: size, borderRadius: "50%", display: "inline-block", verticalAlign: "-2px", flexShrink: 0 }} />
    )
}
function readBodyDark(): boolean {
    try {
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicMorningBriefing(props: Props) {
    const { apiBase, loginUrl, holdingsUrl, stockPath, usStockPath, briefUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))

    // ① 내 자산 상태
    const [rows, setRows] = useState<any[]>(SAMPLE_HOLD)
    const [closes, setCloses] = useState<Record<string, { last: number; prev: number | null }>>({})
    const [isDemo, setIsDemo] = useState(true)
    const [loading, setLoading] = useState<boolean>(() => (onCanvas ? false : !!getToken()))

    // ② 시장 브리핑 상태
    const [brief, setBrief] = useState<any>(onCanvas ? SAMPLE_BRIEF : null)
    const [briefFailed, setBriefFailed] = useState(false)
    const [openSec, setOpenSec] = useState<Record<string, boolean>>({})

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

    // 반응형 폭
    useEffect(() => {
        if (typeof ResizeObserver === "undefined" || !rootRef.current) return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(rootRef.current)
        return () => ro.disconnect()
    }, [])

    // 테마 자가감지
    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver !== "undefined" && document.body) {
            const mo = new MutationObserver(read)
            mo.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
            return () => mo.disconnect()
        }
    }, [onCanvas])

    // 보유종목 로드 (/api/holdings)
    const loadHoldings = useCallback(() => {
        if (onCanvas) return
        const token = getToken()
        if (!token) { setIsDemo(true); setRows(SAMPLE_HOLD); setLoading(false); return }
        setLoading(true)
        fetch(base + "/api/holdings", { headers: { Authorization: "Bearer " + token } })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (Array.isArray(d)) { setIsDemo(false); setRows(d) } })
            .catch(() => {})
            .finally(() => setLoading(false))
    }, [base, onCanvas])
    useEffect(() => { loadHoldings() }, [loadHoldings])

    // 종가(마지막·직전) — stock_flow_5d 재사용. 실시간 아님, 신규 시세 노출 0.
    useEffect(() => {
        if (onCanvas || isDemo) return
        let alive = true
        fetch(FLOW_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const fm = d && (d.flows || d)
                if (!alive || !fm || typeof fm !== "object") return
                const m: Record<string, { last: number; prev: number | null }> = {}
                for (const tk of Object.keys(fm)) {
                    const arr = fm[tk]
                    if (!Array.isArray(arr) || !arr.length) continue
                    const last = Number(arr[arr.length - 1] && arr[arr.length - 1].close)
                    const prevRaw = arr.length >= 2 ? Number(arr[arr.length - 2].close) : NaN
                    if (!isFinite(last) || !last) continue
                    m[tk] = { last, prev: isFinite(prevRaw) && prevRaw ? prevRaw : null }
                }
                setCloses(m)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [isDemo, onCanvas])

    // 시장 브리핑 로드 — sessionStorage cache-fallback (기존 PublicDailyBriefing 이식)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const fallback = () => {
            try {
                const c = sessionStorage.getItem("daily_briefing")
                if (alive && c) { setBrief(JSON.parse(c)); return }
            } catch (e) { /* ignore */ }
            if (alive) setBriefFailed(true)
        }
        fetch(briefUrl || BRIEF_URL, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                if (d && Array.isArray(d.sections)) {
                    setBrief(d)
                    try { sessionStorage.setItem("daily_briefing", JSON.stringify(d)) } catch (e) { /* ignore */ }
                } else fallback()
            })
            .catch(fallback)
        return () => { alive = false }
    }, [onCanvas, briefUrl])

    // ── 내 자산 계산 ──
    const asset = useMemo(() => {
        const usePrev = isDemo ? SAMPLE_PREV : null
        const evald = rows.map((h) => {
            const tk = String(h.ticker)
            const us = isUsMkt(h)
            const fx = us ? FX : 1
            const shares = Number(h.shares) || 0
            const q = closes[tk]
            const last = q ? q.last : (Number(h.price) || Number(h.avg_cost) || 0)
            const prev = q ? q.prev : (usePrev && usePrev[tk] != null ? usePrev[tk] : null)
            const val = last * shares * fx
            const dayDelta = prev != null && isFinite(prev) ? (last - prev) * shares * fx : null
            const prevVal = prev != null && isFinite(prev) ? prev * shares * fx : null
            return { tk, name: h.name || tk, market: h.market, us, _val: val, _day: dayDelta, _prevVal: prevVal,
                     _dayPct: prev != null && prev ? ((last - prev) / prev) * 100 : null }
        })
        const totalVal = evald.reduce((a, b) => a + (b._val || 0), 0)
        const covered = evald.filter((e) => e._day != null)
        const dayChange = covered.reduce((a, b) => a + (b._day || 0), 0)
        const coveredPrevVal = covered.reduce((a, b) => a + (b._prevVal || 0), 0)
        const dayPct = coveredPrevVal > 0 ? (dayChange / coveredPrevVal) * 100 : null
        const hasUncovered = evald.length > covered.length
        const movers = covered.slice().sort((a, b) => Math.abs(b._day || 0) - Math.abs(a._day || 0)).slice(0, 3)
        return { totalVal, dayChange, dayPct, movers, hasUncovered, count: evald.length }
    }, [rows, closes, isDemo])

    const noLogin = !onCanvas && isDemo
    const upC = (v: number) => (v >= 0 ? C.up : C.down)
    const arrow = (v: number) => (v > 0 ? "▲" : v < 0 ? "▼" : "·")
    const narrow = w > 0 && w < 420

    const goHoldings = () => {
        if (typeof window === "undefined") return
        window.location.href = (holdingsUrl || "/holdings").replace(/\/+$/, "")
    }
    const goLogin = () => {
        if (typeof window === "undefined" || !loginUrl) return
        window.location.href = loginUrl
    }
    const goStockTk = (tk: string, us?: boolean) => {
        if (typeof window === "undefined" || !tk) return
        const path = (us ? (usStockPath || "/us/stock") : (stockPath || "/stock")).replace(/\/+$/, "")
        window.location.href = path + "?q=" + encodeURIComponent(tk)
    }

    // ── 브리핑 렌더 준비 (기존 로직 이식) ──
    const pctColor = (v: number) => (v > 0 ? C.up : v < 0 ? C.down : C.sub)
    const fmtPct = (v: number) => (v > 0 ? "+" : "") + Number(v).toFixed(2) + "%"
    const fmtLevel = (v: any) => (typeof v === "number" && isFinite(v) ? v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "")
    // mover 행 — "+13.2% · 같은 날 공시: …" 앞 % 만 등락색 분리
    const moverText = (t: string) => {
        const cut = t.indexOf(" · ")
        if (cut < 0) return <span style={{ color: C.sub, fontWeight: 600 }}>{t}</span>
        const pct = t.slice(0, cut)
        const rest = t.slice(cut)
        const col = pct.indexOf("+") === 0 ? C.up : (pct.indexOf("-") === 0 || pct.indexOf("−") === 0) ? C.down : C.sub
        return (
            <span style={{ minWidth: 0 }}>
                <span style={{ color: col, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{pct}</span>
                <span style={{ color: C.sub, fontWeight: 600 }}>{rest}</span>
            </span>
        )
    }
    const secs: any[] = (brief && brief.sections) || []
    const banner = secs.length && secs[0].recap && typeof secs[0].recap.kospi === "number" ? secs[0].recap : null
    const dateLine = brief && brief.date
        ? String(brief.date).replace(/-/g, ".").slice(5) + " (" + (brief.weekday || "") + ") · 07:30 발행"
        : "매일 아침 07:30 발행"

    // 카드 밖 제호 + 형제 카드 2장 (개인 / 시장). 중첩 카드 회피.
    const shell: CSSProperties = {
        fontFamily: FONT, width: "100%", boxSizing: "border-box", color: C.ink,
        display: "flex", flexDirection: "column", gap: 12,
    }
    const card: CSSProperties = {
        background: C.card, borderRadius: 18,
        padding: narrow ? "16px 16px" : "20px 20px", boxSizing: "border-box",
    }
    const cta: CSSProperties = {
        ...card, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10,
        padding: narrow ? "15px 16px" : "16px 18px", cursor: "pointer",
    }
    const secTitle: CSSProperties = { fontSize: narrow ? 14 : 15, fontWeight: 800, color: C.ink, letterSpacing: "-0.2px" }
    const secNote: CSSProperties = { fontSize: 11, fontWeight: 600, color: C.faint }

    return (
        <div ref={rootRef} style={shell}>
            {/* 제호 — 카드 밖 (카드 2장을 하나의 채널로 묶는 역할) */}
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, padding: "0 4px" }}>
                <span style={{ fontSize: narrow ? 18 : 20, fontWeight: 800, letterSpacing: "-0.5px" }}>모닝 브리핑</span>
                <span style={{ fontSize: 11.5, fontWeight: 600, color: C.faint, whiteSpace: "nowrap" }}>{dateLine}</span>
            </div>

            {/* ── ① 내 자산 카드 ── */}
            {noLogin ? (
                <div onClick={goLogin} role="button" style={{ ...cta, background: C.vgS }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: C.ink, lineHeight: 1.5 }}>
                        <span style={{ color: C.vg }}>내 자산</span> — 로그인하면 보유종목 증감을 여기서 바로 봐요
                    </div>
                    <span style={{ flexShrink: 0, fontSize: 12.5, fontWeight: 800, color: C.vg }}>로그인 →</span>
                </div>
            ) : loading ? (
                <div style={{ ...card, textAlign: "center", color: C.faint, fontSize: 12.5, fontWeight: 600 }}>내 자산 불러오는 중…</div>
            ) : asset.count === 0 ? (
                <div onClick={goHoldings} role="button" style={cta}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: C.sub }}>보유종목을 추가하면 자산 요약이 여기 떠요</div>
                    <span style={{ flexShrink: 0, fontSize: 12.5, fontWeight: 800, color: C.vg }}>추가 →</span>
                </div>
            ) : (
                <div style={{ ...card, paddingBottom: 0 }}>
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                        <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 700 }}>내 자산</span>
                        <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600 }}>평단 입력 기준 · 전일 종가 대비</span>
                    </div>
                    <div style={{ fontSize: narrow ? 23 : 26, fontWeight: 800, letterSpacing: "-1px", margin: "3px 0 2px", fontVariantNumeric: "tabular-nums" }}>{money(asset.totalVal)}</div>
                    {asset.dayPct != null ? (
                        <div style={{ fontSize: 13.5, fontWeight: 800, color: upC(asset.dayChange), fontVariantNumeric: "tabular-nums" }}>
                            {arrow(asset.dayChange)} {(asset.dayChange >= 0 ? "+" : "") + wonCompact(asset.dayChange)} ({(asset.dayPct >= 0 ? "+" : "") + asset.dayPct.toFixed(2)}%)
                            {asset.hasUncovered && <span style={{ fontSize: 10.5, fontWeight: 600, color: C.faint, marginLeft: 6 }}>국내 종목 기준</span>}
                        </div>
                    ) : (
                        <div style={{ fontSize: 12.5, fontWeight: 700, color: C.faint }}>전일 종가 데이터 대기</div>
                    )}
                    {/* 움직인 종목 — 컴팩트 행 */}
                    {asset.movers.length > 0 && (
                        <div style={{ marginTop: 10 }}>
                            {asset.movers.map((m: any) => (
                                <div key={m.tk} onClick={() => goStockTk(m.tk, m.us)} role="button"
                                    style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, padding: "8px 0", borderTop: `1px solid ${C.line}`, cursor: "pointer" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
                                        <FlagIcon code={flagCode(m.market)} size={14} />
                                        <span style={{ fontSize: 13, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m.name}</span>
                                    </div>
                                    <div style={{ display: "flex", alignItems: "center", gap: 9, flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>
                                        {m._dayPct != null && (
                                            <span style={{ fontSize: 12.5, fontWeight: 800, color: upC(m._day) }}>{(m._dayPct >= 0 ? "+" : "") + m._dayPct.toFixed(1)}%</span>
                                        )}
                                        <span style={{ fontSize: 12, fontWeight: 700, color: upC(m._day), minWidth: 64, textAlign: "right" }}>{(m._day >= 0 ? "+" : "") + wonCompact(m._day)}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                    <button onClick={goHoldings}
                        style={{ display: "block", width: "100%", background: "transparent", border: "none", borderTop: `1px solid ${C.line}`, padding: "10px 0", fontFamily: FONT, fontSize: 12.5, fontWeight: 800, color: C.vg, cursor: "pointer", textAlign: "center" }}>
                        보유종목 전체 보기 →
                    </button>
                </div>
            )}

            {/* ── ② 시장 브리핑 카드 ── */}
            <div style={card}>
                {!brief ? (
                    <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>
                        {briefFailed ? "시장 브리핑 준비 중 — 매일 아침 07:30 발행돼요" : "시장 브리핑 수신 중…"}
                    </div>
                ) : (
                    <div>
                        {/* 1면 배너 — 지수 레벨 + 큰 등락% + 흐름 한 줄. 구분선은 아래 섹션이 각자 소유 */}
                        {banner && (
                            <div>
                                <div style={{ display: "flex", gap: narrow ? 20 : 28, alignItems: "flex-end", flexWrap: "wrap" }}>
                                    {[["코스피", banner.kospi, banner.kospi_close], ["코스닥", banner.kosdaq, banner.kosdaq_close]].map(([lb, pct, lv]: any) => (
                                        <div key={lb}>
                                            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                                                <span style={{ fontSize: 12.5, fontWeight: 800, color: C.ink }}>{lb}</span>
                                                {fmtLevel(lv) && <span style={{ fontSize: 11.5, fontWeight: 600, color: C.faint, fontVariantNumeric: "tabular-nums" }}>{fmtLevel(lv)}</span>}
                                            </div>
                                            <div style={{ marginTop: 2, fontSize: narrow ? 22 : 25, fontWeight: 800, letterSpacing: "-0.7px", color: pctColor(pct), fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}>{fmtPct(pct)}</div>
                                        </div>
                                    ))}
                                    <div style={{ marginLeft: "auto", alignSelf: "flex-start", fontSize: 10.5, fontWeight: 600, color: C.faint, whiteSpace: "nowrap" }}>
                                        {banner.date} 종가{Number(brief.warnings_n) > 0 ? " · 시장경보 " + brief.warnings_n : ""}
                                    </div>
                                </div>
                                {banner.headline && (
                                    <div style={{ marginTop: 9, fontSize: narrow ? 14 : 15, fontWeight: 800, letterSpacing: "-0.2px", color: C.ink, lineHeight: 1.45 }}>{banner.headline}</div>
                                )}
                            </div>
                        )}

                        {/* 섹션들 */}
                        {secs.map((s: any, si: number) => {
                            const isBannerSec = si === 0 && !!banner
                            const allItems: any[] = (s.items || []).filter((it: any) => !isBannerSec || (it.name !== "지수" && it.name !== "흐름"))
                            const open = !!openSec[s.title]
                            const items = open ? allItems : allItems.slice(0, PER_SECTION)
                            const extra = allItems.length - PER_SECTION
                            const firstMover = items.findIndex((it: any) => it.mover)
                            if (!allItems.length && !isBannerSec) return null
                            // 섹션 경계 = hairline + 여백 16/16 (사이 32 : 안 7 ≈ 4.5배). 첫 섹션이 카드 최상단이면 선 없음.
                            const divided = !(si === 0 && !banner)
                            return (
                                <div key={si} style={{
                                    marginTop: divided ? 16 : 0,
                                    paddingTop: divided ? 16 : 0,
                                    borderTop: divided ? `1px solid ${C.line}` : "none",
                                }}>
                                    <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                                        <span style={secTitle}>{s.title}</span>
                                        <span style={secNote}>{isBannerSec ? "섹터 · 거래대금 · 같은 날 공시" : s.note}</span>
                                    </div>
                                    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 7 }}>
                                        {items.map((it: any, i: number) => (
                                            <div key={i}>
                                                {isBannerSec && it.mover && i === firstMover && (
                                                    <div style={{ fontSize: 10.5, fontWeight: 700, color: C.faint, letterSpacing: "0.3px", margin: "6px 0 7px", paddingTop: 9, borderTop: `1px dashed ${C.line}` }}>
                                                        같은 날 공시와 함께 움직인 종목
                                                    </div>
                                                )}
                                                <div style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: narrow ? 12.5 : 13, lineHeight: 1.5 }}>
                                                    {/* 종목명 = ink 700 + 흐린 밑줄. 보라는 액션 전용 (섹션 제목과의 위계 역전 방지) */}
                                                    <span onClick={() => goStockTk(String(it.ticker || ""))}
                                                        style={{
                                                            flexShrink: 0, fontWeight: 700,
                                                            color: it.ticker ? C.ink : C.faint,
                                                            cursor: it.ticker ? "pointer" : "default",
                                                            textDecoration: it.ticker ? "underline" : "none",
                                                            textDecorationColor: C.line,
                                                            textUnderlineOffset: 3,
                                                        }}>
                                                        {it.name || it.ticker}
                                                    </span>
                                                    {it.mover && it.text ? moverText(String(it.text)) : (
                                                        <span style={{ color: C.sub, fontWeight: 600, minWidth: 0 }}>
                                                            {it.text || (it.date ? "예상일 " + String(it.date).slice(5) : "")}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                    {extra > 0 && (
                                        <button onClick={() => setOpenSec((o) => ({ ...o, [s.title]: !open }))}
                                            style={{ border: "none", background: "transparent", cursor: "pointer", fontFamily: FONT, fontSize: 11.5, fontWeight: 700, color: C.vg, padding: "7px 0 0" }}>
                                            {open ? "접기" : "+" + extra + "건 더보기"}
                                        </button>
                                    )}
                                </div>
                            )
                        })}

                        {/* 면책 푸터 */}
                        <div style={{ fontSize: 10, color: C.faint, fontWeight: 600, marginTop: 16, paddingTop: 11, borderTop: `1px solid ${C.line}`, lineHeight: 1.5, letterSpacing: "0.2px" }}>
                            {brief.disclaimer || "전부 공시·수집 사실 · 점수·추천 아님"}
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}

addPropertyControls(PublicMorningBriefing, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    loginUrl: { type: ControlType.String, title: "Login URL", defaultValue: "/login" },
    holdingsUrl: { type: ControlType.String, title: "Holdings URL", defaultValue: "/holdings" },
    stockPath: { type: ControlType.String, title: "Stock Path (KR)", defaultValue: "/stock" },
    usStockPath: { type: ControlType.String, title: "Stock Path (US)", defaultValue: "/us/stock" },
    briefUrl: { type: ControlType.String, title: "Briefing JSON", defaultValue: BRIEF_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * 모닝 브리핑 — 홈 최상단 카드 (단일 채널, PM 2026-07-05 · project_daily_briefing_design).
 *
 * 데이터 = daily_briefing.json (daily_briefing_builder — 기존 발행 피드 재조립, 아침 07:30 KST).
 * 🚨 RULE 7 — 전 항목 = 일어난 사실 + 예정 사실(자체계산 예상 창 라벨). 점수·추천 0.
 * 🚨 RULE 6 — LLM 0 (결정론 조립). 문구 전부 빌더 사전 작성.
 * 종목 클릭 → /stock?q=. cache-fallback(sessionStorage). 캔버스 = SAMPLE.
 *
 * 시각 = 사파리 창 목업 + 디스패치 스트림 (PM 확정 2026-07-05).
 *   로드 시 브리핑 줄이 순차 등장(디스패치가 출력되어 오는 느낌) — 세션 1회, prefers-reduced-motion 존중.
 *   🚨 RULE 6 정합: AI 챗 타이핑 아님(챗버블 X, "생성 중" 문구 X). 메타포 = 리서치 데스크 디스패치 수신.
 *   창은 테마 추종(다크모드 존중). 보라 = 기능 링크만. 텍스트·수치 = 무채 (PM 2026-07-05).
 *   폰트 = Pretendard 단일 (사이트 표준 통일 · EntranceMap 정합, mono/serif 미사용).
 *
 * 📰 1면 배너 (2026-07-11 PM "더 강조") — 첫 섹션의 recap(빌더 v2)을 섹션 목록 위
 *   제호 직하 배너로 승격: 지수 레벨(금융위 공공데이터, 청정) + 큰 등락%(KR 관례
 *   상승 빨강/하락 파랑) + 흐름 한 줄(breadth 사실 파생 문장, 인과 0). 섹터·병기
 *   상세는 섹션 01 에 유지. recap 없으면(구 데이터) 배너 생략 — 하위호환.
 */
const LIGHT = {
    page: "#f2f4f6", chrome: "#e9ebee", chromeLine: "#d8dbe0", addr: "#ffffff", addrInk: "#8b95a1",
    card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", violet: "#6c5ce7",
    up: "#f04452", down: "#3182f6",
}
const DARK = {
    page: "#16181d", chrome: "#2a2e37", chromeLine: "#363b45", addr: "#1a1d24", addrInk: "#6b7684",
    card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684", line: "#2b2f37", violet: "#a98bff",
    up: "#f04452", down: "#5b9bff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const DATA_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/daily_briefing.json"
const PER_SECTION = 4 // 섹션당 기본 노출, 초과 = "+N건" 접힘
const STEP = 90 // 스트림 줄 간격(ms)
const ANIM_KEY = "daily_briefing_anim_v1" // 세션 1회 재생 플래그

const SAMPLE = {
    date: "2026-07-05", weekday: "일", warnings_n: 0,
    sections: [
        { title: "지난 거래일 시장", note: "기준 07/09 · 금융위 공공데이터 · 공시 병기 = 사실, 인과 해석 아님",
          recap: { date: "07/09", kospi: 0.62, kosdaq: 1.15, kospi_close: 7291.91, kosdaq_close: 794.0,
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
            { ticker: "402340", name: "SK스퀘어", text: "SK스퀘어 · 12,111,300주 매수 (07-01)" },
        ] },
    ],
    disclaimer: "전부 공시·수집 사실과 자체계산 예상 창 · 점수·추천·매매의견 아님",
}

function readBodyDark(): boolean {
    // 첫 페인트 flash 방지 — body 속성 미설정(마운트 직후) 시 토글 저장 선호(localStorage) → OS 순 폴백.
    // PublicThemeToggle 이 verity_theme 로 저장 + body[data-framer-theme] 설정 = 동일 소스라 첫 페인트부터 정합.
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
export default function PublicDailyBriefing(props: {
    width?: number; dark?: boolean; dataUrl?: string; stockPath?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    // 첫 페인트부터 실제 테마로 시작(캔버스는 prop) — 로딩 창 반대색 flash 제거.
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)
    const [failed, setFailed] = useState(false)
    const [openSec, setOpenSec] = useState<Record<string, boolean>>({})
    const [streaming, setStreaming] = useState(false)

    // 스트림 애니 재생 여부 = 세션 첫 방문 + 모션 허용 + 라이브(캔버스 X). useState 초기화 1회 확정.
    const [wantAnim] = useState<boolean>(() => {
        if (typeof window === "undefined") return false
        try {
            if (RenderTarget.current() === RenderTarget.canvas) return false
            if (sessionStorage.getItem(ANIM_KEY)) return false
            if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return false
            return true
        } catch (e) { return false }
    })

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
        const fallback = () => {
            try {
                const c = sessionStorage.getItem("daily_briefing")
                if (alive && c) { setData(JSON.parse(c)); return }
            } catch (e) { /* ignore */ }
            if (alive) setFailed(true)
        }
        fetch(props.dataUrl || DATA_URL, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                if (d && Array.isArray(d.sections)) {
                    setData(d)
                    try { sessionStorage.setItem("daily_briefing", JSON.stringify(d)) } catch (e) { /* ignore */ }
                } else fallback()
            })
            .catch(fallback)
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    // 데이터 도착 + wantAnim → 스트림 인디케이터 켜고 세션 플래그 소인, 총 재생시간 후 종료.
    useEffect(() => {
        if (!wantAnim || !data || onCanvas) return
        try { sessionStorage.setItem(ANIM_KEY, "1") } catch (e) { /* ignore */ }
        setStreaming(true)
        const rows = (data.sections || []).reduce((n: number, s: any) => n + 1 + Math.min((s.items || []).length, PER_SECTION), 0) + 2
        const t = setTimeout(() => setStreaming(false), rows * STEP + 420)
        return () => clearTimeout(t)
    }, [wantAnim, data, onCanvas])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const stockPath = props.stockPath || "/stock"

    const go = (tk: string) => {
        if (onCanvas || typeof window === "undefined" || !tk) return
        try { window.location.href = `${stockPath}?q=${encodeURIComponent(tk)}` } catch (e) { /* ignore */ }
    }

    // 스트림 등장 스타일 (지연 = 줄 순번 × STEP). 미재생 시 빈 객체.
    const sIn = (idx: number): CSSProperties =>
        wantAnim ? { opacity: 0, animation: `dbStream 340ms ease ${idx * STEP}ms forwards` } : {}

    // 등락 색 (KR 관례: 상승 빨강 / 하락 파랑 / 보합 무채)
    const pctColor = (v: number) => (v > 0 ? C.up : v < 0 ? C.down : C.sub)
    const fmtPct = (v: number) => `${v > 0 ? "+" : ""}${Number(v).toFixed(2)}%`
    const fmtLevel = (v: any) => (typeof v === "number" && isFinite(v) ? v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "")

    // 배경 transparent — 홈 최상단 카드. 자기 page hex 칠하면 Framer 페이지 dark bg(#0f1318)와 어긋나 밝은 사각형으로 튐(윈도우 목업만 남기고 프레임은 페이지에 블렌드).
    const wrap: CSSProperties = {
        width: props.width || 380, maxWidth: "100%", fontFamily: FONT,
        background: "transparent", padding: "6px 14px 10px", boxSizing: "border-box",
    }

    // 사파리 창 크롬 (트래픽라이트 + 주소 필 + 스트림 인디케이터)
    const windowShell = (body: React.ReactNode) => (
        <div style={{
            background: C.card, borderRadius: 12, overflow: "hidden",
            border: `1px solid ${C.chromeLine}`,
            boxShadow: isDark ? "0 8px 28px rgba(0,0,0,0.40)" : "0 6px 22px rgba(31,41,55,0.12)",
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 12px", height: 34, background: C.chrome, borderBottom: `1px solid ${C.chromeLine}` }}>
                <div style={{ display: "flex", gap: 6 }}>
                    <span style={{ width: 11, height: 11, borderRadius: "50%", background: "#ff5f57" }} />
                    <span style={{ width: 11, height: 11, borderRadius: "50%", background: "#febc2e" }} />
                    <span style={{ width: 11, height: 11, borderRadius: "50%", background: "#28c840" }} />
                </div>
                <div style={{ flex: 1, display: "flex", justifyContent: "center", minWidth: 0 }}>
                    <div style={{ maxWidth: 240, width: "100%", background: C.addr, borderRadius: 7, padding: "3px 10px", display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
                        <span style={{ fontSize: 10.5, fontWeight: 600, color: C.addrInk, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>alphanest · 모닝 브리핑</span>
                        {streaming && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#28c840", flexShrink: 0, animation: "dbPulse 900ms ease infinite" }} />}
                    </div>
                </div>
                <div style={{ width: 40 }} />
            </div>
            {body}
        </div>
    )

    if (!data) {
        return (
            <div style={wrap}>
                {windowShell(
                    <div style={{ padding: "20px", fontSize: 12.5, color: C.faint, fontWeight: 600 }}>
                        {failed ? "브리핑을 불러오지 못했어요 — 새로고침 해주세요" : "모닝 브리핑 수신 중…"}
                    </div>
                )}
            </div>
        )
    }

    const dateLine = data.date
        ? `${String(data.date).replace(/-/g, ".")} (${data.weekday || ""}) · 오전 07:30 발행`
        : "매일 아침 07:30 발행"

    const secs: any[] = data.sections || []
    // 📰 1면 배너 = 첫 섹션의 recap (있을 때만). 배너 승격 시 그 섹션 items 에서 지수/흐름 행 제외.
    const banner = secs.length && secs[0].recap && typeof secs[0].recap.kospi === "number" ? secs[0].recap : null

    // 섹션별 스트림 시작 순번 (배너 2줄 + 접힘 기준 가시 줄 수 누적)
    let base = banner ? 2 : 0
    const secBase: number[] = []
    for (const s of secs) { secBase.push(base); base += 1 + Math.min((s.items || []).length, PER_SECTION) }

    // 병기(mover) 행 — "+13.2% · 같은 날 공시: …" 앞 % 만 등락색으로 분리 렌더
    const moverText = (t: string) => {
        const cut = t.indexOf(" · ")
        if (cut < 0) return <span style={{ color: C.sub, fontWeight: 600 }}>{t}</span>
        const pct = t.slice(0, cut)
        const rest = t.slice(cut)
        const col = pct.startsWith("+") ? C.up : pct.startsWith("-") || pct.startsWith("−") ? C.down : C.sub
        return (
            <span style={{ minWidth: 0 }}>
                <span style={{ color: col, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{pct}</span>
                <span style={{ color: C.sub, fontWeight: 600 }}>{rest}</span>
            </span>
        )
    }

    return (
        <div style={wrap}>
            <style>{`@keyframes dbStream{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}@keyframes dbPulse{0%,100%{opacity:0.35}50%{opacity:1}}`}</style>
            {windowShell(
                <div>
                    {/* 제호(masthead) — 즉시 노출 */}
                    <div style={{ padding: "16px 18px 0" }}>
                        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "1.5px", color: C.faint }}>AlphaNest · 데일리 리서치 노트</div>
                        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, marginTop: 3 }}>
                            <span style={{ fontSize: 19, fontWeight: 800, letterSpacing: "-0.5px", color: C.ink, lineHeight: 1.1 }}>모닝 브리핑</span>
                            {Number(data.warnings_n) > 0 && (
                                <span style={{ fontSize: 10.5, fontWeight: 700, color: C.faint, whiteSpace: "nowrap" }}>시장경보 {data.warnings_n}</span>
                            )}
                        </div>
                        <div style={{ marginTop: 5, fontSize: 11, fontWeight: 600, color: C.faint, letterSpacing: "0.2px" }}>{dateLine}</div>
                        <div style={{ marginTop: 13, borderTop: `2px solid ${C.ink}` }} />
                        <div style={{ marginTop: 2, borderTop: `1px solid ${C.line}` }} />

                        {/* 📰 1면 배너 — 지수 레벨+등락%(금융위 공공데이터 사실) + 흐름 한 줄 */}
                        {banner && (
                            <div style={{ padding: "14px 0 13px", borderBottom: `1px solid ${C.line}` }}>
                                <div style={{ display: "flex", gap: 26, alignItems: "flex-end", ...sIn(0) }}>
                                    {[["코스피", banner.kospi, banner.kospi_close], ["코스닥", banner.kosdaq, banner.kosdaq_close]].map(([lb, pct, lv]: any) => (
                                        <div key={lb}>
                                            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                                                <span style={{ fontSize: 11.5, fontWeight: 800, color: C.ink }}>{lb}</span>
                                                {fmtLevel(lv) && <span style={{ fontSize: 11, fontWeight: 600, color: C.faint, fontVariantNumeric: "tabular-nums" }}>{fmtLevel(lv)}</span>}
                                            </div>
                                            <div style={{ marginTop: 2, fontSize: 27, fontWeight: 800, letterSpacing: "-0.8px", color: pctColor(pct), fontVariantNumeric: "tabular-nums", lineHeight: 1.1 }}>{fmtPct(pct)}</div>
                                        </div>
                                    ))}
                                    <div style={{ marginLeft: "auto", fontSize: 10, fontWeight: 600, color: C.faint, whiteSpace: "nowrap" }}>기준 {banner.date} 종가</div>
                                </div>
                                {banner.headline && (
                                    <div style={{ marginTop: 9, fontSize: 14, fontWeight: 800, letterSpacing: "-0.2px", color: C.ink, lineHeight: 1.45, ...sIn(1) }}>{banner.headline}</div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* 섹션 — 줄 순차 스트림 등장 */}
                    <div style={{ padding: "0 18px 16px" }}>
                        {secs.map((s: any, si: number) => {
                            const isBannerSec = si === 0 && !!banner
                            const allItems: any[] = (s.items || []).filter((it: any) => !isBannerSec || (it.name !== "지수" && it.name !== "흐름"))
                            const open = !!openSec[s.title]
                            const items = open ? allItems : allItems.slice(0, PER_SECTION)
                            const extra = allItems.length - PER_SECTION
                            const firstMover = items.findIndex((it: any) => it.mover)
                            return (
                                <div key={si} style={si === 0 ? { marginTop: 15 } : { marginTop: 15, paddingTop: 15, borderTop: `1px solid ${C.line}` }}>
                                    <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap", ...sIn(secBase[si]) }}>
                                        <span style={{ fontSize: 11, fontWeight: 700, color: C.faint, letterSpacing: "0.5px", fontVariantNumeric: "tabular-nums" }}>{String(si + 1).padStart(2, "0")}</span>
                                        <span style={{ fontSize: 13, fontWeight: 800, color: C.ink, letterSpacing: "-0.2px" }}>{s.title}</span>
                                        {isBannerSec ? (
                                            <span style={{ fontSize: 10, fontWeight: 600, color: C.faint }}>섹터 · 거래대금 · 같은 날 공시</span>
                                        ) : (
                                            <span style={{ fontSize: 10, fontWeight: 600, color: C.faint }}>{s.note}</span>
                                        )}
                                    </div>

                                    <div style={{ marginTop: 7, paddingLeft: 26, display: "flex", flexDirection: "column", gap: 5 }}>
                                        {items.map((it: any, i: number) => (
                                            <div key={i}>
                                                {isBannerSec && it.mover && i === firstMover && (
                                                    <div style={{ fontSize: 10, fontWeight: 700, color: C.faint, letterSpacing: "0.3px", margin: "7px 0 5px", paddingTop: 8, borderTop: `1px dashed ${C.line}` }}>
                                                        같은 날 공시와 함께 움직인 종목
                                                    </div>
                                                )}
                                                <div style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 12, lineHeight: 1.45, ...(i < PER_SECTION ? sIn(secBase[si] + 1 + i) : {}) }}>
                                                    <span onClick={() => go(String(it.ticker || ""))}
                                                        style={{ flexShrink: 0, fontWeight: 800, color: it.ticker ? C.violet : C.faint, cursor: it.ticker ? "pointer" : "default" }}>
                                                        {it.name || it.ticker}
                                                    </span>
                                                    {it.mover && it.text ? moverText(String(it.text)) : (
                                                        <span style={{ color: C.sub, fontWeight: 600, minWidth: 0 }}>
                                                            {it.text || (it.date ? `예상일 ${String(it.date).slice(5)}` : "")}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                    {extra > 0 && (
                                        <button onClick={() => setOpenSec((o) => ({ ...o, [s.title]: !open }))}
                                            style={{ border: "none", background: "transparent", cursor: "pointer", fontFamily: FONT, fontSize: 11, fontWeight: 700, color: C.sub, padding: "6px 0 0 26px", }}>
                                            {open ? "접기" : `+${extra}건 더보기`}
                                        </button>
                                    )}
                                </div>
                            )
                        })}

                        {/* 푸터 — 하단 룰 + 면책 */}
                        <div style={{ fontSize: 9.5, color: C.faint, fontWeight: 600, marginTop: 15, paddingTop: 12, borderTop: `2px solid ${C.ink}`, lineHeight: 1.5, letterSpacing: "0.2px", ...sIn(base) }}>
                            {data.disclaimer || "전부 공시·수집 사실 · 점수·추천 아님"}
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}

addPropertyControls(PublicDailyBriefing, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DATA_URL },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * 관점 지도 — AlphaNest 탐색. 욕구 · 경기 체질 · 자사주 3탭.
 * 데이터(Blob): perspective_maps.json (분류·집계 사실만).
 *
 * 🚨 재설계(2026-07-04): 깔끔·심플 — 카테고리 pill(얇은 라인 아이콘) 선택 → 종목 그리드(로고+국기, 최대 15개 5×3, 더보기).
 *   복잡한 피라미드/스펙트럼 제거. 종목이 주인공(크게). shimmer 스켈레톤.
 * 🚨 RULE 7 — 점수·랭킹·추천 0. 분류 기준 공개. 카운트=사실. "관점 = 탐색 렌즈". RULE 6 — LLM narrative 0.
 * 다크모드 자가감지. cache-fallback. 토스 소프트 유지.
 * ※ leaders = 카테고리당 최대 20개(빌더 LEADERS_N), 시총·마진·섹터 enrich → 규모순/수익순 정렬 + 카드 요약.
 *   구 blob(필드 부재) 폴백 시 정렬 UI 자동 숨김(hasSummary 가드).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", track: "#eef0f3", hi: "#f6f7f9",
}
const DARK = {
    bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440", track: "#242830", hi: "#2e333c",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DATA_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/perspective_maps.json"
const LIMIT = 15 // 기본 노출 (5×3), 초과분 더보기

// 카테고리 → 얇은 라인 아이콘 (모노크롬 · currentColor 상속, 이모지 아님). 24x24 stroke path.
const ICON: Record<string, string[]> = {
    survival: ["M12 21C7 17 4 13.5 4 10a4 4 0 018-1 4 4 0 018 1c0 3.5-3 7-8 11z"],           // 필수·건강 = 하트(생명)
    safety: ["M12 3l7 2.5V11c0 4.2-2.9 7.4-7 8.8C7.9 18.4 5 15.2 5 11V5.5L12 3z", "M9 11l2 2 4-4"], // 안전 = 방패+체크
    belonging: ["M5 5h14v9H8l-3 3V5z"],                                                          // 관계·연결 = 말풍선
    esteem: ["M4 9l3.5 3L12 6l4.5 6L20 9l-1.5 9h-13L4 9z"],                                       // 프리미엄·품격 = 왕관
    growth: ["M4 14l5-5 3 3 7-7", "M17 5h4v4"],                                                   // 성장·배움 = 상승 추세
    infra: ["M12 4l8 4-8 4-8-4 8-4z", "M4 12l8 4 8-4", "M4 16l8 4 8-4"],                          // 산업 기반 = 레이어
    steady: ["M12 6v14", "M6 13a6 6 0 0012 0", "M4.5 13H7", "M17 13h2.5", "M9.2 5a3 3 0 015.6 0"], // 안정 = 앵커
    middle: ["M12 4v15", "M7 8h10", "M6 20h12", "M7 8l-3 6a3 3 0 006 0z", "M17 8l-3 6a3 3 0 006 0z"], // 중간 = 저울
    swing: ["M3 12h4l3-8 4 16 3-8h4"],                                                            // 민감 = 변동 파형
    steady_buy: ["M17.7 7A7 7 0 006 8", "M17 4v3h-3", "M6.3 17A7 7 0 0018 16", "M7 20v-3h3"],     // 꾸준 매입 = 순환
    some_buy: ["M12 4v9", "M8.5 9.5L12 13l3.5-3.5", "M5 15v4h14v-4"],                             // 매입 = 담기(↓)
    net_sell: ["M12 13V4", "M8.5 7.5L12 4l3.5 3.5", "M5 15v4h14v-4"],                             // 처분 = 내보내기(↑)
}
function Icon(props: { k: string; size: number }) {
    const paths = ICON[props.k]
    if (!paths) return null
    return (
        <svg width={props.size} height={props.size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" style={{ display: "block", flexShrink: 0 }}>
            {paths.map((d, i) => <path key={i} d={d} />)}
        </svg>
    )
}

const FLAG = "https://hatscripts.github.io/circle-flags/flags/"
const STK_LOGO = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
function isKR(tk: any): boolean { return /^\d{6}$/.test(String(tk || "")) }

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch (e) { return "" }
}
function n0(v: any): string {
    const x = Number(v)
    return isFinite(x) ? Math.round(x).toLocaleString("en-US") : "—"
}

// leaders 정렬·요약 헬퍼 (전부 사실값 나열 — 점수·랭킹 아님, RULE 7)
function marginOf(l: any): number | null {
    if (l && l.op_margin != null && isFinite(Number(l.op_margin))) return Number(l.op_margin)
    if (l && l.net_margin != null && isFinite(Number(l.net_margin))) return Number(l.net_margin)
    return null
}
function marginLabel(l: any): string {
    if (l && l.op_margin != null) return "영업 " + l.op_margin + "%"
    if (l && l.net_margin != null) return "순익 " + l.net_margin + "%"
    return ""
}
function metricOf(l: any, sortKey: string): string {
    return sortKey === "profit" ? marginLabel(l) : (l && l.cap_disp ? String(l.cap_disp) : "")
}
// 카드에 정렬 가능한 요약 필드(시총/마진)가 하나라도 있으면 정렬 UI 노출 (구 blob 폴백 시 숨김)
function hasSummary(list: any[]): boolean {
    return (list || []).some((l) => (l && l.cap_disp) || marginOf(l) != null)
}

// 종목 카드 (그리드 아이템) — 로고 + 국기 배지 + 이름 + 요약(규모/수익). 로고 실패 시 이니셜.
function StockCard(props: { l: any; C: any; sortKey: string; onGo: (t: string) => void }) {
    const { l, C, sortKey, onGo } = props
    const ticker = String((l && l.ticker) || "")
    const name = (l && l.name) || ""
    const [err, setErr] = useState(false)
    const kr = isKR(ticker)
    const initial = ((name || "?").trim().charAt(0)) || "?"
    const metric = metricOf(l, sortKey)
    const sector = (l && l.sector) || ""
    const tip = name + (sector ? " · " + sector : "")
    return (
        <div onClick={() => onGo(ticker)} role="button" tabIndex={0} title={tip}
            style={{ background: C.card, borderRadius: 12, padding: "12px 8px", height: 108, boxSizing: "border-box", cursor: "pointer", textAlign: "center", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 7, minWidth: 0 }}>
            <div style={{ position: "relative", width: 34, height: 34, flexShrink: 0 }}>
                {!err && ticker ? (
                    <img src={STK_LOGO + ticker + ".png"} alt="" width={34} height={34} loading="lazy" onError={() => setErr(true)}
                        style={{ width: 34, height: 34, borderRadius: 9, objectFit: "cover", background: "#fff", display: "block" }} />
                ) : (
                    <span style={{ width: 34, height: 34, borderRadius: 9, background: C.violetSoft, color: C.violet, fontSize: 15, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center" }}>{initial}</span>
                )}
                <img src={FLAG + (kr ? "kr" : "us") + ".svg"} alt="" width={14} height={14}
                    style={{ position: "absolute", right: -3, bottom: -3, width: 14, height: 14, borderRadius: "50%", border: `1.5px solid ${C.card}`, background: C.card, display: "block" }} />
            </div>
            {/* 이름 = 1줄 말줄임 + hover 풀네임+섹터(title). 길면 "삼성바이오로…" 식으로 잘림. */}
            <div style={{ fontSize: 11.5, fontWeight: 700, color: C.ink, lineHeight: 1.3, width: "100%", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</div>
            {/* 요약 = 활성 정렬값(규모=시총 / 수익=마진). 사실값, 없으면 섹터, 둘 다 없으면 미표시 */}
            {metric || sector ? (
                <div style={{ fontSize: 10.5, fontWeight: 700, color: metric ? C.violet : C.faint, lineHeight: 1.2, width: "100%", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontVariantNumeric: "tabular-nums" }}>{metric || sector}</div>
            ) : null}
        </div>
    )
}

// 캔버스 프리뷰 전용 SAMPLE.
const SAMPLE = {
    _meta: { generated_at: "2026-07-04T13:20:05+09:00" },
    desire: {
        tiers: [
            { key: "survival", label: "필수·건강", n_kr: 397, n_us: 250, median_op_margin: 6.8, desc: "먹고 마시고 아프지 않게 — 수요가 유행을 안 탐", leaders: [{ ticker: "005930", name: "삼성전자", mkt: "KR", cap: 5000000, cap_disp: "500조", op_margin: 10.2, sector: "IT" }, { ticker: "000660", name: "SK하이닉스", mkt: "KR", cap: 1500000, cap_disp: "150조", op_margin: 20.5, sector: "IT" }, { ticker: "LLY", name: "일라이릴리", mkt: "US", cap: 982800, cap_disp: "$982.8B", net_margin: 31.7, sector: "제약", revenue: 65179000000 }, { ticker: "JNJ", name: "존슨앤존슨", mkt: "US", cap: 556800, cap_disp: "$556.8B", net_margin: 22.9, sector: "제약", revenue: 94193000000 }, { ticker: "068270", name: "셀트리온", mkt: "KR", cap: 400000, cap_disp: "40조", op_margin: 20.1, sector: "헬스케어" }, { ticker: "207940", name: "삼성바이오로직스", mkt: "KR", cap: 658000, cap_disp: "65.8조", op_margin: 3.7, sector: "헬스케어" }] },
            { key: "safety", label: "안전·보장", n_kr: 67, n_us: 232, median_op_margin: 11.6, desc: "지키고 대비하는 수요 — 보험·방산·보안", leaders: [{ ticker: "012450", name: "한화에어로" }, { ticker: "032830", name: "삼성생명" }] },
            { key: "belonging", label: "관계·연결", n_kr: 98, n_us: 76, median_op_margin: 7.0, desc: "잇고 어울리는 수요 — 통신·콘텐츠·모임", leaders: [{ ticker: "035420", name: "NAVER" }, { ticker: "035720", name: "카카오" }] },
            { key: "esteem", label: "프리미엄·품격", n_kr: 43, n_us: 33, median_op_margin: 6.0, desc: "돋보이고 싶은 수요 — 명품·뷰티·프리미엄", leaders: [{ ticker: "090430", name: "아모레퍼시픽" }] },
            { key: "growth", label: "성장·배움", n_kr: 10, n_us: 14, median_op_margin: 11.7, desc: "배우고 성장하는 수요 — 교육·자기계발", leaders: [{ ticker: "095720", name: "웅진씽크빅" }] },
            { key: "infra", label: "산업 기반", n_kr: 1006, n_us: 900, median_op_margin: 6.0, desc: "욕구를 직접 팔진 않지만 위 전부를 떠받치는 산업 — B2B·부품·장비", leaders: [{ ticker: "042700", name: "한미반도체" }, { ticker: "373220", name: "LG에너지솔루션" }] },
        ],
    },
    cycle: {
        basis: "연간 매출 YoY 변동성(≥4년 실측 종목만)",
        buckets: [
            { key: "steady", label: "매출 꾸준", n: 503, vol_range: [0.1, 5.3], desc: "경기와 덜 흔들리는 매출", leaders: [{ ticker: "033780", name: "KT&G" }, { ticker: "AAPL", name: "애플" }, { ticker: "MSFT", name: "마이크로소프트" }] },
            { key: "middle", label: "중간", n: 503, vol_range: [5.3, 12.7], desc: "중간 변동", leaders: [{ ticker: "005380", name: "현대차" }] },
            { key: "swing", label: "매출 출렁", n: 504, vol_range: [12.7, 10074.7], desc: "경기·업황에 크게 흔들리는 매출", leaders: [{ ticker: "000660", name: "SK하이닉스" }] },
        ],
    },
    buyback: {
        basis: "DART 자기주식 취득·처분 공시 건수",
        buckets: [
            { key: "steady_buy", label: "꾸준히 매입", n: 137, desc: "자기주식을 반복 취득", leaders: [{ ticker: "000270", name: "기아" }, { ticker: "005930", name: "삼성전자" }] },
            { key: "some_buy", label: "가끔 매입", n: 52, desc: "취득 공시 확인", leaders: [{ ticker: "175330", name: "JB금융지주" }] },
            { key: "net_sell", label: "처분 많음", n: 81, desc: "처분이 취득보다 많음", leaders: [{ ticker: "028050", name: "삼성E&A" }] },
        ],
    },
}

export default function PublicPerspectiveMaps(props: { width?: number; dark?: boolean; dataUrl?: string; stockPath?: string }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)
    const [tab, setTab] = useState<string>("desire")
    const [sel, setSel] = useState<Record<string, string>>({})
    const [showAll, setShowAll] = useState<Record<string, boolean>>({})
    const [sortKey, setSortKey] = useState<string>("cap") // cap=규모순 / profit=수익순

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
                if (alive && d && d.desire) {
                    setData(d)
                    try { sessionStorage.setItem("perspective_maps", JSON.stringify(d)) } catch (e) {}
                }
            })
            .catch(() => {
                try { const c = sessionStorage.getItem("perspective_maps"); if (alive && c) setData(JSON.parse(c)) } catch (e) {}
            })
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const stockPath = props.stockPath || "/stock"

    const go = (tk: string) => {
        if (onCanvas || typeof window === "undefined" || !tk) return
        try { window.location.href = `${stockPath}?q=${encodeURIComponent(tk)}` } catch (e) {}
    }

    const wrap: CSSProperties = { width: props.width || 380, maxWidth: "100%", fontFamily: FONT, background: C.bg, color: C.ink, padding: 16, boxSizing: "border-box" }

    /* ── 스켈레톤 ── */
    if (!data) {
        const base = C.track, hi = C.hi
        const sk = (wd: any, ht: number, r = 8, mt = 0): CSSProperties => ({
            width: wd, height: ht, marginTop: mt, borderRadius: r, background: base,
            backgroundImage: `linear-gradient(90deg, ${base} 25%, ${hi} 37%, ${base} 63%)`,
            backgroundSize: "800px 100%", animation: "vpmShimmer 1.4s ease-in-out infinite",
        })
        return (
            <div style={wrap}>
                <style>{`@keyframes vpmShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={sk(96, 18, 6)} />
                <div style={sk("70%", 12, 5, 8)} />
                <div style={{ display: "flex", gap: 6, marginTop: 14 }}>
                    {[58, 74, 58].map((wd, i) => <div key={i} style={sk(wd, 32, 10)} />)}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginTop: 12 }}>
                    {[70, 56, 84, 60].map((wd, i) => <div key={i} style={sk(wd, 30, 9)} />)}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(112px, 1fr))", gap: 8, marginTop: 14 }}>
                    {[0, 1, 2, 3, 4].map((i) => <div key={i} style={sk("100%", 82, 12)} />)}
                </div>
            </div>
        )
    }

    // 탭 config (items·count·meta 통일)
    const desireTiers: any[] = (data.desire && data.desire.tiers) || []
    const cycleBuckets: any[] = (data.cycle && data.cycle.buckets) || []
    const buyBuckets: any[] = (data.buyback && data.buyback.buckets) || []

    const cfg = tab === "desire"
        ? {
            items: desireTiers,
            count: (t: any) => (Number(t.n_kr) || 0) + (Number(t.n_us) || 0),
            meta: (t: any) => `국내 ${n0(t.n_kr)} · 해외 ${n0(t.n_us)}${t.median_op_margin != null ? " · 영업이익률 중앙 " + t.median_op_margin + "%" : ""}`,
        }
        : tab === "cycle"
          ? {
                items: cycleBuckets,
                count: (b: any) => Number(b.n) || 0,
                meta: (b: any) => b.vol_range ? `YoY σ ${b.vol_range[0]}~${b.key === "swing" ? b.vol_range[0] + "%+" : b.vol_range[1] + "%"} · ${n0(b.n)}종목` : `${n0(b.n)}종목`,
            }
          : {
                items: buyBuckets,
                count: (b: any) => Number(b.n) || 0,
                meta: (b: any) => `${n0(b.n)}종목 · KR · DART 공시`,
            }

    const items = cfg.items
    const selKey = (sel[tab] && items.some((x) => x.key === sel[tab])) ? sel[tab] : (items[0] ? items[0].key : "")
    const item = items.find((x) => x.key === selKey) || items[0]
    const leadersRaw: any[] = (item && item.leaders) || []
    const canSort = hasSummary(leadersRaw)
    // 정렬 = 사실값 나열(규모=시총 / 수익=마진). 값 없는 종목은 뒤로. cap순은 빌더가 이미 정렬(안정 유지).
    const leaders = (canSort && sortKey === "profit")
        ? [...leadersRaw].sort((a, b) => (marginOf(b) ?? -1e12) - (marginOf(a) ?? -1e12))
        : (canSort ? [...leadersRaw].sort((a, b) => (Number(b.cap) || 0) - (Number(a.cap) || 0)) : leadersRaw)
    const seeAll = !!showAll[tab]
    const shown = seeAll ? leaders : leaders.slice(0, LIMIT)
    const totalCount = items.reduce((a, x) => a + cfg.count(x), 0)

    const hero =
        tab === "desire" ? { big: n0(totalCount) + "종목", small: "인간 욕구 6계층으로 분류 · 탐색 렌즈" }
            : tab === "cycle" ? { big: n0(totalCount) + "종목", small: "연간 매출 변동성 3분위 · 안정 ↔ 민감" }
                : { big: n0(totalCount) + "종목", small: "자기주식 공시 흐름 · 매입 ↔ 처분" }

    const tabBtn = (v: string, lb: string) => (
        <button key={v} onClick={() => setTab(v)} style={{
            border: "none", cursor: "pointer", fontFamily: FONT, padding: "8px 15px", borderRadius: 10,
            fontSize: 13, fontWeight: 800, background: tab === v ? C.violet : C.card, color: tab === v ? "#fff" : C.sub,
        }}>{lb}</button>
    )

    return (
        <div style={wrap}>
            <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: "-0.4px" }}>관점 지도</div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>
                    같은 시장을 다른 렌즈로 — 분류·집계는 전부 공개 기준의 사실
                    {data._meta && data._meta.generated_at ? " · " + fmtAge(data._meta.generated_at) + " 갱신" : ""}
                </div>
            </div>

            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
                {tabBtn("desire", "욕구")}
                {tabBtn("cycle", "경기 체질")}
                {tabBtn("buyback", "자사주")}
            </div>

            {/* 히어로 */}
            <div style={{ background: C.card, borderRadius: 14, padding: "13px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginBottom: 14 }}>
                <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.6px", color: C.ink }}>{hero.big}</div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>{hero.small}</div>
            </div>

            {/* 카테고리 pill 선택 (얇은 라인 아이콘) */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                {items.map((x) => {
                    const active = x.key === selKey
                    return (
                        <button key={x.key} onClick={() => setSel((s) => ({ ...s, [tab]: x.key }))}
                            style={{
                                border: "none", cursor: "pointer", fontFamily: FONT, display: "inline-flex", alignItems: "center", gap: 6,
                                padding: "8px 12px", borderRadius: 11, fontSize: 12.5, fontWeight: 800,
                                background: active ? C.violet : C.card, color: active ? "#fff" : C.ink,
                                boxShadow: active ? "none" : "0 1px 2px rgba(0,0,0,0.04)",
                            }}>
                            <Icon k={x.key} size={15} />
                            {x.label}
                            <span style={{ fontWeight: 700, opacity: 0.75, fontVariantNumeric: "tabular-nums" }}>{n0(cfg.count(x))}</span>
                        </button>
                    )
                })}
            </div>

            {/* 선택 카테고리 헤더 */}
            {item ? (
                <div style={{ marginTop: 16 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ color: C.violet, background: C.violetSoft, borderRadius: 10, padding: 7, display: "inline-flex", flexShrink: 0 }}><Icon k={item.key} size={22} /></span>
                        <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: 15, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px" }}>{item.label}</div>
                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 1 }}>{cfg.meta(item)}</div>
                        </div>
                    </div>
                    {item.desc ? <div style={{ fontSize: 12, color: C.sub, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>{item.desc}</div> : null}

                    {/* 정렬 (규모순 / 수익순) — 요약 필드 있을 때만 */}
                    {canSort ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 12 }}>
                            <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 700, marginRight: 1 }}>정렬</span>
                            {[{ k: "cap", lb: "규모순" }, { k: "profit", lb: "수익순" }].map((o) => {
                                const on = sortKey === o.k
                                return (
                                    <button key={o.k} onClick={() => setSortKey(o.k)}
                                        style={{ border: "none", cursor: "pointer", fontFamily: FONT, padding: "5px 11px", borderRadius: 8, fontSize: 11.5, fontWeight: 800, background: on ? C.violetSoft : C.card, color: on ? C.violet : C.faint, boxShadow: on ? "none" : "0 1px 2px rgba(0,0,0,0.04)" }}>{o.lb}</button>
                                )
                            })}
                            <span style={{ fontSize: 10, color: C.faint, fontWeight: 600, marginLeft: "auto" }}>사실값 · 랭킹 아님</span>
                        </div>
                    ) : null}

                    {/* 종목 그리드 (5×3, 초과 더보기) */}
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(108px, 1fr))", gap: 8, marginTop: 12 }}>
                        {shown.map((l: any, i: number) => (
                            <StockCard key={(l.ticker || "") + i} l={l} C={C} sortKey={sortKey} onGo={go} />
                        ))}
                    </div>
                    {leaders.length > LIMIT ? (
                        <button onClick={() => setShowAll((s) => ({ ...s, [tab]: !seeAll }))}
                            style={{ width: "100%", marginTop: 10, border: "none", cursor: "pointer", fontFamily: FONT, background: C.card, color: C.violet, borderRadius: 10, padding: "10px 0", fontSize: 12.5, fontWeight: 800, boxShadow: "0 1px 2px rgba(0,0,0,0.04)" }}>
                            {seeAll ? "접기" : `더보기 (${leaders.length - LIMIT}개)`}
                        </button>
                    ) : null}
                </div>
            ) : null}

            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 16, lineHeight: 1.5 }}>
                분류 = 탐색용 관점(기준 공개) · 집계 = 공시 사실 · 종목은 대표 예시 · 점수·등급·추천 아님
            </div>
        </div>
    )
}

addPropertyControls(PublicPerspectiveMaps, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DATA_URL },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
})

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * 관점 지도 — AlphaNest 탐색. 욕구 · 매출 안정성 · 자사주 3탭.
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
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", track: "#eef0f3", hi: "#f6f7f9", gTint: "rgba(108,92,231,0.22)",
}
const DARK = {
    bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440", track: "#242830", hi: "#2e333c", gTint: "rgba(169,155,255,0.26)",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DATA_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/perspective_maps.json"
const LIMIT = 15 // 기본 노출 (5×3), 초과분 더보기
// 규모 분포 바 세그먼트 색 (카테고리 구분용 임의 팔레트 — 우열·랭킹 의미 아님)
const CAP_COLORS = ["#6c5ce7", "#00b8d4", "#12b76a", "#f5a623", "#ec4899", "#8b95a1"]

/* 글래스 아이콘 (토스식 glassmorphism, 2026-07-04 교체) — solid(선명 보라) + glass(반투명 틴트) 2레이어.
   glass 겹침부 = 블러 복제(clipPath+feGaussianBlur) 프로스트. 배경 없음 — pill/카드 어디서든 동작.
   도안 = PublicGlassIcon.tsx 와 동일 15종 (컴포넌트 자립 원칙으로 인라인). 활성 pill 은 흰색 오버라이드. */
const _rr = (x: number, y: number, w: number, h: number, r: number): string =>
    `M${x + r} ${y} H${x + w - r} Q${x + w} ${y} ${x + w} ${y + r} V${y + h - r} Q${x + w} ${y + h} ${x + w - r} ${y + h} H${x + r} Q${x} ${y + h} ${x} ${y + h - r} V${y + r} Q${x} ${y} ${x + r} ${y} Z`
const _circ = (cx: number, cy: number, r: number): string =>
    `M${cx - r} ${cy} a${r} ${r} 0 1 0 ${r * 2} 0 a${r} ${r} 0 1 0 ${-r * 2} 0 Z`
const _CARD = _rr(4, 9, 40, 30, 5)
const _COIN = _circ(20, 26, 13)
const _bar = (y: number): string => _rr(7.5, y, 28, 5.5, 2.75)
const GICONS: Record<string, { solid: (a: string) => any; glass: string }> = {
    // 탭 3종 — 욕구(피라미드) / 매출 안정성(카드+라인) / 자사주(금고)
    desire: {
        solid: (a) => <path d="M24 6 L35 25 Q36.5 28 33 28 H15 Q11.5 28 13 25 Z" fill={a} />,
        glass: "M12.5 24 H35.5 L41.5 38.5 Q43 42 39.5 42 H8.5 Q5 42 6.5 38.5 Z",
    },
    cycle: {
        solid: (a) => (
            <g>
                <polyline points="4,31 16,26 28,27.5 44,19" fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" />
                <circle cx={44} cy={19} r={3.2} fill={a} />
            </g>
        ),
        glass: _CARD,
    },
    buyback: {
        solid: (a) => (
            <g>
                <path d="M30.5 27.5 V23.5 a4.75 4.75 0 0 1 9.5 0 V27.5" fill="none" stroke={a} strokeWidth={3.2} strokeLinecap="round" />
                <path d="M31 27 H40 Q43.5 27 43.5 30.5 V37 Q43.5 40.5 40 40.5 H31 Q27.5 40.5 27.5 37 V30.5 Q27.5 27 31 27 Z" fill={a} />
                <circle cx={35.5} cy={33.5} r={2.2} fill="#ffffff" fillOpacity={0.92} />
            </g>
        ),
        glass: _rr(6, 5, 34, 36, 6) + " " + _rr(10.5, 41.5, 8, 3.5, 1.75) + " " + _rr(27.5, 41.5, 8, 3.5, 1.75),
    },
    // 욕구 6계층 — 생존/심리·안전·소속/연결·존중/과시·자아실현·기반/인프라
    survival: {
        solid: (a) => <polyline points="5,24 14,24 18.5,16.5 25,31.5 29,24 43,24" fill="none" stroke={a} strokeWidth={3.6} strokeLinecap="round" strokeLinejoin="round" />,
        glass: "M24 41 C10 32 6 22 10.5 15.5 C14.5 10 21 11 24 16 C27 11 33.5 10 37.5 15.5 C42 22 38 32 24 41 Z",
    },
    safety: {
        solid: (a) => <polyline points="16,24 22,30 33,17" fill="none" stroke={a} strokeWidth={4.5} strokeLinecap="round" strokeLinejoin="round" />,
        glass: "M24 5 L39 11 V22 C39 32 33 38.5 24 43 C15 38.5 9 32 9 22 V11 Z",
    },
    belonging: {
        solid: (a) => (
            <g fill={a}>
                <circle cx={31} cy={14} r={5.5} />
                <path d="M22 34 Q22 24 31 24 Q40 24 40 34 Q40 36 38 36 H24 Q22 36 22 34 Z" />
            </g>
        ),
        glass: _circ(18, 18, 7) + " M6 40 Q6 27 18 27 Q30 27 30 40 Q30 42.5 27.5 42.5 H8.5 Q6 42.5 6 40 Z",
    },
    esteem: {
        solid: (a) => <circle cx={38} cy={12} r={6} fill={a} />,
        glass: "M10 36 L12 17 L20 25 L24 12.5 L28 25 L36 17 L38 36 Q38 38.5 35.5 38.5 H12.5 Q10 38.5 10 36 Z",
    },
    growth: {
        solid: (a) => <path d="M34 6 L36.4 11.6 L42 14 L36.4 16.4 L34 22 L31.6 16.4 L26 14 L31.6 11.6 Z" fill={a} />,
        glass: "M22 12 L25.4 20.2 L34.2 20.8 L27.4 26.5 L29.6 35 L22 30.2 L14.4 35 L16.6 26.5 L9.8 20.8 L18.6 20.2 Z",
    },
    // 기반/인프라 = 공장 (굴뚝·연기 solid + 톱니 지붕 glass)
    infra: {
        solid: (a) => (
            <g fill={a}>
                <path d="M9.5 6.5 Q9.5 5 11 5 H14 Q15.5 5 15.5 6.5 V22 H9.5 Z" />
                <circle cx={19.5} cy={5.5} r={2.7} />
                <circle cx={25} cy={3.8} r={1.9} />
            </g>
        ),
        glass: "M7 39 V23.5 L17.5 17 V23.5 L28 17 V23.5 L38.5 17 V39 Q38.5 41.5 36 41.5 H9.5 Q7 41.5 7 39 Z",
    },
    // 매출 흔들림 3분위 — 같은 카드 + 진폭 S/M/L (세트 일관성)
    steady: {
        solid: (a) => <polyline points="4,25.5 11,22.5 18,25.5 25,22.5 32,25.5 39,22.5 44,24.5" fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" />,
        glass: _CARD,
    },
    middle: {
        solid: (a) => <polyline points="4,28 11,20 18,28 25,20 32,28 39,20 44,26" fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" />,
        glass: _CARD,
    },
    swing: {
        solid: (a) => <polyline points="4,33 11,14 18,33 25,14 32,33 39,14 44,30" fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" />,
        glass: _CARD,
    },
    // 자사주 3분류 — 코인 스택+↑ / 코인+↑ / 코인+↓
    steady_buy: {
        solid: (a) => (
            <g fill="none" stroke={a} strokeWidth={4.5} strokeLinecap="round" strokeLinejoin="round">
                <line x1={36} y1={36} x2={36} y2={16} />
                <polyline points="29,22 36,14.5 43,22" />
            </g>
        ),
        glass: _bar(19) + " " + _bar(26) + " " + _bar(33),
    },
    some_buy: {
        solid: (a) => (
            <g fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round">
                <line x1={36} y1={30} x2={36} y2={18} />
                <polyline points="31,23 36,17.5 41,23" />
            </g>
        ),
        glass: _COIN,
    },
    net_sell: {
        solid: (a) => (
            <g fill="none" stroke={a} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round">
                <line x1={36} y1={18} x2={36} y2={30} />
                <polyline points="31,25 36,30.5 41,25" />
            </g>
        ),
        glass: _COIN,
    },
}
function GIcon(props: { k: string; size: number; a: string; g: string; float?: boolean }) {
    const def = GICONS[props.k]
    if (!def) return null
    // 같은 k 다중 렌더 = 동일 defs 중복(무해). 색은 defs 밖이라 활성/비활성 공존 OK.
    const fid = "vpmf-" + props.k
    const cid = "vpmc-" + props.k
    // key=색 — 활성 전환(색 변경) 시 그룹 재마운트 → 팝/상승 애니메이션 재생 (키프레임 = 컴포넌트 루트 <style>)
    return (
        <svg width={props.size} height={props.size} viewBox="0 0 48 48" fill="none"
            style={{ display: "block", flexShrink: 0, overflow: "visible", animation: props.float ? "vpmFloat 3.4s ease-in-out infinite" : undefined }}>
            <defs>
                <filter id={fid} x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.1" /></filter>
                <clipPath id={cid}><path d={def.glass} /></clipPath>
            </defs>
            <g key={"s" + props.a} className="vpmGiS">{def.solid(props.a)}</g>
            <g key={"g" + props.a} className="vpmGiG">
                <g clipPath={`url(#${cid})`}>
                    <g filter={`url(#${fid})`} opacity={0.85}>{def.solid(props.a)}</g>
                    <path d={def.glass} fill={props.g} />
                </g>
            </g>
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
// 카테고리 합산 시총(억원, FX 환산) → "12,341조" 표기. 규모 분포용.
function capJo(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x <= 0) return ""
    return Math.round(x / 1e4).toLocaleString("en-US") + "조"
}
function hasCapSum(list: any[]): boolean {
    return (list || []).some((i) => Number(i && i.cap_sum) > 0)
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
            { key: "survival", label: "필수·건강", n_kr: 397, n_us: 250, median_op_margin: 6.8, cap_sum: 123410000, desc: "먹고 마시고 아프지 않게 — 수요가 유행을 안 탐", leaders: [{ ticker: "005930", name: "삼성전자", mkt: "KR", cap: 5000000, cap_disp: "500조", op_margin: 10.2, sector: "IT" }, { ticker: "000660", name: "SK하이닉스", mkt: "KR", cap: 1500000, cap_disp: "150조", op_margin: 20.5, sector: "IT" }, { ticker: "LLY", name: "일라이릴리", mkt: "US", cap: 982800, cap_disp: "$982.8B", net_margin: 31.7, sector: "제약", revenue: 65179000000 }, { ticker: "JNJ", name: "존슨앤존슨", mkt: "US", cap: 556800, cap_disp: "$556.8B", net_margin: 22.9, sector: "제약", revenue: 94193000000 }, { ticker: "068270", name: "셀트리온", mkt: "KR", cap: 400000, cap_disp: "40조", op_margin: 20.1, sector: "헬스케어" }, { ticker: "207940", name: "삼성바이오로직스", mkt: "KR", cap: 658000, cap_disp: "65.8조", op_margin: 3.7, sector: "헬스케어" }] },
            { key: "safety", label: "안전·보장", n_kr: 67, n_us: 232, median_op_margin: 11.6, cap_sum: 117170000, desc: "지키고 대비하는 수요 — 보험·방산·보안", leaders: [{ ticker: "012450", name: "한화에어로" }, { ticker: "032830", name: "삼성생명" }] },
            { key: "belonging", label: "관계·연결", n_kr: 98, n_us: 76, median_op_margin: 7.0, cap_sum: 31720000, desc: "잇고 어울리는 수요 — 통신·콘텐츠·모임", leaders: [{ ticker: "035420", name: "NAVER" }, { ticker: "035720", name: "카카오" }] },
            { key: "esteem", label: "프리미엄·품격", n_kr: 43, n_us: 33, median_op_margin: 6.0, cap_sum: 8890000, desc: "돋보이고 싶은 수요 — 명품·뷰티·프리미엄", leaders: [{ ticker: "090430", name: "아모레퍼시픽" }] },
            { key: "growth", label: "성장·교육", n_kr: 10, n_us: 14, median_op_margin: 11.7, cap_sum: 980000, desc: "배우고 성장하는 수요 — 교육·자기계발", leaders: [{ ticker: "095720", name: "웅진씽크빅" }] },
            { key: "infra", label: "산업 기반", n_kr: 1006, n_us: 900, median_op_margin: 6.0, cap_sum: 840610000, desc: "욕구를 직접 팔진 않지만 위 전부를 떠받치는 산업 — B2B·부품·장비", leaders: [{ ticker: "042700", name: "한미반도체" }, { ticker: "373220", name: "LG에너지솔루션" }] },
        ],
    },
    cycle: {
        basis: "연간 매출 YoY 변동성(≥4년 실측 종목만)",
        buckets: [
            { key: "steady", label: "매출 꾸준", n: 503, vol_range: [0.1, 5.3], cap_sum: 497760000, desc: "경기와 덜 흔들리는 매출", leaders: [{ ticker: "033780", name: "KT&G" }, { ticker: "AAPL", name: "애플" }, { ticker: "MSFT", name: "마이크로소프트" }] },
            { key: "middle", label: "중간", n: 503, vol_range: [5.3, 12.7], cap_sum: 252810000, desc: "중간 변동", leaders: [{ ticker: "005380", name: "현대차" }] },
            { key: "swing", label: "매출 출렁", n: 504, vol_range: [12.7, 10074.7], cap_sum: 324900000, desc: "경기·업황에 크게 흔들리는 매출", leaders: [{ ticker: "000660", name: "SK하이닉스" }] },
        ],
    },
    buyback: {
        basis: "DART 자기주식 취득·처분 공시 건수",
        buckets: [
            { key: "steady_buy", label: "꾸준히 매입", n: 137, cap_sum: 1180000, desc: "자기주식을 반복 취득", leaders: [{ ticker: "000270", name: "기아" }, { ticker: "005930", name: "삼성전자" }] },
            { key: "some_buy", label: "가끔 매입", n: 52, cap_sum: 240000, desc: "취득 공시 확인", leaders: [{ ticker: "175330", name: "JB금융지주" }] },
            { key: "net_sell", label: "처분 많음", n: 81, cap_sum: 240000, desc: "처분이 취득보다 많음", leaders: [{ ticker: "028050", name: "삼성E&A" }] },
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
    // 규모 분포 = 카테고리별 합산 시총(cap_sum, 억원 FX 환산) share. 구 blob 폴백 시 바 숨김.
    const capTotal = items.reduce((a, x) => a + (Number(x.cap_sum) || 0), 0)
    const showCapBar = hasCapSum(items) && capTotal > 0

    const hero =
        tab === "desire" ? { big: n0(totalCount) + "종목", small: "인간 욕구 6계층으로 분류 · 탐색 렌즈" }
            : tab === "cycle" ? { big: n0(totalCount) + "종목", small: "연간 매출 변동성 3분위 · 안정 ↔ 민감" }
                : { big: n0(totalCount) + "종목", small: "자기주식 공시 흐름 · 매입 ↔ 처분" }

    const tabBtn = (v: string, lb: string) => (
        <button key={v} className="vpmBtn" onClick={() => setTab(v)} style={{
            border: "none", cursor: "pointer", fontFamily: FONT, padding: "8px 14px", borderRadius: 10,
            fontSize: 13, fontWeight: 800, background: tab === v ? C.violet : C.card, color: tab === v ? "#fff" : C.sub,
            display: "inline-flex", alignItems: "center", gap: 6,
        }}>
            <GIcon k={v} size={17} a={tab === v ? "#ffffff" : C.violet} g={tab === v ? "rgba(255,255,255,0.38)" : C.gTint} />
            {lb}
        </button>
    )

    return (
        <div style={wrap}>
            {/* 글래스 아이콘 애니메이션 — 토스식 스프링 팝(solid) + 글래스 상승, pill hover 부상, 헤더 둥실.
                재생 트리거 = GIcon 내부 key(활성 색 전환 시 재마운트). prefers-reduced-motion 존중. */}
            <style>{`
                .vpmGiS{animation:vpmPop .5s cubic-bezier(.34,1.6,.64,1) both;transform-box:fill-box;transform-origin:center}
                .vpmGiG{animation:vpmRise .45s ease-out both}
                @keyframes vpmPop{0%{transform:scale(.45) rotate(-10deg);opacity:0}100%{transform:scale(1) rotate(0deg);opacity:1}}
                @keyframes vpmRise{0%{transform:translateY(5px);opacity:0}100%{transform:translateY(0);opacity:1}}
                @keyframes vpmFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-2.5px)}}
                .vpmBtn svg{transition:transform .18s ease}
                .vpmBtn:hover svg{transform:translateY(-1.5px) scale(1.08)}
                .vpmBtn:active svg{transform:scale(.94)}
                @media (prefers-reduced-motion: reduce){.vpmGiS,.vpmGiG{animation:none}.vpmBtn svg{transition:none}svg{animation:none!important}}
            `}</style>
            <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: "-0.4px" }}>관점 지도</div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>
                    같은 시장을 다른 렌즈로 — 분류·집계는 전부 공개 기준의 사실
                    {data._meta && data._meta.generated_at ? " · " + fmtAge(data._meta.generated_at) + " 갱신" : ""}
                </div>
            </div>

            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
                {tabBtn("desire", "욕구")}
                {tabBtn("cycle", "매출 안정성")}
                {tabBtn("buyback", "자사주")}
            </div>

            {/* 히어로 */}
            <div style={{ background: C.card, borderRadius: 14, padding: "13px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginBottom: 14 }}>
                <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.6px", color: C.ink }}>{hero.big}</div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>{hero.small}</div>
            </div>

            {/* 시총 규모 분포 — 카테고리별 합산 시총(국내+해외 환산) share. 사실, 랭킹 아님. 세그먼트 클릭=선택 */}
            {showCapBar ? (
                <div style={{ marginBottom: 14 }}>
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 700, marginBottom: 6 }}>
                        시총 규모 분포 <span style={{ fontWeight: 600 }}>· 국내+해외 환산(근사) · 우열 아님</span>
                    </div>
                    <div style={{ display: "flex", width: "100%", height: 12, borderRadius: 6, overflow: "hidden", background: C.track }}>
                        {items.map((x, i) => {
                            const share = (Number(x.cap_sum) || 0) / capTotal
                            if (share <= 0) return null
                            const on = x.key === selKey
                            return (
                                <div key={x.key} onClick={() => setSel((s) => ({ ...s, [tab]: x.key }))}
                                    title={`${x.label} · ${capJo(x.cap_sum)} · ${(share * 100).toFixed(1)}%`}
                                    style={{ width: (share * 100) + "%", background: CAP_COLORS[i % CAP_COLORS.length], opacity: on ? 1 : 0.5, cursor: "pointer", transition: "opacity 0.15s" }} />
                            )
                        })}
                    </div>
                </div>
            ) : null}

            {/* 카테고리 pill 선택 (얇은 라인 아이콘) */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                {items.map((x) => {
                    const active = x.key === selKey
                    return (
                        <button key={x.key} className="vpmBtn" onClick={() => setSel((s) => ({ ...s, [tab]: x.key }))}
                            style={{
                                border: "none", cursor: "pointer", fontFamily: FONT, display: "inline-flex", alignItems: "center", gap: 6,
                                padding: "8px 12px", borderRadius: 11, fontSize: 12.5, fontWeight: 800,
                                background: active ? C.violet : C.card, color: active ? "#fff" : C.ink,
                                boxShadow: active ? "none" : "0 1px 2px rgba(0,0,0,0.04)",
                            }}>
                            <GIcon k={x.key} size={17} a={active ? "#ffffff" : C.violet} g={active ? "rgba(255,255,255,0.38)" : C.gTint} />
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
                        <span style={{ display: "inline-flex", flexShrink: 0 }}><GIcon key={item.key} k={item.key} size={32} a={C.violet} g={C.gTint} float /></span>
                        <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: 15, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px" }}>{item.label}</div>
                            <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 1 }}>{cfg.meta(item)}{item.cap_sum ? " · 규모 " + capJo(item.cap_sum) : ""}</div>
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
                분류 = 탐색용 관점(기준 공개) · 집계 = 공시 사실 · 종목은 대표 예시
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

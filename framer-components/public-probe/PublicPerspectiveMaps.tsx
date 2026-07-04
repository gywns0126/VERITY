import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * 관점 지도 — AlphaNest 탐색. 욕구(매슬로우 피라미드) · 경기 체질(매출 변동성 스펙트럼) · 자사주(강도 바) 3탭.
 * 데이터(Blob): perspective_maps.json (perspective_maps_builder — 분류·집계 사실만).
 *
 * 🚨 시각 개편(2026-07-04): 균일 카드 스택 → 관점마다 "의미에 맞는 지배적 시각" 1개.
 *   욕구=피라미드(폭∝종목수, 사실), 경기체질=안정↔민감 스펙트럼(σ 실측), 자사주=매입 강도 바. + 탭별 히어로 한 줄. shimmer 스켈레톤.
 * 🚨 RULE 7 — 점수·랭킹·추천 0. 분류 기준 공개(업종 키워드 규칙·실측 3분위·공시 건수). 폭·길이 = 사실(카운트) 인코딩일 뿐 등급 아님.
 *   "관점 = 탐색 렌즈" 문구 고정. RULE 6 — LLM narrative 0.
 * 다크모드 자가감지(body[data-framer-theme]). cache-fallback(sessionStorage). 밀도↑ 터미널 리디자인 X — 토스 소프트 유지.
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
    } catch (e) {
        return ""
    }
}
function n0(v: any): string {
    const x = Number(v)
    return isFinite(x) ? Math.round(x).toLocaleString("en-US") : "—"
}

// 카테고리 → 대표 이모지 (탐색 anchor · 사실 분류 시각화). RULE: 장식 아님, 계층 식별용.
const EMOJI: Record<string, string> = {
    survival: "🍚", safety: "🛡️", belonging: "💬", esteem: "👑", growth: "🎓", infra: "🏗️",
    steady: "⚓", middle: "⚖️", swing: "🎢",
    steady_buy: "🔁", some_buy: "🛒", net_sell: "📤",
}
const FLAG = "https://hatscripts.github.io/circle-flags/flags/"
const STK_LOGO = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
function isKR(tk: any): boolean { return /^\d{6}$/.test(String(tk || "")) }

// 대표 종목 = 로고 + 이름 + 국기 (텍스트 나열 X). 로고 실패 시 이니셜 원. 탭 → 리포트.
function Leader(props: { ticker: string; name: string; C: any; onGo: (t: string) => void }) {
    const { ticker, name, C, onGo } = props
    const [err, setErr] = useState(false)
    const kr = isKR(ticker)
    const initial = ((name || "?").trim().charAt(0)) || "?"
    return (
        <span onClick={(e) => { e.stopPropagation(); onGo(String(ticker || "")) }}
            style={{ display: "inline-flex", alignItems: "center", gap: 6, background: C.violetSoft, borderRadius: 10, padding: "4px 10px 4px 4px", cursor: "pointer" }}>
            {!err && ticker ? (
                <img src={STK_LOGO + ticker + ".png"} alt="" width={18} height={18} loading="lazy" onError={() => setErr(true)}
                    style={{ width: 18, height: 18, borderRadius: 5, objectFit: "cover", background: "#fff", flexShrink: 0 }} />
            ) : (
                <span style={{ width: 18, height: 18, borderRadius: 5, background: C.violet, color: "#fff", fontSize: 10, fontWeight: 800, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{initial}</span>
            )}
            <span style={{ fontSize: 11.5, fontWeight: 700, color: C.violet }}>{name}</span>
            <img src={FLAG + (kr ? "kr" : "us") + ".svg"} alt="" width={12} height={12} style={{ width: 12, height: 12, borderRadius: "50%", flexShrink: 0 }} />
        </span>
    )
}

// 캔버스 프리뷰 전용 SAMPLE (라이브는 fetch). 시각 구조 확인용 축약본.
const SAMPLE = {
    _meta: { generated_at: "2026-07-04T13:20:05+09:00" },
    desire: {
        tiers: [
            { key: "survival", label: "생존·생리", n_kr: 397, n_us: 250, median_op_margin: 6.8, desc: "먹고 마시고 아프지 않게 — 수요가 유행을 안 탐", leaders: [{ ticker: "005930", name: "삼성전자" }, { ticker: "000660", name: "SK하이닉스" }] },
            { key: "safety", label: "안전", n_kr: 67, n_us: 232, median_op_margin: 11.6, desc: "지키고 대비하는 수요 — 보험·방산·보안", leaders: [{ ticker: "012450", name: "한화에어로" }] },
            { key: "belonging", label: "소속·연결", n_kr: 98, n_us: 76, median_op_margin: 7.0, desc: "잇고 어울리는 수요 — 통신·콘텐츠·모임", leaders: [{ ticker: "035420", name: "NAVER" }] },
            { key: "esteem", label: "존중·과시", n_kr: 43, n_us: 33, median_op_margin: 6.0, desc: "돋보이고 싶은 수요 — 명품·뷰티·프리미엄", leaders: [{ ticker: "090430", name: "아모레퍼시픽" }] },
            { key: "growth", label: "자아실현", n_kr: 10, n_us: 14, median_op_margin: 11.7, desc: "배우고 성장하는 수요 — 교육·자기계발", leaders: [{ ticker: "095720", name: "웅진씽크빅" }] },
            { key: "infra", label: "기반·인프라", n_kr: 1006, n_us: 900, median_op_margin: 6.0, desc: "욕구를 직접 팔진 않지만 위 전부를 떠받치는 산업 — B2B·부품·장비", leaders: [{ ticker: "042700", name: "한미반도체" }] },
        ],
    },
    cycle: {
        basis: "연간 매출 YoY 변동성(≥4년 실측 종목만) · 측정 불가 = 미표시",
        buckets: [
            { key: "steady", label: "매출 흔들림 작음", n: 503, vol_range: [0.1, 5.3], desc: "경기와 덜 흔들리는 매출", leaders: [{ ticker: "033780", name: "KT&G" }] },
            { key: "middle", label: "중간", n: 503, vol_range: [5.3, 12.7], desc: "중간 변동", leaders: [{ ticker: "005380", name: "현대차" }] },
            { key: "swing", label: "매출 흔들림 큼", n: 504, vol_range: [12.7, 10074.7], desc: "경기·업황에 크게 흔들리는 매출", leaders: [{ ticker: "000660", name: "SK하이닉스" }] },
        ],
    },
    buyback: {
        basis: "DART 자기주식 취득·처분 공시 건수 (포렌식 수집 창)",
        buckets: [
            { key: "steady_buy", label: "꾸준한 매입", n: 137, desc: "자기주식을 반복 취득", leaders: [{ ticker: "000270", name: "기아" }] },
            { key: "some_buy", label: "매입 있음", n: 52, desc: "취득 공시 확인", leaders: [{ ticker: "175330", name: "JB금융지주" }] },
            { key: "net_sell", label: "처분 우위", n: 81, desc: "처분이 취득보다 많음", leaders: [{ ticker: "028050", name: "삼성E&A" }] },
        ],
    },
}

export default function PublicPerspectiveMaps(props: { width?: number; dark?: boolean; dataUrl?: string; stockPath?: string }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)
    const [tab, setTab] = useState<string>("desire")
    const [sel, setSel] = useState<Record<string, string>>({})

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

    const wrap: CSSProperties = { width: props.width || 380, maxWidth: "100%", fontFamily: FONT, background: C.bg, color: C.ink, padding: 14, boxSizing: "border-box" }

    // 활성 선택 항목 (탭별, 기본 = 리스트 첫 항목)
    const activeKey = (list: any[]): string => {
        const k = sel[tab]
        if (k && list.some((x) => x.key === k)) return k
        return list[0] ? list[0].key : ""
    }
    const pick = (k: string) => setSel((s) => ({ ...s, [tab]: k }))

    const leaderChips = (leaders: any[]) => (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 9 }}>
            {(leaders || []).slice(0, 8).map((l: any, i: number) => (
                <Leader key={(l.ticker || "") + i} ticker={String(l.ticker || "")} name={l.name} C={C} onGo={go} />
            ))}
        </div>
    )

    // 선택 항목 상세 패널 (히어로 비주얼 아래 공통) — 큰 이모지 anchor + 대표 종목(로고·국기)
    const detailPanel = (item: any, metaLine: string) => {
        if (!item) return null
        return (
            <div style={{ background: C.card, borderRadius: 14, padding: 14, marginTop: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 14.5, fontWeight: 800, color: C.ink, display: "inline-flex", alignItems: "center", gap: 8 }}>
                        {EMOJI[item.key] ? <span style={{ fontSize: 22, lineHeight: 1 }}>{EMOJI[item.key]}</span> : null}
                        {item.label}
                    </span>
                    <span style={{ fontSize: 10.5, fontWeight: 700, color: C.faint }}>{metaLine}</span>
                </div>
                {item.desc ? <div style={{ fontSize: 12, color: C.sub, fontWeight: 600, marginTop: 5, lineHeight: 1.5 }}>{item.desc}</div> : null}
                {leaderChips(item.leaders)}
            </div>
        )
    }

    /* ── 스켈레톤 (토스식 shimmer) ── */
    if (!data) {
        const base = C.track, hi = C.hi
        const sk = (wd: any, ht: number, r = 7, mt = 0): CSSProperties => ({
            width: wd, height: ht, marginTop: mt, borderRadius: r, background: base,
            backgroundImage: `linear-gradient(90deg, ${base} 25%, ${hi} 37%, ${base} 63%)`,
            backgroundSize: "800px 100%", animation: "vpmShimmer 1.4s ease-in-out infinite",
        })
        return (
            <div style={wrap}>
                <style>{`@keyframes vpmShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={sk(96, 18, 6)} />
                <div style={sk("72%", 12, 5, 8)} />
                <div style={{ display: "flex", gap: 6, marginTop: 14 }}>
                    <div style={sk(58, 32, 10)} />
                    <div style={sk(74, 32, 10)} />
                    <div style={sk(58, 32, 10)} />
                </div>
                {/* 피라미드 실루엣 */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, marginTop: 16 }}>
                    {[40, 55, 70, 84, 96].map((wp, i) => (
                        <div key={i} style={sk(wp + "%", 34, 9)} />
                    ))}
                </div>
                <div style={sk("100%", 74, 14, 16)} />
            </div>
        )
    }

    // ── 욕구: 피라미드(폭 ∝ 종목수) + 인프라 기반 + 상세 ──
    const desireTiers: any[] = (data.desire && data.desire.tiers) || []
    const infra = desireTiers.find((t) => t.key === "infra")
    const pyramid = desireTiers.filter((t) => t.key !== "infra")
    const cnt = (t: any) => (Number(t.n_kr) || 0) + (Number(t.n_us) || 0)
    const maxCnt = pyramid.reduce((m, t) => Math.max(m, cnt(t)), 1)
    // 피라미드 = 좁은 꼭대기(자아실현) → 넓은 바닥. 데이터 순서(생존…자아실현) 역순.
    const pyramidTop = [...pyramid].reverse()
    const desireActive = activeKey(desireTiers)
    const desireItem = desireTiers.find((t) => t.key === desireActive)

    // ── 경기 체질: 안정↔민감 스펙트럼 ──
    const cycleBuckets: any[] = (data.cycle && data.cycle.buckets) || []
    const cycleActive = activeKey(cycleBuckets)
    const cycleItem = cycleBuckets.find((b) => b.key === cycleActive)
    const cycleTint = (i: number) => {
        // 안정(옅음) → 민감(진함) 단일 hue 강도 (방향성 아닌 변동 강도)
        const t = cycleBuckets.length > 1 ? i / (cycleBuckets.length - 1) : 0
        const a = (0.16 + t * 0.62).toFixed(2)
        return isDark ? `rgba(169,155,255,${a})` : `rgba(108,92,231,${a})`
    }

    // ── 자사주: 매입 강도 바 ──
    const buyBuckets: any[] = (data.buyback && data.buyback.buckets) || []
    const buySorted = [...buyBuckets].sort((a, b) => (Number(b.n) || 0) - (Number(a.n) || 0))
    const buyMax = buySorted.reduce((m, b) => Math.max(m, Number(b.n) || 0), 1)
    const buyActive = activeKey(buyBuckets)
    const buyItem = buyBuckets.find((b) => b.key === buyActive)
    const buyBought = buyBuckets.filter((b) => b.key !== "net_sell").reduce((a, b) => a + (Number(b.n) || 0), 0)
    const buySell = (buyBuckets.find((b) => b.key === "net_sell") || {}).n || 0

    // 탭별 히어로 한 줄 (사실)
    const hero =
        tab === "desire"
            ? { big: n0(pyramid.reduce((a, t) => a + cnt(t), 0)) + "종목", small: "5개 욕구 계층으로 분류 · 기반·인프라 " + n0(infra ? cnt(infra) : 0) + " 별도" }
            : tab === "cycle"
              ? { big: n0(cycleBuckets.reduce((a, b) => a + (Number(b.n) || 0), 0)) + "종목", small: "연간 매출 YoY 변동성 3분위 실측 · 안정 ↔ 민감" }
              : { big: n0(buyBought) + "종목 매입", small: "DART 자기주식 공시 · 처분 우위 " + n0(buySell) }

    const tabBtn = (v: string, lb: string) => (
        <button key={v} onClick={() => setTab(v)} style={{
            border: "none", cursor: "pointer", fontFamily: FONT, padding: "8px 14px", borderRadius: 10,
            fontSize: 13, fontWeight: 800, background: tab === v ? C.violet : C.card, color: tab === v ? "#fff" : C.sub,
        }}>{lb}</button>
    )

    return (
        <div style={wrap}>
            <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>관점 지도</div>
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

            {/* 히어로 한 줄 — 발걸음 멈추는 지점 */}
            <div style={{ background: C.card, borderRadius: 14, padding: "13px 15px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginBottom: 12 }}>
                <div style={{ fontSize: 21, fontWeight: 800, letterSpacing: "-0.6px", color: C.ink }}>{hero.big}</div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 2, lineHeight: 1.45 }}>{hero.small}</div>
            </div>

            {tab === "desire" && (
                <div>
                    {/* 매슬로우 피라미드 (폭 = 종목수, 꼭대기=자아실현) */}
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                        {pyramidTop.map((t, i) => {
                            const c = cnt(t)
                            const wp = 34 + (c / maxCnt) * 62
                            const active = t.key === desireActive
                            return (
                                <div key={t.key} onClick={() => pick(t.key)} role="button" tabIndex={0}
                                    style={{
                                        width: wp + "%", minWidth: 120, cursor: "pointer", boxSizing: "border-box",
                                        background: active ? C.violet : C.violetSoft, color: active ? "#fff" : C.violet,
                                        borderRadius: 9, padding: "9px 12px", display: "flex", alignItems: "center",
                                        justifyContent: "space-between", gap: 8, transition: "all 120ms ease",
                                    }}>
                                    <span style={{ fontSize: 12.5, fontWeight: 800, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{EMOJI[t.key] || "•"} {t.label}</span>
                                    <span style={{ fontSize: 11.5, fontWeight: 800, flexShrink: 0, fontVariantNumeric: "tabular-nums", opacity: active ? 1 : 0.85 }}>{n0(c)}</span>
                                </div>
                            )
                        })}
                    </div>
                    {/* 인프라 = 전부를 떠받치는 기반 (피라미드 토대) */}
                    {infra ? (
                        <div onClick={() => pick(infra.key)} role="button" tabIndex={0}
                            style={{
                                width: "100%", cursor: "pointer", boxSizing: "border-box", marginTop: 6,
                                background: infra.key === desireActive ? C.violet : C.line, color: infra.key === desireActive ? "#fff" : C.sub,
                                borderRadius: 9, padding: "9px 12px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
                            }}>
                            <span style={{ fontSize: 12, fontWeight: 800 }}>🏗️ 기반·인프라 <span style={{ fontWeight: 600, opacity: 0.8 }}>· 토대</span></span>
                            <span style={{ fontSize: 11.5, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{n0(cnt(infra))}</span>
                        </div>
                    ) : null}
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>
                        폭 = 종목 수(사실) · 업종을 욕구 계층으로 분류 · 위 계층을 탭하면 상세
                    </div>
                    {detailPanel(desireItem, desireItem ? `KR ${n0(desireItem.n_kr)} · US ${n0(desireItem.n_us)}${desireItem.median_op_margin != null ? " · 영업이익률 중앙 " + desireItem.median_op_margin + "%" : ""}` : "")}
                </div>
            )}

            {tab === "cycle" && (
                <div>
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginBottom: 8 }}>
                        {data.cycle && data.cycle.basis} — 남의 "방어주" 라벨이 아니라 공시 매출로 직접 잰 흔들림.
                    </div>
                    {/* 안정 ↔ 민감 스펙트럼 (세그먼트 = 3분위) */}
                    <div style={{ display: "flex", height: 58, borderRadius: 11, overflow: "hidden", gap: 2 }}>
                        {cycleBuckets.map((b, i) => {
                            const active = b.key === cycleActive
                            return (
                                <div key={b.key} onClick={() => pick(b.key)} role="button" tabIndex={0}
                                    style={{
                                        flex: Math.max(1, Number(b.n) || 1), cursor: "pointer", background: cycleTint(i),
                                        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 1,
                                        color: i >= cycleBuckets.length - 1 ? "#fff" : C.ink, padding: "0 6px",
                                        boxShadow: active ? `inset 0 0 0 2.5px ${C.violet}` : "none",
                                    }}>
                                    <span style={{ fontSize: 15, lineHeight: 1 }}>{EMOJI[b.key]}</span>
                                    <span style={{ fontSize: 10, fontWeight: 800, textAlign: "center", lineHeight: 1.15 }}>{b.label}</span>
                                    <span style={{ fontSize: 11, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{n0(b.n)}</span>
                                </div>
                            )
                        })}
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: C.faint, fontWeight: 700, marginTop: 6 }}>
                        <span>← 안정 (덜 흔들림)</span>
                        <span>민감 (크게 흔들림) →</span>
                    </div>
                    {detailPanel(cycleItem, cycleItem && cycleItem.vol_range ? `YoY σ ${cycleItem.vol_range[0]}%~${cycleItem.key === "swing" ? cycleItem.vol_range[0] + "%+" : cycleItem.vol_range[1] + "%"}` : (cycleItem ? n0(cycleItem.n) + "종목" : ""))}
                </div>
            )}

            {tab === "buyback" && (
                <div>
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginBottom: 10 }}>
                        {data.buyback && data.buyback.basis} — 자기 주식을 사들이는 회사는 공시로 흔적이 남아요.
                    </div>
                    {/* 매입 강도 바 (길이 ∝ 종목수) */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                        {buySorted.map((b) => {
                            const wp = Math.max(8, ((Number(b.n) || 0) / buyMax) * 100)
                            const sell = b.key === "net_sell"
                            const active = b.key === buyActive
                            return (
                                <div key={b.key} onClick={() => pick(b.key)} role="button" tabIndex={0} style={{ cursor: "pointer" }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                                        <span style={{ fontSize: 12.5, fontWeight: 800, color: active ? C.violet : C.ink }}>{EMOJI[b.key] || ""} {b.label}</span>
                                        <span style={{ fontSize: 11.5, fontWeight: 800, color: C.faint, fontVariantNumeric: "tabular-nums" }}>{n0(b.n)}종목</span>
                                    </div>
                                    <div style={{ height: 12, borderRadius: 6, background: C.track, overflow: "hidden" }}>
                                        <div style={{ width: wp + "%", height: "100%", borderRadius: 6, background: sell ? C.faint : C.violet, opacity: active ? 1 : 0.85 }} />
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                    {detailPanel(buyItem, buyItem ? n0(buyItem.n) + "종목 · KR · DART 공시" : "")}
                </div>
            )}

            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 14, lineHeight: 1.5 }}>
                분류 = 탐색용 관점(기준 공개) · 집계 = 공시 사실 · 폭·길이는 종목 수 인코딩 · 점수·등급·종목 추천 아님
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

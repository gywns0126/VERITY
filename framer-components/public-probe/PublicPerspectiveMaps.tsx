import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

/**
 * 관점 지도 — AlphaNest 탐색. 욕구(매슬로우+인프라) · 경기 체질(매출 변동성 실측) · 자사주(공시 사실) 3탭.
 * 데이터(Blob): perspective_maps.json (perspective_maps_builder — 분류·집계 사실만).
 *
 * 🚨 RULE 7 — 점수·랭킹·추천 0. 분류 기준 공개(업종 키워드 규칙·실측 3분위·공시 건수).
 *   "관점 = 탐색 렌즈" 문구 고정. RULE 6 — LLM narrative 0.
 * 다크모드 자가감지(body[data-framer-theme]). cache-fallback(sessionStorage).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff",
}
const DARK = {
    bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
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

export default function PublicPerspectiveMaps(props: {
    width?: number; dark?: boolean; dataUrl?: string; stockPath?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const [data, setData] = useState<any>(null)
    const [tab, setTab] = useState<string>("desire")

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
        if (onCanvas || typeof window === "undefined") return
        try { window.location.href = `${stockPath}?q=${encodeURIComponent(tk)}` } catch (e) {}
    }

    const wrap: any = { width: props.width || 380, fontFamily: FONT, background: C.bg, color: C.ink, padding: 14, boxSizing: "border-box" }
    if (!data) return <div style={wrap}><div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>관점 지도 준비 중…</div></div>

    const tabBtn = (v: string, lb: string) => (
        <button key={v} onClick={() => setTab(v)} style={{
            border: "none", cursor: "pointer", fontFamily: FONT, padding: "8px 14px", borderRadius: 10,
            fontSize: 13, fontWeight: 800, background: tab === v ? C.violet : C.card, color: tab === v ? "#fff" : C.sub,
        }}>{lb}</button>
    )

    const leaderChips = (leaders: any[]) => (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
            {(leaders || []).map((l: any, i: number) => (
                <span key={(l.ticker || "") + i} onClick={() => go(String(l.ticker || ""))} style={{
                    cursor: "pointer", fontSize: 10.5, fontWeight: 700, padding: "3px 8px", borderRadius: 7,
                    background: C.violetSoft, color: C.violet,
                }}>{l.name}</span>
            ))}
        </div>
    )

    const card = (title: string, sub: string, body: any, key: string) => (
        <div key={key} style={{ background: C.card, borderRadius: 14, padding: 14, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>{title}</span>
                <span style={{ fontSize: 10.5, fontWeight: 700, color: C.faint }}>{sub}</span>
            </div>
            {body}
        </div>
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

            {tab === "desire" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>
                        업종(사실) → 인간 욕구 계층 분류. 욕구를 직접 팔지 않는 산업은 '기반·인프라'로 정직하게 분리.
                    </div>
                    {(data.desire.tiers || []).map((t: any) =>
                        card(
                            t.label,
                            `KR ${t.n_kr} · US ${t.n_us}${t.median_op_margin != null ? ` · 영업이익률 중앙 ${t.median_op_margin}%` : ""}`,
                            <>
                                <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, marginTop: 4, lineHeight: 1.5 }}>{t.desc}</div>
                                {leaderChips(t.leaders)}
                            </>,
                            t.key,
                        )
                    )}
                </div>
            )}

            {tab === "cycle" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>
                        {data.cycle.basis} — 남의 "방어주" 라벨이 아니라 공시 매출로 직접 잰 흔들림.
                    </div>
                    {(data.cycle.buckets || []).map((b: any) =>
                        card(
                            b.label,
                            `${b.n}종목${b.vol_range ? ` · YoY σ ${b.vol_range[0]}~${b.vol_range[1]}%p` : ""}`,
                            <>
                                <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, marginTop: 4 }}>{b.desc}</div>
                                {leaderChips(b.leaders)}
                            </>,
                            b.key,
                        )
                    )}
                </div>
            )}

            {tab === "buyback" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>
                        {data.buyback.basis} — 자기 주식을 사들이는 회사는 공시로 흔적이 남아요.
                    </div>
                    {(data.buyback.buckets || []).map((b: any) =>
                        card(
                            b.label,
                            `${b.n}종목 · KR`,
                            <>
                                <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, marginTop: 4 }}>{b.desc}</div>
                                {leaderChips(b.leaders)}
                            </>,
                            b.key,
                        )
                    )}
                </div>
            )}

            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
                분류 = 탐색용 관점(기준 공개) · 집계 = 공시 사실 · 점수·등급·종목 추천 아님
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

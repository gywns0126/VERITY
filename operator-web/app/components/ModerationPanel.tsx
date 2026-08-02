"use client"
// ModerationPanel — 중용(中庸) 목표비중 (③구성 척추, 오퍼레이터 authed). 공개 알파네스트 디자인.
// 되돌리지 말 것: fetchOperator("moderation_portfolio")=태생 봉인 자산(private bucket, 공개 fallback 없음).
//   🚨 RULE 7: 산출=가설(N<252) 라벨 · 승률류 없음(구성 규율 표시) · brain 미투입 명시. 외곽선 0.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, type Palette } from "@/lib/theme"
import { fetchOperator } from "@/lib/api"

type Excluded = { ticker: string; name: string; reason: string }
type Doc = {
    as_of?: string
    status?: string
    layer1?: { universe_kr?: number; survivors?: number; excluded?: Excluded[]; flags?: string[]; note?: string }
    layer2?: { method?: string; lw_shrinkage?: number; common_days?: number; aligned?: number; cap_relaxed?: string }
    layer3?: { portfolio_vol_annual?: number; k_vol?: number; k_kelly?: number; exposure?: number; cash?: number; bind?: string }
    weights?: Record<string, number>
    names?: Record<string, string>
    us_pending?: string[]
}

export default function ModerationPanel() {
    const dark = useDark()
    const c = palette(dark)
    const [doc, setDoc] = useState<Doc | null>(null)
    const [status, setStatus] = useState<"loading" | "ok" | "auth" | "empty" | "error">("loading")

    useEffect(() => {
        let cancelled = false
        fetchOperator<Doc>("moderation_portfolio").then((r) => {
            if (cancelled) return
            if (!r.ok) {
                setStatus(r.error === "auth" ? "auth" : r.status === 503 ? "empty" : "error")
                return
            }
            setDoc(r.data)
            setStatus("ok")
        })
        return () => {
            cancelled = true
        }
    }, [])

    const head = (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 800, color: c.ink }}>중용 목표비중</span>
            <span style={{ fontSize: 10.5, color: c.faint }}>3층 사전등록 산식 · 가설 N&lt;252 · brain 미투입</span>
        </div>
    )

    if (status !== "ok" || !doc) {
        const msg =
            status === "auth" ? "오퍼레이터 로그인이 필요합니다 (비공개)."
            : status === "empty" ? "산출 미적재 — 중용 빌더 첫 실행 대기(cron)."
            : status === "error" ? "중용 데이터를 불러오지 못했습니다."
            : "불러오는 중"
        return (
            <div style={{ ...cardStyle(c), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 8 }}>
                {head}
                <div style={{ fontSize: 13, color: status === "error" ? c.down : c.sub }}>{msg}</div>
            </div>
        )
    }

    const l1 = doc.layer1 || {}
    const l2 = doc.layer2 || {}
    const l3 = doc.layer3 || {}
    const weights = Object.entries(doc.weights || {}).sort((a, b) => b[1] - a[1])
    const names = doc.names || {}
    const exposure = l3.exposure ?? 0
    const cash = l3.cash ?? 1 - exposure
    const maxW = weights.length ? weights[0][1] : 0

    if (doc.status === "insufficient_breadth") {
        return (
            <div style={{ ...cardStyle(c), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 8 }}>
                {head}
                <div style={{ fontSize: 13, color: c.amber, lineHeight: 1.5 }}>
                    구성 중단 — 극단 배제 후 생존 {l1.survivors}종목 &lt; 8 (억지 구성 금지 규율). {l1.note}
                </div>
            </div>
        )
    }

    return (
        <div style={{ ...cardStyle(c), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: c.ink }}>중용 목표비중</span>
                <span style={{ fontSize: 10.5, color: c.faint, ...NUM }}>{doc.as_of} · 가설 N&lt;252 · brain 미투입</span>
            </div>

            {/* 노출 게이지 — 위험자산 vs 현금 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 20, fontWeight: 800, color: c.vt, ...NUM }}>{(exposure * 100).toFixed(1)}%</span>
                    <span style={{ fontSize: 12, color: c.sub }}>위험자산 노출 · 현금 <b style={{ color: c.ink, ...NUM }}>{(cash * 100).toFixed(1)}%</b></span>
                    <span style={{ fontSize: 10.5, fontWeight: 700, color: c.vt, background: c.vtS, borderRadius: 8, padding: "3px 9px" }}>
                        {l3.bind === "quarter_kelly" ? "quarter-Kelly 바인딩" : l3.bind === "vol_target" ? "목표변동성 바인딩" : "무레버리지 상한"}
                    </span>
                </div>
                <div style={{ display: "flex", height: 10, borderRadius: 6, overflow: "hidden", background: c.hi }}>
                    <div style={{ width: `${Math.min(exposure * 100, 100)}%`, background: c.vt }} />
                </div>
                <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11.5, color: c.sub }}>
                    <span>σ연 <b style={{ color: c.ink, ...NUM }}>{((l3.portfolio_vol_annual ?? 0) * 100).toFixed(1)}%</b></span>
                    <span>목표변동성 스케일 <b style={{ color: c.ink, ...NUM }}>{(l3.k_vol ?? 0).toFixed(2)}</b></span>
                    <span>quarter-Kelly <b style={{ color: c.ink, ...NUM }}>{(l3.k_kelly ?? 0).toFixed(3)}</b></span>
                    <span>상한 <b style={{ color: c.ink }}>1.0 (무레버리지)</b></span>
                </div>
            </div>

            {/* 목표 비중 */}
            {weights.length ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span style={{ fontSize: 10.5, fontWeight: 800, color: c.faint }}>목표 비중 (총자산 대비 · 잔여 현금)</span>
                    {weights.map(([tk, w]) => (
                        <div key={tk} style={{ display: "flex", alignItems: "center", gap: 9 }}>
                            <span style={{ fontSize: 12.5, fontWeight: 600, color: c.ink, width: 128, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{names[tk] || tk}</span>
                            <div style={{ flex: 1, height: 7, borderRadius: 5, background: c.hi, overflow: "hidden" }}>
                                <div style={{ width: `${maxW > 0 ? (w / maxW) * 100 : 0}%`, height: "100%", background: c.vt, opacity: 0.85 }} />
                            </div>
                            <span style={{ fontSize: 12, fontWeight: 700, color: c.ink, width: 52, textAlign: "right", ...NUM }}>{(w * 100).toFixed(2)}%</span>
                        </div>
                    ))}
                </div>
            ) : null}

            {/* 극단 배제 */}
            {(l1.excluded || []).length ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span style={{ fontSize: 10.5, fontWeight: 800, color: c.faint }}>
                        극단 배제 {l1.excluded!.length} / 유니버스 {l1.universe_kr} (비대칭 · 사실만)
                    </span>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {l1.excluded!.slice(0, 8).map((e, i) => (
                            <span key={i} style={{ fontSize: 10.5, fontWeight: 600, color: c.amber, background: c.amberS, borderRadius: 8, padding: "3px 8px" }}>
                                {e.name} · {e.reason.replace(/ 극단/g, "")}
                            </span>
                        ))}
                    </div>
                </div>
            ) : null}

            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 10.5, color: c.faint }}>
                <span>Ledoit-Wolf 수축 <span style={{ ...NUM }}>{l2.lw_shrinkage ?? "—"}</span> · 공통 <span style={{ ...NUM }}>{l2.common_days}</span>일 · {l2.aligned}종목</span>
                {(doc.us_pending || []).length ? <span>US {doc.us_pending!.length}종목 대기(공분산 적재 후 편입)</span> : null}
            </div>
            <div style={{ fontSize: 10, color: c.faint, lineHeight: 1.5 }}>
                Piotroski·Daniel-Moskowitz·Ledoit-Wolf·DeMiguel·Harvey·MacLean-Thorp-Ziemba 원전 사전등록 · 매수/매도 지시 아님
            </div>
        </div>
    )
}

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * 비공개 상세차트 (본인용) — 가격 캔들 위에 재무 파생 오버레이(fair-value 밴드) + 품질 추세 보조패널.
 *
 * 🚨 비공개/인증 게이트 전용. 공개 표면 금지 — Sharadar own-use + 상세 시세는 비공개 트랙만(컴플라이언스).
 * 사용자 원안 "재무 기반 라인을 그래프에 대입 → 정합/특이 눈으로" 의 시각 도구.
 *   단일 산식이 모든 종목을 앵커 못 함 → **4축 앵커 토글** (각자 다른 실패모드 보완):
 *   BVPS×PB(자산: 가치·금융) / EPS×PE(이익: 흑자 성장) / SPS×PS(매출: 적자·사이클서 EPS 대체)
 *   / FCFPS×P/FCF(현금: accrual 왜곡 방어). 가격이 밴드 위=비쌈(특이) · 아래=쌈(특이) · 안=정합.
 *   + 보조패널 = 마진·ROE 추세 (밴드가 못 잡는 가격↔펀더멘털 다이버전스 시각화).
 *   4축+품질 이상 오버레이 추가 = 시각 p-hacking 리스크 — 확장 시 PM 승인 (RULE 7 정합).
 *
 * 🚨 PIT: 오버레이 = 공시 접수일(datekey) 기준 forward-fill, look-ahead 0 (빌더에서 보장).
 * 🚨 RULE 7: 밴드 = 자기 분위(가설). 라벨에 "사실 · 밴드=가설 · PIT" 병기. 점수·추천 0.
 * 데이터 = build_stock_detail_overlay.py 산출 JSON (candles + overlay{4밴드} + aux).
 * 테마 자가감지(body[data-framer-theme]). 차트 = 자체 SVG(PublicLiveChart 좌표 패턴 재사용).
 */

const LIGHT = {
    bg: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb",
    up: "#f04452", down: "#3182f6", grid: "#eef0f3", violet: "#6c5ce7", green: "#0ca678",
    bandFill: "rgba(108,92,231,0.10)", bandLine: "#a99bff", chip: "#f2f4f6",
}
const DARK = {
    bg: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34",
    up: "#f04452", down: "#5b9bff", grid: "#1c222b", violet: "#a99bff", green: "#34e08a",
    bandFill: "rgba(169,155,255,0.13)", bandLine: "#a99bff", chip: "#252b34",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const BANDS: { key: string; btn: string; mult: string }[] = [
    { key: "bvps_band", btn: "BVPS·PB", mult: "PB" },
    { key: "eps_band", btn: "EPS·PE", mult: "PE" },
    { key: "ps_band", btn: "SPS·PS", mult: "PS" },
    { key: "fcf_band", btn: "FCF·P/FCF", mult: "P/FCF" },
]

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
    } catch (e) {}
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function fmtP(v: number): string {
    if (!isFinite(v)) return "—"
    return v >= 1000 ? Math.round(v).toLocaleString("en-US") : v.toFixed(2)
}
function sma(vals: number[], p: number): (number | null)[] {
    const out: (number | null)[] = []
    let s = 0
    for (let i = 0; i < vals.length; i++) {
        s += vals[i]
        if (i >= p) s -= vals[i - p]
        out.push(i >= p - 1 ? s / p : null)
    }
    return out
}

const _sampleBand = (lo: number, mid: number, hi: number, m: any) => ({
    label: "샘플", base: [], lo: Array(60).fill(lo), mid: Array(60).fill(mid), hi: Array(60).fill(hi), mult_pct: m,
})
const SAMPLE = {
    name: "샘플", ticker: "SAMPLE",
    candles: Array.from({ length: 60 }, (_, i) => {
        const base = 100 + Math.sin(i / 6) * 14 + i * 0.4
        return [i * 86400000, base - 1, base + 2, base - 2.5, base + (i % 3 - 1), 1000]
    }),
    overlay: {
        bvps_band: _sampleBand(88, 104, 120, { p20: 1, p50: 1.3, p80: 1.6 }),
        eps_band: _sampleBand(95, 112, 130, { p20: 10, p50: 14, p80: 18 }),
        ps_band: _sampleBand(80, 100, 125, { p20: 2, p50: 2.6, p80: 3.3 }),
        fcf_band: _sampleBand(90, 108, 128, { p20: 12, p50: 15, p80: 19 }),
    },
    aux: Array.from({ length: 16 }, (_, i) => ({
        t: i * 4 * 86400000, netmargin: 18 + Math.sin(i / 2) * 3, grossmargin: 42 + Math.cos(i / 3) * 2, roe: 24 + Math.sin(i / 2.5) * 5,
    })),
}

type Band = { label: string; lo: (number | null)[]; mid: (number | null)[]; hi: (number | null)[]; mult_pct: any }

export default function PrivateStockDetail(props: {
    dataUrl?: string; dark?: boolean; width?: number; height?: number
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))
    const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)
    const [ov, setOv] = useState<string>("bvps_band")   // BANDS key | off
    const [showAux, setShowAux] = useState<boolean>(true)

    useEffect(() => {
        if (onCanvas) return
        setThemeDark(readBodyDark())
        const obs = new MutationObserver(() => setThemeDark(readBodyDark()))
        if (document.body) obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas || !props.dataUrl) return
        let alive = true
        fetch(props.dataUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive && d && Array.isArray(d.candles)) setData(d) })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const W = Math.max(280, (props.width || 720) - 4)
    const H = Math.max(200, (props.height || 460) - (showAux ? 190 : 110))

    const band: Band | null = data && ov !== "off" ? data.overlay?.[ov] : null

    const cv = useMemo(() => {
        if (!data || !Array.isArray(data.candles) || data.candles.length < 2) return null
        const candles: number[][] = data.candles
        const n = candles.length
        const closes = candles.map((c) => c[4])
        const ma20 = sma(closes, 20)
        let pmin = Math.min(...candles.map((c) => c[3]))
        let pmax = Math.max(...candles.map((c) => c[2]))
        if (band) {
            const bl = band.lo.filter((v): v is number => v != null)
            const bh = band.hi.filter((v): v is number => v != null)
            if (bl.length) pmin = Math.min(pmin, ...bl)
            if (bh.length) pmax = Math.max(pmax, ...bh)
        }
        const prng = (pmax - pmin) || 1
        const padT = 12, padB = 10
        const xAt = (i: number) => (i / (n - 1)) * W
        const yP = (v: number) => padT + (H - padT - padB) - ((v - pmin) / prng) * (H - padT - padB)
        const cw = Math.max(1, (W / n) * 0.6)
        const line = (arr: (number | null)[]): string => {
            let d = "", pen = false
            for (let i = 0; i < arr.length; i++) {
                const v = arr[i]
                if (v == null) { pen = false; continue }
                d += (pen ? "L" : "M") + xAt(i).toFixed(1) + "," + yP(v).toFixed(1); pen = true
            }
            return d
        }
        // 밴드 영역(폴리곤): lo 정방향 + hi 역방향
        let bandArea = ""
        if (band) {
            const idx: number[] = []
            for (let i = 0; i < n; i++) if (band.lo[i] != null && band.hi[i] != null) idx.push(i)
            if (idx.length >= 2) {
                bandArea = "M" + idx.map((i) => xAt(i).toFixed(1) + "," + yP(band.lo[i] as number).toFixed(1)).join("L")
                bandArea += "L" + [...idx].reverse().map((i) => xAt(i).toFixed(1) + "," + yP(band.hi[i] as number).toFixed(1)).join("L") + "Z"
            }
        }
        return { n, xAt, yP, cw, pmin, pmax, ma20path: line(ma20),
            bandArea, midPath: band ? line(band.mid) : "", closes }
    }, [data, band, W, H])

    // 품질 추세 보조패널 — 마진·ROE (시간축 매핑, 자체 스케일). 가격↔펀더멘털 다이버전스 시각화.
    const AUX_SERIES = [
        { key: "grossmargin", label: "매출총마진%", color: C.green },
        { key: "netmargin", label: "순마진%", color: C.violet },
        { key: "roe", label: "ROE%", color: C.up },
    ]
    const auxCv = useMemo(() => {
        if (!showAux || !data || !Array.isArray(data.aux) || !Array.isArray(data.candles) || data.candles.length < 2) return null
        const t0 = data.candles[0][0], tN = data.candles[data.candles.length - 1][0]
        const pts = data.aux.filter((a: any) => a && a.t >= t0 && a.t <= tN)
        if (pts.length < 2) return null
        const AH = 64
        let vmin = Infinity, vmax = -Infinity
        for (const p of pts) for (const s of AUX_SERIES) {
            const v = p[s.key]
            if (v != null && isFinite(v)) { vmin = Math.min(vmin, v); vmax = Math.max(vmax, v) }
        }
        if (!isFinite(vmin) || vmin === vmax) return null
        const rng = vmax - vmin
        const xT = (t: number) => ((t - t0) / ((tN - t0) || 1)) * W
        const yA = (v: number) => 5 + (AH - 10) - ((v - vmin) / rng) * (AH - 10)
        const paths = AUX_SERIES.map((s) => {
            let d = "", pen = false
            for (const p of pts) {
                const v = p[s.key]
                if (v == null || !isFinite(v)) { pen = false; continue }
                d += (pen ? "L" : "M") + xT(p.t).toFixed(1) + "," + yA(v).toFixed(1); pen = true
            }
            return { ...s, d }
        }).filter((p) => p.d)
        if (!paths.length) return null
        return { AH, paths, zeroY: vmin < 0 && vmax > 0 ? yA(0) : null, vmin, vmax }
    }, [showAux, data, W, C])

    const wrap: CSSProperties = {
        width: props.width || 720, maxWidth: "100%", fontFamily: FONT, background: C.bg,
        color: C.ink, borderRadius: 16, padding: 14, boxSizing: "border-box",
        border: `1px solid ${C.line}`,
    }

    if (!data || !cv) {
        return <div style={wrap}><div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600, padding: 20, textAlign: "center" }}>상세차트 데이터 준비 중…</div></div>
    }

    const candles: number[][] = data.candles
    const lastClose = candles[candles.length - 1][4]
    // 현재 밴드 대비 판정
    let verdict: { txt: string; color: string } | null = null
    if (band) {
        const lo = [...band.lo].reverse().find((v) => v != null) as number | undefined
        const hi = [...band.hi].reverse().find((v) => v != null) as number | undefined
        const mid = [...band.mid].reverse().find((v) => v != null) as number | undefined
        if (lo != null && hi != null) {
            verdict = lastClose > hi ? { txt: "특이 · 밴드 위(비쌈)", color: C.up }
                : lastClose < lo ? { txt: "특이 · 밴드 아래(쌈)", color: C.down }
                    : { txt: "정합 · 밴드 내", color: C.violet }
            if (mid != null) verdict.txt += ` (fair≈${fmtP(mid)})`
        }
    }
    const multName = (BANDS.find((b) => b.key === ov) || { mult: "" }).mult
    const bandAvailable = (k: string) => {
        const b = data.overlay?.[k]
        return b && Array.isArray(b.mid) && b.mid.some((v: any) => v != null)
    }

    const chipBtn = (active: boolean, onClick: () => void, label: string, disabled?: boolean) => (
        <button key={label} onClick={onClick} disabled={disabled} style={{
            border: "none", cursor: disabled ? "default" : "pointer", fontFamily: FONT, padding: "5px 11px", borderRadius: 8,
            fontSize: 11.5, fontWeight: 700, background: active ? C.violet : C.chip,
            color: active ? "#fff" : disabled ? C.faint : C.sub, opacity: disabled ? 0.5 : 1,
        }}>{label}</button>
    )

    return (
        <div style={wrap}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                    <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.3px" }}>{data.name || data.ticker}</span>
                    <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{data.ticker}{data.sector ? " · " + data.sector : ""}</span>
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                    <span style={{ fontSize: 17, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{fmtP(lastClose)}</span>
                    {verdict && <span style={{ fontSize: 11.5, fontWeight: 800, color: verdict.color }}>{verdict.txt}</span>}
                </div>
            </div>

            {/* 오버레이 토글 — 4축 앵커 + off + 품질패널 */}
            <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap", alignItems: "center" }}>
                {BANDS.map((b) => chipBtn(ov === b.key, () => setOv(b.key), b.btn, !bandAvailable(b.key)))}
                {chipBtn(ov === "off", () => setOv("off"), "가격만")}
                {chipBtn(showAux, () => setShowAux(!showAux), "품질추세")}
                {band && band.mult_pct && (
                    <span style={{ marginLeft: "auto", fontSize: 10.5, color: C.faint, fontWeight: 600 }}>
                        {multName} 분위 {band.mult_pct.p20}·{band.mult_pct.p50}·{band.mult_pct.p80}
                    </span>
                )}
            </div>

            {/* 메인 차트 */}
            <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block", overflow: "visible" }} preserveAspectRatio="none">
                {cv.bandArea && <path d={cv.bandArea} fill={C.bandFill} stroke="none" />}
                {cv.midPath && <path d={cv.midPath} fill="none" stroke={C.bandLine} strokeWidth={1.3} strokeDasharray="5 4" opacity={0.9} />}
                {cv.ma20path && <path d={cv.ma20path} fill="none" stroke={C.faint} strokeWidth={1} opacity={0.7} />}
                {candles.map((c, i) => {
                    const up = c[4] >= c[1]
                    const col = up ? C.up : C.down
                    const x = cv.xAt(i)
                    const yH = cv.yP(c[2]), yL = cv.yP(c[3]), yO = cv.yP(c[1]), yC = cv.yP(c[4])
                    const top = Math.min(yO, yC), bh = Math.max(0.6, Math.abs(yC - yO))
                    return (
                        <g key={i}>
                            <line x1={x} y1={yH} x2={x} y2={yL} stroke={col} strokeWidth={0.8} />
                            <rect x={x - cv.cw / 2} y={top} width={cv.cw} height={bh} fill={col} />
                        </g>
                    )
                })}
            </svg>

            {/* 품질 추세 보조패널 — 다이버전스 렌즈 */}
            {auxCv && (
                <div style={{ marginTop: 8, borderTop: `1px solid ${C.line}`, paddingTop: 6 }}>
                    <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 2, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 10, color: C.faint, fontWeight: 700 }}>품질 추세 (PIT 분기)</span>
                        {auxCv.paths.map((p) => (
                            <span key={p.key} style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 9.5, color: C.faint, fontWeight: 600 }}>
                                <span style={{ width: 10, height: 2, background: p.color, display: "inline-block", borderRadius: 1 }} />{p.label}
                            </span>
                        ))}
                        <span style={{ marginLeft: "auto", fontSize: 9.5, color: C.faint, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
                            {auxCv.vmin.toFixed(0)}~{auxCv.vmax.toFixed(0)}%
                        </span>
                    </div>
                    <svg width="100%" viewBox={`0 0 ${W} ${auxCv.AH}`} style={{ display: "block", overflow: "visible" }} preserveAspectRatio="none">
                        {auxCv.zeroY != null && <line x1={0} y1={auxCv.zeroY} x2={W} y2={auxCv.zeroY} stroke={C.line} strokeWidth={1} strokeDasharray="3 3" />}
                        {auxCv.paths.map((p) => (
                            <path key={p.key} d={p.d} fill="none" stroke={p.color} strokeWidth={1.4} opacity={0.9} />
                        ))}
                    </svg>
                </div>
            )}

            {/* 범례 + RULE 7 라벨 */}
            <div style={{ display: "flex", gap: 12, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, color: C.faint, fontWeight: 600 }}>
                    <span style={{ width: 12, height: 8, background: C.bandFill, border: `1px solid ${C.bandLine}`, display: "inline-block", borderRadius: 2 }} />
                    {band ? band.label : "밴드 꺼짐"} · fair-value
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, color: C.faint, fontWeight: 600 }}>
                    <span style={{ width: 12, height: 2, background: C.faint, display: "inline-block" }} />MA20
                </span>
            </div>
            <div style={{ fontSize: 10, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>
                사실 = 공시 재무(BVPS/EPS/SPS/FCFPS·배수) · 밴드 = 자기 분위 <span style={{ color: C.violet, fontWeight: 700 }}>가설</span> · 공시 접수일 기준 PIT(look-ahead 0) · 점수·추천 아님 · 본인용
            </div>
        </div>
    )
}

addPropertyControls(PrivateStockDetail, {
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: "" },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    width: { type: ControlType.Number, title: "Width", defaultValue: 720 },
    height: { type: ControlType.Number, title: "Height", defaultValue: 460 },
})

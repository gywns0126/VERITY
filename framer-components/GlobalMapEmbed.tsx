import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState, useMemo } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    accentStrong: "0 0 12px rgba(181,255,25,0.50)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
const CSV_URL =
    "https://raw.githubusercontent.com/TheEconomist/big-mac-data/master/output-data/big-mac-full-index.csv"

interface BMEntry {
    date: string
    name: string
    currency: string
    localPrice: number
    dollarPrice: number
    raw: number
}

interface Props {
    mapUrl: string
    borderRadius: number
    showHeader: boolean
}

const KR: Record<string, string> = {
    Argentina: "아르헨티나", Australia: "호주", Azerbaijan: "아제르바이잔",
    Bahrain: "바레인", Brazil: "브라질", Britain: "영국",
    Canada: "캐나다", Chile: "칠레", China: "중국",
    Colombia: "콜롬비아", "Costa Rica": "코스타리카", "Czech Republic": "체코",
    Denmark: "덴마크", Egypt: "이집트", "Euro area": "유로존",
    Guatemala: "과테말라", Honduras: "온두라스", "Hong Kong": "홍콩",
    Hungary: "헝가리", India: "인도", Indonesia: "인도네시아",
    Israel: "이스라엘", Japan: "일본", Jordan: "요르단",
    Kuwait: "쿠웨이트", Lebanon: "레바논", Malaysia: "말레이시아",
    Mexico: "멕시코", Moldova: "몰도바", "New Zealand": "뉴질랜드",
    Nicaragua: "니카라과", Norway: "노르웨이", Oman: "오만",
    Pakistan: "파키스탄", Peru: "페루", Philippines: "필리핀",
    Poland: "폴란드", Qatar: "카타르", Romania: "루마니아",
    Russia: "러시아", "Saudi Arabia": "사우디", Singapore: "싱가포르",
    "South Africa": "남아공", "South Korea": "한국", "Sri Lanka": "스리랑카",
    Sweden: "스웨덴", Switzerland: "스위스", Taiwan: "대만",
    Thailand: "태국", Turkey: "튀르키예", UAE: "UAE",
    Ukraine: "우크라이나", "United States": "미국", Uruguay: "우루과이",
    Vietnam: "베트남",
}

let _cache: BMEntry[] | null = null

function parseCSV(text: string): BMEntry[] {
    const lines = text.trim().split("\n")
    if (lines.length < 2) return []
    const h = lines[0].split(",")
    const ci = (n: string) => h.indexOf(n)
    const out: BMEntry[] = []
    for (let k = 1; k < lines.length; k++) {
        const c = lines[k].split(",")
        const raw = parseFloat(c[ci("USD_raw")])
        if (isNaN(raw)) continue
        out.push({
            date: c[ci("date")] ?? "",
            name: c[ci("name")] ?? "",
            currency: c[ci("currency_code")] ?? "",
            localPrice: parseFloat(c[ci("local_price")]) || 0,
            dollarPrice: parseFloat(c[ci("dollar_price")]) || 0,
            raw,
        })
    }
    return out
}

// ─── Main component ──────────────────────────────────────

export default function GlobalMapEmbed(props: Props) {
    const { mapUrl, borderRadius, showHeader } = props
    const [clientReady, setClientReady] = useState(false)
    const [loaded, setLoaded] = useState(false)
    const [timedOut, setTimedOut] = useState(false)
    const [tab, setTab] = useState<"map" | "bmi">("map")
    const [bmiMounted, setBmiMounted] = useState(false)

    useEffect(() => setClientReady(true), [])

    useEffect(() => {
        if (!clientReady) return
        setLoaded(false)
        setTimedOut(false)
        const t = window.setTimeout(() => setTimedOut(true), 15_000)
        return () => window.clearTimeout(t)
    }, [mapUrl, clientReady])

    useEffect(() => {
        if (tab === "bmi") setBmiMounted(true)
    }, [tab])

    return (
        <div style={{ ...box, borderRadius }}>
            {showHeader && (
                <div style={hdr}>
                    <span style={titleSt}>
                        {tab === "map" ? "글로벌 마켓 맵" : "통화 밸류에이션"}
                    </span>
                    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                        <Pill label="마켓 맵" on={tab === "map"} onClick={() => setTab("map")} />
                        <Pill label="밸류에이션" on={tab === "bmi"} onClick={() => setTab("bmi")} />
                        {tab === "map" && (
                            <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={extLink}>
                                새 창 →
                            </a>
                        )}
                    </div>
                </div>
            )}

            <div style={{
                position: "relative", width: "100%", flex: 1, overflow: "hidden",
                borderRadius: showHeader ? `0 0 ${borderRadius}px ${borderRadius}px` : borderRadius,
                background: C.bgPage,
            }}>
                {/* Map tab — iframe stays mounted to avoid reload */}
                <div style={{ position: "absolute", inset: 0, display: tab === "map" ? "block" : "none" }}>
                    {!clientReady ? (
                        <div style={absCenter}>
                            <span style={accentTxt}>불러오는 중…</span>
                            <span style={grayTxt}>지도를 불러오고 있습니다.</span>
                            <span style={{ ...grayTxt, fontSize: 10, color: C.textTertiary }}>
                                분쟁지역·이벤트 마커는 파이프라인 데이터에 따라 표시됩니다.
                            </span>
                            <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={greenBtn}>
                                새 창에서 지도 열기
                            </a>
                        </div>
                    ) : (
                        <>
                            <iframe
                                key={mapUrl}
                                title="VERITY Global Map"
                                src={mapUrl}
                                onLoad={() => setLoaded(true)}
                                referrerPolicy="no-referrer-when-downgrade"
                                style={{
                                    position: "absolute", top: 0, left: 0,
                                    width: "100%", height: "100%",
                                    border: "none", display: "block", zIndex: 1,
                                }}
                                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
                                loading="eager"
                            />
                            {!loaded && (
                                <div style={absOverlay}>
                                    <span style={accentTxt}>지도 로딩 중…</span>
                                    {timedOut && (
                                        <div style={{ display: "flex", flexDirection: "column" as const, alignItems: "center", gap: 10, maxWidth: 280, textAlign: "center" as const }}>
                                            <span style={grayTxt}>
                                                15초 이상 로딩 중입니다. Vercel 프로젝트의 Authentication이 꺼져 있는지 확인하세요.
                                            </span>
                                            <span style={{ ...grayTxt, fontSize: 10, color: C.textTertiary }}>
                                                지도가 로드되어도 분쟁지역·이벤트 데이터가 없으면 해당 마커는 표시되지 않습니다.
                                            </span>
                                            <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={greenBtn}>
                                                새 창에서 지도 열기
                                            </a>
                                        </div>
                                    )}
                                </div>
                            )}
                        </>
                    )}
                </div>

                {/* Valuation tab — lazy-mounted, then stays alive */}
                {bmiMounted && (
                    <div style={{
                        position: "absolute", inset: 0,
                        display: tab === "bmi" ? "flex" : "none",
                        flexDirection: "column",
                    }}>
                        <BMPanel />
                    </div>
                )}
            </div>
        </div>
    )
}

// ─── Big Mac Index panel ─────────────────────────────────

function BMPanel() {
    const [data, setData] = useState<BMEntry[] | null>(_cache)
    const [loading, setLoading] = useState(!_cache)
    const [error, setError] = useState<string | null>(null)
    const [sub, setSub] = useState<"countries" | "trend">("countries")
    const [selected, setSelected] = useState("South Korea")
    type SK = "name" | "dollarPrice" | "raw"
    const [sortKey, setSortKey] = useState<SK>("raw")
    const [asc, setAsc] = useState(true)

    useEffect(() => {
        if (_cache) return
        fetch(CSV_URL)
            .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
            .then(t => {
                const parsed = parseCSV(t)
                if (!parsed.length) throw new Error("Empty dataset")
                _cache = parsed
                setData(parsed)
            })
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
    }, [])

    const latestDate = useMemo(
        () => data?.reduce((m, d) => (d.date > m ? d.date : m), "") ?? "",
        [data],
    )

    const latest = useMemo(
        () => data?.filter(d => d.date === latestDate && d.name !== "United States") ?? [],
        [data, latestDate],
    )

    const sorted = useMemo(() => {
        const arr = [...latest]
        arr.sort((a, b) => {
            const c = sortKey === "name" ? a.name.localeCompare(b.name) : a[sortKey] - b[sortKey]
            return asc ? c : -c
        })
        return arr
    }, [latest, sortKey, asc])

    const history = useMemo(
        () => data?.filter(d => d.name === selected).sort((a, b) => a.date.localeCompare(b.date)) ?? [],
        [data, selected],
    )

    const countries = useMemo(() => {
        if (!data) return []
        const s = new Set<string>()
        data.forEach(d => { if (d.name !== "United States") s.add(d.name) })
        return Array.from(s).sort()
    }, [data])

    if (loading) {
        return <div style={flexCenter}><span style={accentTxt}>빅맥 지수 데이터 로딩 중…</span></div>
    }
    if (error || !data) {
        return (
            <div style={flexCenter}>
                <span style={{ color: "#FF4D4D", fontSize: 12, fontFamily: FONT }}>데이터 로딩 실패: {error}</span>
                <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT }}>GitHub Raw CSV에 접근할 수 없습니다</span>
            </div>
        )
    }

    const toggleSort = (k: SK) => {
        if (sortKey === k) setAsc(!asc)
        else { setSortKey(k); setAsc(k === "name") }
    }

    return (
        <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 16px 0", flexShrink: 0 }}>
                <div style={{ display: "flex", gap: 2 }}>
                    <UTab label="Countries" on={sub === "countries"} onClick={() => setSub("countries")} />
                    <UTab label="Trend" on={sub === "trend"} onClick={() => setSub("trend")} />
                </div>
                <a
                    href="https://github.com/TheEconomist/big-mac-data"
                    target="_blank" rel="noopener noreferrer"
                    style={{ color: C.textTertiary, fontSize: 9, fontFamily: FONT, textDecoration: "none" }}
                >
                    {latestDate} · The Economist
                </a>
            </div>

            {sub === "countries" ? (
                <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
                    <div style={{ display: "flex", padding: "8px 16px", borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
                        <ColH label="국가" k="name" cur={sortKey} asc={asc} onClick={toggleSort} w="42%" />
                        <ColH label="USD 가격" k="dollarPrice" cur={sortKey} asc={asc} onClick={toggleSort} w="28%" align="right" />
                        <ColH label="밸류에이션" k="raw" cur={sortKey} asc={asc} onClick={toggleSort} w="30%" align="right" />
                    </div>
                    <div style={{ flex: 1, overflowY: "auto" }}>
                        {sorted.map(d => (
                            <CRow
                                key={d.name} d={d} active={d.name === selected}
                                onClick={() => { setSelected(d.name); setSub("trend") }}
                            />
                        ))}
                    </div>
                </div>
            ) : (
                <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "12px 16px", gap: 10, overflow: "hidden" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, flexWrap: "wrap" }}>
                        <select
                            value={selected}
                            onChange={e => setSelected(e.target.value)}
                            style={{
                                background: C.bgElevated, color: C.textPrimary, border: `1px solid ${C.border}`,
                                borderRadius: 6, padding: "6px 10px", fontSize: 12, fontFamily: FONT,
                                outline: "none", cursor: "pointer", maxWidth: 200,
                            }}
                        >
                            {countries.map(c => <option key={c} value={c}>{KR[c] || c}</option>)}
                        </select>
                        {history.length > 0 && (() => {
                            const last = history[history.length - 1]
                            const pct = last.raw * 100
                            return (
                                <span style={{ fontSize: 15, fontWeight: 700, fontFamily: FONT, color: pct > 0 ? "#FF4D4D" : "#B5FF19" }}>
                                    {pct > 0 ? "+" : ""}{pct.toFixed(1)}%
                                    <span style={{ color: C.textTertiary, fontSize: 10, fontWeight: 400, marginLeft: 4 }}>
                                        {pct > 0 ? "고평가" : "저평가"} vs USD
                                    </span>
                                </span>
                            )
                        })()}
                    </div>

                    <div style={{ flex: 1, minHeight: 0 }}>
                        <Chart data={history} />
                    </div>

                    {history.length > 0 && (
                        <div style={{ display: "flex", gap: 6, flexShrink: 0, flexWrap: "wrap" }}>
                            <Stat label="현재 USD가" value={`$${history[history.length - 1].dollarPrice.toFixed(2)}`} />
                            <Stat label="최저" value={`${(Math.min(...history.map(d => d.raw)) * 100).toFixed(1)}%`} color="#B5FF19" />
                            <Stat label="최고" value={`${(Math.max(...history.map(d => d.raw)) * 100).toFixed(1)}%`} color="#FF4D4D" />
                            <Stat label="기간" value={`${history[0].date.slice(0, 4)}–${history[history.length - 1].date.slice(0, 4)}`} />
                        </div>
                    )}
                </div>
            )}
        </>
    )
}

// ─── Trend chart (SVG) ───────────────────────────────────

function Chart({ data }: { data: BMEntry[] }) {
    if (data.length < 2) {
        return <div style={flexCenter}><span style={grayTxt}>트렌드 데이터가 부족합니다</span></div>
    }

    const W = 400, H = 200
    const p = { t: 20, r: 16, b: 28, l: 42 }
    const cW = W - p.l - p.r, cH = H - p.t - p.b

    const vals = data.map(d => d.raw * 100)
    const mn = Math.min(...vals, -5), mx = Math.max(...vals, 5)
    const rng = mx - mn || 1

    const xOf = (i: number) => p.l + (i / (data.length - 1)) * cW
    const yOf = (v: number) => p.t + cH - ((v - mn) / rng) * cH

    const pts = data.map((d, i) => ({ x: xOf(i), y: yOf(d.raw * 100) }))
    const line = pts.map((pt, i) => `${i ? "L" : "M"}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(" ")
    const zeroY = yOf(0)
    const area = `${line} L${pts[pts.length - 1].x.toFixed(1)},${zeroY.toFixed(1)} L${pts[0].x.toFixed(1)},${zeroY.toFixed(1)} Z`

    const step = rng <= 30 ? 5 : rng <= 60 ? 10 : rng <= 120 ? 20 : 50
    const gridVals: number[] = []
    for (let v = Math.ceil(mn / step) * step; v <= mx; v += step) gridVals.push(v)

    const yrs: { x: number; label: string }[] = []
    const seen = new Set<string>()
    const allYears = [...new Set(data.map(d => d.date.slice(0, 4)))]
    const every = Math.max(1, Math.ceil(allYears.length / 7))
    allYears.forEach((yr, idx) => {
        if (idx % every === 0 || idx === allYears.length - 1) {
            const di = data.findIndex(d => d.date.startsWith(yr))
            if (di >= 0 && !seen.has(yr)) { seen.add(yr); yrs.push({ x: xOf(di), label: yr }) }
        }
    })

    return (
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "100%" }} preserveAspectRatio="xMidYMid meet">
            {gridVals.map(v => (
                <g key={v}>
                    <line x1={p.l} y1={yOf(v)} x2={W - p.r} y2={yOf(v)}
                        stroke={v === 0 ? "#555" : "#1a1a1a"} strokeWidth={v === 0 ? 0.8 : 0.5} />
                    <text x={p.l - 4} y={yOf(v) + 3} fill="#555" fontSize="8" textAnchor="end" fontFamily={FONT}>
                        {v > 0 ? "+" : ""}{v}%
                    </text>
                </g>
            ))}
            <defs>
                <linearGradient id="bm_grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#B5FF19" stopOpacity={0.15} />
                    <stop offset="100%" stopColor="#B5FF19" stopOpacity={0} />
                </linearGradient>
            </defs>
            <path d={area} fill="url(#bm_grad)" />
            <path d={line} fill="none" stroke="#B5FF19" strokeWidth={1.8} strokeLinejoin="round" />
            <circle cx={pts[pts.length - 1].x} cy={pts[pts.length - 1].y} r={3.5} fill="#B5FF19" />
            {yrs.map((yl, i) => (
                <text key={i} x={yl.x} y={H - 6} fill="#444" fontSize="8" textAnchor="middle" fontFamily={FONT}>
                    {yl.label}
                </text>
            ))}
        </svg>
    )
}

// ─── Small UI pieces ─────────────────────────────────────

function Pill({ label, on, onClick }: { label: string; on: boolean; onClick: () => void }) {
    return (
        <button onClick={onClick} style={{
            background: on ? "#B5FF19" : "transparent", color: on ? "#000" : "#666",
            border: on ? "none" : "1px solid #333", borderRadius: 6,
            padding: "4px 10px", fontSize: 11, fontWeight: 600,
            cursor: "pointer", fontFamily: FONT,
        }}>{label}</button>
    )
}

function UTab({ label, on, onClick }: { label: string; on: boolean; onClick: () => void }) {
    return (
        <button onClick={onClick} style={{
            background: "none", color: on ? "#fff" : "#555", border: "none",
            borderBottom: on ? "2px solid #B5FF19" : "2px solid transparent",
            padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: FONT,
        }}>{label}</button>
    )
}

function ColH({ label, k, cur, asc, onClick, w, align = "left" }: {
    label: string; k: string; cur: string; asc: boolean
    onClick: (k: any) => void; w: string; align?: string
}) {
    const on = cur === k
    return (
        <div onClick={() => onClick(k)} style={{
            width: w, color: on ? "#B5FF19" : "#555", fontSize: 10, fontWeight: 600,
            cursor: "pointer", fontFamily: FONT, textAlign: align as any, userSelect: "none",
        }}>
            {label}{on ? (asc ? " ▲" : " ▼") : ""}
        </div>
    )
}

function CRow({ d, active, onClick }: { d: BMEntry; active: boolean; onClick: () => void }) {
    const pct = d.raw * 100
    return (
        <div onClick={onClick} style={{
            display: "flex", alignItems: "center", padding: "8px 16px",
            borderBottom: "1px solid #111", cursor: "pointer",
            background: active ? "#0d1a00" : "transparent",
            borderLeft: active ? "3px solid #B5FF19" : "3px solid transparent",
        }}>
            <div style={{ width: "42%" }}>
                <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 500, fontFamily: FONT }}>
                    {KR[d.name] || d.name}
                </span>
                {KR[d.name] && (
                    <span style={{ color: C.textTertiary, fontSize: 9, marginLeft: 4, fontFamily: FONT }}>{d.name}</span>
                )}
            </div>
            <span style={{ width: "28%", color: C.textSecondary, fontSize: 12, fontFamily: FONT, textAlign: "right" }}>
                ${d.dollarPrice.toFixed(2)}
            </span>
            <span style={{
                width: "30%", fontSize: 12, fontWeight: 700, fontFamily: FONT, textAlign: "right",
                color: pct > 0 ? "#FF4D4D" : pct < -10 ? "#B5FF19" : "#888",
            }}>
                {pct > 0 ? "+" : ""}{pct.toFixed(1)}%
            </span>
        </div>
    )
}

function Stat({ label, value, color = "#fff" }: { label: string; value: string; color?: string }) {
    return (
        <div style={{
            flex: 1, minWidth: 70, padding: "6px 8px", background: C.bgCard,
            borderRadius: 8, border: `1px solid ${C.border}`, textAlign: "center",
        }}>
            <div style={{ color: C.textTertiary, fontSize: 9, fontFamily: FONT }}>{label}</div>
            <div style={{ color, fontSize: 11, fontWeight: 700, fontFamily: FONT, marginTop: 2 }}>{value}</div>
        </div>
    )
}

// ─── Styles ──────────────────────────────────────────────

const box: React.CSSProperties = {
    width: "100%", height: "100%", background: C.bgCard,
    border: `1px solid ${C.border}`, overflow: "hidden", fontFamily: FONT,
    boxSizing: "border-box", display: "flex", flexDirection: "column",
}

const hdr: React.CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "12px 16px", borderBottom: `1px solid ${C.border}`, flexShrink: 0,
}

const titleSt: React.CSSProperties = { color: C.textPrimary, fontSize: 14, fontWeight: 700, fontFamily: FONT }

const extLink: React.CSSProperties = {
    color: "#B5FF19", fontSize: 11, fontWeight: 600,
    textDecoration: "none", fontFamily: FONT, marginLeft: 8,
}

const absOverlay: React.CSSProperties = {
    position: "absolute", inset: 0, display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center", gap: 12,
    background: "rgba(10,10,10,0.92)", zIndex: 20, pointerEvents: "auto",
}

const absCenter: React.CSSProperties = {
    position: "absolute", inset: 0, display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center", gap: 14,
    padding: 20, zIndex: 5, textAlign: "center",
}

const flexCenter: React.CSSProperties = {
    flex: 1, display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center", gap: 12,
}

const accentTxt: React.CSSProperties = { color: "#B5FF19", fontSize: 13, fontWeight: 600, fontFamily: FONT }
const grayTxt: React.CSSProperties = { color: C.textSecondary, fontSize: 11, lineHeight: 1.5, fontFamily: FONT }

const greenBtn: React.CSSProperties = {
    color: "#000", background: "#B5FF19", fontSize: 12, fontWeight: 700,
    padding: "8px 14px", borderRadius: 8, textDecoration: "none", fontFamily: FONT,
}

// ─── Framer config ───────────────────────────────────────

const DEFAULT_MAP_URL = "https://map-page-l9qxa0n9c-kim-hyojuns-projects.vercel.app"

GlobalMapEmbed.defaultProps = {
    mapUrl: DEFAULT_MAP_URL,
    borderRadius: 16,
    showHeader: true,
}

addPropertyControls(GlobalMapEmbed, {
    mapUrl: { type: ControlType.String, title: "맵 URL", defaultValue: DEFAULT_MAP_URL },
    borderRadius: { type: ControlType.Number, title: "모서리 곡률", defaultValue: 16, min: 0, max: 32, step: 2 },
    showHeader: { type: ControlType.Boolean, title: "헤더 표시", defaultValue: true },
})

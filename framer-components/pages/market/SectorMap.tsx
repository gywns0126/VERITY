import { addPropertyControls, ControlType } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * SectorMap — VERITY 섹터 히트맵 (Step 4, SectorHeat 모던 심플)
 *
 * 출처: SectorHeat.tsx (340줄) modernize. USSectorMap.tsx (264줄) 흡수 (US toggle 동일 처리).
 *
 * 설계:
 *   - KR/US toggle (시장별 섹터)
 *   - 4 view: 상승 / 하락 / 전체 / 전략 (rotation)
 *   - sector_rotation_check drift alert (KR only)
 *   - 섹터 expand → 대표 종목 list
 *   - bar chart (변화율 기준 좌우 정렬)
 *
 * 모던 심플 6원칙:
 *   1. No card-in-card — 외곽 1개 + 섹션 spacing
 *   2. Flat hierarchy — cap 라벨 + content
 *   3. Mono numerics — 변화율 / 카운트
 *   4. Expand on tap — 섹터 행 클릭 → 대표 종목 펼침
 *   5. Color discipline — heat = success/warn/danger 토큰 alpha
 *   6. Emoji 0 / 자체 색 0
 *
 * feedback_no_hardcode_position 적용: inline 렌더링.
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    success: "0 0 6px rgba(34,197,94,0.30)",
    warn: "0 0 6px rgba(245,158,11,0.30)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ─────────── Portfolio fetch ─────────── */
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000
function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}
function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    const timer = setTimeout(() => ac.abort(), PORTFOLIO_FETCH_TIMEOUT_MS)
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal: ac.signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
        .finally(() => clearTimeout(timer))
}


/* ─────────── 색 매핑 ─────────── */
function pctColor(pct: number | null | undefined): string {
    if (pct == null || !Number.isFinite(pct)) return C.textTertiary
    if (pct > 0) return C.success
    if (pct < 0) return C.danger
    return C.textTertiary
}

function heatColor(heat: string): string {
    if (heat === "hot") return C.success
    if (heat === "warm") return C.success
    if (heat === "cool") return C.warn
    if (heat === "cold") return C.danger
    return C.textTertiary
}

function fmtPct(n: number | null | undefined, digits = 2): string {
    if (n == null || !Number.isFinite(n)) return "—"
    const sign = n > 0 ? "+" : ""
    return `${sign}${n.toFixed(digits)}%`
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

type View = "hot" | "cold" | "all" | "rotation"

interface Props {
    dataUrl: string
    market: "kr" | "us"
}

export default function SectorMap(props: Props) {
    const { dataUrl } = props
    const isUS = props.market === "us"
    const [data, setData] = useState<any>(null)
    const [view, setView] = useState<View>("hot")
    const [expanded, setExpanded] = useState<string | null>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then((d) => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const { sectors, rotation, rotationDrift, hotCount, coldCount, maxPct } = useMemo(() => {
        if (!data) return { sectors: [] as any[], rotation: {} as any, rotationDrift: null as any, hotCount: 0, coldCount: 0, maxPct: 3 }
        const all = (data.sectors || []) as any[]
        const filtered = all.filter((s: any) =>
            isUS ? (s.market || "").toUpperCase() === "US" : (s.market || "").toUpperCase() !== "US"
        )
        const hot = filtered.filter((s: any) => (s.change_pct ?? 0) > 0).length
        const cold = filtered.filter((s: any) => (s.change_pct ?? 0) < 0).length
        const max = Math.max(...filtered.map((s: any) => Math.abs(s.change_pct ?? 0)), 3)

        const rot = data.sector_rotation || {}
        const rotCheck = !isUS ? (data.sector_rotation_check || {}) : {}
        const drift = rotCheck?.consistency?.drift === true ? rotCheck.consistency : null

        return { sectors: filtered, rotation: rot, rotationDrift: drift, hotCount: hot, coldCount: cold, maxPct: max }
    }, [data, isUS])

    const filteredSectors = useMemo(() => {
        if (view === "hot") return sectors.filter((s: any) => (s.change_pct ?? 0) > 0).slice(0, 12)
        if (view === "cold") return [...sectors].sort((a: any, b: any) => (a.change_pct ?? 0) - (b.change_pct ?? 0))
            .filter((s: any) => (s.change_pct ?? 0) < 0).slice(0, 12)
        return sectors.slice(0, 20)
    }, [sectors, view])

    const barWidth = (pct: number) => `${Math.min((Math.abs(pct) / maxPct) * 100, 100)}%`

    if (!data) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>섹터 로딩 중…</span>
                </div>
            </div>
        )
    }

    return (
        <div style={shell}>
            {/* Header */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <span style={titleStyle}>{isUS ? "US 섹터 히트맵" : "KR 섹터 히트맵"}</span>
                    <div style={metaRow}>
                        <span style={{ ...MONO, color: C.success, fontSize: T.cap, fontWeight: T.w_semi }}>
                            상승 {hotCount}
                        </span>
                        <span style={{ color: C.textDisabled, fontSize: T.cap }}>·</span>
                        <span style={{ ...MONO, color: C.danger, fontSize: T.cap, fontWeight: T.w_semi }}>
                            하락 {coldCount}
                        </span>
                    </div>
                </div>
                <div style={viewChips}>
                    {(["hot", "cold", "all", "rotation"] as const).map((v) => (
                        <ViewChip
                            key={v}
                            label={v === "hot" ? "상승" : v === "cold" ? "하락" : v === "all" ? "전체" : "전략"}
                            active={view === v}
                            onClick={() => setView(v)}
                        />
                    ))}
                </div>
            </div>

            {/* Rotation drift alert (KR only) */}
            {!isUS && rotationDrift && (
                <>
                    <div style={hr} />
                    <div style={driftBox}>
                        <div style={driftHeader}>
                            <span
                                style={{
                                    width: 6, height: 6, borderRadius: "50%",
                                    background: C.warn, boxShadow: G.warn,
                                }}
                            />
                            <span style={{ color: C.warn, fontSize: T.cap, fontWeight: T.w_bold, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                                섹터 로테이션 드리프트
                            </span>
                        </div>
                        <div style={{ color: C.textPrimary, fontSize: T.body, lineHeight: T.lh_normal }}>
                            현재 <span style={{ fontWeight: T.w_bold }}>{rotationDrift.quadrant_label || rotationDrift.quadrant || "—"}</span>
                            {" · 드리프트 "}
                            <span style={{ ...MONO, fontWeight: T.w_bold }}>{rotationDrift.drift_count}건</span>
                        </div>
                        {Array.isArray(rotationDrift.top_in_unfavored) && rotationDrift.top_in_unfavored.length > 0 && (
                            <div style={{ color: C.danger, fontSize: T.cap, lineHeight: T.lh_normal }}>
                                상위인데 unfavored: {rotationDrift.top_in_unfavored.map((t: any) => t.sector).join(", ")}
                            </div>
                        )}
                        {Array.isArray(rotationDrift.bottom_in_favored) && rotationDrift.bottom_in_favored.length > 0 && (
                            <div style={{ color: C.success, fontSize: T.cap, lineHeight: T.lh_normal }}>
                                하위인데 favored: {rotationDrift.bottom_in_favored.map((b: any) => b.sector).join(", ")}
                            </div>
                        )}
                    </div>
                </>
            )}

            <div style={hr} />

            {/* Rotation view (전략) */}
            {view === "rotation" && rotation.cycle && (
                <div style={rotationWrap}>
                    {/* Cycle label */}
                    <div>
                        <span style={sectionCap}>CYCLE</span>
                        <div style={{ color: C.accent, fontSize: T.title, fontWeight: T.w_bold, marginTop: 2 }}>
                            {rotation.cycle_label || rotation.cycle}
                        </div>
                        {rotation.cycle_desc && (
                            <div style={{ color: C.textSecondary, fontSize: T.body, lineHeight: T.lh_loose, marginTop: S.xs }}>
                                {rotation.cycle_desc}
                            </div>
                        )}
                    </div>

                    {Array.isArray(rotation.recommended_sectors) && rotation.recommended_sectors.length > 0 && (
                        <div>
                            <span style={{ ...sectionCap, color: C.success }}>추천 섹터</span>
                            <div style={{ display: "flex", flexDirection: "column", marginTop: S.sm }}>
                                {rotation.recommended_sectors.map((s: any, i: number) => (
                                    <RotationRow key={i} sector={s} />
                                ))}
                            </div>
                        </div>
                    )}

                    {Array.isArray(rotation.avoid_sectors) && rotation.avoid_sectors.length > 0 && (
                        <div>
                            <span style={{ ...sectionCap, color: C.danger }}>회피 섹터</span>
                            <div style={{ display: "flex", flexDirection: "column", marginTop: S.sm }}>
                                {rotation.avoid_sectors.map((s: any, i: number) => (
                                    <RotationRow key={i} sector={s} />
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Sector list (상승/하락/전체) */}
            {view !== "rotation" && (
                <div style={listWrap}>
                    {filteredSectors.length === 0 && (
                        <div style={emptyBox}>
                            <span style={{ color: C.textTertiary, fontSize: T.body }}>해당 섹터 없음</span>
                        </div>
                    )}
                    {filteredSectors.map((s: any, i: number) => (
                        <SectorRow
                            key={s.name + i}
                            sector={s}
                            isExpanded={expanded === s.name}
                            onToggle={() => setExpanded(expanded === s.name ? null : s.name)}
                            barWidth={barWidth}
                            isUS={isUS}
                        />
                    ))}
                </div>
            )}
        </div>
    )
}


/* ─────────── 서브 컴포넌트 ─────────── */

function ViewChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
    return (
        <button
            onClick={onClick}
            style={{
                background: active ? C.accentSoft : "transparent",
                border: `1px solid ${active ? C.accent : C.border}`,
                color: active ? C.accent : C.textSecondary,
                padding: `${S.xs}px ${S.md}px`,
                borderRadius: R.pill,
                fontSize: T.cap,
                fontWeight: T.w_semi,
                fontFamily: FONT,
                letterSpacing: "0.05em",
                cursor: "pointer",
                transition: X.base,
            }}
        >
            {label}
        </button>
    )
}

function SectorRow({
    sector,
    isExpanded,
    onToggle,
    barWidth,
    isUS,
}: {
    sector: any
    isExpanded: boolean
    onToggle: () => void
    barWidth: (pct: number) => string
    isUS: boolean
}) {
    const pct = sector.change_pct ?? 0
    const color = pctColor(pct)
    const heat = sector.heat || "neutral"
    const heatC = heatColor(heat)

    return (
        <div>
            <div
                onClick={onToggle}
                style={{
                    display: "flex", alignItems: "center", gap: S.md,
                    padding: `${S.md}px 0`,
                    borderBottom: `1px solid ${C.border}`,
                    cursor: "pointer",
                    transition: X.fast,
                    background: isExpanded ? C.bgElevated : "transparent",
                    paddingLeft: isExpanded ? S.sm : 0,
                    paddingRight: isExpanded ? S.sm : 0,
                    borderRadius: isExpanded ? R.sm : 0,
                }}
            >
                {/* heat dot + 섹터명 */}
                <div style={{ display: "flex", alignItems: "center", gap: S.sm, minWidth: 120, flexShrink: 0 }}>
                    <span
                        style={{
                            width: 6, height: 6, borderRadius: "50%",
                            background: heatC,
                        }}
                    />
                    <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>
                        {sector.name}
                    </span>
                </div>

                {/* bar chart (좌우 정렬) */}
                <div style={{ flex: 1, height: 4, background: C.bgElevated, borderRadius: 2, position: "relative", overflow: "hidden" }}>
                    <div
                        style={{
                            position: "absolute",
                            [pct >= 0 ? "left" : "right"]: 0,
                            top: 0, height: "100%",
                            width: barWidth(pct),
                            background: heatC,
                            borderRadius: 2,
                            transition: "width 0.4s ease",
                        }}
                    />
                </div>

                {/* 변화율 */}
                <span style={{ ...MONO, color, fontSize: T.body, fontWeight: T.w_bold, minWidth: 70, textAlign: "right" }}>
                    {fmtPct(pct)}
                </span>

                {/* 펼침 화살표 */}
                <span
                    style={{
                        color: C.textTertiary, fontSize: T.body,
                        marginLeft: S.xs,
                        transition: "transform 0.2s",
                        transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)",
                        flexShrink: 0,
                    }}
                >
                    ▸
                </span>
            </div>

            {/* 대표 종목 (펼침) */}
            {isExpanded && Array.isArray(sector.top_stocks) && sector.top_stocks.length > 0 && (
                <div style={topStocksWrap}>
                    <span style={topStocksCap}>대표 종목</span>
                    <div style={{ display: "flex", flexDirection: "column" }}>
                        {sector.top_stocks.map((st: any, j: number) => (
                            <div
                                key={j}
                                style={{
                                    display: "flex", justifyContent: "space-between", alignItems: "baseline",
                                    padding: `${S.xs}px 0`,
                                    borderBottom: j < sector.top_stocks.length - 1 ? `1px solid ${C.border}` : "none",
                                }}
                            >
                                <span style={{ color: C.textPrimary, fontSize: T.body }}>{st.name}</span>
                                <div style={{ display: "flex", gap: S.lg, alignItems: "baseline" }}>
                                    <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap }}>
                                        {isUS ? `$${(st.price ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : `${(st.price ?? 0).toLocaleString()}원`}
                                    </span>
                                    <span style={{ ...MONO, color: pctColor(st.change_pct ?? 0), fontSize: T.cap, fontWeight: T.w_semi, minWidth: 60, textAlign: "right" }}>
                                        {fmtPct(st.change_pct ?? 0)}
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

function RotationRow({ sector }: { sector: any }) {
    const pct = sector.change_pct ?? 0
    return (
        <div
            style={{
                display: "flex", justifyContent: "space-between", alignItems: "flex-start",
                padding: `${S.sm}px 0`,
                borderBottom: `1px solid ${C.border}`,
                gap: S.md,
            }}
        >
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>
                    {sector.name}
                </div>
                {sector.reason && (
                    <div style={{ color: C.textTertiary, fontSize: T.cap, marginTop: 2, lineHeight: T.lh_normal }}>
                        {sector.reason}
                    </div>
                )}
            </div>
            <span style={{ ...MONO, color: pctColor(pct), fontSize: T.body, fontWeight: T.w_semi, flexShrink: 0 }}>
                {fmtPct(pct)}
            </span>
        </div>
    )
}


/* ─────────── 스타일 ─────────── */

const shell: CSSProperties = {
    width: "100%", boxSizing: "border-box",
    fontFamily: FONT, color: C.textPrimary,
    background: C.bgPage,
    border: `1px solid ${C.border}`,
    borderRadius: 16,
    padding: S.xxl,
    display: "flex", flexDirection: "column",
    gap: S.lg,
}

const headerRow: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    gap: S.md, flexWrap: "wrap",
}

const headerLeft: CSSProperties = {
    display: "flex", flexDirection: "column", gap: 2,
}

const titleStyle: CSSProperties = {
    fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary,
    letterSpacing: "-0.5px",
}

const metaRow: CSSProperties = {
    display: "flex", alignItems: "center", gap: S.sm,
}

const viewChips: CSSProperties = {
    display: "flex", gap: S.sm, flexWrap: "wrap",
}

const hr: CSSProperties = {
    height: 1, background: C.border, margin: 0,
}

const driftBox: CSSProperties = {
    background: `${C.warn}1A`,
    border: `1px solid ${C.warn}33`,
    borderRadius: R.md,
    padding: `${S.md}px ${S.lg}px`,
    display: "flex", flexDirection: "column",
    gap: S.xs,
}

const driftHeader: CSSProperties = {
    display: "flex", alignItems: "center", gap: S.sm,
}

const sectionCap: CSSProperties = {
    color: C.textTertiary,
    fontSize: T.cap,
    fontWeight: T.w_med,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
}

const rotationWrap: CSSProperties = {
    display: "flex", flexDirection: "column", gap: S.lg,
}

const listWrap: CSSProperties = {
    display: "flex", flexDirection: "column",
    maxHeight: 520, overflowY: "auto",
}

const topStocksWrap: CSSProperties = {
    padding: `${S.sm}px ${S.md}px`,
    background: C.bgPage,
    borderBottom: `1px solid ${C.border}`,
    display: "flex", flexDirection: "column", gap: S.xs,
}

const topStocksCap: CSSProperties = {
    color: C.textTertiary,
    fontSize: T.cap,
    fontWeight: T.w_med,
    letterSpacing: "0.05em",
    textTransform: "uppercase",
    marginBottom: S.xs,
}

const emptyBox: CSSProperties = {
    padding: `${S.xxl}px 0`, textAlign: "center",
}

const loadingBox: CSSProperties = {
    minHeight: 160,
    display: "flex", alignItems: "center", justifyContent: "center",
}


/* ─────────── Framer Property Controls ─────────── */

SectorMap.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    market: "kr",
}

addPropertyControls(SectorMap, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})

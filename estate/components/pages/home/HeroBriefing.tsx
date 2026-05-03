import { addPropertyControls, ControlType } from "framer"
import React, { useState, useEffect, useCallback, useRef } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE DESIGN TOKENS v1.5 ◆ (다크 + 골드 emphasis — 옵션 A 패밀리룩)
 * v1.0 (다크 기본) → v1.5 (골드 강조). v2.0 (화이트) 폐기 사유: 페이지 컨텍스트
 * (네비·지도·하단 헤더 모두 다크) 와 카드만 화이트면 부조화. 다크 패밀리룩
 * 채택 + 골드 액센트 적극 사용 (헤더·정책 제목·강조 숫자) = 옵션 A mockup 톤.
 * 직접 hex 박지 말고 C/X/R 만 쓴다.
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0A0908",        // deep black (옵션 A mockup 외곽 톤)
    bgCard: "#0F0D0A",        // 카드 — 페이지보다 미세히 밝음 (border 분리)
    bgElevated: "#16130E",    // sub-card (metric box) — 살짝 더 밝은 다크
    bgInput: "#1F1B14",
    border: "#26221C",        // 어두운 골드 톤 보더
    borderStrong: "#3A3024",  // 강조 디바이더
    textPrimary: "#F2EFE9",   // ivory
    textSecondary: "#A8A299",
    textTertiary: "#6B665E",
    textDisabled: "#4A453E",
    accent: "#B8864D",                          // 골드 정본
    accentBright: "#D4A26B",                    // 밝은 골드 (강조 — 정책 제목·숫자)
    accentSoft: "rgba(184,134,77,0.15)",        // 골드 15% (다크 위 옅은 wash)
    success: "#22C55E",       // 네온 그린 (다크 위 빛남)
    warn: "#F59E0B",          // amber
    danger: "#EF4444",        // 강한 red
    info: "#5BA9FF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_SERIF = "'Noto Serif KR', 'Times New Roman', serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
/* ◆ TOKENS END ◆ */

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE API BASE (P3-0 정본) ◆
 * Framer publish 도메인 ≠ Vercel API 도메인. 절대 URL 의무 (T29).
 * production domain only — build-specific URL 금지.
 * 미래 4개 ESTATE 컴포넌트 (systemPulse·landexHeatmap·regimeStrip·changeFeed)
 * 도 같은 BASE 인라인 (Framer 컨벤션 self-contained).
 * ────────────────────────────────────────────────────────────── */
const ESTATE_API_BASE = "https://project-yw131.vercel.app"
const ESTATE_HERO_BRIEFING_URL = `${ESTATE_API_BASE}/api/estate/hero-briefing`


/*
 * ESTATE HeroBriefing — P1 Mock UI
 *
 * 운영자(총책임자) 콘솔용 정책 브리핑 카드.
 * 디자인 의도: 운영자가 ESTATE 홈 진입 시 "지난 24시간에 무슨 정책이 떴고
 * AI 가 어떻게 해석했나" 단 하나의 카드로 즉시 파악.
 *
 * 트랩 회피:
 *   1. 가짜 정책 하드코딩 X — 실제 mock JSON 만 페치
 *   2. AI 한줄평 실패 시 mock 텍스트 X — 명시적 사유만 노출
 *   3. URL 은 실제 도메인만 (보도자료 게시판 진입 URL 허용, 가짜 게시글 ID 금지)
 *   7. 디자인 토큰 v1.0 그대로
 *
 * 3-state: loading / error / ok
 *   loading → skeleton placeholders
 *   error   → 빨간 테두리 박스 + 명시적 사유 (가짜 데이터 절대 안 깔림)
 *   ok      → 풀 카드
 *
 * 운영자 메타 노골적 노출(showAdminMeta=true):
 *   policy_24h, ai_success_7d, freshness_minutes, fallback_used,
 *   confidence, tokens, model, generated_at, data_source, wire_status
 */

interface Metric {
    label: string
    value: number
    unit: string
    context?: string
}

interface PolicyAI {
    model?: string
    confidence?: number
    tokens?: number
    fallback_used?: boolean
    generated_at?: string
}

interface Briefing {
    schema_version?: string
    generated_at: string
    policy: {
        id: string
        title: string
        source: string
        source_url?: string
        source_url_note?: string
        published_at?: string
        category?: string
        summary?: string
        key_metrics?: Metric[]
        affected_regions?: string[]
    }
    narrative?: {
        headline: string | null
        body?: string
        ai?: PolicyAI
        fallback_reason?: string
    }
    operator_meta?: {
        policy_24h?: number
        ai_success_7d?: number
        freshness_minutes?: number
        data_source?: string
        wire_status?: string
    }
}

type FetchState =
    | { status: "loading" }
    | { status: "error"; reason: string }
    | { status: "ok"; data: Briefing; fetchedAt: number }

/** 스키마 최소 검증. 4 필드 누락 시 schema_invalid. */
function validate(raw: any): { ok: true; data: Briefing } | { ok: false; reason: string } {
    if (!raw || typeof raw !== "object") return { ok: false, reason: "empty_response" }
    if (!raw.generated_at) return { ok: false, reason: "schema_invalid: generated_at missing" }
    if (!raw.policy) return { ok: false, reason: "schema_invalid: policy missing" }
    if (!raw.policy.id) return { ok: false, reason: "schema_invalid: policy.id missing" }
    if (!raw.policy.title) return { ok: false, reason: "schema_invalid: policy.title missing" }
    if (!raw.policy.source) return { ok: false, reason: "schema_invalid: policy.source missing" }
    return { ok: true, data: raw as Briefing }
}

interface Props {
    jsonUrl: string
    refreshIntervalSec: number
    showAdminMeta: boolean
}

export default function HeroBriefing({ jsonUrl, refreshIntervalSec = 300, showAdminMeta = true }: Props) {
    const [state, setState] = useState<FetchState>({ status: "loading" })
    const inflight = useRef<AbortController | null>(null)

    const load = useCallback(async () => {
        if (!jsonUrl) {
            setState({ status: "error", reason: "no jsonUrl prop" })
            return
        }
        inflight.current?.abort()
        const ac = new AbortController()
        inflight.current = ac
        try {
            const sep = jsonUrl.includes("?") ? "&" : "?"
            const res = await fetch(`${jsonUrl}${sep}_=${Date.now()}`, {
                cache: "no-store",
                signal: ac.signal,
            })
            if (!res.ok) {
                setState({ status: "error", reason: `HTTP ${res.status}` })
                return
            }
            const raw = await res.json()
            const v = validate(raw)
            if (!v.ok) {
                setState({ status: "error", reason: v.reason })
                return
            }
            setState({ status: "ok", data: v.data, fetchedAt: Date.now() })
        } catch (e: any) {
            if (e?.name === "AbortError") return
            setState({ status: "error", reason: e?.message || "fetch failed" })
        }
    }, [jsonUrl])

    useEffect(() => {
        load()
        const sec = Math.max(30, refreshIntervalSec || 300)
        const id = setInterval(load, sec * 1000)
        return () => {
            clearInterval(id)
            inflight.current?.abort()
        }
    }, [load, refreshIntervalSec])

    /* ─── render shell ─── */
    return (
        <div style={cardStyle}>
            <StatusBar state={state} />
            <Header />

            <SectionDivider label="// POLICY · 24h" />
            {state.status === "loading" && <SkeletonPolicy />}
            {state.status === "error" && <ErrorBox reason={state.reason} stage="policy" />}
            {state.status === "ok" && <PolicyBlock data={state.data} />}

            <SectionDivider label="// INTELLIGENCE" />
            {state.status === "loading" && <SkeletonNarrative />}
            {state.status === "error" && <ErrorBox reason={state.reason} stage="intelligence" />}
            {state.status === "ok" && <NarrativeBlock data={state.data} />}

            {showAdminMeta && (
                <>
                    <SectionDivider label="// META" />
                    {state.status === "ok"
                        ? <MetaBlock data={state.data} fetchedAt={state.fetchedAt} />
                        : <div style={{ color: C.textTertiary, fontSize: 11, fontFamily: FONT_MONO, padding: "8px 0" }}>
                            META unavailable — {state.status}
                        </div>}
                </>
            )}

            <Footer />
        </div>
    )
}

/* ─── Subviews ─── */

function StatusBar({ state }: { state: FetchState }) {
    const isOk = state.status === "ok"
    const isErr = state.status === "error"
    const dot = isOk ? C.success : isErr ? C.danger : C.warn
    const label = isOk ? "LIVE" : isErr ? "ERROR" : "LOADING"
    const right = state.status === "ok"
        ? `${ageStr(state.fetchedAt)} · KR`
        : state.status === "error"
            ? "RETRY · 5m"
            : "FETCH · KR"

    return (
        <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            paddingBottom: 14, marginBottom: 18,
            borderBottom: `1px solid ${C.border}`,
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: dot, boxShadow: `0 0 6px ${dot}88`,
                }} />
                <span style={{
                    color: C.textSecondary, fontSize: 10, fontWeight: 700,
                    fontFamily: FONT_MONO, letterSpacing: "0.12em",
                }}>{label}</span>
            </div>
            <span style={{
                color: C.textTertiary, fontSize: 10, fontWeight: 600,
                fontFamily: FONT_MONO, letterSpacing: "0.10em",
            }}>{right}</span>
        </div>
    )
}

function Header() {
    return (
        <div style={{ marginBottom: 18 }}>
            <div style={{
                color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO,
                letterSpacing: "0.18em", marginBottom: 4,
            }}>
                ESTATE · OPERATOR
            </div>
            <div style={{
                color: C.accent, fontSize: 24, fontWeight: 700, fontFamily: FONT_SERIF,
                letterSpacing: "-0.01em", lineHeight: 1.2,
            }}>
                정책 브리핑
            </div>
            <div style={{
                color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 4,
            }}>
                지난 24시간 정부 발표 + AI 한줄 해석
            </div>
        </div>
    )
}

function SectionDivider({ label }: { label: string }) {
    return (
        <div style={{
            display: "flex", alignItems: "center", gap: 10,
            margin: "16px 0 10px",
        }}>
            <span style={{
                color: C.textTertiary, fontSize: 10, fontWeight: 700,
                fontFamily: FONT_MONO, letterSpacing: "0.16em",
            }}>{label}</span>
            <div style={{ flex: 1, height: 1, background: C.border }} />
        </div>
    )
}

function PolicyBlock({ data }: { data: Briefing }) {
    const p = data.policy
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {/* meta row: source + published_at + category */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <Pill text={p.source} kind="accent" />
                {p.published_at && <Pill text={p.published_at} kind="muted" mono />}
                {p.category && <Pill text={p.category} kind="muted" />}
            </div>

            {/* title (serif) — 골드 강조 (옵션 A 패밀리룩) */}
            <div style={{
                color: C.accentBright, fontSize: 16, fontWeight: 700,
                fontFamily: FONT_SERIF, lineHeight: 1.4,
            }}>{p.title}</div>

            {/* summary */}
            {p.summary && (
                <div style={{
                    color: C.textSecondary, fontSize: 13, fontFamily: FONT,
                    lineHeight: 1.6,
                }}>{p.summary}</div>
            )}

            {/* key metrics grid */}
            {p.key_metrics && p.key_metrics.length > 0 && (
                <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))",
                    gap: 8, marginTop: 4,
                }}>
                    {p.key_metrics.map((m) => (
                        <div key={m.label} style={metricBoxStyle}>
                            <div style={{
                                color: C.textTertiary, fontSize: 10,
                                fontFamily: FONT_MONO, letterSpacing: "0.08em",
                                textTransform: "uppercase",
                            }}>{m.label}</div>
                            <div style={{
                                color: C.accent, fontSize: 18, fontWeight: 800,
                                fontFamily: FONT_MONO, marginTop: 2,
                            }}>
                                {m.value > 0 ? "+" : ""}{m.value}
                                <span style={{ fontSize: 11, marginLeft: 1, color: C.accentBright }}>{m.unit}</span>
                            </div>
                            {m.context && (
                                <div style={{
                                    color: C.textTertiary, fontSize: 10, fontFamily: FONT,
                                    marginTop: 2,
                                }}>{m.context}</div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* affected regions chips */}
            {p.affected_regions && p.affected_regions.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
                    {p.affected_regions.map((r) => (
                        <span key={r} style={chipStyle}>{r}</span>
                    ))}
                </div>
            )}

            {/* source url — 외부 링크, 가짜 ID 박지 않음 */}
            {p.source_url && (
                <div style={{ marginTop: 4 }}>
                    <a href={p.source_url} target="_blank" rel="noopener noreferrer" style={linkStyle}>
                        {p.source_url}
                    </a>
                    {p.source_url_note && (
                        <div style={{
                            color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO,
                            marginTop: 2, letterSpacing: "0.04em",
                        }}>{p.source_url_note}</div>
                    )}
                </div>
            )}
        </div>
    )
}

function NarrativeBlock({ data }: { data: Briefing }) {
    const n = data.narrative
    // headline === null → AI 실패. mock 텍스트 절대 안 깔린다.
    if (!n || n.headline === null || n.headline === undefined) {
        return (
            <div style={{
                padding: "12px 14px", borderRadius: R.md,
                border: `1px dashed ${C.borderStrong}`, background: "transparent",
            }}>
                <div style={{
                    color: C.textTertiary, fontSize: 11, fontWeight: 700,
                    fontFamily: FONT_MONO, letterSpacing: "0.10em", marginBottom: 4,
                }}>
                    AI NARRATIVE UNAVAILABLE
                </div>
                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                    {n?.fallback_reason || "사유 미보고. mock 텍스트 비어있음."}
                </div>
            </div>
        )
    }

    const ai = n.ai
    return (
        <div style={{
            padding: "12px 14px", borderRadius: R.md,
            background: C.accentSoft, border: `1px solid ${C.accent}30`,
        }}>
            <div style={{
                color: C.accent, fontSize: 14, fontWeight: 700, fontFamily: FONT_SERIF,
                lineHeight: 1.4, marginBottom: 6,
            }}>{n.headline}</div>
            {n.body && (
                <div style={{ color: C.textPrimary, fontSize: 13, fontFamily: FONT, lineHeight: 1.6 }}>
                    {n.body}
                </div>
            )}
            {ai && (
                <div style={{
                    display: "flex", gap: 10, flexWrap: "wrap",
                    marginTop: 10, paddingTop: 8, borderTop: `1px solid ${C.accent}20`,
                }}>
                    {ai.model && <MiniMeta k="MODEL" v={ai.model} />}
                    {typeof ai.confidence === "number" && <MiniMeta k="CONF" v={ai.confidence.toFixed(2)} />}
                    {typeof ai.tokens === "number" && <MiniMeta k="TOK" v={String(ai.tokens)} />}
                    {ai.fallback_used !== undefined && (
                        <MiniMeta
                            k="FALLBACK"
                            v={ai.fallback_used ? "YES" : "NO"}
                            tone={ai.fallback_used ? "warn" : "ok"}
                        />
                    )}
                </div>
            )}
        </div>
    )
}

function MetaBlock({ data, fetchedAt }: { data: Briefing; fetchedAt: number }) {
    const m = data.operator_meta || {}
    const cells: Array<[string, string, "ok" | "warn" | "neutral"]> = [
        ["GENERATED", data.generated_at, "neutral"],
        ["FETCHED", new Date(fetchedAt).toLocaleTimeString("ko-KR", { hour12: false }), "neutral"],
        ["POLICY/24H", String(m.policy_24h ?? "—"), (m.policy_24h ?? 0) > 0 ? "ok" : "neutral"],
        ["AI_SUCC/7D", typeof m.ai_success_7d === "number" ? `${(m.ai_success_7d * 100).toFixed(0)}%` : "—",
            (m.ai_success_7d ?? 0) >= 0.85 ? "ok" : "warn"],
        ["FRESH/MIN", String(m.freshness_minutes ?? "—"),
            (m.freshness_minutes ?? 0) <= 60 ? "ok" : "warn"],
        ["SOURCE", m.data_source || "—", m.data_source === "mock" ? "warn" : "ok"],
        ["WIRE", m.wire_status || "—", "neutral"],
        ["POLICY_ID", data.policy.id, "neutral"],
    ]
    return (
        <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))",
            gap: 6,
        }}>
            {cells.map(([k, v, tone]) => (
                <div key={k} style={metaCellStyle}>
                    <div style={{
                        color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO,
                        letterSpacing: "0.10em",
                    }}>{k}</div>
                    <div style={{
                        color: tone === "ok" ? C.success : tone === "warn" ? C.warn : C.textPrimary,
                        fontSize: 11, fontFamily: FONT_MONO, marginTop: 2,
                        wordBreak: "break-all",
                    }}>{v}</div>
                </div>
            ))}
        </div>
    )
}

function MiniMeta({ k, v, tone = "ok" }: { k: string; v: string; tone?: "ok" | "warn" | "neutral" }) {
    const color = tone === "warn" ? C.warn : tone === "ok" ? C.textPrimary : C.textSecondary
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            <span style={{
                color: C.textTertiary, fontSize: 9, fontFamily: FONT_MONO,
                letterSpacing: "0.10em",
            }}>{k}</span>
            <span style={{ color, fontSize: 11, fontFamily: FONT_MONO, fontWeight: 700 }}>{v}</span>
        </div>
    )
}

function Pill({ text, kind, mono }: { text: string; kind: "accent" | "muted"; mono?: boolean }) {
    const isAccent = kind === "accent"
    return (
        <span style={{
            padding: "2px 8px", borderRadius: R.pill,
            background: isAccent ? `${C.accent}15` : C.bgElevated,
            border: `1px solid ${isAccent ? `${C.accent}40` : C.border}`,
            color: isAccent ? C.accentBright : C.textSecondary,
            fontSize: 11, fontFamily: mono ? FONT_MONO : FONT,
            fontWeight: 600, letterSpacing: mono ? "0.06em" : 0,
        }}>{text}</span>
    )
}

function ErrorBox({ reason, stage }: { reason: string; stage: string }) {
    return (
        <div style={{
            padding: "10px 12px", borderRadius: R.md,
            background: `${C.danger}10`, border: `1px solid ${C.danger}40`,
        }}>
            <div style={{
                color: C.danger, fontSize: 11, fontWeight: 800,
                fontFamily: FONT_MONO, letterSpacing: "0.10em", marginBottom: 4,
            }}>
                {stage.toUpperCase()} · LOAD FAILED
            </div>
            <div style={{
                color: C.textSecondary, fontSize: 12, fontFamily: FONT_MONO,
                wordBreak: "break-all",
            }}>{reason}</div>
        </div>
    )
}

function SkeletonPolicy() {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <SkelLine w="40%" h={14} />
            <SkelLine w="90%" h={18} />
            <SkelLine w="70%" h={12} />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginTop: 4 }}>
                <SkelBox h={56} /><SkelBox h={56} /><SkelBox h={56} />
            </div>
        </div>
    )
}

function SkeletonNarrative() {
    return (
        <div style={{
            padding: "12px 14px", borderRadius: R.md,
            border: `1px dashed ${C.border}`,
        }}>
            <SkelLine w="60%" h={14} />
            <div style={{ height: 6 }} />
            <SkelLine w="100%" h={11} />
            <div style={{ height: 4 }} />
            <SkelLine w="85%" h={11} />
        </div>
    )
}

function SkelLine({ w, h }: { w: string; h: number }) {
    return <div style={{
        width: w, height: h, borderRadius: R.sm,
        background: `linear-gradient(90deg, ${C.bgElevated} 0%, ${C.bgInput} 50%, ${C.bgElevated} 100%)`,
        backgroundSize: "200% 100%",
        animation: "estateSkel 1.4s ease-in-out infinite",
    }} />
}

function SkelBox({ h }: { h: number }) {
    return <div style={{
        height: h, borderRadius: R.md,
        background: C.bgElevated,
        border: `1px solid ${C.border}`,
    }} />
}

function Footer() {
    return (
        <div style={{
            marginTop: 18, paddingTop: 14,
            borderTop: `1px solid ${C.border}`,
            display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
            <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.10em" }}>
                ESTATE · INTERNAL
            </span>
            <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.10em" }}>
                v1.0 · ENCRYPTED
            </span>
        </div>
    )
}

/* ─── helpers ─── */
function ageStr(fetchedAt: number): string {
    const sec = Math.floor((Date.now() - fetchedAt) / 1000)
    if (sec < 60) return `${sec}s ago`
    const m = Math.floor(sec / 60)
    if (m < 60) return `${m}m ago`
    return `${Math.floor(m / 60)}h ago`
}

/* ─── Styles ─── */
const cardStyle: React.CSSProperties = {
    width: "100%", maxWidth: 720,
    background: C.bgCard, borderRadius: 20,
    border: `1px solid ${C.border}`,
    boxShadow: `0 0 0 1px rgba(184,134,77,0.06), 0 12px 40px rgba(0,0,0,0.4)`,
    padding: "24px 26px",
    fontFamily: FONT, color: C.textPrimary,
}

const metricBoxStyle: React.CSSProperties = {
    background: C.bgElevated, borderRadius: R.md,
    border: `1px solid ${C.border}`,
    padding: "8px 10px",
}

const chipStyle: React.CSSProperties = {
    padding: "3px 8px", borderRadius: R.pill,
    background: C.bgElevated, border: `1px solid ${C.border}`,
    color: C.textSecondary, fontSize: 11, fontFamily: FONT,
    fontWeight: 600,
}

const linkStyle: React.CSSProperties = {
    color: C.accentBright, fontSize: 11, fontFamily: FONT_MONO,
    textDecoration: "underline", wordBreak: "break-all",
}

const metaCellStyle: React.CSSProperties = {
    background: C.bgElevated, borderRadius: R.sm,
    border: `1px solid ${C.border}`,
    padding: "6px 8px",
}

/* skeleton keyframes (Framer 환경에서도 동작) */
if (typeof document !== "undefined" && !document.getElementById("estate-skel-kf")) {
    const s = document.createElement("style")
    s.id = "estate-skel-kf"
    s.textContent = `@keyframes estateSkel { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`
    document.head.appendChild(s)
}

HeroBriefing.defaultProps = {
    jsonUrl: ESTATE_HERO_BRIEFING_URL,
    refreshIntervalSec: 300,
    showAdminMeta: true,
}

addPropertyControls(HeroBriefing, {
    jsonUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: ESTATE_HERO_BRIEFING_URL,
        description: "P1 mock JSON 경로 또는 P2+ API URL",
    },
    refreshIntervalSec: {
        type: ControlType.Number,
        title: "Refresh (sec)",
        defaultValue: 300,
        min: 30, max: 3600, step: 30,
        description: "polling 간격 (최소 30s)",
    },
    showAdminMeta: {
        type: ControlType.Boolean,
        title: "Admin Meta",
        defaultValue: true,
        description: "운영자용 메타 노출 (confidence·tokens·freshness 등)",
    },
})

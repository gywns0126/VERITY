import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 유리박스 — VERITY 공개 터미널 (골든구스) 탭. 검증 과정 공개 = 핵심 차별점(정직).
 *
 * 데이터 = validation_summary.json (build_validation_summary.py, read-only 재집계, RULE 7).
 * 신뢰도 = 성과 숫자가 아니라 "엄밀함 + 전 신호 투명성 + 아직 안 끝났다는 정직"에서.
 *   PM 옵션 B(2026-06-18): 공개=과정·방법·진행만. raw 성과(IC/적중률/기댓값/CI)=검증 후 공개.
 * 표시 정직화(2026-06-19): N=유효표본(관측 T/중첩 k), 달력 일수 아님. 방법론·마일스톤·출처·보류사유 세분화.
 * 🚨 되돌리지 말 것 (2026-08-18) — 표본 목표·진행률 표시를 **의도적으로 제거**했다.
 *   N=252 IC 게이트는 PM 결정(2026-08-15)으로 폐기됐다. 폐기 사유가 정확히 이 UI 형태였다:
 *   검정력을 따지지 않고 표본만 요구하면 출력이 언제나 "더 모아라" 가 된다. 기다림은 결론이 아니다.
 *   백엔드는 이미 `gate: null` 을 보낸다 — 여기서 목표치를 폴백으로 되살리면 폐기가 무효가 된다.
 * RULE 6 — ⓘ/문구 평문 사전 작성. 런타임 LLM 0. ⓘ = 항상 표시, PC hover / 모바일 탭, 툴팁 clamp.
 * 스켈레톤(2026-07-05 PM): 실사이트 로딩 = 토스식 shimmer 스켈레톤. SAMPLE 은 캔버스 전용 —
 *   가짜 숫자(N_eff 145 등) flash 는 RULE 7 위반 소지. 실패 시 sessionStorage 캐시 → 재시도 안내.
 * 테마: Framer 네이티브 추종 — body[data-framer-theme] 읽어 dark 전환(캔버스는 dark prop 정적 프리뷰).
 */

const LIGHT = {
    bg: "#f2f4f6",
    card: "#ffffff",
    ink: "#191f28",
    sub: "#4e5968",
    faint: "#8b95a1",
    line: "#e5e8eb",
    vt: "#6c5ce7",
    vtS: "#f0edff",
    vg: "#0ca678",
    vgS: "#e7faf0",
    amber: "#ff9500",
    amberS: "#fff6e9",
    tipBg: "#191f28",
    tipFg: "#ffffff",
}
const DARK = {
    bg: "#0f1318",
    card: "#171c23",
    ink: "#e3e7ec",
    sub: "#9aa4b1",
    faint: "#828d9b",
    line: "#252b34",
    vt: "#a99bff",
    vtS: "#241f3a",
    vg: "#7fffa0",
    vgS: "#11281d",
    amber: "#ff9500",
    amberS: "#2a2113",
    tipBg: "#222a33",
    tipFg: "#e3e7ec",
}
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const INFO: Record<string, string> = {
    "표본 N":
        "검증 표본 = 전 종목 채점 누적(관측 T)을 예측 중첩(k)으로 나눈 유효표본 N_eff예요. 달력 일수가 아니라 관측 횟수라, 한 번 채점에 여러 종목이 더해져 빨리 쌓여요. 같은 날 종목들은 시장과 함께 움직여 서로 상관되니, N_eff는 진짜 독립 표본보다 다소 큰(낙관) 추정이에요. 표본이 작으면 동전 던지기와 구분되지 않습니다. 다만 '몇 개면 충분' 이라는 고정 최소선은 두지 않습니다 — 필요한 표본 수는 재려는 효과의 크기에 따라 달라지기 때문입니다.",
    "전진 검증":
        "예측을 먼저 기록하고, 만기일이 와야 그때의 미래 실현가로 채점해요. 미래를 미리 보는 일(look-ahead)이 구조적으로 불가능한 방식이라, 과거에 끼워맞춘 백테스트와 달라요.",
    IC: "예측 순위와 실제 수익 순위가 같은 방향인 정도(정보계수). 0이면 동전 던지기, 높을수록 예측력이 있다는 뜻이에요. 표본이 충분해야 의미가 생겨요.",
    사전등록:
        "산식·기준을 검증 시작 전에 문서로 고정하는 것. 결과가 좋게 나오라고 나중에 기준을 바꾸는 곡선 맞추기를 막는 장치예요.",
    DSR: "여러 전략을 시도하면 우연히 좋아 보이는 게 하나쯤 나와요. 그 다중검정을 보정한 샤프지수(Deflated Sharpe). 통과하려면 더 큰 표본(N≥684쯤)이 필요해요.",
}

const SIGNAL_NAME: Record<string, string> = {
    brain_production: "Brain 종합 판정",
    xgb_ml: "XGB 머신러닝 (shadow)",
    factor: "팩터 IC",
    sector: "섹터 로테이션",
}

// 통계 마일스톤 계단 (문서화 상수 — RULE 7 / project_minimum_n_milestones)
const MILESTONES = [
    { n: 30, label: "통계 무의미선", desc: "N<30 = 결론 불가" },
    { n: 100, label: "예비 관찰", desc: "N≥100 = 예비(잠정)" },
    // 🚨 2026-08-18 — N=252 "IC 게이트" 제거. 표본 수 게이트는 PM 결정(2026-08-15)으로
    //   폐기됐다: 검정력을 따지지 않고 표본만 요구하는 형태라 출력이 언제나 "더 모아라" 였다.
    //   30·100 라벨과 684 DSR 참조값은 유지된다(폐기 대상이 아니었다).
    { n: 684, label: "DSR 참조", desc: "다중검정 보정 참조값 (목표 아님)" },
]

interface Sig {
    signal: string
    status?: string
    n?: number
    n_eff?: number
    label?: string
    gate_status?: string
    source?: string
}
interface Gate {
    // 🚨 2026-08-18 — `target_n` · `progress_pct` 제거. 백엔드가 더 보내지 않고(폐기 정합),
    //   타입에 남겨두면 다음 편집자가 "채워야 할 값" 으로 오해해 폴백을 되살린다.
    milestone?: string
    best_signal_n?: number
}

interface Props {
    validationUrl: string
    dark: boolean
}

const DEFAULT_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/validation_summary.json"

const SAMPLE = {
    generated_at: "2026-06-19T17:16:01+09:00",
    gate: {
        milestone: "표본 목표 없음 — 사전 검정력 관문 확정 대기",
        best_signal_n: 145.2,
    },
    signals: [
        {
            signal: "brain_production",
            status: "채점 진행 중",
            n: 726,
            n_eff: 145.2,
            label: "표본 N≥100 누적 (잠정 — 유의성 미검증)",
            gate_status: "가설 (유의성 미달)",
            source: "prediction_ic_history.jsonl (Brain 종합 verdict, prediction_scoring v0)",
        },
        {
            signal: "xgb_ml",
            status: "trail 누적, 채점 도달 0",
            n: null,
            n_eff: null,
            label: "데이터 없음",
            gate_status: "가설 (관측 0)",
            source: "ml_prediction_ic_history.jsonl (XGB up_probability shadow)",
        },
        {
            signal: "factor",
            status: "IC 시계열 누적 중",
            n: 53,
            n_eff: null,
            label: "예비 (N<100, 검증 진행 중)",
            gate_status: "가설 (유의성 미달)",
            source: "factor_ic_history.json (ic_stats machinery, forward_days 30)",
        },
        {
            signal: "sector",
            status: "채점 DEFERRED (return source 미확정)",
            n: 0,
            n_eff: null,
            label: "데이터 없음 (채점 보류)",
            gate_status: "가설 (채점 보류 — return source 미검증)",
            source: "prediction_trail.jsonl (target_type=sector)",
        },
    ] as Sig[],
}

function f2(v: any, d = 2): string {
    const x = Number(v)
    return isFinite(x) ? x.toFixed(d) : "—"
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.
let __anHyd = false
function anReadDark(): boolean {
    if (typeof document === "undefined") return false
    if (!__anHyd) {
        __anHyd = true
        return false
    }
    const h = document.documentElement
        ? document.documentElement.dataset.anTheme
        : null
    if (h === "dark") return true
    if (h === "light") return false
    return !!(document.body && document.body.dataset.framerTheme === "dark")
}

export default function PublicGlassboxTab(props: Props) {
    const { validationUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)
    const [failed, setFailed] = useState(false)
    const [openTip, setOpenTip] = useState<string>("")
    const [tipBox, setTipBox] = useState<{ left: number; width: number }>({
        left: 0,
        width: 250,
    })
    const [hoverCapable, setHoverCapable] = useState(true)
    const [themeDark, setThemeDark] = useState<boolean>(() =>
        RenderTarget.current() === RenderTarget.canvas ? !!dark : anReadDark()
    )

    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 dark prop 정적) */
    useEffect(() => {
        if (onCanvas) return
        const read = () => {
            const t =
                typeof document !== "undefined" && document.body
                    ? document.body.dataset.framerTheme
                    : ""
            setThemeDark(t === "dark")
        }
        read()
        if (
            typeof MutationObserver === "undefined" ||
            typeof document === "undefined" ||
            !document.body
        )
            return
        const obs = new MutationObserver(read)
        obs.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-framer-theme"],
        })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (typeof window === "undefined" || !window.matchMedia) return
        try {
            setHoverCapable(
                window.matchMedia("(hover: hover) and (pointer: fine)").matches
            )
        } catch {
            /* keep default */
        }
    }, [])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries) setW(e.contentRect.width)
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    useEffect(() => {
        if (typeof document === "undefined") return
        const close = () => setOpenTip("")
        document.addEventListener("click", close)
        return () => document.removeEventListener("click", close)
    }, [])

    useEffect(() => {
        if (onCanvas || !validationUrl) return
        let alive = true
        const fallback = () => {
            try {
                const c = sessionStorage.getItem("validation_summary")
                if (alive && c) {
                    setData(JSON.parse(c))
                    return
                }
            } catch (e) {
                /* ignore */
            }
            if (alive) setFailed(true)
        }
        fetch(validationUrl)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                // 🚨 2026-08-19 — 종전 조건은 `d && d.gate` 였다. 백엔드가 표본수 게이트
                //   폐기 정합으로 `gate` 를 **null** 로 보내기 시작하자(§7-1) 이 조건이
                //   항상 거짓이 되어, 데이터가 정상 도착했는데도 "검증 데이터를 불러오지
                //   못했어요" 를 띄웠다. **로드 판정을 폐기된 필드에 걸어둔 것**이 결함이다.
                //   이 컴포넌트가 실제로 렌더하는 것은 `signals` 이므로 그 기준으로 판정한다.
                if (d && Array.isArray(d.signals)) {
                    setData(d)
                    try {
                        sessionStorage.setItem(
                            "validation_summary",
                            JSON.stringify(d)
                        )
                    } catch (e) {
                        /* ignore */
                    }
                } else fallback()
            })
            .catch(fallback)
        return () => {
            alive = false
        }
    }, [validationUrl, onCanvas])

    const narrow = w > 0 && w < 560
    const pad = narrow ? 12 : 18

    const gate: Gate = (data && data.gate) || {}
    const signals: Sig[] = useMemo(() => {
        const s = (data && data.signals) || []
        if (!Array.isArray(s)) return []
        // VERITY wide-scan funnel = 비공개 자산 → 공개 유리박스 노출 금지 (feedback_verity_vs_alphanest_identity)
        return s.filter(
            (x: any) => x && String(x.signal || "").indexOf("funnel") === -1
        )
    }, [data])
    const bestSig = useMemo(() => {
        let best: Sig | null = null
        for (const s of signals) {
            if (
                s.n_eff != null &&
                (best == null || Number(s.n_eff) > Number(best.n_eff || 0))
            )
                best = s
        }
        return best
    }, [signals])

    // 🚨 2026-08-18 — 진행률·목표 표본 제거. 백엔드가 `gate` 를 **null** 로 보내기 시작했는데
    //   (폐기 정합) 여기 폴백이 `|| 252` 라 공개 페이지가 "N_eff 0 / 252 · 0%" 를 그리고 있었다.
    //   폐기된 목표를 0% 진행률로 되살린 셈이다. 표본은 **사실로만** 적는다.
    //   signals 의 n_eff 를 1차 출처로 쓴다 — gate 가 비어도 사실은 남는다.
    const curN =
        Number((bestSig && bestSig.n_eff) ?? gate.best_signal_n) || 0

    const updated = useMemo(() => {
        const g = data && data.generated_at
        if (!g || typeof g !== "string") return ""
        return g.slice(0, 16).replace("T", " ")
    }, [data])

    const openTipAt = (e: any, id: string) => {
        try {
            const root = rootRef.current?.getBoundingClientRect()
            const icon = e?.currentTarget?.getBoundingClientRect?.()
            if (root && icon && root.width > 0) {
                const M = 8
                const width = Math.min(250, Math.max(180, root.width - M * 2))
                const iconLeftC = icon.left - root.left
                const clampedLeftC = Math.max(
                    M,
                    Math.min(iconLeftC, root.width - width - M)
                )
                setTipBox({ left: Math.round(clampedLeftC - iconLeftC), width })
            }
        } catch {
            /* ignore */
        }
        setOpenTip(id)
    }

    // ⓘ — 항상 표시. PC: hover, 모바일: 탭. uid 로 인스턴스별 고유.
    const Info = ({ k, uid }: { k: string; uid: string }) => {
        if (!INFO[k]) return null
        const id = "i:" + k + ":" + uid
        const isOpen = openTip === id
        const hov = hoverCapable
            ? {
                  onMouseEnter: (e: any) => openTipAt(e, id),
                  onMouseLeave: () => setOpenTip(""),
              }
            : {}
        return (
            <span style={{ position: "relative", display: "inline-block" }}>
                <span
                    role="button"
                    tabIndex={0}
                    onClick={(e) => {
                        e.stopPropagation()
                        if (isOpen) setOpenTip("")
                        else openTipAt(e, id)
                    }}
                    {...hov}
                    style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: "1.42em",
                        height: "1.42em",
                        marginLeft: "0.35em",
                        borderRadius: "50%",
                        background: "#6c5ce7",
                        color: "#fff",
                        fontSize: "0.62em",
                        fontWeight: 700,
                        lineHeight: 1,
                        verticalAlign: "middle",
                        position: "relative",
                        top: "-0.08em",
                        cursor: "help",
                    }}
                >
                    i
                </span>
                {isOpen && (
                    <span
                        onClick={(e) => e.stopPropagation()}
                        style={{
                            position: "absolute",
                            top: "calc(100% + 4px)",
                            left: tipBox.left,
                            zIndex: 50,
                            display: "block",
                            width: tipBox.width,
                            background: C.tipBg,
                            color: C.tipFg,
                            borderRadius: 12,
                            padding: "11px 13px",
                            fontSize: 12.5,
                            fontWeight: 500,
                            lineHeight: 1.55,
                            boxShadow: "0 6px 20px rgba(0,0,0,0.18)",
                            whiteSpace: "normal",
                            textAlign: "left",
                        }}
                    >
                        <span
                            style={{
                                fontWeight: 700,
                                display: "block",
                                marginBottom: 3,
                                color: C.vg,
                            }}
                        >
                            {k}
                        </span>
                        {INFO[k]}
                    </span>
                )}
            </span>
        )
    }

    const card: CSSProperties = {
        background: C.card,
        borderRadius: 16,
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
    }
    const secTitle = (t: string, ix: number, infoKey?: string) => (
        <div
            style={{
                fontSize: 13,
                fontWeight: 800,
                color: C.ink,
                letterSpacing: "-0.3px",
                padding: "18px 2px 8px",
                display: "inline-flex",
                alignItems: "center",
            }}
        >
            {t}
            {infoKey ? <Info k={infoKey} uid={"sec" + ix} /> : null}
        </div>
    )

    const wrap: CSSProperties = {
        width: "100%",
        height: "100%",
        maxHeight: "100%",
        overflowY: "auto",
        overflowX: "hidden",
        background: C.bg,
        fontFamily: FONT,
        padding: pad,
        boxSizing: "border-box",
        color: C.ink,
    }

    // 방법론 항목 (사전 작성 — RULE 6)
    const METHOD = [
        {
            k: "전진 검증",
            t: "전진 검증(forward-only)",
            d: "예측을 먼저 기록 → 만기까지 대기 → 미래 실현가로 채점. look-ahead 0.",
        },
        {
            k: "IC",
            t: "횡단면 IC + 방향 적중",
            d: "예측 순위 vs 실제 수익 순위(Spearman IC) + up/down 적중률.",
        },
        {
            k: "표본 N",
            t: "중첩보정 유효표본",
            d: "관측 T를 예측 중첩 k로 나눈 N_eff 로 과대 카운트 억제(보수).",
        },
        {
            k: "사전등록",
            t: "사전등록 + 결정 피드백 0",
            d: "산식 spec v0 고정(곡선 맞추기 차단). 검증은 운영 판단에 되먹임 안 함(관측 only).",
        },
    ]

    // 로딩 스켈레톤 — 실데이터 도착 전 가짜 숫자 노출 0 (토스식 shimmer, StockReportSkeleton 패턴)
    if (!onCanvas && !data) {
        const base = C === DARK ? "#222a33" : "#e9edf1"
        const hi = C === DARK ? "#2d3742" : "#f3f5f7"
        const sk = (
            wd: number | string,
            h: number,
            r = 8,
            mt = 0
        ): CSSProperties => ({
            width: wd,
            height: h,
            borderRadius: r,
            marginTop: mt,
            background: base,
            backgroundImage: `linear-gradient(90deg, ${base} 25%, ${hi} 37%, ${base} 63%)`,
            backgroundSize: "800px 100%",
            animation: "vgbShimmer 1.4s ease-in-out infinite",
        })
        const skCard: CSSProperties = { ...card, padding: 16, marginTop: 12 }
        if (failed) {
            return (
                <div ref={rootRef} style={wrap}>
                    <div
                        style={{
                            ...card,
                            padding: "22px 18px",
                            marginTop: 12,
                            textAlign: "center",
                        }}
                    >
                        <div
                            style={{
                                fontSize: 13.5,
                                fontWeight: 800,
                                color: C.ink,
                            }}
                        >
                            검증 데이터를 불러오지 못했어요
                        </div>
                        <div
                            style={{
                                fontSize: 12,
                                color: C.faint,
                                fontWeight: 600,
                                marginTop: 5,
                            }}
                        >
                            네트워크 확인 후 새로고침 해주세요
                        </div>
                    </div>
                </div>
            )
        }
        return (
            <div ref={rootRef} style={wrap}>
                <style>
                    {
                        "@keyframes vgbShimmer { 0% { background-position: -800px 0 } 100% { background-position: 800px 0 } }"
                    }
                </style>
                <div style={sk(64, 22, 8)} />
                <div style={sk(280, 13, 7, 8)} />
                <div style={skCard}>
                    <div style={sk(180, 12, 6)} />
                    <div style={sk(150, 20, 8, 10)} />
                    <div style={sk("100%", 10, 5, 12)} />
                    <div style={sk("70%", 11, 6, 10)} />
                </div>
                <div style={skCard}>
                    {[0, 1, 2, 3].map((i) => (
                        <div key={i} style={{ paddingTop: i === 0 ? 0 : 12 }}>
                            <div style={sk(140, 13, 7)} />
                            <div style={sk("85%", 11, 6, 6)} />
                        </div>
                    ))}
                </div>
                {[0, 1].map((i) => (
                    <div key={i} style={skCard}>
                        <div style={sk(170, 14, 7)} />
                        <div style={sk(220, 12, 6, 8)} />
                    </div>
                ))}
            </div>
        )
    }

    return (
        <div ref={rootRef} style={wrap}>
            <div style={{ marginBottom: 4 }}>
                <div
                    style={{
                        fontSize: narrow ? 18 : 20,
                        fontWeight: 800,
                        letterSpacing: "-0.5px",
                    }}
                >
                    검증
                </div>
                <div
                    style={{
                        fontSize: 12,
                        color: C.faint,
                        fontWeight: 600,
                        marginTop: 3,
                    }}
                >
                    검증 과정 공개 — 알파네스트는 검증되기 전엔 점수를 공개하지
                    않습니다
                </div>
            </div>

            {/* 1) 표본 현황 — 🚨 진행률 아님. 목표 표본 게이트는 폐기됐다(2026-08-15 결정) */}
            <div style={{ ...card, padding: "16px 16px", marginTop: 12 }}>
                <div
                    style={{
                        fontSize: 11.5,
                        color: C.faint,
                        fontWeight: 700,
                        marginBottom: 2,
                    }}
                >
                    검증 표본 현황 — 목표치 없음
                </div>
                <div
                    style={{
                        fontSize: 22,
                        fontWeight: 800,
                        letterSpacing: "-0.6px",
                        display: "inline-flex",
                        alignItems: "center",
                        flexWrap: "wrap",
                    }}
                >
                    <span>N_eff = {f2(curN, 1)}</span>
                    <Info k="표본 N" uid="gate" />
                </div>
                <div
                    style={{
                        fontSize: 11.5,
                        color: C.sub,
                        fontWeight: 600,
                        marginTop: 3,
                        lineHeight: 1.45,
                    }}
                >
                    관측 {bestSig && bestSig.n != null ? f2(bestSig.n, 0) : "—"}
                    건 누적 → 중첩보정 유효표본 {f2(curN, 1)} · 달력 일수 아님
                </div>
                <div
                    style={{
                        fontSize: 11.5,
                        color: C.faint,
                        fontWeight: 600,
                        lineHeight: 1.5,
                        marginTop: 8,
                    }}
                >
                    🚨 종전에는 여기에 "목표 표본까지 몇 %" 를 그렸습니다. 그 기준은
                    2026-08-15 에 폐기했습니다 — 검정력을 따지지 않은 채 표본 수만
                    요구하면 결론이 언제나 "더 모아라" 가 되기 때문입니다. 기다림은
                    결론이 아닙니다. 대체 기준(사전 검정력 관문)은 확정 전이라, 확정될
                    때까지 여기에 목표치를 지어내지 않습니다. 유의성 판정은 종전대로
                    p 값으로 하며 아래 신호별로 표기합니다.
                </div>
            </div>

            {/* 2) 검증 방법 (엄밀함 = 신뢰) */}
            {secTitle("검증 방법", 0)}
            <div style={{ ...card, padding: "6px 16px" }}>
                {METHOD.map((m, i) => (
                    <div
                        key={m.t}
                        style={{
                            padding: "11px 0",
                            borderTop: i === 0 ? "none" : `1px solid ${C.line}`,
                        }}
                    >
                        <div
                            style={{
                                fontSize: 13,
                                fontWeight: 700,
                                color: C.ink,
                                display: "inline-flex",
                                alignItems: "center",
                            }}
                        >
                            {m.t}
                            <Info k={m.k} uid={"m" + i} />
                        </div>
                        <div
                            style={{
                                fontSize: 12,
                                color: C.sub,
                                fontWeight: 500,
                                lineHeight: 1.5,
                                marginTop: 2,
                            }}
                        >
                            {m.d}
                        </div>
                    </div>
                ))}
            </div>

            {/* 3) 검증 단계 (마일스톤 계단) */}
            {secTitle("검증 단계", 1, "DSR")}
            <div style={{ ...card, padding: "12px 16px" }}>
                {MILESTONES.map((ms, i) => {
                    const reached = curN >= ms.n
                    const here =
                        curN >= ms.n &&
                        (i === MILESTONES.length - 1 ||
                            curN < MILESTONES[i + 1].n)
                    return (
                        <div
                            key={ms.n}
                            style={{
                                display: "flex",
                                gap: 11,
                                alignItems: "flex-start",
                                padding: "8px 0",
                                borderTop:
                                    i === 0 ? "none" : `1px solid ${C.line}`,
                            }}
                        >
                            <span
                                style={{
                                    flexShrink: 0,
                                    width: 9,
                                    height: 9,
                                    borderRadius: "50%",
                                    marginTop: 4,
                                    background: reached ? C.vg : C.line,
                                    border: here ? `2px solid ${C.vt}` : "none",
                                    boxSizing: "border-box",
                                }}
                            />
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div
                                    style={{
                                        fontSize: 12.5,
                                        fontWeight: 800,
                                        color: reached ? C.ink : C.faint,
                                    }}
                                >
                                    N≥{ms.n} · {ms.label}
                                    {here ? (
                                        <span
                                            style={{
                                                color: C.vt,
                                                fontWeight: 800,
                                            }}
                                        >
                                            {" "}
                                            ← 현재 N_eff {f2(curN, 0)}
                                        </span>
                                    ) : null}
                                </div>
                                <div
                                    style={{
                                        fontSize: 11.5,
                                        color: C.faint,
                                        fontWeight: 600,
                                        marginTop: 1,
                                        lineHeight: 1.5,
                                    }}
                                >
                                    {ms.desc}
                                </div>
                            </div>
                        </div>
                    )
                })}
            </div>

            {/* 4) 신호별 상태 (전 신호 투명 — 0건도 정직 표시) */}
            {secTitle("검증 중인 신호", 2)}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {signals.map((s, i) => {
                    const hasN = s.n != null && Number(s.n) > 0
                    const sigName = SIGNAL_NAME[s.signal] || s.signal
                    const srcShort = (s.source || "").split(" (")[0]
                    return (
                        <div key={i} style={{ ...card, padding: "13px 16px" }}>
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 8,
                                    flexWrap: "wrap",
                                    marginBottom: 4,
                                }}
                            >
                                <span
                                    style={{ fontSize: 14.5, fontWeight: 700 }}
                                >
                                    {sigName}
                                </span>
                                <span
                                    style={{
                                        fontSize: 10.5,
                                        fontWeight: 800,
                                        color: hasN ? C.vg : C.faint,
                                        background: hasN ? C.vgS : C.line,
                                        borderRadius: 6,
                                        padding: "2px 8px",
                                    }}
                                >
                                    {s.label || "데이터 없음"}
                                </span>
                            </div>
                            <div
                                style={{
                                    display: "flex",
                                    gap: 8,
                                    alignItems: "baseline",
                                    flexWrap: "wrap",
                                }}
                            >
                                <span
                                    style={{
                                        fontSize: 13.5,
                                        fontWeight: 800,
                                        display: "inline-flex",
                                        alignItems: "center",
                                    }}
                                >
                                    {s.n_eff != null
                                        ? `관측 ${f2(s.n, 0)}건 · 유효표본 ${f2(s.n_eff, 0)}`
                                        : hasN
                                          ? `관측 ${f2(s.n, 0)}건`
                                          : "관측 0"}
                                    <Info k="표본 N" uid={"sig" + i} />
                                </span>
                                <span
                                    style={{
                                        fontSize: 11.5,
                                        color: C.faint,
                                        fontWeight: 600,
                                    }}
                                >
                                    {s.gate_status || "게이트 미도달"}
                                </span>
                            </div>
                            {srcShort && (
                                <div
                                    style={{
                                        fontSize: 10.5,
                                        color: C.faint,
                                        fontWeight: 600,
                                        marginTop: 8,
                                        paddingTop: 8,
                                        borderTop: `1px solid ${C.line}`,
                                    }}
                                >
                                    출처 · {srcShort}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>

            {/* 5) 지금 안 보여주는 것 + 이유 (보류 = 신뢰 신호) */}
            {secTitle("지금 안 보여주는 것", 3)}
            <div
                style={{
                    background: C.amberS,
                    borderRadius: 14,
                    padding: "13px 15px",
                }}
            >
                <div
                    style={{
                        fontSize: 12.5,
                        fontWeight: 800,
                        color: C.amber,
                        marginBottom: 4,
                    }}
                >
                    점수·등급·적중률·IC·기댓값 = 검증 전까지 비공개
                </div>
                <div
                    style={{
                        fontSize: 12,
                        color: C.sub,
                        fontWeight: 600,
                        lineHeight: 1.55,
                    }}
                >
                    표본이 작을 때 좋아 보이는 숫자는 우연과 구분되지
                    않아요. 검증 안 된 성과를 보여주는 건 신뢰를 주는 게 아니라
                    깎는 일이라, 사전등록한 검정을 통과하기 전까지 의도적으로 가립니다.
                    증권사·앱이 구조적으로 안 하는 절제예요.
                </div>
            </div>

            {/* 6) 출처 · 갱신 (provenance) */}
            <div style={{ ...card, padding: "12px 16px", marginTop: 12 }}>
                <div
                    style={{
                        display: "flex",
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                        gap: 6,
                    }}
                >
                    <span
                        style={{
                            fontSize: 11.5,
                            color: C.faint,
                            fontWeight: 700,
                        }}
                    >
                        집계 방식
                    </span>
                    <span
                        style={{
                            fontSize: 11.5,
                            color: C.sub,
                            fontWeight: 600,
                        }}
                    >
                        채점 산출물 read-only 재집계 · 결정 피드백 0
                    </span>
                </div>
                {updated && (
                    <div
                        style={{
                            display: "flex",
                            justifyContent: "space-between",
                            flexWrap: "wrap",
                            gap: 6,
                            marginTop: 6,
                            paddingTop: 6,
                            borderTop: `1px solid ${C.line}`,
                        }}
                    >
                        <span
                            style={{
                                fontSize: 11.5,
                                color: C.faint,
                                fontWeight: 700,
                            }}
                        >
                            갱신
                        </span>
                        <span
                            style={{
                                fontSize: 11.5,
                                color: C.sub,
                                fontWeight: 600,
                            }}
                        >
                            {updated} KST · spec {data.spec_version || "v0"}
                        </span>
                    </div>
                )}
            </div>
        </div>
    )
}

addPropertyControls(PublicGlassboxTab, {
    validationUrl: {
        type: ControlType.String,
        title: "Validation URL",
        defaultValue: DEFAULT_URL,
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark",
        defaultValue: false,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
})

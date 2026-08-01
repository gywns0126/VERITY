// OperatorPicks — 오늘의 추천 종목 (오퍼레이터 전용, authed).
// 사용자 리스트의 "추천 종목". 재구축 컴포넌트.
// 되돌리지 말 것: authed /api/admin?type=portfolio_full 만 읽음(verity_supabase_session Bearer).
//   공개 blob 직독 금지(2026-08-01 봉인 규율). brain_score 노출은 오퍼레이터 authed 라 허용,
//   단 RULE 7 "가설 · 검증 N<252" 라벨 병기 의무 (검증 전 예측력 주장 아님).
import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

const API_BASE = "https://project-yw131.vercel.app"
const DATA_URL = API_BASE + "/api/admin?type=portfolio_full"
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', system-ui, sans-serif"
const MONO = "'SF Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

// 한국 관행: 매수/상승 = 빨강, 하락 = 파랑. 회피 = 파랑계열, 관망/주의 = 회색.
const C_BUY = "#f04452"
const C_AVOID = "#3182f6"
const C_NEU = "#8a8a94"

// verity_supabase_session → Bearer JWT (만료 체크). VerityBrainPanel/AdminDashboard 패턴 정합. esbuild 안전.
function _operatorAuthHeaders() {
    try {
        var raw =
            typeof localStorage !== "undefined"
                ? localStorage.getItem("verity_supabase_session")
                : null
        if (!raw) return {}
        var s = JSON.parse(raw)
        var ok = !s.expires_at || Date.now() / 1000 <= s.expires_at
        var jwt = ok ? s.access_token : null
        return jwt ? { Authorization: "Bearer " + jwt } : {}
    } catch (e) {
        return {}
    }
}

function readBodyDark() {
    if (typeof document === "undefined") return false
    try {
        var attr = document.documentElement.getAttribute("data-theme")
        if (attr === "dark") return true
        if (attr === "light") return false
        var t = localStorage.getItem("verity_theme")
        if (t === "dark") return true
        if (t === "light") return false
        if (window.matchMedia)
            return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {
        return false
    }
    return false
}

function recColor(rec) {
    var r = String(rec || "").toUpperCase()
    if (r.indexOf("BUY") >= 0) return C_BUY
    if (r.indexOf("AVOID") >= 0) return C_AVOID
    return C_NEU
}

function recLabel(rec) {
    var r = String(rec || "").toUpperCase()
    if (r === "STRONG_BUY") return "적극매수"
    if (r === "BUY") return "매수"
    if (r === "AVOID") return "회피"
    if (r === "CAUTION") return "주의"
    return "관망"
}

function num(v) {
    return typeof v === "number" && isFinite(v) ? v : null
}

function brainOf(r) {
    var vb = r && r.verity_brain ? r.verity_brain : null
    var score = vb && num(vb.brain_score) !== null ? vb.brain_score : num(r.brain_score)
    var grade = vb && vb.grade_label ? vb.grade_label : vb && vb.grade ? vb.grade : ""
    return { score: score, grade: grade }
}

const SAMPLE = {
    recommendations: [
        {
            name: "SK하이닉스",
            ticker: "000660",
            currency: "KRW",
            recommendation: "WATCH",
            verity_brain: { brain_score: 57, grade_label: "관망" },
            per: 11.5,
            pbr: 2.1,
            roe: 24.4,
            rec_price: 132000,
            ai_verdict: "브레인 57점 관망. 팩트 우위이나 검증 전 가설.",
        },
        {
            name: "NAVER",
            ticker: "035420",
            currency: "KRW",
            recommendation: "BUY",
            verity_brain: { brain_score: 59, grade_label: "관망" },
            per: 18.2,
            pbr: 1.3,
            roe: 12.1,
            rec_price: 210000,
            ai_verdict: "PBR 저평가 + 수급 개선. 가설.",
        },
    ],
}

/**
 * @framerSupportedLayoutWidth any-prefer-fixed
 * @framerSupportedLayoutHeight auto
 */
export default function OperatorPicks(props) {
    var limit = props && props.limit ? props.limit : 20

    var isCanvas = RenderTarget.current() === RenderTarget.canvas
    var st = useState([])
    var recs = st[0]
    var setRecs = st[1]
    var loadState = useState("loading")
    var status = loadState[0]
    var setStatus = loadState[1]
    var darkState = useState(false)
    var dark = darkState[0]
    var setDark = darkState[1]

    useEffect(function () {
        setDark(readBodyDark())
    }, [])

    useEffect(
        function () {
            if (isCanvas) {
                setRecs(SAMPLE.recommendations)
                setStatus("ok")
                return
            }
            var cancelled = false
            var headers = _operatorAuthHeaders()
            if (!headers.Authorization) {
                setStatus("auth")
                return
            }
            fetch(DATA_URL, { headers: headers })
                .then(function (r) {
                    if (r.status === 401 || r.status === 403) throw new Error("auth")
                    if (!r.ok) throw new Error("http")
                    return r.json()
                })
                .then(function (d) {
                    if (cancelled) return
                    var list = d && d.recommendations ? d.recommendations : []
                    setRecs(list)
                    setStatus("ok")
                })
                .catch(function (e) {
                    if (cancelled) return
                    setStatus(String(e.message) === "auth" ? "auth" : "error")
                })
            return function () {
                cancelled = true
            }
        },
        [isCanvas]
    )

    var bg = dark ? "#0f0f14" : "#f7f7f9"
    var card = dark ? "#17171c" : "#ffffff"
    var fg = dark ? "#f2f2f5" : "#1a1a1e"
    var sub = dark ? "#9a9aa5" : "#8a8a94"
    var border = dark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.06)"

    var wrap = {
        fontFamily: FONT,
        background: bg,
        padding: 16,
        borderRadius: 18,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        width: "100%",
        boxSizing: "border-box",
    }

    if (status === "auth") {
        return (
            <div style={wrap}>
                <div style={{ color: fg, fontSize: 15, fontWeight: 700 }}>추천 종목</div>
                <div style={{ color: sub, fontSize: 13, lineHeight: 1.5 }}>
                    오퍼레이터 로그인이 필요합니다 (VERITY = 비공개).
                </div>
            </div>
        )
    }
    if (status === "error") {
        return (
            <div style={wrap}>
                <div style={{ color: fg, fontSize: 15, fontWeight: 700 }}>추천 종목</div>
                <div style={{ color: C_AVOID, fontSize: 13 }}>데이터를 불러오지 못했습니다.</div>
            </div>
        )
    }

    var sorted = recs.slice()
    sorted.sort(function (a, b) {
        var sa = brainOf(a).score
        var sb = brainOf(b).score
        return (sb === null ? -1 : sb) - (sa === null ? -1 : sa)
    })
    var shown = sorted.slice(0, limit)

    return (
        <div style={wrap}>
            <div
                style={{
                    display: "flex",
                    alignItems: "baseline",
                    justifyContent: "space-between",
                }}
            >
                <div style={{ color: fg, fontSize: 15, fontWeight: 800, letterSpacing: "-0.02em" }}>
                    오늘의 추천 종목
                </div>
                <div style={{ color: sub, fontSize: 11 }}>
                    가설 · 검증 N&lt;252 (2027) · 예측 아님
                </div>
            </div>

            {shown.map(function (r, i) {
                var b = brainOf(r)
                var isUS = r.currency === "USD"
                var price = num(r.rec_price)
                var per = num(r.per)
                var pbr = num(r.pbr)
                var roe = num(r.roe)
                var accent = recColor(r.recommendation)
                return (
                    <div
                        key={(r.ticker || "") + i}
                        style={{
                            background: card,
                            borderRadius: 14,
                            border: "1px solid " + border,
                            padding: "12px 14px",
                            display: "flex",
                            flexDirection: "column",
                            gap: 8,
                        }}
                    >
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                gap: 8,
                            }}
                        >
                            <div style={{ display: "flex", alignItems: "baseline", gap: 7, minWidth: 0 }}>
                                <span
                                    style={{
                                        fontSize: 15,
                                        fontWeight: 700,
                                        color: fg,
                                        letterSpacing: "-0.02em",
                                        whiteSpace: "nowrap",
                                        overflow: "hidden",
                                        textOverflow: "ellipsis",
                                    }}
                                >
                                    {r.name || r.ticker}
                                </span>
                                <span style={{ fontFamily: MONO, fontSize: 11, color: sub }}>
                                    {r.ticker}
                                </span>
                            </div>
                            <span
                                style={{
                                    fontSize: 11,
                                    fontWeight: 800,
                                    color: "#fff",
                                    background: accent,
                                    borderRadius: 7,
                                    padding: "3px 8px",
                                    whiteSpace: "nowrap",
                                }}
                            >
                                {recLabel(r.recommendation)}
                            </span>
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                            {b.score !== null ? (
                                <span style={{ fontSize: 12, color: sub }}>
                                    브레인{" "}
                                    <span style={{ color: fg, fontWeight: 700, fontFamily: MONO }}>
                                        {Math.round(b.score)}
                                    </span>
                                    {b.grade ? <span style={{ color: sub }}> · {b.grade}</span> : null}
                                    <span style={{ color: sub, fontSize: 10 }}> (가설)</span>
                                </span>
                            ) : null}
                            {per !== null ? (
                                <span style={{ fontSize: 12, color: sub }}>
                                    PER <span style={{ color: fg, fontFamily: MONO }}>{per.toFixed(1)}</span>
                                </span>
                            ) : null}
                            {pbr !== null ? (
                                <span style={{ fontSize: 12, color: sub }}>
                                    PBR <span style={{ color: fg, fontFamily: MONO }}>{pbr.toFixed(1)}</span>
                                </span>
                            ) : null}
                            {roe !== null ? (
                                <span style={{ fontSize: 12, color: sub }}>
                                    ROE <span style={{ color: fg, fontFamily: MONO }}>{roe.toFixed(1)}%</span>
                                </span>
                            ) : null}
                            {price !== null ? (
                                <span style={{ fontSize: 12, color: sub }}>
                                    기준가{" "}
                                    <span style={{ color: fg, fontFamily: MONO }}>
                                        {isUS ? "$" + price.toFixed(2) : Math.round(price).toLocaleString()}
                                    </span>
                                </span>
                            ) : null}
                        </div>

                        {r.ai_verdict ? (
                            <div
                                style={{
                                    fontSize: 12,
                                    color: sub,
                                    lineHeight: 1.45,
                                    borderTop: "1px solid " + border,
                                    paddingTop: 7,
                                }}
                            >
                                {r.ai_verdict}
                            </div>
                        ) : null}
                    </div>
                )
            })}

            {shown.length === 0 ? (
                <div style={{ color: sub, fontSize: 13, padding: "8px 0" }}>추천 종목이 없습니다.</div>
            ) : null}
        </div>
    )
}

addPropertyControls(OperatorPicks, {
    limit: {
        type: ControlType.Number,
        title: "표시 개수",
        defaultValue: 20,
        min: 3,
        max: 60,
        step: 1,
        displayStepper: true,
    },
})

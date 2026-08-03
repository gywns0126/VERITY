// TriSynthesisPanel — 3종 LLM 종합 분석 (② 판단 층 센터피스, 오퍼레이터 전용).
// 검색(StockSearch)이 쏜 verity-ticker / ?q= / verity_last_ticker 를 수신해 해당 종목 종합 표시.
// 되돌리지 말 것: authed /api/admin?type=tri_synthesis 만 읽음(Brain grounding=오퍼레이터 전용).
//   공개 blob 직독 금지. RULE 7: LLM 의견=의견(provenance 분리 표기), Brain=가설(N<252) 라벨 필수.
import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

const API_BASE = "https://project-yw131.vercel.app"
const DATA_URL = API_BASE + "/api/admin?type=tri_synthesis"
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', system-ui, sans-serif"
const PURPLE = "#6c5ce7"
const PPLX = "#20808d"   // Perplexity teal
const GEM = "#4285f4"    // Gemini blue

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

function initialTicker() {
    try {
        var u = new URL(window.location.href)
        var q = u.searchParams.get("q")
        if (q) return q.toUpperCase()
        var last = localStorage.getItem("verity_last_ticker")
        if (last) return last.toUpperCase()
    } catch (e) {}
    return ""
}

const SAMPLE = {
    _meta: { generated_at: "2026-08-01T06:00:00+09:00", n_syntheses: 25 },
    syntheses: {
        "000660": {
            ticker: "000660",
            name: "SK하이닉스",
            generated_at: "2026-08-01T06:00:00+09:00",
            sources: {
                claude: { content: "자체 Brain 등급(가설)은 관망이나 최근 수급·계약 사실은 우호적. 밸류에이션 부담과 상충 — 방향은 긍정, 크기는 신중. 지켜볼 트리거: HBM 추가 공급계약 공시.", model: "claude-opus-5" },
                perplexity: { content: "최근 1주: HBM 증설 발표, 외국인 3일 연속 순매수.", citations: ["https://dart.fss.or.kr/..."], model: "sonar-pro" },
                gemini: { content: "강점: 메모리 업사이클·수급. 약점: 밸류 부담. 지켜볼 것: 환율.", model: "gemini-2.5-flash-lite" },
            },
            verity_trail: { summary: "[VERITY 자체 trail — 검증 전 가설]\n- Brain 등급: 관망 (57, 가설)", has_trail: true },
            disclosure: { rule7_hypothesis: true },
        },
    },
}

/**
 * @framerSupportedLayoutWidth any-prefer-fixed
 * @framerSupportedLayoutHeight auto
 */
export default function TriSynthesisPanel(props) {
    var isCanvas = RenderTarget.current() === RenderTarget.canvas

    var dataState = useState(null)
    var data = dataState[0]
    var setData = dataState[1]
    var statusState = useState("loading")
    var status = statusState[0]
    var setStatus = statusState[1]
    var tickerState = useState("")
    var ticker = tickerState[0]
    var setTicker = tickerState[1]
    var darkState = useState(false)
    var dark = darkState[0]
    var setDark = darkState[1]

    useEffect(function () {
        setDark(readBodyDark())
        setTicker(isCanvas ? "000660" : initialTicker())
    }, [])

    // 검색이 쏜 종목 선택 수신
    useEffect(function () {
        if (isCanvas) return
        function onTicker(e) {
            var t = e && e.detail && e.detail.ticker ? String(e.detail.ticker).toUpperCase() : ""
            if (t) setTicker(t)
        }
        window.addEventListener("verity-ticker", onTicker)
        return function () {
            window.removeEventListener("verity-ticker", onTicker)
        }
    }, [isCanvas])

    useEffect(
        function () {
            if (isCanvas) {
                setData(SAMPLE)
                setStatus("ok")
                return
            }
            var headers = _operatorAuthHeaders()
            if (!headers.Authorization) {
                setStatus("auth")
                return
            }
            var cancelled = false
            fetch(DATA_URL, { headers: headers })
                .then(function (r) {
                    if (r.status === 401 || r.status === 403) throw new Error("auth")
                    if (!r.ok) throw new Error("http")
                    return r.json()
                })
                .then(function (d) {
                    if (cancelled) return
                    setData(d)
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
        width: "100%",
        boxSizing: "border-box",
        display: "flex",
        flexDirection: "column",
        gap: 12,
    }

    function Title() {
        return (
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                <div style={{ color: fg, fontSize: 15, fontWeight: 800, letterSpacing: "-0.02em" }}>
                    3종 LLM 종합
                </div>
                <div style={{ color: sub, fontSize: 11 }}>Brain=가설 N&lt;252 · LLM 의견=의견</div>
            </div>
        )
    }

    if (status === "auth") {
        return (
            <div style={wrap}>
                <Title />
                <div style={{ color: sub, fontSize: 13, lineHeight: 1.5 }}>
                    오퍼레이터 로그인이 필요합니다 (VERITY = 비공개).
                </div>
            </div>
        )
    }
    if (status === "error") {
        return (
            <div style={wrap}>
                <Title />
                <div style={{ color: "#f04452", fontSize: 13 }}>데이터를 불러오지 못했습니다.</div>
            </div>
        )
    }

    var syn = data && data.syntheses ? data.syntheses[ticker] : null
    if (!syn) {
        return (
            <div style={wrap}>
                <Title />
                <div style={{ color: sub, fontSize: 13, lineHeight: 1.55 }}>
                    {ticker ? ticker + " 는 사전 종합 대상이 아닙니다." : "종목을 검색해 선택하세요."}
                    <br />3종 LLM 종합은 비용 관리를 위해 추천 상위 종목만 주 1회 사전계산됩니다.
                </div>
            </div>
        )
    }

    var s = syn.sources || {}
    var cl = s.claude || {}
    var px = s.perplexity || {}
    var gm = s.gemini || {}

    function Block(opts) {
        // opts: {tag, tagColor, model, kind, text, citations}
        return (
            <div
                style={{
                    background: card,
                    borderRadius: 14,
                    border: "1px solid " + border,
                    borderLeft: "3px solid " + opts.tagColor,
                    padding: "12px 14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 11, fontWeight: 800, color: opts.tagColor }}>{opts.tag}</span>
                    <span style={{ fontSize: 10, color: sub }}>{opts.model || ""}</span>
                    <span style={{ fontSize: 10, color: sub }}>· {opts.kind}</span>
                </div>
                <div style={{ fontSize: 13, color: fg, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
                    {opts.text || "(없음)"}
                </div>
                {opts.citations && opts.citations.length ? (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 2 }}>
                        {opts.citations.slice(0, 5).map(function (c, i) {
                            return (
                                <a
                                    key={i}
                                    href={c}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{ fontSize: 10, color: opts.tagColor, textDecoration: "none" }}
                                >
                                    출처 {i + 1} →
                                </a>
                            )
                        })}
                    </div>
                ) : null}
            </div>
        )
    }

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                <div style={{ color: fg, fontSize: 16, fontWeight: 800, letterSpacing: "-0.02em" }}>
                    {syn.name || ticker}{" "}
                    <span style={{ fontSize: 12, color: sub, fontWeight: 500 }}>{ticker}</span>
                </div>
                <div style={{ color: sub, fontSize: 10 }}>3종 LLM · Brain=가설</div>
            </div>

            {/* 종합 (Claude) 을 앞에 — 판단의 정합본 */}
            {Block({ tag: "종합", tagColor: PURPLE, model: cl.model, kind: "판단(의견)", text: cl.content })}
            {/* 신선 사실 (Perplexity) */}
            {Block({ tag: "신선 사실", tagColor: PPLX, model: px.model, kind: "외부 사실", text: px.content, citations: px.citations })}
            {/* 구조화 (Gemini) */}
            {Block({ tag: "구조화", tagColor: GEM, model: gm.model, kind: "정리(의견)", text: gm.content })}

            {syn.verity_trail && syn.verity_trail.summary ? (
                <div
                    style={{
                        background: card,
                        borderRadius: 14,
                        border: "1px dashed " + border,
                        padding: "11px 13px",
                    }}
                >
                    <div style={{ fontSize: 11, fontWeight: 700, color: sub, marginBottom: 5 }}>
                        VERITY 자체 관점 (가설, 검증 전)
                    </div>
                    <div style={{ fontSize: 12, color: fg, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
                        {syn.verity_trail.summary}
                    </div>
                </div>
            ) : null}

            <div style={{ fontSize: 10, color: sub, textAlign: "right" }}>
                생성 {String(syn.generated_at || "").slice(0, 16).replace("T", " ")} · 매수/매도 지시 아님
            </div>
        </div>
    )
}

addPropertyControls(TriSynthesisPanel, {})

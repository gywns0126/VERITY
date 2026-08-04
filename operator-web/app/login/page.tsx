"use client"
// /login — 로그인 전용 페이지 (PM 결함 #6: 메인과 로그인 동거 금지). 구글 온리 +
// 비상 세션복구(접힘). 인증되면 즉시 / 로. 메인(/)은 미인증 시 여기로 리다이렉트.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT } from "@/lib/theme"
import { isAuthed } from "@/lib/auth"
import { captureOAuthHash, googleAuthUrl, importSessionJson } from "@/lib/supabase"

export default function Login() {
    const dark = useDark()
    const c = palette(dark)
    const [ready, setReady] = useState(false)
    const [paste, setPaste] = useState("")
    const [showPaste, setShowPaste] = useState(false)
    const [err, setErr] = useState("")

    useEffect(() => {
        captureOAuthHash()
        if (isAuthed()) {
            window.location.replace("/")
            return
        }
        setReady(true)
    }, [])

    function google() {
        window.location.href = googleAuthUrl(window.location.origin + "/login")
    }

    function doImport() {
        setErr("")
        try {
            importSessionJson(paste)
            window.location.replace("/")
        } catch (e) {
            setErr("세션 JSON 해석 실패: " + String((e as Error).message || e))
        }
    }

    return (
        <main style={{ minHeight: "100vh", background: c.bg, fontFamily: FONT, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
            {ready ? (
                <div style={{ ...cardStyle(c, "26px 26px 22px"), width: "100%", maxWidth: 400, display: "flex", flexDirection: "column", gap: 14 }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ display: "flex", alignItems: "center", gap: 9 }}>
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src="/alphanest-logo.svg" alt="" width={26} height={26} style={{ display: "block" }} />
                            <span style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.02em", color: c.ink }}>알파네스트</span>
                        </span>
                        <span style={{ fontSize: 12, color: c.sub }}>오퍼레이터 터미널 · 비공개 · 본인 전용</span>
                    </div>

                    <button
                        onClick={google}
                        style={{ border: "none", borderRadius: 12, padding: "13px 0", fontSize: 14.5, fontWeight: 800, fontFamily: FONT, cursor: "pointer", background: c.vt, color: "#fff" }}
                    >
                        Google로 로그인
                    </button>

                    <div style={{ fontSize: 11, color: c.faint, lineHeight: 1.55 }}>
                        로그인하면 계좌 HUD·보유·추천·호가·주문·3종 LLM 종합이 열립니다. 세션은 이 브라우저에만 저장됩니다.
                    </div>

                    <button onClick={() => setShowPaste((v) => !v)} style={{ border: "none", background: "transparent", color: c.faint, fontSize: 10.5, cursor: "pointer", fontFamily: FONT, textAlign: "left", padding: 0 }}>
                        {showPaste ? "접기" : "세션 복구 (비상용)"}
                    </button>
                    {showPaste ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            <div style={{ fontSize: 11, color: c.sub, lineHeight: 1.5 }}>
                                구글 복귀가 안 될 때만: 알파네스트 탭 콘솔(F12)의 <span style={{ color: c.ink }}>localStorage.getItem(&#39;verity_supabase_session&#39;)</span> 값을 붙여넣으세요.
                            </div>
                            <textarea
                                value={paste}
                                onChange={(e) => setPaste(e.target.value)}
                                rows={3}
                                placeholder='{"access_token":"..."}'
                                style={{ background: dark ? c.bg : c.track, color: c.ink, border: "none", borderRadius: 10, padding: "10px 13px", fontSize: 11.5, fontFamily: FONT, outline: "none", resize: "vertical" }}
                            />
                            <button onClick={doImport} disabled={!paste.trim()} style={{ border: "none", borderRadius: 10, padding: "9px 0", fontSize: 12.5, fontWeight: 700, fontFamily: FONT, cursor: paste.trim() ? "pointer" : "default", background: paste.trim() ? c.hi : c.track, color: paste.trim() ? c.ink : c.faint }}>
                                세션 적용
                            </button>
                        </div>
                    ) : null}
                    {err ? <div style={{ fontSize: 11.5, color: c.up, lineHeight: 1.4 }}>{err}</div> : null}
                </div>
            ) : null}
        </main>
    )
}

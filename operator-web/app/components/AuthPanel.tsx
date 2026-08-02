"use client"
// AuthPanel — 오퍼레이터 로그인. PM 지시(2026-08-03): 구글 로그인 온리.
// OAuth 복귀 해시 캡처(captureOAuthHash) → 동일 세션키/shape 저장 = 기존 authed fetch 무변경 호환.
// "세션 복구"(붙여넣기) = 로그인 수단 아님 — OAuth redirect 허용목록 미설정 등 비상시 복구 전용(접힘).
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT } from "@/lib/theme"
import { isAuthed } from "@/lib/auth"
import { captureOAuthHash, clearSession, googleAuthUrl, importSessionJson, loadSession, refreshIfNeeded } from "@/lib/supabase"

export default function AuthPanel() {
    const dark = useDark()
    const c = palette(dark)
    const [authed, setAuthed] = useState(false)
    const [who, setWho] = useState("")
    const [paste, setPaste] = useState("")
    const [showPaste, setShowPaste] = useState(false)
    const [err, setErr] = useState("")

    useEffect(() => {
        if (captureOAuthHash()) {
            window.location.replace(window.location.pathname)
            return
        }
        setAuthed(isAuthed())
        setWho(loadSession()?.user_email || "")
        const t = setInterval(() => {
            refreshIfNeeded().then((did) => {
                if (did) setAuthed(isAuthed())
            })
        }, 60_000)
        refreshIfNeeded()
        return () => clearInterval(t)
    }, [])

    function google() {
        window.location.href = googleAuthUrl(window.location.origin + window.location.pathname)
    }

    function doImport() {
        setErr("")
        try {
            importSessionJson(paste)
            window.location.reload()
        } catch (e) {
            setErr("세션 JSON 해석 실패: " + String((e as Error).message || e))
        }
    }

    function logout() {
        clearSession()
        window.location.reload()
    }

    if (authed) {
        return (
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: FONT, marginBottom: 18 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: c.green, boxShadow: `0 0 0 3px ${c.greenS}` }} />
                <span style={{ fontSize: 12, color: c.sub }}>오퍼레이터 인증됨{who ? ` · ${who}` : ""}</span>
                <button onClick={logout} style={{ border: "none", background: c.hi, color: c.sub, borderRadius: 999, padding: "5px 11px", fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: FONT }}>
                    로그아웃
                </button>
            </div>
        )
    }

    return (
        <div style={{ ...cardStyle(c), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 10, marginBottom: 18, maxWidth: 460 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: c.ink }}>오퍼레이터 로그인</span>
                <span style={{ fontSize: 10.5, color: c.faint }}>비공개 · 본인 전용</span>
            </div>
            <button
                onClick={google}
                style={{ border: "none", borderRadius: 10, padding: "12px 0", fontSize: 14, fontWeight: 800, fontFamily: FONT, cursor: "pointer", background: c.vt, color: "#fff" }}
            >
                Google로 로그인
            </button>
            <div style={{ fontSize: 10.5, color: c.faint, lineHeight: 1.5 }}>
                로그인하면 추천·3종 LLM 종합·검증·중용 목표비중 패널이 열립니다. 세션은 이 브라우저에만 저장됩니다.
            </div>

            <button onClick={() => setShowPaste((v) => !v)} style={{ border: "none", background: "transparent", color: c.faint, fontSize: 10.5, cursor: "pointer", fontFamily: FONT, textAlign: "left", padding: 0 }}>
                {showPaste ? "접기" : "세션 복구 (비상용)"}
            </button>
            {showPaste ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{ fontSize: 11, color: c.sub, lineHeight: 1.5 }}>
                        구글 복귀가 안 될 때만: 알파네스트 탭 콘솔(F12)의 <span style={{ color: c.ink }}>localStorage.getItem(&#39;verity_supabase_session&#39;)</span> 값을 붙여넣으세요.
                    </div>
                    <textarea value={paste} onChange={(e) => setPaste(e.target.value)} rows={3} placeholder='{"access_token":"..."}' style={{ background: dark ? c.bg : c.track, color: c.ink, border: "none", borderRadius: 10, padding: "10px 13px", fontSize: 11.5, fontFamily: FONT, outline: "none", resize: "vertical" }} />
                    <button onClick={doImport} disabled={!paste.trim()} style={{ border: "none", borderRadius: 10, padding: "9px 0", fontSize: 12.5, fontWeight: 700, fontFamily: FONT, cursor: paste.trim() ? "pointer" : "default", background: paste.trim() ? c.hi : c.track, color: paste.trim() ? c.ink : c.faint }}>
                        세션 적용
                    </button>
                </div>
            ) : null}
            {err ? <div style={{ fontSize: 11.5, color: c.up, lineHeight: 1.4 }}>{err}</div> : null}
        </div>
    )
}

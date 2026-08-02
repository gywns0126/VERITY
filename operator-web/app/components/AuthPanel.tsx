"use client"
// AuthPanel — 오퍼레이터 로그인 (새 오리진 세션, 태스크 #13). 공개 알파네스트 디자인·외곽선 0.
// 성공 시 reload → 전 authed 패널 재fetch. 세션키/shape = 공개사이트와 동일(기존 fetch 무변경 호환).
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT } from "@/lib/theme"
import { isAuthed } from "@/lib/auth"
import { clearSession, importSessionJson, loadSession, refreshIfNeeded, signInPassword } from "@/lib/supabase"

export default function AuthPanel() {
    const dark = useDark()
    const c = palette(dark)
    const [authed, setAuthed] = useState(false)
    const [email, setEmail] = useState("")
    const [pw, setPw] = useState("")
    const [paste, setPaste] = useState("")
    const [showPaste, setShowPaste] = useState(false)
    const [busy, setBusy] = useState(false)
    const [err, setErr] = useState("")
    const [who, setWho] = useState("")

    useEffect(() => {
        setAuthed(isAuthed())
        setWho(loadSession()?.user_email || "")
        // 세션 키퍼 — 만료 5분 전 자동 갱신(60초 주기, 다중 탭 락)
        const t = setInterval(() => {
            refreshIfNeeded().then((did) => {
                if (did) setAuthed(isAuthed())
            })
        }, 60_000)
        refreshIfNeeded()
        return () => clearInterval(t)
    }, [])

    async function login() {
        if (!email.trim() || !pw || busy) return
        setBusy(true)
        setErr("")
        try {
            await signInPassword(email.trim(), pw)
            window.location.reload()
        } catch (e) {
            setErr(String((e as Error).message || e))
            setBusy(false)
        }
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

    const inputStyle = {
        background: dark ? c.bg : c.track, color: c.ink, border: "none", borderRadius: 10,
        padding: "10px 13px", fontSize: 13.5, fontFamily: FONT, outline: "none",
    } as const

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
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="이메일" type="email" autoComplete="username" style={inputStyle} />
            <input value={pw} onChange={(e) => setPw(e.target.value)} placeholder="비밀번호" type="password" autoComplete="current-password" onKeyDown={(e) => { if (e.key === "Enter") login() }} style={inputStyle} />
            <button onClick={login} disabled={busy || !email.trim() || !pw} style={{ border: "none", borderRadius: 10, padding: "11px 0", fontSize: 13.5, fontWeight: 800, fontFamily: FONT, cursor: busy || !email.trim() || !pw ? "default" : "pointer", background: busy || !email.trim() || !pw ? c.hi : c.vt, color: busy || !email.trim() || !pw ? c.faint : "#fff" }}>
                {busy ? "확인 중" : "로그인"}
            </button>
            {err ? <div style={{ fontSize: 11.5, color: c.up, lineHeight: 1.4 }}>{err}</div> : null}

            <button onClick={() => setShowPaste((v) => !v)} style={{ border: "none", background: "transparent", color: c.faint, fontSize: 11, cursor: "pointer", fontFamily: FONT, textAlign: "left", padding: 0 }}>
                {showPaste ? "접기" : "구글 계정이면: 세션 JSON 붙여넣기"}
            </button>
            {showPaste ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <div style={{ fontSize: 11, color: c.sub, lineHeight: 1.5 }}>
                        알파네스트 탭 콘솔(F12)에서 <span style={{ color: c.ink }}>localStorage.getItem(&#39;verity_supabase_session&#39;)</span> 결과를 붙여넣으세요.
                        주의: 세션 공유 방식이라 이후 알파네스트 탭이 로그아웃될 수 있습니다(비밀번호 로그인은 무충돌).
                    </div>
                    <textarea value={paste} onChange={(e) => setPaste(e.target.value)} rows={3} placeholder='{"access_token":"...","refresh_token":"...","expires_at":...}' style={{ ...inputStyle, resize: "vertical", fontSize: 11.5 }} />
                    <button onClick={doImport} disabled={!paste.trim()} style={{ border: "none", borderRadius: 10, padding: "9px 0", fontSize: 12.5, fontWeight: 700, fontFamily: FONT, cursor: paste.trim() ? "pointer" : "default", background: paste.trim() ? c.hi : c.track, color: paste.trim() ? c.ink : c.faint }}>
                        세션 적용
                    </button>
                </div>
            ) : null}
            <div style={{ fontSize: 10.5, color: c.faint, lineHeight: 1.5 }}>
                로그인하면 추천·3종 LLM 종합·검증·중용 목표비중 패널이 열립니다. 세션은 이 브라우저에만 저장됩니다.
            </div>
        </div>
    )
}

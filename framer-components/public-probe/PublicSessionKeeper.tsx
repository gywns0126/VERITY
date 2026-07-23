import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, type CSSProperties } from "react"

/**
 * 세션 키퍼 — AlphaNest 공개 터미널 전역 토큰 유지 (2026-07-14).
 *
 * 문제: Supabase access_token 은 ~1시간 만료. refresh 로직(AlphaNestAuth 60초 인터벌)은 /login 페이지에만 있어,
 *   홈(/)·둥지(/nest) 등 공개 페이지에 오래 머물거나 재방문하면 토큰이 만료된 채 방치됨 →
 *   /api/holdings·/api/trades 가 401 → 보유종목·거래기록·모닝브리핑이 빈 값/데모로 표시되는 사고.
 *
 * 해결: 이 컴포넌트를 각 공개 페이지(또는 Nav)에 1개 배치. 만료 임박/만료 시 refresh_token 으로 재발급하고
 *   localStorage(verity_supabase_session) 갱신 + verity_auth_change dispatch → 기존 소비자(HoldingsTab·
 *   MorningBriefing·NPS·StockReport 등)가 새 토큰으로 자동 재fetch. UI 없음(캔버스만 배치용 라벨).
 *
 * 🚨 표준 refresh 만 — 새 로그인/토큰 발급 경로 신설 아님(기존 refresh_token 을 grant_type=refresh_token 으로 교환).
 * 🚨 이중 refresh 방지(refresh_token 회전 충돌 = 강제 로그아웃 위험):
 *   · /login 에선 skip (AlphaNestAuth 가 담당) · localStorage 락(20s) 로 다중 인스턴스/탭 동시 refresh 차단
 *   · in-flight 플래그(모듈 스코프) · 만료 5분 전에만 트리거(불필요 재발급 0)
 * 세션 shape·엔드포인트·이벤트명 = AlphaNestAuth(PublicAuth.tsx) 와 동일.
 */

const SESSION_KEY = "verity_supabase_session"
const AUTH_EVENT = "verity_auth_change"
const LOCK_KEY = "verity_token_refresh_lock"
const LOCK_MS = 20000 // 다중 인스턴스/탭 동시 refresh 디바운스 (Supabase refresh_token 회전 grace 내)
const REFRESH_MARGIN = 300 // 만료 5분 전부터 refresh (AlphaNestAuth 동일 임계)

const DEFAULT_SUPABASE_URL = "https://lykqebdcurreppowulsl.supabase.co"
// 공개 anon key(브라우저 노출 안전). /login AlphaNestAuth 인스턴스 prop 과 동일 값.
const DEFAULT_SUPABASE_ANON_KEY =
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx5a3FlYmRjdXJyZXBwb3d1bHNsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUwMTcyMTUsImV4cCI6MjA5MDU5MzIxNX0.JhwsWgsrdDJ12BzZZjR7o6jdS-Mxny2eSJeWq59DhNs"

interface Session {
    access_token: string
    refresh_token: string
    expires_at: number
    user?: any
}

// 모듈 스코프 in-flight 가드 — 같은 인스턴스의 동시 refresh 차단.
let refreshing = false

function loadRaw(): Session | null {
    if (typeof window === "undefined") return null
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return null
        const s = JSON.parse(raw)
        return s && typeof s.access_token === "string" ? s : null
    } catch {
        return null
    }
}
function lockActive(): boolean {
    try {
        const t = Number(localStorage.getItem(LOCK_KEY) || 0)
        return isFinite(t) && Date.now() - t < LOCK_MS
    } catch {
        return false
    }
}
function stampLock() {
    try {
        localStorage.setItem(LOCK_KEY, String(Date.now()))
    } catch {
        /* ignore */
    }
}

/** 만료 임박/만료 시 refresh_token 으로 재발급. 성공 + 토큰 변경 시에만 verity_auth_change dispatch. */
async function refreshIfNeeded(url: string, anonKey: string): Promise<void> {
    if (refreshing) return
    const s = loadRaw()
    if (!s || !s.refresh_token) return
    const now = Date.now() / 1000
    if (s.expires_at && now < s.expires_at - REFRESH_MARGIN) return // 아직 신선 → skip
    if (lockActive()) return // 다른 키퍼/탭이 방금 refresh → skip

    refreshing = true
    stampLock()
    try {
        const res = await fetch(
            `${url}/auth/v1/token?grant_type=refresh_token`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    apikey: anonKey,
                    Authorization: `Bearer ${anonKey}`,
                },
                body: JSON.stringify({ refresh_token: s.refresh_token }),
            }
        )
        if (!res.ok) return // 400=refresh_token 만료(진짜 로그아웃)/네트워크 등 → 세션 보존, getToken 이 만료 인지로 CTA 처리
        const body = await res.json().catch(() => null)
        if (!body || !body.access_token) return
        const ns: Session = {
            access_token: body.access_token,
            refresh_token: body.refresh_token || s.refresh_token,
            expires_at: body.expires_at || Date.now() / 1000 + 3600,
            user: body.user || s.user,
        }
        const prev = s.access_token
        try {
            localStorage.setItem(SESSION_KEY, JSON.stringify(ns))
        } catch {
            /* ignore */
        }
        stampLock()
        if (ns.access_token !== prev && typeof window !== "undefined") {
            window.dispatchEvent(new CustomEvent(AUTH_EVENT))
        }
    } catch {
        /* 네트워크 실패 = 세션 보존, 다음 틱 재시도 */
    } finally {
        refreshing = false
    }
}

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    loginPath: string
    intervalSec: number
}

/**
 * @framerSupportedLayoutWidth auto
 * @framerSupportedLayoutHeight auto
 */
export default function PublicSessionKeeper(props: Props) {
    const { supabaseUrl, supabaseAnonKey, loginPath, intervalSec } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const url = (supabaseUrl || DEFAULT_SUPABASE_URL).replace(/\/+$/, "")
    const anonKey = supabaseAnonKey || DEFAULT_SUPABASE_ANON_KEY
    const every = Math.max(15, Number(intervalSec) || 60) * 1000

    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        // /login 에선 AlphaNestAuth 가 refresh 담당 → 이중 refresh 회피.
        const onLogin = () => {
            const p = (loginPath || "/login").replace(/\/+$/, "")
            const cur = window.location.pathname.replace(/\/+$/, "")
            return p && cur === p
        }
        const tick = () => {
            if (onLogin()) return
            refreshIfNeeded(url, anonKey)
        }
        tick() // 마운트 즉시 1회 (만료 임박 페이지 로드 시 바로 갱신 → 소비자 재fetch)
        const id = setInterval(tick, every)
        // 탭 복귀 시 즉시 점검(숨겨진 동안 만료됐을 수 있음).
        const onVis = () => {
            if (document.visibilityState === "visible") tick()
        }
        document.addEventListener("visibilitychange", onVis)
        return () => {
            clearInterval(id)
            document.removeEventListener("visibilitychange", onVis)
        }
    }, [url, anonKey, loginPath, every, onCanvas])

    // 라이브 = UI 없음. 캔버스 = 배치용 라벨(선택/식별).
    if (!onCanvas) return <span aria-hidden style={{ display: "none" }} />
    const chip: CSSProperties = {
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "5px 10px",
        borderRadius: 8,
        background: "#f0edff",
        color: "#6c5ce7",
        fontFamily: "Pretendard, -apple-system, sans-serif",
        fontSize: 11,
        fontWeight: 700,
        whiteSpace: "nowrap",
    }
    return <div style={chip}>🔑 세션 키퍼 · 실사이트 비표시</div>
}

addPropertyControls(PublicSessionKeeper, {
    supabaseUrl: {
        type: ControlType.String,
        title: "Supabase URL",
        defaultValue: DEFAULT_SUPABASE_URL,
    },
    supabaseAnonKey: {
        type: ControlType.String,
        title: "Supabase Anon Key",
        defaultValue: DEFAULT_SUPABASE_ANON_KEY,
    },
    loginPath: {
        type: ControlType.String,
        title: "Login Path (skip)",
        defaultValue: "/login",
    },
    intervalSec: {
        type: ControlType.Number,
        title: "점검 주기(초)",
        defaultValue: 60,
        min: 15,
        max: 600,
        step: 5,
    },
})

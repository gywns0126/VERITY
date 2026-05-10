import { addPropertyControls, ControlType } from "framer"
import React, { useEffect } from "react"

/*
 * VERITY ESTATE — OAuth Hash Catcher
 *
 * Google OAuth 콜백 시 Supabase 가 #access_token=... 을 *Supabase Site URL* 로
 * 리다이렉트한다. estate 의 Site URL 이 `/home` 이면 EstateAuthPage 가 mount 안 된
 * 페이지(/home) 에 hash 가 떨어지고, hash 파싱 누락 → localStorage 미저장 →
 * watchlist "로그인 필요" 영구 결함.
 *
 * 본 컴포넌트는 invisible 한 처리기:
 *   - URL hash 에 access_token 발견 시 즉시 파싱
 *   - Supabase /auth/v1/user 로 user 정보 보강
 *   - profiles.status 체크 (approved 만 저장)
 *   - localStorage 에 verity_supabase_session 저장
 *   - hash 를 URL 에서 제거 (history.replaceState)
 *   - storage event dispatch → 다른 컴포넌트의 polling 없이 즉시 감지
 *
 * 배치: OAuth 콜백이 떨어지는 페이지(/home 등) 에 한 번씩 드롭. 화면에 안 보임.
 */

const SESSION_KEY = "verity_supabase_session"

interface SupaSession {
    access_token: string
    refresh_token: string
    expires_at: number
    user: { id: string; email: string; user_metadata?: any }
}

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
}

export default function OAuthHashCatcher({ supabaseUrl, supabaseAnonKey }: Props) {
    useEffect(() => {
        if (typeof window === "undefined") return
        const hash = window.location.hash || ""
        if (!hash.includes("access_token=")) return

        const params = new URLSearchParams(hash.replace(/^#/, ""))
        const at = params.get("access_token")
        const rt = params.get("refresh_token") || ""
        const expRaw = params.get("expires_at") || params.get("expires_in")
        if (!at) return

        const expires_at = Number(expRaw) > 1e9
            ? Number(expRaw)
            : Date.now() / 1000 + Number(expRaw || 3600)

        const oauthSession: SupaSession = {
            access_token: at,
            refresh_token: rt,
            expires_at,
            user: { id: "", email: "" },
        }

        // hash 즉시 제거 (token 이 URL 에 노출되지 않도록)
        const cleanUrl = window.location.pathname + window.location.search
        window.history.replaceState(null, "", cleanUrl)

        if (!supabaseUrl || !supabaseAnonKey) return

        ;(async () => {
            try {
                const ures = await fetch(`${supabaseUrl}/auth/v1/user`, {
                    headers: { apikey: supabaseAnonKey, Authorization: `Bearer ${at}` },
                })
                if (!ures.ok) return
                const u = await ures.json()
                oauthSession.user = u

                const pres = await fetch(
                    `${supabaseUrl}/rest/v1/profiles?id=eq.${u.id}&select=status`,
                    {
                        headers: {
                            apikey: supabaseAnonKey,
                            Authorization: `Bearer ${at}`,
                            Accept: "application/json",
                        },
                    }
                )
                const rows = pres.ok ? await pres.json().catch(() => []) : []
                const status = Array.isArray(rows) && rows[0]?.status

                if (status === "approved") {
                    localStorage.setItem(SESSION_KEY, JSON.stringify(oauthSession))
                    // 같은 탭의 다른 컴포넌트(WatchComplexesDashboard 등) 의 token 갱신을
                    // polling 대기 없이 즉시 발화. storage event 는 보통 *다른* 탭에서만
                    // 자동 발생 → 같은 탭 즉시성을 위해 수동 dispatch.
                    window.dispatchEvent(new StorageEvent("storage", { key: SESSION_KEY }))
                }
                // approved 아니면 저장 안 함 — EstateAuthPage 의 OAuth 거부 분기 정합
            } catch {
                /* swallow — token 은 hash 제거됨, 다음 로그인 시도 가능 */
            }
        })()
    }, [supabaseUrl, supabaseAnonKey])

    return null
}

OAuthHashCatcher.defaultProps = {
    supabaseUrl: "",
    supabaseAnonKey: "",
}

addPropertyControls(OAuthHashCatcher, {
    supabaseUrl: {
        type: ControlType.String,
        title: "Supabase URL",
        defaultValue: "",
        description: "https://xxxxx.supabase.co",
    },
    supabaseAnonKey: {
        type: ControlType.String,
        title: "Supabase Anon Key",
        defaultValue: "",
        description: "Supabase → Settings → API → anon key",
    },
})

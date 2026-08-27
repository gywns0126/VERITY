"use client"

import { useEffect, useState } from "react"

const DEFAULT_INTERVAL_MS = 5 * 60_000

/**
 * 장시간 열어 두는 오퍼레이터 화면의 스냅샷 재조회 신호.
 * 주기 갱신 외에도 탭 복귀·네트워크 복구 시 즉시 새 데이터를 요청한다.
 */
export function useDataRefreshEpoch(intervalMs = DEFAULT_INTERVAL_MS): number {
    const [epoch, setEpoch] = useState(0)

    useEffect(() => {
        const refresh = () => setEpoch((v) => v + 1)
        const onVisible = () => {
            if (document.visibilityState === "visible") refresh()
        }
        const timer = window.setInterval(refresh, intervalMs)
        document.addEventListener("visibilitychange", onVisible)
        window.addEventListener("online", refresh)
        return () => {
            window.clearInterval(timer)
            document.removeEventListener("visibilitychange", onVisible)
            window.removeEventListener("online", refresh)
        }
    }, [intervalMs])

    return epoch
}

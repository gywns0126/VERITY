"use client"
// 실시간 시세 단일 폴러 (모듈 싱글턴) — Railway /quotes 는 per-IP 30req/60s 제한.
// 컴포넌트별 개별 폴링 = 즉시 429 → 구독 refcount 로 한 폴러(3s)만 가동 (20req/분 < 30 안전).
// KR 6자리만 (fetch_price = 국내 · US 는 전일종가 체계, project_chart_source_split).
import { useEffect, useState } from "react"
import { fetchRailway } from "./api"

export type Quote = {
    price?: number
    prev_close?: number
    change?: number
    change_pct?: number
    volume?: number
    open?: number
    high?: number
    low?: number
}

const POLL_MS = 3000
const MAX_CODES = 30

const refs = new Map<string, number>()
let quotes: Record<string, Quote> = {}
let lastAsof = ""
const listeners = new Set<() => void>()
let timer: ReturnType<typeof setInterval> | null = null
let inflight = false

function activeCodes(): string[] {
    const out: string[] = []
    refs.forEach((n, t) => {
        if (n > 0 && /^\d{6}$/.test(t)) out.push(t)
    })
    return out.slice(0, MAX_CODES)
}

async function poll(): Promise<void> {
    const codes = activeCodes()
    if (!codes.length || inflight) return
    inflight = true
    try {
        const r = await fetchRailway<{ quotes?: Record<string, Quote>; asof?: string }>(
            `quotes?tickers=${codes.join(",")}`
        )
        if (r.ok && r.data.quotes) {
            quotes = { ...quotes, ...r.data.quotes }
            lastAsof = String(r.data.asof || "")
            listeners.forEach((f) => {
                try {
                    f()
                } catch {}
            })
        }
    } finally {
        inflight = false
    }
}

function ensureTimer(): void {
    if (!timer && typeof window !== "undefined") {
        timer = setInterval(poll, POLL_MS)
    }
}

/** 구독 훅 — tickers 의 시세 맵 + asof(HH:MM:SS). 폴러는 전 컴포넌트 공유 1개. */
export function useQuotes(tickers: string[]): { q: Record<string, Quote>; asof: string } {
    const [, force] = useState(0)
    const key = tickers
        .filter(Boolean)
        .slice()
        .sort()
        .join(",")

    useEffect(() => {
        const mine = key ? key.split(",") : []
        mine.forEach((t) => refs.set(t, (refs.get(t) || 0) + 1))
        const l = () => force((x) => x + 1)
        listeners.add(l)
        ensureTimer()
        poll()
        return () => {
            listeners.delete(l)
            mine.forEach((t) => {
                const n = (refs.get(t) || 1) - 1
                if (n <= 0) refs.delete(t)
                else refs.set(t, n)
            })
        }
    }, [key])

    return { q: quotes, asof: lastAsof ? lastAsof.slice(11, 19) : "" }
}

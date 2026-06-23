import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * 종목 검색창 (독립) — VERITY 공개 터미널. Framer 네이티브 nav 안에 끼워 쓰는 검색 전용.
 * Enter → 입력 텍스트를 유니버스에서 *종목코드*로 정규화 → /stock?q=<코드> 이동.
 *   (정규화 이유: 결정 페이지 컴포넌트는 ticker 정확매칭만 함. 종목명 ?q 는 빈 화면이 됨.)
 *   코드/이름 매칭 실패 시에만 raw 텍스트 fallback(리포트가 자체 이름매칭 시도).
 * 종목 공유 = ?q + localStorage `verity_last_ticker` 동시 기록(토글 시 종목 유지, PublicTickerSync 와 동일 키).
 * nav 자체는 Framer 네이티브로 (SPA 페이지 링크). 이 컴포넌트는 검색 UI 만.
 * 테마: Framer 네이티브 추종 — body[data-framer-theme] 읽어 dark 전환(캔버스는 dark prop 정적 프리뷰).
 */

const LIGHT = { ink: "#191f28", faint: "#8b95a1", vg: "#0ca678", field: "#f2f4f6", card: "#ffffff" }
const DARK = { ink: "#e3e7ec", faint: "#828d9b", vg: "#7fffa0", field: "#0f1318", card: "#171c23" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEF_STOCK = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
const LAST_TK_KEY = "verity_last_ticker"

interface Props {
    placeholder: string
    stockPath: string
    stockUrl: string
    usStockUrl: string
    dark: boolean
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicStockSearch(props: Props) {
    const { placeholder, stockPath, stockUrl, usStockUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 dark prop 정적) */
    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    useEffect(() => {
        if (onCanvas) return
        const read = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [q, setQ] = useState("")
    const [universe, setUniverse] = useState<any[]>([])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    /* 유니버스 로드 — KR + US 동시(국장·미장 통합 검색). 2026-06-23. */
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const urls = [stockUrl, usStockUrl].filter(Boolean)
        Promise.all(urls.map((u) => fetch(u, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null)))
            .then((docs) => {
                if (!alive) return
                const merged: any[] = []
                for (const d of docs) { const a = d && (Array.isArray(d) ? d : d.stocks); if (Array.isArray(a)) merged.push(...a) }
                if (merged.length) setUniverse(merged)
            })
        return () => { alive = false }
    }, [stockUrl, usStockUrl, onCanvas])

    /* 입력 → 종목코드. 코드/이름 정확 → 부분일치 → (실패 시) raw 텍스트. */
    const resolveTicker = (text: string): string => {
        const s = text.trim()
        if (!s || !universe.length) return s
        const lower = s.toLowerCase()
        let hit = universe.find((x) => String(x.ticker).toLowerCase() === lower || String(x.name || "").toLowerCase() === lower || String((x as any).name_ko || "") === s)
        if (!hit) hit = universe.find((x) => String(x.ticker).toLowerCase().includes(lower) || String(x.name || "").toLowerCase().includes(lower) || String((x as any).name_ko || "").includes(s))
        return hit ? String(hit.ticker) : s
    }

    const go = () => {
        const raw = q.trim()
        if (!raw || typeof window === "undefined") return
        const tk = resolveTicker(raw)
        try { window.localStorage.setItem(LAST_TK_KEY, tk) } catch { /* private/quota */ }
        const p = (stockPath || "/stock").replace(/\/+$/, "")
        window.location.href = p + "?q=" + encodeURIComponent(tk)
    }

    const narrow = w > 0 && w < 200

    const wrap: CSSProperties = {
        width: "100%", height: "100%", boxSizing: "border-box",
        display: "flex", alignItems: "center", gap: 7,
        background: C.field, borderRadius: 999,
        padding: narrow ? "8px 12px" : "9px 14px",
        fontFamily: FONT,
    }

    return (
        <div ref={rootRef} style={wrap}>
            <span style={{ width: 14, height: 14, borderRadius: "50%", border: `2px solid ${C.faint}`, flexShrink: 0, display: "inline-block", position: "relative" }}>
                <span style={{ position: "absolute", width: 2, height: 6, background: C.faint, right: -3, bottom: -3, transform: "rotate(-45deg)" }} />
            </span>
            <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") go() }}
                placeholder={placeholder || "종목 검색"}
                style={{
                    border: "none", outline: "none", background: "transparent", color: C.ink,
                    fontFamily: FONT, fontSize: narrow ? 13 : 14, fontWeight: 600, width: "100%", minWidth: 0,
                }}
            />
        </div>
    )
}

addPropertyControls(PublicStockSearch, {
    placeholder: { type: ControlType.String, title: "Placeholder", defaultValue: "종목 검색 (이름·코드)" },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: DEF_STOCK },
    usStockUrl: { type: ControlType.String, title: "US Stock URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

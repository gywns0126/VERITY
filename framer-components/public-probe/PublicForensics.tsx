import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * AlphaNest 공개 — 종목 forensics (특수관계자 거래·우발부채·소송·제재). DART 사업보고서 원문 사실.
 * 🚨 RULE 7 — 위험점수·심각도·해석 0. 사실 리스트만. 데이터 = kr_forensics_public.json (Blob).
 * 다크모드 = body[data-framer-theme] 자가감지. 외곽선 없음(소프트 카드).
 * Framer codeFileId = csSSpxV (insertUrl framer.com/m/PublicForensics-6xe2uh.js).
 */

const LIGHT = { card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", vt: "#6c5ce7" }
const DARK = { card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", vt: "#a99bff" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/kr_forensics_public.json"

const SECTIONS: { key: string; label: string }[] = [
    { key: "related_party_transactions", label: "특수관계자 거래" },
    { key: "contingent_liabilities", label: "우발부채·보증" },
    { key: "pending_litigation", label: "진행 중 소송" },
    { key: "material_sanctions", label: "제재" },
]

const SAMPLE: any = {
    related_party_transactions: ["상대방: 계열사 등 / 유형: 제품매출 / 규모: 1,505억원 (영업수익의 약 75%)"],
    contingent_liabilities: ["금융기관 지급보증 USD 137백만 · KRW 419억 등 우발부채"],
    pending_litigation: ["청구액 약 JPY 63백만 · 피고로 계류 중인 소송사건"],
    year: "2025",
    source_note: "DART 사업보고서 원문 사실 · 자체 위험판단 아님",
}

function readDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

export default function PublicForensics(props: { ticker?: string; dataUrl?: string; dark?: boolean }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas || !props.ticker) return
        let alive = true
        fetch(props.dataUrl || DEFAULT_URL, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive) setData(d && d.stocks ? d.stocks[String(props.ticker)] || null : null) })
            .catch(() => { if (alive) setData(null) })
        return () => { alive = false }
    }, [props.ticker, props.dataUrl, onCanvas])

    if (!data) return null
    const hasAny = SECTIONS.some((s) => Array.isArray(data[s.key]) && data[s.key].length)
    if (!hasAny) return null

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", fontFamily: FONT, color: C.ink, display: "flex", flexDirection: "column", gap: 12 }
    return (
        <div style={wrap}>
            <div style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.3px", display: "flex", alignItems: "baseline", gap: 8 }}>
                공시 forensics · 사실
                {data.year ? <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{data.year}</span> : null}
            </div>
            {SECTIONS.map((s) => {
                const items = Array.isArray(data[s.key]) ? data[s.key] : []
                if (!items.length) return null
                return (
                    <div key={s.key} style={{ background: C.card, borderRadius: 14, padding: "13px 15px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ fontSize: 12.5, fontWeight: 800, color: C.vt, marginBottom: 8 }}>
                            {s.label}<span style={{ color: C.faint, marginLeft: 6, fontWeight: 600 }}>{items.length}</span>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            {items.map((it: string, i: number) => (
                                <div key={i} style={{ fontSize: 12, color: C.sub, fontWeight: 500, lineHeight: 1.55, paddingLeft: 11, position: "relative" }}>
                                    <span style={{ position: "absolute", left: 0, color: C.vt }}>·</span>{String(it)}
                                </div>
                            ))}
                        </div>
                    </div>
                )
            })}
            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>
                {data.source_note || "DART 사업보고서 원문 사실 · 자체 위험판단 아님"}
            </div>
        </div>
    )
}

addPropertyControls(PublicForensics, {
    ticker: { type: ControlType.String, title: "종목코드", defaultValue: "" },
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})

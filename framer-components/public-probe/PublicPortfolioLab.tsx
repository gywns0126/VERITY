import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState } from "react"
import { CaretDown, Check, FloppyDisk, LockKey, MagnifyingGlass, Plus, Sparkle, Trash } from "@phosphor-icons/react"

/**
 * 포트폴리오 실험실 — 초보자가 질문을 따라가며 투자 개념을 배우는 독립 페이지.
 * 기본 화면은 무엇을·얼마나·언제부터만 묻고 전문 설정은 접어 둔다.
 * 검증된 가격·배당·세금 엔진 연결 전까지 수익률 결과를 생성하지 않는다.
 */

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const LIGHT = { bg: "#f2f4f6", card: "#fff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", field: "#f2f4f6", vg: "#6c5ce7", vgS: "#f0edff", blue: "#3182f6", blueS: "#e8f1fe", red: "#f04452", on: "#fff", shadow: "rgba(0,0,0,.05)" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", field: "#222831", vg: "#a99bff", vgS: "#241f3a", blue: "#5b9bff", blueS: "#16233a", red: "#f05b67", on: "#0f1318", shadow: "rgba(0,0,0,.24)" }
const P = "plab"
const PALETTE = "body{" + Object.keys(LIGHT).map((k) => `--an-${P}-${k}:${(LIGHT as any)[k]}`).join(";") + "}" + 'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => `--an-${P}-${k}:${(DARK as any)[k]}`).join(";") + "}"
const C: Record<string, string> = {}
for (const k of Object.keys(LIGHT)) C[k] = `var(--an-${P}-${k})`

const UNIVERSE_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
const DEFAULT_API = "https://project-yw131.vercel.app"
const LOGO_BASE = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
interface Props { title: string; dark: boolean; stockUrl: string; apiBase: string; communityPath: string }
type UniverseRow = { ticker: string; name: string; name_ko?: string; market?: string; kw?: string; type?: string; report_kind?: string; instrument_type?: string; underlying_symbol?: string; currency?: string; unit?: string }
type Asset = UniverseRow & { weight: number }
type Preset = UniverseRow & { lesson: string }
const PRESETS: Preset[] = [
    { ticker: "005930", name: "삼성전자", lesson: "한 종목을 오래 보유하면 어떤 일이 생길까요?" },
    { ticker: "069500", name: "KODEX 200", lesson: "여러 국내 대형주에 나눠 투자하는 방법이에요." },
    { ticker: "SPY", name: "S&P 500 ETF", lesson: "미국 대표 기업 전체에 나눠 투자하는 방식이에요." },
]
const field = { width: "100%", minHeight: 50, border: "none", outline: "none", borderRadius: 15, background: C.field, color: C.ink, padding: "0 15px", fontFamily: FONT, fontSize: 14, fontWeight: 700, boxSizing: "border-box" as const }
const card = { background: C.card, borderRadius: 16, padding: 18, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }

function Help({ children }: { children: any }) {
    return <div style={{ color: C.sub, fontSize: 12, lineHeight: 1.55, fontWeight: 600, marginTop: 7 }}>{children}</div>
}

function StockMark({ item, size = 34 }: { item: UniverseRow; size?: number }) {
    const [failed, setFailed] = useState(false)
    const ticker = String(item.ticker || "").trim().toUpperCase()
    const market = String(item.market || "").toUpperCase()
    const commodity = item.type === "commodity" || market === "원자재"
    const flag = /^\d{6}$/.test(ticker) || /KR|KOSPI|KOSDAQ|KONEX/.test(market) ? "kr" : "us"
    const initial = String(item.name_ko || item.name || ticker || "?").trim().charAt(0)
    const flagSize = Math.round(size * 0.46)
    return (
        <span style={{ position: "relative", width: size, height: size, flex: "0 0 auto", display: "inline-flex" }}>
            {commodity ? (
                <span style={{ width: size, height: size, borderRadius: Math.round(size * .32), background: C.vgS, color: C.vg, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * .42), fontWeight: 800 }}>◈</span>
            ) : !failed && ticker ? (
                <img src={LOGO_BASE + encodeURIComponent(ticker.replace(/-/g, ".")) + ".png"} alt="" width={size} height={size} onError={() => setFailed(true)} style={{ width: size, height: size, borderRadius: Math.round(size * .32), objectFit: "cover", display: "block", background: C.field }} />
            ) : (
                <span style={{ width: size, height: size, borderRadius: Math.round(size * .32), background: C.vgS, color: C.vg, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * .42), fontWeight: 800 }}>{initial}</span>
            )}
            {!commodity && <img src={FLAG_BASE + flag + ".svg"} alt={flag === "kr" ? "한국" : "미국"} width={flagSize} height={flagSize} style={{ position: "absolute", right: -3, bottom: -3, width: flagSize, height: flagSize, borderRadius: "50%", background: C.card, boxShadow: `0 0 0 1.5px ${C.card}, 0 1px 2px rgba(0,0,0,.18)` }} />}
        </span>
    )
}

export default function PublicPortfolioLab(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [assets, setAssets] = useState<Asset[]>([{ ...PRESETS[0], weight: 100 }])
    const [universe, setUniverse] = useState<UniverseRow[]>(onCanvas ? PRESETS : [])
    const [query, setQuery] = useState("")
    const [loading, setLoading] = useState(!onCanvas)
    const [amount, setAmount] = useState(300000)
    const [start, setStart] = useState("2020-01-02")
    const [advanced, setAdvanced] = useState(false)
    const [frequency, setFrequency] = useState("monthly")
    const [rebalance, setRebalance] = useState("yearly")
    const [dividend, setDividend] = useState(true)
    const [privacy, setPrivacy] = useState("private")
    const [message, setMessage] = useState("")
    const [sharing, setSharing] = useState(false)
    const totalWeight = useMemo(() => assets.reduce((sum, item) => sum + Number(item.weight || 0), 0), [assets])
    const matches = useMemo(() => {
        const q = query.trim().toLowerCase()
        if (!q) return []
        const rank = (x: UniverseRow) => {
            const t = String(x.ticker || "").toLowerCase(), n = String(x.name || "").toLowerCase(), k = String(x.name_ko || "").toLowerCase()
            return t === q ? 0 : n === q || k === q ? 1 : t.startsWith(q) ? 2 : n.startsWith(q) || k.startsWith(q) ? 3 : 4
        }
        return universe.filter((x) => [x.ticker, x.name, x.name_ko, x.kw].some((v) => String(v || "").toLowerCase().includes(q))).sort((a, b) => rank(a) - rank(b)).slice(0, 10)
    }, [query, universe])
    const valid = assets.length > 0 && Math.abs(totalWeight - 100) < .01 && Boolean(start && amount > 0)

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        setLoading(true)
        fetch(props.stockUrl || UNIVERSE_URL).then((r) => r.ok ? r.json() : null).then((d) => {
            const rows = Array.isArray(d) ? d : d?.stocks
            if (alive && Array.isArray(rows)) setUniverse(rows)
        }).catch(() => {}).finally(() => { if (alive) setLoading(false) })
        return () => { alive = false }
    }, [props.stockUrl, onCanvas])

    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        try {
            const saved = JSON.parse(localStorage.getItem("alphanest_portfolio_lab_draft") || "null")
            if (!saved || !Array.isArray(saved.assets) || !saved.assets.length) return
            setAssets(saved.assets)
            if (Number(saved.amount) > 0) setAmount(Number(saved.amount))
            if (saved.start) setStart(String(saved.start))
            if (saved.frequency) setFrequency(String(saved.frequency))
            if (saved.rebalance) setRebalance(String(saved.rebalance))
            if (typeof saved.dividend === "boolean") setDividend(saved.dividend)
            setPrivacy("private")
            setMessage("공유된 조건을 내 비공개 초안으로 불러왔어요")
        } catch {}
    }, [onCanvas])

    function equalize(rows: Asset[]) {
        if (!rows.length) return rows
        const base = Math.floor(10000 / rows.length) / 100
        return rows.map((row, index) => ({ ...row, weight: index === rows.length - 1 ? Math.round((100 - base * (rows.length - 1)) * 100) / 100 : base }))
    }
    function addAsset(row: UniverseRow) {
        if (assets.some((x) => x.ticker === row.ticker)) {
            setMessage("이미 선택한 종목이에요")
            return
        }
        setAssets((current) => equalize([...current, { ...row, weight: 0 }]))
        setQuery("")
        setMessage("")
    }
    function removeAsset(ticker: string) {
        setAssets((current) => equalize(current.filter((x) => x.ticker !== ticker)))
    }

    function saveDraft() {
        const draft = { assets, amount, start, frequency, rebalance, dividend, privacy, savedAt: new Date().toISOString() }
        try {
            localStorage.setItem("alphanest_portfolio_lab_draft", JSON.stringify(draft))
            setMessage("이 기기에 실험 초안을 저장했어요")
        } catch {
            setMessage("초안을 저장하지 못했어요")
        }
    }
    function shareExperiment() {
        if (!valid || privacy === "private" || sharing || onCanvas) return
        let token = ""
        try {
            const session = JSON.parse(localStorage.getItem("verity_supabase_session") || "{}")
            token = typeof session.access_token === "string" ? session.access_token : ""
        } catch {}
        if (!token) {
            setMessage("커뮤니티 공유는 로그인 후 가능해요")
            return
        }
        setSharing(true)
        const first = assets[0]?.name_ko || assets[0]?.name || "포트폴리오"
        fetch((props.apiBase || DEFAULT_API).replace(/\/+$/, "") + "/api/portfolio_experiments", {
            method: "POST",
            headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
            body: JSON.stringify({ title: assets.length > 1 ? `${first} 외 ${assets.length - 1}개 자산 실험` : `${first} 투자 실험`, assets, amount, start, frequency, rebalance, dividend, privacy, publish: true }),
        }).then(async (r) => {
            const data = await r.json().catch(() => ({}))
            if (!r.ok) throw new Error(data.error || "공유하지 못했어요")
            setMessage("커뮤니티에 공유했어요")
            if (props.communityPath && typeof window !== "undefined") window.setTimeout(() => { window.location.href = props.communityPath }, 600)
        }).catch((e) => setMessage(e instanceof Error ? e.message : "공유하지 못했어요")).finally(() => setSharing(false))
    }

    return (
        <div style={{ width: "100%", minHeight: "100%", background: "transparent", color: C.ink, fontFamily: FONT }}>
            <style>{PALETTE}</style>
            <main style={{ width: "100%", maxWidth: 1000, margin: "0 auto", padding: "8px clamp(14px, 2vw, 20px) 20px", boxSizing: "border-box" }}>
                <section style={{ padding: "0 0 12px" }}>
                    <h1 style={{ margin: 0, fontSize: 18, fontWeight: 800, lineHeight: 1.3, letterSpacing: "-0.4px" }}>내가 그때 투자했다면?</h1>
                    <p style={{ margin: "3px 0 0", maxWidth: 680, color: C.sub, fontSize: 12, lineHeight: 1.5, fontWeight: 600 }}>세 가지만 골라보세요. 어려운 설정은 알파네스트가 기본값으로 준비하고, 각 결과가 무엇을 뜻하는지도 함께 설명합니다.</p>
                </section>

                <section style={card}>
                    <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 17, fontWeight: 800 }}><span style={{ color: C.vg }}>1</span> 무엇에 투자해볼까요?</div>
                    <Help>국내·미국 종목, ETF와 원자재를 이름·종목코드·티커로 검색하세요. 여러 개를 추가하면 비중은 똑같이 나눠드려요.</Help>
                    <div style={{ position: "relative", marginTop: 15 }}>
                        <MagnifyingGlass size={19} color={C.faint} style={{ position: "absolute", left: 15, top: 16, zIndex: 1 }} />
                        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={loading ? "전체 자산을 불러오는 중…" : "예: 삼성전자, 애플, 금, WTI"} style={{ ...field, paddingLeft: 44 }} />
                        {query.trim() && <div style={{ position: "absolute", zIndex: 10, left: 0, right: 0, top: 56, background: C.card, borderRadius: 18, boxShadow: `0 14px 36px ${C.shadow}`, padding: 6, maxHeight: 330, overflowY: "auto" }}>
                            {matches.map((item) => <button key={item.ticker} onClick={() => addAsset(item)} style={{ width: "100%", border: "none", borderRadius: 13, background: "transparent", color: C.ink, padding: "11px 10px", fontFamily: FONT, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, textAlign: "left" }}>
                                <span style={{ display: "flex", alignItems: "center", gap: 11, minWidth: 0 }}><StockMark item={item} /><span style={{ minWidth: 0 }}><b style={{ fontSize: 13.5 }}>{item.name_ko || item.name}</b>{item.name_ko && item.name !== item.name_ko && <span style={{ display: "block", color: C.faint, fontSize: 11, marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.name}</span>}</span></span>
                                <span style={{ color: C.faint, fontSize: 11.5, fontWeight: 700, whiteSpace: "nowrap" }}>{item.ticker} · {item.market || "시장 확인"}</span>
                            </button>)}
                            {!loading && matches.length === 0 && <div style={{ padding: 14, color: C.sub, fontSize: 12, fontWeight: 650 }}>검색 결과가 없어요. 이름이나 티커를 다시 확인해주세요.</div>}
                        </div>}
                    </div>
                    {assets.some((item) => item.type === "commodity") && <div style={{ marginTop: 12, borderRadius: 15, background: C.blueS, color: C.sub, padding: "12px 14px", fontSize: 11.5, lineHeight: 1.6, fontWeight: 650 }}>원자재는 기업 주식이 아니라 선물 연속물 기준입니다. 실제 상품 수익률은 환율·롤오버·보수 때문에 달라질 수 있어요.</div>}
                    <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
                        {assets.map((item) => <div key={item.ticker} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, borderRadius: 16, background: C.field, padding: "11px 12px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 11, minWidth: 0 }}><StockMark item={item} /><div style={{ minWidth: 0 }}><b style={{ fontSize: 13.5 }}>{item.name_ko || item.name}</b><div style={{ color: C.faint, fontSize: 11, fontWeight: 700, marginTop: 3 }}>{item.ticker} · {item.market || (/^\d{6}$/.test(item.ticker) ? "KR" : "US")} · 비중 {item.weight.toFixed(2).replace(".00", "")}%</div></div></div>
                            <button onClick={() => removeAsset(item.ticker)} aria-label={`${item.name} 삭제`} style={{ width: 34, height: 34, padding: 0, border: "none", borderRadius: 11, background: C.card, color: C.faint, cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center", lineHeight: 0, flexShrink: 0 }}><Trash size={16} /></button>
                        </div>)}
                    </div>
                    <div style={{ marginTop: 17, color: C.sub, fontSize: 11.5, fontWeight: 700 }}>빠른 예시</div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 10, marginTop: 15 }}>
                        {PRESETS.map((item) => {
                            const active = assets.some((x) => x.ticker === item.ticker)
                            return <button key={item.ticker} onClick={() => addAsset(item)} style={{ border: "none", borderRadius: 14, padding: 15, textAlign: "left", cursor: "pointer", fontFamily: FONT, background: active ? C.vgS : C.field, color: C.ink }}>
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}><span style={{ display: "flex", alignItems: "center", gap: 10 }}><StockMark item={item} size={30} /><b style={{ fontSize: 14 }}>{item.name}</b></span>{active ? <Check size={16} color={C.vg} weight="bold" /> : <Plus size={16} color={C.faint} weight="bold" />}</div>
                                <div style={{ color: C.faint, fontSize: 11, fontWeight: 800, marginTop: 4 }}>{item.ticker}</div>
                                <div style={{ color: C.sub, fontSize: 11.5, lineHeight: 1.5, fontWeight: 600, marginTop: 9 }}>{item.lesson}</div>
                            </button>
                        })}
                    </div>
                </section>

                <section style={{ ...card, marginTop: 16 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 17, fontWeight: 800 }}><span style={{ color: C.vg }}>2</span> 한 번에 얼마를 넣을까요?</div>
                    <Help>기본값은 매달 30만 원입니다. 부담 없이 상상해볼 금액을 입력하세요.</Help>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 12, marginTop: 15 }}>
                        <div><input aria-label="투자 금액" type="number" min={1} value={amount} onChange={(e) => setAmount(Number(e.target.value))} style={field} /><Help>{amount.toLocaleString("ko-KR")}원씩 투자</Help></div>
                        <div><input aria-label="투자 시작일" type="date" value={start} onChange={(e) => setStart(e.target.value)} style={field} /><Help>이 날짜부터 오늘까지 비교</Help></div>
                    </div>
                </section>

                <section style={{ ...card, marginTop: 16, background: C.blueS }}>
                    <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}><Sparkle size={22} color={C.blue} weight="fill" /><div><div style={{ fontSize: 16, fontWeight: 800 }}>알파네스트가 먼저 이렇게 계산할게요</div><div style={{ color: C.sub, fontSize: 12.5, lineHeight: 1.65, fontWeight: 650, marginTop: 6 }}>매달 같은 날 투자하고, 받은 배당은 다시 투자하며, 세금과 거래비용은 별도로 보여주는 방식입니다. 각 개념은 결과 화면에서 쉬운 말로 풀이합니다.</div></div></div>
                </section>

                <button onClick={() => setAdvanced((v) => !v)} style={{ width: "100%", marginTop: 14, border: "none", borderRadius: 14, padding: "15px 17px", background: C.card, color: C.sub, fontFamily: FONT, fontSize: 13, fontWeight: 800, cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}><span>상세 설정 · 익숙한 분만 열어보세요</span><CaretDown size={18} style={{ transform: advanced ? "rotate(180deg)" : "none", transition: "transform .2s" }} /></button>

                {advanced && <section style={{ ...card, marginTop: 10 }}>
                    <div style={{ fontSize: 17, fontWeight: 800 }}>상세 설정</div>
                    <div style={{ marginTop: 15, padding: 14, borderRadius: 17, background: C.field }}>
                        <b style={{ fontSize: 12 }}>자산 비중</b>
                        <Help>비중은 투자금 100원 중 각 자산에 몇 원을 나눌지 뜻해요. 합계가 100%여야 합니다.</Help>
                        <div style={{ display: "grid", gap: 8, marginTop: 10 }}>{assets.map((item) => <div key={item.ticker} style={{ display: "grid", gridTemplateColumns: "1fr 100px", gap: 10, alignItems: "center" }}><span style={{ fontSize: 12.5, fontWeight: 700 }}>{item.name_ko || item.name}</span><input aria-label={`${item.name} 비중`} type="number" min={0} max={100} value={item.weight} onChange={(e) => setAssets((rows) => rows.map((x) => x.ticker === item.ticker ? { ...x, weight: Number(e.target.value) } : x))} style={{ ...field, minHeight: 40 }} /></div>)}</div>
                        <div style={{ marginTop: 9, color: Math.abs(totalWeight - 100) < .01 ? C.blue : C.red, fontSize: 12, fontWeight: 800 }}>합계 {totalWeight.toFixed(2).replace(".00", "")}% {Math.abs(totalWeight - 100) < .01 ? "· 준비됨" : "· 100%로 맞춰주세요"}</div>
                        <button onClick={() => setAssets((rows) => equalize(rows))} style={{ marginTop: 10, border: "none", borderRadius: 12, background: C.card, color: C.vg, padding: "10px 12px", fontFamily: FONT, fontSize: 12, fontWeight: 800, cursor: "pointer" }}>똑같이 나누기</button>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px,1fr))", gap: 12, marginTop: 15 }}>
                        <div><b style={{ fontSize: 12 }}>투자 주기</b><select value={frequency} onChange={(e) => setFrequency(e.target.value)} style={{ ...field, marginTop: 8 }}><option value="monthly">매월</option><option value="quarterly">매분기</option><option value="once">한 번만</option></select><Help>얼마나 자주 같은 금액을 투자할지 정해요.</Help></div>
                        <div><b style={{ fontSize: 12 }}>비중 조정</b><select value={rebalance} onChange={(e) => setRebalance(e.target.value)} style={{ ...field, marginTop: 8 }}><option value="yearly">매년 원래 비중으로</option><option value="quarterly">매분기 원래 비중으로</option><option value="none">조정하지 않음</option></select><Help>리밸런싱은 달라진 자산 비중을 처음 계획대로 되돌리는 일이에요.</Help></div>
                        <div><b style={{ fontSize: 12 }}>배당금</b><button onClick={() => setDividend((v) => !v)} style={{ ...field, marginTop: 8, cursor: "pointer", textAlign: "left" }}>{dividend ? "다시 투자" : "현금으로 보유"}</button><Help>재투자는 받은 배당금으로 같은 자산을 더 사는 방식이에요.</Help></div>
                        <div><b style={{ fontSize: 12 }}>공개 범위</b><select value={privacy} onChange={(e) => setPrivacy(e.target.value)} style={{ ...field, marginTop: 8 }}><option value="private">나만 보기</option><option value="summary">성과만 공유</option><option value="masked">종목을 숨기고 공유</option><option value="full">전체 공개</option></select><Help><LockKey size={12} /> 기본값은 나만 보기예요.</Help></div>
                    </div>
                </section>}

                <section style={{ ...card, marginTop: 16, display: "flex", gap: 16, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
                    <div><div style={{ fontSize: 16, fontWeight: 800 }}>{assets.length ? `${assets.length}개 자산 실험 준비됨` : "먼저 자산을 골라주세요"}</div><Help>과거 가격·배당·세금 엔진이 연결되면 수익률뿐 아니라 왜 그런 결과가 나왔는지도 보여드려요.</Help>{message && <div style={{ color: C.vg, fontSize: 11.5, fontWeight: 800, marginTop: 6 }}>{message}</div>}</div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <button disabled={!valid} onClick={saveDraft} style={{ border: "none", borderRadius: 15, background: privacy === "private" && valid ? C.vg : C.field, color: privacy === "private" && valid ? C.on : C.sub, padding: "14px 18px", fontFamily: FONT, fontSize: 13, fontWeight: 800, cursor: valid ? "pointer" : "default", display: "inline-flex", alignItems: "center", gap: 8 }}><FloppyDisk size={18} weight="bold" />비공개 초안 저장</button>
                        {privacy !== "private" && <button disabled={!valid || sharing} onClick={shareExperiment} style={{ border: "none", borderRadius: 15, background: valid ? C.vg : C.field, color: valid ? C.on : C.faint, padding: "14px 18px", fontFamily: FONT, fontSize: 13, fontWeight: 800, cursor: valid && !sharing ? "pointer" : "default" }}>{sharing ? "공유 중…" : "커뮤니티에 공유"}</button>}
                    </div>
                </section>
            </main>
        </div>
    )
}

addPropertyControls(PublicPortfolioLab, {
    title: { type: ControlType.String, title: "Title", defaultValue: "내가 그때 투자했다면?" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false },
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: UNIVERSE_URL },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    communityPath: { type: ControlType.String, title: "Community", defaultValue: "/community" },
})

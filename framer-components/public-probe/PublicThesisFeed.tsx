import { RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"
import { DotsThree, Heart, User } from "@phosphor-icons/react"

/**
 * 공개 관점 피드 — 커뮤니티 v1. PublicThesisNote 에서 분리(2026-07-10, MCP 대용량 push 상한 + 관심사 분리).
 * 자체 fetch(/api/thesis_feed) + 좋아요(낙관 갱신) + 신고(⋯ 메뉴, 인스타식). refreshKey 변경 = 재조회.
 * 🚨 RULE 7 — 피드 = 이용자 개인 의견 라벨 필수 (AlphaNest 분석·판단 아님). RULE 6 — LLM 0.
 */

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const DEMO_FEED = [
    { id: "d1", nickname: "길동무", avatar: "", stance: "bull", note: "수주 잔고 증가 + 부채비율 하향 추세. 다음 분기 마진 확인 후 재검토.", created_at: "2026-07-08", likes: 3, liked: false, mine: false },
    { id: "d2", nickname: "가치사냥", avatar: "", stance: "watch", note: "밸류는 싼데 거래량이 죽어 있음. 수급 돌아서면 다시 본다.", created_at: "2026-07-05", likes: 1, liked: true, mine: false },
]

const STANCE_LABEL: Record<string, string> = { bull: "강세", watch: "관망", bear: "약세" }

interface Props {
    tk: string
    base: string
    token: string
    C: any            // 부모(PublicThesisNote) 테마 팔레트 공유
    refreshKey?: number
}

export default function PublicThesisFeed(props: Props) {
    const { tk, base, token, C } = props
    const refreshKey = props.refreshKey || 0
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [feed, setFeed] = useState<any[]>([])
    const [feedMsg, setFeedMsg] = useState("")
    const [reported, setReported] = useState<Record<string, boolean>>({})
    const [menuId, setMenuId] = useState("")

    const stanceColor = (id: string) => (id === "bull" ? C.up : id === "bear" ? C.down : C.faint)

    const loadFeed = () => {
        if (onCanvas || !tk) return
        const h: Record<string, string> = {}
        if (token) h.Authorization = "Bearer " + token
        fetch(base + "/api/thesis_feed?ticker=" + encodeURIComponent(tk), { headers: h, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (d && Array.isArray(d.items)) setFeed(d.items) })
            .catch(() => {})
    }
    useEffect(() => {
        setFeed([])
        setReported({})
        setMenuId("")
        setFeedMsg("")
        if (onCanvas) { setFeed(DEMO_FEED); return }
        loadFeed()
    }, [tk, onCanvas, refreshKey])

    const toggleLike = (it: any) => {
        if (onCanvas) return
        if (!token) { setFeedMsg("좋아요는 로그인 후 가능해요"); return }
        const liked = !it.liked
        setFeed((f) => f.map((x) => (x.id === it.id ? { ...x, liked, likes: Math.max(0, x.likes + (liked ? 1 : -1)) } : x)))
        fetch(base + "/api/thesis_feed", { method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify({ action: liked ? "like" : "unlike", thesis_id: it.id }) }).catch(() => {})
    }
    const reportItem = (it: any) => {
        if (onCanvas || reported[it.id]) return
        if (!token) { setMenuId(""); setFeedMsg("신고는 로그인 후 가능해요"); return }
        setReported((m) => ({ ...m, [it.id]: true }))
        setMenuId("")
        fetch(base + "/api/thesis_feed", { method: "POST", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: JSON.stringify({ action: "report", thesis_id: it.id, reason: "" }) }).catch(() => {})
    }

    const card: CSSProperties = { background: C.card, borderRadius: 14, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", fontFamily: FONT }

    return (
        <div style={{ ...card, marginTop: 10 }}>
            {/* ⋯ 메뉴 바깥 클릭 닫기 backdrop */}
            {menuId && <div onClick={() => setMenuId("")} style={{ position: "fixed", inset: 0, zIndex: 20 }} />}
            <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>공개 관점</span>
                <span style={{ fontSize: 11, fontWeight: 600, color: C.faint }}>· 이 종목을 기록한 사람들{feed.length ? ` ${feed.length}` : ""}</span>
            </div>
            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginTop: 4, marginBottom: 6 }}>
                이용자 개인 의견이며 AlphaNest 의 분석·판단·추천이 아니에요.
            </div>
            {feedMsg && <div style={{ fontSize: 11.5, fontWeight: 700, color: C.up, marginBottom: 6 }}>{feedMsg}</div>}
            {feed.length === 0 ? (
                <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, padding: "6px 0 2px" }}>아직 공개된 관점이 없어요. 위에서 내 관점을 공개해 보세요.</div>
            ) : (
                feed.map((it) => (
                    <div key={it.id} style={{ padding: "10px 0 8px", borderTop: `1px solid ${C.line}` }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            {it.avatar ? (
                                <img src={it.avatar} alt="" width={26} height={26} style={{ width: 26, height: 26, borderRadius: 9, objectFit: "cover", flexShrink: 0 }} />
                            ) : (
                                <div style={{ width: 26, height: 26, borderRadius: 9, background: C.chipBg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                                    <User size={14} color={C.faint} weight="fill" />
                                </div>
                            )}
                            <span style={{ fontSize: 12.5, fontWeight: 800, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{it.nickname}{it.mine ? " (나)" : ""}</span>
                            <span style={{ fontSize: 11, fontWeight: 800, color: stanceColor(it.stance), flexShrink: 0 }}>{STANCE_LABEL[it.stance] || "관망"}</span>
                            <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginLeft: "auto", flexShrink: 0 }}>{(it.created_at || "").slice(0, 10)}</span>
                            {!it.mine && (
                                <span style={{ position: "relative", flexShrink: 0, display: "inline-flex" }}>
                                    <button onClick={() => setMenuId(menuId === it.id ? "" : it.id)} aria-label="더보기"
                                        style={{ border: "none", background: "transparent", cursor: "pointer", padding: 2, margin: -2, display: "inline-flex", alignItems: "center", color: C.faint }}>
                                        <DotsThree size={18} weight="bold" color={C.faint} />
                                    </button>
                                    {menuId === it.id && (
                                        <div style={{ position: "absolute", top: 22, right: 0, zIndex: 30, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, boxShadow: "0 4px 14px rgba(0,0,0,0.12)", overflow: "hidden", minWidth: 104 }}>
                                            <button onClick={() => reportItem(it)} disabled={!!reported[it.id]}
                                                style={{ display: "block", width: "100%", textAlign: "left", border: "none", background: "transparent", cursor: reported[it.id] ? "default" : "pointer", padding: "10px 14px", fontFamily: FONT, fontSize: 12, fontWeight: 700, color: reported[it.id] ? C.faint : C.up, whiteSpace: "nowrap" }}>
                                                {reported[it.id] ? "신고 접수됨" : "신고하기"}
                                            </button>
                                        </div>
                                    )}
                                </span>
                            )}
                        </div>
                        {it.note && <div style={{ fontSize: 12.5, color: C.ink, fontWeight: 500, lineHeight: 1.5, marginTop: 6, whiteSpace: "pre-wrap" }}>{it.note}</div>}
                        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 7 }}>
                            <button onClick={() => toggleLike(it)}
                                style={{ display: "inline-flex", alignItems: "center", gap: 4, border: "none", background: "transparent", cursor: "pointer", padding: 0, fontFamily: FONT, fontSize: 11.5, fontWeight: 700, color: it.liked ? C.up : C.faint }}>
                                <Heart size={14} weight={it.liked ? "fill" : "regular"} color={it.liked ? C.up : C.faint} />
                                {it.likes > 0 ? it.likes : "좋아요"}
                            </button>
                        </div>
                    </div>
                ))
            )}
        </div>
    )
}

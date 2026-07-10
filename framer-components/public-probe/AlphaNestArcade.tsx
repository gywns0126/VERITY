import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * AlphaNest 아케이드 — '블록 트레이딩'(주식 용어 테마 테트리스) + Supabase 랭킹.
 *
 * 이벤트 창에 얹는 자체완결 게임 컴포넌트(마켓플레이스 코드 의존 0, 백엔드 게임로직 0).
 * 데이터 의존 = 랭킹뿐. 게임은 전부 클라이언트.
 *
 * 테마: 게임오버=상장폐지 / 라인클리어=체결 / 점수=수익 / 레벨=변동성 / 4줄=상한가 / 다음=예약주문.
 *
 * 랭킹:
 *   - 읽기 = 공개(anon select top). 등록 = 로그인 사용자만(verity_supabase_session 토큰 재사용, AlphaNest 철학 동일).
 *   - 미로그인 = 플레이 자유, 등록 시 로그인 유도. 점수는 클라 제출이라 위조 가능(이벤트 v0 허용, 추후 서버 HMAC 여지).
 *   - 테이블 없으면 '랭킹 준비 중'으로 graceful degrade(컴포넌트 안 깨짐).
 *
 * 🚨 수동 선행(Supabase 대시보드 SQL 1회):
 *   create table if not exists alpha_nest_arcade_scores (
 *     id uuid primary key default gen_random_uuid(),
 *     user_id uuid references auth.users(id),
 *     name text not null,
 *     score int not null check (score >= 0 and score < 100000000),
 *     lines int not null default 0 check (lines >= 0 and lines < 100000),
 *     created_at timestamptz default now()
 *   );
 *   alter table alpha_nest_arcade_scores enable row level security;
 *   create policy "an arcade public read" on alpha_nest_arcade_scores for select using (true);
 *   create policy "an arcade auth insert own" on alpha_nest_arcade_scores for insert with check (auth.uid() = user_id);
 *   create index if not exists an_arcade_score_idx on alpha_nest_arcade_scores (score desc);
 *
 * 다크모드 = body[data-framer-theme] 추종(캔버스는 dark prop). RULE 9 준수(동사 '박-' 0).
 */

const SESSION_KEY = "verity_supabase_session"
const TABLE = "alpha_nest_arcade_scores"
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", vg: "#6c5ce7", vgS: "#f0edff", boardBg: "#eef1f4", grid: "#e1e6ea",
    btn: "#ffffff", btnInk: "#191f28", up: "#f04452",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", vg: "#a99bff", vgS: "#241f3a", boardBg: "#0b0f14", grid: "#1b222b",
    btn: "#1c232c", btnInk: "#e3e7ec", up: "#f04452",
}

// 블록 색(라이트·다크 공용 — 보드 배경만 테마 분리). AlphaNest 초록·골드 계열 포함.
const COLORS = ["", "#33d6a6", "#f7b733", "#a78bfa", "#34d399", "#f87171", "#60a5fa", "#fb923c"]

const COLS = 10
const ROWS = 20

// 테트로미노(색 인덱스는 행렬 값 자체로 사용 — 모양별 고정).
const SHAPES: Record<string, number[][]> = {
    I: [[0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0], [0, 0, 0, 0]],
    O: [[2, 2], [2, 2]],
    T: [[0, 3, 0], [3, 3, 3], [0, 0, 0]],
    S: [[0, 4, 4], [4, 4, 0], [0, 0, 0]],
    Z: [[5, 5, 0], [0, 5, 5], [0, 0, 0]],
    J: [[6, 0, 0], [6, 6, 6], [0, 0, 0]],
    L: [[0, 0, 7], [7, 7, 7], [0, 0, 0]],
}
const TYPES = ["I", "O", "T", "S", "Z", "J", "L"]

interface Piece {
    m: number[][]
    x: number
    y: number
}
interface Game {
    board: number[][]
    cur: Piece
    next: string
    score: number
    lines: number
    level: number
    status: "idle" | "playing" | "paused" | "over"
    flash: string // "상한가!" 등 일시 표시
    flashUntil: number
    seed: number
}

function emptyBoard(): number[][] {
    const b: number[][] = []
    for (let r = 0; r < ROWS; r++) {
        const row: number[] = []
        for (let c = 0; c < COLS; c++) row.push(0)
        b.push(row)
    }
    return b
}

// seed 기반 PRNG(렌더 결정성 — Math.random 의존 회피, 게임이라 강도 불필요).
function nextRand(g: Game): number {
    g.seed = (g.seed * 1664525 + 1013904223) >>> 0
    return g.seed / 4294967296
}
function randType(g: Game): string {
    return TYPES[Math.floor(nextRand(g) * TYPES.length)] || "T"
}

function cloneShape(t: string): number[][] {
    const s = SHAPES[t]
    return s.map((row) => row.slice())
}

function rotateCW(m: number[][]): number[][] {
    const n = m.length
    const out: number[][] = []
    for (let i = 0; i < n; i++) {
        const row: number[] = []
        for (let j = 0; j < n; j++) row.push(m[n - 1 - j][i])
        out.push(row)
    }
    return out
}

function spawn(g: Game, t: string): Piece {
    const m = cloneShape(t)
    const w = m[0].length
    return { m, x: Math.floor((COLS - w) / 2), y: 0 }
}

function collides(board: number[][], p: Piece, m?: number[][], nx?: number, ny?: number): boolean {
    const mat = m || p.m
    const px = nx === undefined ? p.x : nx
    const py = ny === undefined ? p.y : ny
    for (let r = 0; r < mat.length; r++) {
        for (let c = 0; c < mat[r].length; c++) {
            if (!mat[r][c]) continue
            const bx = px + c
            const by = py + r
            if (bx < 0 || bx >= COLS || by >= ROWS) return true
            if (by >= 0 && board[by][bx]) return true
        }
    }
    return false
}

function lockPiece(g: Game) {
    const { board, cur } = g
    for (let r = 0; r < cur.m.length; r++) {
        for (let c = 0; c < cur.m[r].length; c++) {
            if (!cur.m[r][c]) continue
            const by = cur.y + r
            const bx = cur.x + c
            if (by >= 0 && by < ROWS && bx >= 0 && bx < COLS) board[by][bx] = cur.m[r][c]
        }
    }
    // 라인 체결
    let cleared = 0
    for (let r = ROWS - 1; r >= 0; r--) {
        let full = true
        for (let c = 0; c < COLS; c++) if (!board[r][c]) { full = false; break }
        if (full) {
            board.splice(r, 1)
            const empty: number[] = []
            for (let c = 0; c < COLS; c++) empty.push(0)
            board.unshift(empty)
            cleared++
            r++ // 같은 인덱스 재검사
        }
    }
    if (cleared > 0) {
        const table = [0, 100, 300, 500, 800]
        g.score += (table[cleared] || 800) * g.level
        g.lines += cleared
        g.level = Math.floor(g.lines / 10) + 1
        if (cleared >= 4) { g.flash = "상한가!"; g.flashUntil = g.score } // flashUntil = 표시 토큰(점수 변동 시 갱신)
        else if (cleared >= 2) { g.flash = "체결 x" + cleared; g.flashUntil = g.score }
    }
    // 다음 블록
    const np = spawn(g, g.next)
    g.next = randType(g)
    if (collides(g.board, np)) {
        g.cur = np
        g.status = "over"
    } else {
        g.cur = np
    }
}

function speedMs(level: number): number {
    return Math.max(90, 780 - (level - 1) * 68)
}

function ghostY(board: number[][], p: Piece): number {
    let y = p.y
    while (!collides(board, p, p.m, p.x, y + 1)) y++
    return y
}

function loadSession(): { token: string; name: string; userId: string } {
    if (typeof window === "undefined") return { token: "", name: "", userId: "" }
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return { token: "", name: "", userId: "" }
        const s = JSON.parse(raw)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return { token: "", name: "", userId: "" }
        const meta = (s.user && s.user.user_metadata) || {}
        const name = meta.name || meta.full_name || ((s.user && s.user.email) || "").split("@")[0] || "AlphaNest"
        return { token: s.access_token || "", name, userId: (s.user && s.user.id) || "" }
    } catch {
        return { token: "", name: "", userId: "" }
    }
}

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    cellSize: number
    dark: boolean
}
const DEFAULT_SUPABASE_URL = "https://lykqebdcurreppowulsl.supabase.co"
const DEFAULT_SUPABASE_ANON_KEY = ""

function readBodyDark(): boolean {
    // 첫 페인트 flash 방지 — body 속성 미설정(마운트 직후) 시 토글 저장 선호(localStorage) → OS 순 폴백.
    // PublicThemeToggle 이 verity_theme 로 저장 + body[data-framer-theme] 설정 = 동일 소스라 첫 페인트부터 정합.
    try {
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function AlphaNestArcade(props: Props) {
    const { supabaseUrl, supabaseAnonKey, cellSize, dark } = props
    const url = (supabaseUrl || DEFAULT_SUPABASE_URL).replace(/\/+$/, "")
    const anonKey = supabaseAnonKey || DEFAULT_SUPABASE_ANON_KEY
    const CELL = Math.max(14, Math.min(30, cellSize || 22))
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    // 다크모드 추종
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))
    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT
    useEffect(() => {
        if (onCanvas) return
        const readTheme = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        readTheme()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(readTheme)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const gameRef = useRef<Game | null>(null)
    const canvasRef = useRef<HTMLCanvasElement | null>(null)
    const dropTimer = useRef<any>(null)
    // 테마 색을 ref 로 추적 — 게임 중 interval/키보드 클로저가 옛 색을 잡지 않게(다크 토글 안전).
    const cRef = useRef(C)
    cRef.current = C
    const [, setTick] = useState(0)
    const render = () => setTick((n) => (n + 1) % 1000000)

    const [board, setBoardState] = useState<"idle" | "playing" | "paused" | "over">("idle")
    const [score, setScore] = useState(0)
    const [lines, setLines] = useState(0)
    const [level, setLevel] = useState(1)
    const [flash, setFlash] = useState("")
    const [nextType, setNextType] = useState("T")

    const [showRank, setShowRank] = useState(false)
    const [ranks, setRanks] = useState<any[] | null>(null)
    const [rankErr, setRankErr] = useState(false)
    const [submitState, setSubmitState] = useState<"" | "saving" | "done" | "need-login">("")

    const syncHud = (g: Game) => {
        setBoardState(g.status)
        setScore(g.score)
        setLines(g.lines)
        setLevel(g.level)
        setNextType(g.next)
        if (g.flash) {
            const f = g.flash
            setFlash(f)
            g.flash = ""
            setTimeout(() => setFlash((cur) => (cur === f ? "" : cur)), 900)
        }
    }

    // 캔버스 draw
    const drawBoard = (g: Game | null) => {
        const canvas = canvasRef.current
        if (!canvas) return
        const ctx = canvas.getContext("2d")
        if (!ctx) return
        const C = cRef.current // 최신 테마(클로저 staleness 회피)
        const dpr = (typeof window !== "undefined" && window.devicePixelRatio) || 1
        const w = COLS * CELL
        const h = ROWS * CELL
        if (canvas.width !== Math.round(w * dpr)) {
            canvas.width = Math.round(w * dpr)
            canvas.height = Math.round(h * dpr)
            canvas.style.width = w + "px"
            canvas.style.height = h + "px"
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        ctx.clearRect(0, 0, w, h)
        ctx.fillStyle = C.boardBg
        ctx.fillRect(0, 0, w, h)
        // 격자
        ctx.strokeStyle = C.grid
        ctx.lineWidth = 1
        for (let c = 1; c < COLS; c++) {
            ctx.beginPath(); ctx.moveTo(c * CELL + 0.5, 0); ctx.lineTo(c * CELL + 0.5, h); ctx.stroke()
        }
        for (let r = 1; r < ROWS; r++) {
            ctx.beginPath(); ctx.moveTo(0, r * CELL + 0.5); ctx.lineTo(w, r * CELL + 0.5); ctx.stroke()
        }
        const cell = (cx: number, cy: number, color: string, ghost: boolean) => {
            const x = cx * CELL
            const y = cy * CELL
            if (ghost) {
                ctx.strokeStyle = color
                ctx.globalAlpha = 0.5
                ctx.lineWidth = 2
                ctx.strokeRect(x + 2, y + 2, CELL - 4, CELL - 4)
                ctx.globalAlpha = 1
                return
            }
            ctx.fillStyle = color
            ctx.fillRect(x + 1, y + 1, CELL - 2, CELL - 2)
            // 상단 하이라이트
            ctx.fillStyle = "rgba(255,255,255,0.22)"
            ctx.fillRect(x + 1, y + 1, CELL - 2, Math.max(2, Math.floor(CELL * 0.18)))
        }
        if (!g) return
        // 고정 블록
        for (let r = 0; r < ROWS; r++) {
            for (let c = 0; c < COLS; c++) {
                if (g.board[r][c]) cell(c, r, COLORS[g.board[r][c]] || C.vg, false)
            }
        }
        if (g.status === "playing" || g.status === "paused") {
            // 고스트
            const gy = ghostY(g.board, g.cur)
            for (let r = 0; r < g.cur.m.length; r++) {
                for (let c = 0; c < g.cur.m[r].length; c++) {
                    if (!g.cur.m[r][c]) continue
                    if (gy + r >= 0) cell(g.cur.x + c, gy + r, COLORS[g.cur.m[r][c]] || C.vg, true)
                }
            }
            // 현재 블록
            for (let r = 0; r < g.cur.m.length; r++) {
                for (let c = 0; c < g.cur.m[r].length; c++) {
                    if (!g.cur.m[r][c]) continue
                    if (g.cur.y + r >= 0) cell(g.cur.x + c, g.cur.y + r, COLORS[g.cur.m[r][c]] || C.vg, false)
                }
            }
        }
    }

    // 테마 변경 시 재그리기
    useEffect(() => { drawBoard(gameRef.current) }, [themeDark, CELL])

    const clearTimer = () => { if (dropTimer.current) { clearInterval(dropTimer.current); dropTimer.current = null } }

    const startTimer = () => {
        clearTimer()
        const g = gameRef.current
        if (!g) return
        dropTimer.current = setInterval(() => {
            const gm = gameRef.current
            if (!gm || gm.status !== "playing") return
            step(gm)
        }, speedMs(g.level))
    }

    // 한 칸 낙하(또는 락)
    const step = (g: Game) => {
        if (collides(g.board, g.cur, g.cur.m, g.cur.x, g.cur.y + 1)) {
            const prevLevel = g.level
            lockPiece(g)
            drawBoard(g)
            syncHud(g)
            if (g.status === "over") {
                clearTimer()
                onGameOver(g)
            } else if (g.level !== prevLevel) {
                startTimer() // 속도 갱신
            }
        } else {
            g.cur.y++
            drawBoard(g)
        }
    }

    const move = (dx: number) => {
        const g = gameRef.current
        if (!g || g.status !== "playing") return
        if (!collides(g.board, g.cur, g.cur.m, g.cur.x + dx, g.cur.y)) {
            g.cur.x += dx
            drawBoard(g)
        }
    }
    const softDrop = () => {
        const g = gameRef.current
        if (!g || g.status !== "playing") return
        step(g)
    }
    const rotate = () => {
        const g = gameRef.current
        if (!g || g.status !== "playing") return
        const rm = rotateCW(g.cur.m)
        // 벽킥(좌우 1~2칸 시도)
        const kicks = [0, -1, 1, -2, 2]
        for (let i = 0; i < kicks.length; i++) {
            if (!collides(g.board, g.cur, rm, g.cur.x + kicks[i], g.cur.y)) {
                g.cur.m = rm
                g.cur.x += kicks[i]
                drawBoard(g)
                return
            }
        }
    }
    const hardDrop = () => {
        const g = gameRef.current
        if (!g || g.status !== "playing") return
        const gy = ghostY(g.board, g.cur)
        g.cur.y = gy
        const prevLevel = g.level
        lockPiece(g)
        drawBoard(g)
        syncHud(g)
        if (g.status === "over") { clearTimer(); onGameOver(g) }
        else if (g.level !== prevLevel) startTimer()
    }

    const onGameOver = (g: Game) => {
        // 랭킹 자동 등록(로그인 시) + 리스트 갱신
        const sess = loadSession()
        if (!sess.token || !sess.userId) {
            setSubmitState("need-login")
            setShowRank(true)
            fetchRanks()
            return
        }
        if (g.score <= 0) { setSubmitState(""); setShowRank(true); fetchRanks(); return }
        setSubmitState("saving")
        setShowRank(true)
        submitScore(sess, g.score, g.lines)
    }

    const newGame = () => {
        clearTimer()
        const seed = ((typeof performance !== "undefined" ? Math.floor(performance.now()) : 1) * 2654435761) >>> 0
        const g: Game = {
            board: emptyBoard(),
            cur: { m: [[0]], x: 0, y: 0 },
            next: "T",
            score: 0,
            lines: 0,
            level: 1,
            status: "playing",
            flash: "",
            flashUntil: 0,
            seed: seed || 12345,
        }
        const first = randType(g)
        g.cur = spawn(g, first)
        g.next = randType(g)
        gameRef.current = g
        setSubmitState("")
        syncHud(g)
        drawBoard(g)
        startTimer()
        render()
    }

    const togglePause = () => {
        const g = gameRef.current
        if (!g) return
        if (g.status === "playing") { g.status = "paused"; clearTimer() }
        else if (g.status === "paused") { g.status = "playing"; startTimer() }
        syncHud(g)
        drawBoard(g)
    }

    // 키보드
    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        const onKey = (e: KeyboardEvent) => {
            const g = gameRef.current
            if (!g) return
            const k = e.key
            if (k === "ArrowLeft") { e.preventDefault(); move(-1) }
            else if (k === "ArrowRight") { e.preventDefault(); move(1) }
            else if (k === "ArrowDown") { e.preventDefault(); softDrop() }
            else if (k === "ArrowUp" || k === "x" || k === "X") { e.preventDefault(); rotate() }
            else if (k === " ") { e.preventDefault(); hardDrop() }
            else if (k === "p" || k === "P") { e.preventDefault(); togglePause() }
        }
        window.addEventListener("keydown", onKey)
        return () => window.removeEventListener("keydown", onKey)
    }, [onCanvas])

    useEffect(() => () => clearTimer(), [])

    // ── 랭킹 ──
    const fetchRanks = () => {
        if (onCanvas || !anonKey) { setRanks([]); return }
        fetch(`${url}/rest/v1/${TABLE}?select=name,score,lines,created_at&order=score.desc&limit=80`, {
            headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` },
            cache: "no-store",
        })
            .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
            .then((rows) => {
                if (!Array.isArray(rows)) { setRanks([]); return }
                // 이름별 최고점만(클라 dedupe)
                const best: Record<string, any> = {}
                for (const row of rows) {
                    const nm = String(row.name || "익명")
                    if (!best[nm] || row.score > best[nm].score) best[nm] = row
                }
                const list = Object.keys(best).map((k) => best[k]).sort((a, b) => b.score - a.score).slice(0, 30)
                setRanks(list)
                setRankErr(false)
            })
            .catch(() => { setRanks([]); setRankErr(true) })
    }

    const submitScore = (sess: { token: string; name: string; userId: string }, sc: number, ln: number) => {
        if (!anonKey) { setSubmitState(""); fetchRanks(); return }
        fetch(`${url}/rest/v1/${TABLE}`, {
            method: "POST",
            headers: {
                apikey: anonKey,
                Authorization: `Bearer ${sess.token}`,
                "Content-Type": "application/json",
                Prefer: "return=minimal",
            },
            body: JSON.stringify({ user_id: sess.userId, name: sess.name, score: sc, lines: ln }),
        })
            .then((r) => {
                if (r.ok) setSubmitState("done")
                else setSubmitState("")
            })
            .catch(() => setSubmitState(""))
            .finally(() => fetchRanks())
    }

    // ── 렌더 ──
    const wrap: CSSProperties = {
        width: "100%", height: "100%", background: C.bg, fontFamily: FONT, boxSizing: "border-box",
        color: C.ink, padding: 16, display: "flex", flexDirection: "column", alignItems: "center",
        gap: 12, overflowY: "auto",
    }

    const sess = loadSession()
    const loggedIn = !!sess.token

    const Hud = (
        <div style={{ display: "flex", gap: 8, width: COLS * CELL, maxWidth: "100%" }}>
            {[
                { k: "수익", v: score.toLocaleString() },
                { k: "체결", v: String(lines) },
                { k: "변동성 Lv", v: String(level) },
            ].map((s) => (
                <div key={s.k} style={{ flex: 1, background: C.card, borderRadius: 12, padding: "8px 10px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 700, letterSpacing: "-0.2px" }}>{s.k}</div>
                    <div style={{ fontSize: 17, color: C.ink, fontWeight: 800, letterSpacing: "-0.4px", marginTop: 2 }}>{s.v}</div>
                </div>
            ))}
        </div>
    )

    // 다음 블록 미리보기
    const NextPreview = () => {
        const m = SHAPES[nextType] || SHAPES.T
        const px = 12
        return (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 700 }}>예약주문</span>
                <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                    {m.map((row, ri) => (
                        <div key={ri} style={{ display: "flex", gap: 1 }}>
                            {row.map((v, ci) => (
                                <span key={ci} style={{ width: px, height: px, borderRadius: 2, background: v ? (COLORS[v] || C.vg) : "transparent" }} />
                            ))}
                        </div>
                    ))}
                </div>
            </div>
        )
    }

    const padBtn = (label: string, onClick: () => void) => (
        <button onClick={onClick} onTouchStart={(e) => { e.preventDefault(); onClick() }}
            style={{
                width: 52, height: 52, border: `1px solid ${C.line}`, background: C.btn, color: C.btnInk,
                cursor: "pointer", fontFamily: FONT, fontSize: 20, fontWeight: 800, borderRadius: 14,
                display: "inline-flex", alignItems: "center", justifyContent: "center", touchAction: "manipulation",
            }}>
            {label}
        </button>
    )

    return (
        <div style={wrap}>
            <div style={{ width: COLS * CELL, maxWidth: "100%", display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <div>
                    <div style={{ fontSize: 16, fontWeight: 900, color: C.ink, letterSpacing: "-0.4px" }}>AlphaNest 아케이드</div>
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 700, marginTop: 1 }}>블록 트레이딩 · 이벤트</div>
                </div>
                <button onClick={() => { setShowRank((v) => !v); if (!ranks) fetchRanks() }}
                    style={{ border: `1px solid ${C.line}`, background: C.card, color: C.sub, cursor: "pointer", fontFamily: FONT, fontSize: 12, fontWeight: 800, padding: "6px 11px", borderRadius: 10 }}>
                    {showRank ? "게임" : "랭킹"}
                </button>
            </div>

            {Hud}

            {showRank ? (
                <div style={{ width: COLS * CELL, maxWidth: "100%", background: C.card, borderRadius: 14, padding: "12px 14px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 8 }}>
                        <span style={{ fontSize: 14, fontWeight: 900, color: C.ink }}>랭킹 · 수익 상위</span>
                        {submitState === "saving" && <span style={{ fontSize: 11, color: C.faint, fontWeight: 700 }}>등록 중…</span>}
                        {submitState === "done" && <span style={{ fontSize: 11, color: C.vg, fontWeight: 800 }}>등록 완료</span>}
                    </div>
                    {submitState === "need-login" && (
                        <div style={{ fontSize: 12, color: C.sub, fontWeight: 700, background: C.vgS, borderRadius: 10, padding: "9px 11px", marginBottom: 8, lineHeight: 1.5 }}>
                            로그인하면 이번 수익이 랭킹에 등록돼요 (상단 nav 구글 로그인).
                        </div>
                    )}
                    {ranks === null ? (
                        <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 700, padding: "10px 0" }}>불러오는 중…</div>
                    ) : rankErr || ranks.length === 0 ? (
                        <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 700, padding: "10px 0", lineHeight: 1.5 }}>
                            {rankErr ? "랭킹 준비 중 — 잠시 후 다시 시도해주세요." : "아직 기록이 없어요. 첫 주자가 되어보세요."}
                        </div>
                    ) : (
                        <div>
                            {ranks.map((row, i) => (
                                <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                    <span style={{ width: 22, fontSize: 13, fontWeight: 900, color: i < 3 ? C.vg : C.faint, textAlign: "center" }}>{i + 1}</span>
                                    <span style={{ flex: 1, fontSize: 13, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{row.name}</span>
                                    <span style={{ fontSize: 11, color: C.faint, fontWeight: 700 }}>{row.lines}체결</span>
                                    <span style={{ fontSize: 14, fontWeight: 900, color: C.ink, minWidth: 56, textAlign: "right" }}>{Number(row.score).toLocaleString()}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            ) : (
                <>
                    <div style={{ position: "relative", width: COLS * CELL, maxWidth: "100%" }}>
                        <canvas ref={canvasRef} style={{ display: "block", borderRadius: 12, width: COLS * CELL, height: ROWS * CELL, boxShadow: "0 2px 10px rgba(0,0,0,0.10)" }} />
                        {(board === "idle" || board === "over" || board === "paused") && (
                            <div style={{
                                position: "absolute", inset: 0, borderRadius: 12, display: "flex", flexDirection: "column",
                                alignItems: "center", justifyContent: "center", gap: 10,
                                background: themeDark ? "rgba(8,12,16,0.78)" : "rgba(240,243,246,0.86)",
                            }}>
                                {board === "over" && (
                                    <>
                                        <div style={{ fontSize: 24, fontWeight: 900, color: C.up, letterSpacing: "-0.5px" }}>상장폐지</div>
                                        <div style={{ fontSize: 13, fontWeight: 800, color: C.ink }}>최종 수익 {score.toLocaleString()} · {lines}체결</div>
                                    </>
                                )}
                                {board === "paused" && <div style={{ fontSize: 20, fontWeight: 900, color: C.ink }}>일시정지</div>}
                                {board === "idle" && (
                                    <>
                                        <div style={{ fontSize: 18, fontWeight: 900, color: C.ink }}>블록 트레이딩</div>
                                        <div style={{ fontSize: 12, fontWeight: 700, color: C.sub, textAlign: "center", lineHeight: 1.6, maxWidth: COLS * CELL - 24 }}>
                                            블록을 쌓아 줄을 체결하면 수익.<br />4줄 동시 = 상한가.
                                        </div>
                                    </>
                                )}
                                <button onClick={newGame}
                                    style={{ border: "none", background: C.vg, color: themeDark ? "#0b1f12" : "#ffffff", cursor: "pointer", fontFamily: FONT, fontSize: 14, fontWeight: 900, padding: "11px 22px", borderRadius: 12, marginTop: 4 }}>
                                    {board === "over" ? "다시 거래" : "거래 시작"}
                                </button>
                            </div>
                        )}
                        {flash && (board === "playing") && (
                            <div style={{ position: "absolute", top: 8, left: 0, right: 0, textAlign: "center", pointerEvents: "none" }}>
                                <span style={{ fontSize: 18, fontWeight: 900, color: C.vg, textShadow: "0 1px 6px rgba(0,0,0,0.3)" }}>{flash}</span>
                            </div>
                        )}
                    </div>

                    <div style={{ width: COLS * CELL, maxWidth: "100%", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <NextPreview />
                        {board === "playing" && (
                            <button onClick={togglePause}
                                style={{ border: `1px solid ${C.line}`, background: C.card, color: C.sub, cursor: "pointer", fontFamily: FONT, fontSize: 12, fontWeight: 800, padding: "6px 12px", borderRadius: 10 }}>
                                일시정지
                            </button>
                        )}
                        {board === "paused" && (
                            <button onClick={togglePause}
                                style={{ border: "none", background: C.vg, color: themeDark ? "#0b1f12" : "#ffffff", cursor: "pointer", fontFamily: FONT, fontSize: 12, fontWeight: 800, padding: "6px 12px", borderRadius: 10 }}>
                                재개
                            </button>
                        )}
                    </div>

                    {/* 모바일 터치 컨트롤 */}
                    <div style={{ display: "flex", gap: 10, alignItems: "center", justifyContent: "center", marginTop: 2 }}>
                        {padBtn("◀", () => move(-1))}
                        {padBtn("▼", softDrop)}
                        {padBtn("▶", () => move(1))}
                        {padBtn("↻", rotate)}
                        {padBtn("⤓", hardDrop)}
                    </div>
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, textAlign: "center", lineHeight: 1.5 }}>
                        키보드: ←→ 이동 · ↑/X 회전 · ↓ 한칸 · Space 즉시낙하 · P 일시정지<br />
                        {loggedIn ? "랭킹 등록 = 게임오버 시 자동" : "로그인하면 수익이 랭킹에 등록돼요"}
                    </div>
                </>
            )}
        </div>
    )
}

addPropertyControls(AlphaNestArcade, {
    supabaseUrl: { type: ControlType.String, title: "Supabase URL", defaultValue: DEFAULT_SUPABASE_URL },
    supabaseAnonKey: { type: ControlType.String, title: "Supabase Anon Key", defaultValue: DEFAULT_SUPABASE_ANON_KEY },
    cellSize: { type: ControlType.Number, title: "Cell Size", defaultValue: 22, min: 14, max: 30, step: 1 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})

# VERITY 검수 리포트 — SESSION 6 (Framer 컴포넌트 데이터 바인딩)

**대상:** `framer-components/StockDashboard.tsx`, `StockDetailPanel.tsx`, `VerityBrainPanel.tsx`
**연관 파일:** `framer-components/WatchGroupsCard.tsx`, `fetchPortfolioJson.ts`, `vercel-api/api/watchgroups.py` (서버측 대조)
**검수 범위:** NaN/null/undefined 방어 · portfolio.json fetch 실패 처리 · 실시간 SSE · 차트 엣지케이스 · 관심종목 CRUD 동시성

---

## 🔴 CRITICAL

### CRIT-15. `WatchGroupsCard.tsx`가 JWT Authorization 헤더 미전송 — CRIT-7 서버 수정 후 완전 동작 불능
**framer-components/WatchGroupsCard.tsx > Line 139, 284, 303, 322, 348 + vercel-api/api/watchgroups.py > Line 90~97 > [이전 세션 수정이 남긴 회귀 버그]**

**현상:** SESSION 3 CRIT-7 수정에서 서버(`watchgroups.py`)를 JWT 기반 인증으로 전환했다. 그러나 **실제 UI 컴포넌트인 `WatchGroupsCard.tsx`는 업데이트되지 않았다**. 모든 fetch 호출이 Authorization 헤더 없이 발송:

```tsx
139: fetch(`${api}/api/watchgroups?user_id=${encodeURIComponent(userId)}`, { mode: "cors", credentials: "omit" })
284: fetch(`${api}/api/watchgroups`, { method: "POST", headers: { "Content-Type": "application/json" }, body: ... })
303: fetch(`${api}/api/watchgroups`, { method: "DELETE", ... })
322: fetch(`${api}/api/watchgroups`, { method: "POST", ... })       // add_item
348: fetch(`${api}/api/watchgroups`, { method: "DELETE", ... })     // remove_item
```

서버의 `_authenticate()` (watchgroups.py:90):
```python
jwt = _extract_jwt(h)   # Bearer 헤더에서 토큰 추출
if not jwt:
    _json_response(h, {"error": "Unauthorized"}, 401)
```
→ **모든 요청이 401로 거부됨**. 로딩 → 빈 목록 → 생성/추가/삭제 전부 실패 → `showToast("...실패했습니다")` 메시지만 반복.

또한 `getVerityUserId()` Line 36~44는 localStorage UUID를 사용하는 구 로직이 남아 있다. JWT 모델에서는 불필요.

**수정코드:**
```tsx
// WatchGroupsCard.tsx 상단 헬퍼에 추가
const SESSION_KEY = "verity_supabase_session"

function getAccessToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return ""
        const s = JSON.parse(raw)
        return s && typeof s.access_token === "string" ? s.access_token : ""
    } catch {
        return ""
    }
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
    const token = getAccessToken()
    const h: Record<string, string> = { ...extra }
    if (token) h["Authorization"] = `Bearer ${token}`
    return h
}
```

각 fetch 호출을 다음 패턴으로 교체:
```tsx
// loadGroups (Line 136)
const loadGroups = useCallback(() => {
    if (!api) { setLoading(false); return }
    if (!getAccessToken()) {
        // 로그인 안 됨 → 빈 목록 + 안내
        setGroups([])
        setLoading(false)
        return
    }
    setLoading(true)
    fetch(`${api}/api/watchgroups`, {
        mode: "cors", credentials: "omit",
        headers: authHeaders(),
    })
        .then(r => {
            if (r.status === 401) {
                showToast("로그인이 필요합니다")
                throw new Error("unauthorized")
            }
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.text()
        })
        .then(txt => {
            const data = safeJsonParse(txt)
            if (Array.isArray(data)) setGroups(data)
        })
        .catch(() => {})
        .finally(() => setLoading(false))
}, [api, showToast])

// createGroup (Line 282)
fetch(`${api}/api/watchgroups`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ name: newName.trim(), color: newColor, icon: newIcon }),
    mode: "cors", credentials: "omit",
})

// deleteGroup (Line 303)
fetch(`${api}/api/watchgroups`, {
    method: "DELETE",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ id }),
    mode: "cors", credentials: "omit",
})

// addItem (Line 322)
fetch(`${api}/api/watchgroups`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
        action: "add_item",
        group_id: groupId,
        ticker, name: ticker, market: addMarket,
    }),
    mode: "cors", credentials: "omit",
})

// removeItem (Line 348)
fetch(`${api}/api/watchgroups`, {
    method: "DELETE",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ action: "remove_item", item_id: itemId }),
    mode: "cors", credentials: "omit",
})
```

body에서 `user_id` 필드를 제거(서버가 JWT로 판단). `getVerityUserId()` 함수는 **deprecated 주석만 남기고 내부 사용은 삭제**.

---

### CRIT-16. CRUD 빠른 연속 클릭 → 중복 요청 방어 부재
**framer-components/WatchGroupsCard.tsx > Line 282~357 > [debounce·loading state 없음]**

**현상:** `createGroup`, `deleteGroup`, `addItem`, `removeItem` 모두:
- 제출 버튼에 `disabled` prop이 걸리는 submitting state 없음.
- ref-based dedupe 없음.
- `addItem`의 중복 체크(Line 318)는 **state.groups** 기준인데 state는 fetch 완료 후 갱신되므로 두 번째 클릭이 첫 요청 완료 전에 들어오면 중복 생성.

시나리오:
1. "그룹 생성" 버튼을 0.3초 안에 3회 클릭 → 서버에 3개의 동일 그룹 생성 요청 → DB에 3개 중복 row 삽입.
2. 관심종목 "+추가"를 2회 연속 클릭 → 같은 ticker가 중복 add_item → `watch_group_items`에 동일 행 2개.

**수정코드:**
```tsx
// 진행 중 상태 플래그 (각 액션별)
const [creating, setCreating] = useState(false)
const [addingItemId, setAddingItemId] = useState<string | null>(null)
const [deletingItemId, setDeletingItemId] = useState<string | null>(null)
const inflightRef = useRef<Set<string>>(new Set())

const createGroup = useCallback(() => {
    if (!api || !newName.trim() || creating) return
    setCreating(true)
    fetch(`${api}/api/watchgroups`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ name: newName.trim(), color: newColor, icon: newIcon }),
        mode: "cors", credentials: "omit",
    })
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then(() => { setShowCreate(false); setNewName(""); loadGroups() })
        .catch(() => showToast("그룹 생성에 실패했습니다"))
        .finally(() => setCreating(false))
}, [api, newName, newColor, newIcon, loadGroups, showToast, creating])

const addItem = useCallback((groupId: string) => {
    if (!api || !addTicker.trim()) return
    const ticker = addTicker.trim()
    const dedupeKey = `add:${groupId}:${ticker}`
    if (inflightRef.current.has(dedupeKey)) return
    const group = groups.find(g => g.id === groupId)
    if (group?.items.some(it => it.ticker === ticker)) {
        showToast("이미 추가된 종목입니다"); return
    }
    inflightRef.current.add(dedupeKey)
    setAddingItemId(groupId)
    fetch(/* ... */)
        .then(/* ... */)
        .finally(() => {
            inflightRef.current.delete(dedupeKey)
            setAddingItemId(null)
        })
}, [api, addTicker, addMarket, groups, loadGroups, showToast])

const removeItem = useCallback((itemId: string) => {
    if (deletingItemId === itemId) return
    // ...로컬 분기 생략...
    setDeletingItemId(itemId)
    fetch(/* ... */)
        .then(/* ... */)
        .finally(() => setDeletingItemId(null))
}, [api, deletingItemId, showToast, loadGroups])

// 렌더 부분 — 버튼 disabled 처리
<button onClick={createGroup} disabled={creating || !newName.trim()}>
    {creating ? "생성 중..." : "생성"}
</button>
```

Optimistic update 미도입 이유: CRIT-15 401 대응이 우선. 낙관적 업데이트는 별도 이슈(향후 WARNING).

---

### CRIT-17. portfolio.json fetch 실패 시 무한 "로딩 중..." UI — 성공/실패 구분 불가
**framer-components/StockDashboard.tsx > Line 268, 319~325 > [failure ≠ loading UX]**

**현상:**
```tsx
268:  fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
...
319:  if (!data) {
320:      return (
321:          <div style={...}>
322:              <span>데이터 로딩 중...</span>
323:          </div>
324:      )
325:  }
```
- `.catch(() => {})` — 실패를 **전부 삼킴**. 상태 변수에 에러 기록 없음.
- 사용자 화면은 `data === null` 이면 영원히 "로딩 중..."만 표시.
- 네트워크 불안, CORS 차단, 404 전부 동일 UX → 디버깅 거의 불가능.

동일 패턴이 `VerityBrainPanel` (`catch`에서 error state 없음), `WatchGroupsCard` (위 참조) 에도 존재.

**수정코드 (StockDashboard.tsx 기준):**
```tsx
const [data, setData] = useState<any>(null)
const [loadState, setLoadState] = useState<"loading" | "ok" | "error">("loading")
const [loadError, setLoadError] = useState<string>("")

useEffect(() => {
    if (!dataUrl) return
    const ac = new AbortController()
    setLoadState("loading")
    setLoadError("")
    fetchPortfolioJson(dataUrl, ac.signal)
        .then(d => {
            if (ac.signal.aborted) return
            setData(d)
            setLoadState("ok")
        })
        .catch(err => {
            if (ac.signal.aborted) return
            setLoadState("error")
            setLoadError((err && (err as Error).message) || "unknown")
        })
    return () => ac.abort()
}, [dataUrl])

// 렌더 상단
if (loadState === "error") {
    return (
        <div style={{ ...wrap, justifyContent: "center", alignItems: "center", minHeight: 500, flexDirection: "column", gap: 12 }}>
            <span style={{ color: "#FF4D4D", fontSize: 14, fontWeight: 700 }}>데이터 로드 실패</span>
            <span style={{ color: "#888", fontSize: 11 }}>{loadError}</span>
            <button
                onClick={() => { setLoadState("loading"); /* trigger re-fetch by bumping a nonce or re-calling effect */ }}
                style={{ marginTop: 8, background: "#B5FF19", color: "#000", border: "none", borderRadius: 8, padding: "8px 14px", fontWeight: 700, cursor: "pointer" }}
            >다시 시도</button>
        </div>
    )
}
if (!data || loadState === "loading") {
    return (
        <div style={{ ...wrap, justifyContent: "center", alignItems: "center", minHeight: 500 }}>
            <span style={{ color: "#555", fontSize: 14 }}>데이터 로딩 중...</span>
        </div>
    )
}
```

동일 패턴을 `VerityBrainPanel.tsx`에도 적용 권고 (fetch 호출부는 별도 코드 경로).

---

## 🟡 WARNING

### WARN-21. `toFixed` / `toLocaleString`의 NaN·undefined 노출
**framer-components/StockDashboard.tsx > Line 91, 92, 157, 158, 584~595, 708, 770, 881, 962, 984 > [화면에 "NaN" / "undefined" 문자열 표시]**

**현상:**
```tsx
584:  <MetricCard label="PER" value={stock.per?.toFixed(1) || "—"} />
585:  <MetricCard label="고점대비" value={`${stock.drop_from_high_pct?.toFixed(1)}%`}
587:  <MetricCard label="배당률" value={`${stock.div_yield?.toFixed(1)}%`} />
770:  {Number(val)?.toLocaleString()}
881:  <MetricCard label="MSPR" value={stock.insider_sentiment.mspr?.toFixed(4) || "0"} ... />
```

문제 케이스:
- `stock.per = NaN` → `NaN.toFixed(1)` → `"NaN"` (truthy string) → `|| "—"` 폴백 작동 안 함 → 화면에 "NaN" 노출.
- `stock.drop_from_high_pct` 미정의 → optional chain이 `undefined` 반환 → `${undefined}%` → `"undefined%"` 노출.
- `Number(val)` 가 NaN이면 `.toLocaleString()` 호출 가능하지만 결과가 `"NaN"`.

**수정코드 (공통 헬퍼 추가):**
```tsx
// StockDashboard.tsx 상단 헬퍼 섹션
function fmtFixed(n: any, digits: number = 1, suffix: string = ""): string {
    const x = typeof n === "number" ? n : Number(n)
    if (!Number.isFinite(x)) return "—"
    return `${x.toFixed(digits)}${suffix}`
}
function fmtLocale(n: any, suffix: string = ""): string {
    const x = typeof n === "number" ? n : Number(n)
    if (!Number.isFinite(x)) return "—"
    return `${x.toLocaleString()}${suffix}`
}
```

문제 라인 교체:
```tsx
// 91, 92
<span ...>H {usd ? `$${t.high}` : fmtLocale(t.high)}</span>
<span ...>L {usd ? `$${t.low}` : fmtLocale(t.low)}</span>

// 584~595
<MetricCard label="PER" value={fmtFixed(stock.per, 1)} />
<MetricCard label="고점대비" value={fmtFixed(stock.drop_from_high_pct, 1, "%")} />
<MetricCard label="배당률" value={fmtFixed(stock.div_yield, 1, "%")} />
<MetricCard label="부채비율" value={fmtFixed(stock.debt_ratio, 0, "%")} />
<MetricCard label="영업이익률" value={fmtFixed(stock.operating_margin != null ? stock.operating_margin * 100 : NaN, 1, "%")} />
<MetricCard label="ROE" value={fmtFixed(stock.roe != null ? stock.roe * 100 : NaN, 1, "%")} />

// 770
{Number.isFinite(Number(val)) ? Number(val).toLocaleString() : "—"}

// 881
<MetricCard label="MSPR" value={fmtFixed(stock.insider_sentiment?.mspr, 4)} ... />

// 962, 984
<MetricCard label="USD/KRW" value={`${fmtLocale(macro.usd_krw?.value)}원`} />
<MetricCard label="금" value={`$${fmtLocale(macro.gold?.value)}`} />
```

StockDetailPanel.tsx Line 840:
```tsx
// prevClose > 0 이지만 currentPrice가 NaN일 수 있음
{prevClose > 0 && Number.isFinite(changePct) && (
    <div style={...}>
        {changePct >= 0 ? "+" : ""}{fmtNum(changeAmt)}
        {" "}({changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%)
    </div>
)}
```

---

### WARN-22. SSE 재연결 로직 부재 — 5회 오류 후 영구 포기
**framer-components/StockDetailPanel.tsx > Line 634~638 > [일시적 장애가 영구 연결 끊김으로 이어짐]**

**현상:**
```tsx
634:  es.onerror = () => {
635:      errCount++
636:      setSseConnected(false)
637:      if (errCount > 5 && es) { es.close(); es = null }
638:  }
```
- 브라우저 EventSource는 기본적으로 재연결을 시도하지만, Railway가 5초 동안 재기동할 때 onerror 5회 쉽게 쌓임 → `es.close()` 호출 → 이후 **영구 정적 상태**.
- 사용자는 "연결 중..." 문구만 보고 새로고침 없이는 실시간 복구 불가.

**수정코드:** 지수 백오프 재연결 + max 재시도 상한.
```tsx
useEffect(() => {
    if (!relayUrl || !selectedStock) return
    const ticker = selectedStock.ticker.replace(/\D/g, "").padStart(6, "0")
    if (!ticker || ticker === "000000") return

    setSseConnected(false); setLiveOrderbook(null); setLiveTrades([]); setLiveStrength(0); setLiveCandles([])

    let es: EventSource | null = null
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    let retryCount = 0
    const MAX_RETRIES = 10

    const connect = () => {
        try {
            es = new EventSource(`${relayUrl}/stream/${ticker}`)
            es.onopen = () => { setSseConnected(true); retryCount = 0 }
            es.onerror = () => {
                setSseConnected(false)
                if (es) { es.close(); es = null }
                if (retryCount < MAX_RETRIES) {
                    const delayMs = Math.min(30_000, 1000 * Math.pow(2, retryCount))  // 1s, 2s, 4s, ... max 30s
                    retryCount++
                    retryTimer = setTimeout(connect, delayMs)
                }
            }
            // ... 기존 addEventListener 블록 그대로 ...
            es.addEventListener("snapshot", /* ... */)
            es.addEventListener("candles", /* ... */)
            es.addEventListener("candle", /* ... */)
            es.addEventListener("orderbook", /* ... */)
            es.addEventListener("trade", /* ... */)
        } catch {
            // EventSource 생성 자체 실패 시도 재시도
            if (retryCount < MAX_RETRIES) {
                const delayMs = Math.min(30_000, 1000 * Math.pow(2, retryCount))
                retryCount++
                retryTimer = setTimeout(connect, delayMs)
            }
        }
    }
    connect()

    return () => {
        if (retryTimer) clearTimeout(retryTimer)
        if (es) { es.close(); setSseConnected(false) }
    }
}, [relayUrl, selectedStock])
```

---

### WARN-23. `updated_at` 기반 stale 경고 표시 부재
**framer-components/VerityBrainPanel.tsx > Line 401 + StockDashboard.tsx > Line 1349 > [수일 전 데이터가 "현재"로 오도됨]**

**현상:**
```tsx
// VerityBrainPanel.tsx:401
{data.updated_at ? new Date(data.updated_at).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}
```
타임스탬프 문자열만 표시. GitHub Actions가 장애로 2~3일 멈춰 있어도 사용자는 "24시간 전 데이터"인지 "지금 막 갱신됨"인지 숫자를 직접 계산해야 알 수 있다.

**수정코드 (공통 헬퍼):**
```tsx
function stalenessInfo(updatedAt: string | undefined | null): { label: string; color: string; stale: boolean } {
    if (!updatedAt) return { label: "", color: "#666", stale: false }
    const t = new Date(updatedAt).getTime()
    if (!Number.isFinite(t)) return { label: "", color: "#666", stale: false }
    const hours = (Date.now() - t) / 3_600_000
    if (hours < 1) return { label: `방금 갱신 (${Math.round(hours * 60)}분 전)`, color: "#22C55E", stale: false }
    if (hours < 3) return { label: `${Math.round(hours)}시간 전`, color: "#B5FF19", stale: false }
    if (hours < 12) return { label: `${Math.round(hours)}시간 전`, color: "#FFD600", stale: false }
    if (hours < 24) return { label: `${Math.round(hours)}시간 전 (⚠️ stale 경계)`, color: "#F59E0B", stale: true }
    const days = hours / 24
    return { label: `${days.toFixed(1)}일 전 (⚠️ stale)`, color: "#FF4D4D", stale: true }
}
```

렌더 적용:
```tsx
// VerityBrainPanel.tsx:401 부근
{(() => {
    const s = stalenessInfo(data?.updated_at)
    if (!s.label) return null
    return (
        <span style={{ color: s.color, fontSize: 11, fontWeight: s.stale ? 700 : 500 }}>
            {s.label}
        </span>
    )
})()}
```

동일 헬퍼를 `StockDashboard.tsx`, `StockDetailPanel.tsx` 헤더에도 부착. stale 임계(기본 12h) 넘을 때 **빨간 배지**로 주의 유도.

---

### WARN-24. `fetchPortfolioJson` timeout 부재 — promise 영원히 pending 가능
**framer-components/fetchPortfolioJson.ts > Line 31~44 + StockDashboard.tsx 인라인 Line 21~32 > [네트워크 hang]**

**현상:** `fetch(url, { cache: "no-store", mode: "cors" })` 에 timeout 설정 없음. 느린 네트워크, 중간 CDN 장애 시 browser fetch는 **never resolve/reject**. UI 는 영원히 "로딩 중..." (CRIT-17 와 결합 시 심각).

**수정코드:**
```ts
// fetchPortfolioJson.ts
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000

export function bustPortfolioUrl(url: string): string { /* 기존 그대로 */ }

export const PORTFOLIO_FETCH_INIT: RequestInit = {
    cache: "no-store",
    mode: "cors",
    credentials: "omit",
}

function toBackupUrl(url: string): string {
    return url.replace(/portfolio\.json$/, "portfolio.json.bak")
}

function parsePortfolioText(txt: string): any {
    return JSON.parse(
        txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
    )
}

function withTimeout<T>(p: Promise<T>, ms: number, ac: AbortController): Promise<T> {
    const timer = setTimeout(() => ac.abort(), ms)
    return p.finally(() => clearTimeout(timer))
}

function fetchRaw(url: string, externalSignal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    // 외부 signal abort 시 내부 ac 도 abort
    if (externalSignal) {
        if (externalSignal.aborted) ac.abort()
        else externalSignal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    const init: RequestInit = { ...PORTFOLIO_FETCH_INIT, signal: ac.signal }
    return withTimeout(
        fetch(bustPortfolioUrl(url), init).then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.text()
        }).then(parsePortfolioText),
        PORTFOLIO_FETCH_TIMEOUT_MS,
        ac,
    )
}

export function fetchPortfolioJson(url: string, externalSignal?: AbortSignal): Promise<any> {
    return fetchRaw(url, externalSignal).catch(() => {
        const backup = toBackupUrl(url)
        if (backup === url) throw new Error("no backup available")
        return fetchRaw(backup, externalSignal)
    })
}
```

`StockDashboard.tsx`, `VerityBrainPanel.tsx`, `WatchGroupsCard.tsx` 의 **인라인 복제본**에도 동일 timeout 로직 반영 필요 (Framer 단일 파일 제한 때문에 각자 복사본).

---

## 🟢 INFO

### INFO-17. VerityBrainPanel NaN 방어 정상
**framer-components/VerityBrainPanel.tsx > Line 45, 247 > [확인됨]**

`if (raw == null || Number.isNaN(Number(raw))) return null` + `avgVci = (_rawVci != null && !Number.isNaN(Number(_rawVci))) ? Number(_rawVci) : 0` — 두 지점에서 명시적 NaN 가드. ✅

### INFO-18. StockDetailPanel fmtKRW/fmtNum/fmtVol 안전
**framer-components/StockDetailPanel.tsx > Line 59~75 > [확인됨]**

세 함수 모두 `Number.isFinite(n)` 체크 후 "—" 폴백. ✅ (단 Line 840 `changePct.toFixed(2)` 는 직접 호출 — WARN-21에 포함)

### INFO-19. LineChart 빈/단일 데이터 폴백
**framer-components/StockDetailPanel.tsx > Line 90 + StockDashboard.tsx > Line 56 > [확인됨]**

- StockDetailPanel.tsx:90 : `data.length < 2` 시 "차트 데이터 없음" 표시 ✅
- StockDashboard.tsx:56 : Sparkline `return null` ✅

### INFO-20. SSE useEffect cleanup 정상
**framer-components/StockDetailPanel.tsx > Line 707 > [확인됨]**

`return () => { if (es) { es.close(); setSseConnected(false) } }` — 언마운트 시 연결 해제. 메모리 누수 없음. ✅ (단 재연결은 WARN-22 참조)

### INFO-21. Optimistic update 미사용 — 롤백 버그 없음
**framer-components/WatchGroupsCard.tsx > 전역 > [확인됨]**

모든 CRUD가 server-first, reload-after — 즉각 반영되지 않아 UX는 약간 느리지만 **optimistic/rollback 경로가 없으므로 관련 버그도 없다**. ✅ (개선 여지 O, 현재 동작 정확)

---

## 요약 (심각도순)

| # | 파일 | Line | 유형 | 영향 |
|---|---|---|---|---|
| 🔴 CRIT-15 | WatchGroupsCard.tsx | 139, 284, 303, 322, 348 | 회귀 | JWT 미전송 — 전 CRUD 401 |
| 🔴 CRIT-16 | WatchGroupsCard.tsx | 282, 295, 314, 340 | 동시성 | 빠른 클릭 → 중복 생성/삭제 |
| 🔴 CRIT-17 | StockDashboard.tsx + VerityBrainPanel.tsx | 268, 319 | UX | fetch 실패 = 무한 로딩 |
| 🟡 WARN-21 | StockDashboard.tsx | 584~595, 770, 881, 962, 984 | 렌더 | NaN/undefined 문자열 노출 |
| 🟡 WARN-22 | StockDetailPanel.tsx | 634~638 | 재연결 | SSE 5회 오류 후 영구 끊김 |
| 🟡 WARN-23 | VerityBrainPanel.tsx, StockDashboard.tsx | 401, 1349 | UX | stale 데이터 무경고 |
| 🟡 WARN-24 | fetchPortfolioJson.ts + 3개 인라인 | 31~44 | 네트워크 | timeout 없음 → 무한 pending |
| 🟢 INFO-17 | VerityBrainPanel.tsx | 45, 247 | 확인 | NaN 가드 정상 |
| 🟢 INFO-18 | StockDetailPanel.tsx | 59~75 | 확인 | 숫자 포매터 안전 |
| 🟢 INFO-19 | StockDashboard.tsx, StockDetailPanel.tsx | 56, 90 | 확인 | 빈 차트 폴백 |
| 🟢 INFO-20 | StockDetailPanel.tsx | 707 | 확인 | SSE cleanup 정상 |
| 🟢 INFO-21 | WatchGroupsCard.tsx | 전역 | 확인 | optimistic 미사용 |

---

## 검수 원칙 기준 제외 항목
- **TASK 4 음수 수익률 색상 로직**: 모든 곳에서 `>= 0 ? "#22C55E" : "#EF4444"` 또는 `UP/DOWN` 상수 사용. 음수/양수 구분 정확. 이슈 없음.
- **TASK 3 메모리 누수**: useEffect cleanup 에서 `es.close()` 호출 + AbortController abort 호출. 누수 경로 없음. INFO-20 참조.
- **TASK 4 차트 단일 포인트 처리**: `data.length < 2` 명시 체크. 이슈 없음.
- **CRIT-15 관련 watchGroupsClient.ts**: 해당 파일은 SESSION 3에서 이미 수정되었으며 정상 동작. 문제는 **WatchGroupsCard.tsx가 이 클라이언트를 import하지 않고 fetch를 인라인으로 재구현한 것**. SESSION 3 수정 당시 컴포넌트 파일이 코드 재작성 누락됨.

# VERITY Design System

**작성 시점**: 2026-05-30 (PM 결단 brand 라임 → TIDE 초록 후)
**SoT (Source-of-Truth)**: `framer-components/pages/_shared/AuthPage.tsx` (5/30 refactor 후, Framer codeFile `zOAAs1J`)
**용도**: VERITY frontend 신 컴포넌트 spec / 기존 38 component migrate baseline
**관련**: `docs/design_system_tide.md` (TIDE 정합 구조 share), [[project_verity_brand_change_2026_05_30]]

---

## ⚠ 핵심 룰

- **3색 strict** = 흑 + 백 (gray scale) + TIDE 초록 `#7fffa0` (accent). 다른 색 사용 금지
- **이모지 X** (UI 영역). 채팅 / commit prefix 만 예외 ([[feedback_no_emoji_in_chat]])
- **좌측 vertical strip / colored border-left X** (TIDE 정합)
- **card-level border / shadow X** (TIDE flat shell)
- **horizontal border 채택** (sections / rows 사이) — `1px solid rgba(255,255,255,0.06)` 반투명
- **Lora serif** = hero metric / VERITY logo 만, body 텍스트 X

---

## ⚠ RULE 7 정합 — "가설 (N=X)" 명시 의무

VERITY = 1인 베타 운영 60일째 (4/1~). VAMS reset 후 N=14 trail. 통계 무의미 영역.

site 자기 산식 노출 시:
- **"가설 (N=X일)"** 라벨 의무
- **hit rate** site 노출 시 = expectancy + sample size + CI 병기 의무
- **Tier 진화 path UI** = 자본 path 추정 금지, 성숙도 primary
- **N<30** = "통계 무의미" 명시
- **N<100** = "예비 결과, 검증 진행 중" 명시
- **자기 산식 임계 조정** = ≤ 1회/산식, 사전 PM 승인 commit message WHY/DATA/EXPECTED ([[feedback_pm_decision_trail_in_commit]])

상세 = CLAUDE.md RULE 7 + [[feedback_methodology_pre_registration]]

---

## 색상 palette (3색 strict)

### 흑 — 배경

| 토큰 | Hex | 용도 |
|---|---|---|
| `bgPrimary` | `#0a0a0a` | primary 배경 (pure black, container) |
| `bgElevated` | `#141414` | elevated (tab inactive, chip background) |
| `bgSubtle` | `rgba(255,255,255,0.02)` | section sub-background (희소 사용) |

### 백 — 텍스트 (gray scale)

| 토큰 | Hex | 용도 |
|---|---|---|
| `textPrimary` | `#ffffff` | 강조 텍스트, value |
| `textSecondary` | `#A8ABB2` | secondary text, mini info |
| `textTertiary` | `#6B6E76` | label, timestamp, ADMIN ONLY |
| `textDisabled` | `#4A4C52` | disabled |

### 초록 — Accent (VERITY brand, TIDE share)

| 토큰 | Hex | 용도 |
|---|---|---|
| `accent` | `#7fffa0` | VERITY brand (CTA, focus, status, error/success border) |

### Border / Divider

| 토큰 | 값 | 용도 |
|---|---|---|
| `divider` | `rgba(255,255,255,0.06)` | section / row 사이 |
| `border` | `rgba(255,255,255,0.06)` | container / input outline |

### 폐기 (이전 palette, 5/30 brand change 후)

- 라임 `#B5FF17` (VERITY 이전 brand)
- `#22C55E` success, `#FFD600` warn, `#FFA05A` caution, `#FF5A5A` danger
- `accentSoft`, `borderStrong`

---

## Typography

### 폰트 stack

```css
fontFamily: "'Pretendard', 'Inter', -apple-system, sans-serif"  /* body */
fontFamily: "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"  /* mono (숫자, code id) */
fontFamily: "'Lora', serif"  /* big number, hero metric, VERITY logo */
fontVariantNumeric: "tabular-nums"  /* mono / 숫자 영역 의무 */
```

### 크기 + weight

| 크기 | weight | 용도 |
|---|---|---|
| 11 | 600 | **label** uppercase + letterSpacing 0.04em |
| 12-13 | 400-600 | body / value (input, row) |
| 14 | 600 | title (section 또는 component header) |
| 16-22 | 600-700 | secondary hero (이름 / VERITY 인접) |
| 28 | 700 | VERITY logo (Pretendard, letterSpacing -0.5) |
| 32-56 | 600-700 | big number (drill-down hero metric, Lora serif, lineHeight 1.1) |

---

## Spacing

- container `padding: 24` 또는 `padding: "24px 24px"`
- section 사이 `marginTop: 20-24, paddingBottom: 16, borderBottom: divider`
- row `padding: "6px 0"` 또는 `padding: "4px 0"`
- block (sub-card) `padding: 10-12` + `gap: 8-12`
- gap (flex / grid) = `8` (small) / `12` (medium) / `20` (large)

### borderRadius

- `4` — small (input, chip, button, alert)
- `8` — container (card, top bar)
- `>12` 금지 (TIDE 정합 anti-pattern)
- pill `999` = 사용 X (badge 도 4 통일)

### border + radius 함께

- container = `border: "1px solid rgba(255,255,255,0.06)"` + `borderRadius: 8`
- input = `border: "1px solid rgba(255,255,255,0.06)"` + `borderRadius: 4` + `background: transparent`
- button = `borderRadius: 4`

---

## 패턴

### 1. Row — label + value (좌우 양분)

```tsx
<div style={{
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "6px 0",
    fontSize: 13,
}}>
    <span style={{ color: "#A8ABB2" }}>label</span>
    <span style={{
        color: "#ffffff",
        fontWeight: 600,
        fontFamily: FONT_MONO,
        fontVariantNumeric: "tabular-nums",
    }}>
        value
    </span>
</div>
```

### 2. Label uppercase (모든 section header)

```tsx
const labelStyle = {
    fontSize: 11,
    color: "#6B6E76",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    fontFamily: FONT,
    fontWeight: 600,
}
```

### 3. Section — title + horizontal border 아래

```tsx
<div style={{
    paddingTop: 20,
    paddingBottom: 16,
    borderBottom: "1px solid rgba(255,255,255,0.06)",
}}>
    <div style={labelStyle}>SECTION TITLE</div>
    {/* content */}
</div>
```

### 4. Status indicator dot

```tsx
<div style={{ display: "flex", alignItems: "center", gap: 6 }}>
    <span style={{
        width: 6, height: 6, borderRadius: "50%",
        background: "#7fffa0",
    }} />
    <span style={{ ...labelStyle, color: "#A8ABB2" }}>STATUS</span>
</div>
```

### 5. Tab toggle (active / inactive)

```tsx
<div style={{ display: "flex", gap: 8 }}>
    {(["login", "signup"] as const).map((m) => {
        const active = mode === m
        return (
            <button key={m} style={{
                flex: 1, border: "none", padding: "8px 0",
                background: active ? "#ffffff" : "#141414",
                color: active ? "#0a0a0a" : "#ffffff",
                fontSize: 12, fontWeight: 600,
                borderRadius: 4, cursor: "pointer",
            }}>
                {m}
            </button>
        )
    })}
</div>
```

### 6. Alert (error / success) — border + 텍스트 prefix

```tsx
{error && (
    <div style={{
        padding: "8px 12px", borderRadius: 4,
        border: "1px solid #7fffa0",
    }}>
        <span style={{ color: "#ffffff", fontSize: 12 }}>
            <span style={{ ...labelStyle, marginRight: 6, color: "#7fffa0" }}>오류</span>
            {error}
        </span>
    </div>
)}
```

### 7. Primary CTA button

```tsx
<button style={{
    width: "100%", padding: "12px 0",
    borderRadius: 4, border: "none",
    background: "#7fffa0", color: "#0a0a0a",
    fontSize: 13, fontWeight: 700, fontFamily: FONT,
    letterSpacing: "0.04em", textTransform: "uppercase",
}}>
    EXECUTE
</button>
```

### 8. Input (transparent + border)

```tsx
<input style={{
    width: "100%", padding: "10px 12px", borderRadius: 4,
    border: "1px solid rgba(255,255,255,0.06)",
    background: "transparent",
    color: "#ffffff", fontSize: 13,
    outline: "none", boxSizing: "border-box",
}} />
```

### 9. Loading / Error placeholder

```tsx
{!data && <div style={loadingStyle}>loading...</div>}
{error && <div style={errorStyle}>error: {error}</div>}

const loadingStyle = { color: "#6B6E76", padding: 16, fontSize: 13 }
const errorStyle = { color: "#7fffa0", padding: 16, fontSize: 13 }
```

### 10. VERITY hero logo (28px Pretendard, accent color)

```tsx
<div style={{
    color: "#7fffa0",
    fontSize: 28,
    fontWeight: 700,
    fontFamily: FONT,
    letterSpacing: -0.5,
}}>
    VERITY
</div>
<div style={{ ...labelStyle, marginTop: 4 }}>
    OPERATOR CONSOLE
</div>
```

---

## Anti-pattern (사용 금지)

- 좌측 vertical strip / colored border-left (이전 패턴, TIDE 정합 폐기)
- 색 wash background (severity 영역 등) — flat 배경 채택
- card-level shadow
- 이모지 string (🌗 🟢 🔴 등) — text-only label 채택 (SECURE / ADMIN / WARN)
- 큰 borderRadius (>12px) — 작은 채택 (4, 8)
- gradient (어디서든)
- 큰 padding (>32px) — 16~24 채택
- bold large body text — number 영역 = Lora serif 차별
- 4색+ palette (3색 strict 의무)
- 모던 ES2021+ syntax — numeric separator `100_000_000`, optional chaining `?.` 일부, nullish coalescing `??` 일부 — Framer esbuild panic 위험 ([[feedback_framer_esbuild_modern_syntax_panic]])
- `as const` 과다 사용 — 최소화 (esbuild 안정)
- success/danger color (`#22C55E`, `#FF5A5A` 등) — `accent` (`#7fffa0`) + 텍스트 prefix 로 semantic 표현

---

## Reference 컴포넌트

- `framer-components/pages/_shared/AuthPage.tsx` — VERITY auth (5/30 refactor 후, Framer codeFile `zOAAs1J`)
- `framer-components/arena/ArenaTradeTurn.tsx` — ARENA mockup (Framer codeFile `xjJUSv8`)

---

## 38 component migrate plan (별 sprint, 6월 진입)

VERITY Framer 39 code components 중 1 (AuthPage) 완료. 잔존 38 components migrate 의무 ([[project_verity_brand_change_2026_05_30]] 정합):

| Step | 작업 | 도구 |
|---|---|---|
| 1 | Framer ColorStyle `/VERITY` rgb 변경 | MCP `manageColorStyle` (rgb(181,255,23) → rgb(127,255,160)) |
| 2 | 각 code component `C.accent` hex 변경 | grep `#B5FF17` → `#7fffa0` (local + Framer) |
| 3 | local mirror sync | `framer-components/` 전수 검사 |
| 4 | decorative simplify (선택) | success/danger/warn/caution 색 검토 + 3색 strict 정합 변경 |
| 5 | commit chain | components 그룹별 (admin / market / portfolio 등) 분리 commit |

**변경 의무 룰:**
- 변경 ≤ 1회 ([[feedback_methodology_pre_registration]] 정합)
- 각 component PR 단위 = WHY/DATA/EXPECTED 3요소 ([[feedback_pm_decision_trail_in_commit]])
- 박- self-check 0 매치 (RULE 9)
- typecheck PASS 의무 (esbuild panic 회피)

---

## 관련 메모리

- [[project_verity_brand_change_2026_05_30]] — brand 라임 → TIDE 초록 변경 PM 결단 trail
- [[project_tide_design_system_2026_05_27]] — TIDE design system SoT (구조 share)
- [[project_solo_economy_terminal_frame_2026_05_30]] — 4-site ecosystem frame
- [[feedback_framer_esbuild_modern_syntax_panic]] — Framer esbuild 보수적 syntax 의무
- [[feedback_methodology_pre_registration]] — RULE 7 사전 등록 path
- [[feedback_pm_decision_trail_in_commit]] — PM 결단 commit WHY/DATA/EXPECTED 의무
- [[feedback_no_emoji_in_chat]] — 이모지 사용 룰
- CLAUDE.md RULE 7 — "가설 (N=X)" 명시 의무
- CLAUDE.md RULE 9 — 글쓰기 규율 (박- 회피)

# VERITY TIDE Design System — 신 컴포넌트 spec prompt

**박은 시점**: 2026-05-27 (BrainGradeBreakdown.tsx codeFile OUAKBZw 박은 본문 audit 추출).
**SoT (Source-of-Truth)**: Framer canvas codeFile `OUAKBZw` (BrainGradeBreakdown.tsx).
**용도**: 신 Framer 컴포넌트 박을 때 매번 TIDE MCP 박기 힘들어 spec prompt 박음 (사용자 5/27 명시).

---

## ⚠ 룰

- **이모지 박지 X** (UI 박은 부분, 채팅 / commit prefix 박은 부분 예외 — [[feedback_no_emoji_in_chat]] 정합)
- **좌측 strip / vertical bar 박지 X** (BrainGradeBreakdown 박은 부분 부재)
- **card-level border / shadow 박지 X** (TIDE = flat shell)
- **horizontal border 박음** (sections / rows 박은 사이) — `1px solid rgba(255,255,255,0.06)` 반투명
- **이모지 박는 string field (예: one_liner) 박은 부분 = 사용자 결정 의무** (백엔드 박은 부분 prefix 박지 X, UI 박은 부분 박지 X)

---

## 색상 palette

### 배경
- `#0a0a0a` — primary 배경 (pure black, container 박은 부분)
- `#141414` — elevated (input / select / tooltip 박은 부분)
- `rgba(255,255,255,0.02)` — block / section 박은 sub-background (block 박은 부분)
- `rgba(0,0,0,0.2)` — reasons 박은 부분 inner background

### 텍스트
- `#ffffff` — primary text (강조 박은 부분)
- `#F2F3F5` — primary text (Pretendard 박은 부분, 약간 부드러움)
- `#A8ABB2` — secondary text (mini info, miniStyle)
- `#6B6E76` — tertiary text (label, timestamp)
- `#4A4C52` — disabled

### Accent (grade / score)
- `#7fffa0` — BUY / 강세 / score ≥ 60
- `#22C55E` — GREEN severity / success
- `#FFD600` — YELLOW severity / warning
- `#FFA05A` — HOLD / CAUTION / score 40~60
- `#EF4444` / `#FF5A5A` — AVOID / RED severity / score < 40 / error
- `#84A59D` — contrarian / sentiment (회녹)
- `#2A4F37` — bonus (진녹)
- `#5BA9FF` — info / link (SHA / 파란 강조)

### 구분선
- `1px solid rgba(255,255,255,0.06)` — section / row 사이 (가장 반투명)
- `1px solid rgba(255,255,255,0.04)` — subtle (one-liner 박은 부분 아래)
- `1px solid #23242C` — strong border (block 박은 부분 박은 외곽)
- `1px solid #34353D` — borderStrong (tooltip 박은 외곽)

---

## Typography

### 폰트 stack
```css
fontFamily: "'Pretendard', 'Inter', -apple-system, sans-serif"  /* body */
fontFamily: "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"  /* mono 박은 부분 */
fontFamily: "'Lora', serif"  /* big number, hero metric */
fontVariantNumeric: "tabular-nums"  /* mono 박은 부분 의무 */
```

### 크기 + weight
- `fontSize: 11, color: "#6B6E76", textTransform: "uppercase", letterSpacing: "0.04em"` — **label** (모든 영역 label 박은 부분)
- `fontSize: 13, fontWeight: 600` — number / 값
- `fontSize: 14, fontWeight: 600` — title (Operator Cockpit 등)
- `fontSize: 32~56, fontFamily: Lora, fontWeight: 600~700, lineHeight: 1.1` — **big number** (hero metric)
- `fontSize: 11, color: "#A8ABB2"` — mini text (info, miniStyle)
- `fontSize: 12` — body text

---

## Spacing

- container `padding: 24` (BrainGradeBreakdown 박은 부분) 또는 `padding: "16px 24px"` (Bar 박은 부분 슬림)
- section 사이 `marginTop: 20, paddingBottom: 16, borderBottom: <subtle>`
- row 박은 부분 `padding: "6px 0"` 또는 `padding: "4px 0"`
- block (sub-card) `padding: 10` + `gap: 12`
- gap (flex / grid) = `8` (small) / `12` (medium) / `20` (large)

### borderRadius (TIDE 정합 — 2026-05-28 박음)
- `2` — bar segment (Score Composition 박은 가로 bar)
- `4` — small inner element (tooltip / icDead / select 박은 input)
- `8` — container card / top bar (모서리 박음 의무, 박지 X = anti-pattern)
- 박지 X — `>12` (TIDE 박은 부분 부재)

### border + radius 박은 부분 함께 박음
- container = `border: "1px solid rgba(255,255,255,0.06)"` + `borderRadius: 8`
- container 박은 full-width 박은 부분도 모서리 박음 (단순 borderBottom 박지 X)
- error / loading 박은 placeholder = container 박은 부분 정합 (radius + border)

---

## 패턴

### 1. Bar — 가로 segment (Score Composition 박은 부분)
```tsx
<div style={{ display: "flex", marginTop: 8, gap: 2 }}>
    <Bar label="fact" value={data.fact_contribution} color="#7fffa0" />
    <Bar label="sent" value={data.sentiment_contribution} color="#84a59d" />
</div>

function Bar({ label, value, color }) {
    return (
        <div style={{
            flex: value,
            background: color,
            height: 24,
            borderRadius: 2,
            color: "#0a0a0a",
            fontSize: 11,
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            whiteSpace: "nowrap",
            overflow: "hidden",
        }}>
            {label} {value.toFixed(1)}
        </div>
    )
}
```

### 2. Row — label + value (좌우 양분)
```tsx
<div style={{
    display: "flex",
    justifyContent: "space-between",
    fontSize: 13,
    padding: "6px 0",
}}>
    <span style={{ color: isDead ? "#6b7280" : "#ffffff", textDecoration: isDead ? "line-through" : "none" }}>
        {component.name}
    </span>
    <span style={{ color: scoreColor(component.score), fontWeight: 600 }}>
        {Math.round(component.score)}
    </span>
</div>
```

### 3. Label + Number (큰 숫자 박은 부분)
```tsx
<div>
    <div style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.04em" }}>
        BRAIN SCORE
    </div>
    <div style={{
        fontSize: 56,
        fontFamily: "Lora, serif",
        fontWeight: 600,
        lineHeight: 1.1,
        marginTop: 4,
        color: gradeColor,
    }}>
        {Math.round(data.brain_score)}
    </div>
    <div style={{ fontSize: 14, color: gradeColor, marginTop: 4 }}>
        {data.grade} · {data.grade_label}
    </div>
</div>
```

### 4. Section — title + horizontal border 아래
```tsx
<div style={{
    marginTop: 20,
    paddingBottom: 16,
    borderBottom: "1px solid rgba(255,255,255,0.06)",
}}>
    <div style={{ ...labelStyle, marginBottom: 8 }}>
        Fact Score: {Math.round(data.fact_score)}
    </div>
    {/* rows ... */}
</div>
```

### 5. Footer — 가설 / 면책 박은 부분
```tsx
<div style={{
    marginTop: 24,
    paddingTop: 16,
    borderTop: "1px solid rgba(255,255,255,0.06)",
    fontSize: 11,
    color: "#6b7280",
    lineHeight: 1.6,
}}>
    가설 단계 (Phase 0 N={phaseDays}/{phaseTarget}일 · 표본 {phaseSample}건 · VAMS reset {vamsResetShort} 후 {vamsDays}일)
    <br />
    Bailey-Lopez de Prado N≥252 (2027-05) 도달 전 통계 무의미
</div>
```

### 6. Score → Color (component grade)
```tsx
color: c.score >= 60 ? "#7fffa0" : c.score >= 40 ? "#ffa05a" : "#ff5a5a"
```

### 7. Loading / Error
```tsx
{!data && <div style={loadingStyle}>loading {selected}...</div>}
{error && <div style={errorStyle}>error: {error}</div>}

const loadingStyle: React.CSSProperties = {
    color: "#6b7280", padding: 16, fontSize: 13,
}
const errorStyle: React.CSSProperties = {
    color: "#ff5a5a", padding: 16, fontSize: 13,
}
```

---

## 박지 X (anti-pattern)

- 좌측 vertical strip / colored border-left (이모지 박는 부분 = 옛 패턴 박지 X)
- background tint 박은 severity 박은 부분 (sevBg = `rgba(34,197,94,0.08)` 류) — flat 배경 박음
- card-level shadow 박은 부분
- 이모지 string 박은 (🌗 🟢 🔴 등) — text-only severity label 박음 (GREEN / YELLOW / RED)
- 곡선 박은 큰 border-radius (>8px) — 작은 박음 (2~6)
- gradient 박은 부분
- 큰 padding (>32px) — 16~24 박음
- bold 박은 large body text — number 박은 부분 Lora serif 박은 부분 차별

---

## 박은 reference 컴포넌트

- `framer-components/pages/analysis/BrainGradeBreakdown.tsx` (로컬 mirror)
- Framer canvas codeFile `OUAKBZw` — SoT

---

## 박는 absent design

다음 신 컴포넌트 박을 때 본 spec 박은 부분 follow 의무:
- OperatorCockpitBar (Phase 1 P1-a, 5/27 재설계 대상)
- OperatorCockpitCard (Phase 1 P1-b, 5/27 재설계 대상)
- 향후 신 Framer code component 박음 시

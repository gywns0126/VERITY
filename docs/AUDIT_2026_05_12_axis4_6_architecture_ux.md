# Audit Sprint #4+#6 — 아키텍처 + Frontend/UX sweep (마지막 갈래)

**일자**: 2026-05-12
**범위**: 컴포넌트 overlap / builder overlap / import cycle / workflow overlap / 펜타그램 / Framer 룰
**결과**: 3건 (HIGH 1, MED 2)

---

## 결함 요약

| # | Risk | Axis | File:Line | Drift | Fix |
|---|---|---|---|---|---|
| 1 | **HIGH** | 6 (Framer 룰) | `estate/components/pages/residential/EstateBrainPanel.tsx:700,704,730` | scenario 가 props 전용. GuSelector 패턴 미적용. 사용자가 scenario 바꾸려면 Framer 편집창 열어야 함 | 5/17 queue |
| 2 | MED | 5 (펜타그램) | `estate/components/pages/_shared/SubscriptionCalendar.tsx:295,468` | `opacity: 0.7 / 0.5` 사용 — picture_book 룰 위반 (불투명도 조절 금지, 톤 차이만) | 5/17 queue |
| 3 | MED | 5 (펜타그램) | `estate/components/pages/_shared/PolicyPulse.tsx:533,733` | 동일 opacity 패턴 | 5/17 queue |

**총 3건** (HIGH 1, MED 2)

---

## 검사 6축 결과

| Axis | 상태 | 비고 |
|---|---|---|
| #4-1 Component overlap | 검사함, 결함 0 | SystemHealthBar vs EstateSystemHealthBar 도메인 분리 OK. PolicyPulse가 3 컴포넌트 통합 완료 |
| #4-2 Builder/endpoint overlap | 검사함, 결함 0 | builder-endpoint 1:1 매핑 정합 |
| #4-3 Import cycle | 검사함 (sample), 결함 0 | api/builders 순환 없음 |
| #4-4 Workflow overlap | 검사함, 결함 0 | 동일 data/ write 다중 cron 없음 (이전 sweep에서 정정 완료) |
| #6-1 펜타그램 | **결함 2건** | opacity 사용 잔존 (위 표) |
| #6-2 Framer 룰 | **결함 1건** | EstateBrainPanel scenario in-component selector 부재 |

---

## Drift 상세

### Rule (HIGH 1): EstateBrainPanel scenario selector 부재

메모리 `feedback_in_component_interactivity`: "운영 중 가변값(구/scenario/필터)은 props 만 두지 말고 컴포넌트 내부 셀렉터로. 매 변경 편집창 왕복 = 사이트 의미 없음"

**현황**:
- `GuSelector` 구현됨 (line 614~700, URL 동기화) ✓
- `scenario` (live / mock_balanced / mock_high_pir / mock_redev_uplift) 는 props 전용 (line 700, 704, 730)

**Impact**: 사용자가 scenario 바꾸려면 Framer 편집창 → republish. 메모리 명시한 "사이트 의미 없음" 결함 그대로.

**Fix**: GuSelector 패턴 차용해 `ScenarioSelector` 추가. URL param 동기화 (`?scenario=...`).

### Rule (MED 2): opacity 사용 (picture_book 룰 위반)

메모리 `feedback_picture_book_principle` + `project_pentagram_full_pass` (5/6 완료): hex alpha 폐기, 불투명도 조절 금지. 배경 톤 차이만 사용.

**SubscriptionCalendar.tsx:295,468** + **PolicyPulse.tsx:533,733** 각 2건 — `opacity: 0.7` (color bar), `opacity: 0.5` (skeleton).

**Root cause**: 5/6 30 컴포넌트 펜타그램 완료 후 신규 추가된 컴포넌트(SubscriptionCalendar v0.1, PolicyPulse 5/12 통합)에 룰 부분 누락.

**Fix**: `C.accentSoft` 또는 `C.bgElevated` 직접 사용 (토큰 시스템 정합).

---

## False positive 정정

Agent가 추가 LOW 결함 (LandexPulse tooltip position:fixed 등)을 표시했으나, 동적 계산된 `pos.top/left` 사용은 메모리 `feedback_no_hardcode_position` 의 "사용자 직접 배치" 룰과 위반 X (사용자가 *컴포넌트 자체*는 Framer 캔버스에서 배치, tooltip은 hover 시 동적). 결함 list 제외.

---

## Fix 분류

### 5/17 sprint queue
- **HIGH 1**: EstateBrainPanel ScenarioSelector 추가 (GuSelector 패턴, URL 동기화)
- **MED 2**: SubscriptionCalendar + PolicyPulse opacity → 토큰 교체 (4 라인)

### 권장
HIGH 1건만 fix해도 운영 UX 결정적으로 개선. MED 2건은 시각적 일관성 미세조정.

---

## 6갈래 audit sprint 종합 (별도 summary docs 후속)

`docs/AUDIT_2026_05_12_summary.md` 박을 예정.

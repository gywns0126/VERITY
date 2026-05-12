# Audit Sprint #1 — 시스템 정합성 sweep (메모리 룰 vs 코드 drift)

**일자**: 2026-05-12
**범위**: 10개 메모리 룰 검증
**결과**: 8 정합 / 2 drift / 2 skip (framer estate 범위)

---

## 결함 요약

| # | Risk | Rule | File:Line | Drift | Root Cause | Fix |
|---|---|---|---|---|---|---|
| 1 | **HIGH** | 5 (sector aware) | `api/intelligence/verity_brain.py:1631` | `kis_debt > 300` 하드 floor, 금융주 면제 미적용 | 5/10 helper 생성 후 기존 하드코드 정정 미완 | 5/17 queue |
| 2 | **HIGH** | 5 (sector aware) | `api/analyzers/safe_picks.py:30,46,48` | `debt_ratio > 100/60/50` 단순 분기, `sector_thresholds` helper 미호출. 금융주 자동 탈락 회귀 위험 | 동일 — 일괄 패치 미완 | 5/17 queue |
| 3 | MED | 6 (AI sanitization) | `api/analyzers/gemini_analyst.py:953` | `"ai_verdict": f"AI 분석 오류: {str(e)[:50]}"` 사용자 노출 필드에 raw 에러 | 5/3 메모리 후 부분 누락 | 5/17 queue |
| 4 | MED | 6 (AI sanitization) | `api/analyzers/postmortem.py:334` | 동일 패턴 raw `str(e)` 노출 | 동일 | 5/17 queue |
| 5 | LOW | 2 (R-Multiple) | `vercel-api/api/stock.py:418` | `target_price = min(bb_upper, ma20 * 1.12)` UI 참고값, "자동 액션 X" 명시 | 의도된 잔존 (설계 OK) — 메모리 룰과 literal drift만 | 관찰 |

**총 5건** (HIGH 2, MED 2, LOW 1)

---

## 정합 8 룰 (검사 OK)

| Rule | 메모리 | 상태 |
|---|---|---|
| 1 | ATR Phase 0 (`project_atr_phase0_migration`) | ✓ `ATR_METHOD="wilder_ema_14"` config + secret 분기 정합. 5/3 박힘, 5/16 verdict 대기 |
| 2 | R-Multiple Exit (`project_r_multiple_exit`) | ✓ VAMS 코어 `check_partial_exit` + `execute_partial_sell` 구현 / `exit_targets`/`trailing_active` 영속 OK / 단 vercel-api 레거시 잔존 (LOW) |
| 3 | ATR 동적 손절 (`project_atr_dynamic_stop`) | ✓ `ATR_STOP_MULTIPLIER=2.5` + holding `stop_loss_pct_individual` 영속 |
| 4 | Brain v5 임계값 (`project_brain_v5_self_attribution`) | ✓ fact=0.70/sentiment=0.30, STRONG_BUY 75/BUY 60/WATCH 45/CAUTION 30 |
| 7 | MDD magnitude (`feedback_mdd_magnitude_display`) | ✓ VAMSProfilePanel + ValidationPanel `Math.abs` 사용 |
| 8 | Source attribution (`feedback_source_attribution_discipline`) | ✓ verity_brain.py 헤더 "30권 투자 고전 통합" 출처 명시 |
| 9 | No hardcode position (framer) | SKIP (estate 범위 제외 명시) |
| 10 | In-component interactivity | SKIP (estate 범위 제외) |

---

## Drift 상세

### Rule 5 — Sector aware thresholds (HIGH 2건)

메모리 `feedback_sector_aware_thresholds`: "부채비율 등 섹터 의존 임계는 `sector_thresholds` 헬퍼 사용. 단일 임계 분기 금지 (금융주 오분류)"

**Drift 1**: `api/intelligence/verity_brain.py:1631~1634`
```python
if kis_debt > 300:
    auto_avoid_d.append(_make_flag(f"부채비율 {kis_debt:.0f}% (KIS 기준)"))
elif kis_debt > 200:
    downgrade_d.append(_make_flag(f"고부채 {kis_debt:.0f}% (KIS 기준)"))
```
→ 금융주 D/E는 200~1,000% 정상 범위. 300% 단일 floor 적용 시 은행/보험사 자동 AVOID 회귀.

**Drift 2**: `api/analyzers/safe_picks.py:30,46,48`
```python
if debt_ratio > 100: continue       # line 30 — 금융주 일괄 탈락
elif div_yield >= 4 and debt_ratio < 50 and op_margin > 10: safety_tier = "S"   # line 46
elif div_yield < 3 or debt_ratio > 60: safety_tier = "B"  # line 48
```
→ safe_picks (배당주 선정) 가 금융주를 부채 기준으로 자동 탈락 시킴. 한국 은행주 배당 강자 (KB금융, 신한 등) 회귀 가능.

**Root cause**: `feedback_sector_aware_thresholds` 메모리 5/3 작성. `api/intelligence/sector_thresholds.py` helper 5/10 생성. 그러나 기존 debt_ratio 하드코드 지점 (7곳 추정) 일괄 패치 미완. "단일 변수 통제" 원칙 위반 (한 번에 다 정정해야 함).

### Rule 6 — AI fallback sanitization (MED 2건)

메모리 `feedback_ai_fallback_sanitization`: "LLM fallback 시 사용자 필드는 제네릭, raw 에러는 `_error` + logger. `f\"...{str(e)}\"` 패턴 금지"

**Drift 3**: `api/analyzers/gemini_analyst.py:953`
```python
"ai_verdict": f"AI 분석 오류: {str(e)[:50]}",
```
→ `ai_verdict` 는 사용자 노출 필드 (사이트 카드/리포트에 노출). raw `str(e)` 노출 시 사용자 혼란 + 내부 정보 leak.

**Drift 4**: `api/analyzers/postmortem.py:334` — 동일 패턴.

**Root cause**: 메모리 룰 박힘 후 신규 fallback 경로 추가 시 룰 미적용. 단일 변수 통제 누락.

### Rule 2 — R-Multiple Exit (LOW 1건)

**Drift 5**: `vercel-api/api/stock.py:418`
```python
target_price = min(bb_upper, ma20 * 1.12)  # UI 참고용 (자동 액션 X)
```
주석에 "자동 액션 X" 명시 — 즉 의도된 잔존. VAMS 코어는 1R/2R 트레일링 완전 적용. 단 literal drift 라 관찰만.

---

## Fix 분류

### 5/17 sprint queue
- **P0 (Rule 5)**: `verity_brain.py:1631` + `safe_picks.py:30,46,48` `sector_thresholds` 헬퍼 호출로 정정. 추가로 `debt_ratio` 하드코드 잔존 grep 일괄 검토 (7곳 추정).
- **P1 (Rule 6)**: `gemini_analyst.py:953` + `postmortem.py:334` raw `str(e)` 분리 (`_error` 필드 + 사용자 필드 제네릭).

### 관찰
- **P2 (Rule 2)**: 의도된 literal drift. 메모리 노트 추가 가능 ("vercel-api UI 참고값은 1.12 잔존 — 의도된 예외").

### 5/17 ATR verdict 전 사전 정정 권장
P0 2건은 verdict 신뢰도 영향 낮으나 금융주 데이터 품질 회귀 가능. 가능하면 5/16 전 처리.

---

## 다음 갈래 (5/15)

Axis #3 코드 품질 — dead code / dangling ref / security. `feedback_mass_removal_dangling_ref_audit` 패턴 확장.

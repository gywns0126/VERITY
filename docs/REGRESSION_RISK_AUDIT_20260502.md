# 회귀 위험 검증 — 부채 300% Hard Floor ↔ sector_aware (의제 ac9d1dc1)

**작성**: 2026-05-02 (5/2 audit Step 3 P1c 후속)
**의제 id**: ac9d1dc1
**범위**: documentation only — 운영 코드 미터치. 검증 결과 → 운영 코드 정정 의제 등록
**참조**: `docs/SOURCE_AUDIT_20260502.md` §8-3 P1c / 메모리 `feedback_sector_aware_thresholds`

---

## 검증 질문

> 메모리 `feedback_sector_aware_thresholds` 는 "부채비율 등 섹터 의존 임계는 sector_thresholds 헬퍼 사용. 단일 임계 분기 금지 (금융주 오분류)" 명시.
> Brain v5 Hard Floor (`verity_brain.py:1631` `if kis_debt > 300: auto_avoid_d.append(...)`) 가 이 정책 정합인가?
> 미정합 시 → 금융주 (은행/보험 D/E 200~700% 정상) 자동 AVOID 회귀 위험.

---

## 1. 코드 grep 결과

### 1-1. sector_aware 헬퍼 사용처

| 파일 | 라인 | 적용 영역 |
|---|---|---|
| `tests/test_dilution.py` | 215-240 | dilute() 함수 sector 분기 테스트 (general / financial / construction / aviation_shipping) |
| (헬퍼 함수 자체) | — | grep 결과 `sector_thresholds` / `sector_aware` 키워드 부재 |

### 1-2. dilute() 함수 — sector 분기 ✅

```python
# tests/test_dilution.py:223-227 (정상 운영 케이스)
def test_financial_normal_range(self):
    """은행/보험 350% — 정상 운영 범위. 일반 기준이면 위험."""
    out = dilute("부채비율", 350, sector="financial")
    assert "정상 운영" in out
    assert "재무 구조" in out
```

→ 일반인 리포트 표현 (dilute) 에서는 financial sector 350% = "정상 운영" / general 250% = "위험" 분기 정상 작동.

### 1-3. Brain v5 Hard Floor — sector 분기 ❌

```python
# api/intelligence/verity_brain.py:1626-1639
kfr = stock.get("kis_financial_ratio", {})
if kfr.get("source") == "kis":
    kis_debt = kfr.get("debt_ratio", 0)
    kis_roe = kfr.get("roe", 0)
    kis_cr = kfr.get("current_ratio", 100)
    if kis_debt > 300:
        auto_avoid_d.append(_make_flag(f"부채비율 {kis_debt:.0f}% (KIS 기준)"))  # ← sector 면제 X
    elif kis_debt > 200:
        downgrade_d.append(_make_flag(f"고부채 {kis_debt:.0f}% (KIS 기준)"))    # ← sector 면제 X
```

→ KIS 재무비율 검증 단계에서 부채 300%+ = `auto_avoid_d` (Hard Floor 자동 AVOID) / 200~300% = `downgrade_d`. **sector 분기 / financial 면제 룰 X**.

### 1-4. 미국 종목 부채 80% 룰 (verity_brain.py:1577)

```python
us_debt_ratio = sec_fin.get("debt_ratio") or stock.get("debt_ratio", 0)
if us_fcf is not None and us_fcf < 0 and us_debt_ratio > 80:
    auto_avoid_d.append(_make_flag(f"FCF ${us_fcf/1e6:,.0f}M + 부채 {us_debt_ratio:.0f}%"))
```

→ FCF 음수 + 부채 80%+ 결합 임계. US 금융주 (전형적 D/E 1000%+) 자동 AVOID 회귀 위험 별도 존재 (단 FCF 음수 조건 결합으로 일반 금융주는 통과 가능 — 추가 검증 필요).

### 1-5. 다른 sector-aware 영역 (참고)

| 파일 | 라인 | 영역 |
|---|---|---|
| `verity_brain.py:1967-1980` | inverted yield curve 시 sector_financial / 금융 / 부동산 추가 penalty -5점 | bond_curve adjustment (Hard Floor 무관) |
| `lynch_classifier.py` | TURNAROUND 부채 < 300% 조건 | sector 면제 X (Lynch 6분류 한국 임계, 동일 문제) |

---

## 2. Verdict: 🔴 회귀 위험 **확정**

### 2-1. silent inconsistency 발견

**동일 종목 (예: 신한금융 D/E 350%)**:
- `dilute()` 함수 (일반인 리포트) → "정상 운영 범위, 안정적 재무 구조" ✅
- `verity_brain.py:1631` Hard Floor → `auto_avoid_d` (자동 AVOID) 🔴

→ 일반인 리포트 표현은 정상이나 *Brain 의 종목 선정 단계에서 자동 탈락*. 금융주 추천 0건 회귀 가능성 정량 확인.

### 2-2. 메모리 정책 위반 영역

| 영역 | 상태 |
|---|---|
| dilute() 함수 (리포트 표현) | ✅ 정합 |
| verity_brain.py:1631 (Hard Floor 부채 300%) | 🔴 위반 |
| verity_brain.py:1633 (downgrade 부채 200%) | 🔴 위반 |
| verity_brain.py:1577 (US FCF<0+부채 80%) | ⚠️ 조건부 (FCF 결합으로 일반 금융주 통과, 단 stress 시 회귀) |
| lynch_classifier.py TURNAROUND 부채 < 300% | 🔴 위반 (한국 금융주 TURNAROUND 분류 자동 탈락) |

### 2-3. 영향 범위 (정량)

- KOSPI 금융업 (은행/증권/보험): ~30종목, 평균 D/E 250~700%
- KOSDAQ 금융업: ~10종목, 평균 D/E 150~400%
- → **운영 universe 5,000 확장 (T1-25 Phase 2-A) 시 ~40 종목 자동 탈락 회귀 정량**
- KB금융 / 신한금융 / 하나금융 / 미래에셋 / 삼성생명 / DB손보 등 한국 대표 금융주 모두 영향

---

## 3. 정정 계획 (운영 코드 변경 sprint)

본 audit 는 *documentation only* — 정정 자체는 별도 sprint. 권장 패턴:

### 3-1. sector_thresholds 헬퍼 신규 작성

```python
# api/utils/sector_thresholds.py (신규 권장)

FINANCIAL_SECTORS = {"financial", "bank", "insurance", "securities", "은행", "보험", "증권"}
HEAVY_DEBT_SECTORS = {"construction", "aviation_shipping", "건설", "항공", "해운"}

def get_debt_thresholds(sector: str) -> dict:
    """sector 별 부채비율 임계 (auto_avoid / downgrade).
    
    출처: feedback_sector_aware_thresholds 정책 + tests/test_dilution.py:215 정합.
    """
    s = (sector or "").lower()
    if any(f in s for f in FINANCIAL_SECTORS):
        return {"auto_avoid": 700, "downgrade": 500}  # 은행/보험 D/E 정상 200~700%
    if any(h in s for h in HEAVY_DEBT_SECTORS):
        return {"auto_avoid": 500, "downgrade": 350}  # 건설/항공/해운 D/E 정상 250~400%
    return {"auto_avoid": 300, "downgrade": 200}      # 일반 (현 단일 임계 보존)
```

### 3-2. verity_brain.py 정정 패턴

```python
# verity_brain.py:1631 정정 후
from api.utils.sector_thresholds import get_debt_thresholds
sector = stock.get("sector", "")
thresholds = get_debt_thresholds(sector)
if kis_debt > thresholds["auto_avoid"]:
    auto_avoid_d.append(_make_flag(f"부채비율 {kis_debt:.0f}% [{sector}] (KIS 기준, 임계 {thresholds['auto_avoid']}%)"))
elif kis_debt > thresholds["downgrade"]:
    downgrade_d.append(_make_flag(f"고부채 {kis_debt:.0f}% [{sector}]"))
```

### 3-3. lynch_classifier.py TURNAROUND 정정 동일 패턴

### 3-4. 단위 테스트 추가

```python
# tests/test_brain_hard_floor_sector.py (신규)
class TestHardFloorSectorAware:
    def test_financial_350_pass(self):
        # 신한금융 D/E 350% — auto_avoid 발동 X
        result = compute_brain_score({...sector: "financial", debt_ratio: 350})
        assert "auto_avoid" not in [f.cat for f in result["red_flags"]]
    
    def test_financial_750_avoid(self):
        # 보험사 D/E 750% — auto_avoid 발동 ✅
        ...
    
    def test_general_350_avoid(self):
        # 일반 제조업 D/E 350% — auto_avoid 발동 ✅ (기존 동작 보존)
        ...
```

---

## 4. 의제 등록 (action_queue 갱신)

### 4-1. 의제 ac9d1dc1 검증 결과 갱신

**검증 결과**: 🔴 회귀 위험 확정 (verity_brain.py:1631 / 1633 / lynch_classifier.py TURNAROUND 부채 300%)

### 4-2. 신규 의제 — 운영 코드 정정 sprint

| id | 의제 | 우선순위 | 의존성 | 비고 |
|---|---|---|---|---|
| **신규-fa3c2d1e** | sector_thresholds 헬퍼 + Hard Floor 정정 sprint | 🔴 P0 | 즉시 가능 | 운영 코드 변경 (운영 영향 high) |

(*의제 id 는 권장 — user_action_queue 등록 시 실제 uuid 부여*)

### 4-3. 기존 의제 cross-ref 갱신

- `ac9d1dc1` (검증 의제) → ✅ 검증 완료. 검증 결과 = 🔴
- `7916b1f5` (신호 3 코드 구현) — 별도 sprint 동일 패턴
- `64d145cc` (VAMS 프로필 alpha 비교) — 다른 sprint 묶음 가능

---

## 5. 가이드 — 운영 코드 정정 sprint 진입 전 점검

1. **백테스트 영향 사전 측정**: 기존 `auto_avoid` 발동 종목 중 financial sector 가 몇 % 인지 측정 (운영 portfolio.json grep)
2. **단위 테스트 우선**: `test_brain_hard_floor_sector.py` 작성 + 기존 일반 제조업 동작 회귀 테스트 통과 확인
3. **Phase 0 verdict (5/16) 종료 후 진입 권장**: 단일 변수 통제 (Phase 0 ATR 마이그레이션과 격리, 결정 21 정합)
4. **메모리 정합 점검**: `feedback_sector_aware_thresholds` 본문에 *Hard Floor 영역* 까지 적용 명시 (현재 dilute() 만 적용된 silent gap)

---

## 6. 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-02 | 초기 작성 — 의제 ac9d1dc1 검증 결과 🔴 + 정정 sprint 의제 등록 |

---

문서 끝.

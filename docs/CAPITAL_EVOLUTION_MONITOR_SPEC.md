# Capital Evolution Monitor 모듈 명세

**작성**: 2026-05-03 00:30 KST (Round 3 작업 6)
**모듈 경로**: `api/intelligence/capital_evolution_monitor.py` (신규 예정)
**우선순위**: P2 (운영 데이터 누적 6개월+ 후 즉시 구현 X / 의제 큐잉만)
**참조**:
- 메모리 `project_capital_evolution_path` (6 tier × 7축 + 3 trigger spec)
- `docs/SILENT_ERRORS_20260502.md` Error 5
- `docs/OPS_VERIFICATION_20260502.md` §13 (VAMS 프로필 진단)
- 의제 c5e8f9a2 / b9d4f72a / e8a17b3c / f3a8c1d4

---

## 0. 진입 조건 (선행 의존성) — 의무

본 모듈 구현은 다음 의제 정정 후 진입 의무:

| 우선 | 의제 | 영역 | 영향 |
|---|---|---|---|
| **1** | **c5e8f9a2** (P0+) | vams.total_value=0 + holdings avg_price=0 결함 | **Trigger 1 (Primary 신호) 데이터 source** |
| 2 | e8a17b3c (P0+) | KR sector 수집기 미구현 | **Trigger 2 (시장 임팩트) sector 분포 정확** |
| 3 | b9d4f72a (P1) | VAMS sector_diversification silent gap | **Trigger 2 보강 — sector 한도 trigger 정확** |

**c5e8f9a2 미정정 상태에서 본 모듈 작동 시 결과**:
- Trigger 1 (자본 임계) = `total_value=0` 항상 → 발동 안 함 (silent fail)
- Trigger 2 (시장 임팩트) = holdings avg_price=0 → 매수 가치 산출 불가
- Trigger 3 (활용도) = 작동 가능 (`len(holdings)` 만 사용)

→ c5e8f9a2 정정 전 = **3 trigger 중 1개만 작동 = *활용도 only* 시스템**. 자본 진화 컨셉의 *부분 작동* = 의미 X. 본 모듈은 *전체 trigger 작동* 전제 설계.

---

## 1. 기능 요약

1. **자본 tier 자동 monitor** (매주 1회 cron)
2. **Tier 전환 임계 도달 감지** (사전 -10% 알림 + 도달 즉시 알림)
3. **텔레그램 알림 + action_queue 자동 등록** (`feedback_auto_schedule_action_queue` 정합)
4. **메모리에 진화 이력 영구 기록** (`portfolio.capital_evolution_history` jsonl 누적)

## 2. 모듈 설계

### 2-1. 핵심 함수 시그니처

```python
# api/intelligence/capital_evolution_monitor.py

from typing import TypedDict, Literal

TierName = Literal["tier_1", "tier_2", "tier_3", "tier_4", "tier_5", "tier_6"]

class TierTransition(TypedDict):
    from_tier: TierName
    to_tier: TierName
    trigger: Literal["capital", "impact", "utilization"]
    detected_at: str  # ISO timestamp
    capital_value: float
    impact_pct: float | None
    utilization_pct: float | None
    transition_checklist: list[str]  # Tier 전환 checklist

def determine_tier(capital_value: float) -> TierName:
    """자본 값 → tier 분류.
    
    Tier 1: 0 ~ 100,000,000 (1억)
    Tier 2: 100,000,000 ~ 500,000,000 (5억)
    Tier 3: 500,000,000 ~ 2,000,000,000 (20억)
    Tier 4: 2,000,000,000 ~ 5,000,000,000 (50억)
    Tier 5: 5,000,000,000 ~ 10,000,000,000 (100억)
    Tier 6: 10,000,000,000+ (100억+)
    """
    ...

def check_capital_tier_transition(portfolio: dict) -> TierTransition | None:
    """매주 cron 호출. 3 trigger 검사 후 첫 발현 trigger 의 transition 반환.
    
    Self-protection: total_value=0 시 텔레그램 alert + cron skip (silent fail X).
    """
    # 데이터 검증 (f3a8c1d4 정합)
    total_value = portfolio.get("vams", {}).get("total_value", 0)
    if total_value == 0:
        send_debug_alert("CAPITAL_MONITOR_DATA_ERROR: total_value=0 — c5e8f9a2 미정정")
        return None  # silent fail X — alert + skip
    
    # Trigger 1 (Primary): 자본 임계
    current_tier = portfolio.get("capital_tier", "tier_1")
    new_tier = determine_tier(total_value)
    if new_tier != current_tier:
        return _build_transition(current_tier, new_tier, "capital", portfolio)
    
    # Trigger 2 (Secondary): 시장 임팩트
    impact_alert = _check_market_impact(portfolio)
    if impact_alert:
        return _build_transition(current_tier, _next_tier(current_tier),
                                  "impact", portfolio)
    
    # Trigger 3 (Tertiary): 활용도 cap
    util_alert = _check_utilization_cap(portfolio)
    if util_alert:
        return _build_transition(current_tier, _next_tier(current_tier),
                                  "utilization", portfolio)
    
    return None

def send_evolution_alert(transition: TierTransition) -> None:
    """텔레그램 알림 + action_queue 자동 등록."""
    ...

def register_evolution_sprint(transition: TierTransition) -> None:
    """user_action_queue Supabase 등록 (project_user_action_queue 정합)."""
    ...

def update_capital_evolution_history(transition: TierTransition) -> None:
    """data/metadata/capital_evolution_history.jsonl 누적."""
    ...
```

### 2-2. Self-protection (Error 5 학습 직접 반영)

```python
# 환경변수 디버그 모드
DEBUG_CAPITAL_MONITOR = os.getenv("DEBUG_CAPITAL_MONITOR", "false").lower() == "true"

def send_debug_alert(message: str) -> None:
    """silent fail 차단 — 데이터 결함 즉시 알림.
    
    Error 5 학습 사례 직접 반영:
    - vams.total_value=0 silent error 가 자본 진화 시스템 자체 무효화
    - monitor 가 silent skip 하면 결함 누적 → 알림 의무
    """
    from api.notifications.telegram import send_alert
    send_alert(f"⚠️ Capital Evolution Monitor: {message}")
    if DEBUG_CAPITAL_MONITOR:
        print(f"[DEBUG] {message}")
```

### 2-3. Trigger 우선순위 (project_capital_evolution_path 정합)

종합 룰 (메모리 spec 정합):

```python
def evaluate_triggers(portfolio: dict) -> list[str]:
    """발현된 trigger 들 반환. 1개 발현 시 검토 / 2개+ 즉시 진입 / 3개 강제."""
    triggers = []
    
    # Trigger 1 (Primary)
    if _capital_threshold_reached(portfolio):
        triggers.append("capital")
    
    # Trigger 2 (Secondary)
    if _market_impact_detected(portfolio):
        triggers.append("impact")
    
    # Trigger 3 (Tertiary)
    if _utilization_cap_reached(portfolio):
        triggers.append("utilization")
    
    return triggers


def evolution_sprint_action(triggers: list[str]) -> Literal["review", "enter", "force"]:
    """trigger 발현 수에 따른 액션 결정."""
    n = len(triggers)
    if n == 0:
        return None
    elif n == 1:
        return "review"   # action_queue 등록
    elif n == 2:
        return "enter"    # PM 수동 confirm 후 즉시 진입
    else:  # n >= 3
        return "force"    # 자본 cap 명백 + 시장 임팩트 + 활용도 도달 = 강제 신호
```

## 3. 의존성 (입력 데이터)

| 데이터 source | 위치 | 용도 |
|---|---|---|
| `vams.total_value` | portfolio.json | Trigger 1 — 자본 임계 (c5e8f9a2 의존) |
| `vams.holdings` | portfolio.json | Trigger 2 시장 임팩트 + Trigger 3 활용도 |
| holdings `avg_price` | portfolio.json | Trigger 2 매수 가치 산출 (c5e8f9a2 의존) |
| holdings sector | portfolio.json | Trigger 2 보강 (e8a17b3c 의존) |
| `vams.active_profile` | portfolio.json | Trigger 3 max_picks 산출 |
| `feedback_auto_schedule_action_queue` | 시스템 메모리 | action_queue 자동 등록 mechanism |
| `project_user_action_queue` | 시스템 메모리 | Supabase user_action_queue 등록 |

## 4. 진입 조건 (시점)

### 4-1. 자본 변동성 충분

- 월 5%+ 변동 시작 시점 — 변동성 부족 시 monitor 무의미 (의미 있는 transition 없음)
- 현재 자본 1,000만 가정 시 Tier 1 이내 변동 → 즉시 도입 가치 낮음

### 4-2. Tier 1 → 2 transition 가능성 시점

- 자본 8,000만+ 도달 시 도입 가치 (Tier 1 → 2 임박)
- 현재 5/2 baseline (1,000만, total_value=0 silent error) → 즉시 도입 X

### 4-3. 우선순위

**P2** — 운영 데이터 누적 6개월+ 후 즉시 구현 X. 의제 큐잉만.

본 spec = 향후 도입 시 *설계 baseline* 보존. 즉시 구현 의제 X.

## 5. 단위 테스트 spec (구현 시점에 작성)

```python
# tests/test_capital_evolution_monitor.py (구현 시점 신규)

class TestDetermineTier:
    def test_tier_1_boundary(self):
        assert determine_tier(99_999_999) == "tier_1"
        assert determine_tier(100_000_000) == "tier_2"
    
    def test_tier_6_unbounded(self):
        assert determine_tier(50_000_000_000) == "tier_6"

class TestSelfProtection:
    def test_total_value_zero_alerts(self):
        """Error 5 학습 직접 반영 — silent fail 차단."""
        portfolio = {"vams": {"total_value": 0}}
        with mock.patch("send_alert") as alert:
            result = check_capital_tier_transition(portfolio)
            assert result is None
            alert.assert_called_once()

class TestTriggerEvaluation:
    def test_single_trigger_review(self):
        assert evolution_sprint_action(["capital"]) == "review"
    
    def test_two_triggers_enter(self):
        assert evolution_sprint_action(["capital", "impact"]) == "enter"
    
    def test_three_triggers_force(self):
        assert evolution_sprint_action(["capital", "impact", "utilization"]) == "force"
```

## 6. 출력 / 산출물

### 6-1. portfolio.json 신규 필드

```jsonc
{
  "capital_tier": "tier_1",                       // 신규 — 매주 cron 갱신
  "capital_evolution_history": [                  // 신규 — transition 누적
    {
      "detected_at": "2026-XX-XXT...",
      "from_tier": "tier_1",
      "to_tier": "tier_2",
      "trigger": "capital",
      "capital_value": 100_500_000,
      ...
    }
  ]
}
```

### 6-2. data/metadata/capital_evolution_history.jsonl

매 transition 1줄 append. 시계열 추적 baseline.

### 6-3. action_queue 자동 등록

transition 발현 시 `evolution_sprint_<from_tier>_to_<to_tier>` 의제 user_action_queue 자동 등록 (PM 수동 confirm 게이트).

## 7. 학습 사례 cross-ref (footnote)

본 spec 작성 시 **Error 5 (vams.total_value=0)** finding 발견 (5/2 23:55 진단). 학습:

→ `feedback_source_attribution_discipline` 6번째 학습 사례:
> "데이터 layer 결함 → 의사결정 layer 자체 작동 불가 패턴"

→ 향후 모듈 spec 작성 시 *입력 데이터 검증* 의무화 (의제 f3a8c1d4 — assume X / verify O)

→ 메타 원칙: **"spec 만 짜고 데이터 가정 X — 데이터 검증 후 spec 진입"**

본 spec 자체가 위 룰의 *적용 사례 1번째*: c5e8f9a2 / b9d4f72a / e8a17b3c 선행 의존성 명시 → 본 spec 진입 전 데이터 검증 게이트 통과 의무.

## 8. 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-03 00:30 KST | 초기 작성 — 진입 조건 + 모듈 설계 + Self-protection + Trigger spec + 학습 사례 cross-ref |

---

문서 끝.

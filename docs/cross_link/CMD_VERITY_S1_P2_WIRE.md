# [VERITY-S1-P2-WIRE-20260504] cross_link_layer P2 운영 통합 (Wire)

**상위 spec**: VERITY-CROSSLINK-THRESHOLDS-V1.4-20260504 §11 / §13 / §16
**유형**: P2 wire sprint (운영 통합 + Telegram dispatch + AdminDashboard)
**예상 소요**: 4~6시간
**진입 조건 (둘 다 만족 의무)**:
1. Sprint 1.5 (VERITY-S1.5-NOISE-FLOOR-RETRACTION) 종료 보고 PASS
2. KI-9 cron (VERITY-CRON-BACKTEST-HISTORY) 종료 보고 PASS

---

## §0. 진입 조건 검증 (P2 시작 전 의무)

### 0-1. Sprint 1.5 종료 PASS 검증

```bash
# Sprint 1.5 산출 보고서 존재 확인
ls -la data/mock/cross_link/sprint_1_5_validation_report.md

# trust_score.py 변경 0 확인 (방식 B)
git status --short api/observability/trust_score.py  # 빈 출력 의무

# §9 분기 4 함수 신규 확인
grep -n "_evaluate_noise_floor_escalation" api/observability/cross_link_layer.py

# cross_link_violations.jsonl 영속화 확인
ls -la data/metadata/cross_link_violations.jsonl
```

### 0-2. KI-9 cron 종료 PASS 검증

```bash
# cron 등록 + 1일 검증 보고 확인
# api/cron/backtest_history_append.py 존재 확인
ls -la api/cron/backtest_history_append.py

# backtest_stats_history.jsonl entry 1개 이상 누적 확인
wc -l data/metadata/backtest_stats_history.jsonl  # 1 이상 의무
```

**둘 중 하나라도 미달 시 P2 진입 X. 사용자 통보 후 STOP.**

---

## §1. 작업 배경

### 1-1. P2 wire 정의

Sprint 1 P0 (cross_link_layer.py 482L) → P1 (720L 확장 + 영속화) → Sprint 1.5 (분기 4 retraction) → **P2 wire (운영 통합)**.

P2 wire = mock에서 운영 환경으로 옮기는 단계:
- run_cross_link()를 api/main.py Brain cycle에 chain 진입
- Telegram dispatch 신규 구현 (§11-1)
- AdminDashboard 카드 신규 구현 (§16-3 join)
- 운영 환경 첫 호출 verification

### 1-2. v1.4 정합

- §11-1: Telegram CRITICAL dispatch (cycle 단위)
- §11-2: 주간 PDF 누적 (별도 sprint, P2 범위 X)
- §13: 운영 호출 path에 baseline_override 차단 의무
- §16-3: AdminDashboard에서 trust_score.jsonl + cross_link_violations.jsonl join

### 1-3. P2 범위 명시 (out-of-scope 차단)

| 항목 | P2 범위 | 별도 sprint |
|---|---|---|
| run_cross_link() chain 진입 | ○ | — |
| Telegram CRITICAL dispatch | ○ (§11-1) | — |
| AdminDashboard 카드 | ○ (§16-3 join) | — |
| 주간 PDF 누적 dispatch | X | 별도 sprint |
| 7 sub-factor 추가 evaluator | X | v1.4 cycle 12주 본격 평가 후 |
| backfill 1회 (KI-9) | X | 별도 sprint |
| 운영 환경 cron 작동 검증 | △ (P2 종료 후 1주 검증 보고만) | — |

---

## §2. P0 작업 — Chain 진입 + Telegram + AdminDashboard

### 2-1. run_cross_link() Chain 진입 위치

**가설**: api/main.py Brain cycle 내 trust_score.py 산출 직후, 다음 cycle 진입 직전.

**확정 의무**: Claude Code가 api/main.py의 Brain cycle 흐름 inspection 후 정확한 위치 결정. 다음 위치 후보 검토:

1. trust_score.report_readiness() 호출 직후
2. trust_score 산출 결과 영속화 직후
3. Brain cycle 종료 직전

권고 위치: **trust_score.report_readiness() 호출 직후**. 이유:
- 9번째 sub-factor (§5)가 T-14 verdict 사용 → cross_link 산출이 trust 산출 input이 아님 → trust 산출 후 호출이 자연스러움
- self-healing loop 차단 정신 정합

### 2-2. Chain 진입 코드 (예시)

```python
# api/main.py 또는 api/brain/cycle.py
# 정확한 위치는 Claude Code inspection 후 결정

from api.observability.trust_score import report_readiness
from api.observability.cross_link_layer import run_cross_link

def execute_brain_cycle(cycle_id: str, ...):
    # ... 기존 로직 ...
    
    # trust_score 산출
    trust_result = report_readiness(...)
    
    # cross_link 산출 (P2 신규 chain)
    cross_link_result = run_cross_link(
        backtest_stats_fetcher=lambda: _load_backtest_stats(),
        verification_report_fetcher=lambda: generate_verification_report(...),
        trust_log_fetcher=lambda: _load_trust_log(),
        history_fetcher=lambda: _load_backtest_history(),
        # baseline_override / rolling_violations_fetcher 절대 박지 말 것 (§13 KI-13)
    )
    
    # Telegram dispatch §11-1
    if cross_link_result["verdict"] in ("manual_review", "hold") or \
       cross_link_result.get("escalation_result") is not None:
        _dispatch_telegram_critical(cycle_id, cross_link_result)
    
    # ... 기존 후속 로직 ...
```

### 2-3. Telegram CRITICAL Dispatch 신규

```python
# api/notifications/telegram_dispatcher.py (신규 또는 기존 확장)

import os
import requests

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_PM_CHAT_ID"]
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


def dispatch_cross_link_critical(cycle_id: str, cross_link_result: dict):
    """v1.4 §11-1 — cross-link CRITICAL 즉시 dispatch.
    
    Trigger 조건:
    - §9-3 PM trigger escalation (verdict = manual_review or hold via §9-2)
    - §5 instant_hold 발동
    - §3 STALE_UNKNOWN 산출
    - §10 TIER3 rate limit 도달
    """
    verdict = cross_link_result["verdict"]
    phase = cross_link_result.get("phase", "UNKNOWN")
    alert_tier = cross_link_result.get("alert_tier")
    escalation = cross_link_result.get("escalation_result")
    instant_hold = cross_link_result.get("instant_hold_result")
    raw_failed = cross_link_result.get("raw_failed", False)
    
    # Severity 분기
    if raw_failed:
        severity = "stale_unknown"
        trigger = "산출 자체 불가 (Primary/Secondary 모두 실패)"
    elif instant_hold == "hold":
        severity = "instant_hold"
        trigger = f"§5 silent_pass 누적 ≥3"
    elif escalation is not None:
        severity = escalation["verdict"]  # manual_review or hold
        trigger = f"§9-2 {escalation['trigger_tier']} 누적 {escalation['count']}건"
    else:
        return  # CRITICAL 아님, dispatch X
    
    message = f"""[VERITY CROSS-LINK CRITICAL]
Cycle: {cycle_id}
Severity: {severity}
Phase: {phase}
Alert Tier: {alert_tier or 'None'}
Trigger: {trigger}
Verdict: {verdict}
Action: PM 검토 의무
Dashboard: <admin_dashboard_url>
"""
    
    response = requests.post(
        TELEGRAM_API,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        },
        timeout=10,
    )
    
    if response.status_code != 200:
        # log error, 단 Brain cycle 자체 차단 X (운영 영향 최소화)
        _log_telegram_dispatch_failure(cycle_id, response.status_code, response.text)
```

**중요**: dispatch 실패 시 Brain cycle 자체 차단 X. log only. trust_score / cross_link 산출은 그대로 영속화.

### 2-4. AdminDashboard 카드 신규

`AdminDashboard` (Framer 또는 별도 운영자 사이트, 메모리 운영 사실 검토):

**카드 1 — Cross-Link 현재 상태**:
- verdict (ready / manual_review / hold)
- phase (INSUFFICIENT_DATA / TIER3_DISABLED / FULLY_ACTIVE / HISTORICAL)
- alert_tier (None / yellow / orange / red)
- 최근 5 cycle 변동 trend

**카드 2 — Cross-Link Violations (30 pair rolling)**:
- TIER1/TIER2/TIER3 누적 count vs NOISE_FLOOR (5/3/1)
- progress bar 형태 시각화
- 누적 임계 도달 시 강조 표시

**카드 3 — Cross-Link × Trust Score Join (§16-3)**:
- 최근 30 cycle 데이터: trust_score.jsonl + cross_link_violations.jsonl join
- cycle_id 기준 left join
- 표 형태: cycle_id / trust_score / cross_link_verdict / alert_tier / escalation_trigger

### 2-5. Operating Path baseline_override 차단 (§13 KI-13)

api/main.py chain 진입 코드에 baseline_override 인자 박지 말 것 명시. 코드 review 시 검증:

```bash
grep -n "baseline_override" api/main.py api/brain/  # 0건 의무
```

만약 발견 시 즉시 제거 + 사용자 통보.

### 2-6. cross_link_violations.jsonl Rotation 정책

- 90일 retention (Sprint 1.5에서 신설된 영속화)
- rotation 처리: 본 P2에서 신규 cron 또는 기존 cron 확장
  - 옵션 A: 별도 cron job (KI-9 cron과 동급)
  - 옵션 B: run_cross_link() 호출 시 retention 자동 enforce
  - **권고**: 옵션 B (코드 자체 enforce, 신규 cron 없음, 메모리 룰 10 cohabitation 정합)

---

## §3. P1 작업 — Mock + Integration tests

### 3-1. Telegram Dispatch Mock

```python
# tests/test_telegram_dispatcher.py

@patch("api.notifications.telegram_dispatcher.requests.post")
def test_dispatch_cross_link_critical_manual_review(mock_post):
    cross_link_result = {
        "verdict": "manual_review",
        "phase": "FULLY_ACTIVE",
        "alert_tier": "orange",
        "escalation_result": {"verdict": "manual_review", "trigger_tier": "TIER2", "count": 3},
        "instant_hold_result": None,
        "raw_failed": False,
    }
    mock_post.return_value.status_code = 200
    
    dispatch_cross_link_critical("cycle_42", cross_link_result)
    
    mock_post.assert_called_once()
    payload = mock_post.call_args[1]["json"]
    assert "TIER2" in payload["text"]
    assert "manual_review" in payload["text"]
```

### 3-2. Chain 진입 Integration Test

```python
# tests/test_brain_cycle_cross_link_integration.py

def test_brain_cycle_calls_cross_link_after_trust():
    # mock trust_score.report_readiness
    # mock run_cross_link
    # execute_brain_cycle 호출
    # 호출 순서 확인: report_readiness → run_cross_link
    # cross_link_result가 영속화 + Telegram dispatch 호출 확인
```

### 3-3. AdminDashboard Join Logic Test

```python
# tests/test_admin_dashboard_cross_link_join.py

def test_join_trust_and_cross_link_by_cycle_id():
    # mock trust_score.jsonl
    # mock cross_link_violations.jsonl
    # join 산출 결과 검증
```

### 3-4. baseline_override 차단 Test

```python
def test_main_py_does_not_pass_baseline_override():
    """§13 KI-13 정합 — 운영 호출 path에 baseline_override 박힘 X."""
    main_py_content = Path("api/main.py").read_text()
    assert "baseline_override" not in main_py_content
```

---

## §4. 절대 하지 말 것

1. **trust_score.py 수정 X** — 방식 B 정신, 모든 sprint 공통.
2. **baseline_override 운영 호출 path 박지 말 것** — §13 KI-13. test로 차단.
3. **rolling_violations_fetcher 운영 호출 path 박지 말 것** — Sprint 1.5에서 신설된 mock helper. 운영은 _load_rolling_violations() 자체 호출.
4. **Telegram dispatch 실패가 Brain cycle 차단 X** — 운영 영향 최소화. log only.
5. **신규 cron 신설 X (rotation)** — 옵션 B 채택. cohabitation.
6. **신규 service / Railway project 생성 X** — 룰 10.
7. **Telegram dispatch 1 cycle 다중 발동 X** — 1 cycle = 최대 1 dispatch (severity 우선순위로 1건만).
8. **AdminDashboard에 baseline_override 같은 mock 인자 표시 X** — 운영 dashboard.
9. **주간 PDF dispatch 본 sprint 진입 X** — out-of-scope.
10. **ESTATE 트랙 자산 0**.

---

## §5. 보고 양식

### 결정사항 표

| # | 항목 | 산출물 |
|---|---|---|
| 0 | 진입 조건 검증 PASS | (Sprint 1.5 + KI-9 cron 보고서 인용) |
| 1 | run_cross_link() chain 진입 위치 | api/main.py:line 또는 api/brain/cycle.py:line |
| 2 | Telegram dispatcher 신규 | api/notifications/telegram_dispatcher.py line 수 |
| 3 | AdminDashboard 카드 3종 | (Framer 또는 별도 사이트 — 사이트 형식 실측 후 결정) |
| 4 | baseline_override 차단 검증 | grep 결과 0건 |
| 5 | cross_link_violations.jsonl rotation | 옵션 B 적용 위치 |
| 6 | mock + integration tests | (n/n PASSED) |
| 7 | 보고서 산출 | data/wire/cross_link/p2_validation_report.md |

### 컴플라이언스 체크

- 절대 하지 말 것 10건 위반 0건
- 메모리 룰 자체 점검 9건
- 룰 8 P0 명세 직접 참조 — v1.4 §11 / §13 / §16 인용
- 룰 4 운영 환경 검증 — Telegram dispatch 운영 환경 1회 호출 의무 (mock 외)

### 발견된 신규 known_issues

observed:
- (해당 시 박음)

hypothesis:
- (해당 시 박음)

### 다음 step 진입 OK 요청

P2 wire 종료 후:
- 1주 운영 데이터 누적 → 메모리 v1.4 cycle mid-review 6주 prereq
- 주간 PDF dispatch 별도 sprint 진입 검토
- 7 sub-factor 추가 evaluator 진입 검토 (12주 본격 평가 후)

---

## §6. AdminDashboard 사이트 형식 결정 (P2 진입 전 추가 결정)

본 sprint는 AdminDashboard 카드 3종을 신규 구현 범위에 박지만, **AdminDashboard 사이트 자체가 어디 있는지 사용자 결정 필요**:

옵션 A — Framer 별도 사이트 (VERITY 운영자용)
옵션 B — 기존 VERITY 분석 사이트 내 admin 페이지
옵션 C — 별도 service (메모리 룰 10 검토 — 신규 자산 cohabitation 우선)

**권고**: 옵션 B (기존 VERITY 사이트 내 admin 페이지). 이유:
- 신규 service / 사이트 생성 X = 룰 10 cohabitation 정합
- 메모리 운영 사실: VERITY service 1개 + ESTATE 별도 = VERITY 사이트 내 admin 추가가 자연스러움
- ESTATE 어드민 사이트와 격리 (메모리 트랙 분리)

**Claude Code 진입 전 사용자 결정 의무**.

---

STOP — Sprint 1.5 + KI-9 cron 두 sprint 종료 보고 + AdminDashboard 사이트 형식 결정 후 P2 진입.

---

## §7. v1.4.1 PATCH 통합 (2026-05-04 사용자 검토 결함 X 정정 + TIER1 시나리오 제거)

### 7-1. §2-3 Telegram 핸들러 의존성 명시 (결함 X)

`api/notifications/telegram_dispatcher.py` 신규 외, **`api/notifications/telegram_bot.py` 신규 핸들러 작업** 명시:

| 항목 | 작업 |
|---|---|
| `telegram_bot.py` 존재 확인 | 없으면 신규 생성 (기존 trust_score 알림 패턴 재사용) |
| cross-link CRITICAL 핸들러 등록 | `register_handler("cross_link_critical", dispatch_cross_link_critical)` |
| 환경변수 검증 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_PM_CHAT_ID` 둘 다 set 의무 |
| 핸들러 통합 test | trust_score 핸들러와 동일 패턴 mock 검증 |

**Claude Code inspection 의무**: `api/notifications/` 디렉토리 구조 + 기존 핸들러 패턴 확인 후 신규 파일 vs 기존 파일 확장 결정.

### 7-2. §3-1 Mock — TIER1 강등 시나리오 제거

v1.4.1 §9-2 정정 (TIER1 강등 비활성)에 따라:

- TIER1 누적 ≥ 5건 → manual_review 강등 시나리오 = **삭제**
- TIER1 dashboard yellow 강조만 검증하는 시나리오로 변경

### 7-3. §0 진입 조건 검증 (v1.4.1 영속화 추가)

P2 진입 시 다음 추가 검증:

```bash
# Sprint 1.5에서 신설된 v1.4.1 영속화 확인
ls -la data/metadata/cross_link_phase_state.json  # 결함 V

# violations.jsonl direction 필드 확인 (결함 U)
head -1 data/metadata/cross_link_violations.jsonl | jq '.violations[0].direction'  # silent_pass 또는 cry_wolf 의무

# _rolling_tier_counts 함수 신규 확인
grep -n "_rolling_tier_counts" api/observability/cross_link_layer.py  # 1건 이상
```

---

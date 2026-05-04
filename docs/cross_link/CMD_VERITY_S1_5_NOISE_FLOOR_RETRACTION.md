# [VERITY-S1.5-NOISE-FLOOR-RETRACTION-20260504] §9 분기 4 구현 + max_tier 룰 demote

**상위 spec**: VERITY-CROSSLINK-THRESHOLDS-V1.4-20260504 §3 / §9 / §12 / §16
**유형**: P0 retraction sprint (Sprint 1 P0/P1 갭 메우기)
**예상 소요**: 4~6시간 (P0 + P1 묶음)
**선행 sprint**: Sprint 1 P0 + P1 (완료)

---

## §1. 작업 배경

### 1-1. v1.4 §9 분기 4 채택 사실

VERITY-S1-NOISE-FLOOR-INSPECT 보고 (2026-05-04) 결과 NOISE_FLOOR 상수 5/3/1 미구현 갭 발견. v1.4 §9에서 분기 4 (3 layer 분리) 채택:

- §9-1 1차 dashboard layer: max_tier 즉시 alarm (P0 현재 동작 유지, **단 verdict 영향 제거**)
- §9-2 2차 verdict 강등 layer: 30 pair 누적 NOISE_FLOOR 도달 시 manual_review/hold (**신규 구현**)
- §9-3 3차 PM trigger layer: §9-2 발동 시 §11 Telegram dispatch (P2 wire 작업 범위)

### 1-2. P0/P1 retraction 범위

| 항목 | 현재 동작 | Sprint 1.5 정정 |
|---|---|---|
| `_build_result()` max_tier → verdict 강등 | 즉시 강등 | dashboard 기록 only, verdict 영향 X |
| §9-2 누적 verdict 강등 | 미구현 | **신규 구현** (`_evaluate_noise_floor_escalation()`) |
| `cross_link_violations.jsonl` | 미존재 | **신규 영속화** |
| mock 시나리오 7건 | max_tier 즉시 alarm 가설 | **재작성** (시나리오 3 / 시나리오 5) + 신규 시나리오 §9-2 검증 1건 |
| tests 13건 | max_tier 즉시 alarm 검증 | **재검증** (3~5건 재작성) |

### 1-3. 메모리 룰 정합

- 룰 7 (cry-wolf 차단): 분기 4 채택 자체가 cry-wolf 차단 = 본 sprint의 정신
- 룰 5 (observed/hypothesis 분리): KI-15/16 = observed (P0 갭 직접 확인), KI-17 = hypothesis (cry_wolf 처리 비대칭 형태)
- 룰 8 (P0 명세 직접 참조): 본 명령서가 v1.4 §3 / §9 / §12 / §16 직접 인용

---

## §2. P0 작업 — 코드 retraction + §9-2 신규 구현

### 2-1. `_build_result()` 정정 (verdict 영향 제거)

**현재 동작** (cross_link_layer.py 추정 위치):

```python
# 추정 — Claude Code 실측 후 정정
tier_rank = {"TIER1": 1, "TIER2": 2, "TIER3": 3}
max_tier = max(tier_rank.get(r.get("evaluation"), 0) for r in violations)
alert_tier = {0: None, 1: "yellow", 2: "orange", 3: "red"}[max_tier]

# 현재: max_tier 즉시 verdict 강등
if max_tier >= 2:
    verdict = "manual_review"
elif max_tier >= 3:
    verdict = "hold"
```

**정정 후**:

```python
# alert_tier 산출 유지 (§9-1 dashboard layer)
tier_rank = {"TIER1": 1, "TIER2": 2, "TIER3": 3}
max_tier = max(tier_rank.get(r.get("evaluation"), 0) for r in violations)
alert_tier = {0: None, 1: "yellow", 2: "orange", 3: "red"}[max_tier]

# verdict는 §5 instant_hold + §9-2 누적 only
# max_tier → verdict 영향 룰 삭제

result["alert_tier"] = alert_tier  # dashboard 기록
# verdict는 별도 함수 산출
```

### 2-2. `_evaluate_noise_floor_escalation()` 신규

```python
# 신규 함수 — cross_link_layer.py 내부
ROLLING_WINDOW_DAYS = 30  # 기존 상수 재사용
NOISE_FLOOR_TIER1 = 5  # 기존 상수 재사용
NOISE_FLOOR_TIER2 = 3
NOISE_FLOOR_TIER3 = 1

def _evaluate_noise_floor_escalation(
    rolling_violations: list,  # 30 pair 누적 violation
    cycle_violations: list,     # 이번 cycle violation
) -> Optional[dict]:
    """§9-2 누적 verdict 강등 산출.
    
    Returns:
        {"verdict": "manual_review" | "hold", "trigger_tier": str, "count": int} or None
    """
    # 30 pair 누적 + 이번 cycle 합산
    all_violations = rolling_violations + cycle_violations
    
    # Tier별 count
    tier_counts = {"TIER1": 0, "TIER2": 0, "TIER3": 0}
    for v in all_violations:
        tier = v.get("evaluation")
        if tier in tier_counts:
            tier_counts[tier] += 1
    
    # 임계 도달 검사 (TIER3 우선 — hold 강등이 더 강함)
    if tier_counts["TIER3"] >= NOISE_FLOOR_TIER3:  # ≥ 1
        return {"verdict": "hold", "trigger_tier": "TIER3", "count": tier_counts["TIER3"]}
    
    if tier_counts["TIER2"] >= NOISE_FLOOR_TIER2:  # ≥ 3
        return {"verdict": "manual_review", "trigger_tier": "TIER2", "count": tier_counts["TIER2"]}
    
    if tier_counts["TIER1"] >= NOISE_FLOOR_TIER1:  # ≥ 5
        return {"verdict": "manual_review", "trigger_tier": "TIER1", "count": tier_counts["TIER1"]}
    
    return None  # 임계 미달, verdict 영향 X
```

### 2-3. `_compute_final_verdict()` 정정

verdict 산출 input 통합:

```python
def _compute_final_verdict(
    instant_hold_result: Optional[str],         # §5
    escalation_result: Optional[dict],          # §9-2 (신규)
    raw_failed: bool,                           # §1-4 STALE_UNKNOWN
    phase: str,                                 # §17
) -> str:
    # STALE_UNKNOWN 우선
    if raw_failed:
        return "manual_review"
    
    # §5 instant_hold 우선 (가장 강한 trigger)
    if instant_hold_result == "hold":
        return "hold"
    
    # §9-2 누적 강등
    if escalation_result is not None:
        return escalation_result["verdict"]  # "hold" or "manual_review"
    
    return "ready"
```

**중요**: max_tier 즉시 강등 룰 input 자체에서 제거.

### 2-4. `cross_link_violations.jsonl` 영속화 신규

```python
VIOLATIONS_LOG_PATH = Path("data/metadata/cross_link_violations.jsonl")

def _append_violations_log(
    cycle_id: str,
    timestamp: str,
    violations: list,
    alert_tier: Optional[str],
    verdict: str,
    escalation_result: Optional[dict],
) -> None:
    """§16 영속화. AdminDashboard join source."""
    entry = {
        "cycle_id": cycle_id,
        "timestamp": timestamp,
        "violations": violations,
        "alert_tier": alert_tier,
        "verdict": verdict,
        "escalation_result": escalation_result,
    }
    VIOLATIONS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with VIOLATIONS_LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
```

영속화 시점: `run_cross_link()` 산출 결과 영속화 직전.

### 2-5. 30 pair Rolling Violations 산출

```python
def _load_rolling_violations(
    history_window_days: int = 30,
) -> list:
    """§9-2 누적 source. cross_link_violations.jsonl에서 최근 30 pair load."""
    if not VIOLATIONS_LOG_PATH.exists():
        return []
    
    cutoff_ts = datetime.utcnow() - timedelta(days=history_window_days)
    rolling = []
    with VIOLATIONS_LOG_PATH.open("r") as f:
        for line in f:
            entry = json.loads(line)
            entry_ts = datetime.fromisoformat(entry["timestamp"])
            if entry_ts >= cutoff_ts:
                rolling.extend(entry.get("violations", []))
    return rolling
```

### 2-6. `run_cross_link()` 통합

```python
def run_cross_link(
    backtest_stats_fetcher,
    verification_report_fetcher=None,
    trust_log_fetcher=None,
    history_fetcher=None,
    *,
    baseline_override=None,  # mock only — §13
    rolling_violations_fetcher=None,  # mock only — Sprint 1.5 신규
) -> dict:
    # ... 기존 로직 ...
    
    # cycle violations 산출
    cycle_violations = _evaluate_brain_distribution(...)
    
    # §5 instant_hold
    instant_hold_result = _evaluate_instant_hold(cycle_violations, ...)
    
    # §9-2 escalation (신규)
    if rolling_violations_fetcher is not None:
        rolling_violations = rolling_violations_fetcher()  # mock
    else:
        rolling_violations = _load_rolling_violations()  # 운영
    
    escalation_result = _evaluate_noise_floor_escalation(
        rolling_violations=rolling_violations,
        cycle_violations=cycle_violations,
    )
    
    # §9-1 alert_tier (dashboard only)
    max_tier = max(...)
    alert_tier = {0: None, 1: "yellow", ...}[max_tier]
    
    # final_verdict
    final_verdict = _compute_final_verdict(
        instant_hold_result=instant_hold_result,
        escalation_result=escalation_result,
        raw_failed=raw_failed,
        phase=current_phase,
    )
    
    # 영속화
    _append_violations_log(
        cycle_id=cycle_id,
        timestamp=timestamp,
        violations=cycle_violations,
        alert_tier=alert_tier,
        verdict=final_verdict,
        escalation_result=escalation_result,
    )
    
    return {
        "verdict": final_verdict,
        "phase": current_phase,
        "alert_tier": alert_tier,           # §9-1 dashboard
        "violations": cycle_violations,
        "escalation_result": escalation_result,  # §9-2 결과
        "instant_hold_result": instant_hold_result,
        # ... 기존 필드 ...
    }
```

### 2-7. KI-17 cry_wolf 처리 비대칭 검증 (P0 별도 작업)

`brain_distribution_evaluator.py`의 cry_wolf 산출 로직 inspection:

```bash
grep -n "cry_wolf\|cry-wolf" api/observability/brain_distribution_evaluator.py
```

**검증 항목**:
1. cry_wolf TIER1/TIER2/TIER3 임계가 silent_pass와 같은 σ 임계 사용? (§12 대칭 가정)
2. cry_wolf 산출이 §9-2 escalation에 silent_pass와 동일 임계로 합산? 아니면 별도 처리?
3. v1.4 §12 잠정 채택 ("동일 임계 + manual_review only, hold 미발동")이 P0 코드와 정합? 어긋날 시 정정.

**보고**: P0 산출물 §"KI-17 검증 결과" section.

---

## §3. P1 작업 — Mock 시나리오 + tests 재작성

### 3-1. Mock 시나리오 7건 검토

| # | 현재 동작 | Sprint 1.5 정정 |
|---|---|---|
| scenario_1 (정상 ready) | violation 0건 → ready | 그대로 (영향 없음) |
| scenario_2 (정상 silent_pass T1 1건) | TIER1 silent_pass 1건 → ? | **재작성**: rolling 0건 가정 → ready (1건 < NOISE_FLOOR_TIER1=5) |
| scenario_3 (silent_pass T2) | TIER2 1건 → manual_review (cry-wolf!) | **재작성**: rolling 0건 → ready / rolling 2건 → manual_review (3건 누적) |
| scenario_4 (instant_hold) | silent_pass rolling 3 → hold | 그대로 (§5 룰 영향 없음) |
| scenario_5 (cry_wolf) | TIER2 cry_wolf 1건 → hold (변동 X) | **재작성**: 분기 4 정합으로 (§12 KI-17 검증 결과 따라) |
| scenario_6 (baseline_override) | baseline floor 검증 | 그대로 (§13 mock helper) |
| scenario_7 (STALE_UNKNOWN) | source_used=stale_unknown | 그대로 (§3-3 영향 없음) |

### 3-2. 신규 mock 시나리오 (§9-2 누적 검증)

| 시나리오 | rolling violations | cycle violations | 기대 verdict | 기대 alert_tier |
|---|---|---|---|---|
| **scenario_8 (TIER1 누적 5건)** | TIER1 4건 (silent_pass) | TIER1 1건 → 누적 5건 | manual_review | yellow |
| **scenario_9 (TIER2 누적 3건)** | TIER2 2건 | TIER2 1건 → 누적 3건 | manual_review | orange |
| **scenario_10 (TIER3 1건)** | 0건 | TIER3 1건 | hold | red |
| **scenario_11 (TIER1 누적 4건, 미달)** | TIER1 4건 | violation 0건 | ready | None |

### 3-3. P1 pytest 재작성

`tests/test_cross_link_layer_p1.py`:
- parametrize 7건 → 11건 확장 (scenario_8/9/10/11 추가)
- summary 1건 정정 (분기 4 가정 반영)

### 3-4. P0 regression tests 재검증

`tests/test_cross_link_layer.py` 5건:
- 기존 max_tier 즉시 강등 가정으로 작성된 test 식별
- 각 test의 fixture / assertion 분기 4 가정으로 재작성
- 5/5 PASS 보장

---

## §4. 절대 하지 말 것

1. **trust_score.py 수정 0** — 방식 B 정신 유지. `git status --short api/observability/trust_score.py` 빈 출력 검증 의무.
2. **운영 인터페이스에 baseline_override 박지 말 것** — §13 KI-13 정합. mock fetcher only.
3. **신규 service / Railway project 생성 X** — 메모리 룰 10 cohabitation. 기존 cross_link_layer.py 내부 확장만.
4. **NOISE_FLOOR 상수 변경 X** — 5/3/1 v1.3 의도 그대로 유지 (v1.4 §9-2 임계와 일치). 변경 시 v1.4 §9-2 본문 정정 필요 = sprint 범위 초과.
5. **ESTATE 트랙 코드/패턴 0** — 메모리 트랙 분리 정합.
6. **라이브 데이터 호출 0** — Sprint 1 P0/P1 정신 유지. fetcher 주입 패턴.
7. **§9-2 임계값 임의 변경 X** — TIER1=5/TIER2=3/TIER3=1 그대로. 운영 데이터 누적 후 v1.4 cycle 12주 본격 평가에서 재조정.
8. **STALE_UNKNOWN phase 동작 변경 X** — Sprint 1 P1 §결정사항 4 그대로.

---

## §5. 보고 양식

### 결정사항 표

| # | 항목 | 결정 / 산출물 |
|---|---|---|
| 1 | _build_result() 정정 | (산출물 line 변동 + 함수 signature 변경 명시) |
| 2 | _evaluate_noise_floor_escalation() 신규 | (line 수 + 위치) |
| 3 | _compute_final_verdict() 정정 | (산출물 line 변동) |
| 4 | cross_link_violations.jsonl 영속화 | (path + 영속화 시점) |
| 5 | _load_rolling_violations() 신규 | (line 수) |
| 6 | run_cross_link() 통합 | (인자 변경 + return dict 변경) |
| 7 | KI-17 cry_wolf 검증 결과 | (P0 코드 인용 + §12 잠정 채택과 정합 / 어긋남) |
| 8 | mock 시나리오 7건 검토 + 4건 신규 | (재작성 list + 신규 list) |
| 9 | P1 pytest 재작성 | (11/11 PASSED 확인) |
| 10 | P0 regression 재검증 | (5/5 PASSED 확인) |
| 11 | 보고서 산출 | data/mock/cross_link/sprint_1_5_validation_report.md |

### 컴플라이언스 체크

- 절대 하지 말 것 8건 위반 0건
- 메모리 룰 자체 점검 9건 (특히 룰 7 cry-wolf, 룰 10 cohabitation)
- 룰 8 P0 명세 직접 참조 — v1.4 §9 / §3 / §12 / §16 인용 확인

### 발견된 신규 known_issues

observed:
- (해당 시 박음)

hypothesis:
- (해당 시 박음, KI-17 검증 결과 포함)

### 다음 step 진입 OK 요청

Sprint 1.5 종료 후 P2 wire 명령서 진입 대기. KI-9 history cron 명령서는 Sprint 1.5와 병행 작업 가능.

---

## §6. 진입 OK 체크리스트

- v1.4 spec 본문 (§3 / §9 / §12 / §16) 직접 참조 확인 ✅
- Sprint 1 P0/P1 산출물 ([cross_link_layer.py 720L, brain_distribution_evaluator.py 285L]) 보존 확인 (수정만, 재작성 X)
- trust_score.py 변경 0 정신 유지
- Railway tranquil-healing project 신규 자산 생성 X

---

STOP — Sprint 1.5 종료 보고 후 사용자 다음 지시 대기.

---

## §7. v1.4.1 PATCH 통합 (2026-05-04 사용자 검토 결함 R/S/T/U/V 정정)

본 명령서 §2/§3을 다음과 같이 patch:

### 7-1. §2-2 `_evaluate_noise_floor_escalation()` TIER1 분기 삭제

```python
def _evaluate_noise_floor_escalation(...) -> Optional[dict]:
    # ... 기존 로직 ...
    
    # TIER3 우선
    if tier_counts["TIER3"] >= NOISE_FLOOR_TIER3:  # ≥ 1
        return {"verdict": "hold", "trigger_tier": "TIER3", "count": tier_counts["TIER3"]}
    
    if tier_counts["TIER2"] >= NOISE_FLOOR_TIER2:  # ≥ 3
        return {"verdict": "manual_review", "trigger_tier": "TIER2", "count": tier_counts["TIER2"]}
    
    # TIER1 분기 삭제 (v1.4.1 결함 R: 41% cycle 강등 cry-wolf 차단)
    # NOISE_FLOOR_TIER1=5는 §9-1 dashboard yellow 강조 임계로 재정의 (코드 상수 그대로 유지)
    
    return None
```

### 7-2. §2-4 `cross_link_violations.jsonl` schema 정정 (결함 U)

`direction` 필드 추가:

```python
def _append_violations_log(...) -> None:
    entry = {
        "cycle_id": cycle_id,
        "timestamp": timestamp,
        "violations": [
            {
                "evaluator": v["evaluator"],
                "evaluation": v["evaluation"],   # TIER1/2/3 (필수)
                "direction": v["direction"],     # silent_pass / cry_wolf (v1.4.1 신규 필수)
                "value": v["value"],
                "baseline": v["baseline"],
                "sigma": v["sigma"],
            }
            for v in violations
        ],
        "alert_tier": alert_tier,
        "verdict": verdict,
        "escalation_result": escalation_result,
    }
    # ... 영속화 ...
```

### 7-3. §2-5 `_rolling_tier_counts()` 신규 (결함 U)

`_load_rolling_violations()` 외 별도 산출 함수 명시:

```python
def _rolling_tier_counts(
    jsonl_path: Path = VIOLATIONS_LOG_PATH,
    window_days: int = 30,
) -> Dict[str, int]:
    """v1.4.1 §9-2 산출 함수. silent_pass 단방향만 카운트.
    
    Returns:
        {"TIER1": int, "TIER2": int, "TIER3": int}
    """
    counts = {"TIER1": 0, "TIER2": 0, "TIER3": 0}
    if not jsonl_path.exists():
        return counts
    
    cutoff_ts = datetime.utcnow() - timedelta(days=window_days)
    with jsonl_path.open("r") as f:
        for line in f:
            entry = json.loads(line)
            entry_ts = datetime.fromisoformat(entry["timestamp"])
            if entry_ts < cutoff_ts:
                continue
            for v in entry.get("violations", []):
                # silent_pass 단방향만 (cry_wolf는 §12 비대칭 path)
                if v.get("direction") != "silent_pass":
                    continue
                tier = v.get("evaluation")
                if tier in counts:
                    counts[tier] += 1
    return counts
```

`_evaluate_noise_floor_escalation()`이 본 함수 호출하도록 정정.

### 7-4. §"phase 비가역성" 신규 (결함 V)

신규 영속화 + 산출 함수:

```python
PHASE_STATE_PATH = Path("data/metadata/cross_link_phase_state.json")

def _load_phase_state() -> dict:
    """v1.4.1 결함 V 정정 — phase 비가역성 보장."""
    if not PHASE_STATE_PATH.exists():
        return {"max_snapshot_n": 0, "max_phase": "INSUFFICIENT_DATA"}
    return json.loads(PHASE_STATE_PATH.read_text())

def _update_phase_state(current_snapshot_n: int, current_phase: str) -> dict:
    state = _load_phase_state()
    new_state = {
        "max_snapshot_n": max(state["max_snapshot_n"], current_snapshot_n),
        "max_phase": _phase_max(state["max_phase"], current_phase),
    }
    PHASE_STATE_PATH.write_text(json.dumps(new_state, indent=2))
    return new_state

def _phase_max(p1: str, p2: str) -> str:
    """phase 순위 기반 max."""
    rank = {"INSUFFICIENT_DATA": 0, "TIER3_DISABLED": 1, "FULLY_ACTIVE": 2, 
            "ROLLING_STABLE": 3, "HISTORICAL": 4}
    return p1 if rank.get(p1, 0) >= rank.get(p2, 0) else p2
```

`run_cross_link()`에서 phase 산출 시 `_load_phase_state()["max_phase"]` 사용. snapshot_n 변동으로 phase reverse 차단.

### 7-5. §3-2 mock 시나리오 정정

| 시나리오 | v1.4 정정 (이전) | v1.4.1 patch (현재) |
|---|---|---|
| **scenario_8 (TIER1 누적 5건)** | manual_review 강등 | **삭제 또는 dashboard yellow 검증으로 변경** (TIER1 강등 비활성) |
| scenario_9 (TIER2 누적 3건) | manual_review | 그대로 |
| scenario_10 (TIER3 1건) | hold | 그대로 |
| scenario_11 (TIER1 누적 4건) | ready | 그대로 (의미 변경: 강등 미발동 검증 → dashboard 변동만) |
| **scenario_12 (신규)** | — | **phase 비가역성 검증 — snapshot_n 50→30 변동 시 FULLY_ACTIVE 유지** |

### 7-6. ROLLING_STABLE phase 추가 (결함 T 정정)

§17 phase 산출 로직에 ROLLING_STABLE 추가:

- 활성 시점 (Gate B 통과) 기록
- 활성 + 30 cycle 후 = ROLLING_STABLE 진입
- `cross_link_phase_state.json`에 활성 timestamp 영속화 후 비교

---

## §8. 진입 OK (v1.4.1 patch 통합)

본 명령서 §1~§6 (v1.4) + §7 (v1.4.1 patch) 모두 통합 후 진입.

핵심: TIER1 강등 비활성은 코드 1줄 삭제 (분기 제거) + mock 시나리오 1건 정정 = 작업량 5분 이하. 결함 U/V는 신규 함수 + 영속화 추가 = 1~2시간.

# VERITY Cross-Link Layer Spec v1.4

**Spec ID**: VERITY-CROSSLINK-THRESHOLDS-V1.4-20260504
**작성일**: 2026-05-04
**작성자**: Claude (월스트리트 베테랑 애널리스트 + 시니어 운영 매니저 페르소나)
**상위 spec 계승**: V1.3 (본문 미확보, 코드 헤더 윤곽 기반 재구성)
**상태**: DRAFT — P2 wire 명령서 + KI-9 history cron 명령서 작성 source

---

## §0. Source Map 및 추정 위험 명시 (의무)

### 0-1. v1.3 본문 미확보 사실

VERITY-SPEC-LOCATE 보고 (2026-05-04) 결과:
- repo 내 v1.3 spec 본문 파일 **0건**
- 대화 transcript에만 존재 가능, 별도 파일 저장 없음
- v1.0 (Claude 초기 권고) → v1.1 (사용자 14 섹션) → v1.2 (사용자 18 섹션) → **v1.3 본문 미수령**

따라서 v1.4는 다음 source 합집합으로 재구성:

| Source | 위치 | 신뢰도 |
|---|---|---|
| **Primary** — 코드 헤더 직접 인용 | `cross_link_layer.py:1-19`, `cross_link_evaluators/base.py:1-3`, `brain_distribution_evaluator.py:1-9` | 확정 |
| **Secondary** — 코드 상수값 | `cross_link_layer.py` GATE_A=20 / GATE_B=30 / TIER3_DAILY_LIMIT=3 / ROLLING=30 / INSTANT_HOLD=3 / NOISE_FLOOR T1=5 T2=3 T3=1, `brain_distribution_evaluator.py` BASELINE_FLOOR=0.45 / COLD_START=0.50 / COLD_START_LIMIT=50 / STALE=6h | 확정 (운영 의미는 §별 역추정) |
| **Tertiary** — 사용자 메모리 14건 | recent_updates VERITY-CROSSLINK 관련 항목 | 확정 |
| **Quaternary** — P0/P1 코드 동작 | `cross_link_layer.py` 720L + `brain_distribution_evaluator.py` 285L + tests 13건 | 확정 |
| **Reports** — 산출 보고서 | `data/verification/crosslink_prereq_report_20260503.md`, `data/mock/cross_link/p1_validation_report.md` | 확정 |

### 0-2. 섹션별 source 분류

| § | 제목 | source | 분류 |
|---|---|---|---|
| §1 | source 정의 | 코드 헤더 + 메모리 KI-1 | **확정** |
| §2 | snapshot-pair 모델 | 코드 헤더 + 메모리 KI-4 | **확정** |
| §3 | verdict 3-tier | 코드 헤더 | **확정** |
| §4 | 1차 scope + plugin 패턴 | 코드 헤더 + base.py | **확정** |
| §5 | 9번째 sub-factor + T-14 self-healing 차단 | 코드 헤더 + P0 instant_hold 함수 | **확정 (T-14 채택 형태 v1.3 본문과 교차 검증 미가능)** |
| §6 | baseline 90일 mean + floor 0.45 + cold-start 0.5 | 코드 헤더 + brain_distribution_evaluator.py | **확정** |
| §7 | Tier σ 임계 + σ 단위 (KI-11 정정) | 코드 상수 + 메모리 KI-11 + P1 보고 | **v1.4 정정** |
| §8 | Gate A/B + idempotent (KI-12 정정) | 코드 상수 + P1 §결정사항 2 + 메모리 KI-10 | **v1.4 정정** |
| §9 | noise floor 운영 의미 | 코드 상수 NOISE_FLOOR_T1=5 / T2=3 / T3=1 + P0 동작 역추정 | **역추정 (위험)** |
| §10 | Tier 3 rate limit 일일 3건 | 코드 헤더 + 상수 TIER3_DAILY_LIMIT=3 | **확정** |
| §11 | PM 검토 trigger 채널 분리 | 사용자 결정 (Telegram CRITICAL 즉시 / 주간 PDF 누적) | **v1.4 신규** |
| §12 | 처리 정책 비대칭 | brain_distribution_evaluator.py "처리 정책 비대칭" + P0 코드 역추정 | **역추정 (위험)** |
| §13 | 운영 인터페이스 vs mock helper 분리 | KI-13 (P1 보고) | **v1.4 신규** |
| §14 | (calibration 주기) | source 없음 | **TBD** |
| §15 | unit 통일 0~1 | 코드 헤더 | **확정** |
| §16 | 인프라 path 정의 | 메모리 KI-9 + P1 신설 cumulative_trades.json + 방식 B 영속화 | **v1.4 신규** |
| §17 | 운영 단계 4 phase | 메모리 운영 단계 (0~30 / 30~50 / 50+ / 90+) | **v1.4 신규** |
| §18 | (진입 OK 체크리스트) | source 없음 | **TBD** |
| §19 | (베테랑 인지 사항) | source 없음 | **TBD** |

### 0-3. 추정 위험 항목 (정정 시 v1.5 재작성 가능)

| 위험 | 영향 § | 발견 시 처리 |
|---|---|---|
| §5 결함 L = T-14 verdict (코드 헤더 직접 인용) — v1.3이 raw_verdict 채택했을 위험 | §5 | v1.5 §5 재작성 |
| §9 noise floor 5/3/1의 운영 의미 (cycle violation 무시 임계 vs alarm trigger 임계?) | §9 | v1.5 §9 patch |
| §12 처리 정책 비대칭 형태 (silent_pass / cry_wolf 대칭이지만 처리 비대칭) 정확한 명문화 | §12 | v1.5 §12 patch |
| §11 v1.3 본문에 PM trigger 표 있었는지 미확인 — 사용자 결정 채널이 v1.3 표 대체 | §11 | v1.5 §11 통합 |

### 0-4. v1.3 → v1.4 변경 요약

| 항목 | v1.3 (추정) | v1.4 |
|---|---|---|
| §7 σ 산출 단위 | snapshot_n 기반 (P0 코드 mismatch) | **cumulative_trades 기반 명시** (KI-11 정정) |
| §8 Gate A 누적 | "snapshot-pair 누적 trade 합계, 매 cycle 누적" (메모리) | **idempotent 조건 명시** (하루 1회 누적, KI-12) |
| §11 PM trigger | 채널 모호 (Telegram + PDF 둘 다 박힘, dispatch 조건 없음) | **분리 명시**: Telegram=CRITICAL 즉시 / PDF=주간 누적 |
| §13 (신규) | — | **운영 인터페이스 vs mock helper 분리** (KI-13: baseline_override 운영 호출 금지) |
| §16 (신규) | — | **인프라 path 정의** (KI-9 history cron 정합) |
| §17 (신규) | — | **운영 단계 4 phase** (메모리 운영 단계) |
| STALE_UNKNOWN phase | (v1.3 본문 미확인) | **4번째 phase 정식 박힘** (P1 §결정사항 4) |
| §9 noise floor | (P0 미구현 갭) | **3 layer 분리 명문화** (분기 4 채택, Sprint 1.5 retraction 동반) |
| §3 verdict | (P0 max_tier 즉시 강등) | **§9-2 누적 조건 추가** (verdict 영향은 30 pair 누적 후) |

---

## §1. Source 정의

### 1-1. Primary source (정상 운영)

`data/metadata/backtest_stats.json` — strategy_evolver가 매 cycle 산출하는 raw backtest stats.

- 직접 참조 (verification_report 거치지 않음, KI-1 정정)
- 6h staleness 임계: backtest_stats 파일 mtime > 6h = stale 분기 (§3-stale 처리)
- 필드: `periods.14d.{hit_rate, total_recs, ...}`

### 1-2. Secondary source (fallback)

`generate_verification_report` 직호출 — Primary 미달 시 (예: backtest_stats.json 미존재, schema invalid).

- evaluate_past_recommendations schema 정합 (KI-4: lookback period마다 1 snapshot)
- snapshot-pair 비교 모델 (§2 정합)

### 1-3. 비-source (의무 차단)

| Path | 차단 사유 |
|---|---|
| `data/metadata/verification_report.json` | KI-1: stale snapshot 함정. Primary가 갱신돼도 verification_report는 stale 가능. cross-link layer는 backtest_stats 직접 참조 |
| `api/observability/trust_score.py` 내부 상태 | 방식 B (별도 모듈) 정신: trust_score read-only. cross-link가 trust 결과를 읽기는 가능, 수정/내부 함수 호출 X |

### 1-4. STALE_UNKNOWN 4번째 phase (P1 §결정사항 4)

source 3종 (Primary / Secondary / mock) 외 4번째 phase: **stale_unknown**.

- 발동 조건: Primary 6h 초과 + Secondary 호출 실패 + mock fetcher 미주입
- 동작: evaluators SKIPPED + 영속화 X + raw_failed 만 기준으로 final_verdict 산출
- 운영 의미: 산출 자체 불가 상태. 사용자 통보 (Telegram dispatch §11 검토 대상)

---

## §2. Snapshot-Pair 모델

### 2-1. 비-rolling 산출

cross-link layer는 snapshot-pair 비교만 사용. rolling window 산출 X.

- backtest_stats가 매 cycle 산출하는 새 snapshot
- 직전 snapshot과 짝지어 (snapshot-pair) brain trust 산출 변화 검증
- snapshot 쌍이 모여 누적 baseline 형성 (§6 90일 mean)

### 2-2. 표본 단위

- snapshot 1건 = backtest_stats.periods.14d 1회 산출
- snapshot-pair 1건 = 직전 snapshot과 현재 snapshot 비교 산출
- pair 누적 = 매 cycle pair 1건 누적 (Gate B 30건 정의 §8)

### 2-3. snapshot_n vs cumulative_trades 구분 (KI-11 정합)

| 단위 | 정의 | 사용 위치 |
|---|---|---|
| snapshot_n | 단일 snapshot의 trade 수 (backtest_stats.periods.14d.total_recs 1건) | §3 verdict 산출 1차 |
| cumulative_trades | snapshot-pair 누적 trade 합 (Gate A 통과 후) | §7 σ 산출, §8 Gate A |

**핵심**: σ 산출의 표본 크기는 cumulative_trades. snapshot_n 아님 (KI-11 정정).

---

## §3. Verdict 3-Tier

### 3-1. 산출 결과 3종

| verdict | 의미 | brain 운영 영향 |
|---|---|---|
| **ready** | 정상 운영 | trust_score 그대로 사용 |
| **manual_review** | 운영자 검토 필요 | trust_score 운영 전 PM 승인 필요 |
| **hold** | 운영 정지 | trust_score 사용 차단 |

### 3-2. 강등 조건 (분기 4 채택 후)

**중요 정정**: P0 코드 동작 (max_tier 즉시 강등)은 cry-wolf 위험. v1.4에서 §9-2 누적 조건으로 변경.

| 강등 trigger | 강등 결과 | source 룰 |
|---|---|---|
| §5 instant_hold (silent_pass rolling+this ≥ 3) | hold | §5 |
| §9-2 TIER1 누적 ≥ 5건 (rolling 30 pair) | manual_review | §9-2 |
| §9-2 TIER2 누적 ≥ 3건 | manual_review | §9-2 |
| §9-2 TIER3 누적 ≥ 1건 | hold | §9-2 (TIER3=±3σ extreme outlier, 1건도 의미) |

**비-강등 trigger** (cycle 단위 즉시 alarm 산출 X):
- §9-1 max_tier (yellow/orange/red) = dashboard 기록 only, verdict 영향 X

### 3-3. STALE_UNKNOWN 시 verdict

source_used="stale_unknown" 시 final_verdict = `manual_review` (산출 불가 상태 = 운영자 검토 의무).

---

## §4. 1차 Scope + Plugin 패턴

### 4-1. 1차 sub-factor 1개

`brain_distribution_normal` — brain trust score 분포의 baseline ± kσ 정상성 검증.

`api/observability/cross_link_evaluators/brain_distribution_evaluator.py` (P0 신설, 285L).

### 4-2. Plugin 패턴 (v1.4 7 sub-factor 확장 prereq)

`api/observability/cross_link_evaluators/base.py` — `CrossLinkEvaluator` base class.

```python
"""CrossLinkEvaluator base — v1.3 §4 plugin 패턴.
v1.4 확장 시 나머지 7 sub-factor evaluator가 동일 인터페이스로 추가됨."""
```

확장 예정 7 sub-factor (v1.4 cycle 12주 본격 평가 후 결정):
- TBD — 사용자 추후 보충

각 evaluator가 동일 interface 따르므로 `cross_link_layer.py`는 evaluator 추가/제거 영향 받지 않음 (메모리 v1.4 plugin 패턴 정합).

### 4-3. instant_hold 룰은 §5 별도 처리

instant_hold는 sub-factor가 아닌 cross-link layer 자체 룰. base evaluator 인터페이스 외부에서 처리 (`cross_link_layer.py:_evaluate_instant_hold()` 또는 동급 함수).

---

## §5. 9번째 가상 Sub-Factor + T-14 Self-Healing 차단

### 5-1. 9번째 sub-factor 정의

trust_score.py의 8개 sub-factor 외, cross-link 검증 결과를 9번째 가상 sub-factor로 brain trust 산출에 반영.

이름: `cross_link_violation_clear` (P0 헤더 인용)

### 5-2. T-14 verdict 사용 (Self-Healing 차단)

**핵심 정신**: cross-link 검증 결과를 trust 산출 input으로 즉시 반영하면 self-healing loop 발생 (cross-link가 trust 떨어뜨림 → 떨어진 trust가 다음 cross-link 산출 영향 → ...).

**해결**: 9번째 sub-factor 평가 시점 verdict = T-14 (14일 전 산출된 verdict).

- cycle T 시점: cross-link 9번째 sub-factor input = T-14 cycle의 verdict
- T-14 verdict가 `ready` → 9번째 sub-factor = 1.0 (정상)
- T-14 verdict가 `manual_review` → 9번째 sub-factor = 0.5 (감점)
- T-14 verdict가 `hold` → 9번째 sub-factor = 0.0 (최대 감점)

### 5-3. instant_hold 룰

cross_link_layer.py:35 `INSTANT_HOLD_THRESHOLD = 3`.

- silent_pass 누적 (rolling 30 pair 내 silent_pass count + 이번 cycle silent_pass count) ≥ 3 → 강제 hold
- 운영 의미: silent_pass가 누적되면 brain 산출 자체가 의심되는 상태 = T-14 wait 안 하고 즉시 hold
- §9-2 누적 룰과 별개로 독립 작동

### 5-4. self-healing 차단의 한계

T-14 wait이 self-healing 완전 차단 X (T-14 → T-28 → ... 거슬러 영향 가능). 단 cycle 단위 즉시 loop는 차단. 메모리 v1.4 cycle 12주 본격 평가에서 self-healing 잔여 효과 검증 (calibration self-loop 메타-검증, 메모리 정합).

---

## §6. Baseline 90일 Mean + Floor 0.45 + Cold-Start 0.5

### 6-1. Baseline 산출

`brain_distribution_evaluator.py` (P0 신설):

| Phase | Baseline source | 임계값 |
|---|---|---|
| Cold-start (0 ~ 50 trades) | `COLD_START_BASELINE = 0.50` | snapshot_n < `COLD_START_LIMIT = 50` |
| 정상 (50 trades 이상, 90일 미달) | 누적 baseline (effective_n 주입, P1 KI-11 정정) | snapshot_n ≥ 50 |
| 90일+ 운영 | 직전 90일 historical mean | data/metadata/backtest_stats_history.jsonl (KI-9 cron) |

### 6-2. Baseline Floor

`BASELINE_FLOOR = 0.45`.

- baseline 산출값이 0.45 미만이면 floor=0.45로 clamp
- 운영 의미: brain hit rate가 비정상적으로 낮을 때 baseline이 그 낮은 값을 기준 삼지 않도록 차단

### 6-3. STALE_THRESHOLD_HOURS = 6

`brain_distribution_evaluator.py` STALE 임계 6시간.

- backtest_stats.json mtime > 6h = stale 분기 (§3-stale 처리)

### 6-4. KI-9 history 누적 의존

`data/metadata/backtest_stats_history.jsonl` 신설 필수 (P2 병행 cron 명령서). 미존재 시 90일 historical mean 산출 불가 → 정상 phase의 baseline이 누적 baseline (effective_n)으로 대체 운영.

→ §16 인프라 path 정의 + KI-9 cron 명령서 직접 의존.

---

## §7. Tier σ 임계 + σ 단위 (KI-11 정정)

### 7-1. Tier 임계 정의

baseline ± k·σ:

| Tier | k | 통계 의미 |
|---|---|---|
| TIER0 (silent) | < 1 | baseline ± 1σ 이내 = 정상 noise |
| TIER1 | 1 ≤ k < 2 | ± 1~2σ = 약한 outlier (32% 사건) |
| TIER2 | 2 ≤ k < 3 | ± 2~3σ = 중간 outlier (5% 사건) |
| TIER3 | k ≥ 3 | ± 3σ 이상 = extreme outlier (0.27% 미만) |

### 7-2. σ 산출 단위 (KI-11 정정)

**v1.3 모호 → v1.4 명시**:

| Phase | σ source | 단위 |
|---|---|---|
| Cold-start (snapshot_n < 50) | binomial SE = √(p·(1-p)/n) | n = snapshot_n |
| 정상 (Gate A 통과 후) | binomial SE = √(p·(1-p)/n) | n = **cumulative_trades** (KI-11 정정) |
| 90일+ | historical σ (90일 hit_rate 표준편차) | data/metadata/backtest_stats_history.jsonl |

p = 0.5 (binomial fair coin baseline).

### 7-3. σ phase 진화 (KI-14 정합)

baseline.effective_n 주입 메커니즘:

- mock 시나리오: fetcher가 effective_n=None (또는 baseline_override 직접 주입) → 임계값 mock 직접 산출
- 운영 cold-start: effective_n = snapshot_n (P0 동작)
- 운영 정상 (Gate A 통과 후): effective_n = cumulative_trades (P1 정정)
- 운영 90일+: effective_n 무력화, historical σ 직접 산출

운영 정상 동작. spec drift 위험은 KI-14 (P1 보고)에서 명시.

### 7-4. Cold-Start 시 TIER3 비활성

cold-start phase (snapshot_n < 50) 시 TIER3 평가 비활성. baseline noise가 큼 = ±3σ 산출 신뢰도 낮음 = 운영 단계 4 phase TIER3_DISABLED와 정합 (§17 정합).

---

## §8. Gate A + Gate B + Idempotent (KI-12 정정)

### 8-1. Gate A — snapshot-pair 누적 trade

`GATE_A_MIN_TRADES = 20`.

- 정의: snapshot-pair 누적 trade 합계 ≥ 20
- 누적 source: `data/metadata/cross_link_cumulative_trades.json` (P1 신설, KI-10)
- 통과 시: σ 산출 단위가 cumulative_trades로 전환 (§7-2)

### 8-2. Gate B — pair 누적

`GATE_B_MIN_PAIRS = 30`.

- 정의: snapshot-pair 누적 ≥ 30 pair
- 통과 시: 90일 historical mean baseline 진화 시작 (§6-1)
- ROLLING_WINDOW_DAYS = 30과 단위 일치 (§9-2 누적 검증과 단위 일치)

### 8-3. Idempotent 누적 (KI-12 정정)

`_update_cumulative_trades()` 함수가 idempotent 보장 (P1 §결정사항 2):

- 같은 날 중복 호출 시 누적 X
- cron이 하루에 여러 번 도는 운영 시나리오 (예: trust_score가 매 cycle 마다 cross_link 호출) 시 첫 호출만 누적 반영
- 누적 단위 = "하루 1회"

### 8-4. Gate 통과 phase 매핑 (§17 정합)

| Phase (운영 단계) | Gate A | Gate B | 통과 일수 (snapshot-pair 1/일 가정) |
|---|---|---|---|
| 0~30일 INSUFFICIENT_DATA | 미통과 (대부분) | 미통과 | — |
| 30~50일 TIER3_DISABLED | 통과 시작 | 통과 시작 | A: ~3일 (20 trades), B: ~30일 (30 pairs) |
| 50일+ FULLY_ACTIVE | 통과 | 통과 | — |
| 90일+ historical | 통과 | 통과 + 90 pair | — |

운영 의미: Gate B 통과 = 30 pair 누적 = §9-2 누적 검증 활성 시점 (§9-2 정합).

---

## §9. Alert Tier 산출 — 3 Layer 분리 (분기 4 채택, v1.4 정정 핵심)

### 9-0. v1.3 → v1.4 변경 사실

**v1.3 §9 의도**: noise floor 5/3/1 누적 룰 (NOISE_FLOOR_TIER1=5 / TIER2=3 / TIER3=1).

**P0/P1 미구현 갭** (VERITY-S1-NOISE-FLOOR-INSPECT 보고, 2026-05-04): 
- NOISE_FLOOR 상수 3종 cross_link_layer.py:38-40에 선언만, 사용처 0건
- `_build_result()`는 max_tier 즉시 alarm 룰로 동작 → cycle 단위 single violation으로 verdict 강등 발동
- 결과: cry-wolf 발생 (시나리오 3 = TIER2 1건만으로 manual_review 강등)

**v1.4 분기 4 채택**: 3 layer 분리로 정정. Sprint 1.5 retraction 동반.

### 9-1. 1차 Layer — Cycle 단위 Dashboard 기록

**산출**: `cross_link_layer.py:_build_result()` 현재 max_tier 룰 유지.

```python
tier_rank = {"TIER1": 1, "TIER2": 2, "TIER3": 3}
max_tier = max(tier_rank.get(r.get("evaluation"), 0) for r in violations)
alert_tier = {0: None, 1: "yellow", 2: "orange", 3: "red"}[max_tier]
```

**용도**: dashboard / log 기록 only.
- AdminDashboard 카드에 cycle 단위 alert_tier 표시
- 운영자가 cycle 단위 패턴 디버깅 가능 (메모리 운영 사실: "왜 alert 안 뜨지" 의심 발생 시 1차 참조)
- **verdict 영향 X. PM trigger X.**

**cry-wolf 위험 없음**: dashboard만 보임, brain 운영/PM 통보 영향 0.

### 9-2. 2차 Layer — 30 Pair 누적 Verdict 강등

**산출**: rolling 30 pair 내 Tier별 violation count 누적.

**source**: `data/metadata/cross_link_violations.jsonl` (Sprint 1.5 신설 또는 기존 영속화 활용).

**임계** (NOISE_FLOOR 상수 활용):

| Tier | 누적 임계 | σ 의미 | 강등 결과 | 통계 근거 |
|---|---|---|---|---|
| TIER1 | ≥ 5건 / 30 pair | ±1~2σ | manual_review | 약한 outlier 5건 누적 = 통계적 의미 발생 |
| TIER2 | ≥ 3건 / 30 pair | ±2~3σ | manual_review | 중간 outlier 3건 누적 = 5% 사건이 6배 이상 = 의미 발생 |
| TIER3 | ≥ 1건 | ±3σ extreme | hold | 0.27% 사건 = 1건도 우연 X |

**TIER3 1건 hold 근거**: 통계적으로 ±3σ는 우연 가능성 거의 0. cry-wolf 위험 없음. 단 cold-start phase (§7-4)에서 baseline noise가 커서 ±3σ 산출 신뢰도 낮음 → §17 운영 단계 4 phase에서 0~30일 / 30~50일 TIER3 자체 비활성으로 처리.

**활성 시점**: Gate B 통과 후 (§8-4 정합). 30 pair 미달 시 §9-2 자동 비활성.

### 9-3. 3차 Layer — PM Trigger Escalation

**산출**: §9-2 verdict 강등 발생 시 §11 channel 발동.

**dispatch 룰**:
- §9-2 manual_review 강등 발동 → §11 Telegram CRITICAL 즉시 dispatch
- §9-2 hold 강등 발동 → §11 Telegram CRITICAL 즉시 dispatch
- §9-1 max_tier 변동만 → §11 dispatch X (1차 layer는 PM 통보 X)

**용도**: PM 인지. brain 운영 영향 X (이미 §9-2에서 verdict 강등 처리).

### 9-4. instant_hold 룰과 분리

| 룰 | trigger | 결과 | 영속화 source |
|---|---|---|---|
| §5 instant_hold | silent_pass rolling+this ≥ 3 | hold | rolling silent_pass count |
| §9-2 verdict 강등 | TIER1 ≥5 / TIER2 ≥3 / TIER3 ≥1 누적 | manual_review or hold | cross_link_violations.jsonl |
| §9-3 PM trigger | §9-2 강등 발동 시 | Telegram dispatch | (§11 channel) |

세 룰 독립 작동. OR 관계.

### 9-5. 1차 dashboard layer가 verdict 영향 X 보장

**Sprint 1.5 retraction 핵심**: `_build_result()` 함수에서 max_tier 룰의 verdict 영향 제거.

P0 코드 현재 동작:
- max_tier=2 (orange) → verdict=manual_review
- max_tier=3 (red) → verdict=hold

Sprint 1.5 정정 후:
- max_tier=N (yellow/orange/red) → alert_tier 기록만, verdict 산출 input X
- verdict 산출 input = §5 instant_hold + §9-2 누적 강등 only

---

## §10. Tier 3 Rate Limit — 일일 3건

`TIER3_DAILY_LIMIT = 3` (cross_link_layer.py:35 동급).

### 10-1. 정의

cycle 당 TIER3 violation 산출 일일 누적 ≥ 3건이면 추가 TIER3 산출 차단 (rate limit).

### 10-2. 운영 의미

TIER3 = ±3σ extreme outlier. 정상 운영에서 일일 3건 이상 발생 = 시스템 자체 이상 (예: backtest_stats 산출 버그).

rate limit 도달 시:
- 추가 TIER3 산출 X
- 별도 system alert (PM 통보 channel = §11 검토 대상)
- 시스템 자체 이상 의심 = brain 운영 정지 검토

### 10-3. 분기 4 정합

§9-2에서 TIER3 1건 즉시 hold = rate limit 3건 도달 전에 이미 hold 강등 발동 = §10 rate limit이 거의 발동 안 함.

§10 발동 시점 = TIER3 1건 hold 후에도 계속 TIER3 산출 = 시스템 자체 이상 시그널 (정상 운영 시나리오 아님).

---

## §11. PM 검토 Trigger 채널 분리 (v1.4 신규)

### 11-0. v1.3 모호 사실

v1.3 §11 채널 표 추정: Telegram + 주간 PDF 둘 다 박혀 있으나 dispatch 조건 명문화 없음 → cycle 마다 둘 다 발동? 일부만? 모호.

**v1.4 정정**: 채널 분리 + dispatch 조건 명시.

### 11-1. Telegram 즉시 Dispatch (CRITICAL only)

**dispatch 조건**:
- §9-3 PM trigger escalation 발동 (§9-2 verdict 강등 시)
- §5 instant_hold 발동
- §3 STALE_UNKNOWN 산출 (산출 자체 불가 상태)
- §10 TIER3 rate limit 도달

**dispatch 단위**: cycle 단위, 발동 즉시.

**메시지 양식 (예상)**:
```
[VERITY CROSS-LINK CRITICAL]
Cycle: {cycle_id}
Severity: {manual_review|hold|stale_unknown|rate_limit}
Trigger: {§9-2 TIER2 누적 4건|§5 instant_hold 3건|...}
Action: PM 검토 의무
Dashboard: {url}
```

### 11-2. 주간 PDF 누적 (전체 violation trend)

**dispatch 조건**: 매주 1회 batch (예: 매주 월요일 09:00 KST).

**내용**:
- 해당 주 §9-1 alert_tier 변동 trend (yellow/orange/red 발생 빈도)
- §9-2 verdict 강등 발생 list (이미 Telegram dispatch 했어도 재게재)
- baseline 진화 (cold-start → 누적 → historical mean phase 진행)
- Tier 발동 빈도 (메모리 v1.4 cycle 12주 본격 평가 source data)
- regime 완화 효과 (해당 시)

**dispatch 단위**: 주간 batch.

### 11-3. 채널 분리 정신

| 채널 | 목적 | 발동 빈도 |
|---|---|---|
| Telegram 즉시 | CRITICAL 인지 | cycle 단위, escalation 발동 시만 |
| 주간 PDF | 패턴 인지 + 평가 source | 주 1회 |

**alarm fatigue 방지** (메모리 룰 7 cry-wolf 차단 정합): Telegram이 매 cycle 폭격 X. 진짜 critical만.

**12주 본격 평가 source 정합** (메모리 v1.4 cycle 정의): 주간 PDF가 12주 누적되면 운영 데이터 기반 재정의 source.

### 11-4. v1.3 §11 본문과 차이 (확인 미가능)

v1.3 본문 미확보 = 본 §11이 v1.3 표를 정정한 것인지 신규 박은 것인지 미확인. v1.5 정정 가능.

---

## §12. 처리 정책 비대칭 (역추정 — 위험)

### 12-0. v1.3 추정 사실

`brain_distribution_evaluator.py:1-9` 헤더 인용: "임계: baseline ± kσ (silent_pass / cry_wolf 대칭, 단 처리 정책은 비대칭)".

**대칭**: silent_pass (baseline - kσ 미달, 즉 hit rate 낮음) + cry_wolf (baseline + kσ 초과, 즉 hit rate 높음) 모두 같은 σ 임계 사용.

**비대칭 (처리)**: P0 코드 동작 역추정:

| 방향 | 의미 | §9-2 누적 임계 | 강등 결과 |
|---|---|---|---|
| silent_pass (baseline - kσ) | hit rate 낮음 = brain 산출 의심 | TIER1≥5 / TIER2≥3 / TIER3≥1 | manual_review or hold |
| cry_wolf (baseline + kσ) | hit rate 높음 = backtest_stats 의심 | (분기 4 미정 — 추정 위험 영역) | TBD |

### 12-1. 처리 비대칭의 운영 의미

- **silent_pass**: brain trust 산출이 hit rate 낮음을 표시. 운영 정지 강한 분기 (manual_review/hold).
- **cry_wolf**: brain trust 산출이 hit rate 높음을 표시. 의심 신호이긴 하나 운영 정지보다는 PM 검토 후 backtest_stats 자체 검증 분기.

**§5 instant_hold**: silent_pass 누적에만 적용 (cry_wolf 누적은 instant_hold X). cry_wolf는 brain 운영 차단보다 backtest_stats 산출 자체 검증이 우선.

### 12-2. 추정 위험 (v1.5 정정 가능)

**위험 영역**:
- cry_wolf의 §9-2 누적 임계가 silent_pass와 같은지 다른지 v1.3 본문 미확인
- cry_wolf 강등 결과 (manual_review? PM trigger only? 다른 처리?) 미확인

**v1.4 잠정 채택**: cry_wolf 누적도 §9-2 동일 임계 (TIER1≥5 / TIER2≥3 / TIER3≥1) 적용. 단 강등 결과는 manual_review only (hold 미발동, brain 운영 정지 분기 X). 

**검증 방법**: P0 코드 `_evaluate_cry_wolf()` 또는 동급 함수 동작 확인 명령서 (Sprint 1.5 P0 산출물에 포함).

### 12-3. P0 mock 시나리오 5 (cry_wolf) 정합

mock 시나리오 5: TIER2 cry_wolf 1건 → hold (변동 X) 기대. P0 동작 확인 결과 = max_tier 즉시 hold 강등 (분기 4 정정 대상).

분기 4 채택 후 시나리오 5 재작성 필요 (Sprint 1.5 P1 mock 시나리오 재작성 범위).

---

## §13. 운영 인터페이스 vs Mock Helper 분리 (v1.4 신규, KI-13 정합)

### 13-1. 분리 사실

P1에서 `baseline_override` 키가 시나리오 6 (baseline floor 검증) 용으로 추가됨.

**확정**: `baseline_override`는 **mock 검증 helper**. 운영 인터페이스 X.

### 13-2. 운영 호출 path

`run_cross_link()` 운영 호출 시 인자:

| 인자 | 사용 | 운영 호출? |
|---|---|---|
| `backtest_stats_fetcher` | Primary source 주입 | ○ |
| `verification_report_fetcher` | Secondary source 주입 | ○ (fallback only) |
| `trust_log_fetcher` | KI-7 path alias 처리 | ○ |
| `history_fetcher` | KI-9 cron 산출 history 주입 | ○ |
| `baseline_override` | mock 직접 주입 | **X — mock only** |

### 13-3. 운영 호출 차단 의무

`baseline_override` 키 사용은:
- mock 시나리오 (`tests/mock/cross_link/scenario_*.json`) only
- P0/P1 tests 검증 helper only
- 운영 호출 path (`api/main.py` Brain cycle) 절대 X

**spec drift 차단**: P2 wire 명령서 작성 시 `run_cross_link()` 운영 호출 부 인자 list에 `baseline_override` 절대 박지 말 것 명시 (P2 명령서 §"비-인터페이스" section).

### 13-4. KI-14 정합

`baseline.effective_n` 주입은 fetcher가 `baseline_override` 명시적으로 던지지 않은 경우에만 작동.

mock 시나리오 6: `baseline_override` 사용 → effective_n 주입 무력화 → mock 직접 sigma 산출.
운영: `baseline_override` 미사용 → effective_n 주입 작동.

90일+ 운영: history 누적되어 baseline이 historical σ 산출 → effective_n 주입 자체 무력화 (자연 전환).

---

## §14. Calibration 주기 (v1.4 신규, 메모리 cycle 2단계 분리 정합)

### 14-1. v1.4 cycle 2단계 분리

메모리 v1.4 cycle 정의:

| Cycle | 목적 | 시점 | 평가 범위 |
|---|---|---|---|
| **Mid-review** | Gate 도달 검증 | 6주 후 | 평가 layer 작동 확인 (본격 평가 X) |
| **본격** | 운영 데이터 기반 재정의 | 12주 후 | Tier 발동 빈도 / baseline 진화 / regime 완화 효과 / 7 sub-factor ground truth 매핑 / stagnation alert / calibration self-loop 메타-검증 |

### 14-2. Mid-review (6주) 검증 항목

- Gate A (cumulative_trades ≥ 20) 통과 여부
- Gate B (snapshot-pair ≥ 30) 통과 여부
- §9-2 누적 verdict 강등 layer 작동 검증
- §11 Telegram dispatch 1회 이상 발동 검증
- 주간 PDF 6회 발행 검증

**미통과 시**: Sprint 1.5 retraction 또는 추가 fix 명령서 작성.

### 14-3. 본격 (12주) 평가 항목

- **Tier 발동 빈도**: TIER1/TIER2/TIER3 각각 cycle 당 평균 발동 빈도 → NOISE_FLOOR 5/3/1 임계값 재조정 source
- **baseline 진화**: cold-start → effective_n → historical mean 진행 정상성
- **regime 완화 효과**: market regime 변동 시 baseline floor 0.45 효과
- **7 sub-factor ground truth 매핑**: 1차 brain_distribution 외 추가 6개 sub-factor 도입 source
- **stagnation alert**: trust score 변동 0인 cycle 누적 검증 (별개 alert layer 도입 검토)
- **calibration self-loop 메타-검증**: cross-link 자체 산출이 brain 운영에 미치는 feedback 영향 잔여 검증 (§5 self-healing 차단 효과 측정)

### 14-4. v1.5 진입 시점

본격 평가 12주 후 v1.5 spec 진입 검토. 단 Sprint 1.5 retraction 발동 시 v1.5 진입은 그 처리 후로 미룸.

---

## §15. Unit 통일 — 0~1 비율

### 15-1. 모든 cross-link 산출 단위

| 산출 | 단위 | 예시 |
|---|---|---|
| baseline | 0~1 비율 | 0.50 (cold-start) / 0.62 (정상 누적) |
| hit_rate | 0~1 비율 | 0.55 (backtest_stats.periods.14d.hit_rate) |
| σ | 0~1 단위 비율 | 0.091 (cumulative_trades=30 가정 시) |
| Tier 임계 | 0~1 비율 | baseline ± k·σ |
| 9번째 sub-factor | 0~1 비율 | 1.0 (ready) / 0.5 (manual_review) / 0.0 (hold) |

### 15-2. 백분율 사용 금지

- ❌ "55%" 형태 금지
- ✅ "0.55" 비율 형태 강제

운영 의미: trust_score.py와의 인터페이스 통일. 단위 변환 코드 0 = 버그 위험 0.

---

## §16. 인프라 Path 정의 (v1.4 신규)

### 16-1. 영속화 path 일람

| Path | 신설 시점 | 역할 | Sprint |
|---|---|---|---|
| `data/metadata/backtest_stats.json` | 기존 | Primary source (§1-1) | — |
| `data/metadata/backtest_stats_history.jsonl` | **KI-9 cron 신설 필수** | 90일 historical mean source (§6-1) | **KI-9 cron 명령서 (P2 병행)** |
| `data/metadata/trust_log.jsonl` | 기존 (KI-7 path alias) | trust_score 산출 log | — |
| `data/metadata/cross_link_cumulative_trades.json` | P1 신설 (KI-10) | Gate A 누적 (§8-1) | Sprint 1 P1 |
| `data/metadata/cross_link_violations.jsonl` | Sprint 1.5 신설 또는 기존 활용 | §9-2 누적 검증 source + AdminDashboard join | Sprint 1.5 P0 |

### 16-2. KI-9 cron 명령서 의존

`data/metadata/backtest_stats_history.jsonl` 신설은 별도 cron 명령서 작업.

- 매일 1회 backtest_stats.periods.14d snapshot append
- 90일 retention (LRU 또는 mtime 기준)
- idempotent 보장 (같은 날 중복 append X — KI-12 패턴 재사용)
- Railway cron $5 plan 정합 (메모리 운영 사실)

### 16-3. AdminDashboard Join

방식 B (별도 모듈) 영속화 분리:

- `trust_score.jsonl` ← trust_score.py 산출
- `cross_link_violations.jsonl` ← cross_link_layer.py 산출

AdminDashboard에서 두 jsonl join (cycle_id 기준) → cross-link 결과가 trust 산출에 미친 영향 운영자 가시화.

### 16-4. Rotation 정책

- `cross_link_violations.jsonl`: 90일 retention (cron 또는 P2 wire에서 처리)
- `cross_link_cumulative_trades.json`: 단일 파일 (rotation X, idempotent 누적만)
- `backtest_stats_history.jsonl`: 90일 retention (KI-9 cron 처리)

### 16-5. 신규 인프라 자산 cohabitation 검토 (메모리 룰 10 정합)

본 spec은 신규 service / 신규 Railway project 생성 X. 기존 자산 활용:

- VERITY service 내 cross_link_layer.py (cohabitation, 신규 service X)
- 영속화는 기존 `data/metadata/` 디렉토리 활용
- cron은 Railway tranquil-healing project 내 신규 cron job으로 추가 (메모리 운영 사실: $5 plan 잔여 $10)

---

## §17. 운영 단계 4 Phase (v1.4 신규, 메모리 정합)

### 17-1. Phase 정의

| Phase | 시점 | 활성 layer | 비활성 layer |
|---|---|---|---|
| **0~30일 INSUFFICIENT_DATA** | Gate A/B 미통과 | §9-1 dashboard only | §9-2 누적 / TIER3 / §11 Telegram (대부분) |
| **30~50일 TIER3_DISABLED** | Gate A/B 통과 시작 | §9-1 + §9-2 (TIER1/TIER2만) | TIER3 / cold-start baseline |
| **50일+ FULLY_ACTIVE** | snapshot_n ≥ 50 | §9-1 + §9-2 (TIER1/TIER2/TIER3) + §11 | — |
| **90일+ HISTORICAL** | history 누적 90일 | §9-1 + §9-2 + §11 + historical σ baseline | cold-start / effective_n 주입 |

### 17-2. Phase 자동 전환

전환 조건은 코드 자체에서 자동 판단:

- INSUFFICIENT_DATA → TIER3_DISABLED: Gate A (cumulative_trades ≥ 20) 통과 시
- TIER3_DISABLED → FULLY_ACTIVE: snapshot_n ≥ COLD_START_LIMIT (50) 도달 시
- FULLY_ACTIVE → HISTORICAL: backtest_stats_history.jsonl 누적 ≥ 90 entry 도달 시

### 17-3. Phase별 운영 의미

**INSUFFICIENT_DATA (0~30일)**:
- §9-1 dashboard만 작동 = cycle 단위 alert_tier 표시 only
- verdict 산출은 §5 instant_hold만 작동 (silent_pass 누적 ≥3)
- §11 Telegram dispatch는 §3 STALE_UNKNOWN / §10 rate limit / §5 instant_hold 발동 시만 (§9-3 대부분 비활성)
- "왜 alert 안 뜨지" 의심 시 1차 참조 phase

**TIER3_DISABLED (30~50일)**:
- §9-2 누적 layer 활성 시작 (TIER1/TIER2만)
- TIER3 산출 자체 비활성 (baseline noise 큼, ±3σ 산출 신뢰도 낮음)
- §11 Telegram dispatch 정상 발동

**FULLY_ACTIVE (50일+)**:
- 모든 layer 정상 운영
- baseline은 누적 baseline (effective_n 주입, P1 KI-11 정정)

**HISTORICAL (90일+)**:
- baseline이 historical σ로 진화 (effective_n 주입 자연 무력화, KI-14 정합)
- cold-start fallback 0.5 → system historical mean 전환

### 17-4. Phase 표시 의무

`run_cross_link()` 산출 결과에 `phase` 필드 박음:

```json
{
  "verdict": "ready",
  "phase": "FULLY_ACTIVE",
  "alert_tier": "yellow",
  ...
}
```

운영 의미: AdminDashboard에서 phase 표시 → 운영자가 현재 운영 단계 즉시 인지 가능.

---

## §18. 진입 OK 체크리스트 (TBD)

v1.5 작성 시 보충 예정. v1.4에서는 미작성.

---

## §19. 베테랑 인지 사항 (TBD)

v1.5 작성 시 보충 예정. v1.4에서는 미작성.

---

## 부록 A. v1.3 → v1.4 변경 요약 (재게재)

| 항목 | 변경 분류 | 영향 Sprint |
|---|---|---|
| §3 verdict 강등 조건 | §9-2 누적 조건으로 변경 | Sprint 1.5 retraction |
| §7 σ 산출 단위 | KI-11 cumulative_trades 명시 | Sprint 1 P1 (완료) |
| §8 Gate A idempotent | KI-12 명시 | Sprint 1 P1 (완료) |
| §9 alert tier 산출 | **분기 4 채택, 3 layer 분리** | **Sprint 1.5 retraction** |
| §11 PM trigger 채널 | 분리 명시 (Telegram / 주간 PDF) | P2 wire |
| §12 처리 정책 비대칭 | 역추정 명시 (위험 영역) | Sprint 1.5 검증 |
| §13 mock helper 분리 | KI-13 명시 | P2 wire |
| §14 calibration 주기 | 메모리 cycle 2단계 명시 | — |
| §16 인프라 path | 신규 명시 | KI-9 cron + Sprint 1.5 |
| §17 운영 단계 4 phase | 신규 명시 | — |
| STALE_UNKNOWN | 4번째 phase 정식 | Sprint 1 P1 (완료) |

---

## 부록 B. 신규 KI 누적 (v1.4 발견)

| KI | observed/hypothesis | 처리 |
|---|---|---|
| KI-15 | observed: P0 NOISE_FLOOR 상수 미구현 갭 | Sprint 1.5 retraction |
| KI-16 | observed: P0 max_tier 즉시 강등 = cry-wolf | Sprint 1.5 retraction |
| KI-17 | hypothesis: §12 cry_wolf 처리 비대칭 형태 | Sprint 1.5 P0 검증 |

---

## 부록 C. 다음 작업 묶음

본 spec 작성 후 발행 산출물 3건:

1. **Sprint 1.5 retraction 명령서** — §9 분기 4 구현 (P0 + P1)
2. **KI-9 history cron 명령서** — backtest_stats_history.jsonl 신설
3. **P2 wire 명령서** — Sprint 1.5 종료 후 진입 조건부

---

**END of v1.4 DRAFT.**

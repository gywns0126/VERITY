# Cross-link Prerequisite 검증 보고서

**문서 ID**: VERITY-CROSSLINK-PREREQ-20260503 응답
**일자**: 2026-05-03
**검증 범위**: 최근 14일 (cross-link operating window)
**저장 path**: data/verification/crosslink_prereq_report_20260503.md
**모드**: read-only (수정 0건)

---

## 0. Schema 실측 결과 (§1)

### grep 4종 결과

| 항목 | 가정 (명령서) | 실측 | 일치 |
|---|---|---|---|
| verification 파일 | `data/verification_report.json` | `data/verification_report.json` (2606B, 2026-05-03 10:36) | ✅ |
| hit rate 필드명 | `hit_rate` | `hit_rate`, `hit_rate_pct`, `hit_rate_7d/14d/30d`, `hit_rate_net`, `weighted_positive_hit_rate`, `backtest_hit_rate_14d`, `win_rate` (sim용) — **다층 명명** | ⚠️ 부분 |
| OOS gate 모듈 | `backtest_archive.py` 가정 | **실측: `api/intelligence/strategy_evolver.py:1245~1274`** (`STRATEGY_MIN_OOS_DAYS=30`, `rejected_by_oos`) — backtest_archive 안에는 OOS gate 없음 | ❌ 불일치 |
| evaluate 함수 | `evaluate_past_recommendations` | `api/intelligence/backtest_archive.py:119` — 일치 | ✅ |

### 가정 vs 실측 일치도: **3/4 = 75%**

핵심 불일치 1건:
- **OOS Sharpe gate 위치가 다름.** 명령서 가정은 backtest_archive 였으나, 실제는 `strategy_evolver.py`. 이 차이가 §3 판정 분기에 직접 영향 — gate reject 가 hit rate 산출과 별개 layer 라는 사실로 이어짐.

추가 발견 (예상 외 schema):
- `data/strategy_registry.json` — OOS gate reject 카운터가 여기 누적. `cumulative_stats.total_proposals = 27`, `accepted = 0`. 메모리에 박힌 "27 cycle reject" 의 정체.

---

## 1. Check 결과

### Check 1: 데이터 존재 여부

```
verification_report.json
  - 실측 path: data/verification_report.json
  - 존재: YES (2606B)
  - generated_at: 2026-05-03 07:32:30+09:00
  - hit_rate_7d: null
  - hit_rate_14d: null            ← 모두 null
  - hit_rate_30d: null
  - sharpe_14d: null
  - delisted_count_30d: 0

backtest_stats.json (verification_report 의 SOURCE)
  - 실측 path: data/backtest_stats.json
  - 존재: YES (9288B)
  - updated_at: 2026-05-03 16:11
  - periods.7d:  hit_rate=null,  total_recs=0  (snapshot_date 2026-04-25, 추천 0건)
  - periods.14d: hit_rate=50.0%, total_recs=8, hits=4 (snapshot 2026-04-18)
  - periods.30d: hit_rate=42.9%, total_recs=7, hits=3 (snapshot 2026-04-05)
  - recommendations[]: 실제 ticker 추적 (HPSP +15.1%, SK +12.73%, SK하이닉스 등)

backtest_gap.jsonl
  - 160 entries (2026-04-27 ~ 2026-05-02)
  - 모두 backtest_exit/sim_exit = null (entry 만 기록, exit 미실현)
  - VAMS auto-trade BUY/SELL 로그 — verification 과 별개 trail
```

**중요한 모순 발견**: verification_report.json (07:32 생성) 의 hit_rate 가 모두 null 인데, 같은 날 더 늦게 갱신된 backtest_stats.json (16:11) 에는 14d=50% / 30d=42.9% 가 numeric 으로 채워져 있음. 즉 **verification_report 는 빈 값/fallback 이 아니라 stale snapshot**. SOURCE (backtest_stats) 에는 actual data 있음.

### Check 2: Hit rate 분포 sanity check

backtest_stats.json 의 14d / 30d periods 기준 (verification_report 의 SOURCE):

| 항목 | 14d | 30d |
|---|---|---|
| hit_rate | 50.0% | 42.9% |
| total_recs | 8 | 7 |
| hits | 4 | 3 |
| max_return | +15.10% | +6.67% |
| min_return | -7.01% | -4.78% |
| avg_return | +3.69% | +0.97% |
| sharpe | 0.46 | 0.25 |

- **분포 있음**: max~min spread = 14d 22.11%p, 30d 11.45%p. unique return 값 8 / 7 (각 ticker 별 다른 return).
- **고정값 / 0 누적 아님**: 명시적 actual ticker 추적 (HPSP +15.1, SK +12.73, ...).
- 50% / 42.9% 는 random baseline 0.5 와 우연 인접 가능하나, return 분포가 비대칭 (avg +3.69% > 0) 이라 random 이 아님.
- 다만 small sample (n=8 / n=7) — 통계 신뢰도는 낮음.

### Check 3: actual trade 기반인지 검증

- **메타 필드 풀 존재**:
  - `rec_price` (T+1 시가 보정 — Sprint 11 결함 1 후속, 2026-05-01)
  - `current_price` (today_snap 기준)
  - `return_pct_gross` / `return_pct_net` (slippage + TX 보정)
  - `slippage_pct` (시총 tier 기반 0.1/0.3/0.7%)
  - `hit_gross` / `hit_net` 별도 노출
  - `delisted_count` (survivorship 차단)
- **누적 trade 개수 (최근 14일 lookback)**: 14d=8건 + 30d=7건 = 15건 (단, snapshot 날짜 다름, 중복 가능)
- **명령서 schema 와의 차이**: 명령서는 "최근 14일 entry" 가정. 실측은 "14일 전 1 snapshot 의 BUY 추천 → 14일 후 평가". evaluate_past_recommendations 는 lookback period 마다 **1 snapshot** 평가 (rolling window 아님).
- 14d period 의 "8건" 은 2026-04-18 snapshot 의 BUY 8건을 today (2026-05-03) 가격으로 평가한 결과.

### Check 4: OOS Sharpe gate 영향 확인

**핵심 발견 — 명령서 가정 정정**:

OOS gate (`STRATEGY_MIN_OOS_DAYS=30`, `rejected_by_oos`) 는 `strategy_evolver.py` 에 있고, **strategy proposal (가중치 갱신안) 의 채택 거절** 만 담당. `evaluate_past_recommendations` (hit rate 산출) 와 **완전히 별개 layer**.

증거:
- `data/strategy_registry.json`:
  - `cumulative_stats.total_proposals = 27` ← 메모리의 "27 cycle reject"
  - `accepted = 0`, `rejected = 0` (counter bug 의심 — 실제 reject 발생 중)
  - `growth_runs.weekly`: W16/W17/W18 모두 `rejected_by_backtest`
  - `versions[]` = v1 한 개 (2026-04-08 이후 가중치 진화 0회)
- 그러나 backtest_stats.json 는 같은 기간 동안 **정상 hit rate 산출** (14d=50%, 30d=42.9%).

**OOS gate reject 의 hit rate 영향 = 0%.** Brain v5 가중치는 v1 에서 동결된 채로 운영 중이지만, 그 v1 가중치로 매일 추천이 나오고 추천 → T+N 평가 cycle 은 정상.

⚠️ 명령서 8번 (14일 lookback 한계) 의 가정 — "OOS gate reject 가 verification_report 를 빈 값으로 만든다" — **사실관계 부정확**. 실제로는:
- verification_report 가 null 인 이유 = stale (SOURCE 갱신 전 snapshot)
- OOS gate reject = strategy proposal 채택만 막음, hit rate 와 무관

---

## 2. 종합 판정

### **A. ACTUAL_DATA_OK**

| 기준 | 임계 | 실측 | 통과 |
|---|---|---|---|
| Check 1: actual entries 비율 | ≥ 80% | 14d 8/8=100%, 30d 7/7=100% (SOURCE 기준) | ✅ |
| Check 2: 분포 unique | > 5 | 14d 8 unique returns, 30d 7 unique | ✅ |
| Check 3: trade 추적 active | active | T+1 보정 + ticker 별 메타 풀 추적 | ✅ |
| Check 4: OOS gate reject 영향 | < 20% | **0%** (별개 layer) | ✅ |

**근거**: ground truth 데이터(`backtest_stats.json`)는 actual numeric 값으로 살아있음. `verification_report.json` 의 null 은 cron 순서 stale 이지 fallback 아님. OOS gate 27 reject 는 strategy proposal 채택 layer 의 정체 — hit rate 산출과 별개로 영향 없음.

---

## 3. 다음 step 권고

**[A] cross-link v1.1 재정의 진입 OK.** PM님 승인 후 Sprint 1 명령서 작성.

단, cross-link v1.1 명령서에 다음 known_issue 4건 명시 의무:

| # | 분류 | 내용 |
|---|---|---|
| KI-1 | observed | `verification_report.json` 갱신 시점이 SOURCE(`backtest_stats.json`) 보다 빠름 (07:32 vs 16:11). cross-link 가 verification_report 를 source-of-truth 로 잡으면 stale 데이터 cross-check 함정. → **cross-link source 는 backtest_stats 또는 generate_verification_report() 직호출** 로 잡아야 함. |
| KI-2 | hypothesis | `data/strategy_registry.json` 의 `cumulative_stats.rejected = 0` 인데 실제 reject 발생 (W16/W17/W18 + 27 proposals). counter increment 누락 가능성. cross-link 와 직접 무관하나 OPS 별건 박아둘 것. |
| KI-3 | observed | 명령서 가정 "OOS Sharpe gate 가 hit rate 를 fallback 으로 만든다" 부정확. OOS gate (strategy_evolver) 와 hit rate 산출 (backtest_archive) 은 별개 layer. → cross-link v1.1 재정의 시 "OOS gate reject ↔ hit rate degradation" 가설 폐기. |
| KI-4 | observed | `evaluate_past_recommendations` 의 schema 는 "lookback period 마다 1 snapshot" (rolling 14일 entry 아님). 14d total_recs=8 은 2026-04-18 snapshot 1건의 BUY 8건. → cross-link operating window 정의 시 "snapshot-pair 비교" 모델로 명시 필요. 진짜 "최근 14일 entry rolling" 원하면 별도 집계 layer 필요. |

추가 권고 (lookback 의식적 한계 §8):
- 14일 cross-link 진입은 OK. OOS gate 수리는 cross-link 와 별개 우선순위로 분리. 만약 strategy proposal 채택 0/27 자체를 풀고 싶다면 별도 명령서에서 lookback 30~90일 로 확장해 진단.
- counter bug (KI-2) 는 cross-link 와 분리된 OPS 사이드 트랙.

---

## 4. Raw evidence

### data/verification_report.json (관련 발췌, generated_at 2026-05-03 07:32)
```json
{
  "performance": {
    "hit_rate_7d": null,
    "hit_rate_14d": null,
    "hit_rate_30d": null,
    "sharpe_14d": null,
    "delisted_count_30d": 0
  },
  "feedback_loop_status": "closed",
  "generated_at": "2026-05-03 07:32:30.525828+09:00"
}
```

### data/backtest_stats.json (관련 발췌, updated_at 2026-05-03 16:11)
```json
{
  "periods": {
    "14d": {"hit_rate": 50.0, "avg_return": 3.69, "sharpe": 0.46,
            "total_recs": 8, "hits": 4, "max_return": 15.1, "min_return": -7.01,
            "snapshot_date": "2026-04-18"},
    "30d": {"hit_rate": 42.9, "avg_return": 0.97, "sharpe": 0.25,
            "total_recs": 7, "hits": 3, "max_return": 6.67, "min_return": -4.78,
            "snapshot_date": "2026-04-05"}
  }
}
```

### data/strategy_registry.json (OOS gate 누적 카운트)
```json
{
  "current_version": 1,
  "cumulative_stats": {
    "total_proposals": 27,
    "accepted": 0,
    "rejected": 0,
    "hit_rate_pct": 0
  },
  "growth_runs": {
    "weekly": {
      "2026-W16": {"status": "rejected_by_backtest"},
      "2026-W17": {"status": "rejected_by_backtest"},
      "2026-W18": {"status": "rejected_by_backtest"}
    }
  }
}
```

### api/intelligence/backtest_archive.py:333-409
generate_verification_report() 가 evaluate_past_recommendations() 호출 → periods 의 hit_rate 를 그대로 인용. fallback 로직 없음. null 의 원인은 SOURCE side 의 cron 갱신 전 호출 (또는 list_available_dates 가 비었을 때 line 141 의 early return).

### api/intelligence/strategy_evolver.py:1245-1274
```python
oos_days = max(STRATEGY_MIN_OOS_DAYS, 30)
...
if oos_days < STRATEGY_MIN_OOS_DAYS:
    result["status"] = "rejected_by_oos"
    result["reason"] = f"OOS 기간 부족: {oos_days}일 < 최소 {STRATEGY_MIN_OOS_DAYS}일"
```
이 reject 는 strategy proposal 채택 가드. hit rate 산출과 무관한 별도 layer.

---

**STOP TRIGGER 발동 — 보고서 출력 완료. 후속 작업 시작 금지 (§5/§6).**

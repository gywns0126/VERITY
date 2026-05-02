# Capital Data Hotfix Sprint 명세 (의제 c5e8f9a2)

**작성**: 2026-05-03 00:50 KST (Round 4 보강 1)
**의제 id**: c5e8f9a2 (P0+ — Round 3 격상)
**예상 시간**: ~2시간
**참조**: `docs/SILENT_ERRORS_20260502.md` Error 5 / `docs/OPS_VERIFICATION_20260502.md` §13 / `docs/CAPITAL_EVOLUTION_MONITOR_SPEC.md`

---

## 0. Sprint 목표

`vams.total_value` + holdings `avg_price` 운영 데이터 결함 즉시 정정. 자본 진화 컨셉의 *측정 baseline* 확보 → capital_evolution_monitor + Tier 전환 자동 감지 + holdings 손익 정확 산출 mechanism 작동 가능 상태로 복원.

---

## 1. 진입 조건

### 1-1. Phase 0 verdict 시나리오 분기 (심각도 2 결정 — Round 4 보강)

**시나리오 A — Phase 0 verdict = ok**:
- 즉시 진입 권장. 단일 변수 통제 무관.

**시나리오 B — Phase 0 verdict = fail**:
- *격리 검증 통과 후* 조건부 진입.
- 격리 실패 시 → 5/17 후 (Phase 0 rollback 처리 후) 로 강제 연기.

**시나리오 C — Phase 0 verdict = monitoring (+7일 연장)**:
- **보류** — Phase 0 verdict 확정 후 시나리오 A 또는 B 로 재평가.

### 1-2. 격리 검증 항목 (시나리오 B 진입 전 의무)

| # | 검증 항목 | 통과 기준 |
|---|---|---|
| 1 | `vams/engine.py` 의 avg_price 저장 라인 location 식별 | `grep -n "avg_price" api/vams/engine.py` 결과 위치 명시 |
| 2 | `vams/engine.py` 의 `atr_method_at_entry` 저장 라인 location 식별 | T1-22 P-03 commit (c7f34a8) 의 영속화 위치 |
| 3 | 두 라인 *함수 분리* 확인 | avg_price 가 `execute_buy` / atr_method_at_entry 가 별도 함수 (또는 별도 dict update 블록) |
| 4 | 호출 chain *독립* 확인 | `execute_buy` → avg_price 저장 vs `check_stop_loss` → atr_method 사용 — 독립 chain 검증 |
| 5 | 격리 통과 → hotfix 진입 / 격리 실패 → **5/17 후로 강제 연기** | Phase 0 A/B 비교 baseline 보호 의무 |

### 1-3. 예외 사유 (시나리오 B 진입 시)

- Error 5 = 데이터 layer (vams.total_value 산출 / avg_price 영속화 영역)
- Phase 0 ATR 산출법 (SMA → Wilder EMA) 과 *영역 독립* (격리 검증 통과 시)
- Phase 0 A/B 비교 baseline 에 영향 X — ATR 계산 로직과 데이터 영속화 로직 격리 검증 통과 후
- 자본 진화 컨셉 자체의 측정 baseline 결함 → 격리 통과 시 *Phase 0 verdict 와 무관하게* 정정 가능

### 1-4. 예외 적용 룰 (결정 21 정합)

- "다른 변수 변경" 가드 = ATR 산출법과 *격리 검증 통과한* 영역에만 예외 적용
- 격리 미검증 영역 = 결정 21 strict 적용 (5/17 후 진입 강제)
- hotfix sprint 진입 시 변경 범위 = *데이터 영속화 영역* 명시 제한 (cross-cutting 변경 금지)
- Phase 0 운영 cron 결과 의 ATR 측정 자체는 hotfix 영향 X (격리 검증 통과 시)

### 1-5. 최종 판단

PM 본인 결정 — 5/17 verdict 결과 + 격리 검증 결과 + hotfix 진입 비용 비교 후 결정.

---

## 2. 작업 단계 (순차, ~2시간)

### Step 1 — 결함 origin 추적 (30분)

**목표**: vams.total_value=0 + holdings avg_price=0 의 정확한 발생 위치 확정.

**작업**:
- `vams.total_value` 산출 코드 grep:
  ```bash
  grep -rn "total_value" api/vams/ --include="*.py"
  ```
- `holdings avg_price` 저장 코드 grep:
  ```bash
  grep -rn "avg_price" api/vams/ --include="*.py"
  grep -rn "execute_buy\|execute_partial_sell" api/vams/ --include="*.py"
  ```
- 결함 발생 시점 추적:
  ```bash
  git log --all --pretty=format:"%h %ai %s" -- api/vams/engine.py | head -30
  ls -lt data/portfolio.json.bak* 2>/dev/null | head -10
  ```
- portfolio_history.jsonl (있다면) 시계열 total_value 추적:
  ```bash
  jq '.vams.total_value' data/portfolio_history.jsonl 2>/dev/null | sort -u | head
  ```

**가능한 origin** (가설):
- (a) `execute_buy()` 시 avg_price 저장 누락 (price 만 기록, avg_price 산출 X)
- (b) `save_portfolio()` 시 total_value 산출 누락 (cash 만 영속화, holdings 시가 합 X)
- (c) JSON 직렬화 시 0 으로 reset (의심 낮음)
- (d) Phase 1.2 R-multiple 부분 익절 (T1-24, commit 8ef2c47) 도입 시점 회귀 가능성 (`exit_history` 로직 추가 시 avg_price 영역 영향)

**산출**: origin 위치 (file:line) + 가설 검증 결과 → Step 2 진입 baseline.

### Step 2 — 정정 코드 (30분)

**목표**: origin 위치 1줄 ~ 수줄 정정. 변경 범위 *데이터 영속화 영역* 으로 명시 제한.

**작업**:
- origin 위치 정정 (예: execute_buy 의 avg_price 저장 누락 시 1줄 추가)
- backward compat 가드 — 기존 holdings 데이터 보존 (`holdings.get("avg_price", 0)` fallback)
- 단위 테스트 5 cases 작성:

```python
# tests/test_vams_capital_data.py (신규)

class TestVAMSCapitalData:
    def test_execute_buy_avg_price_set(self):
        """execute_buy 후 avg_price > 0 (price 와 같거나 이동평균)."""
        engine = VAMSEngine()
        engine.execute_buy("005930", price=80000, qty=10)
        holding = engine.holdings["005930"]
        assert holding["avg_price"] > 0
        assert holding["avg_price"] == 80000  # 첫 매수 = price
    
    def test_total_value_correct(self):
        """total_value = cash + sum(holdings 시가)."""
        engine = VAMSEngine()
        engine.cash = 5_000_000
        engine.execute_buy("005930", price=80000, qty=10)  # 현금 -800,000
        # 시가 가정: 85,000 (8% up)
        portfolio = engine.serialize(current_prices={"005930": 85000})
        expected = 5_000_000 - 800_000 + (85000 * 10)  # 5,050,000
        assert portfolio["vams"]["total_value"] == expected
    
    def test_return_pct_accurate(self):
        """return_pct = (current_price - avg_price) / avg_price * 100."""
        engine = VAMSEngine()
        engine.execute_buy("005930", price=80000, qty=10)
        # 현재가 84,000 → return 5%
        portfolio = engine.serialize(current_prices={"005930": 84000})
        h = portfolio["vams"]["holdings"][0]
        assert abs(h["return_pct"] - 5.0) < 0.01
    
    def test_legacy_holdings_compat(self):
        """기존 holdings (avg_price=0 silent error) 로드 시 graceful."""
        engine = VAMSEngine.load_from_dict({
            "vams": {"holdings": [{"ticker": "005930", "avg_price": 0, "quantity": 9}]}
        })
        # 정정 후 코드는 legacy 데이터에 대해 backfill 또는 에러 처리
        assert engine.holdings["005930"].get("legacy_avg_price_zero") is True
    
    def test_empty_holdings_total_value(self):
        """빈 holdings 시 total_value = cash."""
        engine = VAMSEngine()
        engine.cash = 10_000_000
        portfolio = engine.serialize(current_prices={})
        assert portfolio["vams"]["total_value"] == 10_000_000
```

### Step 3 — portfolio.json backfill (30분)

**목표**: 현재 holdings 의 avg_price 복원 + vams.total_value 재산출 + 운영 데이터 직접 patch.

**작업**:
- backup: `cp data/portfolio.json data/portfolio.json.pre_hotfix_5_17`
- 현재 holdings 의 avg_price 복원 source 후보:
  - (a) `data/portfolio_history.jsonl` (있다면 시점별 추적 가능)
  - (b) git log 의 portfolio.json 시계열 grep — 첫 매수 시점 price
  - (c) KIS 거래 내역 (가능하면 fetch)
  - (d) 본인 수동 입력 (fallback — 삼성전자 / KT&G 만이라 가능)
- backfill script (1회 실행):

```python
# scripts/backfill_holdings_avg_price.py (신규, 1회용)

import json
from datetime import datetime

with open('data/portfolio.json') as f:
    p = json.load(f)

# 본인 수동 입력 또는 history 기반 복원
manual_avg = {
    "005930": ?????,  # 삼성전자 진입가 — 본인 확인
    "033780": ?????,  # KT&G 진입가 — 본인 확인
}

for h in p["vams"]["holdings"]:
    t = h["ticker"]
    if h.get("avg_price", 0) == 0 and t in manual_avg:
        h["avg_price"] = manual_avg[t]
        h["avg_price_source"] = "manual_backfill_5_17"

# total_value 재산출
total = p["vams"]["cash"]
for h in p["vams"]["holdings"]:
    # current_price = ??? (KIS fetch 또는 portfolio.json 의 다른 영역)
    current = h.get("current_price") or h["avg_price"] * (1 + h.get("return_pct", 0)/100)
    total += current * h["quantity"]
p["vams"]["total_value"] = round(total)

with open('data/portfolio.json', 'w') as f:
    json.dump(p, f, ensure_ascii=False, indent=2)

print(f"Backfilled: total_value={p['vams']['total_value']:,}")
```

### Step 4 — 검증 매트릭스 (30분)

| 항목 | 통과 기준 |
|---|---|
| 단위 테스트 5/5 통과 | `pytest tests/test_vams_capital_data.py -v` |
| 정정 후 portfolio.json `total_value > 0` | `jq '.vams.total_value' data/portfolio.json` |
| holdings 의 `avg_price > 0` (모든 종목) | `jq '.vams.holdings[].avg_price' data/portfolio.json` |
| return_pct 산출 일치 (정정 전 vs 후 ±0.5%p) | 정정 전 backup 와 비교 |
| D+1 운영 cron 결과 정상 | 다음 cron portfolio.json 의 total_value 추적 (정상 변동) |
| holdings_utilization_baseline.jsonl 의 5/2 entry 보존 | `vams_total_value_silent_error: true` 이력 영구 (정정 전 baseline 보존 의무) |

---

## 3. 롤백 조건

- 정정 후 portfolio_history 의 total_value 시계열 비정상:
  - 음수 발견
  - 100배 점프 (예: 1천만 → 10억)
  - holdings 시가 합 + cash ≠ total_value (±1% 초과 격차)
- 운영 cron 실패 (다음 날 portfolio.json 생성 X)

**롤백 절차**:
1. `cp data/portfolio.json.pre_hotfix_5_17 data/portfolio.json`
2. 정정 코드 revert: `git revert <hotfix-commit>`
3. 별도 진단 의제 등록 (예: `c5e8f9a2-fail` — Step 1 origin 추적 재실행)

---

## 4. 운영 영향

**예상**:
- 자본 진화 monitor 작동 시작 (이전엔 측정 자체 X)
- holdings 손익 정확 산출 → return_pct 신뢰성 ↑
- portfolio_history 시계열 누적 시작

**위험**:
- backfill 시 history 일관성 (시점별 total_value 산출 가능 여부 — manual 입력 의존)
- avg_price 정확도 (수동 입력 시 PM 기억 의존)
- legacy holdings (silent error 영역) graceful 처리 미흡 시 cron 실패

**완화**:
- backup 보존 (`portfolio.json.pre_hotfix_5_17`) 영구
- 단위 테스트 legacy 호환 case 통과 의무
- 첫 cron 시 텔레그램 alert (정상/실패 자동 보고)

---

## 5. 후속 의제 자동 진입 (Step 4 완료 후)

c5e8f9a2 hotfix 완료 → 다음 sprint 진입 가능:

| sprint | 의존성 해제 |
|---|---|
| **작업 7** (SECTOR_PROPAGATION_SPRINT) | VAMS sector 정정 효과 측정 가능 (holdings 분포 변화) |
| **작업 8** (PHASE_1_1_RECONSIDERATION_SPRINT) | 운영 holding 실측 정확도 확보 (return_pct / stop_hit) |
| **capital_evolution_monitor 모듈 구현** | Trigger 1/2/3 모두 작동 가능 (`docs/CAPITAL_EVOLUTION_MONITOR_SPEC.md`) |

---

## 6. 학습 사례 cross-ref

본 hotfix sprint 자체가 학습 사례:

→ `feedback_source_attribution_discipline` 6번째 학습 사례 적용:
> "데이터 layer 결함 → 의사결정 layer 자체 작동 불가 패턴"

→ 의제 f3a8c1d4 (데이터 layer 검증 의무화) 의 *역방향 사례* — 데이터 검증 우선 안 한 시스템에서 사후 hotfix 비용 = ~2시간. 향후 모듈 spec 작성 시 데이터 검증 게이트 통과 의무 (사전 비용 ~10분).

---

## 7. 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-03 00:50 KST | 초기 작성 — 진입 조건 + 단일 변수 통제 예외 검토 + 4 step + 검증 매트릭스 + 롤백 + 후속 의제 진입 |

---

문서 끝.

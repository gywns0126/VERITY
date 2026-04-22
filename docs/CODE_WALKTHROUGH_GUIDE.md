# 코드 정주행 가이드

목적: 실자금 투입 전, **본인이 AI 없이 각 파일을 설명할 수 있는 수준**까지 도달.
기준은 코드 라인 수가 아니라 **장애 시 원인을 스스로 추적할 수 있는지**.

## 읽는 순서 (의존성 역순)

작은·의존 적은 파일부터 → 큰·의존 많은 파일로.

1. `api/vams/validation.py`      (265줄, 의존 없음)
2. `api/vams/engine.py`          (426줄, validation + adjusted + config)
3. `api/trading/auto_trader.py`  (482줄, kis_broker + mock)
4. `api/analyzers/safe_picks.py` (미확인, analyzer 중에선 작을 것)
5. `api/intelligence/verity_brain.py` (1,656줄, 전부 다 의존)

**총 3~4시간 분량**. 하루에 한두 개씩, 3~5일에 나눠 진행 권장.

파일별로 **읽기 전 질문지를 먼저 보고**, 코드 읽으면서 답을 찾는 방식. 다 읽고 답 못 하면 그 파일은 아직 블랙박스.

---

## 1. `api/vams/validation.py` — 가장 쉬움, 여기부터

### 핵심 질문 (8개)
1. `VAMS_VALIDATION_START_DATE` 가 `None` 일 때, 어떤 데이터가 validation 에 들어가는가?
2. `_extract_series` 가 `adjusted_total_asset` 우선이고 `total_asset` 폴백인 이유는?
3. Sharpe 가 샘플 2개 미만이면 `None` 반환 — 이 경우 `overall` 은 어떻게 결정되나?
4. `cost_efficiency` 가 `alpha ≤ 0` 이면 자동 fail — 왜?
5. `regime_coverage` 는 **벤치마크 MDD 기준**. 왜 VAMS MDD 아님?
6. `_trade_stats` 가 `date` 파싱 실패 시 "보수적으로 제외" — 왜 포함이 아닌가?
7. `overall = FAIL` 이 되는 두 가지 경로는?
8. `window.start` 와 `window.validation_start_configured` 의 차이는?

### 숨은 결합점
- `compute_validation_report` 가 기본값으로 `VAMS_VALIDATION_START_DATE` 환경변수를 읽음 → 테스트 시 override 안 하면 prod 값이 섞임.
- `_extract_series` 가 `adjusted_total_asset` 없을 때 `total_asset` 폴백 → **초기 며칠** 은 두 가지 지표가 섞일 수 있음.

### 30분 구두 설명 기준
> "validation_report 는 6개 지표 + overall 을 뱉는다. 입력은 스냅샷 시계열 + history. 각 지표의 pass 는 이런 식으로… overall 은 failed 개수와 Sharpe 임계로 결정…"

---

## 2. `api/vams/engine.py` — VAMS 본체

### 핵심 질문 (10개)
1. `run_vams_cycle` 의 4단계 순서 — 왜 가격 업데이트 → 손절 → 매수 → 재계산 순?
2. `check_stop_loss` 의 세 가지 종료 조건은? 우선순위는?
3. `_apply_half_kelly` 가 하는 일을 한 문장으로.
4. `_check_portfolio_exposure` 가 차단하는 3가지 조건은?
5. `_estimate_slippage` (Almgren-Chriss sqrt) 의 참여율이 높으면 bps 는 어떻게 변하나?
6. `execute_buy` 에서 `actual_cost > cash` 면 None 반환 — 이게 VAMS 레벨에서 잔고 부족 방어선. 실거래 방어선은 어디?
7. `classify_asset` 이 currency 없을 때 ticker 포맷으로 추론하는 규칙은?
8. `compute_adjusted_return` 이 차감하는 3항목과, **차감 안 하는 2항목**은?
9. 배당 누적 훅 (§3.5) 이 실행되는 조건은?
10. `portfolio_lock` 은 왜 필요한가? (hint: 동시 실행)

### 숨은 결합점
- `update_holdings_price` 가 `price_map[ticker.zfill(6)]` — 티커 6자리 미만이면 조용히 누락.
- `execute_sell` 이 history 에 기록한 뒤에야 cash 반영 → 실패 시 중간 상태.
- `compute_adjusted_return` 이 `total_asset` 을 기준으로 차감 — 이미 슬리피지 반영된 수치. 중복 차감 없음 주장의 근거.
- 배당 수령이 현금으로 들어오면 `total_asset` 에는 포함되지만 `dividend_received` 필드로 별도 추적 → `compute_adjusted_return` 이 이걸 보고 세금 차감.

### 30분 구두 설명 기준
> "VAMS 는 3단계 필터를 통과한 종목을 프로필별 규칙으로 가상 매매한다. 매매 실행은 시장충격·수수료 포함한 체결가로… 손절은 세 조건 중 먼저 터지는 쪽… 매수 전엔 Half-Kelly 와 섹터·베타 노출 체크…"

---

## 3. `api/trading/auto_trader.py` — 실자금이 지나가는 곳. 가장 신중히.

### 핵심 질문 (12개 — 다른 파일보다 많음)
1. 3단계 안전장치는? (순서: `plan_orders` 필터 → `apply_safety_limits` → broker 체결)
2. `AUTO_TRADE_MAX_PER_STOCK_KRW` / `AUTO_TRADE_MAX_DAILY_BUY_KRW` / `AUTO_TRADE_MIN_SAFETY_SCORE` / `AUTO_TRADE_MIN_TIMING_SCORE` — 각각이 막는 위험은?
3. 킬스위치 파일 경로는 절대경로인가 상대경로인가? 어느 환경에서 문제될 수 있나?
4. `is_kr_market_open` / `is_us_market_open` 은 어떻게 판단하나? 장 개폐 경계 ±1초에서 어떤 일이 생기나?
5. `_today_buy_spent_krw` 가 어떤 status 레코드만 집계하나? DRY_RUN 이 포함/제외되는 이유는?
6. `execute` 의 `dry_run=True` 경로와 `False` 경로는 history 에 어떻게 다르게 기록되나?
7. broker 가 예외 raise 하면 어떤 레코드가 남는가? 그 다음 주문은?
8. `run_auto_trade_cycle` 이 `master_enabled=False` 반환하는 조건은?
9. `OrderResult.success=False` 와 예외 raise 는 `execute` 에서 같은 처리? 다른 처리?
10. 해외주식이 기본 차단되는 이유와 해제 방법은?
11. VAMS 가상매매 history 와 auto_trader 실거래 history 는 **다른 파일**. 경로는 각각?
12. "하루에 2번 돌려도 한도 초과 안 나는가" 를 증명하는 테스트 이름은? (hint: test_auto_trader_safety.py)

### 숨은 결합점
- **장 개폐 경계 race**: 09:00:00~09:00:01 사이 GitHub Actions 도달 시 결과 분기.
- `plan_orders` 의 recommendation 필터 vs `apply_safety_limits` 의 한도 필터 — 순서가 바뀌면 한도 계산이 왜곡됨.
- `_KILLSWITCH_PATH` 가 conftest 에서 override 되는데 prod 에서 override 안 되는지 점검.

### 30분 구두 설명 기준
> "auto_trader 는 3단계 안전장치가 있다. 1단계는 plan_orders 에서 recommendation·safety·timing 기준으로 종목을 거르고, 2단계는 apply_safety_limits 에서 킬스위치·장시간·일일한도를 확인하고, 3단계는 execute 에서 실제 broker 호출… 각 단계의 실패는 서로 다른 blocks/results 레코드로 남는다…"

---

## 4. `api/analyzers/safe_picks.py` — "안심" 추천 생성기

### 핵심 질문 (6개)
1. "안심"으로 분류되는 종목의 3가지 조건은?
2. 배당주 추천과 파킹 옵션(국채/CMA) 의 분기 로직은?
3. `safety_score` 와 `brain_score` 는 같은 것인가 다른 것인가?
4. 리스크 키워드 감지 로직은 어디서 나오고 어떻게 적용되나?
5. `safe_picks` 출력이 portfolio 의 어느 키에 저장되고, Framer 어느 컴포넌트가 소비하나? (SafePicks.tsx)
6. 안심 추천이 VAMS 가 실제 매수하는 종목과 다를 수 있는가? (hint: VAMS 는 recommendation 필드 기준)

### 숨은 결합점
- `value_hunter.py` 의 `div_yield` 시그널과 겹침.
- `gemini_analyst.py` 가 서술하는 "안심" 과 로직 기반 "안심" 의 일관성 점검 필요.

### 30분 구두 설명 기준
> "safe_picks 는 하락장 대비 저변동 고배당 종목을 따로 뽑는다. 일반 추천이 momentum 편향이라면 safe_picks 는 yield·quality 편향…"

---

## 5. `api/intelligence/verity_brain.py` — 1,656줄, 마지막 관문

### 핵심 질문 (15개)
1. Constitution JSON 의 역할은? 어디서 로드되고, 누가 수정하나?
2. Brain v5.0 의 판단 파이프라인 N단계는?
3. multi-LLM 병합 (Gemini/Claude/Perplexity) 가 어느 단계에서 일어나나?
4. AI 리더보드(`ai_leaderboard.py`) 와 포스트모텀(`postmortem.py`) 이 Brain 의 가중치에 어떻게 피드백되나?
5. `knowledge_base.json` 은 무엇인가? 어떻게 성장하나?
6. Brain 이 종목별로 뱉는 최종 출력은 무슨 필드들인가?
7. `brain_score` 가 60점 미만이면 VAMS 에서 어떻게 처리되나?
8. Brain 이 "확신 없음" 을 표현하는 방법은? (confidence / uncertainty 필드)
9. 반론 로직 — Claude 가 Gemini 와 다른 의견 낼 때 어떻게 처리?
10. `strategy_evolver.py` 가 Brain 에 어떤 영향을 미치나?
11. Brain 의 의사결정을 거슬러 추적하려면 어떤 필드를 보나? (audit trail)
12. Brain 이 장애 시 VAMS 는 어떻게 동작하나? (fallback 경로)
13. niche_intel · tail_risk_digest · value_hunter 가 Brain 에 어떻게 주입되나?
14. 매크로 패널티 (`macro_adjustments.py`) 가 Brain 점수에 어떻게 가산/감산되나?
15. "이번 판단은 왜 BUY/WATCH/AVOID 인가" 를 3줄로 역추적할 수 있는가?

### 숨은 결합점
- Constitution JSON 변경은 **모든 판단을 바꾸는 레버** — 테스트 없이 수정 금지.
- Brain 이 internal cache 를 쓰면 같은 사이클 내 재호출 시 일관성 문제 가능.
- LLM API 쿼터 초과 시 fallback 이 어디로 가는가.

### 30분 구두 설명 기준
> "verity_brain 은 Constitution JSON 규칙에 따라 종목별 최종 판단을 내린다. 입력은 정량 지표 + 정성 분석(3개 LLM) + 매크로 패널티 + tail risk… 출력은 brain_score, recommendation, reasoning… 과거 오심은 postmortem 으로 학습…"

---

## 사이클 전체 30초 설명 (최종 목표)

> "VERITY 는 매일 16:00 에 GitHub Actions 로 돌아간다. 48개 수집기로 시장·종목·매크로 데이터를 긁고, 3단계 깔때기로 필터링한 뒤, 16개 분석기로 점수를 매기고, verity_brain 이 최종 판단을 내린다. 그 판단을 VAMS 가 가상 매매하고, auto_trader 가 (enabled 시) 실거래로 보낸다. 모든 결과는 portfolio.json 에 쓰이고 Framer 가 읽는다. 실패가 났을 때 의심 순서는 수집기 → 분석기 → Brain → VAMS → auto_trader…"

---

## 자가 평가 방법

1. 위 질문지를 보지 않고 해당 파일을 **한 번** 읽는다.
2. 질문지 열고 **답 없이** 본인 말로 답해본다.
3. 못 답한 질문만 해당 섹션 재독.
4. 3번 돌려도 못 답하면 `Bash` 로 `grep` 해서 직접 찾는다. **AI 에게 묻기 전에**.
5. 최종적으로 친구에게 전화로 30분 설명할 수 있으면 그 파일은 완료.

---

## 완료 체크리스트

- [ ] `validation.py` 8개 질문 답변
- [ ] `vams/engine.py` 10개 질문 답변
- [ ] `auto_trader.py` 12개 질문 답변
- [ ] `safe_picks.py` 6개 질문 답변
- [ ] `verity_brain.py` 15개 질문 답변
- [ ] 사이클 전체 30초 설명 가능
- [ ] 각 파일에 대해 "장애 발생 시 가장 먼저 볼 3줄" 정의

이 체크리스트가 전부 되면 **실자금 투입 전 코드 이해 요건 충족**.

# 자동매매 셋업 가이드

VERITY 자동매매는 **4단계 검증 레이어**로 구성된다.
L1 → L4 순서대로 단계적으로 넘어가며, 각 레이어에서 확신이 생긴 후에만 다음 단계로 이동.

```
L1  단위 테스트         (pytest)                 토큰 0, 네트워크 0
L2  Mock 브로커 E2E     (simulate_auto_trade.py)  토큰 0, 네트워크 0
L3  실브로커 Dry Run    (KIS 토큰 有, 주문 미전송)   토큰 必요
L4  실브로커 Live        (실제 체결)                토큰 必요 + 고의적 활성화
```

---

## 아키텍처

```
portfolio.json ──► TimingSignalWatcher ─► 전이 감지 ─► 텔레그램 수동 알림
     │
     └────────────► AutoTrader.plan_orders
                         │
                    apply_safety_limits   (킬스위치·장시간·일일 한도)
                         │
                       execute ◄── Broker (MockKISBroker or KISBroker)
                         │
                    auto_trade_history.json + 텔레그램 체결 알림
```

브로커는 `api/trading/__init__.py`의 `get_broker()` 팩토리를 통해 주입.
환경변수에 따라 MockKISBroker(로컬) 또는 KISBroker(실) 자동 선택.

---

## L1: 단위 테스트

```bash
.venv/bin/pytest tests/ -v
```

- `tests/test_timing_watcher.py` — action 전이/쿨다운/보유-미보유 케이스
- `tests/test_auto_trader.py` — 주문 계획/안전장치/드라이런/Mock 체결/풀 사이클

28 케이스 전부 녹색이어야 다음 단계 진행.

---

## L2: Mock 브로커 End-to-End

```bash
.venv/bin/python scripts/simulate_auto_trade.py --reset-state --allow-after-hours
```

옵션:

| 플래그 | 기본 | 설명 |
|--------|------|------|
| `--live-mock` | off | dry_run 대신 MockBroker로 실제 체결 시뮬 |
| `--allow-after-hours` | off | 장외시간도 주문 허용 (로컬 검증용) |
| `--reset-state` | off | `.timing_state.json` 삭제 (전이 강제 재현) |
| `--min-safety N` | 70 | 안심점수 하한 덮어쓰기 |
| `--min-timing N` | 70 | 타이밍점수 하한 덮어쓰기 |
| `--max-per-stock N` | 200000 | 종목당 매수 한도 (KRW) |
| `--max-daily N` | 500000 | 일일 매수 한도 (KRW) |
| `--initial-cash N` | VAMS 값 | MockBroker 초기 현금 |

산출물:

- `data/mock_orders.log` — MockBroker 주문 이벤트 (JSONL)
- `data/auto_trade_history.json` — AutoTrader 체결 이력
- `data/.timing_state.json` — 타이밍 전이 상태

---

## L3: 실브로커 Dry Run

토큰을 발급받아 `.env`에 넣되 `AUTO_TRADE_DRY_RUN=true`로 **주문 제출 직전에 차단**.
Plan/Safety까지만 실호출 경로를 타고, 실제 `place_order`는 호출되지 않는다.

```bash
# .env
KIS_APP_KEY=xxx
KIS_APP_SECRET=xxx
KIS_ACCOUNT_NO=50123456-01

USE_MOCK_BROKER=false
AUTO_TRADE_ENABLED=true
AUTO_TRADE_DRY_RUN=true
AUTO_TRADE_MIN_SAFETY_SCORE=70
AUTO_TRADE_MIN_TIMING_SCORE=70
AUTO_TRADE_MAX_PER_STOCK_KRW=200000
AUTO_TRADE_MAX_DAILY_BUY_KRW=500000
AUTO_TRADE_ALLOW_OVERSEAS=false
```

며칠간 Dry Run 로그 돌려보고, 주문 계획이 납득 가능한지 관찰.

---

## L4: 실브로커 Live (실체결)

Dry Run에서 일주일 이상 납득 가능한 결과가 나왔을 때만 진행.

```bash
# .env — 딱 한 줄만 바꾼다
AUTO_TRADE_DRY_RUN=false
```

**필수 안전장치** (디폴트로 켜져 있음):

- `AUTO_TRADE_ENABLED=true` 마스터 스위치 없으면 절대 주문 안 함
- `AUTO_TRADE_MAX_DAILY_BUY_KRW` 일일 한도 (기본 50만원)
- `AUTO_TRADE_MAX_PER_STOCK_KRW` 종목당 한도 (기본 20만원)
- `AUTO_TRADE_MIN_SAFETY_SCORE` 안심점수 (기본 70)
- `AUTO_TRADE_MIN_TIMING_SCORE` 타이밍점수 (기본 70)
- `AUTO_TRADE_ALLOW_OVERSEAS=false` 해외 기본 차단
- `AUTO_TRADE_ALLOW_AFTER_HOURS=false` 장외시간 차단
- `AUTO_TRADE_REQUIRE_BUY_REC=false` true면 `recommendation=BUY/STRONG_BUY`까지 요구

**킬스위치** (즉시 중단):

```bash
touch data/.auto_trade_paused       # 전체 자동매매 즉시 OFF
rm data/.auto_trade_paused          # 재개
```

---

## 환경변수 요약

| 변수 | 기본 | 의미 |
|------|------|------|
| `USE_MOCK_BROKER` | 자동 | `true`: 무조건 Mock, `false`: 무조건 실. 미지정 시 `VERITY_MODE`/토큰 여부로 자동 |
| `VERITY_MODE` | dev | `dev`/`staging`/`prod`. prod 아니면 Mock 우선 |
| `AUTO_TRADE_ENABLED` | false | 마스터 스위치 |
| `AUTO_TRADE_DRY_RUN` | true | 실주문 차단 |
| `AUTO_TRADE_MIN_SAFETY_SCORE` | 70 | 안심점수 하한 |
| `AUTO_TRADE_MIN_TIMING_SCORE` | 70 | 타이밍점수 하한 |
| `AUTO_TRADE_MAX_PER_STOCK_KRW` | 200000 | 종목당 매수 한도 |
| `AUTO_TRADE_MAX_DAILY_BUY_KRW` | 500000 | 일일 매수 한도 |
| `AUTO_TRADE_ALLOW_OVERSEAS` | false | 해외주식 허용 |
| `AUTO_TRADE_ALLOW_AFTER_HOURS` | false | 장외시간 허용 |
| `AUTO_TRADE_REQUIRE_BUY_REC` | false | BUY 추천까지 요구 (엄격 모드) |

---

## 수동 타이밍 알림 (자동매매와 독립)

`TimingSignalWatcher`는 자동매매 없이도 동작.
`portfolio.json`의 `recommendations[].timing.action`이 이전 사이클과 다를 때만 텔레그램 전송.

- 쿨다운 4시간
- 보유중 종목은 매도 시그널 강조
- 미보유 종목의 단순 SELL은 필터링, STRONG_SELL만 알림

상태: `data/.timing_state.json` (자동 관리)

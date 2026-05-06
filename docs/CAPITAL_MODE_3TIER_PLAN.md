# Capital 3-Tier Mode Plan (2026-05-06)

**진입 게이트**: 2026-05-17 이후 (ATR Phase 0 verdict 후, profile 상한 동결).

**목적**: 자본 100% 를 risk profile 3 분리 — 60% 보수 / 30% 중간 / 10% 공격.
*심리 분리* + *동시 다중 전략 검증* + *자본 단계 진화 자연*.

## 메모리 정합

- `project_atr_dynamic_stop` Phase 1.1 — ATR×2.5 + profile 상한 (이미 *profile 다중* 의도)
- `project_stock_filter_v0_enhancement` — safe 프로파일 5 (1 profile 박힘, 확장)
- `project_r_multiple_exit` Phase 1.2 — 1R/2R/트레일링, mode 별 비율 차별 가능
- `project_capital_evolution_path` 6 tier × 7축 — mode 와 직교 (둘 다 layer)

## 구조 결정

**하이브리드** — 시그널 공유 / 자본 배분 + 룰만 mode 별 차별:
- Brain v5 평가는 전 종목 한 번 (현재 그대로)
- 같은 종목이 어느 mode 에 들어가나 = grade + size + risk profile 룰
- 단일 portfolio + holdings 에 `mode_tag: "conservative" | "moderate" | "aggressive"`
- VAMS 도 *mode 별 PnL 분해* (전체 PnL + sub-PnL 3개)

## 3 Mode 룰

| Dimension | 60% 보수 | 30% 중간 | 10% 공격 |
|---|---|---|---|
| Brain grade 컷 | STRONG_BUY (85+) | BUY (75+) | BUY (75+, high conviction 만) |
| 종목 수 (목표) | 5-8 | 4-6 | 1-3 |
| 종목당 max (mode 자본 비율) | 15% | 10% | 5% |
| 손절 ATR 배수 | 3.0 (느슨) | 2.5 (기본) | 2.0 (타이트) |
| R 분할 (1R/2R/트레일링) | 50/30/20 | 50/30/20 | 30/30/40 |
| 평균 보유 | 3-12개월 | 1-6개월 | 2주-2개월 |
| Sector cap (mode 내) | 25% | 30% | 50% |
| Multi-bagger 추적 | OFF | 선택 | ON |
| Earnings/momentum 가중 | 낮음 | 기본 | 높음 |

## 자본 배분 흐름

```
total_capital
  ├── 60% conservative  (mode_tag = "conservative")
  ├── 30% moderate      (mode_tag = "moderate")
  └── 10% aggressive    (mode_tag = "aggressive")
```

매수 시:
1. Brain v5 grade 컷 통과 종목 검증
2. 어느 mode 적합한지 결정 (grade + sector cap + 종목당 max 잔여)
3. 해당 mode 의 *현재 잔여 capital* 기반 size 계산
4. holdings 에 `mode_tag` 박힘

매도 시:
1. holding.mode_tag 따라 손절/익절 룰 적용
2. ATR×N + R 분할 비율 mode 별 다름

## 데이터 구조

### portfolio.json 추가 키 (운영 후)

```json
"capital_mode": {
  "version": "v0",
  "split": { "conservative": 0.60, "moderate": 0.30, "aggressive": 0.10 },
  "balances": {
    "conservative": { "allocated": 600000, "available": 450000, "deployed_pct": 0.25 },
    "moderate":     { "allocated": 300000, "available": 180000, "deployed_pct": 0.40 },
    "aggressive":   { "allocated": 100000, "available":  90000, "deployed_pct": 0.10 }
  },
  "pnl_by_mode": {
    "conservative": { "realized": 0, "unrealized": 12000, "win_rate": 0.62 },
    "moderate":     { "realized": 0, "unrealized":  8000, "win_rate": 0.55 },
    "aggressive":   { "realized": 0, "unrealized":  -500, "win_rate": 0.40 }
  }
}
```

### holding 추가 필드

```json
{
  "ticker": "...",
  "mode_tag": "conservative",
  "stop_loss_pct_individual": ...,
  "exit_targets": {...},
  ...
}
```

## V0 박는 작업 (5/17 이후)

1. **VAMS 확장** — `mode_tag` 필드 + mode 별 룰 분기
   - `api/vams/engine.py` — buy/sell 결정 시 mode 룰 적용
   - holding schema 마이그레이션 (기존 holdings = `moderate` 기본 박음)
2. **자본 배분 함수** — `compute_mode_balances(total_capital, holdings)` 신규
3. **Brain v5 mode 라우팅** — `route_to_mode(stock, brain_result)` 신규
   - grade 85+ → conservative 우선
   - grade 75+ + multi-bagger → aggressive
   - 나머지 75+ → moderate
4. **포트폴리오 UI** — VAMSProfilePanel 에 *mode 별 PnL 분해* 카드 추가
5. **AdminDashboard** — capital mode card (3 mode 잔여 + win rate)
6. **백테스트** — mode 별 IC + Sharpe 분리 측정

## V1 (운영 1-2 주 후)

- Mode 자동 vs 수동 override (사용자가 특정 종목 mode 박을 수 있게)
- Mode 간 자본 *재배분* (보수 60% → 50% / 공격 10% → 20% 같은 dynamic shift) — Capital Evolution Path 와 결합
- Mode 별 *learning loop* (postmortem mode 분리 학습)

## V2 (검증 후)

- Mode 4단계 (보수 50 / 안정 30 / 중간 15 / 공격 5) 또는
- 시장 regime 별 mode 비율 자동 조정 (MarketHorizon → bear regime 시 보수 80% / mid_bull 60% / euphoria 40%)

## 위험 / Tradeoff

1. **수치 검증 부족** — V0 룰 (3.0/2.5/2.0 ATR, 15/10/5% size) 은 *추정값*. V1 에서 백테스트 보정 필수
2. **유동성** — 종목당 max 5% (공격) 가 종목 시총 대비 너무 작으면 의미 없음. 최소 시총 컷 추가 필요
3. **세제** — 한국 50억 기준 / 1년 미만 33% (`project_multi_bagger_watch`) 가 mode 별 보유 기간과 충돌 — aggressive (단기) 가 가장 세금 손해. 세후 수익률 측정 필수
4. **심리 분리 정직** — 사용자가 "10% 잃어도 OK" 약속해야 aggressive 의미. 실제 잃을 때 룰 어기면 시스템 의미 0. 운영 약속 박음

## 운영 검증 (V0 박은 후)

- 1주: 매수 분배 실측 (mode 비율 실제 vs 목표)
- 1달: mode 별 win rate / Sharpe 측정 → 룰 보정 여부 결정
- 3달: capital 진화 (자본 활용도 변화 — Tier 1 → 2 진입 시 mode 비율 조정 정당화)

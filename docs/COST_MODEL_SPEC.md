# 거래 비용 모델 — 구현 명세서 (보류 상태, 2026-04-28)

**상태**: 명세 작성 완료 / 구현 보류
**작성**: 2026-04-28
**선결 조건**: Phase A 룰 이식 운영 검증 + Lynch 분류 분포 안정화 후 착수
**예상 스프린트**: 2주 (Week 1 코어 + Week 2 UI / 회귀)

## 검수 결과 요약 (2026-04-28)

VERITY VAMS 가 이 명세의 **약 80% 를 이미 구현 중**:
- ✅ KR/US 매도 세율 분기 (`VAMS_SELL_TAX_KR_STOCK / KR_ETF / US_STOCK / US_ETF`)
- ✅ 위탁수수료 (`VAMS_COMMISSION_RATE`)
- ✅ Almgren-Chriss 제곱근 슬리피지 (`api/vams/engine.py::_estimate_slippage`)
- ✅ 배당세 (`VAMS_DIVIDEND_TAX_RATE`)
- ✅ ValidationPanel.tsx 의 cost breakdown UI (gross vs net 분리)

**진짜 미구현 (실제 작업 4건)**:
1. 시간대 가중치 (장 시작/마감 1.5~2배)
2. alpha-to-cost gate (매수 신호 사전 비용 비교)
3. 거래 회전율 (turnover) 측정 + 200%+ 경고
4. 환전 비용 (KIS 0.5~1% 단방향) — US 종목

따라서 본 명세의 "처음부터 구축" 가정은 부정확. **2주 스프린트 → 4~5일 보강** 으로 단축 가능.

## 명세서 본문 — Perplexity 협업 결과 보존

(이하는 사용자가 Perplexity 와 협업해 작성한 원본 명세서. 구현 시점에 본 검수 결과와 합쳐 4~5일 스프린트로 진행)

### 1. 모듈 구조

```
api/quant/
├── cost_model.py          # NEW: 비용 산출 코어
├── liquidity_cache.py     # NEW: 종목별 ADV/spread 캐시
└── factors/

api/vams/
├── engine.py              # MOD: cost_model 통합 (이미 80% 구현)
├── execution.py           # NEW: 실효 체결가 계산
└── alpha_gate.py          # NEW: alpha-to-cost 게이트
```

### 2. 핵심 로직

**3-tier participation rate 슬리피지** (Almgren-Chriss 단순화):
- < 0.5% ADV: 0.5 × spread
- 0.5~2%: 1.0 × spread + 5bps
- 2~5%: 1.5 × spread + 15bps
- > 5%: 거래 거부

**시간대 가중치**:
- 장 시작 30분: 1.8×
- 장 마감 30분: 1.5×
- 점심 (KR 11:30~13:00): 1.3×
- 그 외: 1.0×

**alpha-to-cost gate**:
- expected_alpha = brain_implied_return × confidence
- threshold: alpha ≥ round_trip_cost × 2.0
- 근거: Grinold·Kahn *Active Portfolio Management* 2판 16장

### 3. 한국 시장 비용 표 (2026-04 기준)

| 항목 | KOSPI | KOSDAQ | KR ETF | US |
|---|---|---|---|---|
| 위탁수수료 | 0.015% | 0.015% | 0.015% | $0 (Robinhood) |
| 유관기관 | 0.0036% | 0.0036% | 0.0036% | — |
| 매도 거래세 | 0.18% | 0.18% | 면제 | SEC 0.0028% |
| 환전 (KR→US) | — | — | — | 50bps 단방향 |

### 4. 하이브리드 30일 병기 (UI)

VAMSProfilePanel 듀얼 카드:
- 신규 비용 반영 수익률 (정확)
- 기존 표시 (비용 미반영, 참고용) — Day 0~30
- Day 31+: 신규만 유지, legacy 는 archive

공지 카피: "성능 저하가 아니라 현실 반영"

### 5. 위험 요소

- 위험 1: STRONG_BUY net 수익률이 BUY 와 비슷하면 → 보유기간 늘림 / 임계 강화
- 위험 2: 단기 모멘텀 (1~3일 보유) 모두 차단 → 가짜 알파였을 가능성, 차단 정상
- 위험 3: 사용자 일부 "수익률 낮아짐" 이탈 → 정직성이 장기 신뢰

## 착수 결정 시 검증 질문 (Perplexity)

1. 한국 거래세 0.18% 의 향후 변경 로드맵 (2025 0.20% → 2027 0.15% 등)?
2. Almgren-Chriss α 한국 시장 실증 추정값 (학술/운용사 보고서)?
3. alpha-to-cost ratio 2.0× 임계의 학술 표준 (Grinold·Kahn 외 다른 권장값)?

## 다음 액션 (구현 착수 시)

1. 본 명세 + 검수 결과 합치기 (이미 80% 구현 인지)
2. 4~5일 스프린트 (2주 → 단축):
   - Day 1: 시간대 가중치 추가
   - Day 2: 회전율 측정 + AdminDashboard 경고
   - Day 3: alpha-to-cost gate
   - Day 4: 환전 비용 (US)
   - Day 5: 30일 spread 캐시 + 백테스트 재실행

---

**현재 보류 사유**: Phase A 룰 이식 (regime_weight / PEG / Hard Floor / Lynch 분류) 의 운영 영향이 먼저 검증되어야 함. 거래 비용 모델까지 동시 변경 시 충격 누적 + 원인 분리 어려움.

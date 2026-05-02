# Silent Errors 종합 평가 — 2026-05-02

**작성**: 2026-05-02 23:45 KST (Round 1 작업 3)
**범위**: 5/2 audit + 진단 결과 silent error 4건 종합 평가 + 상호작용 분석 + 5/17 후 정정 우선순위 매트릭스
**참조**: `docs/SOURCE_AUDIT_20260502.md` / `docs/OPS_VERIFICATION_20260502.md` / `docs/REGRESSION_RISK_AUDIT_20260502.md`

---

## 0. silent error 정의

> 코드 / 데이터 / 룰이 *작동하는 것 처럼 보이나* 본래 설계 의도가 silent fallback 으로 인해 무효화된 상태. 명시적 에러 / 알림 X. 운영 영향 정량 측정 어려움.

본 문서 = 5/2 발견 4건 정리 + 운영 영향 정량 + 4건 상호작용 + 정정 sprint 우선순위.

---

## 1. silent error 4건 + 1건 추가 (5/2 23:55) = 총 5건 list

### Error 1 — Phase 1.1 ATR×2.5 한국 시장 부적합 🔴

| 항목 | 값 |
|---|---|
| 위치 | `api/config.py` `ATR_STOP_MULTIPLIER=2.5` + `api/trade_planner.py:build_trade_plan_v0` + `api/vams/engine.py:check_stop_loss` |
| 발견 | 5/2 풀스캔 v2 — large tier stop_loss_rate **75.6%** / mid 77.8% / small 78.9% |
| 운영 영향 (정량) | 1년 보유 윈도우 75% 종목 손절 hit = whipsaw 위험. avg ATR/price 4.57% × 2.5 = 1R distance 11.4% (한국 종목 일반 변동성 대비 tight) |
| 의제 | fa3c2d1e (운영 코드 변경 sprint) / 57ac6bd0 (4-cell 백테스트 P0) / d7dea48c (운영 영향 사전 검증) / 0f6dce6a (multiplier 재검토) |
| 5/2 메모리 정정 | ✅ project_atr_dynamic_stop 2차 정정 완료 |

### Error 2 — sector 필드 propagation 결함 🔴

| 항목 | 값 |
|---|---|
| 위치 | `api/collectors/krx_openapi.py` / `dart_fundamentals.py` / `universe_builder.py` 모두 sector 키워드 부재 (root cause) |
| 발견 | 5/2 22:30 진단 — recs 51/51 sector + category 모두 None |
| 운영 영향 (정량) | (a) Hard Floor sector 면제 룰 적용 불가 (silent no-op) / (b) VAMS sector_diversification 한도 무효 (Error 3) / (c) daily_actions / TodayActionsCard sector 노출 None / (d) trade_planner sector fallback / (e) value_hunter / meta_validation sector breakdown 무효 |
| 의제 | e8a17b3c (P0+ KR sector 수집기 신규) |
| root cause 확정 | 5/2 23:00 — KR sector 수집기 자체가 미구현 (US/Commodity 는 별도 채널 부착) |

### Error 3 — VAMS sector_diversification silent gap 🔴

| 항목 | 값 |
|---|---|
| 위치 | `api/vams/engine.py:421, 430` — `(stock.get("sector") or "Unknown").strip()` |
| 발견 | 5/2 23:30 진단 — vams.holdings 2건 (삼성전자/KT&G) sector "없음" → 모두 "Unknown" 단일 분류 |
| 운영 영향 (정량) | 베테랑 audit 결함 4 (factor exposure 한도 부재) **운영 발현 증거**. 전 종목 같은 sector 로 처리 → 분산 한도가 사실상 작동하지 않음. holdings 누적 시 sector 한도 trigger 발동 0건 예상 |
| 의제 | b9d4f72a (e8a17b3c 후속 P1) |
| 의존성 | e8a17b3c 정정 후 D+1 운영 cron 측정 |

### Error 5 — vams.total_value=0 + holdings avg_price=0 🔴 (5/2 23:55 추가)

| 항목 | 값 |
|---|---|
| 위치 | `api/vams/engine.py` save_portfolio 또는 거래 산출 단계 — total_value 산출 + avg_price 영속화 영역 |
| 발견 | 5/2 23:55 진단 — `vams.total_value=0` (cash 6,179,471 + holdings 가치 ≠ 0) / holdings 2건 모두 `avg_price=0` |
| 운영 영향 (정량) | 자본 진화 Trigger 1 (자본 임계 도달, Primary 신호) **측정 자체 불가**. capital_evolution_monitor 명세 (Round 3) 의 핵심 데이터 source 결함. holdings 손익 정확 산출도 영향 (return_pct 만 살아있음) |
| 의제 | c5e8f9a2 (P0 — capital_evolution_monitor 명세 진입 *전* 정정 의무) |
| 의존성 | (선행 X) — 즉시 진행 가능, capital_evolution_monitor 명세는 c5e8f9a2 정정 의존 |

---

### Error 4 — 부채 300% Hard Floor sector 면제 부재 🔴

| 항목 | 값 |
|---|---|
| 위치 | `api/intelligence/verity_brain.py:1631` (auto_avoid) / `verity_brain.py:1633` (downgrade 200%) / `lynch_classifier.py` TURNAROUND 부채 < 300% |
| 발견 | 5/2 18:00 audit ac9d1dc1 검증 — `feedback_sector_aware_thresholds` 정책 위반 (dilute() 함수만 적용, Hard Floor 자체 부재) |
| 운영 영향 (정량) | KB금융 (105560) brain=52 grade=**AVOID** + auto_avoid red_flag 발현 확인 (5/2 22:30 진단). 정확 추정 = ~40 한국 금융주 (KOSPI 30 + KOSDAQ 10) 자동 탈락 회귀. 단 sector NULL (Error 2) 로 인해 *확인 자체가 silent* — 부분 발현 (KB금융) 만 확정 |
| 의제 | fa3c2d1e (P0 운영 코드 변경 sprint) |
| 선행 의존성 | e8a17b3c (sector NULL 정정) — 정정 안 하면 fa3c2d1e 의 sector_thresholds 헬퍼 도입 silent no-op |

---

## 2. 4건 상호작용 분석

### 2-1. 의존성 그래프

```
Error 2 (sector NULL)
   ├──→ Error 3 (VAMS 분산 한도 무효)
   ├──→ Error 4 (Hard Floor sector 분기 silent — 발현 여부 silent)
   └──→ daily_actions / value_hunter / meta_validation 다수 silent fallback

Error 4 (Hard Floor sector 부재)
   ├──→ KB금융 부분 발현 (5/2 진단 확정)
   └──→ 추가 금융주 ~40 종목 잠재 회귀

Error 1 (Phase 1.1 ATR×2.5)
   └──→ 분산 안 된 portfolio (Error 3 영향) + tight stop = 변동성 폭증 누적 가능
```

### 2-2. 종합 운영 시나리오

**시나리오 A — *우연히* alpha 있는 sector 에 몰린 경우** (확률 낮음):
- holdings 2건 (삼성전자 + KT&G) 같은 sector 로 처리되나 *실제 다른 sector* → 운 좋게 동시 alpha → 영향 X
- 단 holdings 누적 시 (예: 5종목+) 점점 *우연 의존도* 하락 → 분산 한도 무효 영향 발현

**시나리오 B — sector 가 alpha 없는 분야에 몰린 경우** (확률 중):
- 분산 한도 무효 + alpha 없는 sector 집중 → underperform
- Phase 1.1 tight stop 으로 변동성 폭증 → 손실 누적
- daily_actions BUY/WATCH 추천에 sector 정보 없어 사용자 분산 판단 못 함 → 추가 집중

**시나리오 C — 금융주 의도적 배제 효과** (Error 4 발현):
- KB금융 등 금융주 자동 AVOID → 한국 KOSPI 큰 비중 자동 누락
- 한국 시장 KOSPI 200 의 금융 sector ~15% 비중 → 추천 universe 에서 자동 배제
- bull 장 시 금융주 outperform 시기 missed
- 베테랑 audit "기관급 인프라 + 리테일급 의사결정 게이트" 평가의 *retail 게이트* 영역 직접 발현

### 2-3. cascading silent 위험

- Error 1 (Phase 1.1) verdict 가 Error 2/3/4 *영향 미반영* 한 백테스트 결과 = 정정 후 multiplier 재선택 시 baseline 변경 가능성
- Error 2 정정 (sector 데이터 살아남) → Error 3 (VAMS 분산 한도) 자동 발현 가능 → 기존 종목 분산 한도 trigger 폭주 위험 (rollback 임계 sector 한도 +20% 이내 의제)
- Error 4 정정 후 금융주 추천 갑자기 +5~10건 → 운영 portfolio 급변 (사용자 confirm 게이트 의무)

---

## 3. 정정 sprint 우선순위 매트릭스 (5/17 후)

### 3-1. 진입 순서 (의존성 + 회귀 위험)

```
Phase 0 verdict (5/16) → ok ?
  ├─ ok → Phase 1.5.1 (4-cell 백테스트, 의제 57ac6bd0)
  │         └─ 결과 → Error 1 정정 (multiplier 변경)
  │
  ├─ ok → e8a17b3c (KR sector 수집기 신규)
  │         └─ D+1 검증 → fa3c2d1e (Hard Floor sector 분기) 진입
  │                          └─ D+1 검증 → b9d4f72a (VAMS 분산 한도 검증)
  │
  └─ fail → rollback (단일 변수 통제, 다른 sprint 진입 X)
```

### 3-2. 우선순위 표 (5/17+ 진입 시)

| 우선 | sprint | 정정 대상 error | 운영 영향 | 회귀 위험 |
|---|---|---|---|---|
| **1** | 4-cell 백테스트 (57ac6bd0) | Error 1 verdict | high (multiplier 재선택) | low (분석만) |
| **2** | e8a17b3c (KR sector 수집기) | Error 2 root cause | high (다수 downstream) | low (collector 신규) |
| **3** | fa3c2d1e (Hard Floor sector 분기) | Error 4 정정 | high (금융주 추천 +5~10건) | mid (운영 portfolio 급변) |
| **4** | b9d4f72a (VAMS 분산 한도 검증) | Error 3 발현 측정 | low (검증만) | low |

### 3-3. 우선순위 산출 룰

- **1순위 = 의존성 0개 + 즉시 baseline 확보** (4-cell 백테스트 = Error 1 운영 코드 변경 *전* baseline 산출)
- **2순위 = 다수 downstream 의 root cause** (e8a17b3c 가 Error 3/4 의 전제)
- **3순위 = 직접 운영 영향 high + 회귀 위험 mid** (fa3c2d1e 정정 후 금융주 추천 급변 사용자 confirm 의무)
- **4순위 = 검증성 의제** (b9d4f72a 는 1~3 정정 후 silent gap 효과 측정)

---

## 4. 정정 결과 측정 baseline (현재 상태)

| 측정 항목 | 현재 (정정 전) | 5/17 후 정정 sprint 진입 시 baseline 비교용 |
|---|---|---|
| recs sector 필드 non-null 비율 | 0/51 (0%) | e8a17b3c 정정 후 51/51 (100%) 목표 |
| holdings sector "Unknown" 비율 | 2/2 (100%) | b9d4f72a 측정 시점 |
| 금융주 추천 (sector 기반) | 0건 (sector NULL) | fa3c2d1e 정정 후 5~10건 예상 |
| 금융주 brain grade 분포 | KB금융 AVOID / 신한·하나 CAUTION | fa3c2d1e 정정 후 sector 면제 적용 시 grade 재산출 |
| Phase 1.1 stop_loss large tier | 75.6% (백테스트) | Error 1 정정 후 < 60% 목표 |
| VAMS sector 한도 trigger | 0건 발동 (sector "Unknown" 단일) | b9d4f72a 측정 — 정상 시 sector 다양화 후 trigger 정상 발동 |

---

## 5. 다음 세션 retrospective decision log 통합 권고

본 문서의 4 silent error 종합 평가는 *5/2 audit + 진단 결과의 메타 정리*. 다음 세션 retrospective decision log 갱신 시:

- T1-XX 신규 entry 4건 추가 권고 (각 silent error 별 결정 entry):
  - T1-Sx1: Phase 1.1 ATR×2.5 silent error 발견 + 5/17 후 정정 결정
  - T1-Sx2: sector propagation silent error 발견 + e8a17b3c 정정 결정
  - T1-Sx3: VAMS sector_diversification silent gap + b9d4f72a 검증 결정
  - T1-Sx4: Hard Floor sector 분기 부재 + fa3c2d1e 정정 결정
- Cross-ref: 본 문서 + OPS_VERIFICATION + REGRESSION_RISK_AUDIT + SOURCE_AUDIT 양방향 link
- Sprint 분류: S-06 (Audit Sprint 5/2) + 신규 S-07 (silent error 정정 sprint, 5/17 후 진입)

---

## 6. 보호 대상 (변경 금지 baseline)

본 문서는 *분석 + 종합 평가 only* — 변경하지 않을 항목:
- ✅ Phase 0 ATR A/B 비교 baseline (5/3~5/16) 보호
- ✅ 운영 코드 미터치 (모든 정정 sprint = 5/17 후 진입)
- ✅ 운영 데이터 미터치
- ✅ 메모리 변경 = 학습 사례 추가 1건 (`feedback_source_attribution_discipline` 5번째 사례) 만

---

## 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-02 23:45 KST | 초기 작성 — 4 silent error list + 상호작용 + 정정 우선순위 매트릭스 + retrospective 통합 권고 |
| 2026-05-02 23:55 KST | Error 5 추가 (vams.total_value=0 + avg_price=0, 의제 c5e8f9a2 P0) — VAMS 프로필 진단 follow-up. capital_evolution_monitor 명세 진입 전 의무 |

---

문서 끝.

# Action Queue 베테랑 매트릭스 재배치 (2026-05-02)

**총 24건** (Step 2 + Step 3 추가 후) — schedule 의존 / 운영 영향 / 처리 시간 가중 우선순위.
SOURCE_AUDIT_20260502 + D2/D4 정정 + 풀스캔 v2 산출 의제 통합.

---

## 매트릭스

### 즉시 처리 (~1주, 외부 schedule 의존) — 5건

| 우선 | id | 의제 | due | 영향 |
|---|---|---|---|---|
| 🔴 P1 | 9f48284a | **ATR Phase 0 secret 3개 설정 + sanity check** | 2026-05-02 (오늘) | 운영 — Phase 0 14일 검증 시작 차단 |
| 🔴 P1 | fe6d1c2d | Gemini 캐시 검증 | 2026-05-03 | 운영 — AI 비용 모니터 |
| 🔴 P1 | cdad960a | Stage 2 진입 결정 (universe ramp-up 500→1500) | 2026-05-04 | 운영 — wide_scan 확장 |
| 🔴 P1 | 7f2b51b5 | **D3 5/5 첫 cron sanity** (silent metrics jsonl) | 2026-05-05 | 검증 — 5/12/26 mid 의존 |
| ⚪ P2 | 453e244f | 1주 운영 점검 (Sprint 11 후속) | 2026-05-07 | 모니터링 |

### 2~3주 내 (5/12 ~ 5/17 verdict 직후) — 4건

| 우선 | id | 의제 | due | 영향 |
|---|---|---|---|---|
| ⚪ P2 | ea3d607b | D3 5/12 mid-checkpoint | 2026-05-12 | 검증 |
| 🔴 P1 | 8c96aef5 | **ATR Phase 0 5/16 verdict** | 2026-05-16 | 운영 게이트 |
| 🔴 P1 | 57ac6bd0 | **Phase 1.1 4-cell 백테스트 (verdict=ok 후 P0)** | 2026-05-17 | 운영 — ATR multiplier 결정 |
| 🔴 P1 | 41926867 | D3 5/26 정식 verdict | 2026-05-26 | 운영 — IC 단독 폐기 결정 |

### 6주 내 (운영 데이터 누적 후) — 4건

| 우선 | id | 의제 | 의존성 | 영향 |
|---|---|---|---|---|
| 🔴 P1 | d7dea48c | **Phase 1.1 운영 영향 사전 검증 (큐 3)** — 운영 holding 실측 stop hit vs 75.6% | 운영 holding 30+ 누적 | 운영 — ATR 즉시 재검토 트리거 |
| ✅ → 🔴 | ac9d1dc1 | **부채 300% Hard Floor ↔ sector_aware 면제 검증** (회귀 위험) | **검증 완료 5/2 18:00 KST** — 결과 🔴 (`docs/REGRESSION_RISK_AUDIT_20260502.md`) | 운영 — 금융주 자동 탈락 회귀 정량 확정 (~40 종목) |
| 🔴 P0 | fa3c2d1e | **sector_thresholds 헬퍼 + Hard Floor 정정 sprint** (ac9d1dc1 후속) | Phase 0 verdict (5/17+) 후 진입 권장 — 단일 변수 통제. **caveat: sector 필드 NULL 51/51 — e8a17b3c 선행 의존성** | 운영 코드 — verity_brain.py:1631 / lynch_classifier TURNAROUND 부채 |
| 🔴 **P0+** | **e8a17b3c** | **sector 필드 propagation 결함 정정** (fa3c2d1e 선행) | Phase 0 verdict (5/17+) 후 진입 — 5/2 22:XX 진단 sector NULL 51/51 정량 확정 | 운영 코드 — recs 단계 sector / category 누락 (analyze 또는 attach 단계) |
| ⚪ P2 | a760aaff | Brain 가중치 7:3 OOS 백테스트 | brain_weights_cv 누적 4주+ | 검증 |
| ⚪ P2 | 8d762b0a | Bessembinder 운영 함의 (Concentrated 10 vs 분산 30) | 풀스캔 v2 결과 ✅ | 검증 — 결정 10 재검토 |

### 3개월 보류 (low priority / 의존성 명확) — 7건

| id | 의제 | 의존성 |
|---|---|---|
| eb0c38e7 | P0d-4 13F bonus 한국 적용성 (KRX 5%+ 보고) | 별도 데이터 채널 |
| a76f7dd5 | P0d-3 Candle bonus 임계 출처 검증 (Nison 원전) | Nison 원전 grep |
| 7916b1f5 | P0a 신호 3 코드 구현 정정 | 별도 sprint |
| 0f6dce6a | P0e-c ATR multiplier 재검토 sprint | 4-cell 백테스트 (의제 5) 결과 |
| 22cdd1ec | P1c PEG 3.0 vs Lynch 2.0 보수화 근거 | 메모리 정정 (소량) |
| ad4fa2fd | P1b Lynch 임계 (5조/1조/0.8/300%) 산출 근거 | 메모리 정정 (소량) |
| d9a64306 | P0a/P1b CYCLICAL Lynch Ch.7 챕터 재검증 | Lynch 원전 grep |

### 운영 코드 변경 의제 (별도 sprint) — 3건

| id | 의제 | 영향 |
|---|---|---|
| 7916b1f5 | 신호 3 코드 구현 (verity_brain.py:181/191 정량 룰) | 운영 코드 — high |
| 0f6dce6a | ATR_STOP_MULTIPLIER 변경 sprint | 운영 코드 — high |
| 64d145cc | VAMS 프로필 alpha 비교 + 자본 비례 변환 가이드 | 운영 코드 — mid |

### 운영 미해결 잔여 — 3건

| id | 의제 | 비고 |
|---|---|---|
| b02dffe1 | alert_dispatcher warnings_since reset 누락 | trust 4/30~ |
| 9f61f6ac | data_health.jsonl 28h 미작성 | record_health() 누락 추적 |
| f5a988f9 | heartbeat 자동완료 디버그 (Safari EOF) | 차순위 |

---

## 우선순위 산출 룰

각 의제마다:

| 가중치 | 가중 |
|---|---|
| schedule due 임박 (<7일) | × 3 |
| 운영 영향 high | × 2 |
| 회귀 위험 발견 | × 2 |
| 의존성 충족 (즉시 가능) | × 1.5 |
| 처리 시간 < 1시간 | × 1.2 |
| 6주+ 의존성 | × 0.5 |
| 별도 sprint 필요 | × 0.7 |

**최종 점수 계산** = base (1) × 가중 곱.

---

## 다음 세션 진입 권고

1. **5/2 본인 액션** (오늘): ATR Phase 0 secret 3개 설정 — 9f48284a (P1, due 오늘)
2. **5/3~5/7 자동 진행**: Gemini 캐시 / Stage 2 결정 / D3 5/5 cron / 1주 점검
3. **5/16~5/17 핵심 게이트**: ATR Phase 0 verdict → Phase 1.1 4-cell 즉시 진행
4. **6주 내 회귀 위험 정리**: 부채 300% Hard Floor ↔ sector_aware 면제 검증 (ac9d1dc1) — 즉시 가능, 코드 검증만
5. **운영 데이터 누적 후**: Phase 1.1 운영 영향 사전 검증 (큐 3, d7dea48c) — 75.6% 백테스트 vs 실측 격차 모니터

---

## 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-02 | 초기 작성 (Step 2 + Step 3 통합 24건) |
| 2026-05-02 18:00 KST | 의제 ac9d1dc1 검증 완료 → 🔴 / 신규 의제 fa3c2d1e (sector_thresholds 정정 sprint) 등록. 총 25건 |
| 2026-05-02 22:30 KST | fa3c2d1e 정량 진단 (KB금융 AVOID 발현) + sector NULL 51/51 finding → 신규 의제 e8a17b3c (P0+ fa3c2d1e 선행). 총 26건 |

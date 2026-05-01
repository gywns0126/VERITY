# Phase 0 작업 중 발견 의문 (Type B / Type C)

작성: 2026-05-01
규칙: Type A (Stop-the-line) 는 즉시 PM 보고. Type B/C 는 본 문서에 메모 후 Phase 종료 retrospective.

---

## Type B (Defer — 현재 Phase 결과 해석에 영향)

### B1. `send_alert` 함수 부재 — patch 코드의 implementation 충돌

**발견**: P-04 (rollback script) + P-08 (outlier alert) 가 `from api.notifications.telegram import send_alert` 사용. 그러나 `api/notifications/telegram.py` 에 `send_alert` (단수) 함수 **부재**. 실제 함수: `send_message`, `send_alerts` (복수).

**조치**: patch 의도 = "Telegram 메시지 발송". 함수명만 다름. `send_message(text)` 로 대체 적용. spec intent 보존, implementation detail 만 변경.

**리스크**: spec 그대로 적용 시 ImportError → silent fail (try/except 안에 wrapping 됨). 본 조치로 silent fail 회피.

**PM 판단 요청**: 이게 Type A (silent failure) 인지 Type B (implementation detail) 인지? 진행하되 retrospective 시 결정.

---

### B2. `R_MULTIPLE_*` 환경변수 이름/값 불일치 (patch vs 운영)

**발견**: patch P-01 이 config.py 단일 정의 명시할 때 `R_MULTIPLE_TARGET_1_EXIT_PCT=0.5` (소수) 사용. 그러나 기존 운영 코드 (Phase 1.2 commit `8ef2c47`) 는 `R_MULTIPLE_EXIT_PCT_1=50` (정수, 변수명 다름). 운영에서 50 / 100 = 0.5 로 사용 중.

**조치**: patch 의 R_MULTIPLE 명시는 "config.py 한 곳 정의" 원칙 예시일 뿐, 실제 룰 변경 의도 X. 기존 운영 환경변수명/값 유지. Patch 의 `R_MULTIPLE_TARGET_1_EXIT_PCT=0.5` 부분 무시.

**리스크**: patch 그대로 적용 시 환경변수 이름 충돌 + Phase 1.2 운영 룰 깨짐 (target_1 50% 청산 → 0.5% 청산 등 catastrophic 버그).

**확정**: 기존 R_MULTIPLE_EXIT_PCT_1/2 그대로 유지.

---

### B3. v3 Step 0.6 BrainMonitor 카드 — Framer 컴포넌트 수정

**발견**: BrainMonitor.tsx 는 Framer 코드 컴포넌트. Phase 0 commit 시 같이 수정 시 Framer 재배포 필요. 운영 룰 ("코드 변경과 환경변수 변경 분리") 와 별개로 frontend 변경 자체가 추가 변수.

**조치**: BrainMonitor.tsx 변경은 Phase 0 마지막 commit (P-08 결과 노출) 에 통합. 단 backend (atr_migration_log.jsonl + outlier_counter.json) 가 portfolio.json 에 노출되도록 main.py 수정도 필요한지 확인. 이건 본 작업 범위 외 — backend 가 jsonl 직접 쓰면 BrainMonitor 가 fetch 가능?

**PM 판단 요청**: BrainMonitor 카드 적용 시점 — Phase 0 commit 안에서 / Phase 0 후 별도 turn / 영구 보류?

---

## Type C (Backlog — 미래 분기 검토)

### C1. ATR_MIN_PERIOD 사용 위치 통일

기존 운영 코드 (technical.py:80) 는 `len(close) >= 15` 하드코드. config.py:262 의 `ATR_MIN_PERIOD=20` 은 미사용. P-01 적용 시 헬퍼 함수가 `getattr(_cfg, "ATR_MIN_PERIOD", 20)` 로 사용. 그러나 기존 인라인 → 헬퍼 전환은 P-02 에서. **전환 직후엔 ATR_MIN_PERIOD=20 적용 → 운영 동작 변경 가능 (기존 15일 → 20일 최소).**

이게 의도된 변경? 또는 backward compat 으로 15 유지?

검토: ATR(14) 정확성을 위해 14+buffer 6 = 20 이 합리적. 변경 진행.

---

### C2. `compute_atr_with_ab_comparison` 의 매 cron 호출 비용 (의문 30 후속)

코어 85종목 × 양쪽 산출 = +50ms / cycle. universe 5,000 시 +5초 / cycle. P-05 의 자동 비활성 룰 (universe>1000 시 disable) 로 처리. 단 5,000 / 1,000 cutoff 의 정량 근거 약함. Phase 0 종료 시 운영 측정 → cutoff 정밀화 검토.

---

### C3. atr_migration_outlier_counter.json — date roll-over 로직

P-08 의 counter 가 `data.get("date") != today` 조건으로 일자 갱신. 여러 cron 동시 실행 시 (concurrency=verity-data-write 직렬화 적용 받지만 race 가능?) 카운터 손상 위험. 단 atr 산출은 직렬화 보호받음. 위험 낮음 — backlog 만.

---

### C4. market_abnormal escape 임계 — VIX 30 / 일변동 5% 의 보수성 (PM 인정)

**원본 권고** (PM): "KOSPI 일변동 > 2% 인 날이 5일 중 3일 이상" — 비교적 자주 trigger.
**구현 채택**: VIX > 30 OR |KOSPI/KOSDAQ daily change| > 5% 단일 일자 — 더 보수적.

**PM 평가** (사후): "5% 는 진짜 비정상. 2%/3일 룰은 escape hatch 가 항상 열려있을 위험. 보수적 채택이 베테랑답다." (사용자 메시지 2026-05-01).

**Backlog 검토 항목**:
- 14일 모니터링 운영 종료 후, 5/3~5/16 윈도우 내 escape 트리거 빈도 측정
- escape 0회 = 임계 적정 / escape 빈발 (3+회) = 임계 너무 느슨 / escape 발동 후 verdict fail → 임계 너무 보수적 평가
- Phase 1.5.1 진입 후 배경 데이터 누적 시 임계 정밀화 검토 (장기 baseline)
- 즉시 변경 X — 5/16 verdict 후 retrospective 시 검토

---

## 진행 결정

위 B1/B2/B3 모두 spec 변경 없이 implementation 만 조정. PM 보고 후 retrospective 시 종합 판단.

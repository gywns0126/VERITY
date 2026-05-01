# Phase 0 Runbook — ATR 표준화 마이그레이션 운영 절차

작성: 2026-05-01
대상: 본인 (PM)
참조: VERITY_Phase0_Phase1.5.1_v3_FullSpec.md + VERITY_Phase0_v3.1_Patch.md

---

## 핵심 원칙 (P-06)

**한 번에 한 변경만.**
- 코드 변경과 환경변수 변경 분리
- 각 변경 후 운영 1cycle 정상 작동 확인 후 다음 단계
- 디버깅 단순화: 이상 발생 시 어느 단계 원인인지 즉시 추적

---

## 변경 적용 순서

### Phase 0 코드 commit (Day 1) — 5/2

**현재 상태**: P-01 ~ P-09 코드 commit 완료 (commit hash 8개).
운영 동작 변화 X — `ATR_METHOD` GitHub Secret 미설정 → config.py default `wilder_ema_14` 적용.

⚠️ **중요한 미세 차이**: config.py default 가 이미 `wilder_ema_14` 이므로 코드 commit 이 main 에 머지되는 즉시 다음 cron 부터 Wilder 적용. **environment override 없이도 즉시 활성화됨**.

만약 5/2 secret 설정 전에 SMA 그대로 유지하려면:
```bash
gh secret set ATR_METHOD --body "sma_14" --repo gywns0126/VERITY
```
설정 후 코드 push.

### 5/2 cron 검증

- portfolio.json `recommendations[].technical.atr_14d_method` 노출 확인
- secret 미설정 시 = `"wilder_ema_14"`
- secret = `sma_14` 시 = `"sma_14"`
- 신규 holding `atr_method_at_entry` = 위와 동일

### 5/3 — 환경변수 활성화 (Day 2)

```bash
# Wilder EMA 활성화 (이미 default 이지만 명시)
gh secret set ATR_METHOD --body "wilder_ema_14" --repo gywns0126/VERITY

# A/B 비교 로깅 활성화
gh secret set ATR_MIGRATION_LOGGING --body "true" --repo gywns0126/VERITY
gh secret set ATR_MIGRATION_START_DATE --body "2026-05-03" --repo gywns0126/VERITY
```

**확인**:
- 5/3 cron 정상 실행
- portfolio.json `atr_14d_method = "wilder_ema_14"`
- `data/metadata/atr_migration_log.jsonl` 첫 row 생성
- jsonl 행에 ticker (6자리), atr_wilder, atr_sma, diff_pct 모두 포함

### 5/3 ~ 5/16 — 모니터링 (14일)

**매일 자동 모니터링**:
- A/B diff 분포 추이 (avg, P95, max)
- Outlier (30%+) 빈도
  - 일 5건 초과 시 텔레그램 자동 알림 (P-08)
- 신규 holding 의 `atr_method_at_entry = "wilder_ema_14"`
- 기존 SMA holdings 의 stop_price 변경 없음 (P-03 보호)

**수동 확인 (3일에 1회 권고)**:
```bash
# 가장 최근 100 row 분포
tail -100 data/metadata/atr_migration_log.jsonl | jq -s '
  {
    avg_diff: (map(.diff_pct | fabs) | add / length),
    max_diff: (map(.diff_pct | fabs) | max),
    outliers: (map(select(.diff_pct | fabs > 30)) | length),
    sample_count: length
  }
'
```

### 5/16 — 마이그레이션 검증 (Day 14)

```bash
python scripts/analyze_atr_migration.py --window-start 2026-05-03 --window-end 2026-05-16
# 또는 JSON 출력
python scripts/analyze_atr_migration.py --window-start 2026-05-03 --window-end 2026-05-16 --json
```

**판정 매트릭스 (사전 결정 2026-05-01, 변경 금지)**:

avg_diff_pct = 윈도우 내 atr_migration_log.jsonl 의 |diff_pct| 평균.

| avg_diff_pct | verdict | 후속 조치 |
|---|---|---|
| **< 15%** | **ok** | ATR_MIGRATION_LOGGING=false → Phase 1.5.1 진행 |
| **15% ~ 20%** | **monitoring** | 7일 추가 모니터 후 재판정 |
| **> 20%** (정상 시장) | **fail** | scripts/rollback_atr_to_sma.sh 실행 |
| **> 20%** (market_abnormal) | **monitoring_escape** | 즉시 rollback 보류, 정상 시장 7일 후 재판정 |

**market_abnormal escape 조건** (윈도우 내 1회라도 충족 시 발동):
- VIX > 30 (`macro.vix.value`)
- |KOSPI daily change_pct| > 5% (`market_summary.kospi.change_pct`)
- |KOSDAQ daily change_pct| > 5% (`market_summary.kosdaq.change_pct`)

**Escape 의 의미**: 시장 비정상 신호로 인한 ATR 분포 왜곡 가능성. fail 자동 발동 보류, 정상 시장 회복 후 재판정. 이는 ATR 산출법 자체의 결함이 아닌 외부 환경 변수로 인한 일시적 diff 확대 가능성을 인정.

**보조 지표 (verdict 자체에는 영향 X, 디버깅 참고용)**:
- `p95_diff_pct`: 분포 꼬리 — avg 와 차이 크면 outlier 분포 점검
- `outlier_count` (> 30%): P-08 텔레그램 alert 와 별개, 누적 카운트
- `sample_count`: 14일 운영 시 코어 85종목 × 14일 = ~1,200 권장. < 100 시 insufficient_data verdict

**exit code 매핑** (cron 자동화 시):
- 0: ok / 1: monitoring / 2: fail / 3: monitoring_escape / 4: insufficient_data

**ok 판정 시**:
```bash
# A/B 비교 로깅 종료 (운영 cycle 비용 제거)
gh secret set ATR_MIGRATION_LOGGING --body "false" --repo gywns0126/VERITY
```
→ Phase 1.5.1 진행 가능

**monitoring 판정 시**:
- 7일 추가 모니터링 후 재판정
- ATR_MIGRATION_START_DATE 갱신 (자동 비활성 연장 — 단 P-05 룰: 14일 만료. 수동 false 처리 또는 START_DATE 21일 후로 갱신)

**fail 판정 시**:
```bash
bash scripts/rollback_atr_to_sma.sh
```
→ Phase 0 자체 재검토. ATR 산출법 외 변수 검토 (시장 regime / 데이터 quality).

### UNIVERSE_RAMP_UP_STAGE 변경은 별도 일정

⚠️ **Phase 0 와 절대 동시 변경 금지**.
- 5/3 = Phase 0 environment 활성화
- ~5/16 = Phase 0 검증
- 5/17 이후 = Phase 1.5.1 진행 결정 후 별도 일정

UNIVERSE_RAMP_UP_STAGE > 1000 도달 시 P-05 가 자동으로 ATR_MIGRATION_LOGGING False 처리. 단 START_DATE 14일 만료 전에는 수동 OFF 권고.

---

## 자동 비활성 룰 (P-05)

다음 3 조건 중 하나라도 해당하면 A/B 로깅 자동 OFF:
1. `ATR_MIGRATION_LOGGING=false` (수동)
2. `UNIVERSE_RAMP_UP_STAGE > 1000` (Phase 2-A Stage 4 진입)
3. 마이그레이션 시작 후 14일 경과

3개 모두 충족 시 (default true + Stage 1 + 14일 이내) 만 활성. 안전.

---

## 자동 archive (P-07)

`atr_migration_log.jsonl` 5MB 초과 시 → `data/metadata/archive/atr_migration_log_{ts}.jsonl.gz` 자동 압축. 원본 삭제. 다음 row 부터 새 파일.

코어 85종목 × 14일 = ~1,200 row → 약 0.5MB. 일반 운영에서 rotation 발동 안 함. universe 5,000 시 rotation 발동 가능.

---

## 자동 alert (P-08)

`diff_pct > 30%` outlier 일 5건 초과 시 → 텔레그램 1회 발송 (`api.notifications.telegram.send_message`).
다음 날 카운터 자동 리셋.

---

## Rollback 시나리오

### Trigger 1: 5/3 ~ 5/16 모니터링 중 fail 판정
```bash
bash scripts/rollback_atr_to_sma.sh
```

### Trigger 2: 일 outlier 5건 초과 + 추가 위험 신호
- 텔레그램 alert 받음
- BrainMonitor CardATRMigration 확인 (Phase 0 후속 turn 에서 추가)
- 본인 판단: "이상 정도가 marginal vs 명백한 시장 regime 충돌" 분리

### Trigger 3: 신규 holding 손절 빈도 급증 (Wilder stop 거리가 SMA 보다 짧아 whipsaw 손절)
- 5/3 ~ 5/9 cron 첫 7일 stop_loss 트리거 카운트
- baseline (5/2 이전 7일 SMA) 대비 1.5배 초과 시 위험 신호
- 7일 추가 모니터 후 결정

---

## 운영 룰 (Type A/B/C 분류)

작업 중 새 의문 발견 시 `docs/QUESTIONS_BACKLOG.md` 에 분류 후 등록.

- **Type A** (Stop-the-line): silent failure / 검증 무효화 / 데이터 정합성 → 즉시 PM 보고
- **Type B** (Defer): 현재 Phase 결과 해석 영향 → 메모만, retrospective
- **Type C** (Backlog): 미래 분기 검토 → 메모만, 진행

## 현재까지 등록된 backlog 항목

- B1: send_alert 함수 부재 → send_message 사용 (Phase 0 commit 시 처리됨)
- B2: R_MULTIPLE 환경변수 이름/값 불일치 → 기존 운영 코드 우선
- B3: BrainMonitor 카드 적용 시점 → Phase 0 후속 turn 에 별도 진행 권고
- C1: ATR_MIN_PERIOD 변경 (15 → 20) — 의도된 정정
- C2: A/B 비교 호출 비용 — P-05 자동 비활성으로 처리
- C3: outlier counter race condition — 직렬화 보호 받음, 위험 낮음

---

## 다음 단계

Phase 0 종료 = 14일 모니터링 ok 판정 + ATR_MIGRATION_LOGGING=false.

→ Phase 1.5.1 (Backtest Validation) 진행. 별도 명령서 작성 예정.

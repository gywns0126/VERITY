# Staged Updates — post_phase_0 (2026-05-02 ~ 2026-05-16)

Phase 0 (ATR Wilder vs SMA migration smoke test) 기간 동안 누적될 학습 자료 / 룰 제안 / 코드 변경의
단일 저장소. **5/16 verdict 후** review → 적용.

## 왜 staging 인가

Phase 0 14일 smoke test 의 **A/B 변수가 ATR_METHOD / ATR_STOP_MULTIPLIER 단 둘**.
이 기간 brain 룰 / 가중치 / 임계값 / 추천 로직을 건드리면 verdict 의 신호 vs 노이즈 분리 불가.
→ Phase 0 영향 받는 변경은 모두 여기 staging.

## 적용 대상 (write-time triage)

| 변경 유형 | 처리 |
|---|---|
| `verity_constitution.json` 변경 | STAGED (HIGH) |
| `brain_score` 가중치 ±X% | STAGED (HIGH) |
| `api/intelligence/*` 룰 변경 | STAGED (HIGH) |
| 임계값 ±10% 이상 | STAGED (MEDIUM) |
| 추천 파이프라인 / `recommendations` 로직 | STAGED (HIGH) |
| ATR / 손절 / 익절 산식 | STAGED (HIGH) — Phase 0 본체 |
| 새 텔레메트리 / 로깅 / observability | 즉시 main (LOW) |
| 단순 버그 수정 / 주석 / 문서 | 즉시 main (LOW) |
| 새 스크립트 (Phase 0 영향 X) | 즉시 main (LOW) |
| ESTATE 작업 전반 | 별도 (이 framework 무관) |

애매하면 **STAGED 가 default**.

## 파일 구조

```
data/staged_updates/post_phase_0/
├── README.md             # 이 파일
├── decision_log.jsonl    # 항목별 사유 / 의존성 / tier 영구 기록 (append-only)
├── rule_proposals.json   # 적용 후보 룰 본문 (선택)
├── learning_materials.md # 본인이 본 자료 메모 (선택)
└── assumptions.yaml      # 가정 registry (refresh_assumptions.py 가 갱신)
```

코드 변경은 별도 git 브랜치 `staged/post_phase_0` 에 누적.
5/17 review 시 `git diff main..staged/post_phase_0` 한 번에 review.

## decision_log.jsonl 스키마

```jsonl
{"id":"learning_001","added_at":"2026-05-02T...","title":"...","tier":"HIGH|MEDIUM|LOW","depends_on_assumptions":["A1","A2"],"depends_on_items":[{"id":"learning_000","type":"hard"}],"rationale":"...","applied_at":null,"strikethrough":false,"strikethrough_reason":null}
```

`type`: `hard` (해당 dep 없으면 의미 자체 X — cascade invalidate) / `soft` (영향 받지만 독립 평가 가능 — flag_for_review).
default = hard. soft 마킹은 `--soft-justification` 명시적 정당화 필수.

## 5/17 review 절차

1. `python scripts/refresh_assumptions.py` — assumption 재검 + cascade strikethrough
2. `python scripts/staged_apply.py --list` — 살아남은 항목 확인
3. 항목별 apply: `python scripts/staged_apply.py --item learning_XXX --risk-tier HIGH --tier-evidence "..." --assumption-recheck-passed --decision-log-rationale-still-valid`
4. tier 별 cooldown 자동 적용 (24h between MEDIUM/HIGH)
5. apply 끝나면 staged/post_phase_0 → main 머지

## 수명 (verdict 의존)

| Phase 0 verdict | review 일자 |
|---|---|
| `ok` / `monitoring` | 5/17 |
| `monitoring_escape` | 5/24 (시장 정상화 +7d) |
| `fail` | 대부분 무효 (A2 invalidate cascade) — minimal review |

## 종료 조건

5/17 (또는 verdict 의존 일자) review 완료 + 모든 살아남은 항목 apply 또는 explicit reject 후
이 폴더 / 브랜치 archive (`data/staged_updates/_archive/post_phase_0_2026-05-XX/`).

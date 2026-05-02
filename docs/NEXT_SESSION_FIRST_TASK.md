# 다음 세션 진입 시 첫 작업 — 의무 (자동 진행)

**작성**: 2026-05-03 01:35 KST (Round 4 보강 — 심각도 1 결정 기록)
**참조**: `feedback_source_attribution_discipline` 학습 사례 8번째 / Round 1~4 commit (508cf10 ~ 039bdcb)
**우선순위**: 다음 세션 *첫 작업* 의무 (Round 5 다른 작업 보다 우선)

---

## 0. 작업 요약

본 세션 (5/2 ~ 5/3 새벽) Round 1~4 에서 신규 의제 5건을 docs 임시 hex ID 로 자동 생성했음. 이들은 **docs 만 기록**된 상태 — Supabase user_action_queue (single source of truth) 미등록.

다음 세션 진입 시 **첫 작업** 으로:
1. Supabase user_action_queue 에 5+1 (KIS backfill 추가) = **6 의제 등록**
2. 실제 UUID 6개 수신
3. docs 11+ 곳 임시 ID → 실제 UUID **sed replace 일괄**
4. verification grep 0건 확인
5. 학습 사례 8번째 (메모리 ↔ Supabase) 효과 검증

본 작업 미실행 시 = 본 세션 산출물의 cross-ref 모두 무효화.

---

## 1. 등록 대상 의제 (총 6건)

| # | 임시 ID | title | priority | depends_on | 등록 정보 source |
|---|---|---|---|---|---|
| 1 | `fa3c2d1e` | sector_thresholds 헬퍼 + Hard Floor 정정 sprint | 🔴 P0 | ac9d1dc1 검증 / e8a17b3c 선행 | `docs/REGRESSION_RISK_AUDIT_20260502.md` + `docs/SECTOR_PROPAGATION_SPRINT_SPEC.md` Step 5 |
| 2 | `e8a17b3c` | sector 필드 propagation 결함 정정 (KR sector 수집기 신규) | 🔴 P0+ | (선행 X) | `docs/OPS_VERIFICATION_20260502.md` §10 + `docs/SECTOR_PROPAGATION_SPRINT_SPEC.md` Step 1-3 |
| 3 | `b9d4f72a` | VAMS sector_diversification silent gap 검증 | ⚪ P1 | e8a17b3c 후속 D+1 | `docs/SILENT_ERRORS_20260502.md` Error 3 + `docs/SECTOR_PROPAGATION_SPRINT_SPEC.md` Step 4 |
| 4 | `c5e8f9a2` | vams.total_value=0 + holdings avg_price=0 silent error 정정 (hotfix) | 🔴 P0+ | (선행 X) — hotfix sprint | `docs/SILENT_ERRORS_20260502.md` Error 5 + `docs/CAPITAL_DATA_HOTFIX_SPRINT_SPEC.md` |
| 5 | `f3a8c1d4` | 데이터 layer 검증 의무화 — 모든 모듈 spec 의 전제 조건 | ⚪ P2 | (즉시 발효) | `feedback_source_attribution_discipline` 6번째 학습 사례 |
| **6 (신규)** | (Supabase 자동) | **KIS 계좌 거래 내역 자동 fetch backfill 모듈** (심각도 3 결정) | ⚪ P2 (hotfix 진입 시 P1 격상) | c5e8f9a2 hotfix Step 3 manual 입력 시도 후 | `feedback_source_attribution_discipline` 7번째 학습 사례 |

---

## 2. 작업 순서

### Step 1 — Supabase 등록 (사용자, ~10분)

사용자가 다음을 직접 처리:
- Supabase user_action_queue 테이블에 6 의제 등록
- 등록 정보: title / priority / depends_on / description (위 표 source 참조)
- 등록 시 실제 UUID 6개 수신
- 매핑 기록: docs 임시 ID → 실제 UUID

### Step 2 — Claude Code sed replace 일괄 진행 (자동, ~10분)

사용자 confirm 후 Claude Code 가:

```bash
# 매핑 (사용자가 Step 1 후 제공)
declare -A MAPPING=(
  ["fa3c2d1e"]="<actual-uuid-1>"
  ["e8a17b3c"]="<actual-uuid-2>"
  ["b9d4f72a"]="<actual-uuid-3>"
  ["c5e8f9a2"]="<actual-uuid-4>"
  ["f3a8c1d4"]="<actual-uuid-5>"
)

# 일괄 sed replace (docs + memory 11+ 파일)
for old in "${!MAPPING[@]}"; do
  new="${MAPPING[$old]}"
  grep -rl "$old" docs/ | xargs sed -i '' "s/$old/$new/g"
  grep -rl "$old" /Users/macbookpro/.claude/projects/-Users-macbookpro-Desktop--------/memory/ | xargs sed -i '' "s/$old/$new/g"
done

# verification — 임시 ID 잔여 0건 확인
for old in "${!MAPPING[@]}"; do
  count=$(grep -r "$old" docs/ /Users/macbookpro/.claude/projects/-Users-macbookpro-Desktop--------/memory/ | wc -l)
  echo "$old: $count 잔여 (0 이어야 함)"
done
```

### Step 3 — 6번째 의제 (KIS backfill) 등록 결과 docs 반영

`feedback_source_attribution_discipline` 7번째 학습 사례 + `docs/CAPITAL_DATA_HOTFIX_SPRINT_SPEC.md` Step 3 backfill 영역에 의제 ID 추가.

### Step 4 — verification commit

```bash
git add docs/ # + memory 변경 (memory 는 별도 처리 가능)
git commit -m "fix(docs): Supabase UUID 매핑 정정 — Round 1~4 임시 ID 5+1건 → 실제 UUID"
git push origin main
```

---

## 3. 정정 대상 파일 (현재 임시 ID 출현 위치)

11+ 파일에서 출현 (현재 grep 결과 baseline):

| 파일 | 임시 ID 출현 |
|---|---|
| `docs/ACTION_QUEUE_PRIORITIZATION_20260502.md` | fa3c2d1e × 3 / e8a17b3c × 2 / b9d4f72a × 2 / c5e8f9a2 × 2 / f3a8c1d4 × 2 |
| `docs/DECISION_LOG_MASTER.md` | (Part C + Cross-ref index 다수) |
| `docs/DECISION_LOG_20260502.md` | D-Sector / D-Holdings entry |
| `docs/REGRESSION_RISK_AUDIT_20260502.md` | fa3c2d1e × 1 |
| `docs/OPS_VERIFICATION_20260502.md` | e8a17b3c / fa3c2d1e / b9d4f72a / c5e8f9a2 / f3a8c1d4 |
| `docs/SILENT_ERRORS_20260502.md` | (5 ID 모두) |
| `docs/CAPITAL_EVOLUTION_MONITOR_SPEC.md` | c5e8f9a2 / b9d4f72a / e8a17b3c / f3a8c1d4 |
| `docs/CAPITAL_DATA_HOTFIX_SPRINT_SPEC.md` | c5e8f9a2 (다수) |
| `docs/SECTOR_PROPAGATION_SPRINT_SPEC.md` | e8a17b3c / b9d4f72a / fa3c2d1e / c5e8f9a2 |
| `docs/PHASE_1_1_RECONSIDERATION_SPRINT_SPEC.md` | c5e8f9a2 (다수) |
| 시스템 메모리 `feedback_source_attribution_discipline.md` | 학습 사례 5/6/7/8 (5 ID 모두) |
| 시스템 메모리 `project_capital_evolution_path.md` | c5e8f9a2 |

**주의**: 본 문서 (`NEXT_SESSION_FIRST_TASK.md`) 자체도 sed replace 대상 — 매핑 표 (§1) 의 임시 ID 컬럼 보존하되 grep 결과 0건 위해 별도 처리 필요. **권장**: §1 표의 "임시 ID" 컬럼 → "원래 임시 ID (history)" 로 후처리 의미 보존 + 다른 영역 sed replace.

---

## 4. 정정 안 했을 때 위험

- 본 세션 산출물의 *cross-ref 무결성 0%* — 모든 의제 추적 무효화
- 5/17 sprint 진입 시 PM 이 docs 와 Supabase 매칭 수동 진행 → 시간 비용 ↑ + 누락 위험
- 향후 분기별 review (8/2 예정) 시 cross-ref 신뢰성 부재
- 학습 사례 8번째 (의제 ID alias mismatch) 가 silent error 로 영구화

---

## 5. 진행 시점

베테랑 권장: **다음 세션 진입 시 첫 작업** (Round 5 다른 작업 보다 우선).

이유:
- Round 5 자체는 P1 정정 명세 (의제 ID 추가 등록 거의 X)
- 5/17 sprint 진입 전 정확한 UUID 확보 의무
- 그 시점까지 사용자가 Supabase 등록 시간 확보 (~10분)
- 다음 세션 진입 시 본 문서가 trigger — 자동 reminder

---

## 6. 본 작업 완료 후

- 본 문서 status = "✅ 완료" 갱신 (history 보존)
- `feedback_source_attribution_discipline` 학습 사례 8번째 의 effectiveness verification (sed replace 정합 통과 확인)
- Round 5 (P1 audit Step 4 명세) 진입 OR 다른 작업 진입

---

## 7. 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-03 01:35 KST | 초기 작성 — 심각도 1 결정 (옵션 b) + 6 의제 등록 표 + sed replace 절차 + 정정 대상 파일 매트릭스 |

---

문서 끝.

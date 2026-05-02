# Audit Step 4 — P1 정정 명세

**작성**: 2026-05-03 01:50 KST (Round 5 작업 9)
**진입 조건**: P1 audit (Step 3) 완료 후 — 5/2 audit Step 3 완료 (`docs/SOURCE_AUDIT_20260502.md` §8)
**예상 시간**: ~1시간 (메모리 정정 only, 운영 코드 변경 X)
**참조**: `docs/SOURCE_AUDIT_20260502.md` (Step 1 P0 + Step 3 P1) / 신규 메모리 `project_brain_v5_self_attribution`

---

## 0. Sprint 목표

P1 audit (Step 3) 결과 발견된 🔴 + ❓ 항목 9건의 *메모리 정정* (라벨링 + 검증 의제 큐잉). P0 audit Step 2 (5/2 완료) 와 동일 패턴. **운영 코드 변경 X** — 별도 sprint (`docs/SECTOR_PROPAGATION_SPRINT_SPEC.md` Step 5 / 별도 sprint 의제) 진입 후.

---

## 1. P1 audit 결과 요약 (Step 3 완료 baseline)

`docs/SOURCE_AUDIT_20260502.md` §8 Step 3 P1 audit 결과:

| Verdict | 카운트 | 항목 |
|---|---|---|
| ✅ 통과 | 2 | Lynch FAST_GROWER 임계 / panic_stages vix_range |
| ⚠️ 의제 큐잉 | 1 | Lynch CYCLICAL_KEYWORDS Ch.7 인용 (P0a 와 묶음) |
| 🔴 정정 + 회귀 위험 | 1 | 부채 300% Hard Floor ↔ sector_aware 충돌 (의제 ac9d1dc1 검증 완료 5/2 → fa3c2d1e 정정 sprint) |
| ❓ 자체 결정 라벨링 | 5 | VAMS 프로필 / Lynch 임계 (5조/1조/0.8/300%) / DGS10 4.5% / PEG 3.0 보수화 / VAMS 자본 비례 변환 |

**총 9 항목** — 본 spec = 9 항목의 *메모리 정정* 패턴.

---

## 2. 작업 단계 (메모리 정정 9건)

### Step 1 — 메모리 정정 5건 (P0 Step 2 패턴, ~30분)

**대상**: ❓ 자체 결정 라벨링 5건. 기존 메모리 추가 정정 (P0 Step 2 의 `project_brain_v5_self_attribution` 패턴).

| # | P1 audit 영역 | 정정 메모리 | 정정 내용 |
|---|---|---|---|
| 1 | P1a VAMS 프로필 임계 | `project_brain_v5_self_attribution` 보강 (Step 3 에서 일부 완료) | aggressive/moderate/safe 임계 자체 결정 명시 + 자본 규모 비례 변환 가이드 추가 |
| 2 | P1b Lynch 임계 (5조/1조/0.8/300%) | `project_brain_kb_learning` 또는 신규 메모리 | FAST_GROWER 시총 ≤ 5조 / STALWART 시총 ≥ 1조 / ASSET_PLAY PBR ≤ 0.8 / TURNAROUND 부채 ≤ 300% **자체 캘리브레이션 명시** + 산출 산식 (한국 KOSPI 200 분포 기반 추정 — 별도 검증 의제) |
| 3 | P1c DGS10 4.5% | `project_brain_v5_self_attribution` 보강 또는 신규 메모리 | 미국 10년 국채 4.5% 임계 자체 결정 명시 + 한국 시장 영향 channel 부재 caveat (간접 — 글로벌 valuation 압력) |
| 4 | P1c PEG 3.0 보수화 | `project_brain_kb_learning` 보강 | Lynch 원전 PEG > 2 / 본 시스템 3.0 = 자체 보수화 명시 + 한국 시장 EPS 가이던스 변동성 ↑ 보정 사유 |
| 5 | P1a VAMS 자본 규모 비례 변환 | `project_brain_v5_self_attribution` 보강 | 1억 운영 시 종목당 비중 하락 (15~30만원 효과 X), 비례 스케일링 수동 → 자동화 의제 (`project_capital_evolution_path` Tier transition checklist 정합) |

**산출**: 메모리 5건 정정 (대부분 기존 메모리 보강) + 정정 이력 명시 형식 (`[P1 audit Step 4 정정 2026-05-XX]`)

### Step 2 — 의제 큐잉 4건 (~15분)

**대상**: ⚠️ 의제 큐잉 1건 + 🔴 정정 + 회귀 위험 1건 + Step 1 정정의 검증 의제 추가 2건.

| # | 의제 | priority | 의존성 | docs cross-ref |
|---|---|---|---|---|
| 1 | CYCLICAL_KEYWORDS Lynch Ch.7 챕터 재검증 | ⚪ P2 | Lynch 원전 grep | 의제 d9a64306 (이미 등록) |
| 2 | 부채 300% Hard Floor sector 면제 정정 sprint | 🔴 P0 | Phase 0 verdict | 의제 fa3c2d1e (이미 등록) — `docs/SECTOR_PROPAGATION_SPRINT_SPEC.md` Step 5 |
| 3 | Lynch 임계 (5조/1조/0.8/300%) 산출 근거 보강 | ⚪ P2 | 메모리 정정 + 운영 누적 6개월+ | 의제 ad4fa2fd (이미 등록) |
| 4 | PEG 3.0 vs Lynch 2.0 보수화 근거 보강 | ⚪ P2 | 메모리 정정 (소량) | 의제 22cdd1ec (이미 등록) |

**산출**: action_queue 의제 4건 모두 *기존 등록* — 본 step 에서 신규 등록 X. 단 의제 description 갱신 권장 (Step 1 메모리 정정 cross-ref 추가).

### Step 3 — VAMS 자본 비례 변환 신규 의제 등록 (~15분)

**대상**: P1 audit 에서 발견된 *자본 규모 비례 변환 가이드 부재*. `project_capital_evolution_path` (5/2 신규) 와 정합 시키되, *현재 5/2 baseline 기준* 신규 의제 등록.

| 항목 | 값 |
|---|---|
| id | (Supabase UUID, 다음 세션 등록) |
| title | VAMS 프로필 자본 규모 비례 변환 가이드 신규 |
| priority | ⚪ P2 (Tier 1 → 2 transition 시 P1 격상) |
| depends_on | `project_capital_evolution_path` Tier 2 진입 checklist |
| description | 1억 운영 시 종목당 비중 하락 (15~30만원 효과 X) → 자본 비례 자동 스케일링 모듈 신규 (예: `api/vams/capital_scaler.py`) |

**산출**: 의제 매트릭스 추가 (`docs/ACTION_QUEUE_PRIORITIZATION_20260502.md` + `docs/DECISION_LOG_MASTER.md` Part C)

---

## 3. 검증 매트릭스

### 3-1. Step 1 (메모리 정정 5건)

- [ ] 메모리 5건 정정 (또는 기존 메모리 보강)
- [ ] `[P1 audit Step 4 정정 2026-05-XX]` 정정 이력 명시 형식 적용
- [ ] grep 검증 — *원전 출처 명시 X* 영역 P1 audit 9 항목 모두 정정 / 라벨링 통과

### 3-2. Step 2 (의제 큐잉 4건)

- [ ] 기존 의제 4건 description 갱신 (Step 1 메모리 정정 cross-ref 추가)
- [ ] action_queue 매트릭스 신규 등록 X 확인 (이미 등록)

### 3-3. Step 3 (VAMS 자본 비례 변환 의제 신규)

- [ ] Supabase 등록 (다음 세션 STEP -1 통합)
- [ ] action_queue 매트릭스 + master Part C 추가
- [ ] `project_capital_evolution_path` Tier 1 → 2 checklist 보강 (자본 비례 변환 항목 추가)

---

## 4. 운영 영향

**예상**:
- 메모리 정정 only — 운영 코드 / 운영 데이터 무영향
- 향후 룰 추가 시 silent drift 차단 (메타 원칙 시스템화 보강)
- P1 audit 영역의 자체 결정 라벨링 완료 → audit trail 무결성 ↑

**위험**: 없음 (메모리 정정 only)

**완화**: Step 1 메모리 변경 후 verification grep — 정정 대상 9 항목 모두 라벨링 또는 정정 통과 확인

---

## 5. 후속 의제 (Step 4 완료 후)

- 메모리 정정 효과 verification (1주 후 — 다음 세션 Claude 가 *원전 인용* 으로 오해하지 않는지 검증)
- P0 audit Step 2 (5/2 완료) + P1 audit Step 4 통합 후 *전체 audit 무결성 baseline* 확정
- 다음 audit cycle (분기별 — 8/2 예정) 진입 baseline

---

## 6. 학습 사례 cross-ref

본 spec = `feedback_master_rule_drift_audit` (Phase B drift audit) 의 *지속 적용 사례*.

- 4/29 정책 정립 (T1-08) → 5/2 P1 audit 발견 (Step 3) → 5/17+ 메모리 정정 (Step 4)
- 메타 원칙: **drift audit = 단발 X / 분기별 cycle 의무**
- 본 spec 자체가 audit cycle baseline — 다음 분기 (8/2) review 시 동일 패턴 진입

→ `feedback_source_attribution_discipline` 학습 사례 9번째 후보 (Step 4 완료 시점 추가 검토): "audit cycle 의 메모리 정정 패턴 시스템화 — 단발 정정 X / cycle 정정 의무".

---

## 7. 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-03 01:50 KST | 초기 작성 — Step 1 메모리 정정 5건 + Step 2 의제 큐잉 4건 + Step 3 VAMS 자본 비례 변환 의제 신규 + 검증 매트릭스 + 학습 사례 cross-ref |

---

## 8. 다음 세션 진입 조건 (필수 선행)

본 spec 진입 전 의무:

| 우선 | 작업 | docs |
|---|---|---|
| 1 | Supabase UUID 매핑 정정 (심각도 1) | `docs/NEXT_SESSION_FIRST_TASK.md` |
| 2 | Phase 0 verdict (5/16) ok | T1-22 / 의제 8c96aef5 |
| 3 | c5e8f9a2 hotfix sprint 완료 (조건부 — 자본 비례 변환 의제 등록만 가능) | `docs/CAPITAL_DATA_HOTFIX_SPRINT_SPEC.md` |

본 spec 자체는 *메모리 정정 only* 라 1/2 만 통과 시 진입 가능. 3 (hotfix) 미완료 시 Step 3 의 VAMS 자본 비례 변환 의제 등록만 보류.

---

문서 끝.

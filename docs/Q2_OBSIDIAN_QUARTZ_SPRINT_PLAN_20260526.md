# Q2 자기 trail 강화 sprint — Obsidian + Quartz O path

> **source**: [[project_brain_self_trail_strengthening_2026_05_25]] PM 명시 5/25 23시 선택. `docs/PERPLEXITY_ANSWERS_20260526.md` Q2 자문 정합.
> **trigger**: R 리포트 빈약 sprint 종결 ✓ 2026-05-26 (`2d63b2e2` 박힘) → 진입 가능.
> **목적**: VERITY-style "1인 헤지펀드 미만 + 콘텐츠 기관급" ([[project_positioning_top_retail]]) 자기 trail 공개 노출. LLM 무료 tier 못 가지는 차별점 (자기 산식 / 자기 운영 trail / Brain v5 임계 / Phase 0 / KIS 정책) 박음. CLAUDE.md RULE 6 정합.
> **예상 비용**: ~$1/월 (도메인만). Quartz hosting / GitHub Pages / Obsidian 본체 = 무료.
> **작업 분량**: ~4-8h (PM 결정 박은 후 Engineer 진입).

---

## 4단계 sprint plan

### 단계 1 (PM 결정) — Quartz 데모 직접 확인

PM 발화 trigger = 사용자가 아래 데모 link 3 직접 보고 "정합 / 미정합" 판정.

| 데모 vault | URL | 특징 |
|---|---|---|
| Quartz 공식 데모 | https://quartz.jzhao.xyz | Obsidian + Quartz 박는 사람용 official |
| Andy Matuschak | https://notes.andymatuschak.org | Evergreen notes, 백링크 중심, 산식 비공개 |
| Maggie Appleton | https://maggieappleton.com | Quartz 기반, 공개/비공개 분리 명확 |
| (선택) thelulzy 공개 vault | https://github.com/thelulzy/TF-EE-quartz-obsidian-vault | Quartz + Obsidian 구현 예시 (GitHub) |

**PM 정합 판정 후 단계 2 진입**.

### 단계 2 (PM 결정) — vault content path (a/b/c)

| 옵션 | path | 위험 / 비용 |
|---|---|---|
| (a) Claude 메모리 162 entry 직접 vault | 자동 mirror | ⚠ 사용자 메타 (사고 history / 시드 / PM 발화) 노출 위험 ↑ |
| (b) 별 vault 수동 큐레이션 | 새 vault directory + 매 entry 수동 박음 | 큐레이션 비용 ↑↑ (~4-8h × N entry) |
| (c) **Hybrid (메모리 정합 추천)** | 메모리 frontmatter `publish: true` 박힌 것만 vault → Quartz publish | 위험 ↓, whitelist 일회 박음 후 자동 sync |

**추천 = (c)** — 자동화 + 위험 제어.

### 단계 3 (PM 결정) — publish_whitelist 첫 10건 후보

5/26 발화 trigger 명시 메모리 + Q1 답 정합 (자기 자산 + 학술 정합 입증 자료):

| 우선 | 메모리 | 공개 사유 (CLAUDE.md RULE 6 정합) |
|---|---|---|
| ⭐ | [[project_brain_v5_self_attribution]] | 자기 결정 임계 (가중치 7:3 / 등급 75-60-45-25 / VCI / Lynch / Phase 0) — 학술 정합 입증 trail |
| ⭐ | [[project_capital_evolution_path]] | 자본 함수형 진화 6 tier — 자기 자산 #1 |
| ⭐ | [[project_kis_token_policy]] | KIS 1일 1토큰 정책 — 운영 사고 학습 trail |
| ⭐ | [[project_ic_dead_freeze_2026_05_23]] | N<50 산식 자유 tweak 금지 + Bayesian prior 학술 정합 |
| ⭐ | [[project_sector_aware_exemption_2026_05_26]] | Q5 RULE 7 sector 면제 spec + 학술 정합 |
| ⭐ | [[project_portfolio_slim_spec_2026_05_26]] | data 적재 spec audit drift 차단 룰 |
| ⭐ | [[project_atr_dynamic_stop]] | Phase 1.1 ATR×2.5 동결 trail |
| ⭐ | [[project_r_multiple_exit]] | R-multiple 1R/2R/trailing 50/30/20% 부분 익절 |
| ⭐ | [[project_minimum_n_milestones_2026_05_18]] | N=14/252/684 milestone (Bailey-Lopez de Prado 정합) |
| ⭐ | [[project_system_mantra]] | 7 동사 단일 루프 |

**whitelist 제외 (영구 비공개)**:
- 사용자 메타: `user_profile`, 시드 액수, 사용자 발화 trail
- PM 의사결정 trail: `feedback_pm_*`, `feedback_seed_size_conservatism`
- 사고 history: `feedback_kis_one_token_per_day_sentinel`, `feedback_master_rule_drift_audit`
- 베테랑 진단: `project_sprint_11_veteran_response`
- 외부 API key / 인프라 token

### 단계 4 (Engineer 자율) — Quartz setup + sync script + 자동화

PM 단계 1-3 결정 후 Engineer 자율 박을 작업:

| sub-step | 작업 | 작업 분량 |
|---|---|---|
| 4-1 | 별 repository `verity-methodology-vault` 신설 (private 시작, 단계적 public 전환) | ~30분 |
| 4-2 | Quartz 4 fork + customize (theme / domain) | ~1h |
| 4-3 | publish_whitelist 메모리 10건 frontmatter `publish: true` 박음 | ~30분 |
| 4-4 | sync script (`scripts/sync_memory_to_vault.py`) 신설 — whitelist 박힌 메모리 → vault dir mirror | ~2h |
| 4-5 | GitHub Actions deploy.yml (Quartz build → GitHub Pages 또는 Vercel) | ~1h |
| 4-6 | (옵션) verity-terminal Framer iframe embed (`/methodology` page) | ~30분 |
| 4-7 | 초기 vault content 검증 + publish 1차 박음 + 사용자 review | ~30분 |

**도메인 옵션** (PM 결정 의제):
- (i) GitHub Pages 무료 = `<username>.github.io/verity-methodology-vault`
- (ii) Vercel 서브도메인 = `methodology.verity-terminal.com` (~$1/월 SSL + 도메인 이미 박힘)
- (iii) 별 도메인 = `verity-methodology.com` (~$12/년)

**추천 = (ii)** (인프라 정합, [[project_vercel_infra]] 단일 프로젝트 추가 X, Vercel 서브도메인 무료 SSL).

---

## RULE 7 정합 검증

- 메모리 frontmatter `publish: true` 박음 = data field 추가 (산식 변경 X, RULE 7 미적용).
- whitelist 박힌 메모리 = 이미 박힌 자기 trail (가중치 / 임계 등 변경 X, 노출만).
- 외부 prompt 그대로 박는 path = 영구 제외 ([[feedback_no_new_llm_narrative_features]] 정합).

## 진입 trigger 박을 발화

- "데모 확인했어" / "데모 정합" → 단계 1 종결 → 단계 2 PM 결정
- "Hybrid path" / "c 옵션" → 단계 2 종결 → 단계 3 PM 결정
- "whitelist OK" → 단계 3 종결 → 단계 4 Engineer 자율 진입
- "Vercel 서브도메인" → 도메인 결정

## 영구 제외

- 외부 LLM prompt 그대로 박음 (Karpathy LLM Wiki / Graphify / Obsidian)
- 자기 trail 노출 없는 외부 도구 도입
- 사용자 메타 (시드 / 사고 history / PM 발화) 공개

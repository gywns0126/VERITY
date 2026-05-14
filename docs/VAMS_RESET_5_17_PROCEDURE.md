# VAMS RESET 5/17 PROCEDURE

작성: 2026-05-14 (D-3)
실행: 2026-05-17 KST 09:00 직전
근거: 메모리 `project_vams_reset_2026_05_17`

---

## 사전 준비 (D-3 ~ D-1)

- [x] `scripts/vams_reset_5_17.py` 검증 완료 (dry-run safe, `--execute` 명시 시에만 변경)
- [ ] **5/16 ATR Phase 0 verdict 확인** — 통과 시에만 5/17 진입 (W2/W3 wiring 격리 전제)
- [ ] `data/portfolio.json` git status 깨끗 (uncommitted 변경 없음)
- [ ] `data/vams/` 디렉토리 자동 mkdir 확인 (스크립트가 parents=True 처리)

## 실행 시퀀스 (5/17 KST 09:00)

| 시간 | 액션 | 주체 | 명령 |
|---|---|---|---|
| 08:50 | dry-run 최종 확인 | 사용자 | `python3 scripts/vams_reset_5_17.py` |
| 08:55 | pre-reset commit (rollback 가드) | 사용자 | `git add data/portfolio.json && git commit -m "📸 VAMS pre-reset snapshot"` |
| 08:58 | price_pulse cron 일시 정지 (선택) | 사용자 | dispatch_pulse 가드 또는 Vercel Cron 콘솔 |
| 09:00 | execute reset | 사용자 | `python3 scripts/vams_reset_5_17.py --execute` |
| 09:05 | git status 확인 | 사용자 | `git status data/portfolio.json data/vams/` |
| 09:08 | 결과 commit | 사용자 | `git add data/portfolio.json data/vams/ && git commit -m "🔄 VAMS reset 5/17 — fresh 1000만원 / Phase A 진입"` |
| 09:10 | price_pulse cron 재개 | 사용자 | (08:58 에 정지했다면) |
| 09:15 | smoke test | 사용자 | `python3 -m pytest tests/ -k vams -xvs` (있는 경우) |
| 09:20 | git push | 사용자 | `git push origin main` |

## 검증 체크리스트 (실행 후)

**Archive 산출물**:
- [ ] `data/vams/archive_pre_5_17/portfolio_vams_snapshot.json` (vams subtree + vams_profiles)
- [ ] `data/vams/archive_pre_5_17/portfolio_full_snapshot.json` (전체 portfolio.json 백업)
- [ ] `data/vams/archive_pre_5_17/reset_log.json` (when/why/fresh state)

**Fresh state (data/portfolio.json vams subtree)**:
- [ ] `cash` = 10,000,000
- [ ] `holdings` = []
- [ ] `simulation_stats.total_trades` = 0
- [ ] `active_profile` = "moderate" (보존)
- [ ] `reset_meta.reset_at` 박힘
- [ ] `vams_profiles` 보존 (다른 키 영향 없음)

## Rollback 절차 (이상 감지 시)

### Soft rollback (git 사용)
```bash
git revert HEAD              # 09:08 commit revert
git push origin main
```

### Hard rollback (git 없을 때)
```bash
cp data/vams/archive_pre_5_17/portfolio_full_snapshot.json data/portfolio.json
```

## 스크립트 한계 (사용자 수동 보완 필요)

`scripts/vams_reset_5_17.py` 가 처리 안 하는 항목 — 메모리 `project_vams_reset_2026_05_17` 의 명시 vs 스크립트 실제 동작 갭 (2026-05-14 검증):

| 항목 | 스크립트 처리 | 사용자 수동 액션 |
|---|---|---|
| `data/vams_history.json` | X (별도 파일) | **D-3 시점 미존재 확인됨**. 5/17 직전 재확인 후 존재 시 archive 별도 복사 |
| `data/recommendations.json` (현재 672KB, 옛 룰 추천) | X | **5/17 직전 비우기 또는 archive 로 이동** 결정 (메모리 = 옛 룰 후보 cleanup) |
| `vams.closed_positions` / `vams.history` / `vams.exit_history` fresh state 키 | X (fresh state 에 미포함) | 현재 portfolio.json 에도 없음 (운영 중 자동 생성). 필요 시 reset 후 빈 list 박기 |
| archive README.md (룰 snapshot: git sha + ATR config + W2/W3 weights) | X | **9시 이후 archive_pre_5_17/ 에 README.md 작성** — 옛 룰 결정점 보존 |
| commit prefix `[brain]` (메모리 정합) | X (사용자 commit 메시지 직접 작성) | 위 09:08 / 09:00 commit 메시지에 prefix 적용 결정 |

위 5건 중 **1, 2, 4 는 5/17 당일 사용자 액션 필수**. 3, 5 는 선택.

## Cold start 인지 사항

- price_pulse 가 동기화 전 30분간 admin dashboard NaN 표시 가능 (engine.py:178-179 안전 fallback 있음)
- history.json 비어있어도 validation INSUFFICIENT_DATA 표시 (정상)
- **65 거래일 게이트 카운트 = 5/17 부터 재시작**. 8월 말 PRODUCTION 게이트 재산정

## 5/17 Day 1 직후 작업 (참고)

reset 직후 즉시 진입:
- W2/W3 wiring (격리 정책 — ATR verdict 후 단일 변수 통제)
- Phase A: brain F+G sprint (메모리 `project_brain_score_funnel_audit`)
- Phase A: Stage 0/1 marker 박기 (`docs/UNIVERSE_FUNNEL_REFORM_PLAN_v0.2.md` §10)
- Phase A: step e DART pre-attach (`docs/STEP_E_SPEC_v0.1.md`)
- Earnings Sprint v0.3.1 진입 (메모리 `project_earnings_layer_sprint`)

## 정합 메모리

- `project_vams_reset_2026_05_17` — reset 결정 + timing
- `project_atr_phase0_migration` — 5/16 verdict + W2/W3 격리
- `project_funnel_5stage_sprint` — 5/17 sprint 시작점
- `project_brain_score_funnel_audit` — F+G sprint
- `project_earnings_layer_sprint` — Earnings 진입

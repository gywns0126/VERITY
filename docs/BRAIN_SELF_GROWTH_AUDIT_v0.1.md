# BRAIN 자가 성장 인프라 정밀 AUDIT v0.1

작성: 2026-05-16 (사용자 goal: 5축 정밀 검수 + 미래 방향성)
연관: feedback_continuous_evolution / project_brain_v5_self_attribution

---

## 종합 verdict: **🟡 56/100 — 데이터 축적은 완벽, 진화 logic 끊김, 미래 비전 약함**

| 축 | 점수 | 핵심 결함 |
|---|---|---|
| **P1 학습 루프** | 58/100 | 폐루프 33% (1/3 단계만 작동) |
| **P2 자체 검증** | 58/100 | Phase 1-N verdict cron 부재 |
| **P3 메모리 진화** | 58/100 | 인덱스 26개 누락 + cross-link 0 |
| **P4 운영 데이터** | 75/100 | IC sample N=0 + 가중치 자동 조정 미구현 |
| **P5 미래 방향성** | **32/100** | Brain v6/Tier 2+/글로벌 모두 0% 명시 |

**핵심 패턴**: 데이터는 다 적재되는데 **자동 read back / 가중치 자동 조정 = 0**. 입력 90 / 처리 35 / 출력 30.

---

## 🚨 HIGH 결함 TOP 10 (전체 audit 통합)

### 자가 진화 차단 결함 5건

| # | 결함 | 위치 | 영향 |
|---|---|---|---|
| **1** | brain_learning.jsonl 27/28 entries backtest_hit_rate_14d = null | `api/metadata/brain_learning.py:80` | 적중률 추세 계산 불가, 진화 prompt 입력 손실 |
| **2** | factor_decay IC 계산 OK but constitution writeback 0 | `api/quant/alpha/factor_decay.py:207` ↔ `verity_brain.py:810` | IC 붕괴 감지만 alert, 실제 가중치 조정 X |
| **3** | postmortem.system_suggestion 생성 but strategy_evolver 미반영 | `api/intelligence/postmortem.py:299` | 실패 분석 → 다음 cycle 단절 |
| **4** | IC per factor sample N=0 (insufficient_data 고착) | `api/quant/alpha/factor_decay.py:124` | factor_decay → weight_adjustments 자동 피드백 영원히 차단 |
| **5** | continuous_evolution 4가드 명시만, 자동 작동 0% | `docs/VERITY_SYSTEM_SPEC_2026.md:1499` | 룰 변경 후 이상 감지→자동 롤백 불가 |

### 검증 / 메모리 / 미래 비전 결함 5건

| # | 결함 | 위치 | 영향 |
|---|---|---|---|
| **6** | Phase 1/2/3 verdict cron 부재 (Phase 0만 1회성) | `.github/workflows/atr_phase_0_verdict.yml` | 후속 Phase 자가 검증 X |
| **7** | MEMORY.md 인덱스 26개 누락 (123 메모리 중 21% 손실) | `MEMORY.md` | 신규 메모리 검색 불가, 중복 생성 위험 |
| **8** | Brain v6/v7 로드맵 명시 0% | (메모리/docs 부재) | 다음 진화 방향 불명, 의사결정 표류 |
| **9** | Tier 2+ 운영 전략 미정 (Tier 1만 명시) | `CAPITAL_EVOLUTION_MONITOR_SPEC.md` | 1억 도달 시 즉시 운영 공백 |
| **10** | 글로벌 진출 로드맵 0 (US 베타 외 명시 X) | (메모리/docs 부재) | Japan/China/EU 진입 기준 부재 |

---

## 📊 5축 정밀 평가

### P1. 학습 루프 (58/100)

**작동**:
- ✅ 입력 수집 (backtest_archive / postmortem / brain_learning / factor_decay / trade_plan)

**끊김**:
- ⚠️ 피드백 → 정책 변환 (postmortem.system_suggestion 미사용 / IC weight constitution 미적용)
- ❌ 정책 적용 → 다음 cycle (auto_approve OFF, constitution v1 고착)

**폐루프 작동률 33%** (3단계 中 1단계만)

### P2. 자체 검증 (58/100)

**작동**:
- ✅ trust_score 8조건 verdict gate
- ✅ cron_health_monitor 일일 PASS/WARNING/FAIL
- ✅ cross_link_layer Brain hit_rate ↔ trust_score 정합

**부재**:
- ❌ Phase 1/2/3 verdict cron (Phase 0만 1회성 완료)
- ❌ regime_diag → portfolio weight 미연결 (신호 생산만)
- ❌ staged_updates 자동화 (decision_log.jsonl 1건만 수동)
- ❌ trust_log → Phase state 역피드백
- ❌ 메모리 ↔ 코드 drift 월간 자동 검사

### P3. 메모리 진화 (58/100)

**HIGH 5**:
1. MEMORY.md 인덱스 26개 누락 (21% 손실)
2. project_stock_filter_v0_enhancement (390줄) 코드 drift
3. cross-link `[[name]]` 0개 (메모리 고립)
4. 메모리 size 불균형 (가장 큰 게 평균 7배)
5. validation chain 부재 (verified_on 필드 0)

**현 상태**: 콘텐츠 품질 HIGH, 구조/인덱싱/동기화 붕괴 직전.

### P4. 운영 데이터 진화 (75/100)

**잘 됨**:
- ✅ brain_learning 28일 + IC 97일 + backtest_gap 150 trades 누적
- ✅ Alert dispatcher 기초

**병목**:
- ❌ IC per factor sample N=0 (factor_decay min_history_days=14 통과 X)
- ❌ hit_rate → brain_weights 코드 미존재
- ❌ continuous_evolution Guard 2-3 (grade 분포 모니터링) 비활성
- ❌ backtest_gap slippage > 30bps 알람 미구현
- ⚠️ AUTO_TRADE_ENABLED=false (실데이터 누적 차단)

### P5. 미래 방향성 (32/100 — 가장 약함)

**Blind spot 5**:
1. Brain v6/v7 로드맵 부재 (메모리 의존, 문서 0)
2. Tier 2-6 운영 전략 미정 (Tier 1만 명시)
3. 글로벌 진출 로드맵 0 (US 베타 외)
4. AI 모델 진화 정책 (Claude 5/6, Gemini 3, GPT-5) 0%
5. ESTATE + VAMS 통합 portfolio 가중치 0

**Phase B-C 진행도**:
- Phase A: 100% (오늘 박힘)
- Phase B: 40% (IC 추정만, 정밀 산식 미정)
- Phase C: 0%

---

## 🎯 우선순위 수정·보완 액션 (P0/P1/P2)

### P0 — 즉시 (1주 내)
1. **brain_learning backtest_hit_rate_14d 복구** — log_daily_signals 입력 구조 검증
2. **factor_decay IC sample 임계 완화** — min_history_days 14 → 7
3. **MEMORY.md 인덱스 26개 누락 자동 등록**
4. **Brain v6 명시 스펙 draft** (project_brain_v5_self_attribution 기반)
5. **Phase 1/2/3 verdict cron 템플릿** (Phase 0 복제)

### P1 — 2주 내
6. **postmortem.system_suggestion → strategy_evolver 자동 반영**
7. **hit_rate → brain_weights 자동 조정 logic** (`fact_score/sentiment_score × 0.8~1.2`)
8. **continuous_evolution Guard 3 (grade 분포 monitoring)** alert_dispatcher 추가
9. **staged_apply.py 스크립트 구현** (staged_updates 자동화)
10. **메모리 ↔ 코드 drift 월간 자동 검사 cron**

### P2 — 1개월 내
11. **Tier 2-3 운영 전략 문서화** (rebalance freq + hurdle + sector cap)
12. **backtest_gap slippage > 30bps 알람**
13. **trust_log → Phase state 역피드백** (manual_review 이력 → 현재 결정 가중치 감소)
14. **AI 모델 버전 관리 정책** (Sonnet/Gemini/Perplexity 업그레이드 trigger)
15. **AUTO_TRADE_ENABLED=true 진입 조건** (3 env + sanity check 자동화)

### P3 — 3개월 내
16. **ESTATE + VAMS 통합 portfolio 가중치 결정 로직**
17. **글로벌 진출 단계 로드맵** (Japan/China/EU)
18. **24h 운영 진입 조건** (사용자 1인 → 자동 매매 권한 신청 프로세스)
19. **Brain v7 비전** (Claude 5/6 multi-agent ensemble)
20. **Tier 4-6 자본 변화** (실시간 리밸런싱 / 글로벌 분산)

---

## 🚀 미래 비전 (6M / 1Y / 3Y)

| 시점 | Brain | Tier | 시장 | 자동매매 | 자산 |
|---|---|---|---|---|---|
| 현재 (5/17) | v5 sentiment 7→13 | 1 (8종목) | KR+US | VAMS mock | 주식만 |
| 6M (11/17) | v5 완성 + Phase B-C | 데이터 누적 | US 베타 독립 추적 | VAMS 검증 완료 | ESTATE v1.5 |
| 1Y (2027/5) | **v6 정착** | **Tier 2 진입 (1-10억)** | US slot 확대 | KIS 실매매 opt-in | 통합 rebalance 테스트 |
| 3Y (2029/5) | **v7+ auto-evolution** | **Tier 3-4 (10-100억)** | **Japan/China/EU 진입** | 실시간 자동 옵션 多 | 자산간 최적화 |

---

## 💡 결정적 발견

### "이미 잘 박힌 부분" (감추기 X)
- 데이터 누적 인프라: 30+ jsonl ledger, IC 97일, brain_learning 28일
- trust_score / cross_link / cron_health monitor 3축 안정
- 메모리 100+ 콘텐츠 품질 HIGH (출처 명시, 규칙 상세)
- 17 Perplexity 검증 결과 (자체 정량 12건 false 자동 발견)

### "수면 위 아래 차이"
**겉**: 세미 기관급 logic depth, 17 검증 인프라
**속**: 폐루프 33%, 자동 진화 logic 미연결, 미래 비전 32%

→ **5/18 첫 평일 cron 후 60-65 거래일 운영 = 진정한 자가 성장 진입은 P0/P1 액션 완료 후**.

### "5/17 D-day 의미 재정의"
- 코드 박힘 측면: ✅ 17 임계 검증 + Brain Signal Plan v0.2
- 자가 성장 측면: ⚠️ **진정한 진화는 아직 X** (loop 끊김)
- 향후 6개월 P0-P1 액션 = "자가 성장 진입" 첫 게이트

---

## 메모리 정합

연관:
- `feedback_continuous_evolution` (잠금 폐기 + 4가드 명시만)
- `project_brain_v5_self_attribution` (v5 자체 임계, v6 미명시)
- `project_capital_evolution_path` (Tier 1-6 매핑, 운영 변화 미정)
- `project_phase_2b_wide_scan` (65 거래일 게이트)
- `feedback_perplexity_collaboration` (외부 검증 의무)

신규 박을 메모리 후보:
- `project_brain_v6_roadmap` (P0-4)
- `feedback_self_growth_loop_completion` (loop 폐쇄 룰)
- `project_tier_evolution_v1` (Tier 2-3 운영 전략)

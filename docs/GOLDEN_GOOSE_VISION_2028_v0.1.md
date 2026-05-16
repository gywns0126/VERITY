# Golden Goose Vision 2028 v0.1 — Anti-fragile + Anti-FOMO 산식 + Framework Hierarchy

**박힘**: 2026-05-17 (Perplexity Q6 학계 자문 적용).

`project_golden_goose_vision` SSOT. 2028 도달 지표 Calmar 1.0+ / MDD <20% / Anti-fragile / All-weather / Anti-FOMO.

---

## 1. 1인 운용 Calmar 1.0+ 트랙레코드 현실 (Perplexity Q6)

**공개 검증 가능 5년 1인 트랙레코드 = 사실상 없음**. 구조적 이유:
- 개인 운용자 = GIPS 감사 의무 X → 자기보고 수치만 존재
- Calmar 5년 = 2 regime (2020 코로나 + 2022 금리충격) 통과 필요
- 블로그 / 트위터 공개자 중 브로커 연동 연간 감사 리포트 형태 = 극소수

**유사 사례 (참고 채널)**:
- Andreas Clenow (*Stocks on the Move*) — Substack
- Corey Hoffstein (Newfound Research) — 헤지펀드 법인화 병행
- Quantopian / QuantConnect 커뮤니티 — 라이브 5년+ = 2-3팀

**VERITY moat**: Calmar 1.0+ 1인 트랙 = VERITY 자체가 최초가 될 가능성 → **경쟁 해자**.

---

## 2. Anti-fragility 산식 (Perplexity Q6 학계 자문)

### 핵심 Index
\[
\text{Antifragility Index} = \frac{E[\text{Gain}|\text{Shock}]}{E[\text{Loss}|\text{Shock}]} > 1
\]

### 4단계 실무 적용

1. **바벨 배분 (Taleb 2012 정합)**:
   - 안전자산 85~90% (단기채 / 현금)
   - 비선형 초고위험 10~15% (옵션 롱 / 변동성 매수)
   - VERITY 3-Tier (60/30/10) = barbell 변형. **conservative 60% = 바벨 안전 / aggressive 10% = 바벨 비선형**

2. **Convexity 테스트**:
   - 월간 수익률 분포에서 `Skewness > 0` (오른쪽 꼬리 두꺼움)
   - `Kurtosis > 3` (정규분포보다 꼬리 두꺼움)

3. **Volatility Benefit Ratio (VBR)**:
   ```python
   VBR = avg_return_high_vol_months / avg_return_low_vol_months
   if VBR > 1.5:
       antifragile_confirmed = True
   ```

4. **Delta-adjusted Stress P&L**:
   - 시장 -10% 시 portfolio P&L 양수 (or 벤치마크 초과) → 조건 충족

### 측정 인프라 (별 sprint 큐)
- `api/quant/antifragility.py` 신설 — monthly skewness / kurtosis / VBR 산출
- `cron_health_monitor` step 추가 — Antifragility Index 시간 추세
- 2028 vision: AI > 1 유지 (= 충격에서 이익 비대칭 우위)

---

## 3. Anti-FOMO 산식 (Perplexity Q6)

\[
\text{FOMO Score} = \frac{\text{Realized Turnover}}{\text{Rule-based Turnover}} - 1
\]

| FOMO Score | 해석 | 액션 |
|---|---|---|
| > 0.3 | 위험한 충동매매 | 코드 룰 강제 강화 |
| 0.1 ~ 0.3 | 주의 | 검토 |
| < 0.1 | **Anti-FOMO 달성** ✅ | 정상 |

추가 지표:
- `Entry Timing Regret Rate = (놓친 종목 평균수익) / (portfolio 평균수익)`
- **추적하지 않는 것 자체가 Anti-FOMO 규율** (한 번 추적 시작 = FOMO 정신적 비용 폭증)

### 측정 인프라 (별 sprint 큐)
- VAMS trade history 의 자동 매매 (rule_id 박힘) vs 수동 매매 분리
- `realized_turnover` = 일별 매매 회수, `rule_based_turnover` = trade_plan v0 의 transition_triggers 발화 횟수

---

## 4. 1인 운용 vs 헤지펀드 4대 함정 (Perplexity Q6)

| 함정 | 1인 특유 | 헤지 특유 |
|---|---|---|
| Over-trading | 직장 병행 이중 피로 → 충동 | AUM 압박으로 알파 희석 |
| 심리 | 손실 = 가계 직결, 감정 분리 X | 투자자 리덤션 공포 |
| Data Dredging | KOSPI 800 종목 p-hacking | 검증 layer 부재 |
| Curve Fitting | 백테스트 20+ 파라미터 OOS 붕괴 | 과거 regime 과적합 |

### 1인 최대 고유 함정: **감시자 부재 (No Second Opinion)**
헤지펀드 = 리스크 관리자 + CIO + 투자위원회 서로 견제. 1인 = 설계자 = 실행자 = 심판 동일인 → **자기확인편향 시스템 차단 불가**.

**해결**: 사전 설계 규칙 (Rule-set) 을 **코드로 고정** + 수동 오버라이드 불가 구조. VERITY:
- `verity_constitution.json` = 룰 SSOT
- 자동 매매 = VAMS engine 규칙 통과만
- 사용자 수동 override = audit log 의무 (P1 sprint 큐)

---

## 5. 27 Books + 23 Frameworks 통합 Hierarchy of Authority

### Level 0 — 헌법 (불변 원칙)
- MDD 하드캡 <20% (위반 시 자동 청산, ex-ante gate)
- runtime MDD stop 20% (실시간 강제, ex-ante 와 별)
- 포지션당 최대 손실 한도 (개별 손절)
- 최대 레버리지 한도 (개인 = 0, 신용 X)

### Level 1 — 전략 레이어 (도메인 분리)
- **종목 선정**: Greenblatt + Piotroski (가치/퀄리티), Lynch 6 분류 (project_brain_kb_learning)
- **리스크 사이징**: Kelly Criterion + Half-Kelly, ATR×2.5 stop, Capital 3-Tier (60/30/10)
- **매크로 레짐**: Dalio All-Weather + Taleb Barbell, market_horizon V2.1
- **진입/청산 타이밍**: BB/MA/RSI rules (trade_plan v0), R-multiple 부분 익절

### Level 2 — 운용 레이어 (행동 규율)
- **Anti-FOMO Rule**: 신호 없으면 무조건 현금 유지
- **Anti-Overfit**: 파라미터 수 ≤ log₂(샘플 수)
- **사이드 직장인 budget**: Claude API 월 $20 ([[project_claude_budget_guard]])
- **Workflow git add 정합**: 신 logging path 추가 시 의무 audit ([[feedback_data_collection_verification_mandatory]])

### Level 3 — 리뷰 레이어 (월간 자기감사)
- 룰 위반 횟수 기록 (override audit log)
- Realized vs Rule-based Turnover 비교 (FOMO Score)
- Calmar / MDD 추세 (분기)
- Anti-fragility Index (분기)

### 자기모순 회피 3 원칙 (Perplexity Q6 학계 자문)

1. **도메인 분리**: 두 framework 충돌 시 각자 도메인 분리 (Taleb = 꼬리위험 / Greenblatt = 종목선정). 같은 결정에 동시 적용 X
2. **Falsifiability**: 각 framework 에 "어떤 결과면 폐기" 사전 명문화. 없으면 사후 합리화
3. **Occam's Razor**: 두 framework 동일 예측 시만 신호 채택 (앙상블 일치). 단일 framework 신호 = 가중치 낮춤

### VERITY 2028 맥락
27 books × 23 frameworks 진짜 가치 = **모두 적용 X**. **레벨 0 헌법과 충돌하는 framework 발견 → 제거 필터**.

"황금알 낳는 거위" 비유 그대로 — 거위 해부 (오버라이드 충동) 차단이 Calmar 1.0+ 핵심 조건.

---

## 6. 2028 Vision 측정 지표

| 지표 | 2028 목표 | 측정 시점 | 산식 ref |
|---|---|---|---|
| **Calmar** | 1.0+ | 2027 운영 누적 12개월+ | annual_return / abs(MDD) |
| **MDD** | <20% | 매월 실측 | rolling 252d max-drawdown |
| **Anti-fragile** | AI > 1 + Skew > 0 + Kurt > 3 + VBR > 1.5 | 분기 | 본 docs §2 |
| **Anti-FOMO** | Score < 0.1 | 월간 | 본 docs §3 |
| **All-weather** | regime 4종 (bull/bear/inflation/deflation) 모두 양수 | 연간 | regime tag × P&L |
| **장 무관 수익** | 황금알 — 12개월 rolling 양수 | 매월 | rolling annual return |

---

## 7. Roadmap (2028 도달 path)

```
2026-05 (현재) ─→ Phase 1 (개미 최강) 잔존 결함 fix
2026-06 ─→ Earnings Layer Sprint + Master Rule Drift Audit Phase B
2026-08 말 ─→ TG-1 wide_scan PRODUCTION
2026-08 ─→ Phase 2 Module 1 (Factor v0)
2026-09 ─→ Phase 2 Module 2 (Stress v0)
2026-10 ─→ Phase 2 Module 3 (Regime v0)
2026-11 ─→ Phase 2 Module 4 (Portfolio v0) + repo private (TG-3)
2026-12 ~ 2027-01 ─→ Phase 2 Module 5 (Attribution v0)
2027 Q1 ─→ TG-2 Multi-bagger Bagger Stage Manager (한국 세제)
2027 운영 ─→ Calmar / MDD 측정 가능 (12개월 누적)
2027 ─→ Anti-fragility 산식 + Anti-FOMO 측정 인프라 (별 sprint)
2028 ─→ Calmar 1.0+ / MDD <20% / All-weather / Golden Goose 도달
```

---

## Cross-link

- [[project_golden_goose_vision]] (SSOT)
- [[project_capital_evolution_path]] (6 tier × 7축)
- [[project_positioning_top_retail]] (Phase 1/2)
- [[project_institutional_5module_roadmap]] (Phase 2 5 모듈)
- `docs/PHASE_2_5_MODULE_ROADMAP_v0.1.md` (모듈 학계 자문)
- `docs/MASTER_RULE_DRIFT_AUDIT_v0.1.md` (Phase B 룰 audit)
- `docs/PHILOSOPHY_TIER_ROUTING_v0.md` (3-Tier SSOT)

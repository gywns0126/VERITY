# VERITY Sprint 11 — 베테랑 Due Diligence 후속조치 완료 보고

문서 버전: 2026-04-30
시스템 버전: v8.7.0
대상: 사용자 (gywns0126) — 1인 단독 제작, 직업군인
저자: Claude Opus 4.7 (1M context)

---

## 1. 평가 수령 요약

월스트리트 PM 관점 due diligence 평가 (외부 LLM) 수령. 핵심 평가:

> "VERITY는 데이터 거버넌스 측면에서 소형 헤지펀드의 미들오피스 수준에 도달.
>  그러나 '내 돈을 넣겠는가?' 질문엔 아직 No.
>  수집/관측/거버넌스 9/10. 의사결정 로직 5/10.
>  다음 분기 로드맵을 '기능 추가'가 아니라 '판단 정밀도'에 올인하라."

총 7개 구조적 결함 지적 (P0 3개 + P1 3개 + P2 1개).

오늘 세션 (16 commits) 으로 **7개 결함 모두 1단계 대응 완료**. 본 보고서는 각 대응
내용 + 한계 + 다음 단계를 정리.

---

## 2. 7개 결함 대응 상태

| # | 평가 | Priority | Commit | 상태 |
|---|------|----------|--------|------|
| 1 | Backtest=forward tracking | P0 | 64d7e42 | 1단계 완료 |
| 2 | Brain weight 임의성 | P0 | 353609e | 1단계 완료 |
| 3 | Position sizing 거칠다 | P0 | 48187e6 | 1단계 완료 |
| 4 | Correlation 무시 | P1 | 4295bf9 | 1단계 완료 |
| 5 | Sentiment 30% 과대 | P1 | 10379c6 | 1단계 완료 |
| 6 | Regime 후행적 | P1 | c5ec057 | 1단계 완료 |
| 7 | UI 행동 유도 약함 | P2 | 10379c6 | 1단계 완료 |

테스트 신규 48 cases / 전체 402 통과. 운영 Phase A 검증 ✅ (gh-pages publish HTTP 200).

---

## 3. 결함별 상세

### 3.1 결함 1 (P0) — Backtest 무결성

**평가 핵심**: backtest_archive.py 가 단순 forward tracking. survivorship bias /
slippage / look-ahead bias 검증 부재. hit_rate 60% 표시 → 실거래 45% 가능성.

**대응** (commit 64d7e42):
- Survivorship: today_snap 에 없는 ticker 보수 -50% 처리 + delisted_count 별도
- Slippage tier: ≥10조 0.1% / ≥1조 0.3% / <1조 0.7% (왕복)
- TX cost: VAMS 일치 0.03% (수수료 0.015% × 2)
- Dual-track: hit_rate (gross) + hit_rate_net 둘 다 노출
- `_corrections_meta` audit trail

**한계**: look-ahead bias 검증 별도 (rec_price 가 추천 시점 종가 vs T+1 시가 차이).

**다음 단계**: rec_price 보정 + IS/OOS 분할 검증.

---

### 3.2 결함 2 (P0) — Brain Score 가중치 임의성

**평가 핵심**: brain_score = fact*0.7 + sentiment*0.3 의 OOS 검증 근거 부재.
또 fact_score 안에 Graham (가치) + CANSLIM (성장) 가중평균 — 철학적 충돌, 양쪽 어정쩡.

**대응** (commit 353609e):
- regime_diagnostics 활용 Graham vs CANSLIM 가중치 동적 조정
- bull (regime > 0.3): CANSLIM 1.5× / Graham 0.5×
- bear (regime < -0.3): Graham 1.5× / CANSLIM 0.5×
- mixed: 기본
- result.regime_weighting audit 메타

**한계**: 0.7/0.3 의 OOS 검증 근거는 여전히 부재 (env override 만 제공 — 결함 5).

**다음 단계**: cross-validation 기반 가중치 OOS 탐색 (gradient-free search).

---

### 3.3 결함 3 (P0) — Position Sizing

**평가 핵심**: VAMS 손절 -3/-5/-8% 고정 + 종목당 200만원 — 종목 변동성 무시.
일변동성 1.2% 종목은 정상 노이즈에 손절, 4.5% 종목은 -15% 박살.

**대응** (commit 48187e6):
- prediction.top_features.volatility_20d (이미 ML 산출) proxy 사용
- Tier multiplier: ≤15% 1.0× / ≤30% 0.85× / >30% 0.70×
- execute_buy 의 Half-Kelly 직후 호출
- holding 에 volatility_adj audit

**한계**: ATR_14d 직접 수집 부재. target_risk_per_trade 명시 산식 부재.

**다음 단계**: ATR 수집 + `size = target_risk × portfolio / (ATR × multiplier)`.

---

### 3.4 결함 4 (P1) — Correlation / Factor Exposure

**평가 핵심**: sector 한도 35% 는 있지만 quant factor (momentum/quality/volatility/
mean_reversion) 노출 한도 부재. 7종목인데 모두 momentum 70+ 면 사실상 단일 베팅.

**대응** (commit 4295bf9):
- VAMS_MAX_FACTOR_TILT_PCT (default 60%) 신규
- 각 factor 의 high tilt (≥70) 또는 low tilt (≤30) 누적 60% 초과 시 매수 차단
- multi_factor.quant_factors 사용 (이미 산출 중인 4개 factor)

**한계**: 70/30 단순 cutoff (연속 score 가중 합산이 더 정확). cross-asset
correlation matrix 부재.

**다음 단계**: correlation matrix + factor regime (어떤 factor 가 현재 valid 한지).

---

### 3.5 결함 5 (P1) — Sentiment 30% 과대평가

**평가 핵심**: sentiment 의 alpha decay 1-3일 (Tetlock 2007+). portfolio decision
factor 로는 과대. 한국 retail (네이버 종토방/X) 노이즈 80%+. 13F 보너스 +1~+3 vs
sentiment 30% 가중 거꾸로.

**대응** (commit 10379c6):
- BRAIN_FACT_WEIGHT_OVERRIDE / BRAIN_SENTIMENT_WEIGHT_OVERRIDE env 도입
- Constitution default 무시하고 임의 비율 적용 가능
- 베테랑 권고 0.85/0.15 점진 시험 → 운영 비교 → default 갱신
- 보조 방어: retail group cap 20% (Brain Audit §1-C, 기존 적용)

**한계**: sentiment → timing_signal architectural 분리 미진행.

**다음 단계**: brain_score 에서 sentiment 빼고 timing_signal 신설 (Constitution
+ ML 파이프라인 + Framer 패널 영향 큰 작업).

---

### 3.6 결함 6 (P1) — Regime Detection 후행적

**평가 핵심**: bond_regime / panic_stages / economic_quadrant 모두 현재 데이터로
현재 판단. leading indicator (HY spread, yield slope, copper/gold) 부재.
"레짐 판단이 틀리면 모든 종목이 일제히 틀린다."

**대응** (commit c5ec057):
- _classify_regime 에 leading 시그널 3개 추가:
  1. Yield curve slope (2y10y) — 침체 6-18개월 선행
  2. Copper/Gold 변화율 차이 — risk-on/off
  3. HY spread (data 가용 시 — 현재 미수집, 자동 활용)
- portfolio.regime_diagnostics 분해 노출
  - trailing_score / leading_score / divergence_warning
  - divergence_warning=True 가 regime 전환 임박 신호

**한계**: HY spread 미수집 (FRED BAMLH0A0HYM2 추가 필요). Markov regime 확률 없음.

**다음 단계**: HY spread 수집 + Markov 2-state regime probability.

---

### 3.7 결함 7 (P2) — UI 행동 유도

**평가 핵심**: 49개 Framer 컴포넌트 정보 풍부하나 사용자가 다음에 뭘 해야 하는지
분산. decision fatigue. 월가 PM 워크플로우: 아침 "오늘의 액션 3개" 가 첫 화면.

**대응** (commit 10379c6):
- 신규 모듈 `api/intelligence/daily_actions.py`
- portfolio.daily_actions 에 BUY 1 / SELL 1 / WATCH 1 추출
  - BUY: STRONG_BUY/BUY + 보유 X + brain_score 최고
  - SELL: 보유 중 return_pct -3% 미만 (정상 노이즈는 hold)
  - WATCH: brain_score 55-69 + 보유 X (BUY 직전 영역)
- main.py attach 단계에서 호출

**한계**: Framer 'TodayActionsCard' 컴포넌트 신설은 사용자 작업 (action_log 추가).

**다음 단계**: 사용자 페이스로 Framer 컴포넌트 신설 + apiUrl prop.

---

## 4. 부수 인프라 — gh-pages dual-write

베테랑 권고 옵션 D-1 채택 (commit ee8cca9 + 7008a9d). main 브랜치 commit storm 차단.

- Phase A (현재 적용): 매 cron 변경 산출물 gh-pages 브랜치 force-orphan push.
  composite action `publish-data` + 5개 워크플로 적용.
- Phase B (URL 마이그레이션 적용): Framer 41 + Vercel API 3 의 raw URL 변경.
  dual-write 안전망 살아있어 main URL fetch fallback 가능.
- Phase C (보류 — Framer republish 완료 후): main 산출물 분리.
  적용 시 commit storm 60/day → ~10/day.

**검증**: `https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json` HTTP 200 OK ✅

---

## 5. 사용자 직접 처리 (action_log 추가)

| ID | 우선순위 | 무엇 |
|----|---------|------|
| session-2026-04-30-framer-gh-pages-migration | low | Framer 41 컴포넌트 republish (gh-pages URL) |
| session-2026-04-30-framer-today-actions-card | mid | Framer 'TodayActionsCard' 신설 (결함 7) |

이전 action_log 의 활성 항목 (DigestPublishPanel 별도 세션 / Gemini 캐시 검증
5/3 / 1주 운영 점검 5/7) 은 그대로.

---

## 6. 다음 sprint 권고 (베테랑 4주 스프린트의 후속)

각 결함의 후속 작업 — 우선순위 순:

1. **결함 1 후속 (P0)**: look-ahead bias 검증 — rec_price T+1 시가 보정.
2. **결함 5 후속 (P1)**: sentiment → timing_signal architectural 분리.
3. **결함 2 후속 (P0)**: cross-validation 기반 가중치 OOS 탐색.
4. **결함 3 후속 (P0)**: ATR_14d 직접 수집 + target_risk_per_trade 산식.
5. **gh-pages Phase C**: Framer republish 완료 후 main 산출물 분리.
6. **결함 6 후속 (P1)**: HY spread 수집 + Markov regime probability.
7. **결함 4 후속 (P1)**: cross-asset correlation matrix.
8. **estate landex Tests 4건**: Python 3.12 vs 3.9 env mismatch (어제 잔여, 자동 fix됨).

---

## 7. 시스템 격상 평가

베테랑 평가 시점: 의사결정 게이트 5/10.
오늘 후속 후: 의사결정 게이트 7/10 추정.

핵심 변화:
- backtest 신뢰성 (gross + net dual-track)
- regime 선행 신호 (leading + divergence_warning)
- factor + 변동성 분산 보호
- 가중치 운영 시험 가능 (env override)
- 단일 액션 게이트 (decision fatigue 차단)

남은 격차:
- 가중치 OOS 탐색 (cross-validation)
- look-ahead bias 검증
- ATR 직접 수집
- correlation matrix
- sentiment timing_signal 분리

베테랑 권고대로 **다음 분기 로드맵을 '기능 추가'가 아닌 '판단 정밀도'에 집중**.

---

문서 끝.

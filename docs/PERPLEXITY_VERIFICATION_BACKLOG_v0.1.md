# PERPLEXITY VERIFICATION BACKLOG v0.1

작성: 2026-05-16 (5/17 Sprint Day 1, audit 결과 통합)
연관: memory `feedback_perplexity_collaboration` (외부 사실/통계/법규 = Perplexity 1순위)
       memory `feedback_source_attribution_discipline` (출처 명시 의무)

---

## 전수 audit 결과 요약

**총 76개 임계값 / 매직 넘버 식별** (전수 audit, Explore agent 2026-05-16):
- 출처 **강** (학계/실무 표준 인용 명확): 17개 → 검증 불필요
- 출처 **중** (단일 출처 일관, 환경변수 기본값): 25개 → IC 모니터링으로 자동 보정
- 출처 **약** (자체 설정, "임의 임계", TODO): **34개 → Perplexity 검증 가치**

이 백로그는 출처 "약" 항목 중 검증 가치 HIGH/MED **17건** 정리.

---

## 🔴 HIGH 우선순위 (5건 — 즉시 검증 후 임계 fine-tune)

### Q1. Wide Scan PRODUCTION 65 거래일 게이트 근거
**위치**: `api/config.py:298` / memory `project_phase_2b_wide_scan`  
**현 가정**: Wide Scan SHADOW → PRODUCTION 승급 게이트 = **65 거래일** (≈ 3개월 영업일)  
**문제**: 코드 주석/메모리 어디에도 "왜 65" 근거 X. 60·90 일도 가능했음.

**Perplexity 질문**:
> 정량 트레이딩 시스템의 SHADOW → PRODUCTION 승급 검증 기간 학계/실무 표준은? 65/90/120/252 거래일 중 IC stability 측면에서 권장값? Brain-style 종합 점수 시스템의 OOS 검증 표본 크기 권장 (BARRA / AQR / Two Sigma 가이드라인 있나).

**검증 후 액션**: 65 → 적정값 조정 시 memory `project_phase_2b_wide_scan` + config.py 동시 정정.

---

### Q2. Hohn (TCI) 환원율 < 1% / < 3% 임계
**위치**: `api/intelligence/veteran_triggers.py:244-247`  
**현 가정**: 환원율 (배당+자사주) < 1% = Hohn TCI 캠페인 정량 임계 / < 3% = "낮음"  
**문제**: 코드 주석만 "TCI 캠페인 사례 정합" — 실제 정량 근거 미확인.

**Perplexity 질문**:
> TCI (The Children's Investment Fund) Christopher Hohn 의 activist 캠페인 사례 (J-Power 2008 / Coal India 2014 / Volkswagen 2022 / Aena 2018 등) 진입 시점 target 회사들의 환원율 (dividend yield + buyback yield) 분포. 1% 미만이 "capital allocation 부실" 임계로 적정한가? Hohn 본인 발언/TCI 보고서에 명시된 정량 임계 있나?

**검증 후 액션**: 1% / 3% 임계 정정 또는 추가 차원 (ROIC vs WACC 격차 등) 보강.

---

### Q3. Druckenmiller VCI |val| < 15 conviction 정합 임계
**위치**: `api/intelligence/veteran_triggers.py:68`  
**현 가정**: VCI |val| < 15 = fact-sentiment 정합, 큰 발산 X → conviction 강화  
**문제**: 자체 설정. Cohen contrarian (VCI ≥ 25 fact ≥ 60) 와 다른 차원인데 15·20·25 분리 근거 부재.

**Perplexity 질문**:
> Stanley Druckenmiller 의 "high conviction" 진입 정의 정량화 사례. 그가 인터뷰 / 강연 (Sohn / Robin Hood / Lost Tree) 에서 명시한 conviction 임계 (Brain-style 점수 환산 가능한 자체 기준)? "확신 있을 때 집중, 아니면 작게" 룰의 정량 임계 (예: position size + score 매트릭스)?

**검증 후 액션**: VCI 임계 정정 또는 Druckenmiller 본인 conviction sizing 룰 (Soros macro 패턴) 별도 모듈 분리.

---

### Q4. 카테고리 리더 5%p 매출 격차 임계 (P0a 자체 정량)
**위치**: `api/analyzers/multi_bagger_signals.py:131` / memory `project_multi_bagger_watch` line 25  
**현 가정**: 신호 3 카테고리 리더 = 시총 1위 + 매출 격차 ≥ 5%p (sector 평균 대비) = 자체 설정  
**문제**: Lynch "카테고리 리더" 원전 (Ch.7 인용 부정확 P0a 정정) → 자체 임계. 5%p 가 적정한지 미검증.

**Perplexity 질문**:
> Lynch *One Up On Wall Street* 또는 *Beating the Street* 에서 "category leader / fast grower" 식별 정량 임계 명시? 산업 점유율 격차 또는 매출 성장률 격차의 권장 임계? Mauboussin *Expectations Investing* 의 "competitive advantage period" 정량 측정법? 한국 KOSPI/KOSDAQ 사례 (NAVER 2010~2015 vs Daum / SK하이닉스 2017~2020 vs Micron) 매출 격차 분포?

**검증 후 액션**: 5%p → 적정값 (예: 3%p / 8%p / sector 상대 z-score) 정정.

---

### Q5. ATR Stop Multiplier 2.5 + R-multiple 50/30/20% 부분 익절 분포
**위치**: `api/config.py:273, 280-284` / memory `project_atr_dynamic_stop`, `project_r_multiple_exit`  
**현 가정**: ATR(14)×2.5 손절 = "월가 표준" / +1R 50% / +2R 30% / 트레일링 20%  
**문제**: 2.5x 는 다양한 임계 (Chandelier ATR×3 / Wilder ATR×2 / Tharp 2-3x) 중 하나. R-multiple 부분 익절 50/30/20% 도 자체 분배 — Linda Raschke 표준 인용 명시 X.

**Perplexity 질문**:
> ATR Stop Multiplier 권장값 학계/실무 (Wilder *New Concepts* 1978 / Chuck LeBeau Chandelier / Van Tharp *Trade Your Way to Financial Freedom*) 분포. 2.0 / 2.5 / 3.0 x 중 한국 KOSPI/KOSDAQ 1년 holding 기준 sharpe 최적값? R-multiple 부분 익절 50/30/20% 비율의 실증 근거 (Linda Raschke / Mark Minervini / Stan Weinstein 사례). 트레일링 stop ATR×N 권장.

**검증 후 액션**: 2.5 → 적정값 + ATR 4-cell sweep (5/22 큐) 결과와 종합. R-multiple 비율 조정.

---

## 🟡 MED 우선순위 (12건 — 분기 리뷰 시 검증)

### Brain 가중치 / 등급 (3건)

**Q6. Brain v5 fact:sentiment 7:3 비율 출처**
- `data/verity_constitution.json:396-418`
- 질문: fact:sentiment 가중치 학계 표준 (Fama-French 5-factor 비율 / Andrew Lo 행동재무 권장 분배)? 7:3 vs 6:4 vs 8:2 권장?

**Q7. VCI ±15 / ±25 임계 (Verity Contrarian Index)**
- `data/verity_constitution.json:126-127`
- 질문: contrarian indicator (Steve Cohen / Howard Marks / John Templeton) 정량 임계 분포. 자체 산식 valid 한가?

**Q8. 등급 임계 75-60-45-30 (STRONG_BUY/BUY/WATCH/CAUTION)**
- `data/verity_constitution.json:376-392`
- 질문: 종합 score 등급 cutoff 학계 권장 (analyst consensus rating threshold 분포)? 5등급 quintile 자연 cut (80/60/40/20) vs 현 75-60-45-30 차이.

### Ackman activist target 임계 (4건)

**Q9. Ackman PBR < 1.5 임계**
- `api/intelligence/veteran_triggers.py:143`
- 질문: Pershing Square 1차 진입 시점 target PBR 분포 (Wendy's 2005 / JCPenney 2010 / Herbalife 2012 / Valeant 2015 / ADP 2017 / Hilton 2016 / Chipotle 2016 / Howard Hughes 2010)?

**Q10. Ackman EV/EBITDA < 8 임계**
- `api/intelligence/veteran_triggers.py:147`
- 질문: 위 사례 EV/EBITDA 분포. 8 미만이 activist 진입 trigger 정량 임계인가?

**Q11. Ackman ROE < 8% / GPM > 30% 조합**
- `api/intelligence/veteran_triggers.py:159`
- 질문: "경영 비효율" 정량화 — 잠재 ROE vs 실현 ROE gap 측정. Pershing Square value-driver 분석법.

**Q12. Ackman 시총 KR 1000억 / US $500M 임계**
- `api/intelligence/veteran_triggers.py:172`
- 질문: activist 진입 target 사이즈 분포. Pershing Square / Carl Icahn / Elliott Management 평균 target 시총.

### Multi-bagger 신호 정량 (2건)

**Q13. 매출 가속 ≥ 15% 임계 (Mauboussin)**
- `api/analyzers/multi_bagger_signals.py:44`
- 질문: Mauboussin *Expectations Investing* (2001) / *More Than You Know* "sales growth" 정량 임계. 15% / 20% / 25% 중 권장.

**Q14. 영업 레버리지 OP/Rev > 3x 임계**
- `api/analyzers/multi_bagger_signals.py:67`
- 질문: Mauboussin "operating leverage" 임계 정량. 한국 KOSPI 사례 분포.

### 운영 임계 (3건)

**Q15. VAMS 통과 승률 55% 임계**
- `api/config.py:186`
- 질문: 시뮬레이션 → 운영 진입 승률 학계 권장 (Tharp / Schwager *Market Wizards* 인터뷰)? 55% / 60% 분기점.

**Q16. VAMS Max Factor Tilt 60% / Sector 35% 임계**
- `api/config.py:194, 200`
- 질문: 분산 한도 학계 (Markowitz / Black-Litterman) vs 실무 (Yale Endowment / Norway Pension) 단일 sector 최대 비중.

**Q17. Cohen 역발상 VCI ≥ 20 + fact ≥ 60**
- `api/intelligence/verity_brain.py:1499`
- 질문: Steve Cohen 1987 panic contrarian buy 정량 임계. fact-sentiment gap 어디서 진입? 20 / 25 / 30 분리 근거.

---

## 🟢 LOW 우선순위 (12건 — 6개월 검토 큐)

| 항목 | 위치 | 비고 |
|---|---|---|
| CAPE 버블 30 (Shiller) | verity_brain.py:477 | 강 출처 — 재검증 불필요 |
| ATR_MIN_PERIOD 20 | config.py:275 | 자체, 영향 작음 |
| Hard Floor 시총 100억 / 거래대금 1억 | config.py:251 | KRX 표준 확인 |
| KR Top N 10 / US Top N 15 | config.py:257-258 | 비용 감축 결정 |
| Ramp-up 500/1500/3000/5000 | config.py:289 | 14일 점진 |
| Timing Signal sentiment 0.7 / technical 0.3 | verity_brain.py:2736 | 자체 |
| DEDUPE 8h / CRITICAL 30분 | config.py:464-466 | UX 임계 |
| Quiet 23~7 KST | config.py:478-479 | 본인 수면 |
| 수수료 0.015% / KR 매도세 0.18% | config.py:155-156, 166 | 법규 표준 |
| Spread Slippage 5bp | config.py:173 | 실증 |
| 배당세 15.4% | config.py:174 | 법규 |
| Kelly Scale 0.5 | config.py:193 | Kelly 보수 |

---

## 검증 진행 방식

### Phase 1 — HIGH 5건 (즉시, 사용자 직접 Perplexity)
1. 위 Q1~Q5 copy-paste 로 Perplexity 1회씩 호출
2. 결과 → `docs/PERPLEXITY_VERIFICATION_RESULTS_v0.1.md` 누적 박힘
3. 임계값 정정 commit + memory 갱신

### Phase 2 — MED 12건 (1주 내, 묶음 호출 가능)
- Brain 가중치 3건 → 1회 Perplexity (학계 종합 비교)
- Ackman 4건 → 1회 (8 사례 일괄 분석)
- Multi-bagger 2건 → 1회 (Mauboussin 종합)
- 운영 3건 → 1회

### Phase 3 — LOW 12건 (분기 리뷰, 자동 IC 모니터링)
- 운영 데이터 누적 후 IC/ICIR 자동 검증으로 대체 가능

---

## 후속 action_queue 등록

각 HIGH 5건 + MED 4 묶음 = **9건 user action 큐잉** (Perplexity 호출은 사용자 직접 작업).
검증 후 결과 통합 commit 은 Claude 처리.

---

## 메모리 정합

- `feedback_perplexity_collaboration` — Perplexity 1순위 영역 (학계/실무 통계)
- `feedback_source_attribution_discipline` — 출처 명시 의무
- `feedback_real_call_over_llm_consensus` — 실호출 1회 > LLM 3자 합의
- `project_brain_v5_self_attribution` — 자체 결정 임계 명시
- `project_phase_2b_wide_scan` — 65 거래일 게이트 의제
- `project_multi_bagger_watch` — 5 신호 정량 큐

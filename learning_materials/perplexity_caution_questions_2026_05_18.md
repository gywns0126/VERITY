# Perplexity 6 자문 질문 — CAUTION 72 PM 결정 근거 (2026-05-18)

- 트리거: 5/18 새벽 cron_health CAUTION (score 72)
- 환경: CAPE 99%ile + USD-KRW 1497.76 (1500 임박) + VAMS 보유 0건 (5/17 reset, 0 거래일)
- 추천 모델: **Sonar Pro** (academic search mode 또는 deep research mode)
- 6개 batch 비용 ≈ $2.40 (자동 호출 시 — 사용자가 직접 답 가져옴)

---

## A — 헤지 결정 (concern #3)

### A1. CAPE 99%ile + 인버스 부분 헤지 historical 효과

CAPE Shiller P/E ratio 99th percentile 진입 시점부터 12-month forward의 KOSPI 200 inverse ETF 부분 헤지 (10% / 20% / 30% 비중) historical performance를 정량으로 답해줘.

요구사항:
- 1990-2025 historical episodes 기준 Sharpe ratio + max drawdown + win rate
- 한국 시장 인버스 ETF (KODEX 200선물인버스2X 252670 등) backtest 인용 가능하면 포함
- 비교군 4종: 100% 현금 (MMF/RP) / 100% KOSPI 200 long / 10% 헤지 / 20% 헤지 / 30% 헤지
- 학계 인용 (논문 title + 저자 + 연도) 또는 ETF 발행사 공식 backtest 데이터 명시

---

### A2. 인버스 ETF 부분 진입 비용 잠식률

한국 시드 ~$7,400 (1000만원) 개인투자자가 KODEX 200선물인버스2X (252670) 부분 진입 시 12개월 보유 시 비용 잠식률 정량 추정해줘.

비용 구성:
- expense ratio 0.64%/yr
- 매매수수료 ~0.015% (왕복)
- bid-ask spread + slippage
- 선물 롤오버 contango 비용
- negative compounding (volatility decay, leveraged ETF 특유)

요구사항:
- underlying KOSPI 200 inverse 수익률 대비 잠식률 % 추정
- 실제 252670 backtests 또는 ProShares SDS (-2x SPX) 같은 해외 사례 정량 데이터 인용
- volatility decay 산식 (예: -2x × σ²/2 daily) 명시

---

### A3. USD-KRW 1500 돌파 historical episodes

USD-KRW 환율 1500 돌파 historical episodes 각 직후 12개월간 KOSPI/USDKRW/외국인 매도 통계를 정리해줘.

Episodes (확인 + 누락 시 추가):
- 1997 IMF 외환위기
- 2008 글로벌 금융위기
- 2022 미국 긴축 강도
- 2024 트럼프 재선 후 (확인 필요)

각 episode별 요구사항:
- 1500 돌파 정확 일자
- 직후 12개월 KOSPI 지수 % change
- 직후 12개월 USD-KRW % change (정점/저점)
- 직후 12개월 외국인 KOSPI 순매도/매수 누적 금액 (조원)
- macro context (금리/유가/지정학 등)

마지막에: 2026년 현재 (1497.76, 1500 임박) 환경이 가장 유사한 historical episode 진단 + 차이점.

---

### A4. 시드 작은 개인의 optimal cash allocation 학계 권고

시드 작은 (~$10K = 1000만원) 개인투자자의 optimal cash allocation 학계 권고를 framework별로 정리해줘.

Framework별:
- Markowitz mean-variance optimization
- Kelly criterion (full Kelly / fractional Kelly)
- Merton portfolio problem (continuous-time)
- Behavioral finance (loss aversion, mental accounting, Prospect Theory)

조건:
- CAPE 99%ile + USD-KRW 1500 임박 = macro tail risk 환경의 dynamic asset allocation 권고
- 100% 현금 vs 부분 진입 (헤지 포함) 학계 컨센서스 존재 여부 — 또는 reasonable disagreement
- 거래 비용/세금이 작은 시드에 미치는 영향

논문 제목 + 저자 + 연도 인용 의무.

---

## B — Brain 룰 강화 (concern #1/2/4)

### B1. CAPE 99%ile 환경 고밸류 vs 저밸류 forward return

CAPE 99th percentile 환경에서 high-valuation 종목 (PER > 20 또는 PBR > 3) vs low-valuation 종목 (PER < 10, PBR < 1.0)의 forward 12-month return / max drawdown 정량 비교해줘.

요구사항:
- Fama-French value factor research 데이터
- Asness/AQR value strategy backtest (HML factor performance)
- Research Affiliates fundamental indexing 사례
- 한국 KOSPI/KOSDAQ에서의 같은 패턴 검증 (KCIF / KDI / 한국 academic 연구)
- "high valuation + high CAPE 결합 = forward drawdown 심화" 가설 검증 — factor decomposition
- 1980-2025 데이터 ideal, 한국은 1995-2025 가능 범위

논문 인용 의무 (저자/연도/journal).

---

### B2. Macro overlay + valuation screening 결합 quant strategy 사례

Macro overlay (CAPE percentile + currency strength + interest rate regime) + bottom-up valuation screening 결합 quant strategy 실무 사례 정리해줘.

대상 펀드/firm (가능한 만큼):
- AQR Capital Management
- Research Affiliates Smart Beta
- Bridgewater All Weather
- GMO Asset Allocation
- 한국 사례 (있다면) — 미래에셋 / 한투 / KCGI 등 quant fund

각 사례별 요구사항:
- macro filter 룰 (정확 임계값)
- 효과 정량 데이터 (IC improvement, Sharpe enhancement, drawdown reduction)
- backtest 기간 + universe
- live performance (있다면)

또한:
- binary cutoff (예: WATCH → AVOID 강등) vs continuous score adjustment 두 방식 backtest 우열
- macro filter 추가 시 turnover/transaction cost trade-off
- 1인 운용자 (~$10K seed) 가 모방 가능한 simplified version 권고

---

## 후속 처리 (사용자 답 가져온 후)

답 받으면 같은 폴더에 `perplexity_caution_answers_2026_05_18.md` 저장 권장 ([[reference_learning_materials_folder]] 정합).

PM 결정 (A1~A4 → 헤지 vs 현금 / B1~B2 → Brain 룰 변경 vs 유지) trail 메모리 박힘 후 시스템 적용.

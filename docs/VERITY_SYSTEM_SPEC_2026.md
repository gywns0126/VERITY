# VERITY 시스템 스펙북 v2 (Perplexity 온보딩용)

문서 버전: 2026-04  
대상: Perplexity Enterprise Pro (Sonnet 4.6) 컨텍스트 학습/기획 입력

## 목차

1. 시스템 정의  
2. 아키텍처 개요  
3. 실행 모드/스케줄  
4. 메인 파이프라인  
5. Verity Brain 판단 체계  
6. Constitution 스키마  
7. 수집기(collectors) 카탈로그  
8. 분석/인텔리전스/예측/퀀트  
9. VAMS(가상 매매)  
10. 텔레그램/운영 자동화  
11. 프론트엔드 컴포넌트 구조  
12. CI/CD 및 배포  
13. 환경변수 표준  
14. Perplexity 온보딩 프롬프트  
15. 분기 리서치 기획 템플릿

## 1) 시스템 정의

VERITY는 KR/US 주식 데이터 수집, 정량/정성 분석, AI 해석을 결합해 자동으로 투자 판단을 생성하고, 이를 `data/portfolio.json`으로 배포하는 시스템이다.

- 백엔드: Python (`api/`)
- 프론트엔드: Framer Code Components (`framer-components/`)
- 운영: GitHub Actions (`.github/workflows/`)
- 알림/제어: Telegram (`api/notifications/`)
- 핵심 산출물: `data/portfolio.json`

## 2) 아키텍처 개요

아키텍처 흐름:

```
외부 API/웹소스
  -> collectors
  -> analyzers + predictors + quant
  -> verity_brain
  -> gemini/claude
  -> portfolio.json 저장
  -> github push
  -> framer fetch + telegram 발송
```

핵심 코드 위치:

- 오케스트레이션: `api/main.py`
- 판단 엔진: `api/intelligence/verity_brain.py`
- AI 해석: `api/analyzers/gemini_analyst.py`, `api/analyzers/claude_analyst.py`
- 저장: `api/vams/engine.py`

## 3) 실행 모드/스케줄

### 실시간/일일 모드
- `realtime`: KR 장중 경량
- `quick`: 장외 중간 분석
- `full`: KR 장마감 풀 분석
- `realtime_us`: US 장중
- `full_us`: US 장마감

### 정기 모드
- `periodic_weekly`
- `periodic_monthly`
- `periodic_quarterly`
- `periodic_semi`
- `periodic_annual`

스케줄 원천: `.github/workflows/daily_analysis.yml`

## 4) 메인 파이프라인 (`api/main.py`)

1. 모드 결정 + 헬스체크
2. 시장/매크로/뉴스/이벤트 수집
3. 후보 필터링 (`stock_filter`)
4. 기술/컨센/수급/멀티팩터 계산
5. 예측(XGB)/백테스트/타이밍
6. Verity Brain 적용
7. Gemini 분석 (실패 시 폴백)
8. 선택적 Claude 병합
9. VAMS/브리핑/알림 생성
10. `portfolio.json` 저장 및 배포

## 5) Verity Brain 판단 체계

공식:

`brain_score = fact_score * 0.7 + sentiment_score * 0.3 + vci_bonus`

등급:

- `STRONG_BUY` >= 75
- `BUY` >= 60
- `WATCH` >= 45
- `CAUTION` >= 30
- `AVOID` < 30

주요 특징:

- 레드플래그 조건에 의한 강등/회피
- 매크로 오버라이드(`panic_stages`, `economic_quadrant`)
- VCI 역발상 보정

## 6) Constitution 스키마 (`data/verity_constitution.json`)

핵심 섹션:

- `fact_score.weights`
- `quant_factors.factors` / `quant_factors.regime_weights`
- `sentiment_score.weights`
- `vci.thresholds`
- `hedge_fund_principles`
- `panic_stages`
- `economic_quadrant`
- `position_sizing`
- `decision_tree`
- `red_flags`
- `macro_override`
- `gemini_system_instruction`

해당 파일은 Brain 정책의 SSOT이며, 분기 업데이트 대상이다.

## 7) collectors 카탈로그 (`api/collectors/`)

### 시장/가격
- `stock_data.py`, `krx_openapi.py`, `market_flow.py`, `us_flow.py`

### 매크로
- `macro_data.py`, `fred_macro.py`, `ecos_macro.py`, `crypto_macro.py`

### 뉴스/감성
- `news_headlines.py`, `news_sentiment.py`, `newsapi_client.py`, `x_sentiment.py`, `reddit_sentiment.py`, `naver_community.py`, `RSSScout.py`

### 공시/기업
- `DartScout.py`, `sec_edgar.py`, `ConsensusScout.py`, `group_structure.py`, `ChainScout.py`

### 무역/특수
- `customs_trade_stats.py`, `SpecialScout.py`, `CommodityScout.py`, `global_events.py`, `earnings_calendar.py`, `sector_analysis.py`, `us_sector.py`

## 8) 분석/인텔리전스/예측/퀀트

### analyzers (`api/analyzers/`)
- `stock_filter.py`, `technical.py`, `consensus_score.py`, `multi_factor.py`, `sector_rotation.py`, `safe_picks.py`
- `gemini_analyst.py`: 종목/일일/정기 AI 리포트
- `claude_analyst.py`: 반론/합의/검증

### intelligence (`api/intelligence/`)
- `verity_brain.py`: 종합 판단
- `alert_engine.py`: 알림
- `periodic_report.py`: 기간 통계
- `strategy_evolver.py`: 전략 진화
- `tail_risk_digest.py`: 꼬리위험
- `postmortem.py`, `ai_leaderboard.py`, `backtest_archive.py`, `value_hunter.py`, `chat_engine.py`

### predictors/quant
- 예측: `api/predictors/xgb_predictor.py`
- 타이밍: `api/predictors/timing_signal.py`
- 백테스트: `api/predictors/backtester.py`
- 퀀트 팩터: `api/quant/factors/*`
- IC/Decay: `api/quant/alpha/*`
- 페어: `api/quant/pairs/*`

## 9) VAMS (`api/vams/engine.py`)

- 가상 계좌/보유 관리
- 신규 매수 조건: `recommendation == BUY`, `safety_score` 조건, 리스크키워드 제한
- 손절/트레일링/보유기간 청산
- 손익/거래통계 갱신
- 저장 시 NaN/Infinity sanitize

## 10) 텔레그램/운영 자동화

### 발송
- 일일 리포트
- 모닝 브리핑
- 위험 알림
- 전략 제안(승인/거절)

### 수신 명령
- `/approve_strategy`
- `/reject_strategy`
- `/rollback_strategy`
- `/strategy_status`

핵심 파일:
- `api/notifications/telegram.py`
- `api/notifications/telegram_bot.py`
- `api/notifications/telegram_dedupe.py`

## 11) 프론트엔드 컴포넌트 구조

핵심:
- `StockDashboard.tsx`
- `StockDetailPanel.tsx`
- `TradingPanel.tsx`
- `VerityReport.tsx`
- `VerityBrainPanel.tsx`
- `GlobalMarketsPanel.tsx`
- `MacroPanel.tsx`

US 전용:
- `USFlowPanel.tsx`, `USInsiderFeed.tsx`, `USAnalystView.tsx`, `USEarningsCalendar.tsx`, `USEconCalendar.tsx`, `USSectorMap.tsx`

데이터 패턴:
- 대부분 `portfolio.json` fetch
- 공통 키: `recommendations`, `macro`, `headlines`, `sectors`, `verity_brain`, `*_report`

## 12) CI/CD 및 배포

워크플로:
- `.github/workflows/daily_analysis.yml`
- `.github/workflows/export_trade_daily.yml`
- `.github/workflows/rss_scout.yml`

배포 방식:
1. Actions에서 `api/main.py` 실행
2. `data/` 산출물 커밋/푸시
3. Framer가 GitHub raw URL에서 최신 JSON fetch

## 13) 환경변수 표준

AI:
- `GEMINI_API_KEY`, `GEMINI_MODEL`, `ANTHROPIC_API_KEY`

데이터:
- `DART_API_KEY`, `FRED_API_KEY`, `ECOS_API_KEY`, `PUBLIC_DATA_API_KEY`, `KRX_API_KEY`
- `FINNHUB_API_KEY`, `POLYGON_API_KEY`, `NEWS_API_KEY`, `SEC_EDGAR_USER_AGENT`

운영:
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ALLOWED_CHAT_IDS`
- `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`

## 14) Perplexity 온보딩 프롬프트 (복붙용)

아래 프롬프트를 Perplexity Sonnet 4.6의 "프로젝트 초기 컨텍스트"로 사용:

```
너는 VERITY 시스템의 수석 설계 리뷰어다.

[목표]
- 이 시스템은 KR/US 주식 자동 분석 엔진이다.
- 핵심 출력은 data/portfolio.json이다.
- Brain 정책은 data/verity_constitution.json이 SSOT다.

[분석 범위]
1) api/main.py의 모드별 파이프라인
2) verity_brain.py의 스코어링/레드플래그
3) gemini_analyst.py + claude_analyst.py 역할 분리
4) periodic_report.py + strategy_evolver.py의 주기학습 구조
5) 프론트 컴포넌트가 portfolio.json을 어떻게 소비하는지

[출력 요구]
- 반드시 "아키텍처 요약 -> 리스크 -> 개선안 -> 실행 단계" 순서로 작성
- 개선안은 바로 구현 가능한 파일 단위 액션 아이템으로 제시
- 각 제안은 기대효과/리스크/롤백전략 포함
- 추측은 금지하고, 불확실하면 "추가 코드 확인 필요"로 표기
```

## 15) 분기 리서치 기획 템플릿 (Perplexity용)

```
[요청]
분기 리서치 보고서를 생성하라.
주제: 퀀트 + 헤지펀드 + 롱/숏 + 매크로 레짐

[입력 컨텍스트]
- 현행 constitution: fact/sentiment/vci/red_flags/position_sizing
- 최근 90일 성과: hit_rate, sharpe, max_drawdown
- 최근 실패 패턴: postmortem lesson

[반드시 포함할 산출물]
1) 유지할 원칙 5개
2) 수정 제안 5개 (각 항목은 변경 이유와 수치 근거)
3) constitution 반영 가능한 JSON 패치 초안
4) 위험 시나리오 3개와 대응 규칙
5) 다음 분기 검증 KPI

[형식]
- 한국어
- 표 중심
- 마지막에 "즉시 적용 / 검증 후 적용 / 보류" 3단계 분류
```

## 16) 현재 확장 과제

목표:
- 기존 Gemini API 호출은 유지
- 분기 딥리서치만 Perplexity API로 도입
- 결과를 Constitution/Brain 학습 루프에 연결

추천 구현 축:
- 신규 `api/intelligence/quarterly_research.py`
- `api/main.py`의 `periodic_quarterly` 경로 연동
- `data/research_archive/`에 근거/요약 저장
- `strategy_evolver.py` 검증 패턴 재사용


# VERITY 시스템 전체 스펙북 v3.5

문서 버전: 2026-04-30
시스템 버전: v8.7.0 (Sprint 11: 자가진단 검수 + 베테랑 due diligence 7개 결함 1/6/2/3/4 대응 + gh-pages dual-write 인프라)
대상: Perplexity Enterprise Pro / Claude Sonnet 4.6 컨텍스트 학습 / 기획 입력
GitHub: gywns0126/VERITY


## 목차

1. 시스템 정의 및 기술 스택
2. 프로젝트 디렉토리 구조
3. 아키텍처 개요
4. 실행 모드 및 스케줄
5. 메인 파이프라인 상세 (api/main.py)
6. 수집기(Collectors) 카탈로그
7. 분석기(Analyzers) 상세
8. 인텔리전스(Intelligence) 엔진
9. 예측기(Predictors) 및 퀀트(Quant) 팩터
10. Verity Brain v5.0 판단 체계
11. Constitution 스키마
12. VAMS 가상 매매 시스템
13. Safety Layer (v8.2)
14. 텔레그램 알림 및 봇 명령
15. portfolio.json 데이터 스키마
16. Framer 프론트엔드 컴포넌트
17. Vercel Serverless API
18. KIS 실시간 중계 서버
19. Supabase 데이터 계층
20. CI/CD 및 GitHub Actions
21. PDF 리포트 시스템
22. 환경변수 완전 표
23. 외부 API 의존성 목록
24. Perplexity 온보딩 프롬프트
25. 분기 리서치 기획 템플릿
26. 개발·테스트 자산 (mocks / tracing / tests)


## 1) 시스템 정의 및 기술 스택

VERITY(Verified Equity Research & Investment Technology Yield)는 한국(KR) 및 미국(US) 주식 시장의 데이터를 24시간 자동 수집, 정량/정성 분석, AI 해석을 결합하여 투자 판단을 생성하고, 이를 data/portfolio.json으로 배포하는 종합 AI 자산 분석 시스템이다.

핵심 산출물: data/portfolio.json (GitHub Pages 호스팅, 최대 15분 주기 갱신)

### 기술 스택

백엔드:
- 언어: Python 3.9+ (로컬·워크스페이스 최소). GitHub Actions 러너는 3.11 고정
- 주요 라이브러리: pykrx(>=1.0.45), yfinance(>=1.2.0), pandas(>=2.0), numpy(>=1.24), xgboost(>=2.0), scikit-learn(>=1.3)
- AI: google-genai(>=1.0, Gemini 2.5 Flash), anthropic(>=0.40, Claude Sonnet), Perplexity API(sonar-pro)
- 공시: dart-fss(>=0.4.3)
- 기타: feedparser, beautifulsoup4, python-telegram-bot(>=21.0), fpdf2(>=2.8), exchange_calendars, fear_and_greed, cot_reports

프론트엔드:
- Framer Code Components (React + TypeScript)
- 인라인 스타일 (CSS 모듈/Tailwind 미사용)
- 디자인: 배경 #000, 카드 #111, 보더 #222, 액센트 네온그린 #B5FF19
- 폰트: 'Inter', 'Pretendard', -apple-system, sans-serif

실시간 서버:
- FastAPI + SSE (Server-Sent Events)
- KIS Open API WebSocket 중계
- Railway $5 플랜 배포

Serverless API:
- Vercel Serverless Functions (Node.js/Python)
- 종목 검색, 차트, 채팅, 주문, 관심종목 관리

데이터베이스:
- Supabase (PostgreSQL + Auth) - 관심종목 그룹, 유저 프로필/홀딩스/알림설정, RLS 보안

CI/CD:
- GitHub Actions (4개 워크플로)
- GitHub Pages (data/ 디렉토리 정적 호스팅)


## 2) 프로젝트 디렉토리 구조

```
VERITY/
  api/
    main.py                       <- 메인 파이프라인 오케스트레이터 (~3150줄)
    config.py                     <- 전역 설정, 환경변수 파싱 (~350줄)
    health.py                     <- 시스템 자가진단 (API heartbeat, 데이터 신선도, 버전 동기화)
    __init__.py
    collectors/                   <- 데이터 수집기 (48개 파일)
      stock_data.py               <- pykrx 주가/수급 수집
      krx_openapi.py              <- KRX Open API 공식 데이터
      macro_data.py               <- 매크로 지표 (VIX, 환율, 금리)
      fred_macro.py               <- FRED API (미국 경제지표)
      ecos_macro.py               <- 한국은행 ECOS API
      market_flow.py              <- 투자자 수급 (외인/기관/개인)
      us_flow.py                  <- 미국 자금 흐름
      news_headlines.py           <- 뉴스 헤드라인 수집
      news_sentiment.py           <- 뉴스 감성 분석
      newsapi_client.py           <- NewsAPI 연동
      x_sentiment.py              <- X(Twitter) 감성
      reddit_sentiment.py         <- Reddit 감성
      naver_community.py          <- 네이버 커뮤니티 감성
      RSSScout.py                 <- RSS 피드 스카우트
      DartScout.py                <- DART 공시 수집
      sec_edgar.py                <- SEC EDGAR (미국 공시)
      sec_13f_collector.py        <- SEC 13F (기관 보유현황)
      ConsensusScout.py           <- 컨센서스(목표가) 수집
      ChainScout.py               <- 밸류체인 탐색
      CommodityScout.py           <- 원자재-종목 연관도
      SpecialScout.py             <- 특수 이벤트 스카우트
      group_structure.py          <- 기업집단 구조
      global_events.py            <- 글로벌 이벤트 캘린더
      earnings_calendar.py        <- 실적 발표 일정
      sector_analysis.py          <- 섹터 분석
      us_sector.py                <- 미국 섹터 데이터
      yieldcurve.py               <- 수익률 곡선 데이터
      etfdata.py                  <- KR ETF 요약
      etfus.py                    <- US ETF/채권 ETF 요약
      bonddata.py                 <- 채권 데이터
      bondus.py                   <- 미국 채권 데이터
      crypto_macro.py             <- 크립토 매크로 센서
      market_fear_greed.py        <- CNN Fear & Greed 지수
      cboe_options_collector.py   <- CBOE 풋/콜 비율
      cftc_cot.py                 <- CFTC COT 리포트 (기관 포지셔닝)
      fund_flow.py                <- 펀드 플로우 (EPFR 프록시)
      expiry_calendar.py          <- 파생상품 만기 일정
      finnhub_client.py           <- Finnhub API (미국 종목)
      polygon_client.py           <- Polygon API (미국 시장)
      program_trading_collector.py <- 프로그램 매매 데이터
      trading_value_scanner.py    <- 거래대금 스캐너
      customs_trade_stats.py      <- 관세청 수출입 통계
      dart_corp_code.py           <- DART 기업코드 매핑
      sentiment_engine.py         <- 소셜 감성 통합 엔진
      alt_data_collectors.py      <- 대안 데이터 (QuiverQuant/French/EIA/SOV, UI·아카이브 전용)
      niche_intel.py              <- 틈새 인텔 조립 (trends/legal/credit, macro.niche_credit 파생)
    analyzers/                    <- 분석 엔진 (16개 파일)
      stock_filter.py             <- 3단계 깔때기 필터링
      technical.py                <- 기술적 분석 (RSI, MACD, BB)
      multi_factor.py             <- 멀티팩터 점수
      consensus_score.py          <- 컨센서스 스코어
      sector_rotation.py          <- 섹터 로테이션
      safe_picks.py               <- 안심 추천 생성
      gemini_analyst.py           <- Gemini AI 종합/일일/정기 분석
      claude_analyst.py           <- Claude 심층/반론/검증/병합
      commodity_narrator.py       <- 원자재 영향 서술
      macro_adjustments.py        <- 매크로 기반 패널티
      value_chain_trade.py        <- 밸류체인-무역 오버레이
      bondanalyzer.py             <- 채권 분석
      etfscreener.py              <- ETF 스크리너
      export_hscode_mapper.py     <- HS코드-종목 매핑
      yieldcurveanalyzer.py       <- 수익률 곡선 분석
    intelligence/                 <- AI 판단/학습 엔진 (12개 파일)
      verity_brain.py             <- 종합 판단 엔진 v5.0 (~2200줄)
      alert_engine.py             <- 능동 알림 엔진 (3단계: CRITICAL/WARNING/INFO)
      chat_engine.py              <- Gemini 대화 엔진
      periodic_report.py          <- 정기 리포트 (주간/월간/분기/반기/연간)
      strategy_evolver.py         <- 전략 진화 엔진 (Claude 기반 가중치 최적화)
      tail_risk_digest.py         <- 꼬리위험 감지 (전쟁/재난/쇼크)
      postmortem.py               <- AI 오심 포스트모텀 (실패 분석)
      ai_leaderboard.py           <- LLM 소스별 성과 리더보드
      backtest_archive.py         <- 추천 백테스트 (7/14/30일 추적)
      value_hunter.py             <- 저평가 발굴 엔진
      perplexity_realtime.py      <- Perplexity 실시간 리서치
      quarterly_research.py       <- Perplexity 분기 딥리서치
    predictors/                   <- ML 예측 모듈
      xgb_predictor.py            <- XGBoost 주가 예측
      backtester.py               <- 전략 백테스트
      timing_signal.py            <- 매수/매도 타이밍 시그널
    quant/                        <- 퀀트 팩터 시스템
      factors/
        momentum.py               <- 모멘텀 팩터
        quality.py                <- 퀄리티 팩터
        volatility.py             <- 변동성 팩터
        mean_reversion.py         <- 평균회귀 팩터
      alpha/
        alpha_scanner.py          <- 알파 스캐너
        factor_decay.py           <- 팩터 디케이/IC 분석
      pairs/
        pair_scanner.py           <- 페어 트레이딩 스캐너
        cointegration.py          <- 공적분 분석
    vams/
      engine.py                   <- 가상 투자 엔진 (매수/매도/손절/통계)
    trading/
      kis_broker.py               <- 한국투자증권 실거래 브로커
      auto_trader.py              <- 추천+타이밍 → KIS 주문 계획/실행 (드라이런·한도·킬스위치)
      mock_kis_broker.py          <- KIS 브로커 목 (로컬/테스트)
    notifications/
      telegram.py                 <- 텔레그램 발송 (리포트/알림/브리핑)
      telegram_bot.py             <- 텔레그램 봇 명령 처리
      telegram_dedupe.py          <- 알림 중복 제거
      timing_signal_watcher.py    <- timing.action 전환 감지 → 텔레그램
    mocks/                        <- VERITY_MODE mock 픽스처·리플레이
    tracing/
      run_tracer.py               <- 실행 트레이싱
    reports/
      pdf_generator.py            <- PDF 리포트 생성기 (~1000줄, fpdf2)
      fonts/                      <- NanumGothic 한글 폰트
    workflows/
      archiver.py                 <- 일일 스냅샷 저장/로드/정리
      export_trade_pipeline.py    <- 수출 무역 파이프라인
    clients/
      perplexity_client.py        <- Perplexity API 클라이언트
    utils/
      safe_collect.py             <- 안전 수집 래퍼 (예외 캡슐화)
      portfolio_writer.py         <- portfolio.json 섹션 읽기/쓰기
  framer-components/              <- Framer Code Components (49개 TSX + 유틸)
  data/                           <- 산출물 저장소 (Git 추적, GitHub Pages 호스팅)
    portfolio.json                <- 메인 산출물
    recommendations.json          <- 추천 종목 별도 파일
    raw_data.json                 <- 원시 수집 데이터
    history.json                  <- VAMS 매매 이력
    backtest_stats.json           <- 백테스트 통계
    verity_constitution.json      <- Brain 판단 정책 (SSOT)
    brain_knowledge_base.json     <- Brain v5 학습 기반
    strategy_registry.json        <- 전략 진화 레지스트리
    consensus_data.json           <- 컨센서스 원본
    trade_analysis.json           <- 무역 분석 결과
    group_structure.json          <- 기업집단 구조
    verity_report_daily.pdf       <- 일일 PDF 리포트
    verity_report_weekly.pdf      <- 주간 PDF 리포트
    auto_trade_history.json       <- 자동매매 실행 이력 (선택)
    .auto_trade_paused             <- 자동매매 킬스위치 파일 (존재 시 중단)
    .timing_state.json            <- 타이밍 알림 워처 상태 (gitignore 권장)
    history/                      <- 일일 스냅샷 아카이브 (YYYY-MM-DD.json: 당일 최종본, 400일 보관)
      runs/                       <- 실행별 감사 스냅샷 (YYYY-MM-DD_HHMM_{mode}.json, 90일 보관)
    research_archive/             <- 분기 리서치 아카이브
  vercel-api/                     <- Vercel Serverless Functions
    api/
      search.py                   <- 종목 검색
      stock.py                    <- 종목 요약
      stock_detail.py             <- 종목 상세
      chart.py                    <- 차트 데이터
      chat.py                     <- AI 채팅
      order.py                    <- 주문 API
      watchgroups.py              <- 관심종목 그룹 CRUD
      supabase_client.py          <- Supabase 연결
      unlisted_exposure.py        <- 비상장 노출 체크
    vercel.json                   <- Vercel 설정
    package.json
  server/                         <- KIS 실시간 중계 서버
    main.py                       <- FastAPI + SSE 엔트리포인트
    config.py                     <- 서버 설정
    kis_rest_client.py            <- KIS REST 클라이언트
    kis_ws_client.py              <- KIS WebSocket 클라이언트
    models.py                     <- 데이터 모델
    Dockerfile                    <- Railway 배포용
  supabase/
    migrations/                   <- DB 마이그레이션
      001_watch_groups.sql
      002_watch_groups_rls_harden.sql
      003_auth_profiles.sql       <- Auth 프로필 + user_holdings + user_alert_prefs + watch_groups auth 전환
  scripts/
    generate_spec_pdf.py          <- 이 스펙 문서 -> PDF 변환
    simulate_auto_trade.py        <- 자동매매 시뮬레이션 스크립트
  tests/
    __init__.py
    conftest.py
    test_auto_trader.py
    test_timing_watcher.py
  .github/workflows/
    daily_analysis.yml            <- 메인 분석 파이프라인 (24시간 가동)
    bond_etf_analysis.yml         <- 채권/ETF 분석 (1일 2회)
    export_trade_daily.yml        <- 수출 무역 파이프라인 (1일 1회)
    rss_scout.yml                 <- RSS 뉴스 스카우트 (장중 15분/장외 30분)
  docs/
    KRX_OPEN_API_SETUP.md
    US_STOCK_SCHEMA.md
    VERITY_MODE.md                <- VERITY_MODE(dev/staging/prod) mock·실호출 분기
    SUPABASE_AUTH_SETUP.md        <- Supabase Auth + 프로필/RLS + Framer 연동 가이드
    VERITY_SYSTEM_SPEC_2026.md    <- 이 문서
  .env.example                    <- 환경변수 샘플 (민감값 없음)
```


## 3) 아키텍처 개요

### 데이터 흐름

```
[외부 데이터 소스]
  pykrx, yfinance, FRED, ECOS, DART, SEC EDGAR,
  Finnhub, Polygon, NewsAPI, X, Reddit, Naver,
  KRX Open API, 관세청, CBOE, CFTC, CNN FnG,
  Perplexity, CoinGecko(Binance)
       |
       v
[collectors/ — 48개 수집기]
       |
       v
[analyzers/ — 필터링+기술+멀티팩터+컨센서스+섹터]
  stock_filter (3단계 깔때기)
  -> technical (RSI/MACD/BB)
  -> multi_factor (4팩터 통합점수)
  -> consensus_score (목표가 괴리)
  -> sector_rotation (섹터 순환)
       |
       v
[predictors/ — ML 예측]
  xgb_predictor -> backtester -> timing_signal
       |
       v
[intelligence/verity_brain.py — 종합 판단 엔진 v5.0]
  brain_score = fact*0.7 + sentiment*0.3 + VCI + candle
  -> 등급: STRONG_BUY / BUY / WATCH / CAUTION / AVOID
       |
       v
[gemini_analyst + claude_analyst — Dual AI 해석]
  Gemini: 1차 분석(종목/일일/정기 리포트)
  Claude: 심층 반론/합의/병합 (STRONG_BUY 상위 N개)
       |
       v
[VAMS — 가상 매매 시뮬레이션]
  매수/매도/손절/통계 갱신
       |
       v
[portfolio.json 저장]
  -> git commit & push (GitHub Actions)
  -> GitHub Pages 정적 호스팅
       |
       +---> [Framer Components] portfolio.json fetch -> UI 렌더
       +---> [Telegram Bot] 일일 리포트/모닝 브리핑/긴급 알림
       +---> [Vercel API] 실시간 검색/상세/채팅/주문
       +---> [KIS 서버] 실시간 호가/체결 SSE 중계
```

### 핵심 원칙
- Serverless-First: 상시 서버 없이 GitHub Actions 크론으로 전체 파이프라인 구동
- Single Source of Truth: portfolio.json이 유일한 산출물. 프론트/텔레그램/PDF 모두 이 파일 소비
- Dual AI: Gemini(1차 분석) + Claude(반론/검증) 교차 확인
- Fail-Safe: Deadman Switch + Cross-Verification + 예외 캡슐화
- Self-Evolving: Strategy Evolver가 constitution 가중치를 자동 제안/검증/적용


## 4) 실행 모드 및 스케줄

### 모드 정의

realtime (KST 09:00~15:30, ~1분):
- 가격, 환율, 지수, 수급, 뉴스, X 감성
- 포트폴리오/매크로/꼬리위험 업데이트
- 5~15분 간격 실행

realtime_us (US 장중, ~1분):
- Polygon/Finnhub 미국 시장 데이터
- 15~30분 간격 실행

quick (장외 시간, ~3분):
- realtime + 기술적 분석 + 멀티팩터 + XGBoost 예측
- 매시 정각 실행

full (KST 16:00, ~7분):
- quick + Gemini AI 풀분석 + Claude 심층 + 백테스트
- 재무 분석, VAMS 시뮬레이션, 텔레그램 일일 리포트
- 포스트모텀, 전략 진화, PDF 생성
- 평일 1회 실행

full_us (KST 06:30, ~5분):
- Finnhub(60req/min) + SEC(10req/s) + Polygon(5req/min) 순차
- 미국 장마감 풀분석
- 화~토 1회 실행

periodic_weekly (토요일 KST 09:00):
- 7일 누적 성과 복기 + 메타 분석
- Gemini 주간 리포트

periodic_monthly (매월 1일 KST 09:00):
- 30일 누적 분석

periodic_quarterly (1/4/7/10월 2일 KST 10:00):
- 90일 분석 + Perplexity 딥리서치
- 13F 기관 투자자 포지션 수집 + institutional signal 계산 (portfolio.institutional_13f)
- Constitution 패치 제안

periodic_semi (1/7월 3일 KST 10:00):
- 180일 반기 분석

periodic_annual (1월 4일 KST 10:00):
- 365일 연간 종합 리포트

### GitHub Actions 스케줄 상세

daily_analysis.yml 크론 엔트리 (30개+):
- 개장 전 KST 08:30~08:55: 5분 간격 (realtime)
- 개장 러시 KST 09:00~09:25: 5분 간격 (realtime)
- 장중 안정 KST 09:30~09:45: 15분 간격 (realtime)
- 장중 본장 KST 10:00~14:45: 15분 간격 (realtime)
- 종가 러시 KST 15:00~15:40: 5분 간격 (realtime)
- 마감 직후 KST 15:45~15:55: 5분 간격 (realtime)
- 장마감 풀분석 KST 16:00: full 1회
- 장외 매시 정각: quick (UTC 08~23)
- 야간 경량 KST: 10분 간격 realtime (포트/매크로/꼬리위험)
- 미장 프리마켓 KST 22:00: realtime_us
- 미장 개장 후 KST 23:30: realtime_us
- 미장 장중 30분 간격: realtime_us
- 미장 종가 러시 15분 간격: realtime_us
- 미장 마감 KST 06:30: full_us
- 주간/월간/분기/반기/연간 정기 리포트 별도 크론

Concurrency: daily-analysis 그룹, cancel-in-progress: true
Runner: ubuntu-latest, timeout: 90분

### VERITY_MODE (개발·스테이징·비용 분기)

- 환경변수 `VERITY_MODE`: `dev`(기본) / `staging` / `prod`. AI API(Gemini/Claude/Perplexity) 및 유료 수집기(Finnhub/Polygon/NewsAPI 등) 호출을 mock/실호출로 분기한다.
- `GITHUB_ACTIONS=true` 인 CI에서는 **항상 prod**로 간주되어 mock 배포 사고를 방지한다.
- 상세 키 목록·실행 예시: `docs/VERITY_MODE.md`


## 5) 메인 파이프라인 상세 (api/main.py)

총 ~3150줄. 모드에 따라 실행 단계가 분기된다.

### 1단계: 모드 결정 + 헬스체크
- ANALYSIS_MODE 환경변수 또는 시각 기반 자동 결정
- run_health_check(): API heartbeat (DART, FRED, Telegram, Gemini, Anthropic 등)
- validate_deadman_switch(): 실패 소스 3개 이상이면 분석 중단 + 긴급 알림

### 2단계: 시장/매크로 수집
- get_market_index(): KOSPI, KOSDAQ, S&P500, NASDAQ 지수
- get_macro_indicators(): VIX, 원/달러 환율, 금리 등
- KRX OpenAPI: collect_krx_openapi_snapshot()/collect_krx_tiers()로 수집 후 _slim_krx()로 상세 endpoint rows 제거. portfolio.json에는 summary + 메타(bas_dd, tier_plan, tier_updated_at)만 저장
- 채권 수집: collect_bonds()후 run_bond_analysis()로 bond_regime 산출 → bonds.bond_regime으로 동기화
- collect_headlines(): 한국 뉴스 헤드라인
- collect_bloomberg_google_news_rss(): 블룸버그/구글 뉴스 RSS
- collect_us_headlines(): 미국 뉴스 헤드라인
- collect_global_events(): 글로벌 이벤트 캘린더
- collect_x_sentiment(): X 감성 수집
- collect_market_fear_greed(): CNN Fear & Greed 지수
- get_full_yield_curve_data(): 수익률 곡선
- collect_crypto_macro(): 크립토 매크로 센서

### 3단계: 후보 필터링
- run_filter_pipeline(): 3단계 깔때기
  - 1차: 거래대금 10억원(KR) / $50M(US) 이상
  - 2차: 부채비율 100% 이하
  - 3차: 상위 30종목 선정
- _fetch_watch_tickers(): Supabase 관심종목 병합

### 4단계: 기술 분석 + 멀티팩터
- analyze_technical(): RSI, MACD, 볼린저밴드, 이동평균선
- compute_multi_factor_score(): 모멘텀/퀄리티/변동성/평균회귀 통합
- compute_timing_signal(): 매수/매도 타이밍
- scout_consensus(): 목표가 컨센서스 수집
- build_consensus_block(): 컨센서스 스코어 산출
- attach_commodity_to_stocks(): 원자재 영향도 부착
- attach_value_chain_trade_overlay(): 밸류체인-무역 오버레이

### 5단계: 퀀트 팩터 + ML 예측
- compute_momentum_score(): 모멘텀 팩터
- compute_quality_score(): 퀄리티 팩터
- compute_volatility_score(): 변동성 팩터
- compute_mean_reversion_score(): 평균회귀 팩터
- predict_stock(): XGBoost 5일 후 방향 예측
- backtest_stock(): 전략 백테스트

### 6단계: Verity Brain
- verity_brain_analyze(): 종합 판단 (별도 섹션에서 상세 설명)
- Graham Value / CANSLIM / Candle Psychology / Bubble Detection
- V6: 13F 기관 스마트머니 보너스 (US 종목 한정, 분기 수집 후)
- V5.3: CBOE PCR 오버라이드 (VCI 보정 + 패닉 등급 캡)

### 7단계: Gemini 분석 (full 모드)
- analyze_batch(): 종목별 AI 분석 (추천/리스크/한줄평)
- generate_daily_report(): 일일 종합 리포트
- generate_periodic_report(): 정기 리포트 (주간~연간)
- enrich_commodity_impact_narratives(): 원자재 영향 서술

### 8단계: Claude 병합 (full 모드, 선택적)
- analyze_batch_deep(): Brain STRONG_BUY/BUY 상위 N개 심층 분석
- analyze_batch_light(): quick 모드 경량 분석
- merge_dual_analysis(): Gemini+Claude 합의/분쟁 병합
- check_brain_drift(): Brain 드리프트 감지
- analyze_stock_emergency(): 급등락 종목 긴급 분석

### 9단계: VAMS + 알림
- run_vams_cycle(): 매수/매도/손절 시뮬레이션
- generate_briefing(): 능동 알림 생성
- send_daily_report(): 텔레그램 일일 리포트
- send_morning_briefing(): 모닝 브리핑 (KST 08:00)
- maybe_send_tail_risk_digest(): 꼬리위험 감지 시 즉시 발송

### 10단계: 저장 + 배포
- save_portfolio(): NaN/Infinity sanitize 후 portfolio.json 저장
- archive_daily_snapshot(): data/history/ 에 스냅샷 보관
- generate_all_reports(): PDF 리포트 생성
- Git commit & push (GitHub Actions에서 자동)
- STEP 10.55 alt_data(QuiverQuant/French/EIA/SOV): UI·아카이브 전용. 추천/브레인 점수에 직접 반영되지 않음
- verification_report(IC/ICIR + 추천 성과): 사후 검증용 아카이브. 실시간 판단에 역류하지 않음


## 6) 수집기(Collectors) 카탈로그

### 시장/가격 데이터
- stock_data.py: pykrx로 KOSPI/KOSDAQ 종가, 거래량, 거래대금, 수급 데이터 수집. yfinance로 미국 종목 가격. get_market_index(), get_equity_last_price(), get_stock_data() 함수 제공
- krx_openapi.py: KRX Data Marketplace 공식 API. 종목 스냅샷, 시장경보(정리매매/관리종목/투자경고), 3개 Tier 병렬 수집. collect_krx_openapi_snapshot(), collect_krx_tiers()
- market_flow.py: 외국인/기관/개인 투자자 수급 흐름. get_investor_flow()
- us_flow.py: 미국 시장 자금 흐름. compute_us_flow()
- trading_value_scanner.py: 거래대금 급증 종목 스캐너
- program_trading_collector.py: 프로그램 매매 데이터. get_program_trading_today()

### 매크로 지표
- macro_data.py: VIX, 원/달러 환율, 금리, 유가 등 핵심 매크로. get_macro_indicators()
- fred_macro.py: FRED API - 미국 10년물 금리(DGS10), CPI, 실업률. DGS10 >= 4.5% 시 방어 모드
- ecos_macro.py: 한국은행 ECOS - 기준금리, 소비자물가, M2 통화량
- crypto_macro.py: 크립토 매크로 센서 - BTC/ETH 가격, 펀딩레이트, 김치프리미엄, 크립토 FnG. collect_crypto_macro()
- market_fear_greed.py: CNN Fear & Greed Index. collect_market_fear_greed()

### 파생상품/옵션
- cboe_options_collector.py: CBOE 풋/콜 비율 (시장 패닉/탐욕 보조)
- cftc_cot.py: CFTC COT 리포트 - 기관 선물 포지셔닝 (상업/비상업/레버리지 자금)
- fund_flow.py: EPFR 프록시 - ETF 기반 펀드 플로우 추정
- expiry_calendar.py: 선물/옵션 만기일 캘린더. get_expiry_status()

### 수익률곡선/채권/ETF
- yieldcurve.py: 미국/한국 수익률 곡선 전체 텀 스프레드. get_full_yield_curve_data()
- bonddata.py: 한국 채권 시장 데이터
- bondus.py: 미국 채권 데이터
- etfdata.py: KR ETF 상위 종목 요약. get_top_etf_summary()
- etfus.py: US ETF/채권 ETF 요약. get_us_etf_summary(), get_bond_etf_summary()

### 뉴스/감성
- news_headlines.py: 한국/미국/블룸버그/구글 뉴스 RSS 수집. collect_headlines(), collect_bloomberg_google_news_rss(), collect_us_headlines()
- news_sentiment.py: 종목별 뉴스 감성 점수 산출. get_stock_sentiment()
- newsapi_client.py: NewsAPI.org 연동 (최대 20개 기사)
- x_sentiment.py: X(구 Twitter) 종목 언급 감성 수집. collect_x_sentiment()
- reddit_sentiment.py: Reddit r/wallstreetbets 등 감성
- naver_community.py: 네이버 종목 토론방 감성
- RSSScout.py: RSS 피드 다수 소스 통합 스카우트
- sentiment_engine.py: 소셜 감성 통합 엔진. compute_social_sentiment()

### 공시/기업 정보
- DartScout.py: DART 전자공시 수집 (dart-fss 라이브러리)
- sec_edgar.py: SEC EDGAR (미국) - 8-K/10-K/10-Q 공시, 리스크 키워드 스캔
- sec_13f_collector.py: SEC 13F - 기관 투자자 보유현황 (분기별). collect_all_13f() + compute_institutional_signal()로 스마트머니 시그널 산출 → Brain inst_13f_bonus에 반영
- ConsensusScout.py: 증권사 컨센서스(목표가/투자의견) 스카우트. scout_consensus(), save_consensus_batch()
- group_structure.py: 기업집단(재벌) 구조 수집. collect_group_structures(), attach_group_structure_to_candidates()
- dart_corp_code.py: DART 기업코드 <-> 종목코드 매핑

### 밸류체인/무역/원자재
- ChainScout.py: 종목별 밸류체인(공급망) 구조 탐색
- CommodityScout.py: 원자재 가격이 종목에 미치는 영향 (yfinance 상관 분석). run_commodity_scout(), attach_commodity_to_stocks()
- customs_trade_stats.py: 관세청 품목별/국가별 수출입 실적. 전월비 급증 시 CN/US/VN 세부 조회
- SpecialScout.py: 특수 이벤트 (규제 변경, 정책 수혜 등)

### 글로벌/이벤트
- global_events.py: FOMC, CPI, GDP, 고용 등 글로벌 이벤트 캘린더. collect_global_events()
- earnings_calendar.py: 실적 발표 일정 수집. collect_earnings_for_stocks()
- sector_analysis.py: 섹터별 등락률/거래대금/수급 랭킹. get_sector_rankings()
- us_sector.py: 미국 섹터별 데이터

### 미국 전용 API
- finnhub_client.py: Finnhub API (60 req/min) - 기업 프로필, 재무, 내부자 거래, 뉴스
- polygon_client.py: Polygon API (free: 5 req/min) - 시세, 거래량, 어그리게이트

### 조립·파생 (틈새 인텔)
- niche_intel.py: 기존 수집 데이터로 종목별 `niche_data` 블록(trends / legal 키워드·hits / credit 참고) 조립. 채권 스프레드에서 `macro.niche_credit`(시장 전체 회사채-국고 스프레드 스냅샷) 파생. `api/main.py`에서 후보 종목에 주입 후 Brain 단계로 전달


## 7) 분석기(Analyzers) 상세

### stock_filter.py - 3단계 깔때기 필터링
- 1차 필터: 거래대금 >= 10억원(KR) / $50M(US)
- 2차 필터: 부채비율 <= 100%
- 3차 필터: 상위 30종목 선정 (거래대금 + 시가총액 가중)
- 리스크 키워드 감지: 배임, 횡령, 실적악화, 상장폐지, 감사의견거절, 자본잠식, 분식회계
- 영문 키워드: fraud, embezzlement, delisting, bankruptcy, SEC investigation, class action

### technical.py - 기술적 분석
- RSI (14일): 과매수(>70)/과매도(<30)
- MACD: 시그널 교차
- 볼린저 밴드: 상/하한 이탈
- 이동평균선: 5/20/60/120일 골든/데드크로스
- analyze_technical() 함수

### multi_factor.py - 멀티팩터 통합점수
- 퀀트 4팩터: momentum, quality, volatility, mean_reversion
- 기본 가중치: constitution.json에서 로드 (레짐별 동적 조정 가능)
- 등급: 강력매수 / 매수 / 관망 / 주의 / 회피

### consensus_score.py - 컨센서스 스코어
- 증권사 목표가 vs 현재가 괴리율
- 투자의견 컨센서스
- 수출무역 데이터 병합. load_trade_export_by_ticker(), merge_fundamental_with_consensus()

### sector_rotation.py - 섹터 로테이션
- 섹터별 자금 유입/유출 트렌드
- 순환 단계 판별 (경기순환 위치)

### safe_picks.py - 안심 추천
- 보수적 기준으로 안전 종목 필터링. generate_safe_recommendations()

### gemini_analyst.py - Gemini AI 분석
- Gemini 2.5 Flash 모델 사용 (환경변수로 변경 가능)
- analyze_batch(): 종목별 AI 분석 (추천등급, 리스크 평가, 한줄평)
  - 프롬프트 컨텍스트에 chain_scout(공급망 주요 고객/리스크)와 special_scout(RRA 규제/특허) 요약을 포함
- generate_daily_report(): 시장 전체 일일 리포트
- generate_periodic_report(): 주간/월간/분기 AI 리포트

### claude_analyst.py - Claude 심층 분석
- Anthropic Claude Sonnet 사용
- analyze_batch_deep(): Brain STRONG_BUY/BUY 상위 N개 심층 반론
- analyze_batch_light(): quick 모드 경량 분석
- merge_dual_analysis(): Gemini 결과와 Claude 결과 합의/분쟁 판별 후 병합
- check_brain_drift(): Brain 판단 드리프트 감지
- analyze_stock_emergency(): 급등락(+-5%) 긴급 분석
- generate_morning_strategy(): 모닝 전략 브리핑 (Claude 작성)

### commodity_narrator.py - 원자재 영향 서술
- Gemini를 활용해 원자재 가격 변동이 종목에 미치는 영향을 자연어로 서술

### macro_adjustments.py - 매크로 패널티
- 매크로 환경 기반 종목 펀더멘털 점수 차감. fundamental_penalty_from_macro()

### value_chain_trade.py - 밸류체인-무역 오버레이
- 수출/수입 데이터를 밸류체인에 매핑. attach_value_chain_trade_overlay()

### bondanalyzer.py / yieldcurveanalyzer.py - 채권/수익률곡선 분석
- 수익률 곡선 역전/정상화 판별
- 채권 시장 시황 분석
- run_bond_analysis(): bond_regime(curve_shape, recession_signal) 산출 → bonds.bond_regime으로 동기화

### etfscreener.py - ETF 스크리너
- ETF 유형별(레버리지/인버스/테마 등) 스크리닝


## 8) 인텔리전스(Intelligence) 엔진

### verity_brain.py - 종합 판단 엔진 v5.0 (별도 섹션에서 상세)

### alert_engine.py - 능동 알림 엔진
- 3단계 알림 레벨:
  - CRITICAL (즉시 행동): 손절 트리거, VIX 폭등, 실적 D-1
  - WARNING (주의 필요): 과매수/과매도, 환율 급변, 실적 D-3
  - INFO (참고): 섹터 전환, 신규 매수 기회
- 분석 대상: 매크로 리스크, Fear&Greed, SEC 리스크 스캔, 펀드 플로우, CFTC COT, 보유종목 리스크, 실적 일정 근접, 타이밍 기회, 뉴스 긴급도, 이벤트 근접, 섹터 로테이션, 컨센서스-수출 괴리, 밸류체인 핫이슈, 원자재 모멘텀
- generate_alerts(): 전체 portfolio 데이터를 분석하여 우선순위 알림 리스트 생성
- generate_briefing(): 시장 브리핑 텍스트 생성

### chat_engine.py - Gemini 대화 엔진
- 텔레그램 봇 + 인앱 채팅 공용
- portfolio.json을 system prompt에 주입하여 데이터 기반 답변
- 종목 질문 시 9줄 이내 정형 포맷 (종목/티커/스냅샷/브레인/추천등급/매수관점/매도관점/리스크/요약)
- 없는 데이터 날조 금지 원칙

### periodic_report.py - 정기 리포트 생성
- 기간별: daily(1일), weekly(7일), monthly(30일), quarterly(90일), semi(180일), annual(365일)
- history/ 스냅샷 기간 분석
- 섹터 동향 분석: 섹터별 평균 등락률, TOP/BOTTOM 섹터, 자금 흐름 방향
- compute_sector_trend_summary(): 섹터 트렌드 요약

### strategy_evolver.py - 전략 진화 엔진
- Claude Sonnet에게 현재 constitution 가중치 + 최근 성과 데이터 제공
- 가중치/임계값 변경 제안 수령
- 제안 -> 백테스트 검증 -> 텔레그램 승인 -> constitution 업데이트
- 적중률 80% + 제안 10회 이상 누적 시 자동 승인 모드 전환
- 각 가중치 최대 변경폭: +-0.05 (STRATEGY_MAX_WEIGHT_DELTA)
- 최소 스냅샷 요건: 14일 (STRATEGY_MIN_SNAPSHOT_DAYS, Bull-market 단기 과적합 방지 목적)

### tail_risk_digest.py - 꼬리위험 감지
- 대상: 전쟁, 대규모 재난, 시장 쇼크, 핵/미사일 등
- 키워드 프리필터(영문/한글) -> Gemini 심각도 판별 -> 고심각도만 텔레그램 발송
- quick/full: 매 실행 1회
- realtime: 키워드 프리필터 통과 + 쿨다운 시에만 Gemini 호출 (비용 절약)
- Claude 교차 검증 옵션 (CLAUDE_TAIL_RISK_VERIFY)

### postmortem.py - AI 오심 포스트모텀
- 과거 BUY 추천이 하락(-3% 이상) 또는 AVOID 추천이 상승한 케이스 추출
- Claude Sonnet에 실패 원인 분석 의뢰
- 결과론적 판단 금지 원칙 (어떤 팩터가 잘못된 시그널을 냈는지 구체적 지적)
- 교훈 형식: "다음에 이 패턴이 보이면 이렇게 하자"

### ai_leaderboard.py - LLM 성과 리더보드
- Gemini vs Claude 소스별 추천 성과 30일 윈도 집계
- 적중률, 평균 수익률 비교

### backtest_archive.py - 추천 백테스트
- history/ 스냅샷의 recommendations[]를 비교
- 7/14/30일 후 성과 추적 (적중률, 수익률)
- evaluate_past_recommendations()
- generate_verification_report(): IC/ICIR + 추천 성과 통합 신호 검증 리포트 (사후 검증용 아카이브, 실시간 판단에 역류하지 않음)

### value_hunter.py - 저평가 발굴 엔진
- 게이트 조건: 14d/30d 승률 >= 55%, 표본 >= 10, 양수 수익
- 밸류 스코어 (0~100): PER(30점) + PBR(25점) + ROE(20점) + 배당(10점) + 품질(10점) + 부채(5점)
- run_value_hunt()

### perplexity_realtime.py - Perplexity 실시간 리서치
- 매크로 이벤트 해석: FOMC/CPI 등 고영향 이벤트
- 실적 발표 직후 요약: 어닝콜 핵심 + 시장 반응
- 종목 외부 리스크 탐지: 소송/규제/스캔들

### quarterly_research.py - Perplexity 분기 딥리서치
- Perplexity sonar-pro 모델 활용
- periodic_quarterly 모드에서 실행
- Constitution 현황 + 성과 + 실패 패턴을 입력으로 전략 리포트 생성
- 결과를 data/research_archive/에 저장


## 9) 예측기(Predictors) 및 퀀트(Quant) 팩터

### 예측 모듈 (api/predictors/)

xgb_predictor.py:
- XGBoost 기반 5일 후 주가 방향 예측
- 피처: 기술적 지표, 수급, 매크로, 감성 등
- predict_stock()

backtester.py:
- 전략 백테스트
- 수익률, 승률, MDD, 샤프비율 산출
- backtest_stock()

timing_signal.py:
- 매수/매도 타이밍 시그널 생성
- RSI 극단값 + 거래량 서지 + 이동평균 교차 복합
- compute_timing_signal()

### 퀀트 팩터 (api/quant/factors/)

momentum.py:
- 3/6/12개월 수익률 기반 모멘텀 스코어
- compute_momentum_score(), enrich_momentum_prices()

quality.py:
- ROE, 영업이익률, FCF/매출, 부채비율 등
- compute_quality_score()

volatility.py:
- 히스토리컬 변동성, ATR, 볼린저밴드 폭
- compute_volatility_score(), compute_universe_vol_stats()

mean_reversion.py:
- 이동평균 이격도, RSI 극단, BB %B
- compute_mean_reversion_score()

### 알파/디케이 (api/quant/alpha/)

alpha_scanner.py:
- 팩터 조합 알파 스캐닝

factor_decay.py:
- IC(Information Coefficient) 측정
- ICIR(IC Information Ratio)
- 팩터 디케이 분석 (시간 경과에 따른 예측력 감쇠)

### 페어 트레이딩 (api/quant/pairs/)

pair_scanner.py:
- 상관관계/공적분 기반 페어 탐색

cointegration.py:
- Engle-Granger / Johansen 공적분 검정


## 10) Verity Brain v5.0 판단 체계

### 스코어링 공식

brain_score = fact_score * 0.7 + sentiment_score * 0.3 + vci_bonus + gs_bonus + candle_bonus + inst_13f_bonus - red_flag_penalty

### Fact Score (객관 팩트)
- 구성: 기술적 + Moat(해자) + Graham Value + CANSLIM Growth
- 가중치: verity_constitution.json의 fact_score.weights에서 로드
- Graham Value Score: 안전마진 + PER/PBR + 재무건전성 (Benjamin Graham 방법론)
- CANSLIM Growth Score: EPS 가속도 + RS Rating + 기관 매집 (William O'Neil 방법론)

### Sentiment Score (심리 팩트)
- 구성: 뉴스 감성 + 소셜 감성 + 크립토 가중치(동적)
- 가중치: verity_constitution.json의 sentiment_score.weights에서 로드

### VCI Bonus (Value Contrarian Indicator)
- Cohen 역발상 체크리스트 기반
- 팩트 점수 대비 감성이 극도로 낮을 때 역발상 보너스

### Candle Psychology Bonus
- Nison 3대 원칙 (Rule of Multiple Techniques)
- 확인 체크리스트 -> timing 보너스

### 13F Institutional Bonus (V6, US 종목 한정)
- SEC 13F 분기 수집 데이터에서 기관 스마트머니 시그널 매칭
- inst_13f_bonus: score >= 70 → +3, score >= 60 → +1, 그 외 0
- 분기별 collect_all_13f() + compute_institutional_signal() 이후 존재 시에만 적용

### Bubble Detection
- Mackay/Shiller/Taleb 기반 시장 레벨 경고 플래그
- 버블 감지 시 전체 등급 하향 조정

### 등급 체계
- STRONG_BUY: brain_score >= 75
- BUY: brain_score >= 60
- WATCH: brain_score >= 45
- CAUTION: brain_score >= 30
- AVOID: brain_score < 30

### 레드플래그 강등
- 리스크 키워드 감지 시 등급 강제 하향
- 대상: 배임/횡령/상장폐지/감사의견거절/자본잠식 등

### 매크로 오버라이드
- panic_stages: VIX 급등/신용경색 등 공황 단계별 전체 등급 캡
- economic_quadrant: 경기 사분면(확장/둔화/수축/회복)별 전략 조정
- DGS10 >= 4.5%: 등급 관망 상한, 현금 확대 권고
- CBOE PCR 오버라이드 (V5.3): 풋/콜 비율 극단 시 VCI 보정 + 패닉 트리거 시 전체 등급 WATCH 상한. _apply_cboe_pcr_override()로 market_brain.cboe_pcr에 시그널/VCI 조정값 기록

### Kelly Position Sizing
- Brain 등급 + 승률 + 변동성 기반 포지션 크기 가이드
- position_sizing 섹션에서 파라미터 로드

### 시장 구조 오버라이드 체인
analyze_all() 내에서 순차 적용:
- V5.2: _apply_market_structure_override() — 만기일 + 프로그램 매매
- V5.3: _apply_cboe_pcr_override() — CBOE 풋/콜 비율 VCI 보정 + 패닉 등급 캡

### 학습 소스 (Brain v5)
- Hedge Fund Masters Report: Hohn / McMurtrie / Tang / Dalio / Guindo
- Quant & Smart Money: Renaissance / Soros / Cohen / Citadel
- 30권 투자 고전 통합: brain_knowledge_base.json v1.0


## 11) Constitution 스키마 (data/verity_constitution.json)

이 파일은 Brain 판단 정책의 Single Source of Truth(SSOT)이다. 분기 업데이트 대상.

핵심 섹션:
- fact_score.weights: 팩트 점수 가중치 (기술적/해자/Graham/CANSLIM)
- quant_factors.factors: 퀀트 팩터 정의
- quant_factors.regime_weights: 레짐별 팩터 가중치
- sentiment_score.weights: 감성 점수 가중치
- vci.thresholds: VCI 역발상 임계값
- hedge_fund_principles: 헤지펀드 원칙 (마스터 투자자 규칙)
- panic_stages: 공황 단계별 전략
- economic_quadrant: 경기 사분면 전략
- position_sizing: 포지션 크기 산출 파라미터
- decision_tree: 판단 의사결정 트리
- red_flags: 레드플래그 규칙
- macro_override: 매크로 오버라이드 규칙
- gemini_system_instruction: Gemini AI 시스템 프롬프트


## 12) VAMS 가상 매매 시스템

VAMS (Virtual Asset Management System)은 Brain 판단 결과를 기반으로 가상 투자를 시뮬레이션하는 엔진이다.

### 프로파일 3종 (VAMS_ACTIVE_PROFILE 환경변수로 선택)

aggressive (공격):
- 매수 조건: BUY 또는 STRONG_BUY
- 최소 안심 점수: 45점
- 리스크 키워드 허용: 2개
- 최대 보유 종목: 10개
- 사이클당 최대 매수: 5종목
- 손절: -8%
- 트레일링 스톱: 고점 대비 5% 하락
- 최대 보유 기간: 21일
- 종목당 최대 투자: 300만원

moderate (중간, 기본값):
- 매수 조건: BUY 또는 STRONG_BUY
- 최소 안심 점수: 55점
- 리스크 키워드 허용: 1개
- 최대 보유 종목: 7개
- 사이클당 최대 매수: 5종목
- 손절: -5%
- 트레일링 스톱: 고점 대비 3% 하락
- 최대 보유 기간: 14일
- 종목당 최대 투자: 200만원

safe (안전):
- 매수 조건: BUY만 (STRONG_BUY 제외)
- 최소 안심 점수: 70점
- 리스크 키워드 허용: 0개
- 최대 보유 종목: 3개
- 사이클당 최대 매수: 2종목
- 손절: -3%
- 트레일링 스톱: 고점 대비 2% 하락
- 최대 보유 기간: 10일
- 종목당 최대 투자: 150만원

### 공통 설정
- 초기 자본금: 1,000만원 (VAMS_INITIAL_CASH 환경변수)
- 수수료: 0.015% (VAMS_COMMISSION_RATE = 0.00015)
- NaN/Infinity sanitize 후 저장

### 자동매매 (선택, 실계좌 — api/trading/auto_trader.py)

- `recommendations[]`의 추천·안전점수와 `timing_signal` 기반으로 KIS 매수/매도 주문을 **계획**하고, 한도·장시간·드라이런·킬스위치를 통과하면 **제출**한다.
- 브로커 DI: `MockKISBroker`(`api/trading/mock_kis_broker.py`)로 로컬 검증, `KISBroker`로 실거래.
- 산출·상태: `data/auto_trade_history.json`, 킬스위치 `data/.auto_trade_paused`(파일 존재 시 전체 중단).
- 환경변수: `AUTO_TRADE_*` (§22 참고). 검증용 스크립트: `scripts/simulate_auto_trade.py`.

### 매매 로직 (run_vams_cycle)
1. 매도 검사: 손절/트레일링/보유기간 초과 시 매도
2. 신규 매수: 추천등급 + 안심점수 + 리스크 조건 충족 시 매수
3. 통계 갱신: 누적 수익률, 승률, MDD, 거래 횟수


## 13) Safety Layer (v8.2)

### Deadman's Switch
- api/health.py의 validate_deadman_switch()
- DEADMAN_FAIL_THRESHOLD (기본 3) 이상 데이터 소스 실패 시 분석 즉시 중단
- 텔레그램 긴급 알림: send_deadman_alert()
- 감시 대상: DART, FRED, ECOS, Telegram, Gemini, Anthropic, KIPRIS, 공공데이터, KRX Open API

### Cross-Verification
- Gemini와 Claude 의견 분열 시 텔레그램 즉시 알림
- send_cross_verification_alert()
- 사용자가 최종 판단

### AI 포스트모텀
- 주간 실행 (full 모드)
- 과거 BUY -> 하락, AVOID -> 상승 케이스 추출
- Claude가 원인 분석 -> 텔레그램 발송
- send_postmortem_report()

### Strategy Evolver
- Claude가 constitution 가중치 변경 제안
- 텔레그램 승인 플로우: 제안 -> 검증 -> 승인/거절
- 안전장치: 각 가중치 최대 +-0.05, 합계 1.0 유지
- 자동 승인: 적중률 80% + 누적 10회 이상

### Brain Drift Detection
- check_brain_drift(): Brain 판단 패턴이 과거 대비 편향 발생 시 경고

### CBOE PCR 패닉 가드
- _apply_cboe_pcr_override(): CBOE 풋/콜 비율 극단 시 전체 등급 WATCH 상한
- macro_override 또는 secondary_signals에 cboe_panic 모드 기록
- 개별 종목에 cboe_downgrade 플래그 부착

### VAMS 시뮬레이션 추적
- 누적 매매 통계, 승률, MDD 자동 추적
- send_vams_simulation_report()


## 14) 텔레그램 알림 및 봇 명령

### 발송 모듈 (api/notifications/telegram.py)

send_daily_report(): 일일 종합 리포트 (full 모드, KST 16:30)
send_morning_briefing(): 모닝 브리핑 (KST 08:00)
send_alerts(): 능동 알림 (CRITICAL/WARNING/INFO)
send_deadman_alert(): Deadman Switch 긴급 알림
send_cross_verification_alert(): Gemini-Claude 분열 알림
send_postmortem_report(): AI 오심 복기 리포트
send_vams_simulation_report(): VAMS 시뮬레이션 리포트

### 텔레그램 봇 명령 (api/notifications/telegram_bot.py)

/approve_strategy: 전략 진화 제안 승인
/reject_strategy: 전략 진화 제안 거절
/rollback_strategy: 이전 전략으로 롤백
/strategy_status: 현재 전략 상태 조회

### 중복 제거 (api/notifications/telegram_dedupe.py)
- filter_deduped_realtime_alerts(): 동일 알림 중복 방지
- mark_realtime_alerts_sent(): 발송 완료 마킹
- 15분 주기 실행 환경에서 같은 알림 반복 방지

### 채팅 (chat_engine.py)
- 텔레그램 봇에서 자유 질문 -> Gemini가 portfolio.json 기반 답변
- TELEGRAM_ALLOWED_CHAT_IDS로 접근 제어

### 타이밍 시그널 워처 (api/notifications/timing_signal_watcher.py)
- `recommendations[].timing.action`이 이전 사이클 대비 유의미하게 바뀐 경우에만 텔레그램 알림(쿨다운 적용, 보유 종목 매도 시그널 강조).
- 상태 파일: `data/.timing_state.json`


## 15) portfolio.json 데이터 스키마

portfolio.json은 시스템의 유일한 산출물이며, 모든 프론트엔드/알림/리포트가 이 파일을 소비한다.

### 최상위 키 구조

macro: 매크로 지표 (VIX, 환율, 금리, market_mood 등)
  - niche_credit: (선택) niche_intel이 채권 스프레드에서 파생한 시장 신용 스냅샷
recommendations[]: 종목별 분석 결과 배열
  - ticker, name, market, price, change_pct
  - recommendation (BUY/HOLD/SELL)
  - safety_score, risk_flags[]
  - technical (RSI, MACD, BB 등)
  - multi_factor (multi_score, grade, factor_breakdown)
  - sentiment (score, social, news)
  - xgb_prediction, backtest
  - brain_score, brain_grade, inst_13f_bonus (US 종목)
  - gemini_analysis, claude_analysis
  - consensus, commodity_impact
  - trends (1m/3m/6m/1y), sparkline_weekly[]
  - earnings_date, group_structure
  - niche_data: (선택) trends / legal / credit — niche_intel 조립 결과
vams: VAMS 가상 투자 현황
  - cash, total_value, holdings[]
  - trade_stats (total_trades, win_rate, avg_return, max_drawdown)
headlines[]: 뉴스 헤드라인 배열
sectors[]: 섹터별 등락/거래 데이터
briefing: AI 생성 시장 브리핑 텍스트
global_events[]: 글로벌 이벤트 목록
daily_report: 일일 AI 종합 리포트 (Gemini 생성)
earnings_calendar[]: 실적 발표 일정
sector_rotation: 섹터 로테이션 현황
verity_brain: Brain 시장 집계
  - market_brain (avg_brain_score, grade_distribution, top_picks[])
  - market_brain.cboe_pcr (signal, panic_trigger, vci_adjustment, pcr_latest)
  - macro_override (활성 시 레벨/이유, secondary_signals[])
  - bubble_warning
market_fear_greed: CNN Fear & Greed 지수
cftc_cot: CFTC COT 기관 포지셔닝
fund_flows: 펀드 플로우
yield_curve: 수익률 곡선 데이터
crypto_macro: 크립토 매크로 센서
  - btc_price, eth_price, funding_rate, kimchi_premium, crypto_fng
tail_risk: 꼬리위험 평가
sec_risk_scan: SEC 8-K 리스크 키워드 스캔
institutional_13f: 13F 기관 투자자 분기 데이터
  - institutions_collected, updated_at
  - signal (ok, smart_money_consensus[], ticker_signal{})
krx_openapi: KRX OpenAPI 슬림 스냅샷 (summary + 메타만 저장, 상세 rows 제거)
  - bas_dd, updated_at, summary, tier_plan, tier_updated_at
bonds.bond_regime: 채권 레짐 (curve_shape, recession_signal)
bond_analysis: 채권 분석 결과 (run_bond_analysis 산출물)
alert_history[]: 알림 이력
backtest_results: 백테스트 통계
  - hit_rate_7d, hit_rate_14d, hit_rate_30d
  - avg_return_7d, avg_return_14d, avg_return_30d
ai_leaderboard: Gemini vs Claude 성과 비교
value_hunt[]: 저평가 발굴 종목
postmortem[]: AI 오심 복기 결과
periodic_report: 정기 리포트 데이터
strategy_evolution: 전략 진화 상태
health: 시스템 헬스 (API 상태, 데이터 신선도)
updated_at: 마지막 갱신 시각 (ISO 8601, KST)


## 16) Framer 프론트엔드 컴포넌트

모든 컴포넌트는 Framer Code Components로 작성되며, portfolio.json을 fetch하여 렌더링한다.
인라인 스타일, 다크 테마 (#000 배경, #B5FF19 액센트).

### 인증·게이트·모바일
- AuthPage.tsx: Supabase Auth 기반 로그인/회원가입 UI (프로젝트별 메타·리다이렉트 연동)
- AuthGate.tsx: 세션·프로필(승인 상태 등) 검사 후 자식 컴포넌트 노출
- LogoutButton.tsx: 로그아웃·세션 정리
- MobileApp.tsx: 모바일 단일 셸(탭/네비)에서 대시보드·패널 조합

### 핵심 대시보드
- StockDashboard.tsx (1796줄): 메인 종목 대시보드. 종목 카드, 스파크라인, 트렌드 블록, Brain 점수, 추천등급 표시. kr/us 마켓 전환. Vercel API 연동 (검색/상세)
- StockDetailPanel.tsx (1286줄): 종목 상세 패널. 기술적 차트, 재무 데이터, AI 분석, 컨센서스, 밸류체인
- TradingPanel.tsx: KIS 연동 실거래 패널 (매수/매도/잔고)

### Brain/AI 패널
- VerityBrainPanel.tsx (701줄): Brain 시장 집계 대시보드. 평균 점수, 등급 분포, TOP 종목, 레드플래그, 매크로 오버라이드, 버블 경고
- VerityReport.tsx: Gemini AI 일일/정기 리포트 뷰어
- VerityChat.tsx: AI 채팅 인터페이스

### 매크로/시장
- MacroSentimentPanel.tsx (363줄): 매크로 감성 지표 패널 (VIX, 환율, Fear&Greed, 경기지표)
- MacroPanel.tsx: 매크로 지표 상세
- GlobalMarketsPanel.tsx: 글로벌 시장 지수 현황

### 채권/ETF
- BondDashboard.tsx (206줄): 채권 대시보드 (금리 추이, 스프레드)
- YieldCurvePanel.tsx (198줄): 수익률 곡선 시각화
- ETFDashboard.tsx: ETF 대시보드
- ETFScreenerPanel.tsx: ETF 스크리너

### 관심종목/검색
- WatchGroupsCard.tsx (718줄): 관심종목 그룹 관리 (Supabase CRUD). 그룹 생성/삭제, 종목 추가/제거, 실시간 가격 표시
- StockSearch.tsx (436줄): 종목 검색 (Vercel API + 로컬 필터). KR/US 통합 검색
- CompareCard.tsx: 종목 비교 카드

### VAMS/투자
- VAMSProfilePanel.tsx (310줄): VAMS 프로파일 상태 뷰어. 3종 프로파일 파라미터, 보유종목, 거래 통계
- SafePicks.tsx: 안심 추천 카드
- BacktestDashboard.tsx: 백테스트 결과 대시보드

### 뉴스/센티먼트
- NewsHeadline.tsx: 뉴스 헤드라인 스크롤
- SentimentPanel.tsx: 감성 분석 패널
- NicheIntelPanel.tsx: 틈새 인텔리전스

### 알림/브리핑
- AlertDashboard.tsx: 알림 대시보드 (CRITICAL/WARNING/INFO)
- AlertBriefing.tsx: 시장 브리핑 카드

### 미국 시장 전용
- USInsiderFeed.tsx: 내부자 거래 피드
- USAnalystView.tsx: 애널리스트 뷰
- USEarningsCalendar.tsx: 미국 실적 캘린더
- USEconCalendar.tsx: 미국 경제 캘린더
- USSectorMap.tsx: 미국 섹터 맵
- USMag7Tracker.tsx: Mag7(빅테크) 트래커
- USMapEmbed.tsx: 미국 맵 임베드
- USCapitalFlowRadar.tsx: 미국 자본 흐름 레이더

### 기타 패널
- MarketBar.tsx: 상단 시장 지수 바
- MarketCountdown.tsx: 개장/마감 카운트다운
- ScrollingTicker.tsx: 스크롤링 티커
- WorldClockRow.tsx: 세계 시계 (KST/EST/UTC)
- SectorHeat.tsx: 섹터 히트맵
- KRXHeatmap.tsx: KRX 시장 히트맵
- CapitalFlowRadar.tsx: 한국 자본 흐름 레이더
- CryptoMacroSensor.tsx: 크립토 매크로 센서 패널
- GlobalMapEmbed.tsx: 글로벌 맵 임베드
- TaxGuide.tsx: 세금 가이드
- ManualInput.tsx: 실계좌 수동 입력
- SystemHealthBar.tsx: 시스템 헬스 상태바
- LiveVisitors.tsx: 라이브 방문자

### 공통 유틸리티
- fetchPortfolioJson.ts: portfolio.json fetch 유틸 (NaN 방어, 캐시 무효화)
- _shared-patterns.ts: 공유 패턴
- watchGroupsClient.ts: Supabase 관심종목 API 클라이언트
- netPnlCalc.ts: 순손익 계산
- types/: TypeScript 타입 정의


## 17) Vercel Serverless API

엔드포인트 (vercel-api/api/):

/api/search: 종목 검색 (maxDuration: 5s)
  - KR: KRX 종목명/코드 검색
  - US: Polygon/Finnhub 검색

/api/stock: 종목 요약 (maxDuration: 30s)
  - 현재가, 등락, 추천등급 반환

/api/stock_detail: 종목 상세 (maxDuration: 30s)
  - 재무, 기술적, AI 분석, 컨센서스, 밸류체인

/api/chart: 차트 데이터 (maxDuration: 10s)
  - 일봉/주봉/분봉 OHLCV

/api/chat: AI 채팅 (maxDuration: 30s)
  - Gemini 기반 질의응답

/api/order: 주문 API (maxDuration: 10s)
  - KIS 연동 실거래 주문

/api/watchgroups: 관심종목 CRUD (maxDuration: 10s)
  - Supabase 연동

CORS: 전체 허용 (Access-Control-Allow-Origin: *)
배포: Vercel에 vercel-api/ 루트 디렉토리 설정


## 18) KIS 실시간 중계 서버

server/ 디렉토리. FastAPI + SSE(Server-Sent Events) 구조.

### 기능
- KIS Open API WebSocket을 구독하여 실시간 호가/체결 데이터를 SSE로 중계
- 1분봉 집계 (OHLCV)
- idle 종목 자동 해제 (구독 해지)
- 토픽 기반 라우팅

### 엔드포인트 (kis_rest_client.py)
- fetch_price(): 실시간 가격
- fetch_orderbook(): 호가
- fetch_trades(): 체결
- fetch_daily(): 일별 시세
- fetch_minute(): 분별 시세
- place_kr_order(): KR 주문
- place_us_order(): US 주문
- get_balance(): 잔고 조회

### 배포
- Railway $5 플랜
- Dockerfile 기반 컨테이너 배포
- KIS 토큰 캐시 (하루 1회 재발급)

### 실전/모의 구분
- KIS_OPENAPI_BASE_URL로 결정
- 실전: openapi.koreainvestment.com:9443
- 모의: openapivts.koreainvestment.com:29443


## 19) Supabase 데이터 계층

### 테이블 (요약)
- watch_groups: 관심종목 그룹. RLS 적용. `003`에서 `auth_user_id`(auth.users FK) 점진 전환
- profiles: Auth 사용자 1:1 프로필 (이메일, display_name 등). 트리거로 가입 시 자동 생성
- user_holdings: 유저별 보유 종목(티커, 수량, 평단, 메모)
- user_alert_prefs: 유저별 알림 on/off 등

### 마이그레이션
- 001_watch_groups.sql: 초기 스키마
- 002_watch_groups_rls_harden.sql: RLS 보안 강화
- 003_auth_profiles.sql: profiles + user_holdings + user_alert_prefs + watch_groups auth 연동 컬럼

### 프론트·운영 가이드
- 절차 전체: `docs/SUPABASE_AUTH_SETUP.md` (SQL, RLS, Framer 환경변수, 승인 플로우 등)

### API 접근
- SUPABASE_URL, SUPABASE_ANON_KEY 환경변수 (Framer Code Component 및 Vercel 함수)
- vercel-api/api/supabase_client.py: Supabase 연결
- vercel-api/api/watchgroups.py: CRUD 엔드포인트
- framer-components/watchGroupsClient.ts: 클라이언트


## 20) CI/CD 및 GitHub Actions

### 워크플로 4종

daily_analysis.yml (메인):
- 24시간 가동 (30개+ 크론 엔트리)
- Python 3.11, pip 캐시
- KIS 토큰 캐시 (actions/cache@v4, 하루 1회 키)
- 한글 폰트 자동 다운로드 (NanumGothic)
- 모드 자동 감지 (Detect periodic schedule)
- 분석 실행 -> data/ 커밋 & 푸시 (최대 5회 재시도)
- Concurrency: daily-analysis, cancel-in-progress

bond_etf_analysis.yml:
- 평일 KST 07:00 (채권 시황) + KST 18:30 (ETF 마감)
- 채권/ETF 분석 전용 파이프라인
- 모드: bonds / etfs / all

export_trade_daily.yml:
- 평일 KST 17:30 (장 마감 무렵)
- 관세청 수출입 통계 + HS코드 매핑
- 일 1회 실행 (월 단위 데이터, 호출 절약)

rss_scout.yml:
- 장중: 15분 간격 (KST 09:00~15:30)
- 장외: 30분 간격
- RSS 뉴스 스카우트 전용
- 월 ~900회 실행 (비용 최적화)

### 배포 방식
1. GitHub Actions에서 api/main.py 실행
2. data/ 산출물 git add -> commit -> push
3. GitHub Pages에서 data/ 정적 호스팅
4. Framer가 GitHub raw URL에서 최신 JSON fetch


## 21) PDF 리포트 시스템

### 생성기 (api/reports/pdf_generator.py)
- fpdf2 라이브러리 사용
- 한글 폰트: NanumGothic Regular + Bold (자동 다운로드)
- portfolio.json 데이터 기반 전문 투자 리포트 작성

### 리포트 구조
- 제1장: 요약 (시장 지표 + AI 분석 결과 종합)
- 매크로 환경 (VIX, 환율, Fear&Greed, 수익률 곡선)
- 종목별 분석 (Brain 점수, 추천등급, AI 해석)
- VAMS 운용 성과
- 리스크 평가
- 정기 성과 복기 (주간~연간)

### 출력
- data/verity_report_daily.pdf: 일일 리포트
- data/verity_report_weekly.pdf: 주간 리포트
- 파일명 패턴: verity_report_{period}.pdf

### 문서 ID: VERITY-DR-{YYYYMMDD}


## 22) 환경변수 완전 표

### AI 모델
- GEMINI_API_KEY: Gemini API 키 (필수)
- GEMINI_MODEL: Gemini 기본 모델명 (기본: gemini-2.5-flash)
- GEMINI_MODEL_DEFAULT: 배치 분석용 모델 (미설정 시 GEMINI_MODEL 사용)
- GEMINI_MODEL_CRITICAL: 리포트/상위 종목 재판단용 모델 (기본: gemini-2.5-pro)
- GEMINI_PRO_ENABLE: Pro 하이브리드 라우팅 활성화 (0/1, 기본: 1)
- GEMINI_CRITICAL_TOP_N: Pro 재판단 대상 상위 종목 수 (기본: 3)
- ANTHROPIC_API_KEY: Anthropic Claude API 키 (선택, 심층분석용)
- PERPLEXITY_API_KEY: Perplexity API 키 (선택, 분기 리서치)
- PERPLEXITY_MODEL: Perplexity 모델 (기본: sonar-pro)

### 한국 데이터 API
- DART_API_KEY: DART 전자공시 API
- ECOS_API_KEY: 한국은행 ECOS API
- KRX_API_KEY (또는 KRX_OPENAPI_KEY): KRX Open API 인증키. 키 발급 + API별 이용신청 필요
- PUBLIC_DATA_API_KEY: 공공데이터포털 (관세청 수출입)
- KIPRIS_API_KEY / KIPRIS_ACCESS_KEY: 특허정보원 API

### 미국 데이터 API
- FRED_API_KEY: FRED (미 연준 경제지표)
- FMP_API_KEY: Financial Modeling Prep
- FINNHUB_API_KEY: Finnhub (60 req/min)
- POLYGON_API_KEY: Polygon.io (free: 5 req/min)
- POLYGON_TIER: 요금제 (기본: free)
- NEWS_API_KEY: NewsAPI.org
- SEC_EDGAR_USER_AGENT: SEC EDGAR User-Agent

### 텔레그램
- TELEGRAM_BOT_TOKEN: 텔레그램 봇 토큰
- TELEGRAM_CHAT_ID: 기본 채팅 ID
- TELEGRAM_ALLOWED_CHAT_IDS: 허용 채팅 ID 목록 (쉼표 구분)

### KIS (한국투자증권)
- KIS_APP_KEY: KIS Open API 앱 키
- KIS_APP_SECRET: KIS Open API 앱 시크릿
- KIS_ACCOUNT_NO: 계좌번호
- KIS_OPENAPI_BASE_URL: 실전/모의 서버 URL

### Supabase
- SUPABASE_URL: Supabase 프로젝트 URL
- SUPABASE_ANON_KEY: Supabase Anon 키

### VAMS 설정
- VAMS_INITIAL_CASH: 초기 자본금 (기본: 10,000,000)
- VAMS_MAX_PER_STOCK: 종목당 최대 투자금 (기본: 프로파일 설정)
- VAMS_ACTIVE_PROFILE: 프로파일 (aggressive/moderate/safe, 기본: moderate)

### 자동매매 (KIS, 선택)
- AUTO_TRADE_ENABLED: 마스터 스위치 (기본: false)
- AUTO_TRADE_DRY_RUN: true면 주문 미제출 (기본: true)
- AUTO_TRADE_MAX_DAILY_BUY_KRW: 일일 매수 상한 (기본: 500,000)
- AUTO_TRADE_MAX_PER_STOCK_KRW: 종목당 상한 (기본: 200,000)
- AUTO_TRADE_ALLOW_OVERSEAS: 해외 매매 허용 (기본: false)
- AUTO_TRADE_MIN_SAFETY_SCORE / AUTO_TRADE_MIN_TIMING_SCORE: 최소 점수 (기본: 70)
- AUTO_TRADE_ALLOW_AFTER_HOURS: 장외 허용 (기본: false)

### Claude 분석 설정
- CLAUDE_TOP_N: Brain 상위 N개 심층분석 (기본: 5)
- CLAUDE_MIN_BRAIN_SCORE: 심층분석 최소 점수 (기본: 60)
- CLAUDE_IN_QUICK: quick 모드 Claude (0/1, 기본: 0)
- CLAUDE_IN_REALTIME: realtime 모드 Claude (0/1, 기본: 0)
- CLAUDE_QUICK_TOP_N: quick 모드 상위 N개 (기본: 3)
- CLAUDE_EMERGENCY_THRESHOLD_PCT: 급등락 긴급분석 임계 (기본: 5.0%)
- CLAUDE_EMERGENCY_COOLDOWN_MIN: 긴급분석 쿨다운 (기본: 120분)
- CLAUDE_TAIL_RISK_VERIFY: 꼬리위험 Claude 교차검증 (0/1, 기본: 1)
- CLAUDE_MORNING_STRATEGY: 모닝 전략 생성 (0/1, 기본: 1)

### VERITY_MODE (mock / 실호출 분기)
- VERITY_MODE: `dev`(기본) / `staging` / `prod` — AI·유료 수집기 mock 여부 (상세: `docs/VERITY_MODE.md`)
- VERITY_STAGING_REAL_KEYS: staging에서만 실호출할 논리 키 쉼표 목록 (예: `gemini.daily_report`)

### 운영 설정
- ANALYSIS_MODE: 분석 모드 강제 지정
- DEADMAN_FAIL_THRESHOLD: Deadman 임계 (기본: 3)
- REPORT_SEND_HOUR_KST / REPORT_SEND_MINUTE_KST: 일일 리포트 시각 (기본: 16:30)
- MORNING_BRIEF_HOUR_KST / MORNING_BRIEF_MINUTE_KST: 모닝 브리핑 시각 (기본: 08:00)
- POSTMORTEM_ENABLED: 포스트모텀 (기본: 1)
- STRATEGY_EVOLUTION_ENABLED: 전략 진화 (기본: 1)
- STRATEGY_MAX_WEIGHT_DELTA: 가중치 최대 변경폭 (기본: 0.05)
- STRATEGY_MIN_SNAPSHOT_DAYS: 진화 최소 스냅샷 (기본: 14일)

### 매크로/지표 임계값
- MACRO_DGS10_DEFENSE_PCT: DGS10 방어 임계 (기본: 4.5%)
- MARKET_FNG_EXTREME_GREED: 극단 탐욕 (기본: 75)
- MARKET_FNG_EXTREME_FEAR: 극단 공포 (기본: 25)
- CRYPTO_FUNDING_OVERHEAT: 크립토 펀딩 과열 (기본: 0.06)
- CRYPTO_KIMCHI_PREMIUM_WARN: 김치프리미엄 경고 (기본: 5.0%)
- US_IV_PERCENTILE_WARN: 미국 IV 경고 (기본: 80%)
- US_PUT_CALL_BEARISH: 풋/콜 약세 (기본: 1.5)
- US_INSIDER_MSPR_PENALTY: 내부자 MSPR 패널티 (기본: -5)

### 기타
- NEWSAPI_MAX_ARTICLES: 기사 최대 수 (기본: 20)
- FINNHUB_RATE_LIMIT: Finnhub 분당 제한 (기본: 60)
- SEC_FETCH_TIMEOUT: SEC 요청 타임아웃 (기본: 15초)
- FILTER_MIN_TRADING_VALUE: KR 최소 거래대금 (10억원)
- FILTER_MIN_TRADING_VALUE_US: US 최소 거래대금 ($50M)
- FILTER_MAX_DEBT_RATIO: 최대 부채비율 (100%)
- FILTER_TOP_N: 상위 N종목 (30)


## 23) 외부 API 의존성 목록

### 무료 (키 불필요)
- pykrx: KRX 공개 데이터
- yfinance: Yahoo Finance 시세
- CBOE: 풋/콜 비율
- CoinGecko: 크립토 가격
- RSS 피드: 블룸버그, 구글뉴스 등

### 무료 (키 필요)
- GEMINI: Google AI Studio (google-genai)
- FRED: 미 연준 경제지표
- DART: 전자공시 (dart-fss)
- ECOS: 한국은행
- SEC EDGAR: 미국 공시 (User-Agent만 필요)
- CNN Fear & Greed: fear_and_greed 라이브러리

### 프리미엄/유료
- ANTHROPIC: Claude Sonnet (종량제)
- PERPLEXITY: Sonar Pro (종량제)
- FINNHUB: 60 req/min (무료 티어)
- POLYGON: 5 req/min (무료 티어)
- NewsAPI: 1000 req/일 (무료 개발자)
- KRX Open API: 무료지만 API별 이용신청 필요
- 공공데이터포털: 무료 (활용신청)
- KIS Open API: 한국투자증권 고객 전용
- SUPABASE: 무료 티어 (500MB DB)


## 24) Perplexity 온보딩 프롬프트 (복붙용)

```
너는 VERITY 시스템의 수석 설계 리뷰어다.

[목표]
- 이 시스템은 KR/US 주식 자동 분석 엔진이다.
- 핵심 출력은 data/portfolio.json이다.
- Brain 정책은 data/verity_constitution.json이 SSOT다.
- 24시간 GitHub Actions 기반 서버리스 운영 (15분~1시간 주기).

[시스템 규모]
- 백엔드: Python ~3150줄 메인 + 70개+ 모듈
- 프론트: Framer Code Components 49개 TSX (인증·모바일 셸 포함)
- 수집기: 48개 (KR/US 시장, 매크로, 뉴스, 공시, 원자재, 크립토, 대안 데이터, niche_intel)
- AI: Gemini 2.5 Flash (1차) + Claude Sonnet (반론/검증) + Perplexity (리서치)
- 판단: Verity Brain v5.0 (Graham/CANSLIM/캔들심리/버블감지)
- 자동화: VAMS 가상매매, (선택) KIS 자동매매+타이밍 워처, 전략 진화, AI 포스트모텀, 꼬리위험 감지

[분석 범위]
1) api/main.py의 모드별 파이프라인 (realtime/quick/full/full_us/periodic)
2) verity_brain.py의 스코어링 (fact*0.7 + sentiment*0.3 + VCI + candle)
3) gemini_analyst.py + claude_analyst.py 역할 분리 (1차 분석 vs 반론/합의)
4) periodic_report.py + strategy_evolver.py의 주기학습 구조
5) Safety Layer: Deadman Switch, Cross-Verification, AI 포스트모텀
6) 프론트 컴포넌트가 portfolio.json을 어떻게 소비하는지

[출력 요구]
- 반드시 "아키텍처 요약 -> 리스크 -> 개선안 -> 실행 단계" 순서로 작성
- 개선안은 바로 구현 가능한 파일 단위 액션 아이템으로 제시
- 각 제안은 기대효과/리스크/롤백전략 포함
- 추측은 금지하고, 불확실하면 "추가 코드 확인 필요"로 표기
```


## 25) 분기 리서치 기획 템플릿 (Perplexity용)

```
[요청]
분기 리서치 보고서를 생성하라.
주제: 퀀트 + 헤지펀드 + 롱/숏 + 매크로 레짐

[입력 컨텍스트]
- 현행 constitution: fact/sentiment/vci/red_flags/position_sizing
- 최근 90일 성과: hit_rate, sharpe, max_drawdown
- 최근 실패 패턴: postmortem lesson
- Brain v5.0 학습 소스: Graham/CANSLIM/Cohen VCI/Nison Candle

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


## 26) 개발·테스트 자산

- api/mocks/: VERITY_MODE mock 픽스처·트레이스 리플레이 (`fixtures.py`, `trace_replay.py`)
- api/tracing/run_tracer.py: 파이프라인 실행 추적
- tests/: pytest — `test_auto_trader.py`, `test_timing_watcher.py`, `conftest.py`
- scripts/simulate_auto_trade.py: 자동매매 로컬 시뮬레이션


## 부록 A) 현재 확장 과제

1. Perplexity 분기 딥리서치 (quarterly_research.py) -> Constitution 학습 루프 연결
2. Value Hunter 저평가 발굴 -> VAMS 자동 편입 파이프라인
3. Factor Decay/IC 기반 동적 팩터 가중치 조정
4. Pair Trading 시그널 -> 알림 연동
5. 자동매매 운영 고도화 (승인 큐·감사 로그·해외 정책 등, 현재는 한도·드라이런·킬스위치 중심)

## 부록 B) 버전 이력

- v1.0: 기본 수집 + Gemini 분석
- v2.0: VAMS 가상매매 + 텔레그램 알림
- v3.0: Claude 반론 + 멀티팩터
- v4.0: Brain v3 + Constitution
- v5.0: US 시장 확장 + Finnhub/Polygon/SEC
- v6.0: Brain v4 + 퀀트팩터 + 백테스트
- v7.0: Brain v5 (Graham/CANSLIM/VCI/Candle) + 전략 진화
- v8.0: 24h 15min 가동 + 꼬리위험 + Perplexity
- v8.2: Safety Layer (Deadman/Cross-Verify/포스트모텀) + VAMS 프로파일 3종
- v8.3: CBOE PCR 패닉 오버라이드(V5.3) + 13F 기관 스마트머니 보너스(V6) + Gemini 프롬프트 Scout 컨텍스트 + KRX slim snapshot + bond_regime 동기화 + alt_data/verification_report 아카이브 경계 명시
- v8.4: Supabase Auth·profiles·holdings + Framer AuthGate/AuthPage/MobileApp + niche_intel(`niche_data`, `macro.niche_credit`) + auto_trader/mock broker + timing_signal_watcher + VERITY_MODE 문서 + mocks/tracing/tests + `.env.example`
- v8.4.1: 히스토리 실행별 감사 스냅샷(`history/runs/`) 도입 + Strategy Evolver 최소 스냅샷 기본 7 → 14일 상향 (Brain 로그 무결성·조기 개입 방지)
- v8.5.0 (2026-04-28): Brain Monitor Phase 1~4 + 잠금 폐기 + Phase A 룰 이식 + Brain 진화 시스템 + Vercel 통합 (아래 §27 참조)
- v8.6.0 (2026-04-30): 자가진단 메타-검수 + Trust verdict 정확도 + Drift cry-wolf 완화 + per-source freshness (아래 §28 참조)
- v8.7.0 (2026-04-30): 베테랑 due diligence 7개 결함 중 1/6/2/3/4 대응 + gh-pages dual-write 인프라 (아래 §29 참조)

---

## 27) 2026-04-28 Sprint 10 — Brain Monitor + Phase A 룰 이식

### 27.1 잠금 정책 폐기 (2026-04-26)

분기/반기/연간 리포트의 정적 잠금 (Brain 코드 동결 + N일 누적) 정책 폐기. 검증 의미를 다음과 같이 재정의:

- 옛 정의 (잠금시절): "룰 동결 + N일 누적" — 통제 변수 가정
- 새 정의: "운영 누적 N일치 시그널-결과 페어" — 룰은 진화 OK, 매일 시그널-결과 매칭이 누적되면 검증 데이터로 인정

VAMS 검증 (D+90/D+180/D+365) 자체는 유지. ValidationPanel.tsx 의 "사전 약속 판정" → "운영 누적 판정 · 룰 진화 OK".

4 가드 (`feedback_continuous_evolution`):
1. commit (모든 변경 추적)
2. 시간대 (cron 후 모니터링 기간)
3. 모니터링 (grade 분포 / brain_score 변화)
4. 롤백 (이상 시 commit revert)

### 27.2 Brain Monitor (Phase 1~4)

관리자 전용 모니터링 + 리포트 발행 신뢰도 판정. `api/observability/` 4개 측정 모듈 + 5탭 대시보드 + Telegram 알림 + Trust PDF 게이팅.

Phase 1 — 측정 모듈:
- `data_health.py` — 소스별 신선도/성공률/결측률
- `feature_drift.py` — PSI 기반 drift
- `explainability.py` — Brain Score 기여도 분해
- `trust_score.py` — 8조건 자동 판정 (ready/manual_review/hold)
- `data/metadata/{data_health,feature_drift,explainability,trust_log}.jsonl` 자동 누적

Phase 2 — 5탭 대시보드:
- Framer 코드 컴포넌트 `BrainMonitor.tsx` (단일 .tsx, ~870 라인)
- iframe 우회 (3D Three.js 폐기 → 2D SVG 만)
- Overview / Data Health / Model Health / Drift / Report Readiness
- API: `/api/admin?type=brain_health|data_health|drift|trust|explain`
- 인증: X-Admin-Token (`ADMIN_BYPASS_TOKEN` env)

Phase 3 — 폐기:
- 3D Three.js / CSS2DRenderer 라벨 — 잔상 / Sandbox 충돌 / 모바일 viewport 문제로 단일 .tsx 코드 컴포넌트로 대체

Phase 4 — 알림 + 게이팅:
- `alert_dispatcher.py` — data_health/drift/trust 상태 변화 검출
- 룰: critical 즉시 / warning 1시간 누적 / ready→hold 즉시
- v2 PDF cron 진입 전 `check_release_gate()`:
  - hold → 차단 + 알림
  - manual_review → 진행 + 검수 알림
  - ready → 조용히 진행

### 27.3 Phase A — Brain 룰 이식 (배리티 브레인 투자 바이블)

PDF 9권 → 1권 통합 정리본 (`배리티 브레인 학습 도서/배리티_브레인_투자_바이블.pdf`, 13페이지). 출처: Lynch (2권) + Ackman (Pershing Square) + Druckenmiller + TCI Hohn + Rokos TCFD.

**룰 1 — Druckenmiller regime_weight (commit fd17367):**
`api/analyzers/multi_factor.py` 의 `RATE_ENV_MULTIPLIERS` 추가. bond_regime.rate_environment 따라 multi_factor 가중치 곱셈 보정:
- rate_low_accommodative (QE): macro 1.35× / flow 1.25× / fundamental 0.80×
- rate_normal: 중립 (1.0)
- rate_elevated (QT 시작): fundamental 1.20× / quality 1.20× / macro 0.85×
- rate_high_restrictive (QT 강): fundamental 1.35× / macro 0.70×

`compute_multi_factor_score(... bond_regime=...)` 시그니처 확장. `main.py` 4개 호출 위치에 portfolio.bonds.bond_regime 전달.

**룰 2 — Lynch PEG 승수 → graham_value (commit 7c89024):**
`_compute_graham_score` 에 PEG 보정 추가:
- PEG < 0.5 → +15 (tenbagger 후보)
- PEG < 1.0 → +8 (Lynch 표준 매력)
- PEG ≤ 2.0 → 중립
- PEG > 2.0 → -15 (Lynch 경고)

데이터 fallback: consensus.eps_growth_yoy_pct → eps_growth_qoq_pct → operating_profit_yoy_est_pct → revenue_growth.

**룰 3 — Hard Floor 강화 (commit 396aa5d):**
`_detect_red_flags` 의 auto_avoid (Hard Floor) 2개 추가:
- 유동비율 < 50% (한국 KIS) → "단기 운영 자금 부족" Lynch Turnaround 탈락
- PEG > 3.0 (한미 공통) → "Lynch 절대 매도", graham_value -15 위에 강제 AVOID floor

기존 Hard Floor 유지: 부채비율 300%+, FCF 음수+부채 80%+, VIX 35+ × 멀티팩터 50-, 위험 키워드, 공매도 5일 평균 15%+.

### 27.4 Lynch 6분류 — 한국 KOSPI/KOSDAQ 기준 (commit 9e99620)

`api/intelligence/lynch_classifier.py`. 한국 GDP 2026E 1.9% 기준 임계 확정값:

| 분류 | 임계 | 우선순위 |
|---|---|---|
| FAST_GROWER | 매출 YoY ≥ 15% + 시총 ≤ 5조 + 영업이익 양수 | 3 |
| STALWART | 매출 YoY 5~15% + 시총 ≥ 1조 | 4 |
| TURNAROUND | ROE<0 + op_margin>0 + revenue_growth>0 + 부채<300% | 1 (특수상황 우선) |
| CYCLICAL | sector keyword (철강/화학/조선/건설/해운/항공/반도체장비/정유) | 2 |
| ASSET_PLAY | PBR < 0.8 | 5 |
| SLOW_GROWER | 나머지 default | 6 |

분류 우선순위 (Turnaround → Cyclical → Fast → Stalwart → Asset → Slow) — 반등기 매출 급증 → Fast Grower 오분류 방지, Asset Play 의 저성장 → Slow Grower 오분류 방지.

`data_quality` 플래그 (revenue_growth/market_cap/operating_margin 핵심 데이터 누락 시 "low") + `portfolio.lynch_kr_distribution.low_quality_count` 별도 카운트.

### 27.5 Brain 진화 이력 자동 추적 (commit f044707)

`api/intelligence/brain_evolution.py` — git log 분석으로 commit 메시지의 prefix 자동 파싱:
- 추적: `feat|fix|perf|refactor (brain|observability|reports|estate)`
- portfolio["brain_evolution_log"] 에 최근 30개 attach
- AdminDashboard `CardBrainEvolution` 카드가 최근 8개 표시

memory `feedback_brain_evolution_admin_sync`: commit prefix 형식 의무 (자동 반영, 수동 reporting X).

### 27.6 Vercel 인프라 통합 (commits 97ef820 ~ 4ec0584 등)

estate_backend 별도 프로젝트 → vercel-api 단일 프로젝트로 흡수:
- `vercel-api/api/{stock, search, chat, watchgroups, order, chart, visitor_ping, admin, estate_*, landex_*, corp_probe, digest_publish_readiness}.py` 21 함수
- Hobby 12 함수 한도 → Pro 결제 (2026-04-28) → 250 한도
- admin 5 → 1 통합 (`api/admin.py` query param 라우터, `?type=brain_health|...`)
- vercel.json `ignoreCommand: git diff --quiet HEAD^ HEAD -- vercel-api/ requirements.txt` — cron 의 data push 자동 skip
- `scripts/vercel_deploy.sh` — CLI deploy 자동화

### 27.7 메모리 정책 추가 (4건)

- `feedback_continuous_evolution`: 잠금 폐기 + 4가드
- `project_brain_kb_learning`: PDF 9권 룰 이식 (RAG 아님), 통합본 메인
- `feedback_brain_evolution_admin_sync`: commit prefix 형식 의무
- `feedback_perplexity_collaboration`: 중요 결정 시 Perplexity 검증 질문 후보 동시 작성

### 27.8 검수 발견 3건 정정 (commit 4481855)

- 비정상 1: Lynch Turnaround proxy 약함 (단년 ROE 만) → revenue_growth>0 조건 추가
- 비정상 2: data_quality 누락 시 SLOW_GROWER 강제 → 통계 왜곡 → data_quality 플래그
- 비정상 3: has_critical 시 brain_score 보존이 명시 안 됨 → 코멘트 추가 (mean-reversion oversold 식별 의도)

### 27.9 테스트 커버리지

- 323/323 통과 (Phase A 후 기준, 2026-04-28)
- 신규: `tests/test_lynch_classifier.py` (18 cases)
- 기존: `tests/test_observability.py` (31), brain_feedback_loops 등

---

## 28) 2026-04-30 Sprint 11 — 자가진단 검수 + Trust 정확도

### 28.1 메타-검수 동기

Sprint 10 에서 깔린 자가진단 라인 (data_health / feature_drift / explainability / trust_score / alert_dispatcher / brain_evolution) 가 운영 11회 누적 후 메타-검수 시행. 결과: 라인은 살아있으나 **3개 P0 결함** 으로 신호 의미가 약화된 상태.

### 28.2 P0 결함 + Fix

**결함 1 — brain_evolution_log 디스크 미반영 (commit c33319c)**

quick / realtime 모드에서 `_attach_evo` + `_attach_lynch` 후 `save_portfolio` 호출 누락. full / full_us 모드는 4068 라인의 observability save 에서 보존되지만, quick / realtime 은 in-memory 만 갱신되고 디스크에 안 떨어짐.

→ `api/main.py:4055` 직전에 `if mode not in ("full", "full_us"): save_portfolio(portfolio)` 추가. 진단 print `🧬 Brain 진화 이력: N건` 보강.

**결함 2 — brain_distribution_normal silent PASS (commit c33319c)**

`trust_score._check_brain_distribution` 가 `r.get("grade")` 사용. 실제 grade 위치는 `r.verity_brain.grade` (top-level r.grade 는 항상 None). → grades 리스트 항상 비어 → "grade 미부여 — 첫 분석 단계" 분기로 무조건 PASS.

→ `(r.get("verity_brain") or {}).get("grade")` 로 정정. grade 미부여 시 PASS 대신 FAIL ("측정 불가, brain 산출 점검 필요").

**결함 3 — Drift cry-wolf (commit a0fac4c)**

`feature_drift.compute_drift` 의 룰: 단일 feature critical 1개로 overall 자동 critical 승격. 운영 측정: **11회 중 8회 critical, overall_score=0.0934** (PSI_OK=0.1 미만). mood_score 같은 변동 큰 매크로가 trust verdict 를 만성 manual_review 로 묶음.

→ 새 룰: `critical 비율 ≥ 50% OR overall ≥ PSI_WARN(0.2)` 일 때만 overall critical. 단발 critical 은 warning 으로만 격상 (silent 통과는 방지). 결과 dict 에 `critical_count` 필드 추가.

### 28.3 P1 부수 개선

**Per-source freshness 정확도 (commit 8424bdf)**: data_health 가 모든 소스에 portfolio.updated_at 단일 freshness 사용 → `system_health.checked_at` (probe 실행 시각) 으로 변경. probe 와 portfolio 저장 시각이 다른 케이스에서 source-alive 신호 정확.

**Spec docstring 정정 (commit c33319c)**: trust_score 모듈 docstring 의 `data_freshness < 30분` 명시가 실측 임계 (`TRUST_FRESHNESS_MAX_MIN=1440분`)와 47.5× 차이. drift no_baseline 자동 PASS / pipeline_cron 24h 임계 / deadman warning 통과 등 실측 동작 명시.

**extract_features grade 위치 정합 (commit a0fac4c)**: feature_drift 의 `grade_distribution_buy_pct` 추출도 verity_brain.grade 사용으로 통일. drift baseline 에 grade 분포 변화가 실제로 포함됨.

### 28.4 운영 데이터 변경

- `data/metadata/data_health.jsonl` 첫 빈 라인 정리
- `data/estate_action_log.json` 15개 done 처리 (commit 7bf0fb4) — 남은 활성: scheduled 1 (2026-05-07 운영 점검), pending 2 (DigestPublishPanel 별도 세션 + Gemini 캐시 검증 5/3)

### 28.5 검증 routine

2026-04-30 21:15 KST 자동 실행 (`trig_01QQCfkjeRgjn8AfRY8D56nj`, claude.ai/code/routines). 다음 cron 의 portfolio.json fetch → 3 체크:
1. brain_evolution_log 길이 > 0
2. lynch_kr_distribution.SLOW_GROWER pct ≈ 61.5% (이전 71.2%)
3. observability.trust.conditions.brain_distribution_normal detail 이 'BUY+' 형식 (silent PASS 종료 검증)

### 28.6 메모리 정책 추가/갱신

- `feedback_metavalidation_decompose`: 메타-검증 verdict 는 요소별 분해 + 시간차 baseline 둘 다. 종합값 단일 신뢰 금지
- `project_estate_backtest_methodology`: ESTATE 백테스트 v0 합의 (3자 LLM + 메타-검증, D 산식 v1.1)

### 28.7 테스트

- 49/49 통과 (2026-04-30): `test_observability.py` (31) + `test_metadata.py` (18)
- fixture 의 recommendations 에 `verity_brain` 추가 (prod 형태와 정합)

---

---

## 29) 2026-04-30 Sprint 11 후반 — 베테랑 due diligence + 인프라 분리

### 29.1 베테랑 due diligence 평가 수령

월스트리트 PM 관점 due diligence 보고 (외부 LLM 평가 + 사용자 전달). 7개 구조적
결함 지적, "기관급 인프라 + 리테일급 의사결정 게이트" 평가. **기능 추가가 아니라
판단 정밀도** 우선 강조.

7개 결함:
- P0 결함 1: backtest=forward tracking — survivorship/slippage/look-ahead 부재
- P0 결함 2: Brain Score 가중치 임의성 — Graham/CANSLIM 충돌, OOS 미검증
- P0 결함 3: Position sizing 거칠다 — ATR 부재, 종목 변동성 무시
- P1 결함 4: correlation 무시 — sector 한도만, factor exposure 한도 부재
- P1 결함 5: Sentiment 30% 과대 — alpha decay 1-3일 인 것 고려 시 timing_signal 분리 필요
- P1 결함 6: Regime detection 후행적 — leading indicator 부재
- P2 결함 7: UI 행동 유도 약함 — "오늘의 액션 3개" 단일 카드 부재

### 29.2 결함 1 대응 — backtest 무결성 (commit 64d7e42)

`api/intelligence/backtest_archive.py`:
- Survivorship bias: `today_snap` 에 없는 ticker (상장폐지/거래정지) 자동 제외 →
  보수 -50% 처리 + delisted_count 별도 집계
- Slippage 모델 (시총 tier): ≥10조 0.1% / ≥1조 0.3% / <1조 0.7% 왕복
- TX cost: VAMS 일치 0.03% (수수료 0.015% × 2)

Dual-track 노출 (호환성 보존):
- `hit_rate` / `avg_return` / `sharpe` (gross) — 기존 키 유지, 비교 추세 보존
- `hit_rate_net` / `avg_return_net` (net) — 보정 후, 실거래 근사
- `_corrections_meta` — 가정·한계 명시 (audit trail)

남은 한계: look-ahead bias 검증 별도 (rec_price 가 추천 시점 종가 vs T+1 시가 차이 미보정).

### 29.3 결함 6 대응 — Regime leading indicator (commit c5ec057)

`api/intelligence/strategy_evolver._classify_regime`. 기존 5개 trailing 시그널에
3개 leading 시그널 추가:
- Yield curve slope (2y10y): 침체 6-18개월 선행. 음수=강신호 -2, <0.5=-1, ≥1.0=+1
- Copper/Gold ratio: risk-on/off 빠른 신호. 변화율 차이 ±1pp
- HY spread (option): 5%+ stress, <3% 안정 (현재 미수집, 수집 시 자동 활용)

핵심 신규: `portfolio.regime_diagnostics` 분해 노출
- `trailing_score` / `leading_score` / `divergence_warning` (|diff| ≥ 0.5)
- divergence_warning=True 가 regime 전환 임박 신호 (트레일링 bull / 리딩 bear 등)

### 29.4 결함 2 대응 — Graham vs CANSLIM regime switching (commit 353609e)

`api/intelligence/verity_brain._compute_fact_score`. regime_diagnostics 활용해
Graham (가치) vs CANSLIM (성장) 가중치 동적 조정:
- bull (regime > 0.3): CANSLIM 1.5× / Graham 0.5× — 성장 우세
- bear (regime < -0.3): Graham 1.5× / CANSLIM 0.5× — 가치 우세
- mixed: 기본 가중치
- leading 신호에 1.5× 가중 (선행 우선)

`result["regime_weighting"]` 에 audit 메타 첨부.

남은 한계: 0.7/0.3 (fact vs sentiment) 의 OOS 검증 근거 여전히 부재 — 다음 sprint
에서 cross-validation 기반 가중치 탐색.

### 29.5 결함 3 대응 — VAMS 변동성 sizing (commit 48187e6)

`api/vams/engine._apply_volatility_adj`. ATR 직접 수집 전 임시로
`prediction.top_features.volatility_20d` (이미 ML 산출) proxy 사용.

Tier 기반 multiplier:
- ≤15% (저변동): 1.0× (KOSPI 대형주)
- ≤30% (중): 0.85× (15% 축소)
- >30% (고): 0.70× (30% 축소, 작전주/페니)

execute_buy 의 `_apply_half_kelly` 직후 호출. holding 에 `volatility_adj` audit 첨부.

남은 한계: ATR_14d 직접 수집 + target_risk_per_trade 명시 산식 (`size = target_risk × portfolio_value / (ATR × multiplier)`) — 다음 sprint.

### 29.6 결함 4 대응 — VAMS factor tilt 한도 (commit 4295bf9)

`api/vams/engine._check_portfolio_exposure`. sector 한도 외에 factor 노출 한도 신규.

`VAMS_MAX_FACTOR_TILT_PCT` (default 60%): momentum/quality/volatility/mean_reversion
4개 quant factor 중 한 factor 에 holdings 의 60% 이상이 같은 방향 (≥70 high 또는
≤30 low) 으로 쏠리면 매수 차단.

남은 한계: 연속 score 가중 합산 (cutoff 70/30 보다 정확) + cross-asset correlation
matrix — 다음 sprint.

### 29.7 결함 5/7 1단계 대응 (commit 10379c6/4aa9b0e)

**결함 5 (Sentiment 30% 과대) — env override 도입**:
  `_get_brain_weights` 에 `BRAIN_FACT_WEIGHT_OVERRIDE` /
  `BRAIN_SENTIMENT_WEIGHT_OVERRIDE` 환경변수 처리 추가. Constitution default
  (0.7/0.3) 무시하고 임의 비율 적용 가능. 베테랑 권고 (0.85/0.15) 점진 시험 →
  운영 비교 → default 갱신. retail group cap 20% (§1-C) 가 보조 방어.
  남은 한계: sentiment 의 timing_signal 분리 (architectural) 다음 sprint.

**결함 7 (UI 행동 유도) — daily_actions backend**:
  신규 모듈 `api/intelligence/daily_actions.py`. portfolio.daily_actions 에
  BUY 1 / SELL 1 / WATCH 1 추출.
  - BUY: STRONG_BUY/BUY + 보유 X + brain_score 최고
  - SELL: 보유 중 return_pct 최저, 단 -3% 미만일 때만 (정상 노이즈는 hold 유지)
  - WATCH: brain_score 55-69 + 보유 X (BUY 직전 영역)
  main.py attach 단계에서 호출 (Lynch 직후). 사용자 작업: Framer 'TodayActionsCard'
  컴포넌트 신설 + apiUrl prop.

### 29.8 인프라 분리 — gh-pages dual-write (commit ee8cca9 + 7008a9d)

베테랑 권고 옵션 D-1 채택 — main 의 commit storm 차단.

Phase A (현재 적용): 매 cron 변경 산출물 (portfolio.json + recommendations.json
+ consensus_data.json) 을 gh-pages 브랜치 force-orphan push (peaceiris/actions-
gh-pages@v4 + force_orphan=true → 매번 single commit).

5개 워크플로 publish: daily_analysis / daily_analysis_full / bond_etf / export_trade
/ reports_v2 (verity-data-write 그룹). rss_scout / scout_penny / kis_token_refresh
는 portfolio 미관련이라 skip.

Phase B (URL 마이그레이션 적용): Framer 41 컴포넌트 + Vercel API 3 파일의 raw URL
`/main/data/*` → `/gh-pages/*`. dual-write 살아있어 main URL fetch fallback 가능
(점진 마이그레이션 안전).

Phase C (보류 — Framer republish 완료 후): main 의 산출물 3개 .gitignore + workflow
git add 에서 제외. 이때 main commit 빈도 60/day → ~10/day (history archive +
metadata jsonl 만).

### 29.9 운영 데이터 변경

- `data/estate_action_log.json`: Framer 컴포넌트 41개 republish 1건 추가
- `.github/actions/publish-data/action.yml`: composite action 신설

### 29.10 테스트 커버리지

Sprint 11 신규: 35 cases
- test_backtest_corrections.py (10): slippage tier / 산식
- test_regime_leading_indicators.py (11): yield/copper-gold / divergence
- test_brain_regime_weighting.py (6): bull/bear/mixed/leading 가중
- test_vams_volatility_sizing.py (10): tier / edge cases
- test_vams_factor_tilt.py (5): factor 분산 한도

전체: 389 cases 통과 (estate landex 별개 4건 fail — Python 3.12 vs 3.9 env mismatch
의심, estate 작업 잔여로 별도 fix).

### 29.11 다음 sprint 권고

베테랑 4주 스프린트 권고 중 1/6/2/3/4 부분 대응. 다음:
- 결함 1 후속: look-ahead bias 검증 (rec_price 가 T+1 시가 보정)
- 결함 5: sentiment → timing_signal 분리 (architectural)
- 결함 7: "오늘의 액션 3개" 카드
- 결함 2 후속: cross-validation 기반 가중치 OOS 탐색
- 결함 4 후속: cross-asset correlation matrix

---

문서 끝. (v3.5 — Sprint 11 후반 베테랑 due diligence 5건 대응 + gh-pages 인프라 분리 추가)

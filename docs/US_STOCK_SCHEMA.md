# US 종목 portfolio.json 스키마 확장

`portfolio.json`의 `recommendations[]` 배열 내 US 종목(`currency: "USD"`)에 추가되는 키 목록.

## 기존 공통 키 (KR/US 모두)

```
ticker, name, price, market, currency, market_cap, trading_value,
per, pbr, div_yield, debt_ratio, operating_margin, roe,
drop_from_high_pct, technical, sentiment, multi_factor, prediction,
backtest, verity_brain, recommendation, ai_verdict, confidence,
gold_insight, silver_insight, risk_flags
```

## US 전용 추가 키

### Finnhub (`api/collectors/finnhub_client.py`)

| 키 | 타입 | 설명 |
|---|---|---|
| `analyst_consensus` | `object` | 애널리스트 추천 요약 |
| `.buy` | `int` | 매수(+강매수) 수 |
| `.hold` | `int` | 보유 수 |
| `.sell` | `int` | 매도(+강매도) 수 |
| `.target_mean` | `float` | 평균 목표가 ($) |
| `.target_high` | `float` | 최고 목표가 ($) |
| `.target_low` | `float` | 최저 목표가 ($) |
| `.upside_pct` | `float` | 현재가 대비 업사이드 (%) |
| `earnings_surprises` | `list[object]` | 최근 4분기 실적 서프라이즈 |
| `[].period` | `str` | 분기 (예: "2025-Q4") |
| `[].actual` | `float` | 실제 EPS |
| `[].estimate` | `float` | 예상 EPS |
| `[].surprise_pct` | `float` | 서프라이즈 (%) |
| `insider_sentiment` | `object` | 내부자 거래 심리 (90일) |
| `.mspr` | `float` | Monthly Share Purchase Ratio |
| `.positive_count` | `int` | 순매수 월수 |
| `.negative_count` | `int` | 순매도 월수 |
| `.net_shares` | `int` | 순매수/매도 주식수 |
| `institutional_ownership` | `object` | 기관 보유 현황 |
| `.total_holders` | `int` | 기관 수 |
| `.total_shares` | `int` | 총 보유 주식수 |
| `.change_pct` | `float` | 보유 변동률 (%) |

### SEC EDGAR (`api/collectors/sec_edgar.py`)

| 키 | 타입 | 설명 |
|---|---|---|
| `sec_filings` | `list[object]` | 최근 공시 목록 |
| `[].form_type` | `str` | 10-K, 10-Q, 8-K 등 |
| `[].filed_date` | `str` | 제출일 |
| `[].description` | `str` | 공시 설명 |
| `[].url` | `str` | SEC 링크 |
| `sec_financials` | `object` | XBRL 추출 핵심 재무 |
| `.fcf` | `float?` | Free Cash Flow ($) |
| `.net_income` | `float?` | 순이익 ($) |
| `.revenue` | `float?` | 매출 ($) |
| `.operating_income` | `float?` | 영업이익 ($) |
| `.total_debt` | `float?` | 총 부채 ($) |
| `.total_equity` | `float?` | 자기자본 ($) |
| `.debt_ratio` | `float?` | 부채비율 (%) |

### Polygon.io (`api/collectors/polygon_client.py`)

| 키 | 타입 | 설명 |
|---|---|---|
| `options_flow` | `object` | 옵션 시장 개요 |
| `.put_call_ratio` | `float?` | Put/Call 비율 |
| `.total_oi` | `int` | 총 미결제약정 |
| `.avg_iv` | `float?` | 평균 내재변동성 (%) |
| `.iv_percentile` | `float?` | IV 백분위 |
| `.total_volume` | `int` | 총 거래량 |
| `short_interest` | `object` | 공매도 정보 |
| `.short_pct` | `float?` | 공매도 비율 (%) |
| `.days_to_cover` | `float?` | 커버 소요일 |
| `.short_ratio` | `float?` | Short Ratio |

### NewsAPI (`api/collectors/newsapi_client.py`)

NewsAPI 결과는 `sentiment.detail[]`에 병합됨:

| 키 | 타입 | 설명 |
|---|---|---|
| `sentiment.detail[].source` | `str` | 뉴스 매체명 |
| `sentiment.detail[].description` | `str` | 본문 snippet (최대 300자) |

## 공통 추가 키 (v8.3+)

### `company_type` (KR/US 공통)

| 키 | 타입 | 설명 |
|---|---|---|
| `company_type` | `string?` | 업종 한글 라벨 (예: "반도체", "IT/기술", "건설") |

yfinance `info.sector`/`info.industry` 기반 자동 생성. 매핑 실패 시 빈 문자열.

### `group_structure.major_shareholders` (KR 우선, US 미지원)

| 키 | 타입 | 설명 |
|---|---|---|
| `major_shareholders` | `list[object]` | 상위 5대주주 목록 |
| `[].name` | `string` | 주주명 |
| `[].relate` | `string` | 관계 (최대주주, 특수관계인 등) |
| `[].ownership_pct` | `float` | 지분율 (%) |
| `[].symbol` | `string?` | 상장사 종목코드 (없으면 null) |
| `[].ticker_yf` | `string?` | yfinance 티커 |
| `[].market_cap` | `float?` | 시가총액(억원) |
| `[].links` | `object` | 외부 링크 (best-effort) |
| `[].links.official` | `string?` | 공식 사이트/네이버 금융 |
| `[].links.namuwiki` | `string?` | 나무위키 검색 링크 |
| `[].links.profile` | `string?` | DART 기업 프로필 |

`subsidiaries[]`에도 동일한 `links` 구조 추가.

## Brain 영향

- `verity_brain._detect_red_flags`: SEC FCF 음수 + 부채비율 → auto_avoid / downgrade
- `verity_brain._export_to_score`: 내부자 MSPR, 기관 변동, 애널리스트 비율로 수급 점수 산출
- `verity_brain._detect_red_flags`: P/C ratio > 1.5 → 약세 옵션 시그널, IV > 80 → 고변동성 경고
- `verity_brain._compute_group_structure_bonus`: 대주주 집중도 + NAV 할인율 → Brain Score 보정 (최대 ±5점)

## Gemini 프롬프트

US 종목 분석 시 `[수급 — Finnhub/SEC]` 블록에 위 데이터가 자동 삽입됨.
KR 종목의 `[지분구조]` 블록에 대주주/NAV/자회사 요약이 자동 삽입됨.

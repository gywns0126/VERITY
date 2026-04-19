# VERITY_MODE — 환경 분기 가이드

## 개요

`VERITY_MODE` 환경변수 하나로 AI API(Gemini/Claude/Perplexity) 및 유료 데이터 수집기(Finnhub/Polygon/NewsAPI) 호출을 mock/실호출로 분기합니다.

| 모드 | 언제 | AI API 호출 | 유료 데이터 | 비용 |
|---|---|---|---|---|
| `dev` (기본값) | 기능 개발/테스트 | 전부 mock | 전부 mock | 거의 0 |
| `staging` | 구조 검증/최종 확인 | allowlist만 실호출 | 전부 mock | 중간 |
| `prod` | GitHub Actions 실운용 | 전부 실호출 | 전부 실호출 | 정상 |

## 설정 방법

### .env 파일

```bash
VERITY_MODE=dev
# staging에서 실호출할 키 (쉼표 구분)
VERITY_STAGING_REAL_KEYS=gemini.daily_report,gemini.periodic_report
```

### 커맨드라인 실행

```bash
# dev 모드 (기본값, 생략 가능)
python -m api.main --mode full

# staging — 일일 리포트만 실호출
VERITY_MODE=staging VERITY_STAGING_REAL_KEYS="gemini.daily_report" python -m api.main --mode full

# prod — 전부 실호출
VERITY_MODE=prod python -m api.main --mode full
```

### GitHub Actions

`GITHUB_ACTIONS=true` 환경에서는 **VERITY_MODE 설정과 무관하게 자동으로 `prod`**가 됩니다.
실수로 dev가 섞여 mock 리포트가 배포되는 사고를 방지합니다.

## Mock 키 목록

### AI API (Gemini)
| 키 | 적용 함수 |
|---|---|
| `gemini.stock_analysis` | `analyze_stock()` |
| `gemini.daily_report` | `generate_daily_report()` |
| `gemini.periodic_report` | `generate_periodic_report()` |
| `gemini.batch_analysis` | `analyze_batch()` |
| `gemini.reanalyze_pro` | `reanalyze_top_n_pro()` |
| `gemini.tail_risk` | `maybe_send_tail_risk_digest()` |
| `gemini.chat` | `chat_engine.ask()` |
| `gemini.facilities_parse` | `parse_business_facilities()` |
| `gemini.properties_parse` | `parse_10k_properties()` |
| `gemini.hscode_mapper` | `map_stocks_to_hscode_batch()` |
| `gemini.commodity_narrator` | `enrich_commodity_impact_narratives()` |
| `gemini.commodity_sector_map` | `build_sector_commodity_map_gemini()` |

### AI API (Claude)
| 키 | 적용 함수 |
|---|---|
| `claude.deep` | `analyze_stock_deep()` |
| `claude.batch_deep` | `analyze_batch_deep()` |
| `claude.light` | `analyze_stock_light()` |
| `claude.batch_light` | `analyze_batch_light()` |
| `claude.emergency` | `analyze_stock_emergency()` |
| `claude.verify_tail_risk` | `verify_tail_risk()` |
| `claude.morning_strategy` | `generate_morning_strategy()` |
| `claude.brain_drift` | `check_brain_drift()` |
| `claude.postmortem` | `generate_postmortem()` |
| `claude.strategy_evolution` | `propose_evolution()` |

### AI API (Perplexity)
| 키 | 적용 함수 |
|---|---|
| `perplexity.sonar` | `call_perplexity()` |
| `perplexity.macro_event` | `research_macro_event()` |
| `perplexity.earnings` | `research_earnings()` |
| `perplexity.stock_risk` | `research_stock_risk()` |
| `perplexity.quarterly_research` | `run_quarterly_research()` |

### 유료 데이터 수집기
| 키 | 적용 함수 |
|---|---|
| `finnhub.analyst_consensus` | `get_analyst_consensus()` |
| `finnhub.earnings_surprises` | `get_earnings_surprises()` |
| `finnhub.insider_sentiment` | `get_insider_sentiment()` |
| `finnhub.institutional_ownership` | `get_institutional_ownership()` |
| `finnhub.peer_companies` | `get_peer_companies()` |
| `finnhub.basic_financials` | `get_basic_financials()` |
| `finnhub.company_news` | `get_company_news()` |
| `polygon.options_flow` | `get_options_flow()` |
| `polygon.short_interest` | `get_short_interest()` |
| `polygon.pre_after_market` | `get_pre_after_market()` |
| `newsapi.us_stock_news` | `get_us_stock_news()` |
| `newsapi.market_news` | `get_market_news()` |

## Mock 데이터 우선순위

1. **Trace Replay** — `data/runs/` 아카이브에서 key별 최근 성공 응답 재생 (가장 현실적)
2. **Fixture Fallback** — `api/mocks/fixtures.py`의 하드코딩 최소 구조
3. **Empty Dict** — 위 둘 다 없을 때 `{}` 반환

## 안전장치

- **CI 강제 prod**: `GITHUB_ACTIONS=true`이면 VERITY_MODE 설정 무시, 무조건 prod
- **Mock 메타데이터**: mock 반환에 `model_used="mock"` 등이 포함되어 식별 가능
- **파일 분리**: 비-prod 모드에서는 `portfolio.dev.json`에 저장 → 실운용 데이터 오염 방지
- **시작 배너**: main.py 실행 시 현재 VERITY_MODE가 콘솔에 출력됨

## 무료 API (mock 대상 아님)

다음 API는 VERITY_MODE와 무관하게 **항상 실호출**됩니다:
- FRED (거시 지표)
- DART (한국 공시)
- KRX (한국 시장 데이터)
- 공공데이터 포털
- yfinance
- ECOS (한국은행)

import os
from datetime import datetime, timezone, timedelta
from typing import FrozenSet, Optional
from dotenv import load_dotenv

load_dotenv()

KST = timezone(timedelta(hours=9))


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)

# ── VERITY_MODE: dev(mock) / staging(선택적 실호출) / prod(전부 실호출) ──
_raw_mode = os.getenv("VERITY_MODE", "dev").strip().lower()
if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
    VERITY_MODE = "prod"
else:
    VERITY_MODE = _raw_mode if _raw_mode in ("dev", "staging", "prod") else "dev"

VERITY_STAGING_REAL_KEYS: FrozenSet[str] = frozenset(
    k.strip() for k in os.getenv(
        "VERITY_STAGING_REAL_KEYS",
        "gemini.daily_report,gemini.periodic_report",
    ).split(",") if k.strip()
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# gemini-2.0-flash* 는 신규 키에서 404 — 기본은 2.5 Flash (환경변수 GEMINI_MODEL 로 덮어쓰기)
# preflight MIN-1: 이중 `or` fallback 단순화. 빈 문자열·미설정 env 모두 기본값으로 폴백.
_GEMINI_FLASH_FALLBACK = "gemini-2.5-flash"
_GEMINI_PRO_FALLBACK = "gemini-2.5-pro"
GEMINI_MODEL = (os.environ.get("GEMINI_MODEL") or _GEMINI_FLASH_FALLBACK).strip()

# ── Gemini 하이브리드 라우팅: 대량 배치=Flash, 핵심 구간=Pro ──
GEMINI_MODEL_DEFAULT = (os.environ.get("GEMINI_MODEL_DEFAULT") or GEMINI_MODEL).strip()
GEMINI_MODEL_CRITICAL = (os.environ.get("GEMINI_MODEL_CRITICAL") or _GEMINI_PRO_FALLBACK).strip()
GEMINI_PRO_ENABLE = os.environ.get("GEMINI_PRO_ENABLE", "1").strip().lower() in ("1", "true", "yes", "on")
GEMINI_CRITICAL_TOP_N = _env_int("GEMINI_CRITICAL_TOP_N", 3)
# 챗 엔진 전용 — 단순 Q&A 는 Flash-Lite (Flash 대비 약 50% 비용)
GEMINI_MODEL_CHAT = (os.environ.get("GEMINI_MODEL_CHAT") or "gemini-2.5-flash-lite").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Claude 하이브리드 라우팅: 경량=Haiku, 범용=Sonnet, 전략=Opus ──
CLAUDE_MODEL_LIGHT = (os.environ.get("CLAUDE_MODEL_LIGHT", "claude-haiku-4-5") or "claude-haiku-4-5").strip()
CLAUDE_MODEL_DEFAULT = (os.environ.get("CLAUDE_MODEL_DEFAULT", "claude-sonnet-4-6") or "claude-sonnet-4-6").strip()
CLAUDE_MODEL_HEAVY = (os.environ.get("CLAUDE_MODEL_HEAVY", "claude-opus-4-7") or "claude-opus-4-7").strip()
CLAUDE_OPUS_ENABLE = os.environ.get("CLAUDE_OPUS_ENABLE", "1").strip().lower() in ("1", "true", "yes", "on")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── ESTATE 외부 API (LANDEX 점수 산출용) ──
# 주의: PUBLIC_DATA_API_KEY (line 122 에 정의) 가 정식 이름. 이전 PUBLICDATA_API_KEY
#       변수는 import 어디서도 안 했고 ESTATE 분리로 인해 dead code 였음 (2026-04-26 제거).
ECOS_API_KEY = os.environ.get("ECOS_API_KEY", "")                # 한국은행 ECOS
SEOUL_DATA_API_KEY = os.environ.get("SEOUL_DATA_API_KEY", "")    # 서울 열린데이터 일반
SEOUL_SUBWAY_API_KEY = os.environ.get("SEOUL_SUBWAY_API_KEY", "") # 서울 지하철 (별도 키)
KOSIS_API_KEY = os.environ.get("KOSIS_API_KEY", "")              # 국가통계포털


def _parse_telegram_allowed_chat_ids() -> Optional[FrozenSet[int]]:
    """쉼표 구분 chat_id. 비어 있으면 필터 없음(기존 동작). 설정 시 해당 ID만 봇 응답."""
    raw = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        return None
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            pass
    return frozenset(ids) if ids else None


TELEGRAM_ALLOWED_CHAT_IDS = _parse_telegram_allowed_chat_ids()


def _parse_telegram_admin_chat_ids() -> Optional[FrozenSet[int]]:
    """상태변경 명령(/approve_strategy, /rollback_strategy 등) 허용 chat_id.
    미설정 시 None → telegram_bot의 admin 게이트가 fail-closed로 작동."""
    raw = os.environ.get("TELEGRAM_ADMIN_CHAT_IDS", "").strip()
    if not raw:
        return None
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            pass
    return frozenset(ids) if ids else None


TELEGRAM_ADMIN_CHAT_IDS = _parse_telegram_admin_chat_ids()
DART_API_KEY = os.environ.get("DART_API_KEY", "")
# FRED — https://fredaccount.stlouisfed.org/apikeys
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
# 한국은행 ECOS — https://ecos.bok.or.kr/api/
ECOS_API_KEY = os.environ.get("ECOS_API_KEY", "")
# 미 10년물(DGS10) 이 값 이상이면 브레인 등급 관망 상한·현금 확대 권고(기본 4.5%)
MACRO_DGS10_DEFENSE_PCT = _env_float("MACRO_DGS10_DEFENSE_PCT", 4.5)
# 공공데이터포털 — 관세청 품목별·국가별 수출입실적(getNitemtradeList 등) 활용신청 후 발급
PUBLIC_DATA_API_KEY = os.environ.get("PUBLIC_DATA_API_KEY", "")
# KRX Data Marketplace OPEN API — 인증키 + API별 이용신청 필요 (docs/KRX_OPEN_API_SETUP.md)
KRX_API_KEY = (os.environ.get("KRX_API_KEY", "") or os.environ.get("KRX_OPENAPI_KEY", "")).strip()
# 관세청 API: 1차 조회 국가코드(기본 ZZ=전체), 2차는 전월비 급증 시에만 SURGE_COUNTRIES
CUSTOMS_TRADE_BASE_CNTY = os.environ.get("CUSTOMS_TRADE_BASE_CNTY", "ZZ").strip().upper() or "ZZ"
CUSTOMS_TRADE_SURGE_COUNTRIES = os.environ.get(
    "CUSTOMS_TRADE_SURGE_COUNTRIES",
    "CN,US,VN",
)
# 전월 대비 수출액(%)이 이 값 이상이면 CN·US·VN 세부 조회
CUSTOMS_TRADE_SURGE_MOM_PCT = _env_float("CUSTOMS_TRADE_SURGE_MOM_PCT", 15.0)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
RECOMMENDATIONS_PATH = os.path.join(DATA_DIR, "recommendations.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
TRADE_ANALYSIS_PATH = os.path.join(DATA_DIR, "trade_analysis.json")
CONSENSUS_DATA_PATH = os.path.join(DATA_DIR, "consensus_data.json")
HSCODE_MAPPING_PATH = os.path.join(DATA_DIR, "hscode_mapping.json")
VALUE_CHAIN_MAP_PATH = os.path.join(DATA_DIR, "value_chain_map.json")
CHAIN_SNIPPETS_PATH = os.path.join(DATA_DIR, "chain_snippets.json")
COMMODITY_IMPACT_PATH = os.path.join(DATA_DIR, "commodity_impact.json")
COMMODITY_MAP_CACHE_PATH = os.path.join(DATA_DIR, "commodity_sector_map_cache.json")
STRATEGY_REGISTRY_PATH = os.path.join(DATA_DIR, "strategy_registry.json")
# 원자재 스카우트: 기본은 full 모드만. quick에서도 yfinance 상관·마진 반영하려면 1
_COMMODITY_Q = os.environ.get("COMMODITY_SCOUT_IN_QUICK", "").strip().lower()
COMMODITY_SCOUT_IN_QUICK = _COMMODITY_Q in ("1", "true", "yes", "on")
# quick에서 스카우트는 켰는데 Gemini 서술까지 쓰려면 1 (미설정 시 full에서만 서술)
_COMMODITY_NQ = os.environ.get("COMMODITY_NARRATIVE_IN_QUICK", "").strip().lower()
COMMODITY_NARRATIVE_IN_QUICK = _COMMODITY_NQ in ("1", "true", "yes", "on")

VAMS_INITIAL_CASH = max(1, _env_int("VAMS_INITIAL_CASH", 10_000_000))
VAMS_COMMISSION_RATE = 0.00015
VAMS_ACTIVE_PROFILE: str = os.environ.get("VAMS_ACTIVE_PROFILE", "moderate").strip()

# VAMS 실매매 보정 — VAMS 본체는 수수료·시장충격 슬리피지(impact_coeff_bps≈30)까지 반영.
# compute_adjusted_return()이 아래를 추가 차감해 실매매 추정 수익률을 계산한다.
#
# 세율 분기 (종목 타입별):
#   · KR 일반주: 매도 시 증권거래세 부과 (아래 KR_STOCK 세율)
#   · KR ETF   : 증권거래세 면제 (매매차익은 배당소득세)
#   · US 주식/ETF: 증권거래세 없음 (양도세 22%는 별도, 연 250만 초과분만 — 현 보정에선 제외)
VAMS_SELL_TAX_KR_STOCK = _env_float("VAMS_SELL_TAX_KR_STOCK", 0.0018)   # KR 일반주 매도세
VAMS_SELL_TAX_KR_ETF = _env_float("VAMS_SELL_TAX_KR_ETF", 0.0)          # KR ETF 면제
VAMS_SELL_TAX_US = _env_float("VAMS_SELL_TAX_US", 0.0)                  # US 거래세 (SEC fee 무시 수준)
VAMS_SELL_TAX_RATE = VAMS_SELL_TAX_KR_STOCK  # 하위 호환 별칭 (기존 코드가 참조하던 이름)

# 호가 스프레드: VAMS 시장충격(30bp)과 중복되지 않도록 보수적 5bp 왕복 (≈0.05%).
# 대형주 기준. 중소형주·저유동성 종목 비중 높으면 10~15bp까지 상향 권장.
VAMS_SPREAD_SLIPPAGE_BPS = _env_float("VAMS_SPREAD_SLIPPAGE_BPS", 5)
VAMS_DIVIDEND_TAX_RATE = _env_float("VAMS_DIVIDEND_TAX_RATE", 0.154)    # 배당소득세 (분리과세 15.4%)

# VAMS 검증 판정 기준 — 실거래 전환 전 체크포인트(3·6·12개월)에서 사용.
# 결과 본 뒤 기준 움직이면 confirmation bias. 변경은 git 커밋으로 이력 남길 것.
# 공식 판정 시작일. "YYYY-MM-DD" 포맷. 빈값이면 모든 데이터 사용(=비활성).
# 이 날짜 이전의 스냅샷·매매는 validation_report 계산에서 자동 제외된다.
# compute_adjusted_return은 VAMS total_asset과의 일관성을 위해 필터링하지 않음.
VAMS_VALIDATION_START_DATE: str = os.environ.get("VAMS_VALIDATION_START_DATE", "").strip()
VAMS_VALIDATION_MIN_DAYS = _env_int("VAMS_VALIDATION_MIN_DAYS", 60)              # 최소 거래일 (≈3개월)
VAMS_VALIDATION_MIN_TRADES = _env_int("VAMS_VALIDATION_MIN_TRADES", 20)          # 최소 완료 매매 건수
VAMS_PASS_EXCESS_RETURN_PP = _env_float("VAMS_PASS_EXCESS_RETURN_PP", 0.0)       # 벤치마크 대비 초과수익 (%p)
VAMS_PASS_MDD_RATIO = _env_float("VAMS_PASS_MDD_RATIO", 1.0)                     # |VAMS MDD| / |벤치 MDD| 상한
VAMS_PASS_WIN_RATE = _env_float("VAMS_PASS_WIN_RATE", 0.55)                      # 승률 하한 (55%)
VAMS_PASS_PROFIT_LOSS_RATIO = _env_float("VAMS_PASS_PROFIT_LOSS_RATIO", 1.5)     # 평균수익 / 평균손실 하한
VAMS_PASS_SHARPE = _env_float("VAMS_PASS_SHARPE", 1.0)                           # 샤프 통과선 (연율)
VAMS_REDESIGN_SHARPE = _env_float("VAMS_REDESIGN_SHARPE", 0.5)                   # 미만이면 FAIL(재설계)
VAMS_REGIME_DRAWDOWN_PCT = _env_float("VAMS_REGIME_DRAWDOWN_PCT", 10.0)          # 벤치마크 조정 감지선 (%)

# V6: 포트폴리오 레벨 리스크 제어
VAMS_KELLY_SCALE = _env_float("VAMS_KELLY_SCALE", 0.5)
VAMS_MAX_SECTOR_PCT = _env_float("VAMS_MAX_SECTOR_PCT", 35.0)
VAMS_MAX_PORTFOLIO_BETA = _env_float("VAMS_MAX_PORTFOLIO_BETA", 1.5)
VAMS_MAX_SINGLE_THEME_PCT = _env_float("VAMS_MAX_SINGLE_THEME_PCT", 40.0)
# Sprint 11 결함 4 (베테랑 due diligence): 단일 quant factor 쏠림 한도.
# momentum/quality/volatility/mean_reversion 4개 중 한 factor 에 portfolio 의
# N% 이상이 같은 방향(>=70 또는 <=30)으로 쏠리면 매수 차단. 분산 효과 보호.
VAMS_MAX_FACTOR_TILT_PCT = _env_float("VAMS_MAX_FACTOR_TILT_PCT", 60.0)

VAMS_PROFILES = {
    "aggressive": {
        "label": "공격",
        "recommendations": ("BUY", "STRONG_BUY"),
        "min_safety": 45,
        "max_risk_keywords": 2,
        "max_picks": 10,
        "max_buy_per_cycle": 5,
        "stop_loss_pct": -8.0,
        "trailing_stop_pct": 5.0,
        "max_hold_days": 21,
        "max_per_stock": 3_000_000,
        "impact_coeff_bps": 20,
    },
    "moderate": {
        "label": "중간",
        "recommendations": ("BUY", "STRONG_BUY"),
        "min_safety": 55,
        "max_risk_keywords": 1,
        "max_picks": 7,
        "max_buy_per_cycle": 5,
        "stop_loss_pct": -5.0,
        "trailing_stop_pct": 3.0,
        "max_hold_days": 14,
        "max_per_stock": 2_000_000,
        "impact_coeff_bps": 30,
    },
    "safe": {
        "label": "안전",
        "recommendations": ("BUY",),
        "min_safety": 70,
        "max_risk_keywords": 0,
        "max_picks": 3,
        "max_buy_per_cycle": 2,
        "stop_loss_pct": -3.0,
        "trailing_stop_pct": 2.0,
        "max_hold_days": 10,
        "max_per_stock": 1_500_000,
        "impact_coeff_bps": 40,
    },
}

# 하위 호환: 개별 상수를 참조하는 코드가 있을 수 있으므로 활성 프로필에서 파생
_active_vams = VAMS_PROFILES.get(VAMS_ACTIVE_PROFILE, VAMS_PROFILES["moderate"])
VAMS_MAX_PER_STOCK = _env_int("VAMS_MAX_PER_STOCK", _active_vams["max_per_stock"])
VAMS_STOP_LOSS_PCT = _active_vams["stop_loss_pct"]
VAMS_TRAILING_STOP_PCT = _active_vams["trailing_stop_pct"]
VAMS_MAX_HOLD_DAYS = _active_vams["max_hold_days"]

FILTER_MIN_TRADING_VALUE = 1_000_000_000  # 10억 이상 거래대금 (KRW)
FILTER_MIN_TRADING_VALUE_US = 50_000_000  # $50M 이상 거래대금 (USD)
FILTER_MAX_DEBT_RATIO = 100.0
FILTER_TOP_N = 30

# ── Phase 1.1: ATR 기반 동적 손절 (2026-05-01) ──
# 종목 변동성 비례 손절 → whipsaw 손절 감소. 월가 표준 ATR(14)×2.5.
# fallback: ATR 미산출 시 -5% 고정 (-8% 보다 보수적).
ATR_STOP_MULTIPLIER = float(os.environ.get("ATR_STOP_MULTIPLIER", "2.5"))
FALLBACK_STOP_PCT = float(os.environ.get("FALLBACK_STOP_PCT", "5.0"))
ATR_MIN_PERIOD = _env_int("ATR_MIN_PERIOD", 20)  # ATR 계산 최소 일봉 데이터

# ── Phase 2-A: 유니버스 확장 + Ramp-up (결정 1, 4) ──
# Stage 1=500, Stage 2=1500, Stage 3=3000, Stage 4=5000.
# 단계 변경은 .env 또는 GitHub Secrets 수정 후 cron 재실행. 자동 ramp-up 금지.
UNIVERSE_RAMP_UP_STAGE = _env_int("UNIVERSE_RAMP_UP_STAGE", 500)
UNIVERSE_RAMP_UP_AUTO = (
    os.environ.get("UNIVERSE_RAMP_UP_AUTO", "False").strip().lower() in ("true", "1", "yes")
)

# ── 한국투자증권 Open API (KIS Developers) ──
KIS_APP_KEY = os.environ.get("KIS_APP_KEY", "").strip().strip('"')
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET", "").strip().strip('"')
KIS_ACCOUNT_NO = os.environ.get("KIS_ACCOUNT_NO", "").strip().strip('"')
KIS_OPENAPI_BASE_URL = os.environ.get(
    "KIS_OPENAPI_BASE_URL",
    "https://openapi.koreainvestment.com:9443",  # 실전 서버 (기본값)
).strip().strip('"')
# 모의투자 시: KIS_OPENAPI_BASE_URL=https://openapivts.koreainvestment.com:29443
KIS_IS_REAL = "openapivts" not in KIS_OPENAPI_BASE_URL
KIS_ENABLED = bool(KIS_APP_KEY and KIS_APP_SECRET)

# ── 미장 확장 API ──
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
SEC_EDGAR_USER_AGENT = os.environ.get("SEC_EDGAR_USER_AGENT", "")

RISK_KEYWORDS_EN = [
    "fraud", "embezzlement", "delisting", "bankruptcy",
    "sec investigation", "accounting scandal", "class action",
]

# ── SEC 8-K 리스크 키워드 EFTS 스캔 ──
SEC_RISK_SCAN_ENABLED = os.environ.get("SEC_RISK_SCAN_ENABLED", "1").strip().lower() in (
    "1", "true", "yes", "on",
)
SEC_RISK_SCAN_DAYS = _env_int("SEC_RISK_SCAN_DAYS", 7)
_sec_kw_env = os.environ.get("SEC_RISK_KEYWORDS", "").strip()
SEC_RISK_KEYWORDS = [k.strip() for k in _sec_kw_env.split(",") if k.strip()] if _sec_kw_env else [
    "cybersecurity incident", "supply chain disruption", "tariff",
    "material weakness", "going concern", "restatement",
    "goodwill impairment", "restructuring", "force majeure",
]

# ── 미장 수집기 세부 설정 ──
FINNHUB_RATE_LIMIT = _env_int("FINNHUB_RATE_LIMIT", 60)
POLYGON_TIER = os.environ.get("POLYGON_TIER", "free").strip().lower()
SEC_FETCH_TIMEOUT = _env_int("SEC_FETCH_TIMEOUT", 15)
NEWSAPI_MAX_ARTICLES = _env_int("NEWSAPI_MAX_ARTICLES", 20)
US_OPTIONS_MIN_OI = _env_int("US_OPTIONS_MIN_OI", 1000)
US_SHORT_SQUEEZE_THRESHOLD = _env_float("US_SHORT_SQUEEZE_THRESHOLD", 20.0)
US_IV_PERCENTILE_WARN = _env_float("US_IV_PERCENTILE_WARN", 80.0)
US_PUT_CALL_BEARISH = _env_float("US_PUT_CALL_BEARISH", 1.5)
US_INSIDER_MSPR_PENALTY = _env_float("US_INSIDER_MSPR_PENALTY", -5.0)

# Claude 심층 분석: Brain STRONG_BUY/BUY 상위 N개만 Claude에게 전송
CLAUDE_TOP_N = _env_int("CLAUDE_TOP_N", 3)
CLAUDE_MIN_BRAIN_SCORE = _env_int("CLAUDE_MIN_BRAIN_SCORE", 70)
# V6: STRONG_BUY만 Claude 심층 분석 대상 (True → STRONG_BUY만, False → BUY도 포함)
CLAUDE_STRONG_BUY_ONLY = os.environ.get("CLAUDE_STRONG_BUY_ONLY", "1").strip() in ("1", "true", "yes", "on")

# V6: Gemini 배치 분석 후보 상한 (full 모드)
GEMINI_BATCH_MAX_STOCKS = _env_int("GEMINI_BATCH_MAX_STOCKS", 20)

# Claude 풀가동: quick/realtime 모드 확장 (기본 비활성 — Actions vars로 켜야 함)
CLAUDE_IN_QUICK = os.environ.get("CLAUDE_IN_QUICK", "0").strip() in ("1", "true", "yes", "on")
CLAUDE_IN_REALTIME = os.environ.get("CLAUDE_IN_REALTIME", "0").strip() in ("1", "true", "yes", "on")
CLAUDE_QUICK_TOP_N = _env_int("CLAUDE_QUICK_TOP_N", 3)
CLAUDE_EMERGENCY_THRESHOLD_PCT = _env_float("CLAUDE_EMERGENCY_THRESHOLD_PCT", 5.0)
CLAUDE_EMERGENCY_COOLDOWN_MIN = _env_int("CLAUDE_EMERGENCY_COOLDOWN_MIN", 120)
CLAUDE_TAIL_RISK_VERIFY = os.environ.get("CLAUDE_TAIL_RISK_VERIFY", "1").strip() in ("1", "true", "yes", "on")
CLAUDE_MORNING_STRATEGY = os.environ.get("CLAUDE_MORNING_STRATEGY", "1").strip() in ("1", "true", "yes", "on")

# Deadman's Switch: 이 개수 이상 데이터 소스가 실패하면 분석 중단
DEADMAN_FAIL_THRESHOLD = _env_int("DEADMAN_FAIL_THRESHOLD", 3)

# 텔레그램 일일 리포트 전송 시각 (KST) — full 모드에서만 적용
REPORT_SEND_HOUR_KST = _env_int("REPORT_SEND_HOUR_KST", 16)
REPORT_SEND_MINUTE_KST = _env_int("REPORT_SEND_MINUTE_KST", 30)

# 모닝 브리핑 전송 시각 (KST) — quick 모드에서 장 개장 전 발송
MORNING_BRIEF_HOUR_KST = _env_int("MORNING_BRIEF_HOUR_KST", 8)
MORNING_BRIEF_MINUTE_KST = _env_int("MORNING_BRIEF_MINUTE_KST", 0)

# AI 오심 포스트모텀: full 모드 실행 시 자동 생성 (1=on, 0=off)
POSTMORTEM_ENABLED = os.environ.get("POSTMORTEM_ENABLED", "1").strip() in ("1", "true", "yes", "on")

# Brain V2 전략 진화: full 모드 후 Claude가 가중치/임계값 변경 제안 (1=on, 0=off)
STRATEGY_EVOLUTION_ENABLED = os.environ.get("STRATEGY_EVOLUTION_ENABLED", "1").strip() in ("1", "true", "yes", "on")
# 진화 제안 시 각 가중치 최대 변경폭
STRATEGY_MAX_WEIGHT_DELTA = _env_float("STRATEGY_MAX_WEIGHT_DELTA", 0.05)
# 누적 드리프트 상한 — 초기 baseline(versions[0].pre_change_snapshot) 대비 단일 가중치의
# 절대 변화량이 이 값을 초과하면 제안 거부. 같은 방향 N회 누적 표류 방어.
STRATEGY_MAX_CUMULATIVE_DRIFT = _env_float("STRATEGY_MAX_CUMULATIVE_DRIFT", 0.20)
# 진화에 필요한 최소 스냅샷 일수 — 첫 발화 앞당김 (기본 10일, 강제 시 5일).
# 과적합 방지는 STRATEGY_MAX_WEIGHT_DELTA(±0.05) + MAX_CUMULATIVE_DRIFT(0.20) 가 담당.
STRATEGY_MIN_SNAPSHOT_DAYS = _env_int("STRATEGY_MIN_SNAPSHOT_DAYS", 10)
STRATEGY_MIN_SNAPSHOT_DAYS_FORCED = _env_int("STRATEGY_MIN_SNAPSHOT_DAYS_FORCED", 5)
# 자동 적용 시 최소 Out-of-Sample 검증 기간 (일)
STRATEGY_MIN_OOS_DAYS = _env_int("STRATEGY_MIN_OOS_DAYS", 30)

# ── Perplexity 분기 리서치 ─────────────────────────────────────
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = os.environ.get("PERPLEXITY_MODEL", "sonar-pro")

RISK_KEYWORDS = ["배임", "횡령", "실적악화", "상장폐지", "감사의견거절", "자본잠식", "분식회계"]

# ── 펀드 플로우 (EPFR 프록시 — ETF 기반) ──────────────────────────
FUND_FLOW_ENABLED = os.environ.get("FUND_FLOW_ENABLED", "1").strip().lower() in (
    "1", "true", "yes", "on",
)
_ff_etfs = os.environ.get("FUND_FLOW_ETF_TICKERS", "").strip()
FUND_FLOW_ETF_TICKERS = [t.strip() for t in _ff_etfs.split(",") if t.strip()] if _ff_etfs else None

# ── CFTC COT 리포트 (기관 포지셔닝) ──────────────────────────────
CFTC_COT_ENABLED = os.environ.get("CFTC_COT_ENABLED", "1").strip().lower() in (
    "1", "true", "yes", "on",
)
_cot_instr = os.environ.get("CFTC_COT_INSTRUMENTS", "").strip()
CFTC_COT_INSTRUMENTS = [i.strip() for i in _cot_instr.split(",") if i.strip()] if _cot_instr else None

# ── CBOE 풋/콜 비율 (시장 패닉·탐욕 보조 지표) ─────────────────
CBOE_PCR_ENABLED = os.environ.get("CBOE_PCR_ENABLED", "1").strip().lower() in (
    "1", "true", "yes", "on",
)

# ── CNN Fear & Greed (주식시장 심리 지수) ─────────────────────────
MARKET_FNG_EXTREME_GREED = _env_int("MARKET_FNG_EXTREME_GREED", 75)
MARKET_FNG_EXTREME_FEAR = _env_int("MARKET_FNG_EXTREME_FEAR", 25)
MARKET_FNG_ENABLED = os.environ.get("MARKET_FNG_ENABLED", "1").strip().lower() in (
    "1", "true", "yes", "on",
)

# ── 크립토 매크로 센서 (주식 분석 보조 지표) ──────────────────────
CRYPTO_FUNDING_OVERHEAT = _env_float("CRYPTO_FUNDING_OVERHEAT", 0.06)
CRYPTO_FUNDING_UNDERHEAT = _env_float("CRYPTO_FUNDING_UNDERHEAT", -0.03)
CRYPTO_KIMCHI_PREMIUM_WARN = _env_float("CRYPTO_KIMCHI_PREMIUM_WARN", 5.0)
CRYPTO_FNG_EXTREME_GREED = _env_int("CRYPTO_FNG_EXTREME_GREED", 75)
CRYPTO_FNG_EXTREME_FEAR = _env_int("CRYPTO_FNG_EXTREME_FEAR", 25)
CRYPTO_MACRO_ENABLED = os.environ.get("CRYPTO_MACRO_ENABLED", "1").strip().lower() in (
    "1", "true", "yes", "on",
)

# ── Value Hunter: 저평가 발굴 게이트 ──────────────────────────────────
# 백테스트 승률이 이 값 이상일 때 게이트 개방 (기본 55.0%)
VALUE_HUNT_WIN_RATE_MIN = _env_float("VALUE_HUNT_WIN_RATE_MIN", 55.0)
# 게이트 판단에 필요한 최소 표본 수 (너무 적으면 승률이 의미 없음)
VALUE_HUNT_MIN_TRADES = _env_int("VALUE_HUNT_MIN_TRADES", 10)
# 게이트 개방 시 밸류 후보 최대 노출 수
VALUE_HUNT_TOP_N = _env_int("VALUE_HUNT_TOP_N", 5)
# 승률 체크에 사용할 백테스트 기간 — 콤마 구분 우선순위 순 (기본 14d 우선, 30d 폴백)
VALUE_HUNT_LOOKBACK = os.environ.get("VALUE_HUNT_LOOKBACK", "14d,30d").strip() or "14d,30d"
# 0 또는 "false"로 설정하면 전체 기능 비활성화
_VALUE_HUNT_E = os.environ.get("VALUE_HUNT_ENABLED", "1").strip().lower()
VALUE_HUNT_ENABLED = _VALUE_HUNT_E in ("1", "true", "yes", "on")

# 원/달러: 급변 시에만 WARNING/CRITICAL (장중 텔레그램용). 전일 대비 % 또는 원 절대변동
ALERT_USD_KRW_CHANGE_PCT_WARNING = _env_float("ALERT_USD_KRW_CHANGE_PCT_WARNING", 0.8)
ALERT_USD_KRW_CHANGE_PCT_CRITICAL = _env_float("ALERT_USD_KRW_CHANGE_PCT_CRITICAL", 1.5)
ALERT_USD_KRW_ABS_CHANGE_WARNING = _env_float("ALERT_USD_KRW_ABS_CHANGE_WARNING", 12.0)
ALERT_USD_KRW_ABS_CHANGE_CRITICAL = _env_float("ALERT_USD_KRW_ABS_CHANGE_CRITICAL", 22.0)
# 고환율 수준은 급변 없을 때 INFO만 (기존 WARNING 스팸 방지)
ALERT_USD_KRW_LEVEL_INFO_KRW = _env_float("ALERT_USD_KRW_LEVEL_INFO_KRW", 1450.0)

# realtime 텔레그램: 동일 알림 재전송 최소 간격(시간)
TELEGRAM_ALERT_DEDUPE_HOURS = _env_int("TELEGRAM_ALERT_DEDUPE_HOURS", 4)
# CRITICAL 레벨 알림 전용 짧은 쿨다운(분). CRIT-14: 재발 중인 CRITICAL 이 4시간 묵살되는 문제 방지.
TELEGRAM_CRITICAL_DEDUPE_MINUTES = _env_int("TELEGRAM_CRITICAL_DEDUPE_MINUTES", 30)

# 꼬리위험 Gemini 요약 (quick/full 후 1회)
TAIL_RISK_DIGEST_ENABLED = os.environ.get("TAIL_RISK_DIGEST_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
TAIL_RISK_SEVERITY_MIN = _env_int("TAIL_RISK_SEVERITY_MIN", 8)
TAIL_RISK_HEADLINE_MAX = _env_int("TAIL_RISK_HEADLINE_MAX", 24)
TAIL_RISK_NEWS_FLASH_HOURS = _env_int("TAIL_RISK_NEWS_FLASH_HOURS", 48)
# realtime(경량 루프)에서도 키워드 프리필터 통과 시 Gemini 호출
TAIL_RISK_IN_REALTIME = os.environ.get("TAIL_RISK_IN_REALTIME", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
TAIL_RISK_REALTIME_COOLDOWN_MINUTES = _env_int("TAIL_RISK_REALTIME_COOLDOWN_MINUTES", 12)
_tail_pf_x = os.environ.get("TAIL_RISK_PREFILTER_EXTRA", "").strip()
TAIL_RISK_PREFILTER_EXTRA = [p.strip() for p in _tail_pf_x.split(",") if p.strip()]

# RSS: 지정학·재난 키워드 속보 텔레그램 (신규 헤드라인만, 링크 dedupe)
RSS_GEO_TAIL_TELEGRAM = os.environ.get("RSS_GEO_TAIL_TELEGRAM", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
RSS_GEO_TAIL_DEDUPE_HOURS = _env_int("RSS_GEO_TAIL_DEDUPE_HOURS", 36)

# ── Run Tracing (실행 단위 완전 추적 아카이브) ──────────────────
TRACE_ENABLED = os.environ.get("TRACE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
TRACE_AI_CALLS = os.environ.get("TRACE_AI_CALLS", "1").strip().lower() in ("1", "true", "yes", "on")
TRACE_FEATURES = os.environ.get("TRACE_FEATURES", "1").strip().lower() in ("1", "true", "yes", "on")
TRACE_RETENTION_DAYS = _env_int("TRACE_RETENTION_DAYS", 90)

def now_kst():
    return datetime.now(KST)

def today_str():
    return now_kst().strftime("%Y%m%d")


# ── 캘린더 기반 주기 마감일 계산 ──────────────────────────────────
GROWTH_TRIGGER_PERIODS = ("daily", "weekly", "quarterly", "semi", "annual")

GROWTH_MIN_SNAPSHOTS = {
    "daily": 1,
    "weekly": 5,
    "quarterly": 30,
    "semi": 60,
    "annual": 120,
}


def compute_period_end(period: str, ref: Optional[datetime] = None) -> str:
    """캘린더 기준 주기 마감 식별 키를 반환한다 (KST 기준).

    daily   → YYYY-MM-DD (당일)
    weekly  → YYYY-Www   (ISO 주 번호)
    quarterly → YYYYQ1~Q4
    semi    → YYYYH1 / YYYYH2
    annual  → YYYY
    """
    dt = ref or now_kst()
    if period == "daily":
        return dt.strftime("%Y-%m-%d")
    if period == "weekly":
        return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
    if period == "quarterly":
        q = (dt.month - 1) // 3 + 1
        return f"{dt.year}Q{q}"
    if period == "semi":
        h = 1 if dt.month <= 6 else 2
        return f"{dt.year}H{h}"
    if period == "annual":
        return str(dt.year)
    return dt.strftime("%Y-%m-%d")

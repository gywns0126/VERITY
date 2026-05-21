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
# 2026-05-11: GH Actions 자동 prod 강제 폐기. workflow yml env 우선.
# schedule cron = yml env 'prod' 명시, manual dispatch = default 'staging' (cost 감축).
_raw_mode = os.getenv("VERITY_MODE", "dev").strip().lower()
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

# ── 매크로/외부 API ──
# 주의: PUBLIC_DATA_API_KEY (line 122 에 정의) 가 정식 이름.
# (ESTATE 폐기 2026-05-21: SEOUL_DATA_API_KEY / SEOUL_SUBWAY_API_KEY / KOSIS_API_KEY 제거
#  — 전부 제거된 landex 소스(seoul_subway/kosis) 전용. ECOS 는 VERITY 매크로 공유라 보존.)
ECOS_API_KEY = os.environ.get("ECOS_API_KEY", "")                # 한국은행 ECOS (매크로 공유)


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
#   · US 주식/ETF: 증권거래세 없음 (양도세 22% × 250만원 공제는 별도 — 아래 US 양도세 분기에서 처리)
VAMS_SELL_TAX_KR_STOCK = _env_float("VAMS_SELL_TAX_KR_STOCK", 0.0018)   # KR 일반주 매도세
VAMS_SELL_TAX_KR_ETF = _env_float("VAMS_SELL_TAX_KR_ETF", 0.0)          # KR ETF 면제
VAMS_SELL_TAX_US = _env_float("VAMS_SELL_TAX_US", 0.0)                  # US 거래세 (SEC fee 무시 수준)
VAMS_SELL_TAX_RATE = VAMS_SELL_TAX_KR_STOCK  # 하위 호환 별칭 (기존 코드가 참조하던 이름)

# 호가 스프레드: VAMS 시장충격(30bp)과 중복되지 않도록 보수적 5bp 왕복 (≈0.05%).
# 대형주 기준. 중소형주·저유동성 종목 비중 높으면 10~15bp까지 상향 권장.
VAMS_SPREAD_SLIPPAGE_BPS = _env_float("VAMS_SPREAD_SLIPPAGE_BPS", 5)
# 배당세 — 종목 출처별 분리 (Perplexity 자문 2026-05-17):
#   · KR 직접 주식 / KR 상장 ETF (KODEX, TIGER 등): 15.4% (소득세 14% + 지방세 1.4%)
#   · US 직접 주식 / US 상장 ETF (SPY, QQQ 등): 15.0% (한미 조세조약, US 원천 15% > KR 14% 임계 → KR 추가 0%)
#   · REIT 동일 (한미 조세조약으로 15%)
#   · 금융소득 종합과세 (연 2000만 초과) 미반영 — 자본 5억+ 진입 시 산식 보강 필요
VAMS_DIVIDEND_TAX_RATE_KR = _env_float("VAMS_DIVIDEND_TAX_RATE_KR", 0.154)
VAMS_DIVIDEND_TAX_RATE_US = _env_float("VAMS_DIVIDEND_TAX_RATE_US", 0.150)
VAMS_DIVIDEND_TAX_RATE = VAMS_DIVIDEND_TAX_RATE_KR  # 하위 호환 별칭

# US 양도세 — 한국 거주자 비대주주 기준 (메모리 [[after-tax-sharpe-kr-us]] 산식 적용).
# · 양도차익 22% (국세 20% + 지방세 2%) 분리과세, 연 250만원 양도소득 기본공제.
# · KR 비대주주 상장주식 = 0% (비과세) 가정. 대주주 판정 미박힘.
# · 손익통산: realized SELL/PARTIAL_SELL US PnL 합산. unrealized 는 매도 가정 estimate.
# · 250만 공제 = realized 우선 적용, 잔여만 unrealized 에 적용.
# · 양도일 = 결제일 (T+2 한국 시간, 미국 T+1 + 시차). VAMS history `date` 는 약정일이므로
#   연말 cut-off 정밀화 시 결제일 변환 필요 (현 무).
# · 손익통산 범위: 해외주식 종목간 + KR 비상장/대주주 (현 미박힘, 영향 0).
# · 환차익은 별도 과세 X — 원화 환산 양도차익에 자동 합산. VAMS buy_price 환산 KRW 보관.
VAMS_US_CAPITAL_GAINS_RATE = _env_float("VAMS_US_CAPITAL_GAINS_RATE", 0.22)
VAMS_US_CAPITAL_GAINS_DEDUCTION_KRW = _env_int("VAMS_US_CAPITAL_GAINS_DEDUCTION_KRW", 2_500_000)

# US 환전 비용 — 원-달러 왕복 환전 (대형 증권사 우대 기준, Perplexity 2026-05-17).
# 매도 시 1회 차감 (매수 시 환전은 buy_price 환산에 이미 흡수, 별도 차감 X).
VAMS_US_FX_COST_RATE = _env_float("VAMS_US_FX_COST_RATE", 0.003)

# 무위험수익률 R_f — 한국 학계 표준 = CD91 (양도성예금증서 91일물).
# Perplexity 2026-05-17 자문: 2026-05 현재 CD91 ≈ 3.2%, 국고채 1년 = 3.045%.
# 글로벌 학계 표준 = 세전 R_f 사용. 세후 사용 시 분자/분모 동시 통일 필수 (혼용 = Sharpe 과대 추정).
# Brain v6 / conviction_selector 등 Sharpe 산식에서 호출.
VAMS_RISK_FREE_RATE_PRETAX = _env_float("VAMS_RISK_FREE_RATE_PRETAX", 0.032)

# KR 대주주 판정 + 세율 분기 (Perplexity 2026-05-17, 메모리 [[project_capital_gains_tax_kr_us_2026_05]] §5,6).
# 자동 판정 미박힘 (지분율 데이터 미수집) — 명시 toggle 만. 기본 False = 비대주주 비과세 가정.
# toggle 활성 시 KR 양도세 분기 적용 (1년 미만 30% / 3억 초과 25% / 3억 이하 20%).
VAMS_KR_MAJORITY_SHAREHOLDER = (
    os.environ.get("VAMS_KR_MAJORITY_SHAREHOLDER", "").strip().lower() in ("1", "true", "yes", "on")
)
VAMS_KR_MAJORITY_TAX_RATE_BASE = _env_float("VAMS_KR_MAJORITY_TAX_RATE_BASE", 0.20)         # 3억 이하
VAMS_KR_MAJORITY_TAX_RATE_HIGH = _env_float("VAMS_KR_MAJORITY_TAX_RATE_HIGH", 0.25)         # 3억 초과 누진
VAMS_KR_MAJORITY_TAX_RATE_SHORT = _env_float("VAMS_KR_MAJORITY_TAX_RATE_SHORT", 0.30)       # 1년 미만 보유
VAMS_KR_MAJORITY_HIGH_THRESHOLD_KRW = _env_int("VAMS_KR_MAJORITY_HIGH_THRESHOLD_KRW", 300_000_000)

# ISA 비과세 한도 — 일반형 200만 / 서민형 400만 (Perplexity 2026-05-17, [[project_kis_isa_constraint]]).
# mode_tag = 'isa' 인 VAMS 만 적용. 한도 초과분 = 9.9% 분리과세. 의무 보유 3년.
# 해외주식 직접투자 = ISA 대상 X (해외 ETF 만 가능 — VAMS asset_class 추가 분기 필요).
VAMS_ISA_DEDUCTION_KRW = _env_int("VAMS_ISA_DEDUCTION_KRW", 2_000_000)            # 일반형 기본
VAMS_ISA_DEDUCTION_KRW_LOW_INCOME = _env_int("VAMS_ISA_DEDUCTION_KRW_LOW_INCOME", 4_000_000)
VAMS_ISA_EXCESS_TAX_RATE = _env_float("VAMS_ISA_EXCESS_TAX_RATE", 0.099)          # 9.9% 분리과세

# 금융소득 종합과세 임계 — 연 2000만원 초과 시 종합과세 (6~45% 누진) 전환.
# VAMS = 분리과세 15.4% 유지. 임계 초과 시 assumptions 노트로 사용자 신고 안내.
VAMS_DIVIDEND_COMPREHENSIVE_THRESHOLD_KRW = _env_int("VAMS_DIVIDEND_COMPREHENSIVE_THRESHOLD_KRW", 20_000_000)

# 금투세 재시행 fallback (2027~2029 변곡점, [[project_geumtu_tax_horizon]]).
# 기본 False = KR 양도세 0% (현행). True 활성 시 KR 양도세 분기 박음 (5000만 공제 / 22%·27.5% 누진 / 5년 손실이월).
VAMS_KR_GEUMTU_RESTORED = (
    os.environ.get("VAMS_KR_GEUMTU_RESTORED", "").strip().lower() in ("1", "true", "yes", "on")
)
VAMS_KR_GEUMTU_DEDUCTION_KRW = _env_int("VAMS_KR_GEUMTU_DEDUCTION_KRW", 50_000_000)         # 국내 5000만
VAMS_KR_GEUMTU_TAX_RATE_BASE = _env_float("VAMS_KR_GEUMTU_TAX_RATE_BASE", 0.22)             # 3억 이하
VAMS_KR_GEUMTU_TAX_RATE_HIGH = _env_float("VAMS_KR_GEUMTU_TAX_RATE_HIGH", 0.275)            # 3억 초과
VAMS_KR_GEUMTU_HIGH_THRESHOLD_KRW = _env_int("VAMS_KR_GEUMTU_HIGH_THRESHOLD_KRW", 300_000_000)

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
VAMS_PASS_WIN_RATE = _env_float("VAMS_PASS_WIN_RATE", 0.55)                      # 승률 하한 (55%, Van Tharp 최소 진입 임계)
VAMS_PASS_PROFIT_LOSS_RATIO = _env_float("VAMS_PASS_PROFIT_LOSS_RATIO", 1.5)     # 평균수익 / 평균손실 하한
VAMS_PASS_SHARPE = _env_float("VAMS_PASS_SHARPE", 1.0)                           # 샤프 통과선 (연율)
# 2026-05-16 Perplexity MED-D1: 승률 55% 단독 부족 — Expectancy 동반 의무화.
# Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss). R-multiple 단위.
# Van Tharp 권장: ≥ 1.2R = 1 단위 risk 당 1.2 단위 평균 보상.
# Wide Scan Brain v5 정합 — 55% gate + Expectancy ≥ 1.2R 이중 임계.
VAMS_MIN_EXPECTANCY_R = _env_float("VAMS_MIN_EXPECTANCY_R", 1.2)
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
# 2026-05-16 Perplexity MED-D2: 60% 과도 (KOSPI 섹터 집중 50%+ 구조에서 비선형 리스크).
# CalPERS 50% / Black-Litterman 40% 권장. 60 → 50 정정 (CalPERS 수준, 한국 보수 적용).
VAMS_MAX_FACTOR_TILT_PCT = _env_float("VAMS_MAX_FACTOR_TILT_PCT", 50.0)

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
FILTER_TOP_N = 30  # legacy default (단일 시장 또는 fallback)
# 2026-05-11: 시장별 분리. 사용자 결정 "국장 10 + 미장 15 = 25" — brain 부담 58% 감축.
# 5단계 funnel (5,000→1,000→300→100→Top 10) 의 최종 Top 10 단계 정합.
FILTER_KR_TOP_N = _env_int("FILTER_KR_TOP_N", 10)
FILTER_US_TOP_N = _env_int("FILTER_US_TOP_N", 15)

# ── Phase 0: ATR 표준화 (2026-05-01, P-01 단일 정의) ──
# 산출법 토글 (롤백 안전장치). 옵션 X 적용 후 표준 = wilder_ema_14.
# technical.py 는 import 만 사용 (모듈 변수 재정의 금지 — P-01).
ATR_METHOD = os.environ.get("ATR_METHOD", "wilder_ema_14")
# 2026-05-16 verdict=OK 후 default false (Phase 1.5.1 진입).
# 산출 비교 누적 종료 — log 파일은 보존 (data/metadata/atr_migration_log.jsonl + archive/).
# 재활성 필요 시 ATR_MIGRATION_LOGGING=true 강제 가능.
ATR_MIGRATION_LOGGING = os.environ.get("ATR_MIGRATION_LOGGING", "false").lower() == "true"
ATR_MIGRATION_START_DATE = os.environ.get("ATR_MIGRATION_START_DATE", "")  # ISO date

# ── Phase 1.1: ATR 기반 동적 손절 (2026-05-01) ──
# 종목 변동성 비례 손절 → whipsaw 손절 감소. 월가 표준 ATR(14)×2.5.
# fallback: ATR 미산출 시 -5% 고정 (-8% 보다 보수적).
ATR_STOP_MULTIPLIER = float(os.environ.get("ATR_STOP_MULTIPLIER", "2.5"))
FALLBACK_STOP_PCT = float(os.environ.get("FALLBACK_STOP_PCT", "5.0"))
ATR_MIN_PERIOD = _env_int("ATR_MIN_PERIOD", 20)  # ATR 계산 최소 일봉 데이터

# ── Phase 1.2: R-multiple 기반 부분 익절 (2026-05-01) ──
# 진입가-손절가 거리 = 1R. +1R/+2R 단계별 청산 + 남은 분 트레일링.
# Linda Raschke / Chuck LeBeau 표준. magic number 1.12 폐기.
R_MULTIPLE_TARGET_1 = float(os.environ.get("R_MULTIPLE_TARGET_1", "1.0"))  # +1R
R_MULTIPLE_TARGET_2 = float(os.environ.get("R_MULTIPLE_TARGET_2", "2.0"))  # +2R
R_MULTIPLE_EXIT_PCT_1 = float(os.environ.get("R_MULTIPLE_EXIT_PCT_1", "50"))  # 보유 50%
R_MULTIPLE_EXIT_PCT_2 = float(os.environ.get("R_MULTIPLE_EXIT_PCT_2", "30"))  # 추가 30%
R_MULTIPLE_TRAIL_PCT = float(os.environ.get("R_MULTIPLE_TRAIL_PCT", "5.0"))  # 남은 20% 트레일링

# ── Phase 2-A: 유니버스 확장 + Ramp-up (결정 1, 4) ──
# Stage 1=500, Stage 2=1500, Stage 3=3000, Stage 4=5000.
# 단계 변경은 .env 또는 GitHub Secrets 수정 후 cron 재실행. 자동 ramp-up 금지.
UNIVERSE_RAMP_UP_STAGE = _env_int("UNIVERSE_RAMP_UP_STAGE", 500)
UNIVERSE_RAMP_UP_AUTO = (
    os.environ.get("UNIVERSE_RAMP_UP_AUTO", "False").strip().lower() in ("true", "1", "yes")
)

# ── Phase 2-B: wide_scan Coarse Filter (Perplexity 7-답 종합 + 메모리 원칙 1) ──
# DISABLED: 호출 자체 skip (default — 인프라 박힘 이후에도 명시 활성화 필요)
# SHADOW: 7차원 + F-Score + Z 계산 → data/wide_scan_log.jsonl 만 적재. portfolio.json 영향 0
# CANARY_5: portfolio 5%만 wide_scan 결과 사용 (FIA 자동매매 가이드라인 정합)
# PRODUCTION: 전면 적용 (WIDE_SCAN_PRODUCTION_MIN_DAYS 거래일 SHADOW 검증 후에만)
WIDE_SCAN_MODE = os.environ.get("WIDE_SCAN_MODE", "DISABLED").strip().upper()
if WIDE_SCAN_MODE not in ("DISABLED", "SHADOW", "CANARY_5", "PRODUCTION"):
    WIDE_SCAN_MODE = "DISABLED"
# SHADOW→PRODUCTION 전환 최소 누적 거래일 (게이트).
# 2026-05-22 PM 승인 (RULE 7 1회): 65 → 90.
#   근거 = (1) STRATEGY_MIN_OOS_DAYS=90 과 자기 기준 단일화 (유의성 최소선 통일),
#          (2) Lopez de Prado MinTRL 권장 band(90~120) 하단 = 학계 방어선,
#          (3) funnel cross-sectional → breadth 표본 보강, 120 상단 쿠션 한계효용 낮음.
#   caveat = 필요조건이지 충분조건 아님. PRODUCTION flip 시 N 개수 + N 품질(IC 부호/단조성) 동시 확인 의무.
WIDE_SCAN_PRODUCTION_MIN_DAYS = _env_int("WIDE_SCAN_PRODUCTION_MIN_DAYS", 90)

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
# 2026-05-16 audit: 이하 2개 env reference 0건. 운영 사용 없음.
# 미장 옵션/숏 squeeze 시그널 향후 sprint (Phase B 매크로 게이트 후) 재활성 시 복원.
# US_OPTIONS_MIN_OI = _env_int("US_OPTIONS_MIN_OI", 1000)        # dead
# US_SHORT_SQUEEZE_THRESHOLD = _env_float("US_SHORT_SQUEEZE_THRESHOLD", 20.0)  # dead
US_IV_PERCENTILE_WARN = _env_float("US_IV_PERCENTILE_WARN", 80.0)
US_PUT_CALL_BEARISH = _env_float("US_PUT_CALL_BEARISH", 1.5)
US_INSIDER_MSPR_PENALTY = _env_float("US_INSIDER_MSPR_PENALTY", -5.0)

# Claude 심층 분석: Brain STRONG_BUY/BUY 상위 N개만 Claude에게 전송
CLAUDE_TOP_N = _env_int("CLAUDE_TOP_N", 3)
CLAUDE_MIN_BRAIN_SCORE = _env_int("CLAUDE_MIN_BRAIN_SCORE", 70)
# V6: STRONG_BUY만 Claude 심층 분석 대상 (True → STRONG_BUY만, False → BUY도 포함)
CLAUDE_STRONG_BUY_ONLY = os.environ.get("CLAUDE_STRONG_BUY_ONLY", "1").strip() in ("1", "true", "yes", "on")

# V6: Gemini 배치 분석 후보 상한 (full 모드).
# 2026-05-11: 60 candidate → 50 으로 사용자 결정 (cost 감축, 17% 절감).
# 환경변수 override 시 default 50 적용. brain v5 score 기준 top N.
GEMINI_BATCH_MAX_STOCKS = _env_int("GEMINI_BATCH_MAX_STOCKS", 50)

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
# 자동 적용 시 최소 Out-of-Sample 검증 기간 (일).
# Perplexity Q4 (2026-05-17) 학계 자문: 30 → 90.
# T=22 거래일 SE(SR)≈±0.22 노이즈 폭발. Lopez de Prado MinTRL 기준 90~120일 권장.
# 27 cycle 전부 reject root cause 의 1차 fix.
STRATEGY_MIN_OOS_DAYS = _env_int("STRATEGY_MIN_OOS_DAYS", 90)
# proposal vs current Sharpe 비교 시 절대 margin (0.0 = 미세 차이도 reject).
# Perplexity Q4: 0 → 0.10 (학계 표준). 동시 PSR p<0.10 통계 검정 권장 (별 sprint).
STRATEGY_SHARPE_MIN_MARGIN = float(os.environ.get("STRATEGY_SHARPE_MIN_MARGIN", "0.10"))
# MDD ex-ante gate (전략 선택) vs runtime stop (실시간 청산) 분리.
# ex-ante = circuit_breaker.max_rolling_mdd_pct (현 15%). runtime stop = 20% (절대값, hard).
STRATEGY_RUNTIME_MDD_STOP_PCT = float(os.environ.get("STRATEGY_RUNTIME_MDD_STOP_PCT", "20.0"))
# Perplexity Q4 v2 (2026-05-17): PSR (Probabilistic Sharpe Ratio) optional gate.
# True 시 절대 margin 검정 + PSR > confidence 검정 둘 다 통과 필요 (보수).
# False (default) = margin only. SR returns series 가 simulate_proposal 에서 박혀야 활성 가능.
STRATEGY_PSR_ENABLED = os.environ.get("STRATEGY_PSR_ENABLED", "0").strip().lower() in ("1", "true", "yes")
STRATEGY_PSR_CONFIDENCE = float(os.environ.get("STRATEGY_PSR_CONFIDENCE", "0.90"))  # 90% 단측 검정
# Perplexity Q4 v2: Strategy Pool (sequential → portfolio of strategies).
# True 시 strategy_pool.add_to_pool 통합 — worst strategy 비교 + 교체. False = sequential current 단독.
# api/intelligence/strategy_pool.py 의 가중치 ensemble compute_ensemble_signal 활용.
STRATEGY_POOL_ENABLED = os.environ.get("STRATEGY_POOL_ENABLED", "0").strip().lower() in ("1", "true", "yes")
STRATEGY_POOL_MAX_SIZE = int(os.environ.get("STRATEGY_POOL_MAX_SIZE", "3"))
# Capital 3-Tier hard cap — tier 별 자본 초과 매수 차단 (Perplexity Q3, project_capital_3tier_mode).
# False = soft (mode_tag 추적만, sub-PnL 누적). True = hard (capital_allocation 초과 시 reject).
CAPITAL_3TIER_HARD_CAP_ENABLED = os.environ.get("CAPITAL_3TIER_HARD_CAP_ENABLED", "0").strip().lower() in ("1", "true", "yes")

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
# 2026-05-08: 4 → 8 — 주간 spam 완화. 같은 시그널이 반복 firing 시 8h 쿨다운.
TELEGRAM_ALERT_DEDUPE_HOURS = _env_int("TELEGRAM_ALERT_DEDUPE_HOURS", 8)
# CRITICAL 레벨 알림 전용 짧은 쿨다운(분). CRIT-14: 재발 중인 CRITICAL 이 4시간 묵살되는 문제 방지.
TELEGRAM_CRITICAL_DEDUPE_MINUTES = _env_int("TELEGRAM_CRITICAL_DEDUPE_MINUTES", 30)

# ── 텔레그램 야간 묵음 (Quiet Hours) ──
# 2026-05-08: rss_scout 매 30분 / daily_analysis 시간당 야간 firing 으로 누적된 새벽 spam 차단.
# KST 기준. start <= h < end (자정 넘김 지원: start > end 면 [start..24)+[0..end) ).
# bypass_quiet=True 호출은 여전히 즉시 발송 (deadman, 자동매매 체결, VAMS 손절 등).
TELEGRAM_QUIET_HOURS_ENABLED = os.environ.get("TELEGRAM_QUIET_HOURS_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
TELEGRAM_QUIET_START_KST = _env_int("TELEGRAM_QUIET_START_KST", 23)
TELEGRAM_QUIET_END_KST = _env_int("TELEGRAM_QUIET_END_KST", 7)

# ── 텔레그램 통수 절감 (2026-05-12) ──
# 사용자 호소: "급한 일만 보내라". realtime 묶음 알림이 5분 cron 마다 같은 내용 반복.
# 두 레버:
#   1) TELEGRAM_REALTIME_MIN_LEVEL — realtime 루프(api/main.py)에서 텔레그램으로 묶을 alert 최소 레벨.
#      기본 CRITICAL — WARNING 도 사이트 카드/Bell 로 표시되므로 텔레그램 통수에서 빼는 게 정합.
#   2) TELEGRAM_CRITICAL_ONLY — 비상 스위치. 1 일 때 묶음 alert (send_alerts) 자체가 CRITICAL 0건이면 skip.
#      send_message 직접 호출은 영향 없음 (deadman / auto-trade 체결 등은 그대로).
TELEGRAM_REALTIME_MIN_LEVEL = os.environ.get(
    "TELEGRAM_REALTIME_MIN_LEVEL", "CRITICAL"
).strip().upper() or "CRITICAL"
TELEGRAM_CRITICAL_ONLY = os.environ.get("TELEGRAM_CRITICAL_ONLY", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

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

# RSS 지정학·재난 키워드 텔레그램 발화 폐기 (2026-05-14):
# 키워드 매칭이 메타포 false positive 양산 (예: "AI tsunami" 헤드라인 발화).
# geo_trigger.py 의 USGS 구조화 API (magnitude+location) 만 신뢰. 옵션 B sprint 큐.

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

import os
from datetime import datetime, timezone, timedelta
from typing import FrozenSet, Optional
from dotenv import load_dotenv

load_dotenv()

KST = timezone(timedelta(hours=9))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# gemini-2.0-flash* 는 신규 키에서 404 — 기본은 2.5 Flash (환경변수 GEMINI_MODEL로 덮어쓰기)
GEMINI_MODEL = (os.environ.get("GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
# Financial Modeling Prep — https://site.financialmodelingprep.com/developer/docs
FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


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
DART_API_KEY = os.environ.get("DART_API_KEY", "")
# FRED — https://fredaccount.stlouisfed.org/apikeys
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
# 한국은행 ECOS — https://ecos.bok.or.kr/api/
ECOS_API_KEY = os.environ.get("ECOS_API_KEY", "")
# 미 10년물(DGS10) 이 값 이상이면 브레인 등급 관망 상한·현금 확대 권고(기본 4.5%)
MACRO_DGS10_DEFENSE_PCT = float(os.environ.get("MACRO_DGS10_DEFENSE_PCT", "4.5"))
# 공공데이터포털 — 관세청 품목별·국가별 수출입실적(getNitemtradeList 등) 활용신청 후 발급
PUBLIC_DATA_API_KEY = os.environ.get("PUBLIC_DATA_API_KEY", "")
# 관세청 API: 1차 조회 국가코드(기본 ZZ=전체), 2차는 전월비 급증 시에만 SURGE_COUNTRIES
CUSTOMS_TRADE_BASE_CNTY = os.environ.get("CUSTOMS_TRADE_BASE_CNTY", "ZZ").strip().upper() or "ZZ"
CUSTOMS_TRADE_SURGE_COUNTRIES = os.environ.get(
    "CUSTOMS_TRADE_SURGE_COUNTRIES",
    "CN,US,VN",
)
# 전월 대비 수출액(%)이 이 값 이상이면 CN·US·VN 세부 조회
CUSTOMS_TRADE_SURGE_MOM_PCT = float(os.environ.get("CUSTOMS_TRADE_SURGE_MOM_PCT", "15"))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
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

VAMS_INITIAL_CASH = int(os.environ.get("VAMS_INITIAL_CASH", 10_000_000))
VAMS_MAX_PER_STOCK = int(os.environ.get("VAMS_MAX_PER_STOCK", 2_000_000))
VAMS_COMMISSION_RATE = 0.00015
VAMS_STOP_LOSS_PCT = -5.0
VAMS_TRAILING_STOP_PCT = 3.0
VAMS_MAX_HOLD_DAYS = 14

FILTER_MIN_TRADING_VALUE = 1_000_000_000  # 10억 이상 거래대금
FILTER_MAX_DEBT_RATIO = 100.0
FILTER_TOP_N = 30

# Claude 심층 분석: Brain STRONG_BUY/BUY 상위 N개만 Claude에게 전송
CLAUDE_TOP_N = int(os.environ.get("CLAUDE_TOP_N", "5"))
CLAUDE_MIN_BRAIN_SCORE = int(os.environ.get("CLAUDE_MIN_BRAIN_SCORE", "60"))

# Deadman's Switch: 이 개수 이상 데이터 소스가 실패하면 분석 중단
DEADMAN_FAIL_THRESHOLD = int(os.environ.get("DEADMAN_FAIL_THRESHOLD", "3"))

# 텔레그램 일일 리포트 전송 시각 (KST) — full 모드에서만 적용
REPORT_SEND_HOUR_KST = int(os.environ.get("REPORT_SEND_HOUR_KST", "16"))
REPORT_SEND_MINUTE_KST = int(os.environ.get("REPORT_SEND_MINUTE_KST", "30"))

# 모닝 브리핑 전송 시각 (KST) — quick 모드에서 장 개장 전 발송
MORNING_BRIEF_HOUR_KST = int(os.environ.get("MORNING_BRIEF_HOUR_KST", "8"))
MORNING_BRIEF_MINUTE_KST = int(os.environ.get("MORNING_BRIEF_MINUTE_KST", "0"))

# AI 오심 포스트모텀: full 모드 실행 시 자동 생성 (1=on, 0=off)
POSTMORTEM_ENABLED = os.environ.get("POSTMORTEM_ENABLED", "1").strip() in ("1", "true", "yes", "on")

# Brain V2 전략 진화: full 모드 후 Claude가 가중치/임계값 변경 제안 (1=on, 0=off)
STRATEGY_EVOLUTION_ENABLED = os.environ.get("STRATEGY_EVOLUTION_ENABLED", "1").strip() in ("1", "true", "yes", "on")
# 진화 제안 시 각 가중치 최대 변경폭
STRATEGY_MAX_WEIGHT_DELTA = float(os.environ.get("STRATEGY_MAX_WEIGHT_DELTA", "0.05"))
# 진화에 필요한 최소 스냅샷 일수
STRATEGY_MIN_SNAPSHOT_DAYS = int(os.environ.get("STRATEGY_MIN_SNAPSHOT_DAYS", "7"))

RISK_KEYWORDS = ["배임", "횡령", "실적악화", "상장폐지", "감사의견거절", "자본잠식", "분식회계"]

# 원/달러: 급변 시에만 WARNING/CRITICAL (장중 텔레그램용). 전일 대비 % 또는 원 절대변동
ALERT_USD_KRW_CHANGE_PCT_WARNING = float(os.environ.get("ALERT_USD_KRW_CHANGE_PCT_WARNING", "0.8"))
ALERT_USD_KRW_CHANGE_PCT_CRITICAL = float(os.environ.get("ALERT_USD_KRW_CHANGE_PCT_CRITICAL", "1.5"))
ALERT_USD_KRW_ABS_CHANGE_WARNING = float(os.environ.get("ALERT_USD_KRW_ABS_CHANGE_WARNING", "12"))
ALERT_USD_KRW_ABS_CHANGE_CRITICAL = float(os.environ.get("ALERT_USD_KRW_ABS_CHANGE_CRITICAL", "22"))
# 고환율 수준은 급변 없을 때 INFO만 (기존 WARNING 스팸 방지)
ALERT_USD_KRW_LEVEL_INFO_KRW = float(os.environ.get("ALERT_USD_KRW_LEVEL_INFO_KRW", "1450"))

# realtime 텔레그램: 동일 알림 재전송 최소 간격(시간)
TELEGRAM_ALERT_DEDUPE_HOURS = int(os.environ.get("TELEGRAM_ALERT_DEDUPE_HOURS", "4"))

# 꼬리위험 Gemini 요약 (quick/full 후 1회)
TAIL_RISK_DIGEST_ENABLED = os.environ.get("TAIL_RISK_DIGEST_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
TAIL_RISK_SEVERITY_MIN = int(os.environ.get("TAIL_RISK_SEVERITY_MIN", "8"))
TAIL_RISK_HEADLINE_MAX = int(os.environ.get("TAIL_RISK_HEADLINE_MAX", "24"))
TAIL_RISK_NEWS_FLASH_HOURS = int(os.environ.get("TAIL_RISK_NEWS_FLASH_HOURS", "48"))
# realtime(경량 루프)에서도 키워드 프리필터 통과 시 Gemini 호출
TAIL_RISK_IN_REALTIME = os.environ.get("TAIL_RISK_IN_REALTIME", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
TAIL_RISK_REALTIME_COOLDOWN_MINUTES = int(os.environ.get("TAIL_RISK_REALTIME_COOLDOWN_MINUTES", "12"))
_tail_pf_x = os.environ.get("TAIL_RISK_PREFILTER_EXTRA", "").strip()
TAIL_RISK_PREFILTER_EXTRA = [p.strip() for p in _tail_pf_x.split(",") if p.strip()]

# RSS: 지정학·재난 키워드 속보 텔레그램 (신규 헤드라인만, 링크 dedupe)
RSS_GEO_TAIL_TELEGRAM = os.environ.get("RSS_GEO_TAIL_TELEGRAM", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
RSS_GEO_TAIL_DEDUPE_HOURS = int(os.environ.get("RSS_GEO_TAIL_DEDUPE_HOURS", "36"))

def now_kst():
    return datetime.now(KST)

def today_str():
    return now_kst().strftime("%Y%m%d")

import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

KST = timezone(timedelta(hours=9))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
DART_API_KEY = os.environ.get("DART_API_KEY", "")
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

RISK_KEYWORDS = ["배임", "횡령", "실적악화", "상장폐지", "감사의견거절", "자본잠식", "분식회계"]

def now_kst():
    return datetime.now(KST)

def today_str():
    return now_kst().strftime("%Y%m%d")

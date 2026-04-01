import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

KST = timezone(timedelta(hours=9))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")

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

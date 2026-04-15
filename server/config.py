"""서버 환경변수 설정 — 실전 전용."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

KIS_APP_KEY: str = os.getenv("KIS_APP_KEY", "").strip().strip('"')
KIS_APP_SECRET: str = os.getenv("KIS_APP_SECRET", "").strip().strip('"')
KIS_BASE_URL: str = os.getenv(
    "KIS_OPENAPI_BASE_URL",
    "https://openapi.koreainvestment.com:9443",
).strip().strip('"').rstrip("/")

KIS_ACCOUNT_NO: str = os.getenv("KIS_ACCOUNT_NO", "").strip().strip('"')

KIS_WS_URL: str = "ws://ops.koreainvestment.com:21000"

PORTFOLIO_URL: str = os.getenv(
    "PORTFOLIO_URL",
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
).strip()

ALLOWED_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if o.strip()
]

PORT: int = int(os.getenv("PORT", "8000"))

# ── 최적화 상수 ──
IDLE_UNSUB_TTL: int = int(os.getenv("IDLE_UNSUB_TTL", "300"))
MAX_CANDLE_MINUTES: int = int(os.getenv("MAX_CANDLE_MINUTES", "240"))
SSE_QUEUE_SIZE: int = int(os.getenv("SSE_QUEUE_SIZE", "128"))
CLEANUP_INTERVAL: int = int(os.getenv("CLEANUP_INTERVAL", "60"))
MAX_SUBS: int = int(os.getenv("MAX_SUBS", "20"))

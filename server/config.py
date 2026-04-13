"""서버 환경변수 설정."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

KIS_APP_KEY: str = os.getenv("KIS_APP_KEY", "").strip().strip('"')
KIS_APP_SECRET: str = os.getenv("KIS_APP_SECRET", "").strip().strip('"')
KIS_BASE_URL: str = os.getenv(
    "KIS_OPENAPI_BASE_URL",
    "https://openapivts.koreainvestment.com:29443",
).strip().strip('"').rstrip("/")

IS_PAPER: bool = "vts" in KIS_BASE_URL.lower()

# 실전 vs 모의 WebSocket 주소
KIS_WS_URL: str = (
    "ws://ops.koreainvestment.com:31000"
    if IS_PAPER
    else "ws://ops.koreainvestment.com:21000"
)

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

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

# ── 서버 간 공유 비밀 (Vercel ↔ Railway) ──
# Vercel order.py 가 X-Service-Auth 헤더로 이 값을 보냄. 미설정 시 /api/order fail-closed.
# 2026-04-23 이전엔 ORDER_SECRET + Authorization Bearer 사용 → legacy 호환만 남김.
RAILWAY_SHARED_SECRET: str = os.getenv("RAILWAY_SHARED_SECRET", "").strip().strip('"')
ORDER_SECRET_LEGACY: str = os.getenv("ORDER_SECRET", "").strip().strip('"')

KIS_WS_URL: str = "ws://ops.koreainvestment.com:21000"

# ── KIS 공유 토큰 store (Supabase) — RULE 1 단일 발급원 (PM 결정 2026-05-31) ──
# Railway = 유일 발급원 → 발급 시 kis_shared_token 테이블에 토큰 값 기록.
# GH/Vercel = service_role 읽기 소비. KIS_SHARED_TOKEN=1 일 때만 활성 (단계적 cutover).
KIS_SHARED_TOKEN: bool = os.getenv("KIS_SHARED_TOKEN", "").strip().lower() in ("1", "true", "yes", "on")
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

PORTFOLIO_URL: str = os.getenv(
    "PORTFOLIO_URL",
    # 2026-05-27 VERITY private 전환 sweep 잔재 fix — Vercel Blob cutover.
    # [[project_repo_visibility_plan]]. raw.githubusercontent.com 은 private 404.
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
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

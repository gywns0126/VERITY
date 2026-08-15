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

# ── 다계좌 라우팅 (PM 2026-08-07) ────────────────────────────────────
# 회원 = 오퍼레이터 + 지인 1명. A안 = **각자 자기 계좌에서 자기가 승인**(타인 자금 일임 아님).
# 자격증명은 사람 수가 2명이라 별도 암호화 저장소를 만들지 않고 배포 env 세트로 둔다 —
# 저장소를 새로 만들면 그 자체가 새 유출 표면이고, 2명 규모에선 이득이 없다.
#
# env 규약:
#   operator = 기존 KIS_APP_KEY / KIS_APP_SECRET / KIS_ACCOUNT_NO (변수명 불변 = 하위호환)
#   그 외    = KIS_APP_KEY__<SLUG대문자> / KIS_APP_SECRET__<SLUG> / KIS_ACCOUNT_NO__<SLUG>
#   BROKER_SLUGS = 'operator,friend'  ← allowlist. 여기 없는 슬러그는 해석 자체를 거부.
#
# 🚨 allowlist 가 필수인 이유: 슬러그가 env 키 이름으로 조립되므로, 검증 없이 받으면
#   임의 env 를 읽어내는 통로가 된다. Supabase CHECK(029) + Vercel 정규식 + 여기 allowlist
#   3중. 슬러그 출처가 service_role 전용 컬럼이라 이미 신뢰 구간이지만 방어를 겹친다.
_DEFAULT_BROKER: str = "operator"
BROKER_SLUGS: tuple = tuple(
    s for s in (x.strip() for x in os.getenv("BROKER_SLUGS", _DEFAULT_BROKER).split(","))
    if s and s.replace("_", "").isalnum() and s.islower()
)


def broker_credentials(slug: str) -> dict | None:
    """슬러그 → KIS 자격증명 세트. allowlist 밖이거나 미설정이면 None (= fail-closed).

    호출자는 None 을 반드시 거절로 처리해야 한다. 기본 계좌로 폴백하면 남의 실계좌로
    주문이 나간다 — 이 함수가 막으려는 사고가 정확히 그것이다.
    """
    slug = (slug or "").strip()
    if not slug or slug not in BROKER_SLUGS:
        return None
    if slug == _DEFAULT_BROKER:
        key, secret, acct = KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO
    else:
        sfx = slug.upper()
        key = os.getenv(f"KIS_APP_KEY__{sfx}", "").strip().strip('"')
        secret = os.getenv(f"KIS_APP_SECRET__{sfx}", "").strip().strip('"')
        acct = os.getenv(f"KIS_ACCOUNT_NO__{sfx}", "").strip().strip('"')
    if not (key and secret and acct):
        return None
    return {"slug": slug, "app_key": key, "app_secret": secret, "account_no": acct}

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

# ── CORS ────────────────────────────────────────────────────────────────────
# 🚨 2026-08-15 — 기본값이 "*" 였고 배포본이 그 상태였다(실측: 임의 Origin 으로 호출 시
#   `access-control-allow-origin: *` 응답). 이 서버의 시세 라우트(/chart /quotes /snapshot
#   /candles /stream)는 인증이 없어 KIS 실시간 현재가가 그대로 나가므로, 브라우저 경유
#   제3자 사용까지 열려 있었다. 이 프로젝트의 자체 규율은 "KIS raw 시세 = 제3자 재배포 불가,
#   본인 이용은 합법" 이다(api/collectors/fsc_daily_prices.py 상단).
#
#   ⚠️ CORS 는 브라우저 정책일 뿐이다 — curl·서버 호출은 이걸로 막히지 않는다(실측 확인).
#     서버 대 서버 경로(ticker_facts·kis_quote)는 이 변경의 영향을 받지 않는다.
#     여기서 닫는 것은 "제3자 웹사이트가 브라우저 JS 로 우리 시세를 읽어가는" 벡터뿐이다.
#     인증·rate limit 은 별건으로 남아 있다.
#
#   패턴은 vercel-api/api/cors_helper.py 와 동일하게 맞춘다 — 코드 기본 origin 을 두어
#   env 누락·오설정에도 공개 사이트가 죽지 않게 하고, env 의 "*" 는 명시적으로 제거한다.
_DEFAULT_ORIGINS: tuple[str, ...] = (
    "https://www.alphanest.kr",
    "https://alphanest.kr",
    "https://alphanest-psi.vercel.app",   # 오퍼레이터 사이트
)

_env_origins: list[str] = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if o.strip() and o.strip() != "*"      # wildcard 금지 (cors_helper 정합)
]

ALLOWED_ORIGINS: list[str] = list(dict.fromkeys([*_env_origins, *_DEFAULT_ORIGINS]))

# Framer 퍼블리시·프리뷰 도메인 + 로컬 개발. 공개 컴포넌트
# (framer-components/public-probe/RealtimeChartProbe.tsx)가 브라우저에서 EventSource 로
# /stream/{ticker} 를 붙기 때문에, 프리뷰 도메인을 빠뜨리면 라이브 차트가 죽는다.
# 명시 목록으로는 서브도메인을 다 적을 수 없어 regex 로 둔다 (wildcard 아님 — 도메인 고정).
ALLOWED_ORIGIN_REGEX: str = os.getenv(
    "ALLOWED_ORIGIN_REGEX",
    r"^https://([a-z0-9-]+\.)*framer\.(app|website)$|^http://localhost(:\d+)?$",
)

PORT: int = int(os.getenv("PORT", "8000"))

# ── 최적화 상수 ──
IDLE_UNSUB_TTL: int = int(os.getenv("IDLE_UNSUB_TTL", "300"))
MAX_CANDLE_MINUTES: int = int(os.getenv("MAX_CANDLE_MINUTES", "240"))
SSE_QUEUE_SIZE: int = int(os.getenv("SSE_QUEUE_SIZE", "128"))
CLEANUP_INTERVAL: int = int(os.getenv("CLEANUP_INTERVAL", "60"))
MAX_SUBS: int = int(os.getenv("MAX_SUBS", "20"))

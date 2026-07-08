"""
VERITY Health Monitor — 시스템 자가진단 모듈

감시 항목:
  1. API Heartbeat  : DART, FRED, Telegram, Gemini, Anthropic, KIPRIS, 공공데이터, KRX Open API
  2. GitHub Worker   : 최신 GitHub Actions 실행 결과
  3. Data Recency    : portfolio.json / raw_data.json 최종 갱신 시각
  4. Version Sync    : 로컬 vs 원격 커밋 해시 비교
"""
from __future__ import annotations
import os
import json
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

import requests

from api.config import (
    GEMINI_API_KEY,
    ANTHROPIC_API_KEY,
    DART_API_KEY,
    FRED_API_KEY,
    ECOS_API_KEY,
    TELEGRAM_BOT_TOKEN,
    PUBLIC_DATA_API_KEY,
    KRX_API_KEY,
    PORTFOLIO_PATH,
    DATA_DIR,
    KST,
    now_kst,
    DEADMAN_FAIL_THRESHOLD,
)
from api.collectors.krx_openapi import collect_krx_openapi_snapshot, resolve_published_bas_dd

VERSION = "v8.2.0"
GITHUB_REPO = "gywns0126/VERITY"
# WARN-20: API 특성에 맞는 차등 timeout
_TIMEOUT = 8          # 레거시/기본값 (기존 호출부 호환)
_TIMEOUT_FAST = 5     # gemini / anthropic / polygon / telegram
_TIMEOUT_DEFAULT = 8  # 일반
_TIMEOUT_SLOW = 20    # dart / sec_edgar / krx_open_api (대용량/무역통계)


# ── 1. API Heartbeat ──────────────────────────────────────────

def _probe(label: str, fn, retries: int = 1) -> dict:
    """공통 프로브: 성공/실패/응답시간 기록. 1회 재시도로 일시적 네트워크 떨림 완화."""
    last_err = None
    t0 = time.time()
    for attempt in range(retries + 1):
        try:
            ok, detail = fn()
            elapsed = round((time.time() - t0) * 1000)
            return {
                "status": "ok" if ok else "error",
                "latency_ms": elapsed,
                "detail": detail,
                "attempts": attempt + 1,
            }
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(0.5)
    elapsed = round((time.time() - t0) * 1000)
    return {
        "status": "error",
        "latency_ms": elapsed,
        "detail": str(last_err)[:120],
        "attempts": retries + 1,
    }


def _check_dart() -> tuple:
    if not DART_API_KEY:
        return False, "키 미설정"
    r = requests.get(
        "https://opendart.fss.or.kr/api/corpCode.xml",
        params={"crtfc_key": DART_API_KEY},
        timeout=_TIMEOUT_SLOW,
    )
    if r.status_code == 200:
        return True, "정상"
    return False, f"HTTP {r.status_code}"


def _check_ecos() -> tuple:
    # 한국은행 기준금리(722Y001)는 금통위 결정일에만 row 생성 → 매월 데이터 없음.
    # 직전 6개월 범위로 조회해 1 row 라도 있으면 API/키 정상으로 판정.
    if not ECOS_API_KEY:
        return False, "키 미설정"
    k = quote(str(ECOS_API_KEY).strip(), safe="")
    today = now_kst().date()
    end_dt = today.replace(day=1) - timedelta(days=1)
    start_dt = (end_dt.replace(day=1) - timedelta(days=180)).replace(day=1)
    end_ym = end_dt.strftime("%Y%m")
    start_ym = start_dt.strftime("%Y%m")
    r = requests.get(
        f"https://ecos.bok.or.kr/api/StatisticSearch/{k}/json/kr/1/10/722Y001/M/{start_ym}/{end_ym}/0101000",
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    try:
        data = r.json()
    except Exception:
        return False, "JSON 파싱 실패"
    if isinstance(data, dict) and data.get("RESULT"):
        msg = (data.get("RESULT") or {}).get("MESSAGE", "오류")
        return False, str(msg)[:80]
    rows = (data.get("StatisticSearch") or {}).get("row")
    if not rows:
        return False, f"6개월({start_ym}~{end_ym}) 데이터 없음"
    return True, "정상"


def _check_fred() -> tuple:
    if not FRED_API_KEY:
        return False, "키 미설정"
    r = requests.get(
        "https://api.stlouisfed.org/fred/series",
        params={
            "series_id": "DGS10",
            "api_key": FRED_API_KEY,
            "file_type": "json",
        },
        timeout=_TIMEOUT,
    )
    if r.status_code >= 500:
        return False, f"FRED 서버 오류 HTTP {r.status_code}"
    try:
        data = r.json()
    except Exception:
        return False, f"JSON 파싱 실패 (HTTP {r.status_code})"
    if "error_code" in data:
        return False, data.get("error_message", "인증 실패")[:80]
    return True, "정상"


def _check_telegram() -> tuple:
    if not TELEGRAM_BOT_TOKEN:
        return False, "토큰 미설정"
    r = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe",
        timeout=_TIMEOUT_FAST,
    )
    data = r.json()
    if data.get("ok"):
        bot_name = data["result"].get("username", "?")
        return True, f"@{bot_name}"
    return False, data.get("description", "인증 실패")[:80]


def _check_gemini() -> tuple:
    if not GEMINI_API_KEY:
        return False, "키 미설정"
    r = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": GEMINI_API_KEY},
        timeout=_TIMEOUT_FAST,
    )
    if r.status_code == 200:
        return True, "정상"
    if r.status_code == 429:
        return False, "쿼터 초과(429)"
    return False, f"HTTP {r.status_code}"


def _check_anthropic() -> tuple:
    if not ANTHROPIC_API_KEY:
        return False, "키 미설정"
    return True, "키 존재 확인"


def _check_kipris() -> tuple:
    """KIPRIS 실호출 ping — 무료 공공 API 라 매 헬스체크 부담 없음 (2026-05-07)."""
    key = (
        os.environ.get("KIPRIS_API_KEY", "")
        or os.environ.get("KIPRIS_ACCESS_KEY", "")
    ).strip()
    if not key:
        return False, "키 미설정"
    # 가벼운 ping — applicantNameSearchInfo (단일 dummy 출원인)
    try:
        r = requests.get(
            "http://plus.kipris.or.kr/openapi/rest/patUtiModInfoSearchSevice/applicantNameSearchInfo",
            params={"applicant": "삼성전자", "ServiceKey": key, "numOfRows": 1, "pageNo": 1},
            timeout=8,
        )
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        # XML 응답에 'errMsg' 또는 'resultMsg' 권한 에러 검출
        body = (r.text or "")[:500]
        if "errMsg" in body or "INVALID_REQUEST" in body or "SERVICE_ACCESS_DENIED" in body:
            return False, "권한/요청 오류"
        return True, "정상"
    except requests.RequestException as e:
        return False, f"네트워크 {type(e).__name__}"


def _check_reports_signed_url() -> tuple:
    """리포트 PDF signed URL 발급 + fetch HEAD 검증 (2026-05-07 신설).

    배경: 5/3 운영 시작 ~ 5/7 까지 사용자 다운로드 항상 fail. 원인 = signed URL
    합성 path 의 /storage/v1 prefix 누락. 5/7 fix (5c2a93d) 후 재발 방지 영구
    health check 추가. 메모리 feedback_reports_are_brain_learning_input.

    2026-05-09 instrumentation: silent skip 절대 금지 룰
    (feedback_data_collection_verification_mandatory) 정합. fail 시 정확한
    reason stderr print → 운영 로그에서 root cause 즉시 파악 가능.

    검증:
    1. Supabase Storage signed URL 발급 (verity_daily_public.pdf)
    2. URL 로 HEAD fetch → 200 검증
    3. 깨지면 즉시 false → system_health 의 errors 에 기록됨 → 텔레그램 alert
    """
    import sys

    def _fail(reason: str) -> tuple:
        # 운영 로그에 정확한 reason print — fallback "API 키 미설정" 메시지로
        # 가려지지 않도록. health 결과 dict 의 detail 도 동일.
        print(f"[reports_signed_url] FAIL: {reason}", file=sys.stderr, flush=True)
        return False, reason

    SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
    SUPABASE_SR = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not SUPABASE_URL or not SUPABASE_SR:
        # 어느 변수가 비었는지 정확히 — 둘 중 하나만 비면 그것만 기록
        missing: list = []
        if not SUPABASE_URL:
            missing.append("SUPABASE_URL")
        if not SUPABASE_SR:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        return _fail(f"env empty: {' / '.join(missing)} 미설정 (length 0)")
    # diag length (실제 value 노출 안 함, length 만)
    print(
        f"[reports_signed_url] env present — URL_len={len(SUPABASE_URL)}, "
        f"SR_len={len(SUPABASE_SR)}",
        file=sys.stderr, flush=True,
    )
    try:
        # 1) signed URL 발급
        r = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/sign/verity-reports/verity_daily_public.pdf",
            headers={
                "apikey": SUPABASE_SR,
                "Authorization": f"Bearer {SUPABASE_SR}",
                "Content-Type": "application/json",
            },
            json={"expiresIn": 60},
            timeout=8,
        )
        if r.status_code != 200:
            # body 일부 print (key 일부 노출 risk 적음 — error 메시지만)
            body_snip = (r.text or "")[:200].replace("\n", " ")
            return _fail(f"sign HTTP {r.status_code} body={body_snip}")
        body = r.json()
        signed_path = body.get("signedURL") or body.get("signedUrl")
        if not signed_path:
            return _fail(f"signedURL 키 누락 — body keys={list(body.keys())}")
        # 2) /storage/v1 prefix 검증 (옛 결함 재발 방지)
        if not signed_path.startswith("/storage/v1"):
            signed_path = "/storage/v1" + signed_path
        full_url = f"{SUPABASE_URL}{signed_path}" if not signed_path.startswith("http") else signed_path
        # 3) HEAD fetch — 200 검증
        h = requests.head(full_url, timeout=6, allow_redirects=True)
        if h.status_code != 200:
            return _fail(f"signed URL fetch HTTP {h.status_code}")
        return True, "signed URL + fetch 정상"
    except requests.RequestException as e:
        return _fail(f"네트워크 {type(e).__name__}: {str(e)[:120]}")


def _check_public_data() -> tuple:
    """관세청 무역통계 ping — 진짜 운영 endpoint (nitemtrade) 사용 (2026-05-07)."""
    if not PUBLIC_DATA_API_KEY:
        return False, "키 미설정"
    try:
        r = requests.get(
            "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList",
            params={
                "serviceKey": PUBLIC_DATA_API_KEY,
                "strtYymm": "202604", "endYymm": "202604",
                "hsSgnCd": "0101", "cntyCd": "ZZ",
                "numOfRows": 1, "pageNo": 1,
            },
            timeout=8,
        )
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        body = (r.text or "")[:500]
        if "SERVICE_KEY" in body and ("ERROR" in body or "DENIED" in body):
            return False, "키 거부 (SERVICE_KEY_ERROR)"
        if "INVALID" in body and "REQUEST" in body:
            return False, "요청 오류"
        return True, "정상"
    except requests.RequestException as e:
        return False, f"네트워크 {type(e).__name__}"


# ── CRIT-13: US 분석 파이프라인 핵심 API 감시 ──

def _check_finnhub() -> tuple:
    from api.config import FINNHUB_API_KEY
    if not FINNHUB_API_KEY:
        return False, "키 미설정"
    r = requests.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": "AAPL", "token": FINNHUB_API_KEY},
        timeout=_TIMEOUT_FAST,
    )
    if r.status_code == 200 and isinstance(r.json(), dict):
        return True, "정상"
    if r.status_code == 429:
        return False, "쿼터 초과(429)"
    return False, f"HTTP {r.status_code}"


def _check_polygon() -> tuple:
    from api.config import POLYGON_API_KEY
    if not POLYGON_API_KEY:
        return False, "키 미설정"
    r = requests.get(
        "https://api.polygon.io/v2/aggs/ticker/AAPL/prev",
        params={"apiKey": POLYGON_API_KEY},
        timeout=_TIMEOUT_FAST,
    )
    if r.status_code == 200:
        return True, "정상"
    if r.status_code == 429:
        return False, "쿼터 초과(429)"
    return False, f"HTTP {r.status_code}"


def _check_sec_edgar() -> tuple:
    from api.config import SEC_EDGAR_USER_AGENT
    if not SEC_EDGAR_USER_AGENT:
        return False, "User-Agent 미설정"
    r = requests.get(
        "https://data.sec.gov/submissions/CIK0000320193.json",  # Apple CIK
        headers={"User-Agent": SEC_EDGAR_USER_AGENT},
        timeout=_TIMEOUT_SLOW,
    )
    if r.status_code == 200:
        return True, "정상"
    return False, f"HTTP {r.status_code}"


def _check_perplexity() -> tuple:
    """Perplexity API key 존재 검증.

    이전 구현은 GET /models 호출했으나 Perplexity 공식 API 에는 /models 엔드포인트
    없음 → 항상 404 반환 (시스템헬스 오류로 표시됨).

    실호출 검증은 비용 발생 (chat/completions 가 유일한 엔드포인트) — 헬스체크에
    매 사이클 태우기엔 부담. key 포맷 기초 검증만 수행.
    실제 호출 에러는 해당 모듈이 자체 로깅하므로 그쪽 경로에서 감지 가능.
    """
    from api.config import PERPLEXITY_API_KEY
    if not PERPLEXITY_API_KEY:
        return False, "키 미설정"
    if not PERPLEXITY_API_KEY.startswith("pplx-") or len(PERPLEXITY_API_KEY) < 20:
        return False, "키 포맷 이상"
    return True, "키 설정 OK"


def _recent_bas_dd_krx() -> str:
    """KRX OpenAPI 가 실제로 게시한 가장 최근 영업일 YYYYMMDD.

    헬스체크는 18개 sweep 결과를 공휴일·게시 지연 영향 없이 평가해야 false positive 가
    안 난다. probe walk-back 으로 ok 응답 첫 날짜를 잡는다 (KRX OpenAPI 모듈 helper).
    """
    return resolve_published_bas_dd()


def _prev_published_bas_dd_krx(bas_dd: str) -> str:
    """bas_dd 직전의 KRX 게시 영업일 (EOD 게시 전환 윈도 재확인용). 실패 시 ''."""
    try:
        prev = (datetime.strptime(bas_dd, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
    except (ValueError, TypeError):
        return ""
    return resolve_published_bas_dd(start_date=prev)


def _check_krx_open_api() -> tuple:
    """
    KRX OpenAPI 18개 스냅샷 기준 헬스체크.
    - ok/empty/forbidden/error 건수를 요약해 상세 원인 파악 용이하게 제공
    """
    if not KRX_API_KEY:
        return False, "키 미설정"
    snap = collect_krx_openapi_snapshot(
        bas_dd=_recent_bas_dd_krx(),
        max_rows_per_endpoint=1,
    )
    summary = snap.get("summary", {})
    ok = int(summary.get("ok", 0))
    forbidden = int(summary.get("forbidden", 0))
    empty = int(summary.get("empty", 0))
    error = int(summary.get("error", 0))
    total = int(summary.get("total", 0))
    bas_dd = str(snap.get("bas_dd") or "")

    if ok <= 0 and (forbidden > 0 or error > 0):
        # KRX EOD 게시 전환 윈도 race — probe 1개(stk_bydd_trd)가 오늘-ok 라 bas_dd=오늘 선택됐으나
        # 18-sweep 은 오늘 미게시(403/empty) → 키 오류처럼 보이는 오보. 키 유효 여부 = 직전 영업일
        # 재확인으로 판별: 직전일 정상이면 게시 전환 중(키 유효), 직전일도 forbidden 이면 진짜 error.
        prev_bas = _prev_published_bas_dd_krx(bas_dd)
        if prev_bas and prev_bas != bas_dd:
            psnap = collect_krx_openapi_snapshot(bas_dd=prev_bas, max_rows_per_endpoint=1)
            psum = psnap.get("summary", {})
            p_ok = int(psum.get("ok", 0))
            p_total = int(psum.get("total", 0))
            if p_ok > 0 and (p_ok / max(p_total, 1)) >= 0.30:
                return (
                    True,
                    f"오늘 EOD 게시 전환 중 (basDd={bas_dd}: 권한없음 {forbidden}/{total}) — "
                    f"전 영업일 {prev_bas} ok {p_ok}/{p_total} 정상, 키 유효",
                )
        return (
            False,
            f"ok {ok}/{total}, 권한없음 {forbidden}, 오류 {error}, 빈데이터 {empty} (basDd={bas_dd})",
        )
    # 2026-05-07 추가: ok rate < 30% 면 false positive 방지 (이전 = 16/18 empty 인데 ok 표시)
    ok_rate = ok / max(total, 1)
    if total > 0 and ok_rate < 0.30:
        return (
            False,
            f"degradation: ok {ok}/{total} ({ok_rate:.0%}), 빈데이터 {empty}, 권한없음 {forbidden}, 오류 {error} (basDd={bas_dd})",
        )
    return (
        True,
        f"ok {ok}/{total}, 권한없음 {forbidden}, 오류 {error}, 빈데이터 {empty} (basDd={bas_dd})",
    )


def check_api_health() -> dict:
    """모든 API 상태를 한 번에 점검.
    CRIT-13: Finnhub/Polygon/SEC EDGAR/Perplexity 를 감시 대상에 포함해
    US 분석 파이프라인 블랙홀을 deadman이 탐지할 수 있게 함."""
    checks = {
        "dart": _probe("DART", _check_dart),
        "fred": _probe("FRED", _check_fred),
        "telegram": _probe("Telegram", _check_telegram),
        "gemini": _probe("Gemini", _check_gemini),
        "anthropic": _probe("Anthropic", _check_anthropic),
        "kipris": _probe("KIPRIS", _check_kipris),
        "public_data": _probe("공공데이터", _check_public_data),
        "krx_open_api": _probe("KRX Open API", _check_krx_open_api),
        "reports_signed_url": _probe("리포트 signed URL", _check_reports_signed_url),
    }
    if ECOS_API_KEY:
        checks["ecos"] = _probe("ECOS", _check_ecos)

    # US 파이프라인 핵심 — 키가 설정된 경우만 감시 (미설정 시 optional 취급)
    from api.config import (
        FINNHUB_API_KEY,
        POLYGON_API_KEY,
        SEC_EDGAR_USER_AGENT,
        PERPLEXITY_API_KEY,
    )
    if FINNHUB_API_KEY:
        checks["finnhub"] = _probe("Finnhub", _check_finnhub)
    if POLYGON_API_KEY:
        checks["polygon"] = _probe("Polygon", _check_polygon)
    if SEC_EDGAR_USER_AGENT:
        checks["sec_edgar"] = _probe("SEC EDGAR", _check_sec_edgar)
    if PERPLEXITY_API_KEY:
        checks["perplexity"] = _probe("Perplexity", _check_perplexity)
    return checks


# ── 2. GitHub Worker ──────────────────────────────────────────

def check_github_worker() -> dict:
    """최신 GitHub Actions 워크플로 실행 결과 확인.

    2026-05-17 audit 후속 큐 — per_page=3 fetch 후 latest 1개 표시 시
    Price Pulse (매분 dispatch_chain) 가 거의 항상 "running" 으로 표시됨 → 사용자 가치 ~0.
    개선 후보 (Phase 2): critical workflow filter (universe_scan / macro_collect /
    daily_analysis / dart_batch) 만 모니터 + 최근 N run 의 success rate 표시.
    """
    try:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs",
            params={"per_page": 3},
            headers={"Accept": "application/vnd.github+json"},
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return {"status": "unknown", "detail": f"GitHub API HTTP {r.status_code}"}

        runs = r.json().get("workflow_runs", [])
        if not runs:
            return {"status": "unknown", "detail": "실행 이력 없음"}

        latest = runs[0]
        conclusion = latest.get("conclusion") or latest.get("status", "unknown")
        run_started = latest.get("run_started_at", "")
        name = latest.get("name", "")
        run_url = latest.get("html_url", "")

        # GitHub API: status ∈ {queued, in_progress, pending, waiting, requested, completed}
        #             conclusion ∈ {success, failure, cancelled, timed_out, skipped, neutral, action_required, startup_failure} (완료 시만)
        # 명백한 실패만 error, 진행 중/대기 상태는 running, 나머지(success/skipped/neutral) 는 ok.
        FAILURE_CONCLUSIONS = ("failure", "cancelled", "timed_out", "action_required", "startup_failure")
        RUNNING_STATUSES = ("in_progress", "queued", "pending", "waiting", "requested")
        if conclusion == "success":
            status = "ok"
        elif conclusion in FAILURE_CONCLUSIONS:
            status = "error"
        elif conclusion in RUNNING_STATUSES:
            status = "running"
        else:
            # skipped / neutral / unknown — 실패도 진행도 아님, 정보 부족이라 ok 처리
            status = "ok"

        return {
            "status": status,
            "conclusion": conclusion,
            "workflow": name,
            "started_at": run_started,
            "url": run_url,
            "detail": f"{name}: {conclusion}",
        }
    except Exception as e:
        return {"status": "unknown", "detail": str(e)[:120]}


# ── 3. Data Recency ──────────────────────────────────────────

def _file_age_hours(path: str) -> Optional[float]:
    """파일 수정 시각 → 현재까지 경과 시간(시)"""
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    mtime_dt = datetime.fromtimestamp(mtime, tz=KST)
    delta = now_kst() - mtime_dt
    return round(delta.total_seconds() / 3600, 2)


def check_data_recency() -> dict:
    """주요 데이터 파일의 최종 갱신 시각과 경과 시간 확인.

    파일별 적정 threshold (성격 고려):
      portfolio       — 실시간 분석, 24h 초과 시 error
      trade_analysis  — 일일 갱신, 24h 초과 시 warning
      raw_data        — DART 연간 공시 (3-4월), 365일 threshold. 이벤트성이라
                        연중 대부분 기간에 stale 표시되면 의미없음.
      history         — VAMS 매매 이벤트 로그. 매매 없으면 갱신 없는 게 정상
                        → recency 체크 제외 (존재 여부만 확인)
    """
    # (path, stale_threshold_hours 또는 None=체크안함)
    # 2026-05-17 audit: Phase 2-B 핵심 cron 산출물 3종 추가 — silent skip detect.
    #   universe_candidates  (universe_scan.yml, 평일 KST 15:30, daily) → 26h
    #   dart_fundamentals_kr (dart_batch.yml, weekly)                    → 8d (192h)
    #   macro_snapshot       (macro_collect.yml, 30분 cron)              → 1h
    # data_pipeline_health.json 자체 = 위 3 builder 의 편승 산출물이라 자연 정합 — 별도 추가 X.
    specs = {
        "portfolio":            (PORTFOLIO_PATH,                                       24),
        "trade_analysis":       (os.path.join(DATA_DIR, "trade_analysis.json"),        48),
        "raw_data":             (os.path.join(DATA_DIR, "raw_data.json"),              365 * 24),
        "history":              (os.path.join(DATA_DIR, "history.json"),               None),
        "universe_candidates":  (os.path.join(DATA_DIR, "universe_candidates.json"),   26),
        "dart_fundamentals_kr": (os.path.join(DATA_DIR, "dart_fundamentals_kr.json"),  192),
        "macro_snapshot":       (os.path.join(DATA_DIR, "macro_snapshot.json"),        1),
    }
    result = {}
    overall_status = "ok"

    for key, (path, threshold) in specs.items():
        if not os.path.exists(path):
            result[key] = {"status": "missing", "detail": "파일 없음"}
            overall_status = "warning"
            continue

        age_h = _file_age_hours(path)
        mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=KST)
        mtime_str = mtime.strftime("%Y-%m-%d %H:%M")

        if threshold is None:
            # 이벤트 기반 파일 — 갱신 시각 불문 fresh 로 기록
            status = "event_based"
        elif age_h is not None and age_h > threshold:
            status = "stale"
            if key == "portfolio":
                overall_status = "error"
            elif overall_status != "error":
                overall_status = "warning"
        else:
            status = "fresh"

        result[key] = {
            "status": status,
            "last_updated": mtime_str,
            "age_hours": age_h,
            "threshold_hours": threshold,
        }

    updated_at = None
    try:
        with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
            pdata = json.loads(f.read().replace("NaN", "null"))
        updated_at = pdata.get("updated_at")
    except Exception:
        pass

    return {
        "status": overall_status,
        "updated_at": updated_at,
        "files": result,
    }


# ── 4. Version Sync ──────────────────────────────────────────

def check_version_sync() -> dict:
    """로컬 버전 vs 원격 최신 커밋 비교"""
    result = {"local_version": VERSION, "status": "ok"}

    try:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/commits",
            params={"per_page": 1},
            headers={"Accept": "application/vnd.github+json"},
            timeout=_TIMEOUT,
        )
        if r.status_code == 200:
            commits = r.json()
            if commits:
                latest = commits[0]
                result["remote_sha"] = latest["sha"][:7]
                result["remote_message"] = latest["commit"]["message"][:80]
                result["remote_date"] = latest["commit"]["committer"]["date"]
    except Exception as e:
        result["detail"] = str(e)[:120]
        result["status"] = "unknown"

    try:
        import subprocess
        local_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode().strip()
        result["local_sha"] = local_sha

        if result.get("remote_sha") and local_sha != result["remote_sha"]:
            # cron 자동 commit 은 self-update false positive — health check 가 자기 자신
            # commit 을 "업데이트" 로 오인.
            # 2026-05-17 Phase 3 audit: cron yml 의 `git commit -m "..."` string 전수 sweep.
            # 옛 list (📊 📡 📑 📋) 중 📋 = dead (어떤 cron 도 사용하지 않음) 제거.
            # `[verity-earnings-prep]` = eps_estimate_snapshot.yml (text prefix, 유일).
            # 신 cron 추가 시 이 list 도 정합 의무 (CLAUDE.md RULE 4 sentinel).
            msg = result.get("remote_message", "")
            CRON_AUTO_PREFIXES = (
                # emoji prefix — yml 에서 git commit -m "<emoji> ..." 붙은 거
                "📊 ",   # atr_phase_0_verdict / bond_etf / equity_research_brief / macro_collect
                "🔐 ",   # daily_analysis_full / daily_analysis / daily_realtime / kis_token_refresh
                "🏛️ ",  # dart_batch
                "🏛 ",   # dart_batch 변형 (배리언트)
                "🔍 ",   # universe_scan / scout_penny
                "📡 ",   # rss_scout / r_one_freshness
                # (ESTATE 폐기 2026-05-21: 🧠 🧭 📰 📐 📅 + 📊/🔍/📡 의 estate cron 제거)
                "📦 ",   # export_trade_daily
                "🔔 ",   # operator_deadman
                "💓 ",   # price_pulse
                "📑 ",   # reports_v2_cron
                "📜 ",   # sec_8k_alert
                "📈 ",   # site_growth_daily / trade_plan_followup
                "🎯 ",   # cockpit_aggregate (5분 cron, 2026-05-27)
                "🩺 ",   # cron_health_audit (daily, 2026-05-27)
                # text prefix
                "[verity-earnings-prep] ",   # eps_estimate_snapshot
            )
            if msg.startswith(CRON_AUTO_PREFIXES):
                result["status"] = "ok"
                result["detail"] = f"cron 자동 갱신 — {msg[:40]}"
            else:
                result["status"] = "update_available"
                result["detail"] = "새로운 커밋이 원격에 존재합니다"
    except Exception:
        result["local_sha"] = "unknown"

    return result


# ── 종합 진단 ──────────────────────────────────────────────

def run_health_check() -> dict:
    """
    전체 시스템 자가진단 실행 → portfolio.json에 저장될 구조 반환

    반환 예시:
    {
      "status": "warning",
      "checked_at": "2026-04-05T15:30:00+09:00",
      "version": "v8.1.0",
      "api_health": { "dart": {...}, "gemini": {...}, ... },
      "github_worker": {...},
      "data_recency": {...},
      "version_sync": {...},
      "errors": ["DART API 인증 실패"],
      "warnings": ["raw_data.json 24시간 이상 경과"]
    }
    """
    print("\n[HEALTH] 시스템 자가진단 시작")
    t0 = time.time()

    api_health = check_api_health()
    github_worker = check_github_worker()
    data_recency = check_data_recency()
    version_sync = check_version_sync()

    errors = []
    warnings = []

    api_labels = {
        "dart": "DART 재무",
        "fred": "FRED 매크로",
        "telegram": "Telegram 알림",
        "gemini": "Gemini AI",
        "anthropic": "Claude AI",
        "kipris": "KIPRIS 특허",
        "public_data": "관세청 무역",
        "krx_open_api": "KRX Open API",
    }
    for key, info in api_health.items():
        label = api_labels.get(key, key)
        if info["status"] == "error":
            detail = info.get("detail", "")
            if "미설정" in detail:
                warnings.append(f"{label} API 키 미설정")
            elif "쿼터" in detail:
                warnings.append(f"{label} API 쿼터 초과")
            else:
                errors.append(f"{label} API 오류 — {detail}")

    if github_worker.get("status") == "error":
        errors.append(
            f"GitHub Actions 실패 — {github_worker.get('workflow', '?')}: "
            f"{github_worker.get('conclusion', '?')}"
        )

    files = data_recency.get("files", {})
    for fname, finfo in files.items():
        if finfo.get("status") == "stale":
            age = finfo.get("age_hours", 0)
            thr = finfo.get("threshold_hours", 24)
            warnings.append(f"{fname} 데이터 {age:.0f}시간 경과 ({thr:.0f}h 초과)")
        elif finfo.get("status") == "missing":
            warnings.append(f"{fname} 파일 없음")
        # event_based / fresh 는 warning 아님

    # 2026-05-17 audit: version_sync update_available 는 정보 (자기 commit detect) 라 warnings 에서 제외.
    # SystemHealthBar 가 별도 versionBadge UI 로 표시. warnings 에 두면 site status="warning" false positive
    # (사용자/cron 이 git push 직후 ~30분 매 cron 마다 warning 표시 — 운영 alert 아닌 noise).
    # 운영 alert 가치 있는 update 는 cron prefix 회피 로직 (line ~615 CRON_AUTO_PREFIXES) 이 이미 처리.

    if errors:
        overall = "error"
    elif warnings:
        overall = "warning"
    else:
        overall = "ok"

    elapsed_ms = round((time.time() - t0) * 1000)

    result = {
        "status": overall,
        "checked_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "version": VERSION,
        "elapsed_ms": elapsed_ms,
        "api_health": api_health,
        "github_worker": github_worker,
        "data_recency": data_recency,
        "version_sync": version_sync,
        "errors": errors,
        "warnings": warnings,
    }

    ok_count = sum(1 for v in api_health.values() if v["status"] == "ok")
    total_count = len(api_health)
    print(f"  API: {ok_count}/{total_count} 정상")
    print(f"  Worker: {github_worker.get('status', '?')} — {github_worker.get('detail', '')}")
    print(f"  데이터: {data_recency.get('status', '?')} — 최종 {data_recency.get('updated_at', '?')}")
    print(f"  버전: {version_sync.get('local_version', '?')} ({version_sync.get('local_sha', '?')})")
    if errors:
        for e in errors:
            print(f"  ❌ {e}")
    if warnings:
        for w in warnings:
            print(f"  ⚠️ {w}")
    print(f"  진단 완료: {elapsed_ms}ms | 종합: {overall.upper()}")

    return result


# ── Deadman's Switch ──────────────────────────────────

# 값 자체가 깨졌는지(0 / nan / 음수 / 자릿수 오류 등 garbage) 잡는 corruption 가드.
# 실 시장 변동을 제약하는 게 아니라 "명백히 불가능한 값"만 걸러야 함 → 폭은 넓게.
# 2026-07-08 재정정: KOSPI 상한 5000 = stale. 실측 sparkline 7484~9114(2026 KR 강세 레짐),
#   실제 값 7246 을 오탐 → Deadman 오발동(사용자 격분). 상한을 레짐+헤드룸으로 대폭 상향.
#   (하한은 0/음수 garbage 만 걸리게 유지 — 실 폭락도 통과해야 함.)
_DATA_SANITY_RULES = {
    "kospi": (1000, 15000),
    "kosdaq": (300, 6000),
    "vix": (5, 120),
    "usd_krw": (900, 2200),
}

# Brain Audit §2-B: 핵심/비핵심 API 가중 점수제.
# 핵심 API (분석 결과 정확성에 직접 영향) — 가중치 1.0
# 비핵심 API (알림/보조 데이터) — 가중치 0.3
# 임계: weighted_score >= 3.0 (또는 sanity anomaly >= 2)
CRITICAL_APIS = frozenset({
    "gemini",        # AI 1차 판정
    "anthropic",     # AI 2차 검증
    "dart",          # KR 재무
    "krx_open_api",  # KR 시장 데이터 (코드상 키 — 사용자 명세의 'pykrx' 와 동치)
    "fred",          # US 매크로
    "finnhub",       # US 펀더멘털 (CRIT-13 추가)
    "polygon",       # US 가격/옵션 (CRIT-13 추가)
    "sec_edgar",     # US SEC 공시 (CRIT-13 추가)
})
NON_CRITICAL_WEIGHT = 0.3
CRITICAL_WEIGHT = 1.0
WEIGHTED_ABORT_THRESHOLD = 3.0


def validate_deadman_switch(
    system_health: dict,
    market_summary: Optional[dict] = None,
    macro: Optional[dict] = None,
) -> tuple:
    """
    Deadman's Switch — 데이터 소스 가중 점수 또는 값 이상 시 분석 중단.

    가중치 모델 (Brain Audit §2-B):
      핵심 API 1개 다운 = 1.0 점, 비핵심 1개 다운 = 0.3 점
      → weighted_score >= 3.0 이면 abort (예: 핵심 3개 OR 핵심 2 + 비핵심 4)

    Returns:
        (should_abort: bool, reasons: list[str])
    """
    reasons = []

    api_health = system_health.get("api_health", {})
    # KRX는 키+API별 이용신청 이중 구조라, 스모크 실패만으로 전체 파이프라인을 멈추지 않음
    # → 가중치는 적용하되 별도 optional 리스트에서는 제외
    _deadman_optional_apis = frozenset({"krx_open_api"})
    failed_apis = [
        key for key, info in api_health.items()
        if key not in _deadman_optional_apis
        and info.get("status") == "error"
        and "미설정" not in info.get("detail", "")
    ]
    # Brain Audit §2-B: 가중 점수 계산
    weighted_score = sum(
        CRITICAL_WEIGHT if api in CRITICAL_APIS else NON_CRITICAL_WEIGHT
        for api in failed_apis
    )
    if weighted_score >= WEIGHTED_ABORT_THRESHOLD:
        crit_failed = [a for a in failed_apis if a in CRITICAL_APIS]
        noncrit_failed = [a for a in failed_apis if a not in CRITICAL_APIS]
        detail_parts = []
        if crit_failed:
            detail_parts.append(f"핵심 {len(crit_failed)}개({', '.join(crit_failed)})")
        if noncrit_failed:
            detail_parts.append(f"비핵심 {len(noncrit_failed)}개({', '.join(noncrit_failed)})")
        reasons.append(
            f"API 가중 점수 {weighted_score:.1f} >= {WEIGHTED_ABORT_THRESHOLD} "
            f"({' / '.join(detail_parts)})"
        )

    if market_summary:
        for key, (lo, hi) in _DATA_SANITY_RULES.items():
            val = None
            if key in ("kospi", "kosdaq"):
                val = market_summary.get(key, {}).get("value")
            elif macro:
                if key == "usd_krw":
                    val = macro.get("usd_krw", {}).get("value")
                elif key == "vix":
                    val = macro.get("vix", {}).get("value")
            if val is not None:
                try:
                    v = float(val)
                    if v < lo or v > hi:
                        reasons.append(
                            f"{key} 값 이상: {v} (정상 범위 {lo}~{hi})"
                        )
                except (ValueError, TypeError):
                    pass

    # 발동 조건:
    #   (a) API 가중 점수 임계 초과 + 어떤 anomaly든 1개 이상 (= reasons 비어있지 않음 보장)
    #   (b) sanity anomaly 2개 이상 (API 정상이어도 데이터 값 자체가 비정상)
    anomaly_count = len(reasons)
    should_abort = anomaly_count >= 1 and weighted_score >= WEIGHTED_ABORT_THRESHOLD
    if not should_abort and anomaly_count >= 2:
        should_abort = True

    return should_abort, reasons

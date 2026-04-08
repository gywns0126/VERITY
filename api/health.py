"""
VERITY Health Monitor — 시스템 자가진단 모듈

감시 항목:
  1. API Heartbeat  : DART, FRED, Telegram, Gemini, Anthropic, KIPRIS, 공공데이터, KRX Open API
  2. GitHub Worker   : 최신 GitHub Actions 실행 결과
  3. Data Recency    : portfolio.json / raw_data.json 최종 갱신 시각
  4. Version Sync    : 로컬 vs 원격 커밋 해시 비교
"""
import os
import json
import time
import traceback
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

VERSION = "v8.2.0"
GITHUB_REPO = "gywns0126/VERITY"
_TIMEOUT = 8


# ── 1. API Heartbeat ──────────────────────────────────────────

def _probe(label: str, fn) -> dict:
    """공통 프로브: 성공/실패/응답시간 기록"""
    t0 = time.time()
    try:
        ok, detail = fn()
        elapsed = round((time.time() - t0) * 1000)
        return {
            "status": "ok" if ok else "error",
            "latency_ms": elapsed,
            "detail": detail,
        }
    except Exception as e:
        elapsed = round((time.time() - t0) * 1000)
        return {
            "status": "error",
            "latency_ms": elapsed,
            "detail": str(e)[:120],
        }


def _check_dart() -> tuple:
    if not DART_API_KEY:
        return False, "키 미설정"
    r = requests.get(
        "https://opendart.fss.or.kr/api/corpCode.xml",
        params={"crtfc_key": DART_API_KEY},
        timeout=_TIMEOUT,
    )
    if r.status_code == 200:
        return True, "정상"
    return False, f"HTTP {r.status_code}"


def _check_ecos() -> tuple:
    if not ECOS_API_KEY:
        return False, "키 미설정"
    k = quote(str(ECOS_API_KEY).strip(), safe="")
    today = now_kst().date()
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    ym = last_prev.strftime("%Y%m")
    r = requests.get(
        f"https://ecos.bok.or.kr/api/StatisticSearch/{k}/json/kr/1/1/722Y001/M/{ym}/{ym}/0101000",
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
    if rows is None:
        return False, "데이터 없음"
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
    data = r.json()
    if "error_code" in data:
        return False, data.get("error_message", "인증 실패")[:80]
    return True, "정상"


def _check_telegram() -> tuple:
    if not TELEGRAM_BOT_TOKEN:
        return False, "토큰 미설정"
    r = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe",
        timeout=_TIMEOUT,
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
        timeout=_TIMEOUT,
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
    key = (
        os.environ.get("KIPRIS_API_KEY", "")
        or os.environ.get("KIPRIS_ACCESS_KEY", "")
    ).strip()
    if not key:
        return False, "키 미설정"
    return True, "키 존재 확인"


def _check_public_data() -> tuple:
    if not PUBLIC_DATA_API_KEY:
        return False, "키 미설정"
    return True, "키 존재 확인"


def _recent_bas_dd_krx() -> str:
    """KST 기준 최근 평일(월~금) YYYYMMDD — 공휴일은 API가 빈 목록을 줄 수 있음."""
    d = now_kst().date()
    for _ in range(14):
        if d.weekday() < 5:
            return d.strftime("%Y%m%d")
        d -= timedelta(days=1)
    return now_kst().strftime("%Y%m%d")


def _check_krx_open_api() -> tuple:
    """
    유가증권 일별매매정보(stk_bydd_trd)로 키·권한 스모크 테스트.
    이 API에 이용신청이 안 되어 있으면 403 등으로 실패할 수 있음 → docs/KRX_OPEN_API_SETUP.md 참고.
    """
    if not KRX_API_KEY:
        return False, "키 미설정"
    bas_dd = _recent_bas_dd_krx()
    try:
        r = requests.get(
            "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd",
            params={"AUTH_KEY": KRX_API_KEY, "basDd": bas_dd},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        return False, str(e)[:80]
    if r.status_code == 401:
        return False, "401 인증 실패"
    if r.status_code == 403:
        return False, "403 권한없음(API별 이용신청)"
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    try:
        data = r.json()
    except Exception:
        return False, "JSON 아님"
    if "OutBlock_1" not in data:
        return False, "응답 형식 이상"
    return True, f"정상 basDd={bas_dd}"


def check_api_health() -> dict:
    """모든 API 상태를 한 번에 점검"""
    checks = {
        "dart": _probe("DART", _check_dart),
        "fred": _probe("FRED", _check_fred),
        "telegram": _probe("Telegram", _check_telegram),
        "gemini": _probe("Gemini", _check_gemini),
        "anthropic": _probe("Anthropic", _check_anthropic),
        "kipris": _probe("KIPRIS", _check_kipris),
        "public_data": _probe("공공데이터", _check_public_data),
        "krx_open_api": _probe("KRX Open API", _check_krx_open_api),
    }
    if ECOS_API_KEY:
        checks["ecos"] = _probe("ECOS", _check_ecos)
    return checks


# ── 2. GitHub Worker ──────────────────────────────────────────

def check_github_worker() -> dict:
    """최신 GitHub Actions 워크플로 실행 결과 확인"""
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

        status = "ok" if conclusion == "success" else "error"
        if conclusion in ("in_progress", "queued"):
            status = "running"

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
    """주요 데이터 파일의 최종 갱신 시각과 경과 시간 확인"""
    files = {
        "portfolio": PORTFOLIO_PATH,
        "raw_data": os.path.join(DATA_DIR, "raw_data.json"),
        "trade_analysis": os.path.join(DATA_DIR, "trade_analysis.json"),
        "history": os.path.join(DATA_DIR, "history.json"),
    }
    result = {}
    overall_status = "ok"

    for key, path in files.items():
        if not os.path.exists(path):
            result[key] = {"status": "missing", "detail": "파일 없음"}
            overall_status = "warning"
            continue

        age_h = _file_age_hours(path)
        mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=KST)
        mtime_str = mtime.strftime("%Y-%m-%d %H:%M")

        if age_h is not None and age_h > 24:
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
            warnings.append(f"{fname} 데이터 {age:.0f}시간 경과 (24h 초과)")
        elif finfo.get("status") == "missing":
            warnings.append(f"{fname} 파일 없음")

    if version_sync.get("status") == "update_available":
        warnings.append(
            f"새 업데이트 감지 — {version_sync.get('remote_message', '?')}"
        )

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

_DATA_SANITY_RULES = {
    "kospi": (1000, 5000),
    "kosdaq": (300, 2500),
    "vix": (5, 120),
    "usd_krw": (900, 1800),
}


def validate_deadman_switch(
    system_health: dict,
    market_summary: Optional[dict] = None,
    macro: Optional[dict] = None,
) -> tuple:
    """
    Deadman's Switch — 데이터 소스 3개 이상 실패 또는 값 이상 시 분석 중단.

    Returns:
        (should_abort: bool, reasons: list[str])
    """
    reasons = []

    api_health = system_health.get("api_health", {})
    # KRX는 키+API별 이용신청 이중 구조라, 스모크 실패만으로 전체 파이프라인을 멈추지 않음
    _deadman_optional_apis = frozenset({"krx_open_api"})
    failed_apis = [
        key for key, info in api_health.items()
        if key not in _deadman_optional_apis
        and info.get("status") == "error"
        and "미설정" not in info.get("detail", "")
    ]
    if len(failed_apis) >= DEADMAN_FAIL_THRESHOLD:
        reasons.append(
            f"API {len(failed_apis)}개 응답 불가: {', '.join(failed_apis)}"
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

    anomaly_count = len(reasons)
    should_abort = anomaly_count >= 1 and len(failed_apis) >= DEADMAN_FAIL_THRESHOLD
    if not should_abort and anomaly_count >= 2:
        should_abort = True

    return should_abort, reasons

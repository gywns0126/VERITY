"""
GET /api/estate/health — ESTATE 부동산 고유 자원 헬스체크 (P2 진짜 wire — 2026-05-17)

인프라 표준 v1.1 — endpoint 네임스페이스:
    /api/system/*  = ESTATE/VERITY 공용
    /api/estate/*  = 부동산 고유 (R-ONE/LANDEX/정책)
    /api/verity/*  = 주식 고유

2026-05-17 P2 wire (B1+B2+B3 통합):
    - 옛 P1 mock (landex_cron/policy_cron/data_go_kr_policy hardcoded) 폐기.
    - 진짜 source = data/metadata/estate_system_health.json (R-ONE + LANDEX 메타-검증 verdict)
      + data/estate_policy_archive.jsonl (정책 cron mtime archived_at).
    - estate_change_feed.py read-through 패턴 정합 (SOURCE_URL_ENV 환경변수, fetch fail 시 503).
    - scenario=mock 으로 옛 mock 응답 보존 (Framer 개발 toggle).

Query parameters:
    scenario = "live" (default) | "mock"

응답 schema = contract_system_pulse.md §1 Resource schema (id/label_ko/status/metric/note).

자원 5종 (live):
    1. r_one_weekly         — R-ONE 매매가격지수 (estate_system_health.sources)
    2. r_one_unsold         — R-ONE 미분양 (estate_system_health.sources)
    3. landex_meta_validation — LANDEX 메타-검증 (estate_system_health.meta_validation)
    4. policy_archive       — 정책 수집 cron (estate_policy_archive.jsonl 마지막 archived_at)
    5. estate_api_keys      — ESTATE 외부 API 키 env 검증 (5종: publicdata/ecos/seoul_data/seoul_subway/kosis)
                              ↑ landex_health.py 흡수 (2026-05-17 B5 cleanup — dead endpoint 통합)

거짓말 트랩:
    T1  fabricate 금지   — fetch fail 시 status=unknown + note="source fetch failed" (가짜 healthy X)
    T2  mock fallback X  — scenario=live 가 fetch fail 시 mock 으로 떨어지지 않음 (status=unknown)
    T29 source URL 절대  — SOURCE_URL_ENV 가 절대 URL
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# read-through source URL — env override 가능. fallback 은 public raw.githubusercontent main
# (비-secret, gh-pages root publish 가 아니라 main 의 metadata 폴더 직접 read).
ESH_SOURCE_URL_ENV = "ESTATE_SYSTEM_HEALTH_SOURCE_URL"
ESH_FALLBACK_URL = (
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/"
    "data/metadata/estate_system_health.json"
)
POLICY_SOURCE_URL_ENV = "ESTATE_POLICY_ARCHIVE_SOURCE_URL"
POLICY_FALLBACK_URL = (
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/"
    "data/estate_policy_archive.jsonl"
)

TIMEOUT_SEC = 4            # vercel.json maxDuration=5 안전 마진
CACHE_MAX_AGE = 300        # 5분 — R-ONE/LANDEX 갱신 주기 (일/주) 정합


# ─────────────────────────────────────────────────
# Live fetch helpers
# ─────────────────────────────────────────────────

def _fetch_estate_system_health() -> dict | None:
    """estate_system_health.json read-through (JSON dict)."""
    url = (os.environ.get(ESH_SOURCE_URL_ENV) or ESH_FALLBACK_URL).strip()
    try:
        # cache-buster — 빈도 낮은 갱신이지만 stale 회피
        r = requests.get(f"{url}?_={int(time.time())}", timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        _logger.error("estate_health: ESH fetch failed: %s", e)
        return None
    if r.status_code != 200:
        _logger.error("estate_health: ESH source returned %d", r.status_code)
        return None
    try:
        payload = r.json()
    except (ValueError, json.JSONDecodeError) as e:
        _logger.error("estate_health: ESH invalid JSON: %s", e)
        return None
    return payload if isinstance(payload, dict) else None


def _fetch_policy_last_archived_at() -> str | None:
    """estate_policy_archive.jsonl 마지막 line 의 archived_at (ISO ts).

    raw.githubusercontent 가 매우 작은 jsonl 도 통째 fetch 함 — 50KB 안쪽이라 OK.
    P3 최적화 = HTTP Range 헤더로 tail 만 fetch 가능.
    """
    url = (os.environ.get(POLICY_SOURCE_URL_ENV) or POLICY_FALLBACK_URL).strip()
    try:
        r = requests.get(f"{url}?_={int(time.time())}", timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        _logger.error("estate_health: policy fetch failed: %s", e)
        return None
    if r.status_code != 200:
        _logger.error("estate_health: policy source returned %d", r.status_code)
        return None
    text = r.text or ""
    # 마지막 non-empty line parse
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            return d.get("archived_at") or d.get("published_at")
        except (ValueError, json.JSONDecodeError):
            continue
    return None


def _iso_to_kst(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────────
# Resource builders
# ─────────────────────────────────────────────────

def _resource_r_one(source_key: str, label_ko: str, esh_sources: dict, max_freshness_days: int) -> dict:
    """R-ONE 자원 1건 build (estate_system_health.sources.<key>)."""
    rs = (esh_sources or {}).get(source_key) or {}
    rs_status = (rs.get("status") or "unknown").lower()
    # estate_system_health.json 의 doc.freshness_thresholds_days 임계와 정합:
    #   warning 이상 = degraded, 이외 healthy
    status = "healthy" if rs_status == "ok" else (
        "degraded" if rs_status in ("warning", "stale") else "unknown"
    )
    return {
        "id": source_key,
        "label_ko": label_ko,
        "status": status,
        "metric": {
            "last_success_at": rs.get("last_probe_at"),
            "freshness_days": rs.get("freshness_days"),
            "as_of_date": rs.get("as_of_date"),
            "max_freshness_days": max_freshness_days,
        },
        "note": rs.get("detail"),
    }


def _resource_landex(meta_validation: dict) -> dict:
    """LANDEX 메타-검증 자원 build (estate_system_health.meta_validation)."""
    mv = meta_validation or {}
    active = (mv.get("active_verdict") or "unknown").lower()
    # active_verdict = ready → healthy. manual_review/invalidated → degraded.
    status = "healthy" if active == "ready" else (
        "degraded" if active in ("manual_review", "invalidated") else "unknown"
    )
    metrics = mv.get("metrics") or {}
    return {
        "id": "landex_meta_validation",
        "label_ko": "LANDEX 메타-검증",
        "status": status,
        "metric": {
            "last_success_at": mv.get("last_run_at"),
            "active_verdict": active,
            "latest_verdict": mv.get("latest_verdict"),
            "stability_counter": mv.get("stability_counter"),
            "tier_change_rate": metrics.get("tier_change_rate"),
            "landex_mean_drift": metrics.get("landex_mean_drift"),
        },
        "note": (
            f"verdict={active} (stability {mv.get('stability_counter', 0)}/3)"
            if active != "unknown" else None
        ),
    }


def _resource_estate_api_keys(now: datetime) -> dict:
    """ESTATE 외부 API 키 env 검증 (landex_health.py 흡수).

    publicdata/ecos/seoul_data/seoul_subway/kosis 5종 env 존재 여부만 확인.
    실제 API call X (비용/quota 회피).
    """
    keys = {
        "publicdata":   bool((os.environ.get("PUBLIC_DATA_API_KEY") or "").strip()),
        "ecos":         bool((os.environ.get("ECOS_API_KEY") or "").strip()),
        "seoul_data":   bool((os.environ.get("SEOUL_DATA_API_KEY") or "").strip()),
        "seoul_subway": bool((os.environ.get("SEOUL_SUBWAY_API_KEY") or "").strip()),
        "kosis":        bool((os.environ.get("KOSIS_API_KEY") or "").strip()),
    }
    missing = [k for k, v in keys.items() if not v]
    n_ok = len(keys) - len(missing)
    if not missing:
        status, note = "healthy", None
    elif len(missing) <= 2:
        status = "degraded"
        note = f"미설정 키: {', '.join(missing)}"
    else:
        status = "down"
        note = f"{len(missing)}/5 키 미설정 — ESTATE 외부 데이터 수집 중단 위험"
    return {
        "id": "estate_api_keys",
        "label_ko": "ESTATE 외부 API 키",
        "status": status,
        "metric": {
            "configured": keys,
            "n_ok": n_ok,
            "n_total": len(keys),
            "checked_at": now.isoformat(timespec="seconds"),
        },
        "note": note,
    }


def _resource_policy(now: datetime) -> dict:
    """정책 수집 cron 자원 build (estate_policy_archive.jsonl 마지막 archived_at mtime)."""
    last_ts = _fetch_policy_last_archived_at()
    dt = _iso_to_kst(last_ts)
    if dt is None:
        return {
            "id": "policy_archive",
            "label_ko": "정책 수집 cron",
            "status": "unknown",
            "metric": {"last_success_at": last_ts},
            "note": "source fetch failed or empty",
        }
    age_h = (now - dt).total_seconds() / 3600.0
    # 정책 cron 평일 KST 매일 → 26h 정상. 72h 초과 = degraded. 168h(7d) = down.
    if age_h < 26:
        status = "healthy"
        note = None
    elif age_h < 72:
        status = "degraded"
        note = f"{age_h:.1f}h 경과 (정상 26h 이하)"
    elif age_h < 168:
        status = "degraded"
        note = f"{age_h:.1f}h 경과 (3일 초과 — cron 결함 의심)"
    else:
        status = "down"
        note = f"{age_h:.1f}h 경과 (7일 초과 — cron 중단)"
    return {
        "id": "policy_archive",
        "label_ko": "정책 수집 cron",
        "status": status,
        "metric": {
            "last_success_at": last_ts,
            "age_hours": round(age_h, 1),
        },
        "note": note,
    }


def _build_resources_live(now: datetime) -> list[dict]:
    """진짜 wire — estate_system_health.json + policy archive 합산. fetch fail 시 unknown 명시."""
    esh = _fetch_estate_system_health()
    resources: list[dict] = []
    if esh:
        sources = esh.get("sources") or {}
        resources.append(_resource_r_one("r_one_weekly", "R-ONE 주간 매매지수", sources, 21))
        resources.append(_resource_r_one("r_one_unsold", "R-ONE 미분양", sources, 160))
        resources.append(_resource_landex(esh.get("meta_validation") or {}))
    else:
        # ESH fetch 실패 — 3 자원 모두 unknown 명시 (T1 fabricate 금지)
        for sid, slabel in (
            ("r_one_weekly", "R-ONE 주간 매매지수"),
            ("r_one_unsold", "R-ONE 미분양"),
            ("landex_meta_validation", "LANDEX 메타-검증"),
        ):
            resources.append({
                "id": sid,
                "label_ko": slabel,
                "status": "unknown",
                "metric": {},
                "note": "estate_system_health.json fetch failed",
            })
    resources.append(_resource_policy(now))
    resources.append(_resource_estate_api_keys(now))
    return resources


def _build_resources_mock(now: datetime) -> list[dict]:
    """개발 toggle — 옛 P1 mock 응답 (Framer 개발 검증용 보존)."""
    return [
        {
            "id": "landex_cron",
            "label_ko": "LANDEX Snapshot cron (mock)",
            "status": "healthy",
            "metric": {"last_success_at": (now - timedelta(hours=12)).isoformat()},
            "note": "scenario=mock — 실측 wire 는 scenario=live 사용",
        },
        {
            "id": "policy_cron",
            "label_ko": "정책 수집 cron (mock)",
            "status": "healthy",
            "metric": {"last_success_at": (now - timedelta(hours=8)).isoformat()},
            "note": None,
        },
        {
            "id": "data_go_kr_policy",
            "label_ko": "data.go.kr 정책브리핑 API (mock)",
            "status": "healthy",
            "metric": {
                "last_status_code": 200,
                "last_success_at": (now - timedelta(hours=8)).isoformat(),
            },
            "note": None,
        },
    ]


# ─────────────────────────────────────────────────
# HTTP handler
# ─────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        scenario = (params.get("scenario", ["live"])[0] or "live").strip().lower()
        if scenario not in ("live", "mock"):
            scenario = "live"

        now = datetime.now(KST)
        resources = (
            _build_resources_mock(now) if scenario == "mock" else _build_resources_live(now)
        )
        payload = {
            "schema_version": "1.1",  # P2 wire — scenario semantic 변경
            "fetched_at": now.isoformat(timespec="seconds"),
            "namespace": "estate",
            "scenario": scenario,
            "resources": resources,
        }

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", f"public, max-age={CACHE_MAX_AGE}")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

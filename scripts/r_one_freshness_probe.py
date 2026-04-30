#!/usr/bin/env python3
"""R-ONE freshness probe — 매매가격지수 + 미분양 두 통계의 데이터 신선도 측정.

cron 일 1회 권장. fetch_weekly_index/fetch_monthly_unsold 의 as_of 와 오늘 차이.
estate_system_health.json sources 섹션만 갱신 (meta_validation 은 건드리지 않음).

임계:
  주간 매매가격지수 (매주 목요일 발표 — Perplexity Q1 2026-04-30 cross-check 통과):
    7d 정상 / 14d Warning / 21d Critical
  월간 미분양 (실측 자연 지연 ~90d — feedback_real_call_over_llm_consensus 적용):
    100d 정상 / 130d Warning / 160d Critical
    이유: 첫 probe(2026-04-30, 강남구) 결과 last_seen=2026-02-01 = 88d.
          국토부/R-ONE 미분양 통계는 통상 60~90일 지연 발표. 임의 30/45/60 임계는 항상 critical.
    재검토: 5/5 메타-검증 결과 + Perplexity 후속 cross-check 권장.

샘플 구: 강남구 (안정적, R-ONE CLS_ID 매핑 양쪽 다 검증 완료).
사용:
  python3 scripts/r_one_freshness_probe.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
HEALTH_PATH = ROOT / "data" / "metadata" / "estate_system_health.json"
SAMPLE_GU = "강남구"
KST = timezone(timedelta(hours=9))

WEEKLY_THRESHOLDS_DAYS = {"warning": 14, "critical": 21}
# 미분양 통계 자연 지연 ~90d 실측 후 완화 (2026-04-30 첫 probe).
MONTHLY_THRESHOLDS_DAYS = {"warning": 130, "critical": 160}


# ── 1) .env 로드 + sys.path 셋업 (다른 스크립트와 동일 패턴) ─────────────
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)

VERCEL_API = ROOT / "vercel-api"
import importlib.util
import types

if "vapi" not in sys.modules:
    api_pkg = types.ModuleType("vapi"); api_pkg.__path__ = [str(VERCEL_API / "api")]
    sys.modules["vapi"] = api_pkg
    landex_pkg = types.ModuleType("vapi.landex"); landex_pkg.__path__ = [str(VERCEL_API / "api" / "landex")]
    sys.modules["vapi.landex"] = landex_pkg
    sources_pkg = types.ModuleType("vapi.landex._sources")
    sources_pkg.__path__ = [str(VERCEL_API / "api" / "landex" / "_sources")]
    sys.modules["vapi.landex._sources"] = sources_pkg
    # rone.py 가 from ._lawd import ... 하므로 lawd 도 미리 로드
    lawd_spec = importlib.util.spec_from_file_location(
        "vapi.landex._sources._lawd",
        VERCEL_API / "api" / "landex" / "_sources" / "_lawd.py",
    )
    lawd = importlib.util.module_from_spec(lawd_spec); sys.modules["vapi.landex._sources._lawd"] = lawd
    lawd_spec.loader.exec_module(lawd)
    rone_spec = importlib.util.spec_from_file_location(
        "vapi.landex._sources.rone",
        VERCEL_API / "api" / "landex" / "_sources" / "rone.py",
    )
    rone_mod = importlib.util.module_from_spec(rone_spec); sys.modules["vapi.landex._sources.rone"] = rone_mod
    rone_spec.loader.exec_module(rone_mod)

from vapi.landex._sources import rone  # type: ignore  # noqa: E402


# ── 2) 헬퍼 ────────────────────────────────────────────────────────

def _today_kst() -> datetime:
    return datetime.now(KST)


def _parse_as_of_date(s: Optional[str]) -> Optional[datetime]:
    """R-ONE WRTTIME_DESC 파싱.

    - 주간: "2026-04-27" (ISO)
    - 월간: "2026년 02월" — 월말로 정규화
    """
    if not s:
        return None
    s = s.strip()
    # 주간 ISO
    try:
        return datetime.fromisoformat(s).replace(tzinfo=KST)
    except (ValueError, TypeError):
        pass
    # 월간 한국어
    import re
    m = re.match(r"^(\d{4})년\s*(\d{1,2})월$", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        # 해당 월 1일로 — freshness 보수적 측정 (월말 X)
        return datetime(y, mo, 1, tzinfo=KST)
    return None


def _status_from_freshness(days: Optional[int], thresholds: dict) -> str:
    if days is None:
        return "unknown"
    if days >= thresholds["critical"]:
        return "critical"
    if days >= thresholds["warning"]:
        return "warning"
    return "ok"


def _probe_weekly() -> dict:
    """주간 매매가격지수 freshness."""
    now = _today_kst()
    payload = rone.fetch_weekly_index(SAMPLE_GU, weeks=4)
    if not payload:
        return {
            "status": "critical",
            "as_of_date": None,
            "freshness_days": None,
            "last_probe_at": now.isoformat(timespec="seconds"),
            "detail": "R-ONE 호출 실패 또는 빈 응답 (REB_API_KEY/R_ONE_API_KEY 또는 네트워크)",
        }
    as_of_str = payload.get("as_of")
    as_of_dt = _parse_as_of_date(as_of_str)
    if as_of_dt is None:
        return {
            "status": "unknown",
            "as_of_date": as_of_str,
            "freshness_days": None,
            "last_probe_at": now.isoformat(timespec="seconds"),
            "detail": f"as_of 파싱 실패: {as_of_str!r}",
        }
    days = (now - as_of_dt).days
    status = _status_from_freshness(days, WEEKLY_THRESHOLDS_DAYS)
    return {
        "status": status,
        "as_of_date": as_of_dt.date().isoformat(),
        "freshness_days": days,
        "last_probe_at": now.isoformat(timespec="seconds"),
        "detail": f"sample={SAMPLE_GU}, weeks=4, last_index={payload['series'][-1]['index'] if payload.get('series') else 'N/A'}",
    }


def _probe_unsold() -> dict:
    """월간 미분양 freshness."""
    now = _today_kst()
    payload = rone.fetch_monthly_unsold(SAMPLE_GU, months=4)
    if not payload:
        return {
            "status": "critical",
            "as_of_date": None,
            "freshness_days": None,
            "last_probe_at": now.isoformat(timespec="seconds"),
            "detail": "R-ONE 호출 실패 또는 빈 응답",
        }
    as_of_str = payload.get("as_of")
    as_of_dt = _parse_as_of_date(as_of_str)
    if as_of_dt is None:
        return {
            "status": "unknown",
            "as_of_date": as_of_str,
            "freshness_days": None,
            "last_probe_at": now.isoformat(timespec="seconds"),
            "detail": f"as_of 파싱 실패: {as_of_str!r}",
        }
    days = (now - as_of_dt).days
    status = _status_from_freshness(days, MONTHLY_THRESHOLDS_DAYS)
    return {
        "status": status,
        "as_of_date": as_of_dt.date().isoformat(),
        "freshness_days": days,
        "last_probe_at": now.isoformat(timespec="seconds"),
        "detail": f"sample={SAMPLE_GU}, months=4, last_unsold={payload['series'][-1]['unsold'] if payload.get('series') else 'N/A'}",
    }


def _worst_status(a: str, b: str) -> str:
    order = {"unknown": 0, "ok": 1, "warning": 2, "critical": 3}
    return a if order.get(a, 0) >= order.get(b, 0) else b


def _overall_status(data: dict) -> str:
    src_worst = "ok"
    for src in (data.get("sources") or {}).values():
        if isinstance(src, dict):
            src_worst = _worst_status(src_worst, src.get("status", "unknown"))
    active = (data.get("meta_validation") or {}).get("active_verdict", "ready")
    verdict_status = {
        "ready": "ok", "manual_review": "warning", "invalidated": "critical",
        "unknown": "unknown",
    }.get(active, "unknown")
    return _worst_status(src_worst, verdict_status)


def main() -> None:
    print("=== R-ONE freshness probe ===")
    print(f"sample_gu={SAMPLE_GU}, today={_today_kst().date().isoformat()}\n")

    weekly = _probe_weekly()
    unsold = _probe_unsold()

    print(f"[weekly]  status={weekly['status']:<8s}  as_of={weekly['as_of_date']}  "
          f"freshness={weekly['freshness_days']}d  ({weekly['detail']})")
    print(f"[unsold]  status={unsold['status']:<8s}  as_of={unsold['as_of_date']}  "
          f"freshness={unsold['freshness_days']}d  ({unsold['detail']})")

    # estate_system_health.json 갱신 — sources 섹션만, meta_validation 보존
    try:
        if HEALTH_PATH.exists():
            data = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
        else:
            data = {"_schema_version": "1.0", "sources": {}, "meta_validation": {}}

        data.setdefault("sources", {})
        data["sources"]["r_one_weekly"] = weekly
        data["sources"]["r_one_unsold"] = unsold
        data["generated_at"] = _today_kst().isoformat(timespec="seconds")
        data["overall_status"] = _overall_status(data)

        HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
        HEALTH_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n→ estate_system_health.json 갱신 (overall={data['overall_status']})")
    except Exception as e:
        print(f"\n⚠ estate_system_health.json 갱신 실패: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()

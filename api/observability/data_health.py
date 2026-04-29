"""
데이터 소스별 신선도 / 성공률 / 결측률 측정.

입력 출처:
  - portfolio.system_health.api_health  (per-source status, latency_ms, detail)
  - portfolio.updated_at                 (전체 수집 시각)
  - portfolio.macro.<key>.{collected_at, as_of}  (소스별 시점)
  - 과거 누적 jsonl                      (성공/실패 7일 카운트)

저장: data/metadata/data_health.jsonl (cron 1회 1라인)

가드 (spec §6):
  - 외부 호출 없음 — 순수 분석
  - 모든 진입점 try/except, 실패 시 안전 기본값
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from api.config import DATA_DIR, KST, now_kst

logger = logging.getLogger(__name__)

_PATH = os.path.join(DATA_DIR, "metadata", "data_health.jsonl")

# 신선도 임계 (분)
FRESHNESS_OK_MIN = 30
FRESHNESS_WARN_MIN = 120

# 성공률 임계
SUCCESS_RATE_OK = 0.95
SUCCESS_RATE_WARN = 0.90

# 핵심 소스 (Trust 판정에 직결 — spec §1.4)
CORE_SOURCES = ("yfinance", "fred", "kis", "dart")


def _parse_iso_kst(s: Optional[str]) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        # "2026-04-27T22:00:00+09:00" 또는 "2026-04-27T22:00:00"
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt
    except (ValueError, TypeError):
        return None


def _freshness_minutes(ts: Optional[str], reference: Optional[datetime] = None) -> Optional[int]:
    dt = _parse_iso_kst(ts)
    if dt is None:
        return None
    ref = reference or now_kst()
    delta = ref - dt
    return max(0, int(delta.total_seconds() / 60))


def _status_from_metrics(success_rate: float, freshness_min: Optional[int]) -> str:
    """ok/warning/critical 룰 (spec §1.1)."""
    if freshness_min is None:
        # 신선도 미상 — 성공률만으로 판정
        if success_rate >= SUCCESS_RATE_OK:
            return "warning"
        return "critical"
    if success_rate >= SUCCESS_RATE_OK and freshness_min < FRESHNESS_OK_MIN:
        return "ok"
    if success_rate < SUCCESS_RATE_WARN or freshness_min > FRESHNESS_WARN_MIN:
        return "critical"
    return "warning"


def _load_history(days: int = 7) -> Dict[str, Dict[str, int]]:
    """과거 jsonl 에서 소스별 success/failure 카운트 집계."""
    if not os.path.exists(_PATH):
        return {}
    cutoff = (now_kst().date() - timedelta(days=days)).strftime("%Y-%m-%d")
    counts: Dict[str, Dict[str, int]] = {}
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("date", "") < cutoff:
                        continue
                    for src, meta in (e.get("sources") or {}).items():
                        c = counts.setdefault(src, {"ok": 0, "fail": 0})
                        st = (meta or {}).get("status")
                        if st == "ok":
                            c["ok"] += 1
                        elif st in ("warning", "critical"):
                            c["fail"] += 1
                except (json.JSONDecodeError, AttributeError):
                    continue
    except OSError as e:
        logger.warning("data_health: history read failed: %s", e)
    return counts


def _source_freshness_from_macro(macro: Optional[dict], source_keys: tuple) -> Optional[int]:
    """매크로 섹션에서 source_keys 중 가장 오래된 시점의 freshness."""
    if not isinstance(macro, dict):
        return None
    candidates = []
    for k in source_keys:
        v = macro.get(k)
        if not isinstance(v, dict):
            continue
        # 우선순위: collected_at → as_of
        ts = v.get("collected_at") or v.get("as_of")
        m = _freshness_minutes(ts)
        if m is not None:
            candidates.append(m)
    if not candidates:
        return None
    return max(candidates)


def check_data_health(portfolio: Optional[dict]) -> Dict[str, Any]:
    """
    데이터 소스별 health 진단.

    Returns:
      {
        "yfinance": {
          "last_update_ts": "2026-04-27T22:00:00+09:00",
          "freshness_minutes": 5,
          "success_count_7d": 2851,
          "failure_count_7d": 3,
          "missing_pct": 0.001,
          "status": "ok",
          "latency_ms_p50": 320,
          "detail": "정상",
        },
        ...,
        "_meta": {
          "checked_at": "2026-04-27T22:00:01+09:00",
          "overall_status": "ok",
          "core_sources_ok": True,
        }
      }
    """
    if not isinstance(portfolio, dict):
        logger.warning("data_health: portfolio not dict, returning empty")
        return {"_meta": {"checked_at": now_kst().isoformat(), "overall_status": "critical",
                          "core_sources_ok": False, "error": "no_portfolio"}}

    try:
        sh = portfolio.get("system_health") or {}
        api_health = sh.get("api_health") or {}
        portfolio_ts = portfolio.get("updated_at")
        portfolio_freshness = _freshness_minutes(portfolio_ts)

        history = _load_history(days=7)

        result: Dict[str, Any] = {}
        worst_status = "ok"
        core_ok = True

        # 1) api_health 에 잡히는 소스
        for src, meta in api_health.items():
            if not isinstance(meta, dict):
                continue
            cur_status_raw = meta.get("status", "unknown")
            latency = meta.get("latency_ms", 0)
            detail = meta.get("detail", "")

            # 7일 누적 성공/실패
            hist = history.get(src) or {"ok": 0, "fail": 0}
            total = hist["ok"] + hist["fail"]
            # 오늘 1건도 누적 — 현재 status 기준
            if cur_status_raw == "ok":
                hist["ok"] += 1
            else:
                hist["fail"] += 1
            total += 1
            success_rate = hist["ok"] / total if total > 0 else 0.0

            # detail 안에 결측 정보 있을 수 있음 (예: "ok 2/18, ... 빈데이터 16")
            missing_pct = _parse_missing_from_detail(detail)

            # 신선도 — api_health 자체엔 timestamp 없음, portfolio updated_at 사용
            freshness = portfolio_freshness

            status = _status_from_metrics(success_rate, freshness)
            # B-1: system_health.api_health 가 ok 상태이고 detail 도 정상 텍스트면
            # jsonl 누적 통계 (success_rate < 0.90 등) 무시 — false critical 차단.
            # 운영 시 jsonl 이 부족해서 통계 왜곡되는 케이스가 흔함.
            if cur_status_raw == "ok":
                if status == "critical" and (freshness is None or freshness <= FRESHNESS_WARN_MIN):
                    # api 자체 ok + 신선도 warning 임계 안 → ok 강제
                    status = "ok"
            elif cur_status_raw == "critical":
                status = "critical"
            elif cur_status_raw == "warning" and status == "ok":
                status = "warning"

            result[src] = {
                "last_update_ts": portfolio_ts,
                "freshness_minutes": freshness,
                "success_count_7d": hist["ok"],
                "failure_count_7d": hist["fail"],
                "missing_pct": missing_pct,
                "status": status,
                "latency_ms_p50": int(latency) if isinstance(latency, (int, float)) else 0,
                "detail": detail[:200] if isinstance(detail, str) else "",
            }
            worst_status = _worst(worst_status, status)
            if src in CORE_SOURCES and status == "critical":
                core_ok = False

        # 2) 매크로 소스 (yfinance 보강 + ECOS / FRED 시점)
        macro = portfolio.get("macro") or {}
        macro_freshness = _source_freshness_from_macro(macro, ("vix", "us_10y", "usd_krw", "wti_oil", "sp500"))
        if "yfinance" in result and macro_freshness is not None:
            result["yfinance"]["freshness_minutes"] = max(
                result["yfinance"].get("freshness_minutes") or 0, macro_freshness
            )

        # 3) recommendations 결측률 (빈 grade/brain_score 비율)
        recs = portfolio.get("recommendations") or []
        if recs:
            missing = sum(1 for r in recs if not r.get("grade") or r.get("brain_score") in (None, 0))
            recs_missing_pct = round(missing / len(recs), 3)
            result["recommendations"] = {
                "last_update_ts": portfolio_ts,
                "freshness_minutes": portfolio_freshness,
                "success_count_7d": (history.get("recommendations") or {}).get("ok", 0) + (1 if missing < len(recs) else 0),
                "failure_count_7d": (history.get("recommendations") or {}).get("fail", 0) + (1 if missing == len(recs) else 0),
                "missing_pct": recs_missing_pct,
                "status": "ok" if recs_missing_pct < 0.1 else ("warning" if recs_missing_pct < 0.3 else "critical"),
                "latency_ms_p50": 0,
                "detail": f"recs={len(recs)}, missing={missing}",
            }
            worst_status = _worst(worst_status, result["recommendations"]["status"])

        result["_meta"] = {
            "checked_at": now_kst().isoformat(),
            "portfolio_updated_at": portfolio_ts,
            "portfolio_freshness_minutes": portfolio_freshness,
            "overall_status": worst_status,
            "core_sources_ok": core_ok,
            "sources_count": len(result) - 1,  # _meta 제외
        }
        return result
    except Exception as e:  # noqa: BLE001 — 가드 정책
        logger.warning("data_health: unexpected error: %s", e, exc_info=True)
        return {"_meta": {"checked_at": now_kst().isoformat(), "overall_status": "critical",
                          "core_sources_ok": False, "error": str(e)[:200]}}


def _parse_missing_from_detail(detail: str) -> float:
    """detail 문자열에서 '빈데이터 N' 같은 패턴 파싱. 실패 시 0."""
    if not isinstance(detail, str) or not detail:
        return 0.0
    try:
        # "ok 2/18, 권한없음 0, 오류 0, 빈데이터 16" 같은 포맷
        if "빈데이터" in detail and "/" in detail:
            import re
            m_total = re.search(r"(\d+)\s*/\s*(\d+)", detail)
            m_empty = re.search(r"빈데이터\s*(\d+)", detail)
            if m_total and m_empty:
                total = int(m_total.group(2))
                empty = int(m_empty.group(1))
                if total > 0:
                    return round(empty / total, 3)
    except (ValueError, AttributeError):
        pass
    return 0.0


def _worst(a: str, b: str) -> str:
    """status 우선순위: critical > warning > ok."""
    order = {"ok": 0, "warning": 1, "critical": 2, "unknown": 1}
    if order.get(b, 0) > order.get(a, 0):
        return b
    return a


def persist_health(result: Dict[str, Any]) -> str:
    """jsonl 누적 — cron 1회 1라인."""
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        meta = result.get("_meta") or {}
        entry = {
            "date": now_kst().strftime("%Y-%m-%d"),
            "timestamp": meta.get("checked_at") or now_kst().isoformat(),
            "overall_status": meta.get("overall_status", "unknown"),
            "core_sources_ok": meta.get("core_sources_ok", False),
            "sources": {k: {"status": v.get("status"),
                            "freshness_minutes": v.get("freshness_minutes"),
                            "missing_pct": v.get("missing_pct"),
                            "latency_ms_p50": v.get("latency_ms_p50")}
                        for k, v in result.items() if k != "_meta" and isinstance(v, dict)},
        }
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return _PATH
    except OSError as e:
        logger.warning("data_health: persist failed: %s", e)
        return ""

"""data_pipeline_health — Phase 2-B 데이터 파이프라인 6 아티팩트 종합 진단.

배경 (2026-05-10):
  Phase 2-B SHADOW 활성 후 매일 적재되는 jsonl/json 6종이 silent skip 없이 정상 누적
  되는지 site 에서 한눈에 확인 필요. SystemHealthBar 가 single source — 별도 컴포넌트 X.

진단 대상 (silent skip 차단 — feedback_data_collection_verification_mandatory):
  1. wide_scan_log.jsonl       (Phase 2-B SHADOW run-level, daily)
  2. stock_history/YYYY-Qn.jsonl (분기 시계열, daily 5,000 row 누적)
  3. dart_fundamentals_kr.json  (DART batch, weekly)
  4. macro_snapshot.json        (macro_collect, 30분 cron)
  5. universe_candidates.json   (universe_scan, daily)
  6. metadata/runtime_load_log.jsonl (ramp_up_monitor)

산출: data/metadata/data_pipeline_health.json (collected_at + 6 항목 status)
호출 시점: universe_scan / macro_collect / dart_batch 각 builder 끝 (편승, 별도 cron X)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

KST = timezone(timedelta(hours=9))

_REPO_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUTPUT_PATH = _REPO_ROOT / "data" / "metadata" / "data_pipeline_health.json"


def _now_kst() -> datetime:
    return datetime.now(KST)


def _quarter_filename(dt: datetime) -> str:
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


def _file_mtime_kst(path: Path) -> Optional[datetime]:
    if not path.exists():
        return None
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=KST)
    except OSError:
        return None


def _age_hours(t: Optional[datetime]) -> Optional[float]:
    if t is None:
        return None
    delta = _now_kst() - t
    return round(delta.total_seconds() / 3600.0, 2)


def _status_from_age(age_hours: Optional[float], max_fresh_hours: float) -> str:
    if age_hours is None:
        return "missing"
    if age_hours > max_fresh_hours * 2:
        return "missing"  # 2x 초과 = 사실상 dead
    if age_hours > max_fresh_hours:
        return "stale"
    return "fresh"


def _count_jsonl_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _last_jsonl_entry(path: Path) -> Optional[dict]:
    """jsonl 마지막 라인 parse — diagnostics / triggers 추출용."""
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return None
            chunk_size = min(8192, size)
            f.seek(-chunk_size, 2)
            lines = f.read().decode("utf-8", errors="ignore").splitlines()
            for line in reversed(lines):
                line = line.strip()
                if line:
                    return json.loads(line)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return None


def _load_collected_at(path: Path) -> Optional[datetime]:
    """JSON 파일의 collected_at 필드 → datetime."""
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            ts = d.get("collected_at")
            if ts:
                return datetime.fromisoformat(ts)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return None


# 진단 대상 6 아티팩트 (max_fresh_hours = 정상 갱신 주기 + 안전 마진)
SOURCES = [
    {
        "key": "wide_scan",
        "label": "Phase 2-B Coarse Filter",
        "path": "data/wide_scan_log.jsonl",
        "type": "jsonl_run_summary",
        "max_fresh_hours": 26.0,  # daily + 2h margin
    },
    {
        "key": "quarterly_history",
        "label": "분기 시계열 (5,000 raw)",
        "path_template": "data/stock_history/{quarter}.jsonl",
        "type": "jsonl_quarter",
        "max_fresh_hours": 26.0,
    },
    {
        "key": "dart_batch",
        "label": "DART KR 펀더멘털",
        "path": "data/dart_fundamentals_kr.json",
        "type": "json_collected_at",
        "max_fresh_hours": 8 * 24.0,  # 주 1회 + 1일 마진
    },
    {
        "key": "macro_snapshot",
        "label": "매크로 스냅샷",
        "path": "data/macro_snapshot.json",
        "type": "json_collected_at",
        "max_fresh_hours": 1.0,  # 30분 cron + 30분 마진
    },
    {
        "key": "universe_candidates",
        "label": "Universe 후보 (top N)",
        "path": "data/universe_candidates.json",
        "type": "json_collected_at",
        "max_fresh_hours": 26.0,  # daily cron(평일) + 마진. 2.0 은 오설정이었음(daily 인데 2h → 만성 false missing, dart 같은 진짜 결손 가림). 2026-06-07 fix. api/health.py 26h 와 정합.
    },
    {
        "key": "runtime_load",
        "label": "ramp_up_monitor",
        "path": "data/metadata/runtime_load_log.jsonl",
        "type": "jsonl_runtime",
        "max_fresh_hours": 26.0,
    },
]


def _diagnose_one(src: dict) -> dict:
    """단일 아티팩트 진단."""
    now = _now_kst()
    if src.get("path_template"):
        path = _REPO_ROOT / src["path_template"].format(quarter=_quarter_filename(now))
    else:
        path = _REPO_ROOT / src["path"]

    out: Dict[str, Any] = {
        "key": src["key"],
        "label": src["label"],
        "path": str(path.relative_to(_REPO_ROOT)),
        "type": src["type"],
        "max_fresh_hours": src["max_fresh_hours"],
        "exists": path.exists(),
    }

    # collected_at 우선, 없으면 mtime fallback
    ts: Optional[datetime] = None
    if src["type"] == "json_collected_at":
        ts = _load_collected_at(path)
    if ts is None:
        ts = _file_mtime_kst(path)

    age = _age_hours(ts)
    out["last_update_kst"] = ts.isoformat() if ts else None
    out["age_hours"] = age
    out["status"] = _status_from_age(age, src["max_fresh_hours"])

    # 추가 메타 — 라인 수 / 마지막 entry 핵심 필드
    if src["type"].startswith("jsonl"):
        out["line_count"] = _count_jsonl_lines(path)
        last = _last_jsonl_entry(path)
        if last:
            # 큰 필드는 제외 (UI 부담 통제) — 핵심만
            keep_keys = (
                "ts", "step", "mode", "input_n", "passed_n", "cut_score",
                "ramp_up_stage", "execution_time_seconds", "fail_triggers",
                "yfinance_failure_rate",
            )
            out["last_entry"] = {k: last.get(k) for k in keep_keys if k in last}
    elif src["type"] == "json_collected_at":
        try:
            d = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            d = {}
        diag = d.get("diagnostics") or {}
        if diag:
            keep_keys = (
                "ok", "candidates_count", "kr_count", "us_count",
                "fundamentals_count", "elapsed_s", "used_prev_snapshot",
                "source_counts",
            )
            out["diagnostics"] = {k: diag.get(k) for k in keep_keys if k in diag}

    return out


def collect_data_pipeline_health() -> Dict[str, Any]:
    """6 아티팩트 진단 → 종합 dict."""
    items = [_diagnose_one(s) for s in SOURCES]
    now = _now_kst()
    fresh_n = sum(1 for i in items if i["status"] == "fresh")
    stale_n = sum(1 for i in items if i["status"] == "stale")
    missing_n = sum(1 for i in items if i["status"] == "missing")
    overall = (
        "ok" if missing_n == 0 and stale_n == 0
        else "warn" if missing_n == 0
        else "error"
    )
    return {
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "overall_status": overall,
        "summary": {"fresh": fresh_n, "stale": stale_n, "missing": missing_n, "total": len(items)},
        "items": items,
        "schema_version": "v0",
    }


def write_data_pipeline_health(*, output_path: Optional[Path] = None) -> Dict[str, Any]:
    """진단 + 파일 적재. silent 실패 차단 (try/finally + stderr)."""
    out = output_path or OUTPUT_PATH
    health = collect_data_pipeline_health()
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(health, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, out)
        s = health["summary"]
        print(
            f"[data_pipeline_health] OK overall={health['overall_status']} "
            f"fresh={s['fresh']} stale={s['stale']} missing={s['missing']} → {out.name}",
            file=sys.stderr, flush=True,
        )
    except Exception as e:
        print(
            f"[data_pipeline_health] FAIL — {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
    return health


def main() -> int:
    health = write_data_pipeline_health()
    return 0 if health["overall_status"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())

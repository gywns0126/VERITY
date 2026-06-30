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


# 내용 타임스탬프 후보 키 (top-level + _meta). 파일마다 generated_at/collected_at/as_of/updated_at 혼재.
_CONTENT_TS_KEYS = ("generated_at", "collected_at", "as_of", "updated_at")


def _load_content_ts(path: Path) -> Optional[datetime]:
    """JSON **내용** 타임스탬프(generated_at/_meta.generated_at/collected_at/as_of/updated_at) → datetime(KST).
    🚨 mtime 아님 — CI 가 broad `git add data/` 로 mtime 을 매 run 갱신하면 content 가 동결돼도 mtime 은 fresh.
    insider_trades 6.7일 silent freeze(2026-06-27 P0)가 정확히 이 함정. 내용 시각으로만 freeze 포착."""
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    meta = d.get("_meta") if isinstance(d.get("_meta"), dict) else {}
    for scope in (d, meta):
        for k in _CONTENT_TS_KEYS:
            v = scope.get(k)
            if not v:
                continue
            try:
                dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=KST)
                return dt.astimezone(KST)
            except (ValueError, TypeError):
                continue
    return None


_PERSIST_FREEZE_FACTOR = 4.0  # max_fresh 의 4배 초과 = 명백 동결(주말/월요일 gap false-fire 0)


def _committed_content_ts(rel_path: str, *, is_jsonl: bool) -> Optional[datetime]:
    """HEAD 에 **커밋된** 파일 내용의 타임스탬프 → datetime(KST). 작업본(working copy) 아님.

    🚨 git-add-miss / commit 실패로 영속 안 된 freeze 를 잡는 유일 신호 —
    in-CI 모니터는 hook 직후 fresh 작업본(mtime·content 둘 다)을 봐서 persistence freeze 를 못 잡는다.
    모니터는 commit 前 실행 → HEAD = 직전 커밋(동결 상태) → 커밋 content-ts 가 진짜 영속 신선도.
    git 미가용/파일 미추적 → None (mtime/content fallback, 무해). shallow checkout 라도 HEAD 는 존재."""
    try:
        import subprocess
        r = subprocess.run(
            ["git", "show", f"HEAD:{rel_path}"],
            capture_output=True, text=True, timeout=15, cwd=str(_REPO_ROOT),
        )
        if r.returncode != 0 or not r.stdout:
            return None
        content = r.stdout
    except Exception:
        return None
    try:
        if is_jsonl:
            last_line = None
            for ln in content.splitlines():
                ln = ln.strip()
                if ln:
                    last_line = ln
            if not last_line:
                return None
            obj = json.loads(last_line)
            keys = ("ts", "ts_kst", "logged_at", "created_at") + _CONTENT_TS_KEYS
        else:
            obj = json.loads(content)
            keys = _CONTENT_TS_KEYS
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    meta = obj.get("_meta") if isinstance(obj.get("_meta"), dict) else {}
    for scope in (obj, meta):
        for k in keys:
            v = scope.get(k)
            if not v:
                continue
            try:
                dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=KST)
                return dt.astimezone(KST)
            except (ValueError, TypeError):
                continue
    return None


def _persistence_frozen(items: list) -> list:
    """커밋된 내용(HEAD) 기준 명백 동결 — git-add-miss / commit 실패 포착(working-copy fresh 여도).

    max_fresh × 4 초과만 → 주말·월요일 gap false-fire 0. mtime-기반 jsonl 항목(현 status 사각)도 커버.
    2026-07-01 학습: quarterly_history 50일 freeze(universe_scan.yml git add 누락 + CI mtime false-GREEN 은폐)."""
    frozen = []
    for it in items:
        rel = it.get("path")
        if not rel:
            continue
        is_jsonl = str(it.get("type", "")).startswith("jsonl")
        cts = _committed_content_ts(rel, is_jsonl=is_jsonl)
        if cts is None:
            continue
        age = _age_hours(cts)
        if age is None:
            continue
        limit = float(it.get("max_fresh_hours", 26.0)) * _PERSIST_FREEZE_FACTOR
        if age > limit:
            frozen.append({
                "key": it["key"], "label": it.get("label"),
                "committed_age_hours": round(age, 1), "limit_hours": round(limit, 1),
                "working_status": it.get("status"),
            })
    return frozen


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
        "max_fresh_hours": 6.0,  # 실 publish ~2-4h(daily_full + macro path). 30분 cron 가정은 과빡=만성 false. 2026-06-30 재보정.
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
    # 🚨 AlphaNest 공개 터미널 데이터 (launch-facing) — content generated_at 기반 freeze 포착.
    # 2026-06-27 추가: insider_trades 6.7일 silent freeze 가 모니터 감시밖이라 미포착(P0). 72h = 주말 휴장(금→월 ~64h) false-stale 회피 + 다일 freeze 포착.
    {"key": "insider_kr", "label": "내부자거래 KR (DART)", "path": "data/insider_trades.json", "type": "json_content", "max_fresh_hours": 72.0},
    {"key": "insider_us", "label": "내부자거래 US (Form4)", "path": "data/us_insider_trades.json", "type": "json_content", "max_fresh_hours": 72.0},
    {"key": "stock_report_kr", "label": "종목 리포트 KR", "path": "data/stock_report_public.json", "type": "json_content", "max_fresh_hours": 72.0},
    {"key": "stock_report_us", "label": "종목 리포트 US", "path": "data/us_stock_report_public.json", "type": "json_content", "max_fresh_hours": 35 * 24.0},  # us_financials 월간 cron(0 0 5 * *). 72h=daily 가정 오설정→만성 false. 2026-06-30 재보정.
    {"key": "flow_kr", "label": "외국인·기관 수급", "path": "data/stock_flow_5d.json", "type": "json_content", "max_fresh_hours": 72.0},
    {"key": "forensics_kr", "label": "공시 forensics", "path": "data/disclosure_forensics.json", "type": "json_content", "max_fresh_hours": 72.0},
    {"key": "disclosure_feed_kr", "label": "공시 피드 KR", "path": "data/public_disclosure_feed.json", "type": "json_content", "max_fresh_hours": 72.0},
    {"key": "broker_guide", "label": "증권사 가이드", "path": "data/broker_guide.json", "type": "json_content", "max_fresh_hours": 40 * 24.0},
    {"key": "market_warnings", "label": "시장경보 (투자주의/경고)", "path": "data/market_warnings.json", "type": "json_content", "max_fresh_hours": 30 * 24.0},  # 경보=드문 이벤트. 빌더 매일 정상(daily_full) but 경보 0건 시 출력 무변화→git 동결=정상. 72h=false-stale. 30일=event-rarity 매치(이상적=빌더 heartbeat 별도). 2026-06-30 재보정.
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

    # 내용 타임스탬프 우선, 없으면 mtime fallback (json_content = mtime 절대 신뢰 X, freeze 포착용)
    ts: Optional[datetime] = None
    if src["type"] == "json_content":
        ts = _load_content_ts(path)
    elif src["type"] == "json_collected_at":
        ts = _load_collected_at(path)
    out["ts_source"] = "content" if ts is not None else ("mtime" if path.exists() else "none")
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
    persist_frozen = _persistence_frozen(items)
    overall = (
        "ok" if missing_n == 0 and stale_n == 0
        else "warn" if missing_n == 0
        else "error"
    )
    # persist_frozen = working-copy fresh 라도 영속 안 된 freeze (in-CI status 로는 안 잡힘) → 최소 warn 보장
    if persist_frozen and overall == "ok":
        overall = "warn"
    return {
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "overall_status": overall,
        "summary": {"fresh": fresh_n, "stale": stale_n, "missing": missing_n, "total": len(items)},
        "items": items,
        "persist_frozen": persist_frozen,
        "schema_version": "v0",
    }


def _alert_egregious_freezes(health) -> None:
    """🚨 egregious freeze(>5일급) = telegram 1회. 2026-06-27 PM 결정(insider/market_warnings 7일 silent rot 재발 차단).
    트리거 = status 'missing'(age > 2×cadence) + ts_source 'content'(mtime unreliable 제외).
    cadence-aware 라 주말 휴장(금→월 ~64h) 무관 + broker_guide 월간(80일에야 missing) false-fire 0.
    dedupe(8h TTL) + 라벨만(age 제외) → stable 메시지 → spam 0. quiet hours 존중(야간 묵음). telegram 미설정/실패 = graceful."""
    # 🚨 json_content(AlphaNest 공개 9파일, 전부 72h+ 임계 = 주말 금→월 ~65h weekend-safe)만 알림.
    #   백엔드 content 항목(universe_candidates 26h→missing 52h 등)은 주말 갭에 missing 될 수 있어 제외(월요일 false-fire 방지).
    items = health.get("items", []) if isinstance(health, dict) else (health or [])
    frozen = [it for it in items
              if it.get("type") == "json_content"
              and it.get("status") == "missing"
              and it.get("ts_source") == "content"]
    persist = health.get("persist_frozen", []) if isinstance(health, dict) else []
    if not frozen and not persist:
        return
    try:
        from api.notifications.telegram import send_message
        labels = sorted(set(
            [str(it.get("label") or it.get("key")) for it in frozen]
            + [str(p.get("label") or p.get("key")) + "(영속 동결)" for p in persist]
        ))
        send_message(
            "🔴 데이터 freeze 감지 (정상 주기 2배 초과 미갱신): " + ", ".join(labels)
            + "\n빌더 step env / 워크플로 git add 점검 필요 (data_pipeline_health).",
            dedupe=True,
        )
    except Exception as e:  # noqa: BLE001 — 알림 실패가 모니터를 깨뜨리지 않도록
        print(f"[data_pipeline_health] freeze alert skip: {type(e).__name__}: {e}", file=sys.stderr, flush=True)


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
    # 파일 적재 후 egregious freeze 알림 (write 실패와 무관하게 시도, 알림 자체도 graceful)
    _alert_egregious_freezes(health)
    return health


def main() -> int:
    health = write_data_pipeline_health()
    return 0 if health["overall_status"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())

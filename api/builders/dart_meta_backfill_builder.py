"""
DART 1차 메타 백필 builder (2026-05-29 sprint 신설).

목적:
  KOSPI/KOSDAQ 전 종목의 2015-2026 공시 메타데이터 (list.json) 일괄 백필.
  - 출력: data/dart_kr_cache/_meta/{corp_code}.jsonl (corp_code 단위 증분 친화)
  - 진행 status: data/dart_kr_cache/_meta/_progress.json (restart 가능)
  - 분류: report_nm keyword 기반 정기/수시 자체 분류 (response 에 pblntf_ty 없음, 실호출 확인)

design:
  - DartScout._call 재사용 (overlap audit 의무 [[feedback_component_overlap_audit]])
  - 기간 1년 단위 분할 호출 (대형사 multi-page = total_page > 1 시 loop)
  - mapping.json (KOSPI corp_cls=Y / KOSDAQ K) filter
  - quota guard: 15K calls/day (5K 여유, 메모리 권장 [[project_dart_api_2026_constraints]])
  - 점검 시간 (02-06 KST) 회피
  - 3-4월/8월 마감 폭주 윈도우 = quota 50% 축소

학술/실무 정합:
  - PPL Q5 (2026-05-29) = 2단 백필 전략 1차 메타
  - 회사당 연 ~100-120건 추정 → 2,500 × 11년 × ~1.5 call/year = ~41K calls = ~3일 sprint
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.collectors.DartScout import _call
from api.collectors.dart_corp_code import load_mapping
from api.config import DATA_DIR, now_kst

META_DIR = os.path.join(DATA_DIR, "dart_kr_cache", "_meta")
PROGRESS_PATH = os.path.join(META_DIR, "_progress.json")

DEFAULT_START_YEAR = 2015  # DART fnlttSinglAcntAll 2015~ 정합
DEFAULT_DAILY_QUOTA = 15000  # 메모리 권장 (5K 여유, DART 20K/일 한도)
PAGE_COUNT = 100  # list.json page_count max

# 마감 폭주 윈도우 (KST 월일) — quota 50% 축소
SURGE_WINDOWS: Tuple[Tuple[Tuple[int, int], Tuple[int, int]], ...] = (
    ((3, 25), (4, 5)),   # 사업보고서 마감 직후
    ((8, 10), (8, 20)),  # 반기 마감 직후
)
# 점검 시간 (KST) — 호출 전면 회피
MAINTENANCE_HOUR_START = 2
MAINTENANCE_HOUR_END = 6  # exclusive


def _is_maintenance_window(now: Optional[datetime] = None) -> bool:
    n = now or now_kst()
    return MAINTENANCE_HOUR_START <= n.hour < MAINTENANCE_HOUR_END


def _is_surge_window(now: Optional[datetime] = None) -> bool:
    n = now or now_kst()
    m, d = n.month, n.day
    for (sm, sd), (em, ed) in SURGE_WINDOWS:
        if (m, d) >= (sm, sd) and (m, d) <= (em, ed):
            return True
    return False


def _effective_quota(base: int = DEFAULT_DAILY_QUOTA) -> int:
    return base // 2 if _is_surge_window() else base


def _classify_report_type(report_nm: str) -> str:
    """report_nm keyword 기반 정기/수시 자체 분류.

    정기: 사업보고서 / 반기보고서 / 분기보고서 (DART pblntf_ty A)
    수시: 그 외 모두 (B/C/D + 기타)
    """
    if not report_nm:
        return "unknown"
    for kw in ("사업보고서", "반기보고서", "분기보고서"):
        if kw in report_nm:
            return "정기"
    return "수시"


def _get_kospi_kosdaq_corp_codes() -> List[Tuple[str, str]]:
    """mapping.json 로드 → [(stock_code, corp_code), ...] KOSPI/KOSDAQ 만.

    mapping.json = {stock_code: corp_code} (dart_corp_code.build_mapping).
    stock_code 6자리 (KRX 상장 종목) 정합. 비상장 = mapping 에서 제외됨.
    """
    mapping = load_mapping()
    return sorted(mapping.items())


def _load_progress() -> Dict[str, Any]:
    if not os.path.exists(PROGRESS_PATH):
        return {
            "started_at": now_kst().isoformat(),
            "last_updated": None,
            "corp_codes_done": [],
            "current_corp_code": None,
            "current_year": None,
            "total_calls": 0,
            "total_entries": 0,
            "daily_call_count": 0,
            "daily_call_date": now_kst().date().isoformat(),
        }
    with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_progress(state: Dict[str, Any]) -> None:
    os.makedirs(META_DIR, exist_ok=True)
    state["last_updated"] = now_kst().isoformat()
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _reset_daily_count_if_new_day(state: Dict[str, Any]) -> None:
    today = now_kst().date().isoformat()
    if state.get("daily_call_date") != today:
        state["daily_call_count"] = 0
        state["daily_call_date"] = today


def _call_list_one_year(
    corp_code: str,
    year: int,
    state: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], int]:
    """1 corp_code × 1 year list.json 호출 (multi-page loop). Returns (entries, calls_made)."""
    bgn_de = f"{year}0101"
    end_de = f"{year}1231"
    all_entries: List[Dict[str, Any]] = []
    calls_made = 0

    page_no = 1
    while True:
        resp = _call("list.json", {
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_no": str(page_no),
            "page_count": str(PAGE_COUNT),
        })
        calls_made += 1
        state["total_calls"] += 1
        state["daily_call_count"] += 1

        status = resp.get("status", "")
        if status == "013":  # 데이터 없음
            break
        if status != "000":
            print(
                f"[meta_backfill] WARN corp_code={corp_code} year={year} "
                f"page={page_no} status={status} msg={resp.get('message', '')[:40]}",
                file=sys.stderr,
            )
            break

        entries = resp.get("list", []) or []
        all_entries.extend(entries)

        total_page = int(resp.get("total_page", 1) or 1)
        if page_no >= total_page:
            break
        page_no += 1
        time.sleep(0.3)  # DartScout._call 자체 0.5s delay + 보수 마진

    return all_entries, calls_made


def _save_entries_jsonl(corp_code: str, entries: List[Dict[str, Any]]) -> int:
    """corp_code 단위 jsonl append. report_type 자체 분류 추가. Returns: written count."""
    if not entries:
        return 0
    os.makedirs(META_DIR, exist_ok=True)
    path = os.path.join(META_DIR, f"{corp_code}.jsonl")
    written = 0
    with open(path, "a", encoding="utf-8") as f:
        for e in entries:
            e["report_type"] = _classify_report_type(e.get("report_nm", ""))
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
            written += 1
    return written


def _git_commit_and_push_incremental(state: Dict[str, Any]) -> None:
    """timeout 회피용 incremental commit + push. fail silent (다음 cycle retry).

    2026-05-30 신설 — 5/29 N=1 run cancelled at 4h timeout 시 산출물 lost 사고 학습.
    매 N ticker 처리 시 호출 → 부분 결과 회수 보장.
    """
    try:
        subprocess.run(["git", "config", "user.name", "AI Stock Bot"], check=False, timeout=5)
        subprocess.run(["git", "config", "user.email", "gywns0126@gmail.com"], check=False, timeout=5)
        subprocess.run(["git", "add", "data/dart_kr_cache/_meta/"], check=False, timeout=10)
        r = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False, timeout=10)
        if r.returncode == 0:
            return  # no staged changes
        n_done = len(state.get("corp_codes_done", []))
        n_entries = state.get("total_entries", 0)
        msg = f"📊 dart_meta_backfill incremental — {n_done} ticker / {n_entries} entries"
        subprocess.run(["git", "commit", "-m", msg], check=False, timeout=30)
        subprocess.run(
            ["git", "pull", "--rebase", "--autostash", "-X", "ours", "origin", "main"],
            check=False, timeout=60,
        )
        subprocess.run(["git", "push", "origin", "main"], check=False, timeout=60)
        print(f"[meta_backfill] incremental push: {msg}", file=sys.stderr)
    except Exception as e:
        print(f"[meta_backfill] WARN incremental commit fail: {e}", file=sys.stderr)


def run_backfill(
    max_calls: int = DEFAULT_DAILY_QUOTA,
    start_year: int = DEFAULT_START_YEAR,
    end_year: Optional[int] = None,
    resume: bool = True,
) -> Dict[str, Any]:
    """1차 메타 백필 main loop. max_calls = 이번 실행 quota (default 15K).

    Returns: 최종 진행 status dict.
    """
    if _is_maintenance_window():
        print("[meta_backfill] 점검 시간 (02-06 KST) — 호출 skip, 즉시 종료", file=sys.stderr)
        return {"skipped": "maintenance_window"}

    end_year = end_year or now_kst().year
    state = _load_progress() if resume else {
        "started_at": now_kst().isoformat(),
        "last_updated": None,
        "corp_codes_done": [],
        "current_corp_code": None,
        "current_year": None,
        "total_calls": 0,
        "total_entries": 0,
        "daily_call_count": 0,
        "daily_call_date": now_kst().date().isoformat(),
    }
    _reset_daily_count_if_new_day(state)

    effective_quota = min(max_calls, _effective_quota())
    print(f"[meta_backfill] start — quota={effective_quota} (surge={_is_surge_window()}) "
          f"daily_used={state['daily_call_count']}", file=sys.stderr)

    corp_codes = _get_kospi_kosdaq_corp_codes()
    done_set = set(state.get("corp_codes_done", []))

    tickers_processed_this_run = 0

    for stock_code, corp_code in corp_codes:
        if corp_code in done_set:
            continue

        state["current_corp_code"] = corp_code

        # resume: current_year 부터 시작
        resume_year = (
            state.get("current_year") if state.get("current_corp_code") == corp_code
            else start_year
        )
        resume_year = max(resume_year or start_year, start_year)

        corp_entries_total = 0
        finished_corp = True

        for year in range(resume_year, end_year + 1):
            if state["daily_call_count"] >= effective_quota:
                print(f"[meta_backfill] daily quota 도달 ({effective_quota}). "
                      f"corp_code={corp_code} year={year} 에서 중단. resume 가능.",
                      file=sys.stderr)
                state["current_year"] = year
                finished_corp = False
                _save_progress(state)
                _git_commit_and_push_incremental(state)
                return state

            entries, calls = _call_list_one_year(corp_code, year, state)
            written = _save_entries_jsonl(corp_code, entries)
            state["total_entries"] += written
            corp_entries_total += written

            if year % 4 == 0:  # 4년마다 progress flush
                _save_progress(state)

        if finished_corp:
            done_set.add(corp_code)
            state["corp_codes_done"] = sorted(done_set)
            state["current_year"] = None
            tickers_processed_this_run += 1

            if tickers_processed_this_run % 50 == 0:
                _git_commit_and_push_incremental(state)
            if tickers_processed_this_run % 10 == 0:
                _save_progress(state)
                print(f"[meta_backfill] progress — {len(done_set)} / {len(corp_codes)} "
                      f"({100 * len(done_set) / len(corp_codes):.1f}%) "
                      f"calls={state['total_calls']} entries={state['total_entries']}",
                      file=sys.stderr)

    _save_progress(state)
    _git_commit_and_push_incremental(state)
    print(f"[meta_backfill] complete — {len(done_set)} corp_codes / "
          f"{state['total_calls']} calls / {state['total_entries']} entries",
          file=sys.stderr)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="DART 1차 메타 백필 (KOSPI/KOSDAQ 2015-current)")
    parser.add_argument("--max-calls", type=int, default=DEFAULT_DAILY_QUOTA,
                        help=f"이번 실행 호출 한도 (default {DEFAULT_DAILY_QUOTA})")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR,
                        help=f"백필 시작 연도 (default {DEFAULT_START_YEAR})")
    parser.add_argument("--end-year", type=int, default=None,
                        help="백필 종료 연도 (default = current year)")
    parser.add_argument("--no-resume", action="store_true",
                        help="진행 status 무시하고 처음부터 (testing 용)")
    args = parser.parse_args()

    result = run_backfill(
        max_calls=args.max_calls,
        start_year=args.start_year,
        end_year=args.end_year,
        resume=not args.no_resume,
    )
    print(json.dumps({
        "total_calls": result.get("total_calls"),
        "total_entries": result.get("total_entries"),
        "corp_codes_done": len(result.get("corp_codes_done", [])),
        "current_corp_code": result.get("current_corp_code"),
        "current_year": result.get("current_year"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""dart_quarterly_backfill_builder — KR universe 분기 재무 시계열 backfill (paced, resumable).

배경 (2026-06-27):
  AlphaNest 종목 리포트 깊이 = "재무 단년 스냅샷" 1개뿐 (dart_batch 가 연간 11011 만 fetch).
  분기추이(viz) 노출 위해 5년 × 4분기 = 20기간 backfill 필요. 단 DART rate limit(일 ~1만~2만건)
  + GH IP throttle + GH Actions 6h 한도 때문에 한 run 에 전수 불가 → **체크포인트 paced backfill**.

설계:
  - 작업 단위 = (period = (year, reprt_code)) × ticker. 5년 × 4분기 × ~2,000종목 = ~40K 단위.
  - period-major 순회: 한 period 의 ticker 들을 청크로 끊어 fetch_dart_fundamentals_batch(reprt_code).
  - 매 run = CHUNK_TICKERS(기본 120) 만큼만 진행 → dart_quarterly_snapshots.jsonl append → cursor 저장.
  - 다음 run 이 cursor 이어받음 (drip-fill, 며칠~1주 완주). done 도달 시 no-op loud exit.
  - universe 는 첫 run 에 snapshot(progress 파일에 고정) — 이후 순서 불변(중복/누락 방지).

쿼터 안전:
  - 청크 120종목 × CFS→OFS ~2콜 = ~240콜/run. 시간당 1run = ~5.7K/일 < 1만 cap.
  - 환경변수 DART_BACKFILL_CHUNK 로 조정 가능.

거짓말 트랩 정합 (feedback_data_collection_verification_mandatory):
  - try/finally + logged stderr 표식 + cursor 영속(진도 가시).
  - append = 기존 dart_batch_builder._append_quarterly_snapshots 재사용 (스키마 단일 출처).
  - 🚨 RULE 4: progress + jsonl 둘 다 cron git add 정합 의무 (broad `git add data/` 커버).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROGRESS_PATH = os.path.join(_REPO_ROOT, "data", ".dart_quarterly_backfill_progress.json")

# 10년 × 4분기. reprt_code: 1Q / 반기 / 3Q / 연간 (DART fnlttSinglAcntAll).
# 10 = PublicQuarterlyTrend 표시 상한(40분기=10년, Math.min(40,...)) 꽉 채움. DART 2015~ 지원.
BACKFILL_YEARS = int(os.environ.get("DART_BACKFILL_YEARS", "10"))
# 최신 기간 우선 (PM 2026-07-04 "최신 연도부터") — 사용자 체감 = 최근 분기가 먼저 채워짐.
REPRT_CODES = ["11011", "11014", "11012", "11013"]  # Annual, Q3, H1, Q1 (연도 내 최신→과거)
CHUNK_TICKERS = int(os.environ.get("DART_BACKFILL_CHUNK", "120"))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _target_years() -> List[int]:
    """직전 5개 *완료* 연도 (당해년도 분기는 부분 미제출이라 제외)."""
    last_complete = _now_kst().year - 1
    return list(range(last_complete - BACKFILL_YEARS + 1, last_complete + 1))


def _current_year_periods() -> List[Dict[str, str]]:
    """당해년도 filable 분기 (법정 제출기한 경과분만, 최신 먼저) — 새 분기 공시철이 지나면
    periods 에 자동 편입 → done 상태에서도 main() 이 자동 재개 (v3, PM 2026-07-05 "자동으로")."""
    now = _now_kst()
    y = str(now.year)
    md = (now.month, now.day)
    out: List[Dict[str, str]] = []
    if md >= (11, 16):
        out.append({"year": y, "reprt_code": "11014"})  # Q3 (기한 11/14)
    if md >= (8, 16):
        out.append({"year": y, "reprt_code": "11012"})  # 반기 (기한 8/14)
    if md >= (5, 17):
        out.append({"year": y, "reprt_code": "11013"})  # Q1 (기한 5/15)
    return out


def _periods() -> List[Dict[str, str]]:
    """(year, reprt_code) 기간 리스트 — 당해년도 filable 분기 → 최신 연도부터 연간→Q1 순."""
    out: List[Dict[str, str]] = list(_current_year_periods())
    for y in sorted(_target_years(), reverse=True):
        for code in REPRT_CODES:
            out.append({"year": str(y), "reprt_code": code})
    return out


def _pkey(q: Dict[str, str]) -> str:
    return f"{q['year']}|{q['reprt_code']}"


def _build_universe() -> List[str]:
    """KR universe ticker 리스트 (정렬·고정). dart_batch 와 동일 소스."""
    from api.config import UNIVERSE_RAMP_UP_STAGE
    from api.collectors.universe_builder import build_extended_universe

    stage = max(int(UNIVERSE_RAMP_UP_STAGE or 0), 500)
    kr_target = max(int(stage * 0.4), 100)
    entries: list = []
    for attempt in range(3):
        try:
            entries = build_extended_universe("KR", target_size=kr_target, apply_hard_floor=True)
            if entries:
                break
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"[dart_qbackfill] universe build 실패(시도 {attempt+1}/3): {e}\n")
        if attempt < 2:
            time.sleep(3 * (attempt + 1))
    tickers = sorted({str(e["ticker"]).zfill(6) for e in entries if e.get("ticker")})
    return tickers


def _load_progress() -> Dict[str, Any]:
    if not os.path.isfile(PROGRESS_PATH):
        return {}
    try:
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_progress(p: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(PROGRESS_PATH), exist_ok=True)
    tmp = PROGRESS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PROGRESS_PATH)


def _init_progress() -> Dict[str, Any]:
    universe = _build_universe()
    periods = _periods()
    return {
        "schema": "v3",  # v3 = key 커서 (skip_keys=완료 set + cur_key) — 기간 목록이 자라도 안전
        "created_at": _now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "years": _target_years(),
        "reprt_codes": REPRT_CODES,
        "universe": universe,
        "n_tickers": len(universe),
        "n_periods": len(periods),
        "units_total": len(universe) * len(periods),
        "skip_keys": [],   # 완료한 (year|reprt) — 순서 무관 set
        "cur_key": None,   # 진행 중 기간
        "ticker_idx": 0,
        "units_done": 0,
        "done": False,
    }


# 1 run(수동 dispatch) 당 진행 상한 — DART 쿼터 분할(형제 backfill 과 20K/일 공유). 환경변수 조정.
RUN_UNIT_CAP = int(os.environ.get("DART_BACKFILL_RUN_UNITS", "1500"))   # 종목·단위/run
RUN_DEADLINE_S = float(os.environ.get("DART_BACKFILL_DEADLINE_S", "3000"))  # ~50분(GH timeout 여유)


def _process_chunk(p: Dict[str, Any], periods: List[Dict[str, str]], universe: List[str],
                   append_fn) -> int:
    """1 청크 처리 → append + cursor 전진 + progress 저장. 처리한 종목 수 반환(0=done)."""
    from api.collectors.dart_fundamentals import fetch_dart_fundamentals_batch

    n_tk = len(universe)
    skip = set(p.get("skip_keys") or [])
    pending = [q for q in periods if _pkey(q) not in skip]
    if not pending:
        p["done"] = True
        _save_progress(p)
        return 0
    cur = next((q for q in pending if _pkey(q) == p.get("cur_key")), None)
    if cur is None:
        cur = pending[0]
        p["cur_key"] = _pkey(cur)
        p["ticker_idx"] = 0
    tidx = int(p.get("ticker_idx", 0))

    period = cur
    chunk = universe[tidx: tidx + CHUNK_TICKERS]
    sys.stderr.write(
        f"[dart_qbackfill] period {periods.index(cur)+1}/{len(periods)} (남은 {len(pending)}) "
        f"(year={period['year']} reprt={period['reprt_code']}) ticker {tidx}~{tidx+len(chunk)}/{n_tk}\n"
    )
    funds = fetch_dart_fundamentals_batch(
        chunk, max_workers=6, bsns_year=period["year"], reprt_code=period["reprt_code"]
    ) or {}
    # DART 정식분만 append (source DART* + total_assets>0) — yfinance fallback 은 분기추이 부적합
    dart_funds = {
        tk: f for tk, f in funds.items()
        if str(f.get("source", "")).startswith("DART") and (f.get("total_assets") or 0) > 0
    }
    snapshot = {
        "collected_at": _now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "fundamentals": dart_funds,
    }
    appended = append_fn(snapshot) if dart_funds else 0

    tidx_next = tidx + len(chunk)
    if tidx_next >= n_tk:
        skip.add(_pkey(cur))
        p["skip_keys"] = sorted(skip)
        p["cur_key"] = None
        tidx_next = 0
    p["ticker_idx"] = tidx_next
    p["units_done"] = int(p.get("units_done", 0)) + len(chunk)
    p["last_run_at"] = _now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    p["last_chunk_appended"] = appended
    if not [q for q in periods if _pkey(q) not in skip]:
        p["done"] = True
    _save_progress(p)  # 청크마다 저장 → run 중 잘려도 재개
    return len(chunk)


def main() -> int:
    ok = False
    started = time.time()
    run_units = 0
    try:
        from api.builders.dart_batch_builder import _append_quarterly_snapshots

        p = _load_progress()
        target_years = _target_years()
        prev_years = [int(y) for y in (p.get("years") or [])] if p else []
        if not p or not p.get("universe"):
            p = _init_progress()
            sys.stderr.write(
                f"[dart_qbackfill] 초기화: {p['n_tickers']}종목 × {p['n_periods']}기간 "
                f"= {p['units_total']} 단위 (years={p['years']})\n"
            )
            _save_progress(p)
        elif prev_years != target_years:
            # 이력 깊이(BACKFILL_YEARS) 변경 → 진도 재init. 이미 적재된 jsonl 은 dedup 으로 보존,
            # 재fetch 는 최신 fetched_at 로 갱신될 뿐 손실 0. (5년→10년 확대 등 self-heal.)
            sys.stderr.write(
                f"[dart_qbackfill] years 변경 {prev_years}→{target_years} — 진도 재init "
                f"(적재분 dedup 보존)\n"
            )
            p = _init_progress()
            _save_progress(p)

        if p.get("universe") and p.get("schema") != "v3":
            # v1(오래된 연도 우선)/v2(최신 우선, 인덱스 커서) → v3(key 커서) 이관 — 진도 무손실.
            schema = str(p.get("schema") or "v1")
            old_codes = [str(c) for c in (p.get("reprt_codes") or [])] or ["11013", "11012", "11014", "11011"]
            yrs = [int(y) for y in (p.get("years") or [])]
            if schema == "v2":
                yrs = sorted(yrs, reverse=True)
            old_keys = [f"{y}|{c}" for y in yrs for c in old_codes]
            pi = int(p.get("period_idx", 0))
            done_keys = sorted(set(p.get("skip_keys") or []) | set(old_keys[:pi]))
            p["skip_keys"] = done_keys
            if schema == "v2" and pi < len(old_keys):
                p["cur_key"] = old_keys[pi]  # 진행 중 기간 이어감 (ticker_idx 유지)
            else:
                p["cur_key"] = None
                p["ticker_idx"] = 0
            p["schema"] = "v3"
            p["reprt_codes"] = REPRT_CODES
            p.pop("period_idx", None)
            sys.stderr.write(
                f"[dart_qbackfill] {schema}→v3 이관: key 커서 전환 · 완료 {len(done_keys)}기간 보존 "
                f"· cur={p.get('cur_key')}\n"
            )
            _save_progress(p)

        # 기간 목록 갱신 (당해년도 filable 분기 자동 편입) — done 이어도 신규 기간이 생기면 자동 재개
        periods_now = _periods()
        skip_now = set(p.get("skip_keys") or [])
        pending_n = sum(1 for q in periods_now if _pkey(q) not in skip_now)
        p["n_periods"] = len(periods_now)
        p["units_total"] = len(p.get("universe") or []) * len(periods_now)
        if p.get("done") and pending_n:
            p["done"] = False
            sys.stderr.write(f"[dart_qbackfill] 신규 filable 기간 {pending_n}개 감지 — 자동 재개\n")
            _save_progress(p)

        if p.get("done"):
            sys.stderr.write(
                f"[dart_qbackfill] logged=True · DONE (units_done={p.get('units_done')}/"
                f"{p.get('units_total')}) — no-op\n"
            )
            ok = True
            return 0

        universe: List[str] = p["universe"]
        periods = _periods()

        # run 당 RUN_UNIT_CAP·deadline 까지 청크 루프 (수동 dispatch 1회 = 쿼터-cap 분할)
        while run_units < RUN_UNIT_CAP and (time.time() - started) < RUN_DEADLINE_S:
            processed = _process_chunk(p, periods, universe, _append_quarterly_snapshots)
            if processed == 0 or p.get("done"):
                break
            run_units += processed

        elapsed = round(time.time() - started, 1)
        sys.stderr.write(
            f"[dart_qbackfill] logged=True · run_units={run_units} · 진도 {p['units_done']}/"
            f"{p['units_total']} ({100*p['units_done']//max(p['units_total'],1)}%) · "
            f"{elapsed}s · done={p.get('done')}\n"
        )
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[dart_qbackfill] FAILED: {type(e).__name__}: {str(e)[:200]}\n")
        return 1
    finally:
        if not ok:
            sys.stderr.write("[dart_qbackfill] logged=False\n")


if __name__ == "__main__":
    sys.exit(main())

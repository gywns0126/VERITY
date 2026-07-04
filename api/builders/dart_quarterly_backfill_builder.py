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


def _periods() -> List[Dict[str, str]]:
    """(year, reprt_code) 기간 리스트 — 최신 연도부터, 각 연도 연간→Q1 순 (최신 기간 우선)."""
    out: List[Dict[str, str]] = []
    for y in sorted(_target_years(), reverse=True):
        for code in REPRT_CODES:
            out.append({"year": str(y), "reprt_code": code})
    return out


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
        "schema": "v2",  # v2 = 최신 기간 우선 순회
        "created_at": _now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "years": _target_years(),
        "reprt_codes": REPRT_CODES,
        "universe": universe,
        "n_tickers": len(universe),
        "n_periods": len(periods),
        "units_total": len(universe) * len(periods),
        # cursor = 다음 처리할 (period_idx, ticker_idx)
        "period_idx": 0,
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
    pidx = int(p.get("period_idx", 0))
    tidx = int(p.get("ticker_idx", 0))
    # v1→v2 이관분: 구(오래된 연도 우선) 순서에서 이미 완료한 period 는 건너뜀
    skip = set(p.get("skip_keys") or [])
    while pidx < len(periods) and f"{periods[pidx]['year']}|{periods[pidx]['reprt_code']}" in skip:
        pidx += 1
        tidx = 0
        p["period_idx"] = pidx
        p["ticker_idx"] = 0
    if pidx >= len(periods):
        p["done"] = True
        _save_progress(p)
        return 0

    period = periods[pidx]
    chunk = universe[tidx: tidx + CHUNK_TICKERS]
    sys.stderr.write(
        f"[dart_qbackfill] period {pidx+1}/{len(periods)} "
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
        pidx += 1
        tidx_next = 0
    p["period_idx"] = pidx
    p["ticker_idx"] = tidx_next
    p["units_done"] = int(p.get("units_done", 0)) + len(chunk)
    p["last_run_at"] = _now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    p["last_chunk_appended"] = appended
    if pidx >= len(periods):
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

        if p.get("universe") and not p.get("done") and p.get("schema") != "v2":
            # v1(오래된 연도 우선) → v2(최신 우선) 이관: 완료 prefix 를 skip_keys 로 보존, 커서 리셋.
            # 부분 진행 중이던 period 는 재수집 (jsonl dedup 무해 — 손실 0).
            old_codes = [str(c) for c in (p.get("reprt_codes") or [])] or ["11013", "11012", "11014", "11011"]
            old_keys: List[str] = []
            for y in (p.get("years") or []):
                for code in old_codes:
                    old_keys.append(f"{y}|{code}")
            done_keys = old_keys[: int(p.get("period_idx", 0))]
            p["skip_keys"] = done_keys
            p["schema"] = "v2"
            p["reprt_codes"] = REPRT_CODES
            p["period_idx"] = 0
            p["ticker_idx"] = 0
            sys.stderr.write(
                f"[dart_qbackfill] v1→v2 이관: 최신 기간 우선 순회로 전환 · 완료 {len(done_keys)}기간 skip 보존\n"
            )
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

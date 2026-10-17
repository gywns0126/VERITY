#!/usr/bin/env python3
"""
dart_kr_fin_backfill — KR 종목 연간 재무 시계열 광범위 백필 (재무추이 섹션 부활).

2026-06-27 신설 (PM "죽은 섹션 하나씩 살리자"). 리포트 '재무추이'(fin_series)가 30종목뿐(옛 IC 백필) →
universe(stock_report_public ~1616) × 2015~ 연간 매출/영업이익/순익을 DART fnlttSinglAcntAll 로 수집.
빌더 _load_fin_series 가 dart_kr_fin_history.json 을 dart_kr_backfill_result 와 merge → 대부분 종목 차트.

proven fetcher 재사용: dart_fundamentals._fetch_fnltt_all_cached(캐시 → dart_kr_cache) + _extract_pl_bs_from_dart.
DART only(키 CI 전용·RULE 1 무관). resume(done-ticker)·quota-cap(카탈리스트 백필과 20K/일 공유 — sequencing).
멱등: 캐시 hit 시 API 호출 0. 사실만(매출/영업익/순익) RULE 7.

usage: python scripts/dart_kr_fin_backfill.py [--start-year 2015] [--limit N] [--quota-cap N] [--universe PATH]
출력: data/dart_kr_fin_history.json {rows:[{ticker,name,fiscal_year,period:"annual",fundamentals:{revenue,operating_profit,net_income}}]}
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _ROOT)

from api.config import DATA_DIR
from api.collectors.dart_corp_code import get_corp_code
from api.collectors.dart_fundamentals import _fetch_fnltt_all_cached, _extract_pl_bs_from_dart
from api.builders.stock_report_public_builder import _checked_489790_first_close

OUT_PATH = os.path.join(DATA_DIR, "dart_kr_fin_history.json")
DONE_PATH = os.path.join(DATA_DIR, "dart_kr_fin_history_done.json")
# 🚨 2026-08-23 신설 — (티커, 연도) **셀 단위** 시도 원장.
#   종전 재개 상태는 `done`(티커 단위) 하나였는데, 실제 작업 단위는 셀이다.
#   이 불일치가 실제로 데이터를 얼렸다:
#     2026-07-06 `c7b78b41c` 가 오염 행 72개(37종목)를 purge 하고 "재큐" 했는데,
#     재큐 신호가 "오염 행이 **존재**한다" 였다. 행을 지우면서 신호까지 지운 것이다.
#     티커는 `done` 에 남아 todo 에서 영구 제외 → 48일 뒤인 오늘까지 **48칸 미복구**
#     (19종목, 삼성전자 9년 포함). 알림·에러·실패 0 = 조용한 결손.
#   이제 todo 는 셀에서 계산한다. 빈 응답은 여기 시도 횟수로 기록해 무한 재시도를 막고,
#   성공하면 항목을 지운다. `done` 은 하위호환으로 계속 쓰되 **차단권은 없다**.
MISSING_PATH = os.path.join(DATA_DIR, "dart_kr_fin_history_missing.json")
DEFAULT_UNIVERSE = os.path.join(DATA_DIR, "stock_report_public.json")
# 공식 status 013(자료없음) 응답의 셀 재시도 상한. source/status/parse 오류는
# 이 횟수를 소비하지 않고 계속 재시도한다. 전수 no-data 재시도는 --retry-exhausted.
MAX_CELL_ATTEMPTS = 2


def _universe(path, limit, only):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    stocks = d.get("stocks") if isinstance(d, dict) else d
    out = []
    for s in (stocks or []):
        tk = str(s.get("ticker") or "").strip()
        if only and tk != only:
            continue
        if tk.isdigit() and len(tk) == 6:
            out.append((tk, s.get("name") or tk))
    return out[:limit] if limit else out


def _load_done():
    try:
        with open(DONE_PATH, encoding="utf-8") as f:
            return set(json.load(f).get("tickers") or [])
    except (OSError, json.JSONDecodeError):
        return set()


def _save_done(done):
    tmp = DONE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"tickers": sorted(done)}, f, ensure_ascii=False)
    os.replace(tmp, DONE_PATH)


def _load_missing():
    """{"TICKER|YEAR": {"n": 시도횟수, "last": "YYYY-MM-DD"}}"""
    try:
        with open(MISSING_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return dict(d.get("cells") or {})
    except (OSError, json.JSONDecodeError):
        return {}


def _response_kind(raw):
    """DART status 계약을 분류한다. 반환 reason은 제한된 enum만 사용한다."""
    if not isinstance(raw, str) or not raw:
        return "error", None, "invalid_response"
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return "error", None, "invalid_json"
    if not isinstance(payload, dict):
        return "error", None, "invalid_payload"

    status = payload.get("status")
    if status == "013":
        rows = payload.get("list", [])
        if rows not in (None, []) or not isinstance(rows, list):
            return "error", None, "invalid_payload"
        return "empty", payload, None
    if status != "000":
        return "error", None, "unexpected_status"
    if not isinstance(payload.get("list"), list):
        return "error", None, "invalid_payload"
    return "ok", payload, None


def _record_error(cells, key, reason):
    previous = cells.get(key) or {}
    cells[key] = {
        "n": _nonnegative_int(previous.get("n", 0)),
        "last": date.today().isoformat(),
        "status": "error",
        "error_count": _nonnegative_int(previous.get("error_count", 0)) + 1,
        "no_data_attempts": _no_data_attempts(previous),
        "last_error": reason,
    }


def _nonnegative_int(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _no_data_attempts(record):
    if "no_data_attempts" in record:
        return _nonnegative_int(record.get("no_data_attempts"))
    # Migrate legacy rows only when their last recorded outcome was official 013.
    # An old `error` row's n may count transport/parse failures, not no-data.
    return _nonnegative_int(record.get("n", 0)) if record.get("status") == "013" else 0


def _record_empty(cells, key):
    previous = cells.get(key) or {}
    cells[key] = {
        "n": _nonnegative_int(previous.get("n", 0)) + 1,
        "last": date.today().isoformat(),
        "status": "013",
        "no_data_attempts": _no_data_attempts(previous) + 1,
        "error_count": _nonnegative_int(previous.get("error_count", 0)),
    }


def _is_exhausted_no_data(record):
    if record.get("status") != "013":
        return False
    try:
        return _no_data_attempts(record) >= MAX_CELL_ATTEMPTS
    except (TypeError, ValueError):
        return False


def _save_missing(cells, stats=None):
    tmp = MISSING_PATH + ".tmp"
    payload = {
        "_meta": {
            "artifact": "dart_kr_fin_history_missing",
            "updated_at": date.today().isoformat(),
            "note": "(티커,연도) 셀 원장 — 공식 status 013만 no-data 시도 횟수에 반영",
            "max_cell_attempts": MAX_CELL_ATTEMPTS,
            "cells_n": len(cells),
            "exhausted_n": sum(1 for v in cells.values() if _is_exhausted_no_data(v)),
            **(stats or {}),
        },
        "cells": cells,
    }
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, MISSING_PATH)


def _load_rows():
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            return (json.load(f).get("rows") or [])
    except (OSError, json.JSONDecodeError):
        return []


def _write_out(rows):
    """산출물 저장 — 🚨 RULE 12 ② 자기신고 `_meta` 동반.

    소비자는 전부 `.get("rows")` 로 읽으므로 `_meta` 추가가 안전하다(2026-08-23 전수 확인:
    kr_safety_score_full · kr_lynch_class_builder · stock_report_public_builder ·
    ticker_facts · data_gap_classifier 5곳).
    """
    tks = {r.get("ticker") for r in rows}
    yrs = [r.get("fiscal_year") for r in rows if r.get("fiscal_year")]
    cov = collections.Counter()
    per_tk = collections.Counter(r.get("ticker") for r in rows)
    for n in per_tk.values():
        cov[n] += 1
    payload = {
        "_meta": {
            "artifact": "dart_kr_fin_history",
            "updated_at": date.today().isoformat(),
            "rows_n": len(rows),
            "tickers_n": len(tks),
            "year_min": min(yrs) if yrs else None,
            "year_max": max(yrs) if yrs else None,
            # 🚨 분모 자기신고 — "재무추이 부활" 을 비율 없이 말하지 않는다(RULE 13 ②)
            "years_per_ticker_hist": {str(k): v for k, v in sorted(cov.items())},
            "source": "DART fnlttSinglAcntAll (CFS 우선 → OFS fallback)",
        },
        "rows": rows,
    }
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, OUT_PATH)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2015)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ticker", default=None)
    ap.add_argument("--universe", default=None)
    ap.add_argument("--quota-cap", type=int, default=None, help="이번 run DART 요청 상한(공유 쿼터 throttle, 다일 분할)")
    ap.add_argument("--retry-exhausted", action="store_true",
                    help="시도 상한에 걸린 셀까지 다시 두드린다(원장 초기화 없이 1회 강제)")
    args = ap.parse_args()

    years = list(range(args.start_year, date.today().year))  # 완결 연도만(당해 사업보고서 미공시)
    universe = _universe(args.universe or DEFAULT_UNIVERSE, args.limit, (args.ticker or "").strip() or None)
    done = _load_done()
    missing = _load_missing()
    rows = _load_rows()
    first_close_required = 2024 in years and any(t == "489790" for t, _ in universe)
    first_close_present = _checked_489790_first_close(rows) if first_close_required else False
    def _row_clean(r):
        # 재수집 불요 조건: net 존재 AND op 비오염. 하나라도 어기면 stale → 재수집.
        f = r.get("fundamentals") or {}
        if f.get("net_income") is None:
            return False   # null-net(적자 클램프 잔재) → 재수집(2026-07 순이익 account_id fix 소급)
        rev, op = f.get("revenue") or 0, f.get("operating_profit")
        if rev > 1e10 and op is not None and abs(op) < 1e6:
            return False   # op 오파싱(EPS/중단영업 오치환): 매출 큰데 op 극소 → 재수집(op account_id 승격 소급)
        return True

    # 정상 행만 seen — 오염/null 행은 재수집 대상. dedup 멱등이라 양호분기 손실 0.
    seen = {(r.get("ticker"), r.get("fiscal_year")) for r in rows if _row_clean(r)}
    if first_close_required and (not first_close_present or ("489790", 2024) not in seen):
        raise ValueError("489790 first close requires reviewed history before collection")
    rows_by_key = {(r.get("ticker"), r.get("fiscal_year")): r for r in rows}

    # 🚨 todo = **셀**에서 계산한다 (2026-08-23). 종전 `t not in done or t in gap_tickers` 는
    #   행이 purge 된 셀을 볼 수 없었다 — 07-06 purge 48칸이 그렇게 얼었다.
    def _cell(t, y):
        return f"{t}|{y}"

    def _exhausted(t, y):
        if args.retry_exhausted:
            return False
        record = missing.get(_cell(t, y)) or {}
        # Only confirmed official no-data is exhaustible. Legacy `error` entries
        # with n>=2 and unknown historical statuses remain retryable.
        return _is_exhausted_no_data(record)

    pending_by_tk = {}
    for t, n in universe:
        ys = [y for y in years if (t, y) not in seen and not _exhausted(t, y)]
        if ys:
            pending_by_tk[t] = ys
    todo = [(t, n) for (t, n) in universe if t in pending_by_tk]
    _pending_cells = sum(len(v) for v in pending_by_tk.values())
    _exh = sum(1 for v in missing.values() if _is_exhausted_no_data(v))
    print(f"[fin-bf] universe {len(universe)} | 대상종목 {len(todo)} | 대상칸 {_pending_cells} "
          f"| 시도포기칸 {_exh} | done(참고) {len(done)} | years {years[0]}~{years[-1]} "
          f"| cap {args.quota_cap}", file=sys.stderr)

    attempted_at = datetime.now(timezone.utc).isoformat()
    new_n = req_n = empty_n = error_n = attempted_cells = 0
    touched_tickers = set()

    def _last_run():
        deferred_n = max(0, _pending_cells - new_n - empty_n - error_n)
        return {
            "attempted_at": attempted_at,
            "requested": _pending_cells,
            "attempted": attempted_cells,
            "success": new_n,
            "empty": empty_n,
            "error": error_n,
            "deferred": deferred_n,
            "touched": len(touched_tickers),
            # Legacy aliases remain for existing readers.
            "new_rows": new_n,
            "empty_cells": empty_n,
            "requests": req_n,
            "tickers_touched": len(touched_tickers),
        }

    for idx, (tk, name) in enumerate(todo, 1):
        if args.quota_cap is not None and req_n >= args.quota_cap:
            print(f"[fin-bf] quota-cap {args.quota_cap} 도달 — 중단(다음 run 이어받음)", file=sys.stderr)
            break
        try:
            cc = get_corp_code(tk)
        except Exception:  # noqa: BLE001 — never persist exception text or request URLs
            cc = None
        touched_tickers.add(tk)
        if not cc:
            unresolved = [y for y in pending_by_tk.get(tk, []) if (tk, y) not in seen]
            attempted_cells += len(unresolved)
            for y in unresolved:
                _record_error(missing, _cell(tk, y), "corp_code_unavailable")
                error_n += 1
            done.add(tk); _save_done(done)
            continue
        for y in pending_by_tk.get(tk, []):
            if (tk, y) in seen:
                continue
            if args.quota_cap is not None and req_n >= args.quota_cap:
                break   # 🚨 셀 단위로 끊는다 — 종목 중간에 멈춰도 원장이 이어받는다
            req_n += 1
            attempted_cells += 1
            try:
                raw = _fetch_fnltt_all_cached(cc, str(y), "CFS")
            except Exception:  # noqa: BLE001 — bounded reason only
                _record_error(missing, _cell(tk, y), "fetch_exception")
                error_n += 1
                continue

            kind, data, error_reason = _response_kind(raw)
            if kind == "error":
                _record_error(missing, _cell(tk, y), error_reason)
                error_n += 1
                continue
            if kind == "empty":  # Only official no-data status 013 permits OFS fallback.
                if args.quota_cap is not None and req_n >= args.quota_cap:
                    continue  # deferred; do not spend a no-data attempt until OFS is checked
                req_n += 1
                try:
                    raw = _fetch_fnltt_all_cached(cc, str(y), "OFS")
                except Exception:  # noqa: BLE001 — bounded reason only
                    _record_error(missing, _cell(tk, y), "fetch_exception")
                    error_n += 1
                    continue
                kind, data, error_reason = _response_kind(raw)
                if kind == "error":
                    _record_error(missing, _cell(tk, y), error_reason)
                    error_n += 1
                    continue
                if kind == "empty":
                    _record_empty(missing, _cell(tk, y))
                    empty_n += 1
                    continue

            try:
                source_rows = {}
                plbs = _extract_pl_bs_from_dart(data, source_rows=source_rows)
            except Exception:  # noqa: BLE001 — bounded reason only
                _record_error(missing, _cell(tk, y), "extract_failed")
                error_n += 1
                continue

            def observed(field):
                value = plbs.get(field)
                if value != 0:
                    return value
                # The extractor also initializes absent accounts to zero. Only
                # a numeric zero in the selected raw account is an observation.
                source = source_rows.get(field) or {}
                raw = str(source.get("thstrm_amount", "")).replace(",", "").strip()
                return 0 if re.fullmatch(r"[+-]?0+", raw) else None

            rev, op, net = (observed(field) for field in ("revenue", "operating_profit", "net_income"))
            inv_re = plbs.get("investment_property")
            if all(value is None for value in (rev, op, net)):
                # status 000 with no target metrics is not official no-data;
                # keep it retryable rather than exhausting the cell.
                _record_error(missing, _cell(tk, y), "no_target_metrics")
                error_n += 1
                continue
            # An explicitly reported zero is a fact, not a missing account.
            fund = {"revenue": rev, "operating_profit": op,
                    "net_income": net, "investment_property": inv_re or None}
            existing = rows_by_key.get((tk, y))
            if existing is not None:
                old_fund = existing.get("fundamentals") or {}
                loses_numeric_value = any(
                    isinstance(old_value, (int, float))
                    and not isinstance(old_value, bool)
                    and fund.get(field) is None
                    for field, old_value in old_fund.items()
                )
                if loses_numeric_value:
                    _record_error(missing, _cell(tk, y), "partial_replacement")
                    error_n += 1
                    continue
                existing["fundamentals"] = fund   # null-net 행 in-place 갱신 (중복 append 방지)
            else:
                new_row = {"ticker": tk, "name": name, "fiscal_year": y, "period": "annual", "fundamentals": fund}
                rows.append(new_row)
                rows_by_key[(tk, y)] = new_row
            seen.add((tk, y))
            missing.pop(_cell(tk, y), None)   # 채워졌으면 원장에서 뺀다
            new_n += 1
        done.add(tk)
        _save_done(done)
        if idx % 25 == 0 or idx == len(todo):
            _write_out(rows)                  # 주기 저장(crash-safe)
            _save_missing(missing, {"last_run": _last_run()})
            print(f"[fin-bf] {idx}/{len(todo)} — 신규행 {new_n} · 빈칸 {empty_n} · "
                  f"오류 {error_n} · req {req_n}",
                  file=sys.stderr)

    _write_out(rows)
    _save_missing(missing, {"last_run": _last_run()})
    print(f"[fin-bf] 완료 — 신규행 {new_n} · 빈칸 {empty_n} · 오류 {error_n} · req {req_n} · "
          f"총행 {len(rows)} · 원장 {len(missing)}칸 -> {os.path.relpath(OUT_PATH, _ROOT)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

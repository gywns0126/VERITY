"""
earnings_surprise.py — PEAD 서프라이즈 관측 신호 (Phase 1, observation-only).

사전등록 (2026-06-23, N=0): 서프라이즈 부호+크기 → forward N거래일 수익률 예측 (PEAD).
검증 지표 (미래): Spearman IC + Q5-Q1 spread, Newey-West t.
검증 조건 (미래): N>=50 실적 이벤트 후 별도 사전등록 수행.
검증 윈도우: +1d / +5d / +20d / +60d.

RULE 7: brain_input=False, weight=0. scoring 미개시. observation-only trail만 적재.
KR OP기반 / US EPS기반 혼재 — 별도 caveats 명시.

두 단계:
  stage 1 (run_shadow): 이벤트 발견 → trail append (entry_price, forward=null).
  stage 2 (eval_forward_returns): 경과 거래일 도달 시 forward 수익률 채우기.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from api.config import DATA_DIR, now_kst

TRAIL_PATH = os.path.join(DATA_DIR, "observations", "earnings_surprise.jsonl")

_CAVEAT = (
    "관측-only, N<50 미반영, KR OP기반/US EPS기반 혼재. "
    "사전등록 2026-06-23 N=0. 채점=N>=50 달성 후 별도 등록."
)

# forward 윈도우 (거래일 수)
_FORWARD_WINDOWS: Dict[str, int] = {"d1": 1, "d5": 5, "d20": 20, "d60": 60}

# grace: forward 채점 지연 허용 (snapshot 지연 대응)
_FORWARD_GRACE_DAYS = 14


def _compute_op_surprise_pct(actual_op: float, est_op: float) -> Optional[float]:
    """영업이익 서프라이즈 % = (actual - est) / |est|.

    est=0 또는 None → None (제외). 분모 guard: |est| < 1 → None.
    """
    if est_op is None or actual_op is None:
        return None
    if abs(est_op) < 1:
        return None
    return round((actual_op - est_op) / abs(est_op) * 100.0, 4)


def _load_existing_keys(trail_path: str) -> set:
    """기존 trail에서 (ticker, report_quarter) 집합 반환 — 중복 append 방지."""
    keys: set = set()
    if not os.path.exists(trail_path):
        return keys
    with open(trail_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            for ev in obj.get("events", []):
                t = ev.get("ticker")
                q = ev.get("report_quarter")
                if t and q:
                    keys.add((t, q))
    return keys


def _try_entry_price(
    ticker: str,
    announce_date: str,
    is_us: bool,
    current_price: Optional[float],
) -> Optional[float]:
    """history snapshot에서 announce_date 기준 entry price 조회. 실패 시 current_price fallback."""
    try:
        from api.workflows.archiver import list_available_dates, load_snapshot
        from api.intelligence.backtest_archive import (
            _find_nearest_snapshot,
            _get_price_map_from_snapshot,
        )
        available = list_available_dates()
        snap_date = _find_nearest_snapshot(announce_date, available)
        if not snap_date:
            return current_price
        snap = load_snapshot(snap_date)
        if not snap:
            return current_price
        price = _get_price_map_from_snapshot(snap).get(ticker)
        return float(price) if price and float(price) > 0 else current_price
    except Exception:
        return current_price


def normalize_us_surprise(stock: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Finnhub earnings_surprises → trail events. US EPS 기반.

    stock['earnings_surprises'] = [{period, actual, estimate, surprise_pct}, ...]
    (finnhub_client.get_earnings_surprises 반환값, 최대 4분기).
    """
    raw_list = stock.get("earnings_surprises")
    if not raw_list or not isinstance(raw_list, list):
        return []
    ticker = str(stock.get("ticker") or "")
    if not ticker:
        return []
    current_price: Optional[float] = None
    try:
        current_price = float(stock.get("price") or 0) or None
    except (TypeError, ValueError):
        pass

    events: List[Dict[str, Any]] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        period = item.get("period")
        if not period:
            continue
        surprise_pct = item.get("surprise_pct")
        if surprise_pct is None:
            continue
        try:
            surprise_pct = float(surprise_pct)
        except (TypeError, ValueError):
            continue

        # report_quarter = period 문자열 (e.g. "2024-09-28"). announce_date는 period 근사.
        # TODO(local-verify): Finnhub period = 회계분기 종료일. 실제 발표일은 통상 2~6주 후.
        # PEAD 정밀 연구 시 Finnhub reportDate 또는 별도 announcement_date 소스 필요.
        report_quarter = str(period)
        announce_date = str(period)

        entry_price = _try_entry_price(ticker, announce_date, is_us=True, current_price=current_price)

        events.append({
            "ticker": ticker,
            "market": "US",
            "report_quarter": report_quarter,
            "announce_date": announce_date,
            "surprise_pct": surprise_pct,
            "metric": "eps",
            "est_source": "finnhub",
            "actual_source": "finnhub",
            "entry_price": entry_price,
            "forward": {w: None for w in _FORWARD_WINDOWS},
        })
    return events


def compute_kr_surprise(stock: Dict[str, Any]) -> List[Dict[str, Any]]:
    """KR 영업이익 서프라이즈 계산 시도.

    # TODO(local-verify): 룩어헤드 가드 미충족 — 현 구조로 KR join 불가.
    #
    # 문제: ConsensusScout est_op (operating_profit_estimate_bn) 은 Naver Finance
    # 실시간 스크래핑값 = 현재 시점 estimate. DART annual report 발표 후 애널리스트가
    # estimate를 업데이트하므로, 당해연도 발표 이후 수집된 estimate는
    # post-announcement estimate = look-ahead 오염.
    #
    # 해결 조건: pre-announcement estimate 스냅샷 인프라 구축 필요.
    # (예: eps_estimates.jsonl 방식의 KR OP estimate 일별 스냅샷, estimate_year_label
    #  + 수집 timestamp 기록 → announce_date 이전 스냅샷만 사용)
    # → 별도 Sprint으로 처리. 현재는 skip하여 look-ahead 오염 방지.
    #
    # TODO(local-verify): DART operating_profit 단위 = 백만원 (thstrm_amount 기준).
    # ConsensusScout operating_profit_estimate_bn 단위 = 추정 억원 (Naver 기업실적분석 테이블).
    # 단위 정합: actual_억원 = operating_profit / 100. 로컬 검증 후 활성화.
    #
    # TODO(local-verify): dart_fundamentals.py의 operating_profit = 연간 (reprt_code 11011,
    # 사업보고서). 분기 서프라이즈를 위해서는 reprt_code 11013/11012/11014 (분기/반기/3분기)
    # 별도 호출 필요. 현재 dart_fundamentals.py는 연간만 지원.
    #
    # 아래 코드는 향후 활성화를 위한 참조 구현. 실제 실행 경로: return [].
    """
    # 룩어헤드 오염 방지: KR join 현재 skip.
    return []


# ─── helper (향후 KR 활성화용, 단위 검증 완료 후 compute_kr_surprise에서 호출) ───

def _kr_surprise_from_parts(
    actual_op_m: float,  # DART operating_profit (백만원)
    est_op_eok: float,   # ConsensusScout operating_profit_estimate_bn (추정 억원)
) -> Optional[float]:
    """KR OP 서프라이즈 % (단위 변환 내장).

    # TODO(local-verify): est_op_eok 단위가 실제로 억원인지 검증 필요 (Naver 테이블 기준).
    # 단위 불일치 시 이 함수는 사용 금지.
    actual_op_eok = actual_op_m / 100  (백만원 → 억원)
    """
    if actual_op_m is None or est_op_eok is None:
        return None
    actual_op_eok = actual_op_m / 100.0
    return _compute_op_surprise_pct(actual_op_eok, est_op_eok)


def run_shadow(stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """stage 1: 서프라이즈 이벤트 발견 → trail append (brain_input=False, forward=null).

    - US: Finnhub earnings_surprises (EPS 기반).
    - KR: look-ahead 가드 미충족으로 현재 skip (compute_kr_surprise 참조).
    - 중복 append 방지: (ticker, report_quarter) 기존 trail key 제외.
    """
    existing_keys = _load_existing_keys(TRAIL_PATH)

    new_events: List[Dict[str, Any]] = []
    markets_counter: Dict[str, int] = {"US": 0, "KR": 0}

    for stock in stocks:
        is_us = stock.get("currency") == "USD"
        if is_us:
            evs = normalize_us_surprise(stock)
        else:
            evs = compute_kr_surprise(stock)
        for ev in evs:
            key = (ev["ticker"], ev["report_quarter"])
            if key in existing_keys:
                continue
            existing_keys.add(key)
            new_events.append(ev)
            markets_counter[ev.get("market", "??")] = markets_counter.get(ev.get("market", "??"), 0) + 1

    logged = False
    if new_events:
        try:
            os.makedirs(os.path.dirname(TRAIL_PATH), exist_ok=True)
            entry = {
                "ts_kst": now_kst().isoformat(),
                "shadow": True,
                "brain_input": False,
                "caveat": _CAVEAT,
                "events": new_events,
            }
            with open(TRAIL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            logged = True
        except Exception:
            pass

    return {
        "ts_kst": now_kst().isoformat(),
        "n_events": len(new_events),
        "markets": markets_counter,
        "logged": logged,
        "caveat": _CAVEAT,
    }


# ─── stage 2: forward return 채우기 ───────────────────────────────────────────


def _read_trail(trail_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(trail_path):
        return []
    out: List[Dict[str, Any]] = []
    with open(trail_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _rewrite_trail(trail_path: str, entries: List[Dict[str, Any]]) -> None:
    """원자적 rewrite (forward fill 갱신 반영). temp → replace."""
    os.makedirs(os.path.dirname(trail_path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(trail_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        os.replace(tmp, trail_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _forward_return(
    ticker: str,
    announce_date: str,
    entry_price: Optional[float],
    n_days: int,
    available: List[str],
) -> Optional[float]:
    """announce_date 기준 n_days번째 거래일 수익률.

    prediction_scoring._realized_terminal_return 패턴 재사용.
    한계 주석: 상폐 케이스에서 d1~d60 중 일부 윈도우가 동일 종결가를 공유할 수 있음
    (prediction_scoring 의 single-condition limitation 동일 — 미래 보정 대상).
    """
    if not entry_price or entry_price <= 0:
        return None
    try:
        from api.workflows.archiver import load_snapshot
        from api.intelligence.backtest_archive import _get_price_map_from_snapshot
    except Exception:
        return None

    after = sorted(d for d in available if d > announce_date)
    if not after:
        return None

    if len(after) >= n_days:
        # 정상 경로: n_days번째 available snapshot
        target_snap_date = after[n_days - 1]
        try:
            snap = load_snapshot(target_snap_date)
            p = _get_price_map_from_snapshot(snap).get(ticker) if snap else None
            if p and float(p) > 0:
                return round((float(p) - entry_price) / entry_price * 100.0, 4)
        except Exception:
            pass
        return None
    else:
        # 상폐/소멸 fallback: 마지막 available snapshot (survivorship-free)
        for d in reversed(after):
            try:
                snap = load_snapshot(d)
                p = _get_price_map_from_snapshot(snap).get(ticker) if snap else None
                if p and float(p) > 0:
                    return round((float(p) - entry_price) / entry_price * 100.0, 4)
            except Exception:
                continue
        return None


def eval_forward_returns(trail_path: Optional[str] = None) -> Dict[str, Any]:
    """stage 2: forward return 채우기 (d1/d5/d20/d60).

    forward[window] = None인 이벤트 중 announce_date 기준 충분한 거래일이 경과한 것을 채점.
    history snapshot 기반 (prediction_scoring 패턴).
    """
    trail_path = trail_path or TRAIL_PATH
    entries = _read_trail(trail_path)
    if not entries:
        return {"filled": 0, "pending": 0, "note": "trail 비어있음"}

    try:
        from api.workflows.archiver import list_available_dates
        available = list_available_dates()
    except Exception as e:
        return {"filled": 0, "pending": 0, "note": f"snapshot 조회 실패: {e}"}

    today_str = now_kst().strftime("%Y-%m-%d")
    filled_total = 0
    pending_total = 0
    changed = False

    for entry in entries:
        for ev in entry.get("events", []):
            announce_date = ev.get("announce_date")
            entry_price = ev.get("entry_price")
            ticker = ev.get("ticker")
            fwd = ev.get("forward", {})
            if not announce_date or not ticker:
                continue

            for window, n_days in _FORWARD_WINDOWS.items():
                if fwd.get(window) is not None:
                    continue  # 이미 채워진 윈도우

                # 충분한 snapshot 경과 여부 확인
                after = sorted(d for d in available if d > announce_date)
                if len(after) < n_days and today_str <= announce_date:
                    pending_total += 1
                    continue

                grace_after = sorted(d for d in available if d > announce_date)
                if len(grace_after) < n_days:
                    # 아직 n_days 미경과 — grace 내면 보류
                    pending_total += 1
                    continue

                ret = _forward_return(ticker, announce_date, entry_price, n_days, available)
                if ret is not None:
                    ev["forward"][window] = ret
                    filled_total += 1
                    changed = True

    if changed:
        _rewrite_trail(trail_path, entries)

    return {
        "filled": filled_total,
        "pending": pending_total,
        "note": "forward return 채우기 완료" if changed else "변경 없음",
    }


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="earnings_surprise 관측 신호")
    parser.add_argument("--eval-forward", action="store_true", help="stage 2: forward return 채우기")
    args = parser.parse_args()

    if args.eval_forward:
        r = eval_forward_returns()
        print(f"[earnings_surprise] stage2 forward fill: {r}")
    else:
        print("[earnings_surprise] run_shadow은 main.py에서 candidates와 함께 호출됩니다.")
        print(f"  trail path: {TRAIL_PATH}")
        print(f"  caveat: {_CAVEAT}")
        sys.exit(0)

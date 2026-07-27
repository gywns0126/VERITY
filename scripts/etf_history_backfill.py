#!/usr/bin/env python3
"""ETF 과거 시계열 백필 — KRX etf_bydd_trd 를 거래일별로 거슬러 올라가며 종목별 파일로 축적.

배경 (2026-07-27):
  etf_flow.py 는 "오늘" 만 적재한다. 커버리지를 25 → 1,150 종으로 넓혔지만(#171) 신규 편입 종목은
  시계열이 1일뿐이라 수익률·변동성·누적 자금흐름 같은 판단 재료가 없다. 로컬 가격 레이크
  (kr_prices.duckdb, 2,521종)에도 ETF 는 0건 — 실측 확인.

왜 싼가:
  같은 엔드포인트가 basDd(거래일) 파라미터라 **1콜 = 그날 상장 ETF 전량**. 1년 ≈ 245콜.
  종목 수와 무관하게 일수에만 비례한다.

저장 구조 (per-ticker, compact columnar):
  data/etf_hist/{ticker}.json = {"t": ticker, "n": name, "d": [날짜...], "c": [종가...],
                                  "v": [NAV...], "s": [상장좌수...], "a": [순자산...]}
  · 리포트는 검색된 1종목만 lazy fetch → 단일 blob 비대화 회피(전량 1파일이면 10MB+).
  · 배열 병렬 구조 = 키 반복 제거. 245일 기준 종목당 약 12KB.

운영:
  · 회차당 --max-days 만큼만 진행하고 커서를 _state.json 에 기록 → 다음 실행이 이어받음(drip).
  · --probe 는 쓰기 없이 과거 날짜 응답 여부만 확인(설계 전제 검증용).
  · 이미 담긴 날짜는 건너뜀(멱등). 날짜 오름차순 유지.

🚨 RULE 7 — 여기서 만드는 것은 관측 사실(가격·NAV·좌수·순자산)뿐. 점수·등급·추천 산출 금지.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.config import DATA_DIR, now_kst  # noqa: E402
from api.collectors.etfdata import _fetch_etf_day, _parse_float  # noqa: E402

OUT_DIR = os.path.join(DATA_DIR, "etf_hist")
STATE_PATH = os.path.join(OUT_DIR, "_state.json")

# etf_flow.py 와 동일 키 후보 (KRX 응답 키 변형 대응)
_SHRS_KEYS = ["LIST_SHRS", "LISTSHRS", "LIST_SHRS_CO", "INVSTASST_LIST_SHRS"]
_NETASST_KEYS = ["NETASST_TOTAMT", "INVSTASST_NETASST_TOTAMT", "NETASST", "NETASST_AMT"]
_NAV_KEYS = ["NAV"]
_CLOSE_KEYS = ["TDD_CLSPRC"]

SLEEP_SEC = float(os.environ.get("ETF_HIST_SLEEP", "0.4") or "0.4")
# 빈 응답 재시도 상한 — 이 횟수를 넘겨야 휴장일로 확정(쿼터·일시 장애와 구분)
EMPTY_RETRY = int(os.environ.get("ETF_HIST_EMPTY_RETRY", "3") or "3")


def _pick(row: Dict[str, Any], keys: List[str]) -> Optional[float]:
    for k in keys:
        if k in row:
            v = _parse_float(row.get(k))
            if v is not None:
                return v
    return None


def _business_days_back(n: int) -> List[str]:
    """오늘(KST)부터 거슬러 올라간 평일 n개 — 최신순."""
    out: List[str] = []
    d = now_kst().date()
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


def _load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def probe() -> int:
    """과거 basDd 응답 여부 확인 — 쓰기 없음. 설계 전제(백필 가능) 검증용."""
    days = _business_days_back(400)
    targets = [(0, "최근"), (5, "1주"), (22, "1개월"), (65, "3개월"),
               (130, "6개월"), (250, "1년"), (399, "1년반")]
    ok = 0
    for idx, label in targets:
        if idx >= len(days):
            continue
        bas = days[idx]
        rows = _fetch_etf_day(bas)
        n = len(rows or {})
        print(f"  {label:6} {bas}  rows={n}")
        if n:
            ok += 1
        time.sleep(SLEEP_SEC)
    print(f"\n[PROBE] 응답 있는 시점 {ok}/{len(targets)}")
    if ok <= 1:
        print("[PROBE] ⚠ 과거 날짜 미제공 가능성 — 백필 설계 재검토 필요", file=sys.stderr)
        return 1
    return 0


def backfill(max_days: int, horizon: int) -> Dict[str, Any]:
    os.makedirs(OUT_DIR, exist_ok=True)
    state = _load_json(STATE_PATH)
    done = set(state.get("days_done") or [])
    # 🚨 빈 응답을 휴장일로 단정하면 쿼터·장애로 빈 날이 영구 누락됨(데이터 완결성 직결).
    #   성공한 날만 done, 빈 날은 카운트만 올리고 다음 회차에 재시도. EMPTY_RETRY 회 넘으면 휴장 확정.
    empty = {str(k): int(v) for k, v in (state.get("empty_counts") or {}).items()}

    # 최신 → 과거 순으로 훑되, 이미 성공한 날짜와 휴장 확정일은 건너뜀
    candidates = [
        d for d in _business_days_back(horizon)
        if d not in done and empty.get(d, 0) < EMPTY_RETRY
    ]
    todo = candidates[:max_days]
    if not todo:
        print("[ETF_HIST] 백필 완료 상태 — 새로 받을 거래일 없음")
        return {"status": "complete", "days": 0, "tickers": 0}

    # 종목별 누적 버퍼 (이번 회차에 등장한 종목만 로드/기록)
    buf: Dict[str, Dict[str, Any]] = {}
    fetched_days = 0
    for bas in todo:
        rows = _fetch_etf_day(bas)
        time.sleep(SLEEP_SEC)
        if not rows:
            empty[bas] = empty.get(bas, 0) + 1
            tag = "휴장 확정" if empty[bas] >= EMPTY_RETRY else f"재시도 예정({empty[bas]}/{EMPTY_RETRY})"
            print(f"[ETF_HIST] {bas} 응답 없음 — {tag}", file=sys.stderr)
            continue
        fetched_days += 1
        for ticker, row in rows.items():
            rec = buf.get(ticker)
            if rec is None:
                path = os.path.join(OUT_DIR, f"{ticker}.json")
                rec = _load_json(path) or {}
                rec.setdefault("t", ticker)
                for k in ("d", "c", "v", "s", "a"):
                    rec.setdefault(k, [])
                buf[ticker] = rec
            if bas in rec["d"]:
                continue
            nm = str(row.get("ISU_NM") or "").strip()
            if nm:
                rec["n"] = nm
            rec["d"].append(bas)
            rec["c"].append(_pick(row, _CLOSE_KEYS))
            rec["v"].append(_pick(row, _NAV_KEYS))
            rec["s"].append(_pick(row, _SHRS_KEYS))
            rec["a"].append(_pick(row, _NETASST_KEYS))
        done.add(bas)
        print(f"[ETF_HIST] {bas} {len(rows)}종 적재", file=sys.stderr)

    # 날짜 오름차순 정렬 후 기록
    written = 0
    for ticker, rec in buf.items():
        order = sorted(range(len(rec["d"])), key=lambda i: rec["d"][i])
        for k in ("d", "c", "v", "s", "a"):
            rec[k] = [rec[k][i] for i in order]
        rec["days"] = len(rec["d"])
        rec["updated_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
        with open(os.path.join(OUT_DIR, f"{ticker}.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, separators=(",", ":"))
        written += 1

    state = {
        "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "days_done": sorted(done),
        "days_count": len(done),
        "empty_counts": empty,
        "holiday_confirmed": sorted([d for d, n in empty.items() if n >= EMPTY_RETRY]),
        "horizon": horizon,
        "remaining": max(0, len(candidates) - len(todo)),
        "note": "KRX etf_bydd_trd 거래일별 백필 — 관측 사실(가격·NAV·좌수·순자산)만. drip 진행.",
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

    print(f"[ETF_HIST] 거래일 {fetched_days}일 · 종목 {written}개 기록 · 누적 {len(done)}일 "
          f"· 남은 후보 {state['remaining']}일")
    return {"status": "ok", "days": fetched_days, "tickers": written,
            "cum_days": len(done), "remaining": state["remaining"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="과거 날짜 응답 여부만 확인(쓰기 없음)")
    ap.add_argument("--max-days", type=int, default=40, help="이번 회차에 받을 거래일 수")
    ap.add_argument("--horizon", type=int, default=250, help="백필 목표 거래일(≈1년)")
    a = ap.parse_args()
    if a.probe:
        return probe()
    s = backfill(a.max_days, a.horizon)
    print(json.dumps(s, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

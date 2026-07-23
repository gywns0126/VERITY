"""dart_quarterly_public_builder — KR 분기/연 재무 비율 추이 public 빌더 (PublicQuarterlyTrend 재사용).

입력: data/dart_quarterly_snapshots.jsonl (dart_quarterly_backfill / dart_batch 누적)
  각 라인 = {ticker, quarter_end, roa, debt_ratio, current_ratio, gross_margin, asset_turnover, fetched_at}
출력: data/dart_quarterly_public.json — us_quarterly_public.json 과 동일 스키마
  {stocks: {ticker: {quarters: [{q, debt_ratio, roa, current_ratio, gross_margin, asset_turnover}]}}}
  → PublicQuarterlyTrend 컴포넌트 무변환 재사용 (quarterlyUrl 기본값이 이 파일).

🚨 데이터 질 가드:
  - quarter_end 가 **fiscal-end(03-31/06-30/09-30/12-31)** 인 행만 수록.
    원천에 fetch-날짜(예: 05-17 단일 스냅샷)로 찍힌 junk 행이 섞여 있어 그대로 쓰면 가짜 추이가 됨 → 제거.
  - 동일 (ticker, quarter_end) 중복 = fetched_at 최신 1건만 (재backfill 정합).
  - 5비율이 전부 null 인 분기 = 미수록. 비율 ≥4 분기 종목만 수록(컴포넌트 series<4 미표시 게이트 정합).
🚨 RULE 7 — 계산된 사실 비율만(점수·등급 0). 순수 변환 — 외부호출 0.
publish: data/dart_quarterly_public.json (publish-data action 등재 필요).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUT_PATH = os.path.join(_ROOT, "data", "dart_quarterly_snapshots.jsonl")
OUTPUT_PATH = os.path.join(_ROOT, "data", "dart_quarterly_public.json")

FISCAL_ENDS = {"03-31", "06-30", "09-30", "12-31"}
RATIO_KEYS = ("debt_ratio", "roa", "current_ratio", "gross_margin", "asset_turnover")
MIN_QUARTERS = 4   # 컴포넌트 게이트(series<4 = 미표시) 정합

# 🚨 magnitude 가드 — DART 원천 XBRL 오류(누적-분기 혼입/원가 태그 오류)로 팽창한 값 auto-null.
#   정의·물리 불가능만 격리(오탐 0). self-ref outlier 는 오탐 과다(133 hit 대부분 정상 사업 mix)로
#   auto-null 배제 — 삼성 gm 38→61 류 미세팽창은 수집층(dart_fundamentals) 기간정합 교차검증 후속 큐.
#   근거: /tmp dry-run 실측 2026-07-23 (1,900종목, 12값 격리, 전부 정의상 불가능 확인).
# gross_margin = gp/rev → gp>rev 은 정의 불가(9값: 085660 gm 140-188·060980 781 등). period-agnostic 안전.
# roa = ni/총자산(>0) → roa>100 = ni>자산(단일기간) 물리 불가(3값: 007700 492 등). 음수측은
#   write-off/청산으로 극단 가능 → 하드 X.
RATIO_BOUNDS = {
    "gross_margin": (-100.0, 100.0),
    "roa": (None, 100.0),
}


def _now_kst() -> datetime:
    return datetime.now(KST)


def build() -> Dict[str, Any]:
    # ticker -> {q: (fetched_at, quarter_dict)} — 중복은 fetched_at 최신 1건
    by_ticker: Dict[str, Dict[str, Any]] = {}
    bad_dates = 0
    magnitude_dropped = 0   # 정의·물리 불가능으로 null 처리한 ratio-value 수 (관측)
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ticker = str(row.get("ticker") or "").strip()
            qe = str(row.get("quarter_end") or "").strip()
            if not ticker or len(qe) < 10:
                continue
            if qe[5:10] not in FISCAL_ENDS:   # fetch-날짜 junk 제거
                bad_dates += 1
                continue
            q: Dict[str, Any] = {"q": qe}
            for k in RATIO_KEYS:
                v = row.get(k)
                if v is None:
                    continue
                try:
                    fv = round(float(v), 2)
                except (TypeError, ValueError):
                    continue
                lo_hi = RATIO_BOUNDS.get(k)
                if lo_hi is not None:
                    lo, hi = lo_hi
                    if (lo is not None and fv < lo) or (hi is not None and fv > hi):
                        magnitude_dropped += 1   # 정의·물리 불가능 → null 처리(행은 유지)
                        continue
                q[k] = fv
            if len(q) <= 1:   # 비율 전부 null
                continue
            fetched = str(row.get("fetched_at") or "")
            slot = by_ticker.setdefault(ticker, {})
            prev = slot.get(qe)
            if prev is None or fetched >= prev[0]:   # 최신 fetched_at 우선
                slot[qe] = (fetched, q)

    stocks: Dict[str, Any] = {}
    for ticker, qmap in by_ticker.items():
        quarters = [pair[1] for pair in qmap.values()]
        if len(quarters) < MIN_QUARTERS:
            continue
        quarters.sort(key=lambda x: str(x["q"]))
        stocks[ticker] = {"quarters": quarters}

    return {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "OpenDART (dart_quarterly_snapshots.jsonl, fiscal-end만)",
            "count": len(stocks),
            "dropped_nonfiscal_rows": bad_dates,
            "dropped_magnitude_values": magnitude_dropped,
            "note": "분기/연 재무 비율 사실(부채비율/ROA/유동비율/매출총이익률/자산회전율) — 점수·등급 0 (RULE 7). fiscal-end 행만.",
        },
        "stocks": stocks,
    }


def main() -> int:
    ok = False
    try:
        if not os.path.isfile(INPUT_PATH):
            print(f"[dart_quarterly_public] {INPUT_PATH} 부재 — skip", file=sys.stderr)
            return 0
        out = build()
        if not out["stocks"]:
            # 0종목 = 상류 단일기간(현 dart_quarterly_snapshots 2025-only). 빈 파일 발행 방지 — 아예 안 씀.
            # 기존 파일 있으면 그대로 보존(덮어쓰지 않음). 상류 분기수집 확장되면 자동으로 실데이터 기록.
            print("[dart_quarterly_public] 0 stocks — skip(빈 파일 발행 안 함)", file=sys.stderr)
            ok = True
            return 0
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[dart_quarterly_public] logged=True · {len(out['stocks'])} 종목 "
              f"(non-fiscal {out['_meta']['dropped_nonfiscal_rows']}행 · "
              f"magnitude-null {out['_meta']['dropped_magnitude_values']}값 제거) -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[dart_quarterly_public] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[dart_quarterly_public] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

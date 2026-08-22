"""dart_quarterly_public_builder — KR 분기/연 재무 비율 추이 public 빌더 (PublicQuarterlyTrend 재사용).

입력: data/dart_quarterly_snapshots.jsonl (dart_quarterly_backfill / dart_batch 누적)
  각 라인 = {ticker, quarter_end, roa, debt_ratio, current_ratio, gross_margin, asset_turnover, fetched_at}
출력: data/dart_quarterly_public.json — us_quarterly_public.json 과 동일 스키마
  {stocks: {ticker: {quarters: [{q, debt_ratio, roa, current_ratio, gross_margin, asset_turnover,
                                 revenue, operating_profit, net_income}]}}}
  🚨 손익 3종은 **최근 12분기에만** 실린다(발행 용량). 비율은 전 기간.
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

# 🚨 2026-08-22 — 위 집합은 **12월 결산 전용**이다. 비12월 결산 법인의 분기말은
#   결산월+3/6/9/12 개월이라 이 집합에 없다 — 실측: 결산월 01·02·04·05·07·08·11
#   (14종목)의 분기말이 `01-31`·`02-28`·`05-31` 등이라 **전부 junk 로 폐기**됐다.
#   (3·6·9·12월 결산 39종목은 우연히 같은 집합이라 통과한다.)
#   quarter_end 소급 정정 직후 이 필터가 종목 10개를 떨어뜨린 것이 실측 증거다
#   (2,532 → 2,522 · non-fiscal 2,631 → 3,117).
#   그래서 **종목별 결산월로 허용 집합을 만든다.** 맵 미수록이면 종전 집합(안전측).
_FISCAL_MONTH_PATH = os.path.join(os.path.dirname(OUTPUT_PATH), "kr_fiscal_month.json")
_MMDD_LAST = {"01": "31", "02": "28", "03": "31", "04": "30", "05": "31", "06": "30",
              "07": "31", "08": "31", "09": "30", "10": "31", "11": "30", "12": "31"}
_fiscal_map: Dict[str, str] | None = None


def _allowed_ends(ticker: str) -> set:
    """그 종목의 회계 분기말 4개. 결산월 미상이면 12월 결산 기본값."""
    global _fiscal_map
    if _fiscal_map is None:
        try:
            with open(_FISCAL_MONTH_PATH, encoding="utf-8") as f:
                _fiscal_map = (json.load(f) or {}).get("map") or {}
        except (OSError, ValueError):
            _fiscal_map = {}
    fm = str(_fiscal_map.get(str(ticker)) or "12")
    if fm == "12":
        return FISCAL_ENDS
    out = set()
    for off in (3, 6, 9, 12):
        m = (int(fm) + off - 1) % 12 + 1
        out.add(f"{m:02d}-{_MMDD_LAST[f'{m:02d}']}")
    return out
RATIO_KEYS = ("debt_ratio", "roa", "current_ratio", "gross_margin", "asset_turnover")
MIN_QUARTERS = 4   # 컴포넌트 게이트(series<4 = 미표시) 정합

# 🚨 2026-08-22 — 손익 절대금액을 싣는다. 종전에는 **비율 5종만** 나가서
#   "적자 전환" 이 원리적으로 안 보였다. 실사례 021820(세원정공):
#   연간 순이익 488억(지분법 230 + 금융수익 135 포함)이라 초저평가로 읽히는데
#   분기 영업이익은 81 → 78 → 51 → **−6.7억** 이다. 비율만으로는 이 전환을 못 본다.
#   net_income 만으로도 부족하다 — 본업과 영업외가 섞이기 때문이다.
PL_KEYS = ("revenue", "operating_profit", "net_income")
# 🚨 최근 N분기만 싣는다 — 이 파일은 **발행 대상**이고 Vercel 전송비가 붙는다.
#   실측: 전량 추가 = 8.65 → 14.66MB(1.69배, 발행 총량 89.9MB 대비 +6.7%).
#   12분기(3년)면 적자 전환(4)·YoY(8)·2Q 연속가속(8~12)을 전부 덮으면서 +2.57MB 다.
#   비율은 종전대로 전 기간 유지한다(가벼움).
PL_RECENT_Q = 12

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
            if qe[5:10] not in _allowed_ends(ticker):   # fetch-날짜 junk 제거(결산월 반영)
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
            # 🚨 손익은 여기서 담고, 분기 수 제한은 종목 단위 정렬 후에 적용한다
            #   (여기서 자르면 어느 분기가 최근인지 알 수 없다).
            for k in PL_KEYS:
                v = row.get(k)
                if v is None:
                    continue
                try:
                    q[k] = int(v)
                except (TypeError, ValueError):
                    continue
            # 🚨 종전 조건은 "비율 전부 null 이면 행 폐기" 였다. 손익만 있는 행이
            #   통째로 버려져 왔다 — 021820 이 분기 4개 미만으로 탈락한 원인 중 하나다.
            if len(q) <= 1:   # q 키 하나뿐 = 비율·손익 모두 없음
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
        # 🚨 손익은 최근 PL_RECENT_Q 개에만 남긴다(발행 용량 — 위 상수 주석 참조).
        for qq in quarters[:-PL_RECENT_Q] if len(quarters) > PL_RECENT_Q else []:
            for k in PL_KEYS:
                qq.pop(k, None)
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

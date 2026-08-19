"""분기 매출 시계열 조립 — `revenue_acceleration` 의 2Q 연속가속 보강 입력.

## 왜 필요했나 (PM 승인 2026-08-19 "2Q 보강 배선")

`multi_bagger_signals.detect_revenue_acceleration` 은 설계 당시부터
`stock["dart_financials"]["quarterly_revenue"]` 를 읽어 **가속의 연속성**을 확인하게
돼 있었다(단일 분기 스파이크 = 기저효과 노이즈 배제, score ±10/−5).
그런데 그 키를 **만드는 곳이 코드 전체에 없었다** — grep 결과 참조 4곳이 전부
같은 파일의 소비 지점이었다. 실측 2026-08-19: watch 최신일 **448/448 전량 None**.
설계된 방어가 통째로 죽어 있었고, 산출물만 봐서는 알 수 없었다.

## 데이터 (RULE 13 — 열거 먼저)

`data/dart_quarterly_snapshots.jsonl` — 2,806 티커 · 2021~2026.
고유 분기 ≥3 인 티커 **2,645** / ≥4 **2,568**. 시계열 깊이는 충분하다.
🚨 **다만 이 파일에는 `revenue` 필드가 없었다.** 수집기(`dart_fundamentals`)는 매출을
이미 파싱해 `asset_turnover = rev/ta` 까지 쓰고도 스냅샷에 안 실었다(2026-08-19 수리).
따라서 **과거 행은 매출이 비어 있고**, 신규 수집분부터 채워진다.
전량 소급은 (ticker, quarter) 재조회가 필요하다 = DART 쿼터 사안, PM 결정.

## 🚨 왜 '같은 분기 · 연도 간' 으로 뽑나 (핵심 설계 판단)

소비 코드는 인접 두 항목의 성장률을 비교한다:
    q_growths[i] = (series[i] − series[i+1]) / series[i+1]
    가속 = q_growths[0] > q_growths[1]

여기에 **직전 분기들을 순서대로** 넣으면 두 가지가 동시에 깨진다.

1. **계절성** — 한국 분기 매출은 계절성이 강하다. 전분기 대비 증감은 사업 가속이
   아니라 달력을 재게 된다. 보강의 목적이 "기저효과 노이즈 배제" 인데 정반대가 된다.
2. 🚨 **누적 공시 함정** — DART 분기보고서는 **누적**이다(q1=1Q, h1=상반기 누계,
   q3=3분기 누계, annual=연간). 순차 비교를 하려면 차분(Q2 = h1 − q1)이 선행돼야 하고,
   빠뜨리면 매 분기 "성장" 이 조작된다. 같은 사고 계열 = [[feedback_cluster_silent_defect]].

**그래서 같은 reprt_code 를 연도만 바꿔 뽑는다** (예: 2026 상반기 · 2025 상반기 · 2024 상반기).
그러면 ① 계절성이 상쇄되고 ② 양쪽이 같은 누적 구간이라 **차분 자체가 불필요**하다.
소비 코드는 **한 줄도 바뀌지 않는다** — q_growths[0] 이 올해 YoY, q_growths[1] 이 작년 YoY 가
되어 비교가 "YoY 성장률이 작년보다 높아졌나" = 진짜 가속 판정이 된다.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Tuple

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data")
SNAPSHOT_PATH = os.path.join(_DATA, "dart_quarterly_snapshots.jsonl")

MIN_POINTS = 3          # 소비 코드가 성장률 2개(=가속 비교 1회)를 만들려면 최소 3점


def _fiscal_year(quarter_end: Any) -> int | None:
    s = str(quarter_end or "")[:4]
    return int(s) if s.isdigit() else None


def build_series(path: str = SNAPSHOT_PATH) -> Tuple[Dict[str, List[float]], Dict[str, Any]]:
    """→ ({ticker: [최신연도, 직전연도, ...] 매출}, 커버리지 신고)

    같은 `reprt_code`(= 같은 회계 분기)를 연도만 바꿔 내림차순으로 담는다.
    한 티커가 여러 reprt_code 를 가지면 **가장 최근 quarter_end 가 속한 것** 하나만 쓴다
    (분기를 섞으면 계절성이 다시 들어온다).
    """
    if not os.path.exists(path):
        return {}, {"error": "snapshot_missing", "path": path}

    # (ticker, reprt_code) → {fiscal_year: (quarter_end, revenue)}
    grid: Dict[Tuple[str, str], Dict[int, Tuple[str, float]]] = defaultdict(dict)
    rows_total = rows_with_rev = 0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        rows_total += 1
        rev = r.get("revenue")
        if not isinstance(rev, (int, float)) or rev <= 0:
            continue        # 결측/0 은 성장률 분모가 될 수 없다 — 넣지 않는다
        tk, rc = r.get("ticker"), r.get("reprt_code")
        fy = _fiscal_year(r.get("quarter_end"))
        if not tk or not rc or fy is None:
            continue
        rows_with_rev += 1
        prev = grid[(str(tk), str(rc))].get(fy)
        qe = str(r.get("quarter_end"))
        # 같은 (티커, 분기, 연도) 중복 = 최신 fetched_at 우선이나, 스냅샷은 append 순서가
        # 곧 수집 순서라 뒤에 온 것을 채택한다(기존 load_quarterly_snapshots 규약과 동일).
        if prev is None or qe >= prev[0]:
            grid[(str(tk), str(rc))][fy] = (qe, float(rev))

    # 티커별로 '가장 최근 분기' 하나를 고른다
    best: Dict[str, Tuple[str, str]] = {}      # ticker → (최신 quarter_end, reprt_code)
    for (tk, rc), years in grid.items():
        latest_qe = max(v[0] for v in years.values())
        if tk not in best or latest_qe > best[tk][0]:
            best[tk] = (latest_qe, rc)

    series: Dict[str, List[float]] = {}
    for tk, (_qe, rc) in best.items():
        years = grid[(tk, rc)]
        ordered = [years[fy][1] for fy in sorted(years, reverse=True)]
        if len(ordered) >= MIN_POINTS:
            series[tk] = ordered

    meta = {
        "rows_total": rows_total,
        "rows_with_revenue": rows_with_rev,
        "tickers_with_any_revenue": len(best),
        "tickers_usable": len(series),          # MIN_POINTS 이상 = 가속 판정 가능
        "min_points": MIN_POINTS,
        "basis": "same_reprt_code_year_over_year",
        "note": ("같은 회계분기를 연도만 바꿔 내림차순. 계절성 상쇄 + DART 누적공시라도 "
                 "양쪽이 같은 누적구간이라 차분 불필요."),
    }
    return series, meta


def attach(stocks: Dict[str, Dict[str, Any]],
           path: str = SNAPSHOT_PATH) -> Dict[str, Any]:
    """stock dict 들에 `dart_financials.quarterly_revenue` 를 붙이고 커버리지를 반환.

    🚨 커버리지를 **반드시 반환**한다 — 이 보강이 448/448 죽어 있던 걸 아무도 몰랐던
    이유가 정확히 "붙었는지 아닌지를 아무도 세지 않아서" 다(RULE 12).
    """
    series, meta = build_series(path)
    attached = 0
    for tk, s in stocks.items():
        vals = series.get(str(tk))
        if not vals:
            continue
        fin = s.get("dart_financials")
        if not isinstance(fin, dict):
            fin = {}
            s["dart_financials"] = fin
        fin["quarterly_revenue"] = vals
        attached += 1
    meta["attached"] = attached
    meta["attach_target"] = len(stocks)
    meta["attach_pct"] = round(attached / len(stocks) * 100, 2) if stocks else 0.0
    return meta

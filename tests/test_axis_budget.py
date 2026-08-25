# -*- coding: utf-8 -*-
"""축별 wall-clock 예산 — 한 축이 job 전체를 먹으면 뒤 축이 굶는다 (2026-08-25 신설).

## 사고

`kr-company-facts-backfill` 8/25 06:40 scheduled run 이 **90분 job timeout 으로 cancelled**.
로그 실측 — `chain` 축이 21:42 에 시작해 23:10 취소까지 **88분을 다 썼고**, 그 뒤 축인
`overview` 는 **시작조차 못 했다**. 그게 개요 유니버스 분리의 N=2 였다.

같은 형태가 이전에도 있었다:

| run | chain | 수확 | overview |
|---|---|---|---|
| 8/22 | **51분** | **3/200** | 미실행 |
| 8/23 | 25분 | 17/200 | 175/195 성공 |
| 8/25 | **88분+** | 미완 | **미실행(타임아웃)** |

즉 `overview` 가 도는지 여부가 **chain 이 그날 얼마나 느린가**에 달려 있었다.
축 순서(뒤쪽)가 곧 기아(starvation)였다 —
[[feedback_concurrency_starvation_pending_slot]] 의 축 버전이다.

## 규약

- 축마다 **새로** 예산을 준다. 누적 예산이면 앞 축이 다 쓰고 뒤 축이 0 이 된다.
- 예산으로 끊긴 것은 **정체가 아니다** — 진척이고 다음 run 이 이어받는다.
  전량 실패 가드(`_stalled`)가 이를 실패로 읽으면 exit 1 오탐이 난다.
- 중단은 조용히 하지 않는다. **몇 종목을 안 했는지** 숫자로 신고한다.
"""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _bf():
    spec = importlib.util.spec_from_file_location(
        "bf", str(_ROOT / "scripts" / "kr_company_facts_backfill.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_cli_exposes_axis_budget_with_safe_default():
    m = _bf()
    import argparse, sys
    # main() 의 파서를 직접 재현하지 않고, --help 문자열로 계약만 확인한다.
    src = (_ROOT / "scripts" / "kr_company_facts_backfill.py").read_text(encoding="utf-8")
    assert '"--axis-budget"' in src
    assert "default=1500" in src, "기본 예산이 없으면 아무도 안 켠다"


def test_budget_is_per_axis_not_cumulative():
    """🚨 누적이면 앞 축이 다 쓰고 뒤 축이 0 이 된다 — 지금 고치는 결함 그 자체."""
    src = (_ROOT / "scripts" / "kr_company_facts_backfill.py").read_text(encoding="utf-8")
    i = src.index("for ax in axes:")
    seg = src[i:i + 400]
    assert "time.time() + a.axis_budget" in seg, "축 루프 안에서 예산을 새로 잡아야 한다"


def test_chain_stops_at_deadline_and_reports_remainder():
    """이미 지난 deadline → 첫 항목에서 즉시 중단하고 잔여를 숫자로 신고한다.

    🚨 하드코딩 대신 **불변식**으로 본다 — 첫 작성이 가짜 티커 `000000~000049` 를 썼는데
    그중 일부가 `chain_snippets.json` 에 실재해 todo 가 49 로 줄었다. 분모를 고정값으로
    가정한 것이 원인이다([[feedback_denominator_before_conclusion]] 의 작은 판).
    """
    m = _bf()
    univ = [(f"Z{i:05d}", f"종목{i}") for i in range(50)]   # Z 접두 = 실재하지 않는 형태
    r = m.run_chain(univ, "2025", 0.0, False, limit=50, deadline=time.time() - 1)
    assert r["todo"] > 0, "픽스처가 전부 필터링됐다 — 테스트가 아무것도 검증하지 않는다"
    assert r["budget_stopped"] == r["todo"], "중단 잔여를 숫자로 신고하지 않는다"
    assert r["ok"] == 0


def test_budget_stop_is_not_counted_as_stalled():
    """예산 중단을 '정체' 로 읽으면 전량 실패 가드가 exit 1 오탐을 낸다."""
    src = (_ROOT / "scripts" / "kr_company_facts_backfill.py").read_text(encoding="utf-8")
    i = src.index("def _stalled(v):")
    seg = src[i:i + 420]
    assert "budget_stopped" in seg and "return False" in seg


def test_overview_analyzer_stops_fetching_at_deadline(tmp_path, monkeypatch):
    """지난 deadline → **문서를 받지 않는다**. 비싼 건 fetch 이므로 거기서 끊는다.

    🚨 캐시 히트는 막지 않는다 — 공짜이고, 막으면 이미 채운 종목이 결과에서 빠진다.
    (첫 작성이 `out` 이 비어야 한다고 단정했다가 캐시 히트에 걸려 실패했다.
     예산이 막아야 할 대상은 '결과' 가 아니라 '네트워크' 다.)
    """
    import json as _json
    import inspect
    from api.analyzers import dart_business_overview as O
    assert "deadline" in inspect.signature(O.analyze_all_overview).parameters

    cache = tmp_path / "ov.json"
    cache.write_text(_json.dumps({"rows": {}, "misses": {}}), encoding="utf-8")
    monkeypatch.setattr(O, "CACHE_PATH", str(cache))

    calls = []
    monkeypatch.setattr("api.collectors.DartScout.fetch_business_facilities_raw",
                        lambda cc, y: calls.append(cc) or {"raw_text": "x"})
    stocks = {"005930": {"corp_code": "00126380", "name": "삼성전자", "bsns_year": "2025"}}
    O.analyze_all_overview(stocks, auto_fetch_missing=True, deadline=time.time() - 1)
    assert calls == [], "예산이 지났는데 문서를 받았다"

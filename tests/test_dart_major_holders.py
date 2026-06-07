"""
KR 기관 대량보유(5%+) collector — 필터/집계 검증 (네트워크 없음).
action_queue d7158b4f. 관측 only.
"""
from __future__ import annotations

from api.collectors.dart_major_holders import _is_institutional, aggregate_holders


def test_is_institutional():
    assert _is_institutional("국민연금공단")
    assert _is_institutional("BlackRockFundAdvisors")
    assert _is_institutional("TheCapitalGroupCompanies,Inc.")
    assert _is_institutional("미래에셋자산운용")
    # 전략/사업회사·개인 = 제외
    assert not _is_institutional("삼성물산")
    assert not _is_institutional("이재용")
    assert not _is_institutional("SK디스커버리홀딩스")  # 지주 제외 힌트
    assert not _is_institutional("")


def test_aggregate_latest_per_reporter_and_flow():
    rows = [
        # 국민연금 — 2건 중 최신(2026-02) 채택, 처분(-)
        {"repror": "국민연금공단", "stkrt": "8.0", "stkqy_irds": "100", "rcept_dt": "2025-01-01"},
        {"repror": "국민연금공단", "stkrt": "7.3", "stkqy_irds": "-500", "rcept_dt": "2026-02-01"},
        # BlackRock — 매집(+)
        {"repror": "BlackRockFundAdvisors", "stkrt": "5.0", "stkqy_irds": "200", "rcept_dt": "2026-02-20"},
        # 전략적 대주주 — 제외
        {"repror": "삼성물산", "stkrt": "20.0", "stkqy_irds": "0", "rcept_dt": "2026-01-01"},
        # 이미 처분 완료(0%) — 현재 보유자 아님 → 제외
        {"repror": "Capital Group", "stkrt": "0.0", "stkqy_irds": "-99999", "rcept_dt": "2026-03-01"},
    ]
    out = aggregate_holders(rows)
    assert out["n_institutions"] == 2  # 국민연금 + BlackRock (삼성물산·0% Capital 제외)
    assert out["total_institutional_pct"] == 12.3  # 7.3 + 5.0
    names = [h["reporter"] for h in out["institutional_holders"]]
    assert "삼성물산" not in names and "Capital Group" not in names
    # 국민연금 최신 row = 처분(-500)
    nps = next(h for h in out["institutional_holders"] if h["reporter"] == "국민연금공단")
    assert nps["pct"] == 7.3 and nps["qty_change"] == -500
    # flow: 매집1(BlackRock) / 처분1(국민연금) → neutral
    assert out["net_flow_direction"] == "neutral"


def test_aggregate_empty():
    assert aggregate_holders([])["n_institutions"] == 0
    assert aggregate_holders([])["total_institutional_pct"] is None

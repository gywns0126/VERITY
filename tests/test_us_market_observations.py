"""
미장 관측 로깅 v0 — 파싱/dedupe 검증 (네트워크 없음).
[[project_observation_scoring_prereg_queue]] 관측-only.
"""
from __future__ import annotations

import json


# AAII 페이지 구조 재현: 데이터 테이블(현재행) + 장기평균/High prose 가 공존.
AAII_FIXTURE = """
<table><tr><td>Bullish</td><td>Neutral</td><td>Bearish</td></tr>
<tr><td>6/3/2026</td><td>36.3%</td><td>26.7%</td><td>37.0%</td></tr>
<tr><td>5/27/2026</td><td>35.6%</td><td>22.6%</td><td>41.9%</td></tr></table>
<p>Bullish High: 49.5% Week Ending 1/14/2026</p>
<p>Bearish sentiment has averaged 30.5% over the long term.</p>
"""


def test_parse_aaii_picks_current_row_not_averages():
    from api.collectors.us_market_observations import _parse_aaii
    out = _parse_aaii(AAII_FIXTURE)
    assert out is not None
    assert out["period"] == "2026-06-03"
    m = out["metrics"]
    assert m["bullish"] == 36.3 and m["neutral"] == 26.7 and m["bearish"] == 37.0
    assert m["bull_bear_spread"] == -0.7  # 36.3 - 37.0
    # 현재행 합 = 100 (장기평균 30.5% / High 49.5% 오인 안 함)
    assert 99.0 <= m["bullish"] + m["neutral"] + m["bearish"] <= 101.0


def test_parse_aaii_rejects_when_no_table():
    from api.collectors.us_market_observations import _parse_aaii
    # 데이터 테이블 없이 prose 만 — 현재값 못 잡으면 None (잘못된 값 게재 방지)
    assert _parse_aaii("<p>Bullish has averaged 37.5% historically.</p>") is None


def test_append_observations_dedupe(tmp_path, monkeypatch):
    import api.collectors.us_market_observations as m
    obs = tmp_path / "obs.jsonl"
    monkeypatch.setattr(m, "OBS_DIR", str(tmp_path))
    monkeypatch.setattr(m, "OBS_PATH", str(obs))

    recs = [
        {"source": "aaii", "period": "2026-06-03", "metrics": {"bullish": 36.3}},
        {"source": "naaim", "period": "2026-06-03", "metrics": {"exposure_mean": 86.8}},
    ]
    assert m.append_observations(recs) == 2
    # 동일 (source, period) 재호출 → 0건 (dedupe)
    assert m.append_observations(recs) == 0
    # 새 period 만 추가
    recs2 = [{"source": "aaii", "period": "2026-06-10", "metrics": {"bullish": 40.0}}]
    assert m.append_observations(recs2) == 1

    lines = obs.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert "observed_at" in first and first["source"] == "aaii"

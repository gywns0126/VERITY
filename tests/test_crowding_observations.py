"""
test_crowding_observations.py — 팩터 crowding raw 관측 로거 v0 단위 검증.

관측 only / date dedupe / graceful empty / 조합식·점수 0 / per-symbol short 파싱.
"""
import json

import pytest

from api.observability import crowding_observations as CO


def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def test_snapshot_appends_and_shape(tmp_path):
    p = str(tmp_path / "crowd.jsonl")
    rec = CO.build_crowding_snapshot(
        per_symbol_short={"AAPL": 48.2, "TSLA": 55.1},
        market_short_pct=49.5,
        aaii_metrics={"bullish": 35.0, "bearish": 40.0},
        naaim_metrics={"mean": 62.0},
        factor_ic={"momentum": 0.04, "value": -0.01},
        path=p,
    )
    rows = _load(p)
    assert len(rows) == 1
    r = rows[0]
    assert r["n_symbols"] == 2 and r["per_symbol_short_pct"]["AAPL"] == 48.2
    assert r["market_short_volume_pct"] == 49.5
    assert r["factor_ic_snapshot"]["momentum"] == 0.04
    assert r["aaii_metrics"]["bearish"] == 40.0


def test_observation_only_no_score_fields(tmp_path):
    """RULE 7 — crowding 레코드에 점수/verdict/risk_flag 필드 0."""
    p = str(tmp_path / "crowd.jsonl")
    CO.build_crowding_snapshot(per_symbol_short={"AAPL": 48.0}, market_short_pct=49.0, path=p)
    r = _load(p)[0]
    forbidden = {"score", "verdict", "risk_flag", "risk_flags", "auto_avoid", "brain_score", "weight", "crowding_score"}
    assert forbidden.isdisjoint(r.keys())
    assert r["spec"] == "crowding_v0_raw_observation"


def test_date_dedupe(tmp_path):
    p = str(tmp_path / "crowd.jsonl")
    CO.build_crowding_snapshot(per_symbol_short={"AAPL": 48.0}, market_short_pct=49.0, path=p)
    CO.build_crowding_snapshot(per_symbol_short={"AAPL": 99.0}, market_short_pct=88.0, path=p)  # 같은 날 재시도
    rows = _load(p)
    assert len(rows) == 1  # 중복 append 차단
    assert rows[0]["market_short_volume_pct"] == 49.0  # 첫 기록 유지


def test_graceful_empty(tmp_path):
    """핵심 입력(종목별 + 시장 short) 둘 다 결손 = None, 파일 미생성."""
    import os
    p = str(tmp_path / "crowd.jsonl")
    out = CO.build_crowding_snapshot(per_symbol_short=None, market_short_pct=None, path=p)
    assert out is None
    assert not os.path.exists(p)


def test_market_only_logs(tmp_path):
    """종목별 결손이어도 시장 short 있으면 기록 (graceful 부분)."""
    p = str(tmp_path / "crowd.jsonl")
    rec = CO.build_crowding_snapshot(per_symbol_short=None, market_short_pct=50.0, path=p)
    assert rec is not None and rec["n_symbols"] == 0


def test_finra_per_symbol_parse(monkeypatch):
    """CNMSshvol 개별 행 파싱 — parts[1]=symbol, [2]=short, [4]=total."""
    from api.collectors import us_market_observations as obs

    sample = (
        "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
        "20260612|AAPL|480000|0|1000000|Q\n"
        "20260612|TSLA|550000|0|1000000|Q\n"
        "20260612|ZZZZ|100|0|200|Q\n"  # 유니버스 밖 → 제외
    )

    class _R:
        status_code = 200
        text = sample

    class _S:
        def get(self, *a, **k):
            return _R()

    out = obs.fetch_finra_short_per_symbol(
        obs.now_kst(), ["AAPL", "TSLA"], session=_S()
    )
    assert out is not None
    assert out["per_symbol_short_pct"] == {"AAPL": 48.0, "TSLA": 55.0}
    assert out["covered"] == 2 and "ZZZZ" not in out["per_symbol_short_pct"]

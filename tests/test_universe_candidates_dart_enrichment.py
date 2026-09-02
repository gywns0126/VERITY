import json
from datetime import datetime, timedelta, timezone

from api.utils import dart_pre_attach
from api.utils import universe_candidates as uc


KST = timezone(timedelta(hours=9))


def test_cached_candidates_reapply_dart_after_kr_previous_snapshot(monkeypatch, tmp_path):
    """kr_used_prev snapshot 도 daily fast path 진입 전에 DART 재무를 복구한다."""
    now = datetime.now(KST)
    snapshot_path = tmp_path / "universe_candidates.json"
    dart_path = tmp_path / "dart_fundamentals_kr.json"

    snapshot_path.write_text(
        json.dumps(
            {
                "collected_at": now.isoformat(),
                "diagnostics": {
                    "kr_count": 1,
                    "us_count": 1,
                    "kr_used_prev": True,
                },
                "candidates": [
                    {"ticker": "005930", "currency": "KRW", "name": "삼성전자"},
                    {"ticker": "AAPL", "currency": "USD", "name": "Apple"},
                ],
            }
        ),
        encoding="utf-8",
    )
    dart_path.write_text(
        json.dumps(
            {
                "collected_at": now.isoformat(),
                "fundamentals": {
                    "005930": {
                        "asset_turnover": 0.72,
                        "gross_margin": 36.1,
                        "gross_profit": 10_000,
                        "net_income": 5_000,
                        "revenue": 30_000,
                        "retained_earnings": 20_000,
                        "total_assets": 100_000,
                        "working_capital": 15_000,
                        "source": "DART-test",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(uc, "SNAPSHOT_PATH", str(snapshot_path))
    monkeypatch.setattr(uc, "_now_kst", lambda: now)
    monkeypatch.setattr(dart_pre_attach, "DART_KR_PATH", dart_path)
    uc.reset_cache()

    out = uc.load_universe_candidates(force_reload=True)

    assert out is not None
    kr, us = out["candidates"]
    assert kr["total_assets"] == 100_000
    assert kr["gross_profit"] == 10_000
    assert kr["dart_source"] == "DART-test"
    assert "total_assets" not in us
    assert out["_load_enrichment"]["dart"] == {
        "attached_n": 1,
        "kr_total_n": 1,
        "cache_hit": True,
    }


def test_dart_enrichment_failure_keeps_cached_candidates(monkeypatch, tmp_path):
    """보강 예외는 자기신고하고 기존 후보를 보존한다."""
    now = datetime.now(KST)
    snapshot_path = tmp_path / "universe_candidates.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "collected_at": now.isoformat(),
                "diagnostics": {"kr_count": 1, "us_count": 0},
                "candidates": [{"ticker": "005930", "currency": "KRW"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(uc, "SNAPSHOT_PATH", str(snapshot_path))
    monkeypatch.setattr(uc, "_now_kst", lambda: now)
    monkeypatch.setattr(
        dart_pre_attach,
        "attach_dart_to_stocks",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("test failure")),
    )
    uc.reset_cache()

    out = uc.load_universe_candidates(force_reload=True)

    assert out is not None
    assert out["candidates"] == [{"ticker": "005930", "currency": "KRW"}]
    assert out["_load_enrichment"]["dart"]["cache_hit"] is False
    assert "RuntimeError" in out["_load_enrichment"]["dart"]["error"]

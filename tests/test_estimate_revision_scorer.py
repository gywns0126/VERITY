"""estimate_revision_scorer — A2 리비전 모멘텀 SHADOW 테스트 (2026-06-15).

PIT 리비전(자체 trail current 차이) 산출 + universe 경고 + brain 무입력 검증.
"""
import api.intelligence.estimate_revision_scorer as rs


def _snap(ticker, date_str, eps_0y, eps_1y, invalidate=False):
    return {
        "ticker": ticker, "snapshot_date": date_str, "invalidate": invalidate,
        "eps_trend": {
            "0y": {"current": eps_0y},
            "+1y": {"current": eps_1y},
        },
    }


def test_upward_revision_positive_score():
    # 30일 전 2.0 → 현재 2.2 = +10% 상향
    snaps = [_snap("X", "2026-05-01", 2.0, 3.0), _snap("X", "2026-06-01", 2.2, 3.3)]
    r = rs._ticker_revision(snaps)
    assert r["status"] == "ok"
    assert r["revision_score"] > 0
    assert r["direction"] == "up"
    assert r["cluster_agreement"] == 1.0  # 두 기간 모두 상향


def test_downward_revision_negative():
    snaps = [_snap("X", "2026-05-01", 2.0, 3.0), _snap("X", "2026-06-01", 1.8, 2.7)]
    r = rs._ticker_revision(snaps)
    assert r["revision_score"] < 0 and r["direction"] == "down"


def test_insufficient_single_snapshot():
    assert rs._ticker_revision([_snap("X", "2026-06-01", 2.0, 3.0)])["status"] == "insufficient"


def test_insufficient_prior_too_recent():
    # 두 스냅샷이 5일 차 (< MIN_PRIOR_GAP 14) → insufficient
    snaps = [_snap("X", "2026-05-27", 2.0, 3.0), _snap("X", "2026-06-01", 2.2, 3.3)]
    assert rs._ticker_revision(snaps)["status"] == "insufficient"


def test_find_prior_closest_to_30d():
    latest = rs.date.fromisoformat("2026-06-01")
    snaps = [
        _snap("X", "2026-04-01", 1, 1),  # 61일 전
        _snap("X", "2026-05-02", 1, 1),  # 30일 전 (타겟)
        _snap("X", "2026-05-25", 1, 1),  # 7일 전 (< 14 제외)
    ]
    prior = rs._find_prior(snaps, latest)
    assert prior["snapshot_date"] == "2026-05-02"


def test_invalidate_filtered(tmp_path, monkeypatch):
    trail = tmp_path / "eps.jsonl"
    import json
    rows = [
        _snap("X", "2026-05-01", 2.0, 3.0),
        _snap("X", "2026-06-01", 2.2, 3.3),
        _snap("Y", "2026-06-01", 5.0, 6.0, invalidate=True),  # 무효 → 제외
    ]
    trail.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(rs, "EPS_TRAIL", str(trail))
    loaded = rs._load_trail()
    assert "X" in loaded and "Y" not in loaded


def test_compute_carries_universe_caveat(tmp_path, monkeypatch):
    trail = tmp_path / "eps.jsonl"
    import json
    rows = [_snap("X", "2026-05-01", 2.0, 3.0), _snap("X", "2026-06-01", 2.2, 3.3)]
    trail.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(rs, "EPS_TRAIL", str(trail))
    result = rs.compute_revision_scores()
    # universe 경고 + megacap-decay 명시 필수 (RULE 7 한계 명시)
    assert "megacap" in result["caveat"].lower()
    assert "shadow" in result["caveat"].lower()
    assert result["scored_ok"] == 1


def test_run_shadow_marks_brain_input_false(tmp_path, monkeypatch):
    import json
    trail = tmp_path / "eps.jsonl"
    rows = [_snap("X", "2026-05-01", 2.0, 3.0), _snap("X", "2026-06-01", 2.2, 3.3)]
    trail.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(rs, "EPS_TRAIL", str(trail))
    monkeypatch.setattr(rs, "SHADOW_OUT", str(tmp_path / "shadow.jsonl"))
    rs.run_shadow()
    entry = json.loads((tmp_path / "shadow.jsonl").read_text().strip())
    assert entry["brain_input"] is False and entry["shadow"] is True

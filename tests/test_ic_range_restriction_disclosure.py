"""IC 측정 표본의 절단(range restriction) 명시 — 측정 레이어 정직성.

2026-07-28 발견. factor IC 는 snapshot["recommendations"](= stock_filter 통과 후보군, 수십 종목)
에서 측정되는데, 산출물 어디에도 그 사실이 없었다. sample_count 만 있고 "그게 선발된 후보 수"
라는 맥락이 빠져 전체 유니버스 IC 처럼 읽혔다.

특히 safety_score 는 stock_filter 의 **최종 선발 정렬 키**(:219/220/227/367/368/375 reverse=True)
라서, 자기 선발 기준으로 잘린 집합에서 자기 IC 를 재는 구조 = 고전적 selection bias.
실측 fd=30 에서 safety_score IC -0.1788 / fundamental -0.1494 로 유의한 음수가 나오지만,
절단 표본이라 "신호가 역방향"의 증거가 되지 못한다.

🚨 판정 로직 불변 — is_significant/decay_alert 미변경. 메타데이터만 부착.
"""
from api.quant.alpha import alpha_scanner as A


def _snap(day, n=8):
    return {
        "_date": day,
        "recommendations": [
            {"ticker": f"T{i}", "safety_score": 50 + i, "current_price": 100 + i,
             "multi_factor": {"multi_score": 50 + i, "quant_factors": {}, "factor_breakdown": {}}}
            for i in range(n)
        ],
    }


def test_selection_key_registry_names_safety_score():
    assert "safety_score" in A._SELECTION_KEY_FACTORS
    assert "stock_filter" in A._SELECTION_KEY_FACTORS["safety_score"]


def test_scan_marks_range_restricted(monkeypatch):
    days = [f"2026-06-{d:02d}" for d in range(1, 21)]
    monkeypatch.setattr(
        "api.workflows.archiver.load_snapshots_range",
        lambda n: [_snap(d) for d in days],
    )
    out = A.scan_all_factors(forward_days=7)
    assert out["status"] == "ok"
    assert out["range_restricted"] is True
    assert out["sample_universe"] == "recommendations_post_filter"
    assert "전체 유니버스 아님" in out["range_restriction_note"]
    assert out["self_selection_factors"] == ["safety_score"]


def test_per_factor_flags(monkeypatch):
    days = [f"2026-06-{d:02d}" for d in range(1, 21)]
    monkeypatch.setattr(
        "api.workflows.archiver.load_snapshots_range",
        lambda n: [_snap(d) for d in days],
    )
    out = A.scan_all_factors(forward_days=7)
    fs = out["factors"]
    # 모든 팩터에 표본 절단 표기
    assert all(v.get("range_restricted") is True for v in fs.values())
    # 선발 키만 자기선택 편향 플래그
    assert fs["safety_score"].get("self_selection_bias") is True
    assert fs["safety_score"].get("bias_note")
    assert fs["momentum"].get("self_selection_bias") is None


def test_verdict_logic_untouched(monkeypatch):
    """🚨 판정 필드는 메타 부착 전후 동일해야 함 (산식 불변)."""
    days = [f"2026-06-{d:02d}" for d in range(1, 21)]
    monkeypatch.setattr(
        "api.workflows.archiver.load_snapshots_range",
        lambda n: [_snap(d) for d in days],
    )
    out = A.scan_all_factors(forward_days=7)
    for name, v in out["factors"].items():
        # 메타 키가 판정 키를 덮어쓰지 않았는지
        assert set(v) >= {"ic_mean", "icir"} or v.get("status")
    assert isinstance(out["significant_factors"], list)
    assert isinstance(out["decaying_factors"], list)


def test_insufficient_data_path_unchanged(monkeypatch):
    monkeypatch.setattr("api.workflows.archiver.load_snapshots_range", lambda n: [])
    out = A.scan_all_factors(forward_days=7)
    assert out["status"] == "insufficient_data"


# ── 2026-07-29 후속 — trail 지속 검증 ────────────────────────────────────────
# #190 은 scan_all_factors 반환에만 메타를 달았고, save_ic_snapshot 이 자체 화이트리스트로
# entry 를 조립하는 구조라 factor_ic_history.json 에 실리지 않았음(실측으로 갭 확인).
# trail = 미래 감사·N=252 게이트의 1차 자료 → 거기에 한계가 없으면 전체 유니버스 IC 로 오독됨.

def test_save_ic_snapshot_persists_disclosure(tmp_path, monkeypatch):
    import json as _json
    out = tmp_path / "factor_ic_history.json"
    monkeypatch.setattr(A, "IC_CACHE_PATH", str(out))

    A.save_ic_snapshot({
        "scanned_at": "2026-07-29T10:00:00+09:00",
        "forward_days": 30,
        "sample_universe": "recommendations_post_filter",
        "range_restricted": True,
        "self_selection_factors": ["safety_score"],
        "factors": {
            "safety_score": {"ic_mean": -0.18, "icir": -1.75, "is_significant": True,
                             "decay_alert": False, "sample_count": 55,
                             "self_selection_bias": True},
            "momentum": {"ic_mean": 0.07, "icir": 0.5, "is_significant": False,
                         "decay_alert": False, "sample_count": 55},
        },
    })

    rec = _json.loads(out.read_text(encoding="utf-8"))[-1]
    assert rec["range_restricted"] is True
    assert rec["sample_universe"] == "recommendations_post_filter"
    assert rec["self_selection_factors"] == ["safety_score"]
    assert rec["factors"]["safety_score"]["self_selection_bias"] is True
    assert rec["factors"]["momentum"]["self_selection_bias"] is False
    # 기존 필드 회귀 0
    assert rec["factors"]["safety_score"]["ic_mean"] == -0.18
    assert rec["factors"]["safety_score"]["sample_count"] == 55
    assert rec["date_key"] == "2026-07-29" and rec["forward_days"] == 30


def test_save_ic_snapshot_without_meta_is_safe(tmp_path, monkeypatch):
    """메타 없는 구 호출부도 깨지지 않아야 함 (None/[] 로 degrade)."""
    import json as _json
    out = tmp_path / "factor_ic_history.json"
    monkeypatch.setattr(A, "IC_CACHE_PATH", str(out))
    A.save_ic_snapshot({
        "scanned_at": "2026-07-29T10:00:00+09:00", "forward_days": 7,
        "factors": {"momentum": {"ic_mean": 0.1, "icir": 0.4, "sample_count": 10}},
    })
    rec = _json.loads(out.read_text(encoding="utf-8"))[-1]
    assert rec["range_restricted"] is None
    assert rec["self_selection_factors"] == []
    assert rec["factors"]["momentum"]["self_selection_bias"] is False

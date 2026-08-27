from api.builders import data_health_builder


def test_cdn_cache_age_does_not_change_health_status(monkeypatch):
    monkeypatch.setattr(data_health_builder, "_guard_section", lambda now: {"held_24h": 0, "recent": []})
    monkeypatch.setattr(data_health_builder, "_verify_section", lambda: {
        "ok": True, "failed": 0, "max_cdn_age_s": 999999, "files": []
    })
    monkeypatch.setattr(data_health_builder, "_coverage_section", lambda: {
        "last_run_blocked": False, "last_run_warns": 0
    })
    monkeypatch.setattr(data_health_builder, "_freshness_section", lambda: {
        "stale_p0": [], "stale_other": []
    })

    doc = data_health_builder.build()

    assert doc["status"] == "green"
    assert doc["reasons"] == []

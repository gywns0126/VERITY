import json

from scripts import publish_verify


def test_baseline_ignores_history_from_different_universe_size(tmp_path, monkeypatch):
    hist = tmp_path / "publish_verify.jsonl"
    rows = [
        {"results": [{"file": "stock_report_public.json", "total": 1789,
                      "coverage": {"fin_series": 95.4}}]},
        {"results": [{"file": "stock_report_public.json", "total": 2495,
                      "coverage": {"fin_series": 71.0}}]},
    ]
    hist.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(publish_verify, "HIST", str(hist))

    baseline = publish_verify._baseline_from_history("stock_report_public.json", 2495)

    assert baseline["fin_series"] == 71.0
    assert baseline["_total"] == 2495


def test_baseline_is_empty_when_only_old_denominator_exists(tmp_path, monkeypatch):
    hist = tmp_path / "publish_verify.jsonl"
    hist.write_text(json.dumps({"results": [{"file": "stock_report_public.json", "total": 1789,
                                              "coverage": {"fin_series": 95.4}}]}) + "\n",
                    encoding="utf-8")
    monkeypatch.setattr(publish_verify, "HIST", str(hist))

    assert publish_verify._baseline_from_history("stock_report_public.json", 2495) == {}

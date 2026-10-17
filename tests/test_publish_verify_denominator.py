import json
from unittest.mock import Mock

import pytest

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


def _stocks(n):
    return {"stocks": [{"ticker": f"{i:06}", "facts": {"PER": 10, "PBR": 1}}
                       for i in range(n)]}


@pytest.mark.parametrize("n", [0, 1, 99])
def test_missing_public_universe_fails(monkeypatch, n):
    raw = json.dumps(_stocks(n)).encode()
    monkeypatch.setattr(publish_verify, "_fetch", lambda url: (raw, None))
    result = publish_verify.verify_one("stock_report_public.json", publish_verify.GUARD["stock_report_public.json"])
    assert result["ok"] is False
    assert result["total"] == n


def test_large_universe_loss_is_not_discarded_as_different_cohort(tmp_path, monkeypatch):
    hist = tmp_path / "history.jsonl"
    hist.write_text(json.dumps({"results": [{"file": "stock_report_public.json", "ok": True,
                                            "total": 2500, "coverage": {"fin_series": 90}}]}) + "\n")
    monkeypatch.setattr(publish_verify, "HIST", str(hist))
    raw = json.dumps(_stocks(120)).encode()
    monkeypatch.setattr(publish_verify, "_fetch", lambda url: (raw, None))
    result = publish_verify.verify_one("stock_report_public.json", publish_verify.GUARD["stock_report_public.json"])
    assert result["ok"] is False
    assert "종목수 2500→120" in result["regression"]


def test_repeated_failures_do_not_erase_successful_baseline(tmp_path, monkeypatch):
    hist = tmp_path / "history.jsonl"
    rows = [{"results": [{"file": "stock_report_public.json", "ok": True, "total": 2500}]}]
    rows += [{"results": [{"file": "stock_report_public.json", "ok": False, "total": 2440}]}] * 12
    hist.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    monkeypatch.setattr(publish_verify, "HIST", str(hist))
    assert publish_verify._baseline_from_history("stock_report_public.json", 2440)["_total"] == 2500


def test_malformed_history_row_does_not_crash_or_erase_baseline(tmp_path, monkeypatch):
    hist = tmp_path / "history.jsonl"
    rows = [{"results": [{"file": "stock_report_public.json", "ok": True, "total": 2500}]},
            {"results": [1]}, [], {"results": "bad"},
            {"results": [{"file": "stock_report_public.json", "ok": True,
                          "total": 2500, "coverage": [1]}]}]
    hist.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    monkeypatch.setattr(publish_verify, "HIST", str(hist))
    assert publish_verify._baseline_from_history("stock_report_public.json", 2440)["_total"] == 2500


@pytest.mark.parametrize("plain", [_stocks(101), ValueError("unavailable")])
def test_user_facing_content_must_be_read_and_match(monkeypatch, plain):
    second = plain if isinstance(plain, Exception) else (json.dumps(plain).encode(), None)
    monkeypatch.setattr(publish_verify, "_fetch", Mock(side_effect=[(json.dumps(_stocks(100)).encode(), None), second]))
    result = publish_verify.verify_one("stock_report_public.json", publish_verify.GUARD["stock_report_public.json"])
    assert result["ok"] is False
    assert "일반 공개 주소" in result["error"]


def test_identical_json_with_old_cdn_age_is_valid(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_verify, "HIST", str(tmp_path / "no_history"))
    doc = _stocks(100)
    monkeypatch.setattr(publish_verify, "_fetch", Mock(side_effect=[
        (json.dumps(doc).encode(), None), (json.dumps(doc, indent=2).encode(), "999999")]))
    result = publish_verify.verify_one("stock_report_public.json", publish_verify.GUARD["stock_report_public.json"])
    assert result["ok"] is True
    assert result["plain_matches"] is True


@pytest.mark.parametrize("doc", [[], {"stocks": [3]}, {"stocks": [None]},
                                 {"stocks": [{"facts": [1]}]}, {"stocks": [{"facts": "broken"}]}])
def test_invalid_stock_shape_fails_without_crashing(monkeypatch, doc):
    monkeypatch.setattr(publish_verify, "_fetch", lambda url: (json.dumps(doc).encode(), None))
    assert publish_verify.verify_one("stock_report_public.json", publish_verify.GUARD["stock_report_public.json"])["ok"] is False

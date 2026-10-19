"""Historical correction flags must agree with the official filing title."""
import json
from datetime import datetime

import pytest

from api.builders import disclosure_forensics_builder as builder
from api.builders import public_disclosure_feed_builder as feed_builder
from api.builders.disclosure_why_templates import why_for_kr


def test_historical_false_flags_are_rechecked_without_rewriting_inputs(tmp_path, monkeypatch):
    source = tmp_path / "alerts.jsonl"
    backfill = tmp_path / "backfill.jsonl"
    output = tmp_path / "forensics.json"
    rows = [
        {"ticker": "074610", "rcept_no": "20260618000199", "rcept_dt": "20260618",
         "report_nm": "[기재정정]주요사항보고서(유상증자결정)", "is_correction": False},
        {"ticker": "074610", "rcept_no": "20260618000200", "rcept_dt": "20260618",
         "report_nm": "[첨부정정]사업보고서", "is_correction": False},
        {"ticker": "074610", "rcept_no": "20260618000201", "rcept_dt": "20260618",
         "report_nm": "주요사항보고서(전환사채권발행결정)", "is_correction": False},
        {"ticker": "074610", "rcept_no": "20260618000202", "rcept_dt": "20260618",
         "report_nm": "사업보고서", "corr_yn": "Y"},
        {"ticker": "074610", "rcept_no": "20260618000203", "rcept_dt": "20260618",
         "report_nm": "사업보고서", "is_correction": True},
        {"ticker": "074610", "rcept_no": "20260618000204", "rcept_dt": "20260618",
         "report_nm": "사업보고서", "is_correction": False},
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    backfill.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    before = source.read_bytes(), backfill.read_bytes()
    monkeypatch.setattr(builder, "INPUT_PATH", str(source))
    monkeypatch.setattr(builder, "BACKFILL_PATH", str(backfill))
    monkeypatch.setattr(builder, "OUTPUT_PATH", str(output))

    assert builder.main() == 0
    stock = json.loads(output.read_text())["stocks"][0]
    assert stock["total"] == 5  # Duplicate receipt and ordinary annual filing excluded.
    assert stock["counts"] == {"정정공시": 4, "전환사채(CB)": 1}
    assert stock["dilution_count"] == 1
    assert stock["forensics_flags"]["correction_count"] == 4
    assert stock["forensics_flags"]["correction_pct"] == 80
    events = {event["source_url"].split("=")[-1]: event for event in stock["events"]}
    correction = events["20260618000199"]
    assert correction["is_correction"] is True
    assert correction["category"] == "정정공시"
    assert correction["risk"] == "correction"
    assert (source.read_bytes(), backfill.read_bytes()) == before


@pytest.mark.parametrize("title,stored,corr_yn,expected", [
    ("[기재정정]주요사항보고서(유상증자결정)", False, "", True),
    ("[첨부정정]사업보고서", False, "", True),
    ("사업보고서", False, "Y", True),
    ("사업보고서", True, "", True),
    ("주요사항보고서(유상증자결정)", False, "", False),
])
def test_public_feed_uses_same_correction_fact_and_explanation(monkeypatch, title, stored, corr_yn, expected):
    monkeypatch.setattr(feed_builder, "_now_kst", lambda: datetime(2026, 6, 19, tzinfo=builder.KST))
    monkeypatch.setattr(feed_builder, "_source_collection", lambda now: {"status": "unknown"})
    row = {"ticker": "074610", "rcept_no": "20260618000199", "rcept_dt": "20260618",
           "report_nm": title, "is_correction": stored, "corr_yn": corr_yn}
    before = dict(row)
    monkeypatch.setattr(feed_builder, "_load_alerts", lambda: [row])
    event = feed_builder.build_feed()["items"][0]["disclosures"][0]
    assert event["is_correction"] is expected
    assert event["why_it_matters"] == why_for_kr("정정공시" if expected else "유상증자")
    assert row == before

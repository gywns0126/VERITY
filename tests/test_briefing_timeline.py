"""Behavioral archive tests: preserve observations; never invent a revision."""
from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path

import pytest

from api.builders import briefing_timeline as timeline


def briefing(at="2026-10-06T08:00:00+09:00", amount=100, as_of="2026-10-02"):
    return {"date": datetime.fromisoformat(at).astimezone(timeline.KST).date().isoformat(),
            "generated_at": at, "sections": [{"id": "flow", "title": "수급",
                "as_of": as_of, "note": "추정금액", "items": [{"ticker": "005930",
                "name": "테스트", "text": f"추정 {amount}원", "values": {"estimated_net_krw": amount}}]}]}


def read(folder, name):
    return json.loads((folder / name).read_text())


def test_sessions_archive_three_observations_without_changing_original(tmp_path):
    first = timeline.record_briefing(briefing(), tmp_path)
    original = deepcopy(first["snapshots"][0])
    for at in ("2026-10-06T09:00:00+09:00", "2026-10-06T15:30:00+09:00"):
        latest = timeline.record_briefing(briefing(at), tmp_path)
    assert latest["snapshots"][0] == original
    assert [s["phase"] for s in latest["snapshots"]] == ["pre", "open", "post"]
    assert all(latest["cards"][phase] for phase in ("pre", "open", "post"))
    assert latest["cards"]["closed"] is None
    assert latest["snapshots"][1]["changes"] == []
    before = (tmp_path / "2026-10-06.json").read_bytes()
    timeline.record_briefing(briefing(at), tmp_path)
    assert (tmp_path / "2026-10-06.json").read_bytes() == before


@pytest.mark.parametrize("day,status,reason", [
    ("2026-10-04", "closed", "weekend"), ("2026-10-05", "closed", "holiday"),
    ("2026-10-06", "open", "scheduled_trading_day"),
    ("2026-11-19", "unknown", "special_session_unverified"),
    ("2027-01-02", "unknown", "outside_verified_range"),
    ("2026-09-07", "unknown", "outside_verified_range"),
])
def test_verified_calendar_range_and_special_days(day, status, reason):
    result = timeline.trading_day(date.fromisoformat(day))
    assert (result["status"], result["reason"]) == (status, reason)


def test_holiday_and_unknown_have_no_false_intraday_card(tmp_path):
    closed = timeline.record_briefing(briefing("2026-10-05T12:00:00+09:00"), tmp_path)
    assert closed["cards"]["closed"] and not any(closed["cards"][p] for p in ("pre", "open", "post"))
    unknown = timeline.record_briefing(briefing("2027-01-02T12:00:00+09:00"), tmp_path)
    assert unknown["snapshots"][0]["phase"] == "unknown"
    assert not any(unknown["cards"].values())
    calendar = read(tmp_path, "index.json")["calendar"]
    assert calendar["valid_until"] == "2026-12-31"
    assert "2026-10-05" in calendar["holidays"]
    assert calendar["verified_at"] == "2026-10-04"


def test_same_source_date_numeric_revision_but_new_date_is_observation(tmp_path):
    timeline.record_briefing(briefing(), tmp_path)
    updated = timeline.record_briefing(briefing("2026-10-06T12:00:00+09:00", 125), tmp_path)
    change = updated["snapshots"][-1]["changes"][0]
    assert change["kind"] == "values_changed"
    assert change["delta"] == {"estimated_net_krw": 25}
    assert change["before"]["values"]["estimated_net_krw"] == 100
    later = timeline.record_briefing(briefing("2026-10-06T18:00:00+09:00", 150, "2026-10-06"), tmp_path)
    change = later["snapshots"][-1]["changes"][0]
    assert change["kind"] == "observation"
    assert "delta" not in change
    assert later["snapshots"][0]["source_as_of"] == ["2026-10-02"]


def test_unknown_source_date_never_produces_numeric_delta(tmp_path):
    timeline.record_briefing(briefing(as_of=""), tmp_path)
    updated = timeline.record_briefing(briefing("2026-10-06T12:00:00+09:00", 125, ""), tmp_path)
    assert updated["snapshots"][-1]["changes"][0]["kind"] == "observation"
    assert "delta" not in updated["snapshots"][-1]["changes"][0]


def test_receipt_identity_does_not_merge_distinct_corrections(tmp_path):
    out = briefing()
    row = {"ticker": "005930", "title": "공급계약", "text": "공급계약", "date": "2026-10-06"}
    out["sections"] = [{"id": "disclosures", "title": "공시", "items": [
        {**row, "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261006000001"},
        {**row, "is_correction": True, "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261006000002"},
    ]}]
    archive = timeline.record_briefing(out, tmp_path)
    snapshot = archive["snapshots"][0]
    assert len({item["id"] for item in snapshot["items"]}) == 2
    assert [change["kind"] for change in snapshot["changes"]] == ["new", "correction"]
    assert all("before" not in c for c in snapshot["changes"])


def test_unallowlisted_private_fields_and_urls_do_not_enter_archive(tmp_path):
    out = briefing()
    out["user_id"] = "PRIVATE_SENTINEL"
    out["holdings"] = [{"account": "PRIVATE_SENTINEL"}]
    section = out["sections"][0]
    section["private"] = "PRIVATE_SENTINEL"
    section["items"][0].update({"user_id": "PRIVATE_SENTINEL", "url": "https://private.test/?token=PRIVATE_SENTINEL"})
    section["items"][0]["values"].update({"account_balance": 123, "user_id": "PRIVATE_SENTINEL"})
    timeline.record_briefing(out, tmp_path)
    text = (tmp_path / "2026-10-06.json").read_text()
    assert "PRIVATE_SENTINEL" not in text and "account_balance" not in text
    assert read(tmp_path, "2026-10-06.json")["snapshots"][0]["items"][0]["values"] == {"estimated_net_krw": 100}


def test_next_day_summary_is_sealed_without_synthesizing_gap_days(tmp_path):
    old = timeline.record_briefing(briefing(), tmp_path)
    snapshots = deepcopy(old["snapshots"])
    timeline.record_briefing(briefing("2026-10-08T06:30:00+09:00"), tmp_path)
    sealed = read(tmp_path, "2026-10-06.json")
    assert sealed["snapshots"] == snapshots
    assert sealed["day_summary"]["status"] == "closed"
    assert sealed["day_summary"]["cutoff_at"] == "2026-10-07T00:00:00+09:00"
    assert sealed["day_summary"]["generated_at"] == "2026-10-08T06:30:00+09:00"
    assert not (tmp_path / "2026-10-07.json").exists()
    previous = (tmp_path / "2026-10-06.json").read_bytes()
    timeline.record_briefing(briefing("2026-10-08T12:00:00+09:00"), tmp_path)
    assert (tmp_path / "2026-10-06.json").read_bytes() == previous
    with pytest.raises(ValueError, match="sealed"):
        timeline.record_briefing(briefing("2026-10-06T09:00:00+09:00"), tmp_path)
    assert (tmp_path / "2026-10-06.json").read_bytes() == previous


def test_corrupt_archive_and_out_of_order_input_are_not_overwritten(tmp_path):
    timeline.record_briefing(briefing(), tmp_path)
    before = (tmp_path / "2026-10-06.json").read_bytes()
    with pytest.raises(ValueError, match="out-of-order"):
        timeline.record_briefing(briefing("2026-10-06T07:00:00+09:00"), tmp_path)
    assert (tmp_path / "2026-10-06.json").read_bytes() == before
    (tmp_path / "2026-10-06.json").write_text("invalid json")
    with pytest.raises(ValueError):
        timeline.record_briefing(briefing(), tmp_path)
    assert (tmp_path / "2026-10-06.json").read_text() == "invalid json"


def test_utc_observation_is_bucketed_by_kst_not_utc(tmp_path):
    archive = timeline.record_briefing(briefing("2026-10-05T23:00:00+00:00"), tmp_path)
    assert archive["date"] == "2026-10-06"
    assert archive["snapshots"][0]["phase"] == "pre"
    invalid = briefing()
    invalid["date"] = "2026-10-05"
    with pytest.raises(ValueError, match="KST"):
        timeline.record_briefing(invalid, tmp_path)


def test_builder_hook_produces_compatibility_and_public_archive(tmp_path, monkeypatch):
    from api.builders import daily_briefing_builder as builder
    monkeypatch.setattr(timeline, "ARCHIVE_DIR", tmp_path / "days")
    monkeypatch.setattr(builder, "OUT_PATH", str(tmp_path / "latest.json"))
    monkeypatch.setattr(builder, "HIST_PATH", str(tmp_path / "history.jsonl"))
    monkeypatch.setattr(builder, "_names", lambda: {})
    monkeypatch.setattr(builder, "_load", lambda *args: {})
    for name in ("_sec_market_recap", "_sec_us_filings", "_sec_earnings", "_sec_disclosures", "_sec_insider", "_sec_flow"):
        monkeypatch.setattr(builder, name, lambda *args: {"title": "확인", "items": [{"text": "공개 사실"}]})
    assert builder.main() == 0
    latest = read(tmp_path, "latest.json")
    index = read(tmp_path / "days", "index.json")
    assert index["days"][0]["date"] == latest["date"]
    assert len(latest["sections"]) == 6
    assert read(tmp_path / "days", latest["date"] + ".json")["snapshots"][0]["items"]
    assert builder._session(datetime.fromisoformat("2026-10-05T12:00:00+09:00")) == "휴장"


def test_legacy_public_sections_and_recap_keep_received_numbers(tmp_path):
    out = briefing("2026-10-04T14:15:54+09:00")
    out["sections"] = [{"title": "직전 거래일 시장", "as_of": "20261001",
        "recap": {"kospi": 1.95, "kosdaq": 4.48, "kospi_close": 6971.35, "kosdaq_close": 894.29},
        "items": [{"name": "지수", "text": "코스피 +1.95% · 코스닥 +4.48%"}]}]
    original = deepcopy(out)
    archive = timeline.record_briefing(out, tmp_path)
    row = archive["snapshots"][0]["items"][0]
    assert row["category"] == "market_recap"
    assert row["as_of"] == "2026-10-01"
    assert row["values"] == {"kospi_pct": 1.95, "kosdaq_pct": 4.48, "kospi_close": 6971.35, "kosdaq_close": 894.29}
    assert out == original
    assert archive["snapshots"][0]["sections"][0]["items"] == original["sections"][0]["items"]
    assert archive["date"] == original["date"] and archive["snapshots"][0]["generated_at"] == original["generated_at"]


def test_earnings_expected_date_never_replaces_observation_date():
    for row_as_of, section_as_of, expected_as_of in (
        ("", "", ""), ("", "2026-10-02", "2026-10-02"),
        ("2026-10-03", "2026-10-02", "2026-10-03"),
    ):
        source = {"sections": [{"id": "earnings", "title": "이번 주 실적 공시 예상",
            "as_of": section_as_of, "items": [{"ticker": "005930", "name": "테스트",
                "date": "2026-10-08", "as_of": row_as_of}]}]}
        original = deepcopy(source)
        sections, items = timeline.public_snapshot(source)
        assert items[0]["event_date"] == "2026-10-08"
        assert items[0]["date_kind"] == "expected"
        assert items[0]["as_of"] == expected_as_of
        assert sections[0]["items"][0]["date"] == "2026-10-08"
        assert source == original

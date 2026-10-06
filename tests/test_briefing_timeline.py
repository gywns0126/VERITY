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


def mixed_briefing(at="2026-10-07T00:30:00+09:00"):
    out = briefing(at)
    out["sections"] += [
        {"id": "market_recap", "title": "직전 거래일 시장", "as_of": "20261002",
         "note": "KR_ONLY_NOTE", "recap": {"kospi": 0.46, "headline": "KR_ONLY_HEADLINE"},
         "items": [{"name": "지수", "country": "KR", "text": "KR_ONLY_INDEX"},
                   {"name": "흐름", "text": "KR_ONLY_FLOW"},
                   {"name": "미국 지수", "country": "US", "text": "US index observation",
                    "values": {"sp500_close": 100, "sp500_pct": 1, "kospi_pct": 99},
                    "index_meta": {"sp500": {"source": "fred", "as_of": "2026-10-06T23:02:00+09:00",
                                              "private": "PRIVATE_SENTINEL"}}}]},
        {"id": "us_filings", "title": "미국 공시", "as_of": "2026-10-06",
         "items": [{"ticker": "AAPL", "text": "US filing"},
                   {"ticker": "005930", "text": "KR_ONLY_FILING"}]},
        {"id": "earnings", "title": "예상 실적", "items": [
            {"ticker": "MSFT", "date": "2026-10-08"},
            {"ticker": "UNKNOWN", "text": "UNKNOWN_TICKER"},
            {"ticker": "AAPL", "country": "KR", "text": "KR_ONLY_TAG"},
            {"ticker": "005930", "date": "2026-10-08"}]},
    ]
    return out


@pytest.mark.parametrize("day", "2026-01-01 2026-01-19 2026-02-16 2026-04-03 2026-05-25 2026-06-19 2026-07-03 2026-09-07 2026-11-26 2026-12-25".split())
def test_us_verified_holidays_and_contract_leave_kr_calendar_unchanged(day):
    kr = deepcopy(timeline.calendar_contract())
    result = timeline.trading_day(date.fromisoformat(day), "US")
    assert (result["status"], result["reason"]) == ("closed", "holiday")
    us = timeline.calendar_contract("US")
    assert us["timezone"] == "America/New_York"
    assert (us["valid_from"], us["valid_until"]) == ("2026-01-01", "2026-12-31")
    assert (us["open_minute"], us["close_minute"]) == (570, 960)
    assert us["early_closes"] == {"2026-11-27": 780, "2026-12-24": 780}
    assert us["verified_at"] == "2026-10-06"
    assert us["source_urls"] == [timeline.US_CALENDAR_SOURCE, timeline.US_HOLIDAY_SOURCE]
    assert timeline.calendar_contract() == kr
    assert "timezone" not in kr and "early_closes" not in kr


@pytest.mark.parametrize("at,phase", [
    ("2026-03-06T14:29:00+00:00", "pre"), ("2026-03-06T14:30:00+00:00", "open"),
    ("2026-03-09T13:29:00+00:00", "pre"), ("2026-03-09T13:30:00+00:00", "open"),
    ("2026-10-30T19:59:00+00:00", "open"), ("2026-10-30T20:00:00+00:00", "post"),
    ("2026-11-02T14:29:00+00:00", "pre"), ("2026-11-02T14:30:00+00:00", "open"),
    ("2026-11-02T20:59:00+00:00", "open"), ("2026-11-02T21:00:00+00:00", "post"),
])
def test_us_session_uses_new_york_dst(at, phase):
    now = datetime.fromisoformat(at)
    calendar = timeline.trading_day(now.astimezone(timeline.US_TZ).date(), "US")
    assert timeline.session_phase(now, calendar) == phase


@pytest.mark.parametrize("day", ["2026-11-27", "2026-12-24"])
def test_us_early_close_ends_core_session_at_1300(day):
    calendar = timeline.trading_day(date.fromisoformat(day), "US")
    assert calendar["status"] == "open" and calendar["close_minute"] == 780
    assert timeline.session_phase(datetime.fromisoformat(day + "T12:59:00-05:00"), calendar) == "open"
    assert timeline.session_phase(datetime.fromisoformat(day + "T13:00:00-05:00"), calendar) == "post"


@pytest.mark.parametrize("day,status,reason", [
    ("2025-12-31", "unknown", "outside_verified_range"),
    ("2027-01-01", "unknown", "outside_verified_range"),
    ("2026-10-10", "closed", "weekend"),
])
def test_us_weekend_and_unknown_range_have_no_false_open_phase(day, status, reason):
    calendar = timeline.trading_day(date.fromisoformat(day), "US")
    assert (calendar["status"], calendar["reason"]) == (status, reason)
    assert timeline.session_phase(datetime.fromisoformat(day + "T12:00:00-05:00"), calendar) == status


def test_us_archive_filters_kr_facts_and_preserves_unknown_source_date(tmp_path):
    out = mixed_briefing()
    original = deepcopy(out)
    kr = timeline.record_briefing(out, tmp_path)
    kr_bytes = (tmp_path / "2026-10-07.json").read_bytes()
    kr_calendar = read(tmp_path, "index.json")["calendar"]
    us = timeline.record_us_briefing(out, tmp_path, us_tickers={"MSFT"})
    snapshot = us["snapshots"][0]
    assert us["date"] == "2026-10-06" and us["timezone"] == "America/New_York"
    assert snapshot["generated_at"] == "2026-10-06T11:30:00-04:00"
    assert snapshot["phase"] == "open" and kr["snapshots"][0]["phase"] == "pre"
    assert len(snapshot["items"]) == 3
    assert all(item["country"] == "US" for item in snapshot["items"])
    recap = snapshot["items"][0]
    assert recap["as_of"] == "" and snapshot["source_meta"]["recap_as_of"] == ""
    assert recap["values"] == {"sp500_close": 100, "sp500_pct": 1}
    assert recap["index_meta"]["sp500"] == {"source": "fred", "as_of": "2026-10-06T23:02:00+09:00",
                                               "collected_at": "2026-10-06T23:02:00+09:00"}
    assert snapshot["items"][2]["event_date"] == "2026-10-08"
    assert snapshot["items"][2]["as_of"] == ""
    public_text = json.dumps(us)
    assert "KR_ONLY" not in public_text and "PRIVATE_SENTINEL" not in public_text
    assert "UNKNOWN_TICKER" not in public_text and "estimated_net_krw" not in public_text
    assert "recap" not in snapshot["sections"][0] and "as_of" not in snapshot["sections"][0]
    assert (tmp_path / "2026-10-07.json").read_bytes() == kr_bytes
    assert read(tmp_path, "index.json")["calendar"] == kr_calendar
    assert out == original
    us_bytes = (tmp_path / "us" / "2026-10-06.json").read_bytes()
    timeline.record_us_briefing(out, tmp_path, us_tickers={"MSFT"})
    assert (tmp_path / "us" / "2026-10-06.json").read_bytes() == us_bytes


def test_us_sealing_uses_ny_midnight_and_never_backfills_kr_days(tmp_path):
    timeline.record_briefing(briefing("2026-10-04T12:00:00+09:00"), tmp_path)
    out = mixed_briefing("2026-10-07T00:30:00+09:00")
    first = timeline.record_us_briefing(out, tmp_path)
    snapshots = deepcopy(first["snapshots"])
    later = mixed_briefing("2026-10-09T01:00:00+09:00")
    timeline.record_us_briefing(later, tmp_path)
    sealed = read(tmp_path / "us", "2026-10-06.json")
    assert sealed["snapshots"] == snapshots
    assert sealed["day_summary"]["status"] == "closed"
    assert sealed["day_summary"]["cutoff_at"] == "2026-10-07T00:00:00-04:00"
    assert {entry["date"] for entry in read(tmp_path / "us", "index.json")["days"]} == {"2026-10-06", "2026-10-08"}
    with pytest.raises(ValueError, match="sealed"):
        timeline.record_us_briefing(mixed_briefing("2026-10-07T01:00:00+09:00"), tmp_path)


def test_us_fall_back_chronology_compares_instants_and_seals_with_next_offset(tmp_path):
    for at in ("2026-11-01T01:50:00-04:00", "2026-11-01T01:10:00-05:00"):
        archive = timeline.record_us_briefing(mixed_briefing(at), tmp_path)
    assert len(archive["snapshots"]) == 2
    assert read(tmp_path / "us", "index.json")["generated_at"] == "2026-11-01T01:10:00-05:00"
    with pytest.raises(ValueError, match="out-of-order"):
        timeline.record_us_briefing(mixed_briefing("2026-11-01T01:20:00-04:00"), tmp_path)
    timeline.record_us_briefing(mixed_briefing("2026-11-02T10:00:00-05:00"), tmp_path)
    assert read(tmp_path / "us", "2026-11-01.json")["day_summary"]["cutoff_at"] == "2026-11-02T00:00:00-05:00"


def test_us_unknown_and_holiday_snapshots_do_not_create_intraday_cards(tmp_path):
    closed = timeline.record_us_briefing(mixed_briefing("2026-11-26T12:00:00-05:00"), tmp_path)
    assert closed["cards"]["closed"] and not any(closed["cards"][p] for p in ("pre", "open", "post"))
    unknown = timeline.record_us_briefing(mixed_briefing("2027-01-04T12:00:00-05:00"), tmp_path)
    assert unknown["snapshots"][0]["phase"] == "unknown" and not any(unknown["cards"].values())


def test_publish_staging_only_allows_known_kr_us_archive_json(tmp_path):
    import subprocess
    action = (Path(__file__).resolve().parents[1] / ".github/actions/publish-data/action.yml").read_text()
    block = action.split("        # ── briefing_days/", 1)[1].split("        # ── metadata/", 1)[0]
    command = "\n".join(line[8:] for line in block.splitlines()[1:])
    fake_git = r'''
git() {
  if [[ "$1" == "ls-tree" ]]; then
    printf '%s\n' index.json 2026-10-06.json private.json notes.txt us nested 2026-10-07.json.bak
  else
    printf '{"public":true}\n'
  fi
}
'''
    subprocess.run(["bash", "-c", "set -e\n" + fake_git + command], cwd=tmp_path, check=True)
    emitted = {path.relative_to(tmp_path / "_public_dist").as_posix()
               for path in (tmp_path / "_public_dist").rglob("*.json")}
    assert emitted == {"briefing_days/index.json", "briefing_days/2026-10-06.json",
                       "briefing_days/us/index.json", "briefing_days/us/2026-10-06.json"}

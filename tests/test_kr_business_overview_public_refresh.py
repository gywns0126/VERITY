"""Offline raw -> public -> member-map contract checks.

Workflow seven-axis review (2026-10-11):
1. New step has no endpoint/secret; existing DART and Blob credentials unchanged.
2. No push trigger added; only data/ is staged; Vercel ignoreCommand unchanged.
3. Existing verity-kr-company-facts group/cancel=false and 90-minute cap unchanged.
   That group occurs in one workflow; live average duration remains unverified.
4. Existing daily 21:15 UTC cron/dispatch inputs unchanged; no new schedule.
5. No KIS import, token request, or KIS state file in the new path.
6. Reuses existing python-dotenv dependency through the sentence cutter; no install.
7. Manual + scheduled runtime acceptance is tracked separately from these offline tests.

Pre-edit workflow read: 274/274 lines, 15,600 bytes, last commit 9175437492;
SHA256 ecbbfb57273acfd14c7c9ee7ce2f32f22e8c5d90b8b553d71b685148847fb91b.
Its pre-existing catalog/capture/publish diff belongs to the parent and is retained.
Trace: backfill overview -> dart_business_overview.json -> this CLI -> public file
-> enrich-public-relations.read_sources / project_public_business_overviews.
This refresh does not re-fetch filings or publish the public Blob itself.
"""
import importlib.util
import json
from pathlib import Path
import socket

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "overview_refresh", ROOT / "scripts/refresh_kr_business_overview_public.py")
refresh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh)


def source(**changes):
    return {"name": "시험회사", "text": "당사는 시험용 장비를 공급합니다.",
            "bsns_year": "2025", "rcept_dt": "20260319", "rcept_no": "20260319001329",
            "report_nm": "사업보고서 (2025.12)", "truncated": False, **changes}


@pytest.fixture(autouse=True)
def prohibit_side_effects(monkeypatch):
    from api.builders import stock_report_public_builder as builder

    def forbidden(*args, **kwargs):
        raise AssertionError("network, full report builder and relation worker forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(builder, "main", forbidden)
    monkeypatch.setattr(builder, "_run_optional_public_relation_worker", forbidden, raising=False)
    if hasattr(builder, "subprocess"):
        monkeypatch.setattr(builder.subprocess, "run", forbidden)


@pytest.fixture
def overview_dir(tmp_path):
    directory = tmp_path / "overview-refresh"
    directory.mkdir()
    return directory


def setup_data(tmp_path, raw=None):
    old, _ = refresh.build_public({"rows": {"000001": source()}}, {"rows": {}}, {})
    values = {"dart_business_overview.json": {"rows": raw if raw is not None else {
                  "000001": source(text="새 공시의 시험용 장비 설명입니다.", rcept_dt="20260401",
                                   rcept_no="20260401000001")}},
              refresh.PUBLIC_FILE: old, "kr_listed.json": {"000001": {"name": "시험회사"}},
              "stock_report_public.json": {"untouched": True}, "chain_snippets.json": {}}
    for name, value in values.items():
        (tmp_path / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_refresh_only_public_file_dates_and_consumer(overview_dir):
    from api.intelligence.portfolio_public_sources import project_public_business_overviews
    before = setup_data(overview_dir)
    assert refresh.main(["--data-dir", str(overview_dir)]) == 0
    after = {p.name: p.read_bytes() for p in overview_dir.iterdir()}
    assert {name for name in before if before[name] != after[name]} == {refresh.PUBLIC_FILE}
    assert set(before) == set(after)
    public = json.loads(after[refresh.PUBLIC_FILE])
    row = public["rows"]["000001"]
    assert row["filed_at"] == "20260401" and row["fiscal_year"] == "2025"
    assert row["url"].endswith("20260401000001")
    projected = project_public_business_overviews({refresh.PUBLIC_FILE: public})
    assert projected["coverage"]["accepted"] == 1
    assert projected["rows"][0]["source"]["as_of"] == "2026-04-01"
    assert refresh.refresh(overview_dir)["written"] is False
    assert (overview_dir / refresh.PUBLIC_FILE).read_bytes() == after[refresh.PUBLIC_FILE]


@pytest.mark.parametrize("bad", ["missing", "broken", "empty", "blank", "date", "receipt"])
def test_bad_input_preserves_previous_bytes(overview_dir, bad):
    before = setup_data(overview_dir)
    path = overview_dir / "dart_business_overview.json"
    if bad == "missing":
        path.unlink()
    elif bad == "broken":
        path.write_text("{", encoding="utf-8")
    else:
        rows = {} if bad == "empty" else {"000001": source(**{
            "blank": {"text": "  "}, "date": {"rcept_dt": "20260230"},
            "receipt": {"rcept_no": None}}[bad])}
        path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    assert refresh.main(["--data-dir", str(overview_dir)]) == 1
    assert (overview_dir / refresh.PUBLIC_FILE).read_bytes() == before[refresh.PUBLIC_FILE]


def test_partial_and_older_sources_preserve_prior_rows():
    prior, _ = refresh.build_public({"rows": {"000001": source(), "000002": source(),
        "000003": source()}}, {"rows": {}}, {})
    public, summary = refresh.build_public({"rows": {
        "000001": source(text=""), "000002": source(rcept_dt="20250319", bsns_year="2024"),
        "000004": source(rcept_dt="20260402")}}, prior, {})
    for ticker in ("000001", "000002", "000003"):
        assert public["rows"][ticker] == prior["rows"][ticker]
    assert public["rows"]["000004"]["filed_at"] == "20260402"
    assert summary["public"] == 4 and summary["older_preserved"] == 1


@pytest.mark.parametrize("changes", [
    {"text": "당사는\t장비를 공급합니다."},
    {"text": "<b>당사는 장비를 공급합니다.</b>"},
    {"name": "가" * 161},
], ids=["tab-text", "html-text", "overlong-name"])
def test_consumer_rejection_preserves_valid_prior_bytes(overview_dir, changes):
    from api.intelligence.portfolio_public_sources import project_public_business_overviews

    setup_data(overview_dir, {"000001": source(
        rcept_dt="20260401", rcept_no="20260401000001", **changes)})
    # Exercise the raw-name fallback instead of masking it with a valid catalog name.
    (overview_dir / "kr_listed.json").write_text("{}", encoding="utf-8")
    before = {p.name: p.read_bytes() for p in overview_dir.iterdir()}
    summary = refresh.refresh(overview_dir)
    assert summary["consumer_rejected"] == 1
    assert summary["changed"] is False and summary["written"] is False
    assert {p.name: p.read_bytes() for p in overview_dir.iterdir()} == before
    public = json.loads((overview_dir / refresh.PUBLIC_FILE).read_text())
    projected = project_public_business_overviews({refresh.PUBLIC_FILE: public})
    assert projected["coverage"]["accepted"] == 1
    assert projected["coverage"]["rejected"] == 0
    assert projected["rows"][0]["source"]["as_of"] == "2026-03-19"


def test_invalid_new_rows_skipped_while_valid_new_row_is_written(overview_dir):
    from api.intelligence.portfolio_public_sources import project_public_business_overviews

    before = setup_data(overview_dir, {
        "000002": source(text="당사는\t장비를 공급합니다."),
        "000003": source(text="<b>당사는 장비를 공급합니다.</b>"),
        "000004": source(name="가" * 161),
        "000005": source(rcept_dt="20260401", rcept_no="20260401000001"),
    })
    summary = refresh.refresh(overview_dir)
    assert summary["consumer_rejected"] == 3 and summary["public"] == 2
    assert summary["changed"] is True and summary["written"] is True
    public = json.loads((overview_dir / refresh.PUBLIC_FILE).read_text())
    assert set(public["rows"]) == {"000001", "000005"}
    assert public["rows"]["000001"] == json.loads(before[refresh.PUBLIC_FILE])["rows"]["000001"]
    assert public["rows"]["000005"]["filed_at"] == "20260401"
    projected = project_public_business_overviews({refresh.PUBLIC_FILE: public})
    assert projected["coverage"]["accepted"] == 2
    assert projected["coverage"]["rejected"] == 0
    assert {p.name for p in overview_dir.iterdir()} == set(before)
    for name, content in before.items():
        if name != refresh.PUBLIC_FILE:
            assert (overview_dir / name).read_bytes() == content


@pytest.mark.parametrize("text", ["가" * 900, "공급합니다. " * 100])
def test_existing_cutter_reused_and_ellipsis_fits_consumer(text, monkeypatch):
    calls = []
    cutter = refresh._cut_at_sentence

    def cut(value, limit):
        calls.append((value, limit))
        return cutter(value, limit)

    monkeypatch.setattr(refresh, "_cut_at_sentence", cut)
    public, _ = refresh.build_public({"rows": {"000001": source(text=text)}}, {"rows": {}}, {})
    row = public["rows"]["000001"]
    assert calls == [(text, refresh.BIZ_OVERVIEW_PUBLISH_CHARS)]
    assert row["chars"] == len(row["text"]) <= 600 and row["truncated"] is True


def test_check_mode_and_failed_replace_do_not_change_output(overview_dir, monkeypatch):
    before = setup_data(overview_dir)
    assert refresh.main(["--data-dir", str(overview_dir), "--check"]) == 0
    assert {p.name: p.read_bytes() for p in overview_dir.iterdir()} == before

    def fail(*args):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(refresh.os, "replace", fail)
    assert refresh.main(["--data-dir", str(overview_dir)]) == 1
    assert {p.name: p.read_bytes() for p in overview_dir.iterdir()} == before


def test_workflow_refresh_precedes_consumers_and_stages_exact_file():
    workflow = (ROOT / ".github/workflows/kr_company_facts_backfill.yml").read_text()
    refresh_index = workflow.index("run: python scripts/refresh_kr_business_overview_public.py")
    assert workflow.index("python scripts/kr_company_facts_backfill.py") < refresh_index
    assert workflow.index("build-public-source-filter.cjs") > refresh_index
    assert "data/kr_business_overview_public.json \\\n" in workflow
    assert 'git add "$f"' in workflow
    assert "group: verity-kr-company-facts\n  cancel-in-progress: false" in workflow

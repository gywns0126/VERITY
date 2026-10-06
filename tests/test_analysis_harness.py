"""Offline contract tests. Synthetic facts; never touch the real private journal."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest

from api.intelligence import analysis_harness as h
from api.intelligence import decision_journal as dj
from api.intelligence import operator_context as ctx

NOW = datetime(2026, 10, 5, 10, tzinfo=timezone.utc)


def facts():
    return dict(ticker="005930", name="TEST", missing=["test missing source"],
                _meta={"collected_at": (NOW - timedelta(minutes=1)).isoformat()},
                sections=[dict(label="종가", source="kr_close_latest.json", as_of="2026-10-02",
                               data={"close": 100}),
                          dict(label="재무", source="test_fundamentals", as_of="2026-06-30",
                               data={"revenue": 1000})])


def packet():
    return h.build_packet(facts(), "test question", now=NOW)


def reviewed(p):
    result = h.review_template(p)
    result.update(reviewer="test-reviewer", reviewed_at=(NOW + timedelta(minutes=1)).isoformat(),
        valid_until=(NOW + timedelta(days=1)).isoformat(), identity_verified=True,
        verdict="관심", confidence="medium", basis_axes=["s2"], reasoning_brief="test conclusion",
        counterevidence="test counterevidence", change_conditions=["revenue declines"],
        limitations="Sources outside the bundle have not been reviewed.",
        acknowledged_gaps=h.gap_ids(p),
        section_reviews=[dict(id="s1", status="not_used", reason="not a valuation conclusion", freshness="historical"),
                         dict(id="s2", status="reviewed", reason="source checked", freshness="sufficient")],
        evidence=[dict(section_id="s2", claim="reported revenue", value="1000", source_kind="primary",
                       url="https://example.com/filing", source_as_of="2026-06-30", excerpt="test excerpt",
                       checked_at=(NOW + timedelta(seconds=30)).isoformat(), status="confirmed")])
    return result


def test_packet_is_immutable_and_gap_coverage_is_honest():
    original = facts()
    p = h.build_packet(original, now=NOW)
    original["sections"][0]["data"]["close"] = 999
    assert p["facts"]["sections"][0]["data"]["close"] == 100
    assert p["sources"]["total"] == sum(p["sources"]["counts"].values())
    assert p["sources"]["counts"]["not_in_bundle"] > 0
    assert h.verify_packet(p) == p


@pytest.mark.parametrize("field", ["missing", "_meta", "sections"])
def test_mutating_any_facts_field_rejected(field):
    p = packet()
    p["facts"][field] = []
    with pytest.raises(ValueError, match="digest"):
        h.verify_packet(p)


def test_packet_filename_binding(tmp_path):
    p = packet()
    other = h.build_packet(facts(), "different question", now=NOW)
    path = h.save_packet(p, tmp_path)
    ctx.atomic_json(path, other)
    with pytest.raises(ValueError, match="filename"):
        h.load_packet(p["packet_id"], tmp_path)


def test_prepare_no_live_calls_when_importing_facts(tmp_path, monkeypatch):
    from api.intelligence import operator_ask
    monkeypatch.setattr(operator_ask, "ask", lambda *a: pytest.fail("unexpected live call"))
    p = packet()
    h.save_packet(p, tmp_path)
    assert h.status(p["packet_id"], runtime=tmp_path, journal_path=tmp_path / "journal")["state"] == "awaiting_review"


def test_live_prepare_reuses_existing_reader_once(tmp_path, monkeypatch):
    from api.intelligence import operator_ask
    calls = []
    def ask(query, question):
        calls.append((query, question))
        return {"facts": facts()}
    monkeypatch.setattr(operator_ask, "ask", ask)
    p = h.prepare("005930", "why", runtime=tmp_path)
    assert calls == [("005930", "why")]
    assert h.load_packet(p["packet_id"], tmp_path) == p


def test_complete_review_and_journal_roundtrip(tmp_path):
    p = packet()
    r = reviewed(p)
    h.save_packet(p, tmp_path)
    target = tmp_path / "journal.jsonl"
    rec = h.finalize(p["packet_id"], r, runtime=tmp_path, journal_path=target, now=NOW + timedelta(hours=1))
    again = h.finalize(p["packet_id"], r, runtime=tmp_path, journal_path=target, now=NOW + timedelta(days=2))
    assert rec == again
    assert len(target.read_text().splitlines()) == 1
    assert dj.read_recent("005930", path=target)[0] == rec
    assert rec["facts_at"] == p["facts_at"]
    assert rec["review"]["coverage"]["section_total"] == 2
    assert h.status(p["packet_id"], runtime=tmp_path, journal_path=target, now=NOW + timedelta(hours=1))["state"] == "reviewed"
    status = h.status(p["packet_id"], runtime=tmp_path, journal_path=target, now=NOW + timedelta(days=2))
    assert status["state"] == "review_expired"
    assert status["monitoring_active"] is False
    assert status["orders_authorized"] is False
    assert target.stat().st_mode & 0o777 == 0o600


def test_conflicting_review_cannot_overwrite(tmp_path):
    p, target = packet(), tmp_path / "journal.jsonl"
    r = reviewed(p)
    h.save_packet(p, tmp_path)
    h.finalize(p["packet_id"], r, runtime=tmp_path, journal_path=target, now=NOW + timedelta(hours=1))
    r["reasoning_brief"] = "changed"
    with pytest.raises(dj.JournalError, match="conflict"):
        h.finalize(p["packet_id"], r, runtime=tmp_path, journal_path=target, now=NOW + timedelta(hours=1))
    assert len(target.read_text().splitlines()) == 1


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(identity_verified=False),
    lambda r: r.update(ticker="OTHER"),
    lambda r: r.update(packet_id="0" * 64),
    lambda r: r.update(acknowledged_gaps=[]),
    lambda r: r.update(section_reviews=r["section_reviews"][:1]),
    lambda r: r["section_reviews"][0].update(id="s2"),
    lambda r: r["section_reviews"][1].update(status="pending"),
    lambda r: r["section_reviews"][1].update(reason=""),
    lambda r: r.update(basis_axes=["s1"]),
    lambda r: r.update(change_conditions=[]),
    lambda r: r.update(counterevidence=""),
    lambda r: r.update(reviewed_at="2026-10-05T10:01:00"),
    lambda r: r.update(valid_until=NOW.isoformat()),
    lambda r: r["evidence"][0].update(url="file:///tmp/test"),
    lambda r: r["evidence"][0].update(url="https://user:secret@example.com"),
    lambda r: r["evidence"][0].update(source_kind="model"),
    lambda r: r["evidence"][0].update(source_as_of="2027-01-01"),
    lambda r: r["evidence"][0].update(checked_at=(NOW - timedelta(hours=1)).isoformat()),
])
def test_invalid_review_does_not_write(tmp_path, mutation):
    p, target = packet(), tmp_path / "journal.jsonl"
    r = reviewed(p)
    mutation(r)
    h.save_packet(p, tmp_path)
    with pytest.raises(ValueError):
        h.finalize(p["packet_id"], r, runtime=tmp_path, journal_path=target, now=NOW + timedelta(hours=1))
    assert not target.exists()


@pytest.mark.parametrize("kind", ["unresolved", "stale", "unknown", "no_evidence", "refuted"])
def test_uncertainty_is_hold_only(kind):
    p = packet()
    r = reviewed(p)
    if kind == "unresolved":
        r["unresolved"] = ["unconfirmed capital change"]
    elif kind in ("stale", "unknown"):
        r["section_reviews"][1]["freshness"] = kind
    elif kind == "no_evidence":
        r["evidence"] = []
    else:
        r["evidence"][0]["status"] = kind
    with pytest.raises(ValueError, match="hold"):
        h.validate_review(p, r, now=NOW + timedelta(hours=1))
    r.update(verdict="보류", confidence="low")
    assert h.validate_review(p, r, now=NOW + timedelta(hours=1))["unresolved"] is True


def test_expired_new_review_not_saved(tmp_path):
    p, target = packet(), tmp_path / "journal"
    h.save_packet(p, tmp_path)
    with pytest.raises(ValueError, match="expired"):
        h.finalize(p["packet_id"], reviewed(p), runtime=tmp_path, journal_path=target, now=NOW + timedelta(days=2))
    assert not target.exists()


@pytest.mark.parametrize("data", [
    {"financials": {"period": "2025"}},
    [{"financials": {"period": "2025"}}],
    {"fin": {"period": "2025"}},
])
@pytest.mark.parametrize("verdict", ["관심", "회피"])
def test_known_financial_basis_requires_matching_reporting_period(data, verdict):
    source = facts()
    source["sections"][1]["data"] = data
    p = h.build_packet(source, now=NOW)
    r = reviewed(p)
    r["verdict"] = verdict
    assert h.review_template(p)["financial_reporting_periods"] == {"s2": "2025"}
    for reporting_period in (None, "2026"):
        if reporting_period is None:
            r["evidence"][0].pop("reporting_period", None)
        else:
            r["evidence"][0]["reporting_period"] = reporting_period
        with pytest.raises(ValueError, match="hold"):
            h.validate_review(p, r, now=NOW + timedelta(hours=1))
    r["evidence"][0]["reporting_period"] = "2025"
    coverage = h.validate_review(p, r, now=NOW + timedelta(hours=1))
    assert coverage["unresolved"] is False
    assert coverage["verification"] == "reviewer_attestation_not_machine_proof"
    r["evidence"][0]["reporting_period"] = "2026"
    r.update(verdict="보류", confidence="low")
    assert h.validate_review(p, r, now=NOW + timedelta(hours=1))["unresolved"] is True


def test_legacy_financial_hold_remains_readable():
    source = facts()
    source["sections"][1]["data"] = {"fin": {"period": "2025"}}
    p = h.build_packet(source, now=NOW)
    r = reviewed(p)
    r.update(verdict="보류", confidence="low")
    assert "reporting_period" not in r["evidence"][0]
    assert h.validate_review(p, r, now=NOW + timedelta(hours=1))["primary_supported_basis"] == 1


def test_unused_financial_and_nonfinancial_periods_do_not_block_review():
    source = facts()
    source["sections"][0]["data"] = {"fin": {"period": "2025"}}
    source["sections"][1]["data"] = {"period": "2025-06-30", "year": 2025}
    p = h.build_packet(source, now=NOW)
    r = reviewed(p)
    r["section_reviews"][0]["freshness"] = "stale"
    assert h.validate_review(p, r, now=NOW + timedelta(hours=1))["unresolved"] is False


def test_compare_flags_changes_not_verdict():
    p = packet()
    updated = facts()
    updated["sections"][1]["data"]["revenue"] = 500
    updated["missing"] = []
    result = h.compare(p, h.build_packet(updated, now=NOW))
    assert result["changed_sources"] == ["test_fundamentals"]
    assert result["missing_changed"] is True
    assert "verdict" not in result


def test_cli_offline_roundtrip(tmp_path):
    now = datetime.now(timezone.utc)
    source = facts()
    source["_meta"]["collected_at"] = (now - timedelta(minutes=1)).isoformat()
    source_path = tmp_path / "facts.json"
    source_path.write_text(json.dumps(source))
    base = [sys.executable, str(h.ROOT / "scripts/analysis_harness.py"),
            "--runtime", str(tmp_path / "runtime"), "--journal", str(tmp_path / "journal")]
    def run(*args):
        result = subprocess.run(base + list(args), capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    result = run("prepare", "--facts-file", str(source_path))
    packet_id = result["packet_id"]
    assert run("status", "--packet", packet_id)["state"] == "awaiting_review"
    review_path = tmp_path / "review.json"
    run("template", "--packet", packet_id, "--output", str(review_path))
    p = run("inspect", "--packet", packet_id, "--full")
    r = reviewed(p)
    r.update(reviewed_at=datetime.now(timezone.utc).isoformat(), valid_until=(now + timedelta(days=1)).isoformat())
    r["evidence"][0]["checked_at"] = p["prepared_at"]
    review_path.write_text(json.dumps(r))
    assert run("validate", "--review", str(review_path))["section_total"] == 2
    assert run("finalize", "--review", str(review_path))["state"] == "recorded"
    assert run("status", "--packet", packet_id)["state"] == "reviewed"
    assert run("finalize", "--review", str(review_path))["state"] == "recorded"
    assert len((tmp_path / "journal").read_text().splitlines()) == 1
    overwrite = subprocess.run(base + ["template", "--packet", packet_id, "--output", str(review_path)], capture_output=True)
    assert overwrite.returncode == 2

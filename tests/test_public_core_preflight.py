"""Local public-write preflight: no credentials, network, or Blob SDK required."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

from scripts.publish_verify import GUARD, _finite_multiple

ROOT = Path(__file__).resolve().parents[1]
UPLOADER = ROOT / ".github/actions/publish-data/blob_upload.js"


def reports(folder):
    for name, cfg in GUARD.items():
        rows = [{"ticker": f"{i:06}", "facts": {"PER": "-1.5", "PBR": 0}}
                for i in range(cfg["min_n"])]
        (folder / name).write_text(json.dumps({"stocks": rows}))
    # An empty event feed is legitimate and outside the three core universes.
    (folder / "urgent_alerts.json").write_text("[]")


def run(folder):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the existing uploader")
    # Invalid tokens cannot be used by local-only preflight.
    return subprocess.run([node, str(UPLOADER), "--verify-core", str(folder)],
                          env={**os.environ, "BLOB_READ_WRITE_TOKEN": "not-a-real-token"},
                          capture_output=True, text=True, timeout=10)


def test_valid_core_reports_and_zero_optional_feed_pass(tmp_path):
    reports(tmp_path)
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "3/3 core reports passed" in result.stdout


@pytest.mark.parametrize("name", list(GUARD))
@pytest.mark.parametrize("n", [0, 1])
def test_core_universe_collapse_fails_before_public_write(tmp_path, name, n):
    reports(tmp_path)
    (tmp_path / name).write_text(json.dumps({"stocks": [
        {"ticker": "005930", "facts": {"PER": 10, "PBR": 1}} for _ in range(n)]}))
    result = run(tmp_path)
    assert result.returncode == 1
    assert name in result.stderr and "종목수 부족" in result.stderr


@pytest.mark.parametrize("name", list(GUARD))
def test_missing_core_report_fails(tmp_path, name):
    reports(tmp_path)
    (tmp_path / name).unlink()
    result = run(tmp_path)
    assert result.returncode == 1
    assert name in result.stderr


@pytest.mark.parametrize("value", ["not a number", "NaN", "Infinity", True, {}, [], "—", ""])
def test_present_but_invalid_multiples_do_not_pass(tmp_path, value):
    reports(tmp_path)
    name = "stock_report_public.json"
    (tmp_path / name).write_text(json.dumps({"stocks": [
        {"ticker": f"{i:06}", "facts": {"PER": value, "PBR": value}} for i in range(100)]}))
    assert run(tmp_path).returncode == 1


@pytest.mark.parametrize("doc", [None, [], {}, {"stocks": [None]}, {"stocks": [3]},
                                 {"stocks": [{"facts": "broken"}]}, {"stocks": [{"facts": []}]}])
def test_malformed_reports_fail_with_named_error(tmp_path, doc):
    reports(tmp_path)
    (tmp_path / "stock_report_public.json").write_text(json.dumps(doc))
    result = run(tmp_path)
    assert result.returncode == 1
    assert "public preflight stock_report_public.json:" in result.stderr
    assert "TypeError" not in result.stderr


def test_same_guard_runs_after_overlays_before_both_public_writes():
    action = yaml.safe_load((ROOT / ".github/actions/publish-data/action.yml").read_text())
    steps = action["runs"]["steps"]
    check = next(i for i, s in enumerate(steps) if "--verify-core" in s.get("run", ""))
    overlay = next(i for i, s in enumerate(steps) if "publish_earnings_calendar.cjs" in s.get("run", ""))
    github = next(i for i, s in enumerate(steps) if s.get("id") == "publish_primary")
    blob = next(i for i, s in enumerate(steps) if s["name"].startswith("Dual-write"))
    assert overlay < check < github < blob
    assert not steps[check].get("continue-on-error")


def test_minimum_universe_matches_delivery_verifier():
    source = UPLOADER.read_text()
    for name, cfg in GUARD.items():
        line = next(s for s in source.splitlines() if f'"{name}":' in s)
        assert f'minN: {cfg["min_n"]}' in line
        assert f'floorPct: {int(cfg["floor"])}' in line


@pytest.mark.parametrize("value,expected", [(0, True), (-1.5, True), ("1e2", True),
    (" -2.0 ", True), ("NaN", False), ("Infinity", False), (True, False),
    ({}, False), ([], False), ("not a number", False), ("1,000", False)])
def test_delivery_numeric_contract(value, expected):
    assert _finite_multiple(value) is expected

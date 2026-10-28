"""Offline bridge from the real Python v4 builder to the JS publish preflight."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/member-map/build-prepared-business-index.py"
UPLOADER = ROOT / ".github/actions/publish-data/blob_upload.js"
ARTIFACT = "portfolio_public_business_index.json"
RECEIPT = "portfolio_public_business_release.json"
_DAY = "2026-10-29T00:00:00Z"


def _write_sources(directory):
    kr = [
        {"ticker": f"{number:06d}", "market": "KR",
         "name": f"합성회사{number:03d}", "name_ko": f"한국별칭{number:03d}"}
        for number in range(1, 101)
    ]
    us = [
        {"ticker": f"SYN{number:03d}", "market": "US",
         "name": f"Synthetic Co {number:03d}", "name_ko": f"미국별칭{number:03d}"}
        for number in range(1, 101)
    ]
    facts = {"PER": "12.5", "PBR": "1.2"}
    sources = {
        "universe_search.json": {"stocks": kr + us},
        "stock_report_public.json": {"stocks": [
            {**row, "facts": facts} for row in kr]},
        "us_stock_report_public.json": {"stocks": [
            {**row, "facts": facts} for row in us]},
        "public_disclosure_feed.json": {"items": []},
        "us_disclosure_feed.json": {"items": []},
        "kr_business_overview_public.json": {
            "_meta": {"count": 0, "generated_at": _DAY}, "rows": {}},
    }
    for name, value in sources.items():
        (directory / name).write_text(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )


def _build(directory):
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--source-dir", str(directory),
         "--output", str(directory / ARTIFACT),
         "--receipt-output", str(directory / RECEIPT)],
        capture_output=True, text=True, timeout=60,
        env={"PATH": os.environ.get("PATH", os.defpath)},
    )
    assert result.returncode == 0, result.stderr
    return result


def _verify(node, directory):
    return subprocess.run(
        [node, str(UPLOADER), "--verify-business", str(directory)],
        capture_output=True, text=True, timeout=15,
        env={"PATH": os.environ.get("PATH", os.defpath)},
    )


def _write_artifact_and_receipt(directory, artifact, receipt):
    payload = json.dumps(
        artifact, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    (directory / ARTIFACT).write_bytes(payload)
    receipt = dict(receipt)
    receipt["artifact_sha256"] = hashlib.sha256(payload).hexdigest()
    (directory / RECEIPT).write_text(
        json.dumps(receipt, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def test_real_v4_builder_artifact_passes_js_preflight_and_mutations_fail(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the offline publish bridge")

    _write_sources(tmp_path)
    built = _build(tmp_path)
    assert json.loads(built.stdout)["sources"] == 6
    artifact_path, receipt_path = tmp_path / ARTIFACT, tmp_path / RECEIPT
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert artifact["matcher_version"] == "business-matchers-2026-10-29-v4"
    assert "news_names" in artifact
    assert artifact["news_names"]["encoding"] == "gzip-base64-v1"
    assert artifact["news_names"]["data"]
    assert len(artifact["catalog"]) >= 100
    accepted = _verify(node, tmp_path)
    assert accepted.returncode == 0, accepted.stderr

    bad_encoding = json.loads(json.dumps(artifact))
    bad_encoding["news_names"]["encoding"] = "gzip-base64-v0"
    _write_artifact_and_receipt(tmp_path, bad_encoding, receipt)
    rejected = _verify(node, tmp_path)
    assert rejected.returncode != 0

    extra_field = json.loads(json.dumps(artifact))
    extra_field["news_names"]["unexpected"] = True
    _write_artifact_and_receipt(tmp_path, extra_field, receipt)
    rejected = _verify(node, tmp_path)
    assert rejected.returncode != 0

    artifact_path.write_bytes(json.dumps(
        artifact, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8"))
    bad_receipt = dict(receipt)
    bad_receipt["artifact_sha256"] = "0" * 64
    receipt_path.write_text(
        json.dumps(bad_receipt, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    rejected = _verify(node, tmp_path)
    assert rejected.returncode != 0

"""Offline publisher CLI boundaries; no production sources or services are used."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "company_snapshot_builder", ROOT / "scripts/member-map/build-company-snapshots.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
NAMES = ("universe_search.json", "stock_report_public.json", "us_stock_report_public.json",
         "public_disclosure_feed.json", "us_disclosure_feed.json", "kr_business_overview_public.json")
DEPS = (4096, 4096, NAMES, dict.fromkeys(NAMES, 4096))


def inputs(tmp_path):
    source, output = tmp_path / "staged", tmp_path / "isolated"
    source.mkdir()
    for name in (builder.ARTIFACT, builder.RECEIPT, *NAMES):
        (source / name).write_text(json.dumps({"fixture": name}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return source, output


def test_cli_passes_exact_six_staged_dicts_and_parent_pair_without_network(tmp_path):
    source, output = inputs(tmp_path)
    receipt = (source / builder.RECEIPT).read_bytes()
    seen = []
    def write(artifact, parent, directory, documents, source_hashes, *, parent_raw=None):
        seen.append((artifact, parent, directory, documents, source_hashes, parent_raw))
        return {"parent_receipt_sha256": hashlib.sha256(receipt).hexdigest()}
    result = builder.build(source, output, writer=write, dependencies=DEPS)
    assert result["built"] and result["sources"] == 6
    assert set(seen[0][3]) == set(NAMES)
    assert seen[0][3]["us_disclosure_feed.json"] == {"fixture": "us_disclosure_feed.json"}
    assert seen[0][0] == {"fixture": builder.ARTIFACT}
    assert seen[0][1] == {"fixture": builder.RECEIPT}
    assert seen[0][4] == {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in NAMES}
    assert seen[0][2] == output
    assert type(seen[0][5]) is bytes and seen[0][5] == receipt
    assert len(list(source.iterdir())) == 8


@pytest.mark.parametrize("mutation", ["missing", "symlink", "array", "duplicate", "nonfinite", "oversize"])
def test_bad_input_rejected_before_writer(tmp_path, mutation):
    source, output = inputs(tmp_path)
    file = source / NAMES[3]
    if mutation == "missing":
        file.unlink()
    elif mutation == "symlink":
        file.unlink(); file.symlink_to(source / NAMES[0])
    else:
        file.write_text({"array": "[]", "duplicate": '{"a":1,"a":2}',
                         "nonfinite": '{"a":NaN}', "oversize": " " * 4097}[mutation])
    def unexpected(*_args):
        pytest.fail("invalid input reached writer")
    with pytest.raises((builder.CandidateError, ValueError)):
        builder.build(source, output, writer=unexpected, dependencies=DEPS)


def test_exact_parent_receipt_bytes_are_bound_not_reserialized_json(tmp_path):
    source, output = inputs(tmp_path)
    with pytest.raises(builder.CandidateError, match="parent-bytes-mismatch"):
        builder.build(source, output, writer=lambda *_, **_kw: {"parent_receipt_sha256": "0" * 64}, dependencies=DEPS)


@pytest.mark.parametrize("where", ["same", "nested", "ancestor", "notempty"])
def test_output_cannot_mix_with_public_staging_or_existing_files(tmp_path, where):
    source, output = inputs(tmp_path)
    if where == "same": output = source
    elif where == "nested": output = source / "candidate"
    elif where == "ancestor": output = tmp_path
    else:
        output.mkdir(); (output / "existing").write_text("preserve")
    with pytest.raises(builder.CandidateError):
        builder.build(source, output, writer=lambda *_: pytest.fail("writer called"), dependencies=DEPS)


def test_noncanonical_parent_receipt_rejected_before_writer(tmp_path):
    source, output = inputs(tmp_path)
    file = source / builder.RECEIPT
    file.write_text('{ "fixture" : "parent" }')
    with pytest.raises(builder.CandidateError, match="parent-not-canonical"):
        builder.build(source, output, writer=lambda *_: pytest.fail("writer called"), dependencies=DEPS)


def test_real_offline_six_source_builder_passes_js_candidate_preflight(tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for offline publisher bridge")
    # Reuse the existing synthetic staged source fixture without production data.
    spec = importlib.util.spec_from_file_location("prepared_bridge_fixture", ROOT / "tests/test_prepared_news_publish_bridge.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    source, output = tmp_path / "staged", tmp_path / "candidate"
    source.mkdir(); fixture._write_sources(source)
    (source / "public_disclosure_feed.json").write_text(json.dumps({"items": [{
        "ticker": "000001", "market": "KR", "name": "합성회사001", "disclosures": [{
            "title": "합성 공시", "date": "2024-03-04",
            "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240304000001"}]}]}), encoding="utf-8")
    report = json.loads((source / "stock_report_public.json").read_text())
    report["stocks"][0]["facts"] = [{"metric": "revenue", "value": 123, "unit": "KRW", "as_of": "2025", "source": "DART"}]
    (source / "stock_report_public.json").write_text(json.dumps(report), encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", os.defpath), "PYTHONDONTWRITEBYTECODE": "1"}
    prepared = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/member-map/build-prepared-business-index.py"),
        "--source-dir", str(source), "--output", str(source / builder.ARTIFACT),
        "--receipt-output", str(source / builder.RECEIPT)], capture_output=True, text=True, timeout=60, env=env)
    assert prepared.returncode == 0, prepared.stderr
    built = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/member-map/build-company-snapshots.py"),
        "--source-dir", str(source), "--output-dir", str(output)], capture_output=True, text=True, timeout=60, env=env)
    assert built.returncode == 0, built.stderr
    release = json.loads((output / "member_map_company_release.json").read_text())
    assert release["company_count"] == 200
    assert release["source_sha256"] == {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in NAMES}
    assert release["parent_receipt_sha256"] == hashlib.sha256((source / builder.RECEIPT).read_bytes()).hexdigest()
    for entry in release["buckets"].values():
        bucket = json.loads((output / (entry["sha256"] + ".json")).read_text())
        if "KR:000001" in bucket["companies"]:
            row = bucket["companies"]["KR:000001"]
            assert any(fact["as_of"] == "2025" for fact in row["facts"])
            documents = row["documents"]
            assert any(doc["as_of"] == "2024-03-04" for doc in documents)
    checked = subprocess.run([node, str(ROOT / ".github/actions/publish-data/publish_company_snapshots.cjs"),
        "--output-dir", str(output)], capture_output=True, text=True, timeout=30, env=env)
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)["companies"] == 200


def test_action_uploads_only_explicit_safe_summary_with_short_retention():
    import yaml
    steps = yaml.safe_load((ROOT / ".github/actions/publish-data/action.yml").read_text())["runs"]["steps"]
    publish = next(step for step in steps if step.get("id") == "publish_company_snapshots")
    upload = next(step for step in steps if step.get("uses") == "actions/upload-artifact@v4")
    assert '--summary-output "$summary_file"' in publish["run"]
    assert 'summary_file="$summary_dir/summary.json"' in publish["run"]
    assert '$RUNNER_TEMP/company-snapshot-summary.' in publish["run"]
    assert '[ -s "$summary_file" ]' in publish["run"]
    assert upload["with"]["path"] == "${{ steps.publish_company_snapshots.outputs.summary_path }}"
    assert upload["with"]["name"] == "company-snapshot-safe-summary-${{ github.run_id }}-${{ github.job }}"
    assert 3 <= upload["with"]["retention-days"] <= 7
    assert "summary_path != ''" in upload["if"]
    assert upload["continue-on-error"] is True

"""Offline raw EX-21 cache lifecycle and binding guards."""
import copy
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("us_raw_cache", ROOT / "api/collectors/company_structure_us_refresh.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
from api.intelligence.company_structure_sec import PARSER_REVISION, find_exhibit

CIK = "0000000001"
ACCESSION = "0000000001-26-000001"
URL = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/ex21.htm"
RAW = b"<html><table><tr><th>Name</th><th>Jurisdiction</th></tr><tr><td>Child Inc</td><td>Delaware</td></tr></table></html>"
NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def source():
    metadata = {"issuer_id": "US:T1", "issuer_name": "Public Company Inc", "cik": CIK,
                "accession": ACCESSION, "filed_date": "2026-03-01", "period_end": "2025-12-31",
                "form": "10-K", "primary_document": "annual.htm",
                "url": "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/annual.htm"}
    return {"schema": core.SCHEMA, "universe": {"US": ["T1"]}, "currentCiks": [CIK],
            "unmapped": {}, "issuers": {CIK: {"cik": CIK, "tickerAliases": ["T1"],
            "attemptStatus": "not-attempted", "attemptedAt": None, "filingMetadata": metadata,
            "metadataCheckedAt": NOW.isoformat(), "sourceGap": None}}}


def helpers(calls, parser):
    def get(url, maximum):
        calls.append(url)
        return RAW if url.endswith("/ex21.htm") else b"index"
    def find_exhibit(index, *, cik, accession, form):
        return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/ex21.htm"
    return SimpleNamespace(get_public=get, find_exhibit=find_exhibit,
                           parse_exhibit=parser, latest_metadata=lambda *a: None)


def parsed(raw, metadata, status="needs-review", revision="prior-v1"):
    assert raw == RAW
    return {"schema": "sec-company-subsidiaries-v1", "cik": metadata["cik"],
            "accession": metadata["accession"], "filedDate": metadata["filedDate"],
            "periodEnd": metadata["periodEnd"], "url": metadata["url"],
            "documentSha256": hashlib.sha256(raw).hexdigest(), "parserRevision": revision,
            "status": status, "rows": [{"name": "Child Inc"}] if status == "parsed" else []}


def refresh(doc, tmp_path, cache, parser, now=NOW, calls=None):
    calls = [] if calls is None else calls
    saved = []
    result, summary = core.refresh(doc, source_dir=tmp_path, fetch_public=True, now=now,
        raw_cache_dir=cache, helpers=helpers(calls, parser), checkpoint=lambda value: saved.append(copy.deepcopy(value)))
    return result, summary, calls, saved


def first_review(tmp_path):
    cache = tmp_path / "raw"
    def before_parse(raw, metadata):
        assert (cache / (hashlib.sha256(raw).hexdigest() + ".gz")).is_file()
        return parsed(raw, metadata)
    doc, summary, calls, saved = refresh(source(), tmp_path, cache, before_parse)
    assert summary["rawCacheSaved"] == 1 and summary["requests"] == 2
    assert any(CIK in state["issuers"] and "rawExhibitCache" in state["issuers"][CIK] for state in saved)
    return doc, cache


def next_day(doc):
    doc["requestBudget"]["day"] = "2026-10-21"
    return NOW + timedelta(days=1)


def test_revised_review_reparses_raw_bytes_without_get(tmp_path):
    doc, cache = first_review(tmp_path)
    calls = []
    doc, summary, calls, _ = refresh(doc, tmp_path, cache,
        lambda raw, metadata: parsed(raw, metadata, "parsed", PARSER_REVISION), next_day(doc), calls)
    assert summary["rawCacheHit"] == summary["success"] == 1
    assert summary["requests"] == 0 and calls == []
    assert doc["issuers"][CIK]["exhibit"]["status"] == "parsed"
    assert "reviewExhibit" not in doc["issuers"][CIK]


def test_binding_mismatch_is_error_without_get_or_promotion(tmp_path):
    doc, cache = first_review(tmp_path)
    doc["issuers"][CIK]["reviewExhibit"]["documentSha256"] = "0" * 64
    original = copy.deepcopy(doc["issuers"][CIK]["reviewExhibit"])
    doc, summary, calls, _ = refresh(doc, tmp_path, cache,
        lambda *a: AssertionError("parser must not run"), next_day(doc))
    assert summary["error"] == 1 and summary["requests"] == 0 and calls == []
    assert doc["issuers"][CIK]["sourceGap"] == "sec-raw-cache-binding"
    assert doc["issuers"][CIK]["reviewExhibit"] == original


def test_corrupt_gzip_is_explicit_error_without_get(tmp_path):
    doc, cache = first_review(tmp_path)
    digest = doc["issuers"][CIK]["rawExhibitCache"]["documentSha256"]
    (cache / (digest + ".gz")).write_bytes(b"broken")
    doc, summary, calls, _ = refresh(doc, tmp_path, cache,
        lambda *a: AssertionError("parser must not run"), next_day(doc))
    assert summary["error"] == 1 and calls == []
    assert doc["issuers"][CIK]["sourceGap"] == "sec-raw-cache-invalid"


def test_cache_symlink_cannot_escape_directory(tmp_path):
    doc, cache = first_review(tmp_path)
    digest = doc["issuers"][CIK]["rawExhibitCache"]["documentSha256"]
    blob = cache / (digest + ".gz")
    outside = tmp_path / "outside.gz"
    blob.rename(outside)
    blob.symlink_to(outside)
    doc, summary, calls, _ = refresh(doc, tmp_path, cache,
        lambda *a: AssertionError("parser must not run"), next_day(doc))
    assert summary["error"] == 1 and calls == []
    assert doc["issuers"][CIK]["sourceGap"] == "sec-raw-cache-invalid"


def test_parser_output_must_match_cached_source(tmp_path):
    doc, cache = first_review(tmp_path)
    def wrong_source(raw, metadata):
        value = parsed(raw, metadata, "parsed", PARSER_REVISION)
        value["documentSha256"] = "0" * 64
        return value
    doc, summary, calls, _ = refresh(doc, tmp_path, cache, wrong_source, next_day(doc))
    assert summary["error"] == 1 and calls == []
    assert doc["issuers"][CIK]["sourceGap"] == "sec-raw-cache-parse-mismatch"
    assert "exhibit" not in doc["issuers"][CIK]


def test_new_accession_fetches_instead_of_reusing_cache(tmp_path):
    doc, cache = first_review(tmp_path)
    metadata = doc["issuers"][CIK]["filingMetadata"]
    metadata["accession"] = "0000000001-26-000002"
    metadata["url"] = metadata["url"].replace("000000000126000001", "000000000126000002")
    calls = []
    doc, summary, calls, _ = refresh(doc, tmp_path, cache,
        lambda raw, meta: parsed(raw, meta, "parsed", PARSER_REVISION), next_day(doc), calls)
    assert summary["rawCacheHit"] == 0 and summary["requests"] == len(calls) == 2
    assert doc["issuers"][CIK]["exhibit"]["accession"] == metadata["accession"]


def test_bad_reparse_preserves_previous_good_exhibit(tmp_path):
    doc, cache = first_review(tmp_path)
    issuer = doc["issuers"][CIK]
    good = parsed(RAW, {"cik": CIK, "accession": ACCESSION, "filedDate": "2026-03-01",
                        "periodEnd": "2025-12-31", "url": URL}, "parsed", "prior-v1")
    issuer["exhibit"] = copy.deepcopy(good)
    issuer["lastSuccessAt"] = NOW.isoformat()
    doc, summary, calls, _ = refresh(doc, tmp_path, cache,
        lambda raw, meta: parsed(raw, meta, "needs-review", PARSER_REVISION), next_day(doc))
    assert summary["rawCacheHit"] == summary["retained"] == 1 and calls == []
    assert doc["issuers"][CIK]["exhibit"] == good


def test_dry_run_does_not_touch_raw_cache(tmp_path):
    cache = tmp_path / "raw"
    doc, summary = core.refresh(source(), source_dir=tmp_path, raw_cache_dir=cache, now=NOW)
    assert not cache.exists() and summary["rawCacheHit"] == summary["rawCacheSaved"] == summary["rawCacheSkipped"] == 0
    assert "rawExhibitCache" not in doc["issuers"][CIK]
    cli = core._module(ROOT / "scripts/member-map/refresh-us-company-structure.py", "raw_cache_cli")
    args = cli.parse_args(["--source-dir", str(tmp_path), "--store", str(tmp_path / "store.json"),
                           "--raw-cache-dir", str(cache)])
    assert args.raw_cache_dir == cache


def test_at_capacity_skips_new_blob_but_keeps_valid_parse_and_existing_cache(tmp_path, monkeypatch):
    cache = tmp_path / "raw"
    cache.mkdir()
    prior = cache / ("f" * 64 + ".gz")
    prior.write_bytes(b"existing-cache-content")
    monkeypatch.setattr(core, "MAX_RAW_CACHE_BYTES", prior.stat().st_size)
    doc, summary, calls, _ = refresh(source(), tmp_path, cache,
        lambda raw, meta: parsed(raw, meta, "parsed", PARSER_REVISION))
    assert summary["success"] == summary["rawCacheSkipped"] == 1
    assert summary["rawCacheSaved"] == 0 and summary["requests"] == len(calls) == 2
    assert doc["issuers"][CIK]["exhibit"]["status"] == "parsed"
    assert "rawExhibitCache" not in doc["issuers"][CIK]
    assert prior.read_bytes() == b"existing-cache-content"
    assert list(cache.iterdir()) == [prior]


def test_offline_replay_batch_changes_only_parser_result_fields(tmp_path):
    doc, cache = first_review(tmp_path)
    first = doc["issuers"][CIK]
    second_cik = "0000000002"
    second = copy.deepcopy(first)
    second_metadata = second["filingMetadata"]
    second_metadata["cik"] = second_cik
    second_metadata["accession"] = "0000000002-26-000001"
    second_metadata["url"] = second_metadata["url"].replace("/1/000000000126000001/", "/2/000000000226000001/")
    second_url = URL.replace("/1/000000000126000001/", "/2/000000000226000001/")
    second.update(cik=second_cik)
    second["reviewExhibit"].update(cik=second_cik, accession=second_metadata["accession"], url=second_url)
    second["rawExhibitCache"].update(cik=second_cik, accession=second_metadata["accession"], url=second_url)
    doc["currentCiks"].append(second_cik)
    doc["issuers"][second_cik] = second
    before = copy.deepcopy(doc)
    replayed, summary = core.reparse_cached_reviews(doc, cache, now=NOW,
        helpers=SimpleNamespace(parse_exhibit=lambda raw, meta: parsed(raw, meta, "parsed", PARSER_REVISION)))
    assert summary["eligible"] == summary["cacheHits"] == summary["parsed"] == 2
    assert summary["missing"] == summary["held"] == summary["errors"] == 0
    assert doc == before
    for cik in (CIK, second_cik):
        prior = before["issuers"][cik]
        after = replayed["issuers"][cik]
        for field in ("attemptedAt", "checkedAt", "metadataCheckedAt", "filingMetadata"):
            assert after.get(field) == prior.get(field)
        assert after["attemptStatus"] == "success" and after["sourceGap"] is None
        assert after["lastSuccessAt"] == prior["attemptedAt"]
    assert replayed["requestBudget"] == before["requestBudget"]
    assert replayed.get("generatedAt") == before.get("generatedAt")


def test_offline_replay_missing_raw_is_unchanged(tmp_path):
    doc, cache = first_review(tmp_path)
    binding = doc["issuers"][CIK]["rawExhibitCache"]
    (cache / (binding["documentSha256"] + ".gz")).unlink()
    before = copy.deepcopy(doc)
    replayed, summary = core.reparse_cached_reviews(doc, cache, now=NOW,
        helpers=SimpleNamespace(parse_exhibit=lambda *a: AssertionError("parser must not run")))
    assert replayed == before and summary["eligible"] == summary["missing"] == 1
    assert summary["cacheHits"] == summary["errors"] == 0


def test_offline_replay_bad_cache_reports_error_and_keeps_old_result(tmp_path):
    doc, cache = first_review(tmp_path)
    binding = doc["issuers"][CIK]["rawExhibitCache"]
    (cache / (binding["documentSha256"] + ".gz")).write_bytes(b"broken")
    before = copy.deepcopy(doc)
    replayed, summary = core.reparse_cached_reviews(doc, cache, now=NOW,
        helpers=SimpleNamespace(parse_exhibit=lambda *a: AssertionError("parser must not run")))
    assert replayed == before and summary["eligible"] == summary["errors"] == 1
    assert summary["lists"]["errors"] == [{"cik": CIK, "reason": "sec-raw-cache-invalid"}]


def test_replay_cli_requires_cache_and_excludes_fetch(tmp_path):
    import pytest
    cli = core._module(ROOT / "scripts/member-map/refresh-us-company-structure.py", "raw_cache_cli_replay")
    base = ["--source-dir", str(tmp_path), "--store", str(tmp_path / "store.json")]
    with pytest.raises(SystemExit):
        cli.parse_args(base + ["--replay-cached"])
    with pytest.raises(SystemExit):
        cli.parse_args(base + ["--fetch-public", "--replay-cached", "--raw-cache-dir", str(tmp_path / "raw")])
    doc, cache = first_review(tmp_path)
    store = tmp_path / "store.json"
    core.atomic_json(store, doc)
    args = cli.parse_args(base + ["--replay-cached", "--raw-cache-dir", str(cache)])
    cli.run(args)
    replayed = core.read_json(store, maximum=None)
    assert replayed["requestBudget"] == doc["requestBudget"]
    assert replayed["issuers"][CIK]["attemptedAt"] == doc["issuers"][CIK]["attemptedAt"]


def test_cofiler_review_reason_is_not_generic_error(tmp_path):
    def review_only(raw, metadata):
        raise ValueError("sec-cofiler-issuer-needs-review")
    doc, summary, _, _ = refresh(source(), tmp_path, tmp_path / "raw", review_only)
    assert summary["error"] == 0 and summary["sourceGap"] == 1
    assert doc["issuers"][CIK]["attemptStatus"] == "needs-review"
    assert doc["issuers"][CIK]["sourceGap"] == "sec-cofiler-issuer-needs-review"


def test_revised_review_reuses_derived_binding_after_public_sanitization(tmp_path):
    doc, cache = first_review(tmp_path)
    del doc["issuers"][CIK]["rawExhibitCache"]
    calls = []
    doc, summary, calls, _ = refresh(doc, tmp_path, cache,
        lambda raw, meta: parsed(raw, meta, "parsed", PARSER_REVISION), next_day(doc), calls)
    assert summary["rawCacheHit"] == summary["success"] == 1
    assert summary["requests"] == 0 and calls == []


def test_evicted_cache_falls_back_to_bounded_get(tmp_path):
    doc, cache = first_review(tmp_path)
    digest = doc["issuers"][CIK]["reviewExhibit"]["documentSha256"]
    (cache / (digest + ".gz")).unlink()
    del doc["issuers"][CIK]["rawExhibitCache"]
    doc, summary, calls, _ = refresh(doc, tmp_path, cache,
        lambda raw, meta: parsed(raw, meta, "parsed", PARSER_REVISION), next_day(doc))
    assert summary["rawCacheHit"] == 0 and summary["requests"] == len(calls) == 2
    assert summary["success"] == summary["rawCacheSaved"] == 1


def test_offline_replay_derives_binding_and_original_success_time(tmp_path):
    doc, cache = first_review(tmp_path)
    issuer = doc["issuers"][CIK]
    del issuer["rawExhibitCache"]
    prior_good = copy.deepcopy(issuer)
    issuer["lastSuccessAt"] = "2025-01-01T00:00:00+00:00"
    original_attempt = issuer["attemptedAt"]
    replayed, summary = core.reparse_cached_reviews(doc, cache, now=NOW + timedelta(days=1),
        helpers=SimpleNamespace(parse_exhibit=lambda raw, meta: parsed(raw, meta, "parsed", PARSER_REVISION)))
    assert summary["parsed"] == 1 and summary["errors"] == 0
    assert replayed["issuers"][CIK]["lastSuccessAt"] == original_attempt
    assert replayed["issuers"][CIK]["attemptedAt"] == prior_good["attemptedAt"]
    assert replayed["issuers"][CIK].get("checkedAt") == prior_good.get("checkedAt")


def test_offline_replay_rejects_success_before_filing_observation(tmp_path):
    doc, cache = first_review(tmp_path)
    doc["issuers"][CIK]["attemptedAt"] = "2025-01-01T00:00:00Z"
    before = copy.deepcopy(doc)
    replayed, summary = core.reparse_cached_reviews(doc, cache, now=NOW,
        helpers=SimpleNamespace(parse_exhibit=lambda raw, meta: parsed(raw, meta, "parsed", PARSER_REVISION)))
    assert replayed == before
    assert summary["errors"] == 1 and summary["lists"]["errors"][0]["reason"] == "sec-replay-observation-invalid"


def test_replay_cli_enumerates_current_ciks_without_replacing_public_store(tmp_path):
    cli = core._module(ROOT / "scripts/member-map/refresh-us-company-structure.py", "raw_cache_cli_public")
    doc, cache = first_review(tmp_path)
    doc["generatedAt"] = NOW.isoformat()
    doc.pop("currentCiks")
    doc.pop("requestBudget")
    doc["issuers"][CIK].pop("rawExhibitCache")
    data = tmp_path / "data"
    core.atomic_json(data / "universe_search.json", {"stocks": [{"market": "US", "ticker": "T1"}]})
    core.atomic_json(data / "sec_ticker_cik_map.json", {"T1": CIK})
    store = tmp_path / "public-store.json"
    core.atomic_json(store, doc)
    args = cli.parse_args(["--source-dir", str(tmp_path), "--store", str(store),
                           "--replay-cached", "--raw-cache-dir", str(cache)])
    assert cli.run(args) == 0
    replayed = core.read_json(store, maximum=None)
    assert "currentCiks" not in replayed and "requestBudget" not in replayed
    assert replayed["generatedAt"] == doc["generatedAt"]
    assert replayed["issuers"][CIK]["attemptedAt"] == doc["issuers"][CIK]["attemptedAt"]


def test_broken_deflate_is_per_issuer_cache_error(tmp_path):
    doc, cache = first_review(tmp_path)
    digest = doc["issuers"][CIK]["reviewExhibit"]["documentSha256"]
    blob = cache / (digest + ".gz")
    damaged = bytearray(gzip.compress(RAW))
    damaged[10] = 0xff  # Invalid deflate block type; gzip header remains valid.
    blob.write_bytes(damaged)
    before = copy.deepcopy(doc)
    replayed, summary = core.reparse_cached_reviews(doc, cache, now=NOW,
        helpers=SimpleNamespace(parse_exhibit=lambda *a: AssertionError("parser must not run")))
    assert replayed == before and summary["errors"] == 1
    assert summary["lists"]["errors"] == [{"cik": CIK, "reason": "sec-raw-cache-invalid"}]


def test_incompressible_maximum_raw_roundtrips_cache_size_bound(tmp_path):
    raw = os.urandom(core.MAX_BYTES)
    digest, saved, skipped = core._save_raw_exhibit(tmp_path / "raw", raw)
    assert saved and not skipped
    size = (tmp_path / "raw" / (digest + ".gz")).stat().st_size
    assert core.MAX_BYTES + 1024 < size <= core.MAX_BYTES + 65536
    assert core._read_raw_exhibit(tmp_path / "raw", digest) == raw


def test_cofiler_public_review_rehydrates_proof_and_missing_index_is_cache_gap(tmp_path):
    """CI fixture: public sanitizer omits rawExhibitCache but retains six-field proof."""
    issuer_name = "Public Company Inc"
    accession = "0000000003-26-000001"  # Neither the requested nor archive CIK.
    compact = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/2/{compact}/ex21.htm"
    index = (f'<div class="companyInfo"><span>{issuer_name} (Filer) CIK : {CIK}</span></div>'
             '<div class="companyInfo"><span>Other Registrant Inc (Filer) CIK : 0000000002</span></div>'
             '<table class="tableFile"><tr><th>Document</th><th>Type</th></tr>'
             f'<tr><td><a href="{url}">ex21.htm</a></td><td>EX-21</td></tr></table>').encode()
    exhibit = (f'<p>Subsidiaries of {issuer_name}</p><table><tr><th>Name</th>'
               '<th>Jurisdiction</th></tr><tr><td>Child Inc.</td>'
               '<td>Delaware</td></tr></table>').encode()
    selected, proof = find_exhibit(index, cik=CIK, accession=accession,
                                  issuer_name=issuer_name, return_proof=True)
    assert selected == url and proof["archiveCik"] == "2"
    assert set(proof) == {"requestedCik", "archiveCik", "accession", "issuerName",
                          "exhibitUrl", "indexSha256"}
    assert not core._valid_exhibit_url(url, CIK, accession)
    assert core._valid_exhibit_url(url, CIK, accession, proof)
    import pytest
    with pytest.raises(ValueError, match="sec-cofiler"):
        find_exhibit(index.replace(issuer_name.encode(), b"Different Inc"), cik=CIK,
                     accession=accession, issuer_name=issuer_name, return_proof=True)
    with pytest.raises(ValueError, match="sec-cofiler"):
        find_exhibit(index.replace(b"CIK : 0000000002", b"CIK : 0000000004"), cik=CIK,
                     accession=accession, issuer_name=issuer_name, return_proof=True)

    doc = source()
    row = doc["issuers"][CIK]
    filing = row["filingMetadata"]
    filing["accession"] = accession
    filing["url"] = f"https://www.sec.gov/Archives/edgar/data/1/{compact}/annual.htm"
    row["attemptStatus"] = "needs-review"
    row["attemptedAt"] = NOW.isoformat()
    row["sourceGap"] = "source-gap:ex21-needs-review"
    row["reviewExhibit"] = {"schema": "sec-company-subsidiaries-v1", "cik": CIK,
        "accession": accession, "filedDate": filing["filed_date"],
        "periodEnd": filing["period_end"], "url": url,
        "documentSha256": hashlib.sha256(exhibit).hexdigest(),
        "cofilerProof": proof, "parserRevision": "prior-revision",
        "status": "needs-review", "rows": []}
    assert "rawExhibitCache" not in row
    cache = tmp_path / "raw"
    core._save_raw_exhibit(cache, index)
    core._save_raw_exhibit(cache, exhibit)
    replayed, summary = core.reparse_cached_reviews(doc, cache, now=NOW)
    assert summary["parsed"] == summary["cacheHits"] == 1
    assert summary["errors"] == 0 and len(replayed["issuers"][CIK]["exhibit"]["rows"]) == 1
    assert replayed["issuers"][CIK]["exhibit"]["cofilerProof"] == proof

    (cache / (proof["indexSha256"] + ".gz")).unlink()
    before = copy.deepcopy(doc)
    replayed, summary = core.reparse_cached_reviews(doc, cache, now=NOW)
    assert replayed == before
    assert summary["eligible"] == summary["missing"] == 1
    assert summary["errors"] == summary["cacheHits"] == summary["parsed"] == 0

    index_url = f"https://www.sec.gov/Archives/edgar/data/1/{compact}/{accession}-index.html"
    calls = []
    helpers = core.load_helpers()
    def offline_get(target, maximum):
        calls.append(target)
        return {index_url: index, url: exhibit}[target]
    helpers.get_public = offline_get
    refreshed, summary = core.refresh(doc, source_dir=tmp_path, fetch_public=True,
        raw_cache_dir=cache, helpers=helpers, now=NOW + timedelta(days=1),
        sleep=lambda delay: None, checkpoint=lambda value: None)
    assert calls == [index_url, url]
    assert summary["success"] == 1 and summary["rawCacheHit"] == 0
    assert refreshed["issuers"][CIK]["exhibit"]["cofilerProof"] == proof
    assert len(refreshed["issuers"][CIK]["exhibit"]["rows"]) == 1

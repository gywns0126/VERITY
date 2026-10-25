"""Digest/source binding and model-free filing extraction cache tests."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from api.analyzers.facilities_parser import (
    build_business_facilities_prompt,
    parse_business_facilities,
    validate_business_facilities_data,
)
from api.analyzers.properties_parser import (
    build_10k_properties_prompt,
    parse_10k_properties,
    validate_10k_properties_data,
)
from api.utils.filing_extraction_cache import (
    CACHE_MAX_BYTES,
    FilingExtractionCacheError,
    cache_read,
    cache_write,
    filing_cache_path,
    filing_source_sha256,
)


SEC_EXTRACTOR = "sec-properties-v1"
SEC_ACCESSION = "0000320193-25-000079"
SEC_ID = f"source:sec:{SEC_ACCESSION}"
SEC_DATE = "2025-10-31"
SEC_URL = "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"
SEC_RAW = "Item 2. Properties. " + ("Public filing content. " * 30)

DART_EXTRACTOR = "dart-facilities-v1"
DART_RECEIPT = "20260318001234"
DART_ID = f"source:dart:{DART_RECEIPT}"
DART_DATE = "2026-03-18"
DART_URL = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={DART_RECEIPT}"
DART_RAW = "II. 사업의 내용 " + ("공개 사업보고서 원문 " * 40)


def _generated_at():
    return datetime(2026, 10, 25, tzinfo=timezone.utc).isoformat()


def _write_sec(tmp_path: Path, data: dict | None = None) -> Path:
    return cache_write(
        extractor=SEC_EXTRACTOR,
        source_id=SEC_ID,
        as_of=SEC_DATE,
        raw_sha256=filing_source_sha256(SEC_EXTRACTOR, SEC_RAW),
        url=SEC_URL,
        generated_at=_generated_at(),
        data=data or {"headquarters": None, "summary_ko": "요약"},
        cache_root=tmp_path,
    )


def _write_dart(tmp_path: Path, data: dict | None = None) -> Path:
    return cache_write(
        extractor=DART_EXTRACTOR,
        source_id=DART_ID,
        as_of=DART_DATE,
        raw_sha256=filing_source_sha256(DART_EXTRACTOR, DART_RAW),
        url=DART_URL,
        generated_at=_generated_at(),
        data=data or {"company_type": "manufacturer", "summary_ko": "요약"},
        cache_root=tmp_path,
    )


def test_exact_sec_cache_hit_and_schema_defaults(tmp_path):
    _write_sec(tmp_path)
    got = parse_10k_properties(
        "Apple", "AAPL", SEC_RAW,
        source_id=SEC_ID, as_of=SEC_DATE, source_url=SEC_URL, cache_root=tmp_path,
    )
    assert "error" not in got
    assert got["owned_properties"] == got["leased_properties"] == []
    assert got["summary_ko"] == "요약"


def test_exact_dart_cache_hit_and_schema_defaults(tmp_path):
    _write_dart(tmp_path)
    got = parse_business_facilities(
        "공개회사", "000000", DART_RAW,
        source_id=DART_ID, as_of=DART_DATE, source_url=DART_URL, cache_root=tmp_path,
    )
    assert "error" not in got
    assert got["domestic_facilities"] == got["overseas_facilities"] == []
    assert got["investment_properties"] == [] and got["country_exposure"] == {}


def test_cache_miss_is_pending_and_keeps_source_clock(tmp_path):
    got = parse_10k_properties(
        "Apple", "AAPL", SEC_RAW,
        source_id=SEC_ID, as_of=SEC_DATE, source_url=SEC_URL, cache_root=tmp_path,
    )
    assert got == {
        "error": "extraction_pending",
        "status": "pending",
        "reason": "cache_absent",
        "source_id": SEC_ID,
        "source_sha256": filing_source_sha256(SEC_EXTRACTOR, SEC_RAW),
        "as_of": SEC_DATE,
    }


def test_different_source_bytes_cannot_reuse_cache(tmp_path):
    _write_sec(tmp_path)
    changed = SEC_RAW + " amended"
    got = parse_10k_properties(
        "Apple", "AAPL", changed,
        source_id=SEC_ID, as_of=SEC_DATE, source_url=SEC_URL, cache_root=tmp_path,
    )
    assert got["status"] == "pending" and got["reason"] == "cache_absent"
    assert got["source_sha256"] != filing_source_sha256(SEC_EXTRACTOR, SEC_RAW)


@pytest.mark.parametrize(
    "source_id,source_url,reason",
    [
        (SEC_ID, "https://example.com/Archives/edgar/data/x", "source_identity_mismatch"),
        ("source:sec:0000000000-00-000001", SEC_URL, "source_identity_mismatch"),
        (SEC_ID, "https://www.sec.gov:bad/Archives/edgar/data/x", "nonpublic_source_url"),
    ],
)
def test_nonofficial_or_mismatched_sec_source_is_closed(tmp_path, source_id, source_url, reason):
    got = parse_10k_properties(
        "Apple", "AAPL", SEC_RAW,
        source_id=source_id, as_of=SEC_DATE, source_url=source_url, cache_root=tmp_path,
    )
    assert got["status"] == "pending" and got["reason"] == reason


def test_duplicate_key_and_nan_are_rejected(tmp_path):
    path = _write_sec(tmp_path)
    value = json.loads(path.read_text(encoding="utf-8"))
    text = json.dumps(value, ensure_ascii=False).replace('"status": "ready"', '"status": "ready", "status": "ready"')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(FilingExtractionCacheError, match="duplicate_json_key"):
        cache_read(
            extractor=SEC_EXTRACTOR, source_id=SEC_ID, as_of=SEC_DATE,
            raw_sha256=filing_source_sha256(SEC_EXTRACTOR, SEC_RAW), url=SEC_URL,
            cache_root=tmp_path,
        )
    text = json.dumps(value, ensure_ascii=False).replace('"summary_ko": "요약"', '"summary_ko": NaN')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(FilingExtractionCacheError, match="invalid_json_constant"):
        cache_read(
            extractor=SEC_EXTRACTOR, source_id=SEC_ID, as_of=SEC_DATE,
            raw_sha256=filing_source_sha256(SEC_EXTRACTOR, SEC_RAW), url=SEC_URL,
            cache_root=tmp_path,
        )


def test_oversize_and_symlink_cache_are_rejected(tmp_path):
    path = _write_sec(tmp_path)
    path.write_bytes(b"x" * (CACHE_MAX_BYTES + 1))
    with pytest.raises(FilingExtractionCacheError, match="cache_size_invalid"):
        cache_read(
            extractor=SEC_EXTRACTOR, source_id=SEC_ID, as_of=SEC_DATE,
            raw_sha256=filing_source_sha256(SEC_EXTRACTOR, SEC_RAW), url=SEC_URL,
            cache_root=tmp_path,
        )
    path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    path.symlink_to(outside)
    with pytest.raises(FilingExtractionCacheError, match="cache_symlink_rejected"):
        cache_read(
            extractor=SEC_EXTRACTOR, source_id=SEC_ID, as_of=SEC_DATE,
            raw_sha256=filing_source_sha256(SEC_EXTRACTOR, SEC_RAW), url=SEC_URL,
            cache_root=tmp_path,
        )


def test_prompt_builders_use_the_digest_bound_slice():
    long_sec = "A" * 40_100
    long_dart = "가" * 60_100
    sec_prompt = build_10k_properties_prompt(
        "Company", "T", long_sec,
        source_id=SEC_ID, as_of=SEC_DATE, source_url=SEC_URL,
    )
    dart_prompt = build_business_facilities_prompt(
        "회사", "000000", long_dart,
        source_id=DART_ID, as_of=DART_DATE, source_url=DART_URL,
    )
    assert "A" * 40_000 in sec_prompt and "A" * 40_001 not in sec_prompt
    assert "가" * 60_000 in dart_prompt and "가" * 60_001 not in dart_prompt


def test_prompt_cannot_be_built_before_public_source_validation():
    with pytest.raises(FilingExtractionCacheError, match="source_identity_mismatch"):
        build_10k_properties_prompt(
            "Company", "T", SEC_RAW,
            source_id=SEC_ID, as_of=SEC_DATE, source_url="https://example.com/private",
        )


def test_schema_validators_reject_wrong_nested_container_types():
    with pytest.raises(FilingExtractionCacheError, match="headquarters"):
        validate_10k_properties_data({"headquarters": []})
    with pytest.raises(FilingExtractionCacheError, match="country_exposure"):
        validate_business_facilities_data({"country_exposure": []})
    with pytest.raises(FilingExtractionCacheError, match="invalid_properties_data"):
        validate_10k_properties_data({"error": "model_failed"})


def test_analyzers_have_no_google_or_model_client_import():
    root = Path(__file__).resolve().parents[1]
    for relative in ("api/analyzers/properties_parser.py", "api/analyzers/facilities_parser.py"):
        text = (root / relative).read_text(encoding="utf-8")
        assert "from google" not in text
        assert "genai.Client" not in text
        assert "GEMINI_API_KEY" not in text

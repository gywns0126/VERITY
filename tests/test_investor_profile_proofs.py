"""거장 페이지의 초보자용 인물 증명 카드 계약."""

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "framer-components/public-probe/PublicInvestorPortfolios.tsx"
DATA = ROOT / "data/us_investor_portfolios.json"


def _proof_block() -> str:
    source = COMPONENT.read_text(encoding="utf-8")
    return source[source.index("const PROFILE_PROOFS") : source.index("// 종목 역조회")]


def _proof_keys() -> set[str]:
    block = _proof_block()
    quoted = re.findall(r'^\s{4}"([^"]+)":\s*\{', block, re.MULTILINE)
    bare = re.findall(r"^\s{4}([A-Za-z][A-Za-z0-9]*):\s*\{", block, re.MULTILINE)
    return set(quoted + bare)


def test_every_published_investor_has_a_proof_card():
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    institutions = {item["institution"] for item in payload["investors"]}
    assert len(institutions) == 16
    assert _proof_keys() == institutions


def test_proof_card_has_the_four_requested_fields_and_safe_labels():
    source = COMPONENT.read_text(encoding="utf-8")
    for label in ("주요 경력", "13F 공시 자산", "대표 업적", "대표 보유"):
        assert label in source
    assert "전체 AUM 아님" in source
    assert "slice(0, 3)" in source


def test_curated_proofs_do_not_publish_net_worth_claims():
    block = _proof_block().lower()
    assert "순자산" not in block
    assert "net worth" not in block


def test_every_proof_uses_an_official_or_institutional_source():
    block = _proof_block()
    urls = re.findall(r'sourceUrl:\s*"([^"]+)"', block)
    labels = re.findall(r'sourceLabel:\s*"([^"]+)"', block)
    assert len(urls) == len(labels) == 16
    trusted_hosts = {
        "www.berkshirehathaway.com",
        "www.bridgewater.com",
        "www.rentec.com",
        "pershingsquareholdings.com",
        "www.thirdpoint.com",
        "www.tigerglobal.com",
        "www.ark-invest.com",
        "point72.com",
        "gspp.berkeley.edu",
        "www.opensocietyfoundations.org",
        "ciff.org",
        "vikingglobal.com",
        "www.aqr.com",
        "www.fisherinvestments.com",
        "www.tudor.com",
        "www.gatesfoundation.org",
    }
    assert {urlparse(url).netloc for url in urls} == trusted_hosts
    assert all("공식" in label or label.startswith("UC Berkeley") for label in labels)
    assert "wikipedia.org" not in block.lower()


def test_wikipedia_biography_is_not_rendered_as_factual_evidence():
    source = COMPONENT.read_text(encoding="utf-8")
    render = source[source.index("export default function PublicInvestorPortfolios") :]
    assert "profile.summary" not in render
    assert "profile.source_url" not in render
    assert "위키백과" not in render


def test_public_profile_payload_is_image_only():
    from api.builders.us_investor_portfolios_public_builder import _public_profile

    got = _public_profile({
        "summary": "legacy biography",
        "source_url": "https://example.invalid/bio",
        "image": {
            "url": "https://example.invalid/photo.jpg",
            "artist": "Artist",
            "license": "CC BY",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
        },
    })
    assert got == {"image": {
        "url": "https://example.invalid/photo.jpg",
        "artist": "Artist",
        "license": "CC BY",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    }}
    assert "summary" not in got and "source_url" not in got


def _assert_public_profile_contract(payload):
    assert "profile_source" not in payload["_meta"]
    assert "profile_payload" in payload["_meta"]
    assert datetime.fromisoformat(payload["_meta"]["generated_at"]).utcoffset() is not None
    # profile_sanitized_at records only --sanitize-existing, not normal builds.
    # Check the actual payload instead of requiring that one-off migration stamp.
    for investor in payload["investors"]:
        profile = investor.get("profile")
        assert profile is None or set(profile) == {"image"}
        if profile is not None:
            image = profile["image"]
            assert image.get("url")
            assert set(image) <= {
                "url", "width", "height", "artist", "license", "license_url", "file_page",
            }


def test_committed_investor_payload_contains_no_biography_cache_fields():
    _assert_public_profile_contract(json.loads(DATA.read_text(encoding="utf-8")))


@pytest.mark.parametrize("legacy_profile", [
    None,
    {"summary": "legacy biography", "source_url": "https://example.invalid/bio"},
    {"summary": "legacy biography", "image": {
        "url": "https://example.invalid/photo.jpg", "license": "CC BY",
        "summary": "nested legacy biography",
    }},
])
def test_normal_build_satisfies_profile_contract_without_migration_stamp(monkeypatch, legacy_profile):
    from api.builders import us_investor_portfolios_public_builder as builder

    monkeypatch.setattr(builder, "ACTIVE_MANAGERS", {"1": "Example Fund"})
    monkeypatch.setattr(builder, "collect_profiles", lambda names: {"Example Fund": legacy_profile})
    monkeypatch.setattr(builder, "get_recent_13f_filings", lambda cik, n: [
        {"accession_no": "test", "report_date": "2026-06-30", "filed_at": "2026-08-14"},
    ])
    monkeypatch.setattr(builder, "parse_13f_holdings", lambda accession, cik: [
        {"cusip": "TEST", "shares": 1, "value_usd": 100},
    ])
    monkeypatch.setattr(builder, "resolve_cusips", lambda cusips: {"TEST": "TEST"})
    monkeypatch.setattr(builder, "compute_replication_returns", lambda cik, quarters: [])

    payload = builder.build()
    assert payload["_meta"]["errors"] == []
    assert payload["_meta"]["investor_count"] == len(payload["investors"]) == 1
    assert "profile_sanitized_at" not in payload["_meta"]
    _assert_public_profile_contract(payload)
    expected = ({"image": {"url": "https://example.invalid/photo.jpg", "license": "CC BY"}}
                if legacy_profile and "image" in legacy_profile else None)
    assert payload["investors"][0]["profile"] == expected


def test_sanitize_existing_records_cleanup_without_refreshing_data_date(monkeypatch, tmp_path):
    from api.builders import us_investor_portfolios_public_builder as builder

    generated_at = "2026-08-01T12:00:00+09:00"
    path = tmp_path / "investors.json"
    path.write_text(json.dumps({
        "_meta": {"generated_at": generated_at, "profile_source": "legacy"},
        "investors": [{"profile": {"summary": "legacy biography", "image": {
            "url": "https://example.invalid/photo.jpg", "license": "CC BY",
        }}}],
    }), encoding="utf-8")
    monkeypatch.setattr(builder, "OUTPUT_PATH", str(path))
    monkeypatch.setattr(builder.sys, "argv", ["builder", "--sanitize-existing"])
    assert builder.main() == 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["_meta"]["generated_at"] == generated_at
    assert datetime.fromisoformat(payload["_meta"]["profile_sanitized_at"]).utcoffset() is not None
    _assert_public_profile_contract(payload)


def test_style_map_explains_axes_directly_and_separates_the_caveat():
    source = COMPONENT.read_text(encoding="utf-8")
    assert "→ 오른쪽: 상위 10종목에 더 집중" in source
    assert "↑ 위쪽: 분기별 복제 수익률의 기복이 더 큼" in source
    assert "분산형 ← 상위 10종목 집중 →" in source
    assert "참고 · 위치는 우열 순위가 아니며" in source
    assert 'marginTop: 12' in source
    assert 'borderTop: `1px solid ${C.line}`' in source
    assert "오른쪽일수록 몇 개에 몰아서" not in source
    assert "위일수록 출렁임" not in source

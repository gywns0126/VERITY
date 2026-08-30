"""거장 페이지의 초보자용 인물 증명 카드 계약."""

import json
import re
from pathlib import Path
from urllib.parse import urlparse


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

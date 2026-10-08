"""Public-source failure payloads must not persist request credentials."""
import json

import pytest

from api.collectors import ChainScout as scout


@pytest.mark.parametrize("failure", [RuntimeError, scout.requests.HTTPError])
def test_document_error_does_not_store_provider_url(monkeypatch, failure):
    secret = "sentinel-not-a-real-credential"
    monkeypatch.setattr(scout, "DART_API_KEY", secret)
    monkeypatch.setattr(scout, "get_corp_code", lambda _: "00130587")
    monkeypatch.setattr(scout, "find_latest_business_report_rcept_no",
                        lambda *_: ("20260320001349", "사업보고서 (2025.12)", "20260320"))

    def fail(_):
        raise failure("https://opendart.fss.or.kr/api/document.xml?crtfc_key=" + secret)

    monkeypatch.setattr(scout, "fetch_document_archive", fail)
    result = scout.scout_major_customer_snippets("027040.KS")
    assert result == {"ticker": "027040", "corp_code": "00130587",
                      "rcept_no": "20260320001349", "error": "document.xml 요청 실패"}
    persisted = json.dumps(result)
    assert secret not in persisted
    assert "crtfc_key" not in persisted
    assert "https://" not in persisted

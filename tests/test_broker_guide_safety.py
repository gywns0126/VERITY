from api.collectors.broker_guide import (
    _sanitize_events,
    _sanitize_numeric_claims,
    _sanitize_sources,
    _verified_official_source_url,
)


def test_official_source_verification_rejects_third_party_and_prose_only() -> None:
    assert (
        _verified_official_source_url(
            "한국투자증권",
            "공식 안내 https://www.truefriend.com/fee",
        )
        == "https://www.truefriend.com/fee"
    )
    assert not _verified_official_source_url(
        "미래에셋증권",
        "https://example.com/fee",
    )
    assert not _verified_official_source_url(
        "미래에셋증권",
        "공식 안내에서 확인",
    )


def test_numeric_claims_without_matching_official_source_are_hidden() -> None:
    brokers = [
        {
            "name": "미래에셋증권",
            "domestic_fee": "0.014%",
            "domestic_source": "https://securities.miraeasset.com/fee",
            "fee_basis": "공식 기본 요율",
            "overseas_fee": "0.25%",
            "overseas_source": "공식 안내에서 확인",
            "overseas_basis": "근거 URL 없음",
            "fx_fee": "95%",
            "fx_source": "https://news.example/offer",
            "fx_basis": "제3자 글",
        }
    ]

    flags = _sanitize_numeric_claims(brokers)

    row = brokers[0]
    assert row["domestic_fee"] == "0.014%"
    assert row["domestic_source"] == "https://securities.miraeasset.com/fee"
    assert row["overseas_fee"] == ""
    assert row["overseas_basis"] == ""
    assert row["fx_fee"] == ""
    assert row["fx_basis"] == ""
    assert len(flags) == 2


def test_events_require_official_url_and_explicit_period() -> None:
    brokers = [
        {
            "name": "토스증권",
            "event": "미국주식 수수료 우대 (~2099-12-31)[3]",
            "event_source": "https://corp.tossinvest.com/offer",
        },
        {
            "name": "한국투자증권",
            "event": "환전우대 (~2026-12-31 추정)",
            "event_source": "https://www.truefriend.com/offer",
        },
        {
            "name": "키움증권",
            "event": "신청일로부터 12개월 수수료 우대",
            "event_source": "https://blog.example/offer",
        },
        {
            "name": "삼성증권",
            "event": "미국주식 수수료 우대 (~2026-08-31)",
            "event_source": "https://www.samsungpop.com/offer",
        },
    ]

    flags = _sanitize_events(brokers)

    assert brokers[0]["event"] == "미국주식 수수료 우대 (~2099-12-31)"
    assert brokers[0]["event_source"] == "https://corp.tossinvest.com/offer"
    assert brokers[1]["event"] == ""
    assert brokers[2]["event"] == ""
    assert brokers[3]["event"] == ""
    assert len(flags) == 3


def test_published_citations_are_url_only_and_broker_official() -> None:
    brokers = [
        {
            "name": "NH투자증권",
            "source_url": "https://www.nhsec.com",
            "domestic_source": "",
            "overseas_source": "https://m.nhqv.com/fee",
            "fx_source": "https://card.example/offer",
        }
    ]

    citations = _sanitize_sources(brokers)

    assert citations == ["https://www.nhqv.com", "https://m.nhqv.com/fee"]
    assert all(url.startswith("https://") for url in citations)

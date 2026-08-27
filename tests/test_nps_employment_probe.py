from api.collectors import nps_employment as nps


def _body(name, months):
    return {
        "items": {
            "item": [
                {"wkplNm": f"{name}(주)", "dataCrtYm": month}
                for month in months
            ]
        }
    }


def test_probe_returns_latest_month_common_to_all_probes(monkeypatch):
    docs = {
        "삼성전자(주)": _body("삼성전자", ["202606", "202607"]),
        "현대자동차(주)": _body("현대자동차", ["202606", "202607"]),
        "엘지전자(주)": _body("엘지전자", ["202606", "202607"]),
    }
    monkeypatch.setattr(nps, "_get", lambda op, params, key: docs[params["wkplNm"]])

    assert nps.probe_source_latest_month("test-key") == "202607"


def test_probe_does_not_advance_on_partial_month_release(monkeypatch):
    docs = {
        "삼성전자(주)": _body("삼성전자", ["202606", "202607"]),
        "현대자동차(주)": _body("현대자동차", ["202606"]),
        "엘지전자(주)": _body("엘지전자", ["202606", "202607"]),
    }
    monkeypatch.setattr(nps, "_get", lambda op, params, key: docs[params["wkplNm"]])

    assert nps.probe_source_latest_month("test-key") == "202606"


def test_probe_fails_closed_when_one_probe_is_missing(monkeypatch):
    docs = {
        "삼성전자(주)": _body("삼성전자", ["202607"]),
        "현대자동차(주)": {"items": {}},
        "엘지전자(주)": _body("엘지전자", ["202607"]),
    }
    monkeypatch.setattr(nps, "_get", lambda op, params, key: docs[params["wkplNm"]])

    assert nps.probe_source_latest_month("test-key") is None

from __future__ import annotations

import json

from api.builders import us_quarterly_public_builder as builder


def _point(end: str, value: float, *, fp: str, form: str, annual: bool,
           accn: str = "0001-26-000001", filed: str = "2026-08-01") -> dict:
    return {
        "end": end,
        "fy": 2026,
        "fp": fp,
        "form": form,
        "is_annual": annual,
        "val": value,
        "accn": accn,
        "filed": filed,
    }


def test_one_reported_quarter_is_published_with_evidence():
    end = "2026-06-30"
    doc = {
        "meta": {"cik": 1234},
        "series_quarterly": {
            "revenue": [_point(end, 100, fp="Q2", form="10-Q", annual=False)],
            "net_income": [_point(end, 10, fp="Q2", form="10-Q", annual=False)],
            "total_assets": [_point(end, 200, fp="Q2", form="10-Q", annual=False)],
            "stockholders_equity": [_point(end, 80, fp="Q2", form="10-Q", annual=False)],
            "total_liabilities": [_point(end, 120, fp="Q2", form="10-Q", annual=False)],
        },
    }
    rows = builder._quarters_for(doc)
    assert len(rows) == 1
    row = rows[0]
    assert row["q"] == end
    assert row["fiscal_period"] == "Q2"
    assert row["form"] == "10-Q"
    assert row["filed"] == "2026-08-01"
    assert row["period_kind"] == "reported_quarter"
    assert row["roa"] == 5.0
    assert row["debt_ratio"] == 150.0
    assert "CIK=1234" in row["source_url"]


def test_fiscal_year_end_derives_standalone_q4_and_keeps_10k_evidence():
    prev, end = "2025-06-30", "2026-06-30"
    quarter_ends = (("2025-09-30", "Q1"), ("2025-12-31", "Q2"), ("2026-03-31", "Q3"))
    flow_values = {
        "revenue": (1000, [200, 250, 300]),
        "gross_profit": (400, [80, 100, 120]),
        "operating_income": (200, [30, 40, 50]),
        "net_income": (100, [10, 20, 30]),
    }
    annual = {}
    quarterly = {}
    for key, (fy_value, q_values) in flow_values.items():
        annual[key] = [
            _point(prev, fy_value * 0.8, fp="FY", form="10-K", annual=True),
            _point(end, fy_value, fp="FY", form="10-K", annual=True,
                   accn="0001-26-000099", filed="2026-07-30"),
        ]
        quarterly[key] = [
            _point(q_end, value, fp=fp, form="10-Q", annual=False)
            for (q_end, fp), value in zip(quarter_ends, q_values)
        ]
    for key, value in {
        "total_assets": 1000,
        "current_assets": 300,
        "current_liabilities": 150,
        "total_liabilities": 600,
        "stockholders_equity": 400,
    }.items():
        annual[key] = [
            _point(prev, value * 0.8, fp="FY", form="10-K", annual=True),
            _point(end, value, fp="FY", form="10-K", annual=True,
                   accn="0001-26-000099", filed="2026-07-30"),
        ]
    rows = builder._quarters_for({
        "meta": {"cik": 1234},
        "series_annual": annual,
        "series_quarterly": quarterly,
    })
    q4 = next(row for row in rows if row["q"] == end)
    assert q4["fiscal_period"] == "Q4"
    assert q4["form"] == "10-K"
    assert q4["period_kind"] == "derived_fiscal_q4"
    assert q4["derivation"] == "FY-Q1-Q2-Q3"
    assert set(q4["derived_metrics"]) == set(flow_values)
    assert q4["gross_margin"] == 40.0
    assert q4["operating_margin"] == 32.0
    assert q4["net_margin"] == 16.0
    assert q4["roa"] == 4.0
    assert q4["current_ratio"] == 200.0


def test_incomplete_q1_q2_q3_never_invents_flow_ratio():
    prev, end = "2025-06-30", "2026-06-30"
    annual = {
        "revenue": [_point(prev, 800, fp="FY", form="10-K", annual=True),
                    _point(end, 1000, fp="FY", form="10-K", annual=True)],
        "gross_profit": [_point(prev, 320, fp="FY", form="10-K", annual=True),
                         _point(end, 400, fp="FY", form="10-K", annual=True)],
        "current_assets": [_point(prev, 200, fp="FY", form="10-K", annual=True),
                           _point(end, 300, fp="FY", form="10-K", annual=True)],
        "current_liabilities": [_point(prev, 100, fp="FY", form="10-K", annual=True),
                                _point(end, 150, fp="FY", form="10-K", annual=True)],
    }
    quarterly = {
        key: [_point("2025-09-30", value, fp="Q1", form="10-Q", annual=False),
              _point("2025-12-31", value, fp="Q2", form="10-Q", annual=False)]
        for key, value in {"revenue": 200, "gross_profit": 80}.items()
    }
    rows = builder._quarters_for({"series_annual": annual, "series_quarterly": quarterly})
    year_end = next(row for row in rows if row["q"] == end)
    assert year_end["period_kind"] == "reported_year_end_balance"
    assert year_end["current_ratio"] == 200.0
    assert "gross_margin" not in year_end
    assert "derivation" not in year_end


def test_sticky_merge_preserves_old_metrics_and_adds_new_evidence():
    old = [{"q": "2026-06-30", "roa": 3.0, "gross_margin": 20.0}]
    new = [{"q": "2026-06-30", "roa": 4.0, "form": "10-Q"}]
    assert builder._merge_quarters(old, new) == [{
        "q": "2026-06-30", "roa": 4.0, "gross_margin": 20.0, "form": "10-Q"
    }]


def test_source_url_does_not_guess_registrant_from_accession_prefix():
    url = builder._source_url(2115436, "0000034088-26-000093")
    assert "CIK=2115436" in url


def test_direct_inline_source_url_wins_over_company_page():
    row = _point("2026-06-30", 1, fp="Q2", form="10-Q", annual=False)
    row["source_url"] = "https://www.sec.gov/Archives/edgar/data/1/2/q.htm"
    assert builder._evidence(row, 1234)["source_url"] == row["source_url"]


def test_build_includes_stock_with_only_one_ratio_quarter(tmp_path, monkeypatch):
    fin = tmp_path / "fin"
    fin.mkdir()
    (fin / "XOM.json").write_text(json.dumps({
        "series_quarterly": {
            "revenue": [_point("2026-06-30", 100, fp="Q2", form="10-Q", annual=False)],
            "net_income": [_point("2026-06-30", 10, fp="Q2", form="10-Q", annual=False)],
        }
    }), encoding="utf-8")
    monkeypatch.setattr(builder, "FIN_DIR", str(fin))
    out = builder.build()
    assert out["_meta"]["count"] == 1
    assert out["stocks"]["XOM"]["quarter_count"] == 1
    assert out["stocks"]["XOM"]["trend_ready"] is False

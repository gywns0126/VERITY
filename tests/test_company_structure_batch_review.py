"""Public exhibit layout variants; no source calls or ownership inference."""
import pytest
import json
from pathlib import Path
import yaml

from api.intelligence.company_structure_sec import parse_exhibit, find_exhibit
from api.collectors.company_structure_us_refresh import latest_metadata

META = {"cik": "0000004904", "accession": "0000004904-26-000018",
        "filedDate": "2026-02-12", "periodEnd": "2025-12-31",
        "url": "https://www.sec.gov/Archives/edgar/data/4904/000000490426000018/ex21.htm",
        "issuerName": "American Electric Power Company, Inc."}

CBT_META = {"cik": "0000016040", "accession": "0001193125-25-292412",
            "filedDate": "2025-11-24", "periodEnd": "2025-09-30",
            "url": "https://www.sec.gov/Archives/edgar/data/16040/000119312525292412/cbt-ex21.htm",
            "issuerName": "Cabot Corp"}


def cbt_table(name, *, name_header="Subsidiary", jurisdiction_header="State/Jurisdiction of Incorporation",
              jurisdiction="Delaware"):
    return (f"<table><tr><td>{name_header}</td><td>{jurisdiction_header}</td></tr>"
            f"<tr><td>{name}</td><td>{jurisdiction}</td></tr></table>")


def cbt_three_tables(*, title="Exhibit 21 Subsidiaries of Cabot Corporation (as of September 30, 2025)*",
                     first_gap="Exhibit 21", second_gap="Exhibit 21", second_header="Subsidiary",
                     third_row="Cabot Specialty Fluids LLC"):
    return (f"<p>{title}</p>"
            + cbt_table("Cabot Holdings LLC")
            + f"<p>{first_gap}</p>"
            + cbt_table("Cabot International LLC", name_header=second_header)
            + f"<p>{second_gap}</p>"
            + cbt_table(third_row))


def table(header, jurisdiction="Location of Incorporation"):
    return (f"<table><tr><td>{header}</td><td></td><td>{jurisdiction}</td></tr>"
            "<tr><td>Parent Holdings LLC</td><td></td><td>Delaware</td></tr>"
            "<tr><td style='padding-left:30px'>Indirect Company, Inc.</td><td></td><td>Ohio</td></tr></table>")


@pytest.mark.parametrize("header", ["Name of Company", "Name of Entity", "Entity"])
def test_explicit_entity_headers_preserve_indirect_scope(header):
    # AEP uses Name of Company + Location of Incorporation and indentation to
    # describe intermediate parents. Never infer direct ownership from layout.
    html = ("<p>Subsidiaries of American Electric Power Company, Inc. As of December 31, 2025</p>"
            "<p>Each company shown indented is a subsidiary of the company immediately above.</p>" + table(header))
    result = parse_exhibit(html, META)
    assert result["status"] == "parsed"
    assert [r["name"] for r in result["rows"]] == ["Parent Holdings LLC", "Indirect Company, Inc."]
    assert all(r["ownershipPct"] is None and r["directOwnership"] == "unspecified" for r in result["rows"])


@pytest.mark.parametrize("header", ["Name of Customer", "Name of Supplier", "Doing Business As"])
def test_other_parties_and_trade_names_do_not_become_legal_entities(header):
    result = parse_exhibit(table(header), META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "explicit-name-jurisdiction-header-missing"
    assert result["rows"] == []


@pytest.mark.parametrize("html,reason", [
    ("<p>Variable interest entities</p>", "vie-scope-needs-review"),
    (table("Name of Company", "Country"), "explicit-name-jurisdiction-header-missing"),
    (table("Name") + table("Name"), "multiple-tables-issuer-scope-unbound"),
    ("<p>As of January 1, 2026</p>" + table("Name"), "exhibit-as-of-differs-from-period-end"),
    (table("Name").replace("<td>Ohio</td>", ""), "ambiguous-row-binding"),
])
def test_batch_review_has_actionable_reasons_without_promotion(html, reason):
    result = parse_exhibit(html, META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == reason


@pytest.mark.parametrize("issuer_name,title_name", [
    ("Cabot Corp", "Cabot Corporation"),
    ("Cabot Corporation", "Cabot Corp"),
])
def test_cbt_title_binds_only_terminal_corp_corporation(issuer_name, title_name):
    html = cbt_three_tables(title=f"Exhibit 21 Subsidiaries of {title_name} (as of September 30, 2025)*")
    result = parse_exhibit(html, {**CBT_META, "issuerName": issuer_name})
    assert result["status"] == "parsed"
    assert [row["name"] for row in result["rows"]] == [
        "Cabot Holdings LLC", "Cabot International LLC", "Cabot Specialty Fluids LLC"]
    assert [row["sourceRow"]["tableIndex"] for row in result["rows"]] == [0, 1, 2]
    assert all(row["ownershipPct"] is None and row["directOwnership"] == "unspecified"
               for row in result["rows"])


@pytest.mark.parametrize("marker", ["Exhibit 21", "Exhibit 21.1"])
def test_cbt_three_tables_allow_only_matching_repeated_exhibit_marker(marker):
    html = cbt_three_tables(title=f"{marker} Subsidiaries of Cabot Corporation (as of September 30, 2025)*",
                            first_gap=marker, second_gap=marker)
    result = parse_exhibit(html, CBT_META)
    assert result["status"] == "parsed"
    assert len(result["rows"]) == 3


@pytest.mark.parametrize("changes,reason", [
    ({"title": "Exhibit 21 Subsidiaries of Another Corporation (as of September 30, 2025)*"},
     "multiple-tables-issuer-scope-unbound"),
    ({"title": "Exhibit 21 Former Subsidiaries of Cabot Corporation (as of September 30, 2025)*"},
     "multiple-tables-issuer-scope-unbound"),
    ({"first_gap": "Exhibit 8"}, "continuation-scope-text"),
    ({"first_gap": "Exhibit 21 additional subsidiaries"}, "continuation-scope-text"),
    ({"title": "Subsidiaries of Cabot Corporation (as of September 30, 2025)*"},
     "continuation-scope-text"),
    ({"first_gap": "Exhibit 21.1"}, "continuation-scope-text"),
    ({"second_header": "Company Name"}, "continuation-headers-differ"),
    ({"title": "Exhibit 21 Subsidiaries of Cabot Corporation (as of September 30, 2024)*"},
     "exhibit-as-of-differs-from-period-end"),
    ({"third_row": "Cabot Specialty Fluids LLC<br>Unbound Name LLC"}, "ambiguous-row-binding"),
    ({"third_row": "Cabot Corporation Foundation, Inc."}, "ambiguous-row-binding"),
    ({"third_row": "Energy Transport Limited LLC"}, "ambiguous-row-binding"),
])
def test_cbt_near_misses_remain_held(changes, reason):
    result = parse_exhibit(cbt_three_tables(**changes), CBT_META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == reason


def test_newer_40f_blocks_fallback_to_historical_20f_paper():
    data = {"cik": 756894, "tickers": ["B"], "name": "Barrick Mining Corp",
            "filings": {"recent": {"form": ["40-F", "20-F"],
                "filingDate": ["2026-03-13", "2002-04-01"],
                "reportDate": ["2025-12-31", "2001-12-31"],
                "accessionNumber": ["0000756894-26-000001", "9999999997-02-026337"],
                "primaryDocument": ["annual.htm", "9999999997-02-026337.paper"]}}}
    with pytest.raises(ValueError, match="source-gap:annual-form-40f-needs-review"):
        latest_metadata("B", "0000756894", data)
    for field in data["filings"]["recent"].values():
        del field[0]
    with pytest.raises(ValueError, match="source-gap:annual-paper-document"):
        latest_metadata("B", "0000756894", data)


@pytest.mark.parametrize("cik,accession,archive_cik", [
    ("0000066901", "0000065984-26-000174", "7323"),
    ("0000072741", "0001628280-26-008461", "13372"),
    ("0000715957", "0001193125-26-063120", "103682"),
    ("0000788784", "0001193125-26-077446", "81033"),
])
def test_shared_filing_does_not_prove_the_exhibit_belongs_to_each_issuer(cik, accession, archive_cik):
    url = f"https://www.sec.gov/Archives/edgar/data/{archive_cik}/{accession.replace('-', '')}/ex21.htm"
    index = ("<table class='tableFile'><tr><th>Document</th><th>Type</th></tr>"
             f"<tr><td><a href='{url}'>ex21.htm</a></td><td>EX-21</td></tr></table>")
    with pytest.raises(ValueError, match="sec-cofiler-issuer-needs-review"):
        find_exhibit(index, cik=cik, accession=accession)


@pytest.mark.parametrize("replay_outcome,cache_outcome,should_fail", [("failure", "success", True), ("success", "failure", True), ("success", "success", False)])
def test_cache_replay_failure_is_reported_without_blocking_other_collectors(tmp_path, monkeypatch, replay_outcome, cache_outcome, should_fail):
    workflow = yaml.safe_load((Path(__file__).resolve().parents[1] / '.github/workflows/ownership_backfill.yml').read_text())
    steps = workflow['jobs']['backfill']['steps']
    by_id = {s['id']: s for s in steps if 'id' in s}
    assert by_id['us-replay']['continue-on-error'] is True
    assert by_id['sec-raw-cache']['continue-on-error'] is True
    assert steps.index(by_id['sec-raw-cache']) < steps.index(by_id['us-replay']) < steps.index(by_id['us'])
    report = next(s for s in steps if s.get('name') == 'Report collection failures after durable checkpoint')
    assert "steps.us-replay.outcome == 'failure'" in report['if']
    assert "steps.sec-raw-cache.outcome == 'failure'" in report['if']
    # A normal HTTP budget deferral cannot erase an independent replay failure.
    (tmp_path / 'company-structure-run-status.json').write_text(json.dumps({'US': {'normalDeferred': True}}))
    for key, value in {'RUNNER_TEMP': str(tmp_path), 'KR_OUTCOME': 'success',
                       'US_OUTCOME': 'failure', 'US_REPLAY_OUTCOME': replay_outcome,
                       'SEC_CACHE_OUTCOME': cache_outcome}.items():
        monkeypatch.setenv(key, value)
    code = report['run'].split("python - <<'PY'\n")[1].rsplit('\nPY', 1)[0]
    if should_fail:
        with pytest.raises(SystemExit) as exc:
            exec(code, {})
        assert exc.value.code == 1
    else:
        exec(code, {})

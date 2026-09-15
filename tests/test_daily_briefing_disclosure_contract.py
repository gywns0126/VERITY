"""The home card must carry the actual filing title, not the DART category."""
import json
from api.builders import daily_briefing_builder as builder


def build(tmp_path, monkeypatch, rows):
    source = tmp_path / "events.jsonl"
    source.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    monkeypatch.setattr(builder, "CATALYST_PATH", str(source))
    return builder._sec_disclosures()


def filing(receipt="20260914000433", **overrides):
    return {"ticker": "206400", "name": "테스트 기업", "rcept_no": receipt,
            "rcept_dt": "20260914", "report_nm": "[기재정정]주요사항보고서(전환사채권발행결정)",
            "pblntf_label": "주요사항보고", "is_correction": True, **overrides}


def test_source_title_date_correction_survive(tmp_path, monkeypatch):
    row = filing()
    item = build(tmp_path, monkeypatch, [row])["items"][0]
    assert item["text"] == item["title"] == row["report_nm"]
    assert item["label"] == "주요사항보고"
    assert item["date"] == "2026-09-14"
    assert item["is_correction"] is True
    assert item["url"].endswith(row["rcept_no"])
    assert "severity" not in item and "amount" not in item


def test_same_company_category_keeps_distinct_receipts(tmp_path, monkeypatch):
    rows = [filing(), filing("20260914000434"), filing()]
    items = build(tmp_path, monkeypatch, rows)["items"]
    assert len(items) == 2
    assert items[0]["url"].endswith("20260914000434")


def test_missing_title_is_not_replaced_by_category(tmp_path, monkeypatch):
    item = build(tmp_path, monkeypatch, [filing(report_nm="")])["items"][0]
    assert item["title"] == ""
    assert item["text"] == "공시 제목 미제공"


def test_invalid_rows_cannot_hide_valid_date(tmp_path, monkeypatch):
    rows = [None, [], "bad", filing(rcept_dt="99999999"), filing(rcept_dt="20260230"),
            filing(ticker="ORCL"), filing(rcept_no="bad"), filing()]
    assert len(build(tmp_path, monkeypatch, rows)["items"]) == 1


def test_latest_day_and_limit_only(tmp_path, monkeypatch):
    rows = [filing(f"2026091400{i:04d}") for i in range(20)]
    rows += [filing("20260913000433", rcept_dt="20260913")]
    result = build(tmp_path, monkeypatch, rows)
    assert len(result["items"]) == 8
    assert all(i["date"] == "2026-09-14" for i in result["items"])


def test_empty_has_no_demo_rows(tmp_path, monkeypatch):
    assert build(tmp_path, monkeypatch, [])['items'] == []

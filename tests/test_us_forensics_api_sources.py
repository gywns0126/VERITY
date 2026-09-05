from pathlib import Path


API = Path("vercel-api/api/us_forensics.py")


def test_us_forensics_serves_form144_with_existing_fact_sources():
    body = API.read_text(encoding="utf-8")
    assert '"form144": "us_form144.json"' in body
    assert "6 소스 병렬 fetch" in body
    assert "form144" in body[body.index('"sections"'):]


def test_us_forensics_exposes_record_state_and_dynamic_coverage():
    body = API.read_text(encoding="utf-8")
    assert '"data_state": data_state' in body
    assert '"source_connected_n": ok_n' in body
    assert '"source_total_n": len(SOURCES)' in body
    assert '"record_present_n": present_n' in body
    assert 'data_state = entry.get("event_state") or "unknown"' in body

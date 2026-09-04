from pathlib import Path


API = Path("vercel-api/api/us_forensics.py")


def test_us_forensics_serves_form144_with_existing_fact_sources():
    body = API.read_text(encoding="utf-8")
    assert '"form144": "us_form144.json"' in body
    assert "6 소스 병렬 fetch" in body
    assert "form144" in body[body.index('"sections"'):]

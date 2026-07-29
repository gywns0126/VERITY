"""13F value 단위 정규화 + infotable 확장자 대소문자 — 2026-07-30 실사고 2건.

① 단위: 기존 코드는 "2023+ 는 전부 실달러"를 전역 가정으로 뒀다(주석 "×1000 폐기 —
   2026-06-22 ALLY $39/주 검증"). 그 검증은 filer 1곳 표본이었고, 실제로는 개정 후에도
   천 달러 단위로 계속 제출하는 filer 가 있다.
   실측(15 filer 전수 중앙 단가): Duquesne $0.08 ← 유일 이상치 / 나머지 14곳 $73~$310.
   보정 전 Duquesne 총액 $2.9M(실제 $2.94B) — TSM 을 $0.34 로 표기(실제 ~$340).

② 확장자: Viking Global 은 'MSFS13F033126.XML'(대문자) 제출 → endswith('.xml') 이 놓쳐
   보유 파싱 0건이었다. 실측 수정 후 77종목 $35.75B.
"""
from api.collectors.sec_13f_collector import _normalize_value_units


def _rows(prices, shares=1000):
    return [{"cusip": f"C{i}", "shares": shares, "value_usd": p * shares}
            for i, p in enumerate(prices)]


def test_thousand_unit_filer_scaled():
    """중앙 단가 $1 미만 = 천 달러 단위 → ×1000."""
    rows = _normalize_value_units(_rows([0.09, 0.12, 0.08, 0.25]), cik="1536411")
    assert all(r.get("value_unit_corrected") for r in rows)
    px = [r["value_usd"] / r["shares"] for r in rows]
    assert 80 <= sorted(px)[len(px) // 2] <= 130


def test_dollar_unit_filer_untouched():
    """정상 단위는 건드리지 않음 — 회귀 0 (Berkshire 대조군)."""
    orig = _rows([253.79, 302.48, 76.05, 91.64])
    before = [r["value_usd"] for r in orig]
    rows = _normalize_value_units(orig, cik="1067983")
    assert [r["value_usd"] for r in rows] == before
    assert not any(r.get("value_unit_corrected") for r in rows)


def test_small_sample_holds_judgment():
    """표본 3건 미만이면 판정 보류 — 조용히 틀린 보정 금지."""
    rows = _normalize_value_units(_rows([0.05, 0.06]), cik="X")
    assert not any(r.get("value_unit_corrected") for r in rows)


def test_absurd_after_scaling_not_corrected():
    """×1000 후에도 상식 밖이면 보정 보류 (양방향 오판 방지)."""
    rows = _normalize_value_units(_rows([0.0000001] * 5), cik="X")
    assert not any(r.get("value_unit_corrected") for r in rows)


def test_median_resists_penny_outliers():
    """페니스톡 몇 종목으로 뒤집히지 않음 — 중앙값 기반."""
    rows = _normalize_value_units(_rows([0.3, 0.5, 120.0, 250.0, 310.0]), cik="X")
    assert not any(r.get("value_unit_corrected") for r in rows)


def test_zero_shares_ignored_in_detection():
    """shares 0 행이 판정을 깨지 않음."""
    rows = _rows([120.0, 250.0, 310.0]) + [{"cusip": "Z", "shares": 0, "value_usd": 500}]
    out = _normalize_value_units(rows, cik="X")
    assert not any(r.get("value_unit_corrected") for r in out)


def test_infotable_extension_case_insensitive(monkeypatch):
    """대문자 .XML 도 잡아야 함 (Viking Global 실사고)."""
    import api.collectors.sec_13f_collector as C

    class _R:
        @staticmethod
        def json():
            return {"directory": {"item": [
                {"name": "primary_doc.xml", "size": "2065"},
                {"name": "MSFS13F033126.XML", "size": "42107"},
            ]}}

    monkeypatch.setattr(C.requests, "get", lambda *a, **k: _R())
    url = C._find_infotable_url("1103804", "0001103804-26-000004")
    assert url and url.endswith("MSFS13F033126.XML")


def test_primary_doc_excluded_case_insensitive(monkeypatch):
    """대문자 PRIMARY_DOC.XML 도 보유 테이블로 오인하지 않음."""
    import api.collectors.sec_13f_collector as C

    class _R:
        @staticmethod
        def json():
            return {"directory": {"item": [
                {"name": "PRIMARY_DOC.XML", "size": "999999"},
                {"name": "holdings.xml", "size": "1000"},
            ]}}

    monkeypatch.setattr(C.requests, "get", lambda *a, **k: _R())
    url = C._find_infotable_url("1", "0001-26-000001")
    assert url.endswith("holdings.xml")

"""
KRX 신규상장(IPO) collector — parse / aggregate 검증 (네트워크 없음).
[[project_new_listings_collector_2026_06_07]].
"""
from __future__ import annotations

from datetime import datetime


def _row(cells):
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


SAMPLE_HTML = "<table>" + "".join([
    # 종목명, 신규상장일, 현재가, 전일대비, 공모가, 현재수익률, 시초가, 시초수익률, 첫날고가
    _row(["마키나락스", "2026/05/20", "26,700", "0.95%", "15,000", "78%", "60,000", "300%", "60,000"]),
    _row(["폴레드", "2026/05/14", "4,325", "-1.14%", "5,000", "-13.5%", "20,000", "300%", "20,000"]),
    # SPAC — 제외 대상
    _row(["대신밸런스스팩20호", "2026/06/05", "1,984", "0.00%", "2,000", "-0.8%", "6,200", "210%", "-"]),
    # 예정/미상장 — 시초수익률 파싱 불가 → 제외
    _row(["져스텍", "2026/06/29", "-", "%", "-", "-%", "-", "%", "예정"]),
    _row(["채비", "2026/04/29", "9,010", "-11.06%", "12,300", "-26.75%", "15,250", "23.98%", "22,550"]),
]) + "</table>"


def test_parse_rows_basic():
    from api.collectors.krx_ipo_collector import parse_rows
    rows = parse_rows(SAMPLE_HTML)
    names = {r["name"] for r in rows}
    # 예정(져스텍)은 제외, 나머지 4건 (SPAC 은 파싱하되 flag)
    assert "져스텍" not in names
    assert names == {"마키나락스", "폴레드", "대신밸런스스팩20호", "채비"}
    mk = next(r for r in rows if r["name"] == "마키나락스")
    assert mk["offer_price"] == 15000
    assert mk["first_day_return_pct"] == 300.0
    assert mk["listing_date"] == "2026-05-20"
    assert mk["is_spac"] is False
    spac = next(r for r in rows if "스팩" in r["name"])
    assert spac["is_spac"] is True
    # 시초수익률(c[7]) 을 쓴다 — 현재수익률(c[5]) 아님
    pl = next(r for r in rows if r["name"] == "폴레드")
    assert pl["first_day_return_pct"] == 300.0  # 시초 +300%, 현재가 -13.5% 아님


def test_aggregate_excludes_spac_and_regime_bounds():
    from api.collectors.krx_ipo_collector import aggregate
    asof = datetime(2026, 6, 7, 21, 0, 0)
    records = [
        # recent (직전 90일, 비-SPAC)
        {"name": "A", "listing_date": "2026-05-20", "offer_price": 10000, "first_day_return_pct": 300.0, "is_spac": False},
        {"name": "B", "listing_date": "2026-05-01", "offer_price": 10000, "first_day_return_pct": 100.0, "is_spac": False},
        # SPAC recent — 제외돼야
        {"name": "S스팩", "listing_date": "2026-05-10", "offer_price": 2000, "first_day_return_pct": 200.0, "is_spac": True},
        # baseline post-regime (2024)
        {"name": "C", "listing_date": "2024-09-01", "offer_price": 10000, "first_day_return_pct": 80.0, "is_spac": False},
        {"name": "D", "listing_date": "2024-03-01", "offer_price": 10000, "first_day_return_pct": 60.0, "is_spac": False},
        # baseline pre-regime (2022) — count 엔 포함, return baseline 엔 제외
        {"name": "E", "listing_date": "2022-01-15", "offer_price": 10000, "first_day_return_pct": 30.0, "is_spac": False},
    ]
    out = aggregate(records, asof)
    assert out["recent_3m_count"] == 2  # A, B (S스팩 제외)
    assert out["recent_3m_avg_first_day_pct"] == 200.0  # (300+100)/2
    # pre-regime E 의 30% 는 return baseline 평균에 안 들어감 (C,D 만)
    assert out["baseline_5y_first_day_pct"] == 70.0  # (80+60)/2
    # count baseline 은 5년 전체 윈도 평균 (E 포함)
    assert out["_meta"]["spac_excluded"] is True
    assert out["_meta"]["return_baseline_regime_start"] == "2023-06-26"


def test_aggregate_empty_recent():
    from api.collectors.krx_ipo_collector import aggregate
    asof = datetime(2026, 6, 7)
    out = aggregate([], asof)
    assert out["recent_3m_count"] == 0
    assert out["recent_3m_avg_first_day_pct"] is None

"""BIS Real Estate Price Statistics — 한국 실질 RPPI 어댑터 (50y backbone).

Source: FRED `QKRR628BIS` (BIS Real Residential Property Prices for Republic of Korea)
URL: https://fred.stlouisfed.org/series/QKRR628BIS/downloaddata/QKRR628BIS.csv

특성 (Perplexity 2026-05-09 호출 1 검증):
  - 시작: 1975Q1 / 최신: 2025Q4 (분기 단위, 50년+)
  - 단위: index, 2010=100 base
  - 명목 vs 실질: FRED 미러 = 실질 (CPI 디플레이트). 명목은 BIS 원본 별도.
  - 권역: 전국 only (서울/지방 분리 X — KOSIS-KB 보강 필요)
  - 인증: 무인증 / 무료

CSV 응답 형식:
  DATE,QKRR628BIS
  1975-01-01,33.6504
  1975-04-01,...

서브 region 부재 — estate_brain_backtest_50y_builder 가 KOSIS-KB 와 cross-source.
feedback_macro_timestamp_policy 정합: collected_at + as_of 동시 노출.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

_logger = logging.getLogger(__name__)

FRED_KOREA_REAL_RPPI_URL = (
    "https://fred.stlouisfed.org/series/QKRR628BIS/downloaddata/QKRR628BIS.csv"
)
SERIES_ID = "QKRR628BIS"
TIMEOUT_SEC = 30


def _kst_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def _date_to_quarter(date_str: str) -> Optional[str]:
    """YYYY-MM-DD → YYYYQN (예: 2025-10-01 → 2025Q4)."""
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
        q = (dt.month - 1) // 3 + 1
        return f"{dt.year}Q{q}"
    except (ValueError, AttributeError):
        return None


def fetch_bis_korea_real_rppi(
    timeout: float = TIMEOUT_SEC,
) -> Optional[dict]:
    """BIS 한국 실질 주택가격지수 시계열 fetch.

    Returns:
      {
        "series": [{"date": "YYYY-MM-DD", "quarter": "YYYYQN", "index": float}, ...]
                  (시간 오름차순)
        "as_of": "YYYYQN", "as_of_date": "YYYY-MM-DD",
        "collected_at": "...",
        "source": "fred_bis_korea_real_rppi",
        "series_id": "QKRR628BIS",
        "unit": "index_2010_100_real",
      }
      None → 네트워크 실패 / 빈 응답 / 파싱 실패
    """
    try:
        r = requests.get(FRED_KOREA_REAL_RPPI_URL, timeout=timeout)
        r.raise_for_status()
        body = r.text
    except requests.RequestException as e:
        _logger.warning("BIS FRED fetch 실패: %s", e)
        return None

    series: list[dict] = []
    try:
        reader = csv.DictReader(io.StringIO(body))
        for row in reader:
            date_str = (row.get("DATE") or "").strip()
            val_str = (row.get(SERIES_ID) or "").strip()
            if not date_str or not val_str or val_str == ".":
                continue
            try:
                val = float(val_str)
            except (ValueError, TypeError):
                continue
            quarter = _date_to_quarter(date_str)
            if not quarter:
                continue
            series.append({"date": date_str, "quarter": quarter, "index": val})
    except (csv.Error, ValueError) as e:
        _logger.warning("BIS csv parse 실패: %s — head=%s", e, body[:200])
        return None

    if not series:
        _logger.warning("BIS 빈 시계열 — body head=%s", body[:200])
        return None

    series.sort(key=lambda x: x["date"])
    last = series[-1]
    return {
        "series": series,
        "as_of": last["quarter"],
        "as_of_date": last["date"],
        "collected_at": _kst_now().isoformat(timespec="seconds"),
        "source": "fred_bis_korea_real_rppi",
        "series_id": SERIES_ID,
        "unit": "index_2010_100_real",
        "n_points": len(series),
    }

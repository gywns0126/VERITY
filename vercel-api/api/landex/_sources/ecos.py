"""한국은행 ECOS API 어댑터 — LANDEX R(Risk) 입력.

API: http://ecos.bok.or.kr/api/StatisticSearch/{KEY}/json/kr/{start}/{count}/{stat_code}/{cycle}/{date_from}/{date_to}/[item1]
응답: { StatisticSearch: { list_total_count, row: [...] } } 또는 { RESULT: { CODE, MESSAGE } }

추출 통계:
  - 한국은행 기준금리 (722Y001) — 'M' 월별
  - 통화량 M2 (101Y014) — 'M' 월별 (선택, v1.5)

R 점수 산출 입력:
  - 기준금리 절대값 (낮을수록 가산점)
  - 최근 6개월 변화율 (상승 추세 → R 위험 상승)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

_logger = logging.getLogger(__name__)

ECOS_BASE = "https://ecos.bok.or.kr/api"

# ECOS 통계코드
STAT_BASE_RATE = "722Y001"   # 한국은행 기준금리
ITEM_BASE_RATE = "0101000"   # 한국은행 기준금리 (단일 항목)


def _api_key() -> str:
    return os.environ.get("ECOS_API_KEY", "").strip()


def fetch_base_rate(months_back: int = 12, signal_timeout: float = 8.0) -> Optional[list[dict]]:
    """최근 N개월 한국은행 기준금리 시계열.

    Returns: [{ "yyyymm": "202604", "rate": 3.50 }, ...] (오래된 순)
             None → API 키 미설정 또는 호출 실패
    """
    key = _api_key()
    if not key:
        _logger.warning("ECOS_API_KEY 미설정")
        return None

    # 종료월 = 현재 (YYYYMM), 시작월 = 종료 - months_back
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone(timedelta(hours=9)))  # KST
    end = now.strftime("%Y%m")
    start_dt = now - timedelta(days=31 * months_back)
    start = start_dt.strftime("%Y%m")

    url = (
        f"{ECOS_BASE}/StatisticSearch/{key}/json/kr/1/100/"
        f"{STAT_BASE_RATE}/M/{start}/{end}/{ITEM_BASE_RATE}"
    )

    try:
        r = requests.get(url, timeout=signal_timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _logger.warning("ECOS fetch 실패: %s", e)
        return None

    # ECOS 에러 응답 처리
    if "RESULT" in data and data["RESULT"].get("CODE") not in (None, "INFO-000"):
        _logger.warning("ECOS error: %s", data["RESULT"])
        return None

    rows = (data.get("StatisticSearch") or {}).get("row") or []
    out = []
    for row in rows:
        try:
            yyyymm = row.get("TIME", "").strip()
            val = float(row.get("DATA_VALUE", "").strip())
            out.append({"yyyymm": yyyymm, "rate": val})
        except (ValueError, AttributeError):
            continue
    out.sort(key=lambda x: x["yyyymm"])
    return out


def compute_risk_score(rate_series: list[dict]) -> Optional[float]:
    """기준금리 시계열 → R 위험 점수 (0~100, 낮을수록 위험 큼).

    로직:
      - 최근 금리가 5%↑ 이면 위험 큼 → R 낮음
      - 최근 6개월간 상승 → R 더 낮음
      - 안정·하락 추세 → R 높음

    반환은 'inverted 후' 점수 — 호출자(_compute.compute_landex)가 그대로 가중합 사용.
    """
    if not rate_series or len(rate_series) < 2:
        return None

    latest = rate_series[-1]["rate"]
    earliest = rate_series[0]["rate"]
    delta = latest - earliest

    # 1) 절대 수준 점수 (0% = 100점, 6%↑ = 0점, 선형)
    level_score = max(0.0, min(100.0, 100 - (latest / 6.0) * 100))

    # 2) 추세 보정 (상승 = 감점, 하락 = 가산)
    trend_adj = -delta * 10  # delta=+0.5 → -5점, delta=-0.5 → +5점
    score = max(0.0, min(100.0, level_score + trend_adj))
    return round(score, 1)

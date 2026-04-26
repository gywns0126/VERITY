"""서울시 지하철 데이터 어댑터 — LANDEX C(Convenience) 입력.

서울 열린데이터광장 (별도 지하철 키 SEOUL_SUBWAY_API_KEY 사용)
API: http://openapi.seoul.go.kr:8088/{KEY}/json/{서비스명}/{startIdx}/{endIdx}/[추가파라미터]

사용 서비스:
  - cardSubwayStatsNew: 일별 역별 승하차 인원 (출퇴근 인구 흐름)
    https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do
  - SearchInfoBySubwayNameService 또는 station 정보:
    역 위치는 별도 csv (행정안전부) 사용 권장 — API 별 위치 응답 차이 큼

C 점수 산출 입력:
  - 구별 역 개수 (subway_proximity 비례)
  - 구별 평일 평균 승하차 합 (workplace_accessibility)
  - 구별 환승역 개수 (인프라 다중성)

v1: 카드 승하차 데이터로 출퇴근 점수 산출. 역 위치 매핑은 정적 테이블 사용.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from ._lawd import SEOUL_25_GU

_logger = logging.getLogger(__name__)

SEOUL_BASE = "http://openapi.seoul.go.kr:8088"


def _api_key() -> str:
    return os.environ.get("SEOUL_SUBWAY_API_KEY", "").strip()


# ── 정적 매핑: 서울 지하철 주요역 → 자치구 ──
# v1: 환승·주요역 위주. 전체 역(약 300개)는 v1.5에서 csv 자동 로드.
# 출처: 서울교통공사 노선도, https://data.seoul.go.kr/dataList/OA-12251/F/1/datasetView.do
STATION_TO_GU: dict[str, str] = {
    # 강남
    "강남": "강남구", "역삼": "강남구", "선릉": "강남구", "삼성": "강남구",
    "압구정": "강남구", "신논현": "강남구", "논현": "강남구", "양재": "서초구",
    "교대": "서초구", "고속터미널": "서초구", "잠실": "송파구", "잠실새내": "송파구",
    "잠실나루": "송파구", "석촌": "송파구", "가락시장": "송파구",
    # 강북·도심
    "종로3가": "종로구", "종각": "종로구", "혜화": "종로구",
    "시청": "중구", "을지로입구": "중구", "을지로3가": "중구", "충무로": "중구",
    "동대문": "종로구", "동대문역사문화공원": "중구",
    # 한강 이북 주요
    "광화문": "종로구", "서울역": "용산구", "용산": "용산구", "이태원": "용산구",
    "한강진": "용산구", "녹사평": "용산구",
    # 마포·서대문
    "홍대입구": "마포구", "합정": "마포구", "공덕": "마포구", "마포": "마포구",
    "신촌": "서대문구", "이대": "서대문구", "충정로": "서대문구",
    # 동북부
    "성수": "성동구", "왕십리": "성동구", "한양대": "성동구", "건대입구": "광진구",
    "강변": "광진구", "구의": "광진구",
    # 서남부
    "여의도": "영등포구", "당산": "영등포구", "영등포": "영등포구",
    "신도림": "구로구", "구로": "구로구",
    "사당": "동작구", "이수": "동작구", "노량진": "동작구",
    # 양천·강서
    "목동": "양천구", "오목교": "양천구", "신정": "양천구",
    "김포공항": "강서구", "마곡": "강서구", "발산": "강서구",
    # 관악
    "신림": "관악구", "서울대입구": "관악구",
    # 강동
    "천호": "강동구", "강동": "강동구",
    # 성북·동대문
    "성신여대입구": "성북구", "한성대입구": "성북구", "고려대": "성북구",
    "회기": "동대문구", "외대앞": "동대문구",
    # 노원·도봉·강북
    "노원": "노원구", "상계": "노원구", "창동": "도봉구", "수유": "강북구",
    # 은평
    "연신내": "은평구", "불광": "은평구",
    # 중랑·금천
    "상봉": "중랑구", "면목": "중랑구",
    "독산": "금천구", "가산디지털단지": "금천구",
}


def fetch_card_stats_recent(start_idx: int = 1, end_idx: int = 1000, timeout: float = 10.0) -> Optional[list[dict]]:
    """최근 카드 승하차 통계 (서비스명: CardSubwayStatsNew).

    응답: { CardSubwayStatsNew: { list_total_count, RESULT, row: [...] } }
    row 항목: USE_DT, LINE_NUM, SUB_STA_NM, RIDE_PASGR_NUM, ALIGHT_PASGR_NUM, WORK_DT
    """
    key = _api_key()
    if not key:
        _logger.warning("SEOUL_SUBWAY_API_KEY 미설정")
        return None

    url = f"{SEOUL_BASE}/{key}/json/CardSubwayStatsNew/{start_idx}/{end_idx}/"
    r = None
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        body_snip = ""
        try:
            if r is not None:
                body_snip = r.text[:400].replace("\n", " ")
        except Exception:
            pass
        _logger.warning("Seoul subway fetch 실패: %s | body=%s", e, body_snip)
        return None

    payload = data.get("CardSubwayStatsNew") or {}
    result = payload.get("RESULT") or {}
    if result.get("CODE") and result["CODE"] != "INFO-000":
        _logger.warning("Seoul subway error: %s | full=%s", result, str(data)[:400])
        return None

    rows = payload.get("row") or []
    if not rows:
        # 응답에 row 가 없는데 에러 코드도 없는 경우 — 전체 응답 일부 노출
        _logger.warning("Seoul subway empty rows | full=%s", str(data)[:400])
    out = []
    for row in rows:
        try:
            station = (row.get("SUB_STA_NM") or "").strip()
            ride = int(row.get("RIDE_PASGR_NUM") or 0)
            alight = int(row.get("ALIGHT_PASGR_NUM") or 0)
            out.append({
                "use_dt": row.get("USE_DT", ""),
                "line": row.get("LINE_NUM", ""),
                "station": station,
                "ride": ride,
                "alight": alight,
                "total": ride + alight,
                "gu": STATION_TO_GU.get(station),  # 매핑 없으면 None
            })
        except (ValueError, TypeError):
            continue
    return out


def aggregate_by_gu(rows: list[dict]) -> dict[str, dict]:
    """역별 통계 → 구별 합계.

    Returns: { "강남구": { "stations": N, "daily_passengers_avg": ..., "lines": {...} } }
    """
    by_gu: dict[str, dict] = {gu: {
        "stations": set(), "lines": set(),
        "passenger_sum": 0, "days": set(),
    } for gu in SEOUL_25_GU}

    for r in rows:
        gu = r.get("gu")
        if not gu or gu not in by_gu:
            continue
        by_gu[gu]["stations"].add(r["station"])
        by_gu[gu]["lines"].add(r["line"])
        by_gu[gu]["passenger_sum"] += r["total"]
        if r.get("use_dt"):
            by_gu[gu]["days"].add(r["use_dt"])

    out = {}
    for gu, d in by_gu.items():
        n_days = max(1, len(d["days"]))
        out[gu] = {
            "stations": len(d["stations"]),
            "lines": len(d["lines"]),
            "daily_passengers_avg": d["passenger_sum"] / n_days,
        }
    return out


def compute_convenience_scores(by_gu: dict[str, dict]) -> dict[str, float]:
    """구별 통계 → C(Convenience) 점수 0-100.

    배합:
      - subway_proximity = 역 개수 (40%)
      - workplace_accessibility = 일평균 승하차 인원 (40%)
      - line_diversity = 노선 수 (20%)

    각 구를 25구 분포에서 정규화 (Min-Max).
    """
    if not by_gu:
        return {}

    stations_vals = [d["stations"] for d in by_gu.values()]
    pass_vals = [d["daily_passengers_avg"] for d in by_gu.values()]
    line_vals = [d["lines"] for d in by_gu.values()]

    def _norm(v: float, vals: list[float]) -> float:
        lo, hi = min(vals), max(vals)
        if hi <= lo:
            return 50.0
        return ((v - lo) / (hi - lo)) * 100

    out: dict[str, float] = {}
    for gu, d in by_gu.items():
        s_score = _norm(d["stations"], stations_vals)
        p_score = _norm(d["daily_passengers_avg"], pass_vals)
        l_score = _norm(d["lines"], line_vals)
        c = s_score * 0.4 + p_score * 0.4 + l_score * 0.2
        out[gu] = round(c, 1)
    return out

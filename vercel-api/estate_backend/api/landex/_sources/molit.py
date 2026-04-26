"""국토교통부 아파트 실거래가 API 어댑터 — LANDEX V(Value) 입력.

API: https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade
파라미터:
  serviceKey  공공데이터포털 인증키 (URL-decoded 그대로 사용 — requests 가 다시 인코딩)
  LAWD_CD     5자리 법정동 시군구코드 (서울 25구 → _lawd.GU_TO_LAWD)
  DEAL_YMD    조회 월 (YYYYMM)
  pageNo      기본 1
  numOfRows   최대 1000

응답: XML (data.go.kr 표준). 항목 예:
  <item>
    <거래금액>1,250,000</거래금액>           ← 만원 단위, 콤마 포함
    <전용면적>84.97</전용면적>                ← m²
    <건축년도>2015</건축년도>
    <법정동>역삼동</법정동>
    <아파트>래미안</아파트>
    <거래유형>중개거래</거래유형>             ← '직거래' 등 분류
    <등기일자>26.04.20</등기일자>             ← 빈 값이면 미등기
    <년> <월> <일>
  </item>

이상치 필터링은 어댑터 단계에서 1차(룰 기반)만 수행 — 통계/분포 필터는 _compute.py.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional
from xml.etree import ElementTree as ET

import requests

from ._lawd import GU_TO_LAWD, SEOUL_25_GU

_logger = logging.getLogger(__name__)

MOLIT_BASE = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"

# 1차 룰 필터: 제외할 거래유형
EXCLUDED_TRADE_TYPES = {"직거래"}  # 증여·상속은 별도 API라 여기 안 옴


def _api_key() -> str:
    return os.environ.get("PUBLICDATA_API_KEY", "").strip()


def _to_int(s: str, default: int = 0) -> int:
    try:
        return int(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return default


def _to_float(s: str, default: float = 0.0) -> float:
    try:
        return float(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return default


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None else ""


def fetch_apt_trades(
    gu: str,
    yyyymm: str,
    page: int = 1,
    rows: int = 1000,
    timeout: float = 10.0,
) -> Optional[list[dict]]:
    """단일 구·단일 월의 아파트 실거래 조회.

    Returns:
      [{ apt, dong, area_m2, price_won, build_year, trade_type, registered, deal_date }]
      None → 키 미설정/네트워크 실패/잘못된 입력
    """
    key = _api_key()
    if not key:
        _logger.warning("PUBLICDATA_API_KEY 미설정")
        return None

    lawd = GU_TO_LAWD.get(gu.strip())
    if not lawd:
        _logger.warning("Unknown gu: %s", gu)
        return None

    if not re.fullmatch(r"\d{6}", yyyymm):
        _logger.warning("Invalid yyyymm: %s", yyyymm)
        return None

    params = {
        "serviceKey": key,
        "LAWD_CD": lawd,
        "DEAL_YMD": yyyymm,
        "pageNo": str(page),
        "numOfRows": str(rows),
    }
    try:
        r = requests.get(MOLIT_BASE, params=params, timeout=timeout)
        r.raise_for_status()
        body = r.text
    except Exception as e:
        _logger.warning("MOLIT fetch 실패 (%s/%s): %s", gu, yyyymm, e)
        return None

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        _logger.warning("MOLIT XML parse 실패: %s — head=%s", e, body[:200])
        return None

    # 표준 응답: <response><body><items><item>...</item>...</items></body></response>
    # 에러 시: <response><header><resultCode>... 또는 OpenAPI_ServiceResponse XML
    items = root.findall(".//item")
    out = []
    for it in items:
        price_man = _to_int(_text(it, "거래금액"))  # 만원
        if price_man <= 0:
            continue
        area_m2 = _to_float(_text(it, "전용면적"))
        if area_m2 <= 0:
            continue
        trade_type = _text(it, "거래유형")
        registered = bool(_text(it, "등기일자"))
        year = _to_int(_text(it, "년"))
        month = _to_int(_text(it, "월"))
        day = _to_int(_text(it, "일"))
        deal_date = f"{year:04d}-{month:02d}-{day:02d}" if year else ""

        out.append({
            "apt": _text(it, "아파트"),
            "dong": _text(it, "법정동"),
            "area_m2": area_m2,
            "price_won": price_man * 10_000,
            "price_pyeong": (price_man * 10_000) / (area_m2 / 3.305785),  # 평당가
            "build_year": _to_int(_text(it, "건축년도")),
            "trade_type": trade_type,
            "registered": registered,
            "deal_date": deal_date,
        })
    return out


def fetch_recent_trades(
    gu: str,
    months: int = 6,
    timeout: float = 10.0,
) -> list[dict]:
    """최근 N개월 누적 거래 (가장 최근 월부터 역순으로 수집).

    Vercel 10초 timeout 고려 — 월별 순차 호출. 25구 전체 fetch 는 cron 워커에서.
    """
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone(timedelta(hours=9)))
    out: list[dict] = []
    for i in range(months):
        m_dt = now - timedelta(days=30 * i)
        yyyymm = m_dt.strftime("%Y%m")
        rows = fetch_apt_trades(gu, yyyymm, timeout=timeout)
        if rows:
            for r in rows:
                r["yyyymm"] = yyyymm
            out.extend(rows)
    return out


def filter_rule_based(trades: list[dict]) -> tuple[list[dict], int]:
    """1차 룰 필터: 직거래·미등기 제외.

    Returns: (passed, removed_count)
    """
    passed = []
    for t in trades:
        if t.get("trade_type") in EXCLUDED_TRADE_TYPES:
            continue
        if not t.get("registered"):
            continue
        passed.append(t)
    return passed, len(trades) - len(passed)


def compute_value_score(
    gu_trades: list[dict],
    seoul_avg_pyeong: float,
) -> Optional[float]:
    """단일 구의 V(Value) 점수 산출.

    로직:
      - 구별 평당가 중앙값 vs 서울 25구 평균 평당가
      - 평균 대비 낮음 = 저평가 = V 점수 높음 (역사적 가치)
      - 평균 대비 높음 = 고평가 = V 점수 낮음
      - 기준: ratio = gu_median / seoul_avg
        ratio 0.5 → V=100, ratio 1.0 → V=50, ratio 2.0 → V=0 (선형 보간)

    seoul_avg_pyeong 은 호출자(orchestrator) 가 25구 전체에서 계산해서 전달.
    """
    if not gu_trades or seoul_avg_pyeong <= 0:
        return None

    from statistics import median
    gu_median = median(t["price_pyeong"] for t in gu_trades if t.get("price_pyeong", 0) > 0)
    if gu_median <= 0:
        return None

    ratio = gu_median / seoul_avg_pyeong
    # 0.5 → 100, 1.0 → 50, 2.0 → 0 (선형, clip)
    if ratio <= 0.5:
        score = 100.0
    elif ratio >= 2.0:
        score = 0.0
    else:
        # 0.5 ~ 2.0 구간 선형 변환
        score = 100 - ((ratio - 0.5) / 1.5) * 100
    return round(score, 1)

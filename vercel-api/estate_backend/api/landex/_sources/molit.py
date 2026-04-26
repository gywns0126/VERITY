"""국토교통부 아파트 매매 실거래 상세 자료 API 어댑터 — LANDEX V(Value) 입력.

API: https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev
     (상세 자료 — 기본 자료보다 필드 풍부. LANDEX 가 쓰는 모든 필드 포함)
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

# 아파트매매 실거래 상세 자료 (Dev = 상세). 기본 자료(RTMSDataSvcAptTrade) 와 다른 활용신청 필요.
MOLIT_BASE = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

# 1차 룰 필터: 제외할 거래유형
EXCLUDED_TRADE_TYPES = {"직거래"}  # 증여·상속은 별도 API라 여기 안 옴


def _api_key() -> str:
    return os.environ.get("PUBLIC_DATA_API_KEY", "").strip()


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
        _logger.warning("PUBLIC_DATA_API_KEY 미설정")
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
    r = None
    try:
        r = requests.get(MOLIT_BASE, params=params, timeout=timeout)
        r.raise_for_status()
        body = r.text
    except Exception as e:
        # 403/500 등 에러 시 응답 본문 일부 노출 — data.go.kr 가 XML 로 정확한 에러코드 반환
        # (SERVICE_KEY_IS_NOT_REGISTERED_ERROR / UNAUTHORIZED_KEY_ERROR / EXPIRED_KEY_ERROR 등)
        body_snip = ""
        try:
            if r is not None:
                body_snip = r.text[:400].replace("\n", " ")
        except Exception:
            pass
        _logger.warning("MOLIT fetch 실패 (%s/%s): %s | body=%s", gu, yyyymm, e, body_snip)
        return None

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        _logger.warning("MOLIT XML parse 실패: %s — head=%s", e, body[:200])
        return None

    # 표준 응답: <response><body><items><item>...</item>...</items></body></response>
    # 에러 시: <response><header><resultCode>... 또는 OpenAPI_ServiceResponse XML
    items = root.findall(".//item")
    if not items:
        # 빈 응답 진단 — header 의 resultMsg 등에서 "NO_DATA" 또는 "NORMAL_SERVICE" 확인
        result_msg = ""
        result_code = ""
        h = root.find(".//header")
        if h is not None:
            result_msg = (h.findtext("resultMsg") or "").strip()
            result_code = (h.findtext("resultCode") or "").strip()
        total_count = (root.findtext(".//totalCount") or "").strip()
        _logger.warning("MOLIT empty items (%s/%s) | code=%s msg=%s totalCount=%s | body=%s",
                        gu, yyyymm, result_code, result_msg, total_count, body[:300].replace("\n", " "))
    elif gu == "강남구":
        # 첫 구만 첫 item 의 raw XML 노출 — 필드명 확인용 (상세 API 가 다른 필드 쓰는지)
        try:
            sample = ET.tostring(items[0], encoding="unicode")[:500]
            _logger.warning("MOLIT sample item (%s/%s, %d total) | xml=%s",
                            gu, yyyymm, len(items), sample.replace("\n", " "))
        except Exception:
            pass
    # 상세 API (RTMSDataSvcAptTradeDev) 필드명 — 영문 camelCase
    # 기본 API 의 한글 필드명(거래금액/전용면적/년/월/일 등) 과 다름.
    out = []
    for it in items:
        price_man = _to_int(_text(it, "dealAmount"))  # 만원, 콤마 포함
        if price_man <= 0:
            continue
        area_m2 = _to_float(_text(it, "excluUseAr"))  # 전용면적
        if area_m2 <= 0:
            continue
        trade_type = _text(it, "dealingGbn")  # 중개거래 | 직거래
        # 취소된 거래(cdealType 비어있지 않으면 취소) — 제외
        cancelled = bool(_text(it, "cdealType"))
        if cancelled:
            continue
        # rgstDate (등기일자) — 신규 거래는 비어있을 수 있음. 정보용으로만 보관
        registered = bool(_text(it, "rgstDate"))
        year = _to_int(_text(it, "dealYear"))
        month = _to_int(_text(it, "dealMonth"))
        day = _to_int(_text(it, "dealDay"))
        deal_date = f"{year:04d}-{month:02d}-{day:02d}" if year else ""

        out.append({
            "apt": _text(it, "aptNm"),
            "dong": _text(it, "umdNm"),  # 법정동 (읍면동명)
            "area_m2": area_m2,
            "price_won": price_man * 10_000,
            "price_pyeong": (price_man * 10_000) / (area_m2 / 3.305785),  # 평당가
            "build_year": _to_int(_text(it, "buildYear")),
            "trade_type": trade_type,
            "registered": registered,  # 등기 여부 (정보용)
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
    """1차 룰 필터: 직거래 제외 (취소거래는 fetch 단계에서 이미 제외).

    등기일자(rgstDate)는 신규 거래일수록 비어있을 가능성이 커서 strict 필터로 안 씀.
    cancelled (cdealType 있음) 는 fetch_apt_trades 에서 사전 제외됨.

    Returns: (passed, removed_count)
    """
    passed = []
    for t in trades:
        if t.get("trade_type") in EXCLUDED_TRADE_TYPES:
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

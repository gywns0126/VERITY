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


# ─────────────────────────────────────────────────────────────────────
# 아파트 전월세 실거래 (RTMSDataSvcAptRent) — 2026-05-20 추가
# 실호출 검증: getRTMSDataSvcAptRent code=000 OK (강남구 2026-04 총 1269건).
# Dev 버전(...RentDev)은 미등록 → 비-Dev 사용. 필드 추측 X, 실응답 기준.
# monthlyRent==0 → 전세 / >0 → 월세·반전세. preDeposit/preMonthlyRent = 갱신 종전 조건.
# [[feedback_real_call_over_llm_consensus]] / [[feedback_external_api_4bucket_verify]] 정합.
# ─────────────────────────────────────────────────────────────────────
MOLIT_RENT_BASE = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"


def _parse_rent_item(it: ET.Element, name_tag: str = "aptNm") -> Optional[dict]:
    """전월세 실거래 item 1건 파싱. 보증금/면적 0 이면 None.

    아파트·오피스텔 전월세 동일 schema (실호출 검증) — 건물명 태그만 다름(aptNm / offiNm).
    deposit/monthlyRent = 만원(콤마). monthlyRent==0 → 전세, >0 → 월세/반전세.
    preDeposit/preMonthlyRent = 갱신계약 종전 조건 (신규면 빈 값 → None).
    """
    deposit_man = _to_int(_text(it, "deposit"))
    if deposit_man <= 0:
        return None
    area_m2 = _to_float(_text(it, "excluUseAr"))
    if area_m2 <= 0:
        return None
    monthly_man = _to_int(_text(it, "monthlyRent"))
    pre_deposit_man = _to_int(_text(it, "preDeposit"))
    pre_monthly_man = _to_int(_text(it, "preMonthlyRent"))
    year = _to_int(_text(it, "dealYear"))
    month = _to_int(_text(it, "dealMonth"))
    day = _to_int(_text(it, "dealDay"))
    return {
        "name": _text(it, name_tag),
        "dong": _text(it, "umdNm"),
        "area_m2": area_m2,
        "deposit_won": deposit_man * 10_000,
        "monthly_rent_won": monthly_man * 10_000,
        "lease_type": "전세" if monthly_man == 0 else "월세",
        "floor": _to_int(_text(it, "floor")),
        "build_year": _to_int(_text(it, "buildYear")),
        "contract_type": _text(it, "contractType"),   # 신규 | 갱신 | ''
        "contract_term": _text(it, "contractTerm"),    # 계약기간 (구데이터 빈 값 가능)
        "pre_deposit_won": pre_deposit_man * 10_000 if pre_deposit_man else None,
        "pre_monthly_rent_won": pre_monthly_man * 10_000 if pre_monthly_man else None,
        "deal_date": f"{year:04d}-{month:02d}-{day:02d}" if year else "",
    }


def fetch_apt_rents(
    gu: str,
    yyyymm: str,
    page: int = 1,
    rows: int = 1000,
    timeout: float = 10.0,
) -> Optional[list[dict]]:
    """단일 구·단일 월의 아파트 전월세 실거래 조회 (fetch_apt_trades 패턴 미러).

    Returns:
      [{ apt, dong, area_m2, deposit_won, monthly_rent_won, lease_type, floor,
         build_year, contract_type, contract_term, pre_deposit_won, pre_monthly_rent_won, deal_date }]
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
        r = requests.get(MOLIT_RENT_BASE, params=params, timeout=timeout)
        r.raise_for_status()
        body = r.text
    except Exception as e:
        body_snip = ""
        try:
            if r is not None:
                body_snip = r.text[:400].replace("\n", " ")
        except Exception:
            pass
        _logger.warning("MOLIT rent fetch 실패 (%s/%s): %s | body=%s", gu, yyyymm, e, body_snip)
        return None

    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        _logger.warning("MOLIT rent XML parse 실패: %s — head=%s", e, body[:200])
        return None

    items = root.findall(".//item")
    if not items:
        h = root.find(".//header")
        rc = (h.findtext("resultCode") or "").strip() if h is not None else ""
        rm = (h.findtext("resultMsg") or "").strip() if h is not None else ""
        _logger.warning("MOLIT rent empty (%s/%s) | code=%s msg=%s", gu, yyyymm, rc, rm)
        return []

    out: list[dict] = []
    for it in items:
        parsed = _parse_rent_item(it)
        if parsed is not None:
            out.append(parsed)
    return out


def fetch_recent_rents(
    gu: str,
    months: int = 6,
    timeout: float = 10.0,
) -> list[dict]:
    """최근 N개월 누적 전월세 거래 (fetch_recent_trades 패턴 미러)."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone(timedelta(hours=9)))
    out: list[dict] = []
    for i in range(months):
        m_dt = now - timedelta(days=30 * i)
        yyyymm = m_dt.strftime("%Y%m")
        rows = fetch_apt_rents(gu, yyyymm, timeout=timeout)
        if rows:
            for r in rows:
                r["yyyymm"] = yyyymm
            out.extend(rows)
    return out


# ─────────────────────────────────────────────────────────────────────
# 비아파트 실거래 (연립다세대 / 오피스텔 / 단독다가구) — 2026-05-20 추가
# 실호출 일괄 검증 (강남구 2026-04): RH매매·Offi매매·Offi전월세·SH매매 = code=000 OK.
#   ⚠ RH전월세(RTMSDataSvcRHRent)·SH전월세(RTMSDataSvcSHRent) = HTTP 403 = key 활용신청 미완 →
#     data.go.kr 활용신청(user action) 후 wiring. 추측/임의 박음 X.
# 필드 추측 X, 실응답 기준. 매매(연립/오피스텔)=excluUseAr+floor / 단독=plottageAr(대지)+totalFloorAr(연면적).
# [[feedback_real_call_over_llm_consensus]] / [[feedback_external_api_4bucket_verify]].
# ─────────────────────────────────────────────────────────────────────
RH_TRADE_BASE = "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade"
OFFI_TRADE_BASE = "https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade"
OFFI_RENT_BASE = "https://apis.data.go.kr/1613000/RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent"
SH_TRADE_BASE = "https://apis.data.go.kr/1613000/RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade"


def _fetch_rtms_items(
    base_url: str, gu: str, yyyymm: str, label: str,
    page: int = 1, rows: int = 1000, timeout: float = 10.0,
) -> Optional[list[ET.Element]]:
    """RTMS 공통 fetch — key/lawd/yyyymm 검증 + GET + XML item 리스트 반환.

    Returns: item Element 리스트. None=키미설정/네트워크실패/잘못된입력, []=정상호출이나 0건.
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
        "serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": yyyymm,
        "pageNo": str(page), "numOfRows": str(rows),
    }
    r = None
    try:
        r = requests.get(base_url, params=params, timeout=timeout)
        r.raise_for_status()
        body = r.text
    except Exception as e:
        snip = ""
        try:
            if r is not None:
                snip = r.text[:300].replace("\n", " ")
        except Exception:
            pass
        _logger.warning("MOLIT %s fetch 실패 (%s/%s): %s | body=%s", label, gu, yyyymm, e, snip)
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        _logger.warning("MOLIT %s XML parse 실패: %s — head=%s", label, e, body[:200])
        return None
    items = root.findall(".//item")
    if not items:
        h = root.find(".//header")
        rc = (h.findtext("resultCode") or "").strip() if h is not None else ""
        rm = (h.findtext("resultMsg") or "").strip() if h is not None else ""
        _logger.warning("MOLIT %s empty (%s/%s) | code=%s msg=%s", label, gu, yyyymm, rc, rm)
        return []
    return items


def _parse_dev_trade_item(it: ET.Element, name_tag: str) -> Optional[dict]:
    """연립다세대/오피스텔 매매 item (excluUseAr·floor 보유, 아파트 매매와 동형).

    가격/면적 0 또는 취소거래(cdealType) → None.
    """
    price_man = _to_int(_text(it, "dealAmount"))
    if price_man <= 0:
        return None
    area_m2 = _to_float(_text(it, "excluUseAr"))
    if area_m2 <= 0:
        return None
    if _text(it, "cdealType"):  # 취소거래
        return None
    year = _to_int(_text(it, "dealYear"))
    month = _to_int(_text(it, "dealMonth"))
    day = _to_int(_text(it, "dealDay"))
    return {
        "name": _text(it, name_tag),
        "dong": _text(it, "umdNm"),
        "area_m2": area_m2,
        "price_won": price_man * 10_000,
        "price_pyeong": (price_man * 10_000) / (area_m2 / 3.305785),
        "build_year": _to_int(_text(it, "buildYear")),
        "floor": _to_int(_text(it, "floor")),
        "trade_type": _text(it, "dealingGbn"),
        "registered": bool(_text(it, "rgstDate")),
        "deal_date": f"{year:04d}-{month:02d}-{day:02d}" if year else "",
    }


def _parse_sh_trade_item(it: ET.Element) -> Optional[dict]:
    """단독/다가구 매매 item — 전용면적/층/건물명 없음. 대지면적·연면적 기반.

    가격 0 또는 취소거래 → None. plottageAr=대지면적, totalFloorAr=연면적.
    """
    price_man = _to_int(_text(it, "dealAmount"))
    if price_man <= 0:
        return None
    if _text(it, "cdealType"):
        return None
    year = _to_int(_text(it, "dealYear"))
    month = _to_int(_text(it, "dealMonth"))
    day = _to_int(_text(it, "dealDay"))
    return {
        "house_type": _text(it, "houseType"),
        "dong": _text(it, "umdNm"),
        "total_floor_ar_m2": _to_float(_text(it, "totalFloorAr")),  # 연면적
        "plottage_ar_m2": _to_float(_text(it, "plottageAr")),       # 대지면적
        "price_won": price_man * 10_000,
        "build_year": _to_int(_text(it, "buildYear")),
        "trade_type": _text(it, "dealingGbn"),
        "registered": bool(_text(it, "rgstDate")),
        "deal_date": f"{year:04d}-{month:02d}-{day:02d}" if year else "",
    }


def _collect(items: Optional[list[ET.Element]], parse_fn) -> Optional[list[dict]]:
    if items is None:
        return None
    out: list[dict] = []
    for it in items:
        d = parse_fn(it)
        if d is not None:
            out.append(d)
    return out


def fetch_rh_trades(gu: str, yyyymm: str, timeout: float = 10.0) -> Optional[list[dict]]:
    """연립다세대 매매 실거래 (RTMSDataSvcRHTrade). 건물명 mhouseNm."""
    items = _fetch_rtms_items(RH_TRADE_BASE, gu, yyyymm, "RH매매", timeout=timeout)
    return _collect(items, lambda it: _parse_dev_trade_item(it, "mhouseNm"))


def fetch_offi_trades(gu: str, yyyymm: str, timeout: float = 10.0) -> Optional[list[dict]]:
    """오피스텔 매매 실거래 (RTMSDataSvcOffiTrade). 건물명 offiNm."""
    items = _fetch_rtms_items(OFFI_TRADE_BASE, gu, yyyymm, "Offi매매", timeout=timeout)
    return _collect(items, lambda it: _parse_dev_trade_item(it, "offiNm"))


def fetch_offi_rents(gu: str, yyyymm: str, timeout: float = 10.0) -> Optional[list[dict]]:
    """오피스텔 전월세 실거래 (RTMSDataSvcOffiRent). 아파트 전월세와 동형 schema, 건물명 offiNm."""
    items = _fetch_rtms_items(OFFI_RENT_BASE, gu, yyyymm, "Offi전월세", timeout=timeout)
    return _collect(items, lambda it: _parse_rent_item(it, "offiNm"))


def fetch_sh_trades(gu: str, yyyymm: str, timeout: float = 10.0) -> Optional[list[dict]]:
    """단독/다가구 매매 실거래 (RTMSDataSvcSHTrade). 대지·연면적 기반."""
    items = _fetch_rtms_items(SH_TRADE_BASE, gu, yyyymm, "SH매매", timeout=timeout)
    return _collect(items, _parse_sh_trade_item)


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

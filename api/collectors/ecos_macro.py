"""
한국은행 ECOS Open API — StatisticSearch
  기준금리: 722Y001 (월 M), 항목 0101000
  국고채 10년: 817Y002 (일 D), 항목 010210000
https://ecos.bok.or.kr/api/
"""
from datetime import timedelta
import math
import sys
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from api.config import ECOS_API_KEY, now_kst
from api.utils.macro_provenance import copy_meta, now_iso, observation_meta
from api.utils.macro_runtime import CollectionDeadline, collection_budget, request_timeout

ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
_COLLECTION_BUDGET = 18
_SOURCE_BUDGET = 6
_CONNECT_TIMEOUT = 2
_READ_TIMEOUT = 3
_TRANSIENT_HTTP = {408, 429, 500, 502, 503, 504}
_SOURCE_LABELS = {"722Y001": "policy_rate", "901Y009": "cpi", "817Y002": "gov_10y"}


def _normalize_rows(payload: dict) -> List[dict]:
    if not isinstance(payload, dict) or not payload or "RESULT" in payload:
        return []
    ss = payload.get("StatisticSearch") or {}
    raw = ss.get("row") if isinstance(ss, dict) else None
    if raw is None:
        return []
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


@collection_budget(_SOURCE_BUDGET)
def _ecos_get(
    api_key: str,
    stat_code: str,
    cycle: str,
    period_start: str,
    period_end: str,
    item_code: str,
    start_idx: int = 1,
    end_idx: int = 100,
) -> List[dict]:
    """ECOS StatisticSearch JSON — row 리스트(시간 오름차순)."""
    key_seg = quote(api_key, safe="")
    url = (
        f"{ECOS_BASE}/{key_seg}/json/kr/{int(start_idx)}/{int(end_idx)}"
        f"/{stat_code}/{cycle}/{period_start}/{period_end}/{item_code}"
    )
    label = _SOURCE_LABELS.get(stat_code, "other")
    for attempt in range(1, 3):
        started = time.monotonic()
        status = "error"
        response = None
        try:
            remaining = request_timeout(_CONNECT_TIMEOUT + _READ_TIMEOUT)
            # Divide the remaining allowance between connection and read phases.
            # These are socket caps; the parent process owns hard cancellation.
            timeout = (min(_CONNECT_TIMEOUT, remaining * 0.4),
                       min(_READ_TIMEOUT, remaining * 0.6))
            response = requests.get(url, timeout=timeout, allow_redirects=False)
            status = f"http_{response.status_code}"
            if response.status_code == 200:
                rows = _normalize_rows(response.json())
                request_timeout(1)  # Discard responses completed after the deadline.
                status = "ok" if rows else "empty_or_result"
                return rows
            if response.status_code not in _TRANSIENT_HTTP:
                return []
        except CollectionDeadline:
            status = "CollectionDeadline"
            return []
        except requests.exceptions.SSLError:
            status = "SSLError"
            return []
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as error:
            status = type(error).__name__
        except Exception as error:
            status = type(error).__name__
            return []
        finally:
            if response is not None:
                close = getattr(response, "close", None)
                if close:
                    try:
                        close()
                    except Exception:
                        status += "_close_error"
            elapsed_ms = round((time.monotonic() - started) * 1000)
            sys.stderr.write(
                f"[ecos_fetch] source=ecos:{label} attempt={attempt} "
                f"status={status} elapsed_ms={elapsed_ms}\n"
            )
    return []


def _finite_value(row: dict) -> Optional[float]:
    """A missing/nonfinite observation is not a measured zero."""
    try:
        value = float(row.get("DATA_VALUE"))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _month_range_months_back(months: int) -> tuple:
    """(시작 YYYYMM, 종료 YYYYMM) KST 기준."""
    end = now_kst().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=30 * months)
    return start.strftime("%Y%m"), end.strftime("%Y%m")


def _day_range_days_back(days: int) -> tuple:
    """(시작 YYYYMMDD, 종료 YYYYMMDD) KST 기준."""
    today = now_kst().date()
    start = today - timedelta(days=days)
    return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")


# ── 한국 CPI 인플레 축 (F-c, PREREG_INFLATION_AXIS_2026_08_20 · PM 승인 2026-08-20) ──
# 🚨 창 길이는 **사전 고정**이다. 여러 창을 시도해 좋은 걸 고르면 그 자체가 데이터
#   스누핑이다(White 2000 Econometrica; Q5 답변). 12개월은 El-Ayari(2026 QUANTT)의
#   외생값을 그대로 쓴 것이며, 변경은 사전등록 + 사유 명시로만 한다.
#   테스트가 이 값을 잠근다 — tests/test_inflation_axis_kr_cpi.py
KR_CPI_STAT = "901Y009"        # 소비자물가지수 (ECOS)
KR_CPI_ITEM = "0"              # 총지수 = headline (Q10: 후속 4분면 관행은 headline)
KR_CPI_Z_WINDOW_M = 12         # 🚨 사전 고정. 외생 근거 = El-Ayari(2026)
KR_CPI_MIN_MONTHS = KR_CPI_Z_WINDOW_M + 13   # YoY(12) + z창(12) + 현재(1)


def _kr_cpi_inflation_axis(key: str) -> Optional[Dict[str, Any]]:
    """한국 headline CPI → YoY → 12M 롤링 z-score(부호). 산출 불가면 None.

    🚨 F-c 형태 — **임계가 없다.** z 의 부호만 본다.
    Bridgewater 원전이 인플레 축을 "기대 대비 상승/하락" 으로 정의하고(지표·임계 미특정),
    후속 4분면 구현은 절대 수준이 아니라 **변화·z-score** 를 쓴다(Q10). 부호만 보면
    임계라는 자유 파라미터가 사라져 스누핑 여지가 최소가 된다.

    🚨 결측이면 **값을 만들지 않는다**(B1 센티넬 규율). 소비자가 판정을 보류한다.
    """
    ps, pe = _month_range_months_back(KR_CPI_MIN_MONTHS + 6)
    rows = _ecos_get(key, KR_CPI_STAT, "M", ps, pe, KR_CPI_ITEM, 1, 100)
    fetched_at = now_iso() if rows else None
    if len(rows) < KR_CPI_MIN_MONTHS:
        return None

    idx: Dict[str, float] = {}
    for r in rows:
        t, v = str(r.get("TIME", "")), r.get("DATA_VALUE")
        if len(t) == 6 and v not in (None, "", "."):
            try:
                value = _finite_value(r)
                if value is not None:
                    idx[t] = value
            except (TypeError, ValueError):
                continue
    months = sorted(idx)
    yoy: List[float] = []
    yoy_months: List[str] = []
    for m in months:
        prev = f"{int(m[:4]) - 1}{m[4:]}"
        if prev in idx and idx[prev]:
            yoy.append((idx[m] / idx[prev] - 1.0) * 100.0)
            yoy_months.append(m)
    if len(yoy) < KR_CPI_Z_WINDOW_M + 1:
        return None

    window = yoy[-(KR_CPI_Z_WINDOW_M + 1):-1]      # 현재 제외한 직전 12개월
    mu = sum(window) / len(window)
    var = sum((x - mu) ** 2 for x in window) / (len(window) - 1)
    sd = var ** 0.5
    if sd <= 0:
        return None
    z = (yoy[-1] - mu) / sd
    return {
        "yoy_pct": round(yoy[-1], 3),
        "z": round(z, 3),
        "inflation_up": bool(z > 0),          # 🚨 F-c — 임계 없음, 부호만
        "date": yoy_months[-1],
        "window_months": KR_CPI_Z_WINDOW_M,
        "stat_code": KR_CPI_STAT,
        "item_code": KR_CPI_ITEM,
        "source": "ecos",
        **observation_meta("ecos", yoy_months[-1], fetched_at=fetched_at),
        "form": "rolling_z_sign_only",
        "note": ("한국 headline CPI YoY 의 12M 롤링 z 부호. 절대 임계 없음 — "
                 "PREREG_INFLATION_AXIS_2026_08_20 F-c. 창은 사전 고정(변경=사전등록)"),
    }


@collection_budget(_COLLECTION_BUDGET)
def get_ecos_macro_block() -> Dict[str, Any]:
    """
    ECOS 한국 기준금리(월)·국고채 10년(일).
    키 없거나 오류 시 available=False.
    """
    out: Dict[str, Any] = {"available": False}
    if not ECOS_API_KEY or not str(ECOS_API_KEY).strip():
        return out

    key = str(ECOS_API_KEY).strip()

    ps, pe = _month_range_months_back(24)
    pr_rows = _ecos_get(key, "722Y001", "M", ps, pe, "0101000", 1, 24)
    if pr_rows:
        fetched_at = now_iso()
        last = pr_rows[-1]
        try:
            value = _finite_value(last)
            if value is None:
                raise ValueError("missing policy rate")
            out["korea_policy_rate"] = {
                "value": round(value, 3),
                "date": str(last.get("TIME", "")),
                "unit": last.get("UNIT_NAME"),
                "stat_code": "722Y001",
                "source": "ecos",
                **observation_meta("ecos", last.get("TIME"), fetched_at=fetched_at),
            }
        except (TypeError, ValueError):
            pass

    # 🚨 한국 CPI 인플레 축 (F-c). 실패해도 다른 축을 죽이지 않는다.
    try:
        _kcpi = _kr_cpi_inflation_axis(key)
        if _kcpi:
            out["korea_cpi_axis"] = _kcpi
    except Exception:  # noqa: BLE001 — 수집 실패가 매크로 블록 전체를 죽이지 않는다
        pass

    ds, de = _day_range_days_back(400)
    y_rows = _ecos_get(key, "817Y002", "D", ds, de, "010210000", 1, 320)
    if y_rows:
        fetched_at = now_iso()
        last = y_rows[-1]
        try:
            value = _finite_value(last)
            if value is None:
                raise ValueError("missing government yield")
            val = round(value, 4)
            yoy_pp: Optional[float] = None
            if len(y_rows) >= 200:
                ref = y_rows[max(0, len(y_rows) - 260)]
                ref_value = _finite_value(ref)
                if ref_value is not None:
                    yoy_pp = round(val - ref_value, 3)
            d_raw = str(last.get("TIME", ""))
            date_iso = d_raw
            if len(d_raw) == 8 and d_raw.isdigit():
                date_iso = f"{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:8]}"
            out["korea_gov_10y"] = {
                "value": val,
                "date": date_iso,
                "yoy_pp": yoy_pp,
                "series_id": "ECOS/817Y002/010210000",
                "source_note": "한국은행 ECOS 시장금리(일별) 국고채(10년)",
                "source": "ecos",
                **observation_meta("ecos", date_iso or None, fetched_at=fetched_at),
            }
        except (TypeError, ValueError):
            pass

    out["available"] = bool(out.get("korea_policy_rate") or out.get("korea_gov_10y"))
    return out


def merge_ecos_into_fred(fred: Dict[str, Any], ecos: Dict[str, Any]) -> None:
    """fred 블록에 ECOS 한국 지표를 덮어쓰기·추가(in-place)."""
    if not fred or not ecos or not ecos.get("available"):
        return

    if ecos.get("korea_gov_10y"):
        g = ecos["korea_gov_10y"]
        fred["korea_gov_10y"] = {
            "value": g.get("value"),
            "date": g.get("date"),
            "yoy_pp": g.get("yoy_pp"),
            "series_id": g.get("series_id"),
            "source_note": g.get("source_note"),
            **copy_meta(g),
        }

    if ecos.get("korea_policy_rate"):
        fred["korea_policy_rate"] = dict(ecos["korea_policy_rate"])

    # 🚨 한국 CPI 인플레 축은 **별도 키**로 싣는다. `cpi_yoy`(미국 core)를 덮지 않는다 —
    #   두 값이 다르다는 사실이 산출물에서 보여야 한다(PREREG_INFLATION_AXIS §6).
    if ecos.get("korea_cpi_axis"):
        fred["korea_cpi_axis"] = dict(ecos["korea_cpi_axis"])

    fred["available"] = bool(
        fred.get("dgs10")
        or fred.get("core_cpi")
        or fred.get("m2")
        or fred.get("vix_close")
        or fred.get("korea_discount_rate")
        or fred.get("us_recession_smoothed_prob")
        or fred.get("korea_gov_10y")
        or fred.get("korea_policy_rate")
    )

"""
Shiller CAPE — multpl.com 스크래핑.

FRED 에 직접 시리즈 없어 multpl.com 의 meta description 에서 현재 값 추출.
HTML 형식 변경 시 fallback graceful (None 반환, market_horizon 가 cape_pctile=None 처리).

배경 (2026-05-07): MarketHorizon V0 에서 cape 누락으로 cycle_stage 가 spread/hy_oas
중심으로만 판단. CAPE 추가 시 euphoria 단계 정확 분류 가능.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MULTPL_URL = "https://www.multpl.com/shiller-pe"
_META_RE = re.compile(r"Current Shiller PE Ratio is ([\d.]+)", re.IGNORECASE)
_CHANGE_RE = re.compile(r"a change of ([+-]?[\d.]+) from previous", re.IGNORECASE)


def fetch_cape() -> Optional[dict]:
    """multpl.com 에서 현재 CAPE 값 추출.

    Returns dict with `value` / `change` / `as_of` / `source` 또는 None (실패 시).
    """
    try:
        r = requests.get(
            MULTPL_URL,
            headers={"User-Agent": "Mozilla/5.0 VERITY/1.0 health-check"},
            timeout=8,
        )
        if r.status_code != 200:
            logger.warning("CAPE multpl HTTP %s", r.status_code)
            return None
        html = r.text
        m = _META_RE.search(html)
        if not m:
            logger.warning("CAPE multpl 형식 변경 — meta 추출 실패")
            return None
        value = float(m.group(1))
        change_m = _CHANGE_RE.search(html)
        change = float(change_m.group(1)) if change_m else None
        from api.config import now_kst
        return {
            "value": value,
            "change_from_prev_close": change,
            # now_kst()=aware KST → strftime KST 벽시계 + 정확한 +09:00 (GH=UTC 9h 오기 차단)
            "as_of": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "source": "multpl.com (Shiller PE)",
            "series_id": "MULTPL_SHILLER_PE",
        }
    except (requests.RequestException, ValueError) as e:
        logger.warning("CAPE multpl 실패: %s", e)
        return None

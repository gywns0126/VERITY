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
from datetime import date
from html import unescape
from typing import Optional

import requests
from api.utils.macro_runtime import request_timeout

logger = logging.getLogger(__name__)

# The chart's current timestamp omits the year; the linked table states it.
MULTPL_URL = "https://www.multpl.com/shiller-pe/table/by-month"
_META_RE = re.compile(r"Current Shiller PE Ratio is ([\d.]+)", re.IGNORECASE)
_CHANGE_RE = re.compile(r"a change of ([+-]?[\d.]+) from previous", re.IGNORECASE)
_TABLE_RE = re.compile(r'<table\b[^>]*\bid=[\"\']datatable[\"\'][^>]*>(.*?)</table>', re.I | re.S)
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.I | re.S)
_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _source_date(html: str, current_value: float) -> Optional[str]:
    """Accept only an explicit date on the first table row matching this quote."""
    table = _TABLE_RE.search(html)
    rows = _ROW_RE.findall(table.group(1)) if table else []
    row = next((row for row in rows if re.search(r"<td\b", row, re.I)), "")
    cells = _CELL_RE.findall(row)
    if len(cells) != 2:
        return None
    cells = [unescape(re.sub(r"<[^>]+>", "", cell)).strip() for cell in cells]
    match = re.fullmatch(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})", cells[0])
    if not match:
        return None
    try:
        if float(cells[1].replace(",", "")) != current_value:
            return None
        month, day, year = match.groups()
        return date(int(year), _MONTHS.index(month) + 1, int(day)).isoformat()
    except ValueError:
        return None


def fetch_cape() -> Optional[dict]:
    """multpl.com 에서 현재 CAPE 값 추출.

    Returns dict with `value` / `change` / `as_of` / `source` 또는 None (실패 시).
    """
    try:
        r = requests.get(
            MULTPL_URL,
            headers={"User-Agent": "Mozilla/5.0 VERITY/1.0 health-check"},
            timeout=request_timeout(8),
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
            "source_as_of": _source_date(html, value),
            "source_url": MULTPL_URL,
        }
    except (requests.RequestException, ValueError) as e:
        logger.warning("CAPE multpl 실패: %s", e)
        return None

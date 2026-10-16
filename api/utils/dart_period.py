"""DART receipt-matched reporting periods; never substitute a retrieval date."""
from __future__ import annotations

import re
from datetime import date


def valid_period_end(value, *, as_of: str) -> bool:
    try:
        return len(str(value)) == 10 and date.fromisoformat(str(value)) <= date.fromisoformat(as_of[:10])
    except (TypeError, ValueError):
        return False


def verified_period(data: dict, *, corp_code: str, bsns_year: str,
                    reprt_code: str, fs_div: str, receipt: str,
                    total_assets: int, as_of: str) -> dict:
    """Match fnlttSinglAcnt to the exact all-accounts receipt and statement scope.

    REIT report codes are not reliable calendar-quarter offsets. Both the BS
    date and the IS period must agree; a later amended receipt is not equivalent.
    """
    if data.get("status") != "000" or not re.fullmatch(r"\d{14}", receipt or ""):
        return {}
    rows = [r for r in data.get("list", []) if all(str(r.get(k, "")) == v for k, v in {
        "corp_code": corp_code, "bsns_year": bsns_year, "reprt_code": reprt_code,
        "fs_div": fs_div, "rcept_no": receipt,
    }.items())]
    ends, starts, assets = set(), set(), set()
    bs_seen = is_seen = False
    for row in rows:
        if row.get("sj_div") not in {"BS", "IS", "CIS"}:
            continue
        dates = ["-".join(x) for x in re.findall(r"(\d{4})[.-](\d{2})[.-](\d{2})", str(row.get("thstrm_dt", "")))]
        if not dates or any(not valid_period_end(x, as_of=as_of) for x in dates):
            return {}
        ends.add(dates[-1])
        if row.get("sj_div") == "BS":
            bs_seen = True
            if row.get("account_nm") == "자산총계":
                try:
                    assets.add(int(str(row.get("thstrm_amount", "")).replace(",", "")))
                except ValueError:
                    return {}
        else:
            if len(dates) != 2 or dates[0] > dates[-1]:
                return {}
            is_seen = True
            starts.add(dates[0])
    if not (bs_seen and is_seen and len(ends) == len(starts) == 1 and assets == {total_assets}):
        return {}
    return {"period_start": starts.pop(), "period_end": ends.pop(),
            "period_basis": "source_reported", "rcept_no": receipt,
            "source_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"}

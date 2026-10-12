"""Pure projection of ETF observations from the existing public etf_flow artifact.

Integration: call append_public_etf_facts(payload, companies) once per fresh
company catalog. Only company facts are extended; the source is never mutated.
Coverage partitions ETF rows: input = accepted + rejected + unmatched.
shape_errors separately counts malformed containers/rows, never valid empties.
facts counts appended facts. Missing NAV/net assets do not imply zero and do
not invalidate other observations. No holdings, estimated flows or scores pass.
"""
from collections import Counter
from datetime import date
import math
import re

SOURCE_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/etf_flow.json"
SOURCE = "KRX 공개 ETF 자료"
_METRICS = (
    ("list_shrs", "etf_listed_units", "좌"),
    ("nav", "etf_nav", "KRW"),
    ("netasset", "etf_net_assets", "KRW"),
)


def _day(value):
    if not isinstance(value, str):
        return None
    if re.fullmatch(r"[0-9]{8}", value):
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    # Calendar validity alone cannot establish a KRX observation on a weekend.
    return value if parsed.weekday() < 5 else None


def _number(value, *, units=False, signed=False):
    if type(value) not in (int, float) or abs(value) > 9007199254740991:
        return None
    if not math.isfinite(value) or (not signed and value < 0):
        return None
    if units and int(value) != value:
        return None
    return int(value) if units else value


def _history(rows, trade_date):
    if not isinstance(rows, list) or not rows or len(rows) > 40:
        return None
    dated = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        day = _day(row.get("date"))
        if day is None or (dated and day <= dated[-1][0]):
            return None
        dated.append((day, row))
    return dated if dated[-1][0] == trade_date else None


def _fact(metric, value, unit, ticker, trade_date, previous_date=None):
    provenance = {"kind": "public-etf-flow", "ticker": ticker,
                  "trade_date": trade_date, "source_url": SOURCE_URL}
    if previous_date is not None:
        provenance["previous_date"] = previous_date
    return {"metric": metric, "value": value, "unit": unit,
            "as_of": trade_date, "source": SOURCE, "provenance": provenance}


def append_public_etf_facts(payload, companies):
    """Append exact KR ETF facts in place and return row/fact coverage.

    Latest row fields must equal the same dated history observation. Delta is
    an explicit d_shrs crosschecked against the immediately preceding retained
    trading day, positive prior units, prev_date and the retained days_n count.
    Invalid/ambiguous observations never fall back to an older day.
    Unknown input fields are ignored by constructing facts from an allowlist.
    """
    coverage = dict(input=0, accepted=0, rejected=0, unmatched=0, facts=0, shape_errors=0)
    if not isinstance(payload, dict) or not isinstance(payload.get("etfs"), list):
        coverage["shape_errors"] = 1
        return coverage
    rows = payload["etfs"]
    coverage["input"] = len(rows)
    trade_date = _day(payload.get("bas_dd"))
    history = payload.get("history")
    coverage["shape_errors"] = (int(not isinstance(history, dict))
                                + int(not isinstance(companies, dict)))
    if coverage["shape_errors"]:
        coverage["rejected"] = len(rows)
        return coverage
    if trade_date is None or trade_date > date.today().isoformat():
        coverage["rejected"] = len(rows)
        return coverage
    tickers = Counter(row.get("ticker") for row in rows
                      if isinstance(row, dict) and isinstance(row.get("ticker"), str))
    for row in rows:
        if not isinstance(row, dict):
            coverage["shape_errors"] += 1
            coverage["rejected"] += 1
            continue
        ticker = row.get("ticker") if isinstance(row, dict) else None
        if (not isinstance(ticker, str) or not re.fullmatch(r"[0-9A-Z]{6}", ticker)
                or tickers[ticker] != 1):
            coverage["rejected"] += 1
            continue
        retained = history.get(ticker)
        if not isinstance(retained, list):
            coverage["shape_errors"] += 1
        else:
            coverage["shape_errors"] += sum(not isinstance(entry, dict) for entry in retained)
        series = _history(retained, trade_date)
        if series is None:
            coverage["rejected"] += 1
            continue
        latest = series[-1][1]
        facts = []
        for field, metric, unit in _METRICS:
            value = _number(row.get(field), units=field == "list_shrs")
            observed = _number(latest.get(field), units=field == "list_shrs")
            if value is not None and observed is not None and value == observed:
                facts.append(_fact(metric, value, unit, ticker, trade_date))
        if len(series) >= 2:
            previous_date, previous = series[-2]
            current = _number(row.get("list_shrs"), units=True)
            observed = _number(latest.get("list_shrs"), units=True)
            prior = _number(previous.get("list_shrs"), units=True)
            delta = _number(row.get("d_shrs"), units=True, signed=True)
            if (current is not None and current == observed
                    and prior is not None and prior > 0 and delta is not None
                    and delta == current - prior
                    and _day(row.get("prev_date")) == previous_date
                    and type(row.get("days_n")) is int and row["days_n"] == len(series)):
                facts.append(_fact("etf_unit_change", delta, "좌", ticker,
                                   trade_date, previous_date))
        if not facts:
            coverage["rejected"] += 1
            continue
        identifier = f"KR:{ticker}"
        company = companies.get(identifier)
        if identifier in companies and not isinstance(company, dict):
            coverage["shape_errors"] += 1
        elif isinstance(company, dict) and not isinstance(company.get("facts"), list):
            coverage["shape_errors"] += 1
        if (not isinstance(company, dict) or company.get("ticker") != ticker
                or company.get("market") != "KR"
                or company.get("id", identifier) != identifier
                or not isinstance(company.get("facts"), list)):
            coverage["unmatched"] += 1
            continue
        company["facts"].extend(facts)
        coverage["accepted"] += 1
        coverage["facts"] += len(facts)
    return coverage

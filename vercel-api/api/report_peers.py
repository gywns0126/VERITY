"""Pure peer normalization and bounded, optional public-feed orchestration.

Caller supplies the entire same-market ticker -> stock mapping. Peer periods
come exclusively from stock.financial_evidence.periods (including caller-adapted
us_periods / reviewed_financials output). Only build_peer_comparison performs
local review reads or calls the caller's existing fetch; normalized_peers is pure.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime
import math
import re
from urllib.parse import parse_qs, urlparse

if __package__:
    from .report_reader import valid_period
    from .report_context import _number
    from .report_kr_review import reviewed_financials
    from .report_us_financials import us_periods
else:
    from report_reader import valid_period
    from report_context import _number
    from report_kr_review import reviewed_financials
    from report_us_financials import us_periods


FIELDS = ("start", "end", "period_kind", "currency", "fs_div")
METRICS = ("revenue", "op", "net", "ocf", "capex")
# Report-display freshness ceilings, not statutory filing deadlines.
MAX_AGE_DAYS = {"annual": 550, "quarter": 200, "ytd": 300}
PEER_CAP = 5
US_ENRICHMENT_CAP = 3


def _ticker(value):
    text = value.upper() if isinstance(value, str) else ""
    return text if re.fullmatch(r"[A-Z0-9][A-Z0-9.^-]{0,19}", text) else None


def public_stock_mapping(doc):
    """Accept a public wrapper or raw ticker dict/list without mutating it.

    List entries require ticker; dict keys supply missing ticker. Invalid routes
    are omitted. Conflicting duplicates and key/embedded-ticker mismatches remain
    explicit held identities, never a last-write-wins financial record.
    """
    if isinstance(doc, dict):
        for key in ("stocks", "items", "holdings", "full"):
            if key in doc:
                doc = doc[key]
                break
    if isinstance(doc, dict):
        entries = doc.items()
    elif isinstance(doc, list):
        entries = ((s.get("ticker"), s) for s in doc if isinstance(s, dict))
    else:
        return {}
    out = {}
    for raw_ticker, stock in entries:
        ticker = _ticker(raw_ticker)
        if not ticker or not isinstance(stock, dict):
            continue
        value = dict(stock)
        supplied = value.get("ticker")
        if supplied is not None and _ticker(supplied) != ticker:
            value = {"ticker": ticker, "_peer_mapping_error": "candidate_identity_mismatch"}
        else:
            value["ticker"] = ticker
        if ticker in out and out[ticker] != value:
            value = {"ticker": ticker, "_peer_mapping_error": "ambiguous_stock_identity"}
        out[ticker] = value
    return out


def _dict(value):
    return value if isinstance(value, dict) else {}


def _financial_sector(stock):
    """Conservative exclusion from generic margins, never a company-name guess.

    A true flag or explicit financial classification wins over a false flag.
    Absence is reported as not_identified, not verified nonfinancial status.
    """
    stock = _dict(stock)
    evidence = []
    for prefix, obj in (("", stock), ("meta.", _dict(stock.get("meta"))),
                        ("financial_evidence.", _dict(stock.get("financial_evidence")))):
        if obj.get("is_financial") is True:
            evidence.append({"field": prefix + "is_financial", "value": True})
    for field in ("industry", "gics_industry", "gics_ko", "sector"):
        value = stock.get(field)
        if not isinstance(value, str):
            continue
        label = value.strip().lower()
        if (label in ("financial", "financials", "finance", "financial services", "금융", "금융업")
                or re.search(r"\b(banks?|banking|insurance|insurers?|brokerage|capital markets|consumer finance)\b", label)
                or any(word in label for word in ("은행", "보험", "증권", "금융지주", "여신", "캐피탈"))):
            evidence.append({"field": field, "value": value})
    return {"is_financial": bool(evidence),
            "status": "identified" if evidence else "not_identified", "basis": evidence}


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        return bool(parsed.scheme == "https" and parsed.hostname
                    and not parsed.username and not parsed.password
                    and parsed.path not in ("", "/"))
    except ValueError:
        return False


def _document_identity(url):
    """Identify a filing independently of its main/index/viewer filename.

    Known filing hosts fail closed on malformed identifiers; other HTTPS
    documents are comparable only by their complete, exact URL.
    """
    if not _url(url):
        return None
    parsed = urlparse(url)
    if parsed.hostname == "dart.fss.or.kr":
        receipts = parse_qs(parsed.query, keep_blank_values=True).get("rcpNo", [])
        if (parsed.path not in ("/dsaf001/main.do", "/report/viewer.do")
                or len(receipts) != 1 or not re.fullmatch(r"\d{14}", receipts[0])):
            return None
        return ("DART", receipts[0])
    if parsed.hostname in ("sec.gov", "www.sec.gov"):
        match = re.fullmatch(r"/Archives/edgar/data/(\d{1,10})/(\d{18}|\d{10}-\d{2}-\d{6})/([^/]+)", parsed.path)
        if not match or int(match[1]) <= 0 or match[3] in (".", ".."):
            return None
        return ("SEC", str(int(match[1])), match[2].replace("-", ""))
    return ("HTTPS", url)


def _same_document(row, source):
    parent = _document_identity(row.get("source_url"))
    metric = _document_identity(source.get("source_url"))
    if parent is None or parent != metric:
        return False
    if parent[0] == "HTTPS":
        return "accession" not in source or source["accession"] == row.get("accession")
    if parent[0] in ("DART", "SEC"):
        for obj in (row, source):
            accession = obj.get("accession")
            if accession is None:
                continue
            text = str(accession)
            if parent[0] == "DART":
                if text != parent[1]:
                    return False
            elif (not re.fullmatch(r"\d{18}|\d{10}-\d{2}-\d{6}", text)
                  or text.replace("-", "") != parent[2]):
                return False
    return True


def _standard(row):
    value = row.get("accounting_standard")
    if not isinstance(value, str):
        return None
    value = value.strip().upper().replace("_", "-")
    aliases = {"US GAAP": "US-GAAP", "USGAAP": "US-GAAP",
               "K IFRS": "K-IFRS", "KIFRS": "K-IFRS"}
    value = aliases.get(value, value)
    return None if value in ("", "UNKNOWN", "N/A", "미상", "미수신") else value


def _period_errors(row, today):
    errors = []
    try:
        valid = valid_period(row)
    except (AttributeError, ValueError, TypeError):
        valid = False
    if not valid or not _url(row.get("source_url")):
        errors.append("invalid_or_missing_period_basis")
    end, filed = _date(row.get("end")), _date(row.get("filed"))
    if filed is None:
        errors.append("missing_filed_date")
    elif filed > today or (end and filed < end):
        errors.append("invalid_filed_date")
    if end and end > today:
        errors.append("future_period")
    ceiling = MAX_AGE_DAYS.get(row.get("period_kind"))
    if end and ceiling and (today - end).days > ceiling:
        errors.append("stale_period")
    return errors


def _metrics(row, suppress_margins=False):
    out = {}
    sources = _dict(row.get("metric_sources"))
    for key in METRICS:
        source = _dict(sources.get(key))
        try:
            value = _number(row.get(key))
        except OverflowError:
            value = None
        reason = None
        if value is None:
            reason = "missing_or_nonfinite_value"
        elif (key == "revenue" and value < 0) or (key == "capex" and value < 0):
            reason = "negative_revenue" if key == "revenue" else "negative_capex_outflow"
        elif not (_url(source.get("source_url")) and
                  (source.get("tag") or source.get("account_id") or source.get("name")) and
                  source.get("start") == row.get("start") and
                  source.get("end") == row.get("end") and
                  (source.get("currency") or source.get("unit")) == row.get("currency")):
            reason = "missing_or_mismatched_metric_provenance"
        elif not _same_document(row, source):
            reason = "mismatched_metric_document_identity"
        elif any(k in source and source[k] != row.get(k)
                 for k in ("fs_div", "period_kind", "accounting_standard")):
            reason = "mismatched_metric_provenance"
        out[key] = {"value": value if reason is None else None,
                    "source": deepcopy(source), "reason": reason}
    for key, numerator in (("op_margin", "op"), ("net_margin", "net")):
        revenue, profit = out["revenue"]["value"], out[numerator]["value"]
        value = profit / revenue * 100 if (not suppress_margins and revenue is not None
                                           and revenue > 0 and profit is not None) else None
        if value is not None and not math.isfinite(value):
            value = None
        out[key] = {"value": value, "unit": "percent",
                    "source": {"formula": f"{numerator} / revenue * 100",
                               "numerator": deepcopy(out[numerator]["source"]),
                               "denominator": deepcopy(out["revenue"]["source"])},
                    "reason": ("financial_sector_margin_not_comparable" if suppress_margins else
                               None if value is not None else "requires_positive_revenue_and_sourced_profit")}
    return out


def _has_exact_period(stock, current):
    periods = _dict(_dict(stock).get("financial_evidence")).get("periods")
    return bool(all(current.get(k) is not None for k in FIELDS)
                and isinstance(periods, list)
                and any(isinstance(p, dict) and all(p.get(k) == current[k] for k in FIELDS)
                        for p in periods))


def _classification(stock, field):
    return _dict(stock.get("peer")).get("sector") if field == "peer.sector" else stock.get(field)


def _selection(target_ticker, target, stocks, reviewed, current):
    candidates, notes = [], []
    if reviewed is not None:
        seen = {target_ticker}
        for item in reviewed if isinstance(reviewed, list) else []:
            item = _dict(item)
            ticker = str(item.get("ticker") or "").upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            valid = all(isinstance(item.get(k), str) and item[k].strip()
                        for k in ("reason", "limitation")) and _url(item.get("source_url"))
            candidates.append((ticker, {"mode": "reviewed", "reason": item.get("reason"),
                "limitation": item.get("limitation"), "source_url": item.get("source_url"),
                "valid": bool(valid)}))
        if not candidates:
            notes.append("검수 후보 목록이 비어 자동 후보로 대체하지 않았습니다.")
        return candidates, notes, len(candidates)
    # Use the most specific shared classification; never rank by size or name.
    for field in ("industry", "gics_industry", "peer.sector", "gics_ko", "sector"):
        classification = _classification(target, field)
        if not isinstance(classification, str) or not classification.strip():
            continue
        if classification.strip().lower() in ("unknown", "n/a", "other", "기타", "미상", "업종 미상"):
            continue
        matches = [str(t) for t, s in stocks.items() if str(t) != target_ticker
                   and isinstance(s, dict) and _classification(s, field) == classification]
        if not matches:
            continue
        # Availability of this exact target period, then stable ticker order.
        # This does not establish metric validity or an economic quality rank.
        matches.sort(key=lambda t: (not _has_exact_period(stocks[t], current), t))
        for ticker in matches[:PEER_CAP]:
            candidates.append((ticker, {"mode": "same_industry_candidate", "field": field,
                "classification": classification, "reason": f"동일 공개 업종 분류: {classification}",
                "policy": "exact_target_period_then_ticker",
                "has_exact_target_period": _has_exact_period(stocks[ticker], current),
                "limitation": "넓은 업종 분류일 수 있으며 직접 경쟁사 여부는 검수하지 않았습니다.",
                "source_url": None, "valid": True}))
        notes.append("자동 후보는 대상 최신 기간의 시작·종료·기간종류·통화·재무제표 범위가 일치하는 입력 기간근거 보유 후보 우선, 각 그룹 안에서는 티커순으로 최대 5개를 선정합니다. 경제적 순위·이름·시가총액 순위나 직접 경쟁사 선정이 아닙니다.")
        return candidates, notes, len(matches)
    notes.append("명시적인 동일 업종 분류 후보가 없습니다.")
    return candidates, notes, 0


def normalized_peers(target_ticker, target_stock, target_reader, stocks, now, reviewed_peers=None):
    """Return a detached JSON-safe dict; inputs are never mutated.

    rows: selected peer records, each with status qualified/held, reasons,
      numeric_period_alignment (qualified/held), selection
      (reason/limitation/source_url), period, source_url, metrics
      (metric -> {value, source, reason}), accounting_standard_comparability
      (matched/basis_unknown/mismatch), caveats, ranking_allowed=False and
      median_allowed=False. Held rows expose null numeric values only.
    basis: exact target reader.current period, accounting_standard, freshness
      ceilings, target metrics, reasons. No fallback to an older target period.
    total/qualified/held count selected rows, not the whole market. selection
      reports eligible and omitted counts separately. Empty reviewed list is
      authoritative. Invalid reviewed entries remain held, never auto-replaced.

    Explicit accounting_standard is read only from each period, never inferred
    from CFS, country, ticker, currency, or SEC concept taxonomy. Unknown allows
    sourced numeric display with a caveat; known mismatch holds the peer.
    Any identified financial company in the selected comparison suppresses
    generic revenue-based margins for the entire table, retaining raw amounts.
    """
    if not isinstance(now, (date, datetime)):
        raise ValueError("now must be a date or datetime")
    today = now.date() if isinstance(now, datetime) else now
    ticker = str(target_ticker).upper()
    target, stocks = _dict(target_stock), public_stock_mapping(stocks)
    current = _dict(_dict(target_reader).get("current"))
    basis_errors = _period_errors(current, today)
    candidates, notes, eligible = _selection(ticker, target, stocks, reviewed_peers, current)
    target_sector = _financial_sector(target)
    financial_comparison = target_sector["is_financial"] or any(
        _financial_sector(stocks.get(key))["is_financial"] for key, _ in candidates)
    target_metrics = _metrics(current, financial_comparison)
    if not any(target_metrics[k]["value"] is not None for k in ("revenue", "op", "net")):
        basis_errors.append("no_sourced_target_income")
    target_standard = _standard(current)
    basis = {k: current.get(k) for k in FIELDS}
    basis.update(accounting_standard=target_standard, source_url=current.get("source_url"),
                 filed=current.get("filed"), reasons=basis_errors,
                 scope_basis=current.get("scope_basis"), metrics=target_metrics,
                 financial_sector=target_sector, margins_allowed=not financial_comparison,
                 max_age_days=dict(MAX_AGE_DAYS))
    if basis_errors:
        for metric in basis["metrics"].values():
            metric.update(value=None, reason="target_basis_held")
    rows = []
    for peer_ticker, selection in candidates:
        peer = _dict(stocks.get(peer_ticker))
        reasons = ["target_" + error for error in basis_errors]
        if not peer:
            reasons.append("candidate_not_in_public_feed")
        if not _ticker(peer_ticker):
            reasons.append("invalid_candidate_ticker")
        if bool(re.fullmatch(r"\d{6}", ticker)) != bool(re.fullmatch(r"\d{6}", peer_ticker)):
            reasons.append("candidate_market_mismatch")
        if peer.get("_peer_mapping_error"):
            reasons.append(peer["_peer_mapping_error"])
        if peer.get("ticker") and str(peer["ticker"]) != peer_ticker:
            reasons.append("candidate_identity_mismatch")
        if not selection["valid"]:
            reasons.append("invalid_reviewed_selection")
        periods = _dict(peer.get("financial_evidence")).get("periods")
        periods = [p for p in periods if isinstance(p, dict)] if isinstance(periods, list) else []
        exact = [p for p in periods if all(p.get(k) == current.get(k) for k in FIELDS)]
        selected = {}
        if not exact:
            reasons.append("missing_exact_target_period" if periods else "missing_financial_evidence")
            for field in FIELDS:
                if periods and not any(p.get(field) == current.get(field) for p in periods):
                    reasons.append(field + "_mismatch")
        else:
            # Preserve the newest filing as a whole; do not cherry-pick metrics.
            newest = max(str(p.get("filed") or "") for p in exact)
            finalists = [p for p in exact if str(p.get("filed") or "") == newest]
            selected = finalists[0]
            if any(p != selected for p in finalists[1:]):
                reasons.append("ambiguous_same_period_filing")
            reasons.extend(_period_errors(selected, today))
        standard = _standard(selected)
        accounting = "basis_unknown" if not target_standard or not standard else (
            "matched" if target_standard == standard else "mismatch")
        metrics = _metrics(selected, financial_comparison)
        if exact and not any(metrics[k]["value"] is not None for k in ("revenue", "op", "net")):
            reasons.append("no_sourced_income")
        numeric_alignment = "held" if reasons else "qualified"
        if accounting == "mismatch":
            reasons.append("accounting_standard_mismatch")
        if reasons:
            for metric in metrics.values():
                metric.update(value=None, reason="row_held")
        rows.append({"ticker": peer_ticker, "name": peer.get("name_ko") or peer.get("name"),
            "status": "held" if reasons else "qualified", "reasons": reasons,
            "numeric_period_alignment": numeric_alignment,
            "selection": selection, "period": {k: selected.get(k) for k in FIELDS},
            "available_periods": [{**{k: p.get(k) for k in (*FIELDS, "source_url", "filed")},
                                   "errors": _period_errors(p, today)} for p in periods] if not exact or reasons else [],
            "scope_basis": selected.get("scope_basis"),
            "financial_sector": _financial_sector(peer),
            "source_url": selected.get("source_url"), "filed": selected.get("filed"),
            "accounting_standard": standard, "accounting_standard_comparability": accounting,
            "caveats": (["회계기준 미수신: 숫자의 기간 정렬만 통과했으며 회계기준 비교 가능성은 미확인입니다. 순위·중앙값을 제공하지 않습니다."] if accounting == "basis_unknown" else [])
                + (["금융업이 포함되어 일반 기업식 매출 대비 영업·순이익률 비교를 보류했습니다."] if financial_comparison else []),
            "ranking_allowed": False, "median_allowed": False, "metrics": metrics})
    qualified = sum(r["status"] == "qualified" for r in rows)
    return {"rows": rows, "basis": basis, "total": len(rows), "qualified": qualified,
            "held": len(rows) - qualified,
            "selection": {"eligible": eligible, "selected": len(rows), "omitted": eligible - len(rows)},
            "notes": notes + ["통화변환·연율화·TTM 합성·EV/PER 산출·순위·중앙값을 수행하지 않습니다."]}


def _cik(value):
    text = str(value)
    return int(text) if re.fullmatch(r"\d{1,10}", text) and int(text) > 0 else None


def _us_enrichment(ticker, peer, fetch):
    """At most two existing fetch routes; no SEC filing-document download."""
    financial = False
    try:
        raw = fetch(f"us_financials/{ticker}.json")
        meta = _dict(_dict(raw).get("meta"))
        cik = _cik(meta.get("cik"))
        # Same ticker + positive 1..10 digit CIK gate as report_evidence._extract.
        if not isinstance(raw, dict) or str(raw.get("ticker", "")).upper() != ticker or not cik:
            return [], "us_financials_identity_mismatch", financial
        supplied_ciks = [peer[k] for k in ("cik", "sec_cik") if peer.get(k) is not None]
        if any(_cik(value) != cik for value in supplied_ciks):
            return [], "public_cik_mismatch", financial
        financial = _financial_sector({"meta": meta})["is_financial"]
        facts = fetch(f"sec-companyfacts/{cik:010d}.json")
        if not isinstance(facts, dict) or _cik(facts.get("cik")) != cik:
            return [], "companyfacts_cik_mismatch", financial
        rows = us_periods(raw, facts)
        return rows, "us_enriched" if rows else "us_financials_no_usable_periods", financial
    except Exception:
        # Raw provider errors may contain credentials or signed URLs.
        return [], "us_enrichment_failed", financial


def build_peer_comparison(ticker, target, reader, doc, now, reviewed_peers=None, fetch=None):
    """Select at most five peers before optional bounded enrichment.

    Accepts the raw public list/dict or its stocks/items/holdings/full wrapper.
    KR: only selected peers, using existing local reviewed_financials registry.
    US: only selected peers lacking an exact target FIELDS period; at most three
      candidates, three workers and six fetch calls total. Uses only existing
      us_financials/{ticker}.json and sec-companyfacts/{cik:010d}.json routes.
      The supplied fetch owns caching/timeouts; this helper has no network client.
    Identity failures, fetch failures and budget omissions retain held rows and
    an enrichment status. No enrichment is attempted for an invalid target basis.
    Returns normalized_peers contract plus row.enrichment and top-level
    enrichment limits/counts. Reviewed selection is capped at five here too.
    Financial-sector flags/classifications also suppress generic margins; callers
    can pass target.is_financial=True when the target SEC meta identifies it.
    """
    ticker = str(ticker).upper()
    stocks = public_stock_mapping(doc)
    initial = normalized_peers(ticker, target, reader, stocks, now, reviewed_peers)
    chosen = initial["rows"][:PEER_CAP]
    # Freeze selection. No new candidate is substituted after enrichment fails.
    working = {r["ticker"]: deepcopy(stocks[r["ticker"]]) for r in chosen if r["ticker"] in stocks}
    statuses, jobs = {}, []
    current = _dict(_dict(reader).get("current"))
    for row in chosen:
        key = row["ticker"]
        peer = working.get(key)
        if initial["basis"]["reasons"]:
            statuses[key] = "target_basis_held"
        elif (not peer or not row["selection"]["valid"] or not _ticker(key)
              or any(reason in row["reasons"] for reason in (
                  "candidate_identity_mismatch", "ambiguous_stock_identity", "candidate_market_mismatch"))):
            statuses[key] = "candidate_identity_or_selection_held"
        elif re.fullmatch(r"\d{6}", ticker):
            try:
                existing = _dict(peer.get("financial_evidence"))
                periods = existing.get("periods")
                periods = periods if isinstance(periods, list) else []
                restored = reviewed_financials(key, peer, periods, now)
                peer["financial_evidence"] = {**existing, "periods": restored}
                statuses[key] = "kr_review_applied" if restored != periods else "kr_review_no_change"
            except Exception:
                statuses[key] = "kr_review_failed"
        else:
            if _has_exact_period(peer, current):
                statuses[key] = "existing_exact_period"
            elif not callable(fetch):
                statuses[key] = "fetch_unavailable"
            elif len(jobs) >= US_ENRICHMENT_CAP:
                statuses[key] = "us_enrichment_cap_reached"
            else:
                jobs.append(key)
    if jobs:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda key: _us_enrichment(key, working[key], fetch), jobs))
        for key, (restored, status, financial) in zip(jobs, results):
            statuses[key] = status
            if financial:
                working[key]["meta"] = {**_dict(working[key].get("meta")), "is_financial": True}
            if restored:
                evidence = _dict(working[key].get("financial_evidence"))
                existing = evidence.get("periods")
                existing = existing if isinstance(existing, list) else []
                working[key]["financial_evidence"] = {**evidence, "periods": existing + restored}
    # Explicit reviewed records retain their original selection reason/limitation;
    # auto rows also keep their original classification provenance below.
    frozen = [{"ticker": r["ticker"], "reason": r["selection"]["reason"],
               "limitation": r["selection"]["limitation"],
               "source_url": r["selection"]["source_url"]}
              for r in chosen]
    result = normalized_peers(ticker, target, reader, working, now,
                              frozen if reviewed_peers is not None else None)
    # Enrichment can change period availability. Keep the original selected
    # order and attach selection evidence by ticker, never a reordered zip.
    by_ticker = {row["ticker"]: row for row in result["rows"]}
    result["rows"] = [by_ticker[row["ticker"]] for row in chosen]
    for row, original in zip(result["rows"], chosen):
        row["selection"] = original["selection"]
        row["enrichment"] = statuses.get(row["ticker"], "not_attempted")
        if row["status"] == "held" and row["enrichment"] not in (
                "existing_exact_period", "kr_review_no_change", "kr_review_applied", "us_enriched"):
            row["reasons"].append(row["enrichment"])
    result["qualified"] = sum(r["status"] == "qualified" for r in result["rows"])
    result["held"] = result["total"] - result["qualified"]
    result["selection"] = {"eligible": initial["selection"]["eligible"], "selected": len(chosen),
                           "omitted": initial["selection"]["eligible"] - len(chosen)}
    result["notes"] = initial["notes"] + ["보강은 선정 후보 최대 5개, 미국 조회는 최대 3개·후보당 2회로 제한합니다."]
    result["enrichment"] = {"peer_cap": PEER_CAP, "us_candidate_cap": US_ENRICHMENT_CAP,
                            "max_workers": 3, "us_attempted": len(jobs), "max_fetch_calls": 6}
    return result

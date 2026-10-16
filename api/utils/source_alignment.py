"""Private operator diagnostics for the exact financial inputs already selected.

Alignment checks identity, disclosure, dates, units and duration. It does not
certify accounting truth, infer missing periods, fetch data, or replace scalars.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _day(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def sec_input(row, *, ticker, cik, concept, instant=False):
    return {"ticker": ticker, "issuer_id": str(cik).zfill(10) if str(cik).isdigit() else None,
            "document_id": row.get("accn"), "filed": row.get("filed"),
            "start": None if instant else row.get("start"), "end": row.get("end"),
            "period_kind": "instant" if instant else "annual",
            "unit": "USD", "concept": concept, "form": row.get("form"),
            "raw_value": row.get("val"), "amount_field": "val"}


def dart_input(row):
    # Keep actual dates including non-calendar years; never infer Jan 1 from bsns_year.
    dates = re.findall(r"(20\d{2})[.\-/](\d{2})[.\-/](\d{2})", str(row.get("thstrm_dt") or ""))
    dates = ["-".join(parts) for parts in dates]
    instant = row.get("sj_div") == "BS"
    return {"ticker": row.get("stock_code"), "issuer_id": row.get("corp_code"),
            "document_id": row.get("rcept_no"),
            "filed": (str(row.get("rcept_no"))[:4] + "-" + str(row.get("rcept_no"))[4:6] + "-" + str(row.get("rcept_no"))[6:8]) if row.get("rcept_no") else None,
            "start": dates[0] if len(dates) == 2 and not instant else None,
            "end": dates[-1] if dates else None,
            "period_kind": "instant" if instant else "annual" if row.get("reprt_code") == "11011" else "reported_duration",
            "unit": row.get("currency"), "concept": row.get("account_id") or row.get("account_nm"),
            "form": row.get("reprt_code"), "fs_div": row.get("fs_div"),
            "raw_value": row.get("thstrm_amount"), "amount_field": "thstrm_amount"}


def field_evidence(value, *, source, ticker, issuer_id, definition, unit, inputs):
    return {"value": value, "source": source, "ticker": str(ticker),
            "issuer_id": str(issuer_id), "definition": definition, "unit": unit,
            "inputs": inputs, "observed_at": datetime.now(timezone.utc).isoformat()}


def _check(value, evidence, stock, expected_issuer=None, expected_unit=None):
    # Diagnostics must never abort the scorer on malformed cached JSON metadata.
    try:
        return _check_metadata(value, evidence, stock, expected_issuer, expected_unit)
    except (TypeError, ValueError, AttributeError, OverflowError):
        return {"status": "unknown", "reasons": ["malformed_source_evidence"],
                "source": None, "definition": None}


def _check_metadata(value, evidence, stock, expected_issuer=None, expected_unit=None):
    out = {"status": "unknown", "reasons": [], "source": None, "definition": None}
    if not finite(value):
        out.update(status="missing", reasons=["no_finite_selected_input"])
        return out
    if not isinstance(evidence, dict):
        out["reasons"] = ["selected_input_has_no_source_evidence"]
        return out
    for key in ("source", "ticker", "issuer_id", "definition", "unit", "observed_at"):
        if evidence.get(key) is not None and not isinstance(evidence[key], str):
            out["reasons"] = ["malformed_source_evidence"]
            return out
    for row in evidence.get("inputs") or []:
        if isinstance(row, dict) and any(
            row.get(key) is not None and not isinstance(row[key], str)
            for key in ("ticker", "issuer_id", "document_id", "filed", "start", "end",
                        "period_kind", "unit", "concept", "form", "fs_div")
        ):
            out["reasons"] = ["malformed_source_evidence"]
            return out
    source = evidence.get("source")
    out.update(source=source, definition=evidence.get("definition"), unit=evidence.get("unit"))
    unknown, mismatch = [], []
    if source not in ("SEC", "DART"):
        unknown.append("unsupported_or_unidentified_primary_source")
    ticker = str(stock.get("ticker") or "")
    if str(evidence.get("ticker") or "") != ticker:
        mismatch.append("ticker_mismatch")
    if not finite(evidence.get("value")) or evidence.get("value") != value:
        mismatch.append("selected_value_mismatch")
    issuer = str(evidence.get("issuer_id") or "")
    if not issuer:
        unknown.append("issuer_id_missing")
    out["issuer_id"] = issuer or None
    out["observed_at"] = evidence.get("observed_at")
    observed = str(evidence.get("observed_at") or "")
    observed_day = _day(observed[:10])
    if observed_day is None:
        unknown.append("source_observed_at_missing")
    if expected_issuer and issuer.zfill(10) != str(expected_issuer).zfill(10):
        mismatch.append("issuer_id_mismatch")
    if not evidence.get("definition") or not evidence.get("unit"):
        unknown.append("definition_or_output_unit_missing")
    definition_unit = "percent" if evidence.get("definition") in (
        "long_term_plus_short_borrowings_over_equity",
        "total_liabilities_over_assets_minus_liabilities",
        "annual_net_income_over_closing_equity", "annual_operating_profit_over_revenue"
    ) else None
    expected_unit = expected_unit or definition_unit
    if expected_unit and evidence.get("unit") != expected_unit:
        mismatch.append("output_unit_mismatch")
    inputs = evidence.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        inputs = []
        unknown.append("source_operands_missing")
    docs, ends, starts, units, kinds, fs_divs = set(), set(), set(), set(), set(), set()
    contexts = []
    for row in inputs:
        if not isinstance(row, dict):
            unknown.append("source_operand_missing")
            continue
        contexts.append({k: row.get(k) for k in ("document_id", "filed", "start", "end", "period_kind", "unit", "concept", "form", "fs_div")})
        if str(row.get("ticker") or "") != ticker:
            mismatch.append("source_ticker_mismatch")
        if not row.get("issuer_id"):
            unknown.append("source_response_issuer_missing")
        elif str(row.get("issuer_id")).zfill(10) != issuer.zfill(10):
            mismatch.append("source_issuer_mismatch")
        if not row.get("document_id") or not row.get("concept"):
            unknown.append("document_or_concept_missing")
        else:
            docs.add(row["document_id"])
        filed, end = _day(row.get("filed")), _day(row.get("end"))
        if filed is None or end is None:
            unknown.append("filing_or_period_date_missing")
        elif filed < end:
            mismatch.append("filed_before_period_end")
        if filed and observed_day and filed > observed_day:
            mismatch.append("filing_after_source_observation")
        if end:
            ends.add(end)
        unit = row.get("unit")
        if not unit:
            unknown.append("source_unit_missing")
        else:
            units.add(unit)
            if unit != stock.get("currency"):
                mismatch.append("source_currency_mismatch")
        kind = row.get("period_kind")
        kinds.add(kind)
        if kind != "instant":
            start = _day(row.get("start"))
            if start is None or end is None:
                unknown.append("duration_start_or_end_missing")
            else:
                starts.add(start)
                days = (end - start).days
                if kind != "annual" or not 350 <= days <= 380:
                    mismatch.append("annual_quarter_or_cumulative_definition_mismatch")
        if source == "DART":
            fs_divs.add(row.get("fs_div"))
            if row.get("fs_div") not in ("CFS", "OFS"):
                unknown.append("financial_statement_scope_missing")
        raw = row.get("raw_value")
        if isinstance(raw, str):
            try:
                raw = float(raw.replace(",", ""))
            except ValueError:
                raw = None
        if not finite(raw):
            unknown.append("unmeasured_source_operand")
    if len(docs) > 1:
        mismatch.append("mixed_disclosures")
    if len(ends) > 1 or len(starts) > 1:
        mismatch.append("mixed_accounting_periods")
    if len(units) > 1:
        mismatch.append("mixed_source_units")
    if len(fs_divs) > 1:
        mismatch.append("mixed_financial_statement_scopes")
    out["contexts"] = contexts
    out["reasons"] = sorted(set(mismatch + unknown))
    out["status"] = "mismatch" if mismatch else "unknown" if unknown else "aligned"
    return out


def source_alignment(stock):
    """Check exact Graham source choices and supplied top-level accounting inputs."""
    is_us = stock.get("currency") == "USD"
    sec = stock.get("sec_financials") or {}
    sec = sec if isinstance(sec, dict) else {}
    kis = stock.get("kis_financial_ratio") or {}
    kis = kis if isinstance(kis, dict) and kis.get("source") == "kis" else {}
    top = stock.get("fundamental_source_evidence") or {}
    top = top if isinstance(top, dict) else {}
    sec_ev = sec.get("_source_evidence") or {}
    sec_ev = sec_ev if isinstance(sec_ev, dict) else {}
    fields = {}
    for key in ("debt_ratio", "roe", "current_ratio"):
        if is_us and (sec.get(key) or key == "current_ratio"):
            value, ev = sec.get(key), sec_ev.get(key)
            identity = sec.get("_source_identity") or {}
            issuer = identity.get("cik") if isinstance(identity, dict) else None
        elif not is_us and kis:
            value, ev, issuer = kis.get(key), None, None
        elif key == "current_ratio":
            value, ev, issuer = None, None, None
        else:
            value, ev, issuer = stock.get(key), top.get(key), None
        fields["graham_value." + key] = _check(value, ev, stock, issuer, "percent")
    for key in ("revenue", "operating_profit", "net_income", "operating_cashflow", "operating_margin"):
        fields["stock." + key] = _check(stock.get(key), top.get(key), stock,
                                              expected_unit="percent" if key == "operating_margin" else stock.get("currency"))
    statuses = [row["status"] for row in fields.values()]
    aligned = statuses.count("aligned")
    status = ("mismatch" if "mismatch" in statuses else "aligned" if aligned == len(fields)
              else "partial" if aligned else "unknown" if "unknown" in statuses else "missing")
    return {"schema": "source-alignment-v1", "status": status,
            "aligned_fields": aligned, "field_count": len(fields), "fields": fields,
            "diagnostic_only": True, "is_truth_verified": False,
            "scope": "selected Graham accounting inputs and top-level accounting fields; excludes price ratios, estimates and non-accounting axes"}


def attach_source_alignment(stock):
    diagnostic = source_alignment(stock)
    stock["source_alignment"] = diagnostic
    return diagnostic

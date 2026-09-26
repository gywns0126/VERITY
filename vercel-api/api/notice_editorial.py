"""Editorial metadata only. Publication RLS and creation/audit timestamps stay unchanged."""
from datetime import date
import re

FIELDS = ("display_date", "home_visible", "related_tickers", "related_topics")
TOPICS = ("13f", "report", "disclosure", "macro")
TICKER = re.compile(r"[A-Z0-9][A-Z0-9.^/-]{0,19}\Z")


def editorial_payload(body):
    result = {}
    for key in FIELDS:
        if key not in body:
            continue
        value = body[key]
        if key == "display_date":
            if value in (None, ""):
                value = None
            elif not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("invalid_display_date")
            else:
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError("invalid_display_date") from exc
        elif key == "home_visible":
            if not isinstance(value, bool):
                raise ValueError("home_visible_must_be_boolean")
        else:
            if not isinstance(value, list) or len(value) > 20 or any(not isinstance(v, str) for v in value):
                raise ValueError("invalid_" + key)
            value = list(dict.fromkeys(v.strip().upper() if key == "related_tickers" else v.strip().lower() for v in value))
            if any(not (TICKER.fullmatch(v) if key == "related_tickers" else v in TOPICS) for v in value):
                raise ValueError("invalid_" + key)
        result[key] = value
    return result


def public_metadata(row):
    return {"display_date": row.get("display_date") or "", "home_visible": row.get("home_visible") is True,
            "related_tickers": row.get("related_tickers") or [], "related_topics": row.get("related_topics") or []}


def editorial_query(qs):
    placement = qs.get("placement", [""])[0]
    if placement == "home":
        return {"home_visible": "eq.true", "order": "display_date.desc.nullslast,created_at.desc", "limit": "2"}
    if placement != "related":
        return {}
    ticker = qs.get("ticker", [""])[0].strip().upper()
    topics = [x for x in qs.get("topics", [""])[0].split(",") if x]
    parsed = editorial_payload({"related_tickers": [ticker] if ticker else [], "related_topics": topics})
    terms = (["related_tickers.cs.{" + ticker + "}"] if ticker else [])
    if parsed["related_topics"]:
        terms.append("related_topics.ov.{" + ",".join(parsed["related_topics"]) + "}")
    if not terms:
        raise ValueError("related_context_required")
    return {"or": "(" + ",".join(terms) + ")", "order": "display_date.desc.nullslast,created_at.desc", "limit": "2"}

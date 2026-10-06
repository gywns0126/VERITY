"""Private, read-only projection of the local analysis harness. Never public data.

Only the latest prepared packet per ticker is shown. A new pending packet must
not silently fall back to an older approved review. Raw facts stay local.
"""
from datetime import datetime, timezone
from pathlib import Path

from api.intelligence import analysis_harness as h


def build(*, runtime=h.RUNTIME, journal_path=None, now=None):
    now = now or datetime.now(timezone.utc)
    latest = {}
    for path in sorted((Path(runtime) / "packets").glob("*.json")):
        packet = h.load_packet(path.stem, runtime)
        ticker = packet["facts"]["ticker"]
        previous = latest.get(ticker)
        if previous is None or h.instant(packet["prepared_at"]) > h.instant(previous["prepared_at"]):
            latest[ticker] = packet
    items = {}
    for ticker, packet in latest.items():
        record = h.find_record(packet["packet_id"], journal_path)
        item = dict(packet_id=packet["packet_id"], ticker=ticker,
                    name=packet["facts"].get("name") or ticker,
                    prepared_at=packet["prepared_at"], facts_at=packet["facts_at"],
                    state="awaiting_review", sources=packet["sources"],
                    section_total=len(packet["sections"]), review=None)
        if record:
            review = record["review"]["submission"]
            coverage = h.validate_review(packet, review, now=now)
            if (record["ticker"] != ticker or record["facts_fingerprint"] != packet["facts_fingerprint"]
                    or record["verdict"] != review["verdict"]):
                raise ValueError("journal projection binding mismatch")
            item["state"] = "review_expired" if h.instant(review["valid_until"]) <= now else "reviewed"
            fields = ("verdict", "confidence", "reviewed_at", "valid_until", "reasoning_brief",
                      "counterevidence", "change_conditions", "limitations", "unresolved", "evidence")
            item["review"] = {key: review[key] for key in fields}
            item["review"].update(record_id=record["record_id"], coverage=coverage)
        items[ticker] = item
    return dict(schema="analysis-console-v1", generated_at=now.isoformat(), items=items,
                orders_authorized=False, monitoring_active=False, model_calls=0)

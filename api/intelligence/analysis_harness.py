"""Local research handoff: immutable facts -> explicit review -> existing journal.

No model, order, scheduler or deployment calls. Evidence verification is a
reviewer's attestation, not proof supplied by a URL or by this validator.
The source ledger reports representation in the bundle, NOT successful fetches.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from api.intelligence import decision_journal as journal
from api.intelligence import operator_context as context

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "private/decisions/analysis_harness"
SCHEMA = "analysis-harness-v1"


def instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return parsed
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("timezone-aware timestamp required") from exc


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing text: " + field)
    return value


def source_ledger(facts, root=ROOT):
    """Reuse the collector's declared registries without importing/calling it."""
    lists = context.literals(Path(root) / "api/intelligence/ticker_facts.py",
                             ("CORE_FILES", "SCAN_FILES", "LOCAL_FILES", "PRIVATE_FILES"))
    represented = {section["source"] for section in facts["sections"]}
    us = not re.fullmatch(r"[0-9]{6}", facts["ticker"])
    rows = {}
    for group, entries in lists.items():
        for entry in entries:
            source = entry if isinstance(entry, str) else entry[0]
            if group == "PRIVATE_FILES":
                source = "private:" + source
            name = Path(source).name
            excluded = group != "PRIVATE_FILES" and (
                (name.startswith("us_") and not us)
                or (name.startswith(("kr_", "dart_")) and us))
            state = "in_bundle" if source in represented else (
                "excluded_market" if excluded else "not_in_bundle")
            rows[source] = dict(source=source, group=group, state=state)
    for source in sorted(represented - rows.keys()):
        rows[source] = dict(source=source, group="additional_section", state="in_bundle")
    return dict(entries=list(rows.values()), total=len(rows),
                counts=dict(Counter(row["state"] for row in rows.values())),
                scope="declared file sources plus returned sections; not fetch or semantic coverage",
                limitations=["Direct probes with no returned section are not inventoried here.",
                             "not_in_bundle does not distinguish absence, failure, trimming or identity-only use."])


def build_packet(facts, question="", *, root=ROOT, now=None):
    # JSON round-trip both rejects non-finite values and severs caller mutation.
    facts = json.loads(context.encode(facts))
    if (not isinstance(facts, dict) or not isinstance(facts.get("ticker"), str)
            or not re.fullmatch(r"[A-Za-z0-9.^-]{1,20}", facts["ticker"])):
        raise ValueError("resolved ticker required")
    sections = facts.get("sections")
    if not isinstance(sections, list) or not isinstance(facts.get("missing"), list):
        raise ValueError("invalid facts bundle")
    now = now or datetime.now(timezone.utc)
    if not isinstance(facts.get("_meta"), dict):
        raise ValueError("collection metadata required")
    collected = instant(facts["_meta"].get("collected_at"))
    if collected > now:
        raise ValueError("future collection timestamp")
    ledger = []
    for i, section in enumerate(sections):
        if not isinstance(section, dict) or "data" not in section:
            raise ValueError("invalid section")
        text(section.get("source"), "source")
        text(section.get("label"), "label")
        ledger.append(dict(id=f"s{i + 1}", source=section["source"], label=section["label"],
                           as_of=section.get("as_of"),
                           freshness=context.freshness(section.get("as_of"), now, None)))
    packet = dict(schema=SCHEMA, question=question, facts=facts,
                  prepared_at=now.isoformat(), facts_at=collected.isoformat(),
                  sections=ledger, sources=source_ledger(facts, root),
                  facts_fingerprint=journal.facts_fingerprint(facts),
                  restrictions=dict(model_calls=0, orders_authorized=False,
                                    source_content_is_instructions=False))
    packet["packet_id"] = context.digest(packet)
    return packet


def verify_packet(packet):
    if not isinstance(packet, dict) or packet.get("schema") != SCHEMA:
        raise ValueError("invalid packet")
    body = {key: value for key, value in packet.items() if key != "packet_id"}
    if packet.get("packet_id") != context.digest(body):
        raise ValueError("packet digest mismatch")
    if journal.facts_fingerprint(packet["facts"]) != packet["facts_fingerprint"]:
        raise ValueError("facts fingerprint mismatch")
    return packet


def packet_path(runtime, packet_id):
    if not isinstance(packet_id, str) or not re.fullmatch(r"[0-9a-f]{64}", packet_id):
        raise ValueError("invalid packet id")
    return Path(runtime) / "packets" / (packet_id + ".json")


def save_packet(packet, runtime=RUNTIME):
    verify_packet(packet)
    path = packet_path(runtime, packet["packet_id"])
    Path(runtime).mkdir(parents=True, exist_ok=True, mode=0o700)
    with (Path(runtime) / "prepare.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            if context.read_json(path) != packet:
                raise ValueError("existing packet conflict")
        else:
            context.atomic_json(path, packet)
    return path


def load_packet(packet_id, runtime=RUNTIME):
    packet = verify_packet(context.read_json(packet_path(runtime, packet_id)))
    if packet["packet_id"] != packet_id:
        raise ValueError("packet filename mismatch")
    return packet


def prepare(query, question="", *, runtime=RUNTIME):
    # Explicit live preparation only. Review/status never recollect or call out.
    from api.intelligence.operator_ask import ask
    bundle = ask(query, question)
    packet = build_packet(bundle["facts"], question)
    save_packet(packet, runtime)
    return packet


def financial_reporting_periods(packet):
    """Only known annual-financial fields; filing dates are not fiscal periods."""
    result = {}
    for index, section in enumerate(packet["facts"]["sections"], 1):
        data = section["data"]
        rows = data if isinstance(data, list) else [data]
        periods = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("financials", "fin"):
                financials = row.get(key)
                if isinstance(financials, dict) and "period" in financials:
                    value = financials["period"]
                    value = str(value) if type(value) is int else value
                    periods.add(value if isinstance(value, str) and re.fullmatch(r"[0-9]{4}", value) else None)
        if periods:
            result[f"s{index}"] = next(iter(periods)) if len(periods) == 1 else None
    return result


def review_template(packet):
    verify_packet(packet)
    return dict(packet_id=packet["packet_id"], ticker=packet["facts"]["ticker"],
        reviewer="", reviewed_at="", valid_until="", identity_verified=False,
        verdict="", confidence="", basis_axes=[], reasoning_brief="",
        counterevidence="", change_conditions=[], limitations="", unresolved=[],
        acknowledged_gaps=[],
        financial_reporting_periods=financial_reporting_periods(packet),
        financial_period_rule="Non-hold financial basis evidence requires a matching reporting_period (YYYY); values remain reviewer attestations.",
        section_reviews=[dict(id=s["id"], status="pending", reason="", freshness="unknown")
                         for s in packet["sections"]], evidence=[])


def gap_ids(packet):
    return ([row["source"] for row in packet["sources"]["entries"] if row["state"] == "not_in_bundle"]
            + ["missing:" + str(i) for i in range(len(packet["facts"]["missing"]))])


def validate_review(packet, review, *, now=None):
    verify_packet(packet)
    now = now or datetime.now(timezone.utc)
    if not isinstance(review, dict) or review.get("packet_id") != packet["packet_id"]:
        raise ValueError("review packet mismatch")
    if review.get("ticker") != packet["facts"]["ticker"] or review.get("identity_verified") is not True:
        raise ValueError("identity verification required")
    for field in ("reviewer", "reasoning_brief", "counterevidence", "limitations"):
        text(review.get(field), field)
    reviewed = instant(review.get("reviewed_at"))
    expires = instant(review.get("valid_until"))
    if not instant(packet["prepared_at"]) <= reviewed <= now or expires <= reviewed:
        raise ValueError("invalid review time window")
    if review.get("verdict") not in journal.VERDICTS or review.get("confidence") not in journal.CONFIDENCES:
        raise ValueError("invalid verdict or confidence")
    for field in ("change_conditions", "unresolved", "basis_axes", "acknowledged_gaps"):
        values = review.get(field)
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError("invalid list: " + field)
        if len(values) != len(set(values)):
            raise ValueError("duplicate values: " + field)
    if not review["change_conditions"]:
        raise ValueError("change conditions required")
    if set(review["acknowledged_gaps"]) != set(gap_ids(packet)):
        raise ValueError("source gaps must be acknowledged explicitly")
    sections = {s["id"]: s for s in packet["sections"]}
    reviews = review.get("section_reviews")
    if not isinstance(reviews, list) or any(not isinstance(r, dict) for r in reviews):
        raise ValueError("section reviews required")
    if len(reviews) != len(sections) or {r.get("id") for r in reviews} != set(sections):
        raise ValueError("section review denominator mismatch")
    by_id = {r["id"]: r for r in reviews}
    for row in reviews:
        if row.get("status") not in ("reviewed", "not_used"):
            raise ValueError("unreviewed section")
        if row.get("freshness") not in ("sufficient", "historical", "stale", "unknown"):
            raise ValueError("invalid freshness assessment")
        text(row.get("reason"), "section review reason")
    basis = set(review["basis_axes"])
    if not basis.issubset(sections) or any(by_id[key]["status"] != "reviewed" for key in basis):
        raise ValueError("basis must reference reviewed sections")
    financial_periods = financial_reporting_periods(packet)
    evidence = review.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("evidence list required")
    supported = set()
    uncertain = bool(review["unresolved"])
    for item in evidence:
        if not isinstance(item, dict) or item.get("section_id") not in basis:
            raise ValueError("evidence must reference a basis section")
        for field in ("claim", "value", "source_as_of", "excerpt"):
            text(item.get(field), field)
        url = urlsplit(text(item.get("url"), "url"))
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise ValueError("invalid primary source URL")
        if item.get("source_kind") != "primary" or item.get("status") not in ("confirmed", "unresolved", "refuted"):
            raise ValueError("primary evidence attestation required")
        checked = instant(item.get("checked_at"))
        if not instant(packet["prepared_at"]) <= checked <= reviewed:
            raise ValueError("evidence check must occur during this review")
        try:
            source_date = datetime.fromisoformat(item["source_as_of"].replace("Z", "+00:00")).date()
        except ValueError as exc:
            raise ValueError("invalid evidence source date") from exc
        if source_date > checked.date():
            raise ValueError("future evidence source date")
        if item["status"] == "confirmed":
            section_id = item["section_id"]
            # Period matching does not verify the value/excerpt. The reviewer
            # still attests to those. Legacy hold reviews remain readable.
            period_required = (section_id in financial_periods
                               and (review["verdict"] != "보류" or "reporting_period" in item))
            if period_required and (financial_periods[section_id] is None
                                    or item.get("reporting_period") != financial_periods[section_id]):
                uncertain = True
            else:
                supported.add(section_id)
        else:
            uncertain = True
    uncertain = uncertain or supported != basis or not basis
    uncertain = uncertain or any(by_id[key]["freshness"] in ("stale", "unknown") for key in basis)
    if uncertain and (review["verdict"] != "보류" or review["confidence"] != "low"):
        raise ValueError("unresolved evidence permits only low-confidence hold")
    return dict(section_total=len(sections), reviewed=sum(r["status"] == "reviewed" for r in reviews),
                not_used=sum(r["status"] == "not_used" for r in reviews),
                primary_supported_basis=len(supported), basis_total=len(basis),
                unresolved=uncertain, verification="reviewer_attestation_not_machine_proof")


def find_record(packet_id, path=None):
    path = Path(path or journal.JOURNAL_PATH)
    if not path.exists():
        return None
    with path.open() as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        found = None
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("invalid journal row")
            if row.get("record_id") == "analysis:" + packet_id:
                if found is not None:
                    raise ValueError("duplicate analysis record")
                found = row
    return found


def finalize(packet_id, review, *, runtime=RUNTIME, journal_path=None, now=None):
    packet = load_packet(packet_id, runtime)
    coverage = validate_review(packet, review, now=now)
    now = now or datetime.now(timezone.utc)
    if instant(review["valid_until"]) <= now and find_record(packet_id, journal_path) is None:
        raise ValueError("review expired; prepare and review again")
    rec = journal.record(packet["facts"], review["verdict"], review["confidence"],
        review["basis_axes"], review["reasoning_brief"], packet["question"], path=journal_path,
        facts_at=instant(packet["facts_at"]), record_id="analysis:" + packet_id,
        review=dict(submission=review, coverage=coverage, packet_id=packet_id,
                    orders_authorized=False, model_calls=0))
    if find_record(packet_id, journal_path) != rec:
        raise ValueError("journal readback mismatch")
    return rec


def status(packet_id, *, runtime=RUNTIME, journal_path=None, now=None):
    packet = load_packet(packet_id, runtime)
    rec = find_record(packet_id, journal_path)
    state = "awaiting_review"
    if rec:
        until = instant(rec["review"]["submission"]["valid_until"])
        state = "review_expired" if until <= (now or datetime.now(timezone.utc)) else "reviewed"
    return dict(packet_id=packet_id, ticker=packet["facts"]["ticker"], state=state,
                verdict=rec.get("verdict") if rec else None,
                facts_at=packet["facts_at"], source_coverage=packet["sources"]["counts"],
                record_id=rec.get("record_id") if rec else None, orders_authorized=False,
                monitoring_active=False)


def compare(before, after):
    """Content changes are a re-review queue, never an automatic verdict."""
    verify_packet(before)
    verify_packet(after)
    if before["facts"]["ticker"] != after["facts"]["ticker"]:
        raise ValueError("cannot compare different tickers")
    def indexed(packet):
        grouped = {}
        for row in packet["facts"]["sections"]:
            grouped.setdefault(row["source"], []).append(row)
        return {key: context.digest(value) for key, value in grouped.items()}
    a, b = indexed(before), indexed(after)
    changed = sorted(key for key in a.keys() | b.keys() if a.get(key) != b.get(key))
    return dict(before=before["packet_id"], after=after["packet_id"], changed_sources=changed,
                missing_changed=before["facts"]["missing"] != after["facts"]["missing"],
                interpretation="changes_require_review_not_an_investment_signal")

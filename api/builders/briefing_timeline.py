"""Public briefing observations, preserved by KST day (no collection or LLM).

Only allowlisted, already-public briefing fields enter this archive. A snapshot
is what the builder observed, not a reconstructed historical source document.
Same-date source revisions and later observations are deliberately separate.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

KST = timezone(timedelta(hours=9))
ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "data" / "briefing_days"
SCHEMA_VERSION = 1
PHASES = ("pre", "open", "post", "closed")
# Reuse the explicitly verified range in AlphaTerminalCore.EXCHANGE_CLOCKS.
# Do not use market_calendar's unversioned CSV fallback (conflicting 2026 dates).
# No year rollover: an unverified day is unknown, never a presumed holiday.
CALENDAR_VERSION = "KRX-2026-verified-20260908"
CALENDAR_FROM = date(2026, 9, 8)
CALENDAR_TO = date(2026, 12, 31)
CALENDAR_SOURCE = "https://global.krx.co.kr/contents/GLB/06/0602/0602010201/GLB0602010201T1.jsp"
HOLIDAY_SOURCE = "https://www.kasa.go.kr/prog/bbsArticle/BBSMSTR_000000000010/view.do?bbsId=BBSMSTR_000000000010&nttId=B000000001860Pe2zT3"
HOLIDAYS = frozenset("2026-09-24 2026-09-25 2026-10-05 2026-10-09 2026-12-25 2026-12-31".split())
SPECIAL_UNVERIFIED = frozenset({"2026-11-19"})
CATEGORIES = frozenset({"market_recap", "us_filings", "earnings", "disclosures", "insider", "flow"})
# Existing public payloads predate section IDs. Exact known titles only; do not
# infer arbitrary categories or manufacture any missing historic source fields.
LEGACY_CATEGORIES = {
    "직전 거래일 시장": "market_recap", "밤사이 미국 공시": "us_filings",
    "이번 주 실적 공시 예상": "earnings", "최근 주요 공시": "disclosures",
    "최근 7일 내부자 변동": "insider", "외인·기관 동반 순매수": "flow",
}
ITEM_STRINGS = ("ticker", "name", "text", "title", "label", "date", "as_of")
VALUE_KEYS = {
    "market_recap": {"kospi_pct", "kosdaq_pct", "kospi_close", "kosdaq_close"},
    "flow": {"estimated_net_krw"}, "insider": {"shares_change"},
}


def calendar_contract() -> dict:
    return {"valid_from": CALENDAR_FROM.isoformat(), "valid_until": CALENDAR_TO.isoformat(),
            "holidays": sorted(HOLIDAYS), "unknown_dates": sorted(SPECIAL_UNVERIFIED),
            "open_minute": 540, "close_minute": 930,
            "source_urls": [CALENDAR_SOURCE, HOLIDAY_SOURCE], "verified_at": "2026-10-04",
            "version": CALENDAR_VERSION}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def trading_day(day: date) -> dict:
    result = {"status": "unknown", "calendar_version": CALENDAR_VERSION,
              "verified_from": CALENDAR_FROM.isoformat(), "verified_until": CALENDAR_TO.isoformat(),
              "source_url": CALENDAR_SOURCE, "holiday_source_url": HOLIDAY_SOURCE}
    if not CALENDAR_FROM <= day <= CALENDAR_TO:
        return {**result, "reason": "outside_verified_range"}
    if day.isoformat() in SPECIAL_UNVERIFIED:
        return {**result, "reason": "special_session_unverified"}
    closed = day.weekday() >= 5 or day.isoformat() in HOLIDAYS
    return {**result, "status": "closed" if closed else "open",
            "reason": "weekend" if day.weekday() >= 5 else "holiday" if closed else "scheduled_trading_day"}


def session_phase(now: datetime, calendar: dict) -> str:
    if calendar["status"] == "unknown":
        return "unknown"
    if calendar["status"] == "closed":
        return "closed"
    local = now.astimezone(KST)
    minute = local.hour * 60 + local.minute
    return "pre" if minute < 540 else "open" if minute < 930 else "post"


def _as_of(value) -> str:
    """Canonicalize a provided source date; never substitute collection time."""
    raw = str(value or "")
    if re.fullmatch(r"\d{8}", raw):
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    try:
        if len(raw) == 10:
            return date.fromisoformat(raw).isoformat()
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.isoformat() if parsed.tzinfo else ""
    except ValueError:
        return ""


def _public_url(value) -> str:
    raw = str(value or "")
    parsed = urlparse(raw)
    # Only source links produced by this builder. No tokens, arbitrary hosts or
    # signed/query URLs from a future private input can escape via this field.
    receipt = parse_qs(parsed.query).get("rcpNo", [""])[0]
    if parsed.scheme == "https" and parsed.hostname == "dart.fss.or.kr" and re.fullmatch(r"\d{14}", receipt):
        return "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt
    return ""


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _identity(item: dict, category: str) -> str:
    if category == "disclosures" and item.get("url"):
        return "dart:" + parse_qs(urlparse(item["url"]).query)["rcpNo"][0]
    if category == "flow" and item.get("ticker"):
        return "flow:" + item["ticker"]
    if category == "market_recap" and not item.get("ticker"):
        return "market_recap:" + _digest(item.get("name", ""))[:20]
    # No transaction/filing identity is provided by these source adapters.
    # Content identity is conservative: never merge two filings/trades on ticker.
    keys = (item.get("ticker"), item.get("name"), item.get("date"), item.get("text"), item.get("title"))
    return category + ":" + _digest(keys)[:24]


def public_snapshot(out: dict) -> tuple[list, list]:
    sections, normalized = [], []
    for section in out.get("sections", []):
        category = section.get("id") or LEGACY_CATEGORIES.get(section.get("title"))
        if category not in CATEGORIES:
            continue
        clean = {"id": category, "title": str(section.get("title") or ""), "items": []}
        if isinstance(section.get("note"), str):
            clean["note"] = section["note"]
        source_as_of = _as_of(section.get("as_of"))
        if source_as_of:
            clean["as_of"] = section["as_of"]
        recap = section.get("recap")
        if category == "market_recap" and isinstance(recap, dict):
            clean["recap"] = {k: v for k, v in recap.items()
                              if (k in {"date", "headline"} and isinstance(v, str))
                              or (k in {"kospi", "kosdaq", "kospi_close", "kosdaq_close"} and _finite(v))}
        for row in section.get("items", []):
            if not isinstance(row, dict):
                continue
            item = {key: row[key] for key in ITEM_STRINGS if isinstance(row.get(key), str)}
            for key in ("mover", "is_correction"):
                if isinstance(row.get(key), bool):
                    item[key] = row[key]
            link = _public_url(row.get("url"))
            if link:
                item["url"] = link
            values = row.get("values") or {}
            if isinstance(values, dict):
                values = {k: v for k, v in values.items() if k in VALUE_KEYS.get(category, set()) and _finite(v)}
                if values:
                    item["values"] = values
            clean["items"].append(item)
            norm = {"id": _identity(item, category), "category": category,
                    "title": item.get("title") or item.get("name") or clean["title"],
                    "text": item.get("text") or "",
                    "as_of": _as_of(item.get("as_of") or item.get("date")) or source_as_of}
            if category == "earnings":
                # A predicted event date is not an observation/source date.
                norm.update(event_date=_as_of(item.get("date")), date_kind="expected",
                            as_of=_as_of(item.get("as_of")) or source_as_of)
            for key in ("ticker", "name", "url", "values", "is_correction"):
                if key in item:
                    norm[key] = item[key]
            if category == "market_recap" and item.get("name") == "지수" and isinstance(recap, dict):
                # Legacy public recap already carries these numbers; copy them
                # without parsing rounded display text or rewriting the source row.
                source_values = {target: recap[source] for source, target in (
                    ("kospi", "kospi_pct"), ("kosdaq", "kosdaq_pct"),
                    ("kospi_close", "kospi_close"), ("kosdaq_close", "kosdaq_close"))
                    if _finite(recap.get(source))}
                if source_values:
                    norm["values"] = {**source_values, **norm.get("values", {})}
            normalized.append(norm)
        sections.append(clean)
    # Repeated source rows are not separate events; preserve original rows above.
    normalized = list({item["id"]: item for item in normalized}.values())
    return sections, normalized


def changes_since(snapshots: list, items: list) -> list:
    observed = {}
    for snapshot in snapshots:
        for item in snapshot["items"]:
            observed[item["id"]] = (snapshot["snapshot_id"], item)
    changes = []
    for item in items:
        prior = observed.get(item["id"])
        if not prior:
            changes.append({"id": item["id"], "kind": "correction" if item.get("is_correction") else "new", "after": item})
            continue
        previous_id, before = prior
        if before == item:
            continue
        same_basis = bool(item["as_of"]) and item["as_of"] == before["as_of"]
        kind = "observation"
        delta = {}
        if same_basis:
            a, b = before.get("values", {}), item.get("values", {})
            kind = "values_changed" if a != b else "text_changed"
            delta = {key: b[key] - a[key] for key in a.keys() & b.keys() if b[key] != a[key]}
        change = {"id": item["id"], "kind": kind, "previous_snapshot_id": previous_id,
                  "before": before, "after": item}
        if delta:
            change["delta"] = delta
        changes.append(change)
    return changes


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    # Corrupt/mismatched archives must fail the run, never silently reset history.
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported briefing archive: {path.name}")
    return value


def _write(path: Path, value: dict) -> None:
    encoded = _json(value) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == encoded:
        return
    fd, temporary = tempfile.mkstemp(prefix=".briefing-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(encoded)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def record_briefing(out: dict, archive_dir: Path | None = None) -> dict:
    """Append one real observation; seal previous observed days on the next run.

    Empty/missing historical dates are never synthesized. Re-running the exact
    same input is idempotent; an old-day replay cannot change a sealed summary.
    """
    now = datetime.fromisoformat(out["generated_at"].replace("Z", "+00:00"))
    if now.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    now = now.astimezone(KST)
    day = now.date().isoformat()
    if out["date"] != day:
        raise ValueError("briefing date must match the KST observation date")
    folder = Path(archive_dir) if archive_dir is not None else ARCHIVE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    calendar = trading_day(now.date())
    phase = session_phase(now, calendar)
    sections, items = public_snapshot(out)
    source_meta = {key: out[key] for key in ("date", "generated_at", "publish_at", "session", "recap_as_of", "weekday", "disclaimer")
                   if isinstance(out.get(key), str)}
    if _finite(out.get("warnings_n")):
        source_meta["warnings_n"] = out["warnings_n"]
    snapshot = {"generated_at": now.isoformat(), "phase": phase, "sections": sections, "items": items,
                "source_meta": source_meta,
                "source_as_of": sorted({item["as_of"] for item in items if item["as_of"]})}
    snapshot["snapshot_id"] = _digest(snapshot)
    path = folder / f"{day}.json"
    archive = _load(path) or {"schema_version": SCHEMA_VERSION, "date": day, "timezone": "Asia/Seoul",
                            "trading_day": calendar, "snapshots": [], "cards": dict.fromkeys(PHASES),
                            "day_summary": {"status": "open"}}
    if archive["date"] != day:
        raise ValueError("archive filename/date mismatch")
    prior = archive["snapshots"]
    exists = any(row["snapshot_id"] == snapshot["snapshot_id"] for row in prior)
    if not exists:
        if archive["day_summary"]["status"] == "closed":
            raise ValueError("Cannot append to a sealed briefing day")
        if prior and now < datetime.fromisoformat(prior[-1]["generated_at"]):
            raise ValueError("Cannot insert an out-of-order briefing observation")
        snapshot["changes"] = changes_since(prior, items)
        prior.append(snapshot)
        if phase in PHASES:
            archive["cards"][phase] = snapshot["snapshot_id"]
        _write(path, archive)
    days = []
    for day_path in sorted(folder.glob("????-??-??.json"), reverse=True):
        document = _load(day_path)
        if not document or not document.get("snapshots"):
            raise ValueError(f"Invalid briefing day: {day_path.name}")
        if document["date"] < day and document["day_summary"]["status"] != "closed":
            snapshots = document["snapshots"]
            document["day_summary"] = {
                "status": "closed", "generated_at": now.isoformat(),
                "cutoff_at": (date.fromisoformat(document["date"]) + timedelta(days=1)).isoformat() + "T00:00:00+09:00",
                "snapshot_ids": [row["snapshot_id"] for row in snapshots],
                "observed_changes": [{**change, "snapshot_id": row["snapshot_id"]}
                                     for row in snapshots for change in row["changes"]],
                "note": "보존된 관측분 종합 · 원천자료의 기준일은 각 항목에 표시",
            }
            _write(day_path, document)
        days.append({"date": document["date"], "trading_day": document["trading_day"],
                     "latest_at": document["snapshots"][-1]["generated_at"]})
    previous_index = _load(folder / "index.json")
    generated_at = max(now.isoformat(), (previous_index or {}).get("generated_at", ""))
    _write(folder / "index.json", {"schema_version": SCHEMA_VERSION, "generated_at": generated_at,
                                  "calendar": calendar_contract(), "days": days})
    return archive

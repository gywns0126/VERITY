#!/usr/bin/env python3
"""Run the optional shared-public extraction lane; never send a member portfolio.

--enable records local consent and runs a bounded batch. Later invocations reuse
that setting and the same durable budget/dedup ledger. Candidate results remain
local and unpublished; explicit cost-upload consent permits only the private
Google API cost summary to be uploaded.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.intelligence.portfolio_ai_fallback import (
    MODEL, PROVIDER, REASONING_EFFORT, _digest, _public_raw_answer, replay_answer,
    run_document, select_documents, validate_document,
    MONTH_BUDGET_KRW, BUDGET_KRW_PER_USD, MONTH_LIMIT_MICRO_USD, DAY_LIMIT_MICRO_USD,
)
from api.intelligence.portfolio_public_sources import PUBLIC_SOURCE_MAX_BYTES, _reject_duplicate_keys

STATE = ROOT / ".cache/portfolio-ai"
_UPLOAD_TIMEOUT_SECONDS = 10
_ARCHIVE_ROOT = Path("output/member-map-integration-20260927")
_REVIEW_ARCHIVE = _ARCHIVE_ROOT / "ai-connected-20261009/ai-review.json"
_CONTEXT_ARCHIVES = tuple(_ARCHIVE_ROOT / "ai-context-20261009" / name for name in (
    "20260319001343-response.json", "20260317000864-response.json",
))
_V2_REVIEW_ARCHIVE = _ARCHIVE_ROOT / "luna-harness-v2-20261009/ai-review.json"
_REVIEW_MAX_BYTES = 2_000_000
_REVIEW_MAX_ENTRIES = 100


def _check_local_path(path):
    # Check parents too: O_NOFOLLOW alone only protects the final component.
    relative = path.relative_to(ROOT)
    current = ROOT
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("local-ai-artifact-rejected")
    if path.exists() and not path.is_file():
        raise ValueError("local-ai-artifact-rejected")


def _read_archive(path):
    _check_local_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > _REVIEW_MAX_BYTES:
            raise ValueError("local-ai-archive-rejected")
        raw = handle.read(_REVIEW_MAX_BYTES + 1)
    if len(raw) > _REVIEW_MAX_BYTES:
        raise ValueError("local-ai-archive-rejected")
    return json.loads(raw, object_pairs_hook=_reject_duplicate_keys)


def _archive_entry(entry):
    """Check the saved wire shape, not whether old role judgments were correct."""
    if type(entry) is not dict or set(entry) != {"document", "answer"}:
        raise ValueError("local-ai-archive-rejected")
    validate_document(entry["document"])
    answer = entry["answer"]
    if (type(answer) is not dict or set(answer) != {"candidates"}
            or type(answer["candidates"]) is not list or len(answer["candidates"]) > 4):
        raise ValueError("local-ai-archive-rejected")
    for row in answer["candidates"]:
        fields = {"counterparty_id", "role", "quote"}
        if type(row) is dict and "context" in row:
            fields.add("context")
        if (type(row) is not dict or set(row) != fields
                or any(type(row[key]) is not str for key in ("counterparty_id", "role", "quote"))
                or row["role"] not in ("customer", "supplier")):
            raise ValueError("local-ai-archive-rejected")
        if "context" in row:
            context = row["context"]
            if (type(context) is not dict or set(context) != {"object_quote", "scale_quote", "time_quote"}
                    or any(value is not None and type(value) is not str for value in context.values())):
                raise ValueError("local-ai-archive-rejected")
    return entry


def read_archived_answers(*, entry_digests=None):
    """Only legacy100, two known contexts and the fixed one-document v2 capture."""
    try:
        body = _read_archive(ROOT / _REVIEW_ARCHIVE)
        if (type(body) is not dict or set(body) != {"schema", "entries"}
                or body["schema"] != "local-ai-review-input-v1"
                or type(body["entries"]) is not list or len(body["entries"]) > _REVIEW_MAX_ENTRIES):
            raise ValueError("local-ai-archive-rejected")
        archived = {}
        for entry in body["entries"]:
            entry = _archive_entry(entry)
            fingerprint = _digest(entry["document"])
            if fingerprint in archived:
                raise ValueError("local-ai-archive-rejected")
            archived[fingerprint] = entry
            if entry_digests is not None:
                entry_digests.add(_digest(entry))
        for relative in _CONTEXT_ARCHIVES:
            path = ROOT / relative
            _check_local_path(path)  # A dangling symlink is not an absent archive.
            if not path.exists():
                continue
            capture = _read_archive(path)
            if (type(capture) is not dict or set(capture) != {"scope", "document", "answer", "result"}
                    or type(capture["result"]) is not dict
                    or capture["result"].get("status") != "ok"
                    or any(capture["result"].get(key) != expected for key, expected in (
                        ("provider", PROVIDER), ("model", MODEL), ("reasoning_effort", REASONING_EFFORT)))):
                raise ValueError("local-ai-archive-rejected")
            entry = _archive_entry({"document": capture["document"], "answer": capture["answer"]})
            if entry["document"]["source_id"] != "source:dart:" + relative.name.removesuffix("-response.json"):
                raise ValueError("local-ai-archive-rejected")
            # A separately saved context response takes precedence over legacy
            # extraction for the EXACT document, without changing either archive.
            archived[_digest(entry["document"])] = entry
            if entry_digests is not None:
                entry_digests.add(_digest(entry))
        path = ROOT / _V2_REVIEW_ARCHIVE
        _check_local_path(path)
        if path.exists():
            capture = _read_archive(path)
            if (type(capture) is not dict or set(capture) != {"schema", "entries"}
                    or capture["schema"] != "local-ai-review-input-v1"
                    or type(capture["entries"]) is not list or len(capture["entries"]) != 1):
                raise ValueError("local-ai-archive-rejected")
            entry = _review_entry(capture["entries"][0])
            fingerprint = _digest(entry["document"])
            # Context precedence above is unchanged. This capture may only add
            # a distinct document or an exact answer copy, never choose a winner.
            if fingerprint in archived and _digest(archived[fingerprint]) != _digest(entry):
                raise ValueError("local-ai-archive-rejected")
            archived[fingerprint] = entry
            if entry_digests is not None:
                entry_digests.add(_digest(entry))
        return archived
    except (OSError, ValueError, TypeError, KeyError):
        # Never emit source text, decoder messages, paths or arbitrary keys.
        raise ValueError("local-ai-archive-rejected") from None


def _review_entry(entry):
    """Revalidate retained raw input, without promoting a rejected interpretation."""
    if type(entry) is not dict or set(entry) != {"document", "answer"}:
        raise ValueError("local-ai-review-rejected")
    validate_document(entry["document"])
    if _public_raw_answer(entry["answer"], entry["document"]) is None:
        raise ValueError("local-ai-review-rejected")
    answer = entry["answer"]
    for row in answer.get("claims", answer.get("candidates", [])):
        spans = [*row.get("context", {}).values(), row.get("scope_quote"),
                 row.get("channel_quote"), *row.get("counter_evidence_quotes", [])]
        # The loopback input has a stricter source-binding boundary than the
        # general raw-answer archive, which may retain invalid context for audit.
        if any(value is not None and value not in entry["document"]["text"] for value in spans):
            raise ValueError("local-ai-review-rejected")
    # Both legacy and v2 use today's gates. Semantic rejection is safe to retain;
    # the replay consumer must still withhold that candidate/claim.
    replay_answer(entry["answer"], entry["document"])
    return entry


def read_existing_review():
    """The single known local review is secondary to immutable public archives."""
    path = STATE / "latest-review.json"
    _check_local_path(path)
    if not path.exists():
        return {}
    try:
        body = _read_archive(path)
        if (type(body) is not dict or set(body) != {"schema", "entries"}
                or body["schema"] != "local-ai-review-input-v1"
                or type(body["entries"]) is not list or len(body["entries"]) > _REVIEW_MAX_ENTRIES):
            raise ValueError("local-ai-review-rejected")
        retained = {}
        for entry in body["entries"]:
            entry = _review_entry(entry)
            fingerprint = _digest(entry["document"])
            if fingerprint in retained:
                raise ValueError("local-ai-review-rejected")
            retained[fingerprint] = entry
        return retained
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError("local-ai-review-rejected") from None


def _save_review(entries):
    """Atomic, private loopback input; never a publication or ledger update."""
    path = STATE / "latest-review.json"
    _check_local_path(path)
    raw = (json.dumps({"schema": "local-ai-review-input-v1", "entries": entries},
                      ensure_ascii=False) + "\n").encode()
    if len(entries) > _REVIEW_MAX_ENTRIES or len(raw) > _REVIEW_MAX_BYTES:
        raise ValueError("local-ai-review-too-large")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=STATE, prefix=".latest-review-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        _check_local_path(path)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _publish_cost_summary(*, enabled, dry_run=False):
    """Publish only this local cost artifact after explicit, local consent."""
    if dry_run:
        return {"status": "skipped", "reason": "dry-run"}
    if not enabled:
        return {"status": "skipped", "reason": "disabled"}
    if PROVIDER != "google":
        # Do not silently label or upload OpenAI spending as Google spending.
        return {"status": "skipped", "reason": "provider-not-google"}
    if any(name in os.environ for name in ("CI", "GITHUB_ACTIONS", "VERCEL")):
        return {"status": "skipped", "reason": "non-local-environment"}
    state_dir = STATE
    ledger = state_dir / "ledger.sqlite3"
    settings = state_dir / "settings.json"
    if state_dir.is_symlink() or settings.is_symlink() or ledger.is_symlink() or not ledger.is_file():
        return {"status": "skipped", "reason": "local-ledger-unavailable"}
    try:
        consent = json.loads(settings.read_text(encoding="utf-8")) if settings.is_file() else {}
    except (OSError, ValueError):
        return {"status": "skipped", "reason": "consent-unavailable"}
    if not isinstance(consent, dict) or consent.get("enabled") is not True:
        return {"status": "skipped", "reason": "disabled"}
    if consent.get("cost_upload_enabled") is not True:
        return {"status": "skipped", "reason": "no-cost-upload-consent"}

    try:
        from dotenv import dotenv_values
        file_env = dotenv_values(ROOT / ".env")
    except Exception:
        file_env = {}
    upload_env = os.environ.copy()
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        value = os.environ.get(name) or file_env.get(name)
        if not isinstance(value, str) or not value.strip():
            return {"status": "unknown", "reason": "credentials-unavailable"}
        upload_env[name] = value.strip()

    uploader = ROOT / "scripts" / "upload_operator_data_to_supabase.py"
    try:
        result = subprocess.run(
            (sys.executable, str(uploader), "--only", "google_api_cost"),
            cwd=str(ROOT), env=upload_env, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=_UPLOAD_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "unknown", "reason": "timeout"}
    except Exception:
        return {"status": "unknown", "reason": "process-error"}
    if result.returncode == 0:
        return {"status": "published"}
    return {"status": "failed", "reason": "uploader-nonzero-exit"}


def read_sources():
    # Exactly two shared PUBLIC artifacts. No arbitrary filename/portfolio input.
    documents = {}
    for name in ("universe_search.json", "kr_business_overview_public.json"):
        descriptor = os.open(ROOT / "data" / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > PUBLIC_SOURCE_MAX_BYTES[name]:
                raise ValueError("public-artifact-rejected")
            raw = handle.read(PUBLIC_SOURCE_MAX_BYTES[name] + 1)
        if len(raw) > PUBLIC_SOURCE_MAX_BYTES[name]:
            raise ValueError("public-artifact-too-large")
        documents[name] = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    return documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true")
    group.add_argument("--disable", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error("limit must be between 1 and 10")
    if STATE.is_symlink():
        raise ValueError("state-directory-rejected")
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    settings = STATE / "settings.json"
    if settings.is_symlink():
        raise ValueError("settings-rejected")
    if args.enable or args.disable:
        prior = {}
        if settings.is_file():
            loaded = json.loads(settings.read_text())
            if isinstance(loaded, dict):
                prior = loaded
        prior.update({"enabled": args.enable, "model": MODEL,
                      "provider": PROVIDER, "reasoning_effort": REASONING_EFFORT})
        settings.write_text(json.dumps(prior) + "\n")
        os.chmod(settings, 0o600)
    settings_value = json.loads(settings.read_text()) if settings.exists() else {}
    if not isinstance(settings_value, dict):
        settings_value = {}
    enabled = settings_value.get("enabled") is True
    if not enabled and not args.dry_run:
        cost_publish = _publish_cost_summary(enabled=False)
        print(json.dumps({"status": "disabled", "calls": 0, "cost_publish": cost_publish}))
        return
    if enabled and not args.enable and not args.dry_run and not (STATE / "ledger.sqlite3").exists():
        raise ValueError("budget-ledger-missing")
    if enabled and not args.enable and not args.dry_run and (
            settings_value.get("model") != MODEL or settings_value.get("provider") != PROVIDER
            or settings_value.get("reasoning_effort") != REASONING_EFFORT):
        print(json.dumps({"status": "provider-consent-required", "calls": 0, "model": MODEL}))
        raise SystemExit(2)
    with_claims = (PROVIDER, MODEL, REASONING_EFFORT) == ("openai", "gpt-6-luna", "none")
    docs, coverage = select_documents(read_sources(), include_claims=with_claims)
    existing_review = read_existing_review() if with_claims else {}
    archive_entry_digests = set()
    archived = read_archived_answers(entry_digests=archive_entry_digests) if with_claims and (docs or existing_review) else {}
    if args.dry_run:
        cost_publish = _publish_cost_summary(enabled=enabled, dry_run=True)
        print(json.dumps({"status": "dry-run", "model": MODEL, "coverage": coverage,
                          "calls": 0, "cost_publish": cost_publish}))
        return
    # Archive-only replay does not need to load a credential at all.
    key, key_loaded, budget_ledger = None, False, None
    archived_pairs = {(entry["document"]["source_id"], entry["document"]["issuer_id"])
                      for entry in (*archived.values(), *existing_review.values())}
    counts, calls = Counter(), 0
    # read_existing_review has already replayed/validated every retained entry.
    # Only exact document+answer copies can leave local storage: their immutable
    # archive remains the owner, including legacy responses shadowed by context.
    archive_backed = {key for key, entry in existing_review.items() if _digest(entry) in archive_entry_digests}
    review_entries = {key: entry for key, entry in existing_review.items() if key not in archive_backed}
    review_unavailable = 0
    for doc in docs:
        fingerprint = _digest(doc)
        saved = archived.get(fingerprint, existing_review.get(fingerprint))
        if saved is None and (doc.get("source_id"), doc.get("issuer_id")) in archived_pairs:
            # A changed excerpt/shortlist for an already-paid filing is not a
            # newly authorized call, nor is it safe to attach the old answer.
            counts["archive-document-changed"] += 1
            continue
        if (with_claims and fingerprint not in review_entries and fingerprint not in archived
                and len(review_entries) >= _REVIEW_MAX_ENTRIES):
            # Do not pay for a result we cannot retain, or silently evict old input.
            # Keep validated results already obtained earlier in this batch.
            if review_entries != existing_review:
                _save_review(list(review_entries.values()))
            raise ValueError("local-ai-review-too-large")
        if saved is None and not key_loaded:
            # Existing key only; no global verdict, Pro or synthesis switches.
            from dotenv import dotenv_values
            key = os.environ.get("OPENAI_API_KEY") or dotenv_values(ROOT / ".env.local").get("OPENAI_API_KEY")
            if settings_value.get("budget_backend") == "supabase":
                from api.intelligence.portfolio_ai_budget_ledger import SupabaseBudgetLedger
                budget_env = dotenv_values(ROOT / ".env")
                budget_ledger = SupabaseBudgetLedger(
                    (os.environ.get("SUPABASE_URL") or budget_env.get("SUPABASE_URL", "")).rstrip("/"),
                    os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or budget_env.get("SUPABASE_SERVICE_ROLE_KEY", ""))
            key_loaded = True
        result = run_document(doc, STATE / "ledger.sqlite3", key, enabled=True, with_context=True,
                              with_claims=with_claims, archived_answer=saved, budget_ledger=budget_ledger)
        counts[result["status"]] += 1
        if with_claims and result["status"] in ("ok", "cached") and "raw_answer" in result:
            document, answer = result.get("document", doc), result["raw_answer"]
            if (type(document) is not dict or _digest(document) != fingerprint
                    or result.get("source_sha256") != fingerprint or type(answer) is not dict):
                raise ValueError("local-ai-review-unbound")
            entry = _review_entry({"document": document, "answer": answer})
            if _digest(entry) in archive_entry_digests:
                archive_backed.add(fingerprint)
            else:
                review_entries[fingerprint] = entry
        elif with_claims and result["status"] in ("ok", "cached"):
            review_unavailable += 1  # Do not invent raw answers for legacy ledger rows.
        if result["status"] in ("ok", "error"):
            calls += 1
        # Cache is free, but do not spin through auth/quota errors or retries.
        if result.get("budget_settlement") == "pending-reservation-retained":
            counts["budget-settlement-pending"] += 1
            break
        if calls >= args.limit or result["status"] in ("error", "budget-exhausted", "missing-key", "budget-ledger-unavailable", "result-store-unavailable", "disabled"):
            break
    retained = list(review_entries.values())
    if review_entries != existing_review:
        _save_review(retained)
    failed = bool(counts["error"] or counts["missing-key"] or counts["budget-ledger-unavailable"] or counts["result-store-unavailable"]
                  or counts["budget-settlement-pending"] or counts["disabled"])
    budget_stopped = bool(counts["budget-exhausted"])
    cost_publish = _publish_cost_summary(enabled=enabled)
    summary = {"status": "stopped" if failed or budget_stopped else "bounded-batch", "model": MODEL, "coverage": coverage,
               "provider": PROVIDER, "reasoning_effort": REASONING_EFFORT,
               "results": dict(counts), "calls": calls,
               "review_entries": len(retained), "review_omitted": 0,
               "review_archive_backed": len(archive_backed),
               "review_unavailable": review_unavailable,
               "monthly_reservation_usd": MONTH_LIMIT_MICRO_USD / 1_000_000,
               "daily_reservation_usd": DAY_LIMIT_MICRO_USD / 1_000_000,
               "monthly_budget_krw": MONTH_BUDGET_KRW,
               "budget_krw_per_usd": BUDGET_KRW_PER_USD,
               "budget_accounting": "fresh-valid-usage-settled-unknown-and-legacy-reserved",
               "cost_publish": cost_publish,
               "scope": "local-public-candidates-not-published-not-verified-edges"}
    (STATE / "last-run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    if failed:
        raise SystemExit(2)
    if budget_stopped:
        raise SystemExit(3)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)

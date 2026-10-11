"""Private public-source response archive; no model verdict can accept itself.

Only closed public documents and source-bound answers cross this boundary.
Derived grades/review receipts are never loaded from the archive. Current source
validators run again on recovery; neither a stored answer nor a DB success is a
semantic approval. Credentials/HTTP remain owned by the existing budget client.
"""
from copy import deepcopy
from datetime import date
import json

from .portfolio_ai_budget_ledger import BudgetLedgerUnavailable, _KEY

FIELDS = {"schema", "provider", "model", "reasoning_effort", "task_version",
          "assessed_as_of", "usage", "charge_micro_usd", "status", "raw_answer"}
USAGE_FIELDS = {"input_tokens", "output_tokens", "thinking_tokens", "cached_input_tokens"}


def check_envelope(body, doc):
    from . import portfolio_ai_fallback as ai, portfolio_business_judgment as business
    from .portfolio_ai_claims import VERSION as claim_version
    ai.validate_document(doc)
    if (type(body) is not dict or set(body) != FIELDS
            or body["schema"] != "portfolio-ai-result-v1"
            or (body["provider"], body["model"], body["reasoning_effort"])
                != (ai.PROVIDER, ai.MODEL, ai.REASONING_EFFORT)
            or body["task_version"] not in (ai.VERSION, ai.CONTEXT_VERSION, claim_version, business.VERSION)
            or body["status"] not in ("ok", "error")
            or type(body["charge_micro_usd"]) is not int
            or not 0 <= body["charge_micro_usd"] <= ai.RESERVE_MICRO_USD):
        raise ValueError("private-result-envelope")
    usage = body["usage"]
    if usage is not None and (type(usage) is not dict or set(usage) != USAGE_FIELDS
            or any(type(x) is not int or x < 0 for x in usage.values())
            or not usage["input_tokens"] or not usage["output_tokens"]
            or usage["cached_input_tokens"] > usage["input_tokens"]
            or usage["thinking_tokens"] > usage["output_tokens"]):
        raise ValueError("private-result-usage")
    if body["status"] == "ok" and usage is None:
        raise ValueError("private-result-usage")
    judgment = body["task_version"] == business.VERSION
    if judgment:
        stamp = body["assessed_as_of"]
        if type(stamp) is not str or date.fromisoformat(stamp).isoformat() != stamp or stamp < doc["as_of"]:
            raise ValueError("private-result-date")
    elif body["assessed_as_of"] is not None:
        raise ValueError("private-result-date")
    raw = body["raw_answer"]
    if raw is not None:
        safe = (business.safe_saved_judgment_answer(raw, [doc], as_of=body["assessed_as_of"])
                if judgment else ai._public_raw_answer(raw, doc))
        if safe is None or safe != raw:
            raise ValueError("private-result-answer")
    elif body["status"] == "ok":
        raise ValueError("private-result-answer-missing")
    if len(json.dumps({"document": doc, "result": body}, ensure_ascii=False).encode()) > 120000:
        raise ValueError("private-result-too-large")
    return deepcopy(body)


def pack_result(result, doc, version, charge):
    body = {"schema": "portfolio-ai-result-v1", "provider": result["provider"],
            "model": result["model"], "reasoning_effort": result["reasoning_effort"],
            "task_version": version, "assessed_as_of": result.get("assessed_as_of"),
            "usage": result.get("usage"), "charge_micro_usd": charge,
            "status": result["status"], "raw_answer": result.get("raw_answer")}
    return check_envelope(body, doc)


def replay_result(saved, doc, *, judgment_as_of=None):
    from . import portfolio_ai_fallback as ai, portfolio_business_judgment as business
    body = check_envelope(saved["result"], doc)
    if saved["document"] != doc:
        raise ValueError("private-result-source-mismatch")
    version = body["task_version"]
    if saved["key"] != ai._digest([ai.PROVIDER, ai.MODEL, ai.REASONING_EFFORT, version, doc]):
        raise ValueError("private-result-key-mismatch")
    if (judgment_as_of is not None) != (version == business.VERSION):
        raise ValueError("private-result-task-mismatch")
    raw = body["raw_answer"]
    if raw is None:
        validation = {"candidates": [], "reason": "archived-call-failed-no-safe-answer"}
    else:
        validation = (business.validate_company_judgments(raw, [doc], as_of=body["assessed_as_of"])
                      if judgment_as_of else ai.replay_answer(raw, doc))
    result = {**validation, "status": "cached", "original_status": body["status"],
              "provider": body["provider"], "model": body["model"],
              "reasoning_effort": body["reasoning_effort"], "usage": body["usage"],
              "source_sha256": ai._digest(doc), "budget_backend": "supabase",
              "result_archive": "restored", "provider_calls": 0,
              "published": False, "budget_settlement": "not-rechecked"}
    if raw is not None:
        result["raw_answer"] = deepcopy(raw)
    if judgment_as_of:
        result.update(assessed_as_of=body["assessed_as_of"], requested_as_of=judgment_as_of,
                      fresh_assessment=body["assessed_as_of"] == judgment_as_of)
    return result


class SupabaseResultStore:
    def __init__(self, budget):
        self._budget = budget

    def get(self, keys):
        if (type(keys) is not list or not 1 <= len(keys) <= 4
                or any(type(key) is not str or not _KEY.fullmatch(key) for key in keys)):
            raise BudgetLedgerUnavailable("result-store-keys")
        result = self._budget._rpc("get", {"p_keys": keys}, namespace="result", max_bytes=131072)
        if result == {"status": "missing"}:
            return None
        if (type(result) is not dict or set(result) != {"status", "key", "document", "result"}
                or result["status"] != "stored" or result["key"] not in keys):
            raise BudgetLedgerUnavailable("result-store-response")
        return result

    def put(self, key, reservation_id, doc, result):
        body = check_envelope(result, doc)
        response = self._budget._rpc("put", {"p_key": key, "p_reservation_id": reservation_id,
                                            "p_document": doc, "p_result": body}, namespace="result")
        if response not in ({"status": "stored", "key": key}, {"status": "already-stored", "key": key}):
            raise BudgetLedgerUnavailable("result-store-response")

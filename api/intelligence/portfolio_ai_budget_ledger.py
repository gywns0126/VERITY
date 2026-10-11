"""Private cost-only Supabase ledger. No source text, answers or member data.

The SQL RPC owns limits and UTC accounting. A failed/ambiguous reservation never
permits a provider call; an ambiguous settlement never releases its reservation.
There are no HTTP retries, redirects, local fallback, or credential logging.
"""
import json
import os
import re
import urllib.request
from uuid import UUID


PROJECT_URL = "https://lykqebdcurreppowulsl.supabase.co"
_KEY = re.compile(r"[0-9a-f]{64}\Z")


class BudgetLedgerUnavailable(RuntimeError):
    pass


class SupabaseBudgetLedger:
    def __init__(self, url, service_key):
        if url != PROJECT_URL or not isinstance(service_key, str) or not service_key.strip():
            raise BudgetLedgerUnavailable("budget-ledger-configuration")
        self._url, self._service_key = url, service_key

    @classmethod
    def from_environment(cls):
        if os.environ.get("PORTFOLIO_AI_LEDGER") != "supabase":
            raise BudgetLedgerUnavailable("budget-ledger-required")
        return cls(os.environ.get("SUPABASE_URL", "").rstrip("/"),
                   os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))

    def _rpc(self, name, payload, *, namespace="budget", max_bytes=8192):
        if namespace not in ("budget", "result") or max_bytes not in (8192, 131072):
            raise BudgetLedgerUnavailable("budget-ledger-configuration")
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        request = urllib.request.Request(
            self._url + "/rest/v1/rpc/portfolio_ai_" + namespace + "_" + name,
            data=json.dumps(payload).encode(), method="POST",
            headers={"apikey": self._service_key,
                     "Authorization": "Bearer " + self._service_key,
                     "Content-Type": "application/json"})
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
                raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ValueError()
            result = json.loads(raw)
            if type(result) is not dict:
                raise ValueError()
            return result
        except Exception:
            # Exception text/HTTP response can contain credentials or private
            # database diagnostics. Return only a fixed, non-sensitive code.
            raise BudgetLedgerUnavailable("budget-ledger-unavailable") from None

    def reserve(self, keys):
        if (type(keys) is not list or not 1 <= len(keys) <= 4
                or len(set(keys)) != len(keys)
                or any(type(k) is not str or not _KEY.fullmatch(k) for k in keys)):
            raise BudgetLedgerUnavailable("budget-ledger-keys")
        result = self._rpc("reserve", {"p_keys": keys})
        status = result.get("status")
        if status not in {"reserved", "already-reserved", "already-settled", "budget-exhausted", "disabled"}:
            raise BudgetLedgerUnavailable("budget-ledger-response")
        if status in {"reserved", "already-reserved", "already-settled"} and result.get("key") not in keys:
            raise BudgetLedgerUnavailable("budget-ledger-response")
        if status == "reserved":
            try:
                if result["key"] != keys[0]:
                    raise ValueError()
                UUID(result["reservation_id"])
            except (ValueError, TypeError, KeyError, AttributeError):
                raise BudgetLedgerUnavailable("budget-ledger-response") from None
        return result

    def settle(self, key, reservation_id, charged):
        if type(charged) is not int or not 0 <= charged <= 10000 or not _KEY.fullmatch(key):
            raise BudgetLedgerUnavailable("budget-ledger-charge")
        result = self._rpc("settle", {"p_key": key, "p_reservation_id": reservation_id,
                                      "p_charged": charged})
        if result.get("status") not in {"settled", "already-settled"}:
            raise BudgetLedgerUnavailable("budget-ledger-response")
        return result

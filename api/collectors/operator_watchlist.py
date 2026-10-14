"""Read only the private console owner's watchlist from the scheduled backend.

The owner predicate matches the private portfolio API. Public/anonymous access
remains governed by RLS; a server credential is never returned to callers.
"""
import logging
import os
from uuid import UUID

import requests


_logger = logging.getLogger(__name__)


def _uuid(value):
    return str(UUID(str(value)))


def fetch_operator_watch_items() -> list:
    """Fail closed unless exactly one private console owner can be resolved."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        _logger.warning("operator watchlist unavailable: backend configuration missing")
        return []

    headers = {"apikey": key, "Content-Type": "application/json"}
    # Modern secret keys are not JWTs. Legacy service-role keys still need the
    # bearer header; both forms are restricted to this server-side collector.
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    stage, status = "owner", None
    try:
        with requests.Session() as session:
            def read(table, params):
                nonlocal status
                status = None
                response = session.get(
                    f"{url}/rest/v1/{table}", headers=headers, params=params,
                    timeout=8, allow_redirects=False,
                )
                status = response.status_code
                if status != 200:
                    raise ValueError("unexpected backend response")
                rows = response.json()
                if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                    raise ValueError("invalid backend rows")
                return rows

            owners = read("profiles", {
                "select": "id,is_admin,is_super_admin",
                "is_admin": "eq.true", "is_super_admin": "eq.true", "limit": "2",
            })
            if (len(owners) != 1 or owners[0].get("is_admin") is not True
                    or owners[0].get("is_super_admin") is not True):
                raise ValueError("owner not uniquely resolved")
            owner_id = _uuid(owners[0].get("id"))
            stage = "groups"
            groups = read("watch_groups", {
                "select": "id,user_id", "user_id": f"eq.{owner_id}",
                "order": "id.asc", "limit": "201",
            })
            if len(groups) > 200 or any(_uuid(row.get("user_id")) != owner_id for row in groups):
                raise ValueError("invalid owner group boundary")
            group_ids = {_uuid(row.get("id")) for row in groups}
            if not group_ids:
                _logger.info("operator watchlist loaded: groups=0 items=0")
                return []
            stage = "items"
            items = read("watch_group_items", {
                "select": "group_id,ticker,name,market",
                "group_id": f"in.({','.join(sorted(group_ids))})",
                "order": "id.asc", "limit": "201",
            })
            if any(_uuid(row.get("group_id")) not in group_ids for row in items):
                raise ValueError("invalid watch item ownership")
            if len(items) > 200:
                _logger.warning("operator watchlist capped: selected=200 available_at_least=%d", len(items))
                items = items[:200]
            result = [{field: row.get(field, "") for field in ("ticker", "name", "market")}
                      for row in items]
            _logger.info("operator watchlist loaded: groups=%d items=%d", len(groups), len(result))
            return result
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        # Exception text and response bodies can contain credentials or user IDs.
        _logger.warning("operator watchlist unavailable: stage=%s status=%s", stage, status)
        return []

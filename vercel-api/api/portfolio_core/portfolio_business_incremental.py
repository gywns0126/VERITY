"""Bounded process-local memo for projected PUBLIC business rows only.

The public-index owner calls prepare under its lock for each new bundle, then
mentions/market_context. No selection, response, member value, artifact or
receipt is accepted or retained. This is an optimization of source computation,
not an alternative publisher trust boundary. Roles still run over the full
catalog; source validation, trie construction and aggregation still run too.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
import json
import re

from .portfolio_filing_excerpts import _legal_name
from .portfolio_market_context import index_filing_market_context
from .portfolio_prepared_business import artifact_sha256, implementation_sha256
from .portfolio_public_sources import safe_public_text


MAX_ROWS = 5000
MAX_COMPANIES = 50000
MAX_CHANGED_COMPANIES = 100
MAX_BYTES = 8 * 1024 * 1024
MAX_CATALOG_BYTES = 16 * 1024 * 1024
_ID = re.compile(r"KR:[0-9]{6}|US:[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?", re.ASCII)
_ROW_KEYS = {"issuer_id", "name", "text", "truncated", "fiscal_year", "source"}
_SOURCE_KEYS = {"id", "kind", "receipt_no", "as_of", "report_name", "url", "document_issuer"}


def _fold(text):
    # A conservative superset of both exact-name normalizations: removing
    # legal affixes, footnotes and whitespace can only cause extra misses.
    return _legal_name(text).casefold()


def _catalog_state(documents, by_id):
    if type(by_id) is not dict or len(by_id) > MAX_COMPANIES:
        raise ValueError("unbounded-public-catalog")
    state = {}
    for identifier, row in by_id.items():
        if (type(identifier) is not str or not _ID.fullmatch(identifier)
                or type(row) is not dict or row.get("id") != identifier
                or row.get("market") not in ("KR", "US")
                or not identifier.startswith(row["market"] + ":")):
            raise ValueError("invalid-public-catalog")
        names = row.get("source_names")
        if names is not None and (type(names) is not list or len(names) > 4):
            raise ValueError("unbounded-public-names")
        values = [row.get("name"), *(names or [])]
        if any(type(name) is not str or safe_public_text(name, 160) is None for name in values):
            raise ValueError("invalid-public-name")
        state[identifier] = [[identifier, row.get("market"), row.get("name"), names], [], values]
    declarations = documents.get("universe_search.json", {}).get("stocks", [])
    if type(declarations) not in (list, dict) or len(declarations) > MAX_COMPANIES:
        raise ValueError("unbounded-public-declarations")
    for row in declarations.values() if type(declarations) is dict else declarations:
        market = row.get("market")
        if market not in ("KR", "KONEX", "US"):
            continue
        identifier = f"{'KR' if market == 'KONEX' else market}:{row.get('ticker')}"
        if identifier not in state:
            continue
        names = [row.get("name"), row.get("name_ko")]
        if any(name is not None and (type(name) is not str or len(name) > 160) for name in names):
            raise ValueError("unbounded-public-name")
        state[identifier][1].append([market, row.get("ticker"), *names])
        state[identifier][2].extend(name for name in names if safe_public_text(name, 160) is not None)
    # Store exact closed input digests plus normalized PUBLIC invalidation hints.
    # No financial facts, documents, unknown fields or whole source are retained.
    result = {key: (artifact_sha256(value[:2]), frozenset(_fold(name) for name in value[2]))
              for key, value in state.items()}
    if sum(len(key) + 64 + sum(len(token.encode("utf-8")) for token in tokens)
           for key, (_, tokens) in result.items()) > MAX_CATALOG_BYTES:
        raise ValueError("unbounded-public-catalog")
    return result


class BusinessRowMemo:
    """One active public-row generation; caller supplies the public-index lock.

    Row keys bind the entire sanitized source, including receipt/correction,
    date, issuer name, truncation and fiscal year. Date/code changes invalidate
    everything. Catalog deltas invalidate mention hits AND misses on possible
    old/new alias substrings, including names which become ambiguous. More than
    100 changed identities clears mention results rather than guessing. Local
    market context depends on the source row and dates, not the name catalog.
    Capacity misses always compute normally; nothing is truncated downstream.
    """

    def __init__(self):
        self.clear()

    def clear(self):
        self._boundary = None
        self._catalog = {}
        self._rows = {}
        self._current = {}
        self._bytes = 0
        self._enabled = False

    def prepare(self, documents, by_id, business):
        """Validate current public inputs and discard removed/rejected rows."""
        self._enabled = False
        try:
            rows = business["rows"]
            if type(rows) is not list or len(rows) > MAX_ROWS:
                raise ValueError("unbounded-public-rows")
            current = {}
            for row in rows:
                if (type(row) is not dict or set(row) != _ROW_KEYS
                        or type(row["source"]) is not dict or set(row["source"]) != _SOURCE_KEYS
                        or not _ID.fullmatch(row["issuer_id"])
                        or safe_public_text(row["text"], 600) != row["text"]
                        or safe_public_text(row["name"], 160) != row["name"]):
                    raise ValueError("projected-public-row-required")
                current[row["issuer_id"]] = artifact_sha256(row)
            if len(current) != len(rows):
                raise ValueError("duplicate-public-issuer")
            boundary = (date.today().isoformat(), datetime.now(timezone.utc).date().isoformat(),
                        implementation_sha256())
            catalog = _catalog_state(documents, by_id)
            if boundary != self._boundary:
                self.clear()
            changed = {key for key in self._catalog.keys() | catalog.keys()
                       if self._catalog.get(key) != catalog.get(key)}
            tokens = ({token for key in changed for state in (self._catalog, catalog)
                       for token in state.get(key, (None, ()))[1]}
                      if len(changed) <= MAX_CHANGED_COMPANIES else set())
            kept = {}
            for issuer, entry in self._rows.items():
                if current.get(issuer) != entry["source"]:
                    continue
                if (len(changed) > MAX_CHANGED_COMPANIES or issuer in changed
                        or any(not token or token in entry["text"] for token in tokens)):
                    entry = {key: value for key, value in entry.items() if key != "mentions"}
                kept[issuer] = entry
            self._rows = kept
            self._bytes = sum(self._size(entry) for entry in kept.values())
            self._boundary, self._catalog = boundary, catalog
            self._current = current
            self._enabled = True
        except (AttributeError, KeyError, TypeError, ValueError, OSError, RecursionError, UnicodeError):
            self.clear()
        return self._enabled

    @staticmethod
    def _size(value):
        # Canonical ASCII JSON bounds retained payloads (not Python heap size).
        return len(json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False))

    def _get(self, row, field, compute):
        issuer = row["issuer_id"]
        source = self._current.get(issuer) if self._enabled else None
        # Never admit a different row between prepare and use.
        if source is None or artifact_sha256(row) != source:
            return compute()
        old = self._rows.get(issuer)
        if old is not None and field in old:
            return deepcopy(old[field])
        value = compute()
        entry = {**(old or {"source": source, "text": _fold(row["text"])}), field: deepcopy(value)}
        size = self._size(entry)
        previous_size = self._size(old) if old else 0
        if (len(self._rows) < MAX_ROWS or old is not None) and self._bytes - previous_size + size <= MAX_BYTES:
            self._rows[issuer] = entry
            self._bytes += size - previous_size
        return value

    def mentions(self, row, compute):
        """Memoize the existing matcher's (public IDs, ambiguity count), even misses."""
        return self._get(row, "mentions", compute)

    def market_context(self, business):
        """Reassemble the original context shape with today's aggregate coverage."""
        if not self._enabled:
            return index_filing_market_context(business)
        result = index_filing_market_context({"rows": [], "coverage": business["coverage"]})
        for row in business["rows"]:
            part = self._get(row, "context", lambda: index_filing_market_context({"rows": [row], "coverage": {}}))
            for target, source, field in (
                (result, part, "by_indicator"),
                (result["power"], part["power"], "by_role"),
                (result["infrastructure"], part["infrastructure"], "by_role"),
            ):
                for key, refs in source[field].items():
                    target[field][key].extend(refs)
        for target, field in ((result, "by_indicator"), (result["power"], "by_role"),
                              (result["infrastructure"], "by_role")):
            refs = target[field].values()
            target["coverage"].update(
                matched_issuers=len({ref["company_id"] for group in refs for ref in group}),
                references=sum(map(len, target[field].values())))
        return result

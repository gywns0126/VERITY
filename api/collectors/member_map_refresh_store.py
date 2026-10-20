"""공개 수집 상태 전용 저장소. 고정 프로젝트/RPC만 사용하며 재시도하지 않는다."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
import re
import threading
import time
from uuid import UUID

import requests

PROJECT_URL = "https://lykqebdcurreppowulsl.supabase.co"
CATALOG_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
CATALOG_MAX_BYTES = 16 * 1024 * 1024
STATE_MAX_BYTES = 4 * 1024 * 1024
ENVELOPE_MAX_BYTES = 16 * 1024
RESPONSE_MAX_BYTES = 3 * STATE_MAX_BYTES + ENVELOPE_MAX_BYTES
TABLE = "member_map_refresh_checkpoint"
RPC_TIMEOUT_SECONDS = 3
RPC_NAMES = frozenset(("member_map_refresh_claim", "member_map_refresh_renew", "member_map_refresh_save"))
SOURCES = frozenset(("DART", "SEC", "news"))
DART_REQUEST_BUDGET = 10
DART_DAILY_CAP = 8000


class RefreshStoreError(ValueError):
    """원문 응답·키·주소를 포함하지 않는 고정 오류 코드만 전달한다."""


SAFE_ERROR_CODES = frozenset((
    "refresh-cache-conflict", "refresh-catalog-rejected", "refresh-config-rejected",
    "refresh-http-failure", "refresh-http-unavailable", "refresh-http-rate-limited",
    "refresh-auth-rejected", "refresh-lease-lost", "refresh-owner-rejected",
    "refresh-payload-rejected", "refresh-read-busy", "refresh-read-rejected",
    "refresh-read-timeout", "refresh-response-rejected", "refresh-revision-rejected",
    "refresh-rpc-rejected", "refresh-save-conflict", "refresh-source-rejected",
    "refresh-state-rejected", "refresh-transport-failure", "refresh-transport-timeout",
))


def safe_error_code(error):
    """Only our closed vocabulary may cross the worker/log/health boundary."""
    if isinstance(error, RefreshStoreError) and len(error.args) == 1:
        code = error.args[0]
        if type(code) is str and code in SAFE_ERROR_CODES:
            return code
    return "refresh-unexpected-error"


def _json_bytes(value, limit):
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        if len(raw) > limit:
            raise ValueError
        return raw
    except (ValueError, TypeError, RecursionError, OverflowError, UnicodeError):
        raise RefreshStoreError("refresh-payload-rejected") from None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RefreshStoreError("refresh-response-rejected")
        result[key] = value
    return result


def _read_json_response(response, limit, deadline):
    if response.status_code != 200:
        # Never read/log an error body: it may contain SQL, credentials or URLs.
        if response.status_code in (401, 403):
            raise RefreshStoreError("refresh-auth-rejected")
        if response.status_code == 429:
            raise RefreshStoreError("refresh-http-rate-limited")
        if 500 <= response.status_code < 600:
            raise RefreshStoreError("refresh-http-unavailable")
        raise RefreshStoreError("refresh-http-failure")
    length = response.headers.get("Content-Length")
    if length is not None and (not re.fullmatch(r"[0-9]+", length) or int(length) > limit):
        raise RefreshStoreError("refresh-response-rejected")
    chunks, size = [], 0
    for chunk in response.iter_content(chunk_size=16384):
        size += len(chunk)
        if size > limit or time.monotonic() >= deadline:
            raise RefreshStoreError("refresh-response-rejected")
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks).decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise RefreshStoreError("refresh-response-rejected") from None


def _request_json(method, url, *, headers, body=None, limit=RESPONSE_MAX_BYTES, deadline=None):
    remaining = RPC_TIMEOUT_SECONDS if deadline is None else min(RPC_TIMEOUT_SECONDS, deadline - time.monotonic())
    if remaining <= 0:
        raise RefreshStoreError("refresh-read-timeout")
    deadline = deadline if deadline is not None else time.monotonic() + remaining
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.request(method, url, headers=headers, data=body,
                                 timeout=remaining, allow_redirects=False, stream=True) as response:
                if response.url != url:
                    raise RefreshStoreError("refresh-response-rejected")
                result = _read_json_response(response, limit, deadline)
                if time.monotonic() >= deadline:
                    raise RefreshStoreError("refresh-read-timeout")
                return result
    except RefreshStoreError:
        raise
    except requests.exceptions.Timeout:
        raise RefreshStoreError("refresh-transport-timeout") from None
    except Exception:
        raise RefreshStoreError("refresh-transport-failure") from None


def read_public_catalog():
    """고정된 기존 공개 카탈로그만 읽는다. 자격증명·호출자 URL은 받지 않는다."""
    result = _request_json("GET", CATALOG_URL, headers={"Accept": "application/json"}, limit=CATALOG_MAX_BYTES)
    if type(result) is not dict or not isinstance(result.get("stocks"), (dict, list)):
        raise RefreshStoreError("refresh-catalog-rejected")
    return result


def _source(value):
    if type(value) is not str or value not in SOURCES:
        raise RefreshStoreError("refresh-source-rejected")
    return value


def _owner(value):
    try:
        if type(value) is not str or str(UUID(value)) != value or UUID(value).int == 0:
            raise ValueError
        return value
    except (ValueError, AttributeError):
        raise RefreshStoreError("refresh-owner-rejected") from None


def _integer(value, *, positive=False):
    if type(value) is not int or not (int(positive) <= value < 9007199254740991):
        raise RefreshStoreError("refresh-revision-rejected")
    return value


def _instant(value):
    try:
        if type(value) is not str or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value):
            raise ValueError
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError
        return stamp
    except (ValueError, OverflowError):
        raise RefreshStoreError("refresh-state-rejected") from None


def _date(value):
    try:
        if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise RefreshStoreError("refresh-state-rejected") from None


def _public_helpers():
    # API 복제본에는 상대 모듈, 수집기에는 기존 로컬 정본을 사용한다.
    try:
        from . import portfolio_public_sources as helpers
    except ImportError:
        from api.intelligence import portfolio_public_sources as helpers
    return helpers


ERROR_CODES = frozenset(("collection-failed", "collection_failure", "per-feed-completeness-unavailable",
    "dart-quota-exceeded", "invalid_timestamp", "invalid_text", "invalid_cik", "invalid_catalog",
    "invalid_sec_index", "endpoint_rejected", "invalid_transport_limits", "http_failure", "body_limit",
    "transport_timeout", "transport_failure", "invalid_atom_encoding", "xml_declaration_rejected",
    "invalid_atom", "invalid_sec_identity", "invalid_accession", "invalid_sec_link", "invalid_dart",
    "dart_api_failure", "invalid_pagination", "invalid_dart_row", "invalid_receipt", "invalid_reported_date",
    "invalid_stock_code", "invalid_limits", "invalid_cursor", "invalid_configuration", "invalid_json",
    "incomplete_page", "record_limit", "cursor_not_found", "pagination_stalled", "page_limit",
    "cursor_outside_window", "pagination_changed", "date_outside_window", "incomplete_unique_records", "invalid_page_size"))


def validate_state(source, value, *, public_sources=None):
    """공개 피드·cursor·진단의 닫힌 스키마를 검증한 뒤 독립 복사본을 반환한다."""
    _source(source)
    allowed = {"feed", "cursor", "status", "error", "coverage", "requests", "last_attempt_at",
               "last_success_at", "health", "screen_delivery_verified", "analysis_delivery_verified"}
    if type(value) is not dict or not set(value) <= allowed:
        raise RefreshStoreError("refresh-state-rejected")
    _json_bytes(value, STATE_MAX_BYTES)
    if not value:
        return {}
    required = {"status", "error", "last_attempt_at", "requests", "coverage", "health",
                "screen_delivery_verified", "analysis_delivery_verified"}
    if not required <= set(value):
        raise RefreshStoreError("refresh-state-rejected")
    attempt = _instant(value["last_attempt_at"])
    success = _instant(value["last_success_at"]) if value.get("last_success_at") is not None else None
    if success is not None and success > attempt:
        raise RefreshStoreError("refresh-state-rejected")
    for key in ("screen_delivery_verified", "analysis_delivery_verified"):
        if key in value and value[key] is not False:
            raise RefreshStoreError("refresh-state-rejected")
    status = value["status"]
    if status not in ("success", "partial", "error", "initialized") or (
            status == "initialized" and source != "SEC") or (source == "news" and status not in ("partial", "error")):
        raise RefreshStoreError("refresh-state-rejected")
    error = value["error"]
    if error is not None and (type(error) is not str or error not in ERROR_CODES):
        raise RefreshStoreError("refresh-state-rejected")
    if status in ("success", "initialized") and error is not None or status == "success" and success != attempt:
        raise RefreshStoreError("refresh-state-rejected")
    if error == "dart-quota-exceeded" and (source != "DART" or status != "error"):
        raise RefreshStoreError("refresh-state-rejected")
    requests_count = value.get("requests")
    if requests_count is not None and (type(requests_count) is not int or not 0 <= requests_count <= 10):
        raise RefreshStoreError("refresh-state-rejected")
    if requests_count is None and source != "news":
        raise RefreshStoreError("refresh-state-rejected")
    coverage = value["coverage"]
    if type(coverage) is not dict:
        raise RefreshStoreError("refresh-state-rejected")
    for key, count in coverage.items():
        if key in ("whole_market_coverage", "raw_body_checked", "all_feeds_verified"):
            valid = count is False
        elif key in ("bounded", "historical_gap"):
            valid = type(count) is bool and (key != "bounded" or count is True)
        elif key == "scope":
            valid = source == "SEC" and count == "shared_latest_8-K"
        else:
            caps = {"pages_succeeded": 10, "listing_records": 1000, "total_pages": 999999999,
                    "total_records": 999999999, "accepted": 300, "rejected": 999999999}
            valid = key in caps and type(count) is int and 0 <= count <= caps[key]
        if not valid:
            raise RefreshStoreError("refresh-state-rejected")
    age = (attempt - success).total_seconds() if success else None
    health = {"status": "unknown" if age is None else "on-time" if age <= (300 if source == "news" else 120) else "delayed",
              "age_seconds": age}
    if type(value["health"]) is not dict or set(value["health"]) != set(health) or value["health"] != health or (
            age is not None and (type(value["health"]["age_seconds"]) not in (int, float)
                                 or not math.isfinite(value["health"]["age_seconds"]))):
        raise RefreshStoreError("refresh-state-rejected")
    cursor = value.get("cursor")
    if cursor is not None:
        fields = {"source", "checked_at", "through_date", "ids"} if source == "DART" else {
            "source", "checked_at", "anchor_id", "historical_gap"}
        if source == "news" or type(cursor) is not dict or set(cursor) != fields or cursor["source"] != source:
            raise RefreshStoreError("refresh-state-rejected")
        checked = _instant(cursor["checked_at"])
        if checked > attempt or status in ("success", "initialized") and checked != attempt:
            raise RefreshStoreError("refresh-state-rejected")
        if source == "DART":
            ids = cursor["ids"]
            if _date(cursor["through_date"]) > attempt.astimezone(timezone(timedelta(hours=9))).date() or (
                    type(ids) is not list or len(ids) > 1000 or any(type(i) is not str or not re.fullmatch(r"DART:[0-9]{14}", i) for i in ids)
                    or len(set(ids)) != len(ids)):
                raise RefreshStoreError("refresh-state-rejected")
        elif type(cursor["historical_gap"]) is not bool or type(cursor["anchor_id"]) is not str or not re.fullmatch(
                r"SEC:[1-9][0-9]{0,9}:[0-9]{18}", cursor["anchor_id"]):
            raise RefreshStoreError("refresh-state-rejected")
    elif status == "success" and source != "news":
        raise RefreshStoreError("refresh-state-rejected")
    helpers = public_sources or _public_helpers()
    def text(v, maximum, *, empty=False):
        if empty and v == "":
            return
        if type(v) is not str or helpers.safe_public_text(v, maximum) != v or re.search(
                r"DART_API_KEY|SUPABASE_SERVICE_ROLE_KEY|VERCEL_BLOB_TOKEN", v, re.IGNORECASE):
            raise RefreshStoreError("refresh-state-rejected")
    feed = value.get("feed")
    if feed is None and source == "news":
        return deepcopy(value)
    if type(feed) is not dict:
        raise RefreshStoreError("refresh-state-rejected")
    if source == "news":
        try:
            from .portfolio_market_context import _url
        except ImportError:
            from api.intelligence.portfolio_market_context import _url
        if not set(feed) <= {"headlines", "bloomberg_google_headlines", "us_headlines"}:
            raise RefreshStoreError("refresh-state-rejected")
        for rows in feed.values():
            if type(rows) is not list or len(rows) > 100:
                raise RefreshStoreError("refresh-state-rejected")
            for row in rows:
                if type(row) is not dict or set(row) != {"title", "source", "link", "time"}:
                    raise RefreshStoreError("refresh-state-rejected")
                text(row["title"], 240); text(row["source"], 100)
                if type(row["link"]) is not str or len(row["link"]) > 2048 or not _url(row["link"]) or (
                        _url(row["link"]) != row["link"] or _instant(row["time"]) > attempt):
                    raise RefreshStoreError("refresh-state-rejected")
        return deepcopy(value)
    if not set(feed) <= {"items", "_meta"} or type(feed.get("items")) is not list or len(feed["items"]) > 10000:
        raise RefreshStoreError("refresh-state-rejected")
    tickers, total = set(), 0
    row_keys = {"id", "title", "label", "date", "date_precision", "source_date_field", "source_url", "source",
                "is_correction", "filer", "observed_at"}
    for group in feed["items"]:
        if type(group) is not dict or not {"ticker", "name", "disclosures"} <= set(group) <= {
                "ticker", "name", "disclosures", "latest"}:
            raise RefreshStoreError("refresh-state-rejected")
        ticker = group["ticker"]
        if type(ticker) is not str or not re.fullmatch(r"[0-9]{6}" if source == "DART" else r"[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?", ticker) or ticker in tickers:
            raise RefreshStoreError("refresh-state-rejected")
        tickers.add(ticker); text(group["name"], 160)
        if "latest" in group:
            if _date(group["latest"]) > attempt.astimezone(timezone(timedelta(hours=9))).date():
                raise RefreshStoreError("refresh-state-rejected")
        rows = group["disclosures"]
        if type(rows) is not list or len(rows) > 8:
            raise RefreshStoreError("refresh-state-rejected")
        ids = set()
        for row in rows:
            if type(row) is not dict or not row_keys <= set(row) <= row_keys | {"source_reported_at"}:
                raise RefreshStoreError("refresh-state-rejected")
            identifier = row["id"]
            if type(identifier) is not str or identifier in ids or row["source"] != source or type(row["is_correction"]) is not bool:
                raise RefreshStoreError("refresh-state-rejected")
            ids.add(identifier); text(row["title"], 300); text(row["filer"], 160, empty=True)
            stamp = _date(row["date"])
            if stamp > attempt.astimezone(timezone(timedelta(hours=9))).date() or _instant(row["observed_at"]) > attempt:
                raise RefreshStoreError("refresh-state-rejected")
            target = helpers._canonical_disclosure_url(row["source_url"], source)
            if not target or target[0] != row["source_url"]:
                raise RefreshStoreError("refresh-state-rejected")
            if source == "DART":
                valid = bool(re.fullmatch(r"DART:\d{14}", identifier)) and row["label"] == "DART" and (
                    row["date_precision"] == "date" and row["source_date_field"] == "rcept_dt"
                    and "source_reported_at" not in row and row["source_url"] ==
                    "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + identifier[5:])
            else:
                parts = identifier.split(":")
                valid = bool(re.fullmatch(r"SEC:[1-9][0-9]{0,9}:\d{18}", identifier)) and row["label"] in ("8-K", "8-K/A") and (
                    row["date_precision"] == "timestamp" and row["source_date_field"] == "atom.updated" and
                    row["source_url"].startswith("https://www.sec.gov/Archives/edgar/data/" + "/".join(parts[1:]) + "/"))
                reported = _instant(row.get("source_reported_at"))
                valid = valid and reported <= attempt and reported.date() == stamp
            if not valid:
                raise RefreshStoreError("refresh-state-rejected")
            total += 1
    if total > 50000:
        raise RefreshStoreError("refresh-state-rejected")
    if "_meta" in feed:
        meta = feed["_meta"]
        if type(meta) is not dict or set(meta) != {"generated_at", "count", "disclosure_count"} or (
                type(meta["count"]) is not int or meta["count"] != len(tickers) or
                type(meta["disclosure_count"]) is not int or meta["disclosure_count"] != total or _instant(meta["generated_at"]) > attempt):
            raise RefreshStoreError("refresh-state-rejected")
    return deepcopy(value)


class RefreshStore:
    """멤버용 인증 클라이언트와 분리된 service-role RPC 전용 어댑터."""

    def __init__(self, service_key, *, project_url=PROJECT_URL):
        if project_url != PROJECT_URL or type(service_key) is not str or not service_key.strip() or any(
                ord(c) < 33 or ord(c) == 127 for c in service_key):
            raise RefreshStoreError("refresh-config-rejected")
        self._key = service_key
        self._states = {}
        # 메타데이터 head와 달리, 이 revision은 캐시된 전체 state에만 묶인다.
        self._state_revisions = {}
        self._feed_revisions = {}
        self._uncertain_sources = set()
        self._cache_lock = threading.Lock()
        self._read_inflight = None

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
                   project_url=os.environ.get("SUPABASE_URL", "").rstrip("/"))

    def _rpc(self, name, parameters):
        if name not in RPC_NAMES:
            raise RefreshStoreError("refresh-rpc-rejected")
        result = _request_json("POST", PROJECT_URL + "/rest/v1/rpc/" + name,
            headers={"apikey": self._key, "Authorization": "Bearer " + self._key,
                     "Content-Type": "application/json", "Accept": "application/json"},
            body=_json_bytes(parameters, STATE_MAX_BYTES + ENVELOPE_MAX_BYTES),
            limit=STATE_MAX_BYTES + ENVELOPE_MAX_BYTES)
        if type(result) is not dict:
            raise RefreshStoreError("refresh-response-rejected")
        return result

    def _headers(self):
        return {"apikey": self._key, "Authorization": "Bearer " + self._key, "Accept": "application/json"}

    def read_states(self):
        """작은 head 후 변경 피드만 조회한다. 본문·검증 포함 호출자 대기는 총 3초다."""
        deadline, done, outcome = time.monotonic() + RPC_TIMEOUT_SECONDS, threading.Event(), {}
        if not self._cache_lock.acquire(timeout=max(0, deadline - time.monotonic())):
            raise RefreshStoreError("refresh-read-timeout")
        try:
            if self._read_inflight is not None and not self._read_inflight.is_set():
                raise RefreshStoreError("refresh-read-busy")
            self._read_inflight = done
            snapshot = (self._states.copy(), self._state_revisions.copy(), self._feed_revisions.copy(),
                        self._uncertain_sources.copy())
        finally:
            self._cache_lock.release()
        def fetch():
            try:
                outcome["value"] = self._read_states_changed(snapshot, deadline)
            except Exception as error:
                outcome["error_code"] = safe_error_code(error)
            finally:
                done.set()
        # requests의 DNS/소켓 지연도 호출자를 붙잡지 않게 한다. 늦은 결과는 캐시를 수정하지 않는다.
        threading.Thread(target=fetch, daemon=True).start()
        if not done.wait(max(0, deadline - time.monotonic())) or time.monotonic() >= deadline:
            raise RefreshStoreError("refresh-read-timeout")
        if "error_code" in outcome:
            # Keep a safe cause (503/auth/timeout/schema), not the original exception.
            code = outcome["error_code"]
            raise RefreshStoreError(code if code in SAFE_ERROR_CODES else "refresh-read-rejected")
        states, revisions, feeds, returned = outcome["value"]
        if not self._cache_lock.acquire(timeout=max(0, deadline - time.monotonic())):
            raise RefreshStoreError("refresh-read-timeout")
        try:
            if time.monotonic() >= deadline:
                raise RefreshStoreError("refresh-read-timeout")
            if self._state_revisions != snapshot[1] or self._feed_revisions != snapshot[2] or self._uncertain_sources != snapshot[3]:
                raise RefreshStoreError("refresh-cache-conflict")
            self._states, self._state_revisions, self._feed_revisions = states, revisions, feeds
            self._uncertain_sources.clear()
        finally:
            self._cache_lock.release()
        return returned

    def _read_states_changed(self, snapshot, deadline):
        states, revisions, feeds, uncertain = (part.copy() for part in snapshot)
        url = PROJECT_URL + "/rest/v1/" + TABLE
        heads = _request_json("GET", url + "?select=source,revision,feed_revision&source=in.(DART,SEC,news)&limit=3",
                              headers=self._headers(), limit=ENVELOPE_MAX_BYTES, deadline=deadline)
        if type(heads) is not list or len(heads) != 3:
            raise RefreshStoreError("refresh-response-rejected")
        observed = {}
        for head in heads:
            if type(head) is not dict or set(head) != {"source", "revision", "feed_revision"}:
                raise RefreshStoreError("refresh-response-rejected")
            source = _source(head["source"])
            revision, feed_revision = _integer(head["revision"]), _integer(head["feed_revision"])
            if source in observed or feed_revision > revision or revision < revisions.get(source, 0) or feed_revision < feeds.get(source, 0):
                raise RefreshStoreError("refresh-response-rejected")
            observed[source] = (revision, feed_revision)
        changed = sorted(source for source in SOURCES if source not in states or source in uncertain or observed[source][1] != feeds[source])
        if changed:
            selector = ",".join(changed)
            rows = _request_json("GET", url + "?select=source,state,revision,feed_revision&source=in.(" + selector + ")&limit=3",
                headers=self._headers(), limit=len(changed) * STATE_MAX_BYTES + ENVELOPE_MAX_BYTES, deadline=deadline)
            if type(rows) is not list or len(rows) != len(changed):
                raise RefreshStoreError("refresh-response-rejected")
            seen = set()
            for row in rows:
                if type(row) is not dict or set(row) != {"source", "state", "revision", "feed_revision"}:
                    raise RefreshStoreError("refresh-response-rejected")
                source = _source(row["source"])
                versions = (_integer(row["revision"]), _integer(row["feed_revision"]))
                if source not in changed or source in seen or versions != observed[source]:
                    raise RefreshStoreError("refresh-response-rejected")
                seen.add(source)
                states[source] = validate_state(source, row["state"])
                revisions[source], feeds[source] = versions
        # head-only에서는 revisions·성공 시각을 올리지 않는다. 기존 공개 메타데이터를 유지한다.
        returned = deepcopy(states)
        if time.monotonic() >= deadline:
            raise RefreshStoreError("refresh-read-timeout")
        return states, revisions, feeds, returned

    def claim(self, source, owner):
        source, owner = _source(source), _owner(owner)
        budget = DART_REQUEST_BUDGET if source == "DART" else 0
        with self._cache_lock:
            known_revision = self._state_revisions.get(source, -1) if source not in self._uncertain_sources else -1
            cached = self._states.get(source)
            cached_feed_revision = self._feed_revisions.get(source)
        result = self._rpc("member_map_refresh_claim", {"p_source": source, "p_owner": owner,
            "p_request_budget": budget, "p_known_revision": known_revision})
        if result.get("status") == "not-due" and set(result) == {"status", "retry_after_seconds"} and (
                type(result["retry_after_seconds"]) is int and 0 <= result["retry_after_seconds"] <= 300):
            return result
        if result.get("status") in ("busy", "quota-blocked", "budget-exhausted") and set(result) == {"status"}:
            return result
        required = {"status", "source", "generation", "revision", "feed_revision", "state", "lease_until",
                    "request_day", "requests_reserved", "request_budget"}
        if set(result) != required or result["status"] not in ("claimed", "already-claimed") or result["source"] != source:
            raise RefreshStoreError("refresh-response-rejected")
        _integer(result["generation"], positive=True); _integer(result["revision"])
        feed_revision = _integer(result["feed_revision"])
        if feed_revision > result["revision"]:
            raise RefreshStoreError("refresh-response-rejected")
        _instant(result["lease_until"])
        if type(result["request_budget"]) is not int or result["request_budget"] != budget or (
                type(result["requests_reserved"]) is not int or not budget <= result["requests_reserved"] <= DART_DAILY_CAP):
            raise RefreshStoreError("refresh-response-rejected")
        if source == "DART":
            _date(result["request_day"])
        elif result["request_day"] is not None or result["requests_reserved"] != 0:
            raise RefreshStoreError("refresh-response-rejected")
        if result["state"] is None:
            if known_revision < 0 or result["revision"] != known_revision or cached is None or feed_revision != cached_feed_revision:
                raise RefreshStoreError("refresh-response-rejected")
            result["state"] = deepcopy(cached)
        else:
            result["state"] = validate_state(source, result["state"])
        with self._cache_lock:
            if result["revision"] < self._state_revisions.get(source, 0) or feed_revision < self._feed_revisions.get(source, 0):
                raise RefreshStoreError("refresh-cache-conflict")
            self._states[source] = deepcopy(result["state"])
            self._state_revisions[source] = result["revision"]
            self._feed_revisions[source] = feed_revision
            self._uncertain_sources.discard(source)
        return result

    def renew(self, source, owner, generation):
        source, owner, generation = _source(source), _owner(owner), _integer(generation, positive=True)
        result = self._rpc("member_map_refresh_renew", {"p_source": source, "p_owner": owner, "p_generation": generation})
        if result == {"status": "lease-lost"}:
            raise RefreshStoreError("refresh-lease-lost")
        if set(result) != {"status", "source", "generation", "revision", "lease_until"} or (
                result["status"] != "renewed" or result["source"] != source or result["generation"] != generation):
            raise RefreshStoreError("refresh-response-rejected")
        _integer(result["revision"]); _integer(result["generation"], positive=True); _instant(result["lease_until"])
        return result

    def save(self, source, owner, generation, expected_revision, state):
        source, owner = _source(source), _owner(owner)
        generation, expected_revision = _integer(generation, positive=True), _integer(expected_revision)
        state = validate_state(source, state)
        if not state:
            raise RefreshStoreError("refresh-state-rejected")
        try:
            result = self._rpc("member_map_refresh_save", {"p_source": source, "p_owner": owner,
                "p_generation": generation, "p_expected_revision": expected_revision, "p_state": state})
            if result in ({"status": "lease-lost"}, {"status": "revision-conflict"}):
                raise RefreshStoreError("refresh-save-conflict")
            if set(result) != {"status", "source", "generation", "revision", "feed_revision", "updated_at"} or (
                    result["status"] != "saved" or result["source"] != source or result["generation"] != generation or
                    result["revision"] != expected_revision + 1):
                raise RefreshStoreError("refresh-response-rejected")
            _integer(result["revision"]); _integer(result["generation"], positive=True); _instant(result["updated_at"])
            feed_revision = _integer(result["feed_revision"])
            if feed_revision > result["revision"]:
                raise RefreshStoreError("refresh-response-rejected")
            with self._cache_lock:
                prior_revision = self._state_revisions.get(source, -1)
                prior_feed = self._feed_revisions.get(source, 0)
                if prior_revision > expected_revision or feed_revision < prior_feed or (
                        prior_revision == expected_revision and feed_revision != prior_feed + int(self._states[source].get("feed") != state.get("feed"))):
                    raise RefreshStoreError("refresh-cache-conflict")
                self._states[source] = state
                self._state_revisions[source] = result["revision"]
                self._feed_revisions[source] = feed_revision
                self._uncertain_sources.discard(source)
        except RefreshStoreError:
            # 저장 응답이 불명확하면 제출본을 확정하지 않는다. 다음 읽기는 본문까지 재확인한다.
            with self._cache_lock:
                self._uncertain_sources.add(source)
            raise
        return result

"""Closed public-evidence projection for an identifier-only portfolio window.

Input is the already-built automatic member-map artifact.  This module performs
no file, network, account, model, or collector access.  Automatic evidence is
kept separate from the manual reviewed registry: accepted relationships remain
candidates unless a bound structured source row supports a dated reported
ownership record. Co-mentions remain materials; no verified event is synthesized.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date as calendar_date
from decimal import Decimal
import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Literal, Mapping, Sequence, TypedDict


SUPPORTED_SOURCE_FILES = ("member_map_auto_evidence.json",)
MAX_PORTFOLIO_SYMBOLS = 30

_KR_TICKER = re.compile(r"[0-9]{6}\Z", re.ASCII)
_US_TICKER = re.compile(r"[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?\Z", re.ASCII)
_RECEIPT = re.compile(r"[0-9]{14}\Z", re.ASCII)
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
_DART_SOURCE_ID = re.compile(r"source:dart:([0-9]{14})\Z", re.ASCII)
_GROUP_SOURCE_ID = re.compile(r"source:group-structure:[0-9]{4}-[0-9]{2}-[0-9]{2}:.+\Z")
_EVENT_ID = re.compile(r"event:dart:[0-9]{14}:[0-9]+-[0-9]+:[0-9a-f]{8}\Z", re.ASCII)
_RELATION_ID = re.compile(r"relation:group-structure:[0-9a-f]{8}\Z", re.ASCII)
_CORRECTION_ID = re.compile(r"correction:[0-9]{14}\Z", re.ASCII)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ARTIFACT_MARKETS = {"KR", "US", "KONEX", "ETF", "ETN", "채권", "지수", "원자재"}

_TOP_LEVEL_FIELDS = {
    "schemaVersion", "generatedAt", "scope", "artifactTimestamps",
    "sourceDateCoverage", "inputs", "identityCatalog", "denominators",
    "rejectionReasons", "tickerIndex", "sources", "events", "relations",
    "corrections",
}
_DENOMINATOR_FIELDS = {
    "issuersInput", "issuersIndexed", "documentsInput", "documentsAccepted",
    "excerptsInput", "excerptsAccepted", "excerptsRejected", "relationsInput",
    "relationsAccepted", "relationsRejected",
}
_RELATION_TYPES = {"reported-equity-investment", "reported-major-shareholder-entry"}
_LOCAL_SCOPE = "local-existing-data-builder-and-pure-runtime-filter"
_PUBLIC_SCOPE = "published-automatic-evidence-catalog"
_PUBLIC_SCOPE_NOTE = ("Generated from declared received source snapshots; source timestamps "
                      "are reported separately and are not automatically reverified.")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class PortfolioEvidenceError(ValueError):
    """Non-reflecting automatic-evidence contract rejection."""


class Position(TypedDict):
    ticker: str
    market: Literal["KR", "US"]


class ProjectedRelationship(TypedDict, total=False):
    stable_id: str
    revision: str
    status: Literal["accepted_candidate", "accepted_reported"]
    label: str
    type: str
    verification: str
    participants: list[dict[str, str]]
    source: dict[str, Any]
    evidence: dict[str, Any]


class PortfolioEvidenceProjection(TypedDict):
    schema: Literal["portfolio-auto-evidence-v1"]
    status: Literal["available", "empty"]
    companies: list[dict[str, Any]]
    connected_companies: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    materials: list[dict[str, Any]]
    common_materials: list[dict[str, Any]]
    verified_events: list[dict[str, Any]]
    corrections: list[dict[str, Any]]
    coverage: dict[str, Any]
    _meta: dict[str, Any]
    revision: str


def _plain_mapping(value: Any) -> bool:
    return type(value) is dict


def _safe_text(value: Any, *, maximum: int, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if type(value) is not str or not value or len(value) > maximum or _CONTROL.search(value):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    return value


def _entity_id(value: Any) -> str:
    value = _safe_text(value, maximum=64)
    if value.count(":") != 1:
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    market, ticker = value.split(":", 1)
    if market not in _ARTIFACT_MARKETS or not ticker or len(ticker) > 40 or _CONTROL.search(ticker):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    return value


def _nonnegative_int(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    return value


def _number(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    return float(value)


def _unique_string_list(value: Any) -> list[str]:
    if type(value) is not list:
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    result = [_safe_text(item, maximum=256) for item in value]
    if len(set(result)) != len(result):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    return result


def _revision(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def _validate_source_row(value: Any, major_holder: bool) -> None:
    fields = {"rcept_no", "corp_code", "corp_name", "stlm_dt"}
    fields |= ({"nm", "relate", "stock_knd", "trmend_posesn_stock_qota_rt"} if major_holder
               else {"inv_prm", "trmend_blce_qota_rt"})
    if (not _plain_mapping(value) or set(value) != {"index", "fields"}
            or type(value["index"]) is not int or value["index"] < 0
            or not _plain_mapping(value["fields"]) or set(value["fields"]) != fields):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    for item in value["fields"].values():
        if item is not None and (type(item) is not str or len(item) > 300 or _CONTROL.search(item)):
            raise PortfolioEvidenceError("automatic evidence contract rejected")


def _legal_name(value: str | None) -> str:
    name = unicodedata.normalize("NFKC", value or "").casefold()
    name = re.sub(r"\s+", "", name)
    # Exact legal-name matching only. No substring, group-name or fuzzy joins.
    return re.sub(r"^(?:주식회사|\(주\))|(?:주식회사|\(주\))$", "", name)


def _identity_names(ticker_index: Mapping[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, row in ticker_index.items():
        if key.startswith(("KR:", "KONEX:")):
            result.setdefault(_legal_name(row["issuer"]["name"]), []).append(key)
    return result


def _reported_decision(relation: Mapping[str, Any], source: Mapping[str, Any],
                       names: Mapping[str, list[str]]) -> str:
    if source["kind"] != "dart-structured-relation" or "sourceRow" not in relation:
        return "missing-source-row"
    fields = relation["sourceRow"]["fields"]
    if fields["rcept_no"] != source["receiptNo"] or fields["corp_code"] != source["corpCode"]:
        return "source-row-provenance-mismatch"
    if not source["settlementDate"] or fields["stlm_dt"] != source["settlementDate"]:
        return "missing-or-mismatched-settlement-date"
    major = relation["type"] == "reported-major-shareholder-entry"
    issuer, other = relation["to" if major else "from"], relation["from" if major else "to"]
    if issuer == other:
        return "self-relation"
    for name, expected in ((fields["corp_name"], issuer), (fields["nm" if major else "inv_prm"], other)):
        matches = names.get(_legal_name(name), [])
        if len(matches) > 1:
            return "ambiguous-legal-name"
        if matches != [expected]:
            return "source-row-identity-mismatch"
    if major and (not fields["relate"] or not fields["stock_knd"]
                  or not fields["stock_knd"].strip() or fields["relate"] != relation["role"]):
        return "missing-or-mismatched-holder-role-or-stock-kind"
    raw = (fields["trmend_posesn_stock_qota_rt" if major else "trmend_blce_qota_rt"] or "").strip()
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?", raw):
        return "missing-numeric-ownership"
    percentage = Decimal(raw.replace(",", ""))
    if not 0 < percentage <= 100:
        return "nonpositive-or-out-of-range-ownership"
    projected = relation.get("reportedOwnershipPct", -1)
    if not 0 < projected <= 100 or abs(percentage - Decimal(str(projected))) > Decimal("0.005000001"):
        return "ownership-projection-mismatch"
    return "bound-source-row"


def _validate_positions(positions: Any) -> list[dict[str, str]]:
    if type(positions) is not list or not 1 <= len(positions) <= MAX_PORTFOLIO_SYMBOLS:
        raise PortfolioEvidenceError("portfolio identifiers rejected")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in positions:
        if type(row) is not dict or set(row) != {"ticker", "market"}:
            raise PortfolioEvidenceError("portfolio identifiers rejected")
        ticker, market = row["ticker"], row["market"]
        if type(ticker) is not str or type(market) is not str:
            raise PortfolioEvidenceError("portfolio identifiers rejected")
        pattern = _KR_TICKER if market == "KR" else _US_TICKER if market == "US" else None
        if pattern is None or not pattern.fullmatch(ticker):
            raise PortfolioEvidenceError("portfolio identifiers rejected")
        identifier = f"{market}:{ticker}"
        if identifier not in seen:
            seen.add(identifier)
            result.append({"id": identifier, "ticker": ticker, "market": market})
    return result


def _validate_source(source_id: str, source: Any) -> None:
    if not _plain_mapping(source) or source.get("id") != source_id:
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    kind = source.get("kind")
    if kind == "dart-filing-excerpt":
        required = {"id", "kind", "receiptNo", "sourceDate", "reportName",
                    "documentIssuer", "url"}
        if set(source) != required:
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        receipt = _safe_text(source["receiptNo"], maximum=14)
        match = _DART_SOURCE_ID.fullmatch(source_id)
        if not match or not _RECEIPT.fullmatch(receipt) or match.group(1) != receipt:
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        date = _safe_text(source["sourceDate"], maximum=10)
        if not _DATE.fullmatch(date):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        _safe_text(source["reportName"], maximum=300)
        _entity_id(source["documentIssuer"])
        if source["url"] != "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt:
            raise PortfolioEvidenceError("automatic evidence contract rejected")
    elif kind == "local-structured-relation-candidate":
        required = {"id", "kind", "sourceDate", "artifactObservedAt",
                    "documentIssuer", "receiptNo", "note"}
        if set(source) != required or not _GROUP_SOURCE_ID.fullmatch(source_id):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        if source["sourceDate"] is not None or source["receiptNo"] is not None:
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        _safe_text(source["artifactObservedAt"], maximum=64)
        _entity_id(source["documentIssuer"])
        _safe_text(source["note"], maximum=300)
    elif kind == "dart-structured-relation":
        required = {"id", "kind", "receiptNo", "sourceDate", "settlementDate",
                    "businessYear", "reportCode", "corpCode", "endpoint",
                    "documentIssuer", "artifactObservedAt", "url"}
        if set(source) != required or source["sourceDate"] is not None:
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        receipt = _safe_text(source["receiptNo"], maximum=14)
        year = _safe_text(source["businessYear"], maximum=4)
        corp = _safe_text(source["corpCode"], maximum=8)
        issuer = _entity_id(source["documentIssuer"])
        endpoint = source["endpoint"]
        settlement = source["settlementDate"]
        if (not _RECEIPT.fullmatch(receipt) or not re.fullmatch(r"[0-9]{4}", year)
                or not re.fullmatch(r"[0-9]{8}", corp)
                or not re.fullmatch(r"(?:KR|KONEX):[0-9]{6}", issuer)
                or source["reportCode"] != "11011"
                or endpoint not in ("hyslrSttus", "otrCprInvstmntSttus")):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        if settlement is not None:
            if type(settlement) is not str or not _DATE.fullmatch(settlement):
                raise PortfolioEvidenceError("automatic evidence contract rejected")
            try:
                calendar_date.fromisoformat(settlement)
            except ValueError:
                raise PortfolioEvidenceError("automatic evidence contract rejected") from None
        expected_id = (f"source:dart-structured:{receipt}:{endpoint}:{issuer}:{corp}:"
                       f"{year}:11011:{settlement or 'unknown'}")
        if (source_id != expected_id or source["url"] !=
                "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        _safe_text(source["artifactObservedAt"], maximum=64)
    else:
        raise PortfolioEvidenceError("automatic evidence contract rejected")


def _validate_artifact(artifact: Any) -> None:
    if not _plain_mapping(artifact) or set(artifact) - {"documentFamilies", "contract_facts", "contract_terminations", "filing_excerpts"} != _TOP_LEVEL_FIELDS:
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    # Optional lineage is gated independently, never promoted to a relationship.
    if "documentFamilies" in artifact and (type(artifact["documentFamilies"]) is not list
                                           or len(artifact["documentFamilies"]) > 1000):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    # Contract facts are validated and bound independently by the document
    # projection. They never enter relationship or event candidate output.
    if "contract_facts" in artifact and (type(artifact["contract_facts"]) is not list
                                         or len(artifact["contract_facts"]) > 1000):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    if "contract_terminations" in artifact and (type(artifact["contract_terminations"]) is not list
                                                or len(artifact["contract_terminations"]) > 1000):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    if "filing_excerpts" in artifact and (type(artifact["filing_excerpts"]) is not list
                                          or len(artifact["filing_excerpts"]) > 1000):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    if artifact.get("schemaVersion") != 1:
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    scope = artifact.get("scope")
    if (not _plain_mapping(scope) or set(scope) != {"mode", "runtimeFreshness", "note"}
            or scope.get("mode") not in {_LOCAL_SCOPE, _PUBLIC_SCOPE}
            or scope.get("runtimeFreshness") != "not-automatically-reverified"):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    for field in ("artifactTimestamps", "sourceDateCoverage", "inputs", "identityCatalog"):
        if not _plain_mapping(artifact.get(field)):
            raise PortfolioEvidenceError("automatic evidence contract rejected")

    denominators = artifact.get("denominators")
    if not _plain_mapping(denominators) or set(denominators) != _DENOMINATOR_FIELDS:
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    for value in denominators.values():
        _nonnegative_int(value)
    if (denominators["issuersInput"] != denominators["issuersIndexed"]
            or denominators["excerptsAccepted"] + denominators["excerptsRejected"] != denominators["excerptsInput"]
            or denominators["relationsAccepted"] + denominators["relationsRejected"] != denominators["relationsInput"]):
        raise PortfolioEvidenceError("automatic evidence contract rejected")

    if scope["mode"] == _PUBLIC_SCOPE:
        inputs = artifact["inputs"]
        if set(inputs) != {"universe", "chainSnippets", "groupStructure"}:
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        for metadata in inputs.values():
            if (not _plain_mapping(metadata) or set(metadata) != {"bytes", "sha256"}
                    or type(metadata["bytes"]) is not int or metadata["bytes"] < 0
                    or type(metadata["sha256"]) is not str
                    or not _SHA256.fullmatch(metadata["sha256"])):
                raise PortfolioEvidenceError("automatic evidence contract rejected")
        identity = artifact["identityCatalog"]
        if (set(identity) != {"identities", "textMatchMarkets"}
                or identity.get("identities") != denominators["issuersIndexed"]
                or identity.get("textMatchMarkets") != ["KR", "KONEX", "US"]
                or scope.get("note") != _PUBLIC_SCOPE_NOTE):
            raise PortfolioEvidenceError("automatic evidence contract rejected")

    rejections = artifact.get("rejectionReasons")
    if not _plain_mapping(rejections) or any(type(key) is not str for key in rejections):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    for value in rejections.values():
        _nonnegative_int(value)
    if sum(rejections.values()) != denominators["excerptsRejected"] + denominators["relationsRejected"]:
        raise PortfolioEvidenceError("automatic evidence contract rejected")

    sources, events, relations = (artifact.get(name) for name in ("sources", "events", "relations"))
    ticker_index = artifact.get("tickerIndex")
    if not all(_plain_mapping(value) for value in (sources, events, relations, ticker_index)):
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    if len(ticker_index) != denominators["issuersIndexed"] or len(events) != denominators["excerptsAccepted"] or len(relations) != denominators["relationsAccepted"]:
        raise PortfolioEvidenceError("automatic evidence contract rejected")

    for source_id, source in sources.items():
        _safe_text(source_id, maximum=256)
        _validate_source(source_id, source)

    for event_id, event in events.items():
        required = {"id", "type", "explicitRole", "sourceId", "sourceDate",
                    "documentIssuer", "mentionedCompanies", "evidence"}
        if not _plain_mapping(event) or not required.issubset(event) or set(event) - (required | {"ignoredAmbiguousAliases"}):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        if (event.get("id") != event_id or not _EVENT_ID.fullmatch(event_id)
                or event.get("type") != "co-mention" or event.get("explicitRole") is not False):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        if event.get("sourceId") not in sources or sources[event["sourceId"]].get("kind") != "dart-filing-excerpt":
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        date = _safe_text(event.get("sourceDate"), maximum=10)
        if not _DATE.fullmatch(date):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        issuer = _entity_id(event.get("documentIssuer"))
        mentioned = _unique_string_list(event.get("mentionedCompanies"))
        if issuer in mentioned or any(_entity_id(item) not in ticker_index for item in mentioned) or issuer not in ticker_index:
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        evidence = event.get("evidence")
        if (not _plain_mapping(evidence) or set(evidence) != {"anchor", "charStart", "charEnd", "excerpt"}
                or type(evidence["charStart"]) is not int or type(evidence["charEnd"]) is not int
                or evidence["charStart"] < 0 or evidence["charEnd"] < evidence["charStart"]):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        _safe_text(evidence["anchor"], maximum=100)
        _safe_text(evidence["excerpt"], maximum=2000)

    for relation_id, relation in relations.items():
        required = {"id", "type", "explicitRole", "verification", "from", "to",
                    "sourceId", "sourceDate", "artifactObservedAt", "role"}
        if (not _plain_mapping(relation) or not required.issubset(relation)
                or set(relation) - (required | {"reportedOwnershipPct", "sourceRow"})):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        if (relation.get("id") != relation_id or not _RELATION_ID.fullmatch(relation_id)
                or relation.get("type") not in _RELATION_TYPES or relation.get("explicitRole") is not True
                or relation.get("sourceDate") is not None):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        if relation.get("sourceId") not in sources:
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        source = sources[relation["sourceId"]]
        if source["kind"] == "dart-structured-relation":
            major_holder = relation["type"] == "reported-major-shareholder-entry"
            if (relation["verification"] != "candidate-source-row-receipt"
                    or source["endpoint"] != ("hyslrSttus" if major_holder else "otrCprInvstmntSttus")
                    or source["documentIssuer"] != relation["to" if major_holder else "from"]
                    or source["artifactObservedAt"] != relation["artifactObservedAt"]):
                raise PortfolioEvidenceError("automatic evidence contract rejected")
        elif (source["kind"] != "local-structured-relation-candidate"
              or relation["verification"] != "candidate-unverified-no-document-receipt"):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        for key in ("from", "to"):
            if _entity_id(relation.get(key)) not in ticker_index:
                raise PortfolioEvidenceError("automatic evidence contract rejected")
        _safe_text(relation.get("artifactObservedAt"), maximum=64)
        _safe_text(relation.get("role"), maximum=200)
        if "reportedOwnershipPct" in relation:
            _number(relation["reportedOwnershipPct"])
        if "sourceRow" in relation:
            _validate_source_row(relation["sourceRow"], relation["type"] == "reported-major-shareholder-entry")

    corrections = artifact.get("corrections")
    if type(corrections) is not list:
        raise PortfolioEvidenceError("automatic evidence contract rejected")
    correction_ids: set[str] = set()
    for correction in corrections:
        required = {"stableId", "sourceId", "issuer", "disposition", "reason", "lineage"}
        if not _plain_mapping(correction) or set(correction) != required:
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        stable_id = correction.get("stableId")
        if (type(stable_id) is not str or not _CORRECTION_ID.fullmatch(stable_id)
                or stable_id in correction_ids or correction.get("sourceId") not in sources
                or correction.get("disposition") != "kept-distinct"
                or correction.get("reason") != "explicit-correction-title-distinct-receipt"
                or correction.get("lineage") != "not-provided-by-source"
                or _entity_id(correction.get("issuer")) not in ticker_index):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        correction_ids.add(stable_id)

    for identifier, row in ticker_index.items():
        if (_entity_id(identifier) != identifier or not _plain_mapping(row)
                or set(row) != {"issuer", "sourceCandidates", "eventCandidates", "relationCandidates"}):
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        issuer = row.get("issuer")
        if not _plain_mapping(issuer) or set(issuer) != {"ticker", "market", "name"}:
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        expected = f"{issuer.get('market')}:{issuer.get('ticker')}"
        if expected != identifier:
            raise PortfolioEvidenceError("automatic evidence contract rejected")
        _safe_text(issuer.get("name"), maximum=300)
        source_ids = _unique_string_list(row.get("sourceCandidates"))
        event_ids = _unique_string_list(row.get("eventCandidates"))
        relation_ids = _unique_string_list(row.get("relationCandidates"))
        if (any(item not in sources for item in source_ids)
                or any(item not in events for item in event_ids)
                or any(item not in relations for item in relation_ids)):
            raise PortfolioEvidenceError("automatic evidence contract rejected")


def _canonical_entity(identifier: str) -> str:
    return "KR:" + identifier.split(":", 1)[1] if identifier.startswith("KONEX:") else identifier


def _project_source(source: Mapping[str, Any]) -> dict[str, Any]:
    row = {
        "id": source["id"], "kind": source["kind"],
        "url": source.get("url"), "receipt_no": source.get("receiptNo"),
        "as_of": source.get("sourceDate"),
        "artifact_observed_at": source.get("artifactObservedAt"),
        "document_issuer": _canonical_entity(source["documentIssuer"]),
    }
    if source["kind"] == "dart-filing-excerpt":
        row["report_name"] = source["reportName"]
    elif source["kind"] == "dart-structured-relation":
        row.update(settlement_date=source["settlementDate"], business_year=source["businessYear"],
                   report_code=source["reportCode"], endpoint=source["endpoint"], corp_code=source["corpCode"])
    row["revision"] = _revision(row)
    return row


def project_portfolio_evidence(
    artifact: Mapping[str, Any], positions: Sequence[Position]
) -> PortfolioEvidenceProjection:
    """Project automatic public evidence for a private identifier-only window.

    The result is safe only as a private response.  It is not a reviewed manual
    registry and does not establish a verified event or economic relationship.
    """
    requested = _validate_positions(positions)
    _validate_artifact(artifact)
    ticker_index = artifact["tickerIndex"]
    identity_names = _identity_names(ticker_index)

    selected: dict[str, str] = {}
    companies: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    for request in requested:
        artifact_id = request["id"]
        if artifact_id not in ticker_index and request["market"] == "KR":
            konex = "KONEX:" + request["ticker"]
            artifact_id = konex if konex in ticker_index else artifact_id
        if artifact_id not in ticker_index:
            missing.append({**request, "reason": "not-in-automatic-identity-catalog"})
            continue
        selected[artifact_id] = request["id"]
        identity = ticker_index[artifact_id]["issuer"]
        companies.append({**request, "name": identity["name"]})

    selected_ids = set(selected)
    used_source_ids: set[str] = set()
    relationships: list[dict[str, Any]] = []
    for relation in artifact["relations"].values():
        if relation["from"] not in selected_ids and relation["to"] not in selected_ids:
            continue
        used_source_ids.add(relation["sourceId"])
        projected_source = _project_source(artifact["sources"][relation["sourceId"]])
        projected = {
            "stable_id": relation["id"], "status": "accepted_candidate",
            "label": "관계 후보·원문 확인 필요",
            "type": relation["type"], "verification": relation["verification"],
            "participants": [
                {"id": _canonical_entity(relation["from"]), "role": "from"},
                {"id": _canonical_entity(relation["to"]), "role": "to"},
            ],
            "source": projected_source,
            "evidence": {"role": relation["role"]},
        }
        if "reportedOwnershipPct" in relation:
            projected["evidence"]["reported_ownership_pct"] = relation["reportedOwnershipPct"]
        decision = _reported_decision(relation, artifact["sources"][relation["sourceId"]], identity_names)
        projected["decision_reason"] = decision
        # A mapping change (including a new ambiguous name) invalidates the read revision.
        projected["identity_revision"] = _revision([
            {"id": key, "name": ticker_index[key]["issuer"]["name"],
             "matches": identity_names.get(_legal_name(ticker_index[key]["issuer"]["name"]), [])}
            for key in (relation["from"], relation["to"])
        ])
        if decision == "bound-source-row":
            projected.update(status="accepted_reported", label="공시상 지분 관계 · 결산기준",
                             verification="reported-source-row",
                             snapshot_scope="reported-at-settlement-not-current")
            projected["evidence"]["source_row"] = deepcopy(relation["sourceRow"])
        fingerprint = deepcopy(projected)
        fingerprint["source"].pop("artifact_observed_at", None)
        fingerprint["source"].pop("revision", None)
        if "source_row" in fingerprint["evidence"]:
            fingerprint["evidence"]["source_row"].pop("index", None)
        projected["revision"] = _revision(fingerprint)
        relationships.append(projected)

    materials: list[dict[str, Any]] = []
    common_materials: list[dict[str, Any]] = []
    for event in artifact["events"].values():
        participants = [event["documentIssuer"], *event["mentionedCompanies"]]
        portfolio_participants = [selected[item] for item in participants if item in selected]
        if not portfolio_participants:
            continue
        used_source_ids.add(event["sourceId"])
        projected_source = _project_source(artifact["sources"][event["sourceId"]])
        material = {
            "stable_id": event["id"], "kind": "co_mention_candidate", "verified_event": False,
            "participants": [
                {"id": _canonical_entity(event["documentIssuer"]), "role": "document_issuer"},
                *[{"id": _canonical_entity(item), "role": "mentioned_company"}
                  for item in event["mentionedCompanies"]],
            ],
            "portfolio_company_ids": sorted(set(portfolio_participants)),
            "source": projected_source,
            "evidence": {"anchor": event["evidence"]["anchor"],
                         "char_start": event["evidence"]["charStart"],
                         "char_end": event["evidence"]["charEnd"],
                         "excerpt": event["evidence"]["excerpt"]},
        }
        material["revision"] = _revision(material)
        materials.append(material)
        if len(material["portfolio_company_ids"]) >= 2:
            common = {
                "stable_id": "common-material:" + event["id"],
                "material_id": event["id"],
                "portfolio_company_ids": material["portfolio_company_ids"][:],
                "kind": "shared-source-material",
                "verified_event": False,
            }
            common["revision"] = _revision(common)
            common_materials.append(common)

    selected_candidate_sources: set[str] = set()
    for artifact_id in selected_ids:
        selected_candidate_sources.update(ticker_index[artifact_id]["sourceCandidates"])
    corrections: list[dict[str, Any]] = []
    for correction in artifact["corrections"]:
        if correction["sourceId"] not in selected_candidate_sources:
            continue
        used_source_ids.add(correction["sourceId"])
        projected = {
            "stable_id": correction["stableId"],
            "source": _project_source(artifact["sources"][correction["sourceId"]]),
            "issuer": _canonical_entity(correction["issuer"]),
            "disposition": correction["disposition"], "reason": correction["reason"],
            "lineage": correction["lineage"],
        }
        projected["revision"] = _revision(projected)
        corrections.append(projected)

    relationships.sort(key=lambda row: row["stable_id"])
    materials.sort(key=lambda row: row["stable_id"])
    common_materials.sort(key=lambda row: row["material_id"])
    corrections.sort(key=lambda row: row["stable_id"])
    projected_sources = [_project_source(artifact["sources"][source_id])
                         for source_id in sorted(used_source_ids)]

    result: dict[str, Any] = {
        "schema": "portfolio-auto-evidence-v1",
        "status": "available" if companies else "empty",
        "companies": companies,
        # Outside participants remain in evidence details; they are not graph-node instructions.
        "connected_companies": [],
        "sources": projected_sources,
        "relationships": relationships,
        "materials": materials,
        "common_materials": common_materials,
        "verified_events": [],
        "corrections": corrections,
        "coverage": {
            "requested": len(requested), "matched": len(companies), "missing": missing,
            "accepted_relationship_candidates": sum(row["status"] == "accepted_candidate" for row in relationships),
            "accepted_reported_relationships": sum(row["status"] == "accepted_reported" for row in relationships),
            "co_mention_candidates": len(materials), "common_materials": len(common_materials),
            "verified_events": 0,
            "artifact_candidate_coverage": {
                "issuers": artifact["denominators"]["issuersIndexed"],
                "relationships": artifact["denominators"]["relationsAccepted"],
                "co_mentions": artifact["denominators"]["excerptsAccepted"],
                "corrections": len(artifact["corrections"]),
            },
            "filter_denominators": deepcopy(artifact["denominators"]),
            "filter_rejections": deepcopy(artifact["rejectionReasons"]),
        },
        "_meta": {
            "source_file": SUPPORTED_SOURCE_FILES[0],
            "automatic_evidence": True,
            "manual_review_provenance": False,
            "delivery": "private-response-only",
            "shared_cache": False,
            "external_model_calls": 0,
            "runtime_freshness": artifact["scope"]["runtimeFreshness"],
            "generated_at": artifact["generatedAt"],
        },
    }
    result["revision"] = _revision(result)
    return result  # type: ignore[return-value]


__all__ = (
    "MAX_PORTFOLIO_SYMBOLS", "PortfolioEvidenceError", "PortfolioEvidenceProjection",
    "SUPPORTED_SOURCE_FILES", "project_portfolio_evidence",
)

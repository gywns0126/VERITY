"""AlphaConsole portfolio facts engine: public sources in, private result out.

Do not route operator_ask.ask/ticker_facts.collect results into this module.
Input accepts identifiers only, not account IDs, quantities, costs or notes.
The selected identifiers themselves are personal: never publish/cache the result
in a shared artifact or send it to an external model. No IO occurs here.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json
import re
import threading
import unicodedata

from .portfolio_evidence import project_portfolio_evidence
from .portfolio_public_sources import (
    PUBLIC_SOURCE_FILES,
    project_public_sources,
    project_public_business_overviews,
    safe_public_text,
)
from .portfolio_prices import project_portfolio_prices
from .portfolio_market_context import project_market_context, index_filing_market_context, index_public_news_names
from .portfolio_source_matches import attach_source_matches
from .portfolio_event_lineage import attach_event_lineage
from .portfolio_contract_facts import attach_contract_facts, index_contract_events, select_contract_events
from .portfolio_company_names import add_public_company_names, public_news_name_catalog
from .portfolio_contract_termination import attach_contract_terminations
from .portfolio_capture_archive import retain_captured_documents
from .portfolio_filing_excerpts import index_filing_excerpts, attach_parent_relationships
from .portfolio_business_roles import index_business_roles, attach_business_relationships
from .portfolio_annual_customer_tables import (
    attach_annual_customer_table_relationships,
    index_annual_customer_table_captures,
)


MAX_SYMBOLS = 30  # Analysis window, not a limit on a member's stored holdings.
MAX_RESPONSE_DOCUMENTS = 60
MAX_AUTOMATIC_EVIDENCE_CANDIDATES = 40
MAX_AUTOMATIC_EVIDENCE_RELATIONSHIPS = 20
MAX_AUTOMATIC_EVIDENCE_SOURCES = 40
MAX_AUTOMATIC_EVIDENCE_CORRECTIONS = 20
_TICKER = {"KR": re.compile(r"[0-9]{6}\Z"),
           "US": re.compile(r"[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?\Z")}
_PUBLIC_BUNDLE_REVISION = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_AUTOMATIC_EVIDENCE_FILE = "member_map_auto_evidence.json"
_AUTOMATIC_EVIDENCE_SCOPE = "published-automatic-evidence-catalog"


class _ProjectedPublicIndexCache:
    """One public bundle only; never stores a caller selection or result."""

    def __init__(self):
        self._lock = threading.Lock()
        self._revision = None
        self._index = None

    @staticmethod
    def _build(public_documents):
        projected = project_public_sources(public_documents)
        catalog, archive = retain_captured_documents(public_documents.get(_AUTOMATIC_EVIDENCE_FILE),
            add_public_company_names(public_documents, projected["companies"]))
        by_id = {row["id"]: row for row in catalog}
        auto_evidence = public_documents.get(_AUTOMATIC_EVIDENCE_FILE)
        annual_captures = auto_evidence.get("annual_customer_tables", []) if type(auto_evidence) is dict else []
        try:
            annual_customer_tables = index_annual_customer_table_captures(
                annual_captures, company_catalog=list(by_id.values())
            )
        except (TypeError, ValueError, UnicodeError):
            # The strict evidence projector independently rejects malformed
            # public artifacts; do not fail unrelated portfolio source joins.
            annual_customer_tables = {
                "relations": [], "by_company": [], "sources": [], "holds": [],
                "coverage": {"input": 0, "captures_accepted": 0, "captures_rejected": 1,
                             "customer_cells_examined": 0, "candidate_names": 0,
                             "relationships": 0, "identity_holds": 0,
                             "rejection_reasons": {"capture-rejected": 1}},
            }
        return {
            "by_id": by_id,
            "coverage": projected["coverage"],
            "capture_archive": archive,
            # Localized search/report names are mention hints only. Never add
            # them to the legal-name catalog used for contract-party matching.
            "news_names": index_public_news_names(public_news_name_catalog(public_documents, list(by_id.values()))),
            "business_materials": _business_material_index(public_documents, by_id),
            "contract_events": index_contract_events(public_documents.get(_AUTOMATIC_EVIDENCE_FILE), list(by_id.values())),
            "filing_excerpts": index_filing_excerpts(public_documents.get(_AUTOMATIC_EVIDENCE_FILE), list(by_id.values())),
            "annual_customer_tables": annual_customer_tables,
        }

    def get(self, public_documents, revision):
        if revision is None:
            return self._build(public_documents)
        if type(revision) is not str or not _PUBLIC_BUNDLE_REVISION.fullmatch(revision):
            raise ValueError("invalid-public-bundle-revision")
        with self._lock:
            if revision != self._revision or self._index is None:
                self._index = self._build(public_documents)
                self._revision = revision
            return self._index

    def clear(self):
        with self._lock:
            self._revision = None
            self._index = None


_PROJECTED_PUBLIC_INDEX = _ProjectedPublicIndexCache()


def _name_key(value):
    return " ".join(unicodedata.normalize("NFKC", value).lower().split())


def _public_name_trie(documents, by_id):
    """Same exact-name/ambiguity boundary as build-source-filter.cjs.

    Only declared company-market names are aliases. Search keywords, symbols,
    funds and a caller's selected stocks never enter this shared public index.
    """
    aliases = {}
    universe = documents.get("universe_search.json", {})
    rows = universe.get("stocks", [])
    rows = rows.values() if isinstance(rows, dict) else rows
    for row in rows:
        market = row.get("market")
        if market not in {"KR", "KONEX", "US"}:
            continue
        identifier = f"{'KR' if market == 'KONEX' else market}:{row.get('ticker')}"
        if identifier not in by_id:
            continue
        for raw in (row.get("name"), row.get("name_ko")):
            if safe_public_text(raw, 160) is None:
                continue
            alias = _name_key(raw)
            if len(alias) < 3 or not any(char.isalpha() for char in alias):
                continue
            aliases.setdefault(alias, set()).add(identifier)
    trie = {}
    for alias, identifiers in aliases.items():
        node = trie
        for char in alias:
            node = node.setdefault(char, {})
        node[""] = sorted(identifiers)
    return trie


_KOREAN_PARTICLE = re.compile(
    r"(?:에서|에게|으로|은|는|이|가|을|를|의|와|과|에|께|로|도|만|측)"
    r"(?=$|[\s,.;:!?()\[\]{}'\"·/])"
)
_PRODUCT_NAME_CONTEXT = re.compile(r"차종|모델명|제품명|상품명|브랜드명")


def _company_mentions(text, trie, issuer):
    text = _name_key(text)
    matches, ambiguous = set(), set()
    for start in range(len(text)):
        if start and text[start - 1].isalnum():
            continue
        node = trie
        for end in range(start, len(text)):
            node = node.get(text[end])
            if node is None:
                break
            identities = node.get("")
            if not identities or (end + 1 < len(text) and text[end + 1].isalnum()
                                  and not _KOREAN_PARTICLE.match(text, end + 1)):
                continue
            if len(identities) != 1:
                ambiguous.add(text[start:end + 1])
            elif identities[0] != issuer:
                # A product/model may share a translated issuer name. Check
                # its explicit naming sentence only after an exact alias hit.
                sentence_start = max(text.rfind(".", 0, start), text.rfind("!", 0, start), text.rfind("?", 0, start)) + 1
                if not _PRODUCT_NAME_CONTEXT.search(text[sentence_start:start]):
                    matches.add(identities[0])
    return sorted(matches), len(ambiguous)


def _business_material_index(documents, by_id):
    """Index the received public excerpt once per bundle, not once per member."""
    business = project_public_business_overviews(documents)
    trie = _public_name_trie(documents, by_id) if business["rows"] else {}
    materials, index = {}, {}
    rejected_issuer, without_mentions, ambiguous_only = 0, 0, 0
    for row in business["rows"]:
        issuer = row["issuer_id"]
        if issuer not in by_id:
            rejected_issuer += 1
            continue
        mentions, ambiguous = _company_mentions(row["text"], trie, issuer)
        if not mentions:
            without_mentions += 1
            ambiguous_only += bool(ambiguous)
            continue
        source = {**row["source"], "artifact_observed_at": None}
        source["revision"] = _revision(source)
        # Keep the existing DART material protocol. Offsets explicitly describe
        # this published excerpt, not positions in the full filing document.
        suffix = _revision(["public-business-overview", issuer, mentions])[:8]
        identifier = f"event:dart:{source['receipt_no']}:0-{len(row['text'])}:{suffix}"
        material = {
            "stable_id": identifier, "kind": "co_mention_candidate", "verified_event": False,
            "participants": [{"id": issuer, "role": "document_issuer"},
                             *[{"id": key, "role": "mentioned_company"} for key in mentions]],
            "source": source,
            "evidence": {"anchor": "사업의 개요 · 공개 발췌문 내 위치", "char_start": 0,
                         "char_end": len(row["text"]), "excerpt": row["text"],
                         "published_excerpt_truncated": row["truncated"],
                         "fiscal_year": row["fiscal_year"]},
        }
        materials[identifier] = material
        for key in (issuer, *mentions):
            index.setdefault(key, []).append(identifier)
    coverage = {**business["coverage"], "indexed_materials": len(materials),
                "unknown_issuer": rejected_issuer, "no_unique_other_company_mention": without_mentions,
                "ambiguous_alias_only": ambiguous_only,
                "companies_with_materials": len(index)}
    return {"materials": materials, "by_company": index, "coverage": coverage,
            "market_context": index_filing_market_context(business),
            "reported_roles": index_business_roles(business, list(by_id.values()))}


def _add_business_materials(projection, index, positions, by_id):
    """Only the identifier window is private; the cached source index is not."""
    selected = {f"{row['market']}:{row['ticker']}" for row in positions}
    identifiers = sorted({identifier for key in selected for identifier in index["by_company"].get(key, [])})
    if projection is None:
        if index["coverage"]["missing"]:
            return None
        companies = [{key: by_id[identifier][key] for key in ("id", "ticker", "market", "name")}
                     for identifier in sorted(selected & by_id.keys())]
        projection = {
            "schema": "portfolio-auto-evidence-v1", "status": "available" if companies else "empty",
            "companies": companies, "connected_companies": [], "sources": [], "relationships": [],
            "materials": [], "common_materials": [], "verified_events": [], "corrections": [],
            "coverage": {"requested": len(selected), "matched": len(companies)},
            "_meta": {"source_file": "kr_business_overview_public.json", "automatic_evidence": True,
                      "manual_review_provenance": False, "delivery": "private-response-only",
                      "shared_cache": False, "external_model_calls": 0,
                      "runtime_freshness": "not-automatically-reverified"},
        }
    else:
        projection = deepcopy(projection)
    existing = {row["stable_id"] for row in projection["materials"]}
    sources = {row["id"]: row for row in projection["sources"]}
    for identifier in identifiers:
        if identifier in existing:
            continue
        material = deepcopy(index["materials"][identifier])
        company_ids = sorted(selected & {row["id"] for row in material["participants"]})
        material["portfolio_company_ids"] = company_ids
        material["revision"] = _revision(material)
        projection["materials"].append(material)
        sources.setdefault(material["source"]["id"], material["source"])
        if len(company_ids) >= 2:
            common = {"stable_id": "common-material:" + identifier, "material_id": identifier,
                      "portfolio_company_ids": company_ids, "kind": "shared-source-material",
                      "verified_event": False}
            common["revision"] = _revision(common)
            projection["common_materials"].append(common)
    projection["sources"] = list(sources.values())
    if not index["coverage"]["missing"]:
        projection["coverage"]["business_overviews"] = deepcopy(index["coverage"])
        projection["coverage"]["co_mention_candidates"] = len(projection["materials"])
        projection["coverage"]["common_materials"] = len(projection["common_materials"])
    return projection


def _automatic_evidence_text_is_safe(projection):
    """Reapply the public text boundary before returning automatic excerpts."""
    for company in (*projection.get("companies", []), *projection.get("connected_companies", [])):
        if safe_public_text(company.get("name"), 300) is None:
            return False
    for source in projection.get("sources", []):
        report_name = source.get("report_name")
        if report_name is not None and safe_public_text(report_name, 300) is None:
            return False
    for relationship in projection.get("relationships", []):
        role = relationship.get("evidence", {}).get("role")
        if role is not None and safe_public_text(role, 200) is None:
            return False
        fields = relationship.get("evidence", {}).get("source_row", {}).get("fields", {})
        # Structured receipt/corp/date/percentage fields have strict typed gates;
        # running identifier digits through prose PII heuristics rejects real receipts.
        for key in ("corp_name", "nm", "inv_prm", "relate", "stock_knd"):
            value = fields.get(key)
            if value is not None and safe_public_text(value, 300) is None:
                return False
    for material in projection.get("materials", []):
        evidence = material.get("evidence", {})
        if (
            safe_public_text(evidence.get("anchor"), 100) is None
            or safe_public_text(evidence.get("excerpt"), 2000) is None
        ):
            return False
    return True


def _evidence_record_date(row):
    source = row.get("source", {})
    if type(source) is not dict:
        return ""
    value = source.get("as_of")
    if type(value) is not str:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return ""


def _date_ordered(rows):
    """Newest evidence first, with a stable identifier tie-break."""
    ordered = sorted(
        rows, key=lambda row: row.get("stable_id", row.get("id", ""))
    )
    ordered.sort(key=_evidence_record_date, reverse=True)
    return ordered


def _bound_automatic_evidence(projection):
    """Bound private-response records without claiming the projection is complete."""
    relationships = projection["relationships"]
    materials = projection["materials"]
    retained_relationships = _date_ordered(relationships)[
        :MAX_AUTOMATIC_EVIDENCE_RELATIONSHIPS
    ]
    material_limit = (
        MAX_AUTOMATIC_EVIDENCE_CANDIDATES - len(retained_relationships)
    )
    shared_ids = {row["material_id"] for row in projection["common_materials"]}
    ordered_materials = _date_ordered(materials)
    # Do not bury a source shared by selected stocks under a long tail of
    # single-stock filings. The returned view is still chronological.
    preferred_materials = [row for row in ordered_materials if row["stable_id"] in shared_ids]
    preferred_materials += [row for row in ordered_materials if row["stable_id"] not in shared_ids]
    retained_materials = _date_ordered(preferred_materials[:material_limit])
    retained_material_ids = {row["stable_id"] for row in retained_materials}

    common_by_material = {
        row["material_id"]: row for row in projection["common_materials"]
        if row["material_id"] in retained_material_ids
    }
    common_materials = [
        common_by_material[row["stable_id"]]
        for row in retained_materials
        if row["stable_id"] in common_by_material
    ]
    candidate_source_ids = {
        row["source"]["id"]
        for row in (*retained_relationships, *retained_materials)
    }
    selected_company_ids = {row["id"] for row in projection["companies"]}
    candidate_source_ids.update(
        row["source"]["id"] for row in projection["corrections"]
        if row["issuer"] in selected_company_ids
    )
    retained_sources = _date_ordered([
        row for row in projection["sources"] if row["id"] in candidate_source_ids
    ])[:MAX_AUTOMATIC_EVIDENCE_SOURCES]
    retained_source_ids = {row["id"] for row in retained_sources}
    retained_relationships = [
        row for row in retained_relationships
        if row["source"]["id"] in retained_source_ids
    ]
    retained_materials = [
        row for row in retained_materials
        if row["source"]["id"] in retained_source_ids
    ]
    retained_material_ids = {row["stable_id"] for row in retained_materials}
    common_materials = [
        common_by_material[row["stable_id"]]
        for row in retained_materials
        if row["stable_id"] in common_by_material
    ]
    retained_corrections = [
        row for row in _date_ordered(projection["corrections"])
        if row["source"]["id"] in retained_source_ids
    ][:MAX_AUTOMATIC_EVIDENCE_CORRECTIONS]

    bounded = deepcopy(projection)
    bounded["relationships"] = retained_relationships
    bounded["materials"] = retained_materials
    bounded["common_materials"] = common_materials
    bounded["corrections"] = retained_corrections
    bounded["sources"] = retained_sources
    response_records = {
        "candidate_limit": MAX_AUTOMATIC_EVIDENCE_CANDIDATES,
        "relationship_limit": MAX_AUTOMATIC_EVIDENCE_RELATIONSHIPS,
        "source_limit": MAX_AUTOMATIC_EVIDENCE_SOURCES,
        "correction_limit": MAX_AUTOMATIC_EVIDENCE_CORRECTIONS,
        "ordering": "selected-shared-materials-first-within-cap-then-source-as-of-descending-unknown-last-then-stable-id",
        "relationships": {
            "total": len(relationships),
            "returned": len(retained_relationships),
            "omitted": len(relationships) - len(retained_relationships),
            "truncated": len(retained_relationships) < len(relationships),
        },
        "materials": {
            "total": len(materials),
            "returned": len(retained_materials),
            "omitted": len(materials) - len(retained_materials),
            "truncated": len(retained_materials) < len(materials),
        },
        "common_materials": {
            "total": len(projection["common_materials"]),
            "returned": len(common_materials),
            "omitted": len(projection["common_materials"]) - len(common_materials),
            "truncated": len(common_materials) < len(projection["common_materials"]),
        },
        "corrections": {
            "total": len(projection["corrections"]),
            "returned": len(retained_corrections),
            "omitted": len(projection["corrections"]) - len(retained_corrections),
            "truncated": len(retained_corrections) < len(projection["corrections"]),
        },
        "sources": {
            "total": len(projection["sources"]),
            "returned": len(retained_sources),
            "omitted": len(projection["sources"]) - len(retained_sources),
            "truncated": len(retained_sources) < len(projection["sources"]),
        },
    }
    bounded["coverage"]["response_records"] = response_records
    bounded["revision"] = _revision({
        key: value for key, value in bounded.items() if key != "revision"
    })
    return bounded, response_records


def _automatic_evidence(public_documents, positions, public_index):
    artifact = public_documents.get(_AUTOMATIC_EVIDENCE_FILE)
    business = public_index["business_materials"]
    if artifact is None and business["coverage"]["missing"]:
        return None, {
            "status": "not-supplied",
            "automatic_relationships": {"total": 0, "returned": 0, "omitted": 0, "truncated": False},
            "automatic_materials": {"total": 0, "returned": 0, "omitted": 0, "truncated": False},
            "quotes": {"total": 0, "returned": 0, "omitted": 0, "truncated": False},
            "quote_status": "not-supplied",
        }
    try:
        if artifact is not None and (
            type(artifact) is not dict
            or type(artifact.get("scope")) is not dict
            or artifact["scope"].get("mode") != _AUTOMATIC_EVIDENCE_SCOPE
        ):
            raise ValueError("automatic evidence public scope required")
        projection = project_portfolio_evidence(artifact, positions) if artifact is not None else None
        projection = _add_business_materials(projection, business, positions, public_index["by_id"])
        projection = attach_business_relationships(projection, business["reported_roles"], positions)
        projection = attach_parent_relationships(projection, public_index["filing_excerpts"], positions)
        projection = attach_annual_customer_table_relationships(
            projection, public_index["annual_customer_tables"], positions
        )
        if not _automatic_evidence_text_is_safe(projection):
            raise ValueError("automatic evidence text rejected")
        projection, response_records = _bound_automatic_evidence(projection)
    except Exception:
        return None, {
            "status": "rejected",
            "automatic_relationships": {"total": 0, "returned": 0, "omitted": 0, "truncated": False},
            "automatic_materials": {"total": 0, "returned": 0, "omitted": 0, "truncated": False},
            "quotes": {"total": 0, "returned": 0, "omitted": 0, "truncated": False},
            "quote_status": "rejected",
        }
    materials = projection["materials"]
    returned_quotes = sum(
        isinstance(material.get("evidence", {}).get("excerpt"), str)
        for material in materials
    )
    total_quotes = response_records["materials"]["total"]
    return projection, {
        "status": projection["status"],
        "automatic_relationships": response_records["relationships"],
        "automatic_materials": response_records["materials"],
        "quotes": {"total": total_quotes, "returned": returned_quotes,
                   "omitted": total_quotes - returned_quotes,
                   "truncated": returned_quotes < total_quotes},
        "quote_status": "available" if returned_quotes else "no-matching-quotes",
        **({"business_overviews": deepcopy(business["coverage"])} if not business["coverage"]["missing"] else {}),
    }


def validate_positions(positions):
    """No coercion/fuzzy lookup, and never echo rejected private input."""
    if type(positions) is not list or not 1 <= len(positions) <= MAX_SYMBOLS:
        raise ValueError("invalid-portfolio-window")
    out = []
    seen = set()
    for position in positions:
        if type(position) is not dict or set(position) != {"ticker", "market"}:
            raise ValueError("identifier-only-input-required")
        ticker, market = position["ticker"], position["market"]
        if type(ticker) is not str or type(market) is not str:
            raise ValueError("invalid-security-identifier")
        if market not in _TICKER or not _TICKER[market].fullmatch(ticker):
            raise ValueError("invalid-security-identifier")
        key = f"{market}:{ticker}"
        if key not in seen:
            out.append({"id": key, "ticker": ticker, "market": market})
            seen.add(key)
    return out


def _revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    allow_nan=False).encode()).hexdigest()


def _document_revision(document):
    """Read revision covers displayed semantics, never local capture metadata."""
    fingerprint = deepcopy(document)
    fingerprint.pop("revision", None)
    fingerprint.pop("capture_archive", None)
    return _revision(fingerprint)


def analyze_portfolio(positions, public_documents, *, public_bundle_revision=None, price_documents=None):
    """Join a selected window against explicit public-only source projections.

    A shared filing is common material, NOT a confirmed economic event, trading
    relationship or direction of price impact. Sector counts are not money
    weights. No rating, private history or generated investment advice is added.
    """
    requested = validate_positions(positions)
    # The optional local sidecar is never part of the shared public index.
    # Source permissions remain owned by the pure price projector.
    if price_documents is None:
        price_documents = {}
    if (type(price_documents) is not dict
            or set(price_documents) - {"kr_close", "kr_charts", "us_history_meta", "us_history"}):
        raise ValueError("invalid-price-source-set")
    projected = _PROJECTED_PUBLIC_INDEX.get(public_documents, public_bundle_revision)
    by_id = projected["by_id"]
    companies, missing, documents, groups = [], [], {}, {}
    for request in requested:
        company = by_id.get(request["id"])
        if company is None:
            missing.append({**request, "reason": "not-in-supplied-public-sources"})
            continue
        # Deliberately closed projection, even if the upstream contract expands.
        selected = {**request, "name": company["name"],
                    "facts": deepcopy(company.get("facts", [])), "document_ids": []}
        if len(company.get("source_names", [])) > 1:
            selected["source_names"] = deepcopy(company["source_names"])
        sector = company.get("sector")
        if sector:
            selected["sector"] = sector
            groups.setdefault(sector, []).append(request["id"])
        for doc in company.get("documents", []):
            # Only fields produced by the source policy can enter this join.
            key = doc["id"]
            if key not in documents:
                documents[key] = {field: doc[field] for field in
                                  ("id", "title", "url", "as_of", "kind", "source")}
                documents[key]["company_ids"] = []
                if doc.get("capture_archive") == 'retained-public-capture':
                    documents[key]["capture_archive"] = doc['capture_archive']
            target = documents[key]
            if request["id"] not in target["company_ids"]:
                target["company_ids"].append(request["id"])
            if key not in selected["document_ids"]:
                selected["document_ids"].append(key)
        companies.append(selected)

    all_document_list = sorted(
        documents.values(), key=lambda row: (row["as_of"], row["id"]), reverse=True
    )
    returned_document_ids = {
        row["id"] for row in all_document_list[:MAX_RESPONSE_DOCUMENTS]
    }
    document_list = [
        row for row in all_document_list if row["id"] in returned_document_ids
    ]
    for company in companies:
        company["document_ids"] = [
            identifier for identifier in company["document_ids"]
            if identifier in returned_document_ids
        ]
    source_match_coverage = attach_source_matches(public_documents, document_list)
    lineage_coverage = attach_event_lineage(public_documents.get(_AUTOMATIC_EVIDENCE_FILE),
                                           document_list, list(by_id.values()))
    contract_coverage = attach_contract_facts(public_documents.get(_AUTOMATIC_EVIDENCE_FILE),
                                             document_list, list(by_id.values()))
    termination_coverage = attach_contract_terminations(public_documents.get(_AUTOMATIC_EVIDENCE_FILE),
                                                        document_list, list(by_id.values()))
    for doc in document_list:
        doc["company_ids"].sort()
        doc["revision"] = _document_revision(doc)
    common = [{"document_id": doc["id"], "company_ids": doc["company_ids"][:],
               "kind": "shared-source-document", "verified_common_event": False}
              for doc in document_list if len(doc["company_ids"]) > 1]
    exposures = [{"sector": sector, "company_ids": sorted(ids),
                  "company_count": len(ids), "measure": "company-count-not-capital-weight"}
                 for sector, ids in sorted(groups.items()) if len(ids) > 1]
    price_projection = project_portfolio_prices([
        {"ticker": request["ticker"], "market": request["market"]}
        for request in requested
    ], **price_documents)
    evidence_projection, automatic_evidence_coverage = _automatic_evidence(
        public_documents,
        [{"ticker": request["ticker"], "market": request["market"]}
         for request in requested],
        projected,
    )
    if (isinstance(public_documents, dict) and isinstance(public_documents.get("portfolio.json"), dict)
            and "dart_catalyst_alerts" in public_documents["portfolio.json"]):
        automatic_evidence_coverage["source_matches"] = source_match_coverage
    market_context = project_market_context(public_documents, companies, list(by_id.values()),
                                           projected["business_materials"]["market_context"], projected["filing_excerpts"],
                                           news_name_index=projected["news_names"])
    companies_with_documents = sum(bool(company["document_ids"]) for company in companies)
    result = {
        "schema": "alphaconsole-portfolio-v1",
        "companies": companies,
        "documents": document_list,
        "automatic_evidence": evidence_projection,
        "prices": price_projection["quotes"],
        "common_materials": common,
        "sector_groups": exposures,
        "relationships": [],
        "market_context": market_context,
        "contract_events": select_contract_events(projected["contract_events"], [row["id"] for row in requested]),
        "coverage": {
            "requested": len(requested), "matched": len(companies),
            "missing": missing,
            "sources": deepcopy(projected["coverage"]),
            "missing_source_files": [name for name in PUBLIC_SOURCE_FILES if name not in public_documents],
            "company_data": [{"id": c["id"],
                              "facts": "available" if c["facts"] else "not-supplied-or-rejected",
                              "documents": "available" if c["document_ids"] else "not-supplied-or-rejected"}
                             for c in companies],
            "evidence": {
                "document_links": len(document_list),
                **({"capture_archive": deepcopy(projected['capture_archive'])}
                   if projected['capture_archive']['input'] else {}),
                "document_records": {
                    "limit": MAX_RESPONSE_DOCUMENTS,
                    "ordering": "as-of-descending-then-id",
                    "total": len(all_document_list),
                    "returned": len(document_list),
                    "omitted": len(all_document_list) - len(document_list),
                    "truncated": len(document_list) < len(all_document_list),
                },
                "companies_with_document_links": companies_with_documents,
                **({"event_lineage": lineage_coverage} if isinstance(public_documents.get(_AUTOMATIC_EVIDENCE_FILE), dict)
                   and "documentFamilies" in public_documents[_AUTOMATIC_EVIDENCE_FILE] else {}),
                **({"contract_facts": contract_coverage} if isinstance(public_documents.get(_AUTOMATIC_EVIDENCE_FILE), dict)
                   and "contract_facts" in public_documents[_AUTOMATIC_EVIDENCE_FILE] else {}),
                **({"contract_terminations": termination_coverage} if isinstance(public_documents.get(_AUTOMATIC_EVIDENCE_FILE), dict)
                   and "contract_terminations" in public_documents[_AUTOMATIC_EVIDENCE_FILE] else {}),
                **automatic_evidence_coverage,
            },
            "relationships": "not-established-by-this-source-contract",
            "closing_prices": deepcopy(price_projection["coverage"]),
        },
        "_meta": {"delivery": "private-response-only", "shared_cache": False,
                  "public_projection_cache": "public-bundle-revision-only",
                  "selected_view_limits": {
                      "documents": MAX_RESPONSE_DOCUMENTS,
                      "automatic_candidates": MAX_AUTOMATIC_EVIDENCE_CANDIDATES,
                      "automatic_sources": MAX_AUTOMATIC_EVIDENCE_SOURCES,
                  },
                  "external_model_calls": 0, "operator_private_sources_used": False,
                  "financial_advice": False},
    }
    # Only sanitized content; equality fingerprint, not a timestamp or a score.
    result["revision"] = _revision(result)
    return result


def _reset_projection_cache_for_tests():
    _PROJECTED_PUBLIC_INDEX.clear()

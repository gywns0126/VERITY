"""Offline append protocol only; synthetic reviews are not operator acceptance."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import urllib.request

import pytest

from api.intelligence import portfolio_business_judgment as producer
from api.intelligence import portfolio_ai_public as public
from api.intelligence import portfolio_reported_period as period
from api.intelligence import portfolio_ai_fallback as fallback
from tests.test_portfolio_reported_period import _zip

AS_OF = "2026-10-10"
LEGACY_QUOTE = "당사는 2025년 Synthetic A에 반도체 부품을 공급하며, Synthetic A는 당사의 주요 매출처입니다."


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch):
    # Override unrelated account/trading fixtures; all documents below are synthetic.
    def denied(*args, **kwargs):
        raise AssertionError("offline append must not access network/provider/ledger")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(fallback, "openai_transport", denied)
    monkeypatch.setattr(fallback, "run_document", denied)
    monkeypatch.setattr(fallback.sqlite3, "connect", denied)


def _doc(quote=LEGACY_QUOTE):
    return {"source_id": "source:dart:20260312000001", "issuer_id": "KR:111111",
            "issuer_name": "Synthetic Issuer", "as_of": "2026-03-12",
            "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312000001",
            "text": quote, "counterparties": [{"id": "KR:222222", "name": "Synthetic A"}]}


def _row(document, *, v3=False):
    return {"company_id": document["issuer_id"], "counterparty_id": "KR:222222",
            "source_id": document["source_id"], "source_version": public._digest(document),
            "quote": document["text"],
            "scope_quote": "당사의 반도체사업부" if v3 else "Synthetic A는 당사의 주요 매출처",
            "period_quote": "2025년",
            "degree": {"value": "medium", "basis": "reported_qualitative",
                       "quote": "주요 고객" if v3 else "주요 매출처"},
            "impact": {"direction": "unknown", "channel": "unknown", "condition": None, "quote": None},
            "counter_evidence_quotes": [], "missing_evidence": ["denominator"] if v3 else [],
            "reason": "합성 원문 범위만 검사합니다.", "review_trigger": "새 공시 시 재검토합니다."}


def _review(literal):
    return {"judgment_id": literal["id"], "judgment_revision": literal["revision"],
            "decision": "accept", "reviewed_on": AS_OF, "reason": "합성 protocol 검사용 수락입니다.",
            "checks": {name: True for name in ("company_scope", "period", "degree_support",
                       "impact_mechanism", "counter_evidence", "source_context")}}


def _entry(document):
    return {"document": document, "answer": {"candidates": [{"counterparty_id": "KR:222222",
            "role": "customer", "quote": document["text"]}]}}


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _load_script(filename):
    path = Path(__file__).resolve().parents[1] / "scripts/member-map" / filename
    spec = importlib.util.spec_from_file_location("append_period_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def append_case(tmp_path, monkeypatch):
    # pytest may supply /var on macOS; normalize fixtures, never relax product guards.
    tmp_path = tmp_path.resolve()
    exporter = _load_script("export-ai-candidates.py")
    source = _doc("당사의 반도체사업부 주요 고객은 Synthetic A 등이 있습니다.")
    row = _row(source, v3=True)
    registry = {source["issuer_id"]: {"name": source["issuer_name"], "corp_code": "00000001"}}
    body = _zip(quote=source["text"], member=source["source_id"][12:] + ".xml",
        corp="00000001", issuer=source["issuer_name"],
        table="<TABLE><TR><TH>업체</TH><TH>2025년</TH><TH>2024년</TH></TR>"
              "<TR><TD>Synthetic A</TD><TD>100</TD><TD>90</TD></TR>"
              "<TR><TD>계</TD><TD>200</TD><TD>180</TD></TR></TABLE>")
    archives = {source["source_id"]: body}
    row["period_context_v3"] = period.build_reported_customer_period(
        source, row, archives=archives, issuer_registry=registry)
    literal = producer.validate_company_judgments({"judgments": [row], "remaining_count": 0},
        [source], as_of=AS_OF, period_archives=archives, issuer_registry=registry)["judgments"][0]
    incoming, output = tmp_path / "incoming.json", tmp_path / "member_map_ai_candidates.json"
    raw, receipts, registry_path = tmp_path / "raw.json", tmp_path / "reviews.json", tmp_path / "registry.json"
    directory = tmp_path / "originals"
    directory.mkdir()
    archive = directory / ("dart-document-" + source["source_id"][12:] + ".zip")
    archive.write_bytes(body)
    _write(raw, {"documents": [source], "answer": {"judgments": [row], "remaining_count": 0}})
    _write(receipts, [_review(literal)])
    _write(registry_path, registry)
    options = {"judgment_input": raw, "judgment_reviews": receipts, "judgment_as_of": AS_OF,
               "period_source_dir": directory, "issuer_registry_path": registry_path}
    monkeypatch.setattr(exporter, "load_public_sources", lambda _: {})
    entries = [_entry(source)]
    documents, rows, reviews = [], [], []
    # Two independent legacy records plus one new v3 record. No actual65 claim.
    for number in (2, 3):
        document = _doc()
        receipt = "2026031200000" + str(number)
        document.update(source_id="source:dart:" + receipt,
                        url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt)
        row = _row(document)
        literal = producer.validate_company_judgments(
            {"judgments": [row], "remaining_count": 0}, [document],
            as_of=options["judgment_as_of"])["judgments"][0]
        documents.append(document); rows.append(row); reviews.append(_review(literal))
        entries.append(_entry(document))
    _write(incoming, {"schema": "local-ai-review-input-v1", "entries": entries})
    catalog = [{"id": "KR:111111", "market": "KR", "ticker": "111111", "name": "Synthetic Issuer"},
               {"id": "KR:222222", "market": "KR", "ticker": "222222", "name": "Synthetic A"}]
    monkeypatch.setattr(exporter, "project_public_sources", lambda _: {"companies": catalog})
    legacy_input, legacy_reviews = tmp_path / "legacy-input.json", tmp_path / "legacy-reviews.json"
    _write(legacy_input, {"documents": documents, "answer": {"judgments": rows, "remaining_count": 0}})
    _write(legacy_reviews, reviews)
    exporter.export_candidates(incoming, tmp_path, output, judgment_input=legacy_input,
                               judgment_reviews=legacy_reviews, judgment_as_of=options["judgment_as_of"])
    previous = tmp_path / "previous-public.json"
    previous.write_bytes(output.read_bytes())
    baseline = json.loads(previous.read_bytes())
    assert len(baseline["candidates"]) == 3
    assert len(baseline["company_judgments"]["judgments"]) == 2
    validator = _load_script("validate-public-ai-artifact.py")
    monkeypatch.setattr(validator, "read_review_sources", lambda _: {})
    monkeypatch.setattr(validator, "project_public_sources", lambda _: {"companies": catalog})
    validation = {"period_input": options["judgment_input"],
                  "period_source_dir": options["period_source_dir"],
                  "issuer_registry_path": options["issuer_registry_path"]}
    return {"exporter": exporter, "incoming": incoming, "output": output, "options": options,
            "previous": previous, "baseline": baseline, "archive": archive,
            "validator": validator, "validation": validation, "source": source}


def _append(case):
    return case["exporter"].export_candidates(case["incoming"], case["output"].parent,
        case["output"], append_public_judgments=case["previous"], **case["options"])


def _validate(case, output, **options):
    body = case["output"].read_bytes()
    return case["validator"].validate(case["output"], hashlib.sha256(body).hexdigest(),
                                      case["output"].parent, output, **options)


def test_append_keeps_candidates_coverage_and_two_legacy_rows_exact(append_case, tmp_path, monkeypatch):
    case = append_case
    paths = [case["incoming"], case["previous"], case["archive"],
             case["options"]["judgment_input"], case["options"]["judgment_reviews"],
             case["options"]["issuer_registry_path"]]
    before = {path: path.read_bytes() for path in paths}
    result = _append(case)
    artifact = json.loads(case["output"].read_bytes())
    assert result["network_calls"] == 0 and result["published"] is False
    for key in ("candidates", "coverage"):
        assert artifact[key] == case["baseline"][key]
    rows = artifact["company_judgments"]["judgments"]
    assert rows[:2] == case["baseline"]["company_judgments"]["judgments"]
    assert len(rows) == 3 and rows[2]["status"] == "accepted" and rows[2]["degree"] == "medium"
    assert rows[2]["impact"]["direction"] == "unknown"
    assert "core_selection" not in rows[2] and "economic_v2" not in rows[2]
    seen = []
    original = period.validate_reported_customer_period
    def record(context, source, row, **kwargs):
        seen.append((source["source_id"], deepcopy(kwargs)))
        return original(context, source, row, **kwargs)
    monkeypatch.setattr(period, "validate_reported_customer_period", record)
    directory = tmp_path / "validated"
    directory.mkdir()
    destination = directory / "member_map_ai_candidates.json"
    validated = _validate(case, destination, **case["validation"])
    assert validated["network_calls"] == 0 and validated["count"] == 3
    assert destination.read_bytes() == case["output"].read_bytes()
    assert [source for source, _ in seen] == [case["source"]["source_id"]]
    assert seen[0][1]["archives"] == {case["source"]["source_id"]: before[case["archive"]]}
    assert {path: path.read_bytes() for path in paths} == before


@pytest.mark.parametrize("failure", ["input", "reviews", "as-of", "all", "retained", "duplicate-id",
    "duplicate-added", "coverage", "candidate", "order", "stale-source", "stale-review",
    "original", "pending", "no-addition"])
def test_append_rejects_conflicts_without_replacing_output(append_case, failure):
    case = append_case
    options = deepcopy(case["options"])
    if failure in {"input", "reviews", "as-of", "all"}:
        names = {"input": "judgment_input", "reviews": "judgment_reviews", "as-of": "judgment_as_of"}
        for name in names.values() if failure == "all" else [names[failure]]:
            options.pop(name)
    elif failure == "retained":
        options["retained_public_judgments"] = case["previous"]
    elif failure == "duplicate-id":
        case["exporter"].export_candidates(case["incoming"], case["output"].parent,
                                           case["output"], **options)
        prior = deepcopy(case["baseline"])
        prior["company_judgments"]["judgments"].extend(
            json.loads(case["output"].read_bytes())["company_judgments"]["judgments"])
        _write(case["previous"], prior)
    elif failure in {"coverage", "candidate", "order"}:
        prior = deepcopy(case["baseline"])
        if failure == "coverage":
            prior["coverage"]["input"] += 1
            prior["coverage"]["skipped"] += 1
        elif failure == "order":
            prior["candidates"].reverse()
        else:
            candidate = next(c for c in prior["candidates"] if c["source_id"] == case["source"]["source_id"])
            candidate["quote"] += " 추가 문장입니다."
            candidate["revision"] = public._digest({k: v for k, v in candidate.items() if k != "revision"})
        catalog = case["exporter"].project_public_sources({})["companies"]
        assert public.validate_public_ai_review(prior, catalog) == prior
        _write(case["previous"], prior)
    elif failure == "original":
        case["archive"].write_bytes(case["archive"].read_bytes() + b"changed")
    elif failure == "pending":
        _write(options["judgment_reviews"], [])
    elif failure == "stale-review":
        reviews = json.loads(options["judgment_reviews"].read_bytes())
        reviews[0]["judgment_revision"] = "0" * 64
        _write(options["judgment_reviews"], reviews)
    else:
        raw = json.loads(options["judgment_input"].read_bytes())
        if failure == "stale-source":
            raw["documents"][0]["text"] += " 다른 원문입니다."
        elif failure == "duplicate-added":
            raw["answer"]["judgments"].append(deepcopy(raw["answer"]["judgments"][0]))
        else:
            raw["answer"]["judgments"] = []
        _write(options["judgment_input"], raw)
    case["output"].write_bytes(b"last-good-output")
    with pytest.raises((ValueError, OSError)):
        case["exporter"].export_candidates(case["incoming"], case["output"].parent, case["output"],
            append_public_judgments=case["previous"], **options)
    assert case["output"].read_bytes() == b"last-good-output"


@pytest.mark.parametrize("keep", [(), ("period_input",), ("period_source_dir",), ("issuer_registry_path",),
    ("period_input", "period_source_dir"), ("period_input", "issuer_registry_path"),
    ("period_source_dir", "issuer_registry_path")])
def test_validator_v3_requires_all_original_arguments_and_freezes_output(append_case, tmp_path, keep):
    case = append_case
    _append(case)
    directory = tmp_path / "validated"
    directory.mkdir()
    output = directory / "member_map_ai_candidates.json"
    output.write_bytes(b"last-good-output")
    with pytest.raises(ValueError):
        _validate(case, output, **{key: case["validation"][key] for key in keep})
    assert output.read_bytes() == b"last-good-output"


@pytest.mark.parametrize("failure", ["archive", "source", "registry", "missing"])
def test_validator_recomputes_v3_instead_of_trusting_prepared_wire(append_case, tmp_path, failure):
    case = append_case
    _append(case)
    artifact = case["output"].read_bytes()
    if failure == "archive":
        case["archive"].write_bytes(case["archive"].read_bytes() + b"changed")
    elif failure == "missing":
        case["archive"].unlink()
    elif failure == "registry":
        _write(case["validation"]["issuer_registry_path"], {})
    else:
        raw = json.loads(case["validation"]["period_input"].read_bytes())
        raw["documents"][0]["text"] += " 변경된 원문입니다."
        _write(case["validation"]["period_input"], raw)
    directory = tmp_path / "validated"
    directory.mkdir()
    output = directory / "member_map_ai_candidates.json"
    output.write_bytes(b"last-good-output")
    with pytest.raises((ValueError, OSError)):
        _validate(case, output, **case["validation"])
    assert output.read_bytes() == b"last-good-output"
    assert case["output"].read_bytes() == artifact


def test_validator_legacy_two_rows_remain_exact_without_period_loading(append_case, tmp_path, monkeypatch):
    case = append_case
    def denied(*args, **kwargs):
        raise AssertionError("legacy validation must not recompute v3 originals")
    monkeypatch.setattr(period, "validate_reported_customer_period", denied)
    directory = tmp_path / "validated"
    directory.mkdir()
    output = directory / "member_map_ai_candidates.json"
    _validate(case, output)
    assert output.read_bytes() == case["previous"].read_bytes()


def _append_only(case, **overrides):
    arguments = {**case["options"], "append_public_judgments": case["previous"],
                 "append_only": True, **overrides}
    return case["exporter"].export_candidates(None, case["output"].parent, case["output"], **arguments)


def test_append_only_reuses_published_candidates_without_extractor_and_keeps_legacy_bytes(append_case, monkeypatch):
    case = append_case
    before = {path: path.read_bytes() for path in [case["previous"], case["archive"], *[
        case["options"][key] for key in ("judgment_input", "judgment_reviews", "issuer_registry_path")]]}
    def denied(*args, **kwargs):
        raise AssertionError("append-only must not replay/extract old candidates")
    for name in ("load_ai_review", "prepare_review_candidates", "_worker_payloads"):
        monkeypatch.setattr(case["exporter"], name, denied)
    result = _append_only(case)
    artifact = json.loads(case["output"].read_bytes())
    assert result["network_calls"] == 0 and result["published"] is False
    assert artifact["candidates"] == case["baseline"]["candidates"]
    assert artifact["coverage"] == case["baseline"]["coverage"]
    rows = artifact["company_judgments"]["judgments"]
    old = case["baseline"]["company_judgments"]["judgments"]
    assert len(rows) == 3 and rows[:2] == old
    encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    assert [encode(row) for row in rows[:2]] == [encode(row) for row in old]
    assert (rows[2]["status"], rows[2]["degree"], rows[2]["impact"]["direction"]) == (
        "accepted", "medium", "unknown")
    assert "period_context_v3" in rows[2] and "core_selection" not in rows[2]
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("failure", ["judgment_input", "judgment_reviews", "judgment_as_of",
    "period_source_dir", "issuer_registry_path", "append_public_judgments", "input", "worker", "flag-type", "retained"])
def test_append_only_rejects_partial_or_wrong_mode_before_output(append_case, failure):
    case = append_case
    arguments = {**case["options"], "append_public_judgments": case["previous"], "append_only": True}
    incoming = None
    if failure in arguments:
        arguments.pop(failure)
    elif failure == "input":
        incoming = case["incoming"]
    elif failure == "worker":
        arguments["worker_state"] = True
    elif failure == "flag-type":
        arguments["append_only"] = 1
    else:
        arguments["retained_public_judgments"] = case["previous"]
    case["output"].write_bytes(b"last-good-output")
    with pytest.raises(ValueError):
        case["exporter"].export_candidates(incoming, case["output"].parent, case["output"], **arguments)
    assert case["output"].read_bytes() == b"last-good-output"


def test_append_only_requires_every_new_row_to_have_v3(append_case):
    case = append_case
    raw = json.loads(case["options"]["judgment_input"].read_bytes())
    extra = deepcopy(raw["answer"]["judgments"][0])
    extra.pop("period_context_v3")
    raw["answer"]["judgments"].append(extra)
    _write(case["options"]["judgment_input"], raw)
    case["output"].write_bytes(b"last-good-output")
    with pytest.raises(ValueError, match="^append-only-requires-period-originals$"):
        _append_only(case)
    assert case["output"].read_bytes() == b"last-good-output"


@pytest.mark.parametrize("failure", ["source_id", "url", "as_of", "original", "missing-original", "catalog"])
def test_append_only_rechecks_current_catalog_candidate_source_and_native_original(append_case, monkeypatch, failure):
    case = append_case
    if failure in {"source_id", "url", "as_of"}:
        previous = deepcopy(case["baseline"])
        candidate = next(c for c in previous["candidates"] if c["source_id"] == case["source"]["source_id"])
        if failure == "source_id":
            candidate["source_id"] = "source:dart:20260312000004"
            candidate["url"] = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312000004"
            candidate["id"] = "automatic:ai:" + public._digest([candidate["source_id"], candidate["issuer_id"],
                candidate["counterparty_id"], candidate["role"]])[:24]
        elif failure == "url":
            candidate["url"] = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312000004"
        else:
            candidate["as_of"] = "2026-03-13"
        candidate["revision"] = public._digest({k: v for k, v in candidate.items() if k != "revision"})
        _write(case["previous"], previous)
    elif failure == "original":
        case["archive"].write_bytes(case["archive"].read_bytes() + b"changed")
    elif failure == "missing-original":
        case["archive"].unlink()
    else:
        catalog = deepcopy(case["exporter"].project_public_sources({})["companies"])
        catalog[0]["name"] = "Different Issuer"
        monkeypatch.setattr(case["exporter"], "project_public_sources", lambda _: {"companies": catalog})
    before = case["previous"].read_bytes()
    case["output"].write_bytes(b"last-good-output")
    with pytest.raises((ValueError, OSError)):
        _append_only(case)
    assert case["output"].read_bytes() == b"last-good-output"
    assert case["previous"].read_bytes() == before


def test_docs_only_validator_accepts_only_fresh_original_bound_projection(append_case, tmp_path, monkeypatch):
    case = append_case
    _append_only(case)
    raw = json.loads(case["validation"]["period_input"].read_bytes())
    docs = tmp_path.resolve() / "documents-only.json"
    _write(docs, {"documents": raw["documents"]})
    validation = {**case["validation"], "period_input": docs}
    seen = []
    original = period.validate_reported_customer_period
    def record(context, source, row, **kwargs):
        seen.append((source["source_id"], deepcopy(kwargs["archives"])))
        return original(context, source, row, **kwargs)
    monkeypatch.setattr(period, "validate_reported_customer_period", record)
    directory = tmp_path.resolve() / "documents-validated"
    directory.mkdir()
    destination = directory / "member_map_ai_candidates.json"
    _validate(case, destination, **validation)
    assert destination.read_bytes() == case["output"].read_bytes()
    assert seen == [(case["source"]["source_id"], {case["source"]["source_id"]: case["archive"].read_bytes()})]


@pytest.mark.parametrize("failure", ["extra-top-field", "extra-document-field", "original", "missing-original", "partial"])
def test_docs_only_validator_rejects_extra_fields_and_missing_or_changed_originals(append_case, tmp_path, failure):
    case = append_case
    _append_only(case)
    raw = json.loads(case["validation"]["period_input"].read_bytes())
    payload = {"documents": raw["documents"]}
    if failure == "extra-top-field":
        payload["reviewed"] = True
    elif failure == "extra-document-field":
        payload["documents"][0]["reviewed"] = True
    elif failure == "original":
        case["archive"].write_bytes(case["archive"].read_bytes() + b"changed")
    elif failure == "missing-original":
        case["archive"].unlink()
    docs = tmp_path.resolve() / "documents-only.json"
    _write(docs, payload)
    validation = {**case["validation"], "period_input": docs}
    if failure == "partial":
        validation.pop("period_source_dir")
    directory = tmp_path.resolve() / "documents-validated"
    directory.mkdir()
    destination = directory / "member_map_ai_candidates.json"
    destination.write_bytes(b"last-good-output")
    with pytest.raises((ValueError, OSError)):
        _validate(case, destination, **validation)
    assert destination.read_bytes() == b"last-good-output"


def test_append_only_cli_passes_explicit_mode_without_input_or_worker(append_case, monkeypatch):
    case = append_case
    seen = []
    def record(input_path, source_dir, output, **kwargs):
        seen.append((input_path, kwargs))
        return {"published": False}
    monkeypatch.setattr(case["exporter"], "export_candidates", record)
    arguments = ["export", "--append-only", "--source-dir", str(case["output"].parent),
                 "--output", str(case["output"]), "--append-public-judgments", str(case["previous"])]
    for flag, key in [("--judgment-input", "judgment_input"), ("--judgment-reviews", "judgment_reviews"),
        ("--judgment-as-of", "judgment_as_of"), ("--period-source-dir", "period_source_dir"),
        ("--issuer-registry-path", "issuer_registry_path")]:
        arguments.extend([flag, str(case["options"][key])])
    monkeypatch.setattr(case["exporter"].sys, "argv", arguments)
    assert case["exporter"].main() == 0
    assert seen[0][0] is None and seen[0][1]["append_only"] is True
    assert seen[0][1]["worker_state"] is False
    assert seen[0][1]["append_public_judgments"] == case["previous"]

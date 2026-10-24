"""Cold-fetch canonical hashing parity; no network or member data."""
import hashlib
import importlib
import json
from pathlib import Path
import random
import sys
import types

import pytest

PACKAGE = "map_revision_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "vercel-api/api/portfolio_core")]
sys.modules[PACKAGE] = package
fetch = importlib.import_module(PACKAGE + ".portfolio_public_fetch")


def baseline(value):
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=True,
                              separators=(",", ":"), allow_nan=False)
    for chunk in encoder.iterencode(value):
        digest.update(chunk.encode("utf-8"))
    return digest.hexdigest()


@pytest.mark.parametrize("value", [
    {}, {"rows": []}, {"b": {}, "a": [[], {}]},
    {"한글": "emoji 🎈\n\t\"\\", "surrogate": "\ud800"},
    {"rows": [{"null": None, "bool": True, "negative_zero": -0.0,
               "big": 10**40, "small": 1e-7, "fraction": 1.23456789012345}]},
    {"dict": {"b": {"z": [1, False], "a": 2}, "a": {"c": 3}}},
    {1: "one", 2: "two"}, {"nested": {1: "one"}},
])
def test_exact_previous_revision(value):
    assert fetch._document_revision(value) == baseline(value)


def test_generated_nested_documents_and_shared_values():
    rng = random.Random(20261024)
    def node(depth):
        if depth == 0:
            return rng.choice([None, True, False, -0.0, 1e20, "자료", "", rng.random()])
        if rng.randrange(2):
            return {str(i): node(depth - 1) for i in range(rng.randrange(5))}
        return [node(depth - 1) for _ in range(rng.randrange(5))]
    for _ in range(60):
        shared = node(4)
        document = {"rows": [shared, shared], "meta": node(2)}
        assert fetch._document_revision(document) == baseline(document)


@pytest.mark.parametrize("value", [
    {"rows": [{"value": float("nan")}]},
    {"rows": [{"value": float("inf")}]},
    {"rows": [{"value": float("-inf")}]},
    {"rows": [{"value": object()}]},
    {"mixed": {"a": 1, 2: 3}},
])
def test_rejects_same_invalid_values(value):
    with pytest.raises((TypeError, ValueError)):
        baseline(value)
    with pytest.raises((TypeError, ValueError)):
        fetch._document_revision(value)


def test_cycle_is_rejected_without_infinite_recursion():
    value = {"rows": []}
    value["rows"].append(value)
    with pytest.raises(ValueError):
        fetch._document_revision(value)


def test_encoder_does_not_materialize_whole_artifact(monkeypatch):
    rows = [{"ticker": str(i), "facts": [i, i * 2]} for i in range(200)]
    value = {"stocks": rows, "meta": {"count": len(rows)}}
    original = json.JSONEncoder.encode
    calls = []
    def encode(self, item):
        assert item is not value and item is not rows
        calls.append(item)
        return original(self, item)
    monkeypatch.setattr(json.JSONEncoder, "encode", encode)
    assert fetch._document_revision(value) == baseline(value)
    assert all(any(item is row for item in calls) for row in rows)


@pytest.mark.parametrize("rows", [[{}, None], {"valid": {}, "invalid": []}, {1: {}}])
def test_projector_still_validates_every_container_row_without_iteration(rows):
    sources = importlib.import_module(PACKAGE + ".portfolio_public_sources")
    with pytest.raises(sources.PublicSourceError, match="public source shape rejected"):
        sources.project_public_sources({"universe_search.json": {"stocks": rows}})

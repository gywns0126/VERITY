"""Legacy builder callers must consume verified Mini facts without cloud generation."""
import copy
import json

import pytest

from api.builders import macro_synthesis_builder as builder
from api.intelligence import macro_synthesis as reader


def bundle():
    return {"contract": "macro-facts-v1", "producer": "mac-mini-codex",
            "source_verification": "2/2", "generated_at": "2026-10-25T00:00:00+00:00",
            "verified_at": "2026-10-25T00:01:00+00:00", "_cache": "hit",
            "sources": {key: {"content": text, "source_as_of": "2026-10-23"}
                        for key, text in (("codex_global", "Global official fact"),
                                          ("codex_kr", "Korean official fact"))}}


def test_verified_mini_cache_materializes_without_reclocking(tmp_path, monkeypatch):
    value = bundle()
    value["_cache"] = "miss"
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps(value))
    target = tmp_path / "macro.json"
    monkeypatch.setattr(reader, "OUT_PATH", str(target))
    monkeypatch.setattr(reader, "CACHE_PATH", str(cache))
    monkeypatch.setattr(builder, "OUT_PATH", str(target))
    monkeypatch.setattr(builder.sys, "argv", ["builder", "--force"])
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-be-used")
    assert builder.main() == 0
    expected = dict(value, _cache="hit", consumer_mode="cache_only")
    assert json.loads(target.read_text()) == expected


@pytest.mark.parametrize("case", ["pending", "partial", "unverified", "legacy"])
def test_incomplete_or_retired_contract_cannot_overwrite_last_good(tmp_path, monkeypatch, case):
    value = bundle()
    if case == "pending":
        value = {"status": "pending_mini_producer", "sources": {}}
    elif case == "partial":
        value["sources"].pop("codex_kr")
    elif case == "unverified":
        value["source_verification"] = "1/2"
    else:
        value["sources"] = {"perplexity": {"content": "old global"},
                             "gemini": {"content": "old domestic"}}
    original = copy.deepcopy(bundle())
    target = tmp_path / "macro.json"
    target.write_text(json.dumps(original))
    before = target.read_bytes()
    monkeypatch.setattr(builder, "synthesize_macro", lambda force: value)
    monkeypatch.setattr(builder, "OUT_PATH", str(target))
    monkeypatch.setattr(builder.sys, "argv", ["builder"])
    assert builder.main() == 1
    assert target.read_bytes() == before

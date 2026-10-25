"""Read the Mini-produced, source-verified macro fact bundle.

The retired cloud Gemini/Perplexity producer cannot be restarted by force=True
or by restoring a key. Fact collection is owned by mini_document_readers.py;
this consumer preserves the original source and generation clocks.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from api.config import DATA_DIR

OUT_PATH = os.path.join(DATA_DIR, "macro_synthesis.json")
CACHE_PATH = os.path.join(DATA_DIR, "macro_synthesis_cache.json")


def synthesize_macro(force: bool = False) -> Dict[str, Any]:
    """Compatibility reader only: force never makes a provider request."""
    for path in (OUT_PATH, CACHE_PATH):
        try:
            if os.path.islink(path) or os.path.getsize(path) > 1_048_576:
                continue
            with open(path, encoding="utf-8") as handle:
                value = json.load(handle)
            if (isinstance(value, dict) and value.get("producer") == "mac-mini-codex"
                    and value.get("contract") == "macro-facts-v1"
                    and value.get("source_verification") == "2/2"):
                return dict(value, _cache="hit", consumer_mode="cache_only")
        except (OSError, ValueError, TypeError):
            continue
    return {"contract": "macro-facts-v1", "producer": "mac-mini-codex",
            "status": "pending_mini_producer", "sources": {}, "_cache": "miss",
            "google_calls": 0, "error": "Cloud generation retired; awaiting a verified Mini result"}

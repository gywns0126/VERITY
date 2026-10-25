"""Materialize the verified Mini macro cache for legacy builder callers.

산출 = data/macro_synthesis.json (gitignore, private bucket 만 — 오퍼레이터 전용).
시나리오·전망·추천 생성은 하지 않는다.
"""
from __future__ import annotations

import json
import logging
import sys

from api.intelligence.macro_synthesis import OUT_PATH, synthesize_macro

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    force = "--force" in sys.argv
    r = synthesize_macro(force=force)
    sources = r.get("sources") or {}
    expected = ("codex_global", "codex_kr")
    available = sum(
        isinstance(source, dict) and isinstance(source.get("content"), str)
        and bool(source["content"].strip())
        for source in (sources.get(key) for key in expected)
    ) if isinstance(sources, dict) else 0
    if (r.get("producer") != "mac-mini-codex" or r.get("contract") != "macro-facts-v1"
            or r.get("source_verification") != "2/2" or available != 2
            or not isinstance(sources, dict) or set(sources) != set(expected)):
        logger.error("[macro_facts] pending Mini cache · sources=%s/2 · status=%s",
                     available, r.get("status", "invalid_contract"))
        return 1
    try:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, separators=(",", ":"))
    except OSError as e:
        logger.error("[macro_synth] 저장 실패: %s", e)
        return 1
    logger.info(
        "[macro_facts] cache-only · cache=%s · sources=2/2 · generated_at=%s",
        r.get("_cache"), r.get("generated_at"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

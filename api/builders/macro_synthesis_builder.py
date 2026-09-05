"""macro_synthesis_builder — 출처가 있는 국내외 거시 사실 산출 (평일 장전 cron).

산출 = data/macro_synthesis.json (gitignore, private bucket 만 — 오퍼레이터 전용).
시나리오·전망·추천 생성은 하지 않는다.
"""
from __future__ import annotations

import json
import logging
import sys

from api.config import now_kst
from api.intelligence.macro_synthesis import OUT_PATH, synthesize_macro

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    force = "--force" in sys.argv
    r = synthesize_macro(force=force)
    sources = r.get("sources") or {}
    px = sources.get("perplexity") or {}
    gm = sources.get("gemini") or {}
    if not px.get("content") and not gm.get("content"):
        logger.error("[macro_facts] FAIL — 국내외 사실 모두 없음: px=%s gm=%s", px.get("error"), gm.get("error"))
        return 1
    try:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, separators=(",", ":"))
    except OSError as e:
        logger.error("[macro_synth] 저장 실패: %s", e)
        return 1
    logger.info(
        "[macro_facts] ok · cache=%s · sources=%s/2 · %s",
        r.get("_cache"), int(bool(px.get("content"))) + int(bool(gm.get("content"))), now_kst().strftime("%Y-%m-%d %H:%M"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

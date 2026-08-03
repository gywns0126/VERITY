"""macro_synthesis_builder — 거시 3종 LLM 시나리오 산출 (평일 장전 cron).

산출 = data/macro_synthesis.json (gitignore, private bucket 만 — 오퍼레이터 전용).
LLM 호출은 macro_synthesis.yml 한 곳만 (비용 예측: 1세트/일 ≈ $0.08).
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
    cl = (r.get("sources") or {}).get("claude") or {}
    if not cl.get("content"):
        logger.error("[macro_synth] FAIL — claude 종합 없음: %s", cl.get("error"))
        return 1
    try:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, separators=(",", ":"))
    except OSError as e:
        logger.error("[macro_synth] 저장 실패: %s", e)
        return 1
    logger.info(
        "[macro_synth] ok · cache=%s · out_tokens=%s · %s",
        r.get("_cache"), cl.get("output_tokens"), now_kst().strftime("%Y-%m-%d %H:%M"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

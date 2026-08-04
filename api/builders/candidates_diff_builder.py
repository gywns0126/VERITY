"""candidates_diff_builder — 후보 유니버스 편입/이탈 diff (태스크 #14-①, 2026-08-04).

universe_scan 이 만든 data/universe_candidates.json(25종목)을 직전 스냅샷과 비교해
신규 편입 / 이탈 종목을 산출한다. 오퍼레이터 피드 T2(후보 연동) 소스.

🚨 오퍼레이터 전용: 후보 목록 = 깔때기 산출물(크라운주얼) → 공개 blob 발행 금지.
   gitignore + private bucket(_operator/) + authed /api/admin?type=candidates_diff 만.
LLM 0 · 외부 호출 0 (순수 집합 연산).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from api.config import DATA_DIR, now_kst

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CURRENT_PATH = os.path.join(DATA_DIR, "universe_candidates.json")
PREV_PATH = os.path.join(DATA_DIR, ".candidates_prev.json")
OUT_PATH = os.path.join(DATA_DIR, "candidates_diff.json")
KEEP_FIELDS = ("ticker", "name", "market", "currency", "price", "trading_value")


def _load(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _index(doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for c in doc.get("candidates") or []:
        if isinstance(c, dict) and c.get("ticker"):
            out[str(c["ticker"])] = {k: c.get(k) for k in KEEP_FIELDS if c.get(k) is not None}
    return out


def main() -> int:
    cur_doc = _load(CURRENT_PATH)
    cur = _index(cur_doc)
    if not cur:
        logger.error("[cand_diff] FAIL — universe_candidates 비어있음(스캔 실패 의심). diff 생성 안 함.")
        return 1

    prev_doc = _load(PREV_PATH)
    prev = _index(prev_doc)

    if not prev:
        # 최초 실행 = 비교 대상 없음. 스냅샷만 남기고 빈 diff (전원 '편입' 오탐 방지).
        added: List[Dict[str, Any]] = []
        removed: List[Dict[str, Any]] = []
        note = "최초 실행 — 기준 스냅샷 저장(비교 없음)"
    else:
        added = [v for k, v in cur.items() if k not in prev]
        removed = [v for k, v in prev.items() if k not in cur]
        note = ""

    out = {
        "generated_at": now_kst().isoformat(timespec="seconds"),
        "prev_at": prev_doc.get("collected_at"),
        "curr_at": cur_doc.get("collected_at"),
        "added": added,
        "removed": removed,
        "kept_count": len([k for k in cur if k in prev]),
        "total": len(cur),
        "note": note,
    }
    try:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        with open(PREV_PATH, "w", encoding="utf-8") as f:
            json.dump(cur_doc, f, ensure_ascii=False, separators=(",", ":"))
    except OSError as e:
        logger.error("[cand_diff] 저장 실패: %s", e)
        return 1

    logger.info(
        "[cand_diff] ok · 편입 %d · 이탈 %d · 유지 %d / %d%s",
        len(added), len(removed), out["kept_count"], out["total"],
        f" · {note}" if note else "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

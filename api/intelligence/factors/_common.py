"""Shared helpers for factor modules.

verity_brain.py 와 모든 factors/*.py 가 import.
원본 위치: api/intelligence/verity_brain.py:40-589 (분해 전).
"""
from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Dict, Optional

from api.config import DATA_DIR

logger = logging.getLogger(__name__)

_CONSTITUTION_PATH = os.path.join(DATA_DIR, "verity_constitution.json")
_constitution_cache: Optional[Dict[str, Any]] = None


def _load_constitution() -> Dict[str, Any]:
    global _constitution_cache
    if _constitution_cache is not None:
        return _constitution_cache
    try:
        with open(_CONSTITUTION_PATH, "r", encoding="utf-8") as f:
            _constitution_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _constitution_cache = {}
    return _constitution_cache


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    """None/NaN/Infinity/비숫자 문자열을 안전하게 default로 반환."""
    if v is None:
        return default
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except (TypeError, ValueError):
        return default


# ─── IC/ICIR weight adjustments ──────────────────────────────
# factors.fact._compute_fact_score 와 verity_brain.analyze_all 양쪽 사용.
# 사이클당 1회 캐시 (process-wide singleton).

_ic_adj_cache: Optional[Dict[str, Any]] = None


def _load_ic_adjustments() -> Dict[str, Any]:
    """IC/ICIR 기반 가중치 multiplier를 로드 (사이클당 1회 캐시)."""
    global _ic_adj_cache
    if _ic_adj_cache is not None:
        return _ic_adj_cache
    try:
        from api.quant.alpha.factor_decay import compute_ic_weight_adjustments
        _ic_adj_cache = compute_ic_weight_adjustments()
    except Exception as e:
        logger.debug("IC weight adjustments unavailable: %s", e)
        _ic_adj_cache = {"status": "error", "adjustments": {}, "log": []}
    return _ic_adj_cache


def reset_ic_cache():
    """새 사이클 시작 시 캐시 초기화."""
    global _ic_adj_cache
    _ic_adj_cache = None

"""
portfolio.json 섹션 upsert + 스키마 검증
bonds / etfs 섹션 전용 스키마 및 sanitize 로직 포함.
"""

import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from api.config import PORTFOLIO_PATH

logger = logging.getLogger(__name__)

_PATH = Path(PORTFOLIO_PATH)

# ──────────────────────────────────────────────────────
# 섹션별 기본 스키마 (필수 키 + 기본값)
# verity_brain.py / Framer 컴포넌트가 기대하는 최소 구조 보장
# ──────────────────────────────────────────────────────
SECTION_SCHEMAS: Dict[str, dict] = {
    "bonds": {
        "yield_curves": {
            "kr": {
                "curve":            [],
                "curve_shape":      "unknown",
                "spread_3y_10y":    None,
                "corp_spreads":     {"date": "", "grades": {}},
                "inversion_alerts": [],
                "has_alert":        False,
                "updated_at":       "",
            },
            "us": {
                "curve":            [],
                "curve_shape":      "unknown",
                "spread_2y_10y":    None,
                "spread_3m_10y":    None,
                "credit_spreads":   {
                    "us_ig_oas":  None,
                    "us_hy_oas":  None,
                    "us_ig_risk": None,
                    "us_hy_risk": None,
                },
                "inversion_alerts": [],
                "has_alert":        False,
                "updated_at":       "",
            },
        },
        "credit_spreads": {
            "us_ig_oas":  None,
            "us_hy_oas":  None,
            "us_ig_risk": None,
            "us_hy_risk": None,
        },
        "kr_corp_spreads":  {"date": "", "grades": {}},
        "inversion_alerts": [],
        "has_alert":        False,
        "bond_regime": {
            "rate_environment":  "unknown",
            "curve_shape":       "unknown",
            "credit_cycle":      "neutral",
            "recession_signal":  False,
            "macro_override":    False,
        },
        "updated_at": "",
    },
    "etfs": {
        "kr_top":        [],
        "us_top":        [],
        "overall_top20": [],
        "us_bond":       [],
        "screening_meta": {
            "total_screened":  0,
            "kr_count":        0,
            "us_count":        0,
            "bond_etf_count":  0,
            "factor_weights":  {
                "momentum":  0.35,
                "value":     0.30,
                "quality":   0.25,
                "liquidity": 0.10,
            },
        },
        "updated_at": "",
    },
}


def _sanitize(obj: Any) -> Any:
    """dict/list 재귀 순회 — NaN, Inf → None 치환."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _deep_merge(base: dict, override: dict) -> dict:
    """base 스키마에 override 데이터를 재귀 병합.
    override에 없는 키는 base 기본값 유지 → Framer KeyError 방지."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _validate_section(section: str, data: dict) -> dict:
    """섹션 데이터를 스키마와 병합하여 필수 키 보장."""
    schema = SECTION_SCHEMAS.get(section)
    if not schema:
        return data
    return _deep_merge(schema, data)


def update_section(section: str, data: dict, path: Path = _PATH) -> None:
    """
    portfolio.json의 특정 섹션을 upsert.
    - NaN/Inf sanitize
    - 스키마 병합으로 필수 키 보장
    - updated_at 자동 주입
    - 원자적 파일 쓰기 (tmp → rename)
    """
    clean = _sanitize(data)

    if "updated_at" not in clean or not clean["updated_at"]:
        clean["updated_at"] = datetime.now().isoformat()

    validated = _validate_section(section, clean)

    portfolio = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                portfolio = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"[writer] portfolio.json 파싱 실패: {e}")
            portfolio = {}

    portfolio[section] = validated
    portfolio["_last_updated"] = datetime.now().isoformat()

    tmp_path = path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(portfolio, f, ensure_ascii=False, indent=2, default=str)
        tmp_path.replace(path)
        logger.info(f"[writer] portfolio.json [{section}] 업데이트 완료")
    except Exception as e:
        logger.error(f"[writer] 쓰기 실패: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def read_section(section: str, path: Path = _PATH) -> dict:
    """portfolio.json에서 특정 섹션만 읽기 + 스키마 보장."""
    if not path.exists():
        return SECTION_SCHEMAS.get(section, {})
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        section_data = data.get(section, {})
        return _validate_section(section, section_data)
    except Exception as e:
        logger.error(f"[writer] read_section({section}) 실패: {e}")
        return SECTION_SCHEMAS.get(section, {})

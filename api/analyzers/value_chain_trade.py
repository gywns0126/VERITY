"""
밸류체인 맵 + trade_analysis(거래대금 상위 파이프라인 산출물) 조인.
- 동일 티커가 체인 노드에 속하고 trade_analysis.json stocks에 있으면 가산점·메타 부여.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from api.config import TRADE_ANALYSIS_PATH, VALUE_CHAIN_MAP_PATH

_map_cache: Optional[Dict[str, Any]] = None
_trade_tickers_cache: Optional[Set[str]] = None


def _grade_for_multi_score(multi: int) -> str:
    if multi >= 75:
        return "강력 매수"
    if multi >= 60:
        return "매수"
    if multi >= 45:
        return "관망"
    if multi >= 30:
        return "주의"
    return "회피"


def load_value_chain_map() -> Dict[str, Any]:
    global _map_cache
    if _map_cache is not None:
        return _map_cache
    if not os.path.isfile(VALUE_CHAIN_MAP_PATH):
        _map_cache = {"schema_version": 0, "sectors": {}}
        return _map_cache
    try:
        with open(VALUE_CHAIN_MAP_PATH, "r", encoding="utf-8") as f:
            _map_cache = json.load(f)
    except (json.JSONDecodeError, OSError):
        _map_cache = {"schema_version": 0, "sectors": {}}
    return _map_cache


def load_trade_analysis_tickers() -> Set[str]:
    """trade_analysis.json에 포함된 종목코드(6자리) 집합."""
    global _trade_tickers_cache
    if _trade_tickers_cache is not None:
        return _trade_tickers_cache
    out: Set[str] = set()
    if not os.path.isfile(TRADE_ANALYSIS_PATH):
        _trade_tickers_cache = out
        return out
    try:
        with open(TRADE_ANALYSIS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        _trade_tickers_cache = out
        return out
    for row in data.get("stocks", []):
        t = row.get("ticker")
        if t:
            out.add(str(t).zfill(6))
    _trade_tickers_cache = out
    return out


def resolve_ticker_roles(ticker: str, vc: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """티커가 속한 (섹터, 노드, role) 목록."""
    t6 = str(ticker).zfill(6)
    vc = vc or load_value_chain_map()
    found: List[Dict[str, Any]] = []
    for sid, sec in (vc.get("sectors") or {}).items():
        for node in sec.get("nodes") or []:
            tickers = [str(x).zfill(6) for x in (node.get("tickers") or [])]
            if t6 in tickers:
                found.append(
                    {
                        "sector_id": sid,
                        "sector_label_ko": sec.get("label_ko", sid),
                        "node_id": node.get("id", ""),
                        "node_label_ko": node.get("label_ko", ""),
                        "role": node.get("role", "other"),
                    }
                )
    return found


def _bonus_for_role(role: str) -> int:
    if role == "lead":
        return 4
    if role == "supplier":
        return 3
    return 2


def compute_chain_trade_overlay(ticker: str) -> Dict[str, Any]:
    """
    trade 스캔 유니버스에 포함된 밸류체인 종목에만 보너스.
    """
    t6 = str(ticker).zfill(6)
    trade_set = load_trade_analysis_tickers()
    roles = resolve_ticker_roles(t6)
    in_trade = t6 in trade_set
    if not roles:
        return {
            "active": False,
            "in_trade_scan": in_trade,
            "roles": [],
            "score_bonus": 0,
        }
    best_bonus = 0
    if in_trade:
        for r in roles:
            best_bonus = max(best_bonus, _bonus_for_role(r.get("role", "other")))
    return {
        "active": bool(in_trade and best_bonus > 0),
        "in_trade_scan": in_trade,
        "roles": roles,
        "score_bonus": best_bonus if in_trade else 0,
        "sector_ids": list({r["sector_id"] for r in roles}),
    }


def attach_value_chain_trade_overlay(stock: Dict[str, Any]) -> None:
    """stock에 value_chain 블록 부여 및 multi_factor 점수 소폭 가산 (상한 100)."""
    ticker = stock.get("ticker", "")
    overlay = compute_chain_trade_overlay(ticker)
    stock["value_chain"] = overlay
    bonus = int(overlay.get("score_bonus") or 0)
    if bonus <= 0:
        return
    mf = stock.get("multi_factor")
    if not isinstance(mf, dict):
        return
    base = int(mf.get("multi_score") or 0)
    new_score = min(100, base + bonus)
    mf["multi_score"] = new_score
    mf["grade"] = _grade_for_multi_score(new_score)
    sig = mf.get("all_signals")
    if not isinstance(sig, list):
        sig = []
    label = "리드" if any(r.get("role") == "lead" for r in overlay.get("roles", [])) else "공급"
    sig.append(f"밸류체인({label})×거래대금상위 +{bonus}")
    mf["all_signals"] = sig
    mf["value_chain_bonus_applied"] = bonus

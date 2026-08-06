# -*- coding: utf-8 -*-
"""보유 통화 정규화 마이그레이션 (2026-08-06).

**무엇을 고치는가**: 2026-08-05 에 `execute_buy` 에 통화 정규화(`_fx_norm`)를 넣었는데
**신규 매수에만** 적용됐다. 그 이전에 편입된 보유는 `buy_price`/`current_price` 는 KRW 인데
`exit_targets[*].price` 는 원통화(USD)로 남아 있다.

**증상**: `check_partial_exit` 의 스케일 가드(비율>10 → skip, fail-closed)가 작동해
**미장 보유는 부분익절 평가가 통째로 건너뛰어진다.** 실측 3건(EXE·GOOGL·NEM), 비율 1,312~1,340.
가드가 없었다면 `131,397 >= 99` 로 매 run 익절이 무조건 발동했을 것이다(8/5 실측 EQT 30회).

`measurement_audit` 의 `price_scale` 검사가 이 3건을 **매일** 신고하고 있었으나 로그에만
찍혀 아무도 읽지 않았다(8/6 발견).

**환율을 추정하지 않는다**: `buy_price / buy_price_original` 이 진입 시점 환율의 **정확한**
값이다(두 필드가 같은 매수의 KRW·원통화 쌍). 실측 — EXE 1434.68 · GOOGL 1442.07 · NEM 1428.58.
값이 타당 범위를 벗어나면 변환하지 않고 보고만 한다(추측 금지).

🚨 **멱등**: `entry_currency` 존재 = 처리 완료 표식. 두 번 돌려도 이중 변환되지 않는다.
🚨 **되돌릴 수 있게**: 변환 전/후를 `data/metadata/currency_migration_log.jsonl` 에 남긴다.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

LOG_PATH = os.path.join(DATA_DIR, "metadata", "currency_migration_log.jsonl")

# engine._fx_norm 과 **같은 집합**이어야 한다 (진입 시 정규화와 마이그레이션이 어긋나면 안 된다).
_PRICE_KEYS = {"price", "stop_price", "target_price", "low", "high",
               "min", "max", "entry_low", "entry_high", "risk_per_share"}

# 타당 환율 대역 — 벗어나면 변환하지 않고 보고. KRW/USD 는 역사적으로 이 안에 있었다.
_FX_MIN, _FX_MAX = 500.0, 3000.0
# 동일 통화 판정 허용오차 (KR 보유는 buy_price/buy_price_original ≈ 1.0)
_SAME_CCY_TOL = 0.01


def _is_kr(ticker: Any) -> bool:
    return bool(re.fullmatch(r"\d{6}", str(ticker or "")))


def _implied_fx(h: Dict[str, Any]) -> Optional[float]:
    """진입 시점 환율 = buy_price / buy_price_original. 산출 불가면 None."""
    bp, bo = h.get("buy_price"), h.get("buy_price_original")
    if not isinstance(bp, (int, float)) or not isinstance(bo, (int, float)):
        return None
    if bo <= 0:
        return None
    return bp / bo


def _convert(obj: Any, fx: float) -> Any:
    """가격 성격 키만 fx 배. dict 재귀. (engine._fx_norm 과 동일 규칙)"""
    if not isinstance(obj, dict):
        return obj
    out: Dict[str, Any] = {}
    for k, v in obj.items():
        if isinstance(v, dict):
            out[k] = _convert(v, fx)
        elif k in _PRICE_KEYS and isinstance(v, (int, float)):
            out[k] = round(v * fx, 2)
        else:
            out[k] = v
    return out


def migrate_holdings(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """보유 리스트를 제자리 정규화. 반환 = 처리 리포트.

    처리 규칙:
      · `entry_currency` 이미 있음      → skip (멱등)
      · 6자리 티커(KR)                  → 표식만 (`KRW`), 가격 변환 없음
      · 내재 환율 ≈ 1.0                 → 이미 KRW 표기 → 표식만
      · 내재 환율이 타당 대역            → exit_targets·stop_price·risk_per_share 변환 + 표식
      · 그 외(산출 불가·대역 밖)         → **변환하지 않고** unresolved 로 보고
    """
    report: Dict[str, Any] = {
        "as_of": now_kst().isoformat(timespec="seconds"),
        "total": len(holdings), "converted": [], "marked": [], "skipped": [], "unresolved": [],
    }
    for h in holdings:
        tk = str(h.get("ticker") or "")
        if h.get("entry_currency"):
            report["skipped"].append({"ticker": tk, "reason": "이미 처리됨(멱등)"})
            continue
        if _is_kr(tk):
            h["entry_currency"] = "KRW"
            h["entry_fx_rate"] = None
            report["marked"].append({"ticker": tk, "currency": "KRW"})
            continue

        fx = _implied_fx(h)
        if fx is None:
            report["unresolved"].append(
                {"ticker": tk, "reason": "buy_price/buy_price_original 결손 — 환율 산출 불가"})
            continue
        if abs(fx - 1.0) <= _SAME_CCY_TOL:
            h["entry_currency"] = "KRW"
            h["entry_fx_rate"] = None
            report["marked"].append({"ticker": tk, "currency": "KRW", "implied_fx": round(fx, 4)})
            continue
        if not (_FX_MIN <= fx <= _FX_MAX):
            report["unresolved"].append(
                {"ticker": tk, "implied_fx": round(fx, 2),
                 "reason": f"환율이 타당 대역({_FX_MIN:.0f}~{_FX_MAX:.0f}) 밖 — 변환하지 않음(추측 금지)"})
            continue

        before = {"exit_targets": h.get("exit_targets"),
                  "stop_price": h.get("stop_price"),
                  "risk_per_share": h.get("risk_per_share"),
                  "exit_history": list(h.get("exit_history") or [])}
        if isinstance(h.get("exit_targets"), dict):
            h["exit_targets"] = _convert(h["exit_targets"], fx)
        for k in ("stop_price", "risk_per_share"):
            if isinstance(h.get(k), (int, float)):
                h[k] = round(h[k] * fx, 2)

        # 🚨 오염 시기의 skip 기록 정리.
        # 통화가 섞여 있던 동안 `current_price(KRW) >= target(USD)` 가 **항상 참**이라
        # 타깃이 엉뚱한 시점에 발동했고, 그때 수량이 안 나눠져 skipped_too_small 로 남았다.
        # 즉 그 기록은 **무효한 비교에서 나온 판단**이라 폐기한다.
        # ⚠️ `executed` 는 절대 건드리지 않는다 — 실제로 자금이 움직인 체결이고,
        #    지우면 같은 물량을 두 번 파는 길이 열린다.
        _eh = h.get("exit_history") or []
        purged = [x for x in _eh if x.get("status") == "skipped_too_small"]
        if purged:
            h["exit_history"] = [x for x in _eh if x.get("status") != "skipped_too_small"]

        h["entry_currency"] = "USD"
        h["entry_fx_rate"] = round(fx, 2)
        report["converted"].append({
            "ticker": tk, "fx": round(fx, 2), "before": before,
            "purged_skip_records": len(purged),
            "after": {"exit_targets": h.get("exit_targets"), "stop_price": h.get("stop_price"),
                      "risk_per_share": h.get("risk_per_share"),
                      "exit_history": h.get("exit_history")},
        })
    return report


def run(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """portfolio 의 VAMS 보유를 정규화하고 로그를 남긴다. 파이프라인에서 호출."""
    holdings = ((portfolio.get("vams") or {}).get("holdings")) or []
    rep = migrate_holdings(holdings)
    rep["summary"] = (f"변환 {len(rep['converted'])} · 표식 {len(rep['marked'])} · "
                      f"skip {len(rep['skipped'])} · 미해결 {len(rep['unresolved'])}")
    if rep["converted"] or rep["unresolved"]:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rep, ensure_ascii=False) + "\n")
    return rep

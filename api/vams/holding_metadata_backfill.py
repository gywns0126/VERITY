"""holding_metadata_backfill — 보유 종목의 가드 입력(sector·quant_factors) 백필. 2026-08-11.

## 왜

`check_position_size` 의 포트폴리오 가드 3종이 보유에서 읽는 필드:
  · 섹터 35% 상한        ← `h["sector"]`
  · 베타 1.5 상한        ← `h["beta"]`
  · 팩터쏠림 차단        ← `h["multi_factor"]["quant_factors"]`

**셋 다 `execute_buy` 가 저장하지 않았다** (2026-08-11 실측 0/11).
결과: 전 보유가 섹터 "Unknown" 으로 뭉쳐 후보 섹터 노출이 항상 0 → 섹터 상한 무발동.
베타는 전부 기본값 1.0 → 상한 1.5 사실상 무발동. 팩터 쏠림은 전부 0% → 무발동.
**가드가 존재하는데 입력이 없어 조용히 한 번도 안 걸린 것** — FX 헤지(해제조건 없는 규칙)와
같은 병이다. 신규 매수는 engine 패치로 저장되고, 이 모듈은 **기존 보유**를 메운다.

## 소스와 한계

`data/recommendations.json` (보유는 전부 추천을 거쳐 매수됨 — 2026-08-11 실측 11/11 매칭):
  · sector          — 시간 불변에 가까워 소급 안전
  · quant_factors   — 🚨 **현재 스코어이지 매수 시점 스코어가 아니다.** 가드는 현재
                      포트폴리오 쏠림을 보므로 현재값이 오히려 정합. 출처·시점을 행에 남긴다.
  · beta            — full 분석 backtest 가 동일 시장지수(KR=KOSPI, US=S&P 500) 대비
                      일간수익률 beta 를 산출한다. 채점에는 연결하지 않고 VAMS 가드에만 쓴다.

멱등: 필드가 이미 있으면 건드리지 않는다. 소스에 없는 종목은 그대로 두고 신고한다
(없는 값을 지어내지 않는다).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from api.config import DATA_DIR, now_kst

_REC_PATH = os.path.join(DATA_DIR, "recommendations.json")
_FACTOR_KEYS = ("momentum", "quality", "volatility", "mean_reversion")


def _rec_index() -> Dict[str, Dict[str, Any]]:
    try:
        with open(_REC_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    recs = d if isinstance(d, list) else (d.get("recommendations") or [])
    return {str(r.get("ticker")): r for r in recs if isinstance(r, dict) and r.get("ticker")}


def run(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """보유의 sector / beta / multi_factor.quant_factors 결측을 recommendations 로 채운다."""
    holdings = (portfolio.get("vams") or {}).get("holdings") or []
    idx = _rec_index()
    filled = 0
    missing_source = []
    for h in holdings:
        need_sector = not h.get("sector")
        qf = (h.get("multi_factor") or {}).get("quant_factors") or {}
        need_qf = not qf
        need_beta = h.get("beta") is None
        if not (need_sector or need_qf or need_beta):
            continue
        src = idx.get(str(h.get("ticker")))
        if not src:
            missing_source.append(h.get("ticker"))
            continue
        changed = False
        if need_sector and src.get("sector"):
            h["sector"] = src["sector"]
            changed = True
        if need_qf:
            sqf = (src.get("multi_factor") or {}).get("quant_factors") or {}
            slim = {k: v for k, v in sqf.items()
                    if k in _FACTOR_KEYS and isinstance(v, (int, float))}
            if slim:
                h.setdefault("multi_factor", {})["quant_factors"] = slim
                changed = True
        if need_beta:
            beta = src.get("beta")
            if beta is None:
                beta = (src.get("backtest") or {}).get("beta")
            if isinstance(beta, (int, float)):
                h["beta"] = float(beta)
                changed = True
        if changed:
            # 출처·시점 명시 — 소급값(quant_factors 는 현재 스코어)임을 숨기지 않는다
            h["meta_backfill"] = {"source": "recommendations.json",
                                  "at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")}
            filled += 1
    return {
        "filled": filled,
        "missing_source": missing_source,
        "summary": (f"{filled}건 백필 (소스 부재 {len(missing_source)}건"
                    f"{': ' + ','.join(map(str, missing_source)) if missing_source else ''})"),
    }

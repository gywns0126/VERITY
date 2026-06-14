"""
crowding_observations.py — 팩터 crowding(혼잡도) raw 관측 로거 v0.

2026-06-14 신설. 동기 = 2026-06-13 학술 근거 감사 #1 공통 사각: 학술이 가장 세게 경고하는
알파 부패/크라우딩(McLean-Pontiff 2016 출판후 58%, Chordia-Subrahmanyam-Tong 2014,
Calluzzo-Moneta-Topaloglu 2019)을 VERITY 가 in-sample 고정 임계로 미반영 → crowding 의
forward IC decay 예측력을 사후 검증할 raw 관측을 누적.

🚨 관측 ONLY — 점수/결정 wire 0 (RULE 7). **조합식(factor-level crowding score)** =
Perplexity 방법론 자문(comomentum[Lou-Polk] vs short-weighted-by-factor-exposure vs 분기 13F)
확정 후 v1. 본 v0 = *원자료만* (유니버스 종목별 short% + 시장 froth + factor IC 스냅샷) 시점-페어
로깅 → data/observations/crowding_observations.jsonl. 어느 조합식이든 입력이 되는 low-regret 적재.
(FINRA/가격은 archive backfill 가능 — 본 로그는 시점 페어링 편의 + 누적 시작용.)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

OBS_DIR = os.path.join(DATA_DIR, "observations")
CROWDING_PATH = os.path.join(OBS_DIR, "crowding_observations.jsonl")
FACTOR_IC_PATH = os.path.join(DATA_DIR, "factor_ic_history.json")


def _latest_factor_ic() -> Dict[str, Any]:
    """factor_ic_history.json 최신 스냅샷 (팩터별 IC). 결손/형식이상 = {}."""
    try:
        with open(FACTOR_IC_PATH, encoding="utf-8") as f:
            hist = json.load(f)
    except (OSError, ValueError):
        return {}
    if isinstance(hist, list) and hist:
        return hist[-1] if isinstance(hist[-1], dict) else {}
    if isinstance(hist, dict):
        return hist
    return {}


def build_crowding_snapshot(
    per_symbol_short: Optional[Dict[str, float]],
    market_short_pct: Optional[float],
    aaii_metrics: Optional[Dict[str, Any]] = None,
    naaim_metrics: Optional[Dict[str, Any]] = None,
    factor_ic: Optional[Dict[str, Any]] = None,
    path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """crowding raw 관측 1건 조립 + append (관측 only, date dedupe). 조합식/점수 0.

    입력(종목별 short + 시장 short) 결손 시 None (graceful skip). aaii/naaim/factor_ic 는
    보조 — 키 추측 회피 위해 metrics dict 통째 저장.
    """
    target = path or CROWDING_PATH
    if not per_symbol_short and market_short_pct is None:
        return None  # 핵심 입력 결손 = skip

    now = now_kst()
    rec = {
        "observed_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "date": now.strftime("%Y-%m-%d"),
        "market_short_volume_pct": market_short_pct,
        "per_symbol_short_pct": per_symbol_short or {},
        "n_symbols": len(per_symbol_short or {}),
        "aaii_metrics": aaii_metrics,      # froth proxy (raw, 키 추측 회피)
        "naaim_metrics": naaim_metrics,
        "factor_ic_snapshot": factor_ic if factor_ic is not None else _latest_factor_ic(),
        "spec": "crowding_v0_raw_observation",
        "_note": "관측 only. 조합식(factor crowding score)=Perplexity 후 v1. 점수 wire 0.",
    }

    os.makedirs(os.path.dirname(target), exist_ok=True)
    # date dedupe — 같은 날 중복 append 차단
    try:
        with open(target, encoding="utf-8") as f:
            seen = {json.loads(line).get("date") for line in f if line.strip()}
        if rec["date"] in seen:
            return rec
    except OSError:
        pass

    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    logger.info("crowding 관측 append: %s종목 + 시장 short %s", rec["n_symbols"], market_short_pct)
    return rec


def run_crowding_observation() -> Dict[str, Any]:
    """daily/weekly hook — FINRA per-symbol + 시장 short + sentiment + factor IC 조립 로깅. graceful."""
    from api.collectors import us_market_observations as obs

    asof = now_kst()
    universe: List[str] = obs._us_universe()
    per = obs.fetch_finra_short_per_symbol(asof, universe) if universe else None
    mkt = obs.fetch_finra_short(asof)
    aaii = obs.fetch_aaii()
    naaim = obs.fetch_naaim()

    rec = build_crowding_snapshot(
        per_symbol_short=(per or {}).get("per_symbol_short_pct"),
        market_short_pct=(mkt or {}).get("metrics", {}).get("market_short_volume_pct"),
        aaii_metrics=(aaii or {}).get("metrics"),
        naaim_metrics=(naaim or {}).get("metrics"),
    )
    return {
        "logged": rec is not None,
        "n_symbols": (per or {}).get("covered", 0),
        "universe": len(universe),
    }


if __name__ == "__main__":
    import sys

    try:
        r = run_crowding_observation()
        print(f"[crowding] logged={r['logged']} n_symbols={r['n_symbols']}/{r['universe']}")
    except Exception as e:  # noqa: BLE001 — 관측은 부수효과, 파이프라인 fail 금지
        sys.stderr.write(f"[crowding] 실패 (graceful exit 0): {type(e).__name__}: {e}\n")
    sys.exit(0)

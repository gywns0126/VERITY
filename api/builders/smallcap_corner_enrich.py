"""
smallcap_corner_enrich.py — 소형주 코너 quant 팩터 enrichment (Phase 1, Smallcap Corner Trail Spec v0 §10).

2026-06-20 신설. 코너 종목에 momentum/volatility/mean_reversion(가격레이크) + quality(코너 재무) →
multi_factor 합성. 목적 = brain_score 분산 발생(enrichment 전 = 전 종목 ~50 상수, degenerate IC).

기존 팩터 엔진 전부 재사용 (신 산식 0, RULE 10):
  - api/quant/factors/{momentum,volatility,mean_reversion,quality}.py
  - api/analyzers/multi_factor.compute_multi_factor_score (9팩터 동적 가중)
가격 source = 로컬 가격레이크 ~/VERITY_data_lake/kr_prices.duckdb (ohlcv, [[project_local_data_lake_storage]]).
시장-레벨 신호(sentiment/flow/macro)는 코너 부재 → 중립 50 (얕은 데이터 정직, curve-fit 0).

graceful: duckdb/lake 부재(CI 등) 또는 종목 가격 히스토리 부재 시 enriched=False (해당 종목 분산 0 → trail 제외).
로컬 전용 — 레이크는 repo 밖 자산. enriched 종목만 검증 풀 진입, 레이크 백필 따라 커버리지 성장.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import numpy as np

from api.analyzers.multi_factor import compute_multi_factor_score
from api.quant.factors.mean_reversion import compute_mean_reversion_score
from api.quant.factors.momentum import compute_momentum_score
from api.quant.factors.quality import compute_quality_score
from api.quant.factors.volatility import compute_volatility_score

LAKE_PATH = os.path.expanduser("~/VERITY_data_lake/kr_prices.duckdb")

# 모멘텀 lookback 오프셋(거래일) — momentum.enrich_from_yfinance 와 동일 (21/63/126/252).
_OFFSETS = {"price_1m": 21, "price_3m": 63, "price_6m": 126, "price_12m": 252}
_MIN_HISTORY = 60  # 최소 가격 점수 (모멘텀/변동성 유의미 하한). 미만 = enriched=False.


def _load_close_map(tickers: List[str], lake_path: str) -> Dict[str, List[float]]:
    """가격레이크에서 종목별 close 시리즈 일괄 로드 (graceful — lake/duckdb 부재 시 빈 dict)."""
    if not os.path.exists(lake_path):
        return {}
    try:
        import duckdb
    except Exception:  # noqa: BLE001 — duckdb 부재(CI) = enrichment 없이 진행
        return {}
    out: Dict[str, List[float]] = {}
    try:
        con = duckdb.connect(lake_path, read_only=True)
        try:
            # 단일 쿼리로 전 코너 종목 close 조회 (date 정렬).
            rows = con.execute(
                "SELECT ticker, close FROM ohlcv WHERE ticker IN "
                f"({','.join('?' * len(tickers))}) ORDER BY ticker, date",
                tickers,
            ).fetchall()
        finally:
            con.close()
        for tic, close in rows:
            if close is None:
                continue
            out.setdefault(str(tic), []).append(float(close))
    except Exception:  # noqa: BLE001 — 쿼리 실패 = graceful (enrichment 없이 진행)
        return {}
    return out


def _enrich_one(s: Dict[str, Any], closes: List[float]) -> Dict[str, Any]:
    """단일 코너 종목 → quant 팩터 + multi_factor 부착. closes 부족 시 enriched=False."""
    fin = s.get("financials") or {}
    st: Dict[str, Any] = {
        "ticker": s.get("ticker"),
        "name": s.get("name"),
        "price": s.get("close") or (closes[-1] if closes else 0),
        "roa": fin.get("roa"),
        "debt_ratio": fin.get("debt_ratio"),
        "gross_margin": fin.get("gross_margin"),
        "operating_margin": fin.get("gross_margin"),  # 코너 재무 = op_margin 별도 부재 → gross 대용(보수)
    }
    enriched = len(closes) >= _MIN_HISTORY
    if enriched:
        c = np.asarray(closes, dtype=float)
        st["price_history"] = closes
        st["high_52w"] = float(c[-252:].max())
        st["low_52w"] = float(c[-252:].min())
        for key, d in _OFFSETS.items():
            if len(c) > d:
                st[key] = float(c[-d])

    mo = compute_momentum_score(st)
    vo = compute_volatility_score(st)
    mr = compute_mean_reversion_score(st)
    ql = compute_quality_score(st)
    qf = {"momentum": mo, "quality": ql, "volatility": vo, "mean_reversion": mr}
    # 시장-레벨 신호(fundamental/technical/sentiment/flow/macro) 코너 부재 → 중립 50 (정직).
    mf = compute_multi_factor_score(
        fundamental_score=50,
        technical={"technical_score": 50},
        sentiment={"score": 50},
        flow={"flow_score": 50},
        macro_mood={"score": 50},
        quant_factors=qf,
    )
    out = dict(s)
    out["multi_factor"] = mf
    out["quant_factors"] = {
        "momentum_score": mo.get("momentum_score"),
        "quality_score": ql.get("quality_score"),
        "volatility_score": vo.get("volatility_score"),
        "mean_reversion_score": mr.get("mean_reversion_score"),
    }
    out["enriched"] = enriched
    out["price_points"] = len(closes)
    return out


def enrich_quant_factors(
    stocks: List[Dict[str, Any]], lake_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """코너 종목 리스트 → quant 팩터 enrichment.

    각 종목에 multi_factor / quant_factors / enriched(bool) / price_points 부착.
    enriched=True = 가격 히스토리 충분(≥60점) → brain_score 분산 발생. False = 레이크 부재 → trail 제외 권장.
    graceful: lake/duckdb 부재 시 전 종목 enriched=False (분산 없이 반환 — caller 가 skip).
    """
    if not stocks:
        return []
    lake_path = lake_path or LAKE_PATH
    tickers = [str(s.get("ticker")) for s in stocks if s.get("ticker")]
    close_map = _load_close_map(tickers, lake_path)
    return [_enrich_one(s, close_map.get(str(s.get("ticker")), [])) for s in stocks if s.get("ticker")]

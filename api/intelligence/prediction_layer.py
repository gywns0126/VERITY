"""
prediction_layer.py — VERITY Prediction Layer v0 생성기.

2026-06-01 신설. 사전등록 spec (docs/prediction_layer_spec_v0_2026_06_01.md) 정합.
descriptive(핫 섹터/종목) → predictive 전환. 자기 신호(Brain grade + macro_industry_alignment)의
forward 투영 (RULE 6 — LLM 예측 wrap 금지). 매 daily run 당 cross-section 1벌 생성
(IC 표준, factor_ic_history 정합) → prediction_trail.jsonl 로깅. 채점은 별도 cron.

대상 × horizon = (섹터 로테이션 + 종목 forward) × (단 short / 중 mid / 장 long).
모든 산출 = "예측 추적 중 (가설)" — actionable 아님 (N gate 통과 전, spec §4/§5).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.metadata import prediction_trail as PT

_HORIZONS = ("short", "mid", "long")

# Brain grade → forward 방향 (grade 자체가 암묵적 forward 판단)
_GRADE_DIRECTION = {"BUY": "up", "WATCH": "up", "CAUTION": "neutral", "AVOID": "down"}
# grade_confidence label → 수치 (Brier 채점 입력)
_CONF_MAP = {"firm": 0.7, "tentative": 0.45, "weak": 0.35}


def _conf_num(grade_confidence: Any) -> float:
    if isinstance(grade_confidence, (int, float)):
        return max(0.0, min(1.0, float(grade_confidence)))
    return _CONF_MAP.get(str(grade_confidence).lower(), 0.5)


def generate_stock_predictions(
    recommendations: List[Dict[str, Any]], path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """종목 forward — 각 추천의 Brain grade/score 를 horizon 3개로 투영."""
    out: List[Dict[str, Any]] = []
    for rec in recommendations or []:
        vb = rec.get("verity_brain") or {}
        grade = vb.get("grade")
        score = vb.get("brain_score")
        ticker = rec.get("ticker")
        if not ticker or grade is None or score is None:
            continue  # 데이터 결손 = skip (graceful)
        direction = _GRADE_DIRECTION.get(str(grade).upper(), "neutral")
        conf = _conf_num(vb.get("grade_confidence"))
        signals = {
            "brain_score": score,
            "grade": grade,
            "sector": rec.get("sector"),
            "vci": vb.get("vci"),
            "source": "verity_brain.v5",
        }
        for h in _HORIZONS:
            out.append(
                PT.log_prediction(
                    target_type="stock", target=str(ticker), horizon=h,
                    direction=direction, pred_score=float(score), confidence=conf,
                    signals=signals, path=path,
                )
            )
    return out


# 섀도우 funnel 예측 source 태그 (Shadow Funnel Scoring Spec v0). production 과 분리 집계.
_SHADOW_SOURCE = "shadow_funnel.v0"


def generate_shadow_predictions(
    picks: List[Dict[str, Any]], path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """섀도우 funnel e_factor_rank 100-name → forward 예측 (Shadow Funnel Scoring Spec v0).

    picks = [{"ticker","score","entry_price","currency","name"}, ...] (wide_scan persist).
    source="shadow_funnel.v0" 분리 태그 → 프로덕션 IC 와 별도 집계/비교 (§5).
    pred_score = funnel 합성점수 (cross-section rank-IC 입력). entry_price 는 signals 에 동결 (PIT, §3).

    물리 분리: path 미지정 시 PT.SHADOW_PATH(별도 trail) 에 기록 — 프로덕션 scorer 가
    섀도우를 pool 하지 못하게 함 (§1 무오염, prediction_scoring.py 무변경). 채점은 증분 3 섀도우 scorer.
    """
    path = path or PT.SHADOW_PATH
    out: List[Dict[str, Any]] = []
    for p in picks or []:
        ticker = p.get("ticker")
        score = p.get("score")
        if not ticker or score is None:
            continue  # 결손 = skip (graceful)
        direction = "up" if float(score) >= 50.0 else "neutral"
        signals = {
            "funnel_score": score,
            "entry_price": p.get("entry_price"),  # scan 시점 동결 (pykrx backward-adjust drift 회피)
            "currency": p.get("currency"),
            "name": p.get("name"),
            "stage": "e_factor_rank",
            "source": _SHADOW_SOURCE,
        }
        for h in _HORIZONS:
            out.append(
                PT.log_prediction(
                    target_type="stock", target=str(ticker), horizon=h,
                    direction=direction, pred_score=float(score), confidence=0.5,
                    signals=signals, spec_version="shadow.v0", source=_SHADOW_SOURCE,
                    path=path,
                )
            )
    return out


# ML(XGB up_probability) 예측 source 태그. production/shadow_funnel 과 분리 집계.
_ML_SOURCE = "xgb_ml.v0"


def generate_ml_predictions(
    recommendations: List[Dict[str, Any]], path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """XGB up_probability forward 예측 → ML shadow trail (ML Shadow Prediction Spec v0).

    동기: XGB up_probability 가 ai_upside_relax(verity_brain.py)로 brain AVOID 를 override 하나,
    그 ML 예측 자체의 IC/Brier 가 어느 trail 에도 미채점이던 갭. 관측 only — 채점 결과는
    ai_upside_relax 결정에 피드백 0 (RULE 7). N 누적 후 override 정당성 판정 자료로만.

    매핑 (사전등록, 강제값 = 곡선맞추기 surface 0):
      - pred_score = up_probability (0~100 연속 → cross-section rank-IC 입력)
      - direction  = up if up_prob>50 / down if <50 / neutral if ==50 (P(up) 자연 경계)
      - confidence = P(예측 방향 적중) = up_prob/100 (up) / 1-up_prob/100 (down) / 0.5 (neutral)
                     → Brier 가 XGB 확률 캘리브레이션을 측정 (이게 ML 검증의 핵심).

    genuine ensemble 예측만 (method='ensemble_*'). fallback/rule_based/error = ML 모델 아님 → skip.
    물리 분리: path 미지정 시 PT.ML_PATH (프로덕션/섀도우 scorer 무오염, prediction_scoring.py 무변경).
    """
    path = path or PT.ML_PATH
    out: List[Dict[str, Any]] = []
    for rec in recommendations or []:
        pred = rec.get("prediction") or {}
        method = str(pred.get("method", ""))
        up_prob = pred.get("up_probability")
        ticker = rec.get("ticker")
        if not ticker or up_prob is None or not method.startswith("ensemble"):
            continue  # 결손 또는 비-ensemble(fallback/rule_based/error) = skip (graceful)
        up = float(up_prob)
        if up > 50.0:
            direction, conf = "up", up / 100.0
        elif up < 50.0:
            direction, conf = "down", (100.0 - up) / 100.0
        else:
            direction, conf = "neutral", 0.5
        signals = {
            "up_probability": up,
            "method": method,
            "model_accuracy": pred.get("model_accuracy"),
            "confidence_level": pred.get("confidence_level"),
            "prediction_std": pred.get("prediction_std"),
            "conformal_width_pct": pred.get("conformal_width_pct"),
            "train_samples": pred.get("train_samples"),
            "top_features": pred.get("top_features"),
            "source": _ML_SOURCE,
        }
        for h in _HORIZONS:
            out.append(
                PT.log_prediction(
                    target_type="stock", target=str(ticker), horizon=h,
                    direction=direction, pred_score=up, confidence=conf,
                    signals=signals, spec_version="ml.v0", source=_ML_SOURCE,
                    path=path,
                )
            )
    return out


# 관측-only 신호(us_market_observations) forward 예측 source 태그. production/shadow/ml 과 분리 집계.
_OBS_SOURCE = "obs_us_market.v0"

# 관측 신호 → 시장-레벨 forward 예측 매핑 (사전등록, 강제값 = 곡선맞추기 surface 0).
#   각 entry: (metric_key, sign). pred_score = signals[metric_key] * sign (sign 으로 "up=양수" 정렬만).
#   direction = sign(pred_score) (>0 up / <0 down / ==0 neutral). target = 'sp500' (US 신호 → US 시장).
#   ⚠️ contrarian flip 미적용 (자유 선택 = 곡선맞추기). as-published face-value 방향만 로깅 —
#      face-value vs contrarian 의 정오는 N≥252 forward IC 부호가 답함 (이게 검증의 핵심, RULE 7).
# 강제 근거:
#   aaii          : bull_bear_spread (양수 = bullish 우세 → up). 중심 0 자연 경계.
#   naaim         : exposure_mean − 50 (능동운용 노출 50% 중립 기준 → 초과 = bullish).
#   finra_short   : −(market_short_volume_pct − 50) (공매도 비중 ↑ = bearish → 부호 반전, 50% 중립 기준).
#   insider_form4 : net_buy_minus_sell (내부자 순매수 = bullish). 중심 0 자연 경계.
_OBS_SIGNAL_MAP = {
    "aaii": ("bull_bear_spread", 1.0, 0.0),       # (metric, sign, center)
    "naaim": ("exposure_mean", 1.0, 50.0),        # 능동운용 노출 50% 중립
    "finra_short": ("market_short_volume_pct", -1.0, 50.0),  # 공매도 50% 중립, 반전
    "insider_form4": ("net_buy_minus_sell", 1.0, 0.0),
}
# 환산 불가(순수 메타, 방향 환산 불가능)로 제외한 신호 — 검증 trail 의 정직 기록:
#   aaii.bullish/neutral/bearish (개별 컴포넌트) = bull_bear_spread 에 흡수(중복 회피).
#   finra_short.n_symbols / form4.universe_covered/xml_fetched/capped 등 = 커버리지/메타(방향 없음).
#   ⇒ 4 source 각 1 forward 신호만 (강제) — 자유 신호 선택 surface 0.


def generate_observation_predictions(
    obs_latest: Dict[str, Any], path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """관측-only 신호(us_market_observations) → 시장-레벨 forward 예측 (Observation Signal Trails Spec v0).

    동기: AAII/NAAIM/FINRA/Form4 가 결정에 안 들어간 채(관측 only) 로깅만 되고 forward 채점 trail 이
    없어 "N≥252 때 wire 가치 있나" 판정 불가이던 갭. market-level forward 예측으로 환산 → 채점 누적.
    관측 only — 채점 결과는 어떤 verdict/결정에도 피드백 0 (RULE 7). wire 가치 판정 자료로만.

    obs_latest = us_market_observations.latest_per_source() 출력
                 = {source: {"period": "YYYY-MM-DD", "metrics": {...}}, ...}.
    매핑은 _OBS_SIGNAL_MAP (강제값, 곡선맞추기 surface 0). target='sp500'(US 시장-레벨).
    pred_score = (metric − center) * sign (up=양수 정렬). direction = sign(pred_score).
    confidence = 0.5 고정 (관측 신호는 캘리브레이션된 확률 미보유 — Brier 중립값. ML 과 달리 확률 아님).
    환산 불가(순수 메타) 신호는 _OBS_SIGNAL_MAP 에서 제외 (위 주석에 사유 기록).

    물리 분리: path 미지정 시 PT.OBS_PATH (프로덕션/섀도우/ML scorer 무오염, 기존 scorer 무변경).
    채점은 market-level scorer (시장 index 절대 level forward diff) — observation_scoring.py.
    """
    path = path or PT.OBS_PATH
    out: List[Dict[str, Any]] = []
    for src, (metric_key, sign, center) in _OBS_SIGNAL_MAP.items():
        rec = (obs_latest or {}).get(src)
        if not isinstance(rec, dict):
            continue  # 해당 source 관측 결손 = skip (graceful)
        metrics = rec.get("metrics") or {}
        raw = metrics.get(metric_key)
        if raw is None:
            continue  # metric 결손 = skip (graceful)
        try:
            score = (float(raw) - center) * sign
        except (TypeError, ValueError):
            continue
        if score > 0:
            direction = "up"
        elif score < 0:
            direction = "down"
        else:
            direction = "neutral"
        signals = {
            "obs_source": src,
            "metric_key": metric_key,
            "metric_raw": raw,
            "center": center,
            "sign": sign,
            "obs_period": rec.get("period"),  # 관측 데이터 as_of (PIT 동결)
            "source": _OBS_SOURCE,
        }
        for h in _HORIZONS:
            out.append(
                PT.log_prediction(
                    target_type="market", target="sp500", horizon=h,
                    direction=direction, pred_score=float(score), confidence=0.5,
                    signals=signals, spec_version="obs.v0",
                    source=f"{_OBS_SOURCE}.{src}",  # source 별 pred_id 충돌 회피 + 소스별 IC 분리 집계
                    path=path,
                )
            )
    return out


# 소형주 코너(AlphaNest 병렬 트랙) 검증 신호 = quant 팩터 개별 (PM 결정 2026-06-20, spec §11).
# brain_score 는 코너에서 degenerate — 15 fact component 중 ~3만 present(나머지 시장신호 default 50)
# → 평균이 50-51 상수(stdev 0.3). multi_factor 도 시장신호 5개 상수에 압축(stdev 1.79). 실제 분산 신호 =
# quant 팩터(momentum stdev 13 / quality 11 / vol 8 / mr 5). 각 팩터 별 source 태그 → 팩터별 독립 forward IC
# (관측 obs 패턴 미러, 가중치 자유선택 0, face-value). 어느 팩터가 코너에서 예측하나 = N≥252 IC 가 답함.
_SMALLCAP_BASE_SOURCE = "smallcap_corner"
# 팩터 라벨 → enrich quant_factors 키. 엔진이 이미 高점수=호재 정렬(vol=低변동 高점수 / mr=과매도 高점수)
# → face-value direction(score>50 up). 코너 전용 자유 파라미터 0.
_SMALLCAP_FACTORS = {
    "momentum": "momentum_score",
    "quality": "quality_score",
    "vol": "volatility_score",
    "mr": "mean_reversion_score",
}


def generate_smallcap_predictions(
    corner_stocks: List[Dict[str, Any]],
    neglected_tickers: Optional[List[str]] = None,
    path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """KR 소형주 코너 quant 팩터 → forward 예측 (Smallcap Corner Trail Spec v0, PM 결정 §11).

    동기: 코너 census+사실필터 완료, forward 검증 trail 부재. brain_score 는 코너에서 degenerate(상수)
    → 검증 신호 = quant 팩터 개별(momentum/quality/volatility/mean_reversion). 각 팩터 별 source 태그로
    forward 로깅 → 팩터별 독립 IC 누적. 관측 only — VAMS/Brain 학습 피드백 0 (RULE 7, brain_input=False).

    corner_stocks = smallcap_corner_enrich.enrich_quant_factors 통과 후(quant_factors/enriched 부착).
    enriched=False(가격레이크 부재) = 분산 0 → 제외 (spec §10). 레이크 백필 따라 검증 풀 성장.
    neglected_tickers = 방치 우량 부분군 멤버십 → signals 동결 → 부분군 IC 분리.
    direction = face-value(score>50 up / <50 down / ==50 neutral). 강제값 — 가중치/flip 자유선택 0.
    confidence = 0.5 고정(팩터 score 는 캘리브레이션 확률 아님, 관측 obs 패턴 정합).

    물리 분리: path 미지정 시 PT.SMALLCAP_PATH (메인/섀도우/ML/관측/regime scorer 무오염, 무변경).
    """
    path = path or PT.SMALLCAP_PATH
    neglected = {str(t) for t in (neglected_tickers or [])}
    out: List[Dict[str, Any]] = []
    for s in (corner_stocks or []):
        ticker = str(s.get("ticker") or "")
        # enriched=False(가격레이크 부재) = quant 분산 0 → 제외 (spec §10). enriched 키 부재도 제외.
        if not ticker or not s.get("enriched"):
            continue
        qf = s.get("quant_factors") or {}
        for fac, key in _SMALLCAP_FACTORS.items():
            raw = qf.get(key)
            if raw is None:
                continue  # 해당 팩터 결손 = skip (graceful)
            score = float(raw)
            direction = "up" if score > 50 else "down" if score < 50 else "neutral"
            src = f"{_SMALLCAP_BASE_SOURCE}.{fac}.v0"
            signals = {
                "factor": fac,
                "factor_score": score,
                "neglected_quality": ticker in neglected,  # 방치 우량 부분군 (사실 필터)
                "mktcap_eok": s.get("mktcap_eok"),
                "entry_price": s.get("close"),  # scan 시점 동결 (PIT, pykrx backward-adjust drift 회피)
                "market": s.get("market"),
                "price_points": s.get("price_points"),
                "source": src,
            }
            for h in _HORIZONS:
                out.append(
                    PT.log_prediction(
                        target_type="stock", target=ticker, horizon=h,
                        direction=direction, pred_score=score, confidence=0.5,
                        signals=signals, spec_version="smallcap.v0",
                        source=src, path=path,
                    )
                )
    return out


def generate_sector_predictions(
    macro_alignment: Dict[str, Any], path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """섹터 로테이션 — macro_industry_alignment score 로 rank → 방향 투영.

    PPL Q4: 단기(short) 섹터 로테이션은 단기 반전으로 학술지지 낮음 → low_confidence 플래그.
    """
    out: List[Dict[str, Any]] = []
    sectors = (macro_alignment or {}).get("sectors") or []
    if not sectors:
        return out
    # score desc 정렬 → rank
    ranked = sorted(sectors, key=lambda s: s.get("score", 0.0), reverse=True)
    for rank, s in enumerate(ranked, start=1):
        name = s.get("sector")
        sc = s.get("score")
        if not name or sc is None:
            continue
        tier = str(s.get("tier", "")).upper()
        if tier == "FAVORED" or sc > 0.05:
            direction = "up"
        elif tier == "DISFAVORED" or sc < -0.05:
            direction = "down"
        else:
            direction = "neutral"
        signals = {
            "align_score": sc, "raw_score": s.get("raw_score"),
            "tier": s.get("tier"), "contribution_count": s.get("contribution_count"),
            "source": "macro_industry_alignment.v0.1",
        }
        for h in _HORIZONS:
            out.append(
                PT.log_prediction(
                    target_type="sector", target=str(name), horizon=h,
                    direction=direction, pred_score=float(sc), confidence=0.5,
                    signals=signals, rank=rank,
                    low_confidence=(h == "short"),  # 단기 섹터 = 학술지지 낮음 (PPL Q4)
                    path=path,
                )
            )
    return out


def run_prediction_layer(
    recommendations: List[Dict[str, Any]],
    macro_alignment: Optional[Dict[str, Any]] = None,
    path: Optional[str] = None,
) -> Dict[str, int]:
    """daily 파이프라인 hook 진입점. cross-section 1벌 생성+로깅. 결손 시 graceful 부분 생성."""
    stock = generate_stock_predictions(recommendations, path=path)
    sector = generate_sector_predictions(macro_alignment or {}, path=path)
    return {
        "stock_predictions": len(stock),
        "sector_predictions": len(sector),
        "total": len(stock) + len(sector),
    }

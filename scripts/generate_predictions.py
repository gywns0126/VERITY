#!/usr/bin/env python3
"""
generate_predictions.py — daily Prediction Layer 생성 (decoupled, main.py 무편집).

2026-06-01 신설. 사전등록 spec docs/prediction_layer_spec_v0_2026_06_01.md 정합.
파이프라인 산출물(recommendations.json + macro_industry_alignment.json)을 읽어
prediction_trail.jsonl 에 cross-section 1벌 로깅. daily 워크플로의 main.py 이후 step.

graceful: 입력 결손 시 exit 0 (파이프라인 fail 안 시킴, RULE — 예측은 부수효과).
채점은 별도 cron (eval_date 도달분).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root (cockpit_aggregate 패턴)

from api.config import DATA_DIR, now_kst
from api.intelligence import prediction_layer as PL


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[predict] load fail {path}: {type(e).__name__}: {e}\n")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="trail 경로 override (테스트용). 기본 = data/metadata/prediction_trail.jsonl")
    args = ap.parse_args()

    recs = _load(os.path.join(DATA_DIR, "recommendations.json"))
    macro = _load(os.path.join(DATA_DIR, "macro_industry_alignment.json"))

    if isinstance(recs, dict):
        recs = recs.get("recommendations") or recs.get("data") or []
    # 프로덕션 예측 (recs 결손 시 skip — 섀도우는 독립 진행)
    if recs:
        summary = PL.run_prediction_layer(recs, macro if isinstance(macro, dict) else {}, path=args.out)
        print(
            f"[predict] logged {summary['total']} "
            f"(stock {summary['stock_predictions']} + sector {summary['sector_predictions']})"
        )
        if summary["total"] == 0:
            sys.stderr.write("[predict] 생성 0건 — verity_brain/sectors 결손 가능 (graceful)\n")
    else:
        sys.stderr.write("[predict] recommendations 없음 — production skip (graceful)\n")

    # ML(XGB up_probability) 예측 (ML Shadow Prediction Spec v0 — 별도 trail, 프로덕션 무오염)
    # recs 의 prediction.up_probability 사용 (genuine ensemble 만). 관측 only(RULE 7).
    ml_out = (args.out + ".ml.jsonl") if args.out else None  # 테스트 시에도 ML 격리
    if recs:
        ml = PL.generate_ml_predictions(recs, path=ml_out)
        if ml:
            print(
                f"[predict] ml logged {len(ml)} "
                f"(xgb ensemble {len(ml) // len(PL._HORIZONS)} × {len(PL._HORIZONS)}h, source={PL._ML_SOURCE}, "
                f"trail={'ml_prediction_trail.jsonl' if not ml_out else ml_out})"
            )
        else:
            sys.stderr.write("[predict] ml 0건 — ensemble 예측 없음(fallback/결손) (graceful)\n")

    # 국면(regime) 예측 (Regime Validation Spec v0 — 별도 trail, 프로덕션/섀도우/ML 무오염)
    # market_horizon.cycle_stage + verity_brain.macro_override 가 forward 시장 수익률을 예측하나
    # 관측 검증. 시장레벨 단일값 → 자체 schema(regime_prediction.py). 관측 only(RULE 7).
    # 입력 = 최신 history snapshot (market_horizon + verity_brain + index level 모두 포함).
    regime_out = (args.out + ".regime.jsonl") if args.out else None  # 테스트 시에도 격리
    try:
        from api.intelligence import regime_prediction as RG
        from api.workflows.archiver import load_snapshot
        snap = load_snapshot(now_kst().strftime("%Y-%m-%d"))
        if not snap:
            # 오늘 snapshot 미생성 시 recommendations.json 컨테이너의 portfolio 류 fallback 없음 → skip
            sys.stderr.write("[predict] regime: 오늘 snapshot 없음 — regime skip (graceful)\n")
        else:
            rg = RG.run_regime_layer(snap, path=regime_out)
            if rg.get("regime_predictions"):
                print(
                    f"[predict] regime logged {rg['regime_predictions']} "
                    f"({rg['regime_predictions'] // len(RG._HORIZONS)} state × {len(RG._HORIZONS)}h, "
                    f"source={RG.REGIME_SOURCE}, "
                    f"trail={'regime_prediction_trail.jsonl' if not regime_out else regime_out})"
                )
            else:
                sys.stderr.write("[predict] regime 0건 — macro_override/cycle_stage 결손 (graceful)\n")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[predict] regime skip (graceful): {type(e).__name__}: {e}\n")

    # 섀도우 funnel 예측 (Shadow Funnel Scoring Spec v0 — 별도 trail, 프로덕션 무오염)
    shadow = _load(os.path.join(DATA_DIR, "metadata", "shadow_funnel_picks.json"))
    shadow_out = (args.out + ".shadow.jsonl") if args.out else None  # 테스트 시에도 섀도우 격리
    if isinstance(shadow, dict) and shadow.get("picks"):
        # scan_at 신선도 가드 (P2 #13): universe_scan miss 시 stale picks 재emit → IC 시계열 중복 왜곡 방지.
        scan_day = str(shadow.get("scan_at", ""))[:10]
        today = now_kst().strftime("%Y-%m-%d")
        if scan_day and scan_day < today:
            sys.stderr.write(
                f"[predict] shadow picks stale (scan_at={scan_day} < today={today}) — shadow skip (graceful)\n"
            )
        else:
            sh = PL.generate_shadow_predictions(shadow["picks"], path=shadow_out)
            print(
                f"[predict] shadow logged {len(sh)} "
                f"(funnel {len(shadow['picks'])} × {len(PL._HORIZONS)}h, source={PL._SHADOW_SOURCE}, "
                f"trail={'shadow_prediction_trail.jsonl' if not shadow_out else shadow_out})"
            )
    else:
        sys.stderr.write("[predict] shadow_funnel_picks 없음/빈값 — shadow skip (graceful)\n")

    # 관측-only 신호(us_market_observations: AAII/NAAIM/FINRA/Form4) → market-level forward 예측
    # (Observation Signal Trails Spec v0 — 별도 trail OBS_PATH, 프로덕션/섀도우/ML 무오염). 관측 only(RULE 7).
    obs_out = (args.out + ".obs.jsonl") if args.out else None  # 테스트 시에도 관측 격리
    try:
        from api.collectors.us_market_observations import latest_per_source
        obs_latest = latest_per_source()
    except Exception as e:  # noqa: BLE001 — 관측 결손이 전체 막지 않게 (graceful)
        sys.stderr.write(f"[predict] obs latest 로드 실패: {type(e).__name__}: {e} — obs skip (graceful)\n")
        obs_latest = {}
    if obs_latest:
        obs = PL.generate_observation_predictions(obs_latest, path=obs_out)
        if obs:
            print(
                f"[predict] obs logged {len(obs)} "
                f"({len(obs) // len(PL._HORIZONS)} source × {len(PL._HORIZONS)}h, source={PL._OBS_SOURCE}, "
                f"trail={'observation_prediction_trail.jsonl' if not obs_out else obs_out})"
            )
        else:
            sys.stderr.write("[predict] obs 0건 — 매핑 신호 결손 (graceful)\n")
    else:
        sys.stderr.write("[predict] us_market_observations 없음/빈값 — obs skip (graceful)\n")

    # 소형주 코너(골든구스 병렬 트랙) → brain analyze_all 별도 호출 → forward 예측
    # (Smallcap Corner Trail Spec v0 — 별도 trail SMALLCAP_PATH, 메인/섀도우/ML/관측/regime 무오염).
    # 관측 only — 채점 결과 VAMS/Brain 학습 피드백 0 (RULE 7, brain_input=False).
    smallcap_out = (args.out + ".smallcap.jsonl") if args.out else None  # 테스트 시에도 격리
    corner = _load(os.path.join(DATA_DIR, "smallcap_corner.json"))
    if isinstance(corner, dict) and corner.get("stocks"):
        # 방치 우량 부분군 멤버십(사실 필터, 점수 아님) — signals 동결 → 부분군 IC 분리 집계.
        neglected: list = []
        cf = _load(os.path.join(DATA_DIR, "smallcap_corner_filters.json"))
        if isinstance(cf, dict):
            for filt in cf.get("filters") or []:
                if filt.get("key") == "neglected_quality":
                    neglected = [t.get("ticker") for t in (filt.get("tickers") or []) if t.get("ticker")]
                    break
        # Phase 1 enrichment — 가격레이크 quant 팩터 → brain_score 분산 lever (spec §10).
        # 로컬 전용(레이크 = repo 밖). CI/lake 부재 = 전 종목 enriched=False → generate 가 graceful skip.
        try:
            from api.builders.smallcap_corner_enrich import enrich_quant_factors
            corner_stocks = enrich_quant_factors(corner["stocks"])
            n_enriched = sum(1 for s in corner_stocks if s.get("enriched"))
            sys.stderr.write(f"[predict] smallcap enrich: {n_enriched}/{len(corner_stocks)} (가격레이크 커버)\n")
        except Exception as e:  # noqa: BLE001 — enrich 실패 = 미enrich 진행 (generate 가 skip)
            sys.stderr.write(f"[predict] smallcap enrich skip (graceful): {type(e).__name__}: {e}\n")
            corner_stocks = corner["stocks"]
        sc = PL.generate_smallcap_predictions(corner_stocks, neglected_tickers=neglected, path=smallcap_out)
        if sc:
            n_fac = len(PL._SMALLCAP_FACTORS)
            print(
                f"[predict] smallcap logged {len(sc)} "
                f"({n_enriched} enriched × {n_fac} factor × {len(PL._HORIZONS)}h, "
                f"neglected={len(neglected)}, source={PL._SMALLCAP_BASE_SOURCE}.*, "
                f"trail={'smallcap_corner_prediction_trail.jsonl' if not smallcap_out else smallcap_out})"
            )
        else:
            sys.stderr.write("[predict] smallcap 0건 — enriched 종목 결손 (graceful)\n")
    else:
        sys.stderr.write("[predict] smallcap_corner.json 없음/빈값 — smallcap skip (graceful)\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

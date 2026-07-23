"""validation_summary — 모든 forward trail 의 정직한 검증 상태 단일 집계 (read-only).

목적 (2026-06-13 신설): 흩어진 forward-scoring 산출물(brain production / xgb_ml /
shadow_funnel / factor / sector)을 한 레코드씩 묶어 N=252 IC 게이트(2027-05) 읽기 준비 +
운영자 크레덴셜 surface 로 만든다.

규율:
  · RULE 7 = 관측 only. 어떤 verdict/score/결정에도 피드백 0. 산식 신규 0 —
    이미 채점된 *_ic_history 산출물의 필드를 **재집계만** 한다 (prediction_scoring /
    ic_stats 가 LOCKED 산식으로 산출한 값을 그대로 읽음). 자유 파라미터 없음.
  · 라벨 강제값 = N_eff(없으면 N) 기준: <30 "통계 무의미" / <100 "예비" / 그 외 "유의(잠정)".
    모든 항목 "가설(N=X)" 명시. hit_rate 단독 노출 금지 — expectancy + CI95 + N 병기 의무.
  · graceful = 입력 결손 시 예외 없이 skip (해당 신호 status="데이터 없음").

이 모듈은 산출만 한다 (data/validation_summary.json). UI/Framer 미포함 (commoditized 레이어).
배선 = scripts/build_validation_summary.py (cron 1 step). spec docs/validation_summary_spec_v0_2026_06_13.md.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst
from api.quant.alpha.ic_validity import is_valid_ic_obs

# ── 입력 1차 자료 경로 (모두 기존 산출물 — RULE 10 검증 완료 2026-06-13) ──────────
# brain production 채점 집계 (prediction_scoring → prediction_ic_history.jsonl)
_BRAIN_IC_PATH = os.path.join(DATA_DIR, "prediction_ic_history.jsonl")
# XGB up_probability shadow 채점 집계 (오늘 신설, score_predictions --ic-history)
_ML_IC_PATH = os.path.join(DATA_DIR, "ml_prediction_ic_history.jsonl")
# factor IC 시계열 (ic_stats machinery 산출, 일별 list)
_FACTOR_IC_PATH = os.path.join(DATA_DIR, "factor_ic_history.json")
# trail 원본 (집계 미도달 신호의 정직한 pending 카운트용)
_SHADOW_TRAIL_PATH = os.path.join(DATA_DIR, "metadata", "shadow_prediction_trail.jsonl")
_PRED_TRAIL_PATH = os.path.join(DATA_DIR, "metadata", "prediction_trail.jsonl")

_OUT_PATH = os.path.join(DATA_DIR, "validation_summary.json")

SPEC_VERSION = "v0"

# ── RULE 7 라벨 게이트 (강제값 — 자유 파라미터 아님) ─────────────────────────────
_N_MEANINGLESS = 30    # N<30 = 통계 무의미 (CLAUDE.md RULE 7)
_N_PRELIM = 100        # N<100 = 예비 결과 (project_minimum_n_milestones)
_GATE_N = 252          # N=252 IC 게이트 (Bailey-López de Prado, 2027-05 목표)


def _maturity_label(n_eff: Optional[float]) -> str:
    """N_eff(없으면 raw N) 기준 강제 성숙도 라벨. raw N 아닌 중첩보정 N_eff 우선."""
    if n_eff is None:
        return "데이터 없음"
    if n_eff < _N_MEANINGLESS:
        return "통계 무의미 (N<30)"
    if n_eff < _N_PRELIM:
        return "예비 (N<100, 검증 진행 중)"
    # N≥100 = 표본 크기 마일스톤일 뿐 — 신호 유의성과 별개(IC p 로 판정). "유의 표본 도달"
    # 표현은 신호가 유의한 것으로 오독되어 금지(RULE 7). 2026-06-19 정직화.
    return "표본 N≥100 누적 (잠정 — 유의성 미검증)"


def _gate_status(n_eff: Optional[float], ic_pvalue: Optional[float]) -> str:
    """가설 vs 검증 상태 (N=252 게이트 기준). RULE 7 — 모두 잠정."""
    if n_eff is None:
        return "가설 (관측 0)"
    if n_eff < _GATE_N:
        pct = round(min(n_eff / _GATE_N * 100.0, 99.9), 1)
        return f"가설 (게이트 N≥252 미도달, 진척 {pct}%)"
    # 게이트 도달 — 그래도 단일 검증, RULE 7 잠정 유지
    if ic_pvalue is not None and ic_pvalue < 0.05:
        return "게이트 도달 + p<0.05 (잠정 검증 신호, 단일 trail)"
    return "게이트 도달 (유의성 미달 — 가설 유지)"


# ── jsonl/json 안전 read ─────────────────────────────────────────────────────


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def _read_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _latest_per_horizon(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """ic_history (append-only 스냅샷 list) → horizon 별 최신 1건.

    prediction_scoring._aggregate 가 매 run 마다 horizon 별 1 레코드를 append 하므로
    (target_type='stock', horizon) 최신 = list 뒤에서 처음 만난 stock 레코드.
    """
    latest: Dict[str, Dict[str, Any]] = {}
    for r in records:
        if r.get("target_type") != "stock":
            continue
        h = r.get("horizon")
        if not h:
            continue
        latest[h] = r  # 순차 append → 마지막이 최신
    return latest


def _ic_record_to_signal(name: str, source_note: str,
                         latest: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """prediction_scoring 산출 horizon 스냅샷 → 한 신호 레코드.

    재집계만: ic/ic_pvalue/hit_rate/brier/expectancy/ci95/n/effective_n 은 이미 채점된 값.
    RULE 7 라벨 부착 + hit_rate 병기 강제(expectancy+ci95+n 동반).
    """
    if not latest:
        return {
            "signal": name, "status": "trail 누적, 채점 도달 0",
            "source": source_note, "horizons": {},
            "label": "데이터 없음", "gate_status": "가설 (관측 0)",
            "note": "eval_date 도달 채점분 0 — 누적만 진행 (forward-only).",
        }

    horizons: Dict[str, Any] = {}
    # surface 대표 = short horizon (가장 먼저 표본 누적). 없으면 임의 1건.
    rep = latest.get("short") or next(iter(latest.values()))
    for h, r in latest.items():
        n = r.get("n")
        n_eff = r.get("effective_n")
        horizons[h] = {
            "n": n,
            "n_eff": n_eff,
            "overlap_k": r.get("overlap_k"),
            "ic": r.get("ic"),
            "ic_tstat": r.get("ic_tstat"),
            "ic_pvalue": r.get("ic_pvalue"),
            # hit_rate 단독 금지 — expectancy + ci95 + n 병기 (RULE 7)
            "hit_rate": r.get("hit_rate"),
            "hit_n": r.get("hit_n"),
            "hit_pvalue": r.get("hit_pvalue"),
            "expectancy": r.get("expectancy"),
            "ci95": r.get("ci95"),
            "brier_score": r.get("brier_score"),
            "maturity_label": _maturity_label(n_eff),
            "gate_status": _gate_status(n_eff, r.get("ic_pvalue")),
            "scored_at": r.get("scored_at"),
        }

    rep_n_eff = rep.get("effective_n")
    return {
        "signal": name,
        "status": "채점 진행 중",
        "source": source_note,
        "representative_horizon": rep.get("horizon"),
        "n": rep.get("n"),
        "n_eff": rep_n_eff,
        "ic": rep.get("ic"),
        "ic_pvalue": rep.get("ic_pvalue"),
        "hit_rate": rep.get("hit_rate"),
        "expectancy": rep.get("expectancy"),
        "ci95": rep.get("ci95"),
        "brier_score": rep.get("brier_score"),
        "label": _maturity_label(rep_n_eff),
        "gate_status": _gate_status(rep_n_eff, rep.get("ic_pvalue")),
        "horizons": horizons,
        # RULE 7 명시 — hit_rate 자체 산식 아님, 채점 산출. 병기 강제됨.
        "hypothesis_note": "자기 산식 (가설). hit_rate 단독 해석 금지 — expectancy+CI95+N 병기.",
    }


# ── 신호별 빌더 ───────────────────────────────────────────────────────────────


def _brain_production_signal() -> Dict[str, Any]:
    recs = _read_jsonl(_BRAIN_IC_PATH)
    return _ic_record_to_signal(
        "brain_production",
        "prediction_ic_history.jsonl (Brain 종합 verdict, prediction_scoring v0)",
        _latest_per_horizon(recs),
    )


def _xgb_ml_signal() -> Dict[str, Any]:
    recs = _read_jsonl(_ML_IC_PATH)
    sig = _ic_record_to_signal(
        "xgb_ml",
        "ml_prediction_ic_history.jsonl (XGB up_probability shadow, source-agnostic scorer 재사용)",
        _latest_per_horizon(recs),
    )
    sig["context"] = "ai_upside_relax 가 brain 을 override 하나 미채점이던 갭의 관측 검증 (관측 only)."
    return sig


def _shadow_funnel_signal() -> Dict[str, Any]:
    """shadow_funnel 은 채점 cron(ic_history) 미연결 — trail 원본에서 정직한 카운트만."""
    rows = _read_jsonl(_SHADOW_TRAIL_PATH)
    if not rows:
        return {"signal": "shadow_funnel", "status": "데이터 없음", "label": "데이터 없음",
                "gate_status": "가설 (관측 0)", "source": "shadow_prediction_trail.jsonl"}
    scored = sum(1 for r in rows if r.get("scored") and r.get("realized_return") is not None)
    pending = len(rows) - scored
    return {
        "signal": "shadow_funnel",
        "status": "trail 누적 (채점 ic_history 미연결)",
        "source": "shadow_prediction_trail.jsonl (wide_scan 7차원 funnel SHADOW)",
        "trail_total": len(rows),
        "scored": scored,
        "pending": pending,
        "n": scored,
        "n_eff": None,
        "label": _maturity_label(float(scored) if scored else None),
        "gate_status": _gate_status(float(scored) if scored else None, None),
        "note": "wide_scan SHADOW trail 누적 중. 채점 IC 집계는 미연결 (정직 보고). "
                "활성 시 prediction_scoring source-agnostic 재사용.",
    }


def _factor_signal() -> Dict[str, Any]:
    """factor_ic_history.json (일별 list) → 최신 레코드의 per-factor IC/ICIR 재집계."""
    data = _read_json(_FACTOR_IC_PATH)
    if not isinstance(data, list) or not data:
        return {"signal": "factor", "status": "데이터 없음", "label": "데이터 없음",
                "gate_status": "가설 (관측 0)", "source": "factor_ic_history.json"}
    latest = data[-1]
    factors_raw = latest.get("factors") or {}
    factors: Dict[str, Any] = {}
    max_n = 0
    for fname, fobj in factors_raw.items():
        if not isinstance(fobj, dict):
            continue
        # 2026-06-14 D9: degenerate(sample_count==0 → icir 폭주) 격리. 단일 SoT predicate.
        if not is_valid_ic_obs(fobj):
            continue
        n = fobj.get("sample_count")
        if isinstance(n, (int, float)):
            max_n = max(max_n, int(n))
        factors[fname] = {
            "ic_mean": fobj.get("ic_mean"),
            "icir": fobj.get("icir"),
            "sample_count": n,
            "significant": fobj.get("significant"),
            "decay": fobj.get("decay"),
            "maturity_label": _maturity_label(float(n) if isinstance(n, (int, float)) else None),
        }
    return {
        "signal": "factor",
        "status": "IC 시계열 누적 중",
        "source": "factor_ic_history.json (ic_stats machinery, forward_days "
                  f"{latest.get('forward_days')})",
        "date_key": latest.get("date_key"),
        "forward_days": latest.get("forward_days"),
        "n": max_n or None,
        "n_eff": None,  # factor IC = 일별 시계열 (T), 중첩보정은 ic_stats Newey-West 영역
        "label": _maturity_label(float(max_n) if max_n else None),
        "gate_status": _gate_status(float(max_n) if max_n else None, None),
        "factors": factors,
        "note": "per-factor ic_mean/ICIR = ic_stats LOCKED 산식 산출 (재집계만). "
                "significant 플래그는 ic_stats 산출값 그대로 — 본 surface 재판정 없음.",
    }


def _sector_signal() -> Dict[str, Any]:
    """sector 예측 = prediction_scoring v0 에서 채점 보류(return source 미검증). 정직 보고."""
    rows = _read_jsonl(_PRED_TRAIL_PATH)
    sector_total = sum(1 for r in rows if r.get("target_type") == "sector")
    return {
        "signal": "sector",
        "status": "채점 DEFERRED (검증된 섹터 index return source 미확정)",
        "source": "prediction_trail.jsonl (target_type=sector)",
        "trail_total": sector_total,
        "scored": 0,
        "n": 0,
        "n_eff": None,
        "label": "데이터 없음 (채점 보류)",
        "gate_status": "가설 (채점 보류 — return source 미검증)",
        "note": "sectors[].change_pct = heat/모멘텀 메트릭이며 clean period return 아님. "
                "잘못된 proxy 채점 = RULE 7 위반 → 보류. trail 은 forward 누적만.",
    }


# ── 메인 ─────────────────────────────────────────────────────────────────────


def build_summary() -> Dict[str, Any]:
    """모든 forward trail 의 정직한 검증 상태를 한 dict 로 집계 (순수 read-only)."""
    signals = [
        _brain_production_signal(),
        _xgb_ml_signal(),
        _shadow_funnel_signal(),
        _factor_signal(),
        _sector_signal(),
    ]
    # 게이트 진척 = 신호 중 최대 N_eff(없으면 N) 기준 (운영자 한눈)
    best_n = 0.0
    for s in signals:
        cand = s.get("n_eff")
        if cand is None:
            cand = s.get("n")
        if isinstance(cand, (int, float)):
            best_n = max(best_n, float(cand))

    return {
        "generated_at": now_kst().isoformat(),
        "spec_version": SPEC_VERSION,
        "gate": {
            "target_n": _GATE_N,
            "milestone": "N=252 IC 게이트 (Bailey-López de Prado, 2027-05 목표)",
            "best_signal_n": round(best_n, 2) if best_n else 0,
            "progress_pct": round(min(best_n / _GATE_N * 100.0, 99.9), 1) if best_n else 0.0,
        },
        "rule7_disclaimer": (
            "모든 항목 = 자기 산식 가설 (관측 only, 결정 피드백 0). N<30 통계 무의미 / "
            "N<100 예비. hit_rate 단독 해석 금지 — expectancy + CI95 + N 병기. "
            "N=252 게이트(2027-05) 도달 전 통계 판정 무의미."
        ),
        "signals": signals,
        "_method": "기존 *_ic_history 산출물 재집계만 (신규 산식 0). prediction_scoring / "
                   "ic_stats LOCKED 산출값을 read-only 로 묶음. UI 미포함 (데이터 산출까지).",
    }


# 공개 발행 허용 signal 필드 화이트리스트 (옵션 B, 2026-06-18 + 2026-06-25 재확인).
# 과정 투명성 = 신호명·표본·성숙도·출처는 공개. raw 성과(ic/expectancy/hit_rate/ci95/
# brier/horizons/ic_pvalue 등)는 화이트리스트 밖이라 자동 제외 → 검증(N≥252) 후 공개.
_PUBLIC_SIGNAL_FIELDS = ("signal", "status", "n", "n_eff", "label", "gate_status", "source")


def _sanitize_signal(s: Dict[str, Any]) -> Dict[str, Any]:
    return {k: s.get(k) for k in _PUBLIC_SIGNAL_FIELDS}


def public_slim(summary: Dict[str, Any]) -> Dict[str, Any]:
    """공개 발행용 slim — 과정·신호명·표본만. raw 성과 필드는 화이트리스트로 제거.

    🚨 옵션 B 를 데이터 레이어에서 강제 (이전엔 UI 만 가렸고 raw JSON 은 ic/expectancy 노출 = leak).
    공개: gate 진행률 + 신호명 + N/N_eff + 성숙도 label + gate_status + source.
    비공개: ic·expectancy·hit_rate·ci95·brier·horizons (검증 N≥252 후). PublicGlassboxTab 소비 정합.
    메인 repo PUBLIC + git add data/ broad 라 full 비영속 (raw 성과 disk 커밋 회피).
    """
    return {
        "generated_at": summary.get("generated_at"),
        "spec_version": summary.get("spec_version"),
        "gate": summary.get("gate"),
        "rule7_disclaimer": summary.get("rule7_disclaimer"),
        # 🚨 VERITY wide-scan funnel = 비공개 자산 → 공개 slim 에서 제외 (내부 full 엔 유지).
        #    AlphaNest 공개 표면에 funnel 존재/신호 노출 금지 (feedback_verity_vs_alphanest_identity).
        "signals": [
            _sanitize_signal(s)
            for s in summary.get("signals", [])
            if "funnel" not in str(s.get("signal", "")).lower()
        ],
        "_note": (
            "공개 = 과정·신호명·표본·성숙도만. raw 성과(IC·적중률·기댓값·CI) = 검증(N≥252) 후. "
            "표본 누적 ≠ 신호 검증 (게이트 전 동전던지기와 구별 불가). 점수·등급·종목 추천 아님 (RULE 7 가설)."
        ),
    }


def write_summary(out_path: Optional[str] = None) -> Dict[str, Any]:
    """집계 산출 → validation_summary.json(공개 slim) 원자적 write. 반환 = full 집계 dict(로그용).

    공개 발행 파일은 핵심 제외 slim 만 (public_slim). full(신호별 IC·expectancy) 은
    소비처 0 + 공개 repo 노출 회피 위해 disk 영속하지 않음 — 필요 시 *_ic_history 원본 재집계.
    """
    out_path = out_path or _OUT_PATH
    summary = build_summary()
    public = public_slim(summary)
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(public, f, ensure_ascii=False, indent=2)
        os.replace(tmp, out_path)
    except OSError as e:
        summary["_write_error"] = f"{type(e).__name__}: {e}"
    return summary


if __name__ == "__main__":
    s = write_summary()
    g = s["gate"]
    print(f"[validation_summary] best_signal_n={g['best_signal_n']} "
          f"progress={g['progress_pct']}% (게이트 N={g['target_n']})")
    for sig in s["signals"]:
        print(f"  {sig['signal']:<18} status={sig.get('status')} "
              f"n={sig.get('n')} label={sig.get('label')}")

#!/usr/bin/env python3
"""
berserker_status.py — ARENA 버서커 모드 status + 검증량 카운트다운 (Phase 1)

WHY: PM 결정 2026-06-08 — ARENA를 "최대의 적극적 투자 모델"로 부활(shadow only).
핵심 통합 아이디어 = 공격 다이얼과 잠금 해제 카운트다운을 *하나의* 검증 진행도
함수 validation_progress(N)로 구동. PM 발화 "계속 쌓여가는 데이터 검증을 통해
내놓은" 그대로 — 검증이 깊어질수록 버서커가 이빨을 얻음.

  validation_progress = mean(4 게이트 정규화 비율)   # 0.0 → 1.0
  aggression_multiplier = validation_progress         # 보수코어(0) → 풀버서커(1)
  leverage/short = report overall == PASS 전까지 LOCKED, countdown = 게이트별 잔여

게이트 = VAMS 사전약속 기준 재사용 (자체 임계 신설 X, divergence 0):
  · days       ≥ VAMS_VALIDATION_MIN_DAYS  (60 거래일)
  · trades     ≥ VAMS_VALIDATION_MIN_TRADES (20)
  · expectancy ≥ VAMS_MIN_EXPECTANCY_R     (0.25R)
  · sqn        ≥ VAMS_MIN_SQN              (1.7)

가드:
  · shadow only — 본 모듈은 status/카운트다운만 산출. 실주문·실사이징 0 (Phase 2 = shadow 채점).
  · 레버리지·숏 = arena_sim_prototype.py 에 모델 존재하되 LOCKED. 해제 = PASS + 수동 venue 결정.
  · 측정값 = 가설 (N=X). site 노출 시 "(가설/N=X)" 의무 (RULE 7).
  · 검증 상태 = api.vams 재사용 (자체 재계산 X, [[feedback_component_overlap_audit]]).

산출: data/arena/berserker_status.json
실행:
  python -m api.arena.berserker_status            # 산출 + 콘솔
  python -m api.arena.berserker_status --check    # 네트워크/IO 없이 import·계산 검증만
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from api.config import (
    now_kst,
    DATA_DIR,
    VAMS_VALIDATION_MIN_DAYS,
    VAMS_VALIDATION_MIN_TRADES,
    VAMS_MIN_EXPECTANCY_R,
    VAMS_MIN_SQN,
    VAMS_VALIDATION_START_DATE,
)

# 거래일 → 캘린더일 근사 (5 거래일 ≈ 7 캘린더일). ETA = 추정 라벨 only.
_CAL_PER_TRADING_DAY = 7.0 / 5.0


def _ratio(current: Optional[float], target: float) -> float:
    """게이트 정규화 비율 [0,1]. current None/음수 → 0. target 도달 → 1."""
    if current is None or target <= 0:
        return 0.0
    return max(0.0, min(1.0, current / target))


def compute_progress(report: dict, trades: int) -> dict:
    """VAMS report + trade 수 → 4 게이트 진행도 + 종합 validation_progress.

    Args:
        report: api.vams.validation.compute_validation_report() 반환
        trades: 완료 매매 건수 (_trade_stats["trades"])
    """
    days = report.get("window", {}).get("days", 0) or 0
    metrics = report.get("metrics", {})
    expectancy = metrics.get("expectancy", {}).get("expectancy_r")
    sqn = metrics.get("sqn", {}).get("sqn")

    gates = {
        "days": {
            "current": days,
            "target": VAMS_VALIDATION_MIN_DAYS,
            "progress": _ratio(days, VAMS_VALIDATION_MIN_DAYS),
            "remaining": max(0, VAMS_VALIDATION_MIN_DAYS - days),
            "unit": "거래일",
        },
        "trades": {
            "current": trades,
            "target": VAMS_VALIDATION_MIN_TRADES,
            "progress": _ratio(trades, VAMS_VALIDATION_MIN_TRADES),
            "remaining": max(0, VAMS_VALIDATION_MIN_TRADES - trades),
            "unit": "건",
        },
        "expectancy": {
            "current": expectancy,
            "target": VAMS_MIN_EXPECTANCY_R,
            "progress": _ratio(expectancy, VAMS_MIN_EXPECTANCY_R),
            "remaining": None,  # 표본 누적 전 의미 X — gap 은 site 에서 current/target 로 표기
            "unit": "R",
        },
        "sqn": {
            "current": sqn,
            "target": VAMS_MIN_SQN,
            "progress": _ratio(sqn, VAMS_MIN_SQN),
            "remaining": None,
            "unit": "SQN",
        },
    }

    overall = round(sum(g["progress"] for g in gates.values()) / len(gates), 4)

    # ETA 추정 (days 게이트만 캘린더 환산 — expectancy/sqn 은 표본 의존이라 시점 추정 불가)
    days_remaining = gates["days"]["remaining"]
    eta_calendar_days = int(round(days_remaining * _CAL_PER_TRADING_DAY)) if days_remaining else 0

    return {
        "validation_progress": overall,
        "gates": gates,
        "days_eta_calendar_days_est": eta_calendar_days,
    }


def compute_berserker_status() -> dict:
    """버서커 status 전체 — 검증 진행도 + 공격 다이얼 + 잠금 카운트다운."""
    from api.vams.engine import load_portfolio, load_history
    from api.vams.validation import compute_validation_report, _trade_stats

    portfolio = load_portfolio()
    history = load_history()
    report = compute_validation_report(portfolio, history)
    trade = _trade_stats(history, start_date=VAMS_VALIDATION_START_DATE or None)

    prog = compute_progress(report, trade.get("trades", 0))
    p = prog["validation_progress"]
    fully_unlocked = report.get("overall") == "PASS"

    # 공격 다이얼 = validation_progress. 보수코어(0) → 풀버서커(1).
    # Phase 1 = 다이얼 값 노출만. 실 사이징(full-Kelly×p)은 Phase 2 shadow 채점에서 적용.
    aggression = {
        "multiplier": p,
        "mode": (
            "풀 버서커" if fully_unlocked
            else "준비 (검증 누적 중)" if p > 0
            else "대기 (검증 N 부족)"
        ),
        "note": "공격성 = 검증 진행도의 함수. 풀 Kelly 사이징은 PASS 후 활성 (현재 shadow).",
    }

    locked_features = [
        {
            "name": "leverage",
            "label": "레버리지 (일일 L배)",
            "status": "UNLOCKED" if fully_unlocked else "LOCKED",
            "unlock_condition": "VAMS 검증 overall == PASS",
            "countdown": _countdown_text(prog["gates"]),
            "note": "모델 존재 (scripts/arena_sim_prototype.py). 해제 후 PM 수동 활성.",
        },
        {
            "name": "short_inverse",
            "label": "숏 / 인버스",
            "status": "UNLOCKED" if fully_unlocked else "LOCKED",
            "unlock_condition": "VAMS PASS + 수동 venue 결정 (별도)",
            "countdown": _countdown_text(prog["gates"]),
            "note": "현물 거래소(업비트/KIS) 부재 — 해외 파생·인버스 ETF venue 결정 필요. Tier-up 큐.",
        },
    ]

    return {
        "as_of": now_kst().strftime("%Y-%m-%d %H:%M"),
        "validation_start": VAMS_VALIDATION_START_DATE,
        "validation_overall": report.get("overall"),
        "validation_progress": p,
        "validation_progress_pct": round(p * 100, 1),
        "gates": prog["gates"],
        "days_eta_calendar_days_est": prog["days_eta_calendar_days_est"],
        "aggression": aggression,
        "locked_features": locked_features,
        "fully_unlocked": fully_unlocked,
        "_disclaimer": "가설 — 모든 수치는 검증 진행 중 추정. shadow only (실자본 0).",
        "_source": "api.vams (검증 상태) + ARENA A축 spec (docs/arena_spec_v0_2026_05_30.md)",
    }


def _countdown_text(gates: dict) -> str:
    """미달 게이트만 요약 — '20 거래일 + 18건 + expectancy/SQN' 형태."""
    parts = []
    if gates["days"]["remaining"] > 0:
        parts.append(f"{gates['days']['remaining']} 거래일")
    if gates["trades"]["remaining"] > 0:
        parts.append(f"{gates['trades']['remaining']}건")
    for k in ("expectancy", "sqn"):
        g = gates[k]
        cur, tgt = g["current"], g["target"]
        if cur is None or cur < tgt:
            parts.append(f"{k} {cur if cur is not None else '—'}/{tgt}")
    return " + ".join(parts) if parts else "전 게이트 충족 — 해제 대기"


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="ARENA 버서커 status")
    ap.add_argument("--check", action="store_true", help="IO 없이 import·계산 검증만")
    args = ap.parse_args(argv)

    if args.check:
        # 합성 report 로 compute_progress 순수 함수 검증 (네트워크/파일 X)
        fake_report = {
            "window": {"days": 12},
            "metrics": {"expectancy": {"expectancy_r": None}, "sqn": {"sqn": None}},
            "overall": "INSUFFICIENT_DATA",
        }
        prog = compute_progress(fake_report, trades=0)
        assert 0.0 <= prog["validation_progress"] <= 1.0
        assert prog["gates"]["days"]["remaining"] == VAMS_VALIDATION_MIN_DAYS - 12
        print(f"[check] OK — progress={prog['validation_progress']} "
              f"(days 12/{VAMS_VALIDATION_MIN_DAYS}, trades 0/{VAMS_VALIDATION_MIN_TRADES})")
        return 0

    status = compute_berserker_status()
    out_dir = Path(DATA_DIR) / "arena"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "berserker_status.json"
    out_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[berserker] validation_progress={status['validation_progress_pct']}% "
          f"({status['validation_overall']}) → mode={status['aggression']['mode']}")
    for f in status["locked_features"]:
        print(f"  {f['label']}: {f['status']} — 잔여: {f['countdown']}")
    print(f"  → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

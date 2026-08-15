# -*- coding: utf-8 -*-
"""ic_overlap_check — 팩터 IC 의 t 통계량이 겹침으로 부풀려졌는지 재판정.

왜 존재하는가
-------------
`alpha_scanner.compute_factor_ic` 은 **일별 스냅샷마다** forward 창을 열어 IC 를 낸다.
스냅샷 간격이 중앙 1일이므로 인접 관측은 (fwd-1)/fwd 만큼 **같은 미래 구간을 공유**한다.
그런데 시스템이 쓰는 t 는 관측 일수 n 을 그대로 독립 표본으로 센다:

    t_현행 = ICIR × √n          # n = len(ic_series) = 관측 '일수'
    독립 관측 k = n // fwd       # 겹치지 않는 블록 수

`factor_decay.compute_ic_weight_adjustments()` 는 2026-05-23 에 바로 이 사유로 동결됐고
(독시스트링 "유효-N ≈ 6 … overlap, autocorrelation 착시"), 해제 조건을
**"non-overlapping 또는 Newey-West 보정 도달"** 로 적어 두었다.

이 스크립트가 그 조건을 실측한다. 한 번 재고 끝낼 것이 아니라 **주기적으로 다시 재야 한다** —
겹침이 병목이라 달력이 흘러도 유효 N 이 비례해 늘지 않기 때문이다(2026-08-15 실측: 5/23
추정 6 → 8/15 실측 6, 3개월간 불변).

사용
----
    python3 scripts/audit/ic_overlap_check.py            # 표 출력 + 산출물 기록
    python3 scripts/audit/ic_overlap_check.py --dry-run  # 출력만

산출물: data/analysis/ic_overlap_audit.json
  ⚠️ 이건 사전등록(prereg_*) 산출물이 아니라 **측정층 감사**다. 그래도 RULE 12 정합으로
     `_meta` 에 무엇을 쟀는지·무엇을 못 쟀는지 자기 신고한다.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import statistics
import sys
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from api.config import DATA_DIR, now_kst  # noqa: E402
from api.quant.alpha.alpha_scanner import FACTOR_EXTRACTORS, _spearman_rank_corr  # noqa: E402

# alpha_scanner.scan_all_factors 의 lookback 규칙을 그대로 재현
#   LOOKBACK_DAYS = 60 if forward_days <= 30 else int(forward_days * 1.5) + 40
HORIZONS: List[Tuple[int, bool]] = [(7, False), (14, False), (30, False), (63, True)]

MIN_BLOCKS = 3          # 독립 관측 3개 미만 = 표준오차 추정 불가로 판정
T_CRIT = 1.96           # 5% 양측


def _lookback_for(fwd: int) -> int:
    return 60 if fwd <= 30 else int(fwd * 1.5) + 40


def _load_snapshots() -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for f in sorted(glob.glob(os.path.join(DATA_DIR, "history", "*.json"))):
        d = os.path.basename(f)[:-5]
        if len(d) != 10:
            continue
        try:
            out[d] = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def _window(allsnaps: Dict[str, dict], days: int, today: date) -> List[dict]:
    out = []
    for i in range(days, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        if d in allsnaps:
            s = dict(allsnaps[d])
            s["_date"] = d
            out.append(s)
    return out


def ic_series(snaps: List[dict], factor: str, fwd: int, exact: bool) -> List[float]:
    """alpha_scanner.compute_factor_ic 의 IC 계열 산출을 그대로 재현."""
    ex = FACTOR_EXTRACTORS[factor]
    out: List[float] = []
    for i in range(len(snaps) - 1):
        recs = snaps[i].get("recommendations", [])
        if len(recs) < 5:
            continue
        if exact:
            j = i + fwd
            if j >= len(snaps):
                continue
            fut = snaps[j]
        else:
            fut = None
            for j in range(i + 1, min(i + fwd + 1, len(snaps))):
                fut = snaps[j]
            if not fut:
                continue
        fprice: Dict[str, float] = {}
        for r in fut.get("recommendations", []):
            t, p = r.get("ticker", ""), r.get("price")
            if t and p:
                try:
                    fprice[t] = float(p)
                except (TypeError, ValueError):
                    pass
        xs, ys = [], []
        for st in recs:
            tk, pr, fv = st.get("ticker", ""), st.get("price"), ex(st)
            if fv is None or pr is None or tk not in fprice:
                continue
            try:
                p0 = float(pr)
                if p0 <= 0:
                    continue
                xs.append(float(fv))
                ys.append((fprice[tk] - p0) / p0 * 100)
            except (TypeError, ValueError):
                continue
        if len(xs) >= 5:
            out.append(_spearman_rank_corr(xs, ys))
    return out


def judge(ser: List[float], fwd: int) -> Dict[str, Any]:
    """현행 t 와 비겹침 블록 t 를 함께 낸다."""
    n = len(ser)
    if n < 5:
        return {"n": n, "verdict": "표본부족"}
    mu = statistics.mean(ser)
    sd = statistics.stdev(ser)
    t_now = mu / (sd / math.sqrt(n)) if sd > 1e-9 else 0.0
    k = n // fwd
    row: Dict[str, Any] = {
        "ic_mean": round(mu, 5), "n_days": n, "k_independent": k,
        "t_current": round(t_now, 2),
        "overlap_pct": round((fwd - 1) / fwd * 100, 1),
    }
    if k < MIN_BLOCKS:
        row["verdict"] = "추정불가"
        row["why"] = f"독립 관측 {k}개 < {MIN_BLOCKS} — 표준오차를 추정할 표본이 없다"
        return row
    # 시작 오프셋별 비겹침 부분표본의 t 분포 → 중앙값 채택
    ts = []
    for off in range(fwd):
        sub = ser[off::fwd]
        if len(sub) >= 3 and statistics.stdev(sub) > 1e-9:
            ts.append(statistics.mean(sub) / (statistics.stdev(sub) / math.sqrt(len(sub))))
    if not ts:
        row["verdict"] = "추정불가"
        row["why"] = "비겹침 부분표본의 분산이 0"
        return row
    t_ind = statistics.median(ts)
    row["t_nonoverlap"] = round(t_ind, 2)
    row["t_inflation"] = round(abs(t_now) / abs(t_ind), 1) if abs(t_ind) > 1e-9 else None
    row["verdict"] = "유의" if abs(t_ind) >= T_CRIT else "비유의"
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="산출물 미기록")
    args = ap.parse_args()

    allsnaps = _load_snapshots()
    if len(allsnaps) < 10:
        print(f"스냅샷 부족 ({len(allsnaps)}일) — 판정 불가")
        return 1
    today = date.fromisoformat(max(allsnaps))

    factors = sorted(FACTOR_EXTRACTORS)
    results: Dict[str, Dict[str, Any]] = {}

    print(f"스냅샷 {len(allsnaps)}일 · {min(allsnaps)} ~ {max(allsnaps)}")
    print(f"\n{'팩터':17}" + "".join(f"{'fwd'+str(h):>25}" for h, _ in HORIZONS))
    print(f"{'':17}" + "".join(f"{'IC  t현행 t비겹침  k  판정':>25}" for _ in HORIZONS))
    print("─" * 118)

    for f in factors:
        line = f"{f:17}"
        results[f] = {}
        for h, exact in HORIZONS:
            ser = ic_series(_window(allsnaps, _lookback_for(h), today), f, h, exact)
            r = judge(ser, h)
            results[f][f"fwd{h}"] = r
            if r.get("verdict") == "표본부족":
                line += f"{'표본부족':>25}"
            elif r["verdict"] == "추정불가":
                line += f"{r['ic_mean']:+7.3f}{r['t_current']:7.1f}{'  —':>6}{r['k_independent']:3d} 불가"
            else:
                line += (f"{r['ic_mean']:+7.3f}{r['t_current']:7.1f}"
                         f"{r['t_nonoverlap']:7.2f}{r['k_independent']:3d}"
                         f"{'  유의' if r['verdict']=='유의' else '   ·  '}")
        print(line)

    surviving = [(f, h, r) for f, hs in results.items() for h, r in hs.items()
                 if r.get("verdict") == "유의"]
    unestimable = [(f, h) for f, hs in results.items() for h, r in hs.items()
                   if r.get("verdict") == "추정불가"]
    total = sum(len(hs) for hs in results.values())

    print("\n" + "═" * 118)
    print(f"비겹침 판정 통과 {len(surviving)} / 전체 {total}  ·  추정불가 {len(unestimable)}")
    print("═" * 118)
    for f, h, r in sorted(surviving, key=lambda x: -abs(x[2]["t_nonoverlap"])):
        print(f"  {f:17}{h:<6} IC {r['ic_mean']:+.3f}  "
              f"t 현행 {r['t_current']:+6.1f} → 비겹침 {r['t_nonoverlap']:+5.2f}  "
              f"(부풀림 {r['t_inflation']}배)  k={r['k_independent']}")
    if not surviving:
        print("  0건")

    payload = {
        "_meta": {
            "artifact": "ic_overlap_audit",
            "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "score_system": {
                "name": "factor_ic",
                "is_operational": False,
                "note": ("🚨 이 IC 는 실운용 가중치를 움직이지 않는다. "
                         "factor_decay.compute_ic_weight_adjustments() 가 2026-05-23 동결 "
                         "(frozen static dict) 상태다. 다만 significant_factors 는 "
                         "daily/monthly_admin_pdf 와 strategy_evolver 로 나가 PM 판단 입력이 된다."),
            },
            "what_is_measured": (
                "일별 스냅샷 forward IC 의 t 통계량이 창 겹침으로 부풀려진 정도. "
                "독립 관측 k = 관측일수 // 지평."
            ),
            "what_is_NOT_measured": [
                "표본 풀 자체의 자기선택 편향 (일별 recommendations 는 stock_filter 가 "
                "safety_pct 정렬로 뽑은 상위 집합 — safety_score IC 는 이 때문에 해석 불가)",
                "fwd7/14/30 의 horizon truncation (비-exact 경로는 창 끝에서 "
                "실제 지평이 라벨보다 짧아진다)",
                "일별 종목 수 변동(중앙 40, 범위 18~67)이 각 IC 추정치에 주는 분산",
            ],
            "unfreeze_trigger_ref": (
                "api/quant/alpha/factor_decay.py:293 — 재개 trigger "
                "'유효-N 마일스톤 (non-overlapping 또는 Newey-West 보정) 도달'"
            ),
            "min_blocks_for_estimate": MIN_BLOCKS,
            "t_critical": T_CRIT,
        },
        "snapshot_days": len(allsnaps),
        "snapshot_range": [min(allsnaps), max(allsnaps)],
        "summary": {
            "cells_total": total,
            "cells_significant_nonoverlap": len(surviving),
            "cells_unestimable": len(unestimable),
            "unfreeze_trigger_met": len(surviving) > 0 and len(unestimable) < total / 2,
        },
        "factors": results,
    }

    if args.dry_run:
        print("\n--dry-run — 산출물 미기록")
        return 0
    outdir = os.path.join(DATA_DIR, "analysis")
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, "ic_overlap_audit.json")
    with open(outpath, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"\n기록 → {outpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

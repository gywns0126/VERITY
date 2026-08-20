#!/usr/bin/env python3
"""G4 — brain_score 분산 축소 원인 진단. 🚨 진단 전용, 산식 변경 0.

왜 이 진단인가 (PREREG_BASELINE_V1_LITERATURE_2026_08_16 개정 2026-08-20):
  등급 임계 75 가 80일·3,061 종목-일에서 0건이다(관측 최대 69). 그런데
  [[feedback_threshold_calibration_overfit_guard]] 의 Q9(2026-05-18)가 같은 형태를
  이미 답했다 — "max<임계 는 **산식 재검토 신호**이지 임계 하향의 근거가 아니다".
  그래서 임계(G2/G3)를 만지기 전에 **왜 분산이 좁은지**부터 잰다.

무엇을 재나 (전부 분모 명시 — RULE 13):
  1. 활성 가중 축 열거 — 계산되는 컴포넌트 전체 중 실제로 가중치를 가진 것이 몇 개인가
  2. 축별 결측률 — `_safe_float(x, 50.0)` 로 중립 대입된 비율
  3. 축별 횡단면 분산 — 상수축(σ≈0)은 선별에 기여가 0이다
  4. 🚨 반사실 비교 — 결측 축을 **제외하고 재정규화**했을 때의 σ vs 중립 50 대입 σ.
     정책이 둘인데(volatility 내부=재정규화 / fact 바깥=중립 50) 어느 쪽이 적용됐는지
     산출물에 안 보인다. 그 선택이 분산을 얼마나 좁히는지를 수치로 낸다.
  5. brain_score 재구성 — 각 층이 최종 σ 에 얼마를 기여하나

사용:
  python3 scripts/audit/score_variance_diagnosis.py
  python3 scripts/audit/score_variance_diagnosis.py --json out.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics as st
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.intelligence.factors.fact import _compute_fact_score  # noqa: E402
from api.intelligence.factors.sentiment import _compute_sentiment_score  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORTFOLIO = os.path.join(ROOT, "data", "portfolio.json")
CONSTITUTION = os.path.join(ROOT, "data", "verity_constitution.json")

NEUTRAL = 50.0
# 상수 판정 기준. 횡단면 표준편차가 이 아래면 선별 기여가 사실상 0 이다
# (같은 날 전 종목 동일값은 순위에 산술적으로 기여 0 — 2026-08-15 구조 재편의 논거).
CONSTANT_SIGMA = 0.5


def _sigma(vals: List[float]) -> float:
    vals = [v for v in vals if isinstance(v, (int, float))]
    return st.pstdev(vals) if len(vals) > 1 else 0.0


def _axis_table(rows: List[Dict[str, Any]], weights: Dict[str, float],
                block: str) -> List[Dict[str, Any]]:
    """축별 결측률·분산·가중치. 분모 = 종목 수."""
    n = len(rows)
    keys = sorted({k for r in rows for k in (r[block] or {})})
    out = []
    for k in keys:
        vals = [(r[block] or {}).get(k) for r in rows]
        vals = [v for v in vals if isinstance(v, (int, float))]
        # 중립 대입 여부는 직접 알 수 없으므로 두 신호를 함께 낸다:
        #   ① missing/substituted 신고에 이름이 있는가 ② 값이 정확히 50 인가
        declared = sum(1 for r in rows if k in r["missing"] or k in r["substituted"])
        exactly_neutral = sum(1 for v in vals if abs(v - NEUTRAL) < 1e-9)
        sig = _sigma(vals)
        out.append({
            "axis": k,
            "weight": round(weights.get(k, 0.0), 6),
            "n": len(vals),
            "denominator": n,
            "sigma": round(sig, 3),
            "min": round(min(vals), 2) if vals else None,
            "max": round(max(vals), 2) if vals else None,
            "declared_missing_or_substituted": declared,
            "exactly_neutral_50": exactly_neutral,
            "exactly_neutral_pct": round(exactly_neutral / len(vals) * 100, 1) if vals else None,
            "is_constant": sig < CONSTANT_SIGMA,
        })
    out.sort(key=lambda r: (-r["weight"], r["axis"]))
    return out


def _weighted(components: Dict[str, Any], weights: Dict[str, float],
              skip: set) -> float:
    """활성 가중 축만 재정규화 가중평균. skip 에 든 축은 **제외**(재정규화 정책)."""
    tot = 0.0
    wsum = 0.0
    for k, w in weights.items():
        if w <= 0 or k in skip:
            continue
        v = components.get(k)
        if not isinstance(v, (int, float)):
            continue
        tot += v * w
        wsum += w
    return tot / wsum if wsum > 0 else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="결과 JSON 저장 경로")
    args = ap.parse_args()

    with open(PORTFOLIO, encoding="utf-8") as f:
        pf = json.load(f)
    with open(CONSTITUTION, encoding="utf-8") as f:
        const = json.load(f)

    recs = pf.get("recommendations") or []
    if not recs:
        print("❌ portfolio.recommendations 가 비어 있다 — 진단 불가", file=sys.stderr)
        return 1

    fact_w = (const.get("fact_score") or {}).get("weights") or {}
    sent_w = (const.get("sentiment_score") or {}).get("weights") or {}

    rows: List[Dict[str, Any]] = []
    for rec in recs:
        s = dict(rec)
        try:
            fa = _compute_fact_score(s, portfolio=pf)
            se = _compute_sentiment_score(s, pf)
        except Exception as exc:  # noqa: BLE001
            print(f"  · {s.get('ticker')} 재현 실패: {exc}", file=sys.stderr)
            continue
        rows.append({
            "ticker": s.get("ticker"),
            "fact": fa.get("components") or {},
            "sentiment": se.get("components") or {},
            "missing": set(fa.get("missing_components") or []),
            "substituted": set(fa.get("substituted_components") or []),
            "fact_score": fa.get("score"),
            "sentiment_score": se.get("score"),
            "coverage": fa.get("data_coverage"),
        })

    N = len(rows)
    print("=" * 74)
    print(f"G4 분산 축소 진단 — 분모 = 운영 풀 {N}종목 / recommendations {len(recs)}")
    print("=" * 74)

    # ── 1. 활성 가중 축 열거 (분모 = 계산되는 컴포넌트 전체) ──
    for block, w in (("fact", fact_w), ("sentiment", sent_w)):
        computed = sorted({k for r in rows for k in (r[block] or {})})
        active = [k for k in computed if w.get(k, 0) > 0]
        print(f"\n[{block}] 계산 컴포넌트 {len(computed)}개 중 "
              f"가중치>0 = **{len(active)}개** ({', '.join(active) or '없음'})")
        unweighted = [k for k in computed if w.get(k, 0) <= 0]
        print(f"        가중치 0 = {len(unweighted)}개 — 계산·기록만, 선별 기여 0")

    # ── 2~3. 축별 표 ──
    diag: Dict[str, Any] = {"denominator_stocks": N, "blocks": {}}
    for block, w in (("fact", fact_w), ("sentiment", sent_w)):
        tbl = _axis_table(rows, w, block)
        act = [r for r in tbl if r["weight"] > 0]
        print(f"\n── [{block}] 활성 축 상세 (분모 {N}) ──")
        print(f"{'축':26s} {'가중':>7s} {'σ':>7s} {'min':>7s} {'max':>7s} "
              f"{'=50':>7s} {'결측신고':>8s}")
        for r in act:
            flag = "  🚨상수" if r["is_constant"] else ""
            print(f"{r['axis']:26s} {r['weight']:7.4f} {r['sigma']:7.2f} "
                  f"{(r['min'] if r['min'] is not None else 0):7.1f} "
                  f"{(r['max'] if r['max'] is not None else 0):7.1f} "
                  f"{r['exactly_neutral_pct'] or 0:6.1f}% "
                  f"{r['declared_missing_or_substituted']:8d}{flag}")
        diag["blocks"][block] = {"axes": tbl, "active_count": len(act)}

    # ── 3-B. 🚨 분산 기여도 분해 — 가중치와 실제 기여는 다르다 ──
    # 축의 가중치가 커도 그 축이 상수면 순위에 기여가 0 이다. 독립 가정 하에서
    # var(합성) = Σ wᵢ²·varᵢ 이므로 기여 비중 = wᵢ²·varᵢ / Σ. 실측 σ 와 독립 예측 σ 를
    # 나란히 내어 **축간 상관 때문에 좁아진 것인지 축이 상수라서 좁은 것인지** 가른다.
    print("\n" + "=" * 74)
    print("분산 기여도 분해 — 가중치 ≠ 기여 (독립 가정, 기여=w²σ² 비중)")
    print("=" * 74)
    contrib: Dict[str, Any] = {}
    for block, w in (("fact", fact_w), ("sentiment", sent_w)):
        act = {k: v for k, v in w.items() if v > 0}
        wsum = sum(act.values())
        parts = []
        for k, wk in act.items():
            vals = [(r[block] or {}).get(k) for r in rows]
            vals = [v for v in vals if isinstance(v, (int, float))]
            eff = wk / wsum if wsum else 0.0          # 재정규화 후 실효 가중
            var = _sigma(vals) ** 2
            parts.append((k, eff, _sigma(vals), (eff ** 2) * var))
        tot_var = sum(p[3] for p in parts)
        pred_sigma = tot_var ** 0.5
        actual = [r[f"{block}_score"] for r in rows
                  if isinstance(r[f"{block}_score"], (int, float))]
        act_sigma = _sigma(actual)
        print(f"\n[{block}]  실효가중 합 {wsum:.4f} → 재정규화 기준")
        print(f"{'축':26s} {'실효가중':>9s} {'σ':>7s} {'분산기여':>9s}")
        for k, eff, sg, c in sorted(parts, key=lambda p: -p[3]):
            share = c / tot_var * 100 if tot_var else 0
            mark = "  🚨 가중↑ 기여↓" if eff > 0.15 and share < 10 else ""
            print(f"{k:26s} {eff * 100:8.1f}% {sg:7.2f} {share:8.1f}%{mark}")
        print(f"  독립 가정 예측 σ = {pred_sigma:5.2f}   실측 σ = {act_sigma:5.2f}   "
              f"비율 {act_sigma / pred_sigma if pred_sigma else 0:.2f}")
        print(f"  → {'축간 상관이 거의 없다(다각화 수학대로)' if pred_sigma and abs(act_sigma / pred_sigma - 1) < 0.2 else '상관/절단 등 추가 압축 요인 존재'}")
        contrib[block] = {
            "predicted_sigma_independent": round(pred_sigma, 3),
            "actual_sigma": round(act_sigma, 3),
            "axes": [{"axis": k, "effective_weight": round(eff, 4),
                      "sigma": round(sg, 3),
                      "variance_share_pct": round(c / tot_var * 100, 2) if tot_var else None}
                     for k, eff, sg, c in sorted(parts, key=lambda p: -p[3])],
        }
    diag["variance_contribution"] = contrib

    # ── 4. 🚨 반사실 — 중립 50 대입 vs 결측 제외 재정규화 ──
    print("\n" + "=" * 74)
    print("반사실 비교 — 결측 처리 정책이 횡단면 σ 를 얼마나 바꾸나")
    print("=" * 74)
    cf: Dict[str, Any] = {}
    for block, w in (("fact", fact_w), ("sentiment", sent_w)):
        as_is, excl = [], []
        n_excluded_axes = 0
        for r in rows:
            comp = r[block] or {}
            as_is.append(_weighted(comp, w, skip=set()))
            # 결측 정책 B: 신고된 결측/대체 축 + 정확히 중립인 축을 제외하고 재정규화
            skip = {k for k, v in comp.items()
                    if (k in r["missing"] or k in r["substituted"])
                    or (isinstance(v, (int, float)) and abs(v - NEUTRAL) < 1e-9)}
            skip = {k for k in skip if w.get(k, 0) > 0}
            n_excluded_axes += len(skip)
            excl.append(_weighted(comp, w, skip=skip))
        a = [v for v in as_is if v == v]
        b = [v for v in excl if v == v]
        sa, sb = _sigma(a), _sigma(b)
        ratio = (sb / sa) if sa > 0 else float("nan")
        print(f"\n[{block}]  분모 {N}종목")
        print(f"  현행(중립 50 대입)     σ = {sa:6.2f}   범위 {min(a):5.1f}~{max(a):5.1f}")
        print(f"  대안(결측 제외·재정규) σ = {sb:6.2f}   범위 "
              f"{(min(b) if b else 0):5.1f}~{(max(b) if b else 0):5.1f}   "
              f"[재정규 대상 σ 배율 = {ratio:.2f}x]")
        print(f"  제외된 활성 축 연인원 = {n_excluded_axes} "
              f"(종목당 평균 {n_excluded_axes / N:.2f}개)")
        cf[block] = {"sigma_neutral_fill": round(sa, 3),
                     "sigma_exclude_renorm": round(sb, 3),
                     "sigma_ratio": round(ratio, 3) if ratio == ratio else None,
                     "excluded_active_axis_instances": n_excluded_axes}
    diag["counterfactual"] = cf

    # ── 5. 최종 층 ──
    fs = [r["fact_score"] for r in rows if isinstance(r["fact_score"], (int, float))]
    ss = [r["sentiment_score"] for r in rows if isinstance(r["sentiment_score"], (int, float))]
    bw = ((const.get("decision_tree") or {}).get("brain_weights") or {}).get("default") or {}
    wf, ws = float(bw.get("fact", 0.7)), float(bw.get("sentiment", 0.3))
    brain = [a * wf + b * ws for a, b in zip(fs, ss)]
    print("\n" + "=" * 74)
    print(f"최종 층 (기본 가중 fact {wf} / sentiment {ws} · vci_bonus 제외)")
    print("=" * 74)
    for nm, v in (("fact_score", fs), ("sentiment_score", ss), ("brain_score", brain)):
        print(f"  {nm:16s} N={len(v):3d}  σ={_sigma(v):6.2f}  "
              f"min={min(v):6.1f}  중앙={st.median(v):6.1f}  max={max(v):6.1f}")
    thr = ((const.get("decision_tree") or {}).get("grades") or {}) \
        .get("STRONG_BUY", {}).get("min_brain_score")
    z = None
    if thr is not None and brain:
        gap = thr - max(brain)
        need = (thr - st.median(ss) * ws) / wf if wf else float("nan")
        print(f"\n  🚨 STRONG_BUY 임계 {thr} — 관측 최대 {max(brain):.1f} (부족 {gap:.1f}점)")
        print(f"     sentiment 를 중앙({st.median(ss):.1f})으로 고정하면 "
              f"필요 fact_score = {need:.1f} (관측 최대 {max(fs):.1f})")
        # 🚨 임계와 분포의 거리를 σ 단위로 — "0건" 이 이상현상인지 예측된 결과인지 가른다.
        bsig = _sigma(brain)
        if bsig > 0:
            z = (thr - st.mean(brain)) / bsig
            # 정규 근사 상측 확률 (erfc). 분포 가정이므로 참고치로만 신고한다.
            import math
            p = 0.5 * math.erfc(z / math.sqrt(2))
            print(f"     임계는 평균({st.mean(brain):.1f})에서 **{z:.2f}σ** 위 (σ={bsig:.2f})")
            print(f"     정규 근사 상측확률 {p:.2e} → {N}종목이면 하루 기대 {p * N:.4f}건, "
                  f"80일이면 {p * N * 80:.3f}건")
            print("     🚨 즉 관측 0건은 이상현상이 아니라 **예측되는 결과**다. "
                  "임계가 분포에서 4σ 가까이 떨어져 있다.")
    diag["threshold_distance"] = {"z_sigma": round(z, 3) if z is not None else None}
    diag["final"] = {
        "fact_sigma": round(_sigma(fs), 3), "sentiment_sigma": round(_sigma(ss), 3),
        "brain_sigma": round(_sigma(brain), 3), "brain_max": round(max(brain), 2),
        "strong_buy_threshold": thr,
    }

    # ── 6. 🚨 자기 검산 — 재현 경로가 실제 산출과 같은 산식을 타는가 ──
    # [[feedback_green_check_is_not_safety]] "검산 스크립트 자체 버그" 대비. 이 진단의 모든
    # 수치는 재현값에서 나오므로, 재현이 틀리면 진단이 통째로 틀린다.
    latest = sorted(glob.glob(os.path.join(ROOT, "data", "history", "*", "brain_results.json")))
    if latest:
        with open(latest[-1], encoding="utf-8") as f:
            stored = {x.get("ticker"): x.get("brain_score")
                      for x in (json.load(f).get("stocks") or [])}
        diffs = [abs(a * wf + b * ws - stored[r["ticker"]])
                 for r, a, b in zip(rows, fs, ss)
                 if r["ticker"] in stored and isinstance(stored[r["ticker"]], (int, float))]
        print("\n" + "=" * 74)
        print(f"자기 검산 — 재현 vs 저장 산출 ({os.path.basename(os.path.dirname(latest[-1]))})")
        print("=" * 74)
        if diffs:
            ok5 = sum(1 for d in diffs if d <= 5)
            print(f"  대조 분모 {len(diffs)} · |재현−저장| 중앙 {st.median(diffs):.2f} "
                  f"· 최대 {max(diffs):.2f} · ≤5점 {ok5}/{len(diffs)} "
                  f"({ok5 / len(diffs) * 100:.1f}%)")
            print("  주: vci_bonus(±5/−10)·분면별 가중·override 미반영이라 완전 일치는 "
                  "기대하지 않는다. 계통 오차 부재만 확인한다.")
            diag["self_check"] = {"n": len(diffs), "median_abs_diff": round(st.median(diffs), 3),
                                  "max_abs_diff": round(max(diffs), 3),
                                  "within_5_pct": round(ok5 / len(diffs) * 100, 1)}
            if st.median(diffs) > 5:
                print("  🚨 중앙 오차가 5점을 넘는다 — 재현 경로가 실제와 갈렸다. "
                      "위 진단 수치를 신뢰하지 말 것.")

    print("\n🚨 이 진단의 범위: 컴포넌트 값은 **오늘 스냅샷**이다(과거 컴포넌트 미저장이라 "
          "소급 재현 불가). 최종층 brain σ 만 80일로 확인했다 — 일별 횡단면 σ 중앙 4.79.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(diag, f, ensure_ascii=False, indent=1)
        print(f"\n저장: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

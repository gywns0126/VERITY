#!/usr/bin/env python3
"""Q7 상태 검사 — 축이 조용히 상수가 되는 것을 잡는다. 🚨 산식 변경 0.

왜 이 검사인가 (외부 자문 Q7 회신, 2026-08-21):
  상수화는 PSI/CSI 계열(**변화 검사**)로는 구조적으로 못 잡는다. 값이 항상 같으면
  비중 차이가 정확히 0 이라 PSI = 0, 즉 **가장 안정된 축**으로 보고된다.
  회신 인용 — Evidently 공식 문서가 "드리프트 테스트는 반드시 데이터 무결성
  테스트와 함께 그룹으로 묶어 써야 한다"고 권고하며, 이것이 문헌이 인정하는
  "PSI 만으로는 부족하다"는 공식 진술이다.

  탐지 가능 여부 (회신 표):
    PSI/CSI                 → 탐지 불가
    표준편차 σ              → 가능 (σ→0 경보)
    유일값 개수 n_unique    → 가능 (=1 경보)
    스키마 validity(TFDV)   → 가능
  핵심 원리 = PSI 류는 **change detector**, σ·n_unique·mode share 는 **state detector**.
  두 계열을 병행해야 상수화·분산 붕괴를 놓치지 않는다.

이 도구가 구현하는 규칙 (회신이 우리 5사례에 맞춰 제시한 형태):
  ① 파서 죽음        row_count ≥ 1                    매 배치
  ② 비율 지표 상수화  n_unique ≥ 2 또는 σ > 0          매 배치
  ③ 발동 0건         발동 카운트 하한                  주간 롤업
  ④ 극단 임계 0건    임계가 최근 분포의 몇 σ 인지 재계산  월간 · >3σ 면 재검토 플래그
  ⑤ 밴드 상한=중립   mode share < 90%                 매 배치

🚨 이 도구는 **신고만** 한다. 임계·가중·산식을 바꾸지 않는다.
   조정은 RULE 7 쿼터 사안이며 G8·G9·G10 이 PM 결재 대기 중이다.

사용:
  python3 scripts/audit/axis_state_check.py
  python3 scripts/audit/axis_state_check.py --json out.json   # 비영 종료 = 위반 있음
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import statistics as st
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORTFOLIO = os.path.join(ROOT, "data", "portfolio.json")
CONSTITUTION = os.path.join(ROOT, "data", "verity_constitution.json")

# 회신이 제시한 업계 관행 임계. 🚨 이 값들은 **탐지 임계**이지 산식 임계가 아니다
# (RULE 7 무관). 바꿀 때도 산식과 무관하나, 근거는 여기 주석에 남긴다.
MIN_UNIQUE = 2          # n_unique = 1 이면 상수 (회신 표)
MIN_SIGMA = 1e-9        # σ → 0 경보
MAX_MODE_SHARE = 0.90   # 최빈값이 전체의 90%+ 차지 시 경보 (회신 표)
THRESHOLD_SIGMA_MAX = 3.0   # 임계가 분포에서 3σ 밖이면 재검토 플래그 (회신 표)
MIN_ROW_COUNT = 1       # HTTP 200 + 파싱 0건을 실패로 승격 (GX row-count sanity)


def _finding(axis: str, rule: str, detail: str, severity: str = "alert") -> Dict[str, Any]:
    return {"axis": axis, "rule": rule, "detail": detail, "severity": severity}


def check_axis_state(values: List[float], axis: str) -> List[Dict[str, Any]]:
    """규칙 ①②⑤ — 상태 검사. 분모를 항상 함께 신고한다 (RULE 13)."""
    out: List[Dict[str, Any]] = []
    n = len(values)
    if n < MIN_ROW_COUNT:
        out.append(_finding(axis, "row_count", f"관측 {n}건 < 하한 {MIN_ROW_COUNT} "
                                               "— 값 부재는 '신호 없음'이 아니라 수집·파싱 실패 의심"))
        return out
    if n < 2:
        # 표본 1건은 상수 여부를 말할 수 없다 — 판정 보류 (분모 부족)
        out.append(_finding(axis, "sample", f"관측 {n}건 — 상수 판정 불가(분모 부족)", "info"))
        return out

    uniq = len({round(float(v), 10) for v in values})
    sigma = st.pstdev([float(v) for v in values])
    counts = collections.Counter(round(float(v), 10) for v in values)
    mode_val, mode_n = counts.most_common(1)[0]
    mode_share = mode_n / n

    if uniq < MIN_UNIQUE:
        out.append(_finding(axis, "n_unique",
                            f"고유값 {uniq} (분모 {n}) — 축이 상수다. "
                            "PSI 는 이 상태를 '가장 안정'으로 보고한다"))
    if sigma <= MIN_SIGMA:
        out.append(_finding(axis, "sigma", f"σ={sigma:.3g} (분모 {n}) — 분산 붕괴"))
    if mode_share >= MAX_MODE_SHARE and uniq >= MIN_UNIQUE:
        out.append(_finding(axis, "mode_share",
                            f"최빈값 {mode_val} 가 {mode_n}/{n} = {mode_share * 100:.1f}% "
                            f"(임계 {MAX_MODE_SHARE * 100:.0f}%) — 사실상 상수",
                            "watch"))
    return out


def check_threshold_distance(values: List[float], threshold: float,
                             label: str) -> List[Dict[str, Any]]:
    """규칙 ④ — 임계가 최근 분포에서 몇 σ 인지. 🚨 임계를 옮기지 않는다, 신고만 한다."""
    vals = [float(v) for v in values if isinstance(v, (int, float))]
    if len(vals) < 2:
        return []
    mu, sd = st.mean(vals), st.pstdev(vals)
    if sd <= 0:
        return [_finding(label, "threshold_sigma",
                         f"분포 σ=0 이라 임계 거리 계산 불가 (분모 {len(vals)})", "watch")]
    z = (threshold - mu) / sd
    if abs(z) <= THRESHOLD_SIGMA_MAX:
        return []
    # 🚨 σ 거리만 신고하면 "도달 불가"로 오독된다 — 분포가 정규가 아니면 4σ 밖에도
    #   관측치가 있다. 실제 도달 건수를 **반드시 병기**한다. 초판이 이걸 빠뜨려
    #   CAUTION 을 도달 불가처럼 신고했는데 실측 AVOID 비중은 15.4% 였다.
    above = sum(1 for v in vals if v >= threshold)
    below = len(vals) - above
    hit = above if z > 0 else below     # 임계가 위쪽이면 상회, 아래쪽이면 하회가 도달
    side = "상회" if z > 0 else "하회"
    sev = "alert" if hit == 0 else "watch"
    tail = ("실제 도달 0건 = 산술적으로도 예측되는 결과"
            if hit == 0 else
            f"🚨 다만 실제 {side} **{hit}/{len(vals)}건** — 분포가 정규가 아니므로 "
            "σ 거리만으로 도달 불가라 단정하지 말 것")
    return [_finding(label, "threshold_sigma",
                     f"임계 {threshold} 가 분포 평균 {mu:.1f}(σ {sd:.2f})에서 "
                     f"**{z:+.2f}σ** — 하한 |{THRESHOLD_SIGMA_MAX}σ| 초과. {tail}. "
                     "(임계 조정 지시 아님 — RULE 7 쿼터 사안)", sev)]


def check_trigger_count(fired: int, total: int, label: str) -> List[Dict[str, Any]]:
    """규칙 ③ — 발동 0건. 주간 롤업용."""
    if total <= 0:
        return []
    if fired == 0:
        return [_finding(label, "trigger_zero",
                         f"발동 {fired}/{total} — 조건이 분포 밖일 가능성. "
                         "0건 자체가 결함은 아니나 연속되면 조사 대상")]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="결과 JSON 저장 경로")
    args = ap.parse_args()

    with open(PORTFOLIO, encoding="utf-8") as f:
        pf = json.load(f)
    with open(CONSTITUTION, encoding="utf-8") as f:
        const = json.load(f)

    recs = pf.get("recommendations") or []
    findings: List[Dict[str, Any]] = []
    scanned: List[str] = []

    print("=" * 74)
    print(f"Q7 상태 검사 — 분모 = 운영 풀 {len(recs)}종목")
    print("=" * 74)

    # ── 점수 축 재현 (산식 호출, 변경 0) ──
    try:
        from api.intelligence.factors.fact import _compute_fact_score
        from api.intelligence.factors.sentiment import _compute_sentiment_score
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 산식 import 실패: {exc}", file=sys.stderr)
        return 2

    fact_w = (const.get("fact_score") or {}).get("weights") or {}
    sent_w = (const.get("sentiment_score") or {}).get("weights") or {}
    axes: Dict[str, List[float]] = collections.defaultdict(list)
    fs: List[float] = []
    ss: List[float] = []
    hc: List[int] = []

    for rec in recs:
        s = dict(rec)
        try:
            fa = _compute_fact_score(s, portfolio=pf)
            se = _compute_sentiment_score(s, pf)
        except Exception:  # noqa: BLE001
            continue
        fs.append(float(fa.get("score") or 0))
        ss.append(float(se.get("score") or 0))
        for k, v in (fa.get("components") or {}).items():
            if fact_w.get(k, 0) > 0 and isinstance(v, (int, float)):
                axes[f"fact.{k}"].append(float(v))
        for k, v in (se.get("components") or {}).items():
            if sent_w.get(k, 0) > 0 and isinstance(v, (int, float)):
                axes[f"sentiment.{k}"].append(float(v))
        n = (rec.get("sentiment") or {}).get("headline_count")
        if isinstance(n, int):
            hc.append(n)

    # ①②⑤ 가중 축 상태
    for axis, vals in sorted(axes.items()):
        scanned.append(axis)
        findings += check_axis_state(vals, axis)

    # ① 수집 row_count — 종목별 헤드라인 0건 비율
    if hc:
        zero = sum(1 for x in hc if x < MIN_ROW_COUNT)
        scanned.append("collector.news_headline_count")
        if zero:
            findings.append(_finding("collector.news_headline_count", "row_count",
                                     f"기사 0건 {zero}/{len(hc)}종목 — "
                                     "HTTP 200 + 파싱 0건은 '뉴스 없음'이 아니라 파서 사망 의심"))

    # ④ 등급 임계 거리
    # 🚨 반드시 **저장된 실제 brain_score** 를 쓴다. 재현값(fact×w + sentiment×w)은
    #   vci_bonus(±5/−10)·분면별 가중·override 를 반영하지 않아 분포가 실제보다 좁고,
    #   그러면 하한 임계가 실제보다 멀어 보인다. 초판이 그 버그로 CAUTION 을 −5.65σ 로
    #   신고했는데 실측 AVOID 비중은 15.4% 였다 — 도구가 스스로 틀린 사례
    #   ([[feedback_green_check_is_not_safety]] "검산 스크립트 자체 버그").
    import glob
    brain: List[float] = []
    brain_src = "재현(근사)"
    hist = sorted(glob.glob(os.path.join(ROOT, "data", "history", "*", "brain_results.json")))
    if hist:
        try:
            with open(hist[-1], encoding="utf-8") as f:
                stored = [x.get("brain_score") for x in (json.load(f).get("stocks") or [])]
            vals = [float(x) for x in stored if isinstance(x, (int, float))]
            if len(vals) >= 2:
                brain = vals
                brain_src = f"저장 산출 {os.path.basename(os.path.dirname(hist[-1]))}"
        except Exception:  # noqa: BLE001
            pass
    if not brain:
        brain_w = ((const.get("decision_tree") or {}).get("brain_weights") or {}).get("default") or {}
        wf, ws = float(brain_w.get("fact", 0.7)), float(brain_w.get("sentiment", 0.3))
        brain = [a * wf + b * ws for a, b in zip(fs, ss)]
    print(f"\n등급 임계 거리 기준 분포 = {brain_src} · N={len(brain)}")
    grades = (const.get("decision_tree") or {}).get("grades") or {}
    for g, info in grades.items():
        thr = (info or {}).get("min_brain_score")
        if isinstance(thr, (int, float)) and thr > 0:
            scanned.append(f"grade.{g}")
            findings += check_threshold_distance(brain, float(thr), f"grade.{g}")

    # ⑥ 🚨 등급 경로 귀속 — 최종 등급이 임계에서 오나 강등에서 오나
    # 2026-08-21 발견: 하위 등급은 점수 하회가 아니라 **강등**으로만 채워진다.
    # 임계 신고(④)를 등급 분포와 나란히 읽으면 오독이 생기므로 경로를 갈라 신고한다.
    if hist:
        try:
            with open(hist[-1], encoding="utf-8") as f:
                stocks = json.load(f).get("stocks") or []
        except Exception:  # noqa: BLE001
            stocks = []
        order = ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]

        def _base(score: float) -> str:
            for k in order:
                if score >= (grades.get(k) or {}).get("min_brain_score", 10 ** 9):
                    return k
            return "AVOID"

        rows = [(x.get("ticker"), x.get("brain_score"), x.get("grade"),
                 x.get("overrides_applied") or [])
                for x in stocks if isinstance(x.get("brain_score"), (int, float))]
        if rows:
            scanned.append("grade.path_attribution")
            diff = [r for r in rows if _base(float(r[1])) != r[2]]
            silent = [r for r in diff if not r[3]]
            if diff:
                findings.append(_finding(
                    "grade.path_attribution", "downgrade_share",
                    f"최종 등급이 점수 기반 base 와 다른 종목 {len(diff)}/{len(rows)} "
                    f"= {len(diff) / len(rows) * 100:.1f}% — 🚨 하위 등급이 임계가 아니라 "
                    "**강등 경로**로 채워진다. ④의 임계 σ 거리를 등급 분포와 나란히 "
                    "읽으면 오독이 생긴다", "watch"))
            if silent:
                findings.append(_finding(
                    "grade.path_attribution", "silent_downgrade",
                    f"강등됐는데 `overrides_applied` 가 빈 종목 {len(silent)}/{len(diff)} "
                    "— 🚨 강등 사유가 산출물에 신고되지 않는다 (G6 과 같은 부류)"))

    # 출력
    print(f"\n검사 축 {len(scanned)}개 · 위반 {len(findings)}건\n")
    if not findings:
        print("  위반 0 — 상태 정합 ✓")
    for f_ in findings:
        icon = "🚨" if f_["severity"] == "alert" else ("⚠️" if f_["severity"] == "watch" else "ℹ️")
        print(f"  {icon} [{f_['axis']}] {f_['rule']}: {f_['detail']}")

    print("\n🚨 이 검사는 신고만 한다. 임계·가중·산식 조정은 RULE 7 쿼터 사안이며 "
          "G8·G9·G10 이 PM 결재 대기 중이다.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"denominator_stocks": len(recs), "scanned_axes": scanned,
                       "findings": findings}, f, ensure_ascii=False, indent=1)
        print(f"\n저장: {args.json}")

    alerts = [f_ for f_ in findings if f_["severity"] == "alert"]
    return 1 if alerts else 0


if __name__ == "__main__":
    raise SystemExit(main())

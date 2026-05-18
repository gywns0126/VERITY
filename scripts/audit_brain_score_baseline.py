"""brain audit baseline — daily_full 마다 brain_score 분포 + component fill 측정.

2026-05-18 박힘 — docs/BRAIN_SCORE_AUDIT_20260518.md audit cycle 영속화.
PM 명령 (5/18 12:40 KST) — A1 fix 후 16:07 daily_full 효과 자동 측정 + jsonl 누적.

입력 ([[feedback_scheduled_routine_input_first]]):
  - data/portfolio.json (writer: api/main.py daily_analysis_full)

출력:
  - data/metadata/brain_audit.jsonl (append, writer: 본 script)
  - stderr 명시 (logged=True 정합, [[feedback_data_collection_verification_mandatory]])

측정 metric:
  - brain_score 분포 (min/p25/median/p75/max/mean, N)
  - grade 분포 (STRONG_BUY/BUY/WATCH/CAUTION/AVOID)
  - component fill rate (8종 fact_score component)
  - quadrant 분포 (분면별 종목 수)
  - brain_weights 분포 (unique (fact, sent) 튜플)
  - external_risk fill (perplexity_risk top-N propagate 측정)

비고:
  - 시계열 비교는 jsonl 마지막 N entries 자체 read 로 외부 진단 시 가능
  - 알림 X (RULE 7 — N=25 단계는 "(가설)" 명시 의무, 자동 알림은 sample 누적 후)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(_REPO_ROOT, "data", "portfolio.json")
AUDIT_PATH = os.path.join(_REPO_ROOT, "data", "metadata", "brain_audit.jsonl")

# 8 fact_score component (audit doc §3 기준)
FACT_COMPONENTS = [
    "commodity_margin",
    "dart_business_analysis",
    "external_risk",
    "analyst_report_summary",
    "dart_financials",
    "sec_financials",
    "kis_financial_ratio",
    "backtest",
]


def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    k = (n - 1) * p
    f = int(k)
    c = min(f + 1, n - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _load_portfolio() -> Optional[Dict[str, Any]]:
    try:
        with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"[brain_audit] portfolio.json load fail: {e}\n")
        return None


def measure(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    recs = portfolio.get("recommendations", []) or []
    n = len(recs)
    out: Dict[str, Any] = {"n_total": n}

    # brain_score 분포
    scores: List[float] = []
    for s in recs:
        vb = s.get("verity_brain") or {}
        sc = vb.get("brain_score")
        if isinstance(sc, (int, float)):
            scores.append(float(sc))
    if scores:
        out["brain_score"] = {
            "n": len(scores),
            "min": round(min(scores), 2),
            "p25": round(_percentile(scores, 0.25) or 0, 2),
            "median": round(_percentile(scores, 0.5) or 0, 2),
            "p75": round(_percentile(scores, 0.75) or 0, 2),
            "max": round(max(scores), 2),
            "mean": round(sum(scores) / len(scores), 2),
        }
    else:
        out["brain_score"] = {"n": 0}

    # grade 분포
    grade_counts: Dict[str, int] = {}
    for s in recs:
        g = (s.get("verity_brain") or {}).get("grade") or "UNKNOWN"
        grade_counts[g] = grade_counts.get(g, 0) + 1
    out["grade"] = grade_counts

    # component fill rate
    fill: Dict[str, Dict[str, int]] = {}
    kr_recs = [s for s in recs if s.get("currency") != "USD"]
    us_recs = [s for s in recs if s.get("currency") == "USD"]
    for comp in FACT_COMPONENTS:
        n_filled = sum(1 for s in recs if s.get(comp))
        n_kr = sum(1 for s in kr_recs if s.get(comp))
        n_us = sum(1 for s in us_recs if s.get(comp))
        fill[comp] = {
            "total": f"{n_filled}/{n}",
            "kr": f"{n_kr}/{len(kr_recs)}",
            "us": f"{n_us}/{len(us_recs)}",
        }
    out["component_fill"] = fill

    # quadrant 분포 (verity_brain.brain_weights.quadrant 경로 확정)
    quadrant_counts: Dict[str, int] = {}
    for s in recs:
        vb = s.get("verity_brain") or {}
        w = vb.get("brain_weights") or {}
        q = w.get("quadrant") or vb.get("quadrant") or "UNKNOWN"
        quadrant_counts[q] = quadrant_counts.get(q, 0) + 1
    out["quadrant"] = quadrant_counts

    # brain_weights 분포 (fact, sentiment 키 — verity_brain.py 정합)
    weight_counts: Dict[str, int] = {}
    for s in recs:
        vb = s.get("verity_brain") or {}
        w = vb.get("brain_weights") or {}
        if w:
            key = f"({w.get('fact', '?')},{w.get('sentiment', '?')})"
            weight_counts[key] = weight_counts.get(key, 0) + 1
    out["brain_weights"] = weight_counts

    return out


def append_jsonl(entry: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        sys.stderr.write(f"[brain_audit] logged=True path={AUDIT_PATH}\n")
    except OSError as e:
        sys.stderr.write(f"[brain_audit] jsonl write fail: {e}\n")


def main() -> int:
    portfolio = _load_portfolio()
    if portfolio is None:
        sys.stderr.write("[brain_audit] portfolio.json 부재 — skip\n")
        return 0

    try:
        measurements = measure(portfolio)
    except Exception as e:
        sys.stderr.write(f"[brain_audit] measure fail: {e}\n")
        return 0
    finally:
        pass

    entry = {
        "ts_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "portfolio_mtime": datetime.fromtimestamp(
            os.path.getmtime(PORTFOLIO_PATH), KST
        ).isoformat(timespec="seconds"),
        **measurements,
    }
    append_jsonl(entry)

    # stdout 1줄 요약 (cron 로그 빠른 view)
    bs = measurements.get("brain_score") or {}
    grade = measurements.get("grade") or {}
    print(
        f"[brain_audit] N={measurements.get('n_total')} "
        f"brain_score(min={bs.get('min')} med={bs.get('median')} "
        f"max={bs.get('max')} mean={bs.get('mean')}) "
        f"BUY={grade.get('BUY', 0)} STRONG_BUY={grade.get('STRONG_BUY', 0)} "
        f"WATCH={grade.get('WATCH', 0)} CAUTION={grade.get('CAUTION', 0)} "
        f"AVOID={grade.get('AVOID', 0)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

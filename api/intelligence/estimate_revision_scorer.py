"""estimate_revision_scorer — 컨센서스 EPS 리비전 모멘텀 (A2, SHADOW only).

목적 (2026-06-15): eps_estimate_snapshot.py 가 5/4~ 일일 누적해온 PIT EPS estimate
스냅샷(data/metadata/eps_estimates.jsonl)에서 **리비전 모멘텀 신호**를 산출한다.
생산자 모듈 주석대로("revision_score 산출 로직은 본 모듈에 없음 — Sprint 1") 점수화만 빠져
있었다. 데이터 레이어 신규 0 — 순수 계산.

🚨 SHADOW ONLY — brain 점수/등급/추천에 입력 0. 별도 trail 적재만.
🚨 UNIVERSE MISMATCH (적대적 검증 2026-06-14 핵심 발견): 우리 universe = US 메가캡 40종목.
   리비전 drift 엣지는 microcap 에서 생존하고 **메가캡에서 통계 유의성 소멸**(ex-microcap
   t 2.18 → 1.43). 즉 이 신호는 "엣지 있을 것"이 아니라 "문헌의 megacap-decay 가 우리 데이터
   에서도 맞는지 N 누적으로 확인"하는 관측 목적. wire = N≥252(2027) IC 게이트 + 별도 PM 승인.

PIT 정합 ([[feedback_real_call_over_llm_consensus]] / 검증 "yfinance backfill 금지"):
   리비전 = yfinance 의 "30daysAgo" 필드(복원·재기재 위험) 대신, **우리가 그 시점에 기록한
   current 값**(자체 trail PIT)과 현재 current 의 차이로 산출. 자체 trail 부족 시 insufficient.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

EPS_TRAIL = os.path.join(DATA_DIR, "metadata", "eps_estimates.jsonl")
SHADOW_OUT = os.path.join(DATA_DIR, "metadata", "revision_momentum_shadow.jsonl")

# 리비전 산출에 쓰는 forward 기간 (연간이 분기보다 안정 — 분기는 노이즈 큼).
_FWD_PERIODS = ["0y", "+1y"]
# PIT 리비전 윈도: 현재 vs ~N일 전 자체 스냅샷. 가용 범위 내 가장 근접.
_REVISION_WINDOW_DAYS = 30
_MIN_PRIOR_GAP_DAYS = 14   # 최소 이 정도는 떨어진 과거 스냅샷이어야 의미 있는 리비전

_UNIVERSE_CAVEAT = (
    "SHADOW-only. universe=US megacap 40 → 리비전 엣지 통계 유의성 소멸 구간"
    "(megacap t 2.18→1.43, 2026-06-14 검증). 관측 목적=megacap-decay 가설 확인. "
    "brain-input 0. wire=N>=252 IC 게이트+PM 승인."
)


def _load_trail() -> Dict[str, List[Dict[str, Any]]]:
    """ticker → snapshot_date 오름차순 PIT 스냅샷 리스트."""
    by_ticker: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    if not os.path.exists(EPS_TRAIL):
        return by_ticker
    with open(EPS_TRAIL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("invalidate"):
                continue
            t = d.get("ticker")
            if t and d.get("snapshot_date"):
                by_ticker[t].append(d)
    for t in by_ticker:
        by_ticker[t].sort(key=lambda x: x.get("snapshot_date", ""))
    return by_ticker


def _eps_current(snap: Dict[str, Any], period: str) -> Optional[float]:
    et = snap.get("eps_trend") or {}
    pv = et.get(period) or {}
    v = pv.get("current")
    return float(v) if isinstance(v, (int, float)) else None


def _find_prior(snaps: List[Dict[str, Any]], latest_date: date) -> Optional[Dict[str, Any]]:
    """latest 기준 ~30일 전(>=14일 떨어진) 가장 근접한 과거 스냅샷."""
    target = latest_date.toordinal() - _REVISION_WINDOW_DAYS
    best, best_gap = None, None
    for s in snaps:
        try:
            sd = date.fromisoformat(s["snapshot_date"]).toordinal()
        except Exception:
            continue
        gap_from_latest = latest_date.toordinal() - sd
        if gap_from_latest < _MIN_PRIOR_GAP_DAYS:
            continue  # 너무 최근 = 리비전 의미 없음
        dist = abs(sd - target)
        if best_gap is None or dist < best_gap:
            best, best_gap = s, dist
    return best


def _ticker_revision(snaps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """단일 종목 PIT 리비전 모멘텀. 자체 trail 부족 시 insufficient."""
    if len(snaps) < 2:
        return {"status": "insufficient", "reason": "스냅샷 <2"}
    latest = snaps[-1]
    try:
        latest_date = date.fromisoformat(latest["snapshot_date"])
    except Exception:
        return {"status": "insufficient", "reason": "snapshot_date 파싱 불가"}

    prior = _find_prior(snaps, latest_date)
    if prior is None:
        return {"status": "insufficient", "reason": f"{_MIN_PRIOR_GAP_DAYS}일+ 과거 스냅샷 부재"}

    per_period: Dict[str, Optional[float]] = {}
    revs: List[float] = []
    for p in _FWD_PERIODS:
        cur = _eps_current(latest, p)
        old = _eps_current(prior, p)
        if cur is None or old is None or abs(old) < 1e-9:
            per_period[p] = None
            continue
        rev = (cur - old) / abs(old)   # 부호: + = 상향 리비전 = bullish 가설
        per_period[p] = round(rev, 5)
        revs.append(rev)

    if not revs:
        return {"status": "insufficient", "reason": "유효 EPS period 0"}

    score = sum(revs) / len(revs)
    # clustering: 기간 간 부호 일치도 (전부 동방향 = 강한 신호)
    pos = sum(1 for r in revs if r > 0)
    neg = sum(1 for r in revs if r < 0)
    cluster_agree = max(pos, neg) / len(revs)

    return {
        "status": "ok",
        "revision_score": round(score, 5),
        "direction": "up" if score > 0 else ("down" if score < 0 else "flat"),
        "per_period": per_period,
        "cluster_agreement": round(cluster_agree, 3),
        "n_periods": len(revs),
        "latest_date": latest["snapshot_date"],
        "prior_date": prior["snapshot_date"],
        "window_days": latest_date.toordinal() - date.fromisoformat(prior["snapshot_date"]).toordinal(),
    }


def compute_revision_scores() -> Dict[str, Any]:
    """전 종목 리비전 모멘텀 (SHADOW). brain 미입력."""
    trail = _load_trail()
    scores: Dict[str, Any] = {}
    ok = 0
    for ticker, snaps in trail.items():
        r = _ticker_revision(snaps)
        scores[ticker] = r
        if r.get("status") == "ok":
            ok += 1
    return {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "universe_size": len(trail),
        "scored_ok": ok,
        "caveat": _UNIVERSE_CAVEAT,
        "scores": scores,
    }


def run_shadow() -> Dict[str, Any]:
    """리비전 점수 산출 → revision_momentum_shadow.jsonl 적재(brain 무입력) → 요약 반환."""
    result = compute_revision_scores()
    # 슬림 엔트리만 적재 (종목별 score + 메타)
    entry = {
        "ts_kst": now_kst().isoformat(),
        "universe_size": result["universe_size"],
        "scored_ok": result["scored_ok"],
        "shadow": True,
        "brain_input": False,
        "caveat": _UNIVERSE_CAVEAT,
        "scores": {
            t: {"revision_score": s.get("revision_score"), "direction": s.get("direction"),
                "cluster_agreement": s.get("cluster_agreement")}
            for t, s in result["scores"].items() if s.get("status") == "ok"
        },
    }
    try:
        os.makedirs(os.path.dirname(SHADOW_OUT), exist_ok=True)
        with open(SHADOW_OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return result


if __name__ == "__main__":
    r = run_shadow()
    print(f"[revision_momentum] SHADOW — universe {r['universe_size']} / scored {r['scored_ok']}")
    print(f"  ⚠ {r['caveat']}")
    ok = [(t, s["revision_score"], s["direction"], s["cluster_agreement"])
          for t, s in r["scores"].items() if s.get("status") == "ok"]
    ok.sort(key=lambda x: x[1], reverse=True)
    print(f"  상위 상향 리비전:")
    for t, sc, d, ca in ok[:5]:
        print(f"    {t:8} score={sc:+.4f} {d} cluster={ca}")
    print(f"  하위 하향 리비전:")
    for t, sc, d, ca in ok[-5:]:
        print(f"    {t:8} score={sc:+.4f} {d} cluster={ca}")

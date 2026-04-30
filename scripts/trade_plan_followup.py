"""
trade_plan_v0_log.jsonl 의 진입 후보들에 대해 5/14/30일 사후 추적 데이터를 채워넣는다.

매일 1회 실행 (cron). 각 row 의 horizons=[5,14,30] 에 대해:
  - row.suggested_at 으로부터 calendar day 경과 ≥ horizon
  - row.followups[f"h{horizon}"] 미존재
  → 오늘 시점의 가격·verdict 를 followups 에 기록.

가격·verdict 출처: data/recommendations.json (가장 최근 분석 결과).
N일 거래일 정밀화는 v1 에서. 현재는 calendar day 근사 + "오늘 시점 기록".

horizon=30 채워지면 케이스 자동 종료 (close_reason='horizon_30d').
A 단계에서 회귀 분석할 때 row.snapshot 과 followups 를 페어로 사용.
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(ROOT, "data", "metadata", "trade_plan_v0_log.jsonl")
REC_PATH = os.path.join(ROOT, "data", "recommendations.json")


def _load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _save_jsonl(path: str, rows: list[dict]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _load_current_map() -> dict[str, dict]:
    if not os.path.exists(REC_PATH):
        return {}
    try:
        with open(REC_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, list):
        return {}
    out: dict[str, dict] = {}
    for r in data:
        t = r.get("ticker")
        if not t:
            continue
        out[t] = {
            "price": r.get("current_price") or r.get("price"),
            "verdict": r.get("recommendation"),
            "multi_score": (r.get("multi_factor") or {}).get("multi_score"),
        }
    return out


def main() -> int:
    rows = _load_jsonl(LOG_PATH)
    if not rows:
        print(f"[followup] empty log: {LOG_PATH}")
        return 0

    cur_map = _load_current_map()
    if not cur_map:
        print(f"[followup] no current data at {REC_PATH}")
        return 1

    now = datetime.now(timezone.utc)
    n_filled = 0
    n_closed = 0
    n_missing = 0

    for row in rows:
        ticker = row.get("ticker")
        suggested_at_s = row.get("suggested_at")
        if not ticker or not suggested_at_s:
            continue
        try:
            suggested_at = datetime.fromisoformat(suggested_at_s.replace("Z", "+00:00"))
        except Exception:
            continue

        days_elapsed = (now - suggested_at).total_seconds() / 86400.0
        followups = row.setdefault("followups", {})
        horizons = row.get("horizons") or [5, 14, 30]

        cur = cur_map.get(ticker)
        if not cur:
            n_missing += 1
            continue

        ref_price = (row.get("entry_zone") or {}).get("low")
        if ref_price is None:
            ref_price = (row.get("snapshot") or {}).get("price")

        for h in horizons:
            key = f"h{h}"
            if key in followups:
                continue
            if days_elapsed < h:
                continue
            cur_price = cur.get("price")
            if cur_price is None or ref_price is None:
                continue
            ret_pct = (float(cur_price) - float(ref_price)) / float(ref_price) * 100.0
            followups[key] = {
                "price": cur_price,
                "return_pct": round(ret_pct, 2),
                "verdict": cur.get("verdict"),
                "multi_score": cur.get("multi_score"),
                "filled_at": now.isoformat(),
                "days_actual": round(days_elapsed, 1),
            }
            n_filled += 1

        if "h30" in followups and not row.get("closed_at"):
            row["closed_at"] = now.isoformat()
            row["close_reason"] = "horizon_30d"
            n_closed += 1

    _save_jsonl(LOG_PATH, rows)
    print(f"[followup] filled={n_filled} closed={n_closed} missing_ticker={n_missing} total_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

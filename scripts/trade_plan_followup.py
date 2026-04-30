"""
trade_plan_v0_log.jsonl 의 진입 후보들에 대해 5/14/30일 사후 추적 데이터를 채워넣는다.

매일 1회 실행 (cron). 각 row 의 horizons=[5,14,30] 에 대해:
  - row.suggested_at 으로부터 calendar day 경과 ≥ horizon
  - row.followups[f"h{horizon}"] 미존재
  → 오늘 시점의 가격·verdict 를 followups 에 기록.

가격·verdict 출처: data/recommendations.json (가장 최근 분석 결과).
N일 거래일 정밀화는 v1 에서. 현재는 calendar day 근사 + "오늘 시점 기록".

look-ahead bias 보정 (Sprint 11 결함 1 후속, 2026-05-01):
  ref_price = row.suggested_at 다음 영업일 (T+1) snapshot 의 ticker 가격.
  T+1 snapshot 미존재 시 entry_zone.low fallback (구버전 호환).
  보정값은 row.ref_price_t_plus_1 컬럼에 영구 저장 (idempotency).

horizon=30 채워지면 케이스 자동 종료 (close_reason='horizon_30d').
A 단계에서 회귀 분석할 때 row.snapshot 과 followups 를 페어로 사용.
"""
from __future__ import annotations
import glob
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(ROOT, "data", "metadata", "trade_plan_v0_log.jsonl")
REC_PATH = os.path.join(ROOT, "data", "recommendations.json")
HISTORY_DIR = os.path.join(ROOT, "data", "history")


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


def _list_snapshot_dates() -> list[str]:
    if not os.path.isdir(HISTORY_DIR):
        return []
    files = glob.glob(os.path.join(HISTORY_DIR, "*.json"))
    dates = sorted(os.path.basename(f).replace(".json", "") for f in files
                   if not os.path.basename(f).startswith("runs"))
    return dates


def _next_business_snapshot_date(rec_date: str, available: list[str]) -> str | None:
    try:
        rd = datetime.strptime(rec_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    for d_str in available:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
            if d > rd:
                return d_str
        except ValueError:
            continue
    return None


def _t_plus_1_price(ticker: str, suggested_at_iso: str, available: list[str]) -> float | None:
    """suggested_at 다음 영업일 snapshot 에서 ticker 가격 fetch.
    Look-ahead bias 보정 — 사용자 매수 가능 가격 근사.
    """
    if not ticker or not available:
        return None
    try:
        rec_date = datetime.fromisoformat(suggested_at_iso.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return None
    next_date = _next_business_snapshot_date(rec_date, available)
    if not next_date:
        return None
    snap_path = os.path.join(HISTORY_DIR, f"{next_date}.json")
    try:
        with open(snap_path, "r", encoding="utf-8") as f:
            snap = json.loads(f.read().replace("NaN", "null"))
    except Exception:
        return None
    for r in snap.get("recommendations", []) or []:
        if r.get("ticker") == ticker:
            p = r.get("current_price") or r.get("price")
            try:
                return float(p) if p else None
            except (TypeError, ValueError):
                return None
    return None


def main() -> int:
    rows = _load_jsonl(LOG_PATH)
    if not rows:
        print(f"[followup] empty log: {LOG_PATH}")
        return 0

    cur_map = _load_current_map()
    if not cur_map:
        print(f"[followup] no current data at {REC_PATH}")
        return 1

    snapshot_dates = _list_snapshot_dates()
    now = datetime.now(timezone.utc)
    n_filled = 0
    n_closed = 0
    n_missing = 0
    n_t1_filled = 0

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

        # Look-ahead bias 보정: T+1 시가 우선. 영구 컬럼에 저장 (idempotency).
        if "ref_price_t_plus_1" not in row:
            t1 = _t_plus_1_price(ticker, suggested_at_s, snapshot_dates)
            if t1 is not None:
                row["ref_price_t_plus_1"] = t1
                n_t1_filled += 1

        ref_price = row.get("ref_price_t_plus_1")
        if ref_price is None:
            # T+1 snapshot 없으면 (suggested 직후 cron 미발생, 너무 최신) entry_zone.low fallback
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
    print(f"[followup] filled={n_filled} closed={n_closed} missing_ticker={n_missing} t1_corrected={n_t1_filled} total_rows={len(rows)}")

    # followup 후 즉시 메타-검증 갱신 (data/metadata/trade_plan_meta.json).
    try:
        sys.path.insert(0, ROOT)
        from api.observability.trade_plan_meta_validation import summarize, persist
        meta = summarize(LOG_PATH)
        persist(meta)
        print(f"[meta] status={meta.get('status')} · total={meta.get('sample_size', {}).get('total', 0)}")
    except Exception as e:
        print(f"[meta] update skipped: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

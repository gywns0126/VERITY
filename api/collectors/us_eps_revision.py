"""us_eps_revision — 미장 애널리스트 추정치 **리비전** 관측. 2026-08-09 신설 (트랙 A2).

**왜 신설했나.** `api/collectors/eps_estimate_snapshot.py` 는 docstring 에
*"PIT historical 무료 source 부재 → 자체 누적이 유일"* 이라고 적고 2026-05-04 부터 스냅샷을
쌓아 왔다. 2026-08-09 소스 전수 조사에서 yfinance 가 `eps_trend`(현재/7·30·60·90일 전 추정치)와
`eps_revisions`(상향/하향 건수)를 **직접 준다**는 것을 확인했다.

🚨 **다만 이것은 PIT 히스토리가 아니다.** 당일 기준 90일 롤링 창의 스냅샷이다.
   90일을 넘는 구간은 여전히 자체 누적이 필요하며, `eps_estimates.jsonl`(3,955행) 의 가치는
   그대로다. 여기서 얻는 것은 **콜드스타트 해소 + 상향/하향 건수**이지 시간여행이 아니다.
   docs/DATA_LAYER_RESEARCH_20260809.md §1-2 · §6 정정 #12.

🚨 **라이선스 — L1/L2 전용, L3 발행 금지.** eps_trend·eps_revisions 는 Yahoo 가 외부에서
   라이선스한 애널리스트 집계로 `us_analyst_consensus` 와 같은 class 다. PM 2026-07-10 결정
   (컨센서스 공개 발행 영구 금지)이 이 표면 전체에 적용된다. publish-data allowlist 재추가 금지.

🚨 트랙 A 규율 — **수집만 한다. 스코어 통합 금지.** 검정은 누적 후 사전등록 게이트 통과 뒤.

출력 = data/us_eps_revision.json (최신 스냅샷) + data/us_eps_revision_trail.jsonl (L2 누적)
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.builders.us_insider_trades_public_builder import _now_kst, _ordered_universe  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_eps_revision.json")
OUTPUT_TRAIL = os.path.join(_ROOT, "data", "us_eps_revision_trail.jsonl")

MAX_SECONDS = int(os.environ.get("US_EPS_REV_MAX_SECONDS", "1800"))
THROTTLE_SEC = 0.15
STALE_DROP_DAYS = 21   # 추정치는 분기 주기라 옵션보다 길게 유지

# yfinance eps_trend/eps_revisions 의 period 인덱스 — 0q=당분기 +1q=다음분기 0y=당해 +1y=내년
_PERIODS = ("0q", "+1q", "0y", "+1y")


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _cell(df, period: str, col: str) -> Optional[float]:
    try:
        return _num(df.loc[period, col])
    except (KeyError, ValueError, TypeError, AttributeError):
        return None


def _one(ticker: str) -> Optional[Dict[str, Any]]:
    import yfinance as yf

    t = yf.Ticker(ticker)
    try:
        trend = t.eps_trend
        rev = t.eps_revisions
    except Exception:  # noqa: BLE001 — 개별 실패 격리
        return None
    if trend is None and rev is None:
        return None

    out: Dict[str, Any] = {"ticker": ticker, "as_of": _now_kst().isoformat()}
    periods: Dict[str, Any] = {}
    for p in _PERIODS:
        cur = _cell(trend, p, "current")
        d7 = _cell(trend, p, "7daysAgo")
        d30 = _cell(trend, p, "30daysAgo")
        d90 = _cell(trend, p, "90daysAgo")
        up7 = _cell(rev, p, "upLast7days")
        dn7 = _cell(rev, p, "downLast7Days")   # 🚨 yfinance 컬럼명 대소문자 불일치(Days)
        up30 = _cell(rev, p, "upLast30days")
        dn30 = _cell(rev, p, "downLast30days")
        block: Dict[str, Any] = {}
        if cur is not None:
            block["cur"] = round(cur, 4)
        # 리비전 폭 — 추정치 자체보다 "얼마나 움직였나" 가 신호 후보다. 0 나눗셈 방지.
        for lbl, past in (("d7", d7), ("d30", d30), ("d90", d90)):
            if cur is not None and past not in (None, 0):
                block[f"chg_{lbl}_pct"] = round((cur / past - 1.0) * 100, 3)
        for lbl, v in (("up7", up7), ("dn7", dn7), ("up30", up30), ("dn30", dn30)):
            if v is not None:
                block[lbl] = int(v)
        # 상향−하향 = 리비전 방향의 순량. 분모가 0이면 비율 대신 순량만.
        if up30 is not None and dn30 is not None:
            block["net30"] = int(up30 - dn30)
            tot = up30 + dn30
            if tot > 0:
                block["diffusion30"] = round((up30 - dn30) / tot, 3)
        if block:
            periods[p] = block

    if not periods:
        return None
    out["periods"] = periods
    return out


def append_trail(records: List[Dict[str, Any]]) -> int:
    """L2 누적 — 90일 롤링 창을 넘어서는 구간은 이 trail 로만 복원된다."""
    if not records:
        return 0
    day = _now_kst().strftime("%Y-%m-%d")
    n = 0
    try:
        os.makedirs(os.path.dirname(OUTPUT_TRAIL), exist_ok=True)
        with open(OUTPUT_TRAIL, "a", encoding="utf-8") as f:
            for r in records:
                q = (r.get("periods") or {}).get("+1q") or {}
                y = (r.get("periods") or {}).get("+1y") or {}
                slim = {
                    "d": day, "t": r.get("ticker"),
                    "q_cur": q.get("cur"), "q_chg30": q.get("chg_d30_pct"),
                    "q_net30": q.get("net30"), "q_diff30": q.get("diffusion30"),
                    "y_cur": y.get("cur"), "y_chg30": y.get("chg_d30_pct"),
                    "y_net30": y.get("net30"), "y_diff30": y.get("diffusion30"),
                }
                f.write(json.dumps(slim, ensure_ascii=False, separators=(",", ":")) + "\n")
                n += 1
    except OSError as e:
        print(f"[us_eps_rev] trail 적재 실패(무시): {type(e).__name__}", file=sys.stderr)
        return 0
    return n


def _load_prev() -> Dict[str, Dict[str, Any]]:
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        return {str(s.get("ticker") or ""): s for s in (doc.get("stocks") or []) if s.get("ticker")}
    except (OSError, ValueError):
        return {}


def _age_days(iso: str) -> float:
    from datetime import datetime
    try:
        return (_now_kst() - datetime.fromisoformat(iso)).days
    except (ValueError, TypeError):
        return 1e9


def collect() -> int:
    prev = _load_prev()
    order = _ordered_universe()
    t0 = time.monotonic()
    fresh: Dict[str, Dict[str, Any]] = {}
    tried = no_data = 0

    for tk in order:
        if time.monotonic() - t0 > MAX_SECONDS:
            print(f"[us_eps_rev] budget 도달 ({int(time.monotonic()-t0)}s) — 나머지 carry-forward",
                  file=sys.stderr)
            break
        tried += 1
        try:
            rec = _one(tk)
        except Exception as e:  # noqa: BLE001
            print(f"[us_eps_rev] {tk} 실패: {type(e).__name__}", file=sys.stderr)
            rec = None
        if rec:
            fresh[tk] = rec
        else:
            no_data += 1
        time.sleep(THROTTLE_SEC)

    merged = {k: v for k, v in prev.items() if _age_days(v.get("as_of", "")) <= STALE_DROP_DAYS}
    merged.update(fresh)
    trail_n = append_trail(list(fresh.values()))
    stocks = sorted(merged.values(), key=lambda s: s.get("ticker") or "")

    if not stocks:
        print("[us_eps_rev] 산출 0건 — 발행하지 않는다", file=sys.stderr)
        return 1

    doc = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "yfinance eps_trend + eps_revisions (애널리스트 추정치 리비전)",
            "stock_count": len(stocks),
            "fresh_this_run": len(fresh),
            "trail_appended": trail_n,
            "tried_this_run": tried,
            "no_data_this_run": no_data,
            "window_note": "🚨 당일 기준 **90일 롤링 창** 스냅샷이지 PIT 히스토리가 아니다. "
                           "90일 초과 구간은 us_eps_revision_trail.jsonl 누적으로만 복원된다.",
            "license_note": "🚫 애널리스트 집계 class — L1/L2 전용, **공개 발행 금지**"
                            "(us_analyst_consensus 와 동일 취급, PM 2026-07-10 결정).",
            "disclaimer": "외부 집계 사실만. 자체 점수·매매신호 0(RULE 7). 스코어 미통합(트랙 A).",
        },
        "stocks": stocks,
    }
    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUTPUT_PATH)
    m = doc["_meta"]
    print(f"[us_eps_rev] {m['stock_count']:,}종 보유 (신규 {m['fresh_this_run']:,} · "
          f"trail {trail_n:,} · 시도 {tried:,} · 데이터없음 {no_data:,})")
    return 0


if __name__ == "__main__":
    raise SystemExit(collect())

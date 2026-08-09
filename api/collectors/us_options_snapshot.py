"""us_options_snapshot — 미장 옵션 관측(IV·미결제·P/C·스큐) 일별 스냅샷. 2026-08-09 신설.

**왜 신설했나.** 2026-08-09 커버리지 점검에서 미장 판단 재료 중 **가격 미시구조가 통째로
비어 있다**는 것이 드러났다. 그때 나는 "옵션은 유료 벤더 계약 후에만" 이라고 PM 에게 보고했는데
**그건 Polygon 무료 tier(스냅샷 403)만 보고 내린 결론이었고 틀렸다**. yfinance 가 옵션 체인을
그대로 준다 — 실호출 확인(2026-08-09): AAPL 만기 20개 · calls 47행 · impliedVolatility·
openInterest·volume 전부 포함. 종목당 약 2.2초.

🚨 RULE 7 — 여기 담는 것은 **관측 사실**이다: 시장이 붙인 IV, 거래소 미결제약정·거래량, 그리고
   그 위의 단순 산술(P/C 비율·스큐 차). 우리 점수·등급·매매신호 0. "IV 가 높으니 비싸다" 류
   해석은 이 층에서 하지 않는다.
🚨 스큐 정의를 코드와 산출물에 같이 남긴다 — 정의가 없는 스큐 숫자는 비교 불가라 사실도 아니다.
   여기서 skew_pp = (현재가 0.9배 근처 풋 IV) − (현재가 1.1배 근처 콜 IV), %p. 델타 기준이 아니라
   **행사가 기준 근사**다. 델타 스큐와 같은 자로 재지 말 것.

소스 = yfinance(무료·키 0). 전 유니버스 rotation + carry-forward + wall-clock budget.
출력 = data/us_options.json {_meta, stocks:[{ticker, spot, expiry, iv_atm, skew_pp, pc_volume,
       pc_oi, call_oi, put_oi, call_volume, put_volume, expiry_count, as_of}]}
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
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_options.json")

MAX_SECONDS = int(os.environ.get("US_OPTIONS_MAX_SECONDS", "1800"))
THROTTLE_SEC = 0.15
# 옵션이 상장된 종목만 의미가 있다 — 미상장은 즉시 빠지므로 예산을 거의 안 쓴다.
SKEW_PUT_MONEYNESS = 0.90
SKEW_CALL_MONEYNESS = 1.10
STALE_DROP_DAYS = 14   # 이보다 오래된 carry-forward 는 버린다(옵션은 빨리 늙는다)


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # NaN 제거


def _nearest_iv(df, target: float) -> Optional[float]:
    """target 행사가에 가장 가까운 행의 IV. 빈 프레임이면 None."""
    if df is None or len(df) == 0:
        return None
    try:
        idx = (df["strike"] - target).abs().idxmin()
        return _num(df.loc[idx, "impliedVolatility"])
    except (KeyError, ValueError):
        return None


def _one(ticker: str) -> Optional[Dict[str, Any]]:
    import yfinance as yf

    t = yf.Ticker(ticker)
    try:
        exps = t.options
    except Exception:  # noqa: BLE001 — 개별 실패 격리
        return None
    if not exps:
        return None
    try:
        spot = _num(t.fast_info.last_price)
        ch = t.option_chain(exps[0])
    except Exception:  # noqa: BLE001
        return None
    calls, puts = ch.calls, ch.puts
    if calls is None or puts is None or (len(calls) == 0 and len(puts) == 0):
        return None

    def _sum(df, col) -> float:
        try:
            return float(df[col].fillna(0).sum())
        except (KeyError, ValueError):
            return 0.0

    cv, pv = _sum(calls, "volume"), _sum(puts, "volume")
    coi, poi = _sum(calls, "openInterest"), _sum(puts, "openInterest")

    iv_c = _nearest_iv(calls, spot) if spot else None
    iv_p = _nearest_iv(puts, spot) if spot else None
    iv_atm = None
    if iv_c is not None and iv_p is not None:
        iv_atm = round((iv_c + iv_p) / 2 * 100, 2)
    elif iv_c is not None or iv_p is not None:
        iv_atm = round((iv_c if iv_c is not None else iv_p) * 100, 2)

    skew = None
    if spot:
        otm_p = _nearest_iv(puts, spot * SKEW_PUT_MONEYNESS)
        otm_c = _nearest_iv(calls, spot * SKEW_CALL_MONEYNESS)
        if otm_p is not None and otm_c is not None:
            skew = round((otm_p - otm_c) * 100, 2)

    return {
        "ticker": ticker,
        "spot": round(spot, 4) if spot else None,
        "expiry": exps[0],
        "expiry_count": len(exps),
        "iv_atm_pct": iv_atm,
        "skew_pp": skew,
        "pc_volume": round(pv / cv, 3) if cv else None,
        "pc_oi": round(poi / coi, 3) if coi else None,
        "call_volume": int(cv), "put_volume": int(pv),
        "call_oi": int(coi), "put_oi": int(poi),
        "as_of": _now_kst().isoformat(),
    }


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
    tried = no_options = 0

    for tk in order:
        if time.monotonic() - t0 > MAX_SECONDS:
            print(f"[us_options] budget 도달 ({int(time.monotonic()-t0)}s) — 나머지 carry-forward",
                  file=sys.stderr)
            break
        tried += 1
        try:
            rec = _one(tk)
        except Exception as e:  # noqa: BLE001
            print(f"[us_options] {tk} 실패: {type(e).__name__}", file=sys.stderr)
            rec = None
        if rec:
            fresh[tk] = rec
        else:
            no_options += 1
        time.sleep(THROTTLE_SEC)

    # carry-forward — 단 오래된 것은 버린다. 옵션 스냅샷은 며칠만 지나도 사실이 아니다.
    merged = {k: v for k, v in prev.items() if _age_days(v.get("as_of", "")) <= STALE_DROP_DAYS}
    merged.update(fresh)
    stocks = sorted(merged.values(), key=lambda s: (s.get("call_oi") or 0) + (s.get("put_oi") or 0),
                    reverse=True)

    if not stocks:
        print("[us_options] 산출 0건 — 발행하지 않는다", file=sys.stderr)
        return 1

    doc = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "yfinance 옵션 체인 (근월 만기) — IV·미결제약정·거래량 관측",
            "stock_count": len(stocks),
            "fresh_this_run": len(fresh),
            "tried_this_run": tried,
            "no_options_this_run": no_options,
            "skew_definition": (
                f"skew_pp = 풋 IV(행사가≈현재가×{SKEW_PUT_MONEYNESS}) − 콜 IV(행사가≈현재가×"
                f"{SKEW_CALL_MONEYNESS}), %p. 행사가 기준 근사이며 델타 기준 스큐와 다르다."
            ),
            "carry_forward_drop_days": STALE_DROP_DAYS,
            "note": "시장 관측 사실(IV·OI·거래량)과 그 위의 단순 산술만. 자체 점수·매매신호 0(RULE 7). "
                    "근월 만기 1개 기준이라 만기 구조(term structure)는 담지 않는다.",
        },
        "stocks": stocks,
    }
    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUTPUT_PATH)
    m = doc["_meta"]
    print(f"[us_options] {m['stock_count']:,}종 보유 (이번 run 신규 {m['fresh_this_run']:,} · "
          f"시도 {tried:,} · 옵션 미상장 {no_options:,})")
    return 0


if __name__ == "__main__":
    raise SystemExit(collect())

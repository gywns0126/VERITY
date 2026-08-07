# -*- coding: utf-8 -*-
"""rebalance_review — 드리프트 점검 배선 (2026-08-07).

**무엇을 고치는가**: `quarterly_rebalance`(사전등록 PREREG_TRADING_BANDS_REBALANCE_2026_08_02,
PM 승인 8/2)가 완성돼 있는데 **프로덕션 소비자가 0곳**이었다. 테스트만 import 했다.
5일째 죽은 코드. 목표비중(중용 3층)은 매일 정상 산출되는데 아무도 쓰지 않았다.

실측 배분(2026-08-07) — 이 배선이 없어서 아무도 못 보던 그림:
  총자산 9,709,033원 · 주식 11종 60.8% · 현금 10.3%
  🚨 FX 헷지 ETF 1종(KODEX 미국달러SOFR) **28.9%** — 개별 주식 최대(F&F 9.7%)의 3배

🚨 **표시값 전용. 자동 매매 0** (사전등록 정합 — trade_plan v0 철학).
🚨 **봉인 산출물**: 목표비중이 봉인(gitignore + private bucket)이라 파생물도 같은 등급이다.
   공개 blob·portfolio.json 에 실리지 않는다. `_operator/` 만.
🚨 **brain_score 미투입** — 중용 사전등록의 자기참조 차단 조항 정합.

분기 "점검"이 등록된 주기다. 매일 계산해 드리프트를 관측하되, **액션 리스트는 분기 검토
산출물**이라는 표기를 함께 남긴다(등록 §Part B).
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, Optional, Tuple

from api.config import DATA_DIR, now_kst
from api.portfolio.rebalance import quarterly_rebalance

OUT_PATH = os.path.join(DATA_DIR, "rebalance_review.json")
TRAIL_PATH = os.path.join(DATA_DIR, "rebalance_review_trail.jsonl")

# 분기 점검 월 (등록 = 분기 1회 점검). 그 외 날짜는 관측만.
_REVIEW_MONTHS = (1, 4, 7, 10)


def _fetch_targets() -> Tuple[Dict[str, float], Optional[str]]:
    """중용 목표비중을 private bucket 에서 조회. 실패 시 ({}, 사유).

    로컬 파일을 먼저 보지 않는다 — 봉인 규약상 로컬에 없는 것이 정상이다.
    """
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        return {}, "SUPABASE 자격 미설정 — 목표비중 조회 불가"
    try:
        req = urllib.request.Request(
            f"{url}/storage/v1/object/verity-reports/_operator/moderation_portfolio.json",
            headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            doc = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        return {}, f"목표비중 조회 실패: {type(e).__name__}"
    if doc.get("status") != "ok":
        return {}, f"중용 status={doc.get('status')} — 목표비중 미산출"
    w = doc.get("weights") or {}
    return {str(k): float(v) for k, v in w.items() if v}, None


def current_weights(portfolio: Dict[str, Any]) -> Tuple[Dict[str, float], float, Dict[str, Any]]:
    """현재 비중 {ticker: 0~1} + 총액 + 구성 내역.

    🚨 FX 헷지 리저브를 **반드시 포함**한다. holdings 배열 밖에 있는 별도 필드라
    빼면 총액의 29%가 그림에서 사라진다(2026-08-07 실측에서 실제로 그랬다).
    현금은 비중 계산에 넣지 않는다 — 재분배 대상이 아니라 잔여다.
    """
    v = portfolio.get("vams") or {}
    total = float(v.get("total_asset") or 0)
    parts: Dict[str, float] = {}
    detail: Dict[str, Any] = {"holdings": {}, "fx_hedge": None, "cash": float(v.get("cash") or 0)}

    for h in (v.get("holdings") or []):
        tk = str(h.get("ticker") or "")
        val = float(h.get("current_price") or 0) * float(h.get("quantity") or 0)
        if tk and val > 0:
            parts[tk] = parts.get(tk, 0.0) + val
            detail["holdings"][tk] = round(val)

    fx = v.get("fx_hedge_reserve") or {}
    fx_val = float(fx.get("current_krw") or 0)
    if fx_val > 0:
        tk = str(fx.get("ticker") or "FX_HEDGE")
        parts[tk] = parts.get(tk, 0.0) + fx_val
        detail["fx_hedge"] = {"ticker": tk, "name": fx.get("name"), "krw": round(fx_val),
                              "return_pct": fx.get("return_pct")}

    if total <= 0:
        return {}, 0.0, detail
    return {tk: val / total for tk, val in parts.items()}, total, detail


def build(portfolio: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """드리프트 점검 산출. 목표비중 조회 실패 시에도 현재 배분은 남긴다."""
    if portfolio is None:
        try:
            with open(os.path.join(DATA_DIR, "portfolio.json"), encoding="utf-8") as f:
                portfolio = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            return {"status": "skipped", "reason": f"portfolio.json 읽기 실패: {type(e).__name__}"}

    holdings, total, detail = current_weights(portfolio)
    as_of = now_kst()
    targets, err = _fetch_targets()

    out: Dict[str, Any] = {
        "as_of": as_of.isoformat(timespec="seconds"),
        "version": "rebalance_review_v0",
        "total_value_krw": round(total),
        "allocation": detail,
        "current_weights": {k: round(v, 4) for k, v in sorted(holdings.items(), key=lambda x: -x[1])},
        "is_review_month": as_of.month in _REVIEW_MONTHS,
        "review_months": list(_REVIEW_MONTHS),
        "auto_trade": False,
        "brain_used": False,
        "note": ("표시값 전용 — 자동 매매 0. 액션 리스트는 **분기 검토** 산출물이며 "
                 "그 외 날짜의 값은 드리프트 관측이다(PREREG_TRADING_BANDS_REBALANCE_2026_08_02). "
                 "봉인 등급 — 공개 발행 금지, _operator/ 전용."),
    }
    if not holdings or total <= 0:
        out["status"] = "skipped"
        out["reason"] = "보유·총액 없음"
        return _persist(out)
    if err:
        out["status"] = "targets_unavailable"
        out["reason"] = err
        return _persist(out)

    res = quarterly_rebalance(holdings, targets, total)
    out["status"] = "ok"
    out["targets_n"] = len(targets)
    out.update({k: res[k] for k in ("actions", "review", "profile", "skipped_in_band")})
    # review = 목표비중이 없는 보유. FX 헷지·미장이 여기 들어오는 것이 정상이다
    # (중용 3층은 KR 주식만 산출 — 미장은 us_pending, 헷지는 대상 밖).
    out["review_detail"] = [
        {"ticker": tk, "weight": round(holdings.get(tk, 0), 4),
         "krw": round(holdings.get(tk, 0) * total),
         "kind": ("fx_hedge" if detail.get("fx_hedge", {}) and
                  tk == (detail.get("fx_hedge") or {}).get("ticker")
                  else ("us" if not tk.isdigit() else "kr_no_target"))}
        for tk in res["review"]
    ]
    return _persist(out)


def _persist(doc: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_PATH)
    with open(TRAIL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": doc.get("as_of"), "status": doc.get("status"),
            "total_value_krw": doc.get("total_value_krw"),
            "actions": len(doc.get("actions") or []),
            "review": len(doc.get("review") or []),
            "is_review_month": doc.get("is_review_month"),
        }, ensure_ascii=False) + "\n")
    return doc


def main() -> None:
    d = build()
    if d.get("status") == "ok":
        print(f"[rebalance] 총 {d['total_value_krw']:,}원 · 액션 {len(d['actions'])}건 · "
              f"밴드 내 {d['skipped_in_band']} · 목표 없는 보유 {len(d['review'])}건 · "
              f"분기점검월={d['is_review_month']}")
        for a in d["actions"][:5]:
            print(f"   {a['side']:<5}{a['ticker']:<9}{a['amount_krw']:>11,}원 "
                  f"(드리프트 {a['rel_drift']:+.1%}{' · 최소거래액 미달' if a['gated'] else ''})")
        for r in d.get("review_detail", [])[:5]:
            print(f"   검토 {r['ticker']:<9}{r['krw']:>11,}원 ({r['weight']:.1%}, {r['kind']})")
    else:
        print(f"[rebalance] {d.get('status')} — {d.get('reason')}")


if __name__ == "__main__":
    main()

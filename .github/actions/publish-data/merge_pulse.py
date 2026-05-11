"""
publish-data 단계 inline merge — portfolio.json 에 price_pulse.json 의 indices/prices 주입.

Frontend (Framer 컴포넌트) 가 portfolio.json 만 fetch 하므로 publish 시점에 merge → 모든 컴포넌트 자동 fresh.
pulse 미존재 또는 부분 실패 시 silent (원본 portfolio 그대로 publish).

사용:
    python3 merge_pulse.py <portfolio.json path> <price_pulse.json path>

결과: portfolio.json 을 in-place 갱신.
"""
from __future__ import annotations

import json
import sys


def main(portfolio_path: str, pulse_path: str) -> int:
    try:
        with open(portfolio_path, "r", encoding="utf-8") as f:
            p = json.load(f)
    except Exception as e:
        print(f"  ✗ portfolio.json 읽기 실패: {e}")
        return 1

    try:
        with open(pulse_path, "r", encoding="utf-8") as f:
            pulse = json.load(f)
    except Exception as e:
        print(f"  ✗ price_pulse.json 읽기 실패: {e} — merge skip, portfolio 원본 유지")
        return 0

    indices = pulse.get("indices") or {}
    prices = pulse.get("prices") or {}

    # ── indices override — 기존 schema 의 value/change_pct 만 갈음 (trend/sparkline 유지) ──
    # frontend 컴포넌트가 이미 보고 있는 필드를 직접 갱신 → 컴포넌트 변경 0.
    # pulse 의 key 명 ↔ portfolio 의 key 명 매핑.
    INDEX_MAP = [
        ("kospi", "market_summary", "kospi"),
        ("kosdaq", "market_summary", "kosdaq"),
        ("sp500", "market_summary", "sp500"),
        ("nasdaq", "market_summary", "ndx"),     # portfolio 측 key 는 ndx
        ("vix", "macro", "vix"),
        ("usdkrw", "macro", "usd_krw"),          # portfolio 측 key 는 usd_krw
        # dow 는 기존 schema 없음 — indices_pulse 에만 raw 보관
    ]
    if indices:
        for pulse_key, section, target_key in INDEX_MAP:
            q = indices.get(pulse_key)
            if not q or q.get("value") is None:
                continue
            sec = p.get(section)
            if not isinstance(sec, dict):
                sec = {}
                p[section] = sec
            target = sec.get(target_key)
            if not isinstance(target, dict):
                target = {}
                sec[target_key] = target
            target["value"] = q["value"]
            if q.get("change_pct") is not None:
                target["change_pct"] = q["change_pct"]

        # raw indices 도 함께 보관 (디버그 + dow 등 미매핑 키 잔여)
        ms = p.get("market_summary")
        if not isinstance(ms, dict):
            ms = {}
            p["market_summary"] = ms
        ms["indices_pulse"] = indices

    if prices:
        holdings = (p.get("vams", {}) or {}).get("holdings", []) or []
        for h in holdings:
            tk = h.get("ticker")
            if not tk:
                continue
            is_us = (h.get("currency") or "").upper() == "USD"
            key = str(tk) if is_us else str(tk).zfill(6)
            if key in prices and prices[key]:
                h["current_price"] = prices[key]
                bp = h.get("buy_price") or 0
                if bp:
                    h["return_pct"] = round((prices[key] - bp) / bp * 100, 2)

        for r in p.get("recommendations", []) or []:
            tk = r.get("ticker")
            if not tk:
                continue
            is_us = (r.get("currency") or "").upper() == "USD"
            key = str(tk) if is_us else str(tk).zfill(6)
            if key in prices and prices[key]:
                r["price"] = prices[key]

    p["price_pulse_meta"] = {
        "updated_at": pulse.get("updated_at"),
        "elapsed_sec": pulse.get("elapsed_sec"),
        "counts": pulse.get("counts"),
    }

    with open(portfolio_path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False)

    print(
        f"  ✓ pulse merged: indices={len(indices)} prices={len(prices)} "
        f"updated_at={pulse.get('updated_at')}"
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: merge_pulse.py <portfolio.json> <price_pulse.json>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))

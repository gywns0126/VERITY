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
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from api.utils.kr_pulse_quote import aware_time, publishable_quotes, read_listings  # noqa: E402


def _recover_legacy_price(row, ticker, price, listed, as_of, same_generation):
    # The public sanitizer removes price_pulse_meta. A still-attributed daily bar
    # also identifies the mismatch if both overlaid prices match this rejected pulse.
    # Keep the original dated bar (including the adjustment convention) independent
    # of the pulse. A daily-bar timestamp is not the timestamp of a last trade.
    entry = listed.get(ticker)
    market = entry.get("market") if isinstance(entry, dict) else None
    bar = row.get("price_bar_value")
    bar_time = aware_time(row.get("price_bar_as_of"))
    recoverable = (
        market in ("KQ", "KS") and row.get("ticker_yf") == f"{ticker}.{market}"
        and row.get("price_source") == "yfinance.history"
        and row.get("price_time_kind") == "daily_bar_start"
        and row.get("price_bar_date") and bar_time and bar_time <= as_of
        and row["price_bar_date"] == bar_time.date().isoformat()
        and type(bar) in (int, float) and math.isfinite(bar) and bar > 0
    )
    if (same_generation or recoverable) and row.get("price") == price and row.get("current_price") == price:
        row["price"] = row["current_price"] = bar if recoverable else None


def _apply_kr_quote_time(row, quote):
    """Apply per-symbol provenance only when the observation advances the row."""
    observed = aware_time(quote["observed_at"])
    existing = aware_time(row.get("price_as_of")) or aware_time(row.get("price_timestamp"))
    bar = aware_time(row.get("price_bar_as_of"))
    if (existing and observed <= existing) or (bar and observed < bar):
        return False
    if row.get("price_time_kind") == "daily_bar_start":
        row["price_bar_source"] = row.get("price_source")
        row["price_bar_adjustment"] = row.get("price_adjustment")
    row.update(
        price_as_of=quote["observed_at"],
        price_source=quote["source"],
        price_time_kind="minute_bar" if quote["source"] == "kis" else "trade",
        price_adjustment="unadjusted",
    )
    if "price_timestamp" in row:
        row["price_timestamp"] = quote["observed_at"]
    return True


def main(portfolio_path: str, pulse_path: str, *, as_of=None) -> int:
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

    as_of = as_of or datetime.now(timezone.utc)
    generation = aware_time(pulse.get("updated_at"))
    previous = aware_time((p.get("price_pulse_meta") or {}).get("updated_at"))
    if (previous and (generation is None or generation < previous)) or (generation and generation > as_of):
        print("  · pulse generation rejected")
        return 0

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

    valid_quotes = {}
    if prices:
        # Only the staged export is passed by the publish job.
        listed = read_listings()
        valid_quotes = publishable_quotes(pulse, listed, as_of)

        holdings = (p.get("vams", {}) or {}).get("holdings", []) or []
        for h in holdings:
            ticker = str(h.get("ticker") or "")
            is_us = (h.get("currency") or "").upper() == "USD"
            key = ticker if is_us else ticker.zfill(6)
            price = prices.get(key)
            if not price:
                continue
            if not is_us and (key not in valid_quotes or not _apply_kr_quote_time(h, valid_quotes[key])):
                continue
            h["current_price"] = price
            bp = h.get("buy_price") or 0
            if bp:
                h["return_pct"] = round((price - bp) / bp * 100, 2)

        for r in p.get("recommendations", []) or []:
            tk = r.get("ticker")
            if not tk:
                continue
            is_us = (r.get("currency") or "").upper() == "USD"
            key = str(tk) if is_us else str(tk).zfill(6)
            price = prices.get(key)
            if not price:
                continue
            if not is_us:
                quote = valid_quotes.get(key)
                if quote is None:
                    if generation and not (aware_time(r.get("price_as_of")) or aware_time(r.get("price_timestamp"))):
                        _recover_legacy_price(r, key, price, listed, as_of, generation == previous)
                    continue
                if not _apply_kr_quote_time(r, quote):
                    continue
            r["price"] = prices[key]
            r["current_price"] = prices[key]

    counts = dict(pulse.get("counts") or {})
    counts["kr"] = len(valid_quotes)
    p["price_pulse_meta"] = {
        "updated_at": pulse.get("updated_at"),
        "elapsed_sec": pulse.get("elapsed_sec"),
        "counts": counts,
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

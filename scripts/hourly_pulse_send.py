"""
시간별 정기 시황 텔레그램 발송 (8슬롯/일 = 한국장 5 + 미장 3, DST 자동).

배경 (2026-05-12):
  - 사용자 spam 호소 → 5/12 텔레그램 dedupe 수리 후 "정기 시황"으로 정보 채널 재설계
  - market_info_density_map 메모리 + Perplexity-equivalent fact-check (Virtu APAC 자료)
    "오전 첫 30분 거래량 25%" 확인 → ★★★★★ 윈도우 정합 슬롯 선정

슬롯 (Vercel dispatch_pulse._is_hourly_pulse_slot 와 동일 정의):
  KR (KST): 09:30 / 11:30 / 14:30 / 15:30 / 17:00 — 평일
  US (ET) : 09:30 / 11:30 / 16:00 — 평일 (DST 자동)

발화 경로:
  Vercel Cron 매분 → dispatch_pulse → repository_dispatch:hourly_pulse →
  .github/workflows/hourly_pulse.yml → 본 스크립트.

입력:
  - data/price_pulse.json (1분 cron 갱신 — 지수+종목 fresh 가격)
  - data/portfolio.json (vams.holdings — 종목명/매입가)

출력: 짧은 텔레그램 메시지 (bypass_quiet=True — 정기 push).

dry-run: HOURLY_PULSE_DRY_RUN=1 → 표준출력만, 전송 X.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
PRICE_PULSE = ROOT / "data" / "price_pulse.json"
PORTFOLIO = ROOT / "data" / "portfolio.json"

KST = timezone(timedelta(hours=9))


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        sys.stderr.write(f"[hourly_pulse] load fail {path}: {e}\n")
        return {}


def _is_us_dst(now_utc: datetime) -> bool:
    y = now_utc.year
    march1 = datetime(y, 3, 1, tzinfo=timezone.utc)
    second_sun_mar = march1 + timedelta(days=((6 - march1.weekday()) % 7) + 7)
    nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
    first_sun_nov = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    return second_sun_mar <= now_utc < first_sun_nov


SLOT_TOL_MIN = 15  # gh dispatch→run 지연 흡수 창(분). 초과 지연 = stale 시황이라 발송 안 함.


def _is_trading_day(d, region: str) -> bool:
    """KRX/US 거래일 여부 (휴장·주말 스킵). market_calendar 실패 시 = 평일만(폴백)."""
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from api.utils.market_calendar import is_trading_day
        return bool(is_trading_day(d, region))  # type: ignore[arg-type]
    except Exception as e:
        sys.stderr.write(f"[hourly_pulse] market_calendar 실패({region}): {e} — 평일 폴백\n")
        return d.weekday() <= 4


def _resolve_slot(now_utc: datetime) -> Tuple[str, str]:
    """현재(또는 직전 SLOT_TOL_MIN 분 내) 슬롯 식별. 반환 = (region, label).

    region: 'KR' | 'US' | 'NONE'. label = 'KST HH:MM'.
    🚨 gh dispatch→run 지연 대응 = 직전 SLOT_TOL_MIN 분 역탐색(정확 분 매칭 실패 흡수).
       + KRX/US 휴장 스킵. 슬롯 아니면 ('NONE','') → 발송 안 함(오발송·휴장·새벽 오라벨 차단, 2026-07-17).
    """
    kr_slots = [(9, 30), (11, 30), (14, 30), (15, 30), (17, 0)]
    us_slots = [(9, 30), (11, 30), (16, 0)]
    et_offset = -4 if _is_us_dst(now_utc) else -5
    for back in range(0, SLOT_TOL_MIN + 1):
        t = now_utc - timedelta(minutes=back)
        tk = t + timedelta(hours=9)              # KST
        te = t + timedelta(hours=et_offset)      # ET
        if tk.weekday() <= 4 and (tk.hour, tk.minute) in kr_slots and _is_trading_day(tk.date(), "KR"):
            return "KR", f"{tk.hour:02d}:{tk.minute:02d}"
        if te.weekday() <= 4 and (te.hour, te.minute) in us_slots and _is_trading_day(te.date(), "US"):
            return "US", f"{tk.hour:02d}:{tk.minute:02d}"
    return "NONE", ""


def _fmt_idx(name: str, idx: Optional[Dict[str, Any]]) -> str:
    if not idx:
        return f"{name} —"
    v = idx.get("value")
    pct = idx.get("change_pct")
    if v is None:
        return f"{name} —"
    if isinstance(v, (int, float)):
        if name in ("VIX",):
            v_str = f"{v:.2f}"
        elif name == "USD/KRW":
            v_str = f"{v:,.1f}"
        else:
            v_str = f"{v:,.0f}"
    else:
        v_str = str(v)
    if pct is None:
        return f"{name} {v_str}"
    return f"{name} {v_str} ({pct:+.2f}%)"


def _pick_holding_price(h: Dict[str, Any], pulse_prices: Dict[str, Any], fx_rate: float = 0.0) -> Tuple[float, float]:
    """fresh price 우선, 못 찾으면 portfolio.json 값. 반환 = (current_price, return_pct).

    🚨 US 보유 통화 정합 (2026-07-01 -99.9% 사고): price_pulse 가격은 raw USD 인데
       buy_price 는 KRW 환산 저장(main.py:2266 current_price = raw × fx_rate). 그대로 (rawUSD - KRWbuy)
       계산하면 -99.9% 나옴. → US 는 fresh 도 ×fx_rate 로 KRW 정합. fx 없으면 portfolio 저장값(KRW 정합) 폴백."""
    yf_t = h.get("ticker_yf") or ""
    kr_t = h.get("ticker") or ""
    fresh = None
    for key in (yf_t, kr_t):
        if key and key in pulse_prices:
            fresh = pulse_prices[key]
            break
    buy = h.get("buy_price") or 0
    if fresh is not None and isinstance(fresh, (int, float)):
        is_us = h.get("currency") == "USD"
        if is_us and (not fx_rate or fx_rate <= 0):
            # fx 부재 시 raw USD vs KRW buy_price = 사고 → portfolio 저장값(KRW 정합) 사용
            return float(h.get("current_price") or 0), float(h.get("return_pct") or 0)
        cur = float(fresh) * fx_rate if is_us else float(fresh)
        if buy:
            ret = (cur - buy) / buy * 100
        else:
            ret = h.get("return_pct", 0)
        return cur, ret
    return float(h.get("current_price") or 0), float(h.get("return_pct") or 0)


def _build_message(region: str, label: str, pp: Dict[str, Any], pf: Dict[str, Any]) -> str:
    idx = pp.get("indices") or {}
    pulse_prices = pp.get("prices") or {}

    region_tag = {"KR": "한국장", "US": "미장"}.get(region, "—")
    lines = [f"<b>📊 {label} KST 시황 · {region_tag}</b>"]
    lines.append("─────────────")

    # 지수 순서: 시점에 맞춰 우선순위 다르게 노출
    if region == "KR":
        lines.append(
            f"{_fmt_idx('KOSPI', idx.get('kospi'))} | {_fmt_idx('KOSDAQ', idx.get('kosdaq'))}"
        )
        lines.append(_fmt_idx("USD/KRW", idx.get("usdkrw")))
        lines.append(
            f"{_fmt_idx('S&P', idx.get('sp500'))} | {_fmt_idx('NDX', idx.get('nasdaq'))} | {_fmt_idx('VIX', idx.get('vix'))}"
        )
    else:  # US
        lines.append(
            f"{_fmt_idx('S&P', idx.get('sp500'))} | {_fmt_idx('NDX', idx.get('nasdaq'))} | {_fmt_idx('VIX', idx.get('vix'))}"
        )
        lines.append(_fmt_idx("USD/KRW", idx.get("usdkrw")))
        lines.append(
            f"{_fmt_idx('KOSPI', idx.get('kospi'))} | {_fmt_idx('KOSDAQ', idx.get('kosdaq'))} <i>(전일 종가)</i>"
        )

    # 보유
    vams = pf.get("vams") or {}
    holdings = vams.get("holdings") or []
    total_ret = vams.get("total_return_pct", 0)
    # US 보유 통화 정합용 fx (buy_price 가 KRW 환산이라 fresh USD 도 ×fx 필요, main.py:2266 동일 소스)
    try:
        fx_rate = float((pf.get("macro") or {}).get("usd_krw", {}).get("value") or 0)
    except (TypeError, ValueError):
        fx_rate = 0.0
    if holdings:
        lines.append("─────────────")
        lines.append(f"<b>보유</b> ({len(holdings)}종목, {total_ret:+.2f}%)")
        for h in holdings[:8]:
            name = h.get("name") or h.get("ticker", "?")
            _, ret_pct = _pick_holding_price(h, pulse_prices, fx_rate)
            emoji = "🟢" if ret_pct >= 0 else "🔴"
            lines.append(f" {emoji} {name} {ret_pct:+.1f}%")

    lines.append("─────────────")
    lines.append("<i>정기 시황 · VERITY</i>")
    return "\n".join(lines)


def main() -> int:
    now_utc = datetime.now(timezone.utc)
    region, label = _resolve_slot(now_utc)
    if region == "NONE":
        # 슬롯 아님(gh 지연 SLOT_TOL_MIN 초과=stale / 휴장 / 수동 dispatch) → 오발송 방지로 skip.
        # 구 fallback('가장 가까운 시각 라벨 붙여 전송')은 US 새벽 슬롯을 '한국장'으로 오라벨링 +
        # 휴장 발송 사고 원인 → 폐기 (2026-07-17, 사용자 spam 호소 후속).
        sys.stderr.write("[hourly_pulse] 슬롯 아님 — 발송 skip (휴장/지연초과/수동)\n")
        return 0

    pp = _load_json(PRICE_PULSE)
    pf = _load_json(PORTFOLIO)
    if not pp or not pp.get("indices"):
        sys.stderr.write("[hourly_pulse] price_pulse.json 비어있음 — skip\n")
        return 0

    msg = _build_message(region, label, pp, pf)

    if os.environ.get("HOURLY_PULSE_DRY_RUN", "").strip() in ("1", "true", "yes"):
        print(msg)
        return 0

    # 정기 push — bypass_quiet=True 로 quiet hours 우회 (미장 슬롯 새벽).
    # dedupe=True OK: 슬롯 label 이 본문에 들어가 fp 매번 다름.
    sys.path.insert(0, str(ROOT))
    try:
        from api.notifications.telegram import send_message
    except Exception as e:
        sys.stderr.write(f"[hourly_pulse] import send_message 실패: {e}\n")
        return 1

    ok = send_message(msg, dedupe=True, bypass_quiet=True)
    print(f"[hourly_pulse] sent={ok} region={region} label={label}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

"""
KRX 프로그램 매매동향 수집기
차익/비차익 매도 폭탄 감지 → alert_engine 연동
"""
import os
import logging
from datetime import date
from typing import Optional

import requests

logger = logging.getLogger(__name__)

KRX_BASE = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
HEADERS = {
    "User-Agent": os.getenv("SEC_EDGAR_USER_AGENT", "VERITY verity@example.com"),
    "Referer": "http://data.krx.co.kr",
}

# 임계값 (억원 단위)
_NON_ARB_SELL_BOMB = -5000
_TOTAL_SELL_BOMB = -7000
_ARB_SELL_WARNING = -2000


def get_program_trading_today(target_date: Optional[date] = None) -> dict:
    """
    KRX 프로그램 매매동향 (당일 차익/비차익 순매수 금액).
    출처: KRX 정보데이터시스템 MDCSTAT06401
    """
    today = (target_date or date.today()).strftime("%Y%m%d")
    payload = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT06401",
        "trdDd": today,
    }
    try:
        resp = requests.post(KRX_BASE, data=payload, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        raw = resp.json()
        rows = raw.get("output", [])
        if not rows:
            logger.warning("[Program] KRX 응답 비어있음 (휴장일 가능)")
            return _fallback(today, note="KRX 응답 비어있음 (휴장일 가능)")

        output = rows[0]

        arb_buy = _parse_bn(output.get("ARB_BUY_AMT", "0"))
        arb_sell = _parse_bn(output.get("ARB_SELL_AMT", "0"))
        non_buy = _parse_bn(output.get("NARB_BUY_AMT", "0"))
        non_sell = _parse_bn(output.get("NARB_SELL_AMT", "0"))

        arb_net = arb_buy - arb_sell
        non_net = non_buy - non_sell
        total_net = arb_net + non_net

        return {
            "ok": True,
            "date": today,
            "arb_net_bn": round(arb_net, 1),
            "non_arb_net_bn": round(non_net, 1),
            "total_net_bn": round(total_net, 1),
            "signal": _classify_signal(non_net, arb_net),
            "sell_bomb": non_net < _NON_ARB_SELL_BOMB or total_net < _TOTAL_SELL_BOMB,
            "sell_bomb_reason": _sell_bomb_reason(non_net, arb_net),
        }
    except Exception as e:
        logger.error(f"[Program] KRX 조회 실패: {e}")
        return _fallback(today)


def _classify_signal(non_net: float, arb_net: float) -> str:
    total = non_net + arb_net
    if non_net < _NON_ARB_SELL_BOMB:
        return "SELL_BOMB"
    if total > 3000:
        return "STRONG_BUY_PRESSURE"
    if total > 1000:
        return "BUY_PRESSURE"
    if total > -1000:
        return "NEUTRAL"
    if total > -3000:
        return "SELL_PRESSURE"
    return "STRONG_SELL_PRESSURE"


def _sell_bomb_reason(non_net: float, arb_net: float) -> Optional[str]:
    reasons = []
    if non_net < _NON_ARB_SELL_BOMB:
        reasons.append(f"비차익 매도 {abs(non_net):.0f}억 (임계값 5,000억 초과)")
    if arb_net < _ARB_SELL_WARNING:
        reasons.append(f"차익 매도 {abs(arb_net):.0f}억 (역차익 동반 발생)")
    if (non_net + arb_net) < _TOTAL_SELL_BOMB:
        reasons.append(f"총 프로그램 순매도 {abs(non_net + arb_net):.0f}억")
    return " / ".join(reasons) if reasons else None


def _parse_bn(val: str) -> float:
    """KRX 금액 문자열(백만원 단위) → 억원 단위 float."""
    try:
        cleaned = str(val).replace(",", "").replace("-", "0").strip() or "0"
        return float(cleaned) / 100
    except Exception:
        return 0.0


def _fallback(today_str: Optional[str] = None, note: Optional[str] = None) -> dict:
    return {
        "ok": False,
        "date": today_str or date.today().strftime("%Y%m%d"),
        "arb_net_bn": 0,
        "non_arb_net_bn": 0,
        "total_net_bn": 0,
        "signal": "NEUTRAL",
        "sell_bomb": False,
        "sell_bomb_reason": None,
        "error": note or "KRX 조회 실패",
    }

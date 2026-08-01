"""urgent_alerts_builder — 고영향 이벤트 긴급 팝업 피드 (사실 랭킹, RULE 7 clean).

2026-08-01 신설. PM 발화 예시 = "하이닉스 최태원 회장이 43만주인가 사들인 정보를 늦게 들음.
주가 영향력 큰 정보는 긴급으로 사이트 내 팝업으로". 그 공백을 채운다.

원칙 (RULE 7 — 자체 점수·예측 아님):
  - 전부 **공시 사실**. 임원/대주주 대량거래 = 금액(주식수 × 평가기준가) 순 랭킹.
    공시 긴급도 = dart_catalyst 가 이미 서버 산정한 severity(1~3) 재사용. 우리 산식 신설 0.
  - "고영향" 판정 = 객관 임계(금액 ≥ HIGH_IMPACT_KRW) + severity==3 뿐. 매수/매도 추천·예측 없음.
  - 각 알림에 DART 원문 URL 병기 (1차 자료 직링크).

입력 (전부 기존 발행 사실):
  - data/insider_trades.json      임원·주요주주 특정증권 소유상황보고 (change=주식수, +매수/−매도)
  - data/kr_close_latest.json     평가기준가 맵 {prices:{ticker: 종가}} (금액 산출용)
                                  [[feedback_rotating_collector_not_a_price_source]] 정합 = 이 맵이 기준가
  - data/dart_catalyst_alerts.jsonl  거래소/지분 공시 severity (서버 산정 1~3)

산출: data/urgent_alerts.json  {_meta, alerts:[...]}  (작음 ~15건, 팝업 전용)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

INSIDER_PATH = os.path.join(DATA_DIR, "insider_trades.json")
PRICE_PATH = os.path.join(DATA_DIR, "kr_close_latest.json")
CATALYST_PATH = os.path.join(DATA_DIR, "dart_catalyst_alerts.jsonl")
OUTPUT_PATH = os.path.join(DATA_DIR, "urgent_alerts.json")

# 고영향 임계 — 객관 사실 필터 (자체 산식 아님). 임원/대주주 거래 금액 하한.
HIGH_IMPACT_KRW = 1_000_000_000  # 10억
INSIDER_WINDOW_DAYS = 5          # 최근 5일 거래만
DISCLOSURE_WINDOW_DAYS = 3       # 공시는 잦아 더 짧게
MAX_ALERTS = 15
DART_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"


def _load_json(path: str) -> Optional[Any]:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("[urgent_alerts] %s 로드 실패: %s", path, e)
        return None


def _price_map() -> Dict[str, float]:
    d = _load_json(PRICE_PATH) or {}
    prices = d.get("prices") if isinstance(d, dict) else None
    out: Dict[str, float] = {}
    for k, v in (prices or {}).items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _oku(krw: float) -> str:
    """원 → '억' 한글 표기 (사실 규모)."""
    return f"{krw / 1e8:.1f}억"


def _insider_alerts(cutoff: str, prices: Dict[str, float]) -> List[Dict[str, Any]]:
    doc = _load_json(INSIDER_PATH) or {}
    stocks = doc.get("stocks") if isinstance(doc, dict) else None
    alerts: List[Dict[str, Any]] = []
    for s in stocks or []:
        ticker = str(s.get("ticker") or "")
        name = s.get("name") or ticker
        px = prices.get(ticker)
        for t in s.get("trades") or []:
            date = t.get("date") or ""
            if date < cutoff:
                continue
            shares = t.get("change")
            if not isinstance(shares, (int, float)) or shares == 0:
                continue
            # 금액 = |주식수| × 평가기준가. 가격 결측 시 규모 판정 불가 → 스킵(고영향 확신 불가).
            if px is None:
                continue
            amount = abs(float(shares)) * px
            if amount < HIGH_IMPACT_KRW:
                continue
            is_buy = shares > 0
            person = t.get("person") or "-"
            position = t.get("position") or ""
            if position in ("-", "—"):
                position = ""
            who = f"{person} {position}".strip()
            verb = "매수" if is_buy else "매도"
            headline = f"{who} {abs(int(shares)):,}주 {verb} (약 {_oku(amount)})"
            alerts.append({
                "ticker": ticker,
                "name": name,
                "type": "insider_buy" if is_buy else "insider_sell",
                "headline": headline,
                "amount_krw": int(amount),
                "shares": int(shares),
                "person": person,
                "position": position,
                "date": date,
                "source_url": t.get("source_url") or "",
                "rank_key": amount,
            })
    return alerts


def _disclosure_alerts(cutoff_ymd: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(CATALYST_PATH):
        return []
    alerts: List[Dict[str, Any]] = []
    try:
        with open(CATALYST_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        logger.warning("[urgent_alerts] catalyst 로드 실패: %s", e)
        return []
    # 최근 꼬리만 스캔 (파일이 9천 줄+). severity 3 = 서버 산정 긴급.
    for line in lines[-1500:]:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("severity") != 3:
            continue
        rcept_dt = str(e.get("rcept_dt") or "")
        if rcept_dt < cutoff_ymd:
            continue
        rcept_no = e.get("rcept_no") or ""
        report_nm = (e.get("report_nm") or "").strip()
        alerts.append({
            "ticker": str(e.get("ticker") or ""),
            "name": e.get("name") or "",
            "type": "disclosure",
            "headline": report_nm,
            "severity": 3,
            "label": e.get("pblntf_label") or "공시",
            "filer": e.get("flr_nm") or "",
            "date": f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}" if len(rcept_dt) == 8 else rcept_dt,
            "source_url": DART_URL.format(rcept_no) if rcept_no else "",
            "rank_key": 0.0,  # severity 동일 → 최신순
        })
    return alerts


def build() -> Dict[str, Any]:
    now = now_kst()
    insider_cutoff = (now - timedelta(days=INSIDER_WINDOW_DAYS)).strftime("%Y-%m-%d")
    disc_cutoff = (now - timedelta(days=DISCLOSURE_WINDOW_DAYS)).strftime("%Y%m%d")

    prices = _price_map()
    insider = _insider_alerts(insider_cutoff, prices)
    disclosure = _disclosure_alerts(disc_cutoff)

    # 금액 큰 임원거래 우선, 그다음 최신 긴급공시. type 별 상한으로 한쪽 독점 방지.
    insider.sort(key=lambda a: (a["date"], a["rank_key"]), reverse=True)
    disclosure.sort(key=lambda a: a["date"], reverse=True)
    merged = insider[:10] + disclosure[:10]
    merged.sort(key=lambda a: (a["date"], a["rank_key"]), reverse=True)
    alerts = merged[:MAX_ALERTS]
    for a in alerts:
        a.pop("rank_key", None)

    return {
        "_meta": {
            "generated_at": now.isoformat(),
            "source": "DART 임원·주요주주 소유상황보고 + 거래소 공시(severity 3). 금액=주식수×평가기준가(금융위).",
            "note": "공시 사실만 — 자체 점수·매매신호·예측 아님 (RULE 7). 규모/긴급도는 객관 사실(금액·공시 severity).",
            "high_impact_krw": HIGH_IMPACT_KRW,
            "insider_window_days": INSIDER_WINDOW_DAYS,
            "disclosure_window_days": DISCLOSURE_WINDOW_DAYS,
            "count": len(alerts),
        },
        "alerts": alerts,
    }


def main() -> int:
    result = build()
    try:
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    except OSError as e:
        logger.error("[urgent_alerts] 쓰기 실패: %s", e)
        return 1
    print(f"[urgent_alerts] {result['_meta']['count']}건 → {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

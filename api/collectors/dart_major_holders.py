"""
dart_major_holders — KR 기관 대량보유(5%+) 수집 (DART majorstock.json).

action_queue d7158b4f. 대량보유상황보고서(5% 룰) 중 *기관* 보고자만 추출 →
기관 보유비율 + 최근 증감(accumulation/distribution) 신호.

⚠️ 관측 ONLY — 데이터 필드만 부착. 결정/점수 미반영 (RULE 7, 신규 신호).
   점수 편입은 사전등록([[project_observation_scoring_prereg_queue]]) + 검증 후.
   prior = 기관 보유/순매집 = smart-money flow (학술 mixed → 약 prior, 관측 우선).

source = DART majorstock.json (corp_code 필요). 실호출 검증 2026-06-07:
  국민연금공단 / BlackRock / Capital Group / Vanguard 등 기관 보고자 정상 노출.
필드: repror(보고자) / stkrt(보유비율%) / stkqy_irds(주식 증감) / rcept_dt(접수일).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

DART_URL = "https://opendart.fss.or.kr/api/majorstock.json"

# 기관 보고자 식별 키워드 (KR + 글로벌). 전략적 대주주/개인 제외 목적.
_INST_KEYWORDS = [
    "연금", "운용", "자산운용", "투자신탁", "투자자문", "캐피탈", "증권", "신탁",
    "사학연금", "공무원연금",
    "blackrock", "vanguard", "capital", "fidelity", "statestreet", "state street",
    "advisors", "advisers", "management", "asset", "investment", "norges",
    "templeton", "wellington", "trowe", "t.rowe", "gic", "fundadvisors",
]
# 명백 전략/사업회사 제외 (false positive 차단)
_EXCLUDE_HINTS = ["지주", "홀딩스", "holdings"]


def _is_institutional(name: str) -> bool:
    if not name:
        return False
    n = name.lower().replace(" ", "")
    if any(h in n for h in _EXCLUDE_HINTS):
        return False
    return any(k.replace(" ", "") in n for k in _INST_KEYWORDS)


def _to_float(s: Any) -> Optional[float]:
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def aggregate_holders(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """majorstock list → 기관별 최신 보유비율 + 최근 증감 집계.

    · 보고자별 최신(rcept_dt max) row = 현재 보유비율(stkrt).
    · 최근 증감 = 최신 row 의 stkqy_irds 부호 (+ 매집 / - 처분).
    · 관측 필드만 — 점수 미반영.
    """
    by_reporter: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        rep = (r.get("repror") or "").strip()
        if not rep or not _is_institutional(rep):
            continue
        dt = (r.get("rcept_dt") or "").strip()
        cur = by_reporter.get(rep)
        if cur is None or dt > cur.get("date", ""):
            by_reporter[rep] = {
                "reporter": rep,
                "pct": _to_float(r.get("stkrt")),
                "qty_change": _to_float(r.get("stkqy_irds")),
                "date": dt,
            }
    # 현재 5%+ 보유자만 (최신 보고 pct>0). pct=0 = 이미 처분 완료(5% 밑) → 현재 보유자 아님.
    holders = sorted(
        (h for h in by_reporter.values() if (h.get("pct") or 0) > 0),
        key=lambda x: (x.get("pct") or 0), reverse=True,
    )
    pcts = [h["pct"] for h in holders if h.get("pct") is not None]
    accum = sum(1 for h in holders if (h.get("qty_change") or 0) > 0)
    distrib = sum(1 for h in holders if (h.get("qty_change") or 0) < 0)
    return {
        "institutional_holders": holders,
        "n_institutions": len(holders),
        "total_institutional_pct": round(sum(pcts), 2) if pcts else None,
        "recent_accumulating": accum,
        "recent_distributing": distrib,
        "net_flow_direction": "accumulate" if accum > distrib else "distribute" if distrib > accum else "neutral",
    }


def fetch_major_holders(corp_code: str, api_key: str, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
    sess = session or requests.Session()
    try:
        r = sess.get(DART_URL, params={"crtfc_key": api_key, "corp_code": corp_code}, timeout=12)
        j = r.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("majorstock 실패 corp_code=%s: %s", corp_code, e)
        return None
    status = j.get("status")
    if status == "013":  # 조회 데이터 없음
        return {"_empty": True, "n_institutions": 0}
    if status != "000":
        logger.warning("majorstock status=%s (%s) corp_code=%s", status, j.get("message"), corp_code)
        return None
    return aggregate_holders(j.get("list", []) or [])


def analyze_all(stocks_dict: Dict[str, Any], api_key: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """stocks dict({ticker: {...}}) → {ticker6: 기관 대량보유 집계}. 관측 only."""
    api_key = api_key or os.environ.get("DART_API_KEY", "")
    if not api_key:
        logger.warning("DART_API_KEY 없음 — 대량보유 수집 skip")
        return {}
    from api.collectors.dart_corp_code import get_corp_code

    out: Dict[str, Dict[str, Any]] = {}
    sess = requests.Session()
    for ticker in stocks_dict:
        t6 = re.sub(r"\D", "", str(ticker)).zfill(6)[:6]
        if not t6 or t6 == "000000":
            continue
        corp_code = get_corp_code(t6)
        if not corp_code:
            continue
        res = fetch_major_holders(corp_code, api_key, sess)
        if res and not res.get("_empty"):
            out[t6] = res
    return out

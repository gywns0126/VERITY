"""
dart_cb_bw — 전환사채(CB)·신주인수권부사채(BW) 발행 → 희석 오버행 사실 추출.

한국 개인이 자주 당하는 리스크 = CB/BW 전환·행사 물량 오버행(잠재 희석). 토스·증권사가
종목 화면에 정규화해 주지 않는 KR 공시 사실 = VERITY 해자(1차자료 깊이).

🚨 사실만 (RULE 7): 발행규모·전환가/행사가·발행가능주식수·결의일 + 희석률(발행가능주식수 ÷
   발행주식수 = 표준 비율, 자기 산식 아님). 자체 점수·판단 0. LLM 0 (cvbdIsDecsn/bdwtIsDecsn
   구조화 파싱만). 관측 only — Brain 미반영.

⚠️ 캐비엇(정직): DART 발행 공시 기준 = 전환·상환·소각 미반영이라 "잠재 최대 희석"(오버행 상한).
   실제 미전환 잔량은 별도 추적 필요 → 노출 문구에 "발행 기준·전환 미반영" 명시 의무.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from api.config import now_kst

logger = logging.getLogger(__name__)

# 오버행 관측 창 — CB/BW 는 통상 만기 3~5년. 최근 3년 발행분을 활성 오버행 후보로 집계.
DEFAULT_WINDOW_YEARS = 3
# 캐시 재수집 주기 — 신규 발행 반영(주요사항보고는 수시). 7일 초과 시 refetch.
CACHE_TTL_DAYS = 7


def _cache_path() -> str:
    from api.config import DATA_DIR
    return os.path.join(DATA_DIR, "dart_cb_bw_cache.json")


def _parse_won(v: Any) -> Optional[int]:
    """DART 금액/수량 문자열('1,000,000' / '-' / '') → int. 실패 시 None."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace(" ", "")
    if not s or s in ("-", "해당사항없음", "부"):
        return None
    # 음수 표기('-' 접두 또는 괄호) 방어 — CB/BW 금액은 양수 기대, 이상치 None
    neg = s.startswith("(") or s.startswith("-")
    s = s.lstrip("(-").rstrip(")")
    try:
        n = int(float(s))
    except (TypeError, ValueError):
        return None
    return -n if neg else n


def _extract_instruments(cb_bw: Dict[str, List]) -> List[Dict[str, Any]]:
    """fetch_cb_bw 반환({cb:[...], bw:[...]}) → 통합 instrument 사실 리스트."""
    out: List[Dict[str, Any]] = []
    for row in (cb_bw.get("cb") or []):
        issuable = _parse_won(row.get("cvisstk_cnt"))
        out.append({
            "type": "CB",  # 전환사채
            "bond_kind": str(row.get("bd_tm") or "").strip(),
            "issue_amount": _parse_won(row.get("bd_fta")),      # 권면총액(원)
            "strike": _parse_won(row.get("cvprc")),             # 전환가액(원)
            "issuable_shares": issuable,                        # 전환 시 발행주식수
            "resolved_date": str(row.get("bddd") or "").strip(),
        })
    for row in (cb_bw.get("bw") or []):
        issuable = _parse_won(row.get("nstk_isstk_cnt"))
        out.append({
            "type": "BW",  # 신주인수권부사채
            "bond_kind": str(row.get("bd_tm") or "").strip(),
            "issue_amount": _parse_won(row.get("bd_fta")),
            "strike": _parse_won(row.get("ex_prc")),            # 행사가액(원)
            "issuable_shares": issuable,
            "resolved_date": str(row.get("bddd") or "").strip(),
        })
    # 최근 결의일 우선
    out.sort(key=lambda x: x.get("resolved_date") or "", reverse=True)
    return out


def _summarize(instruments: List[Dict[str, Any]], shares_outstanding: Optional[int]) -> Dict[str, Any]:
    total_issuable = sum((i.get("issuable_shares") or 0) for i in instruments)
    dilution_pct = None
    if shares_outstanding and shares_outstanding > 0 and total_issuable > 0:
        dilution_pct = round(total_issuable / shares_outstanding * 100, 2)
    return {
        "n_instruments": len(instruments),
        "total_issuable_shares": total_issuable or None,
        "dilution_pct": dilution_pct,   # 발행가능주식수 ÷ 발행주식수 (표준 비율)
        "instruments": instruments[:8],  # 최근 8건
    }


def analyze_all_cb_bw(
    stocks_dict: Dict[str, Any],
    window_years: int = DEFAULT_WINDOW_YEARS,
    force: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """stocks dict 일괄 CB/BW 오버행 사실 추출.

    stocks_dict[ticker] = {corp_code, shares_outstanding, name}.
    Returns: {ticker: {n_instruments, total_issuable_shares, dilution_pct, instruments, ...}}.
    instruments 없음 = 오버행 사실 없음(정상, out 에서 제외).
    """
    import json
    from datetime import timedelta

    from api.collectors.DartScout import fetch_cb_bw

    path = _cache_path()
    cache: Dict[str, Any] = {"updated_at": None, "by_ticker": {}}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    by_ticker: Dict[str, Any] = cache.get("by_ticker", {})

    now = now_kst()
    bgn_de = (now - timedelta(days=365 * window_years)).strftime("%Y%m%d")
    end_de = now.strftime("%Y%m%d")

    out: Dict[str, Dict[str, Any]] = {}
    new_count = cached_count = skipped = 0

    for ticker, sd in stocks_dict.items():
        corp_code = sd.get("corp_code")
        if not corp_code:
            skipped += 1
            continue
        shares = _parse_won(sd.get("shares_outstanding"))

        prev = by_ticker.get(ticker)
        fresh = False
        if prev and prev.get("as_of") and not force:
            try:
                age = now - now_kst().fromisoformat(prev["as_of"])
                fresh = age.days < CACHE_TTL_DAYS
            except (ValueError, TypeError):
                fresh = False
        if fresh:
            if prev.get("n_instruments"):
                out[ticker] = prev
            cached_count += 1
            continue

        try:
            cb_bw = fetch_cb_bw(str(corp_code), bgn_de, end_de)
        except Exception as e:  # noqa: BLE001 — 관측 파이프라인, 개별 실패 격리
            logger.warning("[cb_bw] fetch 실패(%s): %s", ticker, str(e)[:60])
            skipped += 1
            continue

        instruments = _extract_instruments(cb_bw or {})
        rec = {"ticker": ticker, "as_of": now.isoformat(), "window": f"{bgn_de}~{end_de}"}
        rec.update(_summarize(instruments, shares))
        # transient DART 빈응답(200-empty, 예외 아님)이 기존 오버행 사실을 덮어쓰지 않게:
        #   신규 0건 + 직전 보유분 있으면 직전 유지(발행 사실=전환·상환 전까지 존속). as_of 만 갱신.
        if not rec.get("n_instruments") and (prev or {}).get("n_instruments"):
            prev["as_of"] = now.isoformat()
            rec = prev
        by_ticker[ticker] = rec
        if rec.get("n_instruments"):
            out[ticker] = rec
        new_count += 1

    cache["by_ticker"] = by_ticker
    cache["updated_at"] = now.isoformat()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

    logger.info("[cb_bw] 신규 %d / 캐시 %d / skip %d / 오버행보유 %d",
                new_count, cached_count, skipped, len(out))
    return out

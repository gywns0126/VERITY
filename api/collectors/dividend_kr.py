"""
dividend_kr — KR 배당 수집기 (VAMS 보정수익률용)

전제:
  - VAMS 보유 종목의 "실제 수령 배당"을 배당락일(ex_date) 기준으로 기록.
  - 지급일이 아닌 배당락일을 채택한 이유:
    · 시장가격이 이미 배당락으로 조정됨 → 권리 확정 시점이 경제적 실체
    · compute_adjusted_return의 손실/배당 시차 왜곡 방지
  - announced(예상) / confirmed(주총 확정) 2단계 필드로 분리.

3티어 수집:
  · Tier 0  pykrx fundamental DPS          — 연간 확정액, fallback
  · Tier 1  DART alotMatter.json           — 공식 연간 배당 계획/확정 (sweep 1/15·7/15)
  · Tier 2  DART list.json 공시 필터        — "현금·현물배당 결정" 수시 탐지 (VAMS cycle)
  · Tier 3  refresh_on_ex_date(ticker)     — ex_date 당일 해당 종목만 갱신

산출: data/dividends_kr.json
  {
    "005930": [
      {
        "ex_date": "2025-12-29",
        "announced_amount_per_share": 361,
        "confirmed_amount_per_share": 361,
        "is_confirmed": true,
        "dividend_type": "year_end",       # year_end | interim | quarterly | special
        "payment_date": "2026-04-18",
        "source": "dart_decision",         # dart_decision | dart_alot | pykrx_dps
        "updated_at": "2026-04-22T00:36:00+09:00"
      }
    ]
  }

VAMS 연동은 api/vams/engine.py 의 run_vams_cycle 내부 훅 참조.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from api.config import DATA_DIR, now_kst

_DIVIDENDS_DB_PATH = os.path.join(DATA_DIR, "dividends_kr.json")

# 한글 카테고리 문자열에서 "보통주 현금배당" 항목을 식별
_CASH_DIVIDEND_PATTERNS = (
    "주당 현금배당금(원)",
    "주당현금배당금(원)",
    "주당 현금배당금",
    "주당현금배당금",
)
_COMMON_STOCK_HINT = "보통주"

# 공시 제목 필터 (Tier 2)
_DECISION_REPORT_RE = re.compile(r"(현금[·ㆍ]?\s*현물\s*)?배당\s*결정")


# ──────────────────────────────────────────────────────────────
# 파서 유틸
# ──────────────────────────────────────────────────────────────

def _parse_amount(s) -> Optional[float]:
    """'1,500 (보통주)' 같은 문자열에서 숫자만 추출. 실패 시 None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s) if s else None
    txt = str(s).replace(",", "").strip()
    m = re.search(r"[-+]?\d+(?:\.\d+)?", txt)
    if not m:
        return None
    try:
        v = float(m.group(0))
        return v if v > 0 else None
    except ValueError:
        return None


def _is_common_cash_dividend_row(row: dict) -> bool:
    """DART alotMatter 행이 '보통주 주당 현금배당금'인지 판단."""
    cat = str(row.get("category", ""))
    if not any(p in cat for p in _CASH_DIVIDEND_PATTERNS):
        return False
    # 우선주 등 분리 기재 시 카테고리에 '우선주' 포함. 보통주/명시 없음만 통과.
    if "우선주" in cat:
        return False
    return True


def _estimate_ex_date(bsns_year: int, dividend_type: str = "year_end") -> str:
    """결산월 기준 배당락일 추정 — 확정 공시 없을 때의 보수적 추정.
    한국 12월 결산 기준: 연말배당 배당락일은 12/30(거래일 마지막 날) 근처.
    """
    if dividend_type == "year_end":
        # 연말 마지막 영업일 가정 (12/30). 정확한 영업일 보정은 상위에서.
        return f"{bsns_year}-12-30"
    if dividend_type == "interim":
        return f"{bsns_year}-06-30"
    if dividend_type == "quarterly":
        # 기본값만 반환 — 실제는 Tier 2 공시 기반
        return f"{bsns_year}-03-31"
    return f"{bsns_year}-12-30"


# ──────────────────────────────────────────────────────────────
# DB I/O
# ──────────────────────────────────────────────────────────────

def load_dividends_db() -> Dict[str, List[dict]]:
    if not os.path.exists(_DIVIDENDS_DB_PATH):
        return {}
    try:
        with open(_DIVIDENDS_DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[dividend_kr] load 실패 (빈 DB 반환): {e}")
        return {}


def save_dividends_db(db: Dict[str, List[dict]]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = _DIVIDENDS_DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(tmp, _DIVIDENDS_DB_PATH)


def _upsert(db: Dict[str, List[dict]], ticker: str, record: dict) -> str:
    """ticker × ex_date 기준 upsert. 반환: 'insert' | 'update' | 'skip'."""
    arr = db.setdefault(ticker, [])
    ex = record.get("ex_date")
    if not ex:
        return "skip"
    for i, existing in enumerate(arr):
        if existing.get("ex_date") == ex:
            # 더 "신뢰도 높은" 소스나 confirmed 여부가 개선될 때만 덮어쓰기
            if _source_rank(record.get("source")) < _source_rank(existing.get("source")):
                return "skip"
            if existing.get("is_confirmed") and not record.get("is_confirmed"):
                return "skip"
            merged = {**existing, **record}
            arr[i] = merged
            return "update"
    arr.append(record)
    arr.sort(key=lambda r: r.get("ex_date", ""))
    return "insert"


_SOURCE_RANK = {"pykrx_dps": 0, "dart_alot": 1, "dart_decision": 2}
def _source_rank(src: Optional[str]) -> int:
    return _SOURCE_RANK.get(src or "", -1)


# ──────────────────────────────────────────────────────────────
# Tier 0 — pykrx fundamental DPS (fallback)
# ──────────────────────────────────────────────────────────────

def fetch_tier0_pykrx(ticker: str, year: Optional[int] = None) -> Optional[dict]:
    """pykrx 로 전년도 DPS 조회. 결산일은 12/30 배당락 가정.
    Tier 1/2 둘 다 실패 시 최후 폴백.
    """
    try:
        from pykrx import stock
    except ImportError:
        return None
    year = year or (now_kst().year - 1)
    tk = str(ticker).zfill(6)
    try:
        df = stock.get_market_fundamental_by_date(f"{year}1201", f"{year}1230", tk)
    except Exception as e:
        print(f"[dividend_kr/tier0] {ticker} pykrx 실패: {e}")
        return None
    if df is None or df.empty or "DPS" not in df.columns:
        return None
    dps_values = [v for v in df["DPS"].tolist() if v and v > 0]
    if not dps_values:
        return None
    dps = float(dps_values[-1])
    return {
        "ex_date": _estimate_ex_date(year, "year_end"),
        "announced_amount_per_share": dps,
        "confirmed_amount_per_share": dps,
        "is_confirmed": True,  # 과거 확정값
        "dividend_type": "year_end",
        "payment_date": None,
        "source": "pykrx_dps",
        "updated_at": now_kst().isoformat(),
    }


# ──────────────────────────────────────────────────────────────
# Tier 1 — DART alotMatter.json (연간 배당 계획/확정)
# ──────────────────────────────────────────────────────────────

def fetch_tier1_dart_annual(ticker: str, bsns_year: Optional[int] = None) -> Optional[dict]:
    """DART 사업보고서 배당정보 → 보통주 주당 현금배당.
    current(당기) 있으면 그 해 배당, previous(전기)로 fallback.
    배당락일은 결산월 말일 추정(정확한 ex_date 는 Tier 2/3 에서 덮어씀).
    """
    try:
        from api.collectors.DartScout import fetch_dividends
        from api.collectors.dart_corp_code import get_corp_code
        from api.config import DART_API_KEY
    except ImportError:
        return None
    if not DART_API_KEY:
        return None

    bsns_year = bsns_year or (now_kst().year - 1)
    corp_code = get_corp_code(str(ticker).zfill(6))
    if not corp_code:
        return None
    try:
        rows = fetch_dividends(corp_code, str(bsns_year))
    except Exception as e:
        print(f"[dividend_kr/tier1] {ticker} DART 실패: {e}")
        return None
    if not rows:
        return None

    amount = None
    for row in rows:
        if not _is_common_cash_dividend_row(row):
            continue
        # current 먼저 시도, 없으면 previous
        a = _parse_amount(row.get("current")) or _parse_amount(row.get("previous"))
        if a:
            amount = a
            break
    if amount is None:
        return None

    return {
        "ex_date": _estimate_ex_date(bsns_year, "year_end"),
        "announced_amount_per_share": amount,
        "confirmed_amount_per_share": amount,
        "is_confirmed": True,  # 사업보고서 기재 = 주총 확정 후
        "dividend_type": "year_end",
        "payment_date": None,
        "source": "dart_alot",
        "updated_at": now_kst().isoformat(),
    }


# ──────────────────────────────────────────────────────────────
# Tier 2 — DART 공시 검색 (현금·현물배당 결정)
# ──────────────────────────────────────────────────────────────

def fetch_tier2_dart_decisions(ticker: str, days_back: int = 14) -> List[dict]:
    """보유 종목의 최근 '현금·현물배당 결정' 공시 제목 탐지.
    공시 본문 파싱은 미구현 — 제목 매칭 + 접수일만 기록. 금액/ex_date는 Tier 1/0 과 병합.
    """
    try:
        from api.collectors.DartScout import fetch_disclosures
        from api.collectors.dart_corp_code import get_corp_code
        from api.config import DART_API_KEY
    except ImportError:
        return []
    if not DART_API_KEY:
        return []

    corp_code = get_corp_code(str(ticker).zfill(6))
    if not corp_code:
        return []

    end = now_kst().strftime("%Y%m%d")
    begin = (now_kst() - timedelta(days=days_back)).strftime("%Y%m%d")
    try:
        disclosures = fetch_disclosures(corp_code, begin, end)
    except Exception as e:
        print(f"[dividend_kr/tier2] {ticker} DART list 실패: {e}")
        return []

    out = []
    for d in disclosures:
        title = str(d.get("report_nm", ""))
        if not _DECISION_REPORT_RE.search(title):
            continue
        rcept = str(d.get("rcept_dt", ""))
        if len(rcept) != 8:
            continue
        rcept_iso = f"{rcept[0:4]}-{rcept[4:6]}-{rcept[6:8]}"
        # 제목으로 type 추정
        dtype = "year_end"
        if "중간" in title or "반기" in title:
            dtype = "interim"
        elif "분기" in title:
            dtype = "quarterly"
        elif "특별" in title:
            dtype = "special"
        out.append({
            "report_title": title,
            "decision_date": rcept_iso,
            "dividend_type": dtype,
        })
    return out


# ──────────────────────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────────────────────

def sweep_annual_plans(tickers: List[str], year: Optional[int] = None) -> Dict[str, str]:
    """Tier 1 전체 sweep — 1/15, 7/15 cron 용.
    반환: 티커별 "insert|update|skip|fail"
    """
    db = load_dividends_db()
    results: Dict[str, str] = {}
    for tk in tickers:
        rec = fetch_tier1_dart_annual(tk, year)
        if not rec:
            rec = fetch_tier0_pykrx(tk, year)
        if not rec:
            results[tk] = "fail"
            continue
        results[tk] = _upsert(db, tk, rec)
    save_dividends_db(db)
    return results


def poll_recent_decisions(tickers: List[str], days_back: int = 14) -> Dict[str, int]:
    """Tier 2 — VAMS 사이클 내부 호출. 최근 공시의 배당 결정 제목만 기록.
    실제 금액/ex_date 는 후속 Tier 1/3 호출로 보강.
    반환: 티커별 탐지된 공시 수.
    """
    db = load_dividends_db()
    hits: Dict[str, int] = {}
    for tk in tickers:
        decisions = fetch_tier2_dart_decisions(tk, days_back)
        if not decisions:
            continue
        hits[tk] = len(decisions)
        arr = db.setdefault(tk, [])
        # 공시 제목 메타만 별도 키로 기록 (배당 레코드와 혼재 방지 위해 마지막만 남김)
        meta = [d for d in arr if d.get("_meta") == "tier2_decisions"]
        if meta:
            meta[0].update({"recent_decisions": decisions, "_updated": now_kst().isoformat()})
        else:
            arr.append({
                "_meta": "tier2_decisions",
                "recent_decisions": decisions,
                "_updated": now_kst().isoformat(),
            })
    save_dividends_db(db)
    return hits


def refresh_on_ex_date(ticker: str) -> str:
    """Tier 3 — ex_date 당일 해당 종목만 최신 데이터로 업데이트."""
    db = load_dividends_db()
    rec = fetch_tier1_dart_annual(ticker) or fetch_tier0_pykrx(ticker)
    if not rec:
        return "fail"
    status = _upsert(db, ticker, rec)
    save_dividends_db(db)
    return status


# ──────────────────────────────────────────────────────────────
# VAMS 헬퍼
# ──────────────────────────────────────────────────────────────

def get_ex_dates_today(tickers: List[str], today: Optional[str] = None) -> List[dict]:
    """오늘(또는 지정일)이 ex_date 인 보유 종목의 배당 레코드 반환.
    VAMS run_vams_cycle 이 호출해서 dividend_received 를 누적.
    반환 스키마: [{ticker, ex_date, announced_amount_per_share, ...}, ...]
    """
    if today is None:
        today = now_kst().strftime("%Y-%m-%d")
    db = load_dividends_db()
    out = []
    for tk in tickers:
        for rec in db.get(tk, []):
            if rec.get("_meta"):  # 메타 레코드 건너뜀
                continue
            if rec.get("ex_date") == today:
                out.append({"ticker": tk, **rec})
    return out


def reconcile_confirmed(tickers: List[str]) -> Dict[str, str]:
    """주 1회 — announced 만 있고 confirmed 안 된 레코드를 Tier 1 재호출로 갱신.
    사업보고서가 최근 올라왔으면 is_confirmed=True 로 승격.
    """
    db = load_dividends_db()
    results: Dict[str, str] = {}
    for tk in tickers:
        arr = db.get(tk, [])
        unconfirmed = [r for r in arr if not r.get("_meta") and not r.get("is_confirmed")]
        if not unconfirmed:
            continue
        rec = fetch_tier1_dart_annual(tk)
        if not rec:
            results[tk] = "no_update"
            continue
        results[tk] = _upsert(db, tk, rec)
    save_dividends_db(db)
    return results

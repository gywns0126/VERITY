"""us_quarterly_public_builder — 미장 분기 재무 비율 추이 public 빌더 (PublicQuarterlyTrend 재사용).

입력: data/us_financials/{TICKER}.json series_quarterly (SEC EDGAR XBRL).
출력: data/us_quarterly_public.json — KR dart_quarterly_public.json 과 동일 스키마
  {stocks: {ticker: {quarters: [{q, debt_ratio, roa, current_ratio, gross_margin, asset_turnover}]}}}
  → PublicQuarterlyTrend 컴포넌트 무변환 재사용(quarterlyUrl 만 US 로).

🚨 RULE 7 — 계산된 사실 비율만(점수·등급 0). 순수 변환 — 외부호출 0.
publish: data/us_quarterly_public.json (action.yml 등재).
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIN_DIR = os.path.join(_ROOT, "data", "us_financials")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_quarterly_public.json")
MIN_PUBLISH_QUARTERS = 1
MIN_TREND_QUARTERS = 4
_FLOW_KEYS = ("revenue", "net_income", "operating_income", "gross_profit")
_INSTANT_KEYS = ("total_assets", "current_assets", "current_liabilities",
                 "total_liabilities", "stockholders_equity")
_RATIO_KEYS = ("debt_ratio", "roa", "current_ratio", "gross_margin",
               "asset_turnover", "operating_margin", "net_margin", "roe")


def _now_kst() -> datetime:
    return datetime.now(KST)


def _by_end(series: Any, annual: bool) -> Dict[str, Dict[str, Any]]:
    """Metric rows → latest accession per end for annual or quarterly values."""
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(series, list):
        return out
    for e in series:
        if (not isinstance(e, dict) or bool(e.get("is_annual")) != annual
                or e.get("val") is None):
            continue
        end = str(e.get("end") or "")
        if not end:
            continue
        try:
            row = dict(e)
            row["val"] = float(e.get("val"))
        except (TypeError, ValueError):
            continue
        old = out.get(end)
        if old is None or (str(row.get("filed") or ""), str(row.get("accn") or "")) > (
                str(old.get("filed") or ""), str(old.get("accn") or "")):
            out[end] = row
    return out


def _value(rows: Dict[str, Dict[str, Any]], end: str) -> Optional[float]:
    row = rows.get(end)
    return float(row["val"]) if row and row.get("val") is not None else None


def _source_url(cik: Any, accession: Any) -> Optional[str]:
    try:
        cik_num = int(cik)
    except (TypeError, ValueError):
        return None
    # Company Facts does not expose primaryDocument and the accession prefix
    # is not always the registrant CIK.  Use the stable SEC company page unless
    # the direct inline fallback supplied an exact filing URL.
    return (f"https://www.sec.gov/edgar/browse/?CIK={cik_num}"
            "&owner=exclude&action=getcompany")


def _evidence(row: Optional[Dict[str, Any]], cik: Any) -> Dict[str, Any]:
    if not row:
        return {}
    out = {
        "fiscal_year": row.get("fy"),
        "fiscal_period": row.get("fp"),
        "form": row.get("form"),
        "filed": row.get("filed"),
        "accession": row.get("accn"),
    }
    url = row.get("source_url") or _source_url(cik, row.get("accn"))
    if url:
        out["source_url"] = url
    return {k: v for k, v in out.items() if v not in (None, "")}


def _derive_fiscal_q4(
    annual_rows: Dict[str, Dict[str, Any]],
    quarterly_rows: Dict[str, Dict[str, Any]],
    end: str,
    previous_end: str,
) -> Optional[float]:
    """Standalone fiscal Q4 = FY − reported Q1 − Q2 − Q3."""
    annual_value = _value(annual_rows, end)
    if annual_value is None or not previous_end:
        return None
    parts = [row for q_end, row in quarterly_rows.items()
             if previous_end < q_end < end and row.get("fp") in {"Q1", "Q2", "Q3"}]
    by_fp = {str(row.get("fp")): row for row in parts}
    if set(by_fp) != {"Q1", "Q2", "Q3"}:
        return None
    return annual_value - sum(float(by_fp[fp]["val"]) for fp in ("Q1", "Q2", "Q3"))


def _previous_fiscal_year_end(ends: List[str], end: str) -> str:
    try:
        current = datetime.strptime(end, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return ""
    for candidate in reversed([value for value in ends if value < end]):
        try:
            days = (current - datetime.strptime(candidate, "%Y-%m-%d").date()).days
        except (TypeError, ValueError):
            continue
        if 300 <= days <= 430:
            return candidate
    return ""


def _ratios(values: Dict[str, Optional[float]]) -> Dict[str, float]:
    rev = values.get("revenue")
    ni = values.get("net_income")
    oi = values.get("operating_income")
    ta = values.get("total_assets")
    ca = values.get("current_assets")
    cl = values.get("current_liabilities")
    tl = values.get("total_liabilities")
    eq = values.get("stockholders_equity")
    gp = values.get("gross_profit")
    out: Dict[str, float] = {}
    for key, value in (
        ("debt_ratio", _ratio(tl, eq, 100.0, 0, 100000)),
        ("roa", _ratio(ni, ta, 100.0, -500, 500)),
        ("current_ratio", _ratio(ca, cl, 100.0, 0, 100000)),
        ("gross_margin", _ratio(gp, rev, 100.0, -1000, 100)),
        ("asset_turnover", _ratio(rev, ta, 1.0, 0, 100)),
        ("operating_margin", _ratio(oi, rev, 100.0, -1000, 100)),
        ("net_margin", _ratio(ni, rev, 100.0, -1000, 100)),
        ("roe", _ratio(ni, eq, 100.0, -500, 500)),
    ):
        if value is not None:
            out[key] = value
    return out


def _ratio(num: Optional[float], den: Optional[float], scale: float = 100.0,
           lo: float = -1e9, hi: float = 1e9) -> Optional[float]:
    if num is None or den in (None, 0):
        return None
    try:
        v = (num / den) * scale
    except ZeroDivisionError:
        return None
    if v != v or v < lo or v > hi:
        return None
    return round(v, 2)


def _quarters_for(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    sq = doc.get("series_quarterly") or {}
    sa = doc.get("series_annual") or {}
    q_maps = {key: _by_end(sq.get(key), annual=False)
              for key in (*_FLOW_KEYS, *_INSTANT_KEYS)}
    a_maps = {key: _by_end(sa.get(key), annual=True)
              for key in (*_FLOW_KEYS, *_INSTANT_KEYS)}
    ends = sorted(set().union(*(set(rows) for rows in q_maps.values())))
    quarters: List[Dict[str, Any]] = []
    for end in ends:
        q: Dict[str, Any] = {"q": end}
        values = {key: _value(rows, end) for key, rows in q_maps.items()}
        q.update(_ratios(values))
        sources = [rows[end] for rows in q_maps.values() if end in rows]
        source = max(sources, key=lambda row: (str(row.get("filed") or ""),
                                               str(row.get("accn") or "")), default=None)
        q.update(_evidence(source, (doc.get("meta") or {}).get("cik")))
        q["period_kind"] = "reported_quarter"
        # 적어도 1개 비율이 있어야 분기 수록
        if any(key in q for key in _RATIO_KEYS):
            quarters.append(q)

    # Fiscal year-end has no 10-Q.  Balance-sheet ratios are reported 10-K
    # values; flow ratios use a standalone Q4 only when FY-Q1-Q2-Q3 is exact.
    annual_ends = sorted(set().union(*(set(rows) for rows in a_maps.values())))
    existing_ends = {row["q"] for row in quarters}
    for end in annual_ends:
        if end in existing_ends:
            continue
        previous_end = _previous_fiscal_year_end(annual_ends, end)
        values: Dict[str, Optional[float]] = {
            key: _value(a_maps[key], end) for key in _INSTANT_KEYS
        }
        derived_keys: List[str] = []
        for key in _FLOW_KEYS:
            value = _derive_fiscal_q4(a_maps[key], q_maps[key], end, previous_end)
            values[key] = value
            if value is not None:
                derived_keys.append(key)
        q = {"q": end, **_ratios(values)}
        if not any(key in q for key in _RATIO_KEYS):
            continue
        annual_sources = [rows[end] for rows in a_maps.values() if end in rows]
        source = max(annual_sources,
                     key=lambda row: (str(row.get("filed") or ""),
                                      str(row.get("accn") or "")), default=None)
        q.update(_evidence(source, (doc.get("meta") or {}).get("cik")))
        q["fiscal_period"] = "Q4"
        q["period_kind"] = "derived_fiscal_q4" if derived_keys else "reported_year_end_balance"
        if derived_keys:
            q["derivation"] = "FY-Q1-Q2-Q3"
            q["derived_metrics"] = derived_keys
        quarters.append(q)
    return quarters


def _merge_quarters(old: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_end = {str(row.get("q")): dict(row) for row in old if isinstance(row, dict) and row.get("q")}
    for row in new:
        end = str(row.get("q") or "")
        if not end:
            continue
        merged = by_end.get(end, {})
        merged.update({k: v for k, v in row.items() if v is not None})
        by_end[end] = merged
    return [by_end[end] for end in sorted(by_end)]


def build() -> Dict[str, Any]:
    stocks: Dict[str, Any] = {}
    for path in glob.glob(os.path.join(FIN_DIR, "*.json")):
        base = os.path.basename(path)
        if base.startswith("_"):   # _summary.json 등 제외
            continue
        ticker = base[:-5]
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = json.load(f) or {}
        except (OSError, json.JSONDecodeError):
            continue
        qs = _quarters_for(doc)
        if len(qs) >= MIN_PUBLISH_QUARTERS:
            stocks[ticker] = {
                "quarters": qs,
                "quarter_count": len(qs),
                "trend_ready": len(qs) >= MIN_TREND_QUARTERS,
                "latest_filing_sync": (doc.get("meta") or {}).get("latest_filing_sync"),
            }
    return {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "SEC EDGAR XBRL (us_financials series_quarterly)",
            "count": len(stocks),
            "publish_min_quarters": MIN_PUBLISH_QUARTERS,
            "trend_min_quarters": MIN_TREND_QUARTERS,
            "note": "분기 재무 비율 사실(부채비율/ROA/유동비율/매출총이익률/자산회전율/영업이익률/순이익률/ROE) — 점수·등급 0 (RULE 7).",
        },
        "stocks": stocks,
    }


def main() -> int:
    ok = False
    try:
        if not os.path.isdir(FIN_DIR):
            print(f"[us_quarterly_public] {FIN_DIR} 부재 — skip", file=sys.stderr)
            return 0
        out = build()
        if not out["stocks"] and os.path.isfile(OUTPUT_PATH):
            print("[us_quarterly_public] 0 stocks — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0
        # sticky merge — CI per-ticker 캐시는 그 run 재수집분만 존재. 부분 재빌드가 전량본을
        # 덮어쓴 실사고(2026-07-11 incremental: 1,494→10종, 분기추이 카드 전멸). 기존 유지 + 신규만 갱신.
        if os.path.isfile(OUTPUT_PATH):
            try:
                with open(OUTPUT_PATH, encoding="utf-8") as _f:
                    prev = (json.load(_f) or {}).get("stocks") or {}
            except (OSError, ValueError):
                prev = {}
            fresh = out["stocks"]
            kept = sum(1 for t in prev if t not in fresh)
            merged = dict(prev)
            for ticker, record in fresh.items():
                old_record = prev.get(ticker) if isinstance(prev.get(ticker), dict) else {}
                quarters = _merge_quarters(old_record.get("quarters") or [],
                                           record.get("quarters") or [])
                merged[ticker] = {**old_record, **record, "quarters": quarters,
                                  "quarter_count": len(quarters),
                                  "trend_ready": len(quarters) >= MIN_TREND_QUARTERS}
            out["stocks"] = merged
            out["_meta"]["count"] = len(out["stocks"])
            out["_meta"]["fresh_this_run"] = len(fresh)
            if kept:
                print(f"[us_quarterly_public] sticky merge — 기존 {kept} 유지 + 신규 {len(fresh)}", file=sys.stderr)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[us_quarterly_public] logged=True · {len(out['stocks'])} 종목 -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[us_quarterly_public] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[us_quarterly_public] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

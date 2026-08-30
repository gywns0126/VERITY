"""종목별 변경·사업·고용·자본조달 사실을 공개용 단일 계약으로 조인한다.

외부 호출은 없다. 기존 공개 산출물과 로컬 시계열만 읽으며 점수·등급·추천을 만들지 않는다.
출력은 종목별 현재 상태와 비교 기준일을 함께 기록해 화면이 없는 정밀도를 만들지 않게 한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUTPUT_DIR = DATA / "stock_change_public"
BUSINESS_STATE_PATH = DATA / "metadata" / "business_overview_state.json"
PORTFOLIO_EXPOSURE_PATH = DATA / "portfolio_exposure_map.json"

KST = timezone(timedelta(hours=9))

REPORT_PATH = DATA / "stock_report_public.json"
US_REPORT_PATH = DATA / "us_stock_report_public.json"
BUSINESS_PATH = DATA / "kr_business_overview_public.json"
EMPLOYMENT_PATH = DATA / "nps_employment.json"
EMPLOYMENT_HISTORY_PATH = DATA / "nps_employment_history.jsonl"
DISCLOSURE_PATH = DATA / "public_disclosure_feed.json"
FORENSICS_PATH = DATA / "disclosure_forensics.json"
KR_FORENSICS_PATH = DATA / "kr_forensics_public.json"
STOCK_HISTORY_DIR = DATA / "stock_history"

CHANGE_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("price", "가격"),
    ("market_cap", "시가총액"),
    ("per", "PER"),
    ("pbr", "PBR"),
    ("eps", "EPS"),
    ("roe", "ROE"),
    ("debt_ratio", "부채비율"),
    ("operating_margin", "영업이익률"),
    ("revenue_growth", "매출성장률"),
    ("shares_outstanding", "발행주식수"),
)

DILUTION_CATEGORIES = {
    "유상증자",
    "전환사채(CB)",
    "신주인수권부사채(BW)",
    "교환사채(EB)",
    "감자",
    "자기주식처분",
    "정정공시",
}


def _load_json(path: Path, default: Any) -> Any:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _write_public_chunks(output: Mapping[str, Any]) -> None:
    """티커 앞 세 자리 단위로 나눠 종목 화면이 전체 유니버스를 받지 않게 한다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    chunks: Dict[str, Dict[str, Any]] = defaultdict(dict)
    for ticker, row in (output.get("stocks") or {}).items():
        chunks[str(ticker)[:3]][str(ticker)] = row
    expected = {"_summary.json"}
    for prefix, rows in chunks.items():
        name = f"{prefix}.json"
        expected.add(name)
        _atomic_json(OUTPUT_DIR / name, {"stocks": rows})
    _atomic_json(OUTPUT_DIR / "_summary.json", {"_meta": output.get("_meta") or {}})
    for path in OUTPUT_DIR.glob("*.json"):
        if path.name not in expected:
            path.unlink()


def _write_portfolio_exposure_map(kr_payload: Mapping[str, Any], us_payload: Mapping[str, Any]) -> None:
    rows: Dict[str, Dict[str, str]] = {}
    for item in list(kr_payload.get("stocks") or []) + list(us_payload.get("stocks") or []):
        if not isinstance(item, Mapping):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        overview = item.get("overview") if isinstance(item.get("overview"), Mapping) else {}
        peer = item.get("peer") if isinstance(item.get("peer"), Mapping) else {}
        rows[ticker] = {
            "name": str(item.get("name_ko") or item.get("name") or ticker),
            "market": str(item.get("market") or ""),
            "sector": str(overview.get("sector") or peer.get("sector") or item.get("business") or ""),
        }
    _atomic_json(
        PORTFOLIO_EXPOSURE_PATH,
        {
            "_meta": {
                "count": len(rows),
                "sector_mapped": sum(bool(row["sector"]) for row in rows.values()),
                "kr_generated_at": str((kr_payload.get("_meta") or {}).get("generated_at") or ""),
                "us_generated_at": str((us_payload.get("_meta") or {}).get("generated_at") or ""),
            },
            "stocks": rows,
        },
    )


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _pct_change(before: float, after: float) -> Optional[float]:
    if before == 0:
        return None
    return round((after - before) / abs(before) * 100, 2)


def _iso_date(value: Any) -> str:
    text = str(value or "")
    return text[:10] if len(text) >= 10 else text


def _read_latest_daily_snapshots() -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """종목별 최근 서로 다른 거래일 2개를 보존한다."""
    files = sorted(STOCK_HISTORY_DIR.glob("*.jsonl"))
    by_ticker_day: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    parsed = 0
    rejected = 0
    for path in files:
        try:
            fh = path.open(encoding="utf-8")
        except OSError:
            continue
        with fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    rejected += 1
                    continue
                ticker = str(row.get("ticker") or "").strip().upper()
                day = _iso_date(row.get("ts"))
                if not ticker or not day:
                    rejected += 1
                    continue
                parsed += 1
                current = by_ticker_day[ticker].get(day)
                if current is None or str(row.get("ts") or "") > str(current.get("ts") or ""):
                    by_ticker_day[ticker][day] = row

    out: Dict[str, List[Dict[str, Any]]] = {}
    for ticker, days in by_ticker_day.items():
        latest_days = sorted(days)[-2:]
        out[ticker] = [days[day] for day in latest_days]
    meta = {
        "files": len(files),
        "rows_parsed": parsed,
        "rows_rejected": rejected,
        "tickers": len(out),
        "tickers_with_pair": sum(len(rows) == 2 for rows in out.values()),
    }
    return out, meta


def _market_changes(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(rows) < 2:
        latest = rows[-1] if rows else {}
        return {
            "status": "insufficient_history",
            "as_of": _iso_date(latest.get("ts")),
            "previous_as_of": None,
            "fields": [],
        }
    before, after = rows[-2], rows[-1]
    changes: List[Dict[str, Any]] = []
    for key, label in CHANGE_FIELDS:
        b = _as_number(before.get(key))
        a = _as_number(after.get(key))
        if b is None or a is None or math.isclose(b, a, rel_tol=1e-12, abs_tol=1e-12):
            continue
        changes.append(
            {
                "key": key,
                "label": label,
                "before": b,
                "after": a,
                "delta": round(a - b, 6),
                "delta_pct": _pct_change(b, a),
            }
        )
    return {
        "status": "changed" if changes else "unchanged",
        "as_of": _iso_date(after.get("ts")),
        "previous_as_of": _iso_date(before.get("ts")),
        "fields": changes,
        "source": "data/stock_history 일별 스냅샷",
    }


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?다요])\s+")


def _sentences(text: str) -> List[str]:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if not compact:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT.split(compact) if len(s.strip()) >= 12]


def _hash_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _business_comparison(current: Mapping[str, Any], previous: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    current_text = str(current.get("text") or "")
    current_view = {
        "fiscal_year": str(current.get("fiscal_year") or ""),
        "filed_at": str(current.get("filed_at") or ""),
        "report": str(current.get("report") or ""),
        "text": current_text,
        "truncated": bool(current.get("truncated")),
        "url": str(current.get("url") or ""),
        "hash": _hash_text(current_text),
    }
    if not previous:
        return {"status": "baseline", "current": current_view, "previous": None, "added": [], "removed": []}
    previous_text = str(previous.get("text") or "")
    previous_view = {
        "fiscal_year": str(previous.get("fiscal_year") or ""),
        "filed_at": str(previous.get("filed_at") or ""),
        "report": str(previous.get("report") or ""),
        "text": previous_text,
        "truncated": bool(previous.get("truncated")),
        "url": str(previous.get("url") or ""),
        "hash": str(previous.get("hash") or _hash_text(previous_text)),
    }
    current_sent = _sentences(current_text)
    previous_sent = _sentences(previous_text)
    current_set, previous_set = set(current_sent), set(previous_sent)
    added = [s for s in current_sent if s not in previous_set][:5]
    removed = [s for s in previous_sent if s not in current_set][:5]
    changed = current_view["hash"] != previous_view["hash"]
    return {
        "status": "changed" if changed else "unchanged",
        "current": current_view,
        "previous": previous_view,
        "added": added,
        "removed": removed,
    }


def _employment_history() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """종목별 보존 월을 모두 읽는다. 최신 스냅샷 파일보다 history가 앞선 경우도 흡수한다."""
    out: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    try:
        fh = EMPLOYMENT_HISTORY_PATH.open(encoding="utf-8")
    except OSError:
        return out
    with fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            ym = str(row.get("ym") or "")
            ticker = str(row.get("ticker") or "").strip()
            if ticker and len(ym) == 6 and ym.isdigit():
                out[ticker][ym] = row
    return out


def _growth(before: Optional[float], after: Optional[float]) -> Optional[float]:
    if before is None or after is None or before == 0:
        return None
    return round((after - before) / abs(before) * 100, 1)


def _employment_performance(
    ticker: str,
    employment: Optional[Mapping[str, Any]],
    history: Mapping[str, Mapping[str, Mapping[str, Any]]],
    latest_ym: str,
    fin_series: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    monthly = dict(history.get(ticker) or {})
    current_file_ym = str((employment or {}).get("ym") or latest_ym or "")
    if current_file_ym:
        monthly[current_file_ym] = {
            "ym": current_file_ym,
            "cnt": (employment or {}).get("jnngp_cnt"),
            "hire": (employment or {}).get("hire"),
            "leave": (employment or {}).get("leave"),
            "net": (employment or {}).get("net"),
        }
    months = sorted(monthly)
    current_ym = months[-1] if months else current_file_ym
    previous_ym = months[-2] if len(months) >= 2 else ""
    current_row = monthly.get(current_ym) or {}
    previous_row = monthly.get(previous_ym) or {}
    current_count = _as_number(current_row.get("cnt"))
    previous_count = _as_number(previous_row.get("cnt"))
    current_hire = _as_number(current_row.get("hire"))
    current_leave = _as_number(current_row.get("leave"))
    current_net = _as_number(current_row.get("net"))
    if current_net is None and current_hire is not None and current_leave is not None:
        current_net = current_hire - current_leave
    fin = [dict(row) for row in fin_series if isinstance(row, Mapping) and row.get("year") is not None]
    fin.sort(key=lambda row: int(row.get("year") or 0))
    latest_fin = fin[-1] if fin else None
    previous_fin = fin[-2] if len(fin) >= 2 else None
    emp_growth = _growth(previous_count, current_count)
    revenue_growth = _growth(
        _as_number((previous_fin or {}).get("revenue")),
        _as_number((latest_fin or {}).get("revenue")),
    )
    op_growth = _growth(
        _as_number((previous_fin or {}).get("op")),
        _as_number((latest_fin or {}).get("op")),
    )
    directions = [x for x in (emp_growth, revenue_growth, op_growth) if x is not None]
    relation = "insufficient"
    if len(directions) == 3:
        signs = [0 if x == 0 else 1 if x > 0 else -1 for x in directions]
        relation = "same_direction" if len(set(signs)) == 1 else "mixed_direction"
    return {
        "status": "ready" if current_count is not None and latest_fin else "partial",
        "employment": {
            "as_of": current_ym or None,
            "count": current_count,
            "previous_as_of": previous_ym or None,
            "previous_count": previous_count,
            "growth_pct": emp_growth,
            "hire": current_hire,
            "leave": current_leave,
            "net": current_net,
            "source": "국민연금공단 가입 사업장",
        },
        "performance": {
            "as_of": (latest_fin or {}).get("year"),
            "previous_as_of": (previous_fin or {}).get("year"),
            "revenue": _as_number((latest_fin or {}).get("revenue")),
            "revenue_previous": _as_number((previous_fin or {}).get("revenue")),
            "revenue_growth_pct": revenue_growth,
            "operating_profit": _as_number((latest_fin or {}).get("op")),
            "operating_profit_previous": _as_number((previous_fin or {}).get("op")),
            "operating_profit_growth_pct": op_growth,
            "source": "DART 연간 재무",
        },
        "relationship": relation,
        "note": "고용과 실적의 방향을 나란히 놓은 사실 비교이며 인과관계나 전망이 아니다.",
    }


def _index_disclosures(payload: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in payload.get("items") or []:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "").strip()
        if ticker:
            out[ticker] = [dict(item) for item in row.get("disclosures") or [] if isinstance(item, Mapping)]
    return out


def _index_forensics(payload: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    stocks = payload.get("stocks") or []
    if isinstance(stocks, Mapping):
        return {str(k): dict(v) for k, v in stocks.items() if isinstance(v, Mapping)}
    out: Dict[str, Dict[str, Any]] = {}
    for row in stocks:
        if isinstance(row, Mapping) and row.get("ticker"):
            out[str(row["ticker"])] = dict(row)
    return out


def _capital_timeline(row: Optional[Mapping[str, Any]], detail: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    events = []
    for event in (row or {}).get("events") or []:
        if not isinstance(event, Mapping) or str(event.get("category") or "") not in DILUTION_CATEGORIES:
            continue
        events.append(
            {
                "date": str(event.get("date") or ""),
                "category": str(event.get("category") or ""),
                "title": str(event.get("title") or ""),
                "is_correction": bool(event.get("is_correction")),
                "source_url": str(event.get("source_url") or ""),
            }
        )
    events.sort(key=lambda event: event["date"], reverse=True)
    cb = (detail or {}).get("cb_bw") if isinstance(detail, Mapping) else None
    instruments = []
    if isinstance(cb, Mapping):
        instruments = [dict(item) for item in cb.get("instruments") or [] if isinstance(item, Mapping)]
    return {
        "status": "ready" if events or instruments else "no_record",
        "events": events[:20],
        "event_total": len(events),
        "instruments": instruments,
        "dilution_pct": (cb or {}).get("dilution_pct") if isinstance(cb, Mapping) else None,
        "note": (cb or {}).get("note") if isinstance(cb, Mapping) else "공시 제목 분류 이력이며 현재 잔존 물량 확정값이 아니다.",
    }


def build(write: bool = True, update_state: bool = True, use_previous_state: bool = True) -> Dict[str, Any]:
    now = datetime.now(KST).isoformat(timespec="seconds")
    report_payload = _load_json(REPORT_PATH, {})
    us_report_payload = _load_json(US_REPORT_PATH, {})
    reports = [row for row in report_payload.get("stocks") or [] if isinstance(row, Mapping)]
    report_map = {str(row.get("ticker") or "").strip(): row for row in reports if row.get("ticker")}
    business_payload = _load_json(BUSINESS_PATH, {})
    business_rows = business_payload.get("rows") or {}
    employment_payload = _load_json(EMPLOYMENT_PATH, {})
    employment_rows = employment_payload.get("stocks") or {}
    employment_meta = employment_payload.get("_meta") or {}
    latest_ym = str(employment_meta.get("data_ym_latest") or "")
    employment_history = _employment_history()
    disclosures_payload = _load_json(DISCLOSURE_PATH, {})
    disclosures = _index_disclosures(disclosures_payload)
    forensic_rows = _index_forensics(_load_json(FORENSICS_PATH, {}))
    kr_forensic_rows = _index_forensics(_load_json(KR_FORENSICS_PATH, {}))
    snapshots, snapshot_meta = _read_latest_daily_snapshots()
    previous_state = _load_json(BUSINESS_STATE_PATH, {}).get("rows") or {} if use_previous_state else {}

    stocks: Dict[str, Dict[str, Any]] = {}
    next_state: Dict[str, Dict[str, Any]] = {}
    for ticker, report in report_map.items():
        business = business_rows.get(ticker) if isinstance(business_rows, Mapping) else None
        business_cmp = _business_comparison(business, previous_state.get(ticker)) if isinstance(business, Mapping) else {
            "status": "missing",
            "current": None,
            "previous": previous_state.get(ticker),
            "added": [],
            "removed": [],
        }
        if isinstance(business, Mapping):
            next_state[ticker] = {
                "fiscal_year": str(business.get("fiscal_year") or ""),
                "filed_at": str(business.get("filed_at") or ""),
                "report": str(business.get("report") or ""),
                "text": str(business.get("text") or ""),
                "truncated": bool(business.get("truncated")),
                "url": str(business.get("url") or ""),
                "hash": _hash_text(str(business.get("text") or "")),
            }
        daily = _market_changes(snapshots.get(ticker, []))
        latest_disclosures = disclosures.get(ticker, [])
        latest_day = str((disclosures_payload.get("_meta") or {}).get("generated_at") or "")[:10]
        daily["disclosures"] = [
            {
                "date": str(item.get("date") or ""),
                "title": str(item.get("title") or ""),
                "label": str(item.get("label") or "공시"),
                "source_url": str(item.get("source_url") or ""),
                "is_correction": bool(item.get("is_correction")),
            }
            for item in latest_disclosures
            if str(item.get("date") or "") == latest_day
        ]
        employment = _employment_performance(
            ticker,
            employment_rows.get(ticker) if isinstance(employment_rows, Mapping) else None,
            employment_history,
            latest_ym,
            report.get("fin_series") or [],
        )
        capital = _capital_timeline(forensic_rows.get(ticker), kr_forensic_rows.get(ticker))
        coverage = {
            "daily_pair": daily.get("status") != "insufficient_history",
            "business_report": business_cmp.get("current") is not None,
            "business_previous": business_cmp.get("previous") is not None,
            "employment": employment.get("employment", {}).get("count") is not None,
            "financial_pair": employment.get("performance", {}).get("previous_as_of") is not None,
            "capital_history": capital.get("status") == "ready",
        }
        stocks[ticker] = {
            "ticker": ticker,
            "name": str(report.get("name") or ticker),
            "market": str(report.get("market") or "KR"),
            "today": daily,
            "business_report": business_cmp,
            "employment_performance": employment,
            "capital_timeline": capital,
            "coverage": {
                "hit": sum(bool(v) for v in coverage.values()),
                "total": len(coverage),
                "fields": coverage,
            },
        }

    output = {
        "_meta": {
            "generated_at": now,
            "source": "기존 공개 산출물 조인 · 외부 호출 0 · 점수/추천 0",
            "count": len(stocks),
            "sources": {
                "market_changes": str(STOCK_HISTORY_DIR.relative_to(ROOT)),
                "business": str(BUSINESS_PATH.relative_to(ROOT)),
                "employment": str(EMPLOYMENT_PATH.relative_to(ROOT)),
                "employment_history": str(EMPLOYMENT_HISTORY_PATH.relative_to(ROOT)),
                "financials": str(REPORT_PATH.relative_to(ROOT)),
                "capital": [str(FORENSICS_PATH.relative_to(ROOT)), str(KR_FORENSICS_PATH.relative_to(ROOT))],
            },
            "denominators": {
                "report_universe": len(report_map),
                "daily_pair": sum(1 for row in stocks.values() if row["today"].get("status") != "insufficient_history"),
                "business_current": sum(1 for row in stocks.values() if row["business_report"].get("current")),
                "business_previous": sum(1 for row in stocks.values() if row["business_report"].get("previous")),
                "employment": sum(1 for row in stocks.values() if row["employment_performance"]["employment"].get("count") is not None),
                "employment_month_pair": sum(
                    1
                    for row in stocks.values()
                    if row["employment_performance"]["employment"].get("previous_count") is not None
                ),
                "employment_financial_pair": sum(
                    1
                    for row in stocks.values()
                    if row["employment_performance"]["employment"].get("count") is not None
                    and row["employment_performance"]["performance"].get("previous_as_of") is not None
                ),
                "capital_history": sum(1 for row in stocks.values() if row["capital_timeline"].get("status") == "ready"),
            },
            "snapshot_scan": snapshot_meta,
            "note": "오늘은 최신 두 거래일 비교를 뜻한다. 각 종목의 as_of와 previous_as_of를 화면에 함께 표시해야 한다.",
        },
        "stocks": stocks,
    }
    if write:
        _write_public_chunks(output)
        _write_portfolio_exposure_map(report_payload, us_report_payload)
        if update_state and next_state != previous_state:
            _atomic_json(
                BUSINESS_STATE_PATH,
                {
                    "_meta": {"updated_at": now, "count": len(next_state)},
                    "rows": next_state,
                },
            )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-state-update", action="store_true")
    parser.add_argument("--ignore-previous-state", action="store_true")
    args = parser.parse_args()
    output = build(
        write=not args.dry_run,
        update_state=not args.no_state_update,
        use_previous_state=not args.ignore_previous_state,
    )
    print(json.dumps(output["_meta"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

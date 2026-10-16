"""us_financials_incremental — 미장 재무 이벤트 기반 증분 갱신 (2026-07-04 신선도 스프린트).

배경: 미장 재무 풀 리프레시 = 월 1회 cron → 어닝 시즌 최대 한 달 지연 (PM 지적 "신선도 치명적이지 않나").
해법: EDGAR daily master index(일 1~수 요청, 전 시장 공시 목록)에서 10-Q/10-K 신규 제출 CIK 를 감지 →
  우리 유니버스(_summary + _summary_smallcap CIK) 교집합 종목만 재수집 → 리포트/분기 재빌드.
  재무 신선도: 월 단위 → 공시 다음 날 (이벤트 기반).

파이프라인:
  1. state(data/metadata/us_fin_incremental_state.json) 이후 영업일들의 master.idx fetch (lookback ≤7일)
  2. form ∈ {10-K,10-Q,20-F,40-F 및 수정본} 행 → CIK → 유니버스 ticker 매핑
  3. run 캡(기본 60종목) 내 us_financials_builder --ticker 재수집 (부분 실행 = _summary 병합 가드 완비)
  4. 감지 커서와 pending을 함께 저장. 실패·초과·최신 제출 미반영은 다음 run에 재시도.

RULE 7 = 수집 사실만. KIS/DART 무관. EDGAR = 일일 쿼터 없음(정중 throttle).
usage: python -m api.builders.us_financials_incremental [--cap N] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA = os.path.join(_ROOT, "data")
STATE_PATH = os.path.join(_DATA, "metadata", "us_fin_incremental_state.json")
EARN_PATTERN_PATH = os.path.join(_DATA, "us_earnings_pattern.json")
EVENT_PATH = os.path.join(_DATA, "us_disclosure_feed.json")
QUARTERLY_PATH = os.path.join(_DATA, "us_quarterly_public.json")
FIN_DIR = os.path.join(_DATA, "us_financials")
PATTERN_KEEP = 10
SUMMARY_PATHS = [
    os.path.join(_DATA, "us_financials", "_summary.json"),
    os.path.join(_DATA, "us_financials", "_summary_smallcap.json"),
]
SEC_USER_AGENT = "VERITY gywns0126@gmail.com"
TARGET_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A"}
LOOKBACK_MAX_DAYS = 7      # state 유실/장기 중단 시 폭주 방지
DEFAULT_CAP = 60           # run 당 재수집 종목 상한 (어닝 피크 방어 — 잔여는 다음 run이 이어감)
IDX_TIMEOUT = 20
THROTTLE_SEC = 0.4
COLLECTION_BUDGET_SEC = 20 * 60  # Leave time for validation and retry-state persistence.


def _quarter(d: date) -> int:
    return (d.month - 1) // 3 + 1


def _idx_url(d: date) -> str:
    return (f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{_quarter(d)}/"
            f"master.{d.strftime('%Y%m%d')}.idx")


def _load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save_state(st: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


def _universe_cik_map() -> Dict[int, List[str]]:
    """유니버스 CIK → 클래스별 tickers (sp1500 + smallcap _summary rows)."""
    out: Dict[int, List[str]] = {}
    for p in SUMMARY_PATHS:
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        for r in (doc.get("rows") or []):
            cik, tk = r.get("cik"), r.get("ticker")
            if cik is None or not tk:
                continue
            try:
                tickers = out.setdefault(int(cik), [])
                ticker = str(tk)
                if ticker not in tickers:
                    tickers.append(ticker)
            except (TypeError, ValueError):
                continue
    return out


def _fetch_day_filers(d: date) -> Optional[List[Tuple[int, str, str]]]:
    """해당 일 master.idx → [(CIK, form, accession)]. 미발행 = None."""
    try:
        r = requests.get(_idx_url(d), headers={"User-Agent": SEC_USER_AGENT}, timeout=IDX_TIMEOUT)
    except requests.RequestException as e:
        print(f"[us_fin_incr] {d} idx fetch 실패: {e!r}", file=sys.stderr)
        return None
    if r.status_code != 200:
        return None
    out: List[Tuple[int, str, str]] = []
    for line in r.text.splitlines():
        parts = line.split("|")
        if len(parts) != 5:
            continue
        cik_s, _name, form, _filed, _fname = parts
        if form.strip() in TARGET_FORMS:
            try:
                accession = os.path.basename(_fname.strip()).removesuffix(".txt")
                if len(accession) == 18 and accession.isdigit():
                    accession = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"
                out.append((int(cik_s), form.strip(), accession))
            except ValueError:
                continue
    return out


def _append_patterns(hits: List[Tuple[str, str, str]]) -> None:
    """(ticker, form, filed) → us_earnings_pattern.json append (어닝 캘린더 일일 유지 — backfill 이후 무추가비용)."""
    if not hits:
        return
    try:
        with open(EARN_PATTERN_PATH, encoding="utf-8") as f:
            doc = json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        doc = {"_meta": {}, "patterns": {}}
    pats = doc.setdefault("patterns", {})
    for tk, form, filed in hits:
        rows = pats.setdefault(tk, [])
        if any(r.get("filed") == filed and r.get("form") == form for r in rows):
            continue
        rows.insert(0, {"form": form, "filed": filed})
        del rows[PATTERN_KEEP:]
    with open(EARN_PATTERN_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    print(f"[us_fin_incr] 어닝 패턴 갱신 {len(hits)}건 → {EARN_PATTERN_PATH}", file=sys.stderr)


def _load_optional(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _merge_candidate(pending: Dict[str, Any], ticker: str, evidence: Dict[str, Any]) -> None:
    old = pending.setdefault(ticker, {"ticker": ticker, "attempts": 0})
    if (evidence.get("filed", ""), evidence.get("accession", "")) >= (
            old.get("filed", ""), old.get("accession", "")):
        if evidence.get("accession") and evidence["accession"] != old.get("accession"):
            old.pop("report_date", None)  # A new filing cannot inherit the old quarter's date.
        old.update({k: v for k, v in evidence.items() if k != "earnings_date"})
    if evidence.get("earnings_date", "") > old.get("earnings_date", ""):
        old["earnings_date"] = evidence["earnings_date"]


def _local_candidates(cik_map: Dict[int, List[str]], today: date,
                      completed: Dict[str, str]) -> Dict[str, Any]:
    """Reuse collected 8-K events and submission evidence; no extra HTTP calls."""
    pending: Dict[str, Any] = {}
    siblings = {tk: tickers for tickers in cik_map.values() for tk in tickers}
    cutoff = (today - timedelta(days=LOOKBACK_MAX_DAYS)).isoformat()
    for item in _load_optional(EVENT_PATH).get("items", []):
        for event in item.get("disclosures", []):
            filed = str(event.get("date") or "")
            if "2.02" not in (event.get("item_codes") or []) or not cutoff <= filed <= today.isoformat():
                continue
            for tk in siblings.get(item.get("ticker"), []):
                if filed > completed.get(tk, ""):
                    _merge_candidate(pending, tk, {"earnings_date": filed})
    for tk, record in _load_optional(QUARTERLY_PATH).get("stocks", {}).items():
        sync = record.get("latest_filing_sync") or {}
        if tk in siblings and sync.get("status") == "source_lag" and sync.get("accession"):
            _merge_candidate(pending, tk, {k: sync[k] for k in (
                "accession", "report_date", "form") if sync.get(k)})
    return pending


def _snapshot_errors(doc: Dict[str, Any], ticker: str) -> List[str]:
    """Fatal integrity checks on refreshed rows only; coverage/missing is separate."""
    from api.intelligence import us_financials as usf

    errors = []
    if doc.get("ticker") != ticker or doc.get("_error"):
        return ["snapshot_missing_or_failed"]
    currency = (doc.get("meta") or {}).get("currency")
    if (not isinstance(currency, str) or len(currency) != 3
            or not currency.isalpha() or not currency.isupper()):
        errors.append("currency_missing_or_invalid")
    for key, annual in (("series_annual", True), ("series_quarterly", False)):
        for metric, rows in (doc.get(key) or {}).items():
            unit = "shares" if metric == "diluted_shares" else (
                "USD/shares" if metric == "eps_diluted" else currency)
            for row in rows:
                if row.get("val") is None:
                    continue
                period = usf._classify_period(row.get("start"), row.get("end"),
                                             row.get("form"), row.get("fp"), row.get("fy"),
                                             metric in usf.INSTANT_METRICS)
                end, filed = usf._parse_iso(row.get("end")), usf._parse_iso(row.get("filed"))
                if (period is None or period.is_annual != annual
                        or row.get("is_annual") is not annual or not filed or not end
                        or end > filed or filed > datetime.now(ZoneInfo("America/New_York")).date()):
                    errors.append(f"{key}.{metric}:period")
                if metric not in usf.INSTANT_METRICS:
                    start = usf._parse_iso(row.get("start"))
                    lo, hi = ((usf.ANNUAL_MIN_DAYS, usf.ANNUAL_MAX_DAYS) if annual else
                              (usf.QUARTER_MIN_DAYS, usf.QUARTER_MAX_DAYS))
                    if not start or not end or not lo <= (end - start).days <= hi:
                        errors.append(f"{key}.{metric}:duration")
                if row.get("unit") != unit or row.get("currency") not in (None, currency):
                    errors.append(f"{key}.{metric}:unit_currency")
                if not row.get("accn"):
                    errors.append(f"{key}.{metric}:accession_missing")
                if not isinstance(row["val"], (float, int)) or not math.isfinite(row["val"]):
                    errors.append(f"{key}.{metric}:nonfinite")
    return sorted(set(errors))


def _refresh(ticker: str, candidate: Dict[str, Any]) -> Tuple[List[str], bool]:
    """Validate a newly saved snapshot and retain missing latest-filing evidence."""
    result = subprocess.run(
        [sys.executable, "-m", "api.builders.us_financials_builder", "--ticker", ticker],
        capture_output=True, text=True, cwd=_ROOT, timeout=300)
    # The builder logs 'summary saved' even when the ticker fetch failed.
    if result.returncode or f"saved {ticker}.json" not in ((result.stderr or "") + (result.stdout or "")):
        return ["collector_failed"], False
    path = os.path.join(FIN_DIR, f"{ticker}.json")
    doc = _load_optional(path)
    errors = _snapshot_errors(doc, ticker)
    if errors:
        return errors, False
    rows = [r for key in ("series_annual", "series_quarterly")
            for series in (doc.get(key) or {}).values() for r in series if r.get("val") is not None]
    accession = candidate.get("accession")
    expected_date = max(candidate.get("filed", ""), candidate.get("earnings_date", ""))
    matching = [r for r in rows if (not accession or r.get("accn") == accession)
                and str(r.get("filed") or "") >= expected_date
                and (not candidate.get("report_date") or r.get("end") == candidate["report_date"])]
    missing = not matching
    evidence = {k: candidate[k] for k in ("accession", "report_date", "form") if candidate.get(k)}
    if matching:
        latest = max(matching, key=lambda r: (r.get("filed", ""), r.get("end", "")))
        evidence.update(accession=latest.get("accn"), report_date=latest.get("end"), form=latest.get("form"))
    doc.setdefault("meta", {})["latest_filing_sync"] = {
        **evidence, "status": "source_lag" if missing else "companyfacts_current",
        "checked_at": datetime.now(KST).isoformat(),
        "expected_filed": expected_date or None,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return [], missing


def _requeue_run() -> None:
    st = _load_state()
    pending = {row["ticker"]: row for row in st.get("pending", [])}
    for row in st.get("last_run_candidates", []):
        if row["ticker"] not in pending:
            pending[row["ticker"]] = {**row, "last_error": "downstream_or_collection_failed"}
        st.get("completed_earnings", {}).pop(row["ticker"], None)
    st["pending"] = list(pending.values())
    # Failed runs must not feed the briefing as successfully refreshed filings.
    st["last_run_tickers"] = []
    _save_state(st)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP, help="run 당 재수집 종목 상한")
    ap.add_argument("--dry-run", action="store_true", help="감지만 출력, 재수집 없음")
    ap.add_argument("--requeue-run", action="store_true", help="실패 run의 후보만 복원; 외부 호출 없음")
    args = ap.parse_args()
    if args.requeue_run:
        _requeue_run()
        return 0
    if not 1 <= args.cap <= DEFAULT_CAP:
        ap.error(f"--cap must be between 1 and {DEFAULT_CAP}")

    cik_map = _universe_cik_map()
    if not cik_map:
        print("[us_fin_incr] 유니버스 CIK 맵 부재(_summary) — blocked", file=sys.stderr)
        return 1

    st = _load_state()
    today_et = datetime.now(ZoneInfo("America/New_York")).date()
    last_s = st.get("last_processed")
    try:
        last = date.fromisoformat(last_s) if last_s else today_et - timedelta(days=2)
    except ValueError:
        last = today_et - timedelta(days=2)
    start = max(last + timedelta(days=1), today_et - timedelta(days=LOOKBACK_MAX_DAYS))

    pending = {row["ticker"]: dict(row) for row in st.get("pending", [])}
    completed = dict(st.get("completed_earnings", {}))
    for tk, evidence in _local_candidates(cik_map, today_et, completed).items():
        _merge_candidate(pending, tk, {k: v for k, v in evidence.items() if k not in ("ticker", "attempts")})
    pattern_hits: List[Tuple[str, str, str]] = []
    processed_through = last
    d = start
    while d < today_et:  # 당일(ET)은 인덱스 미완성 — 전일까지
        if d.weekday() < 5:
            filers = _fetch_day_filers(d)
            if filers is None:
                # 영업일인데 인덱스 부재 = 휴장 or 일시 오류 — 오류 가능성 있으므로 state 전진 중단
                print(f"[us_fin_incr] {d} 인덱스 없음 — 해당 일 이후 보류", file=sys.stderr)
                break
            # Fetch the daily index once, then fan out each issuer to its share classes.
            hit = sorted({tk for c, _f, _a in filers if c in cik_map for tk in cik_map[c]})
            pattern_hits.extend((tk, f, d.isoformat())
                                for c, f, _a in filers if c in cik_map for tk in cik_map[c])
            for cik, form, accession in filers:
                for tk in cik_map.get(cik, []):
                    _merge_candidate(pending, tk, {"filed": d.isoformat(), "form": form,
                                                   "accession": accession})
            print(f"[us_fin_incr] {d}: 재무 제출 {len(filers)} 건, 유니버스 교집합 {len(hit)}", file=sys.stderr)
            time.sleep(THROTTLE_SEC)
        processed_through = d
        d += timedelta(days=1)

    # Priority within a retry round; untouched overflow precedes repeated failures.
    ordered = sorted(pending.values(), key=lambda row: (
        row.get("attempts", 0), not bool(row.get("earnings_date")),
        row.get("filed") or row.get("earnings_date") or "", row["ticker"]))
    capped = ordered[:args.cap]
    if args.dry_run:
        print(f"[us_fin_incr] dry-run — 대상 {len(capped)}/{len(pending)}: "
              f"{[row['ticker'] for row in capped]}", file=sys.stderr)
        return 0
    _append_patterns(pattern_hits)
    st.update(last_processed=processed_through.isoformat(), pending=list(pending.values()),
              last_run_candidates=capped, last_run_tickers=[],
              updated_at=datetime.now(KST).isoformat(), completed_earnings=completed)
    _save_state(st)  # Durable discovery before collection, including timeout/crash candidates.
    ok, fail, missing = [], [], []
    attempted = 0
    started = time.monotonic()
    for candidate in capped:
        if time.monotonic() - started >= COLLECTION_BUDGET_SEC:
            break
        tk = candidate["ticker"]
        attempted += 1
        candidate["attempts"] = candidate.get("attempts", 0) + 1
        try:
            errors, lag = _refresh(tk, candidate)
        except (OSError, ValueError, TypeError, AttributeError, OverflowError,
                subprocess.TimeoutExpired) as exc:
            errors, lag = [type(exc).__name__], False
        if errors:
            candidate["last_error"] = ";".join(errors)
            fail.append(tk)
            print(f"[us_fin_incr] FAIL {tk}: {candidate['last_error']}", file=sys.stderr)
        elif lag:
            candidate["last_error"] = "missing_latest_filing"
            missing.append(tk)
        else:
            ok.append(tk)
            pending.pop(tk)
            if candidate.get("earnings_date"):
                completed[tk] = candidate["earnings_date"]
        time.sleep(THROTTLE_SEC)
    st.update(pending=list(pending.values()), last_run_tickers=ok,
              last_run_failed=fail, missing_latest=missing, completed_earnings=completed,
              updated_at=datetime.now(KST).isoformat())
    _save_state(st)
    print(f"[us_fin_incr] checked={attempted}/{len(ordered)} OK={len(ok)} "
          f"FAIL={fail} missing_latest={missing} pending={len(pending)}", file=sys.stderr)
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())

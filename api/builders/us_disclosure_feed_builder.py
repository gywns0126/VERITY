"""us_disclosure_feed_builder — 공개 터미널 미장(US) 공시속보 빌더.

2026-06-19 국장/미장 분리. combined US 유니버스의 최근 8-K·6-K·20-F·40-F와 정정을
SEC EDGAR submissions 에서 수집 → public-safe JSON. 스키마 = KR public_disclosure_feed.json
동일 → PublicDisclosureFeed 컴포넌트 재사용 (/us/feed 페이지에 feedUrl=이 파일).

🚨 RULE 7 — 공시 사실(폼타입·제목·접수일·원문URL)만. 점수·등급·추천 0.
SEC EDGAR 무료, 요청 간 0.13초 간격. UA = SEC_USER_AGENT.
publish: data/us_disclosure_feed.json (action.yml 등재 필요).
빌더는 네트워크 호출 — us_disclosure_feed(일간) 에서 실행. 테스트는 mock 원천 사용.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_PATH = os.path.join(_ROOT, "data", "us_financials", "_summary.json")
COMBINED_PATH = os.path.join(_ROOT, "data", "us_universe_combined.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_disclosure_feed.json")

WINDOW_DAYS = 90        # 8-K 산발적 → 윈도우 넉넉히 (2026-07-17 60→90: 어닝-8-K 주기 ~91일 포괄. 분기초 위치 종목의 직전 8-K 회수 → disclosures 84.7%→~97%. SEC 콜 0 증가=cutoff 필터만)
MAX_PER_TICKER = 5
# 🚨 예산 가드 — 무가드 1,505 SEC 순회가 daily_analysis_full 에서 완주 못 해 2건만 남던 사고(2026-07-09) 방지.
MAX_SECONDS = int(os.environ.get("US_DISCLOSURE_MAX_SECONDS", "1800"))
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik10}.json"
SEC_DELAY = 0.13
SUPPORTED_FORMS = ("8-K", "8-K/A", "6-K", "6-K/A", "20-F", "20-F/A", "40-F", "40-F/A")


def _now_kst() -> datetime:
    return datetime.now(KST)


def _title(name: str) -> str:
    return " ".join(w.capitalize() for w in str(name or "").split())


def _name_map() -> Dict[str, str]:
    """ticker→표시명 — combined names(전 US, 소형주 포함) + summary entity_name 병합."""
    out: Dict[str, str] = {}
    try:
        with open(COMBINED_PATH, encoding="utf-8") as f:
            names = (json.load(f) or {}).get("names") or {}
        if isinstance(names, dict):
            for tk, nm in names.items():
                if tk and nm:
                    out[str(tk).upper()] = _title(nm)
    except (OSError, json.JSONDecodeError):
        pass
    try:
        with open(SUMMARY_PATH, encoding="utf-8") as f:
            for r in ((json.load(f) or {}).get("rows") or []):
                tk = r.get("ticker")
                if tk and r.get("entity_name"):
                    out[str(tk).upper()] = _title(r.get("entity_name"))
    except (OSError, json.JSONDecodeError):
        pass
    return out


def _universe() -> List[str]:
    """전체 US 유니버스(combined, 소형주 포함) — 심화 파이프라인 공유 rotation 재사용(rec 우선+페이지 회전).
    부재 시 summary(S&P1500) fallback."""
    try:
        from api.builders.us_insider_trades_public_builder import _ordered_universe
        uni = _ordered_universe()
        if uni:
            return [str(t).upper() for t in uni]
    except Exception:  # noqa: BLE001
        pass
    try:
        with open(SUMMARY_PATH, encoding="utf-8") as f:
            return [str(r["ticker"]).upper() for r in ((json.load(f) or {}).get("rows") or []) if r.get("ticker")]
    except (OSError, json.JSONDecodeError, KeyError):
        return []


def _disclosures(payload: Any, cik: str, cutoff: str, asof: str) -> List[Dict[str, Any]]:
    """Parse submissions facts only; malformed responses are not empty coverage."""
    if not isinstance(payload, dict) or not isinstance(payload.get("filings"), dict):
        raise ValueError("invalid submissions filings")
    if "cik" in payload:
        supplied_cik = str(payload["cik"])
        if not re.fullmatch(r"[0-9]{1,10}", supplied_cik) or int(supplied_cik) != int(cik):
            raise ValueError("submissions CIK mismatch")
    recent = payload["filings"].get("recent")
    if not isinstance(recent, dict) or not isinstance(recent.get("form"), list):
        raise ValueError("invalid submissions recent")
    forms = recent["form"]
    columns = {}
    for field in ("filingDate", "accessionNumber", "primaryDocDescription", "primaryDocument",
                  "items", "reportDate", "acceptanceDateTime"):
        values = recent.get(field, [])
        if not isinstance(values, list):
            raise ValueError("invalid submissions column")
        if field in ("filingDate", "accessionNumber") and len(values) != len(forms):
            raise ValueError("incomplete submissions identity")
        columns[field] = values

    def value(field: str, index: int) -> str:
        values = columns[field]
        raw = values[index] if index < len(values) else ""
        if raw is None:
            return ""
        if not isinstance(raw, str):
            raise ValueError("invalid submissions value")
        return raw.strip()

    discs = []
    seen = set()
    for i, form in enumerate(forms):
        if form not in SUPPORTED_FORMS:
            continue
        filed = value("filingDate", i)
        if datetime.strptime(filed, "%Y-%m-%d").date().isoformat() != filed:
            raise ValueError("invalid filing date")
        if filed > asof:
            raise ValueError("future filing date")
        if filed < cutoff:
            continue
        accession = value("accessionNumber", i)
        if not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
            raise ValueError("invalid accession")
        if accession in seen:
            continue
        seen.add(accession)
        accession_plain = accession.replace("-", "")
        primary_document = value("primaryDocument", i)
        if primary_document and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", primary_document):
            raise ValueError("unsafe primary document filename")
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_plain}/"
        discs.append({
            "id": f"SEC:{int(cik)}:{accession_plain}",
            "cik": str(int(cik)),
            "accession_number": accession,
            "primary_document": primary_document,
            "title": value("primaryDocDescription", i) or (
                f"{form} " + ("연차보고서" if form.startswith(("20-F", "40-F")) else "수시공시")
            ),
            "label": form,
            "date": filed,
            "filing_date": filed,
            "report_date": value("reportDate", i),
            # Acceptance is not proof of the time this filing became publicly available.
            "acceptance_datetime": value("acceptanceDateTime", i),
            "is_correction": form.endswith("/A"),
            "source": "SEC",
            # Missing primary document still links to this filing, never a company search.
            "source_url": base + (primary_document or f"{accession}-index.html"),
            "item_codes": [code.strip() for code in value("items", i).split(",") if code.strip()]
                          if form in ("8-K", "8-K/A") else [],
        })
    discs.sort(key=lambda row: (row["date"], row["acceptance_datetime"]), reverse=True)
    return discs[:MAX_PER_TICKER]


def build_feed(window_days: int = WINDOW_DAYS) -> Dict[str, Any]:
    import requests

    from api.builders.us_insider_trades_public_builder import _ticker_cik_map
    from api.intelligence.us_financials import SEC_USER_AGENT

    asof = _now_kst().date()
    cutoff = (asof - timedelta(days=window_days)).isoformat()
    names = _name_map()

    # carry-forward — 이전 스냅샷(이번 회전서 안 건드린 종목 보존). 예산 완주 실패해도 누적.
    prev: Dict[str, Dict[str, Any]] = {}
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            for it in ((json.load(f) or {}).get("items") or []):
                if it.get("ticker"):
                    prev[str(it["ticker"]).upper()] = it
    except (OSError, json.JSONDecodeError):
        pass
    merged: Dict[str, Dict[str, Any]] = dict(prev)

    order = _universe()
    sess = requests.Session()
    cik_map = _ticker_cik_map(sess)
    processed: List[str] = []
    unresolved: List[str] = []
    unavailable: List[str] = []
    unprocessed: List[str] = []
    empty: List[str] = []
    # Cache success, empty and failure by issuer, without cross-run freshness claims.
    submissions: Dict[str, List[Dict[str, Any]] | None] = {}
    reused_cik_tickers = 0
    attempted_at = _now_kst().isoformat()

    t0 = time.monotonic()
    for idx, tk in enumerate(order):
        if time.monotonic() - t0 > MAX_SECONDS:
            unprocessed.extend(order[idx:])
            print(f"[us_disclosure_feed] budget 도달 ({int(time.monotonic()-t0)}s, {len(processed)}종목) — 나머지 carry-forward", file=sys.stderr)
            break
        cik = cik_map.get(tk)
        if not cik:
            unresolved.append(tk)
            continue
        cik = str(cik).zfill(10)
        name = names.get(tk, tk)
        if cik not in submissions:
            submissions[cik] = None
            try:
                response = sess.get(
                    SEC_SUBMISSIONS.format(cik10=cik),
                    headers={"User-Agent": SEC_USER_AGENT, "Accept": "application/json"},
                    timeout=15,
                    allow_redirects=False,
                )
                if response.status_code == 200:
                    submissions[cik] = _disclosures(response.json(), cik, cutoff, asof.isoformat())
            except (requests.RequestException, ValueError, KeyError) as e:
                print(f"[us_disclosure_feed] {tk} submissions fetch 실패: {e!r}", file=sys.stderr)
            finally:
                time.sleep(SEC_DELAY)
        else:
            reused_cik_tickers += 1
        if submissions[cik] is None:
            unavailable.append(tk)
            continue
        processed.append(tk)
        discs = [dict(disclosure, filer=name) for disclosure in submissions[cik]]
        if discs:
            merged[tk] = {"ticker": tk, "name": name, "latest": discs[0]["date"], "disclosures": discs}
        else:
            empty.append(tk)
            merged.pop(tk, None)  # 정상 조회됐으나 윈도우 내 해당 공시 없음.

    # 윈도우 밖으로 밀린 carry-forward 항목 정리
    items = [it for it in merged.values() if str(it.get("latest", "")) >= cutoff]
    items.sort(key=lambda it: it["latest"], reverse=True)
    total = sum(len(it.get("disclosures") or []) for it in items)
    completed_at = _now_kst().isoformat()
    succeeded = sum(value is not None for value in submissions.values())
    complete = bool(order) and len(processed) == len(order)
    collection = {
        "endpoint": SEC_SUBMISSIONS,
        "scope": "submissions.filings.recent; excludes ticker-map request and historical files",
        "status": "success" if complete else "partial" if processed or unprocessed else "error" if order else "unknown",
        "attempted_at": attempted_at if submissions else None,
        "completed_at": completed_at,
        "successful_checked_at": completed_at if complete else None,
        "requests": len(submissions),
        "requests_succeeded": succeeded,
        "requests_failed": len(submissions) - succeeded,
        "reused_cik_tickers": reused_cik_tickers,
        "universe_n": len(order),
        "processed_n": len(processed),
        "empty_n": len(empty),
        "unavailable_n": len(unavailable),
        "unresolved_n": len(unresolved),
        "deferred_n": len(unprocessed),
        "universe_complete": complete,
        "whole_market_coverage": False,
    }
    return {
        "_meta": {
            "generated_at": completed_at,
            "source_collection": collection,
            "source": "SEC EDGAR (8-K·6-K·20-F·40-F 및 정정)",
            "forms": list(SUPPORTED_FORMS),
            "market": "US",
            "count": len(items),
            "disclosure_count": total,
            "window_days": window_days,
            "max_per_ticker": MAX_PER_TICKER,
            "covered_this_run": len(processed),
            "processed_n": len(processed),
            "unresolved_n": len(unresolved),
            "unavailable_n": len(unavailable),
            "unprocessed_n": len(unprocessed),
            "note": "공시 사실·일정만 — 점수·등급·추천 아님 (RULE 7). 제목은 SEC 원문, 링크는 EDGAR. "
                    "유니버스=combined(S&P 1500 + Polygon 소형주), 페이지 회전+carry-forward 누적. "
                    "processed=SEC submissions 정상 파싱, unavailable=원천 응답·파싱 실패, unresolved=CIK 미확인. "
                    "date·filing_date=filingDate, report_date=reportDate, acceptance_datetime=acceptanceDateTime 원문; "
                    "수집 범위=filings.recent만(과거 파일 추가 요청 없음). "
                    "generated_at은 빌더 생성 시각이며 공시 원천 시각이 아님.",
        },
        "_coverage": {
            "universe_n": len(order),
            "processed_tickers": sorted(processed),
            "unresolved_tickers": sorted(unresolved),
            "unavailable_tickers": sorted(unavailable),
            "unprocessed_tickers": sorted(unprocessed),
            "empty_tickers": sorted(empty),
            "carry_forward_tickers": sorted(it["ticker"] for it in items if it["ticker"] not in processed),
        },
        "items": items,
    }


def main() -> int:
    ok = False
    try:
        feed = build_feed()
        n_items = len(feed["items"])
        n_disc = feed["_meta"]["disclosure_count"]
        # build_feed already preserves failed/unprocessed rows and expires old facts.
        # Persist valid empty results too, so stale rows and old coverage cannot survive.
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(feed, f, ensure_ascii=False, indent=2)
        print(f"[us_disclosure_feed] logged=True · {n_items} 종목 · {n_disc} 공시 -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[us_disclosure_feed] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[us_disclosure_feed] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

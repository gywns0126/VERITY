#!/usr/bin/env python3
"""VERITY ESTATE — 회사별 부동산 자산 시계열 워커.

Repo root 에서 실행 (api.collectors.DartScout 직접 import 가능):
  python scripts/estate_corp_snapshot.py --ticker 005930 [--year 2025]
  python scripts/estate_corp_snapshot.py --tickers 005930,066570
  python scripts/estate_corp_snapshot.py --portfolio data/portfolio.json

기존 자산 재활용:
  api.collectors.DartScout.fetch_property_assets         → estate_corp_holdings
  api.collectors.DartScout.fetch_business_facilities_raw → raw text
  api.analyzers.facilities_parser.parse_business_facilities → estate_corp_facilities
  api.collectors.dart_corp_code.get_corp_code            → ticker → corp_code

Supabase upsert (service_role):
  estate_corp_holdings   UNIQUE(corp_code, bsns_year, reprt_code)
  estate_corp_facilities UNIQUE(corp_code, bsns_year, reprt_code, facility_name, location_address)

V1 범위: 사업보고서(annual, reprt_code=11011) 만. 분기/반기 = V1.5.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

# repo root sys.path 보장 (scripts/ 에서 실행되어도 api.* import 가능)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.collectors.DartScout import (  # noqa: E402
    fetch_property_assets,
    fetch_business_facilities_raw,
)
from api.collectors.dart_corp_code import get_corp_code  # noqa: E402

try:
    from api.analyzers.facilities_parser import parse_business_facilities
    HAS_FAC_PARSER = True
except Exception as _imp_err:  # pragma: no cover
    print(f"[corp_snapshot] facilities_parser import 실패 ({_imp_err}) — facilities 저장 건너뜀",
          flush=True)
    HAS_FAC_PARSER = False

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("corp_snapshot")

KST = timezone(timedelta(hours=9))
ANNUAL_REPORT = "11011"

# 부동산 카테고리 ↔ 계정과목 substring 매핑.
# 더 구체적인 키워드를 위에 둔다 (건설중인자산 → "건물" 보다 먼저 매칭).
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("construction_in_progress_krw", ["건설중"]),
    ("right_of_use_assets_krw",      ["사용권자산"]),
    ("investment_property_krw",      ["투자부동산"]),
    ("structures_krw",               ["구축물"]),
    ("buildings_krw",                ["건물"]),
    ("land_krw",                     ["토지"]),
]

SEOUL_GU_RE = re.compile(
    r"(강남|강동|강북|강서|관악|광진|구로|금천|노원|도봉|동대문|동작|마포|"
    r"서대문|서초|성동|성북|송파|양천|영등포|용산|은평|종로|중랑|중)구"
)

SI_TOKENS = (
    "서울특별시", "서울시", "서울",
    "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시",
    "경기도", "강원특별자치도", "강원도",
    "충청북도", "충청남도", "전라북도", "전북특별자치도",
    "전라남도", "경상북도", "경상남도",
    "제주특별자치도", "제주도",
)


# ──────────────────────────────────────────────────────────────
# 정규화
# ──────────────────────────────────────────────────────────────

def categorize_property_items(items: list[dict]) -> dict[str, int]:
    """DartScout items[] → 카테고리별 합계 (KRW)."""
    out = {col: 0 for col, _ in CATEGORY_RULES}
    for item in items:
        acct = item.get("account") or ""
        curr = int(item.get("current") or 0)
        if not curr:
            continue
        for col, kws in CATEGORY_RULES:
            if any(kw in acct for kw in kws):
                out[col] += curr
                break
    return out


def detect_revaluation(items: list[dict]) -> bool:
    """재평가 발생 휴리스틱 — 계정명에 '재평가' 포함 시 True."""
    return any("재평가" in (it.get("account") or "") for it in items)


def parse_period(bsns_year: int, reprt_code: str) -> str:
    return {
        "11013": f"{bsns_year}-Q1",
        "11012": f"{bsns_year}-Q2",
        "11014": f"{bsns_year}-Q3",
        "11011": f"{bsns_year}-FY",
    }.get(reprt_code, f"{bsns_year}-FY")


def extract_location_si_gu(addr: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """주소 → (location_si, location_gu). 서울 25구만 정규화."""
    if not addr:
        return None, None
    s = addr.strip()
    if not s:
        return None, None

    si: Optional[str] = None
    for token in SI_TOKENS:
        if s.startswith(token):
            si = "서울특별시" if token in ("서울시", "서울") else token
            break

    if si and "서울" in si:
        m = SEOUL_GU_RE.search(s)
        return si, (m.group(0) if m else None)
    return si, None


def map_facility_use_to_type(use: Optional[str]) -> str:
    if not use:
        return "other"
    u = use.lower()
    if "본사" in use:                    return "HQ"
    if "공장" in use:                    return "factory"
    if "r&d" in u or "연구" in use:      return "RnD"
    if "물류" in use:                    return "logistics"
    if "매장" in use or "점" in use:     return "store"
    if "투자부동산" in use:              return "investment"
    if "오피스" in use:                  return "HQ"
    return "other"


def map_ownership(s: Optional[str]) -> str:
    if not s:
        return "unknown"
    if "소유" in s:
        return "owned"
    if "임차" in s or "임대" in s:
        return "leased"
    return "unknown"


# ──────────────────────────────────────────────────────────────
# DART company name lookup (boundary call — 1 per ticker)
# ──────────────────────────────────────────────────────────────

_NAME_CACHE: dict[str, str] = {}

def fetch_company_name(corp_code: str) -> Optional[str]:
    if corp_code in _NAME_CACHE:
        return _NAME_CACHE[corp_code]
    key = os.environ.get("DART_API_KEY", "")
    if not key:
        return None
    try:
        r = requests.get(
            "https://opendart.fss.or.kr/api/company.json",
            params={"crtfc_key": key, "corp_code": corp_code},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "000":
            return None
        name = (data.get("corp_name") or "").strip() or None
        if name:
            _NAME_CACHE[corp_code] = name
        return name
    except Exception as e:
        log.warning("company.json fetch %s 실패: %s", corp_code, e)
        return None


# ──────────────────────────────────────────────────────────────
# Supabase upsert
# ──────────────────────────────────────────────────────────────

def supabase_upsert(table: str, rows: list[dict], on_conflict: str) -> bool:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    sk = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not sk:
        log.warning("Supabase env 미설정 — 저장 스킵")
        return False
    if not rows:
        return True
    endpoint = f"{url}/rest/v1/{table}?on_conflict={on_conflict}"
    headers = {
        "apikey": sk,
        "Authorization": f"Bearer {sk}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    try:
        r = requests.post(endpoint, headers=headers, json=rows, timeout=30)
        r.raise_for_status()
        return True
    except requests.HTTPError as e:
        body = ""
        try:
            body = r.text[:400]
        except Exception:
            pass
        log.error("Supabase upsert(%s) %s | %s", table, e, body)
        return False
    except Exception as e:
        log.error("Supabase upsert(%s) %s", table, e)
        return False


# ──────────────────────────────────────────────────────────────
# 단일 회사 처리
# ──────────────────────────────────────────────────────────────

def snapshot_company(ticker: str, bsns_year: int) -> dict:
    """1개 회사 → holdings 1행 + facilities N행 추출 후 Supabase upsert."""
    result = {
        "ticker": ticker, "ok": False, "reason": None,
        "holdings_saved": 0, "facilities_saved": 0,
    }

    corp_code = get_corp_code(ticker)
    if not corp_code:
        result["reason"] = "no_corp_code"
        return result

    bare_ticker = ticker.split(".")[0] if "." in ticker else ticker
    company_name = fetch_company_name(corp_code) or bare_ticker

    # ─── Holdings ───
    try:
        prop = fetch_property_assets(corp_code, str(bsns_year))
    except Exception as e:
        result["reason"] = f"property_fetch:{type(e).__name__}:{e}"
        return result

    items = prop.get("items") or []
    if not items:
        result["reason"] = "no_property_items"
        return result

    cats = categorize_property_items(items)
    total_curr = int(prop.get("total_current") or 0)
    total_prev = int(prop.get("total_previous") or 0)
    total_assets = prop.get("total_assets") or None
    period = parse_period(bsns_year, ANNUAL_REPORT)

    holding_row = {
        "corp_code": corp_code,
        "ticker": bare_ticker,
        "company_name": company_name,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
        "period": period,
        "land_krw":                     cats["land_krw"] or None,
        "buildings_krw":                cats["buildings_krw"] or None,
        "structures_krw":               cats["structures_krw"] or None,
        "construction_in_progress_krw": cats["construction_in_progress_krw"] or None,
        "investment_property_krw":      cats["investment_property_krw"] or None,
        "right_of_use_assets_krw":      cats["right_of_use_assets_krw"] or None,
        "total_property_krw":   total_curr,
        "prev_property_krw":    total_prev or None,
        "total_assets_krw":     total_assets,
        "property_to_asset_pct": prop.get("property_to_asset_pct"),
        "qoq_change_pct":       prop.get("total_change_pct"),
        # yoy_change_pct: 전년도 row 조회 필요 — V1.5 로 미룸
        "book_value_total_krw": total_curr,
        "revaluation_flag":     detect_revaluation(items),
        "raw_breakdown":        items,
        "source": "dart",
    }

    if supabase_upsert("estate_corp_holdings", [holding_row],
                        "corp_code,bsns_year,reprt_code"):
        result["holdings_saved"] = 1

    # ─── Facilities (LLM 파싱) ───
    if not HAS_FAC_PARSER:
        result["ok"] = bool(result["holdings_saved"])
        return result

    try:
        raw = fetch_business_facilities_raw(corp_code, str(bsns_year))
    except Exception as e:
        log.warning("facilities raw fetch %s: %s", ticker, e)
        result["ok"] = bool(result["holdings_saved"])
        return result

    if "error" in raw:
        log.info("facilities raw skipped %s: %s", ticker, raw["error"])
        result["ok"] = bool(result["holdings_saved"])
        return result

    raw_text = raw.get("raw_text") or ""
    if len(raw_text) < 300:
        result["ok"] = bool(result["holdings_saved"])
        return result

    try:
        parsed = parse_business_facilities(company_name, bare_ticker, raw_text)
    except Exception as e:
        log.warning("facilities parse %s 예외: %s", ticker, e)
        result["ok"] = bool(result["holdings_saved"])
        return result

    if "error" in parsed:
        log.info("facilities parse skipped %s: %s", ticker, parsed["error"])
        result["ok"] = bool(result["holdings_saved"])
        return result

    common = {
        "corp_code": corp_code,
        "ticker": bare_ticker,
        "company_name": company_name,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
        "period": period,
        "raw_blob": raw_text[:20000],
        "parsed_by": "gemini-2.5-flash",
        "source": "dart",
    }

    facility_rows: list[dict] = []

    for f in parsed.get("domestic_facilities") or []:
        si, gu = extract_location_si_gu(f.get("location"))
        facility_rows.append({**common,
            "facility_type": map_facility_use_to_type(f.get("use")),
            "ownership_type": map_ownership(f.get("ownership")),
            "facility_name": f.get("name"),
            "location_country": "KR",
            "location_si": si,
            "location_gu": gu,
            "location_address": f.get("location"),
            "area_sqm": f.get("size_sqm"),
            "currency": "KRW",
        })

    for f in parsed.get("overseas_facilities") or []:
        cc = (f.get("country_code") or "").upper() or None
        facility_rows.append({**common,
            "facility_type": "overseas",
            "ownership_type": map_ownership(f.get("ownership")),
            "facility_name": f.get("name"),
            "location_country": cc or (f.get("country") or "XX"),
            "location_si": None,
            "location_gu": None,
            "location_address": f.get("location"),
            "area_sqm": f.get("size_sqm"),
            "currency": "USD",
        })

    for f in parsed.get("investment_properties") or []:
        si, gu = extract_location_si_gu(f.get("location"))
        facility_rows.append({**common,
            "facility_type": "investment",
            "ownership_type": "owned",
            "facility_name": f.get("name"),
            "location_country": "KR",
            "location_si": si,
            "location_gu": gu,
            "location_address": f.get("location"),
            "area_sqm": f.get("size_sqm"),
            "currency": "KRW",
        })

    # 동일 unique key 중복 제거 (PostgREST batch upsert 시 같은 batch 내 중복은 에러)
    if facility_rows:
        seen: set = set()
        dedup: list[dict] = []
        for r in facility_rows:
            key = (r["corp_code"], r["bsns_year"], r["reprt_code"],
                   r["facility_name"] or "", r["location_address"] or "")
            if key in seen:
                continue
            seen.add(key)
            dedup.append(r)
        if supabase_upsert("estate_corp_facilities", dedup,
                            "corp_code,bsns_year,reprt_code,facility_name,location_address"):
            result["facilities_saved"] = len(dedup)

    result["ok"] = bool(result["holdings_saved"])
    return result


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def collect_tickers_from_portfolio(path: Path) -> list[str]:
    if not path.exists():
        log.error("portfolio 없음: %s", path)
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else (data.get("stocks") or [])
    out: list[str] = []
    for r in rows:
        tk = (r.get("ticker") or "").strip()
        if not tk:
            continue
        if tk.endswith(".KS") or tk.endswith(".KQ"):
            out.append(tk)
        elif tk.isdigit() and len(tk) == 6:
            out.append(tk)
    return out


def main():
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--ticker", help="단일 ticker (예: 005930 또는 005930.KS)")
    grp.add_argument("--tickers", help="쉼표 구분 ticker 목록")
    grp.add_argument("--portfolio", help="data/portfolio.json 경로 (한국 종목 자동 추출)")
    parser.add_argument("--year", type=int,
                        default=datetime.now(KST).year - 1,
                        help="bsns_year (default: 전년도)")
    parser.add_argument("--limit", type=int, default=0,
                        help="최대 처리 종목 수 (0=무제한, batch 디버깅용)")
    parser.add_argument("--sleep", type=float, default=1.5,
                        help="회사 간 sleep (DART rate limit 보호)")
    args = parser.parse_args()

    if args.ticker:
        tickers = [args.ticker.strip()]
    elif args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = collect_tickers_from_portfolio(Path(args.portfolio))

    if args.limit > 0:
        tickers = tickers[:args.limit]

    if not tickers:
        log.error("처리할 ticker 없음")
        sys.exit(2)

    log.info("[corp_snapshot] year=%d tickers=%d", args.year, len(tickers))

    summary = {"ok": 0, "fail": 0, "holdings": 0, "facilities": 0}
    for i, tk in enumerate(tickers, 1):
        log.info("[%d/%d] %s ...", i, len(tickers), tk)
        try:
            r = snapshot_company(tk, args.year)
        except Exception as e:
            log.exception("처리 실패 %s: %s", tk, e)
            summary["fail"] += 1
            continue

        if r["ok"]:
            summary["ok"] += 1
            summary["holdings"] += r["holdings_saved"]
            summary["facilities"] += r["facilities_saved"]
            log.info("  ✓ holdings=%d facilities=%d",
                     r["holdings_saved"], r["facilities_saved"])
        else:
            summary["fail"] += 1
            log.info("  skip: %s", r["reason"])

        if args.sleep > 0 and i < len(tickers):
            time.sleep(args.sleep)

    log.info("[corp_snapshot] DONE %s", summary)


if __name__ == "__main__":
    main()

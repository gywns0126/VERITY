"""us_stock_report_public_builder — 공개 터미널 미장(US) 종목 리포트 public-safe 빌더.

2026-06-19 국장/미장 분리. data/us_financials/_summary.json (SEC EDGAR XBRL, 15 빅캡) →
public-safe JSON. 스키마 = KR stock_report_public.json 동일 → PublicStockReport 컴포넌트 재사용
(/us/stock 페이지에 stockUrl=이 파일).

🚨 RULE 7 — allowlist. 노출: ROE / D/E / 매출성장 / 마진 / Altman-Z(학술).
  비노출: fscore_grade / lynch_class (자체 등급). 가격/PER/PBR = 컴포넌트 라이브.
순수 변환 — 외부호출 0. publish: data/us_stock_report_public.json (action.yml 등재 필요).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUMMARY_PATH = os.path.join(_ROOT, "data", "us_financials", "_summary.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_stock_report_public.json")


def _now_kst() -> datetime:
    return datetime.now(KST)


def _pct(v: Any, digits: int = 1, signed: bool = False) -> str | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:
        return None
    sign = "+" if (signed and x > 0) else ""
    return f"{sign}{x:.{digits}f}%"


def _num(v: Any, digits: int = 2) -> str | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:
        return None
    s = f"{x:.{digits}f}".rstrip("0").rstrip(".")
    return s


def _title(name: str) -> str:
    # "MICROSOFT CORPORATION" → "Microsoft Corporation"
    return " ".join(w.capitalize() for w in str(name or "").split())


def build_stock(row: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    facts: Dict[str, str] = {}
    fnote: Dict[str, str] = {}
    roe = _pct(row.get("roe_pct"))
    if roe:
        facts["ROE"] = roe
    de = _num(row.get("debt_to_equity"))
    if de is not None:
        facts["D/E"] = de  # 부채/자본 비율 (낮을수록 빚 부담 적음)
    rg = _pct(row.get("revenue_yoy_pct_annual"), signed=True)
    if rg:
        facts["매출성장"] = rg
    gm = _pct(row.get("gross_margin_pct"))
    if gm:
        facts["매출총이익률"] = gm
    om = _pct(row.get("operating_margin_pct"))
    if om:
        facts["영업이익률"] = om
    nm = _pct(row.get("net_margin_pct"))
    if nm:
        facts["순이익률"] = nm
    az = _num(row.get("altman_z"), 1)
    if az is not None:
        facts["Altman-Z"] = az
        zone = row.get("altman_zone")
        if zone:
            fnote["Altman-Z"] = "안전구간" if zone == "safe" else str(zone)

    sic_desc = (meta or {}).get("sic_description") or ""
    return {
        "ticker": row.get("ticker") or "",
        "name": _title(row.get("entity_name") or row.get("ticker")),
        "market": "US",
        "business": sic_desc,
        "facts": facts,
        "facts_note": fnote,
        "disclosures": [],   # 8-K 는 /us/feed (us_disclosure_feed_builder) 담당
        "ownership": None,
        "consensus": None,
        "calendar": [],
    }


def main() -> int:
    ok = False
    try:
        if not os.path.isfile(SUMMARY_PATH):
            print("[us_stock_report] us_financials/_summary.json 부재 — skip", file=sys.stderr)
            return 0
        with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
            summary = json.load(f)
        rows = summary.get("rows") or []
        # per-ticker 파일에서 meta(sic_description) 보강
        meta_by_ticker: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            tk = r.get("ticker")
            if not tk:
                continue
            p = os.path.join(_ROOT, "data", "us_financials", f"{tk}.json")
            try:
                with open(p, "r", encoding="utf-8") as pf:
                    meta_by_ticker[tk] = (json.load(pf) or {}).get("meta") or {}
            except (OSError, json.JSONDecodeError):
                meta_by_ticker[tk] = {}

        stocks = [build_stock(r, meta_by_ticker.get(r.get("ticker"), {})) for r in rows if r.get("ticker")]
        # ROE 큰 순 (사실 정렬)
        def _roe(s):
            v = s.get("facts", {}).get("ROE", "")
            try:
                return float(str(v).rstrip("%").lstrip("+"))
            except ValueError:
                return -999
        stocks.sort(key=_roe, reverse=True)

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "SEC EDGAR XBRL (us_financials)",
                "count": len(stocks),
                "market": "US",
                "note": "공개 사실만 (RULE 7 allowlist) — 점수·등급·추천 비노출. 가격은 클라이언트 라이브. 15 빅캡 시작.",
            },
            "stocks": stocks,
        }
        if not stocks and os.path.isfile(OUTPUT_PATH):
            print("[us_stock_report] 0 stocks — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[us_stock_report] logged=True · {len(stocks)} 종목 -> {os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[us_stock_report] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[us_stock_report] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

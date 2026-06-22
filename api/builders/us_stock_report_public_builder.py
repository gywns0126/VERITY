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


CACHE_PATH = os.path.join(_ROOT, "data", "cache", "universe_us.json")
# ROE 무의미 임계 — |ROE|>100% = 자사주 매입/자본잠식으로 자기자본 과소 → 수익성 신호 아닌 왜곡.
_ROE_MAX_MEANINGFUL = 100.0


def _load_universe_caps() -> Dict[str, Dict[str, float]]:
    """data/cache/universe_us.json → {ticker: {market_cap, adv}} (header 시총·거래대금)."""
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    out: Dict[str, Dict[str, float]] = {}
    for e in (data if isinstance(data, list) else []):
        tk = str(e.get("ticker") or "").upper()
        if tk:
            out[tk] = {"market_cap": float(e.get("market_cap") or 0),
                       "adv": float(e.get("avg_trading_value_30d") or 0)}
    return out


def _usd_compact(v: Any) -> str | None:
    """USD 큰 수 → $X.XXT / $X.XB / $XXXM (US header)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x or x <= 0:
        return None
    if x >= 1e12:
        return f"${x / 1e12:.2f}T"
    if x >= 1e9:
        return f"${x / 1e9:.1f}B"
    if x >= 1e6:
        return f"${x / 1e6:.0f}M"
    return f"${x:,.0f}"


def build_stock(row: Dict[str, Any], meta: Dict[str, Any], caps: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    facts: Dict[str, str] = {}
    fnote: Dict[str, str] = {}
    # ROE — 자기자본 과소(자사주/자본잠식) 시 |ROE| 폭발 → 가짜 숫자 대신 사유 명시 (정공법).
    try:
        roe_v = float(row.get("roe_pct"))
    except (TypeError, ValueError):
        roe_v = float("nan")
    if roe_v == roe_v:  # not NaN
        if abs(roe_v) > _ROE_MAX_MEANINGFUL:
            facts["ROE"] = "산정불가"
            fnote["ROE"] = "자사주 매입·자본잠식으로 자기자본 과소 → ROE 왜곡(산정 제외)"
        else:
            facts["ROE"] = _pct(roe_v)
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
    # header — 시총·거래대금 (universe 캐시, USD). 52주 범위는 가격 history 부재로 생략(클라이언트 라이브 가격 보완).
    cap = caps.get((row.get("ticker") or "").upper(), {})
    header: Dict[str, str] = {}
    mc = _usd_compact(cap.get("market_cap"))
    if mc:
        header["market_cap"] = mc
    tv = _usd_compact(cap.get("adv"))
    if tv:
        header["trading_value"] = tv + "/일"
    return {
        "ticker": row.get("ticker") or "",
        "name": _title(row.get("entity_name") or row.get("ticker")),
        "market": "US",
        "business": sic_desc,
        "header": header or None,
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

        caps = _load_universe_caps()   # header 시총·거래대금 (universe 캐시)
        stocks = [build_stock(r, meta_by_ticker.get(r.get("ticker"), {}), caps) for r in rows if r.get("ticker")]
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

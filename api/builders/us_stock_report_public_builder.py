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
# display sanity outlier 임계 — 분모(매출/자본) 과소·XBRL 오추출·기간불일치로 폭발한 값 차단.
# 가짜 숫자 대신 "산정불가" + 사유(정공법). 2026-06-23 정밀검수: net 221640%·Altman 7163 등 70종 노출 발견.
_ROE_MAX = 100.0       # |ROE|>100% = 자사주/자본잠식 자기자본 과소
_MARGIN_MAX = 200.0    # |마진|>200% = 매출 분모 과소(금융 순이자·바이오 미미 매출)
_GROSS_MAX = 100.0     # 매출총이익률>100% = 물리 불가(XBRL 오추출)
_ALTMAN_MAX = 100.0    # |Z|>100 = BS 항목 stale/기간불일치 명백 오추출(REX 7163 등). 무차입 고시총(NVDA 66)은 실제값 유지
_GROWTH_MAX = 500.0    # |매출성장|>500% = 전년 매출 ≈0 분모 효과
_DE_MAX = 50.0         # |D/E|>50 = 자본 과소(ROE 산정불가와 동일 root)


def _guarded(v: Any, bound: float, digits: int = 1, signed: bool = False,
             gross_cap: bool = False) -> tuple:
    """수치 → (표시값, is_na). |v|>bound(또는 gross>100) 면 ('산정불가', True), 정상이면 (_pct, False).

    None/NaN = (None, False) (미수록).
    """
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None, False
    if x != x:
        return None, False
    if abs(x) > bound or (gross_cap and x > _GROSS_MAX):
        return "산정불가", True
    return _pct(x, digits=digits, signed=signed), False


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

    def _put(label: str, raw: Any, bound: float, na_reason: str,
             signed: bool = False, gross_cap: bool = False):
        val, na = _guarded(raw, bound, signed=signed, gross_cap=gross_cap)
        if val is not None:
            facts[label] = val
            if na:
                fnote[label] = na_reason

    # 전 facts outlier 가드 (분모 과소·XBRL 오추출 → 가짜 숫자 대신 산정불가, 정공법).
    _put("ROE", row.get("roe_pct"), _ROE_MAX,
         "자사주 매입·자본잠식으로 자기자본 과소 → ROE 왜곡(산정 제외)")
    _put("매출성장", row.get("revenue_yoy_pct_annual"), _GROWTH_MAX,
         "전년 매출 거의 0 → 성장률 분모 효과(산정 제외)", signed=True)
    _put("매출총이익률", row.get("gross_margin_pct"), 1e9,
         "매출총이익률>100% 물리 불가 → XBRL 추출 오류(산정 제외)", gross_cap=True)
    _put("영업이익률", row.get("operating_margin_pct"), _MARGIN_MAX,
         "매출 분모 과소·미미로 마진 왜곡(산정 제외)")
    _put("순이익률", row.get("net_margin_pct"), _MARGIN_MAX,
         "매출 분모 과소(금융 순이자수익 등)로 마진 왜곡(산정 제외)")

    # D/E — 자본 과소 시(ROE 산정불가와 동일 root) 가드, 그 외 그대로.
    de_val, de_na = _guarded(row.get("debt_to_equity"), _DE_MAX)
    de_num = _num(row.get("debt_to_equity"))
    if de_na:
        facts["D/E"] = "산정불가"
        fnote["D/E"] = "자기자본 과소(자사주·자본잠식)로 D/E 왜곡(산정 제외)"
    elif de_num is not None:
        facts["D/E"] = de_num  # 부채/자본 (낮을수록 빚 부담 적음)

    # Altman-Z — |Z|>20 = BS 항목 기간불일치 추출(원천 버그) → 산정불가, 그 외 zone 병기.
    az_v, az_na = _guarded(row.get("altman_z"), _ALTMAN_MAX, digits=1)
    az_num = _num(row.get("altman_z"), 1)
    if az_na:
        facts["Altman-Z"] = "산정불가"
        fnote["Altman-Z"] = "재무항목 기간 불일치 추출로 Z 왜곡(산정 제외)"
    elif az_num is not None:
        facts["Altman-Z"] = az_num
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

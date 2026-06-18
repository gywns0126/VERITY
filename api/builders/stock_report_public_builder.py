"""stock_report_public_builder — 공개 터미널 "종목 리포트" public-safe 합성 빌더.

2026-06-18 전종목 확장: 운영풀 10 → KR 전종목(~1,650).
  - 운영풀(recommendations.json): rich (PER/PBR/ROE/부채/Altman-Z/시총/지분/컨센/일정/공시)
  - 그 외(dart_fundamentals_kr.json 1,650): light (PER/PBR/ROE/부채/영업이익률 + 공시 + 컨센)
  - name/market = kr_listed.json (KP/KQ), 보조 kr_stock_names.json
  - 공시 = dart_catalyst_alerts.jsonl (시장 전체 수집, ticker별)
  - 컨센서스 = consensus_data.json (증권사 집계 — 자체 의견 아님)

🚨 RULE 7 — **allowlist** (점수/등급/추천/trade_plan/prediction 등 전부 비노출).
순수 변환 — 외부호출/KIS 0. publish: data/stock_report_public.json (action.yml 목록 등재됨).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REC_PATH = os.path.join(_ROOT, "data", "recommendations.json")
FUND_PATH = os.path.join(_ROOT, "data", "dart_fundamentals_kr.json")
KRLISTED_PATH = os.path.join(_ROOT, "data", "kr_listed.json")
NAMES_PATH = os.path.join(_ROOT, "data", "kr_stock_names.json")
CONSENSUS_PATH = os.path.join(_ROOT, "data", "consensus_data.json")
CATALYST_PATH = os.path.join(_ROOT, "data", "dart_catalyst_alerts.jsonl")
OUTPUT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="

FAMILY_TYPES = {"동일인", "친족"}
MARKET_MAP = {"KP": "KOSPI", "KQ": "KOSDAQ", "KN": "KONEX"}


def _now_kst() -> datetime:
    return datetime.now(KST)


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _is_kr(rec: Dict[str, Any]) -> bool:
    if str(rec.get("currency") or "") == "USD":
        return False
    mkt = str(rec.get("market") or "")
    return "KOSPI" in mkt or "KOSDAQ" in mkt or "KRX" in mkt or str(rec.get("ticker", "")).isdigit()


def _fmt_cap(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if x <= 0:
        return "—"
    if x >= 1e12:
        return f"{x / 1e12:.1f}조"
    if x >= 1e8:
        return f"{x / 1e8:.0f}억"
    return f"{x:,.0f}"


def _financials(fund: Dict[str, Any]) -> Dict[str, Any] | None:
    """재무 요약 (최근 결산, dart_fundamentals_kr — 단일 연도 실값). 추이 X(KR 소스 단년)."""
    if not fund:
        return None
    out: Dict[str, str] = {}
    for label, key in [("매출", "revenue"), ("영업이익", "operating_profit"), ("순이익", "net_income")]:
        v = fund.get(key)
        if v:
            out[label] = _fmt_cap(v)
    if not out:
        return None
    yr = fund.get("report_date")
    return {"values": out, "period": (str(yr) if yr else "최근 결산")}


def _num(v: Any, suffix: str = "", digits: int = 1) -> Optional[str]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    s = f"{x:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{x:.0f}"
    return f"{s}{suffix}"


def _load_catalyst_by_ticker() -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    if not os.path.isfile(CATALYST_PATH):
        return out
    seen: set = set()
    with open(CATALYST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                continue
            tk = str(a.get("ticker") or "")
            rc = str(a.get("rcept_no") or "")
            if not tk or not rc or rc in seen:
                continue
            seen.add(rc)
            dt = str(a.get("rcept_dt") or "")
            date = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) == 8 else dt
            out.setdefault(tk, []).append({
                "title": a.get("report_nm") or "",
                "label": a.get("pblntf_label") or "",
                "date": date,
                "is_correction": bool(a.get("is_correction")),
                "filer": a.get("flr_nm") or "",
                "source_url": DART + rc,
            })
    for tk in out:
        out[tk].sort(key=lambda d: d["date"], reverse=True)
    return out


def _ownership(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ftc = ((rec.get("group_structure") or {}).get("ftc_official") or {})
    sh = ftc.get("shareholders") or []
    if not isinstance(sh, list) or not sh:
        return None
    family = 0.0
    for s in sh:
        if str(s.get("type") or "") in FAMILY_TYPES:
            try:
                family += float(s.get("qota_rate") or 0)
            except (TypeError, ValueError):
                pass
    return {
        "family_pct": round(family, 2),
        "note": "동일인+친족 합산 (소속회사 지배지분 별도) · 공정위 분류",
        "source": "공정거래위원회 기업집단포털" + (f" ({ftc.get('as_of_year')})" if ftc.get("as_of_year") else ""),
    }


def _consensus_from_rec(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    c = rec.get("consensus") or {}
    if not c.get("consensus_available"):
        return None
    out: Dict[str, Any] = {}
    if c.get("target_price"):
        out["target_price"] = _fmt_won(c["target_price"])
    if c.get("investment_opinion"):
        out["opinion"] = str(c["investment_opinion"])
    eps = rec.get("eps")
    try:
        if eps and float(eps) != 0:
            out["eps"] = f"{float(eps):,.0f}원"
    except (TypeError, ValueError):
        pass
    return out or None


def _fmt_won(v: Any) -> Optional[str]:
    try:
        return f"{float(v):,.0f}원"
    except (TypeError, ValueError):
        return None


def build_rich(rec: Dict[str, Any], catalyst: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    ticker = str(rec.get("ticker") or "")
    altman = (((rec.get("quant_factors") or {}).get("quality") or {}).get("altman") or {})
    facts: Dict[str, str] = {}
    fnote: Dict[str, str] = {}
    for key, src, suf, dg in [("PER", "per", "", 1), ("PBR", "pbr", "", 1),
                               ("ROE", "roe", "%", 1), ("부채비율", "debt_ratio", "%", 0)]:
        val = _num(rec.get(src), suf, dg)
        if val is not None:
            facts[key] = val
    if altman.get("z_score") is not None:
        az = _num(altman.get("z_score"), digits=1)
        if az is not None:
            facts["Altman-Z"] = az
            if altman.get("zone"):
                fnote["Altman-Z"] = "안전구간" if altman["zone"] == "safe" else str(altman["zone"])
    if rec.get("market_cap"):
        facts["시가총액"] = _fmt_cap(rec.get("market_cap"))
    return {
        "ticker": ticker, "name": rec.get("name") or ticker, "market": rec.get("market") or "",
        "business": rec.get("company_tagline") or rec.get("company_type") or "",
        "facts": facts, "facts_note": fnote,
        "disclosures": catalyst.get(ticker, [])[:8],
        "ownership": _ownership(rec),
        "consensus": _consensus_from_rec(rec),
        "calendar": ([{"event": "실적발표", "kind": "실적", "date": (rec.get("earnings") or {}).get("next_earnings")}]
                     if (rec.get("earnings") or {}).get("next_earnings") else []),
        "rich": True,
    }


def build_light(ticker: str, fund: Dict[str, Any], name: str, market: str,
                catalyst: Dict[str, List[Dict[str, Any]]],
                consensus_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    facts: Dict[str, str] = {}
    for key, src, suf, dg in [("PER", "per", "", 1), ("PBR", "pbr", "", 1),
                               ("ROE", "roe", "%", 1), ("부채비율", "debt_ratio", "%", 0),
                               ("영업이익률", "op_margin", "%", 1)]:
        val = _num(fund.get(src), suf, dg)
        if val is not None:
            facts[key] = val
    cons = consensus_map.get(ticker)
    return {
        "ticker": ticker, "name": name or ticker, "market": market or "",
        "business": "",
        "facts": facts, "facts_note": {},
        "disclosures": catalyst.get(ticker, [])[:8],
        "ownership": None,
        "consensus": cons,
        "calendar": [],
        "rich": False,
    }


def main() -> int:
    ok = False
    try:
        recs = _load_json(REC_PATH, [])
        if not isinstance(recs, list):
            recs = []
        fund_doc = _load_json(FUND_PATH, {})
        fundamentals = (fund_doc.get("fundamentals") if isinstance(fund_doc, dict) else {}) or {}
        kr_listed = _load_json(KRLISTED_PATH, {}) or {}
        names = _load_json(NAMES_PATH, {}) or {}
        catalyst = _load_catalyst_by_ticker()

        # 컨센서스 map (증권사 집계 — 자체 의견 아님)
        consensus_map: Dict[str, Dict[str, Any]] = {}
        cdoc = _load_json(CONSENSUS_PATH, {})
        cstocks = (cdoc.get("stocks") if isinstance(cdoc, dict) else cdoc) or []
        for c in (cstocks if isinstance(cstocks, list) else []):
            tk = str(c.get("ticker") or "")
            if not tk:
                continue
            entry: Dict[str, Any] = {}
            tp = _fmt_won(c.get("target_price"))
            if tp:
                entry["target_price"] = tp
            if c.get("investment_opinion"):
                entry["opinion"] = str(c["investment_opinion"])
            if entry:
                consensus_map[tk] = entry

        # 운영풀 rich (recommendations)
        rich_by_ticker: Dict[str, Dict[str, Any]] = {}
        for r in recs:
            if _is_kr(r) and r.get("ticker"):
                t = str(r["ticker"])
                rich_by_ticker[t] = build_rich(r, catalyst)

        def _name_market(tk: str):
            li = kr_listed.get(tk) if isinstance(kr_listed, dict) else None
            if isinstance(li, dict):
                return li.get("name") or names.get(tk) or tk, MARKET_MAP.get(li.get("market"), li.get("market") or "")
            return (names.get(tk) or tk), ""

        # universe = fundamentals 1,650 ∪ 운영풀
        universe = set(fundamentals.keys()) | set(rich_by_ticker.keys())
        stocks: List[Dict[str, Any]] = []
        for tk in universe:
            if tk in rich_by_ticker:
                stocks.append(rich_by_ticker[tk])
            else:
                fund = fundamentals.get(tk) or {}
                nm, mk = _name_market(tk)
                light = build_light(tk, fund, nm, mk, catalyst, consensus_map)
                # 컨센서스 보강만 있고 facts 전무면 노출 가치 낮음 — facts 있을 때만
                if light["facts"] or light["disclosures"]:
                    stocks.append(light)

        # 재무요약 (최근 결산, dart_fundamentals 실값) 부착
        for s in stocks:
            fin = _financials(fundamentals.get(s["ticker"]))
            if fin:
                s["financials"] = fin

        # 정렬: rich 먼저 → 공시 많은 순 → ticker
        stocks.sort(key=lambda s: (s.get("rich", False), len(s.get("disclosures", [])), s["ticker"]), reverse=True)
        for s in stocks:
            s.pop("rich", None)

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "DART(전자공시·재무) · 공정위 · FnGuide 집계 · KRX",
                "count": len(stocks),
                "rich_count": len(rich_by_ticker),
                "note": "공개 사실만 (RULE 7 allowlist) — 점수·등급·추천 비노출. 컨센서스=증권사 집계(자체 의견 아님). 가격은 클라이언트 라이브 조회.",
            },
            "stocks": stocks,
        }
        if not stocks and os.path.isfile(OUTPUT_PATH):
            print("[stock_report_public] 0 stocks — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[stock_report_public] logged=True · {len(stocks)} 종목 (rich {len(rich_by_ticker)}) -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[stock_report_public] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[stock_report_public] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

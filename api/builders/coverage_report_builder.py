"""커버리지(채움율) 감사 — 리포트 섹션별 데이터 채움율 일일 측정 (2026-07-04 커버리지 스프린트).

신선도 감사(freshness — "언제 갱신됐나")와 직교하는 축: "얼마나 채워져 있나".
백필로 올린 커버리지가 소리 없이 회귀하면 즉시 가시화 — 회귀 >10%p 시 WARN 로그(워크플로 로그 가시).

입력(read-only, 로컬 산출물): stock_report_public + dart_quarterly_public + disclosure_forensics
  + insider_trades + securities_lending + stock_flow_5d
출력: data/metadata/coverage_report.json (최신 스냅샷) + coverage_history.jsonl (append, 추이)

규율: 측정만 — 점수/판정/수정 0. 파일 없음 = 해당 항목 null (측정 불가 표기, 가짜 0% 아님).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA = os.path.join(_ROOT, "data")
_META = os.path.join(_DATA, "metadata")
REPORT_PATH = os.path.join(_META, "coverage_report.json")
HISTORY_PATH = os.path.join(_META, "coverage_history.jsonl")

KST = timezone(timedelta(hours=9))

# 리포트 내 필드 채움율 측정 대상 (PublicStockReport 섹션 렌더 가드와 1:1)
REPORT_FIELDS = ["facts", "peer", "financials", "fin_series", "overview", "ownership", "real_estate", "consensus", "calendar"]
US_REPORT_FIELDS = ["facts", "peer", "financials", "fin_series", "consensus", "disclosures"]
# facts 통짜 측정의 사각 — 2026-07-11 사고: 미장 PER/PBR 전량 공백에도 facts 100% 유지(다른 키 잔존).
# 핵심 배수는 서브키 단위로 별도 측정.
FACTS_SUBFIELDS = ["PER", "PBR"]
REGRESSION_WARN_PP = 10.0  # 전 스냅샷 대비 하락 경고 임계 (%p)
# 핵심 지표 급락 = 결함 확률 압도적 (유기적 감소로 30%p 불가) → exit 1 로 같은 run 의 publish 차단.
CORE_FAIL_PP = 30.0
CORE_PREFIXES = ("field.facts", "us.field.facts", "us_smallcap.field.facts",
                 "field.financials", "us.field.financials")


def _load(name: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(_DATA, name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _filled(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def _pct(n: int, total: int) -> Optional[float]:
    return round(n * 100.0 / total, 1) if total > 0 else None


def build() -> Dict[str, Any]:
    report_doc = _load("stock_report_public.json")
    kr = [s for s in ((report_doc or {}).get("stocks") or []) if str(s.get("ticker", "")).isdigit()]
    kr_total = len(kr)

    fields: Dict[str, Any] = {}
    for f in REPORT_FIELDS:
        if kr_total == 0:
            fields[f] = None
            continue
        filled = sum(1 for s in kr if _filled(s.get(f)))
        fields[f] = {"filled": filled, "pct": _pct(filled, kr_total)}
    for sub in FACTS_SUBFIELDS:
        if kr_total == 0:
            fields[f"facts.{sub}"] = None
            continue
        filled = sum(1 for s in kr if _filled((s.get("facts") or {}).get(sub)))
        fields[f"facts.{sub}"] = {"filled": filled, "pct": _pct(filled, kr_total)}

    def _companion(name: str, key: str = "stocks") -> Optional[Dict[str, Any]]:
        doc = _load(name)
        if doc is None:
            return None
        v = doc.get(key)
        cnt = len(v) if isinstance(v, (list, dict)) else None
        if cnt is None:
            return None
        return {"count": cnt, "pct_of_kr": _pct(cnt, kr_total)}

    companions = {
        "quarterly": _companion("dart_quarterly_public.json"),
        "forensics": _companion("disclosure_forensics.json"),
        "insider_kr": _companion("insider_trades.json"),
        "lending": _companion("securities_lending.json"),
        "flow_5d": _companion("stock_flow_5d.json", "flows"),
    }

    # 미장 축 (2026-07-04 확대) — us_stock_report + us_quarterly
    us_doc = _load("us_stock_report_public.json")
    us = (us_doc or {}).get("stocks") or []
    us_total = len(us)
    us_fields: Dict[str, Any] = {}
    for f in US_REPORT_FIELDS:
        if us_total == 0:
            us_fields[f] = None
            continue
        filled = sum(1 for s in us if _filled(s.get(f)))
        us_fields[f] = {"filled": filled, "pct": _pct(filled, us_total)}
    for sub in FACTS_SUBFIELDS:
        if us_total == 0:
            us_fields[f"facts.{sub}"] = None
            continue
        filled = sum(1 for s in us if _filled((s.get("facts") or {}).get(sub)))
        us_fields[f"facts.{sub}"] = {"filled": filled, "pct": _pct(filled, us_total)}

    def _us_companion(name: str, key: str = "stocks") -> Optional[Dict[str, Any]]:
        doc = _load(name)
        if doc is None:
            return None
        v = doc.get(key)
        cnt = len(v) if isinstance(v, (list, dict)) else None
        if cnt is None:
            return None
        return {"count": cnt, "pct_of_us": _pct(cnt, us_total)}

    us_companions = {
        "us_quarterly": _us_companion("us_quarterly_public.json"),
        "us_insider": _us_companion("us_insider_trades.json"),
    }

    # 미장 스몰캡 트랙 (2026-07-04 S1) — 별도 파일이라 별도 축
    sc_doc = _load("us_stock_report_us_smallcap.json")
    sc = (sc_doc or {}).get("stocks") or []
    sc_total = len(sc)
    sc_fields: Dict[str, Any] = {}
    for f in ["facts", "fin_series", "financials"]:
        if sc_total == 0:
            sc_fields[f] = None
            continue
        filled = sum(1 for s in sc if _filled(s.get(f)))
        sc_fields[f] = {"filled": filled, "pct": _pct(filled, sc_total)}
    for sub in FACTS_SUBFIELDS:
        if sc_total == 0:
            sc_fields[f"facts.{sub}"] = None
            continue
        filled = sum(1 for s in sc if _filled((s.get("facts") or {}).get(sub)))
        sc_fields[f"facts.{sub}"] = {"filled": filled, "pct": _pct(filled, sc_total)}

    return {
        "_meta": {
            "generated_at": datetime.now(KST).isoformat(),
            "source": "coverage_report_builder — 리포트 필드·동반 파일 채움율 측정 (판정·수정 0)",
        },
        "kr_total": kr_total,
        "fields": fields,
        "companions": companions,
        "us_total": us_total,
        "us_fields": us_fields,
        "us_companions": us_companions,
        "us_smallcap_total": sc_total,
        "us_smallcap_fields": sc_fields,
    }


def _flat_pcts(report: Dict[str, Any]) -> Dict[str, float]:
    """회귀 비교용 {지표: pct} — null 항목 제외."""
    out: Dict[str, float] = {}
    for k, v in (report.get("fields") or {}).items():
        if isinstance(v, dict) and v.get("pct") is not None:
            out[f"field.{k}"] = v["pct"]
    for k, v in (report.get("companions") or {}).items():
        if isinstance(v, dict) and v.get("pct_of_kr") is not None:
            out[f"companion.{k}"] = v["pct_of_kr"]
    for k, v in (report.get("us_fields") or {}).items():
        if isinstance(v, dict) and v.get("pct") is not None:
            out[f"us.field.{k}"] = v["pct"]
    for k, v in (report.get("us_companions") or {}).items():
        if isinstance(v, dict) and v.get("pct_of_us") is not None:
            out[f"us.companion.{k}"] = v["pct_of_us"]
    for k, v in (report.get("us_smallcap_fields") or {}).items():
        if isinstance(v, dict) and v.get("pct") is not None:
            out[f"us_smallcap.field.{k}"] = v["pct"]
    return out


def main() -> None:
    prev = None
    try:
        with open(REPORT_PATH, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        pass

    report = build()
    os.makedirs(_META, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    now = _flat_pcts(report)
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"date": datetime.now(KST).strftime("%Y-%m-%d"), "kr_total": report["kr_total"], **now}, ensure_ascii=False) + "\n")

    warns = fails = 0
    if prev:
        before = _flat_pcts(prev)
        for k, pct in now.items():
            old = before.get(k)
            if old is None or old - pct <= REGRESSION_WARN_PP:
                continue
            if old - pct > CORE_FAIL_PP and k.startswith(CORE_PREFIXES):
                print(f"[coverage] FAIL {k} 핵심 급락: {old}% → {pct}% (-{round(old - pct, 1)}%p) — publish 차단")
                fails += 1
            else:
                print(f"[coverage] WARN {k} 회귀: {old}% → {pct}% (-{round(old - pct, 1)}%p)")
                warns += 1
    print(f"[coverage] logged=True · kr={report['kr_total']} · 지표 {len(now)}개 · 회귀경고 {warns}건 · 핵심급락 {fails}건 → {REPORT_PATH}")
    if fails:
        # 핵심 필드 급락 = 결함 산출물. 같은 run 의 publish/commit step 진행 차단 (2026-07-11 PM
        # "기본 데이터는 확실히" — 로고 순백 7건·미장 PER 전량 공백이 초록 CI 로 하루 노출된 사고).
        raise SystemExit(1)


if __name__ == "__main__":
    main()

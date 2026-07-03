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
REGRESSION_WARN_PP = 10.0  # 전 스냅샷 대비 하락 경고 임계 (%p)


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

    return {
        "_meta": {
            "generated_at": datetime.now(KST).isoformat(),
            "source": "coverage_report_builder — 리포트 필드·동반 파일 채움율 측정 (판정·수정 0)",
        },
        "kr_total": kr_total,
        "fields": fields,
        "companions": companions,
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

    warns = 0
    if prev:
        before = _flat_pcts(prev)
        for k, pct in now.items():
            old = before.get(k)
            if old is not None and old - pct > REGRESSION_WARN_PP:
                print(f"[coverage] WARN {k} 회귀: {old}% → {pct}% (-{round(old - pct, 1)}%p)")
                warns += 1
    print(f"[coverage] logged=True · kr={report['kr_total']} · 지표 {len(now)}개 · 회귀경고 {warns}건 → {REPORT_PATH}")


if __name__ == "__main__":
    main()

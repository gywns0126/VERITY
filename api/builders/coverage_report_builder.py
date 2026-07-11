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
# 절대 하한 — baseline 무관. 유니버스 충분(≥MIN_UNIVERSE)한 핵심 필드가 이 밑 = 붕괴.
#   회귀 게이트의 사각(초기 run·만성 결손·baseline 오염 = 급락으로 안 잡힘) 보완. 2026-07-12.
CORE_FLOOR_PCT = 5.0
MIN_UNIVERSE = 100
CORE_PREFIXES = ("field.facts", "us.field.facts", "us_smallcap.field.facts",
                 "field.financials", "us.field.financials",
                 # 동반 파일 붕괴도 게이트 (2026-07-11 us_quarterly 1,494→10종 실사고)
                 "companion.quarterly", "us.companion.us_quarterly")


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


def _universe_for(key: str, report: Dict[str, Any]) -> int:
    """flat 지표 키의 유니버스 총수 (절대 하한 게이트용)."""
    if key.startswith("us_smallcap."):
        return int(report.get("us_smallcap_total") or 0)
    if key.startswith("us."):
        return int(report.get("us_total") or 0)
    return int(report.get("kr_total") or 0)


def main() -> None:
    prev = None
    try:
        with open(REPORT_PATH, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        pass

    report = build()
    os.makedirs(_META, exist_ok=True)
    now = _flat_pcts(report)

    warns = fails = 0
    reasons = []

    # 1) 회귀 게이트 — 마지막 GOOD baseline(REPORT_PATH) 대비 핵심 필드 급락(>30%p)
    if prev:
        before = _flat_pcts(prev)
        for k, pct in now.items():
            old = before.get(k)
            if old is None or old - pct <= REGRESSION_WARN_PP:
                continue
            if old - pct > CORE_FAIL_PP and k.startswith(CORE_PREFIXES):
                msg = f"{k} 핵심 급락 {old}%→{pct}% (-{round(old - pct, 1)}%p)"
                print(f"[coverage] FAIL {msg} — publish 차단")
                reasons.append(msg)
                fails += 1
            else:
                print(f"[coverage] WARN {k} 회귀: {old}% → {pct}% (-{round(old - pct, 1)}%p)")
                warns += 1

    # 2) 절대 하한 게이트 — baseline 무관. 유니버스 충분한 핵심 필드가 바닥 = 붕괴.
    #    회귀 게이트가 못 잡는 초기 run·만성 결손·baseline 오염 케이스 포착 (fail-closed 보강).
    for k, pct in now.items():
        if not k.startswith(CORE_PREFIXES):
            continue
        uni = _universe_for(k, report)
        if uni >= MIN_UNIVERSE and pct < CORE_FLOOR_PCT:
            msg = f"{k} 절대 붕괴 {pct}% < {CORE_FLOOR_PCT}% (N={uni})"
            print(f"[coverage] FLOOR {msg} — publish 차단")
            reasons.append(msg)
            fails += 1

    blocked = fails > 0

    # history 는 항상 기록(추이) — blocked 플래그 포함. broad git add data/ = RULE 4 (commit step 등재).
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"date": datetime.now(KST).strftime("%Y-%m-%d"),
                            "ts": datetime.now(KST).isoformat(),
                            "kr_total": report["kr_total"], "blocked": blocked,
                            "fails": fails, "warns": warns, **now}, ensure_ascii=False) + "\n")

    if blocked:
        # 결함 산출물 = GOOD baseline(REPORT_PATH) 덮지 않음 → 다음 run 도 급락/붕괴 계속 탐지(지속 fail-closed).
        #   진단본만 별도 기록. 워크플로가 이 step outcome=failure 로 commit/publish 차단 (2026-07-12 배선).
        blocked_path = os.path.join(_META, "coverage_report.blocked.json")
        with open(blocked_path, "w", encoding="utf-8") as f:
            json.dump({"blocked_at": datetime.now(KST).isoformat(), "reasons": reasons, "report": report},
                      f, ensure_ascii=False, indent=1)
        print(f"[coverage] BLOCKED · 핵심결함 {fails}건 · baseline 보존 · 진단={blocked_path}")
        raise SystemExit(1)

    # 통과 = 새 GOOD baseline 확정
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"[coverage] OK · kr={report['kr_total']} · 지표 {len(now)}개 · 회귀경고 {warns}건 · 핵심결함 0건 → {REPORT_PATH}")


if __name__ == "__main__":
    main()

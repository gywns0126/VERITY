#!/usr/bin/env python3
"""거시 **필드 단위** 신선도·출처 감사. PM 지시 2026-08-19.

## 왜 파일 단위로는 부족한가

`freshness_sla.json` 은 71 스트림의 **파일 나이**를 본다(`macro_snapshot` max_age 360분).
그런데 파일이 20분 전 것이어도 그 안의 `consumer_sentiment` 는 **2.5개월 전 값**일 수 있다.
FRED 계열은 월/분기 갱신이라 정상이지만, **정상 지연과 파이프라인 고장이 구분되지 않는다.**
파일 신선도는 "언제 받아왔나" 이고 필드 기준일은 "언제 시점의 값인가" 다 — 다른 질문이다.
([[feedback_snapshot_cannot_answer_point_in_time]] 계열)

## 무엇을 잡나 — 기계적으로 판정 가능한 3종만

🚨 **D1. 이름과 출처가 어긋난 필드 (같은 series_id 를 다른 이름으로 서빙)**
   실측 2026-08-19: `gdp_growth` 와 `us_recession_smoothed_prob` 이 **둘 다
   series_id=RECPROUSM156N**(경기침체확률)이다. `gdp_growth` 는 GDP 가 아니라
   `2.5 − 0.08 × 침체확률` 이라는 선형변환이고 `source_note` 에 정직하게 적혀 있다.
   그러나 **필드 이름이 gdp_growth 라** source_note 를 안 읽는 소비자는 GDP 로 읽는다.
   실제로 `detect_economic_quadrant` 가 `growth_up = gdp_growth > 1.5` 로 쓰는데,
   산식상 침체확률이 **12.5% 를 넘어야** growth_down 이 된다(현재 0.6%) = 사실상 고정.

🚨 **D2. 파생·프록시인데 등록되지 않은 필드**
   `source_note` 에 proxy/derived/근사 표기가 있으면 아래 `DERIVED_REGISTRY` 에 있어야 한다.
   등록되지 않은 파생 = 새로 생겼거나 조용히 바뀐 것이므로 사람이 봐야 한다.

**D3. 기준일 나이 초과**
   필드별 기대 갱신 주기(cadence)를 넘긴 값. 월간 지표에 일간 잣대를 대면 전부 빨개지므로
   **계열별 기대 주기**를 명시하고 그 배수로만 판정한다.

## 무엇을 잡지 않나 (정직 선언)

- 값의 **정확성** — FRED 가 준 숫자가 맞는지는 여기서 못 본다(원천 대조 필요)
- 이름/의미 불일치 중 series_id 가 **다른** 경우 — 예: `cpi_yoy` 가 실은 core CPI
  (series_id=CPILFESL) 인 건 D1 로 못 잡는다. 그래서 `SEMANTIC_PINS` 에 손으로 고정한다.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAP = os.path.join(_ROOT, "data", "macro_snapshot.json")

# 계열별 기대 갱신 주기(일). 이 값의 EXPIRY_MULT 배를 넘으면 D3.
EXPECTED_CADENCE_DAYS = {
    "dgs10": 1, "dgs2": 1, "vix_close": 1, "hy_spread": 1,
    "breakeven_inflation_10y": 1, "cape": 1, "korea_gov_10y": 1,
    "fed_balance_sheet": 7,
    "core_cpi": 31, "cpi_yoy": 31, "unemployment_rate": 31, "m2": 31,
    "consumer_sentiment": 31, "us_recession_smoothed_prob": 31,
    "gdp_growth": 31, "korea_policy_rate": 31, "korea_discount_rate": 31,
}
EXPIRY_MULT = 3.0          # 정상 지연과 고장을 가르는 배수. 보수적으로 넉넉히.

# 🚨 D2 — 파생/프록시로 **알려진** 필드. 신규 파생이 조용히 끼어들면 감사가 잡는다.
#   등록은 "괜찮다" 가 아니라 "이미 알고 있고 아래 위험이 문서화됐다" 는 뜻이다.
DERIVED_REGISTRY = {
    "gdp_growth": ("RECPROUSM156N 침체확률의 선형변환 2.5−0.08×rp. **GDP 실측 아님.** "
                   "quadrant growth_up 임계 1.5 대비 rp≥12.5% 에서만 뒤집혀 사실상 고정"),
    "cpi_yoy": ("core_cpi.yoy_pct 를 그대로 옮긴 값(series_id=CPILFESL=**근원** CPI). "
                "헤드라인 CPI 아님. quadrant inflation_up 임계 3.0 은 헤드라인 기준 관행이라 "
                "근원을 대면 inflation_down 쪽으로 치우친다"),
}

# 🚨 이름이 암시하는 의미와 실제 series_id 가 다른 곳을 손으로 고정한다.
#   (필드명 → 반드시 이 series_id 여야 함). 어긋나면 D1-b.
SEMANTIC_PINS = {
    "unemployment_rate": "UNRATE",
    "vix_close": "VIXCLS",
    "hy_spread": "BAMLH0A0HYM2",
    "fed_balance_sheet": "WALCL",
    "breakeven_inflation_10y": "T10YIE",
}


def _parse_date(v: Any) -> date | None:
    s = str(v or "")
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y%m", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            d = datetime.strptime(s[:len(datetime.now().strftime(fmt))] if fmt == "%Y%m"
                                  else s, fmt)
            return d.date()
        except (ValueError, TypeError):
            continue
    # ISO with timezone (as_of)
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        return None


def collect_fields(snap: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """FRED/ECOS 계열 필드를 평평하게 → {이름: {value, date, series_id, source_note}}"""
    out: Dict[str, Dict[str, Any]] = {}
    macro = snap.get("macro") or {}
    for group in ("fred", "ecos"):
        for name, v in (macro.get(group) or {}).items():
            if not isinstance(v, dict):
                continue
            out[name] = {
                "group": group,
                "value": v.get("value", v.get("pct", v.get("index", v.get("trillions_usd",
                          v.get("billions_usd"))))),
                "date": v.get("date") or v.get("as_of"),
                "series_id": v.get("series_id") or v.get("source"),
                "source_note": v.get("source_note") or "",
            }
    return out


def audit(snap: Dict[str, Any], today: date | None = None) -> Tuple[List[str], Dict[str, Any]]:
    today = today or date.today()
    fields = collect_fields(snap)
    findings: List[str] = []

    # D1-a: 같은 series_id 를 서로 다른 이름으로 서빙
    by_sid: Dict[str, List[str]] = defaultdict(list)
    for name, f in fields.items():
        sid = f.get("series_id")
        if sid:
            by_sid[str(sid)].append(name)
    for sid, names in sorted(by_sid.items()):
        if len(names) > 1:
            findings.append(
                f"D1-a 같은 출처를 다른 이름으로 서빙: series_id={sid} → {sorted(names)}. "
                f"이름만 읽는 소비자는 서로 다른 지표라고 믿는다")

    # D1-b: 이름↔series_id 고정 위반
    for name, sid in SEMANTIC_PINS.items():
        f = fields.get(name)
        if f and f.get("series_id") and str(f["series_id"]) != sid:
            findings.append(f"D1-b 의미 고정 위반: {name} 의 series_id 가 "
                            f"{f['series_id']} (기대 {sid})")

    # D2: 미등록 파생
    for name, f in sorted(fields.items()):
        note = str(f.get("source_note") or "")
        looks_derived = any(t in note.lower() for t in ("proxy", "derived", "근사", "프록시"))
        if looks_derived and name not in DERIVED_REGISTRY:
            findings.append(f"D2 미등록 파생 필드: {name} — source_note='{note[:80]}'. "
                            f"DERIVED_REGISTRY 등재 후 위험을 명시할 것")

    # D3: 기준일 나이 초과
    ages: Dict[str, int] = {}
    for name, f in sorted(fields.items()):
        d = _parse_date(f.get("date"))
        if d is None:
            if name != "available":
                findings.append(f"D3-x 기준일 파싱 불가: {name} date={f.get('date')!r}")
            continue
        age = (today - d).days
        ages[name] = age
        cad = EXPECTED_CADENCE_DAYS.get(name)
        if cad and age > cad * EXPIRY_MULT:
            findings.append(f"D3 기준일 초과: {name} {age}일 경과 "
                            f"(기대주기 {cad}일 × {EXPIRY_MULT:g} = {cad*EXPIRY_MULT:.0f}일)")

    meta = {
        "fields_total": len(fields),
        "fields_with_date": len(ages),
        "fields_with_series_id": sum(1 for f in fields.values() if f.get("series_id")),
        "derived_registered": len(DERIVED_REGISTRY),
        "collected_at": snap.get("collected_at"),
        "ages": ages,
    }
    return findings, meta


def main() -> int:
    if not os.path.exists(SNAP):
        print(f"[macro_audit] 스냅샷 없음: {SNAP}")
        return 0        # 산출물 부재는 이 감사의 대상이 아니다(파일 SLA 소관)
    with open(SNAP, encoding="utf-8") as f:
        snap = json.load(f)
    findings, meta = audit(snap)

    print("═" * 64)
    print("거시 필드 단위 신선도·출처 감사")
    print("═" * 64)
    print(f"수집시각 {meta['collected_at']} · 필드 {meta['fields_total']} "
          f"· 기준일 보유 {meta['fields_with_date']} · 출처ID 보유 {meta['fields_with_series_id']} "
          f"· 등록 파생 {meta['derived_registered']}")

    print("\n[필드별 기준일 나이]")
    for name, age in sorted(meta["ages"].items(), key=lambda x: -x[1]):
        cad = EXPECTED_CADENCE_DAYS.get(name)
        mark = "🚨" if (cad and age > cad * EXPIRY_MULT) else ("·" if cad else "?")
        print(f"  {mark} {name:<28} {age:>4}일  (기대주기 {cad if cad else '미정의'})")

    if findings:
        print(f"\n🚨 발견 {len(findings)}건")
        for i, f in enumerate(findings, 1):
            print(f"  {i}. {f}")
    else:
        print("\n발견 0 — 필드 단위 정합 ✓")

    print(f"\n[등록된 파생 필드 {len(DERIVED_REGISTRY)}건 — 이름이 출처를 오도한다]")
    for k, why in DERIVED_REGISTRY.items():
        print(f"  · {k}: {why}")
    return 0        # 감사는 보고용 — 파이프라인을 죽이지 않는다(게이트는 테스트가 맡는다)


if __name__ == "__main__":
    raise SystemExit(main())

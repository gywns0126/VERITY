#!/usr/bin/env python3
"""결손 원인 분류 — "80% 네" 로 끝나지 않게 한다.

## 왜 (2026-08-22)

`coverage_report_builder` 는 채움율 %만 낸다. 그래서 `financials 80.2%` 를 6주 동안 보고도
**아무도 왜인지 몰랐다.** 손으로 파보니 원인은 데이터 부재가 아니라 **수집 유니버스 누락**이었고
(1,611 vs 발행 1,790 → 179종목이 DART 에 물어본 적조차 없음), 미수집 10종목을 직접 물으니
**10/10 존재**했다. 즉 **고칠 수 있는 결손이 비율 뒤에 숨어 있었다.**

🚨 이 스크립트가 재는 것은 채움율이 아니라 **"왜 비었는가"** 다. 원인이 갈려야 조치가 갈린다:

    ① 유니버스 누락   수집 대상에 없었다            → 🔧 목록 정합으로 고침 (자동 큐)
    ② 소스 부재       물어봤는데 원천에 없다         → 신고만 (우리 잘못 아님)
    ③ 파싱 실패       원천엔 있는데 우리가 못 읽었다  → 🔧 파서 수정 (자동 큐)
    ④ 정상 부재       스팩·우선주·신규상장 결산 미도래 → 정상, 분모에서 뺀다

②와 ③은 **원천을 물어봐야** 갈린다. 전 종목을 매번 물으면 쿼터가 남지 않으므로
**probe 예산**(기본 40건/run)만 표본 조회하고 나머지는 `미분류` 로 남긴다 —
🚨 모르는 것을 아는 척하지 않는다. 며칠에 걸쳐 자연히 해소된다.

출력: data/metadata/data_gap_report.json
  · `refillable` = ①③ 합계. **이 숫자가 0 이 아니면 우리가 안 고친 결손이 있다는 뜻이다.**

사용: python3 scripts/audit/data_gap_classifier.py [--probe N] [--field financials]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
KST = timezone(timedelta(hours=9))
_DATA = os.path.join(_ROOT, "data")
_META = os.path.join(_DATA, "metadata")
OUT = os.path.join(_META, "data_gap_report.json")

# 측정 대상 = 리포트 필드 : (그 필드를 채우는 원천 파일, 원천 내 종목 맵 경로)
FIELDS = {
    "financials": ("dart_fundamentals_kr.json", ("fundamentals",)),
    "fin_series": (None, None),          # 원천이 여러 곳 — 유니버스 누락만 판정
    "peer": (None, None),
    "real_estate": (None, None),
    "calendar": (None, None),
}
# ④ 정상 부재 판정 — 이름 패턴
_SPAC = re.compile(r"스팩|기업인수목적|제\d+호")
_PREF = re.compile(r"우[BC]?$")


def _load(path, default=None):
    try:
        with open(os.path.join(_DATA, path), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _dig(doc, path):
    for k in path or ():
        doc = (doc or {}).get(k) or {}
    return doc


def _normal_absence(name: str, ticker: str) -> str | None:
    """④ 정상 부재 사유. 아니면 None."""
    if _SPAC.search(name):
        return "스팩"
    if _PREF.search(name) and not name.endswith("우리"):
        return "우선주"
    if ticker.startswith("9"):
        return "외국기업"
    return None


def probe_dart(ticker: str) -> bool | None:
    """원천(DART)에 재무제표가 실제로 있는가. True=있음 False=없음 None=조회불가.

    🚨 이 한 번의 조회가 ②(소스 부재)와 ③(파싱 실패)을 가른다. 이게 없으면 둘이 뭉개지고,
       뭉개지면 '고칠 수 있는 결손' 이 '어쩔 수 없는 결손' 으로 위장된다.
    """
    try:
        import requests
        from api.config import DART_API_KEY
        from api.collectors.dart_corp_code import get_corp_code
        cc = get_corp_code(ticker)
        if not cc:
            return None
        year = str(datetime.now(KST).year - 1)
        for fs in ("CFS", "OFS"):
            r = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json",
                             params={"crtfc_key": DART_API_KEY, "corp_code": cc,
                                     "bsns_year": year, "reprt_code": "11011", "fs_div": fs},
                             timeout=15)
            d = r.json()
            if d.get("status") == "000" and (d.get("list") or []):
                return True
        return False
    except Exception:  # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", type=int, default=40, help="②/③ 판별용 원천 조회 예산")
    ap.add_argument("--field", default="financials")
    a = ap.parse_args()

    pub = _load("stock_report_public.json") or {}
    stocks = pub.get("stocks") or []
    if not stocks:
        print("[gap] stock_report_public 없음 — 측정 불가", file=sys.stderr)
        return 1
    uni = {str(s.get("ticker")): (s.get("name") or "") for s in stocks
           if str(s.get("ticker") or "").isdigit()}

    field = a.field
    src_file, src_path = FIELDS.get(field, (None, None))
    src_map = _dig(_load(src_file, {}), src_path) if src_file else {}

    missing = [(t, uni[t]) for t in uni
               if not (next((s for s in stocks if str(s.get("ticker")) == t), {}) or {}).get(field)]

    rows, probed = [], 0
    for tk, nm in missing:
        why = _normal_absence(nm, tk)
        if why:
            rows.append({"ticker": tk, "name": nm, "cause": "④정상부재", "detail": why})
            continue
        if src_file and tk not in src_map:
            # 원천 수집 결과에 키 자체가 없다 = 물어본 적이 없다
            rows.append({"ticker": tk, "name": nm, "cause": "①유니버스누락",
                         "detail": f"{src_file} 에 키 없음"})
            continue
        if not src_file:
            rows.append({"ticker": tk, "name": nm, "cause": "미분류", "detail": "원천 매핑 미등록"})
            continue
        # 키는 있는데 값이 비었다 → 원천을 물어봐야 ②/③ 이 갈린다
        if probed < a.probe:
            probed += 1
            has = probe_dart(tk)
            if has is True:
                rows.append({"ticker": tk, "name": nm, "cause": "③파싱실패",
                             "detail": "원천에 존재하나 우리 값이 빔"})
            elif has is False:
                rows.append({"ticker": tk, "name": nm, "cause": "②소스부재",
                             "detail": "원천에도 없음"})
            else:
                rows.append({"ticker": tk, "name": nm, "cause": "미분류", "detail": "원천 조회 실패"})
        else:
            rows.append({"ticker": tk, "name": nm, "cause": "미분류", "detail": "probe 예산 소진"})

    c = Counter(r["cause"] for r in rows)
    refillable = c["①유니버스누락"] + c["③파싱실패"]
    n = len(uni)
    doc = {
        "_meta": {
            "generated_at": datetime.now(KST).isoformat(),
            "field": field, "universe": n, "missing": len(rows),
            "coverage": round((n - len(rows)) / n, 4) if n else None,
            "probe_budget": a.probe, "probed": probed,
            "note": ("채움율이 아니라 **원인**을 잰다. ①③ = 우리가 고칠 수 있는 결손, "
                     "②④ = 원천 사정. 미분류는 probe 예산 소진분 — 모르는 것을 아는 척하지 않는다."),
        },
        "🚨 refillable": refillable,
        "🚨 refillable_note": "0 이 아니면 우리가 안 고친 결손이 있다는 뜻이다. ②④ 와 섞어 보지 말 것.",
        "by_cause": dict(c),
        "rows": rows,
    }
    os.makedirs(_META, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)

    print(f"[gap] {field}: 유니버스 {n} · 미보유 {len(rows)} "
          f"(커버 {(n-len(rows))/n:.1%}) · probe {probed}/{a.probe}", file=sys.stderr)
    for k, v in c.most_common():
        print(f"        {k:<12}{v:>5}", file=sys.stderr)
    print(f"[gap] 🚨 고칠 수 있는 결손(①+③) = {refillable} -> {os.path.relpath(OUT, _ROOT)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

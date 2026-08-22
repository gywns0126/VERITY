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

# 측정 대상 = 리포트 필드 : 그 필드를 채우는 **필수 원천** 목록.
#   (파일, 종목맵 경로, 라벨). kind="map" = dict 키가 티커 / "rows" = 리스트 안 ticker 필드.
# 🚨 코드에서 실제 배선을 읽어 등록했다(stock_report_public_builder). 추측 금지 —
#   원천을 잘못 매핑하면 ①(유니버스 누락)이 거짓으로 뜨고, 고칠 게 없는 걸 고치러 간다.
FIELDS = {
    # _financials(fundamentals.get(tk))            — builder:1172
    "financials": [("dart_fundamentals_kr.json", ("fundamentals",), "map", "DART 재무")],
    # _peer(tk, fundamentals, sector_map, …)       — builder:1212. 둘 다 있어야 생성된다
    "peer": [("dart_fundamentals_kr.json", ("fundamentals",), "map", "DART 재무"),
             ("kr_sector_map.json", ("map",), "map", "섹터맵")],
    # _kr_earnings_window(earn_pats.get(tk))       — builder:1179
    "calendar": [("kr_earnings_pattern.json", ("patterns",), "map", "실적발표 패턴")],
    # _load_real_estate_history() = fin_history rows(annual) 투자부동산 — builder:989·1277
    "real_estate": [("dart_kr_fin_history.json", ("rows",), "rows", "연간재무 백필")],
    # _load_fin_series() — 원천 배선 미확인이라 등록하지 않는다(추측 금지 → '미분류'로 남음)
    "fin_series": [],
}
# ④ 정상 부재 판정 — 이름 패턴
_SPAC = re.compile(r"스팩|기업인수목적|제\d+호")
_PREF = re.compile(r"우[BC]?$")


def _re_has_value(entries) -> bool:
    """real_estate 전용 — 원천에 **실제 투자부동산 금액**이 있는가.

    🚨 키 존재만으로 ③파싱실패 를 매기면 안 된다. 투자부동산이 **원래 없는 회사**가 다수이고
       (첫 실행에서 560건이 그렇게 오분류됐다), 그건 ④정상부재이지 우리 결함이 아니다.
       591건을 '고칠 수 있는 결손' 이라 신고하면 없는 일을 고치러 간다.
    """
    for r in entries or []:
        if not isinstance(r, dict) or r.get("period") != "annual":
            continue
        f = r.get("fundamentals") or {}
        try:
            if float(f.get("investment_property") or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


# 필드별 "원천에 값이 실제로 있는가" 검사. 없으면 키 존재만 본다.
VALUE_CHECK = {"real_estate": _re_has_value}


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
    sources = FIELDS.get(field) or []
    # 원천별 보유 티커 집합 — rows 형은 리스트 안 ticker 필드를 모은다
    src_keys = []
    for fname, path, kind, label in sources:
        doc = _dig(_load(fname, {}), path)
        if kind == "rows":
            grouped = {}
            for r in (doc or []):
                if isinstance(r, dict) and r.get("ticker"):
                    grouped.setdefault(str(r["ticker"]), []).append(r)
            entries = grouped
        else:
            entries = dict(doc or {})
        keys = set(entries)
        src_keys.append((label, fname, keys, entries))
        print(f"[gap]   원천 {label}({fname}) 보유 {len(keys)}종목", file=sys.stderr)
    probe_ok = any(f == "dart_fundamentals_kr.json" for f, _, _, _ in sources)

    missing = [(t, uni[t]) for t in uni
               if not (next((s for s in stocks if str(s.get("ticker")) == t), {}) or {}).get(field)]

    rows, probed = [], 0
    for tk, nm in missing:
        why = _normal_absence(nm, tk)
        if why:
            rows.append({"ticker": tk, "name": nm, "cause": "④정상부재", "detail": why})
            continue
        if not sources:
            rows.append({"ticker": tk, "name": nm, "cause": "미분류", "detail": "원천 매핑 미등록"})
            continue
        # 🚨 원천이 티커는 갖고 있으나 **값이 0/부재** = 정상 부재다(우리 결함 아님)
        vchk = VALUE_CHECK.get(field)
        if vchk and all(tk in keys for _l, _f, keys, _e in src_keys):
            if not any(vchk(entries.get(tk)) for _l, _f, _k, entries in src_keys):
                rows.append({"ticker": tk, "name": nm, "cause": "④정상부재",
                             "detail": "원천에 해당 값 없음(보유 자체가 없음)"})
                continue
        lack = [lbl for lbl, _f, keys, _e in src_keys if tk not in keys]
        if lack:
            # 필수 원천 중 하나라도 이 종목을 안 갖고 있다 = 그 원천이 물어본 적이 없다
            rows.append({"ticker": tk, "name": nm, "cause": "①유니버스누락",
                         "detail": "원천 미보유: " + "·".join(lack)})
            continue
        # 원천은 다 갖고 있는데 리포트 값이 비었다 → ②/③. DART 계열만 원천 조회로 갈 수 있다
        if probe_ok and probed < a.probe:
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
        elif not probe_ok:
            # 🚨 원천 조회 경로가 없는 필드는 ②/③ 을 가를 수 없다. ②로 떨어뜨리지 않는다 —
            #    '원천에 없다' 는 확인되지 않은 주장이 되고, 그러면 고칠 결손이 사라진다.
            rows.append({"ticker": tk, "name": nm, "cause": "③파싱실패",
                         "detail": "원천 보유 확인됨 · 리포트 값 빔(조립 단계 문제)"})
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

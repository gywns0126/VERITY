#!/usr/bin/env python3
"""대주주 판정 기준가 — 직전 사업연도 종료일 종가. 2026-08-22 신설.

## 왜

세금 탭이 대주주(양도세 과세 대상)를 **현재가 × 보유수** 로 판정하고 있었다.
법령은 다르다 — 소득세법 시행령 §157⑥:

  "주권상장법인의 주식등의 경우에는 주식등의 양도일이 속하는 사업연도의
   **직전사업연도 종료일 현재의 최종시세가액**. 다만, 직전사업연도 종료일 현재의
   최종시세가액이 없는 경우에는 **직전거래일의 최종시세가액**에 따른다"

즉 2026년 중 양도라면 기준은 **2025년 말 종가**다. 현재가로 재면 장이 오를 때
"아직 대주주가 아닌데 대주주로" 표시되고 내릴 때 반대가 된다 — 8개월 어긋난 값이다.

🚨 **개인 양도자의 '사업연도' = 과세기간 = 역년**이므로 종목 결산월과 무관하게 전 종목
   동일 기준일(직전 역년 말)이다. `kr_fiscal_month.json`(법인 결산월)을 여기 섞으면 안 된다 —
   그건 재무제표 분기 귀속용이지 양도세 판정용이 아니다.

🚨 **휴장 폴백이 조문에 명시돼 있다.** 실측: 2025-12-31 은 연말 폐장이라 거래가 없고
   마지막 거래일이 **2025-12-30** 이다. 조문 단서가 정확히 이 경우를 가리킨다 —
   "없으면 직전거래일". 그래서 `<= 기준일` 중 최댓값을 쓴다.

입력 = data/kr_chart_daily/chunk_*.json (일봉 250일, [yyyymmdd, o, h, l, c, v])
출력 = data/kr_prior_fy_close.json  {_meta{basis_date, requested_date, ...}, prices{ticker: close}}
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(_ROOT, "data", "kr_chart_daily")
OUT = os.path.join(_ROOT, "data", "kr_prior_fy_close.json")


def _now():
    return datetime.now(KST)


def basis_yyyymmdd(today=None) -> int:
    """판정 기준일 = 직전 역년 말(12-31). 개인 과세기간 기준이라 종목 결산월과 무관."""
    y = (today or _now()).year
    return int(f"{y - 1}1231")


def build(today=None) -> dict:
    want = basis_yyyymmdd(today)
    prices, fallback, missing = {}, 0, 0
    names = {}
    for f in sorted(glob.glob(os.path.join(SRC, "chunk_*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        for tk, v in (doc.get("stocks") or {}).items():
            candles = v.get("c") or []
            # 🚨 기준일 '이하' 중 최댓값 — 조문의 "없으면 직전거래일" 을 그대로 구현.
            #    == 로만 찾으면 연말 폐장(2025-12-31) 때 전 종목이 결손이 된다.
            best = None
            for row in candles:
                if not row or len(row) < 5:
                    continue
                d = int(row[0])
                if d <= want and (best is None or d > best[0]):
                    best = (d, row[4])
            if best is None:
                missing += 1
                continue
            if best[0] != want:
                fallback += 1
            c = float(best[1] or 0)
            if c > 0:
                prices[str(tk)] = c
                names[str(tk)] = v.get("n") or ""
    return {"prices": prices, "names": names, "requested": want,
            "fallback_used": fallback, "missing": missing}


def main() -> int:
    r = build()
    if not r["prices"]:
        # 🚨 0건 산출을 성공으로 끝내지 않는다 — 입력 부재·스키마 변경이 조용히 통과한다.
        print("[prior_fy] 종가 0건 — 입력 부재 또는 스키마 변경. exit 1", file=sys.stderr)
        return 1
    doc = {
        "_meta": {
            "generated_at": _now().isoformat(),
            "requested_date": r["requested"],
            "source": "kr_chart_daily (일봉 종가)",
            "rule": ("소득세법 시행령 §157⑥ — 양도일이 속하는 사업연도의 직전사업연도 종료일 "
                     "최종시세가액. 없으면 직전거래일."),
            "count": len(r["prices"]),
            "fallback_used": r["fallback_used"],
            "missing": r["missing"],
            "note": ("대주주 판정 **전용** 기준가. 손익·평가액 표시에는 쓰지 않는다(그건 현재가). "
                     "개인 과세기간=역년이라 종목 결산월과 무관하게 전 종목 동일 기준일."),
        },
        "prices": r["prices"],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    print(f"[prior_fy] {r['requested']} 기준 {len(r['prices']):,}종목 "
          f"(직전거래일 폴백 {r['fallback_used']:,} · 미보유 {r['missing']:,}) "
          f"-> {os.path.relpath(OUT, _ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

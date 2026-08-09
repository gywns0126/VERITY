# -*- coding: utf-8 -*-
"""kr_lynch_class_builder — KR 전 종목 Lynch 6분류 (사실 기반 규칙 분류).

🚨 왜 (PM 2026-08-09 "국장 소형주가 핵심인데 이따구면 안되지")
  `verity_lens`(= 컨센서스 위에 얹는 우리 관점, 토스·네이버·LLM 미보유)는 `rec["lynch_kr"]`
  하나에 의존하는데, 그게 `attach_classifications(portfolio)` 즉 **운영풀 20종에서만** 계산됐다.
  실측: 공개 리포트 1,155 소형주 중 verity_lens 보유 **4종(0.3%)**.

  분류에 필요한 입력은 이미 다 있었다 (코너 1,274 기준 실측):
      operating_margin 83.2% · revenue_growth 82.1% · sector/industry 81.1%
      roe 73.9% · pbr 73.5%(유도) · div_yield 53.9%
  → 데이터가 아니라 **계산 범위**가 문제였다. 전 종목으로 돌린다.

산식 무변경 (RULE 7)
  `api/intelligence/lynch_classifier.classify_lynch_kr` 를 **그대로** 호출한다.
  임계(FAST/STALWART/ASSET_PLAY/TURNAROUND)는 2026-05-23 PM 사전등록 A3 값이며 손대지 않는다.
  이 빌더가 하는 일은 입력 조달과 범위 확대뿐이다.

입력 조달 (전부 기존 발행물)
  · market_cap / close      krx_mktcap.map
  · revenue_growth          dart_kr_fin_history (연간 매출 2개년)
  · operating_margin        dart_kr_fin_history (영업이익/매출)
  · roe / total_assets      dart_fundamentals_kr
  · sector · industry       kr_sector_map     ← 🚨 두 필드를 **따로** 넘긴다.
                              합쳐서 sector 하나로 주면 GICS industry 매칭이 죽어
                              CYCLICAL 이 0건이 된다(2026-08-09 실측 자기 오류).
  · pbr                     유도 = 시총 ÷ 자본총계, 자본총계 = 총자산 ÷ (1 + 부채비율/100)
                              발행 PBR 은 `pbr_invalid_to_1.0` 로 중립화돼 정보가 0이라
                              그대로 쓰면 ASSET_PLAY 가 영영 안 뜬다.
  · div_yield               dividends_kr (DPS ÷ 종가). implausible 플래그 행은 제외.

출력: data/kr_lynch_class.json  {_meta, by_ticker: {ticker: {class,label,summary,color,
      reasons,data_quality,inputs_present}}}
🚨 공개 발행 목록(action.yml) 미등재 — 오퍼레이터 조인 전용. 공개 확대는 PM 결정 사항.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DATA = os.path.join(_ROOT, "data")
OUT = os.path.join(DATA, "kr_lynch_class.json")
KST = timezone(timedelta(hours=9))


def _load(name: str, default: Any = None) -> Any:
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _dps(rows) -> Optional[float]:
    for r in rows or []:
        if r.get("_meta") or r.get("implausible"):
            continue
        a = r.get("confirmed_amount_per_share") or r.get("announced_amount_per_share")
        if a:
            try:
                return float(a)
            except (TypeError, ValueError):
                continue
    return None


def build() -> Dict[str, Any]:
    from api.intelligence.lynch_classifier import classify_lynch_kr

    mk = (_load("krx_mktcap.json", {}) or {}).get("map") or {}
    fund = (_load("dart_fundamentals_kr.json", {}) or {}).get("fundamentals") or {}
    sec = (_load("kr_sector_map.json", {}) or {}).get("map") or {}
    dv = _load("dividends_kr.json", {}) or {}
    hist = (_load("dart_kr_fin_history.json", {}) or {}).get("rows") or []

    rev: Dict[str, Dict[int, float]] = defaultdict(dict)
    op: Dict[str, Dict[int, float]] = defaultdict(dict)
    for r in hist:
        t = r.get("ticker")
        f = r.get("fundamentals") or {}
        y = r.get("fiscal_year")
        if not t or y is None:
            continue
        if f.get("revenue") is not None:
            rev[t][y] = f["revenue"]
        if f.get("operating_profit") is not None:
            op[t][y] = f["operating_profit"]

    by: Dict[str, Any] = {}
    cls_count: Counter = Counter()
    low = 0
    for tk, m in mk.items():
        if not (isinstance(tk, str) and tk.isdigit() and len(tk) == 6):
            continue
        fu = fund.get(tk) or {}
        sm = sec.get(tk) or {}
        ys = sorted(rev[tk])
        y = ys[-1] if ys else None
        rg = None
        if len(ys) >= 2 and rev[tk].get(ys[-2]):
            try:
                rg = (rev[tk][ys[-1]] / rev[tk][ys[-2]] - 1) * 100
            except ZeroDivisionError:
                rg = None
        om = None
        if y and rev[tk].get(y) and op[tk].get(y) is not None:
            try:
                om = op[tk][y] / rev[tk][y] * 100
            except ZeroDivisionError:
                om = None
        pbr = None
        ta, dr = fu.get("total_assets"), fu.get("debt_ratio")
        if m.get("mktcap") and ta and dr is not None:
            eq = ta / (1 + dr / 100)
            if eq > 0:
                pbr = m["mktcap"] / eq
        d = _dps(dv.get(tk))
        dy = (d / m["close"] * 100) if (d and m.get("close")) else None

        stock = {
            "market_cap": m.get("mktcap"), "currency": "KRW",
            "revenue_growth": rg, "operating_margin": om,
            "roe": fu.get("roe"), "debt_ratio": dr,
            "sector": sm.get("sector_ko") or sm.get("sector"),
            "industry": sm.get("industry"),      # 🚨 sector 와 분리 필수 (GICS 매칭 경로)
            "pbr": pbr, "div_yield": dy,
        }
        try:
            res = classify_lynch_kr(stock)
        except Exception:  # noqa: BLE001 — 한 종목 실패가 전체를 막지 않는다
            continue
        present = [k for k in ("revenue_growth", "operating_margin", "roe", "pbr",
                               "div_yield", "sector", "industry") if stock.get(k) is not None]
        res["inputs_present"] = present
        by[tk] = res
        cls_count[res["class"]] += 1
        if res.get("data_quality") != "ok":
            low += 1

    return {
        "_meta": {
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "count": len(by),
            "ok_count": len(by) - low,
            "low_quality_count": low,
            "class_distribution": dict(cls_count.most_common()),
            "source": "lynch_classifier.classify_lynch_kr (임계 무변경, 2026-05-23 PM 사전등록 A3) "
                      "· 입력 = krx_mktcap · dart_kr_fin_history · dart_fundamentals_kr · "
                      "kr_sector_map · dividends_kr",
            "pbr_note": "PBR = 시총 ÷ (총자산 ÷ (1+부채비율/100)) 유도값. 발행 PBR 은 "
                        "pbr_invalid_to_1.0 중립화라 정보가 없어 그대로 쓰면 ASSET_PLAY 가 안 뜬다.",
            "disclaimer": "규칙 기반 사실 분류 — 자체 점수·등급·매매의견 아님 (RULE 7). "
                          "data_quality=low 는 핵심 입력 결측이라 통계에서 분리할 것.",
        },
        "by_ticker": by,
    }


def main() -> int:
    out = build()
    n = out["_meta"]["count"]
    if n == 0:
        # 🚨 0건인데 성공 종료 금지 ([[feedback_silent_total_failure_guard]])
        print("[kr_lynch_class] 🚨 분류 0건 — 입력 전부 결측. 실패 종료", file=sys.stderr)
        return 1
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, OUT)
    m = out["_meta"]
    print(f"[kr_lynch_class] {n}종 (ok {m['ok_count']} / low {m['low_quality_count']}) "
          f"· {m['class_distribution']} → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

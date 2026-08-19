"""macro_multiplier 일별 시계열 원장 — 거시 사전등록 §3 단계 1 (PM 승인 2026-08-19).

## 왜 필요한가

`macro_multiplier` 는 전 종목 사이징을 곱하는 **유일한 거시→결정 경로**인데
(`verity_brain` → `vams/engine.py:941`), **시계열 기록이 없었다**(2경로 확인:
파일 grep + jsonl 본문 스캔). `recommendations.json` 은 스냅샷이라 "어제 얼마였나" 를
답하지 못한다. 그래서 H1(타이밍)·H2(선택) 어느 것도 검정을 시작할 수 없었다.

## 🚨 무엇을 기록하나 — 평균이 아니라 **횡단면 분산**이 핵심이다

Q8 ④(Kelly·Xiu 2023 NBER WP 31502 survey)는 "신호가 횡단면 분산을 잃으면 가중치가
0으로 수렴하는 것이 표준" 이라고 답했다. 그 진단을 하려면 **매일의 cross-sectional
표준편차**가 있어야 한다. 2026-08-19 실측에서 `cape_penalty`·`yield_penalty` 는
고유값이 각각 1개뿐이었다(std=0) — 그게 관측 가능한 형태로 남아야 한다.

같이 기록하는 것:
  · 승수·페널티 4종의 mean/std/min/max  (std=0 이면 그 축은 그날 차등 기여 0)
  · 🚨 `saturated_frac` = 각 페널티가 **상한에 붙은 종목 비율** (포화 직접 관측)
  · 입력 원값 (cape·cape_pct·us_10y·us_10y_pct·usdkrw) — 재현 가능성

## 소급

`data/history/YYYY-MM-DD.json` 각 파일이 그날의 `recommendations` 를 통째로 갖고 있고,
거기에 `macro_multiplier` 가 종목별로 들어 있다(2026-08-19 확인, 118파일).
따라서 **원장을 과거로 재구성할 수 있다** — 새 수집이 아니라 이미 가진 것의 재집계다.

🚨 RULE 4 — 산출 `data/metadata/macro_multiplier_trail.jsonl` 은 신규 파일이다.
이 빌더를 cron 에 올릴 때 해당 워크플로의 `git add` 에 경로를 명시하는 것이 선행 조건.
지금은 **수동 실행 + 수동 커밋** 전용이다.
"""
from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(_ROOT, "data")
HISTORY_GLOB = os.path.join(DATA, "history", "20??-??-??.json")
LIVE = os.path.join(DATA, "recommendations.json")
OUTPUT_PATH = os.path.join(DATA, "metadata", "macro_multiplier_trail.jsonl")

PENALTIES = ("valuation_penalty", "currency_penalty", "cape_penalty", "yield_penalty")
# 각 축의 설계 상한 (verity_brain 기준). 포화 관측용 — 임계 판정에 쓰지 않는다.
CAPS = {"cape_penalty": 0.10, "yield_penalty": 0.10, "currency_penalty": 0.075}


def _stats(vals: List[float]) -> Dict[str, Any]:
    if not vals:
        return {"n": 0}
    a = np.asarray(vals, dtype=float)
    return {
        "n": int(a.size),
        "mean": round(float(a.mean()), 5),
        "std": round(float(a.std(ddof=0)), 5),   # 🚨 횡단면 분산 — Q8 ④ 진단의 핵심
        "min": round(float(a.min()), 5),
        "max": round(float(a.max()), 5),
        "uniq": int(np.unique(np.round(a, 6)).size),
    }


def summarize(recs: List[Dict[str, Any]], date: str) -> Optional[Dict[str, Any]]:
    """하루치 recommendations → 원장 1행. macro_multiplier 보유 0 이면 None."""
    mms = [r["macro_multiplier"] for r in recs
           if isinstance(r, dict) and isinstance(r.get("macro_multiplier"), dict)]
    mult = [m["multiplier"] for m in mms
            if isinstance(m.get("multiplier"), (int, float))]
    if not mult:
        return None

    row: Dict[str, Any] = {
        "date": date,
        "n_stocks": len(recs),
        "n_with_multiplier": len(mult),
        "multiplier": _stats(mult),
        "penalties": {},
        "saturated_frac": {},
        "inputs": {},
    }
    for p in PENALTIES:
        vals = [float(m.get(p) or 0.0) for m in mms]
        row["penalties"][p] = _stats(vals)
        cap = CAPS.get(p)
        if cap is not None and vals:
            row["saturated_frac"][p] = round(
                sum(1 for v in vals if v >= cap - 1e-9) / len(vals), 4)

    # 입력 원값 — 종목마다 같아야 정상. 다르면 최빈값을 싣고 불일치를 신고한다.
    inp_keys = ("cape_pct", "us_10y", "us_10y_percentile", "usdkrw", "pbr")
    for k in inp_keys:
        seen = [m.get("inputs", {}).get(k) for m in mms
                if isinstance(m.get("inputs"), dict) and m["inputs"].get(k) is not None]
        if not seen:
            continue
        uniq = sorted({round(float(x), 6) for x in seen if isinstance(x, (int, float))})
        if k == "pbr":          # pbr 은 종목별이 정상 — 통계로 싣는다
            row["inputs"]["pbr"] = _stats([float(x) for x in seen])
            continue
        row["inputs"][k] = uniq[0] if len(uniq) == 1 else {"values": uniq[:5],
                                                           "inconsistent": True}
    ver = {m.get("version") for m in mms if m.get("version")}
    if ver:
        row["version"] = sorted(ver)[0] if len(ver) == 1 else sorted(ver)
    return row


def _date_from_path(path: str) -> Optional[str]:
    m = re.search(r"(\d{4}-\d{2}-\d{2})\.json$", path)
    return m.group(1) if m else None


def build(include_live: bool = True) -> List[Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for f in sorted(glob.glob(HISTORY_GLOB)):
        d = _date_from_path(f)
        if not d:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        recs = doc.get("recommendations")
        if not isinstance(recs, list):
            continue
        r = summarize(recs, d)
        if r:
            r["source"] = "history"
            rows[d] = r

    if include_live and os.path.exists(LIVE):
        try:
            with open(LIVE, encoding="utf-8") as fh:
                recs = json.load(fh)
        except (OSError, ValueError):
            recs = None
        if isinstance(recs, list):
            # 라이브는 날짜가 없다 — history 최신일 다음날로 두지 않고,
            # 오늘(KST)로 기록하되 history 에 같은 날이 있으면 덮지 않는다(소급 우선).
            from api.utils.market_calendar import now_kst
            today = now_kst().strftime("%Y-%m-%d")
            if today not in rows:
                r = summarize(recs, today)
                if r:
                    r["source"] = "live"
                    rows[today] = r
    return [rows[k] for k in sorted(rows)]


def main() -> None:
    rows = build()
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, OUTPUT_PATH)

    if not rows:
        print("[macro_mult_trail] 행 0 — 입력에 macro_multiplier 가 없다")
        return
    print(f"[macro_mult_trail] {len(rows)}행 · {rows[0]['date']} ~ {rows[-1]['date']}"
          f" → {OUTPUT_PATH}")
    m = [r["multiplier"]["mean"] for r in rows]
    print(f"  승수 평균의 범위 {min(m):.3f} ~ {max(m):.3f} (전 기간 평균 {sum(m)/len(m):.3f})")
    print("\n  🚨 횡단면 표준편차 = 0 인 날 비율 (그 축은 그날 차등 기여 0):")
    for p in PENALTIES:
        z = sum(1 for r in rows if (r["penalties"].get(p) or {}).get("std", 0) == 0)
        sat = [r["saturated_frac"].get(p) for r in rows if p in r.get("saturated_frac", {})]
        extra = f" · 상한 도달 비율 평균 {sum(sat)/len(sat)*100:.1f}%" if sat else ""
        print(f"    {p:<20} {z}/{len(rows)} ({z/len(rows)*100:.0f}%){extra}")


if __name__ == "__main__":
    main()

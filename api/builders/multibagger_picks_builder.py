#!/usr/bin/env python3
"""멀티배거 선별 종목 리스트 — PM 지시 2026-08-22 ("따로 리스트로 만들어줘").

🚨 왜 별 리스트인가:
  멀티배거로 유니버스에 들어온 종목이 **일반 후보와 섞이면 이 결정의 성적을 영영
  분리할 수 없다.** 사전등록(PREREG_MULTIBAGGER_UPSIDE_FUNNEL_2026_08_22 §3-2)이
  `promoted_by` 태그를 필수로 건 이유가 이것이고, 이 빌더가 그 태그를 실제로 쓴다.

세 갈래로 나눠 낸다 — 섞으면 "몇 개가 살아남았나" 를 못 센다:
  · **scored**  — 승격돼 **채점까지 간** 종목 (brain_score·grade 포함)
  · **promoted** — 승격됐으나 아직 채점 전 (스캔 직후 ~ 분석 전 구간)
  · **watching** — alert≥2 인데 상한(CAP)에 밀려 승격 안 된 종목

입력 = multibagger_watch.jsonl(신호) + multibagger_promote.json(승격) + portfolio.json(채점).
🚨 오퍼레이터 전용 — 공개 사이트·발행 파일에 싣지 않는다(유사투자자문 회피).
"""
from __future__ import annotations

import collections
import json
import os
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WATCH = os.path.join(ROOT, "data", "metadata", "multibagger_watch.jsonl")
PROMOTE = os.path.join(ROOT, "data", "metadata", "multibagger_promote.json")
PORTFOLIO = os.path.join(ROOT, "data", "portfolio.json")
OUT = os.path.join(ROOT, "data", "multibagger_picks.json")

MIN_ALERT = 2


def _load_json(p: str, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _latest_watch() -> tuple:
    rows: List[Dict[str, Any]] = []
    try:
        with open(WATCH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return "", []
    if not rows:
        return "", []
    latest = max(r.get("watch_date") or "" for r in rows)
    return latest, [r for r in rows if r.get("watch_date") == latest]


def _fired(r: Dict[str, Any]) -> List[str]:
    return sorted(k for k, v in (r.get("signals") or {}).items()
                  if isinstance(v, dict) and v.get("triggered"))


def build() -> Dict[str, Any]:
    watch_date, rows = _latest_watch()
    eligible = [r for r in rows if int(r.get("alert_count") or 0) >= MIN_ALERT]
    eligible.sort(key=lambda r: -int(r.get("alert_count") or 0))

    promo = _load_json(PROMOTE, {}) or {}
    promoted_t = {c.get("ticker") for c in (promo.get("candidates") or [])
                  if isinstance(c, dict)}

    pf = _load_json(PORTFOLIO, {}) or {}
    scored_by_t: Dict[str, Dict[str, Any]] = {}
    for r in (pf.get("recommendations") or []):
        if not isinstance(r, dict):
            continue
        # 🚨 태그가 있는 것만 = 이 결정으로 들어온 종목. 우연히 겹친 일반 후보는 제외한다
        if (r.get("promoted_by") or {}).get("source") == "multibagger":
            scored_by_t[r.get("ticker")] = r

    def _row(r: Dict[str, Any], scored: Dict[str, Any] | None = None) -> Dict[str, Any]:
        vb = (scored or {}).get("verity_brain") or {}
        return {
            "ticker": r.get("ticker"),
            "name": r.get("name"),
            "sector": r.get("sector"),
            "market_cap": r.get("market_cap"),
            "lynch_class": r.get("lynch_class"),
            "alert_count": r.get("alert_count"),
            "fired": _fired(r),
            # 채점 전이면 None — 🚨 0 으로 채우지 않는다(결측과 실측은 다르다)
            "brain_score": vb.get("brain_score"),
            "grade": vb.get("grade"),
            "price": (scored or {}).get("price"),
        }

    scored, promoted, watching = [], [], []
    for r in eligible:
        t = r.get("ticker")
        if t in scored_by_t:
            scored.append(_row(r, scored_by_t[t]))
        elif t in promoted_t:
            promoted.append(_row(r))
        else:
            watching.append(_row(r))

    gdist = collections.Counter(x["grade"] for x in scored if x.get("grade"))
    return {
        "_meta": {
            # 🚨 분모 먼저 (RULE 13) — 몇 개 중 몇 개가 살아남았는지 없이 목록만 보면
            #   전수처럼 읽힌다
            "watch_date": watch_date,
            "watch_n": len(rows),
            "min_alert": MIN_ALERT,
            "eligible_n": len(eligible),
            "promoted_n": len(promoted_t),
            "scored_n": len(scored),
            "waiting_n": len(promoted),
            "capped_out_n": len(watching),
            "grade_dist": dict(gdist),
            "promote_meta": {k: promo.get(k) for k in ("as_of", "cap", "dropped_no_full_record")},
            "decision_use": False,
            "note": ("멀티배거로 유니버스에 들어온 종목만 분리한 리스트. "
                     "🚨 관측 — 매수 지시가 아니다. 채점은 일반 후보와 동일한 게이트를 받는다. "
                     "capped_out = 신호는 켜졌으나 상한(cap)에 밀린 종목."),
            "operator_only": True,
        },
        "scored": scored,
        "promoted": promoted,
        "watching": watching,
    }


def main() -> int:
    d = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    m = d["_meta"]
    print(f"[multibagger_picks] {OUT} · {os.path.getsize(OUT):,}B")
    print(f"  {m['watch_date']} · 워치 {m['watch_n']} → alert≥{m['min_alert']} {m['eligible_n']} "
          f"→ 승격 {m['promoted_n']} → 채점 {m['scored_n']}")
    print(f"  등급 분포: {m['grade_dist'] or '(아직 채점 전)'}")
    print(f"  대기 {m['waiting_n']} · 상한에 밀림 {m['capped_out_n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""KR 소형주 외국인 순매수 급증 관측 — 도착한 신호를 표면화한다.

🚨 왜 만들었나 (2026-08-09, 제이엠티 094970 사례)
  PM: "외국인 매수를 빠르게 못 잡아서 급등을 바로 못 알아차린 종목."
  그런데 실제로 추적해 보니 **데이터는 늦지 않았다.** 08-03 급등 당일 외국인 +104,642주가
  같은 날 21:44 KST 에 이미 수집돼 있었다(장 마감 6시간 14분 뒤, 커밋 92e27cac0).
  회전 수집에서도 안 밀렸다 — 08-03~08-07 5일 연속 잡혔다.

  즉 갭은 수집 신선도가 아니라 **표면화**였다. 신호가 파일 안에 있었는데 아무도 안 봤다.
  (장중 수급은 원천 불가 — 네이버 일별 외국인·기관 순매매는 장 마감 후 확정치다.
   장중 실시간 수급은 KRX 회원사 유료 피드 영역이라 주기를 당겨도 안 나온다.)

🚨 임계는 전부 **기존 상수 재사용**이다. 새로 만든 숫자가 0개인 게 설계 의도다 —
  이 종목에 맞춰 숫자를 고르면 곡선 맞추기다.
    · flow_x 3.0   ← us_demand_chain 의 vol_ratio 3.0 (같은 "평소의 3배" 의미)
    · move_pct 7.0 ← us_demand_chain 의 move_pct 7.0 그대로
    · 시총 300~3000억 ← smallcap_corner_builder 의 MKTCAP_MIN/MAX 그대로
  🚨 사전등록 없이 조정 금지([[feedback_methodology_pre_registration]]).

발생 빈도 실측(2026-08-09, 5거래일 · 소형주 1,186): 외국인 급증만 358건 → 이중 게이트 41건
  ≈ 8건/일. 단일 게이트(29.5% 종목)는 알림으로 쓸 수 없어 두 번째 조건을 넣었다.

관측 only (RULE 7) — 점수·순위·추천 0. brain_input=false.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from api.config import now_kst  # noqa: E402

FLOW_PATH = os.path.join(_ROOT, "data", "stock_flow_5d.json")
MKTCAP_PATH = os.path.join(_ROOT, "data", "krx_mktcap.json")
OUT_PATH = os.path.join(_ROOT, "data", "observations", "kr_flow_spike.jsonl")

_EOK = 100_000_000
MKTCAP_MIN = 300 * _EOK      # smallcap_corner_builder 와 동일 — dead/shell 차단
MKTCAP_MAX = 3000 * _EOK     # 동일 — 대형(타사 커버) 제외
FLOW_X = 3.0                 # us_demand_chain vol_ratio 재사용
MOVE_PCT = 7.0               # us_demand_chain move_pct 재사용

CAVEAT = (
    "관측-only 가설. 점수 미반영(brain_input=false). 외국인 순매수 급증과 주가 상승의 "
    "동시 발생을 사실로 병기할 뿐 인과 단정이 아니다. 소스는 장 마감 후 확정치라 "
    "장중 신호가 아니다. 임계(3.0x/7.0%)=기존 상수 재사용·이론 고정, 사전등록 없이 조정 금지."
)


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def detect(flows: Dict[str, Any], mktcap: Dict[str, Any]) -> List[Dict[str, Any]]:
    """이중 게이트 통과 건만 돌려준다. 정렬은 날짜순 — 순위·점수 없음(RULE 7)."""
    out: List[Dict[str, Any]] = []
    for tk, rows in (flows or {}).items():
        if not isinstance(rows, list) or len(rows) < 3:
            continue
        mc = (mktcap.get(tk) or {}).get("mktcap")
        if mc is None or not (MKTCAP_MIN <= mc < MKTCAP_MAX):
            continue
        for i, r in enumerate(rows):
            fn = r.get("foreign_net")
            if not isinstance(fn, (int, float)):
                continue
            others = [abs(x.get("foreign_net") or 0) for j, x in enumerate(rows) if j != i]
            base = sum(others) / len(others) if others else 0.0
            if base <= 0 or fn / base < FLOW_X:
                continue
            if i == 0:
                continue  # 전일 종가 없음 — 창의 첫 행. 실운영의 최신일에는 항상 전일이 있다
            prev_close = rows[i - 1].get("close")
            close = r.get("close")
            if not prev_close or not close:
                continue
            move = (close - prev_close) / prev_close * 100.0
            if move < MOVE_PCT:
                continue
            out.append({
                "ticker": tk,
                "date": r.get("date"),
                "foreign_net": int(fn),
                "flow_x": round(fn / base, 2),
                "move_pct": round(move, 1),
                "close": close,
                "mktcap_eok": round(mc / _EOK),
                "inst_net": int(r.get("inst_net") or 0),
            })
    out.sort(key=lambda x: (str(x["date"]), x["ticker"]))
    return out


def main() -> int:
    try:
        flows = (_load(FLOW_PATH) or {}).get("flows") or {}
        mktcap = (_load(MKTCAP_PATH) or {}).get("map") or {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"[kr_flow_spike] 입력 로드 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    # 🚨 전량 실패 가드 (#46). 입력이 비었는데 정상 종료하면 "이벤트 0건" 과 구분되지 않고,
    #   산출 mtime 만 갱신되어 신선도 보드가 통과시킨다.
    if not flows or not mktcap:
        print(f"[kr_flow_spike] outcome=total_fail flows={len(flows)} mktcap={len(mktcap)}"
              " — 입력 부재. 산출 미갱신·실패 종료", file=sys.stderr)
        return 1

    events = detect(flows, mktcap)
    universe = sum(1 for tk in flows
                   if (mktcap.get(tk) or {}).get("mktcap") is not None
                   and MKTCAP_MIN <= mktcap[tk]["mktcap"] < MKTCAP_MAX)

    rec = {
        "ts_kst": now_kst().isoformat(timespec="seconds"),
        "shadow": True,
        "brain_input": False,
        "caveat": CAVEAT,
        "thresholds": {"flow_x": FLOW_X, "move_pct": MOVE_PCT,
                       "mktcap_min_eok": MKTCAP_MIN // _EOK,
                       "mktcap_max_eok": MKTCAP_MAX // _EOK},
        "coverage": {"flows": len(flows), "smallcap_universe": universe},
        "count": len(events),
        "events": events,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[kr_flow_spike] 소형주 {universe} 중 {len(events)}건 관측 → {OUT_PATH}")
    for e in events[-10:]:
        print(f"  {e['date']} {e['ticker']} 외국인 {e['foreign_net']:+,} "
              f"({e['flow_x']}x) · 등락 {e['move_pct']:+.1f}% · 시총 {e['mktcap_eok']}억")
    return 0


if __name__ == "__main__":
    sys.exit(main())

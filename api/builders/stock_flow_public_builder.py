"""stock_flow_public_builder — 공개 터미널 종목 수급(외국인·기관 일별 순매매) public-safe 빌더.

2026-06-19 신설. 🔴 데이터 복구 리서치(workflow whxa2vt29) 결론 적용:
  · 프로덕션 api/collectors/market_flow.py 정규식(class="num")은 네이버 frgn 구조 변경으로 死
    (production flow 전부 0) → 그 fix 는 trade_planner 결정 파이프라인 변경이라 별도 PM 의제.
  · 검증된 파서 = scripts/kr/flow_observation_logger.fetch_flow_panel (class="tah"+euc-kr,
    실호출 검증). 이 빌더는 그 파서를 *재사용*만 — 결정 파이프라인 영향 0 (공개 표시 전용).

대상 유니버스 = recommendations.json 의 KR 6자리 티커(소수, ~25) — anti-bot 안전(×0.4s).
  · liquid_universe(duckdb 레이크)는 CI 부재 → recommendations 만 사용.

🚨 RULE 7 — 외국인/기관 일별 순매매량(주) = 외부 시장 *사실*(네이버 frgn). 자체 점수·flow_score
  비노출. forward 누적만(historical 백필 불가). 일 1회 한정(anti-bot).
publish: data/stock_flow_5d.json (action.yml 등재 필요). 네트워크 호출 — daily 에서 실행.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RECO_PATH = os.path.join(_ROOT, "data", "recommendations.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "stock_flow_5d.json")
N_DAYS = 5
DELAY = 0.4


def _now_kst() -> datetime:
    return datetime.now(KST)


def _load_parser():
    """scripts/kr/flow_observation_logger.fetch_flow_panel 를 파일 경로로 로드(패키지 불요)."""
    path = os.path.join(_ROOT, "scripts", "kr", "flow_observation_logger.py")
    spec = importlib.util.spec_from_file_location("flow_observation_logger", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.fetch_flow_panel


def _kr_tickers() -> List[str]:
    try:
        with open(RECO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    items = data if isinstance(data, list) else (data.get("recommendations") or data.get("stocks") or [])
    out: List[str] = []
    for it in items:
        tk = str(it.get("ticker") or it.get("code") or "").strip()
        if tk.isdigit() and len(tk) == 6 and tk not in out:
            out.append(tk)
    return out


def main() -> int:
    ok = False
    try:
        import requests

        tickers = _kr_tickers()
        if not tickers:
            print("[stock_flow_public] KR 티커 0 — skip", file=sys.stderr)
            return 0
        fetch_flow_panel = _load_parser()

        sess = requests.Session()
        flows: Dict[str, List[Dict[str, Any]]] = {}
        n_ok, n_fail = 0, 0
        for tk in tickers:
            try:
                panel = fetch_flow_panel(tk, sess) or []
            except Exception as e:  # noqa: BLE001
                n_fail += 1
                print(f"[stock_flow_public] {tk} 실패: {e!r}", file=sys.stderr)
                time.sleep(DELAY)
                continue
            # 최신순 정렬 후 N_DAYS — 사실 필드만(외국인·기관 순매매·종가)
            panel_sorted = sorted(panel, key=lambda r: str(r.get("date") or ""), reverse=True)
            rows = []
            for r in panel_sorted[:N_DAYS]:
                if r.get("foreign_net") is None and r.get("inst_net") is None:
                    continue
                rows.append({
                    "date": r.get("date"),
                    "foreign_net": r.get("foreign_net"),
                    "inst_net": r.get("inst_net"),
                    "close": r.get("close"),
                })
            if rows:
                rows.reverse()  # 오래된→최신 (막대 좌→우)
                flows[tk] = rows
                n_ok += 1
            else:
                n_fail += 1
            time.sleep(DELAY)

        if not flows and os.path.isfile(OUTPUT_PATH):
            print("[stock_flow_public] 0 flows — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "네이버 금융 frgn (외국인·기관 일별 순매매량, 주)",
                "universe": "recommendations KR",
                "count": len(flows),
                "days": N_DAYS,
                "note": "외부 시장 사실(순매매량)만 — 자체 flow_score·점수 비노출 (RULE 7). forward 누적.",
            },
            "flows": flows,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[stock_flow_public] logged=True · {n_ok} 종목 flow · {n_fail} 실패 -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[stock_flow_public] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[stock_flow_public] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

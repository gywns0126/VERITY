"""kr_observation_logger — KR 종목 cross-section 관측 신호 raw 적재 (v0, RULE 7 관측 only).

2026-06-21 신설. audit(2026-06-21) 결과 공개 터미널용으로 전종목 수집된 4개 신호(내부자·수급·희석이력·
총수일가 지분)를 엔진(brain score / observation trail) 어디서도 미사용 확인 — 엔진 insider=Finnhub(US),
flow=market_flow(별개), ownership=DART major_shareholders(FTC cross-check만), forensics=red_flags 미wire.

🚨 v0 = **점수·방향·조합식 0, raw 시점-페어 적재만** (crowding_observation_spec_v0 패턴). N≥252(2027) forward
   IC 검증용 trail 을 *지금부터* 누적 시작. v1(방향 환산 + 점수 사전등록) = Perplexity 방법론 + PM 승인 후
   한 번에 하나씩. brain score·decision 무간섭(가중 0). RULE 7 정합.

입력(공개 빌더 산출, 이미 일별 생성): insider_trades.json / stock_flow_5d.json / disclosure_forensics.json /
   stock_report_public.json(ownership.family_pct). commodity_exposure 제외(산업 멤버십=정적, 종목 시변 신호 아님).
출력: data/observations/kr_cross_section_observations.jsonl (주 1회 Fri, date-dedupe, append-only).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INSIDER_PATH = os.path.join(_ROOT, "data", "insider_trades.json")
FLOW_PATH = os.path.join(_ROOT, "data", "stock_flow_5d.json")
FORENSICS_PATH = os.path.join(_ROOT, "data", "disclosure_forensics.json")
REPORT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
OUT_DIR = os.path.join(_ROOT, "data", "observations")
OUT_PATH = os.path.join(OUT_DIR, "kr_cross_section_observations.jsonl")
DILUTIVE = ["유상증자", "전환사채(CB)", "신주인수권부사채(BW)"]


def _now_kst() -> datetime:
    return datetime.now(KST)


def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _already_logged(date_str: str) -> bool:
    """date-dedupe — 같은 날짜 entry 가 이미 있으면 재적재 skip (idempotent)."""
    if not os.path.exists(OUT_PATH):
        return False
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if f'"date": "{date_str}"' in line or f'"date":"{date_str}"' in line:
                    return True
    except OSError:
        pass
    return False


def main() -> int:
    ok = False
    try:
        now = _now_kst()
        # 주 1회(금요일)만 적재 — 신호가 느린 이벤트(공시)라 주간 스냅샷 충분 + trail 비대 회피.
        # daily cron 에 배선해도 금요일 외엔 self-skip (crowding 주간 cron 패턴 정합).
        if now.weekday() != 4 and os.environ.get("KR_OBS_FORCE") != "1":
            print(f"[kr_obs] 금요일 아님(weekday={now.weekday()}) — skip (주간 적재)", file=sys.stderr)
            return 0
        date_str = now.date().strftime("%Y-%m-%d")
        if _already_logged(date_str):
            print(f"[kr_obs] {date_str} 이미 적재됨 — skip (date-dedupe)", file=sys.stderr)
            ok = True
            return 0

        # 입력 4종 → ticker 인덱스
        insider = {str(s.get("ticker")): s for s in (_load_json(INSIDER_PATH, {}).get("stocks") or [])}
        flow = (_load_json(FLOW_PATH, {}).get("flows") or {})
        forensics = {str(s.get("ticker")): s for s in (_load_json(FORENSICS_PATH, {}).get("stocks") or [])}
        report = {str(s.get("ticker")): s for s in (_load_json(REPORT_PATH, {}).get("stocks") or [])}

        # 신호 보유 종목 합집합
        tickers = set(insider) | set(flow) | set(forensics)
        for tk, s in report.items():
            if (s.get("ownership") or {}).get("family_pct") is not None:
                tickers.add(tk)
        if not tickers:
            print("[kr_obs] 신호 보유 종목 0 — skip", file=sys.stderr)
            return 0

        def _dil(tk: str) -> int:
            c = (forensics.get(tk) or {}).get("counts") or {}
            return sum(int(c.get(k) or 0) for k in DILUTIVE)

        def _flow_last(tk: str):
            rows = flow.get(tk) or []
            return rows[-1] if rows else {}

        rows: List[Dict[str, Any]] = []
        for tk in sorted(tickers):
            ins = insider.get(tk) or {}
            fl = _flow_last(tk)
            own = (report.get(tk) or {}).get("ownership") or {}
            rows.append({
                "date": date_str,
                "ticker": tk,
                # 내부자(DART elestock) — net 증감(주), 매수/매도 건수
                "insider_net": ins.get("net_change"),
                "insider_buy_n": ins.get("buy_n"),
                "insider_sell_n": ins.get("sell_n"),
                # 수급(네이버) — 최근일 외국인/기관 순매매(주)
                "foreign_net": fl.get("foreign_net"),
                "inst_net": fl.get("inst_net"),
                # 희석이력(DART) — 유증/CB/BW 누적 빈도
                "dilution_count": _dil(tk),
                # 지배구조(공정위) — 총수일가 지배지분 %
                "family_pct": own.get("family_pct"),
            })

        os.makedirs(OUT_DIR, exist_ok=True)
        with open(OUT_PATH, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[kr_obs] logged=True · {date_str} · {len(rows)}종목 적재 (관측 only, 점수 0) -> "
              f"{os.path.relpath(OUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[kr_obs] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[kr_obs] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

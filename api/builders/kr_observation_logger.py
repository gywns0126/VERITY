"""kr_observation_logger — KR 종목 cross-section 관측 신호 raw 적재 (v0, RULE 7 관측 only).

2026-06-21 신설. audit(2026-06-21) 결과 공개 터미널용으로 전종목 수집된 4개 신호(내부자·수급·희석이력·
총수일가 지분)를 엔진(brain score / observation trail) 어디서도 미사용 확인 — 엔진 insider=Finnhub(US),
flow=market_flow(별개), ownership=DART major_shareholders(FTC cross-check만), forensics=red_flags 미wire.

🚨 v0 = **점수·방향·조합식 0, raw 시점-페어 적재만** (crowding_observation_spec_v0 패턴). 검증 게이트 forward
   IC 검증용 trail 을 *지금부터* 누적 시작. v1(방향 환산 + 점수 사전등록) = Perplexity 방법론 + PM 승인 후
   한 번에 하나씩. brain score·decision 무간섭(가중 0). RULE 7 정합.

입력(공개 빌더 산출, 이미 일별 생성): insider_trades.json / stock_flow_5d.json / disclosure_forensics.json /
   stock_report_public.json(ownership.family_pct). commodity_exposure 제외(산업 멤버십=정적, 종목 시변 신호 아님).
출력: data/observations/kr_cross_section_observations.jsonl (주 1회 Fri, date-dedupe, append-only).

🚨 2026-08-20 두 건 추가:
① insider_net_365d/buy/sell 병기 — 기존 insider_net 은 elestock 전 기간 누적이라 종목별로
   사실상 상수다(000660 8주 실측 104,361 → 106,615, 변동 2.2%). 그대로 252주를 모으면
   '최근 내부자 매수'가 아니라 '누적 보유 수준'의 IC 를 재게 된다. 기존 컬럼은 trail 연속성
   때문에 그대로 두고 창 컬럼을 나란히 시작한다(창 정의 변경 = 앞뒤가 섞임, RULE 13 ⑤).
② 입력 신선도 자기신고 — 이 step 은 같은 run 의 빌더 4종 산출을 읽는다. 분석이 죽어 그
   빌더가 skip 되면 '어제 값'이 '오늘 date'로 적재된다(as-of 거짓 = forward IC trail 오염).
   → _meta.generated_at 이 오늘이 아닌 입력은 컬럼을 null 로 적고 stale_inputs 로 신고한다.
   실측 사고: 2026-08-14(금) daily_analysis_full 3연속 실패 → 그 주 관측 행 영구 결손.
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


def _asof(doc) -> str:
    """입력 산출물의 _meta.generated_at → 'YYYY-MM-DD'. 부재 시 '' (= stale 취급)."""
    try:
        return str(((doc or {}).get("_meta") or {}).get("generated_at") or "")[:10]
    except AttributeError:
        return ""


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

        # 입력 4종 로드 + 신선도 자기신고(docstring ② 참조)
        docs = {
            "insider": _load_json(INSIDER_PATH, {}),
            "flow": _load_json(FLOW_PATH, {}),
            "forensics": _load_json(FORENSICS_PATH, {}),
            "report": _load_json(REPORT_PATH, {}),
        }
        stale = sorted(n for n, d in docs.items() if _asof(d) != date_str)
        if len(stale) == len(docs):
            # 전부 어제 것 = 이 run 에서 빌더가 하나도 안 돌았다. 빈 행을 남기는 대신 skip
            #   (같은 날 뒤 run 이 date-dedupe 에 막히지 않고 제대로 적재하도록).
            print(f"[kr_obs] 입력 4종 전부 stale(asof != {date_str}) — 적재 skip", file=sys.stderr)
            return 0
        if stale:
            print(f"[kr_obs] stale 입력 {stale} — 해당 컬럼 null 적재(as-of 거짓 방지)", file=sys.stderr)

        def _ok(name: str):
            return name not in stale

        insider = {str(s.get("ticker")): s for s in (docs["insider"].get("stocks") or [])}
        flow = (docs["flow"].get("flows") or {})
        forensics = {str(s.get("ticker")): s for s in (docs["forensics"].get("stocks") or [])}
        report = {str(s.get("ticker")): s for s in (docs["report"].get("stocks") or [])}

        # 신호 보유 종목 합집합 — stale 소스는 union 에서 제외(전 컬럼 null 인 유령 행 방지)
        tickers = set()
        if _ok("insider"):
            tickers |= set(insider)
        if _ok("flow"):
            tickers |= set(flow)
        if _ok("forensics"):
            tickers |= set(forensics)
        if _ok("report"):
            for tk, s in report.items():
                if (s.get("ownership") or {}).get("family_pct") is not None:
                    tickers.add(tk)
        if not tickers:
            print("[kr_obs] 신호 보유 종목 0 — skip", file=sys.stderr)
            return 0

        def _dil(tk: str):
            if not _ok("forensics"):
                return None
            c = (forensics.get(tk) or {}).get("counts") or {}
            return sum(int(c.get(k) or 0) for k in DILUTIVE)

        def _flow_last(tk: str):
            if not _ok("flow"):
                return {}
            rows = flow.get(tk) or []
            return rows[-1] if rows else {}

        ins_ok = _ok("insider")
        rows: List[Dict[str, Any]] = []
        for tk in sorted(tickers):
            ins = insider.get(tk) or {}
            fl = _flow_last(tk)
            own = (report.get(tk) or {}).get("ownership") or {} if _ok("report") else {}
            row = {
                "date": date_str,
                "ticker": tk,
                # 내부자(DART elestock) — 전 기간 누적 net 증감(주), 매수/매도 건수.
                #   🚨 창 아님. 2026-06-21~ trail 연속성 때문에 정의 유지.
                "insider_net": ins.get("net_change") if ins_ok else None,
                "insider_buy_n": ins.get("buy_n") if ins_ok else None,
                "insider_sell_n": ins.get("sell_n") if ins_ok else None,
                # 내부자 최근 365일 창 — 2026-08-20 신설(이 날짜 이전 행은 키 자체가 없음).
                "insider_net_365d": ins.get("net_change_365d") if ins_ok else None,
                "insider_buy_n_365d": ins.get("buy_n_365d") if ins_ok else None,
                "insider_sell_n_365d": ins.get("sell_n_365d") if ins_ok else None,
                # 수급(네이버) — 최근일 외국인/기관 순매매(주)
                "foreign_net": fl.get("foreign_net"),
                "inst_net": fl.get("inst_net"),
                # 희석이력(DART) — 유증/CB/BW 누적 빈도
                "dilution_count": _dil(tk),
                # 지배구조(공정위) — 총수일가 지배지분 %
                "family_pct": own.get("family_pct"),
            }
            if stale:
                row["stale_inputs"] = stale   # 정상 주엔 키 자체가 없다(파일 비대 회피)
            rows.append(row)

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

"""insider_trades_public_builder — 공개 터미널 내부자(임원·주요주주) 주식거래 빌더.

2026-06-19 신설. 에이전트 4갈래 가치판정 = build-now(최고 차별). DART elestock.json(임원ㆍ주요주주
특정증권등소유상황보고서) = 美 Form4 KR판. 증권사·토스·네이버 종목페이지에 없는 forensics 신호.
기존 DART 키·무료 20K/일 재사용(KIS 무관, RULE1 안전). dart_major_holders(기관 5%)와 직교 보완.

입력 = DART elestock.json (corp_code, bgn_de~end_de). 유니버스 = recommendations KR(소수, 쿼터 안전).
출력 = data/insider_trades.json (action.yml 등재). 네트워크 빌더 — daily_analysis_full 실행.
🚨 RULE 7 = 공시 사실만(보고자·직위·증감·날짜·원문). 자체 점수·매수신호 0. 관측-only.
  보고자 실명 = DART 공식 공개 사실(인용). 증감 부호 = 매수(+)/매도(−) 사실 표기.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REC_PATH = os.path.join(_ROOT, "data", "recommendations.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "insider_trades.json")
ELESTOCK = "https://opendart.fss.or.kr/api/elestock.json"
DART_VIEW = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
WINDOW_DAYS = 365
MAX_TRADES = 20
DELAY = 0.2


def _now_kst() -> datetime:
    return datetime.now(KST)


def _int(v) -> int:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def _kr_tickers() -> List[Dict[str, str]]:
    try:
        with open(REC_PATH, "r", encoding="utf-8") as f:
            recs = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for r in (recs if isinstance(recs, list) else []):
        tk = str(r.get("ticker") or "").strip()
        if tk.isdigit() and len(tk) == 6:
            out.append({"ticker": tk, "name": r.get("name") or tk})
    return out


def main() -> int:
    ok = False
    try:
        import requests
        from api.config import DART_API_KEY
        from api.collectors.dart_corp_code import get_corp_code

        if not DART_API_KEY:
            print("[insider] DART_API_KEY 부재 — skip", file=sys.stderr)
            return 0

        end_dt = _now_kst().date()
        bgn_de = (end_dt - timedelta(days=WINDOW_DAYS)).strftime("%Y%m%d")
        end_de = end_dt.strftime("%Y%m%d")

        stocks: List[Dict[str, Any]] = []
        sess = requests.Session()
        for u in _kr_tickers():
            tk, name = u["ticker"], u["name"]
            cc = get_corp_code(tk)
            if not cc:
                continue
            try:
                r = sess.get(ELESTOCK, params={"crtfc_key": DART_API_KEY, "corp_code": cc,
                                                "bgn_de": bgn_de, "end_de": end_de}, timeout=15)
                d = r.json()
            except Exception as e:  # noqa: BLE001
                print(f"[insider] {tk} elestock 실패: {e!r}", file=sys.stderr)
                time.sleep(DELAY)
                continue
            rows = d.get("list") or [] if d.get("status") == "000" else []
            trades = []
            net = buy_n = sell_n = 0
            for it in rows:
                chg = _int(it.get("sp_stock_lmp_irds_cnt"))
                net += chg
                if chg > 0:
                    buy_n += 1
                elif chg < 0:
                    sell_n += 1
                rc = str(it.get("rcept_no") or "")
                trades.append({
                    "date": str(it.get("rcept_dt") or ""),
                    "person": str(it.get("repror") or ""),
                    "position": str(it.get("isu_exctv_ofcps") or ""),
                    "registered": str(it.get("isu_exctv_rgist_at") or ""),
                    "change": chg,            # +매수 / −매도 (주)
                    "shares_after": _int(it.get("sp_stock_lmp_cnt")),
                    "source_url": (DART_VIEW + rc) if rc else "",
                })
            if not trades:
                time.sleep(DELAY)
                continue
            trades.sort(key=lambda t: t["date"], reverse=True)
            stocks.append({
                "ticker": tk, "name": name,
                "net_change": net, "buy_n": buy_n, "sell_n": sell_n, "total": len(trades),
                "trades": trades[:MAX_TRADES],
            })
            time.sleep(DELAY)

        if not stocks and os.path.isfile(OUTPUT_PATH):
            print("[insider] 0 종목 — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "DART elestock (임원·주요주주 특정증권 소유상황보고)",
                "window_days": WINDOW_DAYS,
                "count": len(stocks),
                "note": "공시 사실만 — 보고자·직위·증감(매수+/매도−)·날짜·원문. 자체 점수·매매신호 아님 (RULE 7). 美 Form4 KR판.",
            },
            "stocks": stocks,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[insider] logged=True · {len(stocks)} 종목 내부자거래 -> {os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[insider] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[insider] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

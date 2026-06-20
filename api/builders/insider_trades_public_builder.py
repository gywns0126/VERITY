"""insider_trades_public_builder — 공개 터미널 내부자(임원·주요주주) 주식거래 빌더.

2026-06-19 신설. 2026-06-20 전 종목 확장(rotation+carry-forward+rate-limit 가드+budget).
DART elestock.json(임원·주요주주 특정증권등소유상황보고서) = 美 Form4 KR판. 증권사·토스·네이버
종목페이지에 없는 forensics 신호. 기존 DART 키·무료 20K/일 재사용(KIS 무관, RULE1 안전).

🚨 전 종목 확장 설계 (universe 병목 해소):
- universe = stock_report_public.json (discovery와 동일 1,635, insider step 이 그 뒤 실행 → 정합).
  fallback = recommendations.json.
- 1일 1회 daily_analysis_full(120분 job) 내 실행 → 런타임 압박 회피 위해:
  · **일별 rotation**: rec 우선풀 항상 + 나머지를 (day-of-year) offset 회전 → 며칠 내 전 종목 커버.
  · **carry-forward 병합**: 오늘 수집 안 한 종목은 이전 snapshot 유지(내부자 공시=느린 이벤트, staleness 허용).
  · **wall-clock budget**(INSIDER_MAX_SECONDS, 기본 2700s) + MAX_CALLS — 예산 초과 시 안전 정지·보존.
  · **rate-limit 가드**: DART status 020(일일 제한)→정지·보존, 021(분당)→백오프 1회 재시도. 013=데이터없음(정상 공백).
- per-entry collected_at 로 신선도 투명 표기. 출력 = data/insider_trades.json (action.yml 등재).
🚨 RULE 7 = 공시 사실만(보고자·직위·증감·날짜·원문). 자체 점수·매수신호 0. 관측-only.
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
UNIVERSE_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
REC_PATH = os.path.join(_ROOT, "data", "recommendations.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "insider_trades.json")
ELESTOCK = "https://opendart.fss.or.kr/api/elestock.json"
DART_VIEW = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
WINDOW_DAYS = 365
MAX_TRADES = 20
DELAY = 0.2
MAX_SECONDS = int(os.environ.get("INSIDER_MAX_SECONDS", "2700"))  # 45분 wall-clock budget
MAX_CALLS = int(os.environ.get("INSIDER_MAX_CALLS", "5000"))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _int(v) -> int:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def _rec_kr_set() -> set:
    """우선풀 — recommendations.json KR 6자리(항상 수집해 featured 신선 유지)."""
    try:
        with open(REC_PATH, "r", encoding="utf-8") as f:
            recs = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    out = set()
    for r in (recs if isinstance(recs, list) else []):
        tk = str(r.get("ticker") or "").strip()
        if tk.isdigit() and len(tk) == 6:
            out.add(tk)
    return out


def _universe() -> List[Dict[str, str]]:
    """전 종목 universe = stock_report_public.json. 부재 시 recommendations.json fallback."""
    try:
        with open(UNIVERSE_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        arr = doc.get("stocks") if isinstance(doc, dict) else doc
        out = []
        for s in (arr or []):
            tk = str(s.get("ticker") or "").strip()
            if tk.isdigit() and len(tk) == 6:
                out.append({"ticker": tk, "name": s.get("name") or tk})
        if out:
            return out
    except (OSError, json.JSONDecodeError):
        pass
    # fallback
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


def _ordered_universe() -> List[Dict[str, str]]:
    """rec 우선풀 먼저 + 나머지를 day-of-year offset 으로 회전(전 종목 순차 커버)."""
    uni = _universe()
    rec = _rec_kr_set()
    priority = [u for u in uni if u["ticker"] in rec]
    rest = [u for u in uni if u["ticker"] not in rec]
    if rest:
        off = _now_kst().timetuple().tm_yday % len(rest)
        rest = rest[off:] + rest[:off]
    return priority + rest


def _load_prev() -> Dict[str, Dict[str, Any]]:
    """이전 snapshot → {ticker: entry} (carry-forward 병합 베이스)."""
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
        out = {}
        for s in (doc.get("stocks") or []):
            tk = str(s.get("ticker") or "")
            if tk:
                out[tk] = s
        return out
    except (OSError, json.JSONDecodeError):
        return {}


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
        today = end_dt.strftime("%Y-%m-%d")

        merged = _load_prev()            # carry-forward 베이스
        order = _ordered_universe()
        sess = requests.Session()
        t0 = time.monotonic()
        calls = collected = rate_stop = 0

        for u in order:
            if time.monotonic() - t0 > MAX_SECONDS or calls >= MAX_CALLS:
                print(f"[insider] budget 도달 (calls={calls}, {int(time.monotonic()-t0)}s) — 나머지 carry-forward", file=sys.stderr)
                break
            tk, name = u["ticker"], u["name"]
            cc = get_corp_code(tk)
            if not cc:
                continue
            status = ""
            rows: List[Any] = []
            for attempt in range(2):  # 021(분당 제한) 1회 백오프 재시도
                try:
                    r = sess.get(ELESTOCK, params={"crtfc_key": DART_API_KEY, "corp_code": cc,
                                                    "bgn_de": bgn_de, "end_de": end_de}, timeout=15)
                    d = r.json()
                    calls += 1
                except Exception as e:  # noqa: BLE001
                    print(f"[insider] {tk} elestock 실패: {e!r}", file=sys.stderr)
                    status = "ERR"
                    break
                status = str(d.get("status") or "")
                if status == "021" and attempt == 0:   # 분당 요청 제한 → 백오프
                    time.sleep(60)
                    continue
                rows = d.get("list") or [] if status == "000" else []
                break

            if status == "020":  # 일일 요청 제한 초과 — 정지(이후 전부 carry-forward)
                rate_stop = 1
                print(f"[insider] DART 020 일일 제한 — 정지 (collected={collected})", file=sys.stderr)
                break
            if status not in ("000", "013"):
                # 🚨 비권위적 응답(ERR·800 점검·021 재발·미상) — 일시 오류이므로 이전 데이터 보존(pop 금지).
                # 권위적 공백(000 빈 list / 013 데이터없음)만 아래서 aged-out 처리.
                time.sleep(DELAY)
                continue

            collected += 1
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
            if trades:
                trades.sort(key=lambda t: t["date"], reverse=True)
                merged[tk] = {
                    "ticker": tk, "name": name,
                    "net_change": net, "buy_n": buy_n, "sell_n": sell_n, "total": len(trades),
                    "trades": trades[:MAX_TRADES], "collected_at": today,
                }
            else:
                merged.pop(tk, None)   # 윈도우 내 공시 0 — 이전 데이터 제거(aged out)
            time.sleep(DELAY)

        stocks = sorted(merged.values(), key=lambda s: -abs(_int(s.get("net_change"))))

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
                "universe": len(order),
                "collected_today": collected,
                "rate_limited": bool(rate_stop),
                "note": "공시 사실만 — 보고자·직위·증감(매수+/매도−)·날짜·원문. 자체 점수·매매신호 아님 (RULE 7). 美 Form4 KR판. 전 종목 회전 수집(per-stock collected_at).",
            },
            "stocks": stocks,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[insider] logged=True · {len(stocks)} 종목(누적) · 오늘수집 {collected}/{len(order)} -> {os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
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

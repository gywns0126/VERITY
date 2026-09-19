"""insider_trades_public_builder — 공개 터미널 내부자(임원·주요주주) 주식거래 빌더.

2026-06-19 신설. 2026-06-20 전 종목 확장(rotation+carry-forward+rate-limit 가드+budget).
DART elestock.json(임원·주요주주 특정증권등소유상황보고서) = 美 Form4 KR판. 증권사·토스·네이버
종목페이지에 없는 forensics 신호. 기존 DART 키·무료 20K/일 재사용(KIS 무관, RULE1 안전).

🚨 전 종목 확장 설계 (universe 병목 해소):
- universe = stock_report_public.json (discovery와 동일한 공개 KR 전 종목, insider step 이 그 뒤 실행 → 정합).
  fallback = recommendations.json.
- 평일 오전·오후 daily_analysis_full(240분 상한) 내 실행 → 런타임 압박 회피 위해:
  · **반일 rotation**: rec 우선풀 항상 + 나머지를 오전/오후 배치 단위로 회전 → 며칠 내 전 종목 커버.
  · **carry-forward 병합**: 오늘 수집 안 한 종목은 이전 snapshot 유지(내부자 공시=느린 이벤트, staleness 허용).
  · **wall-clock budget**(INSIDER_MAX_SECONDS, 기본 600s) + MAX_CALLS(기본 300) — 예산 초과 시 안전 정지·보존.
  · **rate-limit 가드**: DART status 020(요청 제한)→정지·보존. 013=조회 데이터 없음.
    021은 회사 개수 초과이며 분당 제한이 아니다(공식 개발가이드 2026-09-20 확인); 재시도하지 않는다.
- per-entry collected_at 로 신선도 투명 표기. 출력 = data/insider_trades.json (action.yml 등재).
- coverage.by_ticker = 마지막 시도/성공 근거, 이번 실행의 시도 여부·누락 사유. 과거 부재는 0으로 변환하지 않는다.

🚨 2026-08-20 실측 — elestock 는 bgn_de/end_de 를 **무시하고 자체 약 2년 롤링 창을 반환한다**.
   ① 파라미터 무시: 000660 로 3회 대조(파라미터 없음 / 20260701~20260820 / 20260819 단일일자)
      → 전부 559건 동일. WINDOW_DAYS 를 API 에 넘기는 것만으로는 창이 잡히지 않는다.
   ② 🚨 그런데 '전 기간'도 아니다(같은 날 저녁 정정). 5종목 최古 rcept_dt 실측 —
      005930 2024-08-26 · 005380 2024-08-22 · 035420 2024-08-30 · 000660 2024-09-02
      = 전부 today−730d(2024-08-20) 직후에 몰린다. 즉 **약 2년 롤링**이다.
   ③ 그래서 전 기간 집계는 **매일 조금씩 뒤가 잘려 값이 흔들린다**. 같은 날 실측:
      08:15 run 559건 net +106,615 → 18:11 run 558건 net +106,531 (코드 동일, 2024-08-20 행 소멸).
      같은 두 run 에서 *_365d 는 59,122 / 315건으로 **완전 동일** — 창 필드만 안정적이다.
   2026-06-19 신설 이래 _meta.window_days=365 는 **거짓 신고**였다(약 2년 누적을 1년으로 표기).
   → net_change/buy_n/sell_n/total = 약 2년 롤링 누적(정의 유지 — 기존 랭킹·관측 trail 연속성.
     🚨 단 위 ③ 때문에 시계열 비교·회귀 입력으로는 부적합),
     최근 365일 = rcept_dt 로컬 필터한 *_365d 필드. 창이 필요한 소비자는 후자를 쓸 것.
🚨 RULE 7 = 공시 사실만(보고자·직위·증감·날짜·원문). 자체 점수·매수신호 0. 관측-only.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections import Counter
from copy import deepcopy
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
MAX_SECONDS = int(os.environ.get("INSIDER_MAX_SECONDS", "600"))  # 10분 wall-clock budget
MAX_CALLS = int(os.environ.get("INSIDER_MAX_CALLS", "300"))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _int(v) -> int:
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def _rate(v):
    """소유비율(%) 파싱 — '-'/공백 → None."""
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _is_corporate_action(it: Dict[str, Any], chg: int, shares_after: int) -> bool:
    """비매매(감자·주식병합·무상증자·액면분할·주요주주 전량 재기재) 판정.

    신호 = 유의미 지분(소유비율 ≥1%) 보유자인데 '소유비율 증감'이 0.00% 인데도 대량 수량 증감.
    비례 자본변동은 소유비율이 안 변함(감자 후에도 89.14%). 실제 매매면 비율이 반드시 변함.
    → 대형주 임원 소액매매(소유비율≈0%)·첫취득은 오분류 안 됨(rate_after<1 이라 제외). 실측 검증:
       국일제지 삼라마이다스 -904.5M주(감자, rate_after 89.14%·irds 0.00%)만 잡고 KB/신한/삼성 실매매 전량 보존.
    """
    rate_after = _rate(it.get("sp_stock_lmp_rate"))       # 소유비율 (변동 후, %)
    irds_rate = _rate(it.get("sp_stock_lmp_irds_rate"))   # 소유비율 증감 (%)
    return (
        rate_after is not None and rate_after >= 1.0
        and irds_rate is not None and abs(irds_rate) < 0.005
        and shares_after and abs(chg) >= shares_after * 0.5
    )


def _aggregate(rows: List[Dict[str, Any]], cutoff_365: str):
    """elestock rows → (trades 최신순, 집계 dict). 집계 2벌을 나란히 낸다.

    · 전 기간 누적 = net_change / buy_n / sell_n / total
        elestock 가 날짜 파라미터를 무시하므로 이게 원래부터의 실제 정의였다(docstring 참조).
        정의를 바꾸지 않는다 — 공개 랭킹과 2026-06-21~ 관측 trail 의 연속성 때문.
    · 최근 365일 = *_365d — 창은 API 가 아니라 rcept_dt 로컬 필터가 잡는다.
    자본변동(감자·병합·무상증자·재기재)은 양쪽 net/건수에서 모두 제외하고 total 에는 포함한다
    (기존 정의 유지 — 국일제지 -9억주 '최대 순매도' 유령 차단분).
    """
    trades: List[Dict[str, Any]] = []
    net = buy_n = sell_n = 0
    net365 = buy365 = sell365 = total365 = 0
    for it in rows:
        chg = _int(it.get("sp_stock_lmp_irds_cnt"))
        shares_after = _int(it.get("sp_stock_lmp_cnt"))
        corp_action = _is_corporate_action(it, chg, shares_after)
        rcept_dt = str(it.get("rcept_dt") or "")
        in_365 = bool(rcept_dt) and rcept_dt >= cutoff_365   # 'YYYY-MM-DD' 사전순 = 시간순
        if in_365:
            total365 += 1
        if not corp_action:
            net += chg
            if chg > 0:
                buy_n += 1
            elif chg < 0:
                sell_n += 1
            if in_365:
                net365 += chg
                if chg > 0:
                    buy365 += 1
                elif chg < 0:
                    sell365 += 1
        rc = str(it.get("rcept_no") or "")
        trades.append({
            "date": rcept_dt,
            "person": str(it.get("repror") or ""),
            "position": str(it.get("isu_exctv_ofcps") or ""),
            "registered": str(it.get("isu_exctv_rgist_at") or ""),
            "change": chg,            # +매수 / −매도 (주)
            "shares_after": shares_after,
            "kind": "corporate_action" if corp_action else "trade",
            "source_url": (DART_VIEW + rc) if rc else "",
        })
    trades.sort(key=lambda t: t["date"], reverse=True)
    return trades, {
        "net_change": net, "buy_n": buy_n, "sell_n": sell_n, "total": len(trades),
        "net_change_365d": net365, "buy_n_365d": buy365,
        "sell_n_365d": sell365, "total_365d": total365,
    }


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
    """rec 우선풀 먼저 + 나머지를 오전/오후 배치 단위로 회전한다.

    종전 ``day-of-year % len(rest)`` 는 하루에 한 종목만 전진했다. 호출 상한을 낮추면
    전날 배치와 거의 전부 겹쳐 전 종목 커버에 수년이 걸린다. 우선풀에 소비되는 호출을
    제외한 실제 나머지 배치 폭만큼 이동하고, 06:30/16:50 Full이 서로 다른 구간을 읽는다.
    """
    uni = _universe()
    rec = _rec_kr_set()
    priority = [u for u in uni if u["ticker"] in rec]
    rest = [u for u in uni if u["ticker"] not in rec]
    if rest:
        now = _now_kst()
        half_day_slot = now.timetuple().tm_yday * 2 + int(now.hour >= 12)
        rest_batch = max(1, MAX_CALLS - len(priority))
        off = (half_day_slot * rest_batch) % len(rest)
        rest = rest[off:] + rest[:off]
    return priority + rest


def _load_prev():
    """거래와 조회 근거를 함께 읽는다. 손상된 기존 파일은 빈 자료로 덮지 않는다."""
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        return {}, {}
    if not isinstance(doc, dict) or not isinstance(doc.get("stocks"), list):
        raise ValueError("invalid previous insider snapshot")
    out = {}
    for s in doc["stocks"]:
        if not isinstance(s, dict) or not s.get("ticker"):
            raise ValueError("invalid previous insider row")
        tk = str(s["ticker"])
        if tk in out and out[tk] != s:
            raise ValueError("conflicting previous insider rows")
        out[tk] = s
    coverage = doc.get("coverage", {})
    if not isinstance(coverage, dict):
        raise ValueError("invalid previous insider coverage")
    if coverage and (
        type(coverage.get("schema_version")) is not int or coverage["schema_version"] != 1
        or not isinstance(coverage.get("by_ticker"), dict)
        or any(not isinstance(v, dict) or v.get("state") not in (
            "ok", "empty", "failed", "not_collected", "legacy_unverified",
        ) for v in coverage["by_ticker"].values())
    ):
        raise ValueError("unsupported previous insider coverage")
    return out, coverage.get("by_ticker", {})


def _coverage_base(previous, merged, order):
    """과거 조회 시각은 보존한다. 옛 거래 행의 존재를 새 수집 성공으로 승격하지 않는다."""
    current = {u["ticker"] for u in order}
    entries = deepcopy(previous)
    for tk in sorted(current | set(merged) | set(entries)):
        entry = entries.setdefault(tk, {
            "state": "legacy_unverified" if tk in merged else "not_collected",
        })
        entry.update(attempted_this_run=False, in_universe=tk in current)
        entry.pop("skip_reason", None)
        if tk not in current:
            entry["skip_reason"] = "outside_universe"
    return entries


def _write_snapshot(out):
    """같은 디렉터리의 임시 파일을 완성한 뒤 교체해 중간 쓰기 손실을 막는다."""
    parent = os.path.dirname(os.path.abspath(OUTPUT_PATH))
    fd, temporary = tempfile.mkstemp(prefix=".insider-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, OUTPUT_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


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
        # 🚨 elestock 는 이 두 파라미터를 무시한다(2026-08-20 실측, docstring 참조).
        #    호출 호환을 위해 계속 넘기되, 창 집계는 아래 cutoff_365 로컬 필터가 담당한다.
        bgn_de = (end_dt - timedelta(days=WINDOW_DAYS)).strftime("%Y%m%d")
        end_de = end_dt.strftime("%Y%m%d")
        today = end_dt.strftime("%Y-%m-%d")
        cutoff_365 = (end_dt - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")

        merged, previous_coverage = _load_prev()
        order = _ordered_universe()
        if not order:
            print("[insider] universe 없음 — 기존 snapshot 보존", file=sys.stderr)
            return 1
        coverage = _coverage_base(previous_coverage, merged, order)
        sess = requests.Session()
        t0 = time.monotonic()
        calls = collected = rate_stop = 0
        stop_reason = ""

        for u in order:
            if time.monotonic() - t0 > MAX_SECONDS or calls >= MAX_CALLS:
                print(f"[insider] budget 도달 (calls={calls}, {int(time.monotonic()-t0)}s) — 나머지 carry-forward", file=sys.stderr)
                stop_reason = "budget_exhausted"
                break
            tk, name = u["ticker"], u["name"]
            entry = coverage[tk]
            try:
                cc = get_corp_code(tk)
            except Exception:  # 매핑 실패도 0건 근거가 아니다.
                entry["skip_reason"] = "corp_code_lookup_failed"
                continue
            if not cc:
                entry["skip_reason"] = "corp_code_unavailable"
                continue
            if time.monotonic() - t0 > MAX_SECONDS or calls >= MAX_CALLS:
                stop_reason = "budget_exhausted"
                break  # 매핑 조회 중 예산 소진: 아직 시도하지 않은 요청.
            entry.update(attempted_this_run=True, last_attempt_at=_now_kst().isoformat())
            calls += 1  # 전송/JSON 실패도 실제 시도 횟수에서 빠지지 않는다.
            status, failure = "", ""
            rows: List[Any] = []
            d = None
            try:
                r = sess.get(ELESTOCK, params={"crtfc_key": DART_API_KEY, "corp_code": cc,
                                                "bgn_de": bgn_de, "end_de": end_de}, timeout=15)
                r.raise_for_status()
                d = r.json()
            except Exception as e:  # noqa: BLE001
                # requests 예외 문자열에는 키가 포함된 URL이 있을 수 있다.
                print(f"[insider] {tk} elestock 실패: {type(e).__name__}", file=sys.stderr)
                failure = "request_failed"
            if not failure and not isinstance(d, dict):
                failure = "invalid_response"
            if not failure:
                status = str(d.get("status") or "")
                if status == "000":
                    rows = d.get("list")
                    if not isinstance(rows, list) or any(
                        not isinstance(row, dict) or not row.get("rcept_no") or not row.get("rcept_dt")
                        for row in rows
                    ):
                        failure = "invalid_rows"
                elif status == "013":
                    if d.get("list") not in (None, []):
                        failure = "conflicting_empty_response"
                else:
                    failure = "dart_status"
            entry.pop("dart_status", None)
            if status.isdigit() and len(status) == 3:
                entry["dart_status"] = status
            if status == "020":  # 일일 요청 제한 초과 — 정지(이후 전부 carry-forward)
                rate_stop = 1
                stop_reason = "rate_limit"
                print(f"[insider] DART 020 일일 제한 — 정지 (collected={collected})", file=sys.stderr)
            if not failure:
                try:
                    trades, agg = _aggregate(rows, cutoff_365)
                except (TypeError, ValueError, OverflowError):
                    failure = "invalid_rows"
            if failure:
                entry.update(state="failed", failure_reason=failure)
                if stop_reason:
                    break
                time.sleep(DELAY)
                continue

            collected += 1
            state = "ok" if trades else "empty"
            entry.update(state=state, last_success_at=entry["last_attempt_at"],
                         last_success_state=state, last_success_row_count=len(rows))
            entry.pop("failure_reason", None)
            if trades:
                merged[tk] = {
                    "ticker": tk, "name": name, **agg,
                    "trades": trades[:MAX_TRADES], "collected_at": today,
                }
            else:
                merged.pop(tk, None)   # 공시 0 — 이전 데이터 제거(aged out)
            time.sleep(DELAY)

        for entry in coverage.values():
            if entry["in_universe"] and not entry["attempted_this_run"]:
                entry.setdefault("skip_reason", stop_reason or "not_attempted")
        current_coverage = [e for e in coverage.values() if e["in_universe"]]
        stocks = sorted(merged.values(), key=lambda s: -abs(_int(s.get("net_change"))))

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "DART elestock (임원·주요주주 특정증권 소유상황보고)",
                # 🚨 2026-08-20 정정 — 종전 365 신고는 거짓이었다. elestock 가 날짜 파라미터를
                #    무시하고 자체 약 2년 롤링 창을 준다(docstring ②③). None = "우리가 정한 창 없음".
                #    우리가 통제하는 창은 *_365d 뿐이고 그쪽만 값이 안정적이다.
                "window_days": None,
                "window_note": (
                    "DART elestock 는 bgn_de/end_de 를 무시하고 자체 약 2년 롤링 창을 반환한다"
                    "(2026-08-20 실측 — 5종목 최古 rcept_dt 가 전부 today-730d 직후). "
                    "net_change/buy_n/sell_n/total = 그 약 2년 누적이며 오래된 행이 빠져 매일 흔들린다"
                    "(같은 날 08:15 559건 → 18:11 558건). 안정적인 창 집계 = *_365d 필드."
                ),
                "window_365d_from": cutoff_365,
                "count": len(stocks),
                "universe": len(order),
                "collected_today": collected,
                "batch_max_calls": MAX_CALLS,
                "batch_max_seconds": MAX_SECONDS,
                "rotation": "half_day_batch_stride",
                "rate_limited": bool(rate_stop),
                "note": "공시 사실만 — 보고자·직위·증감(매수+/매도−)·날짜·원문. 자체 점수·매매신호 아님 (RULE 7). 美 Form4 KR판. 전 종목 회전 수집(per-stock collected_at).",
            },
            "stocks": stocks,
            # 되돌리지 말 것: 빈 응답과 미조회는 다르다. empty는 이 조회 시점의 API
            # 반환 창에 한정되며, 영구 0건/현재 거래 없음/완전한 종목 커버리지 뜻이 아니다.
            # last_success_*는 실패·미조회 때 과거 시각 그대로 보존한다. 소비자는 명시적으로
            # 이 근거를 해석해야 하며 기존 stocks 목록에 가상의 0값 행을 만들지 않는다.
            "coverage": {
                "schema_version": 1,
                "universe_count": len(current_coverage),
                "attempted_this_run": sum(e["attempted_this_run"] for e in current_coverage),
                "request_count": calls,
                "counts": dict(Counter(e["state"] for e in current_coverage)),
                "by_ticker": coverage,
            },
        }
        _write_snapshot(out)
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

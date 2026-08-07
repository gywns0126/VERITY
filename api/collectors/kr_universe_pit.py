# -*- coding: utf-8 -*-
"""kr_universe_pit — 시점별(point-in-time) KR 상장 유니버스 수집 → 상폐 종목 복원.

**왜 필요한가**: 백테스트의 생사를 가르는 건 생존 편향이다. 현재 보유한 분기 스냅샷
(dart_quarterly_snapshots, 2016~ 52분기, 1,989종목)은 **오늘 살아남은 종목만** 골라 과거를
채운 것이다 — 2016년 분기를 가진 1,080종목이 **전부 현재 상장 상태**이고 사라진 종목이 0이다.
10년간 상폐가 0건일 수 없으니 확정적 생존 편향이다.

이 데이터로 백테스트를 돌리면 망한 회사가 표본에서 통째로 빠져 어떤 산식이든 수익률이
부풀고, 그 숫자를 믿고 실전에 가면 정확히 그 차이만큼 잃는다. **백테스트가 없는 것보다
나쁘다** — 근거 없는 확신이 생기기 때문이다.

**어떻게 푸는가**: 금융위 주식시세정보 API 는 `basDt`(기준일자)를 받아 **그 날의 전체 상장
종목**을 돌려준다. 실호출 확인(2026-08-07):
    20200102 → 2,475종목 · 20210104 → 2,531 · 20230102 → 2,690
    20250102 → 2,866 · 20260806 → 2,872
과거 날짜의 유니버스를 모으면 그 시점에 존재했다가 지금 없는 종목 = 상폐/합병/편출이다.
별도 상폐 데이터 소스를 붙일 필요가 없다.

산출: data/kr_universe_pit.jsonl  (한 줄 = 한 기준일 스냅샷)
      {as_of, bas_dt, n_listed, tickers:[...], collected_at}
      data/kr_delisting.json      (누적 판정 — 최초/최종 관측일 + 소멸 추정)

🚨 판정 주의: "현재 목록에 없음"이 곧 상장폐지는 아니다. 우선주 병합·티커 변경·이전상장도
   같은 형태로 보인다. 그래서 이 모듈은 **관측 사실(최초/최종 관측일)만 기록**하고
   `disappeared` 로 표기할 뿐, 사유를 단정하지 않는다. 사유 분류는 별도 확인 대상.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set

try:
    from api.config import DATA_DIR
    _DATA = DATA_DIR
except Exception:  # 단독 실행 폴백
    _DATA = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

BASE_URL = ("https://apis.data.go.kr/1160100/service/"
            "GetStockSecuritiesInfoService/getStockPriceInfo")
PIT_PATH = os.path.join(_DATA, "kr_universe_pit.jsonl")
DELIST_PATH = os.path.join(_DATA, "kr_delisting.json")

_ROWS = 5000          # 페이지당 (전체 ~2,900이라 1~2페이지)
_SLEEP = 0.15         # 유량 가드
_TIMEOUT = 25
_MAX_PAGES = 5


def _api_key() -> str:
    return (os.environ.get("PUBLIC_DATA_API_KEY")
            or os.environ.get("KRX_API_KEY") or "")


def _call(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    key = _api_key()
    if not key:
        print("[kr_universe_pit] PUBLIC_DATA_API_KEY 없음", file=sys.stderr)
        return None
    qs = "serviceKey=" + urllib.parse.quote(key, safe="") + "&resultType=json"
    for k, v in params.items():
        qs += f"&{urllib.parse.quote(str(k))}={urllib.parse.quote(str(v))}"
    try:
        req = urllib.request.Request(BASE_URL + "?" + qs,
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            doc = json.loads(r.read().decode("utf-8", "replace"))
        return (doc.get("response") or {}).get("body") or {}
    except Exception as e:  # noqa: BLE001
        print(f"[kr_universe_pit] 호출 실패 {params.get('basDt')}: "
              f"{type(e).__name__}: {str(e)[:80]}", file=sys.stderr)
        return None


def fetch_universe(bas_dt: str) -> Optional[List[str]]:
    """기준일자의 전체 상장 종목코드. 휴장일이면 빈 리스트, 실패면 None.

    🚨 빈 리스트(휴장)와 None(실패)을 구분한다 — 실패를 '그날 상장 0'으로 기록하면
    전 종목이 그날 상폐된 것처럼 보인다.
    """
    body = _call({"numOfRows": _ROWS, "pageNo": 1, "basDt": bas_dt})
    if body is None:
        return None
    total = int(body.get("totalCount") or 0)
    if total == 0:
        return []                       # 휴장일 — 정상
    out: Set[str] = set()

    def _absorb(b: Dict[str, Any]) -> None:
        items = ((b.get("items") or {}).get("item") or [])
        if isinstance(items, dict):
            items = [items]
        for it in items:
            code = str(it.get("srtnCd") or it.get("isinCd") or "").strip()
            if code.startswith("A"):
                code = code[1:]
            if len(code) == 6 and code.isdigit():
                out.add(code)

    _absorb(body)
    pages = min(_MAX_PAGES, (total + _ROWS - 1) // _ROWS)
    for p in range(2, pages + 1):
        time.sleep(_SLEEP)
        b = _call({"numOfRows": _ROWS, "pageNo": p, "basDt": bas_dt})
        if b is None:
            print(f"[kr_universe_pit] {bas_dt} p{p} 실패 — 부분 수집 폐기(오염 방지)",
                  file=sys.stderr)
            return None                 # 부분 유니버스는 상폐 오판을 낳는다
        _absorb(b)
    return sorted(out)


def month_ends(start: date, end: date) -> List[str]:
    """구간 내 월말(달력) 목록. 휴장이면 fetch 가 빈 리스트를 주므로 caller 가 앞당긴다."""
    out: List[str] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        nxt = date(y + (m == 12), (m % 12) + 1, 1)
        out.append((nxt - timedelta(days=1)).strftime("%Y%m%d"))
        y, m = nxt.year, nxt.month
    return out


def _existing_dates() -> Set[str]:
    if not os.path.exists(PIT_PATH):
        return set()
    got: Set[str] = set()
    with open(PIT_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                got.add(str(json.loads(line).get("bas_dt")))
            except Exception:  # noqa: BLE001
                continue
    return got


def collect(start: str, end: str, max_calls: int = 200) -> Dict[str, Any]:
    """월말 기준 시점별 유니버스 수집 (멱등 — 이미 있는 기준일은 skip).

    휴장일이면 최대 5영업일까지 앞당겨 재시도한다(월말이 주말/공휴일인 경우).
    """
    s = date(int(start[:4]), int(start[4:6]), int(start[6:]))
    e = date(int(end[:4]), int(end[4:6]), int(end[6:]))
    done = _existing_dates()
    added, skipped, failed, holiday = 0, 0, 0, 0
    os.makedirs(os.path.dirname(PIT_PATH) or ".", exist_ok=True)
    with open(PIT_PATH, "a", encoding="utf-8") as f:
        for target in month_ends(s, e):
            if added + failed >= max_calls:
                break
            if target in done:
                skipped += 1
                continue
            tickers: Optional[List[str]] = None
            probe = target
            for _ in range(6):          # 월말이 휴장이면 앞 영업일로
                tickers = fetch_universe(probe)
                if tickers:
                    break
                if tickers is None:
                    break               # 실패 — 앞당겨도 같은 결과일 가능성
                d = date(int(probe[:4]), int(probe[4:6]), int(probe[6:])) - timedelta(days=1)
                probe = d.strftime("%Y%m%d")
                time.sleep(_SLEEP)
            if tickers is None:
                failed += 1
                continue
            if not tickers:
                holiday += 1
                continue
            f.write(json.dumps({
                "as_of": target, "bas_dt": probe, "n_listed": len(tickers),
                "tickers": tickers,
                "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                              time.localtime(time.time() + 9 * 3600)),
            }, ensure_ascii=False) + "\n")
            added += 1
            time.sleep(_SLEEP)
    return {"added": added, "skipped": skipped, "failed": failed, "holiday": holiday}


def build_delisting() -> Dict[str, Any]:
    """수집된 시점 유니버스 → 종목별 최초/최종 관측일 + 소멸 표기.

    🚨 사유를 단정하지 않는다. "최종 관측 이후 사라짐"은 상장폐지일 수도, 우선주 병합·
    티커 변경·이전상장일 수도 있다. 관측 사실만 남기고 분류는 소비자 몫이다.
    """
    if not os.path.exists(PIT_PATH):
        return {"status": "no_data"}
    snaps: List[Dict[str, Any]] = []
    with open(PIT_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                snaps.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    if not snaps:
        return {"status": "no_data"}
    snaps.sort(key=lambda x: str(x.get("as_of")))
    latest = str(snaps[-1].get("as_of"))
    first_seen: Dict[str, str] = {}
    last_seen: Dict[str, str] = {}
    for s in snaps:
        d = str(s.get("as_of"))
        for t in (s.get("tickers") or []):
            first_seen.setdefault(t, d)
            last_seen[t] = d
    gone = {t: last_seen[t] for t in last_seen if last_seen[t] != latest}
    doc = {
        "as_of": latest,
        "snapshots": len(snaps),
        "window": [str(snaps[0].get("as_of")), latest],
        "tickers_ever": len(first_seen),
        "tickers_latest": sum(1 for t in last_seen if last_seen[t] == latest),
        "disappeared": len(gone),
        "first_seen": first_seen,
        "last_seen": last_seen,
        "note": ("최종 관측 이후 사라진 종목 = 상폐·합병·티커변경·이전상장 혼재. "
                 "사유 단정 금지 — 관측 사실만 기록한다. "
                 "백테스트 유니버스는 각 시점의 tickers 를 그대로 써야 생존 편향이 없다."),
    }
    tmp = DELIST_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DELIST_PATH)
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20200101")
    ap.add_argument("--end", default=time.strftime("%Y%m%d"))
    ap.add_argument("--max-calls", type=int, default=200)
    ap.add_argument("--build-only", action="store_true")
    a = ap.parse_args()
    if not a.build_only:
        r = collect(a.start, a.end, a.max_calls)
        print(f"[kr_universe_pit] 수집 +{r['added']} · skip {r['skipped']} · "
              f"휴장 {r['holiday']} · 실패 {r['failed']}")
    d = build_delisting()
    if d.get("status") == "no_data":
        print("[kr_universe_pit] 스냅샷 없음")
        return 0
    print(f"[kr_universe_pit] 스냅샷 {d['snapshots']}개 {d['window'][0]}~{d['window'][1]} · "
          f"등장 종목 {d['tickers_ever']:,} · 최신 {d['tickers_latest']:,} · "
          f"사라짐 {d['disappeared']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

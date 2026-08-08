# -*- coding: utf-8 -*-
"""kr_chart_delisted — 소멸 종목 일봉 수집 (백테스트 생존 편향 해소의 마지막 조각).

**왜 별도 수집기인가**: 기존 일봉 레이크(kr_chart_daily 청크 · kr_chart_history Blob)는
**현재 상장 유니버스 기준**으로 수집된다. 그래서 상장 소멸 종목의 가격이 0/415 다.
가격이 없으면 상폐 종목을 유니버스에 넣어도 수익률을 못 매겨 결국 생존 편향이 남는다.

**되는 이유**: 금융위 주식시세정보 API 는 소멸 종목의 과거 시세를 **마지막 거래일까지**
그대로 보유한다. 실호출 확인(2026-08-07):
    008560 메리츠증권 820행 ~2023-04-24 · 007630 폴루스바이오팜 529행
    011160 두산건설 56행 · 003415 쌍용양회우 229행 ~2020-12-02
표본 48건 중 **보통주 90%** (우선주 정리는 10%뿐) — 실제 상장 소멸이 대부분이다.

입력: data/kr_delisting.json 의 `last_seen != as_of` 종목 (kr_universe_pit 산출)
산출: data/kr_chart_delisted/chunk_*.json — kr_chart_daily 와 **동일 스키마**
      {stocks: {ticker: {t, n, c:[[yyyymmdd,o,h,l,c,v], ...]}}}
      백테스트가 현 유니버스 청크와 같은 로더로 읽을 수 있게 맞춘다.

🚨 소멸일(마지막 봉)을 함께 기록한다 — 백테스트에서 그 이후를 조회하면 안 된다.
   상폐 종목의 "이후 수익률"을 0 이나 마지막 가격으로 채우면 **손실을 지운다**.
   실제 상폐는 정리매매에서 대부분 소각되므로, 소비자가 명시적으로 처리하도록
   `last_bar` 를 노출하고 이 모듈은 값을 지어내지 않는다.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

try:
    from api.config import DATA_DIR
    _DATA = DATA_DIR
except Exception:  # 단독 실행 폴백
    _DATA = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

BASE_URL = ("https://apis.data.go.kr/1160100/service/"
            "GetStockSecuritiesInfoService/getStockPriceInfo")
DELIST_PATH = os.path.join(_DATA, "kr_delisting.json")
OUT_DIR = os.path.join(_DATA, "kr_chart_delisted")
META_PATH = os.path.join(_DATA, "kr_chart_delisted_meta.json")

_BULK_ROWS = 5000     # 종목당 전 기간 1콜 (최장 관측 820행)
_WORKERS = 8          # GH 러너→data.go.kr RTT ~1.2s. 8병렬 = 게이트웨이 한도 내
_TIMEOUT = 25
_PER_CHUNK = 60       # 청크당 종목 수 (kr_chart_daily ~780KB 감각 유지)


def _api_key() -> str:
    return (os.environ.get("PUBLIC_DATA_API_KEY")
            or os.environ.get("KRX_API_KEY") or "")


def _call(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    key = _api_key()
    if not key:
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
    except Exception:  # noqa: BLE001 — 개별 실패는 caller 가 집계
        return None


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def fetch_one(ticker: str) -> Optional[Dict[str, Any]]:
    """단일 종목 전 기간 일봉. 실패/무데이터면 None.

    반환 = {t, n, c:[[yyyymmdd,o,h,l,c,v], ...] 오름차순}
    """
    body = _call({"numOfRows": _BULK_ROWS, "pageNo": 1, "likeSrtnCd": ticker})
    if not body:
        return None
    items = ((body.get("items") or {}).get("item") or [])
    if isinstance(items, dict):
        items = [items]
    rows: List[List[int]] = []
    name = None
    for it in items:
        code = str(it.get("srtnCd") or "").lstrip("A")
        if code != ticker:
            continue                      # likeSrtnCd 는 부분일치 — 정확히 걸러낸다
        d = _to_int(it.get("basDt"))
        c = _to_int(it.get("clpr"))
        if d is None or c is None:
            continue
        rows.append([d,
                     _to_int(it.get("mkp")) or 0,
                     _to_int(it.get("hipr")) or 0,
                     _to_int(it.get("lopr")) or 0,
                     c,
                     _to_int(it.get("trqu")) or 0])
        name = name or it.get("itmsNm")
    if not rows:
        return None
    rows.sort(key=lambda x: x[0])
    return {"t": ticker, "n": name, "c": rows}


def _disappeared() -> List[str]:
    try:
        with open(DELIST_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    latest = str(d.get("as_of"))
    last = d.get("last_seen") or {}
    return sorted(t for t, v in last.items() if str(v) != latest)


def _existing() -> Dict[str, int]:
    """이미 수집된 종목 → 봉 수 (멱등 · 재수집 회피)."""
    out: Dict[str, int] = {}
    for p in sorted(__import__("glob").glob(os.path.join(OUT_DIR, "chunk_*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                for tk, ent in (json.load(f).get("stocks") or {}).items():
                    out[str(tk)] = len((ent or {}).get("c") or [])
        except (OSError, json.JSONDecodeError):
            continue
    return out


def collect(limit: int = 500, refresh: bool = False) -> Dict[str, Any]:
    tickers = _disappeared()
    if not tickers:
        return {"status": "no_input", "hint": "kr_universe_pit 먼저 실행"}
    have = {} if refresh else _existing()
    todo = [t for t in tickers if t not in have][:limit]
    fetched: Dict[str, Dict[str, Any]] = {}
    failed: List[str] = []
    if todo:
        with cf.ThreadPoolExecutor(max_workers=_WORKERS) as ex:
            for tk, res in zip(todo, ex.map(fetch_one, todo)):
                if res:
                    fetched[tk] = res
                else:
                    failed.append(tk)

    # 기존 + 신규 병합 후 청크 재작성 (멱등)
    merged: Dict[str, Dict[str, Any]] = {}
    for p in sorted(__import__("glob").glob(os.path.join(OUT_DIR, "chunk_*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                merged.update(json.load(f).get("stocks") or {})
        except (OSError, json.JSONDecodeError):
            continue
    merged.update(fetched)

    os.makedirs(OUT_DIR, exist_ok=True)
    for old in __import__("glob").glob(os.path.join(OUT_DIR, "chunk_*.json")):
        os.remove(old)
    keys = sorted(merged)
    for i in range(0, len(keys), _PER_CHUNK):
        part = {k: merged[k] for k in keys[i:i + _PER_CHUNK]}
        with open(os.path.join(OUT_DIR, f"chunk_{i // _PER_CHUNK:03d}.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"stocks": part}, f, ensure_ascii=False, separators=(",", ":"))

    # 🚨 소멸일 메타 — 백테스트가 그 이후를 조회하면 안 된다.
    #    값을 지어내지 않는다(0 이나 마지막 가격으로 채우면 상폐 손실이 지워진다).
    meta = {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                               time.localtime(time.time() + 9 * 3600)),
        "tickers": len(merged),
        "target_total": len(tickers),
        "fetched_now": len(fetched),
        "failed_now": len(failed),
        "failed_tickers": failed[:30],
        "last_bar": {k: (merged[k].get("c") or [[None]])[-1][0] for k in keys},
        "names": {k: merged[k].get("n") for k in keys},
        "note": ("소멸 종목 일봉. last_bar 이후는 데이터가 없다 — 백테스트에서 그 이후를 "
                 "조회하면 안 되고, 0 이나 마지막 가격으로 채우면 상폐 손실이 지워진다. "
                 "정리매매 소각을 어떻게 처리할지는 소비자가 명시적으로 정할 것."),
    }
    tmp = META_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    os.replace(tmp, META_PATH)
    return {"status": "ok", **{k: meta[k] for k in
                               ("tickers", "target_total", "fetched_now", "failed_now")}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    r = collect(a.limit, a.refresh)
    if r.get("status") != "ok":
        print(f"[kr_chart_delisted] {r.get('status')} — {r.get('hint','')}", file=sys.stderr)
        return 0
    print(f"[kr_chart_delisted] 보유 {r['tickers']}/{r['target_total']} · "
          f"신규 {r['fetched_now']} · 실패 {r['failed_now']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

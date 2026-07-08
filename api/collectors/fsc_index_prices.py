# -*- coding: utf-8 -*-
"""FscIndexPrices — 금융위원회_지수시세정보 (공공데이터포털 15094807) 지수 일봉 수집.

🚨 시세 재배포 컴플라이언스 (2026-07-08):
  현 지수 소스 = yfinance(Yahoo) → 재배포 권리 법률 큐 (project_rights_audit_2026_07_01).
  본 collector 의 source = 금융위 공공데이터 (data.go.kr/data/15094807) —
  주식시세(15094808, fsc_daily_prices.py)의 **형제 API**. "이용허락범위 제한 없음" + 무료.
  · T+1 영업일 지연 (전일 종가까지, 익영업일 13시 이후 갱신) — 당일/실시간 없음.
  · 공개 라벨 의무: "지수 일봉 · 전일까지 · 금융위 공공데이터 (T+1)". 실시간 = 네이버 link-out.
  · 엔드포인트 실호출 확정 2026-07-08 (GetMarketIndexInfoService/getStockMarketIndex,
    다른 후보 = API not found). 활용신청(15094807) 승인 후 필드/지수 커버리지 실 응답 검증 필요.

산출 = data/kr_index_daily.json — { _meta, indices: { <지수명>: {name, csf, c:[[basDt,종가,등락률],...]} } }
  · 지수는 ~수십 개(코스피/코스닥/코스피200/코스닥150/섹터/채권/파생) → 종목처럼 청킹 불필요, 단일 파일.
  · 종가·등락률만 유지 (스파크라인·추세용). O/H/L/거래량은 API 제공하나 지수 뷰엔 불필요 → 슬림.
  · 종목당 최근 KEEP_DAYS(120) 거래일.

키 = PUBLIC_DATA_API_KEY (fsc_daily_prices 와 공용). 활용신청은 데이터셋별 개별 필요.
트래픽 = daily 1콜(최신일 벌크) / backfill ~120콜 1회. 한도 10,000/일 여유.

사용 (🚨 파일 직접 실행 — `-m` 은 collectors/__init__ 이 dotenv 를 당겨 pip 필요):
  python api/collectors/fsc_index_prices.py --mode daily      # cron (평일, 주식차트 동승)
  python api/collectors/fsc_index_prices.py --mode backfill   # 최초 1회
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

BASE_URL = (
    "https://apis.data.go.kr/1160100/service/"
    "GetMarketIndexInfoService/getStockMarketIndex"
)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_PATH = os.path.join(_REPO_ROOT, "data", "kr_index_daily.json")
KEEP_DAYS = 120
_BULK_ROWS = 2000        # 전 지수 1일치 << 2000 (지수 수십 개 × 안전배수)
_REQ_TIMEOUT = 60
_KST = timezone(timedelta(hours=9))

# 응답 필드 후보 (FSC 지수 API 표준 스키마 — 활용신청 승인 후 실 응답으로 재확인).
#   idxNm=지수명, idxCsf=지수분류명, basDt=기준일자, clpr=종가, fltRt=등락률
_F_NAME = ("idxNm",)
_F_CSF = ("idxCsf",)
_F_DATE = ("basDt",)
_F_CLOSE = ("clpr",)
_F_FLT = ("fltRt",)


def _api_key() -> str:
    key = (os.environ.get("PUBLIC_DATA_API_KEY") or "").strip()
    if not key:
        env_path = os.path.join(_REPO_ROOT, ".env")
        if os.path.exists(env_path):
            for line in open(env_path, encoding="utf-8"):
                if line.startswith("PUBLIC_DATA_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return key


def _call(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    key = _api_key()
    if not key:
        print("[fsc_index] PUBLIC_DATA_API_KEY 없음", file=sys.stderr)
        return None
    qs = "serviceKey=" + urllib.parse.quote(key, safe="") + "&resultType=json"
    for k, v in params.items():
        qs += f"&{urllib.parse.quote(str(k))}={urllib.parse.quote(str(v))}"
    url = f"{BASE_URL}?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=_REQ_TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace")
        doc = json.loads(body)
        header = (doc.get("response") or {}).get("header") or {}
        if header.get("resultCode") != "00":
            print(f"[fsc_index] API 에러 {header}", file=sys.stderr)
            return None
        return (doc.get("response") or {}).get("body") or {}
    except Exception as e:
        # 'Forbidden'(활용신청 미승인)·게이트웨이 XML 봉투 = JSON 파싱 실패로 수렴
        print(f"[fsc_index] 호출 실패 {params}: {e}", file=sys.stderr)
        return None


def _pick(row: Dict[str, Any], keys) -> Any:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


def _to_int(v: Any) -> int:
    try:
        return int(float(str(v).replace(",", "")))
    except Exception:
        return 0


def _to_float(v: Any) -> Optional[float]:
    try:
        return round(float(str(v).replace(",", "")), 2)
    except Exception:
        return None


def fetch_day(bas_dt: str) -> List[Dict[str, Any]]:
    """1 거래일 전 지수 시세. 휴장일 = 빈 리스트."""
    body = _call({"numOfRows": _BULK_ROWS, "pageNo": 1, "basDt": bas_dt})
    if not body:
        return []
    items = (body.get("items") or {}).get("item") or []
    if isinstance(items, dict):  # 단일 항목이면 dict 로 옴
        items = [items]
    return items


def latest_available_date() -> Optional[str]:
    """API 최신 거래일 — 코스피 1행 (응답 basDt 내림차순 가정, 실 응답 검증 필요)."""
    body = _call({"numOfRows": 5, "pageNo": 1, "idxNm": "코스피"})
    items = ((body or {}).get("items") or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]
    dates = sorted((str(_pick(x, _F_DATE) or "") for x in items), reverse=True)
    return dates[0] if dates and dates[0] else None


def _load() -> Dict[str, Any]:
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d.get("indices"), dict):
                return d
    except Exception:
        pass
    return {"_meta": {}, "indices": {}}


def _append_rows(store: Dict[str, Any], rows: List[Dict[str, Any]]) -> int:
    indices = store["indices"]
    n = 0
    for row in rows:
        name = str(_pick(row, _F_NAME) or "").strip()
        if not name:
            continue
        bas = _to_int(_pick(row, _F_DATE))
        close = _to_float(_pick(row, _F_CLOSE))
        if bas <= 0 or close is None:
            continue
        flt = _to_float(_pick(row, _F_FLT))
        ent = indices.get(name)
        if ent is None:
            ent = {"name": name, "csf": str(_pick(row, _F_CSF) or ""), "c": []}
            indices[name] = ent
        pt = [bas, close, flt]
        arr = ent["c"]
        if arr and arr[-1][0] == bas:
            arr[-1] = pt            # 같은 날 재수집 = 교체 (멱등)
        elif arr and arr[-1][0] > bas:
            arr.append(pt)
            dedup: Dict[int, List] = {}
            for cd in sorted(arr, key=lambda x: x[0]):
                dedup[cd[0]] = cd
            ent["c"] = sorted(dedup.values(), key=lambda x: x[0])
        else:
            arr.append(pt)
        if len(ent["c"]) > KEEP_DAYS:
            ent["c"] = ent["c"][-KEEP_DAYS:]
        n += 1
    return n


def _save(store: Dict[str, Any], as_of: str) -> None:
    store["_meta"] = {
        "as_of": as_of,
        "count": len(store["indices"]),
        "keep_days": KEEP_DAYS,
        "source": "금융위원회_지수시세정보 (data.go.kr/data/15094807 · 이용허락범위 제한 없음)",
        "freshness": "T+1 EOD (전일 종가, 익영업일 13시 이후 갱신)",
        "generated_at": datetime.now(_KST).isoformat(timespec="seconds"),
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[fsc_index] saved as_of={as_of} indices={len(store['indices'])}")


def run_daily() -> bool:
    latest = latest_available_date()
    if not latest:
        print("[fsc_index] 최신 거래일 발견 실패 (활용신청 승인 확인)", file=sys.stderr)
        return False
    store = _load()
    cur = str((store.get("_meta") or {}).get("as_of") or "")
    if cur and cur >= latest:
        print(f"[fsc_index] 이미 최신 (as_of={cur})")
        return True
    rows = fetch_day(latest)
    if len(rows) < 5:
        print(f"[fsc_index] 벌크 이상 (rows={len(rows)}) — skip", file=sys.stderr)
        return False
    _append_rows(store, rows)
    _save(store, latest)
    return True


def run_backfill(target_days: int = KEEP_DAYS) -> bool:
    store: Dict[str, Any] = {"_meta": {}, "indices": {}}
    today = datetime.now(_KST).date()
    dates: List[str] = []
    d = today
    scanned = 0
    want = int(target_days * 1.15) + 5
    while len(dates) < want and scanned < int(target_days * 2.0) + 30:
        if d.weekday() < 5:
            dates.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
        scanned += 1
    got = 0
    for bas in reversed(dates):
        rows = fetch_day(bas)
        if rows:
            _append_rows(store, rows)
            got += 1
            if got % 20 == 0:
                print(f"[fsc_index] backfill {got} 거래일 (~{bas})")
        time.sleep(0.15)
    as_of = max(
        (ent["c"][-1][0] for ent in store["indices"].values() if ent["c"]),
        default=0,
    )
    if got < 30 or as_of <= 0:
        print(f"[fsc_index] backfill 불충분 (거래일 {got}) — abort", file=sys.stderr)
        return False
    _save(store, str(as_of))
    print(f"[fsc_index] backfill 완료 — 거래일 {got}, 지수 {len(store['indices'])}")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["daily", "backfill", "probe"], default="daily")
    ap.add_argument("--days", type=int, default=KEEP_DAYS)
    args = ap.parse_args()
    if args.mode == "probe":
        # 활용신청 승인 후 실 응답 스키마 확인용 — 지수 목록·필드 덤프
        rows = fetch_day(latest_available_date() or "")
        print(f"rows={len(rows)}")
        if rows:
            print("필드:", list(rows[0].keys()))
            names = sorted(set(str(_pick(r, _F_NAME) or "") for r in rows))
            print(f"지수 {len(names)}개:")
            for n in names:
                print("  -", n)
        sys.exit(0)
    ok = run_backfill(args.days) if args.mode == "backfill" else run_daily()
    sys.exit(0 if ok else 1)

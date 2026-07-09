# -*- coding: utf-8 -*-
"""FscDailyPrices — 금융위원회_주식시세정보 (공공데이터포털 1160100) 일봉 수집.

🚨 시세 재배포 컴플라이언스 (2026-07-04):
  KRX/KIS raw 시세 = 개인 비사업자 제3자 재배포 불가 → 공개 차트 발행 중단(2026-07-02).
  본 collector 의 source = 금융위 공공데이터 (data.go.kr/data/15094808) —
  **"이용허락범위 제한 없음" + 무료** (portal 원문, 2026-07-04 확인). 재배포 합법.
  · T+1 영업일 지연 (전일 종가까지, 익영업일 13시 이후 갱신) — 당일/실시간 없음.
  · 공개 라벨 의무: "일봉 · 전일까지 · 금융위 공공데이터 (T+1)". 실시간 = 네이버 link-out.
  · 4-카테고리 실호출 검증 완료 (KOSPI 대형/KOSDAQ/우선주/일자별 벌크 2,873종목).
  상세 = docs/MIGRATION_KRX_QUOTE_REDISTRIBUTION_2026_07.md.

산출 = data/kr_chart_daily/chunk_00..39.json (+ meta.json).
  · 청크 = int(단축코드, 36) % 40 — 코드에 'K' 포함 우선주 변형 대응 (base36).
    프론트(PublicLiveChart)도 동일 산식: parseInt(code, 36) % 40. 양측 검증 완료.
  · 종목당 최근 KEEP_DAYS(250) 거래일, 캔들 = [basDt, 시, 고, 저, 종, 거래량] 오름차순.
  · publish-data action 이 kr_chart_daily/ 디렉토리째 VERITY-data + Blob dual-write.

키 = PUBLIC_DATA_API_KEY (data.go.kr 일반 인증키, 기존 관세청/공정위 collector 와 공용).
  serviceKey 는 직접 quote (미인코딩 원본 재인코딩 깨짐 — ftc_group_equity 패턴).
트래픽 = daily 2콜 (최신일 발견 1 + 벌크 1) / backfill ~5-600콜 1회. 한도 10,000/일 여유.

사용 (🚨 파일 직접 실행 — `-m` 은 collectors/__init__ 이 dotenv 를 당겨 pip 필요):
  python api/collectors/fsc_daily_prices.py --mode daily      # cron (평일 14:23 KST)
  python api/collectors/fsc_daily_prices.py --mode backfill   # 최초 1회 (250거래일)
"""

from __future__ import annotations

import argparse
import concurrent.futures
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
    "GetStockSecuritiesInfoService/getStockPriceInfo"
)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(_REPO_ROOT, "data", "kr_chart_daily")
HOT_PATH = os.path.join(_REPO_ROOT, "data", "hot_stock.json")
N_CHUNKS = 40

# 거래대금 상위 = "그날 핫한 종목" 후보. ETF/ETN 제외(개별 종목만) — mrktCtg 에 ETF 플래그 없어 발행사 prefix 로 배제.
_ETF_PREFIXES = ("KODEX", "TIGER", "KBSTAR", "ARIRANG", "ACE", "SOL", "PLUS", "HANARO",
                 "KOSEF", "TIMEFOLIO", "RISE", "WOORI", "히어로즈", "마이다스", "파워",
                 "1Q", "BNK", "FOCUS", "KCGI", "TREX", "KIWOOM")
KEEP_DAYS = 250          # ~1년 거래일 (52주 고저 계산 가능)
_BULK_ROWS = 5000        # 전 종목 ~2,900 → 1콜 (실측 2026-07-04: 2,873건 0.3s)
_REQ_TIMEOUT = 60
_KST = timezone(timedelta(hours=9))


def _api_key() -> str:
    key = (os.environ.get("PUBLIC_DATA_API_KEY") or "").strip()
    if not key:
        # 로컬 실행 fallback — .env 직접 파싱 (workflow 는 secrets env 주입)
        env_path = os.path.join(_REPO_ROOT, ".env")
        if os.path.exists(env_path):
            for line in open(env_path, encoding="utf-8"):
                if line.startswith("PUBLIC_DATA_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return key


def _call(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """단일 호출 → response.body dict. 게이트웨이/키 에러 = 로깅 후 None."""
    key = _api_key()
    if not key:
        print("[fsc_daily_prices] PUBLIC_DATA_API_KEY 없음", file=sys.stderr)
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
            print(f"[fsc_daily_prices] API 에러 {header}", file=sys.stderr)
            return None
        return (doc.get("response") or {}).get("body") or {}
    except Exception as e:  # 게이트웨이 XML 봉투(키/쿼터) 포함 — JSON 파싱 실패로 수렴
        print(f"[fsc_daily_prices] 호출 실패 {params}: {e}", file=sys.stderr)
        return None


def fetch_day(bas_dt: str) -> List[Dict[str, Any]]:
    """1 거래일 전 종목 시세. 휴장일 = 빈 리스트."""
    body = _call({"numOfRows": _BULK_ROWS, "pageNo": 1, "basDt": bas_dt})
    if not body:
        return []
    items = (body.get("items") or {}).get("item") or []
    total = int(body.get("totalCount") or 0)
    # 페이지 초과 방어 — 상장 종목 폭증 시 paginate (현 2,873 << 5,000)
    page = 2
    while len(items) < total and page <= 3:
        more = _call({"numOfRows": _BULK_ROWS, "pageNo": page, "basDt": bas_dt})
        extra = ((more or {}).get("items") or {}).get("item") or []
        if not extra:
            break
        items.extend(extra)
        page += 1
    return items


def latest_available_date() -> Optional[str]:
    """API 가 보유한 최신 거래일 (삼성전자 최신 1행 — 응답 basDt 내림차순 실측 확인)."""
    body = _call({"numOfRows": 1, "pageNo": 1, "likeSrtnCd": "005930"})
    items = ((body or {}).get("items") or {}).get("item") or []
    return items[0].get("basDt") if items else None


def _chunk_idx(code: str) -> int:
    return int(code, 36) % N_CHUNKS


def _to_int(v: Any) -> int:
    try:
        return int(float(str(v).replace(",", "")))
    except Exception:
        return 0


def _row_to_candle(row: Dict[str, Any]) -> Optional[List[int]]:
    bas = _to_int(row.get("basDt"))
    c = _to_int(row.get("clpr"))
    if bas <= 0 or c <= 0:
        return None
    o, h, l = _to_int(row.get("mkp")), _to_int(row.get("hipr")), _to_int(row.get("lopr"))
    # 거래 성립 없는 날(시/고/저 0) = 종가 flat 캔들
    if o <= 0 or h <= 0 or l <= 0:
        o = h = l = c
    return [bas, o, h, l, c, _to_int(row.get("trqu"))]


def _load_chunks() -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    for i in range(N_CHUNKS):
        p = os.path.join(OUT_DIR, f"chunk_{i:02d}.json")
        try:
            with open(p, encoding="utf-8") as f:
                chunks.append(json.load(f))
        except Exception:
            chunks.append({"as_of": "", "stocks": {}})
    return chunks


def _save_chunks(chunks: List[Dict[str, Any]], as_of: str) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    n_stocks = 0
    for i, ch in enumerate(chunks):
        ch["as_of"] = as_of
        n_stocks += len(ch["stocks"])
        p = os.path.join(OUT_DIR, f"chunk_{i:02d}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(ch, f, ensure_ascii=False, separators=(",", ":"))
    meta = {
        "as_of": as_of,
        "stocks": n_stocks,
        "chunks": N_CHUNKS,
        "keep_days": KEEP_DAYS,
        "source": "금융위원회_주식시세정보 (data.go.kr/data/15094808 · 이용허락범위 제한 없음)",
        "updated_at": datetime.now(_KST).isoformat(timespec="seconds"),
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"[fsc_daily_prices] saved as_of={as_of} stocks={n_stocks}")


def _append_rows(chunks: List[Dict[str, Any]], rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        code = str(row.get("srtnCd") or "").strip().upper()
        if len(code) != 6:
            continue
        candle = _row_to_candle(row)
        if candle is None:
            continue
        try:
            idx = _chunk_idx(code)
        except ValueError:
            continue
        stocks = chunks[idx]["stocks"]
        ent = stocks.get(code)
        if ent is None:
            ent = {"n": str(row.get("itmsNm") or code), "m": str(row.get("mrktCtg") or ""), "c": []}
            stocks[code] = ent
        ent["n"] = str(row.get("itmsNm") or ent["n"])  # 종목명 변경 추종
        arr = ent["c"]
        if arr and arr[-1][0] == candle[0]:
            arr[-1] = candle          # 같은 날 재수집 = 교체 (멱등)
        elif arr and arr[-1][0] > candle[0]:
            # 과거일 삽입 (backfill 순서 어긋남 방어) — 정렬 삽입
            arr.append(candle)
            arr.sort(key=lambda x: x[0])
            # 같은 날 중복 제거 (뒤 우선)
            dedup: Dict[int, List[int]] = {}
            for cd in arr:
                dedup[cd[0]] = cd
            ent["c"] = sorted(dedup.values(), key=lambda x: x[0])
        else:
            arr.append(candle)
        if len(ent["c"]) > KEEP_DAYS:
            ent["c"] = ent["c"][-KEEP_DAYS:]


def _is_etf_like(name: str) -> bool:
    n = str(name or "").upper()
    if any(n.startswith(p) for p in _ETF_PREFIXES):
        return True
    return ("레버리지" in name) or ("인버스" in name) or ("선물" in name) or ("ETN" in n)


def emit_hot_stock(rows: List[Dict[str, Any]], as_of: str) -> None:
    """전 종목 rows → 거래대금(trPrc) 상위 개별종목 = '그날 핫한 종목'.
    source = 금융위 공공데이터(공공누리, 재배포 합법 — KRX OpenAPI 와 무관). EOD(전 거래일) 사실.
    """
    cand: List[Dict[str, Any]] = []
    for r in rows:
        mk = str(r.get("mrktCtg") or "")
        if mk not in ("KOSPI", "KOSDAQ"):
            continue
        cd = str(r.get("srtnCd") or "").strip().upper()
        nm = str(r.get("itmsNm") or "")
        if len(cd) != 6 or _is_etf_like(nm):
            continue
        tp = _to_int(r.get("trPrc"))
        if tp <= 0:
            continue
        fl = None
        try:
            fl = round(float(str(r.get("fltRt")).replace(",", "")), 2)
        except (TypeError, ValueError):
            fl = None
        cand.append({"ticker": cd, "name": nm, "market": mk, "trPrc": tp, "fltRt": fl})
    if not cand:
        print("[fsc_daily_prices] hot_stock 후보 0 — skip", file=sys.stderr)
        return
    cand.sort(key=lambda x: -x["trPrc"])
    top = cand[:5]
    hot = {"ticker": top[0]["ticker"], "name": top[0]["name"], "market": top[0]["market"],
           "label": "거래대금 1위"}
    doc = {
        "_meta": {
            "as_of": as_of,
            "source": "금융위원회_주식시세정보 (data.go.kr/data/15094808 · 거래대금 상위 · 이용허락범위 제한 없음)",
            "basis": "직전 거래일 거래대금(trPrc) 순 — 사실. 추천 아님.",
            "generated_at": datetime.now(_KST).isoformat(timespec="seconds"),
        },
        "hot": hot,
        "top": top,
    }
    with open(HOT_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[fsc_daily_prices] hot_stock as_of={as_of} → {hot['name']}({hot['ticker']}) "
          f"거래대금={top[0]['trPrc'] / 1e8:.0f}억")


def run_daily() -> bool:
    latest = latest_available_date()
    if not latest:
        print("[fsc_daily_prices] 최신 거래일 발견 실패", file=sys.stderr)
        return False
    chunks = _load_chunks()
    cur = max((ch.get("as_of") or "") for ch in chunks)
    if cur and cur >= latest:
        print(f"[fsc_daily_prices] 이미 최신 (as_of={cur})")
        return True
    rows = fetch_day(latest)
    if len(rows) < 500:  # 전 종목 벌크가 이상 축소 = API 이상 → 기존 데이터 보존
        print(f"[fsc_daily_prices] 벌크 이상 (rows={len(rows)}) — skip", file=sys.stderr)
        return False
    _append_rows(chunks, rows)
    _save_chunks(chunks, latest)
    emit_hot_stock(rows, latest)  # 거래대금 1위 = 리포트 콜드 랜딩 디폴트
    return True


def run_backfill(target_days: int = KEEP_DAYS) -> bool:
    """과거 → 현재 순으로 target_days 거래일 수집 후 청크 재구축."""
    chunks: List[Dict[str, Any]] = [{"as_of": "", "stocks": {}} for _ in range(N_CHUNKS)]
    today = datetime.now(_KST).date()
    # 주중일 중 휴장일 ~8% — 여유 계수(×1.15)로 스캔해 목표 거래일 확보 후 KEEP_DAYS 로 trim
    dates: List[str] = []
    d = today
    scanned = 0
    want_weekdays = int(target_days * 1.15) + 5
    while len(dates) < want_weekdays and scanned < int(target_days * 2.0) + 30:
        if d.weekday() < 5:
            dates.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
        scanned += 1
    got = 0
    for bas in reversed(dates):  # 과거 → 현재 (append 경로 최적)
        rows = fetch_day(bas)
        if rows:
            _append_rows(chunks, rows)
            got += 1
            if got % 20 == 0:
                print(f"[fsc_daily_prices] backfill {got} 거래일 (~{bas})")
        time.sleep(0.15)  # 공용 키 쿼터 예의
    as_of = max(
        (ent["c"][-1][0] for ch in chunks for ent in ch["stocks"].values() if ent["c"]),
        default=0,
    )
    if got < 100 or as_of <= 0:
        print(f"[fsc_daily_prices] backfill 불충분 (거래일 {got}) — abort", file=sys.stderr)
        return False
    _save_chunks(chunks, str(as_of))
    print(f"[fsc_daily_prices] backfill 완료 — 거래일 {got}")
    return True


def run_history(out_dir: str) -> bool:
    """전 종목 전체 히스토리 (2020-01-02~, API 보유 전량) → per-ticker JSON.

    소비 = PublicLiveChart MAX(전체) 탭 lazy fetch. git 비커밋 — Blob 직행
    (repo 165MB 부담 회피). 월 1회 갱신 (최근 250일은 일일 청크가 fresh 담당,
    MAX 뷰는 client 에서 히스토리+최근 청크 병합 → 히스토리 파일 약간 stale 무해).
    유니버스 = data/kr_chart_daily/ 청크의 종목 목록. 종목당 1콜 (numOfRows=5000
    ≥ 보유 1,595행), ~2,992콜 (한도 10,000/일 내).
    """
    chunks = _load_chunks()
    tickers = sorted(code for ch in chunks for code in ch["stocks"].keys())
    if len(tickers) < 500:
        print(f"[fsc_daily_prices] 유니버스 부족 ({len(tickers)}) — 청크 먼저 backfill", file=sys.stderr)
        return False
    dest = os.path.join(out_dir, "kr_chart_history")
    os.makedirs(dest, exist_ok=True)

    # 🚨 병렬 8스레드 (2026-07-04 N=1 audit 학습) — GH 러너(해외)→data.go.kr RTT ~1.2s/콜.
    #   직렬 2,992콜 = 60분+ → timeout 90분 초과 취소. 8병렬 ≈ 8분 (~8tps, 게이트웨이 한도 내).
    def _one(code: str) -> bool:
        body = _call({"numOfRows": _BULK_ROWS, "pageNo": 1, "likeSrtnCd": code})
        items = ((body or {}).get("items") or {}).get("item") or []
        candles: List[List[int]] = []
        name, mkt = code, ""
        for row in items:  # like 매칭 방어 — 정확 코드만
            if str(row.get("srtnCd") or "").strip().upper() != code:
                continue
            cd = _row_to_candle(row)
            if cd:
                candles.append(cd)
            name = str(row.get("itmsNm") or name)
            mkt = str(row.get("mrktCtg") or mkt)
        if len(candles) < 2:
            return False
        candles.sort(key=lambda x: x[0])
        with open(os.path.join(dest, f"{code}.json"), "w", encoding="utf-8") as f:
            json.dump({"t": code, "n": name, "m": mkt, "c": candles}, f, ensure_ascii=False, separators=(",", ":"))
        return True

    ok_n = 0
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for ok in ex.map(_one, tickers):
            done += 1
            if ok:
                ok_n += 1
            if done % 200 == 0:
                print(f"[fsc_daily_prices] history {done}/{len(tickers)} (ok {ok_n})", flush=True)
    print(f"[fsc_daily_prices] history 완료 — {ok_n}/{len(tickers)} 종목 → {dest}", flush=True)
    return ok_n >= 500


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["daily", "backfill", "history"], default="daily")
    ap.add_argument("--days", type=int, default=KEEP_DAYS)
    ap.add_argument("--out", default="_history_dist", help="history 모드 산출 디렉토리 (git 비커밋)")
    args = ap.parse_args()
    if args.mode == "backfill":
        ok = run_backfill(args.days)
    elif args.mode == "history":
        ok = run_history(args.out)
    else:
        ok = run_daily()
    sys.exit(0 if ok else 1)

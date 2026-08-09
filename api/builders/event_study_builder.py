"""
event_study_builder — 종목별 "과거 공시 패턴" 이벤트 스터디 (AlphaNest 공개 터미널).

목적(PM 결정 2026-06-25): 인스타에서 본 "과거 데이터 비교" 류 — 우리는 19년치 가격레이크
(~/VERITY_data_lake/kr_prices.duckdb, OHLCV 2,477종목 2007~) + DART 11년 공시이력으로 더 깊게.
LLM·네이버가 못 하는 자기 데이터 자산 (RULE 6 escape — 자기 trail 위, narrative 아님).

산출: 종목별 **자기 과거** 카탈리스트 공시(유상증자/자기주식취득·처분/전환사채/합병/감자/공급계약 등)
       → 각 발생 당시 종가 대비 +1d/+5d/+20d/+60d 거래일 forward return.

🚨 RULE 7 / PM 결정 2026-06-25:
  - **종목별 자기 과거만** 노출 (종목 간 평균·집계·랭킹 0). 과거 사실 비교지 예측·신호 아님.
  - 종목 간 집계를 안 하므로 생존편향 비해당(그 종목 자기 실제 이력). raw 주가 변화(시장 포함) = 사실.
  - count(N)·날짜는 사실의 일부로 노출. "예측 아님" 류 경고는 PM 결정으로 미부착(사이트 공통 푸터 톤만).
  - 점수·등급·추천 0. Brain 등 결정 경로 미연결(관측 표시 only).

입력:
  data/dart_catalyst_backfill.jsonl + data/dart_catalyst_alerts.jsonl (공시 이벤트, ticker/report_nm/rcept_dt)
  ~/VERITY_data_lake/kr_prices.duckdb (ohlcv: ticker,date,close)

출력: data/event_study.json  { _meta, stocks: { TICKER: { name, events: [ {type,tone,count,occurrences:[...]} ] } } }
publish: public_disclosure_feed_builder 와 동일 family — publish-data action 파일 목록 등재 필요.
RULE 8: 신규 builder → N=2 실 cron 결과 audit 의무.
"""
from __future__ import annotations

import bisect
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.config import DATA_DIR, now_kst  # noqa: E402

KR_LAKE_PATH = os.path.expanduser("~/VERITY_data_lake/kr_prices.duckdb")
# 🚨 폴백 전용 (2026-08-09~). US 정본은 아래 Blob 산출물 — 경위는 _load_us_precomputed 주석.
US_LAKE_PATH = os.path.expanduser("~/VERITY_data_lake/us_prices.duckdb")
US_EVENT_STUDY_BLOB = os.environ.get(
    "US_EVENT_STUDY_URL",
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_chart_history/_event_study.json",
)
BACKFILL_PATH = os.path.join(DATA_DIR, "dart_catalyst_backfill.jsonl")
ALERTS_PATH = os.path.join(DATA_DIR, "dart_catalyst_alerts.jsonl")
US_CAT_PATH = os.path.join(DATA_DIR, "us_catalyst_backfill.jsonl")  # SEC 8-K (label/tone 사전분류 by backfill_us_catalyst)
OUTPUT_PATH = os.path.join(DATA_DIR, "event_study.json")

# forward return 윈도우 (거래일 오프셋). 이벤트 당일(D, rcept_dt 이상 첫 거래일) 종가 기준.
WINDOWS = {"ret_1d": 1, "ret_5d": 5, "ret_20d": 20, "ret_60d": 60}
# 유형별 노출 발생 상한 (UI·payload). 초과분은 count·truncated 로 표기(은닉 방지).
MAX_OCC = 12

# 공시 유형 매핑 — report_nm 에 키워드 포함 시 분류. tone = PublicDisclosureFeed 와 동일 의미축(희석/우호/주의/중립).
# 순서 = 우선순위(먼저 매칭되면 확정). 노이즈(임원소유상황/의결권대리/약식/증권발행실적/투자설명서 등)는 매핑 없음 → 제외.
EVENT_TYPES: List[Tuple[str, str, List[str]]] = [
    ("유상증자", "dilution", ["유상증자"]),
    ("전환사채 발행", "dilution", ["전환사채권발행"]),
    ("신주인수권부사채 발행", "dilution", ["신주인수권부사채권발행"]),
    ("교환사채 발행", "dilution", ["교환사채권발행"]),
    ("자기주식 처분", "dilution", ["자기주식처분"]),
    ("자기주식 취득", "favor", ["자기주식취득결정", "자기주식취득신탁계약체결"]),
    ("무상증자", "favor", ["무상증자"]),
    ("공급계약", "favor", ["단일판매", "공급계약"]),
    ("감자", "alert", ["감자결정"]),
    ("회사 합병", "neutral", ["회사합병결정", "합병결정"]),
    ("회사 분할", "neutral", ["회사분할결정", "분할결정"]),
    ("타법인 주식 양수", "neutral", ["타법인주식및출자증권양수"]),
    ("타법인 주식 양도", "neutral", ["타법인주식및출자증권양도"]),
    ("유형자산 양수", "neutral", ["유형자산양수"]),
    ("유형자산 양도", "neutral", ["유형자산양도"]),
]


def _classify(report_nm: str) -> Optional[Tuple[str, str]]:
    """report_nm → (유형 라벨, tone) 또는 None(미분류 노이즈)."""
    nm = re.sub(r"^\[.*?\]", "", report_nm or "")  # [기재정정] 등 접두 제거
    for label, tone, kws in EVENT_TYPES:
        if any(k in nm for k in kws):
            return label, tone
    return None


def _load_events() -> List[Dict[str, Any]]:
    """backfill + alerts 병합, 분류 가능한 카탈리스트만. (ticker, rcept_dt, label, tone, report_nm) 중복 제거(rcept_no)."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for path in (BACKFILL_PATH, ALERTS_PATH):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rno = r.get("rcept_no")
                if rno in seen:
                    continue
                cls = _classify(r.get("report_nm", ""))
                if not cls:
                    continue
                tic = str(r.get("ticker") or "").strip()
                dt = str(r.get("rcept_dt") or "").strip()
                if not (tic and len(dt) == 8 and dt.isdigit()):
                    continue
                seen.add(rno)
                out.append({
                    "ticker": tic,
                    "name": r.get("name") or "",
                    "date": f"{dt[:4]}-{dt[4:6]}-{dt[6:]}",
                    "label": cls[0],
                    "tone": cls[1],
                    "report_nm": re.sub(r"^\[.*?\]", "", r.get("report_nm", "")),
                })
    return out


def _load_us_events() -> List[Dict[str, Any]]:
    """us_catalyst_backfill.jsonl (SEC 8-K, label/tone 사전분류) → 이벤트 dict. accession dedup."""
    seen = set()
    out: List[Dict[str, Any]] = []
    if not os.path.exists(US_CAT_PATH):
        return out
    with open(US_CAT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            acc = r.get("acc")
            if acc in seen:
                continue
            tic = str(r.get("ticker") or "").strip().upper()
            dt = str(r.get("date") or "").strip()
            if not (tic and r.get("label") and len(dt) == 10):
                continue
            seen.add(acc)
            out.append({
                "ticker": tic,
                "name": r.get("name") or "",
                "date": dt,
                "label": r.get("label"),
                "tone": r.get("tone") or "neutral",
                "report_nm": r.get("label"),  # US = 라벨 자체(8-K item 분류)
            })
    return out


def _load_price_series(tickers: List[str], lake_path: str) -> Dict[str, Tuple[List[str], List[float]]]:
    """레이크에서 종목별 (date 문자열 정렬 리스트, close 리스트). graceful — 부재 시 {}."""
    if not os.path.exists(lake_path) or not tickers:
        return {}
    try:
        import duckdb
    except Exception:  # noqa: BLE001
        return {}
    out: Dict[str, Tuple[List[str], List[float]]] = {}
    try:
        con = duckdb.connect(lake_path, read_only=True)
        try:
            rows = con.execute(
                "SELECT ticker, CAST(date AS VARCHAR), close FROM ohlcv WHERE ticker IN "
                f"({','.join('?' * len(tickers))}) ORDER BY ticker, date",
                tickers,
            ).fetchall()
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return {}
    for tic, d, close in rows:
        if close is None or d is None:
            continue
        bucket = out.setdefault(str(tic), ([], []))
        bucket[0].append(str(d)[:10])
        bucket[1].append(float(close))
    return out


def _forward_returns(dates: List[str], closes: List[float], event_date: str) -> Optional[Dict[str, Any]]:
    """이벤트일 이상 첫 거래일(D) 종가 기준 forward return(%). D 미존재/가격<=0 시 None."""
    idx = bisect.bisect_left(dates, event_date)
    if idx >= len(dates):
        return None  # 이벤트가 가격 이력보다 미래
    base = closes[idx]
    if base <= 0:
        return None
    rec: Dict[str, Any] = {"base_date": dates[idx]}
    for key, off in WINDOWS.items():
        j = idx + off
        rec[key] = round((closes[j] / base - 1.0) * 100.0, 1) if j < len(dates) and closes[j] > 0 else None
    return rec


def _load_price_series_history(
    tickers: List[str], hist_dir: str
) -> Dict[str, Tuple[List[str], List[float]]]:
    """us_chart_history 레이크(티커별 JSON) → {ticker: (날짜, 종가)}.

    🚨 2026-08-09 — US 가격 출처를 로컬 duckdb 에서 이 레이크로 옮기기 위한 로더.
    duckdb 쪽은 수동 백필이라 2026-06-26 에 43일 멈춰 있었고(스케줄 부재), 종목도 1,505 뿐이었다.
    이 레이크는 CI 가 만들고(5,188종·97.4%) 워크플로 자체가 감시 대상이라 조용히 얼지 않는다.
    파일 스키마 = {"t": ticker, "c": [[yyyymmdd, o, h, l, close, vol], ...]} (날짜 오름차순).
    """
    out: Dict[str, Tuple[List[str], List[float]]] = {}
    if not os.path.isdir(hist_dir):
        return out
    for tic in tickers:
        path = os.path.join(hist_dir, f"{tic}.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        dates: List[str] = []
        closes: List[float] = []
        for row in doc.get("c") or []:
            try:
                d, c = int(row[0]), float(row[4])
            except (IndexError, TypeError, ValueError):
                continue
            if c <= 0:
                continue
            s = str(d)
            # 이벤트 날짜가 'YYYY-MM-DD' 라 같은 자로 맞춘다(bisect 는 문자열 비교).
            dates.append(f"{s[:4]}-{s[4:6]}-{s[6:8]}")
            closes.append(c)
        if dates:
            out[tic] = (dates, closes)
    return out


def _build_market(
    events: List[Dict[str, Any]],
    lake_path: str = "",
    prices: Optional[Dict[str, Tuple[List[str], List[float]]]] = None,
) -> Dict[str, Any]:
    """이벤트 + 가격 → {ticker: {name, events:[...]}}. KR/US 공통. ticker 키 충돌 0(KR 숫자/US 영문).

    prices 를 직접 주면 그걸 쓰고, 없으면 duckdb 레이크에서 읽는다(KR 경로).
    """
    tickers = sorted({e["ticker"] for e in events})
    if prices is None:
        prices = _load_price_series(tickers, lake_path)

    stocks: Dict[str, Any] = {}
    for e in events:
        series = prices.get(e["ticker"])
        if not series:
            continue
        fwd = _forward_returns(series[0], series[1], e["date"])
        if fwd is None:
            continue
        st = stocks.setdefault(e["ticker"], {"name": e["name"], "_by_type": {}})
        if e["name"] and not st["name"]:
            st["name"] = e["name"]
        grp = st["_by_type"].setdefault(e["label"], {"type": e["label"], "tone": e["tone"], "occurrences": []})
        grp["occurrences"].append({"date": e["date"], "report_nm": e["report_nm"], **fwd})

    out: Dict[str, Any] = {}
    for tic, st in stocks.items():
        ev_list = []
        for grp in st["_by_type"].values():
            # 같은 날 복수 공시는 forward return 동일 → 날짜당 1행 dedup.
            by_date: Dict[str, Any] = {}
            for o in grp["occurrences"]:
                by_date.setdefault(o["date"], o)
            occ = sorted(by_date.values(), key=lambda o: o["date"], reverse=True)
            grp["count"] = len(occ)
            grp["occurrences"] = occ[:MAX_OCC]
            if len(occ) > MAX_OCC:
                grp["truncated"] = len(occ) - MAX_OCC
            ev_list.append(grp)
        if not ev_list:
            continue
        ev_list.sort(key=lambda g: g["occurrences"][0]["date"], reverse=True)
        out[tic] = {"name": st["name"], "events": ev_list}
    return out


def _load_us_precomputed() -> Tuple[Dict[str, Any], str]:
    """CI 가 만든 US 이벤트스터디 반쪽을 가져온다 → (stocks, 출처 설명).

    🚨 2026-08-09 구조 변경. 이전에는 US 도 로컬 duckdb(`us_prices.duckdb`)에서 만들었는데
      그 레이크는 **갱신 스케줄이 없어** 2026-06-26 에 멈춘 채 43일을 갔다. 백필 스크립트가
      "이미 있는 ticker = skip" 이라 날짜가 늘지 않는 구조였고, 그 위에서 이벤트스터디가
      계속 돌았다 = 측정이 조용히 과거에 고정. 종목도 1,505(S&P1500)뿐이었다.
      이제 US 반쪽은 `us_chart_history` 워크플로(월 1회·5,188종·97.4%)가 CI 에서 만들어
      Blob 에 올리고, 여기서는 내려받아 쓴다. 워크플로 자체가 신선도 감시 대상이라
      조용히 얼지 않는다.

    캐시는 레포 밖(~/VERITY_data_lake)에 둔다 — 12MB 급 파일이라 커밋하면 레포가 붓는다.
    조건부 GET(ETag)으로 변경 없으면 304 라 월 1회만 실제로 내려받는다.
    """
    cache = os.path.expanduser("~/VERITY_data_lake/us_event_study.json")
    etag_path = cache + ".etag"
    url = f"{US_EVENT_STUDY_BLOB}"

    headers = {}
    if os.path.exists(cache) and os.path.exists(etag_path):
        try:
            headers["If-None-Match"] = open(etag_path, encoding="utf-8").read().strip()
        except OSError:
            pass
    try:
        import requests
        r = requests.get(url, headers=headers, timeout=120)
        if r.status_code == 200 and r.content:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            tmp = cache + ".tmp"
            with open(tmp, "wb") as f:
                f.write(r.content)
            os.replace(tmp, cache)
            if r.headers.get("ETag"):
                with open(etag_path, "w", encoding="utf-8") as f:
                    f.write(r.headers["ETag"])
            print(f"[event_study] US 반쪽 내려받음 ({len(r.content) / 1e6:.1f}MB)")
        elif r.status_code == 304:
            print("[event_study] US 반쪽 캐시 최신(304)")
        else:
            print(f"[event_study] US 반쪽 받기 실패 HTTP {r.status_code} — 캐시/폴백 사용")
    except Exception as e:  # noqa: BLE001 — 네트워크 실패는 치명 아님(캐시·폴백 존재)
        print(f"[event_study] US 반쪽 받기 실패({type(e).__name__}) — 캐시/폴백 사용")

    if not os.path.exists(cache):
        return {}, ""
    try:
        with open(cache, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}, ""
    stocks = doc.get("stocks") or {}
    as_of = (doc.get("_meta") or {}).get("generated_at", "")[:10]
    return stocks, f"us_chart_history 레이크(CI 산출 {as_of})"


def build() -> Dict[str, Any]:
    kr = _build_market(_load_events(), KR_LAKE_PATH)

    # US = CI 산출본 우선. 없으면 옛 로컬 duckdb 로 폴백(전환기·오프라인 안전).
    us, us_src = _load_us_precomputed()
    if not us:
        us = _build_market(_load_us_events(), US_LAKE_PATH)
        us_src = "us_prices.duckdb 폴백(로컬·수동 갱신)"
    out_stocks = {**kr, **us}  # ticker 키 충돌 0 (KR 숫자코드 / US 영문)

    total_occ = sum(len(g["occurrences"]) for s in out_stocks.values() for g in s["events"])
    feed = {
        "_meta": {
            "generated_at": now_kst().isoformat(),
            "source": ("KR=DART 공시이력(2015~)+kr_prices · "
                       f"US=SEC 8-K(2015~)+{us_src or 'us_prices'}. "
                       "forward return(거래일 +1/+5/+20/+60)."),
            "us_price_source": us_src or "unknown",
            "note": "종목별 자기 과거 카탈리스트 공시 당시 주가 변화. 종목 간 집계 없음 — 과거 사실 비교용(예측·신호 아님).",
            "windows": WINDOWS,
            "stock_count": len(out_stocks),
            "kr_count": len(kr),
            "us_count": len(us),
            "occurrence_count": total_occ,
        },
        "stocks": out_stocks,
    }
    return feed


def main() -> None:
    feed = build()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)
    m = feed["_meta"]
    print(f"[event_study] {m['stock_count']} 종목 (KR {m.get('kr_count')}/US {m.get('us_count')}) · {m['occurrence_count']} 이벤트 -> {os.path.relpath(OUTPUT_PATH, os.path.dirname(DATA_DIR))}")


if __name__ == "__main__":
    main()

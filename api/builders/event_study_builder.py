"""
event_study_builder — 종목별 "과거 공시 패턴" 이벤트 스터디 (골든구스 공개 터미널).

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
US_LAKE_PATH = os.path.expanduser("~/VERITY_data_lake/us_prices.duckdb")
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


def _build_market(events: List[Dict[str, Any]], lake_path: str) -> Dict[str, Any]:
    """이벤트 + 레이크 → {ticker: {name, events:[...]}}. KR/US 공통. ticker 키 충돌 0(KR 숫자/US 영문)."""
    tickers = sorted({e["ticker"] for e in events})
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


def build() -> Dict[str, Any]:
    kr = _build_market(_load_events(), KR_LAKE_PATH)
    us = _build_market(_load_us_events(), US_LAKE_PATH)
    out_stocks = {**kr, **us}  # ticker 키 충돌 0 (KR 숫자코드 / US 영문)

    total_occ = sum(len(g["occurrences"]) for s in out_stocks.values() for g in s["events"])
    feed = {
        "_meta": {
            "generated_at": now_kst().isoformat(),
            "source": "KR=DART 공시이력(2015~)+kr_prices · US=SEC 8-K(2015~)+us_prices. forward return(거래일 +1/+5/+20/+60).",
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

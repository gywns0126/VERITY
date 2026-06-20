#!/usr/bin/env python3
"""
smallcap_corner_daily.py — 소형주 코너 검증 trail 로컬 일일 runner (③ 로컬 cron).

2026-06-20 신설. 레이크 = 로컬 자산(repo 밖) → 코너 enrichment+trail 생성은 **로컬 전용**.
이 runner 가 그 로컬 파이프라인을 1회 수행 → 출력(trail/ic_history)만 커밋.

체인 (graceful, 단계 실패 = 다음 단계로 — 부분 진행):
  1. 레이크 증분 top-up — 코너 ticker 별 last_date+1 ~ today OHLCV 추가 (momentum 신선도).
  2. trail 생성 — enrich(quant 팩터) → generate_smallcap_predictions → SMALLCAP_PATH append.
  3. 채점 — score_smallcap_corner (eval 도래분 실현 채점 → ic_history).
  4. 커밋/푸시 — trail + ic_history (append-only 검증 자산). brain_input=False, 점수 held(RULE 7).

관측 only — 메인 VAMS/Brain/2027 win condition 무접촉. cron 활성 = 로컬(launchd/crontab), CI 아님.
usage: python3 scripts/kr/smallcap_corner_daily.py [--no-push] [--no-lake-update]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from api.config import DATA_DIR, now_kst

LAKE_PATH = os.path.expanduser("~/VERITY_data_lake/kr_prices.duckdb")
_MARKET_MAP = {"KQ": "KOSDAQ", "KS": "KOSPI", "KOSDAQ": "KOSDAQ", "KOSPI": "KOSPI"}


def _log(msg: str) -> None:
    sys.stdout.write(f"[smallcap-daily] {msg}\n")
    sys.stdout.flush()


def _corner_stocks():
    path = os.path.join(DATA_DIR, "smallcap_corner.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("stocks") or []


def update_lake_incremental(stocks, sleep: float = 0.35) -> int:
    """코너 ticker 별 last_date+1 ~ today OHLCV 추가 (graceful). 추가 row 수 반환."""
    if not os.path.exists(LAKE_PATH):
        _log(f"레이크 부재 {LAKE_PATH} — 증분 skip")
        return 0
    try:
        import duckdb
        from pykrx import stock as pk
    except Exception as e:  # noqa: BLE001
        _log(f"duckdb/pykrx 부재 — 증분 skip ({type(e).__name__})")
        return 0

    con = duckdb.connect(LAKE_PATH, read_only=False)
    today = now_kst().date()
    today_s = today.strftime("%Y%m%d")
    # ticker → 레이크 최신 date
    last_map = {r[0]: r[1] for r in con.execute("SELECT ticker, MAX(date) FROM ohlcv GROUP BY ticker").fetchall()}
    added = 0
    for s in stocks:
        tic = str(s.get("ticker") or "")
        if not tic:
            continue
        last = last_map.get(tic)
        if last is not None and last >= today:
            continue  # 이미 최신
        start = (last.strftime("%Y%m%d") if last is not None else "20100101")
        try:
            df = pk.get_market_ohlcv_by_date(start, today_s, tic)
        except Exception:  # noqa: BLE001 — 종목 실패 = skip
            time.sleep(sleep)
            continue
        if df is None or df.empty:
            time.sleep(sleep)
            continue
        name = s.get("name") or ""
        market = _MARKET_MAP.get(str(s.get("market", "")).upper(), "KOSDAQ")
        rows = []
        for idx, r in df.iterrows():
            d = idx.date() if hasattr(idx, "date") else idx
            if last is not None and d <= last:
                continue  # 기존 날짜 제외 (증분만)
            rows.append((tic, name, market, d,
                         int(r.get("시가", 0) or 0), int(r.get("고가", 0) or 0),
                         int(r.get("저가", 0) or 0), int(r.get("종가", 0) or 0),
                         int(r.get("거래량", 0) or 0), int(r.get("거래대금", 0) or 0)))
        if rows:
            con.execute("BEGIN")
            con.executemany(
                "INSERT OR IGNORE INTO ohlcv (ticker,name,market,date,open,high,low,close,volume,value) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
            con.execute("COMMIT")
            added += len(rows)
        time.sleep(sleep)
    con.close()
    _log(f"레이크 증분 +{added} rows")
    return added


def generate_trail() -> int:
    """enrich → generate_smallcap_predictions (실 SMALLCAP_PATH append). 로깅 수 반환."""
    from api.builders.smallcap_corner_enrich import enrich_quant_factors
    from api.intelligence import prediction_layer as PL

    stocks = _corner_stocks()
    enriched = enrich_quant_factors(stocks)
    n_enriched = sum(1 for s in enriched if s.get("enriched"))
    # 방치 우량 부분군 멤버십
    neglected = []
    cf_path = os.path.join(DATA_DIR, "smallcap_corner_filters.json")
    if os.path.exists(cf_path):
        with open(cf_path, encoding="utf-8") as f:
            cf = json.load(f)
        for filt in cf.get("filters") or []:
            if filt.get("key") == "neglected_quality":
                neglected = [t.get("ticker") for t in (filt.get("tickers") or []) if t.get("ticker")]
                break
    rows = PL.generate_smallcap_predictions(enriched, neglected_tickers=neglected)
    _log(f"trail 생성 {len(rows)} ({n_enriched} enriched × {len(PL._SMALLCAP_FACTORS)} factor × {len(PL._HORIZONS)}h)")
    return len(rows)


def score_trail() -> dict:
    from scripts.score_smallcap_corner import score_smallcap
    res = score_smallcap()
    _log(f"채점 scored={res.get('scored', 0)} pending={res.get('pending', 0)} groups={res.get('groups', 0)}")
    return res


def _git(*args) -> int:
    return subprocess.call(["git", "-C", str(REPO), *args])


def _gitp(*args) -> int:
    # 비공개 보조 repo (.git-private, work-tree=repo root). ic_history(점수 held 2027) 전용.
    gd = str(REPO / ".git-private")
    return subprocess.call(["git", f"--git-dir={gd}", f"--work-tree={REPO}", *args])


def commit_push(push: bool) -> None:
    # raw trail = 로컬 레이크(repo 밖, 8MB/run) → 비커밋. ic_history(IC 결과, 점수 held 2027) → **비공개
    # repo(.git-private)**, 공개 main 무노출(RULE 7, PM 결정 2026-06-20). 공유 .gitignore 차단 → add -f.
    ic = "data/smallcap_corner_ic_history.jsonl"
    if not (REPO / ic).exists():
        _log("커밋 대상 없음 (ic_history 미생성 — 채점 도래 전)")
        return
    _gitp("add", "-f", ic)
    if _gitp("diff", "--cached", "--quiet") == 0:
        _log("변경 없음 — commit skip")
        return
    stamp = now_kst().strftime("%Y-%m-%dT%H:%M")
    _gitp("commit", "-m", f"data(smallcap): 코너 검증 IC 집계 append {stamp} (비공개, 점수 held 2027)")
    if push:
        _gitp("push")
        _log("ic_history 비공개 커밋/푸시 완료")
    else:
        _log("ic_history 비공개 커밋 완료 (--no-push)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true", help="커밋만, push 생략")
    ap.add_argument("--no-lake-update", action="store_true", help="레이크 증분 top-up 생략")
    args = ap.parse_args()

    _log(f"시작 {now_kst().strftime('%Y-%m-%d %H:%M KST')}")
    try:
        if not args.no_lake_update:
            update_lake_incremental(_corner_stocks())
    except Exception as e:  # noqa: BLE001 — 단계 실패 = 다음 단계 진행
        _log(f"레이크 증분 실패 (graceful): {type(e).__name__}: {e}")
    try:
        generate_trail()
    except Exception as e:  # noqa: BLE001
        _log(f"trail 생성 실패 (graceful): {type(e).__name__}: {e}")
    try:
        score_trail()
    except Exception as e:  # noqa: BLE001
        _log(f"채점 실패 (graceful): {type(e).__name__}: {e}")
    try:
        commit_push(push=not args.no_push)
    except Exception as e:  # noqa: BLE001
        _log(f"커밋/푸시 실패 (graceful): {type(e).__name__}: {e}")
    _log("완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""us_event_study_builder — 미장 이벤트스터디 반쪽을 CI 에서 만든다. 2026-08-09 신설.

**왜 분리했나.** `event_study_builder` 는 KR·US 를 한 번에 만들었는데, US 가격 출처가
`~/VERITY_data_lake/us_prices.duckdb`(로컬 맥, **갱신 스케줄 없음**)였다. 그 레이크는
백필 스크립트가 "이미 있는 ticker = skip" 구조라 **날짜가 늘지 않았고**, 2026-06-26 에
멈춘 채 43일을 갔다. 그 위에서 이벤트스터디가 계속 돌았으니 측정이 조용히 과거에 고정된
셈이다. 게다가 종목도 1,505(S&P1500)뿐이었다.

이제 US 반쪽은 `us_chart_history` 워크플로 안에서 만든다. 그 job 은 방금 5,188종(97.4%)
전 기간 일봉을 러너 디스크에 받아 둔 상태라 추가 수집 비용이 0이고, 워크플로 자체가
신선도 감시 대상이라 조용히 얼지 않는다. 산출물은 Blob 에 올리고 로컬 `event_study_builder`
가 조건부 GET 으로 받아 KR 반쪽과 합친다.

🚨 레포에 커밋하지 않는다 — 10MB 급이다. 이미 커밋되는 `event_study.json`(22MB) 위에
   또 얹으면 레포만 붓는다. 전달 경로 = Blob.

입력: data/us_catalyst_backfill.jsonl (SEC 8-K) + data/us_chart_history/{TICKER}.json
출력: data/us_event_study.json { _meta, stocks: { TICKER: {name, events:[...]} } }
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.builders.event_study_builder import (  # noqa: E402
    MAX_OCC,
    WINDOWS,
    _build_market,
    _load_price_series_history,
    _load_us_events,
)
from api.config import DATA_DIR, now_kst  # noqa: E402

HIST_DIR = os.path.join(DATA_DIR, "us_chart_history")
OUTPUT_PATH = os.path.join(DATA_DIR, "us_event_study.json")

# 가격 이력이 이만큼도 없으면 레이크가 안 붙은 상태로 본다(빈 산출 발행 금지).
MIN_PRICED_TICKERS = 200


def build() -> dict:
    events = _load_us_events()
    tickers = sorted({e["ticker"] for e in events})
    prices = _load_price_series_history(tickers, HIST_DIR)
    print(f"[us_event_study] 이벤트 {len(events):,} · 대상 티커 {len(tickers):,} · "
          f"가격 확보 {len(prices):,}")

    stocks = _build_market(events, prices=prices)
    total_occ = sum(len(g["occurrences"]) for s in stocks.values() for g in s["events"])
    return {
        "_meta": {
            "generated_at": now_kst().isoformat(),
            "source": "SEC 8-K(us_catalyst_backfill) + us_chart_history 일봉(yfinance auto_adjust)",
            "note": "종목별 자기 과거 8-K 당시 주가 변화. 종목 간 집계 없음 — 과거 사실 비교용"
                    "(예측·신호 아님). event_study_builder 가 KR 반쪽과 합쳐 발행한다.",
            "windows": WINDOWS,
            "max_occurrences": MAX_OCC,
            "event_count": len(events),
            "ticker_count": len(tickers),
            "priced_ticker_count": len(prices),
            "stock_count": len(stocks),
            "occurrence_count": total_occ,
        },
        "stocks": stocks,
    }


def main() -> int:
    if not os.path.isdir(HIST_DIR):
        print(f"[us_event_study] 가격 레이크 없음: {HIST_DIR} — 중단", file=sys.stderr)
        return 1
    doc = build()
    m = doc["_meta"]
    # 🚨 [[feedback_silent_total_failure_guard]] — 0 건인데 성공 종료하면 옛 Blob 본을
    #    빈 파일로 덮고도 워크플로는 초록이다. 없는 것보다 나쁘다.
    if m["priced_ticker_count"] < MIN_PRICED_TICKERS or not doc["stocks"]:
        print(f"[us_event_study] 가격 확보 {m['priced_ticker_count']} < {MIN_PRICED_TICKERS} "
              f"또는 산출 0 — 발행하지 않고 실패로 끝낸다", file=sys.stderr)
        return 1
    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUTPUT_PATH)
    size_mb = os.path.getsize(OUTPUT_PATH) / 1e6
    print(f"[us_event_study] {m['stock_count']:,} 종목 · {m['occurrence_count']:,} 이벤트 "
          f"· {size_mb:.1f}MB -> {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

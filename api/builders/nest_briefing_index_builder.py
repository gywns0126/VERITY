"""nest_briefing_index — 둥지(보유종목) 브리핑용 티커 색인.

🚨 왜 티커 색인인가 (회원별 발행이 아니라):
    회원 수만큼 서버에서 만들면 blob 캐시가 깨지고 비용이 회원 수에 비례한다.
    대신 **전역 색인 1개**를 캐시로 내려주고, 브라우저가 `/api/holdings` 로 받은
    본인 티커만 골라 렌더한다. 컴포넌트는 이미 그 API 를 호출하고 있어
    (PublicMorningBriefing 내 자산 섹션) 인증·조회 배선이 이미 있다.

🚨 기존 피드를 그대로 쓰지 않는 이유 = 크기.
    us_disclosure_feed 4.1MB + public_disclosure_feed 862KB 는 브라우저가 받기 어렵다.
    최근 창으로 자르고 종목당 상한을 둬서 압축한다.

RULE 7 — 공시 사실·일정만. 점수·등급·추천·매매의견 0. 제목은 원문 그대로, 링크는 원문 viewer.
RULE 6 — LLM 0. 결정론적 재배열뿐이다.

🚨 뉴스는 v1 에 없다. `news_flash.json` 200건이 **티커 연결 0/200** 이고,
   종목별 헤드라인은 `recommendations.json` 분석 풀(수십 종목)에만 있어
   임의 보유종목을 못 덮는다. 넣으려면 뉴스↔종목 매핑이 선행이다(별건).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KR_FEED = os.path.join(_ROOT, "data", "public_disclosure_feed.json")
US_FEED = os.path.join(_ROOT, "data", "us_disclosure_feed.json")
OUT_PATH = os.path.join(_ROOT, "data", "nest_briefing_index.json")

WINDOW_DAYS = 3          # 데일리 브리핑 = 최근 며칠. 길게 잡으면 "오늘 소식" 이 아니게 된다
MAX_PER_TICKER = 3       # 종목당 상한 — 크기 방어
KST = timezone(timedelta(hours=9))


def _now():
    return datetime.now(KST)


def _pack(feed_path: str, market: str, cutoff: str, out: dict) -> int:
    if not os.path.exists(feed_path):
        return 0
    with open(feed_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    n = 0
    for it in d.get("items") or []:
        tk = it.get("ticker")
        if not tk:
            continue
        evs = []
        for x in it.get("disclosures") or []:
            dt = x.get("date") or ""
            if dt < cutoff:
                continue
            evs.append({"d": dt, "t": (x.get("title") or "")[:80],
                        "u": x.get("source_url") or ""})
            if len(evs) >= MAX_PER_TICKER:
                break
        if not evs:
            continue
        evs.sort(key=lambda e: e["d"], reverse=True)
        out[tk] = {"n": (it.get("name") or "")[:30], "m": market, "ev": evs}
        n += 1
    return n


def main() -> int:
    try:
        now = _now()
        cutoff = (now.date() - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
        tickers: dict = {}
        n_kr = _pack(KR_FEED, "KR", cutoff, tickers)
        n_us = _pack(US_FEED, "US", cutoff, tickers)
        out = {
            "_meta": {
                "generated_at": now.isoformat(),
                "source": "DART 전자공시 + SEC EDGAR 8-K — 보유종목 조회용 티커 색인",
                "window_days": WINDOW_DAYS,
                "cutoff": cutoff,
                "max_per_ticker": MAX_PER_TICKER,
                # 🚨 total 은 n_kr+n_us 가 아니라 **실제 키 수**다. KR·US 피드에 같은
                #   티커가 겹치면 dict 에서 덮여쓰이는데 카운터는 두 번 센다(실측 800 vs 799).
                "counts": {"kr": n_kr, "us": n_us, "total": len(tickers)},
                # 🚨 자기신고 — 소비자가 "없음" 과 "안 담음" 을 구분할 수 있어야 한다
                "coverage_note": "공시가 창 안에 있는 종목만 실린다. 색인에 없는 티커 = "
                                 "그 창에 공시 없음(미수집 아님).",
                "news": "미포함 — news_flash 티커 연결 0/200, 종목별 헤드라인은 분석 풀 한정",
                "disclaimer": "공시 사실·일정만 · 점수·추천·매매의견 아님",
            },
            "tickers": tickers,
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        sz = os.path.getsize(OUT_PATH)
        print(f"[nest_briefing_index] logged=True · KR {n_kr} · US {n_us} · "
              f"총 {n_kr + n_us} 티커 · {sz:,}B -> {os.path.relpath(OUT_PATH, _ROOT)}",
              file=sys.stderr)
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[nest_briefing_index] FAILED: {e!r}", file=sys.stderr)
        print("[nest_briefing_index] logged=False", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

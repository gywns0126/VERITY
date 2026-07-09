#!/usr/bin/env python3
"""us_stock_names_ko — 美 종목 한글명 수집 (검색 한글 매칭용, 2026-07-09).

문제: 검색창이 US 종목을 영문명/티커로만 매칭 → "테라울프"(한글) 검색 실패(네이버는 됨).
해결: 네이버 종목 autocomplete(ac.stock.naver.com)로 US 티커별 한글명 수집 → data/us_stock_names_ko.json.
      universe_search 빌더가 name_ko 로 주입 → 한글 검색 매칭.

- 유니버스 = us_universe_combined(Polygon CS ∪ sp1500 ~5,313).
- 캐시 증분: 이미 있는 티커는 skip(이름은 안정적). 예산 가드(wall-clock)로 며칠 누적 가능.
- 네이버 = 이름 metadata only(시세·차트 재배포 아님). throttle + UA. RULE 7 = 사실(한글명)만.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMBINED_PATH = os.path.join(_ROOT, "data", "us_universe_combined.json")
OUT_PATH = os.path.join(_ROOT, "data", "us_stock_names_ko.json")

AC_URL = "https://ac.stock.naver.com/ac?q={q}&target=stock,worldstock,index"
THROTTLE = 0.35  # 네이버 burst rate-limit 회피 (0.2 는 버스트 시 빈 응답 유발)
MAX_SECONDS = int(os.environ.get("US_NAMES_KO_MAX_SECONDS", "1500"))  # 예산 가드(증분 누적)


def _kname(ticker: str) -> str:
    """네이버 autocomplete → 해당 US 티커 한글명 (code 정확일치 + USA). 없으면 ''.
    burst rate-limit(빈 응답) 대비 1회 재시도."""
    for _ in range(2):
        try:
            req = urllib.request.Request(AC_URL.format(q=urllib.parse.quote(ticker)),
                                         headers={"User-Agent": "Mozilla/5.0"})
            d = json.loads(urllib.request.urlopen(req, timeout=8).read())
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
            continue
        items = d.get("items", [])
        for it in items:
            if str(it.get("code", "")).upper() == ticker.upper() and str(it.get("nationCode", "")) == "USA":
                nm = str(it.get("name") or "").strip()
                if nm and any("가" <= c <= "힣" for c in nm):  # 한글 포함 시만
                    return nm
        if items:  # 응답 왔는데 매칭 실패 = 한글명 없음(재시도 무의미)
            return ""
        time.sleep(0.5)  # 빈 응답 = rate-limit 의심 → 재시도
    return ""


def main() -> int:
    ok = False
    try:
        try:
            combined = json.load(open(COMBINED_PATH, encoding="utf-8"))
            tickers = [str(t).strip().upper() for t in (combined.get("tickers") or []) if str(t).strip()]
        except (OSError, ValueError):
            print("[us_names_ko] combined 유니버스 부재 — skip", file=sys.stderr)
            return 0
        try:
            cache: Dict[str, str] = json.load(open(OUT_PATH, encoding="utf-8")).get("names", {})
        except (OSError, ValueError):
            cache = {}

        t0 = time.monotonic()
        fetched = 0
        for tk in tickers:
            if tk in cache:  # 증분 — 이미 수집분 skip (빈 문자열도 '시도함'으로 간주)
                continue
            if time.monotonic() - t0 > MAX_SECONDS:
                print(f"[us_names_ko] budget 도달 ({int(time.monotonic()-t0)}s) — 나머지 다음 회차", file=sys.stderr)
                break
            cache[tk] = _kname(tk)
            fetched += 1
            time.sleep(THROTTLE)

        got = sum(1 for v in cache.values() if v)
        doc = {
            "_meta": {"generated_at": datetime.now(KST).isoformat(),
                      "source": "네이버 종목 autocomplete (한글명 metadata)",
                      "total": len(cache), "with_ko": got, "fetched_this_run": fetched},
            "names": cache,
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        print(f"[us_names_ko] logged=True · 캐시 {len(cache)} · 한글명 {got} · 이번수집 {fetched}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[us_names_ko] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[us_names_ko] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

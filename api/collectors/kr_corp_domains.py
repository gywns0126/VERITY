#!/usr/bin/env python3
"""kr_corp_domains — KR 상장사 홈페이지 도메인 맵 (로고 파이프라인 기반, 2026-07-10).

용도: 토스 로고 핫링킹 제거(PM 결정 7/10) → Brandfetch(도메인 조회) + 공식 파비콘 폴백.
      둘 다 기업 도메인이 필요 — DART 기업개황(company.json) hm_url 로 전 종목 수집.

- 소스 = DART company.json (기존 ftc_group_equity 패턴 재사용). hm_url = 정적 정보 → 증분 캐시.
- 쿼터 = DART 20K/일 공유 ([[project_dart_api_2026_constraints]]) — 초회 ~1.6K콜, 이후 신규 상장만.
- 출력 = data/kr_corp_domains.json {names: {ticker: domain}}. 도메인 정규화(스킴·경로·포트 제거).
🚨 RULE 7 무관(메타데이터). RULE 4 — cron 등재 시 git add data/ broad.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PATH = os.path.join(_ROOT, "data", "kr_corp_domains.json")
REPORT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")

MAX_SECONDS = int(os.environ.get("KR_DOMAINS_MAX_SECONDS", "1500"))
THROTTLE = 0.12


def _norm_domain(url: str) -> str:
    """hm_url → 도메인만 (스킴·www 유지·경로·포트 제거). 유효하지 않으면 ''."""
    s = str(url or "").strip().lower()
    if not s or s in ("-", "n/a", "없음"):
        return ""
    s = re.sub(r"^https?://", "", s)
    s = s.split("/")[0].split("?")[0].split(":")[0].strip()
    # 도메인 형태 검증 (한글·공백 등 배제)
    if not re.match(r"^[a-z0-9][a-z0-9.\-]+\.[a-z]{2,}$", s):
        return ""
    return s


def main() -> int:
    ok = False
    try:
        from api.config import DART_API_KEY
        if not DART_API_KEY:
            print("[kr_domains] DART_API_KEY 없음 — skip", file=sys.stderr)
            return 0
        from api.collectors.dart_corp_code import load_mapping
        code_map = load_mapping()  # ticker → corp_code

        # 유니버스 = universe_search KR+KONEX 전체 (리포트 밖 종목 포함 — 9K 전량 커버 2026-07-10)
        uni_path = os.path.join(_ROOT, "data", "universe_search.json")
        try:
            uni = json.load(open(uni_path, encoding="utf-8")).get("stocks", [])
            tickers = [str(x.get("ticker")) for x in uni if x.get("market") in ("KR", "KONEX")
                       and re.match(r"^\d{6}$", str(x.get("ticker") or ""))]
        except (OSError, ValueError):
            rep = json.load(open(REPORT_PATH, encoding="utf-8"))
            tickers = [str(s.get("ticker")) for s in rep.get("stocks", [])
                       if re.match(r"^\d{6}$", str(s.get("ticker") or ""))]

        try:
            cache: Dict[str, str] = json.load(open(OUT_PATH, encoding="utf-8")).get("domains", {})
        except (OSError, ValueError):
            cache = {}

        t0 = time.monotonic()
        fetched = 0
        for tk in tickers:
            if tk in cache:  # 정적 정보 — 시도분 skip (빈값 포함: 홈페이지 없는 회사 재조회 무의미)
                continue
            if time.monotonic() - t0 > MAX_SECONDS:
                print(f"[kr_domains] budget 도달 — 나머지 다음 회차", file=sys.stderr)
                break
            corp = code_map.get(tk)
            if not corp:
                cache[tk] = ""
                continue
            try:
                url = f"https://opendart.fss.or.kr/api/company.json?crtfc_key={DART_API_KEY}&corp_code={corp}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace"))
                cache[tk] = _norm_domain(d.get("hm_url")) if d.get("status") == "000" else ""
            except Exception:  # noqa: BLE001
                cache[tk] = ""
            fetched += 1
            time.sleep(THROTTLE)

        got = sum(1 for v in cache.values() if v)
        doc = {
            "_meta": {"generated_at": datetime.now(KST).isoformat(),
                      "source": "DART 기업개황(company.json) hm_url",
                      "total": len(cache), "with_domain": got, "fetched_this_run": fetched},
            "domains": cache,
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        print(f"[kr_domains] logged=True · 캐시 {len(cache)} · 도메인 {got} · 이번수집 {fetched}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[kr_domains] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[kr_domains] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

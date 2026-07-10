#!/usr/bin/env python3
"""logo_map_builder — 종목별 최적 로고 URL 확정 (토스 핫링킹 완전 제거, PM 2026-07-10).

전략(실측 기반 2026-07-10):
  KR = ticker/{tk}.KS|.KQ 실로고 8/10 · 글자아이콘 2/10 → 글자아이콘(≤1KB)이면 domain/{도메인} 재시도.
  US = ticker/{tk} 커버 30/30. 미보유 = 엔트리 없음 → 컴포넌트 이니셜 아바타(기존).
  Brandfetch Logo Link = 브라우저 UA·Referer 컨텍스트 필수(실사이트 <img> 자연 충족), 무료 50만/월·출처표기 불요.

- 검증 콜은 빌드타임만(사용자 트래픽 쿼터 소모 0). 증분 캐시 — 확정분 skip, 신규 종목만.
- 출력 data/logo_map.json {logos: {ticker: "ticker/005930.KS" | "domain/xxx.com"}} — 컴포넌트가
  https://cdn.brandfetch.io/{path}?c={CLIENT_ID} 로 조립. 미등재 티커 = 이니셜.
🚨 RULE 7 무관(표시 자산). client id 는 공개 자산(임베드용) — 컴포넌트 상수 OK.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PATH = os.path.join(_ROOT, "data", "logo_map.json")
KR_REPORT = os.path.join(_ROOT, "data", "stock_report_public.json")
UNIVERSE_SEARCH = os.path.join(_ROOT, "data", "universe_search.json")

# ETF 운용사 · ETN 발행 증권사 브랜드 → 도메인 (2026-07-10 Brandfetch 실검증 — 전부 실로고 확인).
# 이름 프리픽스 startswith 매칭. 네트워크 0콜 즉시 배정.
BRAND_DOMAINS = [
    ("KODEX", "samsungfund.com"), ("TIGER", "tigeretf.com"), ("RISE", "kbam.co.kr"),
    ("KBSTAR", "kbam.co.kr"), ("ACE ", "aceetf.co.kr"), ("PLUS", "hanwhafund.co.kr"),
    ("ARIRANG", "hanwhafund.co.kr"), ("KIWOOM", "kiwoomam.com"), ("SOL ", "soletf.com"),
    ("HANARO", "nh-amundi.com"), ("TIMEFOLIO", "timefolio.co.kr"), ("TIME", "timefolio.co.kr"),
    ("WON ", "wooriib.com"), ("KoAct", "samsungactive.co.kr"), ("에셋플러스", "assetplus.co.kr"),
    ("1Q", "hanafn.com"), ("파워", "kyobo.com"), ("BNK", "bnkasset.co.kr"),
    ("UNICORN", "hdfund.co.kr"), ("MIDAS", "midasasset.com"), ("마이다스", "midasasset.com"),
    # ETN 증권사
    ("메리츠", "meritzsec.com"), ("한투", "truefriend.com"), ("KB ", "kbsec.com"),
    ("삼성 ", "samsungpop.com"), ("미래에셋", "securities.miraeasset.com"), ("신한", "shinhansec.com"),
    ("키움", "kiwoom.com"), ("N2", "nhqv.com"), ("하나 ", "hanaw.com"), ("대신", "daishin.com"),
]


def _brand_domain(name: str) -> str:
    nm = str(name or "").strip()
    for pref, dom in BRAND_DOMAINS:
        if nm.startswith(pref.strip()) and (len(pref.strip()) > 2 or nm.startswith(pref)):
            return dom
    return ""
KR_DOMAINS = os.path.join(_ROOT, "data", "kr_corp_domains.json")
US_COMBINED = os.path.join(_ROOT, "data", "us_universe_combined.json")

REAL_LOGO_MIN = 1000   # >1KB = 실로고, ≤ = Brandfetch 글자아이콘(이니셜과 동급 → 도메인 재시도)
MAX_SECONDS = int(os.environ.get("LOGO_MAP_MAX_SECONDS", "2400"))
THROTTLE = 0.12
HDR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
       "Referer": "https://refreshed-fern-675581.framer.app/"}


def _cid() -> str:
    v = os.environ.get("BRANDFETCH_CLIENT_ID", "").strip()
    if v:
        return v
    try:
        env = open(os.path.join(_ROOT, ".env"), encoding="utf-8").read()
        m = re.search(r"BRANDFETCH_client_ID=([A-Za-z0-9_\-]+)", env, re.IGNORECASE)
        return m.group(1) if m else ""
    except OSError:
        return ""


def _logo_size(path: str, cid: str) -> int:
    """Brandfetch 경로 → 이미지 바이트 수 (0=미보유/실패)."""
    url = f"https://cdn.brandfetch.io/{path}?c={cid}&fallback=404"
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=12)
        if "image" not in (r.headers.get("content-type") or ""):
            return 0
        return len(r.read())
    except Exception:  # noqa: BLE001
        return 0


def _resolve_kr(tk: str, market: str, domain: str, cid: str) -> Optional[str]:
    mk = (market or "").upper()
    sufs = ["KQ"] if "KOSDAQ" in mk else (["KS"] if mk else ["KS", "KQ"])  # 미상 = 양쪽 시도
    best_letter = None
    for suf in sufs:
        p = f"ticker/{tk}.{suf}"
        n = _logo_size(p, cid)
        if n > REAL_LOGO_MIN:
            return p
        if n > 0 and not best_letter:
            best_letter = p
        time.sleep(THROTTLE)
    if domain:
        p2 = f"domain/{domain}"
        if _logo_size(p2, cid) > REAL_LOGO_MIN:
            return p2
    return best_letter  # 글자아이콘이라도 Brandfetch 통일감 — 실측 310B


def main() -> int:
    ok = False
    try:
        cid = _cid()
        if not cid:
            print("[logo_map] BRANDFETCH_CLIENT_ID 없음 — skip", file=sys.stderr)
            return 0
        try:
            _prev = json.load(open(OUT_PATH, encoding="utf-8"))
            cache: Dict[str, str] = dict(_prev.get("logos", {}))
            cache.update({k: "" for k in (_prev.get("_tried") or {})})  # 미보유 시도분도 skip (증분)
        except (OSError, ValueError):
            cache = {}

        # 유니버스 = universe_search 전체 (KR+ETF+ETN+KONEX+US ≈ 9,363) — 검색되는 종목 전부 커버.
        uni = json.load(open(UNIVERSE_SEARCH, encoding="utf-8")).get("stocks", [])
        # KR 주식 시장구분(KS/KQ)은 리포트 market 사용, 미상은 domain-first + 양쪽 시도
        rep = json.load(open(KR_REPORT, encoding="utf-8"))
        mk_map = {str(s.get("ticker")): str(s.get("market") or "") for s in rep.get("stocks", [])}
        kr = [(str(x.get("ticker")), mk_map.get(str(x.get("ticker")), ""))
              for x in uni if x.get("market") in ("KR", "KONEX")
              and re.match(r"^\d{6}$", str(x.get("ticker") or ""))]
        etfn = [(str(x.get("ticker")), str(x.get("name") or "")) for x in uni
                if x.get("market") in ("ETF", "ETN")]
        try:
            domains = json.load(open(KR_DOMAINS, encoding="utf-8")).get("domains", {})
        except (OSError, ValueError):
            domains = {}
        us = [str(x.get("ticker")).upper() for x in uni if x.get("market") == "US"]

        t0 = time.monotonic()
        fetched = 0
        # ETF/ETN — 브랜드 프리픽스 → 운용사/증권사 도메인 (네트워크 0콜, 실검증 맵)
        n_brand = 0
        for tk, nm in etfn:
            if tk in cache:
                continue
            d = _brand_domain(nm)
            cache[tk] = f"domain/{d}" if d else ""
            n_brand += 1
        if n_brand:
            print(f"[logo_map] ETF/ETN 브랜드 배정 {n_brand}", file=sys.stderr)
        # KR — 티커 조회 → 도메인 재시도
        for tk, mk in kr:
            if tk in cache:
                continue
            if time.monotonic() - t0 > MAX_SECONDS:
                break
            p = _resolve_kr(tk, mk, domains.get(tk, ""), cid)
            cache[tk] = p or ""
            fetched += 1
            time.sleep(THROTTLE)
        # US — 티커 조회 (실측 30/30, 크기 무관 수용: 글자아이콘도 통일감)
        for tk in us:
            if tk in cache:
                continue
            if time.monotonic() - t0 > MAX_SECONDS:
                print("[logo_map] budget 도달 — 나머지 다음 회차", file=sys.stderr)
                break
            n = _logo_size(f"ticker/{tk}", cid)
            cache[tk] = f"ticker/{tk}" if n > 0 else ""
            fetched += 1
            time.sleep(THROTTLE)

        got = sum(1 for v in cache.values() if v)
        doc = {
            "_meta": {"generated_at": datetime.now(KST).isoformat(),
                      "source": "Brandfetch Logo Link 커버리지 실측 (빌드타임 확정)",
                      "total": len(cache), "with_logo": got, "fetched_this_run": fetched},
            "logos": {k: v for k, v in cache.items() if v},  # 발행은 보유분만 (경량)
            "_tried": {k: "" for k, v in cache.items() if not v},  # 증분 skip 용 시도 기록
        }
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        print(f"[logo_map] logged=True · 캐시 {len(cache)} · 로고 {got} · 이번확정 {fetched}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[logo_map] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[logo_map] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

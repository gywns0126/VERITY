#!/usr/bin/env python3
"""logo.dev 전수 커버리지 조사 → data/metadata/logo_coverage.json

왜 필요한가: 어느 종목이 비는지 정확히 알아야 검수 대상(사람이 볼 목록)이 정해진다.
표본으로는 비율만 알지 **누가 비는지**를 모른다.

🚨 두 함정을 코드로 막는다 (2026-08-22 실측에서 둘 다 밟았다):
 ① **모노그램 폴백** — 못 찾은 종목에 글자 타일을 **200 으로** 준다. 종목마다 글자가 달라
    해시 비교로는 안 걸린다. → `fallback=404` 필수. 이게 없으면 커버리지가 2배로 부풀려진다.
 ② **429 를 '로고 없음' 으로 오독** — 무료 티어는 짧은 창 버스트 제한이 있다(헤더 미노출).
    페이싱 없이 돌리면 커버리지가 81% → 15% 로 보인다. → 재시도 + 간격 + **429 는 결과에서
    분리**해 미측정으로 남긴다. 실패를 0 으로 세지 않는다.

사용: python3 scripts/logo/census.py [--limit N] [--token pk_...]
토큰 = 인자 > LOGODEV_TOKEN 환경변수 > .env 의 LOGODEV_TOKEN
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
import urllib3

urllib3.disable_warnings()
KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
UNIVERSE = os.path.join(_ROOT, "data", "stock_report_public.json")
OUT = os.path.join(_ROOT, "data", "metadata", "logo_coverage.json")
DOM_CACHE = os.path.join(_ROOT, "data", "metadata", "corp_homepage.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
PACE = 0.12          # 요청 간격(초) — 429 0건으로 실측된 값
MAX_RETRY = 4


def _token(arg):
    if arg:
        return arg
    if os.environ.get("LOGODEV_TOKEN"):
        return os.environ["LOGODEV_TOKEN"]
    try:
        for line in open(os.path.join(_ROOT, ".env"), encoding="utf-8", errors="ignore"):
            if "=" in line and line.split("=", 1)[0].strip() == "LOGODEV_TOKEN":
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def load_domains(tickers):
    """DART hm_url → 도메인. 캐시 우선 (DART 20K/일 아끼고 재실행을 빠르게)."""
    cache = {}
    if os.path.exists(DOM_CACHE):
        try:
            cache = json.load(open(DOM_CACHE, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}
    todo = [t for t in tickers if t not in cache]
    if todo:
        from api.config import DART_API_KEY
        from api.collectors.dart_corp_code import get_corp_code
        import concurrent.futures as cf

        def one(tk):
            try:
                cc = get_corp_code(tk)
                if not cc:
                    return tk, ""
                d = requests.get("https://opendart.fss.or.kr/api/company.json",
                                 params={"crtfc_key": DART_API_KEY, "corp_code": cc},
                                 timeout=12).json()
                u = (d.get("hm_url") or "").strip()
                return tk, (re.sub(r"^https?://", "", u).split("/")[0].replace("www.", "") if u else "")
            except Exception:  # noqa: BLE001
                return tk, ""
        print(f"[census] 도메인 신규 조회 {len(todo)}건 (캐시 {len(cache)})", file=sys.stderr)
        with cf.ThreadPoolExecutor(8) as ex:
            for tk, dom in ex.map(one, todo):
                cache[tk] = dom
        os.makedirs(os.path.dirname(DOM_CACHE), exist_ok=True)
        json.dump(cache, open(DOM_CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--token", default=None)
    a = ap.parse_args()
    token = _token(a.token)
    if not token:
        print("[census] 토큰 없음 — --token 또는 LOGODEV_TOKEN", file=sys.stderr)
        return 2

    doc = json.load(open(UNIVERSE, encoding="utf-8"))
    rows = [(s["ticker"], s.get("name") or s["ticker"], s.get("market") or "")
            for s in doc["stocks"] if str(s.get("ticker", "")).isdigit()]
    if a.limit:
        rows = rows[:a.limit]
    doms = load_domains([r[0] for r in rows])

    S = requests.Session()
    S.headers.update(UA)

    def hit(url):
        """200/404 만 결과로 인정. 429 는 재시도하고, 끝내 안 되면 None(미측정)."""
        for i in range(MAX_RETRY):
            try:
                r = S.get(url, params={"token": token, "size": 480, "fallback": "404"},
                          timeout=15, verify=False)
                if r.status_code != 429:
                    return r.status_code
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1.5 * (i + 1))
        return None

    out, t0 = [], time.monotonic()
    for i, (tk, nm, mk) in enumerate(rows):
        sfx = ".KS" if mk == "KOSPI" else ".KQ"
        st_t = hit(f"https://img.logo.dev/ticker/{tk}{sfx}")
        dom = doms.get(tk) or ""
        st_d = hit(f"https://img.logo.dev/{dom}") if dom else None
        out.append({"ticker": tk, "name": nm, "market": mk, "domain": dom,
                    "ticker_ok": st_t == 200, "domain_ok": st_d == 200,
                    "ticker_status": st_t, "domain_status": st_d})
        time.sleep(PACE)
        if (i + 1) % 100 == 0:
            cov = sum(1 for x in out if x["ticker_ok"] or x["domain_ok"]) / len(out)
            print(f"[census] {i+1}/{len(rows)} · 커버 {cov:.1%} · {int(time.monotonic()-t0)}s",
                  file=sys.stderr)

    n = len(out)
    have = [x for x in out if x["ticker_ok"] or x["domain_ok"]]
    unmeasured = [x for x in out if x["ticker_status"] is None and x["domain_status"] is None]
    doc_out = {
        "_meta": {
            "generated_at": datetime.now(KST).isoformat(),
            "source": "logo.dev Logo API (fallback=404 — 모노그램 배제)",
            "universe": n,
            "covered": len(have),
            "coverage": round(len(have) / n, 4) if n else 0,
            "missing": n - len(have) - len(unmeasured),
            "unmeasured_429": len(unmeasured),
            "note": ("🚨 fallback=404 없이 재면 모노그램 폴백이 200 으로 와서 커버리지가 약 2배로 "
                     "부풀려진다. 429 는 '로고 없음' 이 아니라 미측정으로 분리한다."),
        },
        "stocks": out,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(doc_out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[census] 완료 · 커버 {len(have)}/{n} = {len(have)/n:.1%} · "
          f"미측정(429) {len(unmeasured)} -> {os.path.relpath(OUT, _ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

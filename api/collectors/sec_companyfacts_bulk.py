# -*- coding: utf-8 -*-
"""sec_companyfacts_bulk — SEC 벌크 companyfacts 로 미장 재무 커버리지 전량화.

**왜**: 2026-08-08 실측 — 미장 유니버스 5,324종목인데 재무(`us_financials/`)는 **1,502종목
(28%)** 뿐이었다. SEC 한계가 아니라 `us_financials.yml` 의 `default: 'sp1500'` 이라는
**우리 설정**이었다. 그리고 재무에 종속된 축이 둘 더 있다 —
`us_stock_report_public`(28%) · `us_quarterly_public`(28%). 여기가 뚫리면 셋이 같이 오른다.

**왜 벌크인가**: 개별 companyfacts API 는 종목당 ~0.3s + submissions ~0.15s 라
5,324종목이면 **약 7.4시간** → GH Actions 6시간 한도를 넘는다. SEC 는 전 상장사 XBRL 을
zip 한 덩어리로 배포한다(2026-08-08 HEAD 실측 **1.34GB**) — 1회 다운로드로 대체된다.

    https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip

🚨 **파싱은 기존 코드를 그대로 쓴다.** `us_financials.build_ticker_snapshot` 에 facts 를
   주입할 뿐 산식·태그 alias·파생 계산은 한 줄도 새로 쓰지 않는다. 직접 파싱하면 그건
   같은 스키마가 아니라 다른 산출물이 된다(오늘 technical 순수함수 분리와 같은 규율).

🚨 **SIC 는 companyfacts 에 없다**(5/20 실측 확인). submissions.zip 은 1.48GB 로 또 무겁다.
   그래서 SIC 만 개별 HTTP 로 받는다 — SEC 한도 10 req/s, 5,324건 ≈ 9분이면 끝난다.
   SIC 가 필요한 이유 = 금융업 판정(`is_financial`) 이 revenue 태그 alias 를 가른다.
   실패해도 graceful(None) 이라 수집 자체는 멈추지 않는다.

🚨 **zip 은 레포에 두지 않는다.** 캐시 디렉토리(기본 시스템 임시경로)에 받고, 산출물인
   `data/us_financials/{TICKER}.json` 만 남긴다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.request
import zipfile
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from api.config import DATA_DIR
    _DATA = DATA_DIR
except Exception:  # 단독 실행 폴백
    _DATA = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

BULK_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
OUT_DIR = os.path.join(_DATA, "us_financials")
META_PATH = os.path.join(_DATA, "us_financials_bulk_meta.json")
UNIVERSE_PATHS = (
    os.path.join(_DATA, "us_universe_combined.json"),
    os.path.join(_DATA, "us_universe_sp1500.json"),
)

USER_AGENT = "VERITY research gywns0126@gmail.com"   # SEC 는 연락처 UA 를 요구한다
SIC_SLEEP = 0.11        # SEC 10 req/s 한도 — 넉넉히
_DL_CHUNK = 1 << 20


def _headers() -> Dict[str, str]:
    """🚨 Accept-Encoding 을 넣지 않는다 — urllib 은 gzip 응답을 자동 해제하지 않아
    JSON 파싱이 그대로 깨진다(2026-08-08 실측). zip 본체는 이미 압축이라 이득도 없다."""
    return {"User-Agent": USER_AGENT}


def download_bulk(dest: str, force: bool = False) -> str:
    """companyfacts.zip 내려받기. 이미 있고 크기가 맞으면 재사용(멱등)."""
    req = urllib.request.Request(BULK_URL, method="HEAD", headers=_headers())
    with urllib.request.urlopen(req, timeout=60) as r:
        remote = int(r.headers.get("Content-Length") or 0)
    if not force and os.path.exists(dest) and remote and os.path.getsize(dest) == remote:
        print(f"[bulk] 캐시 재사용 {dest} ({remote / 1e9:.2f}GB)", file=sys.stderr)
        return dest
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    t0 = time.time()
    with urllib.request.urlopen(urllib.request.Request(BULK_URL, headers=_headers()),
                                timeout=600) as r, open(tmp, "wb") as f:
        got = 0
        while True:
            b = r.read(_DL_CHUNK)
            if not b:
                break
            f.write(b)
            got += len(b)
            if got % (100 << 20) < _DL_CHUNK:
                print(f"[bulk] {got / 1e9:.2f}/{remote / 1e9:.2f}GB "
                      f"({time.time() - t0:.0f}s)", file=sys.stderr, flush=True)
    os.replace(tmp, dest)
    print(f"[bulk] 완료 {got / 1e9:.2f}GB · {time.time() - t0:.0f}s", file=sys.stderr)
    return dest


def load_ticker_cik() -> Dict[str, int]:
    """{TICKER: cik}. SEC 공식 매핑."""
    try:
        with urllib.request.urlopen(
                urllib.request.Request(TICKER_URL, headers=_headers()), timeout=60) as r:
            doc = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        print(f"[bulk] ticker 매핑 실패 {type(e).__name__}", file=sys.stderr)
        return {}
    out: Dict[str, int] = {}
    for v in (doc or {}).values():
        t = str((v or {}).get("ticker") or "").strip().upper()
        c = (v or {}).get("cik_str")
        if t and isinstance(c, int):
            out[t] = c
    return out


def load_universe() -> List[str]:
    from api.collectors.us_chart_history import load_universe as _u  # 단일 출처
    return _u()


def fetch_sic(cik: int) -> Tuple[Optional[int], Optional[str]]:
    """submissions endpoint 에서 SIC. 실패는 (None, None) — 수집을 멈추지 않는다."""
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=_headers()), timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        sic = d.get("sic")
        return (int(sic) if str(sic).isdigit() else None), (d.get("sicDescription") or None)
    except Exception:  # noqa: BLE001
        return None, None


def _existing() -> Set[str]:
    if not os.path.isdir(OUT_DIR):
        return set()
    return {os.path.splitext(f)[0] for f in os.listdir(OUT_DIR)
            if f.endswith(".json") and not f.startswith("_")}


def collect(zip_path: str, limit: int = 0, refresh: bool = False,
            skip_sic: bool = False) -> Dict[str, Any]:
    from api.intelligence import us_financials as usf

    universe = load_universe()
    if not universe:
        return {"status": "no_universe"}
    tmap = load_ticker_cik()
    if not tmap:
        return {"status": "no_ticker_map"}

    have = set() if refresh else _existing()
    todo = [t for t in universe if t not in have and t.upper() in tmap]
    no_cik = [t for t in universe if t.upper() not in tmap]
    if limit:
        todo = todo[:limit]
    os.makedirs(OUT_DIR, exist_ok=True)

    want_cik = {tmap[t.upper()]: t for t in todo}
    ok, no_facts, errs = 0, [], []
    t0 = time.time()

    with zipfile.ZipFile(zip_path) as z:
        names = {n for n in z.namelist() if n.startswith("CIK") and n.endswith(".json")}
        for i, (cik, ticker) in enumerate(sorted(want_cik.items()), 1):
            member = f"CIK{cik:010d}.json"
            if member not in names:
                no_facts.append(ticker)
                continue
            try:
                facts = json.loads(z.read(member).decode("utf-8", "replace"))
            except Exception:  # noqa: BLE001
                no_facts.append(ticker)
                continue
            sic_pair = (None, None) if skip_sic else fetch_sic(cik)
            if not skip_sic:
                time.sleep(SIC_SLEEP)
            try:
                snap = usf.build_ticker_snapshot(ticker, cik, facts=facts, sic_pair=sic_pair)
            except Exception as e:  # noqa: BLE001
                errs.append(f"{ticker}: {type(e).__name__}")
                continue
            if "_error" in snap:
                errs.append(f"{ticker}: {snap['_error']}")
                continue
            tmp = os.path.join(OUT_DIR, f"{ticker}.json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False, indent=2)
            os.replace(tmp, os.path.join(OUT_DIR, f"{ticker}.json"))
            ok += 1
            if i % 200 == 0:
                print(f"[bulk] {i}/{len(want_cik)} · ok {ok} · {time.time() - t0:.0f}s",
                      file=sys.stderr, flush=True)

    total = _existing()
    meta = {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                               time.localtime(time.time() + 9 * 3600)),
        "universe": len(universe), "have": len(total),
        "fetched_now": ok, "no_facts": len(no_facts), "no_cik": len(no_cik),
        "errors": len(errs), "error_sample": errs[:20],
        "source": "SEC bulk companyfacts.zip + submissions(SIC only)",
        "note": ("🚨 커버리지 부족은 사유를 단정하지 않는다 — no_cik(티커 매핑 부재)와 "
                 "no_facts(XBRL 미제출: ETF·신규상장·외국발행사)를 분리 기록한다."),
    }
    tmp = META_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    os.replace(tmp, META_PATH)
    return {"status": "ok", "elapsed_sec": round(time.time() - t0, 1),
            **{k: meta[k] for k in ("universe", "have", "fetched_now",
                                    "no_facts", "no_cik", "errors")}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(tempfile.gettempdir(), "sec_companyfacts.zip"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true", help="이미 있는 종목도 재생성")
    ap.add_argument("--force-download", action="store_true")
    ap.add_argument("--skip-sic", action="store_true",
                    help="SIC HTTP 생략(빠름). 🚨 금융업 revenue alias 정확도 하락")
    ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args()

    if a.plan_only:
        u = load_universe()
        print(f"[bulk] 유니버스 {len(u):,} · 보유 {len(_existing()):,} · "
              f"잔여 {len([t for t in u if t not in _existing()]):,}")
        return 0

    z = download_bulk(a.cache, force=a.force_download)
    r = collect(z, a.limit, a.refresh, a.skip_sic)
    if r.get("status") != "ok":
        print(f"[bulk] {r.get('status')}", file=sys.stderr)
        return 1
    print(f"[bulk] 보유 {r['have']:,}/{r['universe']:,} · 신규 {r['fetched_now']:,} · "
          f"XBRL부재 {r['no_facts']} · CIK부재 {r['no_cik']} · 오류 {r['errors']} · "
          f"{r['elapsed_sec']}s")
    # 🚨 대상이 있는데 한 건도 못 만들면 성공으로 끝내지 않는다 (오늘 us_chart_daily 학습).
    if r["fetched_now"] == 0 and r["have"] == 0:
        print("[bulk] 🚨 전량 실패", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

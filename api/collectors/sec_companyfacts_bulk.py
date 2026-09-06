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

🚨 **SIC 도 벌크로 받는다**(2026-08-08 재설계). companyfacts 에는 SIC 가 없어(5/20 실측)
   처음에는 종목당 submissions HTTP 를 썼는데 **실패했다**:
     · 프로파일상 0.57s/콜인데 실측 10s/종목 — SEC 가 대량 클라이언트를 지연 처리한다
     · 실측 **SIC 확보율 42%** (표본 400 중 166)
     · SIC 실패 = `is_financial=False` 로 떨어져 **금융주 revenue 태그가 잘못 잡힌다**
       (은행은 RevenuesNetOfInterestExpense 계열을 써야 하는데 부분 계약수익이 잡힘)
   즉 느린 것보다 **틀리는 게 문제**였다. submissions.zip(1.48GB)을 1회 받아
   SIC 를 100% 확보한다 — HTTP 0회, 전체 수집이 분 단위로 떨어진다.

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
SUBMISSIONS_URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
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
_INLINE_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A"}


def _headers() -> Dict[str, str]:
    """🚨 Accept-Encoding 을 넣지 않는다 — urllib 은 gzip 응답을 자동 해제하지 않아
    JSON 파싱이 그대로 깨진다(2026-08-08 실측). zip 본체는 이미 압축이라 이득도 없다."""
    return {"User-Agent": USER_AGENT}


def download_bulk(dest: str, force: bool = False, url: str = BULK_URL) -> str:
    """SEC 벌크 zip 내려받기. 이미 있고 크기가 맞으면 재사용(멱등)."""
    req = urllib.request.Request(url, method="HEAD", headers=_headers())
    with urllib.request.urlopen(req, timeout=60) as r:
        remote = int(r.headers.get("Content-Length") or 0)
    if not force and os.path.exists(dest) and remote and os.path.getsize(dest) == remote:
        print(f"[bulk] 캐시 재사용 {dest} ({remote / 1e9:.2f}GB)", file=sys.stderr)
        return dest
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    t0 = time.time()
    with urllib.request.urlopen(urllib.request.Request(url, headers=_headers()),
                                timeout=1800) as r, open(tmp, "wb") as f:
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
    """개별 submissions endpoint 에서 SIC. 🚨 대량 사용 금지 — SEC 지연 처리로 확보율 42%.

    벌크 경로는 `sic_index_from_zip` 을 쓴다. 이 함수는 단건 확인·폴백 전용으로 남긴다.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=_headers()), timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        sic = d.get("sic")
        return (int(sic) if str(sic).isdigit() else None), (d.get("sicDescription") or None)
    except Exception:  # noqa: BLE001
        return None, None


def submission_indexes_from_zip(
    zip_path: str, want: Set[int]
) -> Tuple[
    Dict[int, Tuple[Optional[int], Optional[str]]],
    Dict[int, Dict[str, Any]],
]:
    """submissions.zip → SIC + latest inline financial filing indexes. HTTP 0회.

    🚨 CIK##########.json 만 읽는다. 같은 zip 에 CIK...-submissions-001.json(과거 공시
       분할본)이 섞여 있는데 그건 SIC 를 갖지 않아 덮어쓰면 결손이 된다.
    """
    sic_out: Dict[int, Tuple[Optional[int], Optional[str]]] = {}
    filing_out: Dict[int, Dict[str, Any]] = {}
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not (name.startswith("CIK") and name.endswith(".json")) or "-submissions-" in name:
                continue
            digits = name[3:-5]
            if not digits.isdigit():
                continue
            cik = int(digits)
            if cik not in want:
                continue
            try:
                d = json.loads(z.read(name).decode("utf-8", "replace"))
            except Exception:  # noqa: BLE001
                continue
            sic = d.get("sic")
            sic_out[cik] = ((int(sic) if str(sic).isdigit() else None),
                            (d.get("sicDescription") or None))
            recent = ((d.get("filings") or {}).get("recent") or {})
            forms = recent.get("form") or []
            candidates: List[Dict[str, Any]] = []
            for i, form in enumerate(forms):
                if form not in _INLINE_FORMS:
                    continue
                def _at(key: str, default: Any = "") -> Any:
                    values = recent.get(key) or []
                    return values[i] if i < len(values) else default
                candidates.append({
                    "form": form,
                    "filing_date": _at("filingDate"),
                    "report_date": _at("reportDate"),
                    "accession": _at("accessionNumber"),
                    "primary_document": _at("primaryDocument"),
                    "is_xbrl": bool(_at("isXBRL", 0)),
                    "is_inline_xbrl": bool(_at("isInlineXBRL", 0)),
                })
            if candidates:
                filing_out[cik] = max(
                    candidates,
                    key=lambda row: (str(row.get("filing_date") or ""),
                                     str(row.get("accession") or "")),
                )
    return sic_out, filing_out


def sic_index_from_zip(zip_path: str, want: Set[int]) -> Dict[int, Tuple[Optional[int], Optional[str]]]:
    """Compatibility wrapper for callers that need only SIC metadata."""
    return submission_indexes_from_zip(zip_path, want)[0]


def _existing() -> Set[str]:
    if not os.path.isdir(OUT_DIR):
        return set()
    return {os.path.splitext(f)[0] for f in os.listdir(OUT_DIR)
            if f.endswith(".json") and not f.startswith("_")}


def collect(zip_path: str, limit: int = 0, refresh: bool = False,
            skip_sic: bool = False,
            sic_index: Optional[Dict[int, Tuple[Optional[int], Optional[str]]]] = None,
            filing_index: Optional[Dict[int, Dict[str, Any]]] = None) -> Dict[str, Any]:
    from api.intelligence import us_financials as usf
    from api.collectors import sec_inline_xbrl as inline

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
    inline_attempted = inline_ok = inline_failed = 0
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
            if skip_sic:
                sic_pair = (None, None)
            elif sic_index is not None:
                sic_pair = sic_index.get(cik, (None, None))   # 벌크 — HTTP 0회
            else:
                sic_pair = fetch_sic(cik)
                time.sleep(SIC_SLEEP)
            latest_filing = (filing_index or {}).get(cik)
            inline_state: Dict[str, Any] = {"status": "not_needed"}
            if latest_filing:
                accession = str(latest_filing.get("accession") or "")
                present = inline.has_accession(facts, accession)
                inline_state = {
                    "status": "companyfacts_current" if present else "source_lag",
                    "accession": accession,
                    "report_date": latest_filing.get("report_date"),
                    "form": latest_filing.get("form"),
                }
                if (not present and latest_filing.get("is_inline_xbrl")
                        and latest_filing.get("primary_document")):
                    inline_attempted += 1
                    try:
                        overlay = inline.fetch_inline_xbrl(cik, latest_filing)
                        fact_count = int((overlay.get("_inline_meta") or {}).get("fact_count") or 0)
                        if fact_count <= 0:
                            raise ValueError("no consolidated us-gaap facts")
                        facts = inline.merge_companyfacts(facts, overlay)
                        inline_ok += 1
                        inline_state.update({
                            "status": "inline_fallback",
                            "fact_count": fact_count,
                            "source_url": (overlay.get("_inline_meta") or {}).get("source_url"),
                        })
                    except Exception as e:  # noqa: BLE001
                        inline_failed += 1
                        inline_state.update({
                            "status": "source_lag",
                            "fallback_error": type(e).__name__,
                        })
                    time.sleep(SIC_SLEEP)
            try:
                snap = usf.build_ticker_snapshot(ticker, cik, facts=facts, sic_pair=sic_pair)
            except Exception as e:  # noqa: BLE001
                errs.append(f"{ticker}: {type(e).__name__}")
                continue
            if "_error" in snap:
                errs.append(f"{ticker}: {snap['_error']}")
                continue
            snap.setdefault("meta", {})["latest_financial_filing"] = latest_filing
            snap["meta"]["latest_filing_sync"] = inline_state
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
        "inline_fallback_attempted": inline_attempted,
        "inline_fallback_ok": inline_ok,
        "inline_fallback_failed": inline_failed,
        "source": "SEC bulk companyfacts.zip + submissions(SIC/latest filing) + inline XBRL fallback",
        "note": ("🚨 커버리지 부족은 사유를 단정하지 않는다 — no_cik(티커 매핑 부재)와 "
                 "no_facts(XBRL 미제출: ETF·신규상장·외국발행사)를 분리 기록한다."),
    }
    tmp = META_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    os.replace(tmp, META_PATH)
    return {"status": "ok", "elapsed_sec": round(time.time() - t0, 1),
            **{k: meta[k] for k in ("universe", "have", "fetched_now",
                                    "no_facts", "no_cik", "errors",
                                    "inline_fallback_attempted", "inline_fallback_ok",
                                    "inline_fallback_failed")}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(tempfile.gettempdir(), "sec_companyfacts.zip"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true", help="이미 있는 종목도 재생성")
    ap.add_argument("--force-download", action="store_true")
    ap.add_argument("--sub-cache",
                    default=os.path.join(tempfile.gettempdir(), "sec_submissions.zip"))
    ap.add_argument("--skip-sic", action="store_true",
                    help="SIC 생략. 🚨 금융업 revenue alias 정확도 하락 — 디버그 전용")
    ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args()

    if a.plan_only:
        u = load_universe()
        print(f"[bulk] 유니버스 {len(u):,} · 보유 {len(_existing()):,} · "
              f"잔여 {len([t for t in u if t not in _existing()]):,}")
        return 0

    z = download_bulk(a.cache, force=a.force_download)

    sic_index = None
    filing_index = None
    if not a.skip_sic:
        # 🚨 SIC 는 벌크로 받는다. 개별 HTTP 는 SEC 지연 처리로 확보율 42% 였다 —
        #    느린 것보다 금융주 revenue 태그가 틀리는 게 문제였다.
        sz = download_bulk(a.sub_cache, force=a.force_download, url=SUBMISSIONS_URL)
        tmap = load_ticker_cik()
        want = {tmap[t.upper()] for t in load_universe() if t.upper() in tmap}
        t0 = time.time()
        sic_index, filing_index = submission_indexes_from_zip(sz, want)
        got = sum(1 for v in sic_index.values() if v[0] is not None)
        print(f"[bulk] SIC 색인 {got:,}/{len(want):,} "
              f"({got / max(len(want), 1) * 100:.1f}%) · {time.time() - t0:.0f}s",
              file=sys.stderr)

    r = collect(z, a.limit, a.refresh, a.skip_sic,
                sic_index=sic_index, filing_index=filing_index)
    if r.get("status") != "ok":
        print(f"[bulk] {r.get('status')}", file=sys.stderr)
        return 1
    print(f"[bulk] 보유 {r['have']:,}/{r['universe']:,} · 신규 {r['fetched_now']:,} · "
          f"XBRL부재 {r['no_facts']} · CIK부재 {r['no_cik']} · 오류 {r['errors']} · "
          f"inline 보충 {r['inline_fallback_ok']}/{r['inline_fallback_attempted']} "
          f"(실패 {r['inline_fallback_failed']}) · "
          f"{r['elapsed_sec']}s")
    # 🚨 대상이 있는데 한 건도 못 만들면 성공으로 끝내지 않는다 (오늘 us_chart_daily 학습).
    if r["fetched_now"] == 0 and r["have"] == 0:
        print("[bulk] 🚨 전량 실패", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

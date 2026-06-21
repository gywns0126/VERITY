"""us_major_holdings_public_builder — 공개 터미널 美 대량보유(5%+) SC 13D/13G 빌더.

2026-06-22 신설. KR 5%+ 대량보유 공시(DART) 의 美 짝 = SEC Schedule 13D/13G.
[[project_us_financials_sec_edgar]] (b) 후속 / [[feedback_us_expansion_settled_no_relitigate]].
13D = 행동주의(경영참여 의도) / 13G = 수동(5%+ 단순보유). 증권사·토스에 없는 forensics.

RULE 10 검증(2026-06-22): SC 13D/13G·SCHEDULE 13D/13G(+/A) 는 **대상회사 CIK submissions 에
  cross-index** → Form4 와 동일 per-ticker 패턴(CUSIP 매핑 불요). modern(2024-12+) 의무 XML
  primary_doc.xml = 구조화(reportingPersonName·classPercent·amountBeneficiallyOwned·eventDate).

설계 = us_insider_trades_public_builder(Form4) 와 동일: sp1500 전 종목 rotation + carry-forward +
  wall-clock budget + SEC 10 req/s. 공유 헬퍼(universe·CIK map·rotation) import 로 단일 출처.
🚨 RULE 7 = 공시 사실만(보고자·지분율·주식수·날짜·13D/13G·원문). 자체 점수·매매신호 0. 관측-only.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from api.builders.us_insider_trades_public_builder import (
    SEC_UA, SEC_SUBMISSIONS, _now_kst, _float, _txt,
    _ticker_cik_map, _ordered_universe,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_major_holdings.json")
SEC_PRIMARY = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/primary_doc.xml"
SEC_INDEX = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/{accn}-index.htm"

# 대상회사 submissions 의 13D/13G 계열 form (대문자 비교).
FORM_SET = {
    "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A",
    "SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A",
}

WINDOW_DAYS = 365
MAX_FILINGS = 20           # 종목당 노출 상한
PER_TICKER_CAP = 10        # 종목당 primary_doc.xml 파싱 상한
SEC_DELAY = 0.13
MAX_SECONDS = int(os.environ.get("US_HOLDINGS_MAX_SECONDS", "2100"))
MAX_CALLS = int(os.environ.get("US_HOLDINGS_MAX_CALLS", "12000"))


def _form_type(form: str) -> str:
    """form → '13D'(행동주의) / '13G'(수동) + 정정(/A) 표기."""
    amend = "/A" in form
    base = "13D" if "13D" in form else "13G" if "13G" in form else "13?"
    return base + ("/A" if amend else "")


def _strip_ns(xml_text: str) -> str:
    """namespace 제거 (schedule13g/13d + com:) → local tag 파싱."""
    x = re.sub(r'\sxmlns(:\w+)?="[^"]*"', "", xml_text)
    x = re.sub(r"<(/?)\w+:", r"<\1", x)
    return x


def _parse_13dg(xml_text: str) -> Optional[Tuple[str, Optional[float], int, str, str]]:
    """primary_doc.xml → (filer, pct, shares, class, event_date). 구조화 부재 시 None."""
    try:
        root = ET.fromstring(_strip_ns(xml_text))
    except ET.ParseError:
        return None
    filer = _txt(root.find(".//reportingPersonName"))
    if not filer:
        filer = _txt(root.find(".//filingPersonName"))
    pct_raw = _txt(root.find(".//classPercent"))
    pct = _float(pct_raw) if pct_raw else None
    shares = int(_float(_txt(root.find(".//reportingPersonBeneficiallyOwnedAggregateNumberOfShares"))
                         or _txt(root.find(".//amountBeneficiallyOwned"))))
    cls = _txt(root.find(".//securitiesClassTitle"))
    ev = _txt(root.find(".//eventDateRequiresFilingThisStatement"))
    if not (filer or pct is not None or shares):
        return None
    return filer, pct, shares, cls, ev


def _load_prev() -> Dict[str, Dict[str, Any]]:
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        return {str(s.get("ticker") or ""): s for s in (doc.get("stocks") or []) if s.get("ticker")}
    except (OSError, ValueError):
        return {}


def main() -> int:
    ok = False
    try:
        import requests

        cutoff = (_now_kst().date() - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
        today = _now_kst().date().strftime("%Y-%m-%d")
        merged = _load_prev()
        order = _ordered_universe()

        sess = requests.Session()
        try:
            cik_map = _ticker_cik_map(sess)
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"[us_holdings] SEC ticker map 실패: {e!r} — skip(이전 보존)", file=sys.stderr)
            return 0

        t0 = time.monotonic()
        calls = collected = 0
        for tk in order:
            if time.monotonic() - t0 > MAX_SECONDS or calls >= MAX_CALLS:
                print(f"[us_holdings] budget 도달 (calls={calls}, {int(time.monotonic()-t0)}s) — 나머지 carry-forward", file=sys.stderr)
                break
            cik = cik_map.get(tk)
            if not cik:
                continue
            try:
                sub = sess.get(SEC_SUBMISSIONS.format(cik10=cik), headers={"User-Agent": SEC_UA}, timeout=15)
                calls += 1
                time.sleep(SEC_DELAY)
                if sub.status_code != 200:
                    continue
                rec = sub.json().get("filings", {}).get("recent", {})
            except (requests.RequestException, ValueError):
                continue
            forms = rec.get("form", [])
            dates = rec.get("filingDate", [])
            accns = rec.get("accessionNumber", [])

            filings: List[Dict[str, Any]] = []
            n_13d = n_13g = n_dg = 0
            per = 0
            for i in range(len(forms)):
                if forms[i].upper() not in FORM_SET or dates[i] < cutoff:
                    continue
                n_dg += 1
                if per >= PER_TICKER_CAP or calls >= MAX_CALLS:
                    break
                ftype = _form_type(forms[i].upper())
                if ftype.startswith("13D"):
                    n_13d += 1
                else:
                    n_13g += 1
                accn = accns[i]
                accn_nodash = accn.replace("-", "")
                filer = cls = ev = ""
                pct: Optional[float] = None
                shares = 0
                try:
                    pr = sess.get(SEC_PRIMARY.format(cik=int(cik), accn_nodash=accn_nodash),
                                  headers={"User-Agent": SEC_UA}, timeout=12)
                    calls += 1
                    per += 1
                    time.sleep(SEC_DELAY)
                    if pr.status_code == 200:
                        parsed = _parse_13dg(pr.text)
                        if parsed:
                            filer, pct, shares, cls, ev = parsed
                except requests.RequestException:
                    pass
                filings.append({
                    "date": dates[i],
                    "event_date": ev,
                    "type": ftype,                 # 13D(행동주의) / 13G(수동) + /A 정정
                    "filer": filer,                # 대량보유 신고자
                    "pct": pct,                    # 지분율(%)
                    "shares": shares,
                    "class": cls,
                    "source_url": SEC_INDEX.format(cik=int(cik), accn_nodash=accn_nodash, accn=accn),
                })

            if filings:
                filings.sort(key=lambda x: x["date"], reverse=True)
                pcts = [f["pct"] for f in filings if f["pct"] is not None]
                merged[tk] = {
                    "ticker": tk, "name": tk, "cik": cik,
                    "latest_pct": pcts[0] if pcts else None,
                    "n_13d": n_13d, "n_13g": n_13g, "total": len(filings),
                    "filings": filings[:MAX_FILINGS], "collected_at": today,
                }
                collected += 1
            elif n_dg == 0:
                # 권위적 공백(200 + 윈도우 내 13D/G 0건) — aged out.
                merged.pop(tk, None)
                collected += 1
            # else: 13D/G 존재하나 파싱 0 → 이전 보존

        # 정렬: 최근 신고일 desc (freshness).
        stocks = sorted(merged.values(), key=lambda s: (s.get("filings") or [{}])[0].get("date", ""), reverse=True)

        if not stocks and os.path.isfile(OUTPUT_PATH):
            print("[us_holdings] 0 종목 — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0

        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "SEC EDGAR Schedule 13D/13G (5%+ 대량보유)",
                "window_days": WINDOW_DAYS,
                "count": len(stocks),
                "universe": len(order),
                "collected_today": collected,
                "note": "공시 사실만 — 신고자·지분율·주식수·날짜·13D(행동주의)/13G(수동)·원문. 자체 점수·매매신호 아님 (RULE 7). KR 5%+ 대량보유의 美 짝. 전 종목(sp1500) 회전 수집.",
            },
            "stocks": stocks,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[us_holdings] logged=True · {len(stocks)} 종목(누적) · 오늘수집 {collected}/{len(order)} · calls={calls} -> {os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[us_holdings] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[us_holdings] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
